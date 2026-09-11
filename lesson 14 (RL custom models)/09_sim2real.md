# Перенос политики: на робота и в ROS 2

## Цель

После этой главы вы сможете назвать всё, что стоит между обученной политикой и работающим роботом,
выгрузить политику SB3 в ONNX так, чтобы она считала ровно то же самое, и обернуть её нодой ROS 2 с
честной частотой и сторожем. Главное умение — проверять перенос числом, а не словами «вроде едет».
Все числа замерены на машине курса (Python 3.12.3, 24 CPU, mujoco 3.9.0, gymnasium 1.0.0,
stable_baselines3 2.4.1, torch 2.6.0+cu124, onnxruntime 1.26.0); файлы экспорта писались вне
репозитория.

## 1. Единственное жёсткое правило

**Наблюдение на роботе обязано численно совпадать с наблюдением в среде**: те же величины, в том же
порядке, в тех же единицах, в тех же рамах, с той же частотой. Политика не умеет спросить, что ей
прислали, — она перемножит вектор на матрицы и выдаст действие при любом входе.

Цена нарушения замерена на готовой политике зависания
[track_c_drone/policies/hover](track_c_drone/policies/hover). Протокол — ровно тот, что в
`evaluate.py::eval_hover`: 20 эпизодов, `HoverEnv(seed=900)`, эпизоды 5000…5019, полная сложность.
Портим вход одним способом за раз:

| вариант входа | прожито шагов из 500 | доля доживших | финальная ошибка, м |
|---|---|---|---|
| как в среде (эталон) | 500.0 | 1.000 | 0.1667 |
| перепутаны блоки `R[:,0]` и `R[:,2]` | 55.4 | 0.000 | 1.9225 |
| `omega` в град/с вместо рад/с | 380.1 | 0.400 | 2.2159 |
| ось z вниз (NED вместо ENU) | 55.6 | 0.000 | 1.8302 |
| политика опрашивается на 25 Гц вместо 50 | 500.0 | 1.000 | 0.4763 |

Для масштаба: «ничего не делать» в этой среде даёт 78.8 шага и 3.38 м
([policies/manifest.txt](track_c_drone/policies/manifest.txt)). Три верхние порчи опускают политику до
уровня выключенного управления или ниже.

* **Порядок.** В [hover_env.py:250-256](track_c_drone/hover_env.py) наблюдение — это
  `concatenate([dp, vb, R[:,0], R[:,2], qvel[3:6], prev_a])`; на роботе сборка пишется заново, и два
  соседних блока по три числа легко меняются местами. Форма совпадает, ошибки нет, дрон падает.
* **Единицы и рамы.** Драйверы IMU часто отдают град/с (множитель 57.3 на трёх каналах из девятнадцати
  оставляет 40 % выживших — хватает на демонстрацию, не хватает на работу), а ENU у ROS против NED у
  автопилотов даёт инверсию знака z-каналов, на глаз неотличимую от исправного кода.
* **Частота.** Вдвое реже — политика жива, но ошибка выросла втрое. Самая коварная порча: не падает, а
  тихо ухудшает.
* **Ручные масштабы.** В [walk_env.py:329-330](track_b_walk/walk_env.py) стоит
  `concatenate([g, gyro * 0.25, qj, vj * 0.05, ...])`: коэффициенты 0.25 и 0.05 — часть контракта.

## 2. VecNormalize на роботе: статистика — часть политики

Политика ест не сырое наблюдение, а `(obs − mean) / std` из VecNormalize. Веса и статистика —
неразделимая пара: в каталоге ошибок (§A9) статистика боевого прогона уезжает на 0.40 сигмы за 2 млн
шагов, а донорские веса промахивались по масштабу канала гравитации в 43 раза.

Среда для чтения статистики не нужна: `VecNormalize.save()` пишет обычный pickle, а `__getstate__`
выбрасывает `venv`. Ровно это делает
[rl_toolkit/checkpointing.py:314-319, 327-329](rl_toolkit/checkpointing.py):

```python
    with open(pair.vecnorm_path, "rb") as fh:
        vn = pickle.load(fh)
    mean = np.asarray(vn.obs_rms.mean, dtype=np.float64)
    var = np.asarray(vn.obs_rms.var, dtype=np.float64)
    eps = float(getattr(vn, "epsilon", 1e-8))
    clip = float(getattr(vn, "clip_obs", 10.0))

    def normalize_obs(obs):
        o = np.asarray(obs, dtype=np.float64)
        return np.clip((o - mean) / np.sqrt(var + eps), -clip, clip).astype(np.float32)
```

Цена ошибки на том же протоколе из 20 эпизодов:

| вход политики | прожито шагов | доля доживших | финальная ошибка, м |
|---|---|---|---|
| нормализация применена (эталон) | 500.0 | 1.000 | 0.1667 |
| нормализация забыта (сырое наблюдение) | 449.7 | 0.350 | 2.0868 |
| нормализация применена дважды | 80.7 | 0.000 | 1.4793 |

Средняя строка важнее остальных: политика доживает до конца в 450 шагах из 500 и решает задачу в трети
эпизодов. Ролик такой политики выглядит прилично. Вывод: не возите на робота отдельно веса и отдельно
`pkl` — вшивайте нормализацию в граф, тогда потерять её нельзя конструктивно.

## 3. Экспорт в ONNX

ONNX — формат графа, который читает `onnxruntime`: без torch и без обвязки SB3, один пакет на роботе.
Скрипт ниже делает три вещи: выгружает, **сверяет выходы** и **замеряет инференс**. Сохраните его как
`export_policy_onnx.py`.

```python
"""python export_policy_onnx.py --ckpt M.zip --vecnorm M.pkl --out p.onnx --obs-dim 19"""
import argparse
import pickle
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from stable_baselines3 import PPO


class ExportedPolicy(torch.nn.Module):
    """Сырое наблюдение среды -> действие, готовое к отправке в привод."""

    def __init__(self, policy, mean, var, eps, clip_obs, low, high):
        super().__init__()
        self.policy = policy
        self.register_buffer("mean", torch.as_tensor(mean, dtype=torch.float32))
        self.register_buffer("std", torch.sqrt(torch.as_tensor(var, dtype=torch.float32) + eps))
        self.register_buffer("lo", torch.as_tensor(low, dtype=torch.float32))
        self.register_buffer("hi", torch.as_tensor(high, dtype=torch.float32))
        self.clip_obs = float(clip_obs)

    def forward(self, obs):
        z = torch.clamp((obs - self.mean) / self.std, -self.clip_obs, self.clip_obs)   # VecNormalize
        return torch.clamp(self.policy(z, deterministic=True)[0], self.lo, self.hi)    # как predict()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--vecnorm", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--obs-dim", type=int, required=True)
    ap.add_argument("--iters", type=int, default=3000)
    a = ap.parse_args()

    model = PPO.load(a.ckpt, device="cpu")
    with open(a.vecnorm, "rb") as fh:          # VecNormalize.save() пишет обычный pickle
        vn = pickle.load(fh)
    print(f"наблюдение {model.observation_space}, действие {model.action_space}\n"
          f"статистика: count={float(vn.obs_rms.count):.0f}, clip_obs={vn.clip_obs}, "
          f"epsilon={vn.epsilon}")

    net = ExportedPolicy(model.policy, vn.obs_rms.mean, vn.obs_rms.var, float(vn.epsilon),
                         float(vn.clip_obs), model.action_space.low,
                         model.action_space.high).eval()
    torch.onnx.export(net, torch.zeros(1, a.obs_dim), a.out,
                      input_names=["obs"], output_names=["action"], opset_version=17)
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1              # на роботе ядро обычно одно
    sess = ort.InferenceSession(a.out, opts, providers=["CPUExecutionProvider"])
    print(f"записан {a.out}, {Path(a.out).stat().st_size} байт\n"
          f"вход  {[(i.name, i.shape, i.type) for i in sess.get_inputs()]}\n"
          f"выход {[(o.name, o.shape, o.type) for o in sess.get_outputs()]}")

    mean = np.asarray(vn.obs_rms.mean, dtype=np.float64)
    std = np.sqrt(np.asarray(vn.obs_rms.var, dtype=np.float64) + float(vn.epsilon))
    rng = np.random.default_rng(0)
    worst = 0.0
    for _ in range(200):                       # сверка: тот же вход -> то же действие
        obs = rng.normal(0.0, 1.0, a.obs_dim).astype(np.float32)
        z = np.clip((obs - mean) / std, -vn.clip_obs, vn.clip_obs).astype(np.float32)
        ref, _ = model.predict(z, deterministic=True)
        got = sess.run(None, {"obs": obs.reshape(1, -1)})[0][0]
        worst = max(worst, float(np.max(np.abs(ref - got))))
    print(f"худшее расхождение SB3 vs ONNX на 200 наблюдениях: {worst:.3e}")
    assert worst < 1e-5, "ONNX считает НЕ ТО — переносить нельзя"

    obs1 = rng.normal(0.0, 1.0, (1, a.obs_dim)).astype(np.float32)
    for _ in range(200):
        sess.run(None, {"obs": obs1})          # прогрев
    lat = []
    for _ in range(a.iters):
        t0 = time.perf_counter()
        sess.run(None, {"obs": obs1})
        lat.append((time.perf_counter() - t0) * 1e6)
    lat = np.asarray(lat)
    print(f"инференс: медиана {np.median(lat):.1f} мкс, p99 {np.percentile(lat, 99):.1f} мкс, "
          f"максимум {lat.max():.1f} мкс ({a.iters} повторов)")


if __name__ == "__main__":
    main()
```

Запуск на политике зависания (`--out` ведёт во временный каталог, не в репозиторий):

```
python export_policy_onnx.py --ckpt track_c_drone/policies/hover/model_1503232_steps.zip \
    --vecnorm track_c_drone/policies/hover/model_vecnormalize_1503232_steps.pkl \
    --out %TEMP%/hover.onnx --obs-dim 19
```

```
наблюдение Box(-inf, inf, (19,), float32), действие Box(-1.0, 1.0, (4,), float32)
статистика: count=1503240, clip_obs=10.0, epsilon=1e-08
записан hover.onnx, 81937 байт
вход  [('obs', [1, 19], 'tensor(float)')]
выход [('action', [1, 4], 'tensor(float)')]
худшее расхождение SB3 vs ONNX на 200 наблюдениях: 7.749e-07
инференс: медиана 28.0 мкс, p99 60.4 мкс, максимум 375.7 мкс (3000 повторов)
```

Та же команда для эталонной политики ходьбы (`walk_60M.zip` + `walk_60M_vecnorm.pkl`, `--obs-dim 35`):
176 359 байт, вход `[1, 35]`, выход `[1, 8]`, расхождение `2.980e-07`, медиана 32.3 мкс, p99 62.3 мкс.

**Зачем `torch.clamp` по `action_space`.** Первая версия скрипта его не имела, и сверка показала
расхождение **4.578** — величину порядка самого действия: `forward()` политики возвращает необрезанное
действие гауссова распределения, а обрезку до границ `Box` делает `predict()`. Без строки сверки эту
ошибку нашли бы на роботе. Порог `1e-5` — уровень float32: при совпадающей математике выходит
`7.7e-07` и `3.0e-07`, на два порядка ниже порога.

**Сверка на одном наблюдении — не вся сверка.** Замкнутый контур усиливает даже float32-разницу:
20 эпизодов зависания под управлением ONNX дали финальную ошибку **0.1640 м** против **0.1667 м** у
SB3 на тех же эпизодах (выживаемость 1.000 у обеих). Разница 1.6 % — это не дефект экспорта, а
чувствительность замкнутой системы. Приёмка переноса — всегда замкнутый прогон.

**Частота.** Медиана 28 мкс при бюджете шага 50 Гц в 20 000 мкс — это 0.14 % бюджета. Сеть не узкое
место контура; узкое место — получение наблюдения и обмен с приводами.

## 4. Тот же контракт у настоящего робота

[Приложение Б](../appendix%20B%20(microduck%20policy%20inference)/README.md): политики Microduck обучены
в MuJoCo, экспортированы в ONNX и исполняются демоном `robotd` на 50 Гц (шаг физики 0.005 с, инференс
каждые 4 шага). Наблюдение 61-мерное: угловая скорость корпуса 3, проекция гравитации 3, позиции
суставов 14, скорости 14, прошлое действие 14, команды 13. Проверяется это той же строкой, что печатает
скрипт раздела 3:

```
alpha_walking.onnx  вход [('obs', [1, 61], 'tensor(float)')]  выход [('actions', [1, 14], 'tensor(float)')]
```

Все девять политик приложения имеют одну сигнатуру `obs[1,61] -> actions[1,14]`, медиана инференса на
машине курса 20.3…23.2 мкс. Это ровно контракт раздела 3: один вход, один выход, вшитая нормализация,
единицы микросекунд. Общий контракт наблюдения — ещё и причина, по которой Microduck переключает
политики на лету: ходьба, стояние, удар и кувырок принимают один и тот же вектор.

## 5. Модель актуатора — главный источник разрыва

Наблюдение можно сделать совпадающим ровно. Динамику привода — нет. В симуляции стоит идеальный
регулятор: [tsaplya2.xml:76-83](track_b_walk/tsaplya2.xml) задаёт `<position kp="376.2" kv="11.29"
forcerange="-112.86 112.86">` — момент появляется мгновенно и держится сколько нужно. У реального серво
есть сопротивление обмотки, противоЭДС, трение, токовый предел и питание, проседающее под нагрузкой.

Приложение Б заменяет PD моделью BAM
([infer_policy_windows.py:37-44](../appendix%20B%20(microduck%20policy%20inference)/code/infer_policy_windows.py)):
мотор `xl330`, модель `m6`, жёсткость прошивки `kp_fw = 200`, напряжение питания рандомизируется при
обучении в 6.5…8.2 В, просадка под нагрузкой `V_drop = gain * sum|tau|` с `gain` в 0.0…0.2, пол
напряжения 6.0 В. Именно BAM, по README приложения, закрывает разрыв sim2real для этого робота;
`--no-bam` возвращает идеальные PD-приводы, и походку можно сравнить.

Для дрона ту же роль играет инерция мотора — [quad.xml:142-146](track_c_drone/quad.xml):

```
dyntype=filterexact, dynprm=0.02: инерция мотора первого порядка,
da/dt = (u - a)/tau, tau = 20 мс -> полоса 1/tau = 50 рад/с.
ЭТО ГЛАВНОЕ ОГРАНИЧЕНИЕ ВСЕГО ТРЕКА: полоса контура угловой скорости
обязана быть <= 1/(3*tau) = 16.7 рад/с, иначе контур входит
в предельный цикл и «висит на дребезге» (грабля 6.1).
```

Политика, обученная без такого фильтра, выучит управление, требующее от мотора мгновенной смены тяги.
На стенде она даст дребезг, и ни одна настройка регулятора не поможет: дело не в настройке. Правило —
**что не смоделировано, то будет выучено неправильно**. Минимум перед первым переносом: конечная полоса
привода (фильтр первого порядка), насыщение по моменту или тяге, задержка команды на шаг-два.

## 6. Нода ROS 2 вокруг политики

Скелет для трека A: политика принимает 15 чисел, выдаёт 2 (угол руля и скорость колёс), частота 20 Гц.
**Код не запускался: ROS 2 на машине курса нет.** Проверены синтаксис (`python -m py_compile`) и,
отдельным тестом без ROS, математика наблюдения: состояние живой среды превращалось в поля
`Odometry`/`JointState` и прогонялось через `_observation` ноды — худшее расхождение с
`car_env._observation()` на 300 шагах составило `0.000e+00`.

```python
#!/usr/bin/env python3
"""ros2 run my_rl policy_node --ros-args -p policy:=/opt/policies/car.onnx"""
import math

import numpy as np
import onnxruntime as ort
import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import Float32MultiArray

# СКОПИРОВАНО ИЗ car_env.py (строки 75-76, 100-101, 128, 210-211) и probe.py:753.
OBS_DIM, ACT_DIM = 15, 2
CTRL_HZ = 20.0                       # FRAME_SKIP 5 * TIMESTEP 0.01 = 0.05 с
SPOT, TARGET_YAW = np.array([0.7, 0.0]), 0.0
PARKED_L, PARKED_R = np.array([0.7, -1.2]), np.array([0.7, 1.2])
STEER_MAX, WHEEL_V_MAX = 0.5, 1.0    # a[0] * 0.5 рад, a[1] * 1.0 м/с
WHEEL_R, WHEELBASE = 0.06, 0.44      # м
STEER_JOINT, WHEEL_JOINT = "steer_left", "roll_left"
STALE_S = 0.15                       # старше трёх периодов — это «нет данных»


class PolicyNode(Node):
    def __init__(self):
        super().__init__("policy_node")
        self.declare_parameter("policy", "car.onnx")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1            # на роботе ядро обычно одно
        self.sess = ort.InferenceSession(self.get_parameter("policy").value, opts,
                                         providers=["CPUExecutionProvider"])
        inp, out = self.sess.get_inputs()[0], self.sess.get_outputs()[0]
        if list(inp.shape) != [1, OBS_DIM] or list(out.shape) != [1, ACT_DIM]:
            raise RuntimeError(f"контракт ONNX не тот: {inp.shape} -> {out.shape}")
        self.in_name = inp.name
        # Подписка RELIABLE на BEST_EFFORT-издателя не получает НИЧЕГО и молчит.
        qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                         history=HistoryPolicy.KEEP_LAST, depth=1)
        self.create_subscription(Odometry, "odom", self._on_odom, qos)
        self.create_subscription(JointState, "joint_states", self._on_joints, qos)
        self.pub_cmd = self.create_publisher(Twist, "cmd_vel", 10)
        self.pub_obs = self.create_publisher(Float32MultiArray, "policy/obs", 10)
        self.odom, self.t_odom, self.t_joints = None, -1.0, -1.0
        self.steer = self.steer_rate = self.wheel_v = 0.0
        self.t_prev = None
        self.create_timer(1.0 / CTRL_HZ, self._on_tick)

    def _now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_odom(self, msg):
        self.odom, self.t_odom = msg, self._now()

    def _on_joints(self, msg):
        try:
            i, j = msg.name.index(STEER_JOINT), msg.name.index(WHEEL_JOINT)
        except ValueError:
            return
        prev, t_prev = self.steer, self.t_joints
        self.steer = float(msg.position[i])
        self.wheel_v = float(msg.velocity[j]) * WHEEL_R      # рад/с -> м/с
        self.t_joints = self._now()
        # В среде steer_rate берётся из qvel. Разность — ДРУГОЙ сигнал:
        # шумнее и с задержкой полпериода; сверять по записи.
        if t_prev > 0.0 and self.t_joints > t_prev:
            self.steer_rate = (self.steer - prev) / (self.t_joints - t_prev)

    def _observation(self):
        """Порядок, рамы и единицы — РОВНО car_env.py:663-682."""
        p, q = self.odom.pose.pose, self.odom.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        x, y = float(p.position.x), float(p.position.y)
        dx, dy = SPOT - np.array([x, y])
        c, s = math.cos(yaw), math.sin(yaw)
        dyaw = (yaw - TARGET_YAW + math.pi) % (2.0 * math.pi) - math.pi
        # Odometry.twist задан в child_frame_id (base_link), то есть УЖЕ в раме
        # кузова; в среде qvel[0:2] мировая и её поворачивают. Повернуть здесь
        # второй раз — тот самый «тот же вектор, другая рама».
        tw = self.odom.twist.twist
        return np.array(
            [c * dx + s * dy, -s * dx + c * dy,
             math.sin(dyaw), math.cos(dyaw),
             float(tw.linear.x), float(tw.linear.y), float(tw.angular.z),
             self.steer, self.steer_rate, self.wheel_v,
             math.hypot(dx, dy), x, y,
             float(np.linalg.norm([x - PARKED_L[0], y - PARKED_L[1]])),
             float(np.linalg.norm([x - PARKED_R[0], y - PARKED_R[1]]))],
            dtype=np.float32)

    def _on_tick(self):
        now = self._now()
        if self.t_prev is not None and now - self.t_prev > 1.5 / CTRL_HZ:
            self.get_logger().warn(f"период {1e3 * (now - self.t_prev):.1f} мс вместо "
                                   f"{1e3 / CTRL_HZ:.1f}", throttle_duration_sec=1.0)
        self.t_prev = now
        if self.odom is None or now - self.t_odom > STALE_S or now - self.t_joints > STALE_S:
            self.pub_cmd.publish(Twist())        # сторож: нет свежих данных — стоп
            self.get_logger().warn("данные устарели — стоп", throttle_duration_sec=1.0)
            return
        obs = self._observation()
        act = np.clip(self.sess.run(None, {self.in_name: obs.reshape(1, -1)})[0][0], -1.0, 1.0)
        # Действие среды — (угол руля, скорость колёс), драйвер принимает Twist.
        # Пересчёт по велосипедной модели — МЕСТО РАЗРЫВА: в симуляции угол
        # ставится напрямую, здесь его восстанавливает контроллер шасси.
        v, steer = float(act[1]) * WHEEL_V_MAX, float(act[0]) * STEER_MAX
        cmd = Twist()
        cmd.linear.x = v
        cmd.angular.z = v * math.tan(steer) / WHEELBASE
        self.pub_cmd.publish(cmd)
        # Наблюдение — в топик: только так его можно сверить с симуляционным
        # оффлайн, по записи ros2 bag (урок 2).
        self.pub_obs.publish(Float32MultiArray(data=obs.tolist()))


def main():
    rclpy.init()
    node = PolicyNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.pub_cmd.publish(Twist())            # последняя команда — ноль
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
```

* **Частота — от таймера, а не от темпа сообщений.** Считать политику по приходу одометрии значит
  отдать период загрузке сети. Жалоба на период больше полутора номиналов — первый признак того, что
  перенос поплывёт.
* **Сторож обязателен.** Пропали данные — публикуется нулевой `Twist`, а не последнее действие: без
  свежего наблюдения политика не «продолжает по инерции», она работает с мусором.
* **QoS.** Подписка `RELIABLE` на `BEST_EFFORT`-издателя молча не получает ничего
  ([урок 2](../lesson%202%20(nodes%20and%20topics)/understanding_topics.md)), а выглядит это как
  «политика не реагирует»; проверка — `ros2 topic info -v`.
* **Один топик — один хозяин.** В `cmd_vel` пишет и Nav2
  ([урок 10](../lesson%2010%20(Nav2)/introducing_nav2.md)): снимайте его контроллер или публикуйте в
  свой топик и сводите команды явным арбитром.
* **Наблюдение уходит наружу.** Записав `policy/obs` в `ros2 bag` и прогнав те же позы в среде, вы
  получаете покомпонентную разницу — единственное доказательство правила раздела 1.

## 7. Домен-рандомизация: страховка и её цена

Рандомизация — способ обучить политику, переживающую расхождение модели с железом: массы, трение,
задержки, шум наблюдения, напряжение питания. Боевая среда трека B имеет 11 источников случайности:
массы ±15 %, трение ×0.5…1.25, позы N(0, 0.03), шум наблюдений, толчок 0.2…0.5 м/с, зеркало, 60 %
команд назад ([walk_env.py:339-345](track_b_walk/walk_env.py)).

Цена измеряется двумя разными способами, и путать их нельзя. **Цена шага почти нулевая** — замер на
`HoverEnv`, 30 000 шагов среды на вариант, два независимых запуска:

```
без рандомизации                                 4265.2 и 4179.3 шаг/с
+ шум наблюдения sigma=0.01                      3956.3 и 4645.2 шаг/с
+ шум + массы ±15 % и трение x0.5..1.25 на reset  4188.9 и 4457.4 шаг/с
```

Разброс между двумя запусками одного варианта (до 11 %) больше разницы между вариантами: **на этой
машине цена рандомизации по времени шага не измеряется**, она тонет в шуме. Заявлять «рандомизация
замедлила прогон на N %» без такого парного замера нельзя.

**Цена в шагах обучения реальна.** Рандомизация делает задачу труднее: в учебной среде трека B её
отключили именно поэтому, и там же записано, что свип с рандомизацией давал 1-2 падения из 3 там, где
без неё их не было. Правило: рандомизировать то, что нельзя измерить на своём железе, и в том диапазоне,
который действительно наблюдали. Рандомизация «на всякий случай» оплачивается шагами обучения.

## 8. Чек-лист переноса

1. Наблюдение на роботе собрано той же функцией или её построчной копией, со ссылкой на файл:строку
   среды в комментарии.
2. Каждый канал проверен по единицам и раме: рад против градусов, м/с против рад/с, мир против кузова,
   ENU против NED.
3. Ручные масштабы наблюдения (вроде `gyro * 0.25`) перенесены и отмечены в комментарии.
4. Нормализация вшита в граф при экспорте; отдельный `pkl` на робота не едет.
5. Выходы ONNX сверены с SB3 на ≥ 100 наблюдениях с порогом `1e-5`, обрезка действия по `action_space`
   учтена.
6. Замкнутый прогон в симуляции выполнен экспортированной политикой, и метрика совпала с приёмочной.
7. Инференс замерен: медиана и p99 против бюджета шага (для 50 Гц бюджет 20 000 мкс).
8. Частота на роботе задана таймером, период логируется, превышение видно в логе.
9. Сторож устаревания данных публикует нулевое действие и проверен отключением датчика.
10. Модель привода содержит конечную полосу, насыщение и задержку; чего в ней нет, то будет выучено
    неправильно.

## Проверки

1. Назовите четыре способа сломать совпадение наблюдения и цену каждого по таблице раздела 1. Какой из
   них не убивает политику, а тихо ухудшает её?
2. Выгрузите политику ходьбы командой из раздела 3 (`--obs-dim 35`). Получите вход `[1, 35]`, выход
   `[1, 8]` и расхождение меньше `1e-5`.
3. Уберите `torch.clamp(..., self.lo, self.hi)` из `forward` и повторите сверку. Убедитесь, что она
   падает на `assert`, и объясните почему.
4. Прочитайте актуаторный блок [quad.xml](track_c_drone/quad.xml) и скажите, какая полоса контура
   угловой скорости допустима при `tau = 20 мс` и почему её нарушение даёт дребезг.
5. Объясните, почему в ноде раздела 6 `vx, vy` берутся из `Odometry.twist` без поворота, а в
   [car_env.py](track_a_car/car_env.py) скорость поворачивают.
6. Назовите два разных измерения цены домен-рандомизации и скажите, какое из них на этой машине
   оказалось неизмеримым.
