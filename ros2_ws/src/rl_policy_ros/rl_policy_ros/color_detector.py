#!/usr/bin/env python3
"""Нода-детектор цвета: самое крупное пятно каждого цвета в кадре -> Detection.

    ros2 run rl_policy_ros color_detector --ros-args -p colors:="['red']" -p use_sim_time:=true

Подписки:  /camera/image_raw, /camera/camera_info
Публикует: /detections        rl_policy_interfaces/Detection, label = имя цвета;
                              u, v — центр пятна в пикселях, bearing/elevation — углы луча
                              на него в оптической раме камеры, distance = -1 (неизвестна)
           /color/debug_image  кадр с обведёнными пятнами

Дальность по одному пятну не определить — размер цели неизвестен. Тот, кому она нужна,
пересекает луч с известной поверхностью (у дрона — с полом, см. drone_search).
"""
import math

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rl_policy_interfaces.msg import Detection
from sensor_msgs.msg import CameraInfo, Image

# Диапазоны HSV (OpenCV: H 0..179). Красный оборачивается через 0 — два диапазона.
HSV = {
    "red": [((0, 120, 80), (8, 255, 255)), ((172, 120, 80), (179, 255, 255))],
    "green": [((45, 120, 60), (80, 255, 255))],
    "blue": [((100, 120, 60), (130, 255, 255))],
    "yellow": [((22, 120, 80), (35, 255, 255))],
}
DRAW = {"red": (0, 0, 255), "green": (0, 200, 0), "blue": (255, 80, 0), "yellow": (0, 220, 255)}


class ColorDetector(Node):
    def __init__(self):
        super().__init__("color_detector")
        self.declare_parameter("colors", ["red", "green", "blue", "yellow"])
        self.declare_parameter("min_area_px", 30)
        self.colors = [c for c in self.get_parameter("colors").value if c in HSV]
        self.min_area = int(self.get_parameter("min_area_px").value)
        self.K = None
        sd = qos_profile_sensor_data
        self.create_subscription(CameraInfo, "camera/camera_info", self._on_info, sd)
        self.create_subscription(Image, "camera/image_raw", self._on_image, sd)
        self.pub = self.create_publisher(Detection, "detections", 10)
        self.pub_dbg = self.create_publisher(Image, "color/debug_image", sd)
        self.get_logger().info(f"цвета: {self.colors}")

    def _on_info(self, m):
        self.K = np.array(m.k, dtype=np.float64).reshape(3, 3)

    def _on_image(self, m):
        if self.K is None or m.encoding != "rgb8":
            return
        rgb = np.frombuffer(m.data, dtype=np.uint8).reshape(m.height, m.width, 3)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        dbg = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        fx, fy, cx, cy = self.K[0, 0], self.K[1, 1], self.K[0, 2], self.K[1, 2]
        for name in self.colors:
            mask = np.zeros(hsv.shape[:2], np.uint8)
            for lo, hi in HSV[name]:
                mask |= cv2.inRange(hsv, np.array(lo), np.array(hi))
            n, _, stats, cent = cv2.connectedComponentsWithStats(mask)
            if n < 2:
                continue
            i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < self.min_area:
                continue
            u, v = map(float, cent[i])
            xn, yn = (u - cx) / fx, (v - cy) / fy           # луч в оптической раме: (xn, yn, 1)
            msg = Detection()
            msg.header = m.header
            msg.label = name
            msg.bearing = float(math.atan2(-xn, 1.0))
            msg.elevation = float(math.atan2(-yn, 1.0))
            msg.distance = -1.0
            msg.size_px = float(math.sqrt(area))
            msg.u, msg.v = u, v
            self.pub.publish(msg)
            x, y, w, h = stats[i, :4]
            cv2.rectangle(dbg, (int(x), int(y)), (int(x + w), int(y + h)), DRAW[name], 2)
            cv2.putText(dbg, f"{name} {area}px", (int(x), max(10, int(y) - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, DRAW[name], 1, cv2.LINE_AA)
        out = Image()
        out.header, out.height, out.width = m.header, m.height, m.width
        out.encoding, out.step = "rgb8", m.width * 3
        out.data = cv2.cvtColor(dbg, cv2.COLOR_BGR2RGB).tobytes()
        self.pub_dbg.publish(out)


def main():
    rclpy.init()
    node = ColorDetector()
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
