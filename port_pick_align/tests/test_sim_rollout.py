"""Closed-loop mock rollout smoke (optional simulation extra)."""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")


@pytest.mark.simulation
@pytest.mark.unit
def test_mock_closed_loop_metrics() -> None:
    from port_pick_align.contract import load_contract
    from port_pick_align.evaluation.eval_alignment import (
        compute_pose_errors,
        infer_grasp_success,
        record_sample,
        summarize,
    )
    from port_pick_align.simulation.env import PickAlignSimEnv
    from port_pick_align.simulation.policies import MockPolicy

    contract = load_contract()
    env = PickAlignSimEnv(contract=contract, max_episode_steps=10)
    policy = MockPolicy(
        chunk_size=int(contract["model"]["chunk_size"]),
        action_dim=int(contract["model"]["action_dim"]),
    )
    try:
        obs, info = env.reset(seed=2)
        for _ in range(8):
            chunk = policy.predict(obs)
            assert chunk.shape == (30, 6)
            obs, _, terminated, truncated, info = env.step(chunk[0])
            if terminated or truncated:
                break
        pos_mm, yaw_deg = compute_pose_errors(
            info["box_xy"], info["box_yaw"], info["target_xy"], info["target_yaw"]
        )
        grasp = infer_grasp_success(
            box_z=float(info["box_z"]),
            table_z=float(info["table_z"]),
        )
        sample = record_sample(pos_mm, yaw_deg, grasp)
        summary = summarize([sample])
        assert summary["n_samples"] == 1
        assert "align_success_rate" in summary
        assert "mean_position_error_mm" in summary
    finally:
        env.close()
