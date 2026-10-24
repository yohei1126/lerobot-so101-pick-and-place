# SO-101 Real-Robot Bring-up (Mac / LeRobot 0.6.1)

This procedure drives a WowRobo pre-assembled SO-101 (Leader / Follower) with LeRobot 0.6.1 on a Mac and verifies teleoperation through camera-backed recording. Equipment list and work-area dimensions are authoritative in [hardware.md](hardware.en.md). Primary references: [SO-101](https://huggingface.co/docs/lerobot/so101), [Cameras](https://huggingface.co/docs/lerobot/cameras), [Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots).

Reflects bring-up on 2026-10-17/18 and **real-hardware validation on the evening of 2026-10-18** (connection via UGREEN hub, simultaneous dual-camera streaming, 60 Hz teleop, two successful `lerobot-record` runs including 23:48–23:50 SGT).

## Prerequisites and environment

Use a **venv separate from this repository’s `.venv`** for the real robot (avoid interfering with training jobs or sim dependencies).

```bash
# Example: create a dedicated venv
python3.12 -m venv ~/work/lerobot-hw/.venv
source ~/work/lerobot-hw/.venv/bin/activate
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

## Safety and arm identification

| Arm | How to tell | Power |
| --- | --- | --- |
| Leader | Has a handle. **No gripper jaws** | **5V** adapter |
| Follower | **Has a gripper** | **12V** adapter |

- **Never swap adapters.** Before plugging in, point-check the label voltage against the board side.
- The board red LED may stay on after unplugging the DC adapter; that is USB power and is normal. Drive torque requires the DC adapter.
- **Always turn the Follower 12V adapter ON (LED lit).** If left OFF, teleop appears to run but the Follower does not move. Measured 2026-10-18: Follower ≈ 12.6 V / Leader ≈ 5.5 V.
- At teleop start, the Follower snaps toward the Leader pose. Align both arms before starting (Leader near neutral; joints at calibration-range ends will not change commanded values).
- Stopping (Ctrl+C) disables torque (`disable_torque_on_disconnect`). Gravity drop or small motion is normal. Support the Follower by hand before stopping.
- In an emergency, unplug the Follower **12V plug** first. Keep the power plug within immediate reach.
- **Keep the camera stand outside the Follower workspace** (roughly ≥ 35 cm from the base). Place paper on the opposite side of the stand. Mark positions with tape. Contact with the stand has occurred during teleop.

## Fixturing and work layout

1. Clamp both arm bases to the table edge with C-clamps.
2. Keep the reachable volume (≈ 45 cm radius from the base) free of obstacles and liquids.
3. Coordinate frame matches sim / [hardware.md](hardware.en.md). **Origin is the Follower base center; +x forward, +y left, +z up** (confirm in `so101_tabletop.xml` / `env.py`).

| Item | Placement |
| --- | --- |
| Object | Sponge (≈ 5×4×4 cm) |
| Start area | 8×8 cm, center (28, −8) cm |
| Goal pad | 8×6 cm (colored paper / felt taped down), center (35, +12) cm, long edge parallel to x. Place away from the camera pole |
| Top camera (C920) | On VIJIM LS08 arm, via USB-A hub. Sponge, paper, and gripper work area must be in frame (trial3 first frames still had gripper out of frame → lower slightly, move back, and/or tip downward) |
| Wrist camera | Kit included (USB2.0_CAM1 / Sonix 05a3:9230). Mount on Follower fixed-jaw side under the gripper motor. Leave cable slack and tape it |

## USB and port identification

Validated 2026-10-18: MacBook Pro M4 connected through a **UGREEN USB-C hub**. Ports stayed stable through the hub. After unplug/replug, names can change—recheck with `ls /dev/tty.usbmodem*`.

C920 and wrist camera are USB-A. A hub with 2× USB-C data + 2× USB-A and PD passthrough is practical: arms on USB-C, cameras on USB-A, Mac charger on PD.

```bash
source ~/work/lerobot-hw/.venv/bin/activate
# Run with USB and power connected to both arms
lerobot-find-port
# When prompted, unplug only the arm you want to identify, then press Enter
# Record the shown port, replug USB, repeat for the other arm (one at a time)
```

| Arm | Port (validated 2026-10-18) | Power | id |
| --- | --- | --- | --- |
| Leader | `/dev/tty.usbmodem5B790143611` | 5V | leader |
| Follower | `/dev/tty.usbmodem5B8E1163071` | 12V | follower |

```bash
export PORT_FOLLOWER=/dev/tty.usbmodem5B8E1163071
export PORT_LEADER=/dev/tty.usbmodem5B790143611
```

**On first bring-up, Leader / Follower ports were swapped and the gripper arm moved as the Leader during teleop.** Re-identify ports and recalibrate if that happens.

## Verify motor IDs

On WowRobo pre-assembled kits, STS3215 IDs 1–6 and baud rate 1,000,000 are often already set. Scan the port before writing; if correct, skip `lerobot-setup-motors` (the official procedure assumes connecting motors one-by-one to the board and would require dismantling cables on an assembled arm).

```bash
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('$PORT_FOLLOWER'))"
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('$PORT_LEADER'))"
```

- Healthy example: `{1000000: [1, 2, 3, 4, 5, 6]}` → proceed to calibration.
- Missing IDs or only another baud rate: check power/wiring; if needed run `lerobot-setup-motors` per the official docs ([SO-101](https://huggingface.co/docs/lerobot/so101)).

## Calibration

If no calibration JSON exists on the host, later connect commands start calibration automatically. Run it explicitly.

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

- **Move only the arm whose port you are calibrating.** Moving the other can cause `same min and max` failures.
- Start pose: each joint near mid-range (roughly L-shaped).
- Move every joint except `wrist_roll` fully in both directions. Avoid winding the wrist cable.
- Gripper full open to full close. Leader trigger travel is inherently short.
- Save locations (default `HF_LEROBOT_HOME=~/.cache/huggingface/lerobot`):
  - `~/.cache/huggingface/lerobot/calibration/robots/so_follower/follower.json`
  - `~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/leader.json`
- On re-run you are prompted to reuse the existing file or press `c` to recalibrate.

## Teleoperation

Before starting, match Leader to the same rest pose as Follower.

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader
```

First bring-up ran at about 60 Hz. Optionally add `--robot.max_relative_target=10` (per-step limit in degrees) or `--teleop_time_s=60`. Support the Follower by hand before stopping.

Checks: each joint tracks in the same direction, gripper opens/closes, no unusual noise or vibration.

## Cameras

1. On macOS, first run may show “not authorized to capture video”. Allow the terminal (or iTerm / VS Code, etc.) under **System Settings → Privacy & Security → Camera**, **restart the app**, then retry. The 2026-10-18 validation had no permission issues.
2. **iPhone Continuity Camera steals an index.** Choose Disconnect on the Continuity Camera alert on the iPhone, and turn off **Settings → General → AirPlay & Continuity → Continuity Camera**.
3. List cameras and take snapshots:

```bash
lerobot-find-cameras opencv
# Images save under outputs/captured_images/opencv_*.png. Indices can change after unplug/replug
# ffmpeg avfoundation numbers differ from OpenCV / LeRobot. Always confirm with the command above and saved images
```

| Camera | OpenCV / LeRobot index (2026-10-18) | Resolution / fps |
| --- | --- | --- |
| wrist (kit USB2.0_CAM1) | 0 | 640×480 / 30 |
| top (C920) | 1 | 640×480 / 30 |
| Built-in camera | 2 | (unused) |

2026-10-18: both external cameras streamed simultaneously through the hub (640×480@30, measured ≈ 29.7 fps).

4. Teleop with display (validated 2026-10-18: 60 Hz, min 57 Hz, 120 s, no camera warnings. Moved sponge onto paper):

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=/dev/tty.usbmodem5B8E1163071 \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader \
  --teleop.port=/dev/tty.usbmodem5B790143611 \
  --teleop.id=leader \
  --display_data=true \
  --fps=60 \
  --teleop_time_s=120
```

The Rerun viewer displays only; it does not save. If using `$PORT_*`, keep the ports above aligned with those env vars.

## Pre-record checklist (required)

**Run this immediately before every `lerobot-record`.** Do not record until it passes. Teleop for 60 s with the same robot / teleop / cameras flags and confirm in Rerun.

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader \
  --display_data=true \
  --fps=60 \
  --teleop_time_s=60
```

| # | Check |
| --- | --- |
| (a) | **top:** sponge, white paper, and gripper stay in frame across the work area |
| (b) | **wrist:** gripper tip and sponge visible on approach |
| (c) | Move Leader slowly through the full pick-and-place path (including extremes); Follower must not hit the camera stand / C920 pole (≥ ~35 cm from base) or table clamps |
| (d) | No camera warnings; loop holds about 60 Hz |
| (e) | Sponge and paper are at the taped start positions |

If any item fails: Ctrl+C → fix → recheck. **Only after all are OK, close Rerun and proceed to `lerobot-record` in the next section.**

## Demo recording (`lerobot-record`)

**Prerequisite:** every item in [Pre-record checklist (required)](#pre-record-checklist-required) has passed.

2026-10-18 trials (both succeeded):

| Trial | Result |
| --- | --- |
| 1st | 2 epi × 25 s, 750 frames each @ 30 fps, ~15 MB, no slow-loop warnings |
| 2nd (23:48–23:50 SGT) | Same 2 epi × 25 s, 1500 frames total, ~17 MB. No slow-loop / OpenCV camera errors |

Command is shared. `--dataset.root=$HOME/work/lerobot-hw/datasets/<name>` (absolute path; `~` not allowed). **Reusing an existing root fails—use a new dataset name every run.**

```bash
# Example: change <name> each run (e.g. so101_pick_sponge_trial2)
lerobot-record \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader \
  --dataset.repo_id=yohei1126/so101_pick_sponge_trial \
  --dataset.single_task='Pick up the yellow sponge and place it on the white paper' \
  --dataset.num_episodes=2 \
  --dataset.episode_time_s=25 \
  --dataset.reset_time_s=10 \
  --dataset.fps=30 \
  --dataset.no_stamp=true \
  --dataset.push_to_hub=false \
  --dataset.root=$HOME/work/lerobot-hw/datasets/<name> \
  --display_data=true
```

Notes:

- A leading `~` right after `--dataset.root=` is not expanded. **Use an absolute path or `$HOME`.** Specifying an existing directory fails.
- **Run in a foreground interactive terminal.** Backgrounding with `nohup` from an agent shell dies right after the first camera connect when the parent shell exits (log shows only rerun `h2 protocol error`, no Python traceback). If background is required, detach the session with `start_new_session=True` or `setsid`.
- Without an interactive terminal or without pynput, keyboard controls (Right / Left / Esc) are disabled and only timers run. Follow the voice cues (`Recording episode N` / `Reset the environment` / `Stop recording`) (Mac sound ON).
- Hung runs can keep serial ports busy. Before retrying, `pkill -f lerobot-record` and confirm both `/dev/tty.usbmodem*` are free with `lsof`. Close leftover Rerun windows.
- In dataset v3.0, per-camera video is concatenated into `videos/observation.images.<cam>/chunk-000/file-000.mp4`.
- Framing (trial3 first-frame check): wrist shows sponge, paper, and gripper. **top (C920) showed only sponge and paper—gripper out of frame.** In pre-record checks (a)(b), lower the C920 slightly, move it back, and/or tip it down until the gripper work area is in frame, then record.
- `objc: Class AVFFrameReceiver is implemented in both ... cv2 ... and /opt/homebrew ... ffmpeg` is a harmless warning (recording still succeeds when it appears).

## Shutdown

1. Stop teleop (etc.) with Ctrl+C. Support the Follower by hand.
2. **Unplug 12V / 5V adapters** (DC first, then USB).
3. Carry by the base. Do not lift by the cables.

## Next steps

Do not deploy a sim checkpoint straight onto the real robot. The sim policy uses **radians** for joints; the real Follower uses **degrees** for body joints and **0–100** for the gripper—I/O contracts do not match.

1. **Scale up demo recording:** after framing and layout are fixed, increase episode count (extend the trial command above)
2. **Training:** ACT with `lerobot-train`, `--policy.device=mps` (real data). For sim data: `python -m port_pick_align.training.train_act --preset sim`
3. **Phase 2-2 (sim→real):** unit-conversion wrapper, dry-run then slow live. Procedure: **[sim_to_real_act.md](sim_to_real_act.en.md)**
4. **Evaluate a real-trained policy:** `lerobot-rollout` (in 0.6.1, policy execution is rollout, not record). Start with a small `--robot.max_relative_target`, slow and short

### Phase 2-2 quick links (details in sim_to_real_act.md)

```bash
# Dry-run (motors not driven) — always do this first
python -m port_pick_align.deploy.run_sim_policy_on_real \
  --checkpoint "$HOME/work/lerobot-hw/outputs/sim_act/best_model.pt" \
  --port "$PORT_FOLLOWER" \
  --dry-run \
  --device mps \
  --episode-time-s 20

# Live (hand on the 12V switch. First run: keep max-delta small)
python -m port_pick_align.deploy.run_sim_policy_on_real \
  --checkpoint "$HOME/work/lerobot-hw/outputs/sim_act/best_model.pt" \
  --port "$PORT_FOLLOWER" \
  --device mps \
  --episode-time-s 20 \
  --max-delta-deg 3 \
  --robot-max-relative-target 3
```

### Example: evaluate a real-trained policy (no unit conversion)

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
| Port missing / unchanged | Confirm data-capable USB-C. Bypass hub and connect direct. `ls /dev/tty.usbmodem*` |
| Ports swapped (gripper arm behaves as Leader) | Re-run `lerobot-find-port` one arm at a time; recalibrate |
| `Permission denied` / `Resource busy` | Kill the process holding the port via `lsof` |
| `Missing motor IDs` | Check `scan_port`, 12V/5V, 3-pin wiring, port swap |
| Teleop runs but Follower does not move | Confirm 12V adapter ON (LED lit) |
| `same min and max` (calibration) | Move only the target arm. From mid pose, drive each joint to its ends |
| Sudden motion at teleop start | Align poses before start. Add `max_relative_target` |
| Camera index drifts / only built-in visible | Disable Continuity Camera. Confirm with `lerobot-find-cameras opencv` and `outputs/captured_images/opencv_*.png` (do not use ffmpeg numbers) |
| `not authorized to capture video` | macOS camera permission → restart terminal → `lerobot-find-cameras opencv` |
| rerun error with `--display_data` | `pip install 'lerobot[viz]==0.6.1'` |
| `lerobot-record` import error | `pip install 'lerobot[dataset]==0.6.1'` |
| `--dataset.root=~/...` fails | `~` is not expanded. Use `$HOME` or an absolute path. Do not reuse an existing root; pick a new `<name>` |
| `lerobot-record` dies in a few seconds (`h2 protocol error` only) | Parent shell exit disconnected the process. Run in a foreground interactive terminal, or detach with `setsid` / `start_new_session=True` |
| Port busy on retry | `pkill -f lerobot-record` → confirm both usbmodem ports free with `lsof`. Close Rerun windows |
| `AVFFrameReceiver is implemented in both ...` | Harmless. Can appear on successful recordings |
| Red LED on with DC unplugged | USB power; normal. Drive still needs the correct DC adapter |
| Follower hits camera stand | Keep pole ≥ ~35 cm from base. Paper on opposite side. Mark with tape |

## References

- [hardware.md](hardware.en.md) — purchased equipment and work-area dimensions
- [sim_to_real_act.md](sim_to_real_act.en.md) — Phase 2-2: sim ACT → real Follower (conversion wrapper)
- [units.md](units.en.md) — radians / degrees / gripper 0–100
- [plan_b.md](plan_b.en.md) — degradation path when real hardware is blocked
- [LeRobot SO-101](https://huggingface.co/docs/lerobot/so101)
- [LeRobot Cameras](https://huggingface.co/docs/lerobot/cameras)
- [Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots)
