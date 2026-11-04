"""Every number ElderLeaf shows is computed here from SAM masks. The LLM never produces numbers."""

from __future__ import annotations

import cv2
import numpy as np

from .masks import class_map
from .sam import Instance

A4_AREA_CM2 = 21.0 * 29.7  # 623.7 cm²

# Photo-quality checks, measured on a 1024 px long side.
# Sharpness = variance of the Laplacian (how strong the pixel-to-pixel edges are).
#   120 PhenoBench photos (stored as JPEG): min 215, median ~6000. Blurred copies: 2-18.
# Exposure: mean gray level plus the share of burned-out pixels.
#   Real photos: <= 1% of pixels have a channel at 255; an overexposed copy: 56%; an A4 sheet ~6%.
BLUR_MIN = 80.0
BRIGHTNESS_RANGE = (50.0, 210.0)
CLIPPED_MAX = 0.20


def image_quality(rgb: np.ndarray) -> dict:
    h, w = rgb.shape[:2]
    scale = 1024 / max(h, w)
    if scale < 1:
        rgb = cv2.resize(rgb, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    highlights = float((rgb >= 250).any(axis=-1).mean())  # any channel burned out
    shadows = float((rgb <= 5).all(axis=-1).mean())  # pure black
    sharp = blur >= BLUR_MIN
    too_dark = brightness < BRIGHTNESS_RANGE[0] or shadows > CLIPPED_MAX
    too_bright = brightness > BRIGHTNESS_RANGE[1] or highlights > CLIPPED_MAX
    return {
        "blur": round(blur, 1),
        "brightness": round(brightness, 1),
        "clipped_pct": round(100 * (highlights + shadows), 1),
        "sharp": sharp,
        "exposure": "too_dark" if too_dark else ("too_bright" if too_bright else "ok"),
        "exposure_ok": not (too_dark or too_bright),
        "level": "good" if sharp and not (too_dark or too_bright) else "low",
    }


def find_scale(paper: list[Instance], min_score: float = 0.6) -> tuple[Instance | None, float | None, str]:
    """Best 'white paper sheet' mask that looks like a flat A4 sheet -> pixels per cm²."""
    for inst in sorted(paper, key=lambda i: i.score_or_one, reverse=True):
        if inst.score_or_one < min_score:
            break
        contours, _ = cv2.findContours(inst.mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        _, (rw, rh), _ = cv2.minAreaRect(max(contours, key=cv2.contourArea))
        if min(rw, rh) == 0:
            continue
        fill = inst.area / (rw * rh)
        aspect = max(rw, rh) / min(rw, rh)
        if fill >= 0.85 and 1.15 <= aspect <= 1.75:  # A4 is 1.414; allow some perspective
            return inst, inst.area / A4_AREA_CM2, f"A4 sheet found ({inst.area} px = 623.7 cm²)."
    if paper:
        return None, None, "Found something paper-like, but not a flat A4 sheet; sizes are in pixels."
    return None, None, "No A4 sheet in the photo; sizes are in pixels."


def compute_metrics(
    crop: list[Instance],
    weed: list[Instance],
    lesion: list[Instance] | None,
    height: int,
    width: int,
    px_per_cm2: float | None,
) -> dict:
    labels = class_map({1: crop, 2: weed}, height, width, priority=[1, 2])  # crop pixels win overlaps
    veg_px = int((labels > 0).sum())
    crop_px = int((labels == 1).sum())
    weed_px = int((labels == 2).sum())

    lesion_share = None
    if lesion is not None:
        lesion_px = class_map({1: lesion}, height, width) > 0
        lesion_share = round(100 * int((lesion_px & (labels == 1)).sum()) / crop_px, 1) if crop_px else 0.0

    mean_area, unit = None, "px"
    if crop:
        mean_px = float(np.mean([c.area for c in crop]))
        mean_area, unit = (mean_px / px_per_cm2, "cm2") if px_per_cm2 else (mean_px, "px")
        mean_area = round(mean_area, 1)

    return {
        "plant_count": len(crop),
        # crop cover only: a weedy plot must not look like a growing crop
        "canopy_cover_pct": round(100 * crop_px / (height * width), 1),
        "weed_share_pct": round(100 * weed_px / veg_px, 1) if veg_px else 0.0,
        "lesion_share_pct": lesion_share,
        "mean_plant_area": mean_area,
        "mean_plant_area_unit": unit,
    }


def mask_polygons(inst: Instance, epsilon: float = 1.0, min_area: float = 4.0) -> list[list[list[int]]]:
    """Outer outlines of a box-local mask, in image coordinates, lightly simplified."""
    contours, _ = cv2.findContours(inst.mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    x0, y0 = inst.box[0], inst.box[1]
    polygons = []
    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            continue
        approx = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
        if len(approx) >= 3:
            polygons.append([[int(x) + x0, int(y) + y0] for x, y in approx])
    return polygons
