"""Трек А урока 14: среда «машинка учится парковаться» (MuJoCo + Gymnasium).

ЗАДАЧА
    Машина с передним рулевым управлением и задним приводом стоит на дороге
    носом поперёк парковки. Нужно заехать в свободное место между двумя
    занятыми, остановиться внутри рамки и простоять 0.4 с.

ЧТО ЗДЕСЬ ИСПРАВЛЕНО ОТНОСИТЕЛЬНО СТАРОЙ ВЕРСИИ УРОКА
    Разбор старой версии — .../analysis/04_lesson14_code.md, 20 дефектов,
    каждый доказан прогоном. Три блокера и как они закрыты:

    Б1. Среда была POMDP. Тяга шла через позиционные приводы и скрытый
        интегратор `_roll_target`, которого не было в наблюдении: два
        состояния с ПОБИТОВО одинаковым obs давали vx=0.0000 и vx=0.2773
        (§1.1). Здесь приводы колёс — velocity, команда есть сама скорость
        колеса, интегратора нет. Плюс в наблюдение добавлены `wheel_v`
        (скорость задних колёс) и `steer_rate`: состояние обоих приводов
        теперь наблюдаемо. Доказательство — `probe.py`, проба «двойник».

    Б2. gamma=0.99 при 100 Гц давала эффективный горизонт
        dt/(1-gamma) = 0.01/0.01 = 1.0 с против 6 с эпизода; терминальные
        +100 стоили в дисконтированной цели 0.38 (§2.3). Здесь FRAME_SKIP=5,
        то есть 20 Гц, dt=0.05 с, и GAMMA=0.995 -> горизонт
        0.05/0.005 = 10 с >= 6 с эпизода.

    Б3. Множества «успех» и «столкновение» пересекались на 13.9 % поз, один
        шаг мог вернуть оба флага (§3.3). Здесь ворота сужены до
        (0.30, 0.30, 0.25 рад), столкновение проверяется ДО успеха, ветки
        разведены через elif, и `probe.py` перебором доказывает, что
        пересечение пусто.

    Остальные 17 — по тексту, каждая правка помечена ссылкой на параграф
    отчёта.

ДЕЙСТВИЕ (Box, 2 числа в [-1, 1])
    a[0] -> угол руля,   a[0] * 0.5 рад
    a[1] -> скорость задних колёс, a[1] * 16.6667 рад/с = a[1] * 1.0 м/с

НАБЛЮДЕНИЕ (16 чисел, см. _observation)
    границы объявлены по ЗАМЕРУ, а не «с запасом» (§1.5)

НАГРАДА
    собирается rl_toolkit.rewards.RewardRegistry из шести именованных членов;
    каждый член снабжён полем `why`. Складывается сумма всех членов, поэтому
    дефект «reward = -30 вместо reward += -30» (§2.5) здесь невозможен
    конструктивно.

БЫСТРАЯ ПРОВЕРКА
    python car_env.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

# MUJOCO_GL обязан быть выставлен ДО import mujoco (§7: в старом уроке выбора
# бэкенда не было вообще, и render() отдавал чёрный кадр).
# glfw — рабочий бэкенд на Windows; на headless-Linux ставьте MUJOCO_GL=egl.
os.environ.setdefault("MUJOCO_GL", "glfw")

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rl_toolkit.rewards import Ctx, RewardRegistry, Term

XML_PATH = Path(__file__).resolve().parent / "car_parking.xml"

# --------------------------------------------------------------------- время
TIMESTEP = 0.01          # шаг физики, задан в car_parking.xml
FRAME_SKIP = 5           # шагов физики на одно действие -> политика 20 Гц
DT = TIMESTEP * FRAME_SKIP                    # 0.05 с
# Эпизод 9 с, а не 6 с, как было в старой версии. Причина — замер, а не вкус.
# Требуемый манёвр разобран в probe.py, проба 9: заехать на место ПЕРЕДНИМ
# ходом при замеренном радиусе поворота 1.067 м геометрически невозможно
# (дуга входит в точку (-0.37, -1.07) — за задней стеной и внутри соседнего
# места), поэтому машина обязана развернуться на дороге и сдать назад.
# Нижняя оценка пути такого манёвра: дуга 90 град (1.676 м) + задний ход
# 1.35 м = 3.03 м, реальная траектория длиннее.
# У старой версии на это было 6 с, но её машина ехала 1.348 м/с при
# заявленных 1.08 (04_lesson14_code.md §4.2), то есть бюджет пути был ~8 м.
# Здесь предел честный (замеренный пик 0.992 м/с), и чтобы бюджет пути
# остался сопоставимым, эпизод удлинён: 1.0 м/с * 9 с = 9 м.
EPISODE_SECONDS = 9.0
MAX_STEPS = int(round(EPISODE_SECONDS / DT))  # 180 шагов политики

# gamma среды. Она же обязана стоять у алгоритма и у VecNormalize, иначе
# потенциальный шейпинг перестаёт быть инвариантным (§2.2).
# Эффективный горизонт = dt/(1-gamma) = 0.05/0.005 = 10 с при эпизоде 9 с,
# то есть покрытие 1.11. У старой версии было 0.01/0.01 = 1.0 с при 6 с
# эпизода — покрытие 0.17 (§2.3).
GAMMA = 0.995

# ------------------------------------------------------------------ геометрия
SPOT = np.array([0.7, 0.0])   # центр целевого места, совпадает с рамкой в XML
TARGET_YAW = 0.0              # нос машины в сторону +x

# Габарит машины для проверки «влезает ли поза в рамку»:
#   полудлина 0.46 м — до кончика бампера (bumper_f pos 0.43 + size 0.03)
#   полуширина 0.265 м — до внешней грани колеса (pos 0.24 + size 0.025)
CAR_HALF_LEN = 0.46
CAR_HALF_WID = 0.265

# --------------------------------------------------------------- ворота успеха
# Старые ворота (0.50, 0.50, 0.70 рад) пересекались со столкновением на 13.9 %
# поз (§3.3). Новые выведены из габарита:
#   при |dyaw| <= 0.25: продольный габарит 0.46*cos + 0.265*sin = 0.511 м
#                       поперечный габарит 0.46*sin + 0.265*cos = 0.370 м
#   x машины при dx<=0.30: [0.7-0.30-0.511, 0.7+0.30+0.511] = [-0.111, 1.511]
#       грань wall_back на -0.150 -> зазор 0.039 м
#   |y| при dy<=0.30: 0.30+0.370 = 0.670, ближняя грань соседа на 0.990
#       -> зазор 0.320 м
# Полный перебор поз внутри ворот средствами MuJoCo — в probe.py.
SUCCESS_DX = 0.30
SUCCESS_DY = 0.30
SUCCESS_DYAW = 0.25            # рад = 14.3 град
SUCCESS_SPEED = 0.15           # м/с, ПОЛНАЯ скорость hypot(vx, vy), не только vx (§2.6)
SUCCESS_OMEGA = 0.40           # рад/с — старая версия не проверяла вращение вовсе
SUCCESS_HOLD = 8               # шагов = 0.4 с. За это время машина на пороговой
                               # скорости 0.15 м/с сместится на 0.06 м < 0.30 м ворот

# ------------------------------------------------------------------ пределы
STEER_MAX = 0.5                # рад, совпадает с ctrlrange рулевых приводов
# ПРЕДЕЛ СКОРОСТИ РУЛЯ. Без него действие могло за один шаг политики (0.05 с)
# перебросить руль с +0.5 на -0.5 рад: рулевой сервопривод kp=20 отрабатывает
# ступеньку за 0.06 с, то есть успевает. Такой переброс на ходу ОПРОКИДЫВАЕТ
# машину — замер build/track_a/m14_flip.py: при случайной политике со std=1.0
# кузов заваливался больше чем на 30 градусов в 58 эпизодах из 60, доезжал до
# 180 градусов (лёг на крышу) и дальше ЛЕЖАЛ до конца эпизода.
# Свип предела (m15_rate.py, 60 эпизодов случайной политики на точку;
# «опрок.» — доля эпизодов, где сработал признак «завалился»):
#   рад/с   за шаг   опрок. std=1.0   опрок. std=0.37   макс наклон   R поворота
#   100.0    5.000        93.3 %           5.0 %          58.0°        1.068 м
#     8.0    0.400         0.0 %           0.0 %          36.4°        1.066 м
#     4.0    0.200         0.0 %           0.0 %          14.5°        1.066 м
#     2.0    0.100         0.0 %           0.0 %           4.1°        1.068 м
#     0.5    0.025         0.0 %           0.0 %           0.3°        1.066 м
# Взято 2.0: опрокидываний нет с большим запасом (4.1° против порога 45°),
# тогда как при 8.0 наклон доходит до 36.4° — почти до порога. И при этом
# МАНЁВРЕННОСТЬ НЕ ПОСТРАДАЛА: установившийся радиус поворота при полном руле
# одинаков (1.066..1.068 м) на всём диапазоне — предел режет только рывок,
# а не саму способность поворачивать.
# 2.0 рад/с = полный размах руля (1.0 рад) за 0.5 с — примерно так же быстро
# крутит руль человек. За шаг политики руль успевает на 0.1 рад.
# Скрытого состояния предел НЕ добавляет: он отсчитывается от ФАКТИЧЕСКОГО
# угла руля qpos, а тот лежит в наблюдении (obs[7]).
STEER_RATE_MAX = 2.0           # рад/с
# Порог «завалился»: проекция оси Z кузова на мировую вертикаль.
# cos(45 град) = 0.707. Меньше — машина на боку или на крыше; из такого
# состояния она уже не выедет, и эпизод обязан оборваться.
TIP_COS_MIN = 0.707
WHEEL_W_MAX = 16.6667          # рад/с, совпадает с ctrlrange velocity-приводов
WHEEL_RADIUS = 0.06            # м, size колеса-капсулы
V_MAX = WHEEL_W_MAX * WHEEL_RADIUS   # 1.0 м/с; замеренный пик кузова 0.992 м/с

# ------------------------------------------------------------ границы площадки
# x > 6.75: дальняя стена на 6.80. x < -0.30: за линией задней стены (-0.15),
# но стена короткая (|y| <= 1.4), поэтому мимо неё уехать назад можно.
OOB_X_MIN, OOB_X_MAX = -0.30, 6.75
OOB_Y_ABS = 3.35

# ------------------------------------------------------------------- старт
# spread=0 — лёгкий старт (ближе и ровнее), spread=1 — честный.
# Оценка ВСЕГДА идёт при spread=1.0 и in_spot_start_prob=0.0.
START_EASY = dict(x=(1.50, 1.70), y=(-0.20, 0.20), yaw=0.10)
START_HARD = dict(x=(1.90, 2.40), y=(-0.80, 0.80), yaw=0.25)
IN_SPOT_START_PROB = 0.0       # по умолчанию трюка НЕТ; его включает куррикулум

# ------------------------------------------------------------------ награда
W_DIST = 2.0                   # вес расстояния в потенциале, награда/м
HEAD_NEAR = 2.0                # см. _heading_weight
HEAD_SOFT = 0.5
# STEP_COST откалиброван ЗАМЕРОМ, а не на глаз (build/track_a/m7_idle.py).
# Потенциальный шейпинг с gamma даёт неподвижной машине ставку
# (gamma-1)*Ф(s) > 0, потому что Ф <= 0. Замер:
#     dist=0.30, dyaw=0.10 -> +0.085 награды/с
#     dist=1.50, dyaw=1.57 -> +0.457 награды/с
#     dist=2.50, dyaw=1.57 -> +0.605 награды/с
# При STEP_COST=0.02 (то есть 0.4 награды/с) пассивная политика получала
# ЗА ЭПИЗОД +2.738 шейпинга против -2.400 времени, итого +0.338:
# стоять на месте было ВЫГОДНО. STEP_COST=0.05 -> 1.0 награды/с перекрывает
# ставку неподвижности на всём рабочем диапазоне; пассивный возврат
# становится -3.26 за эпизод (перепроверено probe.py, проба 7).
STEP_COST = 0.05               # за шаг = 1.0 награды/с при dt=0.05
# SETTLE_W=0.08 -> 1.6 награды/с при полной остановке в месте. Это ВЫШЕ платы
# за время (1.0/с), поэтому «стою в месте» строго лучше, чем «стою где угодно»;
# за весь эпизод член не может дать больше +9.6 против +100 за парковку.
SETTLE_W = 0.08
PARK_BONUS = 100.0
CRASH_PENALTY = -30.0

# Геомы препятствий и геомы машины. Контакт засчитывается ТОЛЬКО когда одна
# сторона — машина, а другая — препятствие: иначе контакт «сосед — пол»
# считался бы столкновением (§4.3 предвычисляет id, чтобы не звать mj_id2name
# 16 раз на шаг — на это уходило 66 % бюджета шага).
OBSTACLE_GEOMS = (
    "wall_back", "wall_left", "wall_right", "wall_far",
    "parked_l_geom", "parked_r_geom", "parked_l_cabin", "parked_r_cabin",
)
CAR_GEOMS = (
    "chassis", "cabin", "bumper_f", "bumper_b",
    "wheel_fr_geom", "wheel_fl_geom", "wheel_rr_geom", "wheel_rl_geom",
)

PARKED_L = np.array([0.7, -1.2])
PARKED_R = np.array([0.7, 1.2])


def _wrap(a: float) -> float:
    """Угол в (-pi, pi]."""
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _heading_weight(dist: float) -> float:
    """Вес ошибки курса в потенциале — МОНОТОННО убывает по расстоянию.

    Старая формула `2.0 * min(1.0, 1.5 / max(dist, 0.3))` была численно
    КОНСТАНТОЙ 2.0 на всём рабочем диапазоне dist <= 1.5 (§3.1: клампа
    доказуемо мёртвая, вес меняется только при dist > 1.5, а туда попадают
    лишь первые доли секунды эпизода). Здесь вес реально меняется:
        dist=0.0 -> 4.000   dist=0.5 -> 2.000   dist=1.0 -> 1.333
        dist=1.5 -> 1.000   dist=1.9 -> 0.833
    Таблицу печатает probe.py, вердикт о наличии градиента — gradient_report.
    """
    return HEAD_NEAR / (HEAD_SOFT + dist)


class CarParkingEnv(gym.Env):
    """Парковка задним/передним ходом. Контракт Gymnasium + контракт rl_toolkit."""

    # render_fps = 1/DT = 20: у старой версии стояло 50 при физике 100 Гц,
    # и собранное по metadata видео шло вдвое медленнее реального (§1.4).
    metadata = {"render_modes": ["rgb_array"], "render_fps": int(round(1.0 / DT))}

    def __init__(
        self,
        render_mode: str | None = None,
        in_spot_start_prob: float = IN_SPOT_START_PROB,
        start_spread: float = 1.0,
        gamma: float = GAMMA,
        render_size: tuple[int, int] = (720, 960),   # (height, width)
    ) -> None:
        super().__init__()
        self.render_mode = render_mode
        self.in_spot_start_prob = float(in_spot_start_prob)
        self.start_spread = float(start_spread)
        self.gamma = float(gamma)
        self._render_hw = (int(render_size[0]), int(render_size[1]))

        self.model = mujoco.MjModel.from_xml_path(str(XML_PATH))
        self.data = mujoco.MjData(self.model)
        self._renderer: mujoco.Renderer | None = None

        # Сверка XML и Python: константы времени обязаны совпадать, иначе все
        # «в секунду» врут молча.
        if abs(self.model.opt.timestep - TIMESTEP) > 1e-12:
            raise ValueError(
                f"timestep в XML {self.model.opt.timestep} != TIMESTEP {TIMESTEP}"
            )

        # -- предвычисленные id (§4.3: mj_id2name на каждый контакт съедал 66 %) --
        g = lambda n: mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, n)
        self._obstacle_ids = frozenset(g(n) for n in OBSTACLE_GEOMS)
        self._car_ids = frozenset(g(n) for n in CAR_GEOMS)
        if -1 in self._obstacle_ids | self._car_ids:
            raise ValueError("в XML нет какого-то из перечисленных геомов")

        j = lambda n: mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, n)
        self._qadr_steer = (self.model.jnt_qposadr[j("steer_fl")],
                            self.model.jnt_qposadr[j("steer_fr")])
        self._dadr_steer = (self.model.jnt_dofadr[j("steer_fl")],
                            self.model.jnt_dofadr[j("steer_fr")])
        self._dadr_roll = (self.model.jnt_dofadr[j("roll_rl")],
                           self.model.jnt_dofadr[j("roll_rr")])

        # -- пространства ---------------------------------------------------
        # Границы выведены из ГЕОМЕТРИИ площадки, а не поставлены «с запасом»
        # (§1.5: у старой версии dist объявлялся до 10 м при физическом
        # максимуме 7.6 м, а x — до 8.0 при пределе выезда 6.75).
        #   площадка: x in [-0.30, 6.75], |y| <= 3.35; место в (0.7, 0)
        #   -> |dx| <= 6.05, |dy| <= 3.35, dist <= hypot(6.05, 3.35) = 6.92
        #   -> до соседа: hypot(6.05, 4.55) = 7.57
        # Скорости: тяга даёт 1.0 м/с, но при ударе кузов отбрасывает — замер
        # 4000 шагов случайной политики дал пик 1.59 м/с, поэтому предел 2.5.
        arena_diag = 6.92
        obs_low = np.array(
            [-arena_diag, -arena_diag, -1.0, -1.0,   # dx_body, dy_body, sin, cos
             -2.5, -2.5, -4.0,                       # vx, vy, omega
             -0.6, -12.0, -1.2,                      # steer, steer_rate, wheel_v
             0.0, OOB_X_MIN, -OOB_Y_ABS,             # dist, x, y
             0.0, 0.0,                               # d_left, d_right
             0.0],                                   # hold_progress
            dtype=np.float32,
        )
        obs_high = np.array(
            [arena_diag, arena_diag, 1.0, 1.0,
             2.5, 2.5, 4.0,
             0.6, 12.0, 1.2,
             arena_diag, OOB_X_MAX, OOB_Y_ABS,
             7.6, 7.6,
             1.0],
            dtype=np.float32,
        )
        self.observation_space = spaces.Box(low=obs_low, high=obs_high, dtype=np.float32)
        self.action_space = spaces.Box(
            low=np.array([-1.0, -1.0], dtype=np.float32),
            high=np.array([1.0, 1.0], dtype=np.float32),
            dtype=np.float32,
        )

        self.rewards = self._build_rewards()

        self._step_count = 0
        self._hold = 0
        self._prev_phi = 0.0
        self._started_in_spot = False
        self._trajectory: list[np.ndarray] = []

    # ------------------------------------------------------------- награда
    def _build_rewards(self) -> RewardRegistry:
        """Шесть именованных членов. Каждый — чистая функция от Ctx.

        Чистота обязательна: только тогда diagnostics.sweep_term может
        подсунуть члену синтетическое состояние и проверить, есть ли у него
        градиент, ДО обучения.
        """
        g = self.gamma
        return (
            RewardRegistry()
            .add(Term(
                "progress",
                fn=lambda c: g * c["phi"] - c["phi_prev"],
                weight=1.0,
                unit="награда",
                why=(
                    "Потенциальный шейпинг по Ng/Harada/Russell: F = gamma*Ф(s') - Ф(s). "
                    "Именно с gamma. Старая версия писала Ф(s')-Ф(s) без gamma, и разница "
                    "(1-gamma)*Ф(s') давала СКРЫТЫЙ штраф -23.3 за эпизод — в 4.5 раза "
                    "больше явного штрафа за время (04_lesson14_code.md §2.2)."
                ),
            ))
            .add(Term(
                "time",
                fn=lambda c: -1.0,
                weight=STEP_COST,
                unit="шаг",
                why=(
                    "Плата за время. Её величина не выбрана на глаз, а откалибрована "
                    "по ставке неподвижности: шейпинг с gamma платит стоящей машине "
                    "(gamma-1)*Ф(s) = до +0.605 награды/с, и при плате 0.4/с пассивная "
                    "политика получала за эпизод +0.338 — стоять было ВЫГОДНО. "
                    "0.05 за шаг = 1.0 награды/с перекрывает это на всём диапазоне."
                ),
            ))
            .add(Term(
                "settle",
                fn=lambda c: 1.0 if c["in_gate"] else 0.0,
                gate=lambda c: max(0.0, 1.0 - c["speed"] / SUCCESS_SPEED),
                weight=SETTLE_W,
                unit="доля",
                why=(
                    "Единственный член, который платит за ОСТАНОВКУ в месте. Гейт "
                    "линейно гасит выплату по полной скорости: стоящая машина получает "
                    "весь член, проезжающая насквозь — ноль. Старые ворота успеха "
                    "смотрели только на продольную скорость, и машина, скользящая боком "
                    "на 2.5 м/с, засчитывалась остановившейся (§2.6)."
                ),
            ))
            .add(Term(
                "park",
                fn=lambda c: 1.0 if c["success"] else 0.0,
                weight=PARK_BONUS,
                unit="событие",
                # Порог достижимости для diagnostics.reachability: во сколько раз
                # путь, который машина успевает пройти за эпизод, покрывает путь
                # от старта до места. Ниже 1.0 — цель физически недостижима,
                # и бонус превращается в постоянно недоплачиваемый штраф.
                threshold=1.0,
                why=(
                    "Собственно цель. При dt=0.05 и gamma=0.995 бонус, полученный на "
                    "шаге 60, стоит в дисконтированной цели 100*0.995^60 = 74.0. "
                    "У старой версии (100 Гц, gamma=0.99, медианный успех на шаге 460) "
                    "тот же бонус стоил 100*0.99^460 = 0.98 (проба 4 в probe.py)."
                ),
            ))
            .add(Term(
                "crash",
                fn=lambda c: 1.0 if c["collision"] else 0.0,
                weight=CRASH_PENALTY,
                unit="событие",
                why=(
                    "Касание стены или соседа. Член СКЛАДЫВАЕТСЯ с остальными, а не "
                    "затирает их: в старой версии стояло `reward = -30.0` (присваивание), "
                    "и шаг «почти припарковался, но задел» платил ровно столько же, "
                    "сколько «влетел в стену на пятом шаге» (§2.5)."
                ),
            ))
            .add(Term(
                "offroad",
                fn=lambda c: 1.0 if c["oob"] else 0.0,
                weight=CRASH_PENALTY,
                unit="событие",
                why="Выезд за площадку. Тот же вес, что у столкновения: исход тот же.",
            ))
            .add(Term(
                "tipped",
                fn=lambda c: 1.0 if c["tipped"] else 0.0,
                weight=CRASH_PENALTY,
                unit="событие",
                why=(
                    "Машина завалилась на бок или на крышу. Это ПОГЛОЩАЮЩЕЕ состояние: "
                    "выехать из него нельзя. Пока эпизод его не обрывал, машина лежала "
                    "вверх дном оставшиеся 5 с из 6 (замер m14_flip.py), и критик был "
                    "обязан моделировать эту бессмысленную половину эпизода. "
                    "Любое физически необратимое состояние обязано терминировать."
                ),
            ))
        )

    # ------------------------------------------------------------------ api
    def reset(self, *, seed: int | None = None, options: dict | None = None):
        # super().reset(seed=...) сидирует self.np_random — и мы им ПОЛЬЗУЕМСЯ.
        # Старая версия заводила отдельный self._rng и сидировала его заново на
        # каждый reset(seed=N), из-за чего reset(seed=42) в цикле давал один и
        # тот же эпизод бесконечно (§1.2).
        super().reset(seed=seed)
        if seed is not None:
            # gymnasium не сидирует action_space сам — из-за этого картинка
            # «случайная политика» в старом уроке была невоспроизводима (§6.5).
            self.action_space.seed(int(seed))

        # mj_resetData, а не ручное обнуление qpos/qvel: иначе через эпизоды
        # переносятся data.time и qacc_warmstart (§1.7).
        mujoco.mj_resetData(self.model, self.data)

        self._started_in_spot = bool(self.np_random.random() < self.in_spot_start_prob)
        if self._started_in_spot:
            x = SPOT[0] + self.np_random.uniform(-0.10, 0.10)
            y = SPOT[1] + self.np_random.uniform(-0.10, 0.10)
            yaw = TARGET_YAW + self.np_random.uniform(-0.10, 0.10)
        else:
            s = float(np.clip(self.start_spread, 0.0, 1.0))
            lerp = lambda a, b: a + (b - a) * s
            x0 = lerp(START_EASY["x"][0], START_HARD["x"][0])
            x1 = lerp(START_EASY["x"][1], START_HARD["x"][1])
            y1 = lerp(START_EASY["y"][1], START_HARD["y"][1])
            dyaw = lerp(START_EASY["yaw"], START_HARD["yaw"])
            x = self.np_random.uniform(x0, x1)
            y = self.np_random.uniform(-y1, y1)
            yaw = math.pi / 2.0 + self.np_random.uniform(-dyaw, dyaw)

        self._set_pose(x, y, yaw)
        mujoco.mj_forward(self.model, self.data)

        self._step_count = 0
        self._hold = 0
        self._trajectory = [np.array([x, y, yaw])]
        self.rewards.reset()
        self._prev_phi = self._potential()
        info = {"curriculum": self._started_in_spot}
        return self._observation(), info

    def step(self, action):
        a = np.asarray(action, dtype=np.float64).reshape(2)
        steer_goal = float(np.clip(a[0], -1.0, 1.0)) * STEER_MAX
        # Предел скорости руля. Отсчитывается от ФАКТИЧЕСКОГО угла, который
        # лежит в наблюдении, поэтому скрытого состояния не появляется.
        steer_now = self._steer_angle()
        max_delta = STEER_RATE_MAX * DT
        steer_cmd = float(np.clip(steer_goal, steer_now - max_delta, steer_now + max_delta))
        wheel_cmd = float(np.clip(a[1], -1.0, 1.0)) * WHEEL_W_MAX
        # Порядок ctrl совпадает с порядком <actuator> в XML:
        # steer_l, steer_r, drive_l, drive_r.
        self.data.ctrl[:] = [steer_cmd, steer_cmd, wheel_cmd, wheel_cmd]

        # FRAME_SKIP шагов физики на одно действие: 20 Гц политики при 100 Гц
        # физики. Именно эта строка чинит блокер про gamma (§2.3, §4.5).
        for _ in range(FRAME_SKIP):
            mujoco.mj_step(self.model, self.data)
        self._step_count += 1

        x, y, yaw = self._pose()
        self._trajectory.append(np.array([x, y, yaw]))

        dx = x - SPOT[0]
        dy = y - SPOT[1]
        dyaw = abs(_wrap(yaw - TARGET_YAW))
        vx, vy = self._body_velocity()
        speed = math.hypot(vx, vy)          # ПОЛНАЯ скорость, не |vx| (§2.6)
        omega = abs(float(self.data.qvel[5]))
        dist = math.hypot(dx, dy)

        collision = self._collision()
        oob = not (OOB_X_MIN < x < OOB_X_MAX and abs(y) < OOB_Y_ABS)
        tipped = self._up_z() < TIP_COS_MIN

        in_gate = (abs(dx) < SUCCESS_DX and abs(dy) < SUCCESS_DY and dyaw < SUCCESS_DYAW)
        parked = in_gate and speed < SUCCESS_SPEED and omega < SUCCESS_OMEGA

        # ПОРЯДОК ВЕТОК — это и есть починка блокера Б3 (§3.3):
        # неудачные исходы проверяются ПЕРВЫМИ и исключают успех на том же шаге.
        success = False
        terminated = False
        if collision or oob or tipped:
            terminated = True
            self._hold = 0
        else:
            if parked:
                self._hold += 1
                if self._hold >= SUCCESS_HOLD:
                    success = True
                    terminated = True
            else:
                self._hold = 0

        phi = self._potential()
        ctx = Ctx(
            DT, t=self._step_count * DT,
            dist=dist, dyaw=dyaw, speed=speed, omega=omega,
            phi=phi, phi_prev=self._prev_phi,
            in_gate=in_gate, success=success, collision=collision, oob=oob,
            tipped=tipped,
            steer=self._steer_angle(), wheel_v=self._wheel_speed(),
        )
        self._prev_phi = phi
        reward, terms = self.rewards(ctx)

        truncated = bool(self._step_count >= MAX_STEPS and not terminated)

        info = {
            "terms": terms,                 # контракт rl_toolkit
            "success": success,
            "collision": bool(collision),
            "out_of_bounds": bool(oob),
            "tipped": bool(tipped),
            "curriculum": self._started_in_spot,
            "dist": dist,
            "dyaw": dyaw,
            "speed": speed,
        }
        if terminated or truncated:
            info["reward_terms_episode"] = self.rewards.episode_summary()
        return self._observation(), float(reward), terminated, truncated, info

    def close(self) -> None:
        """Освобождает GL-контекст рендерера.

        Старая версия close() не определяла вовсе, и mujoco.Renderer тёк при
        каждом создании среды (§1.3).
        """
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def render(self):
        """Кадр rgb_array с камеры «top». Уважает render_mode."""
        if self.render_mode != "rgb_array":
            return None
        if self._renderer is None:
            h, w = self._render_hw
            # Сигнатура Renderer(model, height, width) — старая версия писала
            # Renderer(model, 960, 720) и получала портрет 720x960 (§7).
            self._renderer = mujoco.Renderer(self.model, height=h, width=w)
        self._renderer.update_scene(self.data, camera="top")
        return self._renderer.render()

    # ------------------------------------------------- контракт rl_toolkit
    @property
    def dt(self) -> float:
        """Шаг ПОЛИТИКИ в секундах. Без него все «в секунду» станут «за шаг»."""
        return DT

    @property
    def max_steps(self) -> int:
        return MAX_STEPS

    def set_in_spot_start_prob(self, value: float) -> None:
        """Рампа куррикулума: доля эпизодов со стартом уже на месте.

        Применяется со следующего reset(). Трюк учебный и обязан УГАСАТЬ:
        в старом уроке он стоял константой 0.2, и ровно 20 % эпизодов были
        халявой на 164.92 — кривая обучения показывала 81 при честных 60 (§3.4).
        """
        self.in_spot_start_prob = float(np.clip(value, 0.0, 1.0))

    def set_start_spread(self, value: float) -> None:
        """Рампа куррикулума: 0 — близкий ровный старт, 1 — честный разброс."""
        self.start_spread = float(np.clip(value, 0.0, 1.0))

    def set_probe_state(self, state: dict) -> None:
        """Поставить машину в заданную позу — только для probes.probe_termination.

        Ключи: x, y, yaw (обяз.), v (скорость ВДОЛЬ корпуса, м/с),
        v_lat (скорость ПОПЕРЁК корпуса, м/с), omega (рад/с),
        wheel_w (скорость колёс, рад/с), steer (угол руля, рад),
        hold (сколько шагов выдержки уже набрано).
        """
        x = float(state["x"])
        y = float(state["y"])
        yaw = float(state["yaw"])
        self._set_pose(x, y, yaw)
        v = float(state.get("v", 0.0))
        v_lat = float(state.get("v_lat", 0.0))
        c, s = math.cos(yaw), math.sin(yaw)
        self.data.qvel[0] = v * c - v_lat * s
        self.data.qvel[1] = v * s + v_lat * c
        self.data.qvel[5] = float(state.get("omega", 0.0))
        w = float(state.get("wheel_w", v / WHEEL_RADIUS if v else 0.0))
        for adr in self._dadr_roll:
            self.data.qvel[adr] = w
        st = float(state.get("steer", 0.0))
        for adr in self._qadr_steer:
            self.data.qpos[adr] = st
        mujoco.mj_forward(self.model, self.data)
        self._hold = int(state.get("hold", 0))
        self._prev_phi = self._potential()

    # --------------------------------------------------------------- состояние
    def _set_pose(self, x: float, y: float, yaw: float) -> None:
        self.data.qpos[0:3] = [x, y, 0.06]
        self.data.qpos[3:7] = [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]

    def _pose(self) -> tuple[float, float, float]:
        q = self.data.qpos[3:7]
        yaw = math.atan2(2.0 * (q[0] * q[3] + q[1] * q[2]),
                         1.0 - 2.0 * (q[2] ** 2 + q[3] ** 2))
        return float(self.data.qpos[0]), float(self.data.qpos[1]), yaw

    def _up_z(self) -> float:
        """Проекция оси Z кузова на мировую вертикаль: 1 — ровно, -1 — на крыше."""
        q = self.data.qpos[3:7]
        return float(1.0 - 2.0 * (q[1] * q[1] + q[2] * q[2]))

    def _body_velocity(self) -> tuple[float, float]:
        vx_w, vy_w = float(self.data.qvel[0]), float(self.data.qvel[1])
        yaw = self._pose()[2]
        c, s = math.cos(yaw), math.sin(yaw)
        return c * vx_w + s * vy_w, -s * vx_w + c * vy_w

    def _steer_angle(self) -> float:
        return float((self.data.qpos[self._qadr_steer[0]]
                      + self.data.qpos[self._qadr_steer[1]]) / 2.0)

    def _steer_rate(self) -> float:
        return float((self.data.qvel[self._dadr_steer[0]]
                      + self.data.qvel[self._dadr_steer[1]]) / 2.0)

    def _wheel_speed(self) -> float:
        """Линейная скорость обода задних колёс, м/с. Состояние тягового привода."""
        w = (self.data.qvel[self._dadr_roll[0]] + self.data.qvel[self._dadr_roll[1]]) / 2.0
        return float(w) * WHEEL_RADIUS

    def _observation(self) -> np.ndarray:
        """16 чисел.

        Три добавлены против старой версии и закрывают блокер Б1:
        `steer_rate` и `wheel_v` — состояние приводов; без них политика не
        могла предсказать, поедет ли машина от команды «ноль» (§1.1).

        Шестнадцатое — `hold_progress` = _hold / SUCCESS_HOLD. Счётчик
        удержания в воротах решает, оборвётся ли эпизод успехом и придёт ли
        терминальная награда, но сам по себе НЕ выводится из позы: два
        состояния с побитово одинаковыми первыми 15 числами и одним и тем же
        действием давали награду +0.030 и +100.030. То есть это было ровно
        то скрытое состояние, про которое глава 02 и написана. Держать такой
        счётчик вне наблюдения нельзя — среда обязана быть марковской
        целиком, а не в той части, которую легко заметить.
        """
        x, y, yaw = self._pose()
        dx, dy = SPOT - np.array([x, y])
        c, s = math.cos(yaw), math.sin(yaw)
        dyaw = _wrap(yaw - TARGET_YAW)
        vx, vy = self._body_velocity()
        return np.array(
            [c * dx + s * dy,                       # 0  dx_body
             -s * dx + c * dy,                      # 1  dy_body
             math.sin(dyaw), math.cos(dyaw),        # 2,3 ошибка курса
             vx, vy,                                # 4,5 скорость в раме кузова
             float(self.data.qvel[5]),              # 6  omega
             self._steer_angle(),                   # 7  угол руля
             self._steer_rate(),                    # 8  скорость руля  <- НОВОЕ
             self._wheel_speed(),                   # 9  скорость колёс <- НОВОЕ
             math.hypot(dx, dy),                    # 10 расстояние до места
             x, y,                                  # 11,12 положение в мире
             float(np.linalg.norm([x - PARKED_L[0], y - PARKED_L[1]])),   # 13
             float(np.linalg.norm([x - PARKED_R[0], y - PARKED_R[1]])),   # 14
             self._hold / SUCCESS_HOLD],            # 15 прогресс удержания
            dtype=np.float32,
        )

    def _potential(self) -> float:
        """Ф(s) = -(W_DIST*dist + heading_weight(dist)*|dyaw|). Всегда <= 0."""
        x, y, yaw = self._pose()
        dist = math.hypot(x - SPOT[0], y - SPOT[1])
        dyaw = abs(_wrap(yaw - TARGET_YAW))
        return -(W_DIST * dist + _heading_weight(dist) * dyaw)

    def _collision(self) -> bool:
        """Есть ли контакт «машина — препятствие».

        Сравниваются ЦЕЛЫЕ id, предвычисленные в __init__. Старая версия звала
        mujoco.mj_id2name по 16 раз на шаг, и это съедало 66 % бюджета шага
        (§4.3).
        """
        car, obst = self._car_ids, self._obstacle_ids
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            g1, g2 = int(c.geom1), int(c.geom2)
            if (g1 in car and g2 in obst) or (g2 in car and g1 in obst):
                return True
        return False


def main() -> None:
    """Смоук: контракт, цена шага, пассивный эпизод."""
    sys.stdout.reconfigure(encoding="utf-8")
    env = CarParkingEnv()
    obs, info = env.reset(seed=0)
    print(f"наблюдение: {obs.shape} {obs.dtype}")
    print(f"действие:   {env.action_space}")
    print(f"dt = {env.dt} с ({1/env.dt:.0f} Гц), эпизод {MAX_STEPS} шагов = "
          f"{MAX_STEPS*env.dt:.1f} с, gamma={env.gamma} -> горизонт "
          f"{env.dt/(1-env.gamma):.1f} с")
    total = 0.0
    for k in range(MAX_STEPS):
        obs, r, term, trunc, info = env.step(np.array([0.3, 1.0], dtype=np.float32))
        total += r
        if term or trunc:
            print(f"эпизод оборвался на шаге {k+1}: terminated={term} truncated={trunc} "
                  f"info={ {kk: vv for kk, vv in info.items() if kk not in ('terms','reward_terms_episode')} }")
            break
    print(f"суммарная награда при постоянном действии [0.3, 1.0]: {total:.3f}")
    env.close()


if __name__ == "__main__":
    main()
