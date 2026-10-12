"""Unit tests for RobOps episode quality gates."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from port_pick_align.contract import load_contract
from port_pick_align.dataset.converter import (
    AlignedEpisode,
    AlignedFrame,
    align_episode,
    read_rosbag,
)
from port_pick_align.dataset.validator import validate_episode

FIXTURE_BAG = Path(__file__).resolve().parent / "fixtures" / "sample_bag"
DT_NS = int(1e9 / 30)


def _make_frame(
    t_ns: int,
    state: np.ndarray,
    *,
    sync_offset_ms: float = 0.0,
) -> AlignedFrame:
    return AlignedFrame(
        t_ns=t_ns,
        top=np.zeros((480, 640, 3), dtype=np.uint8),
        wrist=np.zeros((480, 640, 3), dtype=np.uint8),
        state=state.astype(np.float32),
        sync_offset_ms=sync_offset_ms,
    )


def _moving_states(n: int = 8) -> list[np.ndarray]:
    return [np.array([0.1 * i, 0.05 * i, 0.0, 0.0, 0.0, 0.2], dtype=np.float32) for i in range(n)]


@pytest.mark.unit
def test_healthy_sample_bag_passes() -> None:
    pytest.importorskip("rosbags")
    contract = load_contract()
    episode = align_episode(read_rosbag(FIXTURE_BAG, contract=contract), contract)
    report = validate_episode(episode, contract)
    assert report.ok, [f"{i.code}: {i.message}" for i in report.issues]


@pytest.mark.unit
def test_detects_sync_offset() -> None:
    contract = load_contract()
    states = _moving_states()
    frames = [
        _make_frame(i * DT_NS, states[i], sync_offset_ms=0.0 if i else 50.0)
        for i in range(len(states))
    ]
    report = validate_episode(AlignedEpisode(frames=frames), contract)
    assert not report.ok
    assert "SYNC_OFFSET" in report.codes()


@pytest.mark.unit
def test_detects_frame_drop() -> None:
    contract = load_contract()
    states = _moving_states()
    frames = [_make_frame(i * DT_NS, states[i]) for i in range(len(states))]
    # Insert an 80ms gap between frame 2 and 3.
    frames[3] = _make_frame(frames[2].t_ns + int(80e6), states[3])
    for i in range(4, len(frames)):
        frames[i] = _make_frame(frames[i - 1].t_ns + DT_NS, states[i])

    report = validate_episode(AlignedEpisode(frames=frames), contract)
    assert not report.ok
    assert "FRAME_DROP" in report.codes()


@pytest.mark.unit
def test_detects_joint_limit() -> None:
    contract = load_contract()
    states = _moving_states()
    states[2] = states[2].copy()
    states[2][0] = 3.0  # beyond shoulder_pan ±1.9199
    frames = [_make_frame(i * DT_NS, states[i]) for i in range(len(states))]
    report = validate_episode(AlignedEpisode(frames=frames), contract)
    assert not report.ok
    assert "JOINT_LIMIT" in report.codes()


@pytest.mark.unit
def test_detects_static_episode() -> None:
    contract = load_contract()
    static = np.zeros(6, dtype=np.float32)
    frames = [_make_frame(i * DT_NS, static) for i in range(8)]
    report = validate_episode(AlignedEpisode(frames=frames), contract)
    assert not report.ok
    assert "STATIC_EPISODE" in report.codes()
