"""Alignment / grasp evaluation for pick-and-align trials.

Records position offset (mm), yaw error (deg), and grasp success.
Simulators and real sensors feed measured values into this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

# Default thresholds for derived align_success (mm / deg).
DEFAULT_ALIGN_POS_MM = 25.0
DEFAULT_ALIGN_YAW_DEG = 15.0
DEFAULT_GRASP_LIFT_M = 0.02


@dataclass(frozen=True)
class AlignmentSample:
    """One trial of pick-and-align against a target frame.

    ``grasp_success`` stays the legacy broad flag (lifted, ever attached, or
    already near the pad). ``holding_at_end`` and ``released_on_pad`` split that
    flag so a mid-episode attach is not reported as a finished transport.
    """

    position_error_mm: float
    yaw_error_deg: float
    grasp_success: bool
    holding_at_end: bool = False
    released_on_pad: bool = False


def record_sample(
    position_error_mm: float,
    yaw_error_deg: float,
    grasp_success: bool,
    *,
    holding_at_end: bool = False,
    released_on_pad: bool = False,
) -> AlignmentSample:
    """Create an immutable sample from measured (or placeholder) metrics."""
    return AlignmentSample(
        position_error_mm=float(position_error_mm),
        yaw_error_deg=float(yaw_error_deg),
        grasp_success=bool(grasp_success),
        holding_at_end=bool(holding_at_end),
        released_on_pad=bool(released_on_pad),
    )


def trial_outcome(
    *,
    position_error_mm: float,
    yaw_error_deg: float,
    grasping_now: bool,
    grasped_during: bool,
    box_z: float,
    table_z: float,
    ee_xy: Sequence[float] | np.ndarray | None = None,
    box_xy: Sequence[float] | np.ndarray | None = None,
    near_pad_mm: float = 50.0,
) -> AlignmentSample:
    """Score one finished episode.

    ``holding_at_end`` is the sticky grasp at the last step. ``released_on_pad``
    is a release whose planar error is inside the align position threshold.
    """
    pose_grasp = infer_grasp_success(
        box_z=box_z,
        table_z=table_z,
        ee_xy=ee_xy,
        box_xy=box_xy,
    )
    near_target = float(position_error_mm) < float(near_pad_mm)
    grasp_success = bool(pose_grasp or grasped_during or near_target)
    holding = bool(grasping_now)
    released = (not holding) and float(position_error_mm) <= DEFAULT_ALIGN_POS_MM
    return record_sample(
        position_error_mm,
        yaw_error_deg,
        grasp_success,
        holding_at_end=holding,
        released_on_pad=released,
    )


def compute_pose_errors(
    box_xy: Sequence[float] | np.ndarray,
    box_yaw: float,
    target_xy: Sequence[float] | np.ndarray,
    target_yaw: float,
) -> tuple[float, float]:
    """Return (position_error_mm, yaw_error_deg) from planar poses.

    ``yaw_error_deg`` is signed and wrapped to ``(-180, 180]``.
    """
    bx = np.asarray(box_xy, dtype=np.float64).reshape(-1)
    tx = np.asarray(target_xy, dtype=np.float64).reshape(-1)
    if bx.shape[0] < 2 or tx.shape[0] < 2:
        raise ValueError("box_xy and target_xy must have at least 2 elements")
    pos_m = float(np.linalg.norm(bx[:2] - tx[:2]))
    yaw_err = float(box_yaw) - float(target_yaw)
    # Wrap to (-pi, pi]
    yaw_err = (yaw_err + np.pi) % (2.0 * np.pi) - np.pi
    return pos_m * 1000.0, float(np.degrees(yaw_err))


def infer_grasp_success(
    *,
    box_z: float,
    table_z: float,
    ee_xy: Sequence[float] | np.ndarray | None = None,
    box_xy: Sequence[float] | np.ndarray | None = None,
    lift_threshold_m: float = DEFAULT_GRASP_LIFT_M,
    ee_proximity_m: float = 0.08,
) -> bool:
    """Heuristic grasp success from box height (and optional EE proximity)."""
    lifted = float(box_z) >= float(table_z) + float(lift_threshold_m)
    if not lifted:
        return False
    if ee_xy is None or box_xy is None:
        return True
    ee = np.asarray(ee_xy, dtype=np.float64).reshape(-1)[:2]
    box = np.asarray(box_xy, dtype=np.float64).reshape(-1)[:2]
    return float(np.linalg.norm(ee - box)) <= float(ee_proximity_m)


def is_align_success(
    position_error_mm: float,
    yaw_error_deg: float,
    *,
    pos_thresh_mm: float = DEFAULT_ALIGN_POS_MM,
    yaw_thresh_deg: float = DEFAULT_ALIGN_YAW_DEG,
) -> bool:
    """True when planar pose is within alignment thresholds."""
    return abs(float(position_error_mm)) <= float(pos_thresh_mm) and abs(
        float(yaw_error_deg)
    ) <= float(yaw_thresh_deg)


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
        "holding_at_end_rate": 0.0,
        "n_holding_at_end": 0,
        "released_on_pad_rate": 0.0,
        "n_released_on_pad": 0,
        "align_success_rate": 0.0,
        "n_align_success": 0,
    }


def summarize(
    samples: Sequence[AlignmentSample],
    *,
    pos_thresh_mm: float = DEFAULT_ALIGN_POS_MM,
    yaw_thresh_deg: float = DEFAULT_ALIGN_YAW_DEG,
) -> dict[str, Any]:
    """Aggregate samples into mean/std errors and success rates."""
    if not samples:
        return empty_summary()

    positions = [s.position_error_mm for s in samples]
    abs_yaws = [abs(s.yaw_error_deg) for s in samples]
    successes = [1.0 if s.grasp_success else 0.0 for s in samples]
    holdings = [1.0 if s.holding_at_end else 0.0 for s in samples]
    releases = [1.0 if s.released_on_pad else 0.0 for s in samples]
    aligns = [
        1.0
        if is_align_success(
            s.position_error_mm,
            s.yaw_error_deg,
            pos_thresh_mm=pos_thresh_mm,
            yaw_thresh_deg=yaw_thresh_deg,
        )
        else 0.0
        for s in samples
    ]
    n = len(samples)
    n_ok = int(sum(successes))
    n_holding = int(sum(holdings))
    n_released = int(sum(releases))
    n_align = int(sum(aligns))

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
        "holding_at_end_rate": n_holding / n,
        "n_holding_at_end": n_holding,
        "released_on_pad_rate": n_released / n,
        "n_released_on_pad": n_released,
        "align_success_rate": n_align / n,
        "n_align_success": n_align,
    }


def samples_to_dicts(samples: Sequence[AlignmentSample]) -> list[dict[str, Any]]:
    """Serialize samples for JSON / CSV export."""
    return [asdict(s) for s in samples]
