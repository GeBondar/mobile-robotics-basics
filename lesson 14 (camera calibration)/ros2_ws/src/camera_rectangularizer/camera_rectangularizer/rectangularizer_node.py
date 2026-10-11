from __future__ import annotations

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge, CvBridgeError
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image


class CameraRectangularizer(Node):
    """Correct lens distortion and map a planar quadrilateral to a rectangle."""

    def __init__(self) -> None:
        super().__init__('camera_rectangularizer')

        self.declare_parameter('input_image_topic', '/camera/image_raw')
        self.declare_parameter('camera_info_topic', '/camera/camera_info')
        self.declare_parameter(
            'source_points',
            [120.0, 80.0, 520.0, 100.0, 570.0, 420.0, 70.0, 400.0],
        )
        self.declare_parameter('output_width', 640)
        self.declare_parameter('output_height', 480)

        source = list(self.get_parameter('source_points').value)
        if len(source) != 8:
            raise ValueError('source_points must contain exactly 8 numbers')

        self.source_points = np.array(source, dtype=np.float32).reshape(4, 2)
        self.output_width = int(self.get_parameter('output_width').value)
        self.output_height = int(self.get_parameter('output_height').value)

        if self.output_width <= 0 or self.output_height <= 0:
            raise ValueError('output_width and output_height must be positive')

        self.destination_points = np.array(
            [
                [0.0, 0.0],
                [self.output_width - 1.0, 0.0],
                [self.output_width - 1.0, self.output_height - 1.0],
                [0.0, self.output_height - 1.0],
            ],
            dtype=np.float32,
        )
        self.homography = cv2.getPerspectiveTransform(
            self.source_points,
            self.destination_points,
        )

        self.bridge = CvBridge()
        self.camera_matrix: np.ndarray | None = None
        self.dist_coeffs: np.ndarray | None = None

        image_topic = str(self.get_parameter('input_image_topic').value)
        info_topic = str(self.get_parameter('camera_info_topic').value)

        self.create_subscription(
            CameraInfo,
            info_topic,
            self.on_camera_info,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Image,
            image_topic,
            self.on_image,
            qos_profile_sensor_data,
        )
        self.publisher = self.create_publisher(
            Image,
            '/camera/image_rectangularized',
            qos_profile_sensor_data,
        )

        self.get_logger().info(
            f'Input: {image_topic}; output: /camera/image_rectangularized'
        )

    def on_camera_info(self, msg: CameraInfo) -> None:
        matrix = np.asarray(msg.k, dtype=np.float64).reshape(3, 3)
        if matrix[0, 0] == 0.0:
            return

        self.camera_matrix = matrix
        self.dist_coeffs = np.asarray(msg.d, dtype=np.float64)

    def on_image(self, msg: Image) -> None:
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except CvBridgeError as exc:
            self.get_logger().error(f'cv_bridge conversion failed: {exc}')
            return

        if self.camera_matrix is not None and self.dist_coeffs is not None:
            frame = cv2.undistort(
                frame,
                self.camera_matrix,
                self.dist_coeffs,
            )

        result = cv2.warpPerspective(
            frame,
            self.homography,
            (self.output_width, self.output_height),
        )

        output = self.bridge.cv2_to_imgmsg(result, encoding='bgr8')
        output.header = msg.header
        self.publisher.publish(output)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = CameraRectangularizer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
