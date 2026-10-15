"""Device selection, validation split, and CLI preset for ACT training."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("lerobot")

import torch  # noqa: E402
from torch.utils.data import TensorDataset  # noqa: E402

from port_pick_align.training.train_act import (  # noqa: E402
    apply_preset_defaults,
    parse_args,
    resolve_device,
    split_train_val,
)


def _mps_available() -> bool:
    backend = getattr(torch.backends, "mps", None)
    return backend is not None and bool(backend.is_available())


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
    train, val = split_train_val(dataset, val_ratio=0.2, seed=0)
    assert len(train) == 8
    assert val is not None
    assert len(val) == 2
    train_only, no_val = split_train_val(dataset, val_ratio=0.0, seed=0)
    assert len(train_only) == 10
    assert no_val is None


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
