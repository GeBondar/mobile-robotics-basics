"""rl_toolkit.checkpointing — парные ckpt+VecNormalize, честные частоты, честный eval.

ЗАЧЕМ ЭТО НУЖНО
    Веса политики и статистика нормализации наблюдений — это ОДНА
    неразделимая пара. Плюс у колбэков SB3 частота задаётся не в тех
    единицах, в которых её обычно пишут. Оба факта стоили платформе прогонов.

ЧТО ЭТО ПРЕДОТВРАЩАЕТ

 1. «ЕДИНИЦЫ КОЛБЭКОВ SB3»  (06_pitfalls.md §A10, train_walk_r4.py:222-228).
    ПРОВЕРЕНО ПО ИСХОДНИКАМ SB3 2.4.1 (C:/Users/George/anaconda3/Lib/
    site-packages/stable_baselines3/), а не по памяти:
      * common/callbacks.py:44-46
            self.n_calls = 0        # Number of time the callback was called
            self.num_timesteps = 0  # n_envs * n times env.step() was called
      * common/callbacks.py:111-112 — `n_calls += 1` ровно один раз на вызов
        `_on_step`, то есть на один `env.step` ВЕКТОРНОЙ среды;
      * common/callbacks.py:300  — `if self.n_calls % self.save_freq == 0:`
        (условие сохранения — В ВЫЗОВАХ);
      * common/callbacks.py:297  — имя файла:
        f"{name_prefix}_{checkpoint_type}{self.num_timesteps}_steps.{extension}"
        (имя — В ENV-ШАГАХ);
      * common/callbacks.py:449  — у EvalCallback то же самое:
        `if self.eval_freq > 0 and self.n_calls % self.eval_freq == 0:`.
    Отсюда `steps_to_calls()` и главное следствие: РЕАЛЬНЫЙ шаг чекпойнта
    равен `(env_steps // n_envs) * n_envs`. При 12 средах и запрошенных
    500 000 это 499 992, номера накапливают сдвиг, и условие
    `n % 1_000_000 == 0` не выполняется НИКОГДА: «сторож молча простоял весь
    прогон, роликов 0» (RESUME.md:701-711). При 8 средах совпадало случайно,
    потому что 500 000 делится на 8. Отсюда `bucketize()` — «взять последний
    в корзине» вместо проверки делимости.

 2. «ЧУЖОЙ VecNormalize»  (06_pitfalls.md §A9, train_walk_r4.py:214-220).
    «У этой машины статистика наблюдений уезжает на 0.40 сигмы за 2 млн шагов
    (замерено на runs_walk_r4b), то есть чужой vecnorm искажает вход сильнее,
    чем разница между версиями политики.» Масштаб при полном промахе —
    RESUME.md:379-382: obs_rms.count = 78 500 040, замеренные std гравитации
    [0.078, 0.033, 0.023]; донор, обученный на сыром gravity_z ~ 1.0,
    «промахивается по масштабу в 43 раза на первом же канале».
    Короткая формулировка (RESUME.md:1244): «SB3 resume без vecnorm =
    убитая политика».

 3. «У best_model.zip парного vecnorm не бывает».
    ПРОВЕРЕНО по SB3 2.4.1: `EvalCallback._on_step` при новом рекорде делает
    ровно `self.model.save(os.path.join(self.best_model_save_path, "best_model"))`
    (common/callbacks.py:518-521) — и НИЧЕГО про VecNormalize. Пару пишет
    только `CheckpointCallback` при `save_vecnormalize=True`
    (common/callbacks.py:335-341, файл `<prefix>_vecnormalize_<N>_steps.pkl`).
    Поэтому `find_pair()` для `best_model.zip` ГРОМКО предупреждает и отдаёт
    ближайший по номеру vecnorm с пометкой «метрики оценочные».

 4. «ЦЕНА ОЦЕНКИ»  (06_pitfalls.md §A12, train_walk_r4.py:229-237).
    «Замер: интервалы с eval шли на 1218 fps против 1786 без него, и занимали
    26 % времени прогона.» Причём цена НЕСТАЦИОНАРНА: «пока политика падала,
    эпизод обрывался на ~480 шагах; когда она перестала падать, он стал
    полным (1000), и цена оценки удвоилась САМА». Поэтому `setup_callbacks()`
    разводит частоты: чекпойнты часто (они дёшевы), оценка — вдвое реже, и
    печатает предполагаемое число оценок за прогон.

 5. «Честный eval».
    eval-среда: `training=False`, `norm_reward=False` — иначе оценка нормирует
    награду по собственной статистике и становится несравнимой между
    запусками (train_walk_r4.py:120-121). Статистика наблюдений копируется из
    обучающей перед КАЖДОЙ оценкой.
    ЧЕСТНОЕ УТОЧНЕНИЕ ПРО SB3 2.4.1: `EvalCallback` уже сам зовёт
    `sync_envs_normalization(self.training_env, self.eval_env)`
    (common/callbacks.py:451-459), а тот копирует `obs_rms` и `ret_rms`
    через deepcopy (common/vec_env/__init__.py:79-82) — НО только если обе
    среды обёрнуты ОДИНАКОВО, иначе он бросает AssertionError. Наш
    `SyncNormCallback` копирует `obs_rms` напрямую по ссылке на обучающий
    VecNormalize и потому работает и тогда, когда обёртки различаются
    (типичный случай: обучение в SubprocVecEnv, оценка в DummyVecEnv).

 6. «Оценка — не отчёт» (eval_walk_r4.py:5-8): «На R3 это стоило проекта:
    v1 дала 0 % падений и eval 2286 при скорости 0.03 м/с на команде 0.4 —
    политика выучила СТОЯТЬ». Критерий приёмки обязан включать ЦЕЛЕВУЮ
    МЕТРИКУ задачи, а не только награду и выживание.
"""

from __future__ import annotations

import pickle
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback, EvalCallback
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

__all__ = [
    "steps_to_calls",
    "real_checkpoint_step",
    "CheckpointPair",
    "list_pairs",
    "find_pair",
    "bucketize",
    "load_policy",
    "SyncNormCallback",
    "make_eval_env",
    "setup_callbacks",
]

NOTE_PAIRED = "ПАРНЫЙ"
NOTE_NEAREST = "ближайший, метрики оценочные"
NOTE_NONE = "НЕТ"


# ---------------------------------------------------------------------------
# Единицы
# ---------------------------------------------------------------------------


def steps_to_calls(env_steps: int, n_envs: int) -> int:
    """env-шаги -> вызовы `env.step` для `save_freq`/`eval_freq` колбэков SB3.

    Ровно это деление и есть та ошибка, которую все делают один раз:
    колбэк считает СВОИ вызовы (SB3 2.4.1, callbacks.py:300 и :449), а имя
    файла пишет в env-шагах (callbacks.py:297).

    >>> steps_to_calls(500_000, 12)
    41666
    """
    n_envs = int(n_envs)
    if n_envs <= 0:
        raise ValueError("n_envs обязан быть > 0")
    if int(env_steps) <= 0:
        raise ValueError("env_steps обязан быть > 0")
    return max(1, int(env_steps) // n_envs)


def real_checkpoint_step(env_steps: int, n_envs: int) -> int:
    """РЕАЛЬНЫЙ шаг между чекпойнтами после округления вниз в `steps_to_calls`.

    >>> real_checkpoint_step(500_000, 12)   # номера будут 499992, 999984, ...
    499992
    >>> real_checkpoint_step(500_000, 8)    # совпало СЛУЧАЙНО: 500000 % 8 == 0
    500000
    """
    return steps_to_calls(env_steps, n_envs) * int(n_envs)


# ---------------------------------------------------------------------------
# Пара «веса + нормализация»
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckpointPair:
    """Чекпойнт вместе со своей статистикой нормализации наблюдений.

    steps        : номер env-шага из имени файла (не круглый, см. §1 шапки)
    model_path   : путь к .zip с весами
    vecnorm_path : путь к парному .pkl или None
    note         : NOTE_PAIRED | NOTE_NEAREST | NOTE_NONE (+ пояснение)
    """

    steps: int
    model_path: Path
    vecnorm_path: Optional[Path]
    note: str = NOTE_NONE

    @property
    def paired(self) -> bool:
        return self.vecnorm_path is not None and self.note.startswith(NOTE_PAIRED)

    def __str__(self) -> str:
        vn = self.vecnorm_path.name if self.vecnorm_path else "-"
        return f"{self.steps:>12} | {self.model_path.name:<32} | {vn:<40} | {self.note}"


_RE_MODEL = r"^{prefix}_(\d+)_steps\.zip$"
_RE_VECNORM = r"^{prefix}_vecnormalize_(\d+)_steps\.pkl$"


def _scan(run_dir: Path, pattern: str, prefix: str) -> Dict[int, Path]:
    rx = re.compile(pattern.format(prefix=re.escape(prefix)))
    out: Dict[int, Path] = {}
    for p in sorted(Path(run_dir).glob("*")):
        m = rx.match(p.name)
        if m:
            out[int(m.group(1))] = p
    return out


def list_pairs(run_dir: Path, prefix: str = "model") -> List[CheckpointPair]:
    """Все пары `<prefix>_<N>_steps.zip` + `<prefix>_vecnormalize_<N>_steps.pkl`.

    Имена — ровно те, что пишет `CheckpointCallback` в SB3 2.4.1
    (callbacks.py:297). Сортировка по номеру шага, по возрастанию.
    """
    run_dir = Path(run_dir)
    models = _scan(run_dir, _RE_MODEL, prefix)
    vecs = _scan(run_dir, _RE_VECNORM, prefix)
    pairs: List[CheckpointPair] = []
    for n in sorted(models):
        if n in vecs:
            pairs.append(CheckpointPair(n, models[n], vecs[n], NOTE_PAIRED))
        elif vecs:
            near = min(vecs, key=lambda m: (abs(m - n), -m))
            pairs.append(
                CheckpointPair(n, models[n], vecs[near], f"{NOTE_NEAREST} (взят {near})")
            )
        else:
            pairs.append(CheckpointPair(n, models[n], None, NOTE_NONE))
    return pairs


def find_pair(ckpt: Path, run_dir: Optional[Path] = None, prefix: str = "model") -> CheckpointPair:
    """Ищет vecnorm, ПАРНЫЙ чекпойнту по номеру N.

    У `best_model.zip` парного vecnorm НЕ БЫВАЕТ: `EvalCallback` в SB3 2.4.1
    сохраняет только веса (callbacks.py:518-521). В этом случае функция
    печатает громкое предупреждение и возвращает ближайший по номеру pkl с
    пометкой «метрики оценочные».
    """
    ckpt = Path(ckpt)
    run_dir = Path(run_dir) if run_dir is not None else ckpt.parent
    vecs = _scan(run_dir, _RE_VECNORM, prefix)
    m = re.match(_RE_MODEL.format(prefix=re.escape(prefix)), ckpt.name)

    if m is None:
        # best_model.zip и прочие «безномерные» файлы
        if not vecs:
            print(
                f"[vecnorm] ВНИМАНИЕ: у {ckpt.name} нет номера шага и в {run_dir} нет ни одного "
                f"vecnormalize-pkl. Политика получит ЧУЖОЙ масштаб входов "
                f"(0.40 сигмы за 2 млн шагов — 06_pitfalls.md §A9).",
                flush=True,
            )
            return CheckpointPair(-1, ckpt, None, NOTE_NONE + " (нет номера шага)")
        near = max(vecs)
        print(
            f"[vecnorm] ВНИМАНИЕ: у {ckpt.name} парного vecnorm НЕ БЫВАЕТ — EvalCallback "
            f"его не пишет (SB3 2.4.1, callbacks.py:518-521). Взят последний по номеру: "
            f"{vecs[near].name}. Все метрики по этой паре — ОЦЕНОЧНЫЕ.",
            flush=True,
        )
        return CheckpointPair(near, ckpt, vecs[near], f"{NOTE_NEAREST} (best_model, взят {near})")

    n = int(m.group(1))
    if n in vecs:
        return CheckpointPair(n, ckpt, vecs[n], NOTE_PAIRED)
    if vecs:
        near = min(vecs, key=lambda k: (abs(k - n), -k))
        print(
            f"[vecnorm] ВНИМАНИЕ: парного vecnorm для шага {n} нет, взят {near} "
            f"(разница {abs(near - n)} env-шагов). Метрики ОЦЕНОЧНЫЕ.",
            flush=True,
        )
        return CheckpointPair(n, ckpt, vecs[near], f"{NOTE_NEAREST} (взят {near})")
    print(
        f"[vecnorm] ВНИМАНИЕ: в {run_dir} нет ни одного vecnormalize-pkl. "
        f"Загрузка без нормализации — это ДРУГАЯ политика, а не «чуть хуже».",
        flush=True,
    )
    return CheckpointPair(n, ckpt, None, NOTE_NONE)


def bucketize(pairs: Sequence[CheckpointPair], every: int) -> List[CheckpointPair]:
    """По одной паре на интервал `every` env-шагов — БЛИЖАЙШАЯ к его концу.

    НЕ использовать `n % every == 0`: номера чекпойнтов не круглые
    (см. §1 шапки модуля и `real_checkpoint_step`). Раскладка по корзинам
    `n // every` с взятием последнего элемента устойчива к любому шагу и к
    любому числу сред.
    """
    every = int(every)
    if every <= 0:
        raise ValueError("every обязан быть > 0")
    best: Dict[int, CheckpointPair] = {}
    for p in sorted(pairs, key=lambda q: q.steps):
        best[p.steps // every] = p          # последний в корзине затирает предыдущий
    return [best[k] for k in sorted(best)]


# ---------------------------------------------------------------------------
# Загрузка
# ---------------------------------------------------------------------------


def load_policy(pair: CheckpointPair, device: str = "cpu", algo=None):
    """Возвращает `(model, normalize_obs)`.

    `normalize_obs(obs)` повторяет ровно то, что делает VecNormalize внутри
    (SB3 2.4.1, vec_normalize.py:221):

        np.clip((obs - obs_rms.mean) / np.sqrt(obs_rms.var + epsilon),
                -clip_obs, clip_obs)

    Статистика читается прямым `pickle.load` — `VecNormalize.save()` пишет
    обычный pickle (vec_normalize.py:322-330), а `__getstate__` выбрасывает
    `venv` (vec_normalize.py:128-139), поэтому среда для чтения статистики
    НЕ НУЖНА.

    Если пары нет — печатается громкое предупреждение и возвращается
    ТОЖДЕСТВЕННАЯ функция: политика получит сырые наблюдения. Это не
    «чуть хуже», это другая политика (06_pitfalls.md §A9).
    """
    if algo is None:
        from stable_baselines3 import PPO as algo  # ленивый импорт: тяжёлый torch
    model = algo.load(str(pair.model_path), device=device)

    if pair.vecnorm_path is None:
        print(
            f"[vecnorm] ВНИМАНИЕ: {pair.model_path.name} грузится БЕЗ нормализации "
            f"(note={pair.note}). Вход политики в другом масштабе — метрики недостоверны.",
            flush=True,
        )
        return model, (lambda obs: np.asarray(obs, dtype=np.float32))

    with open(pair.vecnorm_path, "rb") as fh:
        vn = pickle.load(fh)
    mean = np.asarray(vn.obs_rms.mean, dtype=np.float64)
    var = np.asarray(vn.obs_rms.var, dtype=np.float64)
    eps = float(getattr(vn, "epsilon", 1e-8))
    clip = float(getattr(vn, "clip_obs", 10.0))
    if not pair.paired:
        print(
            f"[vecnorm] ВНИМАНИЕ: {pair.vecnorm_path.name} — {pair.note}. "
            f"count={float(vn.obs_rms.count):.0f}",
            flush=True,
        )

    def normalize_obs(obs):
        o = np.asarray(obs, dtype=np.float64)
        return np.clip((o - mean) / np.sqrt(var + eps), -clip, clip).astype(np.float32)

    return model, normalize_obs


# ---------------------------------------------------------------------------
# Колбэк честной оценки
# ---------------------------------------------------------------------------


class SyncNormCallback(EvalCallback):
    """EvalCallback, который перед каждой оценкой копирует `obs_rms` в eval-среду.

    Зачем, если SB3 2.4.1 уже делает это сам (callbacks.py:451-459 зовёт
    `sync_envs_normalization`): штатная синхронизация требует, чтобы
    обучающая и оценочная среды были обёрнуты ОДИНАКОВО, иначе бросает
    AssertionError (vec_env/__init__.py:66-78). Типичная боевая конфигурация
    (обучение в SubprocVecEnv, оценка в DummyVecEnv) под это условие не
    подходит. Здесь копирование выполняется до вызова базового `_on_step` и
    не зависит от структуры обёрток.

    Единицы `eval_freq` — ВЫЗОВЫ `env.step`, см. `steps_to_calls`.
    """

    def _on_step(self) -> bool:
        if self.eval_freq > 0 and self.n_calls % self.eval_freq == 0:
            train_vn = self.model.get_vec_normalize_env()
            if train_vn is not None and hasattr(self.eval_env, "obs_rms"):
                self.eval_env.obs_rms = train_vn.obs_rms
        return super()._on_step()


def make_eval_env(env_fn: Callable[[], object], *, clip_obs: float = 10.0, gamma: float = 0.99):
    """Оценочная среда: `VecNormalize(training=False, norm_obs=True, norm_reward=False)`.

    `training=False`  — статистика НЕ обновляется на оценочных эпизодах,
                        иначе оценка «подстраивается» под саму себя;
    `norm_reward=False` — иначе награда нормируется по собственной статистике
                        оценки и становится несравнимой между запусками
                        (train_walk_r4.py:120-121).
    """
    venv = DummyVecEnv([env_fn])
    return VecNormalize(
        venv,
        training=False,
        norm_obs=True,
        norm_reward=False,
        clip_obs=float(clip_obs),
        gamma=float(gamma),
    )


# ---------------------------------------------------------------------------
# Сборка колбэков
# ---------------------------------------------------------------------------


def setup_callbacks(
    *,
    run_dir,
    n_envs: int,
    ckpt_every_steps: int,
    eval_every_steps: Optional[int] = None,
    eval_env=None,
    n_eval_episodes: int = 10,
    curriculum: Optional[BaseCallback] = None,
    name_prefix: str = "model",
    total_timesteps: Optional[int] = None,
    deterministic: bool = True,
    verbose: int = 1,
) -> List[BaseCallback]:
    """Собирает список колбэков с ПРАВИЛЬНО пересчитанными частотами.

    Порядок в списке важен: куррикулум идёт ПЕРВЫМ, чтобы к моменту оценки
    все среды (и обучающие, и eval-копия) уже получили свежие значения рамп
    (05_platform_code.md §1.2 п.2).

    `ckpt_every_steps` / `eval_every_steps` задаются В ENV-ШАГАХ и здесь же
    переводятся в вызовы. По умолчанию оценка идёт ВДВОЕ реже чекпойнтов:
    чекпойнты дёшевы, а оценка стоила платформе 26 % времени прогона
    (1218 fps против 1786 — 06_pitfalls.md §A12).

    Печатает при сборке реальные шаги и предполагаемое число срабатываний —
    одна распечатка вместо смоук-теста.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if eval_every_steps is None:
        eval_every_steps = 2 * int(ckpt_every_steps)

    ckpt_calls = steps_to_calls(ckpt_every_steps, n_envs)
    eval_calls = steps_to_calls(eval_every_steps, n_envs)
    ckpt_real = ckpt_calls * int(n_envs)
    eval_real = eval_calls * int(n_envs)

    if verbose:
        print(
            f"[колбэки] чекпойнт: запрошено {int(ckpt_every_steps)} env-шагов -> "
            f"save_freq={ckpt_calls} вызовов -> РЕАЛЬНЫЙ шаг {ckpt_real} env-шагов",
            flush=True,
        )
        print(
            f"[колбэки] оценка:   запрошено {int(eval_every_steps)} env-шагов -> "
            f"eval_freq={eval_calls} вызовов -> РЕАЛЬНЫЙ шаг {eval_real} env-шагов, "
            f"{int(n_eval_episodes)} эпизодов последовательно в ОДНОЙ среде",
            flush=True,
        )
        if ckpt_real != int(ckpt_every_steps):
            print(
                f"[колбэки] номера чекпойнтов будут НЕ круглыми ({ckpt_real}, {2*ckpt_real}, ...) — "
                f"искать их условием (n % круглое == 0) нельзя, используйте bucketize()",
                flush=True,
            )
        if total_timesteps:
            print(
                f"[колбэки] за {int(total_timesteps)} шагов ожидается "
                f"{int(total_timesteps) // ckpt_real} чекпойнтов и "
                f"{int(total_timesteps) // eval_real} оценок",
                flush=True,
            )

    callbacks: List[BaseCallback] = []
    if curriculum is not None:
        callbacks.append(curriculum)          # ПЕРВЫМ: eval обязан видеть свежие рампы
    callbacks.append(
        CheckpointCallback(
            save_freq=ckpt_calls,
            save_path=str(run_dir),
            name_prefix=name_prefix,
            save_vecnormalize=True,           # ЕДИНСТВЕННЫЙ источник парных pkl
            verbose=max(0, verbose - 1),
        )
    )
    if eval_env is not None:
        callbacks.append(
            SyncNormCallback(
                eval_env,
                best_model_save_path=str(run_dir),
                log_path=str(run_dir),
                eval_freq=eval_calls,
                n_eval_episodes=int(n_eval_episodes),
                deterministic=deterministic,
                render=False,
                verbose=verbose,
            )
        )
    return callbacks


# ---------------------------------------------------------------------------
# САМОПРОВЕРКА
# ---------------------------------------------------------------------------


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError("САМОПРОВЕРКА ПРОВАЛЕНА: " + msg)


def _selftest() -> int:
    import tempfile

    print("=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.checkpointing")
    print("=" * 78)

    # --- 1. Единицы колбэков ---------------------------------------------
    print("\n1. Единицы: env-шаги -> вызовы env.step -> реальный шаг чекпойнта")
    print(f"   {'сред':>5} | {'запрошено':>10} | {'save_freq':>9} | {'реальный шаг':>13} | круглый?")
    table = []
    for n_envs in (1, 4, 8, 12, 24):
        calls = steps_to_calls(500_000, n_envs)
        real = real_checkpoint_step(500_000, n_envs)
        ok = "да" if real == 500_000 else "НЕТ"
        table.append((n_envs, calls, real))
        print(f"   {n_envs:>5} | {500_000:>10} | {calls:>9} | {real:>13} | {ok}")
    _check(steps_to_calls(500_000, 12) == 41666, "steps_to_calls(500000, 12) != 41666")
    _check(real_checkpoint_step(500_000, 12) == 499_992,
           "реальный шаг при 12 средах не 499 992 (RESUME.md:701-711)")
    _check(real_checkpoint_step(500_000, 8) == 500_000,
           "при 8 средах шаг обязан совпасть СЛУЧАЙНО (500000 делится на 8)")
    print("   вывод: при 12 средах реальный шаг 499 992, а не 500 000 — номера уезжают.")

    with tempfile.TemporaryDirectory() as td:
        run = Path(td)
        step = real_checkpoint_step(500_000, 12)      # 499 992

        # --- 2. Раскладка файлов, как их пишет CheckpointCallback ---------
        # k=5 намеренно БЕЗ пары: имитируем прерванный/подчищенный прогон.
        for k in range(1, 9):
            n = step * k
            (run / f"model_{n}_steps.zip").write_bytes(b"fake")
            if k != 5:
                (run / f"model_vecnormalize_{n}_steps.pkl").write_bytes(b"fake")
        (run / "best_model.zip").write_bytes(b"fake")

        pairs = list_pairs(run)
        print(f"\n2. Найдено чекпойнтов: {len(pairs)}")
        print(f"   {'шаг':>12} | {'файл весов':<32} | {'файл нормализации':<40} | пометка")
        for p in pairs:
            print("   " + str(p))
        _check(len(pairs) == 8, f"list_pairs нашёл {len(pairs)} вместо 8")
        _check(sum(p.paired for p in pairs) == 7, "парных чекпойнтов не 7")

        # --- 3. Ошибка «проверка делимости» ------------------------------
        naive = [p for p in pairs if p.steps % 1_000_000 == 0]
        print(f"\n3. Наивный поиск (n % 1 000 000 == 0) нашёл: {len(naive)} чекпойнтов")
        print("   (именно так сторож демо молча простоял весь прогон — 06_pitfalls.md §A10)")
        _check(len(naive) == 0, "делимость внезапно сработала — раскладка теста неверна")

        buckets = bucketize(pairs, every=1_000_000)
        got = [p.steps for p in buckets]
        want = [999_984, 1_999_968, 2_999_952, 3_999_936]
        print(f"   bucketize(..., every=1 000 000) нашёл: {got}")
        print(f"   ожидалось (последний в каждой корзине): {want}")
        _check(got == want, f"bucketize вернул {got}, ожидалось {want}")

        # --- 4. find_pair -------------------------------------------------
        print("\n4. find_pair")
        exact = find_pair(run / f"model_{step*3}_steps.zip", run)
        print(f"   точная пара:     {exact}")
        _check(exact.paired and exact.steps == step * 3, "точная пара не найдена")

        missing = find_pair(run / f"model_{step*5}_steps.zip", run)
        print(f"   пары нет:        {missing}")
        _check(not missing.paired and missing.vecnorm_path is not None,
               "для чекпойнта без пары не подставлен ближайший")

        best = find_pair(run / "best_model.zip", run)
        print(f"   best_model.zip:  {best}")
        _check(not best.paired and "best_model" in best.note,
               "best_model.zip не помечен как беспарный")

        # --- 5. load_policy на настоящих файлах SB3 -----------------------
        print("\n5. load_policy: настоящий PPO + настоящий VecNormalize")
        import gymnasium as gym
        from gymnasium import spaces
        from stable_baselines3 import PPO

        class _TinyEnv(gym.Env):
            """Трёхканальная среда с каналами РАЗНОГО масштаба — как в парковке
            (dist до 10, sin/cos в +-1): именно из-за такого разброса и нужен
            VecNormalize."""

            metadata = {"render_modes": []}

            def __init__(self):
                self.observation_space = spaces.Box(-1e3, 1e3, (3,), dtype=np.float32)
                self.action_space = spaces.Box(-1.0, 1.0, (1,), dtype=np.float32)
                self._k = 0

            def reset(self, seed=None, options=None):
                super().reset(seed=seed)
                self._k = 0
                return np.array([5.0, 0.0, 0.5], dtype=np.float32), {}

            def step(self, action):
                self._k += 1
                obs = np.array([5.0, 0.0, 0.5], dtype=np.float32)
                return obs, 0.0, False, self._k >= 8, {}

        venv = VecNormalize(DummyVecEnv([_TinyEnv]), norm_obs=True, norm_reward=True, clip_obs=10.0)
        model = PPO("MlpPolicy", venv, n_steps=16, batch_size=8, device="cpu", verbose=0)
        # Известная статистика: считать нормировку можно на бумаге.
        venv.obs_rms.mean = np.array([5.0, 0.0, 0.5], dtype=np.float64)
        venv.obs_rms.var = np.array([4.0, 1.0, 0.25], dtype=np.float64)
        venv.obs_rms.count = 1234.0

        n_real = 4096
        model.save(str(run / f"model_{n_real}_steps.zip"))
        venv.save(str(run / f"model_vecnormalize_{n_real}_steps.pkl"))

        pair = find_pair(run / f"model_{n_real}_steps.zip", run)
        _check(pair.paired, "свежесохранённая пара не опознана как парная")
        loaded, normalize_obs = load_policy(pair, device="cpu")

        raw = np.array([9.0, 2.0, 0.0], dtype=np.float32)
        got_norm = normalize_obs(raw)
        want_norm = np.clip(
            (raw.astype(np.float64) - venv.obs_rms.mean) / np.sqrt(venv.obs_rms.var + 1e-8),
            -10.0, 10.0,
        ).astype(np.float32)
        print(f"   сырое наблюдение:        {raw}")
        print(f"   нормированное:           {got_norm}")
        print(f"   ожидалось (по формуле):  {want_norm}")
        _check(np.allclose(got_norm, want_norm, atol=1e-12),
               "normalize_obs разошлась с формулой VecNormalize (vec_normalize.py:221)")
        _check(got_norm.dtype == np.float32, "normalize_obs обязана отдавать float32")

        # Цена «чужого» vecnorm: сравним с тождественной нормировкой.
        drift = float(np.max(np.abs(got_norm - raw)))
        print(f"   максимальное расхождение с СЫРЫМ входом: {drift:.3f} сигмы")
        print("   (для сравнения: у боевой машины статистика уезжает на 0.40 сигмы")
        print("    за 2 млн шагов — 06_pitfalls.md §A9; здесь промах куда крупнее)")
        _check(drift > 0.40, "тестовая статистика слишком мягкая, чтобы что-то показать")

        # Политика обязана принять нормированный вход нужной формы.
        act, _ = loaded.predict(got_norm.reshape(1, -1), deterministic=True)
        _check(act.shape == (1, 1), f"predict вернул форму {act.shape}, ожидалось (1, 1)")

        # --- 6. setup_callbacks: частоты и порядок ------------------------
        print("\n6. setup_callbacks: пересчёт частот и порядок колбэков")
        eval_env = make_eval_env(_TinyEnv)
        _check(eval_env.training is False, "eval-среда обучается: статистика поедет")
        _check(eval_env.norm_reward is False, "eval-среда нормирует награду: метрика несравнима")

        from rl_toolkit.curriculum import CurriculumCallback, linear

        curr = CurriculumCallback(
            venv, eval_env, schedule={"reset": linear(0, 1000)}, sync_to_eval=set()
        )
        cbs = setup_callbacks(
            run_dir=run / "cb",
            n_envs=12,
            ckpt_every_steps=500_000,
            eval_every_steps=1_000_000,
            eval_env=eval_env,
            n_eval_episodes=20,
            curriculum=curr,
            total_timesteps=30_000_000,
        )
        kinds = [type(c).__name__ for c in cbs]
        print(f"   собрано: {kinds}")
        _check(kinds[0] == "CurriculumCallback", "куррикулум обязан идти ПЕРВЫМ")
        _check(kinds[1] == "CheckpointCallback", "чекпойнты вторым")
        _check(kinds[2] == "SyncNormCallback", "оценка последней")
        _check(cbs[1].save_freq == 41666, f"save_freq={cbs[1].save_freq}, ожидалось 41666")
        _check(cbs[1].save_vecnormalize is True, "save_vecnormalize выключен — пар не будет")
        _check(cbs[2].eval_freq == 83333, f"eval_freq={cbs[2].eval_freq}, ожидалось 83333")
        _check(cbs[2].eval_freq > cbs[1].save_freq, "оценка обязана быть реже чекпойнтов")

        eval_env.close()
        venv.close()

    print("\n" + "=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.checkpointing ПРОЙДЕНА")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(_selftest())
