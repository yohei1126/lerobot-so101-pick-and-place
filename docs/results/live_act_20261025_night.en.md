# Real ACT live eval (2026-10-25 night)

Fact log. Success means picking the sponge up and placing it on the paper. Videos are outside the repo, on the work Mac at `$HOME/work/lerobot-hw/outputs/rollouts/`.

This is a post-train live eval. It is separate from teleop-recording QC (`scripts/qc_teleop_dataset.py`). Those thresholds stay in [QC a recorded dataset](../real_robot_bringup.en.md#qc-a-recorded-dataset). Procedure, checkpoint choice, and the 2026-10-24 offline diagnosis are in the [real-eval protocol](../real_eval_protocol.ja.md) (Japanese).

## Layout

Trials used the layout that was current that night (superseded 2026-10-25 ~23:28). New evals use the [current table layout (2026-10-26)](../real_robot_bringup.en.md#current-table-layout-2026-10-26). That night's dimensions are under [superseded layouts](../real_robot_bringup.en.md#superseded-layouts) and are not the current source of truth.

Cameras: wrist OpenCV 0, top C920 OpenCV 1 (after the cable swap). Ports: Follower `…5B8E1163071`, Leader `…5B790143611`.

## Results

`n-action-steps` is 10. Only D uses temporal ensemble (k=0.01).

| Config | Checkpoint | Observation | Trials | Success |
| --- | --- | --- | --- | ---: |
| A | untrim clean28 `last.pt` | Lateral vibrate, no grasp | A1–A3 | 0/3 |
| LT | light-trim `best_model.pt` | Vibrate; slight gripper / slight move | LT1–LT3 | 0/3 |
| B | trim `best_model.pt` | Tries to move; arm cannot fully extend | B1–B3 | 0/3 |
| C | trim `last.pt` | Repeatedly tries to extend; partial extend then tremble | C1–C3 | 0/3 |
| D | trim `last.pt` + TE k=0.01 | Tremble / near-static. Some dual-cam mp4s look static | D1–D3 (includes D2 reruns) | 0/3 |
| C extra | trim `last.pt` | Slight extend while trembling, then end | 1 | 0/1 |

## Videos

All under `$HOME/work/lerobot-hw/outputs/rollouts/`.

| Trial | File | Note |
| --- | --- | --- |
| C3 | `act_20261025_235730.mp4` | |
| B3 | `act_20261025_234938.mp4` | |
| D1 | `act_20261026_000058.mp4` | |
| D2 | `act_20261026_000655.mp4` | |
| D2d | `act_20261026_001850.mp4` | After camera adjust. Auto dual-cam looked static |
| D3 | `act_20261026_002220.mp4` | Eye: tremble |
| C extra | `act_20261026_002457.mp4` | Eye: slight extend while trembling |

## Takeaways

- No successful pick-and-place this night.
- Closed-loop tremble, or failure to fully extend, dominates. TE did not fix the live behavior.
- val_l1 checkpoint ranking still poorly tracks real success (same as the 2026-10-24 trim diagnosis).
- Auto dual-cam mp4 can under-show small vibrations compared with eye or a phone.
