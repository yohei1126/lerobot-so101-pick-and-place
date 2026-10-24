# ACT real-robot trial smoke (2026-10-19)

Facts only. Smoke test that ACT can load and train on existing SO-101 pick-sponge
trial datasets on this Mac (M4 / MPS), before Tuesday's larger collection.

## Dataset inspection

All three roots are LeRobot **v3.0** local datasets with `meta/`, `data/`, `videos/`.

| Dataset | Episodes | Frames | FPS | Cameras | Video (top/wrist) | Action motion |
| --- | ---: | ---: | ---: | --- | --- | --- |
| `~/work/lerobot-hw/datasets/so101_pick_sponge_trial` | 2 | 1500 | 30 | `observation.images.top`, `observation.images.wrist` (640×480 AV1) | 50.0 s / 1500 frames each | **Near-zero**: both episodes action std ≈ 0 (static pose) |
| `~/work/lerobot-hw/datasets/so101_pick_sponge_trial2` | 2 | 1500 | 30 | same | 50.0 s / 1500 frames each | **Partial content**: epi0 has motion; **epi1 action std ≈ 0** (static). Files are complete (not truncated). |
| `~/work/lerobot-hw/datasets/so101_pick_sponge_trial3` | 2 | 1500 | 30 | same | 50.0 s / 1500 frames each | **Both episodes have motion** |

Record logs under `~/work/lerobot-hw/outputs/record_trial_*.log`:

- First `trial` attempt (`…2337.log`) failed on save (`meta/` missing); successful rewrite is `…2338.log`.
- `trial2` (`…2342.log`) and `trial3` (`…234850.log`) exited cleanly after 2 episodes.
- Two aborted `trial3` starts (`…2347.log`, `…234805.log`) failed early (rerun gRPC); final `…234850.log` completed.
- Teleop/record used `use_degrees: True` (joint values stored in degrees).

## How this repo trains ACT

Documented path: [`docs/training.md`](training.en.md) →
`python -m port_pick_align.training.train_act` (course `.venv`, LeRobot 0.6.1).

- Default / `--preset sim` targets sim datasets under `data/sim_expert/…` and closed-loop MuJoCo selection.
- For real-robot smoke: pass `--dataset-root` to a local LeRobot root, **do not** use `--preset sim`
  (avoids closed-loop sim eval). Cameras/chunk match `configs/contract.yaml` keys
  (`top` / `wrist`, chunk_size 30). Contract joint limits are in **radians**; these
  trial datasets are in **degrees**.

Also available: `~/work/lerobot-hw/.venv` has `lerobot-train` (0.6.1). Smoke used the
repo trainer for consistency with prior sim ACT work.

## Smoke train (executed)

Dataset used: **trial3 only** (both episodes movable).

```bash
cd ~/work/lerobot-so101-pick-and-place
source .venv/bin/activate

OUT="$HOME/work/lerobot-hw/outputs/act_so101_trial_smoke_20261019"
LOG="$HOME/work/lerobot-hw/outputs/logs/act_so101_trial_smoke_20261019.log"

caffeinate -dimsu python -X faulthandler -m port_pick_align.training.train_act \
  --dataset-root "$HOME/work/lerobot-hw/datasets/so101_pick_sponge_trial3" \
  --repo-id local/so101_pick_sponge_trial3 \
  --output-dir "$OUT" \
  --steps 200 \
  --batch-size 2 \
  --lr 1e-4 \
  --device mps \
  --val-ratio 0.5 \
  --val-interval 50 \
  --max-val-batches 8 \
  --selection-metric val_l1 \
  --arch smoke \
  --skip-infer \
  2>&1 | tee "$LOG"
```

### `training_metrics.json` losses and val L1

| Field | Value |
| --- | --- |
| `result` | `PASS` |
| `device` | `mps` |
| `arch` | `smoke` |
| `steps` | 200 (`below_recommended_steps: true`) |
| `n_train_episodes` / `n_val_episodes` | 1 / 1 (750 frames each) |
| step 1 `train_loss` | 113.253479 |
| step 10 `train_loss` | 66.735565 |
| step 200 `train_loss` | 44.067341 |
| `best_train_loss` | 19.880795 |
| val_l1 @50 | 38.773180 |
| val_l1 @100 | 38.460627 |
| val_l1 @150 | 38.314042 |
| val_l1 @200 / `best_val_l1` | 38.253009 |
| Wall time | ~46 s (process exit 0) |

Artifacts (outside git; large `.pt` not copied into the course repo):

- Log: `~/work/lerobot-hw/outputs/logs/act_so101_trial_smoke_20261019.log`
- Metrics: `~/work/lerobot-hw/outputs/act_so101_trial_smoke_20261019/training_metrics.json`
- Checkpoints: `…/best_model.pt`, `…/last.pt`

## Verdict

| Question | Fact |
| --- | --- |
| Previous data usable for training? | **Format yes** (all three are valid LeRobot v3). **Motion quality:** use **trial3** (and trial2 epi0 if merging later). **Skip trial1** for learning (static actions). trial2 is complete on disk; epi1 is static. |
| Smoke train succeeded? | **Yes**: data loaded on MPS, train loss fell from ~113 → ~44 over 200 steps, val L1 improved slightly. |
| Tuesday blockers | Need **more successful pick episodes** (2 epi is pipeline-only). Prefer degrees-aware training/deploy path or convert to contract radians before mixing with sim. Ensure record `root` is an absolute existing path (tilde expand + pre-create `meta/` avoided the first trial failure). |
| Recommended next step | **Collect more episodes** (dozens+) of successful sponge picks with motion in every episode; then a longer ACT train (1000+ steps, `arch=full`) on the combined set. Do not treat this 200-step smoke as a deployable policy. |
