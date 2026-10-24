#!/usr/bin/env bash
# Detached SmolVLA fine-tune launcher (macOS: caffeinate + start_new_session).
#
# Usage:
#   scripts/train_smolvla.sh [options] [STEPS=10000] [BATCH=8]
#
# Options:
#   --hw-root <path>              hardware workspace (LEROBOT_HW_ROOT)
#   --dataset-root <path>         clean28 dataset root (SMOLVLA_DATASET_ROOT)
#   --dataset-repo-id <id>        LeRobot repo id (SMOLVLA_DATASET_REPO_ID)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib_hw_root.sh
source "$SCRIPT_DIR/lib_hw_root.sh"

STEPS=""
BATCH=""
DATASET_ROOT="${SMOLVLA_DATASET_ROOT:-}"
REPO_ID="${SMOLVLA_DATASET_REPO_ID:-yohei1126/so101_pick_sponge_main}"

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
    --dataset-repo-id)
      [[ $# -ge 2 ]] || {
        echo "ERROR: --dataset-repo-id requires a value" >&2
        exit 1
      }
      REPO_ID="$2"
      shift 2
      ;;
    --dataset-repo-id=*)
      REPO_ID="${1#*=}"
      shift
      ;;
    -h | --help)
      sed -n '2,12p' "$0" | tr -d '#'
      exit 0
      ;;
    -*)
      echo "ERROR: unknown option: $1" >&2
      exit 1
      ;;
    *)
      if [[ -z "$STEPS" ]]; then
        STEPS="$1"
      elif [[ -z "$BATCH" ]]; then
        BATCH="$1"
      else
        echo "ERROR: unexpected argument: $1" >&2
        exit 1
      fi
      shift
      ;;
  esac
done

STEPS="${STEPS:-10000}"
BATCH="${BATCH:-8}"
DATASET_ROOT="${DATASET_ROOT:-$HW/datasets/so101_pick_sponge_main_20261023_clean28}"
TS="$(date +%Y%m%d_%H%M)"
# shellcheck disable=SC1091
source "$HW/.venv/bin/activate"
mkdir -p "$HW/outputs/logs"
export STEPS BATCH TS
export LEROBOT_HW_ROOT="$HW"
export SMOLVLA_DATASET_ROOT="$DATASET_ROOT"
export SMOLVLA_DATASET_REPO_ID="$REPO_ID"
python - <<'EOF'
import os
import subprocess

hw = os.environ["LEROBOT_HW_ROOT"]
ts = os.environ["TS"]
dataset_root = os.environ["SMOLVLA_DATASET_ROOT"]
repo_id = os.environ["SMOLVLA_DATASET_REPO_ID"]
log_path = f"{hw}/outputs/logs/smolvla_so101_clean28_{ts}.log"
log = open(log_path, "ab")
cmd = [
    "caffeinate",
    "-i",
    "lerobot-train",
    "--policy.path=lerobot/smolvla_base",
    f"--dataset.repo_id={repo_id}",
    f"--dataset.root={dataset_root}",
    "--dataset.video_backend=pyav",
    '--rename_map={"observation.images.top": "observation.images.camera1",'
    ' "observation.images.wrist": "observation.images.camera2"}',
    "--policy.device=mps",
    "--policy.push_to_hub=false",
    f"--batch_size={os.environ['BATCH']}",
    f"--steps={os.environ['STEPS']}",
    "--save_freq=1000",
    "--log_freq=50",
    "--num_workers=4",
    "--wandb.enable=false",
    f"--output_dir={hw}/outputs/smolvla_so101_clean28_{ts}",
    "--job_name=smolvla_so101_clean28",
]
proc = subprocess.Popen(
    cmd,
    cwd=hw,
    stdout=log,
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    start_new_session=True,
)
print("PID", proc.pid)
print("log:", log_path)
EOF
