"""Unit / key conversion between sim-trained ACT and real LeRobot SO-101.

Sim / ``configs/contract.yaml``
  - Joint order: shoulder_pan … gripper (6)
  - Units: radians for all six channels
  - Cameras: ``top``, ``wrist`` at contract resolution (default 640×480), RGB in
    LeRobot datasets (env renders BGR; collectors convert before storage)

Real LeRobot ``so101_follower`` (0.6.1, ``use_degrees=True``)
  - Feature keys: ``shoulder_pan.pos`` … ``gripper.pos`` (same order)
  - Arm joints: degrees
  - Gripper: 0–100 (``MotorNormMode.RANGE_0_100``)
  - Cameras: same names ``top`` / ``wrist`` in this project's bring-up
  - OpenCV camera default color: RGB

Gripper polarity (configurable)
  Default ``gripper_closed_is_high=True`` matches LeRobot's
  ``gripper_velocity_to_joint`` discrete map (close → toward 100, open → toward 0).
  Set ``False`` to use the older ``port_pick_align.units`` "open percent" sense
  (0 closed / 100 open).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from port_pick_align.units import GRIPPER_RAD_MAX, GRIPPER_RAD_MIN

JOINT_NAMES: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
REAL_MOTOR_KEYS: tuple[str, ...] = tuple(f"{name}.pos" for name in JOINT_NAMES)
ARM_JOINT_INDICES: tuple[int, ...] = (0, 1, 2, 3, 4)
GRIPPER_INDEX = 5

ColorMode = Literal["rgb", "bgr"]


def _default_camera_map() -> dict[str, str]:
    return {"top": "top", "wrist": "wrist"}


@dataclass(frozen=True)
class SimToRealConversionConfig:
    """Conversion and safety knobs for sim-checkpoint → real follower."""

    joint_names: tuple[str, ...] = JOINT_NAMES
    # LeRobot SO-101: higher gripper.pos → more closed (see module docstring).
    gripper_closed_is_high: bool = True
    gripper_rad_min: float = GRIPPER_RAD_MIN
    gripper_rad_max: float = GRIPPER_RAD_MAX
    # Per-joint sim limits in radians, shape (6, 2) as [lo, hi].
    joint_limits_rad: np.ndarray | None = None
    # Optional per-step caps in *real* units (deg for arm, 0–100 for gripper).
    max_delta_deg: float | None = 5.0
    max_delta_gripper: float | None = 10.0
    # Real camera key → sim policy camera key.
    camera_map: dict[str, str] = field(default_factory=_default_camera_map)
    # Policy image size (H, W); None keeps the source resolution.
    target_image_hw: tuple[int, int] | None = (480, 640)
    real_image_color: ColorMode = "rgb"

    def limits_array(self) -> np.ndarray | None:
        if self.joint_limits_rad is None:
            return None
        arr = np.asarray(self.joint_limits_rad, dtype=np.float64)
        if arr.shape != (len(self.joint_names), 2):
            raise ValueError(
                f"joint_limits_rad must have shape ({len(self.joint_names)}, 2), got {arr.shape}"
            )
        return arr


def conversion_config_from_contract(
    contract: Mapping[str, Any],
    *,
    gripper_closed_is_high: bool = True,
    max_delta_deg: float | None = 5.0,
    max_delta_gripper: float | None = 10.0,
    real_image_color: ColorMode = "rgb",
) -> SimToRealConversionConfig:
    """Build a conversion config from ``configs/contract.yaml``."""
    names = tuple(str(n) for n in contract["robot"]["joint_names"])
    if names != JOINT_NAMES:
        raise ValueError(f"Unexpected joint_names {names!r}; expected {JOINT_NAMES!r}")
    limits = contract["robot"]["joint_limits"]
    limits_arr = np.array(
        [[float(limits[n][0]), float(limits[n][1])] for n in names],
        dtype=np.float64,
    )
    cams = contract["cameras"]
    top = cams["top"]
    wrist = cams["wrist"]
    if (int(top["height"]), int(top["width"])) != (int(wrist["height"]), int(wrist["width"])):
        raise ValueError("top/wrist camera resolutions in contract must match")
    grip = limits["gripper"]
    return SimToRealConversionConfig(
        joint_names=names,
        gripper_closed_is_high=gripper_closed_is_high,
        gripper_rad_min=float(grip[0]),
        gripper_rad_max=float(grip[1]),
        joint_limits_rad=limits_arr,
        max_delta_deg=max_delta_deg,
        max_delta_gripper=max_delta_gripper,
        camera_map=_default_camera_map(),
        target_image_hw=(int(top["height"]), int(top["width"])),
        real_image_color=real_image_color,
    )


def real_gripper_percent_to_sim_rad(
    percent: float,
    *,
    rad_min: float = GRIPPER_RAD_MIN,
    rad_max: float = GRIPPER_RAD_MAX,
    closed_is_high: bool = True,
) -> float:
    """Map real gripper 0–100 onto sim gripper radians."""
    span = float(rad_max) - float(rad_min)
    if span <= 0.0:
        raise ValueError("rad_max must be greater than rad_min")
    p = float(percent)
    if closed_is_high:
        # 0 open → rad_max; 100 closed → rad_min
        return float(rad_max) - (p / 100.0) * span
    return float(rad_min) + (p / 100.0) * span


def sim_gripper_rad_to_real_percent(
    rad: float,
    *,
    rad_min: float = GRIPPER_RAD_MIN,
    rad_max: float = GRIPPER_RAD_MAX,
    closed_is_high: bool = True,
) -> float:
    """Inverse of :func:`real_gripper_percent_to_sim_rad` (not clipped)."""
    span = float(rad_max) - float(rad_min)
    if span <= 0.0:
        raise ValueError("rad_max must be greater than rad_min")
    open_frac = (float(rad) - float(rad_min)) / span
    if closed_is_high:
        return 100.0 * (1.0 - open_frac)
    return 100.0 * open_frac


def real_joints_to_sim_state(
    real_joints: Sequence[float] | Mapping[str, float] | np.ndarray,
    config: SimToRealConversionConfig,
) -> np.ndarray:
    """Convert real (deg, gripper 0–100) → sim state radians ``(6,)``."""
    vec = _as_joint_vector(real_joints, config.joint_names)
    out = np.empty(6, dtype=np.float64)
    out[:5] = np.radians(vec[:5])
    out[5] = real_gripper_percent_to_sim_rad(
        float(vec[5]),
        rad_min=config.gripper_rad_min,
        rad_max=config.gripper_rad_max,
        closed_is_high=config.gripper_closed_is_high,
    )
    return out.astype(np.float32)


def sim_state_to_real_joints(
    sim_joints: Sequence[float] | np.ndarray,
    config: SimToRealConversionConfig,
) -> np.ndarray:
    """Convert sim radians → real (deg ×5, gripper 0–100)."""
    vec = np.asarray(sim_joints, dtype=np.float64).reshape(-1)
    if vec.shape[0] != 6:
        raise ValueError(f"Expected 6 joints, got shape {vec.shape}")
    out = np.empty(6, dtype=np.float64)
    out[:5] = np.degrees(vec[:5])
    out[5] = sim_gripper_rad_to_real_percent(
        float(vec[5]),
        rad_min=config.gripper_rad_min,
        rad_max=config.gripper_rad_max,
        closed_is_high=config.gripper_closed_is_high,
    )
    return out.astype(np.float32)


def sim_action_to_real_joints(
    sim_action: Sequence[float] | np.ndarray,
    config: SimToRealConversionConfig,
) -> np.ndarray:
    """Clamp in sim units, then convert to real units."""
    clipped = clamp_sim_joints(sim_action, config)
    return sim_state_to_real_joints(clipped, config)


def clamp_sim_joints(
    sim_joints: Sequence[float] | np.ndarray,
    config: SimToRealConversionConfig,
) -> np.ndarray:
    """Clip a 6-D sim joint vector to contract limits (no-op if limits unset)."""
    vec = np.asarray(sim_joints, dtype=np.float64).reshape(-1)
    if vec.shape[0] != 6:
        raise ValueError(f"Expected 6 joints, got shape {vec.shape}")
    limits = config.limits_array()
    if limits is None:
        return vec.astype(np.float32)
    return np.clip(vec, limits[:, 0], limits[:, 1]).astype(np.float32)


def apply_max_delta_real(
    target_real: Sequence[float] | np.ndarray,
    current_real: Sequence[float] | np.ndarray,
    config: SimToRealConversionConfig,
) -> np.ndarray:
    """Limit per-step change in real units (deg / gripper percent)."""
    target = np.asarray(target_real, dtype=np.float64).reshape(6)
    current = np.asarray(current_real, dtype=np.float64).reshape(6)
    out = target.copy()
    if config.max_delta_deg is not None:
        delta = float(config.max_delta_deg)
        if delta < 0:
            raise ValueError(f"max_delta_deg must be >= 0, got {delta}")
        for i in ARM_JOINT_INDICES:
            lo = current[i] - delta
            hi = current[i] + delta
            out[i] = float(np.clip(target[i], lo, hi))
    if config.max_delta_gripper is not None:
        gdelta = float(config.max_delta_gripper)
        if gdelta < 0:
            raise ValueError(f"max_delta_gripper must be >= 0, got {gdelta}")
        out[GRIPPER_INDEX] = float(
            np.clip(
                target[GRIPPER_INDEX],
                current[GRIPPER_INDEX] - gdelta,
                current[GRIPPER_INDEX] + gdelta,
            )
        )
    out[GRIPPER_INDEX] = float(np.clip(out[GRIPPER_INDEX], 0.0, 100.0))
    return out.astype(np.float32)


def real_action_dict(real_joints: Sequence[float] | np.ndarray) -> dict[str, float]:
    """Build a LeRobot ``send_action`` dict from a length-6 real vector."""
    vec = np.asarray(real_joints, dtype=np.float64).reshape(6)
    return {key: float(vec[i]) for i, key in enumerate(REAL_MOTOR_KEYS)}


def extract_real_joint_vector(
    observation: Mapping[str, Any],
    joint_names: Sequence[str] = JOINT_NAMES,
) -> np.ndarray:
    """Pull ``*.pos`` motor values from a LeRobot observation dict."""
    values: list[float] = []
    for name in joint_names:
        key = f"{name}.pos"
        if key not in observation:
            raise KeyError(f"Missing motor key {key!r} in observation")
        values.append(float(observation[key]))
    return np.asarray(values, dtype=np.float32)


def map_real_cameras(
    observation: Mapping[str, Any],
    camera_map: Mapping[str, str],
) -> dict[str, np.ndarray]:
    """Map real camera keys onto sim policy keys.

    Raises ``KeyError`` listing missing real cameras so Phase 2-2 docs can call
    out setup gaps (this project's bring-up provides ``top`` and ``wrist``).
    """
    missing = [real_key for real_key in camera_map if real_key not in observation]
    if missing:
        raise KeyError(
            "Real observation is missing camera keys required by the sim policy: "
            f"{missing}. Configured map (real→sim)={dict(camera_map)}. "
            "Bring-up expects OpenCV cameras named 'top' and 'wrist'."
        )
    return {sim_key: np.asarray(observation[real_key]) for real_key, sim_key in camera_map.items()}


def resize_image_hwc(image: np.ndarray, height: int, width: int) -> np.ndarray:
    """Resize an HWC image to ``(height, width)`` (identity if already matching)."""
    img = np.asarray(image)
    if img.ndim != 3:
        raise ValueError(f"Expected HWC image, got shape {img.shape}")
    if img.shape[0] == height and img.shape[1] == width:
        return np.ascontiguousarray(img)
    try:
        import cv2

        return cv2.resize(img, (width, height), interpolation=cv2.INTER_LINEAR)
    except ImportError:
        from PIL import Image

        pil = Image.fromarray(img)
        resized = pil.resize((width, height), Image.Resampling.BILINEAR)
        return np.asarray(resized)


def image_to_chw_float(
    image_hwc: np.ndarray,
    *,
    source_color: ColorMode,
) -> np.ndarray:
    """HWC uint8/float → CHW RGB float32 in ``[0, 1]`` for ACT."""
    img = np.asarray(image_hwc)
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"Expected HWC image with 3 channels, got shape {img.shape}")
    if img.dtype == np.uint8:
        arr = img.astype(np.float32) / 255.0
    else:
        arr = img.astype(np.float32)
        if arr.max() > 1.0:
            arr = arr / 255.0
    if source_color == "bgr":
        arr = arr[:, :, ::-1]
    elif source_color != "rgb":
        raise ValueError(f"source_color must be 'rgb' or 'bgr', got {source_color!r}")
    return np.transpose(arr, (2, 0, 1)).astype(np.float32, copy=False)


def prepare_policy_images(
    real_cameras: Mapping[str, np.ndarray],
    config: SimToRealConversionConfig,
) -> dict[str, np.ndarray]:
    """Resize (if needed) and convert real camera frames to CHW RGB float32."""
    out: dict[str, np.ndarray] = {}
    for sim_key, frame in real_cameras.items():
        img = np.asarray(frame)
        if config.target_image_hw is not None:
            h, w = config.target_image_hw
            img = resize_image_hwc(img, h, w)
        out[sim_key] = image_to_chw_float(img, source_color=config.real_image_color)
    return out


def _as_joint_vector(
    joints: Sequence[float] | Mapping[str, float] | np.ndarray,
    joint_names: Sequence[str],
) -> np.ndarray:
    if isinstance(joints, Mapping):
        values = []
        for name in joint_names:
            key = f"{name}.pos" if f"{name}.pos" in joints else name
            if key not in joints:
                raise KeyError(f"Missing joint {name!r} (tried {key!r})")
            values.append(float(joints[key]))
        return np.asarray(values, dtype=np.float64)
    vec = np.asarray(joints, dtype=np.float64).reshape(-1)
    if vec.shape[0] != len(joint_names):
        raise ValueError(f"Expected {len(joint_names)} joints, got shape {vec.shape}")
    return vec
