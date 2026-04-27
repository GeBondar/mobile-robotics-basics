import argparse

import rclpy
from custom_action_interfaces.action import Fibonacci
from rclpy.action import ActionClient
from rclpy.node import Node


class FibonacciActionClient(Node):
    def __init__(self):
        super().__init__('fibonacci_action_client')
        self.action_client = ActionClient(self, Fibonacci, 'fibonacci')

    def send_goal(self, order):
        goal = Fibonacci.Goal()
        goal.order = order
        self.action_client.wait_for_server()
        future = self.action_client.send_goal_async(goal, feedback_callback=self.feedback_callback)
        future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected')
            rclpy.shutdown()
            return
        self.get_logger().info('Goal accepted')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        self.get_logger().info(f'Result: {list(result.sequence)}')
        rclpy.shutdown()

    def feedback_callback(self, feedback_msg):
        self.get_logger().info(
            f'Feedback: {list(feedback_msg.feedback.partial_sequence)}'
        )


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('order', type=int, nargs='?', default=10)
    parsed_args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = FibonacciActionClient()
    node.send_goal(parsed_args.order)
    rclpy.spin(node)


if __name__ == '__main__':
    main()
