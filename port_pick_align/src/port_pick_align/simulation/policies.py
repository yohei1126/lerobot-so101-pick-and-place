"""Policy helpers for sim closed-loop eval (mock / checkpoint / scripted)."""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from port_pick_align.training.infer import (
    images_bgr_to_batch,
    mock_action_chunk,
    predict_chunk,
)


class SimPolicy(Protocol):
    def predict(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        """Return action chunk ``(chunk_size, action_dim)``."""
        ...


class MockPolicy:
    def __init__(self, chunk_size: int = 30, action_dim: int = 6) -> None:
        self.chunk_size = chunk_size
        self.action_dim = action_dim

    def predict(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        return mock_action_chunk(obs["state"], self.chunk_size, self.action_dim)


class CheckpointPolicy:
    def __init__(self, policy: Any, *, chunk_size: int = 30, device: str = "cpu") -> None:
        self.policy = policy
        self.chunk_size = chunk_size
        self.device = device

    def predict(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        batch = images_bgr_to_batch(obs["top"], obs["wrist"], obs["state"], device=self.device)
        return predict_chunk(self.policy, batch)


class ScriptedPickAlignPolicy:
    """Heuristic open-loop phases for demo videos (not kinematic IK).

    Phases drive joint targets toward a sequence that approaches the table,
    closes the gripper, lifts, and swings toward the target side.
    """

    def __init__(self, chunk_size: int = 30, action_dim: int = 6) -> None:
        self.chunk_size = chunk_size
        self.action_dim = action_dim
        self._t = 0
        # Phase durations (control steps).
        self._phases = (
            ("approach", 40, np.array([0.35, -0.9, 1.1, 0.8, 0.0, 1.2], dtype=np.float32)),
            ("descend", 35, np.array([0.45, -1.1, 1.3, 0.9, 0.0, 1.2], dtype=np.float32)),
            ("grasp", 25, np.array([0.45, -1.1, 1.3, 0.9, 0.0, 0.0], dtype=np.float32)),
            ("lift", 30, np.array([0.2, -0.5, 0.9, 0.5, 0.0, 0.0], dtype=np.float32)),
            ("carry", 40, np.array([-0.15, -0.7, 1.0, 0.6, 0.0, 0.0], dtype=np.float32)),
            ("place", 35, np.array([-0.2, -1.0, 1.2, 0.8, 0.0, 0.0], dtype=np.float32)),
            ("release", 25, np.array([-0.2, -1.0, 1.2, 0.8, 0.0, 1.2], dtype=np.float32)),
            ("retreat", 30, np.array([0.0, -0.6, 0.9, 0.6, 0.0, 1.2], dtype=np.float32)),
        )

    def reset(self) -> None:
        self._t = 0

    def _target_for_step(self) -> np.ndarray:
        elapsed = 0
        current = self._phases[-1][2]
        for _name, duration, target in self._phases:
            if self._t < elapsed + duration:
                return target
            elapsed += duration
            current = target
        return current

    def predict(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        _ = obs
        target = self._target_for_step()
        self._t += 1
        return np.tile(target.reshape(1, -1), (self.chunk_size, 1)).astype(np.float32)
