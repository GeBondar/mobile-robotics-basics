# **Туториал по ROS 2: Пишем динамический broadcaster (Python)**
*Учимся публиковать движущиеся координатные фреймы для tf2*

## 🎯 **Цель туториала**
Создать и запустить узел ROS 2 на Python, который будет транслировать (**broadcast**) положение движущейся черепахи из симулятора `turtlesim` в библиотеку tf2. Это позволит нам в реальном времени отслеживать положение фрейма `turtle1` относительно фрейма `world`.

---

## 📖 **Зачем нужен динамический broadcaster?**
В предыдущем туториале мы научились публиковать **неподвижные** связи (например, крепление датчика к базе робота). Но роботы движутся! Нам нужно постоянно обновлять информацию о положении его частей (колёс, захватов, самой базы) в пространстве.

**Динамический broadcaster** решает эту задачу: он подписывается на топики с одометрией или данными датчиков положения и публикует актуальные трансформации для tf2 с высокой частотой.

---

## ✅ **Предварительные требования**
1. **Завершённые предыдущие туториалы:**
   *   "[Знакомство с tf2](link_to_intro_tutorial)"
   *   "[Пишем статический broadcaster (Python)](link_to_static_broadcaster_tutorial)"
2. Наличие пакета `learning_tf2_py`, созданного в прошлом туториале.
3. Рабочее окружение ROS 2 (workspace) настроено и файлы `setup.bash` прописаны.

---

## 🚀 **Практическая часть: Оживляем черепаху**

Мы добавим в наш пакет `learning_tf2_py` новый узел, который будет публиковать трансформации для движущейся черепахи.

### **1. Создание файла узла broadcaster'а**
Перейдите в директорию с исходным кодом пакета и загрузите пример кода.

```bash
cd ~/ros2_ws/src/learning_tf2_py/learning_tf2_py
wget https://raw.githubusercontent.com/ros/geometry_tutorials/jazzy/turtle_tf2_py/turtle_tf2_py/turtle_tf2_broadcaster.py
```

Если `wget` недоступен, скопируйте содержимое [файла](https://github.com/ros/geometry_tutorials/blob/jazzy/turtle_tf2_py/turtle_tf2_py/turtle_tf2_broadcaster.py) вручную и сохраните его под именем `turtle_tf2_broadcaster.py`.

### **2. Анализ кода (`turtle_tf2_broadcaster.py`)**
Давайте разберём ключевые отличия от статического broadcaster'а.

```python
import math
from geometry_msgs.msg import TransformStamped
import numpy as np
import rclpy
from rclpy.node import Node
from tf2_ros import TransformBroadcaster  # <-- Импортируем ДИНАМИЧЕСКИЙ broadcaster
from turtlesim.msg import Pose  # <-- Тип сообщений о положении черепахи

# ... (функция quaternion_from_euler та же)

class FramePublisher(Node):

    def __init__(self):
        super().__init__('turtle_tf2_frame_publisher')

        # 1. Объявляем параметр для имени черепахи (позволит использовать один узел для turtle1 и turtle2)
        self.turtlename = self.declare_parameter(
          'turtlename', 'turtle').get_parameter_value().string_value

        # 2. Инициализируем ДИНАМИЧЕСКИЙ broadcaster
        self.tf_broadcaster = TransformBroadcaster(self)

        # 3. Подписываемся на топик с данными о положении черепахи
        self.subscription = self.create_subscription(
            Pose,                          # Тип сообщения
            f'/{self.turtlename}/pose',    # Имя топика (зависит от параметра)
            self.handle_turtle_pose,       # Callback-функция
            1)                              # Глубина очереди
        self.subscription

    def handle_turtle_pose(self, msg):
        # Этот метод вызывается КАЖДЫЙ раз, когда приходит новое сообщение о положении черепахи

        # Создаём объект трансформации
        t = TransformStamped()

        # Заполняем метаданные
        t.header.stamp = self.get_clock().now().to_msg()  # Время получения данных
        t.header.frame_id = 'world'                        # Родительский фрейм
        t.child_frame_id = self.turtlename                 # Дочерний фрейм (имя черепахи)

        # Заполняем трансляцию (перемещение) из сообщения Pose
        t.transform.translation.x = msg.x
        t.transform.translation.y = msg.y
        t.transform.translation.z = 0.0                     # Черепаха в 2D

        # Заполняем поворот (вращение вокруг Z) из сообщения Pose
        q = quaternion_from_euler(0, 0, msg.theta)
        t.transform.rotation.x = q[0]
        t.transform.rotation.y = q[1]
        t.transform.rotation.z = q[2]
        t.transform.rotation.w = q[3]

        # 4. Публикуем трансформацию!
        self.tf_broadcaster.sendTransform(t)

# ... (функция main)
```

**Ключевые изменения по сравнению со статическим broadcaster'ом:**

*   **Тип broadcaster'а:** Используется **`TransformBroadcaster`** (из `tf2_ros`), а не `StaticTransformBroadcaster`. Он оптимизирован для частой публикации меняющихся данных.
*   **Подписка на данные:** Узел **подписывается на топик** (например, `/turtle1/pose`), откуда получает актуальное положение черепахи.
*   **Callback-функция:** Трансформация публикуется **внутри callback'а** при каждом получении нового сообщения о положении. Таким образом, tf2 всегда имеет самую свежую информацию.
*   **Параметр `turtlename`:** Узел использует параметр для гибкости — один и тот же код сможет работать и для `turtle1`, и для `turtle2`.

### **3. Добавление точки входа (entry point)**
Откройте `~/ros2_ws/src/learning_tf2_py/setup.py` и добавьте новую консольную скрипту в список `'console_scripts'`:

```python
    'console_scripts': [
        'static_turtle_tf2_broadcaster = learning_tf2_py.static_turtle_tf2_broadcaster:main',
        'turtle_tf2_broadcaster = learning_tf2_py.turtle_tf2_broadcaster:main',  # <-- Добавьте эту строку
    ],
```

### **4. Создание launch-файла**
Для удобного запуска всех узлов создадим launch-файл. Сначала создайте папку `launch` в корне пакета:

```bash
cd ~/ros2_ws/src/learning_tf2_py
mkdir launch
```

Теперь создайте файл `turtle_tf2_demo.launch.py` внутри папки `launch` со следующим содержимым:

```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # Запускаем симулятор черепахи
        Node(
            package='turtlesim',
            executable='turtlesim_node',
            name='sim'
        ),
        # Запускаем наш broadcaster для turtle1
        Node(
            package='learning_tf2_py',
            executable='turtle_tf2_broadcaster',
            name='broadcaster1',
            parameters=[
                {'turtlename': 'turtle1'}  # Передаём параметр с именем черепахи
            ]
        ),
    ])
```

### **5. Обновление файлов конфигурации**
*   **`package.xml`**: Добавьте зависимости для launch-файлов:
    ```xml
    <exec_depend>launch</exec_depend>
    <exec_depend>launch_ros</exec_depend>
    ```
*   **`setup.py`**: Добавьте импорты и укажите, что папка `launch` должна быть установлена. В начало файла добавьте:
    ```python
    import os
    from glob import glob
    ```
    А в список `data_files` добавьте строку для копирования launch-файлов:
    ```python
    data_files=[
        ...
        (os.path.join('share', package_name, 'launch'), glob('launch/*')),
    ],
    ```

### **6. Сборка и запуск**
Соберите пакет и запустите демонстрацию.

**Сборка:**
```bash
cd ~/ros2_ws
colcon build --packages-select learning_tf2_py
source install/setup.bash
```

**Запуск (в терминале 1):**
```bash
ros2 launch learning_tf2_py turtle_tf2_demo.launch.py
```
Вы увидите окно `turtlesim` с одной черепахой.

**Запуск управления (в терминале 2):**
```bash
ros2 run turtlesim turtle_teleop_key
```
(Не забудьте сделать этот терминал активным, нажав на него).

### **7. Проверка результата**
Откройте **третий терминал** и используйте `tf2_echo`, чтобы увидеть транслируемые данные:

```bash
ros2 run tf2_ros tf2_echo world turtle1
```
Теперь, когда вы управляете черепахой стрелками, вы будете видеть, как координаты её положения (`Translation`) и поворота (`Rotation`) постоянно обновляются в реальном времени.

```
At time 1714913843.708748879
- Translation: [4.541, 3.889, 0.000]
- Rotation: in Quaternion [0.000, 0.000, 0.999, -0.035]
...
```

Если вы попробуете запросить трансформацию для `turtle2` (`tf2_echo world turtle2`), вы получите ошибку — её пока нет в системе.

---

## 📝 **Ключевые выводы**
✅ Для динамических трансформаций используется класс **`TransformBroadcaster`**.
✅ Узел-вещатель обычно **подписывается на топик с данными о положении** (одометрия, поза) и публикует трансформации в callback'е.
✅ Публикация происходит **с частотой поступления входных данных**, обеспечивая актуальность информации в tf2.
✅ **Параметры узла** (как `turtlename`) делают код переиспользуемым для разных сущностей.
✅ Launch-файлы позволяют запускать комплексные демонстрации одной командой.

---

## 🎮 **Практическое задание**
1. Модифицируйте launch-файл, чтобы добавить в него узел `turtle_teleop_key`. *Подсказка: вам понадобится второй `Node` с параметрами `package='turtlesim'`, `executable='turtle_teleop_key'`, `name='teleop'`.*
2. Самостоятельно создайте копию узла `turtle_tf2_broadcaster`, который будет публиковать трансформации для `turtle2`, и добавьте его запуск в launch-файл. *Вам нужно будет скопировать файл `.py` (или использовать тот же с другим параметром `turtlename`) и добавить соответствующий `Node` в launch-файл.*

---

## 🔜 **Что дальше?**
Поздравляю! Вы научились публиковать движущиеся фреймы. Теперь самое интересное — **написать listener (слушателя)**, который будет использовать эти трансформации, чтобы, например, заставить вторую черепаху преследовать первую. Это тема следующего туториала.