"""Lightweight ACT training + inference smoke for contract-aligned synthetic data."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from port_pick_align.contract import DEFAULT_CONTRACT_PATH, load_contract, validate_contract
from port_pick_align.dataset.synthetic import DEFAULT_REPO_ID, make_dummy_image
from port_pick_align.training.policy import build_act_policy

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATASET_ROOT = REPO_ROOT / "data" / "synthetic" / "lerobot"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "checkpoints" / "synthetic_act"
CHECKPOINT_NAME = "best_model.pt"


def resolve_device(requested: str | None = None) -> str:
    if requested:
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
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
) -> Path:
    """Train a short ACT run and save best_model.pt. Returns checkpoint path."""
    validate_contract(contract)
    device_name = resolve_device(device)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    dataset = load_training_dataset(dataset_root, contract, repo_id=repo_id)
    if len(dataset) == 0:
        raise ValueError(f"Empty dataset at {dataset_root}")

    policy = build_act_policy(contract, device=device_name)
    policy.train()
    policy.to(device_name)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=learning_rate)

    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        collate_fn=lambda samples: collate_act_batch(samples, device_name),
        drop_last=len(dataset) >= batch_size,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / CHECKPOINT_NAME

    best_loss = float("inf")
    history: list[dict[str, float | int]] = []
    step = 0
    data_iter = iter(loader)

    while step < steps:
        try:
            batch = next(data_iter)
        except StopIteration:
            data_iter = iter(loader)
            batch = next(data_iter)

        loss, _ = policy(batch)
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
        optimizer.step()

        loss_value = float(loss.detach().item())
        step += 1
        history.append({"step": step, "train_loss": loss_value})
        if loss_value < best_loss:
            best_loss = loss_value
            torch.save(
                {
                    "model_state_dict": policy.state_dict(),
                    "contract": contract,
                    "step": step,
                    "train_loss": loss_value,
                    "device": device_name,
                },
                checkpoint_path,
            )
        if step == 1 or step % 10 == 0 or step == steps:
            print(f"step={step:04d}/{steps:04d} train_loss={loss_value:.6f} best={best_loss:.6f}")

    metrics_path = output_dir / "training_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "result": "PASS",
                "steps": step,
                "best_loss": best_loss,
                "checkpoint": str(checkpoint_path),
                "dataset_root": str(dataset_root),
                "device": device_name,
                "history": history,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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
    policy = build_act_policy(contract, device=device_name)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ACT on synthetic LeRobotDataset.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", type=str, default=None)
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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
