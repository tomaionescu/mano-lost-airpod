"""Prototype A: render a built character with scan-shaped hair cards in Blender (EEVEE, neutral studio light).

usage: Blender -b -P tools/blender/proto_hair_A_render.py -- toma_fit1 anisha [base=1] [tag=_v1] [views=front,34,back,side]
       [res=1100] [samples=64] [shell=off|dark|keep] [cap=1] [occ=1] [bsdf=kk|split|principled] [test=1]
       [spec1=..] [spec2=..] [r1=..] [r2=..] [kknoise=..] [nstr=..]
reads  assets/characters/<stem>.glb (unchanged) and tools/out/proto_A/<stem>_cards.npz (proto_hair_A_grow.py)
writes tools/out/review/hair_proto_A_<id>_<view><tag>.png (prototype; test=1: tools/out/proto_A/tests/) and, with
       base=1, the current shell in the same light: tools/out/proto_A/base_<id>_<view>.png. Nothing in assets/ is written.
The scan shell is hidden by default (shell=off); the grower's scalp cap and inner occluder replace it.
bsdf=kk (default) is an EEVEE stand-in for the game's Kajiya-Kay hair shader (see add_cards); EEVEE has no
anisotropic specular, and the Principled BSDF turned every card facing the softboxes into a white blotch.
"""
import bpy, sys, os, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUTA = os.path.join(ROOT, "tools", "out", "proto_A")
REVIEW = os.path.join(ROOT, "tools", "out", "review")
IDS = {"toma_fit1": "toma", "anisha": "anisha", "ian": "ian", "joaquin": "joaquin", "mano_street": "mano"}

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opts = dict(a.split("=", 1) for a in argv if "=" in a)
stems = [a for a in argv if "=" not in a] or ["toma_fit1", "anisha"]
RES = int(opts.get("res", 1100))
SAMPLES = int(opts.get("samples", 64))
VIEWS = opts.get("views", "front,34,back,side").split(",")
TAG = opts.get("tag", "")


KEY_OFF = (-0.9, -1.6, 0.9)
KEY_DIR = tuple(float(c) for c in (np.array(KEY_OFF) / np.linalg.norm(KEY_OFF)))


def setup_scene(head_c, extent):
    scene = bpy.context.scene
    for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = e
            break
        except TypeError:
            pass
    ee = scene.eevee
    ee.taa_render_samples = SAMPLES
    for attr, val in (("use_raytracing", True), ("use_shadows", True), ("shadow_ray_count", 2),
                      ("shadow_step_count", 8), ("use_gtao", True)):
        if hasattr(ee, attr):
            setattr(ee, attr, val)
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    w = bpy.data.worlds.new("studio")
    scene.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.42, 0.43, 0.45, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.55
    # key (front left, above), fill (front right), rim (behind, above), all soft area lights aimed at the head
    for name, d, energy, size in (("key", KEY_OFF, 260, 0.9), ("fill", (1.5, -1.1, 0.2), 70, 1.6),
                                  ("rim", (0.6, 1.6, 1.1), 220, 0.7), ("rim2", (-1.2, 1.2, 0.4), 90, 0.9)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        if hasattr(ld, "use_shadow"):
            ld.use_shadow = True
        lo = bpy.data.objects.new(name, ld)
        lo.location = Vector(head_c) + Vector(d)
        scene.collection.objects.link(lo)
        lo.rotation_euler = (Vector(head_c) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 85
    return scene, cam


def frame(cam, target, yaw_deg, dist, dz=0.0):
    """Camera on a circle round the target: yaw 0 = in front (-Y), 90 = the character's left, 180 = behind."""
    a = math.radians(yaw_deg)
    off = Vector((math.sin(a), -math.cos(a), 0)) * dist + Vector((0, 0, dz))
    cam.location = Vector(target) + off
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()


def import_char(stem):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, "assets", "characters", stem + ".glb"))
    scene = bpy.context.scene
    for o in scene.objects:
        if o.name.startswith("Icosphere") or o.name.startswith("Cube"):
            o.hide_render = True
    arm = next((o for o in scene.objects if o.type == 'ARMATURE'), None)
    if arm:
        if arm.animation_data:
            arm.animation_data.action = None
        for pb in arm.pose.bones:
            pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    return arm


def shell_object():
    return next((o for o in bpy.context.scene.objects if o.type == 'MESH' and "hairshell" in o.name), None)


def add_cards(stem, data, atlas_path):
    V, F, UV, C = data["V"], data["F"], data["UV"], data["C"]
    me = bpy.data.meshes.new(stem + "_cards")
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    me.loops.add(len(F) * 4)
    me.polygons.add(len(F))
    me.loops.foreach_set("vertex_index", F.astype(np.int32).ravel())
    me.polygons.foreach_set("loop_start", (np.arange(len(F)) * 4).astype(np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(F), 4, np.int32))
    me.update(calc_edges=True)
    me.validate()
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    uvl = me.uv_layers.new(name="UVMap")
    uvl.data.foreach_set("uv", UV[lv].astype(np.float32).ravel())
    ca = me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
    ca.data.foreach_set("color", C.astype(np.float32).ravel())
    me.polygons.foreach_set("use_smooth", np.ones(len(F), bool))
    if "TG" in data.files:
        ta = me.attributes.new("strand", 'FLOAT_VECTOR', 'POINT')
        ta.data.foreach_set("vector", data["TG"].astype(np.float32).ravel())
    if "N" in data.files and opts.get("volnormals", "1") == "1":
        # the hair volume's normal on every card vertex: the cards light as one mass instead of as flakes
        me.normals_split_custom_set_from_vertices([tuple(n) for n in data["N"].astype(np.float64)])
    ob = bpy.data.objects.new(stem + "_cards", me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new(stem + "_cards")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(atlas_path)
    tex.image.alpha_mode = 'STRAIGHT'
    tex.interpolation = 'Cubic'
    va = nt.nodes.new('ShaderNodeVertexColor')
    va.layer_name = "Col"
    mul = nt.nodes.new('ShaderNodeMix')
    mul.data_type = 'RGBA'
    mul.blend_type = 'MULTIPLY'
    mul.inputs[0].default_value = 1.0
    nt.links.new(tex.outputs[0], mul.inputs[6])
    nt.links.new(va.outputs[0], mul.inputs[7])
    nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
    # alpha: a slightly denser core, crisp-ish edges (dithered = hashed in EEVEE)
    pw = nt.nodes.new('ShaderNodeMath')
    pw.operation = 'POWER'
    pw.inputs[1].default_value = 0.8
    pw.use_clamp = True
    nt.links.new(tex.outputs[1], pw.inputs[0])
    nt.links.new(pw.outputs[0], bsdf.inputs["Alpha"])
    curly = "curly" in os.path.basename(atlas_path)
    bsdf.inputs["Roughness"].default_value = float(opts.get("rough", 0.45 if curly else 0.36))
    if "Specular Tint" in bsdf.inputs:
        # dark hair: the secondary (coloured) highlight carries the hair's hue; a white sheen reads as grey hair
        bsdf.inputs["Specular Tint"].default_value = (1.0, 0.86, 0.74, 1) if curly else (0.95, 0.92, 0.9, 1)
    npath = atlas_path.replace(".png", "_n.png")
    if os.path.exists(npath) and opts.get("strandnormals", "1") == "1":
        tn = nt.nodes.new('ShaderNodeTexImage')
        tn.image = bpy.data.images.load(npath)
        tn.image.colorspace_settings.name = 'Non-Color'
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.space = 'TANGENT'
        nm.uv_map = "UVMap"
        nm.inputs["Strength"].default_value = float(opts.get("nstr", 0.8))
        nt.links.new(tn.outputs[0], nm.inputs["Color"])
        nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    if "Specular IOR Level" in bsdf.inputs:
        lay = nt.nodes.new('ShaderNodeMath')
        lay.operation = 'MULTIPLY_ADD'          # spec * (0.2 + 0.8 * layer^2)
        sq = nt.nodes.new('ShaderNodeMath')
        sq.operation = 'POWER'
        sq.inputs[1].default_value = 2.0
        nt.links.new(va.outputs[1], sq.inputs[0])
        nt.links.new(sq.outputs[0], lay.inputs[0])
        lay.inputs[1].default_value = 0.8
        lay.inputs[2].default_value = 0.2
        spm = nt.nodes.new('ShaderNodeMath')
        spm.operation = 'MULTIPLY'
        spm.inputs[1].default_value = float(opts.get("spec", 0.16))
        nt.links.new(lay.outputs[0], spm.inputs[0])
        nt.links.new(spm.outputs[0], bsdf.inputs["Specular IOR Level"])
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = 1.55
    # strands: anisotropic highlight stretched across them (tangent = the card's width direction, UV u)
    if "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value = 0.75
        tg = nt.nodes.new('ShaderNodeTangent')
        tg.direction_type = 'UV_MAP'
        tg.uv_map = "UVMap"
        nt.links.new(tg.outputs[0], bsdf.inputs["Tangent"])
    if opts.get("bsdf", "kk") == "kk" and "TG" in data.files:
        # an EEVEE stand-in for the game's strand shader (hair_common.gdshaderinc: Kajiya-Kay, two shifted lobes,
        # no Fresnel). EEVEE has no anisotropic specular, so each glossy lobe gets the normal that a strand
        # (a thin cylinder along T) would turn towards the key light's half vector: N = normalize(H - T (T.H)).
        # Its GGX peak is then at T perpendicular to H: the highlight becomes a band across the strands, broken
        # per strand by a shift read from the atlas (as in hair_common's shifted lobes). The other lights get the
        # same normals (an approximation; they are weaker).
        out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
        NodeSocket = bpy.types.NodeSocket

        def vm(op, a=None, b=None, scale=None):
            n_ = nt.nodes.new('ShaderNodeVectorMath')
            n_.operation = op
            for i_, x in enumerate((a, b)):
                if x is None:
                    continue
                if isinstance(x, NodeSocket):
                    nt.links.new(x, n_.inputs[i_])
                else:
                    n_.inputs[i_].default_value = x
            if scale is not None:
                if isinstance(scale, NodeSocket):
                    nt.links.new(scale, n_.inputs["Scale"])
                else:
                    n_.inputs["Scale"].default_value = scale
            return n_

        def math(op, a, b=None, c=None):
            n_ = nt.nodes.new('ShaderNodeMath')
            n_.operation = op
            for i_, x in enumerate((a, b, c)):
                if x is None:
                    continue
                if isinstance(x, NodeSocket):
                    nt.links.new(x, n_.inputs[i_])
                else:
                    n_.inputs[i_].default_value = x
            return n_.outputs[0]

        geo = nt.nodes.new('ShaderNodeNewGeometry')
        at = nt.nodes.new('ShaderNodeAttribute')
        at.attribute_type = 'GEOMETRY'
        at.attribute_name = "strand"
        T = vm('NORMALIZE', at.outputs["Vector"]).outputs[0]
        Nv = geo.outputs["Normal"]
        H = vm('NORMALIZE', vm('ADD', KEY_DIR, geo.outputs["Incoming"]).outputs[0]).outputs[0]
        # per-strand shift noise from the atlas's normal map (red: each strand's random tilt round its axis)
        nimg = bpy.data.images.load(atlas_path.replace(".png", "_n.png"), check_existing=True)
        nimg.colorspace_settings.name = 'Non-Color'
        tn2 = nt.nodes.new('ShaderNodeTexImage')
        tn2.image = nimg
        sepn = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(tn2.outputs[0], sepn.inputs[0])
        noise = math('SUBTRACT', sepn.outputs[0], 0.5)

        def kk_normal(shift):
            sh = math('MULTIPLY_ADD', noise, float(opts.get("kknoise", 0.9)), shift)
            T1 = vm('NORMALIZE', vm('ADD', T, vm('SCALE', Nv, scale=sh).outputs[0]).outputs[0]).outputs[0]
            d_ = vm('DOT_PRODUCT', T1, H).outputs["Value"]
            Hp = vm('SUBTRACT', H, vm('SCALE', T1, scale=d_).outputs[0]).outputs[0]
            return vm('NORMALIZE', Hp).outputs[0]

        # strand T runs root -> tip; hair_common shifts lobe 1 towards the tip side (-0.07) and lobe 2 (+0.12)
        g1 = nt.nodes.new('ShaderNodeBsdfGlossy')
        g1.inputs["Roughness"].default_value = float(opts.get("r1", 0.22))
        nt.links.new(kk_normal(-0.07), g1.inputs["Normal"])
        g2 = nt.nodes.new('ShaderNodeBsdfGlossy')
        g2.inputs["Roughness"].default_value = float(opts.get("r2", 0.45))
        nt.links.new(kk_normal(0.12), g2.inputs["Normal"])
        tint = (1.0, 0.9, 0.8) if curly else (0.95, 0.96, 1.0)
        sv = float(opts.get("spec1", 0.007 if curly else 0.014))
        c1 = nt.nodes.new('ShaderNodeMix')
        c1.data_type = 'RGBA'
        c1.blend_type = 'MULTIPLY'
        c1.inputs[0].default_value = 1.0
        c1.inputs[6].default_value = (tint[0] * sv, tint[1] * sv, tint[2] * sv, 1)
        nt.links.new(lay.outputs[0], c1.inputs[7])
        # the white lobe only on the strands themselves (atlas brightness squared): the sheen breaks into strands
        sept = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(tex.outputs[0], sept.inputs[0])
        tsq = math('POWER', sept.outputs[0], 2.5)
        c1b = nt.nodes.new('ShaderNodeMix')
        c1b.data_type = 'RGBA'
        c1b.blend_type = 'MULTIPLY'
        c1b.inputs[0].default_value = 1.0
        nt.links.new(c1.outputs[2], c1b.inputs[6])
        nt.links.new(tsq, c1b.inputs[7])
        nt.links.new(c1b.outputs[2], g1.inputs["Color"])
        c2 = nt.nodes.new('ShaderNodeMix')
        c2.data_type = 'RGBA'
        c2.blend_type = 'MULTIPLY'
        c2.inputs[0].default_value = 1.0
        nt.links.new(mul.outputs[2], c2.inputs[6])
        s2 = float(opts.get("spec2", 1.7 if curly else 1.5))
        c2.inputs[7].default_value = (s2, s2, s2, 1)
        nt.links.new(c2.outputs[2], g2.inputs["Color"])
        dif = nt.nodes.new('ShaderNodeBsdfDiffuse')
        nt.links.new(mul.outputs[2], dif.inputs["Color"])
        if bsdf.inputs["Normal"].links:
            nt.links.new(bsdf.inputs["Normal"].links[0].from_socket, dif.inputs["Normal"])
        a1 = nt.nodes.new('ShaderNodeAddShader')
        nt.links.new(dif.outputs[0], a1.inputs[0])
        nt.links.new(g1.outputs[0], a1.inputs[1])
        a2 = nt.nodes.new('ShaderNodeAddShader')
        nt.links.new(a1.outputs[0], a2.inputs[0])
        nt.links.new(g2.outputs[0], a2.inputs[1])
        tr = nt.nodes.new('ShaderNodeBsdfTransparent')
        mx = nt.nodes.new('ShaderNodeMixShader')
        nt.links.new(pw.outputs[0], mx.inputs[0])
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(a2.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
    elif opts.get("bsdf", "kk") in ("split", "kk"):
        # closer to the game's hair shader (hair_common.gdshaderinc: wrapped diffuse + Kajiya-Kay lobes, no Fresnel)
        # than the Principled BSDF, whose Fresnel turns every grazing card into a white blotch on dark hair:
        # diffuse + a weak, constant-weight glossy lobe (white-ish, narrow) + a broader lobe in the hair's own colour
        out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
        nrm_src = bsdf.inputs["Normal"].links[0].from_socket if bsdf.inputs["Normal"].links else None
        dif = nt.nodes.new('ShaderNodeBsdfDiffuse')
        nt.links.new(mul.outputs[2], dif.inputs["Color"])
        g1 = nt.nodes.new('ShaderNodeBsdfGlossy')
        g1.inputs["Roughness"].default_value = float(opts.get("rough", 0.3 if curly else 0.24))
        g2 = nt.nodes.new('ShaderNodeBsdfGlossy')
        g2.inputs["Roughness"].default_value = 0.55
        tint = (1.0, 0.86, 0.72) if curly else (0.92, 0.94, 1.0)
        # colour of lobe 1: tint * spec * layer factor (inner cards are shadowed by the outer ones)
        k1 = nt.nodes.new('ShaderNodeMix')
        k1.data_type = 'RGBA'
        k1.blend_type = 'MULTIPLY'
        k1.inputs[0].default_value = 1.0
        k1.inputs[6].default_value = (*tint, 1)
        nt.links.new(lay.outputs[0], k1.inputs[7])
        k1b = nt.nodes.new('ShaderNodeMix')
        k1b.data_type = 'RGBA'
        k1b.blend_type = 'MULTIPLY'
        k1b.inputs[0].default_value = 1.0
        nt.links.new(k1.outputs[2], k1b.inputs[6])
        sv = float(opts.get("spec1", 0.05))
        k1b.inputs[7].default_value = (sv, sv, sv, 1)
        nt.links.new(k1b.outputs[2], g1.inputs["Color"])
        # lobe 2: the albedo, boosted (the coloured secondary highlight)
        k2 = nt.nodes.new('ShaderNodeMix')
        k2.data_type = 'RGBA'
        k2.blend_type = 'MULTIPLY'
        k2.inputs[0].default_value = 1.0
        nt.links.new(mul.outputs[2], k2.inputs[6])
        s2 = float(opts.get("spec2", 1.6))
        k2.inputs[7].default_value = (s2, s2, s2, 1)
        nt.links.new(k2.outputs[2], g2.inputs["Color"])
        if nrm_src is not None:
            for n_ in (dif, g1, g2):
                nt.links.new(nrm_src, n_.inputs["Normal"])
        a1 = nt.nodes.new('ShaderNodeAddShader')
        nt.links.new(dif.outputs[0], a1.inputs[0])
        nt.links.new(g1.outputs[0], a1.inputs[1])
        a2 = nt.nodes.new('ShaderNodeAddShader')
        nt.links.new(a1.outputs[0], a2.inputs[0])
        nt.links.new(g2.outputs[0], a2.inputs[1])
        tr = nt.nodes.new('ShaderNodeBsdfTransparent')
        mx = nt.nodes.new('ShaderNodeMixShader')
        nt.links.new(pw.outputs[0], mx.inputs[0])
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(a2.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
    for attr, val in (("surface_render_method", 'DITHERED'), ("use_transparent_shadow", True),
                      ("blend_method", 'HASHED'), ("shadow_method", 'HASHED'), ("use_backface_culling", False)):
        if hasattr(mat, attr):
            try:
                setattr(mat, attr, val)
            except Exception:
                pass
    me.materials.append(mat)
    return ob


def add_cap(stem, data, key="cap", rough=0.8, spec=0.2):
    """A vertex-coloured mesh from the grower (the scalp cap, or the inner occluder): alpha dithered."""
    V, F, C = data[key + "_V"], data[key + "_F"], data[key + "_C"]
    me = bpy.data.meshes.new(stem + "_hair" + key)
    me.from_pydata([tuple(v) for v in V.astype(np.float64)], [], [tuple(f) for f in F.tolist()])
    me.update()
    ca = me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
    ca.data.foreach_set("color", C.astype(np.float32).ravel())
    me.polygons.foreach_set("use_smooth", np.ones(len(F), bool))
    ob = bpy.data.objects.new(stem + "_hair" + key, me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new(stem + "_hair" + key)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    va = nt.nodes.new('ShaderNodeVertexColor')
    va.layer_name = "Col"
    nt.links.new(va.outputs[0], bsdf.inputs["Base Color"])
    nt.links.new(va.outputs[1], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    for attr, val in (("surface_render_method", 'DITHERED'), ("blend_method", 'HASHED'), ("use_transparent_shadow", True)):
        if hasattr(mat, attr):
            try:
                setattr(mat, attr, val)
            except Exception:
                pass
    me.materials.append(mat)
    return ob


def darken_shell(data, mode):
    sh = shell_object()
    if sh is None:
        return
    if mode == "off":
        sh.hide_render = True
        return
    if mode == "keep":
        return
    me = sh.data
    inv = sh.matrix_world.inverted()
    kd = KDTree(len(data["shell_P"]))
    for i, p in enumerate(data["shell_P"]):
        kd.insert(Vector(p), i)
    kd.balance()
    off = data["shell_off"]
    mw = sh.matrix_world
    edge = data["shell_edge"] if "shell_edge" in data.files else None
    fade = np.ones(len(me.vertices), np.float32)
    for v in me.vertices:
        p = mw @ v.co
        _, i, d = kd.find(p)
        if d < 1e-4:
            v.co = inv @ (p + Vector(off[i]))
            if edge is not None:
                fade[v.index] = min(1.0, max(0.0, (float(edge[i]) - 0.002) / 0.015))
    me.update()
    ca = me.color_attributes.new("fade", 'FLOAT_COLOR', 'POINT')
    ca.data.foreach_set("color", np.repeat(fade[:, None], 4, 1).ravel())
    for slot in sh.material_slots:
        m = slot.material
        if not m or not m.use_nodes:
            continue
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
        link = bsdf.inputs["Base Color"].links[0] if bsdf.inputs["Base Color"].links else None
        mul = nt.nodes.new('ShaderNodeMix')
        mul.data_type = 'RGBA'
        mul.blend_type = 'MULTIPLY'
        mul.inputs[0].default_value = 1.0
        mul.inputs[7].default_value = (0.55, 0.55, 0.55, 1)
        if link:
            nt.links.new(link.from_socket, mul.inputs[6])
        nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.85
        fa = nt.nodes.new('ShaderNodeVertexColor')
        fa.layer_name = "fade"
        nt.links.new(fa.outputs[0], bsdf.inputs["Alpha"])
        for attr, val in (("surface_render_method", 'DITHERED'), ("use_transparent_shadow", True)):
            if hasattr(m, attr):
                setattr(m, attr, val)
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.25
        # the shell is only an occluder now: its baked normal map would just add noise
        if bsdf.inputs["Normal"].links:
            nt.links.remove(bsdf.inputs["Normal"].links[0])


def render_views(scene, cam, stem, head_c, z_eye, long_hair, prefix, outdir):
    cid = IDS.get(stem, stem)
    tgt_face = (0.0, head_c[1], z_eye + 0.01)
    shots = {
        "front": (tgt_face if not long_hair else (0.0, head_c[1], z_eye - 0.05), 0, 0.95 if not long_hair else 1.25, 0.0),
        "34": (tgt_face if not long_hair else (0.0, head_c[1], z_eye - 0.05), -40, 0.95 if not long_hair else 1.25, 0.02),
        "side": ((0.0, head_c[1] + 0.02, z_eye - (0.0 if not long_hair else 0.1)), 90, 1.0 if not long_hair else 1.45, 0.02),
        "back": ((0.0, head_c[1] + 0.02, z_eye - (0.0 if not long_hair else 0.14)), 180, 1.05 if not long_hair else 1.7, 0.06),
    }
    paths = []
    for v in VIEWS:
        tgt, yaw, dist, dz = shots[v]
        frame(cam, tgt, yaw, dist, dz)
        path = os.path.join(outdir, f"{prefix}{cid}_{v}{TAG}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        paths.append(path)
        print("[A] wrote", path, flush=True)
    return paths


for stem in stems:
    data = np.load(os.path.join(OUTA, f"{stem}_cards.npz"))
    arm = import_char(stem)
    head = data["head"]
    z_eye = float(data["z_eye"])
    long_hair = str(data["atlas"]) == "straight"
    head_c = (0.0, float(head[1]), z_eye + 0.02)
    scene, cam = setup_scene(head_c, 0.4)
    if opts.get("base") == "1":
        render_views(scene, cam, stem, head_c, z_eye, long_hair, "base_", OUTA)
    darken_shell(data, opts.get("shell", "off"))
    if "cap_V" in data.files and opts.get("cap", "1") == "1":
        add_cap(stem, data)
    if "occ_V" in data.files and opts.get("occ", "1") == "1":
        add_cap(stem, data, "occ", rough=0.9, spec=0.1)
    atlas = os.path.join(OUTA, f"strands_{str(data['atlas'])}.png")
    cards = add_cards(stem, data, atlas)
    print(f"[A] {stem}: cards {len(data['F'])} quads, {len(data['V'])} verts", flush=True)
    outdir = os.path.join(OUTA, "tests") if opts.get("test") == "1" else REVIEW
    os.makedirs(outdir, exist_ok=True)
    render_views(scene, cam, stem, head_c, z_eye, long_hair, "hair_proto_A_", outdir)
    if opts.get("blend") == "1":
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUTA, f"{stem}_proto.blend"))
