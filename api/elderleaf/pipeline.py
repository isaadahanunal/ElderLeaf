"""Photo analysis: SAM 3.1 masks -> cleanup -> metrics -> history -> plain-language context.

Deterministic on purpose: every number is computed in code, and the context sentences are
templates filled with those numbers. The Muse Spark agent (next step) sits on top: it may
re-prompt SAM and rephrase the context, but never invents a number.

Each step is written to `analyses.trace` as it happens, so the UI can show it live by polling.
"""

from __future__ import annotations

import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agent import Proposal, propose_prompts
from .config import settings
from .crops import FALLBACK_PROMPT, crop_label, crop_prompt
from .db import Analysis, SessionLocal
from .llm import LLMClient
from .masks import clean_instances, instance_iou, resolve_cross_class
from .metrics import compute_metrics, find_scale, image_quality, mask_polygons
from .prompting import Attempt, Chain, build_candidates, run_chains, sam_cost, sam_latency
from .sam import Instance, SamClient, SamError, Segmentation
from .schemas import (
    AnalysisResult,
    AttemptOut,
    ChosenPrompt,
    Comparison,
    ContextItem,
    Health,
    HealthSign,
    ImageInfo,
    ImageQuality,
    LLMUsage,
    MaskOut,
    Metrics,
    MetricValue,
    RunStats,
    Scale,
    TraceStep,
)
from .storage import get_storage

log = logging.getLogger("elderleaf.pipeline")

PROMPT_WEED = "weed"
PROMPT_SCALE = "white paper sheet"
PROMPT_LESION = "leaf spot"

CONSULT_CONFIDENCE = 0.6  # plan rule: consult flag when confidence < 0.6
LESION_CONSULT_PCT = 5.0
# Product rules for the "Is this normal?" lines (not agronomic facts; tune with real use)
WEED_HIGH_PCT = 25.0
WEED_DOUBLING_MIN_PCT = 5.0
CANOPY_DROP_PTS = 5.0

COMPARED = ("plant_count", "canopy_cover_pct", "weed_share_pct", "lesion_share_pct", "mean_plant_area")

_sam: SamClient | None = None


def get_sam() -> SamClient:
    global _sam
    if _sam is None:
        _sam = SamClient()
    return _sam


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


def _describe(instances: list[Instance]) -> str:
    if not instances:
        return "no masks"
    return f"{len(instances)} masks, mean confidence {_mean_score(instances):.2f}"


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
        tracer.done(step, "no LLM key configured; using the fixed words", status="skipped")
        return None
    proposal = propose_prompts(llm, image_bytes, label, days_after_planting)
    if proposal.error:
        tracer.done(step, f"agent unavailable ({proposal.error}); using the fixed words", status="failed")
    else:
        crop_words = " / ".join(proposal.crop_prompts) or "-"
        weed_words = " / ".join(proposal.weed_prompts) or "-"
        tracer.done(step, f"crop: {crop_words}; weeds: {weed_words}")
    return proposal


def _analyze(db: Session, analysis: Analysis, tracer: Tracer) -> AnalysisResult:
    started = time.monotonic()
    plot = analysis.plot
    image_bytes = get_storage().get(analysis.image_key)
    rgb = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    h, w = rgb.shape[:2]
    thr = settings.score_threshold
    days_after_planting = (analysis.captured_at - plot.planted_on).days if plot.planted_on else None

    # 1. photo quality
    step = tracer.start("check_image_quality", "Checking photo quality")
    quality = image_quality(rgb)
    tracer.done(step, f"sharpness {quality['blur']}, brightness {quality['brightness']} -> {quality['level']}")

    # 2. what should SAM look for? Agent's 3 ranked phrases first, then the fixed word.
    proposal = _choose_words(tracer, image_bytes, crop_label(plot.crop), days_after_planting)
    agent_ok = proposal is not None and proposal.error is None
    fixed_crop = crop_prompt(plot.crop)
    if agent_ok:  # agent's 3 phrases, then the plain "plant"
        crop_chain = Chain("crop", build_candidates(proposal.crop_prompts, [FALLBACK_PROMPT]))
        weed_chain = Chain("weed", build_candidates(proposal.weed_prompts, [PROMPT_WEED]))
    else:
        crop_chain = Chain("crop", build_candidates([], [fixed_crop, FALLBACK_PROMPT]))
        weed_chain = Chain("weed", build_candidates([], [PROMPT_WEED]))

    def on_start(chain: Chain, prompt: str, rank) -> int:
        what = "crop plants" if chain.target == "crop" else "weeds"
        which = f"agent's choice {rank}" if isinstance(rank, int) else ("fallback word" if agent_ok else "fixed word")
        return tracer.start("run_sam", f"Finding {what} ({which})", input=prompt)

    def on_done(step: int, chain: Chain, attempt: Attempt) -> None:
        if attempt.error:
            tracer.done(step, f"failed: {attempt.error}", status="failed")
            return
        confidence = f", mean confidence {attempt.mean_confidence:.2f}" if attempt.mean_confidence is not None else ""
        verdict = "confident, using it" if attempt.ok else ("weak, no words left" if chain.finished else "weak, trying the next word")
        tracer.done(step, f"{attempt.masks} masks, {attempt.kept} above {thr:g}{confidence}: {verdict}")

    # 3. SAM 3.1: crop and weed chains round by round; A4 (and leaf spots) alongside
    sam = get_sam()
    side_jobs = {"scale": (PROMPT_SCALE, "Looking for an A4 sheet (scale)")}
    if settings.enable_lesion:
        side_jobs["lesion"] = (PROMPT_LESION, "Looking for leaf spots")
    side_steps = {key: tracer.start("run_sam", label, input=prompt) for key, (prompt, label) in side_jobs.items()}
    segs: dict[str, Segmentation | None] = {}
    with ThreadPoolExecutor(max_workers=len(side_jobs)) as side:
        side_futures = {key: side.submit(sam.segment, image_bytes, prompt) for key, (prompt, _) in side_jobs.items()}
        run_chains(sam, image_bytes, [crop_chain, weed_chain], thr, on_start=on_start, on_done=on_done)
        for key, future in side_futures.items():
            try:
                segs[key] = future.result()
                tracer.done(side_steps[key], _describe(segs[key].instances))
            except Exception as exc:  # scale and spots are optional
                segs[key] = None
                tracer.done(side_steps[key], f"skipped: {exc}", status="failed")
    if crop_chain.chosen_seg is None:
        errors = [a.error for a in crop_chain.attempts if a.error]
        raise SamError("SAM gave no answer for the crop" + (f": {errors[-1]}" if errors else ""))
    crop_raw, used_crop_prompt = crop_chain.chosen_seg.instances, crop_chain.chosen.prompt
    weed_raw = weed_chain.chosen_seg.instances if weed_chain.chosen_seg else []
    used_weed_prompt = weed_chain.chosen.prompt if weed_chain.chosen else PROMPT_WEED

    # 4. cleanup + metrics
    step = tracer.start("compute_metrics", "Cleaning masks and computing metrics")
    paper, px_per_cm2, scale_note = find_scale(segs["scale"].instances if segs.get("scale") else [])
    crop = clean_instances(crop_raw, h * w, thr)
    weed = clean_instances(weed_raw, h * w, thr)
    if paper is not None:  # the sheet itself is never a plant
        crop = [c for c in crop if instance_iou(c, paper) < 0.5]
        weed = [x for x in weed if instance_iou(x, paper) < 0.5]
    # The grower told us the crop, so when a weed phrase also matched a crop plant the crop wins
    # (on 6 PhenoBench images this cut the plant-count error from 8.2 to 3.5 for the agent).
    resolved = resolve_cross_class({"crop": crop, "weed": weed}, priority=["crop", "weed"])
    crop, weed = resolved["crop"], resolved["weed"]
    lesion = None
    if segs.get("lesion") is not None:
        lesion = clean_instances(segs["lesion"].instances, h * w, thr, min_area_frac=0.0)
    m = compute_metrics(crop, weed, lesion, h, w, px_per_cm2)

    masks: list[MaskOut] = []

    def add(inst: Instance, cls: str, prompt: str) -> str:
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
            )
        )
        return mask_id

    crop_ids = [add(c, "crop", used_crop_prompt) for c in crop]
    weed_ids = [add(x, "weed", used_weed_prompt) for x in weed]
    lesion_ids = [add(x, "lesion", PROMPT_LESION) for x in lesion or []]
    scale_id = add(paper, "scale", PROMPT_SCALE) if paper is not None else None
    tracer.done(
        step,
        f"{m['plant_count']} plants, canopy {m['canopy_cover_pct']}%, weed share {m['weed_share_pct']}%",
    )

    metrics = Metrics(
        plant_count=MetricValue(
            value=m["plant_count"],
            unit="plants",
            how=f"Number of '{used_crop_prompt}' masks with confidence ≥ {thr}, after removing tiny masks.",
            mask_ids=crop_ids,
        ),
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
        if lesion is None
        else MetricValue(
            value=m["lesion_share_pct"],
            unit="%",
            how="Leaf-spot area on crop plants divided by crop area.",
            mask_ids=lesion_ids,
        ),
        mean_plant_area=MetricValue(
            value=m["mean_plant_area"],
            unit=m["mean_plant_area_unit"],
            how="Average crop mask area; in cm² when an A4 sheet in the photo sets the scale.",
            mask_ids=crop_ids,
        ),
    )

    # 5. history
    step = tracer.start("get_plot_history", "Comparing with the previous photo")
    previous = _previous(db, analysis)
    comparison = _compare(previous, analysis, metrics) if previous else None
    tracer.done(step, comparison.summary if comparison else "first photo of this plot")

    # 6. context + health (templated from the numbers above)
    context = _context(metrics, comparison, previous, quality)
    if proposal is not None and proposal.crop_visible is False:
        context.insert(
            0,
            ContextItem(
                metric="crop",
                status="attention",
                badge="Check crop",
                text=f"The assistant could not clearly see {crop_label(plot.crop).lower()} plants in this photo. Is this the right plot?",
            ),
        )
    detection_confidence = round(_mean_score(crop), 2) if crop else None
    health = _health(m, lesion is not None, lesion_ids, quality, detection_confidence)

    # 7. what the search cost (SAM calls + LLM tokens) and how long it took
    attempts = crop_chain.attempts + weed_chain.attempts
    n_sam = len(attempts) + len(side_jobs)
    llm_usage = proposal.llm if proposal is not None and proposal.llm is not None else None
    llm_cost = llm_usage.cost_usd if llm_usage else 0.0
    run_stats = RunStats(
        strategy="agent" if agent_ok else "fixed",
        scene=proposal.scene if proposal else None,
        crop_visible=proposal.crop_visible if proposal else None,
        proposals={"crop": proposal.crop_prompts, "weed": proposal.weed_prompts} if agent_ok else {},
        attempts=[AttemptOut(**a.to_dict()) for a in attempts],
        chosen={
            chain.target: ChosenPrompt(prompt=chain.chosen.prompt, rank=chain.chosen.rank)
            for chain in (crop_chain, weed_chain)
            if chain.chosen is not None
        },
        sam_calls=n_sam,
        sam_cost_usd=sam_cost(n_sam),
        llm=LLMUsage(**{k: getattr(llm_usage, k) for k in LLMUsage.model_fields}) if llm_usage else None,
        total_cost_usd=None if llm_cost is None else round(sam_cost(n_sam) + llm_cost, 6),
        sam_latency_s=sam_latency(attempts),
        wall_time_s=round(time.monotonic() - started, 2),
    )

    return AnalysisResult(
        analysis_id=analysis.id,
        plot_id=plot.id,
        captured_at=analysis.captured_at,
        days_after_planting=days_after_planting,
        image=ImageInfo(width=w, height=h),
        image_quality=ImageQuality(**quality),
        masks=masks,
        metrics=metrics,
        scale=Scale(found=paper is not None, mask_id=scale_id, px_per_cm2=None if px_per_cm2 is None else round(px_per_cm2, 3), note=scale_note),
        health=health,
        context=context,
        comparison=comparison,
        run_stats=run_stats,
        agent_trace=[TraceStep(**s) for s in tracer.steps],
    )


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


def _context(metrics: Metrics, comparison: Comparison | None, previous: Analysis | None, quality: dict) -> list[ContextItem]:
    items: list[ContextItem] = []
    canopy = metrics.canopy_cover_pct.value
    weed = metrics.weed_share_pct.value
    prev = previous.result["metrics"] if previous else None
    days = comparison.days_between if comparison else None

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


def _health(m: dict, assessed: bool, lesion_ids: list[str], quality: dict, confidence: float | None) -> Health:
    signs: list[HealthSign] = []
    share = m["lesion_share_pct"]
    if assessed and share is not None and share >= 1.0:
        likelihood = "low" if share < 3 else ("medium" if share < 10 else "high")
        signs.append(
            HealthSign(
                type="leaf_spots",
                likelihood=likelihood,
                evidence_mask_ids=lesion_ids[:20],
                description=f"Spots or discolored patches on {share:.1f}% of the crop area.",
            )
        )
    reasons = []
    if quality["level"] == "low":
        reasons.append("Photo quality is low, so these results are less reliable.")
    if share is not None and share >= LESION_CONSULT_PCT:
        reasons.append(f"Leaf spots cover {share:.1f}% of the crop area; spots have many possible causes.")
    if confidence is not None and confidence < CONSULT_CONFIDENCE:
        reasons.append(f"Plant detection confidence is low ({confidence:.2f}).")
    return Health(
        assessed=assessed,
        signs=signs,
        detection_confidence=confidence,
        consult_agronomist=bool(reasons),
        consult_reasons=reasons,
    )
