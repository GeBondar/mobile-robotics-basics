import math

import rclpy
from geometry_msgs.msg import Quaternion, TransformStamped
from rclpy.node import Node
from sensor_msgs.msg import JointState
from tf2_ros import TransformBroadcaster


class StatePublisher(Node):
    def __init__(self):
        super().__init__('state_publisher')
        self.joint_pub = self.create_publisher(JointState, 'joint_states', 10)
        self.broadcaster = TransformBroadcaster(self)
        self.timer = self.create_timer(1.0 / 30.0, self.update)
        self.degree = math.pi / 180.0
        self.swivel = 0.0
        self.tilt = 0.0
        self.height = 0.0
        self.angle = 0.0
        self.tilt_inc = self.degree
        self.height_inc = 0.005

    def update(self):
        now = self.get_clock().now()

        joint_state = JointState()
        joint_state.header.stamp = now.to_msg()
        joint_state.name = ['swivel', 'tilt', 'periscope']
        joint_state.position = [self.swivel, self.tilt, self.height]

        odom_trans = TransformStamped()
        odom_trans.header.stamp = now.to_msg()
        odom_trans.header.frame_id = 'odom'
        odom_trans.child_frame_id = 'axis'
        odom_trans.transform.translation.x = math.cos(self.angle) * 2.0
        odom_trans.transform.translation.y = math.sin(self.angle) * 2.0
        odom_trans.transform.translation.z = 0.0
        odom_trans.transform.rotation = euler_to_quaternion(0.0, 0.0, self.angle)

        self.joint_pub.publish(joint_state)
        self.broadcaster.sendTransform(odom_trans)

        self.tilt += self.tilt_inc
        if self.tilt < -0.5 or self.tilt > 0.0:
            self.tilt_inc *= -1.0

        self.height += self.height_inc
        if self.height > 0.2 or self.height < 0.0:
            self.height_inc *= -1.0

        self.swivel += self.degree
        self.angle += self.degree / 4.0


def euler_to_quaternion(roll, pitch, yaw):
    qx = math.sin(roll / 2) * math.cos(pitch / 2) * math.cos(yaw / 2) - math.cos(roll / 2) * math.sin(pitch / 2) * math.sin(yaw / 2)
    qy = math.cos(roll / 2) * math.sin(pitch / 2) * math.cos(yaw / 2) + math.sin(roll / 2) * math.cos(pitch / 2) * math.sin(yaw / 2)
    qz = math.cos(roll / 2) * math.cos(pitch / 2) * math.sin(yaw / 2) - math.sin(roll / 2) * math.sin(pitch / 2) * math.cos(yaw / 2)
    qw = math.cos(roll / 2) * math.cos(pitch / 2) * math.cos(yaw / 2) + math.sin(roll / 2) * math.sin(pitch / 2) * math.sin(yaw / 2)
    return Quaternion(x=qx, y=qy, z=qz, w=qw)


def main(args=None):
    rclpy.init(args=args)
    node = StatePublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
