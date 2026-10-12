"""Робот и мир в RViz2 без URDF: маркеры из геометрии MuJoCo.

У ЦАПЛИ и дрона нет URDF, поэтому RobotModel показать нечего. Зато вся
геометрия есть в MjModel: каждый геом — примитив с позой в мире. Его можно
отправить в RViz2 как visualization_msgs/Marker. Меши (у Microduck) рисуются
своим габаритным боксом — форма упрощённая, но поза и движение настоящие.
"""
import mujoco
import numpy as np
from visualization_msgs.msg import Marker, MarkerArray

# Видимые по умолчанию группы MuJoCo — 0, 1, 2; группы 3+ обычно коллизии.
VISIBLE_GROUPS = (0, 1, 2)


class GeomMarkers:
    def __init__(self, model: mujoco.MjModel, frame_id: str = "odom"):
        self.frame_id = frame_id
        m = model
        self.items = []         # (geom_id, тип, масштаб xyz, смещение центра в раме геома, rgba)
        for g in range(m.ngeom):
            t = m.geom_type[g]
            if t in (mujoco.mjtGeom.mjGEOM_PLANE, mujoco.mjtGeom.mjGEOM_HFIELD):
                continue
            if m.geom_group[g] not in VISIBLE_GROUPS:
                continue
            mat = m.geom_matid[g]
            rgba = m.mat_rgba[mat] if mat >= 0 else m.geom_rgba[g]
            if rgba[3] < 0.05:
                continue
            s = m.geom_size[g]
            off = np.zeros(3)
            if t == mujoco.mjtGeom.mjGEOM_BOX:
                kind, scale = Marker.CUBE, 2 * s[:3]
            elif t == mujoco.mjtGeom.mjGEOM_SPHERE:
                kind, scale = Marker.SPHERE, np.full(3, 2 * s[0])
            elif t == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
                kind, scale = Marker.SPHERE, 2 * s[:3]
            elif t == mujoco.mjtGeom.mjGEOM_CAPSULE:
                kind, scale = Marker.CYLINDER, np.array([2 * s[0], 2 * s[0], 2 * s[1] + 2 * s[0]])
            elif t == mujoco.mjtGeom.mjGEOM_CYLINDER:
                kind, scale = Marker.CYLINDER, np.array([2 * s[0], 2 * s[0], 2 * s[1]])
            else:                                   # меш и прочее — габаритный бокс
                aabb = m.geom_aabb[g]
                kind, scale, off = Marker.CUBE, 2 * aabb[3:6], aabb[0:3].copy()
            if np.min(scale) <= 0:
                scale = np.maximum(scale, 0.004)    # плоские меши (маркер ArUco) — тонкая пластина
            # плоские объекты мира не отличить от пола, если они серые — оставляем цвет как есть
            self.items.append((g, kind, scale.astype(float), off, [float(c) for c in rgba]))

    def build(self, xpos: np.ndarray, xmat: np.ndarray, stamp) -> MarkerArray:
        """xpos/xmat — копии data.geom_xpos / data.geom_xmat, снятые под замком."""
        arr = MarkerArray()
        q = np.zeros(4)
        for i, (g, kind, scale, off, rgba) in enumerate(self.items):
            R = xmat[g].reshape(3, 3)
            p = xpos[g] + R @ off
            mujoco.mju_mat2Quat(q, xmat[g])
            mk = Marker()
            mk.header.frame_id, mk.header.stamp = self.frame_id, stamp
            mk.ns, mk.id, mk.type, mk.action = "mujoco", i, kind, Marker.ADD
            mk.pose.position.x, mk.pose.position.y, mk.pose.position.z = map(float, p)
            mk.pose.orientation.w, mk.pose.orientation.x = float(q[0]), float(q[1])
            mk.pose.orientation.y, mk.pose.orientation.z = float(q[2]), float(q[3])
            mk.scale.x, mk.scale.y, mk.scale.z = map(float, scale)
            mk.color.r, mk.color.g, mk.color.b, mk.color.a = rgba
            arr.markers.append(mk)
        return arr
