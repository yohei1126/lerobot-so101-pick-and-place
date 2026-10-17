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
# grasp xyz, carry xyz, place xyz → joint targets for those three poses
TransportPlanFn = Callable[
    [np.ndarray, np.ndarray, np.ndarray],
    tuple[np.ndarray, np.ndarray, np.ndarray],
]
# carry xyz, place xyz → joint targets after the grasp has latched
TransportRetargetFn = Callable[[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]
# name, duration, ref, z above table, gripper, joint source
# source: ik (solve, keep IK wrist), pregrasp (IK + grasp wrist),
# grasp / carry / place (planned joint vector)
PhaseSpec = tuple[str, int, str, float, float, str]


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

    The low pad pose is mostly an open hold. Place and release share the same arm
    target, so a memoryless L1 policy predicts the conditional mean of the gripper
    channel. With a long closed place and a short release that mean sits near 0.5,
    under the 0.90 open threshold, and the box stays grasped. A longer stationary
    open makes the settled pad action unambiguously open. Raising the gripper loss
    weight does not change that mean, and lowering the threshold would also open
    on smeared carry commands.

    Late carry also needs a long closed approach before that open. With
    ``n_action_steps=30``, a short closed place lets one chunk open while the box
    is still 11–14 cm short of the pad. An approach longer than the chunk keeps
    those predictions closed until a replan over the pad. The approach uses IK at
    an intermediate height so the arm keeps descending instead of freezing on the
    high carry joints.

    Wrist targets are planned once, from the home posture, and then commanded as
    those joint vectors. A later IK seeded from the carried posture would not
    match the orientation the search measured. The grasp vector is held until the
    gripper closes. Carry and place share one wrist so the box yaws toward the
    pad during transport.
    """

    # Durations sum to the closed-loop horizon (260). Approach is longer than the
    # ACT chunk so closed transport fills a full chunk before the open dwell.
    _PHASES: tuple[PhaseSpec, ...] = (
        ("hover", 28, "box", 0.13, 1.2, "pregrasp"),
        ("descend", 26, "box", 0.055, 1.2, "grasp"),
        ("grasp", 24, "box", 0.055, 0.0, "grasp"),
        ("lift", 22, "box", 0.15, 0.0, "pregrasp_transport"),
        ("carry", 45, "target", 0.15, 0.0, "carry"),
        # Closed descend over the pad path (IK + carry wrist). z_off > 0.08 so
        # pad_gripper_steps does not count these as settled pad labels.
        ("approach", 32, "target", 0.10, 0.0, "pregrasp_transport"),
        ("place", 8, "target", 0.06, 0.0, "place"),
        ("release", 48, "target", 0.06, 1.2, "place"),
        # Retreat toward home-ish XY so the arm does not shove the placed box.
        ("retreat", 27, "home", 0.16, 1.2, "pregrasp_transport"),
    )

    def __init__(self, chunk_size: int = 30, action_dim: int = 6) -> None:
        self.chunk_size = chunk_size
        self.action_dim = action_dim
        self._phase_idx = 0
        self._phase_t = 0
        self._ik_fn: IkFn | None = None
        self._transport_plan_fn: TransportPlanFn | None = None
        self._transport_retarget_fn: TransportRetargetFn | None = None
        self._transport_plan: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        self._transport_retargeted = False
        self._cached_q: np.ndarray | None = None
        self._cached_phase: int = -1

    @classmethod
    def horizon_steps(cls) -> int:
        """Control steps covering every scripted phase once."""
        return sum(phase[1] for phase in cls._PHASES)

    @classmethod
    def pad_gripper_steps(cls) -> tuple[int, int]:
        """Return ``(closed_steps, open_steps)`` commanded at the low pad pose.

        Both counts use the place height. Open steps must dominate so the
        conditional gripper target at that pose clears the release threshold.
        """
        closed = 0
        opened = 0
        for _name, duration, ref, z_off, grip, _wrist in cls._PHASES:
            if ref != "target" or z_off > 0.08:
                continue
            if grip >= 0.9:
                opened += int(duration)
            elif grip <= 0.45:
                closed += int(duration)
        return closed, opened

    def set_ik(self, ik_fn: IkFn) -> None:
        self._ik_fn = ik_fn

    def set_transport_plan(self, transport_plan_fn: TransportPlanFn | None) -> None:
        """Plan grasp/carry/place joint targets, including yaw-aligned wrists."""
        self._transport_plan_fn = transport_plan_fn

    def set_transport_retarget(self, transport_retarget_fn: TransportRetargetFn | None) -> None:
        """Re-aim carry and place once the sticky grasp has latched."""
        self._transport_retarget_fn = transport_retarget_fn

    def reset(self) -> None:
        self._phase_idx = 0
        self._phase_t = 0
        self._transport_plan = None
        self._transport_retargeted = False
        self._cached_q = None
        self._cached_phase = -1

    def _phase_z(self, name: str) -> float:
        for phase_name, _duration, _ref, z_off, _grip, _wrist in self._PHASES:
            if phase_name == name:
                return float(z_off)
        raise KeyError(name)

    def _ensure_transport_plan(self, info: dict[str, Any]) -> None:
        if self._transport_plan is not None or self._transport_plan_fn is None:
            return
        if "box_xy" not in info or "target_xy" not in info:
            return
        table_z = float(info.get("table_z", 0.42))
        box = self._xy_for_ref("box", info)
        target = self._xy_for_ref("target", info)
        grasp_xyz = np.array([box[0], box[1], table_z + self._phase_z("grasp")], dtype=np.float64)
        carry_xyz = np.array(
            [target[0], target[1], table_z + self._phase_z("carry")], dtype=np.float64
        )
        place_xyz = np.array(
            [target[0], target[1], table_z + self._phase_z("place")], dtype=np.float64
        )
        grasp_q, carry_q, place_q = self._transport_plan_fn(grasp_xyz, carry_xyz, place_xyz)
        self._transport_plan = (
            np.asarray(grasp_q, dtype=np.float32).reshape(6).copy(),
            np.asarray(carry_q, dtype=np.float32).reshape(6).copy(),
            np.asarray(place_q, dtype=np.float32).reshape(6).copy(),
        )

    def _maybe_retarget_transport(self, info: dict[str, Any]) -> None:
        if (
            self._transport_retargeted
            or self._transport_plan is None
            or self._transport_retarget_fn is None
            or not info.get("grasping")
        ):
            return
        table_z = float(info.get("table_z", 0.42))
        target = self._xy_for_ref("target", info)
        carry_xyz = np.array(
            [target[0], target[1], table_z + self._phase_z("carry")], dtype=np.float64
        )
        place_xyz = np.array(
            [target[0], target[1], table_z + self._phase_z("place")], dtype=np.float64
        )
        carry_q, place_q = self._transport_retarget_fn(carry_xyz, place_xyz)
        grasp_q = self._transport_plan[0]
        self._transport_plan = (
            grasp_q,
            np.asarray(carry_q, dtype=np.float32).reshape(6).copy(),
            np.asarray(place_q, dtype=np.float32).reshape(6).copy(),
        )
        self._transport_retargeted = True
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
        *,
        joint_source: str,
    ) -> np.ndarray:
        if self._cached_q is not None and self._cached_phase == self._phase_idx:
            q = self._cached_q.copy()
            q[5] = float(grip)
            return q

        planned = self._transport_plan
        if planned is not None and joint_source in {"grasp", "carry", "place"}:
            source_index = {"grasp": 0, "carry": 1, "place": 2}[joint_source]
            q = planned[source_index].copy()
        else:
            table_z = float(info.get("table_z", 0.42))
            xy = self._xy_for_ref(ref, info)
            target_xyz = np.array([xy[0], xy[1], table_z + z_off], dtype=np.float64)
            if self._ik_fn is not None:
                q = np.asarray(self._ik_fn(target_xyz), dtype=np.float32).reshape(6).copy()
            else:
                q = np.asarray(obs["state"], dtype=np.float32).reshape(6).copy()
            if planned is not None and joint_source == "pregrasp":
                q[4] = planned[0][4]
            elif planned is not None and joint_source == "pregrasp_transport":
                q[4] = planned[1][4]
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
        self._ensure_transport_plan(info)
        self._maybe_retarget_transport(info)
        phase = self._PHASES[min(self._phase_idx, len(self._PHASES) - 1)]
        _name, duration, ref, z_off, grip, joint_source = phase
        if info:
            q = self._joint_target(obs, info, ref, z_off, grip, joint_source=joint_source)
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
