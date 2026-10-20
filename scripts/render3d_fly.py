#!/usr/bin/env python3
"""Render the real NeuroMechFly (micro-CT) fly as a translucent blue 'x-ray',
with the actual MaleCNS neuron cloud glowing inside its head."""
import numpy as np, yaml, struct
from PIL import Image, ImageDraw, ImageFilter

MESH = "/workspace/fly/art/meshes"
RIG = "/workspace/fly/art/rigging.yaml"
W, H = 1600, 900
BLUE = np.array([120, 215, 255], np.float32)

PARENT = {
    "c_head": "c_thorax", "c_rostrum": "c_head", "c_haustellum": "c_rostrum",
    "c_abdomen3": "c_thorax", "c_abdomen4": "c_abdomen3", "c_abdomen5": "c_abdomen4",
    "c_abdomen6": "c_abdomen5", "c_abdomen12": "c_abdomen6",
    "l_eye": "c_head", "l_pedicel": "c_head", "l_funiculus": "l_pedicel", "l_arista": "l_funiculus",
    "l_wing": "c_thorax", "l_haltere": "c_thorax",
}
for side in ("l", "r"):
    for leg in ("f", "m", "h"):
        p = f"{side}{leg}"
        PARENT[f"{p}_coxa"] = "c_thorax"
        PARENT[f"{p}_trochanterfemur"] = f"{p}_coxa"
        PARENT[f"{p}_tibia"] = f"{p}_trochanterfemur"
        PARENT[f"{p}_tarsus1"] = f"{p}_tibia"
        for i in range(2, 6):
            PARENT[f"{p}_tarsus{i}"] = f"{p}_tarsus{i-1}"
    for extra in ("eye", "pedicel", "funiculus", "arista", "wing", "haltere"):
        if f"r_{extra}" not in PARENT:
            PARENT[f"r_{extra}"] = "c_head" if extra in ("eye", "pedicel") else "c_thorax"
    PARENT["r_funiculus"] = "r_pedicel"
    PARENT["r_arista"] = "r_funiculus"


def quat_mat(q):
    w, x, y, z = q
    n = (w * w + x * x + y * y + z * z) ** 0.5 or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def load_stl(path):
    with open(path, "rb") as f:
        head = f.read(84)
        n = struct.unpack("<I", head[80:84])[0]
        data = np.frombuffer(f.read(n * 50), dtype=np.uint8).reshape(n, 50)
    tri = data[:, 12:48].copy().view("<f4").reshape(n, 3, 3).astype(np.float32)
    nrm = data[:, 0:12].copy().view("<f4").reshape(n, 3).astype(np.float32)
    return tri, nrm


def load_rig():
    rig = yaml.safe_load(open(RIG))
    out = {}
    for k, v in rig.items():
        out[k] = (np.array(v["pos"], np.float32), quat_mat(v["quat"]))
    return out


def rot_axis(axis, deg):
    a = np.radians(deg)
    c, sn = np.cos(a), np.sin(a)
    if axis == "y":
        return np.array([[c, 0, sn], [0, 1, 0], [-sn, 0, c]], np.float32)
    return np.array([[1, 0, 0], [0, c, -sn], [0, sn, c]], np.float32)


# how much to bend each leg joint so the fly stands instead of dangling
JOINT = {"coxa": ("y", 22.0), "trochanterfemur": ("y", -96.0),
         "tibia": ("y", 46.0), "tarsus1": ("y", 34.0), "tarsus2": ("y", 8.0)}


def extra_rot(name):
    for key, (ax, deg) in JOINT.items():
        if name.endswith(key) and name[:2] in ("lf", "lm", "lh", "rf", "rm", "rh"):
            side = 1.0 if name[0] == "l" else -1.0
            return rot_axis(ax, deg * side)
    return None


def world_transforms(rig):
    T = {}
    def build(name):
        if name in T:
            return T[name]
        pos, R = rig.get(name, (np.zeros(3, np.float32), np.eye(3, dtype=np.float32)))
        ex = extra_rot(name)
        if ex is not None:
            R = R @ ex
        par = PARENT.get(name)
        if par is None:
            T[name] = (R, pos)
        else:
            Rp, tp = build(par)
            T[name] = (Rp @ R, tp + Rp @ pos)
        side = 1.0 if name[0] == "l" else -1.0
        if name.endswith("_coxa"):                  # legs: angle down and slightly out
            Rw, tw = T[name]
            T[name] = (rot_axis("y", -26.0 * side) @ Rw, tw)
        if name.endswith("_wing"):                  # wings: sweep back and up, both sides alike
            Rw, tw = T[name]
            T[name] = (rot_axis("y", 30.0) @ rot_axis("x", -26.0 * side) @ Rw, tw)
        if name.endswith("_haltere"):
            Rw, tw = T[name]
            T[name] = (rot_axis("y", 20.0 * side) @ Rw, tw)
        return T[name]
    for k in rig:
        build(k)
    return T


def camera(yaw, pitch, roll, scale, cx, cy):
    cy_, sy_ = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cr, sr = np.cos(roll), np.sin(roll)
    Rz = np.array([[cy_, -sy_, 0], [sy_, cy_, 0], [0, 0, 1]], np.float32)
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]], np.float32)
    Rr = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]], np.float32)
    R = Rz @ Rx @ Rr
    def proj(P):
        Q = P @ R.T
        return np.stack([Q[:, 0] * scale + cx, cy - Q[:, 2] * scale, Q[:, 1]], -1)
    return R, proj


def main():
    rig = load_rig()
    T = world_transforms(rig)
    # global camera: a 3/4 side view like the reference image
    R, proj = camera(yaw=np.pi / 2 + 0.45, pitch=-0.12, roll=0.0, scale=250.0, cx=W * 0.52, cy=H * 0.52)
    items = []
    for name, (Rp, tp) in T.items():
        base = name[2:] if name[:2] in ("l_", "r_") else name
        meshname = ("l_" if name.startswith("l_") else "l_" if name.startswith("r_") else "") + base if False else None
        # left + centre meshes exist; right side mirrors the left one
        if name.startswith("r_"):
            src = MESH + "/l_" + name[2:] + ".stl"
        elif name.startswith("l_"):
            src = MESH + "/l_" + name[2:] + ".stl"
        else:
            src = MESH + "/" + name + ".stl"
        import os
        if not os.path.exists(src):
            continue
        tri, nrm = load_stl(src)
        tri = tri * 1000.0          # STL is in metres, the rigging is in mm
        if name.startswith("r_"):                     # mirror across the body's y axis
            tri = tri.copy(); tri[:, :, 1] *= -1
            nrm = nrm.copy(); nrm[:, 1] *= -1
        v = tri @ Rp.T + tp
        n = nrm @ Rp.T
        items.append((v, n))
    print("mesh parts rendered:", len(items))
    body = np.concatenate([v.reshape(-1, 3) for v, _ in items
                           if not any(v.shape[0] == 0 for _ in [0])])
    allv = body
    c = (allv.max(0) + allv.min(0)) / 2
    span = (allv.max(0) - allv.min(0)).max() * 0.66
    scale = 0.86 * min(W, H) / span
    R, proj = camera(yaw=-np.pi / 2 - 0.55, pitch=-0.16, roll=0.0, scale=scale,
                     cx=W * 0.52, cy=H * 0.52)
    # head bbox in world space (where the brain goes)
    head_v = []
    for name in ("c_head", "c_rostrum", "l_eye", "r_eye"):
        src = (MESH + "/l_" + name[2:] + ".stl") if name.startswith(("l_", "r_")) else (MESH + "/" + name + ".stl")
        import os as _os
        if not _os.path.exists(src):
            continue
        tri_h, _ = load_stl(src)
        tri_h = tri_h * 1000.0
        if name.startswith("r_"):
            tri_h = tri_h.copy(); tri_h[:, :, 1] *= -1
        Rp, tp = T[name]
        head_v.append(tri_h.reshape(-1, 3) @ Rp.T + tp)
    head_v = np.concatenate(head_v) if head_v else None

    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    # triangles, back to front
    tris = []
    for v, n in items:
        V = v - c
        P = proj(V.reshape(-1, 3)).reshape(-1, 3, 3)
        N = n @ R.T
        depth = P[:, :, 2].mean(1)
        for i in range(len(P)):
            tris.append((depth[i], P[i], N[i]))
    tris.sort(key=lambda t: -t[0])
    view = np.array([0, 0, -1], np.float32)
    for depth, P, N in tris:
        nz = N / (np.linalg.norm(N) + 1e-9)
        fres = 1.0 - abs(float(nz @ view))
        light = max(0.0, float(nz @ np.array([0.3, -0.6, -0.7], np.float32)))
        b = 0.26 + 0.72 * fres + 0.30 * light
        col = np.clip(BLUE * b, 0, 255)
        alpha = int(np.clip(20 + 105 * fres + 32 * light, 0, 190))
        d.polygon([(float(P[0, 0]), float(P[0, 1])), (float(P[1, 0]), float(P[1, 1])),
                   (float(P[2, 0]), float(P[2, 1]))],
                  fill=(int(col[0]), int(col[1]), int(col[2]), alpha))
    # ---- the real neuron cloud, glowing inside the head ----
    try:
        import sys as _sys
        _sys.path.insert(0, "/workspace/fly/scripts")
        from brain_art import load_points, render_cloud
        from scipy.ndimage import gaussian_filter as _gf
        if head_v is not None:
            hc = (head_v.max(0) + head_v.min(0)) / 2          # head centre (world)
            hs = head_v.max(0) - head_v.min(0)                # head size   (world)
            hp = proj(head_v - c)
            hx0, hx1 = float(hp[:, 0].min()), float(hp[:, 0].max())
            hy0, hy1 = float(hp[:, 1].min()), float(hp[:, 1].max())

            pts, _ = load_points(only_brain=True)
            pc = pts.mean(0); ps = pts.max(0) - pts.min(0)
            kk = 0.50 * float(hs.max()) / float(ps.max())

            # six neuron regions (k-means) -> the coloured blobs of the reference figure
            sd = pts.std(0) + 1e-6
            X = (pts / sd).astype(np.float32)
            rng = np.random.default_rng(3)
            C = X[rng.choice(len(X), 6, replace=False)].copy()
            for _ in range(14):
                dd = ((X[:, None, :] - C[None, :, :]) ** 2).sum(-1)
                lab = dd.argmin(1)
                for k in range(6):
                    if (lab == k).any():
                        C[k] = X[lab == k].mean(0)
            PAL = np.array([[255, 70, 150], [255, 150, 40], [130, 100, 255],
                            [40, 220, 255], [255, 230, 80], [90, 255, 160]], np.float32)

            canvas = np.asarray(img, np.float32)
            for k in range(6):
                m = lab == k
                if m.sum() < 50:
                    continue
                q = (pts[m] - pc) * kk + hc
                qp = proj(q - c)
                cxm, cym = float(qp[:, 0].mean()), float(qp[:, 1].mean())
                rx = float(qp[:, 0].std()) * 2.2 + 8
                ry = float(qp[:, 1].std()) * 2.2 + 8
                yy, xx = np.ogrid[:H, :W]
                mask = _gf(np.exp(-(((xx - cxm) / rx) ** 2 + ((yy - cym) / ry) ** 2)), 7.0)
                canvas += mask[:, :, None] * PAL[k][None, None, :] * 0.30

            # and the fine neuron cloud itself, softly
            hw = max(int((hx1 - hx0) * 0.55), 40); hh = max(int((hy1 - hy0) * 0.55), 40)
            cloud, _, _ = render_cloud(pts, PAL[lab], W=hw, H=hh, yaw=1.15, pitch=0.15,
                                       sigma=1.8, gain=1.0)
            cg = np.asarray(cloud, np.float32)
            cg = np.clip(cg / max(cg.max(), 1e-6) * 140.0, 0, 255)
            mm = cg.mean(-1, keepdims=True)
            cg = np.clip(mm + (cg - mm) * 2.0, 0, 255)
            cxa = int((hx0 + hx1) / 2 - cg.shape[1] / 2)
            cya = int((hy0 + hy1) / 2 - cg.shape[0] / 2)
            ys = slice(max(cya, 0), min(cya + cg.shape[0], H))
            xs = slice(max(cxa, 0), min(cxa + cg.shape[1], W))
            sub = cg[max(0, -cya):max(0, -cya) + (ys.stop - ys.start),
                     max(0, -cxa):max(0, -cxa) + (xs.stop - xs.start)]
            region = canvas[ys, xs]
            canvas[ys, xs] = 255.0 - (255.0 - region) * (255.0 - sub * 0.45) / 255.0
            img = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))
            print("brain: 6 regions + cloud inside the head")
    except Exception as e:
        print("neuron cloud skipped:", repr(e))

    base = np.asarray(img, np.float32)
    bloom = np.asarray(img.filter(ImageFilter.GaussianBlur(16)), np.float32)
    out = np.clip(base + bloom * 0.38, 0, 255).astype(np.uint8)
    im = Image.fromarray(out).transpose(Image.FLIP_LEFT_RIGHT)   # head to the right, like the reference
    im.save("/workspace/fly/art/fly_xray.png")
    im.resize((1200, 675), Image.LANCZOS).save("/workspace/fly/art/fly_xray_small.jpg", quality=86)
    print("saved fly_xray.png", im.size)


if __name__ == "__main__":
    main()
