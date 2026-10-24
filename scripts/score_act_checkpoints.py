#!/usr/bin/env python3
"""Rank ACT checkpoints by open-loop metrics on a LeRobot dataset.

Metrics (Issue #43):
  * frame0 chunk travel  ‖pred[-1,:5] − pred[0,:5]‖  (higher → less "wait")
  * step0 arm MAE vs GT
  * mid-episode arm MAE vs GT

Example::

  PYTHONPATH=port_pick_align/src python scripts/score_act_checkpoints.py \\
    --run-dirs ~/work/lerobot-hw/outputs/act_so101_clean28_trim_20261024 \\
               ~/work/lerobot-hw/outputs/act_so101_main_clean28_20261023 \\
    --dataset-root ~/work/lerobot-hw/datasets/so101_pick_sponge_main_20261023_clean28 \\
    --device mps --out outputs/checkpoint_scores.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch


def _hw_default() -> Path:
    return Path.home() / "work" / "lerobot-hw"


def discover_checkpoints(run_dirs: list[Path]) -> list[Path]:
    found: list[Path] = []
    for d in run_dirs:
        d = d.expanduser().resolve()
        if not d.is_dir():
            print(f"[warn] missing run dir: {d}", file=sys.stderr)
            continue
        for p in sorted(d.glob("*.pt")):
            found.append(p)
    return found


def sample_indices(dataset_root: Path, n_eps: int, seed: int) -> dict[str, list[int]]:
    """Pick frame0 / mid indices from a spread of episodes (parquet meta, no video)."""
    import pyarrow.parquet as pq

    ep_files = sorted((dataset_root / "meta" / "episodes").rglob("*.parquet"))
    if not ep_files:
        raise FileNotFoundError(f"No episode parquet under {dataset_root}/meta/episodes")
    ep = pq.read_table(ep_files[0]).to_pandas()
    n = len(ep)
    rng = np.random.default_rng(seed)
    # evenly spaced episode ids for coverage
    if n_eps >= n:
        picks = list(range(n))
    else:
        picks = np.linspace(0, n - 1, n_eps, dtype=int).tolist()
        # tiny jitter without duplicates
        picks = sorted(set(int(i) for i in picks))
    frame0: list[int] = []
    mid: list[int] = []
    for i in picks:
        row = ep.iloc[int(i)]
        s, e = int(row["dataset_from_index"]), int(row["dataset_to_index"])
        frame0.append(s)
        mid.append((s + e) // 2)
    _ = rng  # seed reserved for future random mid sampling
    return {"frame0": frame0, "mid": mid}


@torch.inference_mode()
def eval_checkpoint(
    ckpt: Path,
    dataset,
    indices: dict[str, list[int]],
    device: str,
) -> dict:
    from port_pick_align.training.train_act import load_policy_from_checkpoint

    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    contract = payload["contract"]
    policy = load_policy_from_checkpoint(ckpt, contract, device=device)
    policy.eval()
    chunk = int(contract["model"]["chunk_size"])

    def _bucket(idxs: list[int]) -> dict:
        e0: list[np.ndarray] = []
        travels: list[float] = []
        for i in idxs:
            s = dataset[i]
            top = s["observation.images.top"].unsqueeze(0).to(device)
            wr = s["observation.images.wrist"].unsqueeze(0).to(device)
            st = s["observation.state"]
            gt = s["action"].numpy()
            pad = s["action_is_pad"].numpy()
            batch = {
                "observation.images.top": top,
                "observation.images.wrist": wr,
                "observation.state": torch.as_tensor(st, dtype=torch.float32).reshape(1, -1).to(device),
            }
            pred = policy.predict_action_chunk(batch)
            if pred.ndim == 3:
                pred = pred[0]
            pred = pred.float().cpu().numpy()
            mask = ~pad
            e0.append(np.abs(pred[0] - gt[0]))
            travels.append(float(np.linalg.norm(pred[mask][-1, :5] - pred[mask][0, :5])))
        e0_arr = np.asarray(e0, dtype=np.float64)
        return {
            "mae_step0_arm": float(e0_arr[:, :5].mean()),
            "mae_step0_grip": float(e0_arr[:, 5].mean()),
            "mae_step0_per_joint": e0_arr.mean(0).tolist(),
            "chunk_travel_arm_mean": float(np.mean(travels)),
            "chunk_travel_arm_std": float(np.std(travels)),
            "n": len(idxs),
        }

    out = {
        "path": str(ckpt),
        "name": ckpt.name,
        "run": ckpt.parent.name,
        "step": payload.get("step"),
        "val_l1": payload.get("val_l1"),
        "chunk_size": chunk,
        "frame0": _bucket(indices["frame0"]),
        "mid": _bucket(indices["mid"]),
    }
    del policy
    if device == "mps" and hasattr(torch, "mps"):
        torch.mps.empty_cache()
    return out


def rank_rows(rows: list[dict]) -> list[dict]:
    """Higher frame0 travel is good; lower MAEs are good.

    Composite score (higher better):
      travel_z - 0.5 * mae0_z - 0.25 * mae_mid_z
    """
    if not rows:
        return rows
    travel = np.array([r["frame0"]["chunk_travel_arm_mean"] for r in rows], dtype=np.float64)
    mae0 = np.array([r["frame0"]["mae_step0_arm"] for r in rows], dtype=np.float64)
    maem = np.array([r["mid"]["mae_step0_arm"] for r in rows], dtype=np.float64)

    def _z(x: np.ndarray) -> np.ndarray:
        s = float(x.std())
        if s < 1e-9:
            return np.zeros_like(x)
        return (x - x.mean()) / s

    score = _z(travel) - 0.5 * _z(mae0) - 0.25 * _z(maem)
    for r, sc in zip(rows, score, strict=True):
        r["score"] = float(sc)
    return sorted(rows, key=lambda r: r["score"], reverse=True)


def format_table(rows: list[dict]) -> str:
    lines = [
        "| rank | run | ckpt | step | val_l1 | frame0 travel° | frame0 MAE_arm | mid MAE_arm | score |",
        "|-----:|-----|------|-----:|-------:|---------------:|---------------:|------------:|------:|",
    ]
    for i, r in enumerate(rows, 1):
        vl = r.get("val_l1")
        vl_s = f"{vl:.3f}" if isinstance(vl, (int, float)) else "—"
        step = r.get("step")
        step_s = str(step) if step is not None else "—"
        lines.append(
            f"| {i} | `{r['run']}` | `{r['name']}` | {step_s} | {vl_s} | "
            f"{r['frame0']['chunk_travel_arm_mean']:.2f} | "
            f"{r['frame0']['mae_step0_arm']:.2f} | "
            f"{r['mid']['mae_step0_arm']:.2f} | {r['score']:.3f} |"
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    hw = _hw_default()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--run-dirs",
        type=Path,
        nargs="+",
        default=[
            hw / "outputs" / "act_so101_clean28_trim_20261024",
            hw / "outputs" / "act_so101_main_clean28_20261023",
        ],
    )
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=hw / "datasets" / "so101_pick_sponge_main_20261023_clean28",
    )
    p.add_argument("--repo-id", default="local/clean28")
    p.add_argument("--device", default=None)
    p.add_argument("--n-episodes", type=int, default=6, help="episodes sampled for frame0/mid")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=None, help="JSON output path")
    p.add_argument("--md-out", type=Path, default=None, help="Markdown table output path")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    device = args.device
    if device is None:
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"

    ckpts = discover_checkpoints(list(args.run_dirs))
    if not ckpts:
        print("No checkpoints found", file=sys.stderr)
        return 1
    print(f"[score] device={device} n_ckpts={len(ckpts)} dataset={args.dataset_root}")

    indices = sample_indices(args.dataset_root.expanduser(), args.n_episodes, args.seed)
    print(f"[score] frame0 idx={indices['frame0']}")
    print(f"[score] mid    idx={indices['mid']}")

    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    # chunk size from first ckpt
    probe = torch.load(ckpts[0], map_location="cpu", weights_only=False)
    chunk = int(probe["contract"]["model"]["chunk_size"])
    del probe
    dataset = LeRobotDataset(
        args.repo_id,
        root=args.dataset_root.expanduser(),
        video_backend="pyav",
        delta_timestamps={"action": [i / 30.0 for i in range(chunk)]},
    )

    rows: list[dict] = []
    for i, ckpt in enumerate(ckpts, 1):
        print(f"[score] ({i}/{len(ckpts)}) {ckpt.parent.name}/{ckpt.name}", flush=True)
        rows.append(eval_checkpoint(ckpt, dataset, indices, device))

    ranked = rank_rows(rows)
    table = format_table(ranked)
    print("\n" + table + "\n")

    # Recommendations: top by score within each run + overall top movers
    by_run: dict[str, list[dict]] = {}
    for r in ranked:
        by_run.setdefault(r["run"], []).append(r)
    recs = []
    for run, rs in by_run.items():
        recs.append(rs[0])
    # also flag highest travel overall
    best_travel = max(ranked, key=lambda r: r["frame0"]["chunk_travel_arm_mean"])
    print("[recommend] per-run top score:")
    for r in recs:
        print(
            f"  - {r['run']}/{r['name']}  travel={r['frame0']['chunk_travel_arm_mean']:.1f}° "
            f"mae0={r['frame0']['mae_step0_arm']:.2f} score={r['score']:.3f}"
        )
    print(
        f"[recommend] highest frame0 travel: {best_travel['run']}/{best_travel['name']} "
        f"({best_travel['frame0']['chunk_travel_arm_mean']:.1f}°)"
    )

    payload = {
        "device": device,
        "dataset_root": str(args.dataset_root),
        "indices": indices,
        "ranked": ranked,
        "recommendations": {
            "per_run_top": [
                {"run": r["run"], "name": r["name"], "path": r["path"], "score": r["score"]}
                for r in recs
            ],
            "highest_frame0_travel": {
                "run": best_travel["run"],
                "name": best_travel["name"],
                "path": best_travel["path"],
                "travel": best_travel["frame0"]["chunk_travel_arm_mean"],
            },
        },
    }
    if args.out:
        args.out = args.out.expanduser()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"[score] wrote {args.out}")
    if args.md_out:
        args.md_out = args.md_out.expanduser()
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(table + "\n", encoding="utf-8")
        print(f"[score] wrote {args.md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
