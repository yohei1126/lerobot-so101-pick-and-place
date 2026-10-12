"""rosbag2 → aligned episode → LeRobotDataset conversion (Task 3)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from port_pick_align.contract import load_contract, validate_contract
from port_pick_align.dataset.synthetic import build_features
from port_pick_align.dataset.validator import validate_episode

DEFAULT_REPO_ID = "local/port_pick_align_from_bag"
DEFAULT_TASK = "bag_conversion"


@dataclass
class AlignedFrame:
    t_ns: int
    top: np.ndarray
    wrist: np.ndarray
    state: np.ndarray
    sync_offset_ms: float


@dataclass
class AlignedEpisode:
    frames: list[AlignedFrame]


class ConversionValidationError(ValueError):
    """Raised when an episode fails RobOps quality gates before LeRobot write."""


def _nearest_index(timestamps_ns: np.ndarray, query_ns: int) -> int:
    return int(np.argmin(np.abs(timestamps_ns - query_ns)))


def _header_stamp_ns(msg: Any, fallback_ns: int) -> int:
    """Prefer message header stamp when present (synced publishers); else bag receive time."""
    header = getattr(msg, "header", None)
    if header is None:
        return fallback_ns
    stamp = getattr(header, "stamp", None)
    if stamp is None:
        return fallback_ns
    sec = getattr(stamp, "sec", None)
    nanosec = getattr(stamp, "nanosec", None)
    if sec is None or nanosec is None:
        return fallback_ns
    return int(sec) * 1_000_000_000 + int(nanosec)


def _image_to_rgb_hwc(msg: Any) -> np.ndarray:
    """Decode sensor_msgs/Image-like object to uint8 HWC RGB."""
    height = int(msg.height)
    width = int(msg.width)
    encoding = str(msg.encoding).lower()
    data = np.frombuffer(msg.data, dtype=np.uint8)

    if encoding in {"rgb8", "bgr8"}:
        img = np.asarray(data.reshape(height, width, 3), dtype=np.uint8)
        if encoding == "bgr8":
            return np.ascontiguousarray(img[:, :, ::-1])
        return np.ascontiguousarray(img)

    if encoding in {"mono8", "8uc1"}:
        gray = np.asarray(data.reshape(height, width), dtype=np.uint8)
        return np.stack([gray, gray, gray], axis=-1)

    raise ValueError(f"Unsupported image encoding: {encoding!r}")


def _joint_state_vector(msg: Any, joint_names: list[str]) -> np.ndarray:
    name_to_pos = {str(n): float(p) for n, p in zip(msg.name, msg.position, strict=False)}
    missing = [n for n in joint_names if n not in name_to_pos]
    if missing:
        raise ValueError(f"JointState missing joints: {missing}")
    return np.array([name_to_pos[n] for n in joint_names], dtype=np.float32)


def read_rosbag(
    bag_dir: Path | str,
    contract: dict[str, Any] | None = None,
    contract_path: Path | str | None = None,
) -> dict[str, list[tuple[int, Any]]]:
    """Read contract topics from a rosbag2 directory via rosbags (no ROS runtime)."""
    from rosbags.highlevel import AnyReader
    from rosbags.typesys import Stores, get_typestore

    if contract is None:
        contract = load_contract(contract_path)
    validate_contract(contract)

    bag_path = Path(bag_dir)
    if not bag_path.is_dir():
        raise FileNotFoundError(f"Bag directory not found: {bag_path}")

    top_topic = str(contract["cameras"]["top"]["topic"])
    wrist_topic = str(contract["cameras"]["wrist"]["topic"])
    state_topic = str(contract["states"]["topic"])
    wanted = {top_topic, wrist_topic, state_topic}

    typestore = get_typestore(Stores.ROS2_HUMBLE)
    out: dict[str, list[tuple[int, Any]]] = {t: [] for t in wanted}

    with AnyReader([bag_path], default_typestore=typestore) as reader:
        connections = [c for c in reader.connections if c.topic in wanted]
        missing = wanted - {c.topic for c in connections}
        if missing:
            raise ValueError(f"Bag missing required topics: {sorted(missing)}")

        for connection, timestamp, rawdata in reader.messages(connections=connections):
            msg = reader.deserialize(rawdata, connection.msgtype)
            t_ns = _header_stamp_ns(msg, int(timestamp))
            out[connection.topic].append((t_ns, msg))

    for topic, messages in out.items():
        if not messages:
            raise ValueError(f"No messages on topic {topic}")
        messages.sort(key=lambda item: item[0])

    return out


def align_episode(
    raw: dict[str, list[tuple[int, Any]]],
    contract: dict[str, Any],
) -> AlignedEpisode:
    """Nearest-neighbor align wrist + joints to each top-camera timestamp."""
    top_topic = str(contract["cameras"]["top"]["topic"])
    wrist_topic = str(contract["cameras"]["wrist"]["topic"])
    state_topic = str(contract["states"]["topic"])
    joint_names = list(contract["robot"]["joint_names"])

    top_msgs = raw[top_topic]
    wrist_msgs = raw[wrist_topic]
    state_msgs = raw[state_topic]

    wrist_ts = np.array([t for t, _ in wrist_msgs], dtype=np.int64)
    state_ts = np.array([t for t, _ in state_msgs], dtype=np.int64)

    frames: list[AlignedFrame] = []
    for t_ns, top_msg in top_msgs:
        wi = _nearest_index(wrist_ts, t_ns)
        si = _nearest_index(state_ts, t_ns)
        wrist_t, wrist_msg = wrist_msgs[wi]
        state_t, state_msg = state_msgs[si]

        offset_ms = max(abs(t_ns - wrist_t), abs(t_ns - state_t)) / 1e6
        frames.append(
            AlignedFrame(
                t_ns=int(t_ns),
                top=_image_to_rgb_hwc(top_msg),
                wrist=_image_to_rgb_hwc(wrist_msg),
                state=_joint_state_vector(state_msg, joint_names),
                sync_offset_ms=float(offset_ms),
            )
        )

    return AlignedEpisode(frames=frames)


def convert_bag_to_lerobot(
    bag_dir: Path | str,
    output_dir: Path | str,
    contract: dict[str, Any] | None = None,
    contract_path: Path | str | None = None,
    *,
    repo_id: str = DEFAULT_REPO_ID,
    task: str = DEFAULT_TASK,
    overwrite: bool = True,
    skip_validation: bool = False,
) -> Path:
    """Convert a rosbag2 fixture to a contract-aligned LeRobotDataset."""
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    if contract is None:
        contract = load_contract(contract_path)
    validate_contract(contract)

    raw = read_rosbag(bag_dir, contract=contract)
    episode = align_episode(raw, contract)

    if not skip_validation:
        report = validate_episode(episode, contract)
        if not report.ok:
            details = "; ".join(f"{i.code}: {i.message}" for i in report.issues)
            raise ConversionValidationError(f"Episode failed validation: {details}")

    root = Path(output_dir)
    if root.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {root}")
        shutil.rmtree(root)

    features = build_features(contract)
    fps = int(contract["cameras"]["top"]["fps"])
    ds = LeRobotDataset.create(
        repo_id=repo_id,
        fps=fps,
        features=features,
        root=root,
        robot_type=str(contract["robot"]["name"]),
        use_videos=False,
        image_writer_threads=4,
    )

    frames = episode.frames
    for idx, frame in enumerate(frames):
        next_state = frames[idx + 1].state if idx + 1 < len(frames) else frame.state
        ds.add_frame(
            {
                "observation.images.top": frame.top,
                "observation.images.wrist": frame.wrist,
                "observation.state": frame.state,
                "action": next_state.astype(np.float32, copy=False),
                "task": task,
            }
        )
    ds.save_episode()
    ds.finalize()
    return root
