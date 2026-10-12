# Task 1: Docker 環境 & sample_bag

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

契約の正本は [`configs/contract.yaml`](../configs/contract.yaml)。
