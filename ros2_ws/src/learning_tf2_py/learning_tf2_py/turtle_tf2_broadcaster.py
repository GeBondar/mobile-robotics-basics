import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros import TransformBroadcaster
from turtlesim.msg import Pose

from learning_tf2_py.quaternion import quaternion_from_euler


class FramePublisher(Node):
    def __init__(self):
        super().__init__('turtle_tf2_frame_publisher')
        self.turtlename = self.declare_parameter(
            'turtlename',
            'turtle1',
        ).get_parameter_value().string_value
        self.broadcaster = TransformBroadcaster(self)
        self.subscription = self.create_subscription(
            Pose,
            f'/{self.turtlename}/pose',
            self.handle_turtle_pose,
            1,
        )

    def handle_turtle_pose(self, msg):
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = 'world'
        transform.child_frame_id = self.turtlename
        transform.transform.translation.x = msg.x
        transform.transform.translation.y = msg.y
        transform.transform.translation.z = 0.0
        qx, qy, qz, qw = quaternion_from_euler(0.0, 0.0, msg.theta)
        transform.transform.rotation.x = qx
        transform.transform.rotation.y = qy
        transform.transform.rotation.z = qz
        transform.transform.rotation.w = qw
        self.broadcaster.sendTransform(transform)


def main(args=None):
    rclpy.init(args=args)
    node = FramePublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
