"""Browse every SAM call of an eval run in the browser.

For each image x prompt, two panels:
  left  = what SAM returned: each mask in its own color with "number confidence";
          gray outlines are masks below the confidence threshold (the app drops them)
  right = compared with ground truth: green = correct, red = false alarm, yellow = missed

Reads cached SAM answers only (run run_sam.py first); makes no API calls.

    uv run --project api python eval/gallery.py --run val
    open eval/results/val/gallery/index.html
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from common import CACHE_DIR, RESULTS_DIR
from elderleaf.render import render_comparison, render_segmentation, side_by_side, to_jpeg
from elderleaf.sam import CacheMiss, SamClient
from evaluate import _pairs, greedy_match
from phenobench import PhenoBench


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def render_image(job: tuple) -> dict:
    data_root, split, name, prompts, thr, out_dir, max_side, extras = job
    sample = PhenoBench(data_root).load(split, name)
    rgb = np.array(Image.open(sample.image_path).convert("RGB"))
    client = SamClient(cache_dir=CACHE_DIR)
    cards = []
    # manifest prompts first, then the words the agent tried for this image (group "agent")
    calls = [(p, t, None, p) for p, t in prompts.items()]
    calls += [(p, t, label, "agent") for p, t, label in extras if p not in prompts]
    for prompt, target, label, group in calls:
        try:
            seg = client.segment(sample.image_path, prompt, offline=True)
        except CacheMiss:
            cards.append({"prompt": prompt, "target": target, "label": label, "group": group, "missing": True})
            continue
        gt = sample.leaves if target == "leaf" else sample.plants
        eligible = {g.id for g in gt.instances if target in ("plant", "leaf") or g.cls == target}
        keep = [i.score_or_one >= thr for i in seg.instances]
        pairs = _pairs(seg.instances, gt.labels, np.bincount(gt.labels.ravel()))
        matches = greedy_match(pairs, keep, eligible)
        matched_preds = {p for p, _ in matches.values()}
        missed = sorted(eligible - set(matches))
        left = render_segmentation(rgb, seg.instances, prompt=prompt, threshold=thr, max_side=max_side)
        right = render_comparison(rgb, seg.instances, keep, matched_preds, gt.labels, missed, max_side=max_side)
        file = f"{Path(name).stem}__{_slug(prompt)}.jpg"
        (Path(out_dir) / "img" / file).write_bytes(to_jpeg(side_by_side(left, right)))
        scores = [i.score_or_one for i in seg.instances]
        cards.append(
            {
                "prompt": prompt,
                "target": target,
                "label": label,
                "group": group,
                "file": file,
                "masks": len(scores),
                "kept": sum(keep),
                "tp": len(matches),
                "fp": sum(keep) - len(matched_preds),
                "fn": len(missed),
                "gt": len(eligible),
                "mean_conf": statistics.fmean(scores) if scores else None,
                "latency": seg.meta.get("latency_s"),
            }
        )
    crops = sum(1 for g in sample.plants.instances if g.cls == "crop")
    return {
        "name": name,
        "date": sample.date,
        "counts": {"crop": crops, "weed": len(sample.plants.instances) - crops, "leaf": len(sample.leaves.instances)},
        "cards": cards,
    }


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SAM 3.1 gallery: {run}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; padding: 16px 24px; background: #f4f4f2; color: #1d1d1b; }}
  header {{ position: sticky; top: 0; background: #f4f4f2; padding: 8px 0 12px; border-bottom: 1px solid #ddd; z-index: 1; }}
  h1 {{ font-size: 20px; margin: 0 0 6px; }}
  .legend span {{ display: inline-block; margin-right: 14px; font-size: 14px; }}
  .sw {{ display: inline-block; width: 12px; height: 12px; border-radius: 2px; vertical-align: -1px; margin-right: 4px; }}
  .controls {{ margin-top: 8px; font-size: 14px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }}
  section {{ margin: 22px 0; }}
  h2 {{ font-size: 16px; margin: 0 0 8px; }}
  h2 small {{ font-weight: normal; color: #666; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(620px, 1fr)); gap: 12px; }}
  figure {{ margin: 0; background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 8px; }}
  figcaption {{ font-size: 13px; margin-bottom: 6px; }}
  figure img {{ width: 100%; height: auto; display: block; }}
  .bad {{ color: #c0392b; font-weight: 600; }}
  .missing {{ color: #999; font-style: italic; }}
</style></head><body>
<header>
  <h1>SAM 3.1 outputs, run <code>{run}</code>: {n_images} images, {n_calls} calls, threshold {thr}</h1>
  <div class="legend">
    <span>Left: what SAM returned (each mask its own color, "number confidence"; <span class="sw" style="background:#afafaf"></span>gray = below threshold, dropped)</span><br>
    <span>Right: vs ground truth</span>
    <span><span class="sw" style="background:#1ed23c"></span>correct</span>
    <span><span class="sw" style="background:#f02828"></span>false alarm</span>
    <span><span class="sw" style="background:#ffe100"></span>missed (outline)</span>
  </div>
  <div class="controls">{prompt_boxes}
    <label>Date <select id="date"><option value="all">all</option>{date_options}</select></label>
    <label><input type="checkbox" id="worst"> most errors first</label>
  </div>
</header>
<main id="main">
{sections}
</main>
<script>
  const boxes = [...document.querySelectorAll('input[data-prompt]')];
  const dateSel = document.getElementById('date');
  const worst = document.getElementById('worst');
  const main = document.getElementById('main');
  const sections = [...main.querySelectorAll('section')];
  function apply() {{
    const on = new Set(boxes.filter(b => b.checked).map(b => b.dataset.prompt));
    document.querySelectorAll('figure[data-prompt]').forEach(f => f.hidden = !on.has(f.dataset.prompt));
    sections.forEach(s => s.hidden = dateSel.value !== 'all' && s.dataset.date !== dateSel.value);
    const errors = s => [...s.querySelectorAll('figure[data-prompt]')]
      .filter(f => on.has(f.dataset.prompt)).reduce((a, f) => a + Number(f.dataset.errors || 0), 0);
    const order = worst.checked ? [...sections].sort((a, b) => errors(b) - errors(a)) : sections;
    order.forEach(s => main.appendChild(s));
  }}
  [...boxes, dateSel, worst].forEach(el => el.addEventListener('change', apply));
</script>
</body></html>
"""


def write_html(out_dir: Path, run: str, thr: float, prompts: dict[str, str], images: list[dict]) -> Path:
    esc = html.escape
    prompt_boxes = "".join(
        f'<label><input type="checkbox" checked data-prompt="{esc(p)}"> {esc(p)} <small>→ {esc(t)}</small></label>'
        for p, t in prompts.items()
    )
    if any(c.get("group") == "agent" for i in images for c in i["cards"]):
        prompt_boxes += '<label><input type="checkbox" checked data-prompt="agent"> <b>agent\'s words</b></label>'
    dates = sorted({i["date"] for i in images})
    sections = []
    for img in images:
        c = img["counts"]
        cards = []
        for card in img["cards"]:
            title = f"<b>{esc(card['prompt'])}</b> → {esc(card['target'])}"
            if card.get("label"):
                title += f" <i>({esc(card['label'])})</i>"
            group = esc(card.get("group") or card["prompt"])
            if card.get("missing"):
                cards.append(f'<figure data-prompt="{group}"><figcaption>{title} <span class="missing">not cached; run run_sam.py</span></figcaption></figure>')
                continue
            errors = card["fp"] + card["fn"]
            conf = "–" if card["mean_conf"] is None else f"{card['mean_conf']:.2f}"
            latency = "" if card["latency"] is None else f" · {card['latency']:.1f}s"
            stats = (
                f"{card['masks']} masks ({card['kept']} kept) · GT {card['gt']} · "
                f"<span class='{'bad' if errors else ''}'>✓{card['tp']} ✗{card['fp']} missed {card['fn']}</span>"
                f" · mean conf {conf}{latency}"
            )
            cards.append(
                f'<figure data-prompt="{group}" data-errors="{errors}"><figcaption>{title} · {stats}</figcaption>'
                f'<a href="img/{esc(card["file"])}" target="_blank"><img loading="lazy" src="img/{esc(card["file"])}" alt="{esc(card["prompt"])} on {esc(img["name"])}"></a></figure>'
            )
        sections.append(
            f'<section data-date="{img["date"]}"><h2>{esc(img["name"])} <small>date {img["date"]} · '
            f'ground truth: {c["crop"]} crop, {c["weed"]} weed, {c["leaf"]} leaves</small></h2>'
            f'<div class="cards">{"".join(cards)}</div></section>'
        )
    page = PAGE.format(
        run=esc(run),
        n_images=len(images),
        n_calls=sum(1 for i in images for c in i["cards"] if not c.get("missing")),
        thr=thr,
        prompt_boxes=prompt_boxes,
        date_options="".join(f'<option value="{d}">{d}</option>' for d in dates),
        sections="\n".join(sections),
    )
    path = out_dir / "index.html"
    path.write_text(page, encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--data", default=None, help="override data root from the manifest")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0, help="N images spread evenly over the run (0 = all)")
    ap.add_argument("--max-side", type=int, default=640, help="panel size in px")
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 2))
    args = ap.parse_args()

    run_dir = RESULTS_DIR / args.run
    manifest = json.loads((run_dir / "manifest.json").read_text())
    dataset = PhenoBench(args.data or manifest["data_root"])
    names = manifest["images"]
    if args.limit and args.limit < len(names):  # spread over all dates, not just the first one
        step = len(names) / args.limit
        names = [names[int(i * step)] for i in range(args.limit)]
    out_dir = run_dir / "gallery"
    (out_dir / "img").mkdir(parents=True, exist_ok=True)

    # words the agent tried (from run_agent.py), shown as extra cards
    extras: dict[str, list[tuple[str, str, str]]] = {}
    for agent_file in sorted(run_dir.glob("agent_*.jsonl")):
        provider = agent_file.stem.removeprefix("agent_")
        for line in agent_file.read_text().splitlines():
            rec = json.loads(line)
            for a in rec["attempts"]:
                kept = rec["chosen"].get(a["target"]) or {}
                verdict = "kept" if kept.get("prompt") == a["prompt"] else ("confident" if a["ok"] else "weak")
                rank = f"#{a['rank']}" if isinstance(a["rank"], int) else "fallback"
                extras.setdefault(rec["image"], []).append((a["prompt"], a["target"], f"agent {provider} {rank}, {verdict}"))

    jobs = [
        (str(dataset.root), manifest["split"], n, manifest["prompts"], args.threshold, str(out_dir), args.max_side, extras.get(n, []))
        for n in names
    ]
    print(f"Rendering {len(jobs)} images x {len(manifest['prompts'])} prompts...")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        images = list(pool.map(render_image, jobs))
    path = write_html(out_dir, args.run, args.threshold, manifest["prompts"], images)
    print(f"Open in a browser: {path}")


if __name__ == "__main__":
    main()
