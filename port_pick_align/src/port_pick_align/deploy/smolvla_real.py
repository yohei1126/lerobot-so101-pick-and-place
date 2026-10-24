"""Run fine-tuned SmolVLA (lerobot-train, clean28) on the real SO-101.

* Uses the saved policy_preprocessor / policy_postprocessor (rename top->camera1,
  wrist->camera2, tokenizer, MEAN_STD state/action normalization) so units match.
* camera3: config lists it but empty_cameras=0 and the dataset never had it, so in
  training SmolVLA.prepare_images simply SKIPPED it (missing keys are only padded
  up to empty_cameras=0 -> none). We replicate by NOT supplying camera3.
* Chunk 50; executes --n-action-steps of each chunk then replans (blocking).

Usage::

  python -m port_pick_align.deploy.smolvla_real [--live] [--offline-check] ...
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np
import torch

from port_pick_align.deploy import real_common as rc


def _default_ckpt() -> Path:
    env = os.environ.get("SMOLVLA_CHECKPOINT", "").strip()
    if env:
        return Path(env).expanduser()
    return (
        rc.hw_root()
        / "outputs/smolvla_so101_clean28_20261023_2132/checkpoints/010000/pretrained_model"
    )


def _default_dataset() -> Path:
    env = os.environ.get("SMOLVLA_DATASET", "").strip()
    if env:
        return Path(env).expanduser()
    return rc.hw_root() / "datasets/so101_pick_sponge_main_20261023_clean28"


def load_smolvla(path: Path, device: str):
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

    policy = SmolVLAPolicy.from_pretrained(str(path))
    policy.config.device = device
    policy.to(device).eval()
    pre, post = make_pre_post_processors(
        policy.config,
        pretrained_path=str(path),
        preprocessor_overrides={"device_processor": {"device": device}},
    )
    print(
        f"[smolvla] loaded {path} chunk={policy.config.chunk_size} "
        f"n_action_steps={policy.config.n_action_steps} "
        f"empty_cameras={policy.config.empty_cameras} "
        f"image_features={list(policy.config.image_features)}",
        flush=True,
    )
    return policy, pre, post


def to_chw(img):
    if torch.is_tensor(img):
        return img.float()
    return torch.from_numpy(np.ascontiguousarray(img)).permute(2, 0, 1).float() / 255.0


@torch.inference_mode()
def predict_chunk(policy, pre, post, top, wrist, state, task, device) -> np.ndarray:
    """Build obs with top/wrist only (no camera3); pre renames to camera1/camera2."""
    obs = {
        "observation.images.top": to_chw(top),
        "observation.images.wrist": to_chw(wrist),
        "observation.state": torch.as_tensor(state, dtype=torch.float32),
        "task": task,
    }
    batch = pre(obs)
    chunk = policy.predict_action_chunk(batch)  # (1, 50, 6) normalized
    chunk = post(chunk)
    if chunk.ndim == 3:
        chunk = chunk[0]
    return np.asarray(chunk.float().cpu().numpy(), dtype=np.float32)


def offline_check(policy, pre, post, device, dataset: Path, n_frames, task):
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    chunk = policy.config.chunk_size
    ds = LeRobotDataset(
        "local/clean28",
        root=dataset,
        video_backend="pyav",
        delta_timestamps={"action": [i / 30 for i in range(chunk)]},
    )
    rng = np.random.default_rng(0)
    idx = sorted(rng.choice(len(ds), size=n_frames, replace=False).tolist())
    e0_rows: list[np.ndarray] = []
    e10_rows: list[np.ndarray] = []
    eall_rows: list[np.ndarray] = []
    lats: list[float] = []
    for i in idx:
        s = ds[i]
        gt, pad = s["action"].numpy(), s["action_is_pad"].numpy()
        st = s["observation.state"].numpy()
        torch.manual_seed(0)
        if device == "mps":
            torch.mps.synchronize()
        t0 = time.perf_counter()
        pred = predict_chunk(
            policy,
            pre,
            post,
            s["observation.images.top"],
            s["observation.images.wrist"],
            st,
            task,
            device,
        )
        lats.append((time.perf_counter() - t0) * 1000)
        e0_rows.append(np.abs(pred[0] - gt[0]))
        e10_rows.append(np.abs(pred[:10] - gt[:10]).mean(0))
        eall_rows.append(np.abs(pred[~pad] - gt[~pad]).mean(0))
        print(
            f"  frame {i:6d} ep={int(s['episode_index'])} state {rc.fmt(st)}\n"
            f"               gt[0]  {rc.fmt(gt[0])}\n"
            f"               pred[0]{rc.fmt(pred[0])}  ({lats[-1]:.0f}ms)",
            flush=True,
        )
    e0_arr = np.asarray(e0_rows, dtype=np.float64)
    e10_arr = np.asarray(e10_rows, dtype=np.float64)
    eall_arr = np.asarray(eall_rows, dtype=np.float64)
    print(
        "[offline] MAE step0 per joint: "
        + " ".join(f"{j}={v:.2f}" for j, v in zip(rc.JOINTS, e0_arr.mean(0), strict=True))
    )
    print(
        f"[offline] MAE step0 arm (deg) = {e0_arr[:, :5].mean():.2f}, "
        f"gripper = {e0_arr[:, 5].mean():.2f}"
    )
    print(
        f"[offline] MAE first10 arm (deg) = {e10_arr[:, :5].mean():.2f}, "
        f"gripper = {e10_arr[:, 5].mean():.2f}"
    )
    print(
        f"[offline] MAE full chunk(50) arm (deg) = {eall_arr[:, :5].mean():.2f}, "
        f"gripper = {eall_arr[:, 5].mean():.2f}"
    )
    print(
        f"[offline] latency per chunk ms (excl. warmup) "
        f"mean={np.mean(lats[1:]):.0f} p50={np.median(lats[1:]):.0f}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=(
            "Run fine-tuned SmolVLA on SO-101. Default is dry-run; pass --live to send actions. "
            "Supplies top/wrist only (no camera3)."
        )
    )
    rc.add_common_args(ap)
    ap.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="SmolVLA checkpoint dir (env SMOLVLA_CHECKPOINT; else under $LEROBOT_HW_ROOT/outputs)",
    )
    ap.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="LeRobot dataset root for --offline-check (env SMOLVLA_DATASET)",
    )
    ap.add_argument("--task", default=os.environ.get("SMOLVLA_TASK", rc.TASK))
    ap.add_argument(
        "--n-action-steps",
        type=int,
        default=25,
        help="execute N of the 50-step chunk, then replan",
    )
    ap.add_argument("--offline-check", action="store_true")
    ap.add_argument("--offline-frames", type=int, default=12)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rc.apply_hw_root(args)
    if args.checkpoint is None:
        args.checkpoint = _default_ckpt()
    if args.dataset is None:
        args.dataset = _default_dataset()
    rc.setup_log(
        "smolvla_offline"
        if args.offline_check
        else ("smolvla_live" if args.live else "smolvla_dry")
    )
    print(f"[args] {vars(args)}", flush=True)
    policy, pre, post = load_smolvla(args.checkpoint, args.device)
    if args.offline_check:
        offline_check(policy, pre, post, args.device, args.dataset, args.offline_frames, args.task)
        return
    n_exec = max(1, min(args.n_action_steps, policy.config.chunk_size))
    st = {"chunk": None, "i": 0}

    def reset():
        st["chunk"], st["i"] = None, 0
        policy.reset()

    def step(obs, state):
        replan = st["chunk"] is None or st["i"] >= n_exec
        if replan:
            st["chunk"] = predict_chunk(
                policy, pre, post, obs["top"], obs["wrist"], state, args.task, args.device
            )
            st["i"] = 0
        a = st["chunk"][st["i"]]
        info = f"chunk_i={st['i']}{' REPLAN' if replan else ''}"
        st["i"] += 1
        return a, info

    raise SystemExit(rc.run_loop(args, "smolvla", step, reset))


if __name__ == "__main__":
    main()
