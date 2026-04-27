# turtlesim, ros2 CLI и базовые сущности ROS 2

Цель: запустить `turtlesim`, увидеть ноды и топики, вызвать сервисы и подготовиться к написанию собственных нод.

Официальная основа: <https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Introducing-Turtlesim/Introducing-Turtlesim.html>

## Установка

Для ROS 2 Jazzy:

```bash
sudo apt update
sudo apt install ros-jazzy-turtlesim
```

Для Humble используйте `ros-humble-turtlesim`.

Проверьте, что пакет установлен:

```bash
ros2 pkg executables turtlesim
```

Ожидаемые исполняемые файлы:

```text
turtlesim draw_square
turtlesim mimic
turtlesim turtle_teleop_key
turtlesim turtlesim_node
```

## Запуск turtlesim

В первом терминале:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run turtlesim turtlesim_node
```

Во втором терминале:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run turtlesim turtle_teleop_key
```

Управление выполняется стрелками в активном терминале с `turtle_teleop_key`.

## Ноды

В третьем терминале:

```bash
source /opt/ros/jazzy/setup.bash
ros2 node list
```

Ожидаемый результат:

```text
/teleop_turtle
/turtlesim
```

Посмотрите подробную информацию о ноде:

```bash
ros2 node info /turtlesim
```

## Топики

Список топиков:

```bash
ros2 topic list
ros2 topic list -t
```

Посмотрите команды скорости:

```bash
ros2 topic echo /turtle1/cmd_vel
```

Пока вы нажимаете стрелки в `turtle_teleop_key`, в этом терминале будут появляться сообщения `geometry_msgs/msg/Twist`.

## Сервисы

Список сервисов:

```bash
ros2 service list
```

Создайте вторую черепаху:

```bash
ros2 service call /spawn turtlesim/srv/Spawn "{x: 8.0, y: 8.0, theta: 0.0, name: 'turtle2'}"
```

Измените перо первой черепахи:

```bash
ros2 service call /turtle1/set_pen turtlesim/srv/SetPen "{r: 255, g: 0, b: 0, width: 5, off: 0}"
```

Переместите черепаху в абсолютную позицию:

```bash
ros2 service call /turtle1/teleport_absolute turtlesim/srv/TeleportAbsolute "{x: 5.5, y: 5.5, theta: 0.0}"
```

## Граф ROS 2

Запустите визуализацию графа:

```bash
rqt_graph
```

Сравните граф с выводом:

```bash
ros2 node list
ros2 topic list
ros2 service list
```

## Практика

1. Нарисуйте квадрат, используя `turtle_teleop_key`.
2. Создайте `turtle2` и найдите её топики.
3. Опубликуйте команду скорости вручную:

```bash
ros2 topic pub /turtle1/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 1.0}, angular: {z: 1.0}}"
```

4. Остановите публикацию через `Ctrl+C`.

После этой статьи переходите к нодам и топикам в уроке 2.
