# SO-101 実機 Bring-up 手順（Mac / LeRobot 0.6.1）

本手順は、WowRobo 組立済み SO-101（Leader / Follower）を Mac 上の LeRobot 0.6.1 で駆動し、テレオペまで確認するための実務手順である。機材一覧・作業エリアの寸法は [hardware.md](hardware.md) を正とする。一次情報は [SO-101](https://huggingface.co/docs/lerobot/so101)、[Cameras](https://huggingface.co/docs/lerobot/cameras)、[実機での模倣学習](https://huggingface.co/docs/lerobot/il_robots) である。

2026-10-17/18 の bring-up で確認した内容を反映している。

## 前提と環境

実機用の仮想環境は**本リポジトリの `.venv` とは分離**する（学習ジョブや sim 依存と干渉させない）。

```bash
# 例: 専用ディレクトリに venv を作成
python3.12 -m venv ~/work/lerobot-hw/.venv
source ~/work/lerobot-hw/.venv/bin/activate
pip install -U pip
pip install 'lerobot[feetech]==0.6.1'
# 収録・可視化・学習時に追加
pip install 'lerobot[dataset,viz]==0.6.1'
# 必要に応じて: pip install 'lerobot[hardware,training]==0.6.1'
```

| 項目 | 値 |
| --- | --- |
| Python | 3.12 |
| LeRobot | 0.6.1（`pip install 'lerobot[feetech]'`） |
| ホスト | Apple Silicon Mac（例: M4） |
| ロボット型 | `--robot.type=so101_follower` / `--teleop.type=so101_leader` |
| キャリブレーション id | `follower` / `leader`（以降の全コマンドで同一） |

## 安全とアームの識別

| アーム | 見分け方 | 電源 |
| --- | --- | --- |
| Leader | ハンドル付き。**グリッパ顎がない** | **5V** アダプタ |
| Follower | **グリッパ付き** | **12V** アダプタ |

- **アダプタの取り違えは厳禁。** 挿す前にラベルの電圧と基板側を指差し確認する。
- DC アダプタを外しても基板の赤 LED が点灯することがある。USB 給電によるもので正常である。駆動トルクには DC アダプタが必要である。
- テレオペ開始時、Follower は Leader 姿勢へ一気に動く。開始前に両腕の姿勢をそろえる。
- 終了（Ctrl+C）でトルクが切れる（`disable_torque_on_disconnect`）。重力で落ちるので、終了前に手で Follower を支える。
- 非常時はまず Follower の **12V プラグを抜く**。電源プラグにすぐ手が届く位置で作業する。

## 固定と作業レイアウト

1. 両アームの基部を C クランプでテーブル縁に固定する。
2. 可動範囲（基部から半径およそ 45 cm）に障害物・液体を置かない。
3. 座標系は sim / [hardware.md](hardware.md) と同じである。**原点は Follower 基部中心、+x は前方、+y は左、+z は上**（`so101_tabletop.xml` / `env.py` で確認）。

| 項目 | 配置 |
| --- | --- |
| 物体 | スポンジ（およそ 5×4×4 cm） |
| 開始エリア | 8×8 cm、中心 (28, −8) cm |
| ゴールパッド | 8×6 cm（色紙・フェルト等をテープ固定）、中心 (35, +12) cm、長辺を x に平行 |
| 上カメラ（C920） | 平面 (25, 0) cm の真上、天板から約 63 cm、真下向き（クランプ式カメラアーム） |
| 手首カメラ | キット同梱を Follower のグリッパ／手首へ取付 |

## USB とポート識別

C920 と手首カメラは USB-A である。USB-C データポート 2 + USB-A 2、PD パススルー付きハブを使い、アームを USB-C、カメラを USB-A、Mac 充電器を PD に接続する構成が実務上扱いやすい。

ポート名は `/dev/tty.usbmodemXXXX` 形式で、抜き差し後に変わることがある。**特定のシリアル番号を手順に固定しない。**

```bash
source ~/work/lerobot-hw/.venv/bin/activate
# 両アームに USB と電源を接続した状態で実行
lerobot-find-port
# プロンプトが出たら、識別したいアームの USB を 1 本だけ抜き、Enter
# 表示されたポートを記録し、USB を挿し直す。もう一方も同様（1 台ずつ）
```

| アーム | ポート（記入） | 電源 | id |
| --- | --- | --- | --- |
| Follower | `/dev/tty.usbmodem________` | 12V | follower |
| Leader | `/dev/tty.usbmodem________` | 5V | leader |

```bash
export PORT_FOLLOWER=/dev/tty.usbmodemXXXX
export PORT_LEADER=/dev/tty.usbmodemYYYY
```

**初回 bring-up では Leader / Follower のポートを取り違え、テレオペ時にグリッパ付きアームが Leader 側として動いた。** その場合はポートを再識別し、キャリブレーションをやり直す。

## モーター ID の確認

WowRobo 組立済みキットでは、STS3215 の ID 1–6 とボーレート 1,000,000 が既設定であることが多い。書き込み前にポート走査で確認し、正しければ `lerobot-setup-motors` はスキップする（公式手順はモーターを 1 個ずつ基板へつなぐ前提であり、組立済みアームではケーブル分解が必要になる）。

```bash
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('$PORT_FOLLOWER'))"
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('$PORT_LEADER'))"
```

- 正常例: `{1000000: [1, 2, 3, 4, 5, 6]}` → キャリブレーションへ進む。
- ID 欠落・別ボーレートのみ検出などの場合は電源・配線を確認し、必要なら公式どおり `lerobot-setup-motors` を実行する（[SO-101](https://huggingface.co/docs/lerobot/so101)）。

## キャリブレーション

ホスト側にキャリブレーション JSON が無いと、後続コマンド接続時に自動で始まる。明示的に実行する。

```bash
lerobot-calibrate \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower

lerobot-calibrate \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader
```

実務上の注意:

- **今キャリブレーション中のポートのアームだけを動かす。** もう一方を動かすと `same min and max` 系の失敗が起きうる。
- 開始姿勢は各関節が可動範囲の中央付近（おおむね L 字）。
- `wrist_roll` 以外の各関節を両方向いっぱいに動かす。wrist の巻き付きを避ける。
- グリッパは全開〜全閉。Leader のトリガー行程はもともと狭い。
- 保存先（既定 `HF_LEROBOT_HOME=~/.cache/huggingface/lerobot`）:
  - `~/.cache/huggingface/lerobot/calibration/robots/so_follower/follower.json`
  - `~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/leader.json`
- 再実行時は既存ファイル利用か `c` で再キャリブレーションかのプロンプトが出る。

## テレオペ

開始前に Leader を Follower と同じ休止姿勢に合わせる。

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader
```

初回 bring-up では約 60 Hz で動作した。任意で `--robot.max_relative_target=10`（度単位の 1 ステップ上限）や `--teleop_time_s=60` を付けてよい。終了前に Follower を手で支える。

確認: 各関節が同じ方向に追従する、グリッパが開閉する、異音・振動がない。

## カメラ

1. macOS では初回に「カメラへのアクセスが許可されていない」となりうる。**システム設定 → プライバシーとセキュリティ → カメラ**でターミナル（または iTerm / VS Code 等）を許可し、**アプリを再起動**してから再実行する。
2. カメラ一覧とスナップショット:

```bash
lerobot-find-cameras opencv
# 画像は outputs/captured_images/ に保存される。index は抜き差しで変わりうる
```

| カメラ | index（記入） | 解像度 / fps |
| --- | --- | --- |
| top（C920） | ____ | 640×480 / 30 |
| wrist（キット） | ____ | 640×480 / 30 |

3. 表示付きテレオペには Rerun（`lerobot[viz]`）が必要である。

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader \
  --display_data=true
```

`index_or_path` は手順 2 の値に置き換える。

## シャットダウン

1. テレオペ等のコマンドを止める（Ctrl+C）。Follower を手で支える。
2. **12V / 5V アダプタを抜く**（先に DC、その後 USB）。
3. 運搬時は基部を持つ。ケーブルを持って吊らない。

## 次のステップ（未実施）

sim チェックポイントを実機へ直接載せない。sim ポリシーは関節が**ラジアン**、実機 Follower は本体関節が**度**・グリッパが **0–100** であり、入出力契約が一致しない。

1. **デモ収録:** `lerobot-record`（`lerobot[dataset]`。キーボード操作には `hardware` extra / pynput が必要な場合あり）
2. **学習:** `lerobot-train` で ACT、`--policy.device=mps`
3. **評価:** `lerobot-rollout`（0.6.1 ではポリシー実行は record ではなく rollout）。最初は `--robot.max_relative_target` を小さめにし、低速・短時間で行う

収録例（ポート・カメラ index・`repo_id` は環境に合わせる）:

```bash
lerobot-record \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader \
  --dataset.repo_id=<HF_USER>/so101_pick_align \
  --dataset.single_task="Pick the sponge and place it aligned on the goal pad" \
  --dataset.num_episodes=10 \
  --dataset.episode_time_s=30 \
  --dataset.reset_time_s=20 \
  --dataset.push_to_hub=false \
  --display_data=true
```

評価例:

```bash
lerobot-rollout \
  --strategy.type=base \
  --policy.path=outputs/train/act_so101_real/checkpoints/last/pretrained_model \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --robot.max_relative_target=5 \
  --task="Pick the sponge and place it aligned on the goal pad" \
  --duration=30
```

## トラブルシューティング

| 症状 | 対処 |
| --- | --- |
| ポートが出ない / 変わらない | データ通信対応 USB-C か確認。ハブを外して直結。`ls /dev/tty.usbmodem*` |
| ポート取り違え（グリッパ腕が Leader 動作） | `lerobot-find-port` を 1 台ずつやり直し、再キャリブレーション |
| `Permission denied` / `Resource busy` | `lsof` でポート占有プロセスを終了 |
| `Missing motor IDs` | `scan_port`、12V/5V、3 ピン配線、ポート取り違えを確認 |
| `same min and max`（キャリブ） | 対象アームだけを動かす。中央姿勢から各関節を端まで動かす |
| テレオペ開始時に急動 | 開始前に姿勢をそろえる。`max_relative_target` を付ける |
| `not authorized to capture video` | macOS のカメラ許可 → ターミナル再起動 → `lerobot-find-cameras opencv` |
| `--display_data` で rerun エラー | `pip install 'lerobot[viz]==0.6.1'` |
| `lerobot-record` の import エラー | `pip install 'lerobot[dataset]==0.6.1'` |
| 赤 LED が DC 未接続でも点灯 | USB 給電によるもので正常。駆動には正しい DC アダプタが必要 |

## 参照

- [hardware.md](hardware.md) — 購入機材・作業エリア寸法
- [plan_b.md](plan_b.md) — 実機障害時の縮退
- [LeRobot SO-101](https://huggingface.co/docs/lerobot/so101)
- [LeRobot Cameras](https://huggingface.co/docs/lerobot/cameras)
- [Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots)
