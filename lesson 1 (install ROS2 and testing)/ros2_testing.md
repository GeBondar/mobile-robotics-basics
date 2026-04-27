# Проверка установки ROS 2

Цель: убедиться, что установленная среда ROS 2 Jazzy запускает стандартные demo-ноды.

## Подготовка терминалов

Откройте два терминала и в каждом подключите окружение:

```bash
source /opt/ros/jazzy/setup.bash
```

Если вы проверяете Humble, замените `jazzy` на `humble`.

## Проверка publisher/subscriber

В первом терминале запустите talker:

```bash
ros2 run demo_nodes_cpp talker
```

Во втором терминале запустите listener:

```bash
ros2 run demo_nodes_py listener
```

Ожидаемый результат:

- в первом терминале появляются сообщения вида `Publishing: 'Hello World: N'`;
- во втором терминале появляются сообщения вида `I heard: 'Hello World: N'`.

Если listener получает сообщения, базовая установка ROS 2 и DDS discovery работают корректно.

## Быстрая диагностика

```bash
ros2 node list
ros2 topic list
ros2 doctor
```

Если команды `ros2` не находятся, проверьте, что в текущем терминале выполнен `source /opt/ros/jazzy/setup.bash`.
