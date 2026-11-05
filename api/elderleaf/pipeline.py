"""Photo analysis: SAM 3.1 masks -> cleanup -> metrics -> history -> report agent.

Every number is computed in code. Two Muse Spark agents sit on top: the prompt agent picks what
SAM should look for (agent.py), and after the masks the report agent (report_agent.py) checks
health, crop facts, weather and water need, may ask SAM to look closer, and writes one validated
report. Neither invents a number; without an LLM the code's template texts are used.

Each step is written to `analyses.trace` as it happens, so the UI can show it live by polling.
"""

from __future__ import annotations

import datetime as dt
import io
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import report_agent
from .agent import Proposal, Scan, propose_prompts, scan_plants
from .config import settings
from .crops import FALLBACK_PROMPT, crop_info, crop_label, crop_prompt
from .db import Analysis, Note, SessionLocal, User
from .irrigation import water_need
from .llm import LLMClient, LLMResult
from .masks import clean_instances, drop_on_top_of, instance_iou, merge_duplicates, resolve_cross_class
from .health import coverage_on_crop, measure_color
from .metrics import compute_metrics, find_scale, image_quality, mask_polygons
from .prompting import Attempt, Chain, build_candidates, run_chains, sam_cost, sam_latency
from .sam import Instance, SamClient, SamError, Segmentation
from .schemas import (
    AnalysisResult,
    AttemptOut,
    ChosenPrompt,
    Comparison,
    ContextItem,
    CropBreakdown,
    ImageInfo,
    ImageQuality,
    LLMUsage,
    MaskOut,
    Metrics,
    MetricValue,
    RunStats,
    Scale,
    Summary,
    TraceStep,
)
from .storage import get_storage

log = logging.getLogger("elderleaf.pipeline")

PROMPT_WEED = "weed"
PROMPT_SCALE = "white paper sheet"
PROMPT_LESION = "leaf spot"
NOTES_WINDOW_DAYS = 30  # first photo of a plot: notes from the last 30 days

# Product rules for the "Is this normal?" lines (not agronomic facts; tune with real use)
WEED_HIGH_PCT = 25.0
WEED_DOUBLING_MIN_PCT = 5.0
CANOPY_DROP_PTS = 5.0

COMPARED = ("plant_count", "canopy_cover_pct", "weed_share_pct", "lesion_share_pct", "mean_plant_area")

_sam: SamClient | None = None


def get_sam() -> SamClient:
    global _sam
    if _sam is None:
        if settings.sam_backend == "offline":
            from .devsam import OfflineSegmenter

            _sam = OfflineSegmenter()
        else:
            _sam = SamClient()
    return _sam


def segmenter_name() -> str:
    return getattr(get_sam(), "display_name", "SAM 3.1")


def set_sam(client: SamClient | None) -> None:
    """Swap the SAM client (tests use a fake)."""
    global _sam
    _sam = client


_llm: LLMClient | None = None
_strategy: str | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm


def set_llm(client: LLMClient | None) -> None:
    global _llm
    _llm = client


def current_strategy() -> str:
    return _strategy or settings.prompt_strategy


def set_strategy(name: str | None) -> None:
    """'agent' or 'fixed' (None = use PROMPT_STRATEGY from the environment)."""
    global _strategy
    _strategy = name


# ------------------------------------------------------------------ uploads


def prepare_upload(data: bytes, max_side: int) -> tuple[bytes, int, int]:
    """Decode any phone photo (incl. HEIC), fix EXIF rotation, downscale, re-encode as JPEG."""
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except ImportError:
        pass
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue(), img.width, img.height


# ------------------------------------------------------------------ trace


class Tracer:
    def __init__(self, db: Session, analysis: Analysis) -> None:
        self.db, self.analysis = db, analysis
        self.steps: list[dict] = []
        self._flush()

    def start(self, tool: str, label: str, input: str | None = None) -> int:
        self.steps.append(
            {"step": len(self.steps) + 1, "tool": tool, "label": label, "input": input, "result": None, "status": "running"}
        )
        self._flush()
        return len(self.steps) - 1

    def done(self, index: int, result: str, status: str = "done") -> None:
        self.steps[index].update(result=result, status=status)
        self._flush()

    def fail_running(self, message: str) -> None:
        for step in self.steps:
            if step["status"] == "running":
                step.update(status="failed", result=message)
        self._flush()

    def _flush(self) -> None:
        self.analysis.trace = [dict(s) for s in self.steps]
        self.db.commit()


def _mean_score(instances: list[Instance]) -> float:
    return float(np.mean([i.score_or_one for i in instances])) if instances else 0.0


def _describe(key: str, instances: list[Instance]) -> str:
    if key == "scale":
        return "No A4 sheet in the photo, so sizes are in pixels." if not instances else "Found a sheet of paper; checking it is a flat A4."
    if not instances:
        return "No leaf spots found."
    return f"Found {len(instances)} possible spots ({round(100 * _mean_score(instances))}% sure); keeping the ones on your plants."


# ------------------------------------------------------------------ entry point


def run_analysis(analysis_id: str) -> None:
    with SessionLocal() as db:
        analysis = db.get(Analysis, analysis_id)
        if analysis is None:
            return
        analysis.status, analysis.error = "running", None
        db.commit()
        tracer = Tracer(db, analysis)
        try:
            result = _analyze(db, analysis, tracer)
            analysis.result = result.model_dump(mode="json", by_alias=True)
            analysis.status = "done"
        except Exception as exc:  # the UI shows the error; the log keeps the stack
            log.exception("analysis %s failed", analysis_id)
            tracer.fail_running(str(exc))
            analysis.status, analysis.error = "failed", f"{type(exc).__name__}: {exc}"
        db.commit()


def _choose_words(tracer: Tracer, image_bytes: bytes, label: str, days_after_planting: int | None) -> Proposal | None:
    """Ask the agent for ranked SAM phrases. None (or a Proposal with .error) means: use fixed words."""
    if current_strategy() != "agent":
        return None
    llm = get_llm()
    step = tracer.start("propose_prompts", "Looking at the photo to choose search words", input=label)
    if not llm.configured:
        tracer.done(step, "The assistant is off; using the standard words.", status="skipped")
        return None
    proposal = propose_prompts(llm, image_bytes, label, days_after_planting)
    if proposal.error:
        tracer.done(step, "The assistant did not answer; using the standard words.", status="failed")
    else:
        crop_words = " / ".join(proposal.crop_prompts) or "-"
        weed_words = " / ".join(proposal.weed_prompts) or "-"
        tracer.done(step, f"Plants: {crop_words.replace(' / ', ', ')}. Weeds: {weed_words.replace(' / ', ', ')}.")
    return proposal


def _plot_crops(plot) -> list[str]:
    """The crops in the photo: the main crop, plus the others of a mixed bed."""
    crops = [plot.crop]
    if plot.mixed:
        crops += [c for c in (plot.other_crops or []) if c not in crops]
    return crops


@dataclass
class Search:
    """What SAM found, before cleanup: crop masks per crop id ("*" = plants that could not be told apart)."""

    crops: dict[str, list[tuple[Instance, str]]]
    weeds: list[tuple[Instance, str]]
    attempts: list[Attempt]
    strategy: str
    main_prompt: str | None = None
    llm: LLMResult | None = None
    scene: str | None = None
    crop_visible: bool | None = None
    proposals: dict[str, list[str]] = field(default_factory=dict)
    chosen: dict[str, ChosenPrompt] = field(default_factory=dict)
    scan_items: list[dict] = field(default_factory=list)


def _on_done(tracer: Tracer, thr: float, single_tries: bool = False):
    def on_done(step: int, chain: Chain, attempt: Attempt) -> None:
        if attempt.error:
            tracer.done(step, "The search did not answer; moving on.", status="failed")
            return
        found = "Nothing found" if not attempt.kept else f"Found {attempt.kept}"
        if attempt.kept and attempt.mean_confidence is not None:
            found += f" ({round(100 * attempt.mean_confidence)}% sure)"
        if single_tries:  # scan mode: every phrase is searched; weak ones may get a fallback word later
            verdict = "confident" if attempt.ok else "not sure"
        else:
            verdict = "confident, using it" if attempt.ok else ("not sure, no words left" if chain.finished else "not sure, trying the next word")
        tracer.done(step, f"{found}: {verdict}.")

    return on_done


# ------------------------------------------------------------------ one crop: ranked words


def _single_plan(tracer: Tracer, image_bytes: bytes, crop: str, days_after_planting: int | None):
    """Agent's 3 ranked phrases first, then the plain "plant"; without the agent the crop's library word."""
    proposal = _choose_words(tracer, image_bytes, crop_label(crop), days_after_planting)
    agent_ok = proposal is not None and proposal.error is None
    if agent_ok:
        crop_chain = Chain("crop", build_candidates(proposal.crop_prompts, [FALLBACK_PROMPT]))
        weed_chain = Chain("weed", build_candidates(proposal.weed_prompts, [PROMPT_WEED]))
    else:
        crop_chain = Chain("crop", build_candidates([], [crop_prompt(crop), FALLBACK_PROMPT]))
        weed_chain = Chain("weed", build_candidates([], [PROMPT_WEED]))
    return proposal, agent_ok, crop_chain, weed_chain


def _single_search(tracer: Tracer, sam: SamClient, image_bytes: bytes, crop: str, thr: float, plan) -> Search:
    proposal, agent_ok, crop_chain, weed_chain = plan

    def on_start(chain: Chain, prompt: str, rank) -> int:
        what = "crop plants" if chain.target == "crop" else "weeds"
        which = f"agent's choice {rank}" if isinstance(rank, int) else ("fallback word" if agent_ok else "fixed word")
        return tracer.start("run_sam", f"Finding {what} ({which})", input=prompt)

    run_chains(sam, image_bytes, [crop_chain, weed_chain], thr, on_start=on_start, on_done=_on_done(tracer, thr))
    if crop_chain.chosen_seg is None:
        errors = [a.error for a in crop_chain.attempts if a.error]
        raise SamError("SAM gave no answer for the crop" + (f": {errors[-1]}" if errors else ""))
    crop_prompt_used = crop_chain.chosen.prompt
    weeds = [(i, weed_chain.chosen.prompt) for i in weed_chain.chosen_seg.instances] if weed_chain.chosen_seg else []
    return Search(
        crops={crop: [(i, crop_prompt_used) for i in crop_chain.chosen_seg.instances]},
        weeds=weeds,
        attempts=crop_chain.attempts + weed_chain.attempts,
        strategy="agent" if agent_ok else "fixed",
        main_prompt=crop_prompt_used,
        llm=proposal.llm if proposal is not None else None,
        scene=proposal.scene if proposal is not None else None,
        crop_visible=proposal.crop_visible if proposal is not None else None,
        proposals={"crop": proposal.crop_prompts, "weed": proposal.weed_prompts} if agent_ok else {},
        chosen={c.target: ChosenPrompt(prompt=c.chosen.prompt, rank=c.chosen.rank) for c in (crop_chain, weed_chain) if c.chosen},
    )


# ------------------------------------------------------------------ mixed bed: scan mode


def _mixed_plan(tracer: Tracer, image_bytes: bytes, crops: list[str], days_after_planting: int | None = None) -> Scan | None:
    """Scan mode: the agent lists one phrase per kind of plant it sees (as many as the photo needs)."""
    if current_strategy() != "agent":
        return None
    llm = get_llm()
    labels = [crop_label(c) for c in crops]
    step = tracer.start("scan_plants", "Listing every kind of plant in the photo", input=", ".join(labels))
    if not llm.configured:
        tracer.done(step, "The assistant is off; looking for each crop by name.", status="skipped")
        return None
    scan = scan_plants(llm, image_bytes, labels, days_after_planting=days_after_planting)
    if scan.error:
        tracer.done(step, "The assistant did not answer; looking for each crop by name.", status="failed")
    else:
        groups: dict[str, list[str]] = defaultdict(list)
        for it in scan.items:
            groups[(it["crop"] or "weeds").capitalize()].append(it["phrase"])
        tracer.done(step, " ".join(f"{name}: {', '.join(phrases)}." for name, phrases in groups.items()))
    return scan


def _mixed_search(tracer: Tracer, sam: SamClient, image_bytes: bytes, crops: list[str], thr: float, scan: Scan | None) -> Search:
    """SAM searches every listed phrase. A crop none of whose phrases was confident gets its library word;
    weeds get "weed"; if no crop was found at all, the plain "plant" (those plants can't be told apart).
    Mixed beds measured this way on CropAndWeed: eval/results/mixed/report.md."""
    labels = {c: crop_label(c) for c in crops}
    by_name = {label.lower(): c for c, label in labels.items()}
    items = scan.items if scan is not None and not scan.error else []
    owner: dict[int, str | None] = {}  # id(chain) -> crop id; None for weeds
    chains: list[Chain] = []

    def add_chain(kind: str, prompt: str, rank, crop_id: str | None) -> Chain:
        chain = Chain(kind, [(prompt, rank)])
        owner[id(chain)] = crop_id
        chains.append(chain)
        return chain

    def run_round(batch: list[Chain], round_no: int) -> None:
        def on_start(chain: Chain, prompt: str, rank) -> int:
            crop_id = owner[id(chain)]
            what = "weeds" if crop_id is None else ("plants" if crop_id == "*" else f"{labels[crop_id].lower()} plants")
            which = f"agent's phrase {rank}" if isinstance(rank, int) else "fallback word"
            return tracer.start("run_sam", f"Finding {what} ({which})", input=prompt)

        run_chains(sam, image_bytes, batch, thr, on_start=on_start, on_done=_on_done(tracer, thr, single_tries=True), max_workers=6)
        for chain in batch:
            for attempt in chain.attempts:
                attempt.round = round_no

    def confident(crop_id: str | None) -> bool:
        return any(ch.chosen is not None and ch.chosen.ok for ch in chains if owner[id(ch)] == crop_id)

    def tried(crop_id: str | None) -> set[str]:
        return {ch.candidates[0][0] for ch in chains if owner[id(ch)] == crop_id}

    # A crop whose library word is the generic "plant" ("other") gets no word of its own: "plant" finds
    # every plant and would take the other crops' plants (seen on a real sugar beet + other photo).
    specific = [c for c in crops if crop_prompt(c) != FALLBACK_PROMPT]
    for rank, item in enumerate(items, start=1):
        crop_id = by_name.get(item["crop"]) if item["kind"] == "crop" else None
        if item["kind"] == "weed" or crop_id is not None:
            add_chain(item["kind"], item["phrase"], rank, crop_id)
    if not items:  # no agent: every crop's library word
        for c in specific:
            add_chain("crop", crop_prompt(c), "fallback", c)
    first = list(chains)
    if not any(owner[id(ch)] is None for ch in chains):
        first.append(add_chain("weed", PROMPT_WEED, "fallback", None))
    run_round(first, 1)

    retry = [add_chain("crop", crop_prompt(c), "fallback", c) for c in specific if not confident(c) and crop_prompt(c) not in tried(c)]
    if not confident(None) and PROMPT_WEED not in tried(None):
        retry.append(add_chain("weed", PROMPT_WEED, "fallback", None))
    if retry:
        run_round(retry, 2)
    if not any(confident(c) for c in crops):
        run_round([add_chain("crop", FALLBACK_PROMPT, "fallback", "*")], 3)

    found: dict[str, list[tuple[Instance, str]]] = defaultdict(list)
    weeds: list[tuple[Instance, str]] = []
    for chain in chains:
        if chain.chosen_seg is None:
            continue
        crop_id = owner[id(chain)]
        target = weeds if crop_id is None else found[crop_id]
        target += [(i, chain.chosen.prompt) for i in chain.chosen_seg.instances]
    if not any(ch.chosen_seg is not None for ch in chains if owner[id(ch)] is not None):
        errors = [a.error for ch in chains for a in ch.attempts if a.error]
        raise SamError("SAM gave no answer for the crops" + (f": {errors[-1]}" if errors else ""))
    proposals: dict[str, list[str]] = defaultdict(list)
    for item in items:
        proposals["weed" if item["kind"] == "weed" else by_name.get(item["crop"], item["crop"])].append(item["phrase"])
    return Search(
        crops=dict(found),
        weeds=weeds,
        attempts=[a for ch in chains for a in ch.attempts],
        strategy="scan" if items else "fixed",
        llm=scan.llm if scan is not None else None,
        scene=scan.scene if scan is not None else None,
        proposals=dict(proposals),
        scan_items=items,
    )


# ------------------------------------------------------------------ the analysis


def _analyze(db: Session, analysis: Analysis, tracer: Tracer) -> AnalysisResult:
    started = time.monotonic()
    plot = analysis.plot
    image_bytes = get_storage().get(analysis.image_key)
    rgb = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    h, w = rgb.shape[:2]
    thr = settings.score_threshold
    days_after_planting = (analysis.captured_at - plot.planted_on).days if plot.planted_on else None
    crops = _plot_crops(plot)
    mixed = len(crops) > 1
    label = " + ".join(crop_label(c) for c in crops)

    # 1. photo quality
    step = tracer.start("check_image_quality", "Checking photo quality")
    quality = image_quality(rgb)
    if quality["level"] == "good":
        tracer.done(step, "Sharp and well lit.")
    else:
        problem = "blurry" if not quality["sharp"] else quality["exposure"].replace("_", " ")
        tracer.done(step, f"The photo looks {problem}, so the numbers may be off.")

    # 2. what should SAM look for? One crop: the agent's 3 ranked phrases. Mixed bed: one phrase per kind of plant.
    plan = _mixed_plan(tracer, image_bytes, crops, days_after_planting) if mixed else _single_plan(tracer, image_bytes, plot.crop, days_after_planting)

    # 3. SAM 3.1 runs the search; A4 (and leaf spots) alongside
    sam = get_sam()
    side_jobs = {"scale": (PROMPT_SCALE, "Looking for an A4 sheet (scale)")}
    if settings.enable_lesion:
        side_jobs["lesion"] = (PROMPT_LESION, "Looking for leaf spots")
    side_steps = {key: tracer.start("run_sam", text, input=prompt) for key, (prompt, text) in side_jobs.items()}
    segs: dict[str, Segmentation | None] = {}
    with ThreadPoolExecutor(max_workers=len(side_jobs)) as side:
        side_futures = {key: side.submit(sam.segment, image_bytes, prompt) for key, (prompt, _) in side_jobs.items()}
        if mixed:
            search = _mixed_search(tracer, sam, image_bytes, crops, thr, plan)
        else:
            search = _single_search(tracer, sam, image_bytes, plot.crop, thr, plan)
        for key, future in side_futures.items():
            try:
                segs[key] = future.result()
                tracer.done(side_steps[key], _describe(key, segs[key].instances))
            except Exception as exc:  # scale and spots are optional
                segs[key] = None
                tracer.done(side_steps[key], "The search did not answer; skipped.", status="failed")

    # 4. cleanup + metrics
    step = tracer.start("compute_metrics", "Cleaning masks and computing metrics")
    paper, px_per_cm2, scale_note = find_scale(segs["scale"].instances if segs.get("scale") else [])
    prompt_of: dict[int, str] = {}

    def clean(found: list[tuple[Instance, str]]) -> list[Instance]:
        for inst, prompt in found:
            prompt_of[id(inst)] = prompt
        insts = clean_instances([i for i, _ in found], h * w, thr)
        if paper is not None:  # the sheet itself is never a plant
            insts = [i for i in insts if instance_iou(i, paper) < 0.5]
        return merge_duplicates(insts) if len({p for _, p in found}) > 1 else insts

    crop_by = {c: clean(found) for c, found in search.crops.items()}
    if len(crop_by) > 1:  # the same plant found under two crop names: the higher score wins
        crop_by = resolve_cross_class(crop_by)
    crop = [i for insts in crop_by.values() for i in insts]
    weed = clean(search.weeds)
    # The grower told us the crop(s), so when a weed phrase also matched a crop plant the crop wins
    # (on 6 PhenoBench images this cut the plant-count error from 8.2 to 3.5 for the agent).
    weed = resolve_cross_class({"crop": crop, "weed": weed}, priority=["crop", "weed"])["weed"]
    # A weed mask lying mostly on crop plants is a part of one (e.g. single lettuce leaves found by
    # "grassy weed blade"); IoU above misses it because a leaf is a small part of the plant's mask.
    weeds_found = len(weed)
    weed = drop_on_top_of(weed, crop, h, w)
    weeds_on_crop = weeds_found - len(weed)
    lesion, spots_share = None, None
    if segs.get("lesion") is not None:  # only spots that sit on crop plants count
        found = clean_instances(segs["lesion"].instances, h * w, thr, min_area_frac=0.0)
        on_crop, spots_share = coverage_on_crop(found, crop, h, w)
        lesion = [found[i] for i in on_crop]

    masks: list[MaskOut] = []

    def add(inst: Instance, cls: str, prompt: str, crop_id: str | None = None) -> str:
        mask_id = f"m{len(masks) + 1}"
        masks.append(
            MaskOut(
                id=mask_id,
                class_=cls,
                prompt=prompt,
                score=None if inst.score is None else round(inst.score, 3),
                area_px=inst.area,
                box=list(inst.box),
                polygons=mask_polygons(inst),
                crop=crop_id,
            )
        )
        return mask_id

    crop_ids_by = {c: [add(i, "crop", prompt_of[id(i)], None if c == "*" else c) for i in insts] for c, insts in crop_by.items()}
    crop_ids = [mask_id for ids in crop_ids_by.values() for mask_id in ids]
    weed_ids = [add(x, "weed", prompt_of[id(x)]) for x in weed]
    lesion_ids = [add(x, "lesion", PROMPT_LESION) for x in lesion or []]
    scale_id = add(paper, "scale", PROMPT_SCALE) if paper is not None else None
    # plan: lesion share = spot (SAM) or yellowing (color) pixels on the crop / crop pixels
    color = measure_color(rgb, crop, crop_ids, with_mask=True)
    m = compute_metrics(crop, weed, lesion, h, w, px_per_cm2, discolored=color.pop("discolored_mask", None))
    tracer.done(
        step,
        f"{m['plant_count']} plants. Crop cover {m['canopy_cover_pct']:g}% of the photo, weeds {m['weed_share_pct']:g}% of the green."
        + (f" Skipped {weeds_on_crop} weed find{'s' if weeds_on_crop > 1 else ''} that sat on your crop plants." if weeds_on_crop else ""),
    )

    by_crop = None
    if mixed:
        by_crop = {}
        for c in [*crops, *[c for c in crop_by if c not in crops]]:
            insts = crop_by.get(c, [])
            cover = np.zeros((h, w), bool)
            for inst in insts:
                x0, y0, x1, y1 = inst.box
                cover[y0:y1, x0:x1] |= inst.mask
            by_crop[c] = CropBreakdown(
                label="Plants (not told apart)" if c == "*" else crop_label(c),
                plant_count=len(insts),
                canopy_cover_pct=round(float(cover.mean() * 100), 1),
                mask_ids=crop_ids_by.get(c, []),
            )
    if mixed:
        used = sorted({prompt_of[id(i)] for i in crop})
        count_how = (f"Number of crop masks found by {', '.join(repr(p) for p in used) or 'the search'} with confidence ≥ {thr}, "
                     "after removing tiny masks and duplicates; per crop in by_crop.")
    else:
        count_how = f"Number of '{search.main_prompt}' masks with confidence ≥ {thr}, after removing tiny masks."

    metrics = Metrics(
        plant_count=MetricValue(value=m["plant_count"], unit="plants", how=count_how, mask_ids=crop_ids),
        canopy_cover_pct=MetricValue(
            value=m["canopy_cover_pct"],
            unit="%",
            how="Crop leaf area seen from above (crop masks) divided by the whole photo. Weeds are not counted.",
            mask_ids=crop_ids,
        ),
        weed_share_pct=MetricValue(
            value=m["weed_share_pct"], unit="%", how="Weed area divided by all green area.", mask_ids=weed_ids
        ),
        lesion_share_pct=None
        if m["lesion_share_pct"] is None
        else MetricValue(
            value=m["lesion_share_pct"],
            unit="%",
            how=("Crop area with leaf spots (SAM 3.1 'leaf spot' masks) or clearly yellow/brown color, divided by crop area."
                 if lesion is not None else "Crop area with clearly yellow/brown color, divided by crop area (leaf-spot search off)."),
            mask_ids=lesion_ids,
        ),
        mean_plant_area=MetricValue(
            value=m["mean_plant_area"],
            unit=m["mean_plant_area_unit"],
            how="Average crop mask area; in cm² when an A4 sheet in the photo sets the scale.",
            mask_ids=crop_ids,
        ),
        by_crop=by_crop,
    )

    # 5. history: the previous photo of this plot and the grower's notes since then
    step = tracer.start("get_plot_history", "Comparing with the previous photo and reading your notes")
    previous = _previous(db, analysis)
    comparison = _compare(previous, analysis, metrics) if previous else None
    notes = _notes_since(db, analysis, previous)
    tracer.done(step, (comparison.summary if comparison else "First photo of this plot.") + (f" {len(notes)} of your notes since then." if notes else ""))

    # 6. crop library: where should this crop be today? ("Is this normal?")
    step = tracer.start("lookup_crop_info", "Looking up what is typical for this crop and age", input=f"{crop_label(plot.crop)}, day {days_after_planting}")
    info = crop_info(plot.crop, days_after_planting)
    if info is None:
        tracer.done(step, "Add the crop and the planting date to compare with what is typical.", status="skipped")
    else:
        lo, hi = info["cover_typical_pct"]
        tracer.done(step, f"Day {info['day']}: {info['stage']} stage (days {info['stage_start_day']}-{info['stage_end_day']}). A typical plot covers {lo}-{hi}% now.")

    # 7. "Is this normal?" statuses, set in code (their texts are drafts for the report agent)
    context = _context(metrics, comparison, previous, quality, info)
    if search.crop_visible is False:
        context.insert(
            0,
            ContextItem(
                metric="crop",
                status="attention",
                badge="Check crop",
                text=f"The assistant could not clearly see {crop_label(plot.crop).lower()} plants in this photo. Is this the right plot?",
            ),
        )
    if by_crop:
        for c in crops:
            if by_crop[c].plant_count == 0 and crop_prompt(c) != FALLBACK_PROMPT:  # "other": we can't say what was expected
                context.insert(
                    0,
                    ContextItem(
                        metric="crop",
                        status="attention",
                        badge="Crop not found",
                        text=f"No {crop_label(c).lower()} plants were found in this photo. Is that crop in the frame?",
                    ),
                )

    # 8. water need: FAO-56 Kc (crop library, scaled by the measured cover) x ET0 of the plot location (Open-Meteo)
    step = tracer.start("get_weather", "Getting the weather for the water need (FAO-56)", input=None if plot.lat is None else f"{plot.lat:.2f}, {plot.lon:.2f}")
    irrigation = water_need(plot.crop, days_after_planting, metrics.canopy_cover_pct.value, plot.area_m2, plot.lat, plot.lon, day=_weather_day(analysis))
    if irrigation["available"]:
        total = f" ({irrigation['plot_total_liters']} L for the plot)" if irrigation.get("plot_total_liters") is not None else ""
        tracer.done(step, f"About {irrigation['liters_per_m2']} L of water per m² today{total}.")
    else:
        tracer.done(step, irrigation["reason"], status="skipped")
    detection_confidence = round(_mean_score(crop), 2) if crop else None

    # 9. report agent: health, a closer look if needed, then one validated report in the grower's terms.
    # Like the prompt agent, the writer uses the LLM only with PROMPT_STRATEGY=agent (and ENABLE_SUMMARY=1).
    grower = db.get(User, plot.device_id) if plot.device_id and plot.device_id.startswith("u_") else None
    writer = get_llm() if current_strategy() == "agent" and settings.enable_summary else None
    outcome = report_agent.run(
        report_agent.ReportInputs(
            plot_name=plot.name,
            crop_id=plot.crop,
            crop_label=label,
            captured_at=analysis.captured_at,
            days_after_planting=days_after_planting,
            area_m2=plot.area_m2,
            row_spacing_cm=plot.row_spacing_cm,
            plant_spacing_cm=plot.plant_spacing_cm,
            image_bytes=image_bytes,
            rgb=rgb,
            threshold=thr,
            metrics=metrics,
            quality=quality,
            detection_confidence=detection_confidence,
            crop=crop,
            crop_ids=crop_ids,
            lesion_share=spots_share,
            lesion_ids=lesion_ids,
            comparison=comparison,
            notes=notes,
            context=context,
            px_per_cm2=px_per_cm2,
            crop_info=info,
            irrigation=irrigation,
            experience=grower.experience if grower else None,
            scene=search.scene,
            color=color,
        ),
        tracer,
        sam,
        writer,
        add,
    )

    # 10. what it all cost (SAM calls + LLM tokens) and how long it took
    attempts = search.attempts
    n_sam = len(attempts) + len(side_jobs) + (1 if outcome.report.looked_closer else 0)
    llm_usage = search.llm
    llm_cost = llm_usage.cost_usd if llm_usage else 0.0
    writer_usage = outcome.llm
    writer_cost = writer_usage.cost_usd if writer_usage else 0.0
    run_stats = RunStats(
        strategy=search.strategy,
        scene=search.scene,
        crop_visible=search.crop_visible,
        proposals=search.proposals,
        scan_items=search.scan_items,
        attempts=[AttemptOut(**a.to_dict()) for a in attempts],
        chosen=search.chosen,
        sam_calls=n_sam,
        sam_cost_usd=sam_cost(n_sam),
        llm=LLMUsage(**{k: getattr(llm_usage, k) for k in LLMUsage.model_fields}) if llm_usage else None,
        total_cost_usd=None if llm_cost is None or writer_cost is None else round(sam_cost(n_sam) + llm_cost + writer_cost, 6),
        sam_latency_s=sam_latency(attempts),
        wall_time_s=round(time.monotonic() - started, 2),
        summary_llm=LLMUsage(**{k: getattr(writer_usage, k) for k in LLMUsage.model_fields}) if writer_usage else None,
    )

    result = AnalysisResult(
        analysis_id=analysis.id,
        plot_id=plot.id,
        captured_at=analysis.captured_at,
        days_after_planting=days_after_planting,
        segmenter=segmenter_name(),
        image=ImageInfo(width=w, height=h),
        image_quality=ImageQuality(**quality),
        masks=masks,
        metrics=metrics,
        scale=Scale(found=paper is not None, mask_id=scale_id, px_per_cm2=None if px_per_cm2 is None else round(px_per_cm2, 3), note=scale_note),
        health=outcome.health,
        context=outcome.context,
        comparison=outcome.comparison,
        crop_info=info,
        irrigation=irrigation,
        summary=Summary(**outcome.summary),
        notes_since_previous=notes,
        report=outcome.report,
        run_stats=run_stats,
        agent_trace=[TraceStep(**s) for s in tracer.steps],
    )
    result.report.markdown = report_agent.render_markdown(result, plot.name, label)
    return result


# ------------------------------------------------------------------ history


def _previous(db: Session, analysis: Analysis) -> Analysis | None:
    stmt = (
        select(Analysis)
        .where(
            Analysis.plot_id == analysis.plot_id,
            Analysis.status == "done",
            Analysis.id != analysis.id,
            Analysis.captured_at <= analysis.captured_at,
        )
        .order_by(Analysis.captured_at.desc(), Analysis.created_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def _notes_since(db: Session, analysis: Analysis, previous: Analysis | None) -> list[dict]:
    """The grower's notes between the previous photo and this one (the agent may refer to them)."""
    start = previous.captured_at if previous else analysis.captured_at - dt.timedelta(days=NOTES_WINDOW_DAYS)
    stmt = (
        select(Note)
        .where(Note.plot_id == analysis.plot_id, Note.noted_on > start, Note.noted_on <= analysis.captured_at)
        .order_by(Note.noted_on)
    )
    return [{"date": n.noted_on.isoformat(), "kind": n.kind, "text": n.text[:300]} for n in db.scalars(stmt)]


def _value(metrics: dict, key: str):
    item = metrics.get(key)
    return None if item is None else item.get("value")


def _compare(previous: Analysis, analysis: Analysis, metrics: Metrics) -> Comparison:
    prev = previous.result["metrics"]
    cur = metrics.model_dump()
    days = (analysis.captured_at - previous.captured_at).days
    deltas = {}
    for key in COMPARED:
        a, b = _value(prev, key), _value(cur, key)
        if a is None or b is None:
            continue
        if key == "mean_plant_area" and prev[key]["unit"] != cur[key]["unit"]:
            continue  # px vs cm² are not comparable
        deltas[key] = round(b - a, 1)
    growth = {}
    if days > 0:
        if "canopy_cover_pct" in deltas:
            growth["canopy_pts_per_day"] = round(deltas["canopy_cover_pct"] / days, 2)
        if "mean_plant_area" in deltas:
            growth[f"mean_plant_area_{cur['mean_plant_area']['unit']}_per_day"] = round(deltas["mean_plant_area"] / days, 2)
    a, b = _value(prev, "canopy_cover_pct"), _value(cur, "canopy_cover_pct")
    summary = f"Crop cover went from {a:.1f}% to {b:.1f}% in {days} days."
    return Comparison(
        previous_analysis_id=previous.id,
        previous_captured_at=previous.captured_at,
        days_between=days,
        deltas=deltas,
        growth_rate=growth,
        summary=summary,
    )


def _weather_day(analysis: Analysis):
    """Water need for the day the photo was taken (Open-Meteo keeps ~3 months), else today."""
    import datetime as dt

    today = dt.date.today()
    day = analysis.captured_at
    return day if day <= today and (today - day).days <= 90 else today


def _context(
    metrics: Metrics, comparison: Comparison | None, previous: Analysis | None, quality: dict, info: dict | None = None
) -> list[ContextItem]:
    items: list[ContextItem] = []
    canopy = metrics.canopy_cover_pct.value
    weed = metrics.weed_share_pct.value
    prev = previous.result["metrics"] if previous else None
    days = comparison.days_between if comparison else None

    # "Is this normal?" for crop cover: compare with the crop library band for this age
    if info is not None:
        lo, hi = info["cover_typical_pct"]
        where = f"Day {info['day']} {info['label'].lower()} is in the {info['stage']} stage"
        if canopy < lo:
            items.append(
                ContextItem(
                    metric="canopy_cover_pct",
                    status="attention",
                    badge="Behind typical",
                    text=f"{where}. Crop cover of {canopy:.1f}% is below the {lo}-{hi}% usually seen at this age. "
                    "Plants may be slow, gaps may need replanting, or the photo was taken from higher up than usual.",
                )
            )
        elif canopy > hi:
            items.append(
                ContextItem(
                    metric="canopy_cover_pct",
                    status="typical",
                    text=f"{where}. Crop cover of {canopy:.1f}% is above the {lo}-{hi}% usually seen at this age: "
                    "strong growth, or a closer photo than usual.",
                )
            )
        else:
            items.append(
                ContextItem(
                    metric="canopy_cover_pct",
                    status="typical",
                    text=f"{where}. Crop cover of {canopy:.1f}% is within the {lo}-{hi}% usually seen at this age.",
                )
            )

    if quality["level"] == "low":
        problem = "blurry" if not quality["sharp"] else quality["exposure"].replace("_", " ")
        items.append(
            ContextItem(
                metric="image_quality",
                status="attention",
                badge="Retake photo",
                text=f"The photo looks {problem}, so the numbers may be off. Retake it in even light with a steady hand.",
            )
        )

    if prev is not None and days:
        before = _value(prev, "canopy_cover_pct")
        if canopy - before <= -CANOPY_DROP_PTS:
            items.append(
                ContextItem(
                    metric="canopy_cover_pct",
                    status="attention",
                    badge="Crop cover dropped",
                    text=f"Crop cover fell from {before:.1f}% to {canopy:.1f}% in {days} days. "
                    "Check whether plants were thinned, harvested or damaged, or whether the photo was framed differently.",
                )
            )
        else:
            verb = "rose" if canopy >= before else "eased"
            items.append(
                ContextItem(
                    metric="canopy_cover_pct",
                    status="typical",
                    text=f"Crop cover {verb} from {before:.1f}% to {canopy:.1f}% in {days} days.",
                )
            )
    else:
        items.append(
            ContextItem(
                metric="canopy_cover_pct",
                status="info",
                text=f"Your crop covers {canopy:.1f}% of the photo. Take another photo from the same spot in a few days to see growth.",
            )
        )

    prev_weed = _value(prev, "weed_share_pct") if prev else None
    if prev_weed is not None and days and weed >= WEED_DOUBLING_MIN_PCT and weed >= 2 * prev_weed:
        items.append(
            ContextItem(
                metric="weed_share_pct",
                status="attention",
                badge="Weeds rising",
                text=f"Weed share rose from {prev_weed:.1f}% to {weed:.1f}% in {days} days; a good time to weed.",
            )
        )
    elif weed >= WEED_HIGH_PCT:
        items.append(
            ContextItem(
                metric="weed_share_pct",
                status="attention",
                badge="Many weeds",
                text=f"Weeds make up {weed:.1f}% of the green area in this photo; a good time to weed.",
            )
        )
    else:
        items.append(
            ContextItem(metric="weed_share_pct", status="typical", text=f"Weeds make up {weed:.1f}% of the green area.")
        )
    return items
