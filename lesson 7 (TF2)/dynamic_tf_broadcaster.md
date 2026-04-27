# Динамический broadcaster в tf2

Цель: написать Python-ноду, которая получает позу черепахи из `turtlesim` и публикует её фрейм в tf2.

Официальная основа: <https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Tf2/Writing-A-Tf2-Broadcaster-Py.html>

## Идея

Статический broadcaster публикует неизменяемую связь между фреймами. Динамический broadcaster нужен, когда положение фрейма меняется: робот едет, манипулятор вращается, объект перемещается в сцене.

В этом упражнении нода подписывается на топик `/{turtlename}/pose` и публикует трансформацию `world -> {turtlename}` в `/tf`.

## Нода `turtle_tf2_broadcaster.py`

Создайте файл `learning_tf2_py/turtle_tf2_broadcaster.py`:

```python
import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros import TransformBroadcaster
from turtlesim.msg import Pose

from learning_tf2_py.quaternion import quaternion_from_euler


class FramePublisher(Node):
    def __init__(self):
        super().__init__('turtle_tf2_frame_publisher')
        self.turtlename = self.declare_parameter(
            'turtlename',
            'turtle1',
        ).get_parameter_value().string_value
        self.broadcaster = TransformBroadcaster(self)
        self.subscription = self.create_subscription(
            Pose,
            f'/{self.turtlename}/pose',
            self.handle_turtle_pose,
            1,
        )

    def handle_turtle_pose(self, msg):
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = 'world'
        transform.child_frame_id = self.turtlename
        transform.transform.translation.x = msg.x
        transform.transform.translation.y = msg.y
        transform.transform.translation.z = 0.0

        qx, qy, qz, qw = quaternion_from_euler(0.0, 0.0, msg.theta)
        transform.transform.rotation.x = qx
        transform.transform.rotation.y = qy
        transform.transform.rotation.z = qz
        transform.transform.rotation.w = qw

        self.broadcaster.sendTransform(transform)


def main(args=None):
    rclpy.init(args=args)
    node = FramePublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

Добавьте зависимости в `package.xml`, если их ещё нет:

```xml
<exec_depend>geometry_msgs</exec_depend>
<exec_depend>rclpy</exec_depend>
<exec_depend>tf2_ros_py</exec_depend>
<exec_depend>turtlesim</exec_depend>
```

Добавьте точку входа в `setup.py`:

```python
'turtle_tf2_broadcaster = learning_tf2_py.turtle_tf2_broadcaster:main',
```

## Launch-файл

Создайте `launch/turtle_tf2_demo.launch.py`:

```python
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('target_frame', default_value='turtle1'),
        Node(
            package='turtlesim',
            executable='turtlesim_node',
            name='sim',
            output='screen',
        ),
        Node(
            package='learning_tf2_py',
            executable='turtle_tf2_broadcaster',
            name='broadcaster1',
            parameters=[{'turtlename': 'turtle1'}],
        ),
    ])
```

Чтобы `ros2 launch` видел launch-файлы, добавьте в `setup.py`:

```python
import os
from glob import glob
```

И в `data_files`:

```python
(os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
```

## Сборка и проверка

```bash
cd ~/ros2_ws
rosdep install -i --from-path src --rosdistro jazzy -y
colcon build --packages-select learning_tf2_py
source install/setup.bash
ros2 launch learning_tf2_py turtle_tf2_demo.launch.py
```

В новом терминале:

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 run turtlesim turtle_teleop_key
```

Ещё в одном терминале:

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 run tf2_ros tf2_echo world turtle1
```

При движении черепахи значения трансформации должны обновляться.

## Практика

1. Запустите broadcaster с параметром `turtlename:=turtle1`.
2. Посмотрите топики `/tf` и `/tf_static`.
3. Объясните, почему поза черепахи публикуется в `/tf`, а не в `/tf_static`.

Готовая версия файла есть в `ros2_ws/src/learning_tf2_py/learning_tf2_py/turtle_tf2_broadcaster.py`.
