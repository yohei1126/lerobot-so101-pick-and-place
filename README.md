# utokyo-physical-ai-applied1-final-assignment

Physical AI 応用編1 最終課題の実装リポジトリ。  
海事・港湾モック（小型直方体の把持・整列）と RobOps パイプライン（rosbag2 → 検証 → ACT → ROS 2 推論）を対象とする。

## ディレクトリ構成

```text
.
├── configs/contract.yaml          # トピック・形状・モデル I/O の契約（Single Source of Truth）
├── scripts/generate_sample_bag.py # テスト用 rosbag2 フィクスチャ生成
├── python/                        # スタンドアロン Python（LeRobot / RobOps）
│   ├── src/pai_final/
│   │   ├── dataset/               # converter / validator（Task 3）
│   │   ├── training/              # ACT 学習（Task 2）
│   │   └── evaluation/            # 整列評価（Task 4）
│   └── tests/fixtures/sample_bag/ # 契約準拠の短い rosbag2
├── ros2_ws/                       # ROS 2 ワークスペース（推論・可視化ノード）
│   └── src/pai_final_pkg/
└── docker/                        # ROS 2 Humble 実行環境
```

## 実行環境の役割

| 環境 | 用途 |
| --- | --- |
| Docker (`docker/`) | ROS 2、rosbag2 フィクスチャ生成、validator CI、推論モック |
| Host Python venv | LeRobot CLI ドライラン、Feetech / udev（Task 5） |
| Cloud GPU | ACT 本格学習（Task 2） |

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

## 契約（contract.yaml）

カメラ 2 眼（640×480@30）、関節 6DOF、ACT（ResNet18）のトピック名と次元を一元管理する。  
後続の converter / validator / 推論ノードはすべてこのファイルを参照する。

## Task 1 完了チェック

- [x] `configs/contract.yaml` にカメラトピック・解像度・関節名が定義されている
- [x] `python/` と `ros2_ws/` の二系統ディレクトリが分離されている
- [x] Docker（ROS 2 Humble）でローカル実行環境が固定されている
- [x] `scripts/generate_sample_bag.py` でテスト用 rosbag2 フィクスチャを生成できる

## ライセンス

MIT（提出整備時に `LICENSE` を追加予定）
