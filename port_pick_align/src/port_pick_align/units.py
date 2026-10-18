"""Joint / gripper unit conversions between sim contract and LeRobot SO-101.

Sim and ``configs/contract.yaml`` store all six joint commands/states in
**radians**. Real LeRobot SO-101 follower recordings commonly use **degrees**
for the five arm joints and a **0–100** open-percent scale for the gripper.

This module is the SSOT for those conversions so report text and real-robot
adapters stay aligned with the code.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

# Contract gripper limits (radians). Comments in contract.yaml map these to
# approximately -10 deg .. 100 deg of Feetech travel.
GRIPPER_RAD_MIN = -0.1745
GRIPPER_RAD_MAX = 1.7453

# Scripted / env convention inside this repo (still radians, not 0–100).
SCRIPTED_GRIPPER_CLOSED_RAD = 0.0
SCRIPTED_GRIPPER_OPEN_RAD = 1.2

# MuJoCo sticky-grasp thresholds (radians). See simulation/env.py.
GRIPPER_CLOSE_THRESH_RAD = 0.45
GRIPPER_OPEN_THRESH_RAD = 0.90


def rad_to_deg(rad: float | np.ndarray) -> float | np.ndarray:
    """Convert radians to degrees (scalar or ndarray)."""
    if isinstance(rad, np.ndarray):
        return np.asarray(np.degrees(rad), dtype=np.float64)
    return float(math.degrees(float(rad)))


def deg_to_rad(deg: float | np.ndarray) -> float | np.ndarray:
    """Convert degrees to radians (scalar or ndarray)."""
    if isinstance(deg, np.ndarray):
        return np.asarray(np.radians(deg), dtype=np.float64)
    return float(math.radians(float(deg)))


def joints_rad_to_deg(joints_rad: Sequence[float] | np.ndarray) -> np.ndarray:
    """Convert a 6-D joint vector from radians to degrees (all channels)."""
    arr = np.asarray(joints_rad, dtype=np.float64).reshape(-1)
    return np.asarray(np.degrees(arr), dtype=np.float64)


def joints_deg_to_rad(joints_deg: Sequence[float] | np.ndarray) -> np.ndarray:
    """Convert a 6-D joint vector from degrees to radians (all channels)."""
    arr = np.asarray(joints_deg, dtype=np.float64).reshape(-1)
    return np.asarray(np.radians(arr), dtype=np.float64)


def gripper_rad_to_percent(
    rad: float,
    *,
    rad_min: float = GRIPPER_RAD_MIN,
    rad_max: float = GRIPPER_RAD_MAX,
) -> float:
    """Map contract/sim gripper radians onto LeRobot-style 0–100 open percent.

    ``0`` is fully closed at ``rad_min``, ``100`` is fully open at ``rad_max``.
    Values outside the interval are not clipped so callers can detect overflow.
    """
    span = float(rad_max) - float(rad_min)
    if span <= 0.0:
        raise ValueError("rad_max must be greater than rad_min")
    return 100.0 * (float(rad) - float(rad_min)) / span


def gripper_percent_to_rad(
    percent: float,
    *,
    rad_min: float = GRIPPER_RAD_MIN,
    rad_max: float = GRIPPER_RAD_MAX,
) -> float:
    """Inverse of :func:`gripper_rad_to_percent`."""
    span = float(rad_max) - float(rad_min)
    if span <= 0.0:
        raise ValueError("rad_max must be greater than rad_min")
    return float(rad_min) + (float(percent) / 100.0) * span


def gripper_limits_from_contract(contract: Mapping[str, Any]) -> tuple[float, float]:
    """Return ``(rad_min, rad_max)`` from a loaded contract dict."""
    limits = contract["robot"]["joint_limits"]["gripper"]
    lo, hi = float(limits[0]), float(limits[1])
    if hi <= lo:
        raise ValueError(f"invalid gripper limits: {limits!r}")
    return lo, hi


def describe_unit_conventions() -> dict[str, Any]:
    """Machine-readable unit notes for docs / report paste-in."""
    return {
        "sim_and_contract_joints": "radians",
        "sim_gripper": "radians (same channel as other joints)",
        "scripted_gripper_closed_rad": SCRIPTED_GRIPPER_CLOSED_RAD,
        "scripted_gripper_open_rad": SCRIPTED_GRIPPER_OPEN_RAD,
        "env_gripper_close_thresh_rad": GRIPPER_CLOSE_THRESH_RAD,
        "env_gripper_open_thresh_rad": GRIPPER_OPEN_THRESH_RAD,
        "contract_gripper_rad_min": GRIPPER_RAD_MIN,
        "contract_gripper_rad_max": GRIPPER_RAD_MAX,
        "contract_gripper_deg_comment": [-10.0, 100.0],
        "real_lerobot_so101_arm_joints": "degrees (typical)",
        "real_lerobot_so101_gripper": "0-100 open percent (typical)",
        "yaw_error_in_metrics": "degrees (signed; summary uses abs mean)",
        "box_yaw_in_sim_info": "radians",
        "conversion_helpers": [
            "rad_to_deg",
            "deg_to_rad",
            "joints_rad_to_deg",
            "joints_deg_to_rad",
            "gripper_rad_to_percent",
            "gripper_percent_to_rad",
        ],
    }
