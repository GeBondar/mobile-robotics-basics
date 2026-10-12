#!/usr/bin/env python3
"""Клиент ApproachTarget: обойти несколько целей по очереди.

    ros2 run rl_policy_ros approach_client --ros-args -p use_sim_time:=true \
        -p labels:="['aruco_0','aruco_1','aruco_2','aruco_3']" -p stop_distance:=0.8
"""
import math

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rl_policy_interfaces.action import ApproachTarget


class ApproachClient(Node):
    def __init__(self):
        super().__init__("approach_client")
        self.declare_parameter("labels", ["aruco_0"])
        self.declare_parameter("stop_distance", 0.8)
        self.declare_parameter("timeout", 90.0)
        self.labels = list(self.get_parameter("labels").value)
        self.stop = float(self.get_parameter("stop_distance").value)
        self.timeout = float(self.get_parameter("timeout").value)
        self.ac = ActionClient(self, ApproachTarget, "approach_target")
        self.last_state = None

    def _fb(self, msg):
        f = msg.feedback
        if f.state != self.last_state:
            self.get_logger().info(f"  {f.state}")
            self.last_state = f.state

    def run(self):
        if not self.ac.wait_for_server(timeout_sec=10.0):
            self.get_logger().error("нет сервера approach_target")
            return 1
        ok_all = True
        for label in self.labels:
            self.last_state = None
            self.get_logger().info(f"цель {label}")
            goal = ApproachTarget.Goal(label=label, stop_distance=self.stop, timeout=self.timeout)
            fut = self.ac.send_goal_async(goal, feedback_callback=self._fb)
            rclpy.spin_until_future_complete(self, fut)
            gh = fut.result()
            if not gh.accepted:
                self.get_logger().error("цель отклонена")
                return 1
            rf = gh.get_result_async()
            rclpy.spin_until_future_complete(self, rf)
            r = rf.result().result
            self.get_logger().info(f"{label}: {'успех' if r.success else 'неудача'} — {r.message}, "
                                   f"{r.elapsed:.1f} с")
            print(f"RESULT {label} success={r.success} final={r.final_distance:.3f} "
                  f"elapsed={r.elapsed:.1f}", flush=True)
            ok_all = ok_all and r.success
            if not math.isfinite(r.final_distance):
                break
        return 0 if ok_all else 2


def main():
    rclpy.init()
    node = ApproachClient()
    code = node.run()
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
