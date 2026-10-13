# 継続的インテグレーション（CI）仕様およびローカル検証手順

本資料では、GitHub Actions 上で自動実行される CI ワークフローの構成と、同一の検証をローカル環境で再現するための手順を解説する。

## ローカル環境での検証コマンド

ホスト側の Python 仮想環境において、静的解析ツール（Ruff, mypy）およびテストスイート（pytest）を順次実行する。

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# コードスタイルおよび静的型チェック
ruff check port_pick_align scripts
ruff format --check port_pick_align scripts
(cd port_pick_align && mypy src/port_pick_align)

# 単体テストおよび統合テストの実行
(cd port_pick_align && pytest -m unit -q)
(cd port_pick_align && pytest -m integration -q)
```

## GitHub Actions ワークフロー構成

`.github/workflows/ci.yml` で定義されたパイプラインでは、以下のステージ構成を採用している。

1. **Lint ジョブと Unit テストジョブの並列実行**: コードフォーマット検査、型検査、および高速な単体テストを並行して実行する。
2. **Integration テストジョブの直列実行**: 単体テストジョブが正常終了した後に起動し、モデル重みの保存や推論スモークテストを含む統合テストを実行する。

