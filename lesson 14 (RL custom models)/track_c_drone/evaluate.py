"""Честная оценка обеих ступеней трека C + сравнение с базами.

    python evaluate.py --scan runs/scan --hover runs/hover
    python evaluate.py --scan runs/scan --episodes 30 --images

ЧЕМ ЭТА ОЦЕНКА ОТЛИЧАЕТСЯ ОТ ЧИСЛА В ЛОГЕ ОБУЧЕНИЯ

 1. Среда C2 здесь всегда с `cov_target = 1.01`, то есть порог НЕДОСТИЖИМ
    и эпизод идёт до конца. Мерить качество в среде, которая обрывает эпизод
    ПО ЭТОЙ ЖЕ метрике, нельзя: получится «потолок 0.9167», которого
    не существует, а сравнение политик станет бессмысленным.

 2. Метрика зачёта — ВРЕМЯ до 0.85, а не покрытие на момент останова.
    За полный эпизод покрытие берут все, и скрипт, и политика; отличаются
    они скоростью.

 3. Политика грузится ПАРОЙ ckpt+vecnorm через rl_toolkit.checkpointing:
    чужая статистика нормализации — это другая политика, а не «чуть хуже».
    Для C2 это критичнее, чем для любого другого трека урока: в наблюдении
    лежит карта покрытия, распределение которой по ходу обучения меняется
    радикально (у случайной политики карта пустая, у обученной — полная).

 4. Сравнение идёт СРАЗУ С ТРЕМЯ базами: нулевая политика, случайная и
    скриптовый облёт. Без скриптовой базы неизвестно, что вообще даёт
    задача; без случайной — неизвестно, различает ли награда политики.
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse                                                    # noqa: E402
import sys                                                         # noqa: E402
import time                                                        # noqa: E402
from pathlib import Path                                           # noqa: E402

import numpy as np                                                 # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rl_toolkit.checkpointing import list_pairs, load_policy       # noqa: E402
from rl_toolkit.diagnostics import Table                           # noqa: E402

from hover_env import HoverEnv                                     # noqa: E402
from scan_env import DroneScanEnv, orbit_policy                    # noqa: E402

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
def _last_pair(run_dir: Path):
    """Последняя ПАРА ckpt+vecnorm в каталоге прогона (или None)."""
    pairs = list_pairs(run_dir)
    if not pairs:
        return None
    pair = pairs[-1]
    print(f"[чекпойнт] {pair}")
    return pair


def scan_episode(env: DroneScanEnv, act_fn, seed: int, track_map=False):
    """Один эпизод C2. Возвращает историю покрытия и итог.

    ЛОВУШКА, из-за которой существует `track_map`: векторные обёртки SB3
    делают авто-reset на done, и карта покрытия в объекте среды обнуляется
    ДО того, как её успеешь прочитать. Первая версия картинки нарисовала
    пустую карту с подписью «покрытие 100 %». Поэтому снимок карты берётся
    НА КАЖДОМ шаге, а не в конце.
    """
    obs, _ = env.reset(seed=seed)
    hist = []
    snaps = []
    t85 = None
    info = {}
    i = 0
    for i in range(env.max_steps):
        obs, r, te, tr, info = env.step(act_fn(env, i, obs))
        hist.append(info["coverage"])
        if track_map and (i % 50 == 0 or i == env.max_steps - 1):
            snaps.append((i + 1, env.seen.copy()))
        if t85 is None and info["coverage"] >= 0.85:
            t85 = i + 1
        if te or tr:
            break
    crash = bool(info.get("crash") or info.get("out"))
    return {"coverage": info.get("coverage", 0.0), "t85": t85, "steps": i + 1,
            "crash": crash,
            # Авария ПОСЛЕ выхода на 0.85 — не провал задачи, а выход за пределы
            # того, чему политику учили: в обучающей среде эпизод на пороге
            # обрывался, и «что делать дальше» она не видела ни разу.
            # Считать её наравне с аварией по дороге — значит штрафовать
            # политику за режим, которого в её обучении не существовало.
            "crash_before": crash and t85 is None,
            "hist": hist, "snaps": snaps}


def eval_scan(policies: dict, n_ep: int, images: bool) -> Table:
    t = Table(title=f"C2 «Сканер»: честная оценка, {n_ep} эпизодов, cov_target = 1.01 "
                    f"(порог недостижим, эпизод идёт все 1500 шагов)",
              columns=["политика", "покрытие", "худший эп.", "дошли до 0.85",
                       "шагов до 0.85 (медиана)", "аварий до 0.85", "аварий всего", "с"])
    curves = {}
    for name, act_fn in policies.items():
        t0 = time.perf_counter()
        covs, t85s, crashes, cr_before, hists = [], [], 0, 0, []
        for ep in range(n_ep):
            env = DroneScanEnv(seed=0, cov_target=1.01)
            r = scan_episode(env, act_fn(), 700 + ep, track_map=False)
            covs.append(r["coverage"])
            crashes += int(r["crash"])
            cr_before += int(r["crash_before"])
            hists.append(r["hist"])
            if r["t85"] is not None:
                t85s.append(r["t85"])
            env.close()
        curves[name] = hists
        t.add(**{"политика": name, "покрытие": float(np.mean(covs)),
                 "худший эп.": float(np.min(covs)),
                 "дошли до 0.85": f"{len(t85s)}/{n_ep}",
                 "шагов до 0.85 (медиана)": (int(np.median(t85s)) if t85s else None),
                 "аварий до 0.85": cr_before / n_ep, "аварий всего": crashes / n_ep,
                 "с": round(time.perf_counter() - t0, 1)})
    t.note = ("Читать по колонке «шагов до 0.85», а не по «покрытию»: за полный эпизод "
              "покрытие берут и скрипт, и политика — они отличаются СКОРОСТЬЮ.\n"
              "Две колонки аварий — не придирка. В ОБУЧАЮЩЕЙ среде эпизод обрывался "
              "на пороге 0.85, поэтому «что делать после того, как всё снято» политика "
              "не видела ни разу; здесь порог недостижим, и она продолжает летать "
              "за пределами своего опыта. Провал задачи — это только левая колонка.\n"
              "Критерии C2: медиана шагов до 0.85 < 600, доля дошедших >= 0.90, "
              "покрытие за эпизод >= 0.95, аварий ДО порога <= 0.05")
    if images:
        _draw_curves(curves)
    return t


def _draw_curves(curves: dict) -> None:
    """coverage_curve.png — главная картинка трека: покрытие от номера шага."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:                                   # noqa: BLE001
        print(f"[картинки] matplotlib недоступен ({e}) — пропуск")
        return
    img = HERE / "images"
    img.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=130)
    for name, hists in curves.items():
        L = max(len(h) for h in hists)
        M = np.full((len(hists), L), np.nan)
        for i, h in enumerate(hists):
            M[i, :len(h)] = h
            M[i, len(h):] = h[-1]
        med = np.nanmedian(M, axis=0)
        ax.plot(np.arange(1, L + 1), med, label=name, lw=1.8)
        idx = np.argmax(med >= 0.85) if (med >= 0.85).any() else None
        if idx:
            ax.axvline(idx + 1, ls="--", lw=0.9, alpha=0.5,
                       color=ax.lines[-1].get_color())
    ax.axhline(0.85, color="0.4", ls=":", lw=1)
    ax.set_xlabel("шаг эпизода (50 Гц)")
    ax.set_ylabel("доля покрытия")
    ax.set_title("C2: покрытие от времени, медиана по эпизодам\n"
                 "(пунктир — выход на 0.85)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(img / "coverage_curve.png")
    plt.close(fig)
    print(f"[картинки] {img / 'coverage_curve.png'}")


def draw_map(pair, n_steps=(100, 300, 600, 1500)) -> None:
    """coverage_map.png — киноплёнка развёртки: карта в четыре момента времени.

    Одна панель на политику бесполезна: к концу эпизода обе карты полные.
    Показывать надо, КАК они заполняются.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:                                   # noqa: BLE001
        print(f"[картинки] matplotlib недоступен ({e}) — пропуск")
        return
    rows = []
    labels = []
    pol = orbit_policy()
    rows.append(("скриптовый облёт", lambda: (lambda e, i, o: pol(e, i))))
    if pair is not None:
        model, norm = load_policy(pair, device="cpu")

        def ppo_fn():
            def f(e, i, o):
                a, _ = model.predict(norm(o)[None], deterministic=True)
                return a[0]
            return f
        rows.append(("PPO", ppo_fn))

    fig, axes = plt.subplots(len(rows), len(n_steps), figsize=(3.0 * len(n_steps),
                                                              2.4 * len(rows)), dpi=130)
    axes = np.atleast_2d(axes)
    for r, (name, mk) in enumerate(rows):
        env = DroneScanEnv(seed=0, cov_target=1.01)
        res = scan_episode(env, mk(), 700, track_map=True)
        snaps = dict(res["snaps"])
        for c, ns in enumerate(n_steps):
            key = min(snaps, key=lambda k: abs(k - ns))
            m = snaps[key]
            ax = axes[r, c]
            ax.imshow(m.T, origin="lower", aspect="auto", cmap="viridis",
                      vmin=0, vmax=1, interpolation="nearest")
            # если эпизод оборвался раньше запрошенного шага, это надо ПОДПИСАТЬ,
            # иначе три одинаковые панели читаются как «политика перестала снимать»
            tail = "" if key >= ns else f" (эпизод оборвался на {key})"
            ax.set_title(f"{name}, шаг {min(key, ns)}{tail}\n"
                         f"покрытие {m.mean():.2f}", fontsize=8)
            ax.set_xticks([])
            ax.set_yticks([])
        env.close()
        labels.append(name)
    axes[0, 0].set_ylabel("полосы по высоте")
    fig.suptitle("Развёртка объекта 16 x 6: как заполняется карта покрытия", fontsize=10)
    fig.tight_layout()
    img = HERE / "images"
    img.mkdir(exist_ok=True)
    fig.savefig(img / "coverage_map.png")
    plt.close(fig)
    print(f"[картинки] {img / 'coverage_map.png'}")


def eval_hover(pair, n_ep: int) -> Table:
    t = Table(title=f"C1 «Зависание»: честная оценка, {n_ep} эпизодов, полная сложность",
              columns=["политика", "прожито шагов из 500", "доля доживших",
                       "финальная ошибка, м"])
    fns = {"нулевое действие (= тяга висения)": lambda: (lambda o: np.zeros(4))}
    rng = np.random.default_rng(0)
    fns["случайное действие"] = lambda: (lambda o: rng.uniform(-1, 1, 4))
    if pair is not None:
        model, norm = load_policy(pair, device="cpu")
        fns["PPO"] = lambda: (lambda o: model.predict(norm(o)[None],
                                                      deterministic=True)[0][0])
    for name, mk in fns.items():
        lens, dists, surv = [], [], 0
        fn = mk()
        for ep in range(n_ep):
            env = HoverEnv(seed=900)
            obs, _ = env.reset(seed=5000 + ep)
            info = {}
            i = 0
            for i in range(env.max_steps):
                obs, r, te, tr, info = env.step(fn(obs))
                if te or tr:
                    break
            lens.append(i + 1)
            dists.append(float(info.get("final_dist", 9.0)))
            surv += int(bool(info.get("survived")))
            env.close()
        t.add(**{"политика": name, "прожито шагов из 500": float(np.mean(lens)),
                 "доля доживших": surv / n_ep,
                 "финальная ошибка, м": float(np.mean(dists))})
    t.note = "Критерий C1: доля доживших >= 0.90 И средняя финальная ошибка <= 0.25 м"
    return t


def main() -> int:
    ap = argparse.ArgumentParser(description="Честная оценка трека C")
    ap.add_argument("--scan", default=str(HERE / "runs" / "scan"))
    ap.add_argument("--hover", default=str(HERE / "runs" / "hover"))
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--images", action="store_true", help="нарисовать png в images/")
    ap.add_argument("--skip-hover", action="store_true")
    ap.add_argument("--skip-scan", action="store_true")
    a = ap.parse_args()

    if not a.skip_scan:
        pair_s = _last_pair(Path(a.scan)) if Path(a.scan).exists() else None
        if pair_s is None:
            print(f"[C2] в {a.scan} нет чекпойнтов — оцениваем только базы")
        rng = np.random.default_rng(0)
        pols = {
            "нулевое действие": lambda: (lambda e, i, o: np.zeros(4)),
            "случайное действие": lambda: (lambda e, i, o: rng.uniform(-1, 1, 4)),
            "скриптовый облёт": lambda: (lambda e, i, o, _p=orbit_policy(): _p(e, i)),
        }
        if pair_s is not None:
            model, norm = load_policy(pair_s, device="cpu")

            def ppo():
                def f(e, i, o):
                    act, _ = model.predict(norm(o)[None], deterministic=True)
                    return act[0]
                return f
            pols["PPO"] = ppo
        print(eval_scan(pols, a.episodes, a.images), "\n")
        if a.images:
            draw_map(pair_s)

    if not a.skip_hover:
        pair_h = _last_pair(Path(a.hover)) if Path(a.hover).exists() else None
        if pair_h is None:
            print(f"[C1] в {a.hover} нет чекпойнтов — оцениваем только базы")
        print(eval_hover(pair_h, a.episodes), "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
