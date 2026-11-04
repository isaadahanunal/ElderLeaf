# Evaluation: SAM 3.1 on PhenoBench

Every ElderLeaf number comes from SAM 3.1 masks, so we check those masks against
hand-labelled ground truth. We break the results down by **visibility** (how much of the plant is
inside the photo; edge plants are cut off), **crowding** (plants touching other plants), growth
stage (capture date) and plant size, which shows *when* the numbers can be trusted.

`train/` and `val/` hold one PNG per image in each label folder: `semantics/` (pixel class),
`plant_instances/` and `leaf_instances/` (pixel = object id), `plant_visibility/` and
`leaf_visibility/` (pixel = 0..255 share inside the image). They look black in an image viewer
because the values are small numbers. `eval/show_gt.py` draws them in color. `test/` has no labels.

Data: PhenoBench (Weyler et al., IEEE TPAMI 2024, arXiv 2306.04557). phenobench.org states
CC BY-SA 4.0, and the README inside `PhenoBench-v110.zip` states **CC BY-NC-SA 4.0**. We follow the
stricter one: non-commercial evaluation and demo use only, with attribution. Derived images
(overlays) carry the same license. The dataset is not stored in this repo. Download
`PhenoBench-v110.zip` (md5 `5168bba762053725890478432cdbdb1d`) from https://www.phenobench.org
and unzip it into `data/`.

```bash
cp .env.example .env            # add MODEL_API_KEY
cd api && uv sync && cd ..

# 1. send images to SAM 3.1 (cached; re-runs are free). --dry-run prints the cost first.
uv run --project api python eval/run_sam.py --run calib --split train --per-date 7 --dry-run
uv run --project api python eval/run_sam.py --run calib --split train --per-date 7
uv run --project api python eval/run_sam.py --run val   --split val   --per-date 20

# 2. score them (no API calls). Pick the threshold on calib, report on val.
uv run --project api python eval/evaluate.py --run calib
uv run --project api python eval/evaluate.py --run val --threshold 0.5 --viz 6
```

Outputs in `eval/results/<run>/`: `summary.md` (all tables), `threshold_sweep.csv`,
`gt_matches.csv` (one row per ground-truth object), `images.csv`, `viz/` (side-by-side failures).

## Fixed words vs the prompt agent

The app can choose SAM's search words two ways. **Fixed:** one call with "crop plant" or with the
crop's name. **Agent:** Muse Spark looks at the photo, proposes 3 ranked phrases for the crop and 3
for the weeds, and the app tries them in order until SAM answers confidently (at least one mask
above the threshold and mean confidence ≥ 0.5), then falls back to the fixed word. To compare the
two on the same images for accuracy, cost and time:

```bash
uv run --project api python eval/run_sam.py --run val --split val --per-date 20   # fixed words (cached)
uv run --project api python eval/run_agent.py --run val                            # agent's words, tokens, time
uv run --project api python eval/compare.py --run val                              # -> results/val/compare.md
```

If the network dropped during the agent run (`agent errors: N` at the end, or a SAM attempt with an
error), `run_agent.py --run val --redo-errors` redoes only those images; then run `compare.py` again.

`compare.md` reports crop and weed precision/recall/F1, count, cover and weed-share errors, SAM
calls, $ per image (SAM $0.0025/call + LLM tokens), waiting time, and which of the agent's ranks
worked. Each system is scored under two conflict rules (`score` vs `crop-first`). The gallery also
shows every word the agent tried.

To look at every SAM call (image × prompt) in the browser:

```bash
uv run --project api python eval/gallery.py --run val
open eval/results/val/gallery/index.html
```

Each card has two panels. Left: what SAM returned, each mask in its own color with
"number confidence", and gray outlines for masks below the threshold. Right: compared with
ground truth, where green is correct, red is a false alarm and a yellow outline is a missed object.
You can filter by prompt and date, and sort by most errors (handy for picking failure examples).

Prompts and the GT they're scored against (edit in `common.py` or pass `--prompt "text=target"`):

| prompt | scored against |
|---|---|
| `crop plant`, `sugar beet plant` | crop instances (weeds hit by a crop prompt are reported as "FP = other class") |
| `weed` | weed instances |
| `plant` | all plant instances (canopy cover) |
| `leaf` | crop leaf instances |
