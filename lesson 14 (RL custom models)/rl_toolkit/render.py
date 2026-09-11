"""Запись прогона политики в GIF.

ЗАЧЕМ ЭТО В ЯДРЕ. Каждому треку нужна одна и та же вещь: прокрутить политику
и сложить кадры в гифку, которую не стыдно положить в репозиторий. Отличия
между треками — только камера и то, как делается шаг, поэтому здесь лежит
общая часть, а треки дают тонкие обёртки.

ЧТО ЭТО ПРЕДОТВРАЩАЕТ

1. ЧЁРНЫЙ КАДР ИЗ-ЗА КАМЕРЫ, А НЕ ИЗ-ЗА OpenGL. В этом уроке гифка трека A
   записалась в 1563 байта: 86 кадров, все чёрные, один уникальный цвет.
   Причина была не в GL, а в позе камеры: вид сверху нёс euler="-90 0 0" —
   соглашение ФРОНТАЛЬНОЙ камеры, и камера с высоты восьми метров смотрела
   горизонтально, в пустоту. Поэтому record_frames проверяет первый кадр
   и ГРОМКО ругается, а не молча пишет темноту. Полная проверка всех камер
   модели — rl_toolkit.probes.probe_cameras.

2. МОДЕЛЬ БЕЗ КАМЕР. У двуногого трека B в MJCF нет ни одной камеры
   (model.ncam == 0). Поэтому по умолчанию берётся СЛЕДЯЩАЯ камера:
   mjCAMERA_TRACKING с trackbodyid. Без неё робот уходит из кадра
   через полторы секунды.

3. ГИФКА НА ТРИ МЕГАБАЙТА. Сырой прогон 960x720 при 20 Гц даёт 3.5 МБ на
   четыре секунды. save_gif прореживает кадры, уменьшает размер и сводит
   палитру: те же четыре секунды — 842 КБ.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

import numpy as np

__all__ = ["tracking_camera", "record_frames", "save_gif"]


def tracking_camera(model, body: str | int = 0, *, distance: float = 3.0,
                    azimuth: float = 135.0, elevation: float = -20.0,
                    lookat_z: Optional[float] = None):
    """Камера, привязанная к телу: робот остаётся в центре кадра.

    body — имя или индекс тела. Для моделей БЕЗ камер (трек B) это
    единственный способ получить осмысленный кадр длиннее пары секунд.
    """
    import mujoco

    if isinstance(body, str):
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body)
        if bid < 0:
            raise ValueError("нет тела %r в модели" % body)
    else:
        bid = int(body)

    cam = mujoco.MjvCamera()
    mujoco.mjv_defaultCamera(cam)
    cam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
    cam.trackbodyid = bid
    cam.distance = float(distance)
    cam.azimuth = float(azimuth)
    cam.elevation = float(elevation)
    if lookat_z is not None:
        cam.lookat[2] = float(lookat_z)
    return cam


def record_frames(model, data, step_fn: Callable[[], bool], *, n_steps: int,
                  camera: Any = None, width: int = 640, height: int = 480,
                  every: int = 1, warn_black: bool = True) -> List[np.ndarray]:
    """Кадры прогона. step_fn() двигает симуляцию на ОДИН шаг политики
    и возвращает False, когда эпизод кончился.

    camera — имя камеры модели, её индекс, объект MjvCamera или None
    (свободная камера). every — писать каждый N-й кадр.
    """
    import mujoco

    renderer = mujoco.Renderer(model, height=int(height), width=int(width))
    frames: List[np.ndarray] = []
    try:
        for i in range(int(n_steps)):
            alive = step_fn()
            if i % int(every) == 0:
                if camera is None:
                    renderer.update_scene(data)
                else:
                    renderer.update_scene(data, camera=camera)
                frames.append(renderer.render().copy())
            if not alive:
                break
    finally:
        renderer.close()

    if warn_black and frames:
        m = float(frames[0].mean())
        if m < 5.0:
            print("[рендер] ВНИМАНИЕ: первый кадр почти чёрный (яркость %.2f). "
                  "Сначала проверьте ПОЗУ камеры через "
                  "rl_toolkit.probes.probe_cameras — строка «(свободная)» "
                  "отделяет сломанную камеру от сломанного GL-контекста." % m,
                  flush=True)
    return frames


def save_gif(frames: Sequence[np.ndarray], path: str | Path, *, fps: float = 20.0,
             max_width: int = 480, colors: int = 128, every: int = 1) -> Path:
    """Сохранить кадры в GIF с прореживанием, уменьшением и палитрой."""
    from PIL import Image

    if not frames:
        raise ValueError("нет кадров")
    picked = list(frames)[::int(every)]
    h, w = picked[0].shape[:2]
    scale = min(1.0, float(max_width) / float(w))
    size = (int(w * scale), int(h * scale))

    imgs = []
    for fr in picked:
        im = Image.fromarray(np.asarray(fr, dtype=np.uint8))
        if scale < 1.0:
            im = im.resize(size, Image.LANCZOS)
        imgs.append(im.convert("P", palette=Image.ADAPTIVE, colors=int(colors)))

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    duration = max(20, int(round(1000.0 * every / float(fps))))
    imgs[0].save(out, save_all=True, append_images=imgs[1:],
                 duration=duration, loop=0, optimize=True)
    kb = out.stat().st_size / 1024.0
    print("[рендер] %s: %d кадров %dx%d, %.0f КБ, %.1f с"
          % (out.name, len(imgs), size[0], size[1], kb,
             len(imgs) * every / float(fps)), flush=True)
    return out


def _selftest() -> int:
    """Самопроверка на модели из трёх строк: кадры не чёрные, гифка пишется."""
    import tempfile
    import mujoco

    xml = """<mujoco>
      <worldbody>
        <light pos="0 0 3"/>
        <geom type="plane" size="3 3 .1" rgba=".8 .8 .8 1"/>
        <body name="ball" pos="0 0 1"><freejoint/>
          <geom type="sphere" size=".15" rgba="1 .3 .2 1"/></body>
      </worldbody>
    </mujoco>"""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)

    print("=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.render")
    print("=" * 78)

    def step():
        mujoco.mj_step(model, data)
        return True

    cam = tracking_camera(model, "ball", distance=2.0)
    frames = record_frames(model, data, step, n_steps=40, camera=cam,
                           width=160, height=120)
    mean = float(np.mean([f.mean() for f in frames]))
    print("\n1. Следящая камера: %d кадров, средняя яркость %.2f"
          % (len(frames), mean))
    assert len(frames) == 40, "потеряны кадры"
    assert mean > 5.0, "кадры чёрные — сломан рендер или камера"

    with tempfile.TemporaryDirectory() as d:
        p = save_gif(frames, Path(d) / "t.gif", fps=20, max_width=120, colors=64)
        assert p.exists() and p.stat().st_size > 0, "гифка не записана"
        print("2. Гифка записана: %d байт" % p.stat().st_size)

    # контроль: камера, смотрящая в пустоту, ОБЯЗАНА дать предупреждение
    blind = mujoco.MjvCamera()
    mujoco.mjv_defaultCamera(blind)
    blind.type = mujoco.mjtCamera.mjCAMERA_FREE
    blind.lookat[:] = [0.0, 0.0, 500.0]
    blind.distance = 0.05
    blind.elevation = 89.0
    data2 = mujoco.MjData(model)
    f2 = record_frames(model, data2, lambda: True, n_steps=2, camera=blind,
                       width=80, height=60)
    print("3. Камера в пустоту: яркость первого кадра %.2f "
          "(предупреждение выше — обязательно)" % f2[0].mean())
    assert f2[0].mean() < 5.0, "контрольная слепая камера почему-то видит сцену"

    print("\n" + "=" * 78)
    print("САМОПРОВЕРКА rl_toolkit.render ПРОЙДЕНА")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    import sys as _s
    _s.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(_selftest())
