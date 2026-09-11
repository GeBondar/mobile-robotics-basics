"""Среда парковки автомобиля в MuJoCo (Gymnasium).

Автомобиль с передним рулевым управлением (руль) и задним приводом.
Задача: из случайной точки на дороге заехать в свободное место
на парковке, не задев стены и соседние машины.

Действие (Box [-1, 1] x [-1, 1]):
    a[0] -> угол руля  [-0.5, 0.5] рад
    a[1] -> скорость колёс +/- 1.1 м/с (задний привод)

Наблюдение (13 чисел):
    [dx, dy]      - вектор до центра места в системе координат машины
    [sin, cos]    - ошибка курса (угол между носом машины и целью)
    [vx, vy]      - скорости машины в её системе координат, м/с
    [omega]       - угловая скорость (скорость поворота), рад/с
    [steer]       - текущий угол руля, рад
    [dist]        - расстояние до центра места, м
    [x, y]        - положение машины в мире, м
    [d_left, d_right] - расстояния до соседних припаркованных машин

Быстрая проверка среды (несколько случайных шагов):
    python car_parking_env.py
"""

from __future__ import annotations

import math
from pathlib import Path

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

XML_PATH = Path(__file__).resolve().parent / "car_parking.xml"

SPOT = np.array([0.7, 0.0])          # центр целевого места (x, y)
TARGET_YAW = 0.0                      # курс машины на месте (нос в сторону +x)
SUCCESS_DX, SUCCESS_DY = 0.50, 0.50   # допустимое смещение от центра места
SUCCESS_DYAW = 0.70                   # допустимая ошибка курса, рад (40 градусов)
SUCCESS_SPEED = 0.30                  # максимальная скорость "остановки", м/с
SUCCESS_HOLD = 8                      # сколько шагов простоять в месте

MAX_STEPS = 600                       # 600 шагов * 0.01 с = 6 секунд
DT = 0.01

IN_SPOT_START_PROB = 0.2              # доля эпизодов со стартом уже на месте

STEER_MAX = 0.5                       # максимальный угол руля, рад
WHEEL_V_MAX = 18.0                    # максимальная угловая скорость колёс, рад/с
WHEEL_RADIUS = 0.06

COLLISION_GEOMS = {
    "wall_back", "wall_left", "wall_right", "wall_far",
    "parked_l_geom", "parked_r_geom", "parked_l_cabin", "parked_r_cabin",
}
PARKED_L = np.array([0.7, -1.2])
PARKED_R = np.array([0.7, 1.2])


def _wrap(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


class CarParkingEnv(gym.Env):
    metadata = {"render_modes": ["rgb_array"], "render_fps": 50}

    def __init__(self, render_mode: str | None = None,
                 in_spot_start_prob: float = IN_SPOT_START_PROB) -> None:
        super().__init__()
        self.render_mode = render_mode
        self.in_spot_start_prob = in_spot_start_prob
        self.model = mujoco.MjModel.from_xml_path(str(XML_PATH))
        self.data = mujoco.MjData(self.model)
        self._renderer: mujoco.Renderer | None = None
        self._rng = np.random.default_rng(0)

        obs_low = np.array(
            [-8.0, -8.0, -1.0, -1.0, -3.0, -3.0, -4.0, -0.7, 0.0, -1.0, -4.0, 0.0, 0.0],
            dtype=np.float32,
        )
        obs_high = np.array(
            [8.0, 8.0, 1.0, 1.0, 3.0, 3.0, 4.0, 0.7, 10.0, 8.0, 4.0, 10.0, 10.0],
            dtype=np.float32,
        )
        self.observation_space = spaces.Box(low=obs_low, high=obs_high, dtype=np.float32)
        self.action_space = spaces.Box(
            low=np.array([-1.0, -1.0], dtype=np.float32),
            high=np.array([1.0, 1.0], dtype=np.float32),
            dtype=np.float32,
        )

        self._prev_phi = 0.0
        self._hold = 0
        self._bonus_1 = False
        self._bonus_2 = False
        self._bonus_3 = False
        self._roll_target = 0.0
        self._step_count = 0
        self._trajectory: list[np.ndarray] = []

    # ------------------------------------------------------------------ api

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        if self._rng.random() < self.in_spot_start_prob:
            x = SPOT[0] + self._rng.uniform(-0.1, 0.1)
            y = SPOT[1] + self._rng.uniform(-0.1, 0.1)
            yaw = TARGET_YAW + self._rng.uniform(-0.1, 0.1)
        else:
            x = self._rng.uniform(1.9, 2.4)
            y = self._rng.uniform(-0.8, 0.8)
            yaw = math.pi / 2.0 + self._rng.uniform(-0.25, 0.25)

        self.data.qpos[:] = 0.0
        self.data.qvel[:] = 0.0
        self.data.ctrl[:] = 0.0
        self._roll_target = 0.0
        self.data.qpos[0:2] = [x, y]
        self.data.qpos[2] = 0.06
        self.data.qpos[3:7] = [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
        mujoco.mj_forward(self.model, self.data)

        self._step_count = 0
        self._hold = 0
        self._bonus_1 = False
        self._bonus_2 = False
        self._bonus_3 = False
        self._trajectory = [np.array([x, y, yaw])]
        self._prev_phi = self._potential()
        return self._observation(), {}

    def step(self, action: np.ndarray):
        steer_cmd = float(np.clip(action[0], -1.0, 1.0)) * STEER_MAX
        drive_cmd = float(np.clip(action[1], -1.0, 1.0)) * WHEEL_V_MAX

        self._roll_target += drive_cmd * DT
        self.data.ctrl[:] = [steer_cmd, steer_cmd, self._roll_target, self._roll_target]
        mujoco.mj_step(self.model, self.data)
        self._step_count += 1

        x, y, yaw = self._pose()
        self._trajectory.append(np.array([x, y, yaw]))

        terminated = False
        truncated = False
        reward = self._potential() - self._prev_phi - 0.01
        self._prev_phi = self._potential()

        info: dict = {}

        dx = x - SPOT[0]
        dy = y - SPOT[1]
        dyaw = abs(_wrap(yaw - TARGET_YAW))
        speed = abs(self._body_velocity()[0])
        dist = float(math.hypot(dx, dy))

        if not self._bonus_1 and dist < 0.8:
            self._bonus_1 = True
            reward += 15.0
        if not self._bonus_2 and abs(dx) < 0.5 and abs(dy) < 0.5 and dyaw < 0.9:
            self._bonus_2 = True
            reward += 20.0
        if not self._bonus_3 and dist < 0.28 and dyaw < 0.5:
            self._bonus_3 = True
            reward += 30.0

        if abs(dx) < SUCCESS_DX and abs(dy) < SUCCESS_DY and dyaw < SUCCESS_DYAW and speed < SUCCESS_SPEED:
            self._hold += 1
            if self._hold >= SUCCESS_HOLD:
                reward += 100.0
                terminated = True
                info["success"] = True
        else:
            self._hold = 0

        if self._collision():
            reward = -30.0
            terminated = True
            info["collision"] = True

        if x < 0.05 or x > 6.75 or abs(y) > 3.35:
            reward = -30.0
            terminated = True
            info["out_of_bounds"] = True

        if self._step_count >= MAX_STEPS and not terminated:
            truncated = True

        return self._observation(), float(reward), terminated, truncated, info

    # --------------------------------------------------------------- state

    def _pose(self) -> tuple[float, float, float]:
        q = self.data.qpos[3:7]
        yaw = math.atan2(2.0 * (q[0] * q[3] + q[1] * q[2]), 1.0 - 2.0 * (q[2] ** 2 + q[3] ** 2))
        return float(self.data.qpos[0]), float(self.data.qpos[1]), yaw

    def _body_velocity(self) -> tuple[float, float]:
        vx_w, vy_w = self.data.qvel[0], self.data.qvel[1]
        yaw = self._pose()[2]
        c, s = math.cos(yaw), math.sin(yaw)
        return float(c * vx_w + s * vy_w), float(-s * vx_w + c * vy_w)

    def _observation(self) -> np.ndarray:
        x, y, yaw = self._pose()
        dx, dy = SPOT - np.array([x, y])
        c, s = math.cos(yaw), math.sin(yaw)
        dx_body = c * dx + s * dy
        dy_body = -s * dx + c * dy
        dyaw = _wrap(yaw - TARGET_YAW)
        vx, vy = self._body_velocity()
        omega = float(self.data.qvel[5])
        steer = float((self.data.qpos[7] + self.data.qpos[9]) / 2.0)
        dist = float(math.hypot(dx, dy))
        d_left = float(np.linalg.norm(np.array([x, y]) - PARKED_L))
        d_right = float(np.linalg.norm(np.array([x, y]) - PARKED_R))
        return np.array(
            [dx_body, dy_body, math.sin(dyaw), math.cos(dyaw),
             vx, vy, omega, steer, dist, x, y, d_left, d_right],
            dtype=np.float32,
        )

    def _potential(self) -> float:
        x, y, yaw = self._pose()
        dist = float(math.hypot(x - SPOT[0], y - SPOT[1]))
        dyaw = abs(_wrap(yaw - TARGET_YAW))
        heading_weight = 2.0 * min(1.0, 1.5 / max(dist, 0.3))
        return -(2.0 * dist + heading_weight * dyaw)

    def _collision(self) -> bool:
        for i in range(self.data.ncon):
            contact = self.data.contact[i]
            for geom_id in (contact.geom1, contact.geom2):
                name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
                if name in COLLISION_GEOMS:
                    return True
        return False

    # ------------------------------------------------------------- render

    def render(self) -> np.ndarray:
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, 960, 720)
        self._renderer.update_scene(self.data, camera="top")
        return self._renderer.render()


def main() -> None:
    env = CarParkingEnv(render_mode="rgb_array")
    obs, _ = env.reset(seed=0)
    print(f"Observation shape: {obs.shape}")
    print(f"Action space: {env.action_space}")
    print(f"Observation space: {env.observation_space}")
    total_reward = 0.0
    for step in range(300):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, _ = env.step(action)
        total_reward += reward
        if step % 60 == 0:
            print(f"step {step}: action={np.round(action, 2)} reward={reward:+.2f}")
        if terminated or truncated:
            print(f"Episode finished at step {step}.")
            break
    env.close()
    print(f"Total reward: {total_reward:.2f}")


if __name__ == "__main__":
    main()
