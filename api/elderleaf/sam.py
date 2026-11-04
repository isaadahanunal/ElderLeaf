"""SAM 3.1 client for the Meta Model API.

- Endpoint: POST {base}/responses with model ``sam-3.1`` (OpenAI Responses API shape).
- One concept per request: the API does not segment several noun phrases in one call.
- The answer is special-token text, not JSON. We parse it with Meta's ``meta-sam-parser``.
- Masks come back box-local: a raster covering the object's box, in source pixels.

Every raw answer is cached on disk, keyed by image hash + prompt + model, so the same
photo never goes to the API twice (saves credits; eval re-runs are free).
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import random
import re
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import httpx
import numpy as np
from meta_sam_parser import (
    CompletedOutcome,
    SegmentationBoxRecord,
    SegmentationMask,
    SegmentationMaskRecord,
    decode_mask_to_raster,
    image_segmentation_format,
)
from PIL import Image

from .config import settings

PRICE_PER_IMAGE_USD = 2.50 / 1000


@lru_cache(maxsize=1024)
def _decode_cached(encoding: str, payload: str, width: int, height: int) -> bytes:
    return decode_mask_to_raster(SegmentationMask(encoding=encoding, payload=payload, width=width, height=height))


def _decode(mask: SegmentationMask) -> bytes:
    return _decode_cached(mask.encoding, mask.payload, mask.width, mask.height)


# The official parser validates each mask by decoding it (pure Python, slow). Route that through
# the cache so parse_output reuses the result instead of decoding every mask twice.
_sam_segmentation = importlib.import_module("meta_sam_parser._segmentation")
_sam_segmentation.decode_mask_to_raster = _decode


class SamError(RuntimeError):
    pass


class CacheMiss(SamError):
    pass


@dataclass
class Instance:
    """One segmented object. ``mask`` is box-local: shape (y1 - y0, x1 - x0)."""

    id: str
    score: float | None
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 (half-open, source pixels)
    mask: np.ndarray  # bool

    @property
    def area(self) -> int:
        return int(self.mask.sum())

    @property
    def score_or_one(self) -> float:
        return 1.0 if self.score is None else self.score

    def full_mask(self, height: int, width: int) -> np.ndarray:
        out = np.zeros((height, width), dtype=bool)
        x0, y0, x1, y1 = self.box
        out[y0:y1, x0:x1] = self.mask
        return out


@dataclass
class Segmentation:
    prompt: str
    width: int
    height: int
    instances: list[Instance]
    raw_text: str
    meta: dict = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- parsing


def parse_output(text: str, width: int, height: int) -> tuple[list[Instance], list[str]]:
    """Parse SAM special-token output into box-local instances."""
    parser = image_segmentation_format().create_parser()
    parser.push(text, emit=False)
    result = parser.finish(CompletedOutcome()).result

    boxes: dict[str, SegmentationBoxRecord] = {}
    masks: dict[str, SegmentationMaskRecord] = {}
    for rec in result.records:
        if isinstance(rec, SegmentationBoxRecord):
            boxes[rec.object_id] = rec
        elif isinstance(rec, SegmentationMaskRecord):
            masks[rec.object_id] = rec  # later revisions overwrite earlier ones

    instances: list[Instance] = []
    for oid, mrec in masks.items():
        b = mrec.bounds
        x0, y0 = int(b.left), int(b.top)
        x1, y1 = min(int(b.right), width), min(int(b.bottom), height)
        raster = np.frombuffer(_decode(mrec.mask), dtype=np.uint8)
        raster = raster.reshape(mrec.mask.height, mrec.mask.width)
        bh, bw = int(b.bottom) - y0, int(b.right) - x0
        if raster.shape != (bh, bw):  # docs don't promise box-sized rasters; rescale if not
            raster = cv2.resize(raster, (bw, bh), interpolation=cv2.INTER_NEAREST)
        raster = raster[: y1 - y0, : x1 - x0].astype(bool)
        score = mrec.confidence
        if score is None and oid in boxes:
            score = boxes[oid].confidence
        instances.append(Instance(id=oid, score=score, box=(x0, y0, x1, y1), mask=raster))

    diagnostics = [f"{d.severity}:{d.code}:{d.message}" for d in result.diagnostics]
    return instances, diagnostics


_RECORD = re.compile(r"<\|box;([^|]*)\|>\s*<\|mask;([^|]*)\|>")


def _field(body: str, key: str) -> str | None:
    for part in body.split(";"):
        name, _, value = part.partition("=")
        if name == key:
            return value
    return None


def scores_from_text(text: str) -> list[float | None]:
    """Confidence of every object in a SAM answer, without decoding any mask (fast).
    Mask payloads are base85 without '|' or ';', so the token regex is safe."""
    scores: list[float | None] = []
    for box, mask in _RECORD.findall(text):
        value = _field(mask, "c") or _field(box, "c")
        scores.append(float(value) if value else None)
    return scores


def _extract_output_text(body: dict) -> str:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    parts: list[str] = []
    for item in body.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text":
                parts.append(content.get("text") or "")
    return "".join(parts)


# --------------------------------------------------------------------------- client


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "prompt"


ImageInput = Image.Image | bytes | str | Path


def image_digest(image: ImageInput, max_side: int | None = None) -> str:
    """Cache key of the source content (file bytes, or pixels for PIL images)."""
    if isinstance(image, (str, Path)):
        digest = hashlib.sha256(Path(image).read_bytes()).hexdigest()
    elif isinstance(image, bytes):
        digest = hashlib.sha256(image).hexdigest()
    else:
        digest = hashlib.sha256(image.tobytes()).hexdigest()
    return f"{digest}-{max_side}" if max_side else digest


def _prepare_image(image: ImageInput, max_side: int | None) -> tuple[bytes, int, int, str]:
    """Return (jpeg_bytes, width, height, digest)."""
    digest = image_digest(image, max_side)
    if isinstance(image, (str, Path)):
        pil = Image.open(image)
    elif isinstance(image, bytes):
        pil = Image.open(io.BytesIO(image))
    else:
        pil = image
    pil = pil.convert("RGB")
    if max_side and max(pil.size) > max_side:
        pil.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=95)
    return buf.getvalue(), pil.width, pil.height, digest


class SamClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        cache_dir: str | Path | None = None,
        timeout_s: float = 180.0,
        max_retries: int = 5,
        include_confidence: bool = True,
    ) -> None:
        self.api_key = api_key or settings.model_api_key
        self.base_url = (base_url or settings.meta_api_base).rstrip("/")
        self.model = model or settings.sam_model
        self.cache_dir = Path(cache_dir or settings.sam_cache_dir)
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.include_confidence = include_confidence
        self._local = threading.local()

    # one httpx client per thread
    def _http(self) -> httpx.Client:
        client = getattr(self._local, "client", None)
        if client is None:
            if not self.api_key:
                raise SamError("MODEL_API_KEY is not set (put it in .env at the repo root).")
            client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout_s,
            )
            self._local.client = client
        return client

    def cache_path(self, digest: str, prompt: str) -> Path:
        conf = "c" if self.include_confidence else "nc"
        return self.cache_dir / self.model / digest[:2] / digest / f"{_slug(prompt)}.{conf}.json"

    def is_cached(self, image: ImageInput, prompt: str, max_side: int | None = None) -> bool:
        return self.cache_path(image_digest(image, max_side), prompt).exists()

    def segment(
        self,
        image: Image.Image | bytes | str | Path,
        prompt: str,
        *,
        max_side: int | None = None,
        parse: bool = True,
        offline: bool = False,
    ) -> Segmentation:
        """Segment one concept. ``offline=True`` only reads the cache (raises CacheMiss)."""
        jpeg, width, height, digest = _prepare_image(image, max_side)
        path = self.cache_path(digest, prompt)
        if path.exists():
            record = json.loads(path.read_text())
            record["meta"]["cached"] = True
        elif offline:
            raise CacheMiss(f"No cached SAM output for prompt {prompt!r} ({path})")
        else:
            record = self._request(jpeg, prompt)
            record.update(prompt=prompt, model=self.model, width=width, height=height, digest=digest)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(record))
            tmp.replace(path)
            record["meta"]["cached"] = False

        instances, diagnostics = ([], [])
        if parse:
            instances, diagnostics = parse_output(record["output_text"], width, height)
        return Segmentation(
            prompt=prompt,
            width=width,
            height=height,
            instances=instances,
            raw_text=record["output_text"],
            meta=record["meta"],
            diagnostics=diagnostics,
        )

    def _request(self, jpeg: bytes, prompt: str) -> dict:
        data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        body: dict = {
            "model": self.model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
        }
        if self.include_confidence:
            body["metadata"] = {"include_confidence": "true"}

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            started = time.monotonic()
            try:
                resp = self._http().post("/responses", json=body)
            except httpx.TransportError as exc:  # timeouts, connection resets
                last_error = exc
                self._sleep(attempt, None)
                continue
            latency = time.monotonic() - started
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = SamError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                self._sleep(attempt, resp.headers.get("retry-after"))
                continue
            if resp.status_code >= 400:
                raise SamError(f"HTTP {resp.status_code} for prompt {prompt!r}: {resp.text[:500]}")
            payload = resp.json()
            status = payload.get("status")
            if status not in (None, "completed"):
                raise SamError(f"Response status {status!r}: {json.dumps(payload)[:500]}")
            return {
                "output_text": _extract_output_text(payload),
                "meta": {
                    "latency_s": round(latency, 3),
                    "attempts": attempt + 1,
                    "usage": payload.get("usage"),
                    "response_id": payload.get("id"),
                    "created_at": time.time(),
                },
            }
        raise SamError(f"Giving up after {self.max_retries} attempts: {last_error}")

    @staticmethod
    def _sleep(attempt: int, retry_after: str | None) -> None:
        delay = min(30.0, 2.0**attempt) + random.uniform(0, 1.0)
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        time.sleep(delay)
