# utokyo-physical-ai-applied1-final-assignment

Physical AI 応用編1 最終課題の実装リポジトリ。  
海事・港湾モック（小型直方体の把持・整列）と RobOps パイプライン（rosbag2 → 検証 → ACT → ROS 2 推論）を対象とする。

## ドキュメント

手順・コマンドの詳細は [`docs/`](docs/README.md) を参照。

| 用途 | 文書 |
| --- | --- |
| 環境・契約 | [docs/setup.md](docs/setup.md) |
| データセット | [docs/dataset.md](docs/dataset.md) |
| ACT 学習 | [docs/training.md](docs/training.md) |
| ROS 2 / Rerun | [docs/ros2_inference.md](docs/ros2_inference.md) |
| MuJoCo シミュ | [docs/simulation.md](docs/simulation.md) |
| 整列評価 | [docs/evaluation.md](docs/evaluation.md) |
| E2E / 実機準備 | [docs/e2e.md](docs/e2e.md) · [docs/hardware.md](docs/hardware.md) |
| CI | [docs/ci.md](docs/ci.md) |
| 提出 | [docs/submission.md](docs/submission.md) · [report/](report/) |
| Plan B（縮退） | [docs/plan_b.md](docs/plan_b.md) |

最短の結合確認:

```bash
./scripts/e2e_pipeline_smoke.sh
```

## 提出

- チェックリスト: [docs/submission.md](docs/submission.md)
- レポート原稿: [report/](report/)
- PDF 生成: `./scripts/build_report_pdf.sh yohei1126`
- ハード縮退: [docs/plan_b.md](docs/plan_b.md)

## ディレクトリ構成

```text
.
├── configs/contract.yaml   # トピック・形状・モデル I/O の契約（SSOT）
├── docs/                   # 手順・クイックスタート・提出
├── report/                 # 解説レポート Markdown 雛形
├── scripts/                # bag 生成・変換・E2E / シミュ評価 / PDF 生成
├── deploy/udev/            # Linux udev ルール例
├── port_pick_align/        # Python（LeRobot / RobOps / ACT / MuJoCo）
├── ros2_ws/                # ROS 2 推論・可視化ノード
├── docker/                 # ROS 2 Humble 実行環境
└── .github/workflows/      # lint / unit / integration
```

## 実行環境の役割

| 環境 | 用途 |
| --- | --- |
| Docker (`docker/`) | ROS 2、rosbag2、推論モック、Rerun |
| Host Python venv | 合成データ、ACT、converter / validator、Feetech、MuJoCo |
| Cloud GPU | ACT 本格学習（任意） |

## 契約（contract.yaml）

カメラ 2 眼（640×480@30）、関節 6DOF、ACT（ResNet18、chunk_size=30）のトピック名と次元を一元管理する。  
converter / validator / 推論ノードはすべてこのファイルを参照する。

## ライセンス

[MIT](LICENSE)
