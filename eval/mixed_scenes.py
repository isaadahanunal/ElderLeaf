"""Mixed scenes: fixed words vs the ranked prompt agent vs the agent's scan mode, per LLM.

Photo sets:
  phenobench  PhenoBench val (one crop, sugar beet; weeds not split by species)
  A           CropAndWeed, one crop per photo: 8 crops, mostly 3+ weed species per photo
  B-real      CropAndWeed photos with two crops (3+ plants of the second one)
  B-collage   centre halves of two CropAndWeed photos of different crops, side by side

Systems (the grower tells us the crop(s); weeds are searched with "weed" by the fixed ones):
  fixed "plant"     the app's word when it does not know the crop; finds every plant
  fixed crop name   "<crop> plant" for every crop in the photo, all searched
  agent (ranked)    today's agent: 3 ranked phrases for the crop and for weeds, first confident one
                    wins, then "plant" / "weed". It takes one crop, so it skips two-crop photos
  agent (scan)      the LLM lists one phrase per kind of plant it sees, as many as the photo needs
                    (at most 8), each marked crop (which one) or weed; SAM searches them all
Each LLM run (`--provider`/`--model`) adds its own ranked and scan systems to the report.

    uv run --project api python eval/mixed_scenes.py run --set A B-real B-collage
    uv run --project api python eval/mixed_scenes.py run --set phenobench
    uv run --project api python eval/mixed_scenes.py run --provider meta --model muse-wonder-1.0 \\
        --set A B-real B-collage phenobench --pheno-limit 100
    uv run --project api python eval/mixed_scenes.py report     # -> eval/results/mixed/report.md

`run` caches every SAM and LLM answer and resumes; `report` makes no API calls. Scores use the
app's final masks: confidence >= threshold, tiny masks dropped, duplicates from two phrases merged,
crop wins over weed. CropAndWeed plants of unsorted or rare species are "ignore": a mask on one is
neither a hit nor a false alarm. CropAndWeed images must not be published (see cropandweed.py).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from common import CACHE_DIR, IOU_MATCH, RESULTS_DIR
from cropandweed import CROP_IDS, CROPS, DATA_ROOT, CropAndWeed, GTPlant, Scene, load_selection, read_boxes
from elderleaf.agent import MAX_SCAN_ITEMS, SCAN_TEMPLATE, SYSTEM_PROMPT, USER_TEMPLATE, propose_prompts, scan_plants
from elderleaf.crops import CROPS as LIBRARY
from elderleaf.crops import FALLBACK_PROMPT
from elderleaf.llm import BASETEN_HACKATHON_MODEL, LLMClient
from elderleaf.masks import clean_instances, instance_iou, resolve_cross_class
from elderleaf.prompting import Chain, _scores, build_candidates, run_chains
from elderleaf.sam import PRICE_PER_IMAGE_USD, CacheMiss, SamClient
from evaluate import _pairs, greedy_match, md_table
from phenobench import PhenoBench

OUT_DIR = RESULTS_DIR / "mixed"
SETS = ["phenobench", "A", "B-real", "B-collage"]
FIXED_SYSTEMS = ['fixed "plant"', "fixed crop name"]
WEED_PROMPT = "weed"


def name_prompt(crop: str) -> str:
    """The fixed crop word: the crop library's phrase if it has the crop, else "<crop> plant"."""
    for entry in LIBRARY.values():
        if entry.get("label", "").lower() == crop:
            return entry["sam_prompt"]
    return f"{crop} plant"


def records_path(provider: str, model: str | None) -> Path:
    """The provider's default model keeps records_<provider>.jsonl; other models get their own file."""
    return OUT_DIR / (f"records_{provider}.jsonl" if not model else f"records_{provider}_{model.replace('/', '_')}.jsonl")


def model_label(rec: dict, path: Path) -> str:
    model = rec.get("model") or (BASETEN_HACKATHON_MODEL if path.stem == "records_baseten" else path.stem.split("_", 2)[-1])
    return model.split("/")[-1].removeprefix("muse-")


# ------------------------------------------------------------------------------- photos


def _interleave(groups: list[list[dict]]) -> list[dict]:
    """Round-robin over groups, so --limit still covers every crop."""
    out = []
    for i in range(max((len(g) for g in groups), default=0)):
        out += [g[i] for g in groups if i < len(g)]
    return out


def specs_for(sets: list[str], pheno_run: str, limit: int, pheno_limit: int = 0) -> list[dict]:
    specs: list[dict] = []
    if "phenobench" in sets:
        manifest = json.loads((RESULTS_DIR / pheno_run / "manifest.json").read_text())
        pheno = PhenoBench(manifest["data_root"])
        names = manifest["images"]
        n = pheno_limit or limit
        if n and n < len(names):  # evenly spaced, so every capture date is represented
            names = [names[int(i * len(names) / n)] for i in range(n)]
        specs += [
            {"id": name, "set": "phenobench", "root": str(pheno.root), "split": manifest["split"],
             "image": str(pheno.image_path(manifest["split"], name)), "crops": ["sugar beet"]}
            for name in names
        ]
    cnw_sets = [s for s in sets if s != "phenobench"]
    if not cnw_sets:
        return specs
    sel = load_selection()
    cnw = CropAndWeed(DATA_ROOT)
    crop_of = {n: crop for crop, names in sel["A"].items() for n in names}
    for s in cnw_sets:
        if s == "A":
            items = _interleave([[{"id": n, "crops": [crop]} for n in names] for crop, names in sel["A"].items()])
        elif s == "B-real":
            items = [
                {"id": n, "crops": sorted({CROP_IDS[b[4]] for b in read_boxes(DATA_ROOT, n) if b[4] in CROP_IDS}, key=CROPS.index)}
                for n in sel["B-real"]
            ]
        else:
            items = [
                {"id": f"{a}+{b}", "pair": [a, b], "crops": sorted({crop_of[a], crop_of[b]}, key=CROPS.index)}
                for a, b in sel["B-collage"]
            ]
        for item in items[: limit or None]:
            path = cnw.collage_path(*item["pair"]) if "pair" in item else cnw.image_path(item["id"])
            specs.append({**item, "set": s, "root": str(DATA_ROOT), "image": str(path)})
    return specs


def load_scene(spec: dict) -> Scene:
    if spec["set"] == "phenobench":
        sample = PhenoBench(spec["root"]).load(spec["split"], spec["id"])
        plants = [GTPlant(g.id, g.cls, "sugar beet" if g.cls == "crop" else None, None, g.area) for g in sample.plants.instances]
        sem = sample.semantics
        return Scene(spec["id"], "phenobench", sample.image_path, ["sugar beet"], sample.plants.labels, plants,
                     np.isin(sem, (1, 3)), np.isin(sem, (2, 4)))
    cnw = CropAndWeed(spec["root"])
    if spec["set"] == "B-collage":
        return cnw.load_collage(*spec["pair"])
    return cnw.load(spec["id"], spec["set"])


# ----------------------------------------------------------------------------------- run


def config_key(llm: LLMClient, threshold: float) -> str:
    parts = [SYSTEM_PROMPT, USER_TEMPLATE, SCAN_TEMPLATE, str(MAX_SCAN_ITEMS), llm.provider, llm.model,
             str(llm.reasoning_effort), str(threshold), FALLBACK_PROMPT, WEED_PROMPT]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


def _llm_dict(u) -> dict | None:
    if u is None:
        return None
    return {"input_tokens": u.input_tokens, "cached_input_tokens": u.cached_input_tokens, "output_tokens": u.output_tokens,
            "reasoning_tokens": u.reasoning_tokens, "latency_s": u.latency_s, "cost_usd": u.cost_usd, "cached": u.cached}


def _fixed_call(sam: SamClient, image: Path, prompt: str, threshold: float) -> dict:
    out: dict = {"prompt": prompt}
    try:
        seg = sam.segment(image, prompt, parse=False)
        scores = _scores(seg)
        out.update(masks=len(scores), kept=sum(s >= threshold for s in scores),
                   latency_s=seg.meta.get("latency_s"), cached=bool(seg.meta.get("cached")))
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def run_one(spec: dict, llm: LLMClient, sam: SamClient, threshold: float, key: str) -> dict:
    image = Path(spec["image"])
    data = image.read_bytes()
    crops = spec["crops"]
    prompts = list(dict.fromkeys([FALLBACK_PROMPT, *(name_prompt(c) for c in crops), WEED_PROMPT]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        fixed = list(pool.map(lambda p: _fixed_call(sam, image, p, threshold), prompts))

    ranked = None
    if len(crops) == 1:  # same calls as eval/run_agent.py, so PhenoBench answers come from the cache
        proposal = propose_prompts(llm, data, crops[0])
        ok = proposal.error is None
        chains = [
            Chain("crop", build_candidates(proposal.crop_prompts if ok else [], [FALLBACK_PROMPT])),
            Chain("weed", build_candidates(proposal.weed_prompts if ok else [], [WEED_PROMPT])),
        ]
        run_chains(sam, image, chains, threshold, decode_chosen=False)
        ranked = {
            "proposal": {"crop": proposal.crop_prompts, "weed": proposal.weed_prompts, "scene": proposal.scene, "error": proposal.error},
            "llm": _llm_dict(proposal.llm),
            "attempts": [a.to_dict() for c in chains for a in c.attempts],
            "chosen": {c.target: ({"prompt": c.chosen.prompt, "rank": c.chosen.rank, "ok": c.chosen.ok} if c.chosen else None) for c in chains},
        }

    scan = scan_plants(llm, data, crops)
    chains = [Chain(item["kind"], [(item["phrase"], i)]) for i, item in enumerate(scan.items, start=1)]
    run_chains(sam, image, chains, threshold, max_workers=8, decode_chosen=False)
    return {
        "id": spec["id"], "set": spec["set"], "crops": crops, "image": spec["image"], "root": spec["root"],
        "split": spec.get("split"), "pair": spec.get("pair"), "config": key, "threshold": threshold,
        "provider": llm.provider, "model": llm.model,
        "fixed": fixed, "ranked": ranked,
        "scan": {"items": scan.items, "scene": scan.scene, "error": scan.error, "llm": _llm_dict(scan.llm),
                 "attempts": [a.to_dict() for c in chains for a in c.attempts]},
    }


def _network_error(error: str | None) -> bool:
    return bool(error) and error != "no usable phrases"


def had_error(rec: dict) -> bool:
    """An API call failed (e.g. network down), so this photo is worth redoing."""
    ranked, scan = rec.get("ranked"), rec["scan"]
    return (
        any(f.get("error") for f in rec["fixed"])
        or bool(ranked and (_network_error(ranked["proposal"]["error"]) or any(a.get("error") for a in ranked["attempts"])))
        or _network_error(scan["error"])
        or any(a.get("error") for a in scan["attempts"])
    )


def cmd_run(args: argparse.Namespace) -> None:
    specs = specs_for(args.set, args.pheno_run, args.limit, args.pheno_limit)
    missing = [s["image"] for s in specs if not Path(s["image"]).exists()]
    if missing:
        sys.exit(f"{len(missing)} photos missing (run eval/cropandweed.py download / collages), e.g. {missing[0]}")
    llm = LLMClient(provider=args.provider, model=args.model)
    if not llm.configured:
        sys.exit(f"No API key for provider {llm.provider!r}.")
    sam = SamClient(cache_dir=CACHE_DIR)
    key = config_key(llm, args.threshold)
    out = records_path(llm.provider, args.model)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    records: dict[str, dict] = {}
    if out.exists():
        for line in out.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("config") == key and not rec.get("crashed"):
                    records[rec["id"]] = rec  # a later line for the same photo wins
    if args.redo_errors:
        failed = [i for i, rec in records.items() if had_error(rec)]
        for i in failed:
            del records[i]
        print(f"--redo-errors: redoing {len(failed)} photos whose API calls failed")
    todo = [s for s in specs if s["id"] not in records]
    print(f"{len(specs)} photos ({', '.join(f'{k} {v}' for k, v in Counter(s['set'] for s in specs).items())}); "
          f"{len(specs) - len(todo)} done, {len(todo)} to go; agent = {llm.provider}:{llm.model} -> {out.name}")

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool, out.open("a") as sink:
        futures = {pool.submit(run_one, s, llm, sam, args.threshold, key): s for s in todo}
        for i, future in enumerate(as_completed(futures), start=1):
            spec = futures[future]
            try:
                rec = future.result()
            except Exception as exc:  # one bad photo must not stop the run
                rec = {"id": spec["id"], "crashed": f"{type(exc).__name__}: {exc}"}
                print(f"  [{i}/{len(todo)}] {spec['id']}: CRASHED {rec['crashed']}")
            sink.write(json.dumps(rec) + "\n")
            sink.flush()
            if rec.get("crashed"):
                continue
            records[rec["id"]] = rec
            eta = (time.monotonic() - started) / i * (len(todo) - i)
            items = ", ".join(f"{it['phrase']}" + (f" [{it['crop']}]" if it["crop"] else "") for it in rec["scan"]["items"])
            print(f"  [{i}/{len(todo)}] {rec['set']} {rec['id']}: scan -> {items or rec['scan']['error']}  [eta {eta / 60:.0f} min]", flush=True)

    with out.open("w") as f:  # rewrite without crash markers and replaced lines
        for rec in sorted(records.values(), key=lambda r: (SETS.index(r["set"]), r["id"])):
            f.write(json.dumps(rec) + "\n")
    errors = sum(1 for r in records.values() if had_error(r))
    print(f"\ndone in {time.monotonic() - started:.0f}s -> {out}; photos with failed API calls: {errors}"
          + (" (re-run with --redo-errors)" if errors else ""))


# -------------------------------------------------------------------------------- score


def dedup(instances: list) -> list:
    """Two phrases often find the same plant: keep the higher-scoring mask."""
    kept: list = []
    for inst in sorted(instances, key=lambda i: i.score_or_one, reverse=True):
        if all(instance_iou(inst, k) < IOU_MATCH for k in kept):
            kept.append(inst)
    return kept


def predict(crop_segs: dict[str, list], weed_segs: list, h: int, w: int, threshold: float) -> tuple[dict, list]:
    area = h * w
    by_species: dict[str, list] = {}
    for species, segs in crop_segs.items():
        insts = [i for s in segs for i in clean_instances(s.instances, area, threshold)]
        by_species[species] = dedup(insts) if len(segs) > 1 else insts
    if len(by_species) > 1:  # one plant found under two crop names: the higher score wins
        by_species = resolve_cross_class(by_species)
    weeds = [i for s in weed_segs for i in clean_instances(s.instances, area, threshold)]
    if len(weed_segs) > 1:
        weeds = dedup(weeds)
    crops = [i for insts in by_species.values() for i in insts]
    weeds = resolve_cross_class({"crop": crops, "weed": weeds}, priority=["crop", "weed"])["weed"]
    return by_species, weeds


def tally(insts: list, labels: np.ndarray, areas: np.ndarray, eligible: set[int], ignore: set[int]) -> tuple[int, int, int, dict]:
    if not insts:
        return 0, 0, len(eligible), {}
    pairs = _pairs(insts, labels, areas)
    matches = greedy_match(pairs, [True] * len(insts), eligible)
    used = {p for p, _ in matches.values()}
    on_ignored = {p for iou, p, g in pairs if iou >= IOU_MATCH and g in ignore and p not in used}
    tp = len(matches)
    return tp, len(insts) - tp - len(on_ignored), len(eligible) - tp, matches


def _wait(rec_llm: dict | None, attempts: list[dict]) -> float:
    rounds: dict[int, float] = {}
    for a in attempts:
        rounds[a["round"]] = max(rounds.get(a["round"], 0.0), a.get("latency_s") or 0.0)
    return ((rec_llm or {}).get("latency_s") or 0.0) + sum(rounds.values())


def systems_of(base: dict, agents: dict[str, dict]) -> dict[str, dict]:
    """Fixed systems from one record of the photo (SAM answers are shared); agent systems per LLM."""
    crops = base["crops"]
    one = crops[0] if len(crops) == 1 else None
    fixed_wait = {f["prompt"]: f.get("latency_s") or 0.0 for f in base["fixed"]}
    out = {
        'fixed "plant"': {"crop": {one or "*": [FALLBACK_PROMPT]}, "weed": [WEED_PROMPT], "calls": 2, "llm": None,
                          "wait": max(fixed_wait.get(FALLBACK_PROMPT, 0.0), fixed_wait.get(WEED_PROMPT, 0.0))},
        "fixed crop name": {"crop": {c: [name_prompt(c)] for c in crops}, "weed": [WEED_PROMPT], "calls": len(crops) + 1,
                            "llm": None, "wait": max(fixed_wait.get(p, 0.0) for p in [WEED_PROMPT, *map(name_prompt, crops)])},
    }
    for label, rec in agents.items():
        ranked = rec.get("ranked")
        if ranked and ranked["chosen"]["crop"] and ranked["chosen"]["weed"]:
            out[f"agent (ranked) · {label}"] = {
                "crop": {one: [ranked["chosen"]["crop"]["prompt"]]}, "weed": [ranked["chosen"]["weed"]["prompt"]],
                "calls": len(ranked["attempts"]), "llm": ranked["llm"], "wait": _wait(ranked["llm"], ranked["attempts"]),
            }
        scan = rec["scan"]
        crop_items: dict[str, list[str]] = defaultdict(list)
        for item in scan["items"]:
            if item["kind"] == "crop":
                crop_items[item["crop"]].append(item["phrase"])
        out[f"agent (scan) · {label}"] = {
            "crop": dict(crop_items), "weed": [it["phrase"] for it in scan["items"] if it["kind"] == "weed"],
            "calls": len(scan["items"]), "llm": scan["llm"], "wait": _wait(scan["llm"], scan["attempts"]),
        }
    return out


def score_record(job: tuple[dict, dict[str, dict], float]) -> list[dict]:
    base, agents, threshold = job
    scene = load_scene(base)
    client = SamClient(cache_dir=CACHE_DIR)
    image = Path(base["image"])
    h, w = scene.shape
    gt = {p.id: p for p in scene.plants}
    crop_ids = {i for i, p in gt.items() if p.cls == "crop"}
    weed_ids = {i for i, p in gt.items() if p.cls == "weed"}
    ignore = {i for i, p in gt.items() if p.cls == "ignore"}
    areas = np.bincount(scene.labels.ravel(), minlength=max(gt, default=0) + 1)
    groups = Counter(gt[i].group for i in weed_ids)
    segs: dict[str, object] = {}

    def seg(prompt: str):
        if prompt not in segs:
            segs[prompt] = client.segment(image, prompt, offline=True)
        return segs[prompt]

    rows = []
    for system, spec in systems_of(base, agents).items():
        row = {"set": base["set"], "id": base["id"], "crops": "+".join(base["crops"]), "system": system}
        try:
            by_species, weeds = predict(
                {sp: [seg(p) for p in ps] for sp, ps in spec["crop"].items()}, [seg(p) for p in spec["weed"]], h, w, threshold
            )
        except CacheMiss as exc:
            rows.append({**row, "missing": str(exc)})
            continue
        crops = [i for insts in by_species.values() for i in insts]
        ctp, cfp, cfn, _ = tally(crops, scene.labels, areas, crop_ids, ignore)
        species = None
        if "*" not in by_species:  # every crop mask carries a crop name: is it the right one?
            species = [0, 0, 0]
            count_err = 0
            for sp in base["crops"]:
                eligible = {i for i in crop_ids if gt[i].species == sp}
                t, f, n, _ = tally(by_species.get(sp, []), scene.labels, areas, eligible, ignore)
                species = [species[0] + t, species[1] + f, species[2] + n]
                count_err += abs(len(by_species.get(sp, [])) - len(eligible))
        wtp, wfp, wfn, wmatches = tally(weeds, scene.labels, areas, weed_ids, ignore)
        found = Counter(gt[g].group for g in wmatches)
        cover = np.zeros((h, w), bool)
        for inst in crops:
            x0, y0, x1, y1 = inst.box
            cover[y0:y1, x0:x1] |= inst.mask
        llm = spec["llm"] or {}
        rows.append({
            **row,
            "crop_tp": ctp, "crop_fp": cfp, "crop_fn": cfn,
            "species_tp": species[0] if species else None, "species_fp": species[1] if species else None,
            "species_fn": species[2] if species else None, "species_count_err": count_err if species else None,
            "count_pred": len(crops), "count_gt": len(crop_ids),
            "cover_pred": float(cover.mean() * 100), "cover_gt": float(scene.crop_px.mean() * 100),
            "weed_tp": wtp, "weed_fp": wfp, "weed_fn": wfn,
            "grass_found": found.get("grass", 0), "grass_gt": groups.get("grass", 0),
            "broadleaf_found": found.get("broadleaf", 0), "broadleaf_gt": groups.get("broadleaf", 0),
            "sam_calls": spec["calls"], "sam_cost_usd": spec["calls"] * PRICE_PER_IMAGE_USD,
            "llm_cost_usd": llm.get("cost_usd") or 0.0, "wait_s": spec["wait"],
        })
    return rows


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def aggregate(rows: list[dict]) -> dict:
    total = lambda k: sum(r[k] for r in rows)  # noqa: E731
    mean = statistics.fmean
    cp, cr, cf = _prf(total("crop_tp"), total("crop_fp"), total("crop_fn"))
    wp, wr, wf = _prf(total("weed_tp"), total("weed_fp"), total("weed_fn"))
    species_ok = all(r["species_tp"] is not None for r in rows)
    sf = _prf(total("species_tp"), total("species_fp"), total("species_fn"))[2] if species_ok else None
    grass, broad = total("grass_gt"), total("broadleaf_gt")
    return {
        "photos": len(rows),
        "crop_precision": cp, "crop_recall": cr, "crop_f1": cf,
        "right_crop_f1": sf,
        "count_mae": mean(abs(r["count_pred"] - r["count_gt"]) for r in rows),
        "count_bias": mean(r["count_pred"] - r["count_gt"] for r in rows),
        "cover_mae_pts": mean(abs(r["cover_pred"] - r["cover_gt"]) for r in rows),
        "weed_precision": wp, "weed_recall": wr, "weed_f1": wf,
        "grass_recall": total("grass_found") / grass if grass else None,
        "broadleaf_recall": total("broadleaf_found") / broad if broad else None,
        "sam_calls": mean(r["sam_calls"] for r in rows),
        "cost_usd": mean(r["sam_cost_usd"] + r["llm_cost_usd"] for r in rows),
        "wait_s": mean(r["wait_s"] for r in rows),
    }


SET_TITLES = {
    "phenobench": "PhenoBench (sugar beet, weeds as one class)",
    "A": "A: CropAndWeed, one crop per photo (8 crops, mostly 3+ weed species)",
    "B-real": "B-real: CropAndWeed photos with two crops",
    "B-collage": "B-collage: two photos of different crops side by side",
}
COLS = ["crop_precision", "crop_recall", "crop_f1", "right_crop_f1", "count_mae", "count_bias", "cover_mae_pts",
        "weed_precision", "weed_recall", "weed_f1", "grass_recall", "broadleaf_recall"]


def _tables(rows: list[dict], systems: list[str], photos: set[str], note: str) -> tuple[list[str], dict]:
    agg = {s: aggregate([r for r in rows if r["system"] == s and r["id"] in photos]) for s in systems}
    md = [
        f"{len(photos)} photos{note}.",
        "",
        md_table(["system", "photos", *COLS], [[s, a["photos"], *["–" if a[c] is None else a[c] for c in COLS]] for s, a in agg.items()]),
        "",
        md_table(["system", "SAM calls", "$ / photo", "wait"],
                 [[s, f"{a['sam_calls']:.2f}", f"${a['cost_usd']:.4f}", f"{a['wait_s']:.1f}s"] for s, a in agg.items()]),
        "",
    ]
    return md, agg


def load_records(sets: list[str] | None) -> tuple[dict[str, dict], list[str]]:
    """{photo id: {"base": first record, "agents": {model label: record}}}, model labels in file order."""
    photos: dict[str, dict] = {}
    labels: list[str] = []
    for path in sorted(OUT_DIR.glob("records_*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("crashed") or (sets and rec["set"] not in sets):
                continue
            label = model_label(rec, path)
            if label not in labels:
                labels.append(label)
            photos.setdefault(rec["id"], {"base": rec, "agents": {}})["agents"][label] = rec
    return photos, labels


def cmd_report(args: argparse.Namespace) -> None:
    photos, labels = load_records(args.set)
    if not photos:
        sys.exit("No records; run `mixed_scenes.py run` first.")
    sets_seen = Counter(p["base"]["set"] for p in photos.values())
    print(f"scoring {len(photos)} photos ({', '.join(f'{k} {v}' for k, v in sets_seen.items())}); LLMs: {', '.join(labels)}")
    jobs = [(p["base"], p["agents"], args.threshold) for p in photos.values()]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = [row for result in pool.map(score_record, jobs, chunksize=4) for row in result]
    missing = [r for r in rows if "missing" in r]
    rows = [r for r in rows if "missing" not in r]
    if missing:
        print(f"WARNING: {len(missing)} photo/system pairs skipped (SAM answer not cached), e.g. {missing[0]['missing']}")
    with (OUT_DIR / "rows.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    systems = FIXED_SYSTEMS + [f"agent ({kind}) · {label}" for label in labels for kind in ("ranked", "scan")]
    md = [
        "# Mixed scenes: fixed words vs prompt agent (ranked) vs agent scan mode",
        "",
        f"Confidence threshold {args.threshold}. LLMs: {', '.join(labels)}. Scores use the app's final masks (tiny "
        "masks dropped, duplicates merged, crop wins over weed), matched one-to-one at IoU ≥ 0.5, so PhenoBench "
        "numbers differ a little from compare.md (raw masks). `right_crop_f1` also requires the right crop name "
        "(– when the system cannot tell crops apart). CropAndWeed plants of unsorted or rare species are ignored. "
        "CropAndWeed images may not be published (licence); these numbers may.",
        "",
    ]
    summary: dict = {}
    for set_name in [s for s in SETS if s in sets_seen]:
        set_rows = [r for r in rows if r["set"] == set_name]
        ids = {i for i, p in photos.items() if p["base"]["set"] == set_name}
        present = {s: {r["id"] for r in set_rows if r["system"] == s} for s in systems}
        complete = [s for s in systems if present[s] and present[s] == ids]
        partial = [s for s in systems if present[s] and present[s] != ids]
        md += [f"## {SET_TITLES[set_name]}", ""]
        table, agg = _tables(set_rows, complete, ids, "")
        md += table
        summary[set_name] = {"all": agg}
        if partial:
            common = set.intersection(*(present[s] for s in complete + partial))
            table, agg = _tables(set_rows, complete + partial, common, f" that every system ran on (incl. {', '.join(partial)})")
            md += table
            summary[set_name]["common"] = agg
        if set_name == "A":
            per_crop = []
            for crop in CROPS:
                crop_rows = [r for r in set_rows if r["crops"] == crop]
                if crop_rows:
                    per_crop.append([crop, *[f"{aggregate([r for r in crop_rows if r['system'] == s])['crop_f1']:.2f} / "
                                             f"{aggregate([r for r in crop_rows if r['system'] == s])['weed_f1']:.2f}"
                                             for s in complete]])
            md += ["Crop F1 / weed F1 by crop:", "", md_table(["crop", *complete], per_crop), ""]
        for label in labels:
            scans = [p["agents"][label] for i, p in photos.items() if i in ids and label in p["agents"]]
            if not scans:
                continue
            n_items = [len(r["scan"]["items"]) for r in scans]
            n_crop = [sum(1 for it in r["scan"]["items"] if it["kind"] == "crop") for r in scans]
            named_all = sum(1 for r in scans if {it["crop"] for it in r["scan"]["items"] if it["kind"] == "crop"} >= set(r["crops"]))
            errors = Counter(r["scan"]["error"] or "ok" for r in scans)
            md += [f"Scan mode, {label}: {statistics.fmean(n_items):.1f} phrases per photo ({statistics.fmean(n_crop):.1f} crop); "
                   f"named every crop of the photo in {named_all}/{len(scans)} photos; answers: "
                   + ", ".join(f"{k}: {v}" for k, v in errors.items()), ""]
        shown = sorted(i for i in ids if all(label in photos[i]["agents"] for label in labels))[:6]
        if shown:
            md += [
                md_table(
                    ["photo", "crops", *[f"scan phrases · {label}" for label in labels]],
                    [[i, "+".join(photos[i]["base"]["crops"]),
                      *["; ".join(f"{it['phrase']} ({it['crop'] or 'weed'})" for it in photos[i]["agents"][label]["scan"]["items"])
                        or photos[i]["agents"][label]["scan"]["error"] for label in labels]]
                     for i in shown],
                ),
                "",
            ]
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    md.append("Files: `rows.csv` (one row per photo and system), `summary.json`, `records_*.jsonl` (every call, per LLM).")
    (OUT_DIR / "report.md").write_text("\n".join(md))
    print(f"-> {OUT_DIR / 'report.md'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["run", "report"])
    ap.add_argument("--set", nargs="+", choices=SETS, default=None, help="default: all for report, A B-real B-collage for run")
    ap.add_argument("--pheno-run", default="full", help="PhenoBench run whose photo list to use")
    ap.add_argument("--limit", type=int, default=0, help="photos per set (0 = all)")
    ap.add_argument("--pheno-limit", type=int, default=0, help="PhenoBench photos, evenly spread over dates (0 = --limit)")
    ap.add_argument("--provider", default=None, help="baseten | meta (default: LLM_PROVIDER)")
    ap.add_argument("--model", default=None, help="e.g. muse-wonder-1.0 with --provider meta (default: the provider's)")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--redo-errors", action="store_true", help="redo photos whose API calls failed")
    args = ap.parse_args()
    if args.command == "run":
        args.set = args.set or ["A", "B-real", "B-collage"]
        cmd_run(args)
    else:
        cmd_report(args)


if __name__ == "__main__":
    main()
