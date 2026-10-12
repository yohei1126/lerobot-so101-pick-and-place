"""RobOps data-quality checks for aligned rosbag episodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from port_pick_align.dataset.converter import AlignedEpisode


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    frame_index: int | None = None


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0

    def codes(self) -> set[str]:
        return {issue.code for issue in self.issues}


def validate_episode(episode: AlignedEpisode, contract: dict[str, Any]) -> ValidationReport:
    """Detect sync drift, frame drops, joint-limit violations, and static episodes."""
    quality = contract["quality"]
    sync_tol_ms = float(quality["sync_tolerance_ms"])
    max_gap_ms = float(quality["max_frame_gap_ms"])
    min_var = float(quality["min_joint_variance"])
    joint_names: list[str] = list(contract["robot"]["joint_names"])
    joint_limits = contract["robot"]["joint_limits"]

    report = ValidationReport()
    frames = episode.frames
    if not frames:
        report.issues.append(ValidationIssue(code="EMPTY_EPISODE", message="Episode has no frames"))
        return report

    for idx, frame in enumerate(frames):
        if frame.sync_offset_ms > sync_tol_ms:
            report.issues.append(
                ValidationIssue(
                    code="SYNC_OFFSET",
                    message=(
                        f"Frame {idx}: sync offset {frame.sync_offset_ms:.1f}ms > {sync_tol_ms}ms"
                    ),
                    frame_index=idx,
                )
            )

        for j, name in enumerate(joint_names):
            lo, hi = joint_limits[name]
            value = float(frame.state[j])
            if value < float(lo) or value > float(hi):
                report.issues.append(
                    ValidationIssue(
                        code="JOINT_LIMIT",
                        message=(
                            f"Frame {idx}: joint {name}={value:.4f} outside "
                            f"[{float(lo):.4f}, {float(hi):.4f}]"
                        ),
                        frame_index=idx,
                    )
                )

    for idx in range(1, len(frames)):
        gap_ms = (frames[idx].t_ns - frames[idx - 1].t_ns) / 1e6
        if gap_ms > max_gap_ms:
            report.issues.append(
                ValidationIssue(
                    code="FRAME_DROP",
                    message=(f"Frames {idx - 1}->{idx}: gap {gap_ms:.1f}ms > {max_gap_ms}ms"),
                    frame_index=idx,
                )
            )

    states = np.stack([f.state for f in frames], axis=0)
    mean_var = float(np.mean(np.var(states, axis=0)))
    if mean_var < min_var:
        report.issues.append(
            ValidationIssue(
                code="STATIC_EPISODE",
                message=(f"Mean joint variance {mean_var:.2e} < min_joint_variance {min_var:.2e}"),
            )
        )

    return report
