# Plan B: ハードウェア未着・故障時の縮退運用手順

実機環境（Plan A: SO-ARM101 および卓上モック）の稼働が困難な場合に、シミュレーションおよび公開データセットを活用して評価要件を満たすための縮退運用手順を定める。

## 切り替え判定基準

2026-10-23（金）時点でハードウェアが正常稼働しない場合は、以下の判定フローに従って Plan B へ移行する。

```text
実機の稼働可否 ──可──▶ Plan A（実機把持・整列および実行動画）
               └──否──▶ Plan B（シミュレーション / 公開データおよび RobOps 検証）
```

## 代替実行経路 / RobOps 検証 / レポート章の差し替え

### 1. タスク実行環境とデータ経路

実機動作の代替として、以下のいずれか、または双方を組み合わせてタスク実行結果を提示する。

| 代替経路 | 検証内容 | 参照手順 |
| --- | --- | --- |
| MuJoCo シミュレータ | 卓上把持・整列環境における閉ループ制御と評価メトリクスの算出 | [simulation.md](simulation.ja.md)（出力: `outputs/eval/sim_rollout.mp4`） |
| LeRobot 公開データセット | SO-100 などの公開データを用いた ACT の学習と推論動作確認 | [training.md](training.ja.md) · [dataset.md](dataset.ja.md) |

MuJoCo シミュレーションによる評価動画の出力例:

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,dev]"
python scripts/run_sim_eval.py --policy scripted --save-video --no-rerun
# 出力先: outputs/eval/sim_rollout.mp4
```

### 2. RobOps パイプラインの検証性提示

実機が存在しない場合でも、ソフトウェア側のパイプラインは契約定義に準拠して動作することを検証し、資料上で説明する。

- rosbag2 から LeRobot 形式へのデータ変換機構（[dataset.md](dataset.ja.md)）
- タイムスタンプ同期およびフレーム欠落を検出する品質バリデータ
- GitHub Actions による継続的インテグレーション（[ci.md](ci.ja.md)）
- `configs/contract.yaml` による入出力仕様の厳密な管理

### 3. レポート資料における論述方針

講義方針に基づき、ハードウェアのトラブルや動作の失敗が発生した場合でも、その原因分析、運用上の反省点、および技術的考察を詳述することで評価対象となる。

- 第5章: 定量評価をシミュレーションまたは公開データの結果へ差し替え、Plan B による縮退検証である旨を明記する。
- 第6章: 機材未着または故障の状況、代替手法の選定理由、および得られた知見を技術的に整理する。
- 第8章: 成果発表動画では、シミュレーション画面と RobOps（Rerun による軌道表示や CI ログ）を組み合わせる。

レポート原稿の雛形: [`report/説明資料_PAI最終課題_yohei1126.md`](../report/説明資料_PAI最終課題_yohei1126.ja.md)

## 関連文書

- 成果物提出の全体要件: [submission.md](submission.ja.md)
- 整列精度の評価 API 仕様: [evaluation.md](evaluation.ja.md)

