#!/usr/bin/env python3
"""Нода политики: топики робота -> наблюдение -> ONNX -> /joint_commands.

    ros2 run rl_policy_ros policy_node --ros-args -p robot:=tsaplya2 \
        -p policies:="['walk:tsaplya2_walk.onnx']"

Параметр policies — список "имя:файл". Имена со смыслом для режима auto:
  walk  — когда команда скорости ненулевая;
  stand — когда команда нулевая (если такой политики нет, стоит walk с нулём).
Остальные политики (kick_left, roulade, ...) включаются сервисом /set_policy
на время episode_s и возвращают управление в auto.

Подписки:  /joint_states /imu/data /odom /cmd_vel /head_cmd /target_point
Публикует: /joint_commands, /policy/obs (наблюдение — для сверки по bag),
           /policy/active (имя активной политики), /policy/fallen
Сервис:    /set_policy (rl_policy_interfaces/SetPolicy)
"""
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import rclpy
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PointStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rl_policy_interfaces.srv import SetPolicy
from sensor_msgs.msg import Imu, JointState
from std_msgs.msg import Bool, Float32MultiArray, Float64MultiArray, String

from .contracts import Command, RobotState, make_contract, read_onnx_meta

# Эпизодические политики Microduck: длительность из policies/manifest.json приложения Б.
EPISODE_S = {"kick_left": 0.5, "kick_right": 0.5, "roulade": 1.0, "ground_pick": 2.8}


class PolicyNode(Node):
    def __init__(self):
        super().__init__("policy_node")
        p = self.declare_parameter
        p("robot", "tsaplya2")
        p("policies", ["walk:tsaplya2_walk.onnx"])
        p("policy_dir", "")              # пусто — policies/ пакета
        p("stale_s", 0.1)                # данные старше — сторож
        p("cmd_timeout_s", 0.5)          # /cmd_vel старше — команда в ноль (deadman)
        p("switch_threshold", 0.05)      # |cmd| ниже — auto выбирает stand
        p("stop_on_fall", True)
        g = lambda n: self.get_parameter(n).value  # noqa: E731

        self.c = make_contract(g("robot"))
        pdir = Path(g("policy_dir") or Path(get_package_share_directory("rl_policy_ros")) / "policies")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        self.sessions = {}
        for item in g("policies"):
            name, fname = item.split(":", 1)
            path = Path(fname) if Path(fname).is_absolute() else pdir / fname
            sess = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
            i, o = sess.get_inputs()[0], sess.get_outputs()[0]
            if list(i.shape) != [1, self.c.OBS_DIM] or list(o.shape) != [1, self.c.ACT_DIM]:
                raise RuntimeError(f"{path.name}: {i.shape}->{o.shape}, контракт {self.c.name} "
                                   f"ждёт [1,{self.c.OBS_DIM}]->[1,{self.c.ACT_DIM}]")
            meta = read_onnx_meta(sess)
            if meta.get("robot", self.c.name) != self.c.name:
                raise RuntimeError(f"{path.name} обучена для '{meta['robot']}', а не '{self.c.name}'")
            self.sessions[name] = (sess, i.name)
            self.get_logger().info(f"политика {name}: {path.name} {i.shape}->{o.shape} {meta}")
        self.auto = True
        self.active = "walk" if "walk" in self.sessions else next(iter(self.sessions))
        self.episode_end = None

        self.stale_s = g("stale_s")
        self.cmd_timeout = g("cmd_timeout_s")
        self.switch_thr = g("switch_threshold")
        self.stop_on_fall = g("stop_on_fall")
        self.js = self.imu = self.odom = None
        self.t_js = self.t_imu = self.t_odom = -1.0
        self.cmd, self.t_cmd = Command(), -1.0
        self.idx = None
        self.fallen = False
        self.need_reset = True

        sd = qos_profile_sensor_data
        self.create_subscription(JointState, "joint_states", self._on_js, sd)
        self.create_subscription(Imu, "imu/data", self._on_imu, sd)
        self.create_subscription(Odometry, "odom", self._on_odom, sd)
        self.create_subscription(Twist, "cmd_vel", self._on_cmd, 10)
        self.create_subscription(Float64MultiArray, "head_cmd", self._on_head, 10)
        self.create_subscription(PointStamped, "target_point", self._on_target, 10)
        self.pub_cmd = self.create_publisher(Float64MultiArray, "joint_commands", sd)
        self.pub_obs = self.create_publisher(Float32MultiArray, "policy/obs", 10)
        self.pub_active = self.create_publisher(String, "policy/active", 10)
        self.pub_fallen = self.create_publisher(Bool, "policy/fallen", 10)
        self.create_service(SetPolicy, "set_policy", self._on_set_policy)

        self.period = 1.0 / self.c.CONTROL_HZ
        self.t_prev = None
        self.lat_us = []
        self.periods = []
        self.create_timer(self.period, self._tick)

    def now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    # --- входы ---------------------------------------------------------------
    def _on_js(self, m):
        if self.idx is None:
            missing = [n for n in self.c.JOINTS if n not in m.name]
            if missing:
                self.get_logger().error(f"в joint_states нет суставов {missing}", throttle_duration_sec=2.0)
                return
            self.idx = [list(m.name).index(n) for n in self.c.JOINTS]
        self.js, self.t_js = m, self.now()

    def _on_imu(self, m):
        self.imu, self.t_imu = m, self.now()

    def _on_odom(self, m):
        self.odom, self.t_odom = m, self.now()

    def _on_cmd(self, m):
        self.cmd.vx, self.cmd.vy, self.cmd.wz = m.linear.x, m.linear.y, m.angular.z
        self.t_cmd = self.now()

    def _on_head(self, m):
        if len(m.data) == 4:
            self.cmd.head = np.asarray(m.data, dtype=np.float64)

    def _on_target(self, m):
        self.cmd.target = np.array([m.point.x, m.point.y, m.point.z])

    def _on_set_policy(self, req, resp):
        if req.name == "auto":
            self.auto, self.episode_end = True, None
        elif req.name in self.sessions:
            self.auto = False
            self._switch(req.name)
            dur = EPISODE_S.get(req.name)
            self.episode_end = self.now() + dur if dur else None
        else:
            resp.success, resp.active = False, self.active
            resp.message = f"нет политики '{req.name}', есть: auto, {', '.join(self.sessions)}"
            return resp
        if self.fallen:
            self.fallen, self.need_reset = False, True
        resp.success, resp.active = True, self.active
        resp.message = "ok"
        return resp

    def _switch(self, name):
        if name != self.active:
            self.get_logger().info(f"политика: {self.active} -> {name}")
            self.active = name
            self.need_reset = True

    # --- такт управления --------------------------------------------------------
    def _state(self):
        js = self.js
        q = np.array([js.position[i] for i in self.idx]) if js else np.zeros(0)
        dq = np.array([js.velocity[i] for i in self.idx]) if js else np.zeros(0)
        o, w = self.imu.orientation, self.imu.angular_velocity
        st = RobotState(q=q, dq=dq, quat=np.array([o.w, o.x, o.y, o.z]),
                        gyro=np.array([w.x, w.y, w.z]))
        if self.odom is not None:
            pp, tw = self.odom.pose.pose.position, self.odom.twist.twist.linear
            st.pos = np.array([pp.x, pp.y, pp.z])
            st.vel_body = np.array([tw.x, tw.y, tw.z])
        return st

    def _tick(self):
        now = self.now()
        if self.t_prev is not None:
            self.periods.append(now - self.t_prev)
            if now - self.t_prev > 1.5 * self.period:
                self.get_logger().warn(f"период {1e3 * (now - self.t_prev):.1f} мс вместо "
                                       f"{1e3 * self.period:.1f}", throttle_duration_sec=2.0)
        self.t_prev = now
        need_js = self.c.USES_JOINT_STATES
        ages = [now - self.t_imu, now - self.t_odom] + ([now - self.t_js] if need_js else [])
        if self.imu is None or self.odom is None or (need_js and self.js is None) or max(ages) > self.stale_s:
            if self.imu is not None and (not need_js or self.js is not None):
                self._send(self.c.safe_command(self._state()))
            self.get_logger().warn("данные устарели или не пришли — безопасная команда",
                                   throttle_duration_sec=2.0)
            return
        st = self._state()
        if not self.fallen and self.c.fallen(st) and self.stop_on_fall:
            # Одна безопасная команда — и тишина: упавшую политику не гоняют дальше,
            # а молчание не снимет подвес симулятора после /sim/reset.
            self.get_logger().error("робот упал — политика остановлена; /sim/reset, затем /set_policy auto")
            self._send(self.c.safe_command(st))
            self.fallen = True
        self.pub_fallen.publish(Bool(data=self.fallen))
        if self.fallen:
            return

        cmd = self.cmd
        if now - self.t_cmd > self.cmd_timeout:            # deadman: нет свежей команды — стоим
            cmd = Command(head=self.cmd.head, target=self.cmd.target)
        if self.episode_end is not None and now >= self.episode_end:
            self.auto, self.episode_end = True, None
        if self.auto:
            moving = abs(cmd.vx) + abs(cmd.vy) + abs(cmd.wz) > self.switch_thr
            want = "walk" if moving or "stand" not in self.sessions else "stand"
            self._switch(want)
        if self.episode_end is not None:                    # трюки Microduck идут с нулевой командой
            cmd = Command()
        if self.need_reset:
            self.c.reset(st, cmd)
            self.need_reset = False

        obs = self.c.observe(st, cmd)
        sess, in_name = self.sessions[self.active]
        t0 = time.perf_counter()
        action = sess.run(None, {in_name: obs.reshape(1, -1)})[0][0]
        self.lat_us.append((time.perf_counter() - t0) * 1e6)
        self._send(self.c.act(action))
        self.pub_obs.publish(Float32MultiArray(data=obs.tolist()))
        self.pub_active.publish(String(data=("auto:" if self.auto else "") + self.active))
        if len(self.lat_us) >= 500:
            lat = np.asarray(self.lat_us)
            per = np.asarray(self.periods) * 1e3
            self.get_logger().info(
                f"инференс {self.active}: медиана {np.median(lat):.0f} мкс, p99 "
                f"{np.percentile(lat, 99):.0f} мкс | период: медиана {np.median(per):.1f} мс, "
                f"p99 {np.percentile(per, 99):.1f}, максимум {per.max():.1f}")
            self.lat_us.clear()
            self.periods.clear()

    def _send(self, targets):
        self.pub_cmd.publish(Float64MultiArray(data=[float(v) for v in targets]))


def main():
    rclpy.init()
    node = PolicyNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
