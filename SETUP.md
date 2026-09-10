# Установка окружения курса

Этот файл — единственная точка входа по установке. Все команды взяты из статей курса либо
проверены на машине разработчика; там, где число или поведение не измерялось, так и написано:
«не замерено» или «в курсе не описано».

Полные пошаговые инструкции по каждой теме остаются в уроках — здесь собрано то, что нужно
поставить до начала работы, и в каком порядке.

---

## Главное: курс делится на две независимые дорожки

| Дорожка | Уроки | Что нужно | ROS 2 | ОС |
|---|---|---|---|---|
| **ROS 2** | 1-12 | ROS 2 Jazzy, colcon, Gazebo Harmonic, Nav2, TurtleBot3 | обязателен | Ubuntu 24.04 (нативно, WSL2 или VM) |
| **RL** | 13-14 | Python 3.12, venv, MuJoCo, Gymnasium, Stable-Baselines3, PyTorch | **не нужен** | Windows, Linux или macOS |

Это ключевая мысль: **половину курса можно пройти на Windows вообще без ROS 2**. Уроки 13-14 —
это чистый Python, физика в MuJoCo и обучение с подкреплением; ни одной ROS-ноды там не
запускается. Материалы урока 13 и трека A урока 14 разрабатывались и проверялись именно на
Windows 11 с системным Python 3.12.3.

Обратное тоже верно: дорожка ROS 2 не требует ни GPU, ни PyTorch.

```
       ROS 2                                RL
  уроки 1 → 12                       уроки 13 → 14
  Ubuntu 24.04                    Windows / Linux / macOS
  ROS 2 Jazzy                         Python 3.12 + venv
  Gazebo, Nav2, TF2                MuJoCo, Gymnasium, SB3
```

Пересечений между дорожками на уровне установки нет — их можно ставить в любом порядке или
только одну из двух.

---

## Дорожка ROS 2 (уроки 1-12)

Целевая конфигурация курса — **ROS 2 Jazzy Jalisco на Ubuntu 24.04 (Noble Numbat)**.
Совместимость с Humble на Ubuntu 22.04 отмечается отдельно, см. раздел «Humble как совместимость».

### Выбор платформы

| Вариант | Что работает | Что не работает / на что смотреть | GUI (RViz2, Gazebo, turtlesim) |
|---|---|---|---|
| **Ubuntu 24.04 нативно** | всё, включая USB-устройства и сеть | требует отдельного диска или машины | работает штатно |
| **Windows 11 + WSL2** | основной вариант курса для Windows; вся командная разработка ROS 2 | тяжёлая 3D-графика, нестандартные USB-устройства, сетевые эксперименты | через WSLg переменные `DISPLAY` / `WAYLAND_DISPLAY` обычно настраиваются автоматически |
| **Windows 10 + WSL2** | то же, что выше, кроме GUI из коробки | WSLg нет | нужен внешний X-сервер, либо полноценная VM |
| **VM (VirtualBox / VMware)** | полный Ubuntu, свои USB и сеть | медленнее нативного, аппаратное ускорение 3D ограничено | работает, но рендер Gazebo может потребовать программного режима |
| **Docker** | **в курсе не описан**, статьи нет | — | — |

Требования к WSL2 из статьи курса: Windows 10/11 с включённой виртуализацией в BIOS/UEFI,
права администратора, **20-30 GB свободного места**. Для RViz2 и `turtlesim` с GUI предпочтительна
Windows 11 с WSLg.

Про VM в статье курса сказано прямо: команды установки ROS 2 внутри Ubuntu остаются теми же —
меняется только способ получить саму Ubuntu 24.04.

Про Docker: официальные образы ROS 2 существуют, но **в курсе нет ни статьи, ни проверенных
команд**, и проброс GUI в контейнер здесь не проверялся. Если выбираете Docker, действуйте
по официальной документации ROS 2, а не по этому файлу.

### Установка ROS 2 Jazzy на Ubuntu 24.04

Полная статья: [Установка и проверка ROS 2 Jazzy](<lesson 1 (install ROS2 and testing)/ros2_jazzy_install.md>).

Локаль UTF-8:

```bash
locale
sudo apt update && sudo apt install locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
```

Репозитории:

```bash
sudo apt install software-properties-common
sudo add-apt-repository universe
sudo apt update && sudo apt install curl -y
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
```

Сам ROS 2 — полная установка (GUI-инструменты и симуляторы включены):

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install ros-jazzy-desktop
```

Минимальный вариант без GUI — `ros-jazzy-ros-base`, но тогда RViz2 и `turtlesim` из уроков 1 и 6
работать не будут.

Инструменты сборки:

```bash
sudo apt install python3-colcon-common-extensions python3-rosdep
sudo rosdep init
rosdep update
```

Подключение окружения в каждом новом терминале:

```bash
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

Объём установки `ros-jazzy-desktop` на диске — **не замерено**.

### Windows + WSL2

Полная статья: [Windows + WSL2: локальная среда для ROS 2 Jazzy](<lesson 1 (install ROS2 and testing)/windows_wsl2_jazzy_install.md>).

В PowerShell от имени администратора:

```powershell
wsl --list --online
wsl --install -d Ubuntu-24.04
```

После перезагрузки, уже внутри Ubuntu:

```bash
lsb_release -a
sudo apt update
sudo apt upgrade -y
sudo apt install -y curl gnupg lsb-release software-properties-common
```

Статья про WSL2 использует **другой способ подключить apt-источник ROS 2** — через deb-пакет
`ros2-apt-source`, а не через ручное добавление ключа и строки в `sources.list.d`:

```bash
sudo add-apt-repository universe
sudo apt update
sudo apt install -y curl
export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F'"' '{print $4}')
curl -L -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo ${UBUNTU_CODENAME:-${VERSION_CODENAME}})_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb

sudo apt update
sudo apt install -y ros-jazzy-desktop ros-dev-tools
```

Оба способа рабочие; достаточно любого одного. Не смешивайте их в одной системе — получите
два источника ROS 2 в apt.

Проверка GUI:

```bash
sudo apt install -y ros-jazzy-turtlesim
ros2 run turtlesim turtlesim_node
```

Если окно не открылось:

```bash
echo $DISPLAY
echo $WAYLAND_DISPLAY
```

На Windows 11 с WSLg эти переменные обычно уже заданы. На Windows 10 понадобится внешний
X-сервер или полноценная VM с Ubuntu 24.04.

**Про расположение репозитория.** Если репозиторий лежит в файловой системе Windows, путь внутри
WSL2 начинается с `/mnt/c/...`. Статья курса прямо предупреждает: для максимальной скорости
сборки держите рабочую копию внутри Linux-файловой системы, например в `~/mobile-robotics-basics`.

### Настройка и проверка окружения

Статьи: [Настройка окружения ROS 2](<lesson 1 (install ROS2 and testing)/ros2_environment.md>) и
[Диагностика через ros2doctor](<lesson 1 (install ROS2 and testing)/ros2_doctor.md>).

Underlay — базовая установка в `/opt/ros/jazzy`, overlay — ваш workspace `ros2_ws`. Порядок
подключения важен: сначала underlay, потом overlay.

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
source install/setup.bash
```

`ROS_DOMAIN_ID` разделяет ROS 2 graph между студентами в одной сети. Значение от `0` до `101`:

```bash
echo "export ROS_DOMAIN_ID=17" >> ~/.bashrc
```

Диагностика:

```bash
ros2 doctor
ros2 doctor --report
```

Предупреждения `ros2 doctor` не всегда означают неисправность, но их нужно прочитать.

### Humble как совместимость

Курс основан на Jazzy. Humble Hawksbill на **Ubuntu 22.04** описан как совместимая версия:
[Установка ROS 2 Humble](<lesson 1 (install ROS2 and testing)/ros2_humble_install.md>).

Отличия установки — только в имени дистрибутива:

```bash
sudo apt install ros-humble-desktop
source /opt/ros/humble/setup.bash
rosdep install -i --from-path src --rosdistro humble -y
```

Ожидаемый `ROS_DISTRO` — `humble` вместо `jazzy`.

Важные ограничения: Humble живёт на Ubuntu 22.04, а не 24.04, и Gazebo Harmonic для Humble
курс не проверял — уроки 8 и 11 написаны под Jazzy + Harmonic. Считайте Humble вариантом
для уроков 1-7, а не для всего курса.

### Gazebo Harmonic (урок 8)

Статья: [Установка Gazebo Harmonic](<lesson 8 (Gazebo)/01-installation.md>).

На Jazzy «родной» симулятор — **Gazebo Harmonic** (LTS, поддержка до 2028), а не классический
Gazebo 11. CLI называется `gz`, плагины — `gz-sim-*`, типы сообщений — `gz.msgs.*`.

```bash
sudo apt update
sudo apt install -y \
    ros-jazzy-ros-gz \
    ros-jazzy-ros-gz-sim \
    ros-jazzy-ros-gz-bridge \
    ros-jazzy-ros-gz-interfaces \
    ros-jazzy-teleop-twist-keyboard
```

Метапакет `ros-jazzy-ros-gz` подтягивает сам Gazebo Harmonic (`gz-sim8`, `gz-tools2`, рендер `ogre2`).

Если `gz: command not found` — метапакет не доустановил инструменты:

```bash
sudo apt install gz-tools2
```

**GUI в WSL2 и виртуалке.** Аппаратного ускорения там часто нет, окно Gazebo чёрное или мигает.
Лечится программным рендером, и этот флаг придётся использовать для всех последующих запусков:

```bash
LIBGL_ALWAYS_SOFTWARE=1 gz sim empty.sdf
```

По умолчанию симуляция стартует на паузе — если `/clock` пустой, нажмите **Play** в нижнем
левом углу окна.

### Nav2 (урок 10)

Статья: [Знакомство с Nav2](<lesson 10 (Nav2)/introducing_nav2.md>).

```bash
sudo apt install ros-$ROS_DISTRO-navigation2 ros-$ROS_DISTRO-nav2-bringup
```

Отдельный пакет `slam_toolbox` курсу **не нужен**: карта строится Cartographer'ом из набора
TurtleBot3 (`turtlebot3_cartographer`), см. [Карта и локализация AMCL](<lesson 10 (Nav2)/nav2_localization.md>).
Сохранение карты идёт через `nav2_map_server`, который приходит с Nav2:

```bash
ros2 run nav2_map_server map_saver_cli -f ~/map
```

### TurtleBot3 (урок 11)

Статья: [Установка TurtleBot3 Simulations для ROS 2 Jazzy](<lesson 11 (turtlebot3 sim)/install_jazzy_turtlebot3.md>).

```bash
sudo apt update
sudo apt install ros-jazzy-turtlebot3*
```

> **Предупреждение по статье курса.** В статье команда записана как
> `sudo apt install ros-jazzy-turtlebot3* ros-jazzy-gazebo-ros-pkgs`. Пакет
> `ros-jazzy-gazebo-ros-pkgs` — это интеграция с классическим Gazebo, которого в Jazzy нет;
> его аналог в Jazzy — `ros-jazzy-ros-gz` из урока 8. Если apt ответит
> `Unable to locate package ros-jazzy-gazebo-ros-pkgs`, это ожидаемо: ставьте только
> `ros-jazzy-turtlebot3*`, а мост берите из урока 8.

Дальше по статье — отдельный workspace `~/turtlebot3_ws` с клоном
`turtlebot3_simulations`, `rosdep install`, `colcon build` и переменные окружения:

```bash
echo "export TURTLEBOT3_MODEL=burger" >> ~/.bashrc
source ~/.bashrc
```

Статья предупреждает, что ветка `jazzy` в репозитории `turtlebot3_simulations` может
отсутствовать и понадобится `main` или `rolling` — курс это не проверял, ветку смотрите
на месте через `git branch -a`.

### micro-ROS (урок 12)

**В уроке 12 нет статьи с установкой.** Урок разбирает архитектуру micro-ROS Client / Agent /
XRCE-DDS, ROS-контракт микроконтроллера и диагностику; сценарий занятия рассчитан на работу
**без железа**. Единственные команды запуска, приведённые в уроке
([Agent, firmware и проверка graph](<lesson 12 (micro-ros)/micro_ros_agent_firmware.md>)):

```bash
ros2 run micro_ros_agent micro_ros_agent udp4 --port 8888 -v6
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -v6
```

То есть пакет `micro_ros_agent` должен быть в системе, но **способ его установки в курсе не
описан и здесь не проверялся**. То же касается ESP-IDF и прошивки: урок ссылается на внешний
компонент [micro_ros_espidf_component](https://github.com/micro-ROS/micro_ros_espidf_component),
но своей инструкции по установке тулчейна не даёт. Ставьте по официальной документации
micro-ROS и ESP-IDF.

Если железа нет — урок проходится целиком без Agent'а, по разделу «Практика, диагностика и зачёт».

### Урок 9 (лидары)

Отдельной установки не требует: статьи [2D-лидар](<lesson 9 (lidar sensors)/2d_lidar.md>) и
[3D-лидар](<lesson 9 (lidar sensors)/3d_lidar.md>) работают с уже установленными `tf2_ros` и
данными из симуляции уроков 8 и 11.

---

## Сборка workspace курса `ros2_ws`

В `ros2_ws/src` лежат **12 пакетов**, которые создаются в практических статьях. Канонический
порядок сборки — из [ros2_ws/src/README.md](<ros2_ws/src/README.md>) и статьи
[rosdep: зависимости workspace](<lesson 2 (nodes and topics)/rosdep.md>):

```bash
cd ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
rosdep install -i --from-path src --rosdistro $ROS_DISTRO -y
colcon build --symlink-install
source install/setup.bash
```

### Предупреждение: `my_robot_gazebo` тянет за собой Gazebo Harmonic

Это проверено чтением `ros2_ws/src/my_robot_gazebo/package.xml`. Пакет объявляет
`exec_depend` на:

```
geometry_msgs, launch, launch_ros, nav_msgs, robot_state_publisher,
ros_gz_bridge, ros_gz_sim, rviz2, sensor_msgs, tf2_ros,
teleop_twist_keyboard, xacro
```

Ключи `ros_gz_bridge` и `ros_gz_sim` резолвятся в пакеты Gazebo Harmonic, которые ставятся
**только в уроке 8**. Поэтому команда `rosdep install -i --from-path src` из «быстрого старта»,
запущенная на всём `src` до урока 8, попытается доустановить Gazebo — и на чистой системе
это либо длинная незапланированная установка, либо ошибка rosdep.

Важное уточнение, чтобы не пугать зря: `my_robot_gazebo` — пакет типа `ament_python` без
компилируемого кода, эти зависимости объявлены как `exec_depend`, то есть нужны для **запуска**,
а не для сборки. Сама `colcon build` из-за них не падает — спотыкается именно шаг `rosdep install`.

Три честных варианта:

1. **Сначала урок 8.** Поставьте Gazebo Harmonic по разделу выше, и `rosdep install` пройдёт
   без сюрпризов. Это рекомендуемый путь, если вы идёте по курсу подряд.
2. **Пропустить ключи Gazebo** — если Gazebo пока не нужен:

   ```bash
   rosdep install -i --from-path src --rosdistro $ROS_DISTRO -y \
       --skip-keys "ros_gz_sim ros_gz_bridge"
   ```

3. **Собрать без этого пакета** — если урок 8 не планируется вовсе:

   ```bash
   colcon build --symlink-install --packages-ignore my_robot_gazebo
   ```

**Что здесь не проверено:** сама сборка `ros2_ws` в рамках подготовки этого файла не
запускалась. На машине разработчика есть ROS 2 **Humble** в WSL2 (Ubuntu 22.04) — на нём
проверены сообщения об ошибках из [TROUBLESHOOTING.md](TROUBLESHOOTING.md), — но целевой
связки Jazzy + Ubuntu 24.04 нет, и workspace курса на ней не собирался. Список зависимостей
и тип пакета прочитаны из манифестов, поведение rosdep описано по смыслу его работы,
а не по логу прогона.

Отдельно: в корневом [README.md](README.md) и в [ros2_ws/src/README.md](<ros2_ws/src/README.md>)
перечислено 11 пакетов — `my_robot_gazebo` в списках нет, хотя на диске он есть. Именно из-за
него и возникает описанная выше ловушка rosdep.

### Мелочь про `__pycache__`

В рабочем дереве `ros2_ws/src` лежат 22 каталога `__pycache__`, причём с байткодом двух разных
версий Python (`cpython-312` и `cpython-313`). В git они не попадают — закрыты корневым
[.gitignore](.gitignore), — но на диске остаются. На сборку они не влияют, но если видите
странности, удалите их и пересоберите:

```bash
find src -name __pycache__ -type d -exec rm -rf {} +
colcon build --symlink-install
```

---

## Дорожка RL (уроки 13-14)

ROS 2 здесь не нужен. Всё работает на системном Python — на Windows, Linux или в WSL2.

### Python и виртуальное окружение

Целевая версия — **Python 3.12** (на машине разработчика 3.12.3).

Windows (PowerShell), из корня репозитория:

```powershell
python --version
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Linux / WSL2 / macOS:

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### Установка пакетов

Способ курса — файл с пинами в корне репозитория:

```bash
pip install -r requirements.txt
```

Он ставит ровно те версии, на которых написаны и проверены уроки:

| Пакет | Версия | Зачем |
|---|---|---|
| `gymnasium` | 1.0.0 | API среды: `reset` / `step`, пространства наблюдений и действий |
| `stable-baselines3` | 2.4.1 | PPO, векторные среды, колбэки, `evaluate_policy` |
| `torch` | 2.6.0 | бэкенд нейросетей для SB3 |
| `numpy` | 2.0.2 | массивы наблюдений и действий |
| `cloudpickle` | 3.0.0 | сериализация среды для `SubprocVecEnv` |
| `pandas` | 3.0.2 | логгер прогресса SB3 |
| `mujoco` | 3.9.0 | физика и viewer для MJCF-моделей урока 14 |
| `matplotlib` | 3.10.9 | кривые обучения, схемы, траектории |
| `pillow` | 12.2.0 | кадры эпизодов и анимации |
| `tensorboard` | 2.20.0 | `tensorboard --logdir logs` |

Для сравнения — что написано в самих уроках, без пинов:

* [урок 13](<lesson 13 (stable baselines3)/README.md>):
  `pip install stable-baselines3 gymnasium matplotlib pillow tensorboard`;
* [урок 14, трек A](<lesson 14 (mujoco car parking)/README.md>):
  `pip install mujoco stable-baselines3 gymnasium matplotlib pillow`.

`requirements.txt` — объединение этих двух наборов с зафиксированными версиями.

### CUDA: какой torch ставить

Строка `torch==2.6.0` в `requirements.txt` берёт колесо с PyPI. Этого достаточно для всех
уроков курса.

Если нужна именно CUDA-сборка (на машине разработчика стоит `2.6.0+cu124`), ставьте torch
из индекса PyTorch **до** установки остальных зависимостей:

```bash
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

Проверка:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

На машине разработчика печатает:

```text
2.6.0+cu124 True
```

Если печатает `False` — стоит CPU-сборка torch (в имени версии нет `+cu...`) либо драйвер
NVIDIA не виден процессу. Для курса это не блокер, см. следующий раздел.

### Нужен ли GPU

Короткий ответ: **нет**. Ни один урок курса не требует видеокарты, и в замерах,
сделанных при подготовке уроков 13-14, GPU **не дал выигрыша ни в одном треке**.

| Где | Что измерено | Вывод |
|---|---|---|
| Трек A (машинка, урок 14) | в коде урока `device="cpu"`, сеть `[64, 64]`, обучение ~30-40 мин на CPU | GPU не нужен |
| Трек B (двуногий, урок 14) | MLP `256×128`, батч 4096-16384: на CPU **2063 fps** против **741 fps** на RTX 4060 Laptop | **CPU втрое быстрее**; кроме того, два PPO на одной 4060 дают CUDA OOM — «GPU не делится» |
| Трек C (дрон, урок 14) | `SubprocVecEnv`, 8 сред, `device="cpu"`: замеры 2863-3286 fps, задача решается за 600 тыс. шагов = 3 мин 13 с | GPU вреден: перенос тензоров не окупается, узкое место — CPU-симуляция |

Причина одна и та же во всех трёх случаях: политики маленькие (MLP), а узкое место — шаг
физики MuJoCo, который считается на CPU. Маленькая сеть не загружает GPU даже частично, зато
перекачка тензоров на каждом минибатче стоит дороже самого умножения. Поэтому уроки ускоряются
не видеокартой, а **параллельными средами**: `SubprocVecEnv` на 8 процессов из 24 доступных ядер.

Правило курса: **бюджет обучения определяется не тем, есть ли видеокарта, а тем, что дороже —
шаг среды или шаг оптимизатора.** Для маленьких MLP это шаг среды, и значит решают ядра CPU.

GPU в курсе реально пригождается в одном месте — рендер: сенсор `gpu_lidar` в Gazebo (урок 8)
быстрее CPU-варианта `ray`, а рендер окна MuJoCo без ускорения заметно тормозит.

### Ловушка Windows: `SubprocVecEnv` и файл подкачки

Замерено при подготовке трека C на этой же машине: запуск **16 воркеров** `SubprocVecEnv`
положил машину — каждый воркер импортировал `stable_baselines3.common.monitor`, а вместе с ним
torch, и Windows ответил:

```text
The paging file is too small for this operation to complete
```

Прогон умер молча. Что с этим делать:

* начинайте с **8 воркеров**, а не с числа ядер;
* в воркере импортируйте только `mujoco` / `gymnasium` / `numpy`, а `Monitor` заменяйте на
  `VecMonitor` поверх векторной среды;
* ограничьте потоки: `torch.set_num_threads(1)` и переменная окружения `OMP_NUM_THREADS=1`.

Родственная проблема на Linux — память: на треке B 8 сред занимали около 3.7 ГБ, 12 сред —
около 7 ГБ; при нехватке MuJoCo падает с `ValueError: Error: engine error: Could not allocate memory`.

### Запуск примеров

Урок 13:

```bash
cd "lesson 13 (stable baselines3)/code/01_cartpole"
python train_cartpole.py
python evaluate_cartpole.py
```

Урок 14, трек A. Осторожно с каталогом: урок 14 строится в `lesson 14 (RL custom models)`
(треки A/B/C, статей там пока нет), а рабочий код парковки, который станет треком A, до сих пор
лежит в отдельном каталоге `lesson 14 (mujoco car parking)`. Запускается пока он:

```bash
cd "lesson 14 (mujoco car parking)/code"
python car_parking_env.py     # проверка среды
python train_parking.py       # обучение (~30-40 мин на CPU)
python evaluate_parking.py    # анимация и траектории
python watch_parking.py       # живой просмотр в окне MuJoCo
```

Модели сохраняются в `models/`, логи TensorBoard — в `logs/`, картинки — в `images/`;
`models/` и `logs/` в git не попадают.

---

## Приложения

### Приложение А — ROS 2, MCP и LLM-агенты

[ros2-mcp-openclaw_1.md](<appendix A (ros2 llm agents)/ros2-mcp-openclaw_1.md>) — обзорный
материал про MCP и операторский слой над ROS 2. Установки не требует.

### Приложение Б — Microduck: инференс политик в MuJoCo

[README приложения Б](<appendix B (microduck policy inference)/README.md>) описывает **своё
отдельное окружение** и не использует `requirements.txt` курса: там Windows 10/11, Python 3.12
через [uv](https://docs.astral.sh/uv/), около 3 ГБ диска, отдельные репозитории
`microduck` и `microduck_rl`, ONNX-политики и своя версия MuJoCo (3.10). GPU не обязателен —
инференс и физика идут на CPU.

Ставьте его по README самого приложения, а не по этому файлу.

---

## Чек-лист: проверка установки

### Дорожка ROS 2

```bash
source /opt/ros/jazzy/setup.bash
printenv | grep ROS
```

Ожидаемо (из статьи урока 1):

```text
ROS_VERSION=2
ROS_PYTHON_VERSION=3
ROS_DISTRO=jazzy
```

```bash
echo $ROS_DISTRO      # jazzy
ros2 node list        # пустой список
ros2 topic list       # два топика: /parameter_events и /rosout
ros2 doctor           # завершается без критических ошибок
```

Живая проверка в двух терминалах (в каждом сначала `source /opt/ros/jazzy/setup.bash`):

```bash
ros2 run demo_nodes_cpp talker     # терминал 1
ros2 run demo_nodes_py listener    # терминал 2
```

Ожидаемо: listener получает сообщения от talker.

GUI:

```bash
ros2 run turtlesim turtlesim_node
```

Ожидаемо: открывается окно с черепахой. Если нет — см. раздел про WSL2 и `DISPLAY`.

Workspace:

```bash
cd ros2_ws && source install/setup.bash
ros2 pkg list | grep my_turtle_controller
```

Ожидаемо: пакет найден.

Gazebo (после урока 8):

```bash
gz sim --version      # 8.x (Harmonic)
gz topic -l           # /clock, /stats, /world/empty/...
```

Nav2 (после урока 10):

```bash
ros2 pkg list | grep nav2
```

Ожидаемо, среди прочих: `nav2_bringup`, `nav2_bt_navigator`, `nav2_planner`, `nav2_controller`,
`nav2_map_server`, `nav2_amcl`, `nav2_lifecycle_manager`.

```bash
ros2 interface show nav2_msgs/action/NavigateToPose
```

Ожидаемо: три секции, разделённые `---` — цель, результат, обратная связь.

### Дорожка RL

Версии — одной командой:

```bash
python -c "import sys, numpy, gymnasium, mujoco, stable_baselines3, torch; print('python  ', sys.version.split()[0]); print('numpy   ', numpy.__version__); print('gymnasium', gymnasium.__version__); print('mujoco  ', mujoco.__version__); print('sb3     ', stable_baselines3.__version__); print('torch   ', torch.__version__); print('cuda    ', torch.cuda.is_available())"
```

Фактический вывод на машине разработчика:

```text
python   3.12.3
numpy    2.0.2
gymnasium 1.0.0
mujoco   3.9.0
sb3      2.4.1
torch    2.6.0+cu124
cuda     True
```

`cuda False` — это нормально и на прохождение курса не влияет.

Проверка, что физика и среды действительно работают:

```bash
python -c "import mujoco; m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><body><geom size=\".1\"/><joint type=\"free\"/></body></worldbody></mujoco>'); d = mujoco.MjData(m); [mujoco.mj_step(m, d) for _ in range(100)]; print('mujoco ok, z =', round(float(d.qpos[2]), 4))"
python -c "import gymnasium as gym; e = gym.make('CartPole-v1'); o, _ = e.reset(seed=0); print('gym ok, obs', o.shape)"
```

Фактический вывод на машине разработчика:

```text
mujoco ok, z = -0.1982
gym ok, obs (4,)
```

Число ядер — от него зависит, сколько параллельных сред имеет смысл запускать:

```bash
python -c "import os; print('cpu', os.cpu_count())"
```

На машине разработчика: `cpu 24`.

---

## Что осталось за рамками этого файла

Честный список того, что **не проверялось** при подготовке SETUP.md:

* установка ROS 2 Jazzy, сборка `ros2_ws` и запуск Gazebo/Nav2/TurtleBot3 — на машине, где
  готовился этот файл, стоит только ROS 2 Humble в WSL2 (Ubuntu 22.04), целевой связки
  Jazzy + Ubuntu 24.04 нет; все команды дорожки ROS 2 приведены дословно из статей курса;
* Docker-вариант дорожки ROS 2 — в курсе не описан;
* установка `micro_ros_agent` и тулчейна ESP-IDF — в курсе не описана;
* размер установки на диске для `ros-jazzy-desktop`, Gazebo Harmonic, Nav2 и TurtleBot3 —
  не замерено (для WSL2 статья курса называет общий ориентир 20-30 GB);
* время обучения треков B и C урока 14 на типовом студенческом ноутбуке — не замерено;
  все приведённые цифры fps получены на машине с 24 ядрами.
