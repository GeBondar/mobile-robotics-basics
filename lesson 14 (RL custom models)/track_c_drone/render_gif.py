# -*- coding: utf-8 -*-
"""Гифки трека C: зависание (C1) и облёт объекта (C2).

    python render_gif.py                       # обе ступени
    python render_gif.py --only hover
    python render_gif.py --only scan --seconds 20

Камеры здесь ЕСТЬ в самих моделях: quad.xml несёт `chase` и `nearby`,
scan_scene.xml — `overview` и `chase`. Это удобнее следящей камеры трека B:
поза камеры лежит рядом с геометрией и не разъезжается с ней.

Перед записью каждая камера проверяется rl_toolkit.probes.probe_cameras —
чёрный кадр дешевле поймать до прогона, чем объяснять потом. Именно так
в этом уроке и вскрылась камера вида сверху трека A, смотревшая в пустоту.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from rl_toolkit.checkpointing import find_pair, list_pairs, load_policy  # noqa: E402
from rl_toolkit.probes import probe_cameras                             # noqa: E402
from rl_toolkit.render import record_frames, save_gif                   # noqa: E402


def _latest(run_dir: Path):
    """Последняя пара «веса + парная нормализация» в каталоге прогона."""
    pairs = list_pairs(run_dir, prefix="model")
    if not pairs:
        raise FileNotFoundError("нет чекпойнтов в %s" % run_dir)
    return pairs[-1]


def _check_cameras(model, want: str) -> None:
    rows = probe_cameras(model)
    for r in rows:
        print("   {камера:<14} яркость {яркость:>7} цветов {цветов:>5}  {вердикт}"
              .format(**r))
    bad = [r for r in rows if r["камера"] == want and r["вердикт"] != "OK"]
    if bad:
        raise SystemExit("камера %r даёт пустой кадр — чинить позу камеры в MJCF" % want)


def record(kind: str, run: Path, out: Path, seconds: float, camera: str,
           width: int, height: int, every: int, colors: int, max_width: int) -> None:
    if kind == "hover":
        from hover_env import HoverEnv
        env = HoverEnv(seed=900)
    else:
        from scan_env import DroneScanEnv
        env = DroneScanEnv(seed=0, cov_target=1.01)

    print("\n%s: %s" % (kind, run))
    _check_cameras(env.model, camera)

    pair = _latest(run)
    print("   пара: %s | %s" % (pair.model_path.name, pair.note))
    model_pi, norm = load_policy(pair, device="cpu")

    obs, _ = env.reset(seed=900 if kind == "hover" else 0)
    dt = float(getattr(env, "dt", 0.02))
    n = min(int(env.max_steps), int(round(seconds / dt)))
    state = {"obs": obs}

    def step() -> bool:
        act, _ = model_pi.predict(norm(state["obs"]), deterministic=True)
        o, _, term, trunc, _ = env.step(act)
        state["obs"] = o
        return not (term or trunc)

    frames = record_frames(env.model, env.data, step, n_steps=n, camera=camera,
                           width=width, height=height)
    print("   снято %d шагов из %d (%s)"
          % (len(frames), n, "дошёл до конца" if len(frames) == n else "оборвался"))
    save_gif(frames, out, fps=1.0 / dt, max_width=max_width,
             colors=colors, every=every)
    env.close()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=("hover", "scan"), default=None)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=420)
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--colors", type=int, default=64)
    ap.add_argument("--max-width", type=int, default=400)
    # По умолчанию берётся свой прогон runs/<ступень>. Эти два флага
    # позволяют снять гифку с ГОТОВЫХ весов из policies/ — например,
    # пока своё обучение ещё идёт.
    ap.add_argument("--hover-run", default=None)
    ap.add_argument("--scan-run", default=None)
    a = ap.parse_args()

    img = HERE / "images"
    jobs = []
    if a.only in (None, "hover"):
        jobs.append(("hover", Path(a.hover_run) if a.hover_run else HERE / "runs" / "hover", img / "hover.gif",
                     a.seconds or 8.0, "chase"))
    if a.only in (None, "scan"):
        jobs.append(("scan", Path(a.scan_run) if a.scan_run else HERE / "runs" / "scan", img / "scan.gif",
                     a.seconds or 20.0, "overview"))

    for kind, run, out, secs, cam in jobs:
        if not run.exists():
            print("\n%s: нет каталога прогона %s — пропускаю" % (kind, run))
            continue
        record(kind, run, out, secs, cam, a.width, a.height,
               a.every, a.colors, a.max_width)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
