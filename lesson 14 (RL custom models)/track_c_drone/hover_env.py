"""C1 «Зависание с нуля»: PPO управляет ЧЕТЫРЬМЯ ВИНТАМИ напрямую.

Это разминка трека и одновременно вторая половина «очной ставки» C3:
здесь у политики нет никакого регулятора под ней, она сама обязана построить
внутренний контур, который в C0 писался руками.

ДЕЙСТВИЕ (4): a in [-1, 1]^4  ->  тяга_i = hover * (1 + K_A * a_i), затем clip.
    K_A = 0.6 даёт диапазон 0.4…1.6 от тяги висения (0.73…2.90 Н при
    ctrlrange 0…4.6 Н) — хватает и на спуск, и на энергичный набор.
    ГЛАВНОЕ: a = 0 — это РОВНО висение. Наивная нормировка
    тяга = ctrl_max*(a+1)/2 ставит висение в a = -0.21 (потому что висение —
    39.45 % диапазона, см. паспорт в stand.py), и стартовая гауссова политика
    со средним 0 даёт тяговооружённость 1.27: дрон улетает вверх с первого
    шага КАЖДОГО эпизода. Демонстрация — probe.py, грабля 4.

НАБЛЮДЕНИЕ (19):
    R^T (target - p)   3   вектор до цели в СК корпуса — инвариант к рысканию
    R^T v              3   скорость в СК корпуса
    R[:,0], R[:,2]     6   два столбца матрицы поворота ВМЕСТО кватерниона:
                           q и -q — один и тот же поворот, кватернион даёт
                           разрыв входа там, где физика непрерывна
    omega              3   в теле; из него политика строит демпфирование
    prev_action        4   без него награда за гладкость НЕ марковская

НАГРАДА — через rl_toolkit.rewards.RewardRegistry: каждый член именован,
у каждого записано ЗАЧЕМ он есть, вклады уходят в info["terms"] и оттуда —
в TensorBoard и в пробы. Веса ниже перенесены из рабочей пробы трека
(обучение 1.5 млн шагов: 30/30 выживаний, средняя финальная ошибка 0.1651 м).

ЕДИНИЦЫ: dt = 10 * 0.002 = 0.02 с, то есть управление на 50 Гц,
эпизод 500 шагов = 10 с.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import gymnasium as gym
import mujoco
from gymnasium import spaces

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl_toolkit.rewards import Ctx, RewardRegistry, Term   # noqa: E402

# один поток torch на воркер SubprocVecEnv: цена импорта sb3/torch в среду
# и обоснование числа воркеров разобраны в шапке scan_env.py
import torch                                               # noqa: E402
torch.set_num_threads(1)

XML = Path(__file__).resolve().parent / "quad.xml"
G = 9.81

K_A = 0.6            # полуразмах действия в долях тяги висения (см. шапку)
FRAME_SKIP = 10      # 10 * 0.002 с = 50 Гц управления
MAX_STEPS = 500      # 10 с эпизода
BOX = 3.0            # ±3 м по x и y от цели — «коробка», за ней вылет
Z_LO, Z_HI = 0.15, 4.0


def _registry() -> RewardRegistry:
    """Реестр наград C1. Веса — из прогона 1.5 млн шагов, не «на глаз».

    Проверять их надо не глазами, а `probe.py` -> probe_reward_terms:
    таблица печатает вклад каждого члена В НАГРАДЕ ЗА СЕКУНДУ и его долю.
    Член с долей выше 40 % — кандидат в душители.
    """
    return (RewardRegistry()
            .add(Term("pos", lambda c: math.exp(-2.0 * c["dist"] ** 2), weight=1.0,
                      unit="доля",
                      why="ядро задачи. Экспонента, а НЕ -d: у -d градиент растёт "
                          "с расстоянием, и дальний старт платит огромную награду "
                          "за один рывок к цели; у exp градиент ограничен. "
                          "Платим за близость к ТОЧКЕ, а не за координату z — "
                          "иначе рождается «прыгун» (грабля 6.2)"))
            .add(Term("up", lambda c: c["up"], weight=0.5, unit="проекция",
                      why="R[2,2] — проекция оси корпуса на мировую вертикаль. "
                          "Заменяет отдельные штрафы крена и тангажа и, в отличие "
                          "от них, не имеет разрыва при обходе ±pi"))
            .add(Term("vel", lambda c: -float(np.dot(c["v"], c["v"])), weight=0.10,
                      unit="(м/с)^2",
                      why="без него политика «зависает» пролётом сквозь цель: "
                          "член pos максимален и на нулевой, и на большой скорости"))
            .add(Term("omega", lambda c: -float(np.dot(c["w"], c["w"])), weight=0.02,
                      unit="(рад/с)^2",
                      why="ОБЯЗАТЕЛЕН. Рыскание у квадрокоптера почти бесплатно: "
                          "20 % дифференциала разворачивают аппарат на 122.49° "
                          "за секунду при РОВНО нулевом дрейфе высоты (stand.py, "
                          "тест 5). Без штрафа политика начинает крутиться"))
            .add(Term("act", lambda c: -float(np.sum((c["a"] - c["a_prev"]) ** 2)),
                      weight=0.02, unit="(доля)^2",
                      why="против дребезга. Тяга не бывает отрицательной, поэтому "
                          "клиппинг выпрямляет дребезг в паразитную подъёмную силу "
                          "(stand.py, тест 10) — политика охотно находит этот режим"))
            .add(Term("alive", lambda c: 1.0, weight=0.5, unit="шаг",
                      why="компенсирует отрицательные члены, чтобы «упасть пораньше» "
                          "не было выгоднее, чем жить. Сумма штрафов на висении "
                          "обязана быть меньше 0.5 — это проверяет probe.py"))
            .add(Term("fall", lambda c: 1.0 if c["fell"] else 0.0, weight=-15.0,
                      unit="событие",
                      why="разовый штраф за вылет из коробки или переворот. "
                          "-15 = 30 шагов жизни: падение стоит дороже, чем "
                          "полсекунды хорошего висения")))


class HoverEnv(gym.Env):
    """Среда C1. Контракт rl_toolkit выполнен полностью:

        * info["terms"]              — вклады членов за шаг;
        * unwrapped.dt              — 0.02 с;
        * set_spawn / set_tilt0     — ручки куррикулума;
        * set_probe_state(state)    — для probes.probe_termination;
        * set_k_a(value)            — для probes.probe_controller_sweep.
    """

    metadata = {"render_modes": ["rgb_array"], "render_fps": 50}

    def __init__(self, render_mode: Optional[str] = None, seed: int = 0,
                 spawn: float = 0.8, tilt0: float = 0.3, max_steps: int = MAX_STEPS,
                 k_a: float = K_A) -> None:
        super().__init__()
        self.render_mode = render_mode
        self.model = mujoco.MjModel.from_xml_path(str(XML))
        self.data = mujoco.MjData(self.model)
        self._rng = np.random.default_rng(seed)
        self._renderer = None

        bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "drone")
        self._bid = bid
        self.mass = float(self.model.body_subtreemass[bid])
        self.hover = self.mass * G / int(self.model.nu)
        self.ctrl_hi = float(self.model.actuator_ctrlrange[0, 1])
        self.k_a = float(k_a)

        self.dt = FRAME_SKIP * float(self.model.opt.timestep)   # 0.02 с — контракт ядра
        self.spawn, self.tilt0, self.max_steps = float(spawn), float(tilt0), int(max_steps)
        self.target = np.array([0.0, 0.0, 1.5])

        self.observation_space = spaces.Box(-np.inf, np.inf, (19,), dtype=np.float32)
        self.action_space = spaces.Box(-1.0, 1.0, (4,), dtype=np.float32)
        self.rew = _registry()
        self._prev_a = np.zeros(4, dtype=np.float32)
        self._steps = 0

    # -- ручки куррикулума и проб -----------------------------------------
    def set_spawn(self, value: float) -> None:
        """Разброс стартовой позиции, м. Применяется со СЛЕДУЮЩЕГО reset()."""
        self.spawn = float(value)

    def set_tilt0(self, value: float) -> None:
        """Максимальный стартовый наклон, рад. Применяется со следующего reset()."""
        self.tilt0 = float(value)

    def set_k_a(self, value: float) -> None:
        """Полуразмах действия в долях висения (для свипа в probe.py)."""
        self.k_a = float(value)

    def set_probe_state(self, state: Dict[str, Any]) -> None:
        """Поставить аппарат в заданную позу — только для probes.probe_termination.

        Пять строк в среде против прогона вслепую: без них нельзя проверить,
        что условие обрыва срабатывает ТАМ, где задумано, и НЕ срабатывает там,
        где не задумано.
        """
        if "pos" in state:
            self.data.qpos[:3] = state["pos"]
        if "quat" in state:
            self.data.qpos[3:7] = state["quat"]
        if "rpy" in state:
            r, p, y = state["rpy"]
            cr, sr = math.cos(r / 2), math.sin(r / 2)
            cp, sp = math.cos(p / 2), math.sin(p / 2)
            cy, sy = math.cos(y / 2), math.sin(y / 2)
            self.data.qpos[3:7] = [cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy,
                                   cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy]
        if "vel" in state:
            self.data.qvel[:3] = state["vel"]
        if "omega" in state:
            self.data.qvel[3:6] = state["omega"]
        mujoco.mj_forward(self.model, self.data)

    # -- gymnasium API -----------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        mujoco.mj_resetData(self.model, self.data)

        self.data.qpos[:3] = self.target + self._rng.uniform(-self.spawn, self.spawn, 3)
        self.data.qpos[2] = float(np.clip(self.data.qpos[2], 0.5, 3.0))

        # случайная ось наклона, угол до tilt0. Курс тоже случайный —
        # иначе политика выучит «нос всегда на +x» и рассыплется на реальном старте
        ax = self._rng.normal(size=3)
        ax /= np.linalg.norm(ax)
        ang = self._rng.uniform(0.0, self.tilt0)
        self.data.qpos[3:7] = [math.cos(ang / 2), *(ax * math.sin(ang / 2))]

        self.data.qvel[:3] = self._rng.uniform(-0.5, 0.5, 3)
        self.data.qvel[3:] = self._rng.uniform(-0.8, 0.8, 3)

        # моторы УЖЕ раскручены до висения: состояние фильтра (na=4) иначе
        # стартует с нуля, и первые 60 мс аппарат просто падает
        self.data.act[:] = self.hover
        self.data.ctrl[:] = self.hover
        mujoco.mj_forward(self.model, self.data)

        self._steps = 0
        self._prev_a[:] = 0.0
        self.rew.reset()
        return self._obs(), {}

    def step(self, action):
        a = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        thrust = np.clip(self.hover * (1.0 + self.k_a * a), 0.0, self.ctrl_hi)
        self.data.ctrl[:] = thrust
        for _ in range(FRAME_SKIP):
            mujoco.mj_step(self.model, self.data)
        self._steps += 1

        p = self.data.qpos[:3]
        v = self.data.qvel[:3]
        w = self.data.qvel[3:6]
        R = self.data.xmat[self._bid].reshape(3, 3)
        up = float(R[2, 2])
        d = float(np.linalg.norm(p - self.target))

        fell = bool(abs(p[0] - self.target[0]) > BOX or abs(p[1] - self.target[1]) > BOX
                    or p[2] < Z_LO or p[2] > Z_HI or up < 0.0)

        ctx = Ctx(self.dt, t=self._steps * self.dt, dist=d, v=v, w=w, up=up,
                  a=a, a_prev=self._prev_a.astype(np.float64), fell=fell)
        rew, terms = self.rew(ctx)
        self._prev_a = a.astype(np.float32)

        info: Dict[str, Any] = {"terms": terms, "dist": d, "final_dist": d,
                                "mean_thrust": float(thrust.mean())}
        term = trunc = False
        if fell:
            term = True
            info["fall"] = True
        elif self._steps >= self.max_steps:
            trunc = True
            info["survived"] = True
        return self._obs(), float(rew), term, trunc, info

    # -- наблюдение и рендер ------------------------------------------------
    def _obs(self) -> np.ndarray:
        d = self.data
        R = d.xmat[self._bid].reshape(3, 3)
        dp = R.T @ (self.target - d.qpos[:3])       # цель в СК корпуса
        vb = R.T @ d.qvel[:3]
        return np.concatenate([dp, vb, R[:, 0], R[:, 2], d.qvel[3:6],
                               self._prev_a]).astype(np.float32)

    def render(self):
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, 720, 960)
        self._renderer.update_scene(self.data, camera="chase")
        return self._renderer.render()

    def close(self):
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


def make_hover_env(seed: int = 0, **kw):
    """Фабрика для векторных сред и для проб (`probe_action_scale` ждёт env_fn)."""
    def _f():
        return HoverEnv(seed=seed, **kw)
    return _f


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from rl_toolkit.rewards import report as reward_report

    env = HoverEnv(seed=0)
    o, _ = env.reset(seed=0)
    print(f"obs {o.shape} {o.dtype}, action {env.action_space}, dt = {env.dt} с, "
          f"эпизод {env.max_steps} шагов = {env.max_steps*env.dt:g} с")
    print(f"тяга висения {env.hover:.4f} Н, диапазон действия -> "
          f"[{env.hover*(1-env.k_a):.4f}, {env.hover*(1+env.k_a):.4f}] Н "
          f"при ctrlrange [0, {env.ctrl_hi}]")
    for i in range(50):
        o, r, te, tr, info = env.step(np.zeros(4))
    print("\n", reward_report(env.rew, env.dt), sep="")
