#!/usr/bin/env bash
# Unattended collect → train → multi-checkpoint closed-loop eval pipeline.
#
# Reuses existing collect / train / eval entry points. Writes progress to
# results/<run>/status.json and a Markdown comparison table to
# results/<run>/summary.md. Safe to launch with nohup so an agent can exit.
#
# Full Mac (MPS) run:
#   nohup ./scripts/run_pipeline.sh --device mps --pr N \
#     > results/post41/pipeline.log 2>&1 &
#
# CPU smoke (this VM):
#   ./scripts/run_pipeline.sh --smoke --device cpu
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_NAME=""
DATASET_DIR="$ROOT/data/sim_expert/lerobot_post41"
CKPT_DIR="$ROOT/checkpoints/sim_act_post41"
DEVICE=""
TRAIN_STEPS=5000
COLLECT_EPISODES=100
EVAL_EPISODES=20
EVAL_MAX_STEPS=260
N_ACTION_STEPS=30
BATCH_SIZE=8
# Empty → train_act --preset sim defaults (patience 10, min-steps 3000).
EARLY_STOP_PATIENCE=""
MIN_STEPS=""
PR_NUMBER=""
SKIP_COLLECT=0
SKIP_TRAIN=0
SMOKE=0
SAVE_VIDEO=0
EXTRA_COLLECT_ARGS=()
EXTRA_TRAIN_ARGS=()

usage() {
  cat <<'EOF'
Usage: ./scripts/run_pipeline.sh [options]

  --run NAME              results/<NAME>/ (default: UTC timestamp)
  --dataset-dir PATH      collect/train dataset root (default: data/sim_expert/lerobot_post41)
  --checkpoint-dir PATH   train output / eval checkpoints (default: checkpoints/sim_act_post41)
  --device DEVICE         cpu|mps|cuda (default: train_act auto / eval cpu)
  --steps N               training steps (default: 5000)
  --collect-episodes N    demonstration episodes (default: 100)
  --eval-episodes N       closed-loop eval episodes per checkpoint×mode (default: 20)
  --eval-max-steps N      eval horizon (default: 260)
  --batch-size N          training batch size (default: 8)
  --early-stop-patience N closed-loop pulses without (align,-error) progress before stop
                          (default: train_act sim preset = 10; 0 = off)
  --min-steps N           never early-stop before this step (default: train_act sim = 3000)
  --pr N                  on success, post summary.md via `gh pr comment N`
  --skip-collect          skip demonstration collection
  --skip-train            skip training (evaluate existing checkpoints)
  --smoke                 short CPU-friendly config (few episodes, ~50 steps)
  --save-video            keep per-eval rollout videos (default: off)
  --collect-arg ARG       extra arg for collect_sim_dataset.py (repeatable)
  --train-arg ARG         extra arg for train_act (repeatable)
  -h, --help              show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run) RUN_NAME="$2"; shift 2 ;;
    --dataset-dir) DATASET_DIR="$2"; shift 2 ;;
    --checkpoint-dir) CKPT_DIR="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    --steps) TRAIN_STEPS="$2"; shift 2 ;;
    --collect-episodes) COLLECT_EPISODES="$2"; shift 2 ;;
    --eval-episodes) EVAL_EPISODES="$2"; shift 2 ;;
    --eval-max-steps) EVAL_MAX_STEPS="$2"; shift 2 ;;
    --batch-size) BATCH_SIZE="$2"; shift 2 ;;
    --early-stop-patience) EARLY_STOP_PATIENCE="$2"; shift 2 ;;
    --min-steps) MIN_STEPS="$2"; shift 2 ;;
    --pr) PR_NUMBER="$2"; shift 2 ;;
    --skip-collect) SKIP_COLLECT=1; shift ;;
    --skip-train) SKIP_TRAIN=1; shift ;;
    --smoke) SMOKE=1; shift ;;
    --save-video) SAVE_VIDEO=1; shift ;;
    --collect-arg) EXTRA_COLLECT_ARGS+=("$2"); shift 2 ;;
    --train-arg) EXTRA_TRAIN_ARGS+=("$2"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$SMOKE" -eq 1 ]]; then
  RUN_NAME="${RUN_NAME:-smoke}"
  # Keep smoke artifacts out of the Mac production dirs unless overridden.
  if [[ "$CKPT_DIR" == "$ROOT/checkpoints/sim_act_post41" ]]; then
    CKPT_DIR="$ROOT/checkpoints/sim_act_pipeline_smoke"
  fi
  if [[ "$DATASET_DIR" == "$ROOT/data/sim_expert/lerobot_post41" ]]; then
    DATASET_DIR="$ROOT/data/sim_expert/lerobot_pipeline_smoke"
  fi
  TRAIN_STEPS=50
  COLLECT_EPISODES=2
  EVAL_EPISODES=1
  EVAL_MAX_STEPS=80
  BATCH_SIZE=1
  DEVICE="${DEVICE:-cpu}"
  # Smoke must not inherit the sim early-stop / min-steps floor.
  if [[ -z "$EARLY_STOP_PATIENCE" ]]; then
    EARLY_STOP_PATIENCE=0
  fi
  if [[ -z "$MIN_STEPS" ]]; then
    MIN_STEPS=0
  fi
  EXTRA_COLLECT_ARGS+=(--allow-short --allow-failures --max-steps 80)
  EXTRA_TRAIN_ARGS+=(
    --arch smoke
    --val-interval 25
    --max-val-batches 2
    --closed-loop-val-episodes 1
    --closed-loop-te-episodes 1
    --closed-loop-val-max-steps 80
    --checkpoint-interval 25
  )
fi

if [[ -z "$RUN_NAME" ]]; then
  RUN_NAME="$(date -u +%Y%m%dT%H%M%SZ)"
fi

# Resolve relative paths against repo root.
[[ "$DATASET_DIR" = /* ]] || DATASET_DIR="$ROOT/$DATASET_DIR"
[[ "$CKPT_DIR" = /* ]] || CKPT_DIR="$ROOT/$CKPT_DIR"

RESULTS_DIR="$ROOT/results/$RUN_NAME"
LOG_FILE="$RESULTS_DIR/pipeline.log"
STATUS_FILE="$RESULTS_DIR/status.json"
SUMMARY_FILE="$RESULTS_DIR/summary.md"
EVAL_ROOT="$RESULTS_DIR/eval"
mkdir -p "$RESULTS_DIR" "$EVAL_ROOT"

if [[ -d "$ROOT/.venv" ]] && [[ -z "${VIRTUAL_ENV:-}" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PHASE="init"
PROGRESS="0"
STATE="running"
ERROR_TAIL=""

write_status() {
  local finished_at="${1:-}"
  python3 - "$STATUS_FILE" "$STATE" "$PHASE" "$PROGRESS" "$STARTED_AT" "$finished_at" "$ERROR_TAIL" \
    "$RUN_NAME" "$DATASET_DIR" "$CKPT_DIR" "$DEVICE" "$TRAIN_STEPS" "$COLLECT_EPISODES" \
    "$EVAL_EPISODES" "$PR_NUMBER" "$SKIP_COLLECT" "$SKIP_TRAIN" "$SMOKE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    status_path,
    state,
    phase,
    progress,
    started_at,
    finished_at,
    error_tail,
    run_name,
    dataset_dir,
    ckpt_dir,
    device,
    train_steps,
    collect_episodes,
    eval_episodes,
    pr_number,
    skip_collect,
    skip_train,
    smoke,
) = sys.argv[1:]

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
payload = {
    "state": state,
    "phase": phase,
    "progress_step": progress,
    "started_at": started_at,
    "updated_at": now,
    "finished_at": finished_at or None,
    "error_tail": error_tail or None,
    "run": run_name,
    "config": {
        "dataset_dir": dataset_dir,
        "checkpoint_dir": ckpt_dir,
        "device": device or None,
        "train_steps": int(train_steps),
        "collect_episodes": int(collect_episodes),
        "eval_episodes": int(eval_episodes),
        "pr": int(pr_number) if pr_number else None,
        "skip_collect": skip_collect == "1",
        "skip_train": skip_train == "1",
        "smoke": smoke == "1",
    },
}
Path(status_path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

set_phase() {
  PHASE="$1"
  PROGRESS="$2"
  write_status
  echo "==> [$PHASE] $PROGRESS"
}

post_pr_failure_comment() {
  # Best-effort: never re-enter fail() from here (no set -e exit on gh errors).
  local rc="$1"
  local comment_file
  if [[ -z "$PR_NUMBER" ]]; then
    return 0
  fi
  if ! command -v gh >/dev/null 2>&1; then
    echo "WARN: gh not available; skipping failure PR comment" >&2
    return 0
  fi
  comment_file="$(mktemp "${TMPDIR:-/tmp}/pipeline-fail.XXXXXX.md")"
  {
    echo "## Pipeline failed"
    echo ""
    echo "- run: \`$RUN_NAME\`"
    echo "- phase: \`$PHASE\`"
    echo "- progress: \`$PROGRESS\`"
    echo "- status: \`$STATE\` (exit $rc)"
    echo "- status file: \`$STATUS_FILE\`"
    echo "- log: \`$LOG_FILE\`"
    echo ""
    echo "### Error tail"
    echo ""
    echo '```'
    printf '%s\n' "$ERROR_TAIL"
    echo '```'
  } >"$comment_file"
  if ! gh pr comment "$PR_NUMBER" --body-file "$comment_file"; then
    echo "WARN: gh pr comment (failure) failed; status left at $STATUS_FILE" >&2
  fi
  rm -f "$comment_file"
}

fail() {
  local rc="${1:-1}"
  local msg="${2:-pipeline failed during phase=$PHASE}"
  STATE="failed"
  ERROR_TAIL="$msg"
  if [[ -f "$LOG_FILE" ]]; then
    local log_tail
    log_tail="$(tail -n 40 "$LOG_FILE" 2>/dev/null || true)"
    if [[ -n "$log_tail" ]]; then
      ERROR_TAIL="$log_tail"
    fi
  fi
  write_status "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "ERROR: $msg (rc=$rc). See $STATUS_FILE and $LOG_FILE" >&2
  trap - ERR
  post_pr_failure_comment "$rc" || true
  exit "$rc"
}

on_fail() {
  local rc=$?
  fail "$rc" "pipeline exited with status $rc during phase=$PHASE"
}
trap on_fail ERR

# Tee all subsequent output into the run log (keep stdout/stderr for nohup).
exec > >(tee -a "$LOG_FILE") 2>&1

write_status
echo "Pipeline run=$RUN_NAME results=$RESULTS_DIR"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail 1 "required command not found: $1"
}
need_cmd python3

python3 -c "import port_pick_align" 2>/dev/null \
  || fail 1 "port_pick_align not importable; run: pip install -e \"port_pick_align/[simulation,training]\""

# ---------------------------------------------------------------------------
# Phase: collect
# ---------------------------------------------------------------------------
if [[ "$SKIP_COLLECT" -eq 0 ]]; then
  set_phase "collect" "collecting demonstrations → $DATASET_DIR"
  collect_cmd=(
    python3 scripts/collect_sim_dataset.py
    --episodes "$COLLECT_EPISODES"
    --output "$DATASET_DIR"
  )
  if [[ ${#EXTRA_COLLECT_ARGS[@]} -gt 0 ]]; then
    collect_cmd+=("${EXTRA_COLLECT_ARGS[@]}")
  fi
  "${collect_cmd[@]}"
else
  set_phase "collect" "skipped"
  [[ -d "$DATASET_DIR" ]] || fail 1 "--skip-collect but dataset missing: $DATASET_DIR"
fi

# ---------------------------------------------------------------------------
# Phase: train
# ---------------------------------------------------------------------------
if [[ "$SKIP_TRAIN" -eq 0 ]]; then
  set_phase "train" "training ACT steps=$TRAIN_STEPS → $CKPT_DIR"
  train_cmd=(
    python3 -m port_pick_align.training.train_act
    --preset sim
    --dataset-root "$DATASET_DIR"
    --output-dir "$CKPT_DIR"
    --steps "$TRAIN_STEPS"
    --batch-size "$BATCH_SIZE"
    --skip-infer
  )
  if [[ -n "$DEVICE" ]]; then
    train_cmd+=(--device "$DEVICE")
  fi
  if [[ -n "$EARLY_STOP_PATIENCE" ]]; then
    train_cmd+=(--early-stop-patience "$EARLY_STOP_PATIENCE")
  fi
  if [[ -n "$MIN_STEPS" ]]; then
    train_cmd+=(--min-steps "$MIN_STEPS")
  fi
  if [[ ${#EXTRA_TRAIN_ARGS[@]} -gt 0 ]]; then
    train_cmd+=("${EXTRA_TRAIN_ARGS[@]}")
  fi
  "${train_cmd[@]}"
else
  set_phase "train" "skipped"
fi

# ---------------------------------------------------------------------------
# Phase: eval (best_model / best_model_te / last / step_*.pt × chunk30 + TE)
# ---------------------------------------------------------------------------
set_phase "eval" "discovering checkpoints in $CKPT_DIR"

# bash 3.2 (macOS /bin/bash) has no mapfile/readarray — fill the array with read.
# Prefer command substitution over process-substitution+mapfile so a non-zero
# python exit is visible under `set -e` on older bash.
_ckpt_list="$(
  python3 - "$CKPT_DIR" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
names = []
for name in ("best_model.pt", "best_model_te.pt", "last.pt"):
    p = root / name
    if p.is_file():
        names.append(str(p))
for p in sorted(root.glob("step_*.pt")):
    if p.is_file():
        names.append(str(p))
if not names:
    raise SystemExit(f"no checkpoints found under {root}")
print("\n".join(names))
PY
)" || fail 1 "checkpoint discovery failed under $CKPT_DIR"
CHECKPOINTS=()
while IFS= read -r _ckpt_line || [[ -n "$_ckpt_line" ]]; do
  [[ -n "$_ckpt_line" ]] && CHECKPOINTS+=("$_ckpt_line")
done <<< "$_ckpt_list"
unset _ckpt_list _ckpt_line
if [[ ${#CHECKPOINTS[@]} -eq 0 ]]; then
  fail 1 "no checkpoints discovered under $CKPT_DIR"
fi

EVAL_DEVICE="${DEVICE:-cpu}"
ckpt_i=0
ckpt_n=${#CHECKPOINTS[@]}
for ckpt in "${CHECKPOINTS[@]}"; do
  ckpt_i=$((ckpt_i + 1))
  stem="$(basename "$ckpt" .pt)"
  for mode in chunk30 te; do
    set_phase "eval" "${ckpt_i}/${ckpt_n} ${stem} ${mode}"
    out_dir="$EVAL_ROOT/${stem}/${mode}"
    mkdir -p "$out_dir"
    eval_cmd=(
      python3 scripts/run_sim_eval.py
      --policy checkpoint
      --checkpoint "$ckpt"
      --episodes "$EVAL_EPISODES"
      --max-steps "$EVAL_MAX_STEPS"
      --randomize-box
      --output-dir "$out_dir"
      --device "$EVAL_DEVICE"
      --video-mode topdown
    )
    if [[ "$SAVE_VIDEO" -eq 1 ]]; then
      eval_cmd+=(--save-video)
    else
      eval_cmd+=(--no-save-video)
    fi
    if [[ "$mode" == "chunk30" ]]; then
      eval_cmd+=(--no-temporal-ensemble --n-action-steps "$N_ACTION_STEPS")
    else
      eval_cmd+=(--temporal-ensemble --temporal-ensemble-coeff 0.01 --n-action-steps 1)
    fi
    "${eval_cmd[@]}"
  done
done

# ---------------------------------------------------------------------------
# Phase: summarize
# ---------------------------------------------------------------------------
set_phase "summarize" "writing $SUMMARY_FILE"
python3 - "$EVAL_ROOT" "$SUMMARY_FILE" "$CKPT_DIR" "$RUN_NAME" "$EVAL_EPISODES" "$N_ACTION_STEPS" <<'PY'
import json
import statistics
from pathlib import Path
import sys

eval_root = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
ckpt_dir = Path(sys.argv[3])
run_name = sys.argv[4]
eval_episodes = sys.argv[5]
n_action_steps = sys.argv[6]


def median_pos_mm(metrics: dict) -> float | None:
    samples = metrics.get("samples") or []
    vals = [float(s["position_error_mm"]) for s in samples if "position_error_mm" in s]
    if not vals:
        summary = metrics.get("summary") or {}
        if "median_position_error_mm" in summary:
            return float(summary["median_position_error_mm"])
        return None
    return float(statistics.median(vals))


def fmt(v, digits=3):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


rows = []
order = []
for name in ("best_model", "best_model_te", "last"):
    order.append(name)
for p in sorted(eval_root.glob("step_*")):
    if p.is_dir():
        order.append(p.name)

all_initial_xy = []
for stem in order:
    for mode, label in (("chunk30", f"chunk{n_action_steps}"), ("te", "TE")):
        metrics_path = eval_root / stem / mode / "metrics.json"
        if not metrics_path.is_file():
            continue
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        summary = data.get("summary") or {}
        for sample in data.get("samples") or []:
            xy = sample.get("initial_box_xy")
            if xy is not None and len(xy) >= 2:
                all_initial_xy.append((float(xy[0]), float(xy[1])))
        rows.append(
            {
                "checkpoint": stem,
                "mode": label,
                "align": summary.get("align_success_rate"),
                "mean_pos": summary.get("mean_position_error_mm"),
                "median_pos": median_pos_mm(data),
                "grasp": summary.get("grasp_success_rate"),
                "metrics_path": str(metrics_path.relative_to(eval_root.parent)),
            }
        )

if all_initial_xy:
    xs = [xy[0] for xy in all_initial_xy]
    ys = [xy[1] for xy in all_initial_xy]
    unique_xy = len({(round(x, 6), round(y, 6)) for x, y in all_initial_xy})
    initial_pose_line = (
        f"- Initial box XY spread: "
        f"x=[{min(xs):.4f}, {max(xs):.4f}], "
        f"y=[{min(ys):.4f}, {max(ys):.4f}], "
        f"unique={unique_xy}/{len(all_initial_xy)}"
    )
else:
    initial_pose_line = "- Initial box XY spread: — (no initial_box_xy in metrics)"

lines = [
    f"# Pipeline results: `{run_name}`",
    "",
    f"- Checkpoint dir: `{ckpt_dir}`",
    f"- Eval episodes per cell: {eval_episodes}",
    f"- Chunk mode: `n_action_steps={n_action_steps}` (Temporal Ensembling off)",
    f"- TE mode: temporal ensembling on (`n_action_steps=1`)",
    initial_pose_line,
    "",
    "| Checkpoint | Mode | Align rate | Mean pos err (mm) | Median pos err (mm) | Grasp rate |",
    "| --- | --- | ---: | ---: | ---: | ---: |",
]
for r in rows:
    lines.append(
        f"| `{r['checkpoint']}` | {r['mode']} | {fmt(r['align'])} | "
        f"{fmt(r['mean_pos'], 1)} | {fmt(r['median_pos'], 1)} | {fmt(r['grasp'])} |"
    )
if not rows:
    lines.append("| — | — | — | — | — | — |")
lines.append("")
lines.append("Raw metrics live under `eval/<checkpoint>/<chunk30|te>/metrics.json`.")
lines.append("")
summary_path.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote {summary_path}")
print("\n".join(lines))
PY

# ---------------------------------------------------------------------------
# Phase: optional PR comment
# ---------------------------------------------------------------------------
if [[ -n "$PR_NUMBER" ]]; then
  set_phase "pr_comment" "gh pr comment $PR_NUMBER"
  if command -v gh >/dev/null 2>&1; then
    if ! gh pr comment "$PR_NUMBER" --body-file "$SUMMARY_FILE"; then
      echo "WARN: gh pr comment failed; summary left at $SUMMARY_FILE"
    fi
  else
    echo "WARN: gh not available; skipping PR comment (summary at $SUMMARY_FILE)"
  fi
else
  set_phase "pr_comment" "skipped (no --pr)"
fi

STATE="done"
PHASE="done"
PROGRESS="complete"
trap - ERR
write_status "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Pipeline OK"
echo "  status:  $STATUS_FILE"
echo "  summary: $SUMMARY_FILE"
echo "  log:     $LOG_FILE"
