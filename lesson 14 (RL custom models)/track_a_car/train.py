"""Обучение PPO парковке (трек А урока 14) на rl_toolkit.

Запуск:
    python train.py --steps 150000 --envs 8          # короткий прогон
    python train.py --steps 3000000 --envs 12        # полный прогон
    python train.py --steps 1000000 --resume runs/a1/model_150016_steps.zip

Что здесь принципиально иначе, чем в старой версии урока
(отчёт разбора 04_lesson14_code.md):

  * ОДИН вызов learn(), а не пять в цикле. У старой версии этапы шли циклом
    без reset_num_timesteps=False: счётчик шагов обнулялся на каждом этапе,
    в logs/ накопилось 34 каталога PPO_1..PPO_34, а кривая в TensorBoard была
    разорвана на 34 куска (§5.7). При --resume здесь явно передаётся
    reset_num_timesteps=False.

  * learning_rate — РАСПИСАНИЕ (callable), а не число. Присваивание
    `model.learning_rate = 1e-4` после load() — молчаливый no-op: PPO читает
    self.lr_schedule, который собирается один раз в _setup_lr_schedule()
    (§5.6). Здесь расписание задаётся при создании модели и пересобирается
    явно при resume.

  * VecNormalize(norm_obs, norm_reward). Шаговая награда и терминальные
    +100/-30 различаются на три порядка; без нормировки цели критика скачут
    от -30 до +100 при типичном шаге 0.02 (§5.5).

  * Куррикулум ГАСНЕТ. Трюк «старт уже на месте» в старой версии стоял
    константой 0.2, и ровно 20 % эпизодов были халявой ровно на 164.92 —
    кривая обучения показывала 81 при честных 60 (§3.4). Здесь рампа
    опускает его до нуля к середине бюджета, а eval-среда трюка не видит
    НИКОГДА.

  * Отбор модели и отчёт идут на РАЗНЫХ наборах эпизодов: eval-среда
    засеяна SELECT_SEED, evaluate.py считает по seed'ам из другого,
    непересекающегося диапазона (§5.1).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.utils import get_linear_fn
from stable_baselines3.common.vec_env import (
    DummyVecEnv, SubprocVecEnv, VecNormalize,
)

from car_env import DT, GAMMA, MAX_STEPS, CarParkingEnv
from rl_toolkit.checkpointing import list_pairs, make_eval_env, setup_callbacks
from rl_toolkit.curriculum import CurriculumCallback, explain, linear
from rl_toolkit.rewards import RewardLogCallback

# Наборы seed'ов. Отбор модели и итоговый отчёт НЕ ПЕРЕСЕКАЮТСЯ (§5.1):
# у старой версии обе процедуры шли по одному и тому же потоку default_rng(0),
# и «лучший этап» вырождался в «самый удачливый».
SELECT_SEED = 100_000          # eval-среда колбэка отбора
REPORT_SEED0 = 900_000         # см. evaluate.py

INFO_KEYS = ("success", "collision", "out_of_bounds", "curriculum")


def make_env(rank: int, seed: int, train: bool):
    """Фабрика среды. Должна быть на уровне модуля — SubprocVecEnv её пикает."""

    def _init():
        env = CarParkingEnv(
            # Стартовые значения рамп. Куррикулум перезапишет их на первом же
            # шаге; здесь они стоят на случай запуска без куррикулума.
            in_spot_start_prob=0.35 if train else 0.0,
            start_spread=0.30 if train else 1.0,
            gamma=GAMMA,
        )
        env.reset(seed=seed + rank)
        return Monitor(env, info_keywords=INFO_KEYS)

    return _init


def build_train_env(n_envs: int, seed: int) -> VecNormalize:
    fns = [make_env(i, seed, train=True) for i in range(n_envs)]
    # SubprocVecEnv окупается от 4 сред: замер probe.py показал ~5300 шагов
    # политики в секунду в одном процессе, то есть 0.05 ч на 1 млн шагов.
    venv = SubprocVecEnv(fns) if n_envs > 1 else DummyVecEnv(fns)
    return VecNormalize(
        venv,
        training=True,
        norm_obs=True,
        norm_reward=True,
        clip_obs=10.0,
        clip_reward=10.0,
        # gamma ОБЯЗАНА совпадать с gamma алгоритма и среды: VecNormalize
        # нормирует награду по дисконтированной сумме, и расхождение здесь
        # тихо ломает масштаб.
        gamma=GAMMA,
    )


def build_eval_env() -> VecNormalize:
    """Честная оценочная среда: ни трюка со стартом на месте, ни лёгкого разброса."""
    fn = make_env(0, SELECT_SEED, train=False)
    venv = make_eval_env(fn, clip_obs=10.0, gamma=GAMMA)
    venv.seed(SELECT_SEED)
    return venv


def main() -> int:
    p = argparse.ArgumentParser(description="Обучение PPO парковке, трек А")
    p.add_argument("--steps", type=int, default=1_500_000, help="env-шагов в этом запуске")
    p.add_argument("--envs", type=int, default=8, help="параллельных сред")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--run", type=str, default="a1", help="имя каталога прогона в runs/")
    p.add_argument("--resume", type=str, default=None, help="путь к .zip чекпойнту")
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--eval-episodes", type=int, default=20)
    p.add_argument("--device", type=str, default="cpu")
    args = p.parse_args()

    run_dir = HERE / "runs" / args.run
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print(f"ОБУЧЕНИЕ, трек А. Каталог прогона: {run_dir}")
    print("=" * 78)
    print(f"шагов в этом запуске : {args.steps}")
    print(f"параллельных сред    : {args.envs}")
    print(f"dt={DT} с ({1/DT:.0f} Гц), эпизод {MAX_STEPS} шагов = {MAX_STEPS*DT:.1f} с")
    print(f"gamma={GAMMA} -> эффективный горизонт {DT/(1-GAMMA):.1f} с")

    train_env = build_train_env(args.envs, args.seed)
    eval_env = build_eval_env()

    # Буфер держим около 4096 переходов = ~23 эпизода по 180 шагов. Меньше —
    # и терминальный +100 встречается в буфере единицы раз (§5.4).
    #
    # n_steps округляется ВВЕРХ до кратного N_MINIBATCHES, а batch_size из него
    # выводится. Так буфер делится на batch_size при ЛЮБОМ числе сред.
    # Если задать batch_size константой, ломается ровно то, что рекомендуют
    # в README: при --envs 12 выходило n_steps=341, буфер 4092, и 4092 % 512
    # не ноль. SB3 в таком случае молча берёт последний неполный минибатч
    # (ppo.py:196-204 печатает предупреждение), а здесь стояло assert.
    N_MINIBATCHES = 8
    target_buffer = 4096
    per_env = max(128, -(-target_buffer // args.envs))          # ceil
    n_steps = -(-per_env // N_MINIBATCHES) * N_MINIBATCHES      # вверх до кратного
    buffer = n_steps * args.envs
    batch_size = buffer // N_MINIBATCHES
    assert buffer % batch_size == 0, "буфер обязан делиться на batch_size"
    print(f"буфер {buffer} переходов = {n_steps} шагов x {args.envs} сред; "
          f"{N_MINIBATCHES} минибатчей по {batch_size}; "
          f"это примерно {buffer / MAX_STEPS:.1f} эпизодов на обновление")

    # Расписание LR — callable. Именно так его читает PPO._update_learning_rate.
    lr_schedule = get_linear_fn(args.lr, args.lr * 0.1, 1.0)

    if args.resume:
        model = PPO.load(args.resume, env=train_env, device=args.device)
        # Пересобрать расписание ЯВНО: без этой строки правка LR — no-op (§5.6).
        model.learning_rate = lr_schedule
        model._setup_lr_schedule()
        vn = Path(args.resume).with_name(
            Path(args.resume).stem.replace("_steps", "_vecnormalize_") + ".pkl")
        if vn.exists():
            train_env = VecNormalize.load(str(vn), train_env.venv)
            train_env.training = True
            train_env.norm_reward = True
            model.set_env(train_env)
            print(f"[resume] подхвачена статистика VecNormalize: {vn.name}")
        else:
            print(f"[resume] ВНИМАНИЕ: пары к чекпойнту нет ({vn.name}); "
                  f"статистика obs_rms начнётся заново — первые тысячи шагов "
                  f"политика будет видеть смещённые наблюдения")
        t0 = int(model.num_timesteps)
        print(f"[resume] продолжаем с абсолютного шага {t0}")
    else:
        model = PPO(
            "MlpPolicy",
            train_env,
            policy_kwargs={
                "net_arch": [64, 64],
                # ТИХИЙ СТАРТ. SB3-дефолт log_std_init=0.0 -> std=1.0, и
                # начальная политика физически не может простоять 8 шагов
                # (0.4 с) внутри ворот: порог успеха 0.15 м/с при полной
                # команде 1.0 м/с, то есть уже |a[1]| > 0.15 выбивает из ворот.
                # Замер (build/track_a/m11_logstd.py, 60 эпизодов со стартом
                # НА МЕСТЕ, доля успеха начальной гауссовой политики):
                #   log_std= 0.0 (std 1.000) ->  21.7 %, длина эп. 83.3, R  +9.81
                #   log_std=-1.0 (std 0.368) ->  80.0 %, длина эп. 46.7, R +78.50
                #   log_std=-1.6 (std 0.202) -> 100.0 %, длина эп. 12.7, R +99.92
                #   log_std=-2.3 (std 0.100) -> 100.0 %, длина эп.  8.0, R +100.1
                # Обратная сторона — разведка на дороге сужается (смещение за
                # эпизод при честном старте): 0.628 м при std=1.0, 0.344 м при
                # std=0.368, 0.131 м при std=0.202, 0.043 м при std=0.100.
                # Взято -1.0: трюк со стартом на месте уже работает (80 %),
                # а разведка ужата вдвое, а не в пять раз. Точка ВНУТРИ
                # диапазона, не на краю. Дальше std обучаемый — PPO поднимет
                # его сам, если понадобится.
                "log_std_init": -1.0,
            },
            n_steps=n_steps,
            batch_size=batch_size,
            n_epochs=10,
            learning_rate=lr_schedule,
            gamma=GAMMA,            # совпадает с gamma среды и VecNormalize
            gae_lambda=0.95,
            ent_coef=0.005,
            clip_range=0.2,
            verbose=1,
            tensorboard_log=str(run_dir / "tb"),
            seed=args.seed,
            device=args.device,
        )
        t0 = 0

    # ---- куррикулум ------------------------------------------------------
    # Рампы считаются от АБСОЛЮТНОГО счётчика модели, поэтому при resume
    # расписание не начинается заново (см. шапку rl_toolkit.curriculum).
    total = int(args.steps)
    schedule = {
        # Трюк «старт уже на месте» ОБЯЗАН угаснуть: иначе метрика обучения
        # смешивает халявные эпизоды с честными (§3.4).
        "set_in_spot_start_prob": linear(hold=t0, ramp=max(1, total // 2),
                                         lo=0.35, hi=0.0),
        # Разброс старта, наоборот, растёт до честного.
        "set_start_spread": linear(hold=t0, ramp=max(1, int(total * 0.6)),
                                   lo=0.30, hi=1.0),
    }
    print()
    print(explain(schedule, timesteps=t0, total=total))
    print()
    print("sync_to_eval пуст намеренно: обе рампы ОБЛЕГЧАЮТ задачу, а метрика")
    print("обязана считаться на честной. eval-среда всегда видит")
    print("in_spot_start_prob=0.0 и start_spread=1.0.")
    print()

    curriculum = CurriculumCallback(
        train_env, eval_env, schedule=schedule,
        sync_to_eval=frozenset(),      # ничего не синхронизируем — см. выше
        # min_delta=0.01, а не 0.0. У линейной рампы значение меняется на
        # КАЖДОМ шаге, а рассылка идёт через env_method, то есть у SubprocVecEnv
        # это межпроцессный вызов. Замер на 4 средах: min_delta=0.0 -> 355
        # env-шагов/с, min_delta=0.01 -> см. распечатку в конце прогона.
        # Точность не страдает: 0.01 на рампе 0.35..0 — это 35 ступенек.
        min_delta=0.01, verbose=1,
    )

    ckpt_every = max(10_000, total // 10)
    callbacks = setup_callbacks(
        run_dir=run_dir,
        n_envs=args.envs,
        ckpt_every_steps=ckpt_every,
        eval_every_steps=2 * ckpt_every,
        eval_env=eval_env,
        n_eval_episodes=args.eval_episodes,
        curriculum=curriculum,
        name_prefix="model",
        total_timesteps=total,
        deterministic=True,
        verbose=1,
    )
    callbacks.append(RewardLogCallback(dt=DT, log_freq=1000))

    print()
    t_start = time.perf_counter()
    model.learn(
        total_timesteps=total,
        callback=callbacks,
        # ЕДИНСТВЕННЫЙ вызов learn(). При resume счётчик НЕ обнуляется — это
        # и есть починка §5.7.
        reset_num_timesteps=(args.resume is None),
        tb_log_name="ppo",
        progress_bar=False,
    )
    wall = time.perf_counter() - t_start

    model.save(run_dir / "model_final")
    train_env.save(str(run_dir / "model_final_vecnormalize_.pkl"))
    print()
    print(f"обучение заняло {wall/60:.1f} мин; "
          f"{model.num_timesteps/max(wall,1e-9):.0f} env-шагов/с")
    print(f"абсолютный счётчик модели: {model.num_timesteps}")

    # ---- проверка парности чекпойнтов -----------------------------------
    print()
    print("ЧЕКПОЙНТЫ (парность ckpt + VecNormalize):")
    pairs = list_pairs(run_dir, prefix="model")
    for pr in pairs:
        print(f"  {pr.steps:>9}  {pr.model_path.name:<34} "
              f"vecnorm={'есть' if pr.vecnorm_path else 'НЕТ':<4} {pr.note}")
    unpaired = [pr for pr in pairs if not pr.paired]
    if unpaired:
        print(f"  ВНИМАНИЕ: без пары {len(unpaired)} шт. — чужая статистика "
              f"нормировки даёт смещённые наблюдения")
    else:
        print(f"  все {len(pairs)} чекпойнтов парные")

    print()
    print(f"Дальше: python evaluate.py --run {args.run}")
    train_env.close()
    eval_env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
