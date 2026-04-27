# Использование rqt в ROS 2

Цель: познакомиться с `rqt` и вызвать сервисы `turtlesim` через графический интерфейс.

## Что такое rqt

`rqt` — это графический фреймворк ROS 2 с набором плагинов для просмотра графа нод, топиков, сервисов, параметров и логов.

## Установка

Для ROS 2 Jazzy:

```bash
sudo apt update
sudo apt install '~nros-jazzy-rqt*'
```

Для Humble команда отличается только именем дистрибутива:

```bash
sudo apt install '~nros-humble-rqt*'
```

## Запуск

```bash
source /opt/ros/jazzy/setup.bash
rqt
```

Если список плагинов пустой, закройте окно и запустите повторное обнаружение:

```bash
rqt --force-discover
```

## Демонстрация с turtlesim

В первом терминале:

```bash
ros2 run turtlesim turtlesim_node
```

Во втором терминале:

```bash
ros2 run turtlesim turtle_teleop_key
```

Откройте `rqt` и выберите `Plugins -> Services -> Service Caller`.

## Создание второй черепахи

1. Нажмите `Refresh`.
2. Выберите сервис `/spawn`.
3. Заполните поля:
   - `name`: `turtle2`
   - `x`: `1.0`
   - `y`: `1.0`
   - `theta`: `0.0`
4. Нажмите `Call`.

В окне `turtlesim` должна появиться вторая черепаха.

## Изменение пера

В `Service Caller` выберите `/turtle1/set_pen` и задайте:

- `r`: `255`
- `g`: `0`
- `b`: `0`
- `width`: `5`
- `off`: `0`

После вызова сервиса первая черепаха будет рисовать красной линией.

## Полезные плагины

- `Node Graph` — граф нод и связей.
- `Topic Monitor` — просмотр сообщений в топиках.
- `Plot` — графики числовых данных.
- `Console` — логи ROS 2.
- `Service Caller` — ручной вызов сервисов.

## Практика

1. Создайте `turtle3` через `/spawn`.
2. Измените цвет пера у `turtle2`.
3. Откройте `Node Graph` и сравните его с выводом `ros2 node list` и `ros2 topic list`.
