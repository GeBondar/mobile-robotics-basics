import argparse

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster

from learning_tf2_py.quaternion import quaternion_from_euler


class StaticFramePublisher(Node):
    def __init__(self, child_frame, x, y, z, roll, pitch, yaw):
        super().__init__('static_turtle_tf2_broadcaster')
        self.broadcaster = StaticTransformBroadcaster(self)
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = 'world'
        transform.child_frame_id = child_frame
        transform.transform.translation.x = x
        transform.transform.translation.y = y
        transform.transform.translation.z = z
        qx, qy, qz, qw = quaternion_from_euler(roll, pitch, yaw)
        transform.transform.rotation.x = qx
        transform.transform.rotation.y = qy
        transform.transform.rotation.z = qz
        transform.transform.rotation.w = qw
        self.broadcaster.sendTransform(transform)


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('child_frame', nargs='?', default='mystaticturtle')
    parser.add_argument('x', type=float, nargs='?', default=0.0)
    parser.add_argument('y', type=float, nargs='?', default=0.0)
    parser.add_argument('z', type=float, nargs='?', default=1.0)
    parser.add_argument('roll', type=float, nargs='?', default=0.0)
    parser.add_argument('pitch', type=float, nargs='?', default=0.0)
    parser.add_argument('yaw', type=float, nargs='?', default=0.0)
    parsed_args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = StaticFramePublisher(
        parsed_args.child_frame,
        parsed_args.x,
        parsed_args.y,
        parsed_args.z,
        parsed_args.roll,
        parsed_args.pitch,
        parsed_args.yaw,
    )
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
