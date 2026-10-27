#!/bin/bash
# Read-only SO-101 preflight before teleop or lerobot-record.
# Does not open a motor bus, move the arm, or write a dataset.
# Usage: scripts/preflight_real_so101.sh
#
# Env (optional), same names as docs/real_robot_bringup and the deploy scripts:
#   LEROBOT_HW_ROOT or LEROBOT_HW   hardware workspace (default: $HOME/work/lerobot-hw)
#   PORT_LEADER / PORT_FOLLOWER     serial nodes (default: record_real_so101.sh tty paths)
#   WRIST_INDEX / TOP_INDEX         OpenCV indices (default: 0 / 1)
#
# macOS /bin/bash 3.2 compatible. Checks live in scripts/preflight_real_so101.py.
# The lerobot-hw venv is preferred so OpenCV matches lerobot-record. Without it,
# the Python script falls back to system_profiler / ffmpeg avfoundation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HW="${LEROBOT_HW_ROOT:-${LEROBOT_HW:-$HOME/work/lerobot-hw}}"
if [[ -x "$HW/.venv/bin/python" ]]; then
  exec "$HW/.venv/bin/python" "$ROOT/scripts/preflight_real_so101.py" "$@"
fi
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$ROOT/scripts/preflight_real_so101.py" "$@"
fi
echo "No Python found. Create $HW/.venv or install python3." >&2
exit 1
