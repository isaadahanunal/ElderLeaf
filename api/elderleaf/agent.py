"""Prompt agent: Muse Spark looks at the photo and proposes SAM 3.1 search phrases.

It returns three ranked phrases for the crop and three for the weeds. The pipeline tries them in
order, keeps the first one SAM answers confidently, and falls back to the fixed phrase after that.
The agent never produces numbers; it only decides what SAM should look for.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import asdict, dataclass, field

from PIL import Image

from .llm import LLMClient, LLMResult, image_part

SYSTEM_PROMPT = """You pick search phrases for SAM 3.1, an image segmentation model. SAM finds every object in a photo that matches a short English noun phrase.
Rules for a good SAM phrase:
- 1 to 4 words: a singular noun phrase for one concrete, visible thing.
- Describe what it looks like: plant name, growth stage or leaf shape (for example "sugar beet seedling", "grass seedling", "broadleaf weed rosette").
- Category words on their own ("crop", "weed", "vegetation") often return nothing; pair them with a concrete noun.
- No commas, no "and"/"or", no negation, no numbers, no positions ("on the left").
Answer with one JSON object and nothing else."""

USER_TEMPLATE = """A beginner grower took this top-down photo of their {crop} plot{age}.
Return:
{{"scene": "<one short sentence about what you see, without numbers>",
 "crop_visible": <true if you can see {crop} plants, otherwise false>,
 "crop_prompts": ["<phrase most likely to find each {crop} plant>", "<a different second choice>", "<a different third choice>"],
 "weed_prompts": ["<phrase most likely to find the weeds in this photo>", "<a different second choice>", "<a different third choice>"],
 "leaf_prompts": ["<phrase most likely to find each single leaf of the {crop} plants>", "<a different second choice>", "<a different third choice>"]}}
Rank each list from most to least likely to work. The three phrases in a list must differ. If you see no weeds, still give three phrases for the weeds most likely to grow here.
Weed phrases must not also describe the {crop} plants: avoid plain words like "seedling" or "broadleaf plant" when the {crop} looks like that, and name what makes the weeds look different (for example grass blades or clover leaves)."""

_FORBIDDEN_CHARS = re.compile(r"[,;:+/|\d]")
_FORBIDDEN_WORDS = {"and", "or", "not", "no", "without", "left", "right", "top", "bottom", "near", "behind", "above", "below"}


def clean_phrase(text: object) -> str | None:
    """A SAM-safe phrase, or None. SAM needs one short concrete noun phrase (Meta's prompt rules)."""
    phrase = re.sub(r"\s+", " ", str(text)).strip().strip(".\"'").lower()
    words = phrase.split()
    if not phrase or len(phrase) > 40 or not 1 <= len(words) <= 5:
        return None
    if _FORBIDDEN_CHARS.search(phrase) or _FORBIDDEN_WORDS & set(words):
        return None
    return phrase


def _phrases(values: object, limit: int = 3) -> list[str]:
    out: list[str] = []
    for value in values if isinstance(values, list) else []:
        phrase = clean_phrase(value)
        if phrase and phrase not in out:
            out.append(phrase)
    return out[:limit]


def parse_proposal(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON object in the answer")
    data = json.loads(match.group(0))
    scene = data.get("scene")
    visible = data.get("crop_visible")
    return {
        "crop_prompts": _phrases(data.get("crop_prompts")),
        "weed_prompts": _phrases(data.get("weed_prompts")),
        "leaf_prompts": _phrases(data.get("leaf_prompts")),
        "scene": scene.strip() if isinstance(scene, str) and scene.strip() else None,
        "crop_visible": visible if isinstance(visible, bool) else None,
    }


@dataclass
class Proposal:
    crop_prompts: list[str]
    weed_prompts: list[str]
    scene: str | None
    crop_visible: bool | None
    llm: LLMResult | None
    error: str | None = None
    leaf_prompts: list[str] = field(default_factory=list)  # eval experiment; the app doesn't use leaves yet

    def to_dict(self) -> dict:
        data = asdict(self)
        return data


def _combine(results: list[LLMResult]) -> LLMResult:
    costs = [r.cost_usd for r in results]
    return LLMResult(
        text=results[-1].text,
        provider=results[-1].provider,
        model=results[-1].model,
        input_tokens=sum(r.input_tokens for r in results),
        output_tokens=sum(r.output_tokens for r in results),
        reasoning_tokens=sum(r.reasoning_tokens for r in results),
        latency_s=round(sum(r.latency_s for r in results), 3),
        cost_usd=None if any(c is None for c in costs) else sum(costs),
        cached=all(r.cached for r in results),
        cached_input_tokens=sum(r.cached_input_tokens for r in results),
    )


def _llm_image(image: bytes, max_side: int = 1024) -> bytes:
    img = Image.open(io.BytesIO(image)).convert("RGB")
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def propose_prompts(llm: LLMClient, image: bytes, crop_label: str, days_after_planting: int | None = None) -> Proposal:
    age = f", {days_after_planting} days after planting" if days_after_planting is not None else ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": USER_TEMPLATE.format(crop=crop_label.lower(), age=age)},
                image_part(_llm_image(image)),
            ],
        },
    ]
    results: list[LLMResult] = []
    try:
        results.append(llm.chat(messages))
        try:
            parsed = parse_proposal(results[-1].text)
        except (ValueError, json.JSONDecodeError):
            # one retry, telling the model what went wrong
            messages += [
                {"role": "assistant", "content": results[-1].text},
                {"role": "user", "content": "That was not a valid JSON object. Reply with the JSON object only."},
            ]
            results.append(llm.chat(messages))
            parsed = parse_proposal(results[-1].text)
    except Exception as exc:
        return Proposal([], [], None, None, _combine(results) if results else None, error=f"{type(exc).__name__}: {exc}")
    if not parsed["crop_prompts"] and not parsed["weed_prompts"]:
        return Proposal([], [], parsed["scene"], parsed["crop_visible"], _combine(results), error="no usable phrases")
    return Proposal(**parsed, llm=_combine(results))


# ------------------------------------------------------------------------------ scan mode
# Instead of 3 ranked phrases per target, the agent lists one phrase per kind of plant it sees
# (as many as the photo needs) and SAM searches all of them. Made for photos with several
# crops and weed types; eval/mixed_scenes.py compares it with the ranked mode.

MAX_SCAN_ITEMS = 8

SCAN_TEMPLATE = """A beginner grower took this top-down photo of their plot{age}. The grower says it grows: {crops}.
List what SAM should search for so that every plant in this photo gets found, one entry per kind of plant that looks different:
- each crop you can see: one entry, or two if its plants look clearly different (for example small seedlings and large plants);
- each kind of weed you can see, as separate entries (for example grasses and broadleaf weeds).
Use as many entries as this photo needs (at most {limit}) and only list plants you can actually see.
Return:
{{"scene": "<one short sentence about what you see, without numbers>",
 "items": [{{"phrase": "<SAM phrase>", "kind": "crop", "crop": "<which crop: {crop_list}>"}},
           {{"phrase": "<SAM phrase>", "kind": "weed"}}]}}
Weed phrases must not also describe the crop plants: name what makes the weeds look different (for example grass blades or clover leaves)."""


def _scan_crop(value: object, phrase: str, crops: list[str]) -> str | None:
    """Which of the grower's crops an entry is about (None: a crop the grower did not name)."""
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    if not crops:
        return text or phrase
    if text in crops:
        return text
    for crop in sorted(crops, key=len, reverse=True):  # "sugar beet" before "beet"
        if crop in text or crop in phrase:
            return crop
    return crops[0] if len(crops) == 1 else None


def parse_scan(text: str, crops: list[str], limit: int = MAX_SCAN_ITEMS) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON object in the answer")
    data = json.loads(match.group(0))
    raw_items = data.get("items")
    items: list[dict] = []
    seen: set[str] = set()
    for raw in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw, dict):
            continue
        phrase = clean_phrase(raw.get("phrase", ""))
        kind = str(raw.get("kind", "")).strip().lower()
        if not phrase or phrase in seen or kind not in ("crop", "weed"):
            continue
        crop = _scan_crop(raw.get("crop"), phrase, crops) if kind == "crop" else None
        if kind == "crop" and crop is None:
            continue
        seen.add(phrase)
        items.append({"phrase": phrase, "kind": kind, "crop": crop})
    scene = data.get("scene")
    return {"items": items[:limit], "scene": scene.strip() if isinstance(scene, str) and scene.strip() else None}


@dataclass
class Scan:
    items: list[dict]  # {"phrase", "kind": "crop" | "weed", "crop": crop name or None}
    scene: str | None
    llm: LLMResult | None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def scan_plants(llm: LLMClient, image: bytes, crops: list[str], limit: int = MAX_SCAN_ITEMS, days_after_planting: int | None = None) -> Scan:
    names = [c.lower() for c in crops]
    prompt = SCAN_TEMPLATE.format(
        age=f", {days_after_planting} days after planting" if days_after_planting is not None else "",
        crops=", ".join(names) or "not told",
        crop_list=" or ".join(f'"{c}"' for c in names) or "its common name",
        limit=limit,
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [{"type": "text", "text": prompt}, image_part(_llm_image(image))]},
    ]
    results: list[LLMResult] = []
    try:
        results.append(llm.chat(messages))
        try:
            parsed = parse_scan(results[-1].text, names, limit)
        except (ValueError, json.JSONDecodeError):
            messages += [
                {"role": "assistant", "content": results[-1].text},
                {"role": "user", "content": "That was not a valid JSON object. Reply with the JSON object only."},
            ]
            results.append(llm.chat(messages))
            parsed = parse_scan(results[-1].text, names, limit)
    except Exception as exc:
        return Scan([], None, _combine(results) if results else None, error=f"{type(exc).__name__}: {exc}")
    if not parsed["items"]:
        return Scan([], parsed["scene"], _combine(results), error="no usable phrases")
    return Scan(parsed["items"], parsed["scene"], _combine(results))
