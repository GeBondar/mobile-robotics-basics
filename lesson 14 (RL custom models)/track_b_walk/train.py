"""ОБУЧЕНИЕ учебной среды ходьбы: PPO + куррикулум + парные чекпойнты.

ПРОЧТИТЕ ЭТО ДО ЗАПУСКА
-----------------------
За 30 минут ходьбы НЕ БУДЕТ. Это не пессимизм, а замер: в боевой среде
на отметке 6.5 млн шагов средняя длина эпизода равна РОВНО 53.0 — ровно
столько же, сколько у машины с нулевым действием, и она равна 53.0 на
всех тринадцати точках оценки от 0.5 до 13.0 млн шагов
(`evaluations.npz` прогона r4f; 08_track_b.md, раздел 5). Перелом
происходит на 13.5 млн ≈ 1 ч 02 мин, полный 20-секундный эпизод — на
16.5 млн ≈ 1 ч 16 мин.

Учебная среда ужата так, чтобы за тот же час было что показать на
графике: фактический прогон (08_track_b.md, раздел 6) за 22 минуты /
1.67 млн шагов поднял длину эпизода 53 -> 68.5 (+29 %), тогда как боевая
среда на том же числе шагов даёт плоскую прямую 53.0. Это НЕ ходьба.
Это «политика начала ловить равновесие». Таблица бюджетов — в README.

ЧТО ЗДЕСЬ ВАЖНОГО, КРОМЕ ВЫЗОВА model.learn()
---------------------------------------------
1. log_std_init = -2.3. Тихий старт разведки. Со стандартным std ~ 1
   машина 33 кг с приводами 112.86 Н·м гибнет раньше, чем покажет
   политике хоть одну траекторию «стою» — бутстрап value-функции не
   замыкается (замерено в probe.py, раздел 4: при амплитуде 1.0 жизнь
   0.47 с против пассивных 1.06 с).
2. КУРРИКУЛУМ ведёт `rl_toolkit.curriculum` по АБСОЛЮТНОМУ счётчику
   шагов модели, а не по номеру вызова колбэка. Это принципиально: при
   дообучении (`--resume`) счётчик продолжается, и рампа, задуманная как
   «первые 2 млн шагов полегче», при старте с 60 млн выдаст максимальную
   сложность с первого же шага.
3. ЧЕКПОЙНТЫ ТОЛЬКО ПАРАМИ: `save_vecnormalize=True`. Без парного
   `.pkl` веса бесполезны — см. `demo.py --no-vecnorm`.
4. ОЦЕНКА ЧЕСТНАЯ: eval-среда живёт при 1g ВСЕГДА, гравитационный
   куррикулум в неё не синхронизируется. Синхронизируется только
   масштаб команд — он меняет саму задачу, а не её сложность.

ЗАПУСК
------
    python train.py --steps 100000            # проверить, что всё живо
    python train.py --steps 6000000           # ~30 минут, кривая пойдёт вверх
    python train.py --steps 26000000          # ~2 часа, минимум для ходьбы
    python train.py --steps 6000000 --envs 8  # если есть 16 ГБ ОЗУ
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from rl_toolkit.checkpointing import (  # noqa: E402
    make_eval_env, setup_callbacks,
)
from rl_toolkit.curriculum import CurriculumCallback, explain, linear  # noqa: E402
from rl_toolkit.rewards import RewardLogCallback  # noqa: E402
from walk_env import WalkEnv  # noqa: E402

# --------------------------------------------------------------------------
# ГИПЕРПАРАМЕТРЫ PPO
# Взяты из боевого тренера `sim/train_walk_r4.py` без изменений: это тот
# самый набор, который довёл политику до 60 млн шагов и походки без
# падений. Менять их в уроке нет причин — узкое место не в них.
# --------------------------------------------------------------------------
PPO_KWARGS = dict(
    learning_rate=3e-4,
    n_steps=2048,          # на каждую среду; при 4 средах роллаут 8192 шагов
    batch_size=4096,
    n_epochs=5,
    gamma=0.99,
    gae_lambda=0.95,
    clip_range=0.2,
    ent_coef=0.006,        # чуть выше стандартных 0.0: разведка нужна, но узкая
    vf_coef=0.5,
    max_grad_norm=0.5,
)
# MLP 256x128 — и для политики, и для критика. Сеть намеренно маленькая:
# узкое место здесь MuJoCo на CPU, а не умножение матриц. Именно поэтому
# device="cpu" не компромисс, а БЫСТРЕЕ: замер на этой же RTX 4060 Laptop
# дал 2063 шага/с на CPU против 741 на GPU (08_track_b.md, раздел 5).
NET_ARCH = dict(pi=[256, 128], vf=[256, 128])
LOG_STD_INIT = -2.3        # std = 0.10


def build_schedule(total: int) -> dict:
    """Куррикулум, растянутый на ФАКТИЧЕСКИЙ бюджет прогона.

    В боевом рецепте рампы прибиты к 60 млн шагов: 1g наступает на 28 млн,
    полный диапазон команд — на 38 млн (`_launch_r4f.ps1:10`). На бюджете
    6 млн это означает, что робота ЗА ВСЁ ОБУЧЕНИЕ ни разу не попросили
    идти. Поэтому рампы здесь заданы В ДОЛЯХ бюджета.

    Доли:
      гравитация 0.35g -> 1g : держим до 5 %, поднимаем к 50 % бюджета
      команды    0 -> 1      : держим до 5 %, поднимаем к 75 % бюджета

    Команды растянуты ДЛИННЕЕ гравитации сознательно. Это правка по
    результату фактического прогона учебной среды (08_track_b.md,
    раздел 6, «что я бы поправил»): там cmd_scale дошёл до 1.0 уже на
    0.4 млн шагов, когда машина ещё падала за секунду, и штраф простоя
    утопил награду в -17…-24.
    """
    return {
        "set_gravity_scale": linear(hold=int(0.05 * total),
                                    ramp=max(1, int(0.45 * total)),
                                    lo=0.35, hi=1.0),
        "set_cmd_scale": linear(hold=int(0.05 * total),
                                ramp=max(1, int(0.70 * total)),
                                lo=0.0, hi=1.0),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=6_000_000)
    ap.add_argument("--envs", type=int, default=4)
    ap.add_argument("--vec", choices=("subproc", "dummy"), default="subproc")
    ap.add_argument("--run", type=str, default=None,
                    help="каталог прогона (по умолчанию runs/<время>)")
    ap.add_argument("--eval-episodes", type=int, default=5)
    ap.add_argument("--device", type=str, default="cpu")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import (
        DummyVecEnv, SubprocVecEnv, VecNormalize,
    )

    # --run — ИМЯ прогона, а не путь: иначе прогон ложится в текущий каталог
    # мимо runs/ и мимо .gitignore, и веса попадают в коммит (находка приёмки M3)
    run_dir = (HERE / "runs" / args.run) if args.run else (
        HERE / "runs" / time.strftime("%m%d_%H%M%S"))
    run_dir.mkdir(parents=True, exist_ok=True)

    # --- среды --------------------------------------------------------
    def env_fn(rank: int):
        def _thunk():
            return WalkEnv(seed=args.seed + rank)
        return _thunk

    vec_cls = SubprocVecEnv if (args.vec == "subproc" and args.envs > 1) else DummyVecEnv
    train_env = vec_cls([env_fn(i) for i in range(args.envs)])
    # norm_reward=True — награда тоже нормируется; при этом clip_obs 10.0
    # оставлен стандартным. Статистика этой обёртки и есть то, что
    # сохраняется в парный .pkl.
    train_env = VecNormalize(train_env, norm_obs=True, norm_reward=True,
                             clip_obs=10.0, gamma=PPO_KWARGS["gamma"])

    # ОЦЕНОЧНАЯ среда — ОТДЕЛЬНАЯ и всегда при 1g. Если оценивать в той же
    # среде, где идёт куррикулум, «улучшение» окажется просто следствием
    # того, что задачу пока не усложнили.
    eval_env = make_eval_env(lambda: WalkEnv(seed=args.seed + 1000),
                             clip_obs=10.0, gamma=PPO_KWARGS["gamma"])

    # --- модель -------------------------------------------------------
    model = PPO(
        "MlpPolicy", train_env, device=args.device, seed=args.seed, verbose=1,
        tensorboard_log=str(run_dir / "tb"),
        policy_kwargs=dict(net_arch=NET_ARCH, log_std_init=LOG_STD_INIT),
        **PPO_KWARGS,
    )

    # --- куррикулум ---------------------------------------------------
    schedule = build_schedule(args.steps)
    print("\nКУРРИКУЛУМ")
    for name, ramp in schedule.items():
        print(f"  {name:<20} {ramp.describe()}")
    print()
    print(explain(schedule, timesteps=0, total=args.steps))
    curriculum = CurriculumCallback(
        train_env, eval_env, schedule=schedule,
        # ГРАВИТАЦИЯ В EVAL НЕ УХОДИТ: она делает задачу ЛЕГЧЕ, и с ней
        # метрика перестала бы быть честной. Масштаб команд уходит: он
        # меняет саму задачу, и без него eval мерил бы не то, чему учат.
        sync_to_eval={"set_cmd_scale"},
        verbose=1,
    )

    # --- колбэки ------------------------------------------------------
    # Частоты задаются В ENV-ШАГАХ; пересчёт в «вызовы» (делением на число
    # сред) делает setup_callbacks и ПЕЧАТАЕТ реальный шаг. Это тот самый
    # пересчёт, на котором обычно теряют кратность: при 4 средах запрос
    # «каждые 500 000» превращается в 500 000, а при 6 — в 499 998.
    ckpt_every = max(args.envs * 2048, args.steps // 12)
    callbacks = setup_callbacks(
        run_dir=run_dir,
        n_envs=args.envs,
        ckpt_every_steps=ckpt_every,
        eval_every_steps=ckpt_every,
        eval_env=eval_env,
        n_eval_episodes=args.eval_episodes,
        curriculum=curriculum,
        name_prefix="walk",
        total_timesteps=args.steps,
        verbose=1,
    )
    # вклады членов награды в TensorBoard: rew/<имя>_per_s и rew/<имя>_share
    callbacks.append(RewardLogCallback(dt=0.02, log_freq=200, prefix="rew"))

    print(f"\nПРОГОН: {run_dir}")
    print(f"  шагов {args.steps}, сред {args.envs} ({args.vec}), "
          f"устройство {args.device}")
    t0 = time.perf_counter()
    model.learn(total_timesteps=args.steps, callback=callbacks,
                progress_bar=False)
    wall = time.perf_counter() - t0

    # --- сохранение ПАРОЙ ---------------------------------------------
    model.save(str(run_dir / "final"))
    train_env.save(str(run_dir / "final_vecnormalize.pkl"))
    print(f"\nсохранено ПАРОЙ: final.zip + final_vecnormalize.pkl")

    fps = args.steps / wall if wall > 0 else 0.0
    summary = {
        "steps": int(args.steps),
        "wall_s": round(wall, 1),
        "wall_min": round(wall / 60.0, 2),
        "fps": round(fps, 1),
        "envs": args.envs,
        "vec": args.vec,
        "run_dir": str(run_dir),
        "curriculum_at_end": curriculum.current(),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # --- ЧЕСТНАЯ ОЦЕНКА против пассивной базы -------------------------
    print("\n" + "=" * 78)
    print("ЧЕСТНАЯ ОЦЕНКА: 1g, без куррикулума, против нулевого действия")
    print("=" * 78)
    from rl_toolkit.diagnostics import null_policy_baseline
    base = null_policy_baseline(lambda: WalkEnv(seed=7), seconds=6.0, n=5)
    print(f"пассивная база: {base['alive_steps']:.1f} шагов = "
          f"{base['alive_s']:.2f} с")

    # обученная политика: наблюдения нормируются статистикой ОБУЧАЮЩЕЙ
    # обёртки — той самой, что ушла в парный pkl
    stats = train_env
    ev = WalkEnv(seed=7)
    for cmd in (0.0, 0.4):
        ev.set_cmd_vx(cmd)
        lens = []
        for ep in range(args.eval_episodes):
            obs, _ = ev.reset(seed=200 + ep)
            i = 0
            for i in range(ev.max_steps):
                nobs = stats.normalize_obs(np.asarray(obs, dtype=np.float32))
                act, _ = model.predict(nobs, deterministic=True)
                obs, r, terminated, truncated, _ = ev.step(act)
                if terminated or truncated:
                    break
            lens.append(i + 1)
        mean = float(np.mean(lens))
        verdict = ("ЛУЧШЕ пассивной" if mean > base["alive_steps"]
                   else "НЕ лучше пассивной — политика пока не управляет")
        print(f"cmd {cmd}: длина эпизода {mean:.1f} из {ev.max_steps} "
              f"({mean*ev.dt:.2f} с), эпизоды {lens} -> {verdict}")
    print("\nПланка урока: обогнать 53 шага при 1g. Ходьба (вердикт ХОДИТ =")
    print("слежение >= 60 % и падений <= 20 %) начинается на порядок дальше —")
    print("см. таблицу бюджетов в README.md.")

    train_env.close()
    eval_env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
