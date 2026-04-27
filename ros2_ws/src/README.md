# Workspace курса ROS 2

Папка `src` содержит пакеты, которые создаются в практических статьях курса. Их можно собрать и проверить как единый workspace.

Целевые дистрибутивы:

- ROS 2 Jazzy на Ubuntu 24.04
- ROS 2 Humble на Ubuntu 22.04, где имена пакетов и API совместимы

Сборка из `ros2_ws`:

```bash
source /opt/ros/$ROS_DISTRO/setup.bash
rosdep install -i --from-path src --rosdistro $ROS_DISTRO -y
colcon build --symlink-install
source install/setup.bash
```

Пакеты:

- `my_turtle_controller`: publisher/subscriber для `turtlesim` и entry points для launch-урока.
- `my_turtle_subscriber`: отдельный пакет subscriber из урока по чтению pose.
- `turtle_pose_interfaces`: интерфейс `GetPose.srv`.
- `turtle_pose_service`: сервер и клиент сервиса для запроса позы черепахи.
- `turtle_action`: action `MoveTo.action`, action-сервер и action-клиент.
- `custom_action_interfaces`: интерфейс `Fibonacci.action`.
- `fibonacci_action_py`: Python action-сервер и action-клиент Fibonacci.
- `my_project_start`: launch-пакет для запуска компонентов turtlesim-демо.
- `urdf_tutorial`: примеры URDF/Xacro и launch-файл для визуализации.
- `urdf_tutorial_r2d2`: пакет с примером `robot_state_publisher`.
- `learning_tf2_py`: статический и динамический broadcaster, listener и примеры дополнительных фреймов tf2.
