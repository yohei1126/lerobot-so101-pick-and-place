# ROS 2 推論・Rerun

## Docker: モックセンサ → 推論ノード → Rerun（torch なし）

`policy_mode:=mock` で ApproximateTimeSynchronizer → `/joint_commands` → Hz/ジッターログ → Rerun までを疎通する。

```bash
docker compose -f docker/docker-compose.yml build dev
docker compose -f docker/docker-compose.yml run --rm dev bash -lc '
  cd /workspace/ros2_ws &&
  colcon build --packages-select pai_final_pkg &&
  source install/setup.bash &&
  ros2 launch pai_final_pkg mock_inference.launch.py
'
```

個別起動例:

```bash
ros2 run pai_final_pkg mock_sensor_publisher
ros2 run pai_final_pkg act_policy_node --ros-args -p policy_mode:=mock
ros2 run pai_final_pkg rerun_visualizer --ros-args -p spawn:=false
```

チェックポイント推論（ホストに Py3.12 + training extra、および ROS 2 がある環境）:

```bash
ros2 run pai_final_pkg act_policy_node --ros-args \
  -p policy_mode:=checkpoint \
  -p checkpoint_path:=/workspace/checkpoints/synthetic_act/best_model.pt
```

## ホスト: 推論ヘルパー

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

(cd port_pick_align && pytest -m unit tests/test_infer_helpers.py -q)

# 既存 ckpt があれば integration で predict_chunk を検証
(cd port_pick_align && pytest -m integration tests/test_infer_helpers.py -q)
```

主な成果物:

- `ros2_ws/src/pai_final_pkg/pai_final_pkg/act_policy_node.py`
- `ros2_ws/src/pai_final_pkg/pai_final_pkg/rerun_visualizer.py`

整列評価 API は [evaluation.md](evaluation.md) を参照。
