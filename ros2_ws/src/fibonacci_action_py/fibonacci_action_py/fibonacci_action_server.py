import time

import rclpy
from custom_action_interfaces.action import Fibonacci
from rclpy.action import ActionServer
from rclpy.node import Node


class FibonacciActionServer(Node):
    def __init__(self):
        super().__init__('fibonacci_action_server')
        self.action_server = ActionServer(self, Fibonacci, 'fibonacci', self.execute_callback)

    def execute_callback(self, goal_handle):
        order = max(0, goal_handle.request.order)
        feedback = Fibonacci.Feedback()
        feedback.partial_sequence = []

        for index in range(order):
            if index == 0:
                feedback.partial_sequence.append(0)
            elif index == 1:
                feedback.partial_sequence.append(1)
            else:
                feedback.partial_sequence.append(
                    feedback.partial_sequence[index - 1] + feedback.partial_sequence[index - 2]
                )
            goal_handle.publish_feedback(feedback)
            time.sleep(0.5)

        goal_handle.succeed()
        result = Fibonacci.Result()
        result.sequence = feedback.partial_sequence
        return result


def main(args=None):
    rclpy.init(args=args)
    node = FibonacciActionServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
