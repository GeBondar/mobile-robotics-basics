"""Рисует схему среды RobotReacherEnv: робот, цель, препятствия, лидар.

Запуск из папки code/02_robot_env:
    python draw_env_scheme.py

Результат:
    ../../images/robot_env_scheme.png - схема среды
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from robot_env import GOAL, GOAL_RADIUS, OBSTACLES, OBSTACLE_RADIUS, START, draw_world

IMAGES_DIR = Path(__file__).resolve().parents[2] / "images"


def main() -> None:
    fig, ax = plt.subplots(figsize=(6.2, 6.2), dpi=110)
    draw_world(ax, robot_state=START, rays=True)

    ax.plot(*START[:2], marker="o", color="tab:blue", ms=10)
    ax.annotate(
        "Start\n(x=0.5, y=0.5, theta=0)",
        xy=START[:2], xytext=(0.9, 1.9),
        fontsize=10, fontweight="bold", color="tab:blue",
    )
    ax.annotate(
        "Goal\n(9, 9)",
        xy=GOAL, xytext=(6.8, 8.2),
        fontsize=10, fontweight="bold", color="tab:green",
    )
    for center, radius in zip(OBSTACLES, OBSTACLE_RADIUS):
        ax.annotate(
            f"Obstacle\nr={radius:.1f}",
            xy=center, xytext=(center[0] - 0.6, center[1] + radius + 0.5),
            fontsize=9, fontweight="bold", color="tab:red",
        )
    ax.annotate(
        "Action: v, omega\nObservation: goal, velocities, 8 lidar rays",
        xy=(5.0, 5.0), xytext=(1.2, 9.0),
        fontsize=10, style="italic",
    )
    ax.set_title("RobotReacherEnv: mobile robot must reach the goal")
    fig.tight_layout()
    fig.savefig(IMAGES_DIR / "robot_env_scheme.png")
    plt.close(fig)
    print("Saved images/robot_env_scheme.png")


if __name__ == "__main__":
    main()
