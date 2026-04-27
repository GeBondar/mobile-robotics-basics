# **Туториал по ROS 2: Используем URDF с robot_state_publisher (Python)**
*Учимся симулировать движение шагающего робота и визуализировать его в Rviz*

## Цель туториала
Создать полную симуляцию шагающего робота R2D2:
1.  Использовать готовую URDF-модель.
2.  Написать на Python ноду, которая будет симулировать движение робота и публиковать состояние его суставов (`JointState`).
3.  Подключить `robot_state_publisher`, который на основе URDF и `JointState` вычислит и опубликует все необходимые трансформации tf2.
4.  Визуализировать результат в Rviz.

---

## Зачем нужен robot_state_publisher?
В предыдущих туториалах мы использовали `robot_state_publisher` почти как "чёрный ящик", который просто брал URDF и каким-то образом показывал модель в Rviz. Пришло время понять, как он работает на самом деле.

**`robot_state_publisher`** — это стандартная нода ROS 2, которая выполняет две важные задачи:
1.  **Читает URDF-описание** робота (все линки и джойнты).
2.  **Подписывается на топик `/joint_states`**, где публикуются текущие положения всех нефиксированных суставов.
3.  **Вычисляет** для каждого линка его положение в пространстве, используя кинематическую цепочку, заданную в URDF.
4.  **Публикует** все эти трансформации в виде дерева tf2 (в топики `/tf` и `/tf_static`).

Таким образом, нам нужно лишь предоставить `robot_state_publisher`'у два источника данных: **статическую модель** (URDF) и **динамическое состояние** (JointState). Остальное он сделает сам.

---

## Предварительные требования
1.  Установлены все необходимые пакеты: `rclpy`, `robot_state_publisher`, `joint_state_publisher` (не обязателен, но полезен), `rviz2`, `urdf_tutorial_r2d2` (мы создадим его сами).
2.  Базовое понимание структуры URDF и работы с tf2.
3.  Умение создавать пакеты Python в ROS 2.

---

## Практическая часть: симулируем шагающего R2D2

### **1. Создание пакета**
Всю работу будем вести в новом рабочем пространстве (чтобы не смешивать с предыдущими). Создайте его и пакет:

```bash
mkdir -p ~/second_ros2_ws/src
cd ~/second_ros2_ws/src
ros2 pkg create --build-type ament_python --license Apache-2.0 urdf_tutorial_r2d2 --dependencies rclpy
cd urdf_tutorial_r2d2
```

### **2. Добавление URDF-модели и конфигурации Rviz**
Создайте папку для URDF-файлов и скачайте готовую модель R2D2 и конфиг для Rviz:

```bash
mkdir -p urdf
cd urdf
wget https://raw.githubusercontent.com/ros/urdf_tutorial/ros2/urdf/r2d2.urdf.xml
wget https://raw.githubusercontent.com/ros/urdf_tutorial/ros2/urdf/r2d2.rviz
cd ..
```

Если `wget` не работает, скачайте файлы вручную по ссылкам и поместите их в папку `urdf_tutorial_r2d2/urdf`.

### **3. Написание ноды-симулятора движения (`state_publisher.py`)**
Создадим ноду, которая симулирует движение робота и публикует состояния его суставов.

Создайте файл `~/second_ros2_ws/src/urdf_tutorial_r2d2/urdf_tutorial_r2d2/state_publisher.py` и откройте его в редакторе. Скопируйте туда следующий код:

```python
import math
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from geometry_msgs.msg import Quaternion
from sensor_msgs.msg import JointState
from tf2_ros import TransformBroadcaster, TransformStamped

class StatePublisher(Node):

    def __init__(self):
        super().__init__('state_publisher')

        # Настраиваем QoS (глубина очереди)
        qos_profile = QoSProfile(depth=10)

        # Издатель для топика /joint_states (сюда будем публиковать положения суставов)
        self.joint_pub = self.create_publisher(JointState, 'joint_states', qos_profile)

        # Broadcaster для трансформации одометрии (фрейм odom -> axis)
        self.broadcaster = TransformBroadcaster(self, qos=qos_profile)

        # Таймер, который будет вызывать функцию update 30 раз в секунду
        self.timer = self.create_timer(1.0/30.0, self.update)

        # Константа для перевода градусов в радианы
        self.degree = math.pi / 180.0

        # --- Переменные состояния робота (будем их менять в update) ---
        self.tilt = 0.0          # Наклон головы
        self.tilt_inc = self.degree  # Шаг изменения наклона
        self.swivel = 0.0        # Поворот башни
        self.angle = 0.0         # Угол движения по кругу
        self.height = 0.0        # Высота перископа
        self.height_inc = 0.005  # Шаг изменения высоты

        # --- Предварительная инициализация сообщений ---
        # Трансформация odom -> axis (базовое перемещение робота по кругу)
        self.odom_trans = TransformStamped()
        self.odom_trans.header.frame_id = 'odom'      # Родительский фрейм (мир)
        self.odom_trans.child_frame_id = 'axis'       # Дочерний фрейм (основание робота)

        # Сообщение для joint_states
        self.joint_state = JointState()

        self.get_logger().info("{0} started".format(self.get_name()))

    def update(self):
        """Функция, вызываемая по таймеру. Обновляет состояние и публикует данные."""
        now = self.get_clock().now()

        # --- 1. Заполняем JointState ---
        self.joint_state.header.stamp = now.to_msg()
        # Имена суставов (должны точно совпадать с именами в URDF!)
        self.joint_state.name = ['swivel', 'tilt', 'periscope']
        # Текущие положения этих суставов
        self.joint_state.position = [self.swivel, self.tilt, self.height]

        # --- 2. Заполняем трансформацию одометрии (движение робота по кругу) ---
        self.odom_trans.header.stamp = now.to_msg()
        # Робот движется по окружности радиусом 2 метра
        self.odom_trans.transform.translation.x = math.cos(self.angle) * 2.0
        self.odom_trans.transform.translation.y = math.sin(self.angle) * 2.0
        self.odom_trans.transform.translation.z = 0.7  # Высота основания над землёй
        # Поворот основания: смотрим по касательной к окружности
        self.odom_trans.transform.rotation = euler_to_quaternion(0, 0, self.angle + math.pi/2)

        # --- 3. Публикуем всё ---
        self.joint_pub.publish(self.joint_state)
        self.broadcaster.sendTransform(self.odom_trans)

        # --- 4. Обновляем состояние для следующего кадра ---
        # Наклон головы (качается вверх-вниз)
        self.tilt += self.tilt_inc
        if self.tilt < -0.5 or self.tilt > 0.0:
            self.tilt_inc *= -1

        # Высота перископа (поднимается и опускается)
        self.height += self.height_inc
        if self.height > 0.2 or self.height < 0.0:
            self.height_inc *= -1

        # Башня постоянно вращается
        self.swivel += self.degree

        # Угол движения по окружности увеличивается
        self.angle += self.degree / 4.0


def euler_to_quaternion(roll, pitch, yaw):
    """Вспомогательная функция для перевода углов Эйлера в кватернион."""
    qx = math.sin(roll/2) * math.cos(pitch/2) * math.cos(yaw/2) - math.cos(roll/2) * math.sin(pitch/2) * math.sin(yaw/2)
    qy = math.cos(roll/2) * math.sin(pitch/2) * math.cos(yaw/2) + math.sin(roll/2) * math.cos(pitch/2) * math.sin(yaw/2)
    qz = math.cos(roll/2) * math.cos(pitch/2) * math.sin(yaw/2) - math.sin(roll/2) * math.sin(pitch/2) * math.cos(yaw/2)
    qw = math.cos(roll/2) * math.cos(pitch/2) * math.cos(yaw/2) + math.sin(roll/2) * math.sin(pitch/2) * math.sin(yaw/2)
    return Quaternion(x=qx, y=qy, z=qz, w=qw)


def main():
    try:
        with rclpy.init():
            node = StatePublisher()
            rclpy.spin(node)
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
```

#### **3.1 Ключевые моменты кода**
*   **`JointState`**: Это стандартный тип сообщения `sensor_msgs/msg/JointState`. Он содержит массивы имён суставов и их положений. **Важно!** Имена суставов в этом сообщении должны **точно совпадать** с именами, заданными в URDF-файле.
*   **`TransformBroadcaster`**: Мы используем его, чтобы опубликовать трансформацию от фрейма `odom` (мир) к фрейму `axis` (основание робота). Это симулирует движение всего робота по кругу.
*   **Таймер `1/30`**: Обновление происходит 30 раз в секунду, что даёт плавную анимацию.
*   **Логика движения**: В функции `update` мы не только публикуем данные, но и обновляем внутренние переменные (`tilt`, `swivel`, `height`, `angle`), создавая иллюзию шагающего/движущегося робота.

### **4. Создание launch-файла**
Чтобы запустить всё вместе (и `robot_state_publisher`, и нашу ноду), создадим launch-файл.

Создайте папку `launch` и файл `demo_launch.py` внутри неё:

```bash
cd ~/second_ros2_ws/src/urdf_tutorial_r2d2
mkdir launch
cd launch
touch demo_launch.py
```

Теперь откройте `demo_launch.py` и вставьте следующий код:

```python
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import FileContent, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    # Определяем аргумент для использования симуляционного времени (по умолчанию false)
    use_sim_time = LaunchConfiguration('use_sim_time', default='false')

    # Загружаем содержимое URDF-файла как строку
    urdf = FileContent(
        PathJoinSubstitution([FindPackageShare('urdf_tutorial_r2d2'), 'urdf', 'r2d2.urdf.xml'])
    )

    return LaunchDescription([
        # Объявляем аргумент, чтобы его можно было переопределить при запуске
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use simulation (Gazebo) clock if true'
        ),

        # Нода robot_state_publisher
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{
                'use_sim_time': use_sim_time,
                'robot_description': urdf  # Передаём URDF как параметр
            }],
            # arguments=[urdf]  # Можно и так, но через параметры удобнее
        ),

        # Наша нода-симулятор движения
        Node(
            package='urdf_tutorial_r2d2',
            executable='state_publisher',  # Это имя мы зададим в setup.py
            name='state_publisher',
            output='screen'
        ),
    ])
```

### **5. Редактирование `setup.py`**
Теперь нужно настроить установку пакета, чтобы:
*   Файлы из папок `launch` и `urdf` были скопированы в нужное место.
*   Исполняемый файл `state_publisher` был зарегистрирован.

Откройте `~/second_ros2_ws/src/urdf_tutorial_r2d2/setup.py` и приведите его к следующему виду (я покажу только ключевые изменения):

```python
import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'urdf_tutorial_r2d2'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        # Включаем все файлы из launch и urdf в установку
        (os.path.join('share', package_name, 'launch'), glob('launch/*')),
        (os.path.join('share', package_name), glob('urdf/*')),
        # Остальные стандартные записи (package.xml, etc.)
        (os.path.join('share', package_name), ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ваше_имя',
    maintainer_email='ваш_email@example.com',
    description='URDF tutorial for R2D2 with robot_state_publisher',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # Регистрируем наш исполняемый файл
            'state_publisher = urdf_tutorial_r2d2.state_publisher:main',
        ],
    },
)
```

### **6. Сборка пакета**
Вернитесь в корень рабочего пространства и соберите пакет:

```bash
cd ~/second_ros2_ws
colcon build --symlink-install --packages-select urdf_tutorial_r2d2
source install/setup.bash
```

Флаг `--symlink-install` очень удобен при разработке на Python: он создаёт символические ссылки, и вам не нужно пересобирать пакет после каждого изменения кода.

### **7. Запуск и визуализация**
**Терминал 1:** Запустите наш launch-файл:
```bash
ros2 launch urdf_tutorial_r2d2 demo_launch.py
```

**Терминал 2:** Запустите Rviz с готовой конфигурацией:
```bash
rviz2 -d $(ros2 pkg prefix urdf_tutorial_r2d2 --share)/r2d2.rviz
```

Если команда `ros2 pkg prefix` не найдёт папку `share`, можно указать путь вручную или просто открыть Rviz и загрузить конфигурацию через меню `File -> Open Config`, найдя файл `r2d2.rviz` в вашем workspace.

В Rviz вы должны увидеть модель R2D2, которая:
*   Движется по кругу (трансформация `odom` -> `axis`).
*   Вращает башней (`swivel`).
*   Качает головой (`tilt`).
*   Поднимает и опускает перископ (`periscope`).

В результате получилась симуляция движущегося робота: `robot_state_publisher` строит дерево tf2, а собственная нода публикует `JointState`.

---

## Ключевые выводы
- **`robot_state_publisher`** — стандартная нода ROS 2, которая по URDF и текущим положениям суставов вычисляет и публикует все трансформации tf2.
- Для работы `robot_state_publisher` нужны:
    *   Параметр `robot_description` (содержимое URDF-файла).
    *   Данные в топике `/joint_states` (сообщения `sensor_msgs/msg/JointState`).
- **Имена суставов** в сообщениях `JointState` должны **точно совпадать** с именами, заданными в URDF.
- Можно публиковать не только состояния суставов, но и дополнительные трансформации (например, `odom` -> `base_footprint`), чтобы симулировать перемещение робота в пространстве.
- Разделение ответственности: наша нода отвечает за **симуляцию движения**, а `robot_state_publisher` — за **преобразование этого движения в дерево tf2**.

---

## Практическое задание
1.  **Измените траекторию движения.** В коде `state_publisher.py` найдите место, где задаётся движение по кругу (`cos(angle)*2`, `sin(angle)*2`). Измените траекторию на движение по эллипсу или по прямой с разворотом.
2.  **Добавьте новый сустав.** В URDF-файле `r2d2.urdf.xml` есть и другие суставы? Попробуйте добавить в нашу ноду публикацию положения для дополнительного сустава (например, для колёс). Вам нужно будет добавить его имя в массив `joint_state.name` и соответствующее значение в `joint_state.position`.
3.  **Используйте `joint_state_publisher_gui`.** Временно отключите ноду `state_publisher` (закомментируйте её в launch-файле) и вместо неё запустите `joint_state_publisher_gui` (пакет `joint_state_publisher`). Проверьте, что модель реагирует так же.

---

## Что дальше
Вы прошли полный цикл: от создания статической модели URDF до её оживления с помощью Xacro и `robot_state_publisher`. Теперь вы готовы к более серьёзным вещам:
*   **Симуляция в Gazebo.** Подключите эту модель к симулятору Gazebo, добавьте физику и сенсоры.
*   **Управление с реального джойстика.** Напишите ноду, которая будет преобразовывать команды с геймпада в положения суставов.
*   **Создание собственного робота.** Спроектируйте своего робота в URDF (или с помощью Xacro) и заставьте его двигаться.
