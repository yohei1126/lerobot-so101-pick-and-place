#!/usr/bin/env bash
# Phase 1.5 closed-loop benchmark: trained ACT, randomized box.
#
# Runs two eval modes and writes a combined summary:
#   1) Temporal ensembling (n_action_steps forced to 1) → outputs/eval_sim_act/
#   2) No TE, execute N chunk steps before replan → outputs/eval_sim_act_chunk${N}/
#
# This script does not invent metrics. It exits if the checkpoint is missing.
# On a Mac with the full training run:
#   DEVICE=mps ./scripts/run_phase15_benchmark.sh
# CPU smoke (not the submission result):
#   DEVICE=cpu ./scripts/run_phase15_benchmark.sh /path/to/best_model.pt
# Optional env:
#   EPISODES=20 N_ACTION_STEPS=30 SKIP_TE=0 SKIP_CHUNK=0
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CKPT="${1:-$ROOT/checkpoints/sim_act/best_model.pt}"
DEVICE="${DEVICE:-cpu}"
EPISODES="${EPISODES:-20}"
N_ACTION_STEPS="${N_ACTION_STEPS:-30}"
OUT_TE="${OUT_TE:-$ROOT/outputs/eval_sim_act}"
OUT_CHUNK="${OUT_CHUNK:-$ROOT/outputs/eval_sim_act_chunk${N_ACTION_STEPS}}"
SUMMARY="${SUMMARY:-$ROOT/outputs/eval_sim_act_summary.json}"
SKIP_TE="${SKIP_TE:-0}"
SKIP_CHUNK="${SKIP_CHUNK:-0}"

if [[ -d "$ROOT/.venv" ]] && [[ -z "${VIRTUAL_ENV:-}" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

if [[ ! -f "$CKPT" ]]; then
  echo "ERROR: checkpoint not found: $CKPT" >&2
  echo "Train checkpoints/sim_act/best_model.pt locally before this benchmark." >&2
  echo "Do not fill metrics by hand. See docs/results/eval_sim_act.pending.json." >&2
  exit 1
fi

run_one() {
  local label="$1"
  local out_dir="$2"
  shift 2
  echo "=== Phase 1.5 eval mode: ${label} ==="
  python scripts/run_sim_eval.py \
    --policy checkpoint \
    --checkpoint "$CKPT" \
    --episodes "$EPISODES" \
    --max-steps 260 \
    --randomize-box \
    --output-dir "$out_dir" \
    --device "$DEVICE" \
    --save-video \
    --video-mode topdown \
    "$@"
}

if [[ "$SKIP_TE" != "1" ]]; then
  run_one "temporal_ensemble" "$OUT_TE" \
    --temporal-ensemble \
    --temporal-ensemble-coeff 0.01
fi

if [[ "$SKIP_CHUNK" != "1" ]]; then
  run_one "n_action_steps=${N_ACTION_STEPS}" "$OUT_CHUNK" \
    --no-temporal-ensemble \
    --n-action-steps "$N_ACTION_STEPS"
fi

python - "$OUT_TE" "$OUT_CHUNK" "$SUMMARY" "$CKPT" "$N_ACTION_STEPS" <<'PY'
import json
import sys
from pathlib import Path

out_te, out_chunk, summary_path, ckpt, n_steps = sys.argv[1:6]
modes = {}
for label, path in (
    ("temporal_ensemble", Path(out_te) / "metrics.json"),
    (f"n_action_steps_{n_steps}", Path(out_chunk) / "metrics.json"),
):
    if path.is_file():
        modes[label] = json.loads(path.read_text(encoding="utf-8"))

payload = {
    "checkpoint": ckpt,
    "modes": {
        name: {
            "metrics_path": str(
                (Path(out_te) if name == "temporal_ensemble" else Path(out_chunk))
                / "metrics.json"
            ),
            "thresholds_met": data.get("thresholds_met"),
            "temporal_ensemble": data.get("temporal_ensemble"),
            "n_action_steps": data.get("n_action_steps"),
            "summary": data.get("summary"),
        }
        for name, data in modes.items()
    },
}
Path(summary_path).parent.mkdir(parents=True, exist_ok=True)
Path(summary_path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"wrote {summary_path}")
for name, block in payload["modes"].items():
    summary = block.get("summary") or {}
    print(
        f"{name}: align={summary.get('align_success_rate')} "
        f"grasp={summary.get('grasp_success_rate')} "
        f"pos_mm={summary.get('mean_position_error_mm')} "
        f"thresholds_met={block.get('thresholds_met')}"
    )
PY
