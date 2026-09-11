# -*- coding: utf-8 -*-
"""Грабля §A11: hold задаётся в АБСОЛЮТНЫХ шагах, и при --resume рампа уже отработала.

Числа — из самопроверки `python -m rl_toolkit.curriculum` (разделы 1, 4, 5) и из
цитаты донорского проекта: рампа рельефа linear(hold=2 000 000, ramp=18 000 000,
0 -> 1), продолжение обучения с абсолютного шага 163 500 000 на 30 000 000 шагов;
lvl = min(1, 161.5M/18M) = 1.0 с первого же шага.
Лечение — подставить старт в hold (t0 = model.num_timesteps), как в
track_a_car/train.py:183-184, 232-236.
Формула значения рампы — rl_toolkit/curriculum.py:148-150.

Пересборка:  python curriculum_resume_trap.py
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = "curriculum_resume_trap.png"


def ramp(t, hold, length, lo, hi):
    """rl_toolkit/curriculum.py:148-150."""
    x = np.clip((t - hold) / float(length), 0.0, 1.0)
    return lo + (hi - lo) * x


HOLD = 2_000_000
RAMP = 18_000_000
T0 = 163_500_000
RUN = 30_000_000
m = 1e6

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 4.5))

# --- слева: всё расписание в абсолютных шагах -------------------------------
t = np.linspace(0, T0 + RUN, 4001)
ax1.plot(t / m, ramp(t, HOLD, RAMP, 0.0, 1.0), lw=2)
ax1.axvspan(T0 / m, (T0 + RUN) / m, color="tab:red", alpha=0.18)
ax1.annotate("окно resume:\n163.5 -> 193.5 млн", xy=((T0 + RUN / 2) / m, 0.55),
             ha="center", va="center", fontsize=9, color="tab:red")
ax1.annotate("рампа отработала\nк 20 млн", xy=(20, 1.0), xytext=(45, 0.35),
             fontsize=9, color="0.25",
             arrowprops=dict(arrowstyle="->", color="0.4"))
ax1.set_xlabel("абсолютный счётчик model.num_timesteps, млн")
ax1.set_ylabel("terrain (уровень рельефа)")
ax1.set_title("hold=2 млн, ramp=18 млн\nв абсолютных шагах", fontsize=10)
ax1.set_xlim(0, (T0 + RUN) / m)
ax1.set_ylim(-0.05, 1.12)
ax1.grid(alpha=0.3)

# --- справа: что видит продолженный прогон ----------------------------------
t2 = np.linspace(T0, T0 + RUN, 2001)
ax2.plot(t2 / m, ramp(t2, HOLD, RAMP, 0.0, 1.0), lw=2.5, color="tab:red",
         label="hold = 2 000 000\n(три сгоревших прогона)")
ax2.plot(t2 / m, ramp(t2, T0, RAMP, 0.0, 1.0), lw=2, color="tab:green",
         label="hold = t0 = 163 500 000\n(рампа проходит заново)")
ax2.set_xlabel("абсолютный шаг, млн")
ax2.set_ylabel("terrain (уровень рельефа)")
ax2.set_title("тот же schedule при --resume\nсо 163.5 млн", fontsize=10)
ax2.set_xlim(T0 / m, (T0 + RUN) / m)
ax2.set_ylim(-0.05, 1.12)
ax2.grid(alpha=0.3)
ax2.legend(loc="lower right", fontsize=8)

fig.tight_layout()
fig.savefig(OUT, dpi=110)
print("saved", OUT)
