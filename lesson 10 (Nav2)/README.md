# Урок 9. Nav2

Цель урока - запустить автономную навигацию мобильного робота: построить карту, локализоваться на ней через AMCL и отправить робота в целевую точку средствами навигационного стека Nav2.

## Порядок прохождения

| Шаг | Статья | Результат |
|---:|---|---|
| 1 | [Знакомство с Nav2](introducing_nav2.md) | Понятны серверы Nav2, обязательные tf-фреймы `map -> odom -> base_link` и lifecycle-ноды; Nav2 установлен |
| 2 | [Costmap: как Nav2 видит препятствия](nav2_costmaps.md) | Понятны глобальная и локальная costmap и их слои |
| 3 | [Карта и локализация AMCL](nav2_localization.md) | Построена и сохранена карта `map.pgm` + `map.yaml`; понятен принцип работы AMCL |
| 4 | [Запуск Nav2 в симуляции TurtleBot3](nav2_turtlebot3_sim.md) | Робот автономно доезжает до цели из RViz2 и через действие `NavigateToPose` |

## Предварительные требования

Перед этим уроком должны быть пройдены:

- [Урок 3](<../lesson 3 (actions and services)/README.md>) - серверы Nav2 принимают цели как действия.
- [Урок 7](<../lesson 7 (TF2)/README.md>) - навигация построена на дереве tf-фреймов.
- [Урок 10](<../lesson 11 (turtlebot3 sim)/README.md>) - практика выполняется в симуляции TurtleBot3.

## Внешние источники

- [Nav2 Documentation](https://docs.nav2.org/)
- [TurtleBot3 SLAM Simulation](https://emanual.robotis.com/docs/en/platform/turtlebot3/slam_simulation/)
- [TurtleBot3 Navigation Simulation](https://emanual.robotis.com/docs/en/platform/turtlebot3/nav_simulation/)
- [REP-105: Coordinate Frames for Mobile Platforms](https://www.ros.org/reps/rep-0105.html)

## После урока

Переходите к [уроку 11](<../lesson 12 (micro-ros)/README.md>): micro-ROS и микроконтроллеры.
