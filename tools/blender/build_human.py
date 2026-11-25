"""Build game characters with MPFB (MakeHuman for Blender) and export them as .glb for Godot.

Run:  Blender -b -P tools/blender/build_human.py -- mano[:street] ian ... [--preview] [--no-photo] [--keep]
                                                    [--hair=scan|scan_cards] [--out=<dir>]
--hair overrides a scanned outfit's "hair" for this build (A/B of the scan's hair shell against the strand cards
laid over it, hair_scan_cards.py) without editing cast.py.
Each character gets the MPFB "game_engine" skeleton, ARKit face shapes (blink, visemes, smiles),
MakeHuman clothes refitted to its body (or, for an outfit with a "scan", its body wrapped onto a 3D scan
of the real outfit: scan_wrap.py), a photo-projected face (face_fit.py) and simple PBR materials
the glTF exporter understands. Output: assets/characters/<id>[_<outfit>].glb (+ tools/out previews).
"""
import bpy, bmesh, sys, os, math, importlib, json, time, copy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import cast
importlib.reload(cast)

from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService
from bl_ext.user_default.mpfb.services.faceservice import FaceService
from bl_ext.user_default.mpfb.services.exportservice import ExportService
from bl_ext.user_default.mpfb.services.assetservice import AssetService

OUT = os.path.join(ROOT, "assets", "characters")
PREVIEW = os.path.join(ROOT, "tools", "out")
os.makedirs(OUT, exist_ok=True)
os.makedirs(PREVIEW, exist_ok=True)


def log(*a):
    print("[human]", *a, flush=True)


# ------------------------------------------------------------------ build
def human_info(spec, outfit, height=None):
    info = HumanService._create_default_human_info_dict()
    macro = dict(cast.HumanDefaults) if hasattr(cast, "HumanDefaults") else {}
    phen = {"gender": 0.5, "age": 0.5, "muscle": 0.5, "weight": 0.5, "proportions": 0.5, "height": 0.5,
            "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.33, "caucasian": 0.33, "african": 0.33}}
    phen.update(spec["macro"])
    if height is not None:
        phen["height"] = height
    info["phenotype"] = phen
    info["rig"] = "game_engine"
    info.update(cast.BASE)
    if spec.get("brows"):
        info["eyebrows"] = spec["brows"]
    info["hair"] = (spec.get("hair") or "") if not spec.get("hair_style") else ""
    clothes = [c for c, _ in spec["outfits"][outfit]["clothes"]]
    if spec.get("glasses"):
        clothes.append(spec["glasses"]["asset"])
    info["clothes"] = clothes
    info["targets"] = [{"target": k, "value": v} for k, v in spec.get("targets", {}).items()]
    info["skin_mhmat"] = spec["skin"]
    info["skin_material_type"] = "MAKESKIN"
    info["eyes_material_type"] = "MAKESKIN"
    return info


def build(cid, outfit, photo=True, preview=False, anim=True, hair=None):
    t0 = time.time()
    spec = cast.CAST[cid]
    if hair and spec["outfits"][outfit].get("scan"):
        spec = copy.deepcopy(spec)
        spec["outfits"][outfit]["hair"] = hair
    settings = HumanService.get_default_deserialization_settings()
    settings["subdiv_levels"] = 0

    def make_human(height=None):
        bpy.ops.wm.read_homefile(use_empty=True)
        body = HumanService.deserialize_from_dict(human_info(spec, outfit, height), settings)
        TargetService.bake_targets(body)
        return body

    scanned = bool(spec["outfits"][outfit].get("scan"))
    if scanned:
        import scan_wrap
        importlib.reload(scan_wrap)
    # a scanned outfit keeps the cast's height: scan_wrap fits the scan's head to the body (fit_scan_head)
    basemesh = make_human()
    rig = basemesh.parent
    rig.name = cid
    log(cid, outfit, "created", round(time.time() - t0, 1), "s")

    if photo and spec.get("photo"):
        import face_fit
        importlib.reload(face_fit)
        face_fit.apply(basemesh, rig, spec, cid, ROOT)
        if not scanned and spec.get("photo_finish"):
            # (cast "photo_finish", off by default) face_finish's geometry keys (widen) on an
            # unscanned build, after the photo fit
            import face_finish
            importlib.reload(face_finish)
            face_finish.apply(basemesh, rig, spec["photo_finish"], cid, ROOT)
        if not scanned and (spec.get("glasses") or {}).get("lens_fit"):
            # (cast glasses "lens_fit", off by default) glasses_seat's "lens" / "seat" on an unscanned build
            import glasses_seat
            importlib.reload(glasses_seat)
            glasses_seat.apply(basemesh, rig, 0.0, opts=spec["glasses"]["lens_fit"])
    if scanned:
        scan_wrap.apply(basemesh, rig, spec, outfit, cid, ROOT)
        if spec.get("face_finish"):
            # (cast "face_finish", off by default) per-person touches on the fitted face (face_finish.py)
            import face_finish
            importlib.reload(face_finish)
            face_finish.apply(basemesh, rig, spec["face_finish"], cid, ROOT)
        if (spec.get("glasses") or {}).get("clear"):
            # (cast glasses "clear", off by default) the frame moved forward off the fitted face (glasses_seat.py)
            import glasses_seat
            importlib.reload(glasses_seat)
            # (its "lens" and "seat" keys reshape the front by the eyes and seat it by rays: glasses_seat.shape)
            glasses_seat.apply(basemesh, rig, float(spec["glasses"]["clear"]), opts=spec["glasses"])
    if not scanned and spec.get("hair_stretch"):
        # (cast "hair_stretch", off by default) a MakeHuman hair asset made longer (mh_hair.py)
        import mh_hair
        importlib.reload(mh_hair)
        mh_hair.apply(basemesh, rig, spec)
    hair_mode = spec["outfits"][outfit].get("hair")
    scan_cards = None
    if scanned and hair_mode == "scan_cards":
        # strand cards laid over the scan's hair shell (the shell becomes their dark underlayer) and a scalp cap
        import hair_scan_cards
        importlib.reload(hair_scan_cards)
        scan_cards = hair_scan_cards.make(basemesh, rig, spec, outfit, cid, ROOT)
    # a scanned outfit can keep the scan's own sculpted hair (as a shell, or under cards) instead of generated cards
    if spec.get("hair_style") and hair_mode not in ("scan", "scan_cards"):
        import hair_gen
        importlib.reload(hair_gen)
        skip = ("shoe", "sneaker", "boot", "flat", "glasses", "high-poly", "eyebrow", "eyelash", "teeth", "tongue")
        colliders = [o for o in rig.children if o.type == 'MESH' and o != basemesh and not any(k in o.name.lower() for k in skip)]
        hair = hair_gen.make_hair(basemesh, rig, spec["hair_style"], spec["hair_colors"], f"{cid}.hairgen", ROOT,
                                  seed=spec.get("hair_seed", abs(hash(cid)) % 1000), extra_colliders=colliders,
                                  density=0.6 if spec.get("tier") == "npc" else 1.0, style_over=spec.get("hair_gen"))
        hair["baked_color"] = True
    FaceService.load_targets(basemesh, load_microsoft_visemes=False, load_arkit_faceunits=True)
    FaceService.interpolate_targets(basemesh)
    if scanned:
        scan_wrap.scale_shapes(basemesh, rig)
    if scan_cards:
        # the scalp cap follows the forehead when the brows move (before the helpers go: same vertex ids)
        hair_scan_cards.cap_shapes(basemesh, scan_cards)
    ExportService.bake_modifiers_remove_helpers(basemesh, bake_masks=True, bake_subdiv=False, remove_helpers=True)

    finish_meshes(rig, basemesh, spec, outfit, cid)
    if scanned:
        scan_wrap.split_materials(basemesh, cid)
    cull_hidden(rig, basemesh)
    height = max((basemesh.matrix_world @ v.co).z for v in basemesh.data.vertices)
    log(cid, "height", round(height, 3), "m")

    if anim and os.path.exists(os.path.join(HERE, "retarget.py")):
        import retarget
        importlib.reload(retarget)
        retarget.apply(rig, verbose=False)
        log(cid, "animations", len(bpy.data.actions))

    name = cid if outfit in ("default",) else f"{cid}_{outfit}"
    path = os.path.join(OUT, name + ".glb")
    export(rig, path)
    if preview:
        render_preview(rig, basemesh, os.path.join(PREVIEW, name))
    log(cid, outfit, "done in", round(time.time() - t0, 1), "s ->", os.path.relpath(path, ROOT))
    return path


# ------------------------------------------------------------------ meshes and materials
def split_cornea(obj, cid):
    """MakeHuman eyes map the cornea onto a corner of the eye texture; give it its own glossy see-through mesh."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv = bm.loops.layers.uv.active
    corner = [f for f in bm.faces if all(l[uv].uv.x > 0.85 and l[uv].uv.y < 0.15 for l in f.loops)]
    bm.free()
    if not corner:
        return None
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    me = obj.data
    uvl = me.uv_layers.active.data
    for p in me.polygons:
        p.select = all(uvl[li].uv.x > 0.85 and uvl[li].uv.y < 0.15 for li in p.loop_indices)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='SELECTED')
    bpy.ops.object.mode_set(mode='OBJECT')
    new = [o for o in bpy.context.selected_objects if o != obj][0]
    new.name = f"{cid}_cornea_eye"
    new["kind"] = "cornea"
    return new


LAYER_WORDS = [  # (layer, keywords): higher layers hide what is under them
    (3, ("jacket", "hood", "cardigan", "coat")),
    (2, ("sweater", "shirt", "top", "tee", "polo", "blouse", "lusekofta", "tank", "suit")),
    (1, ("jeans", "trouser", "pants", "cargo", "shorts")),
    (1, ("shoe", "sneaker", "flat", "boot", "sandal")),
]


def garment_layer(obj):
    if obj.get("kind") != "cloth":
        return None
    n = obj.name.lower()
    for layer, words in LAYER_WORDS:
        if any(w in n for w in words):
            return layer
    return None


def cull_hidden(rig, basemesh):
    """Delete faces of the body and inner garments that sit under an outer garment (no poke-through, fewer tris)."""
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    garments = [(garment_layer(o), o) for o in rig.children if o.type == 'MESH' and o != basemesh]
    garments = [(l, o) for l, o in garments if l is not None]
    targets = [(0, basemesh)] + [(l, o) for l, o in garments if l < 3]
    for layer, obj in targets:
        outers = [o for l, o in garments if l > layer]
        if not outers:
            continue
        trees = [BVHTree.FromObject(o, dg) for o in outers]
        mw = obj.matrix_world
        me = obj.data
        covered = []
        for v in me.vertices:
            p = mw @ v.co
            nrm = (mw.to_3x3() @ v.normal).normalized()
            hit = False
            for t in trees:
                # an outer surface just outside along the normal, and one behind is not needed
                loc, n, i, d = t.ray_cast(p - nrm * 0.002, nrm, 0.045)
                if loc is not None:
                    hit = True
                    break
            covered.append(hit)
        body_keep = set()
        if obj == basemesh:
            # never cut the head, hands, or anything with face shapes
            for g in ("head", "neck_01", "hand_l", "hand_r"):
                vg = obj.vertex_groups.get(g)
                if vg:
                    for v in me.vertices:
                        for ge in v.groups:
                            if ge.group == vg.index and ge.weight > 0.2:
                                body_keep.add(v.index)
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        kill = [f for f in bm.faces if all(covered[v.index] and v.index not in body_keep for v in f.verts)]
        if kill:
            bmesh.ops.delete(bm, geom=kill, context='FACES_ONLY')
            loose = [v for v in bm.verts if not v.link_faces]
            bmesh.ops.delete(bm, geom=loose, context='VERTS')
            bm.to_mesh(me)
        bm.free()
        log("cull", obj.name, "removed", len(kill), "faces")


def finish_meshes(rig, basemesh, spec, outfit, cid):
    tints = {os.path.basename(c).replace(".mhclo", ""): t for c, t in spec["outfits"][outfit]["clothes"]}
    for obj in [o for o in rig.children if o.type == 'MESH']:
        if obj.name.split(".", 1)[-1] in ("high-poly", "low-poly"):
            split_cornea(obj, cid)
    for obj in [o for o in rig.children if o.type == 'MESH']:
        if obj.get("kind") == "cornea":
            continue
        key = obj.name.split(".", 1)[-1] if "." in obj.name else obj.name
        kind = classify(obj, basemesh, key, spec)
        obj["kind"] = kind
        # very low-poly clothes come with normal maps that expect subdivision
        if kind == "cloth" and len(obj.data.vertices) < 4000:
            subdivide(obj, 2 if len(obj.data.vertices) < 1200 else 1)
        rebuild_material(obj, kind, tints.get(key), spec, cid)
        for p in obj.data.polygons:
            p.use_smooth = True
        obj.name = f"{cid}_{kind}_{key}"[:60]
    basemesh.name = f"{cid}_body"


def classify(obj, basemesh, key, spec):
    if obj == basemesh:
        return "skin"
    if "eyebrow" in key:
        return "brow"
    if "eyelash" in key:
        return "lash"
    if key in ("high-poly", "low-poly"):
        return "eye"
    if "teeth" in key:
        return "teeth"
    if "tongue" in key:
        return "tongue"
    if key.endswith("haircap"):
        return "haircap"
    if key.endswith("scancards"):
        return "hair"
    if key.endswith("hairunder"):
        return "hairunder"
    if key.endswith("scanhair"):
        return "hairshell"
    if (spec.get("hair") and key in spec["hair"]) or key.endswith("hairgen"):
        return "hair"
    if "glasses" in key:
        return "glasses"
    return "cloth"


def subdivide(obj, levels):
    if obj.data.shape_keys:
        if len(obj.data.shape_keys.key_blocks) > 1:
            return
        obj.shape_key_clear()
    m = obj.modifiers.new("Subsurf", 'SUBSURF')
    m.levels = levels
    m.render_levels = levels
    m.quality = 3
    bpy.context.view_layer.objects.active = obj
    # the armature modifier must stay last so the subdivided mesh keeps its weights
    while obj.modifiers[0].name != "Subsurf":
        bpy.ops.object.modifier_move_up(modifier="Subsurf")
    bpy.ops.object.modifier_apply(modifier="Subsurf")


def find_images(mat):
    """Return (diffuse, normal) images from an MPFB/MakeSkin node tree."""
    diffuse = normal = None
    if not mat or not mat.node_tree:
        return None, None
    for n in mat.node_tree.nodes:
        if n.type != 'TEX_IMAGE' or not n.image:
            continue
        linked_to = [l.to_node for o in n.outputs for l in o.links]
        if any(t.type == 'NORMAL_MAP' for t in linked_to):
            normal = n.image
        elif any(t.type == 'BUMP' for t in linked_to) and diffuse is not None:
            continue
        elif diffuse is None:
            diffuse = n.image
    return diffuse, normal


def recoloured(img, col):
    """New image: tint * (luminance / mean luminance), alpha kept. Works on any source colour."""
    import numpy as np
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    lum = px[:, :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    a = px[:, 3] > 0.5
    mean = float(np.median(lum[a])) if a.any() else float(lum.mean())
    rel = np.clip(lum / max(mean, 1e-4), 0, 3)
    # soften extreme contrast from baked shading, keep weave detail
    rel = 1.0 + (rel - 1.0) * 0.8
    out = np.empty_like(px)
    out[:, :3] = np.clip(rel[:, None] * np.array(col, np.float32)[None, :], 0, 1)
    out[:, 3] = px[:, 3]
    new = bpy.data.images.new(img.name + "_rc", w, h, alpha=True)
    new.colorspace_settings.name = 'sRGB'
    # Blender image pixels are linear for float buffers but this is a byte image: write sRGB-encoded values
    srgb = np.where(out[:, :3] <= 0.0031308, out[:, :3] * 12.92, 1.055 * np.power(np.maximum(out[:, :3], 0), 1 / 2.4) - 0.055)
    out[:, :3] = srgb
    new.pixels.foreach_set(out.ravel())
    new.pack()
    return new


def recolor_iris(img, col):
    """MakeHuman's eye texture has a saturated red-brown iris that renders orange: give the iris the person's
    colour (cast eye_color, linear), keeping its fibres and the pupil; the sclera stays as it is."""
    import numpy as np
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    rgb = px[:, :3]
    mx, mn = rgb.max(1), rgb.min(1)
    sat = (mx - mn) / np.maximum(mx, 1e-4)
    iris = np.clip((sat - 0.25) / 0.2, 0, 1) * (rgb[:, 0] > rgb[:, 2] * 1.1)
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    ref = float(np.median(lum[iris > 0.9])) if (iris > 0.9).any() else float(lum.mean())
    # a little brighter than the photo-measured colour: those are taken in the shade of the brow
    target = np.clip(np.array(col, np.float32)[None, :] * 1.8 * (lum / max(ref, 1e-4))[:, None], 0, 1)
    srgb = np.where(target <= 0.0031308, target * 12.92, 1.055 * np.power(target, 1 / 2.4) - 0.055)
    out = px.copy()
    out[:, :3] = rgb * (1 - iris[:, None]) + srgb * iris[:, None]
    new = bpy.data.images.new(img.name + "_iris", w, h, alpha=True)
    new.pixels.foreach_set(out.ravel())
    new.pack()
    return new


def rebuild_material(obj, kind, tint, spec, cid):
    old = obj.active_material
    if kind in ("haircap", "hairunder") or obj.get("keep_material"):
        # keep their own material: the cap's vertex colour and mask, the underlayer's baked colour, and the scan
        # cards' image x "Col" colour attribute (so the glTF exporter writes COLOR_0 from it)
        return
    diffuse, normal = find_images(old)
    if kind == "eye" and diffuse is not None and spec.get("eye_color"):
        diffuse = recolor_iris(diffuse, cast.hx(spec["eye_color"]))
    if kind == "glasses":
        tint = spec.get("glasses", {}).get("frame") if diffuse is not None else None
    mat = bpy.data.materials.new(f"{cid}_{kind}_{obj.name.split('.')[-1]}"[:60])
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Roughness"].default_value = {"skin": 0.55, "hair": 0.45, "hairshell": 0.5, "eye": 0.05, "teeth": 0.25,
                                             "tongue": 0.35, "glasses": 0.25, "brow": 0.8, "lash": 0.8}.get(kind, 0.85)
    if diffuse is not None:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = diffuse
        if tint is not None or (kind == "hair" and spec.get("hair_tint") and not obj.get("baked_color")):
            col = tint if tint is not None else spec["hair_tint"]
            if kind in ("cloth", "hair", "glasses"):
                # recolour: keep the texture's shading/weave (luminance) but replace its hue with the tint
                diffuse = recoloured(diffuse, col)
                tex.image = diffuse
                nt.links.new(tex.outputs[0], bsdf.inputs["Base Color"])
            else:
                mix = nt.nodes.new('ShaderNodeMix')
                mix.data_type = 'RGBA'
                mix.blend_type = 'MULTIPLY'
                mix.inputs[0].default_value = 1.0
                nt.links.new(tex.outputs[0], mix.inputs[6])
                mix.inputs[7].default_value = (*col, 1.0)
                nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(tex.outputs[0], bsdf.inputs["Base Color"])
        if kind in ("hair", "brow", "lash"):
            # alpha-tested cards; Godot swaps in an alpha-hash + anti-aliased hair shader
            rnd = nt.nodes.new('ShaderNodeMath')
            rnd.operation = 'ROUND'
            nt.links.new(tex.outputs[1], rnd.inputs[0])
            nt.links.new(rnd.outputs[0], bsdf.inputs["Alpha"])
    if diffuse is None and kind == "glasses":
        g = spec.get("glasses", {})
        bsdf.inputs["Base Color"].default_value = (*g.get("frame", (0.6, 0.6, 0.6)), 1.0)
        bsdf.inputs["Metallic"].default_value = g.get("metal", 0.8)
    if normal is not None and kind != "glasses":
        nt_ = nt.nodes.new('ShaderNodeTexImage')
        nt_.image = normal
        normal.colorspace_settings.name = 'Non-Color'
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nt.links.new(nt_.outputs[0], nm.inputs[1])
        nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)


# ------------------------------------------------------------------ export
def export(rig, path):
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    for c in rig.children:
        # MPFB parents bone-shape helpers (Cube, Icosphere) to the rig; only skinned meshes ship
        if c.type == 'MESH' and any(m.type == 'ARMATURE' for m in c.modifiers):
            c.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', use_selection=True, export_apply=False,
        export_skins=True, export_morph=True, export_morph_normal=False, export_try_sparse_sk=True,
        export_animations=bool(bpy.data.actions), export_animation_mode='ACTIONS', export_force_sampling=True,
        export_def_bones=True, export_leaf_bone=False, export_yup=True, export_extras=True,
        export_image_format='AUTO', export_tangents=False)


# ------------------------------------------------------------------ preview render
def render_preview(rig, basemesh, stem):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if hasattr(bpy.types, 'EEVEE_NEXT') or bpy.app.version >= (4, 2, 0) else 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = 900, 1200
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.32, 0.34, 0.38, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    scene.world = world
    for name, loc, energy, size in (("key", (1.6, -2.4, 2.4), 450, 1.5), ("fill", (-2.2, -1.8, 1.4), 160, 2.5), ("rim", (0.5, 2.6, 2.2), 300, 1.0)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        bpy.context.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0, 0, 1.2)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    height = max((basemesh.matrix_world @ v.co).z for v in basemesh.data.vertices)
    cam_d = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_d)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    for tag, loc, target, lens in (("full", (0.9, -4.2, height * 0.55), (0, 0, height * 0.5), 50),
                                   ("face", (0.25, -0.75, height - 0.1), (0, 0, height - 0.11), 85)):
        cam.location = loc
        cam_d.lens = lens
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = f"{stem}_{tag}.png"
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    flags = {a for a in argv if a.startswith("--")}
    hair = next((a.split("=", 1)[1] for a in flags if a.startswith("--hair=")), None)
    out_dir = next((a.split("=", 1)[1] for a in flags if a.startswith("--out=")), None)
    if out_dir:
        # (--out=<dir>: a test build written there instead of assets/characters; the shipped glb is left alone)
        OUT = os.path.abspath(out_dir)
        os.makedirs(OUT, exist_ok=True)
    targets = [a for a in argv if not a.startswith("--")] or ["mano"]
    for t in targets:
        cid, _, outfit = t.partition(":")
        outfits = [outfit] if outfit else list(cast.CAST[cid]["outfits"].keys())[:1]
        for o in outfits:
            build(cid, o, photo="--no-photo" not in flags, preview="--preview" in flags, anim="--no-anim" not in flags,
                  hair=hair)
