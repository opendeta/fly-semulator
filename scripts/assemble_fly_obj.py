#!/usr/bin/env python3
"""Assemble the high-res NeuroMechFly meshes with the verified FK and write one OBJ
that Blender can render with a proper material."""
import sys, numpy as np
sys.path.insert(0, "/workspace/fly/art")
import render3d as R

HI = "/tmp/nmf/data/design/meshes/stl"
NAME = {  # rigging name -> high-res mesh file
    "c_thorax": "Thorax", "c_head": "Head", "c_rostrum": "Rostrum", "c_haustellum": "Haustellum",
    "c_abdomen12": "A1A2", "c_abdomen3": "A3", "c_abdomen4": "A4", "c_abdomen5": "A5", "c_abdomen6": "A6",
    "l_eye": "LEye", "r_eye": "REye", "l_pedicel": "LAntenna", "r_pedicel": "RAntenna",
    "l_wing": "LWing", "r_wing": "RWing", "l_haltere": "LHaltere", "r_haltere": "RHaltere",
}
for side in ("L", "R"):
    for leg, tag in (("F", "f"), ("M", "m"), ("H", "h")):
        NAME[f"{side.lower()}{tag}_coxa"] = f"{side}{leg}Coxa"
        NAME[f"{side.lower()}{tag}_trochanterfemur"] = f"{side}{leg}Femur"
        NAME[f"{side.lower()}{tag}_tibia"] = f"{side}{leg}Tibia"
        for i in range(1, 6):
            NAME[f"{side.lower()}{tag}_tarsus{i}"] = f"{side}{leg}Tarsus{i}"

rig = R.load_rig()
T = R.world_transforms(rig)
# spread the wings outward/back like the reference figure
import numpy as _np
def _rot(axis, deg):
    a = _np.radians(deg); c, sn = _np.cos(a), _np.sin(a)
    if axis == "z":
        return _np.array([[c, -sn, 0], [sn, c, 0], [0, 0, 1]], _np.float32)
    if axis == "y":
        return _np.array([[c, 0, sn], [0, 1, 0], [-sn, 0, c]], _np.float32)
    return _np.array([[1, 0, 0], [0, c, -sn], [0, sn, c]], _np.float32)
WING_SPREAD = True
for nm in list(T):
    if nm.endswith("_wing"):
        side = 1.0 if nm[0] == "l" else -1.0
        Rw, tw = T[nm]
        T[nm] = (_rot("z", 26.0 * side) @ _rot("y", 30.0) @ _rot("x", -12.0) @ Rw, tw)
verts, faces = [], []
off = 0
used = 0
for name, (Rp, tp) in sorted(T.items()):
    meshname = NAME.get(name)
    if meshname is None:
        continue
    path = f"{HI}/{meshname}.stl"
    try:
        tri, _ = R.load_stl(path)
    except FileNotFoundError:
        continue
    tri = tri * 1000.0                       # STL is in metres, the rig is in mm
    v = (tri.reshape(-1, 3) @ Rp.T + tp)
    f = np.arange(len(v)).reshape(-1, 3) + off
    verts.append(v); faces.append(f)
    off += len(v); used += 1
V = np.concatenate(verts); F = np.concatenate(faces)
V = (V - V.mean(0)) / 1000.0                 # centre and convert mm -> m (Blender units)
print("parts:", used, "verts:", len(V), "faces:", len(F))
with open("/workspace/fly/art/fly_assembled.obj", "w") as fh:
    fh.write("# NeuroMechFly assembled by fly-semulator\n")
    for x, y, z in V:
        fh.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
    for a, b, c in F:
        fh.write(f"f {a+1} {b+1} {c+1}\n")
np.save("/workspace/fly/art/fly_bbox.npy", np.stack([V.min(0), V.max(0)]))
print("size (mm):", ((V.max(0) - V.min(0)) * 1000).round(2))
