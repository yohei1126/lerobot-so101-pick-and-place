"""Smoke tests for scripts/generate_report_figures.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_report_figures.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "report_figures"


@pytest.mark.unit
def test_generate_report_figures_from_fixtures(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    out = tmp_path / "figures"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--use-fixtures",
        "--skip-video",
        "--output-dir",
        str(out),
        "--strict",
    ]
    subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))
    assert (out / "training_loss_curve.png").is_file()
    assert (out / "position_error_histogram.png").is_file()
    assert (out / "initial_box_xy_scatter.png").is_file()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["written"]) >= 3
    assert FIXTURES.joinpath("training_metrics.json").is_file()
