cmake_minimum_required(VERSION 3.8)
project(turtle_action)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(action_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(turtlesim REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/MoveTo.action"
  DEPENDENCIES action_msgs geometry_msgs turtlesim
)

install(PROGRAMS
  scripts/action_server.py
  scripts/action_client.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
