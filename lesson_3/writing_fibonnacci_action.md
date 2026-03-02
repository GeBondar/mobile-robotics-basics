### 📚 Создание своего action сервера в ROS 2 Jazzy: Полное руководство

Этот туториал проведет вас через весь процесс создания собственного action сервера в ROS 2 Jazzy. Вы узнаете, как определить пользовательский тип действия (action), реализовать сервер, который будет выполнять полезную работу (вычисление чисел Фибоначчи), и написать клиент для взаимодействия с ним.

#### Часть 1: Создание интерфейса действия (Action Interface)

Прежде чем писать сервер, нужно определить, как будет выглядеть ваше действие. Действие описывается в файлах `.action` и состоит из трех частей: цель (goal), результат (result) и обратная связь (feedback).

**1.1 Создание пакета интерфейсов**
Лучшей практикой является хранение интерфейсов (`.action`, `.msg`, `.srv`) в отдельном пакете. Создадим его:
```bash
cd ~/ros2_ws/src
ros2 pkg create --build-type ament_cmake --license Apache-2.0 custom_action_interfaces
```
Этот пакет создается как CMake пакет, так как требует кодогенерации, но созданные интерфейсы можно будет использовать как в C++, так и в Python узлах.

**1.2 Определение действия Fibonacci**
Внутри пакета создадим папку `action` и файл `Fibonacci.action`:
```bash
cd custom_action_interfaces
mkdir action
```
Теперь откройте файл `action/Fibonacci.action` и добавьте следующее содержимое:
```action
# Goal: Запрашиваемый порядок числа Фибоначчи
int32 order
---
# Result: Итоговая последовательность
int32[] sequence
---
# Feedback: Частичная последовательность (обратная связь во время выполнения)
int32[] partial_sequence
```
Три секции разделены символами `---`. Это определяет структуру сообщений для цели, результата и обратной связи.

**1.3 Сборка интерфейса**
Чтобы ROS могла использовать новое действие, нужно добавить несколько строк в файлы сборки пакета.

В `CMakeLists.txt` перед строкой `ament_package()` добавьте:
```cmake
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/Fibonacci.action"
)
```
В `package.xml` добавьте:
```xml
<buildtool_depend>rosidl_default_generators</buildtool_depend>

<member_of_group>rosidl_interface_packages</member_of_group>
```
Теперь соберите пакет:
```bash
cd ~/ros2_ws
colcon build --packages-select custom_action_interfaces
source install/setup.bash
```
Проверьте, что все прошло успешно:
```bash
ros2 interface show custom_action_interfaces/action/Fibonacci
```
Вы должны увидеть определенное вами действие.

#### Часть 2: Написание action сервера (Python)

Теперь, когда интерфейс готов, создадим сервер, который будет выполнять вычисления.

**2.1 Базовый сервер**
Создайте файл `fibonacci_action_server.py` в вашем домашнем каталоге (или в любом другом месте для теста). Начнем с минимальной структуры:
```python
import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node
from custom_action_interfaces.action import Fibonacci

class FibonacciActionServer(Node):

    def __init__(self):
        super().__init__('fibonacci_action_server')
        self._action_server = ActionServer(
            self,
            Fibonacci,
            'fibonacci',
            self.execute_callback)

    def execute_callback(self, goal_handle):
        self.get_logger().info('Executing goal...')
        # Здесь будет логика выполнения
        result = Fibonacci.Result()
        return result

def main(args=None):
    rclpy.init(args=args)
    fibonacci_action_server = FibonacciActionServer()
    rclpy.spin(fibonacci_action_server)

if __name__ == '__main__':
    main()
```
*   `ActionServer` создается с указанием узла (`self`), типа действия (`Fibonacci`), имени действия (`'fibonacci'`) и функции обратного вызова `execute_callback`, которая будет вызываться для каждой принятой цели.
*   `execute_callback` получает `goal_handle`, через который можно получить доступ к запросу (`goal_handle.request`), а также публиковать обратную связь и устанавливать статус завершения.

Запустите сервер:
```bash
python3 fibonacci_action_server.py
```
В другом терминале отправьте цель через CLI:
```bash
ros2 action send_goal fibonacci custom_action_interfaces/action/Fibonacci "{order: 5}"
```
Вы увидите сообщение "Executing goal...", но цель завершится с ошибкой, так как мы не указали статус. Исправим это, добавив `goal_handle.succeed()`:
```python
    def execute_callback(self, goal_handle):
        self.get_logger().info('Executing goal...')
        goal_handle.succeed() # Указываем, что цель выполнена успешно
        result = Fibonacci.Result()
        return result
```
Перезапустите сервер. Теперь цель должна завершаться со статусом `SUCCEEDED`.

**2.2 Добавление бизнес-логики**
Реализуем вычисление последовательности Фибоначчи и возврат результата:
```python
    def execute_callback(self, goal_handle):
        self.get_logger().info('Executing goal...')

        # Получаем порядок числа из запроса
        order = goal_handle.request.order

        sequence = [0, 1]

        for i in range(1, order):
            sequence.append(sequence[i] + sequence[i-1])

        goal_handle.succeed()

        result = Fibonacci.Result()
        result.sequence = sequence
        return result
```

**2.3 Публикация обратной связи (Feedback)**
Самое интересное в actions — возможность получать промежуточные результаты. Добавим публикацию частичных последовательностей с задержкой в 1 секунду для наглядности:
```python
import time # Добавить импорт в начале файла
# ... (остальные импорты)

    def execute_callback(self, goal_handle):
        self.get_logger().info('Executing goal...')

        feedback_msg = Fibonacci.Feedback()
        feedback_msg.partial_sequence = [0, 1]

        for i in range(1, goal_handle.request.order):
            feedback_msg.partial_sequence.append(
                feedback_msg.partial_sequence[i] + feedback_msg.partial_sequence[i-1])
            self.get_logger().info('Feedback: {0}'.format(feedback_msg.partial_sequence))
            goal_handle.publish_feedback(feedback_msg)
            time.sleep(1)

        goal_handle.succeed()

        result = Fibonacci.Result()
        result.sequence = feedback_msg.partial_sequence
        return result
```
Теперь, перезапустив сервер и отправив цель через CLI с флагом `--feedback`, вы увидите, как каждую секунду приходит обновление:
```bash
ros2 action send_goal --feedback fibonacci custom_action_interfaces/action/Fibonacci "{order: 5}"
```

#### Часть 3: Написание action клиента (Python)

Для полноты картины создадим клиент, который будет взаимодействовать с нашим сервером.

**3.1 Базовый клиент**
Создайте файл `fibonacci_action_client.py`:
```python
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from custom_action_interfaces.action import Fibonacci

class FibonacciActionClient(Node):

    def __init__(self):
        super().__init__('fibonacci_action_client')
        self._action_client = ActionClient(self, Fibonacci, 'fibonacci')

    def send_goal(self, order):
        goal_msg = Fibonacci.Goal()
        goal_msg.order = order

        self._action_client.wait_for_server()

        self._send_goal_future = self._action_client.send_goal_async(goal_msg)
        self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('Goal rejected :(')
            return

        self.get_logger().info('Goal accepted :)')

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        result = future.result().result
        self.get_logger().info('Result: {0}'.format(result.sequence))
        rclpy.shutdown()

def main(args=None):
    rclpy.init(args=args)
    action_client = FibonacciActionClient()
    action_client.send_goal(10)
    rclpy.spin(action_client)

if __name__ == '__main__':
    main()
```
*   `ActionClient` создается аналогично серверу.
*   `send_goal_async` возвращает future, который будет выполнен, когда сервер примет или отклонит цель. Мы добавляем callback `goal_response_callback` для обработки этого события.
*   Если цель принята, мы запрашиваем результат через `get_result_async` и добавляем callback `get_result_callback`, который будет вызван по завершении работы сервера.

**3.2 Запуск**
1.  Запустите сервер (из Части 2) в первом терминале.
2.  Запустите клиент во втором терминале:
    ```bash
    python3 fibonacci_action_client.py
    ```
Вы увидите, как сервер логирует обратную связь, а клиент по окончании выведет итоговую последовательность и завершится.

### ✅ Что дальше?
Теперь у вас есть рабочий пример action сервера и клиента. Вы можете развить его, добавив:
*   **Обработку отмены цели:** в сервере можно реализовать проверку `goal_handle.is_cancel_requested`.
*   **Более сложную логику:** интегрировать сервер в большой проект, заменить вычисление Фибоначчи на управление роботом или выполнение длительной задачи.
*   **Создать полноценный пакет:** перенести файлы Python в соответствующий пакет (`your_package/your_package`), добавить `entry_points` в `setup.py` и протестировать с помощью `ros2 run`.