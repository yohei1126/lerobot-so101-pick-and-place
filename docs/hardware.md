# SO-ARM101 / Feetech STS3215 ドライラン手順書

本手順書は、実機アームの接続前に必要な公式仕様の確認、Linux 環境での udev ルール設定、および Python 依存関係の解決を行うための事前準備手順を定める。配線および電源投入前の段階では物理的な駆動を行わず、ソフトウェア的な接続確認にとどめる。

## 公式仕様と参照ドキュメント

- [Assemble SO-101](https://huggingface.co/docs/lerobot/en/assemble_so101)（組立手順）
- [SO-101](https://huggingface.co/docs/lerobot/en/so101)（モータ初期設定 `lerobot-setup-motors` およびキャリブレーション手順）
- [SO-100](https://huggingface.co/docs/lerobot/en/so100)（ソフトウェア構成の共通仕様）

サーボモータの ID（1〜6）と関節名の対応は、本リポジトリの [`configs/contract.yaml`](../configs/contract.yaml) における `robot.joint_names` の定義と一致させる。

- 割り当て順序: `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper`
- LeRobot におけるロボット識別名: `so101_follower`（リーダー側を使用する場合は `so101_leader`）

## ホスト Python 依存パッケージの導入

```bash
cd /path/to/utokyo-physical-ai-applied1-final-assignment
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "port_pick_align/[training,feetech,dev]"
```

機材非接続状態におけるモジュール読み込みテスト:

```bash
python -c "import lerobot; print('lerobot OK', lerobot.__version__)"
# Feetech モータバス実装の依存関係解決を確認
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print('feetech OK')"
```

読み込み時に `ImportError` が発生した場合は、`pip install -e "port_pick_align/[feetech]"` を再実行して C++ 拡張モジュールやシリアル通信ライブラリの導入状況を確認する。

## シリアル通信ポートの識別

### Linux 環境

```bash
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
# アダプタの属性（vendor / product / serial）の確認
udevadm info -a -n /dev/ttyACM0 | head -n 40
```

### macOS 環境

macOS では udev による静的シンボリックリンク生成が行えないため、接続時に割り当てられたデバイスファイル名を直接確認する。

```bash
ls /dev/tty.usbmodem* /dev/tty.usbserial* 2>/dev/null
```

LeRobot の実行引数には、検出されたパス（例: `/dev/tty.usbmodem585A0076841`）を直接指定する。

## udev ルールの適用（Linux 環境）

設定テンプレート: [`deploy/udev/99-feetech-so101.rules`](../deploy/udev/99-feetech-so101.rules)

1. `udevadm info` を実行し、使用する USB シリアル変換器の `idVendor`, `idProduct`, `serial` を取得する。
2. テンプレート内の `REPLACE_*_SERIAL` および SYMLINK 名を実際の機材シリアル番号に合わせて更新する。
3. ルールファイルをシステムへ配置し、反映する。

```bash
sudo cp deploy/udev/99-feetech-so101.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
# 実行ユーザを dialout グループへ追加（シリアルポートへのアクセス権限付与）
sudo usermod -aG dialout "$USER"
# 再ログイン後に固定シンボリックリンクの生成を確認
ls -l /dev/ttyUSB_so101_*
```

## 実機接続時の初期設定コマンド（参考仕様）

モータ ID の割り当て（各ポート名は使用環境のデバイスファイル名に置換する）:

```bash
lerobot-setup-motors \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyUSB_so101_follower

lerobot-setup-motors \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyUSB_so101_leader
```

キャリブレーション処理（実機の組み立ておよび 12V 電源投入後に実施）:

```bash
# 公式ドキュメントの calibrate / control_robot 手順に準拠して実行する
# 例: python -m lerobot.scripts.control_robot calibrate ...
```

電源仕様上の注意: Feetech STS3215 サーボモータの定格駆動電圧は 12V である。USB バスパワーのみでは駆動しないため、外部電源ユニットを接続する必要がある。また、カメラ画像転送とシリアル通信の帯域競合を防止するため、USB ホストコントローラの分離または規格に適合した USB ハブを経由して接続する。

## 事前準備チェックリスト

- [ ] 公式 SO-101 および Feetech のセットアップ手順を確認した
- [ ] `port_pick_align/[training,feetech]` の依存関係インストールが正常に完了した
- [ ] `lerobot` および Feetech motors モジュールのインポート試験に通過した
- [ ] Linux 環境において、機材固有のシリアル番号に基づく udev ルールを設定した
- [ ] macOS 環境において、`/dev/tty.usbmodem*` デバイスの確認手順を把握した
- [ ] 実機到着後に実行するモータ設定およびキャリブレーションのコマンド仕様を把握した

