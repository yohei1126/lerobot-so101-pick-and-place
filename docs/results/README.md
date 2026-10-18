# 閉ループ評価の記録

本ディレクトリは、実測した評価ログと、未実行のプロトコルを分けて置く。`status` が `pending` のファイルは測定値を持たない。`summary` が null の項目を、達成値としてレポートや表に転記しない。

## 公式: post50 ACT（DoD 主結果）

出典: [PR #34 の post50 パイプライン結果コメント](https://github.com/yohei1126/utokyo-physical-ai-applied1-final-assignment/pull/34#issuecomment-6233795103)。

| ファイル | 内容 |
| --- | --- |
| [`post50_official_summary.json`](post50_official_summary.json) | 公式セル一覧と seed=1000 検証の状態 |
| [`eval_sim_act_post50_best_model_te_te.json`](eval_sim_act_post50_best_model_te_te.json) | **`best_model_te` × TE**: align 1.000、mean 18.1 mm、median 19.0 mm、grasp 1.000（DoD 達成） |
| [`eval_sim_act_post50_best_model_chunk30.json`](eval_sim_act_post50_best_model_chunk30.json) | **`best_model` × chunk30**: align 0.000、mean 39.2 mm、median 39.1 mm、grasp 1.000（比較用・DoD 未達） |
| [`eval_sim_act_post50_seed1000_te.pending.json`](eval_sim_act_post50_seed1000_te.pending.json) | seed=1000・50 epi TE の**未突合**プレースホルダ |

コミット時点では PR コメントの集計値のみを固定している。エピソード配列と `mean_abs_yaw_error_deg` はローカル `metrics.json` が無いため **null / 未収録**である（数値の捏造はしない）。ヨーは現行の `scripts/run_sim_eval.py` が `summarize()` 経由で算出・表示する。

### seed=1000 検証の扱い

依頼文の「成功率 100%、平均 18.28 mm、範囲 14.3–20.0 mm」は、リポジトリ内に対応 JSON が無いため **未検証**である。所有者がローカル JSON を用意したら:

```bash
python scripts/verify_eval_metrics.py \
  --metrics /path/to/metrics.json \
  --expect-seed 1000 --expect-episodes 50 \
  --expect-align 1.0 --expect-mean-pos-mm 18.28 \
  --expect-pos-min-mm 14.3 --expect-pos-max-mm 20.0 \
  --pin docs/results/eval_sim_act_post50_seed1000_te.json
```

不一致時は **JSON の値を正**とし、スクリプトが DIFF を表示する（必要なら `--allow-mismatch-pin`）。

### ローカル metrics のピン留め（公式セルの差し替え）

```bash
python scripts/verify_eval_metrics.py \
  --metrics eval/best_model_te/te/metrics.json \
  --pin docs/results/eval_sim_act_post50_best_model_te_te.json

python scripts/verify_eval_metrics.py \
  --metrics eval/best_model/chunk30/metrics.json \
  --pin docs/results/eval_sim_act_post50_best_model_chunk30.json
```

## 未実行プレースホルダ

[`eval_sim_act.pending.json`](eval_sim_act.pending.json) は、既定パス `checkpoints/sim_act/best_model.pt` 向けの旧プロトコル案内である。post50 の公式数値は上記 post50 ファイルを使う。

## 実測: scripted オラクル

`scripted_random_20.json` は、CPU かつ `MUJOCO_GL=osmesa` の環境で scripted ポリシーを 20 エピソード実行した記録である。各エピソードは 260 ステップ、初期平面位置とヨー角はランダム、Temporal Ensembling は無効、シードは 0 から 19 である。20 試行すべて整列に成功し、平均平面位置誤差は 0.0 mm、平均絶対ヨー角誤差は 0.0 deg、把持成功率は 1.0 である。`thresholds_met` は true である。これはオラクルの結果であり、学習済み ACT の結果ではない。

## 比較条件

オラクル（scripted、初期配置ランダム、Temporal Ensembling なし）:

```bash
python scripts/run_sim_eval.py --policy scripted --episodes 20 --max-steps 260 \
  --randomize-box --no-temporal-ensemble --no-save-video \
  --output-dir outputs/eval_scripted_random
```

学習済み ACT（post50 TE / chunk30）:

```bash
# TE（DoD 主結果）
python scripts/run_sim_eval.py --policy checkpoint \
  --checkpoint checkpoints/sim_act_post50/best_model_te.pt \
  --episodes 20 --max-steps 260 --randomize-box --device mps \
  --temporal-ensemble --temporal-ensemble-coeff 0.01 \
  --output-dir outputs/eval_sim_act_te

# chunk30（比較）
python scripts/run_sim_eval.py --policy checkpoint \
  --checkpoint checkpoints/sim_act_post50/best_model.pt \
  --episodes 20 --max-steps 260 --randomize-box --device mps \
  --no-temporal-ensemble --n-action-steps 30 \
  --output-dir outputs/eval_sim_act_chunk30
```

単位（rad / deg / グリッパ 0–100）は [`docs/units.md`](../units.md) を参照する。

いずれのログも、実行して `status` が `measured` になったファイルだけを数値の根拠にする。
