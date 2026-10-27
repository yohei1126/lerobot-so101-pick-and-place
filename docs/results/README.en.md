# Closed-loop evaluation records

This directory holds measured evaluation logs separately from protocols that have not been run. Files with `status` `pending` have no measurements. Do not copy items whose `summary` is null into reports or tables as achieved values.

## Official: post50 ACT (DoD primary result)

Source: [PR #34 post50 pipeline results comment](https://github.com/yohei1126/lerobot-so101-pick-and-place/pull/34#issuecomment-6233795103). Cell JSON files are measured copies of local `metrics.json` pinned with `scripts/verify_eval_metrics.py --pin`.

| File | Content |
| --- | --- |
| [`post50_official_summary.json`](post50_official_summary.json) | Official cell list and seed=1000 verification status |
| [`eval_sim_act_post50_best_model_te_te.json`](eval_sim_act_post50_best_model_te_te.json) | **`best_model_te` × TE** (seed 0 · 20 epi): align 1.000, mean 18.1 mm, median 19.0 mm, yaw 11.8 deg, grasp 1.000 (DoD met). Source: `results/post50/eval/best_model_te/te/metrics.json` |
| [`eval_sim_act_post50_best_model_chunk30.json`](eval_sim_act_post50_best_model_chunk30.json) | **`best_model` × chunk30** (seed 0 · 20 epi): align 0.000, mean 39.2 mm, median 39.1 mm, yaw 36.7 deg, grasp 1.000 (comparison · DoD not met). Source: `results/post50/eval/best_model/chunk30/metrics.json` |
| [`eval_sim_act_post50_seed1000_te.json`](eval_sim_act_post50_seed1000_te.json) | seed=1000 · 50 epi TE verify: align 1.000, mean 18.28 mm, min/max 14.3–20.0 mm, yaw 11.7 deg (matches requested values within tol). Source: `results/post50_verify/best_model_te/te/metrics.json` |

Each pinned file includes the episode array and `mean_abs_yaw_error_deg`. Display rounding is in the table above / `post50_official_summary.json`; the transfer source of truth is each JSON’s `summary`.

### seed=1000 verification

The request text “success rate 100%, mean 18.28 mm, range 14.3–20.0 mm” was matched against `eval_sim_act_post50_seed1000_te.json` above (`scripts/verify_eval_metrics.py`, tol 0.05, match).

```bash
python scripts/verify_eval_metrics.py \
  --metrics results/post50_verify/best_model_te/te/metrics.json \
  --expect-seed 1000 --expect-episodes 50 \
  --expect-align 1.0 --expect-mean-pos-mm 18.28 \
  --expect-pos-min-mm 14.3 --expect-pos-max-mm 20.0 \
  --pin docs/results/eval_sim_act_post50_seed1000_te.json
```

On mismatch, treat the **JSON values as authoritative**; the script prints DIFF (use `--allow-mismatch-pin` if needed).

### Pinning local metrics (replacing official cells)

```bash
python scripts/verify_eval_metrics.py \
  --metrics results/post50/eval/best_model_te/te/metrics.json \
  --pin docs/results/eval_sim_act_post50_best_model_te_te.json

python scripts/verify_eval_metrics.py \
  --metrics results/post50/eval/best_model/chunk30/metrics.json \
  --pin docs/results/eval_sim_act_post50_best_model_chunk30.json
```

`docs/results/` matches `.gitignore`’s `results/`, so new JSON needs `git add -f`.

## Unrun placeholders

[`eval_sim_act.pending.json`](eval_sim_act.pending.json) is legacy protocol guidance for the default path `checkpoints/sim_act/best_model.pt`. Use the post50 files above for official post50 numbers.

## Measured: scripted oracle

`scripted_random_20.json` records 20 episodes of the scripted policy on CPU with `MUJOCO_GL=osmesa`. Each episode is 260 steps; initial planar pose and yaw are random; Temporal Ensembling is off; seeds are 0–19. All 20 trials aligned successfully; mean planar position error is 0.0 mm, mean absolute yaw error is 0.0 deg, grasp success rate is 1.0. `thresholds_met` is true. This is an oracle result, not a trained ACT result.

## Comparison conditions

Oracle (scripted, randomized initial pose, no Temporal Ensembling):

```bash
python scripts/run_sim_eval.py --policy scripted --episodes 20 --max-steps 260 \
  --randomize-box --no-temporal-ensemble --no-save-video \
  --output-dir outputs/eval_scripted_random
```

Trained ACT (post50 TE / chunk30):

```bash
# TE (DoD primary result)
python scripts/run_sim_eval.py --policy checkpoint \
  --checkpoint checkpoints/sim_act_post50/best_model_te.pt \
  --episodes 20 --max-steps 260 --randomize-box --device mps \
  --temporal-ensemble --temporal-ensemble-coeff 0.01 \
  --output-dir outputs/eval_sim_act_te

# chunk30 (comparison)
python scripts/run_sim_eval.py --policy checkpoint \
  --checkpoint checkpoints/sim_act_post50/best_model.pt \
  --episodes 20 --max-steps 260 --randomize-box --device mps \
  --no-temporal-ensemble --n-action-steps 30 \
  --output-dir outputs/eval_sim_act_chunk30
```

For units (rad / deg / gripper 0–100), see [`docs/units.md`](../units.en.md).

For the sim logs above, only use files that have been run and whose `status` is `measured` as numeric evidence.

## Real live ACT (post-train)

Not a sim `metrics.json` and not teleop-recording QC. The 2026-10-25 night trials (0/3 on all five configs) are in [live_act_20261025_night.en.md](live_act_20261025_night.en.md). Procedure and the 2026-10-24 offline diagnosis are in [real_eval_protocol.ja.md](../real_eval_protocol.ja.md) (Japanese). New evals use the [current table layout (2026-10-26)](../real_robot_bringup.en.md#current-table-layout-2026-10-26).
