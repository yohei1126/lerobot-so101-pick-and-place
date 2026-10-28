# 実機学習ポリシーのデプロイ（ACT / SmolVLA）

実機テレオペで学習した ACT（`port_pick_align.training.train_act`）および
`lerobot/smolvla_base` を fine-tune した SmolVLA を、SO-101 Follower 上で
dry-run → live する手順。Bring-up 共通は [real_robot_bringup.md](real_robot_bringup.ja.md)。
sim 学習 ACT の rad↔deg 変換ラッパーは **使わない**（こちらは [sim_to_real_act.md](sim_to_real_act.ja.md)）。

関連: Issue #76。

## 前提

| 項目 | 値 |
| --- | --- |
| ホスト | Apple Silicon Mac / LeRobot **0.6.1** / MPS |
| 実機 venv | `$LEROBOT_HW_ROOT`（既定 `$HOME/work/lerobot-hw`） |
| カメラ | top=OpenCV index **1**、wrist=index **0**、640×480@30（2026-10-25 のケーブル交換後も同じ） |
| テーブル | [現行配置 2026-10-26](real_robot_bringup.ja.md#現行テーブル配置2026-10-26)（Issue #90）。2026-10-22 と 2026-10-25 ~23:28 は使わない |
| タスク文 | `Pick up the yellow sponge and place it on the white paper` |

パスは環境変数で上書きする（絶対 `/Users/...` は使わない）。

| 変数 | 用途 |
| --- | --- |
| `LEROBOT_HW_ROOT` | データセット・出力・venv のルート |
| `PORT_FOLLOWER` | Follower シリアルポート |
| `ACT_REAL_CHECKPOINT` / `ACT_REAL_DATASET` | ACT 用 |
| `SMOLVLA_CHECKPOINT` / `SMOLVLA_DATASET` / `SMOLVLA_TASK` | SmolVLA 用 |

```bash
source "$HOME/work/lerobot-hw/.venv/bin/activate"
cd "/path/to/lerobot-so101-pick-and-place"
pip install -e "port_pick_align/[training,feetech]"
export PORT_FOLLOWER=/dev/tty.usbmodem5B8E1163071   # lerobot-find-port の結果
```

## 事前点検（Preflight）

デプロイや収録の実行前に `scripts/preflight_real_so101.sh` を実行し、ポート接続およびカメラ 2 系統の疎通を確認する:

```bash
./scripts/preflight_real_so101.sh
```

収録データの品質検証（欠損・外れ値・持続時間の点検）には `scripts/qc_teleop_dataset.py` を利用する。詳細は [real_robot_bringup.md](real_robot_bringup.ja.md#収録後の-qc) を参照。

## 安全モデル

| モード | 接続 | `send_action` | 終了時 |
| --- | --- | --- | --- |
| **dry-run（既定）** | バス read-only + カメラ。`connect()`/`configure()`/トルク書き込みなし | 呼ばない | バス切断時も `disable_torque=False` |
| **`--live`** | 通常の `robot.connect()` + `max_relative_target` | クランプ後に送る | `disconnect()` → **トルク OFF。腕を手で支える** |

追加クランプ（両モード）:

- `--max-delta-deg`（既定 3）: アーム 5 軸の 1 ステップ上限（度）
- `--max-delta-gripper`（既定 5）: グリッパ 0–100 の 1 ステップ上限
- `--max-relative-target`（既定 5、live のみ）: LeRobot 側の相対目標上限

Ctrl-C / SIGTERM でループを中断する。非常時は Follower の **12V を抜く**。

## dry-run から live までの順序

1. Bring-up 済み（ポート・キャリブ・カメラ index）を確認する。
2. **offline-check**（任意・ロボット不要）: データセットフレーム vs 予測の MAE。
3. **dry-run**（必須）: アームは動かさない。ログで state / target / safe を確認。
4. **live**（初回は短時間・小さめ delta）: 12V スイッチに手を置き、終了時は腕を支える。

## ACT（実機学習・単位変換なし）

チェックポイントは `train_act` の `best_model.pt`（正規化なし、度 / グリッパ 0–100）。
`run_sim_policy_on_real` の rad↔deg 変換は **適用しない**。

```bash
# Offline MAE（ロボット不要）
./scripts/run_act_real.sh --offline-check --device mps

# Dry-run
./scripts/run_act_real.sh --device mps --episode-time-s 15

# 推奨の初回 live
./scripts/run_act_real.sh --live --device mps \
  --max-delta-deg 2 --max-delta-gripper 3 \
  --n-action-steps 10 --episode-time-s 15
```

同等の Python モジュール呼び出し:

```bash
python -m port_pick_align.deploy.act_real --live --max-delta-deg 2 ...
```

## SmolVLA（fine-tune）

学習時の pre/post-processor を読み、`top`→`camera1`、`wrist`→`camera2` にリネームする。
`empty_cameras=0` のため **camera3 は渡さない**（学習時もスキップされていた）。

```bash
# Offline
./scripts/run_smolvla_real.sh --offline-check --device mps

# Dry-run
./scripts/run_smolvla_real.sh --device mps --episode-time-s 15

# 推奨の初回 live（chunk 50 のうち 25 ステップ実行して replan）
./scripts/run_smolvla_real.sh --live --device mps \
  --n-action-steps 25 --episode-time-s 15 \
  --max-delta-deg 2 --max-delta-gripper 3
```

## SmolVLA fine-tune 起動

macOS 向け。`caffeinate` + `start_new_session` で離脱する。

```bash
./scripts/train_smolvla.sh 10000 8
# ログ: $LEROBOT_HW_ROOT/outputs/logs/smolvla_so101_clean28_<TS>.log
```

`rename_map` と `dataset.video_backend=pyav` はスクリプト内に固定。データセット root / repo id は環境変数で変更可。

## Mac 上での検証メモ（2026-10-23 時点）

以下は **Mac / MPS 上の offline / dry-run 計測**（2026-10-23）である。実機 live の評価手順・チェックポイント選定は [real_eval_protocol.ja.md](real_eval_protocol.ja.md) を参照。

| 項目 | ACT | SmolVLA |
| --- | --- | --- |
| Offline MAE（先頭ステップ） | 約 **0.57 deg** | 約 **1.09 deg** |
| 推論レイテンシ | 約 **24 ms**/inference | 約 **335 ms**/chunk |

## 収録スクリプトとの整合

ポート・カメラ index・タスク文は [scripts/record_real_so101.sh](../scripts/record_real_so101.sh)
および [real_robot_bringup.md](real_robot_bringup.ja.md) と本デプロイ既定を一致させる:

| 項目 | 値 |
| --- | --- |
| Follower ポート例 | `/dev/tty.usbmodem5B8E1163071` |
| Leader ポート例 | `/dev/tty.usbmodem5B790143611` |
| top / wrist index | 1 / 0 |
| タスク | `Pick up the yellow sponge and place it on the white paper` |

収録手順は [real_robot_bringup.md](real_robot_bringup.ja.md) / `scripts/record_real_so101.sh`（#75）に置く。デモの前はそのページの収録前チェックを使い、収録後は同じページの `scripts/qc_teleop_dataset.py` で root を採点する。

## 参照

- [real_robot_bringup.md](real_robot_bringup.ja.md)
- [sim_to_real_act.md](sim_to_real_act.ja.md): sim ACT のみ（本手順とは別系統）
- [units.md](units.ja.md)
- 実装: `port_pick_align.deploy.real_common` / `act_real` / `smolvla_real`
