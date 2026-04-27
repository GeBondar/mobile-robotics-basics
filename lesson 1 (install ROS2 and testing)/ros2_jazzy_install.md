# Установка и проверка ROS 2 Jazzy на Ubuntu 24.04

Официальная инструкция: [ROS 2 Jazzy Installation Guide](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)

## Предварительные требования

- **Операционная система:** Ubuntu 24.04 (Noble Numbat)
- **Архитектура:** AMD64 (x86_64) или ARM64
- **Версия ROS:** Jazzy Jalisco
- **Языковая локаль:** Рекомендуется UTF-8

### Проверка и настройка локали

    # Проверить текущую локаль
    locale

    # Установить UTF-8 (если не установлена)
    sudo apt update && sudo apt install locales
    sudo locale-gen en_US en_US.UTF-8
    sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
    export LANG=en_US.UTF-8

## 1. Настройка репозиториев

### 1.1. Включить репозиторий Universe

    sudo apt install software-properties-common
    sudo add-apt-repository universe

### 1.2. Добавить ROS 2 GPG ключ

    sudo apt update && sudo apt install curl -y
    sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg

### 1.3. Добавить репозиторий ROS 2

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

## 📦 2. Установка ROS 2

### 2.1. Обновить список пакетов

    sudo apt update

### 2.2. Обновить существующие пакеты (рекомендуется)

    sudo apt upgrade -y

### 2.3. Установить ROS 2

**Выберите один из вариантов:**

**Минимальная установка** (ROS-база, компиляторы и инструменты):

    sudo apt install ros-jazzy-ros-base

**Полная установка** (включая GUI-инструменты, симуляторы):

    sudo apt install ros-jazzy-desktop

## ⚙️ 3. Настройка окружения

### 3.1. Установить дополнительные инструменты

    sudo apt install python3-colcon-common-extensions python3-rosdep

### 3.2. Инициализировать rosdep

    sudo rosdep init
    rosdep update

### 3.3. Настроить переменные окружения

Добавьте в файл `~/.bashrc` автоматическую настройку окружения:

    echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
    source ~/.bashrc

## 4. Проверка установки

### 4.1. Проверить переменные окружения ROS

    # Загрузить окружение ROS 2
    source /opt/ros/jazzy/setup.bash

    # Проверить переменные окружения
    printenv | grep ROS

Ожидаемый вывод:

    ROS_VERSION=2
    ROS_PYTHON_VERSION=3
    ROS_DISTRO=jazzy

Выполните все команды последовательно для быстрой проверки:

    # Проверка текущей версии (дистрибутива) ROS 2 
    echo $ROS_DISTRO

    # Список запущенных нод (должен быть пустым)
    ros2 node list

    # Список запущенных топиков (выведет 2 топика: /parameter_events и /rosout)
    ros2 topic list

## 🔧 5. Устранение неполадок

### Проблема: Команды ROS 2 не найдены

**Решение:**

    # Вручную загрузить окружение
    source /opt/ros/jazzy/setup.bash

    # Или добавьте эту команду в ~/.bashrc
    echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc

### Проблема: Ошибка с rosdep

**Решение:**

    # Повторить инициализацию
    sudo rosdep init
    rosdep update

    # Если проблема сохраняется, попробуйте:
    sudo rm -f /etc/ros/rosdep/sources.list.d/20-default.list
    sudo rosdep init
    rosdep update

### Проблема: Конфликт с другими версиями ROS

**Решение:** Убедитесь, что в `~/.bashrc` нет строк, загружающих другие версии ROS.

## 6. Дополнительные ресурсы

- [Официальная документация ROS 2 Jazzy](https://docs.ros.org/en/jazzy/)
- [Туториалы для начинающих](https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools.html)
- [Примеры пакетов ROS 2](https://github.com/ros2/examples)

**Примечание:** Данная инструкция предназначена для чистой установки на Ubuntu 24.04. Если у вас возникают проблемы, проверьте [официальную документацию](https://docs.ros.org/en/jazzy/Installation.html) или обратитесь к сообществу ROS.

После установки переходите к настройке окружения и проверке `ros2 doctor`.
