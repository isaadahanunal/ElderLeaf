"""Report agent: validator, crop library + water need it gets, color health check, and the agent end to end
(fake LLM). The writer runs with PROMPT_STRATEGY=agent, like the prompt agent; tests switch it on per case."""

import json

import numpy as np
import pytest

from elderleaf import irrigation, pipeline, report_agent
from elderleaf.crops import crop_info
from elderleaf.health import measure_color
from elderleaf.llm import LLMResult
from elderleaf.sam import Instance
from test_api import AGENT_REPLY, DEVICE, client, make_photo, upload  # noqa: F401  (client is a fixture)

FINAL = {
    "action": "final",
    "summary": "Your lettuce is growing and the bed looks tidy. Give it a drink if the soil is dry.",
    "headline": "Your lettuce looks even and is growing well.",
    "lines": {"c1": "Your lettuce is filling in nicely for its age."},
    "health_summary": "No warning signs in this photo.",
    "signs": {},
    "change": None,
    "next_steps": ["Take the next photo from the same spot."],
}


class ScriptedLLM:
    """The prompt agent gets ranked words; the report writer ("You are ElderLeaf...") gets the scripted
    replies in order (the last one repeats). Every writer request is kept."""

    configured = True

    def __init__(self, *replies):
        self.replies, self.requests = [json.dumps(r) if isinstance(r, dict) else r for r in replies], []

    def chat(self, messages, **kwargs):
        if not messages[0]["content"].startswith("You are ElderLeaf"):
            return LLMResult(AGENT_REPLY, "fake", "fake-spark", 1500, 300, 200, 1.0, 0.003, False)
        self.requests.append(messages)
        text = self.replies[min(len(self.requests) - 1, len(self.replies) - 1)]
        return LLMResult(text, "fake", "fake-spark", 2000, 400, 300, 1.0, 0.004, False)


@pytest.fixture()
def weather(monkeypatch):
    monkeypatch.setattr(irrigation, "get_weather", lambda lat, lon, day=None: {
        "date": "2026-11-04", "et0_mm": 3.0, "rain_mm": 0.0, "tmax_c": 16.0, "source": "test weather"})


@pytest.fixture()
def report_client(client, weather):  # noqa: F811
    pipeline.set_strategy("agent")
    yield client
    pipeline.set_strategy(None)
    pipeline.set_llm(None)


def new_plot(c, headers=DEVICE):
    body = {"name": "Bed R", "crop": "lettuce", "planted_on": "2026-10-01", "area_m2": 10, "lat": 39.89, "lon": 32.78}
    return c.post("/plots", headers=headers, json=body).json()


def analyse(c, plot, headers=DEVICE):
    resp = c.post(f"/plots/{plot['id']}/analyses", headers=headers, files={"file": ("plot.png", make_photo(30), "image/png")},
                  data={"captured_at": "2026-11-04"})
    out = c.get(f"/analyses/{resp.json()['id']}").json()
    assert out["status"] == "done", out["error"]
    return out


# ------------------------------------------------------------------------------ unit


def test_validator_accepts_fact_numbers_and_rejects_the_rest():
    facts = {"measurements": {"canopy_cover_pct": {"value": 38.24}}, "plot": {"photo_date": "2026-11-04", "days_after_planting": 34},
             "plant_detection_confidence": 0.82}
    allowed = report_agent.fact_numbers(facts)
    ok = {"action": "final", "headline": "Crop cover is 38.2% on day 34 (about 38%); detection confidence 82%.",
          "lines": {"c1": "Photo from 4 November."}, "next_steps": ["Weed the plot."]}
    assert report_agent.validate(ok, allowed, {"c1"}, set()) == []

    invented = dict(ok, headline="Cover is 41% and will reach 60% in 2 weeks.")
    assert any("number 41" in e and "60" in e for e in report_agent.validate(invented, allowed, {"c1"}, set()))
    chemical = dict(ok, next_steps=["Spray a fungicide."])
    assert any("chemical" in e and "fungicide" in e for e in report_agent.validate(chemical, allowed, {"c1"}, set()))
    dose = dict(ok, next_steps=["Mix 5 ml per liter of water."])
    assert any("dose" in e for e in report_agent.validate(dose, allowed + [5.0], {"c1"}, set()))
    diagnosis = dict(ok, health_summary="This looks like powdery mildew.")
    assert any("disease" in e for e in report_agent.validate(diagnosis, allowed, {"c1"}, set()))
    unmeasured = dict(ok, signs={"wilting": "Leaves droop."})
    assert any("not measured" in e for e in report_agent.validate(unmeasured, allowed, {"c1"}, {"yellowing"}))
    assert report_agent.validate({"action": "look_closer"}, allowed, {"c1"}, set())  # not a report
    short = report_agent.normalize({"summary": "All good.", "next_step": "Weed."})  # the short reply form
    assert short["action"] == "final" and short["headline"] == "All good." and short["next_steps"] == ["Weed."]


def test_crop_library_stage_and_kc_the_agent_quotes():
    info = crop_info("lettuce", 34)  # FAO-56 stages 20/30/15/10 days: development is days 20-50
    assert (info["stage"], info["stage_start_day"], info["stage_end_day"]) == ("development", 20, 50)
    assert info["kc"] == 0.84  # 0.7 + 14/30 x (1.0 - 0.7)
    assert crop_info("lettuce", None) is None and crop_info("other", 10) is None


def test_yellowing_is_measured_against_the_crops_own_color():
    rgb = np.zeros((100, 200, 3), np.uint8)
    rgb[:] = (120, 80, 50)  # soil
    rgb[10:90, 10:90] = (40, 160, 50)  # healthy plant
    rgb[10:90, 110:190] = (40, 160, 50)
    rgb[10:90, 110:150] = (200, 190, 40)  # half of the second plant is yellow
    plants = [Instance("1", 0.9, (10, 10, 90, 90), np.ones((80, 80), bool)), Instance("2", 0.9, (110, 10, 190, 90), np.ones((80, 80), bool))]
    res = measure_color(rgb, plants, ["m1", "m2"])
    assert res["assessed"] and res["yellowing"]["share_pct"] > 15
    assert res["yellowing"]["plant_ids"] == ["m2"]
    rgb[10:90, 110:150] = (40, 160, 50)
    assert measure_color(rgb, plants, ["m1", "m2"])["yellowing"]["share_pct"] == 0


# ------------------------------------------------------------------------------ end to end


def test_agent_writes_a_validated_report(report_client):
    llm = ScriptedLLM(FINAL)
    pipeline.set_llm(llm)
    out = analyse(report_client, new_plot(report_client))
    result = out["result"]
    report, summary = result["report"], result["summary"]
    assert report["written_by"] == "agent" and report["validator"]["passed"]
    assert summary == {"text": FINAL["summary"], "next_step": FINAL["next_steps"][0], "source": "agent", "attempts": 1,
                       "validator_issues": [], "error": None}
    assert result["context"][0]["text"] == FINAL["lines"]["c1"]
    # code did the numbers the app shows: crop library stage and the FAO-56 water need
    assert result["crop_info"]["stage"] == "development"
    water = result["irrigation"]
    assert water["available"] and water["et0_mm"] == 3.0 and water["plot_total_liters"] == round(water["liters_per_m2"] * 10)
    # the writer saw those facts and the photo
    facts_text = llm.requests[0][1]["content"][0]["text"]
    assert '"water_today"' in facts_text and '"crop_library"' in facts_text and '"lines"' in facts_text
    assert llm.requests[0][1]["content"][1]["type"] == "image_url"
    tools = [s["tool"] for s in result["agent_trace"]]
    for tool in ("get_plot_history", "lookup_crop_info", "get_weather", "assess_health", "write_summary", "validate"):
        assert tool in tools
    assert result["run_stats"]["summary_llm"]["cost_usd"] == 0.004
    md = report_client.get(f"/analyses/{out['id']}/report.md")
    assert md.status_code == 200 and FINAL["summary"] in md.text and "## Water need today (FAO-56)" in md.text


def test_invented_numbers_fall_back_to_templates(report_client):
    llm = ScriptedLLM(dict(FINAL, headline="Your 99 plants cover 77% of the photo."))
    pipeline.set_llm(llm)
    result = analyse(report_client, new_plot(report_client))["result"]
    assert result["report"]["written_by"] == "template" and result["summary"]["source"] == "template"
    assert len(llm.requests) == 2  # the draft, then one round with the problems
    assert "99" in llm.requests[1][-1]["content"]  # the problems went back to the model
    assert any("number 99" in i for i in result["summary"]["validator_issues"])
    assert "plants found" in result["summary"]["text"]
    assert [s["status"] for s in result["agent_trace"] if s["tool"] == "validate"] == ["failed", "failed"]


def test_agent_can_ask_sam_to_look_closer(report_client):
    llm = ScriptedLLM({"action": "look_closer", "prompt": "leaf spot", "sign_type": "leaf_spots", "why": "dark dots"}, FINAL)
    pipeline.set_llm(llm)
    result = analyse(report_client, new_plot(report_client))["result"]
    assert result["report"]["looked_closer"] == "leaf spot" and result["report"]["written_by"] == "agent"
    assert "leaf spot" in report_client.fake.calls
    assert any(s["tool"] == "run_sam" and s["input"] == "leaf spot" for s in result["agent_trace"])
    assert "SAM 3.1 looked for" in llm.requests[1][-1]["content"]


def test_the_growers_experience_sets_the_tone(report_client):
    signup = report_client.post("/auth/signup", headers=DEVICE, json={
        "email": "pro@example.com", "password": "long-enough-1", "name": "Pro", "experience": "experienced"}).json()
    auth = {"Authorization": f"Bearer {signup['token']}"}
    llm = ScriptedLLM(FINAL)
    pipeline.set_llm(llm)
    analyse(report_client, new_plot(report_client, auth), auth)
    facts = json.loads(llm.requests[0][1]["content"][0]["text"].split("(JSON):\n", 1)[1].split("\n\n", 1)[0])
    assert facts["grower"]["experience"] == report_agent.EXPERIENCE_TONE["experienced"]


def test_without_llm_the_report_uses_templates(client, weather):  # noqa: F811
    result = analyse(client, new_plot(client))["result"]  # PROMPT_STRATEGY=fixed in tests: no LLM
    assert result["report"]["written_by"] == "template" and result["summary"]["source"] == "template"
    assert result["report"]["markdown"].startswith("# Bed R: Lettuce")
    assert any(s["tool"] == "write_summary" and s["status"] == "skipped" for s in result["agent_trace"])
