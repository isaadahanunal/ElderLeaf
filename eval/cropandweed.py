"""CropAndWeed: loader, image selection, download of the selected images, two-crop collages.

Dataset: Steininger et al., "The CropAndWeed Dataset", WACV 2023.
https://github.com/cropandweed/cropandweed-dataset
8,034 field photos (1920x1088), 8 crops and ~60 weed species; every plant has a box with its
species and every pixel a species id. Images with two crops are rare (109, 38 with 3+ plants
of the second crop), so experiment B also builds collages: the centre halves of two photos of
different crops side by side.

LICENCE (data/cropandweed/LICENCE.txt): non-commercial use only (research, teaching, personal
experimentation), cite the paper, and do NOT distribute the images or modified versions of
them (collages and mask overlays count). Everything stays under data/ (gitignored); only
numbers may be published.

Layout (annotations: cropandweed_annotations.tar, unpacked):
    data/cropandweed/bboxes/<name>.csv                Left,Top,Right,Bottom,LabelID,StemX,StemY
    data/cropandweed/labelIds/CropAndWeed/<name>.png  species id per pixel (255 = unsorted plant)
    data/cropandweed/images/<name>.jpg                only the selected images (`download`)
    data/cropandweed/collages/<a>+<b>.png             built by `collages`

    uv run --project api python eval/cropandweed.py select      # -> eval/results/mixed/selection.json
    uv run --project api python eval/cropandweed.py download    # streams the 4 image archives (11 GB), keeps ~240 images
    uv run --project api python eval/cropandweed.py collages    # builds the two-crop collages
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from common import RESULTS_DIR

REPO = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO / "data" / "cropandweed"
SELECTION = RESULTS_DIR / "mixed" / "selection.json"
URL = "https://vitro-testing.com/wp-content/uploads/2022/12/"
IMAGE_PARTS = [f"cropandweed_images{i}of4" for i in range(1, 5)]

# label id -> crop name used in prompts (the official CropsOrWeed9 grouping)
CROP_IDS = {
    **{i: "maize" for i in range(1, 7)},
    **{i: "sugar beet" for i in range(7, 13)},
    94: "soybean",
    24: "sunflower",
    18: "potato",
    13: "pea",
    26: "bean",
    27: "bean",
    15: "pumpkin",
}
CROPS = ["maize", "sugar beet", "sunflower", "soybean", "pumpkin", "bean", "pea", "potato"]
# the official "Weed" class of CropsOrWeed9; other ids (255 unsorted plants, rare species) are ignored
WEED_IDS = {
    31, 48, 62, 65, 68, 69, 74, 75, 81, 84, 86, 32, 29, 33, 37, 49, 30, 44, 66, 87, 89, 91, 61, 79, 34, 41, 52,
    35, 36, 78, 38, 39, 71, 72, 88, 42, 45, 70, 47, 51, 54, 58, 60, 80, 83, 96, 22, 63, 85, 56, 57, 64, 77, 50,
    59, 67, 76,
}
GRASS_IDS = {31, 48, 62, 65, 68, 69, 74, 75, 81, 84, 86}  # grasses; every other weed is broadleaf
MIN_VISIBLE = 0.25  # a plant cut by the collage window counts only if a quarter of it is left


@dataclass
class GTPlant:
    id: int  # id in Scene.labels
    cls: str  # crop | weed | ignore (unsorted or rare plants: matching them is neither right nor wrong)
    species: str | None  # crop name for crops
    group: str | None  # grass | broadleaf for weeds
    area: int = 0


@dataclass
class Scene:
    """One photo to analyse, with its ground truth. PhenoBench photos are converted to this too."""

    id: str
    set: str  # phenobench | A | B-real | B-collage
    image_path: Path
    crops: list[str]  # what the grower tells us
    labels: np.ndarray  # int32 (H, W): 0 = no plant, else GTPlant.id
    plants: list[GTPlant]
    crop_px: np.ndarray  # bool (H, W)
    weed_px: np.ndarray
    meta: dict = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return self.labels.shape


def read_boxes(root: Path, name: str) -> list[tuple[int, int, int, int, int]]:
    out = []
    with open(root / "bboxes" / f"{name}.csv") as f:
        for row in csv.reader(f):
            if row:
                x0, y0, x1, y1, label = (int(v) for v in row[:5])
                out.append((x0, y0, x1, y1, label))
    return out


def _classify(label: int) -> tuple[str, str | None, str | None]:
    if label in CROP_IDS:
        return "crop", CROP_IDS[label], None
    if label in WEED_IDS:
        return "weed", None, "grass" if label in GRASS_IDS else "broadleaf"
    return "ignore", None, None


def _instances(sem: np.ndarray, boxes: list[tuple[int, int, int, int, int]]) -> tuple[np.ndarray, list[GTPlant]]:
    """Instance map from boxes + species mask: a plant = its species' pixels inside its box.
    Big boxes are painted first, so a small plant inside a big plant's box keeps its pixels."""
    h, w = sem.shape
    labels = np.zeros((h, w), np.int32)
    order = sorted(boxes, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))
    plants = []
    for k, (x0, y0, x1, y1, label) in enumerate(order, start=1):
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1 + 1, w), min(y1 + 1, h)
        labels[y0:y1, x0:x1][sem[y0:y1, x0:x1] == label] = k
        plants.append(GTPlant(k, *_classify(label)))
    areas = np.bincount(labels.ravel(), minlength=len(plants) + 1)
    for p in plants:
        p.area = int(areas[p.id])
        if p.area == 0:
            p.cls = "ignore"
    return labels, plants


class CropAndWeed:
    def __init__(self, root: str | Path = DATA_ROOT) -> None:
        self.root = Path(root)

    def names(self) -> list[str]:
        return sorted(p.stem for p in (self.root / "bboxes").glob("*.csv"))

    def image_path(self, name: str) -> Path:
        return self.root / "images" / f"{name}.jpg"

    def species_mask(self, name: str) -> np.ndarray:
        return np.array(Image.open(self.root / "labelIds" / "CropAndWeed" / f"{name}.png"))

    def load(self, name: str, set_name: str = "A") -> Scene:
        sem = self.species_mask(name)
        labels, plants = _instances(sem, read_boxes(self.root, name))
        crops = sorted({p.species for p in plants if p.cls == "crop"}, key=CROPS.index)
        return Scene(
            name, set_name, self.image_path(name), crops, labels, plants,
            np.isin(sem, list(CROP_IDS)), np.isin(sem, list(WEED_IDS)),
        )

    # ------------------------------------------------------------------ collages
    def collage_path(self, left: str, right: str) -> Path:
        return self.root / "collages" / f"{left}+{right}.png"

    def load_collage(self, left: str, right: str) -> Scene:
        """Centre half of `left` next to the centre half of `right` (same size as one photo)."""
        a, b = self.load(left), self.load(right)
        h, w = a.shape
        half = w // 2
        x = (w - half) // 2
        parts, plants, offset = [], [], 0
        for scene in (a, b):
            if scene.shape != (h, w):
                raise ValueError(f"{scene.id} is {scene.shape}, expected {(h, w)}")
            labels = scene.labels[:, x : x + half]
            visible = np.bincount(labels.ravel(), minlength=len(scene.plants) + 1)
            for p in scene.plants:
                cls = p.cls if visible[p.id] >= MIN_VISIBLE * max(p.area, 1) else "ignore"
                if visible[p.id]:
                    plants.append(GTPlant(p.id + offset, cls, p.species, p.group, int(visible[p.id])))
            parts.append((np.where(labels > 0, labels + offset, 0), scene.crop_px[:, x : x + half], scene.weed_px[:, x : x + half]))
            offset += len(scene.plants)
        labels = np.concatenate([p[0] for p in parts], axis=1).astype(np.int32)
        crops = sorted(set(a.crops) | set(b.crops), key=CROPS.index)
        return Scene(
            f"{left}+{right}", "B-collage", self.collage_path(left, right), crops, labels, plants,
            np.concatenate([p[1] for p in parts], axis=1), np.concatenate([p[2] for p in parts], axis=1),
            {"left": left, "right": right},
        )

    def write_collage(self, left: str, right: str) -> Path:
        out = self.collage_path(left, right)
        if out.exists():  # SAM answers are cached by image bytes: never rewrite an existing collage
            return out
        a = np.array(Image.open(self.image_path(left)).convert("RGB"))
        b = np.array(Image.open(self.image_path(right)).convert("RGB"))
        if a.shape != b.shape:
            raise ValueError(f"{left} {a.shape} and {right} {b.shape} differ in size")
        w = a.shape[1]
        half, x = w // 2, (w - w // 2) // 2
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.concatenate([a[:, x : x + half], b[:, x : x + half]], axis=1)).save(out)
        return out


# ---------------------------------------------------------------------- selection


def image_stats(root: Path) -> dict[str, tuple[Counter, set[int]]]:
    out = {}
    for f in sorted((root / "bboxes").glob("*.csv")):
        boxes = read_boxes(root, f.stem)
        crops = Counter(CROP_IDS[b[4]] for b in boxes if b[4] in CROP_IDS)
        weeds = {b[4] for b in boxes if b[4] in WEED_IDS}
        out[f.stem] = (crops, weeds)
    return out


def select(root: Path, per_crop: int, n_collages: int, min_second: int, seed: int) -> dict:
    """A: `per_crop` one-crop photos per crop, most weed species first, spread over recording
    sessions. B-real: photos with two crops (3+ plants of the second one). B-collage: pairs of
    A photos of two different crops, every crop pair in turn."""
    rng = random.Random(seed)
    stats = image_stats(root)
    single: dict[str, list[str]] = {}
    for crop in CROPS:
        tiers: dict[int, list[str]] = {}
        for name, (crops, weeds) in stats.items():
            if set(crops) == {crop}:
                tiers.setdefault(min(len(weeds), 3), []).append(name)
        picked: list[str] = []
        for tier in (3, 2, 1, 0):
            by_session: dict[str, list[str]] = {}
            for name in sorted(tiers.get(tier, [])):
                by_session.setdefault(name[:8], []).append(name)
            sessions = sorted(by_session)
            rng.shuffle(sessions)
            for names in by_session.values():
                rng.shuffle(names)
            while len(picked) < per_crop and any(by_session.values()):
                for session in sessions:
                    if by_session[session] and len(picked) < per_crop:
                        picked.append(by_session[session].pop())
        single[crop] = picked
    two_crop = sorted(
        name for name, (crops, _) in stats.items() if len(crops) >= 2 and sorted(crops.values())[-2] >= min_second
    )
    pairs = [(a, b) for i, a in enumerate(CROPS) for b in CROPS[i + 1 :]]
    rng.shuffle(pairs)
    pools = {crop: list(names) for crop, names in single.items()}
    for names in pools.values():
        rng.shuffle(names)
    collages: list[list[str]] = []
    for k in range(len(pairs) * per_crop):
        if len(collages) >= n_collages:
            break
        a, b = pairs[k % len(pairs)]
        if pools[a] and pools[b]:
            collages.append([pools[a].pop(), pools[b].pop()])
    return {
        "dataset": "CropAndWeed",
        "seed": seed,
        "A": single,
        "B-real": two_crop,
        "B-collage": collages,
        "weed_species": {name: len(stats[name][1]) for names in single.values() for name in names},
    }


def load_selection() -> dict:
    if not SELECTION.exists():
        sys.exit(f"No selection yet: run `eval/cropandweed.py select` first ({SELECTION}).")
    return json.loads(SELECTION.read_text())


def selected_images(selection: dict) -> list[str]:
    names = {n for names in selection["A"].values() for n in names} | set(selection["B-real"])
    return sorted(names)


def download(root: Path, names: list[str]) -> list[str]:
    """Stream the four image archives (~3 GB each) and keep only `names`. Returns what is missing."""
    todo = [n for n in names if not (root / "images" / f"{n}.jpg").exists()]
    if not todo:
        return []
    listing = root / "wanted.txt"
    listing.write_text("".join(f"images/{n}.jpg\n" for n in todo))

    def fetch(part: str) -> int:
        # tar reports names it did not find in this part; that is expected (each part holds a quarter)
        cmd = f"curl -sSf --retry 3 '{URL}{part}.tar' | tar -x -f - -C '{root}' -T '{listing}' 2>/dev/null"
        return subprocess.run(cmd, shell=True).returncode

    print(f"downloading {len(todo)} images from {len(IMAGE_PARTS)} archives in parallel (~11 GB streamed, nothing else kept)")
    with ThreadPoolExecutor(max_workers=len(IMAGE_PARTS)) as pool:
        list(pool.map(fetch, IMAGE_PARTS))
    return [n for n in names if not (root / "images" / f"{n}.jpg").exists()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["select", "download", "collages"])
    ap.add_argument("--data", default=str(DATA_ROOT))
    ap.add_argument("--per-crop", type=int, default=20)
    ap.add_argument("--collages", type=int, default=40)
    ap.add_argument("--min-second", type=int, default=3, help="B-real: plants of the second crop")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    root = Path(args.data)

    if args.command == "select":
        sel = select(root, args.per_crop, args.collages, args.min_second, args.seed)
        SELECTION.parent.mkdir(parents=True, exist_ok=True)
        SELECTION.write_text(json.dumps(sel, indent=1))
        print(f"A: {sum(len(v) for v in sel['A'].values())} one-crop photos ({', '.join(f'{c} {len(v)}' for c, v in sel['A'].items())})")
        tiers = Counter(min(v, 3) for v in sel["weed_species"].values())
        print(f"   weed species per photo: 3+: {tiers[3]}, 2: {tiers[2]}, 1: {tiers[1]}, 0: {tiers[0]}")
        print(f"B-real: {len(sel['B-real'])} two-crop photos; B-collage: {len(sel['B-collage'])} collages")
        print(f"-> {SELECTION}")
    elif args.command == "download":
        missing = download(root, selected_images(load_selection()))
        if missing:
            sys.exit(f"{len(missing)} images missing after download, e.g. {missing[:3]}")
        print("all selected images present")
    else:
        dataset = CropAndWeed(root)
        pairs = load_selection()["B-collage"]
        for left, right in pairs:
            dataset.write_collage(left, right)
        print(f"{len(pairs)} collages in {root / 'collages'}")


if __name__ == "__main__":
    main()
