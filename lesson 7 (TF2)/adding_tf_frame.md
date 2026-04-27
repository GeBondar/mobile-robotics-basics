# Добавление нового фрейма в tf2

Цель: добавить к дереву tf2 новый фрейм `carrot1` и использовать его как цель для второй черепахи.

Официальная основа: <https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Tf2/Adding-A-Frame-Py.html>

## Идея

tf2 хранит фреймы в виде дерева. У каждого фрейма, кроме корневого, есть один родитель. Когда мы добавляем новый фрейм, мы фактически публикуем ещё одну трансформацию: например, `turtle1 -> carrot1`.

В этом упражнении будут два варианта:

- фиксированный `carrot1`, который всегда находится на 2 м по оси Y от `turtle1`;
- динамический `carrot1`, который движется вокруг `turtle1`.

Перед началом должны быть выполнены статьи:

- [Знакомство с tf2](introducing_tf2.md)
- [Статический broadcaster](static_tf_broadcaster.md)
- [Динамический broadcaster](dynamic_tf_broadcaster.md)
- [Listener](writing_tf_listener.md)

## Фиксированный фрейм

Создайте файл `learning_tf2_py/fixed_frame_tf2_broadcaster.py`:

```python
import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros import TransformBroadcaster


class FixedFrameBroadcaster(Node):
    def __init__(self):
        super().__init__('fixed_frame_tf2_broadcaster')
        self.broadcaster = TransformBroadcaster(self)
        self.timer = self.create_timer(0.1, self.broadcast)

    def broadcast(self):
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = 'turtle1'
        transform.child_frame_id = 'carrot1'
        transform.transform.translation.x = 0.0
        transform.transform.translation.y = 2.0
        transform.transform.translation.z = 0.0
        transform.transform.rotation.w = 1.0
        self.broadcaster.sendTransform(transform)


def main(args=None):
    rclpy.init(args=args)
    node = FixedFrameBroadcaster()
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

Добавьте точку входа в `setup.py`:

```python
'fixed_frame_tf2_broadcaster = learning_tf2_py.fixed_frame_tf2_broadcaster:main',
```

Создайте `launch/turtle_tf2_fixed_frame_demo.launch.py`:

```python
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        IncludeLaunchDescription(
            PathJoinSubstitution([
                FindPackageShare('learning_tf2_py'),
                'launch',
                'turtle_tf2_demo.launch.py',
            ]),
        ),
        Node(
            package='learning_tf2_py',
            executable='fixed_frame_tf2_broadcaster',
            name='fixed_broadcaster',
        ),
    ])
```

Соберите и запустите:

```bash
cd ~/ros2_ws
colcon build --packages-select learning_tf2_py
source install/setup.bash
ros2 launch learning_tf2_py turtle_tf2_fixed_frame_demo.launch.py target_frame:=carrot1
```

Теперь `turtle2` следует не за `turtle1`, а за фреймом `carrot1`.

## Динамический фрейм

Создайте файл `learning_tf2_py/dynamic_frame_tf2_broadcaster.py`:

```python
import math

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros import TransformBroadcaster


class DynamicFrameBroadcaster(Node):
    def __init__(self):
        super().__init__('dynamic_frame_tf2_broadcaster')
        self.broadcaster = TransformBroadcaster(self)
        self.timer = self.create_timer(0.1, self.broadcast)

    def broadcast(self):
        seconds, nanoseconds = self.get_clock().now().seconds_nanoseconds()
        time_value = seconds + nanoseconds / 1e9
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = 'turtle1'
        transform.child_frame_id = 'carrot1'
        transform.transform.translation.x = 2.0 * math.sin(time_value)
        transform.transform.translation.y = 2.0 * math.cos(time_value)
        transform.transform.translation.z = 0.0
        transform.transform.rotation.w = 1.0
        self.broadcaster.sendTransform(transform)


def main(args=None):
    rclpy.init(args=args)
    node = DynamicFrameBroadcaster()
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

Добавьте точку входа в `setup.py`:

```python
'dynamic_frame_tf2_broadcaster = learning_tf2_py.dynamic_frame_tf2_broadcaster:main',
```

Создайте `launch/turtle_tf2_dynamic_frame_demo.launch.py`:

```python
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        IncludeLaunchDescription(
            PathJoinSubstitution([
                FindPackageShare('learning_tf2_py'),
                'launch',
                'turtle_tf2_demo.launch.py',
            ]),
            launch_arguments={'target_frame': 'carrot1'}.items(),
        ),
        Node(
            package='learning_tf2_py',
            executable='dynamic_frame_tf2_broadcaster',
            name='dynamic_broadcaster',
        ),
    ])
```

Запустите динамический вариант:

```bash
cd ~/ros2_ws
colcon build --packages-select learning_tf2_py
source install/setup.bash
ros2 launch learning_tf2_py turtle_tf2_dynamic_frame_demo.launch.py
```

`turtle2` будет следовать за фреймом `carrot1`, который движется вокруг `turtle1`.

## Проверка дерева фреймов

```bash
ros2 run tf2_tools view_frames
```

Откройте сгенерированный `frames.pdf`. В дереве должна появиться связь `turtle1 -> carrot1`.

## Практика

1. Измените радиус движения `carrot1`.
2. Сделайте движение по эллипсу.
3. Добавьте фрейм `laser_frame` как дочерний для `turtle2`.

Готовые версии файлов находятся в `ros2_ws/src/learning_tf2_py/learning_tf2_py`.
