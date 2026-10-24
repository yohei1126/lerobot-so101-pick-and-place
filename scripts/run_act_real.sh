#!/usr/bin/env bash
# Run REAL-trained ACT on the SO-101 follower (LeRobot degrees / gripper 0-100).
# Default = DRY-RUN (reads robot+cameras, never sends actions, no torque writes).
# Pass --live to move the arm. Other flags are forwarded (see --help).
#
# Env (optional):
#   LEROBOT_HW_ROOT   hardware workspace (default: $HOME/work/lerobot-hw)
#   PORT_FOLLOWER     serial port override
#   ACT_REAL_CHECKPOINT / ACT_REAL_DATASET
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HW="${LEROBOT_HW_ROOT:-$HOME/work/lerobot-hw}"
if [[ -f "$HW/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$HW/.venv/bin/activate"
fi
export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"
export PYTHONPATH="${ROOT}/port_pick_align/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m port_pick_align.deploy.act_real "$@"
