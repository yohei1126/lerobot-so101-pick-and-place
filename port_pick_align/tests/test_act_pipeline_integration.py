"""Integration smoke: synthetic data → short ACT train → inference shape."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from port_pick_align.contract import load_contract

pytest.importorskip("torch")
pytest.importorskip("lerobot")

from port_pick_align.dataset.synthetic import generate_synthetic_dataset  # noqa: E402
from port_pick_align.training.train_act import (  # noqa: E402
    load_policy_from_checkpoint,
    run_inference_smoke,
    train_act,
)


@pytest.mark.integration
def test_synthetic_act_pipeline(tmp_path: Path) -> None:
    contract = load_contract()
    dataset_root = tmp_path / "synth"
    output_dir = tmp_path / "ckpt"

    generate_synthetic_dataset(
        dataset_root,
        contract=contract,
        episodes=2,
        frames=16,
        seed=0,
        repo_id="local/integration_synth",
    )

    checkpoint = train_act(
        contract,
        dataset_root,
        output_dir,
        steps=5,
        batch_size=2,
        seed=0,
        device="cpu",
        repo_id="local/integration_synth",
    )
    assert checkpoint.is_file()

    policy = load_policy_from_checkpoint(checkpoint, contract, device="cpu")
    chunk = run_inference_smoke(policy, contract, device="cpu")
    assert tuple(chunk.shape) == (30, 6)

    metrics_path = output_dir / "training_metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["result"] == "PASS"
    assert metrics["device"] == "cpu"
    assert metrics["selection_metric"] == "val_l1"
    assert metrics["n_val"] >= 1
    assert metrics["n_train"] >= 1
    assert metrics["scheduler"] == "cosine"
    assert metrics["below_recommended_steps"] is True
    assert metrics["history"][-1]["val_l1"] is not None
    assert isinstance(metrics["best_val_l1"], float)
