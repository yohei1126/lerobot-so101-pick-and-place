<!-- markdownlint-disable MD013 -->
# 実機評価プロトコル（ACT / SO-101）

チェックポイントは **val_l1 だけで選ばない**。

本ページは学習後の実機 ACT 評価（オープンループ採点と live ロールアウト）の手順書である。テレオペ収録の QC（`scripts/qc_teleop_dataset.py` の閾値）は [収録後の QC](real_robot_bringup.ja.md#収録後の-qc) を参照。

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
  --out "$HOME/work/lerobot-hw/outputs/real_eval/checkpoint_scores.json" \
  --md-out "$HOME/work/lerobot-hw/outputs/real_eval/checkpoint_scores.md"
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

live の前に [現行テーブル配置（140×70 cm）](real_robot_bringup.ja.md#現行テーブル配置2026-10-26) と [live-eval チェックリスト](real_robot_bringup.ja.md#実機-live-eval-チェックリスト) を確認する。

- テーブル 140 × 70 cm。Leader は左から 27 cm / 右から 101 cm。Follower は左から約 68 cm / 右から 61 cm
- 紙は右から 69 cm、手前から 27 cm（縦置き 20×30 cm）。スポンジは右から 54 cm、手前から 44 cm（縦置き 6×11 cm）
- C920 は右端、手前から 16 cm。紙・スポンジ・Follower が写る向き
- 手首カメラは Follower のグリッパ。OpenCV wrist=`0`、top=`1`
- 2026-10-22、2026-10-25 ~23:28、簡易 MuJoCo の (28, −8) / (35, 12) は使わない

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

**エージェントは長時間学習を自動起動しない。** オペレータがライブ試験後に手動で起動する。
