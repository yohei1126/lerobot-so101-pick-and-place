"""Unit tests for alignment evaluation."""

from __future__ import annotations

import math

import numpy as np
import pytest

from port_pick_align.evaluation.eval_alignment import (
    compute_pose_errors,
    empty_summary,
    infer_grasp_success,
    is_align_success,
    record_sample,
    samples_to_dicts,
    summarize,
)


@pytest.mark.unit
def test_empty_summary_keys() -> None:
    summary = empty_summary()
    assert summary["n_samples"] == 0
    assert summary["grasp_success_rate"] == 0.0
    assert summary["align_success_rate"] == 0.0
    assert "mean_position_error_mm" in summary
    assert "mean_abs_yaw_error_deg" in summary


@pytest.mark.unit
def test_summarize_success_rate_and_means() -> None:
    samples = [
        record_sample(10.0, 5.0, True),
        record_sample(20.0, -15.0, False),
        record_sample(30.0, 10.0, True),
    ]
    summary = summarize(samples)
    assert summary["n_samples"] == 3
    assert summary["n_grasp_success"] == 2
    assert summary["grasp_success_rate"] == pytest.approx(2 / 3)
    assert summary["mean_position_error_mm"] == pytest.approx(20.0)
    assert summary["mean_abs_yaw_error_deg"] == pytest.approx(10.0)
    assert summary["std_position_error_mm"] == pytest.approx(10.0)
    # 10mm/5deg and 20mm/15deg and 30mm/10deg with defaults 25mm/15deg → 2 align
    assert summary["n_align_success"] == 2
    assert summary["align_success_rate"] == pytest.approx(2 / 3)


@pytest.mark.unit
def test_samples_to_dicts() -> None:
    sample = record_sample(1.5, -2.0, True)
    rows = samples_to_dicts([sample])
    assert rows == [{"position_error_mm": 1.5, "yaw_error_deg": -2.0, "grasp_success": True}]


@pytest.mark.unit
def test_compute_pose_errors() -> None:
    pos_mm, yaw_deg = compute_pose_errors([0.0, 0.0], 0.0, [0.01, 0.0], 0.0)
    assert pos_mm == pytest.approx(10.0)
    assert yaw_deg == pytest.approx(0.0)
    _, yaw_deg = compute_pose_errors([0, 0], math.pi / 2, [0, 0], 0.0)
    assert yaw_deg == pytest.approx(90.0)


@pytest.mark.unit
def test_infer_grasp_and_align() -> None:
    assert infer_grasp_success(box_z=0.5, table_z=0.42)
    assert not infer_grasp_success(box_z=0.42, table_z=0.42)
    assert is_align_success(10.0, 5.0)
    assert not is_align_success(40.0, 5.0)
    assert infer_grasp_success(
        box_z=0.5,
        table_z=0.42,
        ee_xy=np.array([0.0, 0.0]),
        box_xy=np.array([0.05, 0.0]),
    )
