"""Wrap a sim-trained ACT policy for real SO-101 follower observations/actions."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from port_pick_align.deploy.conversion import (
    JOINT_NAMES,
    SimToRealConversionConfig,
    apply_max_delta_real,
    extract_real_joint_vector,
    map_real_cameras,
    prepare_policy_images,
    real_action_dict,
    real_joints_to_sim_state,
    sim_action_to_real_joints,
)
from port_pick_align.simulation.policies import blend_temporal_ensemble


class SimTrainedACTOnReal:
    """Bridge real LeRobot observations to a sim-trained ACT checkpoint.

    Flow each control step:
      1. Real obs (deg / gripper 0–100 / RGB cameras) → sim state + images
      2. Policy predicts an action chunk in sim radians
      3. Clamp to contract limits, convert to real units, apply max-delta
      4. Return a LeRobot ``{joint}.pos`` action dict (caller may dry-run)
    """

    def __init__(
        self,
        policy: Any,
        config: SimToRealConversionConfig,
        *,
        device: str = "cpu",
        chunk_size: int = 30,
        n_action_steps: int = 1,
        temporal_ensemble: bool = False,
        temporal_ensemble_coeff: float = 0.01,
    ) -> None:
        if n_action_steps < 1:
            raise ValueError(f"n_action_steps must be >= 1, got {n_action_steps}")
        if chunk_size < 1:
            raise ValueError(f"chunk_size must be >= 1, got {chunk_size}")
        self.policy = policy
        self.config = config
        self.device = device
        self.chunk_size = int(chunk_size)
        self.n_action_steps = min(int(n_action_steps), self.chunk_size)
        self.temporal_ensemble = bool(temporal_ensemble)
        self.temporal_ensemble_coeff = float(temporal_ensemble_coeff)
        self._chunk: np.ndarray | None = None
        self._chunk_i = 0
        self._chunk_history: deque[np.ndarray] = deque(maxlen=max(1, self.chunk_size))
        self._last_real_joints: np.ndarray | None = None

    def reset(self) -> None:
        self._chunk = None
        self._chunk_i = 0
        self._chunk_history.clear()
        self._last_real_joints = None
        reset_fn = getattr(self.policy, "reset", None)
        if callable(reset_fn):
            reset_fn()

    def predict_real_action(
        self,
        observation: Mapping[str, Any],
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """Return ``(action_dict, debug)`` for one control step."""
        import torch

        from port_pick_align.training.infer import predict_chunk

        real_joints = extract_real_joint_vector(observation, self.config.joint_names)
        sim_state = real_joints_to_sim_state(real_joints, self.config)
        real_cams = map_real_cameras(observation, self.config.camera_map)
        chw = prepare_policy_images(real_cams, self.config)
        for required in ("top", "wrist"):
            if required not in chw:
                raise KeyError(
                    f"Sim ACT policy requires camera {required!r} after mapping; "
                    f"got {sorted(chw)}. Real bring-up must provide top+wrist; "
                    "there is no third sim camera."
                )

        need_replan = (
            self._chunk is None or self._chunk_i >= self.n_action_steps or self.temporal_ensemble
        )
        if need_replan:
            batch = {
                "observation.images.top": torch.from_numpy(chw["top"]).unsqueeze(0).to(self.device),
                "observation.images.wrist": torch.from_numpy(chw["wrist"])
                .unsqueeze(0)
                .to(self.device),
                "observation.state": torch.from_numpy(sim_state).unsqueeze(0).to(self.device),
            }
            raw_chunk = predict_chunk(self.policy, batch)
            if self.temporal_ensemble:
                self._chunk_history.append(np.array(raw_chunk, dtype=np.float32, copy=True))
                blended = blend_temporal_ensemble(self._chunk_history, self.temporal_ensemble_coeff)
                chunk = np.array(raw_chunk, dtype=np.float32, copy=True)
                chunk[0] = blended
                self._chunk = chunk
                self._chunk_i = 0
            else:
                self._chunk = np.asarray(raw_chunk, dtype=np.float32)
                self._chunk_i = 0

        assert self._chunk is not None
        sim_action = self._chunk[self._chunk_i]
        self._chunk_i += 1

        target_real = sim_action_to_real_joints(sim_action, self.config)
        reference = self._last_real_joints if self._last_real_joints is not None else real_joints
        safe_real = apply_max_delta_real(target_real, reference, self.config)
        self._last_real_joints = safe_real.copy()

        action = real_action_dict(safe_real)
        debug = {
            "real_joints": real_joints,
            "sim_state": sim_state,
            "sim_action": np.asarray(sim_action, dtype=np.float32),
            "target_real": target_real,
            "safe_real": safe_real,
            "chunk_index": self._chunk_i - 1,
        }
        return action, debug


def format_action_line(
    action: Mapping[str, float],
    joint_names: Sequence[str] = JOINT_NAMES,
) -> str:
    """One-line debug print for dry-run."""
    parts = [f"{name}={action[f'{name}.pos']:+.3f}" for name in joint_names]
    return " ".join(parts)
