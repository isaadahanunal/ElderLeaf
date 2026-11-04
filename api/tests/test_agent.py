"""Agent answer parsing and the ranked-candidate chain (no network)."""

from elderleaf.agent import clean_phrase, parse_proposal, propose_prompts
from elderleaf.llm import LLMResult
from elderleaf.prompting import build_candidates


def test_clean_phrase_enforces_sam_rules():
    assert clean_phrase("  Sugar beet plant. ") == "sugar beet plant"
    assert clean_phrase("weed, grass") is None  # lists return nothing in SAM
    assert clean_phrase("plant on the left") is None  # positions
    assert clean_phrase("weed and grass") is None
    assert clean_phrase("3 plants") is None  # numbers
    assert clean_phrase("a very long phrase with far too many words") is None


def test_parse_proposal_tolerates_fences_and_junk():
    text = 'Sure!\n```json\n{"scene": "Rows of seedlings.", "crop_visible": true, "crop_prompts": ["Beet seedling", "beet seedling", "red stem plant", "x, y"], "weed_prompts": []}\n```'
    parsed = parse_proposal(text)
    assert parsed["crop_prompts"] == ["beet seedling", "red stem plant"]  # deduped, invalid dropped
    assert parsed["weed_prompts"] == []
    assert parsed["crop_visible"] is True and parsed["scene"] == "Rows of seedlings."


def test_build_candidates_ranks_then_fallback_without_duplicates():
    assert build_candidates(["a", "b", "c", "d"], ["b", "z"]) == [("a", 1), ("b", 2), ("c", 3), ("z", "fallback")]
    assert build_candidates([], ["x", "y"]) == [("x", "fallback"), ("y", "fallback")]


class ScriptedLLM:
    configured = True

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        return LLMResult(self.replies.pop(0), "fake", "m", 1000, 100, 50, 1.0, 0.001, False)


def _png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (90, 140, 60)).save(buf, format="PNG")
    return buf.getvalue()


def test_propose_prompts_retries_once_on_bad_json():
    llm = ScriptedLLM(["I think it is beets", '{"crop_prompts": ["beet seedling"], "weed_prompts": ["grass seedling"]}'])
    proposal = propose_prompts(llm, _png(), "Sugar beet")
    assert llm.calls == 2 and proposal.error is None
    assert proposal.crop_prompts == ["beet seedling"] and proposal.weed_prompts == ["grass seedling"]
    assert proposal.llm.input_tokens == 2000 and abs(proposal.llm.cost_usd - 0.002) < 1e-12


def test_propose_prompts_reports_unusable_answers():
    proposal = propose_prompts(ScriptedLLM(["nope", "still nope"]), _png(), "Sugar beet")
    assert proposal.error and proposal.crop_prompts == []
