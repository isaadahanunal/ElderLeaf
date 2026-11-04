"""Two-date comparison (the plan's Compare tab) and the lesion share (spots + yellowing on the crop)."""

import json

import numpy as np

from elderleaf import pipeline, report_agent
from elderleaf.llm import LLMResult
from elderleaf.metrics import compute_metrics
from elderleaf.sam import Instance
from test_api import DEVICE, client, make_photo, upload  # noqa: F401  (client is a fixture)


class SummaryLLM:
    configured = True

    def __init__(self, reply):
        self.reply, self.requests = json.dumps(reply), []

    def chat(self, messages, **kwargs):
        self.requests.append(messages)
        return LLMResult(self.reply, "fake", "fake-spark", 3000, 200, 150, 1.0, 0.005, False)


def two_photos(c):
    plot = c.post("/plots", headers=DEVICE, json={"name": "Bed C", "crop": "lettuce"}).json()
    first = upload(c, plot["id"], make_photo(20), "2026-10-29").json()["id"]
    c.post(f"/plots/{plot['id']}/notes", headers=DEVICE, json={"kind": "watering", "date": "2026-11-01", "text": "Watered well"})
    second = upload(c, plot["id"], make_photo(30), "2026-11-03").json()["id"]
    return plot["id"], first, second


def test_compare_two_dates(client):  # noqa: F811
    plot_id, first, second = two_photos(client)
    out = client.get(f"/plots/{plot_id}/compare", params={"a": second, "b": first}).json()  # any order
    assert out["before"]["analysis_id"] == first and out["after"]["analysis_id"] == second
    assert out["days_between"] == 5
    rows = {r["metric"]: r for r in out["rows"]}
    assert rows["plant_count"]["before"] == rows["plant_count"]["after"] == 5
    cover = rows["canopy_cover_pct"]
    assert cover["change"] > 0 and cover["per_day"] == round(cover["change"] / 5, 2)
    assert [n["kind"] for n in out["notes"]] == ["watering"]
    assert out["written_by"] == "template" and "In 5 days" in out["summary"] and "1 note" in out["summary"]
    assert out["after"]["overlay_url"].endswith(f"/analyses/{second}/overlay.png")


def test_compare_summary_by_agent_is_validated(client):  # noqa: F811
    plot_id, first, second = two_photos(client)
    report_agent.set_enabled(True)
    try:
        good = SummaryLLM({"summary": "Your lettuce has grown and covers more of the bed; the watering you logged may have helped.",
                           "next_step": "Keep the same watering rhythm."})
        pipeline.set_llm(good)
        out = client.get(f"/plots/{plot_id}/compare", params={"a": first, "b": second}).json()
        assert out["written_by"] == "agent" and out["validator"]["passed"]
        assert out["next_step"] == "Keep the same watering rhythm."
        content = good.requests[0][1]["content"]
        assert [part["type"] for part in content] == ["text", "image_url", "image_url"]  # facts + both photos
        assert '"notes_between"' in content[0]["text"]

        invented = SummaryLLM({"summary": "Cover tripled to 90% in a week.", "next_step": None})
        pipeline.set_llm(invented)
        out = client.get(f"/plots/{plot_id}/compare", params={"a": first, "b": second}).json()
        assert out["written_by"] == "template" and len(invented.requests) == 2
        assert any("90" in e for e in out["validator"]["errors"])
    finally:
        report_agent.set_enabled(None)
        pipeline.set_llm(None)


def test_compare_rejects_bad_pairs(client):  # noqa: F811
    plot_id, first, second = two_photos(client)
    other_id, other_first, _ = two_photos(client)
    assert client.get(f"/plots/{plot_id}/compare", params={"a": first, "b": first}).status_code == 422
    assert client.get(f"/plots/{plot_id}/compare", params={"a": first, "b": other_first}).status_code == 404


def test_lesion_share_counts_spots_and_yellowing_on_the_crop():
    plant = Instance("1", 0.9, (0, 0, 10, 10), np.ones((10, 10), bool))  # 100 crop pixels
    discolored = np.zeros((20, 20), bool)
    discolored[0:5, 0:5] = True  # 25 yellow pixels on the plant
    discolored[15:20, 15:20] = True  # off the crop: ignored
    spot = Instance("s", 0.8, (5, 5, 7, 10), np.ones((5, 2), bool))  # 10 spot pixels on the plant
    m = compute_metrics([plant], [], [spot], 20, 20, None, discolored=discolored)
    assert m["lesion_share_pct"] == 35.0
    assert compute_metrics([plant], [], None, 20, 20, None)["lesion_share_pct"] is None  # nothing measured


def test_analysis_reports_lesion_share_from_color(client):  # noqa: F811
    plot = client.post("/plots", headers=DEVICE, json={"name": "Bed L", "crop": "lettuce"}).json()
    analysis = client.get(f"/analyses/{upload(client, plot['id'], make_photo(30), '2026-11-04').json()['id']}").json()
    lesion = analysis["result"]["metrics"]["lesion_share_pct"]
    assert lesion["value"] == 0.0  # healthy green test plants
    assert "leaf-spot search off" in lesion["how"]  # tests run with ENABLE_LESION=0
