"""Shared helpers for running trained policies on the real SO-101 follower.

Safety model:
  * dry-run (default): connects ONLY the serial bus (read) + cameras. Does NOT call
    robot.connect()/configure(), never writes torque/goal registers, never calls
    send_action. On exit the bus is closed WITHOUT touching torque.
  * live (--live): standard robot.connect() with max_relative_target, per-step clamp,
    send_action. On exit robot.disconnect() (LeRobot default: disable torque ->
    support the arm!).

Paths default to ``$LEROBOT_HW_ROOT`` (or ``~/work/lerobot-hw``) for logs / rollouts.
Override with env or CLI flags; no absolute ``/Users/...`` paths.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import signal
import sys
import time
from pathlib import Path

import numpy as np

JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
TASK = "Pick up the yellow sponge and place it on the white paper"
# Bring-up default (2026-10-18/22); override with --port or PORT_FOLLOWER.
DEFAULT_PORT = "/dev/tty.usbmodem5B8E1163071"
DEFAULT_HW_ROOT = Path.home() / "work" / "lerobot-hw"


def hw_root() -> Path:
    """Hardware workspace root (datasets, outputs, venv)."""
    env = os.environ.get("LEROBOT_HW_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return DEFAULT_HW_ROOT


def log_dir() -> Path:
    env = os.environ.get("LEROBOT_LOG_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return hw_root() / "outputs" / "logs"


def rollout_dir() -> Path:
    env = os.environ.get("LEROBOT_ROLLOUT_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return hw_root() / "outputs" / "rollouts"


class Tee:
    def __init__(self, path: Path):
        self.f = open(path, "a", buffering=1)
        self.out = sys.stdout

    def write(self, s):
        self.out.write(s)
        self.f.write(s)

    def flush(self):
        self.out.flush()
        self.f.flush()

    def fileno(self):
        return self.out.fileno()

    def isatty(self):
        return self.out.isatty()


def setup_log(name: str) -> Path:
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    sys.stdout = Tee(p)  # type: ignore[assignment]
    sys.stderr = sys.stdout  # type: ignore[assignment]
    print(f"[log] {p}", flush=True)
    return p


def add_common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--live", action="store_true", help="Actually send actions (default: dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="(default) never send actions")
    ap.add_argument(
        "--port",
        default=os.environ.get("PORT_FOLLOWER", DEFAULT_PORT),
        help="Follower serial port (env PORT_FOLLOWER overrides default).",
    )
    ap.add_argument("--robot-id", default="follower")
    ap.add_argument("--top-index", type=int, default=1)
    ap.add_argument("--wrist-index", type=int, default=0)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--episode-time-s", type=float, default=20.0)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument(
        "--max-delta-deg", type=float, default=3.0, help="per-step joint cap (deg), <=0 off"
    )
    ap.add_argument(
        "--max-delta-gripper",
        type=float,
        default=5.0,
        help="per-step gripper cap (0-100), <=0 off",
    )
    ap.add_argument(
        "--max-relative-target",
        type=float,
        default=5.0,
        help="LeRobot robot.max_relative_target (live)",
    )
    ap.add_argument("--device", default="mps")
    ap.add_argument("--print-every", type=int, default=1)
    ap.add_argument(
        "--save-video",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Save top|wrist mp4 under LEROBOT_ROLLOUT_DIR / outputs/rollouts/. "
            "Default: ON for --live, OFF for dry-run. Use --no-save-video to disable."
        ),
    )


def resolve_save_video(args: argparse.Namespace) -> bool:
    """Default --save-video to True when --live, unless explicitly set."""
    explicit = getattr(args, "save_video", None)
    if explicit is not None:
        return bool(explicit)
    return is_live(args)


def is_live(args: argparse.Namespace) -> bool:
    """Resolve live vs dry-run. Default is dry-run; --live and --dry-run are exclusive."""
    if bool(getattr(args, "dry_run", False)) and bool(getattr(args, "live", False)):
        raise SystemExit("--dry-run and --live are exclusive")
    return bool(getattr(args, "live", False))


def build_robot(args, live: bool):
    from lerobot.cameras.opencv import OpenCVCameraConfig
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    cams = {
        "top": OpenCVCameraConfig(
            index_or_path=args.top_index, width=args.width, height=args.height, fps=30
        ),
        "wrist": OpenCVCameraConfig(
            index_or_path=args.wrist_index, width=args.width, height=args.height, fps=30
        ),
    }
    cfg = SO101FollowerConfig(
        port=args.port,
        id=args.robot_id,
        use_degrees=True,
        cameras=cams,
        max_relative_target=(
            float(args.max_relative_target) if live and args.max_relative_target > 0 else None
        ),
    )
    robot = SO101Follower(cfg)
    if live:
        robot.connect()  # standard: configure + torque on
    else:
        # read-only: open serial + cameras; no configure(), no torque writes
        robot.bus.connect()
        try:
            for cam in robot.cameras.values():
                cam.connect()
        except BaseException:
            close_robot(robot, live=False)
            raise
    return robot


def close_robot(robot, live: bool) -> None:
    if robot is None:
        return
    try:
        if live:
            robot.disconnect()  # LeRobot default: disable_torque_on_disconnect=True
        else:
            try:
                robot.bus.disconnect(disable_torque=False)
            except Exception as e:  # noqa: BLE001
                print(f"[warn] bus disconnect: {e}")
            for cam in robot.cameras.values():
                try:
                    cam.disconnect()
                except Exception as e:  # noqa: BLE001
                    print(f"[warn] cam disconnect: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] disconnect error: {e}")
    print("[robot] disconnected", flush=True)


def obs_state(obs) -> np.ndarray:
    return np.array([float(obs[f"{j}.pos"]) for j in JOINTS], dtype=np.float32)


class Clamp:
    """Per-step delta clamp relative to the last commanded target (or current state)."""

    def __init__(self, max_deg: float, max_grip: float):
        self.max_deg = max_deg
        self.max_grip = max_grip
        self.last: np.ndarray | None = None

    def __call__(self, target: np.ndarray, state: np.ndarray) -> np.ndarray:
        ref = self.last if self.last is not None else state
        out = target.astype(np.float32).copy()
        if self.max_deg > 0:
            out[:5] = np.clip(out[:5], ref[:5] - self.max_deg, ref[:5] + self.max_deg)
        if self.max_grip > 0:
            out[5] = np.clip(out[5], ref[5] - self.max_grip, ref[5] + self.max_grip)
        out[5] = np.clip(out[5], 0.0, 100.0)
        self.last = out.copy()
        return out


def action_dict(a: np.ndarray) -> dict:
    return {f"{j}.pos": float(a[i]) for i, j in enumerate(JOINTS)}


def fmt(a: np.ndarray) -> str:
    return " ".join(f"{j[:5]}={a[i]:+7.2f}" for i, j in enumerate(JOINTS))


class VideoSaver:
    def __init__(self, name: str, fps: float, enabled: bool):
        self.w = None
        self.enabled = enabled
        self.path = rollout_dir() / f"{name}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        self.fps = fps

    def add(self, obs):
        if not self.enabled:
            return
        import cv2

        frame = np.concatenate([obs["top"], obs["wrist"]], axis=1)[:, :, ::-1]
        if self.w is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            h, w = frame.shape[:2]
            self.w = cv2.VideoWriter(
                str(self.path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h)
            )
        self.w.write(np.ascontiguousarray(frame))

    def close(self):
        if self.w is not None:
            self.w.release()
            print(f"[video] saved {self.path}", flush=True)


def install_sigterm():
    def _h(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _h)


def run_loop(args, name: str, step_fn, reset_fn=None) -> int:
    """step_fn(obs, state) -> (target np[6], info str). Handles robot, clamp, timing, Ctrl-C."""
    live = is_live(args)
    mode = (
        "LIVE (motors WILL move; hand on 12V switch)"
        if live
        else "DRY-RUN (no send_action, no torque writes)"
    )
    print(f"[mode] {mode}", flush=True)
    install_sigterm()
    clamp = Clamp(args.max_delta_deg, args.max_delta_gripper)
    save_video = resolve_save_video(args)
    args.save_video = save_video  # reflect resolved default in logs
    print(f"[video] save_video={save_video}", flush=True)
    vid = VideoSaver(name, args.fps, save_video)
    robot = None
    step = 0
    lat: list[float] = []
    try:
        robot = build_robot(args, live)
        if reset_fn:
            reset_fn()
        period = 1.0 / args.fps
        t_end = time.perf_counter() + args.episode_time_s
        while time.perf_counter() < t_end:
            t0 = time.perf_counter()
            obs = robot.get_observation()
            st = obs_state(obs)
            t1 = time.perf_counter()
            target, info = step_fn(obs, st)
            t2 = time.perf_counter()
            lat.append((t2 - t1) * 1000)
            safe = clamp(np.asarray(target, dtype=np.float32), st)
            if live:
                robot.send_action(action_dict(safe))
            vid.add(obs)
            if step % max(1, args.print_every) == 0:
                tag = "LIVE" if live else "DRY"
                print(
                    f"[{tag}] {step:04d} state  {fmt(st)}\n"
                    f"[{tag}] {step:04d} target {fmt(np.asarray(target))}\n"
                    f"[{tag}] {step:04d} safe   {fmt(safe)}  infer={lat[-1]:.0f}ms {info}",
                    flush=True,
                )
            step += 1
            dt = period - (time.perf_counter() - t0)
            if dt > 0:
                time.sleep(dt)
    except KeyboardInterrupt:
        print("\n[ctrl-c] interrupted", flush=True)
    finally:
        close_robot(robot, live)
        vid.close()
    if lat:
        a = np.array(lat)
        print(
            f"[done] steps={step} infer_ms mean={a.mean():.1f} "
            f"p50={np.median(a):.1f} max={a.max():.1f} (max = replan steps)",
            flush=True,
        )
    return 0
