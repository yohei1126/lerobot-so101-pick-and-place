#!/bin/bash
# SO-101 demo recording for the 2026-10-26 table layout (Issue #90).
# Interactive: Right=next, Left=re-record, Esc=stop
# Usage: scripts/record_real_so101.sh [num_episodes]   (default 50; re-run resumes into ROOT)
#
# Default ROOT is the 2026-10-27 layout dataset. Episodes 0–9 there are the
# 2026-10-27 05:04–05:11 SGT demos (source indices 32–41 of the mixed archive).
# so101_pick_sponge_main_20261020 is an archive. This script exits if ROOT
# resolves to that directory. Point ROOT at a different new dataset only when
# starting another set on purpose.
set -e
cd "$HOME/work/lerobot-hw"
source .venv/bin/activate
N=${1:-50}
ROOT="${ROOT:-$HOME/work/lerobot-hw/datasets/so101_pick_sponge_layout20261026_20261027}"
ARCHIVE="$HOME/work/lerobot-hw/datasets/so101_pick_sponge_main_20261020"
resolve_dir() {
  if [ -d "$1" ]; then
    (cd "$1" && pwd -P)
  else
    printf '%s\n' "$1"
  fi
}
if [ "$(resolve_dir "$ROOT")" = "$(resolve_dir "$ARCHIVE")" ]; then
  echo "Refusing to record into the archived mixed dataset: $ARCHIVE" >&2
  echo "New demos use \$HOME/work/lerobot-hw/datasets/so101_pick_sponge_layout20261026_20261027 (Issue #90 / 2026-10-26 layout)." >&2
  exit 1
fi
RESUME=false
[ -d "$ROOT" ] && RESUME=true && echo "Existing dataset found -> resume (adds $N episodes) into $ROOT"
pkill -f lerobot-teleoperate 2>/dev/null || true
LOG="outputs/record_main_$(date +%Y%m%d_%H%M%S).log"
lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/tty.usbmodem5B8E1163071 --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader --teleop.port=/dev/tty.usbmodem5B790143611 --teleop.id=leader \
  --dataset.repo_id=yohei1126/so101_pick_sponge_layout20261026 \
  --dataset.single_task='Pick up the yellow sponge and place it on the white paper' \
  --dataset.num_episodes="$N" --dataset.episode_time_s=25 --dataset.reset_time_s=10 --dataset.fps=30 \
  --dataset.no_stamp=true --dataset.push_to_hub=false --dataset.root="$ROOT" \
  --display_data=true --play_sounds=true --resume=$RESUME 2>&1 | tee "$LOG"
