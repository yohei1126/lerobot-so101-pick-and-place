#!/usr/bin/env python3
"""Convert a rosbag2 directory to a contract-aligned LeRobotDataset.

Example:

    pip install -e "port_pick_align/[training]"
    python scripts/convert_bag.py \\
      --bag port_pick_align/tests/fixtures/sample_bag \\
      --output data/from_bag/lerobot
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
from port_pick_align.dataset.converter import (
    DEFAULT_REPO_ID,
    DEFAULT_TASK,
    ConversionValidationError,
    convert_bag_to_lerobot,
)

DEFAULT_OUTPUT = REPO_ROOT / "data" / "from_bag" / "lerobot"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bag", type=Path, required=True, help="rosbag2 directory")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--repo-id", type=str, default=DEFAULT_REPO_ID)
    parser.add_argument("--task", type=str, default=DEFAULT_TASK)
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Fail if the output directory already exists.",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip RobOps quality gates (not recommended).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.bag.is_dir():
        raise SystemExit(f"Bag directory not found: {args.bag}")
    try:
        root = convert_bag_to_lerobot(
            args.bag,
            args.output,
            contract_path=args.contract,
            repo_id=args.repo_id,
            task=args.task,
            overwrite=not args.no_overwrite,
            skip_validation=args.skip_validation,
        )
    except ConversionValidationError as exc:
        raise SystemExit(f"Validation failed: {exc}") from exc
    print(f"LeRobotDataset written to: {root}")


if __name__ == "__main__":
    main()
