"""Render one character's head with several hairstyles for comparison.
Blender -b -P try_hair.py -- <cid> <hair1> <hair2> ..."""
import bpy, sys, os, importlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import build_human as bh, cast
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.assetservice import AssetService
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
cid, hairs = argv[0], argv[1:]
spec = dict(cast.CAST[cid]); spec["hair"] = None; spec["glasses"] = None
bpy.ops.wm.read_homefile(use_empty=True)
s = HumanService.get_default_deserialization_settings(); s["subdiv_levels"] = 0; s["load_clothes"] = False
info = bh.human_info(spec, list(spec["outfits"])[0]); info["clothes"] = []
bm = HumanService.deserialize_from_dict(info, s)
rig = bm.parent
for o in rig.children:
    if o.type == 'MESH':
        k = "skin" if o == bm else bh.classify(o, bm, o.name.split(".", 1)[-1], spec)
        bh.rebuild_material(o, k, None, spec, cid)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.resolution_x, scene.render.resolution_y = 500, 600
w = bpy.data.worlds.new("w"); w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (0.3, 0.32, 0.36, 1); scene.world = w
for name, loc, e in (("k", (1.2, -1.6, 2.2), 250), ("f", (-1.6, -1.2, 1.6), 90), ("r", (0.4, 1.8, 2.0), 200)):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = e; ld.size = 1.2
    lo = bpy.data.objects.new(name, ld); lo.location = loc; bpy.context.collection.objects.link(lo)
    lo.rotation_euler = (Vector((0, 0, 1.55)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
h = max((bm.matrix_world @ v.co).z for v in bm.data.vertices if True)
cd = bpy.data.cameras.new("c"); cd.lens = 70; cam = bpy.data.objects.new("c", cd); bpy.context.collection.objects.link(cam); scene.camera = cam
for hair in hairs:
    path = AssetService.find_asset_absolute_path(f"{hair}/{hair}.mhclo", "hair")
    before = set(o.name for o in bpy.data.objects)
    HumanService.add_mhclo_asset(path, bm, asset_type="Hair", subdiv_levels=0, material_type="MAKESKIN")
    new = [o for o in bpy.data.objects if o.name not in before]
    for o in new:
        if o.type == 'MESH':
            sp = dict(spec); sp["hair"] = hair
            bh.rebuild_material(o, "hair", None, sp, cid)
    for i, (loc, tag) in enumerate((((0.35, -1.0, h - 0.05), "a"), ((-0.9, -0.45, h - 0.02), "b"))):
        cam.location = loc
        cam.rotation_euler = (Vector((0, 0, h - 0.12)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = os.path.join(bh.PREVIEW, f"hair_{cid}_{hair}_{tag}.png")
        bpy.ops.render.render(write_still=True)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
print("DONE")
