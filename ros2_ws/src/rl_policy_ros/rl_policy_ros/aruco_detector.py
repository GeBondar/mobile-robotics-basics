#!/usr/bin/env python3
"""Нода-детектор ArUco: кадр камеры -> где маркер относительно робота.

    ros2 run rl_policy_ros aruco_detector --ros-args -p marker_size:=0.30 -p use_sim_time:=true

Подписки:  /camera/image_raw, /camera/camera_info
Публикует: /detections          rl_policy_interfaces/Detection, по сообщению на маркер,
                                label = "aruco_<id>"
           /aruco/debug_image   кадр с обведёнными маркерами, пеленгом и дальностью

Поза маркера считается solvePnP по четырём углам и известной стороне квадрата
marker_size (чёрная часть, без белой рамки). Пеленг и угол места — в оптической
раме камеры: пеленг > 0 — маркер левее оси, как положительный yaw в ROS.
"""
import math

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rl_policy_interfaces.msg import Detection
from sensor_msgs.msg import CameraInfo, Image

DICTS = {"4x4_50": cv2.aruco.DICT_4X4_50, "5x5_100": cv2.aruco.DICT_5X5_100,
         "6x6_250": cv2.aruco.DICT_6X6_250}


class ArucoDetector(Node):
    def __init__(self):
        super().__init__("aruco_detector")
        self.declare_parameter("marker_size", 0.30)       # м, сторона чёрного квадрата
        self.declare_parameter("dictionary", "4x4_50")
        self.declare_parameter("publish_debug_image", True)
        self.size = float(self.get_parameter("marker_size").value)
        d = cv2.aruco.getPredefinedDictionary(DICTS[self.get_parameter("dictionary").value])
        self.det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
        self.debug = bool(self.get_parameter("publish_debug_image").value)
        h = self.size / 2
        # углы маркера в его раме в порядке, который отдаёт detectMarkers
        self.obj = np.array([[-h, h, 0], [h, h, 0], [h, -h, 0], [-h, -h, 0]], dtype=np.float32)
        self.K = self.D = None
        sd = qos_profile_sensor_data
        self.create_subscription(CameraInfo, "camera/camera_info", self._on_info, sd)
        self.create_subscription(Image, "camera/image_raw", self._on_image, sd)
        self.pub = self.create_publisher(Detection, "detections", 10)
        self.pub_dbg = self.create_publisher(Image, "aruco/debug_image", sd)
        self.n_frames = self.n_hits = 0
        self.create_timer(10.0, self._report)

    def _on_info(self, m):
        self.K = np.array(m.k, dtype=np.float64).reshape(3, 3)
        self.D = np.array(m.d, dtype=np.float64)

    def _on_image(self, m):
        if self.K is None or m.encoding != "rgb8":
            return
        rgb = np.frombuffer(m.data, dtype=np.uint8).reshape(m.height, m.width, 3)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        corners, ids, _ = self.det.detectMarkers(gray)
        self.n_frames += 1
        dbg = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR) if self.debug else None
        if ids is not None:
            self.n_hits += 1
            for c, i in zip(corners, ids.ravel()):
                ok, rvec, tvec = cv2.solvePnP(self.obj, c.reshape(4, 2), self.K, self.D,
                                              flags=cv2.SOLVEPNP_IPPE_SQUARE)
                if not ok:
                    continue
                x, y, z = tvec.ravel()                  # оптическая рама: x вправо, y вниз, z вперёд
                msg = Detection()
                msg.header = m.header
                msg.label = f"aruco_{int(i)}"
                msg.bearing = float(math.atan2(-x, z))
                msg.elevation = float(math.atan2(-y, z))
                msg.distance = float(math.sqrt(x * x + y * y + z * z))
                msg.size_px = float(cv2.contourArea(c.reshape(4, 2)) ** 0.5)
                msg.u, msg.v = map(float, c.reshape(4, 2).mean(axis=0))
                self.pub.publish(msg)
                if dbg is not None:
                    cv2.drawFrameAxes(dbg, self.K, self.D, rvec, tvec, self.size * 0.5)
                    cv2.putText(dbg, f"id{int(i)} {msg.distance:.2f}m {math.degrees(msg.bearing):+.0f}deg",
                                (int(msg.u) - 60, int(msg.v) - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                                (0, 255, 255), 1, cv2.LINE_AA)
            if dbg is not None:
                cv2.aruco.drawDetectedMarkers(dbg, corners, ids)
        if dbg is not None:
            out = Image()
            out.header, out.height, out.width = m.header, m.height, m.width
            out.encoding, out.step = "rgb8", m.width * 3
            out.data = cv2.cvtColor(dbg, cv2.COLOR_BGR2RGB).tobytes()
            self.pub_dbg.publish(out)

    def _report(self):
        if self.n_frames:
            self.get_logger().info(f"кадров {self.n_frames}, с маркерами {self.n_hits}")
        else:
            self.get_logger().warn("кадров нет — проверьте /camera/image_raw и camera_rate сима")
        self.n_frames = self.n_hits = 0


def main():
    rclpy.init()
    node = ArucoDetector()
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
