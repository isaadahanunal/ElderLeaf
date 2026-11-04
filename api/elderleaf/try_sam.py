"""Try SAM 3.1 prompts on any photo and save a picture of what each call returned.

    cd api
    uv run python -m elderleaf.try_sam ../photo.jpg "lettuce plant" "weed" "white paper sheet"

Writes one image per prompt plus an all-in-one sheet to ./sam_outputs (change with --out).
Answers are cached, so re-running the same photo + prompt is free.
"""

from __future__ import annotations

import argparse
import io
import re
from pathlib import Path

import numpy as np
from PIL import Image

from .config import settings
from .pipeline import prepare_upload
from .render import render_segmentation, side_by_side, to_jpeg
from .sam import PRICE_PER_IMAGE_USD, SamClient


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("prompts", nargs="+")
    ap.add_argument("--out", default="sam_outputs")
    ap.add_argument("--threshold", type=float, default=settings.score_threshold)
    ap.add_argument("--max-side", type=int, default=settings.analysis_max_side, help="same downscale as the app")
    args = ap.parse_args()

    # same preprocessing as an upload to the app (EXIF rotation, downscale, JPEG)
    jpeg, _, _ = prepare_upload(Path(args.image).read_bytes(), args.max_side)
    rgb = np.array(Image.open(io.BytesIO(jpeg)).convert("RGB"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(args.image).stem
    client = SamClient()

    panels, paid = [], 0
    for prompt in args.prompts:
        seg = client.segment(jpeg, prompt)
        paid += not seg.meta.get("cached")
        panel = render_segmentation(rgb, seg.instances, prompt=prompt, threshold=args.threshold)
        path = out / f"{stem}__{re.sub(r'[^a-z0-9]+', '-', prompt.lower()).strip('-')}.jpg"
        path.write_bytes(to_jpeg(panel))
        panels.append(panel)
        scores = [i.score_or_one for i in seg.instances]
        kept = sum(s >= args.threshold for s in scores)
        timing = "cached" if seg.meta.get("cached") else f"{seg.meta.get('latency_s', 0):.1f}s"
        mean = f"{np.mean(scores):.2f}" if scores else "-"
        print(f"{prompt!r:28s} {len(scores):3d} masks, {kept:3d} >= {args.threshold:g}, mean conf {mean}, {timing} -> {path}")
    if len(panels) > 1:
        sheet = out / f"{stem}__all.jpg"
        sheet.write_bytes(to_jpeg(side_by_side(*panels)))
        print(f"all prompts side by side -> {sheet}")
    print(f"new SAM calls: {paid} (~${paid * PRICE_PER_IMAGE_USD:.4f})")


if __name__ == "__main__":
    main()
