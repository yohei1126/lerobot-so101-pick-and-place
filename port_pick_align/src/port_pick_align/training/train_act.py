"""ACT training and inference for contract-aligned LeRobot datasets.

Device selection prefers MPS, then CUDA, then CPU. Full sim-expert training
(1,000 steps or more) is intended for Apple Silicon. Short CPU runs only check
that the loop, validation split, and checkpoint write succeed.
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader, Subset, random_split

from port_pick_align.contract import DEFAULT_CONTRACT_PATH, load_contract, validate_contract
from port_pick_align.dataset.sim_collect import DEFAULT_REPO_ID as SIM_REPO_ID
from port_pick_align.dataset.synthetic import DEFAULT_REPO_ID, make_dummy_image
from port_pick_align.training.policy import ARCH_PRESETS, build_act_policy, resolve_arch

# Surface native crashes (OpenCV/PyAV/MuJoCo) instead of a silent abort.
faulthandler.enable(file=sys.stderr, all_threads=True)

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATASET_ROOT = REPO_ROOT / "data" / "synthetic" / "lerobot"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "checkpoints" / "synthetic_act"
SIM_DATASET_ROOT = REPO_ROOT / "data" / "sim_expert" / "lerobot"
SIM_OUTPUT_DIR = REPO_ROOT / "checkpoints" / "sim_act"
CHECKPOINT_NAME = "best_model.pt"
LAST_CHECKPOINT_NAME = "last.pt"
RECOMMENDED_MIN_STEPS = 1000
# Dataset scan midpoint between expert open (≈1.2) and closed (≈0.0).
DEFAULT_GRIPPER_CLOSED_THRESH = 0.45
DEFAULT_GRIPPER_DIM = 5
# Sim-preset defaults for grasp-transition emphasis (smoke / explicit None → off/1.0).
SIM_DEFAULT_GRIPPER_LOSS_WEIGHT = 5.0
SIM_DEFAULT_TRANSITION_OVERSAMPLE_FACTOR = 5
SIM_DEFAULT_TRANSITION_OVERSAMPLE_WINDOW = 15
# 2 episodes made a lucky 0.5 (1/2) win checkpoint selection. 10 is the low end
# of the 10–20 range and stays overridable via --closed-loop-val-episodes.
SIM_DEFAULT_CLOSED_LOOP_VAL_EPISODES = 10
# Full scripted horizon so release and align are visible (eval uses 260).
SIM_DEFAULT_CLOSED_LOOP_VAL_MAX_STEPS = 260
# Selection rollouts execute this many chunk steps between replans. Temporal
# ensembling is logged beside it and does not choose best_model.pt.
CLOSED_LOOP_SELECTION_N_ACTION_STEPS = 30


def _mps_available() -> bool:
    backend = getattr(torch.backends, "mps", None)
    return backend is not None and bool(backend.is_available())


def resolve_device(requested: str | None = None) -> str:
    """Select a torch device.

    An explicit ``mps`` or ``cuda`` request is returned only when that backend
    exists; otherwise this raises. With no request, the order is MPS, CUDA, CPU.
    """
    if requested is not None and requested.strip() != "":
        name = requested.strip().lower()
        if name == "mps":
            if not _mps_available():
                raise RuntimeError(
                    "MPS was requested but torch.backends.mps.is_available() is false"
                )
            return "mps"
        if name == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
            return "cuda"
        if name == "cpu":
            return "cpu"
        raise ValueError(f"Unknown device {requested!r}. Expected mps, cuda, or cpu.")
    if _mps_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def action_delta_timestamps(fps: int, chunk_size: int) -> dict[str, list[float]]:
    return {"action": [i / float(fps) for i in range(chunk_size)]}


def load_training_dataset(
    dataset_root: Path,
    contract: dict[str, Any],
    *,
    repo_id: str = DEFAULT_REPO_ID,
):
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    fps = int(contract["cameras"]["top"]["fps"])
    chunk_size = int(contract["model"]["chunk_size"])
    return LeRobotDataset(
        repo_id=repo_id,
        root=dataset_root,
        delta_timestamps=action_delta_timestamps(fps, chunk_size),
    )


def _to_batch_tensor(value: Any, device: str) -> torch.Tensor:
    if isinstance(value, torch.Tensor):
        tensor = value
    else:
        tensor = torch.as_tensor(value)
    if tensor.ndim >= 3 and tensor.dtype == torch.uint8:
        tensor = tensor.float() / 255.0
    elif tensor.dtype != torch.float32:
        tensor = tensor.float()
    return tensor.unsqueeze(0).to(device)


def collate_act_batch(samples: list[dict[str, Any]], device: str) -> dict[str, torch.Tensor]:
    keys = [
        "observation.images.top",
        "observation.images.wrist",
        "observation.state",
        "action",
        "action_is_pad",
    ]
    batch: dict[str, torch.Tensor] = {}
    for key in keys:
        tensors = []
        for sample in samples:
            value = sample[key]
            if isinstance(value, torch.Tensor):
                tensor = value
            else:
                tensor = torch.as_tensor(value)
            if key.startswith("observation.images.") and tensor.dtype == torch.uint8:
                tensor = tensor.float() / 255.0
            elif tensor.dtype != torch.bool:
                tensor = tensor.float()
            tensors.append(tensor)
        stacked = torch.stack(tensors, dim=0)
        batch[key] = stacked.to(device)
    return batch


def _episode_frame_ranges(dataset: Any) -> list[tuple[int, int]] | None:
    """Return ``[from, to)`` frame ranges per episode, or ``None`` if unavailable."""
    meta = getattr(dataset, "meta", None)
    episodes = getattr(meta, "episodes", None) if meta is not None else None
    if episodes is None:
        return None
    try:
        n_eps = len(episodes)
    except TypeError:
        return None
    if n_eps < 1:
        return None
    ranges: list[tuple[int, int]] = []
    for i in range(n_eps):
        ep = episodes[i]
        try:
            start = int(ep["dataset_from_index"])
            end = int(ep["dataset_to_index"])
        except (KeyError, TypeError, ValueError):
            return None
        if end <= start:
            return None
        ranges.append((start, end))
    return ranges


def _indices_for_episodes(
    ranges: list[tuple[int, int]],
    episode_ids: list[int],
    *,
    sort: bool,
) -> list[int]:
    indices: list[int] = []
    for ep_id in episode_ids:
        start, end = ranges[ep_id]
        indices.extend(range(start, end))
    if sort:
        indices.sort()
    return indices


def split_train_val(
    dataset: Any,
    val_ratio: float,
    seed: int,
) -> tuple[Any, Subset | None, int | None, int | None]:
    """Split into train and validation subsets.

    Prefer episode-level split via ``meta.episodes`` (no frame leakage across
    train/val). Fall back to frame-level ``random_split`` when episode metadata
    is missing. Returns ``(train, val, n_train_episodes, n_val_episodes)``;
    episode counts are ``None`` on the frame-level fallback path.
    """
    if val_ratio < 0 or val_ratio >= 1:
        raise ValueError(f"val_ratio must be in [0, 1), got {val_ratio}")
    n = len(dataset)
    if val_ratio == 0 or n < 2:
        return dataset, None, None, None

    ranges = _episode_frame_ranges(dataset)
    if ranges is not None and len(ranges) >= 2:
        n_eps = len(ranges)
        n_val_eps = max(1, int(round(n_eps * val_ratio)))
        n_val_eps = min(n_val_eps, n_eps - 1)
        n_train_eps = n_eps - n_val_eps
        rng = random.Random(seed)
        order = list(range(n_eps))
        rng.shuffle(order)
        val_ids = sorted(order[:n_val_eps])
        train_ids = sorted(order[n_val_eps:])
        train_indices = _indices_for_episodes(ranges, train_ids, sort=True)
        val_indices = _indices_for_episodes(ranges, val_ids, sort=True)
        if len(train_indices) < 1 or len(val_indices) < 1:
            return dataset, None, None, None
        return (
            Subset(dataset, train_indices),
            Subset(dataset, val_indices),
            n_train_eps,
            n_val_eps,
        )

    n_val = max(1, int(round(n * val_ratio)))
    n_val = min(n_val, n - 1)
    n_train = n - n_val
    generator = torch.Generator().manual_seed(seed)
    train_subset, val_subset = random_split(dataset, [n_train, n_val], generator=generator)
    return train_subset, val_subset, None, None


def evaluate_val_l1(
    policy: Any,
    loader: DataLoader,
    *,
    max_batches: int | None = None,
) -> float:
    """Mean of per-batch action L1 on the validation loader (batch-size weighted).

    ``max_batches`` caps how many batches are evaluated; ``None`` means full pass.
    Uses the unweighted L1 from the policy (comparable across runs).
    """
    policy.eval()
    total = 0.0
    count = 0
    try:
        for batch_idx, batch in enumerate(loader):
            if max_batches is not None and batch_idx >= max_batches:
                break
            batch_size = int(batch["action"].shape[0])
            with torch.inference_mode():
                _loss, loss_dict = policy(batch)
            total += float(loss_dict["l1_loss"]) * batch_size
            count += batch_size
    finally:
        policy.train()
    if count == 0:
        raise RuntimeError("Validation loader produced no batches")
    return total / count


def action_gripper_value(action: Any, gripper_dim: int = DEFAULT_GRIPPER_DIM) -> float:
    """Return the immediate (chunk step 0) gripper command from a sample action."""
    tensor = torch.as_tensor(action).float()
    if tensor.ndim == 2:
        return float(tensor[0, gripper_dim])
    return float(tensor[gripper_dim])


def _episode_and_gripper_series(
    dataset: Any,
    indices: list[int],
    *,
    gripper_dim: int = DEFAULT_GRIPPER_DIM,
) -> tuple[dict[int, int], dict[int, float]]:
    """Map dataset index → episode id and immediate gripper command.

    Prefers ``dataset.hf_dataset`` action / episode columns so we do not decode
    camera frames for every training index (LeRobot ``__getitem__`` is expensive).
    Falls back to per-index ``__getitem__`` for lightweight test doubles.
    """
    index_set = set(int(i) for i in indices)
    episode_of: dict[int, int] = {}
    grip_of: dict[int, float] = {}

    hf = getattr(dataset, "hf_dataset", None)
    if hf is not None and "action" in getattr(hf, "column_names", []):
        slim = hf.select_columns(["action", "episode_index"])
        actions = slim["action"]
        episodes = slim["episode_index"]
        for index in indices:
            idx = int(index)
            episode_of[idx] = int(episodes[idx])
            action = actions[idx]
            if hasattr(action, "__getitem__"):
                grip_of[idx] = float(action[gripper_dim])
            else:
                grip_of[idx] = float(list(action)[gripper_dim])
        return episode_of, grip_of

    for index in indices:
        sample = dataset[int(index)]
        episode_of[int(index)] = int(sample["episode_index"])
        grip_of[int(index)] = action_gripper_value(sample["action"], gripper_dim)
    assert index_set == set(episode_of)
    return episode_of, grip_of


def find_gripper_transition_indices(
    dataset: Any,
    indices: list[int],
    *,
    gripper_dim: int = DEFAULT_GRIPPER_DIM,
    closed_thresh: float = DEFAULT_GRIPPER_CLOSED_THRESH,
    direction: str = "open_to_close",
) -> list[int]:
    """Dataset indices where the gripper crosses within an episode.

    ``direction`` is ``open_to_close`` (grasp), ``close_to_open`` (release), or ``both``.
    """
    if direction not in {"open_to_close", "close_to_open", "both"}:
        raise ValueError(
            f"direction must be open_to_close, close_to_open, or both, got {direction!r}"
        )
    episode_of, grip_of = _episode_and_gripper_series(dataset, indices, gripper_dim=gripper_dim)
    by_episode: dict[int, list[int]] = {}
    for index in indices:
        by_episode.setdefault(episode_of[int(index)], []).append(int(index))

    transitions: list[int] = []
    for episode_indices in by_episode.values():
        ordered = sorted(episode_indices)
        previous_grip: float | None = None
        for index in ordered:
            grip = grip_of[index]
            if previous_grip is not None:
                closing = previous_grip > closed_thresh and grip <= closed_thresh
                opening = previous_grip <= closed_thresh and grip > closed_thresh
                if closing and direction in {"open_to_close", "both"}:
                    transitions.append(index)
                if opening and direction in {"close_to_open", "both"}:
                    transitions.append(index)
            previous_grip = grip
    return transitions


def oversample_indices_near_transitions(
    base_indices: list[int],
    transition_indices: list[int],
    dataset: Any,
    *,
    window: int,
    factor: int,
) -> list[int]:
    """Repeat frames within ``window`` of each gripper transition ``factor`` times.

    ``factor=1`` leaves ``base_indices`` unchanged. Extra copies are appended so
    ``DataLoader(shuffle=True)`` still sees the full base set once per epoch.
    Expansion stays inside the same episode as the transition.
    """
    if factor <= 1 or window < 0 or not transition_indices:
        return list(base_indices)

    base_set = set(base_indices)
    episode_of, _grip_of = _episode_and_gripper_series(dataset, base_indices)
    boost: list[int] = []
    for transition in transition_indices:
        if transition not in base_set:
            continue
        episode = episode_of[transition]
        for offset in range(-window, window + 1):
            candidate = transition + offset
            if candidate in base_set and episode_of.get(candidate) == episode:
                boost.append(candidate)

    expanded = list(base_indices)
    for _ in range(factor - 1):
        expanded.extend(boost)
    return expanded


def compute_act_train_loss(
    policy: Any,
    batch: dict[str, torch.Tensor],
    *,
    gripper_loss_weight: float = 1.0,
    gripper_dim: int = DEFAULT_GRIPPER_DIM,
) -> tuple[torch.Tensor, dict[str, float]]:
    """ACT training loss with an optional higher weight on the gripper dimension.

    Mirrors ``ACTPolicy.forward`` (L1 + VAE KL) but multiplies the gripper
    absolute error by ``gripper_loss_weight`` before the batch mean. Validation
    continues to use the unweighted policy L1 for a stable comparable metric.
    """
    import torch.nn.functional as F
    from lerobot.utils.constants import ACTION, OBS_IMAGES

    if gripper_loss_weight <= 0:
        raise ValueError(f"gripper_loss_weight must be > 0, got {gripper_loss_weight}")

    model_batch: dict[str, Any] = dict(batch)
    if policy.config.image_features:
        model_batch[OBS_IMAGES] = [model_batch[key] for key in policy.config.image_features]

    actions_hat, (mu_hat, log_sigma_x2_hat) = policy.model(model_batch)
    abs_err = F.l1_loss(batch[ACTION], actions_hat, reduction="none")
    valid_mask = (~batch["action_is_pad"]).unsqueeze(-1)
    action_dim = int(abs_err.shape[-1])
    weights = torch.ones(action_dim, device=abs_err.device, dtype=abs_err.dtype)
    if 0 <= gripper_dim < action_dim:
        weights[gripper_dim] = float(gripper_loss_weight)
    weighted_err = abs_err * weights.view(1, 1, -1)
    denom = (valid_mask.sum() * action_dim).clamp_min(1)
    l1_loss = (weighted_err * valid_mask).sum() / denom
    unweighted_l1 = (abs_err * valid_mask).sum() / denom

    loss_dict: dict[str, float] = {
        "l1_loss": float(unweighted_l1.detach().item()),
        "weighted_l1_loss": float(l1_loss.detach().item()),
    }
    if policy.config.use_vae and log_sigma_x2_hat is not None:
        mean_kld = (
            (-0.5 * (1 + log_sigma_x2_hat - mu_hat.pow(2) - log_sigma_x2_hat.exp())).sum(-1).mean()
        )
        loss_dict["kld_loss"] = float(mean_kld.detach().item())
        loss = l1_loss + mean_kld * float(policy.config.kl_weight)
    else:
        loss = l1_loss
    return loss, loss_dict


def _empty_closed_loop_metrics(
    episodes: int,
    *,
    error: str | None = None,
) -> dict[str, float | str | None]:
    payload: dict[str, float | str | None] = {
        "grasp_success_rate": 0.0,
        "align_success_rate": 0.0,
        "mean_position_error_mm": 0.0,
        "holding_at_end_rate": 0.0,
        "released_on_pad_rate": 0.0,
        "n_episodes": float(max(0, episodes)),
        "error": error,
    }
    return payload


def evaluate_closed_loop_grasp(
    policy: Any,
    contract: dict[str, Any],
    *,
    device: str,
    episodes: int = SIM_DEFAULT_CLOSED_LOOP_VAL_EPISODES,
    max_steps: int = SIM_DEFAULT_CLOSED_LOOP_VAL_MAX_STEPS,
    seed: int = 0,
    n_action_steps: int = CLOSED_LOOP_SELECTION_N_ACTION_STEPS,
    temporal_ensemble: bool = False,
    temporal_ensemble_coeff: float = 0.01,
    mode_label: str | None = None,
) -> dict[str, float | str | None]:
    """Cheap closed-loop rollouts: grasp / align rates for checkpoint selection.

    Selection calls this with ``temporal_ensemble=False`` and ``n_action_steps``
    30 (one chunk between replans). A second call with temporal ensembling and
    ``n_action_steps=1`` is a separate metric and must not pick the checkpoint.
    Failures (device mismatch, MuJoCo GL, import errors) are caught and returned
    as zero rates with an ``error`` string so the training process stays alive.
    """
    import gc
    import traceback

    from port_pick_align.evaluation.eval_alignment import (
        compute_pose_errors,
        is_align_success,
        trial_outcome,
    )
    from port_pick_align.simulation.env import PickAlignSimEnv, box_reset_options
    from port_pick_align.simulation.policies import CheckpointPolicy

    if episodes < 1:
        raise ValueError(f"episodes must be >= 1, got {episodes}")
    if max_steps < 1:
        raise ValueError(f"max_steps must be >= 1, got {max_steps}")

    chunk_size = int(contract["model"]["chunk_size"])
    use_ensemble = bool(temporal_ensemble)
    if use_ensemble:
        horizon = 1
    else:
        horizon = max(1, min(int(n_action_steps), chunk_size))
    label = mode_label or ("te" if use_ensemble else f"chunk{horizon}")
    was_training = bool(policy.training)
    device_name = resolve_device(device)
    env: PickAlignSimEnv | None = None
    print(
        f"closed_loop_val begin mode={label} episodes={episodes} max_steps={max_steps} "
        f"device={device_name} n_action_steps={horizon} temporal_ensemble={use_ensemble}",
        flush=True,
    )
    try:
        # Weights must match observation tensors (build_act_policy may have left CPU).
        policy.to(device_name)
        policy.eval()
        if device_name == "mps" and hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
        gc.collect()

        env = PickAlignSimEnv(
            contract=contract,
            max_episode_steps=max_steps,
            render_cameras=True,
        )
        wrapped = CheckpointPolicy(
            policy,
            chunk_size=chunk_size,
            device=device_name,
            temporal_ensemble=use_ensemble,
            temporal_ensemble_coeff=float(temporal_ensemble_coeff),
        )
        n_grasp = 0
        n_align = 0
        n_holding = 0
        n_released = 0
        position_errors: list[float] = []
        for ep in range(episodes):
            wrapped.reset()
            obs, info = env.reset(seed=seed + ep, options=box_reset_options(randomize_box=True))
            grasped_during = bool(info.get("grasping", False))
            chunk: np.ndarray | None = None
            chunk_i = 0
            for _ in range(max_steps):
                if chunk is None or chunk_i >= horizon:
                    chunk = wrapped.predict(obs, info=info)
                    chunk_i = 0
                assert chunk is not None
                action = chunk[chunk_i]
                chunk_i += 1
                obs, _reward, terminated, truncated, info = env.step(action)
                grasped_during = grasped_during or bool(info.get("grasping", False))
                if terminated or truncated:
                    break
            pos_mm, yaw_deg = compute_pose_errors(
                info["box_xy"], info["box_yaw"], info["target_xy"], info["target_yaw"]
            )
            position_errors.append(float(pos_mm))
            sample = trial_outcome(
                position_error_mm=pos_mm,
                yaw_error_deg=yaw_deg,
                grasping_now=bool(info.get("grasping", False)),
                grasped_during=grasped_during,
                box_z=float(info["box_z"]),
                table_z=float(info["table_z"]),
                ee_xy=info["ee_xy"],
                box_xy=info["box_xy"],
            )
            if sample.grasp_success:
                n_grasp += 1
            if sample.holding_at_end:
                n_holding += 1
            if sample.released_on_pad:
                n_released += 1
            if is_align_success(pos_mm, yaw_deg):
                n_align += 1
        metrics: dict[str, float | str | None] = {
            "grasp_success_rate": float(n_grasp) / float(episodes),
            "align_success_rate": float(n_align) / float(episodes),
            "mean_position_error_mm": (float(np.mean(position_errors)) if position_errors else 0.0),
            "holding_at_end_rate": float(n_holding) / float(episodes),
            "released_on_pad_rate": float(n_released) / float(episodes),
            "n_episodes": float(episodes),
            "error": None,
        }
        print(
            f"closed_loop_val end mode={label} grasp={metrics['grasp_success_rate']} "
            f"align={metrics['align_success_rate']} "
            f"pos_mm={metrics['mean_position_error_mm']} "
            f"holding={metrics['holding_at_end_rate']} "
            f"released_on_pad={metrics['released_on_pad_rate']}",
            flush=True,
        )
        return metrics
    except Exception as exc:  # noqa: BLE001 - keep training alive on sim/GL faults
        traceback.print_exc()
        print(f"closed_loop_val FAILED: {exc!r}", flush=True)
        return _empty_closed_loop_metrics(episodes, error=repr(exc))
    finally:
        if env is not None:
            env.close()
        if was_training:
            policy.train()
        if device_name == "mps" and hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
        gc.collect()


def _arch_from_policy(policy: Any) -> dict[str, Any]:
    stored = getattr(policy, "_port_pick_align_arch", None)
    if isinstance(stored, dict):
        return dict(stored)
    return resolve_arch("smoke")


def closed_loop_selection_improves(
    align_rate: float,
    position_error_mm: float,
    best_align_rate: float | None,
    best_position_error_mm: float | None,
) -> bool:
    """True when align rate is higher, or equal and position error is lower."""
    if best_align_rate is None or best_position_error_mm is None:
        return True
    if align_rate > best_align_rate:
        return True
    return align_rate == best_align_rate and position_error_mm < best_position_error_mm


def _save_checkpoint(
    path: Path,
    *,
    policy: Any,
    contract: dict[str, Any],
    step: int,
    train_loss: float,
    val_l1: float | None,
    device_name: str,
    selection_metric: str,
    closed_loop_grasp_rate: float | None = None,
    closed_loop_align_rate: float | None = None,
    closed_loop_position_error_mm: float | None = None,
) -> None:
    payload: dict[str, Any] = {
        "model_state_dict": policy.state_dict(),
        "contract": contract,
        "arch": _arch_from_policy(policy),
        "step": step,
        "train_loss": train_loss,
        "val_l1": val_l1,
        "device": device_name,
        "selection_metric": selection_metric,
    }
    if closed_loop_grasp_rate is not None:
        payload["closed_loop_grasp_rate"] = closed_loop_grasp_rate
    if closed_loop_align_rate is not None:
        payload["closed_loop_align_rate"] = closed_loop_align_rate
    if closed_loop_position_error_mm is not None:
        payload["closed_loop_position_error_mm"] = closed_loop_position_error_mm
    torch.save(payload, path)


def train_act(
    contract: dict[str, Any],
    dataset_root: Path,
    output_dir: Path,
    *,
    steps: int = 100,
    batch_size: int = 2,
    learning_rate: float = 1e-4,
    seed: int = 0,
    device: str | None = None,
    repo_id: str = DEFAULT_REPO_ID,
    val_ratio: float = 0.1,
    val_interval: int = 100,
    max_val_batches: int = 32,
    scheduler: str = "cosine",
    arch: str = "smoke",
    gripper_loss_weight: float = 1.0,
    gripper_dim: int = DEFAULT_GRIPPER_DIM,
    transition_oversample_window: int = 0,
    transition_oversample_factor: int = 1,
    closed_loop_val_interval: int = 0,
    closed_loop_val_episodes: int = SIM_DEFAULT_CLOSED_LOOP_VAL_EPISODES,
    closed_loop_val_max_steps: int = SIM_DEFAULT_CLOSED_LOOP_VAL_MAX_STEPS,
    closed_loop_n_action_steps: int = CLOSED_LOOP_SELECTION_N_ACTION_STEPS,
    closed_loop_te_episodes: int = 0,
    selection_metric: str | None = None,
) -> Path:
    """Train ACT and save best_model.pt.

    Default selection is lowest validation L1 when a val split exists, else
    lowest training loss. Pass ``selection_metric='closed_loop_align'`` to keep
    the checkpoint with the highest closed-loop align rate, breaking ties by
    lower position error. That rate is measured with ``n_action_steps`` (default
    30) and temporal ensembling off. ``closed_loop_grasp`` keeps the highest
    grasp rate on the same rollout. Either closed-loop rule requires
    ``closed_loop_val_interval > 0``. When ``closed_loop_te_episodes > 0``, the
    same pulse also logs a temporal-ensemble rollout; those numbers are not
    compared when saving ``best_model.pt``. The final weights are always
    written to ``last.pt``.
    """
    if steps < 1:
        raise ValueError(f"steps must be >= 1, got {steps}")
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    if val_interval < 1:
        raise ValueError(f"val_interval must be >= 1, got {val_interval}")
    if max_val_batches < 0:
        raise ValueError(f"max_val_batches must be >= 0, got {max_val_batches}")
    if scheduler not in {"cosine", "none"}:
        raise ValueError(f"scheduler must be 'cosine' or 'none', got {scheduler!r}")
    if gripper_loss_weight <= 0:
        raise ValueError(f"gripper_loss_weight must be > 0, got {gripper_loss_weight}")
    if transition_oversample_factor < 1:
        raise ValueError(
            f"transition_oversample_factor must be >= 1, got {transition_oversample_factor}"
        )
    if transition_oversample_window < 0:
        raise ValueError(
            f"transition_oversample_window must be >= 0, got {transition_oversample_window}"
        )
    if closed_loop_val_interval < 0:
        raise ValueError(f"closed_loop_val_interval must be >= 0, got {closed_loop_val_interval}")
    if closed_loop_te_episodes < 0:
        raise ValueError(f"closed_loop_te_episodes must be >= 0, got {closed_loop_te_episodes}")
    if closed_loop_n_action_steps < 1:
        raise ValueError(
            f"closed_loop_n_action_steps must be >= 1, got {closed_loop_n_action_steps}"
        )

    validate_contract(contract)
    device_name = resolve_device(device)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    dataset = load_training_dataset(dataset_root, contract, repo_id=repo_id)
    if len(dataset) == 0:
        raise ValueError(f"Empty dataset at {dataset_root}")

    train_data, val_data, n_train_episodes, n_val_episodes = split_train_val(
        dataset, val_ratio, seed
    )
    if selection_metric is None:
        resolved_selection = "val_l1" if val_data is not None else "train_loss"
    else:
        resolved_selection = selection_metric
    if resolved_selection not in {
        "val_l1",
        "train_loss",
        "closed_loop_grasp",
        "closed_loop_align",
    }:
        raise ValueError(
            "selection_metric must be val_l1, train_loss, closed_loop_grasp, "
            f"or closed_loop_align, got {resolved_selection!r}"
        )
    if resolved_selection in {"closed_loop_grasp", "closed_loop_align"} and (
        closed_loop_val_interval < 1
    ):
        raise ValueError(
            f"selection_metric={resolved_selection!r} requires closed_loop_val_interval >= 1"
        )
    if resolved_selection == "val_l1" and val_data is None:
        resolved_selection = "train_loss"

    n_transition_frames = 0
    n_train_before_oversample = (
        len(train_data.indices)  # type: ignore[attr-defined]
        if isinstance(train_data, Subset)
        else len(train_data)
    )
    if transition_oversample_factor > 1 and transition_oversample_window >= 0:
        base_indices = (
            list(train_data.indices)  # type: ignore[attr-defined]
            if isinstance(train_data, Subset)
            else list(range(len(train_data)))
        )
        transitions = find_gripper_transition_indices(
            dataset,
            base_indices,
            gripper_dim=gripper_dim,
            direction="both",
        )
        n_transition_frames = len(transitions)
        expanded = oversample_indices_near_transitions(
            base_indices,
            transitions,
            dataset,
            window=transition_oversample_window,
            factor=transition_oversample_factor,
        )
        train_data = Subset(dataset, expanded)

    val_batch_cap: int | None = None if max_val_batches == 0 else max_val_batches

    policy = build_act_policy(contract, device=device_name, arch=arch)
    policy.train()
    policy.to(device_name)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=learning_rate)
    lr_scheduler: torch.optim.lr_scheduler.LRScheduler | None
    if scheduler == "cosine":
        lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer,
            T_max=steps,
            eta_min=learning_rate * 0.01,
        )
    else:
        lr_scheduler = None

    train_loader = DataLoader(
        train_data,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        collate_fn=lambda samples: collate_act_batch(samples, device_name),
        drop_last=len(train_data) >= batch_size,
    )
    if len(train_loader) == 0:
        raise ValueError(
            f"Training loader is empty (n={len(train_data)}, batch_size={batch_size}). "
            "Lower --batch-size."
        )
    val_loader: DataLoader | None = None
    if val_data is not None:
        val_loader = DataLoader(
            val_data,
            batch_size=min(batch_size, len(val_data)),
            shuffle=False,
            num_workers=0,
            collate_fn=lambda samples: collate_act_batch(samples, device_name),
            drop_last=False,
        )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / CHECKPOINT_NAME

    # val_l1 / train_loss: minimize. closed-loop rates: maximize.
    maximize = resolved_selection in {"closed_loop_grasp", "closed_loop_align"}
    best_score = float("-inf") if maximize else float("inf")
    best_train_loss = float("inf")
    best_val_l1: float | None = None
    best_closed_loop_grasp: float | None = None
    best_closed_loop_align: float | None = None
    best_closed_loop_pos_mm: float | None = None
    selected_te_align: float | None = None
    selected_te_pos_mm: float | None = None
    history: list[dict[str, float | int | None]] = []
    if closed_loop_val_interval > 0:
        print(
            "checkpoint selection "
            f"metric={resolved_selection} "
            f"exec=n_action_steps_{int(closed_loop_n_action_steps)} "
            "temporal_ensemble=off "
            f"episodes={int(closed_loop_val_episodes)} "
            f"te_episodes={int(closed_loop_te_episodes)} (logged only)",
            flush=True,
        )
    step = 0
    data_iter = iter(train_loader)

    while step < steps:
        try:
            batch = next(data_iter)
        except StopIteration:
            data_iter = iter(train_loader)
            batch = next(data_iter)

        loss, loss_dict = compute_act_train_loss(
            policy,
            batch,
            gripper_loss_weight=gripper_loss_weight,
            gripper_dim=gripper_dim,
        )
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
        optimizer.step()

        loss_value = float(loss.detach().item())
        step += 1
        current_lr = float(optimizer.param_groups[0]["lr"])
        if loss_value < best_train_loss:
            best_train_loss = loss_value

        val_l1: float | None = None
        ran_val = val_loader is not None and (step % val_interval == 0 or step == steps)
        if ran_val and val_loader is not None:
            val_l1 = evaluate_val_l1(policy, val_loader, max_batches=val_batch_cap)
            if best_val_l1 is None or val_l1 < best_val_l1:
                best_val_l1 = val_l1

        closed_loop_grasp: float | None = None
        closed_loop_align: float | None = None
        closed_loop_pos_mm: float | None = None
        closed_loop_holding: float | None = None
        closed_loop_released: float | None = None
        te_align: float | None = None
        te_grasp: float | None = None
        te_pos_mm: float | None = None
        te_released: float | None = None
        cl_error: str | None = None
        ran_closed_loop = closed_loop_val_interval > 0 and (
            step % closed_loop_val_interval == 0 or step == steps
        )
        if ran_closed_loop:
            cl_metrics = evaluate_closed_loop_grasp(
                policy,
                contract,
                device=device_name,
                episodes=closed_loop_val_episodes,
                max_steps=closed_loop_val_max_steps,
                seed=seed + step,
                n_action_steps=closed_loop_n_action_steps,
                temporal_ensemble=False,
                mode_label=f"chunk{int(closed_loop_n_action_steps)}",
            )
            closed_loop_grasp = float(cl_metrics["grasp_success_rate"] or 0.0)
            closed_loop_align = float(cl_metrics["align_success_rate"] or 0.0)
            closed_loop_pos_mm = float(cl_metrics["mean_position_error_mm"] or 0.0)
            closed_loop_holding = float(cl_metrics["holding_at_end_rate"] or 0.0)
            closed_loop_released = float(cl_metrics["released_on_pad_rate"] or 0.0)
            raw_error = cl_metrics.get("error")
            cl_error = str(raw_error) if raw_error else None
            if cl_error:
                print(
                    f"closed_loop_val error at step={step}: {cl_error}",
                    flush=True,
                )
            if closed_loop_te_episodes > 0:
                te_metrics = evaluate_closed_loop_grasp(
                    policy,
                    contract,
                    device=device_name,
                    episodes=closed_loop_te_episodes,
                    max_steps=closed_loop_val_max_steps,
                    seed=seed + step,
                    n_action_steps=1,
                    temporal_ensemble=True,
                    mode_label="te",
                )
                te_error = te_metrics.get("error")
                if te_error:
                    print(
                        f"closed_loop_val te error at step={step}: {te_error}",
                        flush=True,
                    )
                else:
                    te_grasp = float(te_metrics["grasp_success_rate"] or 0.0)
                    te_align = float(te_metrics["align_success_rate"] or 0.0)
                    te_pos_mm = float(te_metrics["mean_position_error_mm"] or 0.0)
                    te_released = float(te_metrics["released_on_pad_rate"] or 0.0)

        record: dict[str, float | int | None] = {
            "step": step,
            "train_loss": loss_value,
            "train_l1_unweighted": float(loss_dict["l1_loss"]),
            "lr": current_lr,
            "val_l1": val_l1,
            "closed_loop_grasp_rate": closed_loop_grasp,
            "closed_loop_align_rate": closed_loop_align,
            "closed_loop_mean_position_error_mm": closed_loop_pos_mm,
            "closed_loop_holding_at_end_rate": closed_loop_holding,
            "closed_loop_released_on_pad_rate": closed_loop_released,
            "closed_loop_te_grasp_rate": te_grasp,
            "closed_loop_te_align_rate": te_align,
            "closed_loop_te_mean_position_error_mm": te_pos_mm,
            "closed_loop_te_released_on_pad_rate": te_released,
        }
        history.append(record)

        improved = False
        if resolved_selection == "val_l1" and val_l1 is not None and val_l1 < best_score:
            best_score = val_l1
            improved = True
        elif resolved_selection == "train_loss" and loss_value < best_score:
            best_score = loss_value
            improved = True
        elif (
            resolved_selection == "closed_loop_grasp"
            and closed_loop_grasp is not None
            and cl_error is None
            and closed_loop_grasp > best_score
        ):
            best_score = closed_loop_grasp
            best_closed_loop_grasp = closed_loop_grasp
            selected_te_align = te_align
            selected_te_pos_mm = te_pos_mm
            improved = True
        elif (
            resolved_selection == "closed_loop_align"
            and closed_loop_align is not None
            and closed_loop_pos_mm is not None
            and cl_error is None
            and closed_loop_selection_improves(
                closed_loop_align,
                closed_loop_pos_mm,
                best_closed_loop_align,
                best_closed_loop_pos_mm,
            )
        ):
            best_score = closed_loop_align
            best_closed_loop_align = closed_loop_align
            best_closed_loop_pos_mm = closed_loop_pos_mm
            selected_te_align = te_align
            selected_te_pos_mm = te_pos_mm
            improved = True
        if improved:
            _save_checkpoint(
                checkpoint_path,
                policy=policy,
                contract=contract,
                step=step,
                train_loss=loss_value,
                val_l1=val_l1 if val_l1 is not None else best_val_l1,
                device_name=device_name,
                selection_metric=resolved_selection,
                closed_loop_grasp_rate=closed_loop_grasp,
                closed_loop_align_rate=closed_loop_align,
                closed_loop_position_error_mm=closed_loop_pos_mm,
            )

        if lr_scheduler is not None:
            lr_scheduler.step()

        if (
            step == 1
            or step % 10 == 0
            or step == steps
            or val_l1 is not None
            or closed_loop_grasp is not None
        ):
            val_text = f"{val_l1:.6f}" if val_l1 is not None else "n/a"
            cl_text = f"{closed_loop_grasp:.2f}" if closed_loop_grasp is not None else "n/a"
            align_text = f"{closed_loop_align:.2f}" if closed_loop_align is not None else "n/a"
            pos_text = f"{closed_loop_pos_mm:.1f}" if closed_loop_pos_mm is not None else "n/a"
            te_align_text = f"{te_align:.2f}" if te_align is not None else "n/a"
            te_pos_text = f"{te_pos_mm:.1f}" if te_pos_mm is not None else "n/a"
            print(
                f"step={step:04d}/{steps:04d} train_loss={loss_value:.6f} "
                f"val_l1={val_text} cl_grasp={cl_text} cl_align={align_text} "
                f"cl_pos_mm={pos_text} te_align={te_align_text} te_pos_mm={te_pos_text} "
                f"lr={current_lr:.3e} best_{resolved_selection}={best_score:.6f}"
            )

    last_path = output_dir / LAST_CHECKPOINT_NAME
    _save_checkpoint(
        last_path,
        policy=policy,
        contract=contract,
        step=step,
        train_loss=loss_value,
        val_l1=val_l1 if val_l1 is not None else best_val_l1,
        device_name=device_name,
        selection_metric=resolved_selection,
        closed_loop_grasp_rate=closed_loop_grasp,
        closed_loop_align_rate=closed_loop_align,
        closed_loop_position_error_mm=closed_loop_pos_mm,
    )
    if not checkpoint_path.is_file():
        _save_checkpoint(
            checkpoint_path,
            policy=policy,
            contract=contract,
            step=step,
            train_loss=loss_value,
            val_l1=val_l1 if val_l1 is not None else best_val_l1,
            device_name=device_name,
            selection_metric=resolved_selection,
            closed_loop_grasp_rate=closed_loop_grasp,
            closed_loop_align_rate=closed_loop_align,
            closed_loop_position_error_mm=closed_loop_pos_mm,
        )

    if resolved_selection == "train_loss":
        reported_best = best_train_loss
    elif resolved_selection == "closed_loop_align" and best_closed_loop_align is not None:
        reported_best = best_closed_loop_align
    else:
        reported_best = best_score
    metrics_path = output_dir / "training_metrics.json"
    metrics = {
        "result": "PASS",
        "steps": step,
        "best_loss": reported_best,
        "best_train_loss": best_train_loss,
        "best_val_l1": best_val_l1,
        "best_closed_loop_grasp_rate": best_closed_loop_grasp,
        "best_closed_loop_align_rate": best_closed_loop_align,
        "best_closed_loop_position_error_mm": best_closed_loop_pos_mm,
        "selection_metric": resolved_selection,
        "closed_loop_selection_exec": f"n_action_steps_{int(closed_loop_n_action_steps)}",
        "closed_loop_te_used_for_selection": False,
        "selected_closed_loop_te_align_rate": selected_te_align,
        "selected_closed_loop_te_position_error_mm": selected_te_pos_mm,
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "val_ratio": val_ratio,
        "val_interval": val_interval,
        "max_val_batches": max_val_batches,
        "scheduler": scheduler,
        "gripper_loss_weight": gripper_loss_weight,
        "gripper_dim": gripper_dim,
        "transition_oversample_window": transition_oversample_window,
        "transition_oversample_factor": transition_oversample_factor,
        "n_gripper_transitions": n_transition_frames,
        "n_train_before_oversample": n_train_before_oversample,
        "closed_loop_val_interval": closed_loop_val_interval,
        "closed_loop_val_episodes": closed_loop_val_episodes,
        "closed_loop_val_max_steps": closed_loop_val_max_steps,
        "closed_loop_n_action_steps": closed_loop_n_action_steps,
        "closed_loop_te_episodes": closed_loop_te_episodes,
        "n_train": len(train_data),
        "n_val": 0 if val_data is None else len(val_data),
        "n_train_episodes": n_train_episodes,
        "n_val_episodes": n_val_episodes,
        "recommended_min_steps": RECOMMENDED_MIN_STEPS,
        "below_recommended_steps": step < RECOMMENDED_MIN_STEPS,
        "checkpoint": str(checkpoint_path),
        "last_checkpoint": str(last_path),
        "dataset_root": str(dataset_root),
        "device": device_name,
        "repo_id": repo_id,
        "arch": _arch_from_policy(policy),
        "history": history,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    if not checkpoint_path.is_file():
        raise RuntimeError("Training finished without saving a checkpoint")
    return checkpoint_path


def load_policy_from_checkpoint(
    checkpoint_path: Path,
    contract: dict[str, Any],
    *,
    device: str | None = None,
):
    device_name = resolve_device(device)
    payload = torch.load(checkpoint_path, map_location=device_name, weights_only=False)
    arch_info = payload.get("arch")
    if isinstance(arch_info, dict) and arch_info:
        # Structure must match training; ImageNet init is overwritten by state_dict.
        policy = build_act_policy(
            contract,
            device=device_name,
            arch=str(arch_info.get("arch", "smoke")),
            dim_model=arch_info.get("dim_model"),
            n_heads=arch_info.get("n_heads"),
            dim_feedforward=arch_info.get("dim_feedforward"),
            n_encoder_layers=arch_info.get("n_encoder_layers"),
            n_decoder_layers=arch_info.get("n_decoder_layers"),
            pretrained_backbone_weights=None,
        )
    else:
        policy = build_act_policy(contract, device=device_name, arch="smoke")
    policy.load_state_dict(payload["model_state_dict"])
    policy.to(device_name)
    policy.eval()
    return policy


def run_inference_smoke(
    policy,
    contract: dict[str, Any],
    *,
    device: str | None = None,
) -> torch.Tensor:
    """Feed dummy 2-camera images + state; return action chunk of shape (chunk, 6)."""
    device_name = resolve_device(device)
    top = contract["cameras"]["top"]
    wrist = contract["cameras"]["wrist"]
    chunk_size = int(contract["model"]["chunk_size"])
    action_dim = int(contract["model"]["action_dim"])

    top_img = make_dummy_image(
        int(top["height"]), int(top["width"]), int(top["channels"]), frame_idx=0, seed=1
    )
    wrist_img = make_dummy_image(
        int(wrist["height"]), int(wrist["width"]), int(wrist["channels"]), frame_idx=0, seed=2
    )
    state = np.zeros((action_dim,), dtype=np.float32)

    batch = {
        "observation.images.top": _to_batch_tensor(
            torch.from_numpy(top_img).permute(2, 0, 1), device_name
        ),
        "observation.images.wrist": _to_batch_tensor(
            torch.from_numpy(wrist_img).permute(2, 0, 1), device_name
        ),
        "observation.state": _to_batch_tensor(state, device_name),
    }

    with torch.inference_mode():
        chunk_tensor = policy.predict_action_chunk(batch)

    if not isinstance(chunk_tensor, torch.Tensor):
        raise TypeError(f"predict_action_chunk returned {type(chunk_tensor)}")
    chunk: torch.Tensor = chunk_tensor
    if chunk.ndim == 3:
        chunk = chunk[0]
    if tuple(chunk.shape) != (chunk_size, action_dim):
        raise AssertionError(
            f"Expected action chunk {(chunk_size, action_dim)}, got {tuple(chunk.shape)}"
        )
    return chunk


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ACT on a contract-aligned LeRobotDataset.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--repo-id", type=str, default=DEFAULT_REPO_ID)
    parser.add_argument(
        "--preset",
        choices=("synthetic", "sim"),
        default=None,
        help="sim selects data/sim_expert/lerobot and checkpoints/sim_act unless overridden.",
    )
    parser.add_argument(
        "--arch",
        choices=tuple(sorted(ARCH_PRESETS)),
        default=None,
        help=(
            "smoke=small CI net; full=sim Phase 1.5 capacity. "
            "Default: full for --preset sim, else smoke."
        ),
    )
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--lr", "--learning-rate", dest="learning_rate", type=float, default=1e-4)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--val-interval", type=int, default=100)
    parser.add_argument(
        "--max-val-batches",
        type=int,
        default=32,
        help="Max validation batches per eval. 0 = full validation set.",
    )
    parser.add_argument("--scheduler", choices=("cosine", "none"), default="cosine")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="mps, cuda, or cpu. Default: mps if available, else cuda, else cpu.",
    )
    parser.add_argument(
        "--gripper-loss-weight",
        type=float,
        default=None,
        help=(
            "Multiply L1 on the gripper action dim. "
            f"Default: {SIM_DEFAULT_GRIPPER_LOSS_WEIGHT} for --preset sim, else 1.0."
        ),
    )
    parser.add_argument(
        "--gripper-dim",
        type=int,
        default=DEFAULT_GRIPPER_DIM,
        help="Action dimension index for the gripper (default: 5).",
    )
    parser.add_argument(
        "--transition-oversample-window",
        type=int,
        default=None,
        help=(
            "Frames before/after gripper transitions (grasp and release) to oversample. "
            f"Default: {SIM_DEFAULT_TRANSITION_OVERSAMPLE_WINDOW} for --preset sim, else 0."
        ),
    )
    parser.add_argument(
        "--transition-oversample-factor",
        type=int,
        default=None,
        help=(
            "How many times to include transition-window frames (1 = off). "
            f"Default: {SIM_DEFAULT_TRANSITION_OVERSAMPLE_FACTOR} for --preset sim, else 1."
        ),
    )
    parser.add_argument(
        "--closed-loop-val-interval",
        type=int,
        default=None,
        help=(
            "Run cheap closed-loop grasp eval every N steps (0 = off). "
            "Default: same as --val-interval for --preset sim, else 0."
        ),
    )
    parser.add_argument(
        "--closed-loop-val-episodes",
        type=int,
        default=SIM_DEFAULT_CLOSED_LOOP_VAL_EPISODES,
        help=(
            "Episodes per closed-loop validation pulse used for checkpoint "
            f"selection (default {SIM_DEFAULT_CLOSED_LOOP_VAL_EPISODES}; use 10–20)."
        ),
    )
    parser.add_argument(
        "--closed-loop-val-max-steps",
        type=int,
        default=SIM_DEFAULT_CLOSED_LOOP_VAL_MAX_STEPS,
        help="Max control steps per closed-loop validation episode.",
    )
    parser.add_argument(
        "--closed-loop-n-action-steps",
        type=int,
        default=CLOSED_LOOP_SELECTION_N_ACTION_STEPS,
        help=(
            "Chunk horizon executed between replans during the closed-loop "
            "rollout that selects the checkpoint. Default 30. Temporal "
            "ensembling is not used for this choice."
        ),
    )
    parser.add_argument(
        "--closed-loop-te-episodes",
        type=int,
        default=None,
        help=(
            "Episodes for a temporal-ensemble rollout logged next to chunk "
            "selection (0 = off). Default: same as --closed-loop-val-episodes "
            "for --preset sim when closed-loop validation is on, else 0."
        ),
    )
    parser.add_argument(
        "--selection-metric",
        choices=("val_l1", "train_loss", "closed_loop_grasp", "closed_loop_align"),
        default=None,
        help=(
            "Checkpoint selection rule. Default: closed_loop_align for --preset sim "
            "(align rate, then lower position error); otherwise val_l1 when a val "
            "split exists, else train_loss."
        ),
    )
    parser.add_argument(
        "--infer-only",
        action="store_true",
        help="Skip training and only run inference smoke from existing checkpoint.",
    )
    parser.add_argument(
        "--skip-infer",
        action="store_true",
        help="Skip the post-training inference smoke check.",
    )
    return parser.parse_args(argv)


def apply_preset_defaults(args: argparse.Namespace) -> None:
    """Fill sim-expert paths and grasp-transition defaults for --preset sim."""
    if args.preset != "sim":
        if args.arch is None:
            args.arch = "smoke"
        if args.gripper_loss_weight is None:
            args.gripper_loss_weight = 1.0
        if args.transition_oversample_window is None:
            args.transition_oversample_window = 0
        if args.transition_oversample_factor is None:
            args.transition_oversample_factor = 1
        if args.closed_loop_val_interval is None:
            args.closed_loop_val_interval = 0
        if args.closed_loop_te_episodes is None:
            args.closed_loop_te_episodes = 0
        return
    if args.dataset_root == DEFAULT_DATASET_ROOT:
        args.dataset_root = SIM_DATASET_ROOT
    if args.output_dir == DEFAULT_OUTPUT_DIR:
        args.output_dir = SIM_OUTPUT_DIR
    if args.repo_id == DEFAULT_REPO_ID:
        args.repo_id = SIM_REPO_ID
    if args.arch is None:
        args.arch = "full"
    if args.gripper_loss_weight is None:
        args.gripper_loss_weight = SIM_DEFAULT_GRIPPER_LOSS_WEIGHT
    if args.transition_oversample_window is None:
        args.transition_oversample_window = SIM_DEFAULT_TRANSITION_OVERSAMPLE_WINDOW
    if args.transition_oversample_factor is None:
        args.transition_oversample_factor = SIM_DEFAULT_TRANSITION_OVERSAMPLE_FACTOR
    if args.closed_loop_val_interval is None:
        args.closed_loop_val_interval = int(args.val_interval)
    if args.selection_metric is None and int(args.closed_loop_val_interval) > 0:
        args.selection_metric = "closed_loop_align"
    if args.closed_loop_te_episodes is None:
        if int(args.closed_loop_val_interval) > 0:
            args.closed_loop_te_episodes = int(args.closed_loop_val_episodes)
        else:
            args.closed_loop_te_episodes = 0


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    apply_preset_defaults(args)
    contract = load_contract(args.contract)
    validate_contract(contract)
    device = resolve_device(args.device)
    checkpoint_path = Path(args.output_dir) / CHECKPOINT_NAME

    if not args.infer_only:
        checkpoint_path = train_act(
            contract,
            args.dataset_root,
            args.output_dir,
            steps=args.steps,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            seed=args.seed,
            device=device,
            repo_id=args.repo_id,
            val_ratio=args.val_ratio,
            val_interval=args.val_interval,
            max_val_batches=args.max_val_batches,
            scheduler=args.scheduler,
            arch=str(args.arch),
            gripper_loss_weight=float(args.gripper_loss_weight),
            gripper_dim=int(args.gripper_dim),
            transition_oversample_window=int(args.transition_oversample_window),
            transition_oversample_factor=int(args.transition_oversample_factor),
            closed_loop_val_interval=int(args.closed_loop_val_interval),
            closed_loop_val_episodes=int(args.closed_loop_val_episodes),
            closed_loop_val_max_steps=int(args.closed_loop_val_max_steps),
            closed_loop_n_action_steps=int(args.closed_loop_n_action_steps),
            closed_loop_te_episodes=int(args.closed_loop_te_episodes),
            selection_metric=args.selection_metric,
        )
        print(f"Saved checkpoint: {checkpoint_path}")

    if not args.skip_infer:
        if not checkpoint_path.is_file():
            raise SystemExit(f"Checkpoint not found: {checkpoint_path}")
        policy = load_policy_from_checkpoint(checkpoint_path, contract, device=device)
        chunk = run_inference_smoke(policy, contract, device=device)
        print(f"Inference OK: action chunk shape={tuple(chunk.shape)}")


if __name__ == "__main__":
    main()
