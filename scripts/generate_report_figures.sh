#!/usr/bin/env bash
# Single-command regenerator for report figures under docs/figures/.
#
# Default: use fixture metrics so the command works without Mac checkpoints.
# For post50 on the owner Mac, pass real paths (see docs/figures/README.md).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Headless Linux CI / cloud agents need OSMesa for MuJoCo imports even when
# video_mode=topdown (the env still loads mujoco).
if [[ -z "${MUJOCO_GL:-}" && "$(uname -s)" == "Linux" ]]; then
  export MUJOCO_GL=osmesa
fi

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage:
  ./scripts/generate_report_figures.sh                 # fixtures + scripted video
  ./scripts/generate_report_figures.sh --post50-local   # Mac post50 defaults
  ./scripts/generate_report_figures.sh -- [args...]     # pass-through to Python

Post50 local (Mac) expects:
  checkpoints/sim_act_post50/training_metrics.json
  eval/best_model_te/te/metrics.json
  eval/best_model/chunk30/metrics.json
  checkpoints/sim_act_post50/best_model_te.pt
EOF
  exit 0
fi

if [[ "${1:-}" == "--post50-local" ]]; then
  shift
  exec python3 scripts/generate_report_figures.py \
    --training-metrics checkpoints/sim_act_post50/training_metrics.json \
    --te-metrics eval/best_model_te/te/metrics.json \
    --chunk30-metrics eval/best_model/chunk30/metrics.json \
    --scatter-metrics eval/best_model_te/te/metrics.json \
    --checkpoint checkpoints/sim_act_post50/best_model_te.pt \
    --video-policy checkpoint \
    --device "${DEVICE:-mps}" \
    --temporal-ensemble \
    "$@"
fi

if [[ "${1:-}" == "--" ]]; then
  shift
  exec python3 scripts/generate_report_figures.py "$@"
fi

# Default: reproducible fixture plots + scripted sim video (no ACT weights needed).
exec python3 scripts/generate_report_figures.py --use-fixtures --video-policy scripted "$@"
