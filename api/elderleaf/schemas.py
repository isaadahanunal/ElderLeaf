"""API shapes. `AnalysisResult` is the contract with the frontend (see /docs or /openapi.json;
generate TS types with `npx openapi-typescript http://localhost:8000/openapi.json -o web/src/api.d.ts`)."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NoteKind = Literal["watering", "fertilizer", "spraying", "observation", "other"]


# ------------------------------------------------------------------ inputs


class PlotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    crop: str = Field(description="crop id from GET /crops (the main crop)")
    mixed: bool = Field(
        default=False,
        description="more than one crop grows in the same photo: the agent lists every kind of plant it sees "
        "(scan mode) instead of choosing words for one crop",
    )
    other_crops: list[str] = Field(default=[], description="the other crops of a mixed bed (crop ids; 'other' if unsure)")
    planted_on: dt.date | None = None
    area_m2: float | None = Field(default=None, gt=0)
    row_spacing_cm: float | None = Field(default=None, gt=0)
    plant_spacing_cm: float | None = Field(default=None, gt=0)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class NoteCreate(BaseModel):
    kind: NoteKind
    date: dt.date
    text: str = Field(min_length=1, max_length=2000)


# ------------------------------------------------------------------ analysis result (stored as JSON)


class ImageInfo(BaseModel):
    width: int
    height: int


class ImageQuality(BaseModel):
    blur: float = Field(description="sharpness: variance of the Laplacian; higher is sharper, < 80 is blurry")
    brightness: float = Field(description="mean gray level 0..255; 50-210 is fine")
    clipped_pct: float = Field(description="% of pixels burned out (a channel at 255) or pure black")
    sharp: bool
    exposure: Literal["ok", "too_dark", "too_bright"]
    exposure_ok: bool
    level: Literal["good", "low"]


class MaskOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    class_: Literal["crop", "weed", "lesion", "scale"] = Field(alias="class")
    prompt: str
    score: float | None
    area_px: int
    box: list[int] = Field(description="x0, y0, x1, y1 in image pixels")
    polygons: list[list[list[int]]] = Field(description="outlines as [[x, y], ...] in image pixels")
    crop: str | None = Field(default=None, description="crop id of a crop mask (None when plants could not be told apart)")


class MetricValue(BaseModel):
    value: float | None
    unit: str
    how: str = Field(description="'How it's computed' text for the UI")
    mask_ids: list[str] = []


class CropBreakdown(BaseModel):
    label: str
    plant_count: int
    canopy_cover_pct: float
    mask_ids: list[str] = []


class Metrics(BaseModel):
    plant_count: MetricValue
    canopy_cover_pct: MetricValue
    weed_share_pct: MetricValue
    lesion_share_pct: MetricValue | None = None
    mean_plant_area: MetricValue
    by_crop: dict[str, CropBreakdown] | None = Field(default=None, description="mixed beds: count and cover per crop id")


class Scale(BaseModel):
    found: bool
    mask_id: str | None = None
    px_per_cm2: float | None = None
    note: str


class HealthSign(BaseModel):
    type: str = Field(description="yellowing | browning | leaf_spots | a sign the agent asked SAM to look for")
    likelihood: Literal["low", "medium", "high"] = Field(description="set in code from share_pct")
    evidence_mask_ids: list[str]
    description: str
    share_pct: float | None = Field(default=None, description="% of crop area showing the sign (measured in code)")
    how: str | None = None


class Health(BaseModel):
    assessed: bool = Field(description="false when there were too few crop pixels to judge")
    signs: list[HealthSign] = []
    detection_confidence: float | None
    confidence: float | None = Field(default=None, description="detection confidence, lowered for a poor photo")
    consult_agronomist: bool
    consult_reasons: list[str] = []
    measures: dict[str, float] = Field(default={}, description="yellowing / browning / leaf_spots as % of crop area")
    summary: str | None = None


class ContextItem(BaseModel):
    metric: str
    status: Literal["typical", "attention", "info"]
    text: str
    badge: str | None = Field(default=None, description="short label for plot cards when status is attention")


class Comparison(BaseModel):
    previous_analysis_id: str
    previous_captured_at: dt.date
    days_between: int
    deltas: dict[str, float]
    growth_rate: dict[str, float]
    summary: str


class TraceStep(BaseModel):
    step: int
    tool: str
    label: str
    input: str | None = None
    result: str | None = None
    status: Literal["running", "done", "failed", "skipped"]
    image_url: str | None = Field(default=None, description="picture of this SAM call's masks (run_sam steps)")


class AttemptOut(BaseModel):
    target: Literal["crop", "weed"]
    prompt: str
    rank: int | Literal["fallback"] = Field(description="1-3 = agent's order; fallback = fixed word")
    round: int
    masks: int
    kept: int
    mean_confidence: float | None
    latency_s: float | None
    cached: bool
    ok: bool = Field(description="SAM answered confidently, so the chain stopped here")
    error: str | None = None


class ChosenPrompt(BaseModel):
    prompt: str
    rank: int | Literal["fallback"]


class LLMUsage(BaseModel):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int = Field(description="includes reasoning tokens")
    reasoning_tokens: int
    latency_s: float
    cost_usd: float | None
    cached: bool
    cached_input_tokens: int = 0


class RunStats(BaseModel):
    """How the SAM search words were chosen, and what it cost."""

    strategy: Literal["agent", "scan", "fixed"] = Field(
        description="agent = ranked words for one crop; scan = mixed bed, one phrase per kind of plant; fixed = no LLM"
    )
    scene: str | None = Field(default=None, description="agent's one-line description of the photo")
    scan_items: list[dict] = Field(default=[], description="scan mode: the phrases the agent listed (phrase, kind, crop)")
    crop_visible: bool | None = None
    proposals: dict[str, list[str]] = {}
    attempts: list[AttemptOut]
    chosen: dict[str, ChosenPrompt]
    sam_calls: int
    sam_cost_usd: float
    llm: LLMUsage | None = None
    total_cost_usd: float | None = Field(description="None when the LLM price is unknown (set LLM_PRICE_*)")
    sam_latency_s: float
    wall_time_s: float
    report_llm: LLMUsage | None = Field(default=None, description="the report agent's LLM calls, summed")


class Irrigation(BaseModel):
    date: dt.date
    et0_mm: float = Field(description="reference evapotranspiration of the day (FAO-56), from Open-Meteo")
    rain_mm: float | None
    kc: float = Field(description="crop coefficient used: stage Kc capped by the measured crop cover")
    kc_stage: float | None
    stage: str | None
    liters_per_m2: float
    plot_total_liters: float | None
    how: str
    text: str
    source: str


class Report(BaseModel):
    """The single combined report: every section above, worded by the report agent."""

    headline: str
    next_steps: list[str] = []
    markdown: str
    written_by: Literal["agent", "template"] = Field(description="template = the agent's text failed the validator or no LLM")
    validator: dict = Field(description="passed, attempts, errors of the last check")
    looked_closer: str | None = Field(default=None, description="SAM phrase the agent asked for to check a possible sign")


class AnalysisResult(BaseModel):
    analysis_id: str
    plot_id: str
    captured_at: dt.date
    days_after_planting: int | None
    image: ImageInfo
    image_quality: ImageQuality
    masks: list[MaskOut]
    metrics: Metrics
    scale: Scale
    health: Health
    context: list[ContextItem]
    comparison: Comparison | None
    irrigation: Irrigation | None = None
    report: Report | None = None
    run_stats: RunStats | None = None
    agent_trace: list[TraceStep]


# ------------------------------------------------------------------ outputs


class CropOut(BaseModel):
    id: str
    label: str


class AnalysisSummary(BaseModel):
    id: str
    captured_at: dt.date
    status: str
    image_url: str
    plant_count: float | None = None
    canopy_cover_pct: float | None = None
    weed_share_pct: float | None = None
    lesion_share_pct: float | None = None
    attention: list[str] = []


class AnalysisOut(BaseModel):
    id: str
    plot_id: str
    captured_at: dt.date
    status: str
    error: str | None
    image_url: str
    overlay_url: str | None = Field(description="picture of the final masks, colored by class")
    trace: list[TraceStep]
    result: AnalysisResult | None


class NoteOut(BaseModel):
    id: str
    kind: str
    date: dt.date
    text: str


class PlotOut(BaseModel):
    id: str
    name: str
    crop: str
    crop_label: str
    mixed: bool = False
    other_crops: list[str] = []
    other_crop_labels: list[str] = []
    planted_on: dt.date | None
    days_after_planting: int | None
    area_m2: float | None
    row_spacing_cm: float | None
    plant_spacing_cm: float | None
    lat: float | None
    lon: float | None
    is_demo: bool
    latest: AnalysisSummary | None
    deltas: dict[str, float] | None = Field(description="latest vs previous analysis")
    attention: list[str]


class PlotDetail(PlotOut):
    analyses: list[AnalysisSummary]
    notes: list[NoteOut]


# ------------------------------------------------------------------ compare two dates


class CompareSide(BaseModel):
    analysis_id: str
    captured_at: dt.date
    days_after_planting: int | None
    image_url: str
    overlay_url: str | None


class CompareRow(BaseModel):
    metric: str
    label: str
    unit: str | None
    before: float | None
    after: float | None
    change: float | None
    per_day: float | None = Field(description="change / days between the photos")


class CompareOut(BaseModel):
    """The plan's Compare tab: two photos of one plot, a difference table, notes in between, agent summary."""

    plot_id: str
    before: CompareSide
    after: CompareSide
    days_between: int
    rows: list[CompareRow]
    by_crop: list[dict] = Field(default=[], description="mixed beds: crop, label, before, after, change (plant counts)")
    notes: list[NoteOut] = Field(description="the grower's notes between the two photos")
    summary: str
    next_step: str | None = None
    written_by: Literal["agent", "template"]
    validator: dict
