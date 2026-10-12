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
        ("share/" + package_name + "/config/worlds", glob("config/worlds/*.yaml")),
        ("share/" + package_name + "/models", glob("models/*.xml")),
        ("share/" + package_name + "/policies", glob("policies/*.onnx") + glob("policies/*.json")),
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
        ],
    },
)
