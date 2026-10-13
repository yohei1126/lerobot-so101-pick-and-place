# ACT モデルの訓練および推論検証手順

本資料では、LeRobot フレームワークを用いた ACT（Action Chunking with Transformers）モデルの訓練手順、チェックポイントの保存、および推論動作の疎通確認手順を解説する。ホスト環境の Python 3.12+ 仮想環境上で実行する（LeRobot 0.6.x 系の動作要件に準拠）。

## 訓練の実行手順

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# 合成データセットの準備（未生成の場合のみ実行）
python scripts/generate_synthetic_dataset.py

# ResNet18 を視覚バックボーンとする ACT モデルを 100 ステップ訓練し、チェックポイントを保存した後に推論動作を検証する
python -m port_pick_align.training.train_act
```

訓練処理によって生成される主な成果物（Git 管理対象外）:

- `data/synthetic/lerobot/`: 訓練に使用した合成データセット
- `checkpoints/synthetic_act/best_model.pt`: 疎通確認用の学習済みモデル重み
- `checkpoints/synthetic_act/training_metrics.json`: 各ステップの損失値ログ

## 推論検証のみの実行

既存のチェックポイントを用いて推論 API の疎通確認のみを再実行する場合は、以下のコマンドを実行する。

```bash
python -m port_pick_align.training.train_act --infer-only
```

## テンソル形状と入出力仕様

モデルの観測キーおよび出力アクションチャンクのテンソル形状は、`configs/contract.yaml` の定義に準拠している。

- カメラ画像入力（`observation.images.top` / `wrist`）: `(B, 3, 480, 640)`、値域 `[0.0, 1.0]` の浮動小数点テンソル
- 関節状態量入力（`observation.state`）: `(B, 6)`
- 出力アクションチャンク（`action`）: `(30, 6)`（30 ステップ分の目標関節位置指令）

