#!/usr/bin/env python3
"""Collect MuJoCo oracle demonstrations as a contract-aligned LeRobotDataset.

The script rolls out ``ScriptedPickAlignPolicy`` in ``PickAlignSimEnv``. Box XY
and yaw are randomized. Top and wrist images are acquired as 640×480 BGR and
stored as RGB. ``DataValidator`` checks timestamp sync, frame gaps, joint
limits, and static episodes. Actions are checked against the same limits.

Official collection (50–100 episodes, full resolution, full horizon) is a local
run. A short low-resolution smoke does not satisfy that requirement.

Examples:

    python scripts/collect_sim_dataset.py --episodes 64

    python scripts/collect_sim_dataset.py --episodes 1 --max-steps 20 \\
        --width 64 --height 48 --allow-short --allow-failures \\
        --output /tmp/sim_expert_smoke/lerobot
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "port_pick_align" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from port_pick_align.contract import DEFAULT_CONTRACT_PATH
from port_pick_align.dataset.sim_collect import (
    DEFAULT_EPISODES,
    DEFAULT_MAX_ATTEMPTS,
    OFFICIAL_EPISODE_MAX,
    OFFICIAL_EPISODE_MIN,
    SimCollectionError,
    collect_sim_dataset,
)
from port_pick_align.simulation.policies import ScriptedPickAlignPolicy

DEFAULT_OUTPUT = REPO_ROOT / "data" / "sim_expert" / "lerobot"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--episodes", type=int, default=DEFAULT_EPISODES)
    horizon = ScriptedPickAlignPolicy.horizon_steps()
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help=f"Control steps per episode (default: scripted horizon {horizon}).",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument(
        "--allow-short",
        action="store_true",
        help="Permit episode counts outside 50–100 or a non-contract render size.",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Keep episodes that pass the validator even if alignment failed.",
    )
    parser.add_argument(
        "--no-randomize-box",
        action="store_true",
        help="Use the fixed box spawn (not an official randomized collection).",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Fail if the output directory already exists.",
    )
    return parser.parse_args(argv)


def _reject_unofficial(args: argparse.Namespace) -> None:
    if args.allow_short:
        return
    if not (OFFICIAL_EPISODE_MIN <= args.episodes <= OFFICIAL_EPISODE_MAX):
        raise SystemExit(
            f"episodes must be {OFFICIAL_EPISODE_MIN}–{OFFICIAL_EPISODE_MAX} "
            f"(got {args.episodes}). Pass --allow-short for a smoke run."
        )
    if args.width is not None or args.height is not None:
        raise SystemExit(
            "Official collection uses the contract resolution 640×480. "
            "Pass --allow-short to override --width/--height."
        )
    if (
        args.max_steps is not None
        and args.max_steps != ScriptedPickAlignPolicy.horizon_steps()
    ):
        raise SystemExit(
            "Official collection uses the full scripted horizon. "
            "Pass --allow-short to set --max-steps."
        )
    if args.allow_failures or args.no_randomize_box:
        raise SystemExit(
            "Official collection randomizes the box and keeps aligned episodes only. "
            "Pass --allow-short together with --allow-failures or --no-randomize-box."
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _reject_unofficial(args)
    try:
        root = collect_sim_dataset(
            args.output,
            contract_path=args.contract,
            episodes=args.episodes,
            max_steps=args.max_steps,
            seed=args.seed,
            overwrite=not args.no_overwrite,
            randomize_box=not args.no_randomize_box,
            require_success=not args.allow_failures,
            max_attempts=args.max_attempts,
            render_height=args.height,
            render_width=args.width,
            report_path=args.report,
        )
    except (SimCollectionError, FileExistsError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Sim expert LeRobotDataset written to: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
