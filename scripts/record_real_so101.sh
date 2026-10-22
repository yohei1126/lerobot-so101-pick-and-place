#!/bin/bash
# SO-101 main dataset recording (interactive: Right=next, Left=re-record, Esc=stop)
# Usage: scripts/record_real_so101.sh [num_episodes]   (default 50; re-run resumes)
set -e
cd "$HOME/work/lerobot-hw"
source .venv/bin/activate
N=${1:-50}
ROOT="$HOME/work/lerobot-hw/datasets/so101_pick_sponge_main_20261020"
RESUME=false
[ -d "$ROOT" ] && RESUME=true && echo "Existing dataset found -> resume (adds $N episodes)"
pkill -f lerobot-teleoperate 2>/dev/null || true
LOG="outputs/record_main_$(date +%Y%m%d_%H%M%S).log"
lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/tty.usbmodem5B8E1163071 --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader --teleop.port=/dev/tty.usbmodem5B790143611 --teleop.id=leader \
  --dataset.repo_id=yohei1126/so101_pick_sponge_main \
  --dataset.single_task='Pick up the yellow sponge and place it on the white paper' \
  --dataset.num_episodes="$N" --dataset.episode_time_s=25 --dataset.reset_time_s=10 --dataset.fps=30 \
  --dataset.no_stamp=true --dataset.push_to_hub=false --dataset.root="$ROOT" \
  --display_data=true --play_sounds=true --resume=$RESUME 2>&1 | tee "$LOG"
