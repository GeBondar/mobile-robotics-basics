# Одна находка детектора в кадре камеры робота.
std_msgs/Header header
string label          # "aruco_3", "red", ...
float32 bearing       # рад, + влево от оптической оси (как yaw в ROS)
float32 elevation     # рад, + вверх
float32 distance      # м, оценка по известному размеру; < 0 — неизвестна
float32 size_px       # видимый размер, пиксели
float32 u             # центр в пикселях
float32 v
