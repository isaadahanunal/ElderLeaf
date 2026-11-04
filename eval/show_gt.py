"""Draw every ground-truth layer of one PhenoBench image next to the photo.

    uv run --project api python eval/show_gt.py --split val --out /tmp/gt.png [--name 06-05_....png]

Without --name it picks the 06-05 image with the most cut-off and touching plants.
"""

from __future__ import annotations

import argparse

import cv2
import numpy as np
from PIL import Image

from phenobench import PhenoBench

PANEL = 512


def _random_colors(n: int, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    colors = rng.integers(60, 255, size=(n + 1, 3), dtype=np.uint8)
    colors[0] = 0
    return colors


def _panel(img: np.ndarray, title: str) -> np.ndarray:
    img = cv2.resize(img, (PANEL, PANEL), interpolation=cv2.INTER_NEAREST)
    bar = np.full((40, PANEL, 3), 255, np.uint8)
    cv2.putText(bar, title, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2, cv2.LINE_AA)
    return np.concatenate([bar, img], axis=0)


def render(dataset: PhenoBench, split: str, name: str) -> np.ndarray:
    s = dataset.load(split, name)
    rgb = np.array(Image.open(s.image_path).convert("RGB"))
    scale = PANEL / rgb.shape[1]

    sem_colors = np.array([[0, 0, 0], [40, 200, 60], [230, 40, 40], [150, 255, 150], [255, 150, 200]], np.uint8)
    semantics = sem_colors[np.clip(s.semantics, 0, 4)]

    plant_ids = _random_colors(int(s.plants.labels.max()))[s.plants.labels]
    vis_map = np.array(Image.open(dataset.root / split / "plant_visibility" / name))
    visibility = np.stack([vis_map] * 3, axis=-1).astype(np.uint8)
    leaves = _random_colors(int(s.leaves.labels.max()), seed=7)[s.leaves.labels]

    crowd_colors = {0: (60, 120, 255), 1: (255, 210, 0), 2: (255, 40, 40)}
    crowding = np.zeros_like(rgb)
    for g in s.plants.instances:
        crowding[s.plants.labels == g.id] = crowd_colors[min(g.neighbours, 2)]

    panels = [
        _panel(rgb, "images/ (the photo)"),
        _panel(semantics, "semantics/ green crop, red weed"),
        _panel(plant_ids, "plant_instances/ one color per plant"),
        _panel(visibility, "plant_visibility/ white = fully inside"),
        _panel(leaves, "leaf_instances/ one color per leaf"),
        _panel(crowding, "touching: blue 0, yellow 1, red 2+"),
    ]
    # write each plant's visibility on the visibility panel
    vis_panel = panels[3]
    for g in s.plants.instances:
        if g.visibility < 0.999:
            x0, y0, x1, y1 = g.box
            cx, cy = int((x0 + x1) / 2 * scale), int((y0 + y1) / 2 * scale) + 40
            cv2.putText(vis_panel, f"{g.visibility:.2f}", (max(cx - 22, 2), cy), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 60, 60), 2, cv2.LINE_AA)
    gap = np.full((PANEL + 40, 8, 3), 255, np.uint8)
    rows = [np.concatenate([panels[i], gap, panels[i + 1], gap, panels[i + 2]], axis=1) for i in (0, 3)]
    return np.concatenate([rows[0], np.full((8, rows[0].shape[1], 3), 255, np.uint8), rows[1]], axis=0)


def pick(dataset: PhenoBench, split: str) -> str:
    best, best_score = None, -1
    for name in [n for n in dataset.names(split) if n.startswith("06-05")][:80]:
        s = dataset.load(split, name)
        cut = sum(g.visibility < 0.999 for g in s.plants.instances)
        touching = sum(g.neighbours > 0 for g in s.plants.instances)
        score = min(cut, 4) + min(touching, 4)
        if score > best_score:
            best, best_score = name, score
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--split", default="val")
    ap.add_argument("--name")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dataset = PhenoBench(args.data)
    name = args.name or pick(dataset, args.split)
    s = dataset.load(args.split, name)
    Image.fromarray(render(dataset, args.split, name)).save(args.out)
    print(f"{name}: {len(s.plants.instances)} plants, {len(s.leaves.instances)} leaves -> {args.out}")
    for g in s.plants.instances:
        print(f"  plant {g.id:3d} {g.cls:4s} area={g.area:6d}px visibility={g.visibility:.2f} partial={g.partial} touching={g.neighbours}")


if __name__ == "__main__":
    main()
