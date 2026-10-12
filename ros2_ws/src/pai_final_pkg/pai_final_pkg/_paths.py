"""Resolve repository root for contract / checkpoint paths."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    candidates = [
        Path("/workspace"),
        Path(__file__).resolve().parents[4],
        Path.cwd(),
    ]
    for candidate in candidates:
        if (candidate / "configs" / "contract.yaml").is_file():
            return candidate
    return Path(__file__).resolve().parents[4]
