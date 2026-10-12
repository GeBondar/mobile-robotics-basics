"""Сверка контрактов ноды с средами обучения — без ROS, за секунды.

    python check_contracts.py

Для ЦАПЛИ-2 и дрона: среда урока 14 едет под управлением ONNX-политики, а
контракт из пакета rl_policy_ros параллельно собирает наблюдение из того же
состояния — так, как его соберёт нода из JointState/Imu/Odometry. Печатается
худшее покомпонентное расхождение и метрика замкнутого прогона.
"""
import math
import sys
from pathlib import Path

import mujoco
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ros2_ws/src/rl_policy_ros"))
sys.path.insert(0, str(ROOT / "lesson 14 (RL custom models)/track_b_walk"))
sys.path.insert(0, str(ROOT / "lesson 14 (RL custom models)/track_c_drone"))
sys.path.insert(0, str(ROOT / "lesson 14 (RL custom models)"))
POL = ROOT / "ros2_ws/src/rl_policy_ros/policies"

from rl_policy_ros.contracts import (Command, QuadHoverContract, RobotState,  # noqa: E402
                                     Tsaplya2Contract)


def session(name):
    return ort.InferenceSession(str(POL / name), providers=["CPUExecutionProvider"])


def state_from(m, d, nu, base_body, quat_from_xquat=False):
    """Ровно то, что публикует sim_node: суставы, IMU корпуса, odom.

    quat_from_xquat: среда дрона берёт поворот из xmat, а MuJoCo считает xmat
    ДО интегрирования шага — он отстаёт от qpos на 2 мс. sim_node публикует
    свежий qpos; разница с обучением — 1e-4 в наблюдении. Для побитовой сверки
    берём поворот так же, как среда.
    """
    quat = d.xquat[base_body].copy() if quat_from_xquat else d.qpos[3:7].copy()
    R = d.xmat[base_body].reshape(3, 3)
    return RobotState(q=d.qpos[7:7 + nu].copy(), dq=d.qvel[6:6 + nu].copy(),
                      quat=quat, gyro=d.qvel[3:6].copy(),
                      pos=d.qpos[0:3].copy(), vel_body=R.T @ d.qvel[0:3])


def check_tsaplya(cmd_vx=0.5, seconds=10.0):
    from _reference_walk_env_r4 import Tsaplya2WalkEnv
    env = Tsaplya2WalkEnv(randomize=False, seed=3)
    obs, _ = env.reset(seed=3)
    env.cmd = np.array([cmd_vx, 0.0, 0.0])
    d_sw = min(0.35, max(0.15, 0.6 * abs(cmd_vx) / env.f_phase))
    env._d_swing, env._f_eff = math.copysign(d_sw, cmd_vx), max(env.f_phase, abs(cmd_vx) / d_sw)
    env._wz_eff = 0.0
    obs = env._obs()
    c = Tsaplya2Contract()
    st = state_from(env.model, env.data, 8, 1)
    c.reset(st, Command())
    c.cmd = env.cmd.copy()                 # без разгона: среда стартует сразу с команды
    c.phase = env._phase
    c.yaw_ref = env._yaw_ref
    sess = session("tsaplya2_walk.onnx")
    worst, x0, fell, n = 0.0, float(env.data.qpos[0]), False, int(seconds / env.dt)
    for i in range(n):
        st = state_from(env.model, env.data, 8, 1)
        mine = c.observe(st, Command(vx=cmd_vx))
        worst = max(worst, float(np.max(np.abs(mine - obs))))
        a = sess.run(None, {"obs": obs.reshape(1, -1)})[0][0]
        ctrl_mine = c.act(a)
        obs, _, term, _, _ = env.step(a)
        worst_ctrl = float(np.max(np.abs(ctrl_mine - env.data.ctrl)))
        worst = max(worst, worst_ctrl)
        if term:
            fell = True
            break
    v = (float(env.data.qpos[0]) - x0) / ((i + 1) * env.dt)
    print(f"tsaplya2: {i + 1} тактов, худшее расхождение obs/ctrl {worst:.2e}, "
          f"скорость {v:.3f} м/с при команде {cmd_vx}, падение: {fell}")
    return worst


def check_quad(episodes=5):
    from hover_env import HoverEnv
    env = HoverEnv(seed=900)
    sess = session("quad_hover.onnx")
    worst, errs = 0.0, []
    for ep in range(episodes):
        obs, _ = env.reset(seed=5000 + ep)
        c = QuadHoverContract()
        bid = env._bid
        for _ in range(env.max_steps):
            st = state_from(env.model, env.data, 0, bid, quat_from_xquat=True)
            mine = c.observe(st, Command(target=env.target))
            # морковка обрезает дальнюю цель; в среде её нет — сверяем только ближнюю
            if np.linalg.norm(env.target - env.data.qpos[:3]) <= c.CARROT:
                worst = max(worst, float(np.max(np.abs(mine - obs))))
            a = sess.run(None, {"obs": obs.reshape(1, -1)})[0][0]
            thrust = c.act(a)
            obs, _, term, trunc, info = env.step(a)
            worst = max(worst, float(np.max(np.abs(thrust - env.data.ctrl))))
            if term or trunc:
                break
        errs.append(info["final_dist"])
    print(f"quad: {episodes} эпизодов, худшее расхождение obs/ctrl {worst:.2e}, "
          f"финальная ошибка {np.mean(errs):.4f} м")
    return worst


if __name__ == "__main__":
    w1 = check_tsaplya()
    w2 = check_quad()
    ok = w1 < 1e-5 and w2 < 1e-5
    print("СВЕРКА ПРОЙДЕНА" if ok else "СВЕРКА НЕ ПРОЙДЕНА")
    sys.exit(0 if ok else 1)
