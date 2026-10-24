#!/usr/bin/env bash
# Run REAL-trained ACT on the SO-101 follower (LeRobot degrees / gripper 0-100).
# Default = DRY-RUN (reads robot+cameras, never sends actions, no torque writes).
# Pass --live to move the arm. Other flags are forwarded (see --help).
#
# Useful flags:
#   --live / --dry-run
#   --n-action-steps 10          (default 10; ignored with --temporal-ensemble)
#   --temporal-ensemble          ACT exp. ensemble, query every step (k=0.01)
#   --temporal-ensemble-k 0.01
#   --save-video / --no-save-video
#       Default: video ON for --live, OFF for dry-run
#   --checkpoint PATH
#
# Env (optional):
#   LEROBOT_HW_ROOT   hardware workspace (default: $HOME/work/lerobot-hw)
#   PORT_FOLLOWER     serial port override
#   ACT_REAL_CHECKPOINT / ACT_REAL_DATASET
#
# Protocol: docs/real_eval_protocol.ja.md
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
