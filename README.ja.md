# lerobot-so101-pick-and-place

[LeRobot](https://github.com/huggingface/lerobot) を使った **SO-101** アームの **ピック＆プレース** 向け OSS ツールキットです。シミュレーション学習、実機デモ収録、**ACT** / **SmolVLA** 学習、安全寄りの実機ランナーを含みます。

[English README](README.md) · [ドキュメントサイト (JA)](https://yohei1126.github.io/lerobot-so101-pick-and-place/ja/) · [Docs site (EN)](https://yohei1126.github.io/lerobot-so101-pick-and-place/)

## ロボットが行うこと

フォロワーアームが卓上の小さな物体を把持し、目標姿勢（平面位置 + ヨー）へ整列・配置します。パイプラインは次のとおりです。

1. **Sim**: MuJoCo 卓上環境、スクリプト教示収集、ACT 閉ループ評価  
2. **Data**: rosbag2 / 合成 / LeRobotDataset 変換と品質検証  
3. **Train**: sim または実機デモでの ACT（および利用可能な SmolVLA スクリプト）  
4. **Real**: SO-101 Leader/Follower の bring-up、テレオペ収録、カメラ、単位変換付き sim→実機および実機学習ポリシーのデプロイランナー  

想定ハードウェアは **SO-101**（Feetech STS3215）と上カメラ・手首カメラです（詳細は docs）。

## クイックスタート

```bash
git clone https://github.com/yohei1126/lerobot-so101-pick-and-place.git
cd lerobot-so101-pick-and-place

python3.12 -m venv .venv
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,training,dev]"

# パイプライン疎通スモーク
./scripts/e2e_pipeline_smoke.sh

# 収集 → ACT 学習 → 複数チェックポイントの sim 評価（スモーク）
./scripts/run_pipeline.sh --smoke --device cpu
```

実機 bring-up、収録、udev、sim→実機 ACT、および実機学習 ACT/SmolVLA のデプロイ手順は `docs/` を参照してください。モータ指令の前に必ず dry-run を行ってください。

## ドキュメント

| トピック | English | 日本語 |
| --- | --- | --- |
| 索引 | [docs/index.en.md](docs/index.en.md) | [docs/index.ja.md](docs/index.ja.md) |
| セットアップ | [docs/setup.en.md](docs/setup.en.md) | [docs/setup.ja.md](docs/setup.ja.md) |
| データセット | [docs/dataset.en.md](docs/dataset.en.md) | [docs/dataset.ja.md](docs/dataset.ja.md) |
| 学習 | [docs/training.en.md](docs/training.en.md) | [docs/training.ja.md](docs/training.ja.md) |
| シミュレーション | [docs/simulation.en.md](docs/simulation.en.md) | [docs/simulation.ja.md](docs/simulation.ja.md) |
| 機材 / bring-up / deploy | [hardware.en.md](docs/hardware.en.md) · [bring-up](docs/real_robot_bringup.en.md) · [deploy](docs/real_robot_deploy.en.md) | [hardware.ja.md](docs/hardware.ja.md) · [bring-up](docs/real_robot_bringup.ja.md) · [deploy](docs/real_robot_deploy.ja.md) |
| 公開サイト | https://yohei1126.github.io/lerobot-so101-pick-and-place/ | https://yohei1126.github.io/lerobot-so101-pick-and-place/ja/ |

一覧は各言語の docs 索引を参照してください。

## ディレクトリ構成

```text
.
├── configs/contract.yaml   # トピック・テンソル形状・モデル入出力（SSOT）
├── docs/                   # バイリンガル手順書（*.en.md / *.ja.md）
├── report/                 # レポート原稿（バイリンガル）
├── scripts/                # bag・変換・E2E・sim 評価・パイプライン
├── deploy/udev/            # Linux udev 例
├── port_pick_align/        # Python パッケージ（dataset / ACT / MuJoCo / deploy）
├── ros2_ws/                # ROS 2 Humble モック推論 / Rerun
├── mkdocs.yml              # GitHub Pages（Material + i18n）
└── tests / port_pick_align/tests
```

## モデル

- **ACT**: sim 閉ループ評価および実機トライアルの主模倣方策（`port_pick_align` の学習エントリ）  
- **SmolVLA**: 学習 / 実機ランナースクリプト（`scripts/train_smolvla.sh`、`scripts/run_smolvla_real.sh`、deploy 系 docs）

## ライセンス

[LICENSE](LICENSE) を参照してください。
