#!/usr/bin/env python3
"""Generate a contract-aligned synthetic LeRobotDataset for ACT smoke training.

Example:

    pip install -e "pai_final/[training]"
    python scripts/generate_synthetic_dataset.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "pai_final" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from pai_final.contract import DEFAULT_CONTRACT_PATH
from pai_final.dataset.synthetic import (
    DEFAULT_EPISODES,
    DEFAULT_FRAMES,
    generate_synthetic_dataset,
)

DEFAULT_OUTPUT = REPO_ROOT / "data" / "synthetic" / "lerobot"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--episodes", type=int, default=DEFAULT_EPISODES)
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Fail if the output directory already exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = generate_synthetic_dataset(
        args.output,
        contract_path=args.contract,
        episodes=args.episodes,
        frames=args.frames,
        seed=args.seed,
        overwrite=not args.no_overwrite,
    )
    print(f"Synthetic LeRobotDataset written to: {root}")


if __name__ == "__main__":
    main()
