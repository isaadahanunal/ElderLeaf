"""Mask cleanup: a weed mask lying on a crop plant is a part of that plant, not a weed."""

import numpy as np

from elderleaf.masks import drop_on_top_of, resolve_cross_class
from elderleaf.sam import Instance


def box(name: str, x0: int, y0: int, x1: int, y1: int) -> Instance:
    return Instance(name, 0.9, (x0, y0, x1, y1), np.ones((y1 - y0, x1 - x0), bool))


def test_weed_masks_lying_on_a_crop_plant_are_dropped():
    plant = box("plant", 0, 0, 40, 40)  # 1600 px
    leaf = box("leaf", 5, 5, 20, 15)  # 150 px, all on the plant (like one lettuce leaf found as "grass blade")
    edge = box("edge", 30, 30, 60, 60)  # 900 px, 100 of them on the plant: a real weed touching it
    apart = box("apart", 70, 70, 80, 80)  # off the plant
    # IoU alone keeps the leaf: it is a small part of the plant's mask (IoU 0.09)
    kept = resolve_cross_class({"crop": [plant], "weed": [leaf, edge, apart]}, priority=["crop", "weed"])["weed"]
    assert [i.id for i in kept] == ["leaf", "edge", "apart"]
    assert [i.id for i in drop_on_top_of(kept, [plant], 100, 100)] == ["edge", "apart"]
    assert drop_on_top_of([leaf], [], 100, 100) == [leaf]
