"""Prototype B: strand cards laid over the scan's hair shell (the shell stays as the hair's volume, shaded dark
and matte, and many short overlapping alpha cards cover it along a flow field; longer cards break the
silhouette at the hairline and the ends).

Blender -b -P tools/blender/proto_hair_B.py -- <stem> [before] [views=front,34,side,back] [res=1100] [seed=1]
                                                [dens=1.0] [tag=] [export=1] [debug=1]
Reads assets/characters/<stem>.glb (never writes it), works in world space on the rest pose:
  1. scalp mask: where the head's baked texture is hair, not skin (Lab distance from the forehead's skin
     colour; no face, no beard, the nape cut for short hair). A cap 1 mm over the head carries it: the hair's
     root colour, its alpha from the mask, so the scan's grey hairline band and the shiny bald dome under the
     shell become dark roots fading into the skin
  2. the shell, Taubin-smoothed (its crumpled clay lumps gone, its volume kept) = the guide the cards follow;
     the same smoothed shell, 1.5 mm further in, darkened and matte = the underlayer seen through the gaps
  3. strand cards grown over shell + bare scalp along the style's flow field, in layers (under / mid / top),
     hairline cards rooted on the mask's iso-line, silhouette cards (curl flicks / flyaways), free-hanging ends
     where a strand runs off the shell (long hair: ragged, tapered)
  4. EEVEE close-ups under neutral studio light: tools/out/review/hair_proto_B_<id><tag>_<view>.png
"before" renders the current game look (the matte shell alone) with the same lights and cameras into
tools/out/proto_B/before_<id>_<view>.png. Atlas: tools/blender/proto_hair_B_atlas.py (tools/out/proto_B/).
"""
import bpy, sys, os, math, time, random
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from mathutils.geometry import barycentric_transform


def _root():
    d = os.path.dirname(os.path.abspath(__file__))
    while d != "/" and not os.path.exists(os.path.join(d, "project.godot")):
        d = os.path.dirname(d)
    return d


ROOT = _root()
OUT = os.path.join(ROOT, "tools", "out", "proto_B")
REVIEW = os.path.join(ROOT, "tools", "out", "review")
BACKDROP = (0.11, 0.12, 0.14)


def srgb(c):
    return tuple(((x / 255.0 + 0.055) / 1.055) ** 2.4 for x in c)


# per glb stem. Lengths in metres. layer = (name, cards per m^2 of base, length range (None: long hair, down to
# the base's lower edge), width range, lift range above the base, tone (AO) range, atlas strips, root fade)
STYLES = {
    "toma_fit1": dict(
        id="toma", kind="curly", atlas="curly", tint=srgb((58, 42, 33)), root=srgb((20, 16, 14)),
        spec1=0.003, spec1_rough=0.34, spec2=srgb((120, 88, 66)), spec2_k=0.07, spec2_rough=0.5, trans=0.25,
        long=False, nape=-0.085, smooth=10,
        # flow: out from a point just in front of and below the forehead hairline (swept up and back over the
        # top, back and down the sides), gravity below the top
        origin=(0.0, -0.012, 0.045), gravity=0.6, seg=0.0065,
        curl=dict(wave=(0.032, 0.044), wiggle=0.2, lift=0.0026, twist=0.32, jitter=0.5),
        free_max=0.014,
        layers=[
            ("under", 4600, (0.05, 0.07), (0.018, 0.026), (0.0004, 0.0014), (0.26, 0.38), (0, 1, 2), 0.25),
            ("mid", 5200, (0.06, 0.085), (0.014, 0.02), (0.0015, 0.004), (0.5, 0.68), (0, 1, 2, 3, 4), 0.25),
            ("top", 3000, (0.06, 0.09), (0.016, 0.024), (0.0032, 0.0065), (0.82, 1.02), (2, 3, 4, 5, 6), 0.3),
        ],
        hairline=dict(step=0.0022, iso=0.18, length=(0.025, 0.05), width=(0.008, 0.013), strips=(2, 3, 4),
                      tone=(0.75, 1.0)),
        brk_pow=2.2, cover=0.006,
        loops=dict(count_per_m2=1100, length=(0.035, 0.06), width=(0.008, 0.013), bulge=(0.006, 0.014),
                   strips=(4, 5, 6)),
        fly=dict(count=150, length=(0.04, 0.08), width=(0.005, 0.009), bulge=(0.004, 0.016)),
    ),
    "anisha": dict(
        id="anisha", kind="long", atlas="straight", tint=srgb((30, 26, 24)), root=srgb((15, 13, 12)),
        spec1=0.0045, spec1_rough=0.25, spec2=srgb((96, 82, 72)), spec2_k=0.05, spec2_rough=0.42, trans=0.2,
        long=True, part=((0.0, -0.075, 0.0), (0.0, 0.035, 0.0)), smooth=30,
        gravity=1.6, seg=0.016, free_max=0.07, max_len=0.75, end_trim=0.07,
        layers=[
            ("under", 1700, None, (0.026, 0.036), (0.0008, 0.0022), (0.36, 0.5), (0, 1), 0.3),
            ("mid", 1900, None, (0.017, 0.025), (0.0026, 0.005), (0.62, 0.8), (0, 1, 2, 3), 0.3),
            ("top", 1500, None, (0.011, 0.017), (0.0045, 0.008), (0.88, 1.02), (2, 3, 4, 5, 6), 0.3),
        ],
        hairline=dict(step=0.004, iso=0.4, length=None, width=(0.007, 0.012), strips=(2, 3, 4, 5),
                      tone=(0.7, 0.9)),
        brk_pow=1.6, cover=0.009,
        fly=dict(count=90, length=(0.08, 0.2), width=(0.005, 0.009), bulge=(0.004, 0.018)),
    ),
}


def log(*a):
    print("[protoB]", *a, flush=True)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ------------------------------------------------------------------ scene
def load(stem):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, "assets", "characters", stem + ".glb"))
    sc = bpy.context.scene
    for o in list(sc.objects):
        if o.name.startswith("Icosphere"):
            o.hide_render = True
            o.hide_viewport = True
    rig = next(o for o in sc.objects if o.type == 'ARMATURE')
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    return rig


def world_tris(obj):
    """Evaluated (skinned, rest pose) mesh in world space: verts, loop triangles, their polygon, per-loop UVs."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    M = np.array(obj.matrix_world)
    V = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    T = np.empty(nt * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", T)
    L = np.empty(nt * 3, np.int32)
    me.loop_triangles.foreach_get("loops", L)
    P = np.empty(nt, np.int32)
    me.loop_triangles.foreach_get("polygon_index", P)
    uv = None
    if me.uv_layers:
        u = np.empty(len(me.loops) * 2, np.float32)
        me.uv_layers.active.data.foreach_get("uv", u)
        uv = u.reshape(-1, 2)[L.reshape(-1, 3)]
    mi = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mi)
    ev.to_mesh_clear()
    return V.astype(np.float64), T.reshape(-1, 3), P, uv, mi


def image_array(img):
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def base_color_image(mat):
    for n in mat.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and n.image.colorspace_settings.name == 'sRGB':
            return n.image
    return None


def vertex_normals(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], fn)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def smooth_normals(V, N, radius):
    kd = KDTree(len(V))
    for i, v in enumerate(V):
        kd.insert(v, i)
    kd.balance()
    out = np.empty_like(N)
    for i, v in enumerate(V):
        acc = np.zeros(3)
        for co, j, d in kd.find_range(v, radius):
            if N[j] @ N[i] > 0.0:
                acc += N[j] * math.exp(-(d / (0.5 * radius)) ** 2)
        out[i] = acc / max(np.linalg.norm(acc), 1e-12)
    return out


# ------------------------------------------------------------------ scalp mask (texture -> hair / skin)
def to_lab(c):
    """sRGB-encoded colours (Image.pixels of a byte image) -> CIE Lab."""
    c = np.clip(c, 0.0, 1.0)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(np.maximum(xyz, 0.0)), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def pool(img, k):
    h, w = img.shape[:2]
    h2, w2 = h // k, w // k
    return img[:h2 * k, :w2 * k].reshape(h2, k, w2, k, -1).mean((1, 3))


def sample_img(img, uv):
    h, w = img.shape[:2]
    x = np.clip((uv[..., 0] % 1.0) * w, 0, w - 1).astype(int)
    y = np.clip((uv[..., 1] % 1.0) * h, 0, h - 1).astype(int)
    return img[y, x]


def hairness(lab, ref):
    """1 = hair (dark or colourless next to the skin), 0 = skin."""
    lr = lab[..., 0] / max(ref[0], 1e-3)
    cr = np.hypot(lab[..., 1], lab[..., 2]) / max(math.hypot(ref[1], ref[2]), 1e-3)
    return np.clip(np.maximum((0.72 - lr) / 0.3, (0.6 - cr) / 0.3), 0.0, 1.0)


def region_weight(P, fr, st):
    """Where hair may grow at all: not the face (brows, lashes), not the beard, not below the nape (short hair)."""
    e, ef = fr["eye"], fr["eye_front"]
    y = P[:, 1] - ef          # behind the front of the eyes
    z = P[:, 2] - e.z         # above the eyes
    front = 1.0 - smoothstep(0.065, 0.085, y)
    brow = smoothstep(0.035, 0.05, z)
    w = 1.0 - front * (1.0 - brow)
    low = 1.0 - smoothstep(-0.03, -0.01, z)
    infront = 1.0 - smoothstep(0.085, 0.1, y)
    w *= 1.0 - low * infront
    if not st["long"]:
        w *= smoothstep(st["nape"] - 0.015, st["nape"], z)
    else:
        # long hair falls over the temples from above: no sideburns of its own
        w *= 1.0 - (1.0 - smoothstep(0.0, 0.02, z)) * infront
    return w


# ------------------------------------------------------------------ hair base
def hair_base(rig, st):
    sc = bpy.context.scene
    body = next(o for o in sc.objects if o.type == 'MESH' and o.name.endswith("_body"))
    shell = next(o for o in sc.objects if o.type == 'MESH' and "hairshell" in o.name)
    eye = next(o for o in sc.objects if o.type == 'MESH' and "_eye_" in o.name)
    Ve, _, _, _, _ = world_tris(eye)
    eye_c = Ve.mean(0)
    eye_front = float(Ve[:, 1].min())
    Vb, Tb, Pb, UVb, MIb = world_tris(body)
    Vs, Ts, _, UVs, _ = world_tris(shell)
    mats = [m for m in body.data.materials]
    head_mi = next(i for i, m in enumerate(mats) if m.name.endswith("_skin_head"))
    tri_mi = MIb[Pb]
    C = Vb[Tb].mean(1)
    fn = np.cross(Vb[Tb[:, 1]] - Vb[Tb[:, 0]], Vb[Tb[:, 2]] - Vb[Tb[:, 0]])
    fn = fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    head = tri_mi == head_mi
    top = float(max(Vb[Tb[head]][:, :, 2].max(), Vs[:, 2].max()))
    hc = Vector((float(eye_c[0]), float(eye_front + 0.085), float(eye_c[2] + 0.02)))
    frame = dict(eye=Vector(eye_c.tolist()), eye_front=eye_front, top=top, centre=hc)
    # -- the scalp mask, from the head's baked texture
    head_img = base_color_image(mats[head_mi])
    tex = image_array(head_img)
    k = max(1, tex.shape[0] // 1024)
    small = pool(tex, k)
    lab_small = to_lab(small[..., :3])
    fore = head & (np.abs(C[:, 0] - eye_c[0]) < 0.025) & (C[:, 2] > eye_c[2] + 0.02) & \
        (C[:, 2] < eye_c[2] + 0.045) & (C[:, 1] < eye_front + 0.03)
    ref = sample_img(lab_small, UVb[fore].reshape(-1, 2)).mean(0)
    hair_tex = hairness(lab_small, ref)
    hh = np.zeros(len(Vb))
    hn = np.zeros(len(Vb))
    np.add.at(hh, Tb[head].ravel(), sample_img(hair_tex, UVb[head].reshape(-1, 2)))
    np.add.at(hn, Tb[head].ravel(), 1.0)
    vh = hh / np.maximum(hn, 1)
    reg = region_weight(Vb, frame, st)
    vhr = vh * reg
    log(f"skin ref Lab {np.round(ref, 1).tolist()}, scalp verts {(vhr > 0.5).sum()}")
    cand = head & (C[:, 2] > eye_c[2] - 0.13)
    cap = cand & (vhr[Tb].max(1) > 0.03)
    # covered by the shell along the normal (the shell and its cards lie over it)
    sbvh = BVHTree.FromPolygons(Vs.tolist(), Ts.tolist(), all_triangles=True)
    covered = np.zeros(len(Tb), bool)
    for i in np.nonzero(cap)[0]:
        hit = sbvh.ray_cast(Vector(C[i] + fn[i] * 0.0008), Vector(fn[i]), 0.09)
        covered[i] = hit[0] is not None
    Nb = vertex_normals(Vb, Tb)
    # the cap (all of the mask: under the shell too, where the shell's smoothing may sink below it)
    Tc = Tb[cap]
    used = np.unique(Tc)
    remap = -np.ones(len(Vb), np.int64)
    remap[used] = np.arange(len(used))
    Vc = Vb[used] + Nb[used] * 0.001
    cap_uv = UVb[cap]
    cap_w = reg[used]
    Tc = remap[Tc]
    # the bare scalp the cards grow over: mask > 0.3 at all three corners, not under the shell
    bare = cap & ~covered & (vhr[Tb].min(1) > 0.3)
    guide = bare.copy()
    n_cape = 0
    cloth_mi = next((i for i, m in enumerate(mats) if m.name.endswith("_cloth_scan")), -1)
    if st["long"] and cloth_mi >= 0 and base_color_image(mats[cloth_mi]) is not None:
        # long hair below the shoulders is part of the body ("cape", cloth material, hair-dark): the cards
        # carry on over it
        cimg = image_array(base_color_image(mats[cloth_mi]))
        sel = np.nonzero((tri_mi == cloth_mi) & (fn[:, 1] > 0.15) & (C[:, 2] > eye_c[2] - 0.62))[0]
        lum = sample_img(cimg, UVb[sel].mean(1))[:, :3] @ np.array([0.2126, 0.7152, 0.0722])
        for i in sel[lum < 0.2]:
            hit = sbvh.ray_cast(Vector(C[i] + fn[i] * 0.0008), Vector(fn[i]), 0.09)
            if hit[0] is None:
                guide[i] = True
                n_cape += 1
    used2 = np.unique(Tb[guide])
    remap2 = -np.ones(len(Vb), np.int64)
    remap2[used2] = np.arange(len(used2))
    Vg = Vb[used2] + Nb[used2] * 0.0012
    Tg = remap2[Tb[guide]]
    # hairline: where the mask crosses iso on the cap's edges (not under the shell)
    iso = st["hairline"]["iso"]
    hl = []
    for tri in Tb[cap & ~covered]:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            ha, hb_ = vhr[a], vhr[b]
            if (ha - iso) * (hb_ - iso) < 0:
                t = (iso - ha) / (hb_ - ha)
                hl.append((Vb[a] + (Vb[b] - Vb[a]) * t + (Nb[a] + Nb[b]) * 0.0005))
    hl = np.unique(np.round(np.array(hl), 6), axis=0) if hl else np.zeros((0, 3))
    log(f"base: shell {len(Ts)} tris; cap {int(cap.sum())} tris ({int((cap & covered).sum())} under the shell), "
        f"bare scalp {int(bare.sum())} tris, cape {n_cape} tris, hairline points {len(hl)}")
    body_bvh = BVHTree.FromPolygons(Vb.tolist(), Tb.tolist(), all_triangles=True)
    return dict(frame=frame, body=body, shell=shell, body_bvh=body_bvh, shell_part=(Vs, Ts, UVs),
                cap_part=(Vc, Tc, cap_uv, cap_w, head_img, hair_tex), guide_cap=(Vg, Tg), hairline=hl,
                head_tex=tex)


def make_mesh(name, V, T, UV=None, mats=(), mat_index=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(V.tolist(), [], T.tolist())
    me.update()
    if UV is not None:
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", np.asarray(UV, np.float32).reshape(-1, 2).ravel())
    for m in mats:
        me.materials.append(m)
    if mat_index is not None:
        me.polygons.foreach_set("material_index", np.asarray(mat_index, np.int32))
    for p in me.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


# ------------------------------------------------------------------ the surface the cards follow
def weld_map(V, T):
    """glTF splits vertices along UV seams: merge them back (exact duplicates). Returns welded V, T and the map
    from the original vertices to the welded ones."""
    key = np.round(V * 1e5).astype(np.int64)
    _, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    return V[idx], inv[T], inv


def weld(V, T):
    Vw, Tw, _ = weld_map(V, T)
    return Vw, Tw


def taubin(V, T, iters, lam=0.5, mu=-0.53):
    """Volume-keeping smoothing (Taubin lambda/mu). Boundary vertices only move along the boundary curve."""
    if iters <= 0:
        return V.copy()
    e = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1)
    u, c = np.unique(e, axis=0, return_counts=True)
    is_b = c == 1
    on_b = np.zeros(len(V), bool)
    on_b[u[is_b].ravel()] = True
    a, b = u[:, 0], u[:, 1]
    # interior vertices average all their neighbours, boundary vertices only their boundary neighbours
    ia = ~on_b[a] | is_b
    ib = ~on_b[b] | is_b
    deg = np.zeros(len(V))
    np.add.at(deg, a[ia], 1.0)
    np.add.at(deg, b[ib], 1.0)
    ok = deg > 0
    V = V.copy()
    for _ in range(iters):
        for f in (lam, mu):
            acc = np.zeros_like(V)
            np.add.at(acc, a[ia], V[b[ia]])
            np.add.at(acc, b[ib], V[a[ib]])
            Lp = np.zeros_like(V)
            Lp[ok] = acc[ok] / deg[ok, None] - V[ok]
            V = V + f * Lp
    return V


class Surface:
    def __init__(self, V, T, welded=False):
        if not welded:
            V, T = weld(V, T)
        self.V, self.T = V, T
        self.N = smooth_normals(V, vertex_normals(V, T), 0.012)
        self.bvh = BVHTree.FromPolygons(V.tolist(), T.tolist(), all_triangles=True)
        self.Vv = [Vector(v) for v in V]
        e = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1)
        u, c = np.unique(e, axis=0, return_counts=True)
        self.boundary_edges = u[c == 1]
        a = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        self.area = 0.5 * np.linalg.norm(a, axis=1)

    def nearest(self, p):
        loc, _, ti, d = self.bvh.find_nearest(p, 0.2)
        if loc is None:
            return None, None, 1e9
        a, b, c = self.T[ti]
        w = barycentric_transform(loc, self.Vv[a], self.Vv[b], self.Vv[c], Vector((1, 0, 0)), Vector((0, 1, 0)),
                                  Vector((0, 0, 1)))
        n = Vector(self.N[a] * w.x + self.N[b] * w.y + self.N[c] * w.z)
        if n.length < 1e-8:
            n = Vector(self.N[a])
        return loc, n.normalized(), d

    def sample(self, count, rng, weight=None):
        p = self.area * (weight if weight is not None else 1.0)
        p = p / p.sum()
        tri = rng.choice(len(self.T), size=count, p=p)
        r1, r2 = rng.random(count), rng.random(count)
        s = np.sqrt(r1)
        bc = np.stack([1 - s, s * (1 - r2), s * r2], 1)
        P = (self.V[self.T[tri]] * bc[:, :, None]).sum(1)
        return P, tri


# ------------------------------------------------------------------ flow fields
def make_flow(st, fr):
    c = fr["centre"]
    if st["kind"] == "curly":
        o = Vector((c.x, fr["eye_front"], fr["eye"].z)) + Vector(st["origin"])

        def flow(p, n):
            r = p - o
            if r.length < 1e-6:
                r = Vector((0, 1, 0))
            g = st["gravity"] * min(1.0, max(0.0, (fr["top"] - 0.03 - p.z) / 0.08))
            return r.normalized() + Vector((0, 0, -1)) * g
        flow.origin = o
        return flow
    a = c + Vector(st["part"][0])
    b = c + Vector(st["part"][1])
    a.z = b.z = fr["top"]

    def flow(p, n):
        ab = b - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
        q = a + ab * t
        r = p - q
        r.z = 0.0
        if t >= 1.0:
            # behind the crown the hair falls back and down, it does not part
            r.x *= 0.25
        elif t <= 0.0:
            # in front of the part: sideways off the parting and a little back, never forward over the brow
            side = 1.0 if p.x >= a.x else -1.0
            r = Vector((side * max(abs(r.x), 0.01), 0.004, 0.0))
        if r.length < 1e-6:
            r = Vector((1, 0, 0))
        g = st["gravity"] * min(1.0, max(0.0, (fr["top"] - 0.015 - p.z) / 0.11)) ** 1.2
        return r.normalized() + Vector((0, 0, -1)) * g
    flow.origin = a
    return flow


def part_distance(st, fr, p):
    c = fr["centre"]
    a = c + Vector(st["part"][0])
    b = c + Vector(st["part"][1])
    a.z = b.z = fr["top"]
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length


# ------------------------------------------------------------------ strands -> cards
def grow(surf, flow, root, length, seg, lift, st, rng, body_bvh, curl=None, free_max=0.02):
    """A strand over the base surface: points (lifted along the smoothed normal), (normal, twist), tangents."""
    p, n, _ = surf.nearest(Vector(root))
    if p is None:
        return None
    nseg = max(2, int(round(length / seg)))
    ds = length / nseg
    pts, nrm, tan = [], [], []
    t_prev = None
    free = False
    free_len = 0.0
    vel = None
    wave = rng.uniform(*curl["wave"]) if curl else 1.0
    # wave phase from the distance to the flow's origin: neighbouring locks wave together (as real wavy hair
    # does), with some jitter so it never reads as a pattern
    ph = (2 * math.pi * (p - flow.origin).length / wave + rng.normal(0, curl["jitter"])) if curl else 0.0
    down = Vector((0, 0, -1))
    for k in range(nseg + 1):
        s = k / nseg
        if not free:
            d = flow(p, n)
            t = d - n * d.dot(n)
            if t.length < 1e-6:
                t = t_prev if t_prev is not None else n.orthogonal()
            t.normalize()
            if t_prev is not None:
                t = (t_prev * 0.45 + t * 0.55).normalized()
        else:
            t = vel.normalized()
        h = lift[0] + (lift[1] - lift[0]) * s
        twist = 0.0
        tt = t
        if curl:
            ang = 2 * math.pi * s * length / wave + ph
            h += curl["lift"] * (0.5 + 0.5 * math.sin(ang)) * min(1.0, s * 4)
            # the lock wiggles over the surface and twists about itself with the same phase: a wave in 3D
            q = Matrix.Rotation(curl["wiggle"] * math.cos(ang), 3, n)
            tt = (q @ t).normalized()
            twist = curl["twist"] * math.sin(ang)
        pts.append(p + n * h)
        nrm.append((n, twist))
        tan.append(tt)
        t_prev = t
        if k == nseg:
            break
        q = p + tt * ds
        if not free:
            loc, nn, dist = surf.nearest(q)
            if loc is None or dist > 0.45 * ds:
                free = True
                vel = tt.copy()
            else:
                p, n = loc, nn
                continue
        # off the base's edge: fall freely (gravity), outside the body, for at most free_max
        free_len += ds
        if free_len > free_max:
            break
        vel = (vel + down * st["gravity"] * 0.35 * ds / 0.01).normalized()
        q = p + vel * ds
        loc, bn, _, _ = body_bvh.find_nearest(q, 0.05)
        if loc is not None and (q - loc).dot(bn) < 0.003:
            q = loc + bn * 0.003
        p = q
        # a small gap (the shell's lower edge onto the hair lying on the back): carry on over the base again
        loc, nn, dist = surf.nearest(q)
        if loc is not None and dist < 0.004 and free_len > 1.5 * ds:
            p, n, free, free_len = loc, nn, False, 0.0
    if len(pts) < 3:
        return None
    if st["long"] and st.get("end_trim"):
        # ragged ends: every lock stops at its own length (a hard common edge reads as a cut-out)
        L = [0.0]
        for i in range(1, len(pts)):
            L.append(L[-1] + (pts[i] - pts[i - 1]).length)
        keep_len = L[-1] - rng.uniform(0.0, st["end_trim"]) * min(1.0, L[-1] / 0.25)
        m = max(3, sum(1 for x in L if x <= keep_len))
        pts, nrm, tan = pts[:m], nrm[:m], tan[:m]
    return pts, nrm, tan


class Cards:
    def __init__(self, strips):
        self.strips = strips
        self.V, self.F, self.UV, self.COL, self.TAN, self.NRM = [], [], [], [], [], []
        self.n = 0
        self.by_layer = {}
        self.volume_normals = True

    def add(self, pts, nrm, tan, width, strip, tone, fade, layer, taper=0.5, rng=None):
        """A ribbon along the strand, lying on the surface (width across tangent x normal, turned by the twist)."""
        u0 = strip / self.strips + 0.003
        u1 = (strip + 1) / self.strips - 0.003
        m = len(pts)
        L = [0.0]
        for k in range(1, m):
            L.append(L[-1] + (pts[k] - pts[k - 1]).length)
        tot = max(L[-1], 1e-6)
        base = len(self.V)
        warm = rng.uniform(-0.04, 0.04) if rng else 0.0
        for k in range(m):
            s = L[k] / tot
            n, twist = nrm[k]
            t = tan[k]
            w = t.cross(n)
            if w.length < 1e-6:
                w = n.orthogonal()
            w.normalize()
            if twist:
                w = (w * math.cos(twist) + n * math.sin(twist)).normalized()
            hw = 0.5 * width * (1.0 - taper * s ** 1.5)
            self.V += [pts[k] - w * hw, pts[k] + w * hw]
            a = 1.0 if fade <= 0 else min(1.0, s / fade) ** 1.5
            c = (tone * (1 + warm), tone, tone * (1 - warm), a)
            self.COL += [c, c]
            self.TAN += [t, t]
            # shading normal: the hair volume's (the base's smoothed normal), so the cards light as one mass
            # of hair instead of as separate flakes
            self.NRM += [n, n]
            self.UV += [(u0, 1.0 - s), (u1, 1.0 - s)]
        for k in range(m - 1):
            i = base + 2 * k
            self.F.append((i, i + 1, i + 3, i + 2))
        self.n += 1
        self.by_layer[layer] = self.by_layer.get(layer, 0) + 1

    def build(self, name, mat):
        me = bpy.data.meshes.new(name)
        me.from_pydata([v.to_tuple() for v in self.V], [], self.F)
        me.update()
        uvl = me.uv_layers.new(name="UVMap")
        loops = np.empty(len(me.loops), np.int32)
        me.loops.foreach_get("vertex_index", loops)
        UV = np.array(self.UV, np.float32)
        uvl.data.foreach_set("uv", UV[loops].ravel())
        col = me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
        col.data.foreach_set("color", np.array(self.COL, np.float32).ravel())
        tan = me.attributes.new("strand", 'FLOAT_VECTOR', 'POINT')
        tan.data.foreach_set("vector", np.array([t.to_tuple() for t in self.TAN], np.float32).ravel())
        for p in me.polygons:
            p.use_smooth = True
        if self.volume_normals:
            me.normals_split_custom_set_from_vertices([n.to_tuple() for n in self.NRM])
        obj = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(obj)
        me.materials.append(mat)
        return obj


def build_hair(st, surf, hb, rng, dens):
    fr = hb["frame"]
    flow = make_flow(st, fr)
    cards = Cards(8)
    area = float(surf.area.sum())
    log(f"guide surface {area * 1e4:.0f} cm^2, {len(surf.V)} verts")
    t0 = time.time()
    curl = st.get("curl")

    def strand(p, name, lrange, wrange, hrange, trange, strips, fade, fade_abs=None):
        if st["long"]:
            length = st["max_len"]
            near_part = part_distance(st, fr, p) < 0.02 and p.z > fr["top"] - 0.05
            # the root fade in absolute terms (a fraction of a 75 cm card would fade in over 20 cm)
            f = (0.004 if near_part else (fade_abs or 0.05)) / length
        else:
            length = rng.uniform(*lrange)
            f = fade if fade_abs is None else fade_abs / length
        lift = (rng.uniform(*hrange), rng.uniform(*hrange) * (1.15 if name == "top" else 1.0))
        fm = st["free_max"] * rng.uniform(0.25 if st["long"] else 0.3, 1.0)
        s = grow(surf, flow, p, length, st["seg"], lift, st, rng, hb["body_bvh"], curl=curl, free_max=fm)
        if s is None:
            return False
        cards.add(*s, width=rng.uniform(*wrange), strip=int(rng.choice(strips)), tone=rng.uniform(*trange),
                  fade=f, layer=name, taper=0.6 if st["long"] else 0.5, rng=rng)
        return True

    for (name, per_m2, lrange, wrange, hrange, trange, strips, fade) in st["layers"]:
        count = int(per_m2 * area * dens)
        P, tri = surf.sample(count, rng)
        made = sum(strand(Vector(p), name, lrange, wrange, hrange, trange, strips, fade) for p in P)
        log(f"layer {name}: {made}/{count} cards")
    # coverage: every guide vertex must lie under an opaque stretch of some card; where none passes, a card
    # is rooted a little upstream (so it is opaque by the time it gets there)
    mid = next(l for l in st["layers"] if l[0] == "mid")
    for it in range(2):
        cp = [(cards.V[k] + cards.V[k + 1]) * 0.5 for k in range(0, len(cards.V), 2) if cards.COL[k][3] > 0.6]
        kd = KDTree(len(cp))
        for i, q in enumerate(cp):
            kd.insert(q, i)
        kd.balance()
        holes = [Vector(v) for v in surf.V if kd.find(Vector(v))[2] > st["cover"]]
        made = 0
        for v in holes:
            loc, n, _ = surf.nearest(v)
            d = flow(loc, n)
            t = d - n * d.dot(n)
            up = loc - (t.normalized() if t.length > 1e-6 else t) * (0.02 if st["long"] else 0.01)
            made += strand(up, "fill", mid[2], mid[3], mid[4], mid[5], mid[6], 0.1, fade_abs=0.008)
        log(f"coverage pass {it}: {len(holes)} bare guide verts -> {made} cards")
        if not holes:
            break
    # the hairline: cards rooted on the scalp mask's iso-line, thinner, with a sharp root
    hl = st["hairline"]
    pts = hb["hairline"]
    if len(pts):
        # thin the iso points to ~step apart (they come per mesh edge, ~1 cm apart: jitter along the line)
        kd = KDTree(len(pts))
        for i, p in enumerate(pts):
            kd.insert(p, i)
        kd.balance()
        made = 0
        n_target = 0
        for i, p in enumerate(pts):
            nb = [q for q, j, d in kd.find_n(p, 3) if j != i]
            per = max(1, int(round(0.01 / (hl["step"] / max(dens, 0.2)))))
            for _ in range(per):
                q = Vector(p)
                if nb:
                    o = nb[int(rng.integers(len(nb)))]
                    q = q.lerp(o, rng.uniform(0.0, 0.5))
                n_target += 1
                made += strand(q, "hairline", hl["length"], hl["width"], (0.0003, 0.0009), hl["tone"],
                               hl["strips"], 0.02)
        log(f"hairline: {made}/{n_target} cards")
    # silhouette: curl flicks springing off the surface (curly) and flyaway strands
    if "loops" in st:
        lp = st["loops"]
        count = int(lp["count_per_m2"] * area * dens)
        wgt = np.clip(surf.N[surf.T].mean(1)[:, 2] + 0.6, 0.05, 1.6)
        P, tri = surf.sample(count, rng, wgt)
        for p in P:
            sp = loop_strand(surf, flow, Vector(p), rng.uniform(*lp["length"]), rng.uniform(*lp["bulge"]), rng, st)
            if sp:
                cards.add(*sp, width=rng.uniform(*lp["width"]), strip=int(rng.choice(lp["strips"])),
                          tone=rng.uniform(0.8, 1.0), fade=0.2, layer="loops", taper=0.4, rng=rng)
    fl = st["fly"]
    wgt = np.clip(surf.N[surf.T].mean(1)[:, 2] + 0.3, 0.02, 1.3)
    P, tri = surf.sample(int(fl["count"] * dens), rng, wgt)
    for p in P:
        sp = loop_strand(surf, flow, Vector(p), rng.uniform(*fl["length"]), rng.uniform(*fl["bulge"]), rng, st,
                         seg=0.008 if not st["long"] else 0.012)
        if sp:
            cards.add(*sp, width=rng.uniform(*fl["width"]), strip=7, tone=rng.uniform(0.85, 1.05), fade=0.15,
                      layer="fly", taper=0.3, rng=rng)
    log(f"cards grown in {time.time() - t0:.1f} s")
    return cards


def loop_strand(surf, flow, p, length, bulge, rng, st, seg=0.006):
    """A strand that leaves the surface and arcs back to it (a curl flick or a flyaway breaking the outline)."""
    loc, n, _ = surf.nearest(p)
    if loc is None:
        return None
    d = flow(loc, n)
    t = (d - n * d.dot(n))
    if t.length < 1e-6:
        return None
    t.normalize()
    t = (Matrix.Rotation(rng.uniform(-0.6, 0.6), 3, n) @ t).normalized()
    m = max(4, int(length / seg))
    pts, nrm, tan = [], [], []
    for k in range(m + 1):
        s = k / m
        h = 0.0015 + bulge * math.sin(math.pi * min(1.0, s * 1.15)) + (0.0 if st["long"] else 0.004 * s)
        q = loc + t * (length * s)
        q2, n2, dist = surf.nearest(q)
        if q2 is None or dist > 0.03:
            q2, n2 = q, n
        pts.append(q2 + n2 * h)
        nrm.append((n2, rng.uniform(-0.3, 0.3)))
    for k in range(len(pts)):
        a = pts[max(k - 1, 0)]
        b = pts[min(k + 1, len(pts) - 1)]
        tan.append((b - a).normalized())
    return pts, nrm, tan


# ------------------------------------------------------------------ materials
def node(nt, kind, **kw):
    n = nt.nodes.new(kind)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def vmath(nt, op, a=None, b=None, scale=None):
    n = nt.nodes.new('ShaderNodeVectorMath')
    n.operation = op
    if a is not None:
        nt.links.new(a, n.inputs[0])
    if b is not None:
        if isinstance(b, (tuple, list)):
            n.inputs[1].default_value = b
        else:
            nt.links.new(b, n.inputs[1])
    if scale is not None:
        if isinstance(scale, float):
            n.inputs["Scale"].default_value = scale
        else:
            nt.links.new(scale, n.inputs["Scale"])
    return n


def fmath(nt, op, a, b=None):
    n = nt.nodes.new('ShaderNodeMath')
    n.operation = op
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = float(x)
        else:
            nt.links.new(x, n.inputs[i])
    return n.outputs[0]


def strand_normal(nt, T, N, V, shift):
    """The strand's own normal facing the viewer: the view vector with its component along the (shifted)
    tangent removed. An isotropic glossy lobe on this normal gives the Kajiya-Kay-like highlight band running
    across the strands, lit by the real lights (and shadowed by them)."""
    tn = vmath(nt, 'SCALE', N, scale=shift)
    t1 = vmath(nt, 'ADD', T, tn.outputs[0])
    t1 = vmath(nt, 'NORMALIZE', t1.outputs[0])
    dot = vmath(nt, 'DOT_PRODUCT', V, t1.outputs[0])
    proj = vmath(nt, 'SCALE', t1.outputs[0], scale=dot.outputs["Value"])
    vp = vmath(nt, 'SUBTRACT', V, proj.outputs[0])
    return vmath(nt, 'NORMALIZE', vp.outputs[0]).outputs[0]


def card_material(st, atlas_path):
    mat = bpy.data.materials.new(f"{st['id']}_hair_protoB")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = node(nt, 'ShaderNodeOutputMaterial')
    tex = node(nt, 'ShaderNodeTexImage')
    tex.image = bpy.data.images.load(atlas_path)
    tex.image.alpha_mode = 'STRAIGHT'
    tex.interpolation = 'Linear'
    uv = node(nt, 'ShaderNodeUVMap')
    uv.uv_map = "UVMap"
    nt.links.new(uv.outputs[0], tex.inputs[0])
    col = node(nt, 'ShaderNodeVertexColor')
    col.layer_name = "Col"
    attr = node(nt, 'ShaderNodeAttribute')
    attr.attribute_name = "strand"
    geo = node(nt, 'ShaderNodeNewGeometry')
    # root darkening by v (root at uv.y = 1)
    sep = node(nt, 'ShaderNodeSeparateXYZ')
    nt.links.new(uv.outputs[0], sep.inputs[0])
    rd = node(nt, 'ShaderNodeMapRange')
    rd.inputs["From Min"].default_value = 1.0
    rd.inputs["From Max"].default_value = 0.78
    rd.inputs["To Min"].default_value = 0.55
    rd.inputs["To Max"].default_value = 1.0
    rd.interpolation_type = 'SMOOTHSTEP'
    nt.links.new(sep.outputs[1], rd.inputs[0])
    m1 = node(nt, 'ShaderNodeMix')
    m1.data_type = 'RGBA'
    m1.blend_type = 'MULTIPLY'
    m1.inputs[0].default_value = 1.0
    nt.links.new(tex.outputs[0], m1.inputs[6])
    nt.links.new(col.outputs[0], m1.inputs[7])
    m2 = node(nt, 'ShaderNodeMix')
    m2.data_type = 'RGBA'
    m2.blend_type = 'MULTIPLY'
    m2.inputs[0].default_value = 1.0
    nt.links.new(m1.outputs[2], m2.inputs[6])
    m2.inputs[7].default_value = (*st["tint"], 1.0)
    alb = vmath(nt, 'SCALE', m2.outputs[2], scale=rd.outputs[0])
    # alpha: texture x vertex alpha (root fade-in of the cards that start on top of other hair)
    am = fmath(nt, 'MULTIPLY', tex.outputs[1], col.outputs[1])
    diff = node(nt, 'ShaderNodeBsdfDiffuse')
    nt.links.new(alb.outputs[0], diff.inputs[0])
    trans = node(nt, 'ShaderNodeBsdfTranslucent')
    tsc = vmath(nt, 'SCALE', alb.outputs[0], scale=float(st["trans"]))
    nt.links.new(tsc.outputs[0], trans.inputs[0])
    add0 = node(nt, 'ShaderNodeAddShader')
    nt.links.new(diff.outputs[0], add0.inputs[0])
    nt.links.new(trans.outputs[0], add0.inputs[1])
    T = attr.outputs["Vector"]
    N = geo.outputs["Normal"]
    V = geo.outputs["Incoming"]
    # strand breakup of the highlights: the texel's own coverage and brightness (strand cores bright, the gaps
    # between strands dark), so a highlight is a band of glints, not a smooth sheet across the card
    bw = node(nt, 'ShaderNodeRGBToBW')
    nt.links.new(tex.outputs[0], bw.inputs[0])
    brk = fmath(nt, 'MULTIPLY', fmath(nt, 'POWER', bw.outputs[0], st["brk_pow"]),
                fmath(nt, 'POWER', tex.outputs[1], 1.5))
    brk = fmath(nt, 'MULTIPLY', brk, 1.6)
    # primary (whiteish, shifted towards the tip) and secondary (hair-coloured, towards the root) highlights
    g1 = node(nt, 'ShaderNodeBsdfGlossy')
    g1.inputs["Roughness"].default_value = st["spec1_rough"]
    k = st["spec1"]
    c1 = node(nt, 'ShaderNodeCombineColor')
    for i, f in enumerate((k, k * 0.97, k * 0.93)):
        nt.links.new(fmath(nt, 'MULTIPLY', brk, f), c1.inputs[i])
    nt.links.new(c1.outputs[0], g1.inputs["Color"])
    nt.links.new(strand_normal(nt, T, N, V, -0.08), g1.inputs["Normal"])
    g2 = node(nt, 'ShaderNodeBsdfGlossy')
    g2.inputs["Roughness"].default_value = st["spec2_rough"]
    c2 = node(nt, 'ShaderNodeCombineColor')
    for i, f in enumerate(st["spec2"]):
        nt.links.new(fmath(nt, 'MULTIPLY', brk, f * st["spec2_k"]), c2.inputs[i])
    nt.links.new(c2.outputs[0], g2.inputs["Color"])
    nt.links.new(strand_normal(nt, T, N, V, 0.12), g2.inputs["Normal"])
    add1 = node(nt, 'ShaderNodeAddShader')
    nt.links.new(add0.outputs[0], add1.inputs[0])
    nt.links.new(g1.outputs[0], add1.inputs[1])
    add2 = node(nt, 'ShaderNodeAddShader')
    nt.links.new(add1.outputs[0], add2.inputs[0])
    nt.links.new(g2.outputs[0], add2.inputs[1])
    tr = node(nt, 'ShaderNodeBsdfTransparent')
    mix = node(nt, 'ShaderNodeMixShader')
    nt.links.new(am, mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(add2.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    set_dithered(mat)
    return mat


def set_dithered(mat):
    for k_, v in (("surface_render_method", 'DITHERED'), ("use_backface_culling", False),
                  ("use_transparent_shadow", True), ("blend_method", 'HASHED')):
        try:
            setattr(mat, k_, v)
        except (AttributeError, TypeError):
            pass


def under_material(name, st, img):
    """The underlayer (smoothed shell): the hair's root colour, a little of the bake's light and dark kept so
    it is not a flat sheet, fully matte. Only seen through the gaps between the cards."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    tx = nt.nodes.new('ShaderNodeTexImage')
    tx.image = img
    bw = nt.nodes.new('ShaderNodeRGBToBW')
    nt.links.new(tx.outputs[0], bw.inputs[0])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs["From Min"].default_value = 0.0
    mr.inputs["From Max"].default_value = 0.08
    mr.inputs["To Min"].default_value = 0.7
    mr.inputs["To Max"].default_value = 1.3
    nt.links.new(bw.outputs[0], mr.inputs[0])
    sc = vmath(nt, 'SCALE', None, scale=mr.outputs[0])
    sc.inputs[0].default_value = st["root"]
    nt.links.new(sc.outputs[0], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.95
    b.inputs["Specular IOR Level"].default_value = 0.1
    return mat


def cap_material(name, st, mask_img, fr=None):
    """The scalp cap: root colour, alpha = the texture's hair mask (sharpened) x the region weight (vertex
    attribute); with a centre part, a 3 mm line of scalp left open along it."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    tx = nt.nodes.new('ShaderNodeTexImage')
    tx.image = mask_img
    tx.image.alpha_mode = 'STRAIGHT'
    at = nt.nodes.new('ShaderNodeAttribute')
    at.attribute_name = "capw"
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.interpolation_type = 'SMOOTHSTEP'
    mr.inputs["From Min"].default_value = 0.4
    mr.inputs["From Max"].default_value = 0.8
    nt.links.new(tx.outputs[1], mr.inputs[0])
    a = fmath(nt, 'MULTIPLY', mr.outputs[0], at.outputs["Fac"])
    if fr is not None and st.get("part"):
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        sp = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(geo.outputs["Position"], sp.inputs[0])
        px = fr["centre"].x + st["part"][0][0]
        dx = fmath(nt, 'ABSOLUTE', fmath(nt, 'SUBTRACT', sp.outputs[0], px))
        band = nt.nodes.new('ShaderNodeMapRange')
        band.interpolation_type = 'SMOOTHSTEP'
        band.inputs["From Min"].default_value = 0.0015
        band.inputs["From Max"].default_value = 0.0035
        nt.links.new(dx, band.inputs[0])
        y0 = fr["centre"].y + st["part"][0][1] - 0.01
        y1 = fr["centre"].y + st["part"][1][1]
        iny = fmath(nt, 'MULTIPLY', fmath(nt, 'GREATER_THAN', sp.outputs[1], y0),
                    fmath(nt, 'LESS_THAN', sp.outputs[1], y1))
        open_ = fmath(nt, 'MULTIPLY', fmath(nt, 'SUBTRACT', 1.0, band.outputs[0]), iny)
        a = fmath(nt, 'MULTIPLY', a, fmath(nt, 'SUBTRACT', 1.0, open_))
    b.inputs["Base Color"].default_value = (*[c * 2.2 for c in st["root"]], 1.0)
    nt.links.new(a, b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.9
    b.inputs["Specular IOR Level"].default_value = 0.12
    set_dithered(mat)
    return mat


def mask_image(name, hair_tex):
    """The scalp mask as an RGBA image (alpha = mask, slightly blurred so the hairline is soft)."""
    h, w = hair_tex.shape
    a = hair_tex.astype(np.float32)
    # 3 box blurs ~ a gaussian of a few texels
    for _ in range(3):
        p = np.pad(a, 2, mode='edge')
        a = sum(p[2 + dy:2 + dy + h, 2 + dx:2 + dx + w] for dy in range(-2, 3) for dx in range(-2, 3)) / 25.0
    img = bpy.data.images.new(name, w, h, alpha=True)
    px = np.ones((h, w, 4), np.float32)
    px[..., 0] = px[..., 1] = px[..., 2] = a      # the mask in rgb too (easy to look at)
    px[..., 3] = a
    img.pixels.foreach_set(px.ravel())
    path = os.path.join(OUT, f"{name}.png")
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = 'Non-Color'
    img.alpha_mode = 'STRAIGHT'
    log("mask", os.path.relpath(path, ROOT), "mean", round(float(a.mean()), 3))
    return img


# ------------------------------------------------------------------ studio + cameras
def studio(scene):
    for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = e
            break
        except TypeError:
            pass
    ee = scene.eevee
    for k, v in (("taa_render_samples", 96), ("use_shadows", True), ("use_raytracing", True),
                 ("shadow_ray_count", 2), ("shadow_step_count", 8)):
        try:
            setattr(ee, k, v)
        except (AttributeError, TypeError):
            pass
    scene.view_settings.view_transform = 'AgX'
    scene.render.film_transparent = True     # composited over the game viewer's dark backdrop afterwards
    w = bpy.data.worlds.new("studio")
    scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.42, 0.45, 0.5, 1)
    bg.inputs[1].default_value = 0.22
    # the game viewer's three lights (char_viewer.gd), in Blender axes, neutral colours
    for name, frm, colr, energy, ang in (("key", (0.47, -0.67, 0.57), (1.0, 0.95, 0.9), 3.6, 3.0),
                                         ("fill", (-0.84, -0.48, 0.26), (0.88, 0.92, 1.0), 1.4, 8.0),
                                         ("rim", (0.32, 0.88, 0.34), (1.0, 0.97, 0.94), 2.8, 3.0)):
        ld = bpy.data.lights.new(name, 'SUN')
        ld.energy = energy
        ld.color = colr
        ld.angle = math.radians(ang)
        lo = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(lo)
        d = Vector(frm).normalized()
        lo.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()


def flatten(path):
    """RGBA render -> over the dark backdrop (sRGB), saved back as RGB."""
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(-1, 4)
    bg = np.array(BACKDROP, np.float32)
    a[:, :3] = a[:, :3] * a[:, 3:4] + bg[None] * (1 - a[:, 3:4])
    a[:, 3] = 1.0
    img.pixels.foreach_set(a.ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def shoot(scene, fr, st, views, res, prefix):
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 85
    scene.render.resolution_x = scene.render.resolution_y = res
    scene.render.image_settings.color_mode = 'RGBA'
    c = fr["centre"]
    paths = []
    for v in views:
        yaw, h, dz = {"front": (0, 0.36, 0.0), "34": (40, 0.36, 0.0), "side": (90, 0.38, -0.01),
                      "back": (155, 0.4, -0.02), "top": (25, 0.34, 0.0), "close": (28, 0.2, 0.05),
                      "closeback": (150, 0.22, 0.05)}[v]
        if st["long"] and v not in ("close", "closeback"):
            h, dz = h * 1.55, dz - 0.11
        tgt = c + Vector((0, 0, dz))
        dist = h / (2 * math.tan(math.atan(18 / 85)))
        off = Matrix.Rotation(math.radians(yaw), 3, 'Z') @ Vector((0, -dist, 0.04 if v != "top" else 0.25))
        cam.location = tgt + off
        cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
        path = f"{prefix}_{v}.png"
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        flatten(path)
        paths.append(path)
        log("render", os.path.relpath(path, ROOT))
    return paths


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    stem = argv[0]
    flags = [a for a in argv[1:] if "=" not in a]
    opts = dict(a.split("=", 1) for a in argv[1:] if "=" in a)
    st = STYLES[stem]
    views = opts.get("views", "front,34,side,back").split(",")
    res = int(opts.get("res", 1100))
    seed = int(opts.get("seed", 1))
    dens = float(opts.get("dens", 1.0))
    tag = opts.get("tag", "")
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(REVIEW, exist_ok=True)
    t0 = time.time()
    rig = load(stem)
    scene = bpy.context.scene
    hb = hair_base(rig, st)
    fr = hb["frame"]
    studio(scene)
    if "before" in flags:
        m = hb["shell"].active_material
        b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        b.inputs["Roughness"].default_value = 0.66
        b.inputs["Specular IOR Level"].default_value = 0.25
        shoot(scene, fr, st, views, res, os.path.join(OUT, f"before_{st['id']}{tag}"))
        log("done", round(time.time() - t0, 1), "s")
        return
    rng = np.random.default_rng(seed)
    random.seed(seed)
    # the guide: the smoothed shell + the bare scalp
    Vs, Ts, UVs = hb["shell_part"]
    Vw, Tw, inv = weld_map(Vs, Ts)
    Vsm = taubin(Vw, Tw, int(opts.get("smooth", st["smooth"])))
    log(f"shell smoothed ({st['smooth']} Taubin steps): mean move {np.linalg.norm(Vsm - Vw, axis=1).mean() * 1000:.1f}"
        f" mm, max {np.linalg.norm(Vsm - Vw, axis=1).max() * 1000:.1f} mm")
    Vgc, Tgc = hb["guide_cap"]
    Vg = np.concatenate([Vsm, Vgc])
    Tg = np.concatenate([Tw, Tgc + len(Vsm)])
    surf = Surface(Vg, Tg, welded=True)
    cards = build_hair(st, surf, hb, rng, dens)
    atlas = os.path.join(OUT, f"atlas_{st['atlas']}.png")
    cobj = cards.build(f"{st['id']}_hair_protoB", card_material(st, atlas))
    # the underlayer: the smoothed shell, 1.5 mm further in, root colour, matte; the original shell hidden
    hb["shell"].hide_render = True
    Nsm = vertex_normals(Vsm, Tw)
    Vu = (Vsm - Nsm * 0.0015)[inv]
    shell_img = base_color_image(hb["shell"].active_material)
    sobj = make_mesh(f"{st['id']}_hairbase_shell", Vu, Ts, UV=UVs,
                     mats=[under_material("under_matte", st, shell_img)])
    Vc, Tc, cuv, cw, head_img, hair_tex = hb["cap_part"]
    objs = [cobj, sobj]
    if len(Tc):
        mimg = mask_image(f"{st['id']}_scalpmask", hair_tex)
        cobj2 = make_mesh(f"{st['id']}_hairbase_cap", Vc, Tc, UV=cuv, mats=[cap_material("cap", st, mimg, fr)])
        at = cobj2.data.attributes.new("capw", 'FLOAT', 'POINT')
        at.data.foreach_set("value", cw.astype(np.float32))
        objs.append(cobj2)
    ntri = len(cards.F) * 2
    log(f"STATS {st['id']}: {cards.n} cards {dict(cards.by_layer)}, {len(cards.V)} verts, {ntri} tris; "
        f"underlayer {len(Ts)} tris, cap {len(Tc)} tris")
    if opts.get("export"):
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs:
            o.select_set(True)
        bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, f"{stem}_hairB{tag}.glb"), use_selection=True,
                                  export_attributes=True)
    if opts.get("debug"):
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, f"debug_{st['id']}{tag}.blend"))
    shoot(scene, fr, st, views, res, os.path.join(REVIEW, f"hair_proto_B_{st['id']}{tag}"))
    log("done", round(time.time() - t0, 1), "s")


main()
