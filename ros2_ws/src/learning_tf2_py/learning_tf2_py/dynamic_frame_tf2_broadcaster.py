import math

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros import TransformBroadcaster


class DynamicFrameBroadcaster(Node):
    def __init__(self):
        super().__init__('dynamic_frame_tf2_broadcaster')
        self.broadcaster = TransformBroadcaster(self)
        self.timer = self.create_timer(0.1, self.broadcast)

    def broadcast(self):
        seconds, nanoseconds = self.get_clock().now().seconds_nanoseconds()
        time_value = seconds + nanoseconds / 1e9
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = 'turtle1'
        transform.child_frame_id = 'carrot1'
        transform.transform.translation.x = 2.0 * math.sin(time_value)
        transform.transform.translation.y = 2.0 * math.cos(time_value)
        transform.transform.translation.z = 0.0
        transform.transform.rotation.w = 1.0
        self.broadcaster.sendTransform(transform)


def main(args=None):
    rclpy.init(args=args)
    node = DynamicFrameBroadcaster()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
