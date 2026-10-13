# ドキュメント体系一覧

本ディレクトリ配下の技術文書は、環境構築、データパイプライン、学習、推論、シミュレーション、および成果物提出の各領域ごとに体系化されている。

| ドキュメント | 対象領域と主な内容 |
| --- | --- |
| [setup.md](setup.md) | Docker コンテナおよびホスト Python 仮想環境の構築手順、契約設定ファイルの概要 |
| [dataset.md](dataset.md) | テスト用 rosbag2 の生成、合成データ作成、LeRobotDataset 形式への変換および品質検証 |
| [training.md](training.md) | ACT モデルの訓練、重みチェックポイントの保存、および推論疎通確認 |
| [ros2_inference.md](ros2_inference.md) | ROS 2 Humble ノード構成、モック推論パイプライン、Rerun 可視化連携 |
| [simulation.md](simulation.md) | MuJoCo シミュレータによる閉ループ制御評価、対話型ビューアおよび動画出力 |
| [evaluation.md](evaluation.md) | 平面位置誤差・ヨー角誤差・成功率の集計モジュール（`eval_alignment`）API 仕様 |
| [e2e.md](e2e.md) | データ収集から推論までを結合して実行するエンドツーエンドパイプライン試験 |
| [hardware.md](hardware.md) | SO-ARM101 および Feetech サーボモータの Linux udev 設定、接続準備ドライラン |
| [ci.md](ci.md) | GitHub Actions CI ワークフローの構成とローカルでの静的解析・テスト実行手順 |
| [submission.md](submission.md) | OmniCampus 提出物仕様（PDF レポート、GitHub、YouTube 動画）および点検リスト |
| [plan_b.md](plan_b.md) | 実機障害時におけるシミュレーションおよび公開データを活用した縮退運用手順 |

