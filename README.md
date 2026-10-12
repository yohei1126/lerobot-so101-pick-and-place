# utokyo-physical-ai-applied1-final-assignment

Physical AI 応用編1 最終課題の実装リポジトリ。  
海事・港湾モック（小型直方体の把持・整列）と RobOps パイプライン（rosbag2 → 検証 → ACT → ROS 2 推論）を対象とする。

## ドキュメント

手順・コマンドの詳細は [`docs/`](docs/README.md) を参照。

| Task | 文書 |
| --- | --- |
| 1 環境・フィクスチャ | [docs/task1_docker_fixture.md](docs/task1_docker_fixture.md) |
| 2 合成データ ACT | [docs/task2_synthetic_act.md](docs/task2_synthetic_act.md) |
| 3 bag → LeRobot | [docs/task3_bag_to_lerobot.md](docs/task3_bag_to_lerobot.md) |
| 4 ROS 2 / Rerun | [docs/task4_ros2_rerun.md](docs/task4_ros2_rerun.md) |
| 5 E2E / Feetech | [docs/task5_e2e.md](docs/task5_e2e.md) · [docs/hardware_udev_feetech.md](docs/hardware_udev_feetech.md) |
| CI | [docs/ci.md](docs/ci.md) |

最短の結合確認:

```bash
./scripts/e2e_pipeline_smoke.sh
```

## ディレクトリ構成

```text
.
├── configs/contract.yaml   # トピック・形状・モデル I/O の契約（SSOT）
├── docs/                   # 手順・クイックスタート
├── scripts/                # bag 生成・変換・E2E スモーク
├── deploy/udev/            # Linux udev ルール例
├── port_pick_align/        # Python（LeRobot / RobOps / ACT）
├── ros2_ws/                # ROS 2 推論・可視化ノード
├── docker/                 # ROS 2 Humble 実行環境
└── .github/workflows/      # lint / unit / integration
```

## 実行環境の役割

| 環境 | 用途 |
| --- | --- |
| Docker (`docker/`) | ROS 2、rosbag2、推論モック、Rerun |
| Host Python venv | 合成データ、ACT、converter / validator、Feetech |
| Cloud GPU | ACT 本格学習（任意） |

## 契約（contract.yaml）

カメラ 2 眼（640×480@30）、関節 6DOF、ACT（ResNet18、chunk_size=30）のトピック名と次元を一元管理する。  
converter / validator / 推論ノードはすべてこのファイルを参照する。

## ライセンス

[MIT](LICENSE)
