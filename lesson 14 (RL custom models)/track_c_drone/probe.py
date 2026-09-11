"""Пробы трека C: ЧТО ИЗМЕРЕНО ДО ОБУЧЕНИЯ + пять граблей, специфичных для дрона.

Прогон обучения стоит минуты, проба — секунды. Всё, что можно узнать про среду
без градиентного шага, здесь и узнаётся.

    python probe.py            # всё, ~2-4 минуты
    python probe.py --quick    # без длинных базовых замеров (20 эпизодов x 3)
    python probe.py --part 2   # только один раздел (1..4)

Разделы:
    1. КОНТРАКТ СРЕДЫ   формы, цена шага, условия обрыва, наблюдаемость,
                        члены награды, свип внутреннего контура
    2. ПЛАНКИ ПОЛИТИК   нулевая / случайная / скриптовый облёт — это те числа,
                        которые обученная политика обязана побить
    3. ГРАБЛИ           пять ловушек раздела «дрон» воспроизводятся ЗАМЕРОМ
    4. СВОДКА           светофор

Ни одно число в выводе не взято из чужого отчёта: всё считается здесь.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np
import mujoco

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rl_toolkit.diagnostics import Table, Verdict, gradient_report, sweep_term  # noqa: E402
from rl_toolkit.probes import (probe_action_scale, probe_controller_sweep,      # noqa: E402
                               probe_observability, probe_reward_terms,
                               probe_shapes, probe_step_cost, probe_termination,
                               report)
from rl_toolkit.rewards import Ctx                                              # noqa: E402

from hover_env import HoverEnv, make_hover_env                                  # noqa: E402
from scan_env import (D_SAFE, DroneScanEnv, RAY_MAX, V_MAX, make_scan_env,      # noqa: E402
                      orbit_policy)
from stand import CascadePD, euler_from_quat, fresh, read_passport              # noqa: E402

HERE = Path(__file__).resolve().parent
G = 9.81


# ===========================================================================
# 1. КОНТРАКТ СРЕДЫ
# ===========================================================================
def part1(quick: bool) -> dict:
    out = {}
    print("=" * 78)
    print("РАЗДЕЛ 1. КОНТРАКТ СРЕДЫ")
    print("=" * 78)

    hover = HoverEnv(seed=0)
    scan = DroneScanEnv(seed=0)

    out["C1 формы"] = probe_shapes(hover)
    out["C2 формы"] = probe_shapes(scan)

    # -- цена шага: прямо переводится в часы обучения -----------------------
    out["C1 цена шага"] = probe_step_cost(hover, n=2000)
    out["C2 цена шага"] = probe_step_cost(scan, n=2000)

    # -- условия обрыва: срабатывают ТАМ, где задумано ----------------------
    out["C1 обрывы"] = probe_termination(hover, {
        "ниже нижней границы (z=0.10)": ({"pos": [0.0, 0.0, 0.10]}, True),
        "выше потолка (z=4.50)":        ({"pos": [0.0, 0.0, 4.50]}, True),
        "вылет по x (x=3.50)":          ({"pos": [3.50, 0.0, 1.5]}, True),
        "перевёрнут (крен 180°)":       ({"pos": [0.0, 0.0, 1.5],
                                          "rpy": [math.pi, 0.0, 0.0]}, True),
        "штатная поза":                 ({"pos": [0.0, 0.0, 1.5]}, False),
    })
    out["C2 обрывы"] = probe_termination(scan, {
        "внутри объекта (0,0,1.8)":     ({"pos": [0.0, 0.0, 1.8]}, True),
        "вылет за арену (r=9.5)":       ({"pos": [9.5, 0.0, 2.0]}, True),
        "ниже нижней границы (z=0.2)":  ({"pos": [4.0, 0.0, 0.2]}, True),
        "покрытие 100 % (финиш)":       ({"pos": [4.0, 0.0, 2.0],
                                          "seen_fraction": 1.0}, True),
        "штатный полёт":                ({"pos": [4.0, 0.0, 2.0],
                                          "seen_fraction": 0.0}, False),
    })

    # -- наблюдаемость того, что штрафуем -----------------------------------
    # Штраф `near` считается по расстоянию до габарита объекта. Если бы это
    # расстояние не выводилось из наблюдения, штраф был бы шумом, а не сигналом.
    scan.reset(seed=3)
    out["C2 наблюдаемость d_obj"] = probe_observability(
        scan, quantity=lambda u: u._d_obj(), obs_index=(0, 1, 2, 3), n=250, tol=0.02)
    hover.reset(seed=3)
    out["C1 наблюдаемость |omega|"] = probe_observability(
        hover, quantity=lambda u: float(np.linalg.norm(u.data.qvel[3:6])),
        obs_index=(12, 13, 14), n=250, tol=0.02)

    # -- члены награды на трёх заданных поведениях --------------------------
    scan2 = DroneScanEnv(seed=0, cov_target=1.01)
    pol = orbit_policy()
    st = {"i": 0}

    def orbit_wrap(_obs):
        a = pol(scan2, st["i"])
        st["i"] += 1
        return a

    out["C2 члены: скриптовый облёт"] = probe_reward_terms(scan2, policy=orbit_wrap,
                                                           seconds=24.0, seed=11)
    scan3 = DroneScanEnv(seed=0, cov_target=1.01)
    out["C2 члены: идеальное висение"] = probe_reward_terms(scan3, policy=None,
                                                            seconds=24.0, seed=11)
    out["C1 члены: нулевое действие"] = probe_reward_terms(HoverEnv(seed=0), policy=None,
                                                           seconds=5.0, seed=11)

    # -- градиент членов: плоский член не лечится весом ---------------------
    reg_s = scan.rew
    dt = scan.dt
    t_near = sweep_term(reg_s["near"], "d_obj, м", [0.4, 0.8, 1.0, 1.2, 1.35, 1.6, 2.0],
                        lambda v: Ctx(dt, d_obj=v), dt)
    print(t_near, "\n")
    out["C2 градиент near"] = gradient_report(t_near, higher_is_better=True)

    t_cov = sweep_term(reg_s["cov"], "новых ячеек", [0, 1, 2, 3, 4],
                       lambda v: Ctx(dt, new_cells=v), dt)
    print(t_cov, "\n")
    out["C2 градиент cov"] = gradient_report(t_cov, higher_is_better=True)

    reg_h = hover.rew
    t_pos = sweep_term(reg_h["pos"], "расстояние, м", [0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0],
                       lambda v: Ctx(hover.dt, dist=v), hover.dt)
    print(t_pos, "\n")
    out["C1 градиент pos"] = gradient_report(t_pos, higher_is_better=False)

    # -- свип внутреннего контура: цена «честной» частоты ПД ------------------
    if not quick:
        sw = DroneScanEnv(seed=0, cov_target=1.01)
        st2 = {"i": 0}

        def orbit_wrap2(_obs):
            a = pol(sw, st2["i"])
            st2["i"] += 1
            return a

        def metric_cov(roll):
            st2["i"] = 0
            return float(roll[-1]["info"]["coverage"])

        t_sweep = probe_controller_sweep(sw, orbit_wrap2, "inner_every", [1, 2, 5, 10],
                                         metric=metric_cov, seconds=16.0, episodes=1, seed=5)
        t_sweep.note += ("\nПокрытие от частоты внутреннего контура НЕ зависит, а скорость "
                         "среды зависит вдвое: ПД можно считать раз в шаг среды (50 Гц), "
                         "потому что полоса контура 12 рад/с ≈ 1.9 Гц — 1/26 частоты "
                         "управления")
        out["C2 свип inner_every"] = t_sweep

    hover.close()
    scan.close()
    return out


# ===========================================================================
# 2. ПЛАНКИ ПОЛИТИК
# ===========================================================================
def _run_scan_policy(make_act_fn, n_ep: int, max_steps: int, seed0: int = 700):
    """Прогон политики в среде БЕЗ обрыва по покрытию (cov_target = 1.01).

    ПРАВИЛО, оплаченное сгоревшим замером: метрику качества НЕЛЬЗЯ мерить
    в среде, которая обрывает эпизод ПО ЭТОЙ ЖЕ метрике. Иначе «покрытие»
    в отчёте — это просто значение в момент пересечения порога, и у скрипта
    получается несуществующий «потолок 0.9167».
    """
    covs, t85, crashes, lens = [], [], 0, []
    for ep in range(n_ep):
        # и среда, и политика создаются заново на КАЖДЫЙ эпизод: у скриптового
        # облёта есть внутреннее состояние (номер текущей высоты), и без
        # пересоздания второй эпизод стартовал бы с середины программы
        act_fn = make_act_fn()
        env = DroneScanEnv(seed=0, cov_target=1.01, max_steps=max_steps)
        env.reset(seed=seed0 + ep)
        mark = None
        cov = 0.0
        crashed = False
        i = 0
        for i in range(max_steps):
            _, _, te, tr, info = env.step(act_fn(env, i))
            cov = info["coverage"]
            if mark is None and cov >= 0.85:
                mark = i + 1
            if te or tr:
                crashed = bool(info.get("crash") or info.get("out"))
                break
        covs.append(cov)
        lens.append(i + 1)
        crashes += int(crashed)
        if mark is not None:
            t85.append(mark)
        env.close()
    return {"покрытие за полный эпизод": float(np.mean(covs)),
            "лучший эпизод": float(np.max(covs)),
            "дошли до 0.85": f"{len(t85)}/{n_ep}",
            "шагов до 0.85 (медиана)": (int(np.median(t85)) if t85 else None),
            "доля аварий": crashes / n_ep,
            "средняя длина эпизода": float(np.mean(lens))}


def part2(quick: bool) -> dict:
    out = {}
    n_ep = 5 if quick else 20
    max_steps = 1500
    print("=" * 78)
    print(f"РАЗДЕЛ 2. ПЛАНКИ ПОЛИТИК ({n_ep} эпизодов, cov_target = 1.01 — порог "
          f"НЕДОСТИЖИМ, эпизод идёт все {max_steps} шагов)")
    print("=" * 78)

    rng = np.random.default_rng(0)
    rows = {
        "нулевое действие": lambda: (lambda e, i: np.zeros(4)),
        "случайное действие": lambda: (lambda e, i: rng.uniform(-1, 1, 4)),
        "скриптовый облёт r=1.9": lambda: (lambda e, i, _p=orbit_policy(): _p(e, i)),
    }
    t = Table(title="C2: планки политик",
              columns=["политика", "покрытие", "лучший", "дошли до 0.85",
                       "шагов до 0.85", "аварий", "длина эп."])
    res = {}
    for name, fn in rows.items():
        t0 = time.perf_counter()
        r = _run_scan_policy(fn, n_ep, max_steps)
        res[name] = r
        print(f"  {name}: {time.perf_counter()-t0:.1f} с", flush=True)
        t.add(**{"политика": name, "покрытие": r["покрытие за полный эпизод"],
                 "лучший": r["лучший эпизод"], "дошли до 0.85": r["дошли до 0.85"],
                 "шагов до 0.85": r["шагов до 0.85 (медиана)"],
                 "аварий": r["доля аварий"], "длина эп.": r["средняя длина эпизода"]})
    t.note = ("ЭТО ТЕ ЧИСЛА, КОТОРЫЕ ОБУЧЕННАЯ ПОЛИТИКА ОБЯЗАНА ПОБИТЬ.\n"
              "Побить надо не по потолку покрытия (скрипт и так берёт почти всё), "
              "а по ВРЕМЕНИ выхода на 0.85.")
    print("\n", t, "\n", sep="")
    out["C2 планки политик"] = t

    rnd = res["случайное действие"]["покрытие за полный эпизод"]
    scr = res["скриптовый облёт r=1.9"]["покрытие за полный эпизод"]
    zero = res["нулевое действие"]
    out["C2 приёмка награды"] = Verdict(
        "порог достижим" if (rnd < 0.20 and scr > 0.95) else "порог достижим НЕ ВЕЗДЕ",
        ok=bool(rnd < 0.20 and scr > 0.95),
        detail=("случайная политика обязана набирать < 0.20 (иначе награда не различает "
                "политики — первая версия среды давала ей 0.62), скриптовая > 0.95 "
                "(иначе задача геометрически неразрешима и виновата не политика)"),
        numbers={"случайная": rnd, "скриптовая": scr,
                 "аварий у нулевой": zero["доля аварий"]})

    # -- C1: та же процедура для зависания ----------------------------------
    lens, dists = [], []
    for ep in range(n_ep):
        env = HoverEnv(seed=0)
        env.reset(seed=900 + ep)
        i = 0
        info = {}
        for i in range(env.max_steps):
            _, _, te, tr, info = env.step(np.zeros(4))
            if te or tr:
                break
        lens.append(i + 1)
        dists.append(float(info.get("final_dist", 9.0)))
        env.close()
    t1 = Table(title="C1: планка «ничего не делать» (действие 0 = РОВНО тяга висения)",
               columns=["величина", "значение"])
    t1.add(**{"величина": "прожито шагов из 500", "значение": float(np.mean(lens))})
    t1.add(**{"величина": "финальная ошибка позиции, м", "значение": float(np.mean(dists))})
    t1.note = ("КОНТРАСТ С C2, который надо проговорить студенту: в C2 «ничего не делать» "
               "безопасно и живёт весь эпизод, в C1 — умирает за пару секунд. Начальный "
               "наклон не возвращается сам (stand.py, тест 6), и аппарат уезжает "
               "из коробки. Две разные ловушки — две разные защиты в награде")
    print(t1, "\n")
    out["C1 планка нулевого действия"] = t1

    out["C1 действие: разведка амплитуды"] = probe_action_scale(
        make_hover_env(0), levels=(0.0, 0.1, 0.3, 1.0), seconds=6.0, n=(2 if quick else 4))
    return out


# ===========================================================================
# 3. ГРАБЛИ
# ===========================================================================
def grabli_1_saturation() -> Table:
    """6.1 Насыщение тяги выпрямляет дребезг в паразитную подъёмную силу.

    Тот же механизм, что у переусиленного ПД в stand.py (тест 10), но со
    стороны RL: политика, которая дёргает действие на границах диапазона,
    получает подъёмную силу БЕСПЛАТНО, если нормировка позволяет клиппинг.
    """
    t = Table(title="ГРАБЛЯ 6.1: клиппинг выпрямляет дребезг (действие ±1 через шаг)",
              columns=["K_A", "тяга до клипа, Н", "тяга после клипа, Н",
                       "паразитная сила, Н", "дрейф z за 2 с, м"])
    for k_a in (0.6, 1.5, 2.5):
        env = HoverEnv(seed=0, k_a=k_a, tilt0=0.0, spawn=0.0)
        env.reset(seed=0)
        env.data.qvel[:] = 0.0
        mujoco.mj_forward(env.model, env.data)
        z0 = float(env.data.qpos[2])
        raws, cls = [], []
        for i in range(100):                       # 2 с
            a = np.full(4, 1.0 if i % 2 == 0 else -1.0)
            raw = env.hover * (1.0 + k_a * a)
            raws.append(raw.mean())
            cls.append(np.clip(raw, 0.0, env.ctrl_hi).mean())
            env.step(a)
        raw_m, cl_m = float(np.mean(raws)), float(np.mean(cls))
        t.add(**{"K_A": k_a, "тяга до клипа, Н": raw_m, "тяга после клипа, Н": cl_m,
                 "паразитная сила, Н": 4 * (cl_m - raw_m),
                 "дрейф z за 2 с, м": float(env.data.qpos[2]) - z0})
        env.close()
    t.note = ("При K_A = 0.6 клиппинга нет: средняя тяга ДО и ПОСЛЕ клипа совпадает, "
              "паразитная сила ровно 0, а оставшийся дрейф — это переходный процесс "
              "(первый полушаг идёт вверх), а не выпрямление.\n"
              "При K_A = 2.5 нижняя граница диапазона уходит под ноль, clip срезает "
              "только НИЗ — и средняя тяга становится больше висения. Дрон поднимается, "
              "НЕ УПРАВЛЯЯ. Политика находит этот режим сама, если нет штрафа "
              "-||a - a_prev||^2. Отсюда K_A = 0.6: тяга висения*(1±0.6) = 0.73…2.90 Н "
              "лежит ВНУТРИ ctrlrange [0, 4.6], клиппинга нет вовсе")
    return t


def grabli_2_jumper(_dt: float = 0.02) -> Table:
    """6.2 Награда за высоту рождает «прыгуна» — на НАСТОЯЩЕЙ физике.

    Гоняем в среде C1 две политики и считаем по одним и тем же траекториям
    ДВЕ награды: наивную «+1.0 * z» и нашу «exp(-2 d^2) - 0.10 ||v||^2».
    Ни одного шага обучения не нужно: если баллистика выигрывает по награде,
    PPO её найдёт — это и есть определение вырождения награды.

    «Прыгун» реализован как релейное управление: полный газ, пока не набрал
    высоту, потом малый газ. Тяговооружённость 2.535 (паспорт) делает такой
    режим доступным физически.
    """
    from rl_toolkit.rewards import RewardRegistry, Term
    reg_bad = RewardRegistry().add(Term("height", lambda c: c["z"], weight=1.0,
                                        why="наивная награда «выше = лучше»"))
    reg_ok = (RewardRegistry()
              .add(Term("pos", lambda c: math.exp(-2.0 * c["dist"] ** 2), weight=1.0,
                        why="плата за близость к ТОЧКЕ"))
              .add(Term("vel", lambda c: -float(np.dot(c["v"], c["v"])), weight=0.10,
                        why="штраф скорости добивает баллистику")))

    def bang_bang(env, obs):
        # релейное управление по высоте: вверх до 3.2 м, потом вниз до 0.6 м
        z = float(env.data.qpos[2])
        if not hasattr(bang_bang, "up"):
            bang_bang.up = True
        if z > 3.2:
            bang_bang.up = False
        elif z < 0.6:
            bang_bang.up = True
        return np.full(4, 1.0 if bang_bang.up else -1.0)

    t = Table(title="ГРАБЛЯ 6.2: «прыгун» против висения — награда на РЕАЛЬНЫХ траекториях",
              columns=["политика", "средняя z, м", "прожито шагов",
                       "наивная +1.0*z, /с", "наша exp(-2d^2), /с"])
    rows = []
    for name, fn in (("висение (действие 0 из цели)", lambda e, o: np.zeros(4)),
                     ("«прыгун» (релейный газ)", bang_bang)):
        if hasattr(bang_bang, "up"):
            del bang_bang.up
        env = HoverEnv(seed=0, spawn=0.0, tilt0=0.0)
        obs, _ = env.reset(seed=0)
        env.data.qvel[:] = 0.0
        mujoco.mj_forward(env.model, env.data)
        reg_bad.reset()
        reg_ok.reset()
        zs = []
        n = 0
        for n in range(1, 501):
            obs, r, te, tr, info = env.step(fn(env, obs))
            z = float(env.data.qpos[2])
            zs.append(z)
            reg_bad(Ctx(env.dt, z=z))
            reg_ok(Ctx(env.dt, dist=info["dist"], v=env.data.qvel[:3].copy()))
            if te or tr:
                break
        rows.append((name, float(np.mean(zs)), n,
                     reg_bad.total / (n * env.dt), reg_ok.total / (n * env.dt)))
        env.close()
    for r in rows:
        t.add(**{"политика": r[0], "средняя z, м": r[1], "прожито шагов": r[2],
                 "наивная +1.0*z, /с": r[3], "наша exp(-2d^2), /с": r[4]})
    win_bad = "«ПРЫГУН»" if rows[1][3] > rows[0][3] else "висение"
    win_ok = "«прыгун»" if rows[1][4] > rows[0][4] else "ВИСЕНИЕ"
    t.note = (f"По наивной награде «+1.0 * z» выигрывает {win_bad}, "
              f"по нашей — {win_ok}.\n"
              "Тяговооружённость 2.535 (паспорт модели) делает баллистику доступной: "
              "полный газ вверх, малый газ вниз, повтор. Средняя ВЫСОТА при этом "
              "высокая, а управления нет вовсе — и наивная награда за это платит.\n"
              "Лечение зашито в награду C1: платим за близость к ТОЧКЕ (exp(-2d^2)) "
              "плюс -0.10*||v||^2. Как поймать в прогоне: член pos около нуля при "
              "высокой суммарной награде и пилообразная длина эпизода")
    return t


def grabli_3_spin() -> Table:
    """6.3 Без штрафа на угловую скорость политика крутится."""
    model = mujoco.MjModel.from_xml_path(str(HERE / "quad.xml"))
    p = read_passport(model)
    hover = p["тяга висения на винт, Н"]
    from stand import Mixer
    mix = Mixer(model)

    t = Table(title="ГРАБЛЯ 6.3: цена вращения для аппарата и для награды",
              columns=["режим", "рыскание за 1 с, град", "дрейф z, мм",
                       "награда C1 БЕЗ члена omega, /с", "награда C1 С членом, /с"])
    env = HoverEnv(seed=0)
    for name, u_yaw in (("висит ровно", 0.0), ("крутится (20 % дифференциала)", 0.20)):
        d = fresh(model, pos=(0, 0, 1.5), hover=hover)
        ctrl = mix(hover, 0.0, 0.0, u_yaw * hover)
        z0 = float(d.qpos[2])
        env.rew.reset()
        for i in range(500):                        # 1 с физики
            d.ctrl[:] = ctrl
            mujoco.mj_step(model, d)
            if i % 10 == 9:                         # шаг среды = 10 шагов физики
                dist = float(np.linalg.norm(d.qpos[:3] - env.target))
                R = d.xmat[1].reshape(3, 3)
                env.rew(Ctx(env.dt, dist=dist, v=d.qvel[:3].copy(), w=d.qvel[3:6].copy(),
                            up=float(R[2, 2]), a=np.zeros(4), a_prev=np.zeros(4),
                            fell=False))
        summ = env.rew.episode_summary()
        with_om = sum(v["per_sec"] for v in summ.values())
        no_om = with_om - summ["omega"]["per_sec"]
        _, _, yaw = euler_from_quat(d.qpos[3:7])
        t.add(**{"режим": name, "рыскание за 1 с, град": math.degrees(yaw),
                 "дрейф z, мм": 1000 * (float(d.qpos[2]) - z0),
                 "награда C1 БЕЗ члена omega, /с": no_om,
                 "награда C1 С членом, /с": with_om})
    env.close()
    t.note = ("Вращение не наказывается ФИЗИКОЙ: дрейф высоты РОВНО ноль, гравитация "
              "рыскание не восстанавливает. Без члена omega две строки по награде "
              "почти совпадают — политике всё равно, крутиться или нет, и она крутится "
              "(шум действия так дешевле). Член -0.02*||w||^2 разводит их.\n"
              "В C2 то же вращение ещё и ВОЗНАГРАЖДАЕТСЯ по ошибке: крутящаяся камера "
              "случайно набирает покрытие. Поэтому там wz ограничен в самом действии "
              "(±1.8 рад/с), а в наблюдении есть sin/cos пеленга — «смотреть на объект» "
              "достижимо без вращения")
    return t


def grabli_4_normalization() -> Table:
    """6.4 Нормировка действия: висение на границе диапазона."""
    model = mujoco.MjModel.from_xml_path(str(HERE / "quad.xml"))
    p = read_passport(model)
    hover = p["тяга висения на винт, Н"]
    ctrl_hi = p["ctrl макс, Н"]
    t = Table(title="ГРАБЛЯ 6.4: где висение при разных нормировках действия",
              columns=["нормировка", "тяга при a=0, Н", "тяговооружённость при a=0",
                       "a висения", "z через 1 с, м"])
    for name, fn in (
        ("наивная: T = ctrl_max*(a+1)/2", lambda a: ctrl_hi * (a + 1) / 2),
        ("наша:    T = hover*(1 + 0.6a)", lambda a: hover * (1 + 0.6 * a)),
    ):
        thr = float(fn(0.0))
        d = fresh(model, pos=(0, 0, 1.5), hover=hover)
        for _ in range(500):
            d.ctrl[:] = thr
            mujoco.mj_step(model, d)
        # a, при котором тяга равна висению
        a_grid = np.linspace(-1, 1, 20001)
        a_h = float(a_grid[np.argmin(np.abs(fn(a_grid) - hover))])
        t.add(**{"нормировка": name, "тяга при a=0, Н": thr,
                 "тяговооружённость при a=0": 4 * thr / p["вес, Н"],
                 "a висения": a_h, "z через 1 с, м": float(d.qpos[2])})
    t.note = ("Тяга висения — 39.45 % от ctrlrange, поэтому при наивной нормировке "
              "висение приходится на a = -0.21. Гауссова политика стартует со средним 0, "
              "то есть с тяговооружённостью 1.27: дрон улетает вверх с ПЕРВОГО шага "
              "каждого эпизода, и первые сотни тысяч шагов уходят на сдвиг среднего.\n"
              "Как поймать в прогоне: средняя тяга за эпизод в начале обучения — она "
              "обязана быть около 1.81 Н, а не 2.3 Н. Поле info['mean_thrust'] в C1 "
              "существует ровно для этого")
    return t


def grabli_5_coverage(quick: bool) -> Table:
    """6.5 Награда за покрытие тянет к двум вырождениям сразу."""
    n_ep = 3 if quick else 8
    t = Table(title="ГРАБЛЯ 6.5: два вырождения задачи покрытия — и вес, который держит",
              columns=["политика", "суммарная награда", "cov", "аварий",
                       "член cov, /с", "член near, /с", "член time, /с"])
    pol = orbit_policy()
    for name, mk in (("идеальное висение", lambda: (lambda e, i: np.zeros(4))),
                     ("скриптовый облёт", lambda: pol)):
        tot, covs, cr = [], [], 0
        terms_acc = {}
        steps = 0
        for ep in range(n_ep):
            env = DroneScanEnv(seed=0, cov_target=0.85, max_steps=1500)
            env.reset(seed=800 + ep)
            s = 0.0
            info = {}
            for i in range(1500):
                _, r, te, tr, info = env.step(mk()(env, i))
                s += r
                for k, v in info["terms"].items():
                    terms_acc[k] = terms_acc.get(k, 0.0) + v
                steps += 1
                if te or tr:
                    break
            tot.append(s)
            covs.append(info["coverage"])
            cr += int(bool(info.get("crash") or info.get("out")))
            env.close()
        t.add(**{"политика": name, "суммарная награда": float(np.mean(tot)),
                 "cov": float(np.mean(covs)), "аварий": cr / n_ep,
                 "член cov, /с": terms_acc.get("cov", 0.0) / steps / 0.02,
                 "член near, /с": terms_acc.get("near", 0.0) / steps / 0.02,
                 "член time, /с": terms_acc.get("time", 0.0) / steps / 0.02})
    t.note = ("ПРОВЕРКА СООТНОШЕНИЯ ВЕСОВ, которую надо гонять после каждой правки "
              "награды: скриптовый облёт обязан набрать ПОЛОЖИТЕЛЬНУЮ суммарную "
              "награду, идеальное висение — ОТРИЦАТЕЛЬНУЮ.\n"
              "«Таран»: ячейка засчитывается с 2.5 м, значит выгодно прижаться к стене — "
              "держит член near (-1.0 за метр внутрь коридора 1.35 м).\n"
              "«Безопасное висение»: нулевое действие не падает НИКОГДА и доживает все "
              "1500 шагов — держит член time (-0.01 за шаг). Убрать любой из двух — "
              "и задача выродится с соответствующей стороны")
    return t


def part3(quick: bool) -> dict:
    print("=" * 78)
    print("РАЗДЕЛ 3. ПЯТЬ ГРАБЕЛЬ, СПЕЦИФИЧНЫХ ДЛЯ ДРОНА")
    print("=" * 78)
    out = {}
    for name, fn in (("грабля 6.1 насыщение тяги", lambda: grabli_1_saturation()),
                     ("грабля 6.2 «прыгун»", lambda: grabli_2_jumper(0.02)),
                     ("грабля 6.3 кручение", lambda: grabli_3_spin()),
                     ("грабля 6.4 нормировка", lambda: grabli_4_normalization()),
                     ("грабля 6.5 покрытие", lambda: grabli_5_coverage(quick))):
        t0 = time.perf_counter()
        tab = fn()
        print(tab, f"\n({time.perf_counter()-t0:.1f} с)\n")
        out[name] = tab
    return out


# ===========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="Пробы трека C")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--part", type=int, default=0, help="1..3, 0 = все")
    a = ap.parse_args()

    results = {}
    t0 = time.perf_counter()
    if a.part in (0, 1):
        results.update(part1(a.quick))
    if a.part in (0, 2):
        results.update(part2(a.quick))
    if a.part in (0, 3):
        results.update(part3(a.quick))
    print(report(results))
    print(f"пробы заняли {time.perf_counter()-t0:.1f} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
