"""ЛОВУШКА: совпадение размерностей — это НЕ совместимость.

СЮЖЕТ
-----
В `policies/` лежат двое весов с ОДИНАКОВОЙ сигнатурой
`Box(35,)` / `Box(8,)`:

    walk_60M.zip        — наши, машина R4 (33 кг, таз 0.4272 м)
    foreign_r3_59M.zip  — ЧУЖИЕ, машина R3 (~5 кг, таз 0.1445 м),
                          соседняя ветка того же проекта

`PPO.load` принимает обоих. Ошибки нет. Предупреждения нет. Один ходит
двадцать секунд без падений, второй роняет машину за полсекунды — то
есть работает ХУЖЕ, чем «ничего не делать».

ЗАЧЕМ ЭТО В КУРСЕ
-----------------
Это самая дорогая ошибка при работе с чужими весами, и она не ловится
ни исключением, ни типами. Ловится она ровно одной проверкой, которую
надо делать ВСЕГДА и ПЕРВОЙ:

    политика обязана быть лучше НУЛЕВОГО ДЕЙСТВИЯ.

Пассивная база меряется `rl_toolkit.diagnostics.null_policy_baseline`.
Если политика живёт меньше — она не управляет, она мешает.

Та же ловушка бывает и внутри своего проекта: в исходном репозитории
каталоги `runs_walk_r4` и `runs_walk_r4b` — архив УСТАРЕВШЕЙ 168-мм
версии той же машины, их чекпойнты тоже грузятся и тоже живут 0.55 с
(08_track_b.md, раздел 3).

ЗАПУСК
------
    python trap.py                 # боевая среда, эпизод 20 с
    python trap.py --env simple    # учебная среда, эпизод 6 с
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from rl_toolkit.checkpointing import CheckpointPair, load_policy  # noqa: E402
from rl_toolkit.diagnostics import Table, null_policy_baseline  # noqa: E402

CMD = 0.4       # м/с — та же команда, на которой снят паспорт политики 60M


def env_factory(kind: str, cmd: float):
    """Одна и та же среда для всех трёх претендентов — иначе сравнение
    ничего не значит."""
    if kind == "full":
        from walk_env_full import make_full_env
        return lambda: make_full_env(cmd_vx=cmd, randomize=False, seed=0)
    from walk_env import WalkEnv

    def _make():
        env = WalkEnv(seed=0)
        env.set_cmd_vx(cmd)
        return env
    return _make


def run_policy(env_fn, pair: CheckpointPair, episodes: int, seed0: int = 0):
    """Прогон политики: длины эпизодов и суммарная награда."""
    model, norm = load_policy(pair)
    env = env_fn()
    lens, rets = [], []
    for ep in range(episodes):
        obs, _ = env.reset(seed=seed0 + ep)
        total = 0.0
        i = 0
        for i in range(env.max_steps):
            act, _ = model.predict(norm(obs), deterministic=True)
            obs, r, terminated, truncated, _ = env.step(act)
            total += float(r)
            if terminated or truncated:
                break
        lens.append(i + 1)
        rets.append(total)
    env.close()
    return lens, rets


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=("full", "simple"), default="full")
    ap.add_argument("--episodes", type=int, default=5)
    args = ap.parse_args()

    env_fn = env_factory(args.env, CMD)
    probe = env_fn()
    dt, max_steps = probe.dt, probe.max_steps
    ep_s = max_steps * dt
    probe.close()
    print(f"среда «{args.env}»: эпизод {max_steps} шагов = {ep_s:.1f} с, "
          f"команда {CMD} м/с, {args.episodes} эпизодов\n")

    # --- 1. ПАССИВНАЯ БАЗА: то, с чем обязана сравниваться любая политика
    base = null_policy_baseline(env_fn, seconds=ep_s, n=args.episodes)
    print(f"пассивная база (действие 0): {base['alive_steps']:.1f} шагов = "
          f"{base['alive_s']:.2f} с, награда {base['return']:.1f}")

    # --- 2. ДВЕ ПАРЫ ВЕСОВ --------------------------------------------
    own = CheckpointPair(60_000_000, HERE / "policies" / "walk_60M.zip",
                         HERE / "policies" / "walk_60M_vecnorm.pkl", "ПАРНЫЙ")
    foreign = CheckpointPair(58_999_794,
                             HERE / "policies" / "foreign_r3_59M.zip",
                             HERE / "policies" / "foreign_r3_59M_vecnorm.pkl",
                             "ПАРНЫЙ")

    print("\nСИГНАТУРЫ (то, по чему обычно и делают вывод «подходит»):")
    from stable_baselines3 import PPO
    for name, pair in (("свои  R4 60M", own), ("ЧУЖИЕ R3 59M", foreign)):
        m = PPO.load(str(pair.model_path), device="cpu")
        print(f"  {name}: obs {m.observation_space}  act {m.action_space}")
    print("  -> совпадают ПОЛНОСТЬЮ. Никакой ошибки при загрузке не будет.\n")

    tab = Table(
        title="ЧТО НА САМОМ ДЕЛЕ ДЕЛАЮТ ЭТИ ВЕСА",
        columns=["претендент", "эпизоды, шагов", "жизнь, с",
                 "награда", "против пассивной"],
        rows=[],
        note="",
    )
    tab.add(**{
        "претендент": "нулевое действие",
        "эпизоды, шагов": str([int(base["alive_steps"])] * 1),
        "жизнь, с": f"{base['alive_s']:.2f}",
        "награда": f"{base['return']:.1f}",
        "против пассивной": "= 1.00 (это и есть база)",
    })
    verdicts = {}
    for name, pair in (("свои R4 60M", own), ("ЧУЖИЕ R3 59M", foreign)):
        lens, rets = run_policy(env_fn, pair, args.episodes)
        alive_s = float(np.mean(lens)) * dt
        ratio = alive_s / base["alive_s"]
        verdicts[name] = ratio
        tab.add(**{
            "претендент": name,
            "эпизоды, шагов": str(lens),
            "жизнь, с": f"{alive_s:.2f}",
            "награда": f"{float(np.mean(rets)):.1f}",
            "против пассивной": f"x {ratio:.2f}"
                                + ("" if ratio >= 1.0 else "  ХУЖЕ, ЧЕМ НИЧЕГО"),
        })
    print(tab)

    print("\nВЫВОД:")
    for name, ratio in verdicts.items():
        if ratio >= 1.0:
            print(f"  {name}: живёт в {ratio:.1f} раза дольше пассивной машины — управляет.")
        else:
            print(f"  {name}: живёт в {1/ratio:.1f} раза МЕНЬШЕ пассивной машины — "
                  f"не управляет, мешает.")
    print("\nОбе пары загрузились без единой ошибки. Разницу показал только "
          "\nзамер против нулевого действия. Делайте его ПЕРВЫМ.")
    print("Паспорт чужих весов — policies/foreign_r3_59M_manifest.txt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
