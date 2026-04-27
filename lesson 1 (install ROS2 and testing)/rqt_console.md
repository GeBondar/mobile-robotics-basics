# rqt_console и уровни логирования

Цель: просматривать сообщения логирования ROS 2 в графическом интерфейсе и менять уровень логов у ноды.

Официальный источник: <https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Using-Rqt-Console/Using-Rqt-Console.html>

## 1. Установка

Для ROS 2 Jazzy:

```bash
sudo apt update
sudo apt install -y ros-jazzy-rqt-console ros-jazzy-rqt-logger-level
```

Для Humble замените `jazzy` на `humble`.

## 2. Запуск rqt_console

Терминал 1:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run rqt_console rqt_console
```

Откроется окно `rqt_console`. Оно показывает сообщения, которые ноды публикуют в систему логирования ROS 2.

## 3. Генерация логов через turtlesim

Терминал 2:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run turtlesim turtlesim_node
```

Терминал 3:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run turtlesim turtle_teleop_key
```

Управляйте черепахой стрелками. Если черепаха упирается в границу окна, `turtlesim` публикует warning-сообщения. Они появятся в `rqt_console`.

## 4. Фильтрация

В `rqt_console` используйте фильтры:

- по уровню логирования: `Info`, `Warn`, `Error`;
- по имени ноды;
- по тексту сообщения.

Практическая проверка: оставьте только warning-сообщения от `turtlesim`.

## 5. Изменение уровня логирования

Запустите настройку уровней:

```bash
ros2 run rqt_logger_level rqt_logger_level
```

Выберите ноду `/turtlesim` и установите уровень `Warn`. После этого информационные сообщения этой ноды перестанут отображаться, а warning/error останутся.

## 6. Проверка через CLI

Список логгеров ноды:

```bash
ros2 service list | grep logger
```

Логи в ROS 2 также доступны через топик:

```bash
ros2 topic echo /rosout
```

## Контрольный результат

- `rqt_console` показывает логи от активных нод.
- Warning от `turtlesim` можно отфильтровать.
- Уровень логирования меняется через `rqt_logger_level`.
