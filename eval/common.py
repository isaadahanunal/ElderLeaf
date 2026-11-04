"""Shared eval settings."""

from __future__ import annotations

import os
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = Path(os.environ.get("ELDERLEAF_EVAL_RESULTS", EVAL_DIR / "results"))
CACHE_DIR = Path(os.environ.get("ELDERLEAF_SAM_CACHE", EVAL_DIR / ".cache" / "sam"))

# prompt text -> what it should find. One prompt = one SAM request per image ($0.0025).
DEFAULT_PROMPTS: dict[str, str] = {
    "crop plant": "crop",  # generic prompt the product uses when crop type is unknown
    "sugar beet plant": "crop",  # crop-specific prompt (the user tells us the crop)
    "weed": "weed",
    "plant": "plant",  # all vegetation (crop + weed), for canopy cover
    "leaf": "leaf",  # crop leaves (PhenoBench labels leaves of crops only)
    "sugar beet leaf": "leaf",  # crop-specific leaf word
}

TARGETS = ("crop", "weed", "plant", "leaf")
IOU_MATCH = 0.5
VIS_BINS = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 0.95), (0.95, 1.01)]
SIZE_BINS = [(0, 200), (200, 2_000), (2_000, 20_000), (20_000, 10**9)]  # px, 1024x1024 images
THRESHOLDS = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def bin_label(value: float, bins: list[tuple[float, float]], fmt: str = "{:g}") -> str:
    for lo, hi in bins:
        if lo <= value < hi:
            hi_txt = "1" if hi > 1 and hi < 2 else ("∞" if hi >= 10**9 else fmt.format(hi))
            return f"{fmt.format(lo)}–{hi_txt}"
    return "other"


def parse_prompt_args(items: list[str] | None) -> dict[str, str]:
    if not items:
        return dict(DEFAULT_PROMPTS)
    prompts = {}
    for item in items:
        text, _, target = item.rpartition("=")
        if not text or target not in TARGETS:
            raise SystemExit(f"--prompt must look like 'text=target' with target in {TARGETS}: {item!r}")
        prompts[text] = target
    return prompts
