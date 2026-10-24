# レポート用図表（再生成）

1 コマンドで学習曲線・誤差ヒストグラム・初期 XY 散布図・代表ロールアウト動画を書き出す。

## ディレクトリの役割

| 場所 | 用途 |
| --- | --- |
| `docs/figures/*.png` / `*.mp4` | **post50 本編**（レポート貼付用）。`--post50-local` の出力 |
| `docs/figures/fixtures/` | 煙試験用（`tests/fixtures/report_figures/` + scripted）。本編ではない |
| `tests/fixtures/report_figures/` | ユニットテスト用の合成 JSON のみ |

## コマンド

```bash
# オーナー Mac の post50 成果物から本編を再生成
./scripts/generate_report_figures.sh --post50-local

# 煙試験（fixtures/ 配下のみ。docs/figures 本編は上書きしない）
./scripts/generate_report_figures.sh
```

依存: `pip install -e "port_pick_align/[report,simulation]"`（図は matplotlib、動画は MuJoCo / imageio）。`.venv` があればスクリプトが自動で使う。

## 本編の出力（レポートへ貼るパス）

| ファイル | 内容 | 入力 |
| --- | --- | --- |
| `training_loss_curve.png` | train_loss / val_l1 | `checkpoints/sim_act_post50/training_metrics.json` |
| `position_error_histogram.png` | TE vs chunk30 の `position_error_mm` | `results/post50/eval/best_model_te/te/metrics.json` と `.../best_model/chunk30/metrics.json` |
| `initial_box_xy_scatter.png` | 初期箱 XY（成功/失敗・最終誤差） | 同上 TE。欠落時は同一 seed の `env.reset` で spawn XY のみ補完 |
| `sim_rollout_representative.mp4` | `best_model_te` + TE の代表 1 epi | `checkpoints/sim_act_post50/best_model_te.pt`（15 MB 超なら ffmpeg で縮小） |
| `manifest.json` | 入力パスと skip 理由 | — |

`docs/figures/_rollout_tmp/` と `_enriched_scatter_metrics.json` は一時ファイル（コミットしない）。
