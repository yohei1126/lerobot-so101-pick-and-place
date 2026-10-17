"""Regression: scripts/run_pipeline.sh must stay macOS /bin/bash 3.2 compatible."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE = REPO_ROOT / "scripts" / "run_pipeline.sh"

# Bash 4+ builtins / syntax that macOS ships without (Apple bash 3.2).
_BASH4_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mapfile", re.compile(r"\bmapfile\b")),
    ("readarray", re.compile(r"\breadarray\b")),
    ("associative array", re.compile(r"\bdeclare\s+-A\b")),
    ("lowercase ${var,,}", re.compile(r"\$\{[^}]+,,\}")),
    ("uppercase ${var^^}", re.compile(r"\$\{[^}]+\^\^\}")),
    ("nameref declare -n", re.compile(r"\bdeclare\s+-n\b")),
)


@pytest.mark.unit
def test_run_pipeline_avoids_bash4_only_features() -> None:
    text = PIPELINE.read_text(encoding="utf-8")
    # Strip comments so documented mentions do not trip the guard.
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    body = "\n".join(lines)
    offenders = [name for name, pat in _BASH4_PATTERNS if pat.search(body)]
    assert not offenders, f"bash 4+ features in {PIPELINE.name}: {offenders}"


@pytest.mark.unit
def test_run_pipeline_posts_failure_comment_when_pr_set() -> None:
    text = PIPELINE.read_text(encoding="utf-8")
    assert "post_pr_failure_comment" in text
    assert "Pipeline failed" in text
    # fail() must invoke the helper before exiting.
    fail_fn = text[text.index("fail()") : text.index("on_fail()")]
    assert "post_pr_failure_comment" in fail_fn


@pytest.mark.unit
def test_run_pipeline_exposes_min_steps_and_patience() -> None:
    text = PIPELINE.read_text(encoding="utf-8")
    assert "--min-steps)" in text
    assert "--early-stop-patience)" in text
    assert 'train_cmd+=(--min-steps "$MIN_STEPS")' in text
    assert 'train_cmd+=(--early-stop-patience "$EARLY_STOP_PATIENCE")' in text
