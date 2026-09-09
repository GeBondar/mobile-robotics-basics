"""Обучение агента PPO на задаче CartPole-v1.

Запуск из папки code/01_cartpole:
    python train_cartpole.py

Результат:
    models/ppo_cartpole.zip                  - обученная модель
    ../../images/cartpole_training_curve.png - график средней награды
    logs/ppo_cartpole/                       - логи для TensorBoard
"""

from pathlib import Path

import gymnasium as gym
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.evaluation import evaluate_policy
from stable_baselines3.common.monitor import Monitor

CODE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = CODE_DIR.parents[1] / "images"

TOTAL_TIMESTEPS = 50_000
SEED = 42


class EpisodeRewardCallback(BaseCallback):
    """Собирает награды эпизодов из Monitor-обёртки."""

    def __init__(self, verbose: int = 0) -> None:
        super().__init__(verbose)
        self.episode_rewards: list[float] = []

    def _on_step(self) -> bool:
        for info in self.locals.get("infos", []):
            if "episode" in info:
                self.episode_rewards.append(float(info["episode"]["r"]))
        return True


def plot_curve(episode_rewards: list[float], path: Path) -> None:
    window = max(1, len(episode_rewards) // 50)
    if len(episode_rewards) >= window:
        smoothed = np.convolve(
            episode_rewards, np.ones(window) / window, mode="valid"
        )
        x_smoothed = np.arange(window - 1, len(episode_rewards))
    else:
        smoothed = np.array(episode_rewards)
        x_smoothed = np.arange(len(episode_rewards))

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=110)
    ax.plot(episode_rewards, alpha=0.35, label="Episode reward", color="tab:blue")
    ax.plot(
        x_smoothed,
        smoothed,
        label=f"Moving average (window {window})",
        color="tab:orange",
        linewidth=2,
    )
    ax.axhline(500, color="tab:green", linestyle="--", label="Max score = 500")
    ax.set_xlabel("Episode")
    ax.set_ylabel("Total reward")
    ax.set_title("PPO on CartPole-v1: training progress")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    env = Monitor(gym.make("CartPole-v1"))
    model = PPO(
        "MlpPolicy",
        env,
        verbose=1,
        tensorboard_log=CODE_DIR / "logs",
        seed=SEED,
        device="cpu",
    )
    callback = EpisodeRewardCallback()
    model.learn(total_timesteps=TOTAL_TIMESTEPS, callback=callback, progress_bar=True)

    model.save(CODE_DIR / "models" / "ppo_cartpole")
    plot_curve(callback.episode_rewards, IMAGES_DIR / "cartpole_training_curve.png")

    eval_env = Monitor(gym.make("CartPole-v1"))
    mean_reward, std_reward = evaluate_policy(model, eval_env, n_eval_episodes=10)
    print(f"\nMean reward over 10 episodes: {mean_reward:.1f} +/- {std_reward:.1f}")
    print(f"Max score is 500, so about {mean_reward / 500.0 * 100:.0f}% of the task is solved.")


if __name__ == "__main__":
    main()
