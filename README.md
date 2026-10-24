# lerobot-so101-pick-and-place

Open-source toolkit for **SO-101** arm **pick-and-place** with [LeRobot](https://github.com/huggingface/lerobot): simulation training, real-robot demo recording, **ACT** and **SmolVLA** training, and safe real-arm runners.

[日本語版 README](README.ja.md) · [Docs site (EN)](https://yohei1126.github.io/lerobot-so101-pick-and-place/) · [ドキュメント (JA)](https://yohei1126.github.io/lerobot-so101-pick-and-place/ja/)

## What this robot does

The follower arm picks a small tabletop object and places it onto a target pose (planar position + yaw). The stack covers:

1. **Sim**: MuJoCo tabletop env, scripted expert collection, closed-loop ACT eval  
2. **Data**: rosbag2 / synthetic / LeRobotDataset conversion and quality checks  
3. **Train**: ACT (and SmolVLA scripts where available) on sim or real demos  
4. **Real**: SO-101 Leader/Follower bring-up, teleop recording, cameras, unit-aware sim→real and real-trained policy deploy runners  

Hardware target: **SO-101** (Feetech STS3215) with top + wrist cameras (see docs).

## Quickstart

```bash
git clone https://github.com/yohei1126/lerobot-so101-pick-and-place.git
cd lerobot-so101-pick-and-place

python3.12 -m venv .venv
source .venv/bin/activate
pip install -e "port_pick_align/[simulation,training,dev]"

# End-to-end smoke (bag → convert → train stub → ROS mock path as applicable)
./scripts/e2e_pipeline_smoke.sh

# Unattended collect → ACT train → multi-checkpoint sim eval
./scripts/run_pipeline.sh --smoke --device cpu
```

Real-robot bring-up, recording, udev, sim→real ACT, and real-trained ACT/SmolVLA deploy steps are under `docs/` (linked below). Prefer dry-run before live motor commands.

## Documentation

| Topic | English | 日本語 |
| --- | --- | --- |
| Docs index | [docs/index.en.md](docs/index.en.md) | [docs/index.ja.md](docs/index.ja.md) |
| Setup | [docs/setup.en.md](docs/setup.en.md) | [docs/setup.ja.md](docs/setup.ja.md) |
| Dataset | [docs/dataset.en.md](docs/dataset.en.md) | [docs/dataset.ja.md](docs/dataset.ja.md) |
| Training | [docs/training.en.md](docs/training.en.md) | [docs/training.ja.md](docs/training.ja.md) |
| Simulation | [docs/simulation.en.md](docs/simulation.en.md) | [docs/simulation.ja.md](docs/simulation.ja.md) |
| Hardware / bring-up / deploy | [hardware.en.md](docs/hardware.en.md) · [bring-up](docs/real_robot_bringup.en.md) · [deploy](docs/real_robot_deploy.en.md) | [hardware.ja.md](docs/hardware.ja.md) · [bring-up](docs/real_robot_bringup.ja.md) · [deploy](docs/real_robot_deploy.ja.md) |
| Published site | https://yohei1126.github.io/lerobot-so101-pick-and-place/ | https://yohei1126.github.io/lerobot-so101-pick-and-place/ja/ |

Full list: see the docs index in each language.

## Repo layout

```text
.
├── configs/contract.yaml   # topics, tensor shapes, model I/O (SSOT)
├── docs/                   # bilingual procedures (*.en.md / *.ja.md)
├── scripts/                # bag, convert, E2E, sim eval, pipeline, real runners
├── deploy/udev/            # Linux udev examples
├── port_pick_align/        # Python package (dataset, ACT, MuJoCo, deploy)
├── ros2_ws/                # ROS 2 Humble mock inference / Rerun
├── mkdocs.yml              # GitHub Pages (Material + i18n)
└── tests / port_pick_align/tests
```

## Models

- **ACT**: primary imitation policy for sim closed-loop eval and real trials (`port_pick_align` training entrypoints).  
- **SmolVLA**: fine-tune / real-runner scripts (`scripts/train_smolvla.sh`, `scripts/run_smolvla_real.sh`, deploy docs).

## License

See [LICENSE](LICENSE).
