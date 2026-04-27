# Listener в tf2

Цель: написать Python-ноду, которая читает трансформации из tf2 и использует их для управления второй черепахой в `turtlesim`.

Официальная основа: <https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Tf2/Writing-A-Tf2-Listener-Py.html>

## Идея

Broadcaster публикует положение фрейма. Listener использует `Buffer` и `TransformListener`, чтобы получить нужную трансформацию из дерева tf2.

В этой статье listener:

1. Создаёт вторую черепаху через сервис `spawn`.
2. Запрашивает трансформацию `turtle2 -> target_frame`.
3. Публикует команды скорости в `turtle2/cmd_vel`.

## Нода `turtle_tf2_listener.py`

Создайте файл `learning_tf2_py/turtle_tf2_listener.py`:

```python
import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from tf2_ros import TransformException
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener
from turtlesim.srv import Spawn


class FrameListener(Node):
    def __init__(self):
        super().__init__('turtle_tf2_frame_listener')
        self.target_frame = self.declare_parameter(
            'target_frame',
            'turtle1',
        ).get_parameter_value().string_value
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.spawner = self.create_client(Spawn, 'spawn')
        self.spawn_future = None
        self.turtle_spawned = False
        self.publisher = self.create_publisher(Twist, 'turtle2/cmd_vel', 1)
        self.timer = self.create_timer(1.0, self.on_timer)

    def on_timer(self):
        if not self.turtle_spawned:
            self.spawn_turtle_once()
            return

        try:
            transform = self.tf_buffer.lookup_transform(
                'turtle2',
                self.target_frame,
                rclpy.time.Time(),
            )
        except TransformException as ex:
            self.get_logger().info(f'Could not transform turtle2 to {self.target_frame}: {ex}')
            return

        msg = Twist()
        msg.angular.z = 4.0 * math.atan2(
            transform.transform.translation.y,
            transform.transform.translation.x,
        )
        msg.linear.x = 0.5 * math.hypot(
            transform.transform.translation.x,
            transform.transform.translation.y,
        )
        self.publisher.publish(msg)

    def spawn_turtle_once(self):
        if not self.spawner.service_is_ready():
            self.spawner.wait_for_service(timeout_sec=0.1)
            return

        if self.spawn_future is None:
            request = Spawn.Request()
            request.name = 'turtle2'
            request.x = 4.0
            request.y = 2.0
            request.theta = 0.0
            self.spawn_future = self.spawner.call_async(request)
            return

        if self.spawn_future.done():
            self.turtle_spawned = True
            self.get_logger().info('Spawned turtle2')


def main(args=None):
    rclpy.init(args=args)
    node = FrameListener()
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
'turtle_tf2_listener = learning_tf2_py.turtle_tf2_listener:main',
```

## Обновление launch-файла

Теперь базовый launch должен запускать:

- `turtlesim_node`;
- broadcaster для `turtle1`;
- broadcaster для `turtle2`;
- listener, который управляет `turtle2`.

Полная версия `launch/turtle_tf2_demo.launch.py`:

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
        Node(
            package='learning_tf2_py',
            executable='turtle_tf2_broadcaster',
            name='broadcaster2',
            parameters=[{'turtlename': 'turtle2'}],
        ),
        Node(
            package='learning_tf2_py',
            executable='turtle_tf2_listener',
            name='listener',
            parameters=[{'target_frame': LaunchConfiguration('target_frame')}],
        ),
    ])
```

## Сборка и запуск

```bash
cd ~/ros2_ws
rosdep install -i --from-path src --rosdistro jazzy -y
colcon build --packages-select learning_tf2_py
source install/setup.bash
ros2 launch learning_tf2_py turtle_tf2_demo.launch.py
```

В новом терминале запустите управление первой черепахой:

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 run turtlesim turtle_teleop_key
```

Если `turtle1` движется, `turtle2` должна следовать за ней.

## Проверка

Посмотрите трансформацию между черепахами:

```bash
ros2 run tf2_ros tf2_echo turtle2 turtle1
```

В начале возможны сообщения вида `Could not transform...`: это нормально, пока listener ещё не получил все фреймы и пока `turtle2` не создана.

## Практика

1. Запустите демо с параметром `target_frame:=world`.
2. Измените коэффициенты `angular.z` и `linear.x` и сравните поведение `turtle2`.
3. Добавьте логирование текущей дистанции до цели.

Готовая версия файла есть в `ros2_ws/src/learning_tf2_py/learning_tf2_py/turtle_tf2_listener.py`.
