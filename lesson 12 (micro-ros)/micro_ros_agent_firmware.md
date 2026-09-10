# Agent, firmware и проверка graph

После описания ROS-контракта можно подключать micro-ROS Agent и firmware. В этой главе важны три вещи: transport, порядок инициализации client-кода и проверка результата обычными ROS 2 CLI-командами.

## Agent, transport и domain

Agent запускается на компьютере, где уже настроено ROS 2 окружение.

UDP-вариант:

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=42
ros2 run micro_ros_agent micro_ros_agent udp4 --port 8888 -v6
```

Serial-вариант:

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=42
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -v6
```

Выбор транспорта:

| Transport | Когда использовать |
|---|---|
| UDP по Wi-Fi | мобильный робот ездит без кабеля |
| UDP по Ethernet | надежная лабораторная сеть |
| Serial по USB-UART | первая отладка firmware на столе |
| USB CDC | плата имеет нативный USB и нужен простой кабельный стенд |

Для Wi-Fi firmware должен знать IP компьютера с Agent. `127.0.0.1` не подходит: для ESP32 это сам ESP32, а не ноутбук.

## Firmware: порядок инициализации

В firmware micro-ROS обычно поднимается в отдельной задаче:

```text
init_messages()
configure_transport()
set_domain_id()
create_node()
create_publishers()
create_subscriptions()
create_executor()
loop:
  publish_telemetry()
  spin_executor()
  check_cmd_vel_timeout()
```

На что обратить внимание:

- строки и массивы сообщений нужно инициализировать заранее;
- `LaserScan.ranges`, `JointState.name`, `JointState.position` требуют выделенной памяти;
- callback `/cmd_vel` не должен долго выполняться;
- управление моторами лучше держать в отдельном control loop;
- при потере `/cmd_vel` firmware должен остановить робота по timeout;
- при потере Agent firmware должен пытаться переподключиться или перейти в безопасный режим.

Пример логики `/cmd_vel`:

```text
cmd_vel_callback(msg):
  target_linear = clamp(msg.linear.x)
  target_angular = clamp(msg.angular.z)
  last_cmd_time = now()

control_loop:
  if now() - last_cmd_time > timeout:
    stop_motors()
  else:
    left, right = diff_drive_inverse_kinematics(target_linear, target_angular)
    set_motor_commands(left, right)
```

Для дифференциальной базы:

```text
v_left  = v_linear - omega * wheel_separation / 2
v_right = v_linear + omega * wheel_separation / 2
```

## Проверка ROS-графа

После запуска Agent и firmware проверьте, что микроконтроллер появился в ROS 2 graph:

```bash
ros2 node list
ros2 topic list -t
```

Проверьте топики:

```bash
ros2 topic info /cmd_vel --verbose
ros2 topic echo /joint_states --once
timeout 8 ros2 topic hz /joint_states || true
timeout 8 ros2 topic hz /imu/data_raw || true
```

Проверьте команду движения только на безопасном стенде:

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.05}, angular: {z: 0.0}}"
sleep 1
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0}, angular: {z: 0.0}}"
```

Если робот едет не туда, не пытайтесь сразу чинить Nav2. Сначала проверьте:

- знак моторов;
- знак энкодеров;
- порядок левого и правого колеса;
- `wheel_radius` и `wheel_separation`;
- ориентацию IMU;
- frame_id и положение датчиков в URDF.

## Резюме

Agent делает firmware видимым в ROS 2 graph, но сам по себе не гарантирует корректное поведение робота. До SLAM и Nav2 нужно отдельно проверить transport, QoS, частоты, знаки моторов, энкодеры и безопасный timeout `/cmd_vel`.

## Следующий шаг

Переходите к [времени, odometry, SLAM и Nav2](micro_ros_navigation_pipeline.md).
