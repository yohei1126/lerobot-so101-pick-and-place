"""Dataset conversion, validation, and synthetic generation helpers."""

from __future__ import annotations

from typing import Any

__all__ = [
    "AlignedEpisode",
    "AlignedFrame",
    "ConversionValidationError",
    "ValidationIssue",
    "ValidationReport",
    "align_episode",
    "convert_bag_to_lerobot",
    "generate_synthetic_dataset",
    "make_dummy_image",
    "read_rosbag",
    "validate_episode",
]


def __getattr__(name: str) -> Any:
    if name in {
        "AlignedEpisode",
        "AlignedFrame",
        "ConversionValidationError",
        "align_episode",
        "convert_bag_to_lerobot",
        "read_rosbag",
    }:
        from port_pick_align.dataset import converter

        return getattr(converter, name)
    if name in {"ValidationIssue", "ValidationReport", "validate_episode"}:
        from port_pick_align.dataset import validator

        return getattr(validator, name)
    if name in {"generate_synthetic_dataset", "make_dummy_image"}:
        from port_pick_align.dataset import synthetic

        return getattr(synthetic, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name}")
