# Development environment setup

Docker owns the ROS 2 runtime (bags, mock inference, Rerun). The host Python virtualenv owns training, dataset conversion, Feetech I/O, and MuJoCo.

## Runtime responsibility split

| Runtime | Scope | Components |
| --- | --- | --- |
| Docker container (`docker/`) | ROS 2 messaging, rosbag2 record/playback, inference mock nodes, Rerun visualization | ROS 2 Humble |
| Host Python virtualenv | Synthetic data generation, ACT training, dataset conversion/quality checks, Feetech I/O, MuJoCo | Python 3.12+ virtualenv (`.venv`) |
| Cloud GPU (optional) | Full-scale ACT training on large episode sets | CUDA-capable compute |

## Single source of truth for the contract

Topic names, image resolution, joint DOF, and model I/O specs are defined in [`configs/contract.yaml`](../configs/contract.yaml). Every component treats this file as the single source of truth.

## Building and starting Docker

On Docker Desktop, Colima, or another container runtime, build the image with:

```bash
# Build the development image (the generate-bag service uses the same image)
docker compose -f docker/docker-compose.yml build dev

# Start an interactive shell
docker compose -f docker/docker-compose.yml run --rm dev
```

For generating the test `sample_bag`, see [dataset.md](dataset.en.md).

## Host Python virtualenv

Create a host-side Python virtualenv and install packages in editable mode (`-e`):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e "port_pick_align/[training,dev]"
```

Depending on the task, install optional extras as needed:

| Extra name | Purpose | Main libraries |
| --- | --- | --- |
| `training` | ACT training and inference | PyTorch, LeRobot, torchvision |
| `feetech` | Serial I/O with real servos | Feetech motor control library |
| `simulation` | Closed-loop evaluation in MuJoCo | MuJoCo, Gymnasium, Rerun |
| `dev` | Development tests and static analysis | pytest, ruff, mypy |
