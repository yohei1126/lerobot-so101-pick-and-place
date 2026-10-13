# データセット管理仕様（rosbag2 / 合成データ / LeRobotDataset）

本資料では、契約仕様に準拠したテスト用 rosbag2 の生成、パイプライン疎通用合成データの作成、ならびに rosbag2 から品質検証を経て LeRobotDataset 形式へ変換する手順を解説する。

## テスト用 rosbag2（sample_bag）の生成

契約定義（`configs/contract.yaml`）に従ったトピック構成およびデータ形状を持つテスト用 rosbag2 を Docker 環境で生成する。

```bash
docker compose -f docker/docker-compose.yml build dev
docker compose -f docker/docker-compose.yml run --rm generate-bag

# 生成された bag のメタデータ確認
docker compose -f docker/docker-compose.yml run --rm dev \
  bash -lc 'ros2 bag info port_pick_align/tests/fixtures/sample_bag'
```

出力先ディレクトリ: `port_pick_align/tests/fixtures/sample_bag/`

## 合成 LeRobotDataset の生成

実機データ取得前のパイプライン疎通検証を目的として、ホスト Python 仮想環境上で擬似的なエピソードデータを生成する（Docker イメージの肥大化を防ぐため、PyTorch および LeRobot はホスト環境でのみ実行する）。

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# 契約準拠の合成データ生成（既定値: 8 エピソード × 各 64 フレーム）
python scripts/generate_synthetic_dataset.py
```

生成されたデータセットは `data/synthetic/lerobot/` に出力される（Git 管理対象外）。

## rosbag2 から LeRobotDataset への変換と品質検証

本リポジトリの変換パイプラインは `rosbags` ライブラリを利用してバイナリを直接解析するため、ホスト側に ROS 2 ランタイムを導入することなくデータ変換を実行できる。変換処理の内部で品質バリデータが動作し、基準を満たさないエピソードを自動的に棄却する。

```bash
# 単体テスト: sample_bag の変換処理および品質検証ゲート（同期・欠落・可動域・静止検知）
(cd port_pick_align && pytest -m unit tests/test_converter.py tests/test_validator.py -q)

# CLI スクリプトによる変換実行
python scripts/convert_bag.py \
  --bag port_pick_align/tests/fixtures/sample_bag \
  --output data/from_bag/lerobot
```

Python スクリプトから直接変換関数を呼び出す場合の記述例:

```python
from pathlib import Path
from port_pick_align.contract import load_contract
from port_pick_align.dataset.converter import convert_bag_to_lerobot

contract = load_contract()
convert_bag_to_lerobot(
    "port_pick_align/tests/fixtures/sample_bag",
    Path("data/from_bag/lerobot"),
    contract=contract,
)
```

同期許容誤差、フレーム欠落閾値、および関節可動域の判定値は、すべて `configs/contract.yaml` の `quality` および `robot.joint_limits` セクションに定義された閾値に従う。

