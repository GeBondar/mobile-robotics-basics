from glob import glob

from setuptools import find_packages, setup

package_name = "rl_policy_ros"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/rviz", glob("rviz/*.rviz")),
        ("share/" + package_name + "/config/worlds", glob("config/worlds/*.yaml")),
        ("share/" + package_name + "/models", glob("models/*.xml")),
        ("share/" + package_name + "/policies", glob("policies/*.onnx") + glob("policies/*.json")),
        ("share/" + package_name + "/policies/microduck",
         glob("policies/microduck/*.onnx") + glob("policies/microduck/*.json")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="course",
    maintainer_email="course@example.com",
    description="RL policies driving MuJoCo robots through ROS 2 (lesson 15).",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "sim_node = rl_policy_ros.sim_node:main",
            "policy_node = rl_policy_ros.policy_node:main",
            "aruco_detector = rl_policy_ros.aruco_detector:main",
            "approach_server = rl_policy_ros.approach_server:main",
            "approach_client = rl_policy_ros.approach_client:main",
            "color_detector = rl_policy_ros.color_detector:main",
            "drone_search = rl_policy_ros.drone_search:main",
            "video_recorder = rl_policy_ros.video_recorder:main",
        ],
    },
)
