"""Render a head scan GLB (Hunyuan3D / Tripo output) from 8 directions, untextured clay and textured, to compare
head scans with each other and with the person's photos.

usage: Blender -b --factory-startup -P tools/dev/head_scan_views.py -- <scan.glb> <out_dir> [res]
Writes <out_dir>/<stem>_<clay|tex>_<yaw>.png for yaw 0, 45, ..., 315 (yaw 0 looks along -Y at the side the
glTF's +Z faces, i.e. the usual front of a generated model), and <stem>_info.json (faces, size, materials).
"""
import bpy, sys, os, json, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]
res = int(argv[2]) if len(argv) > 2 else 900
os.makedirs(out, exist_ok=True)
stem = os.path.splitext(os.path.basename(src))[0]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
dg = bpy.context.evaluated_depsgraph_get()
pts = []
nf = 0
for o in meshes:
    nf += len(o.data.polygons)
    pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
c = (lo + hi) / 2
size = hi - lo
R = max(size) * 1.25

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
scene.render.resolution_x = scene.render.resolution_y = res
scene.render.film_transparent = False
scene.view_settings.view_transform = 'Standard'
world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.42, 0.43, 0.45, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 85
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
fov = 2 * math.atan(cam_data.sensor_width / 2 / cam_data.lens)
dist = (max(size.x, size.z, size.y) * 0.62) / math.tan(fov / 2)


def light(name, loc, energy):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.size = max(size) * 1.5
    lo_ = bpy.data.objects.new(name, ld)
    lo_.location = loc
    lo_.rotation_euler = (c - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    scene.collection.objects.link(lo_)


light("key", c + Vector((-1.2, -2.0, 1.0)) * max(size), 300 * max(size) ** 2)
light("fill", c + Vector((1.5, -1.5, 0.2)) * max(size), 120 * max(size) ** 2)
light("rim", c + Vector((0.5, 2.0, 1.2)) * max(size), 150 * max(size) ** 2)

orig = {o.name: [s.material for s in o.material_slots] for o in meshes}
clay = bpy.data.materials.new("clay")
clay.use_nodes = True
bsdf = clay.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.62, 0.6, 0.58, 1)
bsdf.inputs["Roughness"].default_value = 0.55

for mode in ("clay", "tex"):
    for o in meshes:
        for i, s in enumerate(o.material_slots):
            s.material = clay if mode == "clay" else orig[o.name][i]
    for yaw in range(0, 360, 45):
        a = math.radians(yaw)
        # yaw 0: camera on -Y looking +Y (Blender's front view of a glTF model facing +Z_gltf = -Y_blender)
        cam.location = c + Vector((math.sin(a) * dist, -math.cos(a) * dist, 0))
        cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = os.path.join(out, f"{stem}_{mode}_{yaw:03d}.png")
        bpy.ops.render.render(write_still=True)

json.dump({"faces": nf, "objects": len(meshes), "size": list(size), "centre": list(c),
           "materials": sorted({m.name for ms in orig.values() for m in ms if m})},
          open(os.path.join(out, f"{stem}_info.json"), "w"), indent=1)
print("done", stem, nf, list(size))
