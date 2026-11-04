"""Offline development segmenter. NOT SAM 3.1.

`SAM_BACKEND=offline` swaps SAM for a color rule (Excess Green index + connected components) so
the app runs end to end without an API key or credits while building the UI. Every result made
with it carries `segmenter = "offline dev segmenter (not SAM)"` and the UI shows that label.
Production and the demo workspace use SAM 3.1.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from .sam import Instance, SamClient, Segmentation


class OfflineSegmenter(SamClient):
    display_name = "offline dev segmenter (not SAM)"

    def __init__(self) -> None:
        super().__init__(api_key="unused")

    def segment(self, image, prompt, *, max_side=None, parse=True, offline=False) -> Segmentation:
        if isinstance(image, (bytes, bytearray)):
            pil = Image.open(io.BytesIO(image))
        elif isinstance(image, Image.Image):
            pil = image
        else:
            pil = Image.open(image)
        rgb = np.asarray(pil.convert("RGB")).astype(np.float32)
        h, w = rgb.shape[:2]
        p = prompt.lower()
        if "paper" in p or "sheet" in p:
            hsv = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2HSV)
            mask = (hsv[..., 2] > 200) & (hsv[..., 1] < 40)
            kind = "paper"
        elif "spot" in p or "lesion" in p:
            return Segmentation(prompt, w, h, [], raw_text="", meta={"cached": False, "offline": True})
        else:
            total = rgb.sum(axis=-1) + 1e-6
            r, g, b = (rgb[..., i] / total for i in range(3))
            exg = (2 * g - r - b) * 255
            exg8 = np.clip(exg, 0, 255).astype(np.uint8)
            thr, _ = cv2.threshold(exg8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            mask = exg8 > max(thr, 20)
            kind = "weed" if "weed" in p or "grass" in p else "crop"
        mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        comps = [(k, *map(int, stats[k])) for k in range(1, n)]
        min_area = max(20, int(h * w * 0.0002))
        comps = [c for c in comps if c[5] >= min_area]
        big = max((c[5] for c in comps), default=0)
        instances = []
        for k, x, y, bw, bh, area in comps:
            if kind == "paper":
                if area < h * w * 0.005:
                    continue
                score = 0.9
            elif kind == "crop":
                if area < 0.2 * big:
                    continue
                score = 0.8
            else:
                if area >= 0.2 * big:
                    continue
                score = 0.7
            instances.append(Instance(str(k), score, (x, y, x + bw, y + bh), labels[y : y + bh, x : x + bw] == k))
        return Segmentation(prompt, w, h, instances, raw_text="", meta={"cached": False, "offline": True})
