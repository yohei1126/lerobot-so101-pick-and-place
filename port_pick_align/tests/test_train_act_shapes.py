"""Unit tests for ACT policy I/O shapes (no training loop)."""

from __future__ import annotations

import pytest

from port_pick_align.contract import load_contract

torch = pytest.importorskip("torch")
pytest.importorskip("lerobot")

from port_pick_align.training.policy import build_act_policy  # noqa: E402


@pytest.mark.unit
def test_build_act_policy_features() -> None:
    contract = load_contract()
    policy = build_act_policy(contract, device="cpu")
    config = policy.config

    assert config.vision_backbone == "resnet18"
    assert config.chunk_size == 30
    assert config.input_features["observation.images.top"].shape == (3, 480, 640)
    assert config.input_features["observation.images.wrist"].shape == (3, 480, 640)
    assert config.input_features["observation.state"].shape == (6,)
    assert config.output_features["action"].shape == (6,)

    param_count = sum(p.numel() for p in policy.parameters())
    assert param_count > 0
