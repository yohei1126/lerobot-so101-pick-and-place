# utokyo-physical-ai-applied1-final-assignment

Physical AI 応用編1 最終課題の実装リポジトリ。  
海事・港湾モック（小型直方体の把持・整列）と RobOps パイプライン（rosbag2 → 検証 → ACT → ROS 2 推論）を対象とする。

## ディレクトリ構成

```text
.
├── configs/contract.yaml          # トピック・形状・モデル I/O の契約（Single Source of Truth）
├── scripts/generate_sample_bag.py # テスト用 rosbag2 フィクスチャ生成
├── scripts/generate_synthetic_dataset.py  # 合成 LeRobotDataset（Task 2）
├── port_pick_align/                     # スタンドアロン Python（LeRobot / RobOps）
│   ├── src/port_pick_align/
│   │   ├── dataset/               # converter / validator / synthetic
│   │   ├── training/              # ACT 学習（Task 2）
│   │   └── evaluation/            # 整列評価（Task 4）
│   └── tests/                     # unit / integration
├── ros2_ws/                       # ROS 2 ワークスペース（推論・可視化ノード）
│   └── src/pai_final_pkg/
├── docker/                        # ROS 2 Humble 実行環境
└── .github/workflows/ci.yml       # lint / unit / integration
```

## 実行環境の役割

| 環境 | 用途 |
| --- | --- |
| Docker (`docker/`) | ROS 2、rosbag2 フィクスチャ生成、validator CI、推論モック |
| Host Python venv | 合成データ生成、ACT 疎通学習、LeRobot / Feetech（Task 5） |
| Cloud GPU | ACT 本格学習（任意） |

## Task 1 クイックスタート

前提: Docker（Mac では Colima 等）が利用可能であること。

```bash
# イメージビルド（generate-bag は同一イメージを参照）
docker compose -f docker/docker-compose.yml build dev

# 契約どおりの sample_bag を生成（port_pick_align/tests/fixtures/sample_bag）
docker compose -f docker/docker-compose.yml run --rm generate-bag

# 内容確認
docker compose -f docker/docker-compose.yml run --rm dev \
  bash -lc 'ros2 bag info port_pick_align/tests/fixtures/sample_bag'
```

対話シェル:

```bash
docker compose -f docker/docker-compose.yml run --rm dev
```

## Task 2 クイックスタート（合成データ ACT 疎通）

ホスト Python 3.12+ で実行する（Docker には torch / lerobot を入れない。`lerobot` 0.6.x は 3.12 必須）。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "port_pick_align/[training,dev]"

# 契約準拠の合成 LeRobotDataset（既定: 8 episodes × 64 frames）
python scripts/generate_synthetic_dataset.py

# ResNet18 ACT を 100 step 学習し best_model.pt を保存 → 推論スモーク
python -m port_pick_align.training.train_act
```

成果物（ローカル生成・gitignore 対象）:

- `data/synthetic/lerobot/` — 合成データセット
- `checkpoints/synthetic_act/best_model.pt` — 疎通用チェックポイント
- `checkpoints/synthetic_act/training_metrics.json`

推論のみ再実行:

```bash
python -m port_pick_align.training.train_act --infer-only
```

## Task 3 クイックスタート（rosbag2 → 検証 → LeRobot）

ホスト Python 3.12+（`rosbags` で bag を読む。ROS ランタイムは不要）。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "port_pick_align/[training,dev]"

# unit: sample_bag の変換・品質ゲート（sync / drop / limits / static）
(cd port_pick_align && pytest -m unit tests/test_converter.py tests/test_validator.py -q)
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

## CI（ローカル相当）

```bash
pip install -e "port_pick_align/[training,dev]"

ruff check port_pick_align scripts
ruff format --check port_pick_align scripts
(cd port_pick_align && mypy src/port_pick_align)

(cd port_pick_align && pytest -m unit -q)
(cd port_pick_align && pytest -m integration -q)
```

GitHub Actions（`.github/workflows/ci.yml`）では lint と unit を並列実行し、unit 成功後に integration を実行する。

## 契約（contract.yaml）

カメラ 2 眼（640×480@30）、関節 6DOF、ACT（ResNet18、chunk_size=30）のトピック名と次元を一元管理する。  
後続の converter / validator / 推論ノードはすべてこのファイルを参照する。

## ライセンス

[MIT](LICENSE)
