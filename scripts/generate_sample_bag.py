#!/usr/bin/env python3
"""Generate a short rosbag2 fixture matching configs/contract.yaml.

Intended to run inside the ROS 2 Humble Docker image:

    docker compose -f docker/docker-compose.yml run --rm generate-bag
"""

from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "configs" / "contract.yaml"
OUTPUT_DIR = REPO_ROOT / "python" / "tests" / "fixtures" / "sample_bag"
# Keep short so the committed fixture stays under GitHub's soft size limit (~50 MiB).
DURATION_SEC = 0.5


def _require_ros() -> None:
    try:
        import rclpy  # noqa: F401
        import rosbag2_py  # noqa: F401
        from sensor_msgs.msg import Image, JointState  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "ROS 2 Python packages are required (rosbag2_py, sensor_msgs).\n"
            "Run via Docker:\n"
            "  docker compose -f docker/docker-compose.yml run --rm generate-bag\n"
            f"Original error: {exc}"
        ) from exc


def load_contract(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_dummy_image(
    height: int, width: int, channels: int, frame_idx: int, seed: int
) -> np.ndarray:
    """Create a simple BGR image with a moving stripe for visual sanity checks."""
    img = np.zeros((height, width, channels), dtype=np.uint8)
    img[:, :, 0] = (seed * 40) % 256  # B
    img[:, :, 1] = (seed * 80) % 256  # G
    img[:, :, 2] = (seed * 120) % 256  # R
    stripe = (frame_idx * 8) % width
    img[:, stripe : min(stripe + 16, width), :] = 255
    return img


def numpy_to_image_msg(
    img: np.ndarray, stamp_sec: int, stamp_nanosec: int, frame_id: str
):
    from sensor_msgs.msg import Image

    msg = Image()
    msg.header.stamp.sec = stamp_sec
    msg.header.stamp.nanosec = stamp_nanosec
    msg.header.frame_id = frame_id
    msg.height = img.shape[0]
    msg.width = img.shape[1]
    msg.encoding = "bgr8"
    msg.is_bigendian = 0
    msg.step = img.shape[1] * img.shape[2]
    msg.data = img.tobytes()
    return msg


def make_joint_state(
    joint_names: list[str], t: float, stamp_sec: int, stamp_nanosec: int
):
    from sensor_msgs.msg import JointState

    msg = JointState()
    msg.header.stamp.sec = stamp_sec
    msg.header.stamp.nanosec = stamp_nanosec
    msg.header.frame_id = "base_link"
    msg.name = list(joint_names)
    # Small sinusoidal motion so the episode is not static (validator will use this later).
    msg.position = [
        0.1 * math.sin(t * 2.0 * math.pi * 0.5 + i * 0.3)
        for i in range(len(joint_names))
    ]
    msg.velocity = [0.0] * len(joint_names)
    msg.effort = [0.0] * len(joint_names)
    return msg


def write_bag(contract: dict, output_dir: Path) -> None:
    import rosbag2_py
    from rclpy.serialization import serialize_message

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    top = contract["cameras"]["top"]
    wrist = contract["cameras"]["wrist"]
    states = contract["states"]
    joint_names = contract["robot"]["joint_names"]
    fps = int(top["fps"])
    n_frames = int(DURATION_SEC * fps)
    dt_ns = int(1e9 / fps)

    writer = rosbag2_py.SequentialWriter()
    storage_options = rosbag2_py.StorageOptions(
        uri=str(output_dir), storage_id="sqlite3"
    )
    converter_options = rosbag2_py.ConverterOptions(
        input_serialization_format="cdr",
        output_serialization_format="cdr",
    )
    writer.open(storage_options, converter_options)

    topics = [
        (top["topic"], "sensor_msgs/msg/Image"),
        (wrist["topic"], "sensor_msgs/msg/Image"),
        (states["topic"], "sensor_msgs/msg/JointState"),
    ]
    for topic_name, type_name in topics:
        writer.create_topic(
            rosbag2_py.TopicMetadata(
                name=topic_name,
                type=type_name,
                serialization_format="cdr",
            )
        )

    for i in range(n_frames):
        t_ns = i * dt_ns
        stamp_sec = int(t_ns // 1_000_000_000)
        stamp_nanosec = int(t_ns % 1_000_000_000)
        t_sec = t_ns * 1e-9

        top_img = make_dummy_image(
            top["height"], top["width"], top["channels"], i, seed=1
        )
        wrist_img = make_dummy_image(
            wrist["height"], wrist["width"], wrist["channels"], i, seed=2
        )
        top_msg = numpy_to_image_msg(top_img, stamp_sec, stamp_nanosec, "camera_top")
        wrist_msg = numpy_to_image_msg(
            wrist_img, stamp_sec, stamp_nanosec, "camera_wrist"
        )
        js_msg = make_joint_state(joint_names, t_sec, stamp_sec, stamp_nanosec)

        # Use matching timestamps for a "healthy" fixture (Task 3 will add offset variants).
        writer.write(top["topic"], serialize_message(top_msg), t_ns)
        writer.write(wrist["topic"], serialize_message(wrist_msg), t_ns)
        writer.write(states["topic"], serialize_message(js_msg), t_ns)

    del writer
    print(f"Wrote rosbag2 fixture: {output_dir}")
    print(f"  frames={n_frames}, fps={fps}, duration_s={DURATION_SEC}")
    print(f"  topics={[t[0] for t in topics]}")
    print(f"  joints={joint_names}")


def main() -> int:
    _require_ros()
    if not CONTRACT_PATH.is_file():
        print(f"Contract not found: {CONTRACT_PATH}", file=sys.stderr)
        return 1
    contract = load_contract(CONTRACT_PATH)
    write_bag(contract, OUTPUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
