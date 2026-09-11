"""Пробы среды парковки ДО обучения.

Правило курса: прогон стоит часов, проба — секунды. Ни один запуск обучения
не начинается, пока эти пробы не зелёные.

Запуск:
    python probe.py

Что проверяется (в скобках — параграф отчёта разбора 04_lesson14_code.md,
который эту проверку породил):

    1  формы, границы, dt, детерминизм по seed        (§1.5, §1.2)
    2  БЛОКЕР Б1: скрытого состояния больше нет       (§1.1)
    3  наблюдаемость состояния тягового привода       (§1.1)
    4  БЛОКЕР Б2: арифметика дисконта                 (§2.3)
    5  БЛОКЕР Б3: успех и столкновение не пересекаются (§3.3)
    6  условия обрыва эпизода                         (§2.6, §3.3)
    7  пассивная база и разведка                      (§4.2)
    8  члены награды: у каждого есть градиент         (§2.2, §3.1)
    9  достижимость цели за эпизод                    (§2.3)
   10  цена шага                                      (§4.3)

Код возврата: 0 — все пробы зелёные, 1 — есть красные.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import numpy as np

from car_env import (
    CAR_HALF_LEN, CAR_HALF_WID, CarParkingEnv, DT, EPISODE_SECONDS, GAMMA,
    MAX_STEPS, SPOT, SUCCESS_DX, SUCCESS_DY, SUCCESS_DYAW, SUCCESS_HOLD,
    SUCCESS_OMEGA, V_MAX, _heading_weight,
)
from rl_toolkit.diagnostics import (
    Table, Verdict, gradient_report, reachability, sweep_term,
)
from rl_toolkit.probes import (
    probe_action_scale, probe_null_baseline, probe_observability,
    probe_reward_terms, probe_shapes, probe_step_cost, probe_termination, report,
)
from rl_toolkit.rewards import Ctx

import mujoco

RESULTS: dict[str, object] = {}


def head(n: int, title: str) -> None:
    print()
    print("=" * 78)
    print(f"{n}. {title}")
    print("=" * 78)


# ===========================================================================
# 1. Формы, границы, детерминизм
# ===========================================================================
def probe_1_shapes(env) -> None:
    head(1, "ФОРМЫ, ГРАНИЦЫ, dt, ДЕТЕРМИНИЗМ ПО SEED")
    sh = probe_shapes(env, seed=7)
    for k in ("obs_shape", "obs_dtype", "action_shape", "dt", "hz",
              "max_episode_steps", "max_episode_seconds", "seed_deterministic"):
        print(f"  {k:<22} {sh[k]}")
    print()
    print("  Границы наблюдения выведены из геометрии площадки (§1.5). Проба")
    print("  проверяет, что выходов за них нет, и печатает фактический запас")
    print("  по 4000 шагам случайной политики:")
    names = ["dx_body", "dy_body", "sin_dyaw", "cos_dyaw", "vx", "vy", "omega",
             "steer", "steer_rate", "wheel_v", "dist", "x", "y", "d_left", "d_right"]
    rng = np.random.default_rng(0)
    obs, _ = env.reset(seed=0)
    lo = obs.copy()
    hi = obs.copy()
    viol = 0
    for _ in range(4000):
        a = rng.uniform(-1.0, 1.0, 2).astype(np.float32)
        obs, _, term, trunc, _ = env.step(a)
        lo = np.minimum(lo, obs)
        hi = np.maximum(hi, obs)
        viol += int(np.any(obs < env.observation_space.low) or
                    np.any(obs > env.observation_space.high))
        if term or trunc:
            obs, _ = env.reset()
    t = Table(title="", columns=["поле", "объявлено", "наблюдалось", "запас"])
    for i, nm in enumerate(names):
        dl, dh = float(env.observation_space.low[i]), float(env.observation_space.high[i])
        span_d = dh - dl
        span_o = float(hi[i] - lo[i])
        t.add(**{"поле": nm,
                 "объявлено": f"[{dl:.2f}, {dh:.2f}]",
                 "наблюдалось": f"[{lo[i]:.3f}, {hi[i]:.3f}]",
                 "запас": f"x{span_d / max(span_o, 1e-9):.1f}"})
    print("  " + str(t).replace("\n", "\n  "))
    print(f"  выходов за объявленные границы: {viol} из 4000")
    RESULTS["1 формы и детерминизм"] = Verdict(
        "величина наблюдаема" if sh["seed_deterministic"] and viol == 0 else "проверка не состоялась",
        ok=bool(sh["seed_deterministic"] and viol == 0),
        detail=(f"reset(seed=7) дважды даёт побитово равный obs; "
                f"выходов за границы {viol}/4000; dt={sh['dt']} с ({sh['hz']:.0f} Гц)"),
        numbers={"выходов за границы": float(viol), "dt": float(sh["dt"])},
    )


# ===========================================================================
# 2. БЛОКЕР Б1: POMDP закрыт
# ===========================================================================
def probe_2_pomdp() -> None:
    head(2, "БЛОКЕР Б1: СКРЫТОГО СОСТОЯНИЯ БОЛЬШЕ НЕТ (проба «двойник»)")
    print("""  Метод (повторяет p4_pomdp.py из разбора). Строим два состояния с
  ПОБИТОВО одинаковым наблюдением, но с разной ИСТОРИЕЙ: одно свежее,
  второе получено после 30 шагов полного газа, после чего его qpos/qvel
  насильно приравнены к первому. Дальше обе среды получают ОДНУ И ТУ ЖЕ
  последовательность из 20 действий. Если наблюдение — полное состояние,
  траектории обязаны совпасть побитово.""")

    def twin(make_env, warm_action, steps_warm=30, steps_test=20, set_state=None):
        a_env = make_env()
        c_env = make_env()
        a_env.reset(seed=11)
        c_env.reset(seed=11)
        for _ in range(steps_warm):                       # разная ИСТОРИЯ
            c_env.step(warm_action)
        # приравниваем ФИЗИЧЕСКОЕ состояние
        c_env.unwrapped.data.qpos[:] = a_env.unwrapped.data.qpos
        c_env.unwrapped.data.qvel[:] = a_env.unwrapped.data.qvel
        mujoco.mj_forward(c_env.unwrapped.model, c_env.unwrapped.data)
        oa = a_env.unwrapped._observation()
        oc = c_env.unwrapped._observation()
        same_obs = bool(np.array_equal(oa, oc))
        rng = np.random.default_rng(5)
        acts = rng.uniform(-1.0, 1.0, (steps_test, 2)).astype(np.float32)
        for k in range(steps_test):
            a_env.step(acts[k])
            c_env.step(acts[k])
        va = a_env.unwrapped._body_velocity()[0]
        vc = c_env.unwrapped._body_velocity()[0]
        xa = float(a_env.unwrapped.data.qpos[0])
        xc = float(c_env.unwrapped.data.qpos[0])
        a_env.close()
        c_env.close()
        return same_obs, va, vc, xa, xc

    # --- старая среда: та же проба, для контраста -------------------------
    legacy_line = "  (старая среда _legacy_env.py не найдена — контраст не показан)"
    try:
        import _legacy_env

        same_l, va_l, vc_l, xa_l, xc_l = twin(
            lambda: _legacy_env.CarParkingEnv(in_spot_start_prob=0.0),
            np.array([0.0, 1.0], dtype=np.float32), steps_warm=150, steps_test=20)
        legacy_line = (
            f"  СТАРАЯ среда (_legacy_env.py, позиционные приводы + _roll_target):\n"
            f"    наблюдения совпадают побитово : {same_l}\n"
            f"    после 20 одинаковых действий  : vx(A)={va_l:+.4f}  vx(C)={vc_l:+.4f}  "
            f"|разница|={abs(va_l - vc_l):.4f} м/с\n"
            f"                                    x(A)={xa_l:.4f}   x(C)={xc_l:.4f}   "
            f"|разница|={abs(xa_l - xc_l):.4f} м")
    except Exception as exc:                                   # pragma: no cover
        legacy_line = f"  (старую среду прогнать не удалось: {exc})"

    same_n, va_n, vc_n, xa_n, xc_n = twin(
        lambda: CarParkingEnv(in_spot_start_prob=0.0),
        np.array([0.0, 1.0], dtype=np.float32), steps_warm=30, steps_test=20)

    print()
    print(legacy_line)
    print()
    print(f"  НОВАЯ среда (velocity-приводы, wheel_v и steer_rate в наблюдении):")
    print(f"    наблюдения совпадают побитово : {same_n}")
    print(f"    после 20 одинаковых действий  : vx(A)={va_n:+.10f}  vx(C)={vc_n:+.10f}  "
          f"|разница|={abs(va_n - vc_n):.3e} м/с")
    print(f"                                    x(A)={xa_n:.10f}   x(C)={xc_n:.10f}   "
          f"|разница|={abs(xa_n - xc_n):.3e} м")

    ok = bool(same_n and abs(va_n - vc_n) < 1e-12 and abs(xa_n - xc_n) < 1e-12)
    RESULTS["2 POMDP закрыт (блокер Б1)"] = Verdict(
        "величина наблюдаема" if ok else "величина НЕ наблюдаема",
        ok=ok,
        detail=(
            "два состояния с побитово одинаковым наблюдением и одинаковой цепочкой "
            f"действий расходятся по vx на {abs(va_n - vc_n):.3e} м/с и по x на "
            f"{abs(xa_n - xc_n):.3e} м, то есть не расходятся вовсе: скрытого "
            "состояния в среде нет."
            if ok else
            "состояния с одинаковым наблюдением всё ещё расходятся — что-то в среде "
            "хранится вне наблюдения."
        ),
        numbers={"разница vx, м/с": abs(va_n - vc_n), "разница x, м": abs(xa_n - xc_n)},
    )


# ===========================================================================
# 3. Наблюдаемость состояния привода
# ===========================================================================
def probe_3_observability(env) -> None:
    head(3, "НАБЛЮДАЕМОСТЬ СОСТОЯНИЯ ТЯГОВОГО ПРИВОДА")
    print("""  Тот же вопрос, но инструментом ядра: ищем в выборке пары состояний с
  практически одинаковым наблюдением и смотрим, насколько в них расходится
  состояние привода. Политика — «еду 1 с, стою 1 с»: машина многократно
  приходит в покой, поэтому близкие состояния в выборке вообще появляются.
  Для старой среды берётся ЕЁ скрытая величина — ошибка слежения позиционного
  привода; для новой — скорость колёс.""")

    def pol_new(_obs, box=[0]):
        box[0] += 1
        return np.array([0.0, 0.5 if (box[0] // 20) % 2 == 0 else 0.0], dtype=np.float32)

    def pol_old(_obs, box=[0]):
        box[0] += 1                      # те же 1.0 с, но при dt=0.01
        return np.array([0.0, 0.5 if (box[0] // 100) % 2 == 0 else 0.0], dtype=np.float32)

    t = Table(
        title="",
        columns=["среда", "величина", "tol", "пар", "разброс величины",
                 "в долях сигмы", "вердикт"],
    )
    keep: dict[float, Verdict] = {}
    for tol in (0.05, 0.10):
        v = probe_observability(env, quantity=lambda u: u._wheel_speed(),
                                n=600, tol=tol, seed=1, policy=pol_new)
        keep[tol] = v
        t.add(**{"среда": "новая", "величина": "скорость колёс, м/с", "tol": tol,
                 "пар": int(v.numbers["пар с одинаковым obs"]),
                 "разброс величины": v.numbers["макс разброс величины"],
                 "в долях сигмы": v.numbers["в долях сигмы"], "вердикт": v.verdict})
    try:
        import _legacy_env

        def legacy_err(u):
            """Скрытое состояние старой среды: уставка минус фактический угол колеса."""
            jid = mujoco.mj_name2id(u.model, mujoco.mjtObj.mjOBJ_JOINT, "roll_rl")
            q = float(u.data.qpos[u.model.jnt_qposadr[jid]])
            return float(u._roll_target) - q

        for tol in (0.05, 0.10):
            old = _legacy_env.CarParkingEnv(in_spot_start_prob=0.0)
            v2 = probe_observability(old, quantity=legacy_err, n=600, tol=tol,
                                     seed=1, policy=pol_old)
            old.close()
            t.add(**{"среда": "старая", "величина": "ошибка слежения, рад", "tol": tol,
                     "пар": int(v2.numbers["пар с одинаковым obs"]),
                     "разброс величины": v2.numbers["макс разброс величины"],
                     "в долях сигмы": v2.numbers["в долях сигмы"],
                     "вердикт": v2.verdict})
    except Exception as exc:                                   # pragma: no cover
        t.note = f"(старую среду прогнать не удалось: {exc})"
    print("  " + str(t).replace("\n", "\n  "))

    print("""
  Честная оговорка о том, чего эта проба НЕ доказывает. Состояния лежат на
  гладком многообразии, поэтому «разброс в долях сигмы» здесь почти в точности
  повторяет сам tol (0.05 -> 0.045, 0.10 -> 0.098): порог ok/не-ok сдвигается
  вместе с допуском, и опираться на него как на вердикт нельзя.
  Смотреть надо на АБСОЛЮТНЫЙ разброс, он от допуска почти не зависит:
  у новой среды это сотые доли м/с, у старой — ПОЛТОРА РАДИАНА накопленной
  ошибки привода при одном и том же наблюдении.
  Решающим доказательством остаётся проба 2: там два состояния строятся
  побитово одинаковыми, и расхождение ровно 0.000e+00.""")

    v = keep[0.10]
    RESULTS["3 наблюдаемость скорости колёс"] = Verdict(
        v.verdict, ok=v.ok,
        detail=(f"на {v.numbers['пар с одинаковым obs']:.0f} парах с почти одинаковым "
                f"наблюдением скорость колёс расходится на "
                f"{v.numbers['макс разброс величины']:.4g} м/с; R2 линейной модели "
                f"{v.numbers['R2 линейной модели']:.3f} (величина лежит в obs[9])"),
        numbers=v.numbers,
    )


# ===========================================================================
# 4. БЛОКЕР Б2: арифметика дисконта
# ===========================================================================
def probe_4_discount() -> None:
    head(4, "БЛОКЕР Б2: АРИФМЕТИКА ДИСКОНТА")
    print("""  Эффективный горизонт = dt / (1 - gamma). Он обязан покрывать эпизод,
  иначе терминальная награда не видна критику. Числа старой версии взяты
  из отчёта 04_lesson14_code.md §2.3.""")
    t = Table(
        title="",
        columns=["конфигурация", "dt, с", "gamma", "горизонт, с", "эпизод, с",
                 "покрытие", "стоимость +100 в цели"],
    )
    # Старая версия: 100 Гц, gamma=0.99, медианный успех на шаге 460 (§2.3).
    t.add(**{"конфигурация": "старая (100 Гц)", "dt, с": 0.01, "gamma": 0.99,
             "горизонт, с": 0.01 / 0.01, "эпизод, с": 6.0,
             "покрытие": f"{(0.01/0.01)/6.0:.2f}",
             "стоимость +100 в цели": f"{100 * 0.99 ** 460:.2f}"})
    for g in (0.99, 0.995, 0.999):
        hor = DT / (1.0 - g)
        # шаг 60 — типичный момент парковки при 20 Гц (замер ниже, проба 7/9)
        t.add(**{"конфигурация": f"новая (20 Гц)", "dt, с": DT, "gamma": g,
                 "горизонт, с": hor, "эпизод, с": EPISODE_SECONDS,
                 "покрытие": f"{hor / EPISODE_SECONDS:.2f}",
                 "стоимость +100 в цели": f"{100 * g ** 60:.2f}"})
    print("  " + str(t).replace("\n", "\n  "))
    hor = DT / (1.0 - GAMMA)
    ok = hor >= EPISODE_SECONDS
    print(f"\n  выбрано: dt={DT} с, gamma={GAMMA} -> горизонт {hor:.1f} с "
          f"при эпизоде {EPISODE_SECONDS:.1f} с")
    print(f"  терминальный +100, полученный на шаге 60 (3.0 с), стоит "
          f"{100 * GAMMA ** 60:.1f} против {100 * 0.99 ** 460:.2f} у старой версии")
    RESULTS["4 горизонт дисконта (блокер Б2)"] = Verdict(
        "порог достижим" if ok else "порог НЕДОСТИЖИМ",
        ok=ok,
        detail=f"горизонт {hor:.1f} с покрывает эпизод {EPISODE_SECONDS:.1f} с "
               f"с запасом x{hor / EPISODE_SECONDS:.2f}",
        numbers={"горизонт, с": hor, "эпизод, с": EPISODE_SECONDS,
                 "стоимость +100 на шаге 60": 100 * GAMMA ** 60},
    )


# ===========================================================================
# 5. БЛОКЕР Б3: успех и столкновение не пересекаются
# ===========================================================================
def _sweep_poses(env, dx_max, dy_max, dyaw_max, step_xy=0.02, step_yaw=0.025):
    """Перебор поз внутри ворот; возвращает (всего, в контакте, примеры)."""
    m, d = env.unwrapped.model, env.unwrapped.data
    xs = np.arange(-dx_max, dx_max + 1e-9, step_xy)
    ys = np.arange(-dy_max, dy_max + 1e-9, step_xy)
    ws = np.arange(-dyaw_max, dyaw_max + 1e-9, step_yaw)
    total = 0
    bad = 0
    examples = []
    for dx in xs:
        for dy in ys:
            for w in ws:
                x, y, yaw = SPOT[0] + dx, SPOT[1] + dy, float(w)
                d.qpos[0:3] = [x, y, 0.06]
                d.qpos[3:7] = [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]
                mujoco.mj_kinematics(m, d)
                mujoco.mj_collision(m, d)
                total += 1
                if env.unwrapped._collision():
                    bad += 1
                    if len(examples) < 4:
                        examples.append((round(float(x), 2), round(float(y), 2),
                                         round(float(yaw), 2)))
    return total, bad, examples


def probe_5_disjoint(env) -> None:
    head(5, "БЛОКЕР Б3: МНОЖЕСТВА «УСПЕХ» И «СТОЛКНОВЕНИЕ» НЕ ПЕРЕСЕКАЮТСЯ")
    print("""  Полный перебор поз внутри ворот успеха средствами самого MuJoCo
  (mj_kinematics + mj_collision, шаг 0.02 м / 0.025 рад). У старой версии
  13.9 % таких поз были УЖЕ В КОНТАКТЕ (§3.3), и один шаг мог вернуть
  info={'success': True, 'collision': True}.""")
    env.reset(seed=0)
    t = Table(title="", columns=["ворота (dx, dy, dyaw)", "поз перебрано",
                                 "из них в контакте", "доля"])
    old_total, old_bad, old_ex = _sweep_poses(env, 0.50, 0.50, 0.70, 0.05, 0.10)
    t.add(**{"ворота (dx, dy, dyaw)": "старые (0.50, 0.50, 0.70)",
             "поз перебрано": old_total, "из них в контакте": old_bad,
             "доля": f"{100.0 * old_bad / old_total:.1f} %"})
    new_total, new_bad, new_ex = _sweep_poses(env, SUCCESS_DX, SUCCESS_DY, SUCCESS_DYAW)
    t.add(**{"ворота (dx, dy, dyaw)": f"новые ({SUCCESS_DX:.2f}, {SUCCESS_DY:.2f}, "
                                      f"{SUCCESS_DYAW:.2f})",
             "поз перебрано": new_total, "из них в контакте": new_bad,
             "доля": f"{100.0 * new_bad / new_total:.1f} %"})
    print("  " + str(t).replace("\n", "\n  "))
    if old_ex:
        print(f"  примеры пересечения у СТАРЫХ ворот (x, y, yaw): {old_ex}")

    # геометрическая справка: габарит повёрнутой машины против рамки
    c, s = math.cos(SUCCESS_DYAW), math.sin(SUCCESS_DYAW)
    ext_x = CAR_HALF_LEN * c + CAR_HALF_WID * s
    ext_y = CAR_HALF_LEN * s + CAR_HALF_WID * c
    print(f"\n  габарит машины при |dyaw|={SUCCESS_DYAW}: продольный {ext_x:.3f} м, "
          f"поперечный {ext_y:.3f} м")
    print(f"  крайнее положение по x: {SPOT[0] - SUCCESS_DX - ext_x:+.3f} .. "
          f"{SPOT[0] + SUCCESS_DX + ext_x:+.3f} (грань задней стены -0.150)")
    print(f"  крайнее положение по |y|: {SUCCESS_DY + ext_y:.3f} "
          f"(ближняя грань соседа 0.990, зазор {0.990 - SUCCESS_DY - ext_y:.3f} м)")

    RESULTS["5 успех ∩ столкновение (блокер Б3)"] = Verdict(
        "порог достижим" if new_bad == 0 else "порог достижим НЕ ВЕЗДЕ",
        ok=(new_bad == 0),
        detail=(f"из {new_total} поз внутри новых ворот в контакте {new_bad}; "
                f"у старых ворот было {old_bad} из {old_total} "
                f"({100.0 * old_bad / old_total:.1f} %)"),
        numbers={"поз в контакте (новые)": float(new_bad),
                 "доля у старых ворот, %": 100.0 * old_bad / old_total},
    )


# ===========================================================================
# 6. Условия обрыва
# ===========================================================================
def probe_6_termination(env) -> None:
    head(6, "УСЛОВИЯ ОБРЫВА ЭПИЗОДА")
    print("""  Каждый случай — поза, поставленная напрямую через set_probe_state,
  плюс один шаг нулевым действием. Случай «боком через место» — тот самый,
  который старая версия засчитывала успехом: её ворота смотрели только на
  продольную скорость, и vy=2.5 м/с проходило (§2.6).""")
    cases = {
        "в месте, стоит, выдержка не набрана": (
            dict(x=SPOT[0], y=0.0, yaw=0.0, hold=0), False),
        "в месте, стоит, выдержка добирается": (
            dict(x=SPOT[0], y=0.0, yaw=0.0, hold=SUCCESS_HOLD - 1), True),
        "в месте, но едет вперёд 0.8 м/с": (
            dict(x=SPOT[0], y=0.0, yaw=0.0, v=0.8, hold=SUCCESS_HOLD - 1), False),
        "в месте, но скользит БОКОМ 0.8 м/с": (
            dict(x=SPOT[0], y=0.0, yaw=0.0, v_lat=0.8, hold=SUCCESS_HOLD - 1), False),
        # 3.0 рад/с, а не 1.5: замер m7_idle.py показал, что damping 0.2 на
        # свободном шарнире гасит 1.5 рад/с до 0.005 за ОДИН шаг политики, и
        # такая машина к концу шага действительно стоит. При 3.0 рад/с к концу
        # шага остаётся 0.929 рад/с — это выше порога SUCCESS_OMEGA=0.40.
        f"в месте, но вращается 3.0 рад/с (порог {SUCCESS_OMEGA})": (
            dict(x=SPOT[0], y=0.0, yaw=0.0, omega=3.0, hold=SUCCESS_HOLD - 1), False),
        "в месте, но курс развёрнут на 0.5 рад": (
            dict(x=SPOT[0], y=0.0, yaw=0.5, hold=SUCCESS_HOLD - 1), False),
        "прижался к соседу справа": (
            dict(x=SPOT[0], y=0.78, yaw=0.0), True),
        "уткнулся в заднюю стену": (
            dict(x=0.28, y=0.0, yaw=0.0), True),
        "на дороге, ничего не происходит": (
            dict(x=2.2, y=0.0, yaw=math.pi / 2), False),
        "за дальней границей площадки": (
            dict(x=6.9, y=0.0, yaw=0.0), True),
    }
    t = probe_termination(env, cases)
    print("  " + str(t).replace("\n", "\n  "))
    RESULTS["6 условия обрыва"] = t

    # -- отдельно: поглощающее состояние «завалился» ----------------------
    print()
    print("""  6.1 ПОГЛОЩАЮЩЕЕ СОСТОЯНИЕ. Машина, лежащая на боку, выехать не может.
  Пока эпизод её не обрывал, она лежала оставшиеся секунды, и критик был
  обязан моделировать эту часть эпизода. Проверяем, что признак ловится
  и что эпизод действительно обрывается.""")
    tt = Table(title="", columns=["наклон при постановке", "up_z до шага",
                                  "up_z после шага", "признак tipped", "обрыв"])
    for deg in (0, 20, 40, 50, 90, 180):
        env.reset(seed=0)
        # кладём машину, вращая её вокруг продольной оси на deg
        a = math.radians(deg) / 2.0
        env.unwrapped.data.qpos[0:3] = [2.2, 0.0, 0.20]
        env.unwrapped.data.qpos[3:7] = [math.cos(a), math.sin(a), 0.0, 0.0]
        mujoco.mj_forward(env.unwrapped.model, env.unwrapped.data)
        u0 = env.unwrapped._up_z()
        _, _, term, _, info = env.step(np.zeros(2, dtype=np.float32))
        tt.add(**{"наклон при постановке": f"{deg}°", "up_z до шага": u0,
                  "up_z после шага": env.unwrapped._up_z(),
                  "признак tipped": bool(info.get("tipped")), "обрыв": bool(term)})
    print("  " + str(tt).replace("\n", "\n  "))
    print("""  Признак считается ПОСЛЕ шага физики, поэтому при 40-50 градусов он не
  срабатывает: машина, отпущенная под таким наклоном, за 0.05 с падает обратно
  на колёса (колонка «up_z после шага» это и показывает). Порог 0.707 ловит
  именно необратимое положение — на боку и на крыше.""")

    # частота опрокидываний при случайной политике — с пределом руля и без
    import car_env as _ce

    def flips(rate, std, n=30):
        old = _ce.STEER_RATE_MAX
        _ce.STEER_RATE_MAX = rate
        e = CarParkingEnv(in_spot_start_prob=0.0, start_spread=1.0)
        rng = np.random.default_rng(0)
        cnt = 0
        for ep in range(n):
            e.reset(seed=3000 + ep)
            for _ in range(MAX_STEPS):
                _, _, term, trunc, inf = e.step(
                    np.clip(rng.normal(0, std, 2), -1, 1).astype(np.float32))
                if term or trunc:
                    break
            cnt += bool(inf.get("tipped"))
        e.close()
        _ce.STEER_RATE_MAX = old
        return 100.0 * cnt / n

    t3 = Table(title="доля эпизодов с опрокидыванием (30 эпизодов на клетку)",
               columns=["предел скорости руля", "std=1.0", "std=0.37"])
    t3.add(**{"предел скорости руля": "нет (100 рад/с)",
              "std=1.0": flips(100.0, 1.0), "std=0.37": flips(100.0, 0.368)})
    t3.add(**{"предел скорости руля": f"{_ce.STEER_RATE_MAX} рад/с (рабочий)",
              "std=1.0": flips(_ce.STEER_RATE_MAX, 1.0),
              "std=0.37": flips(_ce.STEER_RATE_MAX, 0.368)})
    print()
    print("  " + str(t3).replace("\n", "\n  "))
    print("""  Предел скорости руля — не косметика: без него переброс руля с +0.5
  на -0.5 рад за один шаг политики опрокидывает машину. Манёвренность при
  этом не страдает — установившийся радиус поворота одинаков (m15_rate.py).""")
    now = t3.column("std=1.0")[1]
    RESULTS["6.1 опрокидывание ловится и обрывает эпизод"] = Verdict(
        "порог достижим" if now == 0.0 else "порог достижим НЕ ВЕЗДЕ",
        ok=(now == 0.0),
        detail=(f"с рабочим пределом руля опрокидываний {now:.1f} % против "
                f"{t3.column('std=1.0')[0]:.1f} % без предела; состояние ловится "
                f"признаком tipped и обрывает эпизод"),
        numbers={"опрокидываний с пределом, %": now,
                 "опрокидываний без предела, %": t3.column("std=1.0")[0]},
    )


# ===========================================================================
# 7. Пассивная база и разведка
# ===========================================================================
def _explore_stats(make_env, n_ep=20, seed0=1000, hz_ratio=1, fixed_action=None):
    """Смещение за эпизод, минимальная дистанция до места, исходы."""
    env = make_env()
    steps = env.unwrapped.max_steps if hasattr(env.unwrapped, "max_steps") else 600
    rng = np.random.default_rng(0)
    disp, dmin = [], []
    outcome = {"success": 0, "collision": 0, "out_of_bounds": 0, "timeout": 0}
    for ep in range(n_ep):
        env.reset(seed=seed0 + ep)
        p0 = np.array(env.unwrapped.data.qpos[0:2], dtype=float)
        best = 1e9
        info = {}
        a = None if fixed_action is None else np.asarray(fixed_action, dtype=np.float32)
        for k in range(steps):
            if fixed_action is None and k % hz_ratio == 0:
                a = rng.uniform(-1, 1, 2).astype(np.float32)
            _, _, term, trunc, info = env.step(a)
            p = np.array(env.unwrapped.data.qpos[0:2], dtype=float)
            best = min(best, float(np.linalg.norm(p - SPOT)))
            if term or trunc:
                break
        p = np.array(env.unwrapped.data.qpos[0:2], dtype=float)
        disp.append(float(np.linalg.norm(p - p0)))
        dmin.append(best)
        for key in ("success", "collision", "out_of_bounds"):
            if info.get(key):
                outcome[key] += 1
                break
        else:
            outcome["timeout"] += 1
    env.close()
    return float(np.mean(disp)), float(np.max(disp)), float(np.mean(dmin)), outcome


def probe_7_baseline() -> None:
    head(7, "ПАССИВНАЯ БАЗА И РАЗВЕДКА")
    print("""  Два вопроса. Первый: выгодно ли НИЧЕГО НЕ ДЕЛАТЬ. Потенциальный
  шейпинг с gamma платит неподвижной машине (gamma-1)*Ф(s) > 0, потому что
  Ф <= 0, и если плата за время меньше этой ставки — оптимально стоять.
  Второй: доезжает ли куда-нибудь случайная политика (у старой версии она была
  вырождена: 100/100 таймаутов, смещение 0.379 м за 6 с, §4.2).""")
    env_fn = lambda: CarParkingEnv(in_spot_start_prob=0.0)
    base = probe_null_baseline(env_fn, seconds=EPISODE_SECONDS, n=8)
    print(f"\n  пассивная база (a=0, {base['episodes']} эпизодов): "
          f"жизнь {base['alive_s']:.2f} с, возврат {base['return']:+.3f}, "
          f"обрывов {base['terminated']}/{base['episodes']}")
    print("  ставки членов на пассивной базе, награда/с:")
    for k, v in sorted(base["terms"].items(), key=lambda kv: -abs(kv[1])):
        print(f"    {k:<10} {v:+8.4f}")
    idle_ok = base["return"] < 0.0
    print(f"  стоять {'НЕВЫГОДНО' if idle_ok else 'ВЫГОДНО'}: возврат "
          f"{base['return']:+.3f} за эпизод "
          f"(при STEP_COST=0.02 тот же замер давал +0.338 — см. m7_idle.py)")

    t = probe_action_scale(env_fn, levels=(0.0, 0.1, 0.3, 1.0),
                           seconds=EPISODE_SECONDS, n=8, seed=0)
    print()
    print("  " + str(t).replace("\n", "\n  "))
    print("""  Замечание к таблице: здесь ноль живёт столько же, сколько единица,
  просто потому что эпизод оканчивается по таймауту в обоих случаях — машину
  на парковке ничто не убивает. Это НЕ случай §A5 «разведка убивает раньше,
  чем учит»; смотреть надо не на время жизни, а на пройденный путь.""")

    print("""
  Ниже разведка меряется в трёх режимах, по 20 эпизодов каждый:
    «раз в шаг»    — действие тянется заново на каждом шаге;
    «раз в 0.5 с»  — действие ДЕРЖИТСЯ 0.5 с (у старой среды это 50 её шагов,
                     у новой 10 — сравнение идёт по времени, не по шагам);
    «полный газ»   — a = [0, 1] весь эпизод: это замер УПРАВЛЯЕМОСТИ, то есть
                     сколько машина вообще способна проехать за 6 с.""")
    tab = Table(title="",
                columns=["среда", "режим", "смещение, м", "максимум, м",
                         "ближе всего к месту, м", "исходы"])
    rows = {}

    def row(tag_env, tag, make, ratio, fixed=None):
        d, dm, dmin, out = _explore_stats(make, hz_ratio=ratio, fixed_action=fixed)
        rows[(tag_env, tag)] = d
        tab.add(**{"среда": tag_env, "режим": tag, "смещение, м": d,
                   "максимум, м": dm, "ближе всего к месту, м": dmin,
                   "исходы": f"т{out['timeout']} с{out['collision']} "
                             f"г{out['out_of_bounds']} у{out['success']}"})

    row("новая", "раз в шаг", env_fn, 1)
    row("новая", "раз в 0.5 с", env_fn, 10)
    row("новая", "полный газ", env_fn, 1, fixed=[0.0, 1.0])
    legacy_ok = True
    try:
        import _legacy_env

        old_fn = lambda: _legacy_env.CarParkingEnv(in_spot_start_prob=0.0)
        row("старая", "раз в шаг", old_fn, 1)
        row("старая", "раз в 0.5 с", old_fn, 50)
        row("старая", "полный газ", old_fn, 1, fixed=[0.0, 1.0])
    except Exception as exc:                                   # pragma: no cover
        legacy_ok = False
        tab.note = f"(старую среду прогнать не удалось: {exc})"
    print("  " + str(tab).replace("\n", "\n  "))

    print("""
  Как это читать — и чего здесь НЕТ. Замер не подтверждает, что новая среда
  разведывает лучше: при случайном действии она проходит МЕНЬШЕ старой
  (0.62 против 0.71 м раз в шаг; 0.85 против 1.62 м при удержании 0.5 с).
  Причина ровно та, ради которой приводы и меняли: у старой среды после смены
  команды машина продолжала катиться на накопленной ошибке слежения — та самая
  скрытая память, которая делала среду POMDP. Новая среда на смену команды
  реагирует немедленно, поэтому знакопеременное случайное действие её
  тормозит. Это осознанный размен: наблюдаемость состояния оплачена
  сужением случайной разведки.
  Замер «полный газ» показывает, что дело не в мощности: при связной команде
  машина за эпизод проезжает почти три метра и во всех 20 эпизодах упирается
  в препятствие. Управляемости хватает с избытком — не хватает связности
  случайной команды.
  Практический вывод: ранняя разведка слаба в обеих средах, и лечится она не
  наградой и не приводами, а куррикулумом — рампы in_spot_start_prob и
  start_spread в train.py дают ранним эпизодам близкий старт и гаснут
  к концу бюджета.""")

    d_drive = rows[("новая", "полный газ")]
    detail = (f"пассивный возврат {base['return']:+.3f} за эпизод (отрицательный: "
              f"стоять невыгодно); при связной команде машина проходит "
              f"{d_drive:.2f} м за эпизод и упирается в препятствие — "
              f"управляемости хватает")
    numbers = {"пассивный возврат": base["return"], "полный газ, м": d_drive}
    if legacy_ok:
        numbers["полный газ старая, м"] = rows[("старая", "полный газ")]

    RESULTS["7 пассивная база и разведка"] = Verdict(
        "градиент есть" if (idle_ok and d_drive > 2.0) else "градиент ОБРАТНЫЙ",
        ok=bool(idle_ok and d_drive > 2.0),
        detail=detail if idle_ok else
        (f"пассивный возврат {base['return']:+.3f} — стоять на месте ВЫГОДНО, "
         "плата за время не перекрывает ставку неподвижности шейпинга"),
        numbers=numbers,
    )


# ===========================================================================
# 8. Члены награды: градиент каждого
# ===========================================================================
def probe_8_terms(env) -> None:
    head(8, "ЧЛЕНЫ НАГРАДЫ: У КАЖДОГО ЛИ ЕСТЬ ГРАДИЕНТ")

    print("\n  8.1 Вес ошибки курса в потенциале (§3.1: старая формула была")
    print("      численно КОНСТАНТОЙ 2.0 на всём рабочем диапазоне dist <= 1.5)")
    t = Table(title="", columns=["dist, м", "старый вес", "новый вес"])
    for d in (0.0, 0.1, 0.28, 0.5, 0.8, 1.2, 1.5, 1.7, 1.9):
        old = 2.0 * min(1.0, 1.5 / max(d, 0.3))
        t.add(**{"dist, м": d, "старый вес": old, "новый вес": _heading_weight(d)})
    print("  " + str(t).replace("\n", "\n  "))
    old_vals = [2.0 * min(1.0, 1.5 / max(d, 0.3)) for d in (0.0, 0.5, 1.0, 1.5)]
    new_vals = [_heading_weight(d) for d in (0.0, 0.5, 1.0, 1.5)]
    print(f"  размах на dist in [0, 1.5]: старый {max(old_vals) - min(old_vals):.3f}, "
          f"новый {max(new_vals) - min(new_vals):.3f}")

    reg = env.unwrapped.rewards
    dyaw_fix = 0.5

    def phi(dist, dyaw):
        return -(2.0 * dist + _heading_weight(dist) * dyaw)

    print("\n  8.2 progress: ставка против скорости СБЛИЖЕНИЯ (dist=1.0 м, dyaw=0.5 рад)")

    def ctx_close(v):
        d0 = 1.0
        d1 = max(0.0, d0 - v * DT)
        return Ctx(DT, phi=phi(d1, dyaw_fix), phi_prev=phi(d0, dyaw_fix))

    tab = sweep_term(reg["progress"], "скорость сближения, м/с",
                     [-1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0], ctx_close, DT)
    print("  " + str(tab).replace("\n", "\n  "))
    v = gradient_report(tab, higher_is_better=True)
    print("  " + str(v).replace("\n", "\n  "))
    RESULTS["8.2 progress по расстоянию"] = v

    print("\n  8.3 progress: ставка против скорости ДОВОРОТА (dist=0.6 м, dyaw=0.8 рад)")

    def ctx_turn(w):
        d = 0.6
        y0 = 0.8
        y1 = max(0.0, y0 - w * DT)
        return Ctx(DT, phi=phi(d, y1), phi_prev=phi(d, y0))

    tab = sweep_term(reg["progress"], "скорость доворота, рад/с",
                     [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0], ctx_turn, DT)
    print("  " + str(tab).replace("\n", "\n  "))
    v = gradient_report(tab, higher_is_better=True)
    print("  " + str(v).replace("\n", "\n  "))
    RESULTS["8.3 progress по курсу"] = v

    print("\n  8.4 settle: ставка против ПОЛНОЙ скорости внутри места")
    print("      (ниже — лучше, поэтому higher_is_better=False)")

    def ctx_settle(s):
        return Ctx(DT, in_gate=True, speed=s)

    tab = sweep_term(reg["settle"], "скорость в месте, м/с",
                     [0.0, 0.03, 0.06, 0.09, 0.12, 0.15, 0.25], ctx_settle, DT)
    print("  " + str(tab).replace("\n", "\n  "))
    v = gradient_report(tab, higher_is_better=False)
    print("  " + str(v).replace("\n", "\n  "))
    RESULTS["8.4 settle по скорости"] = v

    print("\n  8.5 time: постоянная ставка ПО ЗАМЫСЛУ — свип не нужен")
    ct = Ctx(DT)
    print(f"      ставка {reg['time'].rate(ct):+.4f} награды/с, "
          f"за эпизод {reg['time'].value(ct) * MAX_STEPS:+.3f}")

    print("\n  8.6 ставки всех членов на случайной политике (20 с)")
    rng = np.random.default_rng(4)
    t = probe_reward_terms(
        env, policy=lambda o: rng.uniform(-1, 1, 2).astype(np.float32),
        seconds=20.0, seed=2)
    print("  " + str(t).replace("\n", "\n  "))
    print("""  Пометка «кандидат в душители» у time и progress здесь ожидаема и
  безобидна: на случайной политике ненулевые только эти два члена, поэтому их
  доли по определению делят единицу. Смотреть на неё имеет смысл на ОБУЧЕННОЙ
  политике — эту же таблицу печатает evaluate.py.""")
    RESULTS["8.6 ставки членов"] = t

    print("\n  8.7 все члены снабжены полем why (правило курса)")
    missing = [t_.name for t_ in reg.terms if not t_.why.strip()]
    for t_ in reg.terms:
        print(f"    {t_.name:<10} вес {t_.weight:+8.3f}  [{t_.unit}]")
    RESULTS["8.7 у членов есть why"] = Verdict(
        "порог достижим" if not missing else "порог НЕДОСТИЖИМ",
        ok=not missing,
        detail=(f"{len(reg)} членов, у всех заполнено why"
                if not missing else f"без why: {missing}"),
        numbers={"членов": float(len(reg))},
    )


# ===========================================================================
# 9. Достижимость цели за эпизод
# ===========================================================================
def probe_9_reachability(env) -> None:
    head(9, "ДОСТИЖИМА ЛИ ЦЕЛЬ ЗА ЭПИЗОД")
    # Радиус поворота ЗАМЕРЕН, а не взят из велосипедной модели. Модель даёт
    # R = база / tg(руль) = 0.44 / tg(0.5) = 0.805 м, а установившийся радиус
    # при полном руле на замере (m15_rate.py) — 1.067 м, на 33 % больше:
    # оба передних колеса повёрнуты на ОДИН угол (Аккермана нет) и шины
    # уводит. Считать бюджет по формуле было бы занижением на треть.
    wheelbase = 0.44
    r_model = wheelbase / math.tan(0.5)
    r_meas = 1.067
    print(f"  радиус поворота: велосипедная модель {r_model:.3f} м, "
          f"ЗАМЕР {r_meas:.3f} м (+{100*(r_meas/r_model-1):.0f} %)")

    print("""
  Какой манёвр вообще требуется. Цель — поза (0.7, 0, yaw=0), то есть нос
  машины смотрит НА ВЫЕЗД. Если заезжать передним ходом, последняя дуга
  радиуса R должна входить в место с курсом +x, а её начало с курсом +y
  лежит тогда в точке (0.7 - R, -R) = ({:.2f}, {:.2f}) — это за задней стеной
  (её грань на -0.15) и внутри соседнего места (его грань на -0.99).
  Значит ПЕРЕДНИМ ХОДОМ на место не заехать, и правильный манёвр —
  развернуться на дороге и сдать назад. Нижняя оценка его длины:""".format(
        0.7 - r_meas, -r_meas))
    arc = r_meas * math.pi / 2.0
    back = 2.05 - SPOT[0]
    need = arc + back
    print(f"    дуга разворота на 90 град  R*pi/2 = {arc:.3f} м")
    print(f"    задний ход по оси заезда   2.05 -> 0.70 = {back:.3f} м")
    print(f"    ИТОГО нижняя оценка пути                = {need:.3f} м")
    print("  (реальная траектория длиннее: сюда не входит выход на ось заезда)")

    # Бюджет пути: V_MAX * длительность эпизода минус потери на разгон и
    # торможение (замеры m5_final.py: разгон до 90 % 0.59 с, тормозной путь
    # 0.274 м).
    path_budget = V_MAX * EPISODE_SECONDS - 0.30 - 0.274
    print(f"\n  бюджет пути за эпизод = {V_MAX:.2f} м/с * {EPISODE_SECONDS:.1f} с "
          f"- 0.30 м (разгон) - 0.274 м (торможение) = {path_budget:.3f} м")
    print(f"  запас = {path_budget:.3f} / {need:.3f} = x{path_budget/need:.2f}")
    print("""  Для сравнения: у старой версии эпизод был 6 с, но машина ехала
  1.348 м/с при заявленных 1.08, то есть бюджет был ~8 м. Здесь предел скорости
  честный, поэтому эпизод удлинён до 9 с — иначе честная скорость молча
  сделала бы задачу нерешаемой.""")

    ctxs = []
    env.unwrapped.set_start_spread(1.0)
    for i in range(40):
        env.reset(seed=5000 + i)
        x, y, _ = env.unwrapped._pose()
        # к нижней оценке манёвра добавляем выход со старта на ось заезда
        extra = math.hypot(x - 2.05, y - 0.0)
        ctxs.append(Ctx(DT, need=need + extra))
    needs = [c["need"] for c in ctxs]
    print(f"\n  требуемый путь по 40 честным стартам: {min(needs):.3f} .. "
          f"{max(needs):.3f} м (среднее {np.mean(needs):.3f})")
    v = reachability(
        env.unwrapped.rewards["park"],
        achievable=lambda c: path_budget / c["need"],
        ctxs=ctxs,
    )
    print("  " + str(v).replace("\n", "\n  "))
    RESULTS["9 цель достижима за эпизод"] = v


# ===========================================================================
# 10. Цена шага
# ===========================================================================
def probe_10_cost(env) -> None:
    head(10, "ЦЕНА ШАГА")
    print("""  Старая версия: 10 390 шагов физики/с, из них 66 % бюджета съедал
  _collision(), звавший mujoco.mj_id2name по 16 раз на шаг (§4.3). Здесь id
  геомов предвычислены в __init__, а один шаг политики — это 5 шагов физики.""")
    c = probe_step_cost(env, n=4000, seed=0)
    print(f"  мкс на шаг политики      {c['us_per_step']:.1f}")
    print(f"  шагов политики в секунду {c['steps_per_s']:.0f}")
    print(f"  шагов ФИЗИКИ в секунду   {c['steps_per_s'] * 5:.0f}  "
          f"(старая версия: 10 390)")
    print(f"  реального времени на 1 с стены  {c['realtime_factor']:.0f}x  "
          f"(старая версия: 104x)")
    print(f"  часов на 1 млн шагов политики   {c['hours_per_1M']:.3f}  "
          f"(в одном процессе; SubprocVecEnv делит это на число сред)")
    RESULTS["10 цена шага"] = {k: c[k] for k in
                               ("us_per_step", "steps_per_s", "realtime_factor",
                                "hours_per_1M", "resets")}


def main() -> int:
    print("=" * 78)
    print("ПРОБЫ СРЕДЫ ПАРКОВКИ (трек А, урок 14) — ДО ОБУЧЕНИЯ")
    print("=" * 78)
    print(f"mujoco {mujoco.__version__}, numpy {np.__version__}")

    env = CarParkingEnv(in_spot_start_prob=0.0)
    try:
        probe_1_shapes(env)
        probe_2_pomdp()
        probe_3_observability(env)
        probe_4_discount()
        probe_5_disjoint(env)
        probe_6_termination(env)
        probe_7_baseline()
        probe_8_terms(env)
        probe_9_reachability(env)
        probe_10_cost(env)
    finally:
        env.close()

    print()
    print(report(RESULTS))

    red = []
    for name, res in RESULTS.items():
        if isinstance(res, Verdict) and not res.ok:
            red.append(name)
        elif isinstance(res, Table) and ("РАСХОЖДЕНИЙ" in (res.note or "")
                                         or "ВНИМАНИЕ" in (res.note or "")):
            red.append(name)
    if red:
        print("КРАСНЫЕ ПРОБЫ: " + ", ".join(red))
        print("Обучение начинать НЕЛЬЗЯ.")
        return 1
    print("Все пробы зелёные. Можно запускать train.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
