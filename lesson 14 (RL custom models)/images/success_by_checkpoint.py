# -*- coding: utf-8 -*-
"""Успех по чекпойнтам полного прогона трека A (3 млн шагов, 8 сред).

Данные — таблица из track_a_car/README.md, раздел «Результат полного прогона
(3 000 000 шагов, 8 сред, 16.7 мин)»: каждый чекпойнт оценён на 40 эпизодах
набора ОТЧЁТА (seed'ы, которых модель при обучении не видела).
Интервал Уилсона 95 % считается здесь же из тех же (успехи, n), формула —
та же, что в track_a_car/evaluate.py:56-68.

Пересобрать:  python success_by_checkpoint.py
"""
import math
import os

import matplotlib.pyplot as plt

# (шагов обучения, доля успеха в %) — track_a_car/README.md
STEPS = [300_000, 600_000, 900_000, 1_200_000, 1_500_000, 1_800_000,
         2_100_000, 2_400_000, 2_700_000, 3_000_000]
SUCCESS_PCT = [55.0, 82.5, 97.5, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 97.5]
N_EPISODES = 40  # эпизодов на каждый чекпойнт, набор ОТЧЁТА


def wilson(successes, n, z=1.96):
    """Доверительный интервал Уилсона для доли (как в evaluate.py)."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def main():
    lo_err, hi_err = [], []
    for pct in SUCCESS_PCT:
        successes = round(pct / 100.0 * N_EPISODES)
        lo, hi = wilson(successes, N_EPISODES)
        lo_err.append(pct - lo * 100.0)
        hi_err.append(hi * 100.0 - pct)

    x = [s / 1e6 for s in STEPS]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.errorbar(x, SUCCESS_PCT, yerr=[lo_err, hi_err], fmt='o-',
                capsize=4, linewidth=1.6, markersize=5,
                label='успех на наборе отчёта (40 эпизодов, ус — ДИ Уилсона 95 %)')
    ax.axhline(100.0, linestyle='--', linewidth=1.0, color='gray')
    ax.axvline(1.2, linestyle=':', linewidth=1.2, color='tab:green')
    ax.annotate('задача решена,\nдальше плато', xy=(1.2, 62), xytext=(1.32, 58),
                fontsize=9, color='tab:green')
    ax.annotate('последний чекпойнт\n97.5 %, хуже восьми предыдущих',
                xy=(3.0, 97.5), xytext=(1.75, 84),
                fontsize=9, color='tab:red',
                arrowprops=dict(arrowstyle='->', color='tab:red', linewidth=1.2))

    ax.set_xlabel('шагов обучения, млн')
    ax.set_ylabel('доля успешных парковок, %')
    ax.set_title('Трек A: успех по чекпойнтам прогона на 3 млн шагов')
    ax.set_ylim(40, 108)
    ax.set_xticks(x)
    ax.set_xticklabels([f'{v:.1f}' for v in x])
    ax.grid(alpha=0.3)
    ax.legend(loc='lower right', fontsize=9)
    fig.tight_layout()

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'success_by_checkpoint.png')
    fig.savefig(out, dpi=110)
    print('сохранено:', out)


if __name__ == '__main__':
    main()
