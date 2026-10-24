# ROS 2 inference nodes and Rerun visualization

Run the sensor mock, inference node, and Rerun visualizer under ROS 2 Humble.

## Mock inference pipeline in Docker (no PyTorch)

Inside Docker, set `policy_mode:=mock` to verify the ROS 2 messaging layer and visualization stack without installing PyTorch. Sensor topics are synchronized with `ApproximateTimeSynchronizer`; after the inference node publishes `/joint_commands`, period jitter is logged and Rerun visualizes the stream.

```bash
docker compose -f docker/docker-compose.yml build dev
docker compose -f docker/docker-compose.yml run --rm dev bash -lc '
  cd /workspace/ros2_ws &&
  colcon build --packages-select pai_final_pkg &&
  source install/setup.bash &&
  ros2 launch pai_final_pkg mock_inference.launch.py
'
```

Example starting each node separately:

```bash
# Mock publish of sensor topics (Top/Wrist camera images, joint state)
ros2 run pai_final_pkg mock_sensor_publisher

# Inference node in mock mode
ros2 run pai_final_pkg act_policy_node --ros-args -p policy_mode:=mock

# Rerun visualizer (do not auto-spawn Web/native viewer)
ros2 run pai_final_pkg rerun_visualizer --ros-args -p spawn:=false
```

Starting the inference node with a trained checkpoint (host with ROS 2 and PyTorch, etc.):

```bash
ros2 run pai_final_pkg act_policy_node --ros-args \
  -p policy_mode:=checkpoint \
  -p checkpoint_path:=/workspace/checkpoints/synthetic_act/best_model.pt
```

## Host unit and integration tests for inference helpers

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# Unit: tensor conversion and action expansion helpers for inference
(cd port_pick_align && pytest -m unit tests/test_infer_helpers.py -q)

# Integration: predict_chunk inference against an existing checkpoint
(cd port_pick_align && pytest -m integration tests/test_infer_helpers.py -q)
```

Main related sources:

- `ros2_ws/src/pai_final_pkg/pai_final_pkg/act_policy_node.py`: ROS 2 inference node
- `ros2_ws/src/pai_final_pkg/pai_final_pkg/rerun_visualizer.py`: Rerun integration node

For the alignment error aggregation API, see [evaluation.md](evaluation.en.md).
