"""Crop facts the report agent may quote, and the FAO-56 water-need arithmetic.

Numbers come from crop_agronomy.json (FAO-56 Tables 11 and 12, source noted there). The report
agent may only repeat them, never make up its own.

Water need (FAO-56 single crop coefficient): ETc = Kc x ET0, in mm/day = L/m2/day.
- Kc for the day: FAO-56 crop curve (Kc ini during the initial stage, rising to Kc mid over the
  development stage, Kc mid, then easing to Kc end over the late stage).
- Adjusted by the measured crop cover, as the plan asks: a sparse crop transpires less, so Kc is
  capped at Kc ini + (Kc mid - Kc ini) x min(1, 2 x cover). This follows FAO-56's ground-cover
  coefficient (eq. 98, with M_L = 2 and without the plant-height term): from 50% cover the crop
  counts as full. Cover comes from the photo, so it is only as representative as the photo.
- Rain is reported next to the need, not subtracted (effective rainfall needs soil data).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA: dict = json.loads((Path(__file__).parent / "crop_agronomy.json").read_text())
SOURCE: str = DATA["_source"]
STAGES = ("initial", "development", "mid-season", "late season")
FULL_COVER_FACTOR = 2.0  # M_L in FAO-56 eq. 98: crop counts as full once cover reaches 1 / M_L


@dataclass
class CropInfo:
    crop: str
    kc_ini: float
    kc_mid: float
    kc_end: float
    stages_days: list[int] | None  # initial, development, mid-season, late
    stages_note: str
    day: int | None  # days after planting
    stage: str | None  # None when the planting date or the stage lengths are unknown
    stage_start: int | None  # first day of that stage
    stage_end: int | None  # last day of that stage
    kc_stage: float | None  # Kc of the day from the crop curve
    source: str = SOURCE

    def facts(self) -> dict:
        """What the report agent sees (every number here may appear in its text)."""
        out: dict = {"kc": {"initial": self.kc_ini, "mid_season": self.kc_mid, "end": self.kc_end}, "source": "FAO-56"}
        if self.stages_days:
            out["stage_lengths_days"] = dict(zip(("initial", "development", "mid_season", "late"), self.stages_days))
            out["stage_lengths_note"] = self.stages_note
        if self.stage:
            out["stage_today"] = {"name": self.stage, "from_day": self.stage_start, "to_day": self.stage_end}
            if self.stage_end is not None and self.day is not None and self.day > self.stage_end:
                out["stage_today"]["past_typical_season"] = True
        return out


def crop_info(crop_id: str, days_after_planting: int | None) -> CropInfo | None:
    entry = DATA.get(crop_id)
    if not entry or crop_id.startswith("_"):
        return None
    kc = entry["kc"]
    stages = entry.get("stages_days")
    stage = start = end = kc_day = None
    if stages and days_after_planting is not None and days_after_planting >= 0:
        stage, start, end, kc_day = _stage_and_kc(days_after_planting, stages, kc["ini"], kc["mid"], kc["end"])
    return CropInfo(
        crop_id, kc["ini"], kc["mid"], kc["end"], stages, entry.get("stages_note", ""), days_after_planting, stage, start, end, kc_day
    )


def _stage_and_kc(day: int, stages: list[int], ini: float, mid: float, end: float) -> tuple[str, int, int, float]:
    """FAO-56 crop curve (Fig. 34): flat, rising, flat, falling; after the season Kc stays at Kc end."""
    bounds, first = [], 0
    for length in stages:
        bounds.append((first, first + length - 1))
        first += length
    for i, (a, b) in enumerate(bounds):
        if day <= b:
            frac = (day - a) / max(b - a, 1)
            kc = (ini, ini + frac * (mid - ini), mid, mid + frac * (end - mid))[i]
            return STAGES[i], a, b, round(kc, 2)
    a, b = bounds[-1]
    return STAGES[-1], a, b, end


def water_need(info: CropInfo | None, canopy_pct: float | None, et0_mm: float, area_m2: float | None) -> dict:
    """FAO-56 ETc for one day. Without crop data Kc is unknown and so is the need."""
    if info is None:
        raise ValueError("no crop coefficients for this crop")
    cover = max(0.0, (canopy_pct or 0.0) / 100.0)
    kc_cover = info.kc_ini + (info.kc_mid - info.kc_ini) * min(1.0, FULL_COVER_FACTOR * cover)
    kc = min(info.kc_stage, kc_cover) if info.kc_stage is not None else kc_cover
    kc = round(kc, 2)
    liters_per_m2 = round(kc * et0_mm, 1)
    total = round(liters_per_m2 * area_m2) if area_m2 else None
    stage_part = f"{info.stage} stage Kc {info.kc_stage}" if info.kc_stage is not None else "growth stage unknown"
    how = (
        f"FAO-56: water need = Kc x ET0 = {kc} x {et0_mm} mm = {liters_per_m2} L/m2 for the day. "
        f"Kc: {stage_part}, capped by the crop cover measured in the photo ({canopy_pct}%)."
        + (f" Plot total = {liters_per_m2} L/m2 x {area_m2} m2." if total is not None else "")
        + " Rain is not subtracted."
    )
    return {"kc": kc, "kc_stage": info.kc_stage, "stage": info.stage, "liters_per_m2": liters_per_m2, "plot_total_liters": total, "how": how}
