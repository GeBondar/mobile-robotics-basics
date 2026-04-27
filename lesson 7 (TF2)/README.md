# Урок 7. tf2

Цель урока - научиться публиковать и использовать координатные трансформации между фреймами робота. Все практические Python-ноды должны быть цельными файлами, пригодными для запуска через `ros2 run` или `ros2 launch`.

## Порядок прохождения

| Шаг | Статья | Результат |
|---:|---|---|
| 1 | [Знакомство с tf2](introducing_tf2.md) | Запущена демонстрация `turtle_tf2_py` |
| 2 | [Статический broadcaster](static_tf_broadcaster.md) | Опубликован фрейм в `/tf_static` |
| 3 | [Динамический broadcaster](dynamic_tf_broadcaster.md) | Поза `turtle1` публикуется в `/tf` |
| 4 | [Listener](writing_tf_listener.md) | `turtle2` следует за целевым фреймом |
| 5 | [Добавление нового фрейма](adding_tf_frame.md) | Добавлен фиксированный и динамический `carrot1` |

## Пакет в workspace

- `learning_tf2_py`

Готовые цельные версии нод находятся в [../ros2_ws/src/learning_tf2_py](<../ros2_ws/src/learning_tf2_py>).

## После урока

Переходите к [уроку 8](<../lesson 8 (Gazebo)/README.md>): симуляция в Gazebo.
