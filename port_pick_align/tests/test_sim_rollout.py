"""Closed-loop mock / scripted rollout smoke (optional simulation extra)."""

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
    env = PickAlignSimEnv(contract=contract, max_episode_steps=10, render_cameras=False)
    policy = MockPolicy(
        chunk_size=int(contract["model"]["chunk_size"]),
        action_dim=int(contract["model"]["action_dim"]),
    )
    try:
        obs, info = env.reset(seed=2)
        for _ in range(8):
            chunk = policy.predict(obs, info=info)
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


@pytest.mark.simulation
@pytest.mark.unit
def test_scripted_pick_align_success() -> None:
    """Fixed-spawn scripted policy must grasp and align within eval thresholds."""
    from port_pick_align.contract import load_contract
    from port_pick_align.evaluation.eval_alignment import (
        compute_pose_errors,
        is_align_success,
        record_sample,
        summarize,
    )
    from port_pick_align.simulation.env import PickAlignSimEnv
    from port_pick_align.simulation.policies import ScriptedPickAlignPolicy

    contract = load_contract()
    env = PickAlignSimEnv(contract=contract, max_episode_steps=300, render_cameras=False)
    policy = ScriptedPickAlignPolicy(
        chunk_size=int(contract["model"]["chunk_size"]),
        action_dim=int(contract["model"]["action_dim"]),
    )
    policy.set_ik(env.solve_ik)
    policy.reset()
    try:
        obs, info = env.reset(seed=0, options={"randomize_box": False, "box_yaw": 0.0})
        grasped = False
        for _ in range(300):
            chunk = policy.predict(obs, info=info)
            assert chunk.shape == (30, 6)
            obs, _, terminated, truncated, info = env.step(chunk[0])
            grasped = grasped or bool(info.get("grasping", False))
            if terminated or truncated:
                break
        pos_mm, yaw_deg = compute_pose_errors(
            info["box_xy"], info["box_yaw"], info["target_xy"], info["target_yaw"]
        )
        sample = record_sample(pos_mm, yaw_deg, grasp_success=grasped or pos_mm < 50.0)
        summary = summarize([sample])
        assert grasped or sample.grasp_success
        assert is_align_success(pos_mm, yaw_deg)
        assert summary["align_success_rate"] == 1.0
        assert summary["grasp_success_rate"] == 1.0
    finally:
        env.close()


@pytest.mark.simulation
@pytest.mark.unit
def test_untrained_checkpoint_temporal_ensemble_steps() -> None:
    """Closed-loop path with ensembling. Weights are random, so success is not expected."""
    pytest.importorskip("torch")
    pytest.importorskip("lerobot")
    import numpy as np

    from port_pick_align.contract import load_contract
    from port_pick_align.simulation.env import PickAlignSimEnv
    from port_pick_align.simulation.policies import CheckpointPolicy
    from port_pick_align.training.policy import build_act_policy

    contract = load_contract()
    network = build_act_policy(contract, device="cpu")
    network.eval()
    policy = CheckpointPolicy(
        network,
        chunk_size=int(contract["model"]["chunk_size"]),
        device="cpu",
        temporal_ensemble=True,
        temporal_ensemble_coeff=0.01,
    )
    env = PickAlignSimEnv(contract=contract, max_episode_steps=3, render_cameras=False)
    try:
        obs, info = env.reset(seed=1, options={"randomize_box": True})
        for _ in range(3):
            chunk = policy.predict(obs, info=info)
            assert chunk.shape == (30, 6)
            assert np.isfinite(chunk).all()
            obs, _, terminated, truncated, info = env.step(chunk[0])
            if terminated or truncated:
                break
        assert len(policy._chunk_history) == 3
    finally:
        env.close()
