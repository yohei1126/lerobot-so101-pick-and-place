"""CPU-only unit tests for sim↔real ACT conversion (no hardware)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from port_pick_align.contract import load_contract
from port_pick_align.deploy.conversion import (
    JOINT_NAMES,
    REAL_MOTOR_KEYS,
    SimToRealConversionConfig,
    apply_max_delta_real,
    clamp_sim_joints,
    conversion_config_from_contract,
    extract_real_joint_vector,
    image_to_chw_float,
    map_real_cameras,
    real_action_dict,
    real_gripper_percent_to_sim_rad,
    real_joints_to_sim_state,
    resize_image_hwc,
    sim_action_to_real_joints,
    sim_gripper_rad_to_real_percent,
    sim_state_to_real_joints,
)
from port_pick_align.units import GRIPPER_RAD_MAX, GRIPPER_RAD_MIN


@pytest.mark.unit
def test_joint_order_matches_contract() -> None:
    contract = load_contract()
    assert tuple(contract["robot"]["joint_names"]) == JOINT_NAMES
    assert REAL_MOTOR_KEYS == tuple(f"{n}.pos" for n in JOINT_NAMES)


@pytest.mark.unit
def test_arm_rad_deg_roundtrip() -> None:
    cfg = SimToRealConversionConfig(gripper_closed_is_high=True)
    sim = np.array([0.0, -0.6, 0.9, 0.6, 0.0, 1.2], dtype=np.float32)
    real = sim_state_to_real_joints(sim, cfg)
    assert real[:5] == pytest.approx(np.degrees(sim[:5]), rel=1e-5, abs=1e-5)
    back = real_joints_to_sim_state(real, cfg)
    assert back[:5] == pytest.approx(sim[:5], rel=1e-5, abs=1e-5)


@pytest.mark.unit
def test_gripper_lerobot_polarity_closed_is_high() -> None:
    # LeRobot discrete map: close → toward 100, open → toward 0.
    assert real_gripper_percent_to_sim_rad(0.0, closed_is_high=True) == pytest.approx(
        GRIPPER_RAD_MAX
    )
    assert real_gripper_percent_to_sim_rad(100.0, closed_is_high=True) == pytest.approx(
        GRIPPER_RAD_MIN
    )
    assert sim_gripper_rad_to_real_percent(GRIPPER_RAD_MAX, closed_is_high=True) == pytest.approx(
        0.0
    )
    assert sim_gripper_rad_to_real_percent(GRIPPER_RAD_MIN, closed_is_high=True) == pytest.approx(
        100.0
    )
    # Scripted open ~1.2 rad should be nearer open (low percent) than closed.
    open_pct = sim_gripper_rad_to_real_percent(1.2, closed_is_high=True)
    closed_pct = sim_gripper_rad_to_real_percent(0.0, closed_is_high=True)
    assert open_pct < 40.0
    assert closed_pct > 80.0


@pytest.mark.unit
def test_gripper_open_percent_polarity_roundtrip() -> None:
    # units.py sense: 0 closed / 100 open
    mid = 0.5 * (GRIPPER_RAD_MIN + GRIPPER_RAD_MAX)
    assert real_gripper_percent_to_sim_rad(50.0, closed_is_high=False) == pytest.approx(mid)
    assert sim_gripper_rad_to_real_percent(mid, closed_is_high=False) == pytest.approx(50.0)
    for pct in (0.0, 25.0, 100.0):
        rad = real_gripper_percent_to_sim_rad(pct, closed_is_high=False)
        assert sim_gripper_rad_to_real_percent(rad, closed_is_high=False) == pytest.approx(pct)


@pytest.mark.unit
def test_full_joint_vector_roundtrip_with_dict_keys() -> None:
    cfg = conversion_config_from_contract(load_contract(), gripper_closed_is_high=True)
    real = {
        "shoulder_pan.pos": 10.0,
        "shoulder_lift.pos": -30.0,
        "elbow_flex.pos": 45.0,
        "wrist_flex.pos": -5.0,
        "wrist_roll.pos": 2.0,
        "gripper.pos": 20.0,  # mostly open under LeRobot polarity
    }
    sim = real_joints_to_sim_state(real, cfg)
    assert sim[0] == pytest.approx(math.radians(10.0))
    back = sim_state_to_real_joints(sim, cfg)
    for i, key in enumerate(REAL_MOTOR_KEYS):
        assert float(back[i]) == pytest.approx(real[key], abs=1e-4)
    action = real_action_dict(back)
    assert set(action) == set(REAL_MOTOR_KEYS)


@pytest.mark.unit
def test_clamp_sim_joints_uses_contract_limits() -> None:
    cfg = conversion_config_from_contract(load_contract())
    huge = np.array([10.0, -10.0, 10.0, -10.0, 10.0, 10.0], dtype=np.float32)
    clipped = clamp_sim_joints(huge, cfg)
    limits = cfg.limits_array()
    assert limits is not None
    assert np.all(clipped >= limits[:, 0] - 1e-6)
    assert np.all(clipped <= limits[:, 1] + 1e-6)


@pytest.mark.unit
def test_apply_max_delta_limits_speed() -> None:
    cfg = SimToRealConversionConfig(max_delta_deg=5.0, max_delta_gripper=10.0)
    current = np.zeros(6, dtype=np.float32)
    target = np.array([20.0, -20.0, 0.0, 0.0, 0.0, 80.0], dtype=np.float32)
    stepped = apply_max_delta_real(target, current, cfg)
    assert stepped[0] == pytest.approx(5.0)
    assert stepped[1] == pytest.approx(-5.0)
    assert stepped[5] == pytest.approx(10.0)


@pytest.mark.unit
def test_sim_action_to_real_clamps_then_converts() -> None:
    cfg = conversion_config_from_contract(load_contract(), gripper_closed_is_high=True)
    # Way outside shoulder_pan limit (±1.9199 rad ≈ ±110 deg)
    action = np.array([3.0, 0.0, 0.0, 0.0, 0.0, 1.2], dtype=np.float32)
    real = sim_action_to_real_joints(action, cfg)
    # contract limit 1.9199 rad ≈ 110.002… deg
    assert abs(float(real[0])) <= math.degrees(1.9199) + 1e-3


@pytest.mark.unit
def test_camera_key_mapping_and_missing() -> None:
    cfg = conversion_config_from_contract(load_contract())
    obs = {
        "top": np.zeros((480, 640, 3), dtype=np.uint8),
        "wrist": np.ones((480, 640, 3), dtype=np.uint8),
    }
    mapped = map_real_cameras(obs, cfg.camera_map)
    assert set(mapped) == {"top", "wrist"}
    with pytest.raises(KeyError, match="top"):
        map_real_cameras({"wrist": obs["wrist"]}, cfg.camera_map)


@pytest.mark.unit
def test_resize_and_rgb_chw() -> None:
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    img[:, :, 0] = 255  # red in RGB
    resized = resize_image_hwc(img, 480, 640)
    assert resized.shape == (480, 640, 3)
    chw = image_to_chw_float(resized, source_color="rgb")
    assert chw.shape == (3, 480, 640)
    assert float(chw[0].mean()) == pytest.approx(1.0)
    assert float(chw[2].mean()) == pytest.approx(0.0)
    # BGR source with blue channel high → RGB channel 2 after conversion
    bgr = np.zeros((4, 4, 3), dtype=np.uint8)
    bgr[:, :, 0] = 255
    chw_bgr = image_to_chw_float(bgr, source_color="bgr")
    assert float(chw_bgr[2].mean()) == pytest.approx(1.0)


@pytest.mark.unit
def test_extract_real_joint_vector_order() -> None:
    obs = {f"{name}.pos": float(i) for i, name in enumerate(JOINT_NAMES)}
    vec = extract_real_joint_vector(obs)
    assert vec.tolist() == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
