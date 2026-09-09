"""Демонстрация обученной модели PPO на CartPole-v1.

Запуск из папки code/01_cartpole:
    python evaluate_cartpole.py

Результат:
    ../../images/cartpole_evaluation.gif - анимация одного эпизода
    ../../images/cartpole_evaluation.png - три кадра эпизода
"""

from pathlib import Path

import gymnasium as gym
import numpy as np
from PIL import Image
from stable_baselines3 import PPO

CODE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = CODE_DIR.parents[1] / "images"


def frames_to_gif(frames: list[np.ndarray], path: Path, duration_ms: int = 40, width: int = 320) -> None:
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
    model = PPO.load(CODE_DIR / "models" / "ppo_cartpole", device="cpu")
    env = gym.make("CartPole-v1", render_mode="rgb_array")

    obs, _ = env.reset(seed=7)
    frames: list[np.ndarray] = []
    total_reward = 0.0
    step = 0
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, _ = env.step(action)
        total_reward += float(reward)
        done = terminated or truncated
        if step % 3 == 0:
            frames.append(env.render())
        step += 1
    env.close()
    print(f"Total reward: {total_reward:.1f} (max is 500)")

    frames_to_gif(frames, IMAGES_DIR / "cartpole_evaluation.gif")

    collage = np.concatenate(
        [
            frames[len(frames) // 4],
            frames[len(frames) // 2],
            frames[3 * len(frames) // 4],
        ],
        axis=1,
    )
    Image.fromarray(collage).save(IMAGES_DIR / "cartpole_evaluation.png")
    print(f"Saved {len(frames)} frames to images/cartpole_evaluation.gif")


if __name__ == "__main__":
    main()
