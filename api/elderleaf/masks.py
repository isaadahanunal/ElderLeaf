"""Mask cleanup used before any metric is computed (product and eval share this)."""

from __future__ import annotations

import numpy as np

from .sam import Instance

DEFAULT_SCORE_THRESHOLD = 0.5
DEFAULT_MIN_AREA_FRAC = 0.0002  # drop masks smaller than 0.02% of the image


def clean_instances(
    instances: list[Instance],
    image_area: int,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    min_area_frac: float = DEFAULT_MIN_AREA_FRAC,
) -> list[Instance]:
    min_area = min_area_frac * image_area
    return [
        inst
        for inst in instances
        if inst.score_or_one >= score_threshold and inst.area >= min_area
    ]


def _boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def instance_iou(a: Instance, b: Instance) -> float:
    if not _boxes_overlap(a.box, b.box):
        return 0.0
    x0, y0 = min(a.box[0], b.box[0]), min(a.box[1], b.box[1])
    x1, y1 = max(a.box[2], b.box[2]), max(a.box[3], b.box[3])
    canvas_a = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    canvas_b = np.zeros_like(canvas_a)
    canvas_a[a.box[1] - y0 : a.box[3] - y0, a.box[0] - x0 : a.box[2] - x0] = a.mask
    canvas_b[b.box[1] - y0 : b.box[3] - y0, b.box[0] - x0 : b.box[2] - x0] = b.mask
    inter = np.logical_and(canvas_a, canvas_b).sum()
    union = np.logical_or(canvas_a, canvas_b).sum()
    return float(inter / union) if union else 0.0


def resolve_cross_class(
    by_class: dict[str, list[Instance]], iou_threshold: float = 0.5, priority: list[str] | None = None
) -> dict[str, list[Instance]]:
    """When the same object was found under two classes (e.g. crop and weed), keep it under one.

    priority=None: the higher-scoring mask wins.
    priority=["crop", "weed"]: the earlier class always wins (the grower told us the crop; a weed
    phrase like "grass seedling" also matching the crop seedlings must not turn crops into weeds).
    """
    rank = {cls: i for i, cls in enumerate(priority or [])}
    tagged = [(cls, inst) for cls, insts in by_class.items() for inst in insts]
    tagged.sort(key=lambda t: (-rank.get(t[0], len(rank)), t[1].score_or_one), reverse=True)
    kept: list[tuple[str, Instance]] = []
    for cls, inst in tagged:
        if any(
            other_cls != cls and instance_iou(inst, other) >= iou_threshold
            for other_cls, other in kept
        ):
            continue
        kept.append((cls, inst))
    out: dict[str, list[Instance]] = {cls: [] for cls in by_class}
    for cls, inst in kept:
        out[cls].append(inst)
    return out


def class_map(
    by_class: dict[int, list[Instance]], height: int, width: int, priority: list[int] | None = None
) -> np.ndarray:
    """Pixel label map (0 = background). Where masks overlap, the higher score wins,
    or with `priority` (e.g. [1, 2]) the earlier label always wins."""
    labels = np.zeros((height, width), dtype=np.uint8)
    if priority:
        for label in reversed(priority):  # paint low priority first, high priority on top
            for inst in by_class.get(label, []):
                x0, y0, x1, y1 = inst.box
                labels[y0:y1, x0:x1][inst.mask] = label
        return labels
    best = np.full((height, width), -1.0, dtype=np.float32)
    for label, insts in by_class.items():
        for inst in insts:
            x0, y0, x1, y1 = inst.box
            score = inst.score_or_one
            region_best = best[y0:y1, x0:x1]
            region_labels = labels[y0:y1, x0:x1]
            take = inst.mask & (score > region_best)
            region_best[take] = score
            region_labels[take] = label
    return labels
