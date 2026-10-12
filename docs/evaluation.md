# 整列評価（eval_alignment）

把持・整列タスクの位置誤差（mm）、yaw 誤差（deg）、成功率を記録・集計する。

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[dev]"

(cd port_pick_align && pytest -m unit tests/test_eval_alignment.py -q)
```

## API

```python
from port_pick_align.evaluation.eval_alignment import (
    record_sample,
    summarize,
    compute_pose_errors,
    samples_to_dicts,
)

sample = record_sample(
    position_error_mm=12.0,
    yaw_error_deg=-3.5,
    grasp_success=True,
)
summary = summarize([sample])
# summary["mean_position_error_mm"], ["grasp_success_rate"], ["align_success_rate"], ...
```

シミュレータからの測定は [simulation.md](simulation.md) の閉ループ評価が `eval_alignment` を呼び出す。

主な成果物:

- `port_pick_align/src/port_pick_align/evaluation/eval_alignment.py`
