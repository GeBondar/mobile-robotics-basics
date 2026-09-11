"""rl_toolkit.curriculum — рампы сложности и колбэк, который рассылает их в среды.

ЗАЧЕМ ЭТО НУЖНО
    Куррикулум — это расписание: «первые N шагов задача лёгкая, потом плавно
    тяжелеет». Расписание считается от счётчика обучения, и весь вопрос в том,
    ОТ КАКОГО НУЛЯ этот счётчик отсчитывается.

ЧТО ЭТО ПРЕДОТВРАЩАЕТ (числа — из разбора боевой платформы legged_robots)

 1. «Абсолютный счётчик при resume»  (отчёт 06_pitfalls.md §A11,
    первоисточник sim/train_walk_r4.py:190-195).
    `self.num_timesteps` у SB3 — АБСОЛЮТНЫЙ счётчик модели: при
    `model.learn(..., reset_num_timesteps=False)` он продолжается, а не
    обнуляется. Проверено по исходникам SB3 2.4.1,
    `common/base_class.py:411-416`:

        if reset_num_timesteps:
            self.num_timesteps = 0
            self._episode_num = 0
        else:
            # Make sure training timesteps are ahead of the internal counter
            total_timesteps += self.num_timesteps

    Цитата из боевого кода: «30.08 на этом сгорели ТРИ ПРОГОНА: при
    продолжении со 163.5M и --terrain-hold 2000000 выходило
    lvl = min(1, 161.5M/18M) = 1.0 с первого же шага, то есть машину сразу
    бросало на максимальный рельеф.»
    Здесь `hold` документирован как АБСОЛЮТНЫЙ шаг, а `CurriculumCallback`
    печатает стартовые значения всех рамп в первый же вызов — одна строка,
    которая стоила трёх суток машинного времени.
    Дополнительно: `explain()` печатает всю таблицу расписания ДО старта.

 2. «Единицы колбэков SB3»  (отчёт 06_pitfalls.md §A10).
    `self.n_calls` — это ЧИСЛО ВЫЗОВОВ `env.step` векторной среды, а не
    env-шагов. Проверено по исходникам SB3 2.4.1, `common/callbacks.py:44-46`:
        self.n_calls = 0        # Number of time the callback was called
        self.num_timesteps = 0  # n_envs * n times env.step() was called
    Поэтому расписание куррикулума ведётся по `num_timesteps`, а НЕ по
    `n_calls`: при 12 средах они расходятся ровно в 12 раз.

 3. «Что синхронизировать в eval, а что нет»
    (05_platform_code.md §1.2, sim/train_walk_r4.py:184-188).
    Гравитационное послабление в eval-среду НЕ дублируется — иначе метрика
    перестаёт быть честной. Рельеф дублируется обязательно, «иначе метрика
    перестанет отвечать на вопрос, а ходит ли он по камням». Правило:
    то, что делает задачу ЛЕГЧЕ, в eval не синхронизируется;
    то, что меняет САМУ задачу, — синхронизируется.
    `sync_to_eval` заставляет автора назвать этот выбор явно, а не забыть о нём.

 4. «Куррикулум сам по себе не лечит разведку» (05_platform_code.md §1.2 п.5).
    A/B на платформе: даже на зафиксированной 0.35g политика жила 0.17 с при
    пассивных 1.78 с. Замкнул бутстрап только тихий старт log_std_init = -2.3.
    Куррикулум и разведка — две разные болезни; см. probes.probe_action_scale.

ПОРЯДОК КОЛБЭКОВ
    `CurriculumCallback` обязан стоять ПЕРЕД eval-колбэком в списке: к моменту
    оценки все среды (и обучающие, и eval-копия) должны уже получить свежие
    значения. См. checkpointing.setup_callbacks — там порядок зафиксирован.

ЧТО ПРИМЕНЯЕТСЯ НЕ СРАЗУ
    Изменения, требующие пересборки эпизода (рельеф, масса, геометрия),
    среда обязана применять в `reset()`, а не мгновенно: «менять поле под
    стоящей на нём машиной нельзя — её выбросит» (sim/walk_env_r4.py:596-598).
    Колбэк лишь сообщает значение; момент применения — ответственность среды.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from stable_baselines3.common.callbacks import BaseCallback

__all__ = [
    "Ramp",
    "CurriculumCallback",
    "linear",
    "staircase",
    "explain",
]


# ---------------------------------------------------------------------------
# Рампа
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ramp:
    """Расписание одной величины по АБСОЛЮТНОМУ счётчику env-шагов.

    Параметры
    ---------
    hold : int
        Абсолютный номер env-шага, ДО которого держится `lo`.
        Это НЕ «через сколько шагов после старта запуска»: при resume
        счётчик модели продолжается (SB3 2.4.1, base_class.py:411-416).
    ramp : int
        Длительность подъёма `lo` -> `hi` в env-шагах. Должна быть > 0.
    lo, hi : float
        Границы величины. `hi` не обязан быть больше `lo`: убывающая рампа
        (например, послабление, которое снимают) задаётся как lo=1.0, hi=0.0.
    stairs : tuple[(шаг, значение), ...] | None
        Если задано — рампа ступенчатая (см. `staircase`), а `hold`/`ramp`
        игнорируются при вычислении значения.

    Примеры (проверены в самопроверке модуля)
    -----------------------------------------
    >>> Ramp(hold=2_000_000, ramp=18_000_000).value(0)
    0.0
    >>> Ramp(hold=2_000_000, ramp=18_000_000).value(11_000_000)
    0.5
    >>> Ramp(hold=2_000_000, ramp=18_000_000).value(163_500_000)   # resume!
    1.0
    Последняя строка — та самая, что сожгла три прогона: рампа, задуманная как
    «первые 2 млн шагов ровный пол», при старте со 163.5M выдаёт максимальную
    сложность с первого же шага.
    """

    hold: int
    ramp: int
    lo: float = 0.0
    hi: float = 1.0
    stairs: Optional[Tuple[Tuple[int, float], ...]] = None

    def __post_init__(self) -> None:
        if self.stairs is None:
            if int(self.ramp) <= 0:
                raise ValueError("ramp обязан быть > 0 env-шагов (иначе деление на ноль)")
            if int(self.hold) < 0:
                raise ValueError("hold обязан быть >= 0 (это АБСОЛЮТНЫЙ номер шага)")
        else:
            th = [int(s[0]) for s in self.stairs]
            if th != sorted(th):
                raise ValueError("ступени staircase обязаны идти по возрастанию шага")

    # -- вычисление -------------------------------------------------------
    def value(self, timesteps: int) -> float:
        """Значение рампы на АБСОЛЮТНОМ шаге `timesteps`."""
        t = float(timesteps)
        if self.stairs is not None:
            v = float(self.lo)
            for thr, val in self.stairs:
                if t >= float(thr):
                    v = float(val)
            return v
        x = max(0.0, t - float(self.hold)) / float(self.ramp)
        x = min(1.0, x)
        return float(self.lo) + (float(self.hi) - float(self.lo)) * x

    # -- печать -----------------------------------------------------------
    def describe(self) -> str:
        """Однострочное человекочитаемое описание расписания."""
        if self.stairs is not None:
            body = ", ".join(f"{int(t)}->{v:g}" for t, v in self.stairs)
            return f"ступени[{body}] (до первой ступени {self.lo:g})"
        return (
            f"линейно {self.lo:g}->{self.hi:g}, "
            f"держим {self.lo:g} до абс. шага {int(self.hold)}, "
            f"подъём за {int(self.ramp)} шагов "
            f"(конец подъёма на абс. шаге {int(self.hold) + int(self.ramp)})"
        )


def linear(hold: int, ramp: int, lo: float = 0.0, hi: float = 1.0) -> Ramp:
    """Линейная рампа. `hold` — АБСОЛЮТНЫЙ номер env-шага, а не смещение."""
    return Ramp(hold=int(hold), ramp=int(ramp), lo=float(lo), hi=float(hi))


def staircase(steps: Sequence[Tuple[int, float]], lo: Optional[float] = None) -> Ramp:
    """Ступенчатая рампа: [(абс. шаг, значение), ...].

    До первой ступени возвращается `lo` (по умолчанию — значение первой
    ступени, то есть ступень действует «с самого начала»).
    Ступени нужны там, где промежуточные значения физически бессмысленны
    (номер уровня рельефа, число препятствий, индекс сценария).
    """
    st = tuple((int(t), float(v)) for t, v in steps)
    if not st:
        raise ValueError("staircase: нужна хотя бы одна ступень")
    base = float(st[0][1]) if lo is None else float(lo)
    return Ramp(hold=st[0][0], ramp=1, lo=base, hi=float(st[-1][1]), stairs=st)


# ---------------------------------------------------------------------------
# Колбэк
# ---------------------------------------------------------------------------


class CurriculumCallback(BaseCallback):
    """Ведёт несколько рамп сразу и рассылает их значения в среды.

    Параметры
    ---------
    train_env : VecEnv
        Обучающая векторная среда. Значения рассылаются через
        `env_method(имя, значение)`, то есть каждое имя рампы — это имя
        МЕТОДА среды (`set_cmd_scale`, `set_gravity_scale`, ...).
    eval_env : VecEnv | None
        Оценочная среда. В неё уходят ТОЛЬКО рампы из `sync_to_eval`.
    schedule : dict[str, Ramp]
        {имя метода среды: рампа}.
    sync_to_eval : set[str]
        Какие рампы дублировать в eval. Правило платформы: то, что делает
        задачу легче (гравитация, ослабленный ветер, сокращённая дистанция),
        НЕ синхронизируется — иначе метрика перестаёт быть честной; то, что
        меняет саму задачу (рельеф, диапазон команд), синхронизируется
        обязательно (sim/train_walk_r4.py:184-188).
    min_delta : float
        Значение рассылается только когда изменилось больше чем на `min_delta`
        (по умолчанию 0.0 — то есть при любом изменении). Отличие от боевого
        кода, где `env_method` звался КАЖДЫЙ шаг: у `SubprocVecEnv` это
        межпроцессный вызов на каждый шаг обучения. Точность при min_delta=0
        не страдает: рассылка происходит на каждом шаге, где значение реально
        поменялось.

    Единицы
    -------
    Расписание считается по `self.num_timesteps` (env-шаги, абсолютный
    счётчик), НЕ по `self.n_calls` (вызовы env.step). См. шапку модуля.
    """

    def __init__(
        self,
        train_env,
        eval_env=None,
        *,
        schedule: Dict[str, Ramp],
        sync_to_eval: Iterable[str] = frozenset(),
        min_delta: float = 0.0,
        verbose: int = 0,
    ) -> None:
        super().__init__(verbose)
        if not schedule:
            raise ValueError("schedule пуст: колбэк без рамп не нужен")
        self.train_env = train_env
        self.eval_env = eval_env
        self.schedule: Dict[str, Ramp] = dict(schedule)
        self.sync_to_eval = frozenset(sync_to_eval)
        self.min_delta = float(min_delta)
        unknown = self.sync_to_eval - set(self.schedule)
        if unknown:
            raise ValueError(
                f"sync_to_eval ссылается на рампы, которых нет в schedule: {sorted(unknown)}"
            )
        self._last: Dict[str, float] = {}
        self._announced = False

    # -- служебное --------------------------------------------------------
    def _dispatch(self, name: str, value: float) -> None:
        self.train_env.env_method(name, value)
        if self.eval_env is not None and name in self.sync_to_eval:
            self.eval_env.env_method(name, value)
        self._last[name] = value

    def _announce(self, t: int) -> None:
        """Печать стартовых значений — одна строка на рампу.

        Ровно эта распечатка отличает «расписание задумано» от «расписание
        исполняется»: при resume она сразу показывает, что рампа уже на
        максимуме (06_pitfalls.md §A11).
        """
        print(f"[куррикулум] старт на абсолютном шаге {int(t)}", flush=True)
        for name, ramp in self.schedule.items():
            tag = "-> eval ТОЖЕ" if name in self.sync_to_eval else "-> eval НЕТ (честная метрика)"
            print(
                f"[куррикулум]   {name:<20} = {ramp.value(t):.4f}   {tag}   |  {ramp.describe()}",
                flush=True,
            )

    # -- API колбэка ------------------------------------------------------
    def _on_step(self) -> bool:
        t = int(self.num_timesteps)
        if not self._announced:
            self._announce(t)
            self._announced = True
            for name, ramp in self.schedule.items():
                self._dispatch(name, ramp.value(t))
            self._record()
            return True
        for name, ramp in self.schedule.items():
            v = ramp.value(t)
            prev = self._last.get(name)
            if prev is None or abs(v - prev) > self.min_delta:
                self._dispatch(name, v)
        self._record()
        return True

    def _record(self) -> None:
        """Пишет текущие значения рамп в TensorBoard (`curr/<имя>`).

        В боевой платформе значения рамп не логировались вообще — именно
        поэтому ошибка с --terrain-hold прожила три прогона
        (05_platform_code.md §7).
        """
        logger = getattr(getattr(self, "model", None), "logger", None)
        if logger is None:
            return
        for name, v in self._last.items():
            logger.record(f"curr/{name}", float(v))

    def current(self) -> Dict[str, float]:
        """Последние разосланные значения рамп (для логов и отчётов)."""
        return dict(self._last)


# ---------------------------------------------------------------------------
# Печать расписания ДО старта
# ---------------------------------------------------------------------------


def explain(
    schedule: Dict[str, Ramp],
    timesteps: int,
    total: int,
    rows: int = 11,
) -> str:
    """Таблица «абсолютный шаг -> значение каждой рампы» ДО старта обучения.

    Параметры
    ---------
    timesteps : int
        Абсолютный счётчик модели НА МОМЕНТ старта (0 для нового прогона,
        `model.num_timesteps` при resume).
    total : int
        Сколько env-шагов планируется обучать в этом запуске.

    Эта распечатка ловит ошибку §A11 за секунду: если первая строка таблицы
    уже показывает максимум, расписание при resume бессмысленно.
    """
    if rows < 2:
        raise ValueError("rows >= 2")
    names = list(schedule)
    t0, t1 = int(timesteps), int(timesteps) + int(total)
    head = f"{'абс. шаг':>14} | " + " | ".join(f"{n:>12}" for n in names)
    lines: List[str] = []
    lines.append(f"расписание куррикулума: старт {t0}, конец {t1} (env-шаги)")
    for n in names:
        lines.append(f"  {n:<20} {schedule[n].describe()}")
    lines.append("")
    lines.append(head)
    lines.append("-" * len(head))
    for i in range(rows):
        t = t0 + round((t1 - t0) * i / (rows - 1))
        cells = " | ".join(f"{schedule[n].value(t):12.4f}" for n in names)
        lines.append(f"{t:>14} | {cells}")
    flat = [n for n in names if abs(schedule[n].value(t0) - schedule[n].value(t1)) < 1e-12]
    if flat:
        lines.append("")
        lines.append(
            "ВНИМАНИЕ: за весь запуск НЕ МЕНЯЮТСЯ рампы: "
            + ", ".join(flat)
            + " — расписание либо уже отработало (resume!), либо задано в неверных единицах."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# САМОПРОВЕРКА
# ---------------------------------------------------------------------------


class _FakeVecEnv:
    """Заглушка векторной среды: запоминает все вызовы env_method."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.calls: List[Tuple[str, float]] = []

    def env_method(self, name: str, value: float):
        self.calls.append((name, float(value)))
        return [None]


class _FakeLogger:
    def __init__(self) -> None:
        self.records: Dict[str, float] = {}

    def record(self, key: str, value) -> None:
        self.records[key] = value


class _FakeModel:
    """Минимальная замена модели SB3: колбэку нужны num_timesteps и logger."""

    def __init__(self, num_timesteps: int = 0) -> None:
        self.num_timesteps = int(num_timesteps)
        self.logger = _FakeLogger()

    def get_env(self):
        return None


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError("САМОПРОВЕРКА ПРОВАЛЕНА: " + msg)


def _selftest() -> int:
    print("=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.curriculum")
    print("=" * 78)

    # --- 1. Линейная рампа: ответы известны заранее ----------------------
    r = linear(hold=2_000_000, ramp=18_000_000, lo=0.0, hi=1.0)
    cases = [
        (0, 0.0),
        (2_000_000, 0.0),
        (11_000_000, 0.5),          # 2M + 9M = половина рампы
        (20_000_000, 1.0),
        (163_500_000, 1.0),         # resume — та самая ошибка §A11
    ]
    print("\n1. Линейная рампа (hold=2 000 000, ramp=18 000 000, 0 -> 1)")
    print(f"   {'шаг':>14} | {'значение':>9} | {'ожидалось':>9}")
    for t, want in cases:
        got = r.value(t)
        print(f"   {t:>14} | {got:9.4f} | {want:9.4f}")
        _check(abs(got - want) < 1e-12, f"Ramp.value({t}) = {got}, ожидалось {want}")
    print("   вывод: при resume со 163 500 000 рампа выдаёт 1.0000 с ПЕРВОГО шага —")
    print("          ровно так сгорели три прогона (06_pitfalls.md §A11).")

    # --- 2. Убывающая рампа и ступени ------------------------------------
    down = linear(hold=0, ramp=1_000, lo=1.0, hi=0.0)
    _check(abs(down.value(0) - 1.0) < 1e-12, "убывающая рампа в нуле")
    _check(abs(down.value(500) - 0.5) < 1e-12, "убывающая рампа в середине")
    _check(abs(down.value(10_000) - 0.0) < 1e-12, "убывающая рампа на хвосте")

    st = staircase([(0, 0.0), (1_000, 1.0), (5_000, 2.0)])
    print("\n2. Ступенчатая рампа [(0,0), (1000,1), (5000,2)]")
    for t, want in [(0, 0.0), (999, 0.0), (1_000, 1.0), (4_999, 1.0), (5_000, 2.0), (9_9999, 2.0)]:
        got = st.value(t)
        print(f"   шаг {t:>7} -> {got:.2f} (ожидалось {want:.2f})")
        _check(abs(got - want) < 1e-12, f"staircase.value({t}) = {got}, ожидалось {want}")

    try:
        staircase([(1_000, 1.0), (0, 0.0)])
    except ValueError:
        pass
    else:
        raise AssertionError("САМОПРОВЕРКА ПРОВАЛЕНА: staircase принял ступени не по возрастанию")

    try:
        Ramp(hold=0, ramp=0)
    except ValueError:
        pass
    else:
        raise AssertionError("САМОПРОВЕРКА ПРОВАЛЕНА: Ramp принял ramp=0")

    # --- 3. Колбэк: что уходит в train, а что в eval ----------------------
    print("\n3. Колбэк: правило синхронизации с eval")
    train = _FakeVecEnv("train")
    ev = _FakeVecEnv("eval")
    cb = CurriculumCallback(
        train,
        ev,
        schedule={
            "set_cmd_scale": linear(hold=0, ramp=1_000, lo=0.0, hi=1.0),
            "set_gravity_scale": linear(hold=0, ramp=1_000, lo=0.35, hi=1.0),
        },
        sync_to_eval={"set_cmd_scale"},   # гравитация в eval НЕ уходит
    )
    model = _FakeModel(num_timesteps=0)
    cb.init_callback(model)
    for k in range(6):
        model.num_timesteps = k * 200          # 0, 200, ... 1000
        cb.num_timesteps = model.num_timesteps
        cb.n_calls += 1
        cb._on_step()

    train_names = {n for n, _ in train.calls}
    eval_names = {n for n, _ in ev.calls}
    print(f"   в train ушли рампы: {sorted(train_names)}")
    print(f"   в eval  ушли рампы: {sorted(eval_names)}")
    _check(train_names == {"set_cmd_scale", "set_gravity_scale"}, "train получил не все рампы")
    _check(eval_names == {"set_cmd_scale"}, "в eval протекла несинхронизируемая рампа")

    cur = cb.current()
    print(f"   текущие значения: {dict((k, round(v, 4)) for k, v in cur.items())}")
    _check(abs(cur["set_cmd_scale"] - 1.0) < 1e-12, "cmd_scale не дошёл до 1.0")
    _check(abs(cur["set_gravity_scale"] - 1.0) < 1e-12, "gravity_scale не дошёл до 1.0")
    _check(
        model.logger.records.get("curr/set_cmd_scale") is not None,
        "значения рамп не попали в logger (это и есть пробел платформы, §7)",
    )

    # рассылка только при изменении: 6 вызовов * 2 рампы = 12 максимум
    _check(len(train.calls) <= 12, "рассылка чаще, чем менялось значение")
    print(f"   вызовов env_method в train: {len(train.calls)} при 6 шагах и 2 рампах")

    # --- 4. sync_to_eval с опечаткой должен падать -----------------------
    try:
        CurriculumCallback(train, ev, schedule={"a": linear(0, 10)}, sync_to_eval={"b"})
    except ValueError:
        pass
    else:
        raise AssertionError("САМОПРОВЕРКА ПРОВАЛЕНА: sync_to_eval с опечаткой не пойман")

    # --- 5. explain: ловит ошибку resume ---------------------------------
    print("\n4. explain() для НОВОГО прогона (старт 0, 30 млн шагов)")
    good = explain(
        {"terrain": linear(hold=2_000_000, ramp=18_000_000)},
        timesteps=0,
        total=30_000_000,
        rows=6,
    )
    print("\n".join("   " + s for s in good.splitlines()))
    _check("ВНИМАНИЕ" not in good, "explain ругается на исправное расписание")

    print("\n5. explain() при RESUME со 163 500 000 — то же расписание")
    bad = explain(
        {"terrain": linear(hold=2_000_000, ramp=18_000_000)},
        timesteps=163_500_000,
        total=30_000_000,
        rows=6,
    )
    print("\n".join("   " + s for s in bad.splitlines()))
    _check("ВНИМАНИЕ" in bad, "explain НЕ поймал мёртвое расписание при resume")

    print("\n" + "=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.curriculum ПРОЙДЕНА")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(_selftest())
