"""rl_toolkit.probes — замеры среды ДО обучения.

ПРАВИЛО, РАДИ КОТОРОГО МОДУЛЬ СУЩЕСТВУЕТ
    Любая правка среды, награды или наблюдения проверяется ЗАМЕРОМ до
    обучения. Прогон стоит часов, проба — секунды.
    Формулировка платформы (_probe_yaw_loop.py:5-7): «его цену можно узнать
    замером, не потратив ни шага обучения — как того требует правило,
    оплаченное прогоном r4p (“три дефекта, найденные ДО обучения”)».

ЧТО ЭТО ПРЕДОТВРАЩАЕТ

 1. Три дефекта r4p, каждый найден пробой, а не обучением
    (_launch_r4p.ps1:20-33, пересказ в 05_platform_code.md §5.1):
    * «Награда требовала geom НОМЕР 0 (плоский пол). Проверено: робот,
      стоящий обеими стопами на препятствии, числился ЛЕТЯЩИМ. Следствие —
      p_double_air -15/с, r_stride и r_air не начисляются, около -19/с ЗА ТО,
      ЧТО МАШИНА ЗАЛЕЗЛА НА ПРЕПЯТСТВИЕ. То есть награда платила за то, чтобы
      препятствия ОБХОДИТЬ.»  -> `probe_termination` и `probe_reward_terms`.
    * «На верхушке лестницы (+20 см) r_height падал 0.300 -> 0.120 = -9.0/с
      штрафа за подъём.»  -> `probe_termination` на состояниях «на опоре».
    * «H_CLEAR 0.06 -> 0.10 м. Плата насыщалась ровно на 6 см, и порог, на
      котором машина начинает падать, тоже 6 см… Кинематический максимум
      подъёма 178 мм, использовалось 34 %.»  -> `probe_controller_sweep`.

 2. «Штраф за то, чего нет в наблюдении» (06_pitfalls.md §A3, RESUME.md:67-79).
    В наблюдении политики 35 каналов, «ошибки курса там нет ни в каком виде».
    Штраф p_yaw прогнали 7 млн шагов — стало ХУЖЕ: путь по полигону
    2.56 -> 2.41 м, падения 18 -> 25. Лечение — не новый штраф, а обратная
    связь через уже наблюдаемый канал; свип коэффициента сделан НА ГОТОВЫХ
    ВЕСАХ: увод 112.3° -> 39.2° при K = 2.0, плато 1.6…2.6, падений 0/8.
    -> `probe_observability` и `probe_controller_sweep`.

 3. «Тихий старт» (06_pitfalls.md §A5, train_walk_r4.py:79-85).
    SB3 по умолчанию ставит std ~ 1.0 в нормированных единицах действия;
    «с шумом действий 1.0 случайная разведка мгновенно убивает 33-кг машину
    (приводы 112.86 Н·м), и траектория “стоять” ненаблюдаема; с тихим стартом
    ранние эпизоды ~ нулевое действие ~ выживание 1.8 с». A/B: политика жила
    0.17 с при пассивных 1.78 с.
    -> `probe_action_scale`: если |a| = 0 живёт дольше всех, разведка убивает
    машину раньше, чем чему-то учит, и лечится это log_std_init, а не наградой.

 4. «Цена шага» (_launch_r4p.ps1:41-44, C31): плоскость 5116 шагов/с, рельеф
    D=1.0 — 4389 (-14 %); `mj_step` 46.1 -> 10.7 -> 7.5 мкс при сужении масок
    контактов. Усложнение среды переводится прямо в часы обучения.
    -> `probe_step_cost`.

 5. ПРОБА САМА МОЖЕТ ВРАТЬ, и это отдельный урок:
    * `_probe_limp2.py:3-8` — объединение шагов всех эпизодов гасит блуждающий
      перекос и показывает ложное «симметрично», «а робот при этом хромает в
      каждом эпизоде». Поэтому агрегировать надо ПО ЭПИЗОДАМ, а не по
      объединённой выборке (здесь все пробы возвращают и разброс между
      эпизодами, а не только среднее).
    * `_probe_payload.py:81-83` — линейный тренд оставлял в «размахе» кривизну
      пути: «на 0.7 м/с это давало 1064 мм “тряски”, которой нет».
    * `_probe_stride.py:4-11` — в самой пробе стояла та же сломанная формула,
      что и в награде: «числа “0.4 -> 3.9 см”, записанные в журнал по этому
      скрипту, замером НЕ были». Проверять надо и награду, и измеритель
      (см. diagnostics.synthetic_rollout).

ЗАВИСИМОСТИ
    mujoco здесь НЕ импортируется вообще: пробы работают с любой средой
    gymnasium. Импортируйте mujoco только внутри своей среды.
"""

from __future__ import annotations

import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .diagnostics import Table, Verdict, null_policy_baseline, _env_dt, _zero_action
from .rewards import RewardRegistry

__all__ = [
    "probe_shapes",
    "probe_action_scale",
    "probe_null_baseline",
    "probe_reward_terms",
    "probe_termination",
    "probe_step_cost",
    "probe_observability",
    "probe_controller_sweep",
    "report",
]


# ---------------------------------------------------------------------------
# Формы, единицы, детерминизм
# ---------------------------------------------------------------------------


def probe_shapes(env, dt: Optional[float] = None, seed: int = 7) -> Dict[str, Any]:
    """Размерности, границы, dt, длина эпизода и детерминизм по seed.

    Смоук-проверка детерминизма: `env.reset(seed=k)` дважды обязан дать
    ПОБИТОВО равный obs. Если нет — все A/B-сравнения политик становятся
    шумом, и «улучшение» будет неотличимо от разброса.
    """
    obs_space, act_space = env.observation_space, env.action_space
    o1, _ = env.reset(seed=seed)
    o2, _ = env.reset(seed=seed)
    o1, o2 = np.asarray(o1), np.asarray(o2)
    same = bool(o1.shape == o2.shape and np.array_equal(o1, o2))
    step_dt = _env_dt(env, dt)
    spec = getattr(env, "spec", None)
    max_steps = getattr(spec, "max_episode_steps", None) or getattr(
        getattr(env, "unwrapped", env), "max_steps", None
    )
    out: Dict[str, Any] = {
        "obs_shape": tuple(np.shape(o1)),
        "obs_dtype": str(o1.dtype),
        "obs_space": str(obs_space),
        "action_shape": tuple(getattr(act_space, "shape", ()) or ()),
        "action_space": str(act_space),
        "action_low": getattr(act_space, "low", None),
        "action_high": getattr(act_space, "high", None),
        "dt": step_dt,
        "hz": 1.0 / step_dt,
        "max_episode_steps": max_steps,
        "max_episode_seconds": (max_steps * step_dt) if max_steps else None,
        "seed_deterministic": same,
    }
    if not same:
        print(
            "[формы] ВНИМАНИЕ: reset(seed=k) дважды дал РАЗНЫЕ наблюдения. "
            "Любое A/B на такой среде недостоверно.",
            flush=True,
        )
    return out


# ---------------------------------------------------------------------------
# Разведка и пассивная база
# ---------------------------------------------------------------------------


def probe_action_scale(
    env_fn: Callable[[], Any],
    levels: Sequence[float] = (0.0, 0.1, 0.3, 1.0),
    seconds: float = 5.0,
    n: int = 4,
    seed: int = 0,
) -> Table:
    """Сколько живёт эпизод при разведке амплитуды |a| = level * high.

    Если уровень 0.0 живёт ДОЛЬШЕ всех — разведка убивает машину раньше, чем
    чему-то учит: траектория «ничего не делать» ненаблюдаема, бутстрап
    value-функции не замыкается. Лечение — тихий старт (`log_std_init` около
    -2.3 вместо SB3-дефолта 0.0, то есть std ~ 0.1 вместо ~ 1.0), а НЕ
    правка награды и не куррикулум (06_pitfalls.md §A5).

    Замер платформы для калибровки: политика со std ~ 1 жила 0.17 с при
    пассивных 1.78 с; с тихим стартом ранние эпизоды сразу дали 1.93 с.

    Принимает `env_fn` (фабрику), а не готовую среду: каждый уровень меряется
    на своей свежей среде, иначе состояния протекают между замерами.
    """
    t = Table(
        title=f"разведка: время жизни при |a| = level * high ({n} эпизодов на уровень)",
        columns=["level", "жизнь, с", "разброс, с", "шагов", "награда", "обрывов"],
    )
    rows: List[Tuple[float, float]] = []
    for lvl in levels:
        rng = np.random.default_rng(seed)
        if lvl == 0.0:
            act_fn = None
        else:
            def act_fn(obs, space, _lvl=float(lvl), _rng=rng):
                high = np.asarray(getattr(space, "high", 1.0), dtype=np.float64)
                return (_lvl * _rng.uniform(-1.0, 1.0, space.shape) * high).astype(space.dtype)

        res = null_policy_baseline(env_fn, seconds=seconds, n=n, action_fn=act_fn, seed0=seed)
        rows.append((float(lvl), res["alive_s"]))
        t.add(**{
            "level": float(lvl),
            "жизнь, с": res["alive_s"],
            "разброс, с": res["alive_s_std"],
            "шагов": res["alive_steps"],
            "награда": res["return"],
            "обрывов": f"{res['terminated']}/{res['episodes']}",
        })
    best = max(rows, key=lambda r: r[1])
    if best[0] == 0.0 and len(rows) > 1:
        t.note = (
            "ВЫВОД: дольше всех живёт НУЛЕВОЕ действие — разведка убивает машину раньше,\n"
            "чем чему-то учит. Лечится тихим стартом (log_std_init), а не наградой\n"
            "и не куррикулумом (06_pitfalls.md §A5)."
        )
    else:
        t.note = f"дольше всех живёт level = {best[0]:g} ({best[1]:.3f} с)"
    return t


def probe_null_baseline(env_fn: Callable[[], Any], seconds: float = 5.0, n: int = 4) -> Dict[str, Any]:
    """Пассивная база: alive_s, награда, вклад членов. ОБЯЗАТЕЛЬНА до обучения.

    «Если ctrl=0 даёт те же 0.5 с и -0.15 м, все контроллеры не влияли вовсе»
    (_null_test.py:3-4). Политика, живущая МЕНЬШЕ этой базы, не управляет —
    она мешает.
    """
    return null_policy_baseline(env_fn, seconds=seconds, n=n)


# ---------------------------------------------------------------------------
# Члены награды на заданном поведении
# ---------------------------------------------------------------------------


def probe_reward_terms(
    env,
    policy: Optional[Callable[[Any], Any]] = None,
    seconds: float = 10.0,
    dt: Optional[float] = None,
    seed: int = 0,
) -> Table:
    """Ставка каждого члена в /с на заданном поведении (нулевом, случайном, готовом).

    Требует, чтобы среда клала вклады в `info["terms"]` (см. rewards.RewardRegistry).
    Столбец «доля» — кандидаты в душители.

    Отдельная колонка «/с по модулю» существует из-за B18: член, усредняющий
    ЗНАКОВУЮ величину, показывает ноль при полном отсутствии проблемы и при
    сильной знакопеременной раскачке одинаково. Ноль в «/с» при большом
    «/с по модулю» — это не «члена нет», это «члены гасят друг друга».
    """
    step_dt = _env_dt(env, dt)
    n_steps = max(1, int(round(float(seconds) / step_dt)))
    acc: Dict[str, float] = {}
    acc_abs: Dict[str, float] = {}
    nz: Dict[str, int] = {}
    obs, _ = env.reset(seed=seed)
    got = 0
    for _ in range(n_steps):
        a = _zero_action(env.action_space) if policy is None else policy(obs)
        obs, r, terminated, truncated, info = env.step(a)
        terms = info.get("terms") if isinstance(info, dict) else None
        if isinstance(terms, dict):
            got += 1
            for k, v in terms.items():
                acc[k] = acc.get(k, 0.0) + float(v)
                acc_abs[k] = acc_abs.get(k, 0.0) + abs(float(v))
                if float(v) != 0.0:
                    nz[k] = nz.get(k, 0) + 1
        if terminated or truncated:
            obs, _ = env.reset()
    t = Table(
        title=f"члены награды на заданном поведении ({got} шагов, {got*step_dt:.3f} с)",
        columns=["член", "награда/с", "/с по модулю", "доля |суммы|", "ненулевых", "пометка"],
    )
    if got == 0:
        t.note = (
            "ВНИМАНИЕ: среда не кладёт вклады в info['terms'] — калибровать веса нечем. "
            "Заведите rewards.RewardRegistry."
        )
        return t
    abs_total = sum(abs(v) for v in acc.values()) or 1.0
    for k in sorted(acc, key=lambda x: -abs(acc[x])):
        per_s = acc[k] / got / step_dt
        per_s_abs = acc_abs[k] / got / step_dt
        share = abs(acc[k]) / abs_total
        mark = []
        if share > 0.40:
            mark.append("кандидат в душители")
        if abs(per_s) < 1e-9 < per_s_abs:
            mark.append("ЗНАКОПЕРЕМЕННЫЙ: среднее 0 при ненулевом модуле (B18)")
        t.add(**{
            "член": k, "награда/с": per_s, "/с по модулю": per_s_abs,
            "доля |суммы|": share, "ненулевых": nz.get(k, 0), "пометка": "; ".join(mark),
        })
    return t


# ---------------------------------------------------------------------------
# Условия обрыва эпизода
# ---------------------------------------------------------------------------


def probe_termination(env, cases: Dict[str, Any], dt: Optional[float] = None) -> Table:
    """Срабатывают ли условия обрыва там, где должны, и НЕ срабатывают ли там, где не должны.

    `cases`: {имя: (состояние, ожидаемое_terminated)} либо
             {имя: состояние}, где в состоянии есть ключ 'expect_terminated'.
    Среда обязана уметь `env.unwrapped.set_probe_state(state)` — тонкий метод
    «поставить машину в заданную позу», нужный только для проб.

    Ложное падение — самый дорогой класс: у r4p «робот, стоящий обеими стопами
    на препятствии, числился ЛЕТЯЩИМ», и награда платила за то, чтобы
    препятствия ОБХОДИТЬ (_launch_r4p.ps1:20-24).
    """
    u = getattr(env, "unwrapped", env)
    setter = getattr(u, "set_probe_state", None)
    t = Table(
        title="условия обрыва эпизода",
        columns=["случай", "ожидалось", "получено", "совпало"],
    )
    if setter is None:
        t.note = (
            "ВНИМАНИЕ: у среды нет метода set_probe_state(state) — проверить условия обрыва "
            "нечем. Добавьте его: пять строк в среде против прогона вслепую."
        )
        return t
    bad = 0
    for name, case in cases.items():
        if isinstance(case, tuple):
            state, expect = case[0], bool(case[1])
        else:
            state = dict(case)
            expect = bool(state.pop("expect_terminated"))
        env.reset(seed=0)
        setter(state)
        _, _, terminated, _, _ = env.step(_zero_action(env.action_space))
        ok = bool(terminated) == expect
        bad += (not ok)
        t.add(**{"случай": name, "ожидалось": expect, "получено": bool(terminated), "совпало": ok})
    t.note = (
        "все случаи сошлись"
        if bad == 0
        else f"РАСХОЖДЕНИЙ: {bad}. Условие обрыва срабатывает не там, где задумано — "
             f"это дороже любой правки награды."
    )
    return t


# ---------------------------------------------------------------------------
# Цена шага
# ---------------------------------------------------------------------------


def probe_step_cost(env, n: int = 2000, dt: Optional[float] = None, seed: int = 0) -> Dict[str, Any]:
    """мкс на env.step и шагов/с. Мерить ДО прогона.

    Цена усложнения среды выражается прямо в часах обучения: у платформы
    рельеф стоил -14 % (5116 -> 4389 шагов/с), а сужение масок контактов
    вернуло `mj_step` с 46.1 до 10.7 мкс (_launch_r4p.ps1:41-44).
    Полезная арифметика: `часы = шаги / (шагов_в_секунду * 3600)`.
    """
    step_dt = _env_dt(env, dt)
    a = _zero_action(env.action_space)
    env.reset(seed=seed)
    # прогрев: первый шаг тянет ленивую инициализацию и врёт
    for _ in range(min(50, n)):
        _, _, term, trunc, _ = env.step(a)
        if term or trunc:
            env.reset()
    t0 = time.perf_counter()
    done_count = 0
    for _ in range(int(n)):
        _, _, term, trunc, _ = env.step(a)
        if term or trunc:
            env.reset()
            done_count += 1
    el = time.perf_counter() - t0
    sps = float(n) / el
    return {
        "us_per_step": el / float(n) * 1e6,
        "steps_per_s": sps,
        "n": int(n),
        "wall_s": el,
        "resets": done_count,
        "realtime_factor": sps * step_dt,
        "hours_per_1M": 1e6 / sps / 3600.0,
    }


# ---------------------------------------------------------------------------
# Наблюдаемость
# ---------------------------------------------------------------------------


def probe_observability(
    env,
    quantity: Callable[[Any], float],
    obs_index: Optional[Sequence[int]] = None,
    n: int = 200,
    tol: float = 1e-3,
    seed: int = 0,
    policy: Optional[Callable[[Any], Any]] = None,
) -> Verdict:
    """Наблюдаема ли величина, которую собирается штрафовать награда.

    Метод — «одинаковый вход, разный ответ»: если в выборке нашлись состояния
    с ПРАКТИЧЕСКИ ОДИНАКОВЫМ наблюдением, но существенно разной величиной,
    политика физически не может её различить. Дополнительно печатается R²
    линейной регрессии величины на наблюдение — как справка, а не как вердикт
    (величина может быть наблюдаема нелинейно).

    Штраф за ненаблюдаемое — это шум, а не сигнал: у платформы p_yaw за 7 млн
    шагов ухудшил всё (путь 2.56 -> 2.41 м, падения 18 -> 25), потому что
    ошибки курса не было в наблюдении ни в каком виде (06_pitfalls.md §A3).
    Лечение — не новый штраф, а либо добавить величину в наблюдение, либо
    замкнуть контур через уже наблюдаемый канал.
    """
    rng = np.random.default_rng(seed)
    obs, _ = env.reset(seed=seed)
    X: List[np.ndarray] = []
    y: List[float] = []
    u = getattr(env, "unwrapped", env)
    for _ in range(int(n)):
        o = np.asarray(obs, dtype=np.float64).ravel()
        X.append(o if obs_index is None else o[list(obs_index)])
        y.append(float(quantity(u)))
        a = (
            rng.uniform(-1.0, 1.0, env.action_space.shape).astype(env.action_space.dtype)
            if policy is None
            else policy(obs)
        )
        obs, _, term, trunc, _ = env.step(a)
        if term or trunc:
            obs, _ = env.reset()
    Xa = np.asarray(X, dtype=np.float64)
    ya = np.asarray(y, dtype=np.float64)

    sy = float(ya.std())
    scale = Xa.std(axis=0)
    scale[scale < 1e-12] = 1.0
    Z = Xa / scale

    worst = 0.0
    n_dup = 0
    for i in range(len(Z)):
        d = np.max(np.abs(Z[i + 1:] - Z[i]), axis=1) if i + 1 < len(Z) else np.empty(0)
        near = np.nonzero(d < tol)[0]
        if near.size:
            n_dup += int(near.size)
            worst = max(worst, float(np.max(np.abs(ya[i + 1 + near] - ya[i]))))

    A = np.hstack([Xa, np.ones((len(Xa), 1))])
    coef, *_ = np.linalg.lstsq(A, ya, rcond=None)
    resid = ya - A @ coef
    r2 = 1.0 - float(resid.var()) / (float(ya.var()) + 1e-30)

    rel = worst / (sy + 1e-30)
    nums = {
        "пар с одинаковым obs": float(n_dup),
        "макс разброс величины": worst,
        "в долях сигмы": rel,
        "R2 линейной модели": r2,
    }
    if n_dup and rel > 0.1:
        return Verdict(
            "величина НЕ наблюдаема",
            ok=False,
            detail=(
                f"нашлось {n_dup} пар состояний с практически одинаковым наблюдением, "
                f"но величина в них расходится до {worst:.4g} ({rel:.2f} сигмы). "
                f"Штрафовать её бессмысленно: политика не может её различить. "
                f"Либо добавьте величину в obs, либо замкните контур в управлении "
                f"(06_pitfalls.md §A3)."
            ),
            numbers=nums,
        )
    if n_dup:
        return Verdict(
            "величина наблюдаема",
            ok=True,
            detail=(
                f"на {n_dup} парах с одинаковым наблюдением величина совпадает "
                f"(расхождение {rel:.4f} сигмы); R2 линейной модели {r2:.3f}"
            ),
            numbers=nums,
        )
    return Verdict(
        "проверка не состоялась",
        ok=False,
        detail=(
            "в выборке нет ни одной пары состояний с одинаковым наблюдением — "
            "увеличьте n или tol, иначе вывод о наблюдаемости не обоснован. "
            f"R2 линейной модели {r2:.3f} сам по себе доказательством не является."
        ),
        numbers=nums,
    )


# ---------------------------------------------------------------------------
# Свип параметра НА ГОТОВЫХ ВЕСАХ
# ---------------------------------------------------------------------------


def probe_controller_sweep(
    env,
    policy: Optional[Callable[[Any], Any]],
    param: str,
    values: Sequence[float],
    metric: Callable[[List[Dict[str, Any]]], float],
    seconds: float = 5.0,
    episodes: int = 1,
    dt: Optional[float] = None,
    seed: int = 0,
) -> Table:
    """Свип параметра среды/контура НА ГОТОВЫХ ВЕСАХ.

    Если правка не меняет размерность наблюдения, её цену можно узнать за
    минуты вместо суток прогона. Так на платформе выбрали K контура курса:
    увод 112.3° при K=0 против 39.2° при K=2.0, плато 1.6…2.6 — выбор
    сознательно НЕ на краю плато (RESUME.md:95-104).

    Параметр применяется через `env.unwrapped.set_<param>(value)`, а если
    такого метода нет — через `setattr(env.unwrapped, param, value)`.
    `metric(rollout) -> float`, где rollout — список
    {'obs', 'action', 'reward', 'next_obs', 'terminated', 'truncated', 'info'}.
    Метрику считать по 'next_obs': именно там лежит состояние, на котором
    эпизод оборвался, а 'obs' — состояние ДО шага (классическая ошибка на
    единицу в измерителе).
    """
    u = getattr(env, "unwrapped", env)
    setter = getattr(u, f"set_{param}", None)
    step_dt = _env_dt(env, dt)
    n_steps = max(1, int(round(float(seconds) / step_dt)))
    t = Table(
        title=f"свип параметра {param!r} на готовых весах ({episodes} эп. по {seconds:g} с)",
        columns=[param, "метрика", "разброс", "жизнь, с", "награда"],
    )
    best: Optional[Tuple[float, float]] = None
    for val in values:
        if setter is not None:
            setter(float(val))
        else:
            setattr(u, param, float(val))
        ms: List[float] = []
        lives: List[float] = []
        rets: List[float] = []
        for ep in range(int(episodes)):
            obs, _ = env.reset(seed=seed + ep)
            roll: List[Dict[str, Any]] = []
            total = 0.0
            k = 0
            for k in range(1, n_steps + 1):
                a = _zero_action(env.action_space) if policy is None else policy(obs)
                nobs, r, term, trunc, info = env.step(a)
                roll.append({"obs": obs, "action": a, "reward": float(r), "next_obs": nobs,
                             "terminated": bool(term), "truncated": bool(trunc), "info": info})
                total += float(r)
                obs = nobs
                if term or trunc:
                    break
            ms.append(float(metric(roll)))
            lives.append(k * step_dt)
            rets.append(total)
        m = float(np.mean(ms))
        t.add(**{
            param: float(val), "метрика": m, "разброс": float(np.std(ms)),
            "жизнь, с": float(np.mean(lives)), "награда": float(np.mean(rets)),
        })
        if best is None or m > best[1]:
            best = (float(val), m)
    if best is not None:
        edge = best[0] in (float(values[0]), float(values[-1]))
        t.note = f"максимум метрики при {param} = {best[0]:g} ({best[1]:.4f})" + (
            "  <-- НА КРАЮ ДИАПАЗОНА: расширьте свип, оптимум может лежать дальше"
            if edge else "  (оптимум внутри диапазона — выбор не на краю)"
        )
    return t


# ---------------------------------------------------------------------------
# Сводка
# ---------------------------------------------------------------------------


def report(results: Dict[str, Any]) -> str:
    """Печатная сводка со светофором: '!!' — красное, 'OK' — зелёное, '..' — справка."""
    out: List[str] = []
    out.append("=" * 78)
    out.append("СВОДКА ПРОБ")
    out.append("=" * 78)
    for name, res in results.items():
        if isinstance(res, Verdict):
            out.append(f"[{'OK' if res.ok else '!!'}] {name}")
            out.append("     " + str(res).replace("\n", "\n     "))
        elif isinstance(res, Table):
            bad = "РАСХОЖДЕНИЙ" in (res.note or "") or "ВНИМАНИЕ" in (res.note or "")
            out.append(f"[{'!!' if bad else '..'}] {name}")
            out.append("     " + str(res).replace("\n", "\n     "))
        elif isinstance(res, dict):
            out.append(f"[..] {name}")
            for k, v in res.items():
                if isinstance(v, float):
                    out.append(f"     {k:<24} {v:.4f}")
                elif not isinstance(v, (np.ndarray, list, tuple)) or np.size(v) <= 8:
                    out.append(f"     {k:<24} {v}")
        else:
            out.append(f"[..] {name}: {res}")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# САМОПРОВЕРКА
# ---------------------------------------------------------------------------


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError("САМОПРОВЕРКА ПРОВАЛЕНА: " + msg)


def _selftest() -> int:
    import math

    import gymnasium as gym
    from gymnasium import spaces

    print("=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.probes")
    print("=" * 78)

    # ------------------------------------------------------------------
    # Среда 1: периодическая. Наблюдение повторяется каждые 20 шагов,
    # а скрытый счётчик — нет. Ответы известны заранее.
    # ------------------------------------------------------------------
    class _PhaseEnv(gym.Env):
        metadata = {"render_modes": []}
        dt = 0.05                    # 20 Гц
        PERIOD = 20                  # шагов в периоде
        max_steps = 1000

        def __init__(self):
            self.observation_space = spaces.Box(-10.0, 10.0, (3,), dtype=np.float32)
            self.action_space = spaces.Box(-1.0, 1.0, (1,), dtype=np.float32)
            self.gain = 1.0

        def set_gain(self, v):        # для probe_controller_sweep
            self.gain = float(v)

        def _obs(self):
            return np.array(
                [math.sin(self.phase), math.cos(self.phase), self.gain], dtype=np.float32
            )

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            self.k = 0
            self.phase = 0.0
            return self._obs(), {}

        def step(self, action):
            u = float(np.asarray(action).reshape(-1)[0])
            self.k += 1
            self.phase += 2.0 * math.pi / self.PERIOD
            terms = {
                "alive": 1.0,
                "effort": -0.5 * u * u,
                "swing": 0.1 * math.sin(self.phase),   # ЗНАКОПЕРЕМЕННЫЙ член
            }
            r = sum(terms.values())
            return self._obs(), r, False, self.k >= self.max_steps, {"terms": terms}

    # ------------------------------------------------------------------
    # Среда 2: валится. x'' = k*x + gain*u; при u = 0 время жизни известно
    # аналитически: acosh(1/x0)/sqrt(k).
    # ------------------------------------------------------------------
    class _FallEnv(gym.Env):
        metadata = {"render_modes": []}
        dt = 0.01

        def __init__(self, k: float = 25.0, x0: float = 0.01, gain: float = 20.0):
            self.observation_space = spaces.Box(-np.inf, np.inf, (2,), dtype=np.float32)
            self.action_space = spaces.Box(-1.0, 1.0, (1,), dtype=np.float32)
            self.k, self.x0, self.gain = k, x0, gain

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            self.x, self.v = self.x0, 0.0
            return np.array([self.x, self.v], dtype=np.float32), {}

        def step(self, action):
            u = float(np.clip(np.asarray(action).reshape(-1)[0], -1.0, 1.0))
            self.v += self.dt * (self.k * self.x + self.gain * u)
            self.x += self.dt * self.v
            return (
                np.array([self.x, self.v], dtype=np.float32),
                1.0, abs(self.x) > 1.0, False, {"terms": {"alive": 1.0}},
            )

    # ------------------------------------------------------------------
    # Среда 3: условие обрыва. Сломанная версия меряет высоту от
    # АБСОЛЮТНОГО нуля, исправная — от опоры (B17 / дефект r4p № 2).
    # ------------------------------------------------------------------
    class _TermEnv(gym.Env):
        metadata = {"render_modes": []}
        dt = 0.02

        def __init__(self, absolute_height: bool = True):
            self.observation_space = spaces.Box(-10.0, 10.0, (2,), dtype=np.float32)
            self.action_space = spaces.Box(-1.0, 1.0, (1,), dtype=np.float32)
            self.absolute = bool(absolute_height)
            self.z_over_support, self.support = 0.45, 0.0

        def set_probe_state(self, state):
            self.z_over_support = float(state["z_over_support"])
            self.support = float(state["support"])

        def _obs(self):
            return np.array([self.z_over_support, self.support], dtype=np.float32)

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            self.z_over_support, self.support = 0.45, 0.0
            return self._obs(), {}

        def step(self, action):
            if self.absolute:
                fallen = (self.z_over_support + self.support) < 0.50   # СЛОМАНО
            else:
                fallen = self.z_over_support < 0.30                    # верно
            return self._obs(), 1.0, bool(fallen), False, {}

    results: Dict[str, Any] = {}

    # --- 1. Формы -------------------------------------------------------
    print("\n1. probe_shapes")
    env = _PhaseEnv()
    sh = probe_shapes(env)
    results["формы и единицы"] = sh
    for k in ("obs_shape", "action_shape", "dt", "hz", "max_episode_steps", "seed_deterministic"):
        print(f"   {k:<20} {sh[k]}")
    _check(sh["obs_shape"] == (3,), f"obs_shape={sh['obs_shape']}, ожидалось (3,)")
    _check(sh["action_shape"] == (1,), f"action_shape={sh['action_shape']}, ожидалось (1,)")
    _check(abs(sh["dt"] - 0.05) < 1e-12, "dt не подхвачен из среды")
    _check(abs(sh["hz"] - 20.0) < 1e-9, "частота посчитана неверно")
    _check(sh["seed_deterministic"] is True, "среда недетерминирована по seed")

    # --- 2. Цена шага ---------------------------------------------------
    print("\n2. probe_step_cost")
    cost = probe_step_cost(env, n=3000)
    results["цена шага"] = cost
    print(f"   {cost['us_per_step']:.2f} мкс/шаг, {cost['steps_per_s']:.0f} шагов/с, "
          f"реальное время x{cost['realtime_factor']:.0f}")
    print(f"   1 млн шагов этой среды = {cost['hours_per_1M']:.3f} ч чистого времени среды")
    print("   (для сравнения: у боевой платформы плоскость 5116 шагов/с,")
    print("    рельеф D=1.0 — 4389, то есть -14 % — _launch_r4p.ps1:41-44)")
    _check(cost["us_per_step"] > 0 and cost["steps_per_s"] > 0, "цена шага не измерена")

    # --- 3. Разведка ----------------------------------------------------
    print("\n3. probe_action_scale (среда, которая валится)")
    scale = probe_action_scale(_FallEnv, levels=(0.0, 0.1, 0.3, 1.0), seconds=5.0, n=4)
    results["масштаб разведки"] = scale
    print(str(scale))
    lives = scale.column("жизнь, с")
    _check(lives[0] == max(lives), "нулевое действие обязано жить дольше всех в этой среде")
    _check(lives[-1] < lives[0], "разведка амплитуды 1.0 обязана убивать быстрее")
    analytic = math.acosh(1.0 / 0.01) / math.sqrt(25.0)
    _check(abs(lives[0] - analytic) < 0.05,
           f"пассивная жизнь {lives[0]:.3f} с против аналитики {analytic:.3f} с")
    print(f"   аналитика пассивной жизни: acosh(1/0.01)/sqrt(25) = {analytic:.3f} с — совпало")

    # --- 4. Пассивная база ----------------------------------------------
    print("\n4. probe_null_baseline")
    nb = probe_null_baseline(_FallEnv, seconds=5.0, n=4)
    results["пассивная база"] = {k: v for k, v in nb.items() if k != "terms"}
    print(f"   жизнь {nb['alive_s']:.3f} с, награда {nb['return']:.2f}, "
          f"вклады/с: {dict((k, round(v, 2)) for k, v in nb['terms'].items())}")
    _check(abs(nb["alive_s"] - analytic) < 0.05, "пассивная база разошлась с аналитикой")
    _check(abs(nb["terms"]["alive"] - 100.0) < 1e-9, "ставка alive обязана быть 1/dt = 100/с")

    # --- 5. Члены награды -----------------------------------------------
    print("\n5. probe_reward_terms (нулевое действие, 10 с = 200 шагов = 10 периодов)")
    env2 = _PhaseEnv()
    terms_tbl = probe_reward_terms(env2, policy=None, seconds=10.0)
    results["члены награды"] = terms_tbl
    print(str(terms_tbl))
    rate_alive = terms_tbl.column("награда/с")[terms_tbl.column("член").index("alive")]
    i_sw = terms_tbl.column("член").index("swing")
    rate_swing = terms_tbl.column("награда/с")[i_sw]
    abs_swing = terms_tbl.column("/с по модулю")[i_sw]
    _check(abs(rate_alive - 20.0) < 1e-9, f"ставка alive {rate_alive}, ожидалось 1/dt = 20.0")
    _check(abs(rate_swing) < 1e-9, "знакопеременный член обязан дать ноль в среднем")
    _check(abs_swing > 1.0, "у знакопеременного члена модуль обязан быть заметным")
    _check("ЗНАКОПЕРЕМЕННЫЙ" in terms_tbl.column("пометка")[i_sw],
           "знакопеременный член не помечен (B18)")
    print(f"   swing: {rate_swing:.6f}/с в среднем при {abs_swing:.3f}/с по модулю —")
    print("   это НЕ «члена нет», это «члены гасят друг друга» (B18).")

    # --- 6. Условия обрыва ----------------------------------------------
    print("\n6. probe_termination: высота от абсолютного нуля против высоты над опорой")
    cases = {
        "стоит на полу (0.45 над опорой)": ({"z_over_support": 0.45, "support": 0.0}, False),
        "стоит на препятствии +0.20":      ({"z_over_support": 0.45, "support": 0.20}, False),
        "упал на полу (0.10)":             ({"z_over_support": 0.10, "support": 0.0}, True),
        "упал на препятствии +0.20":       ({"z_over_support": 0.10, "support": 0.20}, True),
    }
    broken = probe_termination(_TermEnv(absolute_height=True), cases)
    print(str(broken))
    results["обрыв эпизода (сломанная версия)"] = broken
    n_bad = sum(1 for ok in broken.column("совпало") if not ok)
    _check(n_bad == 1, f"проба нашла {n_bad} расхождений, ожидалось ровно 1")
    _check(broken.column("совпало")[0] is False,
           "проба обязана поймать ложное падение на ровном полу")

    fixed = probe_termination(_TermEnv(absolute_height=False), cases)
    print("\n" + str(fixed))
    results["обрыв эпизода (исправленная)"] = fixed
    _check(all(fixed.column("совпало")), "исправленная версия обязана пройти все случаи")
    print("   вывод: порог, отсчитанный от АБСОЛЮТНОГО нуля, объявляет упавшей стоящую")
    print("   машину — тот же класс, что дефект r4p № 2 (_launch_r4p.ps1:25-28).")

    # --- 7. Наблюдаемость -----------------------------------------------
    print("\n7. probe_observability")
    env3 = _PhaseEnv()
    v_obs = probe_observability(env3, quantity=lambda u: math.sin(u.phase) ** 2, n=200)
    print("   величина sin^2(phase) (выводится из наблюдения):")
    print("   " + str(v_obs).replace("\n", "\n   "))
    results["наблюдаемость: sin^2(phase)"] = v_obs
    _check(v_obs.ok, "наблюдаемая величина объявлена ненаблюдаемой")

    env4 = _PhaseEnv()
    v_hidden = probe_observability(env4, quantity=lambda u: float(u.k), n=200)
    print("   величина «номер шага» (в наблюдении её нет):")
    print("   " + str(v_hidden).replace("\n", "\n   "))
    results["наблюдаемость: скрытый счётчик"] = v_hidden
    _check(not v_hidden.ok, "ненаблюдаемая величина НЕ поймана")
    _check(v_hidden.numbers["пар с одинаковым obs"] > 0, "проба не нашла повторов наблюдения")
    print("   вывод: наблюдение повторяется каждые 20 шагов, а счётчик — нет.")
    print("   Штраф за такую величину — шум (06_pitfalls.md §A3: p_yaw ухудшил")
    print("   путь 2.56 -> 2.41 м и падения 18 -> 25 за 7 млн шагов).")

    # --- 8. Свип на готовых весах ---------------------------------------
    print("\n8. probe_controller_sweep: свип усиления контура")
    # «Готовая политика»: пропорциональный регулятор по x. Метрика — минус
    # конечное |x| (чем ближе к нулю, тем лучше). Ответ известен заранее:
    # при gain*20 около k=25 система стабилизируется, при слабом — валится.
    class _GainFallEnv(_FallEnv):
        def __init__(self):
            super().__init__()
            self.loop_k = 0.0

        def set_loop_k(self, v):
            self.loop_k = float(v)

        def step(self, action):
            u = float(np.asarray(action).reshape(-1)[0]) - self.loop_k * self.x
            return super().step(np.array([np.clip(u, -1.0, 1.0)], dtype=np.float32))

    def metric_final_x(roll):
        # именно next_obs: там состояние, на котором эпизод оборвался
        return -abs(float(roll[-1]["next_obs"][0]))

    genv = _GainFallEnv()
    sweep = probe_controller_sweep(
        genv, policy=None, param="loop_k",
        values=(0.0, 1.0, 2.0, 4.0, 8.0), metric=metric_final_x, seconds=3.0,
    )
    print(str(sweep))
    results["свип контура"] = sweep
    mm = sweep.column("метрика")
    lv = sweep.column("жизнь, с")
    _check(mm[0] < mm[2], "усиление контура обязано улучшать метрику в этой среде")
    _check(mm[0] <= -1.0, "при нулевом усилении машина обязана уйти за |x| = 1")
    _check(lv[0] < 3.0 <= lv[2], "без контура эпизод обязан обрываться, с контуром — доживать")
    print("   (так на платформе выбрали K контура курса: увод 112.3° при K=0 против")
    print("    39.2° при K=2.0, плато 1.6…2.6 — и выбор сознательно НЕ на краю плато)")

    # --- 9. Сводка ------------------------------------------------------
    print("\n9. report()")
    text = report(results)
    print(text)
    _check("СВОДКА ПРОБ" in text, "сводка не собралась")
    _check("[!!]" in text, "в сводке нет ни одной красной строки, хотя дефекты заложены")

    env.close(); env2.close(); env3.close(); env4.close(); genv.close()

    print("=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.probes ПРОЙДЕНА")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(_selftest())
