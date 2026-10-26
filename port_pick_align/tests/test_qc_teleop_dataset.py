"""Unit tests for scripts/qc_teleop_dataset.py (no dataset, no arm)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "qc_teleop_dataset.py"

_SPEC = importlib.util.spec_from_file_location("qc_teleop_dataset", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
qc = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = qc
_SPEC.loader.exec_module(qc)

NAMES = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]


def _score(action: np.ndarray, state: np.ndarray | None = None, **kwargs: float) -> object:
    thresholds = qc.QcThresholds(**kwargs)
    return qc.qc_episode(
        action,
        action if state is None else state,
        joint_names=NAMES,
        fps=30.0,
        thresholds=thresholds,
        dataset="toy",
        episode_index=0,
    )


@pytest.mark.unit
def test_short_opening_pause_stays_unflagged() -> None:
    frames = 90
    action = np.zeros((frames, 6), dtype=np.float64)
    action[20:, 1] = 40.0
    action[20:, 2] = np.linspace(0.0, 30.0, frames - 20)
    state = action.copy()
    state[:, 1] = action[:, 1] - 1.5
    row = _score(action, state)
    assert row.head_idle_frames == 20
    assert row.head_idle_s == pytest.approx(20 / 30)
    assert row.frames_to_first_motion == 20
    assert row.flags == ()
    assert row.severity == "ok"
    assert row.lag_shoulder_lift_deg == pytest.approx(1.5)


@pytest.mark.unit
def test_head_idle_uses_strict_greater_than_two_seconds() -> None:
    def episode(idle_frames: int) -> object:
        frames = idle_frames + 40
        action = np.zeros((frames, 6), dtype=np.float64)
        action[idle_frames:, 1] = np.linspace(10.0, 80.0, frames - idle_frames)
        action[idle_frames:, 2] = np.linspace(5.0, 40.0, frames - idle_frames)
        return _score(action)

    at_two = episode(60)
    assert at_two.head_idle_s == pytest.approx(2.0)
    assert qc.LONG_HEAD_IDLE not in at_two.flags
    over = episode(61)
    assert over.head_idle_s == pytest.approx(61 / 30)
    assert over.flags == (qc.LONG_HEAD_IDLE,)
    assert over.severity == "warn"


@pytest.mark.unit
def test_static_episode_is_low_motion_and_long_head() -> None:
    action = np.zeros((90, 6), dtype=np.float64)
    row = _score(action)
    assert row.frames_to_first_motion is None
    assert row.head_idle_frames == 90
    assert row.flags == (qc.LOW_MOTION, qc.LONG_HEAD_IDLE)
    assert row.severity == "high"


@pytest.mark.unit
def test_gripper_motion_does_not_count_as_arm_motion() -> None:
    frames = 90
    action = np.zeros((frames, 6), dtype=np.float64)
    action[:, 5] = np.linspace(0.0, 80.0, frames)
    row = _score(action)
    assert qc.LOW_MOTION in row.flags
    assert row.frames_to_first_motion is None


@pytest.mark.unit
def test_shoulder_lift_lag_is_high() -> None:
    frames = 60
    action = np.zeros((frames, 6), dtype=np.float64)
    action[:, 1] = np.linspace(-20.0, 60.0, frames)
    action[:, 2] = np.linspace(0.0, 40.0, frames)
    state = action.copy()
    state[:, 1] = action[:, 1] - 8.9
    row = _score(action, state)
    assert row.flags == (qc.HIGH_LAG,)
    assert row.severity == "high"
    assert row.max_lag_joint == "shoulder_lift(dim1)"
    assert row.lag_shoulder_lift_deg == pytest.approx(8.9, abs=1e-6)
    assert qc.LONG_HEAD_IDLE not in row.flags


@pytest.mark.unit
def test_missing_root_does_not_create_a_dataset(tmp_path: Path) -> None:
    missing = tmp_path / "not_a_dataset"
    code = qc.main(["--root", str(missing), "--out", str(tmp_path / "qc.md"), "--format", "md"])
    assert code == 1
    assert not missing.exists()
    assert not (tmp_path / "qc.md").exists()


@pytest.mark.unit
def test_markdown_lists_high_lag() -> None:
    frames = 30
    action = np.zeros((frames, 6), dtype=np.float64)
    action[:, 1] = np.linspace(0.0, 50.0, frames)
    action[:, 2] = np.linspace(0.0, 20.0, frames)
    state = action.copy()
    state[:, 1] = action[:, 1] - 9.0
    row = _score(action, state)
    text = qc.render_markdown([row], qc.QcThresholds(), [Path("/tmp/toy")])
    assert "HIGH_LAG" in text
    assert "shoulder_lift(dim1)" in text
    assert "No high-severity flags." not in text
