# -*- coding: utf-8 -*-
"""Гифка ходьбы: эталонная политика 60M в боевой среде.

    python render_gif.py                      # команда 0.4 м/с, 8 секунд
    python render_gif.py --cmd 0.8 --seconds 6

У модели tsaplya2.xml НЕТ НИ ОДНОЙ КАМЕРЫ (model.ncam == 0), поэтому берётся
следящая камера rl_toolkit.render.tracking_camera, привязанная к корпусу
(тело `trunk`). Со статической камерой робот уходит из кадра за полторы
секунды: при команде 0.4 м/с он проходит 3.2 метра за восемь секунд.

Веса грузятся ПАРОЙ через rl_toolkit.checkpointing.load_policy: без своей
статистики нормировки политика видит смещённые наблюдения и не идёт.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from rl_toolkit.render import record_frames, save_gif, tracking_camera  # noqa: E402
from rl_toolkit.checkpointing import load_policy                        # noqa: E402
from demo import make_pair                                              # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", type=float, default=0.4, help="команда скорости, м/с")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--seed", type=int, default=100)
    ap.add_argument("--out", default=str(HERE / "images" / "walking.gif"))
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=420)
    ap.add_argument("--distance", type=float, default=2.6)
    ap.add_argument("--azimuth", type=float, default=120.0)
    ap.add_argument("--elevation", type=float, default=-12.0)
    # Прореживание и палитра решают ВЕС файла: 200 кадров 480x315
    # при 128 цветах дают 6.6 МБ — столько в репозиторий класть нельзя.
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--colors", type=int, default=96)
    ap.add_argument("--max-width", type=int, default=420)
    a = ap.parse_args()

    from walk_env_full import make_full_env

    model_pi, norm = load_policy(make_pair())
    env = make_full_env(cmd_vx=a.cmd, randomize=False)
    obs, _ = env.reset(seed=a.seed)

    n = min(env.max_steps, int(round(a.seconds / env.dt)))
    state = {"obs": obs}

    def step() -> bool:
        act, _ = model_pi.predict(norm(state["obs"]), deterministic=True)
        o, _, term, trunc, _ = env.step(act)
        state["obs"] = o
        return not (term or trunc)

    cam = tracking_camera(env.model, "trunk", distance=a.distance,
                          azimuth=a.azimuth, elevation=a.elevation)
    frames = record_frames(env.model, env.data, step, n_steps=n, camera=cam,
                           width=a.width, height=a.height)
    print("шагов снято: %d из %d (эпизод %s)"
          % (len(frames), n, "дошёл до конца" if len(frames) == n else "оборвался"))
    save_gif(frames, a.out, fps=1.0 / env.dt, max_width=a.max_width,
             colors=a.colors, every=a.every)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
