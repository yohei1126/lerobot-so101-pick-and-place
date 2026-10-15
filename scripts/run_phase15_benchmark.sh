#!/usr/bin/env bash
# Phase 1.5 closed-loop benchmark: trained ACT, randomized box, temporal ensembling.
#
# This script does not invent metrics. It exits if the checkpoint is missing.
# On a Mac with the full training run:
#   DEVICE=mps ./scripts/run_phase15_benchmark.sh
# CPU smoke (not the submission result):
#   DEVICE=cpu ./scripts/run_phase15_benchmark.sh /path/to/best_model.pt
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CKPT="${1:-$ROOT/checkpoints/sim_act/best_model.pt}"
DEVICE="${DEVICE:-cpu}"
EPISODES="${EPISODES:-20}"
OUT="${OUT:-$ROOT/outputs/eval_sim_act}"

if [[ ! -f "$CKPT" ]]; then
  echo "ERROR: checkpoint not found: $CKPT" >&2
  echo "Train checkpoints/sim_act/best_model.pt locally before this benchmark." >&2
  echo "Do not fill metrics by hand. See docs/results/eval_sim_act.pending.json." >&2
  exit 1
fi

python scripts/run_sim_eval.py \
  --policy checkpoint \
  --checkpoint "$CKPT" \
  --episodes "$EPISODES" \
  --max-steps 260 \
  --randomize-box \
  --temporal-ensemble \
  --temporal-ensemble-coeff 0.01 \
  --output-dir "$OUT" \
  --device "$DEVICE" \
  --save-video \
  --video-mode topdown
