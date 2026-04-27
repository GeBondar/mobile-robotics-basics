import rclpy
from rclpy.node import Node
from turtle_pose_interfaces.srv import GetPose
from turtlesim.msg import Pose


class PoseServer(Node):
    def __init__(self):
        super().__init__('pose_server')
        self.current_pose = None
        self.subscription = self.create_subscription(
            Pose,
            '/turtle1/pose',
            self.pose_callback,
            10,
        )
        self.service = self.create_service(GetPose, 'get_pose', self.get_pose_callback)
        self.get_logger().info('Service /get_pose is ready')

    def pose_callback(self, msg):
        self.current_pose = msg

    def get_pose_callback(self, request, response):
        del request
        if self.current_pose is None:
            self.get_logger().warn('Pose is not known yet; returning zeros')
            response.x = 0.0
            response.y = 0.0
            response.theta = 0.0
            return response

        response.x = self.current_pose.x
        response.y = self.current_pose.y
        response.theta = self.current_pose.theta
        return response


def main(args=None):
    rclpy.init(args=args)
    node = PoseServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
