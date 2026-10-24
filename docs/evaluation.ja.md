# 整列精度評価 API 仕様（eval_alignment）

本資料では、直方体の把持・精密整列タスクにおける平面位置誤差（mm）、ヨー角誤差（deg）、ならびにタスク成功率を記録・集計するための評価モジュールの仕様を解説する。

## テストの実行

ホスト仮想環境において、評価モジュールの単体テストを実行する。

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[dev]"

(cd port_pick_align && pytest -m unit tests/test_eval_alignment.py -q)
```

## Python API の利用方法

本モジュールは、各試行の計測誤差を記録する `record_sample` と、複数エピソードの統計量を集計する `summarize` を提供する。

```python
from port_pick_align.evaluation.eval_alignment import (
    record_sample,
    summarize,
    compute_pose_errors,
    samples_to_dicts,
)

# 1試行の計測結果を記録
sample = record_sample(
    position_error_mm=12.0,
    yaw_error_deg=-3.5,
    grasp_success=True,
)

# 複数試行のサマリーを集計
summary = summarize([sample])
# 取得可能なメトリクス:
# - summary["mean_position_error_mm"]: 平均平面位置誤差
# - summary["median_position_error_mm"]: 中央値平面位置誤差
# - summary["mean_abs_yaw_error_deg"]: 平均絶対ヨー角誤差（度）
# - summary["median_abs_yaw_error_deg"]: 中央値絶対ヨー角誤差（度）
# - summary["grasp_success_rate"]: 把持成功率（エピソード中の付着を含む広いフラグ）
# - summary["holding_at_end_rate"]: 終了時にまだ把持している割合
# - summary["released_on_pad_rate"]: パッド上で解放できている割合（位置 ≤ 25 mm かつ非把持）
# - summary["align_success_rate"]: 許容閾値（位置 ≤ 25 mm、ヨー角 ≤ 15 deg）に基づく整列成功率
```

`scripts/run_sim_eval.py` は終了時に `mean_abs_yaw_error_deg`（および位置の平均・中央値）を 1 行で表示し、同じ値を `metrics.json` の `summary` に書く。

シミュレータからの自動計測では、[simulation.md](simulation.ja.md) で解説する閉ループ評価スクリプト（`run_sim_eval.py`）から本モジュールが呼び出され、`outputs/eval/metrics.json` に結果が出力される。Phase 1.5 の ACT 本評価は `./scripts/run_phase15_benchmark.sh` が chunk30 の結果を `outputs/eval_sim_act/metrics.json` に書く。Temporal Ensembling は `outputs/eval_sim_act_te/metrics.json` の別指標である。post50 の公式集計は [results/post50_official_summary.json](results/post50_official_summary.json) を参照する。既定パス向けの未ピン留め案内は [results/eval_sim_act.pending.json](results/eval_sim_act.pending.json) である。

関節ラジアン／度、グリッパ 0–100 の換算は [units.md](units.ja.md) と `port_pick_align.units` を参照する。

実装ファイル: [`port_pick_align/src/port_pick_align/evaluation/eval_alignment.py`](../port_pick_align/src/port_pick_align/evaluation/eval_alignment.py)

