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
