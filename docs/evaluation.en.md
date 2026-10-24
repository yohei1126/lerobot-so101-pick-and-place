# Alignment evaluation API (`eval_alignment`)

`eval_alignment` records and aggregates planar position error (mm), yaw error (deg), and task success rate for the box grasp-and-precise-alignment task.

## `test_eval_alignment` tests

In the host virtualenv, run the evaluation module unit tests:

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[dev]"

(cd port_pick_align && pytest -m unit tests/test_eval_alignment.py -q)
```

## Python API usage

The module provides `record_sample` to log per-trial measurement errors and `summarize` to aggregate statistics across episodes.

```python
from port_pick_align.evaluation.eval_alignment import (
    record_sample,
    summarize,
    compute_pose_errors,
    samples_to_dicts,
)

# Record one trial measurement
sample = record_sample(
    position_error_mm=12.0,
    yaw_error_deg=-3.5,
    grasp_success=True,
)

# Aggregate a summary over trials
summary = summarize([sample])
# Available metrics:
# - summary["mean_position_error_mm"]: mean planar position error
# - summary["median_position_error_mm"]: median planar position error
# - summary["mean_abs_yaw_error_deg"]: mean absolute yaw error (degrees)
# - summary["median_abs_yaw_error_deg"]: median absolute yaw error (degrees)
# - summary["grasp_success_rate"]: grasp success rate (broad flag including attachment during the episode)
# - summary["holding_at_end_rate"]: fraction still grasping at episode end
# - summary["released_on_pad_rate"]: fraction released on the pad (position ≤ 25 mm and not grasping)
# - summary["align_success_rate"]: alignment success under thresholds (position ≤ 25 mm, yaw ≤ 15 deg)
```

`scripts/run_sim_eval.py` prints `mean_abs_yaw_error_deg` (and position mean/median) on one line at exit, and writes the same values into `metrics.json` under `summary`.

For automatic measurement from the simulator, the closed-loop evaluation script (`run_sim_eval.py`) described in [simulation.md](simulation.en.md) calls this module and writes results to `outputs/eval/metrics.json`. Phase 1.5 ACT main evaluation via `./scripts/run_phase15_benchmark.sh` writes chunk30 results to `outputs/eval_sim_act/metrics.json`. Temporal Ensembling is a separate metric at `outputs/eval_sim_act_te/metrics.json`. For the post50 official aggregate, see [results/post50_official_summary.json](results/post50_official_summary.json). Unpinned guidance for the default path is [results/eval_sim_act.pending.json](results/eval_sim_act.pending.json).

For joint radian/degree and gripper 0–100 conversion, see [units.md](units.en.md) and `port_pick_align.units`.

Implementation: [`port_pick_align/src/port_pick_align/evaluation/eval_alignment.py`](../port_pick_align/src/port_pick_align/evaluation/eval_alignment.py)
