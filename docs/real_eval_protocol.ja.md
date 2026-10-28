<!-- markdownlint-disable MD013 -->
# 実機評価プロトコル（ACT / SO-101）

Issue #43 / #44 / #45 に対応。チェックポイントは **val_l1 だけで選ばない**。2026-10-24 のオフライン診断と 2026-10-25 夜の live（5 設定とも 0/3）がその実例である（[第4節](#act-failures-20261024)）。

本ページは学習後の実機 ACT 評価（オープンループ採点と live ロールアウト）である。テレオペ収録の QC（`scripts/qc_teleop_dataset.py` の閾値）は [収録後の QC](real_robot_bringup.ja.md#収録後の-qc) に置く。live の震え・把持失敗の分析は、その閾値表へ書かない。

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

**推奨:** run ごとに score 上位と、frame0 travel が明確に大きい ckpt を実機候補にする。val_l1 best だけにしない。2026-10-25 夜は untrim last、light-trim best、trim best、trim last、trim last + TE がいずれも 0/3 であり、val_l1 の順位は実機成功を追えていない（第4節）。

## 2. 実機ロールアウト

live の前に [現行テーブル配置（2026-10-26）](real_robot_bringup.ja.md#現行テーブル配置2026-10-26) と [live-eval チェックリスト](real_robot_bringup.ja.md#実機-live-eval-チェックリスト) を確認する（Issue #90）。

- テーブル 140 × 70 cm。Leader は左から 27 cm / 右から 101 cm。Follower は左から約 68 cm / 右から 61 cm
- 紙は右から 69 cm、手前から 27 cm（縦置き 20×30 cm）。スポンジは右から 54 cm、手前から 44 cm（縦置き 6×11 cm）
- C920 は右端、手前から 16 cm。紙・スポンジ・Follower が写る向き
- 手首カメラは Follower のグリッパ。OpenCV wrist=`0`、top=`1`
- 2026-10-22、2026-10-25 ~23:28、簡易 MuJoCo の (28, −8) / (35, 12) は使わない。2026-10-25 夜の 0/3 は、当時の 2026-10-25 ~23:28 配置での記録である（第4節）



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

<a id="act-failures-20261024"></a>

## 4. 記録: 2026-10-24 オフライン診断と 2026-10-25 夜の live

学習後の live 失敗はここに残す。収録 QC の閾値は変えない。

### 2026-10-24 オフライン診断

出典は Mac の `$HOME/work/lerobot-hw/outputs/real_eval_20261024/diagnosis.md`。この診断はオフラインであり、モーターへ指令は出していない。

live の trim / untrim ACT は、しばしば震え、把持しなかった。オフラインでは学習とデプロイの不一致は見つからなかった。カメラ、色、正規化、単位は問題なし。

オープンループでは、trim のモデルは開始姿勢から大きな動作を計画する。untrim の val_l1 best はほぼ静止のままである。live の「震え」は閉ループのアトラクタ（弱い方策）である。当日のスコア表は [checkpoint_scores_20261024.md](checkpoint_scores_20261024.md)（数値の正本は第1節の Mac 出力 `checkpoint_scores.md` / `.json`）。

原因の順位:

1. val_l1 は閉ループの能力と一致しない
2. 閉ループの保持とチャタリング
3. trim は開始時の動作には効いたが、把持には効かなかった
4. home が分布外で、そこでの方策が弱い
5. デプロイ不一致の寄与は低い

第1節の「val_l1 だけで選ばない」は、この失敗で補強する。

### 2026-10-25 夜の live（成功 0）

成功の定義は、スポンジを把持して紙の上に置くこと。試行は当時の配置（廃止した [2026-10-25 ~23:28](real_robot_bringup.ja.md#廃止した配置)）で行った。新しい評価は [現行テーブル配置（2026-10-26）](real_robot_bringup.ja.md#現行テーブル配置2026-10-26) を使う。動画ファイル名とセッションメモは [live_act_20261025_night.ja.md](results/live_act_20261025_night.ja.md)。

`n-action-steps` は 10。D だけ temporal ensemble（k=0.01）。

| 設定 | チェックポイント | 観察 | 試行 | 成功 |
|------|------------------|------|------|------|
| A | untrim clean28 `last.pt` | 横方向に振動。把持なし | A1–A3 | 0/3 |
| LT | light-trim `best_model.pt` | 振動。グリッパと腕がわずかに動く | LT1–LT3 | 0/3 |
| B | trim `best_model.pt` | 動こうとする。腕を伸ばし切れない | B1–B3 | 0/3 |
| C | trim `last.pt` | 伸ばす動作を繰り返す。途中まで伸びてから震える | C1–C3 | 0/3 |
| D | trim `last.pt` + TE k=0.01 | 震える / ほぼ静止。dual-cam の mp4 によっては静止に見える | D1–D3（D2 の再試行を含む） | 0/3 |

C の追加 1 試行（trim `last.pt`、震えながらわずかに伸びて終了）も失敗（0/1）。

要点:

- この夜に pick-and-place は成功していない
- 閉ループの震え、または腕を伸ばし切れないことが主である。TE は live の挙動を直していない
- val_l1 によるチェックポイント順位は、実機成功を依然として追えていない（本節の 2026-10-24 診断と同じ）
- 自動 dual-cam の mp4 は、目視やスマホ撮影に比べて小さな振動を過小に見せることがある
