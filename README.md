# utokyo-physical-ai-applied1-final-assignment

本リポジトリは、東京大学「Physical AI 応用編1」最終課題の実装基盤である。  
造船・海事現場における部品やコンテナの配置作業を模した「卓上直方体の把持・精密整列」タスクを対象とし、データ収集から品質検証、ACT モデルの訓練、ROS 2 上での推論および MuJoCo シミュレーション評価に至る RobOps パイプラインを提供する。

## ドキュメント一覧

環境構築、実行手順、評価方法の詳細は [`docs/`](docs/README.md) 配下の各文書を参照する。

| 対象領域 | 参照文書 | 概要 |
| --- | --- | --- |
| 環境・契約 | [docs/setup.md](docs/setup.md) | Docker、ホスト Python 環境の構築と契約ファイルの仕様 |
| データセット | [docs/dataset.md](docs/dataset.md) | rosbag2 の生成、品質検証、LeRobot 形式への変換 |
| ACT 学習 | [docs/training.md](docs/training.md) | ACT モデルの訓練手順とチェックポイントの生成 |
| ROS 2 / Rerun | [docs/ros2_inference.md](docs/ros2_inference.md) | ROS 2 推論ノードの実行と Rerun による軌道可視化 |
| シミュレーション | [docs/simulation.md](docs/simulation.md) | MuJoCo 環境を用いた閉ループ制御と評価 |
| 評価指標 | [docs/evaluation.md](docs/evaluation.md) | 位置・姿勢誤差の集計 API 仕様 |
| 結合テスト・機材 | [docs/e2e.md](docs/e2e.md) · [docs/hardware.md](docs/hardware.md) | エンドツーエンド結合試験および実機準備手順 |
| 継続的インテグレーション | [docs/ci.md](docs/ci.md) | GitHub Actions およびローカルテストの実行 |
| 提出仕様 | [docs/submission.md](docs/submission.md) · [report/](report/) | 成果物要件と提出用レポート原稿 |
| 縮退運用（Plan B） | [docs/plan_b.md](docs/plan_b.md) | 実機障害時におけるシミュレーション代替運用 |

パイプライン全体の疎通確認は、以下のスクリプトにより一括実行できる。

```bash
./scripts/e2e_pipeline_smoke.sh
```

## 教示収集→学習→評価の一括実行

Issue #41 以降の再学習のように、収集・ACT 学習・複数チェックポイントの閉ループ評価を無人で回すときは `scripts/run_pipeline.sh` を使う。進捗は `results/<run>/status.json`、比較表は `results/<run>/summary.md` に書き出される。エージェントは `nohup` で起動した直後に終了してよい。

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,training]"

# Mac (MPS) 本学習。終了時に PR へ summary.md をコメントする例:
mkdir -p results/post41
nohup ./scripts/run_pipeline.sh \
  --run post41 \
  --device mps \
  --dataset-dir data/sim_expert/lerobot_post41 \
  --checkpoint-dir checkpoints/sim_act_post41 \
  --steps 5000 \
  --collect-episodes 100 \
  --eval-episodes 20 \
  --pr 42 \
  > results/post41/pipeline.log 2>&1 &
echo "pid=$!  status=results/post41/status.json"

# 収集または学習を飛ばして評価だけ再実行:
./scripts/run_pipeline.sh --run post41 --skip-collect --skip-train --device mps

# CPU スモーク（少数エピソード・約 50 step）:
./scripts/run_pipeline.sh --smoke --device cpu
```

評価対象は存在する `best_model.pt` / `best_model_te.pt` / `last.pt` / `step_*.pt` で、それぞれ chunk30 と Temporal Ensembling の両方を既存の `scripts/run_sim_eval.py` で回す。`--pr N` は `gh` が無い環境ではスキップする。

## 成果物の提出

- 提出前チェックリスト: [docs/submission.md](docs/submission.md)
- レポート原稿: [report/](report/)
- レポート PDF の生成コマンド: `./scripts/build_report_pdf.sh yohei1126`
- 機材未着・故障時の縮退方針: [docs/plan_b.md](docs/plan_b.md)

## ディレクトリ構成

```text
.
├── configs/contract.yaml   # トピック名・テンソル形状・モデル入出力の契約（SSOT）
├── docs/                   # 各種手順書・仕様解説
├── report/                 # 提出用レポート Markdown 原稿
├── scripts/                # bag 生成・データ変換・E2E 試験・シミュ評価スクリプト
├── deploy/udev/            # Linux 用 udev 設定ルール例
├── port_pick_align/        # Python パッケージ（LeRobot / RobOps / ACT / MuJoCo）
├── ros2_ws/                # ROS 2 ワークスペース（推論ノード・可視化ノード）
├── docker/                 # ROS 2 Humble 実行環境用 Dockerfile / Compose 設定
└── .github/workflows/      # CI ワークフロー（静的解析・単体テスト・結合テスト）
```

## 実行環境の分離

開発再現性と環境汚染防止のため、実行層ごとに役割を分離している。

| 実行環境 | 担当範囲 |
| --- | --- |
| Docker (`docker/`) | ROS 2 Humble ランタイム、rosbag2 記録再生、推論モック、Rerun 可視化 |
| ホスト Python 仮想環境 | 合成データ生成、PyTorch / ACT 学習、データセット変換器・バリデータ、MuJoCo シミュレータ |
| クラウド GPU（任意） | 大規模エピソードを用いた ACT モデルの本格学習 |

## 契約の一元管理（contract.yaml）

本システムでは、Top/Wrist の 2 眼カメラ（640×480、30 fps）、6 自由度アーム、ACT モデル（ResNet18、chunk_size=30）のトピック名とデータ次元を [`configs/contract.yaml`](configs/contract.yaml) で一元管理している。  
データ変換器、品質バリデータ、および推論ノードはすべて本設定ファイルを参照して動作するため、仕様変更時の不整合を防止できる。

## ライセンス

本リポジトリのコードは [MIT License](LICENSE) の下で公開されている。

