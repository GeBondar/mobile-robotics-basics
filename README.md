# Mobile Robotics Basics: ROS 2 Jazzy

Практический курс по основам мобильной робототехники на ROS 2. Основная версия курса - **ROS 2 Jazzy Jalisco на Ubuntu 24.04**. Для части материалов дополнительно указывается совместимость с **ROS 2 Humble Hawksbill на Ubuntu 22.04**.

Курс устроен как рабочая методичка: каждая статья должна давать понятную цель, минимальную теорию, воспроизводимые команды, ожидаемый результат и контрольные проверки. Термины русской локализации курса: **нода**, **топик**, **сервис**, **действие**, **параметр**, **launch-файл**, **фрейм**.

## Быстрый Старт

1. Подготовьте Ubuntu 24.04: локально, в WSL2 или в виртуальной машине.
2. Установите ROS 2 Jazzy: [Ubuntu 24.04](<lesson 1 (install ROS2 and testing)/ros2_jazzy_install.md>) или [Windows + WSL2](<lesson 1 (install ROS2 and testing)/windows_wsl2_jazzy_install.md>).
3. Настройте окружение: [ROS 2 environment](<lesson 1 (install ROS2 and testing)/ros2_environment.md>).
4. Проверьте установку: [ros2doctor](<lesson 1 (install ROS2 and testing)/ros2_doctor.md>).
5. Пройдите первые практики: [turtlesim](<lesson 1 (install ROS2 and testing)/ros2_turtlesim.md>) и [rqt](<lesson 1 (install ROS2 and testing)/ros2_rqt.md>).
6. Соберите workspace курса: [ros2_ws/src](<ros2_ws/src/README.md>).

```bash
cd ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
rosdep install -i --from-path src --rosdistro $ROS_DISTRO -y
colcon build --symlink-install
source install/setup.bash
```

## Структура Курса

| Урок | Тема | Навигация |
|---:|---|---|
| 1 | Установка, окружение и базовые инструменты | [README](<lesson 1 (install ROS2 and testing)/README.md>) |
| 2 | Ноды, топики, workspace и запись данных | [README](<lesson 2 (nodes and topics)/README.md>) |
| 3 | Сервисы и действия | [README](<lesson 3 (actions and services)/README.md>) |
| 4 | Launch-файлы и параметры | [README](<lesson 4 (launches and parameters)/README.md>) |
| 5 | URDF, Xacro и robot_state_publisher | [README](<lesson 5 (URDF and XACRO)/README.md>) |
| 6 | RViz2 и rqt | [README](<lesson 6 (RViz2 and rqt)/README.md>) |
| 7 | tf2 | [README](<lesson 7 (TF2)/README.md>) |
| 8 | Gazebo | [README](<lesson 8 (Gazebo)/README.md>) |
| 9 | Nav2 | [README](<lesson 9 (NAV2)/README.md>) |
| 10 | TurtleBot3 simulation | [README](<lesson 10 (turtlebot3 sim)/README.md>) |
| 11 | micro-ROS | [README](<lesson 11 (micro-ros)/README.md>) |

## Рекомендуемый Маршрут

### Базовый уровень

1. [Установка ROS 2 Jazzy](<lesson 1 (install ROS2 and testing)/ros2_jazzy_install.md>)
2. [Настройка окружения ROS 2](<lesson 1 (install ROS2 and testing)/ros2_environment.md>)
3. [Проверка установки через ros2doctor](<lesson 1 (install ROS2 and testing)/ros2_doctor.md>)
4. [turtlesim, ros2 CLI и rqt](<lesson 1 (install ROS2 and testing)/ros2_turtlesim.md>)
5. [Ноды](<lesson 2 (nodes and topics)/understanding_nodes.md>)
6. [Топики](<lesson 2 (nodes and topics)/understanding_topics.md>)
7. [Workspace, colcon и пакеты](<lesson 2 (nodes and topics)/workspace_colcon_package.md>)

### Разработка ROS 2 пакетов

1. [Публикатор для turtlesim](<lesson 2 (nodes and topics)/writing_talker.md>)
2. [Подписчик на pose turtlesim](<lesson 2 (nodes and topics)/writing_listener.md>)
3. [rosdep и зависимости workspace](<lesson 2 (nodes and topics)/rosdep.md>)
4. [ros2 bag: запись и воспроизведение данных](<lesson 2 (nodes and topics)/ros2_bag.md>)
5. [Сервисы](<lesson 3 (actions and services)/understanding_services.md>)
6. [Свой сервис](<lesson 3 (actions and services)/writing_service.md>)
7. [Действия](<lesson 3 (actions and services)/understanding_actions.md>)
8. [Своё действие MoveTo](<lesson 3 (actions and services)/writing_action.md>)

### Робототехническая модель и визуализация

1. [Параметры](<lesson 4 (launches and parameters)/understanding_parameters.md>)
2. [Launch-файлы](<lesson 4 (launches and parameters)/understanding_launches.md>)
3. [URDF](<lesson 5 (URDF and XACRO)/understanding_URDF.md>)
4. [Xacro](<lesson 5 (URDF and XACRO)/understanding_xacro.md>)
5. [robot_state_publisher](<lesson 5 (URDF and XACRO)/writing_state_publisher.md>)
6. [RViz2](<lesson 6 (RViz2 and rqt)/RViz_introduction.md>)
7. [tf2](<lesson 7 (TF2)/introducing_tf2.md>)

## Workspace Курса

В репозитории есть готовый исходный workspace: [ros2_ws/src](<ros2_ws/src/README.md>). Он нужен для проверки практических статей и содержит пакеты, создаваемые по ходу курса:

- `my_turtle_controller`
- `my_turtle_subscriber`
- `turtle_pose_interfaces`
- `turtle_pose_service`
- `turtle_action`
- `custom_action_interfaces`
- `fibonacci_action_py`
- `my_project_start`
- `urdf_tutorial`
- `urdf_tutorial_r2d2`
- `learning_tf2_py`

## Соглашения Курса

- Основной дистрибутив: `jazzy`.
- Команды, зависящие от версии ROS 2, по возможности пишутся через `$ROS_DISTRO`.
- Если команда отличается для Humble, это указывается отдельным примечанием.
- Python-пакеты курса используют `ament_python`; интерфейсные пакеты `.srv` и `.action` используют `ament_cmake`.
- В статьях не используются незавершённые фрагменты кода как готовые файлы. Если код надо сохранить в файл, он приводится целиком.

## Диагностика

Если команда ROS 2 не находится:

```bash
source /opt/ros/jazzy/setup.bash
echo $ROS_DISTRO
ros2 doctor
```

Если пакет из workspace не находится:

```bash
cd ros2_ws
source install/setup.bash
ros2 pkg list | grep learning_tf2_py
```

## Внешние Источники

Курс основан на официальных материалах ROS 2 Jazzy:

- [ROS 2 Jazzy Documentation](https://docs.ros.org/en/jazzy/)
- [ROS 2 Jazzy Tutorials](https://docs.ros.org/en/jazzy/Tutorials.html)
- [ROS 2 Jazzy Ubuntu installation](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)

## Служебные Материалы

- [COURSE_AUDIT.md](COURSE_AUDIT.md) - текущий аудит ссылок, покрытия тем и среды запуска.
- [ros2_ws/src](<ros2_ws/src>) - исходники пакетов для проверки практических уроков.
