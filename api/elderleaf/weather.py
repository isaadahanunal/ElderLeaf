"""Daily reference evapotranspiration (ET0) for a place and day, from Open-Meteo (free, no key).

Open-Meteo's `et0_fao_evapotranspiration` is the FAO-56 Penman-Monteith ET0 (mm/day). The forecast
API covers roughly the last 3 months and the next 2 weeks; older days come from the archive API.
Answers are cached on disk (a past day's weather does not change). WEATHER=0 switches it off.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CACHE_DIR = Path(os.environ.get("WEATHER_CACHE_DIR", ".cache/weather"))


class WeatherError(RuntimeError):
    pass


def enabled() -> bool:
    return os.environ.get("WEATHER", "1") != "0"


def daily_et0(lat: float, lon: float, day: dt.date, timeout_s: float = 10.0) -> dict:
    """{"date", "et0_mm", "rain_mm", "source"} or WeatherError."""
    if not enabled():
        raise WeatherError("weather lookups are switched off (WEATHER=0)")
    path = CACHE_DIR / f"{lat:.2f}_{lon:.2f}_{day.isoformat()}.json"
    if path.exists():
        return json.loads(path.read_text())
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "daily": "et0_fao_evapotranspiration,precipitation_sum",
        "timezone": "auto",
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
    }
    errors = []
    for url in (FORECAST_URL, ARCHIVE_URL):
        try:
            resp = httpx.get(url, params=params, timeout=timeout_s)
            if resp.status_code != 200:
                errors.append(f"{url.split('/')[2]}: HTTP {resp.status_code}")
                continue
            daily = resp.json().get("daily") or {}
            et0 = (daily.get("et0_fao_evapotranspiration") or [None])[0]
            if et0 is None:
                errors.append(f"{url.split('/')[2]}: no ET0 for {day}")
                continue
            rain = (daily.get("precipitation_sum") or [None])[0]
            out = {"date": day.isoformat(), "et0_mm": round(float(et0), 1), "rain_mm": None if rain is None else round(float(rain), 1),
                   "source": "Open-Meteo (FAO-56 Penman-Monteith ET0)"}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out))
            return out
        except httpx.HTTPError as exc:
            errors.append(f"{url.split('/')[2]}: {type(exc).__name__}")
    raise WeatherError("; ".join(errors))
