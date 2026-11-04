"""ElderLeaf HTTP API.

    cd api && uv run uvicorn elderleaf.app:app --reload      # docs at http://localhost:8000/docs

No login: the browser sends a random `X-Device-Id` header (kept in localStorage). A device sees
its own plots plus the read-only demo plots.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from contextlib import asynccontextmanager
from urllib.parse import quote

import numpy as np
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .config import settings
from .crops import CROPS, LIBRARY_NOTE, crop_info, crop_label
from .db import Analysis, Note, Plot, get_db, init_db, new_id
from .irrigation import water_need
from .jobs import submit
from .pipeline import current_strategy, get_llm, get_sam, prepare_upload, segmenter_name
from .render import render_analysis, render_segmentation, to_png
from .sam import CacheMiss
from .schemas import (
    AnalysisOut,
    AnalysisResult,
    AnalysisSummary,
    CompareOut,
    CropOut,
    NoteCreate,
    NoteOut,
    PlotCreate,
    PlotDetail,
    PlotOut,
    Summary,
    TraceStep,
    VideoResult,
)
from .summary import write_summary
from .video import still_jpeg, to_web_mp4
from .storage import LocalStorage, get_storage

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 150 * 1024 * 1024
VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/mp4", ".webm": "video/webm"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ElderLeaf API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)
if isinstance(get_storage(), LocalStorage):
    app.mount("/files", StaticFiles(directory=get_storage().root), name="files")


def device_id(x_device_id: str | None = Header(default=None, max_length=64)) -> str | None:
    return x_device_id


# ------------------------------------------------------------------ helpers


def _plot_or_404(db: Session, plot_id: str) -> Plot:
    plot = db.get(Plot, plot_id)
    if plot is None:
        raise HTTPException(404, "Plot not found")
    return plot


def _require_owner(plot: Plot, device: str | None) -> None:
    if plot.is_demo:
        raise HTTPException(403, "Demo plots are read-only. Create your own plot to upload photos.")
    if not device or plot.device_id != device:
        raise HTTPException(403, "This plot belongs to another device.")


def _image_url(request: Request, key: str) -> str:
    return get_storage().url(key, str(request.base_url))


def _ordered(analyses: list[Analysis]) -> list[Analysis]:
    return sorted(analyses, key=lambda a: (a.captured_at, a.created_at))


def _attention(result: dict | None) -> list[str]:
    if not result:
        return []
    badges = [c["badge"] for c in result.get("context", []) if c.get("status") == "attention" and c.get("badge")]
    if result.get("health", {}).get("consult_agronomist"):
        badges.append("Consult suggested")
    return list(dict.fromkeys(badges))


def _summary(a: Analysis, request: Request) -> AnalysisSummary:
    result = a.result or {}
    if a.mode == "video":
        return AnalysisSummary(
            id=a.id,
            mode="video",
            captured_at=a.captured_at,
            status=a.status,
            image_url=_image_url(request, a.image_key),
            summary=(result.get("context") or [{}])[0].get("text"),
            row_plant_count=result.get("row_plant_count"),
            attention=_attention(result),
        )
    metrics = result.get("metrics", {})

    def value(key: str):
        item = metrics.get(key)
        return None if item is None else item.get("value")

    return AnalysisSummary(
        id=a.id,
        captured_at=a.captured_at,
        status=a.status,
        image_url=_image_url(request, a.image_key),
        summary=(result.get("summary") or {}).get("text"),
        plant_count=value("plant_count"),
        canopy_cover_pct=value("canopy_cover_pct"),
        weed_share_pct=value("weed_share_pct"),
        lesion_share_pct=value("lesion_share_pct"),
        mean_plant_area=value("mean_plant_area"),
        mean_plant_area_unit=(metrics.get("mean_plant_area") or {}).get("unit"),
        attention=_attention(result),
    )


def _plot_fields(plot: Plot, request: Request) -> dict:
    done = [a for a in _ordered(plot.analyses) if a.status == "done" and a.mode == "photo"]
    latest = done[-1] if done else None
    comparison = (latest.result or {}).get("comparison") if latest else None
    return {
        "id": plot.id,
        "name": plot.name,
        "crop": plot.crop,
        "crop_label": crop_label(plot.crop),
        "planted_on": plot.planted_on,
        "days_after_planting": (dt.date.today() - plot.planted_on).days if plot.planted_on else None,
        "area_m2": plot.area_m2,
        "row_spacing_cm": plot.row_spacing_cm,
        "plant_spacing_cm": plot.plant_spacing_cm,
        "lat": plot.lat,
        "lon": plot.lon,
        "is_demo": plot.is_demo,
        "latest": _summary(latest, request) if latest else None,
        "deltas": comparison["deltas"] if comparison else None,
        "attention": _attention(latest.result) if latest else [],
    }


def _analysis_out(a: Analysis, request: Request) -> AnalysisOut:
    base = str(request.base_url).rstrip("/")
    steps = []
    for s in a.trace or []:
        step = TraceStep(**s)
        if step.tool == "run_sam" and step.input and step.status == "done":
            step.image_url = f"{base}/analyses/{a.id}/sam.png?prompt={quote(step.input)}"
        steps.append(step)
    video = a.mode == "video"
    return AnalysisOut(
        id=a.id,
        plot_id=a.plot_id,
        mode=a.mode,
        captured_at=a.captured_at,
        status=a.status,
        error=a.error,
        image_url=_image_url(request, a.image_key),
        video_url=_image_url(request, a.video_key) if video and a.video_key else None,
        overlay_url=f"{base}/analyses/{a.id}/overlay.png" if a.result and not video else None,
        trace=steps,
        result=AnalysisResult.model_validate(a.result) if a.result and not video else None,
        video_result=VideoResult.model_validate(a.result) if a.result and video else None,
    )


def _analysis_or_404(db: Session, analysis_id: str) -> Analysis:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(404, "Analysis not found")
    return analysis


# ------------------------------------------------------------------ routes


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "sam_configured": bool(settings.model_api_key),
        "segmenter": segmenter_name(),
        "llm_configured": get_llm().configured,
        "llm_provider": settings.llm_provider,
        "lesion_enabled": settings.enable_lesion,
    }


@app.get("/crops", response_model=list[CropOut])
def crops() -> list[CropOut]:
    return [CropOut(id=k, label=v["label"]) for k, v in CROPS.items()]


@app.get("/plots", response_model=list[PlotOut])
def list_plots(request: Request, device: str | None = Depends(device_id), db: Session = Depends(get_db)):
    condition = Plot.is_demo.is_(True)
    if device:
        condition = or_(condition, Plot.device_id == device)
    plots = db.scalars(select(Plot).where(condition).order_by(Plot.is_demo, Plot.created_at.desc())).all()
    return [PlotOut(**_plot_fields(p, request)) for p in plots]


@app.post("/plots", response_model=PlotOut, status_code=201)
def create_plot(body: PlotCreate, request: Request, device: str | None = Depends(device_id), db: Session = Depends(get_db)):
    if not device:
        raise HTTPException(400, "Send an X-Device-Id header.")
    if body.crop not in CROPS:
        raise HTTPException(422, f"Unknown crop {body.crop!r}; see GET /crops.")
    plot = Plot(id=new_id("p"), device_id=device, **body.model_dump())
    db.add(plot)
    db.commit()
    db.refresh(plot)
    return PlotOut(**_plot_fields(plot, request))


@app.get("/plots/{plot_id}", response_model=PlotDetail)
def get_plot(plot_id: str, request: Request, db: Session = Depends(get_db)):
    plot = _plot_or_404(db, plot_id)
    return PlotDetail(
        **_plot_fields(plot, request),
        analyses=[_summary(a, request) for a in _ordered(plot.analyses)],
        notes=[
            NoteOut(id=n.id, kind=n.kind, date=n.noted_on, text=n.text)
            for n in sorted(plot.notes, key=lambda n: (n.noted_on, n.created_at))
        ],
    )


@app.delete("/plots/{plot_id}", status_code=204)
def delete_plot(plot_id: str, device: str | None = Depends(device_id), db: Session = Depends(get_db)) -> Response:
    plot = _plot_or_404(db, plot_id)
    _require_owner(plot, device)
    db.delete(plot)
    db.commit()
    return Response(status_code=204)


@app.post("/plots/{plot_id}/analyses", response_model=AnalysisOut, status_code=202)
def create_analysis(
    plot_id: str,
    request: Request,
    file: UploadFile = File(...),
    captured_at: dt.date | None = Form(default=None),
    device: str | None = Depends(device_id),
    db: Session = Depends(get_db),
):
    """Upload a photo. Returns at once with status `pending`; poll GET /analyses/{id}."""
    plot = _plot_or_404(db, plot_id)
    _require_owner(plot, device)
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photo is larger than 25 MB.")
    try:
        jpeg, width, height = prepare_upload(data, settings.analysis_max_side)
    except Exception:
        raise HTTPException(400, "Could not read this file as a photo.") from None

    analysis_id = new_id("a")
    key = f"plots/{plot.id}/{analysis_id}.jpg"
    get_storage().put(key, jpeg, "image/jpeg")
    analysis = Analysis(
        id=analysis_id,
        plot_id=plot.id,
        captured_at=captured_at or dt.date.today(),
        image_key=key,
        image_width=width,
        image_height=height,
        status="pending",
        trace=[],
    )
    db.add(analysis)
    db.commit()
    submit(analysis.id)
    db.refresh(analysis)
    return _analysis_out(analysis, request)


@app.post("/plots/{plot_id}/videos", response_model=AnalysisOut, status_code=202)
def create_video_analysis(
    plot_id: str,
    request: Request,
    file: UploadFile = File(...),
    captured_at: dt.date | None = Form(default=None),
    device: str | None = Depends(device_id),
    db: Session = Depends(get_db),
):
    """Upload a row-walk video (MP4/MOV, ~15 s). Returns `pending`; poll GET /analyses/{id}."""
    plot = _plot_or_404(db, plot_id)
    _require_owner(plot, device)
    suffix = "." + (file.filename or "row.mp4").rsplit(".", 1)[-1].lower()
    if suffix not in VIDEO_TYPES:
        suffix = ".mp4"
    data = file.file.read(MAX_VIDEO_BYTES + 1)
    if len(data) > MAX_VIDEO_BYTES:
        raise HTTPException(413, "Video is larger than 150 MB; record about 15 seconds.")
    try:
        still, width, height = still_jpeg(data, suffix)
    except Exception:
        raise HTTPException(400, "Could not read this file as a video (MP4 or MOV).") from None
    analysis_id = new_id("a")
    video_key = f"plots/{plot.id}/{analysis_id}{suffix}"
    web = to_web_mp4(data, suffix)  # small H.264 copy every browser plays; keep only that
    if web is not None:
        data, suffix, video_key = web, ".mp4", f"plots/{plot.id}/{analysis_id}.web.mp4"
    image_key = f"plots/{plot.id}/{analysis_id}.jpg"
    storage = get_storage()
    storage.put(video_key, data, VIDEO_TYPES[suffix])
    storage.put(image_key, still, "image/jpeg")
    analysis = Analysis(
        id=analysis_id,
        plot_id=plot.id,
        mode="video",
        captured_at=captured_at or dt.date.today(),
        image_key=image_key,
        video_key=video_key,
        image_width=width,
        image_height=height,
        status="pending",
        trace=[],
    )
    db.add(analysis)
    db.commit()
    submit(analysis.id)
    db.refresh(analysis)
    return _analysis_out(analysis, request)


@app.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, request: Request, db: Session = Depends(get_db)):
    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(404, "Analysis not found")
    return _analysis_out(analysis, request)


@app.get("/analyses/{analysis_id}/overlay.png", response_class=Response)
def analysis_overlay(analysis_id: str, db: Session = Depends(get_db)) -> Response:
    """The photo with the final masks, colored by class (crop green, weed magenta, A4 blue)."""
    analysis = _analysis_or_404(db, analysis_id)
    if not analysis.result or analysis.mode != "photo":
        raise HTTPException(409, "No mask picture for this analysis.")
    rgb = np.array(Image.open(io.BytesIO(get_storage().get(analysis.image_key))).convert("RGB"))
    return Response(to_png(render_analysis(rgb, analysis.result)), media_type="image/png")


@app.get("/analyses/{analysis_id}/sam.png", response_class=Response)
def sam_call_image(analysis_id: str, prompt: str, db: Session = Depends(get_db)) -> Response:
    """Everything one SAM call of this analysis returned, including masks dropped by the threshold.
    Reads the cache only, so it never triggers a new paid call."""
    analysis = _analysis_or_404(db, analysis_id)
    called = {s.get("input") for s in analysis.trace or [] if s.get("tool") == "run_sam"}
    if prompt not in called:
        raise HTTPException(404, "This analysis did not call SAM with that prompt.")
    image_bytes = get_storage().get(analysis.image_key)
    try:
        seg = get_sam().segment(image_bytes, prompt, offline=True)
    except CacheMiss:
        raise HTTPException(404, "That SAM answer is no longer cached.") from None
    rgb = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    panel = render_segmentation(rgb, seg.instances, prompt=prompt, threshold=settings.score_threshold)
    return Response(to_png(panel), media_type="image/png")


@app.post("/analyses/{analysis_id}/rerun", response_model=AnalysisOut, status_code=202)
def rerun_analysis(analysis_id: str, request: Request, device: str | None = Depends(device_id), db: Session = Depends(get_db)):
    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(404, "Analysis not found")
    _require_owner(analysis.plot, device)
    analysis.status, analysis.result, analysis.error, analysis.trace = "pending", None, None, []
    db.commit()
    submit(analysis.id)
    db.refresh(analysis)
    return _analysis_out(analysis, request)


@app.post("/plots/{plot_id}/notes", response_model=NoteOut, status_code=201)
def create_note(plot_id: str, body: NoteCreate, device: str | None = Depends(device_id), db: Session = Depends(get_db)):
    plot = _plot_or_404(db, plot_id)
    _require_owner(plot, device)
    note = Note(id=new_id("n"), plot_id=plot.id, kind=body.kind, noted_on=body.date, text=body.text)
    db.add(note)
    db.commit()
    return NoteOut(id=note.id, kind=note.kind, date=note.noted_on, text=note.text)


CSV_COLUMNS = [
    "date",
    "analysis_id",
    "plant_count",
    "canopy_cover_pct",
    "weed_share_pct",
    "lesion_share_pct",
    "mean_plant_area",
    "mean_plant_area_unit",
    "image_quality",
    "consult_agronomist",
    "row_plant_count",
    "mode",
]


@app.get("/plots/{plot_id}/export.csv")
def export_csv(plot_id: str, db: Session = Depends(get_db)) -> Response:
    plot = _plot_or_404(db, plot_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for a in _ordered(plot.analyses):
        if a.status != "done" or not a.result:
            continue
        if a.mode == "video":
            writer.writerow([a.captured_at.isoformat(), a.id] + [""] * 8 + [a.result["row_plant_count"], "video"])
            continue
        m = a.result["metrics"]

        def value(key: str):
            return "" if m.get(key) is None else m[key]["value"]

        writer.writerow(
            [
                a.captured_at.isoformat(),
                a.id,
                value("plant_count"),
                value("canopy_cover_pct"),
                value("weed_share_pct"),
                value("lesion_share_pct"),
                value("mean_plant_area"),
                m["mean_plant_area"]["unit"],
                a.result["image_quality"]["level"],
                a.result["health"]["consult_agronomist"],
                "",
                "photo",
            ]
        )
    filename = re.sub(r"[^A-Za-z0-9_-]+", "-", plot.name).strip("-") or plot.id
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


# ------------------------------------------------------------------ water, crop info, compare


@app.get("/plots/{plot_id}/water")
def todays_water(plot_id: str, db: Session = Depends(get_db)) -> dict:
    """Today's water need from the latest crop cover (FAO-56, Open-Meteo ET0)."""
    plot = _plot_or_404(db, plot_id)
    done = [a for a in _ordered(plot.analyses) if a.status == "done" and a.mode == "photo"]
    cover = done[-1].result["metrics"]["canopy_cover_pct"]["value"] if done else None
    day = (dt.date.today() - plot.planted_on).days if plot.planted_on else None
    out = water_need(plot.crop, day, cover, plot.area_m2, plot.lat, plot.lon)
    out["based_on_analysis_id"] = done[-1].id if done else None
    return out


@app.get("/crops/{crop_id}/info")
def crop_reference(crop_id: str, day: int) -> dict:
    info = crop_info(crop_id, day)
    if info is None:
        raise HTTPException(404, "No reference values for this crop.")
    return {**info, "note": LIBRARY_NOTE}


COMPARE_ROWS = [
    ("plant_count", "Plants", "plants"),
    ("canopy_cover_pct", "Crop cover", "%"),
    ("weed_share_pct", "Weed share", "%"),
    ("lesion_share_pct", "Leaf spots", "%"),
    ("mean_plant_area", "Mean plant size", None),
]


@app.get("/plots/{plot_id}/compare", response_model=CompareOut)
def compare(plot_id: str, a: str, b: str, request: Request, db: Session = Depends(get_db)):
    """Two dates of one plot: metric differences, notes in between and a validated change summary."""
    plot = _plot_or_404(db, plot_id)
    first, second = _analysis_or_404(db, a), _analysis_or_404(db, b)
    if first.plot_id != plot.id or second.plot_id != plot.id:
        raise HTTPException(404, "Both analyses must belong to this plot.")
    if first.mode != "photo" or second.mode != "photo" or not (first.result and second.result):
        raise HTTPException(409, "Compare needs two finished photo analyses.")
    if (first.captured_at, first.created_at) > (second.captured_at, second.created_at):
        first, second = second, first
    days = (second.captured_at - first.captured_at).days
    ma, mb = first.result["metrics"], second.result["metrics"]
    rows = []
    for key, label, unit in COMPARE_ROWS:
        va, vb = (ma.get(key) or {}).get("value"), (mb.get(key) or {}).get("value")
        unit = unit or (mb.get(key) or {}).get("unit")
        if key == "mean_plant_area" and (ma.get(key) or {}).get("unit") != (mb.get(key) or {}).get("unit"):
            va = None  # px vs cm² are not comparable
        delta = None if va is None or vb is None else round(vb - va, 1)
        per_day = None if delta is None or days <= 0 else round(delta / days, 2)
        rows.append({"metric": key, "label": label, "unit": unit, "a": va, "b": vb, "delta": delta, "per_day": per_day})
    notes = [
        n
        for n in sorted(plot.notes, key=lambda n: n.noted_on)
        if first.captured_at < n.noted_on <= second.captured_at
    ]
    note_dicts = [{"date": n.noted_on.isoformat(), "kind": n.kind, "text": n.text} for n in notes]
    lines = []
    for r in rows:
        if r["delta"] is None:
            continue
        if r["metric"] == "plant_count":
            lines.append(f"Plant count went from {r['a']:g} to {r['b']:g}.")
        elif r["metric"] in ("canopy_cover_pct", "weed_share_pct"):
            lines.append(f"{r['label']} went from {r['a']:.1f}% to {r['b']:.1f}% in {days} days.")
    facts = {
        "crop": crop_label(plot.crop),
        "days_between": days,
        "dates": [first.captured_at.isoformat(), second.captured_at.isoformat()],
        "rows": rows,
        "context": [{"status": "info", "text": t} for t in lines],
        "grower_notes_between": note_dicts,
        "health": {"consult_agronomist": bool(second.result["health"]["consult_agronomist"])},
    }
    cache_key = f"{first.id}:{len(notes)}"
    cached = (second.result.get("compare_cache") or {}).get(cache_key)
    if cached:
        summary = Summary(**cached)
    else:
        written = write_summary(get_llm() if current_strategy() == "agent" else None, facts)
        summary = Summary(**written.to_dict())
        if not plot.is_demo or written.source == "agent":  # remember agent text so the jury view costs nothing
            result = dict(second.result)
            result["compare_cache"] = {**(result.get("compare_cache") or {}), cache_key: summary.model_dump()}
            second.result = result
            db.commit()
    return CompareOut(
        a=_summary(first, request),
        b=_summary(second, request),
        days_between=days,
        rows=rows,
        notes_between=[NoteOut(id=n.id, kind=n.kind, date=n.noted_on, text=n.text) for n in notes],
        summary=summary,
    )
