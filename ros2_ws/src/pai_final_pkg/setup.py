from setuptools import find_packages, setup

package_name = "pai_final_pkg"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="pai-final",
    maintainer_email="omnicampus@example.com",
    description="ROS 2 nodes for Physical AI Applied1 final assignment",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            # Task 4: act_policy_node, rerun_visualizer
        ],
    },
)
