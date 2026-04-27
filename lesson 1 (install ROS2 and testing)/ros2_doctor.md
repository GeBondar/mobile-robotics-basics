# Диагностика установки через ros2doctor

Цель: использовать `ros2 doctor` для быстрой проверки окружения ROS 2 и работающей системы.

Официальный источник: <https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Getting-Started-With-Ros2doctor.html>

## 1. Проверка установки

Откройте новый терминал:

```bash
source /opt/ros/jazzy/setup.bash
ros2 doctor
```

Если установка в порядке, команда завершится без критических ошибок. Предупреждения не всегда означают неисправность, но их нужно прочитать.

Полный отчёт:

```bash
ros2 doctor --report
```

Сохранение отчёта:

```bash
ros2 doctor --report > ros2_doctor_report.txt
```

## 2. Проверка работающей системы

Терминал 1:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run turtlesim turtlesim_node
```

Терминал 2:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run turtlesim turtle_teleop_key
```

Терминал 3:

```bash
source /opt/ros/jazzy/setup.bash
ros2 doctor
```

`ros2doctor` проверит не только установку, но и активный ROS 2 graph.

## 3. Что проверять в отчёте

Обратите внимание на блоки:

- platform information;
- ROS distro;
- environment variables;
- network configuration;
- RMW middleware;
- topic/service/action graph.

## 4. Типовые проблемы

### ROS_DISTRO пустой

Причина: не подключён setup-файл.

```bash
source /opt/ros/jazzy/setup.bash
echo $ROS_DISTRO
```

### Команда ros2 не найдена

Проверьте установку:

```bash
ls /opt/ros
```

Если каталога `jazzy` нет, ROS 2 Jazzy не установлен.

### Ноды не видят друг друга

Проверьте `ROS_DOMAIN_ID` во всех терминалах:

```bash
echo $ROS_DOMAIN_ID
```

Значение должно совпадать.

## Контрольная проверка

```bash
ros2 doctor
ros2 doctor --report | grep -i distro
```

Ожидаемый дистрибутив для основной версии курса: `jazzy`.
