#!/usr/bin/env bash
# Light-trim ACT retrain (Issue #45). Does NOT auto-detach; run when MPS is free.
#
# Keeps frames from (first_motion − KEEP_BEFORE). Default KEEP_BEFORE=40.
# Optional UNTRIM_MIX (0–1): fraction of episodes left fully untrimmed in train.
# Checkpoints every 2500 steps for open-loop scoring (score_act_checkpoints.py).
#
# Expected duration: ~3.5–4 h on Mac MPS for STEPS=25000 (similar to prior full runs).
#
# Example (foreground)::
#
#   STEPS=25000 KEEP_BEFORE=40 UNTRIM_MIX=0.5 ./scripts/train_act_light_trim.sh
#
# Detached (optional)::
#
#   DETACH=1 ./scripts/train_act_light_trim.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HW="${LEROBOT_HW_ROOT:-$HOME/work/lerobot-hw}"
STEPS="${STEPS:-25000}"
KEEP_BEFORE="${KEEP_BEFORE:-40}"
UNTRIM_MIX="${UNTRIM_MIX:-0.5}"
OUT="${OUT:-$HW/outputs/act_so101_clean28_lighttrim_${KEEP_BEFORE}_mix${UNTRIM_MIX}_$(date +%Y%m%d)}"
LOG_DIR="${HW}/outputs/logs"
LOG="${LOG:-$LOG_DIR/$(basename "$OUT").log}"
CONTRACT="${CONTRACT:-$HW/configs/contract_from_clean28.json}"
DATASET="${DATASET:-$HW/datasets/so101_pick_sponge_main_20261023_clean28}"
DETACH_MODE="${DETACH:-0}"

if [[ ! -f "$CONTRACT" ]]; then
  echo "Missing contract: $CONTRACT" >&2
  echo "Extract from a prior best_model.pt or copy configs/contract.yaml." >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$OUT"
if [[ -f "$HW/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$HW/.venv/bin/activate"
fi
export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"
export PYTHONPATH="${ROOT}/port_pick_align/src${PYTHONPATH:+:$PYTHONPATH}"

CMD=(
  python "$ROOT/scripts/train_act_light_trim.py"
  --keep-before "$KEEP_BEFORE"
  --untrim-mix "$UNTRIM_MIX"
  --contract "$CONTRACT"
  --dataset-root "$DATASET"
  --repo-id local/so101_pick_sponge_main_clean28
  --output-dir "$OUT"
  --arch full
  --steps "$STEPS"
  --batch-size 8
  --lr 1e-4
  --val-ratio 0.1
  --val-interval 500
  --max-val-batches 20
  --scheduler cosine
  --checkpoint-interval 2500
  --device mps
  --skip-infer
)

echo "Light-trim retrain (will use MPS):"
echo "  KEEP_BEFORE=$KEEP_BEFORE UNTRIM_MIX=$UNTRIM_MIX STEPS=$STEPS"
echo "  OUT=$OUT"
echo "  LOG=$LOG"
echo "  expected wall time ~3.5–4h for 25k steps"
echo "Command: ${CMD[*]}"

if [[ "$DETACH_MODE" == "1" ]]; then
  PID_FILE="${OUT}.pid"
  ARGFILE="$(mktemp)"
  printf '%s\0' "${CMD[@]}" >"$ARGFILE"
  HW="$HW" OUT="$OUT" LOG="$LOG" PID_FILE="$PID_FILE" ROOT="$ROOT" ARGFILE="$ARGFILE" \
  python - <<'PY'
import os, subprocess
from pathlib import Path
raw = Path(os.environ["ARGFILE"]).read_bytes().split(b"\0")
cmd = [a.decode() for a in raw if a]
Path(os.environ["ARGFILE"]).unlink(missing_ok=True)
log = open(os.environ["LOG"], "ab")
env = os.environ.copy()
env["PYTHONPATH"] = str(Path(os.environ["ROOT"]) / "port_pick_align" / "src") + (
    (":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else ""
)
env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
full = ["caffeinate", "-i", *cmd]
proc = subprocess.Popen(
    full, cwd=os.environ["HW"], stdout=log, stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL, start_new_session=True, env=env,
)
Path(os.environ["PID_FILE"]).write_text(str(proc.pid) + "\n", encoding="utf-8")
print(f"PID {proc.pid}\nlog: {os.environ['LOG']}\npid: {os.environ['PID_FILE']}")
PY
else
  "${CMD[@]}" 2>&1 | tee -a "$LOG"
fi
