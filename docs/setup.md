# 環境セットアップ

Docker（Mac では Colima 等）とホスト Python 3.12+ の役割分担。

| 環境 | 用途 |
| --- | --- |
| Docker (`docker/`) | ROS 2、rosbag2、推論モック、Rerun |
| Host Python venv | 合成データ、ACT、converter / validator、Feetech、MuJoCo |
| Cloud GPU | ACT 本格学習（任意） |

## 契約（Single Source of Truth）

トピック名・解像度・関節名・モデル I/O の正本は [`configs/contract.yaml`](../configs/contract.yaml)。

## Docker

```bash
# イメージビルド（generate-bag は同一イメージを参照）
docker compose -f docker/docker-compose.yml build dev

# 対話シェル
docker compose -f docker/docker-compose.yml run --rm dev
```

sample_bag の生成は [dataset.md](dataset.md) を参照。

## Host Python venv

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "port_pick_align/[training,dev]"
```

用途に応じて extra を追加する:

| Extra | 用途 |
| --- | --- |
| `training` | ACT / LeRobot / torch |
| `feetech` | 実機モータバス |
| `simulation` | MuJoCo / Gymnasium / Rerun（シミュ評価） |
| `dev` | pytest / ruff / mypy |
