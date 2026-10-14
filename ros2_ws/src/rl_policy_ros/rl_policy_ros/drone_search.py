#!/usr/bin/env python3
"""Сервер действия /search_target: дрон облетает поле, находит цель и зависает над ней.

    ros2 run rl_policy_ros drone_search --ros-args -p use_sim_time:=true
    ros2 action send_goal /search_target rl_policy_interfaces/action/ApproachTarget \
        "{label: red, stop_distance: 1.0, timeout: 120}" --feedback

Тип действия — тот же ApproachTarget, что у шагающих роботов; stop_distance здесь — высота
зависания над целью.

Верхний уровень для политики зависания (трек C1 урока 14): она умеет одно — держать точку
/target_point. Всё остальное — здесь:
  SEARCH    «змейка» над полем на высоте search_alt; полосы через lane_spacing;
  APPROACH  цель в кадре: пиксель -> луч в оптической раме -> через tf в odom ->
            пересечение с полом z = 0. Точку над целью подаём политике;
  DONE      дрон над целью ближе xy_tol по горизонтали дольше hold_s — успех.
"""
import math
import threading
import time

import numpy as np
import rclpy
from geometry_msgs.msg import PointStamped
from nav_msgs.msg import Odometry
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from rl_policy_interfaces.action import ApproachTarget
from rl_policy_interfaces.msg import Detection
from sensor_msgs.msg import CameraInfo
from tf2_ros import Buffer, TransformListener


def quat_to_mat(x, y, z, w):
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


class DroneSearch(Node):
    def __init__(self):
        super().__init__("drone_search")
        p = self.declare_parameter
        p("area", [-5.0, 5.0, -5.0, 5.0])   # xmin, xmax, ymin, ymax поля, м
        p("search_alt", 2.5)                # м
        p("lane_spacing", 3.0)              # м между полосами «змейки»
        p("waypoint_tol", 0.4)              # м: точка маршрута достигнута
        p("xy_tol", 0.15)                   # м: над целью
        p("hold_s", 2.0)                    # с удержания над целью для успеха
        p("lost_timeout", 1.5)              # с
        p("rate", 10.0)
        self.cfg = {n: self.get_parameter(n).value for n in
                    ("area", "search_alt", "lane_spacing", "waypoint_tol", "xy_tol",
                     "hold_s", "lost_timeout", "rate")}
        cb = ReentrantCallbackGroup()
        self.lock = threading.Lock()
        self.odom = None
        self.K = None
        self.last = {}                      # label -> (точка на полу в odom, время)
        self.tf = Buffer()
        TransformListener(self.tf, self)
        sd = qos_profile_sensor_data
        self.create_subscription(Odometry, "odom", self._on_odom, sd, callback_group=cb)
        self.create_subscription(CameraInfo, "camera/camera_info", self._on_info, sd, callback_group=cb)
        self.create_subscription(Detection, "detections", self._on_det, 20, callback_group=cb)
        self.pub = self.create_publisher(PointStamped, "target_point", 10)
        self.pub_found = self.create_publisher(PointStamped, "search/target_on_ground", 10)
        self.busy = False
        ActionServer(self, ApproachTarget, "search_target", self._execute,
                     goal_callback=lambda _: GoalResponse.REJECT if self.busy else GoalResponse.ACCEPT,
                     cancel_callback=lambda _: CancelResponse.ACCEPT, callback_group=cb)
        self.get_logger().info(f"search_target готов: {self.cfg}")

    def now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_odom(self, m):
        self.odom = m

    def _on_info(self, m):
        self.K = np.array(m.k, dtype=np.float64).reshape(3, 3)

    def _on_det(self, m):
        """Пиксель -> точка на полу. tf берётся на момент кадра, а не «сейчас»:
        дрон за 70 мс успевает наклониться, и старая поза камеры даёт другую точку."""
        if self.K is None:
            return
        try:
            tr = self.tf.lookup_transform("odom", m.header.frame_id or "camera_link",
                                          Time.from_msg(m.header.stamp), Duration(seconds=0.1))
        except Exception:                                   # noqa: BLE001 — tf ещё не пришёл
            return
        t, q = tr.transform.translation, tr.transform.rotation
        R = quat_to_mat(q.x, q.y, q.z, q.w)
        ray = R @ np.array([(m.u - self.K[0, 2]) / self.K[0, 0], (m.v - self.K[1, 2]) / self.K[1, 1], 1.0])
        if ray[2] > -1e-3:                                  # луч не смотрит на пол
            return
        s = -t.z / ray[2]
        g = np.array([t.x + s * ray[0], t.y + s * ray[1], 0.0])
        with self.lock:
            self.last[m.label] = (g, self.now())

    def _lawnmower(self):
        x0, x1, y0, y1 = self.cfg["area"]
        pts, ys, k = [], np.arange(y0, y1 + 1e-6, self.cfg["lane_spacing"]), 0
        for y in ys:
            pts += [(x0, y), (x1, y)] if k % 2 == 0 else [(x1, y), (x0, y)]
            k += 1
        return pts

    def _send(self, x, y, z):
        p = PointStamped()
        p.header.frame_id, p.header.stamp = "odom", self.get_clock().now().to_msg()
        p.point.x, p.point.y, p.point.z = float(x), float(y), float(z)
        self.pub.publish(p)

    def _execute(self, gh):
        self.busy = True
        c, g = self.cfg, gh.request
        hover_alt = g.stop_distance if g.stop_distance > 0 else 1.0
        route = self._lawnmower()
        wp, t0, t_over = 0, self.now(), None
        fb, res = ApproachTarget.Feedback(), ApproachTarget.Result()
        self.get_logger().info(f"ищу '{g.label}': {len(route)} точек маршрута на {c['search_alt']} м")
        try:
            while rclpy.ok():
                now = self.now()
                if self.odom is None:
                    time.sleep(0.1)
                    continue
                pos = self.odom.pose.pose.position
                if gh.is_cancel_requested:
                    self._send(pos.x, pos.y, pos.z)
                    gh.canceled()
                    res.message = "отменено"
                    return res
                if g.timeout > 0 and now - t0 > g.timeout:
                    self._send(pos.x, pos.y, pos.z)
                    gh.abort()
                    res.message, res.elapsed = "таймаут", now - t0
                    self.get_logger().warn(f"'{g.label}' не найдена за {g.timeout:.0f} с")
                    return res
                with self.lock:
                    seen = self.last.get(g.label)
                if seen is not None and now - seen[1] < c["lost_timeout"]:
                    gx, gy, _ = seen[0]
                    self._send(gx, gy, hover_alt)
                    d_xy = math.hypot(gx - pos.x, gy - pos.y)
                    fb.state, fb.distance = "APPROACH", float(d_xy)
                    fb.bearing = float(math.atan2(gy - pos.y, gx - pos.x))
                    pt = PointStamped()
                    pt.header.frame_id, pt.header.stamp = "odom", self.get_clock().now().to_msg()
                    pt.point.x, pt.point.y = float(gx), float(gy)
                    self.pub_found.publish(pt)
                    if d_xy < c["xy_tol"] and abs(pos.z - hover_alt) < 0.3:
                        t_over = t_over or now
                        if now - t_over >= c["hold_s"]:
                            gh.succeed()
                            res.success, res.final_distance, res.elapsed = True, d_xy, now - t0
                            res.message = (f"над целью: цель на полу ({gx:.2f}, {gy:.2f}), дрон "
                                           f"({pos.x:.2f}, {pos.y:.2f}, {pos.z:.2f})")
                            self.get_logger().info(res.message)
                            return res
                    else:
                        t_over = None
                else:
                    t_over = None
                    tx, ty = route[wp % len(route)]
                    self._send(tx, ty, c["search_alt"])
                    if math.hypot(tx - pos.x, ty - pos.y) < c["waypoint_tol"]:
                        wp += 1
                    fb.state, fb.distance, fb.bearing = "SEARCH", -1.0, 0.0
                gh.publish_feedback(fb)
                time.sleep(1.0 / c["rate"])
        finally:
            self.busy = False
        return res


def main():
    rclpy.init()
    node = DroneSearch()
    ex = MultiThreadedExecutor(num_threads=3)
    ex.add_node(node)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
