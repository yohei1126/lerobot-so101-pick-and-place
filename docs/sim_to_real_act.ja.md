# Phase 2-2: sim 学習 ACT を実機 SO-101 Follower で試す

sim チェックポイントを実機へ**そのまま**載せない。本リポジトリのラッパーが単位・グリッパ・カメラを変換する。Bring-up 共通手順は [real_robot_bringup.md](real_robot_bringup.ja.md)、単位の背景は [units.md](units.ja.md)。

## 変換ルール（実装）

| 項目 | Sim / 契約 | 実機 LeRobot `so101_follower` |
| --- | --- | --- |
| 関節順 | `shoulder_pan` … `gripper`（6） | 同順、キーは `*.pos` |
| アーム 5 軸 | **ラジアン** | **度**（`use_degrees=True`） |
| グリッパ | **ラジアン**（閉≈0、開≈1.2） | **0–100** |
| カメラ | `top` / `wrist`、契約どおり 640×480、データセットは RGB | 同名。OpenCV 既定は RGB。解像度が違えばリサイズ |

**グリッパ極性（既定）:** LeRobot 0.6.1 の `gripper_velocity_to_joint` に合わせ、**高い `gripper.pos` = より閉じる**（0≈開、100≈閉）。契約ラジアン上限↔開、下限↔閉。逆にしたい場合は `--no-gripper-closed-is-high`（`port_pick_align.units` の「開度パーセント」意味）。

**安全:** 契約 `joint_limits` で sim 側クランプ → 実機単位へ変換 → 任意の per-step 上限（既定アーム 5°、グリッパ 10）。Live 時は LeRobot `max_relative_target` も併用可。

**カメラ不足:** sim ポリシーは `top` と `wrist` の 2 枚のみ。どちらか欠けるとエラー。第三カメラは不要・未使用。

実装: `port_pick_align.deploy.conversion` / `sim_policy_wrapper` / `run_sim_policy_on_real`。

## 前提

- Mac M4、LeRobot **0.6.1**、Follower キャリブ id=`follower`
- 実機 venv（例: `$HOME/work/lerobot-hw/.venv`）に本パッケージを editable で入れる
- sim チェックポイント（`train_act --preset sim` の `best_model.pt` 等）
- ポート変数: `PORT_FOLLOWER`（`lerobot-find-port`）
- カメラ: top=OpenCV index 1、wrist=index 0、640×480@30（bring-up と同じ）

```bash
source "$HOME/work/lerobot-hw/.venv/bin/activate"
cd "/path/to/lerobot-so101-pick-and-place"
pip install -e "port_pick_align/[training,feetech]"
```

パスは環境に合わせて読み替える。ドキュメントでは `~` ではなく `$HOME` を使う。

## Step 1 — Dry-run（必須）

観測を読み、変換後アクションを表示するだけ。**モータ指令は送らない。**

```bash
source "$HOME/work/lerobot-hw/.venv/bin/activate"
cd "/path/to/lerobot-so101-pick-and-place"

export PORT_FOLLOWER=  # lerobot-find-port の結果
CKPT="$HOME/work/lerobot-hw/outputs/sim_act/best_model.pt"  # 実際の sim ckpt に合わせる

python -m port_pick_align.deploy.run_sim_policy_on_real \
  --checkpoint "$CKPT" \
  --port "$PORT_FOLLOWER" \
  --robot-id follower \
  --device mps \
  --dry-run \
  --episode-time-s 20 \
  --max-delta-deg 5 \
  --max-delta-gripper 10
```

確認:

- 例外なく `DRY` 行が出る
- アーム角がおおむね ±110° 程度、グリッパが 0–100
- 急変があれば姿勢・カメラ・極性を疑う（`--no-gripper-closed-is-high` は最終手段）

## Step 2 — Live（低速・短時間）

1. Follower を安全姿勢。障害物なし。カメラスタンドは基部から約 35 cm 以上。
2. **12V 電源スイッチに手を置く。** 異常なら即オフ。
3. 開始前に腕を支える。終了時トルク断で落ちることがある。

```bash
python -m port_pick_align.deploy.run_sim_policy_on_real \
  --checkpoint "$CKPT" \
  --port "$PORT_FOLLOWER" \
  --robot-id follower \
  --device mps \
  --episode-time-s 20 \
  --max-delta-deg 3 \
  --max-delta-gripper 8 \
  --robot-max-relative-target 3 \
  --n-action-steps 1
```

初回は `--max-delta-deg 3` と `--episode-time-s 15`〜`20` を推奨。問題なければ少し緩める。

## 失敗時にレポートへ残すもの

| 項目 | 内容 |
| --- | --- |
| コマンド行 | dry-run / live の全文（ポートは伏せてよい） |
| チェックポイント | パス、sim 学習の step / align 率（分かる範囲） |
| 症状 | 例: 開始直後に跳ねる、グリッパが逆、カメラ KeyError、遅延 |
| ログ抜粋 | 最初と異常付近の `DRY`/`LIVE` 行 |
| 極性試し | `--no-gripper-closed-is-high` の有無と差 |
| 安全操作 | 12V オフしたか、接触・過負荷の有無 |
| 環境 | LeRobot 版、`--device`、カメラ index |

## 単体テスト（ハードウェア不要）

```bash
cd port_pick_align && pytest -m unit tests/test_sim_to_real_conversion.py -q
```

## 限界（期待値の置き方）

- Sim と実機で見た目・摩擦・キャリブが違う。成功は必須ではない。
- 実機デモで学習したポリシー向けの `lerobot-rollout` 経路とは別（単位がすでに実機側）。
- 本ラッパーは **sim ラジアン契約の `train_act` チェックポイント**向け。
