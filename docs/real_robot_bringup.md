# SO-101 実機 Bring-up 手順（Mac / LeRobot 0.6.1）

本手順は、WowRobo 組立済み SO-101（Leader / Follower）を Mac 上の LeRobot 0.6.1 で駆動し、テレオペ・カメラ付き収録まで確認するための実務手順である。機材一覧・作業エリアの寸法は [hardware.md](hardware.md) を正とする。一次情報は [SO-101](https://huggingface.co/docs/lerobot/so101)、[Cameras](https://huggingface.co/docs/lerobot/cameras)、[実機での模倣学習](https://huggingface.co/docs/lerobot/il_robots) である。

2026-10-17/18 の bring-up、および **2026-10-18 夜の実機検証**（UGREEN ハブ経由の接続・両カメラ同時配信・60 Hz テレオペ・`lerobot-record` 2 回成功、23:48–23:50 SGT 含む）を反映している。

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
| ホスト | Apple Silicon Mac（例: MacBook Pro M4） |
| ロボット型 | `--robot.type=so101_follower` / `--teleop.type=so101_leader` |
| キャリブレーション id | `follower` / `leader`（以降の全コマンドで同一） |

## 安全とアームの識別

| アーム | 見分け方 | 電源 |
| --- | --- | --- |
| Leader | ハンドル付き。**グリッパ顎がない** | **5V** アダプタ |
| Follower | **グリッパ付き** | **12V** アダプタ |

- **アダプタの取り違えは厳禁。** 挿す前にラベルの電圧と基板側を指差し確認する。
- DC アダプタを外しても基板の赤 LED が点灯することがある。USB 給電によるもので正常である。駆動トルクには DC アダプタが必要である。
- **Follower の 12V アダプタは必ず ON（LED 点灯）にする。** OFF のままだとテレオペは動くが Follower は動かない。2026-10-18 実測: Follower 約 12.6 V / Leader 約 5.5 V。
- テレオペ開始時、Follower は Leader 姿勢へ一気に動く。開始前に両腕の姿勢をそろえる（Leader は中立付近から。関節がキャリブ範囲端だと指令が変わらない）。
- 終了（Ctrl+C）でトルクが切れる（`disable_torque_on_disconnect`）。重力で落ちたり微動することがあるので正常。終了前に手で Follower を支える。
- 非常時はまず Follower の **12V プラグを抜く**。電源プラグにすぐ手が届く位置で作業する。
- **カメラスタンドは Follower の可動範囲外に置く**（基部からおよそ 35 cm 以上）。紙はスタンドと反対側に置く。位置はテープで印を付ける。テレオペ中にスタンドへ接触した実績あり。

## 固定と作業レイアウト

1. 両アームの基部を C クランプでテーブル縁に固定する。
2. 可動範囲（基部から半径およそ 45 cm）に障害物・液体を置かない。
3. 座標系は sim / [hardware.md](hardware.md) と同じである。**原点は Follower 基部中心、+x は前方、+y は左、+z は上**（`so101_tabletop.xml` / `env.py` で確認）。

| 項目 | 配置 |
| --- | --- |
| 物体 | スポンジ（およそ 5×4×4 cm） |
| 開始エリア | 8×8 cm、中心 (28, −8) cm |
| ゴールパッド | 8×6 cm（色紙・フェルト等をテープ固定）、中心 (35, +12) cm、長辺を x に平行。カメラポールから離れた側に置く |
| 上カメラ（C920） | VIJIM LS08 アーム上、USB-A 経由ハブ。スポンジ・紙・グリッパ作業域が画角に入ること（trial3 先頭でもグリッパ画外 → 少し下げて後ろへ／下向きに傾ける） |
| 手首カメラ | キット同梱（USB2.0_CAM1 / Sonix 05a3:9230）。Follower 固定顎側・グリッパモーター下に取付。ケーブルに余裕を持たせてテープ固定 |

## USB とポート識別

2026-10-18 検証: MacBook Pro M4 + **UGREEN USB-C ハブ**経由で接続。ハブ経由でもポートは不変だった。抜き差し後は名前が変わることがあるので `ls /dev/tty.usbmodem*` で確認する。

C920 と手首カメラは USB-A である。USB-C データポート 2 + USB-A 2、PD パススルー付きハブを使い、アームを USB-C、カメラを USB-A、Mac 充電器を PD に接続する構成が実務上扱いやすい。

```bash
source ~/work/lerobot-hw/.venv/bin/activate
# 両アームに USB と電源を接続した状態で実行
lerobot-find-port
# プロンプトが出たら、識別したいアームの USB を 1 本だけ抜き、Enter
# 表示されたポートを記録し、USB を挿し直す。もう一方も同様（1 台ずつ）
```

| アーム | ポート（2026-10-18 検証） | 電源 | id |
| --- | --- | --- | --- |
| Leader | `/dev/tty.usbmodem5B790143611` | 5V | leader |
| Follower | `/dev/tty.usbmodem5B8E1163071` | 12V | follower |

```bash
export PORT_FOLLOWER=/dev/tty.usbmodem5B8E1163071
export PORT_LEADER=/dev/tty.usbmodem5B790143611
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

1. macOS では初回に「カメラへのアクセスが許可されていない」となりうる。**システム設定 → プライバシーとセキュリティ → カメラ**でターミナル（または iTerm / VS Code 等）を許可し、**アプリを再起動**してから再実行する。2026-10-18 検証では権限問題は発生しなかった。
2. **iPhone Continuity Camera が index を奪う。** iPhone 側の Continuity Camera アラートで Disconnect を選び、さらに **設定 → 一般 → AirPlay と Continuity → Continuity Camera をオフ**にする。
3. カメラ一覧とスナップショット:

```bash
lerobot-find-cameras opencv
# 画像は outputs/captured_images/opencv_*.png に保存される。index は抜き差しで変わりうる
# ffmpeg avfoundation の番号は OpenCV / LeRobot と異なる。必ず上記と保存画像で確認する
```

| カメラ | OpenCV / LeRobot index（2026-10-18） | 解像度 / fps |
| --- | --- | --- |
| wrist（キット USB2.0_CAM1） | 0 | 640×480 / 30 |
| top（C920） | 1 | 640×480 / 30 |
| 内蔵カメラ | 2 | （未使用） |

2026-10-18: ハブ経由で両外部カメラを同時配信（640×480@30、実測約 29.7 fps）。

4. 表示付きテレオペ（2026-10-18 検証: 60 Hz、最低 57 Hz、120 s、カメラ警告なし。スポンジを紙へ移動）:

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=/dev/tty.usbmodem5B8E1163071 \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader \
  --teleop.port=/dev/tty.usbmodem5B790143611 \
  --teleop.id=leader \
  --display_data=true \
  --fps=60 \
  --teleop_time_s=120
```

Rerun ビューアは表示のみで保存しない。`$PORT_*` を使う場合は上記ポートを環境変数に合わせる。

## 収録前チェック（必須）

**毎回 `lerobot-record` の直前に実施する。** 未通過のまま収録しない。同じ robot / teleop / cameras フラグで 60 秒テレオペし、Rerun で確認する。

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader \
  --display_data=true \
  --fps=60 \
  --teleop_time_s=60
```

| # | 確認項目 |
| --- | --- |
| (a) | **top:** スポンジ・白い紙・グリッパが作業域全体で画角に入る |
| (b) | **wrist:** 接近時にグリッパ先端とスポンジが見える |
| (c) | Leader を pick-and-place 全経路（端点含む）でゆっくり動かし、Follower がカメラスタンド／C920 ポール（基部から約 35 cm 以上離す）やテーブルクランプに当たらない |
| (d) | カメラ警告なし、ループがおよそ 60 Hz を維持 |
| (e) | スポンジと紙がテープ印の開始位置にある |

どれか NG なら Ctrl+C → 修正 → 再チェック。**すべて OK になってから Rerun を閉じ、次節の `lerobot-record` に進む。**

## デモ収録（`lerobot-record`）

**前提:** 直前の [収録前チェック（必須）](#収録前チェック必須) をすべて通過していること。

2026-10-18 試行（2 回とも成功）:

| 試行 | 結果 |
| --- | --- |
| 1 回目 | 2 epi × 25 s、各 750 frames @ 30 fps、約 15 MB、slow-loop 警告なし |
| 2 回目（23:48–23:50 SGT） | 同様に 2 epi × 25 s、合計 1500 frames、約 17 MB。slow-loop / OpenCV カメラエラーなし |

コマンドは共通。`--dataset.root=$HOME/work/lerobot-hw/datasets/<name>`（絶対パス。`~` 不可）。**既存 root の再利用は失敗するので、実行ごとに新しいデータセット名を付ける。**

```bash
# 例: <name> を実行ごとに変える（so101_pick_sponge_trial2 など）
lerobot-record \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader \
  --dataset.repo_id=yohei1126/so101_pick_sponge_trial \
  --dataset.single_task='Pick up the yellow sponge and place it on the white paper' \
  --dataset.num_episodes=2 \
  --dataset.episode_time_s=25 \
  --dataset.reset_time_s=10 \
  --dataset.fps=30 \
  --dataset.no_stamp=true \
  --dataset.push_to_hub=false \
  --dataset.root=$HOME/work/lerobot-hw/datasets/<name> \
  --display_data=true
```

注意:

- `--dataset.root=` の直後に `~` を書くと展開されない。**絶対パスまたは `$HOME` を使う。** 既存ディレクトリを指定すると失敗する。
- **フォアグラウンドの対話ターミナルで実行する。** エージェントシェルから `nohup` でバックグラウンド起動すると、親シェル終了後に最初のカメラ接続直後で落ちる（ログに rerun の `h2 protocol error` のみ、Python traceback なし）。バックグラウンドが必要な場合は `start_new_session=True` や `setsid` でセッションを切り離す。
- 対話ターミナルが無い／pynput が無いとキーボード（Right / Left / Esc）は無効で、タイマー駆動のみになる。音声キュー（`Recording episode N` / `Reset the environment` / `Stop recording`）に従う（Mac のサウンドを ON）。
- ハングした実行はシリアルポートを占有したまま残ることがある。再実行前に `pkill -f lerobot-record` し、`lsof` で両 `/dev/tty.usbmodem*` が空いていることを確認。余った Rerun ウィンドウも閉じる。
- dataset v3.0 ではカメラごとに動画が連結され、`videos/observation.images.<cam>/chunk-000/file-000.mp4` に格納される。
- 画角（trial3 先頭フレーム確認）: wrist はスポンジ・紙・グリッパが写る。**top（C920）はスポンジと紙のみでグリッパが画外**だった。収録前チェック (a)(b) で C920 を少し下げて後ろへ／下向きに傾け、グリッパ作業域が入ることを確認してから収録する。
- `objc: Class AVFFrameReceiver is implemented in both ... cv2 ... and /opt/homebrew ... ffmpeg` は無害な警告（このログが出ても収録は成功する）。

## シャットダウン

1. テレオペ等のコマンドを止める（Ctrl+C）。Follower を手で支える。
2. **12V / 5V アダプタを抜く**（先に DC、その後 USB）。
3. 運搬時は基部を持つ。ケーブルを持って吊らない。

## 次のステップ

sim チェックポイントを実機へ直接載せない。sim ポリシーは関節が**ラジアン**、実機 Follower は本体関節が**度**・グリッパが **0–100** であり、入出力契約が一致しない。

1. **デモ収録の本格化:** 画角・レイアウト固定後にエピソード数を増やす（上記試行コマンドを拡充）
2. **学習:** `lerobot-train` で ACT、`--policy.device=mps`（実機データ）。sim データは `python -m port_pick_align.training.train_act --preset sim`
3. **Phase 2-2（sim→実機）:** 単位変換ラッパーで dry-run → 低速 live。手順は **[sim_to_real_act.md](sim_to_real_act.md)**
4. **実機学習ポリシー（ACT / SmolVLA）:** 単位変換不要。dry-run → live は **[real_robot_deploy.md](real_robot_deploy.md)**（`scripts/run_act_real.sh` / `scripts/run_smolvla_real.sh`）。代替として `lerobot-rollout` も可。初回は `--max-relative-target` / `--max-delta-deg` を小さめに、低速・短時間で行う

### Phase 2-2 クイックリンク（詳細は sim_to_real_act.md）

```bash
# Dry-run（モータ非駆動）— 必ず先にこれ
python -m port_pick_align.deploy.run_sim_policy_on_real \
  --checkpoint "$HOME/work/lerobot-hw/outputs/sim_act/best_model.pt" \
  --port "$PORT_FOLLOWER" \
  --dry-run \
  --device mps \
  --episode-time-s 20

# Live（12V スイッチに手を置く。初回は max-delta を小さめに）
python -m port_pick_align.deploy.run_sim_policy_on_real \
  --checkpoint "$HOME/work/lerobot-hw/outputs/sim_act/best_model.pt" \
  --port "$PORT_FOLLOWER" \
  --device mps \
  --episode-time-s 20 \
  --max-delta-deg 3 \
  --robot-max-relative-target 3
```

### 実機学習ポリシー（推奨: リポジトリのランナー）

詳細・安全設定・推奨 live フラグは **[real_robot_deploy.md](real_robot_deploy.md)**。

```bash
# ACT（実機 train_act チェックポイント、単位変換なし）— 既定は dry-run
./scripts/run_act_real.sh --device mps --episode-time-s 15
# 初回 live 例
./scripts/run_act_real.sh --live --device mps \
  --max-delta-deg 2 --max-delta-gripper 3 --n-action-steps 10 --episode-time-s 15

# SmolVLA fine-tune
./scripts/run_smolvla_real.sh --live --device mps --n-action-steps 25 --episode-time-s 15
```

### 代替: lerobot-rollout（単位変換不要）

```bash
lerobot-rollout \
  --strategy.type=base \
  --policy.path=outputs/train/act_so101_real/checkpoints/last/pretrained_model \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}" \
  --robot.max_relative_target=5 \
  --task="Pick up the yellow sponge and place it on the white paper" \
  --duration=30
```

## トラブルシューティング

| 症状 | 対処 |
| --- | --- |
| ポートが出ない / 変わらない | データ通信対応 USB-C か確認。ハブを外して直結。`ls /dev/tty.usbmodem*` |
| ポート取り違え（グリッパ腕が Leader 動作） | `lerobot-find-port` を 1 台ずつやり直し、再キャリブレーション |
| `Permission denied` / `Resource busy` | `lsof` でポート占有プロセスを終了 |
| `Missing motor IDs` | `scan_port`、12V/5V、3 ピン配線、ポート取り違えを確認 |
| テレオペは動くが Follower が動かない | 12V アダプタ ON（LED 点灯）を確認 |
| `same min and max`（キャリブ） | 対象アームだけを動かす。中央姿勢から各関節を端まで動かす |
| テレオペ開始時に急動 | 開始前に姿勢をそろえる。`max_relative_target` を付ける |
| カメラ index がずれる / 内蔵だけ見える | Continuity Camera をオフ。`lerobot-find-cameras opencv` と `outputs/captured_images/opencv_*.png` で確認（ffmpeg 番号は使わない） |
| `not authorized to capture video` | macOS のカメラ許可 → ターミナル再起動 → `lerobot-find-cameras opencv` |
| `--display_data` で rerun エラー | `pip install 'lerobot[viz]==0.6.1'` |
| `lerobot-record` の import エラー | `pip install 'lerobot[dataset]==0.6.1'` |
| `--dataset.root=~/...` が失敗 | `~` は展開されない。`$HOME` または絶対パスを使う。既存 root は使わず新しい `<name>` にする |
| `lerobot-record` が数秒で死ぬ（`h2 protocol error` のみ） | 親シェル終了による切断。フォアグラウンド対話ターミナルで実行するか、`setsid` / `start_new_session=True` で切り離す |
| 再実行時にポート busy | `pkill -f lerobot-record` → `lsof` で両 usbmodem が空いていることを確認。Rerun ウィンドウを閉じる |
| `AVFFrameReceiver is implemented in both ...` | 無害。収録成功時も出ることがある |
| 赤 LED が DC 未接続でも点灯 | USB 給電によるもので正常。駆動には正しい DC アダプタが必要 |
| Follower がカメラスタンドに当たる | ポールを基部から約 35 cm 以上離す。紙はポール反対側。テープで印 |

## 参照

- [hardware.md](hardware.md) — 購入機材・作業エリア寸法
- [sim_to_real_act.md](sim_to_real_act.md) — Phase 2-2: sim ACT → 実機 Follower（変換ラッパー）
- [real_robot_deploy.md](real_robot_deploy.md) — 実機学習 ACT / SmolVLA の dry-run → live
- [units.md](units.md) — ラジアン / 度 / グリッパ 0–100
- [plan_b.md](plan_b.md) — 実機障害時の縮退
- [LeRobot SO-101](https://huggingface.co/docs/lerobot/so101)
- [LeRobot Cameras](https://huggingface.co/docs/lerobot/cameras)
- [Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots)
