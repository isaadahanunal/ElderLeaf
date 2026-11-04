"""Offline tests for SAM output parsing (no API key needed).

Fake responses are built with meta-sam-parser's own one_bit encoder.
"""

import numpy as np
from meta_sam_parser._mask_codec import _encode_raster

from elderleaf.masks import class_map, clean_instances, resolve_cross_class
from elderleaf.sam import parse_output


def _record(oid: int, mask: np.ndarray, x0: int, y0: int, w: int, h: int, conf: float) -> str:
    mh, mw = mask.shape
    payload = _encode_raster(mask.astype(np.uint8).ravel().tolist(), mw, mh)
    x1, y1 = x0 + mw - 1, y0 + mh - 1  # API boxes are inclusive
    return (
        f"{oid}<|box;x1={x0};y1={y0};x2={x1};y2={y1};w={w};h={h};c={conf}|>"
        f"<|mask;x=0;y=0;c={conf};data={mh},{mw},{payload}|>"
    )


def _disk(h: int, w: int) -> np.ndarray:
    yy, xx = np.mgrid[:h, :w]
    return ((yy - h / 2) ** 2 / (h / 2) ** 2 + (xx - w / 2) ** 2 / (w / 2) ** 2) <= 1


def test_parse_places_masks_in_frame():
    W, H = 200, 120
    a, b = _disk(20, 30), _disk(10, 10)
    text = "<0f>" + _record(0, a, 5, 7, W, H, 0.9) + "," + _record(3, b, 150, 100, W, H, 0.4)
    instances, diagnostics = parse_output(text, W, H)
    assert diagnostics == []
    assert [i.id for i in instances] == ["0", "3"]
    first = instances[0]
    assert first.box == (5, 7, 35, 27)
    assert first.score == 0.9
    assert first.area == int(a.sum())
    full = first.full_mask(H, W)
    assert full.sum() == a.sum() and full[7:27, 5:35].sum() == a.sum()


def test_empty_output_is_zero_matches():
    instances, diagnostics = parse_output("", 100, 100)
    assert instances == [] and diagnostics == []


def test_cleanup_and_cross_class():
    W, H = 100, 100
    m = _disk(20, 20)
    crop, _ = parse_output("<0f>" + _record(0, m, 10, 10, W, H, 0.8), W, H)
    weed, _ = parse_output("<0f>" + _record(0, m, 10, 10, W, H, 0.6) + "," + _record(1, _disk(4, 4), 60, 60, W, H, 0.9), W, H)
    # tiny 4x4 weed is below 0.2% of the image
    assert len(clean_instances(weed, W * H, score_threshold=0.5, min_area_frac=0.002)) == 1
    resolved = resolve_cross_class({"crop": crop, "weed": weed})
    assert len(resolved["crop"]) == 1 and len(resolved["weed"]) == 1  # duplicate weed dropped
    labels = class_map({1: crop, 2: weed}, H, W)
    assert (labels == 1).sum() == m.sum()  # crop wins the overlap (0.8 > 0.6)
