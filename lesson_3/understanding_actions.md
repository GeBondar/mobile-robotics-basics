# Понимание действий в ROS 2

**Цель:** Изучить действия (actions) в ROS 2.

## Содержание
- [Введение](#введение)
- [Предварительные требования](#предварительные-требования)
- [Задачи](#задачи)
  1. [Настройка](#1-настройка)
  2. [Использование действий](#2-использование-действий)
  3. [ros2 node info](#3-ros2-node-info)
  4. [ros2 action list](#4-ros2-action-list)
  5. [ros2 action type](#5-ros2-action-type)
  6. [ros2 action info](#6-ros2-action-info)
  7. [ros2 interface show](#7-ros2-interface-show)
  8. [ros2 action send_goal](#8-ros2-action-send_goal)
- [Резюме](#резюме)
- [Следующие шаги](#следующие-шаги)
- [Дополнительные материалы](#дополнительные-материалы)

## Введение

Действия (actions) — это один из типов коммуникации в ROS 2, предназначенный для выполнения длительных задач. Они состоят из трёх частей: **цель (goal)**, **обратная связь (feedback)** и **результат (result)**.

Действия построены на основе тем (topics) и сервисов (services). Их функциональность похожа на сервисы, но действия можно отменять. Кроме того, они предоставляют постоянную обратную связь в процессе выполнения, в отличие от сервисов, которые возвращают только один ответ.

Действия используют модель клиент-сервер, аналогичную модели издатель-подписчик (publisher-subscriber). Узел-клиент действия (action client) отправляет цель узлу-серверу действия (action server), который подтверждает цель и возвращает поток сообщений обратной связи и результат.

![Модель действия](images/Action-SingleActionClient.gif)

## Предварительные требования

Этот урок опирается на концепции, такие как узлы (nodes) и темы (topics), рассмотренные в предыдущих уроках.

В этом уроке используется пакет `turtlesim`.

Как всегда, не забывайте sourceить ROS 2 в каждом новом терминале:

```bash
source /opt/ros/<ваша_версия>/setup.bash
```

## Задачи

### 1. Настройка

Запустите два узла `turtlesim`: `/turtlesim` и `/teleop_turtle`.

Откройте новый терминал и выполните:

```bash
ros2 run turtlesim turtlesim_node
```

Откройте другой терминал и выполните:

```bash
ros2 run turtlesim turtle_teleop_key
```

### 2. Использование действий

При запуске узла `/teleop_turtle` вы увидите следующее сообщение в терминале:

```
Use arrow keys to move the turtle.
Use G|B|V|C|D|E|R|T keys to rotate to absolute orientations. 'F' to cancel a rotation.
```

Сосредоточимся на второй строке, которая соответствует действию. (Первая инструкция относится к теме `cmd_vel`, обсуждавшейся ранее в уроке по темам.)

Обратите внимание, что клавиши `G|B|V|C|D|E|R|T` образуют «рамку» вокруг клавиши `F` на клавиатуре US QWERTY. Каждая клавиша соответствует определённой ориентации в turtlesim. Например, `E` повернёт черепаху в верхний левый угол.

Обратите внимание на терминал, где запущен узел `/turtlesim`. Каждый раз, когда вы нажимаете одну из этих клавиш, вы отправляете цель серверу действия, который является частью узла `/turtlesim`. Цель состоит в том, чтобы повернуть черепаху в заданном направлении. После завершения поворота должно отобразиться сообщение с результатом:

```
[INFO] [turtlesim]: Rotation goal completed successfully
```

Клавиша `F` отменяет выполняющуюся цель.

Попробуйте нажать `C`, а затем `F` до завершения поворота. В терминале с узлом `/turtlesim` вы увидите сообщение:

```
[INFO] [turtlesim]: Rotation goal canceled
```

Не только клиент может остановить цель — сервер также может прервать её выполнение. Когда сервер решает прекратить обработку цели, говорят, что он «прерывает» (abort) цель.

Попробуйте нажать `D`, а затем `G` до завершения первого поворота. Вы увидите предупреждение:

```
[WARN] [turtlesim]: Rotation goal received before a previous goal finished. Aborting previous goal
```

Этот сервер действия решил прервать первую цель, потому что получил новую. Он мог бы выбрать другое поведение (например, отклонить новую цель или выполнить её после завершения первой). Не предполагайте, что каждый сервер действий будет прерывать текущую цель при получении новой.

### 3. ros2 node info

Чтобы увидеть список действий, которые предоставляет узел (в данном случае `/turtlesim`), откройте новый терминал и выполните команду:

```bash
ros2 node info /turtlesim
```

Вывод будет содержать информацию о подписчиках, издателях, сервисах, серверах действий и клиентах действий:

```
/turtlesim
  Subscribers:
    /parameter_events: rcl_interfaces/msg/ParameterEvent
    /turtle1/cmd_vel: geometry_msgs/msg/Twist
  Publishers:
    /parameter_events: rcl_interfaces/msg/ParameterEvent
    /rosout: rcl_interfaces/msg/Log
    /turtle1/color_sensor: turtlesim/msg/Color
    /turtle1/pose: turtlesim/msg/Pose
  Service Servers:
    /clear: std_srvs/srv/Empty
    /kill: turtlesim/srv/Kill
    /reset: std_srvs/srv/Empty
    /spawn: turtlesim/srv/Spawn
    /turtle1/set_pen: turtlesim/srv/SetPen
    /turtle1/teleport_absolute: turtlesim/srv/TeleportAbsolute
    /turtle1/teleport_relative: turtlesim/srv/TeleportRelative
    /turtlesim/describe_parameters: rcl_interfaces/srv/DescribeParameters
    /turtlesim/get_parameter_types: rcl_interfaces/srv/GetParameterTypes
    /turtlesim/get_parameters: rcl_interfaces/srv/GetParameters
    /turtlesim/list_parameters: rcl_interfaces/srv/ListParameters
    /turtlesim/set_parameters: rcl_interfaces/srv/SetParameters
    /turtlesim/set_parameters_atomically: rcl_interfaces/srv/SetParametersAtomically
  Service Clients:

  Action Servers:
    /turtle1/rotate_absolute: turtlesim/action/RotateAbsolute
  Action Clients:
```

Обратите внимание, что `/turtle1/rotate_absolute` находится в разделе **Action Servers**. Это означает, что узел `/turtlesim` отвечает на это действие и предоставляет обратную связь.

Узел `/teleop_turtle` имеет имя `/turtle1/rotate_absolute` в разделе **Action Clients**, что означает, что он отправляет цели для этого действия. Чтобы убедиться в этом, выполните:

```bash
ros2 node info /teleop_turtle
```

```
/teleop_turtle
  Subscribers:
    /parameter_events: rcl_interfaces/msg/ParameterEvent
  Publishers:
    /parameter_events: rcl_interfaces/msg/ParameterEvent
    /rosout: rcl_interfaces/msg/Log
    /turtle1/cmd_vel: geometry_msgs/msg/Twist
  Service Servers:
    /teleop_turtle/describe_parameters: rcl_interfaces/srv/DescribeParameters
    /teleop_turtle/get_parameter_types: rcl_interfaces/srv/GetParameterTypes
    /teleop_turtle/get_parameters: rcl_interfaces/srv/GetParameters
    /teleop_turtle/list_parameters: rcl_interfaces/srv/ListParameters
    /teleop_turtle/set_parameters: rcl_interfaces/srv/SetParameters
    /teleop_turtle/set_parameters_atomically: rcl_interfaces/srv/SetParametersAtomically
  Service Clients:

  Action Servers:

  Action Clients:
    /turtle1/rotate_absolute: turtlesim/action/RotateAbsolute
```

### 4. ros2 action list

Чтобы увидеть все действия в графе ROS, выполните команду:

```bash
ros2 action list
```

```
/turtle1/rotate_absolute
```

Это единственное действие в текущем графе ROS. Оно управляет поворотом черепахи, как вы уже видели. Из предыдущего шага мы знаем, что для этого действия есть один клиент (в узле `/teleop_turtle`) и один сервер (в узле `/turtlesim`).

#### 4.1 ros2 action list -t

Действия имеют типы, аналогично темам и сервисам. Чтобы узнать тип действия `/turtle1/rotate_absolute`, выполните:

```bash
ros2 action list -t
```

```
/turtle1/rotate_absolute [turtlesim/action/RotateAbsolute]
```

В квадратных скобках указан тип действия: `turtlesim/action/RotateAbsolute`. Эта информация понадобится для отправки цели из командной строки или из кода.

### 5. ros2 action type

Если нужно проверить тип конкретного действия, используйте команду:

```bash
ros2 action type /turtle1/rotate_absolute
```

```
turtlesim/action/RotateAbsolute
```

### 6. ros2 action info

Для получения дополнительной информации о действии выполните:

```bash
ros2 action info /turtle1/rotate_absolute
```

```
Action: /turtle1/rotate_absolute
Action clients: 1
    /teleop_turtle
Action servers: 1
    /turtlesim
```

Это подтверждает, что узел `/teleop_turtle` является клиентом, а `/turtlesim` — сервером для данного действия.

### 7. ros2 interface show

Прежде чем отправлять цель, полезно знать структуру типа действия. Выполните команду с указанием типа:

```bash
ros2 interface show turtlesim/action/RotateAbsolute
```

Результат:

```
# The desired heading in radians
float32 theta
---
# The angular displacement in radians to the starting position
float32 delta
---
# The remaining rotation in radians
float32 remaining
```

Раздел над первой чертой `---` описывает структуру запроса цели (goal request). Следующий раздел — структура результата (result). Последний раздел — структура обратной связи (feedback).

### 8. ros2 action send_goal

Теперь отправим цель действия из командной строки. Синтаксис команды:

```bash
ros2 action send_goal <имя_действия> <тип_действия> <значения>
```

Значения должны быть в формате YAML.

Следите за окном `turtlesim` и выполните:

```bash
ros2 action send_goal /turtle1/rotate_absolute turtlesim/action/RotateAbsolute "{theta: 1.57}"
```

Вы увидите примерно такой вывод:

```
Waiting for an action server to become available...
Sending goal:
   theta: 1.57

Goal accepted with ID: f8db8f44410849eaa93d3feb747dd444

Result:
  delta: -1.568000316619873

Goal finished with status: SUCCEEDED
```

Черепаха должна повернуться. У каждой цели есть уникальный идентификатор (ID), показанный в ответе. Также выводится результат — поле `delta`, которое показывает угловое смещение относительно начальной позиции.

Чтобы увидеть обратную связь в процессе выполнения, добавьте флаг `--feedback`:

```bash
ros2 action send_goal /turtle1/rotate_absolute turtlesim/action/RotateAbsolute "{theta: -1.57}" --feedback
```

```
Sending goal:
   theta: -1.57

Goal accepted with ID: e6092c831f994afda92f0086f220da27

Feedback:
  remaining: -3.1268222332000732

Feedback:
  remaining: -3.1108222007751465

…

Result:
  delta: 3.1200008392333984

Goal finished with status: SUCCEEDED
```

Вы будете получать сообщения обратной связи (поле `remaining` — оставшийся угол в радианах) до тех пор, пока цель не будет достигнута.

## Резюме

Действия похожи на сервисы, но позволяют выполнять длительные задачи, предоставлять регулярную обратную связь и могут быть отменены. Робототехническая система, скорее всего, будет использовать действия для навигации: цель может указывать роботу переместиться в определённую позицию; во время движения робот отправляет обновления (обратную связь), а по прибытии — финальный результат.

В пакете `turtlesim` есть сервер действий, которому клиенты могут отправлять цели для поворота черепахи. В этом уроке вы изучили действие `/turtle1/rotate_absolute`, чтобы лучше понять, что такое действия и как они работают.

## Следующие шаги

Теперь вы ознакомились со всеми основными концепциями ROS 2. Следующие уроки познакомят вас с инструментами и методами, упрощающими использование ROS 2, начиная с **Использования rqt_console для просмотра логов**.

## Дополнительные материалы

* Официальная документация ROS 2: [Understanding actions](https://docs.ros.org/en/rolling/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Actions/Understanding-ROS2-Actions.html) (на английском)