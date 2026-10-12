"""Alignment / grasp evaluation stubs (Task 4)."""

from __future__ import annotations

from typing import Any

__all__ = [
    "AlignmentSample",
    "empty_summary",
    "record_sample",
    "samples_to_dicts",
    "summarize",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from port_pick_align.evaluation import eval_alignment

        return getattr(eval_alignment, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
