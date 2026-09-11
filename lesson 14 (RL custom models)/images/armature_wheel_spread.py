"""Разброс угловой скорости колеса при разных armature.

Числа взяты дословно из замера, приведённого в 01_mjcf_model.md, §4
(круг, полный газ, последние 2 с моделирования, car_parking.xml):

    armature=0.01 (урок)  : w 17.483 рад/с (от  16.991 до 18.139), v кузова 0.940 м/с
    armature=0            : w 17.367 рад/с (от -11.722 до 45.016), v кузова 0.822 м/с
    armature=0.001        : w 17.012 рад/с (от  16.253 до 18.044), v кузова 0.888 м/с

Команда привода: 16.667 рад/с (ctrlrange +-16.6667 в car_parking.xml).

Пересборка:  python armature_wheel_spread.py
"""

import matplotlib.pyplot as plt

CMD = 16.667  # рад/с, команда velocity-привода

# (подпись, среднее, минимум, максимум, скорость кузова)
DATA = [
    ("armature = 0.01\n(модель урока)", 17.483, 16.991, 18.139, 0.940),
    ("armature = 0.001", 17.012, 16.253, 18.044, 0.888),
    ("armature = 0", 17.367, -11.722, 45.016, 0.822),
]

fig, ax = plt.subplots(figsize=(8, 4.5), dpi=110)

xs = range(len(DATA))
for x, (_, mean, lo, hi, _v) in zip(xs, DATA):
    ax.vlines(x, lo, hi, linewidth=10, alpha=0.35, color="tab:blue")
    ax.plot([x], [mean], marker="o", color="tab:blue", zorder=3)
    ax.annotate(f"макс {hi:.1f}", (x, hi), textcoords="offset points",
                xytext=(12, 3), fontsize=9)
    ax.annotate(f"мин {lo:.1f}", (x, lo), textcoords="offset points",
                xytext=(12, -11), fontsize=9)

ax.axhline(CMD, color="tab:red", linestyle="--", linewidth=1.2)
ax.annotate(f"команда привода {CMD:.3f} рад/с", (1.55, CMD),
            textcoords="offset points", xytext=(0, 7), ha="left",
            fontsize=9, color="tab:red")

for x, (_, _m, lo, _hi, v) in zip(xs, DATA):
    ax.annotate(f"скорость кузова {v:.3f} м/с", (x, -17),
                ha="center", fontsize=9)

ax.set_xticks(list(xs))
ax.set_xticklabels([d[0] for d in DATA])
ax.set_ylabel("угловая скорость колеса, рад/с")
ax.set_title("Колесо на полном газу: разброс за последние 2 с прогона по кругу")
ax.set_ylim(-20, 50)
ax.set_xlim(-0.5, 2.65)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig("armature_wheel_spread.png")
print("saved armature_wheel_spread.png")
