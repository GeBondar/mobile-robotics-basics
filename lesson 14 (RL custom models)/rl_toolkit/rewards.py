"""rl_toolkit.rewards — реестр членов награды с раздельным учётом вклада.

ЗАЧЕМ ЭТО НУЖНО
    Монолитная награда («сложил всё в одну строку и вернул число») не даёт
    ответить на единственный вопрос, который нужен при отладке: КТО СКОЛЬКО
    ПЛАТИТ. Реестр хранит члены по именам, возвращает их вклады наружу
    (`info["terms"]`) и умеет считать вклад В НАГРАДЕ ЗА СЕКУНДУ.

ПОЧЕМУ ИМЕННО «ЗА СЕКУНДУ», А НЕ «ЗА ШАГ»
    Веса калибруются в единицах «награда/с»: только так сравнимы члены,
    начисляемые на каждом шаге, и члены, начисляемые по событию (посадка
    стопы, пересечение порога). Все замеры платформы сделаны в этих единицах.

ЧТО ЭТО ПРЕДОТВРАЩАЕТ (числа — из разбора платформы legged_robots)

 1. «Один член душит остальные, и это видно только в /с»
    (05_platform_code.md §3.1, sim/walk_env_r4.py:259-264):
    «Вес подобран ЗАМЕРОМ, а не на глаз: при 0.5 член давал -105.5/с против
    r_lin +84.5/с и задавил бы всё остальное (полная награда падала с ~700
    до 2.45/с). При 0.15 это ~32/с.»
    И там же (walk_env_r4.py:330-332): «при 2.0 новый блок съедал 48 %
    награды заднего хода».
    `report()` печатает долю каждого члена от |суммы|; член выше ~40 % —
    кандидат в душители. Этот случай воспроизведён в самопроверке модуля
    один в один по ставкам -105.5/с и +84.5/с.

 2. «Член платит не за то, чем назван» (06_pitfalls.md §A1,
    walk_env_r4.py:128-140): r_stride мерил смещение стопы в СК КОРПУСА и
    для ЛЮБОЙ периодической походки давал тождественный ноль (проверено на
    синтетических походках 0.10 / 0.30 / 0.45 м — метрика 0.0000 м во всех
    трёх), а живая политика собирала по нему 21.9 награды/с, то есть он
    платил за АПЕРИОДИЧНОСТЬ. Поле `Term.why` заставляет автора написать,
    ЗА ЧТО платит член, а `diagnostics.sweep_term` — доказать это замером.

 3. «Аттрактор “стоять”» (06_pitfalls.md §A4, walk_env_r4.py:682-696):
    абсолютное ядро exp(-8*err^2) при cmd 0.4 платит неподвижной машине
    27.8 % награды слежения; относительное ядро с sigma = max(0.35*|cmd|, 0.07)
    платит стоя 1.7 % при ЛЮБОЙ команде. Проверять это надо АРИФМЕТИКОЙ до
    запуска: `RewardRegistry` считается на любом синтетическом Ctx, в том
    числе на «агенте, который ничего не делает».

 4. «Гейт качества» (walk_env_r4.py:820, :872): `r_stride` и `r_air`
    умножаются на качество слежения, «без гейта безусловная оплата шагов
    вырастила маршировку на месте». Отсюда поле `Term.gate`.

 5. Пробел боевой платформы, который здесь закрыт (05_platform_code.md §7):
    среда возвращала `info["terms"]`, но в TensorBoard вклады НЕ писались —
    в train_walk_r4.py нет ни одного `self.logger.record`, и все калибровки
    весов («-105.5/с против +84.5/с», «48 % награды заднего хода») делались
    отдельными офлайн-прогонами задним числом. `RewardLogCallback`
    превращает калибровку весов из археологии в наблюдение.

ДОГОВОРЁННОСТЬ ОБ ЕДИНИЦАХ
    `Term.fn(ctx)` возвращает вклад ЗА ШАГ в единицах награды (уже с учётом
    того, что событие может произойти не на каждом шаге). Ставка в секунду
    получается делением на `dt`. Член, начисляемый по событию с частотой f,
    обязан быть записан как `плата * f * dt` — именно эта запись делает
    видимой ошибку формы (см. diagnostics и 06_pitfalls.md §A2).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from stable_baselines3.common.callbacks import BaseCallback

__all__ = ["Ctx", "Term", "RewardRegistry", "RewardLogCallback", "report"]


# ---------------------------------------------------------------------------
# Снимок состояния
# ---------------------------------------------------------------------------


class Ctx:
    """Снимок состояния среды на одном шаге — вход для членов награды.

    Зачем отдельный объект, а не `self` среды: член награды, который лезет в
    `self.data`, невозможно проверить на синтетике. Ctx делает члены чистыми
    функциями, и тогда `diagnostics.sweep_term` может подсунуть им любое
    состояние с ЗАРАНЕЕ ИЗВЕСТНЫМ ответом.

    Поля
    ----
    dt : float   шаг среды в секундах (для перевода вклада в награду/с)
    t  : float   время от начала эпизода, с
    остальное — произвольные именованные величины: ctx["speed"], ctx.get("cmd")
    """

    __slots__ = ("dt", "t", "v")

    def __init__(self, dt: float, t: float = 0.0, **fields: Any) -> None:
        if float(dt) <= 0.0:
            raise ValueError("dt обязан быть > 0: без него нет единиц награда/с")
        self.dt = float(dt)
        self.t = float(t)
        self.v: Dict[str, Any] = dict(fields)

    def __getitem__(self, key: str) -> Any:
        try:
            return self.v[key]
        except KeyError:
            raise KeyError(
                f"в Ctx нет поля {key!r}; есть: {sorted(self.v)}"
            ) from None

    def get(self, key: str, default: Any = None) -> Any:
        return self.v.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.v

    def with_(self, **fields: Any) -> "Ctx":
        """Копия снимка с изменёнными полями (удобно для свипов)."""
        d = dict(self.v)
        d.update(fields)
        return Ctx(self.dt, self.t, **d)

    def __repr__(self) -> str:
        body = ", ".join(f"{k}={v!r}" for k, v in sorted(self.v.items()))
        return f"Ctx(dt={self.dt}, t={self.t}, {body})"


# ---------------------------------------------------------------------------
# Член награды
# ---------------------------------------------------------------------------


@dataclass
class Term:
    """Один именованный член награды.

    Поля
    ----
    name   : имя (пойдёт в info["terms"], в TensorBoard и в отчёты)
    fn     : Ctx -> вклад ЗА ШАГ в «сырых» единицах члена (без веса)
    weight : вес. Калибруется ЗАМЕРОМ в награде/с, а не на глаз
    unit   : что мерит подынтегральная величина ("м", "рад/с", "доля")
    why    : ЗАЧЕМ член существует. Обязателен по духу курса: член, для
             которого нельзя написать эту строку, не нужен
    gate   : Ctx -> множитель качества (0..1). Отделяет «сделал много» от
             «сделал правильно» (walk_env_r4.py:820 — без гейта безусловная
             оплата шагов вырастила маршировку на месте)
    threshold : физический порог ВНУТРИ члена, если он есть. Нужен
             `diagnostics.reachability`, чтобы проверить: достижим ли он
             вообще при текущей команде. Недостижимый порог = постоянный
             штраф = лазейка (walk_env_r4.py:210-221)
    """

    name: str
    fn: Callable[[Ctx], float]
    weight: float = 1.0
    unit: str = ""
    why: str = ""
    gate: Optional[Callable[[Ctx], float]] = None
    threshold: Optional[float] = None

    def raw(self, ctx: Ctx) -> float:
        """Значение подынтегральной величины БЕЗ веса и гейта."""
        return float(self.fn(ctx))

    def value(self, ctx: Ctx) -> float:
        """Вклад в награду за шаг: weight * fn(ctx) * gate(ctx)."""
        g = 1.0 if self.gate is None else float(self.gate(ctx))
        return float(self.weight) * float(self.fn(ctx)) * g

    def rate(self, ctx: Ctx) -> float:
        """Ставка члена в награде В СЕКУНДУ на данном состоянии."""
        return self.value(ctx) / ctx.dt


# ---------------------------------------------------------------------------
# Реестр
# ---------------------------------------------------------------------------


class RewardRegistry:
    """Реестр членов награды: считает сумму и хранит вклад каждого.

    Использование в среде::

        self.rew = (RewardRegistry()
                    .add(Term("progress", f_progress, weight=1.0, unit="м", why="..."))
                    .add(Term("collide",  f_collide,  weight=-30.0, why="...")))
        ...
        total, terms = self.rew(ctx)
        return obs, total, terminated, truncated, {"terms": terms}

    Накопление за эпизод идёт автоматически; `episode_summary()` возвращает
    сводку, `reset()` вызывается из `env.reset()`.
    """

    def __init__(self, terms: Iterable[Term] = ()) -> None:
        self._terms: List[Term] = []
        self._index: Dict[str, Term] = {}
        for t in terms:
            self.add(t)
        self.reset()

    # -- сборка -----------------------------------------------------------
    def add(self, term: Term) -> "RewardRegistry":
        if term.name in self._index:
            raise ValueError(f"член награды {term.name!r} уже зарегистрирован")
        self._terms.append(term)
        self._index[term.name] = term
        self._sum.setdefault(term.name, 0.0)
        self._nz.setdefault(term.name, 0)
        return self

    @property
    def terms(self) -> Tuple[Term, ...]:
        return tuple(self._terms)

    def __getitem__(self, name: str) -> Term:
        return self._index[name]

    def __len__(self) -> int:
        return len(self._terms)

    # -- счёт -------------------------------------------------------------
    def __call__(self, ctx: Ctx) -> Tuple[float, Dict[str, float]]:
        out: Dict[str, float] = {}
        total = 0.0
        for term in self._terms:
            v = term.value(ctx)
            out[term.name] = v
            total += v
            self._sum[term.name] += v
            if v != 0.0:
                self._nz[term.name] += 1
        self._steps += 1
        self._dt = ctx.dt
        self._total += total
        return float(total), out

    def reset(self) -> None:
        """Обнуляет накопители эпизода (звать из env.reset())."""
        self._sum: Dict[str, float] = {t.name: 0.0 for t in self._terms}
        self._nz: Dict[str, int] = {t.name: 0 for t in self._terms}
        self._steps = 0
        self._total = 0.0
        self._dt = 0.0

    # -- сводка -----------------------------------------------------------
    def episode_summary(self) -> Dict[str, Dict[str, float]]:
        """{name: {sum, per_sec, share, share_pos, share_neg, n_nonzero}}.

        `per_sec` — сумма за эпизод, делённая на его длительность в секундах.
        `share`   — доля |суммы| члена в СУММЕ МОДУЛЕЙ всех членов. Именно эта
                    доля показывает душителя: у платформы один член забирал
                    48 % награды режима (walk_env_r4.py:330-332).
        """
        if self._steps == 0:
            return {t.name: {"sum": 0.0, "per_sec": 0.0, "share": 0.0,
                             "share_pos": 0.0, "share_neg": 0.0, "n_nonzero": 0}
                    for t in self._terms}
        seconds = self._steps * self._dt
        abs_total = sum(abs(v) for v in self._sum.values()) or 1.0
        pos_total = sum(v for v in self._sum.values() if v > 0) or 1.0
        neg_total = -sum(v for v in self._sum.values() if v < 0) or 1.0
        out: Dict[str, Dict[str, float]] = {}
        for t in self._terms:
            s = self._sum[t.name]
            out[t.name] = {
                "sum": s,
                "per_sec": s / seconds,
                "share": abs(s) / abs_total,
                "share_pos": (s / pos_total) if s > 0 else 0.0,
                "share_neg": (-s / neg_total) if s < 0 else 0.0,
                "n_nonzero": self._nz[t.name],
            }
        return out

    @property
    def steps(self) -> int:
        return self._steps

    @property
    def seconds(self) -> float:
        return self._steps * self._dt

    @property
    def total(self) -> float:
        return self._total


# ---------------------------------------------------------------------------
# Логирование вкладов в TensorBoard
# ---------------------------------------------------------------------------


class RewardLogCallback(BaseCallback):
    """Пишет вклады членов награды в TensorBoard: rew/<name>_per_s и rew/<name>_share.

    Читает `info["terms"]` из ВСЕХ сред вектора (SB3 кладёт список info в
    `self.locals["infos"]`), копит окно длиной `log_freq` ВЫЗОВОВ колбэка и
    сбрасывает средние в логгер.

    ЕДИНИЦЫ (проверено по исходникам SB3 2.4.1, common/callbacks.py:44-46,
    :111-112): один вызов `_on_step` — это один `env.step` ВЕКТОРНОЙ среды,
    то есть `n_envs` env-шагов. Поэтому среднее по окну берётся по числу
    собранных записей terms (по одной на среду на вызов), и умножение на
    1/dt даёт честную ставку в награде за секунду ОДНОЙ среды.

    В боевой платформе этого колбэка нет — вклады читались офлайн-скриптами
    задним числом (05_platform_code.md §7).
    """

    def __init__(self, dt: float, log_freq: int = 1000, prefix: str = "rew", verbose: int = 0) -> None:
        super().__init__(verbose)
        if float(dt) <= 0:
            raise ValueError("dt обязан быть > 0")
        if int(log_freq) <= 0:
            raise ValueError("log_freq обязан быть > 0")
        self.dt = float(dt)
        self.log_freq = int(log_freq)
        self.prefix = str(prefix)
        self._acc: Dict[str, float] = {}
        self._n = 0
        self.last: Dict[str, Dict[str, float]] = {}

    def _collect(self, infos) -> None:
        for info in infos or ():
            terms = None
            if isinstance(info, dict):
                terms = info.get("terms")
            if not isinstance(terms, dict):
                continue
            for k, v in terms.items():
                self._acc[k] = self._acc.get(k, 0.0) + float(v)
            self._n += 1

    def _flush(self) -> Dict[str, Dict[str, float]]:
        if self._n == 0:
            return {}
        abs_total = sum(abs(v) for v in self._acc.values()) or 1.0
        out: Dict[str, Dict[str, float]] = {}
        logger = getattr(getattr(self, "model", None), "logger", None)
        for k, v in self._acc.items():
            per_s = v / self._n / self.dt
            share = abs(v) / abs_total
            out[k] = {"per_sec": per_s, "share": share}
            if logger is not None:
                logger.record(f"{self.prefix}/{k}_per_s", per_s)
                logger.record(f"{self.prefix}/{k}_share", share)
        self._acc.clear()
        self._n = 0
        self.last = out
        return out

    def _on_step(self) -> bool:
        self._collect(self.locals.get("infos"))
        if self.n_calls % self.log_freq == 0:
            self._flush()
        return True

    def _on_training_end(self) -> None:
        self._flush()


# ---------------------------------------------------------------------------
# Отчёт
# ---------------------------------------------------------------------------


def report(registry: RewardRegistry, dt: float, top: Optional[int] = None) -> str:
    """Таблица: член | награда/с | доля от |суммы| | знак | единица | зачем.

    Печатается после каждого прогона и после КАЖДОГО изменения весов —
    это и есть калибровка «в единицах награды в секунду» вместо «на глаз».
    Член с долей выше 0.40 помечается как кандидат в душители: у платформы
    такой член забирал 48 % награды режима (walk_env_r4.py:330-332).
    """
    if float(dt) <= 0:
        raise ValueError("dt обязан быть > 0")
    summ = registry.episode_summary()
    rows = sorted(summ.items(), key=lambda kv: -abs(kv[1]["per_sec"]))
    if top:
        rows = rows[:top]
    total_per_s = sum(v["per_sec"] for v in summ.values())
    abs_per_s = sum(abs(v["per_sec"]) for v in summ.values())

    head = (
        f"{'член':<16} | {'награда/с':>11} | {'доля':>6} | {'знак':>4} | "
        f"{'ненулевых':>9} | {'единица':<8} | зачем"
    )
    out: List[str] = []
    out.append(
        f"вклад членов награды: {registry.steps} шагов, dt={dt:g} с, "
        f"{registry.seconds:.3f} с, сумма {registry.total:.3f} "
        f"({total_per_s:.3f}/с, модуль {abs_per_s:.3f}/с)"
    )
    out.append(head)
    out.append("-" * len(head))
    for name, st in rows:
        term = registry[name]
        sign = "+" if st["per_sec"] > 0 else ("-" if st["per_sec"] < 0 else "0")
        flag = "  <-- >40 % |суммы|, кандидат в душители" if st["share"] > 0.40 else ""
        out.append(
            f"{name:<16} | {st['per_sec']:>11.3f} | {st['share']*100:>5.1f}% | {sign:>4} | "
            f"{st['n_nonzero']:>9} | {term.unit:<8} | {term.why}{flag}"
        )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# САМОПРОВЕРКА
# ---------------------------------------------------------------------------


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError("САМОПРОВЕРКА ПРОВАЛЕНА: " + msg)


class _FakeLogger:
    def __init__(self) -> None:
        self.records: Dict[str, float] = {}

    def record(self, key: str, value) -> None:
        self.records[key] = value


class _FakeModel:
    def __init__(self) -> None:
        self.num_timesteps = 0
        self.logger = _FakeLogger()


def _selftest() -> int:
    print("=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.rewards")
    print("=" * 78)

    DT = 0.02  # 50 Гц — шаг синтетической среды самопроверки

    # --- 1. Арифметика: ответы посчитаны на бумаге ------------------------
    # Член платит ровно +2.2 за шаг. При dt = 0.02 это 2.2/0.02 = 110.0/с.
    reg = RewardRegistry()
    reg.add(Term("lin", lambda c: 2.2, weight=1.0, unit="доля", why="слежение за скоростью"))
    reg.add(Term("energy", lambda c: -0.5, weight=1.0, unit="доля", why="штраф за момент"))
    # Гейт качества 0.5 обязан ровно вдвое срезать вклад.
    reg.add(Term("stride", lambda c: 1.0, weight=4.0, gate=lambda c: 0.5,
                 unit="м", why="оплата длины шага, гейтированная качеством слежения"))

    N = 100  # 100 шагов по 0.02 с = ровно 2 секунды
    ctx = Ctx(DT, 0.0, speed=0.25)
    for i in range(N):
        total, terms = reg(ctx)
    _check(abs(total - (2.2 - 0.5 + 2.0)) < 1e-12, f"сумма за шаг {total}, ожидалось 3.7")

    summ = reg.episode_summary()
    print("\n1. Синтетика с известным ответом (100 шагов * 0.02 с = 2.000 с)")
    print(f"   {'член':<8} | {'сумма':>9} | {'/с':>9} | ожидалось /с")
    expected = {"lin": 110.0, "energy": -25.0, "stride": 100.0}
    for name, want in expected.items():
        got = summ[name]["per_sec"]
        print(f"   {name:<8} | {summ[name]['sum']:>9.3f} | {got:>9.3f} | {want:>9.3f}")
        _check(abs(got - want) < 1e-9, f"{name}: {got}/с, ожидалось {want}/с")
    _check(abs(reg.seconds - 2.0) < 1e-12, "длительность эпизода посчитана неверно")
    print("   гейт 0.5 при весе 4.0 и fn=1.0 даёт 4*1*0.5/0.02 = 100.0/с — совпало.")

    # --- 2. Душитель: воспроизводим замер платформы -----------------------
    # walk_env_r4.py:259-264 — «при 0.5 член давал -105.5/с против r_lin +84.5/с
    # и задавил бы всё остальное». Строим ровно такие ставки и проверяем,
    # что доля ловит душителя.
    print("\n2. Душитель: ставки -105.5/с и +84.5/с (числа из walk_env_r4.py:259-264)")
    reg2 = RewardRegistry()
    reg2.add(Term("r_lin", lambda c: 84.5 * DT, unit="доля", why="слежение за командой"))
    reg2.add(Term("p_new", lambda c: -105.5 * DT, unit="доля", why="новый штраф с весом 0.5"))
    reg2.add(Term("r_small", lambda c: 5.0 * DT, unit="доля", why="мелкий бонус"))
    for _ in range(50):
        reg2(Ctx(DT))
    print("\n".join("   " + s for s in report(reg2, DT).splitlines()))
    s2 = reg2.episode_summary()
    _check(abs(s2["p_new"]["per_sec"] + 105.5) < 1e-9, "ставка душителя посчитана неверно")
    _check(abs(s2["r_lin"]["per_sec"] - 84.5) < 1e-9, "ставка r_lin посчитана неверно")
    _check(s2["p_new"]["share"] > 0.40, "душитель (>40 % модуля суммы) НЕ помечен")
    _check(s2["r_small"]["share"] < 0.40, "мелкий член ошибочно помечен душителем")
    print(f"   доля душителя {s2['p_new']['share']*100:.1f} % от |суммы| — помечен верно.")

    # --- 3. Аттрактор «стоять»: абсолютное ядро против относительного -----
    # 06_pitfalls.md §A4 / walk_env_r4.py:682-696: при cmd 0.4 абсолютное ядро
    # exp(-8*err^2) платит СТОЯЩЕЙ машине 27.8 % слежения, относительное — 1.7 %.
    import math

    def abs_kernel(cmd: float, v: float) -> float:
        return math.exp(-8.0 * (cmd - v) ** 2)

    def rel_kernel(cmd: float, v: float) -> float:
        sigma = max(0.35 * abs(cmd), 0.07)
        return math.exp(-2.0 * (cmd - v) ** 2 / sigma ** 2)

    print("\n3. Ядро слежения: сколько платят НЕПОДВИЖНОЙ машине (v = 0)")
    print(f"   {'команда':>8} | {'абсолютное':>11} | {'относительное':>13}")
    for cmd in (0.1, 0.2, 0.4, 0.8):
        a = abs_kernel(cmd, 0.0)
        r = rel_kernel(cmd, 0.0)
        print(f"   {cmd:>8.2f} | {a*100:>10.2f}% | {r*100:>12.2f}%")
        _check(r < a, f"относительное ядро платит стоя не меньше абсолютного при cmd={cmd}")
    a04 = abs_kernel(0.4, 0.0) * 100
    r01 = rel_kernel(0.1, 0.0) * 100
    r04 = rel_kernel(0.4, 0.0) * 100
    print(f"   абсолютное ядро при cmd = 0.40 платит стоя {a04:.1f} %")
    print(f"   относительное ядро: {r04:.4f} % при cmd = 0.40 и {r01:.1f} % на нижней")
    print(f"   границе диапазона cmd = 0.10 (там sigma упирается в пол 0.07) —")
    print("   это и есть худший случай «1.7 % при ЛЮБОЙ команде» из 06_pitfalls.md §A4;")
    print("   там же для абсолютного ядра приведено 27.8 % — совпадает до десятой.")
    _check(abs(a04 - 27.8) < 0.1, f"абсолютное ядро при cmd 0.4 дало {a04:.1f} %, а в отчёте 27.8 %")
    _check(abs(r01 - 1.7) < 0.1, f"относительное ядро на нижней границе дало {r01:.1f} %, а в отчёте 1.7 %")
    _check(r04 < 0.01, "относительное ядро при рабочей команде всё ещё платит стоя заметную долю")
    # Ключевое свойство: выше пола sigma доля стояния ПОСТОЯННА и ничтожна,
    # тогда как у абсолютного ядра она растёт при уменьшении команды.
    _check(
        abs_kernel(0.1, 0.0) > abs_kernel(0.8, 0.0) * 10,
        "абсолютное ядро обязано платить стоя тем больше, чем меньше команда",
    )

    # --- 4. reset() обязан обнулять накопители ---------------------------
    reg2.reset()
    _check(reg2.steps == 0 and reg2.total == 0.0, "reset() не обнулил накопители")
    _check(all(v["sum"] == 0.0 for v in reg2.episode_summary().values()),
           "reset() не обнулил суммы членов")

    # --- 5. Повторное имя — ошибка ---------------------------------------
    try:
        RewardRegistry().add(Term("a", lambda c: 0.0)).add(Term("a", lambda c: 1.0))
    except ValueError:
        pass
    else:
        raise AssertionError("САМОПРОВЕРКА ПРОВАЛЕНА: реестр принял два члена с одним именем")

    # --- 6. RewardLogCallback на синтетических info -----------------------
    print("\n4. RewardLogCallback: вклады из info['terms'] двух сред")
    cb = RewardLogCallback(dt=DT, log_freq=2)
    cb.model = _FakeModel()
    infos = [{"terms": {"lin": 2.2, "energy": -0.5}}, {"terms": {"lin": 2.2, "energy": -0.5}}]
    for _ in range(2):
        cb.n_calls += 1
        cb.locals = {"infos": infos}
        cb._on_step()
    rec = cb.model.logger.records
    print(f"   записано в logger: {sorted(rec)}")
    print(f"   rew/lin_per_s = {rec['rew/lin_per_s']:.3f} (ожидалось 110.000)")
    print(f"   rew/energy_per_s = {rec['rew/energy_per_s']:.3f} (ожидалось -25.000)")
    _check(abs(rec["rew/lin_per_s"] - 110.0) < 1e-9, "колбэк посчитал ставку lin неверно")
    _check(abs(rec["rew/energy_per_s"] + 25.0) < 1e-9, "колбэк посчитал ставку energy неверно")
    _check(abs(rec["rew/lin_share"] - 2.2 / 2.7) < 1e-9, "колбэк посчитал долю неверно")

    print("\n" + "=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.rewards ПРОЙДЕНА")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(_selftest())
