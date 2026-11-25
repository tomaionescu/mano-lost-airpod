"""One-time calibration: where MediaPipe's 468 face landmarks sit on the MakeHuman base mesh.

Renders a neutral MPFB head straight on (orthographic), runs MediaPipe Face Landmarker on the render,
ray-casts every landmark onto the mesh and stores it as (3 vertex indices, barycentric weights).
MPFB topology is fixed, so the result works for every character.
Run: Blender -b -P tools/blender/face_calib.py
"""
import bpy, os, sys, json, subprocess
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform, intersect_point_tri

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.targetservice import TargetService

OUT_JSON = os.path.join(ROOT, "tools", "models", "mpfb_face_anchors.json")
RENDER = os.path.join(ROOT, "tools", "out", "calib_face.png")
PY = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"


def body_triangles(mesh, body_mask):
    tris = []
    for p in mesh.polygons:
        vs = list(p.vertices)
        if not all(body_mask[v] for v in vs):
            continue
        for k in range(1, len(vs) - 1):
            tris.append((vs[0], vs[k], vs[k + 1]))
    return tris


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    info = HumanService._create_default_human_info_dict()
    info["phenotype"] = {"gender": 0.5, "age": 0.45, "muscle": 0.5, "weight": 0.5, "proportions": 0.5, "height": 0.5,
                         "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.33, "caucasian": 0.34, "african": 0.33}}
    info.update({"eyes": "eyes/high-poly/high-poly.mhclo", "eyebrows": "eyebrows/eyebrow001/eyebrow001.mhclo",
                 "eyelashes": "eyelashes/eyelashes01/eyelashes01.mhclo",
                 "skin_mhmat": "skins/young_caucasian_male/young_caucasian_male.mhmat", "skin_material_type": "MAKESKIN",
                 "eyes_material_type": "MAKESKIN"})
    s = HumanService.get_default_deserialization_settings()
    s["subdiv_levels"] = 0
    bm = HumanService.deserialize_from_dict(info, s)
    TargetService.bake_targets(bm)
    mesh = bm.data
    body_group = bm.vertex_groups["body"].index
    body_mask = [any(g.group == body_group and g.weight > 0.5 for g in v.groups) for v in mesh.vertices]
    verts = [bm.matrix_world @ v.co for v in mesh.vertices]
    head_top = max(v.z for i, v in enumerate(verts) if body_mask[i])
    center_z = head_top - 0.115

    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    res = 1024
    scene.render.resolution_x = scene.render.resolution_y = res
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.55, 0.55, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    scene.world = w
    for name, loc, e in (("k", (0.6, -1.5, center_z + 0.4), 120), ("f", (-0.6, -1.5, center_z + 0.2), 90)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = e
        ld.size = 1.5
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        bpy.context.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0, 0, center_z)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cd = bpy.data.cameras.new("c")
    cd.type = 'ORTHO'
    ortho = 0.30
    cd.ortho_scale = ortho
    cam = bpy.data.objects.new("c", cd)
    bpy.context.collection.objects.link(cam)
    cam.location = (0.0, -1.0, center_z)
    cam.rotation_euler = (1.5707963, 0.0, 0.0)
    scene.camera = cam
    scene.render.filepath = RENDER
    bpy.ops.render.render(write_still=True)

    subprocess.run([PY, os.path.join(ROOT, "tools", "py", "landmarks.py"), RENDER], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lm = json.load(open(RENDER + ".lm.json"))
    pts = lm["faces"][0]["pts"]

    tris = body_triangles(mesh, body_mask)
    bvh = BVHTree.FromPolygons([tuple(v) for v in verts], tris)
    anchors = []
    for i, (u, v, _) in enumerate(pts[:468]):
        x = cam.location.x + (u / res - 0.5) * ortho
        z = cam.location.z - (v / res - 0.5) * ortho
        hit, normal, fi, dist = bvh.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)), 3.0)
        if hit is None:
            anchors.append(None)
            continue
        a, b, c = tris[fi]
        A, B, C = verts[a], verts[b], verts[c]
        # barycentric weights of the hit inside triangle ABC
        v0, v1, v2 = B - A, C - A, hit - A
        d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
        d20, d21 = v2.dot(v0), v2.dot(v1)
        den = d00 * d11 - d01 * d01
        wb = (d11 * d20 - d01 * d21) / den
        wc = (d00 * d21 - d01 * d20) / den
        anchors.append({"v": [a, b, c], "w": [1 - wb - wc, wb, wc]})
    json.dump({"anchors": anchors, "render": os.path.basename(RENDER)}, open(OUT_JSON, "w"))
    print("[calib] anchors", sum(1 for a in anchors if a), "of", len(anchors), "->", OUT_JSON)


main()
