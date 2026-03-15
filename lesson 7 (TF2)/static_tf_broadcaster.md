# **Туториал по ROS 2: Пишем статический broadcaster (Python)**
*Учимся публиковать неизменяемые связи между координатными фреймами*

## 🎯 **Цель туториала**
Научиться создавать и запускать узел ROS 2 на Python, который публикует **статические трансформации** (static transforms) в библиотеку tf2. Это основа для описания неподвижных частей робота, например, расположения его датчиков относительно корпуса.

---

## 📖 **Зачем нужны статические трансформации?**
Представьте себе робота с лазерным дальномером (лидаром), установленным на его "голове". Данные от лидара — это расстояния до объектов **в системе координат самого датчика**. Чтобы использовать эти данные для навигации всего робота, нужно знать точное положение и ориентацию датчика **относительно базовой системы координат робота** (обычно `base_link`).

Это отношение (например, "датчик находится на 10 см выше и 5 см спереди центра робота и смотрит прямо") — **не меняется со временем**. Такая трансформация называется **статической**. Публикация статических трансформаций — первый шаг к тому, чтобы tf2 мог автоматически преобразовывать данные из одной системы координат в другую.

---

## ✅ **Предварительные требования**
1. Наличие рабочего пространства (workspace) для ROS 2, например, `ros2_ws`.
2. Знание основ создания пакетов в ROS 2.
3. Понимание концепции координатных фреймов из предыдущего туториала "[Знакомство с tf2](ссылка_на_предыдущий_туториал)".
4. Установленная библиотека `tf2_ros`. Обычно она идёт в комплекте с ROS 2, но если нет — установите её:
   ```bash
   sudo apt-get install ros-<версия>-tf2-ros-py
   ```

---

## 🚀 **Практическая часть: Создаём свой статический фрейм**

Мы создадим пакет `learning_tf2_py` и внутри него напишем узел, который опубликует статическую трансформацию от фрейма `world` к новому фрейму `mystaticturtle`.

### **1. Создание пакета**
Всю работу будем вести в рабочем пространстве. Откройте терминал и выполните:

```bash
cd ~/ros2_ws/src
ros2 pkg create --build-type ament_python --license Apache-2.0 learning_tf2_py
```
Эта команда создаст структуру пакета для Python-кода.

### **2. Написание узла статического broadcaster'а**
Перейдём в только что созданную папку с пакетом и загрузим готовый пример кода.

```bash
cd ~/ros2_ws/src/learning_tf2_py/learning_tf2_py
wget https://raw.githubusercontent.com/ros/geometry_tutorials/ros2/turtle_tf2_py/turtle_tf2_py/static_turtle_tf2_broadcaster.py
```

Если `wget` не работает, скопируйте код вручную из [этого файла](https://github.com/ros/geometry_tutorials/blob/ros2/turtle_tf2_py/turtle_tf2_py/static_turtle_tf2_broadcaster.py).

#### **2.1 Разбор кода (`static_turtle_tf2_broadcaster.py`)**
Давайте разберём ключевые части этого скрипта.

```python
# Импорты: необходимые типы сообщений и библиотеки
from geometry_msgs.msg import TransformStamped  # Сообщение для трансформации
import rclpy
from rclpy.node import Node
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster  # Специальный broadcaster для статики
import numpy as np  # Для математики (не обязательно, но удобно)
import sys

def quaternion_from_euler(ai, aj, ak):
    """Вспомогательная функция для перевода углов Эйлера (roll, pitch, yaw) в кватернион."""
    # ... (математика преобразования)
    return q

class StaticFramePublisher(Node):
    """
    Узел, который публикует неизменяемые трансформации.
    В данном примере публикуется трансформация из 'world' в статический фрейм черепахи.
    Трансформация публикуется только один раз при запуске.
    """

    def __init__(self, transformation):
        super().__init__('static_turtle_tf2_broadcaster')  # Имя узла

        # 1. Создаём broadcaster для статических трансформаций
        self.tf_static_broadcaster = StaticTransformBroadcaster(self)

        # 2. Создаём и отправляем трансформацию
        self.make_transforms(transformation)

    def make_transforms(self, transformation):
        # Создаём объект сообщения TransformStamped
        t = TransformStamped()

        # Заполняем заголовок: время и родительский фрейм
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'world'  # Родительский фрейм
        t.child_frame_id = transformation[1]  # Дочерний фрейм (имя берётся из аргументов)

        # Заполняем трансляцию (перемещение)
        t.transform.translation.x = float(transformation[2])
        t.transform.translation.y = float(transformation[3])
        t.transform.translation.z = float(transformation[4])

        # Заполняем поворот (перевод из углов Эйлера в кватернион)
        quat = quaternion_from_euler(
            float(transformation[5]), float(transformation[6]), float(transformation[7]))
        t.transform.rotation.x = quat[0]
        t.transform.rotation.y = quat[1]
        t.transform.rotation.z = quat[2]
        t.transform.rotation.w = quat[3]

        # Отправляем трансформацию! (только один раз)
        self.tf_static_broadcaster.sendTransform(t)

def main():
    # ... (обработка аргументов командной строки и запуск узла)
    # Ожидание 7 аргументов: имя_узла x y z roll pitch yaw
    # ... 
    with rclpy.init():
        node = StaticFramePublisher(sys.argv)
        rclpy.spin(node)  # Держит узел активным, хотя трансформация уже отправлена
```

**Ключевые моменты:**
*   Используется специальный класс **`StaticTransformBroadcaster`**. Он оптимизирован для публикации трансформаций, которые не меняются.
*   Трансформация публикуется **один раз** в методе `__init__`. Узел продолжает работать (`spin`), но новых сообщений не шлёт.
*   Для поворота используются **кватернионы**, поэтому мы преобразуем удобные для человека углы Эйлера (roll, pitch, yaw) с помощью функции `quaternion_from_euler`.

#### **2.2 Обновление `package.xml`**
Нам нужно указать зависимости нашего пакета. Откройте `~/ros2_ws/src/learning_tf2_py/package.xml` и добавьте следующие строки после тегов `<description>`, `<maintainer>`, `<license>`:

```xml
<exec_depend>geometry_msgs</exec_depend>
<exec_depend>python3-numpy</exec_depend>
<exec_depend>rclpy</exec_depend>
<exec_depend>tf2_ros_py</exec_depend>
```

#### **2.3 Добавление точки входа (entry point)**
Чтобы запустить узел через `ros2 run`, нужно добавить его в `console_scripts` в файле `setup.py`. Откройте `~/ros2_ws/src/learning_tf2_py/setup.py` и найдите секцию `'console_scripts':`. Добавьте туда строку:

```python
    'console_scripts': [
        'static_turtle_tf2_broadcaster = learning_tf2_py.static_turtle_tf2_broadcaster:main',
    ],
```

### **3. Сборка пакета**
Вернитесь в корень рабочего пространства и соберите пакет:

```bash
cd ~/ros2_ws
colcon build --packages-select learning_tf2_py
source install/setup.bash
```

### **4. Запуск и проверка**
Теперь запустим наш узел. Он принимает 7 аргументов:
`имя_дочернего_фрейма` `x` `y` `z` `roll` `pitch` `yaw`

Запустим фрейм с именем `mystaticturtle`, расположенный на 1 метр выше по оси Z (`z=1`):
```bash
ros2 run learning_tf2_py static_turtle_tf2_broadcaster mystaticturtle 0 0 1 0 0 0
```
Узел запустится и замрёт (он будет висеть в терминале). Это нормально.

**Проверим результат.** Откройте **новый терминал** и посмотрите, какие трансформации публикуются на специальном топике `/tf_static`:
```bash
ros2 topic echo /tf_static
```
Вы должны увидеть сообщение, подобное этому:
```
transforms:
- header:
    stamp:
      sec: 1622908754
      nanosec: 208515730
    frame_id: world
  child_frame_id: mystaticturtle
  transform:
    translation:
      x: 0.0
      y: 0.0
      z: 1.0
    rotation:
      x: 0.0
      y: 0.0
      z: 0.0
      w: 1.0
---
```
Поздравляю! Вы только что опубликовали свою первую статическую трансформацию в tf2!

---

## ⚡ **Правильный способ: Использование готового инструмента**
Писать такой код для каждой статической трансформации в реальном проекте не нужно. В ROS 2 есть готовый исполняемый файл `static_transform_publisher` из пакета `tf2_ros`.

Тот же самый фрейм можно опубликовать одной командой:

**С использованием углов Эйлера (yaw/pitch/roll в радианах):**
```bash
ros2 run tf2_ros static_transform_publisher --x 0 --y 0 --z 1 --yaw 0 --pitch 0 --roll 0 --frame-id world --child-frame-id mystaticturtle
```

**С использованием кватерниона:**
```bash
ros2 run tf2_ros static_transform_publisher --x 0 --y 0 --z 1 --qx 0 --qy 0 --qz 0 --qw 1 --frame-id world --child-frame-id mystaticturtle
```

Этот инструмент идеально подходит для быстрого тестирования и использования в launch-файлах.

### **Пример использования в launch-файле (Python)**
```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=['--x', '0', '--y', '0', '--z', '1',
                       '--yaw', '0', '--pitch', '0', '--roll', '0',
                       '--frame-id', 'world', '--child-frame-id', 'mystaticturtle']
        )
    ])
```

---

## 📝 **Ключевые выводы**
✅ **Статические трансформации** описывают неизменяемые связи между фреймами (например, крепление датчика).
✅ Для их публикации используется специальный класс **`StaticTransformBroadcaster`**.
✅ Трансформация публикуется **один раз** при запуске узла.
✅ В реальных проектах используйте готовый инструмент **`static_transform_publisher`** из пакета `tf2_ros`.
✅ Статические трансформации публикуются в топик **`/tf_static`**, в отличие от динамических (которые идут в `/tf`).

---

## 🎮 **Практическое задание**
1. С помощью готового инструмента `static_transform_publisher` опубликуйте трансформацию для вымышленной линзы камеры, которая находится в 5 см справа (`x=0.05`), в 10 см впереди (`y=0.1`) базового фрейма `base_link` и повёрнута на 90 градусов вокруг оси X (`roll=1.57`). Назовите дочерний фрейм `camera_lens`.
2. Проверьте результат командой `ros2 topic echo /tf_static`.
3. Напишите свой собственный launch-файл, который запускает публикацию трёх разных статических фреймов одновременно.

---

## 🔜 **Что дальше?**
Теперь, когда вы умеете публиковать статические фреймы, следующим шагом будет написание **dynamic broadcaster (вещателя динамических фреймов)** для движущихся частей робота, а затем **listener (слушателя)**, чтобы использовать эти данные для управления. Это приблизит вас к созданию собственной демонстрации с преследующими друг друга черепахами!