# Closed-loop evaluation with MuJoCo simulation

Before real-robot operation, use a tabletop manipulation simulator to closed-loop verify the ACT inference pipeline and alignment accuracy.

## Dependency setup (host)

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,dev]"
# Also install the training extra when inferring from a trained checkpoint
pip install -e "port_pick_align/[simulation,training,dev]"
```

Offscreen rendering works with a normal `python` interpreter (`mjpython` is only needed for the interactive 3D viewer). In environments that require an explicit graphics backend, set:

```bash
export MUJOCO_GL=glfw   # default on macOS
# Headless Linux example: export MUJOCO_GL=osmesa
```

## Simulation environment

- Mechanism: 6-DoF arm and gripper (joint names match `configs/contract.yaml`)
- Sensors: Top and Wrist dual cameras (640×480)
- Objects: small rectangular box and a tabletop alignment target frame
- Package: `port_pick_align.simulation` (model: `simulation/assets/so101_tabletop.xml`)

## Table layout (2026-10-26 source of truth)

Real bring-up and live eval use the standardized table layout (**140 × 70 cm**): leader 27 cm from the left / 101 cm from the right, follower ~68 cm from the left / 61 cm from the right, C920 on the right edge 16 cm from the front, paper 69 cm from the right and 27 cm from the front (portrait 20×30 cm), sponge 54 cm from the right and 44 cm from the front (portrait 6×11 cm). Wrist camera on the follower gripper. OpenCV wrist `0`, top `1`.

Those edge measurements map into the sim frame (follower midpoint on the front edge, +x forward, +y left) as:

| Item | Sim `(x, y)` m |
| --- | --- |
| Leader midpoint | (0, 0.405) |
| Follower origin | (0, 0) |
| Paper point | (0.27, 0.025) |
| Sponge point | (0.44, −0.125) |
| Top camera | (0.16, −0.665) |

The map and the conventions behind it (base midpoint, front-edge origin, measured point rather than a stated corner) are in [`table_layout.py`](../port_pick_align/src/port_pick_align/simulation/table_layout.py) and [hardware.md](hardware.en.md#current-table-layout-2026-10-26).

`so101_tabletop.xml` still loads the **superseded** simplified scene: table about 70×60 cm, box spawn `(0.28, -0.08)` m, goal `(0.35, 0.12)` m, nadir top camera `(0.25, 0, 1.05)` m. Current sim eval uses that scene so existing checkpoints stay comparable. Do not copy those geoms into bring-up. The old figure is [so101_layout_guide_superseded_pre_20261026.png](images/so101_layout_guide_superseded_pre_20261026.png). The current figure is [so101_layout_guide.png](images/so101_layout_guide.png). Also superseded, and not in the XML: the 2026-10-25 ~23:28 measurements (table 140×69, C920 28 cm from the right, sponge 70/45, paper 82/26, follower 62 cm from the right) and the 2026-10-22 recording layout.

## Visualization and checks

### 1. MuJoCo interactive 3D viewer

On macOS, thread constraints (`launch_passive`) require starting with **`mjpython`**. In a uv-created venv, create a symlink to the dynamic library first.

```bash
source .venv/bin/activate
# Dynamic library placement for uv venvs (first time only)
mkdir -p .venv/lib
ln -sfn "$(python -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')/libpython3.12.dylib" \
  .venv/lib/libpython3.12.dylib

.venv/bin/mjpython scripts/view_sim.py --policy scripted
```

Controls: drag to orbit, scroll to zoom. Close the window to exit.

### 2. Multi-modal visualization with Rerun

Assumes the `rerun` binary from the venv is on `PATH`.

```bash
export PATH="$PWD/.venv/bin:$PATH"
python scripts/run_sim_eval.py --policy scripted --rerun --save-video
```

### 3. Inspect rollout video files

```bash
python scripts/run_sim_eval.py --policy scripted --save-video --no-rerun
open outputs/eval/sim_rollout.mp4   # playback check on macOS
```

## Closed-loop evaluation commands

Run the following according to policy type and environment.

```bash
# Demo heuristic policy (pick-and-align check at a fixed spawn)
# Default --video-mode topdown writes a top-down schematic video without OpenGL
python scripts/run_sim_eval.py --policy scripted --save-video --no-rerun

# Camera-rendered video where OpenGL / glfw is available
python scripts/run_sim_eval.py --policy scripted --video-mode mujoco --save-video

# Minimal smoke test (repeat current joint positions)
python scripts/run_sim_eval.py --policy mock --episodes 1 --max-steps 20 --no-save-video

# Infer with a trained ACT checkpoint (I/O shape smoke test)
python scripts/run_sim_eval.py --policy checkpoint \
  --checkpoint checkpoints/synthetic_act/best_model.pt --video-mode topdown

# Phase 1.5 full eval. Fails if the checkpoint is missing; does not invent metrics.
# Success criterion uses n_action_steps=30 (no Temporal Ensembling) and writes
# outputs/eval_sim_act/metrics.json. TE metrics go under outputs/eval_sim_act_te/.
# On Mac use DEVICE=mps. Unmeasured placeholder: docs/results/eval_sim_act.pending.json.
DEVICE=mps ./scripts/run_phase15_benchmark.sh

# Closed-loop eval with Rerun visualization
export PATH="$PWD/.venv/bin:$PATH"
python scripts/run_sim_eval.py --policy scripted --rerun --video-mode mujoco
```

Eval script outputs (not Git-tracked):

- `outputs/eval/metrics.json`: planar position error, yaw error, grasp and alignment success aggregates
- `outputs/eval/sim_rollout.mp4`: visualized rollout video

## Unit and integration tests

```bash
(cd port_pick_align && pytest -m simulation -q)
```

If the `mujoco` package is not installed, `pytest.importorskip` skips these tests automatically so a minimal CI pipeline is not blocked.

## Temporal Ensembling

ACT predicts a future action chunk each control cycle. Always taking only the first element of the newest chunk in closed loop makes chunk swaps appear as joint-command steps. `CheckpointPolicy(temporal_ensemble=True)` keeps predictions from past chunks for the same timestep in a queue and averages them with exponential weights, matching Zhao et al. (2023) and LeRobot’s `ACTTemporalEnsembler`. Weights are `w_i = exp(-m * i)` where `i = 0` is the oldest prediction. With `m > 0`, older predictions weigh more; `m = 0` is a uniform average; `m < 0` weighs newer predictions more. Default `m` is 0.01. With the flag off, chunks are returned as-is.

## Collecting oracle demonstration data

Automatic LeRobotDataset collection from the same environment and `ScriptedPickAlignPolicy` is documented in [dataset.md](dataset.en.md). Entry point: `scripts/collect_sim_dataset.py`.

## Related docs

- Current real table and sim-frame map: [hardware.md](hardware.en.md#current-table-layout-2026-10-26), [real_robot_bringup.md](real_robot_bringup.en.md#current-table-layout-2026-10-26)
- Evaluation API: [evaluation.md](evaluation.en.md)
- ACT training: [training.md](training.en.md)
- Demonstration collection: [dataset.md](dataset.en.md)

