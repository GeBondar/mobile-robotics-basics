# rosdep: зависимости workspace

Цель: устанавливать системные зависимости ROS 2 пакетов по записям в `package.xml`.

Официальный источник: <https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Rosdep.html>

## 1. Что делает rosdep

`rosdep` читает зависимости пакетов из `package.xml`, сопоставляет ROS-ключи с системными пакетами вашей ОС и устанавливает недостающие зависимости через пакетный менеджер.

Пример зависимости в `package.xml`:

```xml
<exec_depend>rclpy</exec_depend>
<exec_depend>geometry_msgs</exec_depend>
<exec_depend>turtlesim</exec_depend>
```

## 2. Установка и инициализация

```bash
sudo apt update
sudo apt install -y python3-rosdep
```

Первая инициализация на машине:

```bash
sudo rosdep init
rosdep update
```

Если `sudo rosdep init` сообщает, что файл уже существует, повторно выполнять инициализацию не нужно:

```bash
rosdep update
```

## 3. Установка зависимостей workspace

Перейдите в корень workspace:

```bash
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash
```

Установите зависимости всех пакетов в `src`:

```bash
rosdep install -i --from-path src --rosdistro jazzy -y
```

Параметры команды:

- `-i` пропускает зависимости, которые уже установлены;
- `--from-path src` указывает, где искать ROS 2 пакеты;
- `--rosdistro jazzy` выбирает правила для Jazzy;
- `-y` автоматически подтверждает установку apt-пакетов.

Для Humble:

```bash
rosdep install -i --from-path src --rosdistro humble -y
```

## 4. Проверка перед сборкой

```bash
colcon build --symlink-install
```

Если сборка падает из-за отсутствующего пакета, сначала проверьте `package.xml`: зависимость должна быть записана явно.

## 5. Типовые проблемы

### rosdep key not found

Причины:

- зависимость отсутствует в rosdep database;
- имя зависимости записано не ROS-ключом;
- пакет доступен только из исходников.

Решение: проверить название пакета в ROS Index или установить зависимость вручную и зафиксировать это в статье.

### Cannot locate rosdep definition

Проверьте дистрибутив:

```bash
echo $ROS_DISTRO
rosdep install -i --from-path src --rosdistro $ROS_DISTRO -y
```

## Контрольный результат

После выполнения `rosdep install` workspace собирается командой:

```bash
colcon build --symlink-install
```
