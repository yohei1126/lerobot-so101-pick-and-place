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
  results/post50/eval/best_model_te/te/metrics.json
  results/post50/eval/best_model/chunk30/metrics.json
  checkpoints/sim_act_post50/best_model_te.pt
(Legacy eval/... paths are also accepted if present.)
EOF
  exit 0
fi

if [[ "${1:-}" == "--post50-local" ]]; then
  shift
  # Prefer results/post50/eval (owner Mac layout); fall back to eval/ then docs/results pins.
  te="results/post50/eval/best_model_te/te/metrics.json"
  chunk="results/post50/eval/best_model/chunk30/metrics.json"
  [[ -f "$te" ]] || te="eval/best_model_te/te/metrics.json"
  [[ -f "$te" ]] || te="docs/results/eval_sim_act_post50_best_model_te_te.json"
  [[ -f "$chunk" ]] || chunk="eval/best_model/chunk30/metrics.json"
  [[ -f "$chunk" ]] || chunk="docs/results/eval_sim_act_post50_best_model_chunk30.json"
  py="${PYTHON:-}"
  if [[ -z "$py" ]]; then
    if [[ -x "$ROOT/.venv/bin/python" ]]; then
      py="$ROOT/.venv/bin/python"
    else
      py="python3"
    fi
  fi
  exec "$py" scripts/generate_report_figures.py \
    --training-metrics checkpoints/sim_act_post50/training_metrics.json \
    --te-metrics "$te" \
    --chunk30-metrics "$chunk" \
    --scatter-metrics "$te" \
    --checkpoint checkpoints/sim_act_post50/best_model_te.pt \
    --video-policy checkpoint \
    --device "${DEVICE:-mps}" \
    --temporal-ensemble \
    --backfill-initial-box-xy \
    "$@"
fi

_py() {
  if [[ -n "${PYTHON:-}" ]]; then
    echo "$PYTHON"
  elif [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
  else
    echo "python3"
  fi
}

if [[ "${1:-}" == "--" ]]; then
  shift
  exec "$(_py)" scripts/generate_report_figures.py "$@"
fi

# Default: reproducible fixture plots + scripted sim video (no ACT weights needed).
# Smoke outputs go under docs/figures/fixtures/ so they never overwrite post50 figures.
exec "$(_py)" scripts/generate_report_figures.py \
  --use-fixtures \
  --video-policy scripted \
  --output-dir docs/figures/fixtures \
  "$@"
