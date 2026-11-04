"""Health signals measured in code inside the crop masks; the report agent only puts them into words.

- yellowing: crop pixels clearly yellower than this photo's own crop: hue at least 10 below the median
  crop hue (OpenCV 0-179 scale), with saturation and brightness >= 60. Relative on purpose: a fixed
  "yellow" hue called 28-53% of healthy PhenoBench beet seedlings yellow (camera white balance).
  On healthy crops this measure stays low: median 0.5% over 39 PhenoBench photos and 3.4% over 39
  CropAndWeed photos, at most 15%, hence the 15% threshold. A whole crop yellowing evenly is not caught.
- browning: brown or dry crop pixels (hue <= 17, saturation >= 60, brightness 30-190). Healthy crops: < 0.2%.
- leaf_spots: SAM "leaf spot" masks on crop plants (only when that search ran).
Masks are eroded by 2 px first, so soil at the mask edge does not count.

Likelihood thresholds (% of crop area) are product rules, not agronomy; a sign is only a possibility.
"""

from __future__ import annotations

import cv2
import numpy as np

from .sam import Instance

YELLOW_HUE_DROP = 10
MIN_PIXELS = 200  # fewer crop pixels than this: too little to judge
PLANT_SHARE = 0.3  # a plant is evidence for a sign when 30% of it shows the sign
LEVELS = {  # % of crop area -> low / medium / high
    "yellowing": (15.0, 25.0, 40.0),
    "browning": (2.0, 5.0, 10.0),
    "leaf_spots": (1.0, 3.0, 10.0),
}
HOW = {
    "yellowing": "Share of crop area clearly yellower than the rest of the crop in this photo (color, measured in code).",
    "browning": "Share of crop area that is brown or dry-looking (color, measured in code).",
    "leaf_spots": "Share of crop area covered by SAM 3.1 masks of spots on the crop plants.",
}
_KERNEL = np.ones((5, 5), np.uint8)


def likelihood(sign: str, share_pct: float) -> str | None:
    low, medium, high = LEVELS[sign]
    if share_pct >= high:
        return "high"
    if share_pct >= medium:
        return "medium"
    if share_pct >= low:
        return "low"
    return None


def measure_color(rgb: np.ndarray, crop: list[Instance], crop_ids: list[str]) -> dict:
    """{"assessed", "crop_px", "yellowing": {"share_pct", "plant_ids"}, "browning": {...}}."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    plants = []
    for inst, mask_id in zip(crop, crop_ids):
        x0, y0, x1, y1 = inst.box
        inner = cv2.erode(inst.mask.astype(np.uint8), _KERNEL) > 0
        if inner.sum() < 20:  # tiny seedling: erosion would remove it
            inner = inst.mask
        plants.append((mask_id, hsv[y0:y1, x0:x1][inner].astype(np.int16)))
    total = sum(len(px) for _, px in plants)
    if total < MIN_PIXELS:
        return {"assessed": False, "crop_px": int(total)}
    reference = float(np.median(np.concatenate([px[:, 0] for _, px in plants])))
    counts = {"yellowing": 0, "browning": 0}
    evidence: dict[str, list[tuple[float, str]]] = {"yellowing": [], "browning": []}
    for mask_id, px in plants:
        hue, sat, val = px[:, 0], px[:, 1], px[:, 2]
        brown = (hue <= 17) & (sat >= 60) & (val >= 30) & (val <= 190)
        yellow = (hue <= reference - YELLOW_HUE_DROP) & ~brown & (sat >= 60) & (val >= 60)
        for sign, flags in (("yellowing", yellow), ("browning", brown)):
            n = int(flags.sum())
            counts[sign] += n
            if len(px) and n / len(px) >= PLANT_SHARE:
                evidence[sign].append((n / len(px), mask_id))
    out: dict = {"assessed": True, "crop_px": int(total), "reference_hue": round(reference, 1)}
    for sign in ("yellowing", "browning"):
        out[sign] = {
            "share_pct": round(100.0 * counts[sign] / total, 1),
            "plant_ids": [mask_id for _, mask_id in sorted(evidence[sign], reverse=True)[:20]],
        }
    return out


def coverage_on_crop(found: list[Instance], crop: list[Instance], height: int, width: int, min_inside: float = 0.5) -> tuple[list[int], float]:
    """Which `found` masks sit on crop plants (>= half inside), and the % of crop area they cover."""
    crop_px = np.zeros((height, width), bool)
    for inst in crop:
        x0, y0, x1, y1 = inst.box
        crop_px[y0:y1, x0:x1] |= inst.mask
    total = int(crop_px.sum())
    if not total:
        return [], 0.0
    kept, covered = [], np.zeros_like(crop_px)
    for i, inst in enumerate(found):
        x0, y0, x1, y1 = inst.box
        inside = crop_px[y0:y1, x0:x1][inst.mask]
        if inside.size and inside.mean() >= min_inside:
            kept.append(i)
            covered[y0:y1, x0:x1] |= inst.mask
    return kept, round(100.0 * float((covered & crop_px).sum()) / total, 1)
