# -*- coding: utf-8 -*-
"""Ставка члена r_stride в награду/с как функция длины шага.

Числа взяты из таблицы записи №2 главы 08_pitfalls.md (вывод sweep_term +
gradient_report тулкита урока: dt = 0.005 с, v = 0.30 м/с, W = 8).
Ничего не досчитывается и не интерполируется — рисуются ровно те четыре точки.
"""
import os
import matplotlib.pyplot as plt

stride = [0.06, 0.12, 0.20, 0.30]        # длина шага, м
rate_cap = [16.0, 16.0, 16.0, 16.0]      # плата min(L / L_cap, 1) за посадку
rate_thr = [-9.60, -2.40, 0.48, 1.92]    # плата (L - L0) за посадку, L0 = 0.18 м

fig, ax = plt.subplots(figsize=(8, 4.5), dpi=110)
ax.axhline(0.0, linewidth=0.8, color="0.6")
ax.plot(stride, rate_cap, marker="o",
        label="min(L / L_cap, 1): размах 3.6e-15 — градиента НЕТ")
ax.plot(stride, rate_thr, marker="s",
        label="(L - L0), L0 = 0.18 м: -9.60 -> +1.92 — градиент есть")
ax.axvline(0.18, linestyle=":", linewidth=1.0, color="0.4")
ax.annotate("порог L0 = 0.18 м", xy=(0.183, 9.5), fontsize=9)

ax.set_xlabel("Длина шага L, м")
ax.set_ylabel("Ставка члена награды, награда/с")
ax.set_title("Ставка r_stride в единицу времени как функция длины шага")
ax.legend(loc="lower right", fontsize=9)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "stride_reward_gradient.png"))
