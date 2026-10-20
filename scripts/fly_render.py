"""Stylized 3D fly + light scene renderer (CPU, PIL)."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    FONT_S = ImageFont.load_default(size=17)
    FONT_B = ImageFont.load_default(size=22)
except Exception:
    FONT_S = FONT_B = ImageFont.load_default()

def _norm(v):
    return v / (np.linalg.norm(v) + 1e-9)

class Cam:
    def __init__(self, pos, target, f=430.0):
        self.pos = np.asarray(pos, float)
        self.fwd = _norm(np.asarray(target, float) - self.pos)
        self.right = _norm(np.cross(self.fwd, [0, 0, 1.0]))
        self.up = np.cross(self.right, self.fwd)
        self.f = f

    def project(self, pts, W, H):
        pts = np.atleast_2d(np.asarray(pts, float))
        rel = pts - self.pos
        x = rel @ self.right
        y = rel @ self.up
        z = np.maximum(rel @ self.fwd, 0.6)
        return self.f * x / z + W / 2, H / 2 - self.f * y / z, z

def _sphere(d, cam, p, r, fill, W, H, outline=None):
    px, py, z = cam.project([p], W, H)
    rr = cam.f * r / z[0]
    d.ellipse([px[0]-rr, py[0]-rr, px[0]+rr, py[0]+rr], fill=fill, outline=outline)

def _seg(d, cam, a, b, w, fill, W, H):
    px, py, z = cam.project([a, b], W, H)
    d.line([px[0], py[0], px[1], py[1]], fill=fill, width=max(1, int(w * cam.f / z.mean())))

def _poly(d, cam, pts, fill, W, H, outline=None):
    px, py, _ = cam.project(pts, W, H)
    d.polygon(list(zip(px, py)), fill=fill, outline=outline)

def render_frame(world, W=854, H=480):
    f = world.fly
    yaw = f["yaw"]
    fly = np.array([f["x"], f["y"], f["z"]])
    ca, sa = np.cos(yaw), np.sin(yaw)

    def to_world(p):
        """fly-local -> world"""
        return np.array([fly[0] + p[0]*ca - p[1]*sa,
                         fly[1] + p[0]*sa + p[1]*ca,
                         fly[2] + p[2]])

    cam = Cam(to_world([-15.0, 0, 6.8]), to_world([1.5, 0, 2.3]))
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img, "RGBA")

    # sky
    top = (52, 96, 156); hor = (168, 206, 226)
    for i in range(0, H, 8):
        t = i / H
        c = tuple(int(top[k] + (hor[k]-top[k])*t) for k in range(3))
        d.rectangle([0, i, W, i+8], fill=c)

    # ---------------- meadow: grass field with tufts, flowers and haze ----------
    # horizon = where the ground plane meets infinity along the view direction
    far_pt = cam.project([[f["x"] + 600 * cam.fwd[0], f["y"] + 600 * cam.fwd[1], 0.0]], W, H)
    hz_y = float(far_pt[1][0])
    hz_y = max(0.0, min(hz_y, float(H) - 1))
    for i in range(int(hz_y), H, 4):                 # green ground, lighter far away
        t = (i - hz_y) / max(H - hz_y, 1)
        c = (int(118 + 22 * (1 - t)), int(156 + 26 * (1 - t)), int(74 + 18 * (1 - t)))
        d.rectangle([0, i, W, i + 4], fill=c)
    d.rectangle([0, int(hz_y) - 14, W, int(hz_y) + 2], fill=(196, 216, 200))  # haze band

    def h2(x, y, k):
        n = (int(x * 73856093) ^ int(y * 19349663) ^ k) & 0xFFFFFFFF
        n = (n * 2654435761) & 0xFFFFFFFF
        return (n % 10000) / 10000.0

    fx, fy = f["x"], f["y"]
    step = 1.7
    i0, i1 = int((fx - 24) // step), int((fx + 24) // step)
    j0, j1 = int((fy - 24) // step), int((fy + 24) // step)
    tufts = []
    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            wx = i * step + (h2(i, j, 1) - 0.5) * step
            wy = j * step + (h2(i, j, 2) - 0.5) * step
            dist = ((wx - fx) ** 2 + (wy - fy) ** 2) ** 0.5
            if dist > 24:
                continue
            tufts.append((dist, wx, wy, h2(i, j, 3), h2(i, j, 4)))
    tufts.sort(key=lambda t: -t[0])
    for dist, wx, wy, r1, r2 in tufts:
        haze = min(1.0, dist / 24.0)
        col = (int(66 + 74 * (1 - haze)), int(104 + 78 * (1 - haze)), int(44 + 40 * (1 - haze)), 255)
        hgt = 0.55 + 1.5 * r1
        lean = (r2 - 0.5) * 0.9
        _seg(d, cam, [wx, wy, 0.0], [wx + lean, wy + lean * 0.5, hgt], 0.11, col, W, H)
        if r2 > 0.4:
            _seg(d, cam, [wx, wy, 0.0], [wx - lean * 0.8, wy + lean * 0.7, hgt * 0.75], 0.1, col, W, H)
        if r1 > 0.955:                                # occasional flower
            fc = (236, 110, 140) if r2 > 0.5 else (250, 220, 96)
            _sphere(d, cam, [wx + lean, wy + lean * 0.5, hgt + 0.2], 0.3, fc + (255,), W, H)

    # a few taller clusters as landmarks
    for k in range(3):
        ax = fx + 11 * np.cos(k * 2.1 + 0.7)
        ay = fy + 11 * np.sin(k * 2.1 + 0.7)
        for b in range(6):
            lean = (b - 2.5) * 0.28
            _seg(d, cam, [ax, ay, 0.0], [ax + lean, ay + lean * 0.3, 2.6 + b * 0.22],
                 0.13, (108, 148, 66, 255), W, H)

    # light source glow
    L = world.light
    if L["on"]:
        lx, ly, lz = cam.project([[L["x"], L["y"], L["z"]]], W, H)
        cx, cy = float(lx[0]), float(ly[0])
        for r, a in [(140, 18), (110, 26), (80, 38), (52, 60), (30, 95), (16, 220)]:
            d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(255, 190, 90, a))
        d.ellipse([cx-8, cy-8, cx+8, cy+8], fill=(255, 236, 190, 255))

    # shadow
    sx, sy, sz = cam.project([[f["x"], f["y"], 0.1]], W, H)
    rr = cam.f * 5.5 / sz[0]
    d.ellipse([sx[0]-rr, sy[0]-rr*0.35, sx[0]+rr, sy[0]+rr*0.35], fill=(8, 10, 20, 130))

    # legs (tripod gait)
    leg_ph = [0, np.pi, 0, np.pi, 0, np.pi]
    leg_sp = [1, -1, 1, -1, 1, -1]
    leg_root = [(1.6, 1.5), (0.0, 1.8), (-1.6, 1.5), (1.6, -1.5), (0.0, -1.8), (-1.6, -1.5)]
    for i, (rx, ry) in enumerate(leg_root):
        side = 1 if ry > 0 else -1
        ph = f["phase"] + leg_ph[i]
        sw = 1.8 * np.sin(ph) * leg_sp[i]
        lift = max(0.0, np.sin(ph)) * 1.6
        foot = to_world([rx + sw, ry + side * 3.6, -f["z"] + lift])
        knee = to_world([rx + sw * 0.4, ry + side * 2.2, -0.6])
        root = to_world([rx, ry, -0.1])
        _seg(d, cam, root, knee, 0.42, (74, 51, 36, 255), W, H)
        _seg(d, cam, knee, foot, 0.34, (74, 51, 36, 255), W, H)

    # abdomen (striped)
    for i, (ax, ar, col) in enumerate([(-2.6, 2.1, (150, 92, 52)), (-4.1, 1.8, (120, 72, 40)),
                                        (-5.4, 1.4, (150, 92, 52)), (-6.4, 1.0, (110, 64, 36))]):
        _sphere(d, cam, to_world([ax, 0, 0.25]), ar, col, W, H)

    # wings
    flap = np.sin(f["flap"]) * 0.62
    for side in (1, -1):
        root = to_world([-1.2, side * 1.2, 1.6])
        tip1 = to_world([-1.2 + 4.5 * np.cos(flap), side * (1.2 + 6.2), 1.6 + 4.5 * np.sin(flap)])
        tip2 = to_world([-4.8 + 3.0 * np.cos(flap), side * (1.2 + 4.6), 1.2 + 3.0 * np.sin(flap)])
        back = to_world([-4.2, side * 1.6, 1.2])
        _poly(d, cam, [root, tip1, tip2, back], (225, 228, 255, 88), W, H)

    # thorax + head + eyes
    _sphere(d, cam, to_world([0, 0, 0.55]), 2.7, (138, 90, 46), W, H)
    _sphere(d, cam, to_world([0.2, 0, 1.6]), 1.7, (120, 78, 40), W, H)
    _sphere(d, cam, to_world([2.6, 0, 0.9]), 1.9, (112, 70, 38), W, H)
    for side in (1, -1):
        _sphere(d, cam, to_world([3.1, side * 1.25, 1.35]), 1.25, (158, 42, 34), W, H)
        # antenna
        a0 = to_world([3.9, side * 0.7, 1.9])
        a1 = to_world([5.6, side * 1.1, 3.0])
        _seg(d, cam, a0, a1, 0.16, (90, 62, 40, 255), W, H)

    # HUD
    st = world.stats or {}
    hz = st.get("hz", {})
    lines = [
        "FLY BRAIN LAB  ·  MaleCNS connectome (164,740 neurons) · live",
        f"t={st.get('t',0)}s   speed={st.get('speed',0)} mm/s   dist-to-light={st.get('dist',0)} mm   caught={st.get('caught',0)}",
        f"brain {st.get('brain_x',0)}x real-time   VIS {hz.get('vis_L',0)}/{hz.get('vis_R',0)} Hz   "
        f"DN {hz.get('dn_L',0)}/{hz.get('dn_R',0)} Hz   MOTOR {hz.get('motor',0)} Hz",
    ]
    y = 12
    for i, s in enumerate(lines):
        d.text((13, y), s, font=FONT_B if i == 0 else FONT_S,
               fill=(255, 230, 170) if i == 0 else (210, 220, 238))
        y += 27
    return img
