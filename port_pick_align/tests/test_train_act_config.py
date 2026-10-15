"""Device selection, validation split, and CLI preset for ACT training."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("torch")
pytest.importorskip("lerobot")

import torch  # noqa: E402
from torch.utils.data import DataLoader, TensorDataset  # noqa: E402

from port_pick_align.training.train_act import (  # noqa: E402
    apply_preset_defaults,
    evaluate_val_l1,
    parse_args,
    resolve_device,
    split_train_val,
)


def _mps_available() -> bool:
    backend = getattr(torch.backends, "mps", None)
    return backend is not None and bool(backend.is_available())


class _EpisodeTable:
    def __init__(self, rows: list[dict[str, int]]) -> None:
        self._rows = rows

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, index: int) -> dict[str, int]:
        return self._rows[index]


class _EpisodeDataset(torch.utils.data.Dataset):
    """Minimal dataset with LeRobot-style ``meta.episodes`` ranges."""

    def __init__(self, frames_per_episode: list[int]) -> None:
        self._n = sum(frames_per_episode)
        rows: list[dict[str, int]] = []
        cursor = 0
        for ep_idx, length in enumerate(frames_per_episode):
            rows.append(
                {
                    "episode_index": ep_idx,
                    "length": length,
                    "dataset_from_index": cursor,
                    "dataset_to_index": cursor + length,
                }
            )
            cursor += length
        self.meta = SimpleNamespace(episodes=_EpisodeTable(rows))

    def __len__(self) -> int:
        return self._n

    def __getitem__(self, index: int) -> dict[str, int]:
        return {"index": index}


class _CountingPolicy:
    def __init__(self) -> None:
        self.calls = 0
        self._training = True

    def eval(self) -> None:
        self._training = False

    def train(self) -> None:
        self._training = True

    def __call__(self, batch: dict[str, Any]) -> tuple[None, dict[str, float]]:
        self.calls += 1
        return None, {"l1_loss": 1.0}


@pytest.mark.unit
def test_resolve_device_auto_order() -> None:
    chosen = resolve_device(None)
    if _mps_available():
        assert chosen == "mps"
    elif torch.cuda.is_available():
        assert chosen == "cuda"
    else:
        assert chosen == "cpu"
    assert resolve_device("cpu") == "cpu"
    assert resolve_device(" CPU ") == "cpu"


@pytest.mark.unit
def test_resolve_device_rejects_missing_accelerator() -> None:
    if _mps_available():
        assert resolve_device("mps") == "mps"
    else:
        with pytest.raises(RuntimeError, match="MPS"):
            resolve_device("mps")
    if torch.cuda.is_available():
        assert resolve_device("cuda") == "cuda"
    else:
        with pytest.raises(RuntimeError, match="CUDA"):
            resolve_device("cuda")


@pytest.mark.unit
def test_split_train_val_keeps_both_sides() -> None:
    dataset = TensorDataset(torch.arange(10))
    train, val, n_train_eps, n_val_eps = split_train_val(dataset, val_ratio=0.2, seed=0)
    assert len(train) == 8
    assert val is not None
    assert len(val) == 2
    assert n_train_eps is None
    assert n_val_eps is None
    train_only, no_val, _, _ = split_train_val(dataset, val_ratio=0.0, seed=0)
    assert len(train_only) == 10
    assert no_val is None


@pytest.mark.unit
def test_split_train_val_episode_level_no_leakage() -> None:
    # 5 episodes × 4 frames; val_ratio=0.2 → 1 val episode, 4 train
    dataset = _EpisodeDataset([4, 4, 4, 4, 4])
    train, val, n_train_eps, n_val_eps = split_train_val(dataset, val_ratio=0.2, seed=0)
    assert n_train_eps == 4
    assert n_val_eps == 1
    assert val is not None
    assert len(train) == 16
    assert len(val) == 4

    train_indices = set(train.indices)  # type: ignore[attr-defined]
    val_indices = set(val.indices)  # type: ignore[attr-defined]
    assert train_indices.isdisjoint(val_indices)
    assert train_indices | val_indices == set(range(20))

    # Each episode is wholly in train or wholly in val
    for start in range(0, 20, 4):
        ep_frames = set(range(start, start + 4))
        in_train = ep_frames <= train_indices
        in_val = ep_frames <= val_indices
        assert in_train ^ in_val


@pytest.mark.unit
def test_parse_args_validation_defaults() -> None:
    args = parse_args([])
    assert args.val_interval == 100
    assert args.max_val_batches == 32


@pytest.mark.unit
def test_evaluate_val_l1_respects_max_batches() -> None:
    class _TinyDataset(torch.utils.data.Dataset):
        def __len__(self) -> int:
            return 8

        def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
            return {"action": torch.zeros(2)}

    loader = DataLoader(_TinyDataset(), batch_size=2, shuffle=False)
    policy = _CountingPolicy()
    score = evaluate_val_l1(policy, loader, max_batches=3)
    assert score == pytest.approx(1.0)
    assert policy.calls == 3


@pytest.mark.unit
def test_sim_preset_rewrites_default_paths() -> None:
    args = parse_args(["--preset", "sim", "--steps", "20", "--lr", "2e-5", "--batch-size", "4"])
    apply_preset_defaults(args)
    assert args.learning_rate == pytest.approx(2e-5)
    assert args.steps == 20
    assert args.batch_size == 4
    assert args.dataset_root.name == "lerobot"
    assert args.dataset_root.parent.name == "sim_expert"
    assert args.output_dir.name == "sim_act"
    assert args.repo_id == "local/port_pick_align_sim_expert"

    custom = parse_args(
        ["--preset", "sim", "--dataset-root", "/tmp/custom_ds", "--output-dir", "/tmp/custom_out"]
    )
    apply_preset_defaults(custom)
    assert custom.dataset_root == Path("/tmp/custom_ds")
    assert custom.output_dir == Path("/tmp/custom_out")
    assert custom.repo_id == "local/port_pick_align_sim_expert"
