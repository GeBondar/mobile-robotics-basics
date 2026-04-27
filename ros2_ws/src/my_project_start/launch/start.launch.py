from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='turtlesim',
            executable='turtlesim_node',
            name='turtlesim',
            output='screen',
        ),
        Node(
            package='my_turtle_controller',
            executable='turtle_publisher',
            name='turtle_publisher',
            output='screen',
        ),
        Node(
            package='my_turtle_controller',
            executable='turtle_subscriber',
            name='turtle_subscriber',
            output='screen',
        ),
        Node(
            package='my_turtle_controller',
            executable='number_publisher',
            name='number_publisher',
            output='screen',
        ),
    ])
