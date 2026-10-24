#!/usr/bin/env bash
# SO-101 main dataset recording (interactive: Right=next, Left=re-record, Esc=stop)
#
# Usage:
#   scripts/record_real_so101.sh [options] [num_episodes]
#
# Options (env fallback in parentheses):
#   --hw-root <path>           hardware workspace (LEROBOT_HW_ROOT; default ~/work/lerobot-hw)
#   --dataset-root <path>      dataset root (DATASET_ROOT; default $HW/datasets/so101_pick_sponge_main_20261020)
#   --port-follower <dev>      follower serial (PORT_FOLLOWER; required if unset)
#   --port-leader <dev>        leader serial (PORT_LEADER; required if unset)
#
# Default num_episodes=50; re-run resumes when the dataset root already exists.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib_hw_root.sh
source "$SCRIPT_DIR/lib_hw_root.sh"

DATASET_ROOT="${DATASET_ROOT:-}"
PORT_FOLLOWER="${PORT_FOLLOWER:-}"
PORT_LEADER="${PORT_LEADER:-}"
N=""

resolve_hw_root_args "$@"
set -- "${REMAINING[@]}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dataset-root)
      [[ $# -ge 2 ]] || {
        echo "ERROR: --dataset-root requires a path" >&2
        exit 1
      }
      DATASET_ROOT="$2"
      shift 2
      ;;
    --dataset-root=*)
      DATASET_ROOT="${1#*=}"
      shift
      ;;
    --port-follower)
      [[ $# -ge 2 ]] || {
        echo "ERROR: --port-follower requires a device path" >&2
        exit 1
      }
      PORT_FOLLOWER="$2"
      shift 2
      ;;
    --port-follower=*)
      PORT_FOLLOWER="${1#*=}"
      shift
      ;;
    --port-leader)
      [[ $# -ge 2 ]] || {
        echo "ERROR: --port-leader requires a device path" >&2
        exit 1
      }
      PORT_LEADER="$2"
      shift 2
      ;;
    --port-leader=*)
      PORT_LEADER="${1#*=}"
      shift
      ;;
    -h | --help)
      sed -n '2,16p' "$0" | tr -d '#'
      exit 0
      ;;
    -*)
      echo "ERROR: unknown option: $1" >&2
      exit 1
      ;;
    *)
      N="$1"
      shift
      ;;
  esac
done

N="${N:-50}"
ROOT="${DATASET_ROOT:-$HW/datasets/so101_pick_sponge_main_20261020}"

if [[ -z "$PORT_FOLLOWER" || -z "$PORT_LEADER" ]]; then
  echo "ERROR: set follower/leader serial ports via --port-follower/--port-leader or PORT_FOLLOWER/PORT_LEADER (from lerobot-find-port)." >&2
  exit 1
fi

cd "$HW"
# shellcheck disable=SC1091
source .venv/bin/activate
RESUME=false
if [[ -d "$ROOT" ]]; then
  RESUME=true
  echo "Existing dataset found -> resume (adds $N episodes)"
fi
pkill -f lerobot-teleoperate 2>/dev/null || true
mkdir -p "$HW/outputs"
LOG="$HW/outputs/record_main_$(date +%Y%m%d_%H%M%S).log"
lerobot-record \
  --robot.type=so101_follower --robot.port="$PORT_FOLLOWER" --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader --teleop.port="$PORT_LEADER" --teleop.id=leader \
  --dataset.repo_id=yohei1126/so101_pick_sponge_main \
  --dataset.single_task='Pick up the yellow sponge and place it on the white paper' \
  --dataset.num_episodes="$N" --dataset.episode_time_s=25 --dataset.reset_time_s=10 --dataset.fps=30 \
  --dataset.no_stamp=true --dataset.push_to_hub=false --dataset.root="$ROOT" \
  --display_data=true --play_sounds=true --resume=$RESUME 2>&1 | tee "$LOG"
