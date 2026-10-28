# ACT モデルの訓練および推論検証手順

LeRobot 上で ACT（Action Chunking with Transformers）を訓練し、チェックポイントを保存し、推論疎通を確認する。ホスト環境の Python 3.12+ 仮想環境で実行する（LeRobot 0.6.x 系の動作要件に準拠）。

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

`--preset sim` はチェックポイントを閉ループ整列率で選ぶ。実行は `n_action_steps=30`（Temporal Ensembling なし）で、検証エピソード数の既定は 10（`--closed-loop-val-episodes` で 10〜20 に変える）。進捗と最良重みは `(整列率, -平均位置誤差)` の辞書式比較で決める（整列 0% 同士なら誤差の小さい方）。同じ間隔で Temporal Ensembling の整列率と位置誤差を別指標としてログし、最良の TE 重みを `best_model_te.pt` に同じ基準で保存する。TE は `best_model.pt` の選択には使わないが、chunk30 か TE のどちらかが改善すれば早期終了カウンタをリセットする。無効にするときは `--closed-loop-te-episodes 0`。500 step ごとに `step_XXXXX.pt` を残し、`--min-steps`（既定 3000）以降で閉ループ選択も TE も 10 パルス改善しなければ早期終了する（`--checkpoint-interval` / `--early-stop-patience` / `--min-steps` で変更。patience 0 でオフ）。コサイン減衰の下限はピーク LR の 10% である。

グリッパ損失の重みは 5 のままである。パッド姿勢では閉じたプレースと開いた解放が同じ腕の目標を共有し、L1 はグリッパ次元の条件付き平均へ寄る。重みを上げても平均は動かない。解放閾値 0.90 も変えない。中間の指令で運搬中に箱を落とすためである。シミュレータは開指令でもパッド近傍（10 cm 以内）になるまで解放しないが、解放時にパッド中心へスナップしない（最終箱 XY / ヨーをそのまま評価する）。教示側では、`n_action_steps=30` を超える閉じた approach+place のあとに開いた静止解放を置く。

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

## 教示軌道設計の背景と再収集・学習時の注意事項

本タスクの模倣学習（ACT）を成功させるため、シミュレーション教示軌道には以下の設計要件を反映している:

- **運搬中のヨー整列:** 運搬フェーズ（lift / carry）の段階から箱のヨー角をパッド目標方向へ徐々に一致させる。
- **降下アプローチと静止解放:** パッド上空からの降下区間（approach）および接触後の静止解放区間をチャンク長（`n_action_steps=30`）以上に延長する。この区間が短い教示データでは、パッド手前での早期解放や運搬停止の局所解に陥りやすい。
- **解放判定の近傍ゲート:** 解放時の強制スナップ（テレポート）は廃止されており、シミュレータ側で最終箱座標とパッド座標を厳密に評価する。

教示データを再収集・再学習する際は、上記のアプローチ区間を含む最新の収集スクリプトを使用する。収集と学習は Mac（MPS）で行い、クラウド環境では学習を実行しない。

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,training]"

python scripts/collect_sim_dataset.py \
  --episodes 100 \
  --output data/sim_expert/lerobot_post41

caffeinate -dimsu python -X faulthandler -m port_pick_align.training.train_act \
  --preset sim \
  --dataset-root data/sim_expert/lerobot_post41 \
  --output-dir checkpoints/sim_act_post41 \
  --steps 5000 \
  --batch-size 8 \
  --device mps \
  --skip-infer

# 達成判定は chunk30。TE 最良は best_model_te.pt。
DEVICE=mps EPISODES=20 N_ACTION_STEPS=30 \
  ./scripts/run_phase15_benchmark.sh checkpoints/sim_act_post41/best_model.pt

# 収集→学習→全チェックポイント×chunk30/TE 評価を一括（nohup 可）:
# 詳細と status.json / summary.md は README の「教示収集→学習→評価の一括実行」を参照。
nohup ./scripts/run_pipeline.sh --run post41 --device mps --pr N \
  > results/post41/pipeline.log 2>&1 &
```

`training_metrics.json` の `closed_loop_selection_exec` は `n_action_steps_30`、`closed_loop_te_used_for_selection` は false である。`best_closed_loop_te_align_rate` と `te_checkpoint` が TE 最良、`stopped_early` が早期終了の有無である。`history` の `closed_loop_te_align_rate` も参照する。

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

