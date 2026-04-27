import math

import rclpy
from rclpy.node import Node
from turtlesim.msg import Pose


class TurtleSubscriber(Node):
    def __init__(self):
        super().__init__('turtle_subscriber')
        self.subscription = self.create_subscription(
            Pose,
            '/turtle1/pose',
            self.pose_callback,
            10,
        )
        self.last_pose = None
        self.start_pose = None
        self.total_distance = 0.0
        self.get_logger().info('Waiting for /turtle1/pose messages')

    def pose_callback(self, msg):
        self.get_logger().info(
            f'Pose: x={msg.x:.2f}, y={msg.y:.2f}, theta={msg.theta:.2f}'
        )
        if self.start_pose is None:
            self.start_pose = msg

        if self.last_pose is not None:
            distance = math.hypot(msg.x - self.last_pose.x, msg.y - self.last_pose.y)
            self.total_distance += distance

        self.last_pose = msg


def main(args=None):
    rclpy.init(args=args)
    node = TurtleSubscriber()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
