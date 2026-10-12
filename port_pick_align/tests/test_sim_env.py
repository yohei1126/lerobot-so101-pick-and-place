"""MuJoCo PickAlignSimEnv smoke tests (optional simulation extra)."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")


@pytest.mark.simulation
@pytest.mark.unit
def test_reset_and_step_shapes() -> None:
    from port_pick_align.contract import load_contract
    from port_pick_align.simulation.env import PickAlignSimEnv

    contract = load_contract()
    env = PickAlignSimEnv(contract=contract, max_episode_steps=5)
    try:
        obs, info = env.reset(seed=0, options={"randomize_box": False})
        h = int(contract["cameras"]["top"]["height"])
        w = int(contract["cameras"]["top"]["width"])
        assert obs["top"].shape == (h, w, 3)
        assert obs["wrist"].shape == (h, w, 3)
        assert obs["top"].dtype == np.uint8
        assert obs["state"].shape == (6,)
        assert "box_xy" in info

        action = obs["state"].copy()
        obs2, reward, terminated, truncated, info2 = env.step(action)
        assert obs2["state"].shape == (6,)
        assert isinstance(reward, float)
        assert terminated is False
        assert truncated is False
        assert info2["step"] == 1
    finally:
        env.close()


@pytest.mark.simulation
@pytest.mark.unit
def test_action_clipped_to_limits() -> None:
    from port_pick_align.contract import load_contract
    from port_pick_align.simulation.env import PickAlignSimEnv

    contract = load_contract()
    env = PickAlignSimEnv(contract=contract, max_episode_steps=3)
    try:
        obs, _ = env.reset(seed=1)
        huge = np.full(6, 100.0, dtype=np.float32)
        obs2, _, _, _, _ = env.step(huge)
        limits = contract["robot"]["joint_limits"]
        names = contract["robot"]["joint_names"]
        for i, name in enumerate(names):
            lo, hi = limits[name]
            assert lo <= float(obs2["state"][i]) <= hi + 0.05
    finally:
        env.close()
