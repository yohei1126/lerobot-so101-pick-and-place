# SO-ARM101 / Feetech STS3215 ドライラン手順（Task 5）

実機到着前に、公式ドキュメントの確認・udev（Linux）・Python 依存関係を整える。  
**ここではアームを動かさない**（接続時コマンドは控えのみ）。

## 公式ドキュメント

- [Assemble SO-101](https://huggingface.co/docs/lerobot/en/assemble_so101)
- [SO-101](https://huggingface.co/docs/lerobot/en/so101)（`lerobot-setup-motors`、キャリブレーション）
- [SO-100](https://huggingface.co/docs/lerobot/en/so100)（ソフトウェアは SO-101 と同系）

モータ名（ID 1–6）は本リポジトリの `configs/contract.yaml` の `robot.joint_names` と一致する:

`shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper`

LeRobot 側のロボット型は `so101_follower` / `so101_leader`（契約の `robot.lerobot_type`）。

## Host Python 依存関係

```bash
cd /path/to/utokyo-physical-ai-applied1-final-assignment
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "port_pick_align/[training,feetech,dev]"
```

実機なしの import スモーク:

```bash
python -c "import lerobot; print('lerobot OK', lerobot.__version__)"
# Feetech extra が入っていれば motors バス実装が解決できることだけ確認
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print('feetech OK')"
```

`ImportError` の場合は `pip install -e "port_pick_align/[feetech]"` を再実行する。

## USB シリアルポートの確認

### Linux

```bash
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
# アダプタ詳細（vendor / product / serial）
udevadm info -a -n /dev/ttyACM0 | head -n 40
```

### macOS

udev はない。接続後:

```bash
ls /dev/tty.usbmodem* /dev/tty.usbserial* 2>/dev/null
```

LeRobot には見つかったパスをそのまま渡す（例: `/dev/tty.usbmodem585A0076841`）。

## udev ルール（Linux のみ）

テンプレート: [`deploy/udev/99-feetech-so101.rules`](../deploy/udev/99-feetech-so101.rules)

1. 各アダプタの `idVendor` / `idProduct` / `serial` を `udevadm info` で確認する。
2. ルール内の `REPLACE_*_SERIAL` や SYMLINK 名を自分の機材に合わせて編集する。
3. インストール:

```bash
sudo cp deploy/udev/99-feetech-so101.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
# ユーザーを dialout に追加（未設定の場合）
sudo usermod -aG dialout "$USER"
# 再ログイン後:
ls -l /dev/ttyUSB_so101_*
```

## 実機接続時のコマンド控え（今は実行しない）

モータ ID 設定（公式手順に従い、ポートは自分のデバイスに置換）:

```bash
lerobot-setup-motors \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyUSB_so101_follower

lerobot-setup-motors \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyUSB_so101_leader
```

キャリブレーション（実機到着後・12V 電源投入後）:

```bash
# 公式ドキュメントの calibrate / control_robot 手順に従う
# 例（バージョンにより CLI 名が変わる場合あり）:
# python -m lerobot.scripts.control_robot calibrate ...
```

電源: STS3215 は **12V**。USB のみで駆動しない。USB ハブでカメラとシリアル帯域を分散する。

## チェックリスト

- [ ] 公式 SO-101 / Feetech セットアップを読んだ
- [ ] `pip install -e "port_pick_align/[training,feetech]"` が通る
- [ ] `import lerobot` / Feetech motors の import スモークが通る
- [ ] （Linux）udev ルールを機材の serial に合わせて編集・インストールした
- [ ] （macOS）`/dev/tty.usbmodem*` の確認方法を把握した
- [ ] 実機到着後の `lerobot-setup-motors` / calibrate コマンドを控えた
