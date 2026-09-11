"""БОЕВАЯ среда ходьбы — тонкая обёртка над `_reference_walk_env_r4.py`.

ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ
--------------------
Эталонная политика 60M обучалась в боевой среде: 24 члена награды,
эпизод 20 с, доменная рандомизация, контур курса, зеркальная
аугментация. Чтобы показать её паспортные метрики, нужна именно та
среда. Копировать 70 КБ и 949 строк ради этого нельзя — файл
`_reference_walk_env_r4.py` лежит рядом КАК ЕСТЬ, со всем инженерным
журналом прогонов r4c…r4u в комментариях, и читается как источник, а не
как учебный код. Здесь — двадцать строк, которые его подключают.

Имя файла начинается с подчёркивания, поэтому обычный `import` его не
достаёт красиво (`import _reference_walk_env_r4` сработает, но такое имя
в коде урока выглядит как опечатка). Подключаем через `importlib` —
заодно это готовый рецепт «как импортировать модуль по пути к файлу».

ЧТО ЗДЕСЬ ИЗМЕНЕНО ПРОТИВ БОЕВОЙ СРЕДЫ
--------------------------------------
Ничего в физике и награде. Добавлен только способ ЗАФИКСИРОВАТЬ команду
на эпизод — иначе она разыгрывается случайно и свип «команда -> скорость»
невозможен. Штатная приёмка проекта (`sim/eval_walk_r4.py:117`) делает это
одной строкой `env.cmd = cmd`, оставляя фазовые часы и опору курса от
случайного розыгрыша. Здесь они пересчитываются под фактическую команду.
ЗАМЕРЕНО (3 эпизода по 20 с, политика 60M, ровный пол, без рандомизации):

    команда   как в eval_walk_r4   с пересчётом фазы
    0.2       0.202                0.202
    0.4       0.370                0.371
    0.6       0.528                0.528
    0.8       0.688                0.690

То есть разница в третьем знаке — но пересчёт честнее, и он оставлен.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

_REF = HERE / "_reference_walk_env_r4.py"


def load_reference_module():
    """Подключить `_reference_walk_env_r4.py` как модуль по пути к файлу.

    Стандартный рецепт importlib. Модуль кладётся в `sys.modules`, потому
    что иначе при повторном вызове получатся ДВА разных класса с одним
    именем, и `isinstance` начнёт врать.
    """
    name = "_reference_walk_env_r4"
    if name in sys.modules:
        return sys.modules[name]
    if not _REF.exists():
        raise FileNotFoundError(
            f"нет файла {_REF}. Боевая среда — часть комплекта трека B, "
            f"без неё эталонная политика 60M запускается только в учебной "
            f"среде (walk_env.py), а её паспортные метрики снимались в боевой."
        )
    spec = importlib.util.spec_from_file_location(name, _REF)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def make_full_env(cmd_vx: float = 0.4, randomize: bool = False,
                  seed: int | None = None, model: str = "tsaplya2.xml"):
    """Боевая среда с ЗАФИКСИРОВАННОЙ продольной командой.

    randomize=False — это режим ЧЕСТНОЙ ОЦЕНКИ, а не облегчения: паспорт
    политики (`policies/manifest.txt`) снят именно так. С рандомизацией
    (массы ±15 %, трение x0.5…1.25, толчок 0.2…0.5 м/с) числа будут хуже,
    и сравнивать их с паспортом нельзя.
    """
    ref = load_reference_module()
    env = ref.Tsaplya2WalkEnv(seed=seed, randomize=randomize, model=model)

    _orig_reset = env.reset

    def reset(*, seed=None, options=None):
        obs, info = _orig_reset(seed=seed, options=options)
        # 1. сама команда: вперёд, без бокового сноса и без поворота
        env.cmd = np.array([float(cmd_vx), 0.0, 0.0])
        # 2. фазовые часы боевой среды зависят от команды: каденс =
        #    |v_cmd| / длина_шага, но не ниже базовой f_phase
        #    (_reference_walk_env_r4.py:578-586). Без пересчёта они
        #    остались бы от СЛУЧАЙНОЙ команды, которую мы только что стёрли.
        d = min(0.35, max(0.15, 0.6 * abs(float(cmd_vx)) / env.f_phase))
        env._d_swing = float(np.sign(cmd_vx) * d)
        env._f_eff = max(env.f_phase, abs(float(cmd_vx)) / d)
        # 3. эффективная угловая команда контура курса: на первом кадре
        #    ошибка нулевая по построению, поэтому это ровно cmd[2] = 0
        env._wz_eff = 0.0
        # 4. наблюдение пересобрать: пункты 1-3 в него входят
        return env._obs(), info

    env.reset = reset
    return env


def body_vx(env) -> float:
    """Продольная скорость корпуса в его собственной горизонтальной раме.

    Мировая скорость qvel[0] не годится: машина может ехать боком или под
    углом, и тогда «скорость вперёд» окажется завышенной. Разворачиваем
    на текущий курс — ровно как штатная приёмка проекта
    (`sim/eval_walk_r4.py:129-134`).
    """
    q, v = env.data.qpos, env.data.qvel
    yaw = math.atan2(2 * (q[3] * q[6] + q[4] * q[5]),
                     1 - 2 * (q[5] ** 2 + q[6] ** 2))
    c, s = math.cos(-yaw), math.sin(-yaw)
    return float(c * v[0] - s * v[1])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    env = make_full_env(cmd_vx=0.4, seed=0)
    print(f"боевая среда подключена: obs {env.observation_space.shape} "
          f"act {env.action_space.shape}")
    print(f"эпизод {env.max_steps} шагов = {env.max_steps*env.dt:.1f} с, "
          f"dt {env.dt:.3f} с")
    obs, _ = env.reset(seed=0)
    print(f"команда после reset: {env.cmd}   f_eff {env._f_eff:.4f} Гц")
    n = 0
    while True:
        obs, r, term, trunc, info = env.step(np.zeros(env.nu))
        n += 1
        if term or trunc:
            break
    print(f"пассивный эпизод (действие 0): {n} шагов = {n*env.dt:.2f} с")
    print(f"членов награды в боевой среде: {len(info['terms'])}")
