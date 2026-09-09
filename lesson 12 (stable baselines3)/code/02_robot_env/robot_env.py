"""Двумерная среда мобильного робота для Stable Baselines 3.

Рабочая область - квадрат 10x10 м. Робот (x, y, theta) управляется
линейной скоростью v и угловой скоростью omega. Задача: доехать
до цели (9, 9), не врезавшись в стены и два препятствия.

Среда написана по стандарту Gymnasium, поэтому совместима
со всеми алгоритмами Stable Baselines 3.

Быстрая проверка среды (несколько случайных шагов):
    python robot_env.py
"""

from __future__ import annotations

import math

import gymnasium as gym
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from gymnasium import spaces
from matplotlib.patches import Circle, Rectangle

WORLD_SIZE = 10.0
GOAL = np.array([9.0, 9.0])
GOAL_RADIUS = 0.4
OBSTACLES = np.array([[4.0, 3.0], [7.0, 7.0]])
OBSTACLE_RADIUS = np.array([1.2, 1.0])
START = np.array([0.5, 0.5, 0.0])
START_NOISE = 0.3
ROBOT_RADIUS = 0.25
N_RAYS = 8
MAX_STEPS = 250
DT = 0.1
V_MIN, V_MAX = -0.5, 1.0
W_MIN, W_MAX = -1.5, 1.5
LIDAR_RANGE = 12.0


def _ray_distance(origin: np.ndarray, angle: float) -> float:
    """Расстояние от точки origin до ближайшего препятствия вдоль луча."""
    d = np.array([math.cos(angle), math.sin(angle)])
    best = LIDAR_RANGE

    for center, radius in zip(OBSTACLES, OBSTACLE_RADIUS):
        rel = origin - center
        b = 2.0 * float(np.dot(d, rel))
        c = float(np.dot(rel, rel)) - radius * radius
        disc = b * b - 4.0 * c
        if disc >= 0.0:
            sqrt_disc = math.sqrt(disc)
            for t in ((-b - sqrt_disc) / 2.0, (-b + sqrt_disc) / 2.0):
                if t > 1e-6:
                    best = min(best, t)

    for wall_x in (0.0, WORLD_SIZE):
        if abs(d[0]) > 1e-9:
            t = (wall_x - origin[0]) / d[0]
            y = origin[1] + t * d[1]
            if t > 1e-6 and 0.0 <= y <= WORLD_SIZE:
                best = min(best, t)
    for wall_y in (0.0, WORLD_SIZE):
        if abs(d[1]) > 1e-9:
            t = (wall_y - origin[1]) / d[1]
            x = origin[0] + t * d[0]
            if t > 1e-6 and 0.0 <= x <= WORLD_SIZE:
                best = min(best, t)

    return best


def draw_world(
    ax: plt.Axes,
    robot_state: np.ndarray | None = None,
    rays: bool = False,
    trajectory: np.ndarray | None = None,
) -> None:
    """Рисует рабочую область, препятствия, цель и опционально робота."""
    ax.set_xlim(-0.4, WORLD_SIZE + 0.4)
    ax.set_ylim(-0.4, WORLD_SIZE + 0.4)
    ax.set_aspect("equal")
    ax.add_patch(
        Rectangle((0, 0), WORLD_SIZE, WORLD_SIZE, fill=False, edgecolor="black", lw=2)
    )
    for center, radius in zip(OBSTACLES, OBSTACLE_RADIUS):
        ax.add_patch(Circle(center, radius, fc="tab:red", ec="black", alpha=0.9, label="Obstacle"))
    ax.add_patch(Circle(GOAL, GOAL_RADIUS, fc="tab:green", ec="black", alpha=0.9, label="Goal"))
    ax.plot(*GOAL, marker="x", color="black", ms=8, mew=2)

    if trajectory is not None and len(trajectory) > 0:
        ax.plot(
            trajectory[:, 0], trajectory[:, 1],
            color="tab:purple", lw=2, alpha=0.9, label="Trajectory",
        )

    if robot_state is not None:
        x, y, theta = robot_state
        ax.add_patch(Circle((x, y), ROBOT_RADIUS, fc="tab:blue", ec="black"))
        ax.plot(
            [x, x + 0.55 * math.cos(theta)],
            [y, y + 0.55 * math.sin(theta)],
            color="black", lw=2,
        )
        if rays:
            for i in range(N_RAYS):
                angle = theta + i * 2.0 * math.pi / N_RAYS
                dist = _ray_distance(np.array([x, y]), angle)
                ax.plot(
                    [x, x + dist * math.cos(angle)],
                    [y, y + dist * math.sin(angle)],
                    color="tab:orange", lw=1, alpha=0.8,
                )

    ax.axis("off")


class RobotReacherEnv(gym.Env):
    metadata = {"render_modes": ["rgb_array"], "render_fps": 10}

    def __init__(self, render_mode: str | None = None) -> None:
        super().__init__()
        self.render_mode = render_mode
        self._rng = np.random.default_rng(0)
        self._last_action = np.zeros(2, dtype=np.float32)

        obs_low = np.array(
            [-15.0, -15.0, V_MIN, W_MIN] + [0.0] * N_RAYS, dtype=np.float32
        )
        obs_high = np.array(
            [15.0, 15.0, V_MAX, W_MAX] + [1.0] * N_RAYS, dtype=np.float32
        )
        self.observation_space = spaces.Box(low=obs_low, high=obs_high, dtype=np.float32)
        self.action_space = spaces.Box(
            low=np.array([V_MIN, W_MIN], dtype=np.float32),
            high=np.array([V_MAX, W_MAX], dtype=np.float32),
            dtype=np.float32,
        )

        self.state = START.copy()
        self.step_count = 0
        self.trajectory: list[np.ndarray] = []

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        noise = self._rng.uniform(-START_NOISE, START_NOISE, size=2)
        theta_noise = self._rng.uniform(-0.3, 0.3)
        self.state = np.array(
            [START[0] + noise[0], START[1] + noise[1], START[2] + theta_noise]
        )
        self._last_action = np.zeros(2, dtype=np.float32)
        self.step_count = 0
        self.trajectory = [self.state[:2].copy()]
        return self._observation(), {}

    def _observation(self) -> np.ndarray:
        x, y, theta = self.state
        dx, dy = GOAL - self.state[:2]
        c, s = math.cos(theta), math.sin(theta)
        goal_rel_x = c * dx + s * dy
        goal_rel_y = -s * dx + c * dy
        rays = np.array(
            [
                _ray_distance(self.state[:2], theta + i * 2.0 * math.pi / N_RAYS)
                for i in range(N_RAYS)
            ]
        ) / LIDAR_RANGE
        return np.concatenate(
            [[goal_rel_x, goal_rel_y], self._last_action, rays]
        ).astype(np.float32)

    def _collision(self) -> bool:
        x, y = self.state[:2]
        if (
            x - ROBOT_RADIUS < 0.0
            or x + ROBOT_RADIUS > WORLD_SIZE
            or y - ROBOT_RADIUS < 0.0
            or y + ROBOT_RADIUS > WORLD_SIZE
        ):
            return True
        for center, radius in zip(OBSTACLES, OBSTACLE_RADIUS):
            if np.linalg.norm(self.state[:2] - center) < radius + ROBOT_RADIUS:
                return True
        return False

    def step(self, action: np.ndarray):
        v = float(np.clip(action[0], V_MIN, V_MAX))
        w = float(np.clip(action[1], W_MIN, W_MAX))
        x, y, theta = self.state
        d_prev = float(np.linalg.norm(self.state[:2] - GOAL))

        theta += w * DT
        x += v * math.cos(theta) * DT
        y += v * math.sin(theta) * DT
        self.state = np.array([x, y, theta])
        self._last_action = np.array([v, w], dtype=np.float32)
        self.step_count += 1
        self.trajectory.append(self.state[:2].copy())

        d_new = float(np.linalg.norm(self.state[:2] - GOAL))
        reward = 2.0 * (d_prev - d_new) - 0.02

        terminated = False
        truncated = False

        if d_new <= GOAL_RADIUS:
            reward += 50.0
            terminated = True
        elif self._collision():
            reward = -20.0
            terminated = True
        elif self.step_count >= MAX_STEPS:
            truncated = True

        return self._observation(), float(reward), terminated, truncated, {}

    def render(self) -> np.ndarray:
        fig, ax = plt.subplots(figsize=(6, 6), dpi=100)
        draw_world(ax, robot_state=self.state, rays=True)
        fig.tight_layout(pad=0.1)
        fig.canvas.draw()
        data = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
        plt.close(fig)
        return data


def main() -> None:
    env = RobotReacherEnv(render_mode="rgb_array")
    obs, _ = env.reset(seed=0)
    print(f"Observation shape: {obs.shape}")
    print(f"Action space: {env.action_space}")
    print(f"Observation space: {env.observation_space}")
    total_reward = 0.0
    for step in range(10):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, _ = env.step(action)
        total_reward += reward
        print(f"step {step + 1}: v={action[0]:+.2f}  w={action[1]:+.2f}  reward={reward:+.2f}")
        if terminated or truncated:
            print("Episode finished.")
            break
    env.close()
    print(f"Total reward: {total_reward:.2f}")


if __name__ == "__main__":
    main()
