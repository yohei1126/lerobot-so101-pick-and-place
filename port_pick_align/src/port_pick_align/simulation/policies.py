"""Policy helpers for sim closed-loop eval (mock / checkpoint / scripted)."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import numpy as np

from port_pick_align.training.infer import (
    images_bgr_to_batch,
    mock_action_chunk,
    predict_chunk,
)

IkFn = Callable[[np.ndarray], np.ndarray]


class SimPolicy(Protocol):
    def predict(
        self,
        obs: dict[str, np.ndarray],
        info: dict[str, Any] | None = None,
    ) -> np.ndarray:
        """Return action chunk ``(chunk_size, action_dim)``."""
        ...


class MockPolicy:
    def __init__(self, chunk_size: int = 30, action_dim: int = 6) -> None:
        self.chunk_size = chunk_size
        self.action_dim = action_dim

    def predict(
        self,
        obs: dict[str, np.ndarray],
        info: dict[str, Any] | None = None,
    ) -> np.ndarray:
        _ = info
        return mock_action_chunk(obs["state"], self.chunk_size, self.action_dim)


def blend_temporal_ensemble(chunks: Sequence[np.ndarray], coeff: float) -> np.ndarray:
    """Blend overlapping predictions for the current control step.

    ``chunks`` is ordered oldest to newest. Each array is ``(chunk_size, action_dim)``.
    Weights are ``w_i = exp(-coeff * i)`` where ``i = 0`` is the oldest prediction,
    then normalized to sum to 1. This matches Zhao et al. (2023) and LeRobot
    ``ACTTemporalEnsembler``: a positive coefficient weighs older actions more,
    zero is a uniform mean, and a negative coefficient weighs newer actions more.
    """
    if len(chunks) == 0:
        raise ValueError("chunks must be non-empty")
    n = len(chunks)
    acc: np.ndarray | None = None
    weight_sum = 0.0
    for age, chunk in enumerate(chunks):
        arr = np.asarray(chunk, dtype=np.float64)
        if arr.ndim != 2:
            raise ValueError(f"chunk must be 2D, got shape {arr.shape}")
        offset = n - 1 - age
        if offset < 0 or offset >= arr.shape[0]:
            continue
        weight = math.exp(-float(coeff) * age)
        term = arr[offset] * weight
        acc = term if acc is None else acc + term
        weight_sum += weight
    if acc is None or weight_sum == 0.0:
        raise ValueError("no overlapping action to ensemble")
    return (acc / weight_sum).astype(np.float32)


class CheckpointPolicy:
    def __init__(
        self,
        policy: Any,
        *,
        chunk_size: int = 30,
        device: str = "cpu",
        temporal_ensemble: bool = False,
        temporal_ensemble_coeff: float = 0.01,
    ) -> None:
        self.policy = policy
        self.chunk_size = chunk_size
        self.device = device
        self.temporal_ensemble = bool(temporal_ensemble)
        self.temporal_ensemble_coeff = float(temporal_ensemble_coeff)
        self._chunk_history: deque[np.ndarray] = deque(maxlen=max(1, int(chunk_size)))

    def reset(self) -> None:
        self._chunk_history.clear()

    def blend_chunk(self, chunk: np.ndarray) -> np.ndarray:
        """Return a chunk whose first row is the command to execute.

        With temporal ensembling disabled, the raw chunk is returned unchanged.
        """
        raw = np.asarray(chunk, dtype=np.float32)
        if raw.ndim != 2:
            raise ValueError(f"chunk must be 2D, got shape {raw.shape}")
        if not self.temporal_ensemble:
            return raw
        self._chunk_history.append(np.array(raw, dtype=np.float32, copy=True))
        blended = blend_temporal_ensemble(self._chunk_history, self.temporal_ensemble_coeff)
        out = np.array(raw, dtype=np.float32, copy=True)
        out[0] = blended
        return out

    def predict(
        self,
        obs: dict[str, np.ndarray],
        info: dict[str, Any] | None = None,
    ) -> np.ndarray:
        _ = info
        batch = images_bgr_to_batch(obs["top"], obs["wrist"], obs["state"], device=self.device)
        return self.blend_chunk(predict_chunk(self.policy, batch))


class ScriptedPickAlignPolicy:
    """Closed-loop heuristic: IK waypoints to box/target + sticky-grasp phases.

    IK is solved once per phase (cached) to keep rollouts fast. Gripper open≈1.2,
    closed≈0.0.
    """

    # (name, duration_steps, ref, z_above_table, gripper)
    _PHASES: tuple[tuple[str, int, str, float, float], ...] = (
        ("hover", 35, "box", 0.13, 1.2),
        ("descend", 30, "box", 0.055, 1.2),
        ("grasp", 25, "box", 0.055, 0.0),
        ("lift", 30, "box", 0.15, 0.0),
        ("carry", 45, "target", 0.15, 0.0),
        ("place", 35, "target", 0.06, 0.0),
        ("release", 25, "target", 0.06, 1.2),
        # Retreat toward home-ish XY so the arm does not shove the placed box.
        ("retreat", 35, "home", 0.16, 1.2),
    )

    def __init__(self, chunk_size: int = 30, action_dim: int = 6) -> None:
        self.chunk_size = chunk_size
        self.action_dim = action_dim
        self._phase_idx = 0
        self._phase_t = 0
        self._ik_fn: IkFn | None = None
        self._cached_q: np.ndarray | None = None
        self._cached_phase: int = -1

    @classmethod
    def horizon_steps(cls) -> int:
        """Control steps covering every scripted phase once."""
        return sum(phase[1] for phase in cls._PHASES)

    def set_ik(self, ik_fn: IkFn) -> None:
        self._ik_fn = ik_fn

    def reset(self) -> None:
        self._phase_idx = 0
        self._phase_t = 0
        self._cached_q = None
        self._cached_phase = -1

    def _xy_for_ref(self, ref: str, info: dict[str, Any]) -> np.ndarray:
        if ref == "box":
            return np.asarray(info["box_xy"], dtype=np.float64).reshape(2)
        if ref == "home":
            return np.array([0.18, 0.0], dtype=np.float64)
        return np.asarray(info["target_xy"], dtype=np.float64).reshape(2)

    def _joint_target(
        self,
        obs: dict[str, np.ndarray],
        info: dict[str, Any],
        ref: str,
        z_off: float,
        grip: float,
    ) -> np.ndarray:
        if self._cached_q is not None and self._cached_phase == self._phase_idx:
            q = self._cached_q.copy()
            q[5] = float(grip)
            return q

        table_z = float(info.get("table_z", 0.42))
        xy = self._xy_for_ref(ref, info)
        target_xyz = np.array([xy[0], xy[1], table_z + z_off], dtype=np.float64)
        if self._ik_fn is not None:
            q = np.asarray(self._ik_fn(target_xyz), dtype=np.float32).reshape(6).copy()
        else:
            q = np.asarray(obs["state"], dtype=np.float32).reshape(6).copy()
        q[5] = float(grip)
        self._cached_q = q.copy()
        self._cached_phase = self._phase_idx
        return q

    def predict(
        self,
        obs: dict[str, np.ndarray],
        info: dict[str, Any] | None = None,
    ) -> np.ndarray:
        info = info or {}
        phase = self._PHASES[min(self._phase_idx, len(self._PHASES) - 1)]
        _name, duration, ref, z_off, grip = phase
        if info:
            q = self._joint_target(obs, info, ref, z_off, grip)
        else:
            q = np.asarray(obs["state"], dtype=np.float32).reshape(6).copy()
            q[5] = float(grip)

        self._phase_t += 1
        if self._phase_t >= duration and self._phase_idx < len(self._PHASES) - 1:
            self._phase_idx += 1
            self._phase_t = 0
            self._cached_q = None
            self._cached_phase = -1

        return np.tile(q.reshape(1, -1), (self.chunk_size, 1)).astype(np.float32)
