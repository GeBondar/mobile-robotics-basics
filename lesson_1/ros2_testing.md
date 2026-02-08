### Тестовая демонстрация

#### Пример 1: Обмен сообщениями

**Терминал 1** (издатель):

    source /opt/ros/humble/setup.bash
    ros2 run demo_nodes_cpp talker

**Терминал 2** (подписчик):

    source /opt/ros/humble/setup.bash
    ros2 run demo_nodes_py listener

Если установка успешна, в первом терминале будут появляться сообщения `"Hello World: X"`, а во втором - `"I heard: Hello World: X"`.

#### Пример 2: Turtlesim (графический пример)

**Терминал 1** - запуск симуляции:

    source /opt/ros/humble/setup.bash
    ros2 run turtlesim turtlesim_node

**Терминал 2** - управление черепахой:

    source /opt/ros/humble/setup.bash
    ros2 run turtlesim turtle_teleop_key

Управление: используйте стрелки на клавиатуре для перемещения черепахи.
