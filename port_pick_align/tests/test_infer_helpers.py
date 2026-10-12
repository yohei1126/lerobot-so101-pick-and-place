"""Unit / integration tests for shared ACT inference helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from port_pick_align.contract import load_contract
from port_pick_align.training.infer import (
    bgr_to_chw_float,
    images_bgr_to_batch,
    mock_action_chunk,
    predict_chunk,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CKPT = REPO_ROOT / "checkpoints" / "synthetic_act" / "best_model.pt"


@pytest.mark.unit
def test_mock_action_chunk_shape() -> None:
    state = np.arange(6, dtype=np.float32) * 0.1
    chunk = mock_action_chunk(state, chunk_size=30, action_dim=6)
    assert chunk.shape == (30, 6)
    assert np.allclose(chunk[0], state)
    assert np.allclose(chunk[-1], state)


@pytest.mark.unit
def test_bgr_to_chw_float_swaps_channels() -> None:
    # Pure blue in BGR → channel 0 in RGB after conversion should be ~0, blue→index 2
    img = np.zeros((4, 5, 3), dtype=np.uint8)
    img[:, :, 0] = 255  # B
    chw = bgr_to_chw_float(img)
    assert chw.shape == (3, 4, 5)
    assert chw[2].mean() == pytest.approx(1.0)
    assert chw[0].mean() == pytest.approx(0.0)


@pytest.mark.unit
def test_images_bgr_to_batch_shapes() -> None:
    pytest.importorskip("torch")
    top = np.zeros((480, 640, 3), dtype=np.uint8)
    wrist = np.ones((480, 640, 3), dtype=np.uint8) * 128
    state = np.zeros(6, dtype=np.float32)
    batch = images_bgr_to_batch(top, wrist, state, device="cpu")
    assert tuple(batch["observation.images.top"].shape) == (1, 3, 480, 640)
    assert tuple(batch["observation.images.wrist"].shape) == (1, 3, 480, 640)
    assert tuple(batch["observation.state"].shape) == (1, 6)


@pytest.mark.integration
def test_predict_chunk_from_checkpoint() -> None:
    pytest.importorskip("torch")
    pytest.importorskip("lerobot")
    if not DEFAULT_CKPT.is_file():
        pytest.skip(f"checkpoint not found: {DEFAULT_CKPT}")

    from port_pick_align.training.train_act import load_policy_from_checkpoint

    contract = load_contract()
    policy = load_policy_from_checkpoint(DEFAULT_CKPT, contract, device="cpu")
    top = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    wrist = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    state = np.zeros(6, dtype=np.float32)
    batch = images_bgr_to_batch(top, wrist, state, device="cpu")
    chunk = predict_chunk(policy, batch)
    assert chunk.shape == (30, 6)
    assert chunk.dtype == np.float32
