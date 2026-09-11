# -*- coding: utf-8 -*-
"""Стоимость терминальной награды +100 в дисконтированной цели как функция gamma.

Все числа взяты из главы 02_gym_env.md, §5 (таблица пробы 4 из track_a_car/probe.py):
  старая (100 Гц): dt = 0.01 с, медианный шаг успеха 460, 100 * 0.99^460  = 0.98
  новая  (20 Гц):  dt = 0.05 с, типичный шаг успеха  60, 100 * 0.99^60   = 54.72
                                                         100 * 0.995^60  = 74.03
                                                         100 * 0.999^60  = 94.17
Кривые — та же формула 100 * gamma**k при тех же k. Ничего не выдумано.

Пересборка: python images/gamma_terminal_value.py
"""
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

K_OLD, K_NEW = 460, 60  # шаг политики, на котором приходит +100
R_TERM = 100.0

g = np.linspace(0.980, 0.9995, 600)

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(g, R_TERM * g ** K_NEW, label="dt = 0.05 с (20 Гц), успех на шаге 60")
ax.plot(g, R_TERM * g ** K_OLD, label="dt = 0.01 с (100 Гц), успех на шаге 460")

pts = [
    (0.990, R_TERM * 0.990 ** K_OLD, "0.98\n(старая, 100 Гц)", (10, 16)),
    (0.990, R_TERM * 0.990 ** K_NEW, "54.72", (10, -18)),
    (0.995, R_TERM * 0.995 ** K_NEW, "74.03\n(выбрано)", (-12, -38)),
    (0.999, R_TERM * 0.999 ** K_NEW, "94.17", (-52, 6)),
]
for x, y, text, off in pts:
    ax.plot([x], [y], "o", color="black", markersize=5, zorder=5)
    ax.annotate(text, (x, y), textcoords="offset points", xytext=off, fontsize=9)

ax.set_xlabel("gamma")
ax.set_ylabel("вклад терминальной награды +100\nв дисконтированную цель")
ax.set_title("Что остаётся от +100 к началу манёвра")
ax.set_xlim(0.980, 0.9995)
ax.set_ylim(-4, 108)
ax.grid(True, alpha=0.3)
ax.legend(loc="upper left", fontsize=9)
fig.tight_layout()
fig.savefig("images/gamma_terminal_value.png", dpi=110)
print("ok")
