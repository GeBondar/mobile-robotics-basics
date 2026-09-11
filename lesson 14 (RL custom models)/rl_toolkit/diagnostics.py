"""rl_toolkit.diagnostics — проверка члена награды и метрики ДО обучения.

ЗАЧЕМ ЭТО НУЖНО
    Прогон стоит часов, проверка — секунд. Два класса дефектов, которые
    обучение НЕ покажет никогда (они выглядят как «растущая награда»):

    (1) МЕТРИКА, ТОЖДЕСТВЕННО РАВНАЯ НУЛЮ для целевого движения;
    (2) ФОРМА ПЛАТЫ, у которой ставка в секунду НЕ ЗАВИСИТ от той величины,
        за которую член якобы платит.

    Обе ловятся арифметикой на синтетике с заранее известным ответом.

ЧТО ЭТО ПРЕДОТВРАЩАЕТ

 A1. «Метрика, которая всегда равна нулю» (06_pitfalls.md §A1,
     walk_env_r4.py:128-140, RESUME.md:400-406).
     Длина шага мерилась как смещение стопы В СК КОРПУСА между двумя
     посадками одной ноги. Для ЛЮБОЙ периодической походки это тождественный
     ноль: корпус уехал ровно настолько же, насколько уехала стопа.
     «На синтетических походках 0.10 / 0.30 / 0.45 м метрика даёт 0.0000 м
     во всех трёх. Живая политика собирала по нему 21.9 награды/с, то есть он
     платил за АПЕРИОДИЧНОСТЬ.» Цена: три прогона (r4g/r4h/r4i) отчитывались
     числами, которых не существовало; шаг был 58 мм при кинематическом
     потолке 473 мм — 12 % от возможного (RESUME.md:392-396).
     ТА ЖЕ ошибка сидела в измерительном скрипте `_probe_stride.py`, поэтому
     сверка «награда против пробы» её не ловила: одна формула, скопированная
     в оба места, даёт СОГЛАСОВАННУЮ ЛОЖЬ.
     Здесь это ловит `synthetic_rollout` (см. самопроверку, п.2).

 A2. «Форма платы без градиента» (06_pitfalls.md §A2, walk_env_r4.py:141-147,
     RESUME.md:407-412).
     Плата вида `min(L / L_cap, 1)` начисляется за каждую посадку. При каденсе
     f посадок в секунду 2f, значит ставка = `2f * W * L / L_cap`. Но в
     установившейся ходьбе `L * f = v` (скорость задана командой), поэтому
     ставка = `2 * W * v / L_cap` — ДЛИНА СОКРАЩАЕТСЯ.
     Замер платформы: «L = 0.058 м -> 11.33/с, L = 0.300 м -> 11.16/с. Ровно
     ноль градиента. Подъём веса 8->12 на 70M не мог ничего изменить и не
     изменил.» То же у r_air: `min(t,cap)/cap` при `t = (1-duty)/f` не зависит
     от f вообще.
     Лечение — плата СМЕЩЕНИЕМ ОТ ПОРОГА: `gain = min(L, lmax) - l0`, ставка
     `2W*(v - l0*f)`, строго убывает по каденсу; посадка короче порога — ЧИСТЫЙ
     ШТРАФ, а не «менее выгодная награда». После правки «оптимум ставки 1.25 Гц
     при шаге 0.320 м, а походка 5.25 Гц / 0.058 м получает -14.0/с вместо
     прежних +22.8/с» (_launch_r4j.ps1:9-11); прогон r4j дал шаг 11.2 -> 34.1 см,
     каденс 5.1 -> 2.0 Гц, слежение 78 -> 91.7 % (RESUME.md:477-485).
     Здесь это ловит `sweep_term` + `gradient_report` (самопроверка, п.1).

 A3. «Пассивная база». `_null_test.py:3-4`: «Если ctrl=0 даёт те же 0.5 с и
     -0.15 м, все контроллеры не влияли вовсе». Замер платформы: политика жила
     0.17 с при пассивных 1.78 с (walk_env_r4.py:49-51), то есть обученная
     политика была в десять раз хуже ВЫКЛЮЧЕННОГО робота.
     Здесь это `null_policy_baseline`.

 A4. «Недостижимый порог». walk_env_r4.py:210-221: «Достижимый шаг равен
     v/каденс: при 0.25 м/с и 2.3 Гц это 10.9 см, то есть КОНСТАНТНЫЙ порог
     12 см физически недостижим и штраф платится при любом поведении. Уйти от
     него можно только одним способом — свалить работу на одну ногу.»
     Замер последствия (_probe_limp2.py на r4m 146.5M): назад 0.25 — шаг Л/П
     16.0/11.4 см, потеряно контактов 20 %/5 %; назад 0.60 — 34.8/35.0 см,
     потеряно 1 %/2 %, хромоты НЕТ.
     Здесь это `reachability`.

ГЛАВНОЕ ПРАВИЛО МОДУЛЯ
    Проверяется СТАВКА В СЕКУНДУ, а не значение за шаг. Почти все ошибки формы
    видны только после умножения платы на частоту события.
    И: аналитика первична. Если rate(x) = const, никакой вес не поможет.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np

from .rewards import Ctx, RewardRegistry, Term

__all__ = [
    "Table",
    "Verdict",
    "sweep_term",
    "gradient_report",
    "synthetic_rollout",
    "periodic_gait",
    "null_policy_baseline",
    "reachability",
    "term_share_table",
]


# ---------------------------------------------------------------------------
# Печатные примитивы
# ---------------------------------------------------------------------------


@dataclass
class Table:
    """Табличка с именованными колонками. Печатается как есть в отчёт урока."""

    title: str
    columns: List[str]
    rows: List[Dict[str, Any]] = field(default_factory=list)
    note: str = ""

    def add(self, **cells: Any) -> "Table":
        missing = set(self.columns) - set(cells)
        if missing:
            raise ValueError(f"в строке таблицы нет колонок: {sorted(missing)}")
        self.rows.append({c: cells[c] for c in self.columns})
        return self

    def column(self, name: str) -> List[Any]:
        if name not in self.columns:
            raise KeyError(f"колонки {name!r} нет; есть: {self.columns}")
        return [r[name] for r in self.rows]

    @staticmethod
    def _fmt(v: Any) -> str:
        if isinstance(v, bool):
            return "да" if v else "НЕТ"
        if isinstance(v, float):
            if v != v or abs(v) in (float("inf"),):
                return str(v)
            return f"{v:.4f}" if abs(v) < 1e5 else f"{v:.4g}"
        return str(v)

    def __str__(self) -> str:
        cells = [[self._fmt(r[c]) for c in self.columns] for r in self.rows]
        widths = [
            max(len(c), *(len(row[i]) for row in cells)) if cells else len(c)
            for i, c in enumerate(self.columns)
        ]
        out = [self.title] if self.title else []
        out.append(" | ".join(c.rjust(w) for c, w in zip(self.columns, widths)))
        out.append("-+-".join("-" * w for w in widths))
        for row in cells:
            out.append(" | ".join(v.rjust(w) for v, w in zip(row, widths)))
        if self.note:
            out.append(self.note)
        return "\n".join(out)


@dataclass(frozen=True)
class Verdict:
    """Вердикт диагностики: короткая метка + числа, на которых он основан."""

    verdict: str
    ok: bool
    detail: str = ""
    numbers: Dict[str, float] = field(default_factory=dict)

    def __str__(self) -> str:
        nums = ", ".join(f"{k}={v:.4g}" for k, v in self.numbers.items())
        mark = "OK " if self.ok else "!! "
        return f"{mark}ВЕРДИКТ: {self.verdict}" + (f" ({nums})" if nums else "") + (
            f"\n    {self.detail}" if self.detail else ""
        )


# ---------------------------------------------------------------------------
# Свип члена награды
# ---------------------------------------------------------------------------

NO_GRADIENT = "нет градиента"
HAS_GRADIENT = "градиент есть"
REVERSED_GRADIENT = "градиент ОБРАТНЫЙ"

COL_RATE = "награда/с"
COL_RAW = "сырое"


def sweep_term(
    term: Term,
    axis: str,
    values: Sequence[float],
    make_ctx: Callable[[float], Ctx],
    dt: float,
) -> Table:
    """Ставка члена (награда/с) как функция ОДНОЙ физической величины.

    ПЛОСКАЯ строка = нулевой градиент: обучение по этому члену невозможно,
    сколько бы вес ни поднимали (06_pitfalls.md §A2).

    Требование к `make_ctx`: он обязан вернуть Ctx с тем же `dt`, иначе
    ставка в секунду посчитается в разных единицах — это ловится здесь же.

    Требование к `term.fn`: вклад ЗА ШАГ уже с учётом частоты события.
    Плата за событие, происходящее с частотой f, записывается как
    `плата * f * dt` — именно эта запись делает ошибку формы видимой.
    """
    if float(dt) <= 0:
        raise ValueError("dt обязан быть > 0")
    t = Table(
        title=f"свип члена {term.name!r} по оси {axis!r} (dt={dt:g} с, вес {term.weight:g})",
        columns=[axis, COL_RAW, COL_RATE],
    )
    for v in values:
        ctx = make_ctx(float(v))
        if abs(ctx.dt - float(dt)) > 1e-15:
            raise ValueError(
                f"make_ctx({v}) вернул Ctx с dt={ctx.dt}, а свип идёт при dt={dt}: "
                "ставка в секунду посчиталась бы в разных единицах"
            )
        t.add(**{axis: float(v), COL_RAW: term.raw(ctx), COL_RATE: term.value(ctx) / float(dt)})
    return t


def gradient_report(
    table: Table,
    tol: float = 0.02,
    *,
    higher_is_better: bool = True,
    value_column: str = COL_RATE,
) -> Verdict:
    """ВЕРДИКТ: 'нет градиента' | 'градиент есть' | 'градиент ОБРАТНЫЙ'.

    `tol` — относительный размах ставки по диапазону:
        span = (max - min) / max(|среднее|, 1e-12).
    Если span < tol, член физически не различает крайние точки оси, и
    поднимать вес бессмысленно: умножение нуля на константу — ноль.

    `higher_is_better` — в какую сторону мы ХОТИМ двигать ось. Если ставка на
    правом конце ниже, чем на левом, вердикт «ОБРАТНЫЙ»: член платит за то,
    чего мы не хотим.
    """
    vals = [float(v) for v in table.column(value_column)]
    if len(vals) < 2:
        raise ValueError("для вердикта нужно минимум 2 точки свипа")
    lo, hi = min(vals), max(vals)
    mean = sum(vals) / len(vals)
    span = (hi - lo) / max(abs(mean), 1e-12)
    axis_name = table.columns[0]
    axis_vals = table.column(axis_name)
    i_best = max(range(len(vals)), key=lambda i: vals[i])
    nums = {
        "размах": hi - lo,
        "относительный размах": span,
        "первая": vals[0],
        "последняя": vals[-1],
        "максимум": hi,
        f"аргмакс({axis_name})": float(axis_vals[i_best]),
    }
    if span < tol:
        return Verdict(
            NO_GRADIENT,
            ok=False,
            detail=(
                f"ставка почти не меняется на всём диапазоне {axis_name}: "
                f"{vals[0]:.4f} -> {vals[-1]:.4f} /с. Поднимать вес бесполезно — "
                f"вес умножает ноль на константу (06_pitfalls.md §A2)."
            ),
            numbers=nums,
        )
    grew = (vals[-1] - vals[0]) > 0
    if grew != bool(higher_is_better):
        return Verdict(
            REVERSED_GRADIENT,
            ok=False,
            detail=(
                f"ставка идёт против желаемого направления: {vals[0]:.4f} -> {vals[-1]:.4f} /с. "
                f"Член платит за то, чего мы не хотим."
            ),
            numbers=nums,
        )
    inner = 0 < i_best < len(vals) - 1
    detail = f"ставка меняется {vals[0]:.4f} -> {vals[-1]:.4f} /с"
    if inner:
        detail += (
            f"; внутренний максимум при {axis_name} = {axis_vals[i_best]} "
            f"({hi:.4f}/с) — это и есть рабочая точка члена"
        )
    if lo < 0.0 < hi:
        detail += "; есть СМЕНА ЗНАКА — плохое поведение становится чистым штрафом"
    return Verdict(HAS_GRADIENT, ok=True, detail=detail, numbers=nums)


# ---------------------------------------------------------------------------
# Синтетические траектории
# ---------------------------------------------------------------------------


def synthetic_rollout(
    pattern: Callable[[float], Dict[str, Any]],
    seconds: float,
    dt: float,
) -> Iterator[Ctx]:
    """Синтетическая траектория с ЗАДАННЫМ параметром.

    `pattern(t) -> dict` описывает состояние в момент t; функция выдаёт поток
    `Ctx`. Метрика, которая на трёх заведомо разных траекториях даёт ОДНО И ТО
    ЖЕ число, — сломана, и это видно за секунды (06_pitfalls.md §A1).

    Дисциплина замера: подбирайте dt так, чтобы период движения делился на
    него нацело. Иначе момент события (посадка стопы) плавает внутри шага, и
    сломанная метрика покажет мелкий НЕНУЛЕВОЙ шум — ровно тот шум, за который
    боевой r_stride собирал 21.9 награды/с, «то есть платил за АПЕРИОДИЧНОСТЬ».
    """
    if float(dt) <= 0 or float(seconds) <= 0:
        raise ValueError("seconds и dt обязаны быть > 0")
    n = int(round(float(seconds) / float(dt)))
    for k in range(n):
        t = k * float(dt)
        yield Ctx(float(dt), t, **pattern(t))


def periodic_gait(
    stride: float,
    cadence: float,
    duty: float = 0.6,
    jitter: float = 0.0,
) -> Callable[[float], Dict[str, Any]]:
    """Идеально периодическая походка одной ноги — эталон с известным ответом.

    Параметры
    ---------
    stride  : длина шага, м (расстояние между двумя последовательными
              точками постановки В МИРОВОЙ раме)
    cadence : число посадок этой ноги в секунду, Гц
    duty    : доля периода, которую нога стоит на земле
    jitter  : знакопеременное смещение точки постановки, м. jitter = 0 —
              строго периодическая походка; jitter > 0 — АПЕРИОДИЧНАЯ,
              на которой сломанная метрика «оживает».

    Скорость корпуса берётся из связи установившейся ходьбы: v = stride*cadence.
    Возвращает поля: body_x (положение корпуса, м), foot_x (положение стопы
    в МИРОВОЙ раме, м), contact (стоит ли нога на земле), stride_true, cadence.
    """
    v = float(stride) * float(cadence)
    period = 1.0 / float(cadence)

    def pattern(t: float) -> Dict[str, Any]:
        k = int(math.floor(t / period + 1e-12))
        phase = (t / period) - k
        off_k = jitter * (1.0 if k % 2 == 0 else -1.0)
        off_k1 = jitter * (1.0 if (k + 1) % 2 == 0 else -1.0)
        p0 = k * stride + off_k
        p1 = (k + 1) * stride + off_k1
        if phase < duty:
            foot = p0
            contact = True
        else:
            s = (phase - duty) / (1.0 - duty)
            foot = p0 + (p1 - p0) * s
            contact = False
        return {
            "body_x": v * t,
            "foot_x": foot,
            "contact": contact,
            "stride_true": float(stride),
            "cadence": float(cadence),
            "v": v,
        }

    return pattern


# ---------------------------------------------------------------------------
# Пассивная база
# ---------------------------------------------------------------------------


def _zero_action(space):
    """Нулевое (нейтральное) действие для пространства действий."""
    import gymnasium as gym

    if isinstance(space, gym.spaces.Box):
        return np.zeros(space.shape, dtype=space.dtype)
    if isinstance(space, gym.spaces.Discrete):
        return int(space.n // 2)
    raise TypeError(f"нулевое действие не определено для {type(space).__name__}")


def _env_dt(env, dt: Optional[float]) -> float:
    """Шаг среды в секундах: из аргумента, из `env.unwrapped.dt` или из render_fps."""
    if dt is not None:
        return float(dt)
    u = getattr(env, "unwrapped", env)
    for name in ("dt", "timestep", "step_dt"):
        v = getattr(u, name, None)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    fps = (getattr(env, "metadata", None) or {}).get("render_fps")
    if fps:
        return 1.0 / float(fps)
    print(
        "[dt] ВНИМАНИЕ: у среды нет ни .dt, ни render_fps — принят dt = 1.0 с. "
        "Все «в секунду» станут «за шаг». Задайте dt явно.",
        flush=True,
    )
    return 1.0


def null_policy_baseline(
    env_fn: Callable[[], Any],
    seconds: float,
    n: int = 4,
    *,
    dt: Optional[float] = None,
    action_fn: Optional[Callable[[Any, Any], Any]] = None,
    seed0: int = 0,
) -> Dict[str, Any]:
    """Прогон с action = 0. Возвращает {alive_s, alive_steps, return, terms, ...}.

    Политика, живущая МЕНЬШЕ этой базы, не управляет — она мешает
    (walk_env_r4.py:49-51: политика 0.17 с при пассивных 1.78 с).
    Это ОБЯЗАТЕЛЬНЫЙ замер до обучения: если нулевое действие даёт тот же
    результат, что и любой контроллер, значит контроллер не влияет вовсе
    (_null_test.py:3-4).

    `action_fn(obs, space) -> action` — расширение относительно боевого кода:
    той же функцией меряется случайная или эвристическая база (её использует
    probes.probe_action_scale).
    """
    env = env_fn()
    step_dt = _env_dt(env, dt)
    max_steps = max(1, int(round(float(seconds) / step_dt)))
    alive: List[int] = []
    rets: List[float] = []
    term_sum: Dict[str, float] = {}
    term_steps = 0
    finished = 0
    try:
        for ep in range(int(n)):
            obs, _ = env.reset(seed=seed0 + ep)
            total = 0.0
            k = 0
            for k in range(1, max_steps + 1):
                a = _zero_action(env.action_space) if action_fn is None else action_fn(obs, env.action_space)
                obs, r, terminated, truncated, info = env.step(a)
                total += float(r)
                terms = info.get("terms") if isinstance(info, dict) else None
                if isinstance(terms, dict):
                    for key, val in terms.items():
                        term_sum[key] = term_sum.get(key, 0.0) + float(val)
                    term_steps += 1
                if terminated or truncated:
                    finished += 1
                    break
            alive.append(k)
            rets.append(total)
    finally:
        env.close()

    terms_per_s = (
        {k: v / term_steps / step_dt for k, v in term_sum.items()} if term_steps else {}
    )
    return {
        "alive_s": float(np.mean(alive)) * step_dt,
        "alive_steps": float(np.mean(alive)),
        "alive_s_std": float(np.std(alive)) * step_dt,
        "return": float(np.mean(rets)),
        "return_std": float(np.std(rets)),
        "terms": terms_per_s,
        "dt": step_dt,
        "episodes": int(n),
        "terminated": finished,
        "max_steps": max_steps,
    }


# ---------------------------------------------------------------------------
# Достижимость порога
# ---------------------------------------------------------------------------


def reachability(
    term: Term,
    achievable: Callable[[Ctx], float],
    ctxs: Sequence[Ctx] = (),
) -> Verdict:
    """Порог члена против ФИЗИЧЕСКИ достижимого значения при данной команде.

    Недостижимый порог = постоянный штраф при ЛЮБОМ поведении = лазейка:
    политика начинает искать способ не регистрироваться. У платформы это
    породило хромоту (walk_env_r4.py:210-221): при 0.25 м/с и 2.3 Гц
    достижимый шаг 10.9 см, а порог стоял на 12 см.

    Отличие от эскиза API: сюда передаётся ещё и набор состояний `ctxs`, на
    которых считается достижимое значение — без состояний вопрос
    «достижим ли порог» не имеет смысла.
    """
    if term.threshold is None:
        raise ValueError(
            f"у члена {term.name!r} не задан threshold — проверять нечего. "
            "Если порог есть в формуле, вынесите его в Term.threshold."
        )
    if not ctxs:
        raise ValueError("нужен хотя бы один Ctx: достижимость считается на состояниях")
    vals = [float(achievable(c)) for c in ctxs]
    thr = float(term.threshold)
    lo, hi = min(vals), max(vals)
    nums = {"порог": thr, "достижимо max": hi, "достижимо min": lo, "запас": hi - thr}
    if hi < thr:
        return Verdict(
            "порог НЕДОСТИЖИМ",
            ok=False,
            detail=(
                f"порог {thr:.4g} выше максимума достижимого {hi:.4g} "
                f"({100.0 * hi / thr:.1f} % порога) — штраф платится при ЛЮБОМ поведении, "
                f"и политика будет искать не улучшение, а лазейку."
            ),
            numbers=nums,
        )
    if lo < thr:
        return Verdict(
            "порог достижим НЕ ВЕЗДЕ",
            ok=True,
            detail=(
                f"порог {thr:.4g} достижим при части команд (достижимое {lo:.4g}...{hi:.4g}). "
                f"Правильная форма — порог, ПРОПОРЦИОНАЛЬНЫЙ команде "
                f"(walk_env_r4.py:210-230), а не константа."
            ),
            numbers=nums,
        )
    return Verdict(
        "порог достижим",
        ok=True,
        detail=f"достижимое {lo:.4g}...{hi:.4g} против порога {thr:.4g}",
        numbers=nums,
    )


# ---------------------------------------------------------------------------
# Доли членов
# ---------------------------------------------------------------------------


def term_share_table(registry: RewardRegistry, dt: float, strangler: float = 0.40) -> Table:
    """Доля каждого члена в |сумме| за секунду. Член выше ~40 % — кандидат в душители.

    Числа платформы для калибровки глазомера (walk_env_r4.py:259-264, :330-332):
    член со ставкой -105.5/с против r_lin +84.5/с «задавил бы всё остальное»
    (полная награда падала с ~700 до 2.45/с); другой член «съедал 48 % награды
    заднего хода».
    """
    summ = registry.episode_summary()
    t = Table(
        title=f"доли членов награды ({registry.steps} шагов, {registry.seconds:.3f} с)",
        columns=["член", COL_RATE, "доля |суммы|", "знак", "ненулевых", "пометка"],
    )
    for name, st in sorted(summ.items(), key=lambda kv: -abs(kv[1]["per_sec"])):
        t.add(
            **{
                "член": name,
                COL_RATE: st["per_sec"],
                "доля |суммы|": st["share"],
                "знак": "+" if st["per_sec"] > 0 else ("-" if st["per_sec"] < 0 else "0"),
                "ненулевых": st["n_nonzero"],
                "пометка": "кандидат в душители" if st["share"] > strangler else "",
            }
        )
    return t


# ---------------------------------------------------------------------------
# САМОПРОВЕРКА
# ---------------------------------------------------------------------------


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError("САМОПРОВЕРКА ПРОВАЛЕНА: " + msg)


def _measure_stride(rollout: Iterable[Ctx], frame: str) -> List[float]:
    """Длина шага между посадками одной ноги в раме `frame` ('world' | 'body').

    'body' — ровно та формула, что стояла в боевой награде и в боевой пробе:
    `px = xpos - qpos[0]`, то есть положение стопы в СК корпуса
    (walk_env_r4.py:128-140).
    """
    out: List[float] = []
    prev: Optional[float] = None
    was_contact = True
    for ctx in rollout:
        contact = bool(ctx["contact"])
        if contact and not was_contact:            # передний фронт посадки
            p = ctx["foot_x"] if frame == "world" else ctx["foot_x"] - ctx["body_x"]
            if prev is not None:
                out.append(float(p - prev))
            prev = float(p)
        was_contact = contact
    return out


def _selftest() -> int:
    print("=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.diagnostics")
    print("=" * 78)

    DT = 0.02          # 50 Гц
    V_CMD = 0.25       # командная скорость, м/с — она ЗАДАНА и не зависит от шага
    W = 8.0            # вес члена, как в боевом коде до правки
    L_CAP = 0.30       # потолок платы
    L0, LMAX = 0.09, 0.40   # порог и потолок правильной формы

    # =====================================================================
    # 1. ОШИБКА A2: плата вида min(L/L_cap, 1)
    # =====================================================================
    print("\n1. ФОРМА ПЛАТЫ. Ставка за посадку при установившейся ходьбе (L*f = v)")
    print(f"   команда v = {V_CMD} м/с, вес W = {W}, потолок L_cap = {L_CAP} м, dt = {DT} с")

    def make_ctx(L: float) -> Ctx:
        return Ctx(DT, 0.0, stride=L, cadence=V_CMD / L, v=V_CMD)

    def pay_cap(ctx: Ctx) -> float:
        """Плата min(L/L_cap, 1) за КАЖДУЮ посадку, приведённая к одному шагу.
        Посадок в секунду 2f (две ноги), значит за шаг это 2*f*dt событий."""
        L = ctx["stride"]
        f = ctx["cadence"]
        return 2.0 * f * ctx.dt * min(L / L_CAP, 1.0)

    def pay_offset(ctx: Ctx) -> float:
        """Плата СМЕЩЕНИЕМ ОТ ПОРОГА: gain = min(L, lmax) - l0 (walk_env_r4.py:815)."""
        L = ctx["stride"]
        f = ctx["cadence"]
        return 2.0 * f * ctx.dt * (min(L, LMAX) - L0)

    t_cap8 = sweep_term(
        Term("r_stride_cap", pay_cap, weight=W, unit="м", why="оплата длины шага, форма min(L/L_cap,1)"),
        "L, м", [0.058, 0.10, 0.20, 0.30], make_ctx, DT,
    )
    print("\n" + str(t_cap8))
    v_cap8 = gradient_report(t_cap8)
    print(v_cap8)
    rates = t_cap8.column(COL_RATE)
    _check(max(rates) - min(rates) < 1e-12,
           f"ставка обязана быть ТОЖДЕСТВЕННО постоянной, получено {rates}")
    want_flat = 2.0 * W * V_CMD / L_CAP
    _check(abs(rates[0] - want_flat) < 1e-12,
           f"ставка {rates[0]}, а аналитика 2*W*v/L_cap = {want_flat}")
    _check(v_cap8.verdict == NO_GRADIENT, f"вердикт {v_cap8.verdict!r}, ожидался {NO_GRADIENT!r}")
    print(f"   аналитика: 2*W*v/L_cap = 2*{W}*{V_CMD}/{L_CAP} = {want_flat:.4f}/с при ЛЮБОЙ длине шага")

    # Подъём веса 8 -> 12: ровно та правка, что на платформе не дала ничего.
    t_cap12 = sweep_term(
        Term("r_stride_cap", pay_cap, weight=12.0, unit="м", why="то же, вес поднят 8 -> 12"),
        "L, м", [0.058, 0.10, 0.20, 0.30], make_ctx, DT,
    )
    r12 = t_cap12.column(COL_RATE)
    v_cap12 = gradient_report(t_cap12)
    print(f"\n   тот же член с весом 12: ставка {r12[0]:.4f}/с при L=0.058 и "
          f"{r12[-1]:.4f}/с при L=0.300 — вердикт: {v_cap12.verdict}")
    _check(max(r12) - min(r12) < 1e-12, "с весом 12 ставка вдруг перестала быть плоской")
    _check(v_cap12.verdict == NO_GRADIENT, "подъём веса не должен создавать градиент")
    _check(abs(r12[0] / rates[0] - 1.5) < 1e-12, "вес поднялся не в 1.5 раза")
    print("   вывод: вес умножил ноль на 1.5 и получил ноль (06_pitfalls.md §A2).")

    # За потолком градиент есть, но ОБРАТНЫЙ.
    t_cap_wide = sweep_term(
        Term("r_stride_cap", pay_cap, weight=W, why="та же форма, диапазон за потолок"),
        "L, м", [0.058, 0.10, 0.20, 0.30, 0.45], make_ctx, DT,
    )
    v_wide = gradient_report(t_cap_wide)
    print("\n" + str(t_cap_wide))
    print(v_wide)
    _check(v_wide.verdict == REVERSED_GRADIENT,
           f"за потолком вердикт {v_wide.verdict!r}, ожидался {REVERSED_GRADIENT!r}")

    # Правильная форма.
    t_fix = sweep_term(
        Term("r_stride_offset", pay_offset, weight=W, unit="м",
             why=f"плата смещением от порога l0={L0} м, потолок {LMAX} м", threshold=L0),
        "L, м", [0.058, 0.10, 0.20, 0.30, 0.40, 0.45], make_ctx, DT,
    )
    print("\n" + str(t_fix))
    v_fix = gradient_report(t_fix)
    print(v_fix)
    rf = t_fix.column(COL_RATE)
    _check(v_fix.verdict == HAS_GRADIENT, f"у правильной формы вердикт {v_fix.verdict!r}")
    _check(rf[0] < 0.0 < rf[3], "у правильной формы обязана быть смена знака на пороге")
    want_short = 2.0 * W * (V_CMD / 0.058) * (0.058 - L0)
    _check(abs(rf[0] - want_short) < 1e-9, f"ставка на коротком шаге {rf[0]}, аналитика {want_short}")
    print(f"   семенение L=0.058 м получает {rf[0]:.4f}/с — ЧИСТЫЙ ШТРАФ, а не «меньшая награда»")
    print(f"   (на платформе после той же правки походка 5.25 Гц / 0.058 м стала получать")
    print(f"    -14.0/с вместо прежних +22.8/с — _launch_r4j.ps1:9-11)")

    # =====================================================================
    # 2. ОШИБКА A1: метрика, тождественно равная нулю
    # =====================================================================
    print("\n2. МЕТРИКА. Длина шага в МИРОВОЙ раме против СК КОРПУСА")
    print("   синтетические походки с ЗАРАНЕЕ ИЗВЕСТНЫМ шагом, каденс 1.25 Гц,")
    print(f"   dt = {DT} с (период 0.8 с = ровно 40 шагов, событие не плавает)")
    tbl = Table(
        title="",
        columns=["шаг задан, м", "мир, м", "СК корпуса, м", "посадок", "скорость, м/с"],
    )
    body_vals = []
    for stride in (0.10, 0.30, 0.45):
        pat = periodic_gait(stride=stride, cadence=1.25)
        world = _measure_stride(synthetic_rollout(pat, seconds=8.0, dt=DT), "world")
        body = _measure_stride(synthetic_rollout(pat, seconds=8.0, dt=DT), "body")
        mw = float(np.mean(world))
        mb = float(np.mean(body))
        body_vals.append(mb)
        tbl.add(**{
            "шаг задан, м": stride, "мир, м": mw, "СК корпуса, м": mb,
            "посадок": len(world) + 1, "скорость, м/с": stride * 1.25,
        })
        _check(abs(mw - stride) < 1e-12, f"мировая метрика дала {mw}, а шаг задан {stride}")
        _check(abs(mb) < 1e-12, f"метрика в СК корпуса дала {mb}, а обязана дать тождественный 0")
    print("\n" + str(tbl))
    _check(max(body_vals) - min(body_vals) < 1e-12,
           "метрика в СК корпуса обязана НЕ РАЗЛИЧАТЬ три разные походки")
    print("   вывод: 0.0000 м во всех трёх — метрика в СК корпуса сломана")
    print("   (ровно этот замер в 06_pitfalls.md §A1: три прогона отчитывались числами,")
    print("    которых не существовало; та же формула стояла и в награде, и в пробе).")

    # А на АПЕРИОДИЧНОЙ походке сломанная метрика «оживает» — за это она и платила.
    pat_j = periodic_gait(stride=0.30, cadence=1.25, jitter=0.02)
    body_j = _measure_stride(synthetic_rollout(pat_j, seconds=8.0, dt=DT), "body")
    world_j = _measure_stride(synthetic_rollout(pat_j, seconds=8.0, dt=DT), "world")
    mbj = float(np.mean(np.abs(body_j)))
    mwj = float(np.mean(world_j))
    print(f"\n   апериодичная походка (дрожание точки постановки +-0.02 м, шаг тот же 0.30 м):")
    print(f"     метрика в СК корпуса: {mbj:.4f} м по модулю (было 0.0000)")
    print(f"     метрика в мире:       {mwj:.4f} м (шаг не изменился)")
    _check(mbj > 0.03, "сломанная метрика обязана реагировать на апериодичность")
    _check(abs(mwj - 0.30) < 1e-9, "мировая метрика не должна зависеть от дрожания")
    print("   вывод: сломанный член платил не за длину шага, а за АПЕРИОДИЧНОСТЬ.")

    # =====================================================================
    # 3. Пассивная база
    # =====================================================================
    print("\n3. ПАССИВНАЯ БАЗА: сколько живёт неуправляемая машина")
    import gymnasium as gym
    from gymnasium import spaces

    class _FallingEnv(gym.Env):
        """Неустойчивая точка: x'' = k*x + u. Аналог «робота, который валится».

        Аналитика при u = 0 и x0: x(t) = x0*cosh(sqrt(k)*t), эпизод кончается
        при |x| > 1. Значит время жизни = acosh(1/x0)/sqrt(k) — ответ известен
        заранее, и его можно сверить с замером.
        """

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
            fallen = abs(self.x) > 1.0
            terms = {"alive": 1.0, "effort": -0.01 * u * u}
            return (
                np.array([self.x, self.v], dtype=np.float32),
                1.0 - 0.01 * u * u,
                fallen,
                False,
                {"terms": terms},
            )

    base = null_policy_baseline(_FallingEnv, seconds=5.0, n=4)
    k, x0 = 25.0, 0.01
    analytic = math.acosh(1.0 / x0) / math.sqrt(k)
    print(f"   нулевое действие: живёт {base['alive_s']:.3f} с, награда {base['return']:.2f}")
    print(f"   аналитика (непрерывная): acosh(1/{x0})/sqrt({k}) = {analytic:.3f} с")
    print(f"   вклады членов, /с: " + ", ".join(f"{a}={b:.2f}" for a, b in base['terms'].items()))
    _check(abs(base["alive_s"] - analytic) < 0.05,
           f"замер {base['alive_s']:.3f} с разошёлся с аналитикой {analytic:.3f} с")
    _check(abs(base["terms"]["alive"] - 100.0) < 1e-9,
           "ставка члена alive обязана быть 1/dt = 100/с")

    rng = np.random.default_rng(0)
    loud = null_policy_baseline(
        _FallingEnv, seconds=5.0, n=4,
        action_fn=lambda obs, sp: rng.uniform(-1.0, 1.0, sp.shape).astype(sp.dtype),
    )
    print(f"   случайная разведка амплитуды 1.0: живёт {loud['alive_s']:.3f} с")
    print(f"   отношение: разведка живёт в {base['alive_s'] / loud['alive_s']:.2f} раза МЕНЬШЕ пассивной базы")
    _check(loud["alive_s"] < base["alive_s"],
           "разведка обязана убивать машину быстрее, чем нулевое действие")
    print("   (на платформе то же отношение: политика 0.17 с при пассивных 1.78 с —")
    print("    walk_env_r4.py:49-51; лечится не куррикулумом, а тихим стартом log_std)")

    # =====================================================================
    # 4. Достижимость порога
    # =====================================================================
    print("\n4. ДОСТИЖИМОСТЬ ПОРОГА: константный порог против физики")
    limp_term = Term(
        "p_short_step", lambda c: 0.0, weight=-1.0, unit="м",
        why="штраф за шаг короче 12 см", threshold=0.12,
    )
    slow = [Ctx(DT, 0.0, v=0.25, cadence=2.3)]
    fast = [Ctx(DT, 0.0, v=0.60, cadence=1.7)]
    ach = lambda c: c["v"] / c["cadence"]
    v_slow = reachability(limp_term, ach, slow)
    v_fast = reachability(limp_term, ach, fast)
    print(f"   при v=0.25 м/с и каденсе 2.3 Гц достижимый шаг = {ach(slow[0])*100:.1f} см")
    print("   " + str(v_slow).replace("\n", "\n   "))
    print(f"   при v=0.60 м/с и каденсе 1.7 Гц достижимый шаг = {ach(fast[0])*100:.1f} см")
    print("   " + str(v_fast).replace("\n", "\n   "))
    _check(not v_slow.ok, "недостижимый порог не пойман")
    _check(v_fast.ok, "достижимый порог ошибочно объявлен недостижимым")
    _check(abs(ach(slow[0]) - 0.1087) < 5e-4,
           "достижимый шаг разошёлся с числом отчёта (10.9 см, walk_env_r4.py:210-221)")
    print("   (замер последствия на платформе: назад 0.25 — шаг Л/П 16.0/11.4 см,")
    print("    потеряно контактов 20 %/5 %; назад 0.60 — 34.8/35.0 см, хромоты НЕТ)")

    # =====================================================================
    # 5. Доли членов
    # =====================================================================
    print("\n5. ДОЛИ ЧЛЕНОВ")
    reg = RewardRegistry()
    reg.add(Term("r_lin", lambda c: 84.5 * DT, why="слежение"))
    reg.add(Term("p_new", lambda c: -105.5 * DT, why="новый штраф, вес 0.5"))
    reg.add(Term("r_air", lambda c: 5.0 * DT, why="время полёта"))
    for _ in range(25):
        reg(Ctx(DT))
    share = term_share_table(reg, DT)
    print(str(share))
    marks = share.column("пометка")
    _check(marks[0] == "кандидат в душители", "душитель не помечен в таблице долей")
    _check(marks[-1] == "", "мелкий член ошибочно помечен")

    print("\n" + "=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.diagnostics ПРОЙДЕНА")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(_selftest())
