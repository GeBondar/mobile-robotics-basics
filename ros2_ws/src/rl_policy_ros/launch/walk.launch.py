"""Робот + политика одной командой.

    ros2 launch rl_policy_ros walk.launch.py                        # ЦАПЛЯ-2
    ros2 launch rl_policy_ros walk.launch.py robot:=microduck        # нужен MICRODUCK_RL
    ros2 launch rl_policy_ros walk.launch.py rviz:=true              # + RViz2 с готовым конфигом

Клавиатура запускается отдельно (ей нужен свой терминал):
    ros2 run teleop_twist_keyboard teleop_twist_keyboard
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# Для каждого робота: политики "имя:файл" и мир по умолчанию.
ROBOTS = {
    "tsaplya2": {"policies": ["walk:tsaplya2_walk.onnx"], "world": "tsaplya_aruco.yaml"},
    "microduck": {"policies": ["walk:microduck/alpha_walking.onnx",
                               "stand:microduck/alpha_stand.onnx",
                               "kick_left:microduck/ball_kick_left.onnx",
                               "kick_right:microduck/ball_kick_right.onnx",
                               "roulade:microduck/roulade.onnx"],
                  "world": ""},
}


def nodes(context):
    robot = LaunchConfiguration("robot").perform(context)
    if robot not in ROBOTS:
        raise RuntimeError(f"robot:={robot} — есть только {sorted(ROBOTS)}")
    cfg = ROBOTS[robot]
    world = LaunchConfiguration("world").perform(context)
    world = cfg["world"] if world == "default" else world
    sim = Node(
        package="rl_policy_ros", executable="sim_node", output="screen",
        parameters=[{"robot": robot, "world": world,
                     "viewer": LaunchConfiguration("viewer"),
                     "camera_rate": LaunchConfiguration("camera_rate"),
                     "use_sim_time": True}])
    policy = Node(
        package="rl_policy_ros", executable="policy_node", output="screen",
        parameters=[{"robot": robot, "policies": cfg["policies"],
                     "cmd_timeout_s": LaunchConfiguration("cmd_timeout_s"),
                     "use_sim_time": True}])
    out = [sim, TimerAction(period=3.0, actions=[policy])]   # подвес держит робота, пока политика грузится
    if LaunchConfiguration("rviz").perform(context).lower() == "true":
        rviz_cfg = os.path.join(get_package_share_directory("rl_policy_ros"), "rviz", "lesson15.rviz")
        out.append(Node(package="rviz2", executable="rviz2", arguments=["-d", rviz_cfg],
                        parameters=[{"use_sim_time": True}], output="log"))
    return out


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("robot", default_value="tsaplya2"),
        DeclareLaunchArgument("world", default_value="default"),
        DeclareLaunchArgument("viewer", default_value="true"),
        DeclareLaunchArgument("camera_rate", default_value="15.0"),
        DeclareLaunchArgument("rviz", default_value="false"),
        # teleop_twist_keyboard шлёт команду только при нажатии клавиши, поэтому
        # для ручного управления deadman отключён; автономным нодам — 0.5 с.
        DeclareLaunchArgument("cmd_timeout_s", default_value="1000.0"),
        OpaqueFunction(function=nodes),
    ])
