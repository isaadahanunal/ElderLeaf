"""Row video: a synthetic walk along a row of 12 plants; each must be counted exactly once."""

import cv2
import numpy as np

from test_api import DEVICE, client  # noqa: F401  (fixture with the color-based fake SAM)

N_PLANTS = 12


def make_row_video(path, n_frames=60, fps=10):
    rng = np.random.default_rng(3)
    width, height, view = 3200, 480, 640
    soil = np.clip(np.array([55, 80, 130]) + rng.integers(-25, 25, (height, width, 3)), 0, 255).astype(np.uint8)
    xs = np.linspace(200, width - 200, N_PLANTS).astype(int)
    for i, x in enumerate(xs):
        y = 240 + (25 if i % 2 else -25)
        cv2.circle(soil, (int(x), y), 45 + (i % 3) * 6, (50, 170, 40), -1)  # BGR green
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (view, height))
    for f in range(n_frames):
        x0 = int((width - view) * f / (n_frames - 1))
        writer.write(soil[:, x0 : x0 + view].copy())
    writer.release()


def test_row_video_counts_each_plant_once(client, tmp_path):  # noqa: F811
    video = tmp_path / "row.mp4"
    make_row_video(video)
    plot = client.post("/plots", headers=DEVICE, json={"name": "Row 1", "crop": "lettuce"}).json()
    resp = client.post(
        f"/plots/{plot['id']}/videos",
        headers=DEVICE,
        files={"file": ("row.mp4", video.read_bytes(), "video/mp4")},
        data={"captured_at": "2026-11-03"},
    )
    assert resp.status_code == 202, resp.text
    analysis = client.get(f"/analyses/{resp.json()['id']}").json()
    assert analysis["status"] == "done", analysis["error"]
    assert analysis["mode"] == "video" and analysis["video_url"]
    vr = analysis["video_result"]
    assert vr["row_plant_count"] == N_PLANTS
    assert vr["max_per_frame"] < N_PLANTS  # never all in view at once: counting needs the tracker
    assert len(vr["frames"]) >= 10
    assert any(s["tool"] == "track_plants" for s in analysis["trace"])
    detail = client.get(f"/plots/{plot['id']}").json()
    assert detail["analyses"][0]["row_plant_count"] == N_PLANTS
