"""Демонстрация обученной модели PPO в среде RobotReacherEnv.

Запуск из папки code/02_robot_env:
    python evaluate_robot.py

Результат:
    ../../images/robot_trajectory.png      - траектория обученного агента
    ../../images/robot_random_policy.png   - траектория случайного агента
    ../../images/robot_reach.gif           - анимация эпизода
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from stable_baselines3 import PPO

from robot_env import GOAL, GOAL_RADIUS, START, RobotReacherEnv, draw_world

CODE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = CODE_DIR.parents[1] / "images"


def run_episode(env: RobotReacherEnv, model=None) -> tuple[float, np.ndarray, list[np.ndarray]]:
    """Прогоняет один эпизод. Возвращает (reward, trajectory, frames)."""
    obs, _ = env.reset(seed=0)
    frames: list[np.ndarray] = []
    total_reward = 0.0
    done = False
    while not done:
        if model is None:
            action = env.action_space.sample()
        else:
            action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, _ = env.step(action)
        total_reward += float(reward)
        done = terminated or truncated
        if env.step_count % 4 == 0:
            frames.append(env.render())
    frames.append(env.render())
    trajectory = np.array(env.trajectory)
    return total_reward, trajectory, frames


def save_trajectory(trajectory: np.ndarray, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(6.2, 6.2), dpi=110)
    draw_world(ax, trajectory=trajectory)
    ax.plot(*START[:2], marker="o", color="tab:blue", ms=10, label="Start")
    reached = np.linalg.norm(trajectory[-1] - GOAL) <= GOAL_RADIUS
    ax.plot(*trajectory[-1], marker="*", color="tab:green", ms=16, label="Finish")
    ax.set_title(f"{title}\n(goal {'reached' if reached else 'NOT reached'})")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def frames_to_gif(frames: list[np.ndarray], path: Path, duration_ms: int = 80, width: int = 340) -> None:
    resized = [
        Image.fromarray(frame).resize((width, int(frame.shape[0] * width / frame.shape[1])))
        for frame in frames
    ]
    resized[0].save(
        path,
        save_all=True,
        append_images=resized[1:],
        duration=duration_ms,
        loop=0,
    )


def main() -> None:
    model = PPO.load(CODE_DIR / "models" / "ppo_robot", device="cpu")

    env = RobotReacherEnv(render_mode="rgb_array")
    reward, trajectory, frames = run_episode(env, model)
    env.close()
    print(f"Trained policy: total reward = {reward:.1f}, steps = {len(trajectory)}")
    save_trajectory(trajectory, IMAGES_DIR / "robot_trajectory.png", "Trained policy (PPO)")
    frames_to_gif(frames, IMAGES_DIR / "robot_reach.gif")

    env = RobotReacherEnv(render_mode="rgb_array")
    rewards_random = []
    random_trajectory = None
    for _ in range(5):
        r, traj, _ = run_episode(env, model=None)
        rewards_random.append(r)
        if random_trajectory is None:
            random_trajectory = traj
    env.close()
    mean_random = float(np.mean(rewards_random))
    print(f"Random policy: mean reward over 5 episodes = {mean_random:.1f}")
    save_trajectory(random_trajectory, IMAGES_DIR / "robot_random_policy.png", "Random policy")

    print("Saved images: robot_trajectory.png, robot_random_policy.png, robot_reach.gif")


if __name__ == "__main__":
    main()
