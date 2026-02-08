### Тестовая демонстрация

#### Пример 1: Обмен сообщениями

**Терминал 1** (издатель):

    source /opt/ros/humble/setup.bash
    ros2 run demo_nodes_cpp talker

**Терминал 2** (подписчик):

    source /opt/ros/humble/setup.bash
    ros2 run demo_nodes_py listener

Если установка успешна, в первом терминале будут появляться сообщения `"Hello World: X"`, а во втором - `"I heard: Hello World: X"`.

