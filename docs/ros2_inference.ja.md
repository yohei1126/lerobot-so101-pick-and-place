# ROS 2 推論ノードおよび Rerun 可視化仕様

本資料では、ROS 2 Humble 環境下におけるセンサモック、推論ノード、および Rerun 可視化ノードの実行手順と連携仕様を解説する。

## Docker 環境でのモック推論パイプライン（PyTorch 非依存）

Docker コンテナ内では、`policy_mode:=mock` を指定することで、PyTorch を導入することなく ROS 2 通信層と可視化基盤の疎通を検証できる。センサトピックは `ApproximateTimeSynchronizer` により同期され、推論ノードから `/joint_commands` が発行された後、周期ジッターのログ出力および Rerun による可視化が行われる。

```bash
docker compose -f docker/docker-compose.yml build dev
docker compose -f docker/docker-compose.yml run --rm dev bash -lc '
  cd /workspace/ros2_ws &&
  colcon build --packages-select pai_final_pkg &&
  source install/setup.bash &&
  ros2 launch pai_final_pkg mock_inference.launch.py
'
```

各ノードを個別に起動する場合の実行例:

```bash
# センサトピック（Top/Wrist カメラ画像、関節状態量）の配信モック
ros2 run pai_final_pkg mock_sensor_publisher

# 推論ノードのモックモード起動
ros2 run pai_final_pkg act_policy_node --ros-args -p policy_mode:=mock

# Rerun 可視化ノードの起動（Web/ネイティブビューアの自動起動を行わない設定）
ros2 run pai_final_pkg rerun_visualizer --ros-args -p spawn:=false
```

学習済みチェックポイントを用いた推論ノードの起動（ROS 2 および PyTorch が利用可能なホスト環境等）:

```bash
ros2 run pai_final_pkg act_policy_node --ros-args \
  -p policy_mode:=checkpoint \
  -p checkpoint_path:=/workspace/checkpoints/synthetic_act/best_model.pt
```

## ホスト環境における推論ヘルパーの単体・統合テスト

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# 単体テスト: 推論用テンソル変換およびアクション展開ヘルパーの検証
(cd port_pick_align && pytest -m unit tests/test_infer_helpers.py -q)

# 統合テスト: 既存チェックポイントを用いた predict_chunk の推論検証
(cd port_pick_align && pytest -m integration tests/test_infer_helpers.py -q)
```

主な関連ソースコード:

- `ros2_ws/src/pai_final_pkg/pai_final_pkg/act_policy_node.py`: ROS 2 推論ノード実装
- `ros2_ws/src/pai_final_pkg/pai_final_pkg/rerun_visualizer.py`: Rerun 連携ノード実装

整列誤差の集計 API 仕様については [evaluation.md](evaluation.ja.md) を参照する。

