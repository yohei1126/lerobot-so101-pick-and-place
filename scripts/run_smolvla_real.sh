#!/usr/bin/env bash
# Run fine-tuned SmolVLA on the SO-101 follower.
# Default = DRY-RUN (reads robot+cameras, never sends actions, no torque writes).
# Pass --live to move the arm. Other flags are forwarded (see --help).
#
# Env (optional):
#   LEROBOT_HW_ROOT   hardware workspace (default: $HOME/work/lerobot-hw)
#   PORT_FOLLOWER     serial port override
#   SMOLVLA_CHECKPOINT / SMOLVLA_DATASET / SMOLVLA_TASK
#   HF_HUB_OFFLINE=1  use locally cached tokenizer/base (recommended on Mac)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HW="${LEROBOT_HW_ROOT:-$HOME/work/lerobot-hw}"
if [[ -f "$HW/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$HW/.venv/bin/activate"
fi
export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export PYTHONPATH="${ROOT}/port_pick_align/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m port_pick_align.deploy.smolvla_real "$@"
