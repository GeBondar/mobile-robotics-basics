# ROS-контракт микроконтроллера

Перед firmware-кодом нужно описать ROS-интерфейс. Это такой же важный шаг, как выбор пинов или драйвера моторов: если контракт неясный, остальные ноды будут получать непредсказуемые данные.

## Что входит в контракт

Нужно заранее определить:

1. какие команды приходят с компьютера;
2. какие данные публикует микроконтроллер;
3. какие типы сообщений используются;
4. какой QoS нужен для каждого топика;
5. какие `frame_id` и timestamp будут у сенсорных сообщений.

Минимальный контракт для дифференциальной базы:

| Направление | Топик | Тип | Назначение |
|---|---|---|---|
| ROS 2 -> ESP32 | `/cmd_vel` | `geometry_msgs/msg/Twist` | команда линейной и угловой скорости |
| ESP32 -> ROS 2 | `/joint_states` | `sensor_msgs/msg/JointState` | положение и скорость колес |
| ESP32 -> ROS 2 | `/imu/data_raw` | `sensor_msgs/msg/Imu` | ускорения и угловая скорость |
| ESP32 -> ROS 2 | `/scan` | `sensor_msgs/msg/LaserScan` | дальномер или lidar |
| ESP32 -> ROS 2 | `/battery_voltage` | `std_msgs/msg/Float32` | напряжение питания |
| ESP32 -> ROS 2 | `/firmware_heartbeat` | `std_msgs/msg/Bool` | признак, что firmware жив |

Дополнительные команды можно добавлять отдельно:

| Направление | Топик | Тип | Назначение |
|---|---|---|---|
| ROS 2 -> ESP32 | `/lights_command` | `std_msgs/msg/Bool` | включить или выключить дополнительный выход |
| ROS 2 -> ESP32 | `/imu_calibrate_command` | `std_msgs/msg/Bool` | запустить калибровку IMU |
| ROS 2 -> ESP32 | `/aux_demand_mask` | `std_msgs/msg/Int16` | запросить питание дополнительных датчиков |

Для сенсоров часто выбирают best-effort QoS: лучше получить свежий следующий пакет, чем задерживать систему ради старого сообщения. Для команд движения важно проверять задержку и timeout на стороне firmware.

## Типовая структура проекта

Пример структуры проекта:

```text
esp32_cam_micro_ros_robot/
  firmware/
    esp32cam/
      platformio.ini
      sdkconfig.defaults
      src/
        main.c
        microros_node.c
        motor_control.c
        sensors.c
  ros2_ws/
    src/
      esp32_cam_robot_description/
      esp32_cam_robot_base/
      esp32_cam_robot_bringup/
      esp32_cam_robot_navigation/
```

Роли частей:

| Часть | Что содержит |
|---|---|
| `firmware/esp32cam` | ESP-IDF или PlatformIO firmware, micro-ROS client, драйверы моторов и датчиков |
| `description` | URDF/Xacro, фреймы `base_link`, `base_footprint`, `laser_link`, `imu_link` |
| `base` | restamp, odometry, фильтры и вспомогательные ROS 2 ноды |
| `bringup` | launch-файлы для Agent, robot_state_publisher, odometry, RViz |
| `navigation` | параметры SLAM, map server, AMCL, Nav2 |

Имена пакетов могут быть любыми, но разделение помогает не смешивать firmware, описание робота и высокоуровневые алгоритмы.

## Результат

После этой главы у проекта должна быть таблица топиков микроконтроллера и понятная структура пакетов. Дальше можно запускать Agent и проверять, появляется ли firmware в ROS 2 graph.

## Следующий шаг

Переходите к [Agent, firmware и проверке graph](micro_ros_agent_firmware.md).
