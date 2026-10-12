"""ACT training utilities (Task 2)."""

from __future__ import annotations

from typing import Any

__all__ = ["build_act_policy", "run_inference_smoke", "train_act"]


def __getattr__(name: str) -> Any:
    if name == "build_act_policy":
        from pai_final.training.policy import build_act_policy

        return build_act_policy
    if name in {"run_inference_smoke", "train_act"}:
        from pai_final.training import train_act as train_act_module

        return getattr(train_act_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
