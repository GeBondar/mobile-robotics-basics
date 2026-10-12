"""Сборка сцены MuJoCo: робот + камера + объекты мира из YAML.

Робот берётся из своего MJCF без правок; камера и объекты добавляются через
MjSpec — так исходная модель остаётся той же, на которой учили политику.
"""
from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import mujoco
import numpy as np
import yaml


@dataclass
class RobotProfile:
    model: str                        # путь к MJCF
    base_body: str                    # корпус со свободным суставом
    joints: tuple                     # порядок /joint_commands и /joint_states
    timestep: float | None = None     # переопределить шаг физики
    init_z: float | None = None
    init_joints: tuple | None = None  # стартовая поза суставов (и цели приводов)
    init_ctrl: tuple | None = None    # стартовые команды приводов (тяги дрона)
    camera: str | None = None         # имя готовой камеры в модели
    # Развернуть готовую камеру на 180° вокруг её оси y: у Microduck head_camera задана
    # по-CAD-овски (взгляд вдоль +z), а MuJoCo смотрит вдоль -z — то есть внутрь головы.
    flip_camera: bool = False
    add_camera: dict | None = None    # или добавить: body, pos, xyaxes, fovy
    chase: dict = field(default_factory=lambda: {"distance": 1.0, "elevation": -20.0, "azimuth": 135.0})


def microduck_rl_root() -> Path:
    root = os.environ.get("MICRODUCK_RL", "")
    if not root:
        raise RuntimeError("задайте MICRODUCK_RL — путь к клону microduck_rl (приложение Б)")
    return Path(root)


def make_profile(robot: str, share: Path) -> RobotProfile:
    from .contracts import MicroduckContract, QuadHoverContract, Tsaplya2Contract
    if robot == "microduck":
        return RobotProfile(
            model=str(microduck_rl_root() / "src/mjlab_microduck/robot/microduck/scene.xml"),
            base_body="trunk_base", joints=MicroduckContract.JOINTS, timestep=0.005,
            init_z=0.125, init_joints=tuple(MicroduckContract.DEFAULT_POSE),
            camera="head_camera", flip_camera=True,
            chase={"distance": 0.75, "elevation": -18.0, "azimuth": 150.0})
    if robot == "tsaplya2":
        return RobotProfile(
            model=str(share / "models/tsaplya2.xml"), base_body="trunk",
            joints=Tsaplya2Contract.JOINTS,
            # камера на передней стенке корпуса, смотрит вперёд и чуть вниз
            add_camera={"body": "trunk", "name": "front_camera", "pos": [0.13, 0.0, 0.05],
                        "xyaxes": [0, -1, 0, 0.2, 0, 1], "fovy": 70.0},
            chase={"distance": 2.4, "elevation": -15.0, "azimuth": 150.0})
    if robot == "quad":
        h = QuadHoverContract.HOVER
        return RobotProfile(
            model=str(share / "models/quad.xml"), base_body="drone",
            joints=QuadHoverContract.JOINTS, init_z=1.0, init_ctrl=(h, h, h, h),
            # смотрит вниз; верх кадра — нос дрона
            add_camera={"body": "drone", "name": "down_camera", "pos": [0.0, 0.0, -0.02],
                        "xyaxes": [0, -1, 0, 1, 0, 0], "fovy": 80.0},
            chase={"distance": 3.0, "elevation": -35.0, "azimuth": 135.0})
    raise ValueError(f"неизвестный робот {robot}")


def _aruco_png(marker_id: int, px: int = 240) -> str:
    """PNG маркера с белой рамкой в 1/6 стороны (тихая зона для детектора)."""
    import cv2
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    inner = cv2.aruco.generateImageMarker(d, marker_id, px)
    pad = px // 6
    img = cv2.copyMakeBorder(inner, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    path = Path(tempfile.gettempdir()) / f"rl_policy_ros_aruco_{marker_id}.png"
    cv2.imwrite(str(path), cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    return str(path)


COLORS = {"red": [0.85, 0.1, 0.1, 1], "green": [0.1, 0.7, 0.2, 1], "blue": [0.1, 0.3, 0.85, 1],
          "yellow": [0.95, 0.85, 0.1, 1], "white": [0.95, 0.95, 0.95, 1], "grey": [0.5, 0.5, 0.5, 1]}


def _yaw_quat(deg):
    a = math.radians(deg) / 2
    return [math.cos(a), 0, 0, math.sin(a)]


def add_world(spec: mujoco.MjSpec, world_yaml: str | None) -> list[dict]:
    """Добавить объекты мира. Возвращает список объектов (для логов и проверок)."""
    if not world_yaml:
        return []
    objs = yaml.safe_load(Path(world_yaml).read_text(encoding="utf-8")).get("objects", [])
    for i, o in enumerate(objs):
        kind = o["type"]
        pos = o.get("pos", [0, 0, 0])
        body = spec.worldbody.add_body(name=f"obj{i}_{kind}", pos=pos, quat=_yaw_quat(o.get("yaw", 0)))
        if kind == "aruco":
            # Квадрат маркера смотрит вдоль +x тела: поверните yaw лицом к роботу.
            s = float(o["size"]) * 8 / 6          # маркер + белая рамка
            tex = spec.add_texture(name=f"tex_aruco{i}", type=mujoco.mjtTexture.mjTEXTURE_2D,
                                   file=_aruco_png(int(o["id"])))
            mat = spec.add_material(name=f"mat_aruco{i}")
            mat.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = tex.name
            # Тонкая пластина-меш: две грани, текстура без искажений и без отражения.
            h = s / 2
            mesh = spec.add_mesh(name=f"mesh_aruco{i}")
            mesh.uservert = [0, h, -h, 0, -h, -h, 0, -h, h, 0, h, h]
            mesh.usertexcoord = [0, 1, 1, 1, 1, 0, 0, 0]
            mesh.userface = [0, 2, 1, 0, 3, 2]     # обход против часовой, если смотреть с +x
            mesh.inertia = mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL
            body.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=mesh.name, material=mat.name,
                          contype=0, conaffinity=0, pos=[0.003, 0, 0])
            body.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.002, h, h], rgba=[0.9, 0.9, 0.9, 1])
            if pos[2] - h > 0.01:                 # стойка до пола
                post = pos[2] - h
                body.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[0.01 + 0.02 * s, post / 2],
                              pos=[-0.01, 0, -h - post / 2], rgba=[0.3, 0.3, 0.3, 1])
        elif kind == "ball":
            r = float(o["radius"])
            body.add_freejoint()
            body.add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[r, 0, 0],
                          rgba=COLORS[o.get("color", "red")], mass=o.get("mass", 0.05))
        elif kind == "box":
            body.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=o["size"],
                          rgba=COLORS[o.get("color", "grey")])
        elif kind == "cylinder":
            body.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=o["size"],
                          rgba=COLORS[o.get("color", "grey")])
        elif kind == "pad":                       # плоская цветная метка на полу
            body.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[o["size"], o["size"], 0.002],
                          rgba=COLORS[o.get("color", "red")], contype=0, conaffinity=0)
        else:
            raise ValueError(f"неизвестный тип объекта {kind}")
    return objs


def decorate(spec: mujoco.MjSpec) -> None:
    """Небо и клетчатый пол: без клетки на видео не видно, что робот едет.

    Меняется только внешний вид пола (материал), не его контакт и не трение.
    """
    if not any(t.type == mujoco.mjtTexture.mjTEXTURE_SKYBOX for t in spec.textures):
        spec.add_texture(name="deco_sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX,
                         builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                         rgb1=[0.55, 0.7, 0.85], rgb2=[0.15, 0.2, 0.3], width=256, height=256)
    grid = spec.add_texture(name="deco_grid", type=mujoco.mjtTexture.mjTEXTURE_2D,
                            builtin=mujoco.mjtBuiltin.mjBUILTIN_CHECKER,
                            rgb1=[0.32, 0.34, 0.37], rgb2=[0.42, 0.44, 0.47], width=300, height=300)
    mat = spec.add_material(name="deco_floor", texrepeat=[1, 1], texuniform=True, reflectance=0.05)
    mat.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = grid.name
    for g in spec.worldbody.geoms:
        if g.type == mujoco.mjtGeom.mjGEOM_PLANE:
            g.material = mat.name
            g.rgba = [1, 1, 1, 1]


def build_model(profile: RobotProfile, world_yaml: str | None):
    spec = mujoco.MjSpec.from_file(profile.model)
    decorate(spec)
    if profile.timestep:
        spec.option.timestep = profile.timestep
    cam_name = profile.camera
    if profile.flip_camera:
        cam = spec.camera(cam_name)
        q, q2 = np.zeros(4), np.zeros(4)
        mujoco.mju_mulQuat(q, np.asarray(cam.quat, dtype=float), np.array([0.0, 0.0, 1.0, 0.0]))
        # и на -90° вокруг оси взгляда: иначе горизонт в кадре вертикальный
        mujoco.mju_mulQuat(q2, q, np.array([np.sqrt(0.5), 0.0, 0.0, -np.sqrt(0.5)]))
        cam.quat = q2
    if profile.add_camera:
        c = profile.add_camera
        body = spec.body(c["body"])
        cam = body.add_camera(name=c["name"], pos=c["pos"], fovy=c["fovy"])
        cam.alt.type = mujoco.mjtOrientation.mjORIENTATION_XYAXES
        cam.alt.xyaxes = c["xyaxes"]
        cam_name = c["name"]
    spec.visual.global_.offwidth = max(spec.visual.global_.offwidth, 1280)
    spec.visual.global_.offheight = max(spec.visual.global_.offheight, 960)
    objs = add_world(spec, world_yaml)
    model = spec.compile()
    return model, cam_name, objs


def init_state(model, data, profile: RobotProfile):
    mujoco.mj_resetData(model, data)
    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, profile.base_body)
    jnt = model.body_jntadr[bid]
    qa = model.jnt_qposadr[jnt]
    if profile.init_z is not None:
        data.qpos[qa:qa + 3] = [0.0, 0.0, profile.init_z]
        data.qpos[qa + 3:qa + 7] = [1, 0, 0, 0]
    act_ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, n) for n in profile.joints]
    if profile.init_joints is not None:
        for aid, v in zip(act_ids, profile.init_joints):
            data.qpos[model.jnt_qposadr[model.actuator_trnid[aid, 0]]] = v
            data.ctrl[aid] = v
    if profile.init_ctrl is not None:
        for aid, v in zip(act_ids, profile.init_ctrl):
            data.ctrl[aid] = v
        if model.na:
            data.act[:] = profile.init_ctrl[0]   # моторы дрона уже раскручены (hover_env.py:208)
    mujoco.mj_forward(model, data)
    return bid, act_ids


def camera_intrinsics(model, cam_name, width, height):
    cid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, cam_name)
    fovy = math.radians(float(model.cam_fovy[cid]))
    f = 0.5 * height / math.tan(0.5 * fovy)
    return np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1]])
