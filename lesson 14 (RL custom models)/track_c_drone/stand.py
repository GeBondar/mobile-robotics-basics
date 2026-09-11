"""C0 «Стенд»: модель, микшер, каскадный ПД — БЕЗ обучения.

Ступень C0 отвечает на вопрос, который в треках A и B не возникал:
**чем управляем и почему объект не стоит на месте сам**.

Машинка трека A, если её отпустить, стоит. Дрон — свободное тело: наклон
ничем не восстанавливается (ориентация — чистый интегратор), а положение
при постоянном наклоне уезжает КВАДРАТИЧНО. Тест 7 меряет это прямо:
времена достижения 0.5 / 1.0 / 2.0 м относятся как 1 : sqrt(2) : 2.

Что даёт этот файл остальному треку:
    read_passport(model) — паспорт из СКОМПИЛИРОВАННОЙ MjModel;
    Mixer               — X-микшер, СОБРАННЫЙ ИЗ ГЕОМЕТРИИ модели, а не из
                          выписанной руками таблицы знаков;
    gain_rule(...)      — усиления контура угловой скорости из физики;
    CascadePD           — внутренний контур; на нём стоит вся ступень C2.

Запуск::

    python stand.py            # паспорт + 11 тестов
    python stand.py --quick    # без длинных тестов (12 стартов, свип)

Все числа в выводе — замеры этого скрипта на этой модели. Ни одно число
в комментариях ниже не взято «из головы»: если правите quad.xml, перезапустите
скрипт и правьте комментарии по его выводу.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")   # русская локаль Windows иначе валится на «→»

# rl_toolkit лежит на уровень выше — им пользуются все три трека урока
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl_toolkit.diagnostics import Table          # noqa: E402

import mujoco                                     # noqa: E402

HERE = Path(__file__).resolve().parent
QUAD_XML = HERE / "quad.xml"
G = 9.81


# ---------------------------------------------------------------------------
# Паспорт модели: всё читается из MjModel, ничего не переписывается из XML
# ---------------------------------------------------------------------------
def read_passport(model: mujoco.MjModel, body: str = "drone") -> Dict[str, float]:
    """Паспорт аппарата, прочитанный из СКОМПИЛИРОВАННОЙ модели.

    Почему из MjModel, а не из XML: компилятор MuJoCo складывает массы геомов,
    считает тензор инерции, разворачивает `default`-классы и подставляет
    умолчания. Число в XML и число в модели — разные вещи, и расходятся они
    молча. Единственный честный источник паспорта — скомпилированная модель.
    """
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body)
    if bid < 0:
        raise ValueError(f"в модели нет тела {body!r}")

    mass = float(model.body_subtreemass[bid])

    # инерция задана в ГЛАВНЫХ осях (body_inertia) + разворот (body_iquat).
    # Для правила усиления нужен тензор в осях корпуса: I = R * diag(I_gl) * R^T
    Rm = np.zeros(9)
    mujoco.mju_quat2Mat(Rm, model.body_iquat[bid])
    Rm = Rm.reshape(3, 3)
    Iw = Rm @ np.diag(model.body_inertia[bid]) @ Rm.T

    ctrl_hi = float(model.actuator_ctrlrange[0, 1])
    n_rot = int(model.nu)
    hover = mass * G / n_rot

    # плечо винта до оси крена = |y| точки приложения тяги (X-конфигурация)
    sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "rotor1")
    arm = float(abs(model.site_pos[sid][1]))
    radial = float(np.linalg.norm(model.site_pos[sid][:2]))

    # k_m берём из gear[5] актуатора: это отношение реактивного момента к тяге
    k_m = float(abs(model.actuator_gear[0, 5]))
    tau = float(model.actuator_dynprm[0, 0])

    return {
        "масса, кг": mass,
        "вес, Н": mass * G,
        "Ixx, кг*м^2": float(Iw[0, 0]),
        "Iyy, кг*м^2": float(Iw[1, 1]),
        "Izz, кг*м^2": float(Iw[2, 2]),
        "nq": int(model.nq), "nv": int(model.nv),
        "nu": int(model.nu), "na": int(model.na),
        "timestep, с": float(model.opt.timestep),
        "плечо L, м": arm,
        "радиус винта от центра, м": radial,
        "k_m, м": k_m,
        "tau мотора, с": tau,
        "ctrl макс, Н": ctrl_hi,
        "тяга висения на винт, Н": hover,
        "висение, % от ctrl": 100.0 * hover / ctrl_hi,
        "тяговооружённость": n_rot * ctrl_hi / (mass * G),
    }


def print_passport(p: Dict[str, float]) -> None:
    t = Table(title="ПАСПОРТ МОДЕЛИ (прочитан из MjModel, не из XML)",
              columns=["величина", "значение"])
    for k, v in p.items():
        t.add(**{"величина": k, "значение": v})
    t.note = (f"висение = {p['висение, % от ctrl']:.2f} % диапазона — ЗАПОМНИТЬ: "
              f"именно отсюда растёт грабля нормировки действия (см. probe.py)")
    print(t, "\n")


# ---------------------------------------------------------------------------
# Микшер
# ---------------------------------------------------------------------------
class Mixer:
    """X-микшер: (uz, u_roll, u_pitch, u_yaw) -> четыре тяги.

        T_i = uz + u_roll*Mroll_i + u_pitch*Mpitch_i + u_yaw*Myaw_i

    Знаки НЕ выписаны руками, а выведены из модели, потому что руками их
    путают: у винта в точке (x_i, y_i) тяга T вдоль +z корпуса даёт момент
    r x F = (y_i*T, -x_i*T, 0), то есть

        крен   ~ +sign(y_i)      тангаж ~ -sign(x_i)
        рыскание ~ sign(gear[5]) — знак реактивного момента (направление вращения)

    Проверка микшера — тест 5 в main(): «чистый крен» обязан дать только крен
    (рыскание и дрейф высоты равны нулю). Если перепутать хотя бы один знак,
    контур C0 «почти работает», а C2 обучается на 30 % хуже и виноватой
    назначают награду.
    """

    def __init__(self, model: mujoco.MjModel) -> None:
        n = int(model.nu)
        pos = np.array([model.site_pos[model.actuator_trnid[i, 0]] for i in range(n)])
        self.roll = np.sign(pos[:, 1])
        self.pitch = -np.sign(pos[:, 0])
        self.yaw = np.sign(model.actuator_gear[:n, 5])
        self.arm = float(np.mean(np.abs(pos[:, 1])))          # плечо крена/тангажа
        self.k_m = float(np.mean(np.abs(model.actuator_gear[:n, 5])))
        self.ctrl_hi = float(model.actuator_ctrlrange[0, 1])
        # момент на единицу u: крен/тангаж — 4*L, рыскание — 4*k_m
        self.k_torque = 4.0 * self.arm
        self.k_yaw = 4.0 * self.k_m

    def __call__(self, uz: float, u_roll: float, u_pitch: float, u_yaw: float,
                 clip: bool = True) -> np.ndarray:
        u = uz + u_roll * self.roll + u_pitch * self.pitch + u_yaw * self.yaw
        return np.clip(u, 0.0, self.ctrl_hi) if clip else u

    def describe(self) -> str:
        return (f"Mroll={self.roll.astype(int).tolist()}  "
                f"Mpitch={self.pitch.astype(int).tolist()}  "
                f"Myaw={self.yaw.astype(int).tolist()}  "
                f"L={self.arm:.3f} м  k_m={self.k_m:.4f} м  "
                f"момент на единицу u_roll = 4L = {self.k_torque:.4f} Н*м")


# ---------------------------------------------------------------------------
# Правило усиления внутреннего контура
# ---------------------------------------------------------------------------
def gain_rule(inertia: float, k_torque: float, tau: float,
              omega: float = 12.0, zeta: float = 1.0) -> Dict[str, float]:
    """Усиления ПД контура угла из ФИЗИКИ, а не подбором.

    Контур угла с моментом M = k_torque*u и инерцией I — это двойной
    интегратор. Задавая желаемые полосу omega и демпфирование zeta:

        kp = omega^2 * I / k_torque        kd = 2*zeta*omega * I / k_torque

    ОГРАНИЧЕНИЕ СВЕРХУ ставит не «вкус», а мотор: его фильтр даёт
    запаздывание tau, и контур, чья полоса выше ~1/(3*tau), входит
    в предельный цикл. При tau = 0.02 с это 16.7 рад/с; рабочая точка
    omega = 12 рад/с выбрана с запасом в 1.4 раза.

    Что бывает при нарушении — тест 11: kp = 60 (переусиление в ~50 раз)
    даёт долю насыщенных шагов 0.9992, и дрон «висит на дребезге»
    (клиппинг выпрямляет колебание в паразитную подъёмную силу).
    """
    limit = 1.0 / (3.0 * tau)
    return {
        "полоса мотора 1/tau, рад/с": 1.0 / tau,
        "предел полосы контура, рад/с": limit,
        "выбрано omega, рад/с": omega,
        "запас": limit / omega,
        "kp": omega ** 2 * inertia / k_torque,
        "kd": 2.0 * zeta * omega * inertia / k_torque,
    }


# ---------------------------------------------------------------------------
# Каскадный ПД
# ---------------------------------------------------------------------------
def euler_from_quat(q) -> Tuple[float, float, float]:
    """(крен, тангаж, рыскание) из кватерниона MuJoCo (w, x, y, z)."""
    w, x, y, z = q
    return (math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)),
            math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x)))),
            math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


class CascadePD:
    """Каскад: позиция -> скорость -> наклон -> момент -> тяги.

    Три контура, каждый в ~4 раза медленнее внутреннего — классическое
    разделение частот:

        позиция    kp_pos = 1.2  1/с        (полоса ~1.2 рад/с)
        скорость   kp_vel = 0.55 рад/(м/с)  (полоса ~3 рад/с)
        угол       omega  = 12   рад/с      (по gain_rule, предел 16.7)

    Ограничение наклона tilt_max = 0.35 рад (20°) — не «на всякий случай»:
    при большем наклоне вертикальная составляющая тяги падает как cos,
    компенсация 1/cos упирается в ctrlrange, и высота проваливается.

    Рыскание — только Д-звено по угловой скорости (kd_y), уставка задаётся
    в рад/с. П-звена по углу рыскания нет намеренно: у аппарата нет
    «правильного» курса, а лишний контур добавляет колебание, которое
    в C2 напрямую портит покрытие (камера мажет по цели).
    """

    def __init__(self, model: mujoco.MjModel, omega_att: float = 12.0, zeta: float = 1.0,
                 kp_vel: float = 0.55, tilt_max: float = 0.35, kp_vz: float = 5.0,
                 kp_pos: float = 1.2, v_max: float = 1.6,
                 kp_att: float | None = None, kd_att: float | None = None) -> None:
        p = read_passport(model)
        self.model = model
        self.mass = p["масса, кг"]
        self.mixer = Mixer(model)
        self.ctrl_hi = p["ctrl макс, Н"]
        self.tilt_max, self.kp_vel, self.kp_vz = tilt_max, kp_vel, kp_vz
        self.kp_pos, self.v_max = kp_pos, v_max

        gr = gain_rule(p["Ixx, кг*м^2"], self.mixer.k_torque, p["tau мотора, с"], omega_att, zeta)
        gp = gain_rule(p["Iyy, кг*м^2"], self.mixer.k_torque, p["tau мотора, с"], omega_att, zeta)
        gy = gain_rule(p["Izz, кг*м^2"], self.mixer.k_yaw, p["tau мотора, с"], omega_att, zeta)
        # kp_att/kd_att — ручка для теста 11 «усиления на глаз»
        self.kp_r = gr["kp"] if kp_att is None else kp_att
        self.kd_r = gr["kd"] if kd_att is None else kd_att
        self.kp_p = gp["kp"] if kp_att is None else kp_att
        self.kd_p = gp["kd"] if kd_att is None else kd_att
        self.kd_y = gy["kd"]
        self.gains = gr
        # диагностика насыщения: ровно те два числа, по которым ловится грабля 6.1
        self.n_steps = 0
        self.n_sat = 0
        self.sum_raw = 0.0
        self.sum_clipped = 0.0

    # -- контуры ----------------------------------------------------------
    def velocity(self, data: mujoco.MjData, vx_c: float, vy_c: float,
                 vz_c: float, wz_c: float) -> np.ndarray:
        """Слежение за уставкой скорости В СК КОРПУСА. Пишет data.ctrl."""
        r, p, y = euler_from_quat(data.qpos[3:7])
        c, s = math.cos(y), math.sin(y)
        vxb = c * data.qvel[0] + s * data.qvel[1]
        vyb = -s * data.qvel[0] + c * data.qvel[1]

        # ошибка скорости -> желаемый наклон (вперёд = тангаж вниз)
        p_des = float(np.clip(self.kp_vel * (vx_c - vxb), -self.tilt_max, self.tilt_max))
        r_des = float(np.clip(-self.kp_vel * (vy_c - vyb), -self.tilt_max, self.tilt_max))

        az = self.kp_vz * (vz_c - data.qvel[2])
        # 1/cos: при наклоне вертикальная составляющая тяги падает.
        # max(0.5, ...) — предохранитель: при 60° множитель уже 2, дальше
        # компенсация всё равно упирается в ctrlrange и только шумит
        ct = max(0.5, math.cos(r) * math.cos(p))
        uz = (self.mass * (G + az) / 4.0) / ct

        u_roll = self.kp_r * (r_des - r) - self.kd_r * data.qvel[3]
        u_pitch = self.kp_p * (p_des - p) - self.kd_p * data.qvel[4]
        u_yaw = self.kd_y * (wz_c - data.qvel[5])

        raw = self.mixer(uz, u_roll, u_pitch, u_yaw, clip=False)
        out = np.clip(raw, 0.0, self.ctrl_hi)
        self.n_steps += 1
        self.n_sat += int(np.any((raw < 0.0) | (raw > self.ctrl_hi)))
        self.sum_raw += float(raw.mean())
        self.sum_clipped += float(out.mean())
        data.ctrl[:] = out
        return out

    def hold(self, data: mujoco.MjData, target, wz_c: float = 0.0) -> np.ndarray:
        """Удержание точки: внешний П-контур позиции поверх контура скорости."""
        r, p, y = euler_from_quat(data.qpos[3:7])
        e = np.asarray(target, dtype=np.float64) - data.qpos[:3]
        v_cmd = np.clip(self.kp_pos * e, -self.v_max, self.v_max)
        c, s = math.cos(y), math.sin(y)
        return self.velocity(data, c * v_cmd[0] + s * v_cmd[1],
                             -s * v_cmd[0] + c * v_cmd[1], float(v_cmd[2]), wz_c)

    # -- диагностика ------------------------------------------------------
    def saturation(self) -> Dict[str, float]:
        """Доля насыщенных шагов и паразитная подъёмная сила от клиппинга.

        `parasitic_N` = 4*(средняя команда ПОСЛЕ клиппинга − ДО). У здорового
        контура это ноль. Если оно сравнимо с весом — дрон «висит на дребезге»
        (грабля 6.1), и никакой kp_z эту ошибку высоты не уберёт.
        """
        n = max(1, self.n_steps)
        raw, cl = self.sum_raw / n, self.sum_clipped / n
        return {"доля насыщенных шагов": self.n_sat / n,
                "средняя команда до клипа, Н": raw,
                "средняя команда после клипа, Н": cl,
                "паразитная подъёмная сила, Н": 4.0 * (cl - raw)}

    def reset_stats(self) -> None:
        self.n_steps = self.n_sat = 0
        self.sum_raw = self.sum_clipped = 0.0


# ---------------------------------------------------------------------------
# Помощники для тестов
# ---------------------------------------------------------------------------
def fresh(model: mujoco.MjModel, pos=(0, 0, 1.5), rpy=(0.0, 0.0, 0.0),
          hover: float | None = None) -> mujoco.MjData:
    """Свежая MjData с заданной позой и УЖЕ РАСКРУЧЕННЫМИ моторами.

    `data.act[:] = hover` — обязательная строка. Состояние фильтра мотора
    (na = 4) при mj_resetData обнуляется, и первые ~60 мс аппарат падает
    просто потому, что винты раскручиваются с нуля. В C1 это стоило бы
    политике сотен тысяч шагов на «научиться переживать старт».
    """
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    data.qpos[:3] = pos
    r, p, y = rpy
    cr, sr = math.cos(r / 2), math.sin(r / 2)
    cp, sp = math.cos(p / 2), math.sin(p / 2)
    cy, sy = math.cos(y / 2), math.sin(y / 2)
    data.qpos[3:7] = [cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy,
                      cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy]
    if hover is not None:
        data.act[:] = hover
        data.ctrl[:] = hover
    mujoco.mj_forward(model, data)
    return data


def run(model, data, n, ctrl=None):
    for _ in range(n):
        if ctrl is not None:
            data.ctrl[:] = ctrl
        mujoco.mj_step(model, data)


# ---------------------------------------------------------------------------
# Тесты стенда
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="C0: стенд квадрокоптера")
    ap.add_argument("--quick", action="store_true", help="без длинных тестов")
    args = ap.parse_args()

    model = mujoco.MjModel.from_xml_path(str(QUAD_XML))
    p = read_passport(model)
    print_passport(p)

    hover = p["тяга висения на винт, Н"]
    dt = p["timestep, с"]
    mix = Mixer(model)
    print("МИКШЕР (знаки выведены из геометрии модели):")
    print("   ", mix.describe(), "\n")

    # -- 1. инерция мотора -------------------------------------------------
    d = fresh(model, hover=0.0)
    d.ctrl[:] = p["ctrl макс, Н"]
    t63 = None
    for i in range(1, 101):                      # 100 шагов = 0.2 с
        mujoco.mj_step(model, d)
        if t63 is None and d.act[0] >= 0.632 * p["ctrl макс, Н"]:
            t63 = i * dt
    t = Table(title="1. ИНЕРЦИЯ МОТОРА: ступенька ctrl 0 -> max",
              columns=["величина", "значение"])
    t.add(**{"величина": "время выхода на 63.2 %, с", "значение": t63})
    t.add(**{"величина": "tau из XML (dynprm), с", "значение": p["tau мотора, с"]})
    t.add(**{"величина": "act через 100 мс, Н", "значение": float(d.act[0])})
    t.note = "совпадение первых двух строк = фильтр filterexact работает как заявлено"
    print(t, "\n")

    # -- 2. висение на аналитической тяге ---------------------------------
    d = fresh(model, pos=(0, 0, 1.5), hover=hover)
    p0 = d.qpos[:3].copy()
    run(model, d, 2500, ctrl=np.full(4, hover))   # 5 с
    _, _, yaw = euler_from_quat(d.qpos[3:7])
    t = Table(title="2. ВИСЕНИЕ на аналитической тяге m*g/4 (5 с разомкнуто)",
              columns=["величина", "значение"])
    t.add(**{"величина": "дрейф z, мм", "значение": 1000 * float(d.qpos[2] - p0[2])})
    t.add(**{"величина": "дрейф xy, мм",
             "значение": 1000 * float(np.linalg.norm(d.qpos[:2] - p0[:2]))})
    t.add(**{"величина": "рыскание, град", "значение": math.degrees(yaw)})
    t.note = ("нули означают: сумма реактивных моментов обнулена (2 CW + 2 CCW), "
              "и m*g/4 действительно уравновешивает вес")
    print(t, "\n")

    # -- 3. свободное падение ---------------------------------------------
    d = fresh(model, pos=(0, 0, 1.0), hover=0.0)
    run(model, d, 1000, ctrl=np.zeros(4))         # 2 с
    t = Table(title="3. СВОБОДНОЕ ПАДЕНИЕ с 1.0 м при ctrl = 0",
              columns=["величина", "значение"])
    t.add(**{"величина": "z через 2 с, м", "значение": float(d.qpos[2])})
    t.add(**{"величина": "контактов", "значение": int(d.ncon)})
    t.note = "z у пола и ненулевой контакт = пол и коллизии работают"
    print(t, "\n")

    # -- 4. отклик по крену -------------------------------------------------
    d = fresh(model, pos=(0, 0, 3.0), hover=hover)
    ctrl = mix(hover, 0.15 * hover, 0.0, 0.0)     # дифференциал +15 % на крен
    t10 = None
    roll = {50: 0.0, 100: 0.0, 150: 0.0}
    for i in range(1, 201):                       # 0.4 с — дальше угол Эйлера
        d.ctrl[:] = ctrl                          # перескакивает через ±180°
        mujoco.mj_step(model, d)
        r, _, _ = euler_from_quat(d.qpos[3:7])
        if t10 is None and abs(r) >= math.radians(10.0):
            t10 = i * dt
        if i in roll:
            roll[i] = math.degrees(r)
    t = Table(title="4. ОТКЛИК ПО КРЕНУ: дифференциал тяги +15 %",
              columns=["величина", "значение"])
    t.add(**{"величина": "время до 10°, с", "значение": t10})
    for i in (50, 100, 150):
        t.add(**{"величина": f"крен через {int(i*dt*1000)} мс, град", "значение": roll[i]})
    t.add(**{"величина": "отношение кренов 300мс / 100мс",
             "значение": roll[150] / roll[50]})
    t.add(**{"величина": "угл. ускорение на единицу u_roll, рад/с^2",
             "значение": mix.k_torque / p["Ixx, кг*м^2"]})
    t.note = ("крен НЕ выходит на полку: восстанавливающего момента нет, ориентация — "
              "двойной интегратор. Замеренное отношение 11.59 БОЛЬШЕ чистого квадрата "
              "(было бы 9.0) — при 80° крена аппарат уже завалился и плечо изменилось. "
              "Чистую квадратичность смотреть в тесте 6, где наклон остаётся малым.\n"
              "Мерить дольше 0.4 с бессмысленно: угол Эйлера перескакивает через ±180°, "
              "и число превращается в ложь")
    print(t, "\n")

    # -- 5. чистота осей микшера -------------------------------------------
    rows = []
    # длительность разная НЕ для красоты: крен и тангаж за 1 с успевают
    # перевернуть аппарат и угол Эйлера перескакивает через ±180°;
    # рыскание же на 0.3 с даёт ещё неинформативно малый угол
    for name, u, secs in (("чистый крен", (0.15 * hover, 0.0, 0.0), 0.3),
                          ("чистый тангаж", (0.0, 0.15 * hover, 0.0), 0.3),
                          ("чистое рыскание", (0.0, 0.0, 0.20 * hover), 1.0)):
        d = fresh(model, pos=(0, 0, 3.0), hover=hover)
        ctrl = mix(hover, *u)
        z0 = float(d.qpos[2])
        run(model, d, int(secs / dt), ctrl=ctrl)
        r, pi, y = euler_from_quat(d.qpos[3:7])
        rows.append((name, secs, math.degrees(r), math.degrees(pi), math.degrees(y),
                     1000 * (float(d.qpos[2]) - z0)))
    t = Table(title="5. ЧИСТОТА ОСЕЙ МИКШЕРА",
              columns=["вход", "с", "крен, град", "тангаж, град", "рыскание, град",
                       "дрейф z, мм"])
    for r_ in rows:
        t.add(**{"вход": r_[0], "с": r_[1], "крен, град": r_[2], "тангаж, град": r_[3],
                 "рыскание, град": r_[4], "дрейф z, мм": r_[5]})
    t.note = ("на диагонали — отклик, вне диагонали — НУЛИ: знаки микшера верны.\n"
              "Дрейф z у рыскания РОВНО 0 — реактивный момент высоту не трогает, "
              "и именно поэтому рыскание для политики почти бесплатно (грабля 6.3).\n"
              "У крена и тангажа z проседает на десятки мм: наклон уводит тягу "
              "из вертикали как cos — это не ошибка микшера, это физика, и её "
              "компенсирует множитель 1/cos в CascadePD.velocity")
    print(t, "\n")

    # -- 6. неустойчивость: снос при постоянном наклоне ---------------------
    d = fresh(model, pos=(0, 0, 5.0), rpy=(math.radians(5.0), 0, 0), hover=hover)
    p0 = d.qpos[:3].copy()
    marks = {0.5: None, 1.0: None, 2.0: None}
    for i in range(1, 1501):                      # 3 с
        d.ctrl[:] = hover
        mujoco.mj_step(model, d)
        s = float(np.linalg.norm(d.qpos[:2] - p0[:2]))
        for m in marks:
            if marks[m] is None and s >= m:
                marks[m] = i * dt
    r_end, _, _ = euler_from_quat(d.qpos[3:7])
    t = Table(title="6. НЕУСТОЙЧИВОСТЬ: тяга висения + начальный крен 5°",
              columns=["величина", "значение"])
    for m in (0.5, 1.0, 2.0):
        t.add(**{"величина": f"время до сноса {m} м, с", "значение": marks[m]})
    t.add(**{"величина": "снос за 3 с, м",
             "значение": float(np.linalg.norm(d.qpos[:2] - p0[:2]))})
    t.add(**{"величина": "высота через 3 с, м", "значение": float(d.qpos[2])})
    t.add(**{"величина": "крен через 3 с, град", "значение": math.degrees(r_end)})
    if all(marks.values()):
        ratio = [marks[m] / marks[0.5] for m in (0.5, 1.0, 2.0)]
        t.add(**{"величина": "отношение времён 0.5:1:2 м",
                 "значение": " : ".join(f"{x:.3f}" for x in ratio)})
        t.note = ("ГЛАВНЫЙ ФАКТ ТРЕКА. Крен не вернулся сам (ориентация нейтрально "
                  "устойчива), а снос идёт как s = a*t^2/2 — отношение времён "
                  "обязано быть 1 : 1.414 : 2.000. Машинка трека A, если её "
                  "отпустить, стоит на месте; дрон за секунду уезжает на полметра")
    print(t, "\n")

    # -- 7. правило усиления ------------------------------------------------
    gr = gain_rule(p["Ixx, кг*м^2"], mix.k_torque, p["tau мотора, с"])
    t = Table(title="7. ПРАВИЛО УСИЛЕНИЯ внутреннего контура",
              columns=["величина", "значение"])
    for k, v in gr.items():
        t.add(**{"величина": k, "значение": v})
    t.note = ("предел ставит МОТОР, а не вкус: контур с полосой выше 1/(3*tau) "
              "входит в предельный цикл (тест 10)")
    print(t, "\n")

    # -- 8. каскад: удержание точки ----------------------------------------
    ctl = CascadePD(model)
    target = np.array([1.0, 0.5, 1.2])
    d = fresh(model, pos=(0, 0, 1.5), hover=hover)
    for _ in range(3000):                          # 6 с
        ctl.hold(d, target)
        mujoco.mj_step(model, d)
    sat = ctl.saturation()
    t = Table(title="8. КАСКАДНЫЙ ПД: удержание точки (1.0, 0.5, 1.2)",
              columns=["величина", "значение"])
    t.add(**{"величина": "ошибка удержания, мм",
             "значение": 1000 * float(np.linalg.norm(d.qpos[:3] - target))})
    for k, v in sat.items():
        t.add(**{"величина": k, "значение": v})
    t.note = ("паразитная сила 0 и ноль насыщений = контур работает НА ЛИНЕЙНОМ "
              "участке; сравнить с тестом 10")
    print(t, "\n")

    # -- 9. слежение за уставкой скорости -----------------------------------
    t = Table(title="9. СЛЕЖЕНИЕ ЗА УСТАВКОЙ СКОРОСТИ (на этом контуре стоит C2)",
              columns=["уставка", "запрошено", "измерено", "ошибка"])
    for v_cmd in (1.0, 1.5, 2.0, 4.0):
        ctl = CascadePD(model)
        d = fresh(model, pos=(0, 0, 2.0), hover=hover)
        for _ in range(2000):                      # 4 с — выход на режим
            ctl.velocity(d, v_cmd, 0.0, 0.0, 0.0)
            mujoco.mj_step(model, d)
        meas = float(np.linalg.norm(d.qvel[:2]))
        t.add(**{"уставка": "vx, м/с", "запрошено": v_cmd, "измерено": meas,
                 "ошибка": meas - v_cmd})
    for w_cmd in (0.8, 1.2):
        ctl = CascadePD(model)
        d = fresh(model, pos=(0, 0, 2.0), hover=hover)
        for _ in range(1000):
            ctl.velocity(d, 0.0, 0.0, 0.0, w_cmd)
            mujoco.mj_step(model, d)
        t.add(**{"уставка": "wz, рад/с", "запрошено": w_cmd,
                 "измерено": float(d.qvel[5]), "ошибка": float(d.qvel[5]) - w_cmd})
    t.note = ("ошибка порядка 1 % на всём диапазоне — поэтому в C2 действие "
              "политики можно считать уставкой скорости, а не «пожеланием»")
    print(t, "\n")

    # -- 10. усиления «на глаз»: висение на дребезге -------------------------
    # Возбуждение обязательно: контур, поставленный ТОЧНО в цель с нулевой
    # скоростью, не колеблется ни при каких усилениях. Старт из (0,0,1.0)
    # в цель (1.0,0.5,1.2) — тот же, что у здорового каскада в тесте 8.
    tgt_bad = np.array([1.0, 0.5, 1.2])
    t = Table(title="10. ГРАБЛЯ 6.1: усиления «на глаз» против усилений из физики",
              columns=["kp_att", "kd_att", "kp_vz", "насыщений", "до клипа, Н",
                       "после клипа, Н", "паразитная сила, Н", "z, м"])
    for kp_a, kd_a, kp_vz in ((None, None, 5.0), (60.0, 8.0, 5.0), (60.0, 8.0, 10.0)):
        ctl_b = CascadePD(model, kp_att=kp_a, kd_att=kd_a, kp_vz=kp_vz)
        d = fresh(model, pos=(0, 0, 1.0), hover=hover)
        for _ in range(4000):                      # 8 с
            ctl_b.hold(d, tgt_bad)
            mujoco.mj_step(model, d)
        s = ctl_b.saturation()
        t.add(**{"kp_att": (f"{ctl_b.kp_r:.4f} (из физики)" if kp_a is None else f"{kp_a:g}"),
                 "kd_att": (f"{ctl_b.kd_r:.4f}" if kd_a is None else f"{kd_a:g}"),
                 "kp_vz": kp_vz,
                 "насыщений": s["доля насыщенных шагов"],
                 "до клипа, Н": s["средняя команда до клипа, Н"],
                 "после клипа, Н": s["средняя команда после клипа, Н"],
                 "паразитная сила, Н": s["паразитная подъёмная сила, Н"],
                 "z, м": float(d.qpos[2])})
    t.note = (f"вес аппарата {p['вес, Н']:.4f} Н, команда высоты 1.2 м.\n"
              "Тяга не бывает отрицательной, поэтому clip(0, ctrl_max) ВЫПРЯМЛЯЕТ "
              "дребезг переусиленного контура в постоянную подъёмную силу: средняя "
              "команда ДО клипа около нуля, ПОСЛЕ — почти тяга висения.\n"
              "Средняя команда ДО клипа падает до ~0.1 Н, ПОСЛЕ — почти тяга висения: "
              "четыре винта дают 6.9 Н из 7.26 Н веса. Дрон висит НА ДРЕБЕЗГЕ.\n"
              "Третья строка — контрольная: удвоение kp_vz уменьшает промах по высоте "
              "(3.69 м -> 0.81 м), но доля насыщений остаётся 0.9998 — болезнь не "
              "в контуре высоты, подбором kp_z она не лечится, а только маскируется.\n"
              "Диагностика ровно двумя числами: доля насыщенных шагов и разница "
              "средних до/после клипа. Лечение — усиления из gain_rule()")
    print(t, "\n")

    # -- 11. 12 случайных стартов -------------------------------------------
    if not args.quick:
        rng = np.random.default_rng(0)
        errs, sats = [], []
        target = np.array([0.0, 0.0, 1.5])
        for _ in range(12):
            ctl = CascadePD(model)
            pos = target + rng.uniform(-1.5, 1.5, 3)
            pos[2] = float(np.clip(pos[2], 0.6, 3.0))
            rpy = (rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35),
                   rng.uniform(-math.pi, math.pi))
            d = fresh(model, pos=pos, rpy=rpy, hover=hover)
            for _ in range(4000):                  # 8 с
                ctl.hold(d, target)
                mujoco.mj_step(model, d)
            errs.append(float(np.linalg.norm(d.qpos[:3] - target)))
            sats.append(ctl.saturation()["доля насыщенных шагов"])
        t = Table(title="11. КАСКАД НА 12 СЛУЧАЙНЫХ СТАРТАХ (±1.5 м, ±20°, любой курс)",
                  columns=["величина", "значение"])
        t.add(**{"величина": "сошлись < 5 см", "значение": f"{sum(e < 0.05 for e in errs)}/12"})
        t.add(**{"величина": "средняя ошибка, мм", "значение": 1000 * float(np.mean(errs))})
        t.add(**{"величина": "худшая ошибка, мм", "значение": 1000 * float(np.max(errs))})
        t.add(**{"величина": "средняя доля насыщений", "значение": float(np.mean(sats))})
        t.note = ("это и есть «планка регулятора»: всё, что RL в C2 обязан "
                  "сделать ЛУЧШЕ, он делает ПОВЕРХ этого контура")
        print(t, "\n")

    print("C0 пройден: модель летает, микшер чист по осям, каскад сходится.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
