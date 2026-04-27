# Windows + WSL2: локальная среда для ROS 2 Jazzy

Цель: подготовить на Windows локальную Linux-среду Ubuntu 24.04 для прохождения курса ROS 2 Jazzy.

WSL2 используется как основной вариант для Windows: это лёгкая виртуализированная Linux-среда, хорошо подходящая для командной разработки ROS 2. Для тяжёлой 3D-графики, нестандартных USB-устройств или сетевых экспериментов можно использовать полноценную VM в VirtualBox/VMware, но команды установки ROS 2 внутри Ubuntu остаются теми же.

Официальные источники:

- WSL: <https://learn.microsoft.com/en-us/windows/wsl/install>
- ROS 2 Jazzy Ubuntu install: <https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html>

## Требования

- Windows 10/11 с включённой виртуализацией в BIOS/UEFI.
- Доступ администратора для установки WSL.
- 20-30 GB свободного места.
- Для RViz2 и `turtlesim` с GUI предпочтительна Windows 11 с WSLg.

## 1. Установка WSL2 и Ubuntu 24.04

Откройте PowerShell от имени администратора.

Проверьте доступные дистрибутивы:

```powershell
wsl --list --online
```

Установите Ubuntu 24.04:

```powershell
wsl --install -d Ubuntu-24.04
```

Если WSL уже установлен, но Ubuntu 24.04 ещё нет:

```powershell
wsl --install -d Ubuntu-24.04
```

После установки перезагрузите Windows, если установщик попросил это сделать. Затем откройте Ubuntu 24.04 из меню Start или через Windows Terminal.

Проверьте версию Ubuntu:

```bash
lsb_release -a
```

Ожидаемый результат: `Ubuntu 24.04 LTS`.

## 2. Обновление Ubuntu

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y curl gnupg lsb-release software-properties-common
```

Проверьте locale:

```bash
locale
```

Если UTF-8 locale не настроена:

```bash
sudo apt install -y locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
```

## 3. Установка ROS 2 Jazzy

Включите репозиторий `universe`:

```bash
sudo add-apt-repository universe
sudo apt update
```

Установите пакет, который добавляет apt-источник ROS 2:

```bash
sudo apt install -y curl
export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F'"' '{print $4}')
curl -L -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo ${UBUNTU_CODENAME:-${VERSION_CODENAME}})_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb
```

Установите desktop-вариант ROS 2 Jazzy:

```bash
sudo apt update
sudo apt install -y ros-jazzy-desktop ros-dev-tools
```

## 4. Настройка окружения

Подключите ROS 2 в текущем терминале:

```bash
source /opt/ros/jazzy/setup.bash
echo $ROS_DISTRO
```

Ожидаемый результат:

```text
jazzy
```

Добавьте подключение в `~/.bashrc`:

```bash
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
```

## 5. Проверка CLI

Терминал 1:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run demo_nodes_cpp talker
```

Терминал 2:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run demo_nodes_py listener
```

Ожидаемый результат: listener получает сообщения от talker.

## 6. Проверка GUI

Проверьте `turtlesim`:

```bash
sudo apt install -y ros-jazzy-turtlesim
ros2 run turtlesim turtlesim_node
```

Если окно не открывается:

```bash
echo $DISPLAY
echo $WAYLAND_DISPLAY
```

На Windows 11 с WSLg переменные обычно настроены автоматически. На Windows 10 может понадобиться внешний X-сервер или полноценная VM Ubuntu 24.04.

## 7. Workspace курса

В Ubuntu перейдите в каталог репозитория. Для репозитория, лежащего в Windows, путь обычно начинается с `/mnt/c/...`.

Пример:

```bash
cd /mnt/c/Users/George/Documents/GitHub/mobile-robotics-basics/ros2_ws
rosdep install -i --from-path src --rosdistro jazzy -y
colcon build --symlink-install
source install/setup.bash
```

Для максимальной скорости сборки можно хранить рабочую копию внутри Linux-файловой системы, например в `~/mobile-robotics-basics`.

## Контрольный список

- `lsb_release -a` показывает Ubuntu 24.04.
- `echo $ROS_DISTRO` показывает `jazzy`.
- `ros2 doctor` запускается.
- `ros2 run demo_nodes_cpp talker` и `ros2 run demo_nodes_py listener` обмениваются сообщениями.
- `ros2 run turtlesim turtlesim_node` открывает окно или понятна причина, почему GUI недоступен.
