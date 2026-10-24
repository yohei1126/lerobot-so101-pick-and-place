# エンドツーエンド（E2E）パイプライン結合試験

bag 記録 → 変換・品質検証 → ACT 推論 → ROS 2 / Rerun モック連携を連続実行して疎通を確認する。実機接続前の機材準備は [hardware.md](hardware.ja.md) を参照する。

## 前提条件と環境要件

- Docker ランタイム（ROS 2 実行環境）
- ホスト Python 仮想環境: `pip install -e "port_pick_align/[training,dev]"` をインストール済みであること
- 環境分離方針: Docker イメージには PyTorch を含めない構成としているため、チェックポイント推論はホスト環境で実行し、Docker 内では `policy_mode:=mock` による可視化ループを実行する。

## パイプラインの一括実行

```bash
# 既存のチェックポイント（checkpoints/synthetic_act/best_model.pt）が存在する場合、再学習を省略して推論疎通を行う
./scripts/e2e_pipeline_smoke.sh
```

実行ステージの内訳:

1. Docker 環境: `mock_sensor_publisher` から配信されるセンサトピックを `ros2 bag record` により `data/e2e/recorded_bag` へ記録する。
2. ホスト環境: `scripts/convert_bag.py` を実行し、バリデータによる品質検証を経て `data/e2e/lerobot` へデータ変換を行う（実行環境の負荷により記録バッグにフレーム欠落が生じた場合は、固定フィクスチャ `sample_bag` を用いて後続の検証を進める）。
3. ホスト環境: 学習済みチェックポイントを用いた推論スモークテスト（`--infer-only`）を実行する。
4. Docker 環境: `mock_inference.launch.py` を起動し、モック推論ノードと Rerun ノード間のトピック送受信を検証する。

## 単体 bag 変換・結合テスト・checkpoint 推論

### 1. 単体 bag ファイルの変換

```bash
python scripts/convert_bag.py \
  --bag port_pick_align/tests/fixtures/sample_bag \
  --output data/from_bag/lerobot
```

### 2. ホスト環境における結合テスト（CI integration 相当）

```bash
(cd port_pick_align && pytest -m integration tests/test_e2e_bag_to_infer.py -q)
```

### 3. ホスト ROS 2 でのチェックポイント推論

```bash
ros2 run pai_final_pkg act_policy_node --ros-args \
  -p policy_mode:=checkpoint \
  -p checkpoint_path:=/workspace/checkpoints/synthetic_act/best_model.pt
```

## Feetech extra と udev の事前準備

```bash
pip install -e "port_pick_align/[training,feetech,dev]"
# Linux 環境: deploy/udev/99-feetech-so101.rules のシリアル番号を実機に合わせて修正し、/etc/udev/rules.d/ に配置する
```

詳細な機材設定手順は [hardware.md](hardware.ja.md) を参照する。

