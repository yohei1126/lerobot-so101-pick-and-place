"""Unit tests for rosbag2 → LeRobot conversion."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from port_pick_align.contract import load_contract
from port_pick_align.dataset.converter import align_episode, convert_bag_to_lerobot, read_rosbag

FIXTURE_BAG = Path(__file__).resolve().parent / "fixtures" / "sample_bag"

pytest.importorskip("rosbags")


@pytest.mark.unit
def test_read_and_align_sample_bag() -> None:
    contract = load_contract()
    raw = read_rosbag(FIXTURE_BAG, contract=contract)
    episode = align_episode(raw, contract)

    assert len(episode.frames) == 15
    frame = episode.frames[0]
    assert frame.top.shape == (480, 640, 3)
    assert frame.wrist.shape == (480, 640, 3)
    assert frame.top.dtype == np.uint8
    assert frame.state.shape == (6,)
    assert frame.state.dtype == np.float32
    assert frame.sync_offset_ms == 0.0
    # Healthy fixture: all frames should be perfectly synced.
    assert all(f.sync_offset_ms == 0.0 for f in episode.frames)


@pytest.mark.unit
def test_convert_bag_to_lerobot_shapes(tmp_path: Path) -> None:
    pytest.importorskip("lerobot")
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    contract = load_contract()
    root = tmp_path / "from_bag"
    convert_bag_to_lerobot(
        FIXTURE_BAG,
        root,
        contract=contract,
        repo_id="local/test_from_bag",
    )

    ds = LeRobotDataset(repo_id="local/test_from_bag", root=root)
    assert ds.num_episodes == 1
    assert ds.num_frames == 15
    meta = ds.meta.features
    assert meta["observation.images.top"]["shape"] == (480, 640, 3)
    assert meta["observation.images.wrist"]["shape"] == (480, 640, 3)
    assert meta["observation.state"]["shape"] == (6,)
    assert meta["action"]["shape"] == (6,)
