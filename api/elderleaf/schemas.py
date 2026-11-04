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
    crop: str = Field(description="crop id from GET /crops")
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


class MetricValue(BaseModel):
    value: float | None
    unit: str
    how: str = Field(description="'How it's computed' text for the UI")
    mask_ids: list[str] = []


class Metrics(BaseModel):
    plant_count: MetricValue
    canopy_cover_pct: MetricValue
    weed_share_pct: MetricValue
    lesion_share_pct: MetricValue | None = None
    mean_plant_area: MetricValue


class Scale(BaseModel):
    found: bool
    mask_id: str | None = None
    px_per_cm2: float | None = None
    note: str


class HealthSign(BaseModel):
    type: str
    likelihood: Literal["low", "medium", "high"]
    evidence_mask_ids: list[str]
    description: str


class Health(BaseModel):
    assessed: bool = Field(description="false when leaf-spot detection is switched off")
    signs: list[HealthSign] = []
    detection_confidence: float | None
    consult_agronomist: bool
    consult_reasons: list[str] = []


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

    strategy: Literal["agent", "fixed"]
    scene: str | None = Field(default=None, description="agent's one-line description of the photo")
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
    irrigation: dict | None = None
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
