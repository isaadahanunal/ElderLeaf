"""Send a PhenoBench subset to SAM 3.1 and cache every raw answer.

Network-only step: no metrics here (see evaluate.py). Re-running is free, since
cached (image, prompt) pairs are skipped.

    uv run --project api python eval/run_sam.py --run calib --split train --per-date 7
    uv run --project api python eval/run_sam.py --run val --split val --per-date 20
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import CACHE_DIR, RESULTS_DIR, parse_prompt_args
from elderleaf.sam import PRICE_PER_IMAGE_USD, SamClient, SamError
from phenobench import PhenoBench, date_of


def select_images(names: list[str], per_date: int, seed: int) -> list[str]:
    by_date: dict[str, list[str]] = defaultdict(list)
    for name in names:
        by_date[date_of(name)].append(name)
    rng = random.Random(seed)
    chosen = []
    for date in sorted(by_date):
        pool = by_date[date]
        chosen += sorted(rng.sample(pool, min(per_date, len(pool))))
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data", help="folder containing PhenoBench (default: data)")
    ap.add_argument("--run", required=True, help="run name; results go to eval/results/<run>/")
    ap.add_argument("--split", default="val", choices=["train", "val"])
    ap.add_argument("--per-date", type=int, default=20, help="images sampled per capture date")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--prompt", action="append", help="'text=target' (repeatable); default: common.DEFAULT_PROMPTS")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--resample", action="store_true", help="ignore the image list of an existing manifest")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and cost, call nothing")
    args = ap.parse_args()

    dataset = PhenoBench(args.data)
    run_dir = RESULTS_DIR / args.run
    manifest_path = run_dir / "manifest.json"
    prompts = parse_prompt_args(args.prompt)

    if manifest_path.exists() and not args.resample:
        manifest = json.loads(manifest_path.read_text())
        images = manifest["images"]
        prompts = {**manifest["prompts"], **prompts} if args.prompt else manifest["prompts"]
        print(f"Reusing image list from {manifest_path} ({len(images)} images)")
    else:
        images = select_images(dataset.names(args.split), args.per_date, args.seed)
    if not images:
        sys.exit(f"No images found in {dataset.root / args.split / 'images'}")

    dates = sorted({date_of(n) for n in images})
    client = SamClient(cache_dir=CACHE_DIR)
    jobs = [(name, prompt) for name in images for prompt in prompts]
    todo = [
        (name, prompt)
        for name, prompt in jobs
        if not client.is_cached(dataset.image_path(args.split, name), prompt)
    ]
    print(
        f"{args.split}: {len(images)} images over dates {', '.join(dates)}; {len(prompts)} prompts "
        f"-> {len(jobs)} requests, {len(todo)} not cached (~${len(todo) * PRICE_PER_IMAGE_USD:.2f})"
    )
    if args.dry_run:
        return

    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "dataset": "PhenoBench",
        "data_root": str(dataset.root),
        "split": args.split,
        "seed": args.seed,
        "per_date": args.per_date,
        "images": images,
        "prompts": prompts,
        "model": client.model,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    started = time.monotonic()
    done, failed, latencies = 0, [], []

    def work(name: str, prompt: str):
        seg = client.segment(dataset.image_path(args.split, name), prompt, parse=False)
        return seg.meta

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(work, n, p): (n, p) for n, p in todo}
        for fut in as_completed(futures):
            name, prompt = futures[fut]
            try:
                meta = fut.result()
                latencies.append(meta.get("latency_s", 0.0))
            except SamError as exc:
                failed.append((name, prompt, str(exc)))
                if len(failed) == 1:
                    print(f"  first failure: {exc}")
            done += 1
            if done % 20 == 0 or done == len(todo):
                print(f"  {done}/{len(todo)} done, {len(failed)} failed, {time.monotonic() - started:.0f}s")

    if latencies:
        lat = sorted(latencies)
        print(f"latency per request: median {lat[len(lat) // 2]:.2f}s, max {lat[-1]:.2f}s")
    print(f"spent ~${(len(todo) - len(failed)) * PRICE_PER_IMAGE_USD:.2f}")
    if failed:
        (run_dir / "failures.json").write_text(json.dumps(failed, indent=2))
        print(f"{len(failed)} requests failed -> {run_dir / 'failures.json'} (re-run to retry)")
        sys.exit(1)
    print(f"Next: uv run --project api python eval/evaluate.py --run {args.run}")


if __name__ == "__main__":
    main()
