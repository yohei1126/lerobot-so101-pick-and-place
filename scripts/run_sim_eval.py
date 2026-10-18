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
    samples_to_dicts,
    summarize,
    trial_outcome,
)
from port_pick_align.simulation.env import (
    GRIPPER_OPEN_THRESH,
    RELEASE_NEAR_PAD_M,
    PickAlignSimEnv,
    box_reset_options,
)
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
    temporal_ensemble: bool = False,
    temporal_ensemble_coeff: float = 0.01,
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
        return CheckpointPolicy(
            policy,
            chunk_size=chunk_size,
            device=device,
            temporal_ensemble=temporal_ensemble,
            temporal_ensemble_coeff=temporal_ensemble_coeff,
        )
    raise ValueError(f"unknown policy mode: {mode}")


def render_topdown_frame(
    info: dict[str, Any],
    *,
    height: int = 480,
    width: int = 640,
) -> np.ndarray:
    """RGB top-down schematic (no OpenGL) for rollout videos in headless envs."""
    img = np.full((height, width, 3), 40, dtype=np.uint8)
    # Table region in world: x in [-0.1, 0.6], y in [-0.3, 0.3]
    x0, x1 = -0.05, 0.60
    y0, y1 = -0.30, 0.30

    def to_px(xy: np.ndarray) -> tuple[int, int]:
        u = int((float(xy[0]) - x0) / (x1 - x0) * (width - 1))
        v = int((1.0 - (float(xy[1]) - y0) / (y1 - y0)) * (height - 1))
        return int(np.clip(u, 0, width - 1)), int(np.clip(v, 0, height - 1))

    def fill_rect(
        cx: int, cy: int, hw: int, hh: int, color: tuple[int, int, int]
    ) -> None:
        x_lo, x_hi = max(0, cx - hw), min(width, cx + hw)
        y_lo, y_hi = max(0, cy - hh), min(height, cy + hh)
        img[y_lo:y_hi, x_lo:x_hi] = color

    # Table
    fill_rect(width // 2, height // 2, width // 2 - 20, height // 2 - 20, (90, 75, 55))
    # Target (green)
    tx, ty = to_px(np.asarray(info["target_xy"]))
    fill_rect(tx, ty, 18, 14, (40, 200, 80))
    # Box (orange)
    bx, by = to_px(np.asarray(info["box_xy"]))
    fill_rect(bx, by, 12, 10, (220, 120, 40))
    # EE (red)
    ex, ey = to_px(np.asarray(info["ee_xy"]))
    fill_rect(ex, ey, 6, 6, (220, 40, 40))
    # Grasp indicator
    if info.get("grasping"):
        fill_rect(20, 20, 12, 12, (80, 160, 255))
    return img


def run_episode(
    env: PickAlignSimEnv,
    policy: Any,
    *,
    max_steps: int,
    joint_names: list[str],
    rr: Any | None,
    frames: list[np.ndarray] | None,
    seed: int = 0,
    randomize_box: bool = False,
    video_mode: str = "topdown",
    n_action_steps: int = 1,
) -> Any:
    if hasattr(policy, "reset"):
        policy.reset()
    if isinstance(policy, ScriptedPickAlignPolicy):
        policy.set_ik(env.solve_ik)
        policy.set_transport_plan(env.plan_transport_joints)
        policy.set_transport_retarget(env.retarget_transport_joints)

    obs, info = env.reset(
        seed=seed, options=box_reset_options(randomize_box=randomize_box)
    )
    initial_box_xy = [
        float(v) for v in np.asarray(info["box_xy"], dtype=np.float64).reshape(2)
    ]
    initial_box_yaw = float(info["box_yaw"])
    grasped_during = bool(info.get("grasping", False))
    chunk: np.ndarray | None = None
    chunk_i = 0
    horizon = max(1, int(n_action_steps))
    open_events: list[dict[str, float | bool | int]] = []
    for step in range(max_steps):
        if chunk is None or chunk_i >= min(horizon, int(chunk.shape[0])):
            chunk = policy.predict(obs, info=info)
            chunk_i = 0
        assert chunk is not None
        action = chunk[chunk_i]
        chunk_i += 1
        if rr is not None:
            _log_rerun(rr, step=step, obs=obs, chunk=chunk, joint_names=joint_names)
        if frames is not None:
            if video_mode == "mujoco":
                top = obs["top"][:, :, ::-1]
                wrist = obs["wrist"][:, :, ::-1]
                frames.append(np.concatenate([top, wrist], axis=1))
            else:
                frames.append(
                    render_topdown_frame(
                        info,
                        height=int(env.render_height),
                        width=int(env.render_width),
                    )
                )
        grip_cmd = float(action[5])
        if grip_cmd >= GRIPPER_OPEN_THRESH and info.get("grasping", False):
            box_xy = np.asarray(info["box_xy"], dtype=np.float64).reshape(2)
            pad_xy = np.asarray(info["target_xy"], dtype=np.float64).reshape(2)
            dist_m = float(np.linalg.norm(box_xy - pad_xy))
            open_events.append(
                {
                    "step": int(step),
                    "grip_cmd": grip_cmd,
                    "box_x": float(box_xy[0]),
                    "box_y": float(box_xy[1]),
                    "pad_x": float(pad_xy[0]),
                    "pad_y": float(pad_xy[1]),
                    "box_pad_dist_mm": dist_m * 1000.0,
                    "inside_release_gate": dist_m < RELEASE_NEAR_PAD_M,
                }
            )
        obs, _reward, terminated, truncated, info = env.step(action)
        grasped_during = grasped_during or bool(info.get("grasping", False))
        if terminated or truncated:
            break

    pos_mm, yaw_deg = compute_pose_errors(
        info["box_xy"], info["box_yaw"], info["target_xy"], info["target_yaw"]
    )
    sample = trial_outcome(
        position_error_mm=pos_mm,
        yaw_error_deg=yaw_deg,
        grasping_now=bool(info.get("grasping", False)),
        grasped_during=grasped_during,
        box_z=float(info["box_z"]),
        table_z=float(info["table_z"]),
        ee_xy=info["ee_xy"],
        box_xy=info["box_xy"],
        pad_xy=info["target_xy"],
    )
    final_box_yaw = float(info["box_yaw"])
    # Attach open-vs-distance diagnostics for JSON (not part of AlignmentSample).
    sample_dict = {
        "position_error_mm": sample.position_error_mm,
        "yaw_error_deg": sample.yaw_error_deg,
        "yaw_err_deg": sample.yaw_error_deg,
        "grasp_success": sample.grasp_success,
        "holding_at_end": sample.holding_at_end,
        "released_on_pad": sample.released_on_pad,
        "seed": int(seed),
        "initial_box_xy": initial_box_xy,
        "initial_box_yaw": initial_box_yaw,
        "final_box_xy": list(sample.final_box_xy)
        if sample.final_box_xy is not None
        else None,
        "final_box_yaw": final_box_yaw,
        "pad_xy": list(sample.pad_xy) if sample.pad_xy is not None else None,
        "open_while_holding": open_events,
        "n_open_outside_gate": sum(
            1 for event in open_events if not event["inside_release_gate"]
        ),
        "n_open_inside_gate": sum(
            1 for event in open_events if event["inside_release_gate"]
        ),
    }
    return sample, sample_dict


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
    p.add_argument(
        "--temporal-ensemble",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Blend overlapping ACT chunks (checkpoint policy only).",
    )
    p.add_argument("--temporal-ensemble-coeff", type=float, default=0.01)
    p.add_argument(
        "--n-action-steps",
        type=int,
        default=1,
        help="How many actions to execute from each predicted chunk before re-querying "
        "(1 = every-step replan; 30 = full ACT chunk). Temporal ensembling forces 1.",
    )
    p.add_argument("--rerun", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--save-video", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument(
        "--video-mode",
        choices=("topdown", "mujoco"),
        default="topdown",
        help="topdown=OpenGL-free schematic (default); mujoco=camera renders",
    )
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--randomize-box",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Randomize box XY and yaw (default: fixed spawn, yaw 0).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    contract = load_contract(args.contract)
    joint_names = list(contract["robot"]["joint_names"])
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    use_ensemble = bool(args.temporal_ensemble and args.policy == "checkpoint")
    if args.temporal_ensemble and args.policy != "checkpoint":
        print("temporal ensemble applies only to --policy checkpoint; ignoring it")
    n_action_steps = max(1, int(args.n_action_steps))
    if use_ensemble and n_action_steps != 1:
        print(
            "temporal ensembling re-queries every step; forcing --n-action-steps 1 "
            f"(was {n_action_steps})"
        )
        n_action_steps = 1
    policy = _build_policy(
        args.policy,
        contract,
        checkpoint=args.checkpoint,
        device=args.device,
        temporal_ensemble=use_ensemble,
        temporal_ensemble_coeff=args.temporal_ensemble_coeff,
    )
    # Checkpoint ACT needs real camera pixels. topdown video only changes the
    # saved schematic; it must not disable MuJoCo camera rendering (black images).
    render_cameras = (
        args.policy == "checkpoint" or args.video_mode == "mujoco" or args.rerun
    )
    env = PickAlignSimEnv(
        contract=contract,
        max_episode_steps=args.max_steps,
        render_cameras=render_cameras,
    )

    rr = None
    if args.rerun:
        import rerun as rr_mod

        rr = rr_mod
        rr.init("port_pick_align_sim", spawn=True)

    samples = []
    sample_rows: list[dict[str, Any]] = []
    frames: list[np.ndarray] | None = [] if args.save_video else None
    try:
        for ep in range(args.episodes):
            sample, sample_row = run_episode(
                env,
                policy,
                max_steps=args.max_steps,
                joint_names=joint_names,
                rr=rr,
                frames=frames if ep == 0 else None,
                seed=args.seed + ep,
                randomize_box=args.randomize_box,
                video_mode=args.video_mode,
                n_action_steps=n_action_steps,
            )
            samples.append(sample)
            sample_rows.append(sample_row)
            box_xy = sample.final_box_xy
            pad_xy = sample.pad_xy
            print(
                f"episode {ep}: pos_mm={sample.position_error_mm:.1f} "
                f"yaw_deg={sample.yaw_error_deg:.1f} grasp={sample.grasp_success} "
                f"holding_at_end={sample.holding_at_end} "
                f"released_on_pad={sample.released_on_pad} "
                f"box_xy={None if box_xy is None else [round(v, 4) for v in box_xy]} "
                f"pad_xy={None if pad_xy is None else [round(v, 4) for v in pad_xy]} "
                f"open_out_gate={sample_row['n_open_outside_gate']} "
                f"open_in_gate={sample_row['n_open_inside_gate']}"
            )
    finally:
        env.close()

    summary = summarize(samples)
    thresholds = {
        "align_success_rate_min": 0.85,
        "grasp_success_rate_min": 0.90,
        "mean_position_error_mm_max": 25.0,
        "mean_abs_yaw_error_deg_max": 15.0,
    }
    met = (
        float(summary["align_success_rate"]) >= thresholds["align_success_rate_min"]
        and float(summary["grasp_success_rate"]) >= thresholds["grasp_success_rate_min"]
        and float(summary["mean_position_error_mm"])
        < thresholds["mean_position_error_mm_max"]
        and float(summary["mean_abs_yaw_error_deg"])
        < thresholds["mean_abs_yaw_error_deg_max"]
    )
    metrics_path = out_dir / "metrics.json"
    payload = {
        "status": "measured",
        "policy": args.policy,
        "episodes": args.episodes,
        "max_steps": args.max_steps,
        "seed": args.seed,
        "randomize_box": args.randomize_box,
        "temporal_ensemble": use_ensemble,
        "temporal_ensemble_coeff": args.temporal_ensemble_coeff
        if use_ensemble
        else None,
        "n_action_steps": n_action_steps,
        "device": args.device,
        "checkpoint": str(args.checkpoint) if args.policy == "checkpoint" else None,
        "thresholds": thresholds,
        "thresholds_met": met,
        "summary": summary,
        # Prefer the richer per-episode rows (raw XY + open-gate diagnostics).
        "samples": sample_rows if sample_rows else samples_to_dicts(samples),
    }
    metrics_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {metrics_path}")
    print(json.dumps(summary, indent=2))
    print(
        "aggregate: "
        f"align={summary['align_success_rate']:.3f} "
        f"grasp={summary['grasp_success_rate']:.3f} "
        f"mean_pos_mm={summary['mean_position_error_mm']:.1f} "
        f"median_pos_mm={summary['median_position_error_mm']:.1f} "
        f"mean_abs_yaw_deg={summary['mean_abs_yaw_error_deg']:.2f} "
        f"median_abs_yaw_deg={summary['median_abs_yaw_error_deg']:.2f}"
    )
    print(f"thresholds_met={met}")

    if frames:
        video_path = out_dir / "sim_rollout.mp4"
        save_video(frames, video_path, fps=float(contract["cameras"]["top"]["fps"]))
        print(f"wrote {video_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
