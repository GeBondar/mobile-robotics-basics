"""C1: обучение PPO зависанию СЫРЫМИ ВИНТАМИ.

    python train_hover.py --steps 200000          # 3-4 минуты, метрика уже растёт
    python train_hover.py --steps 1500000         # полный прогон

Читать результат надо в ДВУХ метриках, а не в одной суммарной награде:
    ep_len  — «научился не падать»  (растёт первым, до 500 из 500);
    ep_rew  — «научился попадать»   (растёт вторым, когда падать перестал).
Ровно этот порядок и есть сюжет ступени: сначала выжить, потом попасть.

Всё, что здесь есть общего с любым другим треком урока, взято из rl_toolkit
и НЕ переписано: рампы куррикулума, пересчёт частот колбэков из env-шагов
в вызовы, парные чекпойнты ckpt+vecnorm, честная оценка с копированием
статистики нормализации.
"""
from __future__ import annotations

import os

# ДО первого импорта numpy/torch. Восемь воркеров, каждый со своим пулом
# потоков numpy/torch на 24 ядрах — это оверподписка, при которой воркеры
# начинают отнимать ядра друг у друга. Дочерние процессы SubprocVecEnv
# наследуют окружение родителя, поэтому две строки здесь лечат всех восьмерых.
# Переменные читаются В МОМЕНТ импорта, ставить их после import numpy
# бессмысленно.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse                                                     # noqa: E402
import json                                                         # noqa: E402
import sys                                                          # noqa: E402
import time                                                         # noqa: E402
from pathlib import Path                                            # noqa: E402

import numpy as np                                                  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rl_toolkit.checkpointing import (find_pair, load_policy,       # noqa: E402
                                      make_eval_env, setup_callbacks)
from rl_toolkit.curriculum import CurriculumCallback, explain, linear   # noqa: E402
from rl_toolkit.rewards import RewardLogCallback                    # noqa: E402

HERE = Path(__file__).resolve().parent


def make_env(rank: int):
    """Фабрика для воркера SubprocVecEnv.

    HoverEnv импортируется ВНУТРИ функции: на Windows воркер стартует через
    spawn и заново исполняет модуль верхнего уровня. Импорт среды внутри
    фабрики держит стартовый набор воркера минимальным.
    """
    def _f():
        from hover_env import HoverEnv
        return HoverEnv(seed=rank)
    return _f


class Progress:
    """Печать прогресса — отдельно от rl_toolkit, потому что метрики у трека свои."""

    def __init__(self, every: int):
        self.every = int(every)
        self.mark = int(every)
        self.t0 = time.time()
        self.rews: list = []
        self.lens: list = []
        self.thr: list = []


def main() -> int:
    ap = argparse.ArgumentParser(description="C1: PPO на четыре винта")
    ap.add_argument("--steps", type=int, default=1_500_000)
    ap.add_argument("--envs", type=int, default=8,
                    help="8 — измеренный компромисс: 8 воркеров по ~0.5 ГБ + "
                         "родитель влезают в 16 ГБ, 16 воркеров кладут машину")
    ap.add_argument("--device", default="cpu",
                    help="cpu. GPU здесь ВРЕДЕН: узкое место — шаг среды, "
                         "а не градиент сети 128x128")
    ap.add_argument("--out", default=str(HERE / "runs" / "hover"))
    ap.add_argument("--curriculum", type=int, default=1)
    ap.add_argument("--ckpt-every", type=int, default=200_000, help="в ENV-шагах")
    ap.add_argument("--eval-every", type=int, default=0, help="в ENV-шагах, 0 = не оценивать")
    ap.add_argument("--eval-episodes", type=int, default=10)
    ap.add_argument("--report-every", type=int, default=0, help="0 = steps/10")
    ap.add_argument("--log-std-init", type=float, default=0.0,
                    help="начальный log std гауссовой политики (умолчание SB3 = 0.0, "
                         "то есть std ~ 1.0). probe.py -> «разведка амплитуды» "
                         "показывает, что дольше всех живёт НУЛЕВОЕ действие, а это "
                         "признак того, что тихий старт (около -1…-2) может помочь. "
                         "ДЛЯ ЭТОГО ТРЕКА ВЫИГРЫШ НЕ ИЗМЕРЕН — ручка оставлена, "
                         "чтобы студент померил сам")
    a = ap.parse_args()

    import torch
    torch.set_num_threads(1)
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.vec_env import SubprocVecEnv, VecMonitor, VecNormalize

    run_dir = Path(a.out)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_every = a.report_every or max(10_000, a.steps // 10)

    # -- куррикулум: две ручки, обе линейно за первую половину бюджета -------
    # Правило платформы, унаследованное дословно: то, что делает задачу ЛЕГЧЕ,
    # в оценочную среду НЕ синхронизируется — иначе метрика перестаёт быть
    # честной. Поэтому sync_to_eval пуст, а eval-среда создаётся сразу
    # на полной сложности (spawn 0.8 м, наклон 0.3 рад).
    ramp = a.steps // 2
    schedule = {
        "set_spawn": linear(hold=0, ramp=ramp, lo=0.35, hi=0.80),
        "set_tilt0": linear(hold=0, ramp=ramp, lo=0.12, hi=0.30),
    }
    if a.curriculum:
        print(explain(schedule, timesteps=0, total=a.steps, rows=6))

    venv = SubprocVecEnv([make_env(i) for i in range(a.envs)])
    # VecMonitor поверх ВЕКТОРНОЙ среды, а не Monitor внутри каждой:
    # Monitor тянет в воркер stable_baselines3 целиком
    venv = VecMonitor(venv)
    venv = VecNormalize(venv, norm_obs=True, norm_reward=True, clip_obs=10.0, gamma=0.99)

    eval_env = None
    if a.eval_every:
        eval_env = make_eval_env(make_env(900), clip_obs=10.0, gamma=0.99)

    curr = None
    if a.curriculum:
        curr = CurriculumCallback(venv, eval_env, schedule=schedule,
                                  sync_to_eval=frozenset(), verbose=1)

    callbacks = setup_callbacks(run_dir=run_dir, n_envs=a.envs,
                                ckpt_every_steps=a.ckpt_every,
                                eval_every_steps=(a.eval_every or None),
                                eval_env=eval_env, n_eval_episodes=a.eval_episodes,
                                curriculum=curr, name_prefix="model",
                                total_timesteps=a.steps)
    callbacks.append(RewardLogCallback(dt=0.02, log_freq=1000, prefix="rew"))

    prog = Progress(report_every)

    class ProgressCallback(BaseCallback):
        def _on_step(self) -> bool:
            for info in self.locals.get("infos", []):
                if "episode" in info:
                    prog.rews.append(float(info["episode"]["r"]))
                    prog.lens.append(float(info["episode"]["l"]))
                if "mean_thrust" in info:
                    prog.thr.append(float(info["mean_thrust"]))
            if self.num_timesteps >= prog.mark:
                dt = time.time() - prog.t0
                print(json.dumps({
                    "steps": int(self.num_timesteps), "wall_s": round(dt, 1),
                    "fps": int(self.num_timesteps / dt),
                    "ep_rew_mean_100": round(float(np.mean(prog.rews[-100:] or [0])), 2),
                    "ep_len_mean_100": round(float(np.mean(prog.lens[-100:] or [0])), 1),
                    # средняя тяга — ловушка грабли 6.4: она обязана быть около
                    # 1.81 Н (тяга висения), а не 2.3 Н
                    "mean_thrust_N": round(float(np.mean(prog.thr[-5000:] or [0])), 4),
                    "n_ep": len(prog.rews)}, ensure_ascii=False), flush=True)
                prog.mark += prog.every
            return True

    callbacks.append(ProgressCallback())

    buf = 512 * a.envs
    batch = max(d for d in range(256, min(4096, buf) + 1) if buf % d == 0)
    model = PPO("MlpPolicy", venv, learning_rate=3e-4, n_steps=512, batch_size=batch,
                n_epochs=5, gamma=0.99, gae_lambda=0.95, clip_range=0.2,
                ent_coef=0.002, vf_coef=0.5, max_grad_norm=1.0,
                policy_kwargs=dict(net_arch=dict(pi=[128, 128], vf=[128, 128]),
                                   log_std_init=a.log_std_init),
                device=a.device, verbose=0, seed=1)
    print(f"[обучение] {a.steps} env-шагов, {a.envs} сред, буфер {buf}, батч {batch}, "
          f"устройство {a.device}", flush=True)

    t0 = time.time()
    model.learn(total_timesteps=a.steps, callback=callbacks)
    wall = time.time() - t0

    # Финальная ПАРА: имена ровно те, что понимает rl_toolkit.checkpointing —
    # иначе find_pair() не сойдётся и политика поедет на чужой нормализации
    n = int(model.num_timesteps)
    model.save(run_dir / f"model_{n}_steps.zip")
    venv.save(str(run_dir / f"model_vecnormalize_{n}_steps.pkl"))
    print(json.dumps({"done": True, "steps": n, "wall_min": round(wall / 60, 2),
                      "fps": int(a.steps / wall)}, ensure_ascii=False), flush=True)
    venv.close()

    # -- честная оценка финальной пары --------------------------------------
    pair = find_pair(run_dir / f"model_{n}_steps.zip", run_dir)
    print(f"[чекпойнт] {pair}")
    policy, norm = load_policy(pair, device="cpu")
    from hover_env import HoverEnv
    env = HoverEnv(seed=900)
    lens, dists, surv = [], [], 0
    n_ep = 30
    for ep in range(n_ep):
        obs, _ = env.reset(seed=5000 + ep)
        info = {}
        i = 0
        for i in range(env.max_steps):
            act, _ = policy.predict(norm(obs)[None], deterministic=True)
            obs, r, te, tr, info = env.step(act[0])
            if te or tr:
                break
        lens.append(i + 1)
        dists.append(float(info.get("final_dist", 9.0)))
        surv += int(bool(info.get("survived")))
    print(json.dumps({
        "оценка": "полная сложность, детерминированная политика, парный vecnorm",
        "эпизодов": n_ep,
        "доля доживших до конца": round(surv / n_ep, 3),
        "средняя длина эпизода": round(float(np.mean(lens)), 1),
        "средняя финальная ошибка позиции, м": round(float(np.mean(dists)), 4),
        "критерий успеха C1": "доля >= 0.90 и ошибка <= 0.25 м",
        "пройден": bool(surv / n_ep >= 0.90 and float(np.mean(dists)) <= 0.25),
    }, ensure_ascii=False, indent=2), flush=True)
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
