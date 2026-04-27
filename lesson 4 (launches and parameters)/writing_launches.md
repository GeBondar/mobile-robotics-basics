# Создание launch-файла в ROS 2 Jazzy для запуска turtlesim и связанных нод

## Введение

В предыдущих уроках вы запускали симулятор Turtlesim, action-сервер, action-клиент и публикатор координат отдельными командами в разных терминалах:

```bash
# Терминал 1
ros2 run turtlesim turtlesim_node

# Терминал 2
ros2 run my_turtle_controller turtle_action_server

# Терминал 3
ros2 run my_turtle_controller turtle_action_client

# Терминал 4
ros2 run my_turtle_controller number_publisher
```

Кроме того, иногда нужно было вручную вызывать сервисы (`ros2 service call ...`). Когда компонентов становится много, такой подход неудобен:

- нужно помнить порядок запуска;
- приходится открывать много окон и в каждом активировать рабочее пространство (`source install/setup.bash`);
- легко ошибиться и запустить не ту ноду.

Для таких сценариев в ROS 2 используются **launch-файлы**: они позволяют одной командой поднять несколько нод с нужными параметрами.

## Что такое launch-файл?

Launch-файл — это скрипт (обычно на Python с расширением `.launch.py`), который описывает, какие ноды, в каком порядке и с какими параметрами нужно запустить. В ROS 2 поддерживаются Python, XML и YAML; в этом курсе основной формат — Python, потому что он удобен для учебных примеров и сложной логики:

- можно использовать условные операторы (`if`/`else`) и циклы;
- легко работать с переменными окружения;
- можно подключать любые библиотеки Python для сложной логики.

В этом туториале мы создадим launch-файл, который одновременно запустит все четыре компонента, необходимые для работы с черепашкой.

## 1. Создание пакета для launch-файлов

Launch-файлы обычно хранят либо в том же пакете, где находятся ноды, либо выделяют в отдельный пакет (например, `my_project_start`). Второй вариант удобнее, если у вас много нод из разных пакетов — так проще управлять запуском всего проекта.

Перейдите в директорию `src` вашего рабочего пространства ROS 2 (например, `~/ros2_ws/src`) и создайте новый пакет с типом сборки `ament_python`:

```bash
cd ~/ros2_ws/src
ros2 pkg create --build-type ament_python my_project_start
```

После выполнения появится структура:

```
my_project_start/
├── my_project_start
│   └── __init__.py
├── package.xml
├── resource
│   └── my_project_start
├── setup.cfg
├── setup.py
└── test
    ├── test_copyright.py
    ├── test_flake8.py
    └── test_pep257.py
```

## 2. Создание папки launch и первого launch-файла

Перейдите в созданный пакет и создайте внутри него папку `launch`. В этой папке будут лежать все `.launch.py` файлы.

```bash
cd my_project_start
mkdir launch
touch launch/start.launch.py
chmod +x launch/start.launch.py   # необязательно, но полезно
```

## 3. Написание launch-файла

Откройте файл `launch/start.launch.py` в любом редакторе и добавьте следующий код:

```python
#!/usr/bin/env python3

from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    # Нода симулятора Turtlesim
    turtlesim_node = Node(
        package='turtlesim',
        executable='turtlesim_node',
        name='turtlesim'
    )

    # Action-сервер управления черепашкой
    action_server_node = Node(
        package='my_turtle_controller',
        executable='turtle_action_server',
        name='turtle_action_server'
    )

    # Action-клиент
    action_client_node = Node(
        package='my_turtle_controller',
        executable='turtle_action_client',
        name='turtle_action_client'
    )

    # Публикатор координат (number_publisher)
    number_publisher_node = Node(
        package='my_turtle_controller',
        executable='number_publisher',
        name='number_publisher'
    )

    return LaunchDescription([
        turtlesim_node,
        action_server_node,
        action_client_node,
        number_publisher_node
    ])
```

**Пояснения**:

- `generate_launch_description()` — обязательная функция, которая возвращает объект `LaunchDescription`.
- Для каждой ноды мы создаём экземпляр класса `Node`, указывая:
  - `package` — имя пакета, где находится исполняемый файл ноды;
  - `executable` — имя исполняемого файла (то, что идёт после `ros2 run`);
  - `name` — опциональное имя ноды в системе (если не задать, будет использоваться имя из кода).
- Все созданные ноды передаются в `LaunchDescription` списком.

## 4. Настройка setup.py

Чтобы ROS 2 мог найти наш launch-файл при вызове `ros2 launch`, нужно добавить информацию о нём в файл `setup.py` пакета `my_project_start`.

Откройте `setup.py` и внесите следующие изменения:

1. Добавьте импорты в начале файла (если их ещё нет):
   ```python
   import os
   from glob import glob
   ```

2. Найдите список `data_files` и дополните его, чтобы launch-файлы копировались в нужное место при установке пакета:
   ```python
   data_files=[
       # Указываем, что launch-файлы из папки launch должны быть установлены
       (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
       (os.path.join('share', package_name), ['package.xml']),
   ],
   ```

3. Уберите (или закомментируйте) строку `tests_require` — в шаблоне она может присутствовать, но для простого пакета с launch-файлами не нужна. Секция `tests_require` обычно выглядит так:
   ```python
   tests_require=['pytest'],
   ```
   Её можно удалить, чтобы избежать лишних зависимостей при сборке.

После изменений ваш `setup.py` должен выглядеть примерно так:

```python
import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'my_project_start'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name), ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='your_name',
    maintainer_email='your_email@example.com',
    description='Launch files for turtle project',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
        ],
    },
)
```

## 5. Сборка пакета

Перейдите в корень рабочего пространства (`~/ros2_ws`) и выполните сборку, указав наш пакет:

```bash
cd ~/ros2_ws
colcon build --packages-select my_project_start
```

После успешной сборки не забудьте обновить окружение:

```bash
source install/setup.bash
```

## 6. Запуск проекта через launch-файл

Теперь можно одной командой запустить все четыре ноды:

```bash
ros2 launch my_project_start start.launch.py
```

Вы должны увидеть:
- окно с симулятором черепашки;
- в терминале, где запущена команда, будут отображаться логи всех нод.

Если какая-то нода не запускается, проверьте:
- правильно ли указаны имена пакетов и исполняемых файлов;
- собран ли пакет `my_turtle_controller`;
- активировано ли рабочее пространство (`source install/setup.bash`).

## Заключение

Мы создали простой launch-файл, который одновременно запускает все необходимые компоненты для проекта с черепашкой. Это удобно, экономит время и уменьшает вероятность ошибок.

**Что дальше?**

- В launch-файл можно добавлять аргументы командной строки, условные запуски, включать другие launch-файлы.
- Можно задавать параметры для нод (например, переопределить `turtlesim` background color через параметры).
- Для сложных проектов launch-файлы можно организовывать иерархически.
