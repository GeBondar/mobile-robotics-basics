# Справочник ошибок курса

Этот файл устроен как поисковый указатель. **Заголовок подраздела — дословный текст ошибки**, такой, каким его видит студент в терминале. Ищите по Ctrl+F: скопируйте строку ошибки из терминала и вставьте в поиск по этой странице.

Под каждым заголовком три блока:

- **Почему** — что на самом деле произошло;
- **Как проверить** — команды, которые подтверждают или опровергают гипотезу;
- **Как починить** — минимальное действие.

Основной курс — [README.md](README.md). Раздел «Диагностика» в README оставлен как короткая шпаргалка на два самых частых случая; полный разбор здесь.

## Как читать пометки

| Пометка | Что значит |
|---|---|
| **проверено** | команда фактически выполнена при написании этого файла, вывод приведён дословно |
| **из статьи** | взято из статьи курса, ссылка рядом |
| **из разбора** | измерено в разборе боевых RL-проектов, числа приведены как есть |
| **не замерено** | числа неизвестны, оценка не приводится намеренно |

## Среда, на которой проверялись команды

Всё, что помечено «проверено», выполнено на машине разработчика курса:

| Что | Значение |
|---|---|
| Хост | Windows 11 Pro 10.0.26200 |
| Linux | WSL2, Ubuntu 22.04, ROS 2 **Humble** в `/opt/ros/humble` |
| Python (Windows) | 3.12.3 |
| torch | 2.6.0+cu124, `torch.version.cuda` = 12.4 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU, `torch.cuda.is_available()` = `True` |
| mujoco | 3.9.0 |
| gymnasium | 1.0.0 |
| stable_baselines3 | 2.4.1 |
| numpy | 2.0.2 |
| CPU | 24 логических ядра |
| git | 2.21.0.windows.1 |

Важная оговорка: основная версия курса — **Jazzy на Ubuntu 24.04**, а на машине разработчика стоит **Humble на Ubuntu 22.04**. Поэтому в проверенных выводах встречается `humble` и путь `/opt/ros/humble`. Текст самих сообщений ROS 2 от дистрибутива не зависит; для Jazzy подставляйте `jazzy` вместо `humble` или используйте `$ROS_DISTRO`.

---

## Топ-5 ошибок, которые ловят почти всех

| # | Что видит студент | Одна строка лечения | Раздел |
|---:|---|---|---|
| 1 | `ros2: command not found` | `source /opt/ros/$ROS_DISTRO/setup.bash` | [ROS 2 и окружение](#ros-2-и-окружение) |
| 2 | GUI-окно не открывается в WSL2, ошибок нет | проверить `$DISPLAY` и `$WAYLAND_DISPLAY`, обновить WSL до WSLg | [WSL2 и GUI](#wsl2-и-gui) |
| 3 | `Package 'имя' not found` после успешной сборки | `source install/setup.bash` из корня workspace | [colcon и rosdep](#colcon-и-rosdep) |
| 4 | Окно Gazebo чёрное или не открывается | `LIBGL_ALWAYS_SOFTWARE=1 gz sim empty.sdf` | [Gazebo](#gazebo) |
| 5 | `torch.cuda.is_available()` возвращает `False` | поставить колесо torch с суффиксом `+cuXXX`, а не CPU-сборку | [CUDA и torch](#cuda-и-torch) |

---

## ROS 2 и окружение

### `ros2: command not found`

Полный вид в bash:

```text
bash: ros2: command not found
```

**Почему.** ROS 2 не добавляется в `PATH` при установке. Он появляется только после подключения setup-файла в текущем терминале. Каждый новый терминал начинается заново.

**Как проверить.** Проверено на WSL2 Ubuntu 22.04:

```bash
ls /opt/ros
```

Если каталог с именем дистрибутива есть (`jazzy` или `humble`) — ROS 2 установлен, дело только в `source`. Если каталога нет — ROS 2 не установлен, идите в [установку](<lesson 1 (install ROS2 and testing)/ros2_jazzy_install.md>).

Дословно проверенный вывод до и после подключения:

```text
=== before source
ROS_DISTRO=[]
bash: ros2: command not found
=== after source
ROS_DISTRO=[humble]
ROS_VERSION=[2] ROS_PYTHON_VERSION=[3]
/opt/ros/humble/bin/ros2
```

**Как починить.**

```bash
source /opt/ros/jazzy/setup.bash
echo $ROS_DISTRO
```

Чтобы не повторять в каждом терминале — из статьи [Настройка окружения ROS 2](<lesson 1 (install ROS2 and testing)/ros2_environment.md>):

```bash
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
```

Отдельная ловушка: `~/.bashrc` не читается неинтерактивной оболочкой. Если вы запускаете команды через `wsl.exe -- bash -c ...` или из скрипта, `source` придётся писать явно — это ровно то, что произошло при проверке выше.

### `ROS_DISTRO` пустой

**Почему.** То же самое, что и выше, но замечено раньше: `ros2` мог найтись из другого источника (например, из другого workspace), а переменные окружения не выставлены.

**Как проверить.** Из статьи [ros2doctor](<lesson 1 (install ROS2 and testing)/ros2_doctor.md>):

```bash
printenv | grep -i ROS
```

Минимально ожидаемое (проверено):

```text
ROS_VERSION=2
ROS_PYTHON_VERSION=3
ROS_DISTRO=jazzy
```

**Как починить.** `source /opt/ros/jazzy/setup.bash`. Если после этого `ROS_DISTRO` всё ещё пуст — вы подключили setup-файл workspace (`install/setup.bash`) без предварительного подключения underlay. Порядок обязателен: сначала underlay, потом overlay.

### `Package 'my_turtle_controller' not found`

Так отвечает `ros2 run`. Проверено:

```bash
ros2 run my_turtle_controller talker
```

```text
Package 'my_turtle_controller' not found
```

**Почему.** Три причины, по частоте:

1. workspace собран, но `source install/setup.bash` не выполнен;
2. `source install/setup.bash` выполнен не из корня workspace, а из случайного каталога;
3. пакет не собрался (`colcon build` завершился с ошибкой, а её не прочитали).

**Как проверить.**

```bash
cd ~/ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
source install/setup.bash
ros2 pkg list | grep my_turtle_controller
```

Проверено: на чистом underlay `ros2 pkg list | wc -l` дал 196 пакетов — это только `/opt/ros/humble`, ни одного своего. Если ваше число совпадает с «чистым» и после `source install/setup.bash`, значит overlay не подключился.

**Как починить.** Пересобрать и переподключить, из статьи [Workspace, colcon и первый пакет](<lesson 2 (nodes and topics)/workspace_colcon_package.md>):

```bash
cd ~/ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
colcon build --symlink-install --packages-select my_turtle_controller
source install/setup.bash
ros2 run my_turtle_controller talker
```

### `Package not found`

Так, без имени пакета, отвечает `ros2 pkg prefix`. Проверено:

```bash
ros2 pkg prefix my_turtle_controller
```

```text
Package not found
```

**Почему и как чинить** — то же самое, что в предыдущем подразделе. Отличие только в том, что сообщение не называет пакет, поэтому по нему тяжело искать: имейте в виду, что это та же ошибка.

### `Package 'nav2_bringup' not found: "package 'nav2_bringup' not found, searching: ['/opt/ros/jazzy']"`

Так отвечает `ros2 launch`. Проверено (в проверке подставился `humble`):

```text
Package 'nav2_bringup' not found: "package 'nav2_bringup' not found, searching: ['/opt/ros/humble']"
```

**Почему.** Это самое полезное сообщение из всех трёх, потому что оно печатает **список каталогов, где искали**. Если в списке только `/opt/ros/<distro>` — overlay не подключён. Если в списке есть ваш `install`, а пакет всё равно не найден — пакет действительно не установлен (для Nav2: не поставлен `ros-jazzy-navigation2 ros-jazzy-nav2-bringup`).

**Как проверить.**

```bash
echo $AMENT_PREFIX_PATH
ros2 pkg list | grep nav2
```

**Как починить.** Либо подключить overlay, либо доустановить пакет apt-ом.

### Ноды не видят друг друга

Симптом: в одном терминале `ros2 topic list` показывает топики, в другом — пусто; talker и listener не общаются.

**Почему.** Разные `ROS_DOMAIN_ID` в терминалах. Проверено: по умолчанию переменная **не выставлена вообще** (`ROS_DOMAIN_ID=[]`), и это нормально — тогда используется домен 0. Проблема появляется, когда в одном терминале переменная задана, а в другом нет.

**Как проверить.** Из статьи [ros2doctor](<lesson 1 (install ROS2 and testing)/ros2_doctor.md>), во всех терминалах:

```bash
echo $ROS_DOMAIN_ID
```

**Как починить.** Сделать значение одинаковым, из статьи [Настройка окружения ROS 2](<lesson 1 (install ROS2 and testing)/ros2_environment.md>):

```bash
export ROS_DOMAIN_ID=17
echo "export ROS_DOMAIN_ID=17" >> ~/.bashrc
```

Диапазон для учебных задач — от `0` до `101`.

Вторая по частоте причина того же симптома в WSL2 — разные экземпляры WSL или запуск одной ноды в Windows, а другой в Linux. ROS 2 в курсе живёт **только внутри Linux**.

### `ros2 doctor` печатает предупреждения

**Почему.** Предупреждения `ros2 doctor` не всегда означают неисправность — так прямо сказано в статье [ros2doctor](<lesson 1 (install ROS2 and testing)/ros2_doctor.md>). Но прочитать их надо.

**Как проверить.**

```bash
ros2 doctor
ros2 doctor --report
ros2 doctor --report | grep -i distro
```

Смотрите блоки: platform information, ROS distro, environment variables, network configuration, RMW middleware, topic/service/action graph.

**Как починить.** `ros2 doctor` полезнее всего запускать **третьим терминалом при работающей системе** — тогда он проверяет не только установку, но и живой граф. Сценарий из статьи: терминал 1 — `ros2 run turtlesim turtlesim_node`, терминал 2 — `ros2 run turtlesim turtle_teleop_key`, терминал 3 — `ros2 doctor`.

---

## WSL2 и GUI

### Окно turtlesim, RViz2 или Gazebo не открывается, при этом в терминале нет ошибок

**Почему.** GUI из WSL2 работает через WSLg. Если WSLg нет (старая сборка WSL, Windows 10 без обновлений) или переменные окружения не выставлены, приложение стартует и молча никуда не рисует.

**Как проверить.** Из статьи [Windows + WSL2](<lesson 1 (install ROS2 and testing)/windows_wsl2_jazzy_install.md>):

```bash
echo $DISPLAY
echo $WAYLAND_DISPLAY
```

Проверено на рабочей машине (WSL2, Windows 11):

```text
DISPLAY=[:0] WAYLAND_DISPLAY=[wayland-0]
```

Дополнительные признаки живого WSLg (проверено, оба присутствуют):

```bash
ls -d /mnt/wslg      # каталог WSLg
ls /dev/dxg          # проброс GPU в WSL2
```

Если `$DISPLAY` пуст — WSLg не поднялся.

**Как починить.**

1. Обновить WSL из PowerShell с правами администратора: `wsl --update`, затем `wsl --shutdown` и заново открыть Ubuntu.
2. Проверить версию дистрибутива — она должна быть 2:

```powershell
wsl --list --verbose
```

Проверено, вывод на этой машине:

```text
  NAME            STATE      VERSION
* Ubuntu-22.04    Stopped    2
```

3. На Windows 10 WSLg может отсутствовать. Из статьи: тогда нужен внешний X-сервер или полноценная VM Ubuntu 24.04.

### Сборка `colcon build` в WSL2 идёт очень медленно

**Почему.** Репозиторий лежит в файловой системе Windows и виден из Linux через `/mnt/c/...`. Каждое обращение к файлу идёт через прослойку 9P, и `colcon`, который трогает тысячи мелких файлов, упирается именно в неё.

**Как проверить.**

```bash
pwd
```

Если путь начинается с `/mnt/c/` — вы собираете через прослойку.

**Как починить.** Из статьи [Windows + WSL2](<lesson 1 (install ROS2 and testing)/windows_wsl2_jazzy_install.md>): для максимальной скорости сборки держите рабочую копию внутри Linux-файловой системы, например в `~/mobile-robotics-basics`. Насколько именно быстрее — **не замерено**.

### Команда из статьи не выполняется в PowerShell

Симптом: строка `source /opt/ros/jazzy/setup.bash` в PowerShell даёт ошибку про неизвестный командлет.

**Почему.** В курсе три разных оболочки, и они не взаимозаменяемы:

| Блок кода помечен | Где выполнять |
|---|---|
| ```bash``` | внутри Ubuntu (WSL2 или VM) |
| ```powershell``` | в Windows PowerShell |
| ```text``` | это ожидаемый вывод, а не команда |

**Как починить.** Все команды ROS 2 — только в bash внутри Linux. В PowerShell выполняются лишь `wsl --install`, `wsl --list`, `wsl --update`.

---

## colcon и rosdep

### `colcon: command not found`

Проверено:

```text
bash: colcon: command not found
```

**Почему.** `colcon` ставится отдельным пакетом, метапакет ROS 2 его не тянет. Он также не появится, пока не подключён setup-файл — но, в отличие от `ros2`, чаще всего его просто нет в системе.

**Как проверить.**

```bash
which colcon
```

**Как починить.** Из статьи [Workspace, colcon и первый пакет](<lesson 2 (nodes and topics)/workspace_colcon_package.md>):

```bash
sudo apt update
sudo apt install -y python3-colcon-common-extensions
colcon --help
```

Та же строчка есть в таблице проблем статьи [TurtleBot3](<lesson 11 (turtlebot3 sim)/install_jazzy_turtlebot3.md>).

### `rosdep: command not found`

Проверено:

```text
bash: rosdep: command not found
```

**Почему.** То же самое: `rosdep` — отдельный пакет.

**Как починить.** Из статьи [rosdep](<lesson 2 (nodes and topics)/rosdep.md>):

```bash
sudo apt update
sudo apt install -y python3-rosdep
sudo rosdep init
rosdep update
```

Если `sudo rosdep init` сообщает, что файл уже существует, повторная инициализация не нужна — достаточно `rosdep update`.

### `rosdep key not found`

**Почему.** Из статьи [rosdep](<lesson 2 (nodes and topics)/rosdep.md>) — три причины:

- зависимость отсутствует в базе rosdep;
- имя зависимости записано не ROS-ключом, а как попало;
- пакет доступен только из исходников.

**Как проверить.** Открыть `package.xml` того пакета, на котором споткнулась команда, и сверить имя ключа с ROS Index.

**Как починить.** Исправить ключ в `package.xml` либо установить зависимость вручную через apt и зафиксировать это в статье урока.

### `Cannot locate rosdep definition`

**Почему.** Правила ищутся не для того дистрибутива.

**Как проверить и починить.** Из статьи [rosdep](<lesson 2 (nodes and topics)/rosdep.md>):

```bash
echo $ROS_DISTRO
rosdep install -i --from-path src --rosdistro $ROS_DISTRO -y
```

Писать `--rosdistro $ROS_DISTRO` вместо жёстко зашитого `jazzy` — общее соглашение курса ([README.md](README.md), раздел «Соглашения курса»).

### `rosdep install` на всём `src` требует Gazebo, которого ещё нет

Симптом: студент на уроке 1 выполняет шаг «соберите workspace курса» и получает от `rosdep` ошибку про пакеты `ros_gz_bridge`, `ros_gz_sim`, `teleop_twist_keyboard`, `rviz2`.

**Почему.** В `ros2_ws/src` лежит пакет `my_robot_gazebo` — артефакт урока 8. Команда `rosdep install -i --from-path src` обходит **весь** `src` и тянет его зависимости, то есть требует установленного Gazebo Harmonic, который ставится только в уроке 8.

**Как проверить.**

```bash
cat ros2_ws/src/my_robot_gazebo/package.xml
```

**Как починить.** Спотыкается именно `rosdep`, поэтому чинится он же — ключами Gazebo, которые до урока 8 не нужны:

```bash
cd ros2_ws
rosdep install -i --from-path src --rosdistro $ROS_DISTRO -y \
    --skip-keys "ros_gz_sim ros_gz_bridge"
```

Если урок 8 не планируется вовсе, пакет можно исключить и из сборки:

```bash
colcon build --symlink-install --packages-ignore my_robot_gazebo
```

Флаг `colcon` сам по себе `rosdep` не лечит: это две независимые команды. Третий вариант — сначала пройти [установку Gazebo](<lesson 8 (Gazebo)/01-installation.md>), а потом возвращаться к сборке всего workspace; тот же разбор есть в [SETUP.md](SETUP.md).

### Собралось без ошибок, но `ros2 run` запускает старый код

**Почему.** Две типовые причины: не переподключён overlay после сборки, либо пакет собран без `--symlink-install` (для `ament_python` этот флаг делает так, что правки в исходнике видны без пересборки — во всех статьях курса сборка идёт именно с ним).

**Как проверить.**

```bash
ls -l install/<имя_пакета>/lib/<имя_пакета>/
```

**Как починить.**

```bash
cd ~/ros2_ws
colcon build --symlink-install --packages-select <имя_пакета>
source install/setup.bash
```

Если поведение всё равно старое — снести `build/`, `install/`, `log/` и собрать заново. Насколько часто это реально требуется — **не замерено**.

---

## Gazebo

### `gz: command not found`

**Почему.** Из статьи [Установка Gazebo Harmonic](<lesson 8 (Gazebo)/01-installation.md>): метапакет `ros-jazzy-ros-gz` не доустановил `gz-tools2`.

**Как проверить.** Проверено, что это ровно та же форма сообщения, что у `ros2` и `colcon`:

```text
bash: gz: command not found
```

**Как починить.**

```bash
sudo apt install gz-tools2
gz sim --version
```

Ожидаемо: Harmonic, версия 8.x. На Jazzy «родной» симулятор — именно Gazebo Harmonic, а не классический Gazebo 11; CLI называется `gz`, плагины — `gz-sim-*`, типы сообщений — `gz.msgs.*`.

### Чёрное или мигающее окно Gazebo

**Почему.** Из статьи [Установка Gazebo Harmonic](<lesson 8 (Gazebo)/01-installation.md>): на WSL2 и в виртуальной машине часто нет аппаратного ускорения, и рендер `ogre2` не получает нормального GL-контекста.

**Как проверить.** Запустить пустой мир с отладочным логом:

```bash
gz sim -v 4 empty.sdf
```

**Как починить.** Программный рендер:

```bash
LIBGL_ALWAYS_SOFTWARE=1 gz sim empty.sdf
```

Статья прямо предупреждает: если базовый запуск не работает, этот флаг придётся использовать и во всех последующих запусках Gazebo в курсе — включая launch-файлы уроков 8, 10 и 11.

### `/clock` пустой, `ros2 topic echo /clock` ничего не печатает

**Почему.** Из статьи [Установка Gazebo Harmonic](<lesson 8 (Gazebo)/01-installation.md>): по умолчанию симуляция запускается **на паузе**.

**Как проверить.**

```bash
gz topic -l
```

Должны быть `/clock`, `/stats`, `/world/empty/...`.

**Как починить.** Нажать **Play** в нижнем левом углу окна Gazebo. Только после этого мост начнёт гнать время в ROS 2:

```bash
ros2 run ros_gz_bridge parameter_bridge /clock@rosgraph_msgs/msg/Clock@gz.msgs.Clock
ros2 topic echo /clock
```

### Робот не появляется в мире после `ros2 launch`

**Почему.** Из статьи [Спавн робота](<lesson 8 (Gazebo)/04-spawn-robot.md>): Gazebo стартует асинхронно, и спавн робота до того, как мир готов, приводит к ошибке.

**Как проверить.** Посмотреть, есть ли в launch-файле задержка перед спавном.

**Как починить.** Обернуть спавн в `TimerAction`, как в статье:

```python
TimerAction(period=2.0, actions=[spawn]),
```

### Нет модели робота в Gazebo (TurtleBot3)

**Почему.** Из таблицы проблем статьи [TurtleBot3](<lesson 11 (turtlebot3 sim)/install_jazzy_turtlebot3.md>): не выставлен путь к моделям.

**Как проверить.**

```bash
echo $GAZEBO_MODEL_PATH
echo $TURTLEBOT3_MODEL
```

**Как починить.** Из той же статьи:

```bash
echo "export TURTLEBOT3_MODEL=burger" >> ~/.bashrc
echo "export GAZEBO_MODEL_PATH=\$GAZEBO_MODEL_PATH:~/turtlebot3_ws/src/turtlebot3_simulations/turtlebot3_gazebo/models" >> ~/.bashrc
source ~/.bashrc
```

Модель может быть `burger`, `waffle` или `waffle_pi`.

### Лидар описан в SDF, но `/scan` пуст

**Почему.** Из статьи [Сенсоры](<lesson 8 (Gazebo)/06-sensors.md>): лидар требует рендеринга и работает только через системный плагин `gz-sim-sensors-system`. Без него сенсор в мире есть, а данных нет.

**Как проверить.** Найти в `.sdf` мира блок:

```xml
<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
  <render_engine>ogre2</render_engine>
</plugin>
```

И отдельно — что мост поднят и топик действительно есть:

```bash
gz topic -l | grep scan
ros2 topic list | grep scan
timeout 8 ros2 topic hz /scan || true
```

**Как починить.** Добавить плагин в мир. Если плагин есть, а `/scan` всё равно пуст на WSL2 — это тот же дефект GL, что и «чёрное окно»: рендер-сенсоры не работают без контекста. Пробуйте `LIBGL_ALWAYS_SOFTWARE=1`.

### `ветка jazzy не найдена` при клонировании turtlebot3_simulations

**Почему.** Из таблицы проблем статьи [TurtleBot3](<lesson 11 (turtlebot3 sim)/install_jazzy_turtlebot3.md>): у репозитория может не быть ветки с таким именем.

**Как проверить.**

```bash
cd turtlebot3_simulations
git branch -a
```

**Как починить.** Клонировать `-b main` или `-b rolling` вместо `-b jazzy`.

### Робот падает сразу после спавна (балансир урока 8)

**Почему.** Из статьи [Балансир](<lesson 8 (Gazebo)/08-balancer.md>): контроллер не успел получить данные с IMU.

**Как проверить.** Смотреть в логах флаги `imu_ready` и `odom_ready`.

Сопутствующие симптомы из той же статьи:

| Симптом | Причина и решение |
|---|---|
| Балансирует, но дрейфует в сторону | ЦМ смещён по X — добавить интегральную составляющую |
| Реакция слишком резкая, робот дёргается | Уменьшить `Q[0,0]` или увеличить `R` |
| Реакция слишком медленная, робот падает | Увеличить `Q[0,0]` или уменьшить `R` |

**Как починить.** Дождаться готовности сенсоров перед подачей управления; критерий приёмки из статьи — робот не падает минимум 10 секунд, а `ros2 topic echo /imu --field orientation.y` показывает угол меньше 0.05 рад.

---

## Nav2

Основа этого раздела — таблица диагностики из статьи [Nav2 на TurtleBot3](<lesson 10 (Nav2)/nav2_turtlebot3_sim.md>), развёрнутая по симптомам.

### `ACML cannot publish a pose... Please set the initial pose`

Так это записано в статье [Локализация](<lesson 10 (Nav2)/nav2_localization.md>) — сообщение, которое AMCL печатает в терминал, пока начальная поза не задана. Рядом в логе видны строки `Activating amcl` и `Received a 160 x 141 map`.

**Почему.** Стек Nav2 поднялся, карта загружена, но AMCL не знает, где робот, и потому не публикует трансформацию `map -> odom`. Без неё нет полной цепочки `map -> odom -> base_link`, и навигация не начнётся.

**Как проверить.**

```bash
ros2 run tf2_ros tf2_echo map base_link
```

**Как починить.** Из статьи: нажать **2D Pose Estimate** в верхней панели RViz2, кликнуть на карте в точке, где робот стоит в Gazebo, и, не отпуская кнопку, потянуть стрелку в направлении «взгляда» робота. Скан лидара должен лечь на стены карты; если не совпало — повторить. Затем немного подвигать робота телеуправлением, чтобы AMCL уточнила позу:

```bash
ros2 run turtlebot3_teleop teleop_keyboard
```

### Робот не реагирует на Nav2 Goal

**Почему.** Из таблицы статьи: не задана начальная поза.

**Как проверить.** Смотрите предыдущий подраздел — это тот же дефект, только замеченный позже.

**Как починить.** 2D Pose Estimate, потом Nav2 Goal.

### `message filter dropping message` — ошибки tf в RViz2

**Почему.** Из таблицы статьи: забыт `use_sim_time:=True`. Ноды живут по системному времени, а данные из Gazebo приходят со временем симуляции; фильтр сообщений выбрасывает всё, для чего не может найти трансформацию на нужный момент.

**Как проверить.**

```bash
ros2 param get /amcl use_sim_time
ros2 topic echo /clock --once
```

**Как починить.** Перезапустить Nav2 с `use_sim_time:=True`. Параметр должен стоять у **всех** нод стека, а не только у части.

### Скан лидара не совпадает с картой

**Почему.** Из таблицы статьи: карта строилась в другом мире, либо поза задана неточно.

**Как проверить.** Сравнить имя мира, запущенного в Gazebo, с тем, для которого строилась карта.

**Как починить.** Либо повторить оценку позы, либо перестроить карту в том мире, в котором работаете.

### `map_server` падает при старте

**Почему.** Из таблицы статьи: неверный путь в `map:=` или поле `image` в `map.yaml` указывает не на тот файл.

**Как проверить.**

```bash
cat <путь>/map.yaml
ls -l <путь>
```

Поле `image` в YAML — путь относительно самого YAML.

**Как починить.** Исправить путь. Проверка того, что стек поднялся:

```bash
ros2 lifecycle nodes
ros2 lifecycle get /amcl
```

Ожидаемо `active`; в терминале `lifecycle_manager` при этом пишет `Managed nodes are active` (из статьи [Знакомство с Nav2](<lesson 10 (Nav2)/introducing_nav2.md>)).

### Робот дёргается или едет рывками

**Почему.** Из таблицы статьи: параллельно запущен teleop, и два источника пишут в `cmd_vel` одновременно.

**Как проверить.**

```bash
ros2 topic info /cmd_vel --verbose
```

Смотрите число публикаторов.

**Как починить.** Остановить teleop.

### Costmap не публикуются, в RViz2 пусто

**Почему.** Из статьи [Costmap](<lesson 10 (Nav2)/nav2_costmaps.md>): обе costmap живут внутри lifecycle-нод `planner_server` и `controller_server`. Пока `lifecycle_manager` не активировал стек, costmap не публикуются.

**Как проверить.**

```bash
ros2 lifecycle nodes
ros2 lifecycle get /planner_server
ros2 lifecycle get /controller_server
```

**Как починить.** Дождаться активации либо разобраться, на какой ноде застрял `lifecycle_manager` — он активирует стек в фиксированном порядке и останавливается на первой неготовой ноде.

### В `ros2 node list` нет половины нод Nav2

**Почему.** Стек не поднялся целиком.

**Как проверить.** Из статьи [Nav2 на TurtleBot3](<lesson 10 (Nav2)/nav2_turtlebot3_sim.md>), в списке должны быть: `/amcl`, `/bt_navigator`, `/controller_server`, `/planner_server`, `/behavior_server`, `/map_server`, `/lifecycle_manager_navigation`.

А в `ros2 pkg list` (из статьи [Знакомство с Nav2](<lesson 10 (Nav2)/introducing_nav2.md>)) — `nav2_bringup`, `nav2_bt_navigator`, `nav2_planner`, `nav2_controller`, `nav2_map_server`, `nav2_amcl`, `nav2_lifecycle_manager`.

**Как починить.** Если пакетов нет — доустановить apt-ом. Если пакеты есть, а ноды не поднялись — читать терминал launch-файла с начала: первая ошибка обычно объясняет остальные.

---

## micro-ROS

Основа раздела — [Практика, диагностика и зачёт](<lesson 12 (micro-ros)/micro_ros_practice_debug.md>).

### Микроконтроллер не появляется в ROS 2 graph

Симптом: Agent запущен, ESP32 подключён, а `ros2 node list` его не показывает.

**Как проверить.**

```bash
echo $ROS_DOMAIN_ID
ros2 node list
```

**Почему.** Из статьи, по порядку проверки:

- Agent слушает не тот transport или порт;
- firmware отправляет данные на неверный IP;
- ESP32 и компьютер в разных сетях;
- firewall блокирует UDP;
- `ROS_DOMAIN_ID` не совпадает;
- serial device указан неверно.

**Как починить.** Поднять Agent явно с отладочным уровнем логов, из статьи [Agent, firmware и проверка graph](<lesson 12 (micro-ros)/micro_ros_agent_firmware.md>):

```bash
export ROS_DOMAIN_ID=42
ros2 run micro_ros_agent micro_ros_agent udp4 --port 8888 -v6
```

или по serial:

```bash
export ROS_DOMAIN_ID=42
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -v6
```

Флаг `-v6` показывает, приходят ли пакеты от клиента вообще. Если в логе Agent пусто — проблема ниже уровня ROS 2 (сеть, порт, кабель), и `ROS_DOMAIN_ID` тут ни при чём.

Отдельная ловушка WSL2: USB-устройства в WSL2 по умолчанию не видны, `/dev/ttyUSB0` внутри Linux просто не существует. Для serial-transport нужен либо проброс USB, либо запуск Agent на другой машине. Проверено, что в этой WSL-среде ROS 2 работает, **проброс USB не проверялся**.

### Топики есть, но сообщения не приходят

**Как проверить.** Из статьи:

```bash
ros2 topic list -t
ros2 topic info /joint_states --verbose
timeout 8 ros2 topic hz /joint_states || true
```

**Почему.** Из статьи:

- publisher создан, но publish loop не вызывается;
- сообщение не инициализировано полностью;
- массивы в сообщениях имеют неверный `size` или `capacity`;
- QoS publisher и subscriber плохо совместимы;
- firmware зависает в callback.

**Как починить.** Сначала отделить «не публикуется» от «не доставляется»: `ros2 topic info --verbose` показывает, есть ли публикатор и совпадают ли профили QoS. Если публикатор есть и QoS совпадает, а `hz` молчит — виновата прошивка.

### SLAM строит плохую карту

**Как проверить.** Из статьи — по списку:

- направление вращения колёс и энкодеров;
- yaw IMU;
- `laser_link` в URDF;
- свежесть `/scan_wall_time`;
- `wheel_radius` и `wheel_separation`;
- отсутствие ручного переноса робота во время SLAM.

**Почему.** Чаще всего дело во времени сообщений: микроконтроллер ставит свой timestamp, который не связан с временем хоста, и SLAM видит «старые» данные.

**Как починить.** Либо синхронизировать время на микроконтроллере, либо делать restamp на хосте — оба подхода со своими рисками разобраны в вопросах для самопроверки той же статьи.

### Робот продолжает ехать после потери связи

**Почему.** Timeout `/cmd_vel` не реализован в прошивке. Остановка Nav2 его не заменяет: если связь потеряна, команда «стоп» просто не дойдёт.

**Как починить.** Timeout команд движения должен находиться **в firmware**: не получил `/cmd_vel` дольше заданного времени — обнулил моторы. Это требование безопасности, а не удобства.

---

## MuJoCo и рендер

### `RuntimeError: invalid value for environment variable MUJOCO_GL: egl`

Проверено на Windows с mujoco 3.9.0. Полный вид:

```text
Traceback (most recent call last):
  File "...", line 3, in <module>
    import mujoco
  ...
  File "...\mujoco\rendering\classic\gl_context.py", line 34, in <module>
    raise RuntimeError(
RuntimeError: invalid value for environment variable MUJOCO_GL: egl
```

**Почему.** Список допустимых значений `MUJOCO_GL` зависит от ОС. Проверено по исходнику `mujoco/rendering/classic/gl_context.py` (mujoco 3.9.0):

| ОС | Допустимые значения `MUJOCO_GL` |
|---|---|
| любая | `enable`, `enabled`, `on`, `true`, `1`, `glfw`, пустая строка |
| любая (выключить рендер) | `disable`, `disabled`, `off`, `false`, `0` |
| Linux | дополнительно `glx`, `egl`, `osmesa` |
| Windows | дополнительно `wgl` |
| macOS | дополнительно `cgl` |

То есть `egl` и `osmesa` — это **только Linux**. Рецепт «поставьте `MUJOCO_GL=egl`, чтобы рендерить без экрана» на Windows роняет процесс на строке `import mujoco`.

**Как проверить.**

```bash
python -c "import os; print(repr(os.environ.get('MUJOCO_GL')))"
```

**Как починить.** На Windows — снять переменную или поставить `glfw`:

```powershell
$env:MUJOCO_GL = 'glfw'
```

На headless-Linux (сервер, контейнер без экрана) — `egl`, и обязательно **до** `import mujoco`:

```python
import os
os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
```

Порядок важен: значение читается на импорте модуля, выставить его позже нельзя. Работоспособность `egl` внутри WSL2 **не проверялась**.

### Оффскрин-кадр MuJoCo получается чёрным

Это самая обсуждаемая проблема урока 14, и её надо описать честно.

**Что сказано в курсе.** В статье [Машинка с рулём учится парковаться](<lesson 14 (RL custom models)/track_a_car/README.md>) есть примечание: оффскрин-рендеринг MuJoCo на некоторых машинах выдаёт чёрный кадр, поэтому картинки в статье построены matplotlib по траектории, а на интерактивное окно `watch_parking.py` это не влияет.

**Что показал разбор кода.** Метод `render()` в среде урока **не вызывается ни одним скриптом урока**: все картинки рисует matplotlib по накопленной траектории. То есть примечание описывает код, который не исполняется. Кроме того, ни в одном файле урока нет выбора бэкенда: `MUJOCO_GL` не выставляется нигде.

**Что проверено фактически.** На машине разработчика (Windows 11, native Python 3.12.3, mujoco 3.9.0, RTX 4060) оффскрин-рендер работает **без всякой настройки**:

```text
MUJOCO_GL env before import: None
shape (240, 320, 3) dtype uint8 mean 136.064 max 255
OK: frame is not black
```

С `MUJOCO_GL=glfw` результат побайтово тот же. Чёрного кадра воспроизвести на этой машине **не удалось**.

**А потом чёрный кадр всё-таки случился — и причина оказалась другой.** При
перегенерации иллюстраций трека A `evaluate.py` записал гифку в 1563 байта: 86 кадров,
все чёрные, один уникальный цвет. При этом тот же рендер той же модели в отдельном
процессе давал нормальный кадр. Разница была в одной строке:

```python
renderer.update_scene(data)                  # яркость 82.45, 1305 цветов
renderer.update_scene(data, camera="top")    # яркость  0.00,    1 цвет
```

Дело было **в камере, а не в OpenGL**. В модели стояло:

```xml
<camera name="top" mode="fixed" pos="3.4 0 8" euler="-90 0 0" fovy="48"/>
```

Камера MuJoCo по умолчанию смотрит вдоль **своей оси −Z**, верх кадра — ось **+Y**.
Значит для вида сверху поворот не нужен вообще. А `euler="-90 0 0"` — это соглашение
для **фронтальной** камеры: оно разворачивает взгляд вдоль −Y, и камера с высоты
восьми метров смотрела горизонтально, в пустоту. Кадр честно показывал ничто.

Лечение — убрать поворот: `euler="0 0 0"`.

**Вывод.** Прежде чем чинить OpenGL, проверьте камеру. Порядок диагностики такой:

1. Отрендерьте **без** аргумента `camera` — свободной камерой. Если кадр нормальный,
   GL-контекст в порядке, и проблема в вашей камере.
2. Если чёрный и со свободной камерой — тогда это действительно GL-контекст
   (headless-сервер, контейнер, удалённая сессия, WSL2 без WSLg).

Проверка камеры стоит две строки и должна стоять в пробах модели, а не в отладке
готовых картинок: чёрный кадр обнаружился только на этапе иллюстраций, хотя дефект
жил в модели с самого начала.

**Как проверить у себя.** Минимальная проба, которая отвечает на вопрос за пять секунд:

```python
import os
print("MUJOCO_GL:", repr(os.environ.get("MUJOCO_GL")))
import mujoco

xml = """<mujoco>
  <worldbody>
    <light pos="0 0 3"/>
    <geom type="plane" size="2 2 .1" rgba=".8 .8 .8 1"/>
    <body pos="0 0 .5"><freejoint/><geom type="box" size=".2 .2 .2" rgba="1 0 0 1"/></body>
  </worldbody>
</mujoco>"""

m = mujoco.MjModel.from_xml_string(xml)
d = mujoco.MjData(m)
mujoco.mj_forward(m, d)
r = mujoco.Renderer(m, 240, 320)
r.update_scene(d)
img = r.render()
print("mean", float(img.mean()), "max", int(img.max()))
print("ЧЁРНЫЙ КАДР" if int(img.max()) == 0 else "кадр нормальный")
```

Если `max == 0` — контекста нет. Если ошибка вылетела на `import mujoco` — смотрите предыдущий подраздел про `MUJOCO_GL`.

**Как починить.**

1. На Windows — запускать из обычной локальной сессии, не по RDP/SSH, и не выставлять `MUJOCO_GL` вручную.
2. На headless-Linux — `os.environ.setdefault("MUJOCO_GL", "egl")` до импорта.
3. Проверить, что в модели есть источник света: сцена без `<light>` рендерится тёмной и это не имеет отношения к GL.

### Кадр получился портретный 720×960 вместо 960×720

**Почему.** Сигнатура конструктора — `Renderer(model, height=240, width=320, ...)`: **сначала высота, потом ширина**. Вызов `mujoco.Renderer(self.model, 960, 720)` даёт `height=960, width=720`, то есть портрет 720×960. Ошибка молчаливая: если `<global offwidth>/<offheight>` в модели достаточно велики, исключения не будет.

**Как проверить.**

```python
print(img.shape)   # (height, width, 3)
```

**Как починить.** Писать имена аргументов явно:

```python
mujoco.Renderer(model, height=720, width=960)
```

### Память растёт от эпизода к эпизоду, GL-контекст течёт

**Почему.** Если среда создаёт `mujoco.Renderer`, но не определяет `close()`, GL-контекст не освобождается никогда. `env.close()` при этом не падает — он просто ничего не делает, потому что базовый `gym.Env.close()` пустой. В коде урока 14 `close()` отсутствует, а `evaluate()` создаёт новую среду на каждой проверке.

**Как проверить.**

```python
print("close" in МойКлассСреды.__dict__)
```

**Как починить.** Определить `close()` в среде и освобождать в нём рендерер:

```python
def close(self):
    if self._renderer is not None:
        self._renderer.close()
        self._renderer = None
```

### Видео из среды идёт вдвое медленнее реального времени

**Почему.** `metadata["render_fps"]` не совпадает с реальной частотой управления. В среде урока 14 стоит `render_fps: 50` при `DT = 0.01` и одном `mj_step` на действие, то есть частота управления 100 Гц. Видео, собранное по `metadata`, идёт вдвое медленнее.

**Как проверить.**

```python
print(env.metadata["render_fps"], 1.0 / (env.model.opt.timestep * frame_skip))
```

**Как починить.** Привести `render_fps` в соответствие с реальным шагом управления.

---

## CUDA и torch

### `torch.cuda.is_available()` возвращает `False`

**Как проверить.** Одной командой, проверено на этой машине:

```powershell
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
```

Фактический вывод здесь:

```text
2.6.0+cu124 12.4 True
```

Читать так:

| Что видно | Что это значит |
|---|---|
| версия **без** суффикса `+cuXXX`, например `2.6.0` или `2.6.0+cpu` | установлено CPU-колесо torch; CUDA не будет никогда, сколько ни настраивай драйвер |
| `torch.version.cuda` = `None` | то же самое, другой признак |
| версия `+cu124`, но `is_available()` = `False` | сборка с CUDA есть, а GPU не виден: драйвер, права, отсутствие GPU в этой среде |

**Почему и как починить.**

1. **Стоит CPU-сборка.** Самый частый случай: `pip install torch` без индекса ставит колесо под доступную платформу. Ставить надо с официального индекса нужной версии CUDA (см. страницу выбора на pytorch.org).
2. **Драйвер NVIDIA старее рантайма CUDA.** Проверка:

```powershell
nvidia-smi
```

Если команда не находится — драйвер не установлен или GPU в этой среде нет.

3. **Запуск внутри WSL2.** GPU виден в WSL2 только при современном драйвере с поддержкой WSL и при наличии `/dev/dxg`. Проверено, что на этой машине `/dev/dxg` внутри WSL присутствует. Внутри WSL torch **не проверялся** — все замеры torch делались в Windows-питоне.
4. **Два разных Python.** Классика: `pip install` ушёл в одно окружение, а скрипт запускается другим. Проверка:

```powershell
python -c "import sys; print(sys.executable)"
```

### `UserWarning: You are trying to run PPO on the GPU, but it is primarily intended to run on the CPU when not using a CNN policy`

Полный текст предупреждения, проверено на stable_baselines3 2.4.1:

```text
You are trying to run PPO on the GPU, but it is primarily intended to run on the CPU
when not using a CNN policy (you are using ActorCriticPolicy which should be a MlpPolicy).
See https://github.com/DLR-RM/stable-baselines3/issues/1245 for more info.
You can pass `device='cpu'` or `export CUDA_VISIBLE_DEVICES=` to force using the CPU.
Note: The model will train, but the GPU utilization will be poor and the training might
take longer than on CPU.
```

**Почему.** У MLP-политики сети крошечные, а узкое место — шаг среды, который считается на CPU. Перенос на GPU добавляет копирование тензоров туда-обратно на каждом шаге и в сумме **замедляет** обучение.

**Как проверить.** Замерено здесь, PPO + `MlpPolicy` + `CartPole-v1`, 20 480 шагов, одиночный прогон:

```text
cpu   20480 шагов за  35.23 с =   581.3 шагов/с
cuda  20480 шагов за  72.55 с =   282.3 шагов/с
```

GPU оказался в **2.06 раза медленнее**. Числа получены на загруженной машине и как абсолютные значения не показательны — важно отношение.

**Как починить.** Для всех задач курса на `MlpPolicy` (уроки 13 и 14) явно указывайте CPU:

```python
model = PPO("MlpPolicy", env, device="cpu")
```

GPU в этих уроках нужен не для PPO, а для тяжёлых политик со свёртками и для задач, где среда сама считается на GPU.

### `DeprecatedEnv: Environment version v2 for LunarLander is deprecated. Please use LunarLander-v3 instead.`

Проверено на gymnasium 1.0.0. Дословно:

```text
DeprecatedEnv Environment version v2 for `LunarLander` is deprecated. Please use `LunarLander-v3` instead.
```

**Почему.** В gymnasium 1.0.0 версия `v2` для `LunarLander` снята. Статья [Введение в Stable-Baselines3](<lesson 13 (stable baselines3)/sb3_introduction.md>) в задании предлагает `LunarLander-v2` — на текущем gymnasium это упадёт.

**Как починить.** Использовать `LunarLander-v3`.

Тот же класс сообщений, но безобидный (это `DeprecationWarning`, а не ошибка): `CartPole-v0` создаётся, но печатает `WARN: The environment CartPole-v0 is out of date. You should consider upgrading to version v1.` — проверено. В статьях курса используется `CartPole-v1`, так и надо.

### `DependencyNotInstalled: Box2D is not installed`

Проверено:

```text
DependencyNotInstalled Box2D is not installed, you can install it by run `pip install swig` followed by `pip install "gymnasium[box2d]"`
```

**Почему.** `LunarLander` любой версии требует физического движка Box2D, который ставится отдельно.

**Как починить.** Ровно то, что советует само сообщение:

```bash
pip install swig
pip install "gymnasium[box2d]"
```

Порядок важен: `swig` нужен для сборки биндингов Box2D.

---

## Обучение с подкреплением

Этот раздел про ошибки, которых нет в учебниках: код работает, исключений нет, а результата нет. Числа взяты из разбора боевых RL-проектов курса — это фактические замеры, а не иллюстрации.

### Награда растёт, поведения нет: метрика, которая всегда равна нулю

**Симптом.** В логе есть отдельный член награды за нужное поведение, и он исправно набирает баллы. Самого поведения при этом нет.

**Почему.** Величина измеряется в неправильной системе координат. Реальный случай из разбора: длина шага двуногого измерялась как смещение стопы **в системе координат корпуса** между двумя посадками одной ноги. Для любой периодической походки это тождественный ноль: корпус уехал ровно настолько же, насколько уехала стопа. На синтетических походках с шагом 0.10, 0.30 и 0.45 м метрика давала 0.0000 м во всех трёх случаях. Живая политика при этом собирала по этому члену 21.9 награды в секунду — то есть платили за апериодичность, за дрожание точки постановки.

Отягчающее обстоятельство: одна и та же формула была скопирована и в награду, и в измеритель. Сверка «награда против пробы» сходилась — это была **согласованная ложь**.

**Как проверить.** Прогнать метрику через **синтетический вход с известным ответом**. Для парковки это одна страница кода: посадить машину на заранее заданную траекторию (прямая 1 м, круг, стояние на месте) и потребовать, чтобы метрика вернула 1.0, 0.0 и 0.0 соответственно.

Правило: если метрика на трёх заведомо разных входах даёт одно и то же число — она сломана, независимо от того, как красиво растёт в TensorBoard.

**Как починить.** Считать величину в мировой раме и исправить **оба** места — и награду, и измеритель.

### Поднял вес награды в полтора раза, и ничего не изменилось

**Симптом.** Награда за нужную величину есть, вес ей подняли (8 → 12) — поведение не сдвинулось ни на процент.

**Почему.** Дело не в весе, а в **форме** платы. Замер из разбора: плата вида `min(L / L_cap, 1)` начисляется за каждую посадку; при каденсе `f` посадок в секунду `2f`, значит ставка в секунду равна `2f · W · L / L_cap`. Но в установившейся ходьбе `L · f = v`, где `v` задано командой, поэтому ставка равна `2W · v / L_cap` — **длина сокращается**. Фактические числа: шаг 0.058 м даёт 11.33 награды в секунду, шаг 0.300 м — 11.16. Шаг впятеро длиннее, а ставка на 1.5 % **хуже**. Градиент не просто нулевой, он слегка отрицательный.

**Как проверить.** До запуска выписать ставку награды **в единицу времени** как функцию поведения и убедиться, что производная по целевой величине не ноль.

**Как починить.** Платить **смещением от порога**, а не долей от потолка: `rew = Σ(t − t0) · событие`. Ключ — знак: поведение хуже порога должно становиться чистым штрафом, а не «менее выгодной наградой». После такой правки в разборе шаг вырос с 11.2 до 34.1 см, каденс упал с 5.1 до 2.0 Гц, а слежение за командой выросло с 78 % до 91.7 %.

Правило: «поднять вес» — лечение только тогда, когда градиент есть, но слаб. Если поведение не меняется после изменения веса **в разы**, проблема в форме члена.

### Агент выучил «ничего не делать», и eval бьёт рекорды

**Симптом.** Награда уверенно растёт, оценка ставит рекорды, падений ноль, движения нет.

**Почему.** У задачи есть безрисковое бездействие, и оно почти полностью оплачено. Реальный механизм из разбора: ядро слежения было абсолютным, `exp(−8·err²)` с фиксированной шириной. При малой команде ошибка «стою вместо 0.2 м/с» мала в абсолютных единицах, и ядро платит стоящей машине большую долю максимума. Замеры: при команде 0.4 абсолютное ядро платит стоящей машине **27.8 %** максимума, относительное — **1.7 %**. При команде 0.2 абсолютное ядро платило стоя **73 %**.

Отдельная контринтуитивная деталь: сужение диапазона команд сделало стояние **ещё выгоднее** — в пределах 0.3 ядро платило стоя не меньше 49 %. Три итерации подряд добавление штрафов лишь двигало порог.

**Как проверить.** Посчитать **аналитически**, сколько награды в секунду получает агент, который вообще ничего не делает. Это число считается до запуска, а не ищется в TensorBoard.

**Как починить.** Сделать ширину ядра пропорциональной цели: `σ = max(0.35·|cmd|, 0.07)`. После правки скорость при команде 0.2 выросла с 0 до 0.115 м/с.

### Обученная политика хуже, чем выключенное управление

**Симптом.** Эпизоды длятся 0.17 с, при том что **пассивная** машина с нулевым управлением падает через 1.78 с. Обученная политика в десять раз хуже выключенного робота, и так на любом объёме шагов.

**Почему.** Стартовый шум разведки слишком велик для физики задачи. SB3 по умолчанию ставит `log_std_init = 0.0`, то есть std около 1.0 в нормированных единицах действия. При приводах 112.86 Н·м такой шум — мгновенное падение. Траектория «стоять» становится **ненаблюдаемой**: ни одна траектория не живёт достаточно, чтобы value-функция увидела награду за стояние, и бутстрап критика не замыкается.

Диагностический признак сформулирован в разборе прямо: **обученная политика хуже выключенного управления означает, что проблема не в награде, а в том, что критик никогда не видел хорошей траектории.**

**Как проверить.** Две минуты работы: прогнать эпизод с нулевым действием и эпизод со случайным действием из стартового распределения. Если случайный резко хуже нулевого — стартовый шум надо давить.

**Как починить.** `log_std_init = -2.3` (std около 0.1). В разборе A/B-проба сразу дала 1.93 с выживания и +80 награды вместо 0.17 с.

Зеркальный приём: при **дообучении** зрелой политики шум наоборот надо поднимать, иначе она не выйдет из своего предельного цикла (в одном из прогонов std поднимали с 0.105 до 0.258).

Оговорка честности: для парковки из урока 14 дефолт SB3 нормален — машинка не падает, худшее последствие случайного действия там столкновение или вылет за границы, и случайная политика спокойно доживает до конца эпизода. Приём остаётся в арсенале, но конкретно там не обязателен.

### Куррикулум включили, а он не помог

**Симптом.** Понизили гравитацию, чтобы робот успевал научиться балансу, — эпизоды всё те же 0.17 с.

**Почему.** Куррикулум делает хорошую траекторию **достижимой**, но не делает её **посещаемой**. A/B-проба: даже на намертво зафиксированной 0.35g при нулевых командах политика жила те же 0.17 с при пассивных 1.78 с. Пока разведка убивает машину, окно возможностей бесполезно.

**Как проверить.** Задать себе вопрос до ввода куррикулума: «какая траектория даёт положительную награду, и посещает ли её текущая политика хоть иногда?» Если ответ «никакая» — сначала разведка, потом куррикулум.

**Как починить.** Складывать оба лечения. Когда в разборе тихий старт и куррикулум применили вместе, получилось: 8 млн шагов — 1.6 с; 20 млн — 20/20 с без падений; 24 млн — ходьба 0.356 м/с при нуле падений.

И отдельное правило: **метрика оценки не должна двигаться вместе с куррикулумом**. Оценка идёт всегда на честной 1g.

### Ролик красивый, а честная приёмка плохая

**Симптом.** Отрендерили ролик по восьми дорожкам полигона: **0 падений из 8**. Честная приёмка на том же чекпойнте: **18 падений из 48**, то есть 37 %.

**Почему.** Три независимых искажения сразу:

1. один эпизод на дорожку с фиксированным seed'ом просто оказался удачным;
2. в ролике дорожка обрезана по времени, поэтому метры между роликами несравнимы;
3. замеры без рандомизации систематически льстят.

Сколько эпизодов нужно на самом деле: быстрый скрининг на 2 эпизодах давал одного победителя, на 6 эпизодах порядок поменялся. Девять соседних чекпойнтов одного прогона (164.0…168.0 млн шагов) дали путь 3.00 / 1.24 / 2.58 / 3.21 / 1.71 / 2.16 / 2.24 / 2.66 / 3.26 м. Соседние чекпойнты отличаются в 2.6 раза — это шум, а не прогресс.

**Как проверить.** Сначала измерить **разброс между соседними чекпойнтами**, и только потом решать, сколько эпизодов нужно, чтобы отличить прогресс от шума. Если разброс соседей больше эффекта — эпизодов мало.

**Как починить.**

- Ролик — только иллюстрация поведения; число берётся из отдельного скрипта-приёмщика.
- Оценивать с той же рандомизацией, что в обучении, или строже. Замер на одном фиксированном сценарии измеряет память, а не навык.
- Не путать «оценку для выбора best» (частая, шумная, дешёвая) и «оценку для отчёта» (редкая, большая, честная).

Отдельно стоит знать про код урока 14: скрипт оценки перебирает seed'ы, пока не найдёт первый успешный эпизод, и рисует именно его. Картинка в статье — **лучший из 20**, а не типичный.

### Чужой чекпойнт грузится без единой ошибки и работает хуже нулевого действия

**Симптом.** `PPO.load` отработал, размерности совпали, исключений нет — политика ведёт себя как пьяная.

**Почему.** Совпадение размерностей ничего не гарантирует. Проверено в разборе: чекпойнты ветки, обученной на **другом роботе** (высота 0.1445 м против 0.4272 м, момент 5.26…7 Н·м против 112.86 Н·м), имеют ту же сигнатуру `Box(35,)` / `Box(8,)` и грузятся в чужую среду без ошибки. Результат прогона, 5 эпизодов, команда 0.4 м/с:

```text
свой чекпойнт   эпизоды [1000,1000,1000,1000,1000]  20.00 с
чужой чекпойнт  эпизоды [  28,  34,  37,  28,  33]   0.64 с
```

Чужая политика живёт 0.64 с — **хуже, чем не делать ничего** (пассивная машина живёт 1.06 с). Та же ловушка сработала и внутри одной ветки проекта: чекпойнты от устаревшей версии робота жили 0.55 с, вдвое хуже пассивной машины.

**Как проверить.** Прогнать три эталона рядом:

1. нулевое действие;
2. случайное действие;
3. загруженную политику.

Если загруженная политика хуже нулевого действия — это не «недоучилась», это чужие веса или сломанное наблюдение.

**Как починить.** Класть рядом с каждым набором весов `manifest.txt`: какая модель, какая версия среды, сколько шагов, какие метрики были на приёмке. Тогда «грузится» перестаёт быть аргументом.

### Загрузил чекпойнт без парного `VecNormalize`

**Симптом.** Политика после загрузки ведёт себя как чужая.

**Почему.** Политика ест не сырые наблюдения, а `(obs − mean) / std`, где `mean/std` — накопленная статистика `VecNormalize`, которая непрерывно уезжает по мере изменения поведения. Замерено: у одной из машин разбора статистика наблюдений уезжает на **0.40 сигмы за 2 млн шагов**. То есть чужая или устаревшая статистика искажает вход **сильнее, чем разница между версиями политики**. В худшем случае — донор, обученный на сыром канале, промахивается по масштабу в **43 раза** на первом же канале наблюдения.

**Как проверить.** Проверять парность по номеру шага: рядом с `walk_60000000_steps.zip` обязан лежать `walk_vecnormalize_60000000_steps.pkl` того же номера.

Отдельная ловушка: `EvalCallback` пишет `best_model.zip`, но **не пишет к нему vecnorm**. У `best_model.zip` своей пары не бывает никогда.

**Как починить.**

1. `CheckpointCallback(..., save_vecnormalize=True)`.
2. Частоту чекпойнтов и частоту eval сделать такими, чтобы рядом с каждым `best_model` лежал парный pkl.
3. Для eval-обёртки ставить `training=False, norm_reward=False`, иначе оценка нормирует награду и становится несравнимой между запусками.

Общее правило: всё, что стоит между средой и сетью — нормализатор наблюдений, скейлер награды, фильтр действий — это **часть модели**, а не настройка запуска. Сохраняйте и версионируйте как одно целое.

### Чекпойнты не сохраняются, сторож молчит, ошибок нет

**Симптом.** Скрипт, который ждёт чекпойнт на круглом миллионе шагов, молча простоял весь прогон. Ни ошибки, ни предупреждения. На прошлом прогоне тот же код работал.

**Почему.** `CheckpointCallback` в SB3 считает **вызовы колбэка** (шаги роллаута), а имя файла пишет по `num_timesteps` (env-шаги). Реальный шаг чекпойнта равен `(ckpt_freq // n_envs) * n_envs`. Проверено по исходникам SB3 2.4.1: `callbacks.py` содержит и `self.n_calls`, и `self.num_timesteps` как две разные величины, условие сохранения стоит на `n_calls`, а имя файла собирается из `num_timesteps`.

При 12 средах `500000 // 12 * 12 = 499 992`, номера накапливают сдвиг (например, 103 499 920), и условие `n % 1_000_000 == 0` не выполняется **никогда**. При 8 средах совпадало случайно, потому что 500 000 делится на 8.

**Как проверить.** Просто посмотреть на имена файлов в каталоге чекпойнтов. Если они не круглые — вы уже в этой ситуации.

**Как починить.**

1. Пересчитывать частоту: `ckpt_freq = max(1, args.ckpt_freq // args.envs)`.
2. Никогда не писать условие вида `шаг % круглое_число == 0` по номеру, который сгенерировали не вы. Устойчивый шаблон — разложить чекпойнты по корзинам `n // every` и брать из каждой последний.
3. Каждый автоматический потребитель артефактов обязан уметь сказать «я ничего не нашёл». Молчаливый отказ — самый дорогой класс ошибок здесь.

### После `resume` куррикулум сразу на максимуме

**Симптом.** Продолжаем обучение с чекпойнта 163.5 млн и задаём «два миллиона шагов на ровном полу, потом плавно поднимаем сложность». Робота с первого же шага бросает на максимальный рельеф. В разборе на этом сгорели **три прогона подряд**.

**Почему.** Расписание считалось от `self.num_timesteps`, а это **абсолютный** счётчик: при `resume` он продолжается, а не обнуляется. Значит `--terrain-hold 2000000` означает «до абсолютного шага 2 млн», а не «первые 2 млн этого запуска». Арифметика на старте: `min(1, (163.5M − 2M) / 18M) = 1.0` мгновенно.

Проверено по исходникам SB3 2.4.1 (`common/base_class.py`): при `reset_num_timesteps=True` счётчик обнуляется, иначе `total_timesteps += self.num_timesteps`.

**Как проверить.** Одна строка в лог на первом же шаге после старта:

```python
if self.n_calls <= 1:
    print(f"[расписание] старт на уровне {lvl:.2f} (шаг {int(t)})")
```

Стоимость — одна строка; цена ошибки здесь — трое суток машинного времени.

**Как починить.** Явно решить, от какого нуля считается расписание, и зафиксировать это в документации аргумента. У любого расписания — куррикулум, отжиг lr, рампа сложности — есть этот скрытый вопрос, и при `resume` два нуля расходятся.

### TensorBoard показывает десятки обрывков вместо одной кривой

**Симптом.** В каталоге логов лежат `PPO_1 … PPO_34` вместо одной непрерывной кривой обучения.

**Почему.** `model.learn()` вызывается в цикле по стадиям без `reset_num_timesteps=False`. По умолчанию флаг равен `True`, и SB3 на каждой стадии обнуляет `num_timesteps`, сбрасывает среду и заново стартует внутренний прогресс с 1.0. Расписание learning rate, если оно функция прогресса, перезапускается столько раз, сколько стадий.

**Как проверить.** Посчитать каталоги `PPO_*` в папке логов. Больше одного за прогон — вы в этой ситуации.

**Как починить.**

```python
model.learn(total_timesteps=stage, callback=callback, reset_num_timesteps=False)
```

### Обучение идёт медленнее, чем считали, и замедляется по мере успехов

**Симптом.** Та же машина, то же число сред, а прогон идёт медленнее. Хуже: **чем лучше становится политика, тем медленнее идёт обучение**.

**Почему.** `EvalCallback` гонит `n_eval_episodes` эпизодов **последовательно в одной среде**, без векторизации, с остановкой обучения. Пока политика падала, эпизод обрывался примерно на 480 шагах. Как только она перестала падать, эпизод стал полным (1000 шагов), и цена оценки **удвоилась сама**, без единой правки конфигурации.

Замер из разбора: интервалы с оценкой шли на 1218 fps против 1786 без неё и занимали **26 % времени прогона**.

**Как проверить.** Замерить fps с оценкой и без неё на своей задаче.

**Как починить.** Отвязать частоту оценки от частоты чекпойнтов: чекпойнты дёшевы и нужны часто, оценка нужна вдвое реже — её задача ловить тренд, а не каждый шаг. И назвать вслух размен: меньше эпизодов оценки — быстрее, но шумнее выбор `best_model`.

### Дрон висит выше цели, и ошибка не зависит от `kp_z`

**Симптом.** Каскад управления «работает», но высота держится с постоянной ошибкой около 0.55 м, и эта ошибка не меняется, сколько ни крути коэффициент по высоте.

**Почему.** Внутренний контур с усилениями «на глаз» уходит в высокочастотный предельный цикл, а тяга не может быть отрицательной — `clip(0, 4.6)` **выпрямляет** колебание и превращает дребезг в постоянную подъёмную силу. Замеры из разбора:

| Величина | Значение |
|---|---|
| Доля шагов с насыщением | 0.9992 |
| Средняя команда до клиппинга | −0.0019 Н |
| Средняя команда после клиппинга | 1.8158 Н |
| Паразитная подъёмная сила | 7.2707 Н |
| Вес дрона | 7.2594 Н |
| Итог | дрон висит на дребезге: при команде 1.2 м стоит на 1.746 м |

**Как проверить.** Логировать долю насыщенных шагов и разность `mean(clip(u)) − mean(u)`. Если доля насыщения близка к единице, а разность сравнима с весом — вы нашли причину.

**Как починить.** Усиления считать из физики, а не подбирать. Для RL-версии той же задачи это тот же капкан: политика с нуля охотно находит режим «дребезжать на нижней границе», если нет штрафа за резкость действия вида `−‖a − a_prev‖²`.

### Дрон улетает вверх с первого шага каждого эпизода

**Почему.** Наивное отображение действия `a ∈ [−1, 1] → [0, 4.6]` при тяге висения **39.45 %** от диапазона означает, что висение приходится на `a = −0.21`. Гауссова политика стартует со средним 0, то есть с тяговооружённостью **1.27**. Первые сотни тысяч шагов уходят на то, чтобы сдвинуть среднее.

**Как проверить.** Средняя тяга за эпизод в самом начале обучения. Она должна быть около 1.81 Н, а не 2.3 Н.

**Как починить.** Нормировать действие относительно висения: `тяга = hover · (1 + 0.6 · a)`. Тогда `a = 0` есть в точности висение, а диапазон 0.4…1.6 от висения покрывает и спуск, и энергичный набор.

### Дрон крутится вокруг вертикали

**Почему.** Рыскание у квадрокоптера почти бесплатно: гравитация его не восстанавливает и не наказывает. Замер: 20 % дифференциала винтов дают **−122.49° за одну секунду** при нулевом дрейфе высоты. Политика, которой не запрещено, начинает вращаться. В задаче покрытия это ещё и **вознаграждается по ошибке**: вращающаяся камера случайно набирает покрытие.

**Как проверить.** Гистограмма `|ωz|` в конце эпизода. У здоровой политики медиана меньше 0.5 рад/с.

**Как починить.** Штраф `−0.02·‖ω‖²`; ограничение `ωz` в самом действии; `sin/cos` пеленга в наблюдении, чтобы «смотреть на объект» было достижимо без вращения.

### Награда за высоту родила «прыгуна»

**Почему.** Если в награде стоит `+k·z` или бонус «за то, что не на земле», PPO находит баллистический режим: полная тяга вверх, свободное падение, повтор. Средняя высота высокая, средняя награда высокая, управления нет. Тяговооружённость 2.535 делает такой режим доступным.

**Как проверить.** В реестре членов награды член за позицию близок к нулю при высокой суммарной награде, а длина эпизода пилообразно колеблется.

**Как починить.** Платить `exp(−2·d²)` за близость к **точке**, а не за координату; добавить `−0.10·‖v‖²`; требовать выживания до конца эпизода, а не набранной высоты.

### Штрафую величину — становится хуже

**Почему.** Штрафуется то, чего **нет в наблюдении**. Реальный случай: робот уводил с прямой на 112° за 20 секунд, добавили штраф за накопленную ошибку курса, прогнали 7 млн шагов — стало хуже: путь по полигону 2.56 → 2.41 м, падения 18 → 25. В наблюдении политики 35 каналов, и ошибки курса там нет ни в каком виде: гравитация в СК корпуса вокруг вертикали инвариантна, гироскоп даёт мгновенную угловую скорость, а не накопленный угол. Агент мог уменьшать штрафуемую величину только вслепую — ценой всего остального.

**Как проверить.** Чек-лист перед добавлением любого члена награды:

1. величина выводима из наблюдения?
2. если нет — её надо либо добавить в наблюдение, либо замкнуть контур в управлении, а не штрафовать.

Формулировка из разбора: **прежде чем штрафовать величину, проверь, что она есть в наблюдении. Дешевле любого прогона.**

**Как починить.** Замкнуть обратную связь через уже существующий наблюдаемый канал. Бонус: правка, не меняющая размерность наблюдения, проверяется на готовых весах за минуты вместо суток прогона.

### За 30 минут ничего не выучилось — это сломано или так и должно быть?

Отдельный подраздел, потому что студент, который этого не знает, решит, что у него сломался код.

**Факт из разбора.** Для двуногого робота на отметке 6.5 млн шагов средняя длина эпизода равна **ровно 53.0 шага** — и она ровно 53.0 на каждой из 13 контрольных точек от 0.5 до 13.0 млн. Независимо замеренная пассивная машина с нулевым действием живёт **53 шага**. То есть полчаса обучения дают политику, неотличимую от «ничего не делать». Перелом наступает на 13.5 млн шагов, это примерно час и две минуты. Полный 20-секундный эпизод — на 16.5 млн, около 1 ч 16 мин. Вердикт «ходит» со скоростью 0.356 м/с — на 24 млн, около 1 ч 51 мин.

**Как проверить, что дело не в вас.** Сравнить длину эпизода вашей политики с длиной эпизода при нулевом действии. Если они совпадают — политика ещё не научилась ничему, и это нормальная стадия, а не баг.

**Что делать.** Планировать бюджет честно: полчаса — это «кривая пошла вверх» плюс запуск готовых весов, а не готовый результат.

---

## git и кодировки

### `warning: CRLF will be replaced by LF in <файл>.`

Проверено на git 2.21.0.windows.1, дословно:

```text
warning: CRLF will be replaced by LF in crlf.md.
The file will have its original line endings in your working directory
```

**Почему.** В репозитории курса лежит `.gitattributes` с правилом `* text=auto eol=lf`: в индексе всегда LF. На машине разработчика при этом `core.autocrlf = true` (проверено). Оба механизма делают одно и то же, и предупреждение — это git, честно сообщающий о нормализации при добавлении в индекс.

**Как проверить.**

```bash
git config core.autocrlf
git check-attr text eol -- README.md
```

**Как починить.** Ничего чинить не надо — это информационное сообщение. Правило курса: файлы в репозитории **UTF-8 без BOM, переводы строк LF**; `.gitattributes` это обеспечивает. Проверено сканированием репозитория: файлов `.md` и `.py` с BOM — **0**. Что лежит в индексе, а что в рабочем дереве, показывает одна команда:

```bash
git ls-files --eol
```

Замер на момент написания: в индексе (`i/`) CRLF нет ни у одного текстового файла, а в рабочем дереве (`w/`) CRLF стоит у 39 файлов и ещё у 22 концы строк смешанные. Это нормально: `core.autocrlf` разворачивает LF в CRLF при выгрузке. Число файлов в рабочем дереве меняется от машины к машине и от выгрузки к выгрузке — сверяйте не с цифрой, а с колонкой `i/`: там обязан быть `lf`.

### Git показывает весь файл изменённым, хотя вы правили одну строку

**Почему.** Файл был перезаписан редактором или скриптом с другими переводами строк, и git видит различие в каждой строке.

**Как проверить.**

```bash
git diff --stat <файл>
git diff --ignore-cr-at-eol <файл>
```

Если второй вариант показывает одну-две строки, а первый — весь файл, дело именно в переводах строк.

**Как починить.** Убедиться, что `.gitattributes` подхватился, и перенормализовать файл:

```bash
git add --renormalize <файл>
```

Отдельная ловушка Windows PowerShell 5.1: `Out-File` и `>` пишут UTF-8 **с BOM**, а `Set-Content` и `Add-Content` вообще пишут в системной ANSI-кодировке. Для файлов курса используйте `-Encoding utf8` явно, а лучше пишите файлы редактором или скриптом, который умеет UTF-8 без BOM.

### Кириллица превратилась в `Р•РґРёРЅС‹Рµ РїРµСЂРµРІРѕРґС‹`

Проверено, воспроизводится в одну строку. Файл в UTF-8, прочитан в Windows PowerShell 5.1 без указания кодировки:

```powershell
Get-Content .gitattributes
```

```text
# Р•РґРёРЅС‹Рµ РїРµСЂРµРІРѕРґС‹ СЃС‚СЂРѕРє: РІ СЂРµРїРѕР·РёС‚РѕСЂРёРё LF, ...
```

Тот же файл с явной кодировкой:

```powershell
Get-Content .gitattributes -Encoding UTF8
```

```text
# Единые переводы строк: в репозитории LF, в рабочем дереве — родные для ОС
```

**Почему.** Windows PowerShell 5.1 по умолчанию читает файлы в системной ANSI-кодировке (для русской Windows это cp1251), а файл записан в UTF-8. Каждый двухбайтовый символ кириллицы превращается в два «латинских» символа. Кодовая страница консоли тут ни при чём: проверено, `chcp` показывал 65001, и это не помогло.

**Как проверить.** Первые три байта файла:

```powershell
[System.IO.File]::ReadAllBytes("файл.md")[0..2] | ForEach-Object { $_.ToString('x2') }
```

`ef bb bf` — это BOM, файл в UTF-8 с BOM. Любые другие значения у текстового файла курса означают UTF-8 без BOM, как и требуется.

**Как починить.** Всегда указывать кодировку явно:

```powershell
Get-Content файл.md -Encoding UTF8
```

В PowerShell 7 поведение по умолчанию другое, но на машине разработчика PowerShell 7 не установлен, поэтому **не проверено**.

### Имена файлов в `git status` выглядят как `"\320\243\321\200\320\276\320\272 1.md"`

Проверено, дословный вывод `git status --short` для файла с кириллицей в имени:

```text
A  "\320\241\321\223\320\241\320\202\320\240\321\225\320\240\321\224 1.md"
```

**Почему.** По умолчанию `core.quotepath = true`, и git экранирует все не-ASCII байты в именах файлов восьмеричными последовательностями.

**Как починить.** Проверено, помогает сразу:

```bash
git config core.quotepath false
git status --short
```

```text
A  "урок 1.md"
```

Это настройка отображения; на содержимое репозитория она не влияет.

### Ссылка на файл с пробелами в имени не открывается

**Почему.** Каталоги курса содержат пробелы и скобки: `lesson 9 (lidar sensors)`. Обычная markdown-ссылка на такой путь ломается на первом же пробеле.

**Как починить.** Оформлять путь в угловых скобках:

```markdown
[текст](<lesson 9 (lidar sensors)/2d_lidar.md>)
```

И только относительным путём — абсолютные ссылки вида `https://github.com/.../blob/main/...` внутрь репозитория запрещены соглашениями курса: они ломаются при форке, переименовании ветки и просмотре офлайн.

### `bash: cd: ...: No such file or directory` при команде с пробелами

**Почему.** Путь с пробелами не закавычен.

**Как починить.**

```bash
cd "lesson 14 (RL custom models)/track_a_car"
```

Кавычки обязательны везде, где путь содержит пробел или скобку, включая аргументы `python`, `colcon --packages-select` и `ros2 launch`.

---

## Что делать, если ошибки здесь нет

1. **Прочитайте первую ошибку, а не последнюю.** В логах `colcon`, `ros2 launch` и Gazebo первая ошибка обычно порождает десятки последующих.
2. **Сократите до минимального примера.** Один узел вместо launch-файла, пустой мир вместо мира с роботом, `CartPole-v1` вместо своей среды.
3. **Сравните с эталоном.** Для RL — с нулевым действием и со случайным действием; для ROS 2 — с `demo_nodes_cpp talker` / `demo_nodes_py listener`; для Gazebo — с `empty.sdf`.
4. **Проверьте, что вы в том окружении, в котором думаете:**

```bash
echo $ROS_DISTRO
which ros2
python -c "import sys; print(sys.executable)"
```

5. Если после этого ошибка воспроизводится — добавьте её сюда по тому же шаблону: дословный заголовок, почему, как проверить, как починить.
