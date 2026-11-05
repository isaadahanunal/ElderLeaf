"""Report agent: after the masks, Muse Spark turns the measured facts into one plain-language report.

Follows the plan (docs/Meta Hackathon Proje Planı.docx, "Metrikler ve agent şeması"):
- Every number is computed in code; the LLM only words them. Statuses (typical / attention / info),
  health likelihoods and the "consult an agronomist" flag are set in code.
- Tools, each a step in the analysis trace: get_plot_history, lookup_crop_info and get_weather run in
  pipeline.py (crop library + FAO-56 water need, the numbers the app shows); here: assess_health,
  run_sam (only when the agent asks to look closer at a possible sign it sees in the photo),
  write_summary and validate.
- Validator: every number in the text must match a fact, health signs must be ones measured in code,
  and no pesticide or chemical names, doses or disease names. A failed check goes back to the model
  with the problems (once); after that the code's own template text is used, so the writer never fails
  an analysis. The grower's experience (from their profile) sets the tone.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .agent import _combine, _llm_image, clean_phrase
from .health import HOW, coverage_on_crop, likelihood, measure_color
from .llm import LLMClient, LLMResult, image_part
from .masks import clean_instances
from .sam import Instance, SamClient
from .schemas import AnalysisResult, Comparison, ContextItem, Health, HealthSign, Metrics, Report

CONSULT_CONFIDENCE = 0.6  # plan: consult flag when confidence < 0.6
LESION_CONSULT_PCT = 5.0  # plan: consult flag when the spot share passes a threshold
LOW_QUALITY_FACTOR = 0.8  # a poor photo lowers the health confidence
DENSITY_LOW, DENSITY_HIGH = 0.6, 1.5  # counted / expected plants from the grower's spacing
MAX_FIX_ROUNDS = 1  # validator failures sent back to the model
CLOSER_SIGNS = ("leaf_spots", "holes", "dry_leaves", "wilting", "other_damage")
SIGN_LABELS = {"yellowing": "Yellowing", "browning": "Browning", "leaf_spots": "Leaf spots", "holes": "Holes in leaves",
               "dry_leaves": "Dry leaves", "wilting": "Wilting", "other_damage": "Leaf damage"}
EXPERIENCE_TONE = {
    "just_started": "first season: explain every term in a few words",
    "few_seasons": "a season or two: short and practical",
    "experienced": "experienced: concise, numbers first",
}

_enabled: bool | None = None


def enabled() -> bool:
    return _enabled if _enabled is not None else os.environ.get("REPORT_AGENT", "1") != "0"


def set_enabled(value: bool | None) -> None:
    """Tests switch the LLM writer on or off (None = REPORT_AGENT from the environment)."""
    global _enabled
    _enabled = value


# ------------------------------------------------------------------------------ prompts

SYSTEM = """You are ElderLeaf's report writer for a grower. Code has measured one top-down photo of their plot; you get those facts and the photo.
Rules:
- Use only numbers that appear in the facts. You may round them, but never compute, estimate or invent a number, a range or a percentage.
- Health: talk only about the possible signs listed in the facts, as possibilities that can have several causes (water, light, nutrients, age, pests or disease). Never diagnose, never name a disease, never recommend a pesticide, fungicide or any chemical, product or dose.
- Keep each line's status: "attention" says what to check or do, "typical" reassures, "info" explains.
- Match the grower's experience (facts.grower): first season = explain every term in a few words; a season or two = short and practical; experienced = concise, numbers first.
- Plain, kind English: short sentences, no jargon, at most 2 sentences per text.
Answer with one JSON object and nothing else."""

USER = """Facts measured by code (JSON):
{facts}

{closer}Write the report as:
{{"action": "final",
 "summary": "<2-3 sentences, at most 70 words: what the grower should know today>",
 "headline": "<one sentence>",
 "lines": {{"<line id>": "<the line rewritten for this grower, same status>", ...}},
 "health_summary": "<1-2 sentences about plant health>",
 "signs": {{"<possible sign type from health.possible_signs>": "<what it means, as a possibility>", ...}},
 "change": <"1-2 sentences on what changed since the last photo" or null>,
 "next_steps": ["<short action>", ... at most 3]}}"""

CLOSER = """Look at the photo first. If the crop plants show a possible problem that health.possible_signs does not cover (for example spots, holes or dry leaves), you may ask SAM 3.1 to look closer once, instead of the report:
{{"action": "look_closer", "prompt": "<1-4 word SAM phrase, e.g. leaf spot>", "sign_type": "<one of {signs}>", "why": "<short>"}}
"""

CLOSER_RESULT = """SAM 3.1 looked for "{prompt}": {found} masks, {on_crop} on crop plants, covering {share}% of the crop area. The facts now include this:
{health}
Now write the report (action "final")."""

FIX = """Your report broke these rules:
{errors}
Reply with the corrected JSON report only."""


# ------------------------------------------------------------------------------ validator

_NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")
_CHEMICAL = re.compile(
    r"\b(pesticides?|fungicides?|insecticides?|herbicides?|miticides?|acaricides?|nematicides?|bactericides?|glyphosate|mancozeb|"
    r"chlorothalonil|copper\s+(?:sulfate|sulphate|oxychloride|hydroxide)|bordeaux|sulfur|sulphur|neem|pyrethr\w*|permethrin|"
    r"imidacloprid|spinosad|captan|carbendazim|metalaxyl|azoxystrobin|tebuconazole|cypermethrin|deltamethrin|abamectin|thuringiensis|"
    r"NPK|urea)\b",
    re.I,
)
_DOSE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ml|mg|g|gr|kg|oz|tsp|tbsp|ppm|cc)\s*(?:/|per\b)|\bdos(?:e|es|age)\b", re.I)
_DISEASE = re.compile(
    r"\b(blight|mildew|rust|mosaic|anthracnose|botrytis|fusarium|verticillium|canker|scab|viral|virus(?:es)?|fung(?:al|us|i)|"
    r"bacterial|infect(?:ed|ion|ions)?|aphids?|whitefl(?:y|ies)|spider mites?|nematodes?)\b",
    re.I,
)


def tidy(obj: object) -> object:
    """Whole numbers as integers (5, not 5.0), so the texts read naturally."""
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    if isinstance(obj, dict):
        return {k: tidy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [tidy(v) for v in obj]
    return obj


def plain_problems(errors: list[str]) -> str:
    """What the validator caught, in words a grower understands (the full messages stay in the result)."""
    kinds = [text for key, text in (("number", "a number that is not in your measurements"), ("chemical", "a product name"),
                                    ("dose", "a dose"), ("disease", "a diagnosis")) if any(key in e for e in errors)]
    return " and ".join(kinds) if kinds else "the answer was not in the right shape"


def fact_numbers(facts: object) -> list[float]:
    """Every number anywhere in the facts, including inside strings (dates, notes, drafts)."""
    return [float(n) for n in _NUMBER.findall(json.dumps(facts))]


def _number_ok(written: str, allowed: list[float]) -> bool:
    decimals = len(written.split(".")[1]) if "." in written else 0
    value = float(written)
    for fact in allowed:
        for candidate in (fact, fact * 100):  # a 0.82 confidence may be written as 82%
            if abs(round(candidate, decimals) - value) < 1e-9:
                return True
    return False


def text_errors(texts: list[str], allowed: list[float]) -> list[str]:
    """The plan's checks on any agent text: numbers from the facts only, no chemicals, doses or diagnoses."""
    errors = []
    for text in texts:
        quote = f'"{text[:100]}"'
        bad = [n for n in _NUMBER.findall(text) if not _number_ok(n, allowed)]
        if bad:
            errors.append(f"number {', '.join(bad)} is not in FACTS: {quote}. Use only numbers from the facts.")
        if match := _CHEMICAL.search(text):
            errors.append(f"names a chemical or product ({match.group(0)}): {quote}. Never recommend any.")
        if match := _DOSE.search(text):
            errors.append(f"gives a dose ({match.group(0)}): {quote}. Never give doses.")
        if match := _DISEASE.search(text):
            errors.append(f"names a disease or pest ({match.group(0)}): {quote}. Describe what is seen, as a possibility.")
    return errors


def normalize(reply: dict | None) -> dict | None:
    """Accept the short form {"summary", "next_step"} as a final report too."""
    if not isinstance(reply, dict) or reply.get("action") or "summary" not in reply:
        return reply
    step = reply.get("next_step")
    return {**reply, "action": "final", "headline": reply.get("headline") or reply.get("summary"),
            "next_steps": reply.get("next_steps") or ([step] if isinstance(step, str) and step.strip() else [])}


def _texts(reply: dict) -> list[str]:
    out = [reply.get("summary"), reply.get("headline"), reply.get("health_summary"), reply.get("change")]
    out += list((reply.get("lines") or {}).values()) + list((reply.get("signs") or {}).values())
    out += list(reply.get("next_steps") or [])
    return [t for t in out if isinstance(t, str) and t.strip()]


def validate(reply: object, allowed: list[float], line_ids: set[str], sign_types: set[str]) -> list[str]:
    if not isinstance(reply, dict):
        return ["The reply was not a JSON object."]
    errors = []
    if reply.get("action") != "final":
        errors.append('Write the report itself: "action" must be "final".')
    if not isinstance(reply.get("headline"), str) or not reply["headline"].strip():
        errors.append("The headline is missing.")
    for key in ("lines", "signs"):
        if reply.get(key) is not None and not isinstance(reply[key], dict):
            errors.append(f'"{key}" must be an object.')
    if not isinstance(reply.get("next_steps", []), list):
        errors.append('"next_steps" must be a list.')
    elif len(reply.get("next_steps") or []) > 3:
        errors.append("Give at most 3 next steps.")
    if errors:
        return errors
    unknown_lines = set(reply.get("lines") or {}) - line_ids
    if unknown_lines:
        errors.append(f"Unknown line ids {sorted(unknown_lines)}; use only {sorted(line_ids)}.")
    unknown_signs = set(reply.get("signs") or {}) - sign_types
    if unknown_signs:
        errors.append(f"Signs {sorted(unknown_signs)} were not measured; describe only {sorted(sign_types) or 'none'}.")
    return errors + text_errors(_texts(reply), allowed)


def parse_reply(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


# ------------------------------------------------------------------------------ inputs and outputs


@dataclass
class ReportInputs:
    plot_name: str
    crop_id: str
    crop_label: str
    captured_at: dt.date
    days_after_planting: int | None
    area_m2: float | None
    row_spacing_cm: float | None
    plant_spacing_cm: float | None
    image_bytes: bytes
    rgb: np.ndarray
    threshold: float
    metrics: Metrics
    quality: dict
    detection_confidence: float | None
    crop: list[Instance]
    crop_ids: list[str]
    lesion_share: float | None  # SAM "leaf spot" search, spots on crop plants only
    lesion_ids: list[str]
    comparison: Comparison | None
    notes: list[dict]  # {"date", "kind", "text"} since the previous photo
    context: list[ContextItem]  # statuses set in code, with template texts
    px_per_cm2: float | None
    crop_info: dict | None = None  # crops.crop_info: stage, Kc, typical cover (what the app shows)
    irrigation: dict | None = None  # irrigation.water_need: FAO-56 water need (what the app shows)
    experience: str | None = None  # the grower's profile: just_started | few_seasons | experienced
    scene: str | None = None  # the prompt agent's one-line description of the photo
    color: dict | None = None  # health.measure_color result, when the pipeline already ran it


@dataclass
class Sign:
    type: str
    share_pct: float
    likelihood: str
    evidence: list[str]
    how: str
    default: str


@dataclass
class ReportOutcome:
    context: list[ContextItem]
    health: Health
    comparison: Comparison | None
    summary: dict  # the app's Summary: text, next_step, source, attempts, validator_issues, error
    report: Report
    llm: LLMResult | None = None
    signs: list[Sign] = field(default_factory=list)


# ------------------------------------------------------------------------------ the agent


class _Run:
    def __init__(self, inp: ReportInputs, tracer, sam: SamClient, llm: LLMClient | None, add_mask: Callable[..., str]):
        self.inp, self.tracer, self.sam, self.llm, self.add_mask = inp, tracer, sam, llm, add_mask
        self.h, self.w = inp.rgb.shape[:2]
        self.label = inp.crop_label.lower()
        self.signs: list[Sign] = []
        self.measures: dict[str, float] = {}
        self.assessed = False
        self.looked_closer: str | None = None
        self.closer: dict | None = None  # what the closer look found (its numbers may be quoted)
        self.issues: list[str] = []  # everything the validator rejected on the way

    # -------------------------------------------------------------- tools (code)
    def assess_health(self) -> None:
        inp = self.inp
        step = self.tracer.start("assess_health", "Checking plant color and spots", input=f"{len(inp.crop)} crop masks")
        color = inp.color if inp.color is not None else measure_color(inp.rgb, inp.crop, inp.crop_ids)
        self.assessed = color["assessed"]
        if self.assessed:
            for sign in ("yellowing", "browning"):
                share = color[sign]["share_pct"]
                self.measures[sign] = share
                level = likelihood(sign, share)
                if level:
                    text = ("Parts of the crop look clearly yellower than the rest" if sign == "yellowing"
                            else "Some crop leaves look brown or dry")
                    self.signs.append(Sign(sign, share, level, color[sign]["plant_ids"], HOW[sign], f"{text} ({share}% of the crop area)."))
        if inp.lesion_share is not None:
            self.measures["leaf_spots"] = inp.lesion_share
            level = likelihood("leaf_spots", inp.lesion_share)
            if level:
                self.signs.append(Sign("leaf_spots", inp.lesion_share, level, inp.lesion_ids[:20], HOW["leaf_spots"],
                                       f"Spots or discolored patches on {inp.lesion_share}% of the crop area."))
        if not self.assessed:
            self.tracer.done(step, "Too little crop in the photo to check its color.", status="skipped")
        elif self.signs:
            found = ", ".join(f"{SIGN_LABELS.get(s.type, s.type).lower()} on {s.share_pct:g}% of the crop" for s in self.signs)
            self.tracer.done(step, f"Possible {found}.")
        else:
            self.tracer.done(step, "No yellowing, browning or spots worth noting.")

    def extra_context(self) -> list[ContextItem]:
        """The plan's spacing check for "Is this normal?": counted vs expected plants (needs the A4 scale)."""
        inp, items = self.inp, []
        count = inp.metrics.plant_count.value
        if inp.px_per_cm2 and inp.row_spacing_cm and inp.plant_spacing_cm and count is not None:
            area_m2 = self.w * self.h / inp.px_per_cm2 / 10_000
            expected = area_m2 / (inp.row_spacing_cm / 100 * inp.plant_spacing_cm / 100)
            if expected >= 1:
                ratio = count / expected
                spacing = f"{inp.row_spacing_cm:g} x {inp.plant_spacing_cm:g} cm"
                if ratio < DENSITY_LOW:
                    items.append(ContextItem(metric="plant_count", status="attention", badge="Gaps in rows",
                                             text=f"This photo covers {area_m2:.2f} m², where {spacing} spacing fits about {expected:.0f} plants; {count:.0f} were found. Check for gaps or missing seedlings."))
                elif ratio > DENSITY_HIGH:
                    items.append(ContextItem(metric="plant_count", status="attention", badge="Crowded",
                                             text=f"This photo covers {area_m2:.2f} m², where {spacing} spacing fits about {expected:.0f} plants; {count:.0f} were found. The plants may need thinning."))
                else:
                    items.append(ContextItem(metric="plant_count", status="typical",
                                             text=f"{count:.0f} plants in {area_m2:.2f} m² fits your {spacing} spacing (about {expected:.0f} expected)."))
        return items

    def look_closer(self, prompt: str, sign_type: str) -> str:
        inp = self.inp
        step = self.tracer.start("run_sam", f"Looking closer: {prompt}", input=prompt)
        try:
            seg = self.sam.segment(inp.image_bytes, prompt)
        except Exception as exc:
            self.tracer.done(step, "The search did not answer; moving on.", status="failed")
            return f"SAM could not be reached ({type(exc).__name__}); write the report with the facts you have."
        found = clean_instances(seg.instances, self.h * self.w, inp.threshold, min_area_frac=0.0)
        on_crop, share = coverage_on_crop(found, inp.crop, self.h, self.w)
        ids = [self.add_mask(found[i], "lesion", prompt) for i in on_crop]
        self.tracer.done(step, f"Found it on {share:g}% of the crop." if on_crop else "Nothing like that on your plants.")
        self.closer = {"prompt": prompt, "masks_found": len(found), "on_crop_plants": len(on_crop), "share_of_crop_pct": share}
        self.measures[sign_type] = share
        level = likelihood("leaf_spots", share)
        if level:
            self.signs.append(Sign(sign_type, share, level, ids[:20], f"Share of crop area covered by SAM 3.1 masks of '{prompt}'.",
                                   f"SAM found {prompt} on {share}% of the crop area."))
        return CLOSER_RESULT.format(prompt=prompt, found=len(found), on_crop=len(on_crop), share=share, health=json.dumps(self.health_facts()))

    # -------------------------------------------------------------- health + facts (code)
    def confidence(self) -> float | None:
        det = self.inp.detection_confidence
        if det is None:
            return None
        return round(det * (LOW_QUALITY_FACTOR if self.inp.quality["level"] == "low" else 1.0), 2)

    def consult_reasons(self) -> list[str]:
        reasons = []
        if self.inp.quality["level"] == "low":
            reasons.append("Photo quality is low, so these results are less reliable.")
        for s in self.signs:
            if s.type == "leaf_spots" and s.share_pct >= LESION_CONSULT_PCT:
                reasons.append(f"Leaf spots cover {s.share_pct}% of the crop area; spots have many possible causes.")
            elif s.type != "leaf_spots" and s.likelihood in ("medium", "high"):
                reasons.append(f"{SIGN_LABELS.get(s.type, s.type)} on {s.share_pct}% of the crop area; it has many possible causes.")
        confidence = self.confidence()
        if confidence is not None and confidence < CONSULT_CONFIDENCE:
            reasons.append(f"Plant detection confidence is low ({confidence:.2f}).")
        return reasons

    def health_facts(self) -> dict:
        return {
            "assessed": self.assessed,
            "measured_pct_of_crop_area": self.measures,
            "possible_signs": [{"type": s.type, "likelihood": s.likelihood, "share_of_crop_pct": s.share_pct, "plants_marked": len(s.evidence)}
                               for s in self.signs],
            "confidence": self.confidence(),
            "consult_agronomist": bool(self.consult_reasons()),
            "consult_reasons": self.consult_reasons(),
        }

    def water_facts(self) -> dict:
        water = self.inp.irrigation or {}
        if not water.get("available"):
            return {"unavailable": water.get("reason") or "no water estimate"}
        return {k: v for k, v in water.items() if k not in ("available", "how")}

    def facts(self, lines: list[tuple[str, ContextItem]]) -> dict:
        inp, m = self.inp, self.inp.metrics
        measurements: dict = {key: {"value": mv.value, "unit": mv.unit} for key, mv in m if key != "by_crop" and mv is not None}
        if m.by_crop:  # mixed bed
            measurements["per_crop"] = {b.label: {"plants": b.plant_count, "crop_cover_pct": b.canopy_cover_pct} for b in m.by_crop.values()}
        quality = {"level": inp.quality["level"], "sharp": inp.quality["sharp"], "exposure": inp.quality["exposure"]}
        comparison = None
        if inp.comparison is not None:
            c = inp.comparison
            comparison = {"previous_photo_date": c.previous_captured_at.isoformat(), "days_between": c.days_between,
                          "changes": c.deltas, "growth_per_day": c.growth_rate}
        facts = {
            "plot": {"name": inp.plot_name, "crop": self.label, "photo_date": inp.captured_at.isoformat(),
                     "days_after_planting": inp.days_after_planting, "area_m2": inp.area_m2},
            "grower": {"experience": EXPERIENCE_TONE.get(inp.experience or "", "unknown")},
            "photo_seen_as": inp.scene,
            "crop_library": inp.crop_info,
            "measurements": measurements,
            "photo_quality": quality,
            "plant_detection_confidence": inp.detection_confidence,
            "since_last_photo": comparison,
            "notes_since_last_photo": inp.notes,
            "health": self.health_facts(),
            "closer_look": self.closer,
            "water_today": self.water_facts(),
            "lines": [{"id": i, "topic": c.metric, "status": c.status, "draft": c.text} for i, c in lines],
        }
        return tidy(facts)

    # -------------------------------------------------------------- the LLM writer
    def write(self, lines: list[tuple[str, ContextItem]]) -> tuple[dict | None, dict, LLMResult | None]:
        """Returns (validated reply or None, validator info, combined LLM usage)."""
        step = self.tracer.start("write_summary", "Writing the report")
        if not enabled() or self.llm is None or not self.llm.configured:
            self.tracer.done(step, "Written from your measurements (the AI writer is off).", status="skipped")
            return None, {"passed": False, "attempts": 0, "errors": []}, None
        can_look = True
        closer = CLOSER.format(signs=" | ".join(CLOSER_SIGNS))
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [{"type": "text", "text": USER.format(facts=json.dumps(self.facts(lines), indent=1), closer=closer)},
                                         image_part(_llm_image(self.inp.image_bytes))]},
        ]
        results: list[LLMResult] = []
        attempts, errors = 0, []
        for _ in range(2 + MAX_FIX_ROUNDS + 1):  # look closer + draft + fixes, with one spare
            if step is None:
                step = self.tracer.start("write_summary", "Writing the report" if attempts == 0 else "Fixing the report")
            try:
                results.append(self.llm.chat(messages))
            except Exception as exc:  # LLM down: template text
                self.tracer.done(step, "The assistant did not answer; using the standard text.", status="failed")
                return None, {"passed": False, "attempts": attempts, "errors": [f"LLM unavailable: {type(exc).__name__}"]}, \
                    _combine(results) if results else None
            reply = normalize(parse_reply(results[-1].text))
            if reply and reply.get("action") == "look_closer" and can_look:
                prompt = clean_phrase(reply.get("prompt") or "")
                sign = reply.get("sign_type") if reply.get("sign_type") in CLOSER_SIGNS else "other_damage"
                can_look = False
                if prompt:
                    self.looked_closer = prompt
                    self.tracer.done(step, f"Wants a closer look at “{prompt}”.")
                    step = None
                    messages += [{"role": "assistant", "content": results[-1].text},
                                 {"role": "user", "content": self.look_closer(prompt, sign)}]
                    continue
            self.tracer.done(step, "Draft written.")
            step = None
            attempts += 1
            vstep = self.tracer.start("validate", "Checking every number and claim against the facts")
            errors = validate(reply, fact_numbers(self.facts(lines)), {i for i, _ in lines}, {s.type for s in self.signs})
            if not errors:
                self.tracer.done(vstep, "Every number matches your measurements; no product names or diagnoses.")
                return reply, {"passed": True, "attempts": attempts, "errors": []}, _combine(results)
            self.issues += errors
            self.tracer.done(vstep, f"Sent back: {plain_problems(errors)}.", status="failed")
            if attempts > MAX_FIX_ROUNDS:
                break
            messages += [{"role": "assistant", "content": results[-1].text},
                         {"role": "user", "content": FIX.format(errors="\n".join(f"- {e}" for e in errors))}]
        return None, {"passed": False, "attempts": attempts, "errors": errors}, _combine(results) if results else None


def _template_headline(label: str, m: Metrics, context: list[ContextItem]) -> str:
    count, canopy = m.plant_count.value, m.canopy_cover_pct.value
    text = f"{count:.0f} {label} plants found, covering {canopy}% of the photo"
    badges = [c.badge for c in context if c.status == "attention" and c.badge]
    return text + (f"; worth checking: {', '.join(badges).lower()}." if badges else ".")


def _template_steps(context: list[ContextItem], health: Health, water: dict | None) -> list[str]:
    actions = {
        "Retake photo": "Retake the photo in even light with a steady hand.",
        "Weeds rising": "Weed the plot.",
        "Many weeds": "Weed the plot.",
        "Crop cover dropped": "Check the plants for damage, or whether they were thinned or harvested.",
        "Behind typical": "Check for gaps or slow plants, and take the next photo from the same height.",
        "Check crop": "Make sure the photo shows this plot.",
        "Crop not found": "Make sure every crop of the bed is in the frame.",
        "Gaps in rows": "Check the rows for missing seedlings.",
        "Crowded": "Consider thinning the plants.",
    }
    steps = [actions[c.badge] for c in context if c.status == "attention" and c.badge in actions]
    if health.consult_agronomist:
        steps.append("Show the plants to an agronomist or an experienced grower.")
    if water and water.get("available"):
        steps.append(f"Water about {water['liters_per_m2']} L per m² today if the soil is dry.")
    steps.append("Take the next photo from the same spot in a few days.")
    return list(dict.fromkeys(steps))[:3]


def run(inp: ReportInputs, tracer, sam: SamClient, llm: LLMClient | None, add_mask: Callable[..., str]) -> ReportOutcome:
    agent = _Run(inp, tracer, sam, llm, add_mask)
    agent.assess_health()
    context = list(inp.context) + agent.extra_context()
    lines = [(f"c{i + 1}", item) for i, item in enumerate(context)]
    reply, validator, usage = agent.write(lines)

    texts = reply or {}
    line_texts = texts.get("lines") or {}
    context = [item.model_copy(update={"text": line_texts.get(i) or item.text}) for i, item in lines]
    sign_texts = texts.get("signs") or {}
    reasons = agent.consult_reasons()
    signs = [HealthSign(type=s.type, likelihood=s.likelihood, evidence_mask_ids=s.evidence, description=sign_texts.get(s.type) or s.default,
                        share_pct=s.share_pct, how=s.how) for s in agent.signs]
    if agent.signs:
        default_health = f"Possible {', '.join(SIGN_LABELS.get(s.type, s.type).lower() for s in agent.signs)}; these signs can have several causes."
    elif agent.assessed:
        default_health = "No yellowing, browning or spots above our thresholds in this photo."
    else:
        default_health = "Too little crop in the photo to check plant color."
    health = Health(assessed=agent.assessed, signs=signs, detection_confidence=inp.detection_confidence, confidence=agent.confidence(),
                    consult_agronomist=bool(reasons), consult_reasons=reasons, measures=agent.measures,
                    summary=texts.get("health_summary") or default_health)
    comparison = inp.comparison
    if comparison is not None and texts.get("change"):
        comparison = comparison.model_copy(update={"summary": texts["change"]})

    headline = texts.get("headline") or _template_headline(agent.label, inp.metrics, context)
    steps = [s.strip() for s in texts.get("next_steps") or [] if isinstance(s, str) and s.strip()] or _template_steps(context, health, inp.irrigation)
    if reply:
        summary_text = (texts.get("summary") or headline).strip()
    else:
        parts = [headline, health.summary]
        if inp.irrigation and inp.irrigation.get("available"):
            parts.append(f"Today's water need is about {inp.irrigation['liters_per_m2']} L per m².")
        summary_text = " ".join(parts)
    summary = {"text": summary_text, "next_step": steps[0] if steps else None, "source": "agent" if reply else "template",
               "attempts": validator["attempts"], "validator_issues": agent.issues, "error": None}
    report = Report(headline=headline, next_steps=steps, markdown="", written_by="agent" if reply else "template",
                    validator=validator, looked_closer=agent.looked_closer)
    return ReportOutcome(context, health, comparison, summary, report, usage, agent.signs)


# ------------------------------------------------------------------------------ the single report

_METRIC_LABELS = {"plant_count": "Plants", "canopy_cover_pct": "Crop cover", "weed_share_pct": "Weed share",
                  "lesion_share_pct": "Leaf spots / yellowing", "mean_plant_area": "Average plant size"}
_STATUS = {"typical": "✓", "attention": "⚠", "info": "ℹ"}


def _fmt(value: float | None) -> str:
    if value is None:
        return "–"
    return f"{value:.0f}" if float(value).is_integer() else f"{value:g}"


def render_markdown(result: AnalysisResult, plot_name: str, crop_label: str) -> str:
    """Everything in one page, numbers straight from the result (the agent's text cannot change them)."""
    r, rep = result, result.report
    day = f", day {r.days_after_planting} after planting" if r.days_after_planting is not None else ""
    md = [f"# {plot_name}: {crop_label}, {r.captured_at.isoformat()}{day}", ""]
    if r.summary:
        md += [f"**{r.summary.text}**", ""]
    md += ["## Measurements", "", "| | value | how it's computed |", "|---|---|---|"]
    for key, label in _METRIC_LABELS.items():
        mv = getattr(r.metrics, key)
        if mv is not None:
            md.append(f"| {label} | {_fmt(mv.value)} {mv.unit} | {mv.how} |")
    if r.metrics.by_crop:
        md += ["", "Per crop: " + "; ".join(f"{b.label} {b.plant_count} plants, {_fmt(b.canopy_cover_pct)}% cover" for b in r.metrics.by_crop.values()) + "."]
    if r.crop_info:
        info = r.crop_info
        md += ["", f"Crop library: {info.get('stage')} stage (days {info.get('stage_start_day')}-{info.get('stage_end_day')}), "
                   f"Kc {info.get('kc')}, typical crop cover {info.get('cover_typical_pct')} %. Source: {info.get('source', 'FAO-56')}."]
    md += ["", "## Is this normal?", ""] + [f"- {_STATUS[c.status]} {c.text}" for c in r.context]
    h = r.health
    md += ["", "## Plant health: possible signs, not a diagnosis", ""]
    if h.summary:
        md.append(h.summary)
    for s in h.signs:
        md.append(f"- **{SIGN_LABELS.get(s.type, s.type)}**: {s.likelihood} likelihood, {_fmt(s.share_pct)}% of the crop area, "
                  f"{len(s.evidence_mask_ids)} plants marked. {s.description}")
    if h.measures:
        md.append("")
        md.append("Measured: " + ", ".join(f"{SIGN_LABELS.get(k, k).lower()} {_fmt(v)}% of crop area" for k, v in h.measures.items()) + ".")
    if h.confidence is not None:
        md.append(f"Confidence: {h.confidence}.")
    if h.consult_agronomist:
        md += ["", "**Worth showing to an agronomist or an experienced grower:** " + " ".join(h.consult_reasons)]
    if r.comparison:
        c = r.comparison
        md += ["", f"## Since the last photo ({c.previous_captured_at.isoformat()}, {c.days_between} days earlier)", "", c.summary, ""]
        md += [f"- {_METRIC_LABELS.get(k, k)}: {'+' if v > 0 else ''}{_fmt(v)}" for k, v in c.deltas.items()]
        md += [f"- {k.replace('_', ' ')}: {_fmt(v)}" for k, v in c.growth_rate.items()]
    if r.notes_since_previous:
        md += ["", "Your notes since then: " + "; ".join(f"{n['date']} {n['kind']}: {n['text']}" for n in r.notes_since_previous)]
    water = r.irrigation or {}
    md += ["", "## Water need today (FAO-56)", ""]
    if water.get("available"):
        total = f" ({_fmt(water['plot_total_liters'])} L for the whole plot)" if water.get("plot_total_liters") is not None else ""
        md += [f"About {_fmt(water['liters_per_m2'])} L per m²{total}." + (f" {water['rain_note']}" if water.get("rain_note") else ""),
               "", f"How: {water.get('how', '')}"]
    else:
        md.append(water.get("reason") or "Not available.")
    q = r.image_quality
    md += ["", "## Photo quality", "", f"{q.level}: sharpness {_fmt(q.blur)}, brightness {_fmt(q.brightness)}, {_fmt(q.clipped_pct)}% burned-out pixels."]
    if rep and rep.next_steps:
        md += ["", "## Next steps", ""] + [f"{i}. {s}" for i, s in enumerate(rep.next_steps, start=1)]
    md += ["", "## How this report was made", ""]
    md += [f"{s.step}. {s.label}" + (f" ({s.input})" if s.input else "") + (f": {s.result}" if s.result else "") for s in r.agent_trace]
    if rep:
        who = "Muse Spark wrote the text; a validator checked every number against the measurements" if rep.written_by == "agent" else \
              "Text from ElderLeaf's templates (the AI writer was off or did not pass the checks)"
        md += ["", f"{who}. Every number comes from SAM 3.1 masks and code, not from the AI."]
    md += ["", "_ElderLeaf measures and explains; it does not diagnose. Crop coefficients: FAO-56 (Allen et al., 1998). Weather: Open-Meteo._"]
    return "\n".join(md)
