import math
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.action import ActionServer, CancelResponse
from rclpy.action.server import ServerGoalHandle
from rclpy.node import Node
from turtle_action.action import MoveTo
from turtlesim.msg import Pose


class MoveToActionServer(Node):
    def __init__(self):
        super().__init__('turtle_action_server')
        self.current_pose = None
        self.pose_sub = self.create_subscription(Pose, '/turtle1/pose', self.pose_callback, 10)
        self.cmd_pub = self.create_publisher(Twist, '/turtle1/cmd_vel', 10)
        self.action_server = ActionServer(
            self,
            MoveTo,
            'move_to',
            self.execute_callback,
            cancel_callback=self.cancel_callback,
        )

    def pose_callback(self, msg):
        self.current_pose = msg

    def execute_callback(self, goal_handle: ServerGoalHandle):
        target_x = goal_handle.request.target_x
        target_y = goal_handle.request.target_y
        target_theta = goal_handle.request.target_theta
        speed = max(0.05, goal_handle.request.speed)
        distance = -1.0

        while rclpy.ok() and goal_handle.is_active:
            if goal_handle.is_cancel_requested:
                self.cmd_pub.publish(Twist())
                goal_handle.canceled()
                return MoveTo.Result(success=False, final_distance=distance)

            if self.current_pose is None:
                time.sleep(0.05)
                continue

            dx = target_x - self.current_pose.x
            dy = target_y - self.current_pose.y
            distance = math.hypot(dx, dy)
            angle_to_target = math.atan2(dy, dx)
            angle_diff = self.normalize_angle(angle_to_target - self.current_pose.theta)

            cmd = Twist()
            if distance > 0.1:
                cmd.linear.x = min(speed, distance)
                cmd.angular.z = 2.0 * angle_diff
            else:
                final_angle_diff = self.normalize_angle(target_theta - self.current_pose.theta)
                if abs(final_angle_diff) > 0.05:
                    cmd.angular.z = 1.5 * final_angle_diff
                else:
                    break
            self.cmd_pub.publish(cmd)

            feedback = MoveTo.Feedback()
            feedback.current_x = self.current_pose.x
            feedback.current_y = self.current_pose.y
            feedback.current_theta = self.current_pose.theta
            feedback.distance_left = distance
            goal_handle.publish_feedback(feedback)
            time.sleep(0.1)

        self.cmd_pub.publish(Twist())
        if goal_handle.is_active:
            goal_handle.succeed()
        return MoveTo.Result(success=True, final_distance=distance)

    def cancel_callback(self, goal_handle):
        del goal_handle
        self.cmd_pub.publish(Twist())
        return CancelResponse.ACCEPT

    @staticmethod
    def normalize_angle(angle):
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle


def main(args=None):
    rclpy.init(args=args)
    node = MoveToActionServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
