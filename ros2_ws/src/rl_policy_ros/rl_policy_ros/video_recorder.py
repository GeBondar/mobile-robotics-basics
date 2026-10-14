#!/usr/bin/env python3
"""Запись ролика: внешняя камера сима + картинка детектора в углу -> mp4.

    ros2 run rl_policy_ros video_recorder --ros-args -p use_sim_time:=true \
        -p out:=/tmp/run.mp4 -p inset:=/aruco/debug_image -p title:="ЦАПЛЯ-2: подход к ArUco"

Внешнюю камеру включает sim_node: -p chase_rate:=15.0. Кадр пишется по приходу кадра
внешней камеры, частота ролика — fps (по умолчанию равна chase_rate сима).
Запись идёт до Ctrl+C или до duration секунд времени симуляции.
"""
import signal

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String


def to_bgr(m):
    return cv2.cvtColor(np.frombuffer(m.data, np.uint8).reshape(m.height, m.width, 3), cv2.COLOR_RGB2BGR)


class VideoRecorder(Node):
    def __init__(self):
        super().__init__("video_recorder")
        p = self.declare_parameter
        p("out", "/tmp/rl_policy_ros.mp4")
        p("main", "/sim/chase/image_raw")
        p("inset", "")                 # пусто — без врезки
        p("inset_scale", 0.4)
        p("fps", 15.0)
        p("duration", 0.0)             # с времени симуляции; 0 — до Ctrl+C
        p("title", "")
        g = lambda n: self.get_parameter(n).value  # noqa: E731
        self.out, self.fps, self.dur = g("out"), float(g("fps")), float(g("duration"))
        self.title, self.inset_scale = g("title"), float(g("inset_scale"))
        self.writer = None
        self.inset = None
        self.status = ""
        self.t0 = None
        self.n = 0
        sd = qos_profile_sensor_data
        self.create_subscription(Image, g("main"), self._on_main, sd)
        if g("inset"):
            self.create_subscription(Image, g("inset"), lambda m: setattr(self, "inset", m), sd)
        self.create_subscription(String, "policy/active", lambda m: setattr(self, "status", m.data), 10)
        self.done = False

    def _on_main(self, m):
        t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        self.t0 = self.t0 if self.t0 is not None else t
        if self.dur > 0 and t - self.t0 > self.dur:
            self.done = True
            return
        frame = to_bgr(m).copy()
        H, W = frame.shape[:2]
        if self.inset is not None:
            ins = to_bgr(self.inset)
            w = int(W * self.inset_scale)
            h = int(ins.shape[0] * w / ins.shape[1])
            ins = cv2.resize(ins, (w, h), interpolation=cv2.INTER_AREA)
            frame[H - h - 8:H - 8, W - w - 8:W - 8] = ins
            cv2.rectangle(frame, (W - w - 9, H - h - 9), (W - 8, H - 8), (255, 255, 255), 1)
        lines = [s for s in (self.title, f"t = {t - self.t0:5.1f} s   policy: {self.status}") if s]
        for k, s in enumerate(lines):
            cv2.putText(frame, s, (10, 24 + 22 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(frame, s, (10, 24 + 22 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        if self.writer is None:
            self.writer = cv2.VideoWriter(self.out, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (W, H))
            self.get_logger().info(f"пишу {self.out}: {W}x{H}, {self.fps} к/с")
        self.writer.write(frame)
        self.n += 1

    def close(self):
        if self.writer is not None:
            self.writer.release()
            self.get_logger().info(f"записано {self.n} кадров в {self.out}")


def main():
    rclpy.init()
    node = VideoRecorder()
    # SIGTERM (kill, остановка из скрипта) — тоже штатное завершение: без release()
    # mp4 остаётся без индекса (moov) и не открывается ни одним плеером.
    signal.signal(signal.SIGTERM, lambda *_: setattr(node, "done", True))
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
