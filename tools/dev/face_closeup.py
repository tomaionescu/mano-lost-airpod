"""Blender: one large front close-up of a character's face (or of a raw scan) under flat studio light.
usage: Blender -b -P tools/dev/face_closeup.py -- <file.glb> <out.png> [scan]"""
import bpy, sys, math
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
glb, out = argv[0], argv[1]
raw = len(argv) > 2 and argv[2] == "scan"
opts = dict(a.split("=", 1) for a in argv[2:] if "=" in a)   # dist=<m> zoom; tex=<png> replaces the head colour map
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
scene = bpy.context.scene
if "tex" in opts:
    new = bpy.data.images.load(opts["tex"])
    for m in bpy.data.materials:
        if m.name.endswith("_skin_head") and m.node_tree:
            for n in m.node_tree.nodes:
                if n.type == 'TEX_IMAGE' and n.image and n.image.colorspace_settings.name == 'sRGB':
                    n.image = new
for o in scene.objects:
    if o.name.startswith("Icosphere"):
        o.hide_render = True
arm = next((o for o in scene.objects if o.type == 'ARMATURE'), None)
if arm and "anim" in opts:
    # anim=<clip>[@frame]: pose the body with one of its clips (e.g. anim=idle@20), as the game would
    clip, _, fr = opts["anim"].partition("@")
    act = next((a for a in bpy.data.actions if a.name.split("|")[-1].lower().endswith(clip.lower())), None)
    print("anim", clip, "->", act.name if act else None)
    if act:
        arm.animation_data_create()
        arm.animation_data.action = act
        if hasattr(arm.animation_data, "action_slot") and act.slots:
            arm.animation_data.action_slot = act.slots[0]
        scene.frame_set(int(fr or 1))
elif arm:
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
# shape=<key>:<value>,...: pose the face (e.g. shape=jawOpen:0.4)
for kv in (opts["shape"].split(",") if "shape" in opts else []):
    k, v = kv.split(":")
    for o in scene.objects:
        if o.type == 'MESH' and o.data.shape_keys and k in o.data.shape_keys.key_blocks:
            o.data.shape_keys.key_blocks[k].value = float(v)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
pts = []
for o in scene.objects:
    if o.type == 'MESH' and not o.hide_render:
        ev = o.evaluated_get(dg)
        m = ev.to_mesh()
        pts += [o.matrix_world @ v.co for v in list(m.vertices)[::5]]
        ev.to_mesh_clear()
zs = [p.z for p in pts]
top, bot = max(zs), min(zs)
H = top - bot
# the face looks along -Y for built characters; raw scans face +X/-X/+Y: find the side with the nose
cx = sum(p.x for p in pts) / len(pts); cy = sum(p.y for p in pts) / len(pts)
headpts = [p for p in pts if p.z > top - 0.25 * H * 0.6]
best = max(((math.sin(math.radians(a)), -math.cos(math.radians(a)), a) for a in (0, 90, 180, 270)),
           key=lambda d: max(p.x * d[0] + p.y * d[1] for p in headpts))
d = Vector((best[0], best[1], 0))
# hide=<a,b>: leave out meshes whose object or material name contains one of these (to find a stray part)
for o in scene.objects:
    if "hide" not in opts or o.type != 'MESH':
        continue
    keys = opts["hide"].split(",")
    if any(k in o.name for k in keys):
        o.hide_render = True
    elif any(k in (s.material.name if s.material else "") for k in keys for s in o.material_slots):
        # a body mesh with several materials: drop only the matching faces
        me = o.data
        idx = [i for i, s in enumerate(o.material_slots) if s.material and any(k in s.material.name for k in keys)]
        import bmesh
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in idx], context='FACES')
        bm.to_mesh(me); bm.free()
# cull=1: hide back faces like the game does (Blender shows both sides; a folded triangle only shows in Godot)
if opts.get("cull"):
    for m in bpy.data.materials:
        m.use_backface_culling = True
# flat=1: every material a flat colour of its own, to see which part is which
if opts.get("flat") == "uv":
    # the head's UV as colour (EXR, linear): which texels a pixel of the render reads
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        em = nt.nodes.new("ShaderNodeEmission")
        o_ = nt.nodes.new("ShaderNodeOutputMaterial")
        if m.name.endswith("_skin_head"):
            uvn = nt.nodes.new("ShaderNodeUVMap")
            sep = nt.nodes.new("ShaderNodeSeparateXYZ")
            com = nt.nodes.new("ShaderNodeCombineXYZ")
            nt.links.new(uvn.outputs[0], sep.inputs[0])
            nt.links.new(sep.outputs[0], com.inputs[0]); nt.links.new(sep.outputs[1], com.inputs[1])
            com.inputs[2].default_value = 1.0
            nt.links.new(com.outputs[0], em.inputs[0])
        else:
            em.inputs[0].default_value = (0, 0, 0, 1)
        nt.links.new(em.outputs[0], o_.inputs[0])
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_depth = '32'
    scene.render.filter_size = 0.0
elif opts.get("flat"):
    import colorsys
    for i, m in enumerate(bpy.data.materials):
        if not m.use_nodes:
            continue
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs[0].default_value = (*colorsys.hsv_to_rgb((i * 0.618) % 1.0, 0.8, 0.9), 1)
        o_ = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs[0], o_.inputs[0])
        print("flat", m.name, [round(c, 2) for c in em.inputs[0].default_value[:3]])
for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        scene.render.engine = e; break
    except TypeError:
        pass
scene.render.resolution_x = scene.render.resolution_y = int(opts.get("res", 900))
w = bpy.data.worlds.new("w"); scene.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.5, 0.52, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
z = top - 0.115 * (H / 1.75)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.lens = float(opts.get("lens", 85))
if "ortho" in opts:   # ortho=<m>: orthographic, no perspective (as the scan's own views; frame width for a 1.75 m figure)
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = float(opts["ortho"]) * H / 1.75
c = Vector((cx, cy, z))
cam.location = c + d * float(opts.get("dist", 0.75))
if "dz" in opts:
    c = c + Vector((0, 0, float(opts["dz"])))
    cam.location = cam.location + Vector((0, 0, float(opts["dz"])))
if "camdz" in opts:   # camera only: look up from below the chin, or down from above
    cam.location = cam.location + Vector((0, 0, float(opts["camdz"])))
if "side" in opts:    # camera only: swing round the head by this many degrees
    from mathutils import Matrix
    cam.location = c + Matrix.Rotation(math.radians(float(opts["side"])), 3, 'Z') @ (cam.location - c)
cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print("closeup", out)
