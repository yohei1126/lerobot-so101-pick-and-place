#!/usr/bin/env python3
"""Light idle-start trim wrapper for ACT retrain (Issue #45).

After the normal episode-level train/val split, drop leading frames before
``(first_motion − keep_before)``. Optionally mix a fraction of *untrimmed*
episodes back into the train split so rest→move is still supervised.

Does NOT start training by itself when imported; call ``main()`` or run as
``python scripts/train_act_light_trim.py ...``.

Defaults match a ready-to-run retrain (checkpoint every 2500 steps) but Yohei
must launch when MPS is free — do not auto-start long jobs from agents.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import Subset

MOTION_DEG = 5.0
DEFAULT_KEEP_BEFORE = 40
DEFAULT_UNTRIM_MIX = 0.0  # 0.0 = all light-trimmed; 0.5 = half episodes untrimmed


def _episode_ranges(dataset: Any) -> list[tuple[int, int]]:
    from port_pick_align.training.train_act import _episode_frame_ranges

    ranges = _episode_frame_ranges(dataset)
    if ranges is None or len(ranges) < 1:
        raise RuntimeError("Dataset has no episode frame ranges; cannot light-trim")
    return ranges


def _action_matrix(dataset: Any) -> np.ndarray:
    hf = getattr(dataset, "hf_dataset", None)
    if hf is None or "action" not in getattr(hf, "column_names", []):
        raise RuntimeError("dataset.hf_dataset['action'] required for idle trim")
    slim = hf.select_columns(["action"])
    raw = slim["action"]
    rows = []
    for i in range(len(raw)):
        a = raw[i]
        if isinstance(a, torch.Tensor):
            rows.append(a.detach().cpu().numpy().astype(np.float64, copy=False))
        else:
            rows.append(np.asarray(a, dtype=np.float64))
    return np.stack(rows, axis=0)


def compute_keep_from(
    dataset: Any,
    *,
    motion_deg: float = MOTION_DEG,
    keep_before: int = DEFAULT_KEEP_BEFORE,
) -> tuple[dict[int, int], list[tuple[int, int]]]:
    ranges = _episode_ranges(dataset)
    actions = _action_matrix(dataset)
    keep_from: dict[int, int] = {}
    total_drop = 0
    total_keep = 0
    print(
        f"[light-trim] drop before (first |Δaction|_∞ > {motion_deg} deg) − {keep_before} frames"
    )
    for ep_id, (start, end) in enumerate(ranges):
        ep_len = end - start
        ref = actions[start]
        first_rel: int | None = None
        for rel in range(ep_len):
            if float(np.max(np.abs(actions[start + rel] - ref))) > motion_deg:
                first_rel = rel
                break
        if first_rel is None:
            keep = start
            dropped = 0
            first_s = "none"
        else:
            keep = max(start, start + first_rel - keep_before)
            dropped = keep - start
            first_s = str(first_rel)
        keep_from[ep_id] = keep
        kept = end - keep
        total_drop += dropped
        total_keep += kept
        print(
            f"  ep{ep_id:02d} len={ep_len} first_motion_rel={first_s} "
            f"dropped={dropped} kept={kept}"
        )
    print(
        f"[light-trim] episodes={len(ranges)} total_dropped={total_drop} "
        f"total_kept={total_keep}"
    )
    return keep_from, ranges


def _index_to_episode(ranges: list[tuple[int, int]], index: int) -> int:
    for ep_id, (start, end) in enumerate(ranges):
        if start <= index < end:
            return ep_id
    raise KeyError(f"index {index} not in any episode range")


def install_light_trim_patch(
    *,
    keep_before: int = DEFAULT_KEEP_BEFORE,
    untrim_mix: float = DEFAULT_UNTRIM_MIX,
    seed: int = 0,
) -> None:
    """Monkeypatch ``split_train_val`` with light trim (+ optional untrim mix)."""
    import port_pick_align.training.train_act as train_act_mod

    if not (0.0 <= untrim_mix <= 1.0):
        raise ValueError(f"untrim_mix must be in [0,1], got {untrim_mix}")

    original = train_act_mod.split_train_val
    cache: dict[int, tuple[dict[int, int], list[tuple[int, int]]]] = {}

    def split_train_val_light(dataset: Any, val_ratio: float, seed_split: int):
        train_data, val_data, n_train_eps, n_val_eps = original(
            dataset, val_ratio, seed_split
        )
        ds_id = id(dataset)
        if ds_id not in cache:
            cache[ds_id] = compute_keep_from(dataset, keep_before=keep_before)
        keep_from, ranges = cache[ds_id]

        # Episodes to leave untrimmed (train only), chosen by seed.
        rng = random.Random(seed_split if seed is None else seed)
        all_eps = list(range(len(ranges)))
        n_untrim = round(len(all_eps) * untrim_mix)
        untrim_eps = set(rng.sample(all_eps, n_untrim)) if n_untrim > 0 else set()
        if untrim_eps:
            print(
                f"[light-trim] untrim_mix={untrim_mix} → leave untrimmed eps={sorted(untrim_eps)}"
            )

        def _trim(split: Any, name: str, allow_untrim: bool) -> Any:
            if split is None:
                return None
            if isinstance(split, Subset):
                before = [int(i) for i in split.indices]
            else:
                before = list(range(len(split)))
            after: list[int] = []
            for idx in before:
                ep_id = _index_to_episode(ranges, idx)
                if (allow_untrim and ep_id in untrim_eps) or idx >= keep_from[ep_id]:
                    after.append(idx)
            print(
                f"  {name}: frames {len(before)} -> {len(after)} (removed {len(before) - len(after)})"
            )
            if len(after) < 1:
                raise RuntimeError(f"{name} split empty after light trim")
            base = split.dataset if isinstance(split, Subset) else split
            return Subset(base, after)

        train_data = _trim(train_data, "train", allow_untrim=True)
        val_data = _trim(val_data, "val", allow_untrim=False)
        return train_data, val_data, n_train_eps, n_val_eps

    train_act_mod.split_train_val = split_train_val_light  # type: ignore[assignment]
    print(
        f"[light-trim] patched split_train_val keep_before={keep_before} untrim_mix={untrim_mix}"
    )


def build_recommended_argv(
    *,
    dataset_root: Path,
    output_dir: Path,
    contract: Path,
    steps: int = 25000,
    keep_before: int = DEFAULT_KEEP_BEFORE,
    untrim_mix: float = DEFAULT_UNTRIM_MIX,
) -> list[str]:
    """CLI args for a light-trim retrain (checkpoint every 2500)."""
    return [
        "--contract",
        str(contract),
        "--dataset-root",
        str(dataset_root),
        "--repo-id",
        "local/so101_pick_sponge_main_clean28",
        "--output-dir",
        str(output_dir),
        "--arch",
        "full",
        "--steps",
        str(steps),
        "--batch-size",
        "8",
        "--lr",
        "1e-4",
        "--val-ratio",
        "0.1",
        "--val-interval",
        "500",
        "--max-val-batches",
        "20",
        "--scheduler",
        "cosine",
        "--checkpoint-interval",
        "2500",
        "--device",
        "mps",
        "--skip-infer",
        # keep_before / untrim_mix are consumed by this wrapper, not train_act
        "--keep-before",
        str(keep_before),
        "--untrim-mix",
        str(untrim_mix),
    ]


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Local flags (strip before forwarding to train_act)
    keep_before = DEFAULT_KEEP_BEFORE
    untrim_mix = DEFAULT_UNTRIM_MIX
    seed = 0

    def _pop_opt(flag: str, cast, default):
        nonlocal argv
        if flag in argv:
            i = argv.index(flag)
            val = cast(argv[i + 1])
            del argv[i : i + 2]
            return val
        return default

    keep_before = _pop_opt("--keep-before", int, keep_before)
    untrim_mix = _pop_opt("--untrim-mix", float, untrim_mix)
    seed = _pop_opt("--trim-seed", int, seed)
    dry = False
    if "--print-command-only" in argv:
        argv.remove("--print-command-only")
        dry = True

    install_light_trim_patch(keep_before=keep_before, untrim_mix=untrim_mix, seed=seed)
    if dry:
        print(
            "[light-trim] patch installed; not calling train_act (--print-command-only)"
        )
        return

    from port_pick_align.training import train_act

    train_act.main(argv)


if __name__ == "__main__":
    main()
