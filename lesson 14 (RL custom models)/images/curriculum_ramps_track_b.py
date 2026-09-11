# -*- coding: utf-8 -*-
"""Расписание рамп трека B на учебном бюджете 6 млн шагов.

Числа взяты из track_b_walk/train.py, build_schedule():
    set_gravity_scale: linear(hold=0.05*total, ramp=0.45*total, lo=0.35, hi=1.0)
    set_cmd_scale:     linear(hold=0.05*total, ramp=0.70*total, lo=0.0,  hi=1.0)
Формула значения рампы — rl_toolkit/curriculum.py:148-150.

Пересборка:  python curriculum_ramps_track_b.py
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = "curriculum_ramps_track_b.png"


def ramp(t, hold, length, lo, hi):
    """rl_toolkit/curriculum.py:148-150."""
    x = np.clip((t - hold) / float(length), 0.0, 1.0)
    return lo + (hi - lo) * x


total = 6_000_000
hold = int(0.05 * total)                      # 300 000
g_ramp = max(1, int(0.45 * total))            # 2 700 000
c_ramp = max(1, int(0.70 * total))            # 4 200 000

t = np.linspace(0, total, 2001)
g = ramp(t, hold, g_ramp, 0.35, 1.0)
c = ramp(t, hold, c_ramp, 0.0, 1.0)

m = 1e6
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.axvspan(0, hold / m, color="0.85",
           label="hold = 5 %% бюджета (%d шагов)" % hold)
ax.plot(t / m, g, lw=2, label="set_gravity_scale  0.35 -> 1.0  (в eval НЕ уходит)")
ax.plot(t / m, c, lw=2, label="set_cmd_scale  0.0 -> 1.0  (в eval уходит)")

for x_end, txt in (((hold + g_ramp) / m, "1g на 3.0 млн (50 % бюджета)"),
                   ((hold + c_ramp) / m, "полная команда на 4.5 млн (75 %)")):
    ax.axvline(x_end, color="0.4", ls="--", lw=1)
    ax.annotate(txt, xy=(x_end, 0.55), xytext=(x_end - 0.08, 0.55),
                rotation=90, ha="right", va="center", fontsize=9, color="0.25")

ax.set_xlabel("абсолютный шаг обучения, млн env-шагов")
ax.set_ylabel("значение ручки")
ax.set_title("Куррикулум трека B: рампы заданы в долях бюджета (6 млн шагов)")
ax.set_xlim(0, total / m)
ax.set_ylim(-0.03, 1.08)
ax.grid(alpha=0.3)
ax.legend(loc="lower right", fontsize=9)
fig.tight_layout()
fig.savefig(OUT, dpi=110)
print("saved", OUT)
