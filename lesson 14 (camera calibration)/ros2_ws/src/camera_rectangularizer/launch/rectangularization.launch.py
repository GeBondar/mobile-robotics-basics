from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description() -> LaunchDescription:
    package_share = get_package_share_directory('camera_rectangularizer')
    config = os.path.join(package_share, 'config', 'rectangularization.yaml')

    return LaunchDescription([
        Node(
            package='camera_rectangularizer',
            executable='rectangularizer',
            name='camera_rectangularizer',
            output='screen',
            parameters=[config],
        ),
    ])
