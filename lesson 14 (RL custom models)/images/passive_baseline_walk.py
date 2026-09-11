# -*- coding: utf-8 -*-
"""Длина эпизода трека B как функция числа шагов обучения, рядом с пассивной базой.

Числа — из `evaluations.npz` боевого прогона трека B (честный 1g, 20 эпизодов
на точку, максимум 1000 шагов = 20 с); те же точки приведены в таблице главы
06_diagnostics.md. Пассивная база 53 шага = 1.06 с воспроизведена независимо
в walk_env.py, probe.py, trap.py и train.py (разброс между эпизодами 0.000 с).
Ничего не интерполируется: рисуются ровно замеренные точки.
"""
import os
import matplotlib.pyplot as plt

# шагов обучения, млн
steps = [0.5, 2.0, 4.0, 6.5, 8.0, 10.0, 12.0, 13.0,
         13.5, 14.0, 16.5, 20.0, 25.0, 30.0, 60.0]
# средняя длина эпизода, шагов
ep_len = [53.0, 53.0, 53.0, 53.0, 62.0, 50.2, 59.2, 79.0,
          587.4, 904.0, 1000.0, 897.5, 1000.0, 1000.0, 1000.0]

PASSIVE = 53.0          # пассивный эпизод, нулевое действие
FPS = 3611.0            # шагов/с на этой машине -> часы на оси сверху

fig, ax = plt.subplots(figsize=(8, 4.5), dpi=110)
ax.plot(steps, ep_len, marker="o", label="обученная политика, ep_length")
ax.axhline(PASSIVE, linestyle="--", color="0.35",
           label="пассивная база (нулевое действие): 53 шага = 1.06 с")
ax.axvline(13.5, linestyle=":", color="0.6")
ax.annotate("перелом: 13.5 млн шагов\n(1 ч 02 мин при 3611 шагов/с)",
            xy=(13.5, 587.4), xytext=(20.0, 430.0),
            arrowprops=dict(arrowstyle="->", color="0.3"))
ax.annotate("13 точек подряд ровно 53.0:\nполитика = «ничего не делать»",
            xy=(6.5, 53.0), xytext=(2.0, 250.0),
            arrowprops=dict(arrowstyle="->", color="0.3"))

ax.set_xlabel("шагов обучения, млн")
ax.set_ylabel("длина эпизода, шагов (потолок 1000 = 20 с)")
ax.set_title("Трек B: длина эпизода против пассивной базы")
ax.set_ylim(0, 1100)
ax.grid(True, alpha=0.3)
ax.legend(loc="lower right")

secx = ax.secondary_xaxis(
    "top", functions=(lambda s: s * 1e6 / FPS / 3600.0,
                      lambda h: h * 3600.0 * FPS / 1e6))
secx.set_xlabel("часов обучения при 3611 шагов/с")

fig.tight_layout()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "passive_baseline_walk.png")
fig.savefig(out)
print(out)
