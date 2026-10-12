"""Load and validate configs/contract.yaml (Single Source of Truth)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONTRACT_PATH = REPO_ROOT / "configs" / "contract.yaml"


def load_contract(path: Path | str | None = None) -> dict[str, Any]:
    contract_path = Path(path) if path is not None else DEFAULT_CONTRACT_PATH
    with contract_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Contract must be a mapping: {contract_path}")
    return data


def validate_contract(contract: dict[str, Any]) -> None:
    """Raise ValueError if required Task-2/3 keys / shapes are missing."""
    try:
        robot = contract["robot"]
        cameras = contract["cameras"]
        model = contract["model"]
        quality = contract["quality"]
        top = cameras["top"]
        wrist = cameras["wrist"]
        joint_limits = robot["joint_limits"]
    except KeyError as exc:
        raise ValueError(f"Missing contract key: {exc}") from exc

    if int(robot["dof"]) != 6:
        raise ValueError(f"robot.dof must be 6, got {robot['dof']}")
    if len(robot["joint_names"]) != 6:
        raise ValueError("robot.joint_names must have length 6")

    for name in robot["joint_names"]:
        if name not in joint_limits:
            raise ValueError(f"robot.joint_limits missing entry for {name!r}")
        lim = joint_limits[name]
        if len(lim) != 2 or float(lim[0]) >= float(lim[1]):
            raise ValueError(f"robot.joint_limits[{name}] must be [min, max] with min < max")

    for name, cam in (("top", top), ("wrist", wrist)):
        if int(cam["width"]) != 640 or int(cam["height"]) != 480 or int(cam["channels"]) != 3:
            raise ValueError(
                f"cameras.{name} must be 640x480x3, got "
                f"{cam['width']}x{cam['height']}x{cam['channels']}"
            )

    if model.get("policy") != "act":
        raise ValueError(f"model.policy must be 'act', got {model.get('policy')}")
    if int(model["chunk_size"]) != 30:
        raise ValueError(f"model.chunk_size must be 30, got {model['chunk_size']}")
    if int(model["action_dim"]) != 6:
        raise ValueError(f"model.action_dim must be 6, got {model['action_dim']}")
    if model.get("vision_backbone") != "resnet18":
        raise ValueError(
            f"model.vision_backbone must be 'resnet18', got {model.get('vision_backbone')}"
        )

    for key in ("sync_tolerance_ms", "max_frame_gap_ms", "min_joint_variance"):
        if key not in quality:
            raise ValueError(f"quality.{key} is required")
    if float(quality["sync_tolerance_ms"]) <= 0:
        raise ValueError("quality.sync_tolerance_ms must be positive")
    if float(quality["max_frame_gap_ms"]) <= 0:
        raise ValueError("quality.max_frame_gap_ms must be positive")
    if float(quality["min_joint_variance"]) < 0:
        raise ValueError("quality.min_joint_variance must be non-negative")
