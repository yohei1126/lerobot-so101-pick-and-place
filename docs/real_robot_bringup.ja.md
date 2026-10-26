# SO-101 実機 Bring-up とテレオペ収録手順（Mac / LeRobot 0.6.1）

本手順は、WowRobo 組立済み SO-101（Leader / Follower）を Mac 上の LeRobot 0.6.1 で駆動し、テレオペ・カメラ付きデモ収録まで行うための実務手順である。機材一覧・作業エリアの契約寸法は [hardware.md](hardware.ja.md) を正とする。一次情報は [SO-101](https://huggingface.co/docs/lerobot/so101)、[Cameras](https://huggingface.co/docs/lerobot/cameras)、[実機での模倣学習](https://huggingface.co/docs/lerobot/il_robots) である。

反映した実測:

- 2026-10-17/18 の bring-up（UGREEN ハブ経由の接続・両カメラ同時配信・テレオペ・`lerobot-record` 試行）
- **2026-10-22 / 23** の本収録（テーブル寸法、画角、キーボード操作、モータ温度、クリーンセット作成）
- **2026-10-27** の配置収録。既定 root は `so101_pick_sponge_layout20261026_20261027`。`so101_pick_sponge_main_20261020` はアーカイブ

収録データセットの要約は [real_dataset_so101_pick_sponge_main_20261023.md](real_dataset_so101_pick_sponge_main_20261023.ja.md)。sim→実機の単位変換は [sim_to_real_act.md](sim_to_real_act.ja.md) / [units.md](units.ja.md)。

## 前提と環境

実機用の仮想環境は**本リポジトリの `.venv` とは分離**する（学習ジョブや sim 依存と干渉させない）。

```bash
# 例: 専用ディレクトリに venv を作成
python3.12 -m venv "$HOME/work/lerobot-hw/.venv"
source "$HOME/work/lerobot-hw/.venv/bin/activate"
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

ドキュメントでは `~` ではなく `$HOME` を使う（`--dataset.root=` 直後の `~` は展開されない）。

## ハードウェア（2026-10-22 時点）

| 項目 | 内容 |
| --- | --- |
| ホスト | MacBook Pro M4。USB-C ハブ経由でアーム・カメラを接続 |
| Leader | ハンドル付き・**グリッパなし**。電源 **5V**。ポート例 `/dev/tty.usbmodem5B790143611` |
| Follower | **グリッパ付き**。電源 **12V**。ポート例 `/dev/tty.usbmodem5B8E1163071` |
| 固定 | 両アーム基部を C クランプでテーブル縁に固定 |
| 上カメラ | Logitech C920。VIJIM LS08 カメラアームに取り付け、テーブル縁にクランプ |
| 手首カメラ | キット同梱 USB2.0_CAM1（Follower グリッパ側） |

**アダプタの取り違えは厳禁。** 挿す前にラベルの電圧と基板側を指差し確認する。DC を外しても基板の赤 LED が点灯することがある（USB 給電）。駆動トルクには DC アダプタが必要である。Follower の 12V は必ず ON（LED 点灯）。2026-10-18 実測: Follower 約 12.6 V / Leader 約 5.5 V。

**ポートは抜き差し後に変わることがある。** 作業前に `ls /dev/tty.usbmodem*` と `lerobot-find-port` で再確認する。

### カメラ index（OpenCV / LeRobot）

| カメラ | OpenCV index（2026-10-18 / 22 の典型） | 解像度 / fps |
| --- | ---: | --- |
| wrist（USB2.0_CAM1） | 0 | 640×480 / 30 |
| top（C920） | 1 | 640×480 / 30 |

**index も抜き差し後にずれることがある。** `lerobot-find-cameras opencv` と `outputs/captured_images/opencv_*.png` で確認する（ffmpeg / avfoundation の番号は OpenCV と異なる）。

Rerun 表示時のエンティティ名は `observation.top` と `observation.wrist` である。

## 安全

- テレオペ開始時、Follower は Leader 姿勢へ一気に動く。開始前に両腕の姿勢をそろえる。
- 終了（Ctrl+C）でトルクが切れる（`disable_torque_on_disconnect`）。重力で落ちることがある。終了前に手で Follower を支える。
- 非常時はまず Follower の **12V プラグを抜く**。電源プラグにすぐ手が届く位置で作業する。
- **カメラスタンドは Follower の可動範囲外**（基部からおよそ 35 cm 以上）。テレオペ中にスタンドへ接触した実績あり。

## テーブル配置（実測 2026-10-22）

すべてテーブルの**左端からの距離**。テーブル幅はおよそ **134 cm**。スポンジは Follower 基部とのクリアランス確保のため前方へ寄せた。紙・スポンジ位置はマスキングテープで印を付けることを推奨する。

| 対象 | 左端から | 手前縁から（該当時） |
| --- | ---: | ---: |
| Leader アーム左端 | 28 cm | — |
| 白い紙（縦置き） | 56 cm | 13 cm |
| Follower アーム左端 | 78 cm | — |
| 黄色いスポンジ | 81 cm | 29 cm |
| 上カメラポール | 111 cm（右端から 23 cm） | — |

上面図（左端 = 0 cm、手前が下）:

```text
左端 0 cm                                              右端 ~134 cm
+------------------------------------------------------------------+
|                                                                  |
|   Leader          紙(白)         Follower      スポンジ(黄)   C920 |
|   28cm            56cm /13cm前    78cm          81cm /29cm前  111cm|
|     [====]         [紙]            [====]         [スポ]      |pole|
|                                                                  |
|                         （手前縁）                                |
+------------------------------------------------------------------+
```

座標系（sim / [hardware.md](hardware.ja.md) と同じ）: 原点は Follower 基部中心、+x 前方、+y 左、+z 上。可動範囲（基部から半径およそ 45 cm）に障害物・液体を置かない。

## 上カメラ画角

top には次がすべて写っていること:

1. 白い紙
2. 黄色いスポンジ
3. Follower 基部およびグリッパの作業経路

以前の画角は寄りすぎで、グリッパ経路が欠けた。収録前に Rerun（`observation.top` / `observation.wrist`）で確認する。C920 が狭い場合は少し下げて後ろへ／下向きに傾ける。

## USB とポート識別

```bash
source "$HOME/work/lerobot-hw/.venv/bin/activate"
# 両アームに USB と電源を接続した状態で実行
lerobot-find-port
# プロンプトが出たら、識別したいアームの USB を 1 本だけ抜き、Enter
# 表示されたポートを記録し、USB を挿し直す。もう一方も同様（1 台ずつ）
```

| アーム | ポート（2026-10-18 / 22 の記録） | 電源 | id |
| --- | --- | --- | --- |
| Leader | `/dev/tty.usbmodem5B790143611` | 5V | leader |
| Follower | `/dev/tty.usbmodem5B8E1163071` | 12V | follower |

```bash
export PORT_FOLLOWER=/dev/tty.usbmodem5B8E1163071
export PORT_LEADER=/dev/tty.usbmodem5B790143611
```

**初回 bring-up では Leader / Follower のポートを取り違え、テレオペ時にグリッパ付きアームが Leader 側として動いた。** その場合はポートを再識別し、キャリブレーションをやり直す。

## モーター ID の確認

WowRobo 組立済みキットでは、STS3215 の ID 1–6 とボーレート 1,000,000 が既設定であることが多い。書き込み前にポート走査で確認し、正しければ `lerobot-setup-motors` はスキップする。

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

任意で `--robot.max_relative_target=10`（度単位の 1 ステップ上限）や `--teleop_time_s=60` を付けてよい。終了前に Follower を手で支える。

確認: 各関節が同じ方向に追従する、グリッパが開閉する、異音・振動がない。

### カメラ表示つき

```bash
lerobot-find-cameras opencv
# 画像は outputs/captured_images/opencv_*.png。index は抜き差しで変わりうる
```

macOS では初回にカメラ権限が必要（システム設定 → プライバシーとセキュリティ → カメラ）。**iPhone Continuity Camera が index を奪う**ことがある。Disconnect し、必要なら Continuity Camera をオフにする。

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader \
  --display_data=true
```

## 収録前チェック（必須）

**毎回 `lerobot-record` の直前に実施する。**

1. **稼働中の `lerobot-teleoperate` を止める。** カメラとシリアルの競合が起きる。
2. 同じ robot / teleop / cameras フラグで短時間テレオペし、Rerun で確認する。
3. 確認後にテレオペを止め、収録へ進む。

| # | 確認項目 |
| --- | --- |
| (a) | **top:** 紙・スポンジ・Follower 基部／グリッパ経路が画角に入る |
| (b) | **wrist:** 接近時にグリッパ先端とスポンジが見える |
| (c) | pick-and-place 全経路でスタンド／クランプに当たらない |
| (d) | カメラ警告なし。ループが安定して回る |
| (e) | スポンジと紙がテープ印の開始位置にある |

## デモ収録ルール（2026-10-22/23 で確定）

- **1 エピソード = 1 回の pick-and-place。** 以前、1 エピソードに 2 回置いた試行は破棄した。
- 開始と終了を**同じ休止姿勢**にする。
- スポンジを紙に置いたら **Right 矢印**でエピソードを早めに終了する（`episode_time_s=25` の末尾 およそ 10–17 秒は腕が静止していた）。
- ゆっくり・一貫した動きで行う。
- **およそ 10 エピソードごとに休憩**し、Follower の電源を切ってモータを冷やす。およそ 20 エピソード連続後、Follower の `shoulder_lift` が指令に遅れ、mean `|action-state|` がおよそ **10–12°** まで上がった（通常はおよそ **1.5°**）。

## 収録スクリプト

リポジトリの `scripts/record_real_so101.sh` を使う（実行権限付き）。

```bash
# N エピソードを追加。データセットが既にあれば自動で resume
scripts/record_real_so101.sh [N]
```

| 項目 | 値 |
| --- | --- |
| 既定 N | 50 |
| データセット root | `$HOME/work/lerobot-hw/datasets/so101_pick_sponge_layout20261026_20261027` |
| repo_id | `yohei1126/so101_pick_sponge_layout20261026` |
| タスク文 | `Pick up the yellow sponge and place it on the white paper` |
| episode / reset | 25 s / 10 s、fps 30 |
| ログ | `$HOME/work/lerobot-hw/outputs/record_main_*.log`（cwd は `lerobot-hw`） |

2026-10-26 のテーブル配置（Issue #90）で録るデモの既定 root は上のパスである。`so101_pick_sponge_main_20261020` はアーカイブで、2026-10-22 配置の収録に、2026-10-27 05:04–05:11 SGT の 10 本（当時の episode 32–41）が追記された混合セットである。スクリプトは `ROOT` がそのディレクトリに解決されると終了する。別セットを始めるときだけ `ROOT` で別パスを渡す。

2026-10-27 の 10 本は LeRobot 0.6.1 の `lerobot-edit-dataset --operation.type delete_episodes` で切り出し、新 root の episode 0–9（7,369 frames）になっている。動画は元の `chunk-000/file-003` のバイトコピーである。そのシャードにはこの 10 本だけが入っていたので、再エンコードはしていない。元の `20261020` ツリーは変更していない。

スクリプトは開始前に `lerobot-teleoperate` を `pkill` する。ポートとカメラ index はスクリプト内にハードコードされている。抜き差し後は編集するか、環境に合わせて上書きする。

### 対話ターミナルで実行する（必須）

キーボード操作:

| キー | 意味 |
| --- | --- |
| Right | 現在エピソードを終了して次へ |
| Left | 撮り直し |
| Esc | 収録停止 |

**バックグラウンド／非対話起動ではキーボードが効かない。** macOS の対話 Terminal で実行する。Terminal にアクセシビリティおよび入力監視の権限が必要な場合がある。

バックグラウンドが必要な場合は `nohup` ではなく**新しいセッション**で切り離す（`start_new_session` / `setsid`）。`nohup` ジョブは親終了後に落ちた実績がある。

### 音声キュー

`--play_sounds` は macOS の**デフォルト出力デバイス**へ出る。作業用 Mac では Bluetooth の Jabra ヘッドセットがデフォルトだった。収録前に出力デバイスを確認する。

## 手動の `lerobot-record` 例

スクリプトと同等のフラグ:

```bash
source "$HOME/work/lerobot-hw/.venv/bin/activate"
cd "$HOME/work/lerobot-hw"

lerobot-record \
  --robot.type=so101_follower \
  --robot.port=$PORT_FOLLOWER \
  --robot.id=follower \
  --robot.cameras="{ top: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30} }" \
  --teleop.type=so101_leader \
  --teleop.port=$PORT_LEADER \
  --teleop.id=leader \
  --dataset.repo_id=yohei1126/so101_pick_sponge_layout20261026 \
  --dataset.single_task='Pick up the yellow sponge and place it on the white paper' \
  --dataset.num_episodes=10 \
  --dataset.episode_time_s=25 \
  --dataset.reset_time_s=10 \
  --dataset.fps=30 \
  --dataset.no_stamp=true \
  --dataset.push_to_hub=false \
  --dataset.root=$HOME/work/lerobot-hw/datasets/so101_pick_sponge_layout20261026_20261027 \
  --display_data=true \
  --play_sounds=true \
  --resume=true
```

- 既存 root への追記は `--resume=true`（スクリプトは root が存在すれば自動で true）。上の例の root には切り出した 10 本が既にあるので、追記は resume である。
- dataset v3.0 ではカメラごとに動画が連結され、`videos/observation.images.<cam>/chunk-000/file-000.mp4` に格納される。
- データセット本体は git 外（Mac 上）に置く。

## シャットダウン

1. テレオペ／収録を止める（Ctrl+C または Esc）。Follower を手で支える。
2. **12V / 5V アダプタを抜く**（先に DC、その後 USB）。
3. 運搬時は基部を持つ。ケーブルを持って吊らない。

## 次のステップ

sim チェックポイントを実機へ直接載せない。sim ポリシーは関節が**ラジアン**、実機 Follower は本体関節が**度**・グリッパが **0–100** であり、入出力契約が一致しない。

1. デモ収録 → クリーンセット作成（[real_dataset_so101_pick_sponge_main_20261023.md](real_dataset_so101_pick_sponge_main_20261023.ja.md)）
2. 実機データで ACT 学習: `python -m port_pick_align.training.train_act`（[training.md](training.ja.md)）。MPS 上で実行する。sim データは `train_act --preset sim`
3. Phase 2-2（sim→実機）: 単位変換ラッパーで dry-run → 低速 live。[sim_to_real_act.md](sim_to_real_act.ja.md)
4. 実機学習ポリシー（ACT / SmolVLA）: 単位変換不要。dry-run → live は **[real_robot_deploy.md](real_robot_deploy.ja.md)**（`scripts/run_act_real.sh` / `scripts/run_smolvla_real.sh`）。代替として `lerobot-rollout` も可。初回は `--max-relative-target` / `--max-delta-deg` を小さめに、低速・短時間で行う

### Phase 2-2 クイックリンク（詳細は sim_to_real_act.md）

```bash
# Dry-run（モータ非駆動）; 必ず先にこれ
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

詳細・安全設定・推奨 live フラグは **[real_robot_deploy.md](real_robot_deploy.ja.md)**。

```bash
# ACT（実機 train_act チェックポイント、単位変換なし）; 既定は dry-run
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
| ポートが出ない / 変わる | データ通信対応 USB-C か確認。ハブを外して直結。`ls /dev/tty.usbmodem*`。抜き差し後は再識別 |
| ポート取り違え（グリッパ腕が Leader 動作） | `lerobot-find-port` を 1 台ずつやり直し、再キャリブレーション |
| `Permission denied` / `Resource busy` | `lsof` でポート占有プロセスを終了。収録前に `lerobot-teleoperate` を止める |
| `Missing motor IDs` | `scan_port`、12V/5V、3 ピン配線、ポート取り違えを確認 |
| テレオペは動くが Follower が動かない | 12V アダプタ ON（LED 点灯）を確認 |
| top カメラが開かない／タイムアウト | 直前のプロセス解放直後に起きうる。**再試行**で直ることが多い |
| キーボード（Right / Left / Esc）が効かない | 対話 Terminal で実行。macOS のアクセシビリティ／入力監視を許可 |
| 音声キューが聞こえない | macOS のデフォルト出力デバイスを確認（Bluetooth ヘッドセット等） |
| `nohup` の収録が死ぬ | 新しいセッションで切り離す（`start_new_session` / `setsid`）。対話 Terminal が本線 |
| torchcodec が FFmpeg dylib 不足で失敗 | LeRobot は **pyav にフォールバック**する。長いエラーは無害 |
| `AVFFrameReceiver is implemented in both ...` | 無害。収録成功時も出ることがある |
| `shoulder_lift` の追従遅れ（mean \|action-state\| ≈ 10–12°） | 連続収録を止め、Follower 電源を切って冷却。およそ 10 epi ごとに休憩 |
| カメラ index がずれる / 内蔵だけ見える | Continuity Camera をオフ。`lerobot-find-cameras opencv` と保存画像で確認 |
| `--display_data` で rerun エラー | `pip install 'lerobot[viz]==0.6.1'` |
| `lerobot-record` の import エラー | `pip install 'lerobot[dataset]==0.6.1'` |
| `--dataset.root=~/...` が失敗 | `~` は展開されない。`$HOME` または絶対パスを使う |
| Follower がカメラスタンドに当たる | ポールを基部から約 35 cm 以上離す。紙はポール反対側。テープで印 |

## 参照

- [hardware.md](hardware.ja.md): 購入機材・作業エリア寸法
- [real_dataset_so101_pick_sponge_main_20261023.md](real_dataset_so101_pick_sponge_main_20261023.ja.md): clean28 データセット要約
- [sim_to_real_act.md](sim_to_real_act.ja.md): Phase 2-2: sim ACT → 実機 Follower（変換ラッパー）
- [real_robot_deploy.md](real_robot_deploy.ja.md): 実機学習 ACT / SmolVLA の dry-run → live
- [units.md](units.ja.md): ラジアン / 度 / グリッパ 0–100
- [training.md](training.ja.md): ACT 学習
- [plan_b.md](plan_b.ja.md): 実機障害時の縮退
- [LeRobot SO-101](https://huggingface.co/docs/lerobot/so101)
- [LeRobot Cameras](https://huggingface.co/docs/lerobot/cameras)
- [Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots)
