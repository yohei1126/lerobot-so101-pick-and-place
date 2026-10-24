<!-- markdownlint-disable MD013 -->
# 実機評価プロトコル（ACT / SO-101）

Issue #43 / #44 / #45 に対応。チェックポイントは **val_l1 だけで選ばない**。

## 1. オープンループ採点（実機の前）

```bash
cd <repo>   # lerobot-so101-pick-and-place
source "$HOME/work/lerobot-hw/.venv/bin/activate"
export PYTHONPATH="$PWD/port_pick_align/src"
export PYTORCH_ENABLE_MPS_FALLBACK=1

python scripts/score_act_checkpoints.py \
  --run-dirs \
    "$HOME/work/lerobot-hw/outputs/act_so101_clean28_trim_20261024" \
    "$HOME/work/lerobot-hw/outputs/act_so101_main_clean28_20261023" \
  --dataset-root "$HOME/work/lerobot-hw/datasets/so101_pick_sponge_main_20261023_clean28" \
  --device mps \
  --out "$HOME/work/lerobot-hw/outputs/real_eval_20261024/checkpoint_scores.json" \
  --md-out "$HOME/work/lerobot-hw/outputs/real_eval_20261024/checkpoint_scores.md"
```

見る指標:

| 指標 | 意味 |
|------|------|
| frame0 chunk travel | 開始で「動く」意図があるか（高いほど待機学習が弱い） |
| frame0 MAE_arm | 開始の模倣精度 |
| mid MAE_arm | 中盤の模倣精度 |
| score | travel を上げ、MAE を下げた合成スコア |

**推奨:** run ごとに score 上位と、frame0 travel が明確に大きい ckpt を実機候補にする。val_l1 best だけにしない。

## 2. 実機ロールアウト

```bash
./scripts/home_arm.sh --live

./scripts/run_act_real.sh --live \
  --n-action-steps 10 \
  --checkpoint <ckpt.pt>
# --live ではデフォルトで --save-video が有効（無効化は --no-save-video）

# temporal ensembling（毎ステップ推論 + 指数平均, k=0.01）
./scripts/run_act_real.sh --live \
  --temporal-ensemble \
  --checkpoint <ckpt.pt>

./scripts/home_arm.sh --live
```

ログ: `$LEROBOT_HW_ROOT/outputs/logs/act_live_*.log`  
動画: `$LEROBOT_HW_ROOT/outputs/rollouts/act_*.mp4`

## 3. 軽い trim 再学習（MPS 空き時）

```bash
# 予想: 25k steps で約 3.5–4 時間（MPS）
KEEP_BEFORE=40 UNTRIM_MIX=0.5 STEPS=25000 \
  ./scripts/train_act_light_trim.sh
```

- `KEEP_BEFORE=40`: first_motion の 40 フレーム前から残す  
- `UNTRIM_MIX=0.5`: train 側エピソードの半分は trim しない  
- `--checkpoint-interval 2500`: 中間 ckpt を残して上記スコアリングに回す  

**エージェントは長時間学習を自動起動しない。** Yohei がライブ試験後に起動する。
