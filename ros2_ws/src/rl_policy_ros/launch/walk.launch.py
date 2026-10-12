"""Робот + политика одной командой.

    ros2 launch rl_policy_ros walk.launch.py robot:=tsaplya2 world:=tsaplya_aruco.yaml viewer:=true

Клавиатура запускается отдельно (ей нужен свой терминал):
    ros2 run teleop_twist_keyboard teleop_twist_keyboard
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

DEFAULT_POLICIES = {
    "tsaplya2": "['walk:tsaplya2_walk.onnx']",
}


def generate_launch_description():
    robot = LaunchConfiguration("robot")
    sim = Node(
        package="rl_policy_ros", executable="sim_node", output="screen",
        parameters=[{"robot": robot, "world": LaunchConfiguration("world"),
                     "viewer": LaunchConfiguration("viewer"),
                     "camera_rate": LaunchConfiguration("camera_rate"),
                     "use_sim_time": True}])
    policy = Node(
        package="rl_policy_ros", executable="policy_node", output="screen",
        parameters=[{"robot": robot,
                     "policies": LaunchConfiguration("policies"),
                     "cmd_timeout_s": LaunchConfiguration("cmd_timeout_s"),
                     "use_sim_time": True}])
    return LaunchDescription([
        DeclareLaunchArgument("robot", default_value="tsaplya2"),
        DeclareLaunchArgument("world", default_value="tsaplya_aruco.yaml"),
        DeclareLaunchArgument("viewer", default_value="true"),
        DeclareLaunchArgument("camera_rate", default_value="15.0"),
        DeclareLaunchArgument("policies", default_value=DEFAULT_POLICIES["tsaplya2"]),
        # teleop_twist_keyboard шлёт команду только при нажатии клавиши, поэтому
        # для ручного управления deadman отключён; автономным нодам — 0.5 с.
        DeclareLaunchArgument("cmd_timeout_s", default_value="1000.0"),
        sim,
        TimerAction(period=3.0, actions=[policy]),    # подвес держит робота, пока политика грузится
    ])
