"""Measure SAM 3.1 against PhenoBench ground truth.

Reads cached SAM answers only (run run_sam.py first); calls no API.

Two levels:
  1. SAM itself (instance level): each prompt's masks are matched one-to-one to GT
     instances at IoU >= 0.5. Precision / recall / F1, then recall broken down by
     **visibility** (occlusion), growth stage (date), plant size and partial plants.
  2. ElderLeaf product metrics (image level): the real pipeline (cleanup ->
     crop/weed conflict resolution -> class map) vs GT: plant count, canopy cover,
     weed share, pixel IoU.

    uv run --project api python eval/evaluate.py --run val --threshold 0.5 --viz 6
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np

from common import CACHE_DIR, IOU_MATCH, RESULTS_DIR, SIZE_BINS, THRESHOLDS, VIS_BINS, bin_label
from elderleaf.masks import DEFAULT_MIN_AREA_FRAC, class_map, clean_instances, resolve_cross_class
from elderleaf.sam import PRICE_PER_IMAGE_USD, CacheMiss, SamClient
from phenobench import PhenoBench, Sample

# =============================================================== per image (worker processes)


def _pairs(instances, gt_labels: np.ndarray, gt_areas: np.ndarray) -> list[tuple[float, int, int]]:
    """(iou, pred_idx, gt_id) for every overlapping pred/GT pair."""
    out = []
    for p, inst in enumerate(instances):
        x0, y0, x1, y1 = inst.box
        region = gt_labels[y0:y1, x0:x1][inst.mask]
        if region.size == 0:
            continue
        inter = np.bincount(region)
        for g in np.nonzero(inter)[0]:
            if g == 0:
                continue
            i = int(inter[g])
            out.append((i / (inst.area + int(gt_areas[g]) - i), p, int(g)))
    return out


def _inter_union(pred: np.ndarray, gt: np.ndarray) -> tuple[int, int]:
    return int(np.logical_and(pred, gt).sum()), int(np.logical_or(pred, gt).sum())


def _product_metrics(sample: Sample, segs: dict, prompts: dict[str, str], thr: float, min_area_frac: float) -> dict:
    """Image-level numbers as the product computes them. Canopy = crop cover (weeds excluded)."""
    h, w = sample.shape
    sem = sample.semantics
    gt_veg, gt_crop, gt_weed = sem > 0, np.isin(sem, (1, 3)), np.isin(sem, (2, 4))
    gt_crop_cover = float(gt_crop.mean() * 100)
    gt_weed_share = float(gt_weed.sum() / gt_veg.sum() * 100) if gt_veg.any() else 0.0
    n_crop = sum(1 for g in sample.plants.instances if g.cls == "crop")
    n_crop_whole = sum(1 for g in sample.plants.instances if g.cls == "crop" and not g.partial)

    results = {}
    crop_prompts = [p for p, t in prompts.items() if t == "crop" and p in segs]
    weed_prompts = [p for p, t in prompts.items() if t == "weed" and p in segs]
    for crop_prompt in crop_prompts:
        if not weed_prompts:
            break
        weed_prompt = weed_prompts[0]
        crop = clean_instances(segs[crop_prompt].instances, h * w, thr, min_area_frac)
        weed = clean_instances(segs[weed_prompt].instances, h * w, thr, min_area_frac)
        resolved = resolve_cross_class({"crop": crop, "weed": weed}, priority=["crop", "weed"])  # as the app does
        labels = class_map({1: resolved["crop"], 2: resolved["weed"]}, h, w, priority=[1, 2])
        pred_veg = labels > 0
        results[f"{crop_prompt} + {weed_prompt}"] = {
            "count_pred": len(resolved["crop"]),
            "count_gt": n_crop,
            "count_gt_whole": n_crop_whole,
            "canopy_pred": float((labels == 1).mean() * 100),
            "canopy_gt": gt_crop_cover,
            "weed_share_pred": float((labels == 2).sum() / pred_veg.sum() * 100) if pred_veg.any() else 0.0,
            "weed_share_gt": gt_weed_share,
            "iu_veg": _inter_union(pred_veg, gt_veg),
            "iu_crop": _inter_union(labels == 1, gt_crop),
            "iu_weed": _inter_union(labels == 2, gt_weed),
        }

    # Experiment: crop cover from leaf masks instead of whole-plant masks.
    # "all leaves" also catches weed leaves; "∩ crop" keeps only leaves inside crop-plant masks.
    for leaf_prompt in [p for p, t in prompts.items() if t == "leaf" and p in segs]:
        leaves = clean_instances(segs[leaf_prompt].instances, h * w, thr, min_area_frac=0.0)
        leaf_px = class_map({1: leaves}, h, w) > 0
        results[f"{leaf_prompt} (all leaves)"] = {
            "canopy_pred": float(leaf_px.mean() * 100),
            "canopy_gt": gt_crop_cover,
            "iu_crop": _inter_union(leaf_px, gt_crop),
        }
        if crop_prompts:
            crop = clean_instances(segs[crop_prompts[0]].instances, h * w, thr, min_area_frac)
            inside = leaf_px & (class_map({1: crop}, h, w) > 0)
            results[f"{leaf_prompt} ∩ {crop_prompts[0]}"] = {
                "canopy_pred": float(inside.mean() * 100),
                "canopy_gt": gt_crop_cover,
                "iu_crop": _inter_union(inside, gt_crop),
            }

    # Diagnostic: one generic "plant" prompt for all green (crop + weed)
    for plant_prompt in [p for p, t in prompts.items() if t == "plant" and p in segs]:
        plants = clean_instances(segs[plant_prompt].instances, h * w, thr, min_area_frac)
        pred_veg = class_map({1: plants}, h, w) > 0
        results[f"{plant_prompt} (all green vs GT crop+weed)"] = {
            "count_pred": len(plants),
            "count_gt": len(sample.plants.instances),
            "canopy_pred": float(pred_veg.mean() * 100),
            "canopy_gt": float(gt_veg.mean() * 100),
            "iu_veg": _inter_union(pred_veg, gt_veg),
        }
    return results


def analyze_image(job: tuple) -> dict:
    data_root, split, name, prompts, thr, min_area_frac = job
    sample = PhenoBench(data_root).load(split, name)
    client = SamClient(cache_dir=CACHE_DIR)
    plant_areas = np.bincount(sample.plants.labels.ravel())
    leaf_areas = np.bincount(sample.leaves.labels.ravel())
    out = {
        "name": name,
        "date": sample.date,
        "plants": [asdict(g) for g in sample.plants.instances],
        "leaves": [asdict(g) for g in sample.leaves.instances],
        "prompts": {},
        "missing": [],
    }
    segs = {}
    for prompt, target in prompts.items():
        try:
            seg = client.segment(sample.image_path, prompt, offline=True)
        except CacheMiss:
            out["missing"].append(prompt)
            continue
        segs[prompt] = seg
        gt = sample.leaves if target == "leaf" else sample.plants
        areas = leaf_areas if target == "leaf" else plant_areas
        out["prompts"][prompt] = {
            "preds": [{"score": inst.score_or_one, "area": inst.area} for inst in seg.instances],
            "pairs": _pairs(seg.instances, gt.labels, areas),
            "latency_s": seg.meta.get("latency_s"),
            "diagnostics": seg.diagnostics,
        }
    out["product"] = _product_metrics(sample, segs, prompts, thr, min_area_frac)
    return out


# =============================================================== matching + aggregation


def greedy_match(pairs, keep: list[bool], eligible: set[int], iou_thr: float = IOU_MATCH) -> dict[int, tuple[int, float]]:
    """One-to-one matching, highest IoU first. Returns {gt_id: (pred_idx, iou)}."""
    used: set[int] = set()
    matches: dict[int, tuple[int, float]] = {}
    for iou, p, g in sorted(pairs, reverse=True):
        if iou < iou_thr:
            break
        if p in used or g in matches or not keep[p] or g not in eligible:
            continue
        used.add(p)
        matches[g] = (p, iou)
    return matches


def _gt_for(img: dict, target: str) -> tuple[list[dict], set[int], set[int]]:
    gts = img["leaves"] if target == "leaf" else img["plants"]
    if target in ("plant", "leaf"):
        return gts, {g["id"] for g in gts}, set()
    return gts, {g["id"] for g in gts if g["cls"] == target}, {g["id"] for g in gts if g["cls"] != target}


def evaluate_prompt(images: list[dict], prompt: str, target: str, thr: float, rows: list | None = None) -> dict:
    tp = fp = fn = confused = 0
    ious: list[float] = []
    count_err: list[int] = []
    for img in images:
        rec = img["prompts"].get(prompt)
        if rec is None:
            continue
        gts, eligible, other = _gt_for(img, target)
        keep = [p["score"] >= thr for p in rec["preds"]]
        matches = greedy_match(rec["pairs"], keep, eligible)
        matched_preds = {p for p, _ in matches.values()}
        leftover = [k and i not in matched_preds for i, k in enumerate(keep)]
        if other:
            confused += len(greedy_match(rec["pairs"], leftover, other))
        tp += len(matches)
        fp += sum(leftover)
        fn += len(eligible) - len(matches)
        ious += [iou for _, iou in matches.values()]
        count_err.append(sum(keep) - len(eligible))
        if rows is not None:
            best: dict[int, float] = defaultdict(float)
            for iou, p, g in rec["pairs"]:
                if keep[p]:
                    best[g] = max(best[g], iou)
            for g in gts:
                if g["id"] in eligible:
                    rows.append(
                        {
                            "prompt": prompt,
                            "target": target,
                            "image": img["name"],
                            "date": img["date"],
                            "gt_id": g["id"],
                            "gt_class": g["cls"],
                            "partial": g["partial"],
                            "area_px": g["area"],
                            "visibility": round(g["visibility"], 3),
                            "neighbours": g.get("neighbours", 0),
                            "matched": g["id"] in matches,
                            "iou": round(matches[g["id"]][1], 3) if g["id"] in matches else "",
                            "best_iou": round(best[g["id"]], 3),
                        }
                    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "prompt": prompt,
        "target": target,
        "threshold": thr,
        "gt": tp + fn,
        "pred": tp + fp,
        "tp": tp,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "mean_iou_tp": statistics.fmean(ious) if ious else 0.0,
        "count_mae": statistics.fmean(abs(e) for e in count_err) if count_err else 0.0,
        "count_bias": statistics.fmean(count_err) if count_err else 0.0,
        "fp_other_class": confused,
    }


def breakdown(rows: list[dict], key) -> list[tuple[str, int, float, float]]:
    """[(group, n_gt, recall, mean_iou_of_matched)] sorted by group."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    out = []
    for name in sorted(groups):
        rs = groups[name]
        matched = [r["iou"] for r in rs if r["matched"]]
        out.append((name, len(rs), len(matched) / len(rs), statistics.fmean(matched) if matched else 0.0))
    return out


# =============================================================== reporting


def md_table(headers: list[str], rows: list[list]) -> str:
    def fmt(v):
        return f"{v:.3f}" if isinstance(v, float) else str(v)

    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def breakdown_table(rows: list[dict], prompts: dict[str, str], key, title: str) -> str:
    per_prompt = {p: dict((g, (n, r, i)) for g, n, r, i in breakdown([x for x in rows if x["prompt"] == p], key)) for p in prompts}
    groups = sorted({g for d in per_prompt.values() for g in d})
    table_rows = []
    for g in groups:
        row = [g]
        for p in prompts:
            n, r, i = per_prompt[p].get(g, (0, 0.0, 0.0))
            row.append(f"{r:.2f} / {i:.2f} (n={n})" if n else "–")
        table_rows.append(row)
    return f"{title}\n\n" + md_table(["group", *[f"`{p}`" for p in prompts]], table_rows)


def _vis_key(r):
    return bin_label(r["visibility"], VIS_BINS)


def _size_key(r):
    return bin_label(r["area_px"], SIZE_BINS)


def _crowding_key(r):
    n = r["neighbours"]
    return "0 (isolated)" if n == 0 else ("1" if n == 1 else "2+")


def product_summary(images: list[dict]) -> tuple[str, list[dict], dict]:
    by_combo: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    image_rows = []
    for img in images:
        for combo, m in img["product"].items():
            by_combo[combo].append((img["date"], m))
            image_rows.append({"image": img["name"], "date": img["date"], "pipeline": combo, **{k: v for k, v in m.items() if not k.startswith("iu_")}})

    def stats(entries: list[dict]) -> dict:
        def iou(key):
            inter = sum(m[key][0] for m in entries if key in m)
            union = sum(m[key][1] for m in entries if key in m)
            return inter / union if union else float("nan")

        out = {
            "images": len(entries),
            "canopy_mae_pts": statistics.fmean(abs(m["canopy_pred"] - m["canopy_gt"]) for m in entries),
        }
        if "count_pred" in entries[0]:
            out["count_mae"] = statistics.fmean(abs(m["count_pred"] - m["count_gt"]) for m in entries)
            out["count_bias"] = statistics.fmean(m["count_pred"] - m["count_gt"] for m in entries)
        if "weed_share_pred" in entries[0]:
            out["weed_share_mae_pts"] = statistics.fmean(abs(m["weed_share_pred"] - m["weed_share_gt"]) for m in entries)
        for key in ("veg", "crop", "weed"):
            if f"iu_{key}" in entries[0]:
                out[f"iou_{key}"] = iou(f"iu_{key}")
        return out

    sections, summary = [], {}
    for combo, entries in by_combo.items():
        overall = stats([m for _, m in entries])
        summary[combo] = overall
        dates = sorted({d for d, _ in entries})
        rows = [["all", *[overall.get(k, "") for k in _PRODUCT_COLS]]]
        for d in dates:
            s = stats([m for dd, m in entries if dd == d])
            rows.append([d, *[s.get(k, "") for k in _PRODUCT_COLS]])
        sections.append(f"**Pipeline `{combo}`**\n\n" + md_table(["date", *_PRODUCT_COLS], rows))
    return "\n\n".join(sections), image_rows, summary


_PRODUCT_COLS = ["images", "count_mae", "count_bias", "canopy_mae_pts", "weed_share_mae_pts", "iou_veg", "iou_crop", "iou_weed"]


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# =============================================================== visualization


def save_viz(dataset: PhenoBench, split: str, img: dict, prompts: dict[str, str], thr: float, out_dir: Path) -> None:
    import cv2
    from PIL import Image

    sample = dataset.load(split, img["name"])
    client = SamClient(cache_dir=CACHE_DIR)
    rgb = np.array(Image.open(sample.image_path).convert("RGB"))
    colors = {"crop": (40, 200, 60), "weed": (255, 0, 200)}

    gt_view = rgb.copy()
    for g in sample.plants.instances:
        m = (sample.plants.labels == g.id).astype(np.uint8)
        contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(gt_view, contours, -1, colors[g.cls], 2)

    # prediction panel: first crop prompt filled green, first weed prompt filled magenta,
    # GT crops the crop prompt missed outlined in yellow
    pred_view = rgb.copy()
    first = {t: next((p for p, tt in prompts.items() if tt == t and p in img["prompts"]), None) for t in colors}
    for target, prompt in first.items():
        if prompt is None:
            continue
        seg = client.segment(sample.image_path, prompt, offline=True)
        for inst in seg.instances:
            if inst.score_or_one < thr:
                continue
            x0, y0, x1, y1 = inst.box
            region = pred_view[y0:y1, x0:x1]
            blended = rgb[y0:y1, x0:x1][inst.mask] * 0.4 + np.array(colors[target]) * 0.6
            region[inst.mask] = blended.astype(np.uint8)
    if first["crop"]:
        rec = img["prompts"][first["crop"]]
        _, eligible, _ = _gt_for(img, "crop")
        matched = greedy_match(rec["pairs"], [p["score"] >= thr for p in rec["preds"]], eligible)
        for gt_id in eligible - set(matched):
            m = (sample.plants.labels == gt_id).astype(np.uint8)
            contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(pred_view, contours, -1, (255, 220, 0), 3)

    canvas = np.concatenate([gt_view, np.full((rgb.shape[0], 12, 3), 255, np.uint8), pred_view], axis=1)
    for text, x in (("ground truth", 12), ("SAM 3.1 (yellow = missed crop)", rgb.shape[1] + 24)):
        cv2.putText(canvas, text, (x, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3, cv2.LINE_AA)
    out_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(canvas).save(out_dir / img["name"])


# =============================================================== main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--data", default=None, help="override data root from the manifest")
    ap.add_argument("--threshold", type=float, default=0.5, help="SAM confidence threshold for breakdowns/product")
    ap.add_argument("--min-area-frac", type=float, default=DEFAULT_MIN_AREA_FRAC)
    ap.add_argument("--viz", type=int, default=0, help="save side-by-side images for the N worst count errors")
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 2))
    args = ap.parse_args()

    run_dir = RESULTS_DIR / args.run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    dataset = PhenoBench(args.data or manifest["data_root"])
    prompts: dict[str, str] = manifest["prompts"]
    split = manifest["split"]

    jobs = [(str(dataset.root), split, n, prompts, args.threshold, args.min_area_frac) for n in manifest["images"]]
    print(f"Evaluating {len(jobs)} images x {len(prompts)} prompts with {args.workers} workers...")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        images = list(pool.map(analyze_image, jobs, chunksize=2))

    missing = sum(len(i["missing"]) for i in images)
    if missing:
        print(f"WARNING: {missing} (image, prompt) pairs not cached; run run_sam.py again. They are skipped.")

    # ---- 1. SAM instance level
    sweep = [evaluate_prompt(images, p, t, thr) for p, t in prompts.items() for thr in THRESHOLDS]
    main_rows: list[dict] = []
    headline = [evaluate_prompt(images, p, t, args.threshold, rows=main_rows) for p, t in prompts.items()]
    # highest threshold among ties: SAM returns nothing below ~0.5, so 0.0-0.5 often tie and 0.5 is the honest value
    best_thr = {
        p: max((s for s in sweep if s["prompt"] == p), key=lambda s: (round(s["f1"], 6), s["threshold"])) for p in prompts
    }

    # ---- 2. product level
    product_md, image_rows, product_stats = product_summary(images)

    # ---- write
    write_csv(run_dir / "threshold_sweep.csv", sweep)
    write_csv(run_dir / "gt_matches.csv", main_rows)
    write_csv(run_dir / "images.csv", image_rows)

    latencies = sorted(v["latency_s"] for i in images for v in i["prompts"].values() if v.get("latency_s"))
    dates = sorted({i["date"] for i in images})
    n_requests = sum(len(i["prompts"]) for i in images)
    plant_rows = [r for r in main_rows if r["target"] != "leaf"]

    md = [
        f"# SAM 3.1 on PhenoBench: run `{args.run}`",
        "",
        f"- Split **{split}**, {len(images)} images, capture dates {', '.join(dates)}",
        f"- Prompts: {', '.join(f'`{p}` → {t}' for p, t in prompts.items())}",
        f"- Match rule: one-to-one, IoU ≥ {IOU_MATCH}. Confidence threshold **{args.threshold}**; "
        f"product cleanup also drops masks < {args.min_area_frac * 100:.2f}% of the image.",
        f"- {n_requests} SAM requests (~${n_requests * PRICE_PER_IMAGE_USD:.2f}); "
        + (f"median latency {latencies[len(latencies) // 2]:.2f}s" if latencies else "latency n/a"),
        "",
        "## 1. Instance detection per prompt",
        "",
        md_table(
            ["prompt", "target", "GT", "pred", "precision", "recall", "F1", "mean IoU (TP)", "count MAE/img", "count bias/img", "FP = other class", "best thr (F1)"],
            [
                [f"`{h['prompt']}`", h["target"], h["gt"], h["pred"], h["precision"], h["recall"], h["f1"], h["mean_iou_tp"], h["count_mae"], h["count_bias"], h["fp_other_class"], f"{best_thr[h['prompt']]['threshold']:g} (F1 {best_thr[h['prompt']]['f1']:.2f})" if best_thr[h["prompt"]]["f1"] > 0 else "– (finds nothing)"]
                for h in headline
            ],
        ),
        "",
        "Cells below are **recall / mean IoU of matched (n = GT instances)**.",
        "",
        breakdown_table(
            main_rows,
            prompts,
            _vis_key,
            "## 2. By visibility (share of the object inside the image; low = cut off at the photo edge)",
        ),
        "",
        breakdown_table(main_rows, prompts, lambda r: r["date"], "## 3. By growth stage (capture date)"),
        "",
        breakdown_table(main_rows, prompts, _size_key, "## 4. By object size (px; product cleanup drops < ~210 px)"),
        "",
        breakdown_table(
            plant_rows,
            {p: t for p, t in prompts.items() if t != "leaf"},
            _crowding_key,
            "## 5. By crowding (number of other plants touching this one)",
        ),
        "",
        "## 6. ElderLeaf product metrics (image level)",
        "",
        "Count = crop masks after cleanup and crop/weed conflict resolution vs GT crop instances. "
        "Canopy = **crop cover** (crop pixels / image, weeds excluded) vs GT crop pixels; errors in percentage points. "
        "The `leaf` rows test computing crop cover from leaf masks instead of whole-plant masks. "
        "IoU is pixel IoU pooled over all images.",
        "",
        product_md,
        "",
        "## Files",
        "",
        "- `threshold_sweep.csv`: precision/recall/F1/count error per prompt and threshold",
        "- `gt_matches.csv`: one row per GT instance per prompt (visibility, crowding, size, date, matched, IoU)",
        "- `images.csv`: product metrics per image",
        "",
        "Data: PhenoBench (Weyler et al., IEEE TPAMI 2024), CC BY-NC-SA 4.0 per the v1.1.0 release README.",
    ]
    (run_dir / "summary.md").write_text("\n".join(md))
    (run_dir / "summary.json").write_text(
        json.dumps({"threshold": args.threshold, "prompts": headline, "best_threshold": best_thr, "product": product_stats}, indent=2)
    )

    if args.viz:
        crop_prompt = next((p for p, t in prompts.items() if t == "crop"), None)
        if crop_prompt:
            combo = next((c for c in images[0]["product"] if c.startswith(crop_prompt)), None)
            ranked = sorted(images, key=lambda i: -abs(i["product"].get(combo, {}).get("count_pred", 0) - i["product"].get(combo, {}).get("count_gt", 0)))
            for img in ranked[: args.viz]:
                save_viz(dataset, split, img, prompts, args.threshold, run_dir / "viz")
            print(f"Saved {min(args.viz, len(ranked))} side-by-side images to {run_dir / 'viz'}")

    print((run_dir / "summary.md").read_text().split("## 2.")[0])
    print(f"Full report: {run_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
