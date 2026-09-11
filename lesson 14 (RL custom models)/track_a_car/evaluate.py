"""Честная оценка обученной парковки (трек А урока 14).

Запуск:
    python evaluate.py --run a1                       # лучшая модель прогона
    python evaluate.py --run a1 --ckpt runs/a1/model_final.zip
    python evaluate.py --run a1 --episodes 300 --gif

Чем эта оценка отличается от старой версии урока
(отчёт разбора 04_lesson14_code.md §5.1, §3.3, §6.3, §6.5):

  * Каждый эпизод стартует с ЯВНОГО seed'а: env.reset(seed=REPORT_SEED0+i).
    Старая версия звала reset() без seed, а генератор был жёстко задан в
    __init__, поэтому КАЖДЫЙ вызов evaluate() шёл по одной и той же
    последовательности стартов, и «финальные» 50 эпизодов содержали ровно те
    же 30, по которым выбиралась модель.

  * Диапазон seed'ов для ОТЧЁТА не пересекается с диапазоном, на котором
    колбэк отбирал лучшую модель (SELECT_SEED в train.py). Отбор и отчёт —
    разные выборки, иначе «лучший чекпойнт» вырождается в «самый удачливый».

  * Успехом считается success И НЕ collision. У старой версии множества
    пересекались на 13.9 % поз, и шаг с info={'success':True,'collision':True}
    засчитывался успехом.

  * Рядом с процентом печатается доверительный интервал Уилсона. На 30
    эпизодах при p=0.62 полуширина 95 % ДИ около 17 п.п. — между этапами
    обучения такая разница неотличима от везения.

  * Оценочная среда строится с in_spot_start_prob=0.0 и start_spread=1.0.
    Старый watch_parking.py брал среду с дефолтным 0.2 и показывал 81.5 %
    там, где статья просила сверить с 62 % (§6.3).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import numpy as np

from car_env import DT, GAMMA, MAX_STEPS, SPOT, CarParkingEnv
from rl_toolkit.checkpointing import find_pair, list_pairs, load_policy
from rl_toolkit.diagnostics import Table
from rl_toolkit.probes import probe_controller_sweep
from train import REPORT_SEED0, SELECT_SEED


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Доверительный интервал Уилсона для доли. Возвращает (p, низ, верх).

    Нормальное приближение при малых n и p у краёв даёт границы вне [0, 1];
    Уилсон — нет. Именно поэтому в отчёте стоит он, а не p +- 1.96*sqrt(pq/n).
    """
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, centre - half), min(1.0, centre + half)


def run_episodes(policy, normalize_obs, n: int, seed0: int, collect_traj: int = 0):
    """Прогон n эпизодов с ЯВНЫМИ seed'ами seed0..seed0+n-1."""
    env = CarParkingEnv(in_spot_start_prob=0.0, start_spread=1.0, gamma=GAMMA)
    rows = []
    trajs = []
    term_sum: dict[str, float] = {}
    term_steps = 0
    for i in range(n):
        obs, _ = env.reset(seed=seed0 + i)
        total = 0.0
        info: dict = {}
        for k in range(MAX_STEPS + 1):
            a = policy(normalize_obs(obs))
            obs, r, term, trunc, info = env.step(a)
            total += float(r)
            for key, val in info["terms"].items():
                term_sum[key] = term_sum.get(key, 0.0) + float(val)
            term_steps += 1
            if term or trunc:
                break
        # УСПЕХ = припарковался И НЕ задел. Это не педантизм: у старых ворот
        # 13.9 % поз давали оба флага сразу, и метрика противоречила награде.
        success = bool(info.get("success")) and not bool(info.get("collision"))
        rows.append({
            "seed": seed0 + i,
            "steps": k + 1,
            "seconds": (k + 1) * DT,
            "return": total,
            "success": success,
            "collision": bool(info.get("collision")),
            "oob": bool(info.get("out_of_bounds")),
            "timeout": bool(trunc),
            "dist": float(info.get("dist", float("nan"))),
            "dyaw": float(info.get("dyaw", float("nan"))),
            "speed": float(info.get("speed", float("nan"))),
        })
        if len(trajs) < collect_traj:
            trajs.append((np.array(env.unwrapped._trajectory), rows[-1]))
    env.close()
    terms_per_s = {k: v / term_steps / DT for k, v in term_sum.items()} if term_steps else {}
    return rows, trajs, terms_per_s


def summarise(rows, title: str) -> dict:
    n = len(rows)
    k = sum(r["success"] for r in rows)
    p, lo, hi = wilson(k, n)
    rets = np.array([r["return"] for r in rows])
    print()
    print(f"{title} ({n} эпизодов)")
    print(f"  успех        {k:>4}/{n}  = {100*p:5.1f} %   "
          f"95 % ДИ Уилсона [{100*lo:.1f}, {100*hi:.1f}] "
          f"(полуширина {100*(hi-lo)/2:.1f} п.п.)")
    print(f"  столкновения {sum(r['collision'] for r in rows):>4}/{n}")
    print(f"  за границей  {sum(r['oob'] for r in rows):>4}/{n}")
    print(f"  таймауты     {sum(r['timeout'] for r in rows):>4}/{n}")
    print(f"  возврат      среднее {rets.mean():+8.2f}  ско {rets.std():6.2f}  "
          f"медиана {np.median(rets):+8.2f}")
    ok = [r for r in rows if r["success"]]
    if ok:
        print(f"  у успешных:  время {np.mean([r['seconds'] for r in ok]):.2f} с, "
              f"промах по центру {np.mean([r['dist'] for r in ok]):.3f} м, "
              f"ошибка курса {np.mean([r['dyaw'] for r in ok]):.3f} рад")
    return {"n": n, "k": k, "p": p, "lo": lo, "hi": hi,
            "return": float(rets.mean()), "return_std": float(rets.std())}


def block_table(rows, block: int = 50) -> None:
    """Разброс успешности по непересекающимся блокам.

    Именно эта таблица объясняет, почему в старом уроке появилось «62 %»:
    блоки по 50 эпизодов давали 62 / 82 / 74 / 74 %, и в статью попал
    худший (§5.1).
    """
    if len(rows) < 2 * block:
        return
    t = Table(title=f"разброс успешности по блокам {block} эпизодов",
              columns=["блок", "seed'ы", "успех, %"])
    for i in range(len(rows) // block):
        b = rows[i * block:(i + 1) * block]
        t.add(**{"блок": i + 1,
                 "seed'ы": f"{b[0]['seed']}..{b[-1]['seed']}",
                 "успех, %": 100.0 * sum(r["success"] for r in b) / block})
    print()
    print(t)
    vals = t.column("успех, %")
    print(f"размах между блоками {max(vals) - min(vals):.1f} п.п. — столько стоит "
          f"выбрать «лучший» блок вместо всей выборки")


def save_plots(trajs, terms_per_s, run_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=110)
    # парковка сверху: рамка места, соседи, стены
    ax.add_patch(plt.Rectangle((0.015, -0.59), 1.37, 1.18, fill=False,
                               ec="#d4a017", lw=2, label="целевое место"))
    for yc in (-1.2, 1.2):
        ax.add_patch(plt.Rectangle((0.25, yc - 0.21), 0.9, 0.42,
                                   fc="#3366aa", alpha=0.6))
    ax.add_patch(plt.Rectangle((-0.25, -1.4), 0.1, 2.8, fc="#8a8078"))
    for traj, row in trajs:
        style = "-" if row["success"] else "--"
        ax.plot(traj[:, 0], traj[:, 1], style, lw=1.6,
                label=f"seed {row['seed']}: "
                      f"{'припарковался' if row['success'] else 'не смог'}, "
                      f"R={row['return']:.0f}")
        ax.plot(traj[0, 0], traj[0, 1], "o", ms=6, color=ax.lines[-1].get_color())
    ax.plot(*SPOT, "k+", ms=14, mew=2)
    ax.set_xlim(-0.5, 3.2)
    ax.set_ylim(-2.0, 2.0)
    ax.set_aspect("equal")
    ax.set_xlabel("x, м")
    ax.set_ylabel("y, м")
    ax.set_title("Траектории обученной политики (честные старты)")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p1 = run_dir / "trajectories.png"
    fig.savefig(p1)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.0, 3.8), dpi=110)
    names = list(terms_per_s)
    vals = [terms_per_s[n] for n in names]
    colors = ["#2a9d8f" if v >= 0 else "#e76f51" for v in vals]
    ax.barh(names, vals, color=colors)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_xlabel("награда в секунду")
    ax.set_title("Вклад членов награды на обученной политике")
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    p2 = run_dir / "reward_terms.png"
    fig.savefig(p2)
    plt.close(fig)
    print(f"\nкартинки: {p1.name}, {p2.name}")


def save_gif(policy, normalize_obs, run_dir: Path, seed: int) -> None:
    import imageio.v2 as imageio

    env = CarParkingEnv(render_mode="rgb_array", in_spot_start_prob=0.0,
                        start_spread=1.0, gamma=GAMMA)
    obs, _ = env.reset(seed=seed)
    frames = []
    for _ in range(MAX_STEPS):
        a = policy(normalize_obs(obs[None, :])[0]) if normalize_obs else policy(obs)
        obs, _, term, trunc, _ = env.step(a)
        frames.append(env.render())
        if term or trunc:
            break
    env.close()          # обязателен: освобождает GL-контекст рендерера
    out = run_dir / "parking.gif"
    # fps = 1/DT: metadata среды и реальная частота управления совпадают,
    # поэтому гифка идёт в реальном времени (§1.4, §6.4).
    imageio.mimsave(out, frames, fps=int(round(1.0 / DT)), loop=0)
    print(f"гифка: {out.name} ({len(frames)} кадров, {len(frames)*DT:.1f} с)")


def main() -> int:
    p = argparse.ArgumentParser(description="Честная оценка парковки, трек А")
    p.add_argument("--run", type=str, default="a1")
    p.add_argument("--ckpt", type=str, default=None,
                   help="конкретный .zip; по умолчанию best_model, иначе model_final")
    p.add_argument("--episodes", type=int, default=200, help="эпизодов ОТЧЁТА")
    p.add_argument("--select-episodes", type=int, default=100,
                   help="эпизодов на НЕЗАВИСИМОМ наборе отбора (для сравнения)")
    p.add_argument("--sweep-episodes", type=int, default=20,
                   help="эпизодов на точку свипа сложности")
    p.add_argument("--gif", action="store_true")
    p.add_argument("--device", type=str, default="cpu")
    args = p.parse_args()

    run_dir = HERE / "runs" / args.run
    if args.ckpt:
        ckpt = Path(args.ckpt)
    else:
        for cand in ("best_model.zip", "model_final.zip"):
            ckpt = run_dir / cand
            if ckpt.exists():
                break
        else:
            print(f"в {run_dir} нет ни best_model.zip, ни model_final.zip")
            return 1
    if not ckpt.exists():
        print(f"нет файла {ckpt}")
        return 1

    pair = find_pair(ckpt, run_dir=run_dir, prefix="model")
    print("=" * 78)
    print("ЧЕСТНАЯ ОЦЕНКА, трек А")
    print("=" * 78)
    print(f"модель          {pair.model_path.name}")
    print(f"VecNormalize    {pair.vecnorm_path.name if pair.vecnorm_path else 'НЕТ'}")
    print(f"парность        {pair.note}")
    if not pair.paired:
        print("  ВНИМАНИЕ: без своей статистики нормировки политика видит СМЕЩЁННЫЕ")
        print("  наблюдения. Числа ниже занижены и сравнивать их с парным")
        print("  чекпойнтом нельзя.")

    model, normalize_obs = load_policy(pair, device=args.device)
    print(f"абсолютный счётчик модели: {model.num_timesteps}")
    print(f"gamma модели {model.gamma}, gamma среды {GAMMA} -> "
          f"{'совпадают' if abs(model.gamma - GAMMA) < 1e-12 else 'РАСХОДЯТСЯ'}")

    def policy(o):
        a, _ = model.predict(o, deterministic=True)
        return a

    print()
    print(f"набор ОТБОРА  : seed'ы {SELECT_SEED}.. (их видел колбэк во время обучения)")
    print(f"набор ОТЧЁТА  : seed'ы {REPORT_SEED0}.. (модель их НЕ видела)")

    sel_rows, _, _ = run_episodes(policy, normalize_obs,
                                  args.select_episodes, SELECT_SEED)
    s_sel = summarise(sel_rows, "НАБОР ОТБОРА (на нём выбиралась лучшая модель)")

    rep_rows, trajs, terms = run_episodes(policy, normalize_obs, args.episodes,
                                          REPORT_SEED0, collect_traj=4)
    s_rep = summarise(rep_rows, "НАБОР ОТЧЁТА (независимый) — ЭТО И ЕСТЬ ЧЕСТНОЕ ЧИСЛО")

    print()
    print(f"разница отбор минус отчёт: {100*(s_sel['p'] - s_rep['p']):+.1f} п.п.")
    print("Если она велика, модель подогнана под набор отбора — ровно это и")
    print("произошло бы у старой версии, где оба набора совпадали.")

    block_table(rep_rows, block=50)

    print()
    t = Table(title="вклад членов награды на обученной политике (набор отчёта)",
              columns=["член", "награда/с", "доля |суммы|"])
    tot = sum(abs(v) for v in terms.values()) or 1.0
    for k in sorted(terms, key=lambda x: -abs(terms[x])):
        t.add(**{"член": k, "награда/с": terms[k], "доля |суммы|": abs(terms[k]) / tot})
    print(t)

    # чекпойнты прогона — видно ли рост
    pairs = list_pairs(run_dir, prefix="model")
    if len(pairs) >= 2:
        print()
        tt = Table(title="успех по чекпойнтам (набор отчёта, по 40 эпизодов)",
                   columns=["шагов", "чекпойнт", "успех, %", "возврат", "парный"])
        for pr in pairs:
            m2, norm2 = load_policy(pr, device=args.device)
            rows2, _, _ = run_episodes(
                lambda o: m2.predict(o, deterministic=True)[0], norm2, 40, REPORT_SEED0)
            tt.add(**{"шагов": pr.steps, "чекпойнт": pr.model_path.name,
                      "успех, %": 100.0 * sum(r["success"] for r in rows2) / 40,
                      "возврат": float(np.mean([r["return"] for r in rows2])),
                      "парный": pr.paired})
        print(tt)

    # ---- свип сложности НА ГОТОВЫХ ВЕСАХ --------------------------------
    # start_spread — та самая рампа куррикулума. Свип показывает, насколько
    # политика держится, когда задачу возвращают к честной. Если успех резко
    # падает у правого края, модель выучила облегчённую версию задачи.
    print()
    sweep_env = CarParkingEnv(in_spot_start_prob=0.0, gamma=GAMMA)

    def success_metric(rollout):
        info = rollout[-1]["info"]
        return float(bool(info.get("success")) and not bool(info.get("collision")))

    tsw = probe_controller_sweep(
        sweep_env,
        policy=lambda o: policy(normalize_obs(o)),
        param="start_spread",
        values=(0.0, 0.25, 0.5, 0.75, 1.0),
        metric=success_metric,
        seconds=MAX_STEPS * DT,
        episodes=args.sweep_episodes,
        seed=REPORT_SEED0,
    )
    print(tsw)
    print("метрика — доля успешных эпизодов; 1.0 по оси start_spread — честная задача")
    sweep_env.close()

    save_plots(trajs, terms, run_dir)
    if args.gif:
        save_gif(policy, normalize_obs, run_dir, REPORT_SEED0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
