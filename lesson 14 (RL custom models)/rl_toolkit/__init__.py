"""rl_toolkit — ядро урока 14 «RL: свои модели».

Пять модулей, каждый закрывает свой класс ошибок, каждый оплачен прогонами
боевой платформы `legged_robots` (разбор — отчёты 05_platform_code.md и
06_pitfalls.md):

    curriculum.py     рампы сложности по АБСОЛЮТНОМУ счётчику шагов
                      (при resume расписание не обнуляется: три сгоревших
                      прогона, 06_pitfalls.md §A11)
    checkpointing.py  парные ckpt+VecNormalize и честные частоты колбэков
                      (n_calls — это вызовы env.step, а не env-шаги;
                      чужой vecnorm — 0.40 сигмы за 2 млн шагов;
                      EvalCallback стоил 26 % времени: 1218 против 1786 fps)
    rewards.py        реестр членов награды с учётом вклада В НАГРАДЕ ЗА СЕКУНДУ
                      (один член давал -105.5/с против +84.5/с и душил всё)
    diagnostics.py    проверка члена и метрики на синтетике ДО обучения
                      (метрика, тождественно равная нулю; плата min(L/L_cap,1),
                      у которой ставка не зависит от длины шага)
    probes.py         замеры среды ДО обучения: формы, разведка, пассивная база,
                      условия обрыва, цена шага, наблюдаемость, свипы

ПРИНЦИПЫ, КОТОРЫЕ ЭТИ МОДУЛИ ВНЕДРЯЮТ
    1. Каждая нетривиальная константа сопровождается замером, который её
       породил, — иначе это не константа, а суеверие.
    2. Вклад члена награды измеряется в наградах В СЕКУНДУ, а не за шаг.
    3. Любая правка среды/награды проверяется замером ДО обучения:
       прогон стоит часов, проба — секунды.
    4. Пассивная (нулевая) политика — обязательная база сравнения.
    5. Метрика проверяется на синтетике с ЗАРАНЕЕ ИЗВЕСТНЫМ ответом раньше,
       чем ею меряют политику.

ЗАВИСИМОСТИ
    numpy, gymnasium, stable_baselines3 — на уровне модуля.
    mujoco НЕ импортируется нигде: ядро изучается и проверяется без него.
    Проверено на: Python 3.12.3, numpy 2.0.2, gymnasium 1.0.0,
    stable_baselines3 2.4.1, torch 2.6.0+cu124.

САМОПРОВЕРКА (каждый модуль запускается как скрипт и печатает таблицы;
при нарушении инварианта падает с ненулевым кодом)::

    cd "lesson 14 (RL custom models)"
    python -m rl_toolkit.curriculum
    python -m rl_toolkit.checkpointing
    python -m rl_toolkit.rewards
    python -m rl_toolkit.diagnostics
    python -m rl_toolkit.probes
"""

from __future__ import annotations

import importlib
from typing import Any

__version__ = "1.0.0"

# Импорт ЛЕНИВЫЙ (PEP 562). Две причины, обе практические:
#  1. `python -m rl_toolkit.curriculum` сначала исполняет этот файл; если бы он
#     сам импортировал подмодули, runpy печатал бы RuntimeWarning «found in
#     sys.modules after import of package» перед КАЖДОЙ самопроверкой;
#  2. `import rl_toolkit.rewards` не должен тянуть torch через
#     stable_baselines3-зависимости checkpointing, если он не нужен.
# {экспортируемое имя: (модуль, имя внутри модуля)}
_EXPORTS = {
    # curriculum
    "Ramp": ("curriculum", "Ramp"),
    "CurriculumCallback": ("curriculum", "CurriculumCallback"),
    "linear": ("curriculum", "linear"),
    "staircase": ("curriculum", "staircase"),
    "explain": ("curriculum", "explain"),
    # checkpointing
    "steps_to_calls": ("checkpointing", "steps_to_calls"),
    "real_checkpoint_step": ("checkpointing", "real_checkpoint_step"),
    "CheckpointPair": ("checkpointing", "CheckpointPair"),
    "list_pairs": ("checkpointing", "list_pairs"),
    "find_pair": ("checkpointing", "find_pair"),
    "bucketize": ("checkpointing", "bucketize"),
    "load_policy": ("checkpointing", "load_policy"),
    "SyncNormCallback": ("checkpointing", "SyncNormCallback"),
    "make_eval_env": ("checkpointing", "make_eval_env"),
    "setup_callbacks": ("checkpointing", "setup_callbacks"),
    # rewards
    "Ctx": ("rewards", "Ctx"),
    "Term": ("rewards", "Term"),
    "RewardRegistry": ("rewards", "RewardRegistry"),
    "RewardLogCallback": ("rewards", "RewardLogCallback"),
    "reward_report": ("rewards", "report"),
    # diagnostics
    "Table": ("diagnostics", "Table"),
    "Verdict": ("diagnostics", "Verdict"),
    "sweep_term": ("diagnostics", "sweep_term"),
    "gradient_report": ("diagnostics", "gradient_report"),
    "synthetic_rollout": ("diagnostics", "synthetic_rollout"),
    "periodic_gait": ("diagnostics", "periodic_gait"),
    "null_policy_baseline": ("diagnostics", "null_policy_baseline"),
    "reachability": ("diagnostics", "reachability"),
    "term_share_table": ("diagnostics", "term_share_table"),
    # probes
    "probe_shapes": ("probes", "probe_shapes"),
    "probe_action_scale": ("probes", "probe_action_scale"),
    "probe_null_baseline": ("probes", "probe_null_baseline"),
    "probe_reward_terms": ("probes", "probe_reward_terms"),
    "probe_termination": ("probes", "probe_termination"),
    "probe_step_cost": ("probes", "probe_step_cost"),
    "probe_cameras": ("probes", "probe_cameras"),
    # render
    "tracking_camera": ("render", "tracking_camera"),
    "record_frames": ("render", "record_frames"),
    "save_gif": ("render", "save_gif"),
    "probe_observability": ("probes", "probe_observability"),
    "probe_controller_sweep": ("probes", "probe_controller_sweep"),
    "probe_report": ("probes", "report"),
}


def __getattr__(name: str) -> Any:
    try:
        mod_name, attr = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"в rl_toolkit нет имени {name!r}") from None
    obj = getattr(importlib.import_module(f".{mod_name}", __name__), attr)
    globals()[name] = obj          # больше сюда не заходим
    return obj


def __dir__():
    return sorted(__all__)

__all__ = [
    # curriculum
    "Ramp", "CurriculumCallback", "linear", "staircase", "explain",
    # checkpointing
    "steps_to_calls", "real_checkpoint_step", "CheckpointPair", "list_pairs",
    "find_pair", "bucketize", "load_policy", "SyncNormCallback", "make_eval_env",
    "setup_callbacks",
    # rewards
    "Ctx", "Term", "RewardRegistry", "RewardLogCallback", "reward_report",
    # diagnostics
    "Table", "Verdict", "sweep_term", "gradient_report", "synthetic_rollout",
    "periodic_gait", "null_policy_baseline", "reachability", "term_share_table",
    # probes
    "probe_shapes", "probe_action_scale", "probe_null_baseline", "probe_reward_terms",
    "probe_termination", "probe_step_cost",
    "probe_cameras", "probe_observability",
    "probe_controller_sweep", "probe_report",
    "__version__",
]
