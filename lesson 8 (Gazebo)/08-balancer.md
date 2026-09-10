# Бонус: балансирующий робот (двухколёсный R2D2)

Цель: превратить четырёхколёсного R2D2 в двухколёсный балансирующий робот по принципу Segway. Это упражнение показывает как из физики выводится модель управления, и как теория оптимального управления (LQR) применяется на практике.

**Важно:** этот раздел опционален. Основная часть урока 8 заканчивается на предыдущей статье. Здесь — углублённое расширение для тех кому интересна динамика и теория управления.

Теоретическая база разобрана в двух документах:
- [physics_robotics.docx](./physics_robotics.docx) — вывод физики: моменты инерции, центр масс, уравнения движения маятника.
- [lqr_theory.docx](./lqr_theory.docx) — теория LQR: собственные числа, функция Ляпунова, уравнение Риккати.

## Идея балансира

Перевёрнутый маятник — классическая задача теории управления. Робот на двух колёсах естественно падает под действием гравитации. Контроллер должен двигать колёса так, чтобы база оставалась вертикальной — как человек балансирует на одной ноге, делая маленькие шаги.

```
        * ЦМ
        |
        |  l = 0.435 м
        |
    ===O===  ← ось колёс
```

Если ЦМ наклоняется на угол θ, контроллер должен ускорить базу так, чтобы создать встречный момент.

## Физика робота

Уравнение движения перевёрнутого маятника при малых углах (вывод из законов Ньютона — в `physics_robotics.docx`):

```
θ̈ = (g/l)·θ - (1/l)·u
```

где:
- θ — угол наклона относительно вертикали;
- g = 9.81 м/с²;
- l — высота ЦМ над осью колёс;
- u — ускорение базы (управление).

Первое слагаемое — гравитация валит робота. Второе — контроллер компенсирует через ускорение базы.

Полная модель в пространстве состояний:

```
x = [θ, θ̇, p, ṗ]ᵀ      ← состояние

ẋ = Ax + Bu              ← уравнение системы

A = [0,    1,   0,  0]   B = [0   ]
    [g/l,  0,   0,  0]       [-1/l]
    [0,    0,   0,  1]       [0   ]
    [0,    0,   0,  0]       [1   ]
```

## Изменения в URDF

Для балансира нужны три модификации:

### 1. Убрать задние колёса

В макросе `leg_assembly` оставляем только передние колёса:

```xml
<xacro:wheel side="${side}" position="front"
             parent="${side}_base" x_offset="0.0"/>
<!-- заднее колесо убираем -->
```

### 2. Поставить колёса под ЦМ

В `r2d2_properties.xacro`:

```xml
<!-- БЫЛО: колесо смещено от центра -->
<!-- <xacro:property name="wheel_offset_x" value="0.133"/> -->

<!-- СТАЛО: колесо под центром масс -->
<xacro:property name="wheel_offset_x" value="0.0"/>
```

Это критично — ЦМ должен быть прямо над осью колёс.

### 3. Collision и inertial у всех линков

Балансиру нужна полноценная физика. Макросы `cylinder_inertia`, `box_inertia`, `sphere_inertia` из статьи 3 применяем ко всем линкам.

## Расчёт высоты ЦМ из URDF

Параметр `l` — высота ЦМ над осью колёс — считается как взвешенное среднее высот всех линков. Подробнее в `physics_robotics.docx`, здесь только результат:

```python
import numpy as np

links = {
    'base_link':   {'z': 0.435, 'm': 5.0},
    'head':        {'z': 0.735, 'm': 1.0},
    'right_leg':   {'z': 0.685, 'm': 0.5},
    'left_leg':    {'z': 0.685, 'm': 0.5},
    'right_base':  {'z': 0.085, 'm': 0.3},
    'left_base':   {'z': 0.085, 'm': 0.3},
    'right_wheel': {'z': 0.0,   'm': 0.5},
    'left_wheel':  {'z': 0.0,   'm': 0.5},
}

m_total = sum(d['m'] for d in links.values())
l = sum(d['m'] * d['z'] for d in links.values()) / m_total
print(f"l = {l:.3f} м")  # l = 0.435 м
```

## LQR контроллер

LQR (Linear Quadratic Regulator) находит управление `u = -K·x`, которое минимизирует функцию стоимости:

```
J = ∫(xᵀQx + uᵀRu) dt
```

Q штрафует за отклонение состояния (большой угол — плохо), R штрафует за управление (большие ускорения — дорого). Оптимальное K находится через **уравнение Риккати** (вывод в `lqr_theory.docx`):

```
AᵀP + PA - PBR⁻¹BᵀP + Q = 0
```

Решив это уравнение, получаем матрицу P, из которой вычисляется K:

```
K = R⁻¹BᵀP
```

### Реализация LQR на Python

```python
import numpy as np
from scipy.linalg import solve_continuous_are

g = 9.81
l = 0.435

A = np.array([[0, 1, 0, 0],
              [g/l, 0, 0, 0],
              [0, 0, 0, 1],
              [0, 0, 0, 0]])
B = np.array([[0], [-1.0/l], [0], [1]])

# Матрицы весов — насколько штрафовать каждое состояние и управление
Q = np.diag([50.0, 5.0, 0.1, 2.0])  # [θ, θ̇, p, ṗ]
R = np.array([[5.0]])                 # штраф за ускорение

# Решаем уравнение Риккати
P = solve_continuous_are(A, B, Q, R)

# Вычисляем K
K = np.linalg.inv(R) @ B.T @ P
print(f"K = {K}")
```

### Как выбирать Q и R

Это единственное субъективное решение в LQR. Смысл диагональных элементов Q:

| Элемент | Состояние | Что означает большое значение |
|---------|-----------|-------------------------------|
| Q[0,0] | θ | Сильно штрафовать за наклон |
| Q[1,1] | θ̇ | Штрафовать за быстрое падение |
| Q[2,2] | p | Держать позицию |
| Q[3,3] | ṗ | Ограничивать скорость |

Большое R — контроллер экономит управление, реагирует мягче. Маленькое R — реагирует агрессивно.

## Pole placement — физически обоснованный выбор параметров

Подбирать Q и R вручную неудобно — непонятно как числа связаны с реальным поведением робота. Метод **pole placement** позволяет задать поведение напрямую через физику.

Идея: вместо Q и R задаём желаемые **полюса** замкнутой системы (собственные числа матрицы A-BK). Они определяют скорость и плавность реакции:

```
σ = N · ω₀          ← скорость затухания
ω = σ·√(1-ζ²)/ζ    ← частота колебаний
полюс = -σ ± ωi
```

Параметры имеют физический смысл:
- `ω₀ = √(g/l)` — естественная частота падения робота (для нашего робота ≈ 4.75 рад/с)
- `N` — во сколько раз контроллер быстрее естественного падения
- `ζ` — демпфирование: ζ=1 нет колебаний, ζ=0.7 небольшое перерегулирование

```python
from scipy.signal import place_poles

N = 0.8    # подобрано экспериментально
zeta = 0.9

w0 = np.sqrt(g / l)        # ≈ 4.75 рад/с
sigma = N * w0             # скорость затухания
omega = sigma * np.sqrt(1 - zeta**2) / zeta

poles = [
    -sigma + omega*1j,
    -sigma - omega*1j,
    -2 * w0,
    -1 * w0,
]

K = place_poles(A, B, poles).gain_matrix
print(f"K = {K}")
```

Время затухания можно предсказать:
```
t_settle = 4 / sigma ≈ 1.05 сек
```

Почему N=0.8 а не больше? При N≥1 контроллер становится агрессивным — из-за задержки интегратора скорости система теряет устойчивость. Это ограничение нашей упрощённой модели.

## ROS 2 нода контроллера

```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
import numpy as np
from scipy.linalg import solve_continuous_are
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist
from tf_transformations import euler_from_quaternion


def compute_gains(g, l):
    """LQR через уравнение Риккати."""
    A = np.array([[0, 1, 0, 0],
                  [g/l, 0, 0, 0],
                  [0, 0, 0, 1],
                  [0, 0, 0, 0]])
    B = np.array([[0], [-1.0/l], [0], [1]])
    Q = np.diag([50.0, 5.0, 0.1, 2.0])
    R = np.array([[5.0]])
    P = solve_continuous_are(A, B, Q, R)
    K = np.linalg.inv(R) @ B.T @ P
    return K


class BalanceController(Node):
    def __init__(self):
        super().__init__('balance_controller')
        self.g = 9.81
        self.l = 0.435
        self.K = compute_gains(self.g, self.l)
        self.get_logger().info(f'K = {self.K}')
        self.get_logger().info('Жду данные с IMU...')

        self.theta = 0.0
        self.theta_dot = 0.0
        self.pos = 0.0
        self.vel = 0.0
        self.vel_cmd = 0.0
        self.ang_desired = 0.0
        self.prev_time = None
        self.imu_ready = False
        self.odom_ready = False

        self.create_subscription(Imu, '/imu', self.imu_cb, 10)
        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)
        self.create_subscription(Twist, '/cmd_vel', self.cmd_cb, 10)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel_balanced', 10)
        self.create_timer(0.01, self.control_loop)

    def imu_cb(self, msg):
        q = msg.orientation
        _, self.theta, _ = euler_from_quaternion([q.x, q.y, q.z, q.w])
        self.theta_dot = msg.angular_velocity.y
        if not self.imu_ready:
            self.imu_ready = True
            self.get_logger().info('IMU готов!')

    def odom_cb(self, msg):
        self.pos = msg.pose.pose.position.x
        self.vel = msg.twist.twist.linear.x
        if not self.odom_ready:
            self.odom_ready = True
            self.get_logger().info('Odometry готова!')

    def cmd_cb(self, msg):
        self.ang_desired = msg.angular.z

    def control_loop(self):
        # Ждём пока придут данные с обоих топиков
        if not (self.imu_ready and self.odom_ready):
            return

        now = self.get_clock().now().nanoseconds * 1e-9
        x = np.array([self.theta, self.theta_dot, self.pos, self.vel])

        # u = -K·x — основная формула LQR
        accel = float(-(self.K @ x).item())
        accel = np.clip(accel, -5.0, 5.0)

        # Интегрируем ускорение в скорость
        # (diff-drive принимает скорость, а не ускорение)
        if self.prev_time is not None:
            dt = now - self.prev_time
            if dt > 0:
                self.vel_cmd += accel * dt
                self.vel_cmd = np.clip(self.vel_cmd, -1.0, 1.0)
        self.prev_time = now

        msg = Twist()
        msg.linear.x = float(self.vel_cmd)
        msg.angular.z = self.ang_desired
        self.cmd_pub.publish(msg)


def main():
    rclpy.init()
    node = BalanceController()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
```

## Launch файл балансира

Порядок запуска критичен — bridge должен быть готов до того как робот появился:

```python
return LaunchDescription([
    world_arg,
    gz_sim,
    rsp,
    TimerAction(period=2.0, actions=[bridge]),   # bridge первым
    TimerAction(period=3.0, actions=[spawn]),    # потом робот
    balance,                                      # стартует сразу, ждёт IMU сам
])
```

## Ограничения модели

Контроллер работает на приближении `sin θ ≈ θ`:

```
θ < 0.25 рад (14°) — погрешность ≈ 1%
θ < 0.5  рад (28°) — погрешность ≈ 5%
```

При больших углах модель теряет точность и робот не сможет восстановиться. В коде стоит защитный порог:

```python
if abs(self.theta) > 0.5:
    self.cmd_pub.publish(Twist())  # стоп
    return
```

## Возможные проблемы

**Робот падает сразу после спавна.** Контроллер не успел получить данные с IMU. Проверьте флаги `imu_ready` и `odom_ready` в логах.

**Робот балансирует но дрейфует в сторону.** ЦМ смещён по X — грипперы и декоративные элементы дают вес вперёд. Решение: добавить интегральную составляющую к контроллеру (см. `lqr_theory.docx`).

**Реакция слишком резкая, робот дёргается.** Уменьшите Q[0,0] или увеличьте R.

**Реакция слишком медленная, робот падает.** Увеличьте Q[0,0] или уменьшите R.

## Дальнейшее развитие

В этой статье — базовый LQR контроллер. Можно расширить:

- **Интегральная коррекция** — добавить `∫θ·dt` к управлению. Убирает дрейф от смещённого ЦМ.
- **Область Ляпунова** — формально определить безопасную зону через матрицу P. Разобрано в `lqr_theory.docx`.
- **Калман фильтр** — улучшить оценку угла θ из шумных данных IMU.

## Контрольные проверки

- После `ros2 launch ...` робот спавнится и не падает в течение минимум 10 секунд.
- `ros2 topic echo /imu --field orientation.y` показывает угол близкий к нулю (< 0.05 рад).
- При лёгком толчке робота он восстанавливает вертикаль за 1-2 секунды.

## Что читать дальше

- [physics_robotics.docx](./physics_robotics.docx) — вывод физики: моменты инерции, ЦМ, уравнения движения.
- [lqr_theory.docx](./lqr_theory.docx) — теория LQR от собственных чисел до уравнения Риккати.
- [TurtleBot3 simulation](<../lesson 11 (turtlebot3 sim)/README.md>) — аналог для сравнения.
