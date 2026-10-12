#!/usr/bin/env python3
"""Сервер действия ApproachTarget: найти цель в кадре и подойти к ней.

    ros2 run rl_policy_ros approach_server --ros-args -p use_sim_time:=true
    ros2 action send_goal /approach_target rl_policy_interfaces/action/ApproachTarget \
        "{label: aruco_0, stop_distance: 0.8, timeout: 60}" --feedback

Это верхний уровень иерархии «классика сверху, RL снизу». Сервер не знает ни про
суставы, ни про политику: он читает /detections (кто угодно — ArUco, цвет, нейросеть)
и пишет /cmd_vel. Шагать по этой команде — дело policy_node.

Логика:
  SEARCH    цели нет в кадре дольше lost_timeout — поворот на месте в сторону,
            где её видели последний раз;
  APPROACH  поворот на цель пропорционально пеленгу, ход вперёд пропорционально
            остатку дистанции; пока пеленг больше align_angle — только поворот;
  DONE      дистанция не больше stop_distance + stop_tol — стоп, успех.
"""
import math
import threading
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rl_policy_interfaces.action import ApproachTarget
from rl_policy_interfaces.msg import Detection


def clip(x, lo, hi):
    return max(lo, min(hi, x))


class ApproachServer(Node):
    def __init__(self):
        super().__init__("approach_server")
        p = self.declare_parameter
        p("rate", 10.0)            # Гц, частота команд /cmd_vel
        p("v_max", 0.4)            # м/с
        p("v_min", 0.0)            # м/с; у Microduck ниже 0.3 политика стоит на месте
        p("wz_max", 0.5)           # рад/с
        p("k_bearing", 1.2)        # рад/с на рад пеленга
        p("k_distance", 0.5)       # м/с на м остатка
        p("align_angle", 0.5)      # рад: пеленг больше — только поворот
        p("search_wz", 0.4)        # рад/с поворота при поиске
        p("lost_timeout", 1.0)     # с без детекции — цель потеряна
        p("stop_tol", 0.1)         # м
        self.cfg = {n: self.get_parameter(n).value for n in
                    ("rate", "v_max", "v_min", "wz_max", "k_bearing", "k_distance",
                     "align_angle", "search_wz", "lost_timeout", "stop_tol")}
        cb = ReentrantCallbackGroup()
        self.last = {}             # label -> (Detection, время получения)
        self.lock = threading.Lock()
        self.create_subscription(Detection, "detections", self._on_det, 20, callback_group=cb)
        self.pub = self.create_publisher(Twist, "cmd_vel", 10)
        self.busy = False
        ActionServer(self, ApproachTarget, "approach_target", self._execute,
                     goal_callback=self._on_goal, cancel_callback=lambda _: CancelResponse.ACCEPT,
                     callback_group=cb)
        self.get_logger().info(f"approach_target готов: {self.cfg}")

    def now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_det(self, m):
        with self.lock:
            self.last[m.label] = (m, self.now())

    def _on_goal(self, goal):
        if self.busy:
            self.get_logger().warn("уже выполняется другая цель — отказ")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _send(self, vx, wz):
        t = Twist()
        t.linear.x, t.angular.z = float(vx), float(wz)
        self.pub.publish(t)

    def _execute(self, gh):
        self.busy = True
        c = self.cfg
        g = gh.request
        stop = g.stop_distance if g.stop_distance > 0 else 0.8
        t0 = self.now()
        search_dir = 1.0
        fb = ApproachTarget.Feedback()
        res = ApproachTarget.Result()
        state, dist, bearing = "SEARCH", -1.0, 0.0
        self.get_logger().info(f"цель {g.label}: остановиться в {stop:.2f} м")
        try:
            while rclpy.ok():
                now = self.now()
                if gh.is_cancel_requested:
                    self._send(0, 0)
                    gh.canceled()
                    self.get_logger().info(f"цель {g.label} отменена, робот остановлен")
                    res.message, res.final_distance, res.elapsed = "отменено", dist, now - t0
                    return res
                if g.timeout > 0 and now - t0 > g.timeout:
                    self._send(0, 0)
                    gh.abort()
                    self.get_logger().warn(f"цель {g.label}: таймаут {g.timeout:.0f} с")
                    res.message, res.final_distance, res.elapsed = "таймаут", dist, now - t0
                    return res
                with self.lock:
                    seen = self.last.get(g.label)
                fresh = seen is not None and now - seen[1] < c["lost_timeout"]
                if not fresh:
                    state = "SEARCH"
                    self._send(0.0, search_dir * c["search_wz"])
                else:
                    det = seen[0]
                    dist, bearing = det.distance, det.bearing
                    search_dir = 1.0 if bearing >= 0 else -1.0
                    remaining = dist - stop
                    if remaining <= c["stop_tol"]:
                        state = "DONE"
                        for _ in range(5):                    # несколько нулей: deadman политики не нужен
                            self._send(0, 0)
                            time.sleep(0.05)
                        gh.succeed()
                        res.success, res.final_distance, res.elapsed = True, dist, now - t0
                        res.message = f"на месте: {dist:.2f} м, пеленг {math.degrees(bearing):+.1f}°"
                        self.get_logger().info(res.message)
                        return res
                    state = "APPROACH"
                    wz = clip(c["k_bearing"] * bearing, -c["wz_max"], c["wz_max"])
                    vx = 0.0
                    if abs(bearing) < c["align_angle"]:
                        vx = clip(c["k_distance"] * remaining, 0.0, c["v_max"])
                        vx *= math.cos(bearing)
                        if vx > 0:
                            vx = max(vx, c["v_min"])
                    self._send(vx, wz)
                fb.state, fb.distance, fb.bearing = state, float(dist), float(bearing)
                gh.publish_feedback(fb)
                time.sleep(1.0 / c["rate"])
        finally:
            self.busy = False
        return res


def main():
    rclpy.init()
    node = ApproachServer()
    ex = MultiThreadedExecutor(num_threads=3)
    ex.add_node(node)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node._send(0, 0)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
