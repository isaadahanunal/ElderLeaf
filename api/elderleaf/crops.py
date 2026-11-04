"""Crop library. For now: labels and SAM prompts. Agronomic values (typical canopy by growth
stage, FAO-56 Kc) get added with their sources; the agent may only quote numbers from here."""

from __future__ import annotations

import json
from pathlib import Path

CROPS: dict[str, dict] = json.loads((Path(__file__).parent / "crop_library.json").read_text())
# Last resort for the crop. "crop plant" found nothing on PhenoBench, the plain "plant" does
# (it also catches weeds, so the crop name and the agent's phrases are tried first).
FALLBACK_PROMPT = "plant"


def crop_label(crop_id: str) -> str:
    return CROPS.get(crop_id, {}).get("label", crop_id.replace("_", " ").title())


def crop_prompt(crop_id: str) -> str:
    return CROPS.get(crop_id, {}).get("sam_prompt", FALLBACK_PROMPT)
