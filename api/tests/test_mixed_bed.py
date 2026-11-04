"""Mixed beds: the grower marks "more than one crop" and names them; the agent then lists every kind of
plant (scan mode) instead of choosing words for one crop. Fake SAM: any prompt with "plant" finds the big
green blobs, "weed" the small ones, anything else nothing; "lettuce plant" answers weakly (fixture)."""

import json

from elderleaf import pipeline
from elderleaf.llm import LLMResult
from test_api import DEVICE, client, make_photo, upload  # noqa: F401  (client is a fixture)

SCAN_REPLY = {
    "scene": "Lettuce and tomato seedlings with a few weeds.",
    "items": [
        {"phrase": "lettuce rosette", "kind": "crop", "crop": "lettuce"},
        {"phrase": "tomato plant", "kind": "crop", "crop": "tomato"},
        {"phrase": "grass weed", "kind": "weed"},
    ],
}


REPORT_REPLY = {
    "action": "final",
    "headline": "Both crops are up; the tomatoes are easy to spot.",
    "lines": {},
    "health_summary": "No warning signs in this photo.",
    "signs": {},
    "change": None,
    "water": None,
    "next_steps": ["Check that the lettuce is in the frame next time."],
}


class ScanLLM:
    """First call: the scan list; later calls: the report."""

    configured = True

    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        reply = SCAN_REPLY if self.calls == 1 else REPORT_REPLY
        return LLMResult(json.dumps(reply), "fake", "fake-spark", 1800, 350, 250, 1.0, 0.004, False)


def mixed_plot(c, **extra):
    body = {"name": "Mixed bed", "crop": "lettuce", "mixed": True, "other_crops": ["tomato"], **extra}
    return c.post("/plots", headers=DEVICE, json=body)


def analyse(c, plot_id):
    created = upload(c, plot_id, make_photo(30), "2026-11-04").json()
    out = c.get(f"/analyses/{created['id']}").json()
    assert out["status"] == "done", out["error"]
    return out["result"]


def test_mixed_bed_needs_its_other_crops(client):  # noqa: F811
    assert mixed_plot(client, other_crops=[]).status_code == 422
    assert mixed_plot(client, other_crops=["banana"]).status_code == 422
    plot = mixed_plot(client).json()
    assert plot["mixed"] and plot["other_crops"] == ["tomato"] and plot["other_crop_labels"] == ["Tomato"]
    single = client.post("/plots", headers=DEVICE, json={"name": "One", "crop": "lettuce", "other_crops": ["tomato"]}).json()
    assert single["mixed"] is False and single["other_crops"] == []  # other crops only count for a mixed bed


def test_mixed_bed_without_agent_searches_every_crop_name(client):  # noqa: F811
    result = analyse(client, mixed_plot(client).json()["id"])
    stats = result["run_stats"]
    assert stats["strategy"] == "fixed"
    assert {a["prompt"] for a in stats["attempts"]} == {"lettuce plant", "tomato plant", "weed"}
    by_crop = result["metrics"]["by_crop"]
    assert by_crop["tomato"]["plant_count"] == 5 and by_crop["lettuce"]["plant_count"] == 0
    assert all(m["crop"] == "tomato" for m in result["masks"] if m["class"] == "crop")
    assert any(c["badge"] == "Crop not found" and "lettuce" in c["text"] for c in result["context"])


def test_mixed_bed_scan_mode_with_fallback_words(client):  # noqa: F811
    pipeline.set_strategy("agent")
    llm = ScanLLM()
    pipeline.set_llm(llm)
    try:
        result = analyse(client, mixed_plot(client).json()["id"])
    finally:
        pipeline.set_strategy(None)
        pipeline.set_llm(None)
    stats = result["run_stats"]
    assert stats["strategy"] == "scan" and llm.calls == 1
    assert [i["phrase"] for i in stats["scan_items"]] == ["lettuce rosette", "tomato plant", "grass weed"]
    assert stats["proposals"] == {"lettuce": ["lettuce rosette"], "tomato": ["tomato plant"], "weed": ["grass weed"]}
    # every listed phrase is searched in round 1; lettuce found nothing confident, so round 2 tries its library word
    tries = [(a["prompt"], a["rank"], a["round"]) for a in stats["attempts"]]
    assert ("lettuce rosette", 1, 1) in tries and ("tomato plant", 2, 1) in tries and ("grass weed", 3, 1) in tries
    assert ("lettuce plant", "fallback", 2) in tries
    assert result["metrics"]["by_crop"]["tomato"]["plant_count"] == 5
    assert result["metrics"]["weed_share_pct"]["value"] > 0
    steps = [s["tool"] for s in result["agent_trace"]]
    assert steps.index("scan_plants") < steps.index("run_sam")


def test_mixed_bed_report_agent_sees_each_crop(client):  # noqa: F811
    from elderleaf import report_agent

    pipeline.set_strategy("agent")
    llm = ScanLLM()
    pipeline.set_llm(llm)
    report_agent.set_enabled(True)
    try:
        result = analyse(client, mixed_plot(client).json()["id"])
    finally:
        report_agent.set_enabled(None)
        pipeline.set_strategy(None)
        pipeline.set_llm(None)
    assert llm.calls == 2  # the scan, then the report
    assert result["report"]["written_by"] == "agent" and result["report"]["headline"] == REPORT_REPLY["headline"]
    assert "Per crop: Lettuce 0 plants" in result["report"]["markdown"] and "Tomato 5 plants" in result["report"]["markdown"]


def test_other_crop_never_takes_the_named_crops_plants(client):  # noqa: F811
    # "other" has the generic library word "plant"; searching it would label every plant "other"
    plot = mixed_plot(client, crop="tomato", other_crops=["other"]).json()
    result = analyse(client, plot["id"])
    prompts = [a["prompt"] for a in result["run_stats"]["attempts"]]
    assert "plant" not in prompts and "tomato plant" in prompts
    by_crop = result["metrics"]["by_crop"]
    assert by_crop["tomato"]["plant_count"] == 5 and by_crop["other"]["plant_count"] == 0
    assert not any(c["badge"] == "Crop not found" for c in result["context"])


def test_mixed_bed_falls_back_to_plant_when_no_crop_is_found(client):  # noqa: F811
    client.fake.weak_prompts.add("tomato plant")
    try:
        result = analyse(client, mixed_plot(client).json()["id"])
    finally:
        client.fake.weak_prompts.discard("tomato plant")
    tries = [(a["prompt"], a["round"]) for a in result["run_stats"]["attempts"]]
    assert ("plant", 3) in tries
    by_crop = result["metrics"]["by_crop"]
    assert by_crop["*"]["plant_count"] == 5 and by_crop["*"]["label"] == "Plants (not told apart)"
    assert all(m["crop"] is None for m in result["masks"] if m["class"] == "crop")
