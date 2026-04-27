#!/usr/bin/env python3
import argparse

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from turtle_action.action import MoveTo


class MoveToActionClient(Node):
    def __init__(self):
        super().__init__('move_to_action_client')
        self.action_client = ActionClient(self, MoveTo, 'move_to')

    def send_goal(self, target_x, target_y, target_theta, speed):
        goal = MoveTo.Goal()
        goal.target_x = target_x
        goal.target_y = target_y
        goal.target_theta = target_theta
        goal.speed = speed
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
        result_future.add_done_callback(self.result_callback)

    def result_callback(self, future):
        result = future.result().result
        self.get_logger().info(
            f'Result: success={result.success}, final_distance={result.final_distance:.2f}'
        )
        rclpy.shutdown()

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        self.get_logger().info(
            f'Feedback: x={feedback.current_x:.2f}, y={feedback.current_y:.2f}, '
            f'theta={feedback.current_theta:.2f}, left={feedback.distance_left:.2f}'
        )


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('target_x', type=float, nargs='?', default=8.0)
    parser.add_argument('target_y', type=float, nargs='?', default=2.0)
    parser.add_argument('target_theta', type=float, nargs='?', default=1.57)
    parser.add_argument('speed', type=float, nargs='?', default=1.0)
    parsed_args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = MoveToActionClient()
    node.send_goal(
        parsed_args.target_x,
        parsed_args.target_y,
        parsed_args.target_theta,
        parsed_args.speed,
    )
    rclpy.spin(node)


if __name__ == '__main__':
    main()
