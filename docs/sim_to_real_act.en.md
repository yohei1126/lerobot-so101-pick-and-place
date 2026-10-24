# Phase 2-2: Run a sim-trained ACT on a real SO-101 Follower

Do **not** load a sim checkpoint onto the real robot as-is. This repository’s wrapper converts units, gripper, and cameras. Shared bring-up steps: [real_robot_bringup.md](real_robot_bringup.en.md). Unit background: [units.md](units.en.md).

## Conversion rules (implementation)

| Item | Sim / contract | Real LeRobot `so101_follower` |
| --- | --- | --- |
| Joint order | `shoulder_pan` … `gripper` (6) | Same order; keys are `*.pos` |
| Arm 5 axes | **radians** | **degrees** (`use_degrees=True`) |
| Gripper | **radians** (closed ≈ 0, open ≈ 1.2) | **0–100** |
| Cameras | `top` / `wrist`, 640×480 per contract; datasets are RGB | Same names. OpenCV default is RGB. Resize if resolution differs |

**Gripper polarity (default):** Match LeRobot 0.6.1 `gripper_velocity_to_joint`: **higher `gripper.pos` = more closed** (0 ≈ open, 100 ≈ closed). Contract radian upper bound ↔ open, lower bound ↔ closed. To invert, use `--no-gripper-closed-is-high` (“open percent” meaning in `port_pick_align.units`).

**Safety:** clamp on the sim side with contract `joint_limits` → convert to real units → optional per-step caps (default arm 5°, gripper 10). In live mode, LeRobot `max_relative_target` can also be used.

**Missing cameras:** the sim policy expects exactly `top` and `wrist`. Either missing raises an error. A third camera is unused and not required.

Implementation: `port_pick_align.deploy.conversion` / `sim_policy_wrapper` / `run_sim_policy_on_real`.

## Prerequisites

- Mac M4, LeRobot **0.6.1**, Follower calibration id=`follower`
- Install this package editable into the real-robot venv (`$LEROBOT_HW_ROOT/.venv`)
- Sim checkpoint (e.g. `best_model.pt` from `train_act --preset sim`)
- Port env: `PORT_FOLLOWER` (`lerobot-find-port`)
- Cameras: top=OpenCV index 1, wrist=index 0, 640×480@30 (same as bring-up)

```bash
export LEROBOT_HW_ROOT=<path>
source "$LEROBOT_HW_ROOT/.venv/bin/activate"
cd "/path/to/lerobot-so101-pick-and-place"
pip install -e "port_pick_align/[training,feetech]"
```

Pass host paths via env or CLI placeholders; do not hardcode absolute `/Users/...` paths.

## Step 1: Dry-run (required)

Read observations and print converted actions only. **Do not send motor commands.**

```bash
export LEROBOT_HW_ROOT=<path>
source "$LEROBOT_HW_ROOT/.venv/bin/activate"
cd "/path/to/lerobot-so101-pick-and-place"

export PORT_FOLLOWER=<follower-serial>  # result of lerobot-find-port
CKPT="$LEROBOT_HW_ROOT/outputs/sim_act/best_model.pt"  # or --checkpoint <path>

python -m port_pick_align.deploy.run_sim_policy_on_real \
  --checkpoint "$CKPT" \
  --port "$PORT_FOLLOWER" \
  --robot-id follower \
  --device mps \
  --dry-run \
  --episode-time-s 20 \
  --max-delta-deg 5 \
  --max-delta-gripper 10
```

Confirm:

- `DRY` lines appear with no exceptions
- Arm angles roughly within ±110°, gripper in 0–100
- If jumps appear, suspect pose, cameras, or polarity (`--no-gripper-closed-is-high` is a last resort)

## Step 2: Live (slow, short)

1. Follower in a safe pose. No obstacles. Camera stand ≥ ~35 cm from the base.
2. **Keep a hand on the 12V power switch.** Kill power immediately on anything abnormal.
3. Support the arm before start. Torque-off on exit can let it drop.

```bash
python -m port_pick_align.deploy.run_sim_policy_on_real \
  --checkpoint "$CKPT" \
  --port "$PORT_FOLLOWER" \
  --robot-id follower \
  --device mps \
  --episode-time-s 20 \
  --max-delta-deg 3 \
  --max-delta-gripper 8 \
  --robot-max-relative-target 3 \
  --n-action-steps 1
```

First run: prefer `--max-delta-deg 3` and `--episode-time-s 15`–`20`. Relax slightly only if that looks safe.

## What to keep in the report on failure

| Item | Content |
| --- | --- |
| Command line | Full dry-run / live command (ports may be redacted) |
| Checkpoint | Path; sim training step / align rate if known |
| Symptom | e.g. jumps at start, inverted gripper, camera KeyError, latency |
| Log excerpt | First `DRY`/`LIVE` lines and those near the anomaly |
| Polarity trial | Whether `--no-gripper-closed-is-high` was used and any difference |
| Safety actions | Whether 12V was cut; contact or overload |
| Environment | LeRobot version, `--device`, camera indices |

## Unit tests (no hardware)

```bash
cd port_pick_align && pytest -m unit tests/test_sim_to_real_conversion.py -q
```

## Limits (how to set expectations)

- Appearance, friction, and calibration differ between sim and real. Success is not required.
- This path is separate from `lerobot-rollout` for policies trained on real demos (those units are already real-side).
- This wrapper targets **`train_act` checkpoints under the sim radian contract**.
