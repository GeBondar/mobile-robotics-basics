# Урок 1. Установка, окружение и базовые инструменты

Цель урока - подготовить рабочую среду ROS 2 Jazzy, проверить установку и освоить первые инструменты командной строки и графической отладки.

Основная платформа курса: Ubuntu 24.04 + ROS 2 Jazzy. Humble на Ubuntu 22.04 оставлен как совместимый вариант для машин, где Jazzy пока недоступен.

## Порядок прохождения

| Шаг | Статья | Результат |
|---:|---|---|
| 1 | [Установка ROS 2 Jazzy на Ubuntu 24.04](ros2_jazzy_install.md) | ROS 2 установлен из deb-пакетов |
| 2 | [Windows + WSL2: локальная VM для ROS 2 Jazzy](windows_wsl2_jazzy_install.md) | На Windows создана Ubuntu 24.04 среда для курса |
| 3 | [Настройка окружения ROS 2](ros2_environment.md) | Понятны underlay, overlay и `source` |
| 4 | [Проверка установки через ros2doctor](ros2_doctor.md) | Установка проверена диагностическим инструментом |
| 5 | [Проверочная демонстрация](ros2_testing.md) | Проверен обмен сообщениями demo-ноды |
| 6 | [turtlesim, ros2 CLI и первые эксперименты](ros2_turtlesim.md) | Запущена симуляция, изучены ноды, топики, сервисы |
| 7 | [rqt](ros2_rqt.md) | Освоены базовые графические инструменты |
| 8 | [rqt_console и уровни логирования](rqt_console.md) | Логи ROS 2 просмотрены и отфильтрованы |
| 9 | [Установка ROS 2 Humble](ros2_humble_install.md) | Альтернативная установка для Ubuntu 22.04 |

## Контрольные команды

```bash
echo $ROS_DISTRO
ros2 --help
ros2 doctor
ros2 run demo_nodes_cpp talker
ros2 run demo_nodes_py listener
```

## После урока

Переходите к [уроку 2](<../lesson 2 (nodes and topics)/README.md>): workspace, ноды, топики, запись данных и первые собственные Python-пакеты.
