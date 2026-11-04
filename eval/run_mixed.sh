#!/usr/bin/env bash
# Mixed-scenes experiment, start to finish. Two LLM runs go side by side:
#   Muse Spark Open (Baseten): CropAndWeed A + B, then all 772 PhenoBench photos with the scan mode
#   Muse Wonder 1.0 (Meta API): CropAndWeed A + B and 100 PhenoBench photos (spread over dates)
# then one report. Safe to re-run: SAM and LLM answers are cached and finished photos are skipped.
#
#   caffeinate -i bash eval/run_mixed.sh   # everything (~1.5 h, ~$30)
#   WONDER=0 bash eval/run_mixed.sh        # without Wonder
#   SKIP_PHENO=1 bash eval/run_mixed.sh    # Spark Open on CropAndWeed only
#
# Watch progress:  tail -f eval/results/mixed/run_mixed.log eval/results/mixed/run_wonder.log
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1
PY="uv run --project api python"
mkdir -p eval/results/mixed
exec > >(tee -a eval/results/mixed/run_mixed.log) 2>&1

step() { echo; echo "=== [$(date '+%H:%M:%S')] $* ==="; }
twice() { "$@" || { echo "--- retrying once: $*"; "$@"; }; }
WONDER_ARGS="--provider meta --model muse-wonder-1.0 --set A B-real B-collage phenobench --pheno-limit 100 --workers 8"

step "1/5 CropAndWeed: pick photos (skipped if already picked)"
[ -f eval/results/mixed/selection.json ] || $PY eval/cropandweed.py select
step "2/5 CropAndWeed: download the picked photos, build the two-crop collages"
twice $PY eval/cropandweed.py download && $PY eval/cropandweed.py collages

WONDER_PID=""
if [ "${WONDER:-1}" != "0" ]; then
  echo "Muse Wonder runs in the background -> eval/results/mixed/run_wonder.log"
  (
    $PY eval/mixed_scenes.py run $WONDER_ARGS || $PY eval/mixed_scenes.py run $WONDER_ARGS
    $PY eval/mixed_scenes.py run $WONDER_ARGS --redo-errors
  ) >> eval/results/mixed/run_wonder.log 2>&1 &
  WONDER_PID=$!
fi

step "3/5 Muse Spark Open on A, B-real, B-collage (fixed words, ranked agent, scan agent)"
twice $PY eval/mixed_scenes.py run --set A B-real B-collage --workers 8
$PY eval/mixed_scenes.py run --set A B-real B-collage --redo-errors --workers 8
if [ -z "${SKIP_PHENO:-}" ]; then
  step "4/5 Muse Spark Open on PhenoBench val with the scan mode (fixed and ranked come from the cache)"
  twice $PY eval/mixed_scenes.py run --set phenobench --workers 8
  $PY eval/mixed_scenes.py run --set phenobench --redo-errors --workers 8
fi
if [ -n "$WONDER_PID" ]; then
  step "waiting for Muse Wonder"
  wait "$WONDER_PID"
  tail -n 2 eval/results/mixed/run_wonder.log
fi
step "5/5 report"
$PY eval/mixed_scenes.py report
step "done"
echo "Report: eval/results/mixed/report.md"
