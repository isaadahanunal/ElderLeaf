"""Image storage: local folder (dev, served at /files) or a public Supabase Storage bucket."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import httpx

from .config import settings


class LocalStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def url(self, key: str, base_url: str) -> str:
        return f"{base_url.rstrip('/')}/files/{key}"


class SupabaseStorage:
    """Public bucket. Uploads use the service key; reads use the public URL."""

    def __init__(self, url: str, service_key: str, bucket: str) -> None:
        self.base = url.rstrip("/")
        self.service_key = service_key
        self.bucket = bucket

    def put(self, key: str, data: bytes, content_type: str) -> None:
        resp = httpx.post(
            f"{self.base}/storage/v1/object/{self.bucket}/{key}",
            headers={
                "Authorization": f"Bearer {self.service_key}",
                "apikey": self.service_key,
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            content=data,
            timeout=60,
        )
        resp.raise_for_status()

    def get(self, key: str) -> bytes:
        resp = httpx.get(self.url(key, ""), timeout=60)
        resp.raise_for_status()
        return resp.content

    def url(self, key: str, base_url: str) -> str:
        return f"{self.base}/storage/v1/object/public/{self.bucket}/{key}"


@lru_cache(maxsize=1)
def get_storage() -> LocalStorage | SupabaseStorage:
    if settings.storage_backend == "supabase":
        if not (settings.supabase_url and settings.supabase_service_key):
            raise RuntimeError("STORAGE_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
        return SupabaseStorage(settings.supabase_url, settings.supabase_service_key, settings.supabase_bucket)
    return LocalStorage(settings.storage_dir)
