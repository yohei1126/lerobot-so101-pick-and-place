"""Alignment / grasp evaluation stubs (Task 4).

Defines the recording and aggregation interface for position offset (mm),
yaw error (deg), and grasp success. Real sensor / vision measurement is
wired in later tasks; this module only provides the data shapes and summary.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AlignmentSample:
    """One trial of pick-and-align against a target frame."""

    position_error_mm: float
    yaw_error_deg: float
    grasp_success: bool


def record_sample(
    position_error_mm: float,
    yaw_error_deg: float,
    grasp_success: bool,
) -> AlignmentSample:
    """Create an immutable sample from measured (or placeholder) metrics."""
    return AlignmentSample(
        position_error_mm=float(position_error_mm),
        yaw_error_deg=float(yaw_error_deg),
        grasp_success=bool(grasp_success),
    )


def empty_summary() -> dict[str, Any]:
    """Return an empty aggregate with stable keys for reporting / CI."""
    return {
        "n_samples": 0,
        "mean_position_error_mm": 0.0,
        "std_position_error_mm": 0.0,
        "mean_abs_yaw_error_deg": 0.0,
        "std_abs_yaw_error_deg": 0.0,
        "grasp_success_rate": 0.0,
        "n_grasp_success": 0,
    }


def summarize(samples: Sequence[AlignmentSample]) -> dict[str, Any]:
    """Aggregate samples into mean/std errors and grasp success rate."""
    if not samples:
        return empty_summary()

    positions = [s.position_error_mm for s in samples]
    abs_yaws = [abs(s.yaw_error_deg) for s in samples]
    successes = [1.0 if s.grasp_success else 0.0 for s in samples]
    n = len(samples)
    n_ok = int(sum(successes))

    mean_pos = sum(positions) / n
    mean_yaw = sum(abs_yaws) / n
    if n == 1:
        std_pos = 0.0
        std_yaw = 0.0
    else:
        std_pos = (sum((p - mean_pos) ** 2 for p in positions) / (n - 1)) ** 0.5
        std_yaw = (sum((y - mean_yaw) ** 2 for y in abs_yaws) / (n - 1)) ** 0.5

    return {
        "n_samples": n,
        "mean_position_error_mm": mean_pos,
        "std_position_error_mm": std_pos,
        "mean_abs_yaw_error_deg": mean_yaw,
        "std_abs_yaw_error_deg": std_yaw,
        "grasp_success_rate": n_ok / n,
        "n_grasp_success": n_ok,
    }


def samples_to_dicts(samples: Sequence[AlignmentSample]) -> list[dict[str, Any]]:
    """Serialize samples for JSON / CSV export."""
    return [asdict(s) for s in samples]
