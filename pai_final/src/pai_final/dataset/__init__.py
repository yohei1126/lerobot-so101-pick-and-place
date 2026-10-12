"""Dataset conversion and synthetic generation helpers."""

from __future__ import annotations

from typing import Any

__all__ = ["generate_synthetic_dataset", "make_dummy_image"]


def __getattr__(name: str) -> Any:
    if name in {"generate_synthetic_dataset", "make_dummy_image"}:
        from pai_final.dataset import synthetic

        return getattr(synthetic, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
