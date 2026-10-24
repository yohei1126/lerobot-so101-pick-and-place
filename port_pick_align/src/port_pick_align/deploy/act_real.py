"""Run REAL-trained ACT (port_pick_align train_act on clean28) on the SO-101.

No sim conversion: the model was trained directly on LeRobot degrees / gripper 0-100,
with NO normalization (train_act feeds raw state/action, images float [0,1] RGB).

Must NOT apply the sim rad↔deg conversion used by
``port_pick_align.deploy.run_sim_policy_on_real``.

Usage::

  python -m port_pick_align.deploy.act_real [--live] [--offline-check] ...
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import numpy as np
import torch

from port_pick_align.deploy import real_common as rc

DEFAULT_CKPT = rc.hw_root() / "outputs/act_so101_main_clean28_20261023/best_model.pt"
DEFAULT_DATASET = rc.hw_root() / "datasets/so101_pick_sponge_main_20261023_clean28"


def load_act(ckpt: Path, device: str):
    from port_pick_align.training.train_act import load_policy_from_checkpoint

    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    contract = payload["contract"]
    policy = load_policy_from_checkpoint(ckpt, contract, device=device)
    print(
        f"[act] loaded {ckpt} step={payload.get('step')} val_l1={payload.get('val_l1')} "
        f"chunk={contract['model']['chunk_size']} arch={payload.get('arch', {}).get('arch')}",
        flush=True,
    )
    return policy, int(contract["model"]["chunk_size"])


def img_to_tensor(img_hwc_uint8, device):
    t = torch.from_numpy(np.ascontiguousarray(img_hwc_uint8)).permute(2, 0, 1).float() / 255.0
    return t.unsqueeze(0).to(device)


@torch.inference_mode()
def predict_chunk(policy, top, wrist, state, device) -> np.ndarray:
    """Predict action chunk in real units (deg / gripper 0-100). No rad↔deg conversion."""
    batch = {
        "observation.images.top": top if torch.is_tensor(top) else img_to_tensor(top, device),
        "observation.images.wrist": wrist
        if torch.is_tensor(wrist)
        else img_to_tensor(wrist, device),
        "observation.state": torch.as_tensor(state, dtype=torch.float32).reshape(1, -1).to(device),
    }
    out = policy.predict_action_chunk(batch)
    if out.ndim == 3:
        out = out[0]
    return np.asarray(out.float().cpu().numpy(), dtype=np.float32)


class TemporalEnsembler:
    """ACT-style exponential temporal ensemble (Zhao et al.).

    Query a fresh action chunk every control step. Age previous chunks by one,
    then return the weighted average of all pending predictions for *now*
    with weights ``exp(-k * age)`` (age 0 = newest).
    """

    def __init__(self, k: float = 0.01):
        if k < 0:
            raise ValueError(f"temporal ensemble k must be >= 0, got {k}")
        self.k = float(k)
        self._chunks: list[np.ndarray] = []

    def reset(self) -> None:
        self._chunks.clear()

    def step(self, chunk: np.ndarray) -> np.ndarray:
        chunk = np.asarray(chunk, dtype=np.float32)
        if chunk.ndim != 2:
            raise ValueError(f"expected chunk (T, A), got shape {chunk.shape}")
        aged = [prev[1:] for prev in self._chunks if prev.shape[0] > 1]
        aged.append(chunk)
        # Keep at most one prediction per horizon slot.
        self._chunks = aged[-chunk.shape[0] :]
        actions = np.stack([c[0] for c in self._chunks], axis=0)
        # history is oldest→newest; age of newest is 0
        n = actions.shape[0]
        ages = np.arange(n - 1, -1, -1, dtype=np.float64)
        weights = np.exp(-self.k * ages)
        weights = weights / weights.sum()
        return (actions * weights[:, None]).sum(axis=0).astype(np.float32)


def offline_check(policy, chunk, device, dataset: Path, n_frames: int):
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    ds = LeRobotDataset(
        "local/clean28",
        root=dataset,
        video_backend="pyav",
        delta_timestamps={"action": [i / 30 for i in range(chunk)]},
    )
    rng = np.random.default_rng(0)
    idx = sorted(rng.choice(len(ds), size=n_frames, replace=False).tolist())
    e0_rows: list[np.ndarray] = []
    eall_rows: list[np.ndarray] = []
    lats: list[float] = []
    for i in idx:
        s = ds[i]
        top = s["observation.images.top"].unsqueeze(0).to(device)  # float [0,1] CHW
        wr = s["observation.images.wrist"].unsqueeze(0).to(device)
        st = s["observation.state"].numpy()
        gt = s["action"].numpy()  # (chunk,6)
        pad = s["action_is_pad"].numpy()
        if device == "mps":
            torch.mps.synchronize()
        t0 = time.perf_counter()
        pred = predict_chunk(policy, top, wr, st, device)
        lats.append((time.perf_counter() - t0) * 1000)
        e0_rows.append(np.abs(pred[0] - gt[0]))
        eall_rows.append(np.abs(pred[~pad] - gt[~pad]).mean(0))
        print(
            f"  frame {i:6d} ep={int(s['episode_index'])} state {rc.fmt(st)}\n"
            f"               gt[0]  {rc.fmt(gt[0])}\n"
            f"               pred[0]{rc.fmt(pred[0])}",
            flush=True,
        )
    e0_arr = np.asarray(e0_rows, dtype=np.float64)
    eall_arr = np.asarray(eall_rows, dtype=np.float64)
    print(
        "[offline] MAE step0 per joint: "
        + " ".join(f"{j}={v:.2f}" for j, v in zip(rc.JOINTS, e0_arr.mean(0), strict=True))
    )
    print(
        f"[offline] MAE step0 arm joints (deg) = {e0_arr[:, :5].mean():.2f}, "
        f"gripper(0-100) = {e0_arr[:, 5].mean():.2f}"
    )
    print(
        f"[offline] MAE full chunk arm (deg) = {eall_arr[:, :5].mean():.2f}, "
        f"gripper = {eall_arr[:, 5].mean():.2f}"
    )
    print(
        f"[offline] latency ms (excl. first warmup) mean={np.mean(lats[1:]):.1f} "
        f"p50={np.median(lats[1:]):.1f}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=(
            "Run REAL-trained ACT on SO-101 (degrees / gripper 0-100). "
            "Default is dry-run; pass --live to send actions. "
            "Does NOT apply sim rad↔deg conversion."
        )
    )
    rc.add_common_args(ap)
    ap.add_argument(
        "--checkpoint",
        type=Path,
        default=Path(os.environ.get("ACT_REAL_CHECKPOINT", str(DEFAULT_CKPT))),
    )
    ap.add_argument(
        "--dataset",
        type=Path,
        default=Path(os.environ.get("ACT_REAL_DATASET", str(DEFAULT_DATASET))),
        help="LeRobot dataset root for --offline-check",
    )
    ap.add_argument(
        "--n-action-steps",
        type=int,
        default=10,
        help="execute N steps of each chunk before replanning (ignored if --temporal-ensemble)",
    )
    ap.add_argument(
        "--temporal-ensemble",
        action="store_true",
        help=(
            "ACT exponential temporal ensembling: query the policy every control step "
            "and average overlapping chunk predictions (default k=0.01)."
        ),
    )
    ap.add_argument(
        "--temporal-ensemble-k",
        type=float,
        default=0.01,
        help="exp(-k * age) coefficient for --temporal-ensemble (default 0.01)",
    )
    ap.add_argument("--offline-check", action="store_true", help="dataset check only, no robot")
    ap.add_argument("--offline-frames", type=int, default=24)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rc.setup_log("act_offline" if args.offline_check else ("act_live" if args.live else "act_dry"))
    print(f"[args] {vars(args)}", flush=True)
    policy, chunk = load_act(args.checkpoint, args.device)
    if args.offline_check:
        offline_check(policy, chunk, args.device, args.dataset, args.offline_frames)
        return

    if args.temporal_ensemble:
        ensembler = TemporalEnsembler(k=float(args.temporal_ensemble_k))
        print(
            f"[act] temporal_ensemble ON k={ensembler.k} (query every step)",
            flush=True,
        )

        def reset():
            ensembler.reset()

        def step(obs, state):
            pred = predict_chunk(policy, obs["top"], obs["wrist"], state, args.device)
            a = ensembler.step(pred)
            info = f"te_n={len(ensembler._chunks)}"
            return a, info

    else:
        n_exec = max(1, min(args.n_action_steps, chunk))
        st = {"chunk": None, "i": 0}

        def reset():
            st["chunk"], st["i"] = None, 0

        def step(obs, state):
            replan = st["chunk"] is None or st["i"] >= n_exec
            if replan:
                st["chunk"] = predict_chunk(policy, obs["top"], obs["wrist"], state, args.device)
                st["i"] = 0
            a = st["chunk"][st["i"]]
            info = f"chunk_i={st['i']}{' REPLAN' if replan else ''}"
            st["i"] += 1
            return a, info

    raise SystemExit(rc.run_loop(args, "act", step, reset))


if __name__ == "__main__":
    main()
