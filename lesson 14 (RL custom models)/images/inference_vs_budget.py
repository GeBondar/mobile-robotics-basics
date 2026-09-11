# -*- coding: utf-8 -*-
"""Инференс ONNX против бюджета шага управления.

Все числа взяты из главы 09_sim2real.md (замеры на машине курса,
onnxruntime 1.26.0, intra_op_num_threads=1, CPUExecutionProvider):

  hover      : медиана 28.0 мкс, p99 60.4 мкс  (раздел 3, вывод скрипта)
  walk_60M   : медиана 32.3 мкс, p99 62.3 мкс  (раздел 3, абзац про --obs-dim 35)
  Microduck  : медианы девяти политик 20.3...23.2 мкс, p99 не публиковался (раздел 4)
  бюджет шага 50 Гц = 20 000 мкс (разделы 3 и 8)

Пересборка:  python inference_vs_budget.py
"""
import matplotlib.pyplot as plt
import numpy as np

BUDGET_US = 20_000.0  # шаг 50 Гц

names = ["hover\nobs[1,19] -> act[1,4]",
         "walk_60M\nobs[1,35] -> act[1,8]",
         "Microduck, 9 политик\nobs[1,61] -> act[1,14]"]
median = [28.0, 32.3, None]      # у Microduck опубликован диапазон медиан
p99 = [60.4, 62.3, None]
md_lo, md_hi = 20.3, 23.2

fig, ax = plt.subplots(figsize=(8, 4.5))
x = np.arange(len(names))
w = 0.34

ax.bar(x[:2] - w / 2, median[:2], w, label="медиана")
ax.bar(x[:2] + w / 2, p99[:2], w, label="p99")
ax.bar(x[2], md_hi - md_lo, w, bottom=md_lo, hatch="//",
       label="Microduck: диапазон медиан 9 политик")

for xi, m, p in zip(x[:2], median[:2], p99[:2]):
    ax.text(xi - w / 2, m * 1.12, f"{m:.1f}", ha="center", fontsize=9)
    ax.text(xi + w / 2, p * 1.12, f"{p:.1f}", ha="center", fontsize=9)
ax.text(x[2], md_hi * 1.15, f"{md_lo:.1f}…{md_hi:.1f}", ha="center", fontsize=9)

ax.axhline(BUDGET_US, linestyle="--", color="crimson")
ax.text(-0.45, BUDGET_US * 1.25,
        "бюджет шага 50 Гц = 20 000 мкс", ha="left", color="crimson", fontsize=10)
ax.text(-0.45, 900.0,
        "медиана hover — 0.14 % бюджета:\nсеть не узкое место контура",
        ha="left", fontsize=9, color="gray")

ax.set_yscale("log")
ax.set_xlim(-0.6, len(names) - 0.4)
ax.set_ylim(8, 80_000)
ax.set_ylabel("время одного вызова, мкс (логарифмическая шкала)")
ax.set_xticks(x)
ax.set_xticklabels(names, fontsize=9)
ax.set_title("Инференс ONNX на CPU в одном потоке против бюджета шага")
ax.legend(loc="upper right", fontsize=9)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig("inference_vs_budget.png", dpi=110)
