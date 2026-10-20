import bpy, mathutils, math, sys, os
A = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
RX = int(A[0]) if A else 1600; RY = int(A[1]) if len(A) > 1 else 900
SAMPLES = int(A[2]) if len(A) > 2 else 96
OUT = A[3] if len(A) > 3 else "/workspace/fly/art/fly_blender.png"

# clean scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = False
sc.cycles.max_bounces = 10
sc.cycles.transmission_bounces = 10
sc.cycles.transparent_max_bounces = 10
sc.render.resolution_x, sc.render.resolution_y = RX, RY
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Base Contrast'
sc.render.image_settings.file_format = 'PNG'
sc.render.filepath = OUT
sc.render.film_transparent = False

# near-black world
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.006, 0.012, 0.028, 1.0)
bg.inputs[1].default_value = 1.0

# import the assembled fly
bpy.ops.wm.obj_import(filepath="/workspace/fly/art/fly_assembled.obj")
fly = [o for o in bpy.data.objects if o.type == 'MESH'][0]
print("imported:", fly.name, "verts", len(fly.data.vertices))

mat = bpy.data.materials.new("FlyGlass"); mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
def S(name, val, alt=None):
    for n in ([name] + ([alt] if alt else [])):
        if n in bsdf.inputs:
            try: bsdf.inputs[n].default_value = val; return True
            except Exception: pass
    return False
S("Base Color", (0.04, 0.42, 1.0, 1.0))
S("Roughness", 0.22)
S("IOR", 1.45)
S("Transmission Weight", 0.30, "Transmission")
S("Subsurface Weight", 0.22, "Subsurface")
if "Subsurface Radius" in bsdf.inputs:
    bsdf.inputs["Subsurface Radius"].default_value = (0.00035, 0.0006, 0.0010)
S("Emission Color", (0.06, 0.45, 1.0, 1.0))
S("Emission Strength", 0.35)
S("Coat Weight", 0.35, "Clearcoat")
fly.data.materials.clear(); fly.data.materials.append(mat)

bb = [fly.matrix_world @ mathutils.Vector(c) for c in fly.bound_box]
mn = mathutils.Vector((min(p[i] for p in bb) for i in range(3)))
mx = mathutils.Vector((max(p[i] for p in bb) for i in range(3)))
ctr = (mn + mx) / 2; size = mx - mn
print("bbox mm:", [round(v*1000, 2) for v in size])

cam_data = bpy.data.cameras.new("Cam"); cam = bpy.data.objects.new("Cam", cam_data)
sc.collection.objects.link(cam); sc.camera = cam
cam_data.lens = 55.0; cam_data.clip_start = 0.00005; cam_data.clip_end = 1.0
D = 0.0100
cam.location = (ctr.x, ctr.y - D, ctr.z + 0.0006)
cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
bpy.context.view_layer.update()

def light(name, loc, energy, size_, color):
    ld = bpy.data.lights.new(name, type='AREA')
    ld.energy = energy; ld.size = size_; ld.color = color
    ob = bpy.data.objects.new(name, ld); sc.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (ctr - mathutils.Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return ob
light("key",  (ctr.x + 0.005, ctr.y - 0.007, ctr.z + 0.006), 0.014, 0.008, (0.85, 0.95, 1.0))
light("rim",  (ctr.x - 0.007, ctr.y + 0.006, ctr.z + 0.003), 0.022, 0.006, (0.45, 0.75, 1.0))
light("fill", (ctr.x + 0.001, ctr.y + 0.005, ctr.z - 0.006), 0.008, 0.010, (0.35, 0.55, 1.0))
bpy.context.view_layer.update()

# the six coloured brain regions inside the head
import json
if os.path.exists("/workspace/fly/art/brain_blobs.json"):
    hx = size.x
    head_c = mathutils.Vector((ctr.x + hx * 0.360, ctr.y, ctr.z + 0.0001))
    head_s = mathutils.Vector((hx * 0.100, size.y * 0.22, size.z * 0.22))
    PAL = [(1.0, 0.12, 0.5), (1.0, 0.5, 0.08), (0.42, 0.3, 1.0),
           (0.08, 0.8, 1.0), (1.0, 0.9, 0.2), (0.25, 1.0, 0.5)]
    for i, b in enumerate(json.load(open("/workspace/fly/art/brain_blobs.json"))[:6]):
        m = bpy.data.materials.new(f"Brain{i}"); m.use_nodes = True
        n = m.node_tree.nodes.get("Principled BSDF")
        for nm in ("Emission Color", "Emission"):
            if nm in n.inputs: n.inputs[nm].default_value = (*PAL[i], 1.0); break
        if "Emission Strength" in n.inputs: n.inputs["Emission Strength"].default_value = 3.0
        if "Base Color" in n.inputs: n.inputs["Base Color"].default_value = (*PAL[i], 1.0)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=24, ring_count=12)
        ob = bpy.context.object; ob.name = f"Brain{i}"; ob.data.materials.append(m)
        ob.location = head_c + mathutils.Vector((b["c"][0]*head_s.x, b["c"][1]*head_s.y, b["c"][2]*head_s.z))
        ob.scale = (max(b["r"][0]*head_s.x*0.9, 0.00008), max(b["r"][1]*head_s.y*0.9, 0.00008),
                    max(b["r"][2]*head_s.z*0.9, 0.00008))
bpy.context.view_layer.update()
print("rendering", RX, RY, SAMPLES)
bpy.ops.render.render(write_still=True)
print("saved", OUT)
