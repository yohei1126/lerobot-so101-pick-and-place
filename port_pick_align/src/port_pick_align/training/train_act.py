"""ACT training and inference for contract-aligned LeRobot datasets.

Device selection prefers MPS, then CUDA, then CPU. Full sim-expert training
(1,000 steps or more) is intended for Apple Silicon. Short CPU runs only check
that the loop, validation split, and checkpoint write succeed.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader, Subset, random_split

from port_pick_align.contract import DEFAULT_CONTRACT_PATH, load_contract, validate_contract
from port_pick_align.dataset.sim_collect import DEFAULT_REPO_ID as SIM_REPO_ID
from port_pick_align.dataset.synthetic import DEFAULT_REPO_ID, make_dummy_image
from port_pick_align.training.policy import ARCH_PRESETS, build_act_policy, resolve_arch

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATASET_ROOT = REPO_ROOT / "data" / "synthetic" / "lerobot"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "checkpoints" / "synthetic_act"
SIM_DATASET_ROOT = REPO_ROOT / "data" / "sim_expert" / "lerobot"
SIM_OUTPUT_DIR = REPO_ROOT / "checkpoints" / "sim_act"
CHECKPOINT_NAME = "best_model.pt"
RECOMMENDED_MIN_STEPS = 1000


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


def _arch_from_policy(policy: Any) -> dict[str, Any]:
    stored = getattr(policy, "_port_pick_align_arch", None)
    if isinstance(stored, dict):
        return dict(stored)
    return resolve_arch("smoke")


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
) -> None:
    torch.save(
        {
            "model_state_dict": policy.state_dict(),
            "contract": contract,
            "arch": _arch_from_policy(policy),
            "step": step,
            "train_loss": train_loss,
            "val_l1": val_l1,
            "device": device_name,
            "selection_metric": selection_metric,
        },
        path,
    )


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
) -> Path:
    """Train ACT and save best_model.pt.

    When a validation split exists, the checkpoint is the lowest validation L1.
    Otherwise it is the lowest training loss. Returns the checkpoint path.
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
    selection_metric = "val_l1" if val_data is not None else "train_loss"
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

    best_score = float("inf")
    best_train_loss = float("inf")
    best_val_l1: float | None = None
    history: list[dict[str, float | int | None]] = []
    step = 0
    data_iter = iter(train_loader)

    while step < steps:
        try:
            batch = next(data_iter)
        except StopIteration:
            data_iter = iter(train_loader)
            batch = next(data_iter)

        loss, _loss_dict = policy(batch)
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

        record: dict[str, float | int | None] = {
            "step": step,
            "train_loss": loss_value,
            "lr": current_lr,
            "val_l1": val_l1,
        }
        history.append(record)

        improved = False
        if selection_metric == "val_l1" and val_l1 is not None and val_l1 < best_score:
            best_score = val_l1
            best_val_l1 = val_l1
            improved = True
        elif selection_metric == "train_loss" and loss_value < best_score:
            best_score = loss_value
            improved = True
        if improved:
            _save_checkpoint(
                checkpoint_path,
                policy=policy,
                contract=contract,
                step=step,
                train_loss=loss_value,
                val_l1=val_l1,
                device_name=device_name,
                selection_metric=selection_metric,
            )

        if lr_scheduler is not None:
            lr_scheduler.step()

        if step == 1 or step % 10 == 0 or step == steps or val_l1 is not None:
            val_text = f"{val_l1:.6f}" if val_l1 is not None else "n/a"
            print(
                f"step={step:04d}/{steps:04d} train_loss={loss_value:.6f} "
                f"val_l1={val_text} lr={current_lr:.3e} best_{selection_metric}={best_score:.6f}"
            )

    if selection_metric == "train_loss":
        reported_best = best_train_loss
    else:
        reported_best = best_score
    metrics_path = output_dir / "training_metrics.json"
    metrics = {
        "result": "PASS",
        "steps": step,
        "best_loss": reported_best,
        "best_train_loss": best_train_loss,
        "best_val_l1": best_val_l1,
        "selection_metric": selection_metric,
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "val_ratio": val_ratio,
        "val_interval": val_interval,
        "max_val_batches": max_val_batches,
        "scheduler": scheduler,
        "n_train": len(train_data),
        "n_val": 0 if val_data is None else len(val_data),
        "n_train_episodes": n_train_episodes,
        "n_val_episodes": n_val_episodes,
        "recommended_min_steps": RECOMMENDED_MIN_STEPS,
        "below_recommended_steps": step < RECOMMENDED_MIN_STEPS,
        "checkpoint": str(checkpoint_path),
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
        help="smoke=small CI net; full=sim Phase 1.5 capacity. Default: full for --preset sim, else smoke.",
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
    """Fill sim-expert paths when the user kept the synthetic defaults."""
    if args.preset != "sim":
        if args.arch is None:
            args.arch = "smoke"
        return
    if args.dataset_root == DEFAULT_DATASET_ROOT:
        args.dataset_root = SIM_DATASET_ROOT
    if args.output_dir == DEFAULT_OUTPUT_DIR:
        args.output_dir = SIM_OUTPUT_DIR
    if args.repo_id == DEFAULT_REPO_ID:
        args.repo_id = SIM_REPO_ID
    if args.arch is None:
        args.arch = "full"


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
