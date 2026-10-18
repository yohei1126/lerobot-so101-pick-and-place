#!/usr/bin/env python3
"""Regenerate report figures into docs/figures/ (single entry point).

Produces:
  1. training_loss_curve.png       — from training_metrics.json history
  2. position_error_histogram.png  — TE vs chunk30 position_error_mm
  3. initial_box_xy_scatter.png    — initial_box_xy colored by success / error
  4. sim_rollout_representative.mp4 — one closed-loop episode video

Missing inputs are skipped with a clear message (no invented numbers).
Pass local Mac paths when artifacts are not in the repo.

Examples:
  # All-in-one (skip missing):
  python scripts/generate_report_figures.py

  # Owner Mac (post50):
  python scripts/generate_report_figures.py \\
    --training-metrics checkpoints/sim_act_post50/training_metrics.json \\
    --te-metrics eval/best_model_te/te/metrics.json \\
    --chunk30-metrics eval/best_model/chunk30/metrics.json \\
    --checkpoint checkpoints/sim_act_post50/best_model_te.pt \\
    --video-policy checkpoint --device mps --temporal-ensemble

  # Fixture smoke (CI / no Mac artifacts):
  python scripts/generate_report_figures.py --use-fixtures
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "docs" / "figures"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "report_figures"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            'matplotlib is required. Install with: pip install -e "port_pick_align/[report]"'
        ) from exc
    return plt


def _samples(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("samples")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def plot_training_loss(metrics_path: Path, out_path: Path) -> None:
    plt = _require_matplotlib()
    data = _load_json(metrics_path)
    history = data.get("history")
    if not isinstance(history, list) or not history:
        raise ValueError(f"no history[] in {metrics_path}")

    steps: list[int] = []
    train_loss: list[float] = []
    val_l1: list[float] = []
    for row in history:
        if not isinstance(row, dict) or "step" not in row:
            continue
        steps.append(int(row["step"]))
        if row.get("train_loss") is not None:
            train_loss.append(float(row["train_loss"]))
        else:
            train_loss.append(float("nan"))
        if row.get("val_l1") is not None:
            val_l1.append(float(row["val_l1"]))
        else:
            val_l1.append(float("nan"))

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.plot(steps, train_loss, color="#1f4e79", linewidth=1.6, label="train_loss")
    if any(v == v for v in val_l1):  # not all NaN
        ax.plot(steps, val_l1, color="#c45c26", linewidth=1.4, label="val_l1")
    ax.set_xlabel("step")
    ax.set_ylabel("loss")
    ax.set_title("ACT training loss")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def plot_position_error_histogram(
    te_path: Path,
    chunk30_path: Path,
    out_path: Path,
) -> None:
    plt = _require_matplotlib()
    te = _samples(_load_json(te_path))
    chunk = _samples(_load_json(chunk30_path))
    te_pos = [float(s["position_error_mm"]) for s in te if "position_error_mm" in s]
    chunk_pos = [float(s["position_error_mm"]) for s in chunk if "position_error_mm" in s]
    if not te_pos and not chunk_pos:
        raise ValueError(
            "both metrics files lack samples[].position_error_mm "
            f"(te={te_path}, chunk30={chunk30_path})"
        )

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    bins = 12
    if te_pos:
        ax.hist(
            te_pos,
            bins=bins,
            alpha=0.65,
            color="#1f4e79",
            label=f"TE (n={len(te_pos)})",
        )
    if chunk_pos:
        ax.hist(
            chunk_pos,
            bins=bins,
            alpha=0.55,
            color="#c45c26",
            label=f"chunk30 (n={len(chunk_pos)})",
        )
    ax.axvline(25.0, color="#666666", linestyle="--", linewidth=1.0, label="DoD 25 mm")
    ax.set_xlabel("position error (mm)")
    ax.set_ylabel("count")
    ax.set_title("Position error: TE vs chunk30")
    ax.legend(loc="upper right")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def plot_initial_box_xy_scatter(metrics_path: Path, out_path: Path) -> None:
    plt = _require_matplotlib()
    samples = _samples(_load_json(metrics_path))
    xs: list[float] = []
    ys: list[float] = []
    colors: list[float] = []
    success_flags: list[bool] = []
    for row in samples:
        xy = row.get("initial_box_xy")
        if not (isinstance(xy, (list, tuple)) and len(xy) >= 2):
            continue
        xs.append(float(xy[0]))
        ys.append(float(xy[1]))
        err = float(row.get("position_error_mm", float("nan")))
        colors.append(err)
        align = row.get("align_success")
        if align is None:
            # Fall back: grasp + error within DoD-ish if align flag absent.
            align = bool(row.get("grasp_success", False)) and err <= 25.0
            if "yaw_error_deg" in row or "yaw_err_deg" in row:
                yaw = abs(float(row.get("yaw_error_deg", row.get("yaw_err_deg", 0.0))))
                align = align and yaw <= 15.0
        success_flags.append(bool(align))

    if not xs:
        raise ValueError(
            f"no samples with initial_box_xy in {metrics_path} (need PR #52-style metrics)"
        )

    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    ok_x = [x for x, ok in zip(xs, success_flags, strict=True) if ok]
    ok_y = [y for y, ok in zip(ys, success_flags, strict=True) if ok]
    ok_c = [c for c, ok in zip(colors, success_flags, strict=True) if ok]
    bad_x = [x for x, ok in zip(xs, success_flags, strict=True) if not ok]
    bad_y = [y for y, ok in zip(ys, success_flags, strict=True) if not ok]
    bad_c = [c for c, ok in zip(colors, success_flags, strict=True) if not ok]

    sc = None
    if ok_x:
        sc = ax.scatter(
            ok_x,
            ok_y,
            c=ok_c,
            cmap="viridis",
            marker="o",
            s=48,
            edgecolors="#1b1b1b",
            linewidths=0.4,
            label=f"align OK (n={len(ok_x)})",
        )
    if bad_x:
        sc = ax.scatter(
            bad_x,
            bad_y,
            c=bad_c,
            cmap="viridis",
            marker="x",
            s=56,
            linewidths=1.2,
            label=f"align fail (n={len(bad_x)})",
        )
    if sc is not None:
        cbar = fig.colorbar(sc, ax=ax)
        cbar.set_label("final position error (mm)")
    ax.set_xlabel("initial box x (m)")
    ax.set_ylabel("initial box y (m)")
    ax.set_title("Initial box XY (color = final pos error)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def write_rollout_video(
    *,
    out_path: Path,
    policy: str,
    checkpoint: Path | None,
    device: str,
    temporal_ensemble: bool,
    seed: int,
    max_steps: int,
    video_mode: str,
) -> None:
    """Delegate to run_sim_eval.py for one episode with video."""
    out_dir = out_path.parent / "_rollout_tmp"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_sim_eval.py"),
        "--policy",
        policy,
        "--episodes",
        "1",
        "--max-steps",
        str(max_steps),
        "--seed",
        str(seed),
        "--randomize-box",
        "--save-video",
        "--video-mode",
        video_mode,
        "--no-rerun",
        "--device",
        device,
        "--output-dir",
        str(out_dir),
    ]
    if policy == "checkpoint":
        if checkpoint is None or not checkpoint.is_file():
            raise FileNotFoundError(f"checkpoint required for video: {checkpoint}")
        cmd.extend(["--checkpoint", str(checkpoint)])
    if temporal_ensemble:
        cmd.extend(["--temporal-ensemble", "--temporal-ensemble-coeff", "0.01"])
    else:
        cmd.append("--no-temporal-ensemble")
        if policy == "checkpoint":
            cmd.extend(["--n-action-steps", "30"])

    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))
    src = out_dir / "sim_rollout.mp4"
    if not src.is_file():
        raise FileNotFoundError(f"expected video not written: {src}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(src.read_bytes())
    print(f"wrote {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--training-metrics", type=Path, default=None)
    parser.add_argument("--te-metrics", type=Path, default=None)
    parser.add_argument("--chunk30-metrics", type=Path, default=None)
    parser.add_argument(
        "--scatter-metrics",
        type=Path,
        default=None,
        help="Metrics with initial_box_xy (defaults to --te-metrics)",
    )
    parser.add_argument(
        "--use-fixtures",
        action="store_true",
        help="Use tests/fixtures/report_figures/* when paths omitted",
    )
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument(
        "--video-policy",
        choices=("scripted", "checkpoint"),
        default="scripted",
        help="scripted works without a local ACT checkpoint",
    )
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--temporal-ensemble", action="store_true")
    parser.add_argument("--video-seed", type=int, default=0)
    parser.add_argument("--video-max-steps", type=int, default=260)
    parser.add_argument(
        "--video-mode",
        choices=("topdown", "mujoco"),
        default="topdown",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any requested artifact cannot be produced",
    )
    args = parser.parse_args()

    if args.use_fixtures:
        args.training_metrics = args.training_metrics or (FIXTURES / "training_metrics.json")
        args.te_metrics = args.te_metrics or (FIXTURES / "metrics_te.json")
        args.chunk30_metrics = args.chunk30_metrics or (FIXTURES / "metrics_chunk30.json")
        args.scatter_metrics = args.scatter_metrics or (FIXTURES / "metrics_te.json")

    # Sensible defaults pointing at docs/results (may lack samples).
    if args.te_metrics is None:
        candidate = REPO_ROOT / "docs" / "results" / "eval_sim_act_post50_best_model_te_te.json"
        if candidate.is_file():
            args.te_metrics = candidate
    if args.chunk30_metrics is None:
        candidate = REPO_ROOT / "docs" / "results" / "eval_sim_act_post50_best_model_chunk30.json"
        if candidate.is_file():
            args.chunk30_metrics = candidate
    if args.scatter_metrics is None:
        args.scatter_metrics = args.te_metrics
    if args.training_metrics is None:
        for cand in (
            REPO_ROOT / "checkpoints" / "sim_act_post50" / "training_metrics.json",
            REPO_ROOT / "checkpoints" / "sim_act" / "training_metrics.json",
        ):
            if cand.is_file():
                args.training_metrics = cand
                break

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    def try_step(label: str, path: Path, fn) -> None:
        try:
            fn()
            written.append(f"{label}: {path}")
            print(f"OK  {label} -> {path}")
        except Exception as exc:  # noqa: BLE001 — report and continue unless --strict
            msg = f"{label}: {exc}"
            skipped.append(msg)
            failed.append(msg)
            print(f"SKIP {label}: {exc}", file=sys.stderr)
            if args.strict:
                raise

    if args.training_metrics is not None:
        dest = out / "training_loss_curve.png"
        try_step(
            "training_loss_curve",
            dest,
            lambda: plot_training_loss(args.training_metrics, dest),
        )
    else:
        skipped.append(
            "training_loss_curve: pass --training-metrics PATH "
            "(e.g. checkpoints/sim_act_post50/training_metrics.json)"
        )

    if args.te_metrics is not None and args.chunk30_metrics is not None:
        dest = out / "position_error_histogram.png"
        try_step(
            "position_error_histogram",
            dest,
            lambda: plot_position_error_histogram(args.te_metrics, args.chunk30_metrics, dest),
        )
    else:
        skipped.append("position_error_histogram: pass --te-metrics and --chunk30-metrics")

    if args.scatter_metrics is not None:
        dest = out / "initial_box_xy_scatter.png"
        try_step(
            "initial_box_xy_scatter",
            dest,
            lambda: plot_initial_box_xy_scatter(args.scatter_metrics, dest),
        )
    else:
        skipped.append("initial_box_xy_scatter: pass --scatter-metrics or --te-metrics")

    if not args.skip_video:
        dest = out / "sim_rollout_representative.mp4"
        try_step(
            "sim_rollout_representative",
            dest,
            lambda: write_rollout_video(
                out_path=dest,
                policy=args.video_policy,
                checkpoint=args.checkpoint,
                device=args.device,
                temporal_ensemble=args.temporal_ensemble,
                seed=args.video_seed,
                max_steps=args.video_max_steps,
                video_mode=args.video_mode,
            ),
        )
    else:
        skipped.append("sim_rollout_representative: --skip-video")

    manifest = {
        "output_dir": str(out),
        "written": written,
        "skipped": skipped,
        "failed": failed,
        "inputs": {
            "training_metrics": str(args.training_metrics) if args.training_metrics else None,
            "te_metrics": str(args.te_metrics) if args.te_metrics else None,
            "chunk30_metrics": str(args.chunk30_metrics) if args.chunk30_metrics else None,
            "scatter_metrics": str(args.scatter_metrics) if args.scatter_metrics else None,
            "checkpoint": str(args.checkpoint) if args.checkpoint else None,
            "video_policy": args.video_policy,
        },
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {manifest_path}")
    print(json.dumps(manifest, indent=2))

    if args.strict and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
