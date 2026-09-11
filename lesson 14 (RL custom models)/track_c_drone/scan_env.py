"""C2 «Сканер» — ядро трека: награда за ПОКРЫТИЕ поверхности объекта.

ЧЕМ ЭТА ЗАДАЧА ОТЛИЧАЕТСЯ ОТ ТРЕКОВ A И B
    Трек A платит за расстояние до цели, трек B — за слежение за командой
    скорости. Обе награды — ФУНКЦИЯ ТЕКУЩЕЙ ПОЗЫ. Награда за покрытие
    принципиально другая:
      * она зависит от ИСТОРИИ (ценность точки пространства зависит от того,
        отснята ли уже соответствующая ячейка) — то есть не марковская по позе;
      * поэтому карта покрытия ОБЯЗАНА лежать в наблюдении, иначе награда
        физически ненаблюдаема и штраф превращается в шум;
      * она субмодулярна: отдача убывает, и без штрафа времени задача
        вырождается в «когда-нибудь долети».

ДЕЙСТВИЕ (4): уставка в СК корпуса [vx, vy, vz, wz], диапазоны
    ±1.6 м/с и ±1.8 рад/с. Уставку отрабатывает каскадный ПД из stand.py
    (C0), слежение проверено там же: 1.0 -> 0.999, 1.5 -> 1.498,
    2.0 -> 1.996 м/с; wz 0.8 -> 0.800, 1.2 -> 1.200 рад/с.
    Это и есть «RL поверх регулятора»: политика распоряжается скоростями,
    а не винтами.

СЕНСОР: 15 лучей (5 по азимуту ±35°, 3 по углу места ±22°) через mj_multiRay.
    Батчевый вызов вместо цикла по mj_ray — замер probe.py: ускорение
    от 5.6x на 15 лучах до ~19x на 2048. Форма данных совпадает с
    sensor_msgs/msg/LaserScan из урока 12 (angle_min, angle_max,
    angle_increment, ranges) — см. метод laser_scan().

ПОЧЕМУ ПОЛЕ ЗРЕНИЯ УЗКОЕ И ЕСТЬ ПРЕДЕЛ ДАЛЬНОСТИ ОСМОТРА (R_INSPECT = 2.5 м)
    Первая версия среды (сетка 12x4, «лидар» 140°, без предела дальности)
    давала СЛУЧАЙНОЙ политике 0.62 покрытия: награда почти не различала
    политики, хотя формально работала. Три правки — сетка 16x6, камера
    ±35°/±22°, засчитывать ячейку только с дистанции <= 2.5 м — опустили
    случайную политику до 0.13. Приёмочный тест probe.py требует < 0.20.

ЕДИНИЦЫ: dt = 10 * 0.002 = 0.02 с (50 Гц), эпизод 1500 шагов = 30 с.
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
from rl_toolkit.rewards import Ctx, RewardRegistry, Term      # noqa: E402
from stand import CascadePD                                    # noqa: E402

# ЦЕНА ЭТОГО ИМПОРТА, КОТОРУЮ НАДО ЗНАТЬ.
# rl_toolkit.rewards тянет stable_baselines3, а с ним torch — значит torch
# оказывается в КАЖДОМ воркере SubprocVecEnv и добавляет ~0.4 ГБ на воркер.
# Замер этого прогона: 8 воркеров по ~516 МБ + родитель 600 МБ ≈ 4.7 ГБ.
# Отсюда 8 воркеров по умолчанию, а не 16: 16 воркеров на машине с 16 ГБ дают
# «The paging file is too small for this operation to complete», и прогон
# умирает БЕЗ трейсбека — это ровно то, что случилось при первой попытке
# запустить обучение параллельно с чужим прогоном (BrokenPipeError, воркер
# убит ОС).
#
# ДВА ЗАМЕРА ОДНОЙ И ТОЙ ЖЕ СРЕДЫ, которые стоит показать студенту рядом
# (probe.py, строка «C2 цена шага», n = 2000):
#     машина свободна      143 мкс/шаг   6995 шаг/с   x139.9 к реальному времени
#     идёт чужое обучение 1846 мкс/шаг    541 шаг/с   x10.8
# Разница в ТРИНАДЦАТЬ раз, код среды при этом не менялся ни на строку.
# Практический вывод: цену шага и fps меряют на СВОБОДНОЙ машине, иначе
# в отчёт попадает загрузка соседа, а не свойство среды.
import torch                                                   # noqa: E402
torch.set_num_threads(1)

XML = Path(__file__).resolve().parent / "scan_scene.xml"
G = 9.81

# --- развёртка покрытия ----------------------------------------------------
N_SECT, N_BAND = 16, 6         # 96 ячеек; N_BAND входит в размер наблюдения
Z_LO, Z_HI = 0.4, 3.9          # полосы по высоте: от 0.4 м до крыши 3.84 м
R_HIT_MAX = 2.6                # попадание дальше этого радиуса от оси —
                               # это не объект, а пол или соседняя стена
R_INSPECT = 2.5                # ячейка засчитывается только с этой дистанции

# --- камера ----------------------------------------------------------------
FOV_AZ, N_RAY_AZ = math.radians(35.0), 5
EL_ANGLES = (math.radians(-22.0), 0.0, math.radians(22.0))
RAY_MAX = 6.0

# --- аппарат и арена -------------------------------------------------------
V_MAX, WZ_MAX = 1.6, 1.8
FRAME_SKIP = 10                # 50 Гц управления
INNER_EVERY = 10               # внутренний контур РАЗ в шаг среды (см. ниже)
MAX_STEPS = 1500               # 30 с
ARENA_R, Z_MIN, Z_MAX = 9.0, 0.35, 6.0
D_SAFE = 1.35                  # коридор безопасности вокруг объекта
COV_TARGET = 0.85

# INNER_EVERY = 10 значит «ПД считается один раз за шаг среды, на 50 Гц».
# Замер: ПД 10 раз за шаг среды -> 3046 шаг/с; один раз -> 6824 шаг/с,
# ускорение 2.24x, а качество слежения НЕ изменилось (vx_cmd 1.12 м/с даёт
# 1.1187 м/с при обеих частотах). Правило: контур можно считать на частоте
# управления, если его полоса <= 1/20 этой частоты — у нас 12 рад/с ≈ 1.9 Гц
# против 50 Гц.

W_COV, W_PROG, W_TIME, W_ACT, W_NEAR = 3.0, 0.8, 0.01, 0.02, 1.0
R_DONE, R_CRASH = 60.0, -25.0


def _euler(q):
    w, x, y, z = q
    return (math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)),
            math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x)))),
            math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def _registry() -> RewardRegistry:
    """Реестр наград C2.

    Задача покрытия ломается СРАЗУ С ДВУХ СТОРОН, и оба вырождения измерены:
      «таран»            — ячейка засчитывается с 2.5 м, значит выгодно
                           прижаться к стене вплотную; случайная политика
                           бьётся или вылетает в 100 % эпизодов;
      «безопасное висение» — нулевое действие НИКОГДА не падает, доживает все
                           1500 шагов и набирает 0.0146 покрытия.
    Поэтому члены `near` и `time` обязаны стоять ВМЕСТЕ: первый против тарана,
    второй против висения. Проверка соотношения весов — probe.py: скриптовый
    облёт обязан набрать положительную суммарную награду, идеальное висение —
    отрицательную.
    """
    return (RewardRegistry()
            .add(Term("cov", lambda c: float(c["new_cells"]), weight=W_COV,
                      unit="ячеек",
                      why="ядро задачи: плата за НОВЫЕ ячейки. Считаются только "
                          "отснятые с дистанции <= 2.5 м — без этого предела "
                          "случайная политика набирала 0.62 покрытия и награда "
                          "переставала различать политики"))
            .add(Term("prog", lambda c: float(c["hole_prev"] - c["hole"]), weight=W_PROG,
                      unit="м",
                      why="потенциальный шейпинг до ближайшей НЕотснятой ячейки — "
                          "приём трека A, перенесённый в задачу покрытия. Без него "
                          "между дырами лежит плато нулевой награды длиной "
                          "в десятки шагов, и градиента там нет"))
            .add(Term("time", lambda c: -1.0, weight=W_TIME, unit="шаг",
                      why="против «безопасного висения»: нулевое действие не падает "
                          "никогда и доживает все 1500 шагов. Именно этот член "
                          "делает задачу задачей НА ВРЕМЯ, а покрытие за полный "
                          "эпизод в итоге берут все"))
            .add(Term("act", lambda c: -float(np.sum((c["a"] - c["a_prev"]) ** 2)),
                      weight=W_ACT, unit="(доля)^2",
                      why="гладкость уставки: рывки уставки внутренний контур "
                          "отрабатывает наклоном, а наклон уводит камеру с объекта"))
            .add(Term("near", lambda c: -max(0.0, D_SAFE - c["d_obj"]), weight=W_NEAR,
                      unit="м",
                      why="коридор безопасности. Награда за покрытие ТЯНЕТ прижаться "
                          "к поверхности (осмотр засчитывается с 2.5 м), этот член "
                          "её уравновешивает. Без него — «таран»"))
            .add(Term("crash", lambda c: 1.0 if c["crash"] else 0.0, weight=R_CRASH,
                      unit="событие",
                      why="контакт с объектом или полом. -25 = 2500 шагов штрафа "
                          "времени: разбиться дороже, чем облететь весь объект"))
            .add(Term("out", lambda c: 1.0 if c["out"] else 0.0, weight=R_CRASH,
                      unit="событие",
                      why="вылет за арену (r > 9 м или z вне [0.35, 6.0]). Тот же "
                          "вес, что у аварии: «улететь в поле» — не спасение"))
            .add(Term("done", lambda c: 1.0 if c["done"] else 0.0, weight=R_DONE,
                      unit="событие",
                      why="финиш: покрытие >= cov_target. +60 против штрафа времени "
                          "0.01/шаг делает выгодным добрать последние дыры, "
                          "а не крутиться в уже отснятой зоне")))


class DroneScanEnv(gym.Env):
    """Среда C2. Контракт rl_toolkit выполнен полностью:

        info["terms"]                       вклады членов за шаг
        unwrapped.dt                        0.02 с
        set_cov_target / set_spawn_radius / set_n_sect   ручки куррикулума
        set_probe_state(state)              для probes.probe_termination
        set_inner_every / set_r_inspect     для probes.probe_controller_sweep
    """

    metadata = {"render_modes": ["rgb_array"], "render_fps": 50}

    def __init__(self, render_mode: Optional[str] = None, seed: int = 0,
                 inner_every: int = INNER_EVERY, n_sect: int = N_SECT,
                 n_band: int = N_BAND, r_inspect: float = R_INSPECT,
                 cov_target: float = COV_TARGET, max_steps: int = MAX_STEPS,
                 spawn_radius: float = 4.5) -> None:
        super().__init__()
        self.render_mode = render_mode
        self.model = mujoco.MjModel.from_xml_path(str(XML))
        self.data = mujoco.MjData(self.model)
        self._rng = np.random.default_rng(seed)
        self._renderer = None

        self.inner_every = int(inner_every)
        self.r_inspect = float(r_inspect)
        self.cov_target = float(cov_target)
        self.max_steps = int(max_steps)
        self.spawn_radius = float(spawn_radius)
        self.dt = FRAME_SKIP * float(self.model.opt.timestep)

        self._bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "drone")
        self.mass = float(self.model.body_subtreemass[self._bid])
        self.hover = self.mass * G / int(self.model.nu)
        # внутренний контур — ТОТ ЖЕ объект, что в C0. Ни одной строки
        # регулятора здесь не переписано: если бы переписали, C0 перестал бы
        # быть проверкой того, на чём стоит C2
        self.ctl = CascadePD(self.model)

        # --- сетка покрытия ---
        self.n_band = int(n_band)
        self.n_sect = int(n_sect)
        self._n_sect_next = int(n_sect)      # set_n_sect применяется в reset()
        self._build_grid()

        # --- веер лучей в СК камеры (ось X сайта = взгляд) ---
        dirs = []
        for el in EL_ANGLES:
            for i in range(N_RAY_AZ):
                az = -FOV_AZ + 2 * FOV_AZ * i / (N_RAY_AZ - 1)
                dirs.append([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az),
                             math.sin(el)])
        self._dirs = np.ascontiguousarray(dirs, dtype=np.float64)
        self.n_rays = len(dirs)
        # ВСЕ буферы горячего пути выделены здесь и переиспользуются.
        # Это не микрооптимизация: замер профайлером на этой среде показал,
        # что сам mj_multiRay стоит 14.5 мкс на 15 лучей, а аллокации вокруг
        # него — больше 30 мкс. Цена шага среды прямо превращается в часы
        # обучения, поэтому в горячем пути аллокаций быть не должно.
        self._gid = np.full(self.n_rays, -1, dtype=np.int32)
        self._dist = np.full(self.n_rays, -1.0, dtype=np.float64)
        self._world = np.zeros((self.n_rays, 3), dtype=np.float64)

        self._obj_ids = np.array(sorted(
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, n)
            for n in ("tower", "ledge", "cap")), dtype=np.int32)
        # таблица «геом принадлежит объекту съёмки» вместо np.isin по списку:
        # np.isin на 15 элементах стоил 87 мкс на шаг (профайлер), индексация
        # булевой таблицы — доли микросекунды
        # длина ngeom+1, а не ngeom: mj_multiRay кладёт -1 в geomid там, где
        # луч не попал никуда, и _is_obj[-1] обязан быть False — им и будет,
        # потому что последний элемент таблицы никем не занят
        self._is_obj = np.zeros(int(self.model.ngeom) + 1, dtype=bool)
        self._is_obj[self._obj_ids] = True
        self._floor = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
        self._cam = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "cam")

        n_obs = 4 + 3 + 2 + 1 + self.n_rays + 1 + 5 * self.n_band + 4
        self.observation_space = spaces.Box(-np.inf, np.inf, (n_obs,), dtype=np.float32)
        self.action_space = spaces.Box(-1.0, 1.0, (4,), dtype=np.float32)
        self._obs_buf = np.zeros(n_obs, dtype=np.float32)
        self._i_rays = 10                                   # начало блока дальностей
        self._i_cov = self._i_rays + self.n_rays            # доля покрытия
        self._i_map = self._i_cov + 1                       # локальная карта
        self._i_act = self._i_map + 5 * self.n_band         # прошлое действие
        self._cov = 0.0

        self.rew = _registry()
        self._prev_a = np.zeros(4, dtype=np.float32)
        self._steps = 0
        self._prev_hole = 0.0
        self._last_dists = np.full(self.n_rays, RAY_MAX)

    # -- сетка покрытия ----------------------------------------------------
    def _build_grid(self) -> None:
        """Развёртка боковой поверхности объекта: n_sect секторов x n_band полос.

        Точки-представители ячеек лежат на эллипсе 1.15 x 1.0 м — это габарит
        башни (0.9 x 0.7 полуразмеры) плюс запас на выступ. Они нужны ТОЛЬКО
        для потенциального шейпинга `prog` (расстояние до ближайшей дыры);
        засчитывается ячейка по фактическому попаданию луча.
        """
        self.seen = np.zeros((self.n_sect, self.n_band), dtype=bool)
        c = np.zeros((self.n_sect, self.n_band, 3))
        for i in range(self.n_sect):
            a = 2 * math.pi * (i + 0.5) / self.n_sect
            for j in range(self.n_band):
                z = Z_LO + (Z_HI - Z_LO) * (j + 0.5) / self.n_band
                c[i, j] = [1.15 * math.cos(a), 1.0 * math.sin(a), z]
        self.cell_xyz = c
        self._cells_flat = np.ascontiguousarray(c.reshape(-1, 3))   # для _hole()

    @property
    def n_cells(self) -> int:
        return self.n_sect * self.n_band

    def coverage(self) -> float:
        return float(self.seen.mean())

    # -- ручки куррикулума и проб ------------------------------------------
    def set_cov_target(self, value: float) -> None:
        """Порог успеха. В ОЦЕНОЧНОЙ среде всегда 0.85 и НЕ синхронизируется
        с обучающей: иначе куррикулум подделывает метрику (растёт не политика,
        а порог)."""
        self.cov_target = float(value)

    def set_spawn_radius(self, value: float) -> None:
        """Верхняя граница радиуса старта, м. Применяется со следующего reset()."""
        self.spawn_radius = float(value)

    def set_n_sect(self, value: float) -> None:
        """Число секторов развёртки (грубая сетка = плотная награда на старте).

        Число ПОЛОС не трогаем никогда: локальная карта в наблюдении — это
        5 секторов x n_band, и смена n_band поменяла бы размер наблюдения
        посреди обучения. Применяется со следующего reset().
        """
        self._n_sect_next = max(4, int(round(float(value))))

    def set_inner_every(self, value: float) -> None:
        """Как часто считать внутренний контур (шагов физики). Для свипа."""
        self.inner_every = max(1, int(round(float(value))))

    def set_r_inspect(self, value: float) -> None:
        """Дальность, с которой ячейка считается отснятой, м. Для свипа."""
        self.r_inspect = float(value)

    def set_probe_state(self, state: Dict[str, Any]) -> None:
        """Поставить аппарат (и карту покрытия) в заданное состояние.

        Ключи: pos, yaw, vel, seen_fraction. Нужен только пробам —
        probe_termination иначе не может проверить условия обрыва.
        """
        if "pos" in state:
            self.data.qpos[:3] = state["pos"]
        if "yaw" in state:
            y = float(state["yaw"])
            self.data.qpos[3:7] = [math.cos(y / 2), 0, 0, math.sin(y / 2)]
        if "vel" in state:
            self.data.qvel[:3] = state["vel"]
        if "seen_fraction" in state:
            f = float(state["seen_fraction"])
            flat = self.seen.reshape(-1)
            flat[:] = False
            flat[:int(round(f * flat.size))] = True
        mujoco.mj_forward(self.model, self.data)
        self._cov = self.coverage()
        self._prev_hole = self._hole()

    # -- сенсор -------------------------------------------------------------
    def _scan(self):
        """Веер лучей одним вызовом mj_multiRay + отметка новых ячеек.

        Два аргумента mj_multiRay, которые решают всё:

        bodyexclude = тело дрона. Лучи стартуют из сайта на корпусе, и без
        исключения собственного тела сенсор в принципе может измерить
        расстояние до самого себя. На ТЕКУЩЕЙ геометрии этого не происходит
        (проверено: при bodyexclude = -1 ни один из 15 лучей не попадает
        в свои геомы), но зависеть здесь от удачного взаимного расположения
        сайта и лучей нельзя: сдвинули камеру на сантиметр — получили
        «стену в четырёх сантиметрах» и не поняли почему.

        flg_static = True. Башня, выступ, крыша и пол — СТАТИЧЕСКИЕ геомы
        (тело target_obj без свободного сочленения). При flg_static = False
        лучи прошли бы сквозь объект съёмки, и покрытие осталось бы нулевым
        при внешне работающем сенсоре.
        """
        pos = self.data.site_xpos[self._cam]
        R = self.data.site_xmat[self._cam].reshape(3, 3)
        world = np.dot(self._dirs, R.T, out=self._world)       # (n, 3), без аллокации
        self._gid[:] = -1
        self._dist[:] = -1.0
        mujoco.mj_multiRay(self.model, self.data, pos, world.reshape(-1),
                           None, True, self._bid, self._gid, self._dist, None,
                           self.n_rays, RAY_MAX)

        hit = self._dist >= 0.0
        dists = np.where(hit, self._dist, RAY_MAX)
        good = hit & (self._dist <= self.r_inspect) & self._is_obj[self._gid]
        new = 0
        if good.any():
            hits = pos + self._dist[good, None] * world[good]
            rad = np.hypot(hits[:, 0], hits[:, 1])
            ok = rad < R_HIT_MAX
            if ok.any():
                h = hits[ok]
                ang = np.mod(np.arctan2(h[:, 1], h[:, 0]), 2 * math.pi)
                i = (ang / (2 * math.pi) * self.n_sect).astype(int) % self.n_sect
                j = ((h[:, 2] - Z_LO) / (Z_HI - Z_LO) * self.n_band).astype(int)
                inside = (j >= 0) & (j < self.n_band)
                if inside.any():
                    i, j = i[inside], j[inside]
                    fresh = ~self.seen[i, j]
                    # np.unique, потому что несколько лучей за один шаг могут
                    # попасть в ОДНУ ячейку, и без него агент получил бы
                    # двойную плату за одну и ту же новую ячейку.
                    # .size, а не count_nonzero: ячейка с кодом 0 (сектор 0,
                    # полоса 0) — тоже ячейка, а count_nonzero её потеряет
                    new = int(np.unique(i[fresh] * self.n_band + j[fresh]).size)
                    self.seen[i, j] = True
        self._last_dists = dists
        return dists, new

    def laser_scan(self) -> Dict[str, Any]:
        """Средний ряд лучей в формате sensor_msgs/msg/LaserScan (урок 12).

        Поля те же и в том же смысле: angle_min, angle_max, angle_increment,
        range_min, range_max, ranges. Полный сенсор — три таких веера,
        сложенных по углу места; ровно так устроены «кольца» 3D-лидара,
        разобранного в 3d_lidar.md. Смысл метода один: показать студенту,
        что наблюдение политики — это тот же самый LaserScan, только без ROS,
        и обученную политику можно подписать на /scan без правки наблюдения.
        """
        mid = self._last_dists[N_RAY_AZ:2 * N_RAY_AZ]
        return {"angle_min": -FOV_AZ, "angle_max": FOV_AZ,
                "angle_increment": 2 * FOV_AZ / (N_RAY_AZ - 1),
                "range_min": 0.0, "range_max": RAY_MAX,
                "ranges": mid.copy()}

    # -- геометрия ----------------------------------------------------------
    def _hole(self) -> float:
        """Расстояние до ближайшей НЕотснятой ячейки (потенциал для `prog`).

        Считается по КВАДРАТАМ, корень берётся один раз в конце: np.linalg.norm
        по 96 строкам стоил 39 мкс на шаг среды (профайлер, 2000 шагов) —
        это была вторая по стоимости строка всей среды после mj_step.
        """
        free = ~self.seen.reshape(-1)
        if not free.any():
            return 0.0
        d = self._cells_flat[free] - self.data.qpos[:3]
        return float(math.sqrt(np.einsum("ij,ij->i", d, d).min()))

    def _d_obj(self) -> float:
        """Расстояние до габаритной коробки башни (0.9 x 0.7 x 1.8 полуразмеры).

        Считается аналитически, а не рейкастом, и это не про экономию:
        рейкаст меряет расстояние ТУДА, КУДА СМОТРИТ КАМЕРА, а штраф `near`
        обязан работать и когда объект за спиной. Иначе политика научится
        отворачиваться от стены и подходить к ней вплотную задом.
        """
        p = self.data.qpos[:3]
        return float(math.sqrt(max(abs(p[0]) - 0.9, 0.0) ** 2 +
                               max(abs(p[1]) - 0.7, 0.0) ** 2 +
                               max(abs(p[2] - 1.8) - 1.8, 0.0) ** 2))

    def _crash(self) -> bool:
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            if int(c.geom1) in self._obj_ids or int(c.geom2) in self._obj_ids:
                return True
            if int(c.geom1) == self._floor or int(c.geom2) == self._floor:
                return True
        return False

    # -- gymnasium API ------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        if self._n_sect_next != self.n_sect:
            self.n_sect = self._n_sect_next
            self._build_grid()
        mujoco.mj_resetData(self.model, self.data)

        a = self._rng.uniform(-math.pi, math.pi)
        r = self._rng.uniform(3.0, self.spawn_radius)
        self.data.qpos[:3] = [r * math.cos(a), r * math.sin(a),
                              self._rng.uniform(1.0, 3.0)]
        # курс «примерно на объект» с разбросом ±0.4 рад: полностью случайный
        # курс делает первые 100 шагов эпизода слепыми, и стартовая политика
        # не видит ни одной ячейки — награда на старте тождественный ноль
        yaw = math.atan2(-self.data.qpos[1], -self.data.qpos[0]) + \
            self._rng.uniform(-0.4, 0.4)
        self.data.qpos[3:7] = [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
        self.data.act[:] = self.hover
        self.data.ctrl[:] = self.hover
        mujoco.mj_forward(self.model, self.data)

        self.seen[:] = False
        self._steps = 0
        self._prev_a[:] = 0.0
        self.rew.reset()
        self.ctl.reset_stats()
        d, _ = self._scan()
        self._cov = self.coverage()
        self._prev_hole = self._hole()
        return self._obs(d), {}

    def step(self, action):
        a = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        cmd = (a[0] * V_MAX, a[1] * V_MAX, a[2] * V_MAX, a[3] * WZ_MAX)
        for k in range(FRAME_SKIP):
            if k % self.inner_every == 0:
                self.ctl.velocity(self.data, *cmd)
            mujoco.mj_step(self.model, self.data)
        self._steps += 1

        dists, new = self._scan()
        cov = self._cov = self.coverage()      # считаем ОДИН раз за шаг: _obs()
        hole = self._hole()                    # берёт готовое значение
        d_obj = self._d_obj()
        p = self.data.qpos[:3]

        crash = self._crash()
        out = bool(math.hypot(p[0], p[1]) > ARENA_R or p[2] < Z_MIN or p[2] > Z_MAX)
        done = bool(cov >= self.cov_target)

        ctx = Ctx(self.dt, t=self._steps * self.dt, new_cells=new,
                  hole=hole, hole_prev=self._prev_hole, a=a,
                  a_prev=self._prev_a.astype(np.float64), d_obj=d_obj,
                  crash=crash, out=(out and not crash),
                  done=(done and not crash and not out))
        rew, terms = self.rew(ctx)

        self._prev_hole = hole
        self._prev_a = a.astype(np.float32)

        info: Dict[str, Any] = {"terms": terms, "coverage": float(cov),
                                "d_obj": d_obj, "steps": self._steps}
        term = trunc = False
        if crash:
            term = True
            info["crash"] = True
        elif out:
            term = True
            info["out"] = True
        elif done:
            term = True
            info["success"] = True
            info["steps_to_cover"] = self._steps
        elif self._steps >= self.max_steps:
            trunc = True
        return self._obs(dists), float(rew), term, trunc, info

    # -- наблюдение ---------------------------------------------------------
    def _obs(self, dists) -> np.ndarray:
        d = self.data
        p = d.qpos[:3]
        _, _, y = _euler(d.qpos[3:7])
        rad = math.hypot(p[0], p[1])
        ang = math.atan2(p[1], p[0])
        c, s = math.cos(y), math.sin(y)
        vxb = c * d.qvel[0] + s * d.qvel[1]
        vyb = -s * d.qvel[0] + c * d.qvel[1]
        bearing = math.atan2(-p[1], -p[0]) - y       # пеленг на ось объекта
        sect = int((ang % (2 * math.pi)) / (2 * math.pi) * self.n_sect) % self.n_sect

        o = self._obs_buf                     # заполняем на месте, без аллокаций
        # поза в ЦИЛИНДРИЧЕСКИХ координатах вокруг объекта: естественная
        # симметрия задачи. sin/cos вместо угла — нет разрыва на ±pi
        o[0] = rad / ARENA_R
        o[1] = math.sin(ang)
        o[2] = math.cos(ang)
        o[3] = p[2] / Z_MAX
        o[4] = vxb / V_MAX
        o[5] = vyb / V_MAX
        o[6] = d.qvel[2] / V_MAX
        o[7] = math.sin(bearing)              # пеленг на ось объекта: «куда смотреть»
        o[8] = math.cos(bearing)
        o[9] = d.qvel[5] / WZ_MAX             # штраф вращения требует наблюдаемости
        o[self._i_rays:self._i_cov] = dists / RAY_MAX
        o[self._i_cov] = self._cov            # «сколько осталось»
        # локальная карта: текущий сектор ±2, каждый — столбик из n_band полос.
        # БЕЗ НЕЁ агент не знает, ГДЕ дыра, и награда за покрытие ненаблюдаема:
        # штраф (или плата) за ненаблюдаемое — это шум, а не сигнал
        for n, k in enumerate((-2, -1, 0, 1, 2)):
            i0 = self._i_map + n * self.n_band
            o[i0:i0 + self.n_band] = self.seen[(sect + k) % self.n_sect]
        o[self._i_act:] = self._prev_a
        return o.copy()                       # копия обязательна: SB3 держит
                                              # ссылку на obs в буфере роллаута

    # -- рендер -------------------------------------------------------------
    def render(self):
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, 720, 960)
        self._renderer.update_scene(self.data, camera="overview")
        return self._renderer.render()

    def close(self):
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


# ---------------------------------------------------------------------------
# Скриптовый облёт — БАЗА, с которой сравнивается обученная политика
# ---------------------------------------------------------------------------
def orbit_policy(r_orb: float = 1.9, v_tan: float = 1.1, z_period: int = 430,
                 z_list=(0.9, 1.9, 2.9, 3.7)):
    """«Как сделал бы инженер»: спираль вокруг объекта на радиусе r_orb.

    Держит радиус П-регулятором, идёт по касательной, каждые z_period шагов
    переходит на следующую высоту, носом всегда на ось объекта.
    Это честная база: она НЕ падает и в итоге снимает почти всё. Разница
    с обученной политикой — не в потолке покрытия, а во ВРЕМЕНИ.

    Возвращает функцию (env, step_index) -> действие.
    """
    st = {"zi": 0}

    def f(env: DroneScanEnv, i: int) -> np.ndarray:
        p = env.data.qpos[:3]
        _, _, y = _euler(env.data.qpos[3:7])
        rad = math.hypot(p[0], p[1])
        ang = math.atan2(p[1], p[0])
        if i > 0 and i % z_period == 0:
            st["zi"] = (st["zi"] + 1) % len(z_list)
        vr = float(np.clip(-0.9 * (rad - r_orb), -1.0, 1.0))
        vz = float(np.clip(1.2 * (z_list[st["zi"]] - p[2]), -1.0, 1.0))
        vxw = vr * math.cos(ang) - v_tan * math.sin(ang)
        vyw = vr * math.sin(ang) + v_tan * math.cos(ang)
        dy = ((math.atan2(-p[1], -p[0]) - y + math.pi) % (2 * math.pi)) - math.pi
        c, s = math.cos(y), math.sin(y)
        return np.clip([(c * vxw + s * vyw) / V_MAX, (-s * vxw + c * vyw) / V_MAX,
                        vz / V_MAX, np.clip(2.0 * dy, -1, 1)], -1, 1)
    return f


def make_scan_env(seed: int = 0, **kw):
    """Фабрика для векторных сред и проб."""
    def _f():
        return DroneScanEnv(seed=seed, **kw)
    return _f


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from rl_toolkit.rewards import report as reward_report

    env = DroneScanEnv(seed=0)
    o, _ = env.reset(seed=0)
    print(f"obs {o.shape} {o.dtype}  (4 поза + 3 скорость + 2 пеленг + 1 wz + "
          f"{env.n_rays} лучей + 1 покрытие + {5*env.n_band} карта + 4 действие)")
    print(f"действие {env.action_space}, dt = {env.dt} с, эпизод {env.max_steps} шагов "
          f"= {env.max_steps*env.dt:g} с, ячеек {env.n_cells}")
    ls = env.laser_scan()
    print(f"LaserScan: angle_min={ls['angle_min']:.4f} angle_max={ls['angle_max']:.4f} "
          f"angle_increment={ls['angle_increment']:.4f} ranges={np.round(ls['ranges'], 3)}")
    pol = orbit_policy()
    for i in range(600):
        o, r, te, tr, info = env.step(pol(env, i))
        if te or tr:
            break
    print(f"скриптовый облёт: {i+1} шагов, покрытие {info['coverage']:.4f}, "
          f"итог {'успех' if info.get('success') else 'обрыв/лимит'}")
    print("\n", reward_report(env.rew, env.dt), sep="")
