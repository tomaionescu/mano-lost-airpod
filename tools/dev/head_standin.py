"""Blender: a stand-in head scan cut out of a full-body scan, to test scan_wrap's "head_scan" without a real one.
The bust (head, hair, neck, top of the shoulders), optionally with the face narrowed in X, is turned, scaled and
moved at random and exported like a Tripo / Hunyuan GLB (+Y up, one PBR material, arbitrary unit and facing).
The random transform is written next to it (<out>.json), for reference only: the build must find it by itself.

usage: Blender -b -P tools/dev/head_standin.py -- <scan.glb> <out.glb> [narrow=0.06] [neck=0.004] [seed=7]
                                                   [yaw=<deg>] [tilt=<deg>]
narrow: the face's width change; neck: the neck pushed out by this (m), to try the seam's blend band.
"""
import bpy, bmesh, sys, os, json, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "blender"))
import scan_wrap as sw

argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]
opts = dict(a.split("=", 1) for a in argv[2:] if "=" in a)
narrow, seed = float(opts.get("narrow", 0)), int(opts.get("seed", 7))
work = os.path.join(os.path.dirname(os.path.abspath(out)), "standin_work")
os.makedirs(work, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scan = sw.load_scan(src)
V = sw.world_verts(scan)
H, top = float(np.ptp(V[:, 2])), float(V[:, 2].max())
k = H / 1.8                                                  # the scan's unit, roughly metres
shots = sw.face_landmarks(sw.render_views(scan, work, (0, 90, 180, 270)), ROOT)
front = max([s for s in shots if s["face"]], key=lambda s: s["face"]["width"])
right = np.array(front["mw"].col[0].xyz)
fwd = np.array(front["mw"].col[2].xyz)                       # towards the camera: where the face looks
bvh = BVHTree.FromPolygons(V.tolist(), sw.triangles(scan.data).tolist(), all_triangles=True)
lm = {}
for i, p in enumerate(front["face"]["pts"][:468]):
    loc, n, _, _ = bvh.ray_cast(sw.pixel_to_world(front, p[0], p[1]), Vector(-fwd), 10.0)
    if loc is not None and n.dot(Vector(fwd)) > 0.35:
        lm[i] = np.array(loc)
print("standin: front at", front["angle"], "deg,", len(lm), "landmarks")

# the bust: everything above the top of the shoulders
bm = bmesh.new()
bm.from_mesh(scan.data)
cut = top - 0.25 * H
bmesh.ops.delete(bm, geom=[f for f in bm.faces if min(v.co.z for v in f.verts) < cut], context='FACES')
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
bm.to_mesh(scan.data)
bm.free()
V = sw.world_verts(scan)

if narrow:
    # the face (in front of the ears' landmarks, from under the chin to the forehead's top) narrowed about its
    # midline, fading out over 2 cm: eyes, nose, mouth, cheeks and jaw move in; ears, hair and neck stay
    c = lm[1] if 1 in lm else np.mean([lm[i] for i in (33, 263) if i in lm], 0)
    ears = [lm[i] for i in sw.EARS if i in lm]
    dep_ear = float(np.mean([(p - c) @ fwd for p in ears]))
    chin = min([lm[i] for i in sw.CHIN if i in lm], key=lambda p: p[2])
    brow_top = lm[10][2] if 10 in lm else max(p[2] for p in lm.values())
    lat, dep = (V - c) @ right, (V - c) @ fwd
    w = (sw.smoothstep(dep_ear, dep_ear + 0.02 * k, dep) *
         sw.smoothstep(chin[2] - 0.04 * k, chin[2] - 0.015 * k, V[:, 2]) *
         (1.0 - sw.smoothstep(brow_top, brow_top + 0.02 * k, V[:, 2])))
    V = V - narrow * (w * lat)[:, None] * right[None]
    sw.set_world_verts(scan, V)
    L = np.array(list(lm.values()))
    print(f"standin: face narrowed {narrow * 100:.0f}% in X ({int((w > 0.99).sum())} vertices fully, "
          f"{int((w > 0.01).sum())} in part); face landmarks' spread was {np.ptp((L - c) @ right) / k * 1000:.1f} mm")

neck = float(opts.get("neck", 0))
if neck:
    # a thicker neck (as another reconstruction would make it): pushed out from the neck's axis under the chin and,
    # behind the ears, up to 3 cm under them; the face stays as it is
    c = lm[1] if 1 in lm else np.mean([lm[i] for i in (33, 263) if i in lm], 0)
    ears = [lm[i] for i in sw.EARS if i in lm]
    ear = np.mean(ears, 0)
    dep_ear = float((ear - c) @ fwd)
    chin = min([lm[i] for i in sw.CHIN if i in lm], key=lambda p: p[2])
    dep = (V - c) @ fwd
    w = np.maximum(1.0 - sw.smoothstep(chin[2] - 0.03 * k, chin[2] - 0.01 * k, V[:, 2]),
                   (1.0 - sw.smoothstep(dep_ear, dep_ear + 0.02 * k, dep)) *
                   (1.0 - sw.smoothstep(ear[2] - 0.05 * k, ear[2] - 0.03 * k, V[:, 2])))
    band = (V[:, 2] > chin[2] - 0.06 * k) & (V[:, 2] < chin[2] - 0.02 * k)
    ax = V[band][:, :2].mean(0)
    rad = V[:, :2] - ax
    rad /= np.maximum(np.linalg.norm(rad, axis=1, keepdims=True), 1e-9)
    V = V.copy()
    V[:, :2] += neck * k * w[:, None] * rad
    sw.set_world_verts(scan, V)
    print(f"standin: neck pushed out {neck * 1000:.1f} mm ({int((w > 0.99).sum())} vertices fully)")

# a Tripo-like placement: any facing, slightly tilted, any unit, off centre
rng = np.random.default_rng(seed)
yaw, tilt, tilt_dir = rng.uniform(0, 360), rng.uniform(-8, 8), rng.uniform(0, 360)
yaw, tilt = float(opts.get("yaw", yaw)), float(opts.get("tilt", tilt))     # yaw=, tilt= (deg) force them
scale = float(np.exp(rng.uniform(np.log(0.3), np.log(3.0))))
move = rng.uniform(-1, 1, 3) * scale
axis = Vector((math.cos(math.radians(tilt_dir)), math.sin(math.radians(tilt_dir)), 0))
lo, hi = V.min(0), V.max(0)
M = (Matrix.Translation(Vector(move)) @ Matrix.Scale(scale / H, 4) @ Matrix.Rotation(math.radians(tilt), 4, axis) @
     Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Translation(-Vector((lo + hi) / 2)))
scan.data.transform(M)
scan.data.update()
scan.name = "head"
bpy.ops.object.select_all(action='DESELECT')
scan.select_set(True)
bpy.context.view_layer.objects.active = scan
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=True, export_yup=True,
                          export_image_format='AUTO', export_animations=False, export_skins=False)
json.dump({"src": os.path.relpath(src, ROOT), "narrow": narrow, "neck": neck, "seed": seed, "yaw_deg": yaw, "tilt_deg": tilt,
           "tilt_dir_deg": tilt_dir, "unit_scale": scale / H, "move": move.tolist(), "verts": len(scan.data.vertices),
           "matrix": [list(r) for r in M]}, open(out + ".json", "w"), indent=1)
print(f"standin: {len(scan.data.vertices)} verts, yaw {yaw:.1f} deg, tilt {tilt:.1f} deg, unit x{scale / H:.3f} -> {out}")
