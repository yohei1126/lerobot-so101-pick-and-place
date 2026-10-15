"""Temporal ensembling for closed-loop ACT chunks."""

from __future__ import annotations

import math

import numpy as np
import pytest

from port_pick_align.simulation.policies import CheckpointPolicy, blend_temporal_ensemble


def _chunk(first: float, second: float) -> np.ndarray:
    chunk = np.zeros((2, 6), dtype=np.float32)
    chunk[0, 0] = first
    chunk[1, 0] = second
    return chunk


@pytest.mark.unit
def test_blend_weights_oldest_prediction_highest_when_coeff_positive() -> None:
    oldest = _chunk(first=0.0, second=10.0)
    newest = _chunk(first=0.0, second=0.0)
    coeff = 0.01
    blended = blend_temporal_ensemble([oldest, newest], coeff)
    weight_new = math.exp(-coeff)
    expected = 10.0 / (1.0 + weight_new)
    assert blended.shape == (6,)
    assert blended[0] == pytest.approx(expected)
    assert np.allclose(blended[1:], 0.0)


@pytest.mark.unit
def test_blend_zero_coeff_is_uniform_mean() -> None:
    series = []
    for row in (
        np.array([1.0, 2.0, 3.0], dtype=np.float32),
        np.array([4.0, 5.0, 6.0], dtype=np.float32),
        np.array([7.0, 8.0, 9.0], dtype=np.float32),
    ):
        chunk = np.zeros((3, 6), dtype=np.float32)
        chunk[:, 0] = row
        series.append(chunk)
    blended = blend_temporal_ensemble(series, 0.0)
    # Current step is oldest[:, 2], middle[:, 1], newest[:, 0] → 3, 5, 7.
    assert blended[0] == pytest.approx((3.0 + 5.0 + 7.0) / 3.0)


@pytest.mark.unit
def test_checkpoint_policy_ensemble_flag_and_reset() -> None:
    disabled = CheckpointPolicy(policy=object(), temporal_ensemble=False, chunk_size=2)
    raw = _chunk(first=1.5, second=9.0)
    assert np.allclose(disabled.blend_chunk(raw), raw)
    assert len(disabled._chunk_history) == 0

    enabled = CheckpointPolicy(
        policy=object(),
        temporal_ensemble=True,
        temporal_ensemble_coeff=0.0,
        chunk_size=2,
    )
    first = enabled.blend_chunk(_chunk(first=4.0, second=10.0))
    assert first[0, 0] == pytest.approx(4.0)
    second = enabled.blend_chunk(_chunk(first=0.0, second=0.0))
    # oldest action for now is 10, newest is 0, uniform mean is 5
    assert second[0, 0] == pytest.approx(5.0)
    assert second[1, 0] == pytest.approx(0.0)

    enabled.reset()
    after_reset = enabled.blend_chunk(_chunk(first=2.0, second=8.0))
    assert after_reset[0, 0] == pytest.approx(2.0)
    assert len(enabled._chunk_history) == 1


@pytest.mark.unit
def test_box_reset_options_leave_yaw_free_when_randomized() -> None:
    from port_pick_align.simulation.env import box_reset_options

    randomized = box_reset_options(randomize_box=True)
    assert randomized == {"randomize_box": True}
    assert "box_yaw" not in randomized
    assert box_reset_options(randomize_box=False) == {
        "randomize_box": False,
        "box_yaw": 0.0,
    }
