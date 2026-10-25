# 実機テレオペデータセット: `so101_pick_sponge_main`（clean28）

事実記録。計算日時は 2026-10-23 およそ 01:15 SGT（作業用 Mac、LeRobot 0.6.1 venv）。読み取りのみ。データセットは変更していない。

**データセット本体は git 外（Mac 上）にある。** 本ドキュメントとコンタクトシート画像のみをリポジトリに置く。

関連手順: [real_robot_bringup.md](real_robot_bringup.ja.md)。学習手順: [training.md](training.ja.md)。

## データセット

| | Mac 上のパス | エピソード | フレーム | `du -sh` |
| --- | --- | ---: | ---: | ---: |
| raw | `$HOME/work/lerobot-hw/datasets/so101_pick_sponge_main_20261020` | 32（0–31） | 23,610 | 350M |
| clean | `$HOME/work/lerobot-hw/datasets/so101_pick_sponge_main_20261023_clean28` | 28（0–27） | 20,660 | 309M |

- タスク（単一、`task_index` 0）: `Pick up the yellow sponge and place it on the white paper`
- `repo_id` `yohei1126/so101_pick_sponge_main`、`robot_type` `so_follower`、`codebase_version` v3.0、split train `0:28`
- fps 30。特徴量: `action`（6, float32）、`observation.state`（6, float32）、`observation.images.top`、`observation.images.wrist`、timestamp、frame_index、episode_index、index、task_index
- 関節名（action / state）: `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper`（`.pos`）
- カメラ: `observation.images.top`、`observation.images.wrist`。いずれも 640×480、AV1、yuv420p、30 fps、g=2、crf=30、preset 12、音声なし
- レイアウト: parquet 3 ファイル、カメラあたり mp4 3 ファイル（`chunk-000/file-000..002`）
- ディレクトリ名は `20261020` だが、収録は 2026-10-22 23:30 〜 2026-10-23 00:38 SGT（ログ参照）
- これらのエピソードの物理配置は廃止した 2026-10-22 のテーブルであり、2026-10-26 の正ではない。[廃止した配置](real_robot_bringup.ja.md#廃止した配置) を参照

## clean ↔ raw の対応（action / state 配列が一致することを確認済み）

- clean 0–7 = raw 0–7
- clean 8–16 = raw 10–18
- clean 17–19 = raw 20–22
- clean 20–27 = raw 24–31

除外した raw エピソード:

| raw | 理由 |
| ---: | --- |
| 8（750 frames）、9（743 frames） | 全関節の action レンジが 0（静止） |
| 19 | `shoulder_lift` mean `|action-state|` 9.73、max 45.2 |
| 23 | `shoulder_lift` mean `|action-state|` 12.07、max 34.4 |

clean セットの `shoulder_lift` mean lag はエピソードあたり 1.36〜2.58。

## エピソード長

- 20 エピソードが 750 frames（25.0 s = `episode_time_s` 上限）
- 8 エピソードが 705–709 frames（23.5–23.63 s; clean 7, 15, 16, 23–27）
- 平均 24.60 s、std 0.64 s（母集団; 標本 std 0.65）、min 23.50、max 25.00
- タイムスタンプは 1/30 s で連続。各エピソードで `frame_index` は 0..n-1
- 動き: 最初の動き（いずれかの関節が初期値から 1 超）は 1.2–6.1 s。腕の定着（全関節が最終値の 1 以内）は 7.9–13.6 s、平均 9.6 s。各エピソード末尾のおおよそ 10–17 s は静止

## 関節レンジ（clean 全体、min / max）

| joint | action min | action max | state min | state max | mean abs(action-state) |
| --- | ---: | ---: | ---: | ---: | ---: |
| shoulder_pan | -52.7 | 16.7 | -52.5 | 16.4 | 0.63 |
| shoulder_lift | -69.1 | 84.0 | -68.0 | 81.5 | 1.66 |
| elbow_flex | -96.3 | 96.8 | -94.7 | 96.9 | 1.67 |
| wrist_flex | -0.6 | 101.0 | 0.7 | 100.3 | 0.89 |
| wrist_roll | -25.7 | 8.7 | -25.4 | 8.5 | 0.24 |
| gripper | 0.0 | 77.4 | 0.8 | 76.8 | 1.08 |

## グリッパと把持回数

エピソードごとのグリッパ: idle およそ 14–48 → 開 およそ 48–77 → 閉 およそ 0–1（grasp）→ 再開 およそ 14–49（release）で静止。

idle / release 後の値が中間付近にあるため、固定中点閾値は信頼できない。action に対するエピソード別ヒステリシスで数えた: grasp = グリッパが（エピソード min + 5）未満へ下降、release = その後（エピソード min + 10）超へ上昇。

- 27/28 エピソード: grasp 1 回・release 1 回。grasp 4.4–8.4 s、release 5.5–10.4 s
- clean 25（raw 29）: grasp 2・release 2（G 3.8 s、R 4.5 s、G 5.7 s、R 7.7 s）＝再把持
- エピソードごとの gripper action max 48.2–77.4。min は 0.0–0.6（clean 10 / raw 12 のみ min 10.3。およそ 10 未満まで閉じない）

エピソード別表（Mac 上）: `per_episode_events.csv`。

## 外れ値・注記

- clean 25（raw 29）: 再把持（閉 2 回）
- clean 15, 16（raw 17, 18）: 他より広い姿勢レンジ（`elbow_flex` action min -96.3 / -82.1、他はおおむね ≥ -44; `shoulder_lift` max 84.0 / 80.7; `wrist_flex` max およそ 101）。`shoulder_lift` lag 最大（2.58, 2.44; z > 2.5）。clean 15 の定着が最遅（13.6 s）
- clean 27（raw 31）: `elbow_flex` mean lag 5.00（セット平均 1.68、z > 2.5）
- clean 0: 開始最遅（6.1 s）、grasp 最遅（8.4 s）
- clean 10（raw 12）: gripper 最小 10.3
- `wrist_roll` action が clean 0–9 のおよそ -8..+9 から、clean 23–27 のおよそ -26..-13 へドリフト

## 収録セッション

ログ: `$HOME/work/lerobot-hw/outputs/record_main_*.log`（時刻は SGT）。いずれも root `.../so101_pick_sponge_main_20261020`、`episode_time_s` 25、`reset_time_s` 10、fps 30、`push_to_hub` False。

| log | resume | num_episodes 引数 | 記録されたエピソード | 終了 |
| --- | --- | ---: | --- | --- |
| 20261022_231932 | False | 50 | 0–12 開始（13） | ep 12 中に KeyboardInterrupt（23:28） |
| 20261022_233039 | False | 50 | 0–9（10） | ep 9 中に Esc、停止 23:37:54 |
| 20261022_233916 | True | 10 | 10–19（10） | 正常停止 23:46:30 |
| 20261023_002944 | True | 12 | 20–31（12） | 正常停止 00:38:25 |

2 回目セッションは `resume=False` でエピソード 0 から再開始したため、raw の 32 エピソードはセッション 2–4（10 + 10 + 12）由来。raw 9 が 743 frames なのは Esc で途中終了したため、とログから推定できる。1 回目セッションのデータはデータセットに含まれない。

## サンプルフレーム（コンタクトシート）

![clean28 contact sheet: ep 0 / 14 / 27 の start・midgrasp・end（top / wrist）](images/so101_main_clean28_contact_sheet.jpg)

行 = clean ep 0, 14, 27。列 = start top/wrist、midgrasp top/wrist（grasp と release の中点）、end top/wrist。開始時はスポンジが紙の外、midgrasp でグリッパ保持、終了時は紙の上。

個別 PNG（Mac 上）: `$HOME/work/lerobot-hw/outputs/dataset_summary_20261023/ep{00,14,27}_{start,midgrasp,end}_{top,wrist}.png`。

## 夜間 ACT 学習（開始 2026-10-23 00:52 SGT）

結果は未確定（pending）。

| 項目 | 値 |
| --- | --- |
| エントリ | `port_pick_align.training.train_act` |
| arch | `full` |
| device | MPS |
| batch | 8 |
| lr | 1e-4 |
| steps | 25,000 |
| val_ratio | 0.1 |
| selection | `val_l1` |
| 速度 | およそ 0.75 s / step |
| 見込み終了 | およそ 06:10 SGT |
| 出力 | `$HOME/work/lerobot-hw/outputs/act_so101_main_clean28_20261023` |
