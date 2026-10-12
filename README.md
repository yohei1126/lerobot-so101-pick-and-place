# utokyo-physical-ai-applied1-final-assignment

Physical AI 応用編1 最終課題の実装リポジトリ。  
海事・港湾モック（小型直方体の把持・整列）と RobOps パイプライン（rosbag2 → 検証 → ACT → ROS 2 推論）を対象とする。

## ディレクトリ構成

```text
.
├── configs/contract.yaml          # トピック・形状・モデル I/O の契約（Single Source of Truth）
├── scripts/generate_sample_bag.py # テスト用 rosbag2 フィクスチャ生成
├── scripts/generate_synthetic_dataset.py  # 合成 LeRobotDataset（Task 2）
├── python/                        # スタンドアロン Python（LeRobot / RobOps）
│   ├── src/pai_final/
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

# 契約どおりの sample_bag を生成（python/tests/fixtures/sample_bag）
docker compose -f docker/docker-compose.yml run --rm generate-bag

# 内容確認
docker compose -f docker/docker-compose.yml run --rm dev \
  bash -lc 'ros2 bag info python/tests/fixtures/sample_bag'
```

対話シェル:

```bash
docker compose -f docker/docker-compose.yml run --rm dev
```

## Task 2 クイックスタート（合成データ ACT 疎通）

ホスト Python 3.10+ で実行する（Docker には torch / lerobot を入れない）。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "python/[training,dev]"

# 契約準拠の合成 LeRobotDataset（既定: 8 episodes × 64 frames）
python scripts/generate_synthetic_dataset.py

# ResNet18 ACT を 100 step 学習し best_model.pt を保存 → 推論スモーク
python -m pai_final.training.train_act
```

成果物（ローカル生成・gitignore 対象）:

- `data/synthetic/lerobot/` — 合成データセット
- `checkpoints/synthetic_act/best_model.pt` — 疎通用チェックポイント
- `checkpoints/synthetic_act/training_metrics.json`

推論のみ再実行:

```bash
python -m pai_final.training.train_act --infer-only
```

## CI（ローカル相当）

```bash
pip install -e "python/[training,dev]"

ruff check python scripts
ruff format --check python scripts
(cd python && mypy src/pai_final)

(cd python && pytest -m unit -q)
(cd python && pytest -m integration -q)
```

GitHub Actions（`.github/workflows/ci.yml`）では lint と unit を並列実行し、unit 成功後に integration を実行する。

## 契約（contract.yaml）

カメラ 2 眼（640×480@30）、関節 6DOF、ACT（ResNet18、chunk_size=30）のトピック名と次元を一元管理する。  
後続の converter / validator / 推論ノードはすべてこのファイルを参照する。

## ライセンス

MIT（提出整備時に `LICENSE` を追加予定）
