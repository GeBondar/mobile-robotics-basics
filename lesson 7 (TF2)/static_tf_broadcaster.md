# Статический broadcaster в tf2

Цель: создать Python-ноду, которая публикует неизменяемую трансформацию в tf2, и проверить результат через `/tf_static`.

Официальная основа: <https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Tf2/Writing-A-Tf2-Static-Broadcaster-Py.html>

## Что такое статическая трансформация

Статическая трансформация описывает связь между фреймами, которая не меняется со временем. Типичный пример: положение камеры, лидара или IMU относительно корпуса робота.

В tf2 такие трансформации публикуются в топик `/tf_static`. Для этого используется `StaticTransformBroadcaster`.

## Подготовка пакета

Если пакет `learning_tf2_py` ещё не создан, создайте его в workspace:

```bash
cd ~/ros2_ws/src
ros2 pkg create --build-type ament_python --license Apache-2.0 learning_tf2_py
```

Добавьте зависимости в `package.xml`:

```xml
<exec_depend>geometry_msgs</exec_depend>
<exec_depend>rclpy</exec_depend>
<exec_depend>tf2_ros_py</exec_depend>
```

## Вспомогательный модуль кватернионов

Создайте файл `learning_tf2_py/quaternion.py`:

```python
import math


def quaternion_from_euler(roll, pitch, yaw):
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)

    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )
```

## Нода `static_turtle_tf2_broadcaster.py`

Создайте файл `learning_tf2_py/static_turtle_tf2_broadcaster.py`:

```python
import argparse

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster

from learning_tf2_py.quaternion import quaternion_from_euler


class StaticFramePublisher(Node):
    def __init__(self, child_frame, x, y, z, roll, pitch, yaw):
        super().__init__('static_turtle_tf2_broadcaster')
        self.broadcaster = StaticTransformBroadcaster(self)

        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = 'world'
        transform.child_frame_id = child_frame
        transform.transform.translation.x = x
        transform.transform.translation.y = y
        transform.transform.translation.z = z

        qx, qy, qz, qw = quaternion_from_euler(roll, pitch, yaw)
        transform.transform.rotation.x = qx
        transform.transform.rotation.y = qy
        transform.transform.rotation.z = qz
        transform.transform.rotation.w = qw

        self.broadcaster.sendTransform(transform)


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('child_frame', nargs='?', default='mystaticturtle')
    parser.add_argument('x', type=float, nargs='?', default=0.0)
    parser.add_argument('y', type=float, nargs='?', default=0.0)
    parser.add_argument('z', type=float, nargs='?', default=1.0)
    parser.add_argument('roll', type=float, nargs='?', default=0.0)
    parser.add_argument('pitch', type=float, nargs='?', default=0.0)
    parser.add_argument('yaw', type=float, nargs='?', default=0.0)
    parsed_args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = StaticFramePublisher(
        parsed_args.child_frame,
        parsed_args.x,
        parsed_args.y,
        parsed_args.z,
        parsed_args.roll,
        parsed_args.pitch,
        parsed_args.yaw,
    )

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
'static_turtle_tf2_broadcaster = learning_tf2_py.static_turtle_tf2_broadcaster:main',
```

## Сборка и запуск

```bash
cd ~/ros2_ws
rosdep install -i --from-path src --rosdistro jazzy -y
colcon build --packages-select learning_tf2_py
source install/setup.bash
ros2 run learning_tf2_py static_turtle_tf2_broadcaster mystaticturtle 0 0 1 0 0 0
```

В новом терминале:

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 topic echo /tf_static
```

Ожидаемый результат: в `/tf_static` появится трансформация `world -> mystaticturtle` со смещением `z = 1.0`.

## Готовый инструмент для статических фреймов

В реальных проектах для простых статических фреймов часто достаточно готовой ноды `static_transform_publisher`:

```bash
ros2 run tf2_ros static_transform_publisher \
  --x 0 --y 0 --z 1 \
  --yaw 0 --pitch 0 --roll 0 \
  --frame-id world \
  --child-frame-id mystaticturtle
```

Этот вариант удобно использовать в launch-файлах, когда не нужна отдельная пользовательская нода.

## Практика

1. Опубликуйте фрейм `camera_lens` относительно `base_link`: `x=0.05`, `y=0.1`, `z=0.0`, `roll=1.57`.
2. Проверьте результат командой `ros2 topic echo /tf_static`.
3. Повторите запуск через `static_transform_publisher`.

Готовая версия файла есть в `ros2_ws/src/learning_tf2_py/learning_tf2_py/static_turtle_tf2_broadcaster.py`.
