# ドキュメント体系一覧

本ディレクトリ配下の技術文書は、環境構築、データパイプライン、学習、推論、シミュレーション、および成果物提出の各領域ごとに体系化されている。

| ドキュメント | 対象領域と主な内容 |
| --- | --- |
| [setup.md](setup.md) | Docker コンテナおよびホスト Python 仮想環境の構築手順、契約設定ファイルの概要 |
| [dataset.md](dataset.md) | テスト用 rosbag2 の生成、合成データ作成、MuJoCo 教示データ収集、LeRobotDataset 形式への変換および品質検証 |
| [training.md](training.md) | ACT モデルの訓練、重みチェックポイントの保存、および推論疎通確認 |
| [act_so101_trial_smoke_20261019.md](act_so101_trial_smoke_20261019.md) | 実機 trial3 データセットでの ACT スモーク学習結果（2026-10-19、事実記録） |
| [ros2_inference.md](ros2_inference.md) | ROS 2 Humble ノード構成、モック推論パイプライン、Rerun 可視化連携 |
| [simulation.md](simulation.md) | MuJoCo シミュレータによる閉ループ制御評価、対話型ビューアおよび動画出力 |
| [evaluation.md](evaluation.md) | 平面位置誤差・ヨー角誤差・成功率の集計モジュール（`eval_alignment`）API 仕様 |
| [units.md](units.md) | sim/契約のラジアンと実機 LeRobot の度・グリッパ 0–100 の換算 |
| [sim_to_real_act.md](sim_to_real_act.md) | Phase 2-2: sim 学習 ACT を実機 SO-101 で dry-run / 低速 live |
| [results/README.md](results/README.md) | 閉ループ評価の実測ログと未計測プレースホルダ（post50 公式含む） |
| [figures/README.md](figures/README.md) | レポート図表の再生成（学習曲線・ヒストグラム・初期XY・ロールアウト） |
| [e2e.md](e2e.md) | データ収集から推論までを結合して実行するエンドツーエンドパイプライン試験 |
| [hardware.md](hardware.md) | SO-ARM101 および Feetech サーボモータの Linux udev 設定、接続準備ドライラン、シミュレーション準拠の作業エリア配置、購入済み機材 |
| [real_robot_bringup.md](real_robot_bringup.md) | Mac / LeRobot 0.6.1 による SO-101 Leader/Follower の実機 bring-up（ポート識別、キャリブレーション、テレオペ、カメラ） |
| [real_robot_deploy.md](real_robot_deploy.md) | 実機学習 ACT / SmolVLA の dry-run → live（単位変換なし・安全クランプ） |
| [ci.md](ci.md) | GitHub Actions CI ワークフローの構成とローカルでの静的解析・テスト実行手順 |
| [submission.md](submission.md) | OmniCampus 提出物仕様（PDF レポート、GitHub、YouTube 動画）および点検リスト |
| [plan_b.md](plan_b.md) | 実機障害時におけるシミュレーションおよび公開データを活用した縮退運用手順 |

