"""Launch mock sensors + ACT policy (mock) + Rerun visualizer."""

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
            Node(
                package="pai_final_pkg",
                executable="act_policy_node",
                name="act_policy_node",
                output="screen",
                parameters=[
                    {
                        "policy_mode": "mock",
                        "control_hz": 30.0,
                        "log_every_n": 30,
                    }
                ],
            ),
            Node(
                package="pai_final_pkg",
                executable="rerun_visualizer",
                name="rerun_visualizer",
                output="screen",
                parameters=[
                    {
                        "spawn": False,
                        "application_id": "port_pick_align",
                    }
                ],
            ),
        ]
    )
