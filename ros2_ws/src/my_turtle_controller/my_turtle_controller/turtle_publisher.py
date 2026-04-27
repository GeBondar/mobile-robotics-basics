import argparse
import math
import random

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


class TurtlePublisher(Node):
    def __init__(self, mode='circle'):
        super().__init__('turtle_publisher')
        self.publisher = self.create_publisher(Twist, '/turtle1/cmd_vel', 10)
        self.timer = self.create_timer(0.1, self.timer_callback)
        self.mode = mode
        self.side_counter = 0
        self.step_counter = 0
        self.last_linear = 0.0
        self.last_angular = 0.0
        self.get_logger().info(f'turtle_publisher started in {self.mode} mode')

    def timer_callback(self):
        msg = Twist()
        if self.mode == 'circle':
            self.move_circle(msg)
        elif self.mode == 'square':
            self.move_square(msg)
        elif self.mode == 'spiral':
            self.move_spiral(msg)
        elif self.mode == 'random':
            self.move_random(msg)
        else:
            self.get_logger().warn(f'Unknown mode: {self.mode}')
            return

        self.publisher.publish(msg)
        self.step_counter += 1

    @staticmethod
    def move_circle(msg):
        msg.linear.x = 2.0
        msg.angular.z = 1.0

    def move_square(self, msg):
        steps_per_side = 20
        turn_steps = 10
        if self.side_counter < steps_per_side:
            msg.linear.x = 1.0
            msg.angular.z = 0.0
        elif self.side_counter < steps_per_side + turn_steps:
            msg.linear.x = 0.0
            msg.angular.z = math.pi / 2.0
        else:
            self.side_counter = -1
        self.side_counter += 1

    def move_spiral(self, msg):
        t = self.step_counter * 0.1
        msg.linear.x = 1.0 + 0.1 * t
        msg.angular.z = 2.0 / (1.0 + 0.1 * t)

    def move_random(self, msg):
        if self.step_counter % 10 == 0:
            self.last_linear = random.uniform(0.5, 2.0)
            self.last_angular = random.uniform(-1.5, 1.5)
        msg.linear.x = self.last_linear
        msg.angular.z = self.last_angular


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--mode',
        default='circle',
        choices=['circle', 'square', 'spiral', 'random'],
    )
    parsed_args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = TurtlePublisher(parsed_args.mode)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
