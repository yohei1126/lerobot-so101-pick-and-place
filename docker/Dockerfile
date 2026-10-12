FROM ros:humble-ros-base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-pip \
        python3-numpy \
        python3-opencv \
        python3-yaml \
        python3-pytest \
        ros-humble-rosbag2 \
        ros-humble-rosbag2-storage-default-plugins \
        ros-humble-rosbag2-py \
        ros-humble-cv-bridge \
        ros-humble-sensor-msgs \
        ros-humble-std-msgs \
        ros-humble-message-filters \
    && rm -rf /var/lib/apt/lists/*

# Host-side Python tooling used inside the container (pytest already via apt).
RUN python3 -m pip install --no-cache-dir \
        "rerun-sdk>=0.16" \
        pyyaml \
        numpy \
        opencv-python-headless \
        pytest

WORKDIR /workspace

# Source ROS 2 for interactive and one-shot commands.
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
