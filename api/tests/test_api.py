"""End-to-end API test with a fake SAM (no network, no API key).

The fake 'segments' by color on the uploaded photo: green blobs are plants (big = crop,
small = weed), white blobs are paper. So the whole pipeline runs on real pixels.
"""

import io

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from elderleaf import pipeline
from elderleaf.app import app
from elderleaf.llm import LLMError, LLMResult
from elderleaf.sam import Instance, SamClient, Segmentation

CROPS_XY = [(150, 150), (400, 150), (650, 150), (150, 400), (400, 400)]
WEEDS_XY = [(275, 280), (560, 520)]
DEVICE = {"X-Device-Id": "device-test-1"}


class FakeSam(SamClient):
    def __init__(self, weak_prompts=()):
        super().__init__(api_key="unused")
        self.weak_prompts = set(weak_prompts)
        self.calls: list[str] = []

    def segment(self, image, prompt, **kwargs):
        self.calls.append(prompt)
        rgb = np.array(Image.open(io.BytesIO(image)).convert("RGB")).astype(int)
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        green = (g > 110) & (r < 110) & (b < 110)
        white = (r > 200) & (g > 200) & (b > 200)
        if "weed" in prompt:
            mask, lo, hi = green, 20, 400
        elif "paper" in prompt:
            mask, lo, hi = white, 1000, 10**9
        elif "plant" in prompt:
            mask, lo, hi = green, 400, 10**9
        else:
            mask = None
        instances = []
        if mask is not None:
            n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
            for k in range(1, n):
                x, y, w, h, area = (int(v) for v in stats[k])
                if lo <= area < hi:
                    score = 0.3 if prompt in self.weak_prompts else 0.9
                    instances.append(Instance(str(k), score, (x, y, x + w, y + h), labels[y : y + h, x : x + w] == k))
        return Segmentation(prompt, rgb.shape[1], rgb.shape[0], instances, raw_text="", meta={"cached": False})


def make_photo(radius: int, seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    soil = np.array([130, 80, 55])
    img = np.clip(soil + rng.integers(-20, 20, (600, 800, 3)), 0, 255).astype(np.uint8)  # textured soil
    for x, y in CROPS_XY:
        cv2.circle(img, (x, y), radius, (40, 170, 50), -1)
    for x, y in WEEDS_XY:
        cv2.circle(img, (x, y), 6, (40, 170, 50), -1)
    img[470:569, 700:770] = 250  # A4 sheet, 70 x 99 px (aspect 1.414)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def client():
    fake = FakeSam(weak_prompts={"lettuce plant"})
    pipeline.set_sam(fake)
    with TestClient(app) as c:
        c.fake = fake
        yield c
    pipeline.set_sam(None)


def upload(client, plot_id, photo, captured_at):
    return client.post(
        f"/plots/{plot_id}/analyses",
        headers=DEVICE,
        files={"file": ("plot.png", photo, "image/png")},
        data={"captured_at": captured_at},
    )


def test_full_flow(client):
    assert client.get("/health").json()["ok"] is True
    assert any(c["id"] == "lettuce" for c in client.get("/crops").json())
    assert client.post("/plots", json={"name": "Bed A", "crop": "lettuce"}).status_code == 400  # no device id

    plot = client.post(
        "/plots", headers=DEVICE, json={"name": "Bed A", "crop": "lettuce", "planted_on": "2026-10-01", "area_m2": 4}
    ).json()

    # first photo
    resp = upload(client, plot["id"], make_photo(radius=30), "2026-10-29")
    assert resp.status_code == 202
    first = client.get(f"/analyses/{resp.json()['id']}").json()
    assert first["status"] == "done", first["error"]
    result = first["result"]
    metrics = result["metrics"]
    assert metrics["plant_count"]["value"] == 5
    assert len(metrics["plant_count"]["mask_ids"]) == 5
    assert 0 < metrics["weed_share_pct"]["value"] < 5
    assert 2 < metrics["canopy_cover_pct"]["value"] < 4
    assert result["scale"]["found"] is True
    assert metrics["mean_plant_area"]["unit"] == "cm2"
    assert 200 < metrics["mean_plant_area"]["value"] < 300  # pi*30^2 px / (6930 px / 623.7 cm²)
    assert result["days_after_planting"] == 28
    assert {m["class"] for m in result["masks"]} == {"crop", "weed", "scale"}
    assert all(m["polygons"] for m in result["masks"])
    assert result["comparison"] is None
    # fixed words: the weak crop-specific word was followed by the generic one
    assert "plant" in client.fake.calls
    assert any(s["input"] == "lettuce plant" and "trying the next word" in s["result"] for s in first["trace"])
    assert any(s["input"] == "plant" and "confident, using it" in s["result"] for s in first["trace"])
    assert not any(s["status"] == "failed" for s in first["trace"])
    tools = [s["tool"] for s in first["trace"]]
    assert "lookup_crop_info" in tools and "get_weather" in tools and "assess_health" in tools and "write_summary" in tools
    # day 28 lettuce, ~3% cover: below the crop-library band -> attention
    assert result["crop_info"]["stage"] == "development"
    assert any(c["badge"] == "Behind typical" for c in result["context"])
    assert result["irrigation"]["available"] is False  # no location on this plot
    assert result["summary"]["source"] == "template" and result["summary"]["text"]  # no LLM in this run
    report = result["report"]
    assert report["headline"] and report["markdown"].startswith("# ") and report["written_by"] == "template"
    assert result["segmenter"] == "SAM 3.1"
    stats = result["run_stats"]
    assert stats["strategy"] == "fixed" and stats["llm"] is None
    assert stats["chosen"]["crop"]["prompt"] == "plant"
    assert stats["sam_calls"] == 4  # lettuce plant, plant, weed, white paper sheet
    assert stats["total_cost_usd"] == 0.01

    # second photo, 6 days later, bigger plants
    second = client.get(f"/analyses/{upload(client, plot['id'], make_photo(radius=40, seed=1), '2026-11-04').json()['id']}").json()
    comparison = second["result"]["comparison"]
    assert comparison["previous_analysis_id"] == first["id"]
    assert comparison["days_between"] == 6
    assert comparison["deltas"]["canopy_cover_pct"] > 0
    assert comparison["deltas"]["plant_count"] == 0
    assert any("rose from" in c["text"] for c in second["result"]["context"])

    # plot card + detail + notes + csv + image file
    cards = client.get("/plots", headers=DEVICE).json()
    card = next(c for c in cards if c["id"] == plot["id"])
    assert card["latest"]["id"] == second["id"]
    assert card["deltas"]["canopy_cover_pct"] > 0
    note = client.post(f"/plots/{plot['id']}/notes", headers=DEVICE, json={"kind": "watering", "date": "2026-11-01", "text": "5 L"})
    assert note.status_code == 201
    detail = client.get(f"/plots/{plot['id']}").json()
    assert [a["id"] for a in detail["analyses"]] == [first["id"], second["id"]]
    assert detail["notes"][0]["text"] == "5 L"
    csv_text = client.get(f"/plots/{plot['id']}/export.csv").text
    assert len(csv_text.strip().splitlines()) == 3
    assert client.get(second["image_url"]).status_code == 200

    # pictures to inspect: final masks, and every SAM call of the trace
    overlay = client.get(second["overlay_url"])
    assert overlay.status_code == 200 and overlay.content[:8] == b"\x89PNG\r\n\x1a\n"
    sam_steps = [s for s in second["trace"] if s["tool"] == "run_sam"]
    assert sam_steps and all(s["image_url"] for s in sam_steps)
    for step in sam_steps:
        picture = client.get(step["image_url"])
        assert picture.status_code == 200 and picture.headers["content-type"] == "image/png"
    not_called = client.get(f"/analyses/{second['id']}/sam.png", params={"prompt": "tomato plant"})
    assert not_called.status_code == 404


def test_old_row_video_rows_stay_hidden(client):
    """Row videos were removed; a database that still has such a row must not break the plot pages."""
    import datetime as dt

    from elderleaf.db import Analysis, SessionLocal

    plot = client.post("/plots", headers=DEVICE, json={"name": "Bed V", "crop": "lettuce"}).json()
    photo = upload(client, plot["id"], make_photo(20), "2026-11-01").json()["id"]
    with SessionLocal() as db:
        db.add(Analysis(id="a_oldvideo", plot_id=plot["id"], mode="video", captured_at=dt.date(2026, 11, 2),
                        image_key="old.jpg", status="done", trace=[], result={"row_plant_count": 7}))
        db.commit()
    detail = client.get(f"/plots/{plot['id']}").json()
    assert [a["id"] for a in detail["analyses"]] == [photo] and detail["latest"]["id"] == photo
    assert client.get("/analyses/a_oldvideo").status_code == 404
    assert len(client.get(f"/plots/{plot['id']}/export.csv").text.strip().splitlines()) == 2


def test_rejects_bad_uploads_and_foreign_devices(client):
    plot = client.post("/plots", headers=DEVICE, json={"name": "Bed B", "crop": "other"}).json()
    bad = client.post(f"/plots/{plot['id']}/analyses", headers=DEVICE, files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 400
    other = client.post(
        f"/plots/{plot['id']}/analyses",
        headers={"X-Device-Id": "someone-else"},
        files={"file": ("p.png", make_photo(30), "image/png")},
    )
    assert other.status_code == 403
    assert all(c["id"] != plot["id"] for c in client.get("/plots", headers={"X-Device-Id": "someone-else"}).json())


AGENT_REPLY = """Here you go:
```json
{"scene": "Young lettuce in rows with a few grass weeds.", "crop_visible": true,
 "crop_prompts": ["lettuce seedling", "lettuce plant", "green rosette plant"],
 "weed_prompts": ["grass weed", "small weed", "weed seedling"]}
```"""


SUMMARY_REPLY = '{"summary": "Your lettuce looks small for its age.", "next_step": "Take another photo from the same spot next week."}'


class FakeLLM:
    configured = True

    def __init__(self, reply=AGENT_REPLY, fail=False, summaries=(SUMMARY_REPLY,)):
        self.reply, self.fail, self.calls = reply, fail, 0
        self.summaries = list(summaries)

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.fail:
            raise LLMError("HTTP 503 from fake")
        if messages[0]["content"].startswith("You are ElderLeaf"):  # the summary writer
            text = self.summaries.pop(0) if len(self.summaries) > 1 else self.summaries[0]
            return LLMResult(text, "fake", "fake-spark", 800, 100, 50, 0.5, 0.001, False)
        return LLMResult(self.reply, "fake", "fake-spark", 1500, 300, 200, 1.2, 0.003, False)


@pytest.fixture()
def agent_client(client):
    pipeline.set_strategy("agent")
    yield client
    pipeline.set_strategy(None)
    pipeline.set_llm(None)


def test_agent_tries_ranked_words_then_stops(agent_client):
    pipeline.set_llm(FakeLLM())
    plot = agent_client.post("/plots", headers=DEVICE, json={"name": "Bed C", "crop": "lettuce"}).json()
    analysis = agent_client.get(f"/analyses/{upload(agent_client, plot['id'], make_photo(30), '2026-11-01').json()['id']}").json()
    assert analysis["status"] == "done", analysis["error"]
    stats = analysis["result"]["run_stats"]
    assert stats["strategy"] == "agent"
    assert stats["proposals"]["crop"] == ["lettuce seedling", "lettuce plant", "green rosette plant"]
    # 1 finds nothing, 2 is weak (fake scores it 0.3), 3 is confident -> stop at 3
    crop_tries = [a for a in stats["attempts"] if a["target"] == "crop"]
    assert [(a["prompt"], a["ok"]) for a in crop_tries] == [
        ("lettuce seedling", False),
        ("lettuce plant", False),
        ("green rosette plant", True),
    ]
    assert stats["chosen"]["crop"] == {"prompt": "green rosette plant", "rank": 3}
    assert stats["chosen"]["weed"] == {"prompt": "grass weed", "rank": 1}
    assert stats["sam_calls"] == 5  # 3 crop + 1 weed + A4
    assert stats["llm"]["input_tokens"] == 1500 and stats["llm"]["cost_usd"] == 0.003
    assert stats["summary_llm"]["cost_usd"] == 0.001
    assert stats["total_cost_usd"] == round(5 * 0.0025 + 0.003 + 0.001, 6)
    assert analysis["result"]["summary"]["source"] == "agent" and analysis["result"]["report"]["headline"]
    assert analysis["result"]["metrics"]["plant_count"]["value"] == 5
    assert analysis["trace"][1]["tool"] == "propose_prompts" and analysis["trace"][1]["status"] == "done"


def test_agent_failure_falls_back_to_fixed_words(agent_client):
    pipeline.set_llm(FakeLLM(fail=True))
    plot = agent_client.post("/plots", headers=DEVICE, json={"name": "Bed D", "crop": "lettuce"}).json()
    analysis = agent_client.get(f"/analyses/{upload(agent_client, plot['id'], make_photo(30), '2026-11-01').json()['id']}").json()
    assert analysis["status"] == "done", analysis["error"]
    stats = analysis["result"]["run_stats"]
    assert stats["strategy"] == "fixed"
    assert stats["chosen"]["crop"]["prompt"] == "plant"
    assert any(s["tool"] == "propose_prompts" and s["status"] == "failed" for s in analysis["trace"])


def test_validator_rejects_invented_numbers_then_accepts(agent_client, monkeypatch):
    from elderleaf import irrigation

    monkeypatch.setattr(
        irrigation, "get_weather", lambda lat, lon, day=None: {"date": "2026-11-01", "et0_mm": 2.0, "rain_mm": 0.0, "tmax_c": 15.0, "source": "fake"}
    )
    bad = '{"summary": "Your lettuce covers 42% of the bed. Spray 20 ml/L of fungicide.", "next_step": "Weed."}'
    pipeline.set_llm(FakeLLM(summaries=(bad, SUMMARY_REPLY)))
    plot = agent_client.post(
        "/plots",
        headers=DEVICE,
        json={"name": "Bed E", "crop": "lettuce", "planted_on": "2026-10-04", "area_m2": 10, "lat": 39.89, "lon": 32.78},
    ).json()
    analysis = agent_client.get(f"/analyses/{upload(agent_client, plot['id'], make_photo(30), '2026-11-01').json()['id']}").json()
    result = analysis["result"]
    summary = result["summary"]
    assert summary["source"] == "agent" and summary["attempts"] == 2
    joined = " ".join(summary["validator_issues"])
    assert "number 42" in joined and "fungicide" in joined and "dose" in joined
    assert any(s["tool"] == "validate" for s in analysis["trace"])
    water = result["irrigation"]
    assert water["available"] and water["et0_mm"] == 2.0
    assert water["plot_total_liters"] == round(water["liters_per_m2"] * 10)
    assert 0.15 <= water["kc_adj"] < water["kc"]  # sparse cover uses less water than a full canopy


def test_validator_unit():
    from elderleaf.summary import validate

    facts = {"measurements": {"crop_cover_pct": 38.2, "plant_count": 12}, "change": {"deltas": {"weed": -3.5}}}
    assert validate("Cover is 38.2% (about 38%) with 12 plants; weeds fell by 3.5 points.", facts) == []
    assert validate("An A4 sheet and FAO-56 were used.", facts) == []
    assert validate("You have 15 plants.", facts) == ["number 15 is not in FACTS"]
    assert any("disease" in i for i in validate("This looks like blight.", facts))
