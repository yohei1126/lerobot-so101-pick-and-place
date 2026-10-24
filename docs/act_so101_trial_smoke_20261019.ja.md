# ACT 実機トライアル スモーク（2026-10-19）

事実のみ。火曜の本収集前に、既存の SO-101 pick-sponge トライアルデータセット上で ACT がロード・学習できるかを、本 Mac（M4 / MPS）で確認したスモーク試験。

## データセット検査

3 ルートとも LeRobot **v3.0** のローカルデータセットで、`meta/`、`data/`、`videos/` を持つ。

| Dataset | Episodes | Frames | FPS | Cameras | Video (top/wrist) | Action motion |
| --- | ---: | ---: | ---: | --- | --- | --- |
| `~/work/lerobot-hw/datasets/so101_pick_sponge_trial` | 2 | 1500 | 30 | `observation.images.top`, `observation.images.wrist` (640×480 AV1) | 50.0 s / 1500 frames each | **Near-zero**: both episodes action std ≈ 0 (static pose) |
| `~/work/lerobot-hw/datasets/so101_pick_sponge_trial2` | 2 | 1500 | 30 | same | 50.0 s / 1500 frames each | **Partial content**: epi0 has motion; **epi1 action std ≈ 0** (static). Files are complete (not truncated). |
| `~/work/lerobot-hw/datasets/so101_pick_sponge_trial3` | 2 | 1500 | 30 | same | 50.0 s / 1500 frames each | **Both episodes have motion** |

記録ログは `~/work/lerobot-hw/outputs/record_trial_*.log` 配下:

- 最初の `trial` 試行（`…2337.log`）は保存時に失敗（`meta/` 欠落）。成功した書き換えは `…2338.log`。
- `trial2`（`…2342.log`）と `trial3`（`…234850.log`）は 2 エピソード後に正常終了。
- 中断した `trial3` 開始が 2 件（`…2347.log`、`…234805.log`）あり、早期失敗（rerun gRPC）。最終の `…234850.log` が完了。
- テレオペ／記録は `use_degrees: True`（関節値は度で格納）。

## 本リポジトリでの ACT 学習方法

文書化された経路: [`docs/training.md`](training.ja.md) →
`python -m port_pick_align.training.train_act`（コース `.venv`、LeRobot 0.6.1）。

- 既定 / `--preset sim` は `data/sim_expert/…` 配下の sim データセットと閉ループ MuJoCo 選択を対象とする。
- 実機スモークではローカル LeRobot ルートへ `--dataset-root` を渡し、**`--preset sim` は使わない**
  （閉ループ sim 評価を避ける）。カメラ／チャンクは `configs/contract.yaml` のキーに合わせる
  （`top` / `wrist`、chunk_size 30）。契約の関節制限は **ラジアン**；これらの
  トライアルデータセットは **度**。

利用可能な別環境: `~/work/lerobot-hw/.venv` に `lerobot-train`（0.6.1）あり。スモークは
過去の sim ACT 作業との一貫性のためリポジトリの trainer を使用した。

## スモーク学習（実行済み）

使用データセット: **trial3 のみ**（両エピソードとも可動）。

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

### `training_metrics.json` の損失・val L1

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

成果物（git 外。大きな `.pt` はコースリポジトリへ未コピー）:

- ログ: `~/work/lerobot-hw/outputs/logs/act_so101_trial_smoke_20261019.log`
- メトリクス: `~/work/lerobot-hw/outputs/act_so101_trial_smoke_20261019/training_metrics.json`
- チェックポイント: `…/best_model.pt`、`…/last.pt`

## 判定

| Question | Fact |
| --- | --- |
| 既存データは学習に使えるか？ | **形式は可**（3 つとも有効な LeRobot v3）。**動作品質:** **trial3** を使う（後でマージするなら trial2 epi0 も可）。学習には **trial1 をスキップ**（静止アクション）。trial2 はディスク上は完全；epi1 は静止。 |
| スモーク学習は成功したか？ | **Yes**: MPS 上でデータロード、train loss は 200 ステップで ~113 → ~44 に低下、val L1 はわずかに改善。 |
| 火曜のブロッカー | **成功した pick エピソード数を増やす**必要がある（2 epi はパイプライン確認のみ）。度対応の学習／デプロイ経路を優先するか、sim と混ぜる前に契約ラジアンへ変換する。記録の `root` は絶対パスで既存であること（tilde 展開＋`meta/` 事前作成で最初の trial 失敗を回避済み）。 |
| 推奨次ステップ | 全エピソードに動作がある成功スポンジピックを数十本以上収集する；その後結合セットで長めの ACT 学習（1000+ ステップ、`arch=full`）。この 200 ステップスモークをデプロイ可能なポリシーとみなさない。 |
