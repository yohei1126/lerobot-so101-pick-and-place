# ACT モデルの訓練および推論検証手順

本資料では、LeRobot フレームワークを用いた ACT（Action Chunking with Transformers）モデルの訓練手順、チェックポイントの保存、および推論動作の疎通確認手順を解説する。ホスト環境の Python 3.12+ 仮想環境上で実行する（LeRobot 0.6.x 系の動作要件に準拠）。

## デバイス選択

`--device` を省略した場合の選択順は MPS、CUDA、CPU である。明示した `mps` または `cuda` がその実行環境に無いときは、黙って CPU へ落とさず終了する。このリポジトリの開発用 VM には Apple Silicon が無いため、短縮設定の確認は CPU で行う。1,000 ステップ以上の本学習は MPS が使える端末で実行する。

## 訓練の実行手順

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# 合成データセットの準備（未生成の場合のみ実行）
python scripts/generate_synthetic_dataset.py

# ResNet18 を視覚バックボーンとする ACT を 100 ステップ訓練し、チェックポイント保存後に推論形状を確認する。
# これは API 疎通であり、training_metrics.json の below_recommended_steps は true になる。
python -m port_pick_align.training.train_act
```

訓練処理によって生成される主な成果物（Git 管理対象外）:

- `data/synthetic/lerobot/`: 訓練に使用した合成データセット
- `checkpoints/synthetic_act/best_model.pt`: 疎通確認用の学習済みモデル重み
- `checkpoints/synthetic_act/training_metrics.json`: 各ステップの訓練損失、検証 L1、学習率

学習ループはデータを訓練と検証に分割し、検証 L1 が最小の重みを `best_model.pt` に保存する。分割はエピソード単位（`meta.episodes` の `dataset_from_index` / `dataset_to_index`）で行い、同一エピソードのフレームが train と val に混ざらないようにする。エピソード情報が無いデータセットではフレーム単位の分割にフォールバックする。検証はデフォルトで最大 32 バッチまで評価する（`--max-val-batches 0` で全走査）。検証間隔のデフォルトは `--val-interval 100` である。学習率はコサイン減衰（`--scheduler none` で無効化）である。主な引数は `--dataset-root`、`--output-dir`、`--steps`、`--batch-size`、`--lr`、`--device`、`--val-ratio`、`--val-interval`、`--max-val-batches` である。

## シミュレーション教示データでの本学習

Task 7.1 の収集結果 `data/sim_expert/lerobot` を入力にする。推奨は 1,000 ステップ以上である。損失の数値は実行後の `training_metrics.json` だけを根拠にし、短縮実行の損失を本学習の結果として扱わない。`below_recommended_steps` が true のログは疎通確認である。

```bash
python -m port_pick_align.training.train_act \
  --preset sim \
  --steps 2000 \
  --batch-size 8 \
  --lr 1e-4

# 出力:
#   checkpoints/sim_act/best_model.pt
#   checkpoints/sim_act/training_metrics.json
```

メモリが不足する場合は `--batch-size` を下げる。CPU でのループ確認例（本学習の代替ではない）:

```bash
python -m port_pick_align.training.train_act \
  --preset sim \
  --steps 2 \
  --batch-size 1 \
  --val-interval 1 \
  --device cpu \
  --skip-infer
```

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

