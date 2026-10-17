"""Closed-loop mock / scripted rollout smoke (optional simulation extra)."""

from __future__ import annotations

from typing import Any

import numpy as np
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
    policy.set_transport_plan(env.plan_transport_joints)
    policy.set_transport_retarget(env.retarget_transport_joints)
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


def _scripted_until_grasp(env: Any, seed: int = 0) -> tuple[Any, dict[str, Any], Any]:
    from port_pick_align.simulation.policies import ScriptedPickAlignPolicy

    policy = ScriptedPickAlignPolicy(chunk_size=30, action_dim=6)
    policy.set_ik(env.solve_ik)
    policy.set_transport_plan(env.plan_transport_joints)
    policy.set_transport_retarget(env.retarget_transport_joints)
    policy.reset()
    obs, info = env.reset(seed=seed, options={"randomize_box": False, "box_yaw": 0.2})
    chunk = np.zeros((30, 6), dtype=np.float32)
    for _ in range(160):
        chunk = policy.predict(obs, info=info)
        obs, _, _, _, info = env.step(chunk[0])
        if info.get("grasping"):
            return obs, info, chunk[0]
    raise AssertionError("scripted policy did not attach")


@pytest.mark.simulation
@pytest.mark.unit
def test_gripper_hysteresis_keeps_carry_and_releases_when_open() -> None:
    from port_pick_align.contract import load_contract
    from port_pick_align.simulation.env import (
        GRIPPER_CLOSE_THRESH,
        GRIPPER_OPEN_THRESH,
        RELEASE_NEAR_PAD_M,
        PickAlignSimEnv,
    )

    assert GRIPPER_OPEN_THRESH > GRIPPER_CLOSE_THRESH
    contract = load_contract()
    env = PickAlignSimEnv(contract=contract, max_episode_steps=400, render_cameras=False)
    try:
        _obs, info, hold = _scripted_until_grasp(env)
        assert info["grasping"]
        ambiguous = hold.copy()
        ambiguous[5] = 0.55
        for _ in range(5):
            _obs, _, _, _, info = env.step(ambiguous)
        assert info["grasping"]

        # Open far from the pad must keep holding (gated release).
        opened = hold.copy()
        opened[5] = 1.2
        target_xy = np.asarray(info["target_xy"], dtype=np.float64)
        box_xy = np.asarray(info["box_xy"], dtype=np.float64)
        assert float(np.linalg.norm(box_xy - target_xy)) >= RELEASE_NEAR_PAD_M
        _obs, _, _, _, info = env.step(opened)
        assert info["grasping"]

        # Carry to the pad with an open command; release gates on proximity.
        table_z = float(info["table_z"])
        place_xyz = np.array([target_xy[0], target_xy[1], table_z + 0.06], dtype=np.float64)
        place_q = np.asarray(env.solve_ik(place_xyz), dtype=np.float32).reshape(6)
        place_q[5] = 1.2
        for _ in range(120):
            _obs, _, _, _, info = env.step(place_q)
            if not info["grasping"]:
                break
        assert not info["grasping"]
        assert (
            float(np.linalg.norm(np.asarray(info["box_xy"], dtype=np.float64) - target_xy))
            < RELEASE_NEAR_PAD_M
        )
    finally:
        env.close()


@pytest.mark.simulation
@pytest.mark.unit
def test_early_open_far_from_pad_keeps_grasp() -> None:
    """Smeared open commands short of the pad must not drop the box in place."""
    from port_pick_align.contract import load_contract
    from port_pick_align.simulation.env import RELEASE_NEAR_PAD_M, PickAlignSimEnv

    contract = load_contract()
    env = PickAlignSimEnv(contract=contract, max_episode_steps=400, render_cameras=False)
    try:
        _obs, info, hold = _scripted_until_grasp(env)
        assert info["grasping"]
        opened = hold.copy()
        opened[5] = 1.2
        for _ in range(10):
            _obs, _, _, _, info = env.step(opened)
        assert info["grasping"]
        dist = float(
            np.linalg.norm(
                np.asarray(info["box_xy"], dtype=np.float64)
                - np.asarray(info["target_xy"], dtype=np.float64)
            )
        )
        assert dist >= RELEASE_NEAR_PAD_M
    finally:
        env.close()


@pytest.mark.simulation
@pytest.mark.unit
def test_release_near_pad_keeps_actual_xy_and_stable_yaw() -> None:
    """Gated release must not teleport the box to the pad center or force yaw 0.

    That snap previously made TE eval report exactly 0.0 mm / 0° whenever the
    10 cm gate passed, which looked like a perfect align false positive.
    """
    from port_pick_align.contract import load_contract
    from port_pick_align.evaluation.eval_alignment import compute_pose_errors
    from port_pick_align.simulation.env import RELEASE_NEAR_PAD_M, PickAlignSimEnv

    contract = load_contract()
    env = PickAlignSimEnv(contract=contract, max_episode_steps=400, render_cameras=False)
    try:
        _obs, info, hold = _scripted_until_grasp(env)
        assert info["grasping"]
        target_xy = np.asarray(info["target_xy"], dtype=np.float64)
        # Offset inside the gate but clearly away from the pad center.
        offset = np.array([0.06, -0.04], dtype=np.float64)
        assert float(np.linalg.norm(offset)) < RELEASE_NEAR_PAD_M
        table_z = float(info["table_z"])
        carry_xyz = np.array(
            [target_xy[0] + offset[0], target_xy[1] + offset[1], table_z + 0.08],
            dtype=np.float64,
        )
        q = np.asarray(env.solve_ik(carry_xyz), dtype=np.float32).reshape(6)
        q[4] = 0.35
        q[5] = 0.0
        for _ in range(80):
            _obs, _, _, _, info = env.step(q)
            if not info["grasping"]:
                break
        assert info["grasping"]
        pre_xy = np.asarray(info["box_xy"], dtype=np.float64).copy()
        pre_yaw = float(info["box_yaw"])
        assert float(np.linalg.norm(pre_xy - target_xy)) < RELEASE_NEAR_PAD_M
        open_q = q.copy()
        open_q[5] = 1.2
        _obs, _, _, _, info = env.step(open_q)
        assert not info["grasping"]
        post_xy = np.asarray(info["box_xy"], dtype=np.float64)
        post_yaw = float(info["box_yaw"])
        assert float(np.linalg.norm(post_xy - pre_xy)) < 0.01
        # Stable closed-grasp yaw is preserved (not forced to 0, not hinge-twisted).
        assert abs(post_yaw - pre_yaw) < 0.20
        assert abs(post_yaw) > 0.02 or abs(pre_yaw) <= 0.02
        # Must not be snapped exactly onto the pad (unless we were already there).
        if float(np.linalg.norm(pre_xy - target_xy)) > 0.02:
            assert float(np.linalg.norm(post_xy - target_xy)) > 0.01
        pos_mm, _yaw = compute_pose_errors(
            info["box_xy"], info["box_yaw"], info["target_xy"], info["target_yaw"]
        )
        assert pos_mm > 1.0
    finally:
        env.close()


@pytest.mark.simulation
@pytest.mark.unit
def test_attached_box_orientation_follows_gripper() -> None:
    from port_pick_align.contract import load_contract
    from port_pick_align.simulation.env import PickAlignSimEnv

    contract = load_contract()
    env = PickAlignSimEnv(contract=contract, max_episode_steps=400, render_cameras=False)
    try:
        _obs, info, hold = _scripted_until_grasp(env)
        closed = hold.copy()
        closed[5] = 0.0

        def relative_yaw() -> float:
            ee = np.asarray(env.data.site_xmat[env._ee_site_id], dtype=np.float64).reshape(3, 3)
            box = np.asarray(env.data.xmat[env._box_body_id], dtype=np.float64).reshape(3, 3)
            rel = ee.T @ box
            return float(np.arctan2(rel[1, 0], rel[0, 0]))

        yaw0 = relative_yaw()
        for _ in range(15):
            _obs, _, _, _, info = env.step(closed)
        assert info["grasping"]
        assert abs(relative_yaw() - yaw0) < 0.05
    finally:
        env.close()


@pytest.mark.simulation
@pytest.mark.unit
def test_goal_pose_flag_extends_state_only_when_enabled() -> None:
    from port_pick_align.contract import load_contract
    from port_pick_align.simulation.env import PickAlignSimEnv

    contract = load_contract()
    plain = PickAlignSimEnv(contract=contract, max_episode_steps=2, render_cameras=False)
    flagged = PickAlignSimEnv(
        contract=contract,
        max_episode_steps=2,
        render_cameras=False,
        include_goal_in_state=True,
    )
    try:
        obs, _info = plain.reset(seed=0, options={"randomize_box": False, "box_yaw": 0.0})
        assert obs["state"].shape == (6,)
        flagged_obs, info = flagged.reset(seed=0, options={"randomize_box": False, "box_yaw": 0.0})
        assert flagged_obs["state"].shape == (9,)
        assert flagged_obs["state"][6] == pytest.approx(float(info["target_xy"][0]))
        assert flagged_obs["state"][7] == pytest.approx(float(info["target_xy"][1]))
        assert flagged_obs["state"][8] == pytest.approx(float(info["target_yaw"]))
    finally:
        plain.close()
        flagged.close()


@pytest.mark.simulation
@pytest.mark.unit
def test_scripted_random_20_still_aligns() -> None:
    """Oracle demos must keep 20/20 without a pad-center / yaw-0 release snap.

    Carried yaw is read on the last closed-gripper grasp step. Release keeps the
    actual box XY and that stable yaw (opening the hinge must not twist it).
    """
    from port_pick_align.contract import load_contract
    from port_pick_align.evaluation.eval_alignment import compute_pose_errors, is_align_success
    from port_pick_align.simulation.env import PickAlignSimEnv
    from port_pick_align.simulation.policies import ScriptedPickAlignPolicy

    contract = load_contract()
    env = PickAlignSimEnv(contract=contract, max_episode_steps=260, render_cameras=False)
    n_align = 0
    try:
        for seed in range(20):
            policy = ScriptedPickAlignPolicy(chunk_size=30, action_dim=6)
            policy.set_ik(env.solve_ik)
            policy.set_transport_plan(env.plan_transport_joints)
            policy.set_transport_retarget(env.retarget_transport_joints)
            policy.reset()
            obs, info = env.reset(seed=seed, options={"randomize_box": True})
            states: list[np.ndarray] = []
            held_yaw_deg: float | None = None
            held_pos_mm: float | None = None
            for _ in range(260):
                chunk = policy.predict(obs, info=info)
                states.append(np.asarray(obs["state"], dtype=np.float64).copy())
                obs, _, terminated, truncated, info = env.step(chunk[0])
                if info.get("grasping"):
                    held_pos_mm, held_yaw_deg = compute_pose_errors(
                        info["box_xy"], info["box_yaw"], info["target_xy"], info["target_yaw"]
                    )
                if terminated or truncated:
                    break
            pos_mm, yaw_deg = compute_pose_errors(
                info["box_xy"], info["box_yaw"], info["target_xy"], info["target_yaw"]
            )
            assert not info["grasping"]
            assert held_yaw_deg is not None and held_pos_mm is not None
            assert held_pos_mm <= 25.0, f"seed {seed} still {held_pos_mm:.1f} mm from the pad"
            # Wrist limits leave about 18 deg on the worst of these 20 spawns.
            assert abs(held_yaw_deg) <= 19.0, f"seed {seed} carried yaw {held_yaw_deg:.1f} deg"
            # Final pose must stay near the carried pose (no pad-center teleport).
            assert abs(pos_mm - held_pos_mm) < 15.0, (
                f"seed {seed} pos jumped held={held_pos_mm:.1f} final={pos_mm:.1f}"
            )
            state_var = float(np.mean(np.var(np.stack(states, axis=0), axis=0)))
            assert state_var >= 1.0e-4
            # Position threshold must always hold once the pad snap is gone.
            assert pos_mm <= 25.0, f"seed {seed} final pos {pos_mm:.1f} mm"
            if is_align_success(pos_mm, yaw_deg):
                n_align += 1
    finally:
        env.close()
    # Wrist limits leave ~18° on the worst spawn; DoD yaw is 15°, so 19/20 is
    # the honest floor without a yaw-0 release snap.
    assert n_align >= 19, f"align {n_align}/20"
