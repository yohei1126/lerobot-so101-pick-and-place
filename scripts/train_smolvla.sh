#!/usr/bin/env bash
# Detached SmolVLA fine-tune launcher (macOS: caffeinate + start_new_session).
# Usage: scripts/train_smolvla.sh [STEPS=10000] [BATCH=8]
#
# Env (optional):
#   LEROBOT_HW_ROOT          hardware workspace (default: $HOME/work/lerobot-hw)
#   SMOLVLA_DATASET_ROOT     clean28 dataset root
#   SMOLVLA_DATASET_REPO_ID  LeRobot repo id (default: yohei1126/so101_pick_sponge_main)
set -euo pipefail
STEPS="${1:-10000}"
BATCH="${2:-8}"
HW="${LEROBOT_HW_ROOT:-$HOME/work/lerobot-hw}"
TS="$(date +%Y%m%d_%H%M)"
# shellcheck disable=SC1091
source "$HW/.venv/bin/activate"
mkdir -p "$HW/outputs/logs"
export STEPS BATCH TS
export LEROBOT_HW_ROOT="$HW"
export SMOLVLA_DATASET_ROOT="${SMOLVLA_DATASET_ROOT:-$HW/datasets/so101_pick_sponge_main_20261023_clean28}"
export SMOLVLA_DATASET_REPO_ID="${SMOLVLA_DATASET_REPO_ID:-yohei1126/so101_pick_sponge_main}"
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
