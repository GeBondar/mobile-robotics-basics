# Время, odometry, SLAM и Nav2

Когда firmware уже виден в ROS 2 graph, данные нужно подготовить для алгоритмов на хосте. В этой главе путь идет от timestamp и restamp к `/odom`, TF, SLAM и Nav2.

## Время сообщений и restamp

У микроконтроллера и компьютера разные часы. Если ESP32 публикует timestamp по своему внутреннему таймеру, ROS 2 алгоритмы могут считать сообщения слишком старыми или будущими.

Для учебного робота есть два нормальных варианта:

1. синхронизировать время и публиковать корректные timestamp прямо с firmware;
2. на хосте переписывать timestamp сенсорных сообщений в wall time.

Второй вариант проще для старта. Обычно делают отдельные ноды:

| Нода | Вход | Выход |
|---|---|---|
| `joint_state_restamper` | `/joint_states` | `/joint_states_tf` |
| `laser_scan_restamper` | `/scan` | `/scan_wall_time` |

Дальше `robot_state_publisher`, odometry, SLAM, AMCL и costmap используют уже restamp-топики.

## Odometry, TF и SLAM

Минимальный ROS 2 pipeline после micro-ROS:

```text
/joint_states -> restamp -> odometry -> /odom + TF odom -> base_footprint
/scan -> restamp -> slam_toolbox -> /map + TF map -> odom
URDF -> robot_state_publisher -> TF base_footprint -> sensors
```

Проверки:

```bash
ros2 topic echo /odom --once
timeout 8 ros2 topic hz /scan_wall_time || true
timeout 8 ros2 run tf2_ros tf2_echo odom base_footprint || true
```

Для SLAM:

```bash
ros2 launch esp32_cam_robot_bringup slam.launch.py
```

Ожидаемые признаки:

- `/scan_wall_time` обновляется;
- `/odom` обновляется;
- TF `odom -> base_footprint` есть;
- `slam_toolbox` публикует `/map`;
- в RViz карта строится без резких разворотов и скачков.

## Nav2

Nav2 подключайте после того, как отдельно проверены:

- `/cmd_vel` двигает робота в правильную сторону;
- `/joint_states` и `/odom` имеют правильные знаки;
- lidar или дальномер публикует стабильный `/scan`;
- TF-дерево непрерывное;
- карта сохранена и соответствует помещению.

Типовой запуск:

```bash
ros2 launch esp32_cam_robot_bringup nav.launch.py \
  map:=/path/to/map.yaml
```

Проверки:

```bash
ros2 action list | grep navigate_to_pose
timeout 8 ros2 topic hz /odom || true
timeout 8 ros2 topic hz /scan_wall_time || true
timeout 8 ros2 run tf2_ros tf2_echo map base_footprint || true
```

Если Nav2 не едет:

- если `/cmd_vel` не появляется, проблема чаще в AMCL, costmap, lifecycle или TF;
- если `/cmd_vel` есть, но робот не двигается, проблема ближе к firmware, питанию или драйверу моторов;
- если робот едет, но теряется, проверьте карту, lidar, footprint и initial pose.

## Резюме

micro-ROS дает ROS 2 доступ к данным микроконтроллера, но навигация зависит от качества времени, TF, odometry и сенсоров. Поэтому сначала проверяются restamp, `/odom`, `/scan_wall_time` и TF, а уже потом запускаются SLAM и Nav2.

## Следующий шаг

Переходите к [практике, диагностике и зачёту](micro_ros_practice_debug.md).
