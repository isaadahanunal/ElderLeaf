"""Plain-language summary: Muse Spark explains the numbers; a validator makes sure it only explains.

The model gets a FACTS object (metrics, comparison, crop-library stage, water need, notes) and
writes 2-3 sentences plus one next step. Before anything reaches the grower, `validate` checks:

1. every number in the text appears in FACTS (copied, or rounded),
2. no pesticide / chemical names and no doses,
3. no disease names presented as a diagnosis.

If the text fails, the model gets the list of problems and one more try. If it fails again (or
there is no LLM key) the grower sees the template summary built from the same facts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .llm import LLMClient, LLMResult

SYSTEM_PROMPT = """You are ElderLeaf, a calm, experienced grower helping a beginner understand measurements of their plot.
Rules:
- Use only the numbers in FACTS, copied exactly as written there (you may round to whole numbers). Never compute or invent a number.
- Plain English for someone who has never farmed. Short sentences. No jargon without a few words explaining it.
- Never name a pesticide, fungicide, herbicide, chemical or fertilizer product, and never give a dose or mixing rate.
- Never name a disease or pest as a diagnosis. Visible signs can have several causes; if FACTS says consult_agronomist is true, say an agronomist or an experienced grower should take a look.
- If photo quality is low, say the numbers may be off.
Answer with one JSON object and nothing else: {"summary": "<2-3 sentences, at most 70 words>", "next_step": "<one practical thing to do this week, at most 25 words>"}"""

_NUMBER = re.compile(r"(?<![A-Za-z])-?\d+(?:[.,]\d+)?")
# names and units that contain digits but are not measurements
_NOT_NUMBERS = re.compile(r"\b(?:A4|FAO-?56|SAM ?3(?:\.1)?|ET0|ETc|m²|m2|cm²|cm2|CO2)\b", re.IGNORECASE)
_CHEMICALS = re.compile(
    r"\b(pesticide|fungicide|insecticide|herbicide|miticide|glyphosate|copper sulfate|copper sulphate|"
    r"bordeaux|neem|sulfur spray|sulphur spray|mancozeb|chlorothalonil|imidacloprid|permethrin|pyrethr\w*|"
    r"carbendazim|NPK|urea)\b",
    re.IGNORECASE,
)
_DOSE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:ml|mL|g|gr|kg|cc|tbsp|tsp|teaspoons?|tablespoons?)\s*(?:/|per)\s*(?:l\b|liter|litre|da\b|decare|ha\b|hectare|acre|gallon)",
    re.IGNORECASE,
)
_DIAGNOSIS = re.compile(
    r"\b(blight|mildew|fusarium|anthracnose|verticillium|mosaic virus|virus|aphids?|whitefl(?:y|ies)|"
    r"spider mites?|nematodes?|diagnos\w*)\b",
    re.IGNORECASE,
)


@dataclass
class SummaryResult:
    text: str
    next_step: str | None
    source: str  # "agent" | "template"
    attempts: int = 0
    issues: list[str] = field(default_factory=list)  # problems the validator found on the way
    llm: LLMResult | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "next_step": self.next_step,
            "source": self.source,
            "attempts": self.attempts,
            "validator_issues": self.issues,
            "error": self.error,
        }


# ------------------------------------------------------------------ validator


def _numbers_in(obj, out: set[float]) -> set[float]:
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for token in _NUMBER.findall(_NOT_NUMBERS.sub(" ", obj)):
            out.add(float(token.replace(",", ".")))
    elif isinstance(obj, dict):
        for value in obj.values():
            _numbers_in(value, out)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _numbers_in(value, out)
    return out


def allowed_numbers(facts: dict) -> set[float]:
    """Every number in FACTS, plus its roundings and absolute value (a delta of -3 may be said as 'fell by 3')."""
    allowed: set[float] = set()
    for value in _numbers_in(facts, set()):
        for v in (value, abs(value)):
            allowed.update({v, round(v), round(v, 1), float(int(v))})
    return allowed


def validate(text: str, facts: dict) -> list[str]:
    issues: list[str] = []
    allowed = allowed_numbers(facts)
    for token in _NUMBER.findall(_NOT_NUMBERS.sub(" ", text)):
        value = float(token.replace(",", "."))
        if value not in allowed and abs(value) not in allowed:
            issues.append(f"number {token} is not in FACTS")
    if m := _CHEMICALS.search(text):
        issues.append(f"names a chemical product ({m.group(0)})")
    if m := _DOSE.search(text):
        issues.append(f"gives a dose ({m.group(0)})")
    if m := _DIAGNOSIS.search(text):
        issues.append(f"names a disease or pest ({m.group(0)})")
    return list(dict.fromkeys(issues))


# ------------------------------------------------------------------ writers


def template_summary(facts: dict) -> SummaryResult:
    """Short summary built from the same facts, used when the agent is off or its text fails."""
    m = facts.get("measurements")
    if m is None:  # compare view: the context lines are already short
        lines = [c["text"] for c in facts.get("context", [])]
        notes = facts.get("grower_notes_between") or []
        if notes:
            lines.append(f"You wrote {len(notes)} note{'s' if len(notes) != 1 else ''} in between.")
        text = " ".join(lines[:3]) or "No measurements to compare."
        return SummaryResult(text=text, next_step=None, source="template")

    crop = facts.get("crop", "crop").lower()
    count, cover, weed = m.get("plant_count"), m.get("crop_cover_pct"), m.get("weed_share_pct")
    sentences = []
    if count is not None and cover is not None:
        n = int(count)
        sentences.append(
            f"{n} {crop} plant{'s' if n != 1 else ''} cover {cover:g}% of the photo"
            + (f", and weeds are {weed:g}% of the green area." if weed is not None else ".")
        )
    if facts.get("photo_quality") == "low":
        sentences.append("The photo is not sharp or well lit, so treat these numbers with care.")
    lib, day = facts.get("crop_library"), facts.get("days_after_planting")
    below = False
    if lib and cover is not None and day is not None:
        lo, hi = lib["typical_crop_cover_pct"]
        if cover < lo:
            below = True
            sentences.append(f"That is less cover than usual for day {day} ({lo}-{hi}%).")
        elif cover > hi:
            sentences.append(f"That is more cover than usual for day {day} ({lo}-{hi}%): strong growth, or a closer photo.")
        else:
            sentences.append(f"That is normal for day {day} ({lo}-{hi}%).")
    change = facts.get("change_since_previous_photo") or {}
    delta = (change.get("deltas") or {}).get("canopy_cover_pct")
    if delta is not None and change.get("days_between"):
        verb = "rose" if delta >= 0 else "fell"
        sentences.append(f"Cover {verb} by {abs(delta):g} points in {change['days_between']} days.")

    attention = {c.get("metric") for c in facts.get("context", []) if c.get("status") == "attention"}
    if facts.get("health", {}).get("consult_agronomist") and facts.get("photo_quality") != "low":
        step = "Ask an agronomist or an experienced grower to look at the plants."
    elif facts.get("photo_quality") == "low":
        step = "Retake the photo in even light with a steady hand, from the same spot."
    elif "weed_share_pct" in attention:
        step = "Pull the weeds this week while they are still small."
    elif below:
        step = "Look for gaps or slow plants, and take the next photo from the same height."
    else:
        step = "Take another photo from the same spot in a few days to follow growth."
    return SummaryResult(text=" ".join(sentences[:3]), next_step=step, source="template")


def _parse(text: str) -> tuple[str, str | None]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    start, end = text.find("{"), text.rfind("}")
    data = json.loads(text[start : end + 1])
    summary = str(data.get("summary", "")).strip()
    if not summary:
        raise ValueError("empty summary")
    step = data.get("next_step")
    return summary, (str(step).strip() if step else None)


def _total(calls: list[LLMResult]) -> LLMResult:
    from .agent import _combine  # sums tokens, time and cost over retries

    return _combine(calls)


def write_summary(llm: LLMClient | None, facts: dict, max_attempts: int = 2) -> SummaryResult:
    """Muse Spark summary, validated; falls back to the template."""
    fallback = template_summary(facts)
    if llm is None or not llm.configured:
        fallback.error = "no LLM key configured"
        return fallback
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "FACTS:\n" + json.dumps(facts, ensure_ascii=False, default=str)},
    ]
    issues_seen: list[str] = []
    last: LLMResult | None = None
    calls: list[LLMResult] = []
    for attempt in range(1, max_attempts + 1):
        try:
            last = llm.chat(messages, max_tokens=2048)
            calls.append(last)
            summary, step = _parse(last.text)
        except Exception as exc:  # network, bad JSON
            issues_seen.append(f"attempt {attempt}: unreadable answer ({type(exc).__name__})")
            if last is None:
                fallback.attempts, fallback.issues, fallback.error = attempt, issues_seen, f"{type(exc).__name__}: {exc}"
                return fallback
            messages += [
                {"role": "assistant", "content": last.text},
                {"role": "user", "content": "That was not a valid JSON object. Reply with the JSON object only."},
            ]
            continue
        problems = validate(summary + " " + (step or ""), facts)
        if not problems:
            return SummaryResult(summary, step, "agent", attempt, issues_seen, _total(calls))
        issues_seen += [f"attempt {attempt}: {p}" for p in problems]
        messages += [
            {"role": "assistant", "content": last.text},
            {
                "role": "user",
                "content": "The validator rejected that answer: "
                + "; ".join(problems)
                + ". Rewrite it following the rules. Use only numbers that appear in FACTS.",
            },
        ]
    fallback.attempts, fallback.issues, fallback.llm = max_attempts, issues_seen, _total(calls) if calls else None
    fallback.error = "validator rejected the agent's text; showing the template summary"
    return fallback
