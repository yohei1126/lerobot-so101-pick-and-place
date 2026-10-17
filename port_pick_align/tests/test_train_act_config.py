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

from port_pick_align.contract import load_contract  # noqa: E402
from port_pick_align.simulation.policies import ScriptedPickAlignPolicy  # noqa: E402
from port_pick_align.training.policy import build_act_policy  # noqa: E402
from port_pick_align.training.train_act import (  # noqa: E402
    COSINE_ETA_MIN_RATIO,
    SIM_DEFAULT_CHECKPOINT_INTERVAL,
    SIM_DEFAULT_CLOSED_LOOP_VAL_MAX_STEPS,
    SIM_DEFAULT_EARLY_STOP_PATIENCE,
    action_gripper_value,
    apply_preset_defaults,
    closed_loop_selection_improves,
    compute_act_train_loss,
    evaluate_val_l1,
    find_gripper_transition_indices,
    oversample_indices_near_transitions,
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
    assert args.gripper_loss_weight is None
    assert args.transition_oversample_factor is None
    assert args.closed_loop_val_interval is None
    assert args.selection_metric is None


@pytest.mark.unit
def test_sim_preset_enables_grasp_transition_defaults() -> None:
    args = parse_args(["--preset", "sim"])
    apply_preset_defaults(args)
    assert args.gripper_loss_weight == pytest.approx(5.0)
    assert args.transition_oversample_window == 15
    assert args.transition_oversample_factor == 5
    assert args.closed_loop_val_interval == 100
    assert args.closed_loop_val_episodes == 10
    assert args.closed_loop_te_episodes == 10
    assert args.closed_loop_n_action_steps == 30
    assert args.closed_loop_val_max_steps == 260
    assert args.selection_metric == "closed_loop_align"
    assert args.arch == "full"
    assert args.checkpoint_interval == SIM_DEFAULT_CHECKPOINT_INTERVAL
    assert args.early_stop_patience == SIM_DEFAULT_EARLY_STOP_PATIENCE
    assert COSINE_ETA_MIN_RATIO == pytest.approx(0.1)


@pytest.mark.unit
def test_sim_preset_can_disable_temporal_ensemble_metric() -> None:
    args = parse_args(["--preset", "sim", "--closed-loop-te-episodes", "0"])
    apply_preset_defaults(args)
    assert args.closed_loop_val_episodes == 10
    assert args.closed_loop_te_episodes == 0
    assert args.closed_loop_n_action_steps == 30


@pytest.mark.unit
def test_sim_preset_can_disable_early_stop_and_periodic_checkpoints() -> None:
    args = parse_args(
        ["--preset", "sim", "--checkpoint-interval", "0", "--early-stop-patience", "0"]
    )
    apply_preset_defaults(args)
    assert args.checkpoint_interval == 0
    assert args.early_stop_patience == 0


@pytest.mark.unit
def test_non_sim_preset_keeps_grasp_helpers_off() -> None:
    args = parse_args([])
    apply_preset_defaults(args)
    assert args.gripper_loss_weight == pytest.approx(1.0)
    assert args.transition_oversample_window == 0
    assert args.transition_oversample_factor == 1
    assert args.closed_loop_val_interval == 0
    assert args.closed_loop_te_episodes == 0
    assert args.checkpoint_interval == 0
    assert args.early_stop_patience == 0


@pytest.mark.unit
def test_action_gripper_value_reads_chunk_step0() -> None:
    chunk = torch.zeros(30, 6)
    chunk[0, 5] = 1.2
    chunk[10, 5] = 0.0
    assert action_gripper_value(chunk) == pytest.approx(1.2)
    assert action_gripper_value(chunk[0]) == pytest.approx(1.2)


@pytest.mark.unit
def test_find_and_oversample_gripper_transitions() -> None:
    class _GripDataset(torch.utils.data.Dataset):
        def __init__(self) -> None:
            # Episode 0: open then close at index 3. Episode 1: always open.
            self._grips = [1.2, 1.2, 1.2, 0.0, 0.0, 1.2, 1.2, 1.2]

        def __len__(self) -> int:
            return len(self._grips)

        def __getitem__(self, index: int) -> dict[str, Any]:
            action = torch.zeros(30, 6)
            action[:, 5] = float(self._grips[index])
            return {
                "episode_index": 0 if index < 5 else 1,
                "action": action,
            }

    dataset = _GripDataset()
    indices = list(range(len(dataset)))
    transitions = find_gripper_transition_indices(dataset, indices)
    assert transitions == [3]
    expanded = oversample_indices_near_transitions(
        indices, transitions, dataset, window=1, factor=3
    )
    # base 8 + 2 extra copies of {2,3,4}
    assert len(expanded) == 8 + 2 * 3
    assert expanded.count(3) == 3
    unchanged = oversample_indices_near_transitions(
        indices, transitions, dataset, window=1, factor=1
    )
    assert unchanged == indices


@pytest.mark.unit
def test_find_release_transition_and_both() -> None:
    class _GripDataset(torch.utils.data.Dataset):
        def __init__(self) -> None:
            # Close at index 1, release at index 3, all one episode.
            self._grips = [1.2, 0.0, 0.0, 1.2, 1.2]

        def __len__(self) -> int:
            return len(self._grips)

        def __getitem__(self, index: int) -> dict[str, Any]:
            action = torch.zeros(6)
            action[5] = float(self._grips[index])
            return {"episode_index": 0, "action": action}

    dataset = _GripDataset()
    indices = list(range(len(dataset)))
    assert find_gripper_transition_indices(dataset, indices, direction="open_to_close") == [1]
    assert find_gripper_transition_indices(dataset, indices, direction="close_to_open") == [3]
    assert find_gripper_transition_indices(dataset, indices, direction="both") == [1, 3]
    with pytest.raises(ValueError, match="direction"):
        find_gripper_transition_indices(dataset, indices, direction="sideways")


@pytest.mark.unit
def test_closed_loop_align_tie_breaks_on_position_error() -> None:
    assert closed_loop_selection_improves(0.0, 150.0, None, None)
    assert closed_loop_selection_improves(0.5, 80.0, 0.0, 10.0)
    assert not closed_loop_selection_improves(0.0, 200.0, 0.5, 80.0)
    assert closed_loop_selection_improves(0.5, 40.0, 0.5, 80.0)
    assert not closed_loop_selection_improves(0.5, 80.0, 0.5, 40.0)
    assert not closed_loop_selection_improves(0.5, 40.0, 0.5, 40.0)


@pytest.mark.unit
def test_closed_loop_val_horizon_matches_scripted_demo() -> None:
    assert SIM_DEFAULT_CLOSED_LOOP_VAL_MAX_STEPS == ScriptedPickAlignPolicy.horizon_steps()
    assert SIM_DEFAULT_CLOSED_LOOP_VAL_MAX_STEPS == 260


@pytest.mark.unit
def test_pad_release_hold_dominates_closed_place() -> None:
    """Settled pad actions must be open, or L1 regresses below the release threshold."""
    closed, opened = ScriptedPickAlignPolicy.pad_gripper_steps()
    assert closed > 0
    assert opened >= 4 * closed
    assert ScriptedPickAlignPolicy.horizon_steps() == 260


@pytest.mark.unit
def test_closed_approach_covers_full_action_chunk() -> None:
    """Closed approach+place must exceed n_action_steps so chunks stay closed until replan."""
    closed_before_open = 0
    for name, duration, ref, z_off, grip, _wrist in ScriptedPickAlignPolicy._PHASES:
        if name == "release":
            break
        if ref == "target" and grip <= 0.45:
            closed_before_open += int(duration)
        _ = z_off
    # One full chunk (30) plus margin so a mid-approach replan stays closed.
    assert closed_before_open > 45
    approach = next(p for p in ScriptedPickAlignPolicy._PHASES if p[0] == "approach")
    assert approach[1] >= 30
    assert approach[4] <= 0.45


@pytest.mark.unit
def test_early_stop_resets_when_te_or_chunk_improves() -> None:
    """Patience must clear on TE improvement even if chunk30 selection is flat."""
    # Mirrors train_act: selection improve OR te_improved → reset counter.
    chunk_improved = False
    te_improved = closed_loop_selection_improves(0.9, 5.0, 0.0, 200.0)
    pulses = 3
    if chunk_improved or te_improved:
        pulses = 0
    assert te_improved
    assert pulses == 0
    te_flat = not closed_loop_selection_improves(0.5, 80.0, 0.9, 5.0)
    chunk_flat = not closed_loop_selection_improves(0.0, 160.0, 0.0, 150.0)
    assert te_flat and chunk_flat


@pytest.mark.unit
def test_build_act_policy_moves_weights_to_requested_device() -> None:
    contract = load_contract()
    policy = build_act_policy(contract, device="cpu", arch="smoke")
    assert next(policy.parameters()).device.type == "cpu"


@pytest.mark.unit
def test_compute_act_train_loss_weights_gripper() -> None:
    class _FakeConfig:
        image_features = None
        use_vae = False
        kl_weight = 1.0

    class _FakeModel(torch.nn.Module):
        def forward(self, batch: dict[str, Any]) -> tuple[torch.Tensor, tuple[None, None]]:
            # Predict zeros; GT has error 1.0 on every dim.
            target = batch["action"]
            return torch.zeros_like(target), (None, None)

    class _FakePolicy:
        def __init__(self) -> None:
            self.config = _FakeConfig()
            self.model = _FakeModel()

    batch = {
        "action": torch.ones(2, 4, 6),
        "action_is_pad": torch.zeros(2, 4, dtype=torch.bool),
    }
    policy = _FakePolicy()
    loss_1, dict_1 = compute_act_train_loss(policy, batch, gripper_loss_weight=1.0)
    loss_5, dict_5 = compute_act_train_loss(policy, batch, gripper_loss_weight=5.0)
    assert dict_1["l1_loss"] == pytest.approx(1.0)
    assert dict_5["l1_loss"] == pytest.approx(1.0)
    assert float(loss_5.detach()) > float(loss_1.detach())
    # Mean over 6 dims with gripper×5 → (5+1+1+1+1+1)/6 = 10/6
    assert float(loss_5.detach()) == pytest.approx(10.0 / 6.0)


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
