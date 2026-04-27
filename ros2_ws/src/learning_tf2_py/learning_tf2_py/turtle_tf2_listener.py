import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from tf2_ros import TransformException
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener
from turtlesim.srv import Spawn


class FrameListener(Node):
    def __init__(self):
        super().__init__('turtle_tf2_frame_listener')
        self.target_frame = self.declare_parameter(
            'target_frame',
            'turtle1',
        ).get_parameter_value().string_value
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.spawner = self.create_client(Spawn, 'spawn')
        self.spawn_future = None
        self.turtle_spawned = False
        self.publisher = self.create_publisher(Twist, 'turtle2/cmd_vel', 1)
        self.timer = self.create_timer(1.0, self.on_timer)

    def on_timer(self):
        if not self.turtle_spawned:
            self.spawn_turtle_once()
            return

        try:
            transform = self.tf_buffer.lookup_transform(
                'turtle2',
                self.target_frame,
                rclpy.time.Time(),
            )
        except TransformException as ex:
            self.get_logger().info(f'Could not transform turtle2 to {self.target_frame}: {ex}')
            return

        msg = Twist()
        msg.angular.z = 4.0 * math.atan2(
            transform.transform.translation.y,
            transform.transform.translation.x,
        )
        msg.linear.x = 0.5 * math.hypot(
            transform.transform.translation.x,
            transform.transform.translation.y,
        )
        self.publisher.publish(msg)

    def spawn_turtle_once(self):
        if not self.spawner.service_is_ready():
            self.spawner.wait_for_service(timeout_sec=0.1)
            return

        if self.spawn_future is None:
            request = Spawn.Request()
            request.name = 'turtle2'
            request.x = 4.0
            request.y = 2.0
            request.theta = 0.0
            self.spawn_future = self.spawner.call_async(request)
            return

        if self.spawn_future.done():
            self.turtle_spawned = True
            self.get_logger().info('Spawned turtle2')


def main(args=None):
    rclpy.init(args=args)
    node = FrameListener()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
