# **Туториал по ROS 2: Пишем listener (Python)**
*Учимся получать и использовать трансформации из tf2 для управления роботом*

## 🎯 **Цель туториала**
Создать узел-слушатель (**listener**), который будет запрашивать у tf2 трансформацию между фреймами двух черепах и на её основе публиковать команды скорости, чтобы одна черепаха следовала за другой. Мы воссоздадим демонстрацию из вводного туториала "[Знакомство с tf2](link_to_intro)".

---

## 📖 **Зачем нужен listener?**
Broadcaster'ы публикуют данные о положении фреймов. Но чтобы эти данные стали полезными, нужен механизм их **получения и обработки**. Listener — это узел, который:
1.  Накопляет все трансформации, публикуемые в системе (с помощью `Buffer`).
2.  Позволяет в любой момент запросить: «Какая трансформация между фреймом `A` и фреймом `B` в момент времени `T`?»
3.  Использует полученные координаты для принятия решений: например, для вычисления траектории движения.

---

## ✅ **Предварительные требования**
1.  **Полностью выполнены предыдущие туториалы:**
    *   "[Пишем статический broadcaster (Python)](link_to_static)"
    *   "[Пишем динамический broadcaster (Python)](link_to_dynamic)"
2.  Наличие пакета `learning_tf2_py` с добавленными в него узлами `turtle_tf2_broadcaster.py` и настроенными зависимостями.
3.  Рабочее окружение ROS 2 (workspace) и базовые знания о сервисах в ROS 2 (для понимания спавна второй черепахи).

---

## 🚀 **Практическая часть: Заставляем черепах играть в догонялки**

Мы добавим в пакет `learning_tf2_py` узел-слушатель и обновим launch-файл для запуска полной демонстрации с двумя черепахами.

### **1. Создание файла узла listener'а**
Перейдите в директорию с исходным кодом пакета и загрузите пример кода.

```bash
cd ~/ros2_ws/src/learning_tf2_py/learning_tf2_py
wget https://raw.githubusercontent.com/ros/geometry_tutorials/jazzy/turtle_tf2_py/turtle_tf2_py/turtle_tf2_listener.py
```

Если `wget` недоступен, скопируйте содержимое [файла](https://github.com/ros/geometry_tutorials/blob/jazzy/turtle_tf2_py/turtle_tf2_py/turtle_tf2_listener.py) вручную и сохраните его под именем `turtle_tf2_listener.py`.

### **2. Анализ кода (`turtle_tf2_listener.py`)**
Этот узел сложнее предыдущих, так как он выполняет несколько задач одновременно. Разберём его по частям.

```python
import math
from geometry_msgs.msg import Twist  # Для команд скорости
import rclpy
from rclpy.node import Node
from tf2_ros import TransformException  # Для обработки ошибок tf2
from tf2_ros.buffer import Buffer  # Хранилище трансформаций
from tf2_ros.transform_listener import TransformListener  # Слушатель tf2
from turtlesim.srv import Spawn  # Сервис для создания новой черепахи

class FrameListener(Node):

    def __init__(self):
        super().__init__('turtle_tf2_frame_listener')

        # 1. Параметр: за какой черепахой следить (по умолчанию turtle1)
        self.target_frame = self.declare_parameter(
          'target_frame', 'turtle1').get_parameter_value().string_value

        # 2. Создаём буфер и слушатель tf2
        self.tf_buffer = Buffer()  # Буфер будет хранить трансформации
        self.tf_listener = TransformListener(self.tf_buffer, self)  # Слушатель наполняет буфер

        # 3. Клиент для сервиса spawn (создание второй черепахи)
        self.spawner = self.create_client(Spawn, 'spawn')
        self.turtle_spawning_service_ready = False
        self.turtle_spawned = False

        # 4. Издатель для команд скорости черепахи turtle2
        self.publisher = self.create_publisher(Twist, 'turtle2/cmd_vel', 1)

        # 5. Таймер, который будет вызывать функцию каждую секунду
        self.timer = self.create_timer(1.0, self.on_timer)

    def on_timer(self):
        # Эта функция вызывается каждую секунду

        # --- Часть 1: Спавн второй черепахи (если ещё не создана) ---
        # ... (код с использованием сервиса Spawn) ...

        # --- Часть 2: Получение трансформации и управление ---
        # Определяем, от какого фрейма (target_frame) к какому (turtle2) нужно получить трансформацию
        from_frame_rel = self.target_frame
        to_frame_rel = 'turtle2'

        # Проверяем, что черепаха создана
        if self.turtle_spawned:
            try:
                # ✨✨✨ ГЛАВНОЕ: ЗАПРАШИВАЕМ ТРАНСФОРМАЦИЮ ✨✨✨
                # Запрос: трансформация фрейма target_frame относительно фрейма turtle2 на текущий момент времени
                t = self.tf_buffer.lookup_transform(
                    to_frame_rel,      # Целевой фрейм (turtle2)
                    from_frame_rel,    # Исходный фрейм (например, turtle1)
                    rclpy.time.Time()) # Запрашиваем самую свежую трансформацию
            except TransformException as ex:
                # Если трансформация ещё недоступна (например, нет данных), просто логируем и выходим
                self.get_logger().info(f'Could not transform {to_frame_rel} to {from_frame_rel}: {ex}')
                return

            # Если трансформация получена, создаём сообщение Twist
            msg = Twist()
            # Поворачиваемся в сторону цели: atan2(y, x) даёт угол до цели
            msg.angular.z = 1.0 * math.atan2(
                t.transform.translation.y,
                t.transform.translation.x)

            # Едем вперёд со скоростью, пропорциональной расстоянию до цели
            msg.linear.x = 0.5 * math.sqrt(
                t.transform.translation.x ** 2 +
                t.transform.translation.y ** 2)

            # Публикуем команду для turtle2
            self.publisher.publish(msg)

# ... (функция main)
```

#### **2.1 Ключевые моменты кода**

*   **`Buffer` и `TransformListener`**:
    *   `self.tf_buffer = Buffer()` — создаётся буфер, который хранит все входящие трансформации (по умолчанию 10 секунд).
    *   `self.tf_listener = TransformListener(self.tf_buffer, self)` — слушатель автоматически наполняет буфер данными из топиков `/tf` и `/tf_static`.
*   **`lookup_transform()`**:
    *   Это **сердце listener'а**. Функция ищет в буфере трансформацию, которая связывает два фрейма.
    *   Аргументы: `target_frame` (куда мы хотим преобразовать), `source_frame` (откуда), и время.
    *   Возвращает объект `TransformStamped`, содержащий вектор `translation` и кватернион `rotation`. В нашем случае, это положение `turtle1` (source) в системе координат `turtle2` (target).
    *   Всегда вызывается внутри `try-except`, так как трансформация может быть ещё недоступна (например, если фрейм не публикуется).
*   **Управление**:
    *   Угловая скорость (`angular.z`) вычисляется через `atan2(y, x)`, чтобы смотреть прямо на цель.
    *   Линейная скорость (`linear.x`) пропорциональна расстоянию (`sqrt(x^2 + y^2)`), чтобы черепаха замедлялась при приближении.

### **3. Добавление точки входа (entry point)**
Откройте `~/ros2_ws/src/learning_tf2_py/setup.py` и добавьте новую консольную скрипту в список `'console_scripts'`:

```python
    'console_scripts': [
        'static_turtle_tf2_broadcaster = learning_tf2_py.static_turtle_tf2_broadcaster:main',
        'turtle_tf2_broadcaster = learning_tf2_py.turtle_tf2_broadcaster:main',
        'turtle_tf2_listener = learning_tf2_py.turtle_tf2_listener:main',  # <-- Добавьте эту строку
    ],
```

### **4. Обновление launch-файла**
Теперь соберём всё вместе. Откройте файл `turtle_tf2_demo.launch.py`, который мы создали ранее, и обновите его, добавив:
*   Запуск второго broadcaster'а для `turtle2`.
*   Запуск нашего listener'а.
*   Аргумент `target_frame`, чтобы можно было менять цель.

Вот полное содержимое файла:

```python
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # --- Запускаем симулятор черепахи ---
        Node(
            package='turtlesim',
            executable='turtlesim_node',
            name='sim'
        ),

        # --- Broadcaster для turtle1 ---
        Node(
            package='learning_tf2_py',
            executable='turtle_tf2_broadcaster',
            name='broadcaster1',
            parameters=[
                {'turtlename': 'turtle1'}
            ]
        ),

        # --- Broadcaster для turtle2 ---
        Node(
            package='learning_tf2_py',
            executable='turtle_tf2_broadcaster',
            name='broadcaster2',
            parameters=[
                {'turtlename': 'turtle2'}
            ]
        ),

        # --- Аргумент для listener'а: за кем следить? (по умолчанию turtle1) ---
        DeclareLaunchArgument(
            'target_frame', default_value='turtle1',
            description='Target frame name (the one being followed).'
        ),

        # --- Listener, который управляет turtle2 ---
        Node(
            package='learning_tf2_py',
            executable='turtle_tf2_listener',
            name='listener',
            parameters=[
                {'target_frame': LaunchConfiguration('target_frame')}
            ]
        ),
    ])
```

### **5. Сборка**
Убедитесь, что все зависимости установлены, и соберите пакет.

```bash
cd ~/ros2_ws
rosdep install -i --from-path src --rosdistro jazzy -y
colcon build --packages-select learning_tf2_py
source install/setup.bash
```

### **6. Запуск полной демонстрации**
Теперь мы можем запустить всё одной командой и увидеть результат!

**Терминал 1: Запуск демо**
```bash
ros2 launch learning_tf2_py turtle_tf2_demo.launch.py
```
Должно открыться окно `turtlesim` с двумя черепахами. Вторая черепаха (`turtle2`) пока стоит на месте (в координатах `x=4, y=2`, которые мы задали в коде listener'а).

**Терминал 2: Управление**
```bash
ros2 run turtlesim turtle_teleop_key
```
(Сделайте этот терминал активным).

**Результат:** Как только вы начнёте двигать первую черепаху стрелками, вторая черепаха тут же оживёт и начнёт преследовать её! 🎉

### **7. Проверка работы**
*   В терминале, где запущен listener, вы можете увидеть сообщения вроде `Could not transform turtle2 to turtle1...` в самом начале — это нормально, пока трансформации не появились.
*   Используйте `tf2_echo`, чтобы увидеть трансформацию между черепахами в реальном времени:
    ```bash
    ros2 run tf2_ros tf2_echo turtle2 turtle1
    ```
    Вы увидите, как координаты `turtle1` относительно `turtle2` постоянно меняются.

---

## 📝 **Ключевые выводы**
✅ **`TransformListener`** автоматически получает все трансформации из сети и хранит их в **`Buffer`**.
✅ Метод **`lookup_transform()`** позволяет запросить трансформацию между любыми двумя фреймами на любой момент времени.
✅ Всегда обрабатывайте исключение **`TransformException`**, так как запрашиваемая трансформация может быть временно недоступна.
✅ Listener — это связующее звено между данными о положении (трансформациями) и действием (управлением).
✅ Вы завершили создание полноценной tf2-системы: broadcaster'ы публикуют данные, listener их использует.

---

## 🎮 **Практическое задание**
1.  Попробуйте изменить цель для следования. Остановите демо (`Ctrl+C`) и запустите его снова, но теперь укажите, чтобы `turtle2` следовала за `world`:
    ```bash
    ros2 launch learning_tf2_py turtle_tf2_demo.launch.py target_frame:=world
    ```
    Что произойдёт? Почему?
2.  Модифицируйте код listener'а, чтобы изменить поведение второй черепахи. Например, сделайте так, чтобы она следовала за первой наоборот (пятясь задом) или всегда держалась на расстоянии.
3.  Добавьте в launch-файл запуск `rviz2` с конфигурацией для визуализации фреймов (как мы делали во вводном туториале), чтобы видеть оси координат черепах в 3D.

---

## 🔜 **Что дальше?**
Поздравляю! Вы прошли полный цикл работы с tf2: от понимания концепции до написания собственных broadcaster'ов и listener'а. Это фундаментальный навык для работы с любой реальной робототехнической системой в ROS 2.

Следующими темами для изучения могут быть:
*   **Добавление фреймов** (Adding a frame) — создание иерархических деревьев фреймов.
*   **Использование времени в tf2** (Time travel) — запрос трансформаций в прошлом.
*   **Обработка временных задержек** (Timeouts) в трансформациях.