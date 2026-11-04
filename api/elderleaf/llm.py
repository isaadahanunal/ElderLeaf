"""Muse Spark client (OpenAI-style chat completions, text + images) for two providers:

- "baseten": Muse Spark Open (open weights) on Baseten, model meta-models/muse-spark-open-1026
- "meta":    Muse Spark 1.3 on Meta Model API

Both always reason before answering; reasoning tokens are billed as output tokens.
Answers are cached on disk by request body, so eval re-runs cost nothing.
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import settings

BASETEN_HACKATHON_MODEL = "meta-models/muse-spark-open-1026"

# Prices in USD per 1M tokens: input / cached input / output (reasoning counts as output).
PROVIDERS: dict[str, dict] = {
    "meta": {
        "base_url": "https://api.meta.ai/v1",
        "model": "muse-spark-1.3",
        "key": "model_api_key",
        "price_in": 1.25,  # dev.meta.ai pricing, standard mode
        "price_cached": 0.15,
        "price_out": 4.25,
    },
    "baseten": {
        "base_url": "https://inference.baseten.co/v1",
        # Organizers: "Use exactly meta-models/muse-spark-open-1026. Your key only works with this model."
        "model": BASETEN_HACKATHON_MODEL,
        "key": "baseten_api_key",
        "price_in": 1.25,  # hackathon pricing for Muse Spark Open on Baseten
        "price_cached": 0.15,
        "price_out": 4.25,
    },
}


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int  # all input tokens, including the cached ones
    output_tokens: int  # includes reasoning tokens
    reasoning_tokens: int
    latency_s: float
    cost_usd: float | None
    cached: bool  # answer came from our disk cache (no new call)
    cached_input_tokens: int = 0  # provider-side prompt cache hits (cheaper)


def image_part(jpeg: bytes) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}}


def _content_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


class LLMClient:
    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        cache_dir: str | Path | None = None,
        reasoning_effort: str | None = None,
        timeout_s: float = 180.0,
        max_retries: int = 4,
    ) -> None:
        self.provider = provider or settings.llm_provider
        if self.provider not in PROVIDERS:
            raise ValueError(f"Unknown LLM provider {self.provider!r}; use one of {sorted(PROVIDERS)}")
        cfg = PROVIDERS[self.provider]
        self.base_url = cfg["base_url"]
        self.model = model or settings.llm_model or cfg["model"]
        if self.provider == "baseten" and self.model != BASETEN_HACKATHON_MODEL:
            raise ValueError(f"Baseten hackathon keys only work with {BASETEN_HACKATHON_MODEL!r}, not {self.model!r}.")
        self.api_key = api_key or getattr(settings, cfg["key"])
        self.price_in = settings.llm_price_in_per_m if settings.llm_price_in_per_m is not None else cfg["price_in"]
        self.price_out = settings.llm_price_out_per_m if settings.llm_price_out_per_m is not None else cfg["price_out"]
        self.price_cached = cfg.get("price_cached", self.price_in)
        self.reasoning_effort = reasoning_effort or settings.llm_reasoning_effort
        self.cache_dir = Path(cache_dir or settings.llm_cache_dir)
        self.timeout_s = timeout_s
        self.max_retries = max_retries

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def cost(self, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> float | None:
        if self.price_in is None or self.price_out is None:
            return None
        cached_price = self.price_in if self.price_cached is None else self.price_cached
        fresh = max(input_tokens - cached_input_tokens, 0)
        return (fresh * self.price_in + cached_input_tokens * cached_price + output_tokens * self.price_out) / 1_000_000

    def chat(self, messages: list[dict], *, max_tokens: int = 4096) -> LLMResult:
        body: dict = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / self.provider / key[:2] / f"{key}.json"
        if path.exists():
            record, cached = json.loads(path.read_text()), True
        else:
            record, cached = self._request(body), False
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(record))
            tmp.replace(path)
        usage = record.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        cached_input = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        return LLMResult(
            text=record["text"],
            provider=self.provider,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning,
            latency_s=record["latency_s"],
            cost_usd=self.cost(input_tokens, output_tokens, cached_input),
            cached=cached,
            cached_input_tokens=cached_input,
        )

    def _request(self, body: dict) -> dict:
        if not self.api_key:
            raise LLMError(f"No API key for LLM provider {self.provider!r} (see .env.example).")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last: Exception | None = None
        for attempt in range(self.max_retries):
            started = time.monotonic()
            try:
                resp = httpx.post(f"{self.base_url}/chat/completions", headers=headers, json=body, timeout=self.timeout_s)
            except httpx.TransportError as exc:
                last = exc
                self._sleep(attempt, None)
                continue
            latency = time.monotonic() - started
            if resp.status_code == 429 or resp.status_code >= 500:
                last = LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                self._sleep(attempt, resp.headers.get("retry-after"))
                continue
            if resp.status_code == 400 and "reasoning" in resp.text.lower() and "reasoning_effort" in body:
                body = {k: v for k, v in body.items() if k != "reasoning_effort"}  # provider rejects the knob
                continue
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code} from {self.provider}: {resp.text[:500]}")
            payload = resp.json()
            choices = payload.get("choices") or []
            if not choices:
                raise LLMError(f"No choices in response: {json.dumps(payload)[:300]}")
            return {
                "text": _content_text(choices[0].get("message") or {}),
                "usage": payload.get("usage"),
                "latency_s": round(latency, 3),
                "finish_reason": choices[0].get("finish_reason"),
                "response_id": payload.get("id"),
                "created_at": time.time(),
            }
        raise LLMError(f"Giving up after {self.max_retries} attempts: {last}")

    @staticmethod
    def _sleep(attempt: int, retry_after: str | None) -> None:
        delay = min(30.0, 2.0**attempt) + random.uniform(0, 1.0)
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        time.sleep(delay)
