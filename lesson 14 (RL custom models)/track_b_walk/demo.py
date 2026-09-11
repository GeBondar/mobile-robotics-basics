"""ЭТАЛОН: запуск готовой политики 60M и сверка с её паспортом.

ЧТО ЭТО ПОКАЗЫВАЕТ
------------------
Куда студент идёт. Политика обучалась 60 млн шагов / 4.63 часа на 8
средах CPU (`policies/manifest.txt`). Здесь она грузится за секунды и
проходит свип команд 0 / 0.2 / 0.4 / 0.6 / 0.8 м/с — а в конце скрипт
сам сравнивает полученные числа с паспортом.

ГЛАВНОЕ ПРАВИЛО, РАДИ КОТОРОГО ЭТОТ СКРИПТ НАПИСАН ИМЕННО ТАК
-------------------------------------------------------------
Веса грузятся ТОЛЬКО ПАРОЙ: `walk_60M.zip` + `walk_60M_vecnorm.pkl`.
`.pkl` — это статистика нормализации наблюдений (VecNormalize). Без неё
политика получает вход в другом масштабе; это не «чуть хуже», это другая
политика. Поэтому пара собирается явным `CheckpointPair`, а нормализация
берётся из `rl_toolkit.checkpointing.load_policy`, который читает pkl
напрямую (среда для чтения статистики не нужна) и ГРОМКО ругается, если
пары нет.

Проверить, что будет без пары, можно флагом `--no-vecnorm`.

ЗАПУСК
------
    python demo.py                    # свип 5 команд, 3 эпизода по 20 с
    python demo.py --episodes 10      # как в паспорте
    python demo.py --env simple       # то же в УЧЕБНОЙ среде (эпизод 6 с)
    python demo.py --no-vecnorm       # показать цену потери pkl
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
from rl_toolkit.diagnostics import Table  # noqa: E402

# Паспортные метрики из policies/manifest.txt (честный eval, 1g, 10 эпизодов,
# ровный пол, боевая среда). Это НЕ «ожидаемые» числа, а замер автора весов;
# скрипт сверяет с ними то, что получилось на машине студента.
MANIFEST = {0.0: 0.008, 0.2: 0.201, 0.4: 0.358, 0.6: 0.533, 0.8: 0.694}
# Свип, воспроизведённый при разборе проекта на ЭТОЙ машине
# (08_track_b.md, раздел 3, 3 эпизода по 20 с, randomize=False)
REPORT_08 = {0.0: 0.006, 0.2: 0.201, 0.4: 0.369, 0.6: 0.527, 0.8: 0.686}


def make_pair(with_vecnorm: bool = True) -> CheckpointPair:
    """Пара «веса + нормализация». `note` — не украшение: `load_policy`
    печатает предупреждение, если пара неполная или подобрана по соседству."""
    zip_path = HERE / "policies" / "walk_60M.zip"
    pkl_path = HERE / "policies" / "walk_60M_vecnorm.pkl"
    if not zip_path.exists():
        raise FileNotFoundError(f"нет весов {zip_path}")
    return CheckpointPair(
        steps=60_000_000,
        model_path=zip_path,
        vecnorm_path=pkl_path if with_vecnorm else None,
        note="ПАРНЫЙ" if with_vecnorm else "НЕТ",
    )


def rollout(env, model, norm, episodes: int, seed0: int = 100):
    """Прогон политики. Возвращает (список длин эпизодов, средняя vx, снос по Y).

    Скорость меряется в ГОРИЗОНТАЛЬНОЙ РАМЕ КОРПУСА, а не по мировой оси:
    машина может ехать под углом, и мировая проекция завысит результат.
    """
    from walk_env_full import body_vx
    lens, vxs, dys = [], [], []
    for ep in range(episodes):
        obs, _ = env.reset(seed=seed0 + ep)
        y0 = float(env.data.qpos[1])
        vlog = []
        i = 0
        for i in range(env.max_steps):
            act, _ = model.predict(norm(obs), deterministic=True)
            obs, r, terminated, truncated, _ = env.step(act)
            vlog.append(body_vx(env))
            if terminated or truncated:
                break
        lens.append(i + 1)
        vxs.append(float(np.mean(vlog)) if vlog else 0.0)
        dys.append(abs(float(env.data.qpos[1]) - y0))
    return lens, float(np.mean(vxs)), float(np.mean(dys))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=3,
                    help="эпизодов на команду (в паспорте 10)")
    ap.add_argument("--env", choices=("full", "simple"), default="full",
                    help="full — боевая среда (эпизод 20 с, как в паспорте); "
                         "simple — учебная (6 с)")
    ap.add_argument("--no-vecnorm", action="store_true",
                    help="грузить БЕЗ парного pkl — показать цену ошибки")
    ap.add_argument("--cmds", type=float, nargs="*",
                    default=[0.0, 0.2, 0.4, 0.6, 0.8])
    args = ap.parse_args()

    pair = make_pair(with_vecnorm=not args.no_vecnorm)
    print(f"чекпойнт : {pair.model_path.name}  ({pair.model_path.stat().st_size/1e6:.3f} МБ)")
    print(f"нормировка: {pair.vecnorm_path.name if pair.vecnorm_path else 'НЕТ — политика мертва'}")
    print(f"пара полная: {pair.paired}\n")

    model, norm = load_policy(pair)
    print(f"observation_space весов: {model.observation_space}")
    print(f"action_space весов     : {model.action_space}")
    # log_std — ширина разведки. У зрелой политики она мала: 60M шагов
    # довели её до 0.057 (08_track_b.md, раздел 3). Это важно знать, если
    # соберётесь ДООБУЧАТЬ: такая политика не может перестроиться без
    # искусственного расширения std (в боевом тренере это флаг --std-add).
    log_std = float(np.mean(model.policy.log_std.detach().cpu().numpy()))
    print(f"log_std (среднее)      : {log_std:.4f}  ->  std {np.exp(log_std):.4f}\n")

    tab = Table(
        title=f"СВИП КОМАНД, политика 60M, среда «{args.env}», "
              f"{args.episodes} эпизодов",
        columns=["команда, м/с", "достигнуто, м/с", "слежение, %",
                 "полных эпизодов", "падений", "снос |dy|, м", "паспорт, м/с"],
        rows=[],
    )
    for cmd in args.cmds:
        if args.env == "full":
            from walk_env_full import make_full_env
            env = make_full_env(cmd_vx=cmd, randomize=False, seed=0)
        else:
            from walk_env import WalkEnv
            env = WalkEnv(seed=0)
            env.set_cmd_vx(cmd)
        lens, vx, dy = rollout(env, model, norm, args.episodes)
        full = sum(1 for L in lens if L >= env.max_steps)
        falls = args.episodes - full
        ratio = (vx / cmd * 100.0) if abs(cmd) > 1e-6 else float("nan")
        tab.add(**{
            "команда, м/с": f"{cmd:.1f}",
            "достигнуто, м/с": f"{vx:.3f}",
            "слежение, %": "—" if np.isnan(ratio) else f"{ratio:.1f}",
            "полных эпизодов": f"{full}/{args.episodes}",
            "падений": falls,
            "снос |dy|, м": f"{dy:.2f}",
            "паспорт, м/с": f"{MANIFEST.get(round(cmd, 2), float('nan')):.3f}",
        })
        env.close()
    print(tab)

    # --- сверка с паспортом -------------------------------------------
    if args.env == "full" and not args.no_vecnorm:
        print("\nСВЕРКА С ПАСПОРТОМ (policies/manifest.txt) и с отчётом разбора:")
        worst = 0.0
        for row in tab.rows:
            cmd = float(row["команда, м/с"])
            got = float(row["достигнуто, м/с"])
            ref_m = MANIFEST.get(round(cmd, 2))
            ref_r = REPORT_08.get(round(cmd, 2))
            dm, dr = abs(got - ref_m), abs(got - ref_r)
            worst = max(worst, dr)
            print(f"  cmd {cmd:.1f}: получено {got:.3f}   "
                  f"паспорт {ref_m:.3f} (D {dm:.3f})   "
                  f"отчёт 08 {ref_r:.3f} (D {dr:.3f})")
        print(f"\n  худшее расхождение с отчётом 08: {worst:.3f} м/с")
        print("  ВЫВОД: " + (
            "числа воспроизведены — пара весов рабочая."
            if worst <= 0.02 else
            "ЧИСЛА НЕ СОШЛИСЬ. Проверьте, что грузится ПАРА и что среда боевая."))
        print("\n  Почему паспорт и отчёт немного расходятся на 0.4 и 0.6:")
        print("  паспорт снят по 10 эпизодам, отчёт и этот запуск — по 3.")
        print("  Это разброс выборки, а не другой результат.")
    if args.no_vecnorm:
        print("\nЭто прогон БЕЗ парного pkl. Сравните с обычным запуском:")
        print("сигнатура весов совпала, ошибки не было — а походки нет.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
