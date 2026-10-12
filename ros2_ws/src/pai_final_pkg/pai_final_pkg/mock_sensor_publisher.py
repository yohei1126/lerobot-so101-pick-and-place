"""Publish contract-aligned mock camera + joint_states for Task 4 loop smoke."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import rclpy
import yaml
from rclpy.node import Node
from sensor_msgs.msg import Image, JointState

from pai_final_pkg._paths import repo_root

DEFAULT_CONTRACT = repo_root() / "configs" / "contract.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Contract must be a mapping: {path}")
    return data


def make_dummy_image(
    height: int, width: int, channels: int, frame_idx: int, seed: int
) -> np.ndarray:
    img = np.zeros((height, width, channels), dtype=np.uint8)
    img[:, :, 0] = (seed * 40) % 256
    img[:, :, 1] = (seed * 80) % 256
    img[:, :, 2] = (seed * 120) % 256
    stripe = (frame_idx * 8) % width
    img[:, stripe : min(stripe + 16, width), :] = 255
    return img


def numpy_to_image_msg(
    img: np.ndarray, stamp, frame_id: str
) -> Image:
    msg = Image()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.height = int(img.shape[0])
    msg.width = int(img.shape[1])
    msg.encoding = "bgr8"
    msg.is_bigendian = 0
    msg.step = int(img.shape[1] * img.shape[2])
    msg.data = img.tobytes()
    return msg


class MockSensorPublisher(Node):
    def __init__(self) -> None:
        super().__init__("mock_sensor_publisher")
        self.declare_parameter("contract_path", str(DEFAULT_CONTRACT))
        self.declare_parameter("rate_hz", 30.0)

        contract_path = Path(self.get_parameter("contract_path").get_parameter_value().string_value)
        contract = _load_yaml(contract_path)
        self.top = contract["cameras"]["top"]
        self.wrist = contract["cameras"]["wrist"]
        self.joint_names = list(contract["robot"]["joint_names"])
        rate_hz = float(self.get_parameter("rate_hz").get_parameter_value().double_value)

        self.top_pub = self.create_publisher(Image, str(self.top["topic"]), 10)
        self.wrist_pub = self.create_publisher(Image, str(self.wrist["topic"]), 10)
        self.state_pub = self.create_publisher(JointState, str(contract["states"]["topic"]), 10)

        self._frame = 0
        self._t0 = self.get_clock().now()
        period = 1.0 / max(rate_hz, 1.0)
        self.create_timer(period, self._tick)
        self.get_logger().info(f"mock_sensor_publisher at {rate_hz:.1f} Hz")

    def _tick(self) -> None:
        now = self.get_clock().now()
        stamp = now.to_msg()
        elapsed = (now - self._t0).nanoseconds * 1e-9

        top_img = make_dummy_image(
            int(self.top["height"]),
            int(self.top["width"]),
            int(self.top["channels"]),
            self._frame,
            seed=1,
        )
        wrist_img = make_dummy_image(
            int(self.wrist["height"]),
            int(self.wrist["width"]),
            int(self.wrist["channels"]),
            self._frame,
            seed=2,
        )
        self.top_pub.publish(numpy_to_image_msg(top_img, stamp, "camera_top"))
        self.wrist_pub.publish(numpy_to_image_msg(wrist_img, stamp, "camera_wrist"))

        js = JointState()
        js.header.stamp = stamp
        js.header.frame_id = "base_link"
        js.name = list(self.joint_names)
        js.position = [
            0.1 * math.sin(elapsed * 2.0 * math.pi * 0.5 + i * 0.3)
            for i in range(len(self.joint_names))
        ]
        js.velocity = [0.0] * len(self.joint_names)
        js.effort = [0.0] * len(self.joint_names)
        self.state_pub.publish(js)
        self._frame += 1


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = MockSensorPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
