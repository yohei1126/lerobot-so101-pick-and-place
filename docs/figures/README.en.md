# Report figures (regenerate)

One command writes training curves, error histograms, initial XY scatter plots, and a representative rollout video.

## Directory roles

| Location | Purpose |
| --- | --- |
| `docs/figures/*.png` / `*.mp4` | **post50 main** (for report paste). Output of `--post50-local` |
| `docs/figures/fixtures/` | Smoke only (`tests/fixtures/report_figures/` + scripted). Not main content |
| `tests/fixtures/report_figures/` | Synthetic JSON for unit tests only |

## Commands

```bash
# Regenerate main figures from owner Mac post50 artifacts
./scripts/generate_report_figures.sh --post50-local

# Smoke (under fixtures/ only; does not overwrite docs/figures main)
./scripts/generate_report_figures.sh
```

Dependencies: `pip install -e "port_pick_align/[report,simulation]"` (figures via matplotlib, video via MuJoCo / imageio). If `.venv` exists, the script uses it automatically.

## Main outputs (paths to paste into the report)

| File | Content | Input |
| --- | --- | --- |
| `training_loss_curve.png` | train_loss / val_l1 | `checkpoints/sim_act_post50/training_metrics.json` |
| `position_error_histogram.png` | TE vs chunk30 `position_error_mm` | `results/post50/eval/best_model_te/te/metrics.json` and `.../best_model/chunk30/metrics.json` |
| `initial_box_xy_scatter.png` | Initial box XY (success/fail · final error) | Same TE. If missing, fill spawn XY only via `env.reset` with the same seed |
| `sim_rollout_representative.mp4` | One representative epi of `best_model_te` + TE | `checkpoints/sim_act_post50/best_model_te.pt` (if over 15 MB, shrink with ffmpeg) |
| `manifest.json` | Input paths and skip reasons | — |

`docs/figures/_rollout_tmp/` and `_enriched_scatter_metrics.json` are temporary (do not commit).
