"""Integration: sample_bag → convert/validate → ACT ckpt infer (Task 5 host path)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from port_pick_align.contract import load_contract

pytest.importorskip("torch")
pytest.importorskip("lerobot")
pytest.importorskip("rosbags")

from port_pick_align.dataset.converter import convert_bag_to_lerobot  # noqa: E402
from port_pick_align.dataset.synthetic import generate_synthetic_dataset  # noqa: E402
from port_pick_align.training.infer import images_bgr_to_batch, predict_chunk  # noqa: E402
from port_pick_align.training.train_act import (  # noqa: E402
    load_policy_from_checkpoint,
    train_act,
)

FIXTURE_BAG = Path(__file__).resolve().parent / "fixtures" / "sample_bag"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CKPT = REPO_ROOT / "checkpoints" / "synthetic_act" / "best_model.pt"


@pytest.mark.integration
def test_e2e_bag_convert_validate_infer(tmp_path: Path) -> None:
    contract = load_contract()
    chunk_size = int(contract["model"]["chunk_size"])
    action_dim = int(contract["model"]["action_dim"])
    height = int(contract["cameras"]["top"]["height"])
    width = int(contract["cameras"]["top"]["width"])

    dataset_root = tmp_path / "from_bag"
    convert_bag_to_lerobot(
        FIXTURE_BAG,
        dataset_root,
        contract=contract,
        repo_id="local/e2e_bag",
        task="e2e_test",
    )
    assert dataset_root.is_dir()

    ckpt_dir = tmp_path / "ckpt"
    if DEFAULT_CKPT.is_file():
        checkpoint = DEFAULT_CKPT
    else:
        synth_root = tmp_path / "synth"
        generate_synthetic_dataset(
            synth_root,
            contract=contract,
            episodes=2,
            frames=16,
            seed=0,
            repo_id="local/e2e_fallback_synth",
        )
        checkpoint = train_act(
            contract,
            synth_root,
            ckpt_dir,
            steps=5,
            batch_size=2,
            seed=0,
            device="cpu",
            repo_id="local/e2e_fallback_synth",
        )

    policy = load_policy_from_checkpoint(checkpoint, contract, device="cpu")
    top = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    wrist = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    state = np.zeros(action_dim, dtype=np.float32)
    batch = images_bgr_to_batch(top, wrist, state, device="cpu")
    chunk = predict_chunk(policy, batch)
    assert chunk.shape == (chunk_size, action_dim)
    assert chunk.dtype == np.float32
