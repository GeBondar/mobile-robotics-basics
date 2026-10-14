"""Сценарий «найти объект в кадре»: дрон, политика зависания, детектор цвета, поиск.

    ros2 launch rl_policy_ros drone_search.launch.py rviz:=true
    ros2 action send_goal /search_target rl_policy_interfaces/action/ApproachTarget \
        "{label: red, stop_distance: 1.0, timeout: 150}" --feedback
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = get_package_share_directory("rl_policy_ros")
    rviz = Node(package="rviz2", executable="rviz2", output="log",
                arguments=["-d", os.path.join(share, "rviz", "lesson15.rviz")],
                parameters=[{"use_sim_time": True}],
                condition=IfCondition(LaunchConfiguration("rviz")))
    return LaunchDescription([
        DeclareLaunchArgument("viewer", default_value="true"),
        DeclareLaunchArgument("rviz", default_value="false"),
        DeclareLaunchArgument("chase_rate", default_value="0.0"),
        DeclareLaunchArgument("lockstep", default_value="true"),
        Node(package="rl_policy_ros", executable="sim_node", output="screen",
             parameters=[{"robot": "quad", "world": "quad_field.yaml",
                          "viewer": LaunchConfiguration("viewer"), "camera_rate": 15.0,
                          "chase_rate": LaunchConfiguration("chase_rate"),
                          "lockstep": LaunchConfiguration("lockstep"),
                          "use_sim_time": True}]),
        TimerAction(period=3.0, actions=[Node(
            package="rl_policy_ros", executable="policy_node", output="screen",
            parameters=[{"robot": "quad", "policies": ["hover:quad_hover.onnx"],
                         "use_sim_time": True}])]),
        Node(package="rl_policy_ros", executable="color_detector", output="screen",
             parameters=[{"use_sim_time": True}]),
        Node(package="rl_policy_ros", executable="drone_search", output="screen",
             parameters=[{"use_sim_time": True}]),
        rviz,
    ])
