# Урок 2. Workspace, ноды и топики

Цель урока - научиться ориентироваться в графе ROS 2, создавать workspace, собирать пакеты через `colcon`, писать первые ноды-публикаторы и ноды-подписчики, а также записывать данные через `ros2 bag`.

## Порядок прохождения

| Шаг | Статья | Результат |
|---:|---|---|
| 1 | [Workspace, colcon и первый пакет](workspace_colcon_package.md) | Создан `ros2_ws`, понятны `src`, `build`, `install`, `log` |
| 2 | [Понимание нод](understanding_nodes.md) | Понятны имена нод, запуск и introspection |
| 3 | [Понимание топиков](understanding_topics.md) | Понятны publish/subscribe и команды `ros2 topic` |
| 4 | [Публикатор для turtlesim](writing_talker.md) | Создана Python-нода, публикующая команды скорости |
| 5 | [Подписчик на pose turtlesim](writing_listener.md) | Создана Python-нода, читающая позицию черепахи |
| 6 | [rosdep и зависимости workspace](rosdep.md) | Зависимости пакетов устанавливаются по `package.xml` |
| 7 | [ros2 bag: запись и воспроизведение данных](ros2_bag.md) | Записан и воспроизведён топик `/turtle1/cmd_vel` |

## Пакеты в workspace

Практика урока соответствует пакетам:

- `my_turtle_controller`
- `my_turtle_subscriber`

Готовые версии находятся в [../ros2_ws/src](<../ros2_ws/src>).

## После урока

Переходите к [уроку 3](<../lesson 3 (actions and services)/README.md>): сервисы, действия и собственные интерфейсы.
