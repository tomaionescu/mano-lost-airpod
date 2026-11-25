"""Dress an MPFB character in a 3D scan of the person in their own outfit, keeping its rig and ARKit face shapes
(called by build_human.py for outfits with a "scan").

The scan (tools/scans/<id>/*.glb: Tripo via Higgsfield, from a full-body reference of the person) is one
textured shell of clothes, shoes, hair and skin, with no face rig and fused fingers. So the character's own
body mesh is wrapped onto it instead:

1. normalise the scan: upright, facing -Y, soles on the floor, eyes at the character's eye height. The front is
   the side where the face landmarker finds a face; its landmarks, cast onto the scan, are the face's 3D points.
   With a "head_scan" (splice_head), a separate scan of the head replaces the scan's head first: placed by its
   face landmarks and turned straight ahead, decimated (a full-resolution copy kept beside it, moved and cut the same
   way, is what the bakes read: bake_source), cut in under the jaw (its hood dropped, its hood-hidden neck toned and
   cleaned in its own texture to meet the body scan's, the body scan's hood behind the neck darkened like the hair);
   its face landmarks are found again, so its face is the one used, fit_head then moves the whole head onto it as one
   smooth field, flatten_ears turns the template's ears in towards the scan's and tuck_skull holds the template's
   skull under the scan's hair down to an adult skull's size (fit_hair then moves the hair out over it, and out at
   the temples and over the ears' tops); widen_jaw ("head_scan_jaw"), open_canthus and settle_lashes after the face;
2. fit the face: a Gaussian RBF moves the character's face (and eyes, teeth, lashes) onto those points, so the
   eyelids, lips and face shapes keep working;
3. bring the scan into the character's rest pose: skeleton posed to the scan's stance (arm and leg axes from
   horizontal slices, feet turned to the shoes), scan skinned to it, then un-posed. Lifting the scan's arms
   stretches its armpits like fabric would; posing the body down instead would crush them;
4. project the body onto the scan part by part (sleeve, trouser leg, torso and hair) along its normals,
   smoothing the offsets over the mesh; the fitted face and the hands keep their own shape;
5. bake the scan's colour, roughness and detail normals into the body's UVs (scan_compose.py fills the missed
   texels and tones the kept hands to the face). Skin-coloured faces of the head, neck and hands keep the skin
   material; the rest (clothes, hair) gets a cloth material (split_materials). With a head scan the head texture is
   then cleaned (clean_eye_corners, soften_scan_skin, paint_sideburns, nape_band, nape_paint, clean_lobes,
   neck_shading, tone_ears; after the portrait, nostril_skin), and the body's neck faces keep the skin or cloth a build
   without the head scan gives them (absent_fit, body_classes).
"""
import bpy, bmesh, os, json, math, subprocess, shutil
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

PY = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"
TEX = 4096
HANDS = ("hand", "index", "middle", "ring", "pinky", "thumb")
PARTS = ("core", "arm_l", "arm_r", "leg_l", "leg_r")
REACH = (0.14, 0.1, 0.1, 0.25, 0.25)   # how far (m) the body may move onto each part: the hood, sleeves, balloon jeans
SIGMA, LAMBDA = 0.022, 2e-3            # face RBF, as face_fit.py


QUIET = [0]             # > 0: log() says nothing (body_classes runs the steps without a head scan a second time)


def log(*a):
    if not QUIET[0]:
        print("[scan]", *a, flush=True)


def part_of(bone):
    side = bone[-2:] if bone[-2:] in ("_l", "_r") else ""
    stem = bone[:-2] if side else bone
    if side and (stem.startswith(HANDS) or stem in ("upperarm", "lowerarm")):
        return PARTS.index("arm" + side)
    if side and stem in ("thigh", "calf", "foot", "ball"):
        return PARTS.index("leg" + side)
    return 0


# ------------------------------------------------------------------ mesh helpers
def world_verts(obj):
    me = obj.data
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    mw = np.array(obj.matrix_world)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def set_world_verts(obj, P, mask=None):
    me = obj.data
    inv = np.linalg.inv(np.array(obj.matrix_world))
    local = P @ inv[:3, :3].T + inv[:3, 3]
    if mask is not None:
        co = np.empty(len(me.vertices) * 3, np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        co[mask] = local[mask]
        local = co
    me.vertices.foreach_set("co", local.astype(np.float32).ravel())
    me.update()


def triangles(me):
    me.calc_loop_triangles()
    t = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", t)
    return t.reshape(-1, 3)


def edges(me):
    e = np.empty(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def vertex_normals(P, T):
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])   # area-weighted
    N = np.zeros_like(P)
    for k in range(3):
        for c in range(3):
            N[:, c] += np.bincount(T[:, k], weights=fn[:, c], minlength=len(P))
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def neighbour_mean(x, E, n):
    deg = np.maximum(np.bincount(E.ravel(), minlength=n), 1)
    return (np.bincount(E[:, 0], weights=x[E[:, 1]], minlength=n) + np.bincount(E[:, 1], weights=x[E[:, 0]], minlength=n)) / deg


def smooth(X, conf, E, iters, lam=0.6):
    """Confidence-weighted Laplacian smoothing over mesh edges E (n x 2): low-confidence vertices take their
    neighbours' values, confident ones keep most of their own."""
    n = len(X)
    c = conf.astype(np.float64).copy()
    Y = X * c[:, None]
    for _ in range(iters):
        sc = neighbour_mean(c, E, n)
        sy = np.stack([neighbour_mean(Y[:, k], E, n) for k in range(Y.shape[1])], 1)
        Y = (1 - lam) * Y + lam * sy
        c = (1 - lam) * c + lam * sc
    return Y / np.maximum(c, 1e-9)[:, None]


def seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ------------------------------------------------------------------ the scan
def load_scan(path, weld=1e-5):
    """Import a scan's glTF as one mesh object named "scan", its glTF-split vertices welded within weld (in the
    file's own units; "relative": a millionth of its largest side, for a head scan in any unit)."""
    bpy.ops.object.select_all(action='DESELECT')
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    scan = bpy.context.view_layer.objects.active
    for o in new:
        if o != scan and o.name in bpy.data.objects:
            bpy.data.objects.remove(o)
    scan.name = "scan"
    if weld == "relative":
        weld = 1e-6 * float(np.ptp(world_verts(scan), 0).max())
    # glTF splits vertices along UV seams; weld them (UVs live on the loops) so re-posing cannot open cracks
    bm = bmesh.new()
    bm.from_mesh(scan.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
    bm.to_mesh(scan.data)
    bm.free()
    for p in scan.data.polygons:
        p.use_smooth = True
    return scan


def set_eevee(scene):
    for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = e
            return
        except TypeError:
            pass


def render_views(scan, work, angles, size=(768, 768), centre=None, scale=None, prefix="scan_view"):
    """Orthographic close-ups of the scan's head (the face detector wants big faces), camera on a circle
    around it (0 deg = looking from -Y). centre / scale frame something else than a full body's head (a head
    scan); prefix names the images."""
    scene = bpy.context.scene
    hidden = [o for o in scene.objects if o != scan and not o.hide_render]
    for o in hidden:
        o.hide_render = True
    set_eevee(scene)
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    world = bpy.data.worlds.new("scan_world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.7, 0.7, 0.72, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    old_world, scene.world = scene.world, world
    V = world_verts(scan)
    lo, hi = V.min(0), V.max(0)
    H = float(hi[2] - lo[2])
    c = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2] - 0.11 * H)) if centre is None else Vector(centre)
    cam_d = bpy.data.cameras.new("scan_cam")
    cam_d.type = 'ORTHO'
    cam_d.ortho_scale = 0.3 * H if scale is None else scale
    cam = bpy.data.objects.new("scan_cam", cam_d)
    scene.collection.objects.link(cam)
    old_cam, scene.camera = scene.camera, cam
    shots = []
    for ang in angles:
        a = math.radians(ang)
        d = Vector((math.sin(a), -math.cos(a), 0.0))
        cam.location = c + d * (H * 2.0)
        cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        bpy.context.view_layer.update()
        path = os.path.join(work, f"{prefix}_{ang}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        shots.append({"angle": ang, "path": path, "mw": cam.matrix_world.copy(), "scale": cam_d.ortho_scale,
                      "w": size[0], "h": size[1]})
    bpy.data.objects.remove(cam)
    bpy.data.cameras.remove(cam_d)
    scene.camera, scene.world = old_cam, old_world
    bpy.data.worlds.remove(world)
    for o in hidden:
        o.hide_render = False
    return shots


def pixel_to_world(shot, px, py):
    """A pixel of an orthographic shot -> a world point on the camera plane (right and height are what count)."""
    w, h, s = shot["w"], shot["h"], shot["scale"]
    aspect = min(w, h) / max(w, h)
    sx, sy = (s * aspect, s) if h >= w else (s, s * aspect)
    mw = shot["mw"]
    right, up = mw.col[0].xyz, mw.col[1].xyz
    return mw.translation + right * ((px / w - 0.5) * sx) + up * ((0.5 - py / h) * sy)


def face_landmarks(shots, root):
    subprocess.run([PY, os.path.join(root, "tools", "py", "landmarks.py")] + [s["path"] for s in shots],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for s in shots:
        faces = json.load(open(s["path"] + ".lm.json"))["faces"]
        s["face"] = faces[0] if faces else None
    return shots


def anchor_points(basemesh, root):
    anchors = json.load(open(os.path.join(root, "tools", "models", "mpfb_face_anchors.json")))["anchors"]
    V = world_verts(basemesh)
    return {i: (V[a["v"]] * np.array(a["w"])[:, None]).sum(0) for i, a in enumerate(anchors) if a is not None}


INNER = [33, 7, 163, 144, 145, 153, 154, 155, 133, 246, 161, 160, 159, 158, 157, 173,
         263, 249, 390, 373, 374, 380, 381, 382, 362, 466, 388, 387, 386, 385, 384, 398,
         61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185,
         1, 2, 4, 5, 6, 168, 195, 197, 98, 327]
EYE_CORNERS = (33, 133, 362, 263)


def face_ratio(pts, floor):
    """Spread of the inner face (eyes, nose, mouth) over the eye height, both in the frontal plane: scale-free,
    so a scan and a body can be compared before either is scaled."""
    xz = np.array([pts[i] for i in INNER if i in pts])
    spread = float(np.sqrt(((xz - xz.mean(0)) ** 2).sum(1).mean()))
    return spread / (float(np.mean([pts[i][1] for i in EYE_CORNERS])) - floor)


def fit_height(make_human, scan_path, cid, root):
    """MakeHuman height that gives the body the scan's head-to-body proportions. Scanned people (and
    the GPT image behind them) have heads 8-25 % bigger, for their eye height, than an MPFB body of the cast's
    height; fitting the face would then blow the head up and the character would end up two metres tall.
    So the body is made shorter or taller instead, until its face spread over eye height matches the scan's
    (bisection over the height macro; make_human(h) builds a fresh human). Cached next to the scan."""
    cache = os.path.splitext(scan_path)[0] + "_fit.json"
    st = os.stat(scan_path)
    key = f"{st.st_size}:{int(st.st_mtime)}"
    if os.path.exists(cache):
        c = json.load(open(cache))
        if c.get("key") == key:
            log(cid, f"height macro {c['height']:.3f} (cached)")
            return c["height"]
    work = os.path.join(root, "tools", "out", f"scan_{cid}")
    os.makedirs(work, exist_ok=True)
    bpy.ops.wm.read_homefile(use_empty=True)
    scan = load_scan(scan_path)
    V = world_verts(scan)
    shots = face_landmarks(render_views(scan, work, (0, 90, 180, 270)), root)
    found = [sh for sh in shots if sh["face"]]
    if not found:
        raise RuntimeError("no face found on any side of the scan")
    front = max(found, key=lambda sh: sh["face"]["width"])
    right = front["mw"].col[0].xyz
    pts = {}
    for i in INNER + list(EYE_CORNERS):
        q = pixel_to_world(front, *front["face"]["pts"][i][:2])
        pts[i] = (q.dot(right), q.z)
    target = face_ratio(pts, float(V[:, 2].min()))
    lo, hi = 0.0, 1.0
    for _ in range(7):
        h = (lo + hi) / 2
        body = make_human(h)
        A = anchor_points(body, root)
        r = face_ratio({i: (a[0], a[2]) for i, a in A.items()}, float(world_verts(body)[:, 2].min()))
        lo, hi = (h, hi) if r > target else (lo, h)
    h = (lo + hi) / 2
    log(cid, f"height macro {h:.3f}: the scan's face spread / eye height is {target:.4f}")
    json.dump({"key": key, "height": h, "scan_ratio": target}, open(cache, "w"))
    return h


def normalise_scan(scan, basemesh, root, work):
    """Rotate the scan to face -Y, scale it so its eyes sit at the character's eye height and put it where the
    character stands (soles on the floor, face over face). Returns the face landmarks on the scan surface:
    {MediaPipe index: point}, frontal hits only."""
    V = world_verts(scan)
    ext = V.max(0) - V.min(0)
    if int(np.argmax(ext)) != 2:
        raise RuntimeError(f"scan is not upright (extents {ext})")
    shots = face_landmarks(render_views(scan, work, (0, 90, 180, 270)), root)
    found = [s for s in shots if s["face"]]
    if not found:
        raise RuntimeError("no face found on any side of the scan")
    front = max(found, key=lambda s: s["face"]["width"])
    ang = front["angle"]
    log("front at", ang, "deg; faces on", [s["angle"] for s in found])
    # rotating by -ang about Z brings that camera (and the face it saw) to -Y
    c = Vector((V.min(0) + V.max(0)) / 2)
    rot = Matrix.Translation(c) @ Matrix.Rotation(math.radians(-ang), 4, 'Z') @ Matrix.Translation(-c)
    pts = front["face"]["pts"]
    lm2d = [rot @ pixel_to_world(front, p[0], p[1]) for p in pts]
    scan.data.transform(rot)
    scan.data.update()

    def cast(V, bvh, p):
        """The scan surface straight in front of a landmark (seen from -Y): point and normal."""
        loc, n, _, _ = bvh.ray_cast(Vector((p.x, float(V[:, 1].min()) - 1.0, p.z)), Vector((0, 1, 0)), 4.0)
        return (np.array(loc), np.array(n)) if loc is not None else (None, None)

    V = world_verts(scan)
    ST = triangles(scan.data).tolist()
    bvh = BVHTree.FromPolygons(V.tolist(), ST, all_triangles=True)
    eye_s = (lm2d[33] + lm2d[133] + lm2d[362] + lm2d[263]) / 4
    nose_s = cast(V, bvh, lm2d[1])[0]
    floor_s = float(V[:, 2].min())

    A = anchor_points(basemesh, root)
    eye_t = (A[33] + A[133] + A[362] + A[263]) / 4
    floor_t = float(world_verts(basemesh)[:, 2].min())
    s = (eye_t[2] - floor_t) / (eye_s.z - floor_s)
    # scale about the scan's floor point under the eyes, then move it onto the character
    M = (Matrix.Translation(Vector((eye_t[0], A[1][1], floor_t))) @ Matrix.Scale(s, 4) @
         Matrix.Translation(-Vector((eye_s.x, nose_s[1], floor_s))))
    scan.data.transform(M)
    scan.data.update()
    V = world_verts(scan)
    bvh = BVHTree.FromPolygons(V.tolist(), ST, all_triangles=True)
    lms = {}
    for i, p in enumerate(lm2d[:468]):
        loc, n = cast(V, bvh, M @ p)
        if loc is not None and -n[1] > 0.35:   # facing the camera: not a grazing hit on a cheek or the hair
            lms[i] = loc
    log(f"scale {s:.3f}, scan height {float(np.ptp(V[:, 2])):.3f} m, {len(lms)} face landmarks on the scan")
    return lms


# ------------------------------------------------------------------ head scan
# An outfit's "head_scan" (a bust: head, hair, neck, top of the shoulders, made from a head crop of the portrait)
# replaces the full-body scan's head, whose face is a guess a few hundred pixels wide. It is aligned to the body
# scan's head, spliced in under the jaw, and the rest of the build runs on the joined scan as on any other.
HEAD_BAND = 0.015                               # the head scan's neck blends onto the body scan's over this (m)
HEAD_REACH = 0.015                              # where the body scan's neck is this close (m) ...
BODY_BAND = 0.04                                # ... further off, the body scan closes in onto the head scan's
                                                # neck over this under the seam
HEAD_FACE_EDGE = 0.0012                         # its face is decimated to edges of about this (m) ...
HEAD_DENSITY = 1.0                              # ... the rest (hair, ears, neck) to this times the body scan's
                                                # faces per m² on its own head
CHIN = (152, 175, 199, 200, 148, 377, 176, 400)
EARS = (234, 454, 127, 356, 93, 323)
# MediaPipe face mesh landmarks and their mirror images (from its canonical face), 3-12 cm apart, off the outline:
# the direction between each pair is the face's left-right axis (face_yaw)
YAW_PAIRS = [(7, 249), (22, 252), (23, 253), (24, 254), (25, 255), (26, 256), (27, 257), (28, 258), (29, 259), (30, 260),
             (31, 261), (32, 262), (33, 263), (35, 265), (36, 266), (40, 270), (42, 272), (43, 273), (46, 276), (47, 277),
             (48, 278), (49, 279), (50, 280), (52, 282), (53, 283), (56, 286), (57, 287), (61, 291), (62, 292), (63, 293),
             (64, 294), (65, 295), (66, 296), (68, 298), (69, 299), (70, 300), (74, 304), (76, 306), (77, 307), (78, 308),
             (88, 318), (89, 319), (90, 320), (91, 321), (92, 322), (95, 324), (96, 325), (100, 329), (101, 330),
             (102, 331), (104, 333), (105, 334), (106, 335), (108, 337), (110, 339), (111, 340), (112, 341), (113, 342),
             (117, 346), (118, 347), (119, 348), (120, 349), (121, 350), (124, 353), (126, 355), (129, 358), (130, 359),
             (133, 362), (135, 364), (138, 367), (140, 369), (142, 371), (144, 373), (145, 374), (146, 375), (153, 380),
             (154, 381), (155, 382), (157, 384), (158, 385), (159, 386), (160, 387), (161, 388), (163, 390), (165, 391),
             (169, 394), (170, 395), (173, 398), (182, 406), (183, 407), (184, 408), (185, 409), (186, 410), (187, 411),
             (190, 414), (191, 415), (192, 416), (194, 418), (202, 422), (203, 423), (204, 424), (205, 425), (206, 426),
             (207, 427), (209, 429), (210, 430), (211, 431), (212, 432), (214, 434), (216, 436), (221, 441), (222, 442),
             (223, 443), (224, 444), (225, 445), (226, 446), (228, 448), (229, 449), (230, 450), (231, 451), (232, 452),
             (233, 453), (243, 463), (246, 466), (247, 467)]


def face_yaw(lms):
    """How far (degrees, about +Z) a face's left-right axis is turned from +X: the median direction between mirrored
    landmarks (weighted by their distance apart). 0 for a face looking straight down -Y."""
    D = []
    for a, b in YAW_PAIRS:
        if a in lms and b in lms:
            d = np.asarray(lms[b], np.float64) - np.asarray(lms[a], np.float64)
            D.append(d if d[0] >= 0 else -d)
    if len(D) < 10:
        return 0.0, len(D)
    D = np.array(D)
    ang = np.degrees(np.arctan2(D[:, 1], D[:, 0]))
    w = np.linalg.norm(D[:, :2], axis=1)
    o = np.argsort(ang)
    cw = np.cumsum(w[o])
    return float(ang[o][np.searchsorted(cw, cw[-1] / 2)]), len(D)


def similarity_3d(X, Y):
    """Least-squares similarity X -> Y (Umeyama): Y ~ s R X + t."""
    mx, my = X.mean(0), Y.mean(0)
    Xc, Yc = X - mx, Y - my
    U, S, Vt = np.linalg.svd(Yc.T @ Xc)
    D = np.diag([1.0, 1.0, float(np.sign(np.linalg.det(U @ Vt)))])
    R = U @ D @ Vt
    s = float((S * np.diag(D)).sum() / (Xc ** 2).sum())
    return s, R, my - s * R @ mx


def as_matrix(s, R, t):
    M = np.eye(4)
    M[:3, :3] = s * R
    M[:3, 3] = t
    return M


def apply_matrix(M, P):
    return P @ M[:3, :3].T + M[:3, 3]


def surface_landmarks(obj, shot):
    """The face landmarks of a view from -Y (angle 0) cast onto the mesh, frontal hits only (as normalise_scan)."""
    V = world_verts(obj)
    bvh = BVHTree.FromPolygons(V.tolist(), triangles(obj.data).tolist(), all_triangles=True)
    y0 = float(V[:, 1].min()) - 1.0
    out = {}
    for i, p in enumerate(shot["face"]["pts"][:468]):
        q = pixel_to_world(shot, p[0], p[1])
        loc, n, _, _ = bvh.ray_cast(Vector((q.x, y0, q.z)), Vector((0, 1, 0)), 4.0)
        if loc is not None and -n[1] > 0.35:
            out[i] = np.array(loc)
    return out


def head_view(head, work, root, centre, width):
    """Close front view of the head scan, centred on its face (width: the face's, m); its landmarks on it."""
    shot = face_landmarks(render_views(head, work, (0,), centre=centre, scale=3.2 * width, prefix="head_front"),
                          root)[0]
    if not shot["face"]:
        raise RuntimeError("head scan: no face in the front close-up")
    hl = surface_landmarks(head, shot)
    if len(hl) < 100:
        raise RuntimeError(f"head scan: only {len(hl)} of 468 face landmarks landed on a surface facing the camera "
                           "(faces inside out, or the face hidden behind something?)")
    return hl


def fix_winding(obj, what):
    """Make a scan's faces wind outward: inconsistent winding (neighbouring faces disagreeing) is recomputed, a
    mesh turned inside out as a whole is flipped. Landmarks only count hits on faces turned to the camera, so an
    inside-out head scan would find no face at all."""
    me = obj.data
    V = world_verts(obj)
    T = triangles(me)
    d = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    _, cnt = np.unique(d[:, 0] * len(V) + d[:, 1], return_counts=True)
    clash = int((cnt > 1).sum())                 # an edge walked the same way by both its faces
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    vol = float((fn * (V[T].mean(1) - V.mean(0))).sum()) / 6.0
    if clash <= 0.001 * len(d) and vol >= 0:
        return
    bm = bmesh.new()
    bm.from_mesh(me)
    if clash > 0.001 * len(d):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        V, T = world_verts(obj), triangles(me)
        fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        vol2 = float((fn * (V[T].mean(1) - V.mean(0))).sum()) / 6.0
        log(f"{what}: {clash} edges with clashing winding; face winding recomputed")
        if vol2 < 0:
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
            log(f"{what}: still inside out; all faces flipped")
    else:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        log(f"{what}: faces were inside out (volume {vol:.4g}); all flipped")
    bm.to_mesh(me)
    bm.free()
    me.update()


def load_head_scan(path, work, root):
    """Load a head scan (any unit, +Y-up glTF, facing unknown), give it a nominal size (largest side 0.5 m) and turn
    its face to -Y: the landmarker looks at it from eight sides, the widest face wins, then once more from the front,
    close. Returns the object and its face landmarks on its surface."""
    head = load_scan(path, weld="relative")
    head.name = "head_scan"
    V = world_verts(head)
    lo, hi = V.min(0), V.max(0)
    head.data.transform(Matrix.Scale(0.5 / float((hi - lo).max()), 4) @ Matrix.Translation(-Vector((lo + hi) / 2)))
    head.data.update()
    fix_winding(head, "head scan")
    shots = face_landmarks(render_views(head, work, range(0, 360, 45), centre=(0, 0, 0), scale=0.6,
                                        prefix="head_view"), root)
    found = [s for s in shots if s["face"]]
    if not found:
        raise RuntimeError(f"no face found on any side of the head scan {path}")
    front = max(found, key=lambda s: s["face"]["width"])
    rot = Matrix.Rotation(math.radians(-front["angle"]), 4, 'Z')
    head.data.transform(rot)
    head.data.update()
    c = rot @ pixel_to_world(front, *np.array(front["face"]["pts"])[:, :2].mean(0))
    width = front["face"]["width"] * front["scale"] / front["w"]
    hl = head_view(head, work, root, (c.x, 0.0, c.z), width)
    log(f"head scan {os.path.basename(path)}: {len(head.data.vertices)} verts, {len(head.data.polygons)} faces, "
        f"{len(head.data.materials)} material(s); front at {front['angle']} deg (faces on "
        f"{[s['angle'] for s in found]}), {len(hl)} face landmarks")
    return head, hl


def landmark_fit(hl, lms):
    """Robust similarity from the head scan's face landmarks onto the body scan's: refitted without the points
    further off than 2.5x the median (or 2 mm), so a different jaw or cheek (what the head scan is for) does not
    pull the head round."""
    keys = sorted(set(hl) & set(lms))
    if len(keys) < 30:
        raise RuntimeError(f"head scan: only {len(keys)} face landmarks in common with the body scan's; "
                           "cannot place it")
    X = np.array([hl[k] for k in keys])
    Y = np.array([lms[k] for k in keys])
    keep = np.ones(len(keys), bool)
    for _ in range(5):
        s, R, t = similarity_3d(X[keep], Y[keep])
        r = np.linalg.norm(X @ (s * R).T + t - Y, axis=1)
        keep = r < max(2.5 * float(np.median(r[keep])), 0.002)
    s, R, t = similarity_3d(X[keep], Y[keep])
    r = np.linalg.norm(X @ (s * R).T + t - Y, axis=1)
    return as_matrix(s, R, t), r, keep


def neck_cut(lms):
    """The seam between the body scan and the head scan, a height over depth z(y) under the jaw: 1.8 cm under the
    chin in front, rising along the jaw line to 6 cm under the ears' landmarks just behind the jaw angle, then level
    round the back of the neck, above the hood bunched there and below the hair segment_hair keeps."""
    L = np.array(list(lms.values()))
    chin = min([lms[i] for i in CHIN if i in lms] or [L[L[:, 2].argmin()]], key=lambda p: p[2])
    ears = [lms[i] for i in EARS if i in lms]
    ear = np.mean(ears, 0) if ears else np.array([0.0, L[:, 1].max(), L[:, 2].mean()])
    y_f, z_f = chin[1] + 0.02, chin[2] - 0.018
    y_b, z_b = ear[1] + 0.05, ear[2] - 0.06
    return lambda y: z_f + (z_b - z_f) * smoothstep(y_f, y_b, y)


def head_regions(lms):
    """Masks on points: the face (in front of the ears' landmarks, below the forehead's top) and the head's column."""
    L = np.array(list(lms.values()))
    ears = [lms[i] for i in EARS if i in lms]
    ear_y = float(np.mean([p[1] for p in ears])) if ears else float(L[:, 1].max())
    top = float(lms[10][2]) if 10 in lms else float(L[:, 2].max())
    axis = np.array([float(L[:, 0].mean()), ear_y + 0.02])

    def face(P):
        return (P[:, 1] < ear_y) & (P[:, 2] < top + 0.01)

    def column(P, radius=0.17):
        return np.linalg.norm(P[:, :2] - axis, axis=1) < radius
    return face, column, axis


def nearest_landmark(P, L):
    """Distance from each point to the nearest of the points L."""
    out = np.empty(len(P))
    for s in range(0, len(P), 4000):
        out[s:s + 4000] = np.sqrt(((P[s:s + 4000, None, :] - L[None]) ** 2).sum(-1).min(1))
    return out


def face_areas(V, T):
    return 0.5 * np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1)


def head_density(scan, z_cut, column):
    """Faces (triangles) per m² of the body scan's head: above the seam, in the head's column."""
    SV = world_verts(scan)
    ST = triangles(scan.data)
    c = SV[ST].mean(1)
    m = (c[:, 2] > z_cut(c[:, 1])) & column(c)
    return float(m.sum() / max(face_areas(SV, ST[m]).sum(), 1e-9)), int(m.sum())


def decimate_where(obj, vmask, ratio):
    """Collapse-decimate the faces between the flagged vertices (a vertex group; edges between two unflagged
    vertices never collapse) by about ratio."""
    me = obj.data
    if ratio >= 0.999 or not vmask.any():
        return
    vg = obj.vertex_groups.new(name="decimate")
    vg_name = vg.name
    vg.add(np.nonzero(vmask)[0].tolist(), 1.0, 'REPLACE')
    n = len(me.polygons)
    T = triangles(me)
    sel = vmask[T].any(1).sum()
    mod = obj.modifiers.new("decimate", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = float((n - sel * (1.0 - ratio)) / n)    # the modifier's ratio is over the whole mesh
    mod.vertex_group = vg_name
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.vertex_groups.remove(obj.vertex_groups[vg_name])


def decimate_head(head, lms, density):
    """Bring a head scan (1-2M faces from Tripo or Hunyuan) down before it joins the body scan: the face (within
    3.5 cm of its landmarks, in front of the ears, below the forehead's top, not hair-dark) to edges of
    HEAD_FACE_EDGE, as project_face and the normal bake read its shape there; the rest (hair, ears, neck) to
    HEAD_DENSITY times the body scan's density on its own head, so segment_hair and the hair cards' fixed smoothing
    get a shell like a body scan's (a few thousand faces, not 300k)."""
    def regions():
        V = world_verts(head)
        T = triangles(head.data)
        L = np.array(list(lms.values()))
        ears = [lms[i] for i in EARS if i in lms]
        ear_y = float(np.mean([p[1] for p in ears])) if ears else float(L[:, 1].max())
        top = float(lms[10][2]) if 10 in lms else float(L[:, 2].max())
        dense = ((nearest_landmark(V, L) < 0.035) & (V[:, 1] < ear_y + 0.015) & (V[:, 2] < top + 0.005)
                 & (to_lab(scan_colors(head.data))[:, 0] > 20))      # not the fringe and sideburns: hair
        fd = dense[T].all(1)
        A = face_areas(V, T)
        return V, T, dense, fd, A
    V, T, dense, fd, A = regions()
    n0, nf0 = len(T), int(fd.sum())
    tf = A[fd].sum() / (0.433 * HEAD_FACE_EDGE ** 2)
    tr = A[~fd].sum() * density * HEAD_DENSITY
    decimate_where(head, dense, tf / max(nf0, 1))
    V, T, dense, fd, A = regions()
    decimate_where(head, ~dense, tr / max(len(T) - int(fd.sum()), 1))
    V, T, dense, fd, A = regions()
    log(f"head scan decimated: {n0} -> {len(T)} triangles; face {nf0} -> {int(fd.sum())} (target {tf:.0f}, edges "
        f"~{HEAD_FACE_EDGE * 1000:.1f} mm), rest {n0 - nf0} -> {len(T) - int(fd.sum())} (target {tr:.0f}: "
        f"{HEAD_DENSITY} x the body scan's {density:.0f} faces/m² on its head)")


def bake_images(target, tex, name, kind, data, passes, size):
    """Bake the selected objects onto `target` (active, its material's image node `tex` active) through each
    (cage extrusion, max ray distance, margin) of `passes` in turn; a texel takes the first pass whose ray hit it
    (alpha). Returns the pixels (size x size x 4, alpha 1)."""
    out = None
    for ext, reach, margin in passes:
        img = bpy.data.images.new(f"rebake_{name}", size, size, alpha=True, float_buffer=False)
        img.colorspace_settings.name = 'sRGB' if data == "color" else 'Non-Color'
        tex.image = img
        tex.id_data.nodes.active = tex
        bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=ext, max_ray_distance=reach,
                            margin=margin, use_clear=True)
        px = np.empty(size * size * 4, np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(size, size, 4)
        bpy.data.images.remove(img)
        if out is None:
            out = px
        else:
            miss = out[..., 3] < 0.5
            out[miss] = px[miss]
    out[..., 3] = 1.0
    return out


def skew(P):
    """Rows of the cross-product matrices [p]x, n x 3 x 3."""
    Z = np.zeros(len(P))
    return np.stack([np.stack([Z, -P[:, 2], P[:, 1]], 1), np.stack([P[:, 2], Z, -P[:, 0]], 1),
                     np.stack([-P[:, 1], P[:, 0], Z], 1)], 1)


def icp_head(head, scan, lms, hl, z_cut, iters=30):
    """Refine the head scan's placement by a rigid point-to-plane ICP (rotation and offset only: the face landmarks
    set its size) of its skin round the ears and under the hairline onto the body scan's: the cranium's own
    surface, not the hair (two scans never agree on hair), nor the face (what the head scan replaces). The face
    landmarks (hl, the head scan's, already placed) pull towards the body scan's with as much weight as all those
    points together, so the landmark fit stays the authority. The result is kept only if it moves the face
    landmarks no further from the body scan's; otherwise the landmark fit stands. Returns a 4x4 matrix."""
    face, column, _ = head_regions(lms)
    L = np.array(list(lms.values()))
    brow = float(np.mean([lms[i][2] for i in BROWS if i in lms] or [L[:, 2].mean()]))

    def skin(obj):
        P = world_verts(obj)
        light = to_lab(scan_colors(obj.data))[:, 0] > 35            # hair (and the dark hood) is darker
        return P, light & ~face(P) & column(P) & (P[:, 2] > z_cut(P[:, 1]) + 0.025) & (P[:, 2] < brow + 0.02)
    SV, sm = skin(scan)
    ST = triangles(scan.data)
    ST = ST[sm[ST].all(1)]
    HV, hm = skin(head)
    if len(ST) < 100 or hm.sum() < 200:
        log(f"head scan ICP: too little skin round the ears ({len(ST)} body faces, {int(hm.sum())} head points); "
            "landmark fit kept")
        return np.eye(4)
    bvh = BVHTree.FromPolygons(SV.tolist(), ST.tolist(), all_triangles=True)
    HN = vertex_normals(HV, triangles(head.data))
    sel = np.nonzero(hm)[0]
    sel = sel[::max(1, len(sel) // 6000)]
    P0, N0 = HV[sel], HN[sel]
    keys = sorted(set(hl) & set(lms))
    X0 = np.array([hl[k] for k in keys])
    Y = np.array([lms[k] for k in keys])
    r0 = np.linalg.norm(X0 - Y, axis=1)
    lk = r0 < max(2.5 * float(np.median(r0)), 0.002)                # the landmarks the fit kept
    X0, Y = X0[lk], Y[lk]

    def match(M, thr):
        P = apply_matrix(M, P0)
        Nn = N0 @ M[:3, :3].T
        Q, QN, d = np.zeros_like(P), np.zeros_like(P), np.full(len(P), np.inf)
        for i, p in enumerate(P):
            loc, n, _, dist = bvh.find_nearest(Vector(p), thr)
            if loc is not None:
                Q[i], QN[i], d[i] = loc, n, dist
        return P, Q, QN, d, np.isfinite(d) & ((Nn * QN).sum(1) > 0.5)

    M = np.eye(4)
    thr = 0.015
    it = 0
    for it in range(iters):
        P, Q, QN, d, ok = match(M, thr)
        if ok.sum() < 100:
            log(f"head scan ICP: only {int(ok.sum())} skin points matched; landmark fit kept")
            return np.eye(4)
        thr = float(np.clip(3.0 * np.median(d[ok]), 0.002, 0.015))
        ok &= d < thr
        X = apply_matrix(M, X0)
        c = P[ok].mean(0)
        pc, n = P[ok] - c, QN[ok]
        A1 = np.hstack([np.cross(pc, n), n])
        b1 = -((P[ok] - Q[ok]) * n).sum(1)
        wl = math.sqrt(ok.sum() / (3.0 * len(X)))                   # landmarks weigh as much as the ICP points
        A2 = np.concatenate([-skew(X - c), np.repeat(np.eye(3)[None], len(X), 0)], 2).reshape(-1, 6) * wl
        b2 = (Y - X).ravel() * wl
        x = np.linalg.lstsq(np.vstack([A1, A2]), np.concatenate([b1, b2]), rcond=None)[0]
        w, t = x[:3], x[3:]
        a = float(np.linalg.norm(w))
        Rw = np.array(Matrix.Rotation(a, 3, Vector(w / a))) if a > 1e-12 else np.eye(3)
        inc = np.eye(4)
        inc[:3, :3] = Rw
        inc[:3, 3] = c + t - Rw @ c
        M = inc @ M
        if a < 1e-5 and np.linalg.norm(t) < 1e-5:
            break
    P, Q, QN, d, ok = match(M, 0.015)
    r1 = np.linalg.norm(apply_matrix(M, X0) - Y, axis=1)
    moved = np.linalg.norm(P - P0, axis=1)
    ang = math.degrees(math.acos(np.clip((np.trace(M[:3, :3]) - 1) / 2, -1, 1)))
    msg = (f"head scan ICP on the skin round the ears ({len(P0)} points, {it + 1} steps, rigid): {ok.mean() * 100:.0f}% "
           f"matched, distance median {np.median(d[ok]) * 1000:.2f} mm, 95% {np.percentile(d[ok], 95) * 1000:.2f} mm; "
           f"would move it {moved.mean() * 1000:.1f} mm, turn {ang:.2f} deg; face landmarks median "
           f"{np.median(r0[lk]) * 1000:.2f} -> {np.median(r1) * 1000:.2f} mm")
    if np.median(r1) > np.median(r0[lk]) + 0.0002 or ang > 4.0 or moved.mean() > 0.01:
        log(msg + "; rejected, landmark fit kept")
        return np.eye(4)
    log(msg + "; kept")
    return M


def cut_at(obj, z_cut, keep_above, column=None):
    """Cut a mesh along the seam z = z_cut(y) and drop one side (within the column only, if given). The seam is
    a plane in a space sheared by z_cut, so bisect_plane cuts it exactly: the new edge lies on it."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    for v in bm.verts:
        v.co.z -= float(z_cut(v.co.y))
    faces = list(bm.faces)
    if column is not None:
        inside = column(np.array([v.co for v in bm.verts]))
        bm.verts.ensure_lookup_table()
        faces = [f for f in faces if all(inside[v.index] for v in f.verts)]
    geom = faces + list({e for f in faces for e in f.edges}) + list({v for f in faces for v in f.verts})
    bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-7, plane_co=(0, 0, 0), plane_no=(0, 0, 1),
                           clear_outer=not keep_above, clear_inner=keep_above)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    for v in bm.verts:
        v.co.z += float(z_cut(v.co.y))
    bm.verts.index_update()
    ring = [(e.verts[0].index, e.verts[1].index) for e in bm.edges if e.is_boundary and
            all(abs(v.co.z - z_cut(v.co.y)) < 1e-5 for v in e.verts)]
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return np.array(ring, np.int64).reshape(-1, 2)


def components(n, E):
    """Connected pieces of a mesh: a label per vertex (union-find in numpy: hook roots, then pointer jumping)."""
    p = np.arange(n)
    while len(E):
        pu, pv = p[E[:, 0]], p[E[:, 1]]
        diff = pu != pv
        if not diff.any():
            break
        np.minimum.at(p, np.maximum(pu[diff], pv[diff]), np.minimum(pu[diff], pv[diff]))
        while True:
            q = p[p]
            if (q == p).all():
                break
            p = q
    return p


def keep_head_pieces(head, lms, z_cut, axis, quiet=False):
    """After the cut, keep the head scan's piece that holds the face, and pieces that float free well above the seam
    close to the head (stray curls); the rest goes, chiefly its hood or collar, which the seam cut loose from the
    neck at the back (it stood behind the nape as a flap)."""
    me = head.data
    V = world_verts(head)
    lab = components(len(V), edges(me))
    L = np.array([lms[k] for k in lms])
    kd = KDTree(len(V))
    for i, p in enumerate(V):
        kd.insert(p, i)
    kd.balance()
    face_lab = np.array([lab[kd.find(p)[1]] for p in L])
    main = int(np.bincount(face_lab).argmax())
    h = V[:, 2] - z_cut(V[:, 1])
    rad = np.linalg.norm(V[:, :2] - axis, axis=1)
    ids, inv = np.unique(lab, return_inverse=True)
    keep = np.zeros(len(ids), bool)
    hmin = np.full(len(ids), np.inf)
    np.minimum.at(hmin, inv, h)
    rmax = np.zeros(len(ids))
    np.maximum.at(rmax, inv, rad)
    keep[ids == main] = True
    keep |= (hmin > 0.03) & (rmax < 0.17)
    drop = ~keep[inv]
    sizes = np.bincount(inv)
    gone = [(int(sizes[j]), round(float(hmin[j]) * 1000, 1)) for j in np.argsort(-sizes) if not keep[j]][:6]
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.nonzero(drop)[0]], context='VERTS')
    bm.to_mesh(me)
    bm.free()
    me.update()
    if not quiet:
        log(f"head scan pieces after the cut: {len(ids)}; kept {int(keep.sum())} ({int((~drop).sum())} verts), dropped "
            f"{int(drop.sum())} verts in {int((~keep).sum())} pieces (largest, verts and lowest mm over the seam: {gone})")
    return int(drop.sum())


def to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def harmonic(X, fixed, E, iters=400):
    """Values at the unfixed vertices replaced by the harmonic interpolation (over the mesh's edges) of the fixed."""
    X = X.copy()
    free = ~fixed
    if not free.any() or not fixed.any():
        return X
    X[free] = X[fixed].mean(0)
    for _ in range(iters):
        nm = np.stack([neighbour_mean(X[:, k], E, len(X)) for k in range(X.shape[1])], 1)
        X[free] = nm[free]
    return X


def gauss_mean(P, Q, C, sigma, min_w=1e-3):
    """Per point P: the Gaussian-weighted mean of the colours C at the points Q, and the weight behind it."""
    out, wsum = np.zeros((len(P), C.shape[1])), np.zeros(len(P))
    if not len(Q):
        return out, wsum
    for s in range(0, len(P), 512):
        w = np.exp(-((P[s:s + 512, None, :] - Q[None]) ** 2).sum(-1) / (2 * sigma ** 2))
        wsum[s:s + 512] = w.sum(1)
        out[s:s + 512] = (w @ C) / np.maximum(w.sum(1, keepdims=True), min_w)
    return out, wsum


def value_noise(P, scale, seed=0):
    """Smooth 3D value noise in 0-1: a hashed lattice `scale` apart, interpolated with smoothstep (deterministic)."""
    Q = np.asarray(P, np.float64) / scale
    i0 = np.floor(Q).astype(np.int64)
    f = Q - i0
    u = f * f * (3.0 - 2.0 * f)
    out = np.zeros(len(Q))
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                k = ((i0[:, 0] + dx) * 73856093) ^ ((i0[:, 1] + dy) * 19349663) ^ ((i0[:, 2] + dz) * 83492791) ^ (seed * 977 + 1)
                k = (k ^ (k >> 13)) * 1274126177
                k = (k ^ (k >> 16)) & 0xFFFF
                w = (u[:, 0] if dx else 1 - u[:, 0]) * (u[:, 1] if dy else 1 - u[:, 1]) * (u[:, 2] if dz else 1 - u[:, 2])
                out += w * (k / 65535.0)
    return out


def texel_hash(xs, ys, seed=0):
    """A fixed pseudo-random number in 0-1 per texel."""
    k = (np.asarray(xs, np.int64) * 73856093) ^ (np.asarray(ys, np.int64) * 19349663) ^ (seed * 83492791 + 7)
    k = (k ^ (k >> 13)) * 1274126177
    return ((k ^ (k >> 16)) & 0xFFFF) / 65535.0


def uv_texels(UVp, W, H, pad=0.0, small=6, chunk=60000):
    """Rasterise triangles given in texel units (n x 3 x 2): every texel whose centre lies inside one, or within `pad`
    texels outside it, with that triangle, its barycentric coordinates (clamped onto it) and how far outside it lies
    (0 inside). Returns ys, xs, tri, bary (k x 3), out. Triangles whose box spans up to `small` texels go in batches
    (a full head scan's 2M triangles), the others one by one."""
    UVp = np.asarray(UVp, np.float64)
    Ys, Xs, Ts, Bs, Os = [], [], [], [], []

    def emit(P, qx, qy, tri, valid):
        a2 = (P[:, 1, 0] - P[:, 0, 0]) * (P[:, 2, 1] - P[:, 0, 1]) - (P[:, 2, 0] - P[:, 0, 0]) * (P[:, 1, 1] - P[:, 0, 1])
        good = np.abs(a2) >= 1e-9
        lam = np.empty(qx.shape + (3,))
        dist = np.empty(qx.shape + (3,))
        for k in range(3):
            A_, B_ = P[:, (k + 1) % 3], P[:, (k + 2) % 3]
            cr = (B_[:, 0, None] - A_[:, 0, None]) * (qy - A_[:, 1, None]) - (B_[:, 1, None] - A_[:, 1, None]) * (qx - A_[:, 0, None])
            lam[..., k] = cr / np.where(good, a2, 1.0)[:, None]
            dist[..., k] = cr * np.sign(a2)[:, None] / np.maximum(np.hypot(B_[:, 0] - A_[:, 0], B_[:, 1] - A_[:, 1]), 1e-9)[:, None]
        out = np.maximum(-dist.min(-1), 0.0)
        m = valid & (out <= pad) & good[:, None]
        if not m.any():
            return
        lb = np.clip(lam[m], 0.0, None)
        lb /= np.maximum(lb.sum(1, keepdims=True), 1e-12)
        Ys.append(qy[m].astype(np.int64))
        Xs.append(qx[m].astype(np.int64))
        Ts.append(np.broadcast_to(tri[:, None], qx.shape)[m])
        Bs.append(lb)
        Os.append(out[m])
    lo = np.floor(UVp.min(1) - pad).astype(np.int64)
    hi = np.ceil(UVp.max(1) + pad).astype(np.int64)
    lo = np.maximum(lo, 0)
    hi[:, 0] = np.minimum(hi[:, 0], W - 1)
    hi[:, 1] = np.minimum(hi[:, 1], H - 1)
    ext = hi - lo + 1
    is_small = (ext <= small).all(1) & (ext > 0).all(1)
    g = np.arange(small)
    idx = np.nonzero(is_small)[0]
    for c0 in range(0, len(idx), chunk):
        t = idx[c0:c0 + chunk]
        gx = lo[t, 0, None, None] + g[None, None, :]
        gy = lo[t, 1, None, None] + g[None, :, None]
        valid = ((gx <= hi[t, 0, None, None]) & (gy <= hi[t, 1, None, None])).reshape(len(t), -1)
        qx = np.broadcast_to(gx, (len(t), small, small)).reshape(len(t), -1) + 0.5
        qy = np.broadcast_to(gy, (len(t), small, small)).reshape(len(t), -1) + 0.5
        emit(UVp[t], qx, qy, t, valid)
    for t in np.nonzero(~is_small & (ext > 0).all(1))[0]:
        gx, gy = np.meshgrid(np.arange(lo[t, 0], hi[t, 0] + 1) + 0.5, np.arange(lo[t, 1], hi[t, 1] + 1) + 0.5)
        emit(UVp[t:t + 1], gx.ravel()[None], gy.ravel()[None], np.array([t]), np.ones((1, gx.size), bool))
    if not Ys:
        z = np.zeros(0, np.int64)
        return z, z, z, np.zeros((0, 3)), np.zeros(0)
    return np.concatenate(Ys), np.concatenate(Xs), np.concatenate(Ts), np.concatenate(Bs), np.concatenate(Os)


def color_node(mat):
    """The image node behind a material's base colour."""
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    node = bsdf.inputs["Base Color"].links[0].from_node if bsdf.inputs["Base Color"].links else None
    while node is not None and node.type != 'TEX_IMAGE':
        node = next((i.links[0].from_node for i in node.inputs if i.links), None)
    return node


def fill_neck(head, lms, scan, ring, z_cut, work, hi=None):
    """The head scan's neck between the seam and the jaw (seam to 4-6 cm up, under the earlobes) is made to meet the
    body scan's, in its own 4K texture, texel by texel. In a portrait with a hood up to the jaw the scan's maker never
    saw that skin and painted it with whatever came to hand (stubble down to the hood, a streak of hair down the side
    of the neck, a lip of the hood's lining); once the hood is gone it shows. Done per vertex, the fill is a flat,
    smeared band with a straight top edge from the earlobe to the chin, so it is done on a copy of the texture:
    - it is toned to the body scan's skin at the seam: a gain (linear RGB), the ratio of the two skins just above and
      below the seam (Gaussian means over 1.5 cm, skin only; 1 where either side is not skin, as the hair at the back),
      interpolated harmonically up to 1 at the strip's top and round the face's landmarks. Its pores stay;
    - in front of the ears only (behind them the head scan's hair runs down to the seam, as the body scan's dark nape
      under it: filled with skin it was a pale strip between the hair and a grey band), the beard and stubble end at a
      neckline 3-13 mm above the seam, its height wandering with a 2.5 cm and a 7 mm noise, thinning out and fading over
      1.4 cm texel by texel (a dither, as hairs thin out); below it the texels take clean skin: the head scan's own
      toned skin round them (not beard, not hair), turning into the body scan's skin along the seam;
    - in front of the ears, texels much darker than its skin (hair painted down the neck, the hood's lining) further
      than 1-2.4 cm from the face's landmarks take that clean skin too (the beard along the jaw keeps its texture);
    - within 6 mm of the seam every texel turns into the body scan's own colour just under it (skin in front, the
      dark nape behind), so no step is left at the seam itself.
    hi: the full head scan (bake_source), whose triangles find the texels (the decimated ones' UVs are a collapsed,
    smeared version of the same atlas: texels only the full scan uses were left as they were); the fields worked out
    on the decimated vertices reach its vertices from the nearest of them.
    Returns the number of texels changed."""
    me = head.data
    V = world_verts(head)
    h = V[:, 2] - z_cut(V[:, 1])
    L = np.array(list(lms.values()))
    ears = [lms[i] for i in EARS if i in lms]
    ear_z = float(np.mean([p[2] for p in ears])) if ears else float(L[:, 2].mean())
    ear_y = float(np.mean([p[1] for p in ears])) if ears else float(L[:, 1].max())
    near = nearest_landmark(V, L)
    reg = (1.0 - smoothstep(ear_z - 0.045, ear_z - 0.03, V[:, 2])) * (1.0 - smoothstep(0.04, 0.06, h))
    strip = reg > 1e-3
    if not strip.any():
        return 0
    E = edges(me)
    c = scan_colors(me)
    lab = to_lab(c)
    lin = to_linear(c)
    # its own skin: round the chin and the jaw (1-3 cm from the landmarks below the mouth), light (not stubble)
    mouth_z = float(lms[14][2]) if 14 in lms else float(L[:, 2].mean())
    ref = (near > 0.008) & (near < 0.03) & (V[:, 2] < mouth_z) & (h > 0.0) & (lab[:, 0] > 40)
    skin_l = float(np.median(lab[ref, 0])) if ref.sum() > 20 else float(np.percentile(lab[strip, 0], 75))
    # the tone at the seam: the body scan's skin just under it over the head scan's just above it
    SV = world_verts(scan)
    hb = SV[:, 2] - z_cut(SV[:, 1])
    sc = scan_colors_by_material(scan.data)        # (with fill_body_band's smoothing)
    slab = to_lab(sc)
    slin = to_linear(sc)
    cen = V[strip, :2].mean(0)
    under = (hb > -0.025) & (hb < 1e-5) & (np.linalg.norm(SV[:, :2] - cen, axis=1) < 0.15)
    body_s = under & (slab[:, 0] > 40)                                # its skin (the hood is L ~20, hair < 10)
    head_s = strip & (h > -1e-5) & (h < 0.025) & (lab[:, 0] > skin_l - 12)
    seam = strip & (np.abs(h) < 1e-5)
    gain = np.ones((len(V), 3))
    fixed = ~strip | (near < 0.012) | (h > 0.055) | seam
    if seam.any() and body_s.any() and head_s.any():
        cb, wb = gauss_mean(V[seam], SV[body_s], slin[body_s], 0.015)
        ch, wh = gauss_mean(V[seam], V[head_s], lin[head_s], 0.015)
        ok = (wb > 0.5) & (wh > 0.5)
        g = np.clip(cb / np.maximum(ch, 1e-3), 0.65, 1.5)
        si = np.nonzero(seam)[0]
        gain[si[ok]] = g[ok]
        gain = np.clip(harmonic(gain, fixed, E), 0.65, 1.5)
    toned = lin * gain
    # clean skin per vertex: the head scan's own toned skin round it, the body scan's skin along the seam
    sv = np.nonzero(strip)[0]
    skin_h = (V[:, 2] < ear_z) & (h > -1e-5) & (h < 0.08) & (lab[:, 0] > skin_l - 10) & (near > 0.004)
    Sh, wsh = gauss_mean(V[sv], V[skin_h], toned[skin_h], 0.012)
    Sb, wsb = gauss_mean(V[sv], SV[body_s], slin[body_s], 0.012)
    a = 1.0 - smoothstep(0.0, 0.02, h[sv])
    a = np.where(wsh < 0.2, 1.0, np.where(wsb < 0.2, 0.0, a))
    S = np.zeros((len(V), 3))
    S[sv] = Sh * (1 - a)[:, None] + Sb * a[:, None]
    lost = (wsh < 0.2) & (wsb < 0.2)
    S[sv[lost]] = np.median(toned[skin_h], 0) if skin_h.any() else toned[sv[lost]]
    # the body scan's own colour just under the seam (skin or not)
    band = under & (hb > -0.012)
    Cs = np.zeros((len(V), 3))
    wcs = np.zeros(len(V))
    if band.any():
        Cs[sv], wcs[sv] = gauss_mean(V[sv], SV[band], slin[band], 0.008)
    # texel by texel, in a copy of its texture
    node = color_node(me.materials[0])
    if node is None or node.image is None:
        log("head scan: no colour texture; its neck left as it is")
        return 0
    img = node.image
    W_, H_ = img.size
    px = np.empty(W_ * H_ * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(H_, W_, 4)
    gain_seam = np.round(gain[seam].mean(0), 2).tolist() if seam.any() else [1, 1, 1]
    n_strip = int(strip.sum())
    tm = hi.data if hi is not None else me
    tm.calc_loop_triangles()
    tv = np.empty(len(tm.loop_triangles) * 3, np.int64)
    tm.loop_triangles.foreach_get("vertices", tv)
    tl = np.empty(len(tm.loop_triangles) * 3, np.int64)
    tm.loop_triangles.foreach_get("loops", tl)
    tv, tl = tv.reshape(-1, 3), tl.reshape(-1, 3)
    uv = np.empty(len(tm.loops) * 2, np.float32)
    tm.uv_layers.active.data.foreach_get("uv", uv)
    UVp = (uv.reshape(-1, 2)[tl] % 1.0) * np.array([W_, H_])
    if hi is not None:
        # the fields onto the full scan's vertices: those set by place here, the others from the decimated vertices
        Vt = world_verts(hi)
        ht = Vt[:, 2] - z_cut(Vt[:, 1])
        reg_t = (1.0 - smoothstep(ear_z - 0.045, ear_z - 0.03, Vt[:, 2])) * (1.0 - smoothstep(0.04, 0.06, ht))
        sel_t = np.nonzero((reg_t[tv] > 1e-3).any(1))[0]
        need = np.unique(tv[sel_t])
        kd = KDTree(len(V))
        for i, p in enumerate(V.tolist()):
            kd.insert(p, i)
        kd.balance()
        J = np.empty((len(need), 4), np.int64)
        Dd = np.empty((len(need), 4))
        for r_, p in enumerate(Vt[need].tolist()):
            hits = kd.find_n(p, 4)
            J[r_] = [h_[1] for h_ in hits]
            Dd[r_] = [h_[2] for h_ in hits]
        Wk = 1.0 / (Dd + 1e-4) ** 2
        Wk /= Wk.sum(1, keepdims=True)

        def onto(X, fill=0.0):
            X = np.asarray(X, np.float64)
            out = np.full((len(Vt),) + X.shape[1:], fill)
            out[need] = (Wk.reshape(Wk.shape + (1,) * (X.ndim - 1)) * X[J]).sum(1)
            return out
        gain, S, Cs, wcs = onto(gain, 1.0), onto(S), onto(Cs), onto(wcs)
        reg = reg_t
        near_t = np.full(len(Vt), 1.0)
        near_t[need] = nearest_landmark(Vt[need], L)
        near = near_t
        V = Vt
        log(f"head scan: its neck's texels found by the full scan's triangles ({len(sel_t)})")
    else:
        sel_t = np.nonzero(strip[tv].any(1))[0]
    # every triangle's own texels (a texel just outside a strip triangle may belong to another part of the head)
    cov = np.zeros((H_, W_), bool)
    uv_lo = UVp[sel_t].reshape(-1, 2).min(0) - 4
    uv_hi = UVp[sel_t].reshape(-1, 2).max(0) + 4
    box = np.nonzero(((UVp.max(1) >= uv_lo) & (UVp.min(1) <= uv_hi)).all(1))[0]
    ys, xs, _, _, _ = uv_texels(UVp[box], W_, H_)
    cov[ys, xs] = True
    ys, xs, tt, bb, out = uv_texels(UVp[sel_t], W_, H_, pad=1.5)
    ok = (out == 0) | ~cov[ys, xs]
    ys, xs, tt, bb, out = ys[ok], xs[ok], tt[ok], bb[ok], out[ok]
    o = np.argsort(-out, kind="stable")               # inside texels last: they win over a neighbour's margin
    ys, xs, tt, bb = ys[o], xs[o], tt[o], bb[o]
    tvs = tv[sel_t][tt]

    def at(X):
        return (bb[..., None] * X[tvs]).sum(1) if X.ndim == 2 else (bb * X[tvs]).sum(1)
    P = at(V)
    ht = P[:, 2] - z_cut(P[:, 1])
    front = 1.0 - smoothstep(ear_y + 0.01, ear_y + 0.03, P[:, 1])
    orig = px[ys, xs, :3].astype(np.float64)
    T_ = to_linear(orig) * at(gain)
    Lt = to_lab(orig)[:, 0]
    nl = 0.003 + 0.007 * value_noise(P, 0.025, 1) + 0.003 * (value_noise(P, 0.007, 2) - 0.5)
    wn = front * (1.0 - smoothstep(nl, nl + 0.014, ht))
    bad = front * at(reg) * smoothstep(skin_l - 12, skin_l - 24, Lt) * smoothstep(0.012, 0.024, at(near))
    w = np.maximum(wn, bad)
    u = 0.2 + 0.6 * texel_hash(xs, ys, 3)
    wt = np.maximum(smoothstep(u - 0.2, u + 0.2, w), 0.8 * w)     # the hairs thin out and fade
    res = T_ + wt[:, None] * (at(S) - T_)
    sw = (1.0 - smoothstep(0.0, 0.006, ht)) * smoothstep(0.2, 0.5, at(wcs))
    res = res + sw[:, None] * (at(Cs) - res)
    new = to_srgb(res)
    changed = np.abs(new - orig).max(1) > 1.0 / 255
    px[ys, xs, :3] = new
    out_img = bpy.data.images.new(img.name + "_neck", W_, H_, alpha=True)
    out_img.pixels.foreach_set(px.ravel())
    path = os.path.join(work, "head_scan_color.png")
    out_img.filepath_raw = path
    out_img.file_format = 'PNG'
    out_img.save()
    bpy.data.images.remove(out_img)
    new_img = bpy.data.images.load(path, check_existing=False)
    new_img.colorspace_settings.name = img.colorspace_settings.name
    node.image = new_img
    fw = wt > 0.5
    log(f"head scan: its neck between the seam and the jaw ({n_strip} vertices) toned to the body scan's skin at "
        f"the seam (gain there {gain_seam}, its skin L "
        f"{skin_l:.0f}), in its texture: {int(changed.sum())} texels changed, {int((fw & (wn >= bad)).sum())} cleaned "
        f"under its neckline, {int((fw & (bad > wn)).sum())} not skin in front of the ears cleaned, "
        f"{int((sw > 0.5).sum())} within 6 mm of the seam onto the body scan's colour")
    return int(changed.sum())


def fill_body_band(scan, z_cut, column, depth=0.03, head=None, ear_y=None):
    """The body scan's neck just under the seam (`depth`, where it is skin, not its hood) takes a smooth version of its
    own colour (Gaussian over 1.5 cm): its old jaw line and beard edge, now under the head scan's slimmer jaw, showed
    as a dotted dark line from the earlobe down to the chin (dots finer than its mesh). Same attributes and material
    mix as fill_neck (gain 1).
    head (a head scan, ear_y its ears' depth): behind the ears the body scan's band under the seam is its hood pulled in
    onto the neck (close_in), a grey, streaky band under the head scan's hair with skin round it that read as a
    collar under a key light. It takes the head scan's hair colour just over the seam, fading out 2-4 cm down along a
    wandering line into the hood: the hair comes down to the collar."""
    me = scan.data
    SV = world_verts(scan)
    hb = SV[:, 2] - z_cut(SV[:, 1])
    c = scan_colors(me)
    lin = to_linear(c)
    lab = to_lab(c)
    E = edges(me)
    near = column(SV) & (hb > -depth - 0.015) & (hb < 1e-5)
    skin = near & (lab[:, 0] > 40)                         # the hood is L ~20
    x = skin.astype(np.float64)
    for _ in range(3):
        x = np.maximum(x, (neighbour_mean(x, E, len(SV)) > 0).astype(np.float64))
    w = (1.0 - smoothstep(depth - 0.01, depth + 0.005, -hb)) * (x > 0) * near
    w = smooth(w[:, None], np.ones(len(SV)), E, 2)[:, 0] * near
    fill = lin.copy()
    if skin.any():
        sel = np.nonzero(w > 1e-3)[0]
        fill[sel] = gauss_mean(SV[sel], SV[skin], lin[skin], 0.015)[0]
    n_back = 0
    if head is not None and ear_y is not None:
        HV = world_verts(head)
        hh = HV[:, 2] - z_cut(HV[:, 1])
        hc = scan_colors(head.data)
        hair = (hh > 0) & (hh < 0.025) & (HV[:, 1] > ear_y + 0.01) & (to_lab(hc)[:, 0] < 25)
        if hair.sum() > 20:
            hair_lin = np.median(to_linear(hc[hair]), 0)
            behind = smoothstep(ear_y + 0.005, ear_y + 0.025, SV[:, 1])
            end = 0.03 + 0.012 * (value_noise(SV, 0.02, 11) - 0.5)
            wb = behind * (1.0 - smoothstep(end - 0.012, end, -hb)) * column(SV) * (hb < 1e-5) * (hb > -0.05)
            wb = smooth(wb[:, None], np.ones(len(SV)), E, 2)[:, 0] * column(SV) * (hb < 1e-5)
            wb *= ~skin
            sel = wb > 1e-3
            tot = np.maximum(w + wb, 1e-9)
            fill[sel] = (fill[sel] * w[sel, None] + hair_lin * wb[sel, None]) / tot[sel, None]
            w = np.maximum(w, wb)
            n_back = int((wb > 0.5).sum())
    ca = me.color_attributes.new("scan_fill", 'FLOAT_COLOR', 'POINT')
    ca.data.foreach_set("color", np.hstack([np.clip(fill, 0, 1), np.ones((len(SV), 1))]).astype(np.float32).ravel())
    ga = me.color_attributes.new("scan_gain", 'FLOAT_COLOR', 'POINT')
    ga.data.foreach_set("color", np.ones((len(SV), 4), np.float32).ravel())
    wa = me.attributes.new("scan_fill_w", 'FLOAT', 'POINT')
    wa.data.foreach_set("value", w.astype(np.float32))
    band = poly_mean(me, (w > 1e-3).astype(np.float64)) > 0
    mi = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mi)
    src = me.materials[0]
    if not band.any() or (mi[band] != 0).any():
        log("body scan: neck band under the seam not filled (no skin there, or more than one material)")
        return 0
    img = base_color_image(src)
    mat = src.copy()
    mat.name = src.name + "_fill"
    mat["scan_fill_image"] = img.name if img else ""
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    sock = lambda node, ident: next(x for x in list(node.inputs) + list(node.outputs) if x.identifier == ident)
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    col = nt.nodes.new('ShaderNodeVertexColor')
    col.layer_name = "scan_fill"
    wn = nt.nodes.new('ShaderNodeAttribute')
    wn.attribute_name = "scan_fill_w"
    if bsdf.inputs["Base Color"].links:
        nt.links.new(bsdf.inputs["Base Color"].links[0].from_socket, sock(mix, "A_Color"))
    else:
        sock(mix, "A_Color").default_value = bsdf.inputs["Base Color"].default_value
    nt.links.new(col.outputs["Color"], sock(mix, "B_Color"))
    nt.links.new(wn.outputs["Fac"], sock(mix, "Factor_Float"))
    nt.links.new(sock(mix, "Result_Color"), bsdf.inputs["Base Color"])
    me.materials.append(mat)
    mi[band] = len(me.materials) - 1
    me.polygons.foreach_set("material_index", mi)
    me.update()
    log(f"body scan: its neck under the seam ({int((w > 0.5).sum())} vertices, {int(band.sum())} faces, skin only) "
        f"smoothed over 1.5 cm" + (f"; behind the ears {n_back} vertices of its hood take the head scan's hair colour"
                                   if head is not None else ""))
    return int(band.sum())


def fill_colours(me, mat, base):
    """scan_colors for fill_neck's material: the texture colours (base, sRGB) toned by its gain and mixed with its fill
    by its weight, as the material does (in linear RGB)."""
    ca, wa, ga = me.color_attributes.get("scan_fill"), me.attributes.get("scan_fill_w"), me.color_attributes.get("scan_gain")
    if ca is None or wa is None:
        return base
    n = len(me.vertices)
    fill = np.empty(n * 4, np.float32)
    ca.data.foreach_get("color", fill)
    fill = np.clip(fill.reshape(-1, 4)[:, :3].astype(np.float64), 0, 1)
    gain = np.ones((n, 3))
    if ga is not None:
        g = np.empty(n * 4, np.float32)
        ga.data.foreach_get("color", g)
        gain = g.reshape(-1, 4)[:, :3].astype(np.float64)
    w = np.empty(n, np.float32)
    wa.data.foreach_get("value", w)
    lin = to_linear(base) * gain
    return to_srgb(lin + w[:, None].astype(np.float64) * (fill - lin))


def nearest_on_segments(P, A, B):
    """Nearest point of each P on a set of segments A-B, and its distance."""
    out, dist = np.zeros_like(P), np.full(len(P), np.inf)
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-18)
    for s in range(0, len(P), 512):
        p = P[s:s + 512, None, :]
        t = np.clip(((p - A[None]) * AB[None]).sum(-1) / L2[None], 0, 1)
        Q = A[None] + t[..., None] * AB[None]
        d = np.linalg.norm(p - Q, axis=-1)
        k = d.argmin(1)
        out[s:s + 512] = Q[np.arange(len(k)), k]
        dist[s:s + 512] = d[np.arange(len(k)), k]
    return out, dist


def close_in(scan, SV, ring, H, z_cut, column):
    """Move the body scan's seam edge onto the head scan's (H: its seam points) round the neck's axis: at each angle
    the edge's distance from the axis becomes the head scan's, and the body's band under the seam follows, fully at
    the seam, not at all BODY_BAND down (never inside the head scan's neck). Returns the new points and how far the
    edge moved at most."""
    if not len(ring) or not len(H):
        return SV, 0.0
    c = H[:, :2].mean(0)

    def polar(P):
        d = P[:, :2] - c
        return np.arctan2(d[:, 1], d[:, 0]), np.linalg.norm(d, axis=1)
    ah, rh = polar(H)
    oh = np.argsort(ah)
    rv = np.unique(ring)
    ab, rb = polar(SV[rv])
    ob = np.argsort(ab)

    def r_head(a):
        return np.interp(a, ah[oh], rh[oh], period=2 * np.pi)

    def r_body(a):
        return np.interp(a, ab[ob], rb[ob], period=2 * np.pi)
    h = SV[:, 2] - z_cut(SV[:, 1])
    sel = np.nonzero((h > -BODY_BAND) & (h < 1e-5) & column(SV))[0]
    a, r = polar(SV[sel])
    dr = np.clip(r_head(a) - r_body(a), -0.06, 0.06)
    w = 1.0 - smoothstep(0.0, BODY_BAND, -h[sel])
    r2 = r + w * dr
    r2 = np.where(dr < 0, np.maximum(r2, np.minimum(r, r_head(a))), r2)
    P = SV.copy()
    P[sel, 0] = c[0] + np.cos(a) * r2
    P[sel, 1] = c[1] + np.sin(a) * r2
    edge = np.isin(sel, rv)
    P[sel[edge], 2] = z_cut(P[sel[edge], 1])          # the edge stays on the seam
    set_world_verts(scan, P)
    return P, float(np.abs(r2 - r)[edge].max()) if edge.any() else 0.0


def splice_head(scan, basemesh, lms, path, root, work):
    """Put a head scan in place of the body scan's head: placed by its face landmarks (a similarity; a rigid ICP on
    the skin round the ears may refine it if the face landmarks agree) and turned so its face looks straight ahead,
    decimated, both cut along neck_cut, the head scan kept to its head (its hood cut loose by the seam goes), its neck
    blended onto the body scan's over HEAD_BAND above the seam (its edge lands on the body's), both necks' colours made
    to meet (fill_neck, fill_body_band), and joined into the one scan object; both keep their materials. The joined
    scan keeps the body scan's normalisation; its face landmarks (scan_landmarks) are the head scan's."""
    head, hl = load_head_scan(path, work, root)
    face, column, axis = head_regions(lms)
    z_cut = neck_cut(lms)
    # 1. face landmarks, twice: the second time seen from the front as the body scan's face was; in between it is
    #    decimated
    M, r, keep = landmark_fit(hl, lms)
    head.data.transform(Matrix(M.tolist()))
    head.data.update()
    hi = head.copy()
    hi.data = head.data.copy()
    bpy.context.scene.collection.objects.link(hi)
    hi.name = "head_scan_full"
    decimate_head(head, lms, head_density(scan, z_cut, column)[0])
    L = np.array(list(lms.values()))
    hl = head_view(head, work, root, (float(L[:, 0].mean()), 0.0, float(L[:, 2].mean())), float(np.ptp(L[:, 0])))
    M, r, keep = landmark_fit(hl, lms)
    head.data.transform(Matrix(M.tolist()))
    head.data.update()
    hi.data.transform(Matrix(M.tolist()))
    log(f"head scan -> body scan by {int(keep.sum())} of {len(keep)} face landmarks: scale "
        f"x{np.cbrt(np.linalg.det(M[:3, :3])):.4f}, residual median {np.median(r[keep]) * 1000:.1f} mm, max "
        f"{r[keep].max() * 1000:.1f} mm; {int((~keep).sum())} dropped"
        + (f" (median {np.median(r[~keep]) * 1000:.1f} mm)" if (~keep).any() else ""))
    hl = {k: apply_matrix(M, p[None])[0] for k, p in hl.items()}
    # 2. rigid ICP on the skin round the ears, checked against the face landmarks
    Mi = icp_head(head, scan, lms, hl, z_cut)
    head.data.transform(Matrix(Mi.tolist()))
    head.data.update()
    hi.data.transform(Matrix(Mi.tolist()))
    hl = {k: apply_matrix(Mi, p[None])[0] for k, p in hl.items()}
    # 2b. the face straight ahead. The landmark fit hardly fixes the turn of the head (the two faces' depths differ by
    #     more than a few degrees make), and the portrait behind a head scan is often turned a little: left as it is,
    #     the character's head looks aside on its own neck and every side-dependent step comes out one-sided. Turned
    #     about the vertical half way between its face and its neck, so neither moves far from the body scan's
    yaw, npair = face_yaw(hl)
    yaw_b, _ = face_yaw(lms)
    if abs(yaw) > 0.5:
        Lh = np.array(list(hl.values()))
        piv = (Lh.mean(0) + np.array([axis[0], axis[1], Lh[:, 2].mean()])) / 2
        Mz = np.array(Matrix.Translation(Vector(piv)) @ Matrix.Rotation(math.radians(-yaw), 4, 'Z')
                      @ Matrix.Translation(-Vector(piv)))
        head.data.transform(Matrix(Mz.tolist()))
        head.data.update()
        hi.data.transform(Matrix(Mz.tolist()))
        hl = {k: apply_matrix(Mz, p[None])[0] for k, p in hl.items()}
    log(f"head scan face turned {yaw:+.1f} deg from straight ahead ({npair} landmark pairs; the body scan's "
        f"{yaw_b:+.1f})" + (": turned back" if abs(yaw) > 0.5 else "") + f", now {face_yaw(hl)[0]:+.1f}")
    SV, HV = world_verts(scan), world_verts(head)
    ST = triangles(scan.data)
    bvh = BVHTree.FromPolygons(SV.tolist(), ST.tolist(), all_triangles=True)
    above = (HV[:, 2] > z_cut(HV[:, 1]) + 0.01) & column(HV)
    d = [bvh.find_nearest(Vector(p), 0.1)[3] for p in HV[above]]
    d = np.array([0.1 if x is None else x for x in d])          # None: nothing within 10 cm
    fm = face(HV[above])
    log(f"head scan vs body scan above the seam: face median {np.median(d[fm]) * 1000:.2f} mm, 95% "
        f"{np.percentile(d[fm], 95) * 1000:.2f} mm; rest median {np.median(d[~fm]) * 1000:.2f} mm, 95% "
        f"{np.percentile(d[~fm], 95) * 1000:.2f} mm")
    # 3. cut: the body scan loses its head (within the head's column), the head scan its shoulders and its hood
    near = ST[(np.abs(SV[ST][:, :, 2] - z_cut(SV[ST][:, :, 1])) < HEAD_BAND + 0.03).any(1)]
    ref = BVHTree.FromPolygons(SV.tolist(), near.tolist(), all_triangles=True)    # the body's neck, uncut
    n_body = len(scan.data.vertices)
    ring = cut_at(scan, z_cut, keep_above=False, column=column)
    cut_at(head, z_cut, keep_above=True)
    keep_head_pieces(head, lms, z_cut, axis)
    cut_at(hi, z_cut, keep_above=True)
    keep_head_pieces(hi, lms, z_cut, axis, quiet=True)
    SV, HV = world_verts(scan), world_verts(head)
    A, B = SV[ring[:, 0]], SV[ring[:, 1]]
    # 4. the blend band: the head scan's neck moves onto the body scan's, fully at the seam, not at all HEAD_BAND up
    hb = bmesh.new()
    hb.from_mesh(head.data)
    edge_ring = np.array([v.is_boundary for v in hb.verts])
    hb.free()
    h = HV[:, 2] - z_cut(HV[:, 1])
    band = np.nonzero(h < HEAD_BAND)[0]
    on_seam = edge_ring & (np.abs(h) < 1e-5)
    D = np.zeros_like(HV)
    conf = np.zeros(len(HV))
    for i in band:
        if on_seam[i]:
            continue
        loc, _, _, dist = ref.find_nearest(Vector(HV[i]), HEAD_REACH)
        if loc is not None:
            D[i], conf[i] = np.array(loc) - HV[i], 1.0
    seam = np.nonzero(on_seam)[0]
    if len(seam) and len(A):
        Q, dq = nearest_on_segments(HV[seam], A, B)
        hit = dq < HEAD_REACH
        D[seam[hit]], conf[seam[hit]] = Q[hit] - HV[seam[hit]], 1.0
    E = edges(head.data)
    E = E[np.isin(E, band).all(1)]
    Ds = smooth(D, conf, E, 4, lam=0.5)
    Ds[seam] = D[seam]
    w = 1.0 - smoothstep(0.0, HEAD_BAND, h)
    w[h >= HEAD_BAND] = 0.0
    HV0 = HV.copy()
    HV = HV + w[:, None] * Ds
    set_world_verts(head, HV)
    Vf = world_verts(hi)
    carry(hi, HV0, HV - HV0, sel=Vf[:, 2] - z_cut(Vf[:, 1]) < HEAD_BAND + 0.005)
    # 4b. the body side: where its edge stands off the head scan's (the hood's outside at the back, a few cm behind
    #     the head scan's nape), its band under the seam closes in round the neck's axis onto the head scan's edge
    SV, moved = close_in(scan, SV, ring, HV[seam], z_cut, column)
    A, B = SV[ring[:, 0]], SV[ring[:, 1]]
    seam_full(hi, A, B, z_cut)
    fill_body_band(scan, z_cut, column, head=head, ear_y=float(np.mean([lms[i][1] for i in EARS if i in lms]
                                                                     or [axis[1] - 0.02])))
    fill_neck(head, lms, scan, ring, z_cut, work, hi=hi)
    # how well the two edges meet: each side's seam vertices against the other side's seam edges
    hr = np.array([(a, b) for a, b in edges(head.data) if on_seam[a] and on_seam[b]], np.int64).reshape(-1, 2)
    gap_h = nearest_on_segments(HV[seam], A, B)[1] if len(seam) and len(A) else np.zeros(1)
    gap_b = nearest_on_segments(SV[np.unique(ring)], HV[hr[:, 0]], HV[hr[:, 1]])[1] if len(hr) else np.full(1, np.inf)
    log(f"head scan spliced under the jaw (seam {z_cut(axis[1] - 0.1):.3f} m in front, {z_cut(axis[1] + 0.05):.3f} m "
        f"behind): body scan {n_body} -> {len(SV)} verts, head scan {len(HV)} verts, {len(head.data.polygons)} faces; "
        f"band moved {np.linalg.norm(Ds[band] * w[band, None], axis=1).mean() * 1000:.1f} mm on average, the body's "
        f"edge up to {moved * 1000:.1f} mm; seam gap "
        f"head->body max {gap_h.max() * 1000:.2f} mm ({int((gap_h > 0.002).sum())} of {len(gap_h)} head seam points "
        f"over 2 mm), body->head median {np.median(gap_b) * 1000:.2f} mm, max {gap_b.max() * 1000:.2f} mm "
        f"({int((gap_b > 0.002).sum())} of {len(gap_b)} body seam points open)")
    # 5. one object, both materials (the colour bake reads each side's own texture)
    n_mat = len(scan.data.materials)
    if scan.data.uv_layers.active and head.data.uv_layers.active:
        head.data.uv_layers.active.name = scan.data.uv_layers.active.name
    bpy.ops.object.select_all(action='DESELECT')
    head.select_set(True)
    scan.select_set(True)
    bpy.context.view_layer.objects.active = scan
    n0 = len(scan.data.vertices)
    bpy.ops.object.join()
    scan.data["head_mat0"] = n_mat
    # the full head scan stays beside it, the source of the bakes (bake_source)
    scan["head_full"] = hi.name
    HEAD_FULL[hi.name] = (n0, world_verts(scan)[n0:].copy())
    SEAM.update(z_cut=z_cut, ear_y=float(np.mean([lms[i][1] for i in EARS if i in lms] or [axis[1] - 0.02])))
    hi.hide_render = True
    return scan_landmarks(scan, work, root)


def drop_scan_ears(hi, basemesh, in_body, thick=0.012, reach=0.035):
    """The head scan's own ears leave the full head scan the bakes read: flatter and nearer the head than the
    character's ears (turned only half way to them, flatten_ears), they lie on its skin beside them, and the bake's
    rays found them: the skin under each lobe took the scan's lobe (a pale second earlobe with a dark outline under
    it). An ear is a flap: from its skin-coloured surface within `reach` of the character's ears, a ray into it comes
    out of its other side within `thick` (from a cheek it runs on into the head). Those faces go; the character's ears
    keep their own skin anyway (ear_mask), and the skin round them now bakes from the head scan's skin behind its ears
    or, where nothing is there, is filled from round about (scan_compose)."""
    ears = ear_group(basemesh, in_body)
    if not ears.any():
        return 0
    Vb = world_verts(basemesh)
    kd = KDTree(int(ears.sum()))
    for j, p in enumerate(Vb[ears].tolist()):
        kd.insert(p, j)
    kd.balance()
    me = hi.data
    V = world_verts(hi)
    T = triangles(me)
    N = vertex_normals(V, T)
    bvh = BVHTree.FromPolygons(V.tolist(), T.tolist(), all_triangles=True)
    lo, hi_ = Vb[ears].min(0) - reach, Vb[ears].max(0) + reach
    cand = np.nonzero(((V > lo) & (V < hi_)).all(1))[0]
    skin = to_lab(scan_colors(me))[:, 0] > 25
    flap = np.zeros(len(V), bool)
    for i in cand:
        if not skin[i] or kd.find(V[i])[2] > reach:
            continue
        n = Vector(N[i])
        loc, _, _, _ = bvh.ray_cast(Vector(V[i]) - n * 0.0003, -n, thick)
        flap[i] = loc is not None
    fv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", fv)
    ls = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    gone = np.minimum.reduceat(flap[fv].astype(np.int8), ls) > 0
    if gone.any():
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(gone)[0]], context='FACES_ONLY')
        bm.to_mesh(me)
        bm.free()
        me.update()
    log(f"bakes: the head scan's own ears left out ({int(gone.sum())} faces of thin skin by the character's ears)")
    return int(gone.sum())


def seam_full(hi, A, B, z_cut, band=0.012):
    """The full head scan's cut edge onto the body scan's (segments A-B), the skin above it following over `band`: it
    came with the decimated head scan's edge only roughly (its neck carried by the nearest decimated vertices, whose cut
    runs a few millimetres off the full surface's), and the bakes' rays went through the gaps into the body scan's
    inside (a dotted dark line along the seam at the back of the neck)."""
    if not len(A):
        return
    me = hi.data
    V = world_verts(hi)
    h = V[:, 2] - z_cut(V[:, 1])
    bm = bmesh.new()
    bm.from_mesh(me)
    edge = np.array([v.is_boundary for v in bm.verts])
    bm.free()
    seam = np.nonzero(edge & (np.abs(h) < 1e-4))[0]
    if not len(seam):
        return
    Q, dq = nearest_on_segments(V[seam], A, B)
    ok = dq < HEAD_REACH
    seam, D = seam[ok], (Q - V[seam])[ok]
    if not len(seam):
        return
    kd = KDTree(len(seam))
    for j, p in enumerate(V[seam].tolist()):
        kd.insert(p, j)
    kd.balance()
    near = np.nonzero((h > -1e-4) & (h < band))[0]
    out = V.copy()
    for i in near:
        hits = kd.find_n(V[i], 4)
        w = np.array([1.0 / (x[2] + 1e-4) ** 2 for x in hits])
        out[i] = V[i] + (1.0 - smoothstep(0.0, band, h[i])) * (w[:, None] * D[[x[1] for x in hits]]).sum(0) / w.sum()
    out[seam] = V[seam] + D
    set_world_verts(hi, out)


SEAM = {}               # the head scan's seam (z_cut) and its ears' depth, for the passes after the bake


def _corner_frames(obj):
    """Per corner (loop) of obj's mesh, its tangent frame as Blender bakes a normal map and the game reads one
    (MikkTSpace in the active UV map; world space): (loops, 3, 3), columns tangent, bitangent, normal. Per corner, not
    per vertex: a vertex on a UV seam (the body's down the back of the neck, the head texture's edge, the hood lining's
    islands) has one frame per side (summed per vertex, the turned normals draw a light seam down the nape, a stepped
    edge along the head's material and coloured borders round the lining's islands)."""
    me = obj.data
    n = len(me.loops)
    N = np.empty(n * 3, np.float32)
    me.loops.foreach_get("normal", N)
    try:
        me.calc_tangents(uvmap=me.uv_layers.active.name)
        T = np.empty(n * 3, np.float32)
        me.loops.foreach_get("tangent", T)
        S = np.empty(n, np.float32)
        me.loops.foreach_get("bitangent_sign", S)
        me.free_tangents()
    except RuntimeError:
        # (n-gons: per UV wedge, the triangles' UV tangents summed by their corner angles)
        me.calc_loop_triangles()
        lt_v = np.empty(len(me.loop_triangles) * 3, np.int64)
        me.loop_triangles.foreach_get("vertices", lt_v)
        lt_l = np.empty(len(me.loop_triangles) * 3, np.int64)
        me.loop_triangles.foreach_get("loops", lt_l)
        lt_v, lt_l = lt_v.reshape(-1, 3), lt_l.reshape(-1, 3)
        co = np.empty(len(me.vertices) * 3, np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        uv_ = np.empty(n * 2, np.float64)
        me.uv_layers.active.data.foreach_get("uv", uv_)
        uv_ = uv_.reshape(-1, 2)
        e1, e2 = co[lt_v[:, 1]] - co[lt_v[:, 0]], co[lt_v[:, 2]] - co[lt_v[:, 0]]
        d1, d2 = uv_[lt_l[:, 1]] - uv_[lt_l[:, 0]], uv_[lt_l[:, 2]] - uv_[lt_l[:, 0]]
        det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
        inv_ = np.where(np.abs(det) > 1e-14, 1.0 / np.where(np.abs(det) > 1e-14, det, 1.0), 0.0)
        Tt = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * inv_[:, None]
        Bt = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * inv_[:, None]
        lv = np.empty(n, np.int64)
        me.loops.foreach_get("vertex_index", lv)
        key = np.unique(np.stack([lv, np.round(uv_[:, 0] * 1e6), np.round(uv_[:, 1] * 1e6)], 1), axis=0,
                        return_inverse=True)[1].ravel()
        Tw = np.zeros((key.max() + 1, 3))
        Bw = np.zeros((key.max() + 1, 3))
        for k_ in range(3):
            a_ = co[lt_v[:, (k_ + 1) % 3]] - co[lt_v[:, k_]]
            b_ = co[lt_v[:, (k_ + 2) % 3]] - co[lt_v[:, k_]]
            ang = np.arccos(np.clip((a_ * b_).sum(1) / np.maximum(np.linalg.norm(a_, axis=1) *
                                                                  np.linalg.norm(b_, axis=1), 1e-12), -1, 1))
            np.add.at(Tw, key[lt_l[:, k_]], Tt * ang[:, None])
            np.add.at(Bw, key[lt_l[:, k_]], Bt * ang[:, None])
        Nl = N.reshape(-1, 3).astype(np.float64)
        T = Tw[key] - Nl * (Tw[key] * Nl).sum(1, keepdims=True)
        S = np.sign((np.cross(Nl, T) * Bw[key]).sum(1) + 1e-12).astype(np.float32)
        T = T.astype(np.float32).ravel()
    R = np.array(obj.matrix_world)[:3, :3]
    R = R / np.maximum(np.linalg.norm(R, axis=0, keepdims=True), 1e-12)
    T = T.reshape(-1, 3).astype(np.float64) @ R.T
    N = N.reshape(-1, 3).astype(np.float64) @ R.T
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    B = S.astype(np.float64)[:, None] * np.cross(N, T)
    return np.stack([T, B, N], 2)


def _corner_texels(basemesh, faces, size, wv=None, box=None):
    """The texels (size x size, active UV map) of the triangles of `faces` (those with a vertex where wv > 1e-4, when
    given; those reaching into box = (y0, y1, x0, x1) texels, when given): ys, xs, each texel's triangle's corners
    (loops, k x 3) and vertices (k x 3), and its barycentric weights."""
    me = basemesh.data
    me.calc_loop_triangles()
    tv = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tv)
    tl = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("loops", tl)
    tp = np.empty(len(me.loop_triangles), np.int64)
    me.loop_triangles.foreach_get("polygon_index", tp)
    tv, tl = tv.reshape(-1, 3), tl.reshape(-1, 3)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    sel = faces[tp].copy()
    if wv is not None:
        sel &= (np.asarray(wv)[tv] > 1e-4).any(1)
    q = uv.reshape(-1, 2)[tl] * size
    if box is not None:
        sel &= (q[:, :, 1].max(1) >= box[0] - 1) & (q[:, :, 1].min(1) <= box[1] + 1) & \
            (q[:, :, 0].max(1) >= box[2] - 1) & (q[:, :, 0].min(1) <= box[3] + 1)
    sel = np.nonzero(sel)[0]
    ys, xs, tt, bb, _ = uv_texels(q[sel], size, size)
    return ys, xs, tl[sel][tt], tv[sel][tt], bb


def _turn_to_abs(rgb, cl, bb, Rc):
    """Normal-map texels (k x 3, 0-1) read in that build's frame, written in this surface's: each turned by its
    triangle's corners' turns Rc (this frame^T x that frame per corner) interpolated."""
    m = rgb.astype(np.float64) * 2.0 - 1.0
    Rk = (bb[:, :, None, None] * Rc[cl]).sum(1)
    out = np.einsum('kij,kj->ki', Rk, m)
    out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)
    return out * 0.5 + 0.5


def _dilate_into(px, done, todo, iters=16, block=None):
    """Spread the values of the texels `done` into the texels `todo` next to them (iters rings; px h x w x c):
    the bake's margin round an island, so mip levels and filtering at its edge read the island's own values. With
    `block` (other islands' texels), a margin texel nearer to one of those (grown ring by ring alongside) is left as it
    is: their margin."""
    out = px.copy()
    have = done.copy()
    blk = block.copy() if block is not None else None
    for _ in range(iters):
        if blk is not None:
            blk = blk | (_bmax(blk, 1) & todo & ~have)
        acc = np.zeros(out.shape, np.float64)
        cnt = np.zeros(have.shape, np.float64)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(have, (dy, dx), (0, 1))
            acc += np.roll(out * have[..., None], (dy, dx), (0, 1))
            cnt += sh
        new = todo & ~have & (cnt > 0)
        if blk is not None:
            new &= ~blk
        if not new.any():
            break
        out[new] = acc[new] / cnt[new][:, None]
        have |= new
    return out


def absent_maps(basemesh, head_faces, in_body, W, names, root, low=(0.012, 0.028), P_abs=None, cloth=None):
    """Head scans: the body's maps a build without the head scan gives it (absent_bake), away from the head and down
    the back of the neck. Below the seam the body scan the bakes read is the one the head scan was spliced into: its
    hood behind the neck pulled in onto the head scan's neck (close_in) and darkened like its hair (fill_body_band),
    its neck smoothed. Baked from that, the hood's top behind the neck comes out as a pale grey patch with stepped
    edges and the nape as a patchwork of pale patches and bare skin strips; in the build without the head scan the
    nape is the body scan's dark hair down to the hood. The body's cloth (`cloth`, per face, as that build classifies
    it) takes that build's colour, normal and roughness maps as they are, every texel and the islands' margins: its
    normals turned to this surface would light the hood's lining beside the neck as pale hard-edged patches at every
    side and three-quarter dialogue camera. Its skin takes them below `low` under the seam (fading in from low[0]) and
    on the back and sides of the neck behind the ears' front (fading out over 1.6 cm towards it; up to 1 cm over the
    ears' tops behind them, the ears' middle under them; not the ears), and so do the head's faces there within 2 cm
    of the body's (fading out up them) and its nape: one weight per vertex for both materials, so they meet without an
    edge. Behind the ears the normals are turned into this surface's frame (corner by corner: that build's tangent
    frame read into this one's, at most 60 deg): read as they are, on the head scan's slimmer neck they light as a
    grey sheen down the nape. In front of the ears the neck's skin keeps the head scan's colour up to the head's
    material and the template's smooth normals both sides of it, the body's fading into that build's normals as they
    are from 4 mm to 2 cm under it (with that build's normals on one side and this build's on the other, the edge
    between the two materials drew polygon patches and a stepped seam on both sides of the neck)."""
    am = json.loads(basemesh.get("scan_abs_maps", "{}") or "{}")
    if not am or not os.path.exists(am.get("color", "")):
        return
    A = anchor_points(basemesh, root)
    V = world_verts(basemesh)
    z_cut = neck_cut(A)              # the seam on the character's own landmarks
    h = V[:, 2] - z_cut(V[:, 1])
    w_low = 1.0 - smoothstep(-low[1], -low[0], h)
    neck = in_body & (W[:, names.index("neck_01")] > 0.5)
    cy = float(V[neck, 1].mean()) if neck.any() else float(np.mean([A[i][1] for i in EARS if i in A]))
    mid = float(V[neck, 0].mean()) if neck.any() else float(V[in_body, 0].mean())
    eg = ear_group(basemesh, in_body)
    if eg.any():
        ear_front, ear_back = float(np.percentile(V[eg, 1], 5)), float(np.percentile(V[eg, 1], 95))
        z_mid, z_et = float(np.percentile(V[eg, 2], 50)), float(np.percentile(V[eg, 2], 95))
    else:
        ear_front, ear_back = cy - 0.03, cy
        z_mid = z_et = float(z_cut(cy)) + 0.06
    # behind the ears' front (the throat and the jaw stay the head scan's)
    w_y = smoothstep(ear_front + 0.002, ear_front + 0.018, V[:, 1])
    # up to 1 cm over the ears' tops behind them (under the hair: the head scan paints a grey wash there), the ears'
    # middle under them
    behind = smoothstep(ear_back - 0.01, ear_back + 0.005, V[:, 1])
    z_hi = z_mid + behind * (z_et + 0.01 - z_mid)
    w_up = 1.0 - smoothstep(z_hi - 0.02, z_hi + 0.005, V[:, 2])
    # (not the ears: from 1.5 mm off them; from 4 mm, the head scan's skin stands as a pale strip behind each ear down
    # the side of the neck)
    away = smoothstep(0.0015, 0.006, nearest_landmark(V, V[eg])) if eg.any() else np.ones(len(V))
    z_top = z_et + 0.01
    E = edges(basemesh.data)
    E = E[in_body[E].all(1)]
    # (smoothed over 8 rings, the ears kept out after: over 2, the copied normals' edge in front of the ears drew a
    # polygon outline along the triangles on the side of the neck under a key light)
    w = smooth((np.maximum(w_low, w_y * w_up * away) * in_body)[:, None], np.ones(len(V)), E, 8)[:, 0] * in_body * away
    wb = smooth((w_y * in_body)[:, None], np.ones(len(V)), E, 4)[:, 0] * in_body
    body_f = poly_mean(basemesh.data, in_body.astype(np.float64)) > 0.999
    cloth_f = np.zeros(len(body_f), bool) if cloth is None else (np.asarray(cloth) > 0)
    skin_f = body_f & ~head_faces & ~cloth_f
    hv0 = np.zeros(len(V), bool)
    bv0 = np.zeros(len(V), bool)
    for poly in basemesh.data.polygons:
        if head_faces[poly.index]:
            hv0[list(poly.vertices)] = True
        elif body_f[poly.index]:
            bv0[list(poly.vertices)] = True
    edge_v = hv0 & bv0 & in_body
    d_b = nearest_landmark(V, V[edge_v]) if edge_v.any() else np.full(len(V), 1.0)
    ramp = (1.0 - smoothstep(0.004, 0.02, d_b)) * in_body
    # one weight for both materials (that build's maps): behind the ears its maps, on the head's faces fading out
    # within 2 cm of the body's (and down the nape as far as w reaches); in front of the ears, the body's below the
    # seam only, from 4 mm to 2 cm under the head's material
    a_back = np.maximum(w, ramp) * away * in_body
    a_front = w * smoothstep(0.004, 0.02, d_b)
    A_body = a_front + wb * (a_back - a_front)
    A_head = wb * a_back
    # (only the neck: from 5 to 8 cm under the seam down every texel is that build's, normals and margins included)
    Z = smoothstep(-0.08, -0.05, h) * in_body
    # behind the ears the body's faces lie on the head scan's neck (3 cm further in at the nape than the body scan's),
    # where that build's lie on the body scan's nape and on its hood's lining rising beside the neck: their normals are
    # turned into this surface's frame, cloth and skin alike, so they light as that build's do. As they are, the
    # lining's faces beside the neck light as pale hard-edged panels in the game's side views, and the nape's cloth
    # patches as lighter panels between the turned skin (the frames are per corner: per-vertex frames give facets and
    # coloured island borders)
    tb = wb
    tw_cloth = Z * tb
    # that build's tangent frames (its surface: the body at P_abs) against this one's, per corner
    Rc, turn_ok = None, None
    if P_abs is not None:
        me_a = basemesh.data.copy()
        tmp = bpy.data.objects.new("abs_frames", me_a)
        bpy.context.scene.collection.objects.link(tmp)
        tmp.matrix_world = basemesh.matrix_world.copy()
        set_world_verts(tmp, P_abs, in_body)
        Fa = _corner_frames(tmp)
        bpy.data.objects.remove(tmp)
        bpy.data.meshes.remove(me_a)
        Fb = _corner_frames(basemesh)
        Rc = np.einsum('lki,lkj->lij', Fb, Fa)
        # (turns over 85 deg cut back to 85 about their own axis: set back to none, or cut back to 60, those corners'
        # triangles light as lighter hard-edged panels on the nape, where the head scan's neck stands 3 cm further in
        # than the body scan's)
        ang = np.arccos(np.clip((np.trace(Rc, axis1=1, axis2=2) - 1.0) / 2.0, -1.0, 1.0))
        most = math.radians(85.0)
        turn_ok = ang <= most
        big = np.nonzero(~turn_ok)[0]
        if len(big):
            Rb = Rc[big]
            ax = np.stack([Rb[:, 2, 1] - Rb[:, 1, 2], Rb[:, 0, 2] - Rb[:, 2, 0], Rb[:, 1, 0] - Rb[:, 0, 1]], 1)
            ax /= np.maximum(np.linalg.norm(ax, axis=1, keepdims=True), 1e-9)
            K = np.zeros((len(big), 3, 3))
            K[:, 0, 1], K[:, 0, 2], K[:, 1, 2] = -ax[:, 2], ax[:, 1], -ax[:, 0]
            K[:, 1, 0], K[:, 2, 0], K[:, 2, 1] = ax[:, 2], -ax[:, 1], ax[:, 0]
            Rc[big] = np.eye(3)[None] + math.sin(most) * K + (1.0 - math.cos(most)) * np.einsum('kij,kjl->kil', K, K)
    mat = basemesh.active_material
    nt = mat.node_tree
    col_node = next(n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image and
                    not any(l.to_node.type in ('NORMAL_MAP', 'BUMP') for o in n.outputs for l in o.links))
    nrm_node = next((n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image and
                     any(l.to_node.type == 'NORMAL_MAP' for o in n.outputs for l in o.links)), None)
    rough = bpy.data.images.get(basemesh.get("scan_rough", ""))
    jobs = [(col_node.image, am["color"], "color")]
    if nrm_node is not None:
        jobs.append((nrm_node.image, am["normal"], "normal"))
    if rough is not None:
        jobs.append((rough, am["rough"], "rough"))
    turns = []
    n_skin = n_kept = n_cloth_t = 0
    for img, apath, kind in jobs:
        size = img.size[0]
        aimg = bpy.data.images.load(apath, check_existing=False)
        if aimg.size[0] != size:
            aimg.scale(size, size)
        apx = np.empty(size * size * 4, np.float32)
        aimg.pixels.foreach_get(apx)
        bpy.data.images.remove(aimg)
        apx = apx.reshape(size, size, 4)
        px = np.empty(size * size * 4, np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(size, size, 4)
        # the body's skin near the head: this build's own where A_body < 1 (colour), the turned or flat normals
        ys, xs, cl, cv, bb = _corner_texels(basemesh, skin_f, size, wv=Z)
        a = (bb * A_body[cv]).sum(1)
        zt = (bb * Z[cv]).sum(1)
        if kind == "normal":
            wbt = (bb * wb[cv]).sum(1)
            af = (bb * a_front[cv]).sum(1)
            ab = (bb * a_back[cv]).sum(1)
            flat = np.array([0.5, 0.5, 1.0])
            ab_n = apx[ys, xs, :3].astype(np.float64)
            n_front = flat + af[:, None] * (ab_n - flat)
            tn = _turn_to_abs(ab_n, cl, bb, Rc) if Rc is not None else ab_n
            # (turned on the back of the neck only; on its sides behind the ears that build's as they are: the skin
            # there wears the hood's dark lining in that build's colour, and turned it lights as pale hard-edged
            # patches at every side dialogue camera)
            tbt = (bb * tb[cv]).sum(1)
            tn = ab_n + tbt[:, None] * (tn - ab_n)
            own = px[ys, xs, :3].astype(np.float64)
            n_back = own + ab[:, None] * (tn - own)
            v = n_front + wbt[:, None] * (n_back - n_front)
            v = v * 2.0 - 1.0
            v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
            val = v * 0.5 + 0.5
            if Rc is not None:
                ang = np.degrees(np.arccos(np.clip((((tn * 2 - 1) * (ab_n * 2 - 1)).sum(1)) /
                                                   np.maximum(np.linalg.norm(ab_n * 2 - 1, axis=1), 1e-9), -1, 1)))
                turns.append(ang[(wbt > 0.5) & (ab > 0.5) & (tbt > 0.5)])
        else:
            val = px[ys, xs, :3] + a[:, None] * (apx[ys, xs, :3] - px[ys, xs, :3])
        val = apx[ys, xs, :3] + zt[:, None] * (val - apx[ys, xs, :3])
        own_t = np.zeros((size, size), bool)
        own_t[ys, xs] = True
        out = apx.copy()
        out[ys, xs, :3] = val
        out[ys, xs, 3] = px[ys, xs, 3]
        if kind == "normal" and Rc is not None:
            cy_, cx_, ccl, ccv, cbb = _corner_texels(basemesh, cloth_f & body_f & ~head_faces, size, wv=tw_cloth)
            if len(cy_):
                tw_ = (cbb * tw_cloth[ccv]).sum(1)
                ab_c = apx[cy_, cx_, :3].astype(np.float64)
                vc = ab_c + tw_[:, None] * (_turn_to_abs(ab_c, ccl, cbb, Rc) - ab_c)
                vc = vc * 2.0 - 1.0
                vc /= np.maximum(np.linalg.norm(vc, axis=1, keepdims=True), 1e-9)
                sel_c = tw_ > 0.002
                out[cy_[sel_c], cx_[sel_c], :3] = vc[sel_c] * 0.5 + 0.5
                own_t[cy_[sel_c], cx_[sel_c]] = True
                n_cloth_t = int((tw_ > 0.5).sum())
                ys = np.concatenate([ys, cy_[sel_c]])
                xs = np.concatenate([xs, cx_[sel_c]])
        # (the margin round those texels from them; every other texel, the islands' margins included, that build's)
        if own_t.any():
            y0, y1 = max(ys.min() - 20, 0), min(ys.max() + 21, size)
            x0, x1 = max(xs.min() - 20, 0), min(xs.max() + 21, size)
            cov = np.zeros((size, size), bool)
            cys, cxs, _, _, _ = _corner_texels(basemesh, body_f & ~head_faces, size, box=(y0, y1, x0, x1))
            cov[cys, cxs] = True
            # (only the neck skin's own margin: the cloth islands' margins next to it stay that build's)
            sub = _dilate_into(out[y0:y1, x0:x1, :3].astype(np.float64), own_t[y0:y1, x0:x1], ~cov[y0:y1, x0:x1],
                               block=cov[y0:y1, x0:x1] & ~own_t[y0:y1, x0:x1])
            out[y0:y1, x0:x1, :3] = sub
        img.pixels.foreach_set(out.ravel())
        img.save()
        if kind == "color":
            n_skin = int(len(ys))
            n_kept = int((a < 0.5).sum())
    # the head's colour and normals near the body and on the nape
    maps = json.loads(basemesh["scan_head_maps"])
    n_head = 0
    for key in ("color", "normal"):
        if not os.path.exists(am.get("head_" + key, "")) or not maps.get(key):
            continue
        img, size, px = _head_img(maps, key)
        ys, xs, cl, cv, bb = _corner_texels(basemesh, head_faces, size, wv=A_head)
        if len(ys):
            aimg = bpy.data.images.load(am["head_" + key], check_existing=False)
            if aimg.size[0] != size:
                aimg.scale(size, size)
            apx = np.empty(size * size * 4, np.float32)
            aimg.pixels.foreach_get(apx)
            bpy.data.images.remove(aimg)
            apx = apx.reshape(size, size, 4)
            a = (bb * A_head[cv]).sum(1)
            src = apx[ys, xs, :3].astype(np.float64)
            if key == "normal" and Rc is not None:
                tbt = (bb * tb[cv]).sum(1)
                src = src + tbt[:, None] * (_turn_to_abs(src, cl, bb, Rc) - src)
            own = px[ys, xs, :3].astype(np.float64)
            v = own + a[:, None] * (src - own)
            if key == "normal":
                v = v * 2.0 - 1.0
                v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
                v = v * 0.5 + 0.5
            px[ys, xs, :3] = v
            n_head = max(n_head, int((a > 0.5).sum()))
        _save_img(img, px, maps[key])
    med = float(np.median(np.concatenate(turns))) if turns and len(np.concatenate(turns)) else 0.0
    log(f"body: the maps of a build without the head scan on its cloth ({int(cloth_f.sum())} faces, as they are but the "
        f"normals of the cloth on the neck behind the ears, turned as the skin's: {n_cloth_t} texels) and on "
        f"its skin below {low[1] * 1000:.0f} mm under the seam and on the back and sides of the neck (behind y "
        f"{ear_front + 0.018:.3f}, the ears' front + 18 mm; up to z {z_top:.3f} behind the ears, {z_mid:.3f} under "
        f"them): {n_skin} texels of the neck's skin set ({n_kept} keep this build's colour), {n_head} of the head's "
        f"colour and normals" + (f" (normals turned into this surface's frame corner by corner behind the ears, median "
                                 f"{med:.0f} deg; {int((~turn_ok).sum())} corners' turns over 85 deg cut back to 85)" if Rc is not None else ""))


HEAD_FULL = {}          # the full head scan's name -> (its first vertex in the joined scan, their places when joined)


def carry(obj, P0, D, sel=None, k=6):
    """Move an object's vertices (or those flagged by sel) as the points P0 near them moved (D): the inverse-distance
    mean of the k nearest's displacements."""
    V = world_verts(obj)
    idx = np.arange(len(V)) if sel is None else np.nonzero(sel)[0]
    if not len(idx) or not len(P0):
        return
    kd = KDTree(len(P0))
    for i, p in enumerate(P0.tolist()):
        kd.insert(p, i)
    kd.balance()
    J = np.empty((len(idx), k), np.int64)
    Dd = np.empty((len(idx), k))
    for r, p in enumerate(V[idx].tolist()):
        hits = kd.find_n(p, k)
        J[r] = [h[1] for h in hits]
        Dd[r] = [h[2] for h in hits]
    Wt = 1.0 / (Dd + 1e-4) ** 2
    V[idx] += (Wt[..., None] * D[J]).sum(1) / Wt.sum(1, keepdims=True)
    set_world_verts(obj, V)


def bake_source(scan, basemesh=None, in_body=None):
    """What the bakes read: the joined scan with its head part swapped for the full head scan (moved as the
    decimated one has been since the join: the head fitted to the character's, the re-pose). Decimated 80 times
    outside the face across a scan's atlas of hundreds of small islands, the head scan's triangles spanned several
    islands and read the texture between them: straight-edged shards in the hair and the scalp, the strand direction
    jumping at every triangle edge (the hair cards found no strand flow: coherence 0.24 against 0.82 on a body scan's
    hair), and a hard-edged wedge in the normal map on the neck where a triangle's tangents came from three islands.
    Returns the scan itself without a head scan."""
    name = scan.get("head_full")
    hi = bpy.data.objects.get(name) if name else None
    if hi is None or name not in HEAD_FULL:
        return scan
    n0, P0 = HEAD_FULL[name]
    carry(hi, P0, world_verts(scan)[n0:] - P0)
    if basemesh is not None:
        drop_scan_ears(hi, basemesh, in_body)
    me = scan.data.copy()
    src = bpy.data.objects.new("scan_bake_src", me)
    bpy.context.scene.collection.objects.link(src)
    src.matrix_world = scan.matrix_world.copy()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in range(n0, len(bm.verts))], context='VERTS')
    bm.to_mesh(me)
    bm.free()
    hc = hi.copy()
    hc.data = hi.data.copy()
    bpy.context.scene.collection.objects.link(hc)
    if me.uv_layers.active and hc.data.uv_layers.active:
        hc.data.uv_layers.active.name = me.uv_layers.active.name
    bpy.ops.object.select_all(action='DESELECT')
    hc.select_set(True)
    src.select_set(True)
    bpy.context.view_layer.objects.active = src
    bpy.ops.object.join()
    log(f"bakes read the full head scan ({len(hi.data.polygons)} faces) with the body scan under it")
    return src


def scan_landmarks(scan, work, root):
    """The face landmarks of a normalised scan (a head scan spliced in), as normalise_scan finds them but without
    moving it: normalised again, the joined scan was scaled and shifted by the new face's eyes (0.2 %) and the body
    under the head re-wrapped differently (a shoe 5 cm off, collar faces turned to cloth)."""
    shot = face_landmarks(render_views(scan, work, (0,)), root)[0]
    if not shot["face"]:
        raise RuntimeError("no face found on the front of the scan after splicing the head scan in")
    lms = surface_landmarks(scan, shot)
    log(f"spliced scan: {len(lms)} face landmarks on it (not moved again)")
    return lms


# ------------------------------------------------------------------ face
class Field:
    def __init__(self, X, D, sigma=SIGMA):
        self.X, self.sigma = X, sigma
        d2 = ((X[:, None, :] - X[None, :, :]) ** 2).sum(-1)
        self.alpha = np.linalg.solve(np.exp(-d2 / sigma ** 2) + LAMBDA * np.eye(len(X)), D)

    def __call__(self, P):
        out = np.zeros_like(P)
        for s in range(0, len(P), 4000):
            d2 = ((P[s:s + 4000, None, :] - self.X[None, :, :]) ** 2).sum(-1)
            out[s:s + 4000] = np.exp(-d2 / self.sigma ** 2) @ self.alpha
        return out


RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 246, 161, 160, 159, 158, 157, 173]
LEFT_EYE = [263, 249, 390, 373, 374, 380, 381, 382, 362, 466, 388, 387, 386, 385, 384, 398]
LIPS = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191,
        61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149,
        150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
CHIN_PIN = (152, 148, 176, 149, 377, 400, 378, 175, 199, 200)   # the chin, under and in front (shape_from_portrait)
CHIN_HOLD = (0.012, 0.035)      # ... held fully within this of them, free beyond (m)


def deep_eye_anchors(A, depth=0.01):
    """Eye landmarks whose anchors on the template (tools/models/mpfb_face_anchors.json) lie in the eye socket, not on
    the lid: more than `depth` behind the eye's corners. On MakeHuman's upper lids 246, 161, 160 (right) and 466, 388,
    387, 386 (left) sit about 2 cm behind the lid, 386 4.5 mm above its mirror image 159: matched to the scan's and
    the portrait's lid line, they pulled the left upper lid and its painted lash line out of place (one eye's lashes
    stood taller than the other's). Head scans leave them out of the face fits and the portrait's warp."""
    bad = set()
    for ids, corners in ((RIGHT_EYE, (33, 133)), (LEFT_EYE, (263, 362))):
        if all(k in A for k in corners):
            cy = float(np.mean([A[k][1] for k in corners]))
            bad |= {i for i in ids if i in A and A[i][1] > cy + depth}
    return bad


def fit_affine(X, Y):
    """Least-squares affine X -> Y (4 x 3, rows: x, y, z, offset) fitted in the front plane (x, z) only. Face
    landmarks hardly vary in depth, so a free depth scale is mostly noise (it came out 0.72-0.89 and flattened
    faces): depth gets the front plane's mean scale instead."""
    B, *_ = np.linalg.lstsq(np.hstack([X[:, [0, 2]], np.ones((len(X), 1))]), Y[:, [0, 2]], rcond=None)
    sd = float(np.sqrt(abs(np.linalg.det(B[:2]))))
    M = np.zeros((4, 3))
    M[0, 0], M[2, 0], M[3, 0] = B[0, 0], B[1, 0], B[2, 0]
    M[0, 2], M[2, 2], M[3, 2] = B[0, 1], B[1, 1], B[2, 1]
    M[1, 1] = sd
    M[3, 1] = Y[:, 1].mean() - sd * X[:, 1].mean()
    return M


def fit_similarity(X, Y):
    """As fit_affine, but one scale and an in-plane rotation (Umeyama in the front plane): the shape's own
    proportions survive. Depth gets the same scale."""
    A, B = X[:, [0, 2]], Y[:, [0, 2]]
    ma, mb = A.mean(0), B.mean(0)
    U, S, Vt = np.linalg.svd((B - mb).T @ (A - ma))
    d = float(np.sign(np.linalg.det(U @ Vt)))
    s = float((S * np.array([1.0, d])).sum() / ((A - ma) ** 2).sum())
    L = s * (U @ np.diag([1.0, d]) @ Vt)
    t = mb - L @ ma
    M = np.zeros((4, 3))
    M[0, 0], M[2, 0], M[3, 0] = L[0, 0], L[0, 1], t[0]
    M[0, 2], M[2, 2], M[3, 2] = L[1, 0], L[1, 1], t[1]
    M[1, 1] = s
    M[3, 1] = Y[:, 1].mean() - s * X[:, 1].mean()
    return M


def affine(M, P):
    return P @ M[:3] + M[3]


def fit_face(basemesh, rig, lms, root, w_head, planar=False):
    """Move the head onto the scan's face landmarks in two steps, so nothing inside it folds through the skin:
    one affine for the whole head (skull, sockets, eyes, teeth move together; it fades out down the neck),
    then a Gaussian RBF for what is left at each landmark. Eyeballs and teeth stay rigid, following their own
    eyelid and lip landmarks. Returns, per body vertex, how firmly the landmarks hold it (1 on the face).
    planar (a head scan): the RBF moves the features in the front plane only; fit_head gives the face the scan's
    depth. A head scan's eyes are a closed surface over the opening and its landmarks' depths there pulled the lower
    lids a centimetre off the cheek below (a flap)."""
    A = anchor_points(basemesh, root)
    keys = [i for i in lms if i in A]
    if planar:
        deep = deep_eye_anchors(A)
        keys = [i for i in keys if i not in deep]
    X = np.array([A[i] for i in keys])
    Y = np.array([lms[i] for i in keys])
    M = fit_affine(X, Y)
    r = np.linalg.norm(affine(M, X) - Y, axis=1)
    good = r < min(0.015, np.percentile(r, 90))
    M = fit_affine(X[good], Y[good])
    keys = [k for k, g in zip(keys, good) if g]
    X, Y = X[good], Y[good]
    Xa = affine(M, X)
    D = Y - Xa
    # the outline is seen edge-on from the front (unreliable) and must meet the side of the head: it stays on the
    # affine; the RBF only shapes the features inside it, by at most a centimetre
    D[[k in OVAL for k in keys]] = 0.0
    if planar:
        D[:, 1] = 0.0
    n = np.linalg.norm(D, axis=1, keepdims=True)
    D *= np.minimum(1.0, 0.01 / np.maximum(n, 1e-9))
    field = Field(Xa, D)
    lin = M[:3] - np.eye(3)
    log(f"face: {len(keys)} landmarks; head affine shift {np.linalg.norm(M[3] + X.mean(0) @ lin) * 1000:.1f} mm, "
        f"scale {np.round(np.linalg.svd(M[:3])[1], 3).tolist()}; RBF mean {np.linalg.norm(D, axis=1).mean() * 1000:.1f} mm, "
        f"max {np.linalg.norm(D, axis=1).max() * 1000:.1f} mm")

    def moved(P, w):
        Pa = P + w[:, None] * (affine(M, P) - P)
        return Pa, field(Pa) * w[:, None]

    def landmark_shift(ids):
        sel = [j for j, k in enumerate(keys) if k in ids]
        return D[sel].mean(0) if sel else np.zeros(3)

    V = world_verts(basemesh)
    Va, d = moved(V, w_head)
    set_world_verts(basemesh, Va + d)
    basemesh["scan_head_linear"] = M[:3].ravel().tolist()   # scale_shapes() resizes the face shapes with it
    for obj in [o for o in rig.children if o.type == 'MESH' and o != basemesh]:
        P = world_verts(obj)
        Pa, d = moved(P, np.ones(len(P)))
        name = obj.name.lower()
        if "high-poly" in name or "low-poly" in name:
            # each eyeball follows its own eyelids
            for ids in (RIGHT_EYE, LEFT_EYE):
                c = np.array([lms[i] for i in ids if i in lms]).mean(0)
                side = np.sign(c[0] - Pa[:, 0].mean())
                sel = np.sign(Pa[:, 0] - Pa[:, 0].mean()) == side
                d[sel] = landmark_shift(ids)
        elif "teeth" in name or "tongue" in name:
            d[:] = landmark_shift(LIPS)
        elif "glasses" in name:
            d[:] = np.median(d, 0)
        set_world_verts(obj, Pa + d)
    Vn = world_verts(basemesh)
    near = np.full(len(Vn), 1e9)
    for s in range(0, len(Vn), 4000):
        near[s:s + 4000] = np.sqrt(((Vn[s:s + 4000, None, :] - Y[None]) ** 2).sum(-1).min(1))
    return 1.0 - smoothstep(0.012, 0.03, near)


def fit_scan_head(scan, basemesh, lms, root, similarity=False):
    """Fit the scan's head to the character's head, not the other way round. The AI image behind a scan often
    gives the person a head 8-25 % too big for their height; growing the character's head to match made big-
    headed, two-metre characters, and shrinking the body made Joaquin 1.54 m. So the body keeps the cast's
    height, and one affine from the scan's face landmarks to the character's moves the scan's head (hair, ears,
    jaw) onto the character's, fading out down its neck. Returns the landmarks moved with it.
    similarity (a head scan): one scale instead of the affine, so the face keeps the head scan's proportions
    (the affine gives it the template's; a full-body scan's face is only a guess)."""
    A = anchor_points(basemesh, root)
    keys = [i for i in lms if i in A]
    X = np.array([lms[i] for i in keys])
    Y = np.array([A[i] for i in keys])
    fit = fit_similarity if similarity else fit_affine
    M = fit(X, Y)
    r = np.linalg.norm(affine(M, X) - Y, axis=1)
    good = r < min(0.015, np.percentile(r, 90))
    M = fit(X[good], Y[good])
    SV = world_verts(scan)
    chin = lms[152][2] if 152 in lms else X[:, 2].min()
    w = smoothstep(chin - 0.10, chin - 0.02, SV[:, 2])
    set_world_verts(scan, SV + w[:, None] * (affine(M, SV) - SV))
    log(f"scan head fitted to the character's{' (similarity)' if similarity else ''}: scale "
        f"{np.round(np.linalg.svd(M[:3])[1], 3).tolist()}, {int(good.sum())} landmarks")
    return {i: affine(M, p[None])[0] for i, p in lms.items()}


INNER_LIPS = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191]


def mouth_inside(basemesh, in_body, head_faces, root):
    """The mouth's inside (palate, cheeks, throat). In MakeHuman's UVs it is its own island, joined to the face's
    island deep behind the lips. Returns the vertices strictly inside it, and its faces."""
    me = basemesh.data
    A = anchor_points(basemesh, root)
    c = (A[13] + A[14]) / 2
    V = world_verts(basemesh)
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    use = [f for f in bm.faces if head_faces[f.index] and all(in_body[v.index] for v in f.verts)]
    parent = {f.index: f.index for f in use}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for f in use:
        for l in f.loops:
            for l2 in l.edge.link_loops:
                g = l2.face
                if g is f or g.index not in parent:
                    continue
                # the same UVs at both ends of the shared edge: one island
                a1, b1 = l[uvl].uv, l.link_loop_next[uvl].uv
                a2, b2 = ((l2[uvl].uv, l2.link_loop_next[uvl].uv) if l2.vert is l.vert
                          else (l2.link_loop_next[uvl].uv, l2[uvl].uv))
                if (a1 - a2).length < 1e-5 and (b1 - b2).length < 1e-5:
                    ra, rb = find(f.index), find(g.index)
                    if ra != rb:
                        parent[ra] = rb
    bm.free()
    islands = {}
    for f in parent:
        islands.setdefault(find(f), []).append(f)
    face_island = max(islands.values(), key=len)
    faces = np.zeros(len(me.polygons), bool)
    for fs in islands.values():
        if fs is face_island:
            continue
        vs = np.unique(np.concatenate([list(me.polygons[i].vertices) for i in fs]))
        if np.linalg.norm(V[vs] - c, axis=1).min() < 0.008:
            faces[fs] = True
    on = np.zeros(len(V), bool)
    off = np.zeros(len(V), bool)
    for poly in me.polygons:
        (on if faces[poly.index] else off)[list(poly.vertices)] = True
    log(f"mouth: inside {int(faces.sum())} faces, {int((on & ~off).sum())} vertices")
    return on & ~off, faces


# upper / lower inner-lip landmarks facing each other, from the mouth's middle out to its corners
LIP_PAIRS = [(13, 14), (82, 87), (312, 317), (81, 178), (311, 402), (80, 88), (310, 318), (191, 95), (415, 324)]


def lip_gaps(basemesh, root):
    """How far apart the lips are (mm), from the middle out to the corners."""
    A = anchor_points(basemesh, root)
    return [round(float(np.linalg.norm(A[u] - A[l])) * 1000, 1) for u, l in LIP_PAIRS if u in A and l in A]


def follow_mouth(basemesh, V0, inside, faces, head_faces, in_body, root, sigma=0.006):
    """Move the mouth's inside the way the skin around it moved. The face fits (landmark RBF, the skin laid onto
    the scan, the portrait's proportions) each move the face's skin their own way; left to them, the inside lagged
    behind and came out through the chin under the lower lip (pale jagged patches) or up through a nostril (a red
    streak). So the inside is put back where the template had it (V0, before the fits) and moved by the skin's
    own displacement, averaged with a Gaussian of `sigma` over the skin near each vertex: it keeps its place
    behind the lips, under the nose and inside the cheeks."""
    me = basemesh.data
    V = world_verts(basemesh)
    A = anchor_points(basemesh, root)
    lip = (A[13] + A[14]) / 2
    on = np.zeros(len(V), bool)
    for poly in me.polygons:
        if head_faces[poly.index] and not faces[poly.index]:
            on[list(poly.vertices)] = True
    skin = np.nonzero(on & in_body & ~inside & (np.linalg.norm(V0 - lip, axis=1) < 0.06))[0]
    S0, DS = V0[skin], V[skin] - V0[skin]
    idx = np.nonzero(inside)[0]
    B0 = V0[idx]
    d2 = ((B0[:, None, :] - S0[None]) ** 2).sum(-1)
    w = np.exp(-(d2 - d2.min(1, keepdims=True)) / (2 * sigma ** 2))   # relative to the nearest: no underflow
    D = (w @ DS) / w.sum(1, keepdims=True)
    before = np.linalg.norm(V[idx] - B0, axis=1)
    V[idx] = B0 + D
    # and a little smaller, away from where it joins the lips: its floor otherwise grazed the chin from inside
    seam = set(np.nonzero(np.isin(np.arange(len(V)), np.unique(np.concatenate(
        [list(me.polygons[p].vertices) for p in np.nonzero(faces)[0]]))) & ~inside)[0].tolist())
    ring = {v: 0 for v in seam}
    E = edges(me)
    E = E[(inside[E[:, 0]] | np.isin(E[:, 0], list(seam))) & (inside[E[:, 1]] | np.isin(E[:, 1], list(seam)))]
    nbr = {}
    for a, b in E:
        nbr.setdefault(a, []).append(b)
        nbr.setdefault(b, []).append(a)
    todo = list(seam)
    while todo:
        nxt = []
        for v in todo:
            for w in nbr.get(v, []):
                if w not in ring:
                    ring[w] = ring[v] + 1
                    nxt.append(w)
        todo = nxt
    s = np.array([min(ring.get(v, 3), 3) / 3.0 for v in idx])[:, None]
    c = V[idx].mean(0)
    V[idx] = V[idx] + s * ((c + (V[idx] - c) * 0.88) - V[idx])
    set_world_verts(basemesh, V, inside)
    log(f"mouth: inside follows {len(skin)} skin vertices, moved {np.linalg.norm(D, axis=1).mean() * 1000:.1f} mm on "
        f"average (the fits alone had moved it {before.mean() * 1000:.1f} mm)")


def face_island(basemesh, in_body, head_faces):
    """The face's own UV island (the largest of the head's): its outer skin, eyelids and lips, without the eye
    sockets and the mouth's inside, which MakeHuman maps to islands of their own. Returns a face mask."""
    me = basemesh.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    use = [f for f in bm.faces if head_faces[f.index] and all(in_body[v.index] for v in f.verts)]
    parent = {f.index: f.index for f in use}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for f in use:
        for l in f.loops:
            for l2 in l.edge.link_loops:
                g = l2.face
                if g is f or g.index not in parent:
                    continue
                a1, b1 = l[uvl].uv, l.link_loop_next[uvl].uv
                a2, b2 = ((l2[uvl].uv, l2.link_loop_next[uvl].uv) if l2.vert is l.vert
                          else (l2.link_loop_next[uvl].uv, l2[uvl].uv))
                if (a1 - a2).length < 1e-5 and (b1 - b2).length < 1e-5:
                    ra, rb = find(f.index), find(g.index)
                    if ra != rb:
                        parent[ra] = rb
    bm.free()
    islands = {}
    for f in parent:
        islands.setdefault(find(f), []).append(f)
    out = np.zeros(len(me.polygons), bool)
    out[max(islands.values(), key=len)] = True
    return out


def eye_objects(rig, basemesh):
    return [o for o in rig.children if o.type == 'MESH' and o != basemesh
            and ("high-poly" in o.name.lower() or "low-poly" in o.name.lower())]


def follow_eyes(basemesh, rig, V0, E0, in_body, head_faces, root, gap=0.0006, max_push=0.004):
    """Move each eyeball the way the skin around its eye moved. The face fits each move the eyelids their own way
    and the eyeballs only with landmark averages, so an eyeball could end up low or forward and show through the
    lower lid (Joaquin's right eye: a white bulge under the iris). From the template (E0, V0) each eyeball is moved
    by the mean displacement of its eyelid ring (the eye landmarks' vertices and the skin within 4 mm), then pushed
    straight back if any of it is still level with or in front of the face's skin seen from the front."""
    anchors = json.load(open(os.path.join(root, "tools", "models", "mpfb_face_anchors.json")))["anchors"]
    V1 = world_verts(basemesh)
    rings = []
    for ids in (RIGHT_EYE, LEFT_EYE):
        vs = sorted({v for i in ids if i < len(anchors) and anchors[i] for v in anchors[i]["v"]})
        P = V0[vs]
        near = np.full(len(V0), 1e9)
        for s in range(0, len(V0), 4000):
            near[s:s + 4000] = np.sqrt(((V0[s:s + 4000, None, :] - P[None]) ** 2).sum(-1).min(1))
        ring = np.nonzero((near < 0.004) & in_body)[0]
        rings.append((V0[vs].mean(0), (V1[ring] - V0[ring]).mean(0)))
    me = basemesh.data
    me.calc_loop_triangles()
    tv = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tv)
    tp = np.empty(len(me.loop_triangles), np.int64)
    me.loop_triangles.foreach_get("polygon_index", tp)
    skin = tv.reshape(-1, 3)[face_island(basemesh, in_body, head_faces)[tp]]
    bvh = BVHTree.FromPolygons(V1.tolist(), skin.tolist(), all_triangles=True)
    ahead, back = Vector((0, -0.06, 0)), Vector((0, 1, 0))
    report = []
    for obj in eye_objects(rig, basemesh):
        P0 = E0.get(obj.name)
        if P0 is None or len(P0) != len(obj.data.vertices):
            continue
        mid = (rings[0][0][0] + rings[1][0][0]) / 2
        side_r = np.sign(rings[0][0][0] - mid)
        P = P0.copy()
        for k, (c, d) in enumerate(rings):
            sel = (np.sign(P0[:, 0] - mid) == (side_r if k == 0 else -side_r))
            P[sel] = P0[sel] + d
            # nothing of the eyeball may sit in front of the lids or cheek around it
            need = 0.0
            for p in P[sel][::3]:
                loc, n, _, _ = bvh.ray_cast(Vector(p) + ahead, back, 0.1)
                if loc is not None and n.y < -0.2:
                    need = max(need, loc.y + gap - p[1])
            push = min(need, max_push)
            P[sel, 1] += push
            report.append(f"{'right' if k == 0 else 'left'} moved {np.linalg.norm(d) * 1000:.1f} mm, "
                          f"pushed back {push * 1000:.1f} mm" + (" (capped)" if need > max_push else ""))
        set_world_verts(obj, P)
    log("eyes: " + "; ".join(report))


def inner_lips(basemesh, V0, in_body, inside, root):
    """The lips' wet inner sides (facing down, up or back into the mouth on the template, within 8 mm of the
    inner lip line): no portrait reaches them and the scan's colour there is whatever its lip line was, which showed
    as pale torn strips along the lip line. Per vertex, 0..1."""
    me = basemesh.data
    T = triangles(me)
    T = T[in_body[T].all(1)]
    N0 = vertex_normals(V0, T)
    anchors = json.load(open(os.path.join(root, "tools", "models", "mpfb_face_anchors.json")))["anchors"]
    P = np.array([(V0[anchors[i]["v"]] * np.array(anchors[i]["w"])[:, None]).sum(0)
                  for i in INNER_LIPS if i < len(anchors) and anchors[i]])
    d = np.full(len(V0), 1e9)
    for s in range(0, len(V0), 4000):
        d[s:s + 4000] = np.sqrt(((V0[s:s + 4000, None, :] - P[None]) ** 2).sum(-1).min(1))
    w = (1.0 - smoothstep(0.003, 0.008, d)) * smoothstep(-0.2, 0.3, N0[:, 1])
    w[~in_body | inside] = 0.0
    log(f"inner lips: {int((w > 0.5).sum())} vertices take the template's lip colour")
    return w


def tuck_mouth(basemesh, inside, faces, head_faces, in_body, gap=0.0025):
    """Safety net after follow_mouth: an inside vertex still level with or in front of the skin in front of it
    (along -Y, the character's front) goes back until it is `gap` behind it, its neighbours with it."""
    me = basemesh.data
    V = world_verts(basemesh)
    me.calc_loop_triangles()
    tv = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tv)
    tp = np.empty(len(me.loop_triangles), np.int64)
    me.loop_triangles.foreach_get("polygon_index", tp)
    tv = tv.reshape(-1, 3)
    # the head's own skin: not the inside, nor MakeHuman's helper teeth and tongue (deleted later, but they sit
    # behind the lips and face the front)
    skin = tv[head_faces[tp] & ~faces[tp] & in_body[tv].all(1)]
    bvh = BVHTree.FromPolygons(V.tolist(), skin.tolist(), all_triangles=True)
    push = np.zeros(len(V))
    ahead, back = Vector((0, -0.08, 0)), Vector((0, 1, 0))
    for i in np.nonzero(inside)[0]:
        p = Vector(V[i])
        loc, n, _, _ = bvh.ray_cast(p + ahead, back, 0.12)
        # the first skin along the line must face the front (not an inner lip seen through the mouth's slit)
        if loc is None or n.y > -0.2:
            continue
        push[i] = max(0.0, loc.y + gap - p.y)
    E = edges(me)
    E = E[inside[E].all(1)]
    for _ in range(4):
        nb = np.zeros(len(V))
        np.maximum.at(nb, E[:, 0], push[E[:, 1]])
        np.maximum.at(nb, E[:, 1], push[E[:, 0]])
        push = np.maximum(push, 0.75 * nb)
    V[:, 1] += push
    set_world_verts(basemesh, V, inside)
    log(f"mouth: {int((push > 0).sum())} of {int(inside.sum())} inside vertices tucked behind the skin "
        f"({int((push > 0.005).sum())} by over 5 mm), max {push.max() * 1000:.1f} mm")


def project_face(basemesh, scan, lms, face_hold, in_body, inside=None):
    """After the landmark fit, lay the face's skin onto the scan's own face surface, so the cheeks, jaw, nose
    and forehead have the scan's shape rather than MakeHuman's between the landmarks (that mix read as puffy
    cheeks and swollen lips). The eyelids and sockets, the inner lips and mouth, and the nostrils keep the
    landmark fit: their shape keys (blink, jaw, visemes) need the template's geometry there. Offsets fade out
    over a few millimetres around those parts and are smoothed over the mesh."""
    me = basemesh.data
    V = world_verts(basemesh)
    Tri = triangles(me)
    Tri = Tri[in_body[Tri].all(1)]
    E = edges(me)
    E = E[in_body[E].all(1)]
    n = len(V)
    N = vertex_normals(V, Tri)
    SV = world_verts(scan)
    face_z = min(p[2] for p in lms.values()) - 0.03
    ST = triangles(scan.data)
    ST = ST[(SV[ST][:, :, 2] > face_z).all(1)]
    bvh = BVHTree.FromPolygons(SV.tolist(), ST.tolist(), all_triangles=True)
    keep_out = np.zeros(n)

    def protect(centre, radius, fade=0.006):
        d = np.linalg.norm(V - centre, axis=1)
        return 1.0 - smoothstep(radius, radius + fade, d)

    for ids in (RIGHT_EYE, LEFT_EYE):
        P = np.array([lms[i] for i in ids if i in lms])
        if len(P):
            c = P.mean(0)
            keep_out = np.maximum(keep_out, protect(c, float(np.linalg.norm(P - c, axis=1).max()) + 0.004))
    P = np.array([lms[i] for i in INNER_LIPS if i in lms])
    if len(P):
        d = np.sqrt(((V[:, None, :] - P[None]) ** 2).sum(-1).min(1))
        keep_out = np.maximum(keep_out, 1.0 - smoothstep(0.004, 0.010, d))
        # the mouth's inside, behind the lips
        c = P.mean(0)
        inside = (V[:, 1] > c[1] + 0.004) & (np.linalg.norm((V - c)[:, [0, 2]], axis=1) < 0.03)
        keep_out[inside] = 1.0
    if 1 in lms:
        tip = lms[1]
        under = (np.linalg.norm(V - tip, axis=1) < 0.022) & (N[:, 2] < -0.35)   # nostrils face down
        keep_out[under] = 1.0
    if inside is not None:
        keep_out[inside] = 1.0   # the mouth's inside (follow_mouth moves it with the skin around it)
    region = in_body & (face_hold > 0.3) & (keep_out < 0.99)
    D = np.zeros_like(V)
    conf = np.zeros(n)
    for i in np.nonzero(region)[0]:
        p, nn = Vector(V[i]), Vector(N[i])
        best = None
        for d in (nn, -nn):
            loc, hn, _, dist = bvh.ray_cast(p, d, 0.012)
            if loc is not None and hn.dot(nn) > 0.3 and (best is None or dist < best[1]):
                best = (loc, dist)
        if best is not None:
            D[i] = np.array(best[0]) - V[i]
            conf[i] = 1.0
    D = smooth(D, conf, E, 6, lam=0.5)
    w = np.clip(face_hold, 0, 1) * (1.0 - keep_out)
    w = smooth(w[:, None], np.ones(n), E, 3)[:, 0] * (keep_out < 0.99)
    moved = np.linalg.norm(D, axis=1) * w
    set_world_verts(basemesh, V + D * w[:, None], in_body)
    log(f"face surface: {int(conf.sum())} vertices onto the scan's face, mean {moved[region].mean() * 1000:.1f} mm, "
        f"max {moved.max() * 1000:.1f} mm")


def coincident(V, tol=1e-6):
    """A representative per vertex: vertices at the same place share one (MakeHuman's mesh is not welded round the
    eyelids and a few other parts)."""
    kd = KDTree(len(V))
    for i, p in enumerate(V):
        kd.insert(p, i)
    kd.balance()
    pairs = []
    for i, p in enumerate(V):
        for _, j, _ in kd.find_range(p, tol):
            if j > i:
                pairs.append((i, j))
    return components(len(V), np.array(pairs, np.int64).reshape(-1, 2)), len(pairs)


def solve_field(E, dom, T, c, alpha=0.3, beta=3.0, iters=6000, tol=1e-6, rep=None):
    """A smooth displacement over the dom vertices: least squares of sum c |D - T|^2 (the data) + alpha |grad D|^2 +
    beta |lap D|^2 over the mesh's edges E (graph Laplacian; vertices outside dom hold D = 0). Where there is no data
    it is the smoothest continuation (bending, not a tent), so a region that moves far fades out over centimetres with
    no step or crease at its edge. Conjugate gradients, matrix-free (Jacobi preconditioned). rep (coincident()):
    vertices at one place are one unknown (left apart, the eyelids' unwelded rim let them stand off the face)."""
    if rep is not None:
        n0 = len(dom)
        u, r = np.unique(rep, return_inverse=True)
        m0 = len(u)
        Er = r[E]
        Er = Er[Er[:, 0] != Er[:, 1]]
        Er = np.unique(np.sort(Er, 1), axis=0)
        dr = np.zeros(m0, bool)
        np.logical_or.at(dr, r, dom)
        cr = np.bincount(r, weights=c, minlength=m0)
        Tr = np.stack([np.bincount(r, weights=c * T[:, k], minlength=m0) for k in range(T.shape[1])], 1)
        Tr /= np.maximum(cr, 1e-12)[:, None]
        Dr, its = solve_field(Er, dr, Tr, cr, alpha, beta, iters, tol)
        return Dr[r] * dom[:, None], its
    n = len(dom)
    idx = np.nonzero(dom)[0]
    m = len(idx)
    loc = -np.ones(n, np.int64)
    loc[idx] = np.arange(m)
    deg = np.bincount(E.ravel(), minlength=n)[idx].astype(np.float64)
    Ein = E[dom[E].all(1)]
    a, b = loc[Ein[:, 0]], loc[Ein[:, 1]]

    def lap(X):
        out = deg[:, None] * X
        for k in range(X.shape[1]):
            out[:, k] -= np.bincount(a, weights=X[b, k], minlength=m) + np.bincount(b, weights=X[a, k], minlength=m)
        return out
    cc = c[idx].astype(np.float64)

    def A(X):
        LX = lap(X)
        return cc[:, None] * X + alpha * LX + beta * lap(LX)
    rhs = cc[:, None] * T[idx]
    diag = (cc + alpha * deg + beta * (deg ** 2 + deg))[:, None]
    X = np.zeros((m, T.shape[1]))
    R = rhs - A(X)
    Z = R / diag
    P = Z.copy()
    rz = float((R * Z).sum())
    stop = tol * max(float(np.sqrt((rhs ** 2).sum())), 1e-12)
    it = 0
    for it in range(iters):
        AP = A(P)
        step = rz / max(float((P * AP).sum()), 1e-30)
        X += step * P
        R -= step * AP
        if float(np.sqrt((R ** 2).sum())) < stop:
            break
        Z = R / diag
        rz2 = float((R * Z).sum())
        P = Z + (rz2 / max(rz, 1e-30)) * P
        rz = rz2
    D = np.zeros((n, T.shape[1]))
    D[idx] = X
    return D, it + 1


def fit_head(basemesh, scan, lms, face_hold, in_body, W, names, ear, rig, mouth_in=None, gap=0.006):
    """Head scans: after the landmark fit, the whole head follows the head scan by one smooth displacement field
    (solve_field), instead of the face alone laid onto it. The face's skin, its jaw line and underside and its cheeks
    back to the ears (where the scan there is skin) land on the scan, along their normals (12 mm on the face, 4 cm by
    the ears; the nearest skin point at half weight when no ray finds it); the skull keeps `gap` under the scan's hair
    (and on its skin where the nearest is skin); the eyelids, the lips and mouth, the nostrils and the ears have no
    data: they move with the skin round them as one, keeping the template's shape for their face shapes. The field
    is zero down the neck (wrap() takes it from there). Laying the face alone onto a scan narrower than the template
    left a step from the temple past the eye to the jaw and a ledge across the forehead where the moved face met the
    rest of the head; the lips, eyes, skull and ears moved by separate steps folded where they met (a lower-lid flap,
    an upper lid collapsed over the iris, nostrils torn open)."""
    me = basemesh.data
    V = world_verts(basemesh)
    Tri = triangles(me)
    Tri = Tri[in_body[Tri].all(1)]
    E = edges(me)
    E = E[in_body[E].all(1)]
    n = len(V)
    N = vertex_normals(V, Tri)
    w_head = W[:, names.index("head")]
    SV = world_verts(scan)
    L = np.array(list(lms.values()))
    chin = float(L[:, 2].min())
    ST = triangles(scan.data)
    ST = ST[(SV[ST][:, :, 2] > chin - 0.07).all(1)]
    skin = to_lab(scan_colors(scan.data))[:, 0] > 20             # not hair
    bvh = BVHTree.FromPolygons(SV.tolist(), ST.tolist(), all_triangles=True)
    brow = float(np.mean([lms[i][2] for i in BROWS if i in lms] or [L[:, 2].mean()]))
    ear_y = float(np.mean([lms[i][1] for i in EARS if i in lms] or [L[:, 1].max()]))
    dom = in_body & ((w_head > 0.03) | (face_hold > 0.01))
    rep, n_weld = coincident(V)
    # no data: the eyes (lids and sockets), the lips and mouth, the nostrils, the ears. Each moves as one, by the median
    # displacement of the skin in a ring round it (weakly held there: left to the smooth continuation alone, the right
    # eye's lids bulged 5 mm out of the face)
    groups = []
    near_eye = np.zeros(n, bool)
    for ids in (RIGHT_EYE, LEFT_EYE):
        P = np.array([lms[i] for i in ids if i in lms])
        if len(P):
            cen = P.mean(0)
            dist = np.linalg.norm(V - cen, axis=1)
            r = float(np.linalg.norm(P - cen, axis=1).max())
            groups.append(("eye", dist < r + 0.008))
            # (the scan's eyes are a surface over the opening: rays from the template's orbit there found it ~1 cm out)
            near_eye |= dist < r + 0.022
    P = np.array([lms[i] for i in INNER_LIPS if i in lms])
    if len(P):
        cen = P.mean(0)
        lip = (nearest_landmark(V, P) < 0.007) | ((V[:, 1] > cen[1] + 0.004)
                                                  & (np.linalg.norm((V - cen)[:, [0, 2]], axis=1) < 0.03))
        if mouth_in is not None:
            lip |= mouth_in
        groups.append(("lips", lip))
    if 1 in lms:
        groups.append(("nostrils", (np.linalg.norm(V - lms[1], axis=1) < 0.022) & (N[:, 2] < -0.35)))
    groups.append(("ears", ear > 0.05))
    keep = np.zeros(n, bool)
    for _, g in groups:
        keep |= g
    rings = []
    for _, g in groups:
        x = g.astype(np.float64)
        for _ in range(4):
            x = np.maximum(x, neighbour_mean(x, E, n) > 0)
        rings.append((x > 0) & ~keep & dom)
    face = dom & ~keep & (face_hold > 0.3)
    side = dom & ~keep & ~face & (w_head > 0.3) & (V[:, 2] < brow) & (V[:, 1] < ear_y + 0.03)
    reach = np.where(face, np.where(near_eye, 0.004, 0.012), np.where(side, 0.04, 0.0))
    T = np.zeros_like(V)
    c = np.zeros(n)
    for i in np.nonzero(face | side)[0]:
        p, nn = Vector(V[i]), Vector(N[i])
        best = None
        for d in (nn, -nn):
            loc, hn, ti, dist = bvh.ray_cast(p, d, reach[i])
            if loc is not None and hn.dot(nn) > 0.3 and skin[ST[ti]].all() and (best is None or dist < best[1]):
                best = (loc, dist)
        if best is not None:
            T[i], c[i] = np.array(best[0]) - V[i], 1.0
        elif side[i]:
            loc, hn, ti, dist = bvh.find_nearest(p, reach[i])
            if loc is not None and hn.dot(nn) > 0.3 and skin[ST[ti]].all():
                T[i], c[i] = np.array(loc) - V[i], 0.5
    n_face, n_side = int((face & (c > 0)).sum()), int((side & (c > 0)).sum())
    skull = dom & ~keep & ~face & ~side & (w_head > 0.5) & (V[:, 2] > chin)
    D, its = solve_field(E, dom, T, c, rep=rep)
    # data that disagree with their neighbours (a ray into a crease or a nostril of the scan) are dropped once
    r = np.linalg.norm(D - T, axis=1)
    out = (c > 0) & (r > 0.003)
    c[out] = 0.0
    tucked = 0
    moved_as_one = {}

    def hold_groups(D):
        for (nm, g), ring in zip(groups, rings):
            if ring.any() and g.any():
                m = np.median(D[ring], 0)
                T[g], c[g] = m, 0.3
                moved_as_one[nm] = moved_as_one.get(nm, []) + [float(np.linalg.norm(m)) * 1000]
    for rnd in range(4):
        D, its = solve_field(E, dom, T, c, rep=rep)
        hold_groups(D)
        D, its = solve_field(E, dom, T, c, rep=rep)
        P = V + D
        add = 0
        for i in np.nonzero(skull & (c == 0))[0]:
            loc, nq, ti, _ = bvh.find_nearest(Vector(P[i]), 0.1)
            if loc is None:
                continue
            g = gap if not skin[ST[ti]].all() else 0.001
            o = float((P[i] - np.array(loc)) @ np.array(nq))
            if o > -g:
                T[i], c[i] = P[i] - (o + g) * np.array(nq) - V[i], 0.5
                add += 1
        tucked += add
        if not add:
            break
    D, its = solve_field(E, dom, T, c, rep=rep)
    if mouth_in is not None:
        D[mouth_in] = 0.0                       # follow_mouth moves the mouth's inside with the skin round it
    set_world_verts(basemesh, V + D, in_body)
    # the lashes and brows ride on their lids, the teeth and tongue on the lips round them
    kd = KDTree(int(in_body.sum()))
    body_i = np.nonzero(in_body)[0]
    for j, i in enumerate(body_i):
        kd.insert(V[i], j)
    kd.balance()
    lips = np.array([lms[i] for i in INNER_LIPS if i in lms])
    lip_v = in_body & (nearest_landmark(V, lips) < 0.012) if len(lips) else np.zeros(n, bool)
    for obj in [o for o in rig.children if o.type == 'MESH' and o != basemesh]:
        name = obj.name.lower()
        Po = world_verts(obj)
        if "lash" in name or "brow" in name:
            d = np.array([D[body_i[kd.find(p)[1]]] for p in Po])
        elif ("teeth" in name or "tongue" in name) and lip_v.any():
            d = np.repeat(D[lip_v].mean(0)[None], len(Po), 0)
        else:
            continue
        set_world_verts(obj, Po + d)
    mv = np.linalg.norm(D, axis=1)
    mid = float(V[in_body, 0].mean())
    sides = []
    for s, nm in ((-1, "right"), (1, "left")):
        sel = dom & (np.sign(V[:, 0] - mid) == s) & (np.abs(V[:, 0] - mid) > 0.045) & (face_hold > 0.3)
        sides.append(f"{nm} {float(-(D[sel, 0] * s).mean()) * 1000:.1f}")
    em = [f"{float(mv[(ear > 0.5) & (np.sign(V[:, 0] - mid) == s)].mean()) * 1000:.1f}" for s in (-1, 1)]
    log(f"head onto the head scan: {n_face} face and {n_side} jaw, cheek and neck vertices onto its skin, {int(out.sum())} "
        f"dropped as off their neighbours, {tucked} skull vertices tucked {gap * 1000:.0f} mm under its hair; field "
        f"over {int(dom.sum())} vertices ({n_weld} unwelded pairs joined; {its} steps): mean {mv[dom].mean() * 1000:.1f} mm, max {mv.max() * 1000:.1f} mm; "
        f"face sides moved in (right, left) {sides[0]}, {sides[1]} mm; moved as one: "
        + ", ".join(f"{k} {v[-1]:.1f} mm" for k, v in moved_as_one.items()))
    return D


def ear_group(basemesh, in_body):
    """MakeHuman's "ears" vertex group (weight over 0.5, body vertices only)."""
    vg = basemesh.vertex_groups.get("ears")
    ears = np.zeros(len(basemesh.data.vertices), bool)
    if vg is None:
        return ears
    for v in basemesh.data.vertices:
        for g in v.groups:
            if g.group == vg.index and g.weight > 0.5:
                ears[v.index] = True
    return ears & in_body


def flatten_ears(basemesh, scan, in_body, share=0.5, max_turn=30.0, reach_out=0.035):
    """Head scans: MakeHuman's ears stand out from the head about twice as far as a head scan's. The scan's hair is
    shaped round its own flat ears, so it runs through the template's (clear_ears then has to cut the hair beside them
    away, leaving the ears bare and the hair narrow). Each ear turns in towards the head as one piece, about a hinge
    along the front of its root (a vertical line through the root's front third: the ear's free part reaches back from
    there), until its rim is `share` of the way from its own reach to the scan's ear (at most `max_turn` degrees); the
    skin round it follows by a smooth field fading out within `reach_out` (solve_field), so the root neither creases
    nor tears. (Squeezed sideways, an ear reads as a thin plate from behind; bent over its first centimetre, its thin
    rim and lobe tear into spikes.) Returns the turns in degrees (right, left)."""
    me = basemesh.data
    ears = ear_group(basemesh, in_body)
    if not ears.any():
        return []
    V = world_verts(basemesh)
    E = edges(me)
    E = E[in_body[E].all(1)]
    root = np.zeros(len(V), bool)
    cross = ears[E[:, 0]] != ears[E[:, 1]]
    root[E[cross][ears[E[cross]]]] = True
    SV = world_verts(scan)
    sl = to_lab(scan_colors(scan.data))[:, 0] > 25
    mid = float(V[in_body, 0].mean())
    T = np.zeros_like(V)
    turns = []
    for side in (-1.0, 1.0):
        e = ears & (np.sign(V[:, 0] - mid) == side)
        r = root & e
        if r.sum() < 6:
            turns.append(0.0)
            continue
        P = V[e]
        lo, hi = P.min(0), P.max(0)
        box = sl & (np.sign(SV[:, 0] - mid) == side) & (SV[:, 1] > lo[1]) & (SV[:, 1] < hi[1]) & \
            (SV[:, 2] > lo[2]) & (SV[:, 2] < hi[2])
        if box.sum() < 20:
            turns.append(0.0)
            continue
        reach = float(np.abs(P[:, 0] - mid).max())
        scan_reach = float(np.percentile(np.abs(SV[box, 0] - mid), 99))
        target = reach - share * max(reach - scan_reach, 0.0)
        R0 = V[r]
        c = R0[R0[:, 1] <= np.percentile(R0[:, 1], 33)].mean(0)
        idx = np.nonzero(e)[0]

        def turned(deg):
            Q = V[idx].copy()
            a = math.radians(deg)
            x, y = Q[:, 0] - c[0], Q[:, 1] - c[1]
            Q[:, 0] = c[0] + x * math.cos(a) - y * math.sin(a)
            Q[:, 1] = c[1] + x * math.sin(a) + y * math.cos(a)
            return Q
        sgn = 1.0 if np.abs(turned(5.0)[:, 0] - mid).max() < np.abs(turned(-5.0)[:, 0] - mid).max() else -1.0
        best = 0.0
        for deg in np.arange(1.0, max_turn + 0.1, 1.0):
            best = deg
            if np.abs(turned(sgn * deg)[:, 0] - mid).max() <= target:
                break
        T[idx] = turned(sgn * best) - V[idx]
        turns.append(best)
        log(f"ear ({'right' if side < 0 else 'left'}): rim {reach * 1000:.1f} mm from the middle, the head scan's ear "
            f"{scan_reach * 1000:.1f}; turned in {best:.0f} deg about the front of its root (target {target * 1000:.1f} mm)")
    if not any(turns):
        return turns
    dom = in_body & (nearest_landmark(V, V[ears]) < reach_out)
    D, _ = solve_field(E, dom, T, ears.astype(np.float64) * 50.0, alpha=0.3, beta=3.0, rep=coincident(V)[0])
    Tri = triangles(me)
    Tri = Tri[in_body[Tri].all(1) & ~ears[Tri].any(1)]
    skin0 = BVHTree.FromPolygons(V.tolist(), Tri.tolist(), all_triangles=True)
    V2 = V + D
    skin1 = BVHTree.FromPolygons(V2.tolist(), Tri.tolist(), all_triangles=True)
    ei = np.nonzero(ears)[0]
    d0 = np.array([skin0.find_nearest(Vector(V[i]), 0.03)[3] or 0.03 for i in ei])
    d1 = np.array([skin1.find_nearest(Vector(V2[i]), 0.03)[3] or 0.03 for i in ei])
    set_world_verts(basemesh, V2, in_body)
    for s_, nm in ((-1.0, "right"), (1.0, "left")):
        sel = ears & (np.sign(V[:, 0] - mid) == s_)
        log(f"ear ({nm}): rim now {np.abs(V2[sel, 0] - mid).max() * 1000:.1f} mm, off by "
            f"{np.linalg.norm(D[sel] - T[sel], axis=1).max() * 1000:.1f} mm at most from the turn; the skin round it moved "
            f"{np.linalg.norm(D[dom & ~ears & (np.sign(V[:, 0] - mid) == s_)], axis=1).max() * 1000:.1f} mm at most")
    log(f"ears: {int(((d1 < 0.001) & (d0 >= 0.001)).sum())} of their vertices came within 1 mm of the skin round them")
    return turns


SKULL_MIN = (0.199, 0.150)      # tuck_skull keeps at least this skull length (glabella to the back) and breadth (m)


def tuck_skull(basemesh, scan, in_body, W, names, face_hold, gap=0.009, skin_gap=0.0015, rounds=3, root=None,
               limits=SKULL_MIN, crown=None):
    """Head scans: the template's skull under the head scan's hair. fit_head asks for it (6 mm under, as weak data at
    the nearest scan point along that point's normal), but against the field's bending the back and the crown of
    MakeHuman's round skull stayed 5-10 mm outside the scan's hair, which is cut closer to the head there: the hair
    cards' underlayer lay inside the scalp over half the back of the head and the crown, and the scalp showed between
    the cards. Each skull vertex (the head bone's, behind the face and above the ears' lobes) is held `gap` under the
    scan's outer surface where that is hair (`skin_gap` where it is skin), found by a ray from outside towards the
    head's centre (the outer surface, whatever its normals say); the face, the ears and the neck hold still and the
    rest follows by a smooth field (solve_field). Returns the largest move."""
    me = basemesh.data
    V = world_verts(basemesh)
    E = edges(me)
    E = E[in_body[E].all(1)]
    w_head = W[:, names.index("head")]
    ears = ear_group(basemesh, in_body)
    near_ear = nearest_landmark(V, V[ears]) if ears.any() else np.full(len(V), 1.0)
    SV = world_verts(scan)
    ST = triangles(scan.data)
    zc = float(V[in_body & (w_head > 0.5), 2].min())
    ST = ST[(SV[ST][:, :, 2] > zc).all(1)]
    bvh = BVHTree.FromPolygons(SV.tolist(), ST.tolist(), all_triangles=True)
    hair_v = to_lab(scan_colors(scan.data))[:, 0] < 25
    sel = in_body & (V[:, 2] > 1.0)
    lv = in_body & (np.abs(V[:, 2] - V[sel & (w_head > 0.9), 2].mean()) < 0.03) & (w_head > 0.9)
    c0 = np.array([float(V[in_body, 0].mean()), float((V[lv, 1].min() + V[lv, 1].max()) / 2),
                   float(V[sel & (w_head > 0.9), 2].mean())])
    # the cranium: above the ears' tops, or behind the ears above their lobes
    mid = float(V[in_body, 0].mean())
    if ears.any():
        e_top = float(np.percentile(V[ears, 2], 90))
        e_low = float(np.percentile(V[ears, 2], 30))
        e_back = float(np.percentile(V[ears, 1], 70))
    else:
        e_top, e_low, e_back = c0[2] + 0.02, c0[2] - 0.02, c0[1]
    cran = (V[:, 2] > e_top - 0.005) | ((V[:, 1] > e_back + 0.01) & (V[:, 2] > e_low))
    skull = in_body & (w_head > 0.6) & (face_hold < 0.02) & (near_ear > 0.012) & cran
    held = in_body & ((face_hold > 0.3) | (near_ear < 0.004) | (w_head < 0.3))
    dom = in_body & (w_head > 0.05)
    rep = coincident(V)[0]
    P = V.copy()
    moved = 0.0
    T = np.zeros_like(V)
    c = np.where(held, 10.0, 0.0)
    # an adult skull (limits: its length from the glabella to the back, its breadth above the ears): a head scan made
    # from a front portrait guesses the head's depth and can be several centimetres short at the back; tucked fully
    # under its hair the cranium would come out a child's size (the template's is 204 x 161 mm). The vertices that
    # make the length (the back, near the middle) and the breadth (the sides at their widest) may go in only so far
    # that the skull keeps `limits`; the crown, and whatever lies well inside those extremes, are free. Where the
    # skull then stays outside the scan's hair, fit_hair moves the hair out
    A = anchor_points(basemesh, root) if root is not None else {}
    lim_x = lim_y = None
    if limits is not None and 9 in A:
        g9 = A[9]
        hv = in_body & (w_head > 0.5) & ~ears
        mid_ = hv & (np.abs(V[:, 0] - mid) < 0.01)
        L0 = float(V[mid_, 1].max() - g9[1])
        up_ = hv & (V[:, 2] > float(np.mean([A[i][2] for i in (234, 454) if i in A] or [c0[2]])) + 0.035)
        hb0 = float(np.abs(V[up_, 0] - mid).max()) if up_.any() else 0.0
        ex = smoothstep(hb0 - 0.02, hb0 - 0.005, np.abs(V[:, 0] - mid))          # the sides at their widest
        ey = smoothstep(L0 - 0.03, L0 - 0.008, V[:, 1] - g9[1])                    # the back
        lim_x = max(hb0 - limits[1] / 2, 0.0) * ex + 0.05 * (1.0 - ex)
        lim_y = max(L0 - limits[0], 0.0) * ey + 0.05 * (1.0 - ey)
        log(f"skull before the tuck: {L0 * 1000:.0f} mm long (glabella to the back), {2 * hb0 * 1000:.0f} mm wide; "
            f"it may go in {max(L0 - limits[0], 0.0) * 1000:.0f} mm at the back, {max(hb0 - limits[1] / 2, 0.0) * 1000:.0f} "
            f"mm at each side")

    # (outfit key "skull_crown", a dict, off by default) the crown held `gap` metres further under the scan's hair, in
    # full from z[1] metres over the brows' landmarks, none below z[0]: hair_scan_cards' style crown lowers the hair
    # on top, which the skull just under the scan's hair would otherwise stop
    cw_ = None
    if crown and A and all(i in A for i in BROWS):
        zb_ = float(np.mean([A[i][2] for i in BROWS]))
        zr_ = crown.get("z", (0.05, 0.085))
        cw_ = float(crown.get("gap", 0.006)) * smoothstep(zb_ + float(zr_[0]), zb_ + float(zr_[1]), V[:, 2])

    def allowed(i, d):
        if lim_x is None:
            return np.inf
        return min(float(lim_x[i]) / max(abs(float(d[0])), 1e-3), float(lim_y[i]) / max(float(d[1]), 1e-3))
    capped = 0
    under_lip = set()
    for _ in range(rounds + (3 if limits is not None else 0)):
        add = 0
        for i in np.nonzero(skull)[0]:
            d = P[i] - c0
            r = float(np.linalg.norm(d))
            if r < 1e-6:
                continue
            d /= r
            loc, _, ti, dist = bvh.ray_cast(Vector(c0 + d * 0.3), Vector(-d), 0.3)
            if loc is None:
                continue
            rs = float(np.linalg.norm(np.array(loc) - c0))
            g = gap if hair_v[ST[ti]].any() else skin_gap
            if g == gap:
                # skin under a lip of hair (the fringe's and the temples' rolled hairline): the skull stays just under
                # that skin. Held 9 mm under the lip's outside, the forehead and temples sank under the scan's skin at
                # the hairline, and the hair underlayer's edge (on that skin) stood up to 29-44 mm off the skull
                q = Vector(np.array(loc) - d * 0.0005)
                for _ in range(3):
                    l2, _, t2, _ = bvh.ray_cast(q, Vector(-d), 0.03 - float(np.linalg.norm(np.array(q) - np.array(loc))))
                    if l2 is None:
                        break
                    if not hair_v[ST[t2]].any():
                        rs, g = float(np.linalg.norm(np.array(l2) - c0)), skin_gap
                        under_lip.add(int(i))
                        break
                    q = l2 - Vector(d) * 0.0005
            if cw_ is not None and g == gap:
                g = gap + float(cw_[i])
            if r > rs - g + 0.0005:
                r0 = float(np.linalg.norm(V[i] - c0))
                tgt = max(rs - g, r0 - allowed(i, d))
                if tgt > rs - g:
                    capped += 1
                if r - tgt < 0.0005 and c[i] > 0:
                    continue
                T[i] = P[i] + d * (tgt - r) - V[i]
                c[i] = 10.0 if tgt > rs - g else 1.0          # (a limit holds against the field's pull)
                add += 1
        if lim_x is not None:
            # the limits hold for every vertex of the cranium, not only the tucked ones: dragged in by the field round
            # them, the back and the sides still went 2-4 mm past them
            for i in np.nonzero(dom & ~held & (c < 10.0))[0]:
                d = V[i] - c0
                r0 = float(np.linalg.norm(d))
                if r0 < 1e-6:
                    continue
                d /= r0
                m = r0 - float(np.linalg.norm(P[i] - c0))
                a_ = allowed(i, d)
                if m > a_ + 0.0005:
                    T[i] = d * -a_
                    c[i] = 10.0
                    add += 1
        if not add:
            break
        D, _ = solve_field(E, dom, T, c, rep=rep)
        P = V + D
        moved = float(np.linalg.norm(D, axis=1).max())
    n_t = int((c[skull] > 0).sum())
    n_sm = 0
    if lim_x is not None and moved > 0:
        # the cranium's move smoothed (each vertex the mean of its neighbours', 60 times; 25 left an edge at 45.5 deg)
        # and the field solved again with that as its data, the limits held: where a limit held a vertex beside others
        # tucked further in, the back of the cranium and the crown came out with creases (17 edges over 30 deg, up to
        # 49 deg; the template has 3)
        D = P - V
        Ds = D.copy()
        mv_ = dom & ~held & (c < 10.0)
        for _ in range(60):
            nm = np.stack([neighbour_mean(Ds[:, k], E, len(V)) for k in range(3)], 1)
            Ds[mv_] = nm[mv_]
        c2 = np.where(held, 10.0, np.where(c >= 10.0, 10.0, np.where(dom, 1.0, 0.0)))
        T2 = np.where((c >= 10.0)[:, None] & ~held[:, None], D, Ds)
        D2, _ = solve_field(E, dom, T2, c2, rep=rep)
        n_sm = int(mv_.sum())
        P = V + D2
        moved = float(np.linalg.norm(D2, axis=1).max())
    if lim_x is not None and up_.any():
        # (and out to the adult breadth where the head scan's skull was narrower already, under SKULL_MIN; the sides
        # over the ears pushed out by what is missing, fading out 2 cm in from the widest and below 1.5-3.5 cm over
        # the ears' landmarks; the hair moves out over it, fit_hair)
        hb_ = float(np.abs(P[up_, 0] - mid).max())
        short = limits[1] / 2 - hb_
        if short > 0.0002:
            ez_ = float(np.mean([A[i][2] for i in (234, 454) if i in A] or [c0[2]]))
            wx = smoothstep(hb_ - 0.02, hb_ - 0.002, np.abs(P[:, 0] - mid)) * smoothstep(ez_ + 0.015, ez_ + 0.035, P[:, 2])
            wx = wx * (dom & ~held & hv)
            P[:, 0] += np.sign(P[:, 0] - mid) * (short + 0.0003) * wx
            log(f"skull: its sides over the ears {short * 1000:.1f} mm out to the adult breadth ({int((wx > 0.5).sum())} "
                f"vertices)")
    set_world_verts(basemesh, P, in_body)
    if lim_x is not None:
        L1 = float(P[mid_, 1].max() - g9[1])
        hb1 = float(np.abs(P[up_, 0] - mid).max()) if up_.any() else 0.0
        log(f"skull after the tuck: {L1 * 1000:.0f} mm long, {2 * hb1 * 1000:.0f} mm wide")
    log(f"skull: {n_t} of its vertices held {gap * 1000:.0f} mm under the head scan's hair (rays from outside; "
        f"{capped} of them held out by the adult skull's limits, {len(under_lip)} under a lip of hair held at the skin "
        f"under it), the skull moved {moved * 1000:.1f} mm at most; its move smoothed over {n_sm} vertices")
    if cw_ is not None:
        log(f"skull: the crown held up to {float(cw_.max()) * 1000:.1f} mm further under the hair (skull_crown; "
            f"{int((cw_ > 0.001).sum())} vertices); the head's top now {float(P[in_body, 2].max()):.4f} m")
    return moved


def unfold(basemesh, V0, in_body, sel, rounds=30, steps=20):
    """Where the face fits folded the skin over itself (a triangle turned more than ~80 deg from the template's, or
    squashed to a tenth of its area: the landmark RBF pulls neighbouring landmarks up to a centimetre apart), the
    displacement from the template (V0) is relaxed: replaced by its neighbours' mean over the folded triangles' vertices
    and two rings round them, until nothing is folded. The template has no folds, so a locally smoother displacement
    gives the template's own shape back there (a flap under the left lower lid, nostrils torn open, creases at the
    inner eye corners and along the lip line). sel: the vertices it may move."""
    me = basemesh.data
    V = world_verts(basemesh)
    Tri = triangles(me)
    Tri = Tri[sel[Tri].all(1)]
    E = edges(me)
    E = E[in_body[E].all(1)]
    n = len(V)

    def frame(P):
        f = np.cross(P[Tri[:, 1]] - P[Tri[:, 0]], P[Tri[:, 2]] - P[Tri[:, 0]])
        a = np.linalg.norm(f, axis=1)
        return f / np.maximum(a, 1e-15)[:, None], a
    n0, a0 = frame(V0)
    D = V - V0

    def folded(P):
        f, a = frame(P)
        return ((f * n0).sum(1) < 0.2) | (a < 0.1 * a0)
    bad_t = folded(V)
    first = int(bad_t.sum())
    moved = np.zeros(n, bool)
    rnd = 0
    for rnd in range(rounds):
        if not bad_t.any():
            break
        x = np.zeros(n)
        x[np.unique(Tri[bad_t])] = 1.0
        for _ in range(2 + rnd // 5):
            x = np.maximum(x, (neighbour_mean(x, E, n) > 0).astype(np.float64))
        m = (x > 0) & sel
        moved |= m
        for _ in range(steps):
            nm = np.stack([neighbour_mean(D[:, k], E, n) for k in range(3)], 1)
            D[m] = nm[m]
        bad_t = folded(V0 + D)
    set_world_verts(basemesh, V0 + D, sel)
    left = (V0 + D)[Tri[bad_t]].mean(1)
    log(f"unfold: {first} folded face triangles -> {int(bad_t.sum())} ({int(moved.sum())} vertices relaxed, {rnd + 1} "
        f"rounds, at most {float(np.linalg.norm(V0 + D - V, axis=1).max()) * 1000:.1f} mm)"
        + (f"; left at {np.round(left, 3).tolist()[:4]}" if len(left) else ""))
    return moved


def seat_lashes(rig, basemesh, V0, L0, in_body):
    """Head scans: each eyelash strip (MakeHuman's four, a row of roots along the lid and a row of tips) is put back on
    its lid from the template (L0, V0): every vertex moves by the displacement of the skin under the root nearest to
    it. Moved by the face fits at their own places, the tips (their nearest skin the lid fold above) went up further
    than the roots and the left upper lashes stood upright, fanned off the lid."""
    V = world_verts(basemesh)
    D = V - V0
    body_i = np.nonzero(in_body)[0]
    kd = KDTree(len(body_i))
    for j, i in enumerate(body_i):
        kd.insert(V0[i], j)
    kd.balance()
    n = 0
    for obj in [o for o in rig.children if o.type == 'MESH' and o != basemesh and "lash" in o.name.lower()]:
        P0 = L0.get(obj.name)
        if P0 is None or len(P0) != len(obj.data.vertices):
            continue
        lab = components(len(P0), edges(obj.data))
        near = [kd.find(p) for p in P0]
        dist = np.array([h[2] for h in near])
        skin = np.array([body_i[h[1]] for h in near])
        out = np.zeros_like(P0)
        for c in np.unique(lab):
            idx = np.nonzero(lab == c)[0]
            # the roots: the vertices on the lid itself (the closest 40% took in upper lashes' tips, which curl up
            # close to the lid's fold: they rose with the fold, and the left upper lashes stood 2 mm taller)
            root = idx[dist[idx] <= max(np.percentile(dist[idx], 12), 0.0003)]
            for i in idx:
                r = root[np.argmin(np.linalg.norm(P0[root] - P0[i], axis=1))]
                out[i] = D[skin[r]]
        set_world_verts(obj, P0 + out)
        n += 1
    log(f"lashes: {n} object(s) seated back on their lids, strip by strip")


EYE_OPEN = 12.0                 # open_canthus: how far (deg) the outer corner of each eye turns back round its eyeball


def open_canthus(basemesh, rig, in_body, W, names, root, turn=EYE_OPEN, V0=None):
    """Head scans: the outer half of each eye's lids turned back round its eyeball, so the eye reads open in profile.
    The head scan's eye corners stand far forward (the corneas 6-7 mm in front of the outer corners, the template's
    9.2): seen from the side at dialogue distance the eye is a slit of lid and lashes. Each lid vertex beyond the
    eye's middle (by how far out it lies, all of it at the corner) turns about the vertical through its eyeball's
    centre by up to `turn` degrees, backwards: it stays on the eyeball's sphere, the corner goes back 2-3 mm; the skin
    round it follows by a smooth field fading out within 1.5 cm (solve_field). Both eyes alike."""
    if turn <= 0:
        return
    A = anchor_points(basemesh, root)
    anchors = json.load(open(os.path.join(root, "tools", "models", "mpfb_face_anchors.json")))["anchors"]
    V = world_verts(basemesh)
    E = edges(basemesh.data)
    E = E[in_body[E].all(1)]
    eyes = eye_objects(rig, basemesh)
    if not eyes:
        return
    EP = np.concatenate([world_verts(o) for o in eyes])
    mid = float((A[234][0] + A[454][0]) / 2) if 234 in A and 454 in A else float(V[in_body, 0].mean())
    T = np.zeros_like(V)
    c = np.zeros(len(V))
    dom = np.zeros(len(V), bool)
    report = []
    for ids, outer, inner in ((RIGHT_EYE, 33, 133), (LEFT_EYE, 263, 362)):
        if outer not in A or inner not in A:
            continue
        side = np.sign(A[outer][0] - mid)
        eb = EP[np.sign(EP[:, 0] - mid) == side]
        cen = eb.mean(0)
        rad = float(np.median(np.linalg.norm(eb - cen, axis=1)))
        lid_v = sorted({v for i in ids if i < len(anchors) and anchors[i] for v in anchors[i]["v"]})
        lid = nearest_landmark(V, V[lid_v]) < 0.003
        lid &= in_body
        # how far out along the eye (0 at its middle, 1 at the outer corner)
        ax = A[outer] - A[inner]
        half = float(np.linalg.norm(ax)) / 2
        ax /= max(np.linalg.norm(ax), 1e-9)
        s_ = ((V - (A[outer] + A[inner]) / 2) @ ax) / max(half, 1e-6)
        wv = smoothstep(0.1, 1.0, s_) * lid
        sgn = side            # turning backwards about +Z (the character faces -Y)
        for i in np.nonzero(wv > 1e-3)[0]:
            a = math.radians(turn) * float(wv[i]) * sgn
            q = V[i] - cen
            x, y = q[0] * math.cos(a) - q[1] * math.sin(a), q[0] * math.sin(a) + q[1] * math.cos(a)
            T[i] = np.array([cen[0] + x, cen[1] + y, V[i, 2]]) - V[i]
            c[i] = 5.0
        dom |= in_body & (np.linalg.norm(V - A[outer], axis=1) < 0.03) & (np.sign(V[:, 0] - mid) == side)
        held = dom & (nearest_landmark(V, V[lid_v]) > 0.003) & ((V - A[outer]) @ ax < -half * 0.2)
        c[held & (c == 0)] = 1.0
        corner = int(np.argmin(np.linalg.norm(V - A[outer], axis=1) + (~lid) * 1.0))
        report.append(f"{'right' if side < 0 else 'left'} corner back {T[corner, 1] * 1000:.1f} mm (eyeball radius "
                      f"{rad * 1000:.1f} mm)")
    far = in_body & ~dom
    c[far] = 0.0
    D, _ = solve_field(E, dom, T, c, rep=coincident(V)[0])
    set_world_verts(basemesh, V + D, in_body)
    log(f"eyes: the outer halves of the lids turned back up to {turn:.0f} deg round the eyeballs: " + "; ".join(report))


def settle_lashes(basemesh, rig, in_body, W, names, root, V0=None, L0=None, E0=None, max_turn=40.0, upper_drop=0.0):
    """Head scans, after seat_lashes: each lash strip turned about the line of its roots until its tips stand as high
    over (or as low under) its eyeball's centre as the template's strip did over the template's eyeball, never into the
    lid. Seated on the fitted lids the strips kept their angle to the template's lids, which the head scan's lids do not
    share: the left upper lashes stood 1.9 mm taller and 1 mm further forward than the right (8.6 against 6.7 mm over
    the eyeballs' centres), sparse and upright like a comb."""
    if V0 is None or L0 is None or not E0:
        return
    V = world_verts(basemesh)
    Tri = triangles(basemesh.data)
    Tri = Tri[in_body[Tri].all(1)]
    bvh = BVHTree.FromPolygons(V.tolist(), Tri.tolist(), all_triangles=True)
    EP = np.concatenate([world_verts(o) for o in eye_objects(rig, basemesh)])
    EP0 = np.concatenate([E0[o.name] for o in eye_objects(rig, basemesh) if o.name in E0])
    mid = float(V[in_body, 0].mean())
    cen = {s_: EP[np.sign(EP[:, 0] - mid) == s_].mean(0) for s_ in (-1.0, 1.0)}
    mid0 = float(V0[in_body, 0].mean())
    cen0 = {s_: EP0[np.sign(EP0[:, 0] - mid0) == s_].mean(0) for s_ in (-1.0, 1.0)}

    def inside(P):
        n = 0
        for p in P:
            loc, nn, _, dd = bvh.find_nearest(Vector(p), 0.01)
            if loc is not None and (Vector(p) - loc).dot(nn) < -0.0001:
                n += 1
        return n
    out = []
    for obj in [o for o in rig.children if o.type == 'MESH' and o != basemesh and "lash" in o.name.lower()]:
        P = world_verts(obj)
        P0 = L0.get(obj.name)
        if P0 is None or len(P0) != len(P):
            continue
        lab = components(len(P), edges(obj.data))
        rep = []
        # the template's own strips are not symmetric (its left upper lashes stand 2.2 mm over its right): both sides
        # go to the lower-lying upper strip's height, and to the mean of the lower strips'
        tpl = {}
        for cl in np.unique(lab):
            idx = np.nonzero(lab == cl)[0]
            s_ = float(np.sign(P0[idx, 0].mean() - mid0))
            up_ = P0[idx, 2].mean() > cen0[s_][2]
            tpl.setdefault(up_, []).append((P0[idx, 2].max() if up_ else P0[idx, 2].min()) - cen0[s_][2])
        # (the upper strips `upper_drop` lower than the template's: at its height the left upper lashes still stood
        # upright like a comb at 45 deg, the head scan's lid margin being lower under them)
        tgt = {True: min(tpl.get(True, [0.0])) - upper_drop, False: float(np.mean(tpl.get(False, [0.0])))}
        for cl in np.unique(lab):
            idx = np.nonzero(lab == cl)[0]
            s_ = float(np.sign(P[idx, 0].mean() - mid))
            upper = P[idx, 2].mean() > cen[s_][2]
            h0 = tgt[bool(upper)]
            d = np.array([bvh.find_nearest(Vector(p), 0.05)[3] or 0.05 for p in P[idx]])
            root_ = idx[d <= np.percentile(d, 15)]
            if len(root_) < 3:
                continue
            c_ = P[root_].mean(0)
            ax = np.linalg.svd(P[root_] - c_)[2][0]
            n_in = inside(P[idx])
            hz = lambda Q: (Q[:, 2].max() if upper else Q[:, 2].min()) - cen[s_][2]
            best = (abs(hz(P[idx]) - h0), 0.0, P[idx])
            for deg in np.arange(-max_turn, max_turn + 0.1, 1.0):
                if deg == 0:
                    continue
                R = np.array(Matrix.Rotation(math.radians(deg), 3, Vector(ax)))
                Q = (P[idx] - c_) @ R.T + c_
                e = abs(hz(Q) - h0)
                if e < best[0] - 1e-5 and inside(Q) <= n_in + 0.02 * len(idx):
                    best = (e, float(deg), Q)
            rep.append(f"{'right' if s_ < 0 else 'left'} {'upper' if upper else 'lower'} {hz(P[idx]) * 1000:+.1f} -> "
                       f"{hz(best[2]) * 1000:+.1f} mm (template {h0 * 1000:+.1f}, turned {best[1]:+.0f} deg)")
            P[idx] = best[2]
        set_world_verts(obj, P)
        out.append(f"{obj.name}: " + ", ".join(rep))
    log("lashes: tips over the eyeballs' centres as the template's: " + "; ".join(out))


def lay_lashes(basemesh, rig, in_body, V0, L0, slack=0.0002, lay=0.12, most=0.003):
    """Head scans, after settle_lashes: every lash vertex `lay` times as far off its lid as the template's was off the
    template's (its distance to the nearest skin, along that skin's normal; the strip's correction smoothed along it,
    `most` at most). Seated and turned, the strips kept the template's curve while the head scan's lids are flatter:
    they stand over a millimetre off the lids, the upper lashes up like a comb, and holding them at the template's own
    distance does not bring them down."""
    if V0 is None or L0 is None:
        return
    V = world_verts(basemesh)
    Tri = triangles(basemesh.data)
    Tri = Tri[in_body[Tri].all(1)]
    bvh = BVHTree.FromPolygons(V.tolist(), Tri.tolist(), all_triangles=True)
    bvh0 = BVHTree.FromPolygons(V0.tolist(), Tri.tolist(), all_triangles=True)
    rep = []
    for obj in [o for o in rig.children if o.type == 'MESH' and o != basemesh and "lash" in o.name.lower()]:
        P = world_verts(obj)
        P0 = L0.get(obj.name)
        if P0 is None or len(P0) != len(P):
            continue
        E_ = edges(obj.data)
        corr = np.zeros_like(P)
        d1 = np.zeros(len(P))
        dd = np.zeros(len(P))
        for i in range(len(P)):
            l0, n0_, _, _ = bvh0.find_nearest(Vector(P0[i]), 0.02)
            l1, n1, _, _ = bvh.find_nearest(Vector(P[i]), 0.02)
            if l0 is None or l1 is None:
                continue
            h0 = max(float((Vector(P0[i]) - l0).dot(n0_)), 0.0)
            h1 = float((Vector(P[i]) - l1).dot(n1))
            d1[i], dd[i] = h1, h0
            if h1 > lay * h0 + slack:
                corr[i] = -np.array(n1) * min(h1 - lay * h0 - slack, most)
        # (smoothed along the strip twice: a third pass leaves the lashes standing further off the lids)
        for _ in range(2):
            corr = 0.5 * corr + 0.5 * np.stack([neighbour_mean(corr[:, k], E_, len(P)) for k in range(3)], 1)
        set_world_verts(obj, P + corr)
        for s_, nm in ((-1.0, "right"), (1.0, "left")):
            m = np.sign(P[:, 0] - float(V[in_body, 0].mean())) == s_
            if m.any():
                rep.append(f"{nm} {np.median(d1[m]) * 1000:.2f} -> {np.median(np.maximum(d1[m] - np.linalg.norm(corr[m], axis=1), 0)) * 1000:.2f}"
                           f" mm (template {np.median(dd[m]) * 1000:.2f})")
    log(f"lashes: laid {lay:.2f} times as far off the lids as the template's (median off the skin): " + "; ".join(rep))


def nostril_cavity(basemesh, in_body, root, occlusion=False):
    """How deep in a nostril each vertex lies (0-1): of 32 rays round its normal, the share that hit the face within
    3 cm, near the nose tip. With a sharp head scan the bake paints the template's nostril tubes, deeper than the
    scan's nostrils, with the skin round them (light shards inside dark nostrils); the cavity darkens them as the
    mouth's inside is darkened."""
    A = anchor_points(basemesh, root)
    if 1 not in A:
        z = np.zeros(len(basemesh.data.vertices))
        return (z, z) if occlusion else z
    V = world_verts(basemesh)
    Tri = triangles(basemesh.data)
    Tri = Tri[in_body[Tri].all(1)]
    N = vertex_normals(V, Tri)
    bvh = BVHTree.FromPolygons(V.tolist(), Tri.tolist(), all_triangles=True)
    k = np.arange(32) + 0.5
    phi, th = np.arccos(1 - 2 * k / 32), math.pi * (1 + 5 ** 0.5) * k
    dirs = np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], 1)
    occ = np.zeros(len(V))
    for i in np.nonzero(in_body & (np.linalg.norm(V - A[1], axis=1) < 0.03))[0]:
        hemi = dirs[dirs @ N[i] > 0.1]
        p = Vector(V[i] + N[i] * 2e-4)
        occ[i] = sum(bvh.ray_cast(p, Vector(d), 0.03)[0] is not None for d in hemi) / max(len(hemi), 1)
    # (from 0.2 the rims and the wings' creases darkened too: dark blobs round each nostril)
    cav = smoothstep(0.3, 0.55, occ)
    log(f"nostrils: {int((cav > 0.5).sum())} vertices inside them darkened")
    return (cav, occ) if occlusion else cav


def shape_from_portrait(basemesh, rig, face_hold, portrait, root, outline=True):
    """Give the face the portrait's proportions seen from the front. The scan's head is a guess from one
    full-body image (often a wider face); the portrait is the sharp likeness. After a similarity fit (scale,
    rotation, offset) of the portrait's landmarks onto the character's, what is left at each landmark (narrower
    jaw, higher cheekbones, eye spacing) moves the face sideways and up/down only, through the same Gaussian RBF
    as the landmark fit, at most 12 mm, faded out off the face. Depth stays the scan's. The eyeballs and teeth
    follow their own landmarks, rigidly. The texture projection then lands almost undistorted.
    outline=False (a head scan, already the portrait's face in 3D): the face's outline (OVAL) is not pulled; moved
    sideways by up to 12 mm and faded out off the face, it stood out from the side of the head."""
    lm_path = portrait + ".lm.json"
    if not os.path.exists(lm_path):
        subprocess.run([PY, os.path.join(root, "tools", "py", "landmarks.py"), portrait], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    faces = json.load(open(lm_path))["faces"]
    if not faces:
        log("portrait: no face found; shape left as the scan's")
        return
    L = np.array(faces[0]["pts"])[:, :2]
    A = anchor_points(basemesh, root)
    keys = [k for k in sorted(A) if k < len(L)]
    # a smiling portrait does not shape the mouth: pulling closed lips into a wide smile pushes the upper lip through
    # the lower lip and the lower lip through the chin (zigzag tears at three-quarter view). The mouth keeps the
    # scan's shape there; the projection still paints the portrait's lips onto it. Smile = how far the mouth corners
    # sit above the lip line, over the mouth's width.
    smile = float(((L[13] + L[14]) / 2 - (L[61] + L[291]) / 2)[1] / max(np.linalg.norm(L[291] - L[61]), 1e-6))
    if smile > 0.09:
        keys = [k for k in keys if k not in set(LIPS)]
        log(f"portrait: smiling ({smile:.2f}); the lips keep the scan's shape")
    if not outline:
        deep = deep_eye_anchors(A)
        keys = [k for k in keys if k not in set(OVAL) and k not in deep]
    S = np.array([[A[k][0], A[k][2]] for k in keys])            # front view: x right, z up
    P = np.array([[L[k][0], -L[k][1]] for k in keys])           # portrait: y down -> up

    def onto(S):
        """similarity portrait -> character's front view (Umeyama): the portrait's landmarks there"""
        mp, ms = P.mean(0), S.mean(0)
        Pc, Sc = P - mp, S - ms
        U, sv, Vt = np.linalg.svd(Sc.T @ Pc)
        R = U @ np.diag([1.0, np.sign(np.linalg.det(U @ Vt))]) @ Vt
        sc = sv.sum() / (Pc ** 2).sum()
        return (Pc @ R.T) * sc + ms, sc
    pose, Rp, c3 = "", np.eye(3), np.zeros(3)
    if not outline:
        # (a head scan) the portrait's head is seen a little turned or nodded against the character's: a nod lifts
        # what stands out in front (nose tip, lips, chin) against the eyes. Read in the front plane alone it would
        # count as shape and move the nose tip, the lips and the chin up by several millimetres. The character's
        # landmarks are seen from the turn and nod that fit the portrait best (a 0.5 degree grid), so only what
        # differs beyond the pose moves the face
        X3 = np.array([A[k] for k in keys])
        c3 = X3.mean(0)
        best = (np.inf, 0.0, 0.0, S, np.eye(3))
        for nod in np.arange(-15.0, 15.01, 0.5):
            for turn in np.arange(-10.0, 10.01, 0.5):
                Rx = np.array(Matrix.Rotation(math.radians(nod), 3, 'X'))
                Rz = np.array(Matrix.Rotation(math.radians(turn), 3, 'Z'))
                Sr = ((X3 - c3) @ (Rz @ Rx).T + c3)[:, [0, 2]]
                Tg, _ = onto(Sr)
                e = float(((Tg - Sr) ** 2).sum(1).mean() / ((Sr - Sr.mean(0)) ** 2).sum(1).mean())
                if e < best[0]:
                    best = (e, nod, turn, Sr, Rz @ Rx)
        e0 = float(np.sqrt(((onto(S)[0] - S) ** 2).sum(1).mean()))
        S, Rp = best[3], best[4]
        e1 = float(np.sqrt(((onto(S)[0] - S) ** 2).sum(1).mean()))
        pose = (f"; the portrait seen nodded {best[1]:+.1f} deg and turned {best[2]:+.1f} deg against the character "
                f"(residual rms {e0 * 1000:.1f} -> {e1 * 1000:.1f} mm)")
    Tgt, sc = onto(S)
    res = Tgt - S
    n = np.linalg.norm(res, axis=1, keepdims=True)
    res *= np.minimum(1.0, 0.012 / np.maximum(n, 1e-9))
    X = np.array([A[k] for k in keys])
    D = np.zeros((len(keys), 3))
    D[:, 0], D[:, 2] = res[:, 0], res[:, 1]
    Xf, Df = X, D
    hold = None
    if not outline:
        # (a head scan) its chin stays the head scan's: a front view reads the chin a few millimetres shorter, and the
        # field, pulled up there and free at the outline, would raise it and pull it back in profile. Held as data
        # (zero at its 10 landmarks inside a field moving the lips and cheeks round them) it comes out a faceted point
        # with a hard V under it, so its landmarks give no data and the field fades out smoothly round them
        # (CHIN_HOLD)
        sel = [j for j, k in enumerate(keys) if k not in CHIN_PIN]
        Xf, Df = X[sel], D[sel]
        Cp = np.array([A[k] for k in CHIN_PIN if k in A])
        hold = lambda P: smoothstep(CHIN_HOLD[0], CHIN_HOLD[1], nearest_landmark(P, Cp))[:, None] if len(Cp) else 1.0
    field = Field(Xf, Df)
    if hold is not None:
        _f = field
        field = lambda P: _f(P) * hold(P)
    V = world_verts(basemesh)
    w = np.clip(face_hold, 0, 1)[:, None]
    set_world_verts(basemesh, V + field(V) * w)

    def shift(ids):
        sel = [j for j, k in enumerate(keys) if k in ids]
        return D[sel].mean(0) if sel else np.zeros(3)

    for obj in [o for o in rig.children if o.type == 'MESH' and o != basemesh]:
        Po = world_verts(obj)
        name = obj.name.lower()
        if "high-poly" in name or "low-poly" in name:
            d = np.zeros_like(Po)
            for ids in (RIGHT_EYE, LEFT_EYE):
                c = np.array([A[i] for i in ids if i in A]).mean(0)
                side = np.sign(c[0] - Po[:, 0].mean())
                d[np.sign(Po[:, 0] - Po[:, 0].mean()) == side] = shift(ids)
        elif "teeth" in name or "tongue" in name:
            d = np.repeat(shift(LIPS)[None], len(Po), 0)
        elif "glasses" in name:
            d = np.repeat(np.median(field(Po), 0)[None], len(Po), 0)
        else:
            d = field(Po)
        set_world_verts(obj, Po + d)
    # fine pass: the eyelids and lips change shape over millimetres (how open the eyes are, the lip line),
    # below what the first pass can express; their eyeballs and teeth stay put
    A2 = anchor_points(basemesh, root)
    # not the inner lip line: on a closed mouth its upper and lower landmarks sit on one spot, and moving them with
    # a 7 mm field dragged the upper and lower lips through each other (Joaquin's smile tore along the lip line)
    fine = [j for j, k in enumerate(keys) if k in set(RIGHT_EYE + LEFT_EYE + LIPS) - set(INNER_LIPS)]
    X2 = np.array([A2[keys[j]] for j in fine])
    r2 = Tgt[fine] - ((X2 - c3) @ Rp.T + c3)[:, [0, 2]]
    n2 = np.linalg.norm(r2, axis=1, keepdims=True)
    r2 *= np.minimum(1.0, 0.004 / np.maximum(n2, 1e-9))
    D2 = np.zeros((len(fine), 3))
    D2[:, 0], D2[:, 2] = r2[:, 0], r2[:, 1]
    field2 = Field(X2, D2, sigma=0.007)
    V = world_verts(basemesh)
    D2 = field2(V) * w
    set_world_verts(basemesh, V + D2)
    if not outline:
        # (a head scan) each lash moves with the lid vertex it grows from: moved by the field at its own place, a
        # lash's tip lagged its root by millimetres and the lashes stood upright off the lid
        held = np.nonzero(w[:, 0] > 0.5)[0]              # the face's own skin (not MakeHuman's helper lashes)
        kd = KDTree(len(held))
        for j, i in enumerate(held):
            kd.insert(V[i], j)
        kd.balance()
    for obj in [o for o in rig.children if o.type == 'MESH' and o != basemesh and "lash" in o.name.lower()]:
        Po = world_verts(obj)
        if outline:
            set_world_verts(obj, Po + field2(Po))
        else:
            set_world_verts(obj, Po + np.array([D2[held[kd.find(p)[1]]] for p in Po]))
    log(f"portrait shape: scale {sc:.5f} m/px, residual mean {np.linalg.norm(res, axis=1).mean() * 1000:.1f} mm, "
        f"max {np.linalg.norm(res, axis=1).max() * 1000:.1f} mm; eyelids and lips {np.linalg.norm(r2, axis=1).mean() * 1000:.1f} mm"
        + pose)


JAW_WIDEN = (0.16, 0.006, 0.35)  # widen_jaw at amount 1: the jaw angles this much wider (x), the chin lifted (m), and the
                                 # front of the lower face (mouth, chin) widened by this share of the jaw angles


def widen_jaw(basemesh, rig, in_body, W, names, root, amount):
    """Head scans: the lower face wider and the chin angle softer, by `amount` (the outfit's "head_scan_jaw": 0 leaves
    the head scan's face, 1 applies the full widening, 0.5 half of it). A head scan made from one portrait can come
    out narrower and longer below the cheekbones than reference photos taken at a matched camera. The face widens
    sideways about its middle, each point by JAW_WIDEN[0] x amount of its distance from it at the jaw angles and
    JAW_WIDEN[2] of that at the front of the lower face (the mouth's and the chin's outline), fading in from the
    cheekbones (the outline by the ears) down to the corners of the mouth and out behind the jaw angles, under the jaw
    into the neck and round the lips (the mouth keeps its width); the chin's underside rises by JAW_WIDEN[1] x amount,
    fading out up to the lower lip (a shorter, blunter chin). Moved before the lips, eyes and mouth inside are settled
    (follow_mouth, tuck_mouth), so they follow it."""
    if amount <= 0:
        return
    A = anchor_points(basemesh, root)
    need = (234, 454, 132, 361, 136, 365, 152, 17, 61, 291)
    if not all(i in A for i in need):
        log("jaw: landmarks missing; left as it is")
        return
    V = world_verts(basemesh)
    w_head = W[:, names.index("head")]
    mid = float((A[234][0] + A[454][0]) / 2)
    z_cb = float((A[234][2] + A[454][2]) / 2)
    # (the jaw angles, MediaPipe's 58 / 172 and 288 / 397, between 132 / 136 and 361 / 365 on the face's outline)
    z_gon = float((A[132][2] + A[136][2] + A[361][2] + A[365][2]) / 4)
    y_gon = float((A[132][1] + A[136][1] + A[361][1] + A[365][1]) / 4)
    z_mc = float((A[61][2] + A[291][2]) / 2)
    z_men, z_lip = float(A[152][2]), float(A[17][2])
    ears = ear_group(basemesh, in_body)
    near_ear = nearest_landmark(V, V[ears]) if ears.any() else np.full(len(V), 1.0)
    lips = np.array([A[i] for i in LIPS if i in A])
    near_lip = nearest_landmark(V, lips)
    # sideways: none at the cheekbones, all of it from the mouth's corners down; most at the jaw angles, a third of it
    # at the front of the lower face (the mouth's and the chin's outline)
    sz = 1.0 - smoothstep(z_mc, z_cb, V[:, 2])
    y_mc = float((A[61][1] + A[291][1]) / 2)
    sy = (JAW_WIDEN[2] + (1.0 - JAW_WIDEN[2]) * smoothstep(y_mc, y_gon, V[:, 1])) * \
        (1.0 - smoothstep(y_gon + 0.005, y_gon + 0.03, V[:, 1]))
    f = sz * sy * smoothstep(0.35, 0.85, w_head) * smoothstep(0.006, 0.018, near_lip) * \
        smoothstep(0.004, 0.015, near_ear) * in_body
    D = np.zeros_like(V)
    D[:, 0] = (V[:, 0] - mid) * JAW_WIDEN[0] * amount * f
    # the chin's underside up: all of it at and under the menton, none at the lower lip; only round the chin (not the
    # jaw line back to the ears)
    t = (z_lip - V[:, 2]) / max(z_lip - z_men, 1e-3)
    wc = smoothstep(0.15, 1.0, t) * (1.0 - smoothstep(0.02, 0.045, np.abs(V[:, 0] - mid))) * \
        (1.0 - smoothstep(float(A[152][1]) + 0.02, float(A[152][1]) + 0.045, V[:, 1])) * smoothstep(0.35, 0.85, w_head)
    D[:, 2] = JAW_WIDEN[1] * amount * wc * in_body
    set_world_verts(basemesh, V + D, in_body)
    A2 = anchor_points(basemesh, root)
    jw = lambda B: abs(B[365][0] - B[136][0])
    log(f"jaw: lower face up to {JAW_WIDEN[0] * amount * 100:.1f} % wider at the jaw angles (amount {amount:g}): jaw "
        f"{jw(A) * 1000:.1f} -> {jw(A2) * 1000:.1f} mm apart, mouth corners {abs(A[291][0] - A[61][0]) * 1000:.1f} -> "
        f"{abs(A2[291][0] - A2[61][0]) * 1000:.1f} mm; chin raised {D[:, 2].max() * 1000:.1f} mm "
        f"(moved {np.linalg.norm(D, axis=1).max() * 1000:.1f} mm at most)")


MOUTH_NARROW = 0.04     # narrow_mouth: the mouth this much narrower, corner to corner (head scans)


def narrow_mouth(basemesh, in_body, root, amount=MOUTH_NARROW):
    """Head scans: the mouth `amount` narrower, for a head scan whose mouth measures wider than the reference photos'
    (corner to corner over the eyes' spacing). The lips and the skin round them (fading out from 6 to 16 mm off the
    lips' outline) move in towards the face's middle, each by `amount` of its distance from it; before the mouth's
    inside, the teeth and the lips' colour are settled (follow_mouth, tuck_mouth, the portrait), so they follow."""
    A = anchor_points(basemesh, root)
    if not all(i in A for i in (61, 291, 0, 17)):
        return
    V = world_verts(basemesh)
    mid = float((A[61][0] + A[291][0]) / 2)
    lips = np.array([A[i] for i in LIPS if i in A])
    near = nearest_landmark(V, lips)
    zc = float((A[61][2] + A[291][2]) / 2)
    f = (1.0 - smoothstep(0.006, 0.016, near)) * (1.0 - smoothstep(0.012, 0.03, np.abs(V[:, 2] - zc))) * in_body
    D = np.zeros_like(V)
    D[:, 0] = -(V[:, 0] - mid) * amount * f
    set_world_verts(basemesh, V + D, in_body)
    A2 = anchor_points(basemesh, root)
    log(f"mouth: {amount * 100:.0f} % narrower: corners {abs(A[291][0] - A[61][0]) * 1000:.1f} -> "
        f"{abs(A2[291][0] - A2[61][0]) * 1000:.1f} mm apart (moved {np.abs(D[:, 0]).max() * 1000:.1f} mm at most)")


def ear_mask(basemesh, root, W, names, in_body):
    """The character's ears (behind and outside the face's side landmarks) keep their own skin texture:
    scanned ears are lumps under the hair and rarely line up with the body's ears."""
    A = anchor_points(basemesh, root)
    V = world_verts(basemesh)
    head = in_body & (W[:, names.index("head")] > 0.5)
    m = np.zeros(len(V))
    for i in (234, 454):
        t = A[i]
        side = np.sign(t[0])
        c = t + np.array([side * 0.008, 0.02, -0.005])
        d = np.linalg.norm(V - c, axis=1)
        # soft on every side: a hard edge in front of the ear shows as a seam down the cheek
        behind = smoothstep(t[1] - 0.012, t[1] + 0.006, V[:, 1])
        outside = smoothstep(abs(t[0]) - 0.025, abs(t[0]) - 0.008, V[:, 0] * side)
        m = np.maximum(m, head * behind * outside * (1.0 - smoothstep(0.03, 0.045, d)))
    return m


# ------------------------------------------------------------------ stance
def slice_parts(SV, z, half=0.006, gap=0.022):
    sel = SV[np.abs(SV[:, 2] - z) < half]
    if len(sel) < 8:
        return []
    o = np.argsort(sel[:, 0])
    cut = np.where(np.diff(sel[o, 0]) > gap)[0] + 1
    return [sel[g] for g in np.split(o, cut) if len(g) >= 4]


def centre(pts, z):
    c = (pts.min(0) + pts.max(0)) / 2
    c[2] = z
    return c


def arm_line(SV, side, z_top, z_bottom):
    """Centre line of one arm, top to fingertips: the outermost cross-section in each horizontal slice."""
    pts, misses = [], 0
    for z in np.arange(z_top, z_bottom, -0.008):
        parts = slice_parts(SV, z)
        arm = None
        if len(parts) >= 2:
            cand = parts[-1] if side > 0 else parts[0]
            if np.ptp(cand[:, 0]) < 0.18 and np.ptp(cand[:, 1]) < 0.22:
                c = centre(cand, z)
                if not pts or abs(c[0] - pts[-1][0]) < 0.04:
                    arm = c
        if arm is not None:
            pts.append(arm)
            misses = 0
        elif pts:
            misses += 1
            if misses >= 4:
                break
    return np.array(pts)


def leg_line(SV, hip_x, z_top, z_bottom):
    pts = []
    for z in np.arange(z_top, z_bottom, -0.01):
        parts = slice_parts(SV, z)
        if len(parts) < 2:
            continue
        cs = [centre(p, z) for p in parts]
        k = int(np.argmin([abs(c[0] - hip_x) for c in cs]))
        # this leg must be its own piece, not the two legs still joined at the crotch
        if parts[k][:, 0].min() < 0 < parts[k][:, 0].max():
            continue
        pts.append(cs[k])
    return np.array(pts)


def point_at(line, start, dist):
    """Walk from start through the polyline; the point at arc length dist (or the end)."""
    prev, run = np.asarray(start, float), 0.0
    for q in line:
        seg = np.linalg.norm(q - prev)
        if run + seg >= dist and seg > 1e-9:
            return prev + (q - prev) * ((dist - run) / seg)
        run += seg
        prev = q
    return prev


def arc_length(line, start):
    return float(np.linalg.norm(line[0] - start) + np.linalg.norm(np.diff(line, axis=0), axis=1).sum())


def aim(rig, name, target):
    pb = rig.pose.bones[name]
    t = rig.matrix_world.inverted() @ Vector(target)
    head = pb.head.copy()
    want = t - head
    if want.length < 1e-5:
        return
    q = (pb.tail - pb.head).rotation_difference(want)
    pb.matrix = Matrix.Translation(head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-head) @ pb.matrix
    bpy.context.view_layer.update()


def bone_head(rig, name):
    return np.array(rig.matrix_world @ rig.pose.bones[name].head)


def bone_tail(rig, name):
    return np.array(rig.matrix_world @ rig.pose.bones[name].tail)


def match_stance(rig, SV, V, W, names):
    """Pose arms and legs along the scan's limbs; feet flat and turned like the shoes."""
    for side, s in (("_l", 1.0), ("_r", -1.0)):
        # arm: shoulder -> elbow -> wrist -> fingertip, lengths shared out in the template's proportions
        S = bone_head(rig, "upperarm" + side)
        E0, Wr0 = bone_head(rig, "lowerarm" + side), bone_head(rig, "hand" + side)
        hand = sum(W[:, names.index(n)] for n in names if n.endswith(side) and n.startswith(HANDS))
        hv = V[hand > 0.5]
        F0 = hv[np.argmax((hv - Wr0) @ (Wr0 - E0) / np.linalg.norm(Wr0 - E0))]
        L = [np.linalg.norm(E0 - S), np.linalg.norm(Wr0 - E0), np.linalg.norm(F0 - Wr0)]
        line = arm_line(SV, s, S[2] - 0.12, 0.25)
        if len(line) < 10:
            log("arm" + side, "not found in the scan; left as is")
        else:
            total = arc_length(line, S)
            if total > 0.75 * sum(L):
                k = total / sum(L)
                E = point_at(line, S, L[0] * k)
                Wr = point_at(line, S, (L[0] + L[1]) * k)
                tip = line[-1]
            else:
                # the slices lost the arm part way (sleeve touching the body): keep it straight towards the end
                d = (line[-1] - S) / np.linalg.norm(line[-1] - S)
                E, Wr, tip = S + d * L[0], S + d * (L[0] + L[1]), S + d * sum(L)
            aim(rig, "upperarm" + side, E)
            aim(rig, "lowerarm" + side, Wr)
            aim(rig, "hand" + side, tip)
            ang = math.degrees(math.atan2(abs(E[0] - S[0]), S[2] - E[2]))
            log("arm" + side, f"{len(line)} slices, {total:.2f} m (template {sum(L):.2f}), {ang:.0f} deg from the body")
        # leg: hip -> knee -> ankle; the ankle where the template's ankle height is
        H = bone_head(rig, "thigh" + side)
        K0, A0 = bone_head(rig, "calf" + side), bone_head(rig, "foot" + side)
        line = leg_line(SV, H[0], H[2] - 0.12, A0[2] + 0.02)
        if len(line) < 10:
            log("leg" + side, "not found in the scan; left as is")
            continue
        Lt, Lc = np.linalg.norm(K0 - H), np.linalg.norm(A0 - K0)
        total = arc_length(line, H)
        K = point_at(line, H, total * Lt / (Lt + Lc))
        aim(rig, "thigh" + side, K)
        aim(rig, "calf" + side, line[-1])
        # foot flat on the floor (its rest orientation), turned to the shoe's long axis
        pb = rig.pose.bones["foot" + side]
        rest = pb.bone.matrix_local.copy()
        rest.translation = pb.head
        pb.matrix = rest
        bpy.context.view_layer.update()
        fh, bh = bone_head(rig, "foot" + side), bone_head(rig, "ball" + side)
        shoe = SV[(SV[:, 2] < 0.05) & (np.abs(SV[:, 0] - fh[0]) < 0.16) & (SV[:, 0] * s > 0.0)]
        if len(shoe) > 50:
            xy = shoe[:, :2] - shoe[:, :2].mean(0)
            ax = np.linalg.eigh(xy.T @ xy)[1][:, -1]
            if ax[1] > 0:
                ax = -ax
            cur = (bh - fh)[:2]
            yaw = math.atan2(cur[0] * ax[1] - cur[1] * ax[0], cur @ ax)
            yaw = max(-0.35, min(0.35, yaw))
            hd = pb.head.copy()
            pb.matrix = Matrix.Translation(hd) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Translation(-hd) @ pb.matrix
            bpy.context.view_layer.update()
            log("foot" + side, f"turned {math.degrees(yaw):+.0f} deg to the shoe")


# ------------------------------------------------------------------ skinning
def deform_weights(obj, names):
    idx = {obj.vertex_groups[n].index: k for k, n in enumerate(names) if n in obj.vertex_groups}
    W = np.zeros((len(obj.data.vertices), len(names)), np.float64)
    for v in obj.data.vertices:
        for g in v.groups:
            k = idx.get(g.group)
            if k is not None:
                W[v.index, k] = g.weight
    s = W.sum(1, keepdims=True)
    return np.divide(W, s, out=np.zeros_like(W), where=s > 1e-6)


def bone_matrices(rig, names):
    """Linear-blend skinning matrix of each bone in the current pose (world space, 3 x 4)."""
    mw = rig.matrix_world
    return np.array([np.array(mw @ rig.pose.bones[n].matrix @ rig.pose.bones[n].bone.matrix_local.inverted() @
                              mw.inverted())[:3, :4] for n in names])


def blend(W, Ms):
    A = np.einsum('nb,bij->nij', W, Ms)
    A[W.sum(1) < 1e-6] = np.eye(4)[:3]
    return A


def lbs(A, V):
    return np.einsum('nij,nj->ni', A[:, :, :3], V) + A[:, :, 3]


def unlbs(A, P):
    return np.einsum('nij,nj->ni', np.linalg.inv(A[:, :, :3]), P - A[:, :, 3])


def bone_segments(rig, P, W, names):
    """(head, tail, thickness, part) per bone; fingers fold into the hand, which reaches the fingertips."""
    segs = []
    owner = W.argmax(1)
    for k, n in enumerate(names):
        if n.startswith(HANDS[1:]):
            continue
        a, b = bone_head(rig, n), bone_tail(rig, n)
        if n.startswith("hand"):
            hv = P[sum(W[:, j] for j, m in enumerate(names) if m.endswith(n[-2:]) and m.startswith(HANDS)) > 0.5]
            b = hv[np.argmax(np.linalg.norm(hv - a, axis=1))]
        mine = P[(owner == k) & (W[:, k] > 0.5)]
        r = float(np.median(seg_dist(mine, a, b))) if len(mine) > 20 else 0.05
        segs.append((a, b, max(r, 0.025), part_of(n)))
    return segs


def label_points(SV, segs):
    """Body part of every scan vertex: the nearest bone, in units of that bone's thickness."""
    D = np.stack([seg_dist(SV, a, b) / r for a, b, r, _ in segs], 1)
    return np.array([segs[k][3] for k in D.argmin(1)])


def repose_scan(scan, rig, names, W, V, in_body):
    """Skin the scan to the skeleton posed in its stance (weights from the nearest body vertices of the same
    part, smoothed over the scan), then undo that pose: the scan now stands in the character's rest pose."""
    Ms = bone_matrices(rig, names)
    P0 = lbs(blend(W, Ms), V)
    SV = world_verts(scan)
    labels = label_points(SV, bone_segments(rig, P0, W, names))
    Wp = np.stack([sum(W[:, k] for k, n in enumerate(names) if part_of(n) == p) for p in range(len(PARTS))], 1)
    own = Wp.argmax(1)
    Ws = np.zeros((len(SV), len(names)))
    for p in range(len(PARTS)):
        src = np.nonzero(in_body & (own == p))[0]
        dst = np.nonzero(labels == p)[0]
        if len(src) == 0 or len(dst) == 0:
            continue
        kd = KDTree(len(src))
        for j, i in enumerate(src):
            kd.insert(P0[i], j)
        kd.balance()
        for s in dst:
            hits = kd.find_n(SV[s], 6)
            ws = np.array([1.0 / (h[2] + 0.004) for h in hits])
            Ws[s] = (ws[:, None] * W[src[[h[1] for h in hits]]]).sum(0) / ws.sum()
    E = edges(scan.data)
    Ws = smooth(Ws, np.ones(len(SV)), E, 8, lam=0.5)
    Ws /= np.maximum(Ws.sum(1, keepdims=True), 1e-9)
    set_world_verts(scan, unlbs(blend(Ws, Ms), SV))
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    log("scan re-posed to the rest pose:", {PARTS[p]: int((labels == p).sum()) for p in range(len(PARTS))})


# ------------------------------------------------------------------ wrap
def project(P, N, active, allowed, bvhs, conf_floor=0.3):
    """Each active vertex moves along its normal (either way) to the scan surface of its own body part, at most
    that part's reach; the nearest point is the fallback. Returns targets and a confidence per vertex."""
    T = P.copy()
    conf = np.zeros(len(P))
    for i in np.nonzero(active)[0]:
        p, n = Vector(P[i]), Vector(N[i])
        best = None
        for part in allowed[i]:
            bvh = bvhs.get(part)
            if bvh is None:
                continue
            for d in (n, -n):
                loc, hn, _, dist = bvh.ray_cast(p, d, REACH[part])
                if loc is not None and hn.dot(n) > 0.15 and (best is None or dist < best[1]):
                    best = (loc, dist, 1.0)
        if best is None:
            for part in allowed[i]:
                bvh = bvhs.get(part)
                if bvh is None:
                    continue
                loc, hn, _, dist = bvh.find_nearest(p, REACH[part] * 0.5)
                if loc is not None and hn.dot(n) > 0.3 and (best is None or dist < best[1]):
                    best = (loc, dist, conf_floor)
        if best is not None:
            T[i] = best[0]
            conf[i] = best[2]
    return T, conf


def wrap(basemesh, rig, scan, names, W, in_body, face_hold, ear, exclude=None):
    """Rest pose: move the body onto the re-posed scan. Returns the new positions and, per vertex, how much of the
    template's own skin texture to keep (the hands)."""
    me = basemesh.data
    V = world_verts(basemesh)
    Tri = triangles(me)
    Tri = Tri[in_body[Tri].all(1)]
    E = edges(me)
    E = E[in_body[E].all(1)]
    n = len(V)

    SV = world_verts(scan)
    ST = triangles(scan.data)
    if exclude is not None:
        # the hair shell is its own mesh: the body must not land on it (a neck inflated into the hair curtain)
        tp = np.empty(len(scan.data.loop_triangles), np.int64)
        scan.data.loop_triangles.foreach_get("polygon_index", tp)
        ST = ST[~exclude[tp]]
    labels = label_points(SV, bone_segments(rig, V, W, names))
    fp = labels[ST]
    fp = np.where((fp[:, 0] == fp[:, 1]) | (fp[:, 0] == fp[:, 2]), fp[:, 0], fp[:, 1])
    svl = SV.tolist()
    bvhs = {p: BVHTree.FromPolygons(svl, ST[fp == p].tolist(), all_triangles=True)
            for p in range(len(PARTS)) if (fp == p).any()}

    # parts each vertex may land on: its own, and any other it is skinned to by a fifth or more
    Wp = np.stack([sum(W[:, k] for k, nm in enumerate(names) if part_of(nm) == p) for p in range(len(PARTS))], 1)
    allowed = [list(np.nonzero(row > 0.2)[0]) or [int(row.argmax())] for row in Wp]

    # how far each vertex follows the scan: not the hands (fused in scans) nor the head (face fitted to the
    # landmarks, skull under the separate hair shell)
    w_hand = sum(W[:, k] for k, nm in enumerate(names) if nm.startswith(HANDS))
    w_head = W[:, names.index("head")]
    free = 1.0 - np.clip(w_hand + face_hold + w_head, 0, 1)
    free = smooth(free[:, None], np.ones(n), E, 4)[:, 0]
    free[(w_hand > 0.9) | (face_hold > 0.95) | (w_head > 0.9) | ~in_body] = 0.0
    active = free > 1e-3

    P = V.copy()
    for alpha, iters in ((0.6, 30), (0.85, 12), (1.0, 3)):
        N = vertex_normals(P, Tri)
        T, conf = project(P, N, active, allowed, bvhs)
        # a vertex that jumps much further than its neighbours found another surface (across a gap): ignore it
        dist = np.linalg.norm(T - P, axis=1)
        nb = neighbour_mean(dist * (conf > 0), E, n)
        conf[dist > 2.5 * nb + 0.015] = 0.0
        D = smooth(T - P, conf, E, iters)
        P = P + alpha * D * free[:, None]
    N = vertex_normals(P, Tri)
    T, conf = project(P, N, active, allowed, bvhs)
    err = np.linalg.norm(T - P, axis=1)[active & (conf > 0.5)]
    log(f"wrap: {int(active.sum())} vertices, residual median {np.median(err) * 1000:.1f} mm, "
        f"95% {np.percentile(err, 95) * 1000:.1f} mm, unmatched {int((active & (conf == 0)).sum())}")
    keep = np.clip(w_hand * 1.25 + ear, 0, 1)
    keep = smooth(keep[:, None], np.ones(n), E, 2)[:, 0]
    return P, keep


# ------------------------------------------------------------------ hair
def base_color_image(mat):
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    node = bsdf.inputs["Base Color"].links[0].from_node if bsdf.inputs["Base Color"].links else None
    while node is not None and node.type != 'TEX_IMAGE':
        node = next((i.links[0].from_node for i in node.inputs if i.links), None)
    return node.image if node is not None else None


BROWS = [70, 63, 105, 66, 107, 336, 296, 334, 293, 300]


def head_surface(basemesh, names, W, in_body, neck=False):
    V = world_verts(basemesh)
    head = in_body & (W[:, names.index("head")] > 0.5)
    if neck:
        head = in_body & (W[:, names.index("head")] + W[:, names.index("neck_01")] > 0.5)
    Tri = triangles(basemesh.data)
    Tri = Tri[head[Tri].all(1)]
    return BVHTree.FromPolygons(V.tolist(), Tri.tolist(), all_triangles=True)


def scan_colors(me, size=1024):
    """sRGB colour of every scan vertex, read from a small copy of its base colour texture."""
    if me.get("head_mat0") is not None:
        return scan_colors_by_material(me, size)
    img = base_color_image(me.materials[0]).copy()
    img.scale(size, size)
    px = np.empty(size * size * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(size, size, 4)
    bpy.data.images.remove(img)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    vuv = np.zeros((len(me.vertices), 2), np.float32)
    vuv[lv] = uv.reshape(-1, 2)
    return px[np.clip((vuv[:, 1] % 1) * size, 0, size - 1).astype(int),
              np.clip((vuv[:, 0] % 1) * size, 0, size - 1).astype(int), :3].astype(np.float64)


def scan_colors_by_material(me, size=1024):
    """scan_colors for a scan joined from two (a head scan spliced in): each vertex reads its own material's
    texture."""
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    vuv = np.zeros((len(me.vertices), 2), np.float32)
    vuv[lv] = uv.reshape(-1, 2)
    fm, ls, lt = (np.empty(len(me.polygons), np.int64) for _ in range(3))
    me.polygons.foreach_get("material_index", fm)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    order = np.argsort(ls)                       # polygons' loops tile the loop array in loop_start order
    vm = np.zeros(len(me.vertices), np.int64)
    vm[lv] = fm[np.repeat(order, lt[order])]
    out = np.zeros((len(me.vertices), 3))
    for k, mat in enumerate(me.materials):
        sel = vm == k
        if not sel.any():
            continue
        if mat is not None and mat.get("scan_fill_image") is not None:
            img = bpy.data.images.get(mat["scan_fill_image"])
            base = np.zeros((len(me.vertices), 3))
            if img is not None:
                im = img.copy()
                im.scale(size, size)
                px = np.empty(size * size * 4, np.float32)
                im.pixels.foreach_get(px)
                bpy.data.images.remove(im)
                px = px.reshape(size, size, 4)
                base[sel] = px[np.clip((vuv[sel, 1] % 1) * size, 0, size - 1).astype(int),
                               np.clip((vuv[sel, 0] % 1) * size, 0, size - 1).astype(int), :3]
            out[sel] = fill_colours(me, mat, base)[sel]
            continue
        if mat is None or base_color_image(mat) is None:
            log(f"scan colours: material {k} ({mat.name if mat else None}) has no colour texture; "
                f"its {int(sel.sum())} vertices read black (as hair)")
            continue
        img = base_color_image(mat).copy()
        img.scale(size, size)
        px = np.empty(size * size * 4, np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(size, size, 4)
        bpy.data.images.remove(img)
        out[sel] = px[np.clip((vuv[sel, 1] % 1) * size, 0, size - 1).astype(int),
                      np.clip((vuv[sel, 0] % 1) * size, 0, size - 1).astype(int), :3]
    return out


def to_lab(srgb):
    lin = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def kmeans(X, k, iters=12):
    """A few colour centres (deterministic: seeded at lightness quantiles)."""
    if len(X) <= k:
        return X.copy()
    C = X[np.argsort(X[:, 0])[np.linspace(0, len(X) - 1, k).astype(int)]].copy()
    for _ in range(iters):
        lab = ((X[:, None] - C[None]) ** 2).sum(-1).argmin(1)
        for j in range(k):
            if (lab == j).any():
                C[j] = X[lab == j].mean(0)
    return C


def poly_mask_components(me, vmask, min_faces=300):
    """Faces with at least two flagged vertices, keeping only connected pieces of min_faces or more."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    keep = {f.index for f in bm.faces if sum(vmask[v.index] for v in f.verts) >= 2}
    seen, pieces = set(), []
    for f0 in keep:
        if f0 in seen:
            continue
        stack, piece = [f0], []
        seen.add(f0)
        while stack:
            f = bm.faces[stack.pop()]
            piece.append(f.index)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index in keep and g.index not in seen:
                        seen.add(g.index)
                        stack.append(g.index)
        pieces.append(piece)
    bm.free()
    mask = np.zeros(len(me.polygons), bool)
    for piece in pieces:
        if len(piece) >= min_faces:
            mask[piece] = True
    return mask, sum(len(p) >= min_faces for p in pieces)


def segment_hair(scan, basemesh, rig, names, W, in_body, lms, long_hair):
    """Which scan faces are hair. Its colours are learnt from the scan itself: the crown (above the character's
    own skull) is surely hair and the torso surely clothes, and every other candidate takes the nearer of the
    two in Lab, so blonde, braided or two-tone hair works as well as black. Candidates sit outside the body,
    off the face, and above the skull base (short hair, within 6 cm of the skull) or above the shoulders (long
    hair; below that it lies on the back like a cape and stays part of the wrapped body)."""
    me = scan.data
    SV = world_verts(scan)
    V = world_verts(basemesh)
    Tri = triangles(basemesh.data)
    body = BVHTree.FromPolygons(V.tolist(), Tri[in_body[Tri].all(1)].tolist(), all_triangles=True)
    skull = head_surface(basemesh, names, W, in_body)
    lab = to_lab(scan_colors(me))
    top = float(V[in_body, 2].max())
    z_head = float(bone_head(rig, "head")[2])
    z_sh = float(bone_head(rig, "upperarm_l")[2])
    z_hip = float(bone_head(rig, "pelvis")[2])
    zmin = z_sh + 0.02 if long_hair else z_head - 0.015
    out = np.full(len(SV), -1.0)
    near = np.full(len(SV), 1.0)
    z_lo = min(zmin, z_head - 0.045) if me.get("head_mat0") is not None and not long_hair else zmin
    for i in np.nonzero(SV[:, 2] > z_lo)[0]:
        p = Vector(SV[i])
        loc, n, _, _ = body.find_nearest(p, 0.4)
        if loc is not None:
            out[i] = (p - loc).dot(n)
        loc, _, _, d = skull.find_nearest(p, 0.4)
        if loc is not None:
            near[i] = d
    L = np.array(list(lms.values()))
    brow_z = float(np.mean([lms[i][2] for i in BROWS if i in lms]))
    ear_y = float(np.mean([lms[i][1] for i in (234, 454, 127, 356) if i in lms] or [L[:, 1].max()]))
    face = np.zeros(len(SV), bool)
    for s0 in range(0, len(SV), 4000):
        face[s0:s0 + 4000] = np.sqrt(((SV[s0:s0 + 4000, None, :] - L[None]) ** 2).sum(-1).min(1)) < 0.018
    face |= (SV[:, 2] < brow_z) & (SV[:, 1] < ear_y + 0.005)
    seeds = (SV[:, 2] > top - 0.02) & (out > 0.005) & ~face
    if me.get("head_mat0") is not None and 10 in lms:
        # (a head scan: its skull now tucked under the scan's hair (tuck_skull), the scan's forehead stood out of the
        # lowered crown too and its skin became a hair colour; the hair then took in skin down the side of the neck)
        seeds &= SV[:, 1] > lms[10][1] + 0.015
    cloth = (SV[:, 2] > z_hip + 0.1) & (SV[:, 2] < z_sh - 0.12) & (np.abs(SV[:, 0]) < 0.12)
    if seeds.sum() < 30 or cloth.sum() < 30:
        log("hair: no crown or torso to learn colours from; dark-only rule")
        hairlike = (scan_colors(me) * np.array([0.2126, 0.7152, 0.0722])).sum(1) < 0.2
    else:
        Ch, Cc = kmeans(lab[seeds], 3), kmeans(lab[cloth], 4)
        dh = np.sqrt(((lab[:, None] - Ch[None]) ** 2).sum(-1).min(1))
        dc = np.sqrt(((lab[:, None] - Cc[None]) ** 2).sum(-1).min(1))
        hairlike = (dh < dc) & (dh < 28)
        log("hair colours (Lab):", np.round(Ch).astype(int).tolist(), "clothes:", np.round(Cc).astype(int).tolist())
    reach = 0.35 if long_hair else 0.06
    # a head scan's hair is sculpted in locks with grooves 1-2 cm deep between them (its surface dips within 4 mm of
    # the skull, or under it, over much of the back of the head) and runs down the nape: on its vertices the hair may
    # lie up to 2 cm in and start 4.5 cm under the head bone (short hair)
    n0 = me.get("head_mat0")
    head_v = np.zeros(len(SV), bool)
    if n0 is not None:
        fm = np.empty(len(me.polygons), np.int64)
        me.polygons.foreach_get("material_index", fm)
        lv = np.empty(len(me.loops), np.int64)
        me.loops.foreach_get("vertex_index", lv)
        lt = np.empty(len(me.polygons), np.int64)
        me.polygons.foreach_get("loop_total", lt)
        head_v[lv[np.repeat(fm, lt) >= n0]] = True
    out_min = np.where(head_v, -0.02, 0.004)
    zmin_v = np.where(head_v & (not long_hair), z_head - 0.045, zmin)
    if n0 is not None and not long_hair:
        # (behind the ears no lower than without a head scan: down to the seam the cards hang 3 cm lower on the nape,
        # and with the head tilted up their vertices go into the neck; the nape's skin is painted dark hair down to
        # the hood instead, nape_paint)
        zmin_v = np.where(head_v & (SV[:, 1] > ear_y + 0.02), zmin, zmin_v)
    hair = ((SV[:, 2] > zmin_v) & (out > out_min) & ~face & hairlike & (near < reach)) | seeds
    cand = (SV[:, 2] > zmin_v) & ~face
    log(f"hair candidates {int(cand.sum())}: outside the body {int((cand & (out > out_min)).sum())}, hair-coloured "
        f"{int((cand & hairlike).sum())}, near the skull {int((cand & (near < reach)).sum())}; all {int(hair.sum())} "
        f"(crown seeds {int(seeds.sum())})")
    mask, pieces = poly_mask_components(me, hair)
    log(f"hair: {int(mask.sum())} faces in {pieces} pieces ({'long, down to the shoulders' if long_hair else 'short'})")
    return mask


HAIR_SIDE = 0.014       # fit_hair: how far the hair over the temples and the ears' tops is moved out sideways (m)
HAIR_DROP = 0.022       # ... and how far its edge on the sides comes down, over the ears' tops (m)
HAIR_EAR_CLEAR = 0.013  # ... and how far off the ears' outer sides it comes down (m)


def fit_hair(scan, mask, basemesh, rig, in_body, W, names, root, gap=0.008, side=HAIR_SIDE, drop=HAIR_DROP):
    """Head scans: the head scan's hair over the character's skull, and down and out over the temples and the ears'
    tops. tuck_skull keeps an adult skull (a head scan can be several centimetres short at the back): where it stands
    within `gap` of the hair's outer surface, or outside it, the hair moves out along the direction from the head's
    centre to `gap` over it. The head scan's hair lies close to the head at the temples and ends above the ears, where
    the reference photos show it fuller and down over the ears' tops. Its edge on the sides, from behind the temples
    back over the ears, comes down by up to `drop` (most over the ears, outside them), the scan's skin under it
    following within 3 cm (the bakes read it: the hair's colour comes down with it), and the hair over the sides, from
    that edge up to the brows (fading out up to the crown, behind the ears and in front of the temples), moves out
    sideways by up to `side`. Pushed out at brow level with its edge held where it was, the hair would stand out as
    two flat wings with the ears bare under them. The hairline in front of the temples lies flat on the skin (see
    below). One smooth field (solve_field) over the hair and that skin, zero where the hair's other edges meet the
    skin; solved again with the hairline held flat (laid flat after the solve, vertex by vertex, it would stand next
    to hair pushed out 15 mm and leave a straight trench at the temple). Returns the hair mask (unchanged)."""
    ears = ear_group(basemesh, in_body)
    V = world_verts(basemesh)
    w_head = W[:, names.index("head")]
    A = anchor_points(basemesh, root)
    if not all(i in A for i in (33, 133, 263, 362, 234, 454)):
        return mask
    hd = in_body & (w_head > 0.5) & ~ears
    Tb = triangles(basemesh.data)
    skull = BVHTree.FromPolygons(V.tolist(), Tb[hd[Tb].all(1)].tolist(), all_triangles=True)
    mid = float((A[234][0] + A[454][0]) / 2)
    cr, cl = (A[33] + A[133]) / 2, (A[263] + A[362]) / 2
    iod = float(np.linalg.norm(cl - cr))
    ez = float((cr[2] + cl[2]) / 2)
    brow = float(np.mean([A[i][2] for i in BROWS if i in A]))
    ear_y = float((A[234][1] + A[454][1]) / 2)
    front = float(min(A[i][1] for i in (159, 145, 386, 374) if i in A)) if 159 in A else ear_y - 0.08
    lv = in_body & (np.abs(V[:, 2] - V[hd & (w_head > 0.9), 2].mean()) < 0.03) & (w_head > 0.9)
    c0 = np.array([mid, float((V[lv, 1].min() + V[lv, 1].max()) / 2), float(V[hd & (w_head > 0.9), 2].mean())])
    me = scan.data
    SV = world_verts(scan)
    # holes in the hair (a highlight or a grey patch on the head scan's hair taken for skin): left out, their faces
    # pinned the hair round them while it moved out (dents), and their rims stood in the air as edges of the hair
    # underlayer (up to 38 mm off the skin). Pieces of not-hair under 400 faces with hair all round become hair
    n_h = me.get("head_mat0")
    if n_h is not None:
        fm = np.empty(len(me.polygons), np.int64)
        me.polygons.foreach_get("material_index", fm)
        fv = np.empty(len(me.loops), np.int64)
        me.loops.foreach_get("vertex_index", fv)
        ls_ = np.empty(len(me.polygons), np.int64)
        me.polygons.foreach_get("loop_start", ls_)
        lt_ = np.empty(len(me.polygons), np.int64)
        me.polygons.foreach_get("loop_total", lt_)
        order = np.argsort(ls_)
        fi = np.repeat(order, lt_[order])
        other = ~mask & (fm >= n_h)
        sel = other[fi]
        lab = components(len(me.polygons) + len(SV), np.stack([fi[sel], len(me.polygons) + fv[sel]], 1))
        pl = lab[np.nonzero(other)[0]]
        ids, cnt = np.unique(pl, return_counts=True)
        # a piece touches the rest of the scan (the face, the neck, the body scan) if a vertex of it is on a face that
        # is neither hair nor in it
        vpiece = np.full(len(SV), -1, np.int64)
        vpiece[fv[sel]] = lab[fi[sel]]
        outer = set(np.unique(vpiece[fv[(~mask[fi]) & ~other[fi]]]).tolist())
        small = np.isin(pl, ids[(cnt < 400)]) & ~np.isin(pl, list(outer))
        if small.any():
            mask = mask.copy()
            mask[np.nonzero(other)[0][small]] = True
        log(f"hair: {int(small.sum())} faces in {len(set(pl[small].tolist()))} holes in it (not hair-coloured, hair all round) "
            f"taken in")
    T = triangles(me)
    tp = np.empty(len(me.loop_triangles), np.int64)
    me.loop_triangles.foreach_get("polygon_index", tp)
    hv = np.zeros(len(SV), bool)
    hv[np.unique(T[mask[tp]])] = True
    fixed = np.zeros(len(SV), bool)
    fixed[np.unique(T[~mask[tp]])] = True
    free = hv & ~fixed
    edge = hv & fixed
    # the hair's own open edges (a head scan's hair is often a shell with a free rim over the scalp) stay on it, out only
    # as far as the skull needs: pushed out sideways with the rest, the rim at the temples stood up to 44 mm off the skin
    Th_ = T[mask[tp]]
    e_ = np.sort(np.concatenate([Th_[:, [0, 1]], Th_[:, [1, 2]], Th_[:, [2, 0]]]), axis=1)
    ue_, cnt_ = np.unique(e_, axis=0, return_counts=True)
    rim = np.zeros(len(SV), bool)
    rim[ue_[cnt_ == 1].ravel()] = True
    rim &= free
    # the edge on the sides (from behind the temples back over the ears, low on the head) comes down
    Vb = world_verts(basemesh)
    lat = np.abs(SV[:, 0] - mid)
    y_t = front + 0.045                       # behind the temples' front (the brows' tails stay)
    if ears.any():
        Pe = Vb[ears]
        ear_front = float(np.percentile(Pe[:, 1], 5))
        ear_back = float(np.percentile(Pe[:, 1], 95))
        ear_top = float(np.percentile(Pe[:, 2], 97))
    else:
        Pe = np.zeros((0, 3))
        ear_front, ear_back, ear_top = ear_y - 0.015, ear_y + 0.03, ez + 0.01
    # (not where the edge already runs down behind the ear: only the edge at or over the ears' tops comes down)
    sr = edge & (lat > 0.045) & (SV[:, 2] < ez + 0.045) & (SV[:, 1] > y_t - 0.01) & (SV[:, 1] < ear_back + 0.02) & \
        (SV[:, 2] > ear_top - 0.015)
    fy = smoothstep(y_t - 0.01, y_t + 0.025, SV[:, 1]) * (1.0 - smoothstep(ear_back - 0.01, ear_back + 0.02, SV[:, 1])) \
        * smoothstep(ear_top - 0.015, ear_top - 0.005, SV[:, 2])
    over = smoothstep(ear_front - 0.015, ear_front, SV[:, 1])
    dz = np.where(sr, drop * fy * (0.7 + 0.3 * over), 0.0)
    sr &= dz > 0.0005
    Tgt = np.zeros_like(SV)
    c = np.zeros(len(SV))
    n_out = 0
    for i in np.nonzero(sr)[0]:
        t = np.array([0.0, 0.0, -dz[i]])
        if len(Pe):
            # over an ear: outside it, HAIR_EAR_CLEAR off its outer side at the height the edge comes down to
            sd_ = np.sign(SV[i, 0] - mid)
            near_e = (np.sign(Pe[:, 0] - mid) == sd_) & (np.abs(Pe[:, 1] - SV[i, 1]) < 0.01) & \
                (Pe[:, 2] > SV[i, 2] - dz[i] - 0.012)
            if near_e.any():
                need_x = float(np.abs(Pe[near_e, 0] - mid).max()) + HAIR_EAR_CLEAR - lat[i]
                if need_x > 0:
                    t[0] = sd_ * need_x
                    n_out += 1
        Tgt[i], c[i] = t, 5.0
    # the scan's skin under that edge follows (within 4 cm of it, the head scan's skin only, not round the face)
    band = np.zeros(len(SV), bool)
    if sr.any() and n_h is not None:
        hsv = np.zeros(len(SV), bool)
        hsv[np.unique(T[fm[tp] >= n_h])] = True
        kd = KDTree(int(sr.sum()))
        for j, i in enumerate(np.nonzero(sr)[0]):
            kd.insert(SV[i], j)
        kd.balance()
        cand = np.nonzero(hsv & ~hv & (lat > 0.035) & (SV[:, 1] > y_t - 0.02) & (SV[:, 2] > ez - 0.06))[0]
        for i in cand:
            if kd.find(SV[i])[2] < 0.04:
                band[i] = True
    fi = np.nonzero(free)[0]
    need = np.zeros(len(SV))
    for i in fi:
        d = SV[i] - c0
        r = float(np.linalg.norm(d))
        loc = skull.ray_cast(Vector(c0 + d / max(r, 1e-9) * 0.3), Vector(-d / max(r, 1e-9)), 0.3)[0]
        if loc is not None:
            need[i] = max(float(np.linalg.norm(np.array(loc) - c0)) + gap - r, 0.0)
    n_skull, worst = int((need > 0).sum()), float(need.max())
    # a rounded envelope of what the skull needs (each need spreads to `round_r` round it, falling off smoothly): pushed
    # out only where it was needed, the back of the head came out boxy, a flat back meeting the crown in a corner
    round_r = 0.035
    src = np.nonzero(need > 0.0005)[0]
    if len(src):
        kd = KDTree(len(src))
        for j, i in enumerate(src):
            kd.insert(SV[i], j)
        kd.balance()
        env = need.copy()
        for i in fi:
            for _, j, dist in kd.find_range(SV[i], round_r):
                env[i] = max(env[i], need[src[j]] * (1.0 - (dist / round_r) ** 2) ** 2)
        need = env
    for i in fi:
        p = SV[i]
        d = p - c0
        r = float(np.linalg.norm(d))
        if r < 1e-6:
            continue
        d /= r
        push = d * need[i]
        # the sides: out sideways over the temples and the ears' tops (most from the eyes' level to the brows)
        ws = smoothstep(0.3, 0.7, abs(float(d[0])))
        wz = smoothstep(ez - 1.2 * iod, ez - 0.5 * iod, p[2]) * (1.0 - smoothstep(brow + 0.2 * iod, brow + 1.3 * iod, p[2]))
        wy = smoothstep(front + 0.03, front + 0.06, p[1]) * (1.0 - smoothstep(ear_back + 0.0, ear_back + 0.035, p[1]))
        sv = side * float(ws * wz * wy)
        if sv > 1e-5:
            push = push + np.array([np.sign(p[0] - mid) * sv, 0.0, 0.0]) * (1.0 - min(1.0, float(push @ d) / max(sv, 1e-9))
                                                                               * 0.5)
        if rim[i]:
            Tgt[i], c[i] = d * need[i], 5.0
        elif float(np.linalg.norm(push)) > 1e-5:
            Tgt[i], c[i] = push, 1.0
    if not (c > 0).any():
        return mask
    dom = free | sr | band
    E = edges(me)
    E = E[(hv | band)[E].all(1)]
    D, its = solve_field(E, dom, Tgt, c, alpha=0.3, beta=3.0)
    # (the field may fall short of a need under it: what the skull needs is a floor)
    short = (c > 0) & ~sr & ((D * Tgt).sum(1) < (Tgt * Tgt).sum(1) * 0.95)
    D[short] = np.where(((D[short] * Tgt[short]).sum(1) < (Tgt[short] ** 2).sum(1))[:, None], Tgt[short], D[short])
    # the hairline flat on the skin in front of the temples: the head scan rolls its hair over at the forehead and the
    # temples into a lip a centimetre or two off the skin; the cards' underlayer drops the lip's underside (facing away
    # from the cards) and its edge then stood 2-4 cm off the forehead and temples, in the air. Within 4 rings of the
    # hair's edge (its edge itself too), in front of the temples and over the lobes, the hair comes in along the
    # direction from the head's centre to at most 4 mm plus 2 mm per ring over the skull: held there, the field is
    # solved again
    hairf = mask[tp]
    eh = np.sort(np.concatenate([T[hairf][:, [0, 1]], T[hairf][:, [1, 2]], T[hairf][:, [2, 0]]]), axis=1)
    eh = np.unique(eh, axis=0)
    ring = np.full(len(SV), 99, np.int64)
    ring[edge] = 0
    for k in range(1, 5):
        prev = ring == k - 1
        nb = np.zeros(len(SV), bool)
        nb[eh[prev[eh[:, 0]], 1]] = True
        nb[eh[prev[eh[:, 1]], 0]] = True
        ring[nb & hv & (ring > k)] = k
    SV1 = SV + D
    zone = free & (ring <= 4) & (SV1[:, 1] < front + 0.06) & (SV1[:, 2] > ez - 0.6 * iod)
    flat = 0
    for i in np.nonzero(zone)[0]:
        dd = SV1[i] - c0
        r = float(np.linalg.norm(dd))
        if r < 1e-6:
            continue
        dd /= r
        loc = skull.ray_cast(Vector(c0 + dd * 0.3), Vector(-dd), 0.3)[0]
        if loc is None:
            continue
        h = r - float(np.linalg.norm(np.array(loc) - c0))
        lim = 0.004 + 0.002 * ring[i]
        if h > lim:
            Tgt[i], c[i] = D[i] - dd * (h - lim), 10.0
            flat += 1
    if flat:
        D, its2 = solve_field(E, dom, Tgt, c, alpha=0.3, beta=3.0)
        its += its2
        short = (c > 0) & (c < 10.0) & ~sr & ((D * Tgt).sum(1) < (Tgt * Tgt).sum(1) * 0.95)
        D[short] = np.where(((D[short] * Tgt[short]).sum(1) < (Tgt[short] ** 2).sum(1))[:, None], Tgt[short], D[short])
    SV2 = SV + D
    set_world_verts(scan, SV2)
    mv = np.linalg.norm(D, axis=1)
    log(f"hair: its edge in front of the temples laid flat on the skin ({flat} vertices within 4 rings of it held at "
        f"4-12 mm over the skull in the field)")
    log(f"hair: its edge on the sides down by up to {float(dz.max()) * 1000:.0f} mm ({int(sr.sum())} vertices, {n_out} "
        f"of them out over an ear; {int(band.sum())} vertices of the scan's skin under it follow)")
    log(f"hair fitted over the skull and out at the sides: {n_skull} of its vertices within {gap * 1000:.0f} mm of the "
        f"skull or under it (by up to {worst * 1000:.1f} mm) moved out to {gap * 1000:.0f} mm over it, the temples and the "
        f"ears' tops out by up to {side * 1000:.0f} mm, its open rim ({int(rim.sum())} vertices) only as the skull needs; "
        f"{int((mv > 0.001).sum())} vertices moved, {mv.max() * 1000:.1f} mm at most ({its} steps)")
    return mask


def clear_ears(scan, mask, basemesh, in_body, clear=0.006, min_faces=300, lift=True, max_lift=0.012):
    """A head scan's hair, laid round its own ears (flatter and closer to the head than the template's, even once
    flatten_ears has turned them in), passes through the character's ears: the hair cards grown on it crossed the helix
    and filled the concha. Its faces within `clear` of an ear (MakeHuman's "ears" group) leave the hair shell, and so do
    the bits of it that cutting leaves on their own (under `min_faces`): cut at 14 mm round the ears, the shell lost the
    hair beside them (a narrow head of hair) and left pieces in front of them that grew loose clumps of cards on the skin.
    lift: the hair over an ear's outer side (its top and the helix, where the nearest ear point faces away from the head)
    is lifted off it to `clear` instead (at most `max_lift`; further in, it goes), the hair round it following smoothly,
    and stays: cut there, the hair would end above the ears in a straight edge and the head of hair would come out
    narrower than the portrait's. Behind the ear (between it and the head) it still goes. The scan's hair moves with
    it (the hair shell and the full head scan the bakes read are cut from it)."""
    ears = ear_group(basemesh, in_body)
    if not ears.any():
        return mask
    P = world_verts(basemesh)[ears]
    kd = KDTree(len(P))
    for i, p in enumerate(P):
        kd.insert(p, i)
    kd.balance()
    SV = world_verts(scan)
    T = triangles(scan.data)
    tp = np.empty(len(scan.data.loop_triangles), np.int64)
    scan.data.loop_triangles.foreach_get("polygon_index", tp)
    near = np.zeros(len(SV), bool)
    Th = T[mask[tp]]
    cand = np.unique(Th)
    # the hair cards smooth the shell first (hair_scan_cards.taubin: 10 lambda/mu steps; their underlayer lies 1.5 mm
    # under it): a face a little further off can come through the ear once smoothed (the underlayer cut through the
    # concha of an ear turned in by flatten_ears). Both its places count
    e = np.sort(np.concatenate([Th[:, [0, 1]], Th[:, [1, 2]], Th[:, [2, 0]]]), axis=1)
    u, cnt = np.unique(e, axis=0, return_counts=True)
    is_b = cnt == 1
    on_b = np.zeros(len(SV), bool)
    on_b[u[is_b].ravel()] = True
    a_, b_ = u[:, 0], u[:, 1]
    ia, ib = ~on_b[a_] | is_b, ~on_b[b_] | is_b
    deg = np.zeros(len(SV))
    np.add.at(deg, a_[ia], 1.0)
    np.add.at(deg, b_[ib], 1.0)
    ok = deg > 0
    S = SV.copy()
    for _ in range(10):
        for f in (0.5, -0.53):
            acc = np.zeros_like(S)
            np.add.at(acc, a_[ia], S[b_[ia]])
            np.add.at(acc, b_[ib], S[a_[ib]])
            Lp = np.zeros_like(S)
            Lp[ok] = acc[ok] / deg[ok, None] - S[ok]
            S = S + f * Lp
    # and what lies inside the head by the ears (the hair cards push it out along the skin's normal there: through the
    # concha, as a black shard)
    Vb = world_verts(basemesh)
    Tb = triangles(basemesh.data)
    Tb = Tb[in_body[Tb].all(1)]
    bvh = BVHTree.FromPolygons(Vb.tolist(), Tb.tolist(), all_triangles=True)
    NS = vertex_normals(S, Th)
    inside = 0
    Dl = np.zeros_like(SV)
    if lift:
        Ne = vertex_normals(Vb, Tb)[ears]
        mid = float(Vb[in_body, 0].mean())
        # only vertices of hair faces alone move (the skin round the hair stays on the scan)
        fixed = np.ones(len(SV), bool)
        fixed[np.unique(Th)] = False
        fixed[np.unique(T[~mask[tp]])] = True
        # over the ear: above its middle (behind its lower half the hair goes, as before)
        ez = np.zeros(len(P))
        for side in (-1.0, 1.0):
            e_ = np.sign(P[:, 0] - mid) == side
            if e_.any():
                ez[e_] = np.percentile(P[e_, 2], 50)
        too_far = np.zeros(len(SV), bool)
        for _ in range(3):
            for i in cand:
                if fixed[i] or too_far[i]:
                    continue
                q_ = SV[i] + Dl[i]
                _, j, d = kd.find(q_)
                if d >= clear + 0.002 or q_[2] < ez[j]:
                    continue
                n = Ne[j]
                if n[0] * np.sign(P[j][0] - mid) < -0.2 and n[2] < 0.5:
                    continue                            # behind the ear: left to the cut below
                need = clear + 0.002 - float((q_ - P[j]) @ n)
                if need > 0:
                    Dl[i] += n * need
                    if np.linalg.norm(Dl[i]) > max_lift:
                        Dl[i] = 0.0
                        too_far[i] = True
        lifted = np.linalg.norm(Dl, axis=1) > 1e-6
        if lifted.any():
            # spread over the hair (6 mm edges: ~4 cm), the lifted ones held
            hold = lifted | fixed
            for _ in range(40):
                acc = np.zeros_like(Dl)
                cnt_ = np.zeros(len(SV))
                np.add.at(acc, u[:, 0], Dl[u[:, 1]])
                np.add.at(acc, u[:, 1], Dl[u[:, 0]])
                np.add.at(cnt_, u[:, 0], 1.0)
                np.add.at(cnt_, u[:, 1], 1.0)
                free = ~hold & (cnt_ > 0)
                Dl[free] = 0.7 * acc[free] / cnt_[free, None]
            SV = SV + Dl
            S = S + Dl
            set_world_verts(scan, SV)
    for i in cand:
        d = min(kd.find(SV[i])[2], kd.find(S[i])[2])
        near[i] = d < clear
        if not near[i] and d < 0.025:
            for q in (SV[i], S[i] - NS[i] * 0.0015):
                loc, n, _, _ = bvh.find_nearest(Vector(q), 0.03)
                if loc is not None and (Vector(q) - loc).dot(n) < 0:
                    near[i] = True
                    inside += 1
                    break
    drop = np.zeros(len(mask), bool)
    np.logical_or.at(drop, tp, near[T].any(1))
    drop &= mask
    keep = mask & ~drop
    # the pieces cutting left on their own
    me = scan.data
    fv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", fv)
    ls = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", lt)
    order = np.argsort(ls)                       # polygons' loops tile the loop array in loop_start order
    fi = np.repeat(order, lt[order])
    sel = keep[fi]
    lab = components(len(me.polygons) + len(SV), np.stack([fi[sel], len(me.polygons) + fv[sel]], 1))
    pl = lab[np.nonzero(keep)[0]]
    ids, cnt = np.unique(pl, return_counts=True)
    small = np.isin(pl, ids[cnt < min_faces])
    keep[np.nonzero(keep)[0][small]] = False
    if lift:
        log(f"hair over the ears: {int((np.linalg.norm(Dl, axis=1) > 1e-6).sum())} vertices lifted off them, by up to "
            f"{np.linalg.norm(Dl, axis=1).max() * 1000:.1f} mm")
    log(f"hair: {int(drop.sum())} of its {int(mask.sum())} faces within {clear * 1000:.0f} mm of the ears or inside the "
        f"head beside them ({inside} vertices) left out, and "
        f"{int(small.sum())} more in {int((cnt < min_faces).sum())} pieces left on their own; {int(keep.sum())} faces in "
        f"{int((cnt >= min_faces).sum())} pieces")
    return keep


HAIR_ENV_TH = math.radians(150.0)   # hair_envelope: the cap's UVs reach this far from straight up (deg)
HAIR_COVER = {}         # hair_envelope_mesh: the head's centre and the cap texels the hair shell covers (paint_sideburns)
HAIR_EAR_CUT = 0.45     # hair_shell (head scans): the hair over each ear ends this far down it
HAIR_EAR_GAP = 0.016    # ... this far off the ears
HAIR_SIDE_OUT = 0.008   # ... and over and beside them this much further out


def _env_uv(P, c):
    d = np.asarray(P, np.float64) - c
    r = np.linalg.norm(d, axis=1)
    d = d / np.maximum(r, 1e-9)[:, None]
    th = np.arccos(np.clip(d[:, 2], -1.0, 1.0))
    ph = np.arctan2(d[:, 1], d[:, 0])
    rho = th / HAIR_ENV_TH * 0.49
    return np.stack([0.5 + rho * np.cos(ph), 0.5 + rho * np.sin(ph)], 1), r, th


def _env_dirs(U):
    p = (U - 0.5) / 0.49
    th = np.linalg.norm(p, axis=-1) * HAIR_ENV_TH
    ph = np.arctan2(p[..., 1], p[..., 0])
    return np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1)


def _env_raster(V, T, c, M, th_lim=math.radians(148.0), nearest=False):
    """The farthest (or nearest) of a mesh from c along every direction of the cap's M x M grid (-inf: none)."""
    out = np.full((M, M), np.inf if nearest else -np.inf)
    if not len(T):
        return out
    UV, r, th = _env_uv(V, c)
    T = np.asarray(T, np.int64)
    T = T[(th[T] < th_lim).all(1)]
    UVp = UV[T] * M
    T = T[((UVp.max(1) - UVp.min(1)) < 48).all(1)]
    ys, xs, tt, bb, _ = uv_texels(UV[T] * M, M, M)
    (np.minimum if nearest else np.maximum).at(out, (ys, xs), (bb * r[T[tt]]).sum(1))
    return np.where(np.isfinite(out), out, -np.inf)


def _bmax(m, r):
    return max_filter(max_filter(m, r, 0), r, 1)


def _bmin(m, r):
    return min_filter(min_filter(m, r, 0), r, 1)


def _norm_blur(X, m, sigma):
    den = gauss_blur(m.astype(np.float64), sigma)
    return gauss_blur(np.where(m, X, 0.0), sigma) / np.maximum(den, 1e-9), den


def _largest(m):
    lab = components_2d(m)
    if lab.max() <= 1:
        return m
    return lab == (1 + int(np.argmax(np.bincount(lab[lab > 0])[1:])))


def _fill_holes(m):
    lab = components_2d(~m)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    return m | ((lab > 0) & ~np.isin(lab, edge))


def hair_envelope_mesh(SV, ST, c, skin, ears, sides, z_nape, y_nape, brow=None, M=256, N=128, close=2, sigma=1.5, gap=0.006,
                       ear_gap=0.012, max_lift=0.015, ear_cut=0.45, nape_t=0.005, nape_mass=0.0, relief=(0.008, 0.018),
                       side_out=0.0):
    """Head scans: the hair shell as one clean height field over the directions from the head's centre c (the cap's
    UVs: azimuthal, the crown in the middle), the outermost of the scan's hair along each, its grooves closed over
    `close` texels and smoothed (normalised, so its rim keeps its own height), at least `gap` over the skin under it (the body's nearest surface from c) and
    `ear_gap` over the ears. Over each ear (`sides`: per side x sign, top and bottom z, front and back y) it ends at
    `ear_cut` of the ear's height under its top (wandering 3 mm); behind the ears it goes on down the nape to `z_nape`,
    lying `nape_t` over the skin at its lower end. `side_out`: the hair over and beside each ear, from 1-4 cm over its
    top down to the cut, that much further out. Returns vertices, triangles, per-vertex UVs and a few counts."""
    c = np.asarray(c, np.float64)
    Rh = _env_raster(SV, ST, c, M)
    Rk = _env_raster(skin[0], skin[1], c, M, nearest=True)
    Re = _env_raster(ears[0], ears[1], c, M)
    g = (np.arange(M) + 0.5) / M
    U = np.stack(np.meshgrid(g, g), -1)
    D = _env_dirs(U)
    have = np.isfinite(Rh)
    cov = _bmin(_bmax(have, 3), 3)
    cov = _fill_holes(cov)
    cov = _bmax(_bmin(cov, 2), 2) & cov
    cov = _largest(cov)
    Rf, _ = _norm_blur(np.where(have, Rh, 0.0), have, 2.0)
    Rf = np.where(have, Rh, Rf)
    Rd = _bmax(np.where(cov, Rf, -1.0), close)
    Rc = _bmin(np.where(cov, Rd, 10.0), close)
    Rc_s, _ = _norm_blur(Rc, cov, sigma)
    Rr_s, _ = _norm_blur(Rf, cov, 2.0)
    dist = np.zeros((M, M))
    m = cov.copy()
    for _ in range(10):
        dist += m
        m = _bmin(m, 1)
    R = Rr_s + smoothstep(2.0, 8.0, dist) * (Rc_s - Rr_s)
    # (and the curls' clumps as a gentle relief, `relief` = amplitude and scale (m), out from the rim: rebuilt this
    # smooth, the cards' normals agreed 0.98 with their neighbours' (the body scan's hair 0.96) and the key light lay
    # on the hair as one broad sheen, a helmet at 0.55 m)
    if relief and relief[0] > 0:
        P0 = (c + D * R[..., None]).reshape(-1, 3)
        rn = (value_noise(P0, relief[1], 13) + 0.6 * value_noise(P0, relief[1] * 0.45, 14)) / 1.6
        R = R + relief[0] * (2.0 * rn.reshape(M, M) - 1.0) * smoothstep(3.0, 9.0, dist)
    P = c + D * R[..., None]
    n0 = int(cov.sum())
    # over each ear: the hair ends a third of the way down it
    cut = np.zeros((M, M), bool)
    for s in sides:
        y = P[..., 1]
        ramp = smoothstep(s["y_front"] - 0.008, s["y_front"], y) * (1.0 - smoothstep(s["y_back"] + 0.002, s["y_back"] + 0.01, y))
        # (lower behind than in front, 8 mm over the ear's length, and ragged: 5 mm over 7 mm and 3 mm over 2 cm; at one
        # height, wandering 3 mm, the hair over the ear ended in a straight horizontal rim in the game at 0.6 m)
        yr = np.clip((P[..., 1] - s["y_front"]) / max(s["y_back"] - s["y_front"], 1e-3), 0.0, 1.0)
        zc = (s["z_top"] - ear_cut * (s["z_top"] - s["z_bot"]) - 0.008 * (yr - 0.3)
              + 0.005 * (2.0 * value_noise(P.reshape(-1, 3), 0.007, 5).reshape(M, M) - 1.0)
              + 0.003 * (2.0 * value_noise(P.reshape(-1, 3), 0.02, 6).reshape(M, M) - 1.0))
        on = cov & (s["sign"] * (P[..., 0] - c[0]) > 0.04) & (ramp > 0.5) & (P[..., 2] < zc)
        cut |= on
    if brow is not None:
        # (over the face's front, nothing within 15 mm over the brows: the rim there, feathered onto the skin with no
        # card over it, lay on the forehead over the brow's tail as a grey-blue wedge of underlayer under a key light)
        front = cov & (P[..., 1] < brow[1]) & (P[..., 2] < brow[0] + 0.015)
        cut |= front
    cov &= ~cut
    cov = _largest(_bmax(_bmin(cov, 1), 1) & cov)
    if side_out > 0:
        # (the hair over and beside the ears moved out by side_out, so the head of hair is not pinched at the temples
        # and the ears)
        P_ = c + D * R[..., None]
        out_ = np.zeros((M, M))
        for s in sides:
            ry = smoothstep(s["y_front"] - 0.025, s["y_front"] - 0.005, P_[..., 1]) * \
                (1.0 - smoothstep(s["y_back"] - 0.01, s["y_back"] + 0.012, P_[..., 1]))
            rz = 1.0 - smoothstep(s["z_top"] + 0.01, s["z_top"] + 0.04, P_[..., 2])
            lat = smoothstep(0.03, 0.055, s["sign"] * (P_[..., 0] - c[0]))
            out_ = np.maximum(out_, ry * rz * lat)
        out_s, _ = _norm_blur(out_, cov, 3.0)
        R = np.where(cov, R + side_out * out_s, R)
    # behind the ears: down the nape to z_nape
    Ps = c + D * np.where(np.isfinite(Rk), Rk, 0.0)[..., None]
    cand = ~cov & np.isfinite(Rk) & (Ps[..., 1] > y_nape) & (Ps[..., 2] >= z_nape) & (D[..., 2] < 0.3)
    grown = cov.copy()
    for _ in range(80):
        nxt = grown | (_bmax(grown, 1) & cand)
        if (nxt == grown).all():
            break
        grown = nxt
    new = grown & ~cov
    thick = np.clip(np.where(cov & np.isfinite(Rk), R - Rk, 0.0), 0.0, 0.03)
    tk, _ = _norm_blur(thick, cov & np.isfinite(Rk), 6.0)
    t_new = np.maximum(nape_t, tk * smoothstep(z_nape, z_nape + 0.03, Ps[..., 2]))
    R = np.where(new, np.where(np.isfinite(Rk), Rk, 0.0) + t_new, R)
    cov = grown
    HAIR_COVER.update(c=c.copy(), cov=cov.copy(), M=M)
    # (`nape_mass` > 0: behind the ears the hair comes down over the nape as a mass, from `nape_t` over the skin at its
    # lower end to nape_mass 4 cm higher. Off: the nape looks fuller from behind with it, but with the head tilted up
    # many more card vertices low on the nape go into the neck; the nape's dark matte look comes from its maps,
    # absent_maps)
    zs = Ps[..., 2]
    lift_n = np.zeros((M, M), bool)
    if nape_mass > 0:
        floor_t = (nape_t + (nape_mass - nape_t) * smoothstep(z_nape, z_nape + 0.04, zs)) * \
            (1.0 - smoothstep(z_nape + 0.05, z_nape + 0.075, zs))
        back = cov & np.isfinite(Rk) & (Ps[..., 1] > y_nape)
        lift_n = back & (R < Rk + floor_t)
        R = np.where(lift_n, np.where(np.isfinite(Rk), Rk, 0.0) + floor_t, R)
    # clear of the skin and the ears (only what lies under the hair: along the rim the rays reach the neck)
    for Rx, gx, lift in ((Rk, gap, max_lift), (Re, ear_gap, 0.025)):
        under = cov & np.isfinite(Rx) & (Rx + gx - R < lift)
        R = np.where(under, np.maximum(R, Rx + gx), R)
    R2, _ = _norm_blur(R, cov, 1.5)
    R = np.where(cov, R2, R)
    for Rx, gx, lift in ((Rk, gap, max_lift), (Re, ear_gap, 0.025)):
        under = cov & np.isfinite(Rx) & (Rx + gx - R < lift)
        R = np.where(under, np.maximum(R, Rx + gx), R)
    # the mesh: N x N nodes, each the mean of 2 x 2 texels (outside the hair the hair's value spread out)
    Rout, den = _norm_blur(np.where(cov, R, 0.0), cov, 4.0)
    Rfull = np.where(cov, R, Rout)
    k = M // N
    Rn = Rfull.reshape(N, k, N, k).mean((1, 3))
    cn = cov.reshape(N, k, N, k).mean((1, 3)) > 0.49
    gN = (np.arange(N) + 0.5) / N
    Un = np.stack(np.meshgrid(gN, gN), -1)
    Pn = c + _env_dirs(Un) * Rn[..., None]
    idx = -np.ones((N, N), np.int64)
    idx[cn] = np.arange(int(cn.sum()))
    a, b, cc, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    full = (a >= 0) & (b >= 0) & (cc >= 0) & (d >= 0)
    T = [np.stack([a[full], b[full], d[full]], 1), np.stack([a[full], d[full], cc[full]], 1)]
    for p, q, r_, miss in ((a, b, d, cc), (a, d, cc, b), (a, b, cc, d), (b, d, cc, a)):
        three = (p >= 0) & (q >= 0) & (r_ >= 0) & (miss < 0)
        T.append(np.stack([p[three], q[three], r_[three]], 1))
    T = np.concatenate(T)
    V = Pn[cn]
    UVv = Un[cn]
    # no bits on their own
    E = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    lab = components(len(V), E)
    big = np.bincount(lab).argmax()
    keepf = lab[T[:, 0]] == big
    T = T[keepf]
    used = np.unique(T)
    remap = -np.ones(len(V), np.int64)
    remap[used] = np.arange(len(used))
    stats = dict(texels=n0, cut_over_ears=int(cut.sum()), nape_added=int(new.sum()), nape_thickened=int(lift_n.sum()),
                 lifted=int((R > Rr_s + 1e-4).sum()))
    return V[used], remap[T], UVv[used], stats


def hair_env_inputs(basemesh, rig, in_body, W, names, root):
    """What hair_envelope_mesh needs from the fitted character: the head's centre (hair_scan_cards.frame_of's), the
    skin round the head and the ears (world triangles), each ear's extent, and where the nape's hair may end (as
    without a head scan: segment_hair's 1.5 cm under the head bone, behind the ears)."""
    A = anchor_points(basemesh, root)
    if not all(i in A for i in (33, 133, 263, 362, 159, 145, 386, 374)):
        return None
    eye = np.mean([A[i] for i in (33, 133, 362, 263)], 0)
    ef = float(min(A[i][1] for i in (159, 145, 386, 374))) - 0.0015
    c = np.array([eye[0], ef + 0.085, eye[2] + 0.02])
    V = world_verts(basemesh)
    T = triangles(basemesh.data)
    T = T[in_body[T].all(1)]
    T = T[np.linalg.norm(V[T].mean(1) - c, axis=1) < 0.2]
    eg = ear_group(basemesh, in_body)
    sides = []
    for sg in (-1.0, 1.0):
        e = eg & (sg * (V[:, 0] - c[0]) > 0)
        if e.sum() < 10:
            continue
        Ev = V[e]
        sides.append(dict(sign=sg, z_top=float(np.percentile(Ev[:, 2], 97)), z_bot=float(np.percentile(Ev[:, 2], 3)),
                          y_front=float(np.percentile(Ev[:, 1], 3)), y_back=float(np.percentile(Ev[:, 1], 97))))
    Te = T[eg[T].any(1)]
    y_nape = max([s["y_back"] for s in sides] or [float(c[1]) + 0.03]) + 0.005
    brow_z = float(np.mean([A[i][2] for i in BROWS if i in A]))
    return dict(c=c, skin=(V, T), ears=(V, Te), sides=sides, z_nape=float(bone_head(rig, "head")[2]) - 0.015,
                y_nape=y_nape, brow=(brow_z, ef + 0.045))


HAIR_EDGE_MAX = 0.012   # hair_shell (head scans): the shell's longest edge after fit_hair's stretch (m)


def hair_shell(scan, mask, cid, env=None):
    """The scan's hair faces as their own mesh with fresh UVs (bake_hair() gives it its own maps). A head scan's (with
    `env`, hair_env_inputs) is rebuilt as one clean height field over the head (hair_envelope_mesh): Tripo sculpts the
    hair in locks with undercuts and grooves 1-2 cm deep, and the cards take their shading normal from the guide
    (averaged over 12 mm): 2.1 % of their vertices faced into the head (0.4 % on a body scan's hair), lit from behind
    as black slashes, and the rest of the lumps as flat grey facets under a key light; its decimated, stretched
    triangles also left long slivers (a dark bar through the curls) and duplicate faces (the underlayer failed
    Blender's mesh check). Built over the directions from the head's centre it has no undercut (none of the cards'
    normals faces in; their neighbours' normals agree 0.98, the body scan's hair 0.96)."""
    bm = bmesh.new()
    bm.from_mesh(scan.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not mask[f.index]], context='FACES')
    n_split = 0
    if scan.data.get("head_mat0") is not None and env is not None:
        mw = np.array(scan.matrix_world)
        bm.verts.ensure_lookup_table()
        SV = np.array([v.co[:] for v in bm.verts], np.float64) @ mw[:3, :3].T + mw[:3, 3]
        ST = np.array([[v.index for v in f.verts] for f in bm.faces if len(f.verts) == 3], np.int64).reshape(-1, 3)
        quads = [[v.index for v in f.verts] for f in bm.faces if len(f.verts) == 4]
        if quads:
            q = np.array(quads, np.int64)
            ST = np.concatenate([ST, q[:, [0, 1, 2]], q[:, [0, 2, 3]]])
        bm.free()
        V, T, UVv, st_ = hair_envelope_mesh(SV, ST, env["c"], env["skin"], env["ears"], env["sides"], env["z_nape"],
                                            env["y_nape"], brow=env.get("brow"), ear_cut=HAIR_EAR_CUT,
                                            ear_gap=HAIR_EAR_GAP, side_out=HAIR_SIDE_OUT)
        inv = np.linalg.inv(mw)
        Vl = V @ inv[:3, :3].T + inv[:3, 3]
        new_me = bpy.data.meshes.new(f"{cid}.scanhair")
        new_me.from_pydata(Vl.tolist(), [], T.tolist())
        new_me.update()
        obj = bpy.data.objects.new(f"{cid}.scanhair", new_me)
        bpy.context.scene.collection.objects.link(obj)
        obj.matrix_world = scan.matrix_world.copy()
        uvl = new_me.uv_layers.new(name="UVMap")
        lv = np.empty(len(new_me.loops), np.int64)
        new_me.loops.foreach_get("vertex_index", lv)
        uvl.data.foreach_set("uv", UVv[lv].astype(np.float32).ravel())
        for p in new_me.polygons:
            p.use_smooth = True
        ok = new_me.validate(verbose=False)
        off = np.linalg.norm(V - env["c"], axis=1)
        log(f"hair shell: one height field over the head from its centre ({len(V)} vertices, {len(T)} triangles, "
            f"{uv_islands(new_me)} UV island; the scan's hair over {st_['texels']} of the cap's texels, "
            f"{st_['cut_over_ears']} cut over the ears ({100 * HAIR_EAR_CUT:.0f} % down them, {HAIR_EAR_GAP * 1000:.0f} mm off them, {HAIR_SIDE_OUT * 1000:.0f} mm further out over them) and the brows, {st_['nape_added']} added down "
            f"the nape to z {env['z_nape']:.3f}, {st_['nape_thickened']} thickened over the nape; {st_['lifted']} lifted by the closing or off the skin; mesh "
            f"{'fixed by validate' if ok else 'valid'}; {off.min() * 1000:.0f}-{off.max() * 1000:.0f} mm from the centre)")
        return obj
    if scan.data.get("head_mat0") is not None:
        # (fit_hair stretches the shell where it moves the hair out over the temples and the ears' tops, leaving long
        # slivers along a crease that the cards' smoothing cannot round with so few vertices; the underlayer then
        # shows through the cards as a straight dark bar. Edges over `HAIR_EDGE_MAX` are halved until none is)
        mw = scan.matrix_world.copy()
        for _ in range(6):
            long_ = [e for e in bm.edges if (mw @ e.verts[0].co - mw @ e.verts[1].co).length > HAIR_EDGE_MAX]
            if not long_:
                break
            n_split += len(long_)
            bmesh.ops.subdivide_edges(bm, edges=long_, cuts=1)
            bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    new_me = bpy.data.meshes.new(f"{cid}.scanhair")
    bm.to_mesh(new_me)
    bm.free()
    obj = bpy.data.objects.new(f"{cid}.scanhair", new_me)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = scan.matrix_world.copy()
    while new_me.uv_layers:
        new_me.uv_layers.remove(new_me.uv_layers[0])
    new_me.uv_layers.new(name="UVMap")
    new_me.materials.clear()
    if scan.data.get("head_mat0") is not None:
        # a head scan's hair is sculpted in locks (grooves 1-2 cm deep), decimated to uneven triangles: unwrapped as it
        # is (smart project, even of a smoothed copy) it fell into 1500-2700 islands, half its triangles under 14
        # texels, and the cards lost the strand direction painted in its texture (coherence 0). It is a cap round the
        # head instead: one island, by the direction of each point of its smoothed shape from the head's centre
        # (azimuthal equidistant about the vertical: the crown in the middle, the nape at the rim)
        co = np.empty(len(new_me.vertices) * 3, np.float64)
        new_me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3) @ np.array(obj.matrix_world)[:3, :3].T
        E = edges(new_me)
        S = co.copy()
        for _ in range(60):
            nm = np.stack([neighbour_mean(S[:, k], E, len(S)) for k in range(3)], 1)
            S += 0.6 * (nm - S)
            nm = np.stack([neighbour_mean(S[:, k], E, len(S)) for k in range(3)], 1)
            S -= 0.62 * (nm - S)                 # Taubin: smooth without shrinking it to a ball
        lo, hi = S.min(0), S.max(0)
        cen = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2] - 0.1])
        d = S - cen
        d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        th = np.arccos(np.clip(d[:, 2], -1, 1))
        ph = np.arctan2(d[:, 1], d[:, 0])
        rr = th / max(float(th.max()), 1e-6) * 0.49
        vuv = np.stack([0.5 + rr * np.cos(ph), 0.5 + rr * np.sin(ph)], 1)
        lv = np.empty(len(new_me.loops), np.int64)
        new_me.loops.foreach_get("vertex_index", lv)
        new_me.uv_layers.active.data.foreach_set("uv", vuv[lv].astype(np.float32).ravel())
        log(f"hair shell UVs: one cap round the head ({uv_islands(new_me)} islands; {n_split} edges over "
            f"{HAIR_EDGE_MAX * 1000:.0f} mm halved first, {len(new_me.polygons)} triangles)")
    else:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
        bpy.ops.object.mode_set(mode='OBJECT')
    for p in new_me.polygons:
        p.use_smooth = True
    return obj


def uv_islands(me):
    """How many UV islands a mesh has (faces joined where they share both UVs of an edge)."""
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = np.round(uv.reshape(-1, 2) * 1e5).astype(np.int64)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    _, uid = np.unique(np.stack([lv, uv[:, 0], uv[:, 1]], 1), axis=0, return_inverse=True)
    ls = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", lt)
    # a UV vertex per (vertex, uv); polygons' consecutive loops are UV edges
    E = []
    for s, t in zip(ls, lt):
        for k in range(t):
            E.append((uid[s + k], uid[s + (k + 1) % t]))
    E = np.array(E, np.int64).reshape(-1, 2)
    lab = components(int(uid.max()) + 1, E)
    return int(len(np.unique(lab[uid])))


def feather_hair(obj, bvh, zmin):
    """Taper the shell's cut edge at the hairline down onto the scalp (after baking, so the texture is
    unaffected): no step at the hairline, and the scalp under it carries the same baked hair colour. Edges
    below zmin (long hair cut at the shoulders, continuing as the cape on the back) stay where they are."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    mw = obj.matrix_world
    inv = mw.inverted()
    ring = {v.index: 0 for v in bm.verts if v.is_boundary and (mw @ v.co).z > zmin}
    frontier = list(ring)
    for k in range(1, 4):
        nxt = []
        for i in frontier:
            for e in bm.verts[i].link_edges:
                j = e.other_vert(bm.verts[i]).index
                if j not in ring:
                    ring[j] = k
                    nxt.append(j)
        frontier = nxt
    for i, k in ring.items():
        v = bm.verts[i]
        p = mw @ v.co
        loc, n, _, _ = bvh.find_nearest(p, 0.1)
        if loc is not None:
            v.co = inv @ p.lerp(loc + n * 0.0008, (1 - k / 4) ** 1.5)
    bm.to_mesh(obj.data)
    bm.free()


def finish_hair(obj, rig, maps):
    """Material from the baked maps, parented to the rig like the other parts. Skinned by height: rigid on the
    head down to the skull base, then blending into the neck and the upper back, so long hair resting on the
    shoulders stays on them when the head turns."""
    mat = bpy.data.materials.new(obj.name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    tc = nt.nodes.new('ShaderNodeTexImage')
    tc.image = maps["color"]
    nt.links.new(tc.outputs[0], bsdf.inputs["Base Color"])
    tn = nt.nodes.new('ShaderNodeTexImage')
    tn.image = maps["normal"]
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(tn.outputs[0], nm.inputs["Color"])
    nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    obj.data.materials.append(mat)
    z_head = float(bone_head(rig, "head")[2])
    z_neck = float(bone_head(rig, "neck_01")[2])
    Z = world_verts(obj)[:, 2]
    h = smoothstep(z_neck + 0.02, z_head, Z)
    nk = (1.0 - h) * smoothstep(z_neck - 0.06, z_neck + 0.01, Z)
    sp = 1.0 - h - nk
    for name, w in (("head", h), ("neck_01", nk), ("spine_03", sp)):
        vg = obj.vertex_groups.new(name=name)
        for i in np.nonzero(w > 1e-3)[0]:
            vg.add([int(i)], float(w[i]), 'REPLACE')
    mw = obj.matrix_world.copy()
    obj.parent = rig
    obj.matrix_world = mw
    mod = obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig


# ------------------------------------------------------------------ bake
def setup_cycles(scene):
    scene.render.engine = 'CYCLES'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'METAL'
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scene.cycles.device = 'GPU'
    except Exception as e:
        log("cycles on the CPU:", e)
    scene.cycles.samples = 4
    scene.render.bake.margin = 16


def emit_from(mat, what):
    """Rewire a glTF material's output to emit its base colour or roughness (or back to the BSDF)."""
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    if what == "bsdf":
        nt.links.new(bsdf.outputs[0], out.inputs[0])
        return
    em = nt.nodes.get("scan_emit") or nt.nodes.new('ShaderNodeEmission')
    em.name = "scan_emit"
    sock = bsdf.inputs["Base Color" if what == "color" else "Roughness"]
    for l in list(em.inputs[0].links):
        nt.links.remove(l)
    if sock.links:
        nt.links.new(sock.links[0].from_socket, em.inputs[0])
    else:
        v = sock.default_value
        em.inputs[0].default_value = tuple(v) if what == "color" else (v, v, v, 1.0)
    nt.links.new(em.outputs[0], out.inputs[0])


def poly_mean(me, vals):
    ls = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", lt)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    return np.add.reduceat(vals[lv], ls) / lt


def repack_head_uvs(obj, mask):
    """The head gets its own texture: its faces' UVs are packed to fill 0-1. In MakeHuman's single atlas the
    whole face gets only ~350 px of a 4K texture, which is why every face read as soft. The body keeps the
    rest of the atlas; the two never share an image, so the overlap does not matter."""
    me = obj.data
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(me)
    bm.faces.ensure_lookup_table()
    for v in bm.verts:
        v.select_set(False)
    for f in bm.faces:
        f.select_set(bool(mask[f.index]))
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(rotate=False, margin=0.003)
    bpy.ops.object.mode_set(mode='OBJECT')


def body_copy(basemesh, in_body, name):
    """A plain copy of the wrapped body (helpers removed) to bake into or out of."""
    me = basemesh.data.copy()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = basemesh.matrix_world.copy()
    if me.shape_keys:
        obj.shape_key_clear()
    return obj, me


def drop_helpers(me, in_body):
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not in_body[v.index]], context='VERTS')
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True


def bake_maps(basemesh, scan, in_body, keep, face_hold, head, work, head_faces=None, uvsrc=None, cavity=None, tag=""):
    """Bake the scan into the body's UVs from a copy of the wrapped body: colour, roughness, normal, plus a mask
    (R = keep the template's skin, G = inside the islands: 1, down to 0.6 deep in the mouth (cavity), B = 1 on the
    face, 0.5 elsewhere on the head).
    Alpha marks the texels a ray hit. With head_faces, the head's faces bake into their own images (*_head.png);
    uvsrc (a copy of the body with the old UVs and its own skin texture) then also resamples the template's
    skin into those new UVs (bake_skin*.png), for the parts that keep it. tag: in the files' names (bake_<map><tag>*.png:
    absent_bake's second bake)."""
    scene = bpy.context.scene
    setup_cycles(scene)
    obj, me = body_copy(basemesh, in_body, "scan_bake")
    attr = me.color_attributes.new("scan_mask", 'FLOAT_COLOR', 'POINT')
    b = np.where(face_hold > 0.5, 1.0, np.where(head, 0.5, 0.0))
    g = 1.0 - 0.4 * (cavity if cavity is not None else np.zeros_like(keep))
    c = np.stack([keep, g, b, np.ones_like(keep)], 1)
    attr.data.foreach_set("color", c.astype(np.float32).ravel())
    me.materials.clear()
    sets = [tag] + ([tag + "_head"] if head_faces is not None else [])
    if head_faces is not None:
        me.polygons.foreach_set("material_index", head_faces.astype(np.int32))
    drop_helpers(me, in_body)
    texs = []
    for suffix in sets:
        mat = bpy.data.materials.new("scan_bake" + suffix)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        em = nt.nodes.new('ShaderNodeEmission')
        at = nt.nodes.new('ShaderNodeAttribute')
        at.attribute_name = "scan_mask"
        nt.links.new(at.outputs["Color"], em.inputs[0])
        nt.links.new(em.outputs[0], out.inputs[0])
        texs.append((suffix, nt, nt.nodes.new('ShaderNodeTexImage')))
        me.materials.append(mat)

    def bake(name, kind, source, data, cage=0.04, reach=0.12):
        imgs = []
        for suffix, nt, tex in texs:
            img = bpy.data.images.new(f"scan_{name}{suffix}", TEX, TEX, alpha=True, float_buffer=False)
            img.colorspace_settings.name = 'sRGB' if data == "color" else 'Non-Color'
            tex.image = img
            nt.nodes.active = tex
            imgs.append((suffix, img))
        bpy.ops.object.select_all(action='DESELECT')
        if source is not None:
            source.select_set(True)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        kw = dict(type=kind, margin=16, use_clear=True, use_selected_to_active=source is not None)
        if source is not None:
            kw.update(cage_extrusion=cage, max_ray_distance=reach)
        bpy.ops.object.bake(**kw)
        for suffix, img in imgs:
            img.filepath_raw = os.path.join(work, f"bake_{name}{suffix}.png")
            img.file_format = 'PNG'
            img.save()
            bpy.data.images.remove(img)

    bake("mask", 'EMIT', None, "data")
    for m in scan.data.materials:
        emit_from(m, "color")
    bake("color", 'EMIT', scan, "color")
    for m in scan.data.materials:
        emit_from(m, "rough")
    bake("rough", 'EMIT', scan, "data")
    for m in scan.data.materials:
        emit_from(m, "bsdf")
    bake("normal", 'NORMAL', scan, "data")
    if uvsrc is not None:
        # same surface, old UVs: a tiny cage carries the template's own skin over to the new head UVs
        for what, data in (("skin", "color"), ("skinnormal", "data")):
            if uvsrc.get(what):
                emit_image(uvsrc.active_material, bpy.data.images[uvsrc[what]], data)
                bake(what, 'EMIT', uvsrc, data, cage=0.002, reach=0.01)
    bpy.data.objects.remove(obj)
    bpy.data.meshes.remove(me)
    for _, nt, _ in texs:
        pass
    for suffix in sets:
        bpy.data.materials.remove(bpy.data.materials["scan_bake" + suffix])


def emit_image(mat, img, data):
    """Make a material emit one image (used to resample the template's own maps into new UVs)."""
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    tx = nt.nodes.new('ShaderNodeTexImage')
    tx.image = img
    if data != "color":
        img.colorspace_settings.name = 'Non-Color'
    nt.links.new(tx.outputs[0], em.inputs[0])
    nt.links.new(em.outputs[0], out.inputs[0])


def uv_source(basemesh, in_body):
    """A copy of the wrapped body with the original UVs and a material slot for its own skin maps (taken
    before the head's UVs are repacked)."""
    obj, me = body_copy(basemesh, in_body, "scan_uvsrc")
    nt = basemesh.active_material.node_tree
    col = next(n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image and
               not any(l.to_node.type in ('NORMAL_MAP', 'BUMP') for o in n.outputs for l in o.links))
    nrm = next((n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image and
                any(l.to_node.type == 'NORMAL_MAP' for o in n.outputs for l in o.links)), None)
    obj["skin"] = col.image.name
    if nrm is not None:
        obj["skinnormal"] = nrm.image.name
    mat = bpy.data.materials.new("scan_uvsrc")
    mat.use_nodes = True
    me.materials.clear()
    me.materials.append(mat)
    drop_helpers(me, in_body)
    return obj


def run_compose(work, root, suffix, skin, skin_normal, out):
    job = {"work": work, "suffix": suffix, "skin": skin, "skin_normal": skin_normal,
           "out_color": out["color"], "out_normal": out["normal"], "out_rough": out["rough"]}
    job_path = os.path.join(work, f"compose_job{suffix}.json")
    json.dump(job, open(job_path, "w"))
    r = subprocess.run([PY, os.path.join(root, "tools", "py", "scan_compose.py"), job_path], capture_output=True, text=True)
    for line in (r.stdout + r.stderr).strip().splitlines()[-4:]:
        log(line)
    if r.returncode != 0:
        raise RuntimeError("scan_compose failed:\n" + r.stderr[-2000:])


def load_map(path, data):
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = 'sRGB' if data == "color" else 'Non-Color'
    return img


def compose(basemesh, cid, work, root, head=False, absent=False):
    """scan_compose.py turns the bakes into the final maps; they replace the skin material's images (and, with a
    separate head texture, go to the head material that split_materials() makes). absent (head scans): absent_bake's
    maps too, composed as a build without the head scan composes its own (basemesh["scan_abs_maps"])."""
    mat = basemesh.active_material
    nt = mat.node_tree
    col_node = next(n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image and
                    not any(l.to_node.type in ('NORMAL_MAP', 'BUMP') for o in n.outputs for l in o.links))
    nrm_node = next((n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image and
                     any(l.to_node.type == 'NORMAL_MAP' for o in n.outputs for l in o.links)), None)

    def file_of(img):
        path = bpy.path.abspath(img.filepath)
        if not img.filepath or not os.path.exists(path):
            path = os.path.join(work, f"in_{img.name}.png".replace("/", "_"))
            img.filepath_raw = path
            img.file_format = 'PNG'
            img.save()
        return path

    out = {k: os.path.join(work, f"{cid}_scan_{k}.png") for k in ("color", "normal", "rough")}
    skin_in, skin_n = file_of(col_node.image), file_of(nrm_node.image) if nrm_node else None
    run_compose(work, root, "", skin_in, skin_n, out)
    if head:
        hout = {k: os.path.join(work, f"{cid}_scan_head_{k}.png") for k in ("color", "normal", "rough")}
        hskin = os.path.join(work, "bake_skin_head.png")
        hnorm = os.path.join(work, "bake_skinnormal_head.png")
        run_compose(work, root, "_head", hskin, hnorm if os.path.exists(hnorm) else None, hout)
        basemesh["scan_head_maps"] = json.dumps(hout)
    if absent:
        aout = {k: os.path.join(work, f"{cid}_scan_abs_{k}.png") for k in ("color", "normal", "rough")}
        run_compose(work, root, "_abs", skin_in, skin_n, aout)
        ahout = {k: os.path.join(work, f"{cid}_scan_abs_head_{k}.png") for k in ("color", "normal", "rough")}
        hskin = os.path.join(work, "bake_skin_head.png")
        hnorm = os.path.join(work, "bake_skinnormal_head.png")
        run_compose(work, root, "_abs_head", hskin, hnorm if os.path.exists(hnorm) else None, ahout)
        aout["head_color"] = ahout["color"]
        aout["head_normal"] = ahout["normal"]
        basemesh["scan_abs_maps"] = json.dumps(aout)
    col_node.image = load_map(out["color"], "color")
    nimg = load_map(out["normal"], "data")
    if nrm_node is not None:
        nrm_node.image = nimg
    else:
        bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
        tn = nt.nodes.new('ShaderNodeTexImage')
        tn.image = nimg
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nt.links.new(tn.outputs[0], nm.inputs["Color"])
        nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    basemesh["scan_rough"] = load_map(out["rough"], "data").name
    return col_node.image


def max_filter(a, r, axis):
    out = a.copy()
    for k in range(1, r + 1):
        out = np.maximum(out, np.roll(a, k, axis))
        out = np.maximum(out, np.roll(a, -k, axis))
    return out


def min_filter(a, r, axis):
    out = a.copy()
    for k in range(1, r + 1):
        out = np.minimum(out, np.roll(a, k, axis))
        out = np.minimum(out, np.roll(a, -k, axis))
    return out


def clean_eye_corners(basemesh, head_faces, in_body, root, radius=0.028, line=0.0015):
    """A head scan paints each eye's lid line on past its outer corner (out towards the temple, a centimetre or two):
    on the template's eyes, where the portrait paints only faintly (the skin there turns from the camera), it read as
    a crease from each outer eye corner. Thin dark lines there (narrower than `line` each side) are closed in the head
    texture before the portrait goes on: per channel a grey closing (max, then min, over 2 x line), mixed in round
    each outer corner, lateral of it and under the brow."""
    maps = json.loads(basemesh["scan_head_maps"])
    me = basemesh.data
    V = world_verts(basemesh)
    A = anchor_points(basemesh, root)
    m = np.zeros(len(V))
    for c in (33, 263):
        if c not in A:
            continue
        a = A[c]
        side = np.sign(a[0] - V[in_body, 0].mean())
        d = np.linalg.norm(V - a, axis=1)
        m = np.maximum(m, (1.0 - smoothstep(radius - 0.008, radius, d)) * smoothstep(0.002, 0.005, d)
                       * smoothstep(-0.002, 0.003, (V[:, 0] - a[0]) * side)
                       * (1.0 - smoothstep(a[2] + 0.004, a[2] + 0.009, V[:, 2])))
    m *= in_body
    if not (m > 0.01).any():
        return
    img = bpy.data.images.load(maps["color"], check_existing=False)
    W_, H_ = img.size
    px = np.empty(W_ * H_ * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(H_, W_, 4)
    me.calc_loop_triangles()
    tv = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tv)
    tl = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("loops", tl)
    tp = np.empty(len(me.loop_triangles), np.int64)
    me.loop_triangles.foreach_get("polygon_index", tp)
    tv, tl = tv.reshape(-1, 3), tl.reshape(-1, 3)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2) * np.array([W_, H_])
    sel = head_faces[tp] & (m[tv].max(1) > 0.01)
    mask = np.zeros((H_, W_), np.float32)
    for t in np.nonzero(sel)[0]:
        P = uv[tl[t]]
        x0, y0 = np.floor(P.min(0)).astype(int)
        x1, y1 = np.ceil(P.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W_ - 1), min(y1, H_ - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        Q = np.stack([gx.ravel(), gy.ravel()], 1)
        T = np.array([[P[1, 0] - P[0, 0], P[2, 0] - P[0, 0]], [P[1, 1] - P[0, 1], P[2, 1] - P[0, 1]]])
        if abs(np.linalg.det(T)) < 1e-9:
            continue
        b = np.linalg.solve(T, (Q - P[0]).T).T
        w = np.stack([1 - b.sum(1), b[:, 0], b[:, 1]], 1)
        ins = (w >= -0.01).all(1)
        val = (w[ins] * m[tv[t]]).sum(1)
        yy, xx = (Q[ins, 1] - 0.5).astype(int), (Q[ins, 0] - 0.5).astype(int)
        mask[yy, xx] = np.maximum(mask[yy, xx], val)
    ys, xs = np.nonzero(mask > 0.01)
    if not len(ys):
        bpy.data.images.remove(img)
        return
    # texels per metre on the face, from the triangles' UV and world areas
    t3 = tv[sel]
    a3 = 0.5 * np.linalg.norm(np.cross(V[t3[:, 1]] - V[t3[:, 0]], V[t3[:, 2]] - V[t3[:, 0]]), axis=1).sum()
    q = uv[tl[sel]]
    a2 = 0.5 * np.abs((q[:, 1, 0] - q[:, 0, 0]) * (q[:, 2, 1] - q[:, 0, 1]) - (q[:, 2, 0] - q[:, 0, 0]) * (q[:, 1, 1] - q[:, 0, 1])).sum()
    r = max(2, int(round(line * np.sqrt(a2 / max(a3, 1e-12)))))
    y0, y1 = max(ys.min() - 3 * r, 0), min(ys.max() + 3 * r + 1, H_)
    x0, x1 = max(xs.min() - 3 * r, 0), min(xs.max() + 3 * r + 1, W_)
    crop = px[y0:y1, x0:x1, :3]
    closed = np.empty_like(crop)
    for k in range(3):
        c = max_filter(max_filter(crop[..., k], r, 0), r, 1)
        closed[..., k] = min_filter(min_filter(c, r, 0), r, 1)
    mk = mask[y0:y1, x0:x1, None]
    px[y0:y1, x0:x1, :3] = crop + mk * (closed - crop)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = maps["color"]
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    log(f"eye corners: dark lines up to {2 * line * 1000:.0f} mm wide closed round both outer corners "
        f"({int((mask > 0.5).sum())} texels, {r} px)")


def blend_portrait_edge(basemesh, head_faces, in_body, root, reach=0.02, band=0.0015, ramp=0.006):
    """Head scans, after the portrait: its edge blended into the scan's skin. The portrait paints inside its own face
    outline, a little lighter and smoother than the scan's skin round it, and its feathered edge reads as a thin
    vertical crease down each cheek from beside the outer eye corner and a lighter strip with a straight edge at the
    temple; carrying only its tone out over the edge still leaves a step in grain. Its broad tone (its offset from the
    unpainted head, blurred over 6 mm) runs on across the edge into the skin outside, fading out over `reach`, and
    inside the edge its own detail fades in over about 1.1 cm (a blur of the inside over `ramp`) over the scan's, so
    neither the tone nor the grain steps; across the edge the colour is blurred over `band`. Skin only, a soft mask
    (not the hair, the brows, the ears or the painted hairline: a hard lightness threshold leaves a pale patch with
    mottled edges at the hairline)."""
    maps = json.loads(basemesh["scan_head_maps"])
    base_path = maps["color"].replace(".png", "_base.png")
    if not os.path.exists(base_path):
        return
    V = world_verts(basemesh)
    img, size, px = _head_img(maps)
    bimg = bpy.data.images.load(base_path, check_existing=False)
    bp = np.empty(size * size * 4, np.float32)
    bimg.pixels.foreach_get(bp)
    bpy.data.images.remove(bimg)
    bp = bp.reshape(size, size, 4)
    hv, tpm = head_texels(basemesh, head_faces, np.ones(len(V)), size)
    valid = hv > 0.5
    d = px[..., :3] - bp[..., :3]
    inside = valid & (np.abs(d).max(-1) > 0.012)
    if not inside.any():
        bpy.data.images.remove(img)
        return
    ys, xs = np.nonzero(valid)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    cr = px[y0:y1, x0:x1, :3]
    b0 = bp[y0:y1, x0:x1, :3]
    dd = d[y0:y1, x0:x1]
    val = valid[y0:y1, x0:x1].astype(np.float32)
    # (the inside as one region: the portrait's paint can equal the scan's here and there inside it)
    ins = (gauss_blur(inside[y0:y1, x0:x1].astype(np.float32), 0.001 * tpm) > 0.5).astype(np.float32) * val
    L = to_lab(np.clip(cr.reshape(-1, 3), 0, 1).astype(np.float64))[:, 0].reshape(cr.shape[:2])
    Lb = gauss_blur(L.astype(np.float32), 0.002 * tpm)
    hairy = gauss_blur((L < 30.0).astype(np.float32) * val, 0.003 * tpm)
    skin = smoothstep(30.0, 42.0, Lb) * (1.0 - smoothstep(0.08, 0.3, hairy)) * val
    skin *= 1.0 - _tex_mask("hairline", size, y0, y1, x0, x1)
    sg = 0.006 * tpm
    off = gauss_blur(dd * ins[..., None], sg) / np.maximum(gauss_blur(ins, sg), 1e-4)[..., None]
    near = gauss_blur(ins, 0.5 * reach * tpm)
    k_out = np.clip(near * 2.0, 0.0, 1.0) * (1.0 - ins) * skin
    depth = gauss_blur(ins, ramp * tpm)
    t_in = smoothstep(0.5, 0.97, depth)
    k_in = (1.0 - t_in) * ins * skin
    new = cr + k_out[..., None] * off
    new = new + k_in[..., None] * ((b0 + off) - new)
    edge = gauss_blur(ins, 0.004 * tpm)
    k_b = (smoothstep(0.03, 0.25, edge) * (1.0 - smoothstep(0.75, 0.97, edge))) * skin
    bl = gauss_blur(new * val[..., None], band * tpm) / np.maximum(gauss_blur(val, band * tpm), 1e-4)[..., None]
    new = new + k_b[..., None] * (bl - new)
    px[y0:y1, x0:x1, :3] = np.clip(new, 0.0, 1.0)
    _save_img(img, px, maps["color"])
    log(f"portrait: its edge blended into the scan's skin ({int((k_out > 0.5).sum())} texels toned to it outside, "
        f"{int((k_in > 0.5).sum())} inside fading its detail in over the scan's, {int((k_b > 0.5).sum())} blurred "
        f"across it)")


def tone_beard(basemesh, head_faces, in_body, root, boost=0.8, deepen=0.22):
    """Head scans, after the portrait: the moustache and the goatee made dark and even. The portrait's paint fades out
    round the chin, which leaves the goatee light and sparse, and it can leave a one-sided smudge in the moustache. In
    both, the broad tone (blurred over 2.5 mm) takes the lighter of its own and its mirror image's across the face's
    middle, the mean of the two (a one-sided smudge goes, the beard's own darkness stays), and the strands (the
    texture under that broad tone) are darkened by `boost` of how far they already are under it, toward the hair's
    dark."""
    maps = json.loads(basemesh["scan_head_maps"])
    V = world_verts(basemesh)
    A = anchor_points(basemesh, root)
    if not all(i in A for i in (0, 2, 17, 61, 291, 152, 13, 14)):
        return
    mid = float(V[in_body, 0].mean())
    x = np.abs(V[:, 0] - mid)
    mw = abs(float(A[291][0] - A[61][0])) / 2
    must = (smoothstep(A[0][2] - 0.002, A[0][2] + 0.001, V[:, 2]) * (1.0 - smoothstep(A[2][2] - 0.008, A[2][2] - 0.005, V[:, 2]))
            * (1.0 - smoothstep(mw + 0.002, mw + 0.008, x)))
    goat = (smoothstep(A[152][2] - 0.012, A[152][2] - 0.004, V[:, 2]) * (1.0 - smoothstep(A[17][2] - 0.003, A[17][2], V[:, 2]))
            * (1.0 - smoothstep(0.018, 0.026, x)))
    reg = np.maximum(must, goat)
    reg *= smoothstep(0.0015, 0.004, nearest_landmark(V, np.array([A[i] for i in LIPS if i in A])))
    reg *= in_body
    if not (reg > 0.01).any():
        return
    img, size, px = _head_img(maps)
    # (the broad tone deepened on the moustache only: deepened on the goatee too, it came out a glossy black ball)
    must_w = must * smoothstep(0.0015, 0.004, nearest_landmark(V, np.array([A[i] for i in LIPS if i in A]))) * in_body
    # (the upper lip up to the nostrils, for the cool cast)
    ulip = (smoothstep(A[0][2] - 0.002, A[0][2] + 0.001, V[:, 2]) * (1.0 - smoothstep(A[2][2] + 0.001, A[2][2] + 0.004, V[:, 2]))
            * (1.0 - smoothstep(mw + 0.004, mw + 0.012, x))) * in_body
    reg = np.maximum(reg, 1e-3 * ulip)
    m, tpm = head_texels(basemesh, head_faces, np.stack([reg, V[:, 0], V[:, 1], V[:, 2], np.ones(len(V)), must_w,
                                                         ulip], 1), size)
    ys, xs = np.nonzero(m[..., 0] > 0.01)
    if not len(ys):
        bpy.data.images.remove(img)
        return
    r = int(0.006 * tpm) + 4
    y0, y1, x0, x1 = max(ys.min() - r, 0), min(ys.max() + r + 1, size), max(xs.min() - r, 0), min(xs.max() + r + 1, size)
    crop = px[y0:y1, x0:x1, :3].copy()
    w = m[y0:y1, x0:x1, 0]
    P = m[y0:y1, x0:x1, 1:4]
    valid = m[y0:y1, x0:x1, 4] > 0.99
    lum = crop @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    vf = valid.astype(np.float32)
    broad = gauss_blur(lum * vf, 0.0025 * tpm) / np.maximum(gauss_blur(vf, 0.0025 * tpm), 1e-4)
    # the mirror image's broad tone: the nearest texel to each texel's point mirrored across the face's middle
    vy, vx = np.nonzero(valid)
    step = 2
    sub = (vy % step == 0) & (vx % step == 0)
    kd = KDTree(int(sub.sum()))
    for k, (yy, xx) in enumerate(zip(vy[sub], vx[sub])):
        kd.insert(P[yy, xx], k)
    kd.balance()
    sy, sx = vy[sub], vx[sub]
    on = np.nonzero(valid & (w > 0.01))
    mir = np.full(lum.shape, np.nan, np.float32)
    for yy, xx in zip(*on):
        q = P[yy, xx]
        co, k, d = kd.find((2.0 * mid - q[0], q[1], q[2]))
        if k is not None and d < 0.002:
            mir[yy, xx] = broad[sy[k], sx[k]]
    has = np.isfinite(mir)
    # (the mean of the two sides: the darker side lighter and the lighter darker by as much; taking the lighter of the
    # two, a mirror point that fell on the skin under a nostril left pale patches over the moustache)
    target = np.where(has, 0.5 * (broad + np.nan_to_num(mir)), broad)
    gain = np.clip(target / np.maximum(broad, 1e-4), 0.8, 1.25)
    fine = np.clip(lum / np.maximum(broad, 1e-4), 0.0, 1.5)
    dark, tip = hair_tone(basemesh)
    # (and the broad tone itself `deepen` darker, the strands `boost` of the way to the hair's dark x 1.2)
    wm = m[y0:y1, x0:x1, 5] if m.shape[-1] > 5 else w
    even = crop * (gain * (1.0 - deepen * np.clip(wm * 1.5, 0, 1)))[..., None]
    strands = np.clip(1.0 - fine, 0.0, 1.0)
    out = even + (boost * np.clip(strands * 2.0, 0, 1))[..., None] * (dark[None, None] * 1.2 - even)
    a = (w * valid).astype(np.float32)
    fin = crop + a[..., None] * (out - crop)
    # (and no cool cast: a grey-blue smudge sat on the moustache under the left nostril, the portrait's; over the upper
    # lip each texel's chromaticity pulled towards the moustache's median where its blue share stands over it)
    tot = np.maximum(fin.sum(-1, keepdims=True), 1e-4)
    chrom = fin / tot
    sel_ = (w > 0.3) & valid
    med_c = np.median(chrom[sel_], 0) if sel_.any() else np.array([0.45, 0.32, 0.23])
    ul = m[y0:y1, x0:x1, 6]
    k_c = (smoothstep(0.012, 0.035, chrom[..., 2] - med_c[2]) * np.clip(np.maximum(w, ul) * 2.0, 0, 1) * valid)
    fin = fin + k_c[..., None] * (med_c[None, None] * tot - fin)
    n_cool = int((k_c > 0.5).sum())
    px[y0:y1, x0:x1, :3] = fin
    _save_img(img, px, maps["color"])
    log(f"beard: {n_cool} cool texels warmed to the beard's own tone")
    log(f"beard: moustache and goatee even across the face (the broad tone x {float(np.percentile(gain[a > 0.5], 1)):.2f}-"
        f"{float(np.percentile(gain[a > 0.5], 99)):.2f} towards its mirror image's, the moustache's {deepen:.2f} darker) and their strands "
        f"darkened ({boost:.2f}; {int((a > 0.5).sum())} texels)")


def clean_skin_lines(basemesh, head_faces, in_body, root, line=0.0009, depth=7.0):
    """Head scans, after the portrait: thin dark marks on the forehead, the temples and the cheeks closed in the head
    texture (a grey closing over 2 x `line`, kept only where it lifts the skin by over `depth` L and an eighth of its
    lightness: pores and the portrait's broad shading stay). They are stray hairs painted on the skin under the
    hairline and thin creases down the cheek from beside the outer eye corner. Not the brows, the eyes, the nose, the
    lips and the beard, the ears or the hair."""
    maps = json.loads(basemesh["scan_head_maps"])
    V = world_verts(basemesh)
    A = anchor_points(basemesh, root)
    need = (33, 133, 263, 362, 1, 2, 61, 291, 13, 10)
    if not all(i in A for i in need):
        return
    mid = float(V[in_body, 0].mean())
    brow_z = float(np.mean([A[i][2] for i in BROWS if i in A]))
    eye_z = float(np.mean([A[i][2] for i in (33, 133, 263, 362)]))
    front = float(min(A[i][1] for i in (33, 263)))
    ear_y = float(np.mean([A[i][1] for i in (234, 454) if i in A] or [front + 0.06]))
    x = np.abs(V[:, 0] - mid)
    forehead = smoothstep(brow_z + 0.004, brow_z + 0.01, V[:, 2]) * (1.0 - smoothstep(0.055, 0.065, x))
    cheek = (smoothstep(A[2][2] - 0.004, A[2][2] + 0.002, V[:, 2]) * (1.0 - smoothstep(eye_z - 0.012, eye_z - 0.007, V[:, 2]))
             * smoothstep(0.024, 0.03, x))
    temple = (smoothstep(eye_z - 0.01, eye_z - 0.004, V[:, 2]) * (1.0 - smoothstep(brow_z + 0.02, brow_z + 0.03, V[:, 2]))
              * smoothstep(0.052, 0.058, x))
    reg = np.maximum(np.maximum(forehead, cheek), temple)
    reg *= 1.0 - smoothstep(ear_y - 0.012, ear_y - 0.004, V[:, 1])
    keep_out = [A[i] for i in BROWS if i in A] + [A[i] for i in RIGHT_EYE + LEFT_EYE if i in A]
    reg *= smoothstep(0.006, 0.01, nearest_landmark(V, np.array(keep_out)))
    eg = ear_group(basemesh, in_body)
    if eg.any():
        reg *= smoothstep(0.004, 0.008, nearest_landmark(V, V[eg]))
    reg *= in_body
    if not (reg > 0.01).any():
        return
    img, size, px = _head_img(maps)
    m, tpm = head_texels(basemesh, head_faces, reg, size)
    ys, xs = np.nonzero(m > 0.01)
    if not len(ys):
        bpy.data.images.remove(img)
        return
    r = max(2, int(round(line * tpm)))
    y0, y1 = max(ys.min() - 3 * r, 0), min(ys.max() + 3 * r + 1, size)
    x0, x1 = max(xs.min() - 3 * r, 0), min(xs.max() + 3 * r + 1, size)
    crop = px[y0:y1, x0:x1, :3]
    closed = np.empty_like(crop)
    for k in range(3):
        c_ = max_filter(max_filter(crop[..., k], r, 0), r, 1)
        closed[..., k] = min_filter(min_filter(c_, r, 0), r, 1)
    L = to_lab(np.clip(crop.reshape(-1, 3), 0, 1).astype(np.float64))[:, 0].reshape(crop.shape[:2])
    Lc = to_lab(np.clip(closed.reshape(-1, 3), 0, 1).astype(np.float64))[:, 0].reshape(crop.shape[:2])
    # (on skin only: its lightness round it over 2.5 mm; the hairline's strands stay, and so does everything within 5
    # mm of the hair or the painted hairline: closed along the hairline's ragged edge, the square closing leaves a
    # pale patch with blocky, mottled edges)
    skin = gauss_blur(L.astype(np.float32), 0.0025 * tpm) > 40.0
    hairy = gauss_blur((L < 30.0).astype(np.float32), 0.003 * tpm)
    near_hair = np.maximum(smoothstep(0.02, 0.1, hairy), _tex_mask("hairline", size, y0, y1, x0, x1))
    diff = Lc - L
    mk = ((diff > depth) & (diff > 0.125 * Lc) & skin).astype(np.float32) * m[y0:y1, x0:x1] * (1.0 - near_hair)
    mk = np.clip(gauss_blur(max_filter(max_filter(mk, 1, 0), 1, 1), 0.8) * 1.5, 0, 1) * (m[y0:y1, x0:x1] > 0.01)
    px[y0:y1, x0:x1, :3] = crop + mk[..., None] * (closed - crop)
    _save_img(img, px, maps["color"])
    log(f"skin: thin dark marks on the forehead, temples and cheeks closed ({int((mk > 0.5).sum())} texels, lines up to "
        f"{2 * r / tpm * 1000:.1f} mm wide, over {depth:.0f} L darker than the skin round them)")


def shade_ears(basemesh, head_faces, in_body, depth=0.5):
    """Head scans: the ears' skin under the hair shell darker (`depth` at most), as the hair over them shades them:
    with the hair brought down over the ears' tops, the template's pink inner ear showed between the strands as pink
    flecks along the hair's edge over the right ear (0.3-0.55 m, profile)."""
    maps = json.loads(basemesh["scan_head_maps"])
    eg = ear_group(basemesh, in_body)
    V = world_verts(basemesh)
    sd = _shell_rim_distance(V)
    if not eg.any() or sd is None:
        return
    k = eg.astype(np.float64) * (1.0 - smoothstep(-0.008, 0.003, sd)) * depth
    if not (k > 0.01).any():
        return
    img, size, px = _head_img(maps)
    m, _ = head_texels(basemesh, head_faces, k, size)
    px[..., :3] *= (1.0 - m)[..., None].astype(np.float32)
    _save_img(img, px, maps["color"])
    log(f"ears: their skin under the hair shell darkened ({int((m > 0.25).sum())} texels, up to {depth:.2f})")


def head_margins(basemesh, head_faces, rings=12):
    """Head scans, after the head texture's passes: the margins round the head texture's islands taken again from the
    texels next to them (rings deep). The passes paint inside the triangles only, so a margin kept the colour from
    before them, and where they darkened the skin up to an island's edge (the stubble and the goatee under the jaw)
    filtering read the old, lighter margin: a thin light line along the head's material edge under the jaw."""
    maps = json.loads(basemesh["scan_head_maps"])
    n = 0
    for key in ("color", "normal"):
        if not maps.get(key) or not os.path.exists(maps[key]):
            continue
        img, size, px = _head_img(maps, key)
        ys, xs, _, _, _ = _corner_texels(basemesh, head_faces, size)
        have = np.zeros((size, size), bool)
        have[ys, xs] = True
        y0, y1, x0, x1 = max(ys.min() - rings, 0), min(ys.max() + rings + 1, size), max(xs.min() - rings, 0), \
            min(xs.max() + rings + 1, size)
        h = have[y0:y1, x0:x1].copy()
        out = px[y0:y1, x0:x1, :3].astype(np.float32).copy()
        out[~h] = 0.0
        for _ in range(rings):
            acc = np.zeros_like(out)
            cnt = np.zeros(h.shape, np.float32)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                acc += np.roll(out, (dy, dx), (0, 1))
                cnt += np.roll(h, (dy, dx), (0, 1))
            new = ~h & (cnt > 0)
            if not new.any():
                break
            out[new] = acc[new] / cnt[new][:, None]
            h |= new
            n += int(new.sum()) if key == "color" else 0
        fill = h & ~have[y0:y1, x0:x1]
        sub = px[y0:y1, x0:x1, :3]
        sub[fill] = out[fill]
        px[y0:y1, x0:x1, :3] = sub
        _save_img(img, px, maps[key])
    log(f"head texture: its islands' margins taken again from their edges ({n} texels, {rings} rings)")


JAW_OVAL = [234, 93, 132, 58, 172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288, 361, 323, 454]


def paint_beard(basemesh, head_faces, in_body, root, stubble=0.5, goatee=0.56, lay=(0.5, 0.64), shape=None):
    """Head scans, after tone_beard: the goatee and the stubble along the jaw, painted as short dark strands. The
    portrait's paint fades out round the chin, and the head scan's jaw stubble, kept at 35 % (soften_scan_skin), all
    but disappears. The goatee: from 3 mm under the lower lip to 1 cm under the chin, 2.4 cm either side of the middle
    at the chin narrowing to 1.3 cm under the lip, its edge wandering and feathered over 4 mm, `goatee` of the skin
    covered; the stubble: within 1.6 cm of the jaw line (the face outline's landmarks from ear to ear), fading out to
    2.6 cm, from the ears' front to the goatee, down to 6 mm over the seam (fill_neck's neckline), `stubble` of the
    skin covered in patches; not the lips. Strands 2.5 mm long on the jaw, 4 mm on the chin, two texels wide, running
    down the face, toned like the hair (a sixth of the tone the skin's own), laid on at `lay` over skin a little
    darker under them (stubble's shadow)."""
    maps = json.loads(basemesh["scan_head_maps"])
    V = world_verts(basemesh)
    A = anchor_points(basemesh, root)
    jo = [i for i in JAW_OVAL if i in A]
    if not all(i in A for i in (17, 152)) or len(jo) < 8:
        return
    mid = float(V[in_body, 0].mean())
    x = np.abs(V[:, 0] - mid)
    eg = ear_group(basemesh, in_body)
    z_cut = neck_cut(A)
    h = V[:, 2] - z_cut(V[:, 1])
    lip_z, chin_z, chin_y = float(A[17][2]), float(A[152][2]), float(A[152][1])
    # the goatee: the chin's front and its underside to 1.5 cm behind its point
    t = np.clip((lip_z - 0.003 - V[:, 2]) / max(lip_z - 0.003 - chin_z, 1e-3), 0.0, 1.0)
    hw = 0.013 + 0.011 * np.sqrt(t) + 0.002 * (2.0 * value_noise(V, 0.006, 41) - 1.0)
    # (beard_dark "goat_w", "goat_back", off by default) the goatee up to goat_w wider either side toward its bottom
    # and reaching goat_back further back under the chin
    gw_, gb_ = (float((shape or {}).get("goat_w", 0.0)), float((shape or {}).get("goat_back", 0.0)))
    hw = hw + gw_ * t ** 1.5
    goat = ((1.0 - smoothstep(lip_z - 0.004, lip_z - 0.002, V[:, 2])) * smoothstep(chin_z - 0.014, chin_z - 0.008, V[:, 2])
            * (1.0 - smoothstep(hw - 0.004, hw, x)) * (1.0 - smoothstep(chin_y + 0.012 + gb_, chin_y + 0.02 + gb_, V[:, 1])))
    # the jaw line, ear to ear
    J = np.array([A[i] for i in jo])
    dj = np.full(len(V), 1.0)
    for k in range(len(J) - 1):
        dj = np.minimum(dj, seg_dist(V, J[k], J[k + 1]))
    jaw = 1.0 - smoothstep(0.009, 0.02, dj + 0.004 * (2.0 * value_noise(V, 0.01, 42) - 1.0))
    if eg.any():
        for side in (-1.0, 1.0):
            es = eg & (np.sign(V[:, 0] - mid) == side)
            if es.sum() > 10:
                ef = float(np.percentile(V[es, 1], 5))
                jaw *= np.where(np.sign(V[:, 0] - mid) == side, 1.0 - smoothstep(ef - 0.008, ef - 0.002, V[:, 1]), 1.0)
        jaw *= smoothstep(0.003, 0.008, nearest_landmark(V, V[eg]))
    # (patches: stubble is uneven)
    jaw *= 0.7 + 0.6 * (value_noise(V, 0.012, 43) - 0.5)
    goat *= smoothstep(chin_z - 0.016, chin_z - 0.006, V[:, 2])
    reg = np.maximum(goat * goatee, jaw * stubble)
    # (fading out over the neck 2-16 mm over the seam along a wandering line: cut at one height the stubble's lower
    # edge drew a hard line under the jaw)
    reg *= smoothstep(0.002, 0.016, h + 0.004 * (2.0 * value_noise(V, 0.008, 47) - 1.0))
    reg *= smoothstep(0.003, 0.007, nearest_landmark(V, np.array([A[i] for i in LIPS if i in A])))
    reg *= in_body
    if not (reg > 0.01).any():
        return
    img, size, px = _head_img(maps)
    m, tpm = head_texels(basemesh, head_faces, np.stack([reg, V[:, 0], V[:, 1], V[:, 2], np.ones(len(V)), goat], 1), size)
    ys, xs = np.nonzero(m[..., 0] > 0.005)
    if not len(ys):
        bpy.data.images.remove(img)
        return
    r = 8
    y0, y1, x0, x1 = max(ys.min() - r, 0), min(ys.max() + r + 1, size), max(xs.min() - r, 0), min(xs.max() + r + 1, size)
    crop = px[y0:y1, x0:x1, :3].copy()
    dens = m[y0:y1, x0:x1, 0]
    Pm = m[y0:y1, x0:x1, 1:4]
    valid = m[y0:y1, x0:x1, 4] > 0.99
    gt = m[y0:y1, x0:x1, 5]
    P = Pm.reshape(-1, 3)
    T3 = np.zeros_like(Pm)
    # (the goatee's strands curl: run straight down they read as combed vertical streaks)
    T3[..., 0] = (0.25 + 0.9 * smoothstep(0.2, 0.6, gt)) * (2.0 * value_noise(P, 0.003, 44).reshape(dens.shape) - 1.0)
    T3[..., 1], T3[..., 2] = 0.15 + 0.6 * smoothstep(0.2, 0.6, gt) * (2.0 * value_noise(P, 0.003, 48).reshape(dens.shape) - 1.0), -1.0
    dxm, dym = texture_dirs(Pm, valid, T3)
    ok = valid & (dxm ** 2 + dym ** 2 > 0.5)
    # (stubble: hairs 1.3 mm long, one texel wide, a fine stipple; at 2.5 mm and two texels it read as a pelt of ink
    # dashes at 0.3 m. The goatee 2.2 mm, two texels, curling. Laid on at lay[0] and lay[1]: at 0.82 and 0.9 of the skin covered
    # the goatee came out a solid black ball under a key light)
    u_j = lic(dxm, dym, ok, int(round(0.0013 * tpm)), seed=45, x0=x0, y0=y0, cell=1)
    u_g = lic(dxm, dym, ok, int(round(0.0022 * tpm)), seed=46, x0=x0, y0=y0, cell=2)
    g_ = smoothstep(0.2, 0.6, gt)
    u = u_j + g_ * (u_g - u_j)
    strand = smoothstep(1.0 - dens - 0.08, 1.0 - dens + 0.08, u) * (dens > 0.005)
    strand = gauss_blur(strand.astype(np.float32), 0.5)
    dark, tip = hair_tone(basemesh)
    tone = dark[None, None] + (tip - dark)[None, None] * smoothstep(0.0, 1.0, (u * 5.0) % 1.0)[..., None]
    tone = tone + (1.0 / 6.0) * (crop * 0.35 - tone)
    # (and the skin under them a little darker: stubble's shadow)
    under = crop * (1.0 - 0.2 * np.clip(dens * 1.6, 0, 1))[..., None]
    lay_ = lay[0] + (lay[1] - lay[0]) * g_
    paint = under + (strand * lay_)[..., None] * (tone - under)
    a = valid.astype(np.float32)
    px[y0:y1, x0:x1, :3] = crop + a[..., None] * (paint - crop)
    _save_img(img, px, maps["color"])
    log(f"beard: goatee ({goatee:.2f} of the skin) and stubble along the jaw ({stubble:.2f}) painted as strands "
        f"({int(((dens > 0.3) & valid).sum())} texels over 0.3, laid on at {lay[0]:.2f} and {lay[1]:.2f})")


# each brow's upper and lower edge landmarks (MediaPipe), outer end first: right, left
BROW_EDGES = (([70, 63, 105, 66, 107], [46, 53, 52, 65, 55]), ([300, 293, 334, 296, 336], [276, 283, 282, 295, 285]))


def _hex_srgb(h):
    return np.array([int(h[k:k + 2], 16) / 255.0 for k in (1, 3, 5)])


def brow_coords(V, A, up, lo, n_sub=24):
    """Per vertex, where it lies against one brow (its upper and lower edge landmarks `up`, `lo`, outer end first): t
    (0 at the outer end of the brow's middle line, 1 at the inner end, by arc length), r (the signed offset from that
    line over the brow's half height there: +1 the upper edge, -1 the lower), past_out / past_in (m beyond either end
    along the line), dist (m to the line), and the line's direction (outer -> inner) and the brow's upward direction
    at the nearest point of the line."""
    U = np.array([A[i] for i in up], np.float64)
    L = np.array([A[i] for i in lo], np.float64)
    C, H = (U + L) / 2, (U - L) / 2
    s = np.linspace(0, len(C) - 1, (len(C) - 1) * n_sub + 1)
    k = np.minimum(s.astype(int), len(C) - 2)
    f = (s - k)[:, None]
    Cd, Hd = C[k] * (1 - f) + C[k + 1] * f, H[k] * (1 - f) + H[k + 1] * f
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(Cd, axis=0), axis=1))])
    Td = np.gradient(Cd, axis=0)
    Td /= np.maximum(np.linalg.norm(Td, axis=1, keepdims=True), 1e-12)
    hw = np.linalg.norm(Hd, axis=1)
    Hu = Hd / np.maximum(hw[:, None], 1e-12)
    j = np.empty(len(V), np.int64)
    dist = np.empty(len(V))
    for s0 in range(0, len(V), 4000):
        d2 = ((V[s0:s0 + 4000, None, :] - Cd[None]) ** 2).sum(-1)
        j[s0:s0 + 4000] = d2.argmin(1)
        dist[s0:s0 + 4000] = np.sqrt(d2.min(1))
    D = V - Cd[j]
    a = (D * Td[j]).sum(1)
    r = (D * Hu[j]).sum(1) / np.maximum(hw[j], 1e-6)
    past_out = np.where(j == 0, np.maximum(-a, 0.0), 0.0)
    past_in = np.where(j == len(Cd) - 1, np.maximum(a, 0.0), 0.0)
    return dict(t=arc[j] / arc[-1], r=r, hw=hw[j], past_out=past_out, past_in=past_in, dist=dist, T=Td[j], Up=Hu[j])


def brow_paint_px(px, V, A, in_body, texels, cfg):
    """paint_brows on the head texture's pixels (px: Blender orientation; texels(vals) -> (per-texel values, texels per
    metre)). Returns (texels painted over half, texels darkened under the brows)."""
    thick = float(cfg.get("thick", 1.3))          # the brow's height at its inner end, x the landmarks' band
    up_, lo_ = float(cfg.get("up", 1.0)), float(cfg.get("lo", 1.1))   # its edges, x the half band above and below
    tail_ = float(cfg.get("tail", 0.45))          # its height at the outer end, x that in the middle
    soft = float(cfg.get("soft", 0.6))            # where the edge starts to feather (x the edge)
    cover = cfg.get("cover", (0.6, 0.85))         # the skin covered at the outer end and at the inner
    lay = float(cfg.get("lay", 0.8))
    hair_len = float(cfg.get("len", 0.0028))
    shade = float(cfg.get("shade", 0.25))         # the skin under the brow darker (dense brows)
    crease = float(cfg.get("crease", 0.12))       # under the brow ridge, down toward the upper lid's crease
    tone_k = float(cfg.get("tone", 0.35))         # strands from `dark` (0) toward `tip` (1)
    dark, tip = _hex_srgb(cfg.get("dark", "#140f0d")), _hex_srgb(cfg.get("tip", "#2a201b"))
    eye_up = [i for i in (159, 158, 157, 160, 161, 386, 385, 384, 387, 388) if i in A]
    mask, dens, crz = np.zeros(len(V)), np.zeros(len(V)), np.zeros(len(V))
    Tdir = np.zeros((len(V), 3))
    for up, lo in BROW_EDGES:
        if not all(i in A for i in up + lo):
            continue
        b = brow_coords(V, A, up, lo)
        t, r = b["t"], b["r"]
        near = (b["dist"] < 0.03) & in_body
        k_t = 1.0 + (thick - 1.0) * smoothstep(0.35, 1.0, t)
        tail = tail_ + (1.0 - tail_) * smoothstep(0.0, 0.35, t)
        rr = np.where(r >= 0, r / (up_ * k_t * tail), -r / (lo_ * k_t * tail)) + 0.3 * (value_noise(V, 0.0025, 61) - 0.5)
        m = (1.0 - smoothstep(soft, 1.12, rr)) * (1.0 - smoothstep(0.0, 0.004, b["past_out"])) * \
            (1.0 - smoothstep(0.0, 0.0015, b["past_in"])) * near
        mask = np.maximum(mask, m)
        # (the hairs: out along the brow, rising toward its inner end)
        ang = np.radians(15.0 + 45.0 * smoothstep(0.55, 1.0, t))
        d = -b["T"] * np.cos(ang)[:, None] + b["Up"] * np.sin(ang)[:, None]
        sel = m > 0.01
        Tdir[sel] = d[sel]
        dens = np.maximum(dens, m * (float(cover[0]) + (float(cover[1]) - float(cover[0])) * smoothstep(0.2, 0.8, t)))
        # under the brow: from its lower edge down 2-8 mm, between its ends, not on the lids (2-3.5 mm over the upper
        # lid's landmarks)
        below = (-r - lo_ * k_t * tail) * b["hw"]
        c = smoothstep(0.0, 0.002, below) * (1.0 - smoothstep(0.004, 0.008, below)) * \
            smoothstep(-0.05, 0.15, t) * (1.0 - smoothstep(0.0, 0.003, b["past_out"])) * near
        if eye_up:
            c *= smoothstep(0.0015, 0.0035, nearest_landmark(V, np.array([A[i] for i in eye_up])))
        crz = np.maximum(crz, c)
    if not (mask > 0.01).any():
        return 0, 0
    one = np.ones(len(V))
    m_, tpm = texels(np.stack([mask, V[:, 0], V[:, 1], V[:, 2], one, Tdir[:, 0], Tdir[:, 1], Tdir[:, 2], dens, crz], 1))
    ys, xs = np.nonzero((m_[..., 0] > 0.005) | (m_[..., 9] > 0.005))
    if not len(ys):
        return 0, 0
    size = px.shape[0]
    y0, y1, x0, x1 = max(ys.min() - 8, 0), min(ys.max() + 9, size), max(xs.min() - 8, 0), min(xs.max() + 9, size)
    crop = px[y0:y1, x0:x1, :3].copy()
    mk, Pm, valid = m_[y0:y1, x0:x1, 0], m_[y0:y1, x0:x1, 1:4], m_[y0:y1, x0:x1, 4] > 0.99
    T3, dn, cz = m_[y0:y1, x0:x1, 5:8], m_[y0:y1, x0:x1, 8], m_[y0:y1, x0:x1, 9]
    dxm, dym = texture_dirs(Pm, valid, T3)
    ok = valid & (dxm ** 2 + dym ** 2 > 0.5)
    u = lic(dxm, dym, ok, max(2, int(round(hair_len * tpm))), seed=62, x0=x0, y0=y0, cell=1)
    strand = smoothstep(1.0 - dn - 0.08, 1.0 - dn + 0.08, u) * (dn > 0.005)
    strand = gauss_blur(strand.astype(np.float32), 0.5)
    tone = dark[None, None] + (tip - dark)[None, None] * (tone_k * smoothstep(0.0, 1.0, (u * 4.0) % 1.0))[..., None]
    under = crop * (1.0 - shade * np.clip(mk * 1.3, 0, 1))[..., None] * (1.0 - crease * cz)[..., None]
    paint = under + (strand * lay)[..., None] * (tone - under)
    a = valid.astype(np.float32)
    px[y0:y1, x0:x1, :3] = crop + a[..., None] * (paint - crop)
    return int(((mk > 0.5) & valid).sum()), int(((cz > 0.5) & valid).sum())


def paint_brows(basemesh, head_faces, in_body, root, cfg):
    """Head scans, outfit key "brow_paint" (a dict, off by default): the brows painted thick and dark over the head
    texture, where the portrait's paint (with the scan's under it) comes out lighter, thinner and fuzzy. Each brow
    fills the band between its MediaPipe upper and lower edge landmarks (`up`, `lo` x the half band; `thick` x toward
    the inner end, `tail` at the outer, the edge wandering and feathered from `soft`), with short strands (`len` m; a
    line integral convolution along the brow, rising toward the inner end) covering `cover` of the skin (outer, inner)
    in `dark` to `tip` (sRGB hex), laid on at `lay` over skin `shade` darker; under the brow, from its lower edge down
    2-8 mm, the skin `crease` darker (the brow ridge's shadow, not on the lids)."""
    maps = json.loads(basemesh["scan_head_maps"])
    V = world_verts(basemesh)
    A = anchor_points(basemesh, root)
    img, size, px = _head_img(maps)
    n, nc = brow_paint_px(px, V, A, in_body, lambda vals: head_texels(basemesh, head_faces, vals, size), cfg)
    if not n:
        bpy.data.images.remove(img)
        return
    _save_img(img, px, maps["color"])
    log(f"brows: painted thick and dark ({n} texels over half; x {float(cfg.get('thick', 1.3)):.2f} toward the inner "
        f"ends), {nc} texels under them darkened")


def beard_dark_px(px, V, A, in_body, texels, cfg, z_cut):
    """darken_beard on the head texture's pixels (see paint_brows). Returns texels darkened over half."""
    col = _hex_srgb(cfg.get("color", "#1a1411"))
    k_m, k_g, k_s = (float(x) for x in cfg.get("amount", (0.6, 0.62, 0.3)))   # moustache, goatee, strap
    fill = float(cfg.get("fill", 1.3))          # the strands' detail kept up to this over their broad tone
    mh = float(cfg.get("must_h", 0.005))        # the moustache's height over the lip's edge
    if not all(i in A for i in (0, 2, 17, 61, 291, 152, 13, 14)):
        return 0
    mid = float(V[in_body, 0].mean())
    x = np.abs(V[:, 0] - mid)
    mw = abs(float(A[291][0] - A[61][0])) / 2
    dl = nearest_landmark(V, np.array([A[i] for i in LIPS if i in A]))
    # the moustache: a band `mh` over the upper lip's edge (wandering), the mouth's width + 2-6 mm, not the lips
    must = (smoothstep(A[0][2] - 0.001, A[0][2] + 0.0015, V[:, 2]) * (1.0 - smoothstep(A[2][2] - 0.006, A[2][2] - 0.003, V[:, 2]))
            * (1.0 - smoothstep(mw + 0.002, mw + 0.006, x)))
    must *= 1.0 - smoothstep(mh * 0.6, mh * 1.4, V[:, 2] - A[0][2] + 0.0015 * (2.0 * value_noise(V, 0.003, 64) - 1.0))
    must *= smoothstep(0.001, 0.003, dl)
    # the goatee: paint_beard's outline, its sides feathered over 8 mm
    lip_z, chin_z, chin_y = float(A[17][2]), float(A[152][2]), float(A[152][1])
    t = np.clip((lip_z - 0.003 - V[:, 2]) / max(lip_z - 0.003 - chin_z, 1e-3), 0.0, 1.0)
    hw = 0.013 + 0.011 * np.sqrt(t) + 0.002 * (2.0 * value_noise(V, 0.006, 41) - 1.0)
    gw_, gb_ = float(cfg.get("goat_w", 0.0)), float(cfg.get("goat_back", 0.0))     # (as paint_beard's shape)
    hw = hw + gw_ * t ** 1.5
    goat = ((1.0 - smoothstep(lip_z - 0.005, lip_z - 0.002, V[:, 2])) * smoothstep(chin_z - 0.016, chin_z - 0.006, V[:, 2])
            * (1.0 - smoothstep(hw - 0.007, hw + 0.001, x)) * (1.0 - smoothstep(chin_y + 0.01 + gb_, chin_y + 0.022 + gb_, V[:, 1])))
    goat *= smoothstep(0.002, 0.004, dl)
    # the strap: along the jaw line from the goatee toward the ears, fading out 2-4.5 cm before them, and over the neck
    J = np.array([A[i] for i in JAW_OVAL if i in A])
    dj = np.full(len(V), 1.0)
    for k in range(len(J) - 1):
        dj = np.minimum(dj, seg_dist(V, J[k], J[k + 1]))
    strap = 1.0 - smoothstep(0.004, 0.011, dj + 0.002 * (2.0 * value_noise(V, 0.008, 63) - 1.0))
    su_ = cfg.get("strap_up")
    if su_ is not None and len(J) > 1 and 1 in A:
        # ("strap_up" [soft, reach] m, off by default) on the cheek's side of the jaw line (toward the nose tip from
        # the line's nearest point) the strap reaches only `reach`, its edge fading out from `soft`; under the line it
        # keeps the band above. With the band the same both sides, on the shadow side it reads as a dark hard-edged
        # band over the lower cheek up to the ear
        best = np.full(len(V), 1e9)
        Jn = np.zeros_like(V)
        for k in range(len(J) - 1):
            ab = J[k + 1] - J[k]
            tt = np.clip(((V - J[k]) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
            Q = J[k] + tt[:, None] * ab
            d_ = np.linalg.norm(V - Q, axis=1)
            m_ = d_ < best
            best[m_] = d_[m_]
            Jn[m_] = Q[m_]
        inner = ((V - Jn) * (np.asarray(A[1])[None] - Jn)).sum(1) > 0.0
        up_ = 1.0 - smoothstep(float(su_[0]), float(su_[1]), dj + 0.0015 * (2.0 * value_noise(V, 0.006, 65) - 1.0))
        strap = np.where(inner, np.minimum(strap, up_), strap)
    ears = np.array([A[i] for i in (234, 454) if i in A])
    if len(ears):
        # ("strap_ear", off by default: how far before the ears it fades out, m)
        se_ = cfg.get("strap_ear", (0.02, 0.045))
        strap *= smoothstep(float(se_[0]), float(se_[1]), nearest_landmark(V, ears))
    strap *= smoothstep(0.004, 0.014, V[:, 2] - z_cut(V[:, 1]))
    w = np.maximum(np.maximum(must * k_m, goat * k_g), strap * k_s) * in_body
    if not (w > 0.01).any():
        return 0
    m_, tpm = texels(np.stack([w, np.ones(len(V))], 1))
    ys, xs = np.nonzero(m_[..., 0] > 0.005)
    if not len(ys):
        return 0
    rp = int(0.004 * tpm) + 4
    size = px.shape[0]
    y0, y1, x0, x1 = max(ys.min() - rp, 0), min(ys.max() + rp + 1, size), max(xs.min() - rp, 0), min(xs.max() + rp + 1, size)
    crop = px[y0:y1, x0:x1, :3].copy()
    wm, valid = m_[y0:y1, x0:x1, 0], m_[y0:y1, x0:x1, 1] > 0.99
    lum = crop @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    vf = valid.astype(np.float32)
    broad = gauss_blur(lum * vf, 0.0015 * tpm) / np.maximum(gauss_blur(vf, 0.0015 * tpm), 1e-4)
    fine = np.clip(lum / np.maximum(broad, 1e-4), 0.45, fill)
    a = (wm * valid).astype(np.float32)
    px[y0:y1, x0:x1, :3] = crop + a[..., None] * (col[None, None] * fine[..., None] - crop)
    # (texels darkened by over a tenth of the way: counted over half, amounts of 0.5 or less counted none and the
    # pass was dropped unsaved)
    return int((a > 0.1).sum())


def darken_beard(basemesh, head_faces, in_body, root, cfg):
    """Head scans, outfit key "beard_dark" (a dict, off by default), after paint_beard: the moustache, the goatee and
    a faint strap along the jaw darkened toward `color` (sRGB hex), by `amount` (moustache, goatee, strap) of the way,
    each texel keeping its strand detail (its lightness over the broad tone, 1.5 mm, clamped to 0.45 -`fill`: the skin
    between the strands filled). The moustache a pencil band `must_h` over the lip's edge."""
    maps = json.loads(basemesh["scan_head_maps"])
    V = world_verts(basemesh)
    A = anchor_points(basemesh, root)
    img, size, px = _head_img(maps)
    n = beard_dark_px(px, V, A, in_body, lambda vals: head_texels(basemesh, head_faces, vals, size), cfg, neck_cut(A))
    if not n:
        bpy.data.images.remove(img)
        return
    _save_img(img, px, maps["color"])
    log(f"beard: darkened toward {cfg.get('color', '#1a1411')} ({n} texels over a tenth of the way; moustache, goatee, strap "
        f"{[float(x) for x in cfg.get('amount', (0.6, 0.62, 0.3))]})")


# (side_clear) per side: the ear's front line (MediaPipe face outline from the ear's top down to the jaw's angle), the
# jaw's lower edge from that angle to the chin, and three clean cheek landmarks
SIDE_LINES = (([127, 234, 93, 132, 136], [136, 150, 149, 176, 148, 152], [116, 123, 147]),
              ([356, 454, 323, 361, 365], [365, 379, 378, 400, 377, 152], [345, 352, 376]))


def side_clear_px(px, V, A, in_body, texels, cfg):
    """clear_sides on the head texture's pixels (see paint_brows). Returns the texels toned over 0.3 of the way."""
    ear_r = cfg.get("ear", (0.02, 0.03))        # cleared within ear[0] of the ear's front line, none past ear[1]
    jaw_r = cfg.get("jaw", (0.008, 0.014))      # a strap along the jaw's lower edge kept: none within jaw[0]
    k_e = float(cfg.get("amount", 0.85))
    shade_lo = float(cfg.get("shade_lo", 0.82))
    w_e = np.zeros(len(V))
    sid = np.zeros(len(V))
    if 1 not in A:
        return 0
    mid = float(V[in_body, 0].mean())
    for s, (ear_l, jaw_l, _) in enumerate(SIDE_LINES):
        if not all(i in A for i in ear_l + jaw_l):
            continue
        E = np.array([A[i] for i in ear_l])
        J = np.array([A[i] for i in jaw_l])
        on = np.sign(V[:, 0] - mid) == np.sign(E[0, 0] - mid)
        de = np.full(len(V), 1.0)
        for k in range(len(E) - 1):
            de = np.minimum(de, seg_dist(V, E[k], E[k + 1]))
        best = np.full(len(V), 1e9)
        Q = np.zeros_like(V)
        for k in range(len(J) - 1):
            ab = J[k + 1] - J[k]
            tt = np.clip(((V - J[k]) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
            P_ = J[k] + tt[:, None] * ab
            d_ = np.linalg.norm(V - P_, axis=1)
            m_ = d_ < best
            best[m_] = d_[m_]
            Q[m_] = P_[m_]
        # (on the cheek's side of the jaw's edge: toward the nose tip from its nearest point)
        inner = ((V - Q) * (np.asarray(A[1])[None] - Q)).sum(1) > 0.0
        nz = 0.002 * (2.0 * value_noise(V, 0.007, 71) - 1.0)
        w = (1.0 - smoothstep(float(ear_r[0]), float(ear_r[1]), de + nz)) * \
            smoothstep(float(jaw_r[0]), float(jaw_r[1]), best + nz) * inner
        # the sideburn kept: nothing above the tragus (landmark 234's height), fading in from 93's
        w *= 1.0 - smoothstep(float(A[ear_l[2]][2]), float(A[ear_l[1]][2]), V[:, 2] + nz)
        w *= on & (V[:, 1] < E[:, 1].max() + 0.004)
        w_e = np.maximum(w_e, w)
        sid[on] = s
    w_e *= k_e * in_body
    if not (w_e > 0.01).any():
        return 0
    cks = []
    for _, _, ck_l in SIDE_LINES:
        L_ = np.array([A[i] for i in ck_l if i in A])
        cks.append((nearest_landmark(V, L_) < 0.008).astype(float) if len(L_) else np.zeros(len(V)))
    m_, tpm = texels(np.stack([w_e, cks[0], cks[1], sid, np.ones(len(V))], 1))
    valid = m_[..., 4] > 0.99
    lumw = np.array([0.2126, 0.7152, 0.0722], np.float32)
    srgb = px[..., :3]
    refs = []
    for s in range(2):
        sel = (m_[..., 1 + s] > 0.99) & valid
        refs.append(np.median(np.where(srgb[sel] <= 0.04045, srgb[sel] / 12.92, ((srgb[sel] + 0.055) / 1.055) ** 2.4), 0)
                    if sel.any() else None)
    if refs[0] is None and refs[1] is None:
        return 0
    refs = [r if r is not None else refs[1 - k] for k, r in enumerate(refs)]
    ys, xs = np.nonzero(m_[..., 0] > 0.005)
    rp = int(0.01 * tpm) + 4
    size = px.shape[0]
    y0, y1, x0, x1 = max(ys.min() - rp, 0), min(ys.max() + rp + 1, size), max(xs.min() - rp, 0), min(xs.max() + rp + 1, size)
    c_ = px[y0:y1, x0:x1, :3].astype(np.float64)
    cl = np.where(c_ <= 0.04045, c_ / 12.92, ((c_ + 0.055) / 1.055) ** 2.4)
    v_ = valid[y0:y1, x0:x1].astype(np.float32)
    L = (cl @ lumw).astype(np.float32)
    broad = gauss_blur(L * v_, 0.008 * tpm) / np.maximum(gauss_blur(v_, 0.008 * tpm), 1e-4)
    near = gauss_blur(L * v_, 0.0012 * tpm) / np.maximum(gauss_blur(v_, 0.0012 * tpm), 1e-4)
    we = m_[y0:y1, x0:x1, 0] * v_
    ref = np.where((m_[y0:y1, x0:x1, 3] > 0.5)[..., None], refs[1][None, None], refs[0][None, None])
    # the clean cheek's colour, keeping the broad shading (down to shade_lo of the cheek's) and the skin's own
    # detail at 1.2 mm (within 7 %), so the stubble's strands go and the skin does not turn flat
    shade = np.clip(broad / np.maximum(ref @ lumw, 1e-4), shade_lo, 1.0)
    fine = np.clip(near / np.maximum(broad, 1e-4), 0.93, 1.07)
    out = cl + we[..., None] * (ref * (shade * fine)[..., None] - cl)
    px[y0:y1, x0:x1, :3] = np.clip(np.where(out <= 0.0031308, out * 12.92,
                                            1.055 * np.power(np.maximum(out, 0.0), 1 / 2.4) - 0.055), 0.0, 1.0)
    return int((we > 0.3).sum())


def clear_sides(basemesh, head_faces, in_body, root, cfg):
    """Head scans, outfit key "side_clear" (a dict, off by default), after darken_beard: the stubble on the cheek in
    front of each ear (the head scan's own and paint_beard's, within `ear` [full, none] metres of the ear's front
    line) toned toward the clean cheek's colour by `amount`, keeping a strap along the jaw's lower edge (none within
    `jaw` [none, full] of it) and the sideburn above the tragus. Without it the stubble there forms a broad grey patch
    with a hard vertical front edge."""
    maps = json.loads(basemesh["scan_head_maps"])
    V = world_verts(basemesh)
    A = anchor_points(basemesh, root)
    img, size, px = _head_img(maps)
    n = side_clear_px(px, V, A, in_body, lambda vals: head_texels(basemesh, head_faces, vals, size), cfg)
    if not n:
        bpy.data.images.remove(img)
        return
    _save_img(img, px, maps["color"])
    log(f"sides: the stubble in front of the ears toned toward the cheek ({n} texels over 0.3 of the way; ear "
        f"{[float(x) for x in cfg.get('ear', (0.02, 0.03))]}, jaw {[float(x) for x in cfg.get('jaw', (0.008, 0.014))]})")


def box_blur(a, r, axis):
    """Box filter of half-width r along an axis (edges clamped), by cumulative sums."""
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode='edge'), axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(a.dtype)


def gauss_blur(a, sigma):
    """About a Gaussian of `sigma` texels: three box filters each way."""
    r = max(1, int(round(sigma * 0.85)))     # three boxes of half-width r: variance 3 * r (r + 1) / 3
    for _ in range(3):
        a = box_blur(box_blur(a, r, 0), r, 1)
    return a


def head_texels(basemesh, head_faces, vals, size):
    """Per texel of the head texture (size x size; MakeHuman head UVs as repacked), the vertex values `vals` (n, or
    n x k) interpolated over the head faces' triangles; 0 off them. Also the texels per metre on the head."""
    me = basemesh.data
    V = world_verts(basemesh)
    me.calc_loop_triangles()
    tv = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tv)
    tl = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("loops", tl)
    tp = np.empty(len(me.loop_triangles), np.int64)
    me.loop_triangles.foreach_get("polygon_index", tp)
    tv, tl = tv.reshape(-1, 3), tl.reshape(-1, 3)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    vals = np.asarray(vals, np.float64)
    vv = vals if vals.ndim == 2 else vals[:, None]
    sel = np.nonzero(head_faces[tp] & (np.abs(vv[tv]).max(2).max(1) > 1e-4))[0]
    UVp = uv.reshape(-1, 2)[tl[sel]] * size
    ys, xs, tt, bb, _ = uv_texels(UVp, size, size)
    out = np.zeros((size, size, vv.shape[1]))
    out[ys, xs] = (bb[..., None] * vv[tv[sel][tt]]).sum(1)
    t3 = tv[head_faces[tp]]
    a3 = face_areas(V, t3).sum()
    q = uv.reshape(-1, 2)[tl[head_faces[tp]]] * size
    a2 = 0.5 * np.abs((q[:, 1, 0] - q[:, 0, 0]) * (q[:, 2, 1] - q[:, 0, 1]) -
                      (q[:, 2, 0] - q[:, 0, 0]) * (q[:, 1, 1] - q[:, 0, 1])).sum()
    return (out if vals.ndim == 2 else out[..., 0]), float(np.sqrt(a2 / max(a3, 1e-12)))


def soften_scan_skin(basemesh, head_faces, face_hold, in_body, root, keep=0.35, sigma=0.0008):
    """A head scan's own texture beside the face, where the portrait does not paint (the cheeks turned from the camera
    back to the ears, the jaw and under it, the temples), carries the scan maker's lighting in its colour: stubble
    there reads as crinkled, scaly skin up close, with an edge mid-cheek where the smooth portrait takes over. There
    its fine detail (finer than `sigma`) is kept at `keep` of its strength, its tone (the stubble's shadow) as it is;
    hair (dark texels: the sideburns) is left alone. Before the portrait goes on, so its own feathered edge blends
    into the softened skin."""
    maps = json.loads(basemesh["scan_head_maps"])
    me = basemesh.data
    V = world_verts(basemesh)
    N = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("normal", N)
    N = N.reshape(-1, 3) @ np.array(basemesh.matrix_world)[:3, :3].T
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    A = anchor_points(basemesh, root)
    painted = np.clip((-N[:, 1] - 0.3) / 0.4, 0, 1) * np.clip(face_hold, 0, 1)   # as portrait_project's alpha
    ear_y = max(A[i][1] for i in (234, 454) if i in A) + 0.01
    brow = float(np.mean([A[i][2] for i in BROWS if i in A]))
    chin = float(A[152][2]) if 152 in A else float(V[in_body, 2].min())
    region = in_body & (V[:, 1] < ear_y) & (V[:, 2] < brow + 0.005) & (V[:, 2] > chin - 0.05)
    w = region * (1.0 - painted)
    E = edges(me)
    E = E[in_body[E].all(1)]
    w = smooth(w[:, None], np.ones(len(V)), E, 3)[:, 0] * in_body
    img = bpy.data.images.load(maps["color"], check_existing=False)
    size = img.size[0]
    wm, tpm = head_texels(basemesh, head_faces, w, size)
    ys, xs = np.nonzero(wm > 0.01)
    if not len(ys):
        bpy.data.images.remove(img)
        return
    px = np.empty(size * size * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(size, size, 4)
    sg = sigma * tpm
    m = int(4 * sg) + 2
    y0, y1, x0, x1 = max(ys.min() - m, 0), min(ys.max() + m + 1, size), max(xs.min() - m, 0), min(xs.max() + m + 1, size)
    crop = px[y0:y1, x0:x1, :3].copy()
    low = gauss_blur(crop, sg)
    lum = to_lab(np.clip(low.reshape(-1, 3), 0, 1).astype(np.float64))[:, 0].reshape(low.shape[:2])
    k = wm[y0:y1, x0:x1] * smoothstep(18.0, 30.0, lum)          # not the hair
    px[y0:y1, x0:x1, :3] = crop - ((1.0 - keep) * k)[..., None] * (crop - low)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = maps["color"]
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    log(f"scan skin beside the face: fine detail under {sigma * 1000:.1f} mm ({sg:.1f} px) kept at {keep:.2f} over "
        f"{int((k > 0.5).sum())} texels (not where the portrait paints, not the hair)")


def texture_dirs(P, valid, T3):
    """Per texel, the texture-space direction (dx, dy; unit) along which the surface runs in the 3D direction T3 (per
    texel, h x w x 3), from the texel positions P (h x w x 3) by their local Jacobian; 0 where it cannot be told."""
    Px = np.zeros_like(P)
    Py = np.zeros_like(P)
    Px[:, 1:-1] = (P[:, 2:] - P[:, :-2]) * 0.5
    Py[1:-1, :] = (P[2:, :] - P[:-2, :]) * 0.5
    ok = valid.copy()
    ok[:, 1:-1] &= valid[:, 2:] & valid[:, :-2]
    ok[1:-1, :] &= valid[2:, :] & valid[:-2, :]
    ok[:, [0, -1]] = False
    ok[[0, -1], :] = False
    a11, a12, a22 = (Px * Px).sum(-1), (Px * Py).sum(-1), (Py * Py).sum(-1)
    b1, b2 = (Px * T3).sum(-1), (Py * T3).sum(-1)
    det = a11 * a22 - a12 * a12
    ok &= np.abs(det) > 1e-18
    det = np.where(ok, det, 1.0)
    dx, dy = (a22 * b1 - a12 * b2) / det, (a11 * b2 - a12 * b1) / det
    n = np.maximum(np.hypot(dx, dy), 1e-12)
    return np.where(ok, dx / n, 0.0), np.where(ok, dy / n, 0.0)


def lic(dx, dy, valid, length, seed=0, x0=0, y0=0, cell=1):
    """Line integral convolution of a fixed white noise along a texture-space direction field (dx, dy): streaks
    `length` texels long each way, like strands. Returns values rank-normalised to 0-1 over the valid texels."""
    h, w = dx.shape
    yy, xx = np.indices((h, w))
    noise = texel_hash((xx + x0) // cell, (yy + y0) // cell, seed).astype(np.float32)
    acc = noise.copy()
    cnt = np.ones((h, w), np.float32)
    for sgn in (1.0, -1.0):
        px, py = xx.astype(np.float32), yy.astype(np.float32)
        ddx, ddy = dx.astype(np.float32) * sgn, dy.astype(np.float32) * sgn
        alive = valid.copy()
        for _ in range(length):
            px, py = px + ddx, py + ddy
            ix = np.clip(np.round(px).astype(np.int64), 0, w - 1)
            iy = np.clip(np.round(py).astype(np.int64), 0, h - 1)
            alive &= valid[iy, ix]
            acc += noise[iy, ix] * alive
            cnt += alive
            # (follow the field as it turns, keeping the direction's sign)
            nx, ny = dx[iy, ix], dy[iy, ix]
            flip = (nx * ddx + ny * ddy) < 0
            ddx = np.where(alive, np.where(flip, -nx, nx), ddx).astype(np.float32)
            ddy = np.where(alive, np.where(flip, -ny, ny), ddy).astype(np.float32)
    v = acc / cnt
    out = np.zeros((h, w), np.float32)
    if valid.any():
        vv = v[valid]
        out[valid] = (np.argsort(np.argsort(vv)) + 0.5) / len(vv)
    return out


def hair_tone(basemesh):
    """The person's hair colours for paint on the skin (sRGB): the scan hair's darkest and its tips', from the outfit's
    hair_cards ("under" and "tip") as the cards are tinted, else a dark brown default."""
    hc = basemesh.get("scan_hair_tones")
    if hc:
        return [np.array(c, np.float64) for c in json.loads(hc)]
    return [np.array([0.067, 0.055, 0.051]), np.array([0.141, 0.114, 0.098])]


def skin_fill(crop, keep_w, tpm, sigma=0.0025, detail_from=None, grain=0.001):
    """The skin under a region repainted from the skin round it: a normalised blur of the texels with keep_w (the clean
    skin round the region), at `sigma` (and four times that further in), plus fine detail (finer than `grain`) borrowed
    from the texels `detail_from` = (sy, sx) maps, where given (pores and stubble: a smooth fill alone stayed a smooth,
    pale patch)."""
    sk = sigma * tpm
    num = gauss_blur(crop * keep_w[..., None], sk)
    den = gauss_blur(keep_w, sk)
    num2 = gauss_blur(crop * keep_w[..., None], 4 * sk)
    den2 = gauss_blur(keep_w, 4 * sk)
    t_ = smoothstep(0.02, 0.1, den)[..., None]
    skin = t_ * num / np.maximum(den, 1e-4)[..., None] + (1 - t_) * num2 / np.maximum(den2, 1e-4)[..., None]
    if detail_from is not None:
        sy, sx, ok = detail_from
        detail = crop - gauss_blur(crop, grain * tpm)
        skin = skin + detail[sy, sx] * ok[..., None]
    return skin


def away_from(region, tpm, dist):
    """For every texel, the texel `dist` (m) away from `region` (a 0-1 map) along its blurred gradient, and whether that
    one lies outside it (where to borrow the skin's grain from)."""
    B = gauss_blur(region.astype(np.float32), 0.006 * tpm)
    gy, gx = np.gradient(B)
    gn = np.maximum(np.hypot(gx, gy), 1e-9)
    hy, hx = np.indices(region.shape)
    sy = np.clip(np.round(hy - gy / gn * dist * tpm).astype(int), 0, region.shape[0] - 1)
    sx = np.clip(np.round(hx - gx / gn * dist * tpm).astype(int), 0, region.shape[1] - 1)
    ok = ((region[sy, sx] < 0.05) & (gn > 1e-6)).astype(np.float32)
    return sy, sx, ok


def _head_img(maps, key="color"):
    img = bpy.data.images.load(maps[key], check_existing=False)
    size = img.size[0]
    px = np.empty(size * size * 4, np.float32)
    img.pixels.foreach_get(px)
    return img, size, px.reshape(size, size, 4)


def _save_img(img, px, path):
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


TEX_MASKS = {}          # texel masks one texture pass leaves for the next (paint_sideburns -> clean_lobes)


def _tex_mask(key, size, y0, y1, x0, x1):
    """A texel mask a texture pass left (TEX_MASKS) over the crop y0:y1, x0:x1 of a size x size map (0 elsewhere)."""
    out = np.zeros((y1 - y0, x1 - x0), np.float32)
    if key not in TEX_MASKS:
        return out
    sy0, sx0, sm = TEX_MASKS[key]
    full = np.zeros((size, size), np.float32)
    full[sy0:sy0 + sm.shape[0], sx0:sx0 + sm.shape[1]] = sm
    return full[y0:y1, x0:x1]


def _shell_rim_distance(V, step_m=None, steps=24):
    """Per point (the head's vertices): how far (m) it lies under the hair shell's rim (> 0: below it, outside the
    shell; < 0: under the shell, that far in from its rim), by the envelope's cap texels (HAIR_COVER) and the point's
    own distance from the head's centre. None without a hair envelope."""
    if not HAIR_COVER:
        return None
    c, cov, M = HAIR_COVER["c"], HAIR_COVER["cov"], HAIR_COVER["M"]
    U, r, th = _env_uv(V, c)
    ix = np.clip((U[:, 0] * M).astype(int), 0, M - 1)
    iy = np.clip((U[:, 1] * M).astype(int), 0, M - 1)
    d_out = np.full((M, M), float(steps))
    m = cov.copy()
    for k in range(1, steps + 1):
        m2 = _bmax(m, 1)
        d_out[m2 & ~m] = k - 0.5
        m = m2
    d_out[cov] = 0.0
    d_in = np.zeros((M, M))
    m = cov.copy()
    for k in range(1, steps + 1):
        m2 = _bmin(m, 1)
        d_in[m & ~m2] = k - 0.5
        m = m2
    d_in[m] = float(steps)
    # (a cap texel spans HAIR_ENV_TH / (0.49 M) radians from the centre)
    dth = HAIR_ENV_TH / (0.49 * M)
    return (d_out[iy, ix] - d_in[iy, ix]) * dth * r


def paint_sideburns(basemesh, head_faces, in_body, root, density=0.7, end=0.0, fade=0.007, rim=0.007, width=0.016,
                    lay=0.8):
    """Head scans: the hair the head scan paints on the skin beside the face, in front of the ears and at the temples
    up to the hair shell, repainted as strands. The head scan paints its sideburns and its temples' hair as flat dark
    bands with ruler-straight edges. The scalp cap (hair_scan_cards), which learns where hair is from this texture,
    draws such sideburns as flat grey-black plates, and the temples' paint below the shell's rim, where no card grows
    (the shell ends 15 mm over the brows), reads as a flat wedge with hard straight edges between the hair and the
    brow's tail at the game's dialogue distance. Beside the face from the tragus up to the brows' height and back to
    the ears, the scan's paint is taken out (the skin round it, with its grain from 1.2 cm away, spread in: skin_fill)
    except deep under the shell (more than 6 mm in from its rim: the cards and the cap cover it), and painted back as
    short dark strands running down the face (a line integral convolution of a noise along the surface's downward
    direction) in clumps, toned like the hair (hair_tone; a fifth of the tone the skin's own, darkened: the hair's
    neutral dark read cool grey-blue in profile) over skin a little darker under them, `density` of the skin covered
    at most, laid on at `lay`: a band `rim` under the shell's rim all along the side (from the temple to the ear, its
    edge wandering, thinning out) blending into the paint under the shell, and the sideburn in front of each ear,
    `width` wide from the ear's front (both sides alike, its front edge wandering 4 mm over 1 cm), ending `end` over
    the ear canal over `fade`, each strand at its own height."""
    maps = json.loads(basemesh["scan_head_maps"])
    V = world_verts(basemesh)
    A = anchor_points(basemesh, root)
    if 234 not in A or 454 not in A:
        return
    mid = float(V[in_body, 0].mean())
    eg = ear_group(basemesh, in_body)
    brow_z = float(np.mean([A[i][2] for i in BROWS if i in A]))
    sd = _shell_rim_distance(V)
    if sd is None:
        sd = np.full(len(V), 1.0)
    reg = np.zeros(len(V))
    sb = np.zeros(len(V))
    xs_ = V[:, 0] - mid
    for i in (234, 454):
        t = A[i]
        side = np.sign(t[0] - mid)
        es = eg & (np.sign(V[:, 0] - mid) == side)
        ef = float(np.percentile(V[es, 1], 5)) if es.sum() > 10 else float(t[1]) + 0.01
        # beside the face: the side of the head from the tragus' height up to 4 cm over the brows, from the ear's front
        # forward to 6.5 cm in front of it (the brow's tail), not the eye and not the brow
        lat = smoothstep(abs(t[0] - mid) - 0.03, abs(t[0] - mid) - 0.018, xs_ * side)
        reg = np.maximum(reg, lat * (1.0 - smoothstep(ef + 0.002, ef + 0.008, V[:, 1]))
                         * smoothstep(ef - 0.085, ef - 0.075, V[:, 1])
                         * smoothstep(t[2] - 0.06, t[2] - 0.045, V[:, 2])
                         * (1.0 - smoothstep(brow_z + 0.03, brow_z + 0.045, V[:, 2])))
        # the sideburn: `width` in front of the ear's front, its front edge wandering
        fw = width + 0.004 * (2.0 * value_noise(V, 0.01, 31 + int(side > 0)) - 1.0)
        sb = np.maximum(sb, lat * smoothstep(ef - fw - 0.003, ef - fw + 0.002, V[:, 1])
                        * (1.0 - smoothstep(ef + 0.001, ef + 0.005, V[:, 1])))
    # (not the eyes, nor the brows themselves: kept 6-12 mm off the brows too, the scan's grey paint just over the left
    # brow's tail stayed, a translucent grey patch with pale curl outlines in profile)
    reg *= smoothstep(0.006, 0.012, nearest_landmark(V, np.array([A[i] for i in RIGHT_EYE + LEFT_EYE if i in A])))
    Bz = np.array([A[i] for i in BROWS if i in A])
    db = np.sqrt(((V[:, None, :] - Bz[None]) ** 2).sum(-1))
    above = V[:, 2] > Bz[db.argmin(1), 2] + 0.002          # (BROWS are the brows' upper edge)
    reg *= np.where(above, smoothstep(0.002, 0.004, db.min(1)), smoothstep(0.0045, 0.009, db.min(1)))
    if eg.any():
        reg *= smoothstep(0.0015, 0.004, nearest_landmark(V, V[eg]))
    reg *= in_body
    if not (reg > 0.01).any():
        return
    z_ear = float(np.percentile(V[eg, 2], 30)) if eg.sum() > 20 else float((A[234][2] + A[454][2]) / 2)
    img, size, px = _head_img(maps)
    m, tpm = head_texels(basemesh, head_faces, np.stack([reg, V[:, 0], V[:, 1], V[:, 2], np.ones(len(V)), sd, sb], 1),
                         size)
    ys, xs = np.nonzero(m[..., 0] > 0.01)
    if not len(ys):
        bpy.data.images.remove(img)
        return
    r = int(0.012 * tpm) + 4
    y0, y1, x0, x1 = max(ys.min() - r, 0), min(ys.max() + r + 1, size), max(xs.min() - r, 0), min(xs.max() + r + 1, size)
    crop = px[y0:y1, x0:x1, :3].copy()
    w = m[y0:y1, x0:x1, 0]
    Pm = m[y0:y1, x0:x1, 1:4]
    valid = m[y0:y1, x0:x1, 4] > 0.99
    sdt = m[y0:y1, x0:x1, 5]
    sbt = m[y0:y1, x0:x1, 6]
    P = Pm.reshape(-1, 3)
    lab_ = to_lab(np.clip(crop.reshape(-1, 3), 0, 1).astype(np.float64))
    L = lab_[:, 0].reshape(w.shape)
    chroma = np.hypot(lab_[:, 1], lab_[:, 2]).reshape(w.shape)
    # (dark paint, and the scan's translucent grey paint: skin is warm, its chroma well over 12)
    hair = np.maximum(smoothstep(32.0, 20.0, L), smoothstep(13.0, 8.0, chroma) * smoothstep(68.0, 55.0, L))
    hair = hair.astype(np.float32) * (w > 0.001)
    band = (gauss_blur(hair, 0.0012 * tpm) > 0.3).astype(np.float32)
    grown = (gauss_blur(band, 0.0015 * tpm) > 0.03).astype(np.float32)
    cover = smoothstep(0.3, 0.7, gauss_blur(grown, 0.001 * tpm))
    # 1. out: the skin round the scan's paint spread over it, with the skin's grain from 1.2 cm away
    keep_w = ((L > 24) * (w > 0.001) * (grown < 0.5)).astype(np.float32)
    base = skin_fill(crop, keep_w, tpm, detail_from=away_from(band, tpm, 0.012))
    ok = smoothstep(0.005, 0.03, np.maximum(gauss_blur(keep_w, 0.0025 * tpm), gauss_blur(keep_w, 0.01 * tpm)))
    zz = P[:, 2].reshape(w.shape)
    wob = (0.45 * (value_noise(P, 0.01, 6).reshape(w.shape) - 0.5) + 0.35 * (value_noise(P, 0.005, 7).reshape(w.shape) - 0.5)
           + 0.25 * (value_noise(P, 0.0025, 8).reshape(w.shape) - 0.5))
    # 2. back in as strands: under the shell's rim (dense, thinning out `rim` below it, its edge wandering), the scan's
    # own paint below the rim (feathered, half as dense: the temples' short hair) and the sideburns (ending over the ear
    # canal); more than 14-24 mm in under the shell the scan's paint stays (the cards and the cap cover it), and the
    # strands are densest just outside that, so they run into it (cut off 3-8 mm in, a hard edge stays between the
    # dark paint and the lighter strands)
    rim_w = 1.0 - smoothstep(-0.004, rim * (1.0 + 0.8 * wob), sdt)
    # (the sideburn down to the ear's lower third: ending at the ear's middle it left the skin in front of the lower
    # ear bare between the temples' hair and the stubble on the jaw)
    zl = z_ear + end + 0.004 * (value_noise(P, 0.01, 6).reshape(w.shape) - 0.5)
    low = smoothstep(zl - fade, zl, zz)
    sbs = np.clip(gauss_blur(sbt.astype(np.float32), 0.0025 * tpm) * 1.25 + 0.6 * wob, 0.0, 1.0) * low
    deep = smoothstep(-0.014, -0.024, sdt)
    # (the scan's own paint below the rim as a soft dark wash of strands: its own edge blurred over 4 mm and
    # wandering, so neither its hard straight edges nor a flat patch stay; taken out altogether, the skin spread over
    # it reads as a pale smeared strip down the temple)
    soft_paint = smoothstep(0.15, 0.85, gauss_blur(band, 0.004 * tpm) + 0.3 * wob) * low
    dens = np.maximum(np.maximum(0.95 * rim_w * rim_w, 0.8 * soft_paint), density * sbs) * (w > 0.001)
    soft = np.clip(dens / density, 0.0, 1.0)
    # strand direction: down the face, a little back (sideburns grow down)
    T3 = np.zeros_like(Pm)
    T3[..., 1], T3[..., 2] = 0.25, -1.0
    dxm, dym = texture_dirs(Pm, valid, T3)
    # (strands two texels wide, 0.4 mm: one texel wide they read as scratches; 5 mm long: at 3 mm, evenly spaced, the
    # band read as a stamped patch of vertical dashes at 0.6 m in the game)
    u = lic(dxm, dym, valid & (dxm ** 2 + dym ** 2 > 0.5), int(round(0.005 * tpm)), seed=21, x0=x0, y0=y0, cell=2)
    # (each strand ends at its own height, up to 12 mm over the band's end: ending together, along the band's edge, they
    # drew a crisp, stepped lower edge in profile; the LIC value is constant along a strand)
    own = np.mod(u * 13.7, 1.0)
    dens = dens * smoothstep(zl - 0.002, zl + 0.012 * own, zz)
    strand = smoothstep(1.0 - dens - 0.1, 1.0 - dens + 0.1, u) * (dens > 0.005)
    # (in clumps, sparser between them: evenly spaced, the strands read as a patch of brush dashes)
    clump = smoothstep(0.25, 0.75, value_noise(P, 0.003, 9).reshape(w.shape))
    strand = strand * (0.6 + 0.4 * clump)
    strand = gauss_blur(strand.astype(np.float32), 0.6)
    dark, tip = hair_tone(basemesh)
    tone = dark[None, None] + (tip - dark)[None, None] * smoothstep(0.0, 1.0, (u * 7.0) % 1.0)[..., None]
    tone = tone + 0.12 * (base * 0.32 - tone)
    under = base * (1.0 - 0.35 * np.clip(dens * 1.2, 0, 1))[..., None]
    lay_t = lay + (0.88 - lay) * rim_w
    paint = under + (strand * lay_t)[..., None] * (tone - under)
    a = (w * np.maximum(cover, soft > 0.01) * ok * (1.0 - deep)).astype(np.float32)
    # (and the scan's paint kept under the shell toned towards the hair's dark; kept from 8 mm in, its translucent grey
    # hairline, with pale curl outlines painted in it, showed between the cards as a grey-blue patch over the left brow's
    # tail)
    k_d = (0.85 * cover * w * deep).astype(np.float32)
    crop = crop + k_d[..., None] * (dark[None, None] * 1.2 - crop)
    new = crop + a[..., None] * (paint - crop)
    px[y0:y1, x0:x1, :3] = new
    TEX_MASKS["sideburns"] = (y0, x0, (gauss_blur((sbs * (w > 0.001)).astype(np.float32), 0.001 * tpm) * w).astype(np.float32))
    # (the whole painted hairline and the scan's paint kept under the shell: the passes after the portrait leave it)
    TEX_MASKS["hairline"] = (y0, x0, np.clip(gauss_blur((np.maximum(soft, deep * cover) * (w > 0.001)).astype(np.float32),
                                                        0.0015 * tpm) * 1.5, 0, 1).astype(np.float32))
    _save_img(img, px, maps["color"])
    log(f"sideburns: the painted bands ({int((band * w > 0.5).sum())} texels) taken out beside the face up to the hair "
        f"shell (its paint kept over 14-24 mm in under the shell, toned towards the hair's dark: {int((deep * w > 0.5).sum())} texels) and painted back as "
        f"strands ({density:.2f} of the skin covered on the sideburns, 0.95 at the shell's rim, 0.8 over its paint softened, "
        f"laid on at {lay:.2f}-0.88, "
        f"toned like the hair): a band {rim * 1000:.0f} mm under the shell's rim and the sideburns {width * 1000:.0f} mm wide in front of each ear, ending {end * 1000:+.0f} mm "
        f"over the ear's lower third over {fade * 1000:.0f} mm")


def clean_lobes(basemesh, head_faces, in_body, root, reach=0.014, under=0.024):
    """Head scans: the skin in front of and under each ear repainted from the skin round it. The head scan paints its
    own earlobe lower and further forward than the character's, fused to the cheek (no flap for drop_scan_ears to
    find): a pale rounded nub with a shadow outline, a second earlobe; and between the tragus and the cheek the
    template's and the fill's smooth paler skin met the scan's pored cheek along a vertical edge (a pale, poreless
    strip). In front of the ear's lower half within `reach` of it, and under its lobe down to `under` below it, the
    colour becomes that of the clean skin just outside (a normalised blur over 4 mm and more, skin_fill), with the
    grain of the skin 1.5 cm further from the ear."""
    maps = json.loads(basemesh["scan_head_maps"])
    eg = ear_group(basemesh, in_body)
    if not eg.any():
        return
    V = world_verts(basemesh)
    mid = float(V[in_body, 0].mean())
    d_ear = nearest_landmark(V, V[eg])
    w = np.zeros(len(V))
    for side in (-1.0, 1.0):
        e = eg & (np.sign(V[:, 0] - mid) == side)
        if e.sum() < 10:
            continue
        s_ = (np.sign(V[:, 0] - mid) == side) & in_body
        z0, z1 = np.percentile(V[e, 2], [0, 100])
        y_front, y_back = np.percentile(V[e, 1], [5, 95])
        lobe = e & (V[:, 2] < z0 + 0.3 * (z1 - z0))
        yl0, yl1 = np.percentile(V[lobe, 1], [0, 100]) if lobe.any() else (y_front, y_back)
        zm = z0 + 0.6 * (z1 - z0)
        off = smoothstep(0.0004, 0.0015, d_ear)
        front = (1.0 - smoothstep(reach * 0.6, reach, d_ear)) * (1.0 - smoothstep(y_front + 0.004, y_front + 0.012, V[:, 1])) \
            * (1.0 - smoothstep(zm, zm + 0.008, V[:, 2]))
        below = (1.0 - smoothstep(under * 0.7, under, d_ear)) * (1.0 - smoothstep(z0 + 0.1 * (z1 - z0), z0 + 0.3 * (z1 - z0), V[:, 2])) \
            * smoothstep(yl0 - 0.018, yl0 - 0.008, V[:, 1]) * (1.0 - smoothstep(yl1, yl1 + 0.008, V[:, 1]))
        w = np.maximum(w, off * np.maximum(front, below) * s_)
    if not (w > 0.01).any():
        return
    img, size, px = _head_img(maps)
    y_fr = {sd_: float(np.percentile(V[eg & (np.sign(V[:, 0] - mid) == sd_), 1], 5)) for sd_ in (-1.0, 1.0)
            if (eg & (np.sign(V[:, 0] - mid) == sd_)).any()}
    m, tpm = head_texels(basemesh, head_faces, np.stack([w, eg.astype(np.float64), V[:, 0] - mid, V[:, 1],
                                                         np.ones(len(V))], 1), size)
    ys, xs = np.nonzero(m[..., 0] > 0.01)
    r = int(0.03 * tpm) + 4
    y0, y1, x0, x1 = max(ys.min() - r, 0), min(ys.max() + r + 1, size), max(xs.min() - r, 0), min(xs.max() + r + 1, size)
    crop = px[y0:y1, x0:x1, :3].copy()
    wc, ec = m[y0:y1, x0:x1, 0], m[y0:y1, x0:x1, 1]
    xc, yc, okc = m[y0:y1, x0:x1, 2], m[y0:y1, x0:x1, 3], m[y0:y1, x0:x1, 4] > 0.99
    L = to_lab(np.clip(crop.reshape(-1, 3), 0, 1).astype(np.float64))[:, 0].reshape(wc.shape)
    on = (wc > 0.02).astype(np.float32)
    ring = (gauss_blur(on, 0.006 * tpm) > 0.01) & (wc <= 0.02)
    texel = np.zeros_like(on, bool)
    texel[ys - y0, xs - x0] = True
    keep_w = (ring & (L > 30) & (ec < 0.05) & (gauss_blur(texel.astype(np.float32), 2.0) > 0.0)).astype(np.float32)
    fill = skin_fill(crop, keep_w, tpm, sigma=0.004, detail_from=away_from(on, tpm, 0.015))
    # each side's fill toned to the cheek in front of it (its skin, stubble too, 1.2-3 cm in front of the ear): the
    # ring round the region is mostly the paler skin under and behind the lobe, and the strip by the left tragus came
    # out lighter and smoother than the cheek
    gains = []
    for sd_, yf_ in y_fr.items():
        sidem = okc & (np.sign(xc) == sd_)
        cheek = sidem & (wc <= 0.02) & (yc < yf_ - 0.012) & (yc > yf_ - 0.03) & (L > 22) & (ec < 0.05) & \
            (gauss_blur(on, 0.012 * tpm) > 0.01)
        reg = sidem & (wc > 0.3)
        if cheek.sum() > 200 and reg.sum() > 200:
            Y_ = np.array([0.2126, 0.7152, 0.0722])
            g = float(np.median(to_linear(np.clip(crop[cheek], 0, 1).astype(np.float64)) @ Y_) /
                      max(np.median(to_linear(np.clip(fill[reg], 0, 1).astype(np.float64)) @ Y_), 1e-5))
            g = float(np.clip(g, 0.8, 1.03))
            sel_ = sidem & (wc > 0.0)
            fill[sel_] = to_srgb(to_linear(np.clip(fill[sel_], 0, 1).astype(np.float64)) * g).astype(np.float32)
            gains.append(f"{'right' if sd_ < 0 else 'left'} {g:.2f}")
    a = smoothstep(0.0, 0.5, wc).astype(np.float32)
    if "sideburns" in TEX_MASKS:
        # (not the sideburns paint_sideburns has just painted down to the tragus)
        sy0, sx0, sm = TEX_MASKS["sideburns"]
        full = np.zeros((size, size), np.float32)
        full[sy0:sy0 + sm.shape[0], sx0:sx0 + sm.shape[1]] = sm
        a *= 1.0 - smoothstep(0.02, 0.25, full[y0:y1, x0:x1])
    px[y0:y1, x0:x1, :3] = crop + a[..., None] * (fill - crop)
    _save_img(img, px, maps["color"])
    log(f"ears: the skin in front of and under each lobe repainted from the skin round it ({int((a > 0.5).sum())} texels; "
        f"the scan's own earlobe and the pale strip by the tragus), toned to the cheek in front ({', '.join(gains)})")


def nostril_skin(basemesh, head_faces, in_body, root, work, reach=0.022, core=0.55):
    """Head scans, after the portrait: the nose's underside takes the template's own skin (its nostrils painted for its
    own nostrils: dark openings with their walls shading into them), toned to the head scan's skin round it. The bake
    lays the head scan's nostrils, black holes painted larger than the template's openings, over the template's nose:
    from below they were black disks with a ragged dark halo on the rims, and in profile a crisp black slash on each
    wing; darkened by occlusion or repainted by depth, the template's few vertices there gave blobs. Where the nose
    faces down or is enclosed (within `reach` of its tip, over the lip, inside its wings), the colour becomes the
    template's skin (bake_skin_head.png, the template's texture in the head's UVs) times a gain in linear RGB, the
    ratio of the two skins on the nose round it; the edge blends over a few millimetres."""
    A = anchor_points(basemesh, root)
    path = os.path.join(work, "bake_skin_head.png")
    if 1 not in A or 2 not in A or not os.path.exists(path):
        return
    V = world_verts(basemesh)
    Tri = triangles(basemesh.data)
    Tri = Tri[in_body[Tri].all(1)]
    N = vertex_normals(V, Tri)
    tip, sub = A[1], A[2]
    mid = float(tip[0])
    wing = max(abs(A[i][0] - mid) for i in (129, 358, 64, 294) if i in A) if any(i in A for i in (129, 358)) else 0.018
    nose_v = in_body & (np.linalg.norm(V - tip, axis=1) < 0.03) & (V[:, 2] > sub[2] - 0.0015) & \
        (np.abs(V[:, 0] - mid) < wing + 0.002)
    nt = Tri[nose_v[Tri].all(1)]
    bvh = BVHTree.FromPolygons(V.tolist(), nt.tolist(), all_triangles=True)
    k = np.arange(32) + 0.5
    phi, th = np.arccos(1 - 2 * k / 32), math.pi * (1 + 5 ** 0.5) * k
    dirs = np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], 1)
    occ = np.zeros(len(V))
    for i in np.nonzero(nose_v)[0]:
        hemi = dirs[dirs @ N[i] > 0.1]
        occ[i] = sum(bvh.ray_cast(Vector(V[i] + N[i] * 2e-4), Vector(d), 0.025)[0] is not None for d in hemi) / \
            max(len(hemi), 1)
    near = 1.0 - smoothstep(reach * 0.75, reach, np.linalg.norm(V - tip, axis=1))
    w = nose_v * near * np.maximum(smoothstep(-0.2, -0.5, N[:, 2]), smoothstep(0.25, 0.4, occ))
    ring = nose_v & (w < 0.05) & (N[:, 2] > -0.2) & (np.linalg.norm(V - tip, axis=1) < reach + 0.008)
    if not (w > 0.05).any() or not ring.any():
        return
    maps = json.loads(basemesh["scan_head_maps"])
    img, size, px = _head_img(maps)
    timg = bpy.data.images.load(path, check_existing=False)
    tpx = np.empty(size * size * 4, np.float32)
    if timg.size[0] != size:
        timg.scale(size, size)
    timg.pixels.foreach_get(tpx)
    tpx = tpx.reshape(size, size, 4)
    bpy.data.images.remove(timg)
    m, tpm = head_texels(basemesh, head_faces, np.stack([w, ring.astype(np.float64)], 1), size)
    rt = m[..., 1] > 0.5
    lt = to_linear(px[rt, :3].astype(np.float64))
    lb = to_linear(tpx[rt, :3].astype(np.float64))
    yl = lt @ np.array([0.2126, 0.7152, 0.0722])
    ok = yl > np.percentile(yl, 30)
    gain = np.clip(np.median(lt[ok], 0) / np.maximum(np.median(lb[ok], 0), 1e-4), 0.4, 1.6)
    ys, xs = np.nonzero(m[..., 0] > 0.005)
    y0, y1, x0, x1 = max(ys.min() - 8, 0), min(ys.max() + 9, size), max(xs.min() - 8, 0), min(xs.max() + 9, size)
    a = smoothstep(0.05, 0.6, gauss_blur(m[y0:y1, x0:x1, 0].astype(np.float32), 0.0006 * tpm))[..., None]
    a = a * (m[y0:y1, x0:x1, 0] > 0.0)[..., None]
    tlin = to_linear(tpx[y0:y1, x0:x1, :3].astype(np.float64).reshape(-1, 3)) * gain
    # (the openings' cores a little deeper than the template paints them)
    rel = (tlin @ np.array([0.2126, 0.7152, 0.0722])) / max(float(np.median(lt[ok] @ np.array([0.2126, 0.7152, 0.0722]))), 1e-4)
    tlin *= (1.0 - core * smoothstep(0.7, 0.3, rel))[:, None]
    tl = to_srgb(tlin).reshape(a.shape[:2] + (3,))
    px[y0:y1, x0:x1, :3] = px[y0:y1, x0:x1, :3] + a * (tl - px[y0:y1, x0:x1, :3])
    _save_img(img, px, maps["color"])
    log(f"nostrils: the nose's underside ({int((m[..., 0] > 0.5).sum())} texels) takes the template's own skin and "
        f"nostrils, toned to the scan's nose (gain {np.round(gain, 2).tolist()})")


def neck_shading(basemesh, head_faces, in_body, root, big=0.016, small=0.0015, floor=2.0):
    """Head scans: dark blots of baked shading on the sides of the neck lifted. The full-resolution head scan carries
    its maker's lighting, and can paint a dark dimple on the side of the neck under the ear (a muscle's shadow) that
    reads as a dent in any light. On the neck's sides (under the earlobes, 2 cm or more from the face's inner
    landmarks, beside the throat), wherever the colour blurred over `small` is darker than over `big` by more than
    `floor` (Lab L) and smooth (stubble and pores, with fine detail of their own, stay), the colour is lifted by the
    ratio, its finer detail kept."""
    A = anchor_points(basemesh, root)
    if 152 not in A:
        return
    V = world_verts(basemesh)
    L_ = np.array([p for i, p in A.items() if i not in set(OVAL)])
    mid = float(V[in_body, 0].mean())
    eg = ear_group(basemesh, in_body)
    z_lobe = float(V[eg, 2].min()) if eg.any() else float(A[152][2]) + 0.04
    w = in_body * (1.0 - smoothstep(z_lobe - 0.01, z_lobe, V[:, 2])) * \
        smoothstep(0.015, 0.025, nearest_landmark(V, L_)) * smoothstep(0.02, 0.035, np.abs(V[:, 0] - mid))
    if eg.any():
        # (in front of the ears' middle: behind it the nape is the dark hair absent_maps gives it, whose edge read as
        # a blot to lift)
        y_ear = float(np.median(V[eg, 1]))
        w = w * (1.0 - smoothstep(y_ear, y_ear + 0.015, V[:, 1]))
    if not (w > 0.01).any():
        return
    maps = json.loads(basemesh["scan_head_maps"])
    img, size, px = _head_img(maps)
    m, tpm = head_texels(basemesh, head_faces, np.stack([w, np.ones(len(V))], 1), size)
    # each piece of the region on its own (the two sides lie far apart in the texture)
    small_m = (m[::16, ::16, 0] > 0.01).astype(np.uint8)
    lab_ = components_2d(small_m)
    total, worst = 0, 0.0
    for lid in range(1, lab_.max() + 1):
        yy, xx = np.nonzero(lab_ == lid)
        r = int(2 * big * tpm) + 8
        y0, y1 = max(yy.min() * 16 - r, 0), min((yy.max() + 1) * 16 + r, size)
        x0, x1 = max(xx.min() * 16 - r, 0), min((xx.max() + 1) * 16 + r, size)
        crop = px[y0:y1, x0:x1, :3].copy()
        wc, on = m[y0:y1, x0:x1, 0].astype(np.float32), (m[y0:y1, x0:x1, 1] > 0.5).astype(np.float32)
        lin = to_linear(np.clip(crop, 0, 1)).astype(np.float32)
        lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        nrm = lambda x, sg: gauss_blur(x * on, sg) / np.maximum(gauss_blur(on, sg), 1e-4)
        lo, hi = nrm(lum, small * tpm), nrm(lum, big * tpm)
        Llo = 116 * np.cbrt(np.maximum(lo, 1e-6)) - 16
        Lhi = 116 * np.cbrt(np.maximum(hi, 1e-6)) - 16
        deficit = np.clip(Lhi - Llo - floor, 0, None) * (on > 0)
        Lf = 116 * np.cbrt(np.maximum(lum, 1e-6)) - 16
        sg = 0.0006 * tpm
        fine = np.sqrt(np.maximum(nrm(Lf ** 2, sg) - nrm(Lf, sg) ** 2, 0))
        a = smoothstep(0.0, 3.0, deficit) * smoothstep(0.0, 0.5, wc) * (1.0 - smoothstep(4.0, 8.0, fine))
        a = gauss_blur(a.astype(np.float32), 0.001 * tpm) * (on > 0)
        gain = np.clip(hi / np.maximum(lo, 1e-6), 1.0, 2.0)
        new = lin * (1.0 + a * (gain - 1.0))[..., None]
        px[y0:y1, x0:x1, :3] = to_srgb(new)
        total += int((a > 0.5).sum())
        worst = max(worst, float((deficit * (wc > 0.5)).max()))
    _save_img(img, px, maps["color"])
    log(f"neck: dark blots of baked shading on its sides lifted ({total} texels, at most {worst:.0f} L under the skin "
        f"round them)")


def components_2d(mask):
    """4-connected components of a small 2D mask (labels 1..n, 0 outside)."""
    h, w = mask.shape
    idx = np.arange(h * w).reshape(h, w)
    E = np.concatenate([np.stack([idx[:, :-1].ravel(), idx[:, 1:].ravel()], 1)[(mask[:, :-1] & mask[:, 1:]).ravel() > 0],
                        np.stack([idx[:-1, :].ravel(), idx[1:, :].ravel()], 1)[(mask[:-1, :] & mask[1:, :]).ravel() > 0]])
    lab = components(h * w, E) if len(E) else np.arange(h * w)
    out = np.zeros(h * w, np.int64)
    on = mask.ravel() > 0
    _, inv = np.unique(lab[on], return_inverse=True)
    out[on] = inv + 1
    return out.reshape(h, w)


def tone_ears(basemesh, head_faces, in_body, keep):
    """Head scans: the ears keep the template's skin (ear_mask), toned with the hands to the face's mid skin, and read
    paler than the scan's cheek beside them (the scan's skin darkens towards the sides). Each ear's kept skin is toned
    to the skin just in front of it (a gain in linear RGB, the ratio of the two medians, 0.7-1.2)."""
    maps = json.loads(basemesh["scan_head_maps"])
    eg = ear_group(basemesh, in_body)
    if not eg.any():
        return
    V = world_verts(basemesh)
    mid = float(V[in_body, 0].mean())
    d = nearest_landmark(V, V[eg])
    img = bpy.data.images.load(maps["color"], check_existing=False)
    size = img.size[0]
    px = np.empty(size * size * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(size, size, 4)
    gains = []
    for side in (-1.0, 1.0):
        s_ = (np.sign(V[:, 0] - mid) == side) & in_body
        ear_w = np.clip(keep, 0, 1) * s_ * (d < 0.016)
        root_y = float(V[eg & s_, 1].min()) if (eg & s_).any() else 0.0
        ring = (s_ & ~eg & (d > 0.004) & (d < 0.03) & (V[:, 1] < root_y + 0.004) & (keep < 0.05)).astype(np.float64)
        m, _ = head_texels(basemesh, head_faces, np.stack([ear_w, ring], 1), size)
        e_t, r_t = m[..., 0] > 0.5, m[..., 1] > 0.5
        # (the cheek's skin, not the sideburn in front of the ear's top)
        ry, rx = np.nonzero(r_t)
        dark = to_lab(np.clip(px[ry, rx, :3], 0, 1).astype(np.float64))[:, 0] <= 35
        r_t[ry[dark], rx[dark]] = False
        if e_t.sum() < 200 or r_t.sum() < 200:
            gains.append(None)
            continue
        cr = px[r_t, :3]
        ce = px[e_t, :3]
        lr = to_linear(cr.astype(np.float64))
        le = to_linear(ce.astype(np.float64))
        yr, ye = lr @ np.array([0.2126, 0.7152, 0.0722]), le @ np.array([0.2126, 0.7152, 0.0722])
        sr = lr[(yr > np.percentile(yr, 30)) & (yr < np.percentile(yr, 85))]   # skin, not stubble or hair
        g = np.clip(np.median(sr, 0) / np.maximum(np.median(le[ye > np.percentile(ye, 30)], 0), 1e-4), 0.7, 1.2)
        wt = m[..., 0]
        ys, xs = np.nonzero(wt > 0.01)
        c = to_linear(px[ys, xs, :3].astype(np.float64))
        px[ys, xs, :3] = to_srgb(c * (1.0 + wt[ys, xs, None] * (g - 1.0)))
        gains.append(np.round(g, 2).tolist())
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = maps["color"]
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    log(f"ears: their skin toned to the cheek in front of them (gain right {gains[0]}, left {gains[1]})")


def paint_portrait(basemesh, head_faces, face_hold, portrait, cid, work, root, skip=()):
    """Project the sharp studio portrait onto the head texture (tools/py/portrait_project.py); `skip`: landmarks left
    out of its warp."""
    me = basemesh.data
    V = world_verts(basemesh)
    me.calc_loop_triangles()
    tri_v = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tri_v)
    tri_l = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("loops", tri_l)
    tri_p = np.empty(len(me.loop_triangles), np.int64)
    me.loop_triangles.foreach_get("polygon_index", tri_p)
    tri_v, tri_l = tri_v.reshape(-1, 3), tri_l.reshape(-1, 3)
    sel = head_faces[tri_p]
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    N = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("normal", N)
    N = N.reshape(-1, 3) @ np.array(basemesh.matrix_world)[:3, :3].T
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    A = anchor_points(basemesh, root)
    AK = [k for k in sorted(A) if k not in set(skip)]
    npz = os.path.join(work, "portrait_mesh.npz")
    np.savez(npz, V=V, T=tri_v[sel], UV=uv[tri_l[sel]], N=N, W=face_hold, AK=np.array(AK), AP=np.array([A[k] for k in AK]))
    lm_path = portrait + ".lm.json"
    if not os.path.exists(lm_path):
        subprocess.run([PY, os.path.join(root, "tools", "py", "landmarks.py"), portrait], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    maps = json.loads(basemesh["scan_head_maps"])
    base = maps["color"].replace(".png", "_base.png")
    shutil.copyfile(maps["color"], base)        # the unpainted head, to re-run the projection on its own
    job = {"mesh": npz, "portrait": portrait, "landmarks": lm_path, "texture": base, "out": maps["color"]}
    job_path = os.path.join(work, "portrait_job.json")
    json.dump(job, open(job_path, "w"))
    r = subprocess.run([PY, os.path.join(root, "tools", "py", "portrait_project.py"), job_path], capture_output=True, text=True)
    for line in (r.stdout + r.stderr).strip().splitlines()[-4:]:
        log(line)
    if r.returncode != 0:
        raise RuntimeError("portrait_project failed:\n" + r.stderr[-2000:])


def body_copy_scan(scan):
    """A copy of the (normalised) body scan before a head scan is spliced into it: body_classes wraps the body onto it
    as a build without the head scan does."""
    me = scan.data.copy()
    obj = bpy.data.objects.new("scan_body_only", me)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = scan.matrix_world.copy()
    obj.hide_render = True
    return obj


def absent_fit(basemesh, rig, body0, lms0, root, w_aff, in_body, mouth, fit, mouth_fit=None):
    """Head scans: the template's face fitted as a build without the head scan fits it (fit_face, project_face onto the
    body scan, the portrait's shape with its outline), on a copy of the template (rig's other meshes put back after),
    for body_classes. Returns (the copy, its face_hold)."""
    tpl = basemesh.copy()
    tpl.data = basemesh.data.copy()
    tpl.name = "template_without_head_scan"
    bpy.context.scene.collection.objects.link(tpl)
    mw = basemesh.matrix_world.copy()
    tpl.parent = None
    tpl.matrix_world = mw
    tpl.hide_render = True
    # (fit_face and shape_from_portrait move every other mesh of the rig with the face: the eyes, teeth, lashes and the
    # character's own body too, which is put back with them)
    kids = {}
    for o in rig.children:
        if o.type == 'MESH':
            co = np.empty(len(o.data.vertices) * 3, np.float32)
            o.data.vertices.foreach_get("co", co)
            kids[o.name] = co
    QUIET[0] += 1
    try:
        fh = fit_face(tpl, rig, lms0, root, w_aff, planar=False)
        fh[~in_body] = 0.0
        project_face(tpl, body0, lms0, fh, in_body, mouth > 0)
        if fit.get("face"):
            shape_from_portrait(tpl, rig, fh, os.path.join(root, "tools", "scans", fit["face"]), root, outline=True)
        if mouth_fit is not None:
            # (and the mouth's inside as that build moves it: without, the template's head differed from that build's
            # inside the mouth, the stance and the skinning read it, and the body wrapped onto the body scan came out up
            # to 23 mm off that build's in the crotch and the armpits)
            V0_, inside_, inside_faces_, head_faces_ = mouth_fit
            follow_mouth(tpl, V0_, inside_, inside_faces_, head_faces_, in_body, root)
            tuck_mouth(tpl, inside_, inside_faces_, head_faces_, in_body)
    finally:
        QUIET[0] -= 1
        for o in rig.children:
            if o.name in kids:
                o.data.vertices.foreach_set("co", kids[o.name])
                o.data.update()
    return tpl, fh


def body_classes(body0, tpl0, rig, names, W, in_body, lms0, long_hair, root):
    """Head scans: the body as a build without the head scan wraps it: the template fitted that way (absent_fit, tpl0)
    wrapped onto the body scan as it was before the head scan went in (body0, fitted and re-posed as without one).
    Returns per vertex: P (the wrapped places, where absent_bake bakes the body scan), moved, keep, face_hold, for
    classify and the bake's mask as without the head scan."""
    tpl, fh0 = tpl0
    QUIET[0] += 1
    try:
        ear0 = ear_mask(tpl, root, W, names, in_body)
        hair0 = segment_hair(body0, tpl, rig, names, W, in_body, lms0, long_hair)
        V = world_verts(tpl)
        P0, keep0 = wrap(tpl, rig, body0, names, W, in_body, fh0, ear0, exclude=hair0)
    finally:
        QUIET[0] -= 1
    return dict(P=P0, moved=np.linalg.norm(P0 - V, axis=1), keep=keep0, face_hold=fh0)


def absent_bake(basemesh, body0, body, in_body, head_faces, W, names, work):
    """Head scans: the body scan without the head scan (body0) baked into this body's UVs at the places a build
    without the head scan wraps the body to (body_classes), as that build bakes them (bake_*_abs*.png; composed by
    compose(absent=True)). Away from the head and down the back of the neck the body keeps that build's maps
    (absent_maps), and classify reads its colour."""
    me = basemesh.data.copy()
    tmp = bpy.data.objects.new("scan_abs_target", me)
    bpy.context.scene.collection.objects.link(tmp)
    tmp.matrix_world = basemesh.matrix_world.copy()
    set_world_verts(tmp, body["P"], in_body)
    on_head0 = in_body & (W[:, names.index("head")] > 0.5)
    hidden = body0.hide_render
    body0.hide_render = False

    def cover(path):
        im = bpy.data.images.load(path, check_existing=False)
        px = np.empty(im.size[0] * im.size[1] * 4, np.float32)
        im.pixels.foreach_get(px)
        bpy.data.images.remove(im)
        return float(px[3::4].mean())
    try:
        # (once more if its colour bake's hit mask comes out covering far more than this build's own: the bake
        # occasionally sets the alpha nearly everywhere, and scan_compose then fills no missed texel)
        for attempt in range(2):
            bake_maps(tmp, body0, in_body, body["keep"], body["face_hold"], on_head0, work, head_faces=head_faces,
                      tag="_abs")
            a_abs, a_own = cover(os.path.join(work, "bake_color_abs.png")), cover(os.path.join(work, "bake_color.png"))
            if abs(a_abs - a_own) < 0.05:
                break
            log(f"bakes: the body scan without the head scan baked again (its hit mask covered {a_abs:.2f} of the map, "
                f"this build's {a_own:.2f})")
    finally:
        body0.hide_render = hidden
        bpy.data.objects.remove(tmp)
        bpy.data.meshes.remove(me)
    log("bakes: the body scan without the head scan baked at the body's places without it (for the body away from "
        "the head, the nape and classify)")


def classify(basemesh, names, W, face_hold, keep, color_img, moved):
    """Skin or cloth per face: the hands and the whole head (stubble included; the scalp is under the hair
    shell) are skin. On the neck, skin is what stayed on the body's own neck or has the face's skin colour;
    what moved out onto the hood is cloth, like everything else. With a head scan apply() passes the inputs of a build
    without it (body_classes' move, keep and face_hold, and absent_bake's composed colour), so the body's faces keep
    that build's skin and cloth (read from this build's own inputs, the head scan's pulled-in, darkened hood and its
    nape would change the class of some faces)."""
    me = basemesh.data
    w, h = color_img.size
    px = np.empty(w * h * 4, np.float32)
    color_img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[..., :3]
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    vuv = np.zeros((len(me.vertices), 2), np.float32)
    vuv[lv] = uv
    xi = np.clip((vuv[:, 0] % 1.0) * w, 0, w - 1).astype(int)
    yi = np.clip((vuv[:, 1] % 1.0) * h, 0, h - 1).astype(int)
    col = px[yi, xi]
    lum = col @ np.array([0.2126, 0.7152, 0.0722])
    chroma = col / np.maximum(col.sum(1, keepdims=True), 1e-4)
    ref = face_hold > 0.9
    band = ref & (lum > np.percentile(lum[ref], 30)) & (lum < np.percentile(lum[ref], 85))
    ref_c, ref_l = np.median(chroma[band], 0), np.median(lum[band])
    skinlike = (np.abs(chroma[:, 0] - ref_c[0]) < 0.05) & (np.abs(chroma[:, 1] - ref_c[1]) < 0.035) & \
               (lum > 0.5 * ref_l) & (lum < 1.7 * ref_l)
    col_i = {n: k for k, n in enumerate(names)}
    head = W[:, col_i["head"]] > 0.5
    neck = W[:, col_i["head"]] + W[:, col_i["neck_01"]] > 0.3
    skin = (keep > 0.5) | (face_hold > 0.5) | head | (neck & (skinlike | (moved < 0.012)))
    fk = np.zeros(len(me.polygons), np.int32)
    for p in me.polygons:
        fk[p.index] = 0 if skin[list(p.vertices)].mean() > 0.5 else 1
    attr = me.attributes.new("scan_cloth", 'INT', 'FACE')
    attr.data.foreach_set("value", fk)
    return int(fk.sum()), int((fk == 0).sum()), (ref_c, float(ref_l), int(band.sum()))


def bake_hair(obj, scan, work, size=2048, full=False):
    """Colour and normal of the scan, baked onto the hair shell's own UVs (same surface: tiny cage). full: the scan is
    bake_source's, its head the full head scan, whose locks stand up to a centimetre off the decimated surface the
    shell was cut from: what the tiny cage misses is baked again from 2 cm out."""
    mat = bpy.data.materials.new("hair_bake")
    mat.use_nodes = True
    tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    maps = {}
    for name, kind, src in (("color", 'EMIT', "color"), ("normal", 'NORMAL', "bsdf")):
        for m in scan.data.materials:
            if m is not None:
                emit_from(m, src)
        bpy.ops.object.select_all(action='DESELECT')
        scan.select_set(True)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        if full:
            px = bake_images(obj, tex, name, kind, "color" if name == "color" else "data",
                             ((0.003, 0.012, 0), (0.02, 0.05, 8)), size)
            img = bpy.data.images.new(f"{obj.name}_{name}", size, size, alpha=False, float_buffer=False)
            img.colorspace_settings.name = 'sRGB' if name == "color" else 'Non-Color'
            img.pixels.foreach_set(px.ravel())
        else:
            img = bpy.data.images.new(f"{obj.name}_{name}", size, size, alpha=False, float_buffer=False)
            img.colorspace_settings.name = 'sRGB' if name == "color" else 'Non-Color'
            tex.image = img
            mat.node_tree.nodes.active = tex
            bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=0.003, max_ray_distance=0.012,
                                margin=8, use_clear=True)
        path = os.path.join(work, f"hair_{name}.png")
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
        bpy.data.images.remove(img)
        maps[name] = bpy.data.images.load(path, check_existing=False)
        maps[name].colorspace_settings.name = 'sRGB' if name == "color" else 'Non-Color'
    for m in scan.data.materials:
        emit_from(m, "bsdf")
    obj.data.materials.clear()
    bpy.data.materials.remove(mat)
    return maps


def hair_tex_flow(shell, maps, basemesh, rig, in_body, spec, outfit, root, length=56, blur=24.0):
    """Head scans: the hair shell's baked colour (hair_scan_cards reads its strand direction for the cards, its light and
    dark for the underlayer, its colours for the scalp's hair mask) given strands along the style's own flow. Tripo's
    curly texture has no flow to read (median coherence 0.24, vertex agreement 0.17 against 0.82 / 0.72 on a body
    scan's hair) and the full-resolution bake added bright shards to it (290 blobs over three times the median): under
    a key light the underlayer showed them as grey patches between the cards. Bright outliers (over 1.5 times the
    local mean) go to the local mean, the result is blurred over `blur` texels (the curls' broad light and dark stay;
    the baked highlights capped at 1.8 times the median) and modulated 0.35-1.65 by a line integral convolution of a
    noise along hair_scan_cards' style field (Flow.style: curly, from in front of the forehead up, back and down), so the
    cards' flow is the style field's (blurred over 16 texels and modulated 0.45-1.55: coherence 0.58, agreement 0.41).
    The bake's margin round the shell's island (read by the cards at 1024 px, where it bleeds into the rim) takes the
    redrawn texels' colour: left as baked, it kept the brightest shards (18 blobs over five times the median, all along
    the shell's rim)."""
    import hair_scan_cards as hsc
    img = maps["color"]
    size = img.size[0]
    px = np.empty(size * size * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(size, size, 4)
    me = shell.data
    me.calc_loop_triangles()
    tv = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tv)
    tl = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("loops", tl)
    tv, tl = tv.reshape(-1, 3), tl.reshape(-1, 3)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    UVp = uv.reshape(-1, 2)[tl] * size
    SV = world_verts(shell)
    # the style's flow at the shell's vertices (the frame as hair_scan_cards.gather makes it)
    A = anchor_points(basemesh, root)
    V = world_verts(basemesh)
    G = {"eye_c": np.mean([A[i] for i in (33, 133, 362, 263)], 0),
         "eye_front": float(min(A[i][1] for i in (159, 145, 386, 374))) - 0.0015,
         "brow_z": float(np.mean([A[i][2] for i in BROWS if i in A])), "ears": np.array([A[234], A[454]]),
         "top": float(max(V[in_body, 2].max(), SV[:, 2].max()))}
    if all(i in A for i in hsc.LIDS):
        G["eye_lids"] = np.array([A[i] for i in hsc.LIDS])
    flow = hsc.Flow(hsc.style_for(spec, outfit), hsc.frame_of(G))
    F = np.array([hsc.unit(flow.style(p)) for p in SV])
    ys, xs, tt, bb, _ = uv_texels(UVp, size, size)
    Pm = np.zeros((size, size, 3), np.float32)
    Fm = np.zeros((size, size, 3), np.float32)
    valid = np.zeros((size, size), bool)
    Pm[ys, xs] = (bb[..., None] * SV[tv[tt]]).sum(1)
    Fm[ys, xs] = (bb[..., None] * F[tv[tt]]).sum(1)
    valid[ys, xs] = True
    col = px[..., :3].copy()
    lum = col @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    vf = valid.astype(np.float32)
    shards = 0
    for _ in range(2):
        mean = gauss_blur(lum * vf, 6.0) / np.maximum(gauss_blur(vf, 6.0), 1e-4)
        mcol = gauss_blur(col * vf[..., None], 6.0) / np.maximum(gauss_blur(vf, 6.0), 1e-4)[..., None]
        bright = valid & (lum > 1.5 * mean + 0.004)
        shards += int(bright.sum())
        col[bright] = mcol[bright]
        lum = col @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    low = gauss_blur(col * vf[..., None], blur) / np.maximum(gauss_blur(vf, blur), 1e-4)[..., None]
    # (the scan's baked highlights on the curls, wider than the shards, capped at 1.8 times the median)
    ll = low @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    cap = 1.8 * float(np.median(ll[valid]))
    low *= np.minimum(1.0, cap / np.maximum(ll, 1e-6))[..., None]
    dxm, dym = texture_dirs(Pm, valid, Fm)
    ok = valid & (dxm ** 2 + dym ** 2 > 0.5)
    # (the noise 3 texels coarse: hair_scan_cards reads the texture at 1024. Over the tone blurred 16 texels the strands
    # carry the texture's structure: coherence 0.62, agreement 0.43 offline, against 0.46 / 0.32 over a 3-texel blur)
    u = lic(dxm, dym, ok, length, seed=41, cell=3)
    mod = 0.35 + 1.3 * u
    new = np.where(valid[..., None], np.clip(low * mod[..., None], 0, 1), px[..., :3])
    # the margin: the redrawn colour spread out of the island (normalised blurs, finer first)
    out_ = ~valid
    for sg in (3.0, 8.0, 24.0):
        den = gauss_blur(vf, sg)
        fillc = gauss_blur(new * vf[..., None], sg) / np.maximum(den, 1e-6)[..., None]
        take = out_ & (den > 1e-3)
        new[take] = fillc[take]
        out_ &= ~take
    px[..., :3] = new
    img.pixels.foreach_set(px.ravel())
    img.save()
    log(f"hair shell texture: {shards} bright shard texels to the local mean, strands along the style's flow "
        f"({int(ok.sum())} texels)")


def apply(basemesh, rig, spec, outfit, cid, root):
    scan_path = os.path.join(root, "tools", "scans", spec["outfits"][outfit]["scan"])
    work = os.path.join(root, "tools", "out", f"scan_{cid}")
    os.makedirs(work, exist_ok=True)
    scan = load_scan(scan_path)
    log(cid, "scan", os.path.relpath(scan_path, root), len(scan.data.vertices), "verts")
    lms = normalise_scan(scan, basemesh, root, work)
    body0, lms0 = None, None
    if spec["outfits"][outfit].get("head_scan"):
        body0, lms0 = body_copy_scan(scan), dict(lms)
        lms = splice_head(scan, basemesh, lms, os.path.join(root, "tools", "scans", spec["outfits"][outfit]["head_scan"]),
                          root, work)

    names = [b.name for b in rig.data.bones if b.use_deform and b.name in basemesh.vertex_groups]
    W = deform_weights(basemesh, names)
    body = basemesh.vertex_groups["body"].index
    in_body = np.zeros(len(basemesh.data.vertices), bool)
    for v in basemesh.data.vertices:
        in_body[v.index] = any(g.group == body and g.weight > 0.5 for g in v.groups)
    fit = spec["outfits"][outfit]
    if fit.get("head_scan"):
        lms = fit_scan_head(scan, basemesh, lms, root, similarity=fit.get("head_scan_fit", "similarity") == "similarity")
        QUIET[0] += 1
        lms0 = fit_scan_head(body0, basemesh, lms0, root)       # (as without the head scan: body_classes)
        QUIET[0] -= 1
    else:
        lms = fit_scan_head(scan, basemesh, lms, root)
    w_aff = np.clip(W[:, names.index("head")] + 0.5 * W[:, names.index("neck_01")], 0, 1)
    head_faces = poly_mean(basemesh.data, W[:, names.index("head")]) > 0.5
    inside, inside_faces = mouth_inside(basemesh, in_body, head_faces, root)
    log("lips apart (mm), template:", lip_gaps(basemesh, root))
    mouth = np.zeros(len(inside))     # every vertex of the inside's faces, seam included
    for poly in np.nonzero(inside_faces)[0]:
        mouth[list(basemesh.data.polygons[poly].vertices)] = 1.0
    V0 = world_verts(basemesh)        # the template, before the face fits (follow_mouth, follow_eyes)
    E0 = {o.name: world_verts(o) for o in eye_objects(rig, basemesh)}
    L0 = {o.name: world_verts(o) for o in rig.children if o.type == 'MESH' and o != basemesh and "lash" in o.name.lower()}
    lip_in = inner_lips(basemesh, V0, in_body, inside, root)
    tpl0 = absent_fit(basemesh, rig, body0, lms0, root, w_aff, in_body, mouth, fit,
                      mouth_fit=(V0, inside, inside_faces, head_faces)) if body0 is not None else None
    face_hold = fit_face(basemesh, rig, lms, root, w_aff, planar=bool(fit.get("head_scan")))
    face_hold[~in_body] = 0.0
    if fit.get("head_scan"):
        fit_head(basemesh, scan, lms, face_hold, in_body, W, names, ear_mask(basemesh, root, W, names, in_body), rig,
                 mouth > 0)
        flatten_ears(basemesh, scan, in_body, share=0.45)
        tuck_skull(basemesh, scan, in_body, W, names, face_hold, root=root, crown=fit.get("skull_crown"))
    else:
        project_face(basemesh, scan, lms, face_hold, in_body, mouth > 0)
    if fit.get("face"):
        shape_from_portrait(basemesh, rig, face_hold, os.path.join(root, "tools", "scans", fit["face"]), root,
                            outline=not fit.get("head_scan"))
    if fit.get("head_scan"):
        widen_jaw(basemesh, rig, in_body, W, names, root, float(fit.get("head_scan_jaw", 0.0)))
        narrow_mouth(basemesh, in_body, root)
    if fit.get("head_scan"):
        # (not the lips: their inner sides face each other and stand turned from the template's by the fits)
        unfold(basemesh, V0, in_body, in_body & (W[:, names.index("head")] > 0.3) & ~inside
               & (nearest_landmark(world_verts(basemesh), np.array([lms[i] for i in LIPS if i in lms])) > 0.006))
    follow_mouth(basemesh, V0, inside, inside_faces, head_faces, in_body, root)
    tuck_mouth(basemesh, inside, inside_faces, head_faces, in_body)
    follow_eyes(basemesh, rig, V0, E0, in_body, head_faces, root)
    if fit.get("head_scan"):
        open_canthus(basemesh, rig, in_body, W, names, root)
        # (and what the turn folded at the outer corners relaxed, as after the face fits: 3 and 2 triangles turned over;
        # a few rounds only, kept only if it unfolds them: relaxed for 30 rounds round a fold it could not undo, the
        # right corner went 2.2 mm back towards the template's, half the turn)
        Ac = anchor_points(basemesh, root)
        cn = np.array([Ac[i] for i in (33, 263) if i in Ac])
        if len(cn):
            Vc = world_verts(basemesh)
            selc = in_body & (W[:, names.index("head")] > 0.3) & (nearest_landmark(Vc, cn) < 0.02)
            Tc = triangles(basemesh.data)
            Tc = Tc[selc[Tc].all(1)]

            def n_folds(P):
                f0 = np.cross(V0[Tc[:, 1]] - V0[Tc[:, 0]], V0[Tc[:, 2]] - V0[Tc[:, 0]])
                f1 = np.cross(P[Tc[:, 1]] - P[Tc[:, 0]], P[Tc[:, 2]] - P[Tc[:, 0]])
                a0, a1 = np.linalg.norm(f0, axis=1), np.linalg.norm(f1, axis=1)
                cos = (f0 * f1).sum(1) / np.maximum(a0 * a1, 1e-20)
                return int(((cos < 0.2) | (a1 < 0.1 * a0)).sum())
            before = n_folds(Vc)
            if before:
                unfold(basemesh, V0, in_body, selc, rounds=4)
                after = n_folds(world_verts(basemesh))
                if after >= before:
                    set_world_verts(basemesh, Vc, in_body)
                log(f"eyes: {before} triangles folded at the outer corners by the turn -> "
                    f"{after if after < before else before}{' (relaxing them left them folded: undone)' if after >= before else ''}")
        seat_lashes(rig, basemesh, V0, L0, in_body)
        settle_lashes(basemesh, rig, in_body, W, names, root, V0=V0, L0=L0, E0=E0)
        lay_lashes(basemesh, rig, in_body, V0, L0)
    log("lips apart (mm), fitted:", lip_gaps(basemesh, root))
    ear = ear_mask(basemesh, root, W, names, in_body)
    ear0 = ear.copy()
    if fit.get("head_scan"):
        # the template's own skin on the ears themselves only: the mask's soft ball round each ear left a pale halo on
        # the sideburn and behind the ear, round a scan whose ears and skin match its face
        eg = ear_group(basemesh, in_body)
        if eg.any():
            Ve = world_verts(basemesh)
            ear = ear * (1.0 - smoothstep(0.001, 0.004, nearest_landmark(Ve, Ve[eg])))
            # (not the skin under and in front of each lobe: kept, the template's pale skin there was a second earlobe
            # and a pale strip by the tragus; clean_lobes repaints it from the cheek after the bakes)

    V = world_verts(basemesh)
    match_stance(rig, world_verts(scan), V, W, names)
    repose_scan(scan, rig, names, W, V, in_body)
    if body0 is not None:
        # (as a build without the head scan re-poses it: its stance from the body scan alone and the template as that
        # build fits it (absent_fit; the stance and the skinning read the template's head and neck). Re-posed in this
        # build's stance and with its head-scan-fitted template, the body scan comes out a few mm to 3 cm off in the
        # armpits and the crotch, and so do the maps absent_bake makes of it)
        Vt = world_verts(tpl0[0])
        QUIET[0] += 1
        match_stance(rig, world_verts(body0), Vt, W, names)
        repose_scan(body0, rig, names, W, Vt, in_body)
        QUIET[0] -= 1
    hair = segment_hair(scan, basemesh, rig, names, W, in_body, lms, bool(fit.get("hair_long"))) \
        if fit.get("hair") in ("scan", "scan_cards") else None
    P, keep = wrap(basemesh, rig, scan, names, W, in_body, face_hold, ear, exclude=hair)
    body = body_classes(body0, tpl0, rig, names, W, in_body, lms0, bool(fit.get("hair_long")), root) \
        if body0 is not None else None
    if body is not None:
        np.save(os.path.join(work, "abs_P.npy"), body["P"])
    # the mouth's inside keeps the template's own colour (the scan has none); 0.75 keeps it fully but leaves it
    # out of the hands' and ears' tone match (scan_compose samples the kept skin at R > 0.8)
    keep = np.maximum(keep, 0.75 * np.maximum(mouth, lip_in))
    if body is not None:
        body["keep"] = np.maximum(body["keep"], 0.75 * np.maximum(mouth, lip_in))
    # and it darkens with depth behind the lips: no light gets far into a mouth (the inner lips a little: the
    # lip line reads as a soft dark line)
    Vm = world_verts(basemesh)
    lips = (anchor_points(basemesh, root)[13] + anchor_points(basemesh, root)[14]) / 2
    cavity = np.maximum(mouth * smoothstep(0.004, 0.03, Vm[:, 1] - lips[1]), 0.35 * lip_in)
    nostrils, nost_occ = nostril_cavity(basemesh, in_body, root, occlusion=True) if fit.get("head_scan") else \
        (np.zeros(len(Vm)), np.zeros(len(Vm)))
    cavity = np.maximum(cavity, (0.6 if fit.get("head_scan") else 0.9) * nostrils)
    set_world_verts(basemesh, P, in_body)
    if fit.get("head_scan") and hair is not None and hair.any():
        hair = fit_hair(scan, hair, basemesh, rig, in_body, W, names, root)
        hair = clear_ears(scan, hair, basemesh, in_body)
    env = hair_env_inputs(basemesh, rig, in_body, W, names, root) if fit.get("head_scan") else None
    shell = hair_shell(scan, hair, cid, env=env) if hair is not None and hair.any() else None
    # the head's own 4K texture (see repack_head_uvs)
    uvsrc = uv_source(basemesh, in_body)
    repack_head_uvs(basemesh, head_faces)
    src = bake_source(scan, basemesh, in_body)
    on_head = in_body & (W[:, names.index("head")] > 0.5)
    if fit.get("head_scan"):
        # every vertex of the head texture's faces counts as the head (keeps its own normals, scan_compose): its faces
        # on the neck with a vertex under the head bone's half weight kept the head scan's normals there, a hard-edged
        # bright wedge under a key light where the slimmer scanned neck turns from the template's
        hv = np.zeros(len(on_head), bool)
        for poly in np.nonzero(head_faces)[0]:
            hv[list(basemesh.data.polygons[poly].vertices)] = True
        on_head |= hv & in_body
    bake_maps(basemesh, src, in_body, keep, face_hold, on_head, work,
              head_faces=head_faces, uvsrc=uvsrc, cavity=cavity)
    bpy.data.objects.remove(uvsrc)
    if body is not None:
        absent_bake(basemesh, body0, body, in_body, head_faces, W, names, work)
    if shell is not None:
        maps = bake_hair(shell, src, work, full=src is not scan)
        if fit.get("head_scan"):
            hair_tex_flow(shell, maps, basemesh, rig, in_body, spec, outfit, root)
        # (onto the skull, as without a head scan: feathered onto the neck too, the nape's edge lies on the neck down
        # to 1.5 cm under the head bone, and with the head tilted up the card vertices low on the nape go into it)
        feather_hair(shell, head_surface(basemesh, names, W, in_body), float(bone_head(rig, "head")[2]) - 0.02)
        finish_hair(shell, rig, maps)
    color = compose(basemesh, cid, work, root, head=True, absent=body is not None)
    cloth_abs = None
    if body is not None:
        # (as a build without the head scan classifies: its move, keep, face_hold and composed body colour; before
        # absent_maps, which gives the cloth that build's maps as they are)
        abs_col = load_map(json.loads(basemesh["scan_abs_maps"])["color"], "color")
        cloth, skin, (ref_c, ref_l, n_ref) = classify(basemesh, names, W, body["face_hold"], body["keep"], abs_col,
                                                      body["moved"])
        bpy.data.images.remove(abs_col)
        log(f"classify: as without the head scan (skin reference chroma {[round(float(x), 3) for x in ref_c]}, luminance "
            f"{ref_l:.3f}, {n_ref} texels); {cloth} cloth faces")
        cloth_abs = np.empty(len(basemesh.data.polygons), np.int32)
        basemesh.data.attributes["scan_cloth"].data.foreach_get("value", cloth_abs)
    if fit.get("head_scan"):
        if body is not None:
            absent_maps(basemesh, head_faces, in_body, W, names, root, P_abs=body["P"], cloth=cloth_abs)
        clean_eye_corners(basemesh, head_faces, in_body, root)
        if fit.get("face"):
            soften_scan_skin(basemesh, head_faces, face_hold, in_body, root)
        hc = fit.get("hair_cards") or {}
        basemesh["scan_hair_tones"] = json.dumps([[int(h[k:k + 2], 16) / 255.0 for k in (1, 3, 5)]
                                                  for h in (hc.get("under", "#110e0d"), hc.get("tip", "#241d19"))])
        paint_sideburns(basemesh, head_faces, in_body, root)
        clean_lobes(basemesh, head_faces, in_body, root)
        neck_shading(basemesh, head_faces, in_body, root)
        tone_ears(basemesh, head_faces, in_body, keep)
        shade_ears(basemesh, head_faces, in_body)
    if fit.get("face"):
        # (a nostril's inside only where it is deep: the portrait's own dark nostrils land on the openings)
        paint_portrait(basemesh, head_faces, face_hold * (1.0 - mouth) * (1.0 - lip_in) * (1.0 - nostrils ** 2),
                       os.path.join(root, "tools", "scans", fit["face"]), cid, work, root,
                       skip=deep_eye_anchors(anchor_points(basemesh, root)) if fit.get("head_scan") else ())
    if fit.get("head_scan"):
        # (a gentler ramp from the rim in and a 1 mm blur: at 0.3-0.6 and 0.5 mm they read as punched black slots in
        # three-quarter view, with a hard rim)
        nostril_skin(basemesh, head_faces, in_body, root, work)
        if fit.get("face"):
            blend_portrait_edge(basemesh, head_faces, in_body, root)
        clean_skin_lines(basemesh, head_faces, in_body, root)
        tone_beard(basemesh, head_faces, in_body, root)
        paint_beard(basemesh, head_faces, in_body, root, shape=fit.get("beard_dark"))
        if fit.get("brow_paint"):
            paint_brows(basemesh, head_faces, in_body, root, fit["brow_paint"])
        if fit.get("beard_dark"):
            darken_beard(basemesh, head_faces, in_body, root, fit["beard_dark"])
        if fit.get("side_clear"):
            clear_sides(basemesh, head_faces, in_body, root, fit["side_clear"])
        head_margins(basemesh, head_faces)
    attr = basemesh.data.attributes.new("scan_head", 'INT', 'FACE')
    attr.data.foreach_set("value", head_faces.astype(np.int32))
    if body is None:
        cloth, skin, _ = classify(basemesh, names, W, face_hold, keep, color, np.linalg.norm(P - V, axis=1))
    for o_ in (body0, tpl0[0] if tpl0 else None):
        if o_ is not None:
            me_ = o_.data
            bpy.data.objects.remove(o_)
            bpy.data.meshes.remove(me_)
    for o in ((src,) if src is not scan else ()) + tuple(o for o in (bpy.data.objects.get(scan.get("head_full", "")),) if o):
        me_ = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(me_)
    for m in scan.data.materials:
        if m:
            bpy.data.materials.remove(m)
    bpy.data.objects.remove(scan)
    log(cid, f"wrapped; {cloth} cloth faces, {skin} skin faces")


def scale_shapes(basemesh, rig):
    """The face shapes (ARKit, loaded after the fit) are offsets sized for the template's head: scale them with the
    head's affine, so a blink still closes the fitted eyelids and the mouth opens in proportion."""
    keys = basemesh.data.shape_keys
    L = basemesh.get("scan_head_linear")
    if keys is None or L is None:
        return
    L = np.array(L, np.float64).reshape(3, 3)
    R = np.array(basemesh.matrix_world)[:3, :3]
    Ll = R.T @ L @ np.linalg.inv(R.T)          # the same map for local-space offsets (row vectors)
    names = [b.name for b in rig.data.bones if b.use_deform and b.name in basemesh.vertex_groups]
    W = deform_weights(basemesh, names)
    w = np.clip(W[:, names.index("head")] + 0.5 * W[:, names.index("neck_01")], 0, 1)[:, None]
    n = len(basemesh.data.vertices)
    B = np.empty(n * 3, np.float64)
    keys.reference_key.data.foreach_get("co", B)
    B = B.reshape(-1, 3)
    K = np.empty(n * 3, np.float64)
    scaled = 0
    for kb in keys.key_blocks:
        if kb == keys.reference_key:
            continue
        kb.data.foreach_get("co", K)
        d = K.reshape(-1, 3) - B
        if np.abs(d).max() < 1e-7:
            continue
        kb.data.foreach_set("co", (B + d + w * (d @ Ll - d)).astype(np.float32).ravel())
        scaled += 1
    log(f"scaled {scaled} face shapes with the head fit")


def split_materials(obj, cid):
    """After build_human.finish_meshes: the cloth faces get a copy of the skin material with the scan's
    roughness map, named <id>_cloth_scan so the game shades it as fabric."""
    attr = obj.data.attributes.get("scan_cloth")
    if attr is None:
        log("split_materials: no scan_cloth attribute; attributes:", [a.name for a in obj.data.attributes])
        return
    skin = obj.active_material
    cloth = skin.copy()
    cloth.name = f"{cid}_cloth_scan"
    nt = cloth.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    rough = bpy.data.images.get(obj.get("scan_rough", ""))
    if rough is not None:
        tn = nt.nodes.new('ShaderNodeTexImage')
        tn.image = rough
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(tn.outputs[0], sep.inputs[0])
        nt.links.new(sep.outputs[1], bsdf.inputs["Roughness"])
    obj.data.materials.append(cloth)
    fk = np.empty(len(obj.data.polygons), np.int32)
    attr.data.foreach_get("value", fk)
    hattr = obj.data.attributes.get("scan_head")
    if hattr is not None and obj.get("scan_head_maps"):
        # the head: skin with its own 4K maps
        maps = json.loads(obj["scan_head_maps"])
        head = skin.copy()
        head.name = f"{cid}_skin_head"
        hn = head.node_tree
        for n in hn.nodes:
            if n.type == 'TEX_IMAGE' and n.image:
                is_normal = any(l.to_node.type == 'NORMAL_MAP' for o in n.outputs for l in o.links)
                n.image = load_map(maps["normal"] if is_normal else maps["color"], "data" if is_normal else "color")
        obj.data.materials.append(head)
        hk = np.empty(len(obj.data.polygons), np.int32)
        hattr.data.foreach_get("value", hk)
        fk = np.where(hk == 1, 2, fk).astype(np.int32)
    obj.data.polygons.foreach_set("material_index", fk)
    # by name, one at a time: removing an attribute invalidates Python references to the others (a stale one
    # removed material_index itself)
    for name in ("scan_cloth", "scan_head"):
        if name in obj.data.attributes:
            obj.data.attributes.remove(obj.data.attributes[name])
    obj.data.update()
    log("split_materials:", [m.name for m in obj.data.materials], np.bincount(fk).tolist())
