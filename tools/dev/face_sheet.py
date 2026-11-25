"""Blender: a review sheet of a character's face from its .glb (no Godot import needed): front, three-quarter
and profile at rest, plus blink, mouth open and smile from its ARKit shapes, and a full-body front view.

usage: Blender -b -P tools/dev/face_sheet.py -- <character.glb> <out.png> [label]
"""
import bpy, sys, os, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
glb, out = argv[0], argv[1]
label = argv[2] if len(argv) > 2 else os.path.basename(glb)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
for o in scene.objects:
    if o.name.startswith("Icosphere"):
        o.hide_render = True
body = next(o for o in scene.objects if o.type == 'MESH' and o.name.endswith("_body"))
keys = body.data.shape_keys.key_blocks if body.data.shape_keys else {}
H = max((body.matrix_world @ v.co).z for v in body.data.vertices)
head_z = H - 0.115
for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        scene.render.engine = e
        break
    except TypeError:
        pass
scene.render.resolution_x = scene.render.resolution_y = 520
scene.render.film_transparent = False
w = bpy.data.worlds.new("w")
scene.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.42, 0.44, 0.48, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.5
for name, loc, energy in (("key", (0.9, -1.5, H + 0.35), 140), ("fill", (-1.3, -1.1, H - 0.05), 55),
                          ("rim", (0.3, 1.4, H + 0.2), 70)):
    l = bpy.data.objects.new(name, bpy.data.lights.new(name, 'AREA'))
    l.data.energy = energy
    l.data.size = 1.0
    l.location = loc
    scene.collection.objects.link(l)
    l.rotation_euler = (Vector((0, 0, head_z)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
tiles = []


def shot(tag, ang, dist=0.62, lens=85, z=head_z, shapes=None, full=False):
    for k in keys:
        k.value = 0.0
    for n, v in (shapes or {}).items():
        if n in keys:
            keys[n].value = v
    a = math.radians(ang)
    d = Vector((math.sin(a), -math.cos(a), 0))
    if full:
        cam.data.lens = 50
        cam.location = d * 4.4 + Vector((0, 0, H * 0.55))
        target = Vector((0, 0, H * 0.5))
    else:
        cam.data.lens = lens
        cam.location = d * dist + Vector((0, 0, z + 0.01))
        target = Vector((0, 0, z))
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    path = out + f".{tag}.png"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    tiles.append((tag, path))


shot("front", 0)
shot("34", 35)
shot("profile", 80)
shot("blink", 0, shapes={"eyeBlinkLeft": 1, "eyeBlinkRight": 1})
shot("talk", 0, shapes={"jawOpen": 0.45, "mouthFunnel": 0.15})
shot("smile", 0, shapes={"mouthSmileLeft": 0.8, "mouthSmileRight": 0.8, "cheekSquintLeft": 0.4, "cheekSquintRight": 0.4})
shot("full", 0, full=True)
# contact sheet with Blender's image API (no PIL inside Blender)
T = 520
cols = 4
rows = (len(tiles) + cols - 1) // cols
sheet = bpy.data.images.new("sheet", T * cols, T * rows)
import numpy as np
buf = np.zeros((T * rows, T * cols, 4), np.float32)
buf[..., 3] = 1
for i, (tag, path) in enumerate(tiles):
    im = bpy.data.images.load(path)
    px = np.empty(T * T * 4, np.float32)
    im.pixels.foreach_get(px)
    r, c = i // cols, i % cols
    buf[(rows - 1 - r) * T:(rows - r) * T, c * T:(c + 1) * T] = px.reshape(T, T, 4)
    os.remove(path)
sheet.pixels.foreach_set(buf.ravel())
sheet.filepath_raw = out
sheet.file_format = 'PNG'
sheet.save()
print("face sheet:", out, "height", round(H, 3), "shapes", len(keys))
