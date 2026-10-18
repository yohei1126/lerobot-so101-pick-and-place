# レポート用図表（再生成）

1 コマンドで学習曲線・誤差ヒストグラム・初期 XY 散布図・代表ロールアウト動画を `docs/figures/` に書き出す。

## コマンド

```bash
# リポジトリ内フィクスチャ + scripted 動画（クラウドでも可）
./scripts/generate_report_figures.sh

# オーナー Mac の post50 成果物から本編用に再生成
./scripts/generate_report_figures.sh --post50-local
# または
DEVICE=mps python3 scripts/generate_report_figures.py \
  --training-metrics checkpoints/sim_act_post50/training_metrics.json \
  --te-metrics eval/best_model_te/te/metrics.json \
  --chunk30-metrics eval/best_model/chunk30/metrics.json \
  --checkpoint checkpoints/sim_act_post50/best_model_te.pt \
  --video-policy checkpoint --device mps --temporal-ensemble
```

依存: `pip install -e "port_pick_align/[report,simulation]"`（図は matplotlib、動画は MuJoCo / imageio）。

## 出力ファイル（レポートへ貼るパス）

| ファイル | 内容 |
| --- | --- |
| `training_loss_curve.png` | `training_metrics.json` の train_loss / val_l1 |
| `position_error_histogram.png` | TE と chunk30 の `position_error_mm` ヒストグラム |
| `initial_box_xy_scatter.png` | `initial_box_xy` を成功/失敗と最終誤差で色分け |
| `sim_rollout_representative.mp4` | 代表 1 エピソードのロールアウト |
| `manifest.json` | 今回書けた／スキップした入力の記録 |

`docs/results/` の post50 公式 JSON は PR コメント集計のみで `samples` が null のため、ヒストグラム／散布図には使えない。per-episode 付きのローカル `metrics.json` を渡すこと。

## フィクスチャ注意

`./scripts/generate_report_figures.sh`（引数なし）は `tests/fixtures/report_figures/` の合成データと **scripted** ロールアウトで煙試験用成果物を作る。**post50 本編の数値・ACT 動画ではない。** レポート本編には `--post50-local` の出力を使う。

本ディレクトリにコミットされている PNG/MP4 は、その煙試験出力である（`manifest.json` の `inputs` を確認）。

一時ディレクトリ `docs/figures/_rollout_tmp/` はコミットしない。
