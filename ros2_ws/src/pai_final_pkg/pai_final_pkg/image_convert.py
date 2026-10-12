"""Convert sensor_msgs/Image to numpy without cv_bridge (numpy ABI safe)."""

from __future__ import annotations

import numpy as np
from sensor_msgs.msg import Image


def image_msg_to_bgr(msg: Image) -> np.ndarray:
    """Decode ``bgr8`` / ``rgb8`` Image into contiguous HWC uint8 BGR array."""
    encoding = msg.encoding.lower()
    if encoding not in {"bgr8", "rgb8"}:
        raise ValueError(f"Unsupported image encoding: {msg.encoding!r}")
    expected = int(msg.height) * int(msg.width) * 3
    if len(msg.data) < expected:
        raise ValueError(
            f"Image data too short: got {len(msg.data)} bytes, need >= {expected}"
        )
    arr = np.frombuffer(msg.data, dtype=np.uint8, count=expected).reshape(
        int(msg.height), int(msg.width), 3
    )
    if encoding == "rgb8":
        return arr[:, :, ::-1].copy()
    return np.ascontiguousarray(arr)
