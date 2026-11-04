"""Runtime settings, read from the environment (and the nearest .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return default if value in (None, "") else value


def _env_float(name: str) -> float | None:
    value = _env(name)
    return None if value is None else float(value)


@dataclass(frozen=True)
class Settings:
    # Meta Model API
    model_api_key: str | None = _env("MODEL_API_KEY")
    meta_api_base: str = _env("META_API_BASE", "https://api.meta.ai/v1")
    sam_model: str = _env("SAM_MODEL", "sam-3.1")
    sam_cache_dir: str = _env("SAM_CACHE_DIR", ".cache/sam")

    # persistence: SQLite + local files for dev, Supabase Postgres + Storage in prod
    database_url: str = _env("DATABASE_URL", "sqlite:///.data/elderleaf.db")
    storage_backend: str = _env("STORAGE_BACKEND", "local")  # local | supabase
    storage_dir: str = _env("STORAGE_DIR", ".data/files")
    supabase_url: str | None = _env("SUPABASE_URL")
    supabase_service_key: str | None = _env("SUPABASE_SERVICE_KEY")
    supabase_bucket: str = _env("SUPABASE_BUCKET", "images")

    # web
    # the Android app (Capacitor) loads the web app from http://localhost, so it is always allowed
    cors_origins: tuple[str, ...] = tuple(
        dict.fromkeys([o.strip() for o in _env("CORS_ORIGINS", "*").split(",")] + ["http://localhost", "https://localhost"])
    )
    job_mode: str = _env("JOB_MODE", "thread")  # thread | sync (tests)

    # analysis
    analysis_max_side: int = int(_env("ANALYSIS_MAX_SIDE", "1600"))
    score_threshold: float = float(_env("SCORE_THRESHOLD", "0.5"))
    # SAM "leaf spot" search for the lesion share (plan). 0 false spots on 8 healthy PhenoBench photos.
    enable_lesion: bool = _env("ENABLE_LESION", "1") == "1"

    # prompt agent (Muse Spark chooses SAM search words). agent | fixed
    prompt_strategy: str = _env("PROMPT_STRATEGY", "agent")
    # "baseten" = Muse Spark Open (open weights) on Baseten, "meta" = Muse Spark 1.3 on Meta Model API
    baseten_api_key: str | None = _env("BASETEN_API_KEY")
    llm_provider: str = _env("LLM_PROVIDER", "baseten" if _env("BASETEN_API_KEY") else "meta")
    llm_model: str | None = _env("LLM_MODEL")  # default depends on the provider
    llm_reasoning_effort: str | None = _env("LLM_REASONING_EFFORT", "low")
    llm_price_in_per_m: float | None = _env_float("LLM_PRICE_IN_PER_M")  # USD per 1M input tokens
    llm_price_out_per_m: float | None = _env_float("LLM_PRICE_OUT_PER_M")  # USD per 1M output tokens
    llm_cache_dir: str = _env("LLM_CACHE_DIR", ".cache/llm")
    # Muse Spark writes the plain-language summary (checked by the validator). 1 = on
    enable_summary: bool = _env("ENABLE_SUMMARY", "1") == "1"

    # "meta" = SAM 3.1 on Meta Model API. "offline" = color-based dev segmenter, NOT SAM: lets the
    # app run without a key while developing; every result made with it is labelled as such.
    sam_backend: str = _env("SAM_BACKEND", "meta")

    # irrigation (Open-Meteo, no key)
    weather_url: str | None = _env("WEATHER_URL")

    # row video: frames sampled per second, and the most frames sent to SAM per video
    video_fps: float = float(_env("VIDEO_FPS", "2"))
    video_max_frames: int = int(_env("VIDEO_MAX_FRAMES", "40"))
    video_max_side: int = int(_env("VIDEO_MAX_SIDE", "960"))


settings = Settings()
