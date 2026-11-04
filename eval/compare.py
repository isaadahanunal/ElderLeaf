"""Fixed words vs the prompt agent on the same images: accuracy, cost and time.

Systems (crop word; weeds always "weed" for the fixed ones):
  fixed "plant"             the most basic word: every plant counts as crop
  fixed "crop plant"        generic crop word
  fixed "sugar beet plant"  the crop's name
  agent                     Muse Spark proposes 3 ranked phrases per target; first confident answer wins,
                            then the plain word ("plant", "weed", "leaf")
Leaf experiment: fixed "leaf", fixed "sugar beet leaf", agent.

    uv run --project api python eval/compare.py --run val --provider baseten

Needs SAM answers cached for both systems: run_sam.py (with "crop plant", "sugar beet plant", "weed")
and run_agent.py for the same run. Makes no API calls.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from common import CACHE_DIR, RESULTS_DIR
from elderleaf.masks import class_map, clean_instances, resolve_cross_class
from elderleaf.sam import PRICE_PER_IMAGE_USD, CacheMiss, SamClient
from evaluate import _pairs, greedy_match, md_table
from phenobench import PhenoBench

FIXED_SYSTEMS = {
    'fixed "plant"': "plant",
    'fixed "crop plant"': "crop plant",
    'fixed "sugar beet plant"': "sugar beet plant",
}
WEED_PROMPT = "weed"
# leaf experiment: fixed words vs the agent's leaf phrase
LEAF_FIXED_SYSTEMS = {'fixed "leaf"': "leaf", 'fixed "sugar beet leaf"': "sugar beet leaf"}
# what happens when the same plant is found as crop and as weed
CONFLICT_RULES = {"score": (None, None), "crop-first": (["crop", "weed"], [1, 2])}


def _match(instances, gt, cls: str, thr: float) -> tuple[int, int, int]:
    eligible = {g.id for g in gt.instances if g.cls == cls}
    keep = [i.score_or_one >= thr for i in instances]
    matches = greedy_match(_pairs(instances, gt.labels, np.bincount(gt.labels.ravel())), keep, eligible)
    tp = len(matches)
    return tp, sum(keep) - tp, len(eligible) - tp


def _rounds_wait(attempts: list[dict]) -> float:
    """SAM waiting time: calls of one round run in parallel, rounds one after another."""
    rounds: dict[int, float] = {}
    for x in attempts:
        rounds[x["round"]] = max(rounds.get(x["round"], 0.0), x.get("latency_s") or 0.0)
    return sum(rounds.values())


def score_image(job: tuple) -> dict:
    data_root, split, name, thr, systems, leaf_systems = job
    sample = PhenoBench(data_root).load(split, name)
    client = SamClient(cache_dir=CACHE_DIR)
    h, w = sample.shape
    sem = sample.semantics
    gt_veg, gt_crop, gt_weed = sem > 0, np.isin(sem, (1, 3)), np.isin(sem, (2, 4))
    n_crop_gt = sum(1 for g in sample.plants.instances if g.cls == "crop")
    decoded: dict[str, object] = {}

    def seg_for(prompt: str):  # decode each answer once per image (several systems share "weed")
        if prompt not in decoded:
            decoded[prompt] = client.segment(sample.image_path, prompt, offline=True)
        return decoded[prompt]

    rows = []
    for system, spec in systems.items():
        try:
            crop_seg = seg_for(spec["crop"])
            weed_seg = seg_for(spec["weed"])
        except CacheMiss as exc:
            rows.append({"image": name, "system": system, "missing": str(exc)})
            continue
        ctp, cfp, cfn = _match(crop_seg.instances, sample.plants, "crop", thr)
        wtp, wfp, wfn = _match(weed_seg.instances, sample.plants, "weed", thr)
        crop = clean_instances(crop_seg.instances, h * w, thr)
        weed = clean_instances(weed_seg.instances, h * w, thr)
        if "agent" in spec:
            a = spec["agent"]
            llm = a["llm"] or {}
            crop_weed = [x for x in a["attempts"] if x["target"] in ("crop", "weed")]  # leaves are separate
            sam_calls, sam_wait = len(crop_weed), _rounds_wait(crop_weed)
            llm_cost = llm.get("cost_usd")
            tokens_in, tokens_out, llm_wait = llm.get("input_tokens", 0), llm.get("output_tokens", 0), llm.get("latency_s", 0.0)
            crop_rank, weed_rank = (a["chosen"][t]["rank"] if a["chosen"][t] else None for t in ("crop", "weed"))
        else:
            sam_calls = 2
            sam_wait = max(crop_seg.meta.get("latency_s") or 0.0, weed_seg.meta.get("latency_s") or 0.0)
            llm_cost, tokens_in, tokens_out, llm_wait = 0.0, 0, 0, 0.0
            crop_rank = weed_rank = None
        sam_dollars = sam_calls * PRICE_PER_IMAGE_USD
        for rule, (class_priority, label_priority) in CONFLICT_RULES.items():
            resolved = resolve_cross_class({"crop": crop, "weed": weed}, priority=class_priority)
            labels = class_map({1: resolved["crop"], 2: resolved["weed"]}, h, w, priority=label_priority)
            veg = labels > 0
            rows.append(
                {
                    "image": name,
                    "date": sample.date,
                    "system": system,
                    "rule": rule,
                    "crop_prompt": spec["crop"],
                    "weed_prompt": spec["weed"],
                    "crop_rank": crop_rank,
                    "weed_rank": weed_rank,
                    "crop_tp": ctp,
                    "crop_fp": cfp,
                    "crop_fn": cfn,
                    "weed_tp": wtp,
                    "weed_fp": wfp,
                    "weed_fn": wfn,
                    "count_pred": len(resolved["crop"]),
                    "count_gt": n_crop_gt,
                    "cover_pred": float((labels == 1).mean() * 100),
                    "cover_gt": float(gt_crop.mean() * 100),
                    "weed_share_pred": float((labels == 2).sum() / veg.sum() * 100) if veg.any() else 0.0,
                    "weed_share_gt": float(gt_weed.sum() / gt_veg.sum() * 100) if gt_veg.any() else 0.0,
                    "sam_calls": sam_calls,
                    "sam_cost_usd": sam_dollars,
                    "llm_cost_usd": llm_cost,
                    "total_cost_usd": None if llm_cost is None else sam_dollars + llm_cost,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "latency_s": (llm_wait or 0.0) + sam_wait,
                }
            )

    # leaf experiment: fixed "leaf" vs the agent's leaf phrase, against PhenoBench's sugar beet leaves
    leaf_rows = []
    for system, spec in leaf_systems.items():
        try:
            seg = seg_for(spec["leaf"])
        except CacheMiss as exc:
            leaf_rows.append({"image": name, "system": system, "missing": str(exc)})
            continue
        tp, fp, fn = _match(seg.instances, sample.leaves, "leaf", thr)
        kept = [i for i in seg.instances if i.score_or_one >= thr]
        on_weed = sum(1 for i in kept if gt_weed[i.box[1] : i.box[3], i.box[0] : i.box[2]][i.mask].mean() > 0.5)
        if "agent" in spec:
            leaf_attempts = [x for x in spec["agent"]["attempts"] if x["target"] == "leaf"]
            calls, wait = len(leaf_attempts), _rounds_wait(leaf_attempts)
        else:
            calls, wait = 1, seg.meta.get("latency_s") or 0.0
        leaf_rows.append(
            {
                "image": name,
                "date": sample.date,
                "system": system,
                "leaf_prompt": spec["leaf"],
                "leaf_rank": spec.get("rank"),
                "leaf_tp": tp,
                "leaf_fp": fp,
                "leaf_fn": fn,
                "kept": len(kept),
                "on_weed": on_weed,
                "sam_calls": calls,
                "sam_cost_usd": calls * PRICE_PER_IMAGE_USD,
                "latency_s": wait,
            }
        )
    return {"rows": rows, "leaf_rows": leaf_rows}


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def aggregate(rows: list[dict]) -> dict:
    def total(key):
        return sum(r[key] for r in rows)

    cp, cr, cf = _prf(total("crop_tp"), total("crop_fp"), total("crop_fn"))
    wp, wr, wf = _prf(total("weed_tp"), total("weed_fp"), total("weed_fn"))
    mean = statistics.fmean
    costs = [r["total_cost_usd"] for r in rows]
    return {
        "images": len(rows),
        "crop_precision": cp,
        "crop_recall": cr,
        "crop_f1": cf,
        "count_mae": mean(abs(r["count_pred"] - r["count_gt"]) for r in rows),
        "count_bias": mean(r["count_pred"] - r["count_gt"] for r in rows),
        "cover_mae_pts": mean(abs(r["cover_pred"] - r["cover_gt"]) for r in rows),
        "weed_precision": wp,
        "weed_recall": wr,
        "weed_f1": wf,
        "weed_share_mae_pts": mean(abs(r["weed_share_pred"] - r["weed_share_gt"]) for r in rows),
        "sam_calls": mean(r["sam_calls"] for r in rows),
        "sam_cost_usd": mean(r["sam_cost_usd"] for r in rows),
        "llm_cost_usd": None if None in [r["llm_cost_usd"] for r in rows] else mean(r["llm_cost_usd"] for r in rows),
        "total_cost_usd": None if None in costs else mean(costs),
        "total_cost_sum_usd": None if None in costs else sum(costs),
        "tokens_in": mean(r["tokens_in"] for r in rows),
        "tokens_out": mean(r["tokens_out"] for r in rows),
        "latency_s": mean(r["latency_s"] for r in rows),
    }


def aggregate_leaf(rows: list[dict]) -> dict:
    p, r, f = _prf(sum(x["leaf_tp"] for x in rows), sum(x["leaf_fp"] for x in rows), sum(x["leaf_fn"] for x in rows))
    kept = sum(x["kept"] for x in rows)
    mean = statistics.fmean
    return {
        "images": len(rows),
        "leaf_precision": p,
        "leaf_recall": r,
        "leaf_f1": f,
        "masks_on_weeds_pct": 100 * sum(x["on_weed"] for x in rows) / kept if kept else 0.0,
        "sam_calls": mean(x["sam_calls"] for x in rows),
        "sam_cost_usd": mean(x["sam_cost_usd"] for x in rows),
        "sam_cost_sum_usd": sum(x["sam_cost_usd"] for x in rows),
        "latency_s": mean(x["latency_s"] for x in rows),
    }


def fmt_money(v) -> str:
    return "n/a" if v is None else f"${v:.4f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--provider", default=None, help="which agent_<provider>.jsonl to read (default: the only one)")
    ap.add_argument("--data", default=None)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 2))
    args = ap.parse_args()

    run_dir = RESULTS_DIR / args.run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    dataset = PhenoBench(args.data or manifest["data_root"])
    agent_files = sorted(run_dir.glob("agent_*.jsonl"))
    if args.provider:
        agent_files = [run_dir / f"agent_{args.provider}.jsonl"]
    if not agent_files or not agent_files[0].exists():
        raise SystemExit("No agent results; run eval/run_agent.py first.")
    agent_file = agent_files[0]
    agent_name = f"agent ({agent_file.stem.removeprefix('agent_')})"
    agent = {json.loads(line)["image"]: json.loads(line) for line in agent_file.read_text().splitlines() if line.strip()}

    jobs = []
    for name in manifest["images"]:
        if name not in agent:
            continue
        systems = {label: {"crop": prompt, "weed": WEED_PROMPT} for label, prompt in FIXED_SYSTEMS.items()}
        a = agent[name]
        if a["chosen"]["crop"] and a["chosen"]["weed"]:
            systems[agent_name] = {"crop": a["chosen"]["crop"]["prompt"], "weed": a["chosen"]["weed"]["prompt"], "agent": a}
        leaf_systems = {label: {"leaf": prompt} for label, prompt in LEAF_FIXED_SYSTEMS.items()}
        if a["chosen"].get("leaf"):  # agent run included the leaf experiment (not --no-leaf)
            leaf_systems[agent_name] = {"leaf": a["chosen"]["leaf"]["prompt"], "rank": a["chosen"]["leaf"]["rank"], "agent": a}
        jobs.append((str(dataset.root), manifest["split"], name, args.threshold, systems, leaf_systems))
    print(f"Comparing {len(jobs)} images: {', '.join([*FIXED_SYSTEMS, agent_name])}")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(score_image, jobs))
    rows = [r for res in results for r in res["rows"]]
    leaf_rows = [r for res in results for r in res["leaf_rows"] if "missing" not in r]

    missing = [r for r in rows if "missing" in r]
    rows = [r for r in rows if "missing" not in r]
    if missing:
        print(f"WARNING: {len(missing)} image/system pairs skipped (SAM answer not cached), e.g. {missing[0]['missing']}")
    systems = [*FIXED_SYSTEMS, agent_name]
    # compare on images every system has
    common = set.intersection(*({r["image"] for r in rows if r["system"] == s} for s in systems))
    rows = [r for r in rows if r["image"] in common]
    for r in rows:
        r["system"] = f"{r['system']} · {r['rule']}"
    labels_in_order = [f"{s} · {rule}" for s in systems for rule in CONFLICT_RULES]
    agg = {s: aggregate([r for r in rows if r["system"] == s]) for s in labels_in_order if any(r["system"] == s for r in rows)}

    leaf_systems_order = [*LEAF_FIXED_SYSTEMS] + ([agent_name] if any(r["system"] == agent_name for r in leaf_rows) else [])
    leaf_sets = [{r["image"] for r in leaf_rows if r["system"] == s} for s in leaf_systems_order]
    leaf_common = set.intersection(*leaf_sets) if all(leaf_sets) else set()
    leaf_rows = [r for r in leaf_rows if r["image"] in leaf_common]
    leaf_agg = {s: aggregate_leaf([r for r in leaf_rows if r["system"] == s]) for s in leaf_systems_order if leaf_common}

    with (run_dir / "compare.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    if leaf_rows:
        with (run_dir / "compare_leaves.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(leaf_rows[0].keys()))
            writer.writeheader()
            writer.writerows(leaf_rows)
    (run_dir / "compare.json").write_text(json.dumps({"crop_weed": agg, "leaves": leaf_agg}, indent=2))

    acc_cols = ["crop_precision", "crop_recall", "crop_f1", "count_mae", "count_bias", "cover_mae_pts", "weed_precision", "weed_recall", "weed_f1", "weed_share_mae_pts"]
    cost_rows = []
    for s, a in agg.items():
        if not s.endswith("· crop-first"):
            continue  # cost and time don't depend on the conflict rule
        s = s.removesuffix(" · crop-first")
        cost_rows.append(
            [
                s,
                f"{a['sam_calls']:.2f}",
                fmt_money(a["sam_cost_usd"]),
                f"{a['tokens_in']:.0f} / {a['tokens_out']:.0f}",
                fmt_money(a["llm_cost_usd"]),
                fmt_money(a["total_cost_usd"]),
                fmt_money(a["total_cost_sum_usd"]),
                f"{a['latency_s']:.1f}s",
            ]
        )
    agent_rows = [agent[n] for n in sorted(common)]
    rank_lines = []
    for target in ("crop", "weed", "leaf"):
        ranks = Counter(str(a["chosen"][target]["rank"]) for a in agent_rows if a["chosen"].get(target))
        if ranks:
            rank_lines.append(f"- {target}: " + ", ".join(f"#{k}: {v}" for k, v in sorted(ranks.items())))
    leaf_md: list[str] = []
    if leaf_agg:
        leaf_cols = ["leaf_precision", "leaf_recall", "leaf_f1", "masks_on_weeds_pct"]
        leaf_md = [
            "## Leaves (experiment)",
            "",
            f"{len(leaf_common)} images. Scored against PhenoBench's sugar beet leaves; weed leaves are not labelled, "
            "so a leaf mask on a weed counts as a false alarm (`masks_on_weeds_pct` shows how often). The agent's leaf "
            "phrases come from the same Muse Spark call, so leaves only add SAM calls.",
            "",
            md_table(
                ["system", *leaf_cols, "SAM calls", "SAM $ / image", f"SAM $ ({len(leaf_common)} images)", "SAM wait"],
                [
                    [s, *[v[c] for c in leaf_cols], f"{v['sam_calls']:.2f}", fmt_money(v["sam_cost_usd"]), fmt_money(v["sam_cost_sum_usd"]), f"{v['latency_s']:.1f}s"]
                    for s, v in leaf_agg.items()
                ],
            ),
            "",
        ]
    by_date = defaultdict(dict)
    for s in agg:
        for d in sorted({r["date"] for r in rows}):
            sub = aggregate([r for r in rows if r["system"] == s and r["date"] == d])
            by_date[d][s] = sub
    date_rows = [
        [d, s, v["crop_f1"], v["count_mae"], v["weed_f1"], v["cover_mae_pts"]] for d, per in by_date.items() for s, v in per.items()
    ]
    def words(a: dict, target: str) -> str:
        chosen = a["chosen"].get(target)
        if not chosen:
            return "–"
        return " / ".join(a["proposal"].get(target) or []) + f" → **{chosen['prompt']}**"

    examples = [
        [a["image"], a["proposal"]["scene"] or "–", words(a, "crop"), words(a, "weed"), words(a, "leaf")]
        for a in agent_rows[:12]
    ]
    md = [
        f"# Fixed words vs prompt agent: run `{args.run}`",
        "",
        f"{len(common)} PhenoBench images, confidence threshold {args.threshold}. Same images, same SAM 3.1, same "
        "cleanup; only the search words differ. Accuracy uses one-to-one matching at IoU ≥ 0.5.",
        "",
        "Conflict rule = what happens when the same plant is found as crop and as weed: `score` keeps the "
        "higher-confidence mask, `crop-first` always keeps the crop (the grower told us the crop). "
        "Crop/weed precision, recall and F1 are raw SAM masks, so they don't depend on the rule; count, "
        "cover and weed share do.",
        "",
        "## Accuracy",
        "",
        md_table(["system", *acc_cols], [[s, *[a[c] for c in acc_cols]] for s, a in agg.items()]),
        "",
        "## Cost and time per image",
        "",
        md_table(["system", "SAM calls", "SAM $", "LLM tokens in / out", "LLM $", "total $ / image", f"total $ ({len(common)} images)", "wait"], cost_rows),
        "",
        "SAM: $0.0025 per call. Muse Spark: $1.25 / 1M input, $0.15 / 1M cached input, $4.25 / 1M output "
        "tokens (reasoning counts as output). Wait = LLM time + SAM rounds (calls in a round run in parallel), "
        "measured while the eval ran many images at once, so absolute seconds are pessimistic.",
        "",
        *leaf_md,
        "## Which of the agent's words worked (kept word, by rank)",
        "",
        *rank_lines,
        "",
        "## By growth stage",
        "",
        md_table(["date", "system", "crop F1", "count MAE", "weed F1", "crop cover MAE"], date_rows),
        "",
        "## What the agent proposed (first images)",
        "",
        md_table(["image", "agent's view", "crop words → kept", "weed words → kept", "leaf words → kept"], examples),
        "",
        "Files: `compare.csv` (one row per image and system), `compare_leaves.csv`, `compare.json` (the tables above).",
    ]
    (run_dir / "compare.md").write_text("\n".join(md))
    print("\n".join(md[:14]))
    print(f"\nFull report: {run_dir / 'compare.md'}")


if __name__ == "__main__":
    main()
