#!/usr/bin/env python3
"""Cross-check claimed eval aggregates against a metrics.json (JSON wins).

Example (seed=1000 TE verification once the owner provides the file):

  python scripts/verify_eval_metrics.py \\
    --metrics /path/to/eval/best_model_te/te/metrics.json \\
    --expect-seed 1000 --expect-episodes 50 \\
    --expect-align 1.0 --expect-mean-pos-mm 18.28 \\
    --expect-pos-min-mm 14.3 --expect-pos-max-mm 20.0 \\
    --pin docs/results/eval_sim_act_post50_seed1000_te.json

Also pin a full post50 cell:

  python scripts/verify_eval_metrics.py \\
    --metrics eval/best_model_te/te/metrics.json \\
    --pin docs/results/eval_sim_act_post50_best_model_te_te.json
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary(data: dict[str, Any]) -> dict[str, Any]:
    summary = data.get("summary")
    if not isinstance(summary, dict):
        raise TypeError(f"{data.get('status')!r}: missing summary object")
    return summary


def _sample_positions(data: dict[str, Any]) -> list[float]:
    samples = data.get("samples") or []
    out: list[float] = []
    for row in samples:
        if isinstance(row, dict) and "position_error_mm" in row:
            out.append(float(row["position_error_mm"]))
    return out


def _approx_equal(got: float, expect: float, *, tol: float) -> bool:
    return abs(float(got) - float(expect)) <= float(tol)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics", type=Path, required=True, help="Path to metrics.json"
    )
    parser.add_argument("--expect-seed", type=int, default=None)
    parser.add_argument("--expect-episodes", type=int, default=None)
    parser.add_argument("--expect-align", type=float, default=None)
    parser.add_argument("--expect-mean-pos-mm", type=float, default=None)
    parser.add_argument("--expect-mean-yaw-deg", type=float, default=None)
    parser.add_argument("--expect-pos-min-mm", type=float, default=None)
    parser.add_argument("--expect-pos-max-mm", type=float, default=None)
    parser.add_argument(
        "--tol", type=float, default=0.05, help="Absolute tolerance for floats"
    )
    parser.add_argument(
        "--pin",
        type=Path,
        default=None,
        help="If checks pass (or no expects given), copy metrics.json to this path",
    )
    parser.add_argument(
        "--allow-mismatch-pin",
        action="store_true",
        help="Pin even when claimed expects disagree (JSON wins; print DIFF)",
    )
    args = parser.parse_args()

    if not args.metrics.is_file():
        print(f"ERROR: metrics not found: {args.metrics}", file=sys.stderr)
        return 2

    data = _load(args.metrics)
    summary = _summary(data)
    positions = _sample_positions(data)
    diffs: list[str] = []

    def check(label: str, got: Any, expect: Any, *, tol: float | None = None) -> None:
        if expect is None:
            return
        if got is None:
            diffs.append(f"{label}: missing in JSON (claimed {expect})")
            return
        if tol is None:
            if got != expect:
                diffs.append(f"{label}: JSON={got} claimed={expect} → JSON wins")
            return
        if not _approx_equal(float(got), float(expect), tol=tol):
            diffs.append(f"{label}: JSON={got} claimed={expect} → JSON wins")

    check("seed", data.get("seed"), args.expect_seed)
    check("episodes", data.get("episodes"), args.expect_episodes)
    check(
        "align_success_rate",
        summary.get("align_success_rate"),
        args.expect_align,
        tol=args.tol,
    )
    check(
        "mean_position_error_mm",
        summary.get("mean_position_error_mm"),
        args.expect_mean_pos_mm,
        tol=args.tol,
    )
    check(
        "mean_abs_yaw_error_deg",
        summary.get("mean_abs_yaw_error_deg"),
        args.expect_mean_yaw_deg,
        tol=args.tol,
    )

    if positions:
        pos_min = min(positions)
        pos_max = max(positions)
        check("position_error_mm_min", pos_min, args.expect_pos_min_mm, tol=args.tol)
        check("position_error_mm_max", pos_max, args.expect_pos_max_mm, tol=args.tol)
        # Recompute mean from samples when present; JSON summary must match.
        sample_mean = sum(positions) / len(positions)
        summary_mean = float(summary["mean_position_error_mm"])
        if not _approx_equal(sample_mean, summary_mean, tol=max(args.tol, 0.01)):
            diffs.append(
                "mean_position_error_mm: summary disagrees with samples "
                f"(summary={summary_mean}, samples_mean={sample_mean:.4f}) → investigate"
            )
    elif args.expect_pos_min_mm is not None or args.expect_pos_max_mm is not None:
        diffs.append("position range: samples missing in JSON; cannot verify min/max")

    yaw = summary.get("mean_abs_yaw_error_deg")
    print("JSON summary (authoritative when present):")
    print(
        json.dumps(
            {
                "seed": data.get("seed"),
                "episodes": data.get("episodes"),
                "align_success_rate": summary.get("align_success_rate"),
                "mean_position_error_mm": summary.get("mean_position_error_mm"),
                "median_position_error_mm": summary.get("median_position_error_mm"),
                "mean_abs_yaw_error_deg": yaw,
                "n_samples": summary.get("n_samples"),
                "position_error_mm_min": min(positions) if positions else None,
                "position_error_mm_max": max(positions) if positions else None,
            },
            indent=2,
        )
    )

    if diffs:
        print("DIFF vs claimed expects (JSON wins):")
        for line in diffs:
            print(f"  - {line}")
    else:
        expects_given = any(
            v is not None
            for v in (
                args.expect_seed,
                args.expect_episodes,
                args.expect_align,
                args.expect_mean_pos_mm,
                args.expect_mean_yaw_deg,
                args.expect_pos_min_mm,
                args.expect_pos_max_mm,
            )
        )
        if expects_given:
            print("OK: claimed expects match JSON within tolerance.")
        else:
            print("OK: loaded metrics (no expects given).")

    if yaw is None or (isinstance(yaw, float) and math.isnan(yaw)):
        print(
            "NOTE: mean_abs_yaw_error_deg is missing; re-run scripts/run_sim_eval.py "
            "with a current tree so summarize() writes yaw."
        )

    if args.pin is not None:
        if diffs and not args.allow_mismatch_pin:
            print(
                "Refusing to --pin while expects disagree (pass --allow-mismatch-pin)."
            )
            return 1
        args.pin.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.metrics, args.pin)
        print(f"pinned {args.metrics} -> {args.pin}")

    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
