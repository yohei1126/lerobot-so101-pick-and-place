# SO-ARM101 / Feetech STS3215 Dry-Run Procedure

Before wiring and power-on: confirm official specs, set Linux udev rules, resolve Python dependencies, match the sim work-area layout, and list purchased gear. Limit checks to software connectivity; do not drive motors yet.

## Official specs and reference docs

- [Assemble SO-101](https://huggingface.co/docs/lerobot/en/assemble_so101) (assembly)
- [SO-101](https://huggingface.co/docs/lerobot/en/so101) (motor initial setup with `lerobot-setup-motors` and calibration)
- [SO-100](https://huggingface.co/docs/lerobot/en/so100) (shared software configuration)

Servo motor IDs (1–6) must match the joint-name mapping in this repository’s [`configs/contract.yaml`](../configs/contract.yaml) under `robot.joint_names`.

- Assignment order: `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper`
- LeRobot robot type name: `so101_follower` (use `so101_leader` when using the leader arm)

## Install host Python dependencies

```bash
cd /path/to/lerobot-so101-pick-and-place
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "port_pick_align/[training,feetech,dev]"
```

Module import test with no hardware attached:

```bash
python -c "import lerobot; print('lerobot OK', lerobot.__version__)"
# Confirm Feetech motor-bus dependency resolution
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print('feetech OK')"
```

If import raises `ImportError`, re-run `pip install -e "port_pick_align/[feetech]"` and check that C++ extensions and serial libraries installed correctly.

## Identify the serial port

### Linux

```bash
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
# Adapter attributes (vendor / product / serial)
udevadm info -a -n /dev/ttyACM0 | head -n 40
```

### macOS

macOS cannot create static udev symlinks, so confirm the device node assigned at connect time.

```bash
ls /dev/tty.usbmodem* /dev/tty.usbserial* 2>/dev/null
```

Pass the detected path (e.g. `/dev/tty.usbmodem585A0076841`) directly to LeRobot arguments.

## Apply udev rules (Linux)

Template: [`deploy/udev/99-feetech-so101.rules`](../deploy/udev/99-feetech-so101.rules)

1. Run `udevadm info` and obtain `idVendor`, `idProduct`, and `serial` for the USB serial adapter in use.
2. Update `REPLACE_*_SERIAL` and SYMLINK names in the template to match the hardware serial numbers.
3. Install the rules file and reload.

```bash
sudo cp deploy/udev/99-feetech-so101.rules /etc/udev/rules.d/
# Reload rules (permissions: MODE=0660 / GROUP=dialout)
sudo udevadm control --reload-rules && sudo udevadm trigger
# dialout group is required (if not a member, add and log out → log in once)
sudo usermod -aG dialout $USER
# After re-login, confirm fixed symlinks exist
ls -l /dev/ttyUSB_so101_*
```

## Initial setup commands when hardware is connected (reference)

Motor ID assignment (replace each port name with the device node on your machine):

```bash
lerobot-setup-motors \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyUSB_so101_follower

lerobot-setup-motors \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyUSB_so101_leader
```

Calibration (after the real arm is assembled and 12V power is connected):

```bash
# Follow the official calibrate / control_robot procedure
# Example: python -m lerobot.scripts.control_robot calibrate ...
```

Power notes: Follower Feetech STS3215 (C018) drive voltage is 12V. USB bus power alone will not drive it; connect the kit’s 12V adapter. Leader STS3215 (7.4V rating) is driven at 5V; connect the included 5V adapter (30W). See “[Purchased equipment](#purchased-equipment)” for part names. To avoid bandwidth contention between camera video and serial traffic, separate USB host controllers or use a standards-compliant USB hub.

## Purchased equipment

Place the real hardware on the kitchen table. Layout numbers follow “[Work-area layout](#work-area-layout-simulation-aligned)”.

| Item | Qty | Use / notes |
| --- | --- | --- |
| WowRobo “SO-ARM101 DIY Kit & Assembled Version” Package 3 (Assembled SO-101 Arm, Black) | 1 | Leader 1, Follower 1, camera 1. Vendor-assembled and calibrated |
| Follower Feetech STS3215 12V (C018) | 6 | Follower joint servos. Included in kit |
| Follower bus servo driver (Waveshare / Feetech, DC jack 5.5×2.1 mm) | 1 | Follower servo bus. Included in kit |
| 12V DC power adapter (with UK 3-pin cord) | 1 | Follower drive power. Included in kit |
| Leader Feetech STS3215 7.4V (5V drive) | 6 | Leader joint servos. Included in kit |
| Leader bus servo driver board | 1 | Leader servo bus. Included in kit |
| 5V power adapter (30W, with UK 3-pin cord) | 1 | Leader drive power. Included in kit |
| USB-C cable (white) | 2 | Connect each driver board to the Mac. Included in kit |
| Wrist camera module (with housing, screws included) | 1 | Wrist camera. Mount on the gripper. Included in kit |
| DELIXI C-clamps | 4 | Clamp arm bases to the table. Included in kit |
| 3D-printed parts (orange / black) and small parts | 1 set | Kit print parts and accessories |
| Feetech small box | 1 | Spare STS3215 servo. Confirm voltage on the box label. Included in kit |
| VIJIM LS08 (C-clamp flexible camera arm) | 1 | Clamp to the table edge; hold the top camera at roughly (25, 0) cm planar from the base, 63 cm above the tabletop, pointing straight down. Mount screw is 1/4 inch |
| Logitech C920 | 1 | Top camera (USB) |

### Still needed

- Extension cord or power strip. Singapore Safety Mark, UK plug, 3+ outlets. Use for the 12V adapter, 5V adapter, and spare on the kitchen table.

## Work-area layout (simulation-aligned)

Equipment is listed under “[Purchased equipment](#purchased-equipment)”. Origin is the arm base center; +x is forward, +y is left, +z is up. Planar positions in the table below are distances from the base center. Numbers come from the simplified MuJoCo scene and differ in scale from the real SO-101 link lengths. Reach is approximate.

Sources:

- [`port_pick_align/src/port_pick_align/simulation/assets/so101_tabletop.xml`](../port_pick_align/src/port_pick_align/simulation/assets/so101_tabletop.xml)
- [`port_pick_align/src/port_pick_align/simulation/env.py`](../port_pick_align/src/port_pick_align/simulation/env.py)
- [`port_pick_align/src/port_pick_align/evaluation/eval_alignment.py`](../port_pick_align/src/port_pick_align/evaluation/eval_alignment.py)

![Work-area layout guide (top and side views)](images/so101_layout_guide.png)

Printable PDF: [so101_layout_guide.pdf](images/so101_layout_guide.pdf). Regenerate the figure with `python scripts/draw_layout_guide.py`; output goes to `docs/images/`.

| Item | Value | Source |
| --- | --- | --- |
| Tabletop | z = 0.42 m (floor at z = 0) | `TABLE_Z` in `env.py`. XML table geom center z = 0.40 m, half-thickness 0.02 m |
| Box | 5×4×4 cm, 30 g | XML `box_geom` half-size `0.025 0.02 0.02`, `mass="0.03"` |
| Box initial center | (28, −8) cm. xy ±4 cm each, yaw ±0.3 rad (≈ ±17°) uniform | `env.py` reset. Base `(0.28, -0.08)` plus `uniform(-0.04, 0.04)`; yaw `uniform(-0.3, 0.3)` |
| Goal `target_frame` | Center (35, +12) cm, pad 8×6 cm, yaw 0 | XML `target_frame` pos `0.35 0.12 0.42`, `target_pad` half-size `0.04 0.03` (no rotation) |
| Alignment success | Planar position error ≤ 25 mm and yaw error ≤ 15° | `DEFAULT_ALIGN_POS_MM = 25`, `DEFAULT_ALIGN_YAW_DEG = 15` in `eval_alignment.py` (both `<=`) |
| Top camera | Planar (25, 0) cm, 63 cm above tabletop (world z = 1.05 m), straight down, vertical FOV 55°. Field of view on tabletop ≈ 87×66 cm (estimate) | XML `camera name="top"` pos `0.25 0 1.05`, `xyaxes="1 0 0 0 1 0"`, `fovy="55"` |
| Wrist camera | 2 cm forward and 4 cm up from gripper link origin, ~30° downward, vertical FOV 60° | XML `camera name="wrist"` pos `0.02 0 0.04`, `xyaxes="0 -1 0 0.5 0 0.866"`, `fovy="60"` |
| Reach | ≈ 42 cm (`shoulder_pan` ±110°. Geometric max of the simplified model) | Upper arm 12 cm + forearm 14 cm + wrist 8 cm + gripper 3 cm + end-effector site 5 cm. pan range ±1.9199 rad |

The top-camera FOV ≈ 87×66 cm is estimated from height 63 cm above the tabletop, vertical FOV 55°, and contract image aspect 640×480. x (horizontal FOV ≈ 69°) ≈ 87 cm; y (vertical FOV 55°) ≈ 66 cm. The XML stores camera pose and `fovy`; FOV edge lengths are computed from those.

### Tape markers (proposed)

The following are proposed for real-robot setup: markers so the same initial distribution and goal can be reproduced on the table.

- Orange frame 8×8 cm: reachable initial range for the box center. Frame center at (28, −8) cm.
- Green cross and frame 8×6 cm: goal. Center at (35, +12) cm. Long edge parallel to x (yaw 0).
- Purple ×: directly under the top camera at (25, 0) cm.
- Prefer a sponge or block about 5 cm on a side. The sim box is 5×4×4 cm, 30 g.

### Cameras

ACT inputs are both the top camera (`/camera/top/image_raw`) and the wrist camera (`/camera/wrist/image_raw`). Resolution is 640×480 each at 30 fps ([`configs/contract.yaml`](../configs/contract.yaml)). Use a Logitech C920 for the top camera, fixed with a VIJIM LS08 directly above (25, 0) cm, 63 cm above the tabletop, pointing straight down. Mount the kit wrist-camera module on the gripper. See “[Purchased equipment](#purchased-equipment)”. Missing wrist imagery is out of distribution for training.

### Work-area prep checklist

- [ ] Defined table coordinates with arm base center as origin, forward +x, left +y
- [ ] Matched tabletop height to sim 0.42 m, or recorded the difference if that is not possible
- [ ] Applied proposed tape markers (orange frame, green cross and frame, purple ×)
- [ ] Prepared a sponge or block about 5×4×4 cm, ~30 g
- [ ] Fixed the top camera (C920) with VIJIM LS08 directly above (25, 0) cm, 63 cm above the tabletop, pointing straight down
- [ ] Connected the top camera (C920) and the kit wrist camera

## Pre-work checklist

- [ ] Reviewed official SO-101 and Feetech setup procedures
- [ ] Successfully installed `port_pick_align/[training,feetech]` dependencies
- [ ] Passed import tests for `lerobot` and Feetech motors modules
- [ ] On Linux, configured udev rules from hardware-specific serial numbers
- [ ] On macOS, know how to identify `/dev/tty.usbmodem*` devices
- [ ] Understand motor setup and calibration commands to run after hardware arrives

