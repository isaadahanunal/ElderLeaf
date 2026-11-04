"""Draw SAM masks on photos so people can inspect them (eval gallery, debug endpoints, CLI)."""

from __future__ import annotations

import colorsys

import cv2
import numpy as np

from .sam import Instance

CLASS_COLORS = {"crop": (40, 200, 60), "weed": (255, 0, 200), "lesion": (255, 210, 0), "scale": (0, 190, 255)}
GRAY = (175, 175, 175)
GREEN, RED, YELLOW = (30, 210, 60), (240, 40, 40), (255, 225, 0)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def distinct_colors(n: int) -> list[tuple[int, int, int]]:
    golden = 0.618033988749895
    return [tuple(int(c * 255) for c in colorsys.hsv_to_rgb((0.1 + i * golden) % 1.0, 0.8, 1.0)) for i in range(n)]


def _contours(inst: Instance) -> list[np.ndarray]:
    contours, _ = cv2.findContours(inst.mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    offset = np.array([[inst.box[0], inst.box[1]]])
    return [c + offset for c in contours]


def _fill(canvas: np.ndarray, base: np.ndarray, inst: Instance, color, alpha: float = 0.5) -> None:
    x0, y0, x1, y1 = inst.box
    region, src = canvas[y0:y1, x0:x1], base[y0:y1, x0:x1]
    region[inst.mask] = (src[inst.mask] * (1 - alpha) + np.array(color) * alpha).astype(np.uint8)


def _centroid(inst: Instance) -> tuple[float, float]:
    ys, xs = np.nonzero(inst.mask)
    return inst.box[0] + float(xs.mean()), inst.box[1] + float(ys.mean())


def _shrink(img: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    h, w = img.shape[:2]
    s = min(1.0, max_side / max(h, w))
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return img, s


def _thickness(shape: tuple[int, ...], max_side: int, px: float = 2.0) -> int:
    return max(1, round(px * max(shape[:2]) / max_side))


def _label(img: np.ndarray, x: float, y: float, text: str, color) -> None:
    (tw, th), base = cv2.getTextSize(text, FONT, 0.38, 1)
    h, w = img.shape[:2]
    x = int(np.clip(x - tw / 2, 1, max(w - tw - 1, 1)))
    y = int(np.clip(y + th / 2, th + 2, h - base - 1))
    cv2.rectangle(img, (x - 2, y - th - 2), (x + tw + 2, y + base), (0, 0, 0), -1)
    cv2.putText(img, text, (x, y), FONT, 0.38, color, 1, cv2.LINE_AA)


def title_bar(width: int, lines: list[str]) -> np.ndarray:
    bar = np.full((10 + 22 * len(lines), width, 3), 255, np.uint8)
    for k, line in enumerate(lines):
        cv2.putText(bar, line, (8, 24 + 22 * k), FONT, 0.55 if k == 0 else 0.45, (0, 0, 0) if k == 0 else (70, 70, 70), 1, cv2.LINE_AA)
    return bar


def side_by_side(*panels: np.ndarray, gap: int = 8) -> np.ndarray:
    height = max(p.shape[0] for p in panels)
    padded = [np.pad(p, ((0, height - p.shape[0]), (0, 0), (0, 0)), constant_values=255) for p in panels]
    spacer = np.full((height, gap, 3), 255, np.uint8)
    out = [padded[0]]
    for p in padded[1:]:
        out += [spacer, p]
    return np.concatenate(out, axis=1)


def render_segmentation(
    rgb: np.ndarray, instances: list[Instance], *, prompt: str, threshold: float, max_side: int = 768
) -> np.ndarray:
    """One SAM call: each kept mask in its own color with 'number confidence'; dropped masks in gray."""
    canvas = rgb.copy()
    kept = [i for i in instances if i.score_or_one >= threshold]
    dropped = [i for i in instances if i.score_or_one < threshold]
    colors = distinct_colors(len(kept))
    thick = _thickness(rgb.shape, max_side)
    for inst in dropped:
        cv2.drawContours(canvas, _contours(inst), -1, GRAY, thick, cv2.LINE_AA)
    for inst, color in zip(kept, colors):
        _fill(canvas, rgb, inst, color)
        cv2.drawContours(canvas, _contours(inst), -1, color, thick, cv2.LINE_AA)
    small, s = _shrink(canvas, max_side)
    for k, (inst, color) in enumerate(zip(kept, colors), start=1):
        cx, cy = _centroid(inst)
        _label(small, cx * s, cy * s, f"{k} {inst.score_or_one:.2f}", color)
    mean = np.mean([i.score_or_one for i in instances]) if instances else 0.0
    lines = [
        f'SAM 3.1: "{prompt}"',
        f"{len(kept)} masks >= {threshold:g} (colored), {len(dropped)} below (gray), mean confidence {mean:.2f}",
    ]
    return np.concatenate([title_bar(small.shape[1], lines), small], axis=0)


def render_comparison(
    rgb: np.ndarray,
    instances: list[Instance],
    keep: list[bool],
    matched_preds: set[int],
    gt_labels: np.ndarray,
    missed_gt: list[int],
    *,
    max_side: int = 768,
) -> np.ndarray:
    """SAM vs ground truth: green = matched a real object, red = false alarm, yellow = missed object."""
    canvas = rgb.copy()
    thick = _thickness(rgb.shape, max_side)
    for i, inst in enumerate(instances):
        if not keep[i]:
            cv2.drawContours(canvas, _contours(inst), -1, GRAY, thick, cv2.LINE_AA)
            continue
        color = GREEN if i in matched_preds else RED
        _fill(canvas, rgb, inst, color, alpha=0.45)
        cv2.drawContours(canvas, _contours(inst), -1, color, thick, cv2.LINE_AA)
    for gt_id in missed_gt:
        contours, _ = cv2.findContours((gt_labels == gt_id).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(canvas, contours, -1, YELLOW, thick + 1, cv2.LINE_AA)
    small, _ = _shrink(canvas, max_side)
    n_fp = sum(1 for i, k in enumerate(keep) if k and i not in matched_preds)
    lines = [
        "vs ground truth",
        f"{len(matched_preds)} correct (green), {n_fp} false alarms (red), {len(missed_gt)} missed (yellow)",
    ]
    return np.concatenate([title_bar(small.shape[1], lines), small], axis=0)


def render_analysis(rgb: np.ndarray, result: dict, *, max_side: int = 1024) -> np.ndarray:
    """Final kept masks of an analysis, colored by class, with mask ids."""
    overlay = rgb.copy()
    by_class: dict[str, list[np.ndarray]] = {}
    for m in result["masks"]:
        polys = [np.array(p, np.int32).reshape(-1, 1, 2) for p in m["polygons"]]
        by_class.setdefault(m["class"], []).extend(polys)
        cv2.fillPoly(overlay, polys, CLASS_COLORS[m["class"]])
    canvas = cv2.addWeighted(overlay, 0.45, rgb, 0.55, 0)
    thick = _thickness(rgb.shape, max_side)
    for cls, polys in by_class.items():
        cv2.polylines(canvas, polys, True, CLASS_COLORS[cls], thick, cv2.LINE_AA)
    small, s = _shrink(canvas, max_side)
    for m in result["masks"]:
        x0, y0, x1, y1 = m["box"]
        _label(small, (x0 + x1) / 2 * s, (y0 + y1) / 2 * s, m["id"], CLASS_COLORS[m["class"]])
    metrics = result["metrics"]
    counts = {cls: sum(1 for m in result["masks"] if m["class"] == cls) for cls in CLASS_COLORS}
    lines = [
        f"{counts['crop']} crop (green), {counts['weed']} weed (magenta), "
        f"{counts['lesion']} spots (yellow), {'A4 found (blue)' if counts['scale'] else 'no A4'}",
        f"crop cover {metrics['canopy_cover_pct']['value']}%, weed share {metrics['weed_share_pct']['value']}%, "
        f"photo quality {result['image_quality']['level']}",
    ]
    return np.concatenate([title_bar(small.shape[1], lines), small], axis=0)


def to_png(rgb: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return buf.tobytes()


def to_jpeg(rgb: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()
