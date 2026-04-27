# Настройка окружения ROS 2

Цель: понять, зачем в ROS 2 используется `source`, чем underlay отличается от overlay, и как проверить переменные окружения.

Официальный источник: <https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Configuring-ROS2-Environment.html>

## 1. Underlay

Underlay - это базовая установленная среда ROS 2. Для Jazzy при установке из deb-пакетов она находится в `/opt/ros/jazzy`.

Подключите underlay:

```bash
source /opt/ros/jazzy/setup.bash
```

Проверьте переменные:

```bash
printenv | grep -i ROS
```

Минимально ожидаемые переменные:

```text
ROS_VERSION=2
ROS_PYTHON_VERSION=3
ROS_DISTRO=jazzy
```

## 2. Автоматическое подключение

Чтобы не выполнять `source` вручную в каждом новом терминале:

```bash
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
```

Откройте новый терминал и проверьте:

```bash
echo $ROS_DISTRO
```

Для Humble команда отличается только именем дистрибутива:

```bash
source /opt/ros/humble/setup.bash
```

## 3. Overlay workspace

Overlay - это ваш рабочий workspace, который расширяет underlay. В курсе используется `ros2_ws`.

Сначала подключается underlay, затем overlay:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
source install/setup.bash
```

Порядок важен: overlay должен подключаться после сборки workspace и после underlay.

## 4. Типовой цикл работы

```bash
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
ros2 pkg list | grep my_turtle_controller
```

Если пакет не находится, проверьте:

```bash
pwd
ls src
ls install
source install/setup.bash
```

## 5. ROS_DOMAIN_ID

`ROS_DOMAIN_ID` разделяет ROS 2 graph между разными студентами или разными экспериментами в одной сети.

Пример:

```bash
export ROS_DOMAIN_ID=17
```

Для постоянной настройки:

```bash
echo "export ROS_DOMAIN_ID=17" >> ~/.bashrc
```

Используйте значение от `0` до `101` для обычных учебных задач.

## Контрольная проверка

```bash
echo $ROS_DISTRO
echo $ROS_DOMAIN_ID
ros2 node list
```

Если ROS 2 установлен и окружение подключено, команда `ros2 node list` выполнится без ошибки, даже если список нод пуст.
