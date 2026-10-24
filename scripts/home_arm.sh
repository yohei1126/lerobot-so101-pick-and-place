#!/bin/bash
# Move the SO-101 follower to the recording start pose.
# Default = DRY-RUN (prints current/target/delta, sends nothing). Add --live to move.
# Torque stays ON at the end unless --release is given.
set -e
HW="${LEROBOT_HW_ROOT:-$HOME/work/lerobot-hw}"
cd "$HW"
source .venv/bin/activate
exec python scripts/home_arm.py "$@"
