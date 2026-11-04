"""Set up and check the Supabase project the API uses in production.

    cd api && uv run python scripts/setup_supabase.py

Reads DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_KEY and SUPABASE_BUCKET from the repo's .env and:
  1. connects to Postgres, creates the tables (plots, analyses, notes, users, auth_sessions) and turns on
     row level security, so Supabase's public REST API can't read them;
  2. creates the Storage bucket as public if it is missing (photos and videos are served from it);
  3. uploads, reads back and deletes a small test file.
Safe to run again: nothing that exists is changed or deleted.
"""

from __future__ import annotations

import sys
import time

import httpx
from sqlalchemy import inspect, text


def step(ok: bool, label: str, detail: str = "") -> bool:
    print(f"  {'✓' if ok else '✗'} {label}{f'  ({detail})' if detail else ''}")
    return ok


def main() -> int:
    from elderleaf.config import settings

    print("Database")
    url = settings.database_url
    if not url.startswith(("postgres://", "postgresql")):
        step(False, "DATABASE_URL is not a Postgres URL", "paste the Session pooler URI from Supabase → Connect")
        return 1
    from elderleaf.db import engine, init_db

    try:
        with engine.connect() as conn:
            version = conn.execute(text("select version()")).scalar_one().split(",")[0]
        step(True, "connected", version)
        init_db()
        tables = set(inspect(engine).get_table_names())
        wanted = {"plots", "analyses", "notes", "users", "auth_sessions"}
        step(wanted <= tables, "tables ready", ", ".join(sorted(wanted & tables)))
        with engine.connect() as conn:
            rls = dict(conn.execute(text("select relname, relrowsecurity from pg_class where relname = any(:t)"), {"t": list(wanted)}).all())
        step(all(rls.get(t) for t in wanted), "row level security on")
    except Exception as e:  # noqa: BLE001
        step(False, "database", f"{type(e).__name__}: {e}".splitlines()[0][:200])
        return 1

    print("Storage")
    if not (settings.supabase_url and settings.supabase_service_key):
        step(False, "SUPABASE_URL and SUPABASE_SERVICE_KEY are needed")
        return 1
    base = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_key
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}  # works for sb_secret_... and legacy service_role keys
    bucket = settings.supabase_bucket
    with httpx.Client(timeout=30, headers=headers) as http:
        resp = http.get(f"{base}/storage/v1/bucket/{bucket}")
        if resp.status_code == 200:
            info = resp.json()
            if not info.get("public"):
                http.put(f"{base}/storage/v1/bucket/{bucket}", json={"id": bucket, "name": bucket, "public": True}).raise_for_status()
                step(True, f"bucket '{bucket}' made public")
            else:
                step(True, f"bucket '{bucket}' exists and is public")
        elif resp.status_code in (400, 404):
            made = http.post(f"{base}/storage/v1/bucket", json={"id": bucket, "name": bucket, "public": True})
            if not step(made.status_code in (200, 201), f"bucket '{bucket}' created", made.text[:120] if made.status_code >= 300 else "public"):
                return 1
        else:
            step(False, "storage", f"HTTP {resp.status_code}: {resp.text[:160]}")
            return 1

        probe = f"healthcheck/{int(time.time())}.txt"
        put = http.post(f"{base}/storage/v1/object/{bucket}/{probe}", content=b"elderleaf ok", headers={"Content-Type": "text/plain", "x-upsert": "true"})
        if not step(put.status_code in (200, 201), "upload", f"HTTP {put.status_code}"):
            return 1
        public = httpx.get(f"{base}/storage/v1/object/public/{bucket}/{probe}", timeout=30)
        step(public.status_code == 200 and public.content == b"elderleaf ok", "public read", f"HTTP {public.status_code}")
        http.request("DELETE", f"{base}/storage/v1/object/{bucket}", json={"prefixes": [probe]})

    print("\nAll set. Start the API with STORAGE_BACKEND=supabase to use it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
