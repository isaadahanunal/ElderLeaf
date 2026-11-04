"""Report agent: validator, FAO-56 arithmetic, color health check, and the agent end to end (fake LLM)."""

import json

import numpy as np
import pytest

from elderleaf import pipeline, report_agent
from elderleaf.agronomy import crop_info, water_need
from elderleaf.health import measure_color
from elderleaf.llm import LLMResult
from elderleaf.sam import Instance
from test_api import DEVICE, client, make_photo, upload  # noqa: F401  (client is a fixture)

FINAL = {
    "action": "final",
    "headline": "Your lettuce looks even and is growing well.",
    "lines": {"c1": "Your lettuce is filling in nicely."},
    "health_summary": "No warning signs in this photo.",
    "signs": {},
    "change": None,
    "water": "Give the bed a good drink today if the soil is dry.",
    "next_steps": ["Take the next photo from the same spot."],
}


class ScriptedLLM:
    """Answers with the given replies in order (the last one repeats) and keeps every request."""

    configured = True

    def __init__(self, *replies):
        self.replies, self.requests = [json.dumps(r) if isinstance(r, dict) else r for r in replies], []

    def chat(self, messages, **kwargs):
        self.requests.append(messages)
        text = self.replies[min(len(self.requests) - 1, len(self.replies) - 1)]
        return LLMResult(text, "fake", "fake-spark", 2000, 400, 300, 1.0, 0.004, False)


@pytest.fixture()
def report_client(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(report_agent.weather, "daily_et0", lambda lat, lon, day: {
        "date": day.isoformat(), "et0_mm": 3.0, "rain_mm": 0.0, "source": "test weather"})
    report_agent.set_enabled(True)
    yield client
    report_agent.set_enabled(None)
    pipeline.set_llm(None)


def new_plot(c):
    body = {"name": "Bed R", "crop": "lettuce", "planted_on": "2026-10-01", "area_m2": 10, "lat": 39.89, "lon": 32.78}
    return c.post("/plots", headers=DEVICE, json=body).json()


def analyse(c, plot):
    created = upload(c, plot["id"], make_photo(30), "2026-11-04").json()
    out = c.get(f"/analyses/{created['id']}").json()
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
    assert any("41" in e and "60" in e for e in report_agent.validate(invented, allowed, {"c1"}, set()))
    chemical = dict(ok, next_steps=["Spray a fungicide."])
    assert any("chemical" in e for e in report_agent.validate(chemical, allowed, {"c1"}, set()))
    dose = dict(ok, next_steps=["Mix 5 ml per liter of water."])
    assert any("dose" in e for e in report_agent.validate(dose, allowed + [5.0], {"c1"}, set()))
    diagnosis = dict(ok, health_summary="This looks like powdery mildew.")
    assert any("disease" in e for e in report_agent.validate(diagnosis, allowed, {"c1"}, set()))
    unmeasured = dict(ok, signs={"wilting": "Leaves droop."})
    assert any("not measured" in e for e in report_agent.validate(unmeasured, allowed, {"c1"}, {"yellowing"}))
    assert report_agent.validate({"action": "look_closer"}, allowed, {"c1"}, set())  # not a report


def test_fao56_stage_kc_and_water_need():
    info = crop_info("lettuce", 34)  # stages 20/30/15/10 days: development is days 20-49
    assert (info.stage, info.stage_start, info.stage_end) == ("development", 20, 49)
    assert info.kc_stage == 0.84  # 0.7 + 14/29 x (1.0 - 0.7)
    need = water_need(info, canopy_pct=20.0, et0_mm=3.0, area_m2=10)
    assert need["kc"] == 0.82  # capped by cover: 0.7 + 0.3 x min(1, 2 x 0.2)
    assert (need["liters_per_m2"], need["plot_total_liters"]) == (2.5, 25)
    assert crop_info("lettuce", None).stage is None
    assert crop_info("other", 10) is None


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
    report = result["report"]
    assert report["written_by"] == "agent" and report["validator"]["passed"]
    assert report["headline"] == FINAL["headline"]
    assert result["context"][0]["text"] == FINAL["lines"]["c1"]
    # code did the numbers: FAO-56 water need from the (fake) weather, stage from the planting date
    irrigation = result["irrigation"]
    assert irrigation["et0_mm"] == 3.0 and irrigation["stage"] == "development"
    assert irrigation["text"] == FINAL["water"]
    assert irrigation["plot_total_liters"] == round(irrigation["liters_per_m2"] * 10)
    # the agent saw the facts and the photo
    facts_text = llm.requests[0][1]["content"][0]["text"]
    assert '"water_today"' in facts_text and '"lines"' in facts_text
    assert llm.requests[0][1]["content"][1]["type"] == "image_url"
    tools = [s["tool"] for s in result["agent_trace"]]
    for tool in ("get_plot_history", "lookup_crop_info", "assess_health", "get_weather", "compute_irrigation", "write_report", "validate_report"):
        assert tool in tools
    assert result["run_stats"]["report_llm"]["cost_usd"] == 0.004
    md = report_client.get(f"/analyses/{out['id']}/report.md")
    assert md.status_code == 200 and FINAL["headline"] in md.text and "## Water need today (FAO-56)" in md.text


def test_invented_numbers_fall_back_to_templates(report_client):
    llm = ScriptedLLM(dict(FINAL, headline="Your 99 plants cover 77% of the photo."))
    pipeline.set_llm(llm)
    result = analyse(report_client, new_plot(report_client))["result"]
    report = result["report"]
    assert report["written_by"] == "template" and not report["validator"]["passed"]
    assert len(llm.requests) == 2  # the draft, then one round with the errors
    assert "99" in llm.requests[1][-1]["content"]  # the errors went back to the model
    assert "plants found" in report["headline"]
    assert [s["status"] for s in result["agent_trace"] if s["tool"] == "validate_report"] == ["failed", "failed"]


def test_agent_can_ask_sam_to_look_closer(report_client):
    llm = ScriptedLLM({"action": "look_closer", "prompt": "leaf spot", "sign_type": "leaf_spots", "why": "dark dots"}, FINAL)
    pipeline.set_llm(llm)
    result = analyse(report_client, new_plot(report_client))["result"]
    assert result["report"]["looked_closer"] == "leaf spot"
    assert result["report"]["written_by"] == "agent"
    assert "leaf spot" in report_client.fake.calls
    assert any(s["tool"] == "run_sam" and s["input"] == "leaf spot" for s in result["agent_trace"])
    assert "SAM 3.1 looked for" in llm.requests[1][-1]["content"]


def test_without_llm_the_report_uses_templates(client):  # noqa: F811
    report_agent.set_enabled(False)
    try:
        result = analyse(client, new_plot(client))["result"]
    finally:
        report_agent.set_enabled(None)
    assert result["report"]["written_by"] == "template"
    assert result["report"]["markdown"].startswith("# Bed R: Lettuce")
    assert result["irrigation"] is None  # WEATHER=0 in tests
