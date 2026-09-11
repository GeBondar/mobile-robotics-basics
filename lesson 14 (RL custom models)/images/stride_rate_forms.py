"""Ставка члена награды за длину шага как функция самой длины шага.

Числа НЕ выдуманы: это ровно та самоproverka, что печатает
`python -m rl_toolkit.diagnostics` (rl_toolkit/diagnostics.py:585-680) —
dt = 0.02 c, вес W = 8, команда v = 0.25 м/с, потолок L_cap = 0.30 м,
правильная форма с порогом l0 = 0.09 м и потолком l_max = 0.40 м.

Формулы взяты из pay_cap()/pay_offset() того же файла. В установившейся
ходьбе L*f = v, посадок в секунду 2f, поэтому

    ставка_cap(L)    = 2*W*(v/L) * min(L/L_cap, 1)
    ставка_offset(L) = 2*W*(v/L) * (min(L, l_max) - l0)

Контрольные точки, совпадающие с выводом диагностики:
    cap:    L=0.058 -> 13.3333/с, L=0.300 -> 13.3333/с, L=0.450 -> 8.8889/с
    offset: L=0.058 -> -2.2069/с, L=0.100 -> 0.4000/с,
            L=0.400 -> 3.1000/с,  L=0.450 -> 2.7556/с

Пересборка:  python images/stride_rate_forms.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

W = 8.0
V_CMD = 0.25
L_CAP = 0.30
L0, LMAX = 0.09, 0.40


def rate_cap(L):
    return 2.0 * W * (V_CMD / L) * np.minimum(L / L_CAP, 1.0)


def rate_offset(L):
    return 2.0 * W * (V_CMD / L) * (np.minimum(L, LMAX) - L0)


L = np.linspace(0.04, 0.50, 400)

fig, ax = plt.subplots(figsize=(8, 4.5), dpi=110)

ax.axhline(0.0, color="black", linewidth=0.8)
ax.plot(L, rate_cap(L), label="плата min(L/L_cap, 1), L_cap = 0.30 м")
ax.plot(L, rate_offset(L), label="плата min(L, 0.40) - 0.09")

# точки, вокруг которых идёт разбор в главе
for x, fn, txt, dy in (
    (0.058, rate_cap, "13.33/с", 1.1),
    (0.300, rate_cap, "13.33/с", 1.1),
    (0.058, rate_offset, "-2.21/с", -1.4),
    (0.400, rate_offset, "3.10/с", 1.1),
):
    y = float(fn(np.array([x]))[0])
    ax.plot([x], [y], marker="o", color="black", markersize=4, zorder=5)
    ax.annotate(txt, (x, y), textcoords="offset points",
                xytext=(4, 10 * dy), fontsize=9)

ax.axvline(0.058, color="gray", linestyle=":", linewidth=1.0)
ax.axvline(L0, color="gray", linestyle="--", linewidth=1.0)
ax.text(0.062, 17.2, "семенение\n0.058 м", fontsize=9, color="gray", va="top")
ax.text(0.098, -4.7, "порог l0 = 0.09 м", fontsize=9, color="gray")

ax.set_xlabel("длина шага L, м  (скорость задана командой: L*f = 0.25 м/с)")
ax.set_ylabel("ставка члена, награда/с")
ax.set_title("Форма платы за длину шага: где есть градиент, а где его нет")
ax.set_xlim(0.04, 0.50)
ax.set_ylim(-5.4, 17.5)
ax.grid(True, alpha=0.3)
ax.legend(loc="center right", fontsize=9)

fig.tight_layout()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stride_rate_forms.png")
fig.savefig(out)
print("saved:", out)

# контроль: печатаем те же числа, что и диагностика
for x in (0.058, 0.100, 0.300, 0.400, 0.450):
    print(f"L={x:.3f}  cap={float(rate_cap(np.array([x]))[0]):8.4f}/с"
          f"  offset={float(rate_offset(np.array([x]))[0]):8.4f}/с")
