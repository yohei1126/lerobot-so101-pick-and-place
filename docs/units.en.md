# Joint and gripper units (sim / contract / real LeRobot)

The code-level single source of truth is [`port_pick_align/units.py`](../port_pick_align/src/port_pick_align/units.py) and [`configs/contract.yaml`](../configs/contract.yaml). Use this wording when transferring units into the report (`docs/hardware.md` is not modified).

## Unit table (sim / contract / real)

| System | Arm 5 axes | Gripper | Box yaw / evaluation yaw |
| --- | --- | --- | --- |
| MuJoCo sim / `contract.yaml` | **radians** | **radians** (6th dim, same as other joints) | sim `box_yaw` is **radians**. `metrics.json` `yaw_error_deg` / `mean_abs_yaw_error_deg` are **degrees** |
| Real LeRobot SO-101 (typical) | **degrees** | **0–100** (opening percent) | (align to degrees for real-robot eval) |

Before training on real data, confirm units in real-robot logs and, if needed, convert to contract radians with `deg_to_rad` / `gripper_percent_to_rad`.

## Contract gripper range

`contract.yaml` `joint_limits.gripper` is `[-0.1745, 1.7453]` rad (about −10° .. 100° in comments). This module’s linear “opening percent” map is:

- `0` ↔ `−0.1745` rad (more closed)
- `100` ↔ `1.7453` rad (more open)
- Implementation: `gripper_rad_to_percent` / `gripper_percent_to_rad`

**Note (real deploy):** On LeRobot 0.6.1 SO follower, discrete gripper command polarity is best read as **higher `gripper.pos` = more closed** (0≈open, 100≈closed). The sim→real wrapper ([sim_to_real_act.md](sim_to_real_act.en.md)) uses that polarity by default; `--no-gripper-closed-is-high` switches to this module’s opening-percent meaning. If calibration looks inverted, confirm in dry-run.

## Simulator conventions (not 0–100)

| Constant | Value (rad) | Role |
| --- | --- | --- |
| Scripted closed | `0.0` | Close command in `ScriptedPickAlignPolicy` |
| Scripted open | `1.2` | Open command (same) |
| `GRIPPER_CLOSE_THRESH` | `0.45` | Close threshold for sticky grasp |
| `GRIPPER_OPEN_THRESH` | `0.90` | Open threshold / near-pad release gate |

These are all radians. On a 0–100 scale, closed ≈ 9% and open(1.2) ≈ 72% (linear map to contract limits).

## Evaluation yaw

`compute_pose_errors` returns planar position in mm and yaw difference converted from radians to degrees. `summarize()` reports absolute-value mean/median as `mean_abs_yaw_error_deg` / `median_abs_yaw_error_deg`. `scripts/run_sim_eval.py` prints these on one line at exit.

## Check commands

```bash
python -c "from port_pick_align.units import describe_unit_conventions; import json; print(json.dumps(describe_unit_conventions(), indent=2))"
(cd port_pick_align && pytest -m unit tests/test_units.py -q)
```
