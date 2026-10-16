"""Oracle sim-dataset collection: validator gates and a short MuJoCo smoke."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from port_pick_align.contract import load_contract
from port_pick_align.dataset.sim_collect import (
    CollectedFrame,
    bgr_hwc_to_rgb,
    validate_collected_frames,
)
from port_pick_align.simulation.policies import ScriptedPickAlignPolicy


def _frame(index: int, *, action: np.ndarray | None = None) -> CollectedFrame:
    state = np.array(
        [0.15 * np.sin(index / 3.0), -0.4 + 0.01 * index, 0.4, 0.2, 0.05 * index, 0.8],
        dtype=np.float32,
    )
    if action is None:
        action = state.copy()
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    image[..., 0] = np.uint8(index * 3)
    image[..., 1] = 10
    image[..., 2] = 20
    return CollectedFrame(
        top_bgr=image,
        wrist_bgr=image.copy(),
        state=state,
        action=np.asarray(action, dtype=np.float32),
    )


@pytest.mark.unit
def test_scripted_horizon_matches_phase_table() -> None:
    assert ScriptedPickAlignPolicy.horizon_steps() == 260
    closed, opened = ScriptedPickAlignPolicy.pad_gripper_steps()
    assert opened > closed


@pytest.mark.unit
def test_bgr_hwc_to_rgb_swaps_channels() -> None:
    bgr = np.zeros((2, 2, 3), dtype=np.uint8)
    bgr[..., 0] = 1
    bgr[..., 1] = 2
    bgr[..., 2] = 3
    rgb = bgr_hwc_to_rgb(bgr)
    assert rgb.shape == (2, 2, 3)
    assert int(rgb[0, 0, 0]) == 3
    assert int(rgb[0, 0, 2]) == 1
    assert rgb.flags["C_CONTIGUOUS"]


@pytest.mark.unit
def test_validate_collected_frames_passes_and_flags_limits() -> None:
    contract = load_contract()
    frames = [_frame(i) for i in range(16)]
    report = validate_collected_frames(frames, contract, fps=30)
    assert report.ok, [issue.message for issue in report.issues]

    bad_action = frames[-1].action.copy()
    bad_action[0] = 9.0
    frames[-1] = _frame(15, action=bad_action)
    rejected = validate_collected_frames(frames, contract, fps=30)
    assert not rejected.ok
    assert "JOINT_LIMIT" in rejected.codes()

    dropped = validate_collected_frames(frames, contract, fps=1)
    assert "FRAME_DROP" in dropped.codes()


@pytest.mark.simulation
@pytest.mark.unit
def test_collect_sim_dataset_smoke(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    pytest.importorskip("lerobot")
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    from port_pick_align.dataset.sim_collect import collect_sim_dataset

    contract = load_contract()
    root = tmp_path / "lerobot"
    report_path = tmp_path / "validation_report.json"
    written = collect_sim_dataset(
        root,
        contract=contract,
        episodes=1,
        max_steps=20,
        seed=0,
        repo_id="local/test_sim_expert",
        require_success=False,
        randomize_box=True,
        render_height=48,
        render_width=64,
        report_path=report_path,
        image_writer_threads=0,
    )
    assert written == root
    dataset = LeRobotDataset(repo_id="local/test_sim_expert", root=root)
    assert dataset.num_episodes == 1
    assert dataset.num_frames == 20
    features = dataset.meta.features
    assert features["observation.images.top"]["shape"] == (48, 64, 3)
    assert features["observation.images.wrist"]["shape"] == (48, 64, 3)
    assert features["observation.state"]["shape"] == (6,)
    assert features["action"]["shape"] == (6,)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["result"] == "PASS"
    assert payload["official_collection"] is False
    assert payload["acquired_color"] == "bgr"
    assert payload["stored_color"] == "rgb"
    assert payload["episodes_accepted"] == 1
    assert payload["attempts"][0]["validation_ok"] is True
