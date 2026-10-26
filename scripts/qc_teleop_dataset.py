#!/usr/bin/env python3
"""QC recorded SO-101 teleop / demo LeRobot v3 datasets.

Per episode this reports length, mean arm motion, how long the arm stays on
the opening pose, shoulder_lift lag, the joint with the largest mean
|action-state|, and action std. Videos are not decoded.

Flags:
  LOW_MOTION      high   busiest arm joint is near-static for the whole episode
  LONG_HEAD_IDLE  warn   opening pose is held longer than --head-idle-s
  HIGH_LAG        high   some joint's mean |action-state| is at least --high-lag-deg

Head idle is the frame index where any non-gripper joint first leaves the
opening pose by --motion-eps-deg. A short pause is printed and left unflagged.
--strict exits non-zero when a high-severity flag is present.

Example::

  source "$HOME/work/lerobot-hw/.venv/bin/activate"
  python scripts/qc_teleop_dataset.py \\
    --root "$HOME/work/lerobot-hw/datasets/so101_pick_sponge_layout20261026_20261027" \\
    --root "$HOME/work/lerobot-hw/datasets/so101_pick_sponge_layout20261026_20261027_batch2"
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

LOW_MOTION = "LOW_MOTION"
LONG_HEAD_IDLE = "LONG_HEAD_IDLE"
HIGH_LAG = "HIGH_LAG"
HIGH_FLAGS = frozenset({LOW_MOTION, HIGH_LAG})
WARN_FLAGS = frozenset({LONG_HEAD_IDLE})
FLAG_ORDER = (LOW_MOTION, LONG_HEAD_IDLE, HIGH_LAG)


class QcError(Exception):
    """A dataset could not be scored."""


@dataclass(frozen=True)
class QcThresholds:
    motion_eps_deg: float = 1.0
    head_idle_s: float = 2.0
    low_motion_std_deg: float = 5.0
    high_lag_deg: float = 6.0


@dataclass(frozen=True)
class _Joints:
    names: list[str]
    arm: list[int]
    shoulder_lift: int | None
    elbow: int | None

    def label(self, index: int) -> str:
        name = self.names[index]
        name = name.removesuffix(".pos")
        return f"{name}(dim{index})"


@dataclass(frozen=True)
class EpisodeQc:
    dataset: str
    root: str
    episode_index: int
    num_frames: int
    fps: float
    mean_motion_deg_per_frame: float
    head_idle_frames: int
    head_idle_s: float
    head_idle_fraction: float
    frames_to_first_motion: int | None
    lag_shoulder_lift_deg: float | None
    max_lag_joint: str
    max_lag_deg: float
    action_std_arm_max: float
    action_std_shoulder_lift: float | None
    action_std_elbow_flex: float | None
    lag_by_joint: str
    action_std_by_joint: str
    flags: tuple[str, ...]
    severity: str


def joint_layout(names: list[str]) -> _Joints:
    """Arm joints are every name without 'gripper'. dim1 is shoulder_lift when unnamed."""
    gripper = [i for i, name in enumerate(names) if "gripper" in name.lower()]
    arm = [i for i in range(len(names)) if i not in gripper]
    if not arm:
        arm = list(range(len(names)))
    shoulder = next(
        (i for i, name in enumerate(names) if "shoulder_lift" in name.lower()), None
    )
    if shoulder is None and len(names) >= 2 and names[1].lower().startswith("dim"):
        shoulder = 1
    elbow = next((i for i, name in enumerate(names) if "elbow" in name.lower()), None)
    return _Joints(names=list(names), arm=arm, shoulder_lift=shoulder, elbow=elbow)


def _severity(flags: tuple[str, ...]) -> str:
    if any(flag in HIGH_FLAGS for flag in flags):
        return "high"
    if any(flag in WARN_FLAGS for flag in flags):
        return "warn"
    return "ok"


def qc_episode(
    action: np.ndarray,
    state: np.ndarray,
    *,
    joint_names: list[str],
    fps: float,
    thresholds: QcThresholds,
    dataset: str = "",
    root: str = "",
    episode_index: int = 0,
) -> EpisodeQc:
    """Score one episode. action and state are (T, D) in dataset units (degrees / gripper)."""
    action = np.asarray(action, dtype=np.float64)
    state = np.asarray(state, dtype=np.float64)
    if action.ndim != 2 or state.shape != action.shape:
        raise QcError(
            f"{dataset} ep{episode_index}: action shape {action.shape} != state shape {state.shape}"
        )
    if action.shape[1] != len(joint_names):
        raise QcError(
            f"{dataset} ep{episode_index}: {action.shape[1]} joints, names={joint_names}"
        )
    if fps <= 0:
        raise QcError(f"fps must be positive, got {fps}")

    joints = joint_layout(joint_names)
    num_frames = int(action.shape[0])
    arm = joints.arm
    if num_frames >= 2:
        step = np.abs(np.diff(action[:, arm], axis=0))
        mean_motion = float(step.mean()) if step.size else 0.0
    else:
        mean_motion = 0.0

    action_std = np.std(action, axis=0) if num_frames else np.zeros(action.shape[1])
    arm_std_max = float(action_std[arm].max()) if num_frames and arm else 0.0

    if num_frames == 0:
        head_idle_frames = 0
        frames_to_motion: int | None = None
    else:
        depart = np.max(np.abs(action[:, arm] - action[0, arm]), axis=1)
        moved = np.flatnonzero(depart >= thresholds.motion_eps_deg)
        if moved.size == 0:
            head_idle_frames = num_frames
            frames_to_motion = None
        else:
            head_idle_frames = int(moved[0])
            frames_to_motion = head_idle_frames
    head_idle_s = head_idle_frames / fps
    head_idle_fraction = (head_idle_frames / num_frames) if num_frames else 0.0

    lag = (
        np.mean(np.abs(action - state), axis=0)
        if num_frames
        else np.zeros(action.shape[1])
    )
    max_lag_index = int(np.argmax(lag)) if lag.size else 0
    max_lag_deg = float(lag[max_lag_index]) if lag.size else 0.0
    lag_sl = (
        float(lag[joints.shoulder_lift]) if joints.shoulder_lift is not None else None
    )
    std_sl = (
        float(action_std[joints.shoulder_lift])
        if joints.shoulder_lift is not None
        else None
    )
    std_elbow = float(action_std[joints.elbow]) if joints.elbow is not None else None

    flags: list[str] = []
    if arm_std_max < thresholds.low_motion_std_deg:
        flags.append(LOW_MOTION)
    if head_idle_s > thresholds.head_idle_s:
        flags.append(LONG_HEAD_IDLE)
    if max_lag_deg >= thresholds.high_lag_deg:
        flags.append(HIGH_LAG)
    ordered = tuple(flag for flag in FLAG_ORDER if flag in flags)

    return EpisodeQc(
        dataset=dataset,
        root=root,
        episode_index=episode_index,
        num_frames=num_frames,
        fps=fps,
        mean_motion_deg_per_frame=mean_motion,
        head_idle_frames=head_idle_frames,
        head_idle_s=head_idle_s,
        head_idle_fraction=head_idle_fraction,
        frames_to_first_motion=frames_to_motion,
        lag_shoulder_lift_deg=lag_sl,
        max_lag_joint=joints.label(max_lag_index) if joints.names else "",
        max_lag_deg=max_lag_deg,
        action_std_arm_max=arm_std_max,
        action_std_shoulder_lift=std_sl,
        action_std_elbow_flex=std_elbow,
        lag_by_joint=" ".join(
            f"{joints.label(i)}:{lag[i]:.2f}" for i in range(len(joints.names))
        ),
        action_std_by_joint=" ".join(
            f"{joints.label(i)}:{action_std[i]:.2f}" for i in arm
        ),
        flags=ordered,
        severity=_severity(ordered),
    )


def format_text(rows: list[EpisodeQc], thresholds: QcThresholds) -> str:
    lines = [
        (
            "[qc] thresholds "
            f"motion_eps_deg={thresholds.motion_eps_deg:g} "
            f"head_idle_s>{thresholds.head_idle_s:g} (LONG_HEAD_IDLE warn) "
            f"low_motion_std_deg<{thresholds.low_motion_std_deg:g} (LOW_MOTION high) "
            f"high_lag_deg>={thresholds.high_lag_deg:g} (HIGH_LAG high)"
        ),
        (
            f"{'dataset':<56} {'ep':>3} {'T':>5} {'mean_mot':>8} {'idle_fr':>7} "
            f"{'idle_s':>7} {'frac':>6} {'to_mot':>6} {'lag_sl':>7} "
            f"{'max_lag':<22} {'lag':>6}  action_std  flags"
        ),
    ]
    for row in rows:
        to_mot = (
            ""
            if row.frames_to_first_motion is None
            else str(row.frames_to_first_motion)
        )
        lag_sl = (
            ""
            if row.lag_shoulder_lift_deg is None
            else f"{row.lag_shoulder_lift_deg:.2f}"
        )
        flags = ",".join(row.flags)
        lines.append(
            f"{row.dataset:<56} {row.episode_index:3d} {row.num_frames:5d} "
            f"{row.mean_motion_deg_per_frame:8.3f} {row.head_idle_frames:7d} "
            f"{row.head_idle_s:7.2f} {row.head_idle_fraction:6.3f} {to_mot:>6} "
            f"{lag_sl:>7} {row.max_lag_joint:<22} {row.max_lag_deg:6.2f}  "
            f"{row.action_std_by_joint}  {flags}"
        )
    high = sum(row.severity == "high" for row in rows)
    warn = sum(row.severity == "warn" for row in rows)
    ok = sum(row.severity == "ok" for row in rows)
    lines.append(f"[qc] episodes={len(rows)} high={high} warn={warn} ok={ok}")
    return "\n".join(lines)


def _md(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _num(value: float | None, spec: str) -> str:
    if value is None:
        return ""
    return format(value, spec)


def render_markdown(
    rows: list[EpisodeQc], thresholds: QcThresholds, roots: list[Path]
) -> str:
    by_dataset: dict[str, list[EpisodeQc]] = {}
    for row in rows:
        by_dataset.setdefault(row.dataset, []).append(row)
    lines = [
        "# Teleop dataset QC",
        "",
        "Read-only pass over local LeRobot v3 datasets. Dataset files were not modified.",
        "",
        "Thresholds:",
        "",
        f"- motion: arm joint leaves the opening pose by {thresholds.motion_eps_deg:g}°",
        (
            f"- `{LONG_HEAD_IDLE}` (warn): head idle > {thresholds.head_idle_s:g} s "
            "(leading frames still within the motion epsilon)"
        ),
        (
            f"- `{LOW_MOTION}` (high): max arm-joint action std "
            f"< {thresholds.low_motion_std_deg:g}° (population std, ddof=0)"
        ),
        (
            f"- `{HIGH_LAG}` (high): max mean |action-state| "
            f">= {thresholds.high_lag_deg:g} (same units as the joint vector)"
        ),
        "",
        "Roots:",
        "",
    ]
    lines.extend(f"- `{root}`" for root in roots)
    lines.extend(
        [
            "",
            "## Counts",
            "",
            "| dataset | episodes | high | warn | ok |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, group in by_dataset.items():
        lines.append(
            "| {name} | {n} | {high} | {warn} | {ok} |".format(
                name=_md(name),
                n=len(group),
                high=sum(row.severity == "high" for row in group),
                warn=sum(row.severity == "warn" for row in group),
                ok=sum(row.severity == "ok" for row in group),
            )
        )
    lines.extend(["", "## High severity", ""])
    high_rows = [row for row in rows if row.severity == "high"]
    if not high_rows:
        lines.append("No high-severity flags.")
    else:
        lines.extend(
            [
                (
                    "| dataset | ep | flags | lag_sl | max_lag_joint | "
                    "max_lag | head_idle_s | std_arm_max |"
                ),
                "| --- | ---: | --- | ---: | --- | ---: | ---: | ---: |",
            ]
        )
        for row in high_rows:
            lines.append(
                "| {ds} | {ep} | {flags} | {lag} | {joint} | {max_lag} | {idle} | {std} |".format(
                    ds=_md(row.dataset),
                    ep=row.episode_index,
                    flags=_md(",".join(row.flags)),
                    lag=_num(row.lag_shoulder_lift_deg, ".2f"),
                    joint=_md(row.max_lag_joint),
                    max_lag=f"{row.max_lag_deg:.2f}",
                    idle=f"{row.head_idle_s:.2f}",
                    std=f"{row.action_std_arm_max:.2f}",
                )
            )
    lines.extend(
        [
            "",
            "## Episodes",
            "",
            (
                "| dataset | ep | T | mean_motion | idle_fr | idle_s | idle_frac | "
                "to_motion | lag_sl | max_lag_joint | max_lag | std_sl | std_elbow | "
                "std_arm_max | severity | flags |"
            ),
            (
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | "
                "---: | ---: | ---: | ---: | --- | --- |"
            ),
        ]
    )
    for row in rows:
        to_mot = (
            ""
            if row.frames_to_first_motion is None
            else str(row.frames_to_first_motion)
        )
        lines.append(
            "| {ds} | {ep} | {t} | {mot} | {ifr} | {idle} | {frac} | {to} | {lag} | "
            "{joint} | {max_lag} | {std_sl} | {std_el} | {std_arm} | {sev} | {flags} |".format(
                ds=_md(row.dataset),
                ep=row.episode_index,
                t=row.num_frames,
                mot=f"{row.mean_motion_deg_per_frame:.3f}",
                ifr=row.head_idle_frames,
                idle=f"{row.head_idle_s:.2f}",
                frac=f"{row.head_idle_fraction:.3f}",
                to=to_mot,
                lag=_num(row.lag_shoulder_lift_deg, ".2f"),
                joint=_md(row.max_lag_joint),
                max_lag=f"{row.max_lag_deg:.2f}",
                std_sl=_num(row.action_std_shoulder_lift, ".2f"),
                std_el=_num(row.action_std_elbow_flex, ".2f"),
                std_arm=f"{row.action_std_arm_max:.2f}",
                sev=row.severity,
                flags=_md(",".join(row.flags)),
            )
        )
    lines.append("")
    return "\n".join(lines)


_CSV_FIELDS = [
    "dataset",
    "episode_index",
    "num_frames",
    "fps",
    "mean_motion_deg_per_frame",
    "head_idle_frames",
    "head_idle_s",
    "head_idle_fraction",
    "frames_to_first_motion",
    "lag_shoulder_lift_deg",
    "max_lag_joint",
    "max_lag_deg",
    "action_std_arm_max",
    "action_std_shoulder_lift",
    "action_std_elbow_flex",
    "action_std_by_joint",
    "lag_by_joint",
    "severity",
    "flags",
]


def write_csv(path: Path, rows: list[EpisodeQc]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "dataset": row.dataset,
                    "episode_index": row.episode_index,
                    "num_frames": row.num_frames,
                    "fps": row.fps,
                    "mean_motion_deg_per_frame": f"{row.mean_motion_deg_per_frame:.6f}",
                    "head_idle_frames": row.head_idle_frames,
                    "head_idle_s": f"{row.head_idle_s:.6f}",
                    "head_idle_fraction": f"{row.head_idle_fraction:.6f}",
                    "frames_to_first_motion": (
                        ""
                        if row.frames_to_first_motion is None
                        else row.frames_to_first_motion
                    ),
                    "lag_shoulder_lift_deg": _num(row.lag_shoulder_lift_deg, ".6f"),
                    "max_lag_joint": row.max_lag_joint,
                    "max_lag_deg": f"{row.max_lag_deg:.6f}",
                    "action_std_arm_max": f"{row.action_std_arm_max:.6f}",
                    "action_std_shoulder_lift": _num(
                        row.action_std_shoulder_lift, ".6f"
                    ),
                    "action_std_elbow_flex": _num(row.action_std_elbow_flex, ".6f"),
                    "action_std_by_joint": row.action_std_by_joint,
                    "lag_by_joint": row.lag_by_joint,
                    "severity": row.severity,
                    "flags": ";".join(row.flags),
                }
            )


def _default_output_stem(roots: list[Path]) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    preferred = Path.home() / "work" / "lerobot-hw" / "outputs"
    base = preferred if preferred.is_dir() else roots[0]
    return base / f"qc_teleop_{stamp}"


def _output_stem(out: Path | None, roots: list[Path]) -> Path:
    if out is None:
        return _default_output_stem(roots)
    out = out.expanduser()
    if out.suffix.lower() in {".md", ".csv"}:
        return out.with_suffix("")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return out / f"qc_teleop_{stamp}"


def _rows_to_numpy(column: Any) -> np.ndarray:
    rows = list(column)
    if not rows:
        return np.zeros((0,), dtype=np.float64)
    first = rows[0]
    if isinstance(first, np.ndarray):
        return np.stack([np.asarray(row, dtype=np.float64) for row in rows])
    torch: Any
    try:
        import torch
    except ImportError:
        torch = None
    if torch is not None and isinstance(first, torch.Tensor):
        tensors = [
            row if isinstance(row, torch.Tensor) else torch.as_tensor(row)
            for row in rows
        ]
        return torch.stack(tensors).detach().cpu().numpy()
    return np.asarray(rows, dtype=np.float64)


def _matrix(column: Any) -> np.ndarray:
    array = np.asarray(_rows_to_numpy(column), dtype=np.float64)
    if array.ndim == 1:
        return array.reshape(-1, 1)
    if array.ndim > 2:
        return array.reshape(array.shape[0], -1)
    return array


def _repo_id_for(root: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    info_path = root / "meta" / "info.json"
    try:
        payload = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    repo = payload.get("repo_id") if isinstance(payload, dict) else None
    if isinstance(repo, str) and repo.strip():
        return repo.strip()
    return f"local/{root.name}"


def _feature_names(features: dict[str, Any]) -> list[str]:
    action = features.get("action")
    if not isinstance(action, dict):
        raise QcError("dataset features have no action spec")
    raw_names = action.get("names")
    shape = action.get("shape") or []
    width = int(shape[0]) if shape else 0
    if isinstance(raw_names, list) and raw_names:
        return [str(name) for name in raw_names]
    if width <= 0:
        raise QcError("action feature has no names and no shape")
    return [f"dim{i}" for i in range(width)]


def load_root(
    root: Path,
    *,
    repo_id: str | None,
    thresholds: QcThresholds,
    fps_override: float | None,
) -> list[EpisodeQc]:
    """Load action / state / episode_index via LeRobotDataset (pyav, no video decode)."""
    root = root.expanduser().resolve()
    info = root / "meta" / "info.json"
    if not info.is_file():
        raise QcError(f"not a local LeRobot dataset (missing {info})")
    try:
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
    except ImportError as exc:
        raise QcError(
            "lerobot is not installed. Activate the real-robot venv "
            "($HOME/work/lerobot-hw/.venv) and retry."
        ) from exc

    dataset = LeRobotDataset(
        _repo_id_for(root, repo_id),
        root=root,
        video_backend="pyav",
        download_videos=False,
    )
    fps = float(fps_override if fps_override is not None else dataset.meta.fps)
    names = _feature_names(dataset.features)
    hf = dataset.hf_dataset
    for key in ("action", "observation.state", "episode_index"):
        if key not in hf.column_names:
            raise QcError(f"{root}: missing column {key}")
    action = _matrix(hf["action"])
    state = _matrix(hf["observation.state"])
    episode_index = np.asarray(
        _rows_to_numpy(hf["episode_index"]), dtype=np.int64
    ).reshape(-1)
    if action.shape[0] != state.shape[0] or action.shape[0] != episode_index.shape[0]:
        raise QcError(
            f"{root}: length mismatch action={action.shape[0]} state={state.shape[0]} "
            f"episode_index={episode_index.shape[0]}"
        )

    groups: dict[int, list[int]] = {}
    order: list[int] = []
    for row_index, episode in enumerate(episode_index.tolist()):
        episode_i = int(episode)
        if episode_i not in groups:
            groups[episode_i] = []
            order.append(episode_i)
        groups[episode_i].append(row_index)

    scored: list[EpisodeQc] = []
    for episode_i in order:
        index = np.asarray(groups[episode_i], dtype=np.int64)
        scored.append(
            qc_episode(
                action[index],
                state[index],
                joint_names=names,
                fps=fps,
                thresholds=thresholds,
                dataset=root.name,
                root=str(root),
                episode_index=episode_i,
            )
        )
    return scored


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        type=Path,
        action="append",
        required=True,
        help="LeRobot v3 dataset root. Repeat for more than one dataset.",
    )
    parser.add_argument(
        "--repo-id",
        default=None,
        help="LeRobot repo id. Only with a single --root. Default: info.json or local/<dirname>.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Summary stem, .csv/.md file, or directory. "
            "Default: $HOME/work/lerobot-hw/outputs, or next to the first dataset."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("csv", "md", "both"),
        default="both",
        help="Summary files to write (default: both).",
    )
    parser.add_argument("--fps", type=float, default=None, help="Override dataset fps.")
    parser.add_argument(
        "--motion-eps-deg",
        type=float,
        default=1.0,
        help="Arm departure from the opening pose that ends the idle head (default: 1).",
    )
    parser.add_argument(
        "--head-idle-s",
        type=float,
        default=2.0,
        help="Flag LONG_HEAD_IDLE when head idle is longer than this many seconds (default: 2).",
    )
    parser.add_argument(
        "--low-motion-std-deg",
        type=float,
        default=5.0,
        help="Flag LOW_MOTION when every arm joint's action std is below this (default: 5).",
    )
    parser.add_argument(
        "--high-lag-deg",
        type=float,
        default=6.0,
        help="Flag HIGH_LAG when any joint's mean |action-state| reaches this (default: 6).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when any episode has a high-severity flag (LOW_MOTION or HIGH_LAG).",
    )
    args = parser.parse_args(argv)
    if args.repo_id and len(args.root) != 1:
        parser.error("--repo-id applies to a single --root")
    if args.fps is not None and args.fps <= 0:
        parser.error("--fps must be positive")
    if args.motion_eps_deg < 0 or args.head_idle_s < 0:
        parser.error("--motion-eps-deg and --head-idle-s must be >= 0")
    if args.low_motion_std_deg < 0 or args.high_lag_deg < 0:
        parser.error("--low-motion-std-deg and --high-lag-deg must be >= 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    thresholds = QcThresholds(
        motion_eps_deg=args.motion_eps_deg,
        head_idle_s=args.head_idle_s,
        low_motion_std_deg=args.low_motion_std_deg,
        high_lag_deg=args.high_lag_deg,
    )
    roots = [path.expanduser().resolve() for path in args.root]
    rows: list[EpisodeQc] = []
    try:
        for root in roots:
            rows.extend(
                load_root(
                    root,
                    repo_id=args.repo_id,
                    thresholds=thresholds,
                    fps_override=args.fps,
                )
            )
    except QcError as exc:
        print(f"[qc] {exc}", file=sys.stderr)
        return 1

    print(format_text(rows, thresholds))
    if not rows:
        print("[qc] no episodes", file=sys.stderr)
        return 1

    stem = _output_stem(args.out, roots)
    written: list[Path] = []
    if args.format in {"csv", "both"}:
        csv_path = stem.with_suffix(".csv")
        write_csv(csv_path, rows)
        written.append(csv_path)
    if args.format in {"md", "both"}:
        md_path = stem.with_suffix(".md")
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(rows, thresholds, roots), encoding="utf-8")
        written.append(md_path)
    for path in written:
        print(f"[qc] wrote {path}")

    if args.strict and any(row.severity == "high" for row in rows):
        print("[qc] strict: high-severity flag present", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
