from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='learning_tf2_py',
            executable='static_turtle_tf2_broadcaster',
            arguments=['mystaticturtle', '0', '0', '1', '0', '0', '0'],
        ),
    ])
