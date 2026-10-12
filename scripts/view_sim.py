#!/usr/bin/env python3
"""Interactive MuJoCo viewer for the pick-and-align tabletop (macOS: use mjpython).

Examples:

    # Apple Silicon / macOS (required for launch_passive)
    .venv/bin/mjpython scripts/view_sim.py

    # Linux / Windows
    python scripts/view_sim.py --policy scripted
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "port_pick_align" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from port_pick_align.contract import load_contract
from port_pick_align.simulation.env import PickAlignSimEnv
from port_pick_align.simulation.policies import (
    CheckpointPolicy,
    MockPolicy,
    ScriptedPickAlignPolicy,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy", choices=("mock", "checkpoint", "scripted"), default="scripted")
    p.add_argument(
        "--checkpoint",
        type=Path,
        default=REPO_ROOT / "checkpoints" / "synthetic_act" / "best_model.pt",
    )
    p.add_argument("--max-steps", type=int, default=0, help="0 = run until window closed")
    p.add_argument("--hz", type=float, default=30.0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default="cpu")
    return p.parse_args()


def main() -> int:
    import mujoco.viewer

    args = parse_args()
    contract = load_contract()
    chunk_size = int(contract["model"]["chunk_size"])
    action_dim = int(contract["model"]["action_dim"])

    if args.policy == "mock":
        policy: object = MockPolicy(chunk_size=chunk_size, action_dim=action_dim)
    elif args.policy == "scripted":
        policy = ScriptedPickAlignPolicy(chunk_size=chunk_size, action_dim=action_dim)
    else:
        from port_pick_align.training.train_act import load_policy_from_checkpoint

        act = load_policy_from_checkpoint(args.checkpoint, contract, device=args.device)
        policy = CheckpointPolicy(act, chunk_size=chunk_size, device=args.device)

    env = PickAlignSimEnv(contract=contract, max_episode_steps=10_000)
    obs, _ = env.reset(seed=args.seed)
    if hasattr(policy, "reset"):
        policy.reset()

    print("MuJoCo viewer: drag=orbit, scroll=zoom. Close the window to exit.")
    dt = 1.0 / max(args.hz, 1.0)
    step = 0
    try:
        with mujoco.viewer.launch_passive(env.model, env.data) as viewer:
            while viewer.is_running():
                chunk = policy.predict(obs)  # type: ignore[attr-defined]
                obs, _, terminated, truncated, _ = env.step(chunk[0])
                viewer.sync()
                time.sleep(dt)
                step += 1
                if terminated or truncated or (args.max_steps and step >= args.max_steps):
                    if args.max_steps and step >= args.max_steps:
                        break
                    obs, _ = env.reset(seed=args.seed + step)
                    if hasattr(policy, "reset"):
                        policy.reset()
                    step = 0
    finally:
        env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
