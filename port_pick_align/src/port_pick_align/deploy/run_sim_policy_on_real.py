"""CLI: run a sim-trained ACT checkpoint on the real SO-101 follower.

Dry-run (recommended first):

  python -m port_pick_align.deploy.run_sim_policy_on_real \\
    --checkpoint $LEROBOT_HW_ROOT/outputs/sim_act/best_model.pt \\
    --port $PORT_FOLLOWER \\
    --dry-run \\
    --episode-time-s 20

Live (12V switch under hand, low speed):

  python -m port_pick_align.deploy.run_sim_policy_on_real \\
    --checkpoint $LEROBOT_HW_ROOT/outputs/sim_act/best_model.pt \\
    --port $PORT_FOLLOWER \\
    --max-delta-deg 3 \\
    --episode-time-s 20
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from port_pick_align.contract import DEFAULT_CONTRACT_PATH, load_contract, validate_contract
from port_pick_align.deploy.conversion import (
    JOINT_NAMES,
    conversion_config_from_contract,
)
from port_pick_align.deploy.sim_policy_wrapper import (
    SimTrainedACTOnReal,
    format_action_line,
)
from port_pick_align.training.train_act import load_policy_from_checkpoint, resolve_device


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a sim-trained ACT policy on the real SO-101 follower with "
            "rad↔deg / gripper conversion and safety clamps."
        )
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Path to sim-trained best_model.pt / last.pt from train_act.",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT_PATH,
        help="Contract YAML (joint limits / camera size). Default: configs/contract.yaml",
    )
    parser.add_argument(
        "--port",
        type=str,
        required=True,
        help="Follower serial port, e.g. /dev/tty.usbmodemXXXX (from lerobot-find-port).",
    )
    parser.add_argument("--robot-id", type=str, default="follower")
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="mps, cuda, or cpu. Default: mps if available, else cuda, else cpu.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read observations and print converted actions; never send_action.",
    )
    parser.add_argument(
        "--episode-time-s",
        type=float,
        default=20.0,
        help="Wall-clock episode duration in seconds (default 20).",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="Control loop rate (default 30, matching contract / record).",
    )
    parser.add_argument(
        "--n-action-steps",
        type=int,
        default=1,
        help="Chunk steps to execute between replans (default 1 for safety).",
    )
    parser.add_argument(
        "--temporal-ensemble",
        action="store_true",
        help="Enable ACT temporal ensembling (replan every step).",
    )
    parser.add_argument(
        "--max-delta-deg",
        type=float,
        default=5.0,
        help="Per-step arm joint cap in degrees (default 5). Set <=0 to disable.",
    )
    parser.add_argument(
        "--max-delta-gripper",
        type=float,
        default=10.0,
        help="Per-step gripper cap on 0–100 scale (default 10). Set <=0 to disable.",
    )
    parser.add_argument(
        "--robot-max-relative-target",
        type=float,
        default=5.0,
        help=(
            "Also set LeRobot robot.max_relative_target (degrees) for live sends. "
            "Ignored in --dry-run. Set <=0 to disable."
        ),
    )
    parser.add_argument(
        "--gripper-closed-is-high",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "LeRobot polarity: higher gripper.pos = more closed (default true). "
            "Pass --no-gripper-closed-is-high for units.py open-percent sense."
        ),
    )
    parser.add_argument(
        "--real-image-color",
        choices=("rgb", "bgr"),
        default="rgb",
        help="Color order of OpenCV frames (LeRobot default rgb).",
    )
    parser.add_argument(
        "--top-camera-index",
        type=int,
        default=1,
        help="OpenCV index for top camera (bring-up default 1).",
    )
    parser.add_argument(
        "--wrist-camera-index",
        type=int,
        default=0,
        help="OpenCV index for wrist camera (bring-up default 0).",
    )
    parser.add_argument("--camera-width", type=int, default=640)
    parser.add_argument("--camera-height", type=int, default=480)
    parser.add_argument("--camera-fps", type=int, default=30)
    parser.add_argument(
        "--print-every",
        type=int,
        default=1,
        help="Print converted action every N steps (default 1).",
    )
    return parser.parse_args(argv)


def _build_robot(args: argparse.Namespace, *, dry_run: bool) -> Any:
    from lerobot.cameras.opencv import OpenCVCameraConfig
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    max_rel: float | None
    if dry_run or args.robot_max_relative_target <= 0:
        max_rel = None
    else:
        max_rel = float(args.robot_max_relative_target)

    config = SO101FollowerConfig(
        port=args.port,
        id=args.robot_id,
        max_relative_target=max_rel,
        use_degrees=True,
        cameras={
            "top": OpenCVCameraConfig(
                index_or_path=int(args.top_camera_index),
                width=int(args.camera_width),
                height=int(args.camera_height),
                fps=int(args.camera_fps),
            ),
            "wrist": OpenCVCameraConfig(
                index_or_path=int(args.wrist_camera_index),
                width=int(args.camera_width),
                height=int(args.camera_height),
                fps=int(args.camera_fps),
            ),
        },
    )
    robot = SO101Follower(config)
    robot.connect()
    return robot


def _optional_delta(value: float) -> float | None:
    return None if value <= 0 else float(value)


def run(args: argparse.Namespace) -> int:
    if args.episode_time_s <= 0:
        raise SystemExit("--episode-time-s must be > 0")
    if args.fps <= 0:
        raise SystemExit("--fps must be > 0")
    if not args.checkpoint.is_file():
        raise SystemExit(f"Checkpoint not found: {args.checkpoint}")

    contract = load_contract(args.contract)
    validate_contract(contract)
    device = resolve_device(args.device)
    conv = conversion_config_from_contract(
        contract,
        gripper_closed_is_high=bool(args.gripper_closed_is_high),
        max_delta_deg=_optional_delta(args.max_delta_deg),
        max_delta_gripper=_optional_delta(args.max_delta_gripper),
        real_image_color=args.real_image_color,  # type: ignore[arg-type]
    )
    chunk_size = int(contract["model"]["chunk_size"])

    print(
        json.dumps(
            {
                "mode": "dry-run" if args.dry_run else "live",
                "checkpoint": str(args.checkpoint),
                "device": device,
                "port": args.port,
                "robot_id": args.robot_id,
                "episode_time_s": args.episode_time_s,
                "fps": args.fps,
                "gripper_closed_is_high": conv.gripper_closed_is_high,
                "max_delta_deg": conv.max_delta_deg,
                "max_delta_gripper": conv.max_delta_gripper,
                "joint_order": list(JOINT_NAMES),
                "cameras": {
                    "top_index": args.top_camera_index,
                    "wrist_index": args.wrist_camera_index,
                    "size": [args.camera_width, args.camera_height],
                    "color": args.real_image_color,
                },
            },
            indent=2,
        ),
        flush=True,
    )
    if not args.dry_run:
        print(
            "LIVE MODE: motors will move. Keep a hand on the 12V power switch. "
            "Ctrl+C aborts the loop (then support the arm — torque may drop).",
            flush=True,
        )

    policy = load_policy_from_checkpoint(args.checkpoint, contract, device=device)
    wrapper = SimTrainedACTOnReal(
        policy,
        conv,
        device=device,
        chunk_size=chunk_size,
        n_action_steps=int(args.n_action_steps),
        temporal_ensemble=bool(args.temporal_ensemble),
    )

    robot = _build_robot(args, dry_run=bool(args.dry_run))
    period = 1.0 / float(args.fps)
    deadline = time.perf_counter() + float(args.episode_time_s)
    step = 0
    wrapper.reset()
    try:
        while time.perf_counter() < deadline:
            t0 = time.perf_counter()
            obs = robot.get_observation()
            action, debug = wrapper.predict_real_action(obs)
            if not args.dry_run:
                robot.send_action(action)
            if step % max(1, int(args.print_every)) == 0:
                prefix = "DRY" if args.dry_run else "LIVE"
                print(
                    f"[{prefix}] step={step:04d} {format_action_line(action)} "
                    f"sim_grip={float(debug['sim_action'][5]):+.3f}rad",
                    flush=True,
                )
            step += 1
            sleep_s = period - (time.perf_counter() - t0)
            if sleep_s > 0:
                time.sleep(sleep_s)
    except KeyboardInterrupt:
        print("Interrupted by user.", flush=True)
    finally:
        print(f"Disconnecting after {step} steps…", flush=True)
        robot.disconnect()

    print(f"Done. steps={step} dry_run={bool(args.dry_run)}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
