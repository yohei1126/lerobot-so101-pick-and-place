"""Stream camera images, joint state, and predicted action chunks to Rerun."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import rclpy
import yaml
from rclpy.node import Node
from sensor_msgs.msg import Image, JointState
from std_msgs.msg import Float32MultiArray

from pai_final_pkg._paths import repo_root
from pai_final_pkg.image_convert import image_msg_to_bgr

DEFAULT_CONTRACT = repo_root() / "configs" / "contract.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Contract must be a mapping: {path}")
    return data


class RerunVisualizer(Node):
    def __init__(self) -> None:
        super().__init__("rerun_visualizer")
        self.declare_parameter("contract_path", str(DEFAULT_CONTRACT))
        self.declare_parameter("application_id", "port_pick_align")
        self.declare_parameter("spawn", False)
        self.declare_parameter("action_chunk_topic", "/policy/action_chunk")

        contract_path = Path(self.get_parameter("contract_path").get_parameter_value().string_value)
        contract = _load_yaml(contract_path)
        self.joint_names: list[str] = list(contract["robot"]["joint_names"])
        self.chunk_size = int(contract["model"]["chunk_size"])
        self.action_dim = int(contract["model"]["action_dim"])

        top_topic = str(contract["cameras"]["top"]["topic"])
        wrist_topic = str(contract["cameras"]["wrist"]["topic"])
        states_topic = str(contract["states"]["topic"])
        chunk_topic = (
            self.get_parameter("action_chunk_topic").get_parameter_value().string_value
        )
        app_id = self.get_parameter("application_id").get_parameter_value().string_value
        spawn = bool(self.get_parameter("spawn").get_parameter_value().bool_value)

        import rerun as rr

        self.rr = rr
        rr.init(app_id, spawn=spawn)

        self.create_subscription(Image, top_topic, self._on_top, 10)
        self.create_subscription(Image, wrist_topic, self._on_wrist, 10)
        self.create_subscription(JointState, states_topic, self._on_joints, 10)
        self.create_subscription(Float32MultiArray, chunk_topic, self._on_chunk, 10)

        self.get_logger().info(
            f"rerun_visualizer ready app_id={app_id} spawn={spawn} "
            f"listening to cameras/joints/{chunk_topic}"
        )

    def _on_top(self, msg: Image) -> None:
        bgr = image_msg_to_bgr(msg)
        rgb = bgr[:, :, ::-1]
        self.rr.log("cameras/top", self.rr.Image(rgb))

    def _on_wrist(self, msg: Image) -> None:
        bgr = image_msg_to_bgr(msg)
        rgb = bgr[:, :, ::-1]
        self.rr.log("cameras/wrist", self.rr.Image(rgb))

    def _on_joints(self, msg: JointState) -> None:
        names = list(msg.name) if msg.name else self.joint_names
        for i, name in enumerate(names):
            if i >= len(msg.position):
                break
            self.rr.log(f"state/joints/{name}", self.rr.Scalars(float(msg.position[i])))

    def _on_chunk(self, msg: Float32MultiArray) -> None:
        data = np.asarray(msg.data, dtype=np.float32)
        expected = self.chunk_size * self.action_dim
        if data.size != expected:
            self.get_logger().warning(
                f"action_chunk size {data.size} != expected {expected}; skipping"
            )
            return
        chunk = data.reshape(self.chunk_size, self.action_dim)
        for j, name in enumerate(self.joint_names[: self.action_dim]):
            # Log each joint trajectory as a sequence of scalars over chunk index.
            for t in range(self.chunk_size):
                self.rr.set_time("chunk_step", sequence=t)
                self.rr.log(f"policy/action_chunk/{name}", self.rr.Scalars(float(chunk[t, j])))
        self.rr.set_time("chunk_step", sequence=0)
        self.rr.log("policy/action_chunk/tensor", self.rr.Tensor(chunk))


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = RerunVisualizer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
