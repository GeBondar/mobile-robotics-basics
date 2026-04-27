# Создание publisher для управления turtlesim в ROS 2

## Цель
Создать ноду-publisher на Python, которая публикует команды движения в топик `/turtle1/cmd_vel` для управления черепахой в turtlesim.

---

## Что мы будем делать
1. Создадим свой ROS 2 пакет
2. Напишем ноду-publisher на Python
3. Реализуем различные паттерны движения:
   - Движение по кругу
   - Движение по квадрату
   - Спираль
   - Случайное блуждание

---

## Шаг 1: Создание рабочего пространства и пакета

### **1.1 Создаём рабочее пространство (если ещё нет)**
```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
```

### **1.2 Создаём Python пакет**
```bash
ros2 pkg create my_turtle_controller \
  --build-type ament_python \
  --dependencies rclpy geometry_msgs turtlesim
```

### **1.3 Переходим в директорию пакета**
```bash
cd ~/ros2_ws/src/my_turtle_controller/my_turtle_controller
```

---

## Шаг 2: Создание ноды-publisher

### **2.1 Создаём файл с нодой**
```bash
touch turtle_publisher.py
chmod +x turtle_publisher.py
```

### **2.2 Открываем файл для редактирования**
```bash
nano turtle_publisher.py
```

### **2.3 Код ноды-publisher (полная версия)**
```python
#!/usr/bin/env python3
"""
Нода-publisher для управления черепахой в turtlesim.
Поддерживает несколько режимов движения.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import math
import random
import time

class TurtlePublisher(Node):
    def __init__(self):
        super().__init__('turtle_publisher')
        
        # Создаём издателя для топика /turtle1/cmd_vel
        self.publisher = self.create_publisher(Twist, '/turtle1/cmd_vel', 10)
        
        # Таймер для публикации сообщений каждые 0.1 секунды
        timer_period = 0.1  # секунды
        self.timer = self.create_timer(timer_period, self.timer_callback)
        
        # Выбираем режим движения
        self.mode = 'circle'  # Доступные: 'circle', 'square', 'spiral', 'random'
        self.get_logger().info(f'Запущена нода turtle_publisher в режиме: {self.mode}')
        
        # Переменные для разных режимов
        self.angle = 0.0
        self.side_counter = 0
        self.spiral_radius = 1.0
        self.step_counter = 0
    
    def timer_callback(self):
        """Вызывается регулярно для публикации команд движения"""
        msg = Twist()
        
        if self.mode == 'circle':
            self.move_circle(msg)
        elif self.mode == 'square':
            self.move_square(msg)
        elif self.mode == 'spiral':
            self.move_spiral(msg)
        elif self.mode == 'random':
            self.move_random(msg)
        else:
            self.get_logger().warn('Неизвестный режим движения')
            return
        
        # Публикуем сообщение
        self.publisher.publish(msg)
        self.step_counter += 1
    
    def move_circle(self, msg):
        """Движение по кругу"""
        # Линейная скорость вперед
        msg.linear.x = 2.0
        # Постоянный поворот для движения по кругу
        msg.angular.z = 1.0
    
    def move_square(self, msg):
        """Движение по квадрату"""
        # Каждая сторона квадрата - 20 шагов (2 секунды)
        steps_per_side = 20
        
        if self.side_counter < steps_per_side:
            # Движение вперед
            msg.linear.x = 1.0
            msg.angular.z = 0.0
        elif self.side_counter < steps_per_side + 10:
            # Поворот на 90 градусов
            msg.linear.x = 0.0
            msg.angular.z = math.pi / 2  # 90 градусов за 1 секунду
        else:
            self.side_counter = -1  # Сброс для следующей стороны
        
        self.side_counter += 1
    
    def move_spiral(self, msg):
        """Движение по спирали"""
        # Увеличиваем радиус спирали со временем
        t = self.step_counter * 0.1  # Время в секундах
        
        # Линейная скорость растет со временем
        msg.linear.x = 1.0 + 0.1 * t
        
        # Угловая скорость уменьшается для создания спирали
        msg.angular.z = 2.0 / (1.0 + 0.1 * t)
    
    def move_random(self, msg):
        """Случайное блуждание"""
        if self.step_counter % 10 == 0:  # Меняем направление каждую секунду
            # Случайная линейная скорость от 0.5 до 2.0
            msg.linear.x = random.uniform(0.5, 2.0)
            # Случайный поворот от -1.5 до 1.5 рад/с
            msg.angular.z = random.uniform(-1.5, 1.5)
        
        # Сохраняем последнюю скорость до следующего изменения
        if hasattr(self, 'last_linear'):
            msg.linear.x = self.last_linear
            msg.angular.z = self.last_angular
        
        self.last_linear = msg.linear.x
        self.last_angular = msg.angular.z

def main(args=None):
    rclpy.init(args=args)
    
    # Создаём ноду
    turtle_publisher = TurtlePublisher()
    
    try:
        # Запускаем ноду
        rclpy.spin(turtle_publisher)
    except KeyboardInterrupt:
        turtle_publisher.get_logger().info('Остановка ноды...')
    finally:
        # Очистка
        turtle_publisher.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

---

## 📦 **Шаг 3: Настройка пакета**

### **3.1 Редактируем файл setup.py**
```bash
cd ~/ros2_ws/src/my_turtle_controller
nano setup.py
```

### **3.2 Добавляем точку входа в секцию entry_points**
```python
entry_points={
    'console_scripts': [
        'turtle_publisher = my_turtle_controller.turtle_publisher:main',
    ],
},
```

### **3.3 Проверяем package.xml (должен содержать зависимости)**
```xml
<depend>rclpy</depend>
<depend>geometry_msgs</depend>
<depend>turtlesim</depend>
```

---

## 🔨 **Шаг 4: Сборка и запуск**

### **4.1 Собираем пакет**
```bash
cd ~/ros2_ws
colcon build --packages-select my_turtle_controller
source install/setup.bash
```

### **4.2 Запускаем turtlesim (в первом терминале)**
```bash
ros2 run turtlesim turtlesim_node
```

### **4.3 Запускаем наш publisher (во втором терминале)**
```bash
ros2 run my_turtle_controller turtle_publisher
```

---

## Шаг 5: Эксперименты и модификации

### **5.1 Добавляем параметры командной строки**
Модифицируем код для поддержки разных режимов через аргументы:

```python
# В начало файла добавить:
import argparse

# В класс TurtlePublisher в __init__:
def __init__(self, mode='circle'):
    super().__init__('turtle_publisher')
    self.mode = mode
    # остальная часть инициализации остается как в полной версии выше

# В функцию main:
def main(args=None):
    rclpy.init(args=args)
    
    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default='circle',
                       choices=['circle', 'square', 'spiral', 'random'],
                       help='Режим движения черепашки')
    args = parser.parse_args()
    
    turtle_publisher = TurtlePublisher(mode=args.mode)
    # остальная часть main остается как в полной версии выше
```

### **5.2 Запуск с разными режимами**
```bash
# Движение по кругу (по умолчанию)
ros2 run my_turtle_controller turtle_publisher --mode circle

# Движение по квадрату
ros2 run my_turtle_controller turtle_publisher --mode square

# Спираль
ros2 run my_turtle_controller turtle_publisher --mode spiral

# Случайное блуждание
ros2 run my_turtle_controller turtle_publisher --mode random
```

### **5.3 Дополнительные улучшения**

#### **Добавление плавного старта/остановки:**
```python
def smooth_move(self, msg, target_linear, target_angular, acceleration=0.1):
    """Плавное изменение скорости"""
    if not hasattr(self, 'current_linear'):
        self.current_linear = 0.0
        self.current_angular = 0.0
    
    # Плавное изменение скорости
    self.current_linear += acceleration * (target_linear - self.current_linear)
    self.current_angular += acceleration * (target_angular - self.current_angular)
    
    msg.linear.x = self.current_linear
    msg.angular.z = self.current_angular
```

#### **Добавление обратной связи (подписка на pose):**
```python
# В __init__ добавляем подписчика
self.pose_subscriber = self.create_subscription(
    Pose,
    '/turtle1/pose',
    self.pose_callback,
    10
)
self.current_pose = None

def pose_callback(self, msg):
    """Получаем текущую позицию черепашки"""
    self.current_pose = msg
    # Можно использовать для интеллектуального движения
```

---

## 🧪 **Шаг 6: Тестирование и отладка**

### **6.1 Просмотр публикуемых сообщений**
```bash
# В третьем терминале:
ros2 topic echo /turtle1/cmd_vel
```

### **6.2 Измерение частоты публикации**
```bash
ros2 topic hz /turtle1/cmd_vel
```

### **6.3 Визуализация графа**
```bash
ros2 run rqt_graph rqt_graph
```

### **6.4 Мониторинг нод**
```bash
ros2 node list
ros2 node info /turtle_publisher
```

---

## Шаг 7: Дополнительные упражнения

### **Упражнение 1: Восьмёрка**
Реализуйте движение черепашки по траектории в виде восьмёрки (лемнискаты).

**Подсказка:** используйте параметрические уравнения:
```python
t = self.step_counter * 0.1
scale = 2.0
msg.linear.x = scale * math.cos(t)
msg.angular.z = scale * math.sin(2*t) / (1 + math.cos(t)**2)
```

### **Упражнение 2: Следующая точка**
Создайте ноду, которая ведёт черепаху к заданным координатам.

### **Упражнение 3: Избегание препятствий**
Добавьте логику для изменения направления при приближении к краю экрана.

---

## 🧹 **Шаг 8: Очистка**
Не забудьте остановить все ноды нажатием **Ctrl+C** в каждом терминале.

---

## Ключевые концепции

- **Создание ROS 2 пакета**
- **Написание ноды-publisher на Python**
- **Работа с сообщениями типа Twist**
- **Использование таймеров для периодических действий**
- **Реализация разных алгоритмов движения**
- **Сборка и запуск собственной ноды**

---

## Что дальше

1. **Создание подписчика (subscriber)** для чтения позиции черепашки
2. **Использование сервисов** для изменения цвета фона
3. **Создание действий (actions)** для сложных последовательностей движений
4. **Работа с параметрами** для настройки ноды без изменения кода
