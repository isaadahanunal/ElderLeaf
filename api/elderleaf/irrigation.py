"""Daily water need with FAO-56: ETc = Kc_adj x ET0.

- ET0 (reference evapotranspiration, mm/day) comes from Open-Meteo for the plot location. It is
  computed there with the FAO-56 Penman-Monteith equation. Free, no key. Cached per place and day.
- Kc comes from the crop library for the growth stage (FAO-56 Tables 11-12).
- Sparse plots use less water than a full canopy, so Kc is scaled down by the measured crop cover
  (FAO-56 eq. 97-98): Kd = min(1, ML * fc, fc ** (1 / (1 + h))), Kc_adj = Kc_min + Kd (Kc - Kc_min).
- 1 mm of water over 1 m² is 1 liter, so ETc in mm is also L/m².

This is the agent's `get_weather` tool plus arithmetic. No LLM is involved.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading

import httpx

from .config import settings
from .crops import KC_MIN, crop_info

log = logging.getLogger("elderleaf.irrigation")

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
ML = 2.0  # FAO-56: multiplier on fc, 1.5-2.0

_cache: dict[tuple, dict] = {}
_lock = threading.Lock()


class WeatherError(RuntimeError):
    pass


def get_weather(lat: float, lon: float, day: dt.date | None = None) -> dict:
    """ET0 and rain for one day at a place (today by default). Open-Meteo keeps ~3 months of past days."""
    day = day or dt.date.today()
    key = (round(lat, 2), round(lon, 2), day.isoformat())
    with _lock:
        if key in _cache:
            return _cache[key]
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "et0_fao_evapotranspiration,precipitation_sum,temperature_2m_max",
        "timezone": "auto",
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
    }
    if (dt.date.today() - day).days > 90:
        raise WeatherError("weather for dates older than 3 months is not available")
    try:
        resp = httpx.get(settings.weather_url or OPEN_METEO, params=params, timeout=15)
        resp.raise_for_status()
        daily = resp.json()["daily"]
        out = {
            "date": day.isoformat(),
            "et0_mm": round(float(daily["et0_fao_evapotranspiration"][0]), 2),
            "rain_mm": round(float(daily["precipitation_sum"][0] or 0.0), 1),
            "tmax_c": None if daily["temperature_2m_max"][0] is None else round(float(daily["temperature_2m_max"][0]), 1),
            "source": "Open-Meteo (FAO-56 Penman-Monteith ET0)",
        }
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise WeatherError(f"weather service unavailable: {exc}") from exc
    with _lock:
        _cache[key] = out
    return out


def cover_adjusted_kc(kc: float, cover_fraction: float | None, height_m: float) -> tuple[float, float]:
    """FAO-56 eq. 97-98 density coefficient. Returns (Kd, Kc_adj)."""
    if cover_fraction is None:
        return 1.0, kc
    fc = min(max(cover_fraction, 0.0), 1.0)
    kd = min(1.0, ML * fc, fc ** (1.0 / (1.0 + height_m))) if fc > 0 else 0.0
    return round(kd, 2), round(KC_MIN + kd * (kc - KC_MIN), 2)


def water_need(
    crop: str,
    days_after_planting: int | None,
    canopy_cover_pct: float | None,
    area_m2: float | None,
    lat: float | None,
    lon: float | None,
    day: dt.date | None = None,
) -> dict:
    """Water need for one day. Always returns a dict; `available` says whether it could be computed."""
    info = crop_info(crop, days_after_planting)
    if info is None:
        return {"available": False, "reason": "Add the crop type and planting date to estimate water need."}
    if lat is None or lon is None:
        return {"available": False, "reason": "Add the plot location to estimate water need."}
    try:
        weather = get_weather(lat, lon, day)
    except WeatherError as exc:
        return {"available": False, "reason": str(exc)}
    cover = None if canopy_cover_pct is None else canopy_cover_pct / 100
    kd, kc_adj = cover_adjusted_kc(info["kc"], cover, info["height_m"])
    etc = round(kc_adj * weather["et0_mm"], 1)
    return {
        "available": True,
        "date": weather["date"],
        "et0_mm": weather["et0_mm"],
        "rain_mm": weather["rain_mm"],
        "tmax_c": weather["tmax_c"],
        "stage": info["stage"],
        "kc": info["kc"],
        "kd": kd,
        "kc_adj": kc_adj,
        "canopy_cover_pct": canopy_cover_pct,
        "liters_per_m2": etc,
        "area_m2": area_m2,
        "plot_total_liters": None if area_m2 is None else round(etc * area_m2),
        "how": (
            f"ET0 {weather['et0_mm']} mm today (Open-Meteo) x crop coefficient {kc_adj} "
            f"(FAO-56 {info['stage']} Kc {info['kc']}, scaled by the measured crop cover) = {etc} mm = {etc} L/m²."
        ),
        "rain_note": (
            f"{weather['rain_mm']} mm of rain is expected today; that counts toward this amount."
            if weather["rain_mm"] >= 1
            else None
        ),
    }
