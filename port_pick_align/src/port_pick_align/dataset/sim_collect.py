"""Collect contract-aligned LeRobotDataset episodes from the MuJoCo oracle."""

from __future__ import annotations

import copy
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from port_pick_align.contract import load_contract, validate_contract
from port_pick_align.dataset.converter import AlignedEpisode, AlignedFrame
from port_pick_align.dataset.synthetic import build_features
from port_pick_align.dataset.validator import ValidationIssue, ValidationReport, validate_episode
from port_pick_align.evaluation.eval_alignment import (
    compute_pose_errors,
    infer_grasp_success,
    is_align_success,
)
from port_pick_align.simulation.policies import ScriptedPickAlignPolicy

DEFAULT_REPO_ID = "local/port_pick_align_sim_expert"
DEFAULT_TASK = "sim_pick_align"
DEFAULT_EPISODES = 64
DEFAULT_MAX_ATTEMPTS = 5
# Paper / contract cameras. Smoke runs may override this; official runs must not.
OFFICIAL_EPISODE_MIN = 50
OFFICIAL_EPISODE_MAX = 100


class SimCollectionError(RuntimeError):
    """Raised when oracle collection cannot satisfy the quality gate."""


@dataclass
class CollectedFrame:
    """One control step. Images are HWC BGR uint8, as returned by the simulator."""

    top_bgr: np.ndarray
    wrist_bgr: np.ndarray
    state: np.ndarray
    action: np.ndarray


@dataclass
class EpisodeRollout:
    frames: list[CollectedFrame]
    seed: int
    position_error_mm: float
    yaw_error_deg: float
    grasp_success: bool
    align_success: bool


def bgr_hwc_to_rgb(image: np.ndarray) -> np.ndarray:
    """Convert an HWC BGR uint8 image to contiguous HWC RGB."""
    img = np.asarray(image)
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"Expected HWC image with 3 channels, got shape {img.shape}")
    return np.ascontiguousarray(img[:, :, ::-1])


def _dt_ns(fps: int) -> int:
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    return int(round(1_000_000_000 / float(fps)))


def collected_frames_to_aligned_episode(
    frames: list[CollectedFrame],
    *,
    fps: int,
) -> AlignedEpisode:
    """Map sim steps onto validator frames. Cameras and joints share one clock."""
    dt = _dt_ns(fps)
    aligned: list[AlignedFrame] = []
    for index, frame in enumerate(frames):
        aligned.append(
            AlignedFrame(
                t_ns=index * dt,
                top=bgr_hwc_to_rgb(frame.top_bgr),
                wrist=bgr_hwc_to_rgb(frame.wrist_bgr),
                state=np.asarray(frame.state, dtype=np.float32).reshape(-1),
                sync_offset_ms=0.0,
            )
        )
    return AlignedEpisode(frames=aligned)


def _action_limit_issues(
    frames: list[CollectedFrame],
    contract: dict[str, Any],
) -> list[ValidationIssue]:
    joint_names: list[str] = list(contract["robot"]["joint_names"])
    joint_limits = contract["robot"]["joint_limits"]
    issues: list[ValidationIssue] = []
    for idx, frame in enumerate(frames):
        action = np.asarray(frame.action, dtype=np.float32).reshape(-1)
        if action.shape[0] != len(joint_names):
            issues.append(
                ValidationIssue(
                    code="ACTION_DIM",
                    message=f"Frame {idx}: action dim {action.shape[0]} != {len(joint_names)}",
                    frame_index=idx,
                )
            )
            continue
        for joint_index, name in enumerate(joint_names):
            lo, hi = joint_limits[name]
            value = float(action[joint_index])
            if value < float(lo) or value > float(hi):
                issues.append(
                    ValidationIssue(
                        code="JOINT_LIMIT",
                        message=(
                            f"Frame {idx}: action {name}={value:.4f} outside "
                            f"[{float(lo):.4f}, {float(hi):.4f}]"
                        ),
                        frame_index=idx,
                    )
                )
    return issues


def validate_collected_frames(
    frames: list[CollectedFrame],
    contract: dict[str, Any],
    *,
    fps: int,
) -> ValidationReport:
    """Run DataValidator, then apply the same joint limits to recorded actions."""
    report = validate_episode(
        collected_frames_to_aligned_episode(frames, fps=fps),
        contract,
    )
    report.issues.extend(_action_limit_issues(frames, contract))
    return report


def _clip_action(action: np.ndarray, contract: dict[str, Any]) -> np.ndarray:
    joint_names: list[str] = list(contract["robot"]["joint_names"])
    limits = contract["robot"]["joint_limits"]
    clipped = np.asarray(action, dtype=np.float32).reshape(-1).copy()
    for index, name in enumerate(joint_names):
        lo, hi = limits[name]
        clipped[index] = float(np.clip(clipped[index], float(lo), float(hi)))
    return clipped


def rollout_scripted_episode(
    env: Any,
    *,
    seed: int,
    max_steps: int,
    contract: dict[str, Any],
    randomize_box: bool = True,
) -> EpisodeRollout:
    """Roll out the scripted oracle for one episode and keep BGR observations."""
    policy = ScriptedPickAlignPolicy(
        chunk_size=int(contract["model"]["chunk_size"]),
        action_dim=int(contract["model"]["action_dim"]),
    )
    policy.reset()
    policy.set_ik(env.solve_ik)
    obs, info = env.reset(seed=seed, options={"randomize_box": randomize_box})

    frames: list[CollectedFrame] = []
    grasped = bool(info.get("grasping", False))
    for _ in range(max_steps):
        chunk = policy.predict(obs, info=info)
        action = _clip_action(chunk[0], contract)
        frames.append(
            CollectedFrame(
                top_bgr=np.array(obs["top"], dtype=np.uint8, copy=True),
                wrist_bgr=np.array(obs["wrist"], dtype=np.uint8, copy=True),
                state=np.array(obs["state"], dtype=np.float32, copy=True),
                action=action,
            )
        )
        obs, _reward, terminated, truncated, info = env.step(action)
        grasped = grasped or bool(info.get("grasping", False))
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
    grasp = bool(grasp or grasped or pos_mm < 50.0)
    return EpisodeRollout(
        frames=frames,
        seed=seed,
        position_error_mm=float(pos_mm),
        yaw_error_deg=float(yaw_deg),
        grasp_success=grasp,
        align_success=bool(is_align_success(pos_mm, yaw_deg)),
    )


def _features_for_render(
    contract: dict[str, Any],
    *,
    height: int,
    width: int,
) -> dict[str, dict[str, Any]]:
    """Feature spec for the rendered resolution.

    ``validate_contract`` requires 640×480. Smoke runs therefore build features
    from a copy and do not re-validate that copy.
    """
    rendered = copy.deepcopy(contract)
    for name in ("top", "wrist"):
        rendered["cameras"][name]["height"] = int(height)
        rendered["cameras"][name]["width"] = int(width)
    return build_features(rendered)


def _episode_accepted(
    report: ValidationReport,
    rollout: EpisodeRollout,
    *,
    require_success: bool,
) -> bool:
    if not report.ok:
        return False
    if require_success and not rollout.align_success:
        return False
    return True


def _detail(
    episode_index: int,
    rollout: EpisodeRollout,
    report: ValidationReport,
    *,
    accepted: bool,
) -> dict[str, Any]:
    return {
        "episode_index": episode_index,
        "seed": rollout.seed,
        "n_frames": len(rollout.frames),
        "accepted": accepted,
        "validation_ok": report.ok,
        "issue_codes": sorted(report.codes()),
        "issues": [issue.message for issue in report.issues],
        "position_error_mm": rollout.position_error_mm,
        "yaw_error_deg": rollout.yaw_error_deg,
        "grasp_success": rollout.grasp_success,
        "align_success": rollout.align_success,
    }


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def collect_sim_dataset(
    output_dir: Path | str,
    contract: dict[str, Any] | None = None,
    contract_path: Path | str | None = None,
    *,
    repo_id: str = DEFAULT_REPO_ID,
    episodes: int = DEFAULT_EPISODES,
    max_steps: int | None = None,
    seed: int = 0,
    task: str = DEFAULT_TASK,
    overwrite: bool = True,
    randomize_box: bool = True,
    require_success: bool = True,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    render_height: int | None = None,
    render_width: int | None = None,
    report_path: Path | str | None = None,
    image_writer_threads: int = 4,
) -> Path:
    """Write oracle demonstrations and a DataValidator report.

    Observations are acquired as BGR and stored as RGB so training pixels match
    ``images_bgr_to_batch`` at closed-loop inference. Returns the dataset root.
    """
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    from port_pick_align.simulation.env import PickAlignSimEnv

    if episodes < 1:
        raise ValueError(f"episodes must be >= 1, got {episodes}")
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")

    if contract is None:
        contract = load_contract(contract_path)
    validate_contract(contract)

    horizon = ScriptedPickAlignPolicy.horizon_steps()
    steps = horizon if max_steps is None else int(max_steps)
    if steps < 1:
        raise ValueError(f"max_steps must be >= 1, got {steps}")

    height = int(render_height or contract["cameras"]["top"]["height"])
    width = int(render_width or contract["cameras"]["top"]["width"])
    fps = int(contract["cameras"]["top"]["fps"])
    official = (
        OFFICIAL_EPISODE_MIN <= episodes <= OFFICIAL_EPISODE_MAX
        and height == int(contract["cameras"]["top"]["height"])
        and width == int(contract["cameras"]["top"]["width"])
        and steps == horizon
        and require_success
        and randomize_box
    )

    root = Path(output_dir)
    if report_path is None:
        report_file = root.parent / "validation_report.json"
    else:
        report_file = Path(report_path)
    if root.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {root}")
        shutil.rmtree(root)

    features = _features_for_render(contract, height=height, width=width)
    dataset = LeRobotDataset.create(
        repo_id=repo_id,
        fps=fps,
        features=features,
        root=root,
        robot_type=str(contract["robot"]["name"]),
        use_videos=False,
        image_writer_threads=image_writer_threads,
    )

    env = PickAlignSimEnv(
        contract=contract,
        max_episode_steps=steps,
        render_width=width,
        render_height=height,
        render_cameras=True,
    )
    details: list[dict[str, Any]] = []
    seed_cursor = int(seed)
    try:
        for episode_index in range(episodes):
            accepted_rollout: EpisodeRollout | None = None
            accepted_report: ValidationReport | None = None
            for _attempt in range(max_attempts):
                episode_seed = seed_cursor
                seed_cursor += 1
                rollout = rollout_scripted_episode(
                    env,
                    seed=episode_seed,
                    max_steps=steps,
                    contract=contract,
                    randomize_box=randomize_box,
                )
                report = validate_collected_frames(rollout.frames, contract, fps=fps)
                accepted = _episode_accepted(report, rollout, require_success=require_success)
                details.append(_detail(episode_index, rollout, report, accepted=accepted))
                if accepted:
                    accepted_rollout = rollout
                    accepted_report = report
                    break
            if accepted_rollout is None or accepted_report is None:
                payload = _report_payload(
                    root=root,
                    repo_id=repo_id,
                    episodes_requested=episodes,
                    fps=fps,
                    height=height,
                    width=width,
                    max_steps=steps,
                    horizon=horizon,
                    require_success=require_success,
                    randomize_box=randomize_box,
                    official=official,
                    details=details,
                    result="FAIL",
                )
                _write_report(report_file, payload)
                shutil.rmtree(root, ignore_errors=True)
                last = details[-1]
                raise SimCollectionError(
                    "Episode "
                    f"{episode_index} failed quality/success after {max_attempts} attempts "
                    f"(seed={last['seed']}, issues={last['issue_codes']}, "
                    f"align_success={last['align_success']}). Report: {report_file}"
                )

            for frame in accepted_rollout.frames:
                dataset.add_frame(
                    {
                        "observation.images.top": bgr_hwc_to_rgb(frame.top_bgr),
                        "observation.images.wrist": bgr_hwc_to_rgb(frame.wrist_bgr),
                        "observation.state": np.asarray(frame.state, dtype=np.float32),
                        "action": np.asarray(frame.action, dtype=np.float32),
                        "task": task,
                    }
                )
            dataset.save_episode()
            print(
                f"episode {episode_index}: frames={len(accepted_rollout.frames)} "
                f"seed={accepted_rollout.seed} "
                f"pos_mm={accepted_rollout.position_error_mm:.2f} "
                f"yaw_deg={accepted_rollout.yaw_error_deg:.2f} "
                f"align={accepted_rollout.align_success}"
            )
    finally:
        env.close()

    dataset.finalize()
    payload = _report_payload(
        root=root,
        repo_id=repo_id,
        episodes_requested=episodes,
        fps=fps,
        height=height,
        width=width,
        max_steps=steps,
        horizon=horizon,
        require_success=require_success,
        randomize_box=randomize_box,
        official=official,
        details=details,
        result="PASS",
    )
    _write_report(report_file, payload)
    print(f"validation report: {report_file} result=PASS official={official}")
    return root


def _report_payload(
    *,
    root: Path,
    repo_id: str,
    episodes_requested: int,
    fps: int,
    height: int,
    width: int,
    max_steps: int,
    horizon: int,
    require_success: bool,
    randomize_box: bool,
    official: bool,
    details: list[dict[str, Any]],
    result: str,
) -> dict[str, Any]:
    accepted = [item for item in details if item["accepted"]]
    return {
        "result": result,
        "official_collection": official and result == "PASS",
        "dataset_root": str(root),
        "repo_id": repo_id,
        "episodes_requested": episodes_requested,
        "episodes_accepted": len(accepted),
        "total_frames": int(sum(int(item["n_frames"]) for item in accepted)),
        "fps": fps,
        "image_hwc": [height, width, 3],
        "acquired_color": "bgr",
        "stored_color": "rgb",
        "max_steps": max_steps,
        "scripted_horizon_steps": horizon,
        "require_success": require_success,
        "randomize_box": randomize_box,
        "attempts": details,
    }
