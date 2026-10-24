# SO-101 Real-Robot Bring-up and Teleop Recording (Mac / LeRobot 0.6.1)

This procedure drives a WowRobo pre-assembled SO-101 (Leader / Follower) with LeRobot 0.6.1 on a Mac through teleoperation and camera-backed demo recording. Equipment list and work-area contract dimensions are authoritative in [hardware.md](hardware.en.md). Primary references: [SO-101](https://huggingface.co/docs/lerobot/so101), [Cameras](https://huggingface.co/docs/lerobot/cameras), [Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots).

Measured results reflected here:

- Bring-up on 2026-10-17/18 (connection via UGREEN hub, simultaneous dual-camera streaming, teleop, `lerobot-record` trials)
- **Main recording on 2026-10-22 / 23** (table dimensions, camera framing, keyboard controls, motor temperature, clean-set creation)

Dataset summary: [real_dataset_so101_pick_sponge_main_20261023.md](real_dataset_so101_pick_sponge_main_20261023.en.md). Sim→real unit conversion: [sim_to_real_act.md](sim_to_real_act.en.md) / [units.md](units.en.md).

## Prerequisites and environment

Use a **venv separate from this repository’s `.venv`** for the real robot (avoid interfering with training jobs or sim dependencies).

```bash
# Example: create a dedicated venv
python3.12 -m venv "$HOME/work/lerobot-hw/.venv"
source "$HOME/work/lerobot-hw/.venv/bin/activate"
pip install -U pip
pip install 'lerobot[feetech]==0.6.1'
# Add for recording / visualization / training
pip install 'lerobot[dataset,viz]==0.6.1'
# As needed: pip install 'lerobot[hardware,training]==0.6.1'
```

| Item | Value |
| --- | --- |
| Python | 3.12 |
| LeRobot | 0.6.1 (`pip install 'lerobot[feetech]'`) |
| Host | Apple Silicon Mac (e.g. MacBook Pro M4) |
| Robot types | `--robot.type=so101_follower` / `--teleop.type=so101_leader` |
| Calibration ids | `follower` / `leader` (same for every later command) |

Prefer `$HOME` over `~` in docs (`~` right after `--dataset.root=` is not expanded).

## Hardware (as of 2026-10-22)

| Item | Detail |
| --- | --- |
| Host | MacBook Pro M4. Arms and cameras connected via a USB-C hub |
| Leader | Has a handle. **No gripper**. Power **5V**. Port example `/dev/tty.usbmodem5B790143611` |
| Follower | **Has a gripper**. Power **12V**. Port example `/dev/tty.usbmodem5B8E1163071` |
| Fixturing | Clamp both arm bases to the table edge with C-clamps |
| Top camera | Logitech C920. Mounted on a VIJIM LS08 camera arm, clamped to the table edge |
| Wrist camera | Kit-included USB2.0_CAM1 (Follower gripper side) |

**Never swap adapters.** Before plugging in, point-check the label voltage against the board side. The board red LED may stay on after unplugging DC (USB power). Drive torque requires the DC adapter. Follower 12V must be ON (LED lit). Measured 2026-10-18: Follower ≈ 12.6 V / Leader ≈ 5.5 V.

**Ports can change after unplug/replug.** Before work, re-check with `ls /dev/tty.usbmodem*` and `lerobot-find-port`.

### Camera indices (OpenCV / LeRobot)

| Camera | OpenCV index (typical 2026-10-18 / 22) | Resolution / fps |
| --- | ---: | --- |
| wrist (USB2.0_CAM1) | 0 | 640×480 / 30 |
| top (C920) | 1 | 640×480 / 30 |

**Indices can also shift after unplug/replug.** Confirm with `lerobot-find-cameras opencv` and `outputs/captured_images/opencv_*.png` (ffmpeg / avfoundation numbers differ from OpenCV).

Rerun entity names when displaying: `observation.top` and `observation.wrist`.

## Safety

- At teleop start, the Follower snaps toward the Leader pose. Align both arms before starting.
- Stopping (Ctrl+C) disables torque (`disable_torque_on_disconnect`). Gravity drop is possible. Support the Follower by hand before stopping.
- In an emergency, unplug the Follower **12V plug** first. Keep the power plug within immediate reach.
- **Keep the camera stand outside the Follower workspace** (roughly ≥ 35 cm from the base). Contact with the stand has occurred during teleop.

## Table layout (measured 2026-10-22)

All distances are from the **left edge** of the table. Table width is approximately **134 cm**. The sponge was shifted forward to keep clearance from the Follower base. Mark paper and sponge positions with masking tape.

| Target | From left edge | From near edge (when applicable) |
| --- | ---: | ---: |
| Leader arm left edge | 28 cm | — |
| White paper (portrait) | 56 cm | 13 cm |
| Follower arm left edge | 78 cm | — |
| Yellow sponge | 81 cm | 29 cm |
| Top camera pole | 111 cm (23 cm from right edge) | — |

Top view (left edge = 0 cm, near edge at bottom):

```text
左端 0 cm                                              右端 ~134 cm
+------------------------------------------------------------------+
|                                                                  |
|   Leader          紙(白)         Follower      スポンジ(黄)   C920 |
|   28cm            56cm /13cm前    78cm          81cm /29cm前  111cm|
|     [====]         [紙]            [====]         [スポ]      |pole|
|                                                                  |
|                         （手前縁）                                |
+------------------------------------------------------------------+
```

Coordinate frame (same as sim / [hardware.md](hardware.en.md)): origin at Follower base center, +x forward, +y left, +z up. Keep the reachable volume (≈ 45 cm radius from the base) free of obstacles and liquids.

## Top camera framing

The top view must show all of:

1. White paper
2. Yellow sponge
3. Follower base and gripper work path

Earlier framing was too tight and cut off the gripper path. Before recording, confirm in Rerun (`observation.top` / `observation.wrist`). If the C920 FOV is tight, lower it slightly and move it back / tilt it downward.

## USB and port identification

```bash
source "$HOME/work/lerobot-hw/.venv/bin/activate"
# Run with USB and power connected to both arms
lerobot-find-port
# When prompted, unplug only the USB of the arm you want to identify, then Enter
# Record the shown port, replug USB. Repeat for the other arm (one at a time)
```

| Arm | Port (recorded 2026-10-18 / 22) | Power | id |
| --- | --- | --- | --- |
| Leader | `/dev/tty.usbmodem5B790143611` | 5V | leader |
| Follower | `/dev/tty.usbmodem5B8E1163071` | 12V | follower |

```bash
export PORT_FOLLOWER=/dev/tty.usbmodem5B8E1163071
export PORT_LEADER=/dev/tty.usbmodem5B790143611
```

**On first bring-up, Leader / Follower ports were swapped, so the gripper arm moved as the Leader during teleop.** Re-identify ports and redo calibration.

## Motor ID check

On WowRobo pre-assembled kits, STS3215 IDs 1–6 and baud rate 1,000,000 are often already set. Scan the port before writing; if correct, skip `lerobot-setup-motors`.

```bash
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('$PORT_FOLLOWER'))"
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('$PORT_LEADER'))"
```

- Healthy example: `{1000000: [1, 2, 3, 4, 5, 6]}` → proceed to calibration.
- If IDs are missing or only another baud rate is found, check power/wiring, then run `lerobot-setup-motors` per the official docs if needed ([SO-101](https://huggingface.co/docs/lerobot/so101)).

## Calibration

If the host has no calibration JSON, later connect commands start calibration automatically. Run it explicitly.

```bash
lerobot-calibrate \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower

lerobot-calibrate \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader
```

Practical notes:

- **Move only the arm whose port is currently being calibrated.** Moving the other can cause `same min and max` failures.
- Start pose: each joint near mid-range (roughly an L shape).
- Move every joint except `wrist_roll` fully both ways. Avoid wrapping the wrist cable.
- Gripper: full open to full close. The Leader trigger travel is inherently short.
- Save locations (default `HF_LEROBOT_HOME=~/.cache/huggingface/lerobot`):
  - `~/.cache/huggingface/lerobot/calibration/robots/so_follower/follower.json`
  - `~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/leader.json`
- On re-run, you get a prompt to reuse the existing file or press `c` to recalibrate.

## Teleoperation

Before starting, match the Leader to the same rest pose as the Follower.

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader
```

Optional: `--robot.max_relative_target=10` (per-step limit in degrees) or `--teleop_time_s=60`. Support the Follower by hand before stopping.

Checks: each joint follows in the same direction, gripper opens/closes, no abnormal noise or vibration.

### With camera display

```bash
lerobot-find-cameras opencv
# Images land in outputs/captured_images/opencv_*.png. Indices can change after unplug/replug
```

On macOS, camera permission is required the first time (System Settings → Privacy & Security → Camera). **iPhone Continuity Camera can steal an index.** Disconnect it, and turn Continuity Camera off if needed.

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader \
  --display_data=true
```

## Pre-recording checklist (required)

**Run this immediately before every `lerobot-record`.**

1. **Stop any running `lerobot-teleoperate`.** Camera and serial contention will occur.
2. Teleop briefly with the same robot / teleop / cameras flags and confirm in Rerun.
3. Stop teleop after the check, then proceed to recording.

| # | Check |
| --- | --- |
| (a) | **top:** paper, sponge, and Follower base / gripper path are in frame |
| (b) | **wrist:** gripper tip and sponge are visible on approach |
| (c) | No contact with stand / clamps along the full pick-and-place path |
| (d) | No camera warnings. Loop runs stably |
| (e) | Sponge and paper are at the taped start positions |

## Demo recording rules (finalized 2026-10-22/23)

- **1 episode = 1 pick-and-place.** Earlier trials that placed twice in one episode were discarded.
- Start and end in the **same rest pose**.
- After placing the sponge on the paper, end the episode early with the **Right arrow** (the last ~10–17 s of `episode_time_s=25` often had a stationary arm).
- Move slowly and consistently.
- **Rest about every 10 episodes**, power off the Follower, and cool the motors. After ~20 continuous episodes, Follower `shoulder_lift` lagged commands and mean `|action-state|` rose to about **10–12°** (normally about **1.5°**).

## Recording script

Use the repository’s `scripts/record_real_so101.sh` (executable).

```bash
# Append N episodes. Auto-resumes if the dataset already exists
scripts/record_real_so101.sh [N]
```

| Item | Value |
| --- | --- |
| Default N | 50 |
| Dataset root | `$HOME/work/lerobot-hw/datasets/so101_pick_sponge_main_20261020` |
| repo_id | `yohei1126/so101_pick_sponge_main` |
| Task string | `Pick up the yellow sponge and place it on the white paper` |
| episode / reset | 25 s / 10 s, fps 30 |
| Logs | `$HOME/work/lerobot-hw/outputs/record_main_*.log` (cwd is `lerobot-hw`) |

The script `pkill`s `lerobot-teleoperate` before start. Ports and camera indices are hardcoded in the script. Edit them after unplug/replug, or override for your environment.

### Run in an interactive terminal (required)

Keyboard controls:

| Key | Meaning |
| --- | --- |
| Right | End current episode and go to next |
| Left | Re-record |
| Esc | Stop recording |

**Keyboard input does not work under background / non-interactive launch.** Run in an interactive macOS Terminal. Terminal may need Accessibility and Input Monitoring permissions.

If you must detach, use a **new session** (`start_new_session` / `setsid`), not `nohup`. `nohup` jobs have died after the parent exited.

### Audio cues

`--play_sounds` goes to the macOS **default output device**. On the working Mac, a Bluetooth Jabra headset was the default. Confirm the output device before recording.

## Manual `lerobot-record` example

Flags equivalent to the script:

```bash
source "$HOME/work/lerobot-hw/.venv/bin/activate"
cd "$HOME/work/lerobot-hw"

lerobot-record \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader \
  --dataset.repo_id=yohei1126/so101_pick_sponge_main \
  --dataset.single_task='Pick up the yellow sponge and place it on the white paper' \
  --dataset.num_episodes=10 \
  --dataset.episode_time_s=25 \
  --dataset.reset_time_s=10 \
  --dataset.fps=30 \
  --dataset.no_stamp=true \
  --dataset.push_to_hub=false \
  --dataset.root=$HOME/work/lerobot-hw/datasets/so101_pick_sponge_main_20261020 \
  --display_data=true \
  --play_sounds=true \
  --resume=true
```

- Append to an existing root with `--resume=true` (the script sets true automatically if the root exists).
- In dataset v3.0, videos are concatenated per camera into `videos/observation.images.<cam>/chunk-000/file-000.mp4`.
- Keep the dataset itself outside git (on the Mac).

## Shutdown

1. Stop teleop / recording (Ctrl+C or Esc). Support the Follower by hand.
2. **Unplug the 12V / 5V adapters** (DC first, then USB).
3. Carry by the base. Do not lift by the cables.

## Next steps

Do not load a sim checkpoint onto the real robot directly. Sim policies use **radians** for joints; the real Follower uses **degrees** for body joints and **0–100** for the gripper: the I/O contracts do not match.

1. Demo recording → clean-set creation ([real_dataset_so101_pick_sponge_main_20261023.md](real_dataset_so101_pick_sponge_main_20261023.en.md))
2. Train ACT on real data: `python -m port_pick_align.training.train_act` ([training.md](training.en.md)). Run on MPS. For sim data use `train_act --preset sim`
3. Phase 2-2 (sim→real): dry-run with the unit-conversion wrapper → slow live. [sim_to_real_act.md](sim_to_real_act.en.md)
4. Real-trained policies (ACT / SmolVLA): no unit conversion. dry-run → live via **[real_robot_deploy.md](real_robot_deploy.en.md)** (`scripts/run_act_real.sh` / `scripts/run_smolvla_real.sh`). Alternatively `lerobot-rollout`. First runs: keep `--max-relative-target` / `--max-delta-deg` small, slow, and short

### Phase 2-2 quick links (details in sim_to_real_act.md)

```bash
# Dry-run (motors not driven); always do this first
python -m port_pick_align.deploy.run_sim_policy_on_real \
  --checkpoint "$HOME/work/lerobot-hw/outputs/sim_act/best_model.pt" \
  --port "$PORT_FOLLOWER" \
  --dry-run \
  --device mps \
  --episode-time-s 20

# Live (keep a hand on the 12V switch. First run: smaller max-delta)
python -m port_pick_align.deploy.run_sim_policy_on_real \
  --checkpoint "$HOME/work/lerobot-hw/outputs/sim_act/best_model.pt" \
  --port "$PORT_FOLLOWER" \
  --device mps \
  --episode-time-s 20 \
  --max-delta-deg 3 \
  --robot-max-relative-target 3
```

### Real-trained policies (recommended: repository runners)

Details, safety settings, and recommended live flags: **[real_robot_deploy.md](real_robot_deploy.en.md)**.

```bash
# ACT (real train_act checkpoint, no unit conversion); default is dry-run
./scripts/run_act_real.sh --device mps --episode-time-s 15
# First live example
./scripts/run_act_real.sh --live --device mps \
  --max-delta-deg 2 --max-delta-gripper 3 --n-action-steps 10 --episode-time-s 15

# SmolVLA fine-tune
./scripts/run_smolvla_real.sh --live --device mps --n-action-steps 25 --episode-time-s 15
```

### Alternative: lerobot-rollout (no unit conversion)

```bash
lerobot-rollout \
  --strategy.type=base \
  --policy.path=outputs/train/act_so101_real/checkpoints/last/pretrained_model \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}" \
  --robot.max_relative_target=5 \
  --task="Pick up the yellow sponge and place it on the white paper" \
  --duration=30
```

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Port missing / changes | Confirm data-capable USB-C. Bypass hub and connect direct. `ls /dev/tty.usbmodem*`. Re-identify after unplug/replug |
| Ports swapped (gripper arm acts as Leader) | Re-run `lerobot-find-port` one arm at a time; recalibrate |
| `Permission denied` / `Resource busy` | Kill the process holding the port with `lsof`. Stop `lerobot-teleoperate` before recording |
| `Missing motor IDs` | Check `scan_port`, 12V/5V, 3-pin wiring, port swap |
| Teleop runs but Follower does not move | Confirm 12V adapter ON (LED lit) |
| Top camera fails to open / times out | Can happen right after freeing a prior process. **Retry** often fixes it |
| Keyboard (Right / Left / Esc) ignored | Run in an interactive Terminal. Grant macOS Accessibility / Input Monitoring |
| No audio cues | Check macOS default output device (Bluetooth headset, etc.) |
| `nohup` recording dies | Detach with a new session (`start_new_session` / `setsid`). Interactive Terminal is the main path |
| torchcodec fails on missing FFmpeg dylib | LeRobot **falls back to pyav**. Long errors are harmless |
| `AVFFrameReceiver is implemented in both ...` | Harmless. Can appear on successful recordings too |
| `shoulder_lift` tracking lag (mean \|action-state\| ≈ 10–12°) | Stop continuous recording; power off Follower and cool. Rest about every 10 epi |
| Camera index shifts / only built-in visible | Turn Continuity Camera off. Confirm with `lerobot-find-cameras opencv` and saved images |
| rerun error with `--display_data` | `pip install 'lerobot[viz]==0.6.1'` |
| `lerobot-record` import error | `pip install 'lerobot[dataset]==0.6.1'` |
| `--dataset.root=~/...` fails | `~` is not expanded. Use `$HOME` or an absolute path |
| Follower hits the camera stand | Keep the pole ≥ ~35 cm from the base. Paper on the opposite side of the pole. Mark with tape |

## References

- [hardware.md](hardware.en.md): purchased equipment and work-area dimensions
- [real_dataset_so101_pick_sponge_main_20261023.md](real_dataset_so101_pick_sponge_main_20261023.en.md): clean28 dataset summary
- [sim_to_real_act.md](sim_to_real_act.en.md): Phase 2-2: sim ACT → real Follower (conversion wrapper)
- [real_robot_deploy.md](real_robot_deploy.en.md): real-trained ACT / SmolVLA dry-run → live
- [units.md](units.en.md): radians / degrees / gripper 0–100
- [training.md](training.en.md): ACT training
- [plan_b.md](plan_b.en.md): fallback when real hardware is blocked
- [LeRobot SO-101](https://huggingface.co/docs/lerobot/so101)
- [LeRobot Cameras](https://huggingface.co/docs/lerobot/cameras)
- [Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots)
