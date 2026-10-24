# 開発環境のセットアップ手順

本リポジトリでは、ROS 2 ランタイムを内包する Docker 環境と、機械学習モデルの訓練やシミュレーションを行うホスト Python 仮想環境の役割を明確に分離している。

## 実行環境の責務分担

| 実行環境 | 担当範囲 | 構成要素 |
| --- | --- | --- |
| Docker コンテナ (`docker/`) | ROS 2 通信基盤、rosbag2 記録再生、推論モックノード、Rerun 可視化 | ROS 2 Humble |
| ホスト Python 仮想環境 | 合成データ生成、ACT 訓練、データセット変換・品質検証、Feetech 通信、MuJoCo | Python 3.12+ 仮想環境 (`.venv`) |
| クラウド GPU（任意） | 大規模エピソードを用いた ACT モデルの本格学習 | CUDA 対応コンピュート環境 |

## 契約ファイルの一元管理

トピック名、画像解像度、関節自由度、およびモデル入出力仕様の正本は [`configs/contract.yaml`](../configs/contract.yaml) に定義されている。各コンポーネントはこの設定を一意の参照元（Single Source of Truth）として利用する。

## Docker 環境の構築と起動

Docker Desktop または Colima 等のコンテナランタイム環境上で、以下のコマンドを実行してイメージをビルドする。

```bash
# 開発用イメージのビルド（generate-bag サービスも同一イメージを参照）
docker compose -f docker/docker-compose.yml build dev

# 対話型シェルの起動
docker compose -f docker/docker-compose.yml run --rm dev
```

テスト用 sample_bag の生成手順は [dataset.md](dataset.md) を参照する。

## ホスト Python 仮想環境の構築

ホスト側の Python 仮想環境を作成し、必要なパッケージを編集可能モード（`-e`）で導入する。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "port_pick_align/[training,dev]"
```

実行するタスクに応じて、以下のオプショナル依存関係（extra）を追加してインストールする。

| 拡張機能名 | 用途 | 主な含まれるライブラリ |
| --- | --- | --- |
| `training` | ACT モデルの訓練および推論 | PyTorch, LeRobot, torchvision |
| `feetech` | 実機サーボモータとのシリアル通信 | Feetech モータ制御ライブラリ |
| `simulation` | MuJoCo シミュレータによる閉ループ評価 | MuJoCo, Gymnasium, Rerun |
| `dev` | 開発時テストおよび静的解析 | pytest, ruff, mypy |

