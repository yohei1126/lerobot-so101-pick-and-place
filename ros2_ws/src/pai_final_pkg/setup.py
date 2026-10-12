import os
from glob import glob

from setuptools import find_packages, setup

package_name = "pai_final_pkg"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
    ],
    install_requires=["setuptools", "numpy", "pyyaml"],
    zip_safe=True,
    maintainer="pai-final",
    maintainer_email="omnicampus@example.com",
    description="ROS 2 nodes for Physical AI Applied1 final assignment",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "act_policy_node = pai_final_pkg.act_policy_node:main",
            "rerun_visualizer = pai_final_pkg.rerun_visualizer:main",
            "mock_sensor_publisher = pai_final_pkg.mock_sensor_publisher:main",
        ],
    },
)
