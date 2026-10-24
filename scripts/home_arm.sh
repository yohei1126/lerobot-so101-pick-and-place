#!/usr/bin/env bash
# Move the SO-101 follower to the recording start pose.
# Default = DRY-RUN (prints current/target/delta, sends nothing). Add --live to move.
# Torque stays ON at the end unless --release is given.
#
# Options:
#   --hw-root <path>   hardware workspace (LEROBOT_HW_ROOT; default ~/work/lerobot-hw)
# Remaining args are forwarded to scripts/home_arm.py under that workspace.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib_hw_root.sh
source "$SCRIPT_DIR/lib_hw_root.sh"
resolve_hw_root_args "$@"
set -- "${REMAINING[@]}"

cd "$HW"
# shellcheck disable=SC1091
source .venv/bin/activate
exec python scripts/home_arm.py "$@"
