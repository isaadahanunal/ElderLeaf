"""Run the prompt agent on an eval run's images and record what happened.

Per image: the agent's 3 ranked phrases for crop and weeds, every SAM attempt (masks, confidence,
time), which phrase was kept, LLM tokens, cost and latency. Same code path as the app
(elderleaf.agent + elderleaf.prompting).

    uv run --project api python eval/run_agent.py --run val                  # provider from .env
    uv run --project api python eval/run_agent.py --run val --provider meta  # Muse Spark 1.3
    uv run --project api python eval/run_agent.py --run val --redo-errors    # redo images hit by network errors

Writes eval/results/<run>/agent_<provider>.jsonl. LLM and SAM answers are cached (re-runs are free).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import CACHE_DIR, RESULTS_DIR
from elderleaf.agent import SYSTEM_PROMPT, USER_TEMPLATE, propose_prompts
from elderleaf.crops import FALLBACK_PROMPT, crop_label
from elderleaf.llm import LLMClient
from elderleaf.prompting import Chain, build_candidates, run_chains, sam_cost, sam_latency
from elderleaf.sam import PRICE_PER_IMAGE_USD, SamClient
from phenobench import PhenoBench

CROP_ID = "sugar_beet"  # PhenoBench is a sugar beet field
# after the agent's 3 phrases, each chain falls back to the plain word (same as the app)
FALLBACKS = {"crop": FALLBACK_PROMPT, "weed": "weed", "leaf": "leaf"}


def config_key(llm: LLMClient, threshold: float, targets: list[str]) -> str:
    """Records are only reused (resume) when made with the same agent instructions and settings."""
    parts = [SYSTEM_PROMPT, USER_TEMPLATE, llm.provider, llm.model, str(llm.reasoning_effort), str(threshold)]
    parts += [",".join(targets), json.dumps(FALLBACKS, sort_keys=True)]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


def had_error(rec: dict) -> bool:
    """The LLM call or a SAM attempt failed (e.g. network down), so the chain moved on early."""
    return bool(rec["proposal"]["error"]) or any(a.get("error") for a in rec["attempts"])


def run_one(
    dataset: PhenoBench, split: str, name: str, llm: LLMClient, sam: SamClient, threshold: float, targets: list[str]
) -> dict:
    path = dataset.image_path(split, name)
    proposal = propose_prompts(llm, path.read_bytes(), crop_label(CROP_ID))
    ok = proposal.error is None
    proposed = {"crop": proposal.crop_prompts, "weed": proposal.weed_prompts, "leaf": proposal.leaf_prompts}
    chains = [Chain(t, build_candidates(proposed[t] if ok else [], [FALLBACKS[t]])) for t in targets]
    run_chains(sam, path, chains, threshold, decode_chosen=False)  # eval only needs the scores
    attempts = [a for c in chains for a in c.attempts]
    u = proposal.llm
    return {
        "image": name,
        "config": config_key(llm, threshold, targets),
        "provider": llm.provider,
        "model": llm.model,
        "threshold": threshold,
        "proposal": {
            "crop": proposal.crop_prompts,
            "weed": proposal.weed_prompts,
            "leaf": proposal.leaf_prompts,
            "scene": proposal.scene,
            "crop_visible": proposal.crop_visible,
            "error": proposal.error,
        },
        "llm": None
        if u is None
        else {
            "input_tokens": u.input_tokens,
            "cached_input_tokens": u.cached_input_tokens,
            "output_tokens": u.output_tokens,
            "reasoning_tokens": u.reasoning_tokens,
            "latency_s": u.latency_s,
            "cost_usd": u.cost_usd,
            "cached": u.cached,
        },
        "attempts": [a.to_dict() for a in attempts],
        "chosen": {
            c.target: ({"prompt": c.chosen.prompt, "rank": c.chosen.rank, "ok": c.chosen.ok} if c.chosen else None)
            for c in chains
        },
        "sam_calls": len(attempts),
        "sam_cost_usd": sam_cost(len(attempts)),
        "sam_latency_s": sam_latency(attempts),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--provider", default=None, help="baseten | meta (default: LLM_PROVIDER)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--data", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--workers", type=int, default=4, help="images in parallel")
    ap.add_argument("--no-leaf", action="store_true", help="skip the leaf experiment (crop and weed only)")
    ap.add_argument(
        "--redo-errors", action="store_true", help="also redo finished images whose LLM or SAM call failed"
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    targets = ["crop", "weed"] if args.no_leaf else ["crop", "weed", "leaf"]

    run_dir = RESULTS_DIR / args.run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    dataset = PhenoBench(args.data or manifest["data_root"])
    names = manifest["images"][: args.limit or None]
    llm = LLMClient(provider=args.provider, model=args.model)
    max_sam = len(names) * 4 * len(targets)
    print(
        f"{len(names)} images, agent = {llm.provider}:{llm.model}, targets {', '.join(targets)}; "
        f"{len(names)} LLM calls and at most {max_sam} SAM calls (<= ${max_sam * PRICE_PER_IMAGE_USD:.2f} for SAM)"
    )
    if args.dry_run:
        return
    if not llm.configured:
        sys.exit(f"No API key for provider {llm.provider!r}.")

    sam = SamClient(cache_dir=CACHE_DIR)
    out = run_dir / f"agent_{llm.provider}.jsonl"
    # resume: keep finished images, redo only missing or failed ones
    records: dict[str, dict] = {}
    key = config_key(llm, args.threshold, targets)
    if out.exists():
        stale = 0
        for line in out.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("crashed"):
                    continue
                if rec.get("config") != key:
                    stale += 1  # made with other instructions/settings: redo
                    continue
                records[rec["image"]] = rec  # a later line for the same image wins
        if stale:
            print(f"{stale} earlier records used different agent instructions; redoing them")
        if args.redo_errors:
            failed = [n for n, rec in records.items() if had_error(rec)]
            for n in failed:
                del records[n]
            print(f"--redo-errors: redoing {len(failed)} images whose LLM or SAM call failed")
    todo = [n for n in names if n not in records]
    if records:
        print(f"resuming: {len(records)} images already done, {len(todo)} to go")

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool, out.open("a") as sink:
        futures = {
            pool.submit(run_one, dataset, manifest["split"], n, llm, sam, args.threshold, targets): n for n in todo
        }
        for i, future in enumerate(as_completed(futures), start=1):
            name = futures[future]
            try:
                rec = future.result()
            except Exception as exc:  # one bad image must not stop a long run
                rec = {"image": name, "crashed": f"{type(exc).__name__}: {exc}"}
                print(f"  [{i}/{len(todo)}] {name}: CRASHED {rec['crashed']}")
            sink.write(json.dumps(rec) + "\n")
            sink.flush()
            if rec.get("crashed"):
                continue
            records[name] = rec
            elapsed = time.monotonic() - started
            eta = elapsed / i * (len(todo) - i)
            picks = ", ".join(
                f"{t} -> {c['prompt']} (#{c['rank']})" if (c := rec["chosen"].get(t)) else f"{t} -> -" for t in targets
            )
            print(f"  [{i}/{len(todo)}] {name}: {picks}  [eta {eta / 60:.0f} min]", flush=True)

    # rewrite in manifest order, without crash markers that were redone
    with out.open("w") as f:
        for name in names:
            if name in records:
                f.write(json.dumps(records[name]) + "\n")
    crashed = [n for n in names if n not in records]
    if crashed:
        print(f"{len(crashed)} images crashed; re-run the same command to retry them")

    rows = list(records.values())
    errors = sum(1 for r in rows if r["proposal"]["error"])
    llm_rows = [r["llm"] for r in rows if r["llm"]]
    print(f"\ndone in {time.monotonic() - started:.0f}s -> {out}")
    print(f"agent errors: {errors}/{len(rows)}")
    for target in targets:
        ranks = Counter(str(r["chosen"][target]["rank"]) for r in rows if r["chosen"].get(target))
        print(f"{target} word kept, by rank: {dict(sorted(ranks.items()))}")
    if llm_rows:
        tin = sum(u["input_tokens"] for u in llm_rows)
        tout = sum(u["output_tokens"] for u in llm_rows)
        costs = [u["cost_usd"] for u in llm_rows]
        cost = "unknown (set LLM_PRICE_IN_PER_M / LLM_PRICE_OUT_PER_M)" if None in costs else f"${sum(costs):.4f}"
        print(f"LLM tokens: {tin} in / {tout} out; LLM cost {cost}")
    print(f"SAM calls: {sum(r['sam_calls'] for r in rows)}")
    print(f"Next: uv run --project api python eval/compare.py --run {args.run} --provider {llm.provider}")
    if crashed:
        sys.exit(1)


if __name__ == "__main__":
    main()
