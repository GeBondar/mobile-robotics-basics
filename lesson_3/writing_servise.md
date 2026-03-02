# **Создание своего сервиса для получения координат черепашки в ROS 2**

## 🎯 **Цель**
Создать собственный сервис в ROS 2, который позволит получать текущие координаты черепашки из симулятора turtlesim. Вы научитесь описывать тип сервиса, реализовывать сервер и клиент на Python, а также комбинировать топики и сервисы в одном узле.

---

## 📋 **Что мы будем делать**
1. Создадим два ROS 2 пакета:
   - `turtle_pose_interfaces` — пакет типа `ament_cmake` для определения типа сервиса `GetPose.srv`.
   - `turtle_pose_service` — пакет типа `ament_python` для Python-узлов (сервер и клиент).
2. Опишем свой тип сервиса `GetPose.srv` (запрос пустой, ответ содержит x, y, theta).
3. Напишем **сервер**, который:
   - подписывается на топик `/turtle1/pose`;
   - хранит последнее полученное положение;
   - по запросу клиента возвращает сохранённые координаты.
4. Напишем **клиента**, который вызывает этот сервис и выводит результат.
5. Соберём пакет и проверим работу.

> ⚠️ **Почему два пакета?**
> В ROS 2 определения сообщений и сервисов (.srv, .msg, .action) должны компилироваться отдельным пакетом типа `ament_cmake` с помощью `rosidl_default_generators`. Пакет типа `ament_python` не умеет генерировать интерфейсы. Поэтому стандартная практика — выносить интерфейсы в отдельный пакет.

---

## 🚀 **Шаг 1: Создание рабочего пространства и пакета**

### **1.1 Создаём рабочее пространство (если ещё нет)**
```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
```

### **1.2 Создаём пакет для интерфейсов**
```bash
cd ~/ros2_ws/src
ros2 pkg create turtle_pose_interfaces \
  --build-type ament_cmake
```

### **1.3 Создаём Python пакет с необходимыми зависимостями**
```bash
cd ~/ros2_ws/src
ros2 pkg create turtle_pose_service \
  --build-type ament_python \
  --dependencies rclpy turtlesim turtle_pose_interfaces
```

- `rclpy` — клиентская библиотека Python.
- `turtlesim` — для работы с черепашкой (тип `Pose`).
- `turtle_pose_interfaces` — наш пакет с определением сервиса.

### **1.4 Структура пакетов**
После создания у вас должна получиться следующая структура:

```
ros2_ws/
└── src/
    ├── turtle_pose_interfaces/
    │   ├── CMakeLists.txt
    │   ├── package.xml
    │   └── srv/
    │       └── GetPose.srv
    └── turtle_pose_service/
        ├── package.xml
        ├── setup.py
        ├── setup.cfg
        ├── resource/
        │   └── turtle_pose_service
        └── turtle_pose_service/
            ├── __init__.py
            ├── pose_server.py
            └── pose_client.py
```

Создадим папку `srv` в пакете интерфейсов:

```bash
mkdir ~/ros2_ws/src/turtle_pose_interfaces/srv
```

---

## 📄 **Шаг 2: Определение своего типа сервиса**

### **2.1 Создаём файл `GetPose.srv`**
```bash
touch ~/ros2_ws/src/turtle_pose_interfaces/srv/GetPose.srv
```

### **2.2 Редактируем `srv/GetPose.srv`**
Откройте файл в любом редакторе и добавьте:
```text
---
float32 x
float32 y
float32 theta
```
Здесь до `---` находится запрос (пустой), после – ответ (поля `x`, `y`, `theta`).

### **2.3 Настраиваем `CMakeLists.txt` пакета интерфейсов**
Откройте `~/ros2_ws/src/turtle_pose_interfaces/CMakeLists.txt` и приведите его к следующему виду:
```cmake
cmake_minimum_required(VERSION 3.8)
project(turtle_pose_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/GetPose.srv"
)

ament_package()
```

### **2.4 Настраиваем `package.xml` пакета интерфейсов**
Откройте `~/ros2_ws/src/turtle_pose_interfaces/package.xml` и приведите его к следующему виду:
```xml
<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>turtle_pose_interfaces</name>
  <version>0.0.0</version>
  <description>Custom service interfaces for turtle_pose_service</description>
  <maintainer email="your@email.com">your_name</maintainer>
  <license>Apache-2.0</license>

  <buildtool_depend>ament_cmake</buildtool_depend>
  <buildtool_depend>rosidl_default_generators</buildtool_depend>

  <exec_depend>rosidl_default_runtime</exec_depend>

  <member_of_group>rosidl_interface_packages</member_of_group>

  <export>
    <build_type>ament_cmake</build_type>
  </export>
</package>
```

> ⚠️ **Важно:** `rosidl_default_generators` указывается именно как `buildtool_depend`, а не `depend`. Это инструмент сборки, который не нужен во время выполнения.

---

## 🐍 **Шаг 3: Написание сервера**

### **3.1 Создаём файл `pose_server.py`**
```bash
cd ~/ros2_ws/src/turtle_pose_service/turtle_pose_service
touch pose_server.py
chmod +x pose_server.py
```

### **3.2 Код сервера**
```python
#!/usr/bin/env python3
"""
Сервер, предоставляющий сервис GetPose.
Подписывается на /turtle1/pose и хранит последнее положение.
"""

import rclpy
from rclpy.node import Node
from turtlesim.msg import Pose
from turtle_pose_interfaces.srv import GetPose  # сгенерированный тип сервиса

class PoseServer(Node):
    def __init__(self):
        super().__init__('pose_server')
        # Подписка на топик с положением черепашки
        self.subscription = self.create_subscription(
            Pose,
            '/turtle1/pose',
            self.pose_callback,
            10)
        self.current_pose = None  # здесь будем хранить последнее положение

        # Создаём сервис
        self.srv = self.create_service(GetPose, 'get_pose', self.get_pose_callback)
        self.get_logger().info('Сервер готов. Жду запросов на /get_pose')

    def pose_callback(self, msg):
        """Сохраняем полученное положение"""
        self.current_pose = msg
        self.get_logger().debug(f'Получена позиция: x={msg.x:.2f}, y={msg.y:.2f}', throttle_duration_sec=2)

    def get_pose_callback(self, request, response):
        """Обработчик запроса сервиса: заполняет ответ последними данными"""
        if self.current_pose is None:
            self.get_logger().warn('Запрос получен, но позиция ещё неизвестна')
            # Можно вернуть нули или вызвать исключение, но для примера просто вернём 0
            response.x = 0.0
            response.y = 0.0
            response.theta = 0.0
        else:
            response.x = self.current_pose.x
            response.y = self.current_pose.y
            response.theta = self.current_pose.theta
            self.get_logger().info(f'Отправлен ответ: x={response.x:.2f}, y={response.y:.2f}')
        return response

def main(args=None):
    rclpy.init(args=args)
    node = PoseServer()
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

### **3.3 Что здесь происходит**
- Узел подписывается на топик `/turtle1/pose` и в коллбэке `pose_callback` сохраняет последнее сообщение в `self.current_pose`.
- Сервис `get_pose` типа `GetPose` создаётся вызовом `create_service`. Его обработчик `get_pose_callback` заполняет поля ответа из сохранённой позиции.
- Если черепашка ещё не прислала ни одного сообщения, сервис вернёт нули (можно было бы отказаться отвечать, но для простоты так).

---

## 🐍 **Шаг 4: Написание клиента**

### **4.1 Создаём файл `pose_client.py`**
```bash
cd ~/ros2_ws/src/turtle_pose_service/turtle_pose_service
touch pose_client.py
chmod +x pose_client.py
```

### **4.2 Код клиента**
```python
#!/usr/bin/env python3
"""
Клиент для вызова сервиса get_pose.
"""

import sys
import rclpy
from rclpy.node import Node
from turtle_pose_interfaces.srv import GetPose

class PoseClient(Node):
    def __init__(self):
        super().__init__('pose_client')
        self.cli = self.create_client(GetPose, 'get_pose')
        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Сервис /get_pose не доступен, ждём...')
        self.req = GetPose.Request()

    def send_request(self):
        """Отправляет запрос и возвращает ответ"""
        self.future = self.cli.call_async(self.req)
        rclpy.spin_until_future_complete(self, self.future)
        return self.future.result()

def main(args=None):
    rclpy.init(args=args)

    client = PoseClient()
    response = client.send_request()
    client.get_logger().info(f'Текущая позиция черепашки: x={response.x:.2f}, y={response.y:.2f}, theta={response.theta:.2f}')

    client.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

### **4.3 Пояснения**
- Клиент ждёт появления сервиса `get_pose`.
- Отправляет асинхронный запрос и дожидается ответа.
- Выводит полученные координаты.

---

## 📦 **Шаг 5: Настройка entry points и сборка**

### **5.1 Редактируем `setup.py`**
Откройте `~/ros2_ws/src/turtle_pose_service/setup.py` и добавьте в `entry_points`:
```python
    entry_points={
        'console_scripts': [
            'pose_server = turtle_pose_service.pose_server:main',
            'pose_client = turtle_pose_service.pose_client:main',
        ],
    },
```

### **5.2 Проверяем `package.xml` пакета `turtle_pose_service`**
Убедитесь, что в `package.xml` есть зависимость на `turtle_pose_interfaces` и **нет** лишних зависимостей `rosidl_default_generators` (они нужны только в пакете интерфейсов):
```xml
<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>turtle_pose_service</name>
  <version>0.0.0</version>
  <description>Turtle pose service server and client</description>
  <maintainer email="your@email.com">your_name</maintainer>
  <license>Apache-2.0</license>

  <depend>rclpy</depend>
  <depend>turtlesim</depend>
  <depend>turtle_pose_interfaces</depend>

  <test_depend>ament_copyright</test_depend>
  <test_depend>ament_flake8</test_depend>
  <test_depend>ament_pep257</test_depend>
  <test_depend>python3-pytest</test_depend>

  <export>
    <build_type>ament_python</build_type>
  </export>
</package>
```

### **5.3 Сборка пакетов**
Сначала соберём пакет интерфейсов, затем пакет с узлами:
```bash
cd ~/ros2_ws

# Сборка пакета интерфейсов
colcon build --packages-select turtle_pose_interfaces

# Подключаем результаты сборки, чтобы turtle_pose_service нашёл интерфейсы
source install/setup.bash

# Сборка пакета с узлами
colcon build --packages-select turtle_pose_service
```

---

## 🔨 **Шаг 6: Запуск и проверка**

### **6.1 Запускаем turtlesim (терминал №1)**
```bash
source ~/ros2_ws/install/setup.bash
ros2 run turtlesim turtlesim_node
```

### **6.2 Запускаем сервер (терминал №2)**
```bash
source ~/ros2_ws/install/setup.bash
ros2 run turtle_pose_service pose_server
```
Должно появиться сообщение:
```
[INFO] [...] [pose_server]: Сервер готов. Жду запросов на /get_pose
```

### **6.3 Запускаем клиента (терминал №3)**
```bash
source ~/ros2_ws/install/setup.bash
ros2 run turtle_pose_service pose_client
```

Вы увидите вывод с координатами черепашки, например:
```
[INFO] [1740078123.123456] [pose_client]: Текущая позиция черепашки: x=5.54, y=5.54, theta=0.00
```

### **6.4 Проверяем список сервисов**
```bash
ros2 service list
```
Должен присутствовать `/get_pose`.

### **6.5 Вызов сервиса из командной строки**
```bash
ros2 service call /get_pose turtle_pose_interfaces/srv/GetPose "{}"
```
Ответ придёт в виде структуры с координатами:
```
waiting for service to become available...
requester: making request: turtle_pose_interfaces.srv.GetPose_Request()

response:
turtle_pose_interfaces.srv.GetPose_Response(x=5.544444561004639, y=5.544444561004639, theta=0.0)
```

---

## 🎮 **Шаг 7: Дополнительные упражнения**

### **Упражнение 1: Сервис случайной телепортации**
Создайте новый сервис `RandomTeleport.srv` (запрос пустой, ответ — новые координаты). Сервер должен генерировать случайные координаты в пределах окна turtlesim (от 0 до 11) и вызывать стандартный сервис `/turtle1/teleport_absolute`, чтобы переместить черепашку. Клиент вызывает этот сервис и сообщает, куда переместилась черепашка.

**Подсказка:** внутри сервера используйте клиент для вызова `/turtle1/teleport_absolute`.

### **Упражнение 2: Многосервисный узел**
Объедините оба сервиса (`GetPose` и `RandomTeleport`) в одном узле. Проверьте их работу.

### **Упражнение 3: Обработка ошибок**
Модифицируйте клиента `pose_client` так, чтобы он повторял запрос каждые 2 секунды и выводил изменения координат.

---

## 🧹 **Шаг 8: Очистка**
Не забудьте остановить все узлы нажатием **Ctrl+C** в каждом терминале.

---

## 📚 **Ключевые концепции, которые вы освоили**

✅ **Создание собственного типа сервиса (файл .srv)**  
✅ **Разделение интерфейсов и логики узлов на два пакета**  
✅ **Генерация кода сервиса при сборке пакета (`ament_cmake` + `rosidl`)**  
✅ **Реализация сервера сервиса с доступом к данным из топика**  
✅ **Реализация клиента для вызова сервиса**  
✅ **Комбинирование подписки на топики и предоставления сервисов**  
✅ **Запуск и отладка сервисов в ROS 2**

---

## 🔜 **Что дальше?**

1. **Использование действий (actions)** для длительных задач (например, движение к цели).
2. **Работа с параметрами узла** для настройки поведения без перекомпиляции.
3. **Создание более сложных сервисов** с непустыми запросами (например, задание целевой позиции).
4. **Интеграция сервисов в большие проекты** с несколькими узлами.