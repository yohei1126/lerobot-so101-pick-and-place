"""Launch mock sensors only (for parallel ros2 bag record in E2E smoke)."""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            Node(
                package="pai_final_pkg",
                executable="mock_sensor_publisher",
                name="mock_sensor_publisher",
                output="screen",
                parameters=[{"rate_hz": 30.0}],
            ),
        ]
    )
