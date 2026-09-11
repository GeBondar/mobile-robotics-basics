"""C2: обучение PPO сканированию — награда за ПОКРЫТИЕ, поверх контура скорости.

    python train_scan.py --steps 200000           # 3-5 минут, метрика уже растёт
    python train_scan.py --steps 600000           # рабочая политика
    python train_scan.py --steps 2000000          # «красивая» политика

ЧТО СМОТРЕТЬ В ЛОГЕ (и почему не одну цифру):
    coverage_mean_100 — среднее покрытие последних 100 эпизодов В ОБУЧАЮЩЕЙ
        среде. Оно упирается в потолок около cov_target, потому что эпизод
        по этому порогу и обрывается. Это НЕ качество политики.
    success_100       — доля эпизодов, дошедших до порога. Вот это метрика.
    ep_len_mean_100   — сколько шагов уходит на порог. Именно её обученная
        политика обязана опустить: у скриптового облёта это ~1116 шагов.

ГЛАВНОЕ ПРАВИЛО, ОПЛАЧЕННОЕ СГОРЕВШИМ ЗАМЕРОМ:
    качество НЕЛЬЗЯ мерить в среде, которая обрывает эпизод по этой же
    метрике. Поэтому итоговая оценка идёт в evaluate.py, в среде
    с cov_target = 1.01 (порог недостижим), и меряет ВРЕМЯ до 0.85.
"""
from __future__ import annotations

import os

# ДО первого импорта numpy/torch: восемь воркеров со своими пулами потоков —
# это оверподписка ядер. Воркеры SubprocVecEnv наследуют окружение родителя,
# поэтому две строки здесь действуют на всех. См. также шапку scan_env.py
# о цене импорта stable_baselines3 внутрь воркера.
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


def make_env(rank: int, cov_target: float = 0.85):
    def _f():
        from scan_env import DroneScanEnv
        return DroneScanEnv(seed=rank, cov_target=cov_target)
    return _f


def make_eval_fn(rank: int = 900):
    """Оценочная среда — ВСЕГДА на боевом пороге 0.85 и полном радиусе старта.

    Куррикулум в неё не синхронизируется НИЧЕМ (sync_to_eval пуст): иначе
    покрытие «растёт», потому что растёт порог, а не политика.
    """
    def _f():
        from scan_env import DroneScanEnv
        return DroneScanEnv(seed=rank, cov_target=0.85, spawn_radius=4.5)
    return _f


def main() -> int:
    ap = argparse.ArgumentParser(description="C2: PPO поверх контура скорости")
    ap.add_argument("--steps", type=int, default=2_000_000)
    ap.add_argument("--envs", type=int, default=8)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default=str(HERE / "runs" / "scan"))
    ap.add_argument("--curriculum", type=int, default=1)
    ap.add_argument("--grid-curriculum", type=int, default=0,
                    help="дополнительно поднимать сетку 8 -> 16 секторов. "
                         "ВЫКЛЮЧЕНО по умолчанию: выигрыш НЕ измерен, а сдвиг "
                         "распределения локальной карты посреди обучения — реален")
    ap.add_argument("--ckpt-every", type=int, default=200_000)
    ap.add_argument("--eval-every", type=int, default=0)
    ap.add_argument("--eval-episodes", type=int, default=10)
    ap.add_argument("--report-every", type=int, default=0)
    a = ap.parse_args()

    import torch
    torch.set_num_threads(1)
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.vec_env import SubprocVecEnv, VecMonitor, VecNormalize

    run_dir = Path(a.out)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_every = a.report_every or max(10_000, a.steps // 10)

    ramp = a.steps // 2
    schedule = {
        # «сначала покажи, что умеешь облетать» -> «теперь добери дыры за выступом»
        "set_cov_target": linear(hold=0, ramp=ramp, lo=0.50, hi=0.85),
        # против переобучения на удобный ракурс старта
        "set_spawn_radius": linear(hold=0, ramp=ramp, lo=3.5, hi=4.5),
    }
    if a.grid_curriculum:
        schedule["set_n_sect"] = linear(hold=0, ramp=ramp // 2, lo=8, hi=16)
    if a.curriculum:
        print(explain(schedule, timesteps=0, total=a.steps, rows=6))

    # cov_target у обучающих сред стартует с нижнего конца рампы: иначе первые
    # 512*envs шагов идут на старом значении, и куррикулум «включается» с опозданием
    cov0 = 0.50 if a.curriculum else 0.85
    venv = SubprocVecEnv([make_env(i, cov0) for i in range(a.envs)])
    venv = VecMonitor(venv, info_keywords=("coverage",))
    venv = VecNormalize(venv, norm_obs=True, norm_reward=True, clip_obs=10.0, gamma=0.995)

    eval_env = None
    if a.eval_every:
        eval_env = make_eval_env(make_eval_fn(900), clip_obs=10.0, gamma=0.995)

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

    state = {"mark": report_every, "t0": time.time(),
             "rew": [], "cov": [], "succ": [], "len": []}

    class ProgressCallback(BaseCallback):
        def _on_step(self) -> bool:
            for info in self.locals.get("infos", []):
                ep = info.get("episode")
                if ep is not None:
                    state["rew"].append(float(ep["r"]))
                    state["len"].append(float(ep["l"]))
                    state["cov"].append(float(ep.get("coverage", info.get("coverage", 0.0))))
                    state["succ"].append(float(bool(info.get("success"))))
            if self.num_timesteps >= state["mark"]:
                dt = time.time() - state["t0"]
                row = {"steps": int(self.num_timesteps), "wall_s": round(dt, 1),
                       "fps": int(self.num_timesteps / dt),
                       "ep_rew_mean_100": round(float(np.mean(state["rew"][-100:] or [0])), 2),
                       "coverage_mean_100": round(float(np.mean(state["cov"][-100:] or [0])), 4),
                       "success_100": round(float(np.mean(state["succ"][-100:] or [0])), 3),
                       "ep_len_mean_100": round(float(np.mean(state["len"][-100:] or [0])), 1),
                       "n_ep": len(state["rew"])}
                if curr is not None:
                    row["curr"] = {k: round(v, 3) for k, v in curr.current().items()}
                print(json.dumps(row, ensure_ascii=False), flush=True)
                state["mark"] += report_every
            return True

    callbacks.append(ProgressCallback())

    buf = 512 * a.envs
    batch = max(d for d in range(256, min(4096, buf) + 1) if buf % d == 0)
    # gamma = 0.995, а не 0.99: эпизод длинный (до 1500 шагов = 30 с), и при 0.99
    # горизонт 1/(1-g) = 100 шагов = 2 с — политика физически не видит выгоды
    # долететь до дальней дыры. При 0.995 горизонт 200 шагов = 4 с.
    # ent_coef = 0.004 против 0.002 в C1: задача покрытия требует ИССЛЕДОВАНИЯ,
    # и слишком быстрое схлопывание политики даёт «кружиться в отснятой зоне».
    model = PPO("MlpPolicy", venv, learning_rate=3e-4, n_steps=512, batch_size=batch,
                n_epochs=5, gamma=0.995, gae_lambda=0.95, clip_range=0.2,
                ent_coef=0.004, vf_coef=0.5, max_grad_norm=1.0,
                policy_kwargs=dict(net_arch=dict(pi=[128, 128], vf=[128, 128])),
                device=a.device, verbose=0, seed=1)
    print(f"[обучение] {a.steps} env-шагов, {a.envs} сред, буфер {buf}, батч {batch}, "
          f"устройство {a.device}", flush=True)

    t0 = time.time()
    model.learn(total_timesteps=a.steps, callback=callbacks)
    wall = time.time() - t0

    n = int(model.num_timesteps)
    model.save(run_dir / f"model_{n}_steps.zip")
    venv.save(str(run_dir / f"model_vecnormalize_{n}_steps.pkl"))
    print(json.dumps({"done": True, "steps": n, "wall_min": round(wall / 60, 2),
                      "fps": int(a.steps / wall)}, ensure_ascii=False), flush=True)
    venv.close()

    # -- короткая честная оценка: в среде с НЕДОСТИЖИМЫМ порогом --------------
    pair = find_pair(run_dir / f"model_{n}_steps.zip", run_dir)
    print(f"[чекпойнт] {pair}")
    policy, norm = load_policy(pair, device="cpu")
    from scan_env import DroneScanEnv
    env = DroneScanEnv(seed=900, cov_target=1.01)
    covs, t85, crashes = [], [], 0
    n_ep = 10
    for ep in range(n_ep):
        obs, _ = env.reset(seed=7000 + ep)
        mark = None
        info = {}
        for i in range(env.max_steps):
            act, _ = policy.predict(norm(obs)[None], deterministic=True)
            obs, r, te, tr, info = env.step(act[0])
            if mark is None and info["coverage"] >= 0.85:
                mark = i + 1
            if te or tr:
                break
        covs.append(info["coverage"])
        crashes += int(bool(info.get("crash") or info.get("out")))
        if mark is not None:
            t85.append(mark)
    print(json.dumps({
        "оценка": "cov_target=1.01 (порог недостижим), детерминированная политика",
        "эпизодов": n_ep,
        "покрытие за полный эпизод": round(float(np.mean(covs)), 4),
        "дошли до 0.85": f"{len(t85)}/{n_ep}",
        "шагов до 0.85 (медиана)": (int(np.median(t85)) if t85 else None),
        "с чем сравнивать": "скриптовый облёт из probe.py, раздел 2 — там же "
                            "измеряется его медиана шагов до 0.85",
        "доля аварий": round(crashes / n_ep, 3),
    }, ensure_ascii=False, indent=2), flush=True)
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
