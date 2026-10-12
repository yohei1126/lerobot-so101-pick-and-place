"""ROS 2 ACT policy node: synced cameras + joints → joint commands."""

from __future__ import annotations

import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import rclpy
import yaml
from message_filters import ApproximateTimeSynchronizer, Subscriber
from rclpy.node import Node
from sensor_msgs.msg import Image, JointState
from std_msgs.msg import Float32MultiArray, MultiArrayDimension

from pai_final_pkg._paths import repo_root
from pai_final_pkg.image_convert import image_msg_to_bgr

# Allow importing host package from the mounted workspace (Docker / local).
_WORKSPACE_SRC = repo_root() / "port_pick_align" / "src"
if _WORKSPACE_SRC.is_dir() and str(_WORKSPACE_SRC) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_SRC))

from port_pick_align.training.infer import (  # noqa: E402
    images_bgr_to_batch,
    mock_action_chunk,
    predict_chunk,
)

DEFAULT_CONTRACT = repo_root() / "configs" / "contract.yaml"
DEFAULT_CHECKPOINT = repo_root() / "checkpoints" / "synthetic_act" / "best_model.pt"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Contract must be a mapping: {path}")
    return data


class ActPolicyNode(Node):
    def __init__(self) -> None:
        super().__init__("act_policy_node")
        self.declare_parameter("contract_path", str(DEFAULT_CONTRACT))
        self.declare_parameter("checkpoint_path", str(DEFAULT_CHECKPOINT))
        self.declare_parameter("policy_mode", "mock")
        self.declare_parameter("control_hz", 30.0)
        self.declare_parameter("sync_slop", 0.033)
        self.declare_parameter("sync_queue_size", 10)
        self.declare_parameter("log_every_n", 30)

        contract_path = Path(self.get_parameter("contract_path").get_parameter_value().string_value)
        self.contract = _load_yaml(contract_path)
        self.policy_mode = (
            self.get_parameter("policy_mode").get_parameter_value().string_value.lower()
        )
        self.control_hz = float(
            self.get_parameter("control_hz").get_parameter_value().double_value
        )
        self.log_every_n = int(self.get_parameter("log_every_n").get_parameter_value().integer_value)

        self.joint_names: list[str] = list(self.contract["robot"]["joint_names"])
        self.chunk_size = int(self.contract["model"]["chunk_size"])
        self.action_dim = int(self.contract["model"]["action_dim"])
        top_topic = str(self.contract["cameras"]["top"]["topic"])
        wrist_topic = str(self.contract["cameras"]["wrist"]["topic"])
        states_topic = str(self.contract["states"]["topic"])
        commands_topic = str(self.contract["commands"]["topic"])

        self.policy: Any | None = None
        self.device = "cpu"
        if self.policy_mode == "checkpoint":
            self._load_checkpoint()
        elif self.policy_mode != "mock":
            raise ValueError(f"Unknown policy_mode: {self.policy_mode!r} (use mock|checkpoint)")

        self.cmd_pub = self.create_publisher(JointState, commands_topic, 10)
        self.chunk_pub = self.create_publisher(Float32MultiArray, "/policy/action_chunk", 10)

        self._top_sub = Subscriber(self, Image, top_topic)
        self._wrist_sub = Subscriber(self, Image, wrist_topic)
        self._state_sub = Subscriber(self, JointState, states_topic)
        slop = float(self.get_parameter("sync_slop").get_parameter_value().double_value)
        queue_size = int(self.get_parameter("sync_queue_size").get_parameter_value().integer_value)
        self._sync = ApproximateTimeSynchronizer(
            [self._top_sub, self._wrist_sub, self._state_sub],
            queue_size,
            slop,
        )
        self._sync.registerCallback(self._on_synced)

        self._last_callback_t: float | None = None
        self._dt_history: deque[float] = deque(maxlen=300)
        self._callback_count = 0

        self.get_logger().info(
            f"act_policy_node ready mode={self.policy_mode} "
            f"topics=({top_topic}, {wrist_topic}, {states_topic}) → {commands_topic}"
        )

    def _load_checkpoint(self) -> None:
        from port_pick_align.training.train_act import load_policy_from_checkpoint, resolve_device

        ckpt = Path(self.get_parameter("checkpoint_path").get_parameter_value().string_value)
        if not ckpt.is_file():
            raise FileNotFoundError(f"Checkpoint not found: {ckpt}")
        self.device = resolve_device(None)
        self.policy = load_policy_from_checkpoint(ckpt, self.contract, device=self.device)
        self.get_logger().info(f"Loaded checkpoint {ckpt} on {self.device}")

    def _on_synced(self, top_msg: Image, wrist_msg: Image, state_msg: JointState) -> None:
        now = time.perf_counter()
        if self._last_callback_t is not None:
            self._dt_history.append(now - self._last_callback_t)
        self._last_callback_t = now
        self._callback_count += 1

        top_bgr = image_msg_to_bgr(top_msg)
        wrist_bgr = image_msg_to_bgr(wrist_msg)
        positions = list(state_msg.position)
        if len(positions) < self.action_dim:
            positions = positions + [0.0] * (self.action_dim - len(positions))
        state = np.asarray(positions[: self.action_dim], dtype=np.float32)

        if self.policy_mode == "mock" or self.policy is None:
            chunk = mock_action_chunk(state, self.chunk_size, self.action_dim)
        else:
            batch = images_bgr_to_batch(top_bgr, wrist_bgr, state, device=self.device)
            chunk = predict_chunk(self.policy, batch)

        self._publish_commands(state_msg, chunk)
        self._maybe_log_timing()

    def _publish_commands(self, state_msg: JointState, chunk: np.ndarray) -> None:
        first = chunk[0]
        cmd = JointState()
        cmd.header.stamp = self.get_clock().now().to_msg()
        cmd.header.frame_id = state_msg.header.frame_id
        cmd.name = list(self.joint_names)
        cmd.position = [float(x) for x in first.tolist()]
        cmd.velocity = [0.0] * self.action_dim
        cmd.effort = [0.0] * self.action_dim
        self.cmd_pub.publish(cmd)

        flat = Float32MultiArray()
        flat.layout.dim = [
            MultiArrayDimension(label="chunk", size=self.chunk_size, stride=self.chunk_size * self.action_dim),
            MultiArrayDimension(label="action", size=self.action_dim, stride=self.action_dim),
        ]
        flat.data = [float(x) for x in chunk.reshape(-1).tolist()]
        self.chunk_pub.publish(flat)

    def _maybe_log_timing(self) -> None:
        if self._callback_count % max(self.log_every_n, 1) != 0:
            return
        if not self._dt_history:
            return
        dts = np.asarray(self._dt_history, dtype=np.float64)
        mean_dt = float(dts.mean())
        hz = (1.0 / mean_dt) if mean_dt > 0 else 0.0
        jitter_std = float(dts.std())
        jitter_max = float(np.abs(dts - mean_dt).max())
        target = self.control_hz
        self.get_logger().info(
            f"control_loop hz={hz:.2f} (target={target:.1f}) "
            f"jitter_std_s={jitter_std:.4f} jitter_max_s={jitter_max:.4f} "
            f"n={len(dts)}"
        )


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = ActPolicyNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
