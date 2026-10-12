"""Unit tests for synthetic LeRobotDataset generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pai_final.contract import load_contract
from pai_final.dataset.synthetic import build_features, generate_synthetic_dataset, make_dummy_image

pytest.importorskip("lerobot")


@pytest.mark.unit
def test_make_dummy_image_shape() -> None:
    img = make_dummy_image(480, 640, 3, frame_idx=3, seed=1)
    assert img.shape == (480, 640, 3)
    assert img.dtype.name == "uint8"


@pytest.mark.unit
def test_build_features_match_contract() -> None:
    contract = load_contract()
    features = build_features(contract)
    assert set(features) == {
        "observation.images.top",
        "observation.images.wrist",
        "observation.state",
        "action",
    }
    assert features["observation.images.top"]["shape"] == (480, 640, 3)
    assert features["observation.images.wrist"]["dtype"] == "image"
    assert features["observation.state"]["shape"] == (6,)
    assert features["action"]["shape"] == (6,)


@pytest.mark.unit
def test_generate_synthetic_dataset_episodes(tmp_path: Path) -> None:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    contract = load_contract()
    root = tmp_path / "synth"
    generate_synthetic_dataset(
        root,
        contract=contract,
        episodes=2,
        frames=8,
        seed=0,
        repo_id="local/test_synth",
    )

    ds = LeRobotDataset(repo_id="local/test_synth", root=root)
    assert ds.num_episodes == 2
    assert ds.num_frames == 16
    meta_features = ds.meta.features
    assert meta_features["observation.images.top"]["shape"] == (480, 640, 3)
    assert meta_features["observation.images.wrist"]["shape"] == (480, 640, 3)
    assert meta_features["observation.state"]["shape"] == (6,)
    assert meta_features["action"]["shape"] == (6,)
