# Урок 5. URDF, Xacro и robot_state_publisher

Цель урока - описывать геометрию и кинематическую структуру робота, проверять модель в RViz2 и публиковать состояние суставов.

## Порядок прохождения

| Шаг | Статья | Результат |
|---:|---|---|
| 1 | [Визуальная модель URDF](understanding_URDF.md) | Созданы базовые link/joint модели |
| 2 | [Подвижная модель](movable_robot.md) | Использованы joint-типы `continuous`, `revolute`, `prismatic` |
| 3 | [Физические и collision-свойства](physical_and_collisions.md) | Добавлены `collision` и `inertial` |
| 4 | [Xacro](understanding_xacro.md) | URDF упрощён через свойства и макросы |
| 5 | [robot_state_publisher](writing_state_publisher.md) | Опубликованы `joint_states` и tf-трансформации |
| 6 | [Экспорт URDF](exporting_URDF.md) | Рассмотрены CAD/exporter инструменты |

## Пакеты в workspace

- `urdf_tutorial`
- `urdf_tutorial_r2d2`

## После урока

Переходите к [уроку 6](<../lesson 6 (RViz2 and rqt)/README.md>): визуализация и инспекция робототехнических данных.
