"""Контракты политик: наблюдение из сообщений ROS 2 и действие -> команда приводам.

Контракт — всё, что политика видела в среде обучения, кроме самих весов:
порядок и масштаб каналов наблюдения, внутреннее состояние (фазовые часы,
прошлое действие, фильтры), пересчёт действия в цели приводов. Каждый класс
ниже — построчная копия своей среды со ссылкой на файл и строки. Разошлись с
средой хоть в одном канале — политика получит чужой вектор и честно выдаст
по нему действие (глава 09 урока 14, раздел 1).

Контракт не знает про ROS: он принимает RobotState, собранный нодой из
JointState/Imu/Odometry, и возвращает numpy-массивы. Поэтому его можно
проверить без ROS — тем же состоянием, что даёт среда (см. tests/).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class RobotState:
    """Что знает о себе робот. Заполняется нодой из топиков."""
    q: np.ndarray                    # позиции суставов, рад, в порядке JOINTS контракта
    dq: np.ndarray                   # скорости суставов, рад/с
    quat: np.ndarray                 # ориентация корпуса (w, x, y, z), мир <- корпус
    gyro: np.ndarray                 # угловая скорость корпуса в раме корпуса, рад/с
    pos: np.ndarray = field(default_factory=lambda: np.zeros(3))   # мир, м (из odom)
    vel_body: np.ndarray = field(default_factory=lambda: np.zeros(3))  # раме корпуса, м/с


@dataclass
class Command:
    """Высокоуровневая команда: то, что приходит в /cmd_vel и соседние топики."""
    vx: float = 0.0
    vy: float = 0.0
    wz: float = 0.0
    head: np.ndarray = field(default_factory=lambda: np.zeros(4))   # только Microduck
    target: np.ndarray | None = None                               # только дрон: точка в мире


def quat_to_mat(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def yaw_of(q):
    w, x, y, z = q
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def gravity_body(q):
    return quat_to_mat(q).T @ np.array([0.0, 0.0, -1.0])


class Contract:
    name = "base"
    JOINTS: tuple = ()
    OBS_DIM = 0
    ACT_DIM = 0
    CONTROL_HZ = 50.0
    USES_JOINT_STATES = True     # дрону суставы не нужны: только IMU и odom

    def reset(self, st: RobotState, cmd: Command) -> None:
        """Обнулить внутреннее состояние. Вызывается при смене политики и старте."""

    def observe(self, st: RobotState, cmd: Command) -> np.ndarray:
        raise NotImplementedError

    def act(self, action: np.ndarray) -> np.ndarray:
        """Действие сети -> массив для /joint_commands."""
        raise NotImplementedError

    def safe_command(self, st: RobotState) -> np.ndarray:
        """Что слать, когда данных нет: сторож из главы 09."""
        raise NotImplementedError

    def fallen(self, st: RobotState) -> bool:
        return False


# ---------------------------------------------------------------------------
class MicroduckContract(Contract):
    """Microduck: obs[61] -> actions[14], 50 Гц.

    Источник — appendix B, code/infer_policy_windows.py:
    get_observations() строки 665-691, DEFAULT_POSE строки 129-144,
    apply_action() строки 875-892. Нормализация вшита в ONNX.
    """
    name = "microduck"
    JOINTS = ("left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
              "neck_pitch", "head_pitch", "head_yaw", "head_roll",
              "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle")
    OBS_DIM, ACT_DIM = 61, 14
    DEFAULT_POSE = np.array([0.0, -0.0873, -0.4579, -0.0049, 0.4530,
                             0.3491, 0.3491, 0.0, 0.0,
                             0.0, 0.0873, 0.4579, 0.0049, -0.4530])
    ACTION_SCALE = 1.0

    def __init__(self):
        self.last_action = np.zeros(self.ACT_DIM)

    def reset(self, st, cmd):
        # last_action НЕ обнуляется при переключении политики: в скрипте приложения Б
        # он общий для всех сессий, и политики обучены подхватывать чужое действие.
        pass

    def observe(self, st, cmd):
        command = np.zeros(13)
        command[0:3] = (cmd.vx, cmd.vy, cmd.wz)
        command[3:7] = cmd.head                    # neck_pitch, head_pitch, head_yaw, head_roll
        # command[7:13] — поза корпуса (стоячая политика); 0 = номинальная
        return np.concatenate([st.gyro, gravity_body(st.quat), st.q - self.DEFAULT_POSE,
                               st.dq, self.last_action, command]).astype(np.float32)

    def act(self, action):
        self.last_action = np.asarray(action, dtype=np.float64).copy()
        return self.DEFAULT_POSE + self.last_action * self.ACTION_SCALE

    def safe_command(self, st):
        return self.DEFAULT_POSE.copy()

    def fallen(self, st):
        return gravity_body(st.quat)[2] > -0.5      # наклон больше 60°


# ---------------------------------------------------------------------------
class Tsaplya2Contract(Contract):
    """ЦАПЛЯ-2 (legged_robots, прогон r4u): obs[35] -> action[8], 50 Гц.

    Источник — lesson 14/track_b_walk/_reference_walk_env_r4.py
    (побитово равен legged_robots/sim/walk_env_r4.py):
      _obs()      строки 474-499: [g, gyro*0.25, qj, vj*0.05, prev_act, cmd, sin/cos фазы]
      reset()     строки 549-585: опорный курс, фаза, d_swing, f_eff
      step()      строки 613-616: задержка на такт + EMA 0.3/0.7, act_scale = 0.25*(hi-lo)
                  строки 631-647: контур курса wz_eff и фазовые часы
    """
    name = "tsaplya2"
    JOINTS = ("left_yaw", "left_roll", "left_hip", "left_knee",
              "right_yaw", "right_roll", "right_hip", "right_knee")
    OBS_DIM, ACT_DIM = 35, 8
    DT = 0.02
    # ctrlrange из tsaplya2.xml, строки 76-83
    CTRL_LO = np.array([-1.0472, -0.6981, -0.7854, -0.8674, -1.0472, -0.6981, -0.7854, -0.8674])
    CTRL_HI = np.array([1.0472, 0.6981, 0.7854, 1.0175, 1.0472, 0.6981, 0.7854, 1.0175])
    Z0, H_REF, V_REF, F_PHASE_REF = 0.4272, 0.1445, 0.5, 1.4
    CTRL_YAW_K, CTRL_WZ_MAX, CTRL_WZ_CORR_MAX = 2.0, 0.6, 0.40
    SLEW_V, SLEW_W = 1.2, 3.0          # legged_robots/sim/play_wasd.py:68-69

    def __init__(self):
        k = math.sqrt(self.Z0 / self.H_REF)
        self.v_max = self.V_REF * k                       # 0.86 м/с
        self.f_phase = self.F_PHASE_REF / k               # 0.814 Гц
        self.act_scale = 0.25 * (self.CTRL_HI - self.CTRL_LO)
        self.cmd = np.zeros(3)
        self._reset_buffers()
        self.phase = 0.0
        self.yaw_ref = 0.0
        self.wz_eff = 0.0
        self.started = False

    def _reset_buffers(self):
        self.prev_act = np.zeros(8)     # то, что попадёт в наблюдение
        self.last_act = np.zeros(8)     # действие прошлого такта
        self.delayed = np.zeros(8)
        self.act_filt = np.zeros(8)

    def reset(self, st, cmd):
        self._reset_buffers()
        self.cmd = np.zeros(3)
        self.yaw_ref = yaw_of(st.quat)
        self.wz_eff = 0.0
        self.phase = 0.0
        self.started = False

    def _clamp_cmd(self, cmd):
        """Полоса обучения: vx ±v_max, vy ±0.2·v_max, wz ±0.6, плюс ограничитель скачка."""
        want = np.array([np.clip(cmd.vx, -self.v_max, self.v_max),
                         np.clip(cmd.vy, -0.2 * self.v_max, 0.2 * self.v_max),
                         np.clip(cmd.wz, -0.6, 0.6)])
        lim = np.array([self.SLEW_V, self.SLEW_V, self.SLEW_W]) * self.DT
        self.cmd = self.cmd + np.clip(want - self.cmd, -lim, lim)

    def observe(self, st, cmd):
        self._clamp_cmd(cmd)
        d_swing = min(0.35, max(0.15, 0.6 * abs(self.cmd[0]) / self.f_phase))
        f_eff = max(self.f_phase, abs(self.cmd[0]) / d_swing)
        if self.started:
            # в среде это делается ПОСЛЕ физики и ДО сборки наблюдения (строки 631-647)
            self.yaw_ref += self.cmd[2] * self.DT
            e = (yaw_of(st.quat) - self.yaw_ref + math.pi) % (2 * math.pi) - math.pi
            corr = float(np.clip(-self.CTRL_YAW_K * e, -self.CTRL_WZ_CORR_MAX, self.CTRL_WZ_CORR_MAX))
            self.wz_eff = float(np.clip(self.cmd[2] + corr, -self.CTRL_WZ_MAX, self.CTRL_WZ_MAX))
            self.phase = (self.phase + 2 * math.pi * f_eff * self.DT) % (2 * math.pi)
        else:
            self.wz_eff = float(self.cmd[2])
            self.started = True
        obs = np.concatenate([gravity_body(st.quat), st.gyro * 0.25, st.q, st.dq * 0.05,
                              self.prev_act, [self.cmd[0], self.cmd[1], self.wz_eff],
                              [math.sin(self.phase), math.cos(self.phase)]])
        # В среде obs_{t+1} собирается ДО строки prev_act = a_t, поэтому в наблюдении
        # лежит действие ДВУХТАКТНОЙ давности. Повторяем буквально.
        self.prev_act = self.last_act.copy()
        return obs.astype(np.float32)

    def act(self, action):
        a = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        self.last_act = a.copy()
        self.act_filt = 0.3 * self.act_filt + 0.7 * self.delayed
        self.delayed = a.copy()
        return np.clip(self.act_filt * self.act_scale, self.CTRL_LO, self.CTRL_HI)

    def safe_command(self, st):
        return np.zeros(8)              # нулевая поза — стойка

    def fallen(self, st):
        return gravity_body(st.quat)[2] > -0.7071 or st.pos[2] < 0.55 * self.Z0


# ---------------------------------------------------------------------------
class QuadHoverContract(Contract):
    """Дрон трека C1: obs[19] -> тяги 4 винтов, 50 Гц.

    Источник — lesson 14/track_c_drone/hover_env.py:
      _obs()  строки 250-256: [dp_body, v_body, R[:,0], R[:,2], omega, prev_a]
      step()  строки 216-218: thrust = clip(hover*(1 + 0.6*a), 0, 4.6)
    Цель задаётся топиком; в обучении она была в пределах ±spawn от дрона,
    поэтому дальняя цель подаётся «морковкой» не дальше CARROT метров.
    """
    name = "quad"
    JOINTS = ("thrust1", "thrust2", "thrust3", "thrust4")
    OBS_DIM, ACT_DIM = 19, 4
    USES_JOINT_STATES = False
    HOVER, K_A, T_MAX = 0.740 * 9.81 / 4, 0.6, 4.6   # hover_env.py:133, масса из quad.xml
    CARROT = 0.8                                     # spawn = ±0.8 м по каждой оси в обучении

    def __init__(self):
        self.prev_a = np.zeros(4)
        self.target = None

    def reset(self, st, cmd):
        self.prev_a = np.zeros(4)

    def observe(self, st, cmd):
        if cmd.target is not None:
            self.target = np.asarray(cmd.target, dtype=np.float64)
        if self.target is None:
            self.target = st.pos.copy()           # нет цели — висим, где стоим
        R = quat_to_mat(st.quat)
        off = self.target - st.pos
        n = float(np.linalg.norm(off))
        if n > self.CARROT:
            off = off * (self.CARROT / n)
        return np.concatenate([R.T @ off, st.vel_body, R[:, 0], R[:, 2], st.gyro,
                               self.prev_a]).astype(np.float32)

    def act(self, action):
        a = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        self.prev_a = a.copy()
        return np.clip(self.HOVER * (1.0 + self.K_A * a), 0.0, self.T_MAX)

    def safe_command(self, st):
        return np.full(4, self.HOVER * 0.8)       # мягкое снижение, а не выключение винтов

    def fallen(self, st):
        return quat_to_mat(st.quat)[2, 2] < 0.0


CONTRACTS = {"microduck": MicroduckContract, "tsaplya2": Tsaplya2Contract, "quad": QuadHoverContract}


def make_contract(name: str) -> Contract:
    if name not in CONTRACTS:
        raise ValueError(f"нет контракта '{name}', есть: {sorted(CONTRACTS)}")
    return CONTRACTS[name]()


def read_onnx_meta(sess) -> dict:
    meta = sess.get_modelmeta().custom_metadata_map
    return {k: (json.loads(v) if v[:1] in "[{" else v) for k, v in meta.items()}
