# Dataset management (rosbag2 / synthetic data / LeRobotDataset)

This document covers generating contract-compliant test rosbag2 files, creating synthetic data for pipeline smoke tests, collecting MuJoCo oracle demonstrations, and converting rosbag2 to LeRobotDataset with quality validation.

## Generating the test rosbag2 (`sample_bag`)

Generate a test rosbag2 in Docker with topics and shapes that follow the contract (`configs/contract.yaml`):

```bash
docker compose -f docker/docker-compose.yml build dev
docker compose -f docker/docker-compose.yml run --rm generate-bag

# Inspect bag metadata
docker compose -f docker/docker-compose.yml run --rm dev \
  bash -lc 'ros2 bag info port_pick_align/tests/fixtures/sample_bag'
```

Output directory: `port_pick_align/tests/fixtures/sample_bag/`

## Generating a synthetic LeRobotDataset

Before real-robot data is available, generate pseudo episode data on the host Python virtualenv for pipeline smoke tests (PyTorch and LeRobot run only on the host to keep the Docker image lean):

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# Contract-compliant synthetic data (default: 8 episodes × 64 frames each)
python scripts/generate_synthetic_dataset.py
```

The dataset is written to `data/synthetic/lerobot/` (not tracked by Git).

## Collecting MuJoCo oracle demonstrations

Roll out `ScriptedPickAlignPolicy` on `PickAlignSimEnv` and write a contract-compliant LeRobotDataset to `data/sim_expert/lerobot/`. Each episode randomizes the box’s initial planar pose and yaw, then records joint targets and dual-camera images at 30 Hz from grasp through alignment. The scripted trajectory is 260 steps long. During lift, carry, approach, and place, wrist roll moves so the held box yaw matches the pad yaw. Near the pad, a closed approach of 32 steps (at least one chunk length) descends; at pad height, a closed place of 8 steps is followed by an open stationary release of 48 steps. If closed and open share the same arm pose half and half, the conditional mean of the gripper command falls below the release threshold 0.90. The simulator does not release on an open command until the pad neighborhood (within 10 cm). Observation images come from the simulator as BGR (640×480). To match training pixel order with closed-loop inference `images_bgr_to_batch` (BGR→RGB), the dataset stores RGB. This trajectory is not in earlier collections; recollect before training.

For each recorded episode, run `validate_episode` (sync skew, frame interval, joint limits, stillness) and apply the same joint limits to recorded actions. Episodes that fail validation or fail alignment are not kept. Trial logs go to `data/sim_expert/validation_report.json`. The dataset and logs are not Git-tracked. `official_collection` is true only when episode count is 50–100 inclusive, resolution is contract 640×480, step count is 260, and both initial-pose randomization and required alignment success are satisfied.

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,training]"

# Full collection. --episodes must be 50–100. Default is 64.
python scripts/collect_sim_dataset.py --episodes 64 --output data/sim_expert/lerobot

# Smoke check. Low resolution / short episodes; not a substitute for full collection.
python scripts/collect_sim_dataset.py --episodes 1 --max-steps 20 \
  --width 64 --height 48 --allow-short --allow-failures \
  --output /tmp/sim_expert_smoke/lerobot
```

If offscreen rendering fails in a headless environment, set `MUJOCO_GL=osmesa`. On macOS, use the default `glfw`.

## Converting rosbag2 to LeRobotDataset with quality checks

The conversion pipeline uses the `rosbags` library to parse binaries directly, so conversion runs on the host without a ROS 2 runtime. A quality validator runs inside conversion and rejects episodes that fail the criteria.

```bash
# Unit tests: sample_bag conversion and quality gates (sync, dropouts, joint limits, stillness)
(cd port_pick_align && pytest -m unit tests/test_converter.py tests/test_validator.py -q)

# Convert via CLI
python scripts/convert_bag.py \
  --bag port_pick_align/tests/fixtures/sample_bag \
  --output data/from_bag/lerobot
```

Example calling the converter from Python:

```python
from pathlib import Path
from port_pick_align.contract import load_contract
from port_pick_align.dataset.converter import convert_bag_to_lerobot

contract = load_contract()
convert_bag_to_lerobot(
    "port_pick_align/tests/fixtures/sample_bag",
    Path("data/from_bag/lerobot"),
    contract=contract,
)
```

Sync tolerance, frame-drop thresholds, and joint-limit checks all follow the `quality` and `robot.joint_limits` sections of `configs/contract.yaml`.
