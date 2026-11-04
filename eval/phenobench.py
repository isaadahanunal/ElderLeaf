"""PhenoBench loader + ground-truth instance extraction.

Dataset: Weyler et al., "PhenoBench", IEEE TPAMI 2024 (arXiv 2306.04557).
License: website says CC BY-SA 4.0, the v1.1.0 zip README says CC BY-NC-SA 4.0; we follow
the stricter one (non-commercial use, attribution, share-alike).
Layout after unzipping into data/:

    data/PhenoBench/{train,val}/{images,semantics,plant_instances,leaf_instances,
                                 plant_visibility,leaf_visibility}/<name>.png

semantics: 0 background, 1 crop, 2 weed, 3 partial crop, 4 partial weed.
Visibility maps are 0..255 per pixel (255 = fully visible); we take the median over
each instance's pixels as that instance's visibility in [0, 1].

What visibility means here (checked on 837 val plants): it is the share of the plant that
lies inside this 1024x1024 tile. Images are tiles of a larger field mosaic, so plants on the
tile edge are cut off. 99.6% of plants with visibility < 1 touch the image border, and
"partial" == visibility < 0.5 exactly. It does NOT measure occlusion by other plants (top-down
labels can't see hidden leaves). For crowding we count touching neighbours instead
(``GTInstance.neighbours``: other plants within 2 px of this one).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

SEM_CLASSES = {1: "crop", 2: "weed", 3: "crop", 4: "weed"}
SEM_PARTIAL = {3, 4}
SUBDIRS = ("images", "semantics", "plant_instances", "leaf_instances", "plant_visibility", "leaf_visibility")


def find_root(path: str | Path) -> Path:
    """Accept data/, data/PhenoBench or the split parent; return the dir holding train/ and val/."""
    path = Path(path)
    for candidate in (path, path / "PhenoBench", *path.glob("*/")):
        if (candidate / "train" / "images").is_dir() or (candidate / "val" / "images").is_dir():
            return candidate
    raise FileNotFoundError(
        f"No PhenoBench split found under {path}. Expected <root>/val/images/*.png "
        "(unzip PhenoBench-v110.zip into data/)."
    )


def date_of(name: str) -> str:
    """Filenames start with the capture date, e.g. 05-15_00028_P0030852.png -> '05-15'."""
    return name[:5]


@dataclass
class GTInstance:
    id: int  # dense id in the instance label map (1..N)
    cls: str  # crop | weed | leaf
    partial: bool
    area: int
    visibility: float  # 0..1, share of the object inside the image
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 half-open
    neighbours: int = 0  # other plants touching this one (plants only)


@dataclass
class GTSet:
    labels: np.ndarray  # int32 (H, W), 0 = none, else GTInstance.id
    instances: list[GTInstance]

    def by_id(self) -> dict[int, GTInstance]:
        return {inst.id: inst for inst in self.instances}


@dataclass
class Sample:
    split: str
    name: str
    image_path: Path
    semantics: np.ndarray
    plants: GTSet
    leaves: GTSet

    @property
    def date(self) -> str:
        return date_of(self.name)

    @property
    def shape(self) -> tuple[int, int]:
        return self.semantics.shape


class PhenoBench:
    def __init__(self, root: str | Path) -> None:
        self.root = find_root(root)

    def names(self, split: str) -> list[str]:
        return sorted(p.name for p in (self.root / split / "images").glob("*.png"))

    def image_path(self, split: str, name: str) -> Path:
        return self.root / split / "images" / name

    def _read(self, split: str, sub: str, name: str) -> np.ndarray | None:
        path = self.root / split / sub / name
        return np.array(Image.open(path)) if path.exists() else None

    def load(self, split: str, name: str) -> Sample:
        semantics = self._read(split, "semantics", name)
        if semantics is None:
            raise FileNotFoundError(f"No labels for {split}/{name} (test split has none).")
        semantics = semantics.astype(np.int32)
        plant_ids = self._read(split, "plant_instances", name)
        plant_vis = self._read(split, "plant_visibility", name)
        leaf_ids = self._read(split, "leaf_instances", name)
        leaf_vis = self._read(split, "leaf_visibility", name)
        plants = _plant_instances(plant_ids, semantics, plant_vis)
        leaves = _leaf_instances(leaf_ids, leaf_vis) if leaf_ids is not None else GTSet(np.zeros_like(semantics), [])
        return Sample(split, name, self.image_path(split, name), semantics, plants, leaves)


def _dense(ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Relabel arbitrary instance ids to 1..N. Returns (dense_map, original_ids)."""
    originals, inverse = np.unique(ids, return_inverse=True)
    dense = inverse.reshape(ids.shape).astype(np.int32)
    if originals[0] != 0:  # no background pixels at all
        dense += 1
        return dense, originals
    return dense, originals[1:]


def _visibility(vis: np.ndarray | None, labels: np.ndarray, n: int) -> np.ndarray:
    if vis is None or n == 0:
        return np.ones(n)
    index = np.arange(1, n + 1)
    return np.asarray(ndimage.median(vis.astype(np.float32), labels, index)) / 255.0


def _boxes(labels: np.ndarray, n: int) -> list[tuple[int, int, int, int]]:
    out = []
    for sl in ndimage.find_objects(labels, max_label=n):
        if sl is None:
            out.append((0, 0, 0, 0))
        else:
            out.append((sl[1].start, sl[0].start, sl[1].stop, sl[0].stop))
    return out


def _touching_neighbours(labels: np.ndarray, boxes: list[tuple[int, int, int, int]], radius: int = 2) -> list[int]:
    """For each instance, how many other instances lie within ``radius`` px of it."""
    h, w = labels.shape
    kernel = np.ones((2 * radius + 1, 2 * radius + 1), np.uint8)
    out = []
    for i, (x0, y0, x1, y1) in enumerate(boxes, start=1):
        X0, Y0, X1, Y1 = max(x0 - radius, 0), max(y0 - radius, 0), min(x1 + radius, w), min(y1 + radius, h)
        region = labels[Y0:Y1, X0:X1]
        grown = cv2.dilate((region == i).astype(np.uint8), kernel) > 0
        others = np.unique(region[grown])
        out.append(int(np.count_nonzero((others != 0) & (others != i))))
    return out


def _plant_instances(ids: np.ndarray | None, semantics: np.ndarray, vis: np.ndarray | None) -> GTSet:
    if ids is None:
        return GTSet(np.zeros_like(semantics), [])
    ids = np.where(semantics > 0, ids.astype(np.int64), 0)
    labels, _ = _dense(ids)
    n = int(labels.max())
    areas = np.bincount(labels.ravel(), minlength=n + 1)
    # majority semantic class per instance
    combo = np.bincount(labels.ravel() * 8 + semantics.ravel(), minlength=(n + 1) * 8).reshape(n + 1, 8)
    majority = combo.argmax(axis=1)
    visibility = _visibility(vis, labels, n)
    boxes = _boxes(labels, n)
    neighbours = _touching_neighbours(labels, boxes)
    instances = []
    for i in range(1, n + 1):
        sem = int(majority[i])
        if sem not in SEM_CLASSES:
            continue
        instances.append(
            GTInstance(
                i, SEM_CLASSES[sem], sem in SEM_PARTIAL, int(areas[i]), float(visibility[i - 1]), boxes[i - 1], neighbours[i - 1]
            )
        )
    return GTSet(labels, instances)


def _leaf_instances(ids: np.ndarray, vis: np.ndarray | None) -> GTSet:
    labels, _ = _dense(ids.astype(np.int64))
    n = int(labels.max())
    areas = np.bincount(labels.ravel(), minlength=n + 1)
    visibility = _visibility(vis, labels, n)
    boxes = _boxes(labels, n)
    instances = [
        GTInstance(i, "leaf", False, int(areas[i]), float(visibility[i - 1]), boxes[i - 1]) for i in range(1, n + 1)
    ]
    return GTSet(labels, instances)
