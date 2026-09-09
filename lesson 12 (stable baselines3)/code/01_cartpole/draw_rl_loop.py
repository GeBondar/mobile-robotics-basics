"""Рисует схему цикла обучения с подкреплением (агент <-> среда).

Запуск из папки code/01_cartpole:
    python draw_rl_loop.py

Результат:
    ../../images/rl_loop.png - схема взаимодействия агента и среды
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

IMAGES_DIR = Path(__file__).resolve().parents[2] / "images"


def box(ax, xy, w, h, text, fc):
    ax.add_patch(
        FancyBboxPatch(
            xy, w, h,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            fc=fc, ec="black", lw=1.5,
        )
    )
    ax.text(
        xy[0] + w / 2, xy[1] + h / 2, text,
        ha="center", va="center", fontsize=14, fontweight="bold",
    )


def main() -> None:
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=120)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.5)
    ax.axis("off")

    box(ax, (0.8, 1.8), 2.6, 1.3, "Agent\n(policy: PPO)", "#cfe8ff")
    box(ax, (6.6, 1.8), 2.6, 1.3, "Environment\n(Gymnasium)", "#d6f5d6")

    top = FancyArrowPatch(
        (2.35, 3.45), (8.1, 3.45),
        arrowstyle="-|>", mutation_scale=24, lw=2, color="#b0413e",
        connectionstyle="arc3,rad=-0.35",
    )
    ax.add_patch(top)
    ax.text(5.2, 4.15, "action a_t", ha="center", va="center",
            fontsize=13, fontweight="bold", color="#b0413e")

    bottom = FancyArrowPatch(
        (8.1, 1.55), (2.35, 1.55),
        arrowstyle="-|>", mutation_scale=24, lw=2, color="#1f6fb2",
        connectionstyle="arc3,rad=-0.35",
    )
    ax.add_patch(bottom)
    ax.text(5.2, 0.65, "next state s_{t+1},  reward r_t",
            ha="center", va="center", fontsize=13, fontweight="bold", color="#1f6fb2")

    fig.tight_layout()
    fig.savefig(IMAGES_DIR / "rl_loop.png")
    plt.close(fig)
    print("Saved images/rl_loop.png")


if __name__ == "__main__":
    main()
