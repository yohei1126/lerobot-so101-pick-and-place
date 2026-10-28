# SO-101 実機 Bring-up とテレオペ収録手順（Mac / LeRobot 0.6.1）

本手順は、WowRobo 組立済み SO-101（Leader / Follower）を Mac 上の LeRobot 0.6.1 で駆動し、テレオペ・カメラ付きデモ収録まで行うための実務手順である。機材一覧・作業エリアの契約寸法は [hardware.md](hardware.ja.md) を正とする。一次情報は [SO-101](https://huggingface.co/docs/lerobot/so101)、[Cameras](https://huggingface.co/docs/lerobot/cameras)、[実機での模倣学習](https://huggingface.co/docs/lerobot/il_robots) である。

反映した実測:

- 2026-10-17/18 の bring-up（UGREEN ハブ経由の接続・両カメラ同時配信・テレオペ・`lerobot-record` 試行）
- **2026-10-22 / 23** の本収録（当時のテーブル寸法、画角、キーボード操作、モータ温度、クリーンセット作成）。そのテーブルは廃止。[廃止した配置](#廃止した配置) を参照
- **新しい bring-up と live eval の現行テーブルは 2026-10-26**（Issue #90）。[現行テーブル配置](#現行テーブル配置2026-10-26) を参照
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
| 上カメラ | Logitech C920。VIJIM LS08。現行の固定はテーブル右端、手前から 16 cm。[現行テーブル配置](#現行テーブル配置2026-10-26) |
| 手首カメラ | キット同梱 USB2.0_CAM1（Follower グリッパ側） |

**アダプタの取り違えは厳禁。** 挿す前にラベルの電圧と基板側を指差し確認する。DC を外しても基板の赤 LED が点灯することがある（USB 給電）。駆動トルクには DC アダプタが必要である。Follower の 12V は必ず ON（LED 点灯）。2026-10-18 実測: Follower 約 12.6 V / Leader 約 5.5 V。

**ポートは抜き差し後に変わることがある。** 作業前に `ls /dev/tty.usbmodem*` と `lerobot-find-port` で再確認する。

### カメラ index（OpenCV / LeRobot）

| カメラ | OpenCV index | 解像度 / fps |
| --- | ---: | --- |
| wrist（USB2.0_CAM1、Follower グリッパ） | 0 | 640×480 / 30 |
| top（C920） | 1 | 640×480 / 30 |

この index は 2026-10-25 のケーブル交換後のもので、2026-10-26 も同じである（2026-10-18 / 22 の番号とも一致）。

**index も抜き差し後にずれることがある。** `lerobot-find-cameras opencv` と `outputs/captured_images/opencv_*.png` で確認する（ffmpeg / avfoundation の番号は OpenCV と異なる）。

Rerun 表示時のエンティティ名は `observation.top` と `observation.wrist` である。

## 安全

- テレオペ開始時、Follower は Leader 姿勢へ一気に動く。開始前に両腕の姿勢をそろえる。
- 終了（Ctrl+C）でトルクが切れる（`disable_torque_on_disconnect`）。重力で落ちることがある。終了前に手で Follower を支える。
- 非常時はまず Follower の **12V プラグを抜く**。電源プラグにすぐ手が届く位置で作業する。
- **カメラスタンドは Follower の可動範囲外。** C920 はテーブル右端、手前から 16 cm（2026-10-26）。2026-10-22 のポール（幅およそ 134 cm のテーブルで右端から約 23 cm）は廃止。テレオペ中にスタンドへ接触した実績あり。

## 現行テーブル配置（2026-10-26）

新しい bring-up、新しい収録、実機 live eval の正である。2026-10-26 ~00:36 SGT、上カメラを動かしてスポンジ・紙・Follower が写るようにしたあとの実測。2026-10-25 ~23:28 と 2026-10-22 を置き換える。数値は [hardware.md](hardware.ja.md#現行テーブル配置2026-10-26) と同じ。定数は `port_pick_align.simulation.table_layout`。

テーブル: 幅 **140 cm** × 奥行 **70 cm**。紙とスポンジはテープで印を付ける。古い図に合わせるためにハードウェアを動かさない。

| 対象 | 配置 | 備考 |
| --- | --- | --- |
| Leader 基部 | 左から 27 cm / 右から 101 cm | 5V。基部の両端 |
| Follower 基部 | 左から約 68 cm / 右から 61 cm | 12V。左からの距離は概数 |
| 上カメラ（C920） | テーブル**右端**、**手前から 16 cm** | 紙・スポンジ・Follower が写る向き |
| 紙（ゴール） | 右から 69 cm、手前から 27 cm | 縦置き 幅 20 cm × 奥行 30 cm |
| スポンジ | 右から 54 cm、手前から 44 cm | 縦置き 幅 6 cm × 奥行 11 cm |
| 手首カメラ | Follower のグリッパ | OpenCV **0** |
| 上カメラ index | OpenCV **1** | 2026-10-25 のケーブル交換後も同じ |

上面図（手前縁が下）:

```text
奥（手前から 70 cm）
+------------------------------------------------------------------------------+
|                          スポンジ 6×11 縦置き                                |
|                          右から 54 cm、手前から 44 cm                        |
|                                                                              |
|  Leader 基部              紙 20×30 縦置き                 Follower 基部      |
|  左から 27 cm             右から 69 cm                    左から約 68 cm     |
|  右から 101 cm            手前から 27 cm                  右から 61 cm       |
|  5V                                                                  C920    |
|                                                                      右端    |
|                                                                      手前    |
|                                                                      16 cm   |
+------------------------------------------------------------------------------+
手前縁（0）                                                              140 cm
左 0
```

### sim 座標系への写像

原点は Follower 基部の**中点**を手前縁に置いた点。+x は前方（テーブル奥へ）、+y は左。中点は、左から約 68 cm と右から 61 cm が示す区間の中央（左から 68 cm 〜 79 cm、中点 73.5 cm）。基部の手前オフセットは再計測していないので、原点は手前縁上である。紙・スポンジ・カメラの座標は実測点である（記録は点が角であるとは書いていない）。

| 対象 | sim `(x, y)` cm | sim `(x, y)` m |
| --- | --- | --- |
| Leader 中点 | (0, 40.5) | (0, 0.405) |
| Follower 原点 | (0, 0) | (0, 0) |
| 紙 | (27, 2.5) | (0.27, 0.025) |
| スポンジ | (44, −12.5) | (0.44, −0.125) |
| 上カメラ | (16, −66.5) | (0.16, −0.665) |

MuJoCo の `so101_tabletop.xml` は廃止した簡易シーンのままである（箱 `(0.28, -0.08)` m、ゴール `(0.35, 0.12)` m、真下カメラ `(0.25, 0, 1.05)` m）。これらの geom はこのテーブルではない。Follower まわりの可動範囲に障害物・液体を置かない。

![現行テーブル配置](images/so101_layout_guide.png)

## 実機 live-eval チェックリスト

`scripts/run_act_real.sh --live`、`scripts/run_smolvla_real.sh --live`、または `lerobot-rollout` の前に実施する。デプロイのフラグは [real_robot_deploy.md](real_robot_deploy.ja.md)。採点、trim、学習後の live 評価プロトコルは [real_eval_protocol.ja.md](real_eval_protocol.ja.md)。

| # | 確認 |
| --- | --- |
| 1 | テーブルは **140 × 70 cm**。2026-10-22（約 134 cm）と 2026-10-25 ~23:28（140×69、C920 は右から 28 cm）は使わない |
| 2 | Leader 基部は左から 27 cm / 右から 101 cm（5V）。Follower 基部は左から約 68 cm / 右から 61 cm（12V） |
| 3 | 紙は右から 69 cm、手前から 27 cm（縦置き 20×30 cm） |
| 4 | スポンジは右から 54 cm、手前から 44 cm（縦置き 6×11 cm） |
| 5 | C920 は**右端**、**手前から 16 cm**。紙・スポンジ・Follower が写る向き |
| 6 | 手首カメラは Follower のグリッパ。OpenCV **wrist = 0**、**top = 1**。抜き差し後は `scripts/preflight_real_so101.sh` と `lerobot-find-cameras opencv` で再確認 |
| 7 | Rerun: `observation.top` に紙・スポンジ・Follower、`observation.wrist` に接近時のグリッパ先端とスポンジ |
| 8 | 先に dry-run。トルクオフの前に Follower を手で支える。12V プラグに手が届くこと |

## 上カメラ画角

top には次がすべて写っていること:

1. 白い紙
2. 黄色いスポンジ
3. Follower 基部およびグリッパの作業経路

2026-10-26 の設置は、その画角のために C920 を右端、手前から 16 cm に置いている。収録または live eval の前に Rerun（`observation.top` / `observation.wrist`）で確認する。2026-10-22 のポールや、2026-10-25 の位置（右から 28 cm）へ戻さない。

## 廃止した配置

新しいセッションをここから組まない。

### 2026-10-25 ~23:28

テーブル 140×69 cm。C920 は右から 28 cm。スポンジは右から 70 cm / 手前から 45 cm。紙は右から 82 cm / 手前から 26 cm。Follower は右から 62 cm。

### 2026-10-22（本収録テレオペのみ）

下の距離は**左端から**。テーブル幅はおよそ **134 cm**。スポンジは Follower 基部とのクリアランスのため前方へ寄せてあった。clean28 データセットはこの配置で収録した。それらのエピソードを 2026-10-26 のテーブルとして書き換えない。

| 対象 | 左端から | 手前縁から（該当時） |
| --- | ---: | ---: |
| Leader アーム左端 | 28 cm | — |
| 白い紙（縦置き） | 56 cm | 13 cm |
| Follower アーム左端 | 78 cm | — |
| 黄色いスポンジ | 81 cm | 29 cm |
| 上カメラポール | 111 cm（右端から 23 cm） | — |

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

廃止した図（簡易 MuJoCo シーン。2026-10-22 のテープ位置そのものではない）: [so101_layout_guide_superseded_pre_20261026.png](images/so101_layout_guide_superseded_pre_20261026.png)。

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

**毎回 `lerobot-record` の直前に実施する。** ポート、カメラ index、テープ位置は上の節で定義する。この表がセッション開始の確認項目である。

デバイスの有無は `scripts/preflight_real_so101.sh` で確認する。テレオペまたは収録の前に実行する。読み取り専用であり、モーターバスは開かず、アームは動かさず、データセットも書かない。Leader port、Follower port、wrist cam、top cam のそれぞれが `PASS` または `FAIL` を出し、最後に `RESULT PASS` または `RESULT FAIL` を出す。ハードな失敗は非ゼロで終了する。`RESULT FAIL` のあとにはテレオペも `lerobot-record` も始めない。

この事前チェックはシリアルノードの存在と、各カメラインデックスが開けることだけを見る。画角は判定しない。下の 6 は引き続き Rerun を見る。

```bash
scripts/preflight_real_so101.sh
```

既定値は `scripts/record_real_so101.sh` と同じである。

| 確認 | 既定 |
| --- | --- |
| Leader port（5V） | `/dev/tty.usbmodem5B790143611` |
| Follower port（12V） | `/dev/tty.usbmodem5B8E1163071` |
| wrist cam | OpenCV index **0** |
| top cam | OpenCV index **1** |

macOS は同じアダプタに `/dev/cu.usbmodem*` も作る。このリポジトリの LeRobot コマンドは `tty` ノードを使う。抜き差しでノードが動いたときは `PORT_LEADER`、`PORT_FOLLOWER`、`WRIST_INDEX`、`TOP_INDEX` で上書きする。venv は `$LEROBOT_HW_ROOT/.venv`（`LEROBOT_HW` も可。既定は `$HOME/work/lerobot-hw`）で、`scripts/run_act_real.sh` と同じである。

カメラ確認は、その venv の OpenCV で 1 フレーム取る。index は `lerobot-record` が使う値である。OpenCV が無いときは `system_profiler` と ffmpeg の `avfoundation` でカメラを列挙し、ffmpeg があれば 1 フレーム取る。avfoundation の番号は OpenCV の index ではない。Continuity Camera、iPhone カメラ、iPad カメラが列挙されたら失敗である。外して Continuity Camera をオフにする。カメラを初めて開くときは macOS のカメラ権限が要る（システム設定 → プライバシーとセキュリティ → カメラ）。

`PORT_*` と `*_INDEX` は事前チェックだけに効く。`scripts/record_real_so101.sh` のポートとカメラ index はハードコードのままである。抜き差しのあとは `ls /dev/tty.usbmodem*` の `tty` ノードに合わせてそのスクリプトを直す。事前チェックは他の `tty.usbmodem*` / `cu.usbmodem*` を表示するだけで、どれかを自動では選ばない。自動選択は Leader と Follower の取り違えになる。

| # | 確認項目 |
| --- | --- |
| 1 | テーブル配置は [現行の 2026-10-26 配置](#現行テーブル配置2026-10-26)（Issue #90）である。スポンジと紙はその節のテープ印にあり、2026-10-22 のテープ印ではない。この配置はアーカイブ `so101_pick_sponge_main_20261020` と混ぜない。 |
| 2 | Leader の電源は **5V**、Follower の電源は **12V** で、基板の LED が点灯している。アダプタはそれぞれのアームに付いたままである。 |
| 3 | `ls /dev/tty.usbmodem*` と `scripts/preflight_real_so101.sh` でポートを読み直した（`Leader port` と `Follower port` が `PASS`）。スクリプトの既定は Leader `/dev/tty.usbmodem5B790143611`、Follower `/dev/tty.usbmodem5B8E1163071`。抜き差しで変わったら `scripts/record_real_so101.sh` を直す。 |
| 4 | OpenCV index は wrist **0**、top **1** である。iPhone の Continuity Camera は切断し、オフにしてある。`scripts/preflight_real_so101.sh` の `wrist cam` と `top cam` が `PASS` である。画像は `lerobot-find-cameras opencv` で確認する。 |
| 5 | Leader と Follower は**同じ休止姿勢**から始める。テレオペ開始時に Follower が急に寄らない。 |
| 6 | 同じ robot / teleop / camera フラグで短時間テレオペし、Rerun（`observation.top` / `observation.wrist`）を見る。**top:** 紙・スポンジ・Follower 基部／グリッパ経路が画角に入る。**wrist:** 接近時にグリッパ先端とスポンジが見える。経路はスタンドとクランプに当たらない。カメラ警告はない。スポンジと紙は 2026-10-26 配置のテープ印の開始位置にある。 |
| 7 | 収録前に `lerobot-teleoperate` を止める。収録スクリプトも `pkill` する。残っているとカメラとシリアルを取り合う。 |
| 8 | `ROOT` は新しいデータセットディレクトリか、現在の配置 root（`so101_pick_sponge_layout20261026_20261027`、または `..._batch2` のような名前付きバッチ）への意図した resume である。`ROOT` が `so101_pick_sponge_main_20261020` に解決されるとスクリプトは終了する。 |
| 9 | `lerobot-record` の前に root を **mkdir しない**。`scripts/record_real_so101.sh` はディレクトリが存在するだけで `--resume=true` にする。空ディレクトリも同じである。初回のツリーは `lerobot-record` が作る。新しいバッチは、まだ存在しない `ROOT` を使う。 |
| 10 | シェルは対話 Terminal である。**Right** でエピソード終了、**Left** で撮り直し、**Esc** で停止。エピソード開始と同時に動かし始める。置き終わったら **Right** を押し、静止した末尾をデータセットに残さない。 |
| 11 | **およそ 10 エピソードごと**に休む。Follower の電源を切り、モータを冷やす。 |

## デモ収録ルール（2026-10-22/23 で確定）

- **1 エピソード = 1 回の pick-and-place。** 以前、1 エピソードに 2 回置いた試行は破棄した。
- 開始と終了を**同じ休止姿勢**にする。
- **エピソード開始と同時に動かし始める。** 初期姿勢を数秒保つ区間は後で先頭だけ切る。その待機だけではエピソードを捨てない。
- スポンジを紙に置いたら **Right 矢印**でエピソードを早めに終了する（`episode_time_s=25` の末尾 およそ 10–17 秒は腕が静止していた）。QC スクリプトはその末尾を採点しない。Right で終えると、その静止区間はデータセットに入らない。
- ゆっくり・一貫した動きで行う。
- **およそ 10 エピソードごとに休憩**し、Follower の電源を切ってモータを冷やす。およそ 20 エピソード連続後、Follower の `shoulder_lift` が指令に遅れ、mean `|action-state|` がおよそ **10–12°** まで上がった（通常はおよそ **1.5°**）。

## 収録スクリプト

リポジトリの `scripts/record_real_so101.sh` を使う（実行権限付き）。

```bash
# N エピソードを追加。データセットが既にあれば自動で resume
scripts/preflight_real_so101.sh
scripts/record_real_so101.sh [N]
```

収録の前に `scripts/preflight_real_so101.sh` が `RESULT PASS` を出す。

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

スクリプトの前に root を `mkdir` しない。空ディレクトリを含め、ディレクトリが既にあると `--resume=true` になり、そのパスへ追記する。初回のツリーは `lerobot-record` が作る。

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

## 収録後の QC

この節はテレオペ収録データの QC だけを扱う。閾値は `scripts/qc_teleop_dataset.py` のままである。学習後の実機 ACT 評価（オープンループ採点と live ロールアウト）は [実機評価プロトコル](real_eval_protocol.ja.md) を参照。

`scripts/qc_teleop_dataset.py` は、ローカルの LeRobot v3 root を 1 つ以上、エピソードごとに採点する。`LeRobotDataset` を作る前に `meta/info.json` があることを確認するので、無いパスは作られない。読み込みは `video_backend="pyav"` と `download_videos=False` で、列は `action`、`observation.state`、`episode_index` を使う。動画はデコードしない。アームへの指令は出さず、エピソードの結合・除外・切り詰めもしない。

実機用 venv（`$HOME/work/lerobot-hw/.venv`）を有効にする。`HF_HUB_OFFLINE=1` にすると読み込みはディスク上で完結する。

```bash
source "$HOME/work/lerobot-hw/.venv/bin/activate"
HF_HUB_OFFLINE=1 python scripts/qc_teleop_dataset.py \
  --root "$HOME/work/lerobot-hw/datasets/so101_pick_sponge_layout20261026_20261027" \
  --root "$HOME/work/lerobot-hw/datasets/so101_pick_sponge_layout20261026_20261027_batch2"
```

`--repo-id` は `--root` が 1 つのときだけ使える。既定は `info.json` の `repo_id` で、無ければ `local/<dirname>` である。`--fps` はデータセットの fps を上書きする。`--out` は stem、`.csv` / `.md` のパス、またはディレクトリである。`--format` は `csv`、`md`、`both`（既定 `both`）である。

### 測る量

腕関節は、名前に `gripper` を含まない action である。名前が `dim*` で 2 個以上あるときは `dim1` を `shoulder_lift` とする。標準偏差は母標準偏差（`np.std`、`ddof=0`）である。

| 量 | 定義 |
| --- | --- |
| 平均動作 | 腕関節の `action` について、フレーム間絶対差分の平均。単位は度/フレーム |
| 先頭アイドル | 腕関節の `\|action - action[0]\|` の最大が `--motion-eps-deg`（既定 **1.0**）に初めて達するフレーム番号。一度も離れなければ `idle_fr` はエピソード長 `T` で、`to_mot` は空。`idle_s = idle_fr / fps` |
| 遅れ | 関節ごとの mean `\|action - state\|`。グリッパを含む。`lag_sl` は常に `shoulder_lift`。`max_lag` は平均が最大の関節 |
| action 標準偏差 | 腕関節ごとの `action` の標準偏差。`LOW_MOTION` はその最大を使う |

### フラグ

比較の向きはスクリプトの実装と一致する。

| フラグ | 深刻度 | 条件 | ACT 学習の前 |
| --- | --- | --- | --- |
| `LOW_MOTION` | high | 腕関節の action 標準偏差の最大が `--low-motion-std-deg`（既定 **5**）**未満** | そのエピソードを外す。収録全体がほぼ静止している |
| `HIGH_LAG` | high | 全関節（グリッパを含む）の mean `\|action-state\|` の最大が `--high-lag-deg`（既定 **6**）**以上** | 外すか、再確認する。この機体で熱を持つ関節は通常 `shoulder_lift` である（健全時およそ 1.5–2°、長い連続収録でおよそ 10–12°）。フラグ自体は閾値に達した任意の関節に付く |
| `LONG_HEAD_IDLE` | warn | `idle_s` が `--head-idle-s`（既定 **2**）**より大きい**。ちょうど 2.0 秒では付かない | そのエピソードの `idle_fr` / `to_mot` を使い、先頭アイドルだけを軽く切る。待機だけでは捨てない。30 フレーム固定で切ると、3–4 秒の待機の大半が残る |

深刻度は、`LOW_MOTION` または `HIGH_LAG` があるとき `high`、フラグが `LONG_HEAD_IDLE` だけのとき `warn`、それ以外は `ok` である。`--strict` が終了コード 1 にするのは `high` だけである。warn だけの実行は 0 で終わる。`info.json` が無い、読み込みに失敗した、エピソードが 0 件、のいずれも 1 で終わる。

静止した末尾は収録時の規則である。置き終わったら Right を押す。スクリプトはその末尾を採点しない。

標準出力はエピソード 1 行と、最後の `episodes / high / warn / ok` である。`$HOME/work/lerobot-hw/outputs/` があるときは `qc_teleop_<UTC>.csv` と `.md` をそこへ書く。無いときは先頭の `--root` の隣へ書く。

### ACT 学習の前

スクリプトは報告だけをする。学習前の作業は手で行う。

1. 同じ配置のバッチを 1 つのクリーンな root にまとめる。
2. `HIGH_LAG` のエピソードを外すか再確認する。2026-10-27 では set 1 の episode 3（`shoulder_lift` の遅れ 8.92°）である。
3. 先頭アイドルを軽く切る。`LONG_HEAD_IDLE` のエピソードは残す。
4. この配置を `so101_pick_sponge_main_20261020` と混ぜない。

2026-10-27 の配置 QC（10 + 10 エピソード、7,369 + 7,373 フレーム）は Mac 上の `$HOME/work/lerobot-hw/outputs/qc_layout20261026_20261027.md` にある。

## 次のステップ

sim チェックポイントを実機へ直接載せない。sim ポリシーは関節が**ラジアン**、実機 Follower は本体関節が**度**・グリッパが **0–100** であり、入出力契約が一致しない。

1. デモ収録 → QC（前節、`scripts/qc_teleop_dataset.py`）→ クリーンセット作成（[real_dataset_so101_pick_sponge_main_20261023.md](real_dataset_so101_pick_sponge_main_20261023.ja.md)）
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
| 事前チェックが `RESULT FAIL` | `FAIL` の行を読む。そのポートかカメラを直し、Continuity Camera をオフにして `scripts/preflight_real_so101.sh` をやり直す。テレオペと収録は `RESULT PASS` を待ってから始める |
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
| Follower がカメラスタンドに当たる | C920 は右端、手前から 16 cm のままにする。廃止したポール位置へ戻さない。紙とスポンジはテープで印 |

## 参照

- [hardware.md](hardware.ja.md): 購入機材・作業エリア寸法
- [real_dataset_so101_pick_sponge_main_20261023.md](real_dataset_so101_pick_sponge_main_20261023.ja.md): clean28 データセット要約
- [sim_to_real_act.md](sim_to_real_act.ja.md): Phase 2-2: sim ACT → 実機 Follower（変換ラッパー）
- [real_robot_deploy.md](real_robot_deploy.ja.md): 実機学習 ACT / SmolVLA の dry-run → live
- [real_eval_protocol.ja.md](real_eval_protocol.ja.md): 学習後の実機 ACT 評価（オープンループ採点と live 評価手順）。収録 QC の閾値は本ページ
- [units.md](units.ja.md): ラジアン / 度 / グリッパ 0–100
- [training.md](training.ja.md): ACT 学習
- [LeRobot SO-101](https://huggingface.co/docs/lerobot/so101)
- [LeRobot Cameras](https://huggingface.co/docs/lerobot/cameras)
- [Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots)
