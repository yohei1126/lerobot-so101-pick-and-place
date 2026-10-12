"""Synthetic LeRobotDataset generation matching configs/contract.yaml."""

from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from pai_final.contract import load_contract, validate_contract

DEFAULT_REPO_ID = "local/pai_final_synthetic"
DEFAULT_TASK = "synthetic_alignment"
DEFAULT_EPISODES = 8
DEFAULT_FRAMES = 64


def make_dummy_image(
    height: int,
    width: int,
    channels: int,
    frame_idx: int,
    seed: int,
) -> np.ndarray:
    """Create a uint8 HWC image with a moving stripe (same idea as sample_bag)."""
    img = np.zeros((height, width, channels), dtype=np.uint8)
    img[:, :, 0] = (seed * 40) % 256
    img[:, :, 1] = (seed * 80) % 256
    img[:, :, 2] = (seed * 120) % 256
    stripe = (frame_idx * 8) % width
    img[:, stripe : min(stripe + 16, width), :] = 255
    return img


def make_joint_vector(t: float, dof: int, noise: float, rng: np.random.Generator) -> np.ndarray:
    """Sinusoidal joint vector plus small noise (avoids static episodes)."""
    base = np.array(
        [0.3 * math.sin(t * (i + 1) * 0.4 + i) for i in range(dof)],
        dtype=np.float32,
    )
    if noise > 0:
        base = base + rng.normal(0.0, noise, size=dof).astype(np.float32)
    return base


def build_features(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    top = contract["cameras"]["top"]
    wrist = contract["cameras"]["wrist"]
    joint_names = list(contract["robot"]["joint_names"])
    h, w, c = int(top["height"]), int(top["width"]), int(top["channels"])
    wh, ww, wc = int(wrist["height"]), int(wrist["width"]), int(wrist["channels"])
    if (wh, ww, wc) != (h, w, c):
        raise ValueError("top and wrist camera shapes must match for ACT")
    dof = int(contract["robot"]["dof"])
    return {
        "observation.images.top": {
            "dtype": "image",
            "shape": (h, w, c),
            "names": ["height", "width", "channels"],
        },
        "observation.images.wrist": {
            "dtype": "image",
            "shape": (wh, ww, wc),
            "names": ["height", "width", "channels"],
        },
        "observation.state": {
            "dtype": "float32",
            "shape": (dof,),
            "names": joint_names,
        },
        "action": {
            "dtype": "float32",
            "shape": (dof,),
            "names": joint_names,
        },
    }


def generate_synthetic_dataset(
    output_dir: Path | str,
    contract: dict[str, Any] | None = None,
    contract_path: Path | str | None = None,
    *,
    repo_id: str = DEFAULT_REPO_ID,
    episodes: int = DEFAULT_EPISODES,
    frames: int = DEFAULT_FRAMES,
    seed: int = 0,
    task: str = DEFAULT_TASK,
    overwrite: bool = True,
) -> Path:
    """Write a contract-aligned LeRobotDataset and return its root path."""
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    if contract is None:
        contract = load_contract(contract_path)
    validate_contract(contract)

    root = Path(output_dir)
    if root.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {root}")
        shutil.rmtree(root)

    features = build_features(contract)
    top = contract["cameras"]["top"]
    wrist = contract["cameras"]["wrist"]
    fps = int(top["fps"])
    dof = int(contract["robot"]["dof"])
    rng = np.random.default_rng(seed)

    ds = LeRobotDataset.create(
        repo_id=repo_id,
        fps=fps,
        features=features,
        root=root,
        robot_type=str(contract["robot"]["name"]),
        use_videos=False,
        image_writer_threads=4,
    )

    for ep in range(episodes):
        for frame_idx in range(frames):
            t = frame_idx / fps
            state = make_joint_vector(t, dof, noise=0.01, rng=rng)
            # Next-step target keeps action correlated but not identical.
            action = make_joint_vector(t + 1.0 / fps, dof, noise=0.01, rng=rng)
            top_img = make_dummy_image(
                int(top["height"]),
                int(top["width"]),
                int(top["channels"]),
                frame_idx,
                seed=ep,
            )
            wrist_img = make_dummy_image(
                int(wrist["height"]),
                int(wrist["width"]),
                int(wrist["channels"]),
                frame_idx,
                seed=ep + 17,
            )
            ds.add_frame(
                {
                    "observation.images.top": top_img,
                    "observation.images.wrist": wrist_img,
                    "observation.state": state,
                    "action": action,
                    "task": task,
                }
            )
        ds.save_episode()

    ds.finalize()
    return root
