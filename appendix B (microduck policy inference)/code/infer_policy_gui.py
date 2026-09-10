#!/usr/bin/env python3
"""Microduck GUI: MuJoCo window with on-screen clickable control buttons.

Buttons (hold to drive, release to stop):
  [Поворот ◀] [◀ Влево] [▲ Вперёд] [СТОП] [▼ Назад] [Вправо ▶] [Поворот ▶]

Keyboard also works: W/S/A/D or arrows = move, Q/E = yaw, SPACE = stop,
Y = sit/stand, G = ground pick, K/L = kicks, R = roulade, P = push,
T = pause policy, ESC = quit.
Mouse: hold LEFT on a button = drive, RIGHT-drag = orbit camera, wheel = zoom.

Reuses the policy/scene machinery of infer_policy_windows.py; only the
viewer loop is replaced (GLFW window + fixed-function OpenGL overlay),
because mujoco.viewer exposes no mouse events, so buttons cannot be
clicked in the standard viewer.

Requires: uv pip install glfw PyOpenGL   (Pillow comes with matplotlib)
"""

import argparse
import math
import os
import queue
import random
import sys
import threading
import time

import numpy as np
import mujoco
import glfw
from OpenGL import GL
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from infer_policy_windows import (
    load_bam_model,
    load_mujoco_with_bam,
    PolicyInference,
    BAM_KP_FW,
    BAM_VIN_MIN,
    MICRODUCK_XML,
    MICRODUCK_ROLLERS_XML,
    MICRODUCK_BALL_XML,
)

# ---------------------------------------------------------------------------
# Buttons: (id, icon, label, (vx, vy, wz)) — the command applied while held.
# Strafe/yaw signs match infer_policy.py's arrow/A-E mapping.
# ---------------------------------------------------------------------------
BUTTONS = [
    ("yaw_left",     "yawl", "Поворот", (0.0,  0.0,  1.5)),
    ("strafe_left",  "left", "Влево",   (0.0,  0.2,  0.0)),
    ("fwd",          "up",   "Вперёд",  (0.3,  0.0,  0.0)),
    ("stop",         "stop", "СТОП",    None),
    ("back",         "down", "Назад",   (-0.3, 0.0,  0.0)),
    ("strafe_right", "right", "Вправо", (0.0, -0.2,  0.0)),
    ("yaw_right",    "yawr", "Поворот", (0.0,  0.0, -1.5)),
]

BUTTON_W, BUTTON_H, BUTTON_GAP, BUTTON_MARGIN = 112, 56, 10, 12

COL_IDLE = (44, 55, 82, 235)
COL_HOVER = (70, 95, 140, 245)
COL_HELD = (245, 150, 30, 255)
COL_STOP_IDLE = (150, 50, 55, 235)
COL_STOP_HELD = (235, 60, 40, 255)


def _font(size):
    return ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size)


def _draw_triangle(d, cx, cy, direction, size):
    s = size
    if direction == "up":
        pts = [(cx, cy - s), (cx - s * 0.75, cy + s * 0.7), (cx + s * 0.75, cy + s * 0.7)]
    elif direction == "down":
        pts = [(cx, cy + s), (cx - s * 0.75, cy - s * 0.7), (cx + s * 0.75, cy - s * 0.7)]
    elif direction == "left":
        pts = [(cx - s, cy), (cx + s * 0.7, cy - s * 0.75), (cx + s * 0.7, cy + s * 0.75)]
    else:
        pts = [(cx + s, cy), (cx - s * 0.7, cy - s * 0.75), (cx - s * 0.7, cy + s * 0.75)]
    d.polygon(pts, fill=(255, 255, 255, 255))


def _draw_yaw_arrow(d, cx, cy, right=False):
    """Circular arrow: 290° arc plus a tangential arrowhead."""
    r = 17
    pts = []
    for a_deg in range(30, 321, 10):
        a = math.radians(a_deg)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.line(pts, fill=(255, 255, 255, 255), width=5)
    if not right:
        a_h = math.radians(320)
        tip = (cx + r * math.cos(a_h), cy + r * math.sin(a_h))
        t1 = (cx + (r - 9) * math.cos(a_h + 0.55), cy + (r - 9) * math.sin(a_h + 0.55))
        t2 = (cx + (r - 9) * math.cos(a_h - 0.55), cy + (r - 9) * math.sin(a_h - 0.55))
    else:
        a_h = math.radians(30)
        tip = (cx + r * math.cos(a_h), cy + r * math.sin(a_h))
        t1 = (cx + (r - 9) * math.cos(a_h - 0.55), cy + (r - 9) * math.sin(a_h - 0.55))
        t2 = (cx + (r - 9) * math.cos(a_h + 0.55), cy + (r - 9) * math.sin(a_h + 0.55))
    d.polygon([tip, t1, t2], fill=(255, 255, 255, 255))


def make_button_image(icon, text):
    """Render one button's white icon+text (RGBA) for a texture overlay."""
    W, H = BUTTON_W * 2, BUTTON_H * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = 44, H // 2
    if icon == "up":
        _draw_triangle(d, cx, cy, "up", 22)
    elif icon == "down":
        _draw_triangle(d, cx, cy, "down", 22)
    elif icon == "left":
        _draw_triangle(d, cx, cy, "left", 22)
    elif icon == "right":
        _draw_triangle(d, cx, cy, "right", 22)
    elif icon in ("yawl", "yawr"):
        _draw_yaw_arrow(d, cx, cy, right=(icon == "yawr"))
    else:  # stop: filled square
        s = 26
        d.rectangle([cx - s, cy - s, cx + s, cy + s], fill=(255, 255, 255, 255))
    fnt = _font(32)
    d.text((78, H // 2 - 21), text, font=fnt, fill=(255, 255, 255, 255))
    return img


def upload_texture(img):
    w, h = img.size
    data = img.tobytes("raw", "RGBA", 0, -1)  # flip rows for GL
    tex = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
    GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, w, h, 0,
                    GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, data)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
    return tex


class ButtonPanel:
    """State + hit-testing + drawing of the on-screen buttons."""

    def __init__(self):
        self.commands = {b[0]: b[3] for b in BUTTONS}
        self.held = {}                    # btn id -> True
        self.hover = None
        self.rects = []                   # (id, x, y, w, h) in framebuffer px
        self.textures = {}
        for btn_id, icon, text, _cmd in BUTTONS:
            self.textures[btn_id] = upload_texture(make_button_image(icon, text))

    def layout(self, fb_w, fb_h):
        n = len(BUTTONS)
        total = n * BUTTON_W + (n - 1) * BUTTON_GAP
        x0 = (fb_w - total) // 2
        y0 = fb_h - BUTTON_H - BUTTON_MARGIN
        self.rects = []
        for i, (btn_id, _icon, _text, _cmd) in enumerate(BUTTONS):
            x = x0 + i * (BUTTON_W + BUTTON_GAP)
            self.rects.append((btn_id, x, y0, BUTTON_W, BUTTON_H))

    def hit(self, mx, my):
        for btn_id, x, y, w, h in self.rects:
            if x <= mx <= x + w and y <= my <= y + h:
                return btn_id
        return None

    def press(self, btn_id):
        """Toggle a command on/off (click to drive, click again to stop)."""
        if btn_id is None:
            return
        if btn_id == "stop":
            self.held.clear()
        else:
            if self.held.get(btn_id):
                self.held.pop(btn_id)
            else:
                self.held[btn_id] = True

    def current_cmd(self):
        vx = vy = wz = 0.0
        for btn_id in self.held:
            c = self.commands.get(btn_id)
            if c:
                vx += c[0]
                vy += c[1]
                wz += c[2]
        return vx, vy, wz

    def draw(self):
        # mjr_render leaves DEPTH/CULL/LIGHTING enabled; with LIGHTING on,
        # fixed-function glColor is consumed as a material and the buttons
        # come out near-black — everything must be switched off.
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_FOG)
        GL.glDisable(GL.GL_ALPHA_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glTexEnvf(GL.GL_TEXTURE_ENV, GL.GL_TEXTURE_ENV_MODE, GL.GL_MODULATE)
        GL.glColor4f(1.0, 1.0, 1.0, 1.0)

        for btn_id, x, y, w, h in self.rects:
            is_stop = self.commands.get(btn_id) is None
            if btn_id in self.held:
                col = COL_STOP_HELD if is_stop else COL_HELD
            elif btn_id == self.hover:
                col = COL_STOP_IDLE if is_stop else COL_HOVER
            else:
                col = COL_STOP_IDLE if is_stop else COL_IDLE
            GL.glDisable(GL.GL_TEXTURE_2D)
            GL.glColor4f(*[c / 255.0 for c in col])
            GL.glBegin(GL.GL_QUADS)
            GL.glVertex2f(x, y)
            GL.glVertex2f(x + w, y)
            GL.glVertex2f(x + w, y + h)
            GL.glVertex2f(x, y + h)
            GL.glEnd()

            GL.glEnable(GL.GL_TEXTURE_2D)
            GL.glColor4f(1.0, 1.0, 1.0, 1.0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self.textures[btn_id])
            # The texture was uploaded bottom-up (row 0 = IMAGE bottom); v=1 is
            # the image TOP. The screen quad is y-down, so the top-left screen
            # corner takes texcoord (0,1) — this keeps the text upright.
            GL.glBegin(GL.GL_QUADS)
            GL.glTexCoord2f(0, 1)
            GL.glVertex2f(x, y)
            GL.glTexCoord2f(1, 1)
            GL.glVertex2f(x + w, y)
            GL.glTexCoord2f(1, 0)
            GL.glVertex2f(x + w, y + h)
            GL.glTexCoord2f(0, 0)
            GL.glVertex2f(x, y + h)
            GL.glEnd()

        GL.glDisable(GL.GL_TEXTURE_2D)
        GL.glEnable(GL.GL_DEPTH_TEST)


def main():
    parser = argparse.ArgumentParser(description="Microduck MuJoCo GUI with on-screen buttons")
    parser.add_argument("--roller", action="store_true")
    parser.add_argument("--scene", type=str, default=None)
    parser.add_argument("--walking", type=str, default=None)
    parser.add_argument("--standing", "-s", type=str, default=None)
    parser.add_argument("--sitstand", type=str, default=None)
    parser.add_argument("--sit", type=str, default=None)
    parser.add_argument("--ground-pick", type=str, default=None)
    parser.add_argument("--kick-left", type=str, default=None)
    parser.add_argument("--kick-right", type=str, default=None)
    parser.add_argument("--roulade", type=str, default=None)
    parser.add_argument("--new-cmd-obs", action="store_true",
                        help="Required for the alpha policies (61D obs)")
    parser.add_argument("--no-bam", action="store_true")
    parser.add_argument("--vin", type=float, default=7.4)
    parser.add_argument("--vin-drop-gain", type=float, default=0.1)
    parser.add_argument("--kp-fw", type=float, default=BAM_KP_FW)
    parser.add_argument("--current-limit", type=float, default=0.0)
    parser.add_argument("--action-scale", type=float, default=1.0)
    parser.add_argument("--delay", type=int, nargs="*", default=None)
    parser.add_argument("--switch-threshold", type=float, default=0.05)
    parser.add_argument("--lin-vel-x", type=float, default=0.0)
    parser.add_argument("--lin-vel-y", type=float, default=0.0)
    parser.add_argument("--ang-vel-z", type=float, default=0.0)
    parser.add_argument("--auto-quit", type=float, default=None,
                        help="quit after N seconds (smoke tests)")
    parser.add_argument("--selftest", action="store_true",
                        help="simulate button presses: fwd 2-5s, yaw-right 6-9s, quit at 10.5s")
    parser.add_argument("--screenshot", type=str, default=None,
                        help="save one frame as PNG after 1 s and quit")
    parser.add_argument("--bench", action="store_true",
                        help="print per-stage timings")
    args = parser.parse_args()

    if not args.walking and not args.standing and not args.sitstand:
        parser.error("At least one of --walking, --standing or --sitstand must be provided")
    if args.sitstand and not args.new_cmd_obs:
        parser.error("--sitstand requires --new-cmd-obs")
    if (args.kick_left or args.kick_right or args.roulade) and not args.new_cmd_obs:
        parser.error("kick/roulade require --new-cmd-obs")
    if (args.kick_left or args.kick_right or args.roulade) and args.roller:
        parser.error("kick/roulade are trained on the walking robot, not rollers")

    delay_min_lag = delay_max_lag = 0
    if args.delay is not None:
        if len(args.delay) == 0:
            delay_min_lag, delay_max_lag = 1, 2
        elif len(args.delay) == 1:
            delay_min_lag = delay_max_lag = args.delay[0]
        else:
            delay_min_lag, delay_max_lag = args.delay[0], args.delay[1]

    if args.scene:
        xml_path = args.scene
    elif args.roller:
        xml_path = MICRODUCK_ROLLERS_XML
    elif args.kick_left or args.kick_right:
        xml_path = MICRODUCK_BALL_XML
    else:
        xml_path = MICRODUCK_XML
    print(f"Loading MuJoCo model from: {xml_path}")

    bam_ctrl = None
    if not args.no_bam:
        bam_model = load_bam_model(args.kp_fw, args.vin, args.current_limit)
        vin_drop_gain = args.vin_drop_gain if args.vin_drop_gain > 0 else None
        model, data, bam_ctrl, _ = load_mujoco_with_bam(
            xml_path, bam_model, 0.005, vin_drop_gain, BAM_VIN_MIN)
    else:
        model = mujoco.MjModel.from_xml_path(xml_path)
        model.opt.timestep = 0.005
        data = mujoco.MjData(model)

    policy = PolicyInference(
        model, data,
        bam_ctrl=bam_ctrl,
        walking_onnx_path=args.walking,
        action_scale=args.action_scale,
        delay_min_lag=delay_min_lag,
        delay_max_lag=delay_max_lag,
        standing_onnx_path=args.standing,
        switch_threshold=args.switch_threshold,
        use_projected_gravity=True,
        ground_pick_onnx_path=args.ground_pick,
        sit_onnx_path=args.sit,
        new_cmd_obs=args.new_cmd_obs,
        sitstand_onnx_path=args.sitstand,
        kick_left_onnx_path=args.kick_left,
        kick_right_onnx_path=args.kick_right,
        roulade_onnx_path=args.roulade,
    )
    policy.set_vel_cmd(args.lin_vel_x, args.lin_vel_y, args.ang_vel_z)

    if args.roller:
        import re
        for j in range(model.njnt):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j)
            if name and re.match(r"^passive_.*", name):
                model.dof_frictionloss[model.jnt_dofadr[j]] = 0.003
        policy.vel_max_x, policy.vel_min_x = 0.6, -0.5
        policy.vel_max_y, policy.vel_min_y = 0.0, 0.0
        policy.vel_max_ang = 1.0
    else:
        policy.vel_max_x, policy.vel_min_x = 0.3, -0.3
        policy.vel_max_y, policy.vel_min_y = 0.2, -0.2
        policy.vel_max_ang = 1.5

    # Initial placement: upright at HOME height, joints at the default pose.
    freejoint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "trunk_base_freejoint")
    qpos_adr = model.jnt_qposadr[freejoint_id]
    data.qpos[qpos_adr + 2] = 0.1385 if args.roller else 0.125
    for i, qpos_idx in enumerate(policy.joint_qpos_indices):
        data.qpos[qpos_idx] = policy.default_pose[i]
    if bam_ctrl is not None:
        bam_ctrl.reset(data.qpos)
    policy.set_position_targets(policy.default_pose)
    mujoco.mj_forward(model, data)

    trunk_qvel_adr = int(model.jnt_dofadr[freejoint_id])

    print("=" * 72)
    print("Microduck MuJoCo GUI")
    print("=" * 72)
    print("Buttons in the window: click to drive, click again to stop.")
    print("  Поворот ◀/▶   Влево/Вправо   Вперёд/Назад   СТОП (reset)")
    print("Mouse: RIGHT-drag = camera orbit, wheel = zoom.")
    print("Keys: WASD/arrows move (toggle), Q/E yaw, SPACE stop, Y sit, G pick,")
    print("      K/L kick, R roulade, P push, T pause, ESC quit.")
    if policy.walking_session:
        print("Walking policy: loaded")
    if policy.standing_session:
        print("Standing policy: loaded")
    if policy.sit_session:
        print("Sitstand policy: loaded")
    if policy.ground_pick_session:
        print("Ground pick policy: loaded")
    for name in policy.behavior_sessions:
        print(f"{name} policy: loaded")
    print()

    # ---------------------------------------------------------------- window
    if not glfw.init():
        raise RuntimeError("glfw.init failed")
    window = glfw.create_window(1280, 900, "Microduck — MuJoCo", None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("glfw.create_window failed")
    glfw.make_context_current(window)

    ctx = mujoco.MjrContext(model, mujoco.mjtFontScale.mjFONTSCALE_150)
    scn = mujoco.MjvScene(model, maxgeom=10000)
    # The reflected-floor pass and the shadow map are by far the most
    # expensive parts of mjr_render (60-100 ms on an iGPU); the duck walks
    # on a dark virtual floor either way.
    model.vis.quality.shadowsize = 0
    scn.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = 0
    scn.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.distance = 1.7
    cam.azimuth = 90.0
    cam.elevation = -12.0
    cam.lookat[:] = [0.05, 0.0, 0.32]
    opt = mujoco.MjvOption()
    opt.label = mujoco.mjtLabel.mjLABEL_NONE
    pert = mujoco.MjvPerturb()

    panel = ButtonPanel()
    state = {"mx": 0, "my": 0, "orbit": False, "quit": False,
             "policy_enabled": True, "t0": time.time()}

    KEY_CMDS = {
        glfw.KEY_UP: "fwd", glfw.KEY_W: "fwd",
        glfw.KEY_DOWN: "back", glfw.KEY_S: "back",
        glfw.KEY_LEFT: "strafe_left", glfw.KEY_A: "strafe_left",
        glfw.KEY_RIGHT: "strafe_right", glfw.KEY_D: "strafe_right",
        glfw.KEY_Q: "yaw_left", glfw.KEY_E: "yaw_right",
    }

    def fb_size():
        return glfw.get_framebuffer_size(window)

    def window_size():
        return glfw.get_window_size(window)

    def to_fb(mx, my):
        fbw, fbh = fb_size()
        ww, wh = window_size()
        return mx * fbw / max(1, ww), my * fbh / max(1, wh)

    def apply_held():
        vx, vy, wz = panel.current_cmd()
        policy.set_vel_cmd(float(np.clip(vx, policy.vel_min_x, policy.vel_max_x)),
                           float(np.clip(vy, policy.vel_min_y, policy.vel_max_y)),
                           float(np.clip(wz, -policy.vel_max_ang, policy.vel_max_ang)))

    # UI callbacks run on the main (render) thread: policy data is only
    # touched through a per-event queue drained by the physics thread.
    def on_cursor(window, x, y):
        state["mx"], state["my"] = x, y
        xf, yf = to_fb(x, y)
        if state["orbit"]:
            dx = xf - state["orbit_x"]
            dy = yf - state["orbit_y"]
            cam.azimuth -= dx * 0.35
            cam.elevation = float(np.clip(cam.elevation - dy * 0.35, -80, 80))
            state["orbit_x"], state["orbit_y"] = xf, yf
        else:
            panel.hover = panel.hit(xf, yf)

    def on_mouse(window, button, action, mods):
        if button == glfw.MOUSE_BUTTON_RIGHT:
            if action == glfw.PRESS:
                state["orbit"] = True
                state["orbit_x"], state["orbit_y"] = to_fb(state["mx"], state["my"])
            else:
                state["orbit"] = False
            return
        if button != glfw.MOUSE_BUTTON_LEFT:
            return
        if action != glfw.PRESS:
            return  # toggle semantics: release does nothing
        btn_id = panel.hit(*to_fb(state["mx"], state["my"]))
        events.put(("press", btn_id))

    def on_scroll(window, xoff, yoff):
        cam.distance = float(np.clip(cam.distance * (0.9 if yoff > 0 else 1.1), 0.5, 6.0))

    def on_key(window, key, scancode, action, mods):
        if key in KEY_CMDS:
            if action == glfw.PRESS:
                events.put(("press", KEY_CMDS[key]))
            return
        if action not in (glfw.PRESS, glfw.REPEAT):
            return
        if key == glfw.KEY_ESCAPE:
            shared["quit"] = True
        elif key == glfw.KEY_SPACE:
            events.put(("stop", None))
        elif key == glfw.KEY_T:
            events.put(("key", "toggle_pause"))
        elif key == glfw.KEY_Y:
            events.put(("key", "sit"))
        elif key == glfw.KEY_G:
            events.put(("key", "ground_pick"))
        elif key == glfw.KEY_K:
            events.put(("key", "kick_left"))
        elif key == glfw.KEY_L:
            events.put(("key", "kick_right"))
        elif key == glfw.KEY_R:
            events.put(("key", "roulade"))
        elif key == glfw.KEY_P:
            events.put(("key", "push"))

    glfw.set_cursor_pos_callback(window, on_cursor)
    glfw.set_mouse_button_callback(window, on_mouse)
    glfw.set_scroll_callback(window, on_scroll)
    glfw.set_key_callback(window, on_key)

    # ------------------------------------------------------------------
    # Two threads: the policy/physics loop must run at a constant 50 Hz —
    # a slower loop drives a robot that moves less than the policy expects
    # and it falls over. The renderer (up to ~60 ms/frame on an iGPU) runs
    # in the main thread and never steals time from it. UI events go from
    # the main thread into a queue the physics thread drains each tick.
    # ------------------------------------------------------------------
    control_dt = 4 * model.opt.timestep  # 0.02 s = 50 Hz
    selftest_plan = [(2.0, "fwd"), (5.0, "fwd"),
                     (6.0, "yaw_right"), (9.0, "yaw_right"),
                     (10.5, None)] if args.selftest else []
    events = queue.Queue()
    shared = {"quit": False}

    def push_evt(kind, payload):
        events.put((kind, payload))

    def quit_duck():
        shared["quit"] = True

    def physics_loop():
        prev = time.time()
        rt_check = time.time()
        sim_time_accum = 0.0
        bench = {"infer": 0.0, "physics": 0.0}
        bench_frames = 0
        while not shared["quit"]:
            now = time.time()
            while True:
                try:
                    kind, payload = events.get_nowait()
                except queue.Empty:
                    break
                if kind == "press":
                    panel.press(payload)
                    apply_held()
                elif kind == "stop":
                    panel.held.clear()
                    apply_held()
                elif kind == "key":
                    if payload == "toggle_pause":
                        state["policy_enabled"] = not state["policy_enabled"]
                        print(f"Policy inference: "
                              f"{'ON' if state['policy_enabled'] else 'OFF (paused)'}")
                    elif payload == "sit":
                        policy.toggle_sit()
                    elif payload == "ground_pick":
                        policy.trigger_ground_pick()
                    elif payload == "kick_left":
                        policy.trigger_behavior("kick_left")
                    elif payload == "kick_right":
                        policy.trigger_behavior("kick_right")
                    elif payload == "roulade":
                        policy.trigger_behavior("roulade")
                    elif payload == "push":
                        angle = random.uniform(0, 2 * np.pi)
                        data.qvel[trunk_qvel_adr + 0] = math.cos(angle)
                        data.qvel[trunk_qvel_adr + 1] = math.sin(angle)
                        print(f"PUSH: v=[{math.cos(angle):.2f}, {math.sin(angle):.2f}] m/s")
                elif kind == "quit":
                    shared["quit"] = True
                    return

            if args.auto_quit and now - shared["t0"] >= args.auto_quit:
                shared["quit"] = True
                return
            if selftest_plan and now - shared["t0"] >= selftest_plan[0][0]:
                btn_id = selftest_plan.pop(0)[1]
                if btn_id:
                    panel.press(btn_id)
                    apply_held()
                else:
                    shared["quit"] = True
                    return
            if now - rt_check >= 2.0:
                rt = sim_time_accum / max(1e-6, now - rt_check)
                print(f"[real-time] {rt:.2f}x  (duck falls over if too far below 1.0x)")
                if args.bench and bench_frames >= 5:
                    for k, v in bench.items():
                        print(f"  bench {k:10s}: {v / max(1, bench_frames) * 1000:7.1f} ms")
                rt_check = now
                sim_time_accum = 0.0
                bench_frames = 0
                bench = {"infer": 0.0, "physics": 0.0}

            dt = now - prev
            prev = now

            t_pc = time.perf_counter()
            policy.update_ground_pick_phase(dt)
            policy.update_behavior(dt)
            if state["policy_enabled"]:
                action = policy.infer()
                policy.apply_action(action)
            t1 = time.perf_counter()
            bench["infer"] += t1 - t_pc

            for _ in range(4):
                if bam_ctrl is not None:
                    bam_ctrl.update()
                mujoco.mj_step(model, data)
            sim_time_accum += control_dt
            t2 = time.perf_counter()
            bench["physics"] += t2 - t1
            bench_frames += 1

            sleep = control_dt - (time.time() - now)
            if sleep > 0:
                time.sleep(sleep)

    shared["t0"] = time.time()
    physics_thread = threading.Thread(target=physics_loop, daemon=True)
    physics_thread.start()

    try:
        while not shared["quit"] and not glfw.window_should_close(window):
            glfw.poll_events()

            fbw, fbh = fb_size()
            viewport = mujoco.MjrRect(0, 0, fbw, fbh)
            mujoco.mjv_updateScene(model, data, opt, pert, cam,
                                   mujoco.mjtCatBit.mjCAT_ALL, scn)
            mujoco.mjr_render(viewport, scn, ctx)

            panel.layout(fbw, fbh)
            # mjr_render leaves GL state (bound program/VAO/scissor etc.)
            # behind; the fixed-function overlay needs the old pipeline back.
            GL.glUseProgram(0)
            try:
                GL.glBindVertexArray(0)
            except Exception:
                pass
            GL.glDisable(GL.GL_SCISSOR_TEST)
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glPushMatrix()
            GL.glLoadIdentity()
            GL.glOrtho(0, fbw, fbh, 0, -1, 1)
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glPushMatrix()
            GL.glLoadIdentity()
            panel.draw()
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glPopMatrix()
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glPopMatrix()

            if args.screenshot and not state.get("shot_saved") and \
                    time.time() - shared["t0"] >= 1.0:
                buf = GL.glReadPixels(0, 0, fbw, fbh, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
                img = Image.frombytes("RGBA", (fbw, fbh), buf)
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
                img.save(args.screenshot)
                state["shot_saved"] = True
                shared["quit"] = True

            glfw.swap_buffers(window)
    finally:
        events.put(("quit", None))
        glfw.terminate()

    print("Simulation stopped.")


if __name__ == "__main__":
    main()
