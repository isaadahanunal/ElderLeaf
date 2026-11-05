"""Build the read-only demo workspace the jury opens without signing in.

    cd api
    uv run python scripts/seed_demo.py demo/manifest.json            # add / refresh demo plots
    uv run python scripts/seed_demo.py demo/manifest.json --reset    # delete all demo plots first

Every photo in the manifest runs through the normal pipeline once (SAM 3.1 + Muse Spark,
same as a grower's upload) and the results are stored. Visitors then only read stored results:
opening the demo costs no API credits, and it keeps working if the credits run out.

Manifest (paths are relative to the manifest file):

{
  "plots": [
    {
      "name": "Bed 3 · lettuce", "crop": "lettuce", "planted_on": "2026-10-01",
      "area_m2": 6, "lat": 39.891, "lon": 32.783,
      "photos": [{"file": "bed3_1029.jpg", "date": "2026-10-29"}, {"file": "bed3_1103.jpg", "date": "2026-11-03"}],
      "notes":  [{"kind": "watering", "date": "2026-11-01", "text": "Watered about 10 L in the evening"}]
    }
  ]
}
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("JOB_MODE", "sync")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from elderleaf.crops import CROPS  # noqa: E402
from elderleaf.db import Analysis, Note, Plot, SessionLocal, init_db, new_id  # noqa: E402
from elderleaf.pipeline import prepare_upload, run_analysis, segmenter_name  # noqa: E402
from elderleaf.config import settings  # noqa: E402
from elderleaf.storage import get_storage  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--reset", action="store_true", help="delete every demo plot first")
    parser.add_argument("--allow-offline", action="store_true", help="allow the offline dev segmenter (never for the real demo)")
    args = parser.parse_args()

    if segmenter_name() != "SAM 3.1" and not args.allow_offline:
        sys.exit("The demo must be made with SAM 3.1: set MODEL_API_KEY and SAM_BACKEND=meta (or pass --allow-offline for a local test).")

    if segmenter_name() == "SAM 3.1" and not settings.model_api_key:
        sys.exit("MODEL_API_KEY is not set (put it in .env at the repo root).")

    spec = json.loads(args.manifest.read_text())
    base = args.manifest.parent
    init_db()
    storage = get_storage()

    with SessionLocal() as db:
        if args.reset:
            for plot in db.scalars(select(Plot).where(Plot.is_demo.is_(True))).all():
                db.delete(plot)
            db.commit()
            print("removed old demo plots")

        for p in spec["plots"]:
            if p["crop"] not in CROPS:
                sys.exit(f"unknown crop {p['crop']!r}")
            old = db.scalars(select(Plot).where(Plot.is_demo.is_(True), Plot.name == p["name"])).first()
            if old is not None:
                db.delete(old)
                db.commit()
            plot = Plot(
                id=new_id("p"),
                device_id=None,
                is_demo=True,
                name=p["name"],
                crop=p["crop"],
                planted_on=dt.date.fromisoformat(p["planted_on"]) if p.get("planted_on") else None,
                area_m2=p.get("area_m2"),
                row_spacing_cm=p.get("row_spacing_cm"),
                plant_spacing_cm=p.get("plant_spacing_cm"),
                lat=p.get("lat"),
                lon=p.get("lon"),
            )
            db.add(plot)
            for n in p.get("notes", []):
                db.add(Note(id=new_id("n"), plot_id=plot.id, kind=n["kind"], noted_on=dt.date.fromisoformat(n["date"]), text=n["text"]))
            db.commit()
            print(f"plot {plot.name} ({plot.id})")

            for item in sorted(p.get("photos", []), key=lambda x: x["date"]):  # history is built in date order
                data = (base / item["file"]).read_bytes()
                analysis_id = new_id("a")
                jpeg, width, height = prepare_upload(data, settings.analysis_max_side)
                image_key = f"plots/{plot.id}/{analysis_id}.jpg"
                storage.put(image_key, jpeg, "image/jpeg")
                db.add(
                    Analysis(
                        id=analysis_id,
                        plot_id=plot.id,
                        captured_at=dt.date.fromisoformat(item["date"]),
                        image_key=image_key,
                        image_width=width,
                        image_height=height,
                        status="pending",
                        trace=[],
                    )
                )
                db.commit()
                run_analysis(analysis_id)
                db.expire_all()
                done = db.get(Analysis, analysis_id)
                print(f"  photo {item['file']} {item['date']}: {done.status} {done.error or ''}")


if __name__ == "__main__":
    main()
