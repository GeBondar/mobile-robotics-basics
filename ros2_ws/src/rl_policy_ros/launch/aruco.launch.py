"""Сценарий «подойти к ArUco-маркеру»: робот, политика, детектор, сервер действия.

    ros2 launch rl_policy_ros aruco.launch.py                 # ЦАПЛЯ-2, окно MuJoCo
    ros2 launch rl_policy_ros aruco.launch.py rviz:=true

Цель отправляется отдельно:
    ros2 action send_goal /approach_target rl_policy_interfaces/action/ApproachTarget \
        "{label: aruco_0, stop_distance: 0.8, timeout: 60}" --feedback
или обход всех маркеров:
    ros2 run rl_policy_ros approach_client --ros-args -p use_sim_time:=true \
        -p labels:="['aruco_0','aruco_1','aruco_2','aruco_3']"
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# Сторона чёрного квадрата маркера в мире робота — должна совпадать с YAML мира.
MARKER_SIZE = {"tsaplya2": 0.30, "microduck": 0.10}
# Регулятор подхода под возможности политики.
APPROACH = {
    "tsaplya2": {"v_max": 0.4, "v_min": 0.0, "wz_max": 0.5, "search_wz": 0.4},
    # у Microduck ниже 0.3 м/с политика стоит на месте (мёртвая зона, см. статью)
    "microduck": {"v_max": 0.3, "v_min": 0.3, "wz_max": 0.6, "search_wz": 0.5},
}


def nodes(context):
    robot = LaunchConfiguration("robot").perform(context)
    walk = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory("rl_policy_ros"), "launch", "walk.launch.py")),
        launch_arguments={"robot": robot, "world": LaunchConfiguration("world"),
                          "viewer": LaunchConfiguration("viewer"),
                          "rviz": LaunchConfiguration("rviz"),
                          "camera_rate": "15.0", "cmd_timeout_s": "0.5"}.items())
    det = Node(package="rl_policy_ros", executable="aruco_detector", output="screen",
               parameters=[{"marker_size": MARKER_SIZE[robot], "use_sim_time": True}])
    srv = Node(package="rl_policy_ros", executable="approach_server", output="screen",
               parameters=[{**APPROACH[robot], "use_sim_time": True}])
    return [walk, det, srv]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("robot", default_value="tsaplya2"),
        DeclareLaunchArgument("world", default_value="default"),
        DeclareLaunchArgument("viewer", default_value="true"),
        DeclareLaunchArgument("rviz", default_value="false"),
        OpaqueFunction(function=nodes),
    ])
