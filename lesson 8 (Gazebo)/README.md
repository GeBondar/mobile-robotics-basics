# Урок 8. Gazebo Harmonic

Раздел курса по симуляции мобильных роботов в **Gazebo Harmonic** с ROS 2 **Jazzy Jalisco**.

Связанный материал: [TurtleBot3 simulation](https://github.com/GeBondar/mobile-robotics-basics/blob/main/lesson%2011%20(turtlebot3%20sim)/README.md).

## Цель урока

Научиться запускать симуляцию мобильного робота в Gazebo Harmonic в связке с ROS 2 Jazzy, перенести топики между шинами через `ros_gz_bridge` и собрать готовый стенд для перехода к Nav2.

К концу урока у вас будет:

* свой пакет `my_robot_gazebo` с **diff-drive** роботом, **лидаром** и **IMU**;
* кастомный мир с препятствиями (`obstacles.sdf`);
* одна команда `ros2 launch my_robot_gazebo spawn_robot.launch.py`, поднимающая всё разом;
* управление с клавиатуры через `teleop_twist_keyboard`;
* топики `/scan`, `/odom`, `/cmd_vel`, `/imu`, `/tf` в ROS 2 — готовые для Nav2.

## Что нужно знать заранее

| Из урока | Что используем |
|----------|----------------|
| Урок 4 | launch-файлы, передача аргументов |
| Урок 5 | URDF, Xacro, инерции |
| Урок 6 | RViz2 displays |
| Урок 7 | tf2: фреймы `odom`, `base_footprint`, `base_link` |

## Порядок прохождения

### Основная часть

| Шаг | Статья | Результат |
|-----|--------|-----------|
| 1 | [Установка Gazebo Harmonic](./01-installation.md) | `gz sim empty.sdf` открывает GUI, `parameter_bridge` пробрасывает `/clock` |
| 2 | [Первый мир и gz CLI](./02-first-world.md) | Свой `empty.sdf` запускается, освоены `gz topic`/`gz model`/`gz service` |
| 3 | [URDF робота и Xacro макросы](./03-urdf-xacro.md) | Diff-drive R2D2 написан на Xacro с переиспользуемыми макросами |
| 4 | [Спавн робота в Gazebo](./04-spawn-robot.md) | Робот появляется в Gazebo, едет по командам через `gz topic` |
| 5 | [Мост Gazebo ↔ ROS 2](./05-bridge.md) | `parameter_bridge` с YAML конфигом переносит топики в DDS |
| 6 | [Сенсоры: лидар и IMU](./06-sensors.md) | `/scan` 10 Гц, `/imu` 100 Гц, точки видны в RViz |
| 7 | [Свой мир и teleop](./07-world-teleop.md) | `obstacles.sdf` + teleop клавиатурой, готов стенд для Nav2 |

### Бонусная часть (углублённо)

| Шаг | Статья | Результат |
|-----|--------|-----------|
| 8 | [Балансирующий робот](./08-balancer.md) | Двухколёсный R2D2 с LQR контроллером (Segway-style) |

Бонусная часть **опциональна**. В ней разбирается:

* Вывод физики перевёрнутого маятника из законов Ньютона.
* Расчёт центра масс из URDF.
* Теория оптимального управления (LQR), pole placement.
* Реализация контроллера на ROS 2.

К ней прилагаются два дополнительных документа:

* [physics_robotics.docx](./physics_robotics.docx) — физика: моменты инерции, центр масс, уравнения движения.
* [lqr_theory.docx](./lqr_theory.docx) — математика: от собственных чисел до уравнения Риккати.

## Пакет в workspace

`my_robot_gazebo` — целиком: Xacro модель, два SDF мира, два launch, YAML bridge, RViz layout, контроллер балансира.

Сборка:

```bash
cd ~/ros2_ws
rosdep install -i --from-path src --rosdistro $ROS_DISTRO -y
colcon build --symlink-install --packages-select my_robot_gazebo
source install/setup.bash
```

## Команды одной шпаргалкой

```bash
# Только симулятор
ros2 launch my_robot_gazebo gazebo.launch.py world:=empty

# Полный сценарий (Gazebo + робот + bridge + RViz)
ros2 launch my_robot_gazebo spawn_robot.launch.py

# Со своим миром
ros2 launch my_robot_gazebo spawn_robot.launch.py world:=obstacles

# Teleop в другом терминале
ros2 run teleop_twist_keyboard teleop_twist_keyboard

# Запись bag для последующего воспроизведения
ros2 bag record -o teleop_run /cmd_vel /odom /scan /imu /tf /tf_static

# Бонус: запуск балансирующего робота
ros2 launch my_robot_gazebo balance.launch.py
```

## Соглашения урока

* Все блоки SDF/URDF приводятся в статьях с прямой ссылкой на цельный файл в workspace.
* Имена плагинов и типов сообщений — именно для **Harmonic** (`gz-sim-*-system`, `gz.msgs.*`). Для Gazebo Classic / `gazebo_ros_pkgs` они другие и здесь не используются.
* Все ROS 2 ноды запускаются с `use_sim_time:=true`, иначе TF и LaserScan «уплывут» во времени.

## Структура пакета

```
my_robot_gazebo/
├── CMakeLists.txt
├── package.xml
├── config/
│   └── ros_gz_bridge.yaml
├── launch/
│   ├── gazebo.launch.py
│   ├── spawn_robot.launch.py
│   └── balance.launch.py          (бонус)
├── scripts/
│   └── balance_controller.py      (бонус)
├── urdf/
│   ├── r2d2.urdf.xacro
│   ├── r2d2_macros.xacro
│   ├── r2d2_properties.xacro
│   └── r2d2_gazebo.xacro
└── worlds/
    ├── empty.sdf
    ├── blue.sdf
    └── obstacles.sdf
```

## После урока

* Урок 9 — **Nav2**: тот же робот, но с глобальным/локальным планировщиком и SLAM.
* Урок 10 — **TurtleBot3**: готовый промышленный аналог, можно сравнить структуру `*.sdf` и плагины.
