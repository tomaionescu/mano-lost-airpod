"""Hair prototype C (the scan shell, done right), step 2: a new hair shell from the captured scan, its maps, renders.

usage: Blender -b -P tools/blender/proto_hair_C.py -- <stem> [stage=all|render] [tex=1] [before=1] [tag=..]
         [views=front,face34,back] [variants=name:k=v,k=v|name2:k=v] [<STYLE key>=value ...]
  needs tools/out/proto_C/<stem>_capture.blend (+ .npz) from proto_hair_C_capture.py
  shading keys (also inside variants): spec, sheen, sheenr, nstr (normal map strength), radd (roughness offset),
  engine=eevee|cycles, aniso (Cycles only: anisotropic GGX across the strands, the stand-in for Godot's
  ANISOTROPY_FLOW; EEVEE ignores anisotropy), spp

What changes against scan_wrap.hair_shell (the current helmet):
  1. coverage: every hair-coloured scan face above the hairline, including those lying on or inside the template's
     skull (the current 4 mm rule left the back of the head bare skin), and for long hair down to the tips;
  2. surface: Taubin-smoothed (no AI crumple, no faceting), subdivided once; NOT pushed out of the template's skull
     or body (every push folded the shell where the collider ended): the body is tucked under the shell instead
     (tuck_body: scalp, and the long-hair "cape" the wrap pulled onto the hair, go 0.6-4 mm under it);
  3. a strand flow field: a style model (crown-radial, or a centre part in front of the crown and crown-radial
     behind it) blended with the painted strand streaks of the scan's own texture (structure tensor);
  4. clump relief in the geometry: 3D line-integral convolution of noise along the flow, displaced along normals;
  5. smoothed shading normals (custom normals, 35 % curls / 80 % straight): one coherent sheen, no blotches;
  6. maps (proto_hair_C_tex.py): strand height -> tangent normal map, albedo (person's colour, roots darker,
     strand-level variation, cavity AO; the scan's painted lighting is not used), roughness, alpha for strand tips
     at the free edges and the hairline, AO, and a flow map for Godot's anisotropy;
  7. two "fuzz" shells floating 1-4 mm above it with sparse alpha strands: soft, broken silhouette.
Outputs: tools/out/proto_C/<stem>_hair.blend, maps in tools/out/proto_C/<stem>/, renders
tools/out/review/hair_proto_C_<id><tag><variant>_<view>.png (before=1: _before_<view> with the current shell).
"""
import bpy, bmesh, os, sys, math, json, subprocess, time
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "tools", "out", "proto_C")
REVIEW = os.path.join(ROOT, "tools", "out", "review")
PY = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"
sys.path.insert(0, HERE)
import scan_wrap as sw

T0 = time.time()
SHADE = {}
DEBUG = {}
GROW_RINGS = 3


def log(*a):
    print(f"[protoC {time.time() - T0:6.1f}s]", *a, flush=True)


def srgb_lin(h):
    h = h.lstrip('#')
    c = np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# per character: how the hair is made. flow: "part" (centre part, falls down) or "crown" (out from the crown).
STYLE = {
    "toma_fit1": dict(cid="toma", flow="crown", data_flow=0.75, crown_fwd=0.02,
                      smooth=12, clump_cell=0.012, clump_len=0.014, clump_amp=0.003,
                      fuzz=(0.0016, 0.0036), root="#0b0705", tip="#2e1c11", tex=2048,
                      fine_len=0.006, mid_len=0.010, coarse_len=0.016, tip_len=0.016, wave=0.0, nsmooth=0.35),
    "anisha": dict(cid="anisha", flow="part", data_flow=0.35, crown_fwd=-0.01,
                   smooth=10, clump_cell=0.0060, clump_len=0.028, clump_amp=0.0014,
                   fuzz=(0.0012, 0.0028), root="#080605", tip="#1a1310", tex=2048,
                   fine_len=0.009, mid_len=0.016, coarse_len=0.03, tip_len=0.022, wave=0.0, nsmooth=0.8),
}


# ------------------------------------------------------------------ small mesh tools (numpy)
def mesh_arrays(obj):
    P = sw.world_verts(obj)
    T = sw.triangles(obj.data)
    E = sw.edges(obj.data)
    return P, T, E


def taubin(P, E, fixed, iters, lam=0.5, mu=-0.53):
    n = len(P)
    free = (~fixed)[:, None].astype(np.float64)
    for _ in range(iters):
        for k in (lam, mu):
            M = np.stack([sw.neighbour_mean(P[:, c], E, n) for c in range(3)], 1)
            P = P + k * (M - P) * free
    return P


def vec_smooth(F, E, iters, lam=0.5):
    n = len(F)
    for _ in range(iters):
        M = np.stack([sw.neighbour_mean(F[:, c], E, n) for c in range(3)], 1)
        F = (1 - lam) * F + lam * M
    return F


def geodesic(P, E, seeds, iters=200):
    """Approximate distance along the mesh from the seed vertices (Bellman-Ford over edges)."""
    d = np.full(len(P), np.inf)
    d[seeds] = 0.0
    L = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1)
    for _ in range(iters):
        d0 = d.copy()
        np.minimum.at(d, E[:, 0], d[E[:, 1]] + L)
        np.minimum.at(d, E[:, 1], d[E[:, 0]] + L)
        if np.allclose(d, d0, equal_nan=True):
            break
    return d


def boundary_verts(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    b = np.array([v.is_boundary for v in bm.verts], bool)
    bm.free()
    return b


def hash01(ix, iy, iz, seed):
    h = (ix * np.int64(73856093)) ^ (iy * np.int64(19349663)) ^ (iz * np.int64(83492791)) ^ np.int64(seed * 2654435761 % (1 << 31))
    h = (h ^ (h >> np.int64(13))) * np.int64(1274126177)
    h = h ^ (h >> np.int64(16))
    return (h & np.int64(0xFFFFFF)).astype(np.float64) / float(0xFFFFFF)


def vnoise3(P, seed=0):
    f = np.floor(P)
    i = f.astype(np.int64)
    t = P - f
    u = t * t * t * (t * (t * 6 - 15) + 10)
    acc = np.zeros(len(P))
    for dx in (0, 1):
        wx = u[:, 0] if dx else 1 - u[:, 0]
        for dy in (0, 1):
            wy = u[:, 1] if dy else 1 - u[:, 1]
            for dz in (0, 1):
                wz = u[:, 2] if dz else 1 - u[:, 2]
                acc += wx * wy * wz * (hash01(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed) * 2 - 1)
    return acc


class FlowGrid:
    """The shell's flow splatted into a voxel grid, for line integrals off the vertices."""

    def __init__(self, P, F, h=0.003):
        self.lo = P.min(0) - 0.03
        self.h = h
        shape = np.ceil((P.max(0) + 0.03 - self.lo) / h).astype(int) + 2
        acc = np.zeros(tuple(shape) + (3,), np.float32)
        w = np.zeros(tuple(shape), np.float32)
        idx = np.round((P - self.lo) / h).astype(int)
        np.add.at(acc, (idx[:, 0], idx[:, 1], idx[:, 2]), F.astype(np.float32))
        np.add.at(w, (idx[:, 0], idx[:, 1], idx[:, 2]), 1.0)
        for _ in range(3):
            acc = self._box(acc)
            w = self._box(w)
        self.F = acc / np.maximum(w, 1e-6)[..., None]
        self.shape = shape

    @staticmethod
    def _box(a):
        out = a.copy()
        for ax in range(3):
            out = out + np.roll(out, 1, ax) + np.roll(out, -1, ax)
        return out / 27.0

    def sample(self, P):
        g = (P - self.lo) / self.h
        g = np.clip(g, 0, np.array(self.shape) - 1.001)
        i = np.floor(g).astype(int)
        t = g - i
        out = np.zeros((len(P), 3))
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (t[:, 0] if dx else 1 - t[:, 0]) * (t[:, 1] if dy else 1 - t[:, 1]) * (t[:, 2] if dz else 1 - t[:, 2])
                    out += w[:, None] * self.F[i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz]
        return out


def lic3(P, F0, grid, length, cell, seed, step=0.001):
    """Mean of 3D value noise along the flow through each point (both ways): elongated clumps."""
    n = max(2, int(length / step))
    acc = vnoise3(P / cell, seed)
    wsum = np.ones(len(P))
    for sgn in (1.0, -1.0):
        q = P.copy()
        prev = F0 * sgn
        for k in range(1, n + 1):
            f = grid.sample(q)
            f = f * np.sign(np.sum(f * prev, 1, keepdims=True) + 1e-12)
            f /= np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-9)
            q = q + step * f
            prev = f
            w = 0.5 + 0.5 * math.cos(math.pi * k / (n + 1))
            acc += w * vnoise3(q / cell, seed)
            wsum += w
    return acc / wsum


# ------------------------------------------------------------------ 1. which scan faces are hair (all of them)
def full_hair_mask(scan, body, rig, lms, long_hair):
    me = scan.data
    SV = sw.world_verts(scan)
    V = sw.world_verts(body)
    names = [b.name for b in rig.data.bones if b.use_deform and b.name in body.vertex_groups]
    W = sw.deform_weights(body, names)
    in_body = np.ones(len(V), bool)
    Tri = sw.triangles(body.data)
    bodyt = BVHTree.FromPolygons(V.tolist(), Tri.tolist(), all_triangles=True)
    skull = sw.head_surface(body, names, W, in_body)
    lab = sw.to_lab(sw.scan_colors(me))
    top = float(V[:, 2].max())
    z_head = float(sw.bone_head(rig, "head")[2])
    z_sh = float(sw.bone_head(rig, "upperarm_l")[2])
    z_hip = float(sw.bone_head(rig, "pelvis")[2])
    zmin = z_hip + 0.2 if long_hair else z_head - 0.03
    out = np.full(len(SV), -1.0)
    near = np.full(len(SV), 1.0)
    for i in np.nonzero(SV[:, 2] > zmin)[0]:
        p = Vector(SV[i])
        loc, n, _, _ = bodyt.find_nearest(p, 0.4)
        if loc is not None:
            out[i] = (p - loc).dot(n)
        loc, _, _, d = skull.find_nearest(p, 0.5)
        if loc is not None:
            near[i] = d
    L = np.array(list(lms.values()))
    brow_z = float(np.mean([lms[i][2] for i in sw.BROWS if i in lms]))
    ear_y = float(np.mean([lms[i][1] for i in (234, 454, 127, 356) if i in lms] or [L[:, 1].max()]))
    half_w = float(np.mean([abs(lms[i][0]) for i in (234, 454) if i in lms] or [0.07]))
    cx = float(np.mean([lms[i][0] for i in (1, 4, 6) if i in lms] or [0.0]))
    face = np.zeros(len(SV), bool)
    for s0 in range(0, len(SV), 4000):
        face[s0:s0 + 4000] = np.sqrt(((SV[s0:s0 + 4000, None, :] - L[None]) ** 2).sum(-1).min(1)) < 0.016
    # below the brows in front of the ears is face, except the curtains beside it
    face |= (SV[:, 2] < brow_z) & (SV[:, 1] < ear_y + 0.005) & (np.abs(SV[:, 0] - cx) < half_w + (0.004 if long_hair else 0.02))
    seeds = (SV[:, 2] > top - 0.02) & (out > 0.0) & ~face
    cloth = (SV[:, 2] > z_hip + 0.1) & (SV[:, 2] < z_sh - 0.12) & (np.abs(SV[:, 0]) < 0.12)
    Ch, Cc = sw.kmeans(lab[seeds], 3), sw.kmeans(lab[cloth], 4)
    dh = np.sqrt(((lab[:, None] - Ch[None]) ** 2).sum(-1).min(1))
    dc = np.sqrt(((lab[:, None] - Cc[None]) ** 2).sum(-1).min(1))
    hairlike = (dh < dc) & (dh < 28)
    reach = 0.4 if long_hair else 0.07
    # no "4 mm outside the body" rule: hair lying on (or sunk into) the template's skull is hair too
    hair = ((SV[:, 2] > zmin) & (out > -0.03) & ~face & hairlike & (near < reach)) | seeds
    DEBUG.update(out=out, face=face, hairlike=hairlike, near=near, zmin=zmin, reach=reach, raw=hair.copy())
    # close small holes / specks on the vertex graph
    E = sw.edges(me)
    n = len(SV)
    h = hair.astype(np.float64)
    # grow ~1 cm down over the hairline band the scan paints onto the skin (darker than skin, lighter than hair),
    # staying off the brows and eyes: the shell's sparse root strands then sit over it instead of a grey stripe
    skin_l = float(np.median(lab[face & (SV[:, 2] > brow_z - 0.03), 0])) if (face & (SV[:, 2] > brow_z - 0.03)).any() else 60.0
    eye_ids = [i for i in sw.BROWS + [33, 133, 362, 263, 159, 386] if i in lms]
    Le = np.array([lms[i] for i in eye_ids])
    off_eyes = np.sqrt(((SV[:, None, :] - Le[None]) ** 2).sum(-1).min(1)) > 0.014
    band = (lab[:, 0] < skin_l - 10) & off_eyes & (SV[:, 2] > brow_z + 0.01) & (SV[:, 2] > zmin)
    for _ in range(int(DEBUG.get("grow_rings", GROW_RINGS))):
        nb = (np.bincount(E[:, 0], weights=h[E[:, 1]], minlength=n) > 0) | (np.bincount(E[:, 1], weights=h[E[:, 0]], minlength=n) > 0)
        h = np.maximum(h, nb & band)
    log(f"hairline band: skin L {skin_l:.0f}; mask grown by {int((h > 0.5).sum() - hair.sum())} vertices")
    for _ in range(2):
        h = np.maximum(h, (np.bincount(E[:, 0], weights=h[E[:, 1]], minlength=n) > 0) | (np.bincount(E[:, 1], weights=h[E[:, 0]], minlength=n) > 0))
    for _ in range(2):
        nb = sw.neighbour_mean(h, E, n)
        h = h * (nb > 0.999)
    hair = h > 0.5
    mask, pieces = sw.poly_mask_components(me, hair, min_faces=150)
    log(f"hair mask: {int(mask.sum())} faces in {pieces} pieces (current pipeline's rule kept fewer)")
    info = dict(z_head=z_head, z_sh=z_sh, brow_z=brow_z, names=names)
    return mask, skull, bodyt, W, names, info


# ------------------------------------------------------------------ 2. the shell surface
def build_shell(scan, fmask, name):
    bm = bmesh.new()
    bm.from_mesh(scan.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not fmask[f.index]], context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    # drop slivers: pieces of under 60 faces
    bm.faces.ensure_lookup_table()
    seen, small = set(), []
    for f0 in bm.faces:
        if f0.index in seen:
            continue
        stack, piece = [f0], []
        seen.add(f0.index)
        while stack:
            f = stack.pop()
            piece.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        if len(piece) < 60:
            small += piece
    if small:
        bmesh.ops.delete(bm, geom=small, context='FACES')
    # pinholes in the mask (a few faces the colour test missed) show as dark specks: fill loops of up to 12 edges
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=12)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = scan.matrix_world.copy()
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    for a in list(me.color_attributes):
        me.color_attributes.remove(a)
    me.materials.clear()
    return obj


def unwrap(obj, P, E):
    """UVs from a heavily smoothed copy of the shell (curl lumps would cut smart-project into thousands of
    islands), packed tight; the real positions come back afterwards (same topology, so the UVs carry over)."""
    proxy = taubin(P, E, np.zeros(len(P), bool), 60, lam=0.6, mu=-0.62)
    sw.set_world_verts(obj, proxy)
    me = obj.data
    me.uv_layers.new(name="UVMap")
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(70), island_margin=0.002)
    try:
        bpy.ops.uv.pack_islands(rotate=True, margin=0.002, shape_method='CONCAVE')
    except TypeError:
        bpy.ops.uv.pack_islands(rotate=True, margin=0.002)
    bpy.ops.object.mode_set(mode='OBJECT')
    sw.set_world_verts(obj, P)


def subdivide(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1, use_grid_fill=True)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def push_out(P, bvh, gap, maxd=0.03, mask=None):
    """Move points that are inside (or closer than gap to) a surface out to gap along its normal. Only within
    maxd of it: further away the nearest point's normal says nothing (long hair below the nape collapsed onto it)."""
    moved = np.zeros(len(P))
    for i in range(len(P)):
        if mask is not None and not mask[i]:
            continue
        loc, n, _, d = bvh.find_nearest(Vector(P[i]), maxd)
        if loc is None:
            continue
        v = Vector(P[i]) - loc
        s = v.dot(n)
        if s >= gap:
            continue
        # nearest point on the rim of an open patch (offset mostly sideways): the point is beyond the patch,
        # not inside it; pushing it along the rim triangle's normal folds the shell onto the rim
        if s > -0.004 and (v - n * s).length > max(0.0015, 0.5 * abs(s)):
            continue
        P[i] = np.array(loc + n * gap)
        moved[i] = gap - s
    return P, moved


def signed_dist(P, bvh, maxd=0.3):
    """Signed distance near the surface (inside < 0), plain distance beyond 2 cm."""
    s = np.full(len(P), maxd)
    nn = np.zeros((len(P), 3))
    for i in range(len(P)):
        loc, n, _, d = bvh.find_nearest(Vector(P[i]), maxd)
        if loc is not None:
            s[i] = (Vector(P[i]) - loc).dot(n) if d < 0.02 else d
            nn[i] = n
    return s, nn


# ------------------------------------------------------------------ 3. flow
def scan_strand_dirs(scan, faces):
    """Per scan face: the direction of the painted strand streaks in its texture (3D, unsigned) and how clear it is."""
    me = scan.data
    img = sw.base_color_image(me.materials[0]).copy()
    S = 2048
    img.scale(S, S)
    px = np.empty(S * S * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    Lm = (px.reshape(S, S, 4)[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)).astype(np.float64)
    gx = np.zeros_like(Lm)
    gy = np.zeros_like(Lm)
    gx[:, 1:-1] = (Lm[:, 2:] - Lm[:, :-2]) * 0.5
    gy[1:-1, :] = (Lm[2:, :] - Lm[:-2, :]) * 0.5

    def blur(a, r=5):
        for ax in (0, 1):
            for _ in range(2):
                c = np.cumsum(np.pad(a, [(r + 1, r) if k == ax else (0, 0) for k in range(2)], mode='edge'), axis=ax)
                a = (np.take(c, range(2 * r + 1, c.shape[ax]), axis=ax) - np.take(c, range(0, c.shape[ax] - 2 * r - 1), axis=ax)) / (2 * r + 1)
        return a

    Jxx, Jxy, Jyy = blur(gx * gx), blur(gx * gy), blur(gy * gy)
    theta = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy) + math.pi / 2       # along the streaks (minor eigenvector)
    tr = Jxx + Jyy
    det = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2)
    coh = np.where(tr > 1e-9, det / np.maximum(tr, 1e-12), 0.0)
    SV = sw.world_verts(scan)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2).astype(np.float64)
    ls = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", lt)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    D = np.zeros((len(me.polygons), 3))
    C = np.zeros(len(me.polygons))
    for f in np.nonzero(faces)[0]:
        l0 = ls[f]
        if lt[f] < 3:
            continue
        i0, i1, i2 = lv[l0], lv[l0 + 1], lv[l0 + 2]
        u0, u1, u2 = uv[l0], uv[l0 + 1], uv[l0 + 2]
        A = np.array([u1 - u0, u2 - u0]).T          # 2x2: columns are UV edges
        if abs(np.linalg.det(A)) < 1e-12:
            continue
        Ep = np.array([SV[i1] - SV[i0], SV[i2] - SV[i0]]).T   # 3x2
        J = Ep @ np.linalg.inv(A)                          # dP/dUV
        c = (u0 + u1 + u2) / 3
        x = int(np.clip((c[0] % 1) * S, 0, S - 1))
        y = int(np.clip((c[1] % 1) * S, 0, S - 1))
        th = theta[y, x]
        d = J @ np.array([math.cos(th), math.sin(th)])
        nd = np.linalg.norm(d)
        if nd > 1e-12:
            D[f] = d / nd
            C[f] = coh[y, x]
    return D, C


def base_flow(P, N, style, crown, part_x):
    """Root -> tip direction from a simple model of the style."""
    down = np.array([0.0, 0.0, -1.0])
    if style["flow"] == "part":
        # the part runs from the front hairline back to the crown only: in front of the crown strands leave the
        # part sideways, behind it they leave the crown radially (mostly backwards), and everything then falls.
        # No step functions: the only discontinuity left is the part itself.
        side = np.tanh((P[:, 0] - part_x) / 0.002)
        top = sw.smoothstep(crown[2] - 0.075, crown[2] - 0.01, P[:, 2])
        R = P - crown
        R[:, 2] = 0.0
        R /= np.maximum(np.linalg.norm(R, axis=1, keepdims=True), 1e-9)
        lat = side[:, None] * np.array([1.0, 0, 0])
        behind = sw.smoothstep(-0.025, 0.02, P[:, 1] - crown[1])[:, None]
        spread = lat * (1 - behind) + R * behind
        F = spread * (1.5 * top)[:, None] + down[None] * (0.35 + 0.65 * (1 - top))[:, None]
    else:
        R = P - crown
        R /= np.maximum(np.linalg.norm(R, axis=1, keepdims=True), 1e-9)
        F = R + down * 0.5
    F = F - N * np.sum(F * N, 1, keepdims=True)
    return F / np.maximum(np.linalg.norm(F, axis=1, keepdims=True), 1e-9)


def offset_mesh(obj, Dw):
    """Add world-space offsets to a mesh's vertices, in its shape keys too (the body has the face's shapes)."""
    R = np.linalg.inv(np.array(obj.matrix_world)[:3, :3])
    Dl = (Dw @ R.T).astype(np.float32)
    me = obj.data
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    me.vertices.foreach_set("co", (co.reshape(-1, 3) + Dl).ravel())
    if me.shape_keys:
        for kb in me.shape_keys.key_blocks:
            k = np.empty(len(me.vertices) * 3, np.float32)
            kb.data.foreach_get("co", k)
            kb.data.foreach_set("co", (k.reshape(-1, 3) + Dl).ravel())
    me.update()


def tuck_body(body, shell, d_hl, depth=0.004):
    """Body vertices that poke through the hair shell, or lie on it (the long-hair "cape"), go under it: 4 mm deep
    inside the hair, fading to just under it at the hairline so the feathered edge still sits on the skin. Only
    where the nearest shell point is inside the shell (not on its rim: the face, the shoulders past the tips stay).
    Smoothed a few rings outwards so the skin and cloth around do not crease. The scalp is never seen."""
    P, T, E = mesh_arrays(shell)
    sb = BVHTree.FromPolygons(P.tolist(), T.tolist(), all_triangles=True)
    BV = sw.world_verts(body)
    BE = sw.edges(body.data)
    D = np.zeros_like(BV)
    hit = np.zeros(len(BV), bool)
    for i in range(len(BV)):
        loc, n, f, d = sb.find_nearest(Vector(BV[i]), 0.03)
        if loc is None:
            continue
        v = Vector(BV[i]) - loc
        s = v.dot(n)
        if (v - n * s).length > 0.001 or s > 0.012:
            continue
        dh = float(np.mean(d_hl[T[f]]))
        de = 0.0006 + (depth - 0.0006) * float(sw.smoothstep(0.0, 0.012, dh))
        if s > -de:
            D[i] = -np.array(n) * (s + de)
            hit[i] = True
    Ds = D.copy()
    for _ in range(3):
        Ds = vec_smooth(Ds, BE, 1, lam=0.5)
        Ds[hit] = D[hit]
    offset_mesh(body, Ds)
    mv = np.linalg.norm(Ds, axis=1)
    log(f"tucked {int(hit.sum())} body vertices under the hair (max {mv.max() * 1000:.1f} mm), "
        f"{int(((mv > 1e-5) & ~hit).sum())} more eased")


def set_shading_normals(obj, w, iters=40):
    """Shading normals from a much smoother copy of the shell, mixed with its own: the clump relief stays in the
    silhouette and the AO, but the highlight follows the head's big shape (one clean sheen band broken by the
    strand grooves of the normal map) instead of fragmenting on every lump. Written as custom normals, so the
    glTF carries them to Godot (no shader work)."""
    P, T, E = mesh_arrays(obj)
    N = sw.vertex_normals(P, T)
    if w <= 0:
        return
    Ps = taubin(P, E, np.zeros(len(P), bool), iters, lam=0.6, mu=-0.62)
    Ns = sw.vertex_normals(Ps, T)
    Nm = N * (1 - w) + Ns * w
    Nm /= np.maximum(np.linalg.norm(Nm, axis=1, keepdims=True), 1e-9)
    R = np.array(obj.matrix_world.to_3x3().inverted().transposed())
    Nl = Nm @ R.T
    Nl /= np.maximum(np.linalg.norm(Nl, axis=1, keepdims=True), 1e-9)
    obj.data.normals_split_custom_set_from_vertices([tuple(v) for v in Nl])
    log(f"shading normals: {w:.2f} of a {iters}-step smoothed shell")


# ------------------------------------------------------------------ bakes
def setup_cycles(scene, samples=4):
    sw.setup_cycles(scene)
    scene.cycles.samples = samples


def bake_material(obj):
    mat = bpy.data.materials.new("protoC_bake")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    nt.links.new(em.outputs[0], out.inputs[0])
    tex = nt.nodes.new('ShaderNodeTexImage')
    nt.nodes.active = tex
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return mat, nt, em, tex


def new_float_image(name, size, alpha=True):
    img = bpy.data.images.new(name, size, size, alpha=alpha, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'
    img.generated_color = (0, 0, 0, 0)
    return img


def pixels(img):
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def bake_attr(obj, nt, em, tex, attr, size, margin=16):
    """Bake a colour attribute (or 'coverage': 1 inside the UV islands) into a float image."""
    for l in list(em.inputs[0].links):
        nt.links.remove(l)
    if attr == "coverage":
        em.inputs[0].default_value = (1, 1, 1, 1)
    else:
        an = nt.nodes.new('ShaderNodeAttribute')
        an.attribute_name = attr
        nt.links.new(an.outputs[0], em.inputs[0])
    img = new_float_image(f"bake_{attr}", size)
    tex.image = img
    nt.nodes.active = tex
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type='EMIT', margin=margin, use_clear=True)
    a = pixels(img)
    bpy.data.images.remove(img)
    return a


# ------------------------------------------------------------------ main build
def build(stem, style, work):
    cap = np.load(os.path.join(OUT, f"{stem}_capture.npz"))
    lms = {int(k): np.array(v) for k, v in zip(cap["lms_k"], cap["lms_v"])}
    long_hair = bool(cap["long_hair"])
    cid = style["cid"]
    scene = bpy.context.scene
    scan = bpy.data.objects["protoC_scan"]
    scan.hide_set(False)
    rig = next(o for o in scene.objects if o.type == 'ARMATURE')
    body = bpy.data.objects[f"{cid}_body"]
    old = next(o for o in scene.objects if "hairshell" in o.name)
    log("scan", len(scan.data.vertices), "verts; old shell", old.name, len(old.data.polygons), "faces")

    fmask, skull, bodyt, W, names, info = full_hair_mask(scan, body, rig, lms, long_hair)
    shell = build_shell(scan, fmask, f"{cid}.protoC_hair")
    D_scan, C_scan = scan_strand_dirs(scan, fmask)
    scan_hair_bvh = BVHTree.FromPolygons(sw.world_verts(scan).tolist(),
                                         [list(p.vertices) for p in scan.data.polygons], all_triangles=False)
    log("strand directions from the scan texture: coherence median", round(float(np.median(C_scan[fmask])), 2))
    # the build wrapped the body's neck and back onto the scan's long hair (the "cape"): those body triangles lie
    # ON the hair, so they are no collider for it (pushing the shell off them folded it where the cape ends).
    # In the real pipeline the full hair mask is excluded from the wrap, so the cape does not exist.
    SVs = sw.world_verts(scan)
    hair_only = BVHTree.FromPolygons(SVs.tolist(), [list(p.vertices) for p in scan.data.polygons if fmask[p.index]],
                                     all_triangles=False)
    BV = sw.world_verts(body)
    BT = sw.triangles(body.data)
    on_hair = np.zeros(len(BV), bool)
    w_head = W[:, names.index("head")]
    for i in np.nonzero((BV[:, 2] > info["z_sh"] - 0.35) & (w_head < 0.5))[0]:
        loc, _, _, d = hair_only.find_nearest(Vector(BV[i]), 0.012)
        on_hair[i] = loc is not None and d < 0.01
    # grow by two rings over the body's edges (the wrap residual leaves specks)
    BE = sw.edges(body.data)
    for _ in range(2):
        nb = np.zeros(len(BV), bool)
        nb[BE[:, 0]] |= on_hair[BE[:, 1]]
        nb[BE[:, 1]] |= on_hair[BE[:, 0]]
        on_hair |= nb & (w_head < 0.5) & (BV[:, 2] > info["z_sh"] - 0.35)
    keep_t = ~on_hair[BT].all(1)
    bodyt = BVHTree.FromPolygons(BV.tolist(), BT[keep_t].tolist(), all_triangles=True)
    log(f"cape: {int(on_hair.sum())} body vertices lie on the scan's hair; {int((~keep_t).sum())} triangles dropped "
        "from the collider")

    # smooth away the scan's crumple, then subdivide and smooth again
    P, T, E = mesh_arrays(shell)
    bnd = boundary_verts(shell)
    P = taubin(P, E, bnd, style["smooth"])
    sw.set_world_verts(shell, P)
    subdivide(shell)
    P, T, E = mesh_arrays(shell)
    bnd = boundary_verts(shell)
    P = taubin(P, E, np.zeros(len(P), bool), 4)
    # out of the skull (3 mm) and the rest of the body (4 mm): smoothed so pushed areas do not crease
    # the shell is NOT pushed out of the template's skull and body any more (every push left a fold where the
    # collider ended): the scan's own hair surface stays, and the body is tucked under it once it is final
    sw.set_world_verts(shell, P)
    log(f"shell: {len(shell.data.vertices)} verts, {len(T)} tris")
    unwrap(shell, P, E)

    P, T, E = mesh_arrays(shell)
    N = sw.vertex_normals(P, T)
    # crown: top of the hair, a little behind its middle; part: the face's centre line
    head_v = sw.world_verts(body)[W[:, names.index("head")] > 0.5]
    hc = (head_v.min(0) + head_v.max(0)) / 2
    crown = np.array([hc[0], hc[1] + 0.03 + style["crown_fwd"], P[:, 2].max()])
    part_x = float(np.mean([lms[i][0] for i in (1, 4, 6, 168) if i in lms]))
    B = base_flow(P, N, style, crown, part_x)
    # strand directions of the nearest scan face, signed root -> tip by the model
    Dv = np.zeros_like(P)
    Cv = np.zeros(len(P))
    for i in range(len(P)):
        loc, _, f, _ = scan_hair_bvh.find_nearest(Vector(P[i]), 0.05)
        if f is not None and fmask[f]:
            Dv[i] = D_scan[f]
            Cv[i] = C_scan[f]
    Dv = Dv - N * np.sum(Dv * N, 1, keepdims=True)
    Dv /= np.maximum(np.linalg.norm(Dv, axis=1, keepdims=True), 1e-9)
    Dv *= np.sign(np.sum(Dv * B, 1, keepdims=True) + 1e-12)
    w = style["data_flow"] * np.clip(Cv / 0.5, 0, 1)
    F = w[:, None] * Dv + (1 - w)[:, None] * B
    for _ in range(4):
        F = vec_smooth(F, E, 5)
        F = F - N * np.sum(F * N, 1, keepdims=True)
        F /= np.maximum(np.linalg.norm(F, axis=1, keepdims=True), 1e-9)
    log("flow: data weight mean", round(float(w.mean()), 2))

    # boundary kinds: hairline (on the scalp or skin, feathered) or free (tips in the air)
    sd_skull, _ = signed_dist(P, skull, 0.3)
    sd_body, _ = signed_dist(P, bodyt, 0.3)
    hairline = bnd & (np.minimum(sd_skull, sd_body) < 0.012) & (P[:, 2] > info["z_sh"] + 0.02)
    free = bnd & ~hairline
    d_hl = geodesic(P, E, np.nonzero(hairline)[0]) if hairline.any() else np.full(len(P), 1.0)
    d_free = geodesic(P, E, np.nonzero(free)[0]) if free.any() else np.full(len(P), 1.0)
    log(f"boundary: {int(hairline.sum())} hairline verts, {int(free.sum())} free-edge verts")

    # clump relief along the flow
    grid = FlowGrid(P, F)
    c1 = lic3(P, F, grid, style["clump_len"], style["clump_cell"], seed=11)
    c2 = lic3(P, F, grid, style["clump_len"] * 0.6, style["clump_cell"] * 0.45, seed=23)
    c = c1 / (c1.std() + 1e-9) * 0.75 + c2 / (c2.std() + 1e-9) * 0.35
    relief = np.tanh(c * 1.2)
    fade = np.clip(d_hl / 0.012, 0, 1) * (0.35 + 0.65 * sw.smoothstep(0.004, 0.02, sd_skull))   # flat at the scalp
    P = P + N * (relief * style["clump_amp"] * fade)[:, None]
    # feather the hairline onto the scalp (as feather_hair, by distance instead of rings)
    near_hl = d_hl < 0.008
    for i in np.nonzero(near_hl)[0]:
        hits = [h for h in (skull.find_nearest(Vector(P[i]), 0.1), bodyt.find_nearest(Vector(P[i]), 0.1)) if h[0] is not None]
        if hits:
            loc, n, _, _ = min(hits, key=lambda h: h[3])
            k = (1 - d_hl[i] / 0.008) ** 1.5
            P[i] = P[i] * (1 - k) + np.array(loc + n * 0.0008) * k
    sw.set_world_verts(shell, P)
    N = sw.vertex_normals(P, T)
    for p in shell.data.polygons:
        p.use_smooth = True
    tuck_body(body, shell, d_hl)

    # per-vertex data for the maps
    me = shell.data
    depth = np.clip(sd_skull, 0, 0.08)
    lo, ext = P.min(0) - 0.01, float((P.max(0) - P.min(0)).max()) + 0.02
    attrs = {
        "flow": np.c_[0.5 + 0.5 * F, np.ones(len(P))],
        "pos": np.c_[(P - lo) / ext, np.ones(len(P))],
        "nrm": np.c_[0.5 + 0.5 * N, np.ones(len(P))],
        "scal": np.c_[np.clip(d_free / 0.05, 0, 1), np.clip(d_hl / 0.03, 0, 1), depth / 0.08, 0.5 + 0.5 * relief],
    }
    for k, v in attrs.items():
        a = me.color_attributes.new(k, 'FLOAT_COLOR', 'POINT')
        a.data.foreach_set("color", v.astype(np.float32).ravel())

    # bakes
    size = style["tex"]
    setup_cycles(scene, 2)
    mat, nt, em, tex = bake_material(shell)
    maps = {}
    for k in ("coverage", "flow", "pos", "nrm", "scal"):
        maps[k] = bake_attr(shell, nt, em, tex, k, size, margin=0 if k == "coverage" else 24)
        log("baked", k)
    # colour from the scan (selected to active, from well outside: the shell moved off the scan surface)
    scan.hide_render = False
    for m in scan.data.materials:
        sw.emit_from(m, "color")
    img = bpy.data.images.new("bake_color", size, size, alpha=False, float_buffer=True)
    tex.image = img
    nt.nodes.active = tex
    bpy.ops.object.select_all(action='DESELECT')
    scan.select_set(True)
    shell.select_set(True)
    bpy.context.view_layer.objects.active = shell
    bpy.ops.object.bake(type='EMIT', use_selected_to_active=True, cage_extrusion=0.012, max_ray_distance=0.05,
                        margin=24, use_clear=True)
    maps["color"] = pixels(img)
    bpy.data.images.remove(img)
    for m in scan.data.materials:
        sw.emit_from(m, "bsdf")
    log("baked colour")
    # ambient occlusion from the head, the body and the hair itself
    scan.hide_set(True)
    scan.hide_render = True
    old.hide_render = True
    old.hide_set(True)
    scene.cycles.samples = 48
    scene.world = scene.world or bpy.data.worlds.new("w")
    scene.world.light_settings.distance = 0.025
    img = bpy.data.images.new("bake_ao", size, size, alpha=False, float_buffer=True)
    tex.image = img
    nt.nodes.active = tex
    bpy.ops.object.select_all(action='DESELECT')
    shell.select_set(True)
    bpy.context.view_layer.objects.active = shell
    bpy.ops.object.bake(type='AO', margin=24, use_clear=True)
    maps["ao"] = pixels(img)
    bpy.data.images.remove(img)
    log("baked AO")
    shell.data.materials.clear()
    bpy.data.materials.remove(mat)
    set_shading_normals(shell, style.get("nsmooth", 0.5))
    os.makedirs(work, exist_ok=True)
    np.savez(os.path.join(work, "maps.npz"), **{k: v.astype(np.float32) for k, v in maps.items()})
    json.dump(dict(style, stem=stem, long_hair=long_hair, tris=int(len(T)), pos_lo=lo.tolist(), pos_ext=ext), open(os.path.join(work, "style.json"), "w"))
    return shell, old


# ------------------------------------------------------------------ materials (EEVEE stand-in for the game shader)
def load_png(path, data):
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = 'Non-Color' if data else 'sRGB'
    return img


def hair_material(name, work, layer=None, style=None):
    """Principled BSDF: albedo, strand normal map, roughness; alpha from the tip/hairline mask (core) or a fuzz
    layer's strands. Dithered alpha (EEVEE), like alpha-hash in the game."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    alb = nt.nodes.new('ShaderNodeTexImage')
    alb.image = load_png(os.path.join(work, "albedo.png"), False)
    nrm = nt.nodes.new('ShaderNodeTexImage')
    nrm.image = load_png(os.path.join(work, "normal.png"), True)
    rgh = nt.nodes.new('ShaderNodeTexImage')
    rgh.image = load_png(os.path.join(work, "rough.png"), True)
    msk = nt.nodes.new('ShaderNodeTexImage')
    msk.image = load_png(os.path.join(work, "mask.png"), True)
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(nrm.outputs[0], nm.inputs["Color"])
    nm.inputs["Strength"].default_value = float(SHADE.get("nstr", 1.0))
    nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    sep = nt.nodes.new('ShaderNodeSeparateColor')
    nt.links.new(rgh.outputs[0], sep.inputs[0])
    radd = nt.nodes.new('ShaderNodeMath')
    radd.operation = 'ADD'
    radd.use_clamp = True
    radd.inputs[1].default_value = float(SHADE.get("radd", 0.0))
    nt.links.new(sep.outputs[0], radd.inputs[0])
    nt.links.new(radd.outputs[0], bsdf.inputs["Roughness"])
    if SHADE.get("engine", "eevee") == "cycles":
        # anisotropic GGX like Godot's ANISOTROPY_FLOW: highlight stretched across the strands (tangent = N x flow)
        at = nt.nodes.new('ShaderNodeAttribute')
        at.attribute_name = "flow"
        vm = nt.nodes.new('ShaderNodeVectorMath')
        vm.operation = 'MULTIPLY_ADD'
        nt.links.new(at.outputs["Vector"], vm.inputs[0])
        vm.inputs[1].default_value = (2.0, 2.0, 2.0)
        vm.inputs[2].default_value = (-1.0, -1.0, -1.0)
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        cr = nt.nodes.new('ShaderNodeVectorMath')
        cr.operation = 'CROSS_PRODUCT'
        nt.links.new(geo.outputs["Normal"], cr.inputs[0])
        nt.links.new(vm.outputs[0], cr.inputs[1])
        nz = nt.nodes.new('ShaderNodeVectorMath')
        nz.operation = 'NORMALIZE'
        nt.links.new(cr.outputs[0], nz.inputs[0])
        nt.links.new(nz.outputs[0], bsdf.inputs["Tangent"])
        bsdf.inputs["Anisotropic"].default_value = float(SHADE.get("aniso", 0.85))
    msep = nt.nodes.new('ShaderNodeSeparateColor')
    nt.links.new(msk.outputs[0], msep.inputs[0])
    if layer is None:
        nt.links.new(alb.outputs[0], bsdf.inputs["Base Color"])
        nt.links.new(msep.outputs[2], bsdf.inputs["Alpha"])   # B: core alpha (tips, hairline)
    else:
        # loose strands catch a little more light than the mass under them
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs[0].default_value = 1.0
        nt.links.new(alb.outputs[0], mix.inputs[6])
        mix.inputs[7].default_value = (1.05, 1.03, 1.0, 1.0)
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        lw = nt.nodes.new('ShaderNodeLayerWeight')
        lw.inputs["Blend"].default_value = 0.5
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs["From Min"].default_value = 0.1
        mr.inputs["From Max"].default_value = 0.7
        mr.inputs["To Min"].default_value = 0.3
        mr.inputs["To Max"].default_value = 1.0
        nt.links.new(lw.outputs["Facing"], mr.inputs["Value"])
        mul = nt.nodes.new('ShaderNodeMath')
        mul.operation = 'MULTIPLY'
        nt.links.new(msep.outputs[layer], mul.inputs[0])
        nt.links.new(mr.outputs[0], mul.inputs[1])
        nt.links.new(mul.outputs[0], bsdf.inputs["Alpha"])
    bsdf.inputs["IOR"].default_value = 1.55
    bsdf.inputs["Specular IOR Level"].default_value = float(SHADE.get("spec", 0.5))
    bsdf.inputs["Specular Tint"].default_value = (1.0, 0.96, 0.92, 1.0)
    bsdf.inputs["Sheen Weight"].default_value = float(SHADE.get("sheen", 0.03))
    bsdf.inputs["Sheen Roughness"].default_value = float(SHADE.get("sheenr", 0.35))
    bsdf.inputs["Sheen Tint"].default_value = (0.85, 0.8, 0.75, 1.0)
    try:
        mat.surface_render_method = 'DITHERED'
    except Exception:
        mat.blend_method = 'HASHED'
    mat.use_backface_culling = False
    return mat


def make_fuzz(shell, offsets, work):
    layers = []
    for k, off in enumerate(offsets):
        me = shell.data.copy()
        ob = bpy.data.objects.new(f"{shell.name}_fuzz{k + 1}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.matrix_world = shell.matrix_world.copy()
        P = sw.world_verts(ob)
        N = sw.vertex_normals(P, sw.triangles(me))
        sw.set_world_verts(ob, P + N * off)
        me.materials.clear()
        me.materials.append(hair_material(f"protoC_fuzz{k + 1}", work, layer=k))
        layers.append(ob)
    return layers


# ------------------------------------------------------------------ render
def setup_eevee(scene):
    for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = e
            break
        except TypeError:
            pass
    if SHADE.get("engine", "eevee") == "cycles":
        sw.setup_cycles(scene)
        scene.cycles.samples = int(SHADE.get("spp", 96))
        scene.cycles.use_denoising = True
        scene.cycles.transparent_max_bounces = 32
        scene.cycles.max_bounces = 6
        scene.cycles.use_adaptive_sampling = True
    ee = scene.eevee
    for k, v in (("taa_render_samples", 96), ("use_raytracing", True), ("use_shadows", True),
                 ("shadow_ray_count", 2), ("shadow_step_count", 8), ("use_gtao", True), ("gtao_distance", 0.05)):
        if hasattr(ee, k):
            setattr(ee, k, v)
    if hasattr(ee, "ray_tracing_options"):
        ee.ray_tracing_options.resolution_scale = '1'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'None'
    w = bpy.data.worlds.new("protoC_world")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.42, 0.43, 0.45, 1)
    bg.inputs[1].default_value = 0.45
    scene.world = w
    for o in [o for o in scene.objects if o.type == 'LIGHT']:
        bpy.data.objects.remove(o)
    for name, loc, energy, size, col in (("key", (0.9, -1.25, 2.15), 100, 0.9, (1.0, 0.96, 0.9)),
                                         ("fill", (-1.3, -0.9, 1.75), 32, 1.6, (0.9, 0.95, 1.0)),
                                         ("rim", (-0.4, 1.3, 2.0), 90, 0.7, (1.0, 1.0, 1.0)),
                                         ("rim2", (0.9, 0.9, 1.9), 45, 0.7, (1.0, 0.98, 0.95))):
        ld = bpy.data.lights.new("protoC_" + name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = col
        lo = bpy.data.objects.new("protoC_" + name, ld)
        lo.location = loc
        scene.collection.objects.link(lo)
        lo.rotation_euler = (Vector((0, 0, 1.6)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()


def render_views(scene, target, views, prefix, dist):
    cam = bpy.data.objects.get("protoC_cam") or bpy.data.objects.new("protoC_cam", bpy.data.cameras.new("protoC_cam"))
    if cam.name not in scene.collection.objects:
        scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 85
    scene.render.resolution_x = scene.render.resolution_y = 1100
    angles = {"front": 0, "face34": 38, "side": 90, "back34": 145, "back": 180}
    for v in views:
        a = math.radians(angles[v])
        c = Vector(target)
        d = Vector((math.sin(a), -math.cos(a), 0.06))
        cam.location = c + d * dist
        cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = f"{prefix}{v}.png"
        bpy.ops.render.render(write_still=True)
        log("render", os.path.relpath(scene.render.filepath, ROOT))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    stem = argv[0]
    opts = dict(a.split("=", 1) for a in argv[1:] if "=" in a)
    style = dict(STYLE[stem])
    SHADE.update({k: v for k, v in opts.items() if k in ("spec", "sheen", "sheenr", "nstr", "radd", "aniso", "engine", "spp")})
    for k, v in opts.items():
        if k in style and isinstance(style[k], (int, float)):
            style[k] = type(style[k])(v)
    cid = style["cid"]
    DEBUG["grow_rings"] = int(opts.get("grow_rings", GROW_RINGS))
    work = os.path.join(OUT, stem)
    stage = opts.get("stage", "all")
    tag = opts.get("tag", "")
    if stage == "all":
        bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, f"{stem}_capture.blend"))
        shell, old = build(stem, style, work)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, f"{stem}_hair.blend"), copy=True)
    else:
        bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, f"{stem}_hair.blend"))
        shell = bpy.data.objects[f"{cid}.protoC_hair"]
        old = next(o for o in bpy.context.scene.objects if "hairshell" in o.name)
    if opts.get("tex", "1") == "1":
        r = subprocess.run([PY, os.path.join(HERE, "proto_hair_C_tex.py"), work] +
                           [f"{k}={v}" for k, v in opts.items() if k not in ("stage", "views", "tag", "tex")],
                           capture_output=True, text=True)
        print(r.stdout[-3000:], r.stderr[-3000:])
        if r.returncode != 0:
            raise RuntimeError("proto_hair_C_tex failed")
    scene = bpy.context.scene
    fuzz = make_fuzz(shell, style["fuzz"], work)
    for o in scene.objects:
        if o.name.startswith("Icosphere") or o.name == "protoC_scan":
            o.hide_render = True
    # the body's "cape" (neck and back wrapped onto the long hair) lies under the new shell: hidden with it, as
    # cull_hidden would; the current look ("before") keeps it, it is how the long hair shows today
    body_o = bpy.data.objects[f"{cid}_body"]
    cape = None
    if "protoC_cape" in body_o.vertex_groups:
        cape = body_o.modifiers.new("protoC_cape", 'MASK')
        cape.vertex_group = "protoC_cape"
        cape.invert_vertex_group = True
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    if arm.animation_data:
        arm.animation_data.action = None
    P = sw.world_verts(shell)
    body = bpy.data.objects[f"{cid}_body"]
    V = sw.world_verts(body)
    top = float(V[:, 2].max())
    target = (float(P[:, 0].mean()), float(np.median(V[V[:, 2] > top - 0.25, 1])), top - 0.11)
    views = opts.get("views", "front,face34,back").split(",")
    dist = float(opts.get("dist", 1.05 if style["flow"] == "part" else 0.85))
    if style["flow"] == "part":
        target = (target[0], target[1], target[2] - 0.06)
    os.makedirs(REVIEW, exist_ok=True)
    for m in old.data.materials:
        b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if m and m.use_nodes else None
        if b:
            b.inputs["Roughness"].default_value = 0.66
            b.inputs["Specular IOR Level"].default_value = 0.25
    # material variants in one session: variants=name:k=v,k=v|name2:k=v (keys as the SHADE options)
    variants = [("", {})]
    if opts.get("variants"):
        variants = []
        for chunk in opts["variants"].split("|"):
            vn, _, kv = chunk.partition(":")
            variants.append((vn, dict(x.split("=", 1) for x in kv.split(",") if "=" in x)))
    base = dict(SHADE)
    before_done = set()
    for vn, vo in variants:
        SHADE.clear()
        SHADE.update(base)
        SHADE.update(vo)
        shell.data.materials.clear()
        shell.data.materials.append(hair_material("protoC_core", work))
        for k, f in enumerate(fuzz):
            f.data.materials.clear()
            f.data.materials.append(hair_material(f"protoC_fuzz{k + 1}", work, layer=k))
        setup_eevee(scene)
        eng = SHADE.get("engine", "eevee")
        etag = "" if eng == "eevee" else "_" + eng
        if opts.get("before", "1") == "1" and eng not in before_done:
            before_done.add(eng)
            if cape:
                cape.show_render = False
            shell.hide_render = True
            for f in fuzz:
                f.hide_render = True
            old.hide_render = False
            render_views(scene, target, views, os.path.join(REVIEW, f"hair_proto_C_{cid}{etag}_before_"), dist)
        shell.hide_render = False
        for f in fuzz:
            f.hide_render = False
        old.hide_render = True
        if cape:
            cape.show_render = True
        render_views(scene, target, views, os.path.join(REVIEW, f"hair_proto_C_{cid}{tag}{vn}_"), dist)
        log("variant", vn or "(base)", dict(SHADE))
    tris = [len(sw.triangles(o.data)) for o in [shell] + fuzz]
    log(f"hair: core {tris[0]} tris + {len(fuzz)} fuzz layers = {sum(tris)} tris")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, f"{stem}_render.blend"), copy=True)

if __name__ == "__main__":
    main()
