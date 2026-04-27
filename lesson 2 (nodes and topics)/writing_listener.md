# Создание subscriber для чтения позиции turtlesim в ROS 2

## Цель
Создать ноду-subscriber на Python, которая читает данные о позиции черепахи из топика `/turtle1/pose` и обрабатывает их.

---

## Что мы будем делать
1. Используем существующий ROS 2 пакет (или создадим новый)
2. Напишем ноду-subscriber на Python
3. Реализуем различные способы обработки данных:
   - Простой вывод позиции в консоль
   - Вычисление пройденного расстояния
   - Отслеживание угла поворота
   - Определение достижения целевой точки

---

## Шаг 1: Подготовка рабочего пространства и пакета

### **1.1 Используем существующий пакет (или создаём новый)**
```bash
# Если пакет my_turtle_controller уже существует (из предыдущего туториала)
cd ~/ros2_ws/src/my_turtle_controller/my_turtle_controller

# ИЛИ создаём новый пакет
ros2 pkg create my_turtle_subscriber \
  --build-type ament_python \
  --dependencies rclpy turtlesim
```

---

## Шаг 2: Создание ноды-subscriber

### **2.1 Создаём файл с нодой**
```bash
touch turtle_subscriber.py
chmod +x turtle_subscriber.py
```

### **2.2 Открываем файл для редактирования**
```bash
nano turtle_subscriber.py
```

### **2.3 Код ноды-subscriber (базовая версия)**
```python
#!/usr/bin/env python3
"""
Нода-subscriber для чтения позиции черепахи в turtlesim.
"""

import rclpy
from rclpy.node import Node
from turtlesim.msg import Pose
import math

class TurtleSubscriber(Node):
    def __init__(self):
        super().__init__('turtle_subscriber')
        
        # Создаём подписчика для топика /turtle1/pose
        self.subscription = self.create_subscription(
            Pose,
            '/turtle1/pose',
            self.pose_callback,
            10
        )
        
        # Предотвращаем предупреждение о неиспользуемой переменной
        self.subscription
        
        # Переменные для хранения истории
        self.last_pose = None
        self.total_distance = 0.0
        self.start_pose = None
        
        self.get_logger().info('Нода turtle_subscriber запущена. Ожидание данных о позиции черепахи...')
    
    def pose_callback(self, msg):
        """Обработчик сообщений с позицией черепашки"""
        # Простой вывод позиции
        self.get_logger().info(
            f'Позиция: x={msg.x:.2f}, y={msg.y:.2f}, θ={msg.theta:.2f} рад'
        )
        
        # Если это первое сообщение, сохраняем как стартовую позицию
        if self.start_pose is None:
            self.start_pose = msg
            self.get_logger().info(f'Стартовая позиция: x={msg.x:.2f}, y={msg.y:.2f}')
        
        # Вычисляем пройденное расстояние
        if self.last_pose is not None:
            distance = math.sqrt(
                (msg.x - self.last_pose.x)**2 + 
                (msg.y - self.last_pose.y)**2
            )
            self.total_distance += distance
            
            # Периодически выводим пройденное расстояние
            if int(self.total_distance * 10) % 10 == 0:
                self.get_logger().info(f'Пройдено расстояние: {self.total_distance:.2f} единиц')
        
        # Сохраняем текущую позицию для следующего вычисления
        self.last_pose = msg

def main(args=None):
    rclpy.init(args=args)
    
    # Создаём ноду
    turtle_subscriber = TurtleSubscriber()
    
    try:
        # Запускаем ноду
        rclpy.spin(turtle_subscriber)
    except KeyboardInterrupt:
        turtle_subscriber.get_logger().info('Остановка ноды...')
        
        # Выводим итоговую статистику
        if turtle_subscriber.start_pose is not None and turtle_subscriber.last_pose is not None:
            final_distance = math.sqrt(
                (turtle_subscriber.last_pose.x - turtle_subscriber.start_pose.x)**2 + 
                (turtle_subscriber.last_pose.y - turtle_subscriber.start_pose.y)**2
            )
            turtle_subscriber.get_logger().info(
                f'Итог: пройдено {turtle_subscriber.total_distance:.2f} единиц, '
                f'смещение от старта: {final_distance:.2f} единиц'
            )
    finally:
        # Очистка
        turtle_subscriber.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

---

## 📦 **Шаг 3: Настройка пакета**

### **3.1 Редактируем файл setup.py**
```bash
cd ~/ros2_ws/src/my_turtle_subscriber
nano setup.py
```

### **3.2 Добавляем точку входа в секцию entry_points**
```python
entry_points={
    'console_scripts': [
        'turtle_subscriber = my_turtle_subscriber.turtle_subscriber:main',
    ],
},
```

### **3.3 Проверяем package.xml (должен содержать зависимости)**
```xml
<depend>rclpy</depend>
<depend>turtlesim</depend>
```

---

## 🔨 **Шаг 4: Сборка и запуск**

### **4.1 Собираем пакет**
```bash
cd ~/ros2_ws
colcon build --packages-select my_turtle_subscriber
source install/setup.bash
```

### **4.2 Запускаем turtlesim (в первом терминале)**
```bash
ros2 run turtlesim turtlesim_node
```

### **4.3 Запускаем publisher для движения черепашки (во втором терминале)**
```bash
# Используем publisher из предыдущего туториала или стандартный teleop
ros2 run turtlesim turtle_teleop_key
# ИЛИ если есть наш publisher:
ros2 run my_turtle_controller turtle_publisher
```

### **4.4 Запускаем наш subscriber (в третьем терминале)**
```bash
ros2 run my_turtle_subscriber turtle_subscriber
```

---

## Шаг 5: Улучшения и расширения

### **5.1 Добавляем фильтрацию сообщений**
Модифицируем код для вывода позиции только при значительных изменениях:

```python
def pose_callback(self, msg):
    """Обработчик с фильтрацией"""
    # Выводим только если позиция изменилась значительно
    if (self.last_pose is None or 
        abs(msg.x - self.last_pose.x) > 0.1 or 
        abs(msg.y - self.last_pose.y) > 0.1):
        
        self.get_logger().info(
            f'Позиция изменилась: x={msg.x:.2f}, y={msg.y:.2f}'
        )
    
    self.last_pose = msg
```

### **5.2 Реализуем отслеживание цели**
```python
class GoalTrackingSubscriber(Node):
    def __init__(self, goal_x=5.0, goal_y=5.0):
        super().__init__('goal_tracking_subscriber')
        
        self.subscription = self.create_subscription(
            Pose,
            '/turtle1/pose',
            self.pose_callback,
            10
        )
        
        self.goal_x = goal_x
        self.goal_y = goal_y
        self.goal_reached = False
        self.goal_threshold = 0.5  # радиус достижения цели
        
        self.get_logger().info(f'Цель: ({goal_x}, {goal_y})')
    
    def pose_callback(self, msg):
        # Вычисляем расстояние до цели
        distance_to_goal = math.sqrt(
            (msg.x - self.goal_x)**2 + 
            (msg.y - self.goal_y)**2
        )
        
        # Проверяем достижение цели
        if not self.goal_reached and distance_to_goal < self.goal_threshold:
            self.goal_reached = True
            self.get_logger().info('Цель достигнута')
        
        # Выводим информацию о расстоянии до цели
        if not self.goal_reached:
            self.get_logger().info(
                f'До цели: {distance_to_goal:.2f} единиц, '
                f'текущая позиция: ({msg.x:.2f}, {msg.y:.2f})'
            )
```

### **5.3 Добавляем параметры командной строки**
```python
import argparse

def main(args=None):
    rclpy.init(args=args)
    
    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser()
    parser.add_argument('--goal_x', type=float, default=5.0,
                       help='X-координата цели')
    parser.add_argument('--goal_y', type=float, default=5.0,
                       help='Y-координата цели')
    parsed_args, _ = parser.parse_known_args()
    
    # Создаём ноду с параметрами
    turtle_subscriber = GoalTrackingSubscriber(
        goal_x=parsed_args.goal_x,
        goal_y=parsed_args.goal_y
    )
    
    # остальная часть main остается как в полной версии выше
```

---

## 🧪 **Шаг 6: Тестирование и отладка**

### **6.1 Просмотр топиков**
```bash
# Список всех топиков
ros2 topic list

# Информация о топике /turtle1/pose
ros2 topic info /turtle1/pose

# Ручная публикация в топик (для тестирования)
ros2 topic pub /turtle1/cmd_vel geometry_msgs/msg/Twist "{linear: {x: 2.0}, angular: {z: 1.0}}"
```

### **6.2 Визуализация данных**
```bash
# Запуск rqt_plot для графического отображения позиции
ros2 run rqt_plot rqt_plot
# Затем в интерфейсе: /turtle1/pose/x, /turtle1/pose/y
```

### **6.3 Мониторинг нод**
```bash
# Список запущенных нод
ros2 node list

# Информация о нашей ноде-subscriber
ros2 node info /turtle_subscriber
```

### **6.4 Запись и воспроизведение данных**
```bash
# Запись топика в файл
ros2 bag record /turtle1/pose

# Воспроизведение записанных данных
ros2 bag play <имя_файла_bag>
```

---

## Шаг 7: Дополнительные упражнения

### **Упражнение 1: Скорость и ускорение**
Реализуйте вычисление мгновенной скорости черепашки на основе разности позиций во времени.

**Подсказка:**
```python
# Добавьте в класс
self.last_time = None

def pose_callback(self, msg):
    current_time = self.get_clock().now()
    
    if self.last_pose is not None and self.last_time is not None:
        dt = (current_time - self.last_time).nanoseconds / 1e9
        
        if dt > 0:
            vx = (msg.x - self.last_pose.x) / dt
            vy = (msg.y - self.last_pose.y) / dt
            speed = math.sqrt(vx**2 + vy**2)
            
            self.get_logger().info(f'Скорость: {speed:.2f} ед/сек')
    
    self.last_pose = msg
    self.last_time = current_time
```

### **Упражнение 2: Визуализация траектории**
Создайте ноду, которая сохраняет траекторию движения черепахи и выводит её в конце.

### **Упражнение 3: Автоматический контроллер**
Создайте ноду, которая является одновременно subscriber (читает позицию) и publisher (публикует команды движения) для следования к цели.

---

## 🧹 **Шаг 8: Очистка**
Не забудьте остановить все ноды нажатием **Ctrl+C** в каждом терминале.

---

## Ключевые концепции

- **Создание ROS 2 ноды-subscriber на Python**
- **Работа с сообщениями типа Pose**
- **Обработка callback-функций**
- **Вычисление расстояний и скоростей**
- **Работа с параметрами командной строки**
- **Отладка и мониторинг подписчиков**

---

## Что дальше

1. **Создание ноды с двумя подписками** для чтения данных из нескольких топиков
2. **Использование tf2** для работы с системами координат
3. **Интеграция publisher и subscriber** в одной ноде (контроллер с обратной связью)
4. **Работа с кастомными сообщениями** для передачи сложных структур данных
5. **Создание launch-файлов** для одновременного запуска нескольких нод

---

## Советы по разработке subscribers

1. **Эффективность callback-функций:** Не выполняйте долгие операции в callback, используйте отдельные потоки если нужно
2. **Обработка ошибок:** Всегда добавляйте проверки на None и обработку исключений
3. **Память:** Следите за утечками памяти, особенно при долгой работе
4. **Частота обработки:** Настраивайте QoS (Quality of Service) для контроля частоты сообщений
5. **Тестирование:** Создавайте тестовые сценарии с использованием симуляторов или записями bag-файлов
