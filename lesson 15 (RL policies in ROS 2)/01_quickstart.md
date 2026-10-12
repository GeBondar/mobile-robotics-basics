# Запуск: ЦАПЛЯ-2 идёт по /cmd_vel

**Цель:** собрать пакеты урока, запустить робота в MuJoCo и его политику как две ноды ROS 2 и
вести робота с клавиатуры через `/cmd_vel`. Результат: окно MuJoCo с двуногим, который идёт
по команде; `ros2 topic hz /joint_commands` показывает 50 Гц.

Проверено на Ubuntu 22.04 в WSL2 (Windows 11, WSLg), ROS 2 Humble, Python 3.10.12,
mujoco 3.9.0, onnxruntime 1.23.2, opencv-python-headless 4.10.0.84. На Jazzy не запускалось.

## Минимальная теория

Обученная политика — это функция «вектор наблюдения → вектор действия». Чтобы она работала
вне среды обучения, кто-то должен собрать тот же вектор из того, что реально есть у робота.
В ROS 2 это значит: из `JointState`, `Imu`, `Odometry` и команды `Twist`.

Всё, что для этого нужно знать о политике, кроме весов, называется **контрактом**: порядок и
масштаб каналов, внутренние часы, прошлое действие, фильтр команд. Для ЦАПЛИ-2 контракт
включает три вещи, которых нет ни в одном топике:

- **фазовые часы** — синус и косинус фазы шага, частота зависит от команды скорости;
- **контур курса** — поправка угловой команды по ошибке курса (`wz_eff`);
- **прошлое действие двухтактной давности** — в среде наблюдение собирается до того, как
  обновляется `prev_act`, и нода обязана повторить это буквально.

Контракт ЦАПЛИ — класс `Tsaplya2Contract` в
[contracts.py](<../ros2_ws/src/rl_policy_ros/rl_policy_ros/contracts.py>), каждая строка со
ссылкой на строки среды обучения.

Робот с точечными стопами не стоит сам. Поэтому `sim_node` держит корпус «на подвесе», пока
не придёт первая команда приводам, — так же двуногих включают на кране.

## Установка

Зависимости Python ставятся pip-ом поверх системного Python ROS:

```bash
pip3 install --user mujoco==3.9.0 onnxruntime==1.23.2 opencv-python-headless==4.10.0.84
```

На Ubuntu 24.04 (Jazzy) pip без venv запрещён (PEP 668). Добавьте
`--break-system-packages`; вариант с venv для ROS 2 в курсе пока не проверен.

ROS-пакеты для управления и просмотра:

```bash
sudo apt install ros-$ROS_DISTRO-teleop-twist-keyboard ros-$ROS_DISTRO-rqt-image-view python3-colcon-common-extensions
```

Сборка — из `ros2_ws` курса:

```bash
cd ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
colcon build --symlink-install --packages-select rl_policy_interfaces rl_policy_ros
source install/setup.bash
```

Если репозиторий лежит на диске Windows (`/mnt/c/...`), сборка там медленная. Удобнее сделать
workspace в домашнем каталоге WSL со ссылками на пакеты:

```bash
mkdir -p ~/l15_ws/src && cd ~/l15_ws/src
ln -s "/mnt/c/путь/к/mobile-robotics-basics/ros2_ws/src/rl_policy_interfaces" .
ln -s "/mnt/c/путь/к/mobile-robotics-basics/ros2_ws/src/rl_policy_ros" .
cd ~/l15_ws && colcon build --symlink-install && source install/setup.bash
```

## Запуск

Робот и политика одной командой. Откроется окно MuJoCo: ЦАПЛЯ-2 на подвесе и четыре
ArUco-маркера на стойках.

```bash
ros2 launch rl_policy_ros walk.launch.py
```

Во втором терминале (после `source install/setup.bash`) — клавиатура:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

Клавиши: `i` — вперёд, `,` — назад, `j` / `l` — поворот на месте, `k` — стоп, `x` — медленнее.
Команды за пределами полосы обучения контракт обрезает: скорость до ±0.86 м/с, боком до
±0.17 м/с, поворот до ±0.6 рад/с, разгон не быстрее 1.2 м/с².

То же раздельно, по нодам — так удобнее менять параметры:

```bash
ros2 run rl_policy_ros sim_node --ros-args -p robot:=tsaplya2 -p world:=tsaplya_aruco.yaml -p viewer:=true -p use_sim_time:=true
```

```bash
ros2 run rl_policy_ros policy_node --ros-args -p robot:=tsaplya2 -p use_sim_time:=true -p cmd_timeout_s:=1000.0
```

`cmd_timeout_s` — deadman: если `/cmd_vel` не приходил дольше, команда считается нулевой.
По умолчанию 0.5 с, но `teleop_twist_keyboard` шлёт сообщение только при нажатии, поэтому
для ручного управления deadman отключён.

## Ожидаемый результат

В терминале `sim_node`:

```
[sim_node]: робот tsaplya2: 8 приводов, шаг физики 2.0 мс, камера 'front_camera', объектов мира 5
[sim_node]: первая команда получена — подвес снят
[sim_node]: симуляция: x1.00 реального времени, просадок 0, худшее отставание ...
```

В терминале `policy_node` — имя политики, её сигнатура и метаданные ONNX, затем раз в 10 с
статистика:

```
[policy_node]: политика walk: tsaplya2_walk.onnx [1, 35]->[1, 8] {... 'robot': 'tsaplya2'}
[policy_node]: инференс walk: медиана 122 мкс, p99 286 мкс | период: медиана 18.0 мс, ...
```

Замер на машине курса: команда 0.5 м/с вперёд, 8 с после разгона — 0.575 м/с по `/odom`,
без падений.

**Известная проблема.** В части прогонов процессы нод периодически замирают на 20–70 мс
(сама WSL при этом ровная: цикл со сном 2 мс за 20 с не дал ни одного разрыва больше 2.7 мс).
Для ЦАПЛИ такая пауза — пропуск трёх тактов управления, и в таких прогонах она падает через
10–15 с. Причина ищется. Если робот упал:

```bash
ros2 service call /sim/reset std_srvs/srv/Trigger
```

```bash
ros2 service call /set_policy rl_policy_interfaces/srv/SetPolicy "{name: auto}"
```

Сначала сброс (робот снова на подвесе), потом включение политики: упавшая политика молчит,
чтобы не снять подвес раньше времени.

## Контрольные проверки

1. Частота управления:

   ```bash
   ros2 topic hz /joint_commands
   ```

   Ожидается около 50 Гц — частота, на которой политика обучена. `/joint_states` — 100 Гц,
   `/odom` — 50 Гц, `/clock` — 200 Гц.

2. Граф: `rqt_graph` показывает `/teleop_twist_keyboard → /cmd_vel → /policy_node →
   /joint_commands → /sim_node`, и обратно топики робота.

3. Наблюдение уходит наружу — его можно записать в `ros2 bag` и сверить со средой:

   ```bash
   ros2 topic echo /policy/obs --once
   ```

   35 чисел. Первые три — гравитация в раме корпуса, у стоящего робота около `[0, 0, -1]`.

4. Толчок корпуса — проверка устойчивости:

   ```bash
   ros2 topic pub --once /sim/push geometry_msgs/msg/Vector3 "{x: 0.0, y: 0.4, z: 0.0}"
   ```

5. Камера робота:

   ```bash
   ros2 run rqt_image_view rqt_image_view /camera/image_raw
   ```

   Поверните робота клавишами `j`/`l`, пока в кадре не окажется маркер.

## Итог

- Политика живёт в ROS 2 без Gym и SB3: ONNX + контракт + таймер на частоте обучения.
- Робот в MuJoCo публикует только то, что дал бы настоящий, — поэтому этот же `policy_node`
  годится и для железа.
- Частота и задержки — часть контракта: пауза в 60 мс роняет двуногого так же надёжно,
  как перепутанный канал наблюдения.

Следующая статья: контракт политики и его сверка со средой без ROS — пишется.
Оглавление урока — [README.md](README.md).
