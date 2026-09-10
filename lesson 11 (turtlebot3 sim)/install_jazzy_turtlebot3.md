Вот пошаговая инструкция по установке TurtleBot3 Simulations для ROS 2 Jazzy на русском языке.

---

## Установка TurtleBot3 Simulations для ROS 2 Jazzy

### 1. Убедитесь, что ROS 2 Jazzy установлен
Если ROS 2 Jazzy ещё не установлен, выполните официальную инструкцию:
[Установка ROS 2 Jazzy](https://docs.ros.org/en/jazzy/Installation.html)

После установки проверьте, что окружение настроено:
```bash
source /opt/ros/jazzy/setup.bash
```

---

### 2. Установите зависимости TurtleBot3 и Gazebo
```bash
sudo apt update
sudo apt install ros-jazzy-turtlebot3* ros-jazzy-gazebo-ros-pkgs
```

---

### 3. Создайте рабочее пространство и клонируйте репозиторий
```bash
mkdir -p ~/turtlebot3_ws/src
cd ~/turtlebot3_ws/src
git clone -b jazzy https://github.com/ROBOTIS-GIT/turtlebot3_simulations.git
```

Если ветка `jazzy` отсутствует, проверьте доступные ветки:
```bash
cd turtlebot3_simulations
git branch -a
```
Возможно, нужна ветка `main` или `rolling`. При необходимости замените `jazzy` на актуальную.

---

### 4. Установите недостающие зависимости через rosdep
```bash
cd ~/turtlebot3_ws
rosdep install --from-paths src --ignore-src -r -y
```
Если `rosdep` не инициализирован, выполните:
```bash
sudo rosdep init
rosdep update
```

---

### 5. Соберите рабочее пространство
```bash
cd ~/turtlebot3_ws
colcon build --symlink-install
```

Если сборка прерывается ошибками, попробуйте:
```bash
colcon build --symlink-install --packages-select turtlebot3_gazebo
```

---

### 6. Настройте окружение
Добавьте в файл `~/.bashrc` следующие строки:
```bash
echo "source ~/turtlebot3_ws/install/setup.bash" >> ~/.bashrc
echo "export TURTLEBOT3_MODEL=burger" >> ~/.bashrc
echo "export GAZEBO_MODEL_PATH=\$GAZEBO_MODEL_PATH:~/turtlebot3_ws/src/turtlebot3_simulations/turtlebot3_gazebo/models" >> ~/.bashrc
```

Примените изменения:
```bash
source ~/.bashrc
```

> **Примечание:** Модель может быть `burger`, `waffle` или `waffle_pi`. Выберите нужную.

---

### 7. Проверьте установку
Запустите пустой мир Gazebo:
```bash
ros2 launch turtlebot3_gazebo empty_world.launch.py
```

Если мир загрузился, установка прошла успешно.

---

### 8. Запуск примеров симуляции
**Мир с домом:**
```bash
ros2 launch turtlebot3_gazebo turtlebot3_house.launch.py
```

**Управление роботом с клавиатуры (в новом терминале):**
```bash
ros2 run turtlebot3_teleop teleop_keyboard
```

---

### Возможные проблемы и их решение

| Проблема | Решение |
|----------|--------|
| Ветка `jazzy` не найдена при клонировании | Используйте `-b main` или `-b rolling` вместо `-b jazzy` |
| Ошибка `colcon: command not found` | Установите colcon: `sudo apt install python3-colcon-common-extensions` |
| Нет модели робота в Gazebo | Проверьте переменную `GAZEBO_MODEL_PATH`: `echo $GAZEBO_MODEL_PATH` |
| Не запускается `ros2 launch` | Убедитесь, что sourced `setup.bash` из вашего workspace |

---

Если у вас возникнут ошибки на каком-то шаге, пришлите текст ошибки — я помогу их исправить.
