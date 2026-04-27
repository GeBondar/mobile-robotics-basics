# Понимание launch-файлов в ROS 2

**Цель:** Использовать инструмент командной строки для запуска нескольких нод одновременно.

**Уровень:** Начинающий

**Время:** 5 минут

## Содержание
- [Введение](#введение)
- [Предварительные требования](#предварительные-требования)
- [Задачи](#задачи)
  1. [Запуск launch-файла](#1-запуск-launch-файла)
  2. [(Опционально) Управление нодами turtlesim](#2-опционально-управление-нодами-turtlesim)
- [Резюме](#резюме)
- [Следующие шаги](#следующие-шаги)

## Введение

В большинстве вводных уроков вам приходилось открывать новые терминалы для каждой новой запускаемой ноды. Когда вы создаёте более сложные системы со всё большим количеством одновременно работающих нод, открывать терминалы и заново вводить параметры конфигурации становится утомительно.

Launch-файлы позволяют запускать и настраивать несколько исполняемых файлов, содержащих ноды ROS 2, одновременно.

Запуск одного launch-файла с помощью команды `ros2 launch` поднимет всю вашу систему — все ноды и их конфигурации — сразу.

## Предварительные требования

Перед началом этих уроков установите ROS 2 Jazzy, следуя инструкциям на странице [Installation](https://docs.ros.org/en/jazzy/Installation.html).

Команды, используемые в этом уроке, предполагают, что вы следовали руководству по установке бинарных пакетов для вашей операционной системы (deb-пакеты для Linux). Вы всё ещё можете следовать инструкциям, если собрали ROS 2 из исходников, но путь к вашим файлам setup, скорее всего, будет другим. Кроме того, вы не сможете использовать команду `sudo apt install ros-<distro>-<package>` (часто используемую в уроках для начинающих) при установке из исходников.

Если вы используете Linux и ещё не знакомы с оболочкой, вам поможет раздел prerequisites в уроке [Introducing turtlesim](https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Introducing-Turtlesim/Introducing-Turtlesim.html#prerequisites).

Как всегда, не забывайте sourceить ROS 2 в каждом новом терминале:

```bash
source /opt/ros/jazzy/setup.bash
```

## Задачи

### 1. Запуск launch-файла

Откройте новый терминал и выполните:

```bash
ros2 launch turtlesim multisim.launch.py
```

Эта команда запустит следующий launch-файл:

```python
from launch import LaunchDescription
import launch_ros.actions

def generate_launch_description():
    return LaunchDescription([
        launch_ros.actions.Node(
            namespace='turtlesim1', package='turtlesim',
            executable='turtlesim_node', output='screen'),
        launch_ros.actions.Node(
            namespace='turtlesim2', package='turtlesim',
            executable='turtlesim_node', output='screen'),
    ])
```

> **Примечание:** Launch-файл выше написан на Python, но ROS 2 также поддерживает XML и YAML. Сравнение форматов есть в уроке [Integrating launch files into ROS 2 packages](https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Launch/Launch-system.html).

В результате будут запущены две ноды `turtlesim`:

![Два окна turtlesim](images/turtlesim_multisim.png)

Подробный разбор launch-файлов будет в следующих статьях курса. Дополнительную информацию можно найти в официальном разделе [Launch](https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Launch/Launch-Main.html).

### 2. (Опционально) Управление нодами turtlesim

Теперь, когда эти ноды запущены, вы можете управлять ими как любыми другими нодами ROS 2. Например, можно заставить черепах двигаться в противоположных направлениях, открыв два дополнительных терминала и выполнив следующие команды:

**Во втором терминале:**

```bash
ros2 topic pub /turtlesim1/turtle1/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 2.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 1.8}}"
```

**В третьем терминале:**

```bash
ros2 topic pub /turtlesim2/turtle1/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 2.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: -1.8}}"
```

После выполнения этих команд вы увидите примерно следующее:

![Черепахи движутся по кругу](images/turtlesim_multisim_spin.png)

## Резюме

Главное, что вы сделали — запустили две ноды `turtlesim` одной командой. Когда вы научитесь писать собственные launch-файлы, вы сможете запускать несколько нод и настраивать их конфигурацию аналогичным образом с помощью команды `ros2 launch`.

## Следующие шаги

Дополнительные уроки по launch-файлам ROS 2 можно найти на [главной странице раздела Launch](https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Launch/Launch-Main.html).
