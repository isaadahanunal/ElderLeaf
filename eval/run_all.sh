#!/usr/bin/env bash
# Full evaluation, start to finish. Safe to re-run: every SAM and LLM answer is cached and
# finished work is skipped, so an interrupted run continues where it stopped.
#
#   bash eval/run_all.sh                         # every val image (772)
#   PER_DATE=20 bash eval/run_all.sh             # quicker: 20 images per capture date
#   AGENT_ARGS=--no-leaf bash eval/run_all.sh    # skip the agent's leaf experiment
#
# Watch progress:  tail -f eval/results/full/run_all.log
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1

RUN=${RUN:-full}
PER_DATE=${PER_DATE:-1000}          # 1000 = every image of each date
CALIB_PER_DATE=${CALIB_PER_DATE:-20}
PY="uv run --project api python"
mkdir -p "eval/results/$RUN"
exec > >(tee -a "eval/results/$RUN/run_all.log") 2>&1

step() { echo; echo "=== [$(date '+%H:%M:%S')] $* ==="; }
twice() { "$@" || { echo "--- retrying once: $*"; "$@"; }; }

step "1/7 SAM on calibration images (train, $CALIB_PER_DATE per date)"
twice $PY eval/run_sam.py --run calib --split train --per-date "$CALIB_PER_DATE" --workers 16
step "2/7 calibration report (which confidence threshold works best)"
$PY eval/evaluate.py --run calib
step "3/7 SAM with fixed words on val ($PER_DATE per date)"
twice $PY eval/run_sam.py --run "$RUN" --split val --per-date "$PER_DATE" --workers 16
step "4/7 prompt agent (Muse Spark Open) on val"
twice $PY eval/run_agent.py --run "$RUN" --workers 8 ${AGENT_ARGS:-}
step "5/7 SAM report: visibility, crowding, growth stage, size, app numbers"
$PY eval/evaluate.py --run "$RUN" --viz 12
step "6/7 comparison: plant / crop plant / sugar beet plant / agent"
$PY eval/compare.py --run "$RUN"
step "7/7 gallery (60 images spread over all dates)"
$PY eval/gallery.py --run "$RUN" --limit 60
step "done"
echo "Reports: eval/results/$RUN/compare.md  eval/results/$RUN/summary.md  eval/results/calib/summary.md"
echo "Gallery: eval/results/$RUN/gallery/index.html"
