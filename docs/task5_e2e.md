# Task 5: E2E 結合スモーク

Task 1–4 の部品を一本につなぐスモーク。実機前の Feetech / udev 準備は [hardware_udev_feetech.md](hardware_udev_feetech.md)。

## 前提

- Docker
- Host venv: `pip install -e "port_pick_align/[training,dev]"`
- Docker には torch がないため、ckpt 推論は Host、Rerun ループは Docker の `policy_mode:=mock`

## 一括実行

```bash
# 任意: 既存 ckpt があれば Stage C は再学習しない
# checkpoints/synthetic_act/best_model.pt

./scripts/e2e_pipeline_smoke.sh
```

ステージ概要:

1. Docker: `mock_sensor_publisher` → `ros2 bag record` → `data/e2e/recorded_bag`
2. Host: `scripts/convert_bag.py`（converter + validator）→ `data/e2e/lerobot`  
   （Docker Desktop 負荷でライブ bag が FRAME_DROP 等になる場合は配線確認後、`sample_bag` で品質ゲート）
3. Host: 既存 ckpt の推論スモーク（`--infer-only`）
4. Docker: `mock_inference.launch.py`（mock 推論 + Rerun、短時間）

## 単体の bag 変換

```bash
python scripts/convert_bag.py \
  --bag port_pick_align/tests/fixtures/sample_bag \
  --output data/from_bag/lerobot
```

## ホスト側結合テスト（CI integration 相当）

```bash
(cd port_pick_align && pytest -m integration tests/test_e2e_bag_to_infer.py -q)
```

## ホスト ROS 2 での checkpoint 推論

```bash
ros2 run pai_final_pkg act_policy_node --ros-args \
  -p policy_mode:=checkpoint \
  -p checkpoint_path:=/workspace/checkpoints/synthetic_act/best_model.pt
```

## ハードウェア ドライラン（実機なし）

```bash
pip install -e "port_pick_align/[training,feetech,dev]"
# Linux: deploy/udev/99-feetech-so101.rules を機材 serial に合わせてから /etc/udev/rules.d/ へ
```

詳細: [hardware_udev_feetech.md](hardware_udev_feetech.md)
