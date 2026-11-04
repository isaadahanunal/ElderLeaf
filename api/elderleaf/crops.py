"""Crop library: labels, SAM prompts, FAO-56 growth stages and crop coefficients.

`crop_info(crop, day)` is the agent's `lookup_crop_info` tool: it answers "where should this crop
be on day X?" with numbers taken only from crop_library.json. The agent may quote these numbers,
nothing else (the validator checks)."""

from __future__ import annotations

import json
from pathlib import Path

_RAW: dict = json.loads((Path(__file__).parent / "crop_library.json").read_text())
LIBRARY_NOTE: str = _RAW.pop("_about", "")
CROPS: dict[str, dict] = _RAW
# Last resort for the crop. "crop plant" found nothing on PhenoBench, the plain "plant" does
# (it also catches weeds, so the crop name and the agent's phrases are tried first).
FALLBACK_PROMPT = "plant"

STAGE_NAMES = ("initial", "development", "mid-season", "late-season")
KC_MIN = 0.15  # FAO-56 Kc of bare soil (eq. 98)
COVER_AT_EMERGENCE = 0.03


def crop_label(crop_id: str) -> str:
    return CROPS.get(crop_id, {}).get("label", crop_id.replace("_", " ").title())


def crop_prompt(crop_id: str) -> str:
    return CROPS.get(crop_id, {}).get("sam_prompt", FALLBACK_PROMPT)


def crop_info(crop_id: str, day: int | None) -> dict | None:
    """Growth stage, FAO-56 Kc and the expected crop-cover band on a given day after planting.
    None when the crop has no agronomic data or the planting date is unknown."""
    entry = CROPS.get(crop_id)
    if not entry or "stages" not in entry or day is None or day < 0:
        return None
    ini, dev, mid, late = entry["stages"]
    kc_ini, kc_mid, kc_end = entry["kc"]
    bounds = [0, ini, ini + dev, ini + dev + mid, ini + dev + mid + late]
    stage = next((i for i in range(4) if day < bounds[i + 1]), 3)

    # FAO-56 Fig. 25: Kc is flat in the initial and mid stages, linear in between
    if day < bounds[1]:
        kc = kc_ini
    elif day < bounds[2]:
        kc = kc_ini + (kc_mid - kc_ini) * (day - bounds[1]) / max(dev, 1)
    elif day < bounds[3]:
        kc = kc_mid
    elif day < bounds[4]:
        kc = kc_mid + (kc_end - kc_mid) * (day - bounds[3]) / max(late, 1)
    else:
        kc = kc_end

    # Expected crop cover (ElderLeaf rule of thumb): small during the initial stage, rising
    # linearly through development to cover_max, then flat.
    cmax = entry["cover_max"]
    if day < bounds[1]:
        expected = COVER_AT_EMERGENCE + (0.10 - COVER_AT_EMERGENCE) * day / max(ini, 1)
    elif day < bounds[2]:
        expected = 0.10 + (cmax - 0.10) * (day - bounds[1]) / max(dev, 1)
    else:
        expected = cmax
    low = max(0, round(100 * expected * 0.5))
    high = min(100, round(100 * expected * 1.5 + 5))

    stage_end = bounds[stage + 1]
    return {
        "crop": crop_id,
        "label": entry["label"],
        "day": day,
        "stage": STAGE_NAMES[stage],
        "stage_start_day": bounds[stage],
        "stage_end_day": stage_end,
        "season_days": bounds[4],
        "kc": round(kc, 2),
        "kc_stages": entry["kc"],
        "height_m": entry["height_m"],
        "cover_typical_pct": [low, high],
        "source": "FAO-56 Tables 11-12 (stage lengths, Kc); cover range is an ElderLeaf rule of thumb",
    }
