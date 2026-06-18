# Урок 11. micro-ROS

Цель урока - разобраться, как встроить микроконтроллер в ROS 2 систему через micro-ROS: поднять Agent, описать ROS-сущности на firmware, проверить топики и довести данные до одометрии, SLAM или Nav2.

Практический пример основан на учебном ESP32-CAM стеке мобильного робота. Реальный робот полезен для аппаратной проверки, но не обязателен: архитектуру, ROS-контракт, Agent, transport и диагностику можно разобрать без конкретного железа.

## Порядок прохождения

| Шаг | Статья | Результат |
|---:|---|---|
| 1 | [micro-ROS в стеке ESP32-CAM робота](micro_ros_esp32_stack.md) | Понятны роли micro-ROS Client, Agent, transport и ROS 2 graph |
| 2 | [ROS-контракт микроконтроллера](micro_ros_contract.md) | Описаны команды, сенсорные топики, QoS, timestamp и структура проекта |
| 3 | [Agent, firmware и проверка graph](micro_ros_agent_firmware.md) | Запущен Agent, понятен порядок инициализации firmware и CLI-проверки |
| 4 | [Время, odometry, SLAM и Nav2](micro_ros_navigation_pipeline.md) | Собран путь от timestamp и restamp до `/odom`, TF, SLAM и Nav2 |
| 5 | [Практика, диагностика и зачёт](micro_ros_practice_debug.md) | Подготовлен сценарий без железа, разобраны типовые ошибки и вопросы |

## Что нужно знать заранее

Перед уроком рекомендуется пройти:

- [ноды и топики](<../lesson 2 (nodes and topics)/README.md>);
- [сервисы и действия](<../lesson 3 (actions and services)/README.md>);
- [launch-файлы и параметры](<../lesson 4 (launches and parameters)/README.md>);
- [tf2](<../lesson 7 (TF2)/README.md>);
- [TurtleBot3 simulation](<../lesson 10 (turtlebot3 sim)/README.md>) или другой материал про мобильного робота в ROS 2.

Для практики понадобится ROS 2 Jazzy.

## После урока

Студент должен уметь:

- объяснить роли micro-ROS Client, micro-ROS Agent, XRCE-DDS и ROS 2 graph;
- поднять Agent по UDP или serial и проверить подключение клиента через `ros2 node list` и `ros2 topic list`;
- читать и интерпретировать топики `cmd_vel`, `joint_states`, `imu/data_raw`, `scan`, `odom`;
- объяснить, зачем на хосте нужны restamp-узлы для сообщений с микроконтроллера;
- безопасно проверить движение дифференциального робота и подготовить данные для SLAM/Nav2.
