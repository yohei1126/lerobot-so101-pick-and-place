# データセット（bag / 合成 / LeRobot）

## sample_bag（フィクスチャ）

契約どおりの rosbag2 を Docker で生成する。

```bash
docker compose -f docker/docker-compose.yml build dev
docker compose -f docker/docker-compose.yml run --rm generate-bag

docker compose -f docker/docker-compose.yml run --rm dev \
  bash -lc 'ros2 bag info port_pick_align/tests/fixtures/sample_bag'
```

出力先: `port_pick_align/tests/fixtures/sample_bag/`

## 合成 LeRobotDataset

ホスト Python 3.12+（Docker には torch / lerobot を入れない）。

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# 契約準拠の合成データ（既定: 8 episodes × 64 frames）
python scripts/generate_synthetic_dataset.py
```

成果物（gitignore 対象）: `data/synthetic/lerobot/`

## rosbag2 → 検証 → LeRobotDataset

`rosbags` で bag を読む。ROS ランタイムは不要。

```bash
# unit: sample_bag の変換・品質ゲート（sync / drop / limits / static）
(cd port_pick_align && pytest -m unit tests/test_converter.py tests/test_validator.py -q)

python scripts/convert_bag.py \
  --bag port_pick_align/tests/fixtures/sample_bag \
  --output data/from_bag/lerobot
```

プログラムから:

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

閾値と可動域は `configs/contract.yaml` の `quality` / `robot.joint_limits`。
