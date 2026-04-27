# Workspace, colcon и первый пакет

Цель: создать рабочее пространство ROS 2, собрать его через `colcon` и создать минимальный Python-пакет.

Официальные источники:

- <https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Colcon-Tutorial.html>
- <https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Creating-A-Workspace/Creating-A-Workspace.html>
- <https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Creating-Your-First-ROS2-Package.html>

## 1. Установка colcon

```bash
source /opt/ros/jazzy/setup.bash
sudo apt update
sudo apt install -y python3-colcon-common-extensions
```

Проверка:

```bash
colcon --help
```

## 2. Создание workspace

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws
```

Структура:

```text
ros2_ws/
└── src/
```

`src` содержит исходники пакетов. После сборки рядом появятся каталоги `build`, `install` и `log`.

## 3. Создание Python-пакета

```bash
cd ~/ros2_ws/src
ros2 pkg create my_first_py_pkg \
  --build-type ament_python \
  --license Apache-2.0 \
  --node-name hello_node
```

Проверьте структуру:

```bash
tree my_first_py_pkg -L 2
```

Важные файлы:

- `package.xml` - метаданные и зависимости пакета;
- `setup.py` - установка Python-модуля и executable;
- `setup.cfg` - путь установки executable для `ros2 run`;
- `resource/my_first_py_pkg` - marker-файл пакета;
- `my_first_py_pkg/hello_node.py` - Python-нода.

## 4. Сборка workspace

```bash
cd ~/ros2_ws
colcon build --symlink-install
```

Сборка одного пакета:

```bash
colcon build --symlink-install --packages-select my_first_py_pkg
```

## 5. Подключение overlay

```bash
source install/setup.bash
```

Проверка:

```bash
ros2 pkg list | grep my_first_py_pkg
```

## 6. Запуск ноды

```bash
ros2 run my_first_py_pkg hello_node
```

Ожидаемый результат:

```text
Hi from my_first_py_pkg.
```

## 7. Типовой цикл разработки

```bash
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select my_first_py_pkg
source install/setup.bash
ros2 run my_first_py_pkg hello_node
```

## Контрольные вопросы

1. Почему пакеты кладут в `src`, а не в корень workspace?
2. Чем отличается underlay `/opt/ros/jazzy` от overlay `~/ros2_ws/install`?
3. Что произойдёт, если после сборки не выполнить `source install/setup.bash`?
