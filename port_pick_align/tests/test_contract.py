"""Unit tests for configs/contract.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest

from port_pick_align.contract import DEFAULT_CONTRACT_PATH, load_contract, validate_contract

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_default_contract_path_exists() -> None:
    assert DEFAULT_CONTRACT_PATH.is_file()


@pytest.mark.unit
def test_contract_shapes_match_task2() -> None:
    contract = load_contract(REPO_ROOT / "configs" / "contract.yaml")
    validate_contract(contract)

    assert contract["robot"]["dof"] == 6
    assert len(contract["robot"]["joint_names"]) == 6
    for cam_name in ("top", "wrist"):
        cam = contract["cameras"][cam_name]
        assert cam["width"] == 640
        assert cam["height"] == 480
        assert cam["channels"] == 3
        assert cam["fps"] == 30
    assert contract["model"]["policy"] == "act"
    assert contract["model"]["chunk_size"] == 30
    assert contract["model"]["action_dim"] == 6
    assert contract["model"]["vision_backbone"] == "resnet18"
    assert set(contract["robot"]["joint_limits"]) == set(contract["robot"]["joint_names"])
    assert contract["quality"]["sync_tolerance_ms"] == 33
    assert contract["quality"]["max_frame_gap_ms"] == 50
    assert contract["quality"]["min_joint_variance"] == 1.0e-4


@pytest.mark.unit
def test_validate_contract_rejects_wrong_backbone() -> None:
    contract = load_contract()
    contract = {**contract, "model": {**contract["model"], "vision_backbone": "resnet50"}}
    with pytest.raises(ValueError, match="resnet18"):
        validate_contract(contract)
