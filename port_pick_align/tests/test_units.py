"""Unit tests for joint / gripper unit conversions."""

from __future__ import annotations

import math

import numpy as np
import pytest

from port_pick_align.units import (
    GRIPPER_RAD_MAX,
    GRIPPER_RAD_MIN,
    SCRIPTED_GRIPPER_CLOSED_RAD,
    SCRIPTED_GRIPPER_OPEN_RAD,
    deg_to_rad,
    describe_unit_conventions,
    gripper_percent_to_rad,
    gripper_rad_to_percent,
    joints_deg_to_rad,
    joints_rad_to_deg,
    rad_to_deg,
)


@pytest.mark.unit
def test_rad_deg_roundtrip() -> None:
    assert rad_to_deg(math.pi) == pytest.approx(180.0)
    assert deg_to_rad(90.0) == pytest.approx(math.pi / 2)
    vec = np.array([0.0, math.pi / 2, -math.pi], dtype=np.float64)
    assert joints_rad_to_deg(vec) == pytest.approx(np.array([0.0, 90.0, -180.0]))
    assert joints_deg_to_rad([0.0, 90.0, -180.0]) == pytest.approx(vec)


@pytest.mark.unit
def test_gripper_0_100_maps_contract_limits() -> None:
    assert gripper_rad_to_percent(GRIPPER_RAD_MIN) == pytest.approx(0.0)
    assert gripper_rad_to_percent(GRIPPER_RAD_MAX) == pytest.approx(100.0)
    mid = 0.5 * (GRIPPER_RAD_MIN + GRIPPER_RAD_MAX)
    assert gripper_rad_to_percent(mid) == pytest.approx(50.0)
    assert gripper_percent_to_rad(0.0) == pytest.approx(GRIPPER_RAD_MIN)
    assert gripper_percent_to_rad(100.0) == pytest.approx(GRIPPER_RAD_MAX)
    assert gripper_percent_to_rad(gripper_rad_to_percent(1.2)) == pytest.approx(1.2)


@pytest.mark.unit
def test_scripted_gripper_stays_in_rad_not_percent() -> None:
    # Scripted policy uses ~0.0 closed / ~1.2 open in radians — not 0–100.
    assert SCRIPTED_GRIPPER_CLOSED_RAD == pytest.approx(0.0)
    assert SCRIPTED_GRIPPER_OPEN_RAD == pytest.approx(1.2)
    closed_pct = gripper_rad_to_percent(SCRIPTED_GRIPPER_CLOSED_RAD)
    open_pct = gripper_rad_to_percent(SCRIPTED_GRIPPER_OPEN_RAD)
    assert 0.0 < closed_pct < 20.0
    assert 60.0 < open_pct < 90.0


@pytest.mark.unit
def test_describe_unit_conventions_keys() -> None:
    info = describe_unit_conventions()
    assert info["sim_and_contract_joints"] == "radians"
    assert info["real_lerobot_so101_gripper"] == "0-100 open percent (typical)"
    assert "gripper_rad_to_percent" in info["conversion_helpers"]
