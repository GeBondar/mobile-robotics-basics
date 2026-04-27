import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32


class NumberPublisher(Node):
    def __init__(self):
        super().__init__('number_publisher')
        self.publisher = self.create_publisher(Int32, 'numbers', 10)
        self.counter = 0
        self.timer = self.create_timer(1.0, self.publish_number)

    def publish_number(self):
        msg = Int32()
        msg.data = self.counter
        self.publisher.publish(msg)
        self.get_logger().info(f'Published number: {self.counter}')
        self.counter += 1


def main(args=None):
    rclpy.init(args=args)
    node = NumberPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
