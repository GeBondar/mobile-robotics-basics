import rclpy
from rclpy.node import Node
from turtle_pose_interfaces.srv import GetPose


class PoseClient(Node):
    def __init__(self):
        super().__init__('pose_client')
        self.client = self.create_client(GetPose, 'get_pose')
        while not self.client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for /get_pose...')

    def send_request(self):
        future = self.client.call_async(GetPose.Request())
        rclpy.spin_until_future_complete(self, future)
        return future.result()


def main(args=None):
    rclpy.init(args=args)
    node = PoseClient()
    try:
        response = node.send_request()
        node.get_logger().info(
            f'Pose: x={response.x:.2f}, y={response.y:.2f}, theta={response.theta:.2f}'
        )
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
