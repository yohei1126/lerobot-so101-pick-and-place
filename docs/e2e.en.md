# End-to-end (E2E) pipeline integration test

Run bag record → convert/validate → ACT inference → ROS 2 / Rerun mock wiring in sequence. For equipment prep before connecting the real robot, see [hardware.md](hardware.en.md).

## Prerequisites

- Docker runtime (ROS 2 execution environment)
- Host Python virtualenv with `pip install -e "port_pick_align/[training,dev]"` installed
- Environment split: the Docker image does not include PyTorch, so checkpoint inference runs on the host; inside Docker, run the visualization loop with `policy_mode:=mock`.

## One-shot pipeline run

```bash
# If checkpoints/synthetic_act/best_model.pt already exists, skip retraining and smoke-test inference
./scripts/e2e_pipeline_smoke.sh
```

Stages:

1. Docker: record sensor topics from `mock_sensor_publisher` with `ros2 bag record` into `data/e2e/recorded_bag`.
2. Host: run `scripts/convert_bag.py`, convert to `data/e2e/lerobot` after validator quality checks (if the recorded bag has frame dropouts under load, continue with the fixed fixture `sample_bag`).
3. Host: inference smoke test with a trained checkpoint (`--infer-only`).
4. Docker: launch `mock_inference.launch.py` and verify topic I/O between the mock inference node and the Rerun node.

## Single bag convert, integration test, checkpoint infer

### 1. Convert a single bag file

```bash
python scripts/convert_bag.py \
  --bag port_pick_align/tests/fixtures/sample_bag \
  --output data/from_bag/lerobot
```

### 2. Host integration test (CI integration equivalent)

```bash
(cd port_pick_align && pytest -m integration tests/test_e2e_bag_to_infer.py -q)
```

### 3. Checkpoint inference in a host ROS 2 environment

```bash
ros2 run pai_final_pkg act_policy_node --ros-args \
  -p policy_mode:=checkpoint \
  -p checkpoint_path:=/workspace/checkpoints/synthetic_act/best_model.pt
```

## Feetech extra and udev prep

```bash
pip install -e "port_pick_align/[training,feetech,dev]"
# Linux: edit serial numbers in deploy/udev/99-feetech-so101.rules for your hardware and install under /etc/udev/rules.d/
```

For detailed hardware setup, see [hardware.md](hardware.en.md).
