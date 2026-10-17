"""Per-episode initial pose fields in run_sim_eval metrics.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

EPISODE_KEYS = (
    "initial_box_xy",
    "initial_box_yaw",
    "seed",
    "final_box_yaw",
    "yaw_err_deg",
)


@pytest.mark.simulation
@pytest.mark.unit
def test_run_sim_eval_metrics_include_initial_pose(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    import run_sim_eval

    out_dir = tmp_path / "eval"
    rc = run_sim_eval.main(
        [
            "--policy",
            "mock",
            "--episodes",
            "3",
            "--max-steps",
            "4",
            "--seed",
            "1000",
            "--randomize-box",
            "--no-save-video",
            "--no-rerun",
            "--output-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    metrics_path = out_dir / "metrics.json"
    assert metrics_path.is_file()
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    samples = payload["samples"]
    assert len(samples) == 3
    for i, sample in enumerate(samples):
        for key in EPISODE_KEYS:
            assert key in sample, f"missing {key} in episode {i}"
        assert sample["seed"] == 1000 + i
        assert isinstance(sample["initial_box_xy"], list)
        assert len(sample["initial_box_xy"]) == 2
        assert isinstance(sample["initial_box_yaw"], float)
        assert isinstance(sample["final_box_yaw"], float)
        assert sample["yaw_err_deg"] == sample["yaw_error_deg"]

    xy_tuples = [tuple(s["initial_box_xy"]) for s in samples]
    assert len(set(xy_tuples)) >= 2, (
        f"expected randomized initial_box_xy to differ across episodes, got {xy_tuples}"
    )


@pytest.mark.unit
def test_run_pipeline_summary_mentions_initial_box_xy_spread() -> None:
    text = (REPO_ROOT / "scripts" / "run_pipeline.sh").read_text(encoding="utf-8")
    assert "Initial box XY spread" in text
    assert "initial_box_xy" in text
    assert "unique=" in text
