# Plan B: ハード未着・故障時の縮退運用

実機本線（Plan A: SO-ARM101 + 日常品モック）が使えない場合でも、修了合格（および考察による加点）を死守する手順。

## 判定ゲート

**2026-10-23（金）時点**でハードウェアが正常稼働しない場合は Plan B に切り替える。

```text
HW OK? ──Yes──▶ Plan A（実機把持・整列 + 動画）
       └─No───▶ Plan B（公開データ / シミュ + RobOps 前面）
```

## Plan B の構成

### 1. データとタスク実行

次のいずれか（または併用）でタスク実行デモを用意する。

| 経路 | 内容 | 本リポでの入口 |
| --- | --- | --- |
| MuJoCo シミュ | 卓上把持・整列の閉ループ評価 | [simulation.md](simulation.md)（`outputs/eval/sim_rollout.mp4`） |
| LeRobot 公開データ | SO-100 など公開データセットで学習・推論 | [training.md](training.md) / [dataset.md](dataset.md) |

例（MuJoCo ロールアウト動画）:

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,dev]"
python scripts/run_sim_eval.py --policy scripted --save-video --no-rerun
# → outputs/eval/sim_rollout.mp4
```

### 2. RobOps を主軸にアピール

実機がなくても、次は契約どおり動作する想定。レポート・動画で前面に出す。

- rosbag2 → LeRobot 変換（[dataset.md](dataset.md)）
- validator（時刻同期・フレームドロップ等）
- GitHub Actions CI（[ci.md](ci.md)）
- 契約 SSOT: `configs/contract.yaml`

### 3. レポートでの扱い

公式方針どおり、ハードトラブルや失敗でも **原因・反省・技術的考察** を書けば評価対象になりうる。

- 第5章: シミュ / 公開データでの定量評価に差し替え、Plan B である旨を明記
- 第6章: ハード未着・故障・代替経路の選定理由と学びを詳述
- 第8章: 動画はシミュ画面 + RobOps（Rerun / CI）構成でも可

原稿雛形: [`report/説明資料_PAI最終課題_yohei1126.md`](../report/説明資料_PAI最終課題_yohei1126.md)

## 関連

- 提出全体: [submission.md](submission.md)
- 評価 API: [evaluation.md](evaluation.md)
