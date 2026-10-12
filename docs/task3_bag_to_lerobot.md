# Task 3: rosbag2 → 検証 → LeRobotDataset

ホスト Python 3.12+（`rosbags` で bag を読む。ROS ランタイムは不要）。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "port_pick_align/[training,dev]"

# unit: sample_bag の変換・品質ゲート（sync / drop / limits / static）
(cd port_pick_align && pytest -m unit tests/test_converter.py tests/test_validator.py -q)
```

CLI:

```bash
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
