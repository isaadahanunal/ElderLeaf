"""Compare two photos of one plot (the plan's Compare tab).

Code computes the difference table (plants, crop cover, weed share, leaf spots, average plant size,
change per day) and collects the grower's notes between the two dates. The report agent's LLM sees
both photos and these facts and writes a short change summary that may refer to the notes; the same
validator as the report checks it (numbers from the facts only, no chemicals, doses or diagnoses).
A failed check goes back once; after that, or without an LLM, a template summary is used.
"""

from __future__ import annotations

import json

from .agent import _llm_image
from .llm import LLMClient, image_part
from .report_agent import fact_numbers, parse_reply, text_errors

COMPARED = [
    ("plant_count", "Plants"),
    ("canopy_cover_pct", "Crop cover"),
    ("weed_share_pct", "Weed share"),
    ("lesion_share_pct", "Leaf spots / yellowing"),
    ("mean_plant_area", "Average plant size"),
]

SYSTEM = """You compare two top-down photos of the same plot for a beginner grower. Code has measured both; you get the measurements, the changes and the grower's notes, plus the two photos (earlier first).
Rules:
- Use only numbers that appear in the facts (you may round them). Never compute or invent a number.
- Never diagnose, never name a disease, never recommend a pesticide or any chemical, product or dose.
- If a note may explain a change (watering, weeding, thinning, harvest), say so, as a possibility.
- Plain, kind English: at most 3 short sentences.
Answer with one JSON object and nothing else."""

USER = """Facts (JSON):
{facts}

Reply as {{"summary": "<what changed between the two photos and what it may mean>", "next_step": "<one short action, or null>"}}."""

FIX = """Your reply broke these rules:
{errors}
Reply with the corrected JSON only."""


def _value(result: dict, key: str) -> tuple[float | None, str | None]:
    item = (result.get("metrics") or {}).get(key)
    return (None, None) if not item else (item.get("value"), item.get("unit"))


def _fmt(value: float | None) -> str:
    if value is None:
        return "–"
    return f"{value:.0f}" if float(value).is_integer() else f"{value:g}"


def difference(before: dict, after: dict, days: int) -> tuple[list[dict], list[dict]]:
    """Rows of the difference table, and per-crop plant counts for mixed beds."""
    rows = []
    for key, label in COMPARED:
        (a, unit_a), (b, unit_b) = _value(before, key), _value(after, key)
        comparable = a is not None and b is not None and unit_a == unit_b  # px vs cm² are not comparable
        change = round(b - a, 1) if comparable else None
        rows.append({
            "metric": key, "label": label, "unit": unit_b or unit_a, "before": a, "after": b, "change": change,
            "per_day": round(change / days, 2) if change is not None and days > 0 else None,
        })
    by_crop = []
    crops_a = (before.get("metrics") or {}).get("by_crop") or {}
    crops_b = (after.get("metrics") or {}).get("by_crop") or {}
    for crop in dict.fromkeys([*crops_a, *crops_b]):
        a, b = (crops_a.get(crop) or {}).get("plant_count"), (crops_b.get(crop) or {}).get("plant_count")
        label = (crops_b.get(crop) or crops_a.get(crop) or {}).get("label", crop)
        by_crop.append({"crop": crop, "label": label, "before": a, "after": b,
                        "change": b - a if a is not None and b is not None else None})
    return rows, by_crop


def _template(days: int, rows: list[dict], notes: list[dict]) -> str:
    parts = [f"{r['label'].lower()} {_fmt(r['before'])} → {_fmt(r['after'])}" + ("%" if r["unit"] == "%" else "")
             for r in rows if r["metric"] in ("plant_count", "canopy_cover_pct", "weed_share_pct") and r["change"] is not None]
    text = f"In {days} days: " + ", ".join(parts) + "." if parts else f"{days} days between the two photos."
    if notes:
        text += f" You logged {len(notes)} note{'s' if len(notes) > 1 else ''} in between."
    return text


def _signs(result: dict) -> list[dict]:
    health = result.get("health") or {}
    return [{"type": s.get("type"), "likelihood": s.get("likelihood"), "share_of_crop_pct": s.get("share_pct")} for s in health.get("signs") or []]


def compare(crop_label: str, before, after, notes: list[dict], images: tuple[bytes, bytes] | None, llm: LLMClient | None) -> dict:
    """`before` / `after` are finished Analysis rows (before is the earlier one)."""
    days = (after.captured_at - before.captured_at).days
    rows, by_crop = difference(before.result, after.result, days)
    out = {"days_between": days, "rows": rows, "by_crop": by_crop, "summary": _template(days, rows, notes), "next_step": None,
           "written_by": "template", "validator": {"passed": False, "attempts": 0, "errors": ["no LLM; template summary used"]}}
    if llm is None or not llm.configured or images is None:
        return out
    facts = {
        "crop": crop_label.lower(),
        "earlier_photo": {"date": before.captured_at.isoformat(), "days_after_planting": before.result.get("days_after_planting"),
                          "possible_health_signs": _signs(before.result)},
        "later_photo": {"date": after.captured_at.isoformat(), "days_after_planting": after.result.get("days_after_planting"),
                        "possible_health_signs": _signs(after.result)},
        "days_between": days,
        "measurements": [{k: r[k] for k in ("label", "unit", "before", "after", "change", "per_day")} for r in rows],
        "plants_per_crop": by_crop or None,
        "notes_between": notes,
    }
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": [{"type": "text", "text": USER.format(facts=json.dumps(facts, indent=1))},
                                     image_part(_llm_image(images[0])), image_part(_llm_image(images[1]))]},
    ]
    allowed = fact_numbers(facts)
    errors: list[str] = []
    for attempt in range(1, 3):
        try:
            result = llm.chat(messages)
        except Exception as exc:  # LLM down: keep the template
            out["validator"] = {"passed": False, "attempts": attempt - 1, "errors": [f"LLM unavailable: {type(exc).__name__}"]}
            return out
        reply = parse_reply(result.text)
        summary = reply.get("summary") if reply else None
        step = reply.get("next_step") if reply else None
        if not isinstance(summary, str) or not summary.strip():
            errors = ['Reply with {"summary": "...", "next_step": ...}.']
        else:
            errors = text_errors([summary] + ([step] if isinstance(step, str) else []), allowed)
        if not errors:
            out.update(summary=summary.strip(), next_step=step.strip() if isinstance(step, str) and step.strip() else None,
                       written_by="agent", validator={"passed": True, "attempts": attempt, "errors": []})
            return out
        messages += [{"role": "assistant", "content": result.text},
                     {"role": "user", "content": FIX.format(errors="\n".join(f"- {e}" for e in errors))}]
    out["validator"] = {"passed": False, "attempts": 2, "errors": errors}
    return out
