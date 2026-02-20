# **Создание своего Action для перемещения черепашки в ROS 2**

## 🎯 **Цель**
Создать собственный action в ROS 2, который позволит перемещать черепашку в симуляторе turtlesim в заданную точку. Вы научитесь описывать тип action, реализовывать action-сервер и action-клиент на Python, а также обрабатывать обратную связь (feedback) во время выполнения длительной задачи.

---

## 📋 **Что такое Actions в ROS2?**
Actions — это механизм взаимодействия, предназначенный для **длительных задач**, которые могут выполняться несколько секунд или минут. Они сочетают в себе свойства сервисов (запрос‑ответ) и топиков (обратная связь в реальном времени).  
- **Клиент** отправляет цель (goal).
- **Сервер** выполняет задачу и периодически шлёт **обратную связь** (feedback).
- По завершении сервер возвращает **результат** (result).
- Также можно **отменить** выполнение цели.

В этом туториале мы реализуем action `MoveTo`, который будет перемещать черепашку из текущего положения в заданную точку (x, y) с заданной скоростью, публикуя команды в `/turtle1/cmd_vel` и выдавая обратную связь о текущем положении и оставшемся расстоянии.

---

## 🚀 **Шаг 1: Создание рабочего пространства и пакета**

### **1.1 Создаём рабочее пространство (если ещё нет)**
```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
```

### **1.2 Создаём пакет с поддержкой actions**
Для работы с actions нам понадобятся зависимости: `rclpy`, `turtlesim`, `geometry_msgs`, а также инструменты для компиляции интерфейсов.

Создадим пакет типа `ament_cmake`, потому что для компиляции файлов `.action` проще использовать CMake, а Python-узлы разместим в подпапке. Альтернативно можно создать `ament_python` и добавить поддержку CMake, но мы выберем стандартный путь.

```bash
ros2 pkg create turtle_action \
  --build-type ament_cmake \
  --dependencies rclcpp rclpy rclcpp_action turtlesim geometry_msgs action_msgs
```

> Примечание: мы добавили и C++, и Python зависимости, но будем писать только на Python. Это не помешает.

### **1.3 Структура пакета**
Перейдите в пакет и создайте папки:
```bash
cd ~/ros2_ws/src/turtle_action
mkdir action scripts
```

Папка `action` будет содержать файлы описания действий, `scripts` — наши Python-узлы.

---

## 📄 **Шаг 2: Определение своего типа Action**

### **2.1 Создаём файл `MoveTo.action`**
```bash
touch action/MoveTo.action
```

### **2.2 Редактируем `action/MoveTo.action`**
Откройте файл и добавьте:
```text
# Запрос (goal)
float32 target_x
float32 target_y
float32 target_theta   # желаемая ориентация (опционально)
float32 speed          # линейная скорость
---
# Результат (result)
bool success           # удалось ли достичь цели
float32 final_distance # финальное расстояние до цели
---
# Обратная связь (feedback)
float32 current_x
float32 current_y
float32 current_theta
float32 distance_left  # оставшееся расстояние до цели
```
Структура: три секции, разделённые `---`. Первая — цель (goal), вторая — результат (result), третья — обратная связь (feedback).

### **2.3 Настройка CMakeLists.txt для компиляции action**
В `CMakeLists.txt` нужно добавить вызов `rosidl_generate_interfaces` для нашего action. Также необходимо найти пакеты, предоставляющие средства генерации.

Отредактируйте `CMakeLists.txt` примерно так:
```cmake
cmake_minimum_required(VERSION 3.8)
project(turtle_action)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclpy REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(turtlesim REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(action_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

# Генерация интерфейсов (action)
rosidl_generate_interfaces(${PROJECT_NAME}
  "action/MoveTo.action"
  DEPENDENCIES geometry_msgs turtlesim action_msgs
)

# Установка Python-скриптов
install(PROGRAMS
  scripts/action_server.py
  scripts/action_client.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
```

### **2.4 Настройка package.xml**
Убедитесь, что в `package.xml` есть следующие строки:
```xml
<depend>rclcpp</depend>
<depend>rclpy</depend>
<depend>rclcpp_action</depend>
<depend>turtlesim</depend>
<depend>geometry_msgs</depend>
<depend>action_msgs</depend>
<depend>rosidl_default_generators</depend>
<exec_depend>rosidl_default_runtime</exec_depend>
<member_of_group>rosidl_interface_packages</member_of_group>
```

---

## 🐍 **Шаг 3: Написание action-сервера**

Сервер будет подписываться на топик `/turtle1/pose`, чтобы знать текущее положение черепашки. При получении цели он начнёт публиковать команды скорости в `/turtle1/cmd_vel` для движения к цели, периодически отправляя feedback.

### **3.1 Создаём файл `action_server.py`**
```bash
cd ~/ros2_ws/src/turtle_action/scripts
touch action_server.py
chmod +x action_server.py
```

### **3.2 Код сервера**
```python
#!/usr/bin/env python3
"""
Action-сервер для перемещения черепашки в заданную точку.
Подписывается на /turtle1/pose, публикует в /turtle1/cmd_vel.
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.action.server import ServerGoalHandle
from geometry_msgs.msg import Twist
from turtlesim.msg import Pose
from turtle_action.action import MoveTo  # сгенерированный тип action

import math
import time

class MoveToActionServer(Node):
    def __init__(self):
        super().__init__('move_to_action_server')
        
        # Подписка на текущее положение черепашки
        self.pose_sub = self.create_subscription(Pose, '/turtle1/pose', self.pose_callback, 10)
        self.current_pose = None

        # Издатель команд скорости
        self.cmd_pub = self.create_publisher(Twist, '/turtle1/cmd_vel', 10)

        # Создание action-сервера
        self._action_server = ActionServer(
            self,
            MoveTo,
            'move_to',
            self.execute_callback,
            cancel_callback=self.cancel_callback  # опционально
        )

        self.get_logger().info('Action-сервер готов к работе.')

    def pose_callback(self, msg):
        """Сохраняем последнее положение"""
        self.current_pose = msg

    def execute_callback(self, goal_handle: ServerGoalHandle):
        """Основная логика выполнения цели"""
        self.get_logger().info('Получена новая цель: x={:.2f}, y={:.2f}, theta={:.2f}, speed={:.2f}'.format(
            goal_handle.request.target_x,
            goal_handle.request.target_y,
            goal_handle.request.target_theta,
            goal_handle.request.speed
        ))

        # Параметры движения
        target_x = goal_handle.request.target_x
        target_y = goal_handle.request.target_y
        target_theta = goal_handle.request.target_theta
        speed = goal_handle.request.speed
        # Порог близости (когда считаем, что цель достигнута)
        distance_tolerance = 0.1
        angle_tolerance = 0.05

        # Частота отправки feedback (раз в секунду)
        feedback_period = 0.5  # сек
        last_feedback_time = self.get_clock().now().nanoseconds / 1e9

        # Пока цель активна и не запрошена отмена
        while rclpy.ok() and goal_handle.is_active:
            # Проверяем, не было ли запроса отмены
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                self.get_logger().info('Цель отменена.')
                return MoveTo.Result(success=False, final_distance=-1.0)

            # Ждём, пока появится первая позиция
            if self.current_pose is None:
                time.sleep(0.1)
                continue

            # Вычисляем расстояние и угол до цели
            dx = target_x - self.current_pose.x
            dy = target_y - self.current_pose.y
            distance = math.sqrt(dx*dx + dy*dy)
            angle_to_target = math.atan2(dy, dx)

            # Вычисляем разницу углов (с учётом направления черепашки)
            angle_diff = self.normalize_angle(angle_to_target - self.current_pose.theta)

            # Публикуем команду скорости (простой регулятор)
            cmd = Twist()
            if distance > distance_tolerance:
                # Если далеко, едем вперёд и поворачиваем
                cmd.linear.x = min(speed, distance)  # не быстрее speed
                cmd.angular.z = 2.0 * angle_diff
            else:
                # Если близко, останавливаемся и корректируем угол
                cmd.linear.x = 0.0
                # Доворот до целевого угла
                angle_diff_final = self.normalize_angle(target_theta - self.current_pose.theta)
                if abs(angle_diff_final) > angle_tolerance:
                    cmd.angular.z = 1.5 * angle_diff_final
                else:
                    cmd.angular.z = 0.0
                    # Цель полностью достигнута
                    self.get_logger().info('Цель достигнута!')
                    break

            self.cmd_pub.publish(cmd)

            # Отправляем feedback с определённой периодичностью
            now = self.get_clock().now().nanoseconds / 1e9
            if now - last_feedback_time >= feedback_period:
                feedback_msg = MoveTo.Feedback()
                feedback_msg.current_x = self.current_pose.x
                feedback_msg.current_y = self.current_pose.y
                feedback_msg.current_theta = self.current_pose.theta
                feedback_msg.distance_left = distance
                goal_handle.publish_feedback(feedback_msg)
                last_feedback_time = now

            # Небольшая пауза, чтобы не загружать процессор
            time.sleep(0.05)

        # Останавливаем черепашку
        self.cmd_pub.publish(Twist())

        if goal_handle.is_active:
            goal_handle.succeed()

        # Формируем результат
        result = MoveTo.Result()
        result.success = True
        result.final_distance = distance if self.current_pose else -1.0
        return result

    def cancel_callback(self, goal_handle):
        """Обработчик отмены цели (можно просто принять отмену)"""
        self.get_logger().info('Получен запрос на отмену цели.')
        # Можно выполнить дополнительные действия (остановить движение)
        self.cmd_pub.publish(Twist())  # остановка
        return rclpy.action.CancelResponse.ACCEPT

    @staticmethod
    def normalize_angle(angle):
        """Приводит угол в диапазон [-pi, pi]"""
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

def main(args=None):
    rclpy.init(args=args)
    node = MoveToActionServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Остановка сервера')
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

### **3.3 Пояснения**
- В `execute_callback` мы реализуем цикл движения, который работает, пока цель активна.
- Используем простой пропорциональный регулятор для поворота к цели и движения вперёд.
- Feedback отправляется каждые 0.5 секунды.
- Предусмотрена обработка отмены цели (cancel).
- После достижения цели черепашка останавливается.

---

## 🐍 **Шаг 4: Написание action-клиента**

Клиент будет отправлять цель и выводить feedback и результат.

### **4.1 Создаём файл `action_client.py`**
```bash
touch action_client.py
chmod +x action_client.py
```

### **4.2 Код клиента**
```python
#!/usr/bin/env python3
"""
Action-клиент для перемещения черепашки.
Принимает координаты цели из командной строки.
"""

import sys
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from turtle_action.action import MoveTo

class MoveToActionClient(Node):
    def __init__(self):
        super().__init__('move_to_action_client')
        self._action_client = ActionClient(self, MoveTo, 'move_to')

    def send_goal(self, target_x, target_y, target_theta, speed):
        goal_msg = MoveTo.Goal()
        goal_msg.target_x = target_x
        goal_msg.target_y = target_y
        goal_msg.target_theta = target_theta
        goal_msg.speed = speed

        self.get_logger().info('Отправляем цель...')

        # Ждём, пока action-сервер станет доступен
        self._action_client.wait_for_server()

        # Отправляем цель
        self._send_goal_future = self._action_client.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback
        )
        self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Цель отклонена сервером')
            return

        self.get_logger().info('Цель принята, ждём результат...')
        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        self.get_logger().info('Результат: success={}, final_distance={:.2f}'.format(
            result.success, result.final_distance))
        rclpy.shutdown()

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        self.get_logger().info('Текущая позиция: x={:.2f}, y={:.2f}, theta={:.2f}, осталось {:.2f} м'.format(
            feedback.current_x, feedback.current_y, feedback.current_theta, feedback.distance_left))

def main(args=None):
    rclpy.init(args=args)

    # Разбираем аргументы командной строки
    if len(sys.argv) != 5:
        print("Использование: action_client.py <target_x> <target_y> <target_theta> <speed>")
        print("Пример: action_client.py 8.0 2.0 1.57 1.0")
        return

    target_x = float(sys.argv[1])
    target_y = float(sys.argv[2])
    target_theta = float(sys.argv[3])
    speed = float(sys.argv[4])

    client = MoveToActionClient()
    client.send_goal(target_x, target_y, target_theta, speed)

    # Запускаем spin, чтобы обрабатывать callback'и
    rclpy.spin(client)

if __name__ == '__main__':
    main()
```

### **4.3 Пояснения**
- Клиент использует `ActionClient`.
- При отправке цели регистрируется callback для получения feedback.
- После получения результата программа завершается.

---

## 📦 **Шаг 5: Настройка entry points и сборка**

Мы уже установили скрипты в `CMakeLists.txt` через `install(PROGRAMS ...)`, поэтому не требуется добавлять их в `setup.py` (пакет `ament_cmake`). Но для удобства запуска через `ros2 run` нужно убедиться, что скрипты установлены в `lib/${PROJECT_NAME}`.

Выполним сборку:

```bash
cd ~/ros2_ws
colcon build --packages-select turtle_action
source install/setup.bash
```

---

## 🔨 **Шаг 6: Запуск и проверка**

### **6.1 Запускаем turtlesim (терминал №1)**
```bash
ros2 run turtlesim turtlesim_node
```

### **6.2 Запускаем action-сервер (терминал №2)**
```bash
source ~/ros2_ws/install/setup.bash
ros2 run turtle_action action_server.py
```
Должно появиться сообщение: `Action-сервер готов к работе.`

### **6.3 Запускаем action-клиента (терминал №3)**
Например, переместим черепашку в точку (8.0, 2.0) с целевым углом 1.57 радиан (90°) и скоростью 1.0:
```bash
source ~/ros2_ws/install/setup.bash
ros2 run turtle_action action_client.py 8.0 2.0 1.57 1.0
```

Вы увидите, как черепашка поворачивается и движется к цели, а клиент выводит обратную связь. По достижении цели клиент выведет результат и завершится.

### **6.4 Проверка списка действий**
```bash
ros2 action list
```
Должен быть `/move_to`.

### **6.5 Информация о типе действия**
```bash
ros2 action info /move_to
ros2 action show turtle_action/action/MoveTo
```

### **6.6 Отмена цели (попробуйте прервать выполнение)**
Если во время движения нажать **Ctrl+C** на клиенте, цель не отменяется автоматически. Чтобы отменить, нужно добавить логику обработки сигналов или запустить клиент и быстро прервать его. Но наш сервер поддерживает отмену, и если клиент пошлёт запрос на отмену, она сработает. Для теста можно запустить клиент, а в другом терминале выполнить:
```bash
ros2 action send_goal /move_to turtle_action/action/MoveTo "{target_x: 5.0, target_y: 5.0, target_theta: 0.0, speed: 1.0}" --feedback
```
Затем в другом терминале отменить:
```bash
ros2 action cancel /move_to
```
Это продемонстрирует обработку отмены сервером.

---

## 🎮 **Шаг 7: Дополнительные упражнения**

### **Упражнение 1: Параметры движения**
Добавьте в goal поле `linear_tolerance` и `angular_tolerance`, чтобы можно было задавать точность достижения цели. Используйте их в сервере.

### **Упражнение 2: Движение по ломаной**
Модифицируйте action так, чтобы можно было передавать список точек (например, через массив). Черепашка должна последовательно посетить все точки.

### **Упражнение 3: Интеграция с сервисом**
Добавьте в сервер сервис для остановки текущего движения (например, `StopMoving.srv`). При вызове сервиса текущая цель должна отменяться.

### **Упражнение 4: Обработка коллизий**
Используйте данные о положении, чтобы предотвращать выход за границы окна (0–11). Если цель вне допустимой области, отклоняйте goal с соответствующим результатом.

---

## 🧹 **Шаг 8: Очистка**
Не забудьте остановить все узлы нажатием **Ctrl+C** в каждом терминале.

---

## 📚 **Ключевые концепции, которые вы освоили**

✅ **Создание собственного типа action (файл .action)**  
✅ **Генерация кода action при сборке**  
✅ **Реализация action-сервера с долгой задачей и обратной связью**  
✅ **Реализация action-клиента с обработкой feedback и result**  
✅ **Обработка отмены цели**  
✅ **Использование топиков и публикации внутри action-сервера**  
✅ **Запуск и отладка actions в ROS 2**

---

## 🔜 **Что дальше?**

1. **Изучение более сложных паттернов управления** с использованием библиотек типа `nav2`.
2. **Создание action для управления группой роботов.**
3. **Использование действий для планирования движения (move_base) в ROS2 Navigation.**
4. **Интеграция actions с параметрами и сервисами в больших проектах.**