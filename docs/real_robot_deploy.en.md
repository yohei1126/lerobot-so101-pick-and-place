# Deploying Real-Trained Policies (ACT / SmolVLA)

Procedure to dry-run → live on the SO-101 Follower with ACT trained from real teleop
(`port_pick_align.training.train_act`) and SmolVLA fine-tuned from
`lerobot/smolvla_base`. Shared bring-up: [real_robot_bringup.md](real_robot_bringup.en.md).
Do **not** use the sim-trained ACT rad↔deg conversion wrapper (that path is [sim_to_real_act.md](sim_to_real_act.en.md)).

## Prerequisites

| Item | Value |
| --- | --- |
| Host | Apple Silicon Mac / LeRobot **0.6.1** / MPS |
| Real-robot venv | `$LEROBOT_HW_ROOT` (default `$HOME/work/lerobot-hw`) |
| Cameras | top=OpenCV index **1**, wrist=index **0**, 640×480@30 (2026-10-25 cable swap, still current) |
| Table | [Current layout (140 × 70 cm)](real_robot_bringup.en.md#current-table-layout-2026-10-26). Do not use legacy dimensions |
| Task string | `Pick up the yellow sponge and place it on the white paper` |

Override paths with environment variables (do not hardcode absolute `/Users/...` paths).

| Variable | Purpose |
| --- | --- |
| `LEROBOT_HW_ROOT` | Root for datasets, outputs, and venv |
| `PORT_FOLLOWER` | Follower serial port |
| `ACT_REAL_CHECKPOINT` / `ACT_REAL_DATASET` | For ACT |
| `SMOLVLA_CHECKPOINT` / `SMOLVLA_DATASET` / `SMOLVLA_TASK` | For SmolVLA |

```bash
source "$HOME/work/lerobot-hw/.venv/bin/activate"
cd "/path/to/lerobot-so101-pick-and-place"
pip install -e "port_pick_align/[training,feetech]"
export PORT_FOLLOWER=/dev/tty.usbmodem5B8E1163071   # from lerobot-find-port
```

## Preflight checks

Run `scripts/preflight_real_so101.sh` before deployment or recording to verify port connections and dual-camera feeds:

```bash
./scripts/preflight_real_so101.sh
```

For recorded dataset quality checks (missing frames, outlier velocities, duration), use `scripts/qc_teleop_dataset.py`. See [real_robot_bringup.md](real_robot_bringup.en.md#qc-a-recorded-dataset) for details.

## Safety model

| Mode | Connection | `send_action` | On exit |
| --- | --- | --- | --- |
| **dry-run (default)** | Bus read-only + cameras. No `connect()`/`configure()`/torque writes | Not called | Bus disconnect also uses `disable_torque=False` |
| **`--live`** | Normal `robot.connect()` + `max_relative_target` | Sent after clamping | `disconnect()` → **torque OFF. Support the arm by hand** |

Additional clamps (both modes):

- `--max-delta-deg` (default 3): per-step limit for the 5 arm joints (degrees)
- `--max-delta-gripper` (default 5): per-step limit for gripper 0–100
- `--max-relative-target` (default 5, live only): LeRobot relative-target limit

Interrupt the loop with Ctrl-C / SIGTERM. In an emergency, unplug the Follower **12V**.

## Procedure overview (dry-run → live)

1. Confirm bring-up is done (ports, calibration, camera indices).
2. **offline-check** (optional, no robot): MAE of predictions vs dataset frames.
3. **dry-run** (required): arm does not move. Confirm state / target / safe in logs.
4. **live** (first run: short, small deltas): keep a hand on the 12V switch; support the arm on exit.

## ACT (real-trained, no unit conversion)

Checkpoint is `train_act`’s `best_model.pt` (no normalization; degrees / gripper 0–100).
Do **not** apply the rad↔deg conversion from `run_sim_policy_on_real`.

```bash
# Offline MAE (no robot)
./scripts/run_act_real.sh --offline-check --device mps

# Dry-run
./scripts/run_act_real.sh --device mps --episode-time-s 15

# Recommended first live
./scripts/run_act_real.sh --live --device mps \
  --max-delta-deg 2 --max-delta-gripper 3 \
  --n-action-steps 10 --episode-time-s 15
```

Equivalent Python module call:

```bash
python -m port_pick_align.deploy.act_real --live --max-delta-deg 2 ...
```

## SmolVLA (fine-tune)

Load the train-time pre/post-processors and rename `top`→`camera1`, `wrist`→`camera2`.
Because `empty_cameras=0`, do **not** pass camera3 (it was also skipped at train time).

```bash
# Offline
./scripts/run_smolvla_real.sh --offline-check --device mps

# Dry-run
./scripts/run_smolvla_real.sh --device mps --episode-time-s 15

# Recommended first live (run 25 of chunk 50, then replan)
./scripts/run_smolvla_real.sh --live --device mps \
  --n-action-steps 25 --episode-time-s 15 \
  --max-delta-deg 2 --max-delta-gripper 3
```

## Launching SmolVLA fine-tune

For macOS. Detach with `caffeinate` + `start_new_session`.

```bash
./scripts/train_smolvla.sh 10000 8
# Log: $LEROBOT_HW_ROOT/outputs/logs/smolvla_so101_clean28_<TS>.log
```

`rename_map` and `dataset.video_backend=pyav` are fixed in the script. Dataset root / repo id can be changed via environment variables.

## Verification notes on Mac (as of 2026-10-23)

The following are **offline / dry-run measurements on Mac / MPS** (2026-10-23). For real live rollout procedures and checkpoint selection, see [real_eval_protocol.ja.md](real_eval_protocol.ja.md) (Japanese).

| Item | ACT | SmolVLA |
| --- | --- | --- |
| Offline MAE (first step) | ≈ **0.57 deg** | ≈ **1.09 deg** |
| Inference latency | ≈ **24 ms**/inference | ≈ **335 ms**/chunk |

## Alignment with the recording script

Keep ports, camera indices, and task string consistent across [scripts/record_real_so101.sh](../scripts/record_real_so101.sh),
[real_robot_bringup.md](real_robot_bringup.en.md), and these deploy defaults:

| Item | Value |
| --- | --- |
| Follower port example | `/dev/tty.usbmodem5B8E1163071` |
| Leader port example | `/dev/tty.usbmodem5B790143611` |
| top / wrist index | 1 / 0 |
| Task | `Pick up the yellow sponge and place it on the white paper` |

Recording steps stay in [real_robot_bringup.md](real_robot_bringup.en.md) / `scripts/record_real_so101.sh` (#75). Before a demo session, use the pre-recording checklist on that page. After recording, score the root with `scripts/qc_teleop_dataset.py` (same page).

## References

- [real_robot_bringup.md](real_robot_bringup.en.md)
- [sim_to_real_act.md](sim_to_real_act.en.md): sim ACT only (separate from this procedure)
- [units.md](units.en.md)
- Implementation: `port_pick_align.deploy.real_common` / `act_real` / `smolvla_real`
