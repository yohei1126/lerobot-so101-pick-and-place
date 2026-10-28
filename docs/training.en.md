# ACT Model Training and Inference Smoke Procedure

Train ACT (Action Chunking with Transformers) with LeRobot, save checkpoints, and smoke-test inference on a host Python 3.12+ virtual environment (aligned with LeRobot 0.6.x requirements).

## Device selection

When `--device` is omitted, preference order is MPS, CUDA, then CPU. If you explicitly request `mps` or `cuda` and that backend is unavailable, the process exits instead of silently falling back to CPU. This repository’s development VM has no Apple Silicon, so short-config checks run on CPU. Full training of 1,000+ steps should run on a machine with MPS.

## Training procedure

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# Prepare synthetic dataset (only if not already generated)
python scripts/generate_synthetic_dataset.py

# Train ACT with a ResNet18 vision backbone for 100 steps, save a checkpoint, then check inference shapes.
# This is an API smoke test; below_recommended_steps in training_metrics.json will be true.
python -m port_pick_align.training.train_act
```

Main artifacts from training (not Git-tracked):

- `data/synthetic/lerobot/`: synthetic dataset used for training
- `checkpoints/synthetic_act/best_model.pt`: smoke-trained model weights
- `checkpoints/synthetic_act/training_metrics.json`: per-step train loss, val L1, learning rate

The training loop splits data into train and validation and saves the weights with the lowest val L1 as `best_model.pt`. The split is episode-based (`dataset_from_index` / `dataset_to_index` from `meta.episodes`) so frames from the same episode do not mix across train and val. Datasets without episode metadata fall back to a frame-level split. Validation evaluates at most 32 batches by default (`--max-val-batches 0` for a full pass). Default validation interval is `--val-interval 100`. Learning rate uses cosine decay (disable with `--scheduler none`). Main arguments: `--dataset-root`, `--output-dir`, `--steps`, `--batch-size`, `--lr`, `--device`, `--val-ratio`, `--val-interval`, `--max-val-batches`.

## Full training on simulation demonstration data

Use Task 7.1 collection output `data/sim_expert/lerobot` as input. Prefer 1,000+ steps. Treat only post-run `training_metrics.json` as evidence for loss numbers; do not treat short-run losses as full-training results. Logs with `below_recommended_steps` true are smoke tests.

```bash
python -m port_pick_align.training.train_act \
  --preset sim \
  --steps 2000 \
  --batch-size 8 \
  --lr 1e-4

# Output:
#   checkpoints/sim_act/best_model.pt
#   checkpoints/sim_act/training_metrics.json
```

`--preset sim` selects checkpoints by closed-loop alignment rate. Execution uses `n_action_steps=30` (no Temporal Ensembling); default validation episode count is 10 (change to 10–20 with `--closed-loop-val-episodes`). Progress and best weights use lexicographic comparison of `(align_rate, -mean_position_error)` (when both align rates are 0%, prefer smaller error). At the same interval, Temporal Ensembling align rate and position error are logged as separate metrics, and the best TE weights are saved to `best_model_te.pt` under the same criterion. TE does not affect `best_model.pt` selection, but improvement on either chunk30 or TE resets the early-stop counter. Disable with `--closed-loop-te-episodes 0`. Every 500 steps a `step_XXXXX.pt` is kept; after `--min-steps` (default 3000), early stop triggers if neither closed-loop selection nor TE improves for 10 pulses (change with `--checkpoint-interval` / `--early-stop-patience` / `--min-steps`; patience 0 turns it off). Cosine decay floor is 10% of peak LR.

Gripper loss weight stays at 5. On the pad pose, closed place and open release share the same arm target, so L1 leans toward a conditional mean of the gripper dimension. Raising the weight does not move that mean. The release threshold 0.90 is also unchanged: intermediate commands drop the box mid-carry. The simulator does not release on an open command until near the pad (within 10 cm), and does not snap to pad center on release (final box XY / yaw are evaluated as-is). On the demonstration side, place an open static release after a closed approach+place longer than `n_action_steps=30`.

If memory is tight, lower `--batch-size`. CPU loop-check example (not a substitute for full training):

```bash
python -m port_pick_align.training.train_act \
  --preset sim \
  --steps 2 \
  --batch-size 1 \
  --val-interval 1 \
  --device cpu \
  --skip-infer
```

## Demonstration trajectory design and collection precautions

To ensure robust imitation learning (ACT) on this task, the simulation expert demonstrations incorporate the following key design requirements:

- **Yaw alignment during carry:** Box yaw is progressively aligned toward the target pad during the lift and carry phase to avoid sudden rotations near the surface.
- **Approach descent and static release:** The descent approach segment from above the pad and the subsequent static release segment are extended to be longer than the action chunk length (`n_action_steps=30`). Datasets lacking these segments tend to suffer from early release or stalled transports before reaching the pad.
- **Near-pad release gating:** Forced teleportation/snapping to the pad center is disabled; the simulator strictly evaluates the final box position against the pad coordinate thresholds.

When recollecting demonstrations or retraining, ensure that the active collection script with the extended approach segments is used. Collect and train on Mac (MPS); do not run training jobs in cloud CI environments.

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,training]"

python scripts/collect_sim_dataset.py \
  --episodes 100 \
  --output data/sim_expert/lerobot_post41

caffeinate -dimsu python -X faulthandler -m port_pick_align.training.train_act \
  --preset sim \
  --dataset-root data/sim_expert/lerobot_post41 \
  --output-dir checkpoints/sim_act_post41 \
  --steps 5000 \
  --batch-size 8 \
  --device mps \
  --skip-infer

# Success criterion is chunk30. Best TE is best_model_te.pt.
DEVICE=mps EPISODES=20 N_ACTION_STEPS=30 \
  ./scripts/run_phase15_benchmark.sh checkpoints/sim_act_post41/best_model.pt

# Collect → train → evaluate all checkpoints × chunk30/TE in one shot (nohup OK):
# Details and status.json / summary.md: see README section on batch collect → train → eval.
nohup ./scripts/run_pipeline.sh --run post41 --device mps --pr N \
  > results/post41/pipeline.log 2>&1 &
```

In `training_metrics.json`, `closed_loop_selection_exec` is `n_action_steps_30` and `closed_loop_te_used_for_selection` is false. `best_closed_loop_te_align_rate` and `te_checkpoint` are the best TE; `stopped_early` indicates early stop. Also see `closed_loop_te_align_rate` in `history`.

## Inference-only smoke

To re-run only the inference API smoke test against an existing checkpoint:

```bash
python -m port_pick_align.training.train_act --infer-only
```

## Tensor shapes and I/O contract

Observation keys and output action-chunk tensor shapes follow `configs/contract.yaml`.

- Camera image inputs (`observation.images.top` / `wrist`): `(B, 3, 480, 640)`, float tensors in `[0.0, 1.0]`
- Joint state input (`observation.state`): `(B, 6)`
- Output action chunk (`action`): `(30, 6)` (30-step target joint-position commands)

