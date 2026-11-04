"""Row counting from a walking video: every plant gets one id and is counted once.

The grower walks slowly along a row with the phone pointed down (~15 s). We:

1. sample frames (VIDEO_FPS per second, at most VIDEO_MAX_FRAMES),
2. pick the SAM phrase on the middle frame (crop name first, then "plant"), like the photo flow,
3. run SAM 3.1 on every sampled frame (cached by frame hash, run in parallel),
4. estimate how the camera moved between frames (ORB features + RANSAC similarity transform;
   phase correlation if there is too little texture),
5. move each plant's last box by that motion and match it to the new masks with IoU
   (Hungarian assignment). A match keeps the id; an unmatched mask starts a new id,
6. count ids seen in >= 2 sampled frames, or once with high confidence (a plant at the very
   start or end of the walk). Short, weak tracks are kept on screen but not counted.

Why our own tracker: SAM 3.1 image calls are known to work with our parser and cache; this needs
no assumption about how long the video endpoint keeps an object id. A native video call can
replace steps 3-5 later without changing the result shape.
"""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment

from .config import settings
from .crops import FALLBACK_PROMPT, crop_label, crop_prompt
from .db import Analysis, SessionLocal
from .masks import clean_instances
from .prompting import is_confident, sam_cost
from .sam import Instance
from .schemas import ContextItem, TraceStep, VideoBox, VideoFrame, VideoResult, VideoTrack
from .storage import get_storage

log = logging.getLogger("elderleaf.video")

MATCH_IOU = 0.15
MAX_MISSES = 2  # sampled frames a plant may be hidden before its id is retired
SINGLE_FRAME_SCORE = 0.8
SAM_WORKERS = 8


# ------------------------------------------------------------------ frames


def read_video(data: bytes, suffix: str = ".mp4") -> tuple[list[np.ndarray], list[float], float]:
    """Decode and sample frames. Returns RGB frames, their times (s) and the video duration (s)."""
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(data)
        tmp.flush()
        cap = cv2.VideoCapture(tmp.name)
        if not cap.isOpened():
            raise ValueError("could not open the video")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = total / fps if total else 0.0
        step = max(1, round(fps / settings.video_fps))
        if total and total / step > settings.video_max_frames:
            step = int(np.ceil(total / settings.video_max_frames))
        frames, times, index = [], [], 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if index % step == 0:
                ok, bgr = cap.retrieve()
                if not ok:
                    break
                h, w = bgr.shape[:2]
                scale = settings.video_max_side / max(h, w)
                if scale < 1:
                    bgr = cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
                frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                times.append(round(index / fps, 3))
            index += 1
        cap.release()
    if not frames:
        raise ValueError("the video has no readable frames")
    return frames, times, duration or (index / fps)


def still_jpeg(data: bytes, suffix: str = ".mp4") -> tuple[bytes, int, int]:
    """A still frame of the video for cards and thumbnails."""
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(data)
        tmp.flush()
        cap = cv2.VideoCapture(tmp.name)
        ok, bgr = cap.read()
        cap.release()
    if not ok:
        raise ValueError("could not read the video")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    img.thumbnail((settings.video_max_side, settings.video_max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue(), img.width, img.height


def to_web_mp4(data: bytes, suffix: str) -> bytes | None:
    """Phones record HEVC / MOV, which many desktop browsers can't play. With ffmpeg available,
    re-encode to H.264 MP4 (<= 1280 px, no audio, fast start). None when ffmpeg is missing or fails."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / f"in{suffix}", Path(tmp) / "out.mp4"
        src.write_bytes(data)
        cmd = [
            ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-an",
            "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=300)
            return dst.read_bytes()
        except (subprocess.SubprocessError, OSError):
            log.warning("ffmpeg could not convert the video; keeping the original")
            return None


def _jpeg(rgb: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# ------------------------------------------------------------------ camera motion


def estimate_motion(prev: np.ndarray, cur: np.ndarray) -> np.ndarray:
    """2x3 transform mapping points of `prev` to `cur`."""
    g0 = cv2.cvtColor(prev, cv2.COLOR_RGB2GRAY)
    g1 = cv2.cvtColor(cur, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(1500)
    k0, d0 = orb.detectAndCompute(g0, None)
    k1, d1 = orb.detectAndCompute(g1, None)
    if d0 is not None and d1 is not None and len(k0) >= 12 and len(k1) >= 12:
        matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d0, d1)
        if len(matches) >= 12:
            p0 = np.float32([k0[m.queryIdx].pt for m in matches])
            p1 = np.float32([k1[m.trainIdx].pt for m in matches])
            matrix, inliers = cv2.estimateAffinePartial2D(p0, p1, method=cv2.RANSAC, ransacReprojThreshold=4.0)
            if matrix is not None and inliers is not None and int(inliers.sum()) >= 10:
                return matrix
    (dx, dy), _ = cv2.phaseCorrelate(np.float32(g0), np.float32(g1))
    return np.float32([[1, 0, dx], [0, 1, dy]])


def _warp_box(box: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = box
    pts = np.float32([[x0, y0], [x1, y0], [x0, y1], [x1, y1]])
    moved = pts @ matrix[:, :2].T + matrix[:, 2]
    return np.array([moved[:, 0].min(), moved[:, 1].min(), moved[:, 0].max(), moved[:, 1].max()])


EDGE_PX = 3


def _touches_edge(box: np.ndarray, width: int, height: int) -> bool:
    return box[0] <= EDGE_PX or box[1] <= EDGE_PX or box[2] >= width - EDGE_PX or box[3] >= height - EDGE_PX


def _match_score(a: np.ndarray, b: np.ndarray, width: int, height: int, a_was_cut: bool = False) -> float:
    """IoU; but a plant cut by the frame edge only shows part of itself, so when either box
    is cut by the edge (`a_was_cut`: when it was last seen) we use how much of the smaller box
    lies inside the other."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    if a_was_cut or _touches_edge(a, width, height) or _touches_edge(b, width, height):
        smaller = min(area_a, area_b)
        return inter / smaller if smaller > 0 else 0.0
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


# ------------------------------------------------------------------ tracking


@dataclass
class Track:
    track_id: int
    box: np.ndarray  # last known box, moved along with the camera while hidden
    scores: list[float] = field(default_factory=list)
    times: list[float] = field(default_factory=list)
    misses: int = 0
    edge_only: bool = True  # never seen whole (always cut by the frame edge)
    last_cut: bool = False  # cut by the edge when last seen
    max_area: float = 0.0
    typical_area: float = 0.0  # median whole-plant box in this video, set after tracking

    def counted(self) -> bool:
        if len(self.times) >= 2:
            return True
        # seen once: count a confident plant; if it was cut by the edge, only when at least half
        # of a typical plant is visible (a thin sliver is too unsure)
        if not self.scores or max(self.scores) < SINGLE_FRAME_SCORE:
            return False
        return not self.edge_only or self.max_area >= 0.5 * self.typical_area


def track(frames: list[np.ndarray], times: list[float], detections: list[list[Instance]]):
    """Returns per-frame boxes with ids and the list of tracks."""
    tracks: list[Track] = []
    alive: list[Track] = []
    per_frame: list[list[tuple[int, list[int], float | None]]] = []
    height, width = frames[0].shape[:2]
    for i, dets in enumerate(detections):
        if i > 0:
            matrix = estimate_motion(frames[i - 1], frames[i])
            for t in alive:
                t.box = _warp_box(t.box, matrix)
        boxes = [np.array(d.box, dtype=float) for d in dets]
        assigned: dict[int, Track] = {}
        if alive and boxes:
            cost = np.ones((len(alive), len(boxes)))
            for a, t in enumerate(alive):
                for b, box in enumerate(boxes):
                    cost[a, b] = 1.0 - _match_score(t.box, box, width, height, t.last_cut)
            rows, cols = linear_sum_assignment(cost)
            for a, b in zip(rows, cols):
                if 1.0 - cost[a, b] >= MATCH_IOU:
                    assigned[b] = alive[a]
        frame_boxes = []
        matched = set()
        for b, (det, box) in enumerate(zip(dets, boxes)):
            t = assigned.get(b)
            if t is None:
                t = Track(track_id=len(tracks) + 1, box=box)
                tracks.append(t)
                alive.append(t)
            t.box, t.misses = box, 0
            t.last_cut = _touches_edge(box, width, height)
            t.max_area = max(t.max_area, float((box[2] - box[0]) * (box[3] - box[1])))
            t.edge_only = t.edge_only and t.last_cut
            t.scores.append(det.score_or_one)
            t.times.append(times[i])
            matched.add(t.track_id)
            frame_boxes.append((t.track_id, [int(v) for v in box], None if det.score is None else round(det.score, 3)))
        for t in alive:
            if t.track_id not in matched:
                t.misses += 1
        alive = [t for t in alive if t.misses <= MAX_MISSES]
        per_frame.append(frame_boxes)
    whole = [t.max_area for t in tracks if not t.edge_only]
    typical = float(np.median(whole)) if whole else 0.0
    for t in tracks:
        t.typical_area = typical
    return per_frame, tracks


# ------------------------------------------------------------------ job


def run_video_analysis(analysis_id: str) -> None:
    from .pipeline import Tracer, get_sam, segmenter_name

    with SessionLocal() as db:
        analysis = db.get(Analysis, analysis_id)
        if analysis is None:
            return
        analysis.status, analysis.error = "running", None
        db.commit()
        tracer = Tracer(db, analysis)
        try:
            started = time.monotonic()
            plot = analysis.plot
            data = get_storage().get(analysis.video_key)
            suffix = Path(analysis.video_key).suffix or ".mp4"
            thr = settings.score_threshold
            sam = get_sam()

            step = tracer.start("extract_frames", "Reading the video")
            if not analysis.video_key.endswith(".web.mp4"):
                web = to_web_mp4(data, suffix)
                if web is not None:  # play and analyse the same, browser-friendly file
                    key = str(Path(analysis.video_key).with_suffix("")) + ".web.mp4"
                    get_storage().put(key, web, "video/mp4")
                    analysis.video_key, data, suffix = key, web, ".mp4"
                    db.commit()
            frames, times, duration = read_video(data, suffix)
            h, w = frames[0].shape[:2]
            tracer.done(step, f"{duration:.1f} s video, {len(frames)} frames sampled ({settings.video_fps:g} per second)")

            # choose the phrase on the middle frame: crop name, then the plain "plant"
            middle = _jpeg(frames[len(frames) // 2])
            prompt = None
            for candidate in dict.fromkeys([crop_prompt(plot.crop), FALLBACK_PROMPT]):
                s = tracer.start("run_sam", f"Finding {crop_label(plot.crop).lower()} plants on the middle frame", input=candidate)
                seg = sam.segment(middle, candidate)
                scores = [i.score_or_one for i in seg.instances]
                if is_confident(scores, thr):
                    tracer.done(s, f"{len(seg.instances)} masks: confident, using it")
                    prompt = candidate
                    break
                tracer.done(s, f"{len(seg.instances)} masks: weak, trying the next word")
            prompt = prompt or FALLBACK_PROMPT

            step = tracer.start("run_sam", f"Finding plants on all {len(frames)} frames", input=prompt)
            jpegs = [_jpeg(f) for f in frames]
            with ThreadPoolExecutor(max_workers=SAM_WORKERS) as pool:
                segs = list(pool.map(lambda j: sam.segment(j, prompt), jpegs))
            detections = [clean_instances(s.instances, h * w, thr) for s in segs]
            per_frame_max = max((len(d) for d in detections), default=0)
            tracer.done(step, f"{sum(len(d) for d in detections)} plant masks over {len(frames)} frames (at most {per_frame_max} in one frame)")

            step = tracer.start("track_plants", "Following each plant from frame to frame")
            boxes, tracks = track(frames, times, detections)
            counted = [t for t in tracks if t.counted()]
            tracer.done(step, f"{len(tracks)} plant ids, {len(counted)} counted (seen twice, or once with high confidence)")

            context = [
                ContextItem(
                    metric="row_plant_count",
                    status="info",
                    text=f"{len(counted)} {crop_label(plot.crop).lower()} plants counted along this row, each once.",
                )
            ]
            if duration < 5:
                context.append(
                    ContextItem(
                        metric="video",
                        status="attention",
                        badge="Short video",
                        text="The video is short; walk the whole row slowly (about 15 seconds) so every plant is seen.",
                    )
                )
            if per_frame_max >= 14:
                context.append(
                    ContextItem(
                        metric="video",
                        status="attention",
                        badge="Crowded frames",
                        text="Many plants were in view at once; hold the phone lower so 5-12 plants are in view.",
                    )
                )
            n_calls = len(frames) + len(
                [s for s in tracer.steps if s["tool"] == "run_sam" and "middle frame" in s["label"]]
            )
            result = VideoResult(
                analysis_id=analysis.id,
                plot_id=plot.id,
                captured_at=analysis.captured_at,
                segmenter=segmenter_name(),
                prompt=prompt,
                width=w,
                height=h,
                duration_s=round(duration, 2),
                sampled_fps=settings.video_fps,
                row_plant_count=len(counted),
                max_per_frame=per_frame_max,
                frames=[
                    VideoFrame(t=times[i], boxes=[VideoBox(track_id=tid, box=box, score=sc) for tid, box, sc in boxes[i]])
                    for i in range(len(frames))
                ],
                tracks=[
                    VideoTrack(
                        track_id=t.track_id,
                        frames=len(t.times),
                        first_t=t.times[0],
                        last_t=t.times[-1],
                        mean_score=round(float(np.mean(t.scores)), 3) if t.scores else None,
                        counted=t.counted(),
                    )
                    for t in tracks
                ],
                how=(
                    f"SAM 3.1 found '{prompt}' on {len(frames)} frames. Each plant's box is moved with the camera "
                    "motion and matched to the next frame's masks, so a plant keeps one id. Ids seen in at least "
                    f"2 frames (or once with confidence ≥ {SINGLE_FRAME_SCORE}) are counted."
                ),
                context=context,
                run_stats={
                    "sam_calls": n_calls,
                    "sam_cost_usd": sam_cost(n_calls),
                    "wall_time_s": round(time.monotonic() - started, 2),
                },
                agent_trace=[TraceStep(**s) for s in tracer.steps],
            )
            analysis.result = result.model_dump(mode="json")
            analysis.status = "done"
        except Exception as exc:
            log.exception("video analysis %s failed", analysis_id)
            tracer.fail_running(str(exc))
            analysis.status, analysis.error = "failed", f"{type(exc).__name__}: {exc}"
        db.commit()
