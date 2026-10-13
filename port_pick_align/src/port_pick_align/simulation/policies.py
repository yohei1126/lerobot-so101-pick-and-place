"""Policy helpers for sim closed-loop eval (mock / checkpoint / scripted)."""

from __future__ import annotations

from collections.abc import Callable
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


class CheckpointPolicy:
    def __init__(self, policy: Any, *, chunk_size: int = 30, device: str = "cpu") -> None:
        self.policy = policy
        self.chunk_size = chunk_size
        self.device = device

    def predict(
        self,
        obs: dict[str, np.ndarray],
        info: dict[str, Any] | None = None,
    ) -> np.ndarray:
        _ = info
        batch = images_bgr_to_batch(obs["top"], obs["wrist"], obs["state"], device=self.device)
        return predict_chunk(self.policy, batch)


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
