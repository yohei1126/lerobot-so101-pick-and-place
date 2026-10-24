#!/usr/bin/env bash
# Run fine-tuned SmolVLA on the SO-101 follower.
# Default = DRY-RUN (reads robot+cameras, never sends actions, no torque writes).
# Pass --live to move the arm. Other flags are forwarded (see --help).
#
# Path / port options (also accepted by the Python module):
#   --hw-root <path>   hardware workspace (LEROBOT_HW_ROOT; default ~/work/lerobot-hw)
# Env (optional):
#   LEROBOT_HW_ROOT   hardware workspace
#   PORT_FOLLOWER     serial port override
#   SMOLVLA_CHECKPOINT / SMOLVLA_DATASET / SMOLVLA_TASK
#   HF_HUB_OFFLINE=1  use locally cached tokenizer/base (recommended on Mac)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib_hw_root.sh
source "$SCRIPT_DIR/lib_hw_root.sh"
resolve_hw_root_args "$@"
set -- "${REMAINING[@]}"
if [[ -f "$HW/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$HW/.venv/bin/activate"
fi
export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export PYTHONPATH="${ROOT}/port_pick_align/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m port_pick_align.deploy.smolvla_real --hw-root "$HW" "$@"
