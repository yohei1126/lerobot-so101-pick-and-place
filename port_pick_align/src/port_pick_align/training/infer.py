"""Shared ACT inference helpers for host smoke tests and ROS 2 policy node."""

from __future__ import annotations

from typing import Any

import numpy as np


def mock_action_chunk(
    state: np.ndarray,
    chunk_size: int,
    action_dim: int,
) -> np.ndarray:
    """Repeat the current joint state across the action chunk (Docker / no-torch mode)."""
    flat = np.asarray(state, dtype=np.float32).reshape(-1)
    if flat.shape[0] != action_dim:
        raise ValueError(f"state dim must be {action_dim}, got {flat.shape[0]}")
    return np.tile(flat, (chunk_size, 1))


def bgr_to_chw_float(image_bgr: np.ndarray) -> np.ndarray:
    """Convert HWC BGR uint8/float image to CHW RGB float32 in [0, 1]."""
    img = np.asarray(image_bgr)
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"Expected HWC image with 3 channels, got shape {img.shape}")
    if img.dtype == np.uint8:
        rgb = img[:, :, ::-1].astype(np.float32) / 255.0
    else:
        rgb = img[:, :, ::-1].astype(np.float32)
        if rgb.max() > 1.0:
            rgb = rgb / 255.0
    return np.transpose(rgb, (2, 0, 1))


def images_bgr_to_batch(
    top_bgr: np.ndarray,
    wrist_bgr: np.ndarray,
    state: np.ndarray,
    device: str = "cpu",
) -> dict[str, Any]:
    """Build a single-sample ACT observation batch from ROS-style BGR images."""
    import torch

    top_chw = bgr_to_chw_float(top_bgr)
    wrist_chw = bgr_to_chw_float(wrist_bgr)
    state_vec = np.asarray(state, dtype=np.float32).reshape(-1)

    return {
        "observation.images.top": torch.from_numpy(top_chw).unsqueeze(0).to(device),
        "observation.images.wrist": torch.from_numpy(wrist_chw).unsqueeze(0).to(device),
        "observation.state": torch.from_numpy(state_vec).unsqueeze(0).to(device),
    }


def predict_chunk(policy: Any, batch: dict[str, Any]) -> np.ndarray:
    """Run ``policy.predict_action_chunk`` and return ``(chunk_size, action_dim)`` float32."""
    import torch

    with torch.inference_mode():
        chunk_tensor = policy.predict_action_chunk(batch)

    if not isinstance(chunk_tensor, torch.Tensor):
        raise TypeError(f"predict_action_chunk returned {type(chunk_tensor)}")
    chunk = chunk_tensor
    if chunk.ndim == 3:
        chunk = chunk[0]
    if chunk.ndim != 2:
        raise ValueError(f"Expected 2D action chunk, got shape {tuple(chunk.shape)}")
    return chunk.detach().cpu().numpy().astype(np.float32, copy=False)
