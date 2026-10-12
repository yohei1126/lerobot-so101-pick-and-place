#!/usr/bin/env python3
"""Closed-loop MuJoCo pick-and-align evaluation (mock / checkpoint / scripted)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "port_pick_align" / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "port_pick_align" / "src"))

from port_pick_align.contract import load_contract
from port_pick_align.evaluation.eval_alignment import (
    compute_pose_errors,
    infer_grasp_success,
    record_sample,
    samples_to_dicts,
    summarize,
)
from port_pick_align.simulation.env import PickAlignSimEnv
from port_pick_align.simulation.policies import (
    CheckpointPolicy,
    MockPolicy,
    ScriptedPickAlignPolicy,
)


def _rr_scalar(rr: Any, value: float) -> Any:
    if hasattr(rr, "Scalars"):
        return rr.Scalars(value)
    return rr.Scalar(value)


def _rr_set_time_sequence(rr: Any, timeline: str, sequence: int) -> None:
    if hasattr(rr, "set_time_sequence"):
        rr.set_time_sequence(timeline, sequence)
        return
    rr.set_time(timeline, sequence=sequence)


def _log_rerun(
    rr: Any,
    *,
    step: int,
    obs: dict[str, np.ndarray],
    chunk: np.ndarray,
    joint_names: list[str],
) -> None:
    _rr_set_time_sequence(rr, "step", step)
    # BGR → RGB for Rerun
    top_rgb = obs["top"][:, :, ::-1]
    wrist_rgb = obs["wrist"][:, :, ::-1]
    rr.log("cameras/top", rr.Image(top_rgb))
    rr.log("cameras/wrist", rr.Image(wrist_rgb))
    state = obs["state"]
    for i, name in enumerate(joint_names):
        rr.log(f"state/joints/{name}", _rr_scalar(rr, float(state[i])))
    for i, name in enumerate(joint_names):
        for t in range(chunk.shape[0]):
            _rr_set_time_sequence(rr, "chunk_step", t)
            rr.log(f"policy/action_chunk/{name}", _rr_scalar(rr, float(chunk[t, i])))
    _rr_set_time_sequence(rr, "step", step)
    if hasattr(rr, "Tensor"):
        rr.log("policy/action_chunk/tensor", rr.Tensor(chunk))


def _build_policy(
    mode: str,
    contract: dict[str, Any],
    *,
    checkpoint: Path | None,
    device: str,
) -> Any:
    chunk_size = int(contract["model"]["chunk_size"])
    action_dim = int(contract["model"]["action_dim"])
    if mode == "mock":
        return MockPolicy(chunk_size=chunk_size, action_dim=action_dim)
    if mode == "scripted":
        return ScriptedPickAlignPolicy(chunk_size=chunk_size, action_dim=action_dim)
    if mode == "checkpoint":
        if checkpoint is None or not checkpoint.is_file():
            raise FileNotFoundError(f"checkpoint not found: {checkpoint}")
        from port_pick_align.training.train_act import load_policy_from_checkpoint

        policy = load_policy_from_checkpoint(checkpoint, contract, device=device)
        return CheckpointPolicy(policy, chunk_size=chunk_size, device=device)
    raise ValueError(f"unknown policy mode: {mode}")


def run_episode(
    env: PickAlignSimEnv,
    policy: Any,
    *,
    max_steps: int,
    joint_names: list[str],
    rr: Any | None,
    frames: list[np.ndarray] | None,
) -> Any:
    if hasattr(policy, "reset"):
        policy.reset()
    obs, info = env.reset()
    for step in range(max_steps):
        chunk = policy.predict(obs)
        action = chunk[0]
        if rr is not None:
            _log_rerun(rr, step=step, obs=obs, chunk=chunk, joint_names=joint_names)
        if frames is not None:
            # Side-by-side top | wrist (RGB for video)
            top = obs["top"][:, :, ::-1]
            wrist = obs["wrist"][:, :, ::-1]
            frames.append(np.concatenate([top, wrist], axis=1))
        obs, _reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break

    pos_mm, yaw_deg = compute_pose_errors(
        info["box_xy"], info["box_yaw"], info["target_xy"], info["target_yaw"]
    )
    grasp = infer_grasp_success(
        box_z=float(info["box_z"]),
        table_z=float(info["table_z"]),
        ee_xy=info["ee_xy"],
        box_xy=info["box_xy"],
    )
    # At episode end, also count as grasp if box stayed near target after release.
    near_target = pos_mm < 50.0
    grasp = bool(grasp or near_target)
    return record_sample(pos_mm, yaw_deg, grasp)


def save_video(frames: list[np.ndarray], path: Path, fps: float = 30.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import imageio.v2 as imageio
    except ImportError:
        import imageio  # type: ignore[no-redef]

    imageio.mimsave(path, frames, fps=fps)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--contract",
        type=Path,
        default=REPO_ROOT / "configs" / "contract.yaml",
    )
    p.add_argument(
        "--policy",
        choices=("mock", "checkpoint", "scripted"),
        default="scripted",
    )
    p.add_argument(
        "--checkpoint",
        type=Path,
        default=REPO_ROOT / "checkpoints" / "synthetic_act" / "best_model.pt",
    )
    p.add_argument("--episodes", type=int, default=1)
    p.add_argument("--max-steps", type=int, default=260)
    p.add_argument("--output-dir", type=Path, default=REPO_ROOT / "outputs" / "eval")
    p.add_argument("--device", default="cpu")
    p.add_argument("--rerun", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--save-video", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    contract = load_contract(args.contract)
    joint_names = list(contract["robot"]["joint_names"])
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    policy = _build_policy(
        args.policy, contract, checkpoint=args.checkpoint, device=args.device
    )
    env = PickAlignSimEnv(contract=contract, max_episode_steps=args.max_steps)

    rr = None
    if args.rerun:
        import rerun as rr_mod

        rr = rr_mod
        rr.init("port_pick_align_sim", spawn=True)

    samples = []
    frames: list[np.ndarray] | None = [] if args.save_video else None
    try:
        for ep in range(args.episodes):
            sample = run_episode(
                env,
                policy,
                max_steps=args.max_steps,
                joint_names=joint_names,
                rr=rr,
                frames=frames if ep == 0 else None,
            )
            samples.append(sample)
            print(
                f"episode {ep}: pos_mm={sample.position_error_mm:.1f} "
                f"yaw_deg={sample.yaw_error_deg:.1f} grasp={sample.grasp_success}"
            )
    finally:
        env.close()

    summary = summarize(samples)
    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {"summary": summary, "samples": samples_to_dicts(samples)},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {metrics_path}")
    print(json.dumps(summary, indent=2))

    if frames:
        video_path = out_dir / "sim_rollout.mp4"
        save_video(frames, video_path, fps=float(contract["cameras"]["top"]["fps"]))
        print(f"wrote {video_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
