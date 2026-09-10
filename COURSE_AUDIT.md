# Аудит курса ROS 2 Jazzy/Humble

Дата проверки: 2026-04-27.

Проверено 31 markdown-файл курса: 30 статей в уроках и корневой `README.md`.

## 1. Ссылки

### Локальные ссылки

Найдено 22 нерабочие локальные ссылки или placeholder-ссылки.

| Файл | Строка | Проблема |
|---|---:|---|
| `README.md` | 29 | `lesson_1` не существует |
| `README.md` | 34 | `lesson_1/ros2_humble_install.md` не существует |
| `README.md` | 37 | `lesson_1/ros2_jazzy_install.md` не существует |
| `README.md` | 43 | `lesson_1/ros2_turtlesim.md` не существует |
| `README.md` | 58 | `lesson_1/ros2_rqt` не существует |
| `README.md` | 71 | `lesson_2` не существует |
| `README.md` | 75 | `lesson_2/understanding_nodes.md` не существует |
| `README.md` | 86 | `lesson_2/understanding_topics.md` не существует |
| `README.md` | 97 | `lesson_2/writing_talker.md` не существует |
| `README.md` | 108 | `lesson_2/writing_listener.md` не существует |
| `README.md` | 119 | `lesson_2/images` не существует |
| `lesson 2 (nodes and topics)/understanding_nodes.md` | 167 | placeholder `ссылка_на_туториал_по_топикам` |
| `lesson 7 (TF2)/adding_tf_frame.md` | 21-24 | placeholder `link_to_intro`, `link_to_static`, `link_to_dynamic`, `link_to_listener` |
| `lesson 7 (TF2)/dynamic_tf_broadcaster.md` | 18-19 | placeholder `link_to_intro_tutorial`, `link_to_static_broadcaster_tutorial` |
| `lesson 7 (TF2)/static_tf_broadcaster.md` | 19 | placeholder `ссылка_на_предыдущий_туториал` |
| `lesson 7 (TF2)/writing_tf_listener.md` | 5, 19-20 | placeholder `link_to_intro`, `link_to_static`, `link_to_dynamic` |

Главная причина: `README.md` использует старые короткие пути `lesson_1/...`, а реальные папки называются `lesson 1 (install ROS2 and testing)/...`.

### Внешние ссылки

Проверено 55 уникальных внешних URL. Явно проблемные:

| Файл | Строка | URL | Статус |
|---|---:|---|---|
| `lesson 5 (URDF and XACRO)/exporting_URDF.md` | 16 | `https://github.com/OVERCROSS-FreeCAD-Addons/RobotCAD` | 404; лучше заменить на `https://github.com/drfenixion/freecad.robotcad` или `https://github.com/galou/freecad.cross` |
| то же | 17 | `https://github.com/FreeCAD/freecad.cadquery_gazebo` | 404 |
| то же | 19 | `https://github.com/Adlink-ROS/urdf-fusion-sdf-exporter` | 404 |
| то же | 22 | `https://github.com/robcog-iai/ExportURDF` | 404 |
| то же | 42 | `http://wiki.ros.org/sdformat_to_urdf` | 404 |
| то же | 43 | `https://github.com/andreasBihlmaier/sdf2urdf` | 404 |
| то же | 46 | `https://docs.omniverse.nvidia.com/app_isaacsim/app_isaacsim/tutorial_import_urdf.html` | 403/устаревший путь; заменить на `https://docs.isaacsim.omniverse.nvidia.com/latest/importer_exporter/import_urdf.html` |
| то же | 47 | `https://github.com/dfki-ric/blender_robotics_tools` | 404 |
| то же | 61 | `https://gramaziokohler.github.io/urdf-viewer/` | 404 |
| то же | 61 | `https://github.com/gramaziokohler/urdf-viewer` | 404 |
| то же | 66 | `http://wiki.ros.org/sdformat_to_urdf/Tutorials/ViewSDFModelsInRviz` | 404 |
| то же | 68 | `https://github.com/robostudio/jupyterlab-ros` | 404 |

Требуют ручной проверки в обычном браузере:

- `https://wiki.freecad.org/RobotWorkbench` — доступ блокируется/путь выглядит устаревшим.
- `https://cad.onshape.com/documents/...` — похоже на несуществующий или приватный пример.
- `https://www.coppeliarobotics.com/helpFiles/en/urdfImportExport.htm` — проверка истекла по timeout.
- `https://www.roboforge.dev/` — automated fetch не прошел; поисковая выдача видит `https://roboforge.dev/`.

## 2. Покрытие тем ROS 2 tutorials

Курс хорошо покрывает:

- installation basics for Humble/Jazzy;
- turtlesim, rqt, nodes, topics, services, actions, parameters;
- Python publisher/subscriber, custom service, custom action;
- launch basics;
- URDF, Xacro, robot_state_publisher;
- RViz user guide;
- tf2 Python intro/static/dynamic/listener/adding frame;
- TurtleBot3/Gazebo intro.

Приоритетные пробелы относительно официального списка ROS 2 Jazzy tutorials:

| Приоритет | Тема | Официальный tutorial |
|---|---|---|
| P1 | Окружение ROS 2: `source`, underlay/overlay, `$ROS_DISTRO`, `$ROS_DOMAIN_ID` | `Configuring environment` |
| P1 | Workspace/package/colcon как отдельный базовый урок | `Using colcon`, `Creating a workspace`, `Creating a package` |
| P1 | `rqt_console` и уровни логирования | `Using rqt_console to view logs` |
| P1 | `ros2 bag`: запись/воспроизведение topics/services/actions | `Recording and playing back data` |
| P1 | `ros2doctor` для диагностики установки | `Using ros2doctor to identify issues` |
| P1 | `rosdep`: установка зависимостей workspace | `Managing Dependencies with rosdep` |
| P2 | Python parameters in a class | `Using parameters in a class (Python)` |
| P2 | Custom msg/srv/action interfaces как отдельная статья | `Creating custom msg and srv files`, `Implementing custom interfaces`, `Creating an action` |
| P2 | Launch substitutions/event handlers/large projects | `Using substitutions`, `Using event handlers`, `Managing large projects` |
| P2 | TF2 debugging, time travel, quaternion basics | `Debugging`, `Using time`, `Traveling in time`, `Quaternion fundamentals` |
| P2 | Testing: pytest, launch_testing, command line tests | `Testing` section |
| P2 | QoS, lifecycle nodes, composition | `Demos` and `Intermediate` sections |
| P3 | Security/SROS2 | `Security` section |
| P3 | Webots/MVSim/Foxglove/Docker/VSCode workflows | Advanced/How-to guides |

Предложение для следующего согласования: начать с P1-статей, потому что они нужны для воспроизводимости курса и проверки всех практических работ.

## 3. Стиль, орфография, следы AI-промптов

Прямых следов промптов ChatGPT/GPT/Claude/Copilot внутри markdown-файлов не найдено.

Явные орфографические/именовательные проблемы:

- `lesson 2 (nodes and topics)/understendibg topics.md` -> `understanding_topics.md`.
- `lesson 3 (actions and services)/writing_servise.md` -> `writing_service.md`.
- `lesson 3 (actions and services)/writing_fibonnacci_action.md` -> `writing_fibonacci_action.md`.
- `lesson 5 (URDF and XACRO)/phisical_and_collisions.md` -> `physical_and_collisions.md`.

Разнобой стиля:

- Смешаны `ROS2` и `ROS 2`; лучше везде `ROS 2`.
- Смешаны `нода`, `узел`, `node`; выбрать основной русский термин и английский давать в скобках при первом появлении.
- Смешаны `топик`, `тема`, `topic`; лучше `топик (topic)` или `тема (topic)`, но единообразно.
- Есть много дистрибутив-специфичных команд `humble`/`jazzy`/`rolling`. Для курса Jazzy с совместимостью Humble лучше писать шаблон через `$ROS_DISTRO`, а рядом давать примеры для Jazzy/Humble.
- Несколько статей ссылаются на `docs.ros.org/en/rolling/...`; для стабильного курса лучше заменить на `jazzy` и при необходимости добавить примечание по Humble.
- Встречаются разговорные маркеры: "Давайте", "магия", "волшебство", "Удачи", "Полное руководство", много emoji. Это не промпты, но создает ощущение сгенерированного текста и разный тон между статьями.
- Часть code snippets в TF2 содержит `...` и не является исполняемой как файл. В `ros2_ws/src/learning_tf2_py` я добавил цельные версии этих узлов.

## 4. `ros2_ws/src`

Создан единый workspace source tree:

- `ros2_ws/src/my_turtle_controller`
- `ros2_ws/src/my_turtle_subscriber`
- `ros2_ws/src/turtle_pose_interfaces`
- `ros2_ws/src/turtle_pose_service`
- `ros2_ws/src/turtle_action`
- `ros2_ws/src/custom_action_interfaces`
- `ros2_ws/src/fibonacci_action_py`
- `ros2_ws/src/my_project_start`
- `ros2_ws/src/urdf_tutorial`
- `ros2_ws/src/urdf_tutorial_r2d2`
- `ros2_ws/src/learning_tf2_py`

Локально без ROS проверено:

- Python syntax: OK, 41 файла.
- XML/package/URDF/Xacro parse: OK, 19 файлов.

Полный `colcon build` не запускался, потому что на машине не обнаружена установленная Linux-среда с ROS 2.

## 5. VM/локальная среда ROS 2

Проверка Windows-хоста:

- WSL установлен.
- Найден WSL-дистрибутив `Ubuntu-22.04`, состояние `Stopped`, WSL version `2`.
- Внутри `Ubuntu-22.04`: `Ubuntu 22.04.5 LTS`, ROS 2 не обнаружен, `/opt/ros` не показал установленных дистрибутивов.
- Ubuntu 24.04 / Jazzy environment не обнаружен.
- Docker CLI установлен: `C:\Program Files\Docker\Docker\resources\bin\docker.exe`, но Docker daemon сейчас недоступен.
- `VBoxManage` и `vagrant` в PATH не найдены.

Итог: текущая локальная среда не готова для проверки ROS 2 Jazzy tutorials. Для Jazzy нужен Ubuntu 24.04 (например WSL `Ubuntu-24.04`, VM Ubuntu 24.04 или Docker/Dev Container с Jazzy). Текущий `Ubuntu-22.04` подходит как база для Humble, но ROS 2 Humble тоже пока не установлен.

## 6. Рекомендуемые следующие правки

1. Исправить broken links в README и placeholder links в TF2/Nodes.
2. Привести все ссылки ROS docs к `jazzy`, а Humble давать как совместимость.
3. Переименовать markdown-файлы с опечатками и обновить ссылки на них.
4. Убрать/переписать неполные snippets с `...` в TF2-статьях.
5. Согласовать и написать P1-статьи: environment, colcon/workspace/package, rqt_console, rosbag2, ros2doctor, rosdep.
6. Поставить или подготовить Jazzy-среду: WSL Ubuntu 24.04 + ROS 2 Jazzy либо контейнер/VM.
