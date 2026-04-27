# ros2 bag: запись и воспроизведение данных

Цель: записать данные из топика ROS 2, посмотреть метаданные записи и воспроизвести её.

Официальный источник: <https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Recording-And-Playing-Back-Data/Recording-And-Playing-Back-Data.html>

## 1. Подготовка

Проверьте, что установлен `rosbag2`:

```bash
source /opt/ros/jazzy/setup.bash
ros2 bag --help
```

Если команда недоступна:

```bash
sudo apt update
sudo apt install -y ros-jazzy-rosbag2
```

## 2. Запуск turtlesim

Терминал 1:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run turtlesim turtlesim_node
```

Терминал 2:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run turtlesim turtle_teleop_key
```

Управляйте черепахой стрелками. Teleop публикует команды скорости в топик `/turtle1/cmd_vel`.

## 3. Выбор топика

Терминал 3:

```bash
source /opt/ros/jazzy/setup.bash
ros2 topic list
ros2 topic info /turtle1/cmd_vel
```

Тип топика:

```text
geometry_msgs/msg/Twist
```

## 4. Запись одного топика

```bash
mkdir -p ~/ros2_bag_files
cd ~/ros2_bag_files
ros2 bag record /turtle1/cmd_vel
```

Вернитесь в терминал teleop и подвигайте черепаху 10-15 секунд. Затем остановите запись через `Ctrl+C`.

В каталоге появится папка вида:

```text
rosbag2_YYYY_MM_DD-HH_MM_SS/
```

## 5. Просмотр информации о записи

```bash
ros2 bag info rosbag2_YYYY_MM_DD-HH_MM_SS
```

Проверьте:

- duration;
- storage identifier;
- topic `/turtle1/cmd_vel`;
- message count.

## 6. Воспроизведение

Остановите teleop, оставьте `turtlesim_node` запущенным.

```bash
ros2 bag play rosbag2_YYYY_MM_DD-HH_MM_SS
```

Черепаха повторит записанные команды движения.

## 7. Запись нескольких топиков

```bash
ros2 bag record /turtle1/cmd_vel /turtle1/pose
```

Запись всех топиков:

```bash
ros2 bag record -a
```

Для учебных работ не используйте `-a` без необходимости: запись быстро растёт и может содержать лишние данные.

## 8. Практическое задание

1. Запишите движение по квадрату через teleop или свою ноду-публикатор.
2. Остановите все управляющие ноды.
3. Воспроизведите запись через `ros2 bag play`.
4. Сравните траекторию с исходной.

## Контрольный результат

- Создан bag-каталог.
- `ros2 bag info` показывает топик `/turtle1/cmd_vel`.
- `ros2 bag play` воспроизводит движение в `turtlesim`.
