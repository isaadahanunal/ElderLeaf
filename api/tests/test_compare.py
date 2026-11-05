"""Two-date comparison (the plan's Compare tab, the app's GET /plots/{id}/compare) and the lesion share."""

import json

import numpy as np

from elderleaf import pipeline
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


def two_photos(c, **plot):
    body = {"name": "Bed C", "crop": "lettuce", **plot}
    created = c.post("/plots", headers=DEVICE, json=body).json()
    first = upload(c, created["id"], make_photo(20), "2026-10-29").json()["id"]
    c.post(f"/plots/{created['id']}/notes", headers=DEVICE, json={"kind": "watering", "date": "2026-11-01", "text": "Watered well"})
    second = upload(c, created["id"], make_photo(30), "2026-11-03").json()["id"]
    return created["id"], first, second


def with_agent(llm, fn):
    pipeline.set_strategy("agent")
    pipeline.set_llm(llm)
    try:
        return fn()
    finally:
        pipeline.set_strategy(None)
        pipeline.set_llm(None)


def test_compare_two_dates(client):  # noqa: F811
    plot_id, first, second = two_photos(client)
    out = client.get(f"/plots/{plot_id}/compare", params={"a": second, "b": first}).json()  # any order
    assert out["a"]["id"] == first and out["b"]["id"] == second
    assert out["days_between"] == 5
    rows = {r["metric"]: r for r in out["rows"]}
    assert rows["plant_count"]["a"] == rows["plant_count"]["b"] == 5
    cover = rows["canopy_cover_pct"]
    assert cover["delta"] > 0 and cover["per_day"] == round(cover["delta"] / 5, 2)
    assert [n["kind"] for n in out["notes_between"]] == ["watering"]
    summary = out["summary"]
    assert summary["source"] == "template" and "In 5 days" in summary["text"] and "1 note" in summary["text"]


def test_compare_summary_by_agent_is_validated(client):  # noqa: F811
    plot_id, first, second = two_photos(client)
    good = SummaryLLM({"summary": "Your lettuce has grown and covers more of the bed; the watering you logged may have helped.",
                       "next_step": "Keep the same watering rhythm."})
    out = with_agent(good, lambda: client.get(f"/plots/{plot_id}/compare", params={"a": first, "b": second}).json())
    assert out["summary"]["source"] == "agent" and out["summary"]["next_step"] == "Keep the same watering rhythm."
    content = good.requests[0][1]["content"]
    assert [part["type"] for part in content] == ["text", "image_url", "image_url"]  # facts + both photos
    assert '"notes_between"' in content[0]["text"]
    # the agent's text is kept: the same pair again costs nothing
    again = with_agent(good, lambda: client.get(f"/plots/{plot_id}/compare", params={"a": first, "b": second}).json())
    assert again["summary"] == out["summary"] and len(good.requests) == 1

    plot_id, first, second = two_photos(client)
    invented = SummaryLLM({"summary": "Cover tripled to 90% in a week.", "next_step": None})
    out = with_agent(invented, lambda: client.get(f"/plots/{plot_id}/compare", params={"a": first, "b": second}).json())
    assert out["summary"]["source"] == "template" and len(invented.requests) == 2
    assert any("number 90" in i for i in out["summary"]["validator_issues"])


def test_compare_mixed_bed_has_rows_per_crop(client):  # noqa: F811
    plot_id, first, second = two_photos(client, crop="tomato", mixed=True, other_crops=["lettuce"])
    rows = {r["metric"]: r for r in client.get(f"/plots/{plot_id}/compare", params={"a": first, "b": second}).json()["rows"]}
    assert rows["plant_count:tomato"]["label"] == "Plants (tomato)" and rows["plant_count:tomato"]["b"] == 5
    assert rows["plant_count:lettuce"]["b"] == 0


def test_compare_rejects_bad_pairs(client):  # noqa: F811
    plot_id, first, second = two_photos(client)
    _, other_first, _ = two_photos(client)
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
