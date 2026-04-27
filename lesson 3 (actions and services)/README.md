# Урок 3. Сервисы и действия

Цель урока - освоить два механизма request/response и long-running-задач в ROS 2: сервисы и действия. В практической части создаются собственные `.srv` и `.action` интерфейсы.

## Порядок прохождения

| Шаг | Статья | Результат |
|---:|---|---|
| 1 | [Понимание сервисов](understanding_services.md) | Понятны команды `ros2 service` и структура запроса/ответа |
| 2 | [Свой сервис GetPose](writing_service.md) | Созданы `turtle_pose_interfaces` и `turtle_pose_service` |
| 3 | [Понимание действий](understanding_actions.md) | Понятны goal, feedback, result и команды `ros2 action` |
| 4 | [Своё действие MoveTo](writing_action.md) | Создан пакет `turtle_action` |
| 5 | [Действие Fibonacci](writing_fibonacci_action.md) | Создан интерфейс `custom_action_interfaces/action/Fibonacci` |

## Пакеты в workspace

- `turtle_pose_interfaces`
- `turtle_pose_service`
- `turtle_action`
- `custom_action_interfaces`
- `fibonacci_action_py`

## После урока

Переходите к [уроку 4](<../lesson 4 (launches and parameters)/README.md>): параметры и launch-файлы.
