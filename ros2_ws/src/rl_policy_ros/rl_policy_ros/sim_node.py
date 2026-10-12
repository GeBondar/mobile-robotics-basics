#!/usr/bin/env python3
"""Нода-«робот»: MuJoCo в реальном времени за интерфейсом ROS 2.

    ros2 run rl_policy_ros sim_node --ros-args -p robot:=tsaplya2 -p world:=<yaml>

Публикует ровно то, что отдал бы настоящий робот, и ничего сверх:
  /joint_states        sensor_msgs/JointState   позиции и скорости суставов
  /imu/data            sensor_msgs/Imu          ориентация и угловая скорость корпуса
  /odom                nav_msgs/Odometry        поза в мире, скорость в раме корпуса
  /camera/image_raw    sensor_msgs/Image        бортовая камера (+ camera_info)
  /clock               rosgraph_msgs/Clock      время симуляции
Принимает:
  /joint_commands      std_msgs/Float64MultiArray  цели приводов в порядке JointState
                       (как forward_command_controller из ros2_control)
  /sim/push            geometry_msgs/Vector3       толчок корпуса, м/с
  /sim/reset           std_srvs/Trigger            вернуть робота в стартовую позу

Физика крутится в своём потоке и подгоняется под настенные часы; не успевает —
замедляется, а /clock честно показывает время симуляции. Все ноды курса
запускаются с use_sim_time:=true и поэтому замедляются вместе с ней.
"""
import threading
import time
from pathlib import Path

import mujoco
import numpy as np
import rclpy
from ament_index_python.packages import get_package_share_directory
from builtin_interfaces.msg import Time
from geometry_msgs.msg import TransformStamped, Vector3
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image, Imu, JointState
from std_msgs.msg import Float64MultiArray
from std_srvs.srv import Trigger
from tf2_ros import TransformBroadcaster
from visualization_msgs.msg import MarkerArray

from . import scene
from .markers import GeomMarkers

# MuJoCo-камера смотрит вдоль -z, y вверх; оптическая рама ROS — вдоль +z, y вниз.
MJ_TO_OPTICAL = np.diag([1.0, -1.0, -1.0])


def stamp(t: float) -> Time:
    sec = int(t)
    return Time(sec=sec, nanosec=int((t - sec) * 1e9))


class SimNode(Node):
    def __init__(self):
        super().__init__("sim_node")
        p = self.declare_parameter
        p("robot", "tsaplya2")
        p("world", "")                 # YAML с объектами мира; пусто — пустой пол
        p("clock_rate", 200.0)         # Гц /clock: шаг, с которым срабатывают таймеры нод
        p("state_rate", 100.0)         # Гц: JointState и Imu
        p("odom_rate", 50.0)           # Гц: Odometry и tf
        p("camera_rate", 15.0)         # Гц бортовой камеры; 0 — выключить
        p("camera_width", 320)
        p("camera_height", 240)
        p("chase_rate", 0.0)           # Гц внешней камеры для видео; 0 — выключить
        p("chase_width", 640)
        p("chase_height", 480)
        p("markers_rate", 10.0)        # Гц маркеров робота и мира для RViz2; 0 — выключить
        p("real_time_factor", 1.0)
        p("viewer", False)             # окно MuJoCo (нужен дисплей)
        p("spawn", [0.0, 0.0, 0.0])    # x, y, yaw (рад) старта
        # Подвес: до первой команды корпус удерживается в стартовой позе, как
        # двуногого держит кран при включении. Точечные стопы ЦАПЛИ не дают
        # стоять самой — без подвеса она падает раньше, чем стартует политика.
        p("hold_until_command", True)
        g = lambda n: self.get_parameter(n).value  # noqa: E731

        share = Path(get_package_share_directory("rl_policy_ros"))
        self.profile = scene.make_profile(g("robot"), share)
        world = g("world")
        if world and not Path(world).is_absolute():
            world = str(share / "config/worlds" / world)
        self.model, self.cam_name, objs = scene.build_model(self.profile, world or None)
        self.data = mujoco.MjData(self.model)
        self.spawn = [float(v) for v in g("spawn")]
        self.hold_enabled = bool(g("hold_until_command"))
        self._reset_state()
        self.lock = threading.Lock()

        self.clock_dt = 1.0 / g("clock_rate")
        self.state_dt = 1.0 / g("state_rate")
        self.odom_dt = 1.0 / g("odom_rate")
        self.cam_dt = 1.0 / g("camera_rate") if g("camera_rate") > 0 else None
        self.chase_dt = 1.0 / g("chase_rate") if g("chase_rate") > 0 else None
        self.markers_dt = 1.0 / g("markers_rate") if g("markers_rate") > 0 else None
        self.geom_markers = GeomMarkers(self.model) if self.markers_dt else None
        self.cam_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, self.cam_name)
        self.cam_wh = (g("camera_width"), g("camera_height"))
        self.chase_wh = (g("chase_width"), g("chase_height"))
        self.rtf = float(g("real_time_factor"))
        self.want_viewer = bool(g("viewer"))

        jnt_ids = [self.model.actuator_trnid[a, 0] for a in self.act_ids]
        self.qadr = np.array([self.model.jnt_qposadr[j] for j in jnt_ids])
        self.vadr = np.array([self.model.jnt_dofadr[j] for j in jnt_ids])
        self.joint_names = list(self.profile.joints)
        self.is_joint_robot = self.model.actuator_trntype[self.act_ids[0]] == mujoco.mjtTrn.mjTRN_JOINT
        self.pending = None            # последняя пришедшая команда
        self.push = None

        sd = qos_profile_sensor_data
        self.pub_js = self.create_publisher(JointState, "joint_states", sd)
        self.pub_imu = self.create_publisher(Imu, "imu/data", sd)
        self.pub_odom = self.create_publisher(Odometry, "odom", sd)
        self.pub_clock = self.create_publisher(Clock, "/clock", 10)
        self.pub_img = self.create_publisher(Image, "camera/image_raw", sd)
        self.pub_info = self.create_publisher(CameraInfo, "camera/camera_info", sd)
        self.pub_chase = self.create_publisher(Image, "sim/chase/image_raw", sd)
        self.pub_markers = self.create_publisher(MarkerArray, "sim/markers", 1)
        self.tf = TransformBroadcaster(self)
        self.create_subscription(Float64MultiArray, "joint_commands", self._on_cmd, sd)
        self.create_subscription(Vector3, "sim/push", self._on_push, 10)
        self.create_service(Trigger, "sim/reset", self._on_reset)

        self.get_logger().info(
            f"робот {g('robot')}: {len(self.joint_names)} приводов, шаг физики "
            f"{self.model.opt.timestep * 1e3:.1f} мс, камера '{self.cam_name}', объектов мира {len(objs)}")
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    # --- входы ---------------------------------------------------------------
    def _reset_state(self):
        self.bid, self.act_ids = scene.init_state(self.model, self.data, self.profile)
        x, y, yaw = self.spawn
        qa = self.model.jnt_qposadr[self.model.body_jntadr[self.bid]]
        self.data.qpos[qa:qa + 2] = [x, y]
        self.data.qpos[qa + 3:qa + 7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
        mujoco.mj_forward(self.model, self.data)
        self.fqa = qa
        self.fva = self.model.jnt_dofadr[self.model.body_jntadr[self.bid]]
        self.hold_qpos = self.data.qpos[qa:qa + 7].copy()
        self.holding = self.hold_enabled

    def _on_cmd(self, msg):
        if len(msg.data) != len(self.act_ids):
            self.get_logger().error(f"в joint_commands {len(msg.data)} чисел, нужно "
                                    f"{len(self.act_ids)}", throttle_duration_sec=2.0)
            return
        self.pending = np.asarray(msg.data, dtype=np.float64)

    def _on_push(self, msg):
        self.push = np.array([msg.x, msg.y, msg.z])

    def _on_reset(self, req, resp):
        with self.lock:
            self._reset_state()
            self.pending = None
        resp.success, resp.message = True, "робот в стартовой позе"
        return resp

    # --- физика и публикация ---------------------------------------------------
    def _loop(self):
        m, d = self.model, self.data
        cam = mujoco.Renderer(m, self.cam_wh[1], self.cam_wh[0]) if self.cam_dt else None
        chase = mujoco.Renderer(m, self.chase_wh[1], self.chase_wh[0]) if self.chase_dt else None
        mcam = mujoco.MjvCamera()
        mcam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
        mcam.trackbodyid = self.bid
        for k, v in self.profile.chase.items():
            setattr(mcam, k, v)
        viewer = None
        if self.want_viewer:
            from mujoco import viewer as mj_viewer
            viewer = mj_viewer.launch_passive(m, d, show_left_ui=False, show_right_ui=False)
        K = scene.camera_intrinsics(m, self.cam_name, *self.cam_wh) if cam else None
        t_clock = t_state = t_odom = t_cam = t_chase = t_mk = 0.0
        wall0, sim0 = time.perf_counter(), d.time
        n_steps, t_log, t_sim_log, lag = 0, time.perf_counter(), d.time, 0.0
        self.n_slips = 0
        prof = {"lock": 0.0, "step": 0.0, "pub": 0.0, "loop": 0.0}
        t_loop = time.perf_counter()
        while self.running and rclpy.ok():
            t_a = time.perf_counter()
            prof["loop"] = max(prof["loop"], t_a - t_loop)
            t_loop = t_a
            with self.lock:
                t_b = time.perf_counter()
                prof["lock"] = max(prof["lock"], t_b - t_a)
                if self.pending is not None:
                    d.ctrl[self.act_ids] = self.pending
                    if self.holding:
                        self.holding = False
                        self.get_logger().info("первая команда получена — подвес снят")
                if self.holding:
                    d.qpos[self.fqa:self.fqa + 7] = self.hold_qpos
                    d.qvel[self.fva:self.fva + 6] = 0.0
                if self.push is not None:
                    d.qvel[self.fva:self.fva + 3] += self.push
                    self.push = None
                t_c = time.perf_counter()
                mujoco.mj_step(m, d)
                t_d = time.perf_counter()
                prof["step"] = max(prof["step"], t_d - t_c)
                n_steps += 1
                t = d.time
                if t - t_clock >= self.clock_dt - 1e-9:
                    t_clock = t
                    self.pub_clock.publish(Clock(clock=stamp(t)))
                if t - t_state >= self.state_dt - 1e-9:
                    t_state = t
                    with_odom = t - t_odom >= self.odom_dt - 1e-9
                    if with_odom:
                        t_odom = t
                    self._publish_state(t, with_odom)
                    prof["pub"] = max(prof["pub"], time.perf_counter() - t_d)
                frame = chase_frame = geoms = None
                if self.markers_dt and t - t_mk >= self.markers_dt - 1e-9:
                    t_mk = t
                    geoms = (d.geom_xpos.copy(), d.geom_xmat.copy())
                if cam and t - t_cam >= self.cam_dt - 1e-9:
                    t_cam = t
                    cam.update_scene(d, self.cam_name)
                    frame = cam.render()
                if chase and t - t_chase >= self.chase_dt - 1e-9:
                    t_chase = t
                    chase.update_scene(d, mcam)
                    chase_frame = chase.render()
                if viewer is not None and n_steps % 8 == 0:
                    viewer.sync()
            if frame is not None:
                self._publish_image(self.pub_img, frame, t, "camera_link")
                self._publish_info(K, t)
            if chase_frame is not None:
                self._publish_image(self.pub_chase, chase_frame, t, "chase")
            if geoms is not None:
                self.pub_markers.publish(self.geom_markers.build(*geoms, stamp(t)))
            # Подгонка под настенные часы. Отстали — НЕ догоняем: догонка прогнала бы
            # физику пачкой в десятки миллисекунд, пока политика отвечает старой командой.
            # Вместо этого якорь переносится, симуляция просто идёт медленнее.
            ahead = (t - sim0) / self.rtf - (time.perf_counter() - wall0)
            if ahead > 0.001:
                time.sleep(ahead)
            elif ahead < -0.005:
                wall0, sim0 = time.perf_counter(), t
                self.n_slips += 1
            lag = max(lag, -ahead)
            now = time.perf_counter()
            if now - t_log > 10.0:
                rate = (t - t_sim_log) / (now - t_log)
                self.get_logger().info(f"симуляция: x{rate:.2f} реального времени, просадок "
                                       f"{self.n_slips}, худшее отставание {lag * 1e3:.0f} мс | max мс: "
                                       + ", ".join(f"{k} {v * 1e3:.1f}" for k, v in prof.items()))
                prof = dict.fromkeys(prof, 0.0)
                t_log, t_sim_log, lag, self.n_slips = now, t, 0.0, 0
        if viewer is not None:
            viewer.close()

    def _publish_state(self, t, with_odom=True):
        d = self.data
        st = stamp(t)
        qa, va = self.fqa, self.fva
        quat = d.qpos[qa + 3:qa + 7]
        R = np.zeros(9)
        mujoco.mju_quat2Mat(R, quat)
        R = R.reshape(3, 3)

        if self.is_joint_robot:
            js = JointState()
            js.header.stamp = st
            js.name = self.joint_names
            js.position = d.qpos[self.qadr].tolist()
            js.velocity = d.qvel[self.vadr].tolist()
            js.effort = d.actuator_force[self.act_ids].tolist()
            self.pub_js.publish(js)

        imu = Imu()
        imu.header.stamp, imu.header.frame_id = st, "base_link"
        imu.orientation.w, imu.orientation.x, imu.orientation.y, imu.orientation.z = map(float, quat)
        w = d.qvel[va + 3:va + 6]         # у свободного сустава угловая скорость — в раме корпуса
        imu.angular_velocity.x, imu.angular_velocity.y, imu.angular_velocity.z = map(float, w)
        self.pub_imu.publish(imu)
        if not with_odom:
            return

        od = Odometry()
        od.header.stamp, od.header.frame_id, od.child_frame_id = st, "odom", "base_link"
        pp = od.pose.pose
        pp.position.x, pp.position.y, pp.position.z = map(float, d.qpos[qa:qa + 3])
        pp.orientation = imu.orientation
        vb = R.T @ d.qvel[va:va + 3]       # линейная скорость свободного сустава — в мире
        tw = od.twist.twist
        tw.linear.x, tw.linear.y, tw.linear.z = map(float, vb)
        tw.angular = imu.angular_velocity
        self.pub_odom.publish(od)

        tf = TransformStamped()
        tf.header = od.header
        tf.child_frame_id = "base_link"
        tf.transform.translation.x = pp.position.x
        tf.transform.translation.y = pp.position.y
        tf.transform.translation.z = pp.position.z
        tf.transform.rotation = pp.orientation
        tfs = [tf]
        if self.cam_id >= 0:
            # Камера на голове утки двигается вместе с шеей, поэтому tf динамический.
            pb = d.qpos[qa:qa + 3]
            pc = R.T @ (d.cam_xpos[self.cam_id] - pb)
            Rc = R.T @ d.cam_xmat[self.cam_id].reshape(3, 3) @ MJ_TO_OPTICAL
            qc = np.zeros(4)
            mujoco.mju_mat2Quat(qc, Rc.ravel())
            ct = TransformStamped()
            ct.header.stamp, ct.header.frame_id, ct.child_frame_id = st, "base_link", "camera_link"
            ct.transform.translation.x, ct.transform.translation.y, ct.transform.translation.z = map(float, pc)
            r = ct.transform.rotation
            r.w, r.x, r.y, r.z = map(float, qc)
            tfs.append(ct)
        self.tf.sendTransform(tfs)

    def _publish_image(self, pub, rgb, t, frame_id):
        msg = Image()
        msg.header.stamp, msg.header.frame_id = stamp(t), frame_id
        msg.height, msg.width = rgb.shape[:2]
        msg.encoding, msg.step = "rgb8", rgb.shape[1] * 3
        msg.data = rgb.tobytes()
        pub.publish(msg)

    def _publish_info(self, K, t):
        info = CameraInfo()
        info.header.stamp, info.header.frame_id = stamp(t), "camera_link"
        info.width, info.height = self.cam_wh
        info.distortion_model = "plumb_bob"
        info.d = [0.0] * 5
        info.k = [float(v) for v in K.ravel()]
        info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        info.p = [float(v) for v in (K[0, 0], 0, K[0, 2], 0, 0, K[1, 1], K[1, 2], 0, 0, 0, 1, 0)]
        self.pub_info.publish(info)


def main():
    rclpy.init()
    node = SimNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.running = False
        node.thread.join(timeout=2.0)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
