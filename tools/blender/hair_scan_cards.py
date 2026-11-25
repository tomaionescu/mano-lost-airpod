"""Hair for the scanned outfits: strand cards laid over the scan's hair shell (cast.py outfit "hair": "scan_cards").

The scan's sculpted hair (scan_wrap.segment_hair / hair_shell) carries each person's real hairstyle, but shown as a
surface it reads as a matte helmet. Here it is never shown as a surface; it is used three ways:
1. Taubin-smoothed (its crumpled clay lumps gone, its volume kept), it is the guide the cards follow;
2. that smoothed shell, 1.5 mm further in, is the underlayer seen through the gaps between cards: the scan shell
   object edited in place and renamed <id>.hairunder (kind "hairunder"), dark and matte, its colour baked here
   (the hair's root colour x a little of the shell bake's light and dark);
3. short overlapping alpha strand cards (<id>.scancards, kind "hair") cover it along a flow field for the cast
   hair_style (curly, long_part, swept, fringe), blended with the strand direction painted in the scan's own texture
   (structure tensor of the shell bake), in three layers (under / mid / top), a coverage pass (every guide vertex
   under an opaque stretch of some card), hairline cards, curl flicks and a few short flyaways.
A scalp cap (<id>.haircap, kind "haircap"): the head's hair-covered triangles 1 mm above the skin, with the head's
UVs and a mask texture of where the head's baked texture is hair (two Lab clusters learnt per person: the shell's
own colours against the forehead skin). It turns the scan's grey hairline band and the bald, hair-painted dome under
the shell into dark roots fading into the skin, without touching the face texture. A centre part is a 2-3 mm gap
baked into that mask (in head UV space: the head moves under skinning, so no world-space band in a shader).
Long hair: a face window (fitted per person to the hairline painted on the head, fit_face_window) keeps cards,
underlayer and cap off the face, strands reaching the shoulders drape to the front or the back, and everything below
the shoulders is skinned to spine_03 / spine_02.
The underlayer only stays where an opaque card lies over it (elsewhere it read as a smooth dark slab) and is pushed out
of the ears; short hair also gets hairline cards on the scalp under the shell's front lip (hair_base: hairline_cov).
Per-style options (cast "hair_cards"): fill_pits (the guide's craters closed), floor_slide / floor_arch / floor_wave
(a fringe edge the strands run along instead of ending on it), normal_r (how far the cards' shading normal is
averaged), front_len / front_y / front_det (long hair's front locks over the shoulders). Always on: glasses' arms
press the hair under them (press_under_arms) and nothing lies between a lens and the face (GlassesFront); long hair
never roots inside the mouth or below the ears; long hair beside the face lies on the skin (hug).

build_human.build() calls make() right after scan_wrap.apply(), and cap_shapes() once the face shapes are loaded
(the cap follows the brows). The inputs go to tools/out/scan_<id>/hair_guide.npz; tools/dev/hair_cards_preview.py
regrows the hair from it (or from a shipped .glb) in plain python3.11 for tuning, without Blender.
The geometry core (generate()) runs in both: mathutils BVH / KD trees inside Blender, scipy outside.
"""
import json, math, os, sys, time
import numpy as np

try:
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from mathutils.kdtree import KDTree
    BLENDER = True
except ImportError:          # plain python3.11 (tools/dev/hair_cards_preview.py)
    bpy = None
    BLENDER = False

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import hair_atlas

DOWN = np.array([0.0, 0.0, -1.0])
UP = np.array([0.0, 0.0, 1.0])
BACK = np.array([0.0, 1.0, 0.0])      # MPFB characters face -Y
XAX = np.array([1.0, 0.0, 0.0])       # the character's left
BROWS = [70, 63, 105, 66, 107, 336, 296, 334, 293, 300]
# the upper lids from the outer corner to the inner one (MediaPipe face mesh): the person's right eye, then the left
LIDS = [33, 246, 161, 160, 159, 158, 157, 173, 133, 263, 466, 388, 387, 386, 385, 384, 398, 362]


def log(*a):
    print("[hair]", *a, flush=True)


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, np.float64) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def unit(v):
    v = np.asarray(v, np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def vlen(v):
    return math.sqrt(float(v[0]) * float(v[0]) + float(v[1]) * float(v[1]) + float(v[2]) * float(v[2]))


def hash01(p):
    """A repeatable value in [0, 1) from a point: for draws that must not take from the build's random sequence
    (a rule that adds a draw there reshuffles every card grown after it, and the hair comes out as a new random
    draw with its own new defects)."""
    x = math.sin(float(p[0]) * 12.9898e3 + float(p[1]) * 78.233e3 + float(p[2]) * 37.719e3) * 43758.5453
    return x - math.floor(x)


def vunit(v):
    n = vlen(v)
    return v / n if n > 1e-12 else v


def ortho(n):
    a = XAX if abs(n[0]) < 0.9 else BACK
    return vunit(np.cross(n, a))


def rotate(v, k, ang):
    """v turned by ang about the unit axis k (Rodrigues)."""
    c, s = math.cos(ang), math.sin(ang)
    return v * c + np.cross(k, v) * s + k * (float(np.dot(k, v)) * (1.0 - c))


def lin(hexstr):
    return tuple(float(x) for x in hair_atlas.hex_lin(hexstr))


# ------------------------------------------------------------------ styles
# Per cast hair_style, overridable per outfit with "hair_cards": {...} (cast.py). Lengths in metres.
# layer = (name, cards per m^2 of guide, length range (None: long hair, down to max_len), width range, lift range
# above the guide, tone (depth AO, 0.25-1) range, atlas strips, root fade (fraction of the card))
# short hair's bare-scalp guide over the skin (the cap lies 1 mm over it)
GUIDE_LIFT = 0.002
_SHORT_HAIRLINE = dict(step=0.0026, iso=0.2, length=(0.022, 0.042), width=(0.007, 0.011), strips=(2, 3, 4),
                       tone=(0.72, 0.95))
STYLES = {
    # curly: loose curls, fuller on top, ears half covered
    "curly": dict(
        flow="curly", atlas="curly", long=False, smooth=10, tex_w=0.4, nape=-0.085, front_floor=-0.006, ear_free=0.026,
        # flow: out from a point just in front of and below the forehead hairline (up and back over the top, back
        # and down the sides), gravity below the top
        origin=(0.0, -0.012, 0.045), gravity=0.6, seg=0.0065,
        curl=dict(wave=(0.032, 0.044), wiggle=0.2, lift=0.0026, twist=0.3, jitter=0.5),
        free_max=0.014,
        layers=[
            ("under", 4600, (0.05, 0.07), (0.018, 0.026), (0.0004, 0.0014), (0.26, 0.38), (0, 1, 2), 0.25),
            ("mid", 5200, (0.06, 0.085), (0.014, 0.02), (0.0015, 0.004), (0.5, 0.68), (0, 1, 2, 3, 4), 0.25),
            ("top", 3000, (0.06, 0.09), (0.016, 0.024), (0.0032, 0.0065), (0.82, 1.0), (2, 3, 4, 5, 6), 0.3),
        ],
        hairline=dict(step=0.0022, iso=0.18, length=(0.025, 0.05), width=(0.008, 0.013), strips=(2, 3, 4),
                      tone=(0.75, 1.0)),
        cover=0.006,
        loops=dict(count_per_m2=1100, length=(0.035, 0.06), width=(0.008, 0.013), bulge=(0.006, 0.014),
                   strips=(4, 5, 6)),
        # few and short: long thin flyaways read as spider-web lines against a dark background
        fly=dict(count=80, length=(0.03, 0.055), width=(0.005, 0.008), bulge=(0.003, 0.01)),
    ),
    # long_part: long straight hair, centre part, past the shoulders
    "long_part": dict(
        flow="long_part", atlas="straight", long=True, smooth=30, tex_w=0.15,
        part=((0.0, -0.075, 0.0), (0.0, 0.035, 0.0)), gravity=1.6, seg=0.02, free_max=0.07, max_len=0.75,
        fill_len=0.35, end_trim=0.1, face_window=True, drape=True, front_drop=1.0, taper=0.35, deflate=0.007,
        layers=[
            ("under", 1700, None, (0.026, 0.036), (0.0008, 0.0022), (0.36, 0.5), (0, 1), 0.3),
            ("mid", 1900, None, (0.017, 0.025), (0.0026, 0.005), (0.62, 0.8), (0, 1, 2, 3), 0.3),
            ("top", 1500, None, (0.011, 0.017), (0.0045, 0.008), (0.88, 1.0), (2, 3, 4, 5, 6), 0.3),
        ],
        hairline=dict(step=0.004, iso=0.4, length=None, width=(0.007, 0.012), strips=(2, 3, 4, 5),
                      tone=(0.7, 0.9)),
        cover=0.009,
        fly=dict(count=40, length=(0.05, 0.1), width=(0.004, 0.007), bulge=(0.003, 0.01)),
    ),
    # swept (and, with "flow": "side_swept", a side part): short hair swept up and back from the forehead
    "swept": dict(
        flow="swept", atlas="short", long=False, smooth=10, tex_w=0.6, nape=-0.08, front_floor=0.012, ear_free=0.02,
        part_x=0.0, spread=2.5, lift=0.9, sweep=0.9, gravity=0.55, seg=0.0075,
        curl=dict(wave=(0.07, 0.1), wiggle=0.1, lift=0.0012, twist=0.12, jitter=1.0),
        free_max=0.012,
        layers=[
            ("under", 4200, (0.05, 0.07), (0.016, 0.024), (0.0004, 0.0013), (0.28, 0.4), (0, 1, 2), 0.25),
            ("mid", 4800, (0.055, 0.08), (0.013, 0.019), (0.0014, 0.0035), (0.52, 0.7), (0, 1, 2, 3, 4), 0.25),
            ("top", 2800, (0.055, 0.085), (0.011, 0.017), (0.003, 0.006), (0.82, 1.0), (2, 3, 4, 5, 6), 0.3),
        ],
        hairline=_SHORT_HAIRLINE, cover=0.006,
        fly=dict(count=50, length=(0.03, 0.05), width=(0.004, 0.007), bulge=(0.002, 0.008)),
    ),
    # fringe: thick straight hair, a heavy fringe down to the brows, sides over the tops of the ears
    "fringe": dict(
        flow="fringe", atlas="short", long=False, smooth=10, tex_w=0.5, nape=-0.085, front_floor=0.002,
        crown=(0.0, 0.03, 0.012), sweep=0.08, gravity=0.85, seg=0.0075, curl=None, free_max=0.012,
        layers=[
            ("under", 4400, (0.055, 0.075), (0.016, 0.024), (0.0004, 0.0013), (0.26, 0.38), (0, 1, 2), 0.25),
            ("mid", 5000, (0.06, 0.085), (0.013, 0.019), (0.0014, 0.0035), (0.5, 0.68), (0, 1, 2, 3, 4), 0.25),
            ("top", 3000, (0.065, 0.095), (0.011, 0.017), (0.003, 0.006), (0.82, 1.0), (2, 3, 4, 5, 6), 0.3),
        ],
        hairline=_SHORT_HAIRLINE, cover=0.006,
        fly=dict(count=40, length=(0.03, 0.05), width=(0.004, 0.007), bulge=(0.002, 0.008)),
    ),
}


def style_for(spec, outfit):
    """The style preset for a cast entry and outfit, with its colours (linear RGB): root and tip of the strands
    (the cast's hair_colors unless the outfit's hair_cards overrides them) and the underlayer's colour."""
    name = spec.get("hair_style") or "curly"
    over = dict(spec["outfits"][outfit].get("hair_cards") or {})
    st = json.loads(json.dumps(STYLES.get(over.get("style", name), STYLES["curly"])))
    st["name"] = over.pop("style", name)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(st.get(k), dict):
            st[k].update(v)
        elif k not in ("root", "tip", "under"):
            st[k] = v
    cols = spec.get("hair_colors") or {"root": lin("#0e0907"), "tip": lin("#2a1c14")}
    st["root"] = lin(over["root"]) if "root" in over else tuple(cols["root"])
    st["tip"] = lin(over["tip"]) if "tip" in over else tuple(cols["tip"])
    st["under"] = lin(over["under"]) if "under" in over else tuple(min(1.0, c * 1.5) for c in st["root"])
    st["layers"] = [tuple(tuple(x) if isinstance(x, list) else x for x in layer) for layer in st["layers"]]
    return st


# ------------------------------------------------------------------ geometry backends
def vertex_normals(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], fn)
    return unit(N)


class Points:
    """Nearest neighbours in a point set (mathutils KDTree in Blender, scipy outside)."""

    def __init__(self, P):
        self.P = np.ascontiguousarray(P, np.float64).reshape(-1, 3)
        if BLENDER:
            self.kd = KDTree(max(len(self.P), 1))
            for i, p in enumerate(self.P.tolist()):
                self.kd.insert(p, i)
            self.kd.balance()
        elif len(self.P):
            from scipy.spatial import cKDTree
            self.kd = cKDTree(self.P)

    def nearest(self, Q):
        Q = np.asarray(Q, np.float64).reshape(-1, 3)
        if not len(self.P):
            return np.full(len(Q), np.inf), np.full(len(Q), -1, np.int64)
        if BLENDER:
            d = np.empty(len(Q))
            i = np.empty(len(Q), np.int64)
            for k, q in enumerate(Q.tolist()):
                _, idx, dist = self.kd.find(q)
                d[k], i[k] = (dist, idx) if idx is not None else (np.inf, -1)
            return d, i
        d, i = self.kd.query(Q)
        return np.asarray(d, np.float64), np.asarray(i, np.int64)

    def near_n(self, q, n):
        """[(index, distance)] of the n nearest points to q."""
        if not len(self.P):
            return []
        if BLENDER:
            return [(i, d) for _, i, d in self.kd.find_n(list(map(float, q)), n)]
        d, i = self.kd.query(q, k=min(n, len(self.P)))
        return list(zip(np.atleast_1d(i).tolist(), np.atleast_1d(d).tolist()))

    def within(self, q, r):
        """[(index, distance)] of the points within r of q."""
        if not len(self.P):
            return []
        if BLENDER:
            return [(i, d) for _, i, d in self.kd.find_range(list(map(float, q)), r)]
        idx = self.kd.query_ball_point(q, r)
        return [(i, float(np.linalg.norm(self.P[i] - q))) for i in idx]


def closest_on_tris(p, A, B, C):
    """Closest points to p on triangles (k, 3 each) and their barycentric weights (Ericson, vectorised)."""
    ab, ac, ap = B - A, C - A, p - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - B
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - C
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = va + vb + vc
    den = np.where(np.abs(den) < 1e-20, 1e-20, den)
    v, w = vb / den, vc / den
    bc = np.stack([1 - v - w, v, w], 1)

    def ratio(a, b):
        ok = np.abs(b) > 1e-20
        return np.clip(np.where(ok, a / np.where(ok, b, 1.0), 0.0), 0.0, 1.0)

    # in reverse order of Ericson's early returns, so the first matching region wins
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    t = ratio(d4 - d3, (d4 - d3) + (d5 - d6))
    bc[m] = np.stack([np.zeros(m.sum()), 1 - t[m], t[m]], 1)
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t = ratio(d2, d2 - d6)
    bc[m] = np.stack([1 - t[m], np.zeros(m.sum()), t[m]], 1)
    m = (d6 >= 0) & (d5 <= d6)
    bc[m] = (0.0, 0.0, 1.0)
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t = ratio(d1, d1 - d3)
    bc[m] = np.stack([1 - t[m], t[m], np.zeros(m.sum())], 1)
    m = (d3 >= 0) & (d4 <= d3)
    bc[m] = (0.0, 1.0, 0.0)
    m = (d1 <= 0) & (d2 <= 0)
    bc[m] = (1.0, 0.0, 0.0)
    bad = ~np.isfinite(bc).all(1)
    bc[bad] = (1.0, 0.0, 0.0)
    Q = A * bc[:, :1] + B * bc[:, 1:2] + C * bc[:, 2:3]
    return Q, bc


def barycentric(p, tri):
    a, b, c = tri
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-24:
        return np.array([1.0, 0.0, 0.0])
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return np.array([1.0 - v - w, v, w])


class Mesh:
    """Closest points and ray hits on a triangle mesh; N: per-vertex shading normals (default: area-weighted)."""

    def __init__(self, V, T, N=None):
        self.V = np.ascontiguousarray(V, np.float64).reshape(-1, 3)
        self.T = np.ascontiguousarray(T, np.int64).reshape(-1, 3)
        fn = np.cross(self.V[self.T[:, 1]] - self.V[self.T[:, 0]], self.V[self.T[:, 2]] - self.V[self.T[:, 0]])
        self.area = 0.5 * np.linalg.norm(fn, axis=1)
        self.FN = unit(fn)
        self.N = vertex_normals(self.V, self.T) if N is None else N
        if BLENDER:
            self.bvh = BVHTree.FromPolygons(self.V.tolist(), self.T.tolist(), all_triangles=True)
        else:
            from scipy.spatial import cKDTree
            self.C = self.V[self.T].mean(1)
            self.kd = cKDTree(self.C)
            self.k = min(16, len(self.T))

    def nearest(self, p, maxd=0.2):
        """(location, triangle, barycentric weights, distance) of the closest surface point, or None."""
        if BLENDER:
            loc, _, idx, d = self.bvh.find_nearest(Vector((float(p[0]), float(p[1]), float(p[2]))), maxd)
            if loc is None:
                return None
            loc = np.array(loc)
            return loc, idx, barycentric(loc, self.V[self.T[idx]]), d
        _, cand = self.kd.query(p, k=self.k)
        cand = np.atleast_1d(cand)
        tri = self.T[cand]
        Q, bc = closest_on_tris(np.asarray(p, np.float64), self.V[tri[:, 0]], self.V[tri[:, 1]], self.V[tri[:, 2]])
        dd = np.linalg.norm(Q - p, axis=1)
        j = int(np.argmin(dd))
        if dd[j] > maxd:
            return None
        return Q[j], int(cand[j]), bc[j], float(dd[j])

    def normal_at(self, tri, bc):
        n = bc @ self.N[self.T[tri]]
        ln = vlen(n)
        return n / ln if ln > 1e-9 else self.FN[tri].copy()

    def crossings(self, o, d, maxn=24):
        """How many times a ray from o along d crosses the mesh (odd: o is inside a closed surface)."""
        if BLENDER:
            n, o = 0, Vector((float(o[0]), float(o[1]), float(o[2])))
            d = Vector((float(d[0]), float(d[1]), float(d[2]))).normalized()
            while n < maxn:
                loc = self.bvh.ray_cast(o, d)[0]
                if loc is None:
                    break
                n += 1
                o = loc + d * 1e-5
            return n
        A, B, C = self.V[self.T[:, 0]], self.V[self.T[:, 1]], self.V[self.T[:, 2]]
        e1, e2 = B - A, C - A
        pv = np.cross(d, e2)
        det = (e1 * pv).sum(1)
        ok = np.abs(det) > 1e-14
        inv = 1.0 / np.where(ok, det, 1.0)
        tv = o - A
        u = (tv * pv).sum(1) * inv
        qv = np.cross(tv, e1)
        v = (qv @ d) * inv
        t = (e2 * qv).sum(1) * inv
        return int((ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-7)).sum())

    def inside(self, p):
        """Inside a closed surface, by ray parity along two directions (both must agree)."""
        return self.crossings(p, np.array([1.0, 1.3e-4, 2.1e-4])) % 2 == 1 and \
            self.crossings(p, np.array([-2.2e-4, 1.1e-4, 1.0])) % 2 == 1

    def ray_hits(self, O, D, maxd):
        """Per ray: does it hit the mesh within maxd?"""
        O = np.asarray(O, np.float64).reshape(-1, 3)
        D = np.asarray(D, np.float64).reshape(-1, 3)
        if BLENDER:
            return np.array([self.bvh.ray_cast(Vector(o), Vector(d), maxd)[0] is not None
                             for o, d in zip(O.tolist(), D.tolist())], bool)
        A, B, C = self.V[self.T[:, 0]], self.V[self.T[:, 1]], self.V[self.T[:, 2]]
        e1, e2 = B - A, C - A
        out = np.zeros(len(O), bool)
        for s in range(0, len(O), 64):
            o, d = O[s:s + 64, None, :], D[s:s + 64, None, :]
            pv = np.cross(d, e2[None])
            det = (e1[None] * pv).sum(-1)
            ok = np.abs(det) > 1e-14
            inv = 1.0 / np.where(ok, det, 1.0)
            tv = o - A[None]
            u = (tv * pv).sum(-1) * inv
            qv = np.cross(tv, e1[None])
            v = (d * qv).sum(-1) * inv
            t = (e2[None] * qv).sum(-1) * inv
            hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0) & (t < maxd)
            out[s:s + 64] = hit.any(1)
        return out


def smooth_normals(V, N, radius):
    """Vertex normals averaged over a radius (Gaussian, same-facing only): the hair volume's normal."""
    pts = Points(V)
    out = np.empty_like(N)
    for i, v in enumerate(V):
        acc = np.zeros(3)
        for j, d in pts.within(v, radius):
            if N[j] @ N[i] > 0.0:
                acc += N[j] * math.exp(-(d / (0.5 * radius)) ** 2)
        ln = vlen(acc)
        out[i] = acc / ln if ln > 1e-12 else N[i]
    return out


class Surface(Mesh):
    """The guide the cards follow: smoothed (volume) normals, area-weighted sampling."""

    def __init__(self, V, T, normal_r=0.012):
        V = np.ascontiguousarray(V, np.float64)
        super().__init__(V, T, smooth_normals(V, vertex_normals(V, np.asarray(T, np.int64)), normal_r))

    def nearest_n(self, p, maxd=0.2):
        r = self.nearest(p, maxd)
        if r is None:
            return None
        loc, tri, bc, d = r
        return loc, self.normal_at(tri, bc), d, tri, bc

    def sample(self, count, rng, weight=None):
        p = self.area * (weight if weight is not None else 1.0)
        p = p / p.sum()
        tri = rng.choice(len(self.T), size=count, p=p)
        r1, r2 = rng.random(count), rng.random(count)
        s = np.sqrt(r1)
        bc = np.stack([1 - s, s * (1 - r2), s * r2], 1)
        return (self.V[self.T[tri]] * bc[:, :, None]).sum(1), tri


def weld_map(V, T):
    """glTF and the scan split vertices along UV seams: merge exact duplicates. Returns the welded vertices and
    triangles, and the map from the original vertices to the welded ones."""
    key = np.round(np.asarray(V) * 1e5).astype(np.int64)
    _, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    return np.asarray(V)[idx], inv[T], inv


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


def boundary_edges(T):
    """Boundary edges (n, 2) of a triangle mesh, the triangle each belongs to, and that triangle's third vertex."""
    E = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    opp = np.concatenate([T[:, 2], T[:, 0], T[:, 1]])
    tri = np.tile(np.arange(len(T)), 3)
    key = np.sort(E, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    b = cnt[inv.reshape(-1)] == 1
    return E[b], tri[b], opp[b]


def tri_components(T):
    """Connected component label per triangle (sharing a vertex), union-find in plain numpy/python."""
    T = np.asarray(T, np.int64).reshape(-1, 3)
    if not len(T):
        return np.zeros(0, np.int64)
    ids, inv = np.unique(T, return_inverse=True)
    inv = inv.reshape(-1, 3)
    par = list(range(len(ids)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    for a, b, c in inv.tolist():
        ra, rb, rc = find(a), find(b), find(c)
        par[rb] = ra
        par[find(rc)] = ra
    roots = np.array([find(t[0]) for t in inv.tolist()])
    _, lab = np.unique(roots, return_inverse=True)
    return lab.reshape(-1)


def fill_pits(V, T, body, head_V, fr, st, radius):
    """The guide's pits filled: the scan sculpts some hair as a curl or a crater whose floor reaches the scalp
    (Ian: a 2.5 cm wide pit 4 cm deep at the front of the top); the cards followed it down and it read as a hole
    in the hair, with the cards' edges ringing it. The guide's height over the scalp (a height field on the skin)
    is closed morphologically (dilate, then erode, both over `radius`): a pit or a groove narrower than 2 x radius
    fills up to its rim, the outline and the hairline keep their own height (the bare skin around the hair counts
    as height 0, so the closing never raises an edge). Never within ~1.5 cm of the shell's edge (its lip curls
    under: raised, it would stand off the forehead as a ledge), never at a centre part (its groove is the part).
    Returns the vertices and how many moved more than 2 mm."""
    V = np.array(V, np.float64)
    F = np.empty_like(V)
    h = np.zeros(len(V))
    for i, v in enumerate(V):
        r = body.nearest(v, 0.2)
        if r is None:
            F[i], h[i] = v, 0.0
        else:
            F[i], h[i] = r[0], r[3]
    u = V - F
    ln = np.linalg.norm(u, axis=1)
    u = np.where(ln[:, None] > 1e-6, u / np.maximum(ln, 1e-9)[:, None], 0.0)
    # the bare skin around the hair: height 0
    dF, _ = Points(F).nearest(head_V)
    Z = head_V[dF > 0.004]
    S = np.concatenate([F, Z])
    hS = np.concatenate([h, np.zeros(len(Z))])
    pts = Points(S)
    dil = np.array([max([hS[i]] + [hS[j] for j, _ in pts.within(p, radius)]) for i, p in enumerate(S)])
    clo = np.array([min([dil[i]] + [dil[j] for j, _ in pts.within(p, radius)]) for i, p in enumerate(F)])
    # where it may fill: away from the shell's edge, off a centre part
    E, _, _ = boundary_edges(T)
    bd, _ = Points(V[np.unique(E)]).nearest(V) if len(E) else (np.full(len(V), 1.0), None)
    # near the edge only what faces the skin (the lip's underside) keeps its height: a pit right behind the
    # hairline (Ian's) faces out like the rest of the top and fills
    N = vertex_normals(V, np.asarray(T, np.int64))
    nu = (N * u).sum(1)
    nu = nu * (1.0 if np.median(nu) >= 0 else -1.0)
    w = np.maximum(smoothstep(0.006, 0.015, bd), smoothstep(0.1, 0.5, nu))
    if st.get("flow") == "curtain" or st.get("part"):
        c = fr["centre"]
        w = w * (1.0 - (1.0 - smoothstep(0.008, 0.02, np.abs(V[:, 0] - (c[0] + st.get("part_x", 0.0))))) *
                 (1.0 - smoothstep(0.02, 0.045, V[:, 1] - c[1])) * smoothstep(0.03, 0.05, V[:, 2] - fr["eye"][2]))
    rise = np.clip(clo - h, 0.0, 0.03) * w
    V2 = F + u * (h + rise)[:, None]
    ok = ln > 1e-6
    V[ok] = V2[ok]
    # blend the filled stretches into their surroundings
    Vs = taubin(V, T, 4)
    m = smoothstep(0.0, 0.004, rise)
    V = V + (Vs - V) * m[:, None]
    return V, int((rise > 0.002).sum()), float(rise.max())


def glasses_arms(coll, fr, body, rng):
    """The glasses' temple arms where they run over the hair (behind the frame's front, beside the head, from the
    hinge back to the top of the ear): sample points' feet on the skin and the arm's underside height over it."""
    if coll is None or not len(coll.T):
        return None
    p = coll.area / max(float(coll.area.sum()), 1e-12)
    tri = rng.choice(len(coll.T), size=8000, p=p)
    r1, r2 = rng.random(len(tri)), rng.random(len(tri))
    s = np.sqrt(r1)
    bc = np.stack([1 - s, s * (1 - r2), s * r2], 1)
    S = (coll.V[coll.T[tri]] * bc[:, :, None]).sum(1)
    e, ef = fr["eye"], fr["eye_front"]
    ear_y = float(fr["ears"][:, 1].max())
    # (to the top of the ear only: pressed under the earpiece behind the ear too, the hair there left it bare,
    # a dark bar with a dotted highlight across the hair seen from behind)
    S = S[(S[:, 1] > ef + 0.012) & (S[:, 1] < ear_y + 0.03) & (np.abs(S[:, 0] - e[0]) > 0.045)]
    if not len(S):
        return None
    F = np.empty_like(S)
    h = np.empty(len(S))
    for i, q in enumerate(S):
        r = body.nearest(q, 0.08)
        F[i], h[i] = (r[0], r[3]) if r is not None else (q, 1.0)
    pts = Points(F)
    hu = np.array([min([h[i]] + [h[j] for j, _ in pts.within(f, 0.0025)]) for i, f in enumerate(F)])
    # not where the arm rests on the ear (its foot on the helix, its underside 0-1 mm over it): there is no room for
    # hair under it, and the hair over the ear's top pressed to under it lay on the helix as a black clump with the
    # skin showing through (Mano, at the end of his left arm). Hair over the ear stays over the arm there
    on_ear = ear_weight(F, fr, 0.02, 0.03) > 0.5
    if on_ear.all():
        return None
    F, hu = F[~on_ear], hu[~on_ear]
    return dict(F=F, H=hu, pts=Points(F), lo=F.min(0) - 0.03, hi=F.max(0) + 0.03, fr=fr)


class GlassesFront:
    """The front of the glasses (lenses and frame, not the arms) as a height field seen from the front: per cell of
    a 0.75 mm grid in x and z, the front-most y. A fringe that comes down to the glasses lies in front of them:
    between the lens and the face (Mano's lenses sit 1-9 mm off it) the cards were cut along the lens outline
    by the lens drawn over them, a dark slab with the lens's curve for its lower edge."""

    def __init__(self, coll, fr, cell=0.00075):
        e, ef = fr["eye"], fr["eye_front"]
        cen = coll.V[coll.T].mean(1)
        T = coll.T[(cen[:, 1] < ef + 0.02) & (np.abs(cen[:, 0] - e[0]) < 0.075)]
        self.x0, self.z0, self.cell = e[0] - 0.085, e[2] - 0.05, cell
        n = int(0.17 / cell) + 1
        self.Y = np.full((n, n), np.inf)
        for t in T:
            P = coll.V[t]
            u = (P[:, 0] - self.x0) / cell
            v = (P[:, 2] - self.z0) / cell
            i0, i1 = max(int(np.floor(u.min())), 0), min(int(np.ceil(u.max())), n - 1)
            j0, j1 = max(int(np.floor(v.min())), 0), min(int(np.ceil(v.max())), n - 1)
            if i1 < i0 or j1 < j0:
                continue
            us, vs = np.meshgrid(np.arange(i0, i1 + 1) + 0.5, np.arange(j0, j1 + 1) + 0.5, indexing="ij")
            den = (v[1] - v[2]) * (u[0] - u[2]) + (u[2] - u[1]) * (v[0] - v[2])
            if abs(den) < 1e-12:
                continue
            l0 = ((v[1] - v[2]) * (us - u[2]) + (u[2] - u[1]) * (vs - v[2])) / den
            l1 = ((v[2] - v[0]) * (us - u[2]) + (u[0] - u[2]) * (vs - v[2])) / den
            l2 = 1 - l0 - l1
            m = (l0 >= -0.05) & (l1 >= -0.05) & (l2 >= -0.05)
            if not m.any():
                continue
            y = l0 * P[0, 1] + l1 * P[1, 1] + l2 * P[2, 1]
            sub = self.Y[i0:i1 + 1, j0:j1 + 1]
            self.Y[i0:i1 + 1, j0:j1 + 1] = np.where(m, np.minimum(sub, y), sub)
        # a cell and a half of margin round the outline
        Yd = self.Y.copy()
        for di in (-2, -1, 1, 2):
            Yd = np.minimum(Yd, np.roll(self.Y, di, 0))
        Y2 = Yd.copy()
        for dj in (-2, -1, 1, 2):
            Y2 = np.minimum(Y2, np.roll(Yd, dj, 1))
        self.Y = Y2
        self.n = n
        self.ef = ef

    def front_y(self, q):
        i = int((q[0] - self.x0) / self.cell)
        j = int((q[2] - self.z0) / self.cell)
        if not (0 <= i < self.n and 0 <= j < self.n):
            return None
        y = self.Y[i, j]
        return float(y) if np.isfinite(y) else None

    def shift(self, q, gap=0.0015, reach=0.004, far=0.008):
        """How far q must come forward to lie `gap` in front of the glasses. Only what is just behind them moves
        (between a lens and the face there is at most a few mm): hair 1-3 cm behind the frame's outer corners and
        hinges is the temple's, beside the head, and pulled onto the frame's front plane it lay flat across the
        lens corner as a dark sheet. Fades out from `reach` to `far` behind the front."""
        y = self.front_y(q)
        if y is None or q[1] > self.ef + 0.03:
            return 0.0
        need = float(q[1] - (y - gap))
        if need <= 0.0:
            return 0.0
        return need * (1.0 - float(smoothstep(reach, far, need)))

    def keep_front(self, q, gap=0.0015):
        """q moved in front of the glasses if it is just behind them (between them and the face)."""
        s = self.shift(q, gap)
        if s <= 0.0:
            return q, False
        q = np.array(q, np.float64)
        q[1] -= s
        return q, True


class EarSide:
    """The ears as height fields seen from the side: per 1 mm cell in y and z, how far out (sideways, from the face's
    middle) the ear reaches. Hair hanging free over an ear (style ear_drape) lies on its outside: falling from the
    shell's edge (cut 6 mm round the ear, scan_wrap.clear_ears) it hung down between the ear and the skull, behind
    the ear's rim, and the rim's top showed as a bare faceted skin peak poking up into the hair (Mano: his hair falls
    over the tops of his ears)."""

    def __init__(self, V, T, fr, cell=0.001):
        self.cx, self.cell = float(fr["eye"][0]), cell
        w = ear_weight(V, fr, 0.02, 0.03)
        self.sides = []
        for t in fr["ears"]:
            side = 1.0 if t[0] >= self.cx else -1.0
            sel = T[(w[T] > 0.5).all(1) & ((V[T][:, :, 0] - self.cx) * side > 0).all(1)]
            if not len(sel):
                continue
            P = V[sel]
            y0, z0 = float(P[:, :, 1].min()) - 0.003, float(P[:, :, 2].min()) - 0.003
            ny = int((float(P[:, :, 1].max()) + 0.003 - y0) / cell) + 1
            nz = int((float(P[:, :, 2].max()) + 0.003 - z0) / cell) + 1
            H = np.full((ny, nz), -np.inf)
            for tri in P:
                u = (tri[:, 1] - y0) / cell
                v = (tri[:, 2] - z0) / cell
                lat = (tri[:, 0] - self.cx) * side
                i0, i1 = max(int(np.floor(u.min())), 0), min(int(np.ceil(u.max())), ny - 1)
                j0, j1 = max(int(np.floor(v.min())), 0), min(int(np.ceil(v.max())), nz - 1)
                if i1 < i0 or j1 < j0:
                    continue
                us, vs = np.meshgrid(np.arange(i0, i1 + 1) + 0.5, np.arange(j0, j1 + 1) + 0.5, indexing="ij")
                den = (v[1] - v[2]) * (u[0] - u[2]) + (u[2] - u[1]) * (v[0] - v[2])
                if abs(den) < 1e-12:
                    continue
                l0 = ((v[1] - v[2]) * (us - u[2]) + (u[2] - u[1]) * (vs - v[2])) / den
                l1 = ((v[2] - v[0]) * (us - u[2]) + (u[0] - u[2]) * (vs - v[2])) / den
                l2 = 1 - l0 - l1
                m = (l0 >= -0.05) & (l1 >= -0.05) & (l2 >= -0.05)
                if not m.any():
                    continue
                x = l0 * lat[0] + l1 * lat[1] + l2 * lat[2]
                sub = H[i0:i1 + 1, j0:j1 + 1]
                H[i0:i1 + 1, j0:j1 + 1] = np.where(m, np.maximum(sub, x), sub)
            self.sides.append((side, y0, z0, H))

    def below(self, q, depth=0.012):
        """Whether an ear lies under q (within `depth` straight down, on q's side)."""
        for side, y0, z0, H in self.sides:
            if (q[0] - self.cx) * side <= 0:
                continue
            i = int((q[1] - y0) / self.cell)
            if not 0 <= i < H.shape[0]:
                return False
            j1 = int((q[2] - z0) / self.cell)
            j0 = int((q[2] - depth - z0) / self.cell)
            j0, j1 = max(j0, 0), min(j1, H.shape[1] - 1)
            return j1 >= j0 and bool(np.isfinite(H[i, j0:j1 + 1]).any())
        return False

    def drape(self, q, clear=0.0015):
        """(q moved out sideways onto the ear's outside if it lies over an ear and inside its outer surface,
        whether it lies on an ear)."""
        for side, y0, z0, H in self.sides:
            if (q[0] - self.cx) * side <= 0:
                continue
            i, j = int((q[1] - y0) / self.cell), int((q[2] - z0) / self.cell)
            if not (0 <= i < H.shape[0] and 0 <= j < H.shape[1]) or not np.isfinite(H[i, j]):
                return q, False
            out = float(H[i, j]) + clear
            if (q[0] - self.cx) * side < out:
                q = np.array(q, np.float64)
                q[0] = self.cx + side * out
            return q, True
        return q, False


def press_under_arms(P, arms, body, clear=0.0008, band=0.0035, slope=0.9, under=False):
    """Hair under the glasses' arms: the arms rest 2-4 mm off the skin at the temples, and the hair there (the
    scan's volume, 1-2 cm) swallowed them from the hinge to behind the ear. Within `band` of an arm's
    foot on the skin, hair is pressed to just under it; away from it, it rises back at `slope` (a groove, as
    glasses press real hair down). under: the underlayer, flat under the lowest a pressed card comes (half the
    cards' height). Returns the points and a mask of those moved."""
    P = np.array(P, np.float64)
    moved = np.zeros(len(P), bool)
    if arms is None or not len(P):
        return P, moved
    near = np.nonzero((P >= arms["lo"]).all(1) & (P <= arms["hi"]).all(1))[0]
    for i in near:
        r = body.nearest(P[i], 0.05)
        if r is None:
            continue
        foot = r[0]
        # (hair over the ear is never pressed onto it: see glasses_arms)
        if "fr" in arms and ear_weight(foot[None], arms["fr"], 0.02, 0.03)[0] > 0.5:
            continue
        d, j = arms["pts"].nearest(foot)
        d, j = float(d[0]), int(j[0])
        if d > band + 0.025:
            continue
        cap = max(float(arms["H"][j]) - clear, 0.0012) + max(0.0, d - band) * slope
        off = P[i] - foot
        h = vlen(off)
        # compressed, not cut off: the layers keep their order (all pressed to the same height, under and top
        # cards lay in one plane and fought, a mottle of flat dark and light patches on the sideburn)
        k = 0.5 * cap
        if under:
            k = max(k - 0.0003, 0.0005)
            if h > k and h > 1e-6:
                P[i] = foot + off / h * k
                moved[i] = True
            continue
        if h > k and h > 1e-6:
            h2 = k + k * (1.0 - math.exp(-(h - k) / k))
            P[i] = foot + off / h * h2
            moved[i] = True
    return P, moved


def push_over(P, coll, body, clear, step=0.0008, reach=0.015):
    """Points closer than `clear` to a thin collider (the glasses' arms beside the head) moved out along the skin's
    normal until they clear it: hair the arms do not press (over the ear, behind it) lies over them. Pushed away
    from the arm's nearest point instead, the hair over the ear's top split round the arm, a hard straight edge 3 mm
    above it with skin between. Falls back to push_out where `reach` does not clear it."""
    P = np.array(P, np.float64)
    for i in range(len(P)):
        r = coll.nearest(P[i], clear)
        if r is None:
            continue
        rb = body.nearest(P[i], 0.05)
        if rb is None:
            P[i] = push_out(P[i][None], coll, clear)[0]
            continue
        n = body.FN[rb[1]]
        q = P[i].copy()
        moved = 0.0
        while moved < reach:
            q = q + n * step
            moved += step
            if coll.nearest(q, clear) is None:
                break
        P[i] = q if moved < reach else push_out(P[i][None], coll, clear)[0]
    return P


def push_out(P, coll, clear, solid=False, reach=0.03):
    """Points closer than `clear` to a collider moved out to `clear`. A thin collider (glasses frames): away from
    the nearest point on it. A solid one (the body, outward normals): anything behind its surface within `reach`
    comes out along the face normal, however deep."""
    if coll is None:
        return P
    P = np.array(P, np.float64)
    for i in range(len(P)):
        r = coll.nearest(P[i], reach if solid else clear)
        if r is None:
            continue
        loc, tri, _, d = r
        n = coll.FN[tri]
        off = P[i] - loc
        h = float(off @ n)
        if solid:
            # behind the surface's nearest face is not always inside (creases beside the neck, under the jaw):
            # only a confirmed inside point moves, however deep; one just outside moves out to `clear`
            if h < 0 and coll.inside(P[i]):
                P[i] = loc + n * clear
            elif 0 <= h < clear:
                P[i] = loc + n * clear
            continue
        if d >= clear:
            continue
        if h >= 0 and d > 1e-6:
            P[i] = loc + off / d * clear
        else:
            P[i] = loc + n * clear
    return P


# ------------------------------------------------------------------ textures (Blender orientation: row 0 = v 0)
def to_lab(c):
    """sRGB-encoded colours -> CIE Lab."""
    c = np.clip(np.asarray(c, np.float64), 0.0, 1.0)
    li = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = li @ M.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(np.maximum(xyz, 0.0)), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def sample_img(img, uv):
    h, w = img.shape[:2]
    uv = np.clip(np.asarray(uv, np.float64), 0.0, 1.0 - 1e-7)
    return img[(uv[..., 1] * h).astype(int), (uv[..., 0] * w).astype(int)]


def kmeans(X, k, iters=12):
    """A few colour centres (deterministic: seeded at lightness quantiles)."""
    if len(X) <= k:
        return np.asarray(X, np.float64).copy()
    C = X[np.argsort(X[:, 0])[np.linspace(0, len(X) - 1, k).astype(int)]].astype(np.float64).copy()
    for _ in range(iters):
        lab = ((X[:, None] - C[None]) ** 2).sum(-1).argmin(1)
        for j in range(k):
            if (lab == j).any():
                C[j] = X[lab == j].mean(0)
    return C


def nearest_dist(X, C):
    out = np.empty(len(X))
    for s in range(0, len(X), 1 << 18):
        out[s:s + (1 << 18)] = np.sqrt(((X[s:s + (1 << 18), None] - C[None]) ** 2).sum(-1).min(1))
    return out


def box_blur(a, r, n=3):
    """n box blurs of radius r (about a Gaussian), edges clamped."""
    h, w = a.shape[:2]
    for _ in range(n):
        for axis, size in ((0, h), (1, w)):
            p = np.pad(a, [(r, r) if k == axis else (0, 0) for k in range(a.ndim)], mode='edge')
            c = np.cumsum(p, axis=axis, dtype=np.float64)
            c = np.concatenate([np.zeros_like(np.take(c, [0], axis=axis)), c], axis=axis)
            a = (np.take(c, np.arange(2 * r + 1, 2 * r + 1 + size), axis=axis) -
                 np.take(c, np.arange(0, size), axis=axis)) / (2 * r + 1)
    return a.astype(np.float32)


def uv_raster(UVc, P, size, sel=None):
    """Rasterise triangles into a UV-space position map: per texel the 3D point (NaN where no triangle).
    UVc: (m, 3, 2) corner UVs, P: (m, 3, 3) corner positions."""
    h = w = size
    pos = np.full((h, w, 3), np.nan, np.float32)
    idx = np.arange(len(UVc)) if sel is None else np.nonzero(sel)[0]
    for i in idx:
        t = UVc[i] * np.array([w, h]) - 0.5
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        a, b, c = t
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        l1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        l2 = 1 - l0 - l1
        m = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        if not m.any():
            continue
        q = l0[m, None] * P[i, 0] + l1[m, None] * P[i, 1] + l2[m, None] * P[i, 2]
        pos[ys[m], xs[m]] = q
    return pos


# ------------------------------------------------------------------ the face frame and where hair may grow
def frame_of(G):
    eye = np.asarray(G["eye_c"], np.float64)
    ef = float(G["eye_front"])
    fr = dict(eye=eye, eye_front=ef, top=float(G["top"]), brow_z=float(G["brow_z"]),
              ears=np.asarray(G["ears"], np.float64).reshape(-1, 3))
    fr["centre"] = np.array([eye[0], ef + 0.085, eye[2] + 0.02])     # middle of the skull
    fr["y_face"] = ef + 0.057                                          # a little behind the eyes: the temples' plane
    # the upper lids per eye, as (x ascending, z) from corner to corner: the build's landmarks, or (an older
    # hair_guide.npz) a typical lid arc 18-45 mm either side of the eyes' middle, 6 mm high over the iris
    L = G.get("eye_lids")
    if L is not None and len(L) == len(LIDS):
        L = np.asarray(L, np.float64)
        lids = [L[:9], L[9:]]
    else:
        xs = np.linspace(0.018, 0.045, 9)
        zs = eye[2] + 0.006 - 0.007 * ((xs - 0.0315) / 0.0135) ** 2
        lids = [np.stack([eye[0] - xs, np.full(9, ef), zs], 1), np.stack([eye[0] + xs, np.full(9, ef), zs], 1)]
    fr["lids"] = [l[np.argsort(l[:, 0])] for l in lids]
    return fr


def eye_floor(q, fr, clear=0.0025, beyond=1.0):
    """The lowest a fringe strand may come at q's x in front of the eyes: `clear` over the upper lid between the
    corners (a lock hanging over the iris read as a black bar through the eye in the frontal close-up), falling
    away by `beyond` metres per metre past each corner (a longer lock may hang between the eyes, as the portrait's).
    None away from the eyes."""
    if q[1] > fr["eye_front"] + 0.035:
        return None
    best = None
    for l in fr["lids"]:
        x0, x1 = float(l[0, 0]), float(l[-1, 0])
        x = float(q[0])
        z = float(np.interp(x, l[:, 0], l[:, 2])) + clear - beyond * max(x0 - x, x - x1, 0.0)
        if x0 - 0.02 < x < x1 + 0.02 and (best is None or z > best):
            best = z
    return best


def on_brows(P, fr):
    """Points on the brows (in front of the face, between the brows' outer ends, below 1 cm over them). Short hair
    never roots there: where a style lets the scalp mask take in the brows (brow_band: Mano's scan painted its
    fringe onto his forehead), its hairline ran round them and the guide's bare scalp covered them, and cards rooted
    there grew out of the eyebrows under the fringe's ends."""
    P = np.atleast_2d(P)
    return (P[:, 1] < fr["eye_front"] + 0.03) & (np.abs(P[:, 0] - fr["eye"][0]) < 0.05) & \
        (P[:, 2] < fr["brow_z"] + 0.01)


def off_brows(p, fr, nearest, rng=None, step=0.0015, reach=0.05, extra=(0.0005, 0.007)):
    """A root on the brows (on_brows) moved straight up over a surface to just above them, a random `extra` further
    so the moved roots do not line up. nearest(q) -> (closest point, its normal) or None. Returns (root, distance
    walked), or (None, 0) when it cannot get out within `reach`. Dropped instead, those roots left the band over the
    brows bare under Mano's fringe: the cards from higher up fade in at their roots, and the cap's dark roots
    showed through them as a soft black smear with no strands."""
    q = np.asarray(p, np.float64).copy()
    walked, over = 0.0, 0.0
    ext = float(rng.uniform(*extra)) if rng is not None else float(extra[0])
    up = np.array([0.0, 0.0, 1.0])
    for _ in range(int(reach / step) + 1):
        r = nearest(q)
        if r is None:
            return None, 0.0
        loc, n = r
        t = up - n * float(n @ up)
        t = t / vlen(t) if vlen(t) > 0.2 else up
        if not on_brows(loc, fr)[0]:
            over += step
            if over > ext:
                return loc, walked
        q = loc + t * step
        walked += step
    return None, 0.0


def near_ears(P, fr, r=0.045):
    """Points within r of an ear (sideways and front to back) and no higher than its top."""
    P = np.atleast_2d(P)
    m = np.zeros(len(P), bool)
    for t in fr["ears"]:
        m |= (np.linalg.norm(P[:, :2] - t[None, :2], axis=1) < r) & (P[:, 2] < fr["eye"][2] + 0.05) & \
            (P[:, 2] > fr["eye"][2] - 0.09)
    return m


def ear_weight(P, fr, r0, r1):
    """The ears (as scan_wrap.ear_mask: behind and outside the face's side landmarks 234 / 454)."""
    m = np.zeros(len(P))
    cx = fr["eye"][0]
    for t in fr["ears"]:
        side = 1.0 if t[0] >= cx else -1.0
        c = t + np.array([side * 0.008, 0.02, -0.005])
        d = np.linalg.norm(P - c, axis=1)
        behind = smoothstep(t[1] - 0.012, t[1] + 0.006, P[:, 1])
        ax = abs(t[0] - cx)
        outside = smoothstep(ax - 0.025, ax - 0.008, (P[:, 0] - cx) * side)
        m = np.maximum(m, behind * outside * (1.0 - smoothstep(r0, r1, d)))
    return m


# the face window (long hair, from design A): half-width of the face by height above the eyes. The default; each
# person's own (fit_face_window: where the head's baked texture stops being skin, per side) replaces it where it
# is narrower, so the cards cover the scan's painted hair beside the face (shown bare, it read as a dark leathery
# sheet over the temple, cheek and jaw)
FW_Z = [-0.14, -0.12, -0.07, 0.0, 0.03, 0.05, 0.068]
FW_W = [0.0, 0.046, 0.064, 0.07, 0.058, 0.036, 0.0]


def face_halfwidth(z_rel, margin, fr=None, side=None):
    """Half-width of the face window at z_rel (above the eyes); side (per point: +1 the character's left, -1 the
    right) picks the person's fitted profile when the frame has one."""
    fw = fr.get("fw") if fr is not None else None
    if fw is None or side is None:
        hw = np.interp(z_rel, FW_Z, FW_W)
    else:
        Z, Wn, Wp = fw
        hw = np.where(np.asarray(side) >= 0, np.interp(z_rel, Z, Wp), np.interp(z_rel, Z, Wn))
    return np.where(hw > 0, hw + margin, 0.0)


def in_face_window(P, fr, margin=0.0):
    P = np.atleast_2d(P)
    dx = P[:, 0] - fr["eye"][0]
    hw = face_halfwidth(P[:, 2] - fr["eye"][2], margin, fr, np.sign(dx))
    return (np.abs(dx) < hw) & (P[:, 1] < fr["y_face"])


def window_top(x_abs, side, fr, z_from, margin=0.0):
    """The face window's upper edge above z_from (above the eyes) at |dx| = x_abs: the first height above it where
    the window is narrower than x_abs."""
    zs = np.arange(z_from, 0.1, 0.0005)
    hw = face_halfwidth(zs, margin, fr, np.full(len(zs), side))
    out = zs[hw <= x_abs]
    return float(out[0]) if len(out) else 0.1


def clamp_out_of_window(V, fr, margin=0.002, body=None):
    """Card vertices inside the face window moved out to its nearest edge: up (the forehead's hairline) or sideways
    (beside the face). The strands themselves never enter it; this is for the cards' width: a card running along
    the hairline hung half its width over the forehead, a straight edge that read as a fringe or a headband.
    With the body, a moved vertex keeps its height over the skin (moved sideways alone it stayed level with the
    forehead, in front of the temple, which lies further back: a short card there stood off it like a flyaway)."""
    V = np.array(V, np.float64)
    idx = np.nonzero(in_face_window(V, fr, margin))[0]
    cx, ez = fr["eye"][0], fr["eye"][2]
    for i in idx:
        h0 = None
        if body is not None:
            r = body.nearest(V[i], 0.05)
            if r is not None:
                h0 = float((V[i] - r[0]) @ body.FN[r[1]])
        dx = V[i, 0] - cx
        sd = 1.0 if dx >= 0 else -1.0
        z = V[i, 2] - ez
        hw = float(face_halfwidth(z, margin, fr, sd))
        zt = window_top(abs(dx), sd, fr, z, margin)
        if zt - z < hw - abs(dx):
            V[i, 2] = ez + zt + 0.0005
        else:
            V[i, 0] = cx + sd * (hw + 0.0005)
        if h0 is not None:
            r = body.nearest(V[i], 0.05)
            if r is not None:
                h = float((V[i] - r[0]) @ body.FN[r[1]])
                if h > max(h0, 0.002) + 0.002:
                    V[i] = r[0] + body.FN[r[1]] * max(h0, 0.002)
    return V, len(idx)


def fit_face_window(G, fr, hair_tex, overlap=0.004, wmin=0.7):
    """The person's face window: per side and height, where the head's baked texture turns from skin to hair going
    out from the face's middle (the painted hairline), `overlap` further in so the cards cover its soft edge; never
    wider than the default window, never narrower than `wmin` (style window_min, default 0.7) of it; a wmin over 1
    widens the default itself by that much. The eyes and brows (dark, but not hair) are skipped and bridged; heights
    with no clear hairline keep the default. (Silvia: peach hair and her skin are a few Lab units apart, the face's
    shaded sides read as hair and the window came out at the 70 % floor everywhere, her hair over her cheeks and the
    corners of her forehead; at the default width, locks hung in front of her glasses' outer rims: window_min 1.06)"""
    Vb, Tb, UVb, head = G["body_V"], G["body_T"], G["body_UV"], G["body_head"]
    C = Vb[Tb].mean(1)
    e, cx = fr["eye"], fr["eye"][0]
    h = sample_img(hair_tex, UVb.mean(1))
    front = head & (C[:, 1] < fr["y_face"] + 0.02)
    Z = np.round(np.arange(-0.14, 0.071, 0.005), 3)
    Wd = np.interp(Z, FW_Z, FW_W) * max(1.0, wmin)
    out = []
    for side in (-1.0, 1.0):
        W = np.full(len(Z), np.nan)
        for i, z in enumerate(Z):
            if -0.04 <= z <= 0.032 and not (-0.012 < z < -0.006):
                continue        # eyes, lids and brows
            m = front & (np.abs(C[:, 2] - (e[2] + z)) < 0.003) & ((C[:, 0] - cx) * side >= 0)
            if m.sum() < 6:
                continue
            xa = np.abs(C[m, 0] - cx)
            ha = h[m]
            o = np.argsort(xa)
            xa, ha = xa[o], ha[o]
            lo = 0.03 if z < 0.032 else 0.0        # the nose, mouth and their shadows are not hair
            for j in range(len(xa)):
                if xa[j] < lo or ha[j] <= 0.5:
                    continue
                run = (xa >= xa[j]) & (xa < xa[j] + 0.005)
                if ha[run].mean() > 0.6:
                    W[i] = xa[j]
                    break
        ok = np.isfinite(W)
        if ok.sum() >= 4:
            Wf = np.interp(Z, Z[ok], W[ok])
            # a 3-tap median, then the overlap
            Wm = np.array([np.median(Wf[max(0, i - 1):i + 2]) for i in range(len(Wf))]) - overlap
            Wf = np.clip(Wm, min(1.0, wmin) * Wd, Wd)
        else:
            Wf = Wd.copy()
        out.append(np.where(Wd > 0, Wf, 0.0))
    log("face window (half-width, mm, every 2 cm from 14 cm below the eyes): right " +
        " ".join(f"{w * 1000:.0f}" for w in out[0][::4]) + "; left " + " ".join(f"{w * 1000:.0f}" for w in out[1][::4]) +
        "; default " + " ".join(f"{w * 1000:.0f}" for w in Wd[::4]))
    return Z, out[0], out[1]


def smooth_window(fw, sigma):
    """(style window_smooth, off by default) the fitted face window's half-widths smoothed over height (Gaussian,
    sigma metres), at most 2 mm wider than before. Fitted every 5 mm from the painted hairline, the profile steps by up to
    5 mm within a centimetre; the strands beside the face hug its edge, all of them along the same stepped line, and
    the curtain's front edge beside the cheek read as stair-stepped vertical lines (Anisha, 3/4 view)."""
    Z, Wn, Wp = fw
    out = []
    for W in (Wn, Wp):
        k = np.exp(-0.5 * ((Z[:, None] - Z[None, :]) / sigma) ** 2) * (W[None, :] > 0)
        Ws = (k * W[None, :]).sum(1) / np.maximum(k.sum(1), 1e-9)
        out.append(np.where(W > 0, np.minimum(Ws, W + 0.002), 0.0))
    log(f"face window smoothed over {sigma * 1000:.0f} mm: right " + " ".join(f"{w * 1000:.0f}" for w in out[0][::4]) +
        "; left " + " ".join(f"{w * 1000:.0f}" for w in out[1][::4]))
    return Z, out[0], out[1]


def hairline_window(fw, fr, wh):
    """(style window_hairline {h, w, from}, off by default) the face window's top over the forehead from the person's
    hairline measured in the portrait: half-widths `w` at heights `h` over the eyes' centre, both in inter-ocular
    distances (IOD, the upper lids' middles apart), taken where narrower than the fitted window, from `from` IOD over
    the eyes up (fading in over 5 mm below). Silvia: her peach hair is a few Lab units from her skin, so the fit kept
    the default window (x1.06): its top reached 1.34 IOD over her eyes and 1.15 IOD either side at 0.56 IOD, a bare
    dome of forehead up to the part with skin over her temples; in her portrait the hair falls from the part at
    1.08 IOD to the brows' tails (0.9 IOD out at 0.3 IOD over the eyes)."""
    Z, Wn, Wp = fw
    L = fr["lids"]
    iod = abs(float(L[1][:, 0].mean() - L[0][:, 0].mean()))
    h = np.asarray(wh["h"], np.float64) * iod
    w = np.asarray(wh["w"], np.float64) * iod
    o = np.argsort(h)
    tgt = np.interp(Z, h[o], w[o], left=1.0, right=0.0)
    z0 = float(wh.get("from", 0.3)) * iod
    # (`fade`, IOD: how far below `from` it fades in; 5 mm without it)
    k = smoothstep(z0 - (float(wh["fade"]) * iod if "fade" in wh else 0.005), z0, Z)
    out = []
    for W in (Wn, Wp):
        Wt = np.minimum(W, tgt)
        out.append(np.where(W > 0, W + k * (Wt - W), 0.0))
    log(f"face window from the portrait's hairline (IOD {iod * 1000:.1f} mm, from {z0 * 1000:.0f} mm over the eyes): "
        f"right " + " ".join(f"{x * 1000:.0f}" for x in out[0][::4]) +
        "; left " + " ".join(f"{x * 1000:.0f}" for x in out[1][::4]))
    return Z, out[0], out[1]


def region_weight(P, fr, st):
    """Where hair may grow at all: not the face (brows, lashes), not the beard, not below the nape (short hair),
    no sideburns and nothing in the face window (long hair)."""
    e, ef = fr["eye"], fr["eye_front"]
    y = P[:, 1] - ef          # behind the front of the eyes
    z = P[:, 2] - e[2]        # above the eyes
    front = 1.0 - smoothstep(0.065, 0.085, y)
    # (a style whose fringe comes down over the forehead lowers this band: Mano's scan wrapped his forehead onto
    # its fringe, a hair-painted ledge over the brows that the cards have to cover)
    b0, b1 = st.get("brow_band", (0.035, 0.05))
    brow = smoothstep(b0, b1, z)
    infront = 1.0 - smoothstep(0.085, 0.1, y)
    if st["long"] and st.get("face_window") and fr.get("fw") is not None:
        # long hair with the person's own face window: below the eyes that window alone keeps the hair off the
        # face (the scan paints the hair down beside the cheeks and jaw; left bare it read as a dark leathery
        # sheet over them), never the throat; the brows and eyes as for everyone, but only down to the lower lids:
        # the band reaching 4.5 cm below the eyes kept the hair beside the cheekbones (outside the window) bare,
        # so the locks from the temple fell free there and ended mid-cheek over the scan's painted hair, a muddy
        # gap with the underlayer's dark edge in it (Anisha, 3/4 view)
        w = 1.0 - front * (1.0 - brow) * smoothstep(-0.022, -0.01, z)
        w *= 1.0 - (1.0 - smoothstep(-0.13, -0.11, z)) * infront
        return w * ~in_face_window(P, fr, 0.0)
    w = 1.0 - front * (1.0 - brow)
    low = 1.0 - smoothstep(-0.03, -0.01, z)
    w *= 1.0 - low * infront
    if not st["long"]:
        w *= smoothstep(st["nape"] - 0.015, st["nape"], z)
    else:
        w *= 1.0 - (1.0 - smoothstep(0.0, 0.02, z)) * infront
    if st.get("face_window"):
        w *= ~in_face_window(P, fr, 0.0)
    return w


def hairness_map(G, fr, st):
    """Per texel of the head's baked texture: 1 = hair, 0 = skin. Two sets of Lab colour clusters learnt for this
    person: the shell's own bake (surely hair) and the forehead's skin (between the brows and the hairline), each
    texel taking the nearer, softly. If the two do not separate, the fixed rule of the prototype (darker or less
    coloured than the skin)."""
    tex = np.asarray(G["head_tex"], np.float32)
    lab = to_lab(tex)
    Vb, Tb, UVb, head = G["body_V"], G["body_T"], G["body_UV"], G["body_head"]
    C = Vb[Tb].mean(1)
    e, ef = fr["eye"], fr["eye_front"]
    # skin: the forehead between the brows and the hairline, and the upper cheeks (a heavy fringe paints the
    # forehead dark: then the cheeks carry it)
    fore = head & (np.abs(C[:, 0] - e[0]) < 0.025) & (C[:, 2] > e[2] + 0.02) & (C[:, 2] < e[2] + 0.045) & \
        (C[:, 1] < ef + 0.03)
    cheek = head & (np.abs(np.abs(C[:, 0] - e[0]) - 0.037) < 0.012) & (C[:, 2] > e[2] - 0.04) & \
        (C[:, 2] < e[2] - 0.015) & (C[:, 1] < ef + 0.045)
    skin = sample_img(lab, UVb[fore | cheek].reshape(-1, 2))
    if len(skin):
        # not brows, stubble, a fringe or a shadow: the skin's own colour
        skin = skin[skin[:, 0] > 0.75 * np.percentile(skin[:, 0], 80)]
    suv = np.concatenate([G["shell_UV"].reshape(-1, 2), G["shell_UV"].mean(1)])
    hair = sample_img(to_lab(np.asarray(G["shell_tex"], np.float32)), suv)
    hair = hair[hair[:, 0] > 0.5]                                  # not the bake's empty background
    if len(hair) > 50:
        hair = hair[hair[:, 0] <= np.percentile(hair[:, 0], 85)]   # not the generator's painted highlights
    ref = skin.mean(0) if len(skin) else np.array([65.0, 15.0, 20.0])
    lr = lab[..., 0] / max(ref[0], 1e-3)
    cr = np.hypot(lab[..., 1], lab[..., 2]) / max(math.hypot(ref[1], ref[2]), 1e-3)
    rule = np.clip(np.maximum((0.72 - lr) / 0.3, (0.6 - cr) / 0.3), 0.0, 1.0)
    if len(skin) < 20 or len(hair) < 50:
        log(f"hairness: too few samples (skin {len(skin)}, hair {len(hair)}); prototype rule")
        return rule.astype(np.float32), ref
    Ch, Cs = kmeans(hair, 3), kmeans(skin, 3)
    sep = float(np.sqrt(((hair.mean(0) - skin.mean(0)) ** 2).sum()))
    if sep < 18:
        log(f"hairness: hair and skin only {sep:.0f} Lab apart; prototype rule")
        return rule.astype(np.float32), ref
    flat = lab.reshape(-1, 3)
    dh, ds = nearest_dist(flat, Ch), nearest_dist(flat, Cs)
    t = (ds / np.maximum(dh + ds, 1e-6)).reshape(lab.shape[:2])
    learned = smoothstep(0.38, 0.62, t)
    log(f"hairness: hair Lab {np.round(Ch).astype(int).tolist()}, skin Lab {np.round(Cs).astype(int).tolist()}, "
        f"{sep:.0f} apart; learned covers {float((learned > 0.5).mean()):.2f} of the head texture, "
        f"the fixed rule {float((rule > 0.5).mean()):.2f}")
    return learned.astype(np.float32), ref


def part_line(st, fr):
    """The centre part: from the front hairline to just behind the top of the head, on the skull's top."""
    c = fr["centre"]
    a = c + np.array(st["part"][0], np.float64)
    b = c + np.array(st["part"][1], np.float64)
    a[2] = b[2] = fr["top"]
    return a, b


def hair_base(G, fr, st):
    """The scalp mask on the body, the cap, the bare scalp the cards also grow over (not under the shell), the
    long-hair cape (hair-dark back of the clothes) and the hairline's iso points."""
    Vb, Tb, UVb = G["body_V"], G["body_T"], G["body_UV"]
    head, cloth = G["body_head"], G["body_cloth"]
    body = Mesh(Vb, Tb)
    C = Vb[Tb].mean(1)
    fn = body.FN
    hair_tex, ref = hairness_map(G, fr, st)
    if st.get("face_window"):
        fr["fw"] = fit_face_window(G, fr, hair_tex, wmin=float(st.get("window_min", 0.7)))
        if st.get("window_smooth"):
            fr["fw"] = smooth_window(fr["fw"], float(st["window_smooth"]))
        if st.get("window_hairline"):
            fr["fw"] = hairline_window(fr["fw"], fr, st["window_hairline"])
    hh = np.zeros(len(Vb))
    hn = np.zeros(len(Vb))
    np.add.at(hh, Tb[head].ravel(), sample_img(hair_tex, UVb[head].reshape(-1, 2)))
    np.add.at(hn, Tb[head].ravel(), 1.0)
    vh = hh / np.maximum(hn, 1)
    reg = region_weight(Vb, fr, st)
    if st["long"] and st.get("face_window") and fr.get("fw") is not None:
        # the mouth's inside (palate, throat: dark, so "hair" to the texture) lies behind the face window's back
        # plane: with only that window to keep long hair off the face below the eyes, it became scalp, and cards
        # rooted in the throat came out under the jaw as a dark blade in front of the neck. Skin that looks at
        # more of the body within a few cm along its own normal is inside the head, never scalp
        e_, ear_y = fr["eye"], float(fr["ears"][:, 1].min())
        sel = np.nonzero(head & (C[:, 2] < e_[2] - 0.015) & (C[:, 1] < ear_y + 0.04) &
                         (np.abs(C[:, 0] - e_[0]) < 0.045))[0]
        inner = sel[body.ray_hits(C[sel] + fn[sel] * 0.0005, fn[sel], 0.06)]
        reg[np.unique(Tb[inner])] = 0.0
        log(f"inside the mouth: {len(inner)} head tris kept off the scalp")
    vhr = vh * reg
    ears = ear_weight(Vb, fr, 0.022, 0.032)
    cand = head & (C[:, 2] > fr["eye"][2] - 0.13)
    cap = cand & (vhr[Tb].max(1) > 0.03) & (ear_weight(C, fr, 0.016, 0.024) < 0.5)
    band = np.zeros(len(Tb), bool)
    if st.get("part"):
        # along a centre part the scan is often painted skin (and its shell slit open): the cap and the guide
        # cover a band either side of the line, so the part is the 2-3 mm gap baked into the cap, not a stripe
        a, b = part_line(st, fr)
        band = head & (np.abs(C[:, 0] - a[0]) < 0.02) & (C[:, 1] > a[1] - 0.012) & (C[:, 1] < b[1] + 0.01) & \
            (C[:, 2] > fr["top"] - 0.075) & (fn[:, 2] > 0.2)
        cap |= band
    shell = Mesh(G["shell_V"], G["shell_T"])
    covered = np.zeros(len(Tb), bool)
    ci = np.nonzero(cap)[0]
    covered[ci] = shell.ray_hits(C[ci] + fn[ci] * 0.0008, fn[ci], 0.09)
    # the bare scalp the cards grow over: mask > 0.3 at all three corners, not under the shell, not the ears
    bare = cap & ~covered & (((vhr[Tb].min(1) > 0.3) & (ears[Tb].max(1) < 0.3)) | band)
    guide = bare.copy()
    wh_ = st.get("window_hairline") or {}
    if wh_.get("guide") and fr.get("fw") is not None:
        # (window_hairline "guide", off by default) the forehead's corners between the face window and the scan's
        # own hairline grow cards on the skin (bare scalp guide; no cap: no dark roots painted there). Silvia's scan
        # sculpts and paints her hair from a hairline 1-2 cm higher than her portrait's, so a narrower window alone
        # left those corners bare: the dome of skin up to the part, a bare patch over the temple
        Lw = fr["lids"]
        iod_ = abs(float(Lw[1][:, 0].mean() - Lw[0][:, 0].mean()))
        e_, ef_ = fr["eye"], fr["eye_front"]
        cand = np.nonzero(head & ~cap & (C[:, 2] > e_[2] + float(wh_.get("guide_from", wh_.get("from", 0.3))) * iod_) &
                          (C[:, 1] < ef_ + float(wh_.get("depth", 0.06))) & ~in_face_window(C, fr, 0.0) &
                          (ear_weight(C, fr, 0.016, 0.024) < 0.5))[0]
        if len(cand):
            hit = shell.ray_hits(C[cand] + fn[cand] * 0.0008, fn[cand], 0.09)
            cand = cand[~hit]
            guide[cand] = True
        log(f"hairline from the portrait: {len(cand)} forehead tris outside the window and off the shell made guide")
    n_cape = 0
    if st["long"] and G.get("body_tex") is not None and st.get("cape", True):
        # (style cape = False turns it off: it takes dark clothes for dark hair, and Silvia's black jacket under her
        # shoulder-length peach hair grew cards down her back to the waist)
        # long hair below the shoulders is part of the body ("cape": clothes, hair-dark, facing back), on the back
        # between the shoulder blades only: in the scan's A-pose the hands hang beside the hips, and a dark patch on
        # a sleeve grew cards there that the spine bones then left floating in mid-air beside the hip
        btex = np.asarray(G["body_tex"], np.float32)
        B = G.get("bones") or {}
        cx = fr["eye"][0]
        half = 0.13
        if "upperarm_l" in B and "upperarm_r" in B:
            half = min(half, 0.9 * min(abs(float(B["upperarm_l"][0]) - cx), abs(float(B["upperarm_r"][0]) - cx)))
        z_hi = float(B["neck_01"][2]) + 0.05 if "neck_01" in B else fr["eye"][2]
        sel = np.nonzero(cloth & (fn[:, 1] > 0.15) & (C[:, 2] > fr["eye"][2] - 0.62) & (C[:, 2] < z_hi) &
                         (np.abs(C[:, 0] - cx) < half))[0]
        lum = sample_img(btex, UVb[sel].mean(1))[:, :3] @ np.array([0.2126, 0.7152, 0.0722])
        sel = sel[lum < 0.2]
        if len(sel):
            hit = shell.ray_hits(C[sel] + fn[sel] * 0.0008, fn[sel], 0.09)
            sel = sel[~hit]
            # and only patches of some size (a stray dark triangle is a shadow or a seam, not hair)
            lab = tri_components(Tb[sel])
            big = np.bincount(lab)[lab] >= 6
            guide[sel[big]] = True
            n_cape = int(big.sum())
            if (~big).any():
                log(f"cape: {int((~big).sum())} stray tris dropped")
    used = np.unique(Tb[guide])
    remap = -np.ones(len(Vb), np.int64)
    remap[used] = np.arange(len(used))
    # (short hair: 2 mm over the skin, a millimetre over the cap's dark roots, 1 mm over it: at 1.2 mm the cards
    # lying on it, a few tenths of a mm over the cap and sagging between their rows over the brow ridge, went under
    # it, and the cap was drawn over the fringe's lower half, a soft black band with no strands)
    Vg = Vb[used] + body.N[used] * (0.0012 if st["long"] else GUIDE_LIFT)
    Tg = remap[Tb[guide]]
    # hairline: where the mask crosses iso on the uncovered cap's edges
    iso = st["hairline"]["iso"]
    hl = []
    for tri in Tb[cap & ~covered]:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            ha, hb_ = vhr[a], vhr[b]
            if (ha - iso) * (hb_ - iso) < 0 and max(ears[a], ears[b]) < 0.3:
                t = (iso - ha) / (hb_ - ha)
                hl.append(Vb[a] + (Vb[b] - Vb[a]) * t + (body.N[a] + body.N[b]) * 0.0005)
    hl = np.unique(np.round(np.array(hl), 6), axis=0) if hl else np.zeros((0, 3))
    hl_moved = np.zeros(len(hl), bool)
    if st["long"] and len(hl):
        # long hair: the scan paints its hair down beside the jaw and the neck, where the mask's edge is not a
        # hairline: roots there (a hairline card runs the hair's full length) hung below the jaw as blades. Hair
        # grows in front of the ear down to its middle, behind it down to the nape
        e_, ears_ = fr["eye"], fr["ears"]
        ear_z, ear_y = float(ears_[:, 2].mean()), float(ears_[:, 1].max())
        ok = (hl[:, 2] > ear_z - 0.025) | ((hl[:, 1] > ear_y + 0.025) & (hl[:, 2] > e_[2] - 0.12))
        if (~ok).any():
            log(f"hairline: {int((~ok).sum())} points below the ears or on the jaw dropped")
        hl = hl[ok]
        hl_moved = hl_moved[ok]
    if not st["long"] and len(hl):
        # short hair: no hairline on the brows. Where a style lets the scalp mask take in the brows (brow_band:
        # Mano's scan painted its fringe onto his forehead), the mask's edge runs round them, and the cards rooted
        # there (four to a point) lay under the fringe's ends as flat dark tabs: a straight dark edge along the brow
        # over each eye and a hard chip over the inner corner. Grown sparse instead, they ran from the brow out over
        # the glasses' top bar (kept in front of the lenses), oblique sheets that read as black flakes over the eye.
        # They are moved up over the skin to just above the brows (off_brows), and their cards hang from there down
        # over the brows to the fringe's floor. (Dropped, the band over the brows had no strands of its own: the
        # cards from higher up fade in at their roots, and the cap showed through them as a soft black smear.)
        # build_hair thins them to one per step again
        on_brow = on_brows(hl, fr)
        if on_brow.any():
            rng_b = np.random.default_rng(11)

            def on_skin(q):
                r = body.nearest(q, 0.03)
                return None if r is None else (r[0], body.FN[r[1]])

            moved = []
            for q in hl[on_brow]:
                q2, _ = off_brows(q, fr, on_skin, rng_b)
                if q2 is not None:
                    r = body.nearest(q2, 0.03)
                    moved.append(q2 + body.FN[r[1]] * 0.0005)
            log(f"hairline: {int(on_brow.sum())} points on the brows moved up over them ({len(moved)} kept)")
            hl = np.concatenate([hl[~on_brow], np.array(moved).reshape(-1, 3)])
            hl_moved = np.arange(len(hl)) >= int((~on_brow).sum())
    # the front hairline under the shell's overhang (short hair): the shell's lip stands off the forehead, its
    # cards end at its edge, and the scalp between that edge and the hairline showed as a smooth dark band (the
    # cap) with no strands over it. Hairline cards rooted there run up over the scalp itself (build_hair)
    hl_cov, scalp = np.zeros((0, 3)), None
    if not st["long"]:
        e_, ef_ = fr["eye"], fr["eye_front"]
        pts = []
        for tri in Tb[cap & covered & (C[:, 1] < ef_ + 0.07) & (C[:, 2] > e_[2] + 0.02)]:
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                ha, hb_ = vhr[a], vhr[b]
                if (ha - iso) * (hb_ - iso) < 0 and max(ears[a], ears[b]) < 0.3:
                    t = (iso - ha) / (hb_ - ha)
                    pts.append(Vb[a] + (Vb[b] - Vb[a]) * t + (body.N[a] + body.N[b]) * 0.0005)
        if pts:
            hl_cov = np.unique(np.round(np.array(pts), 6), axis=0)
            su = np.unique(Tb[cap])
            rm = -np.ones(len(Vb), np.int64)
            rm[su] = np.arange(len(su))
            scalp = Surface(Vb[su] + body.N[su] * (GUIDE_LIFT - 0.0004), rm[Tb[cap]])
    log(f"base: cap {int(cap.sum())} tris ({int((cap & covered).sum())} under the shell), bare scalp "
        f"{int(bare.sum())} tris, cape {n_cape} tris, hairline points {len(hl)} (+{len(hl_cov)} under the shell's lip)")
    return dict(body=body, shell=shell, cap=cap, reg=reg, vhr=vhr, hair_tex=hair_tex, guide=(Vg, Tg), hairline=hl,
                hairline_moved=hl_moved, skin_ref=ref, band=band, hairline_cov=hl_cov, scalp=scalp)


# ------------------------------------------------------------------ flow fields
class Flow:
    """Strand direction at a guide point: the style's analytic field, blended with the strand direction painted
    in the scan's texture (per guide vertex: TF, TC = direction and coherence x agreement)."""

    def __init__(self, st, fr):
        self.st, self.fr = st, fr
        self.TF = self.TC = self.T = None
        c = fr["centre"]
        k = st["flow"]
        if k == "curly":
            self.origin = np.array([c[0], fr["eye_front"], fr["eye"][2]]) + np.array(st["origin"])
        elif k == "long_part":
            a = c + np.array(st["part"][0])
            b = c + np.array(st["part"][1])
            a[2] = b[2] = fr["top"]
            self.a, self.b = a, b
            self.origin = a
        elif k in ("fringe", "curtain"):
            cr = np.array(st.get("crown", (0.0, 0.03, 0.012)))
            self.origin = np.array([c[0] + cr[0], c[1] + cr[1], fr["top"] - cr[2]])
        else:
            self.origin = np.array([c[0] + st.get("part_x", 0.0), fr["eye_front"] + 0.02, fr["top"] - 0.02])

    def style(self, p):
        st, fr = self.st, self.fr
        k = st["flow"]
        c, top = fr["centre"], fr["top"]
        if k == "curly":
            r = p - self.origin
            if vlen(r) < 1e-6:
                r = BACK.copy()
            g = st["gravity"] * min(1.0, max(0.0, (top - 0.03 - p[2]) / 0.08))
            return vunit(r) + DOWN * g
        if k == "long_part":
            a, b = self.a, self.b
            ab = b - a
            t = max(0.0, min(1.0, float((p - a) @ ab) / float(ab @ ab)))
            r = p - (a + ab * t)
            r[2] = 0.0
            if t >= 1.0:
                # behind the crown the hair falls back and down, it does not part
                r[0] *= 0.25
            elif t <= 0.0:
                # in front of the part: sideways off the parting and a little back, never forward over the brow
                side = 1.0 if p[0] >= a[0] else -1.0
                r = np.array([side * max(abs(r[0]), 0.01), 0.004, 0.0])
            if vlen(r) < 1e-6:
                r = XAX.copy()
            g = st["gravity"] * min(1.0, max(0.0, (top - 0.015 - p[2]) / 0.11)) ** 1.2
            # the front falls away from the part over the curve of the forehead: sideways and down (sideways
            # alone ran the cards level across the top of the forehead, a straight edge like a fringe)
            fd = st.get("front_drop", 0.0)
            if fd:
                fw = float(1.0 - smoothstep(-0.04, -0.01, p[1] - c[1]))
                g += fd * fw * min(1.0, max(0.0, (top - 0.008 - p[2]) / 0.04))
            return vunit(r) + DOWN * g
        if k == "fringe":
            # out from the crown: forward and down over the forehead (the fringe), down the sides and the back
            d = p - self.origin
            d[2] *= 0.4
            if vlen(d) < 1e-6:
                d = -BACK.copy()
            front = 1.0 - smoothstep(-0.02, 0.02, p[1] - c[1])
            d = vunit(d) + XAX * (st.get("sweep", 0.0) * float(front))
            g = st["gravity"] * min(1.0, max(0.0, (top - 0.025 - p[2]) / 0.07))
            return vunit(d) + DOWN * g
        if k == "curtain":
            # a centre-part curtain fringe: out from the crown, forward over the top; in front the hair parts
            # at part_x and falls to either side of it over the forehead; back and down at the sides and the back
            d = p - self.origin
            d[2] *= 0.4
            if vlen(d) < 1e-6:
                d = -BACK.copy()
            front = float(1.0 - smoothstep(-0.02, 0.025, p[1] - c[1]))
            lat = float(p[0] - (c[0] + st.get("part_x", 0.0)))
            side = lat / max(abs(lat), 0.008)
            # away from the part: sideways over the forehead, then back round the temples towards the ears (pure
            # sideways met the temples head on and the hair there hung straight down in blades)
            back = max(0.0, float(p[1] - (fr["eye_front"] + 0.025))) / 0.025
            d = vunit(d) + vunit(np.array([side, back, 0.0])) * (st.get("split", 1.2) * front)
            g = st["gravity"] * min(1.0, max(0.0, (top - 0.025 - p[2]) / 0.07))
            return vunit(d) + DOWN * g
        # swept / side_swept: up and back from the forehead, back over the top, back and down at the sides
        front = float(1.0 - smoothstep(-0.03, 0.03, p[1] - c[1]))
        lat = p[0] - (c[0] + st.get("part_x", 0.0))
        g = st["gravity"] * min(1.0, max(0.0, (top - 0.035 - p[2]) / 0.08)) ** 1.2
        if k == "side_swept":
            # a side part (part_x): above it the hair sweeps over to the other side (sweep > 0: the character's
            # left, +X), below it on the parting's side it falls back and down
            over = float(smoothstep(-0.006, 0.006, lat * math.copysign(1.0, st.get("sweep", 1.0))))
            side = math.copysign(1.0, st.get("sweep", 1.0))
            # (front_back: how far back the swept front still goes; low, it sweeps across and down over the
            # forehead instead of up and back into a quiff)
            bk = 0.55 + 0.25 * (1 - over)
            bk = bk + (st.get("front_back", bk) - bk) * front * over
            # the part runs from the forehead to just behind the crown; behind it the hair goes back and down from
            # the crown (split left and right all the way down the back, the two sides met in a seam)
            pw = float(1.0 - smoothstep(0.0, 0.04, p[1] - c[1]))
            lateral = side * (abs(st.get("sweep", 1.0)) * over - 0.7 * (1 - over)) * pw + \
                max(-1.0, min(1.0, lat * st.get("spread", 2.5))) * (1.0 - pw)
            d = BACK * bk + XAX * lateral + UP * st.get("lift", 0.9) * front * over
            return d + DOWN * (g + 0.3 * (1 - over) + st.get("front_down", 0.0) * front * over)
        d = BACK + UP * st.get("lift", 0.9) * front + XAX * max(-1.0, min(1.0, lat * st.get("spread", 2.5)))
        return d + DOWN * g

    def set_texture(self, TF, TC, T):
        self.TF, self.TC, self.T = TF, TC, T

    def __call__(self, p, n, tri=None, bc=None):
        d = self.style(p)
        if self.TF is not None and tri is not None:
            ids = self.T[tri]
            tc = float(bc @ self.TC[ids])
            if tc > 1e-3:
                tf = bc @ self.TF[ids]
                if float(tf @ d) < 0:
                    tf = -tf
                w = min(0.95, self.st["tex_w"] * tc)
                d = vunit(d) * (1 - w) + vunit(tf) * w
        return d


def texture_flow(tex, V, T, UVc, sigma=3.5):
    """Strand direction (3D, sign-free) and coherence per triangle, from the structure tensor of the shell's baked
    colour (the scan's painted strands), mapped through each triangle's UV -> 3D Jacobian."""
    L = (np.asarray(tex, np.float32)[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)).astype(np.float32)
    valid = (L > 0.012).astype(np.float32)
    valid = np.minimum(valid, box_blur(valid, 2, 1) > 0.99).astype(np.float32)
    Lb = box_blur(L, 1, 2)
    gx = np.zeros_like(Lb)
    gy = np.zeros_like(Lb)
    gx[:, 1:-1] = (Lb[:, 2:] - Lb[:, :-2]) * 0.5
    gy[1:-1, :] = (Lb[2:, :] - Lb[:-2, :]) * 0.5
    gx *= valid
    gy *= valid
    r = max(1, int(round(sigma)))
    norm = box_blur(valid, r) + 1e-6
    Jxx = box_blur(gx * gx, r) / norm
    Jxy = box_blur(gx * gy, r) / norm
    Jyy = box_blur(gy * gy, r) / norm
    theta = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy) + np.pi / 2          # along the streaks, not across
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / np.maximum(Jxx + Jyy, 1e-9)
    coh = coh * (norm > 0.5)
    uvc = UVc.mean(1)
    th, c = sample_img(theta, uvc), sample_img(coh, uvc)
    d2 = np.stack([np.cos(th), np.sin(th)], 1)
    e1, e2 = V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]
    q1, q2 = UVc[:, 1] - UVc[:, 0], UVc[:, 2] - UVc[:, 0]
    det = q1[:, 0] * q2[:, 1] - q1[:, 1] * q2[:, 0]
    ok = np.abs(det) > 1e-12
    det = np.where(ok, det, 1.0)
    dPdu = (e1 * q2[:, 1:2] - e2 * q1[:, 1:2]) / det[:, None]
    dPdv = (e2 * q1[:, 0:1] - e1 * q2[:, 0:1]) / det[:, None]
    F = unit(dPdu * d2[:, :1] + dPdv * d2[:, 1:2])
    return F, np.where(ok, np.clip(c, 0, 1), 0.0)


def vertex_texture_flow(flow, V, T, F, c):
    """Per vertex: the triangles' texture directions, each turned to agree with the style's flow there, averaged
    and weighted by coherence. TC = |mean| (coherent and in agreement -> 1)."""
    S = unit(np.array([flow.style(v) for v in V]))
    acc = np.zeros_like(V)
    cnt = np.zeros(len(V))
    for k in range(3):
        s = np.sign((F * S[T[:, k]]).sum(1))
        s[s == 0] = 1.0
        np.add.at(acc, T[:, k], F * (s * c)[:, None])
        np.add.at(cnt, T[:, k], 1.0)
    TC = np.linalg.norm(acc, axis=1) / np.maximum(cnt, 1)
    return unit(acc), np.clip(TC, 0, 1)


# ------------------------------------------------------------------ strands -> cards
def floor_z(q, fr, st, off=0.0):
    """The height the fringe stops at above q (None: no floor there). A parted fringe (floor_rise) is shortest at
    the part and comes lower towards the temples, in a rounded arch (a straight V read as two cut lines)."""
    ff = st.get("front_floor")
    if ff is None or st["long"]:
        return None
    c = fr["centre"]
    if not (q[1] < fr["eye_front"] + 0.045 and abs(q[0] - c[0]) < 0.075):
        return None
    rise = st.get("floor_rise", 0.0)
    if rise:
        t = min(1.0, abs(q[0] - (c[0] + st.get("part_x", 0.0))) / st.get("rise_w", 0.04))
        rise *= 0.5 + 0.5 * math.cos(math.pi * t)
    arch = st.get("floor_arch")
    if arch:
        # a curtain fringe's opening: a broad arch over the forehead, as high as the hairline in the middle
        # and down to the brows at the temples (floor_arch = (height, half-width), elliptical, about the face's
        # middle: the part sits off it, the opening does not)
        t = min(1.0, abs(q[0] - c[0]) / arch[1])
        rise += arch[0] * math.sqrt(1.0 - t * t)
    wave = st.get("floor_wave")
    wv = 0.0
    if wave:
        # locks of their own lengths, a few cm across (a per-strand jitter alone averaged out into a straight
        # edge across a dense fringe)
        # (style floor_wave_fine, default 0.4: the 11 mm wave's share; with the 23 mm one at its full depth its
        # troughs were 6 mm deep and 4-5 mm wide, and the strand sliding into one hung below an even hairline as a
        # pointed flat tab: Joaquin's notch)
        dx = float(q[0] - c[0])
        wv = wave * (0.6 * math.sin(2 * math.pi * dx / 0.023 + 1.3) +
                     float(st.get("floor_wave_fine", 0.4)) * math.sin(2 * math.pi * dx / 0.011 + 4.1))
    z = fr["brow_z"] + ff + off + rise + wv
    if fr.get("lids") is not None:
        # never over the eyes (Mano's fringe comes down to his lids): over each eye the edge keeps `eye_clear` above
        # the upper lid, still ragged (the strand's own jitter and the locks' wave, only upwards: the wave's lower
        # half cut flat left the edge level along the lid between the locks, a straight cut line over the eye)
        ze = eye_floor(q, fr, st.get("eye_clear", 0.0025), st.get("eye_beyond", 1.0))
        if ze is not None:
            z = max(z, ze + 0.6 * max(off, 0.0) + 0.5 * (wv + (wave or 0.0)))
    return z


def floor_hit(q, fr, st, off=0.0):
    """Short hair: the fringe and the hair at the temples stop at the brows (front_floor above them; off: this
    strand's own jitter, so the fringe's edge is ragged rather than cut straight)."""
    z = floor_z(q, fr, st, off)
    return z is not None and bool(q[2] < z)


def floor_slide(p, q, fr, st, off, ds):
    """A strand reaching the floor (style floor_slide: a curtain fringe) runs on along it instead of stopping
    there: the fringe's lower edge is then the side of its strands, a smooth sweep out to the temples, not a row
    of cut tips. Returns the step's end on the floor, or None when the strand has no way along it (heading
    straight down: it ends there)."""
    z = floor_z(q, fr, st, off)
    if z is None or q[2] >= z:
        return q
    q = q.copy()
    q[2] = z + 1e-4
    if vlen(q - p) < 0.35 * ds:
        return None
    return q


def grow(surf, flow, root, length, seg, lift, st, fr, rng, body, coll=None, curl=None, free_max=0.02, drape=None,
         gfront=None, face_free=True, info=None, ears=None):
    """A strand over the guide surface: points (lifted along the smoothed normal), (normal, twist), tangents.
    info (a dict, optional): "free_at", the first point off the guide (None: none), and "over_ear", whether it
    hangs free over an ear."""
    r = surf.nearest_n(root)
    if r is None:
        return None
    p, n, _, tri, bc = r
    nseg = max(2, int(round(length / seg)))
    ds = length / nseg
    pts, nrm, tan = [], [], []
    t_prev = None
    free = False
    free_len = 0.0
    vel = None
    side = 0.0
    limit, over_face, over_ear = free_max, False, False
    fell_on = False
    lie, rolled = False, False
    edge_hang = False
    f_off = st["floor_jitter"] * rng.uniform(-0.5, 1.0) if st.get("floor_jitter") else 0.0
    # (the under layer's strands end at the edge: run along it, their deep tone was the outermost hair there, a
    # black jagged lip under a curtain or a swept hairline)
    slide = bool(st.get("floor_slide")) and not st["long"] and face_free
    slid, slide_max = 0.0, (float(st.get("slide_max", 0.02)) * rng.uniform(0.5, 1.0) if slide else 0.0)
    # long hair rooted in front of the ears (drape "front_len"): a front lock. The scan has all the hair pushed
    # behind the shoulders; the person's hangs in front of them, down the chest. Below the jaw it leaves the
    # guide (which curves back behind the shoulder) and falls on, draped to the front over the shoulder
    lock = bool(drape is not None and drape.get("front_len") and p[1] < drape["front_y"])
    detached = False
    # long hair off the guide beside the face, above the jaw, lies on the skin (hug): with long hair's 2 cm steps
    # a free strand from the front hairline cut straight across the hollow of the temple and stood off it as a
    # stiff flyaway blade
    hug = False
    if slide and floor_hit(p, fr, st, max(f_off, 0.0) + 0.002):
        return None            # rooted below the fringe's edge (it would jump up onto it, or lie alone on the skin)
    wave = rng.uniform(*curl["wave"]) if curl else 1.0
    # wave phase from the distance to the flow's origin: neighbouring locks wave together (as real wavy hair does),
    # with some jitter so it never reads as a pattern
    ph = (2 * math.pi * vlen(p - flow.origin) / wave + rng.normal(0, curl["jitter"])) if curl else 0.0
    fw_margin = rng.uniform(0.0, 0.009)

    def land(p_, q_):
        # a strand stepping over the floor ends on it, not at its last whole step above it: with 7.5 mm steps the
        # fringe's tips stopped up to a step short of their own (jittered) floor, so its dense part ended about a
        # centimetre above the brows and the cap's dark roots showed under it as a soft black band. Only
        # a fringe lying on the forehead (front_free; a sliding one runs on along its floor instead)
        if not st.get("front_free"):
            return
        fz = floor_z(q_, fr, st, f_off)
        if fz is None or p_[2] <= fz or q_[2] >= fz:
            return
        t_ = (p_[2] - fz) / (p_[2] - q_[2])
        if t_ * ds < 0.001:
            return
        e_ = p_ + (q_ - p_) * t_
        if gfront is not None:
            e_, _ = gfront.keep_front(e_)
        pts.append(e_ + nrm[-1][0] * h)
        nrm.append(nrm[-1])
        tan.append(tan[-1])

    for k in range(nseg + 1):
        s = k / nseg
        if not free:
            d = flow(p, n, tri, bc)
            t = d - n * float(d @ n)
            if vlen(t) < 1e-6:
                t = t_prev if t_prev is not None else ortho(n)
            t = vunit(t)
            if t_prev is not None:
                t = vunit(t_prev * 0.45 + t * 0.55)
        else:
            t = vunit(vel)
        h = lift[0] + (lift[1] - lift[0]) * s
        twist = 0.0
        tt = t
        if curl:
            ang = 2 * math.pi * s * length / wave + ph
            h += curl["lift"] * (0.5 + 0.5 * math.sin(ang)) * min(1.0, s * 4)
            # the lock wiggles over the surface and twists about itself with the same phase: a wave in 3D
            tt = vunit(rotate(t, n, curl["wiggle"] * math.cos(ang)))
            twist = curl["twist"] * math.sin(ang)
        pts.append(p + n * h)
        nrm.append((n, twist))
        tan.append(tt)
        t_prev = t
        if k == nseg:
            break
        q = p + tt * ds
        if not np.isfinite(q).all():
            break
        if slide:
            q0 = q
            q = floor_slide(p, q, fr, st, f_off, ds)
            if q is None:
                break
            if q is not q0:
                # along the edge for a stretch only (all of them running on to their ends stacked a band of
                # parallel cards along it, read as flat tiles and a dark jagged lip: Ian's right front)
                slid += ds
                if slid > slide_max:
                    break
        elif floor_hit(q, fr, st, f_off):
            land(p, q)
            break
        if gfront is not None:
            q, _ = gfront.keep_front(q)
        if not free:
            r = surf.nearest_n(q)
            if r is None or r[2] > 0.45 * ds:
                free = True
                if info is not None and info.get("free_at") is None:
                    info["free_at"] = len(pts)
                vel = tt.copy()
                limit = free_max
                # short hair whose fringe comes down over the forehead (front_free): off the guide's front edge
                # the strand lies on the forehead for up to front_free, held to the skin
                over_face = bool(st.get("front_free") and not st["long"] and q[1] < fr["eye_front"] + 0.05 and
                                 abs(q[0] - fr["eye"][0]) < 0.07 and q[2] > fr["eye"][2])
                if over_face and not face_free:
                    break
                hug = bool(st["long"] and q[1] < float(fr["ears"][:, 1].min()) + 0.01 and
                           q[2] > fr["eye"][2] - 0.07)
                roll_end = bool(fr.get("roll_edge") is not None and not st["long"] and
                                float(fr["roll_edge"].nearest(p[None])[0][0]) < 0.004)
                if info is not None and st["long"] and info.get("front_at") is None and \
                        q[1] < float(fr["ears"][:, 1].min()) + 0.01:
                    info["front_at"] = len(pts)
                if st["long"] and st.get("fall_on") and drape is not None and q[2] < fr["eye"][2] - 0.03 and \
                        q[1] < drape["y_sh"] + 0.02:
                    # (style fall_on = metres, long hair, off by default) off the guide below the cheekbones beside
                    # the face and the neck, in front of the shoulders' middle, a strand falls on for fall_on (onto
                    # the shoulder, draped to the front or the back) instead of free_max: ending 2-7 cm off the guide's
                    # edge, a few dozen cards stopped together in mid-air beside the neck (Anisha: 151 card ends
                    # there, 51 with it). No draw: limit is free_max's
                    limit = max(limit, float(st["fall_on"]))
                    fell_on = True
                if roll_end:
                    limit = 0.0
                if fr.get("roll_lie") is not None and not st["long"] and not over_face and \
                        float(fr["roll_lie"].nearest(p[None])[0][0]) < 0.004:
                    # (style roll_drape, a dict, with roll_under, off by default) a strand leaving the guide where
                    # roll_under cut the roll's underside goes on down over the temple, lying on the skin `clear`
                    # metres off it, for its own length (`len`, from its root: no draw) and lit as the skin there
                    # (`skin` of its normal); an under-layer strand ends there. Ending all of them at the cut stacked
                    # every layer's card ends along one line at the roll's edge, read from above as flat card tabs
                    # with stair-stepped edges at the far front corner and a blunt edge before the ear
                    rd_ = st["roll_drape"]
                    rolled = True
                    if face_free:
                        lr_ = rd_.get("len", (0.012, 0.03))
                        limit = float(lr_[0]) + (float(lr_[1]) - float(lr_[0])) * hash01(root)
                        lie = True
                        if info is not None:
                            info["lie_at"] = len(pts)
                    else:
                        limit = 0.0
                if lock and q[2] < drape["z_det"] + 0.03:
                    detached, side = True, -1.0
                    limit = drape["front_len"] * rng.uniform(0.55, 1.0)
                elif over_face:
                    limit = max(free_max, st["front_free"] * rng.uniform(0.45, 1.0))
                elif st.get("ear_free") and not st["long"] and near_ears(q[None], fr, 0.05)[0]:
                    # over the ears each lock ends at its own length (all ending at the shell's edge read as a
                    # hard horizontal line above the ear). The under layer's too: cut at the edge, they left the
                    # ear's top bare, a faceted skin peak poking up into the hair with the earpiece showing behind
                    # it; hanging on, they are outer hair there (strand(): narrower, wispier, lit), not the
                    # wide dark cards that hung over the ear as flat black tabs
                    # (an under-layer strand's length from its root, not from the random sequence: they ended at
                    # the edge before, and a draw here reshuffled all the hair grown after them)
                    u_ = rng.uniform(0.15, 1.0) if face_free else 0.15 + 0.85 * hash01(root)
                    if not rolled:
                        # (rolled: roll_drape's, its draw still taken, so the random sequence stays the same)
                        limit = max(free_max, st["ear_free"] * u_)
                        over_ear = True
                ed_ = st.get("edge_free") or None
                if ed_ and not st["long"] and face_free and not over_face and not lock and not rolled and \
                        (not over_ear or ed_.get("ears")) and \
                        q[2] < fr["eye"][2] + float(ed_.get("z", 0.05)) and \
                        q[1] > fr["eye_front"] + float(ed_.get("y", 0.02)):
                    # (style edge_free, a dict, short hair, off by default) off the shell's lower edge on the sides
                    # and the back (below `z` over the eyes, `y` behind their front) a strand hangs on for a length
                    # set mostly by a smooth noise of where it leaves (`scale` metres: whole clumps hang lower or end
                    # higher, `len` [min, max], skewed short by `pow`), lit as the side of the head (with each strand
                    # ending at its own random length, the lengths average out into a smooth hard lower edge from the
                    # temple to the nape). No draw
                    lr_ = ed_.get("len", (0.006, 0.028))
                    u_ = 0.7 * vnoise(q, float(ed_.get("scale", 0.018)), 9) + 0.3 * hash01(root)
                    limit = max(limit, float(lr_[0]) + (float(lr_[1]) - float(lr_[0])) * u_ ** float(ed_.get("pow", 1.5)))
                    edge_hang = True
            else:
                p, n, _, tri, bc = r
                if lock and p[2] < drape["z_det"]:
                    free, detached = True, True
                    vel = vunit(np.array([tt[0] * 0.5, min(float(tt[1]), 0.0), 0.0]) + DOWN)
                    limit = drape["front_len"] * rng.uniform(0.55, 1.0)
                    side = -1.0
                continue
        # off the guide's edge: fall freely (gravity), outside the body, for at most free_max
        free_len += ds
        if free_len > limit:
            break
        vel = vunit(vel + DOWN * st["gravity"] * 0.35 * ds / 0.01)
        q = p + vel * ds
        rb = body.nearest(q, 0.05)
        if rb is not None:
            loc, btri, _, _ = rb
            bn = body.FN[btri]
            hb = float((q - loc) @ bn)
            if hb < 0.003:
                q = loc + bn * 0.003
            elif (over_face or (hug and q[2] > fr["eye"][2] - 0.07)) and hb > 0.005:
                q = loc + bn * 0.005
            elif lie and hb > float(st["roll_drape"].get("clear", 0.004)):
                # (down onto it by at most `descend` a step: snapped onto it at once off the roll's edge 1-1.5 cm
                # out, the ribbon folded into a lit V, and the scalp under the roll showed past it)
                q = loc + bn * max(float(st["roll_drape"].get("clear", 0.004)),
                                   hb - float(st["roll_drape"].get("descend", 0.003)))
            if hug:
                vn = float(vel @ bn)
                if vn > 0:
                    vel = vunit(vel - bn * vn * 0.85)
            if lie:
                vn = float(vel @ bn)
                if vn > 0:
                    vel = vunit(vel - bn * vn * 0.85)
                sk_ = float(st["roll_drape"].get("skin", 0.6))
                n = vunit(n * (1.0 - sk_) + body.normal_at(rb[1], rb[2]) * sk_)
            if over_face:
                vn = float(vel @ bn)
                if vn > 0:
                    vel = vunit(vel - bn * vn * 0.85)
                # lying on the forehead it is lit as the forehead (with the last guide normal, often the underside
                # of the shell's front lip, it lit as a grey or black flake)
                n = vunit(n * 0.25 + body.normal_at(rb[1], rb[2]) * 0.75)
            elif over_ear or edge_hang:
                # hanging over the ear it is lit as the side of the head (the shell's lower edge there turns in and
                # down: with its normal, the locks over the ears' tops lit as black tabs under the glasses' arms)
                n = vunit(n * 0.25 + body.normal_at(rb[1], rb[2]) * 0.75)
            if drape is not None and bn[2] > 0.45 and q[2] < drape["z_neck"] and hb < 0.007:
                # over the shoulders: drape to the front or the back (the side the strand arrives on) instead of
                # sliding sideways along the shoulder line, which piles strands into a ridge
                if side == 0.0:
                    # (style fall_front = metres, with fall_on, off by default: a strand that fell on beside the neck
                    # drapes to the front over the shoulder unless it lands fall_front behind the shoulders' middle.
                    # Parted at the middle, the strands landing behind it slid back off the shoulder's top and left
                    # it bare between the front lock and the back hair: the sweater showed through a gap there with
                    # the hair's bend over the shoulder a hard straight edge above it, from the front)
                    y_part = drape["y_sh"] + (float(st.get("fall_front") or 0.0) if fell_on else 0.0)
                    side = -1.0 if q[1] < y_part else 1.0
                q = q + BACK * side * ds * 0.7
        if over_ear and ears is not None:
            # and lies on the ear's outside, not between it and the skull (EarSide), lit as the ear's outside
            # (with the normal of the skin it hung by, the ear's back or the skull, the locks over the ear were black)
            q, on_ear = ears.drape(q, float(st.get("ear_drape", 0.0015)))
            if on_ear:
                n = vunit(XAX * math.copysign(1.0, q[0] - fr["eye"][0]) + UP * 0.35)
        if coll is not None:
            q = push_out(q[None], coll, 0.004)[0]
        if st.get("face_window") and in_face_window(q, fr, fw_margin)[0]:
            # long hair falls beside the face, never across it
            if info is not None:
                info["window"] = True
                if info.get("front_at") is None:
                    info["front_at"] = len(pts)
            sd = math.copysign(1.0, q[0] - fr["eye"][0])
            hw = float(face_halfwidth(q[2] - fr["eye"][2], fw_margin, fr, sd))
            q[0] = fr["eye"][0] + sd * hw
            if hug and q[2] > fr["eye"][2] - 0.07:
                # moved sideways out of the window it is still level with the forehead, in front of the temple
                # (which lies further back): back onto the skin
                rb2 = body.nearest(q, 0.05)
                if rb2 is not None:
                    hb2 = float((q - rb2[0]) @ body.FN[rb2[1]])
                    if hb2 > 0.005 or hb2 < 0.003:
                        q = rb2[0] + body.FN[rb2[1]] * min(max(hb2, 0.003), 0.005)
        if slide:
            q2 = floor_slide(p, q, fr, st, f_off, ds)
            if q2 is None:
                break
            if q2 is not q:
                vel = vunit(q2 - p)          # on along the floor
                slid += ds
                if slid > slide_max:
                    break
            q = q2
        elif floor_hit(q, fr, st, f_off):
            land(p, q)
            break
        if gfront is not None:
            q, _ = gfront.keep_front(q)
        p = q
        # a small gap (the shell's lower edge onto the hair lying on the back): carry on over the guide again
        r = surf.nearest_n(q)
        if r is not None and r[2] < 0.004 and free_len > 1.5 * ds and not detached:
            p, n, _, tri, bc = r
            free, free_len = False, 0.0
    if len(pts) < 3:
        return None
    if info is not None:
        info["over_ear"] = over_ear
        if edge_hang:
            info["edge_hang"] = True
    if st["long"] and st.get("end_trim"):
        # ragged ends: every lock stops at its own length (a hard common edge reads as a cut-out)
        L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(np.array(pts), axis=0), axis=1))])
        # (most a little, a few a lot: evenly spread trims of a few cm read as a row of icicles from behind)
        keep_len = L[-1] - st["end_trim"] * rng.random() ** 1.6 * min(1.0, L[-1] / 0.25)
        m = max(3, int((L <= keep_len).sum()))
        pts, nrm, tan = pts[:m], nrm[:m], tan[:m]
    return pts, nrm, tan


def loop_strand(surf, flow, p, length, bulge, rng, st, seg=0.006):
    """A strand that leaves the surface and arcs back to it (a curl flick or a flyaway breaking the outline)."""
    r = surf.nearest_n(p)
    if r is None:
        return None
    loc, n, _, tri, bc = r
    d = flow(loc, n, tri, bc)
    t = d - n * float(d @ n)
    if vlen(t) < 1e-6:
        return None
    t = vunit(rotate(vunit(t), n, rng.uniform(-0.6, 0.6)))
    m = max(4, int(length / seg))
    pts, nrm, tan = [], [], []
    if st["long"]:
        # long hair: the flyaway walks over the guide (a straight chord 5-10 cm long left the head's curve and
        # stuck out level from the hairline like a beak) and stops at its edge; never in front of the face
        fr = flow.fr
        if loc[1] < fr["y_face"] and loc[2] < fr["top"] - 0.02:
            return None
        ds = length / m
        q, nq = loc, n
        for k in range(m + 1):
            s = k / m
            h = 0.0015 + bulge * math.sin(math.pi * min(1.0, s * 1.15))
            pts.append(q + nq * h)
            nrm.append((nq, rng.uniform(-0.3, 0.3)))
            if k == m:
                break
            r2 = surf.nearest_n(q + t * ds)
            if r2 is None or r2[2] > 0.5 * ds:
                break
            q, nq = r2[0], r2[1]
            t = t - nq * float(t @ nq)
            if vlen(t) < 1e-6:
                break
            t = vunit(t)
        if len(pts) < 4 or in_face_window(np.array(pts), fr, 0.004).any():
            return None
        for k in range(len(pts)):
            tan.append(vunit(pts[min(k + 1, len(pts) - 1)] - pts[max(k - 1, 0)]))
        return pts, nrm, tan
    for k in range(m + 1):
        s = k / m
        h = 0.0015 + bulge * math.sin(math.pi * min(1.0, s * 1.15)) + (0.0 if st["long"] else 0.004 * s)
        q = loc + t * (length * s)
        r2 = surf.nearest_n(q)
        if r2 is None or r2[2] > 0.03:
            q2, n2 = q, n
        else:
            q2, n2 = r2[0], r2[1]
        pts.append(q2 + n2 * h)
        nrm.append((n2, rng.uniform(-0.3, 0.3)))
    for k in range(len(pts)):
        a = pts[max(k - 1, 0)]
        b = pts[min(k + 1, len(pts) - 1)]
        tan.append(vunit(b - a))
    return pts, nrm, tan


ATLAS_TIP = 0.65      # where the atlas' strands start thinning out toward their tips (v)
_STRIP_COVER = {}


def strip_cover(kind, nv=10, nu=12):
    """How much of what lies behind a card each atlas strip hides: (strips, nv, nu), the share of the strip's texels
    the alpha test keeps (alpha >= 0.5) by v (root -> tip) and across the card (u), from the neutral atlas."""
    if kind not in _STRIP_COVER:
        _, a = hair_atlas.make(kind)
        H, W = a.shape
        ns = len(hair_atlas.KINDS[kind]["strips"])
        sw = W // ns
        k = (a >= 0.5).astype(np.float32)
        out = np.zeros((ns, nv, nu), np.float32)
        for s in range(ns):
            blk = k[:, s * sw:(s + 1) * sw]
            for i in range(nv):
                rows = blk[int(i * H / nv):int((i + 1) * H / nv)]
                for j in range(nu):
                    out[s, i, j] = rows[:, int(j * sw / nu):int((j + 1) * sw / nu)].mean()
        _STRIP_COVER[kind] = out
    return _STRIP_COVER[kind]


class FrontCover:
    """The hair seen from the front (along +y; turned by `turn` radians about the vertical through `centre`: seen
    from a little to one side) over a grid in x and z: the body's frontmost depth per cell, and how much of it the
    cards in front of it hide (1 - the product of what each card lets through, by its strip's coverage across and
    along it and its root fade)."""

    def __init__(self, body, gx, gz, cover, turn=0.0, centre=None):
        self.gx, self.gz, self.cell = gx, gz, float(gx[1] - gx[0])
        self.cover = cover
        self.c, self.s = math.cos(turn), math.sin(turn)
        self.o = np.zeros(3) if centre is None else np.asarray(centre, np.float64)
        self.yb = np.full((len(gz), len(gx)), np.inf)
        V, T = self.rot(body.V), body.T
        for t in range(len(T)):
            P = V[T[t]]
            self._tri(P, lambda iz, ix, bc, P=P: np.minimum.at(self.yb, (iz, ix), bc @ P[:, 1]))
        self.trans = np.ones((len(gz), len(gx)))

    def rot(self, P):
        if self.s == 0.0:
            return P
        Q = np.array(P, np.float64).reshape(-1, 3) - self.o
        return np.stack([Q[:, 0] * self.c - Q[:, 1] * self.s, Q[:, 0] * self.s + Q[:, 1] * self.c, Q[:, 2]], 1) + self.o

    def _tri(self, P, fn):
        x, z = P[:, 0], P[:, 2]
        g0x, g0z, c = self.gx[0], self.gz[0], self.cell
        ia, ib = int(math.ceil((x.min() - g0x) / c)), int(math.floor((x.max() - g0x) / c))
        ja, jb = int(math.ceil((z.min() - g0z) / c)), int(math.floor((z.max() - g0z) / c))
        ia, ja = max(ia, 0), max(ja, 0)
        ib, jb = min(ib, len(self.gx) - 1), min(jb, len(self.gz) - 1)
        if ib < ia or jb < ja:
            return
        den = (z[1] - z[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (z[0] - z[2])
        if abs(den) < 1e-14:
            return
        xs, zs = np.meshgrid(self.gx[ia:ib + 1], self.gz[ja:jb + 1])
        l0 = ((z[1] - z[2]) * (xs - x[2]) + (x[2] - x[1]) * (zs - z[2])) / den
        l1 = ((z[2] - z[0]) * (xs - x[2]) + (x[0] - x[2]) * (zs - z[2])) / den
        l2 = 1.0 - l0 - l1
        m = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9)
        if not m.any():
            return
        jj, ii = np.nonzero(m)
        fn(jj + ja, ii + ia, np.stack([l0[m], l1[m], l2[m]], 1))

    def card_trans(self, V, UV, COL, base, m):
        """What one card (rows base.., m of them) lets through, per cell it covers in front of the body:
        {(iz, ix): transmission}."""
        out = {}
        strip = int(min(max(UV[base][0] * 8.0, 0.0), 7.0))
        tab = self.cover[strip]
        nv, nu = tab.shape

        def put(iz, ix, bc, P, uu, vv, aa):
            y = bc @ P[:, 1]
            u = np.clip(bc @ uu, 0.0, 0.999)
            v = np.clip(bc @ vv, 0.0, 0.999)
            a = bc @ aa
            ok = y < self.yb[iz, ix] - 0.001
            occ = tab[(v * nv).astype(int), (u * nu).astype(int)] * smoothstep(0.45, 0.8, a)
            for z_, x_, o_ in zip(iz[ok].tolist(), ix[ok].tolist(), occ[ok].tolist()):
                # (a card is one layer: where two of its triangles meet over a cell it counts once)
                out[(z_, x_)] = min(out.get((z_, x_), 1.0), 1.0 - o_)

        for k in range(m - 1):
            i = base + 2 * k
            q = [i, i + 1, i + 3, i + 2]
            P = self.rot(np.array([V[j] for j in q]))
            uu = np.array([0.0, 1.0, 1.0, 0.0])
            vv = np.array([1.0 - UV[j][1] for j in q])
            aa = np.array([COL[j][3] for j in q])
            for tri in ((0, 1, 2), (0, 2, 3)):
                tr = list(tri)
                self._tri(P[tr], lambda iz, ix, bc, tr=tr: put(iz, ix, bc, P[tr], uu[tr], vv[tr], aa[tr]))
        return out

    def add(self, tr):
        for (iz, ix), t in tr.items():
            self.trans[iz, ix] *= t

    def covered(self):
        return 1.0 - self.trans


def atlas_v(s, tip=None):
    """The atlas' v at s along a card (0 root, 1 tip). tip: the fraction of the card its thinning tips take (the
    atlas' last third, from ATLAS_TIP); None: all of the card evenly."""
    if tip is None or tip >= 1.0 - ATLAS_TIP:
        return s
    knee = 1.0 - tip
    return s * ATLAS_TIP / knee if s <= knee else ATLAS_TIP + (s - knee) * (1.0 - ATLAS_TIP) / tip


class Cards:
    """Ribbons along strands, lying on the guide (width across tangent x normal, turned by the twist)."""

    def __init__(self, strips=8):
        self.strips = strips
        self.V, self.UV, self.COL, self.NRM, self.F = [], [], [], [], []
        self.rows = []          # (first vertex, number of rows) per card
        self.n = 0
        self.by_layer = {}
        self.meta = []          # (width, taper, fade, tip) per card

    def add(self, pts, nrm, tan, width, strip, tone, fade, layer, taper=0.5, rng=None, tip=None, wk=None):
        """tone: the card's depth tone, or one per point (a lock hanging free over the face is not in the hair's
        shadow: its stretch there is lit, while its root stays as deep as its layer). tip: see atlas_v. wk (optional):
        a width factor per point (None: the card's width and taper alone)."""
        u0 = strip / self.strips + 0.003
        u1 = (strip + 1) / self.strips - 0.003
        m = len(pts)
        P = np.array(pts)
        L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        tot = max(L[-1], 1e-6)
        base = len(self.V)
        warm = rng.uniform(-0.04, 0.04) if rng is not None else 0.0
        tones = np.broadcast_to(np.asarray(tone, np.float64), (m,))
        w_prev = None
        for k in range(m):
            s = L[k] / tot
            n, twist = nrm[k]
            t = tan[k]
            w = np.cross(t, n)
            # the ribbon's width direction stays continuous along the card: where the strand runs along the guide's
            # normal (off a lip, down a brow) tangent x normal is ill-defined and flipped or swung 90 degrees from
            # row to row, and the ribbon twisted into a crumpled flat flake
            if w_prev is not None:
                wp = w_prev - t * float(w_prev @ t)
                if vlen(w) < 0.35 * max(vlen(wp), 1e-9):
                    w = wp
                elif float(w @ wp) < 0.0:
                    w = -w
            if vlen(w) < 1e-6:
                w = ortho(n)
            w = vunit(w)
            w_prev = w
            if twist:
                w = vunit(w * math.cos(twist) + n * math.sin(twist))
            hw = 0.5 * width * (1.0 - taper * s ** 1.5)
            if wk is not None:
                hw = hw * float(wk[k])
            self.V += [P[k] - w * hw, P[k] + w * hw]
            a = 1.0 if fade <= 0 else min(1.0, s / fade) ** 1.5
            # depth tone x a little warmth; 8-bit vertex colour in Godot, so never above 1 (the hue is in the atlas)
            tk = float(tones[k])
            c = (min(1.0, tk * (1 + warm)), min(1.0, tk), min(1.0, tk * (1 - warm)), a)
            self.COL += [c, c]
            # shading normal: the hair volume's (the guide's smoothed normal), so the cards light as one mass of
            # hair instead of as separate flakes
            self.NRM += [n, n]
            # Blender UV (u, 1 - v): root at the top of the atlas, UV.y = v (root -> tip) in glTF and Godot
            v = atlas_v(s, tip)
            self.UV += [(u0, 1.0 - v), (u1, 1.0 - v)]
        for k in range(m - 1):
            i = base + 2 * k
            self.F.append((i, i + 1, i + 3, i + 2))
        self.rows.append((base, m))
        self.meta.append((width, taper, fade, tip) if wk is None else (width, taper, fade, tip, list(wk)))
        self.n += 1
        self.by_layer[layer] = self.by_layer.get(layer, 0) + 1

    def trim(self, cuts):
        """Shorten cards: {card index: rows kept}; fewer than 3 rows drops the card. A shortened card is laid out
        again over its new length (UVs root -> tip, taper, root fade), so it still ends in the atlas' strand tips
        instead of a cut edge."""
        if not cuts:
            return
        bad = [j for j, k in cuts.items() if k < 3]
        for j, k in cuts.items():
            if k < 3:
                continue
            base, m = self.rows[j]
            width, taper, fade, tip = self.meta[j][:4]
            wk = self.meta[j][4] if len(self.meta[j]) > 4 else None
            if tip is not None:
                # (the same absolute tip on the shorter card)
                Lo = np.array(self.V[base:base + 2 * m:2])
                Lo = float(np.linalg.norm(np.diff(Lo, axis=0), axis=1).sum())
            A = np.array(self.V[base:base + 2 * k:2])
            B = np.array(self.V[base + 1:base + 2 * k:2])
            c = (A + B) * 0.5
            L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
            tot = max(L[-1], 1e-6)
            if tip is not None:
                tip = min(1.0, tip * Lo / tot)
                self.meta[j] = (width, taper, fade, tip)
            if wk is not None:
                self.meta[j] = (width, taper, fade, tip, wk[:k])
            for r in range(k):
                s = L[r] / tot
                w = B[r] - A[r]
                w = w / max(vlen(w), 1e-9)
                hw = 0.5 * width * (1.0 - taper * s ** 1.5)
                if wk is not None:
                    hw = hw * float(wk[r])
                self.V[base + 2 * r] = c[r] - w * hw
                self.V[base + 2 * r + 1] = c[r] + w * hw
                for i in (base + 2 * r, base + 2 * r + 1):
                    self.UV[i] = (self.UV[i][0], 1.0 - atlas_v(s, tip))
                    a = 1.0 if fade <= 0 else min(1.0, s / fade) ** 1.5
                    self.COL[i] = self.COL[i][:3] + (a,)
            self.rows[j] = (base, k)
        self._rebuild(set(bad))

    def refine(self, body, below_z, clear=0.0015, depth=2):
        """Rows added where a card's straight stretch between two rows cuts into the body: long hair's 2 cm steps
        over the curve of the nape and the upper back sank up to 6 mm into it between rows that lay on it, and the
        scan's clothes (painted with its hair) came through the hair as a flat tan patch. A new row halfway, out
        to `clear` over the skin, and again on either side (depth). Returns how many rows were added."""
        V, UV, COL, NRM, F, rows = [], [], [], [], [], []
        added = 0

        def row(i):
            return (self.V[i], self.V[i + 1], self.UV[i], self.UV[i + 1], self.COL[i], self.COL[i + 1],
                    self.NRM[i], self.NRM[i + 1])

        def mid(r0, r1, d):
            nonlocal added
            a = (r0[0] + r1[0]) * 0.5
            b = (r0[1] + r1[1]) * 0.5
            c = (a + b) * 0.5
            if c[2] >= below_z:
                return []
            r = body.nearest(c, 0.03)
            if r is None:
                return []
            n = body.FN[r[1]]
            h = float((c - r[0]) @ n)
            if h >= clear:
                return []
            a = a + n * (clear - h)
            b = b + n * (clear - h)
            uv = lambda p, q: ((p[0] + q[0]) * 0.5, (p[1] + q[1]) * 0.5)
            col = lambda p, q: tuple((x + y) * 0.5 for x, y in zip(p, q))
            m = (a, b, uv(r0[2], r1[2]), uv(r0[3], r1[3]), col(r0[4], r1[4]), col(r0[5], r1[5]),
                 vunit(r0[6] + r1[6]), vunit(r0[7] + r1[7]))
            added += 1
            if d <= 1:
                return [m]
            return mid(r0, m, d - 1) + [m] + mid(m, r1, d - 1)

        for base, m in self.rows:
            out = []
            for k in range(m):
                r = row(base + 2 * k)
                if out:
                    out += mid(out[-1], r, depth)
                out.append(r)
            nb = len(V)
            for r in out:
                V += [r[0], r[1]]
                UV += [r[2], r[3]]
                COL += [r[4], r[5]]
                NRM += [r[6], r[7]]
            for k in range(len(out) - 1):
                i = nb + 2 * k
                F.append((i, i + 1, i + 3, i + 2))
            rows.append((nb, len(out)))
        self.V, self.UV, self.COL, self.NRM, self.F, self.rows = V, UV, COL, NRM, F, rows
        return added

    def opaque_points(self, step=0.005, min_alpha=0.6, max_s=None):
        """Points every `step` along the cards' centre lines where they are opaque (past the root fade; with max_s,
        also short of that fraction of the card: the atlas' strands thin out over its last third)."""
        V = np.array(self.V).reshape(-1, 3)
        A = np.array(self.COL)[:, 3]
        S = 1.0 - np.array(self.UV)[:, 1]
        out = []
        for base, m in self.rows:
            c = (V[base:base + 2 * m:2] + V[base + 1:base + 2 * m:2]) * 0.5
            ok = A[base:base + 2 * m:2] > min_alpha
            if max_s is not None:
                ok = ok & (S[base:base + 2 * m:2] <= max_s)
            for k in range(m - 1):
                if ok[k] and ok[k + 1]:
                    n = max(1, int(math.ceil(vlen(c[k + 1] - c[k]) / step)))
                    out.append(c[k] + (c[k + 1] - c[k]) * (np.arange(n)[:, None] / n))
            if m and ok[m - 1]:
                out.append(c[m - 1:m])
        return np.concatenate(out) if out else np.zeros((0, 3))

    def drop(self, bad):
        """Remove whole cards (indices into rows)."""
        bad = set(int(b) for b in bad)
        if not bad:
            return
        self._rebuild(bad)

    def names(self):
        """Each card's layer (cards are added layer by layer)."""
        return [k for k, v in self.by_layer.items() for _ in range(v)]

    def _rebuild(self, bad):
        V, UV, COL, NRM, F, rows, layers, meta = [], [], [], [], [], [], {}, []
        names = self.names()
        for j, (base, m) in enumerate(self.rows):
            if j in bad:
                continue
            nb = len(V)
            V += self.V[base:base + 2 * m]
            UV += self.UV[base:base + 2 * m]
            COL += self.COL[base:base + 2 * m]
            NRM += self.NRM[base:base + 2 * m]
            for k in range(m - 1):
                i = nb + 2 * k
                F.append((i, i + 1, i + 3, i + 2))
            rows.append((nb, m))
            meta.append(self.meta[j])
            if j < len(names):
                layers[names[j]] = layers.get(names[j], 0) + 1
        self.V, self.UV, self.COL, self.NRM, self.F, self.rows, self.meta = V, UV, COL, NRM, F, rows, meta
        self.n = len(rows)
        self.by_layer = layers

    def arrays(self):
        return dict(V=np.array(self.V, np.float64).reshape(-1, 3), F=np.array(self.F, np.int64).reshape(-1, 4),
                    UV=np.array(self.UV, np.float32).reshape(-1, 2), COL=np.array(self.COL, np.float32).reshape(-1, 4),
                    NRM=np.array(self.NRM, np.float64).reshape(-1, 3), n=self.n, by_layer=dict(self.by_layer))


def eye_cuts(cards, fr, clear=0.0008):
    """{card: rows kept} for the cards that reach an eye opening (in front of the face, between the corners, lower
    than `clear` over the upper lid): each ends a row before the first row that does."""
    V = np.array(cards.V).reshape(-1, 3)
    if not len(V):
        return {}
    front = V[:, 1] < fr["eye_front"] + 0.03
    hit = np.zeros(len(V), bool)
    for l in fr["lids"]:
        # (and 3 mm past each corner, at the corner's height: a lock between the eyes, wider than its strand, hung
        # its edge over the inner corner as a soft dark smudge below it, Mano's left eye)
        inx = front & (V[:, 0] > l[0, 0] - 0.003) & (V[:, 0] < l[-1, 0] + 0.003)
        if inx.any():
            zl = np.interp(V[inx, 0], l[:, 0], l[:, 2])
            hit[np.nonzero(inx)[0][V[inx, 2] < zl + clear]] = True
    cuts = {}
    for j, (base, m) in enumerate(cards.rows):
        h = hit[base:base + 2 * m].reshape(m, 2).any(1)
        if h.any():
            cuts[j] = int(np.argmax(h))
    return cuts


def shadow_cut(V, fr):
    """Per card vertex, where it lies for the shadow pass (UV2, hair_scan.gdshader): x, how far it is in front of
    the face (1 within the eyes' outer corners and in front of the face's front, 0 past the temples or behind
    the face), y, its height over the brows (metres, + 0.5). The shader keeps hair in front of the face below a
    height over the brows (shadow_cut_z) out of the shadow map: it hangs a few mm to 2 cm off the skin, the shadow
    bias hides its shadow on the forehead and the lids, and only where the face falls far away behind it (the
    eye's inner corner beside the nose) did its lock tips' shadows show, an isolated two-lobed purple-brown blob
    that read as a bruise under Mano's left eye in the 3/4 close-up (thin hair's ends let most light through)."""
    V = np.atleast_2d(V)
    e, ef = fr["eye"], fr["eye_front"]
    front = 1.0 - smoothstep(ef + 0.02, ef + 0.04, V[:, 1])
    across = 1.0 - smoothstep(0.045, 0.058, np.abs(V[:, 0] - e[0]))
    # (the upper face only: long hair's front locks hang in front of the chest, and their shadow there is theirs)
    upper = smoothstep(e[2] - 0.04, e[2] - 0.025, V[:, 2])
    return np.stack([front * across * upper, 0.5 + np.clip(V[:, 2] - fr["brow_z"], -0.49, 0.49)],
                    1).astype(np.float32)


def part_distance(st, fr, p):
    c = fr["centre"]
    a = c + np.array(st["part"][0])
    b = c + np.array(st["part"][1])
    a[2] = b[2] = fr["top"]
    ab = b - a
    t = max(0.0, min(1.0, float((p - a) @ ab) / float(ab @ ab)))
    return vlen(p - (a + ab * t))


def part_near(st, fr, p, r=0.02):
    """Within r of the centre part sideways, between the front hairline and just behind the crown, on the upper
    head (the part line itself is drawn at the top of the head; the front of the part curves down the forehead)."""
    a, b = part_line(st, fr)
    return bool(abs(p[0] - a[0]) < r and a[1] - 0.02 < p[1] < b[1] + 0.01 and p[2] > fr["eye"][2] + 0.045)


def vnoise(p, scale, seed=0):
    """Smooth value noise in [0, 1) at a point, lattice `scale` metres apart (hash01 at the corners, smoothstep)."""
    q = np.asarray(p, np.float64) / scale
    i0 = np.floor(q)
    f = q - i0
    u = f * f * (3.0 - 2.0 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                c = (i0 + np.array([dx, dy, dz], np.float64)) * 0.001 + seed * 0.0137
                w = (u[0] if dx else 1 - u[0]) * (u[1] if dy else 1 - u[1]) * (u[2] if dz else 1 - u[2])
                out += w * hash01(c)
    return float(out)


def front_locks(st, fl, surf, shell_part, cards, fr, body, coll, gfront, flow):
    """(style front_locks, a dict, short hair, off by default) locks from the front hairline hanging onto the
    forehead. The curly flow runs every strand up and back from the hairline, so without them the hair ends at the
    shell's front edge in a clean hard arc. `n` locks spread across the forehead within `half` metres of the face's
    middle (jittered), each rooted `back` metres up the guide behind the shell's front edge and run forward and down
    over it (`sweep`: how far it slants sideways), then lying on the forehead for `hang` metres (lit as the forehead,
    3-5 mm off the skin, as a front_free fringe), never below `floor` over the brows; its free stretch waves sideways
    (`wave`: [amplitude, wavelength] metres, a loose curl), `clump` cards a lock (`w` wide, atlas strips `strips`,
    their strands thinning over the last `tip` metres). `short` (a dict of the same keys) adds a second set (shorter
    wisps breaking the edge between the locks). `temples` (a dict of the same keys, with `at`: offsets from the face's
    middle, each used on both sides, and `dir`: the lock's direction [outward, back, up] instead of forward and down)
    adds locks from the hairline's corners down over the temples. Their own random sequence (never the build's), added
    once all the rest is grown."""
    rng_f = np.random.default_rng(int(fl.get("seed", 23)))
    Vsm_, Tsm_ = shell_part
    E_, _, _ = boundary_edges(Tsm_)
    mids = (Vsm_[E_[:, 0]] + Vsm_[E_[:, 1]]) * 0.5
    e_, ef_ = fr["eye"], fr["eye_front"]
    curl = st.get("curl")
    groups = [dict(fl)]
    for key_ in ("short", "temples"):
        if fl.get(key_):
            g2 = dict(fl)
            g2.pop("n", None) if key_ == "temples" else None
            g2.update(fl[key_])
            g2["short"] = g2["temples"] = None
            groups.append(g2)
    n_locks = n_cards = 0
    for g in groups:
        at_ = g.get("at")
        n = 2 * len(at_) if at_ else int(g.get("n", 8))
        half = max(abs(float(a)) for a in at_) if at_ else float(g.get("half", 0.045))
        fe = mids[(mids[:, 1] < ef_ + 0.045) & (np.abs(mids[:, 0] - e_[0]) < half + 0.012) &
                  (mids[:, 2] > fr["brow_z"] + 0.005)]
        if not len(fe) or n < 1:
            continue
        if at_:
            xs = np.array([s_ * abs(float(a)) for a in at_ for s_ in (-1.0, 1.0)])
            sp = float(g.get("jit", 0.006))
        else:
            xs = np.linspace(-half, half, n) if n > 1 else np.zeros(1)
            sp = (2.0 * half / max(n - 1, 1))
        dir_ = g.get("dir")
        hang_r = tuple(float(v) for v in g.get("hang", (0.03, 0.055)))
        back_r = tuple(float(v) for v in g.get("back", (0.015, 0.03)))
        w_r = tuple(float(v) for v in g.get("w", (0.012, 0.02)))
        strips = tuple(int(v) for v in g.get("strips", (1, 2, 3, 4)))
        tone_r = tuple(float(v) for v in g.get("tone", (0.86, 1.0)))
        root_tone = tuple(float(v) for v in g.get("root_tone", (0.6, 0.78)))
        wave = g.get("wave") or (0.004, 0.03)
        sweep = float(g.get("sweep", 0.35))
        clump = int(g.get("clump", 2))
        floor = float(g.get("floor", 0.01))
        tip_l = float(g.get("tip", 0.012))
        for k in range(n):
            x_ = float(e_[0] + xs[k] + rng_f.uniform(-0.35, 0.35) * sp)
            near = fe[np.abs(fe[:, 0] - x_) < 0.005]
            hang = rng_f.uniform(*hang_r)
            back = rng_f.uniform(*back_r)
            sx = rng_f.uniform(-sweep, sweep)
            ph = rng_f.uniform(0.0, 2 * math.pi)
            amp = float(wave[0]) * rng_f.uniform(0.6, 1.2)
            lam = float(wave[1]) * rng_f.uniform(0.8, 1.25)
            w0 = rng_f.uniform(*w_r)
            if not len(near):
                continue
            edge = near[int(np.argmin(near[:, 1]))]

            d_l = np.array([sx, -0.6, -1.0]) if not dir_ else \
                np.array([float(dir_[0]) * math.copysign(1.0, x_ - float(e_[0])) + sx * 0.3, float(dir_[1]), float(dir_[2])])

            class LockFlow:
                origin = flow.origin

                def __call__(self, q, n_, tri=None, bc=None, _d=d_l):
                    return vunit(_d)

            made = False
            for c in range(clump):
                j_ = rng_f.normal(0, 0.0025, 3) * np.array([1.0, 0.4, 0.4]) if c else np.zeros(3)
                r = surf.nearest_n(edge + np.array([0.0, back * 0.55, back * 0.85]) + j_)
                hang_c = hang * (rng_f.uniform(0.7, 1.0) if c else 1.0)
                w_c = w0 * (rng_f.uniform(0.6, 0.85) if c else 1.0)
                strip_c = int(rng_f.choice(strips))
                tr_c = rng_f.uniform(*root_tone)
                tl_c = rng_f.uniform(*tone_r)
                ph_c = ph + (rng_f.uniform(-0.5, 0.5) if c else 0.0)
                lift_c = (rng_f.uniform(0.0015, 0.003), rng_f.uniform(0.002, 0.004))
                if r is None:
                    continue
                st_l = dict(st, front_free=hang_c, front_floor=floor, floor_slide=False, floor_wave=None,
                            floor_rise=0.0, floor_arch=None)
                info = {}
                s = grow(surf, LockFlow(), r[0], back * 1.6 + hang_c + 0.01, st["seg"], lift_c, st_l, fr, rng_f, body,
                         coll=coll, curl=curl, free_max=hang_c * 0.85, gfront=gfront, face_free=True, info=info)
                if s is None or info.get("free_at") is None:
                    continue
                P = np.array(s[0], np.float64)
                N = [nn for nn in s[1]]
                k0 = min(int(info["free_at"]), len(P) - 1)
                L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
                Lf = np.maximum(L - L[max(k0 - 1, 0)], 0.0) * (np.arange(len(P)) >= k0)
                # (the free stretch waves sideways over the skin: a loose curl, not a straight stroke)
                for i in range(k0, len(P)):
                    n_i = N[i][0]
                    t_i = vunit(P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)])
                    side = vunit(np.cross(t_i, n_i))
                    P[i] = P[i] + side * amp * math.sin(2 * math.pi * Lf[i] / lam + ph_c) * \
                        float(smoothstep(0.0, 0.01, Lf[i]))
                    rb = body.nearest(P[i], 0.05)
                    if rb is not None:
                        hb = float((P[i] - rb[0]) @ body.FN[rb[1]])
                        if hb < 0.0025:
                            P[i] = rb[0] + body.FN[rb[1]] * 0.0025
                T = [vunit(P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]) for i in range(len(P))]
                lit = smoothstep(0.0, 0.004, Lf) * (np.arange(len(P)) >= k0)
                tones = tr_c + (tl_c - tr_c) * lit
                Ls = float(L[-1])
                cards.add(list(P), N, T, width=w_c, strip=strip_c, tone=tones,
                          fade=min(1.0, 0.004 / max(Ls, 1e-6)), layer="front_lock", taper=0.45, rng=None,
                          tip=min(1.0, tip_l / max(Ls, 1e-6)))
                n_cards += 1
                made = True
            n_locks += int(made)
    log(f"front locks: {n_locks} locks over the forehead, {n_cards} cards")


def curl_tips(st, ct, cards, fr):
    """(style curl_tips, a dict, short hair, off by default) short curled ends breaking the hair's outline, which is
    otherwise a smooth even cap (the style's longer loops stand off the crown as spikes). `n` cards of the `layers`
    layers (picked with their own random sequence, never the build's) each get a curl branching off `at` of the way
    along them: an arc of radius `r` turning `turn` turns up off the hair (in the plane of the card's direction and
    the hair's normal there), drifting `drift` x its radius sideways per radian, `w` wide, atlas strips `strips`,
    toned `tone` (outer hair). None below `z` over the brows, in front of the face, or past the floor."""
    rng = np.random.default_rng(int(ct.get("seed", 31)))
    names = cards.names()
    layers = tuple(ct.get("layers", ("top",)))
    cand = [j for j, nm in enumerate(names) if nm in layers]
    if not cand:
        return
    n = min(int(ct.get("n", 60)), len(cand))
    at_r = tuple(float(v) for v in ct.get("at", (0.6, 0.85)))
    r_r = tuple(float(v) for v in ct.get("r", (0.003, 0.005)))
    turn_r = tuple(float(v) for v in ct.get("turn", (0.5, 0.75)))
    w_r = tuple(float(v) for v in ct.get("w", (0.005, 0.008)))
    strips = tuple(int(v) for v in ct.get("strips", (3, 4, 5)))
    tone_r = tuple(float(v) for v in ct.get("tone", (0.85, 1.0)))
    drift = float(ct.get("drift", 0.25))
    zmin = float(ct.get("z", 0.02))
    e_ = fr["eye"]
    made = 0
    for j in rng.permutation(cand):
        if made >= n:
            break
        base, m = cards.rows[j]
        if m < 4:
            continue
        Vc = np.array(cards.V[base:base + 2 * m])
        C = (Vc[0::2] + Vc[1::2]) * 0.5
        Nn = np.array(cards.NRM[base:base + 2 * m:2])
        L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))])
        k = int(np.clip(np.searchsorted(L, rng.uniform(*at_r) * L[-1]), 1, m - 2))
        p0 = C[k]
        t0 = vunit(C[k + 1] - C[k - 1])
        n0 = Nn[k] - t0 * float(Nn[k] @ t0)
        if vlen(n0) < 0.5:
            continue
        n0 = vunit(n0)
        if p0[2] < fr["brow_z"] + zmin or (p0[1] < e_[1] + 0.03 and abs(p0[0] - e_[0]) < 0.07 and
                                           p0[2] < fr["brow_z"] + 0.06):
            continue
        b0 = vunit(np.cross(t0, n0))
        r = rng.uniform(*r_r)
        th = 2 * math.pi * rng.uniform(*turn_r)
        side = rng.choice((-1.0, 1.0))
        seg = max(6, int(th * r / 0.0025))
        pts = [p0 + r * (math.sin(th * i / seg) * t0 + (1.0 - math.cos(th * i / seg)) * n0) +
               b0 * side * drift * r * th * i / seg for i in range(seg + 1)]
        if any(floor_hit(q_, fr, st) for q_ in pts):
            continue
        tan = [vunit(pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]) for i in range(len(pts))]
        cards.add(pts, [(n0, 0.0)] * len(pts), tan, width=rng.uniform(*w_r), strip=int(rng.choice(strips)),
                  tone=rng.uniform(*tone_r), fade=0.3, layer="curl_tip", taper=0.5, rng=None)
        made += 1
    log(f"curl tips: {made} curled ends off the {'/'.join(layers)} cards")


def lock_clump(cards, lc, surf, flow, fr):
    """(style lock_clump, a dict, short hair, off by default) the cards gathered into bigger locks with dark grooves
    between them, where the cards alone read as an even fine-grained curl texture under a smooth rounded outline at
    the dialogue camera. Evenly spaced streamlines of the flow over the guide (lock spines `sep` apart, traced `step`
    at a time) are cut into locks `seg` long, each waving sideways (an S: `amp`, `period`) and in and out (`bump`);
    every card of `layers` belongs to the lock nearest its middle (within 1.5 sep) and each of its rows moves `pull`
    of the way toward that lock's spine (the ribbon `narrow` x as wide) and out along the normal by `bulge` at the
    lock's core (`core` x sep), in by `sink` at its flanks (the grooves deepen without the outline growing: bulge
    raises the hair's top). `flare` {n, h, from, ny, nz, z, gap}: n locks on the outline seen from the front (the
    guide's normal within ny of the sideways plane and its upward part at most nz, at least z over the brows, centres
    `gap` apart) lift their ends off the hair, h (a range, metres) along the normal from `from` of the way along the
    lock to its end. Not near the face or the ears. Its own random sequence; runs before the coverage pass, which
    fills what the locks bare."""
    rng = np.random.default_rng(int(lc.get("seed", 31)))
    sep = float(lc.get("sep", 0.036))
    step = float(lc.get("step", 0.004))
    seg_r = tuple(lc.get("seg", (0.05, 0.08)))
    amp_r = tuple(lc.get("amp", (0.004, 0.008)))
    per_r = tuple(lc.get("period", (0.045, 0.065)))
    pull = float(lc.get("pull", 0.6))
    narrow = float(lc.get("narrow", 1.0))
    bulge = float(lc.get("bulge", 0.003))
    bump = float(lc.get("bump", 0.0))
    sink = float(lc.get("sink", 0.0))
    core = float(lc.get("core", 0.35))
    layers = set(lc.get("layers", ("mid", "top", "fill", "loops")))
    max_len = float(lc.get("max_len", 0.3))
    cell = sep * 0.5
    grid = {}

    def key(p):
        return tuple(np.floor(p / cell).astype(int).tolist())

    def near(p, r):
        k = key(p)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in grid.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                        if vlen(q - p) < r:
                            return True
        return False

    def trace(p0, sign):
        r = surf.nearest_n(p0)
        if r is None:
            return []
        p, n, _, tri, bc = r
        pts, t_prev, L = [], None, 0.0
        while L < max_len:
            d = flow(p, n, tri, bc) * sign
            t = d - n * float(d @ n)
            if vlen(t) < 1e-6:
                break
            t = vunit(t)
            if t_prev is not None:
                if float(t @ t_prev) < 0.3:
                    break
                t = vunit(t_prev * 0.5 + t * 0.5)
            r = surf.nearest_n(p + t * step)
            if r is None or r[2] > 0.5 * step:
                break
            p, n, _, tri, bc = r
            if near(p, 0.5 * sep):
                break
            pts.append(p)
            t_prev = t
            L += step
        return pts

    lines = []
    for i in rng.permutation(len(surf.V)):
        p0 = surf.V[i]
        if near(p0, 0.9 * sep):
            continue
        r = surf.nearest_n(p0)
        if r is None:
            continue
        pts = trace(p0, -1.0)[::-1] + [r[0]] + trace(p0, 1.0)
        if len(pts) * step < 0.02:
            continue
        P = np.array(pts)
        lines.append(P)
        for q in P:
            grid.setdefault(key(q), []).append(q)
    if not lines:
        return
    # each line: arclength, frame, the locks along it (their own phase, amplitude, period, bulge; start and end)
    S, Sl, Su, SN, SB, Sk, locks = [], [], [], [], [], [], []
    for li, P in enumerate(lines):
        u = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        T = np.gradient(P, axis=0)
        T = T / np.maximum(np.linalg.norm(T, axis=1), 1e-9)[:, None]
        N = np.array([surf.nearest_n(p)[1] for p in P])
        B = np.cross(N, T)
        B = B / np.maximum(np.linalg.norm(B, axis=1), 1e-9)[:, None]
        # the first lock starts part way in (locks along neighbouring lines end at different places)
        cuts = [-rng.uniform(0.0, seg_r[1])]
        while cuts[-1] < u[-1]:
            cuts.append(cuts[-1] + rng.uniform(*seg_r))
        lk = np.searchsorted(np.array(cuts[1:]), u, side="right")
        base = len(locks)
        for c in range(len(cuts)):
            locks.append((rng.uniform(0, 2 * math.pi), rng.uniform(*amp_r), rng.uniform(*per_r),
                          rng.uniform(0.7, 1.3), cuts[c], cuts[c + 1] if c + 1 < len(cuts) else cuts[c] + seg_r[1]))
        S.append(P); Sl.append(np.full(len(P), li)); Su.append(u); SN.append(N); SB.append(B); Sk.append(base + lk)
    S, Sl, Su = np.concatenate(S), np.concatenate(Sl), np.concatenate(Su)
    SN, SB, Sk = np.concatenate(SN), np.concatenate(SB), np.concatenate(Sk)
    e_, ef_, bz_ = fr["eye"], fr["eye_front"], fr["brow_z"]
    # (flare) the locks whose ends lift off the outline
    lift = {}
    fl = lc.get("flare")
    if fl:
        ny, zmin, gap = float(fl.get("ny", 0.45)), float(fl.get("z", 0.03)), float(fl.get("gap", 0.05))
        nz = float(fl.get("nz", 1.0))
        cand = []
        for k_ in np.unique(Sk):
            on = np.nonzero(Sk == k_)[0]
            if len(on) * step < 0.04:
                continue
            c = on[len(on) // 2]
            p, n = S[c], SN[c]
            if abs(float(n[1])) > ny or float(n[2]) > nz or p[2] < bz_ + zmin or p[1] < ef_ + 0.03:
                continue
            if ear_weight(p[None], fr, 0.03, 0.05)[0] > 0.0:
                continue
            cand.append((int(k_), p))
        picked = []
        for ci in rng.permutation(len(cand)):
            if len(picked) >= int(fl.get("n", 8)):
                break
            k_, p = cand[ci]
            if all(vlen(p - q) > gap for _, q in picked):
                picked.append((k_, p))
        h_r = tuple(fl.get("h", (0.008, 0.015)))
        for k_, _ in picked:
            lift[k_] = rng.uniform(*h_r)
    pts = Points(S)
    names = cards.names()
    V = np.array(cards.V, np.float64).reshape(-1, 3)
    n_mv, n_fl, moved = 0, 0, []
    for j, (b0, m) in enumerate(cards.rows):
        if names[j] not in layers:
            continue
        A = V[b0:b0 + 2 * m:2]
        Bv = V[b0 + 1:b0 + 2 * m:2]
        C = (A + Bv) * 0.5
        d_, i_ = pts.nearest(C.mean(0)[None])
        if not np.isfinite(d_[0]) or d_[0] > 1.5 * sep:
            continue
        li, lk = int(Sl[i_[0]]), int(Sk[i_[0]])
        ph, am, pe, bf, c0, c1 = locks[lk]
        on = np.nonzero(Sl == li)[0]
        # each row's nearest sample on that line
        k = on[np.argmin(np.linalg.norm(C[:, None, :] - S[on][None], axis=2), axis=1)]
        ang = 2 * math.pi * Su[k] / pe + ph
        Sp = S[k] + SB[k] * (am * np.sin(ang))[:, None]
        x = np.einsum("ij,ij->i", C - Sp, SB[k])
        # never near the face: the front hairline and the temples keep their cards where they grew
        front = 1.0 - smoothstep(ef_ + 0.03, ef_ + 0.06, C[:, 1])
        w = 1.0 - front * (1.0 - smoothstep(bz_ + 0.03, bz_ + 0.06, C[:, 2]))
        w = w * (1.0 - ear_weight(C, fr, 0.03, 0.05))
        xn = x * (1.0 - pull)
        prof = np.exp(-(xn / max(core * sep, 1e-6)) ** 2)
        hn = bulge * bf * prof + bump * np.cos(ang) * prof - sink * (1.0 - prof)
        if lk in lift:
            tt = (Su[k] - c0) / max(c1 - c0, 1e-6)
            hn = hn + lift[lk] * smoothstep(float(fl.get("from", 0.4)), 1.0, tt)
            n_fl += 1
        D = (-SB[k] * (x * pull)[:, None] + SN[k] * hn[:, None]) * w[:, None]
        hw = (Bv - A) * 0.5 * (1.0 - (1.0 - narrow) * w)[:, None]
        Cn = C + D
        V[b0:b0 + 2 * m:2] = Cn - hw
        V[b0 + 1:b0 + 2 * m:2] = Cn + hw
        moved.append(np.linalg.norm(D, axis=1).max())
        n_mv += 1
    cards.V = [v for v in V]
    mv = np.array(moved) if moved else np.zeros(1)
    log(f"lock clump: {len(lines)} lock lines {sep * 100:.1f} cm apart, {len(locks)} locks, {n_mv} cards drawn in "
        f"(moved p50/p90 {np.percentile(mv, 50) * 1000:.1f} / {np.percentile(mv, 90) * 1000:.1f} mm), "
        f"{len(lift)} locks flared ({n_fl} cards)")


def build_hair(st, surf, flow, base, fr, rng, coll=None, drape=None, shell_part=None, arms=None, gfront=None,
               cover_mask=None):
    cards = Cards(8)
    area = float(surf.area.sum())
    ear_side = None
    ear_locks = []
    # (style ear_wisp, off by default: the locks over the ears as fine wisps, not tufts. Keys: w, their width x w;
    # strips, the atlas strips they take (from the draws they had); step, the edge locks' spacing (m); tip, the
    # fraction of a lock its strands thin out over. Cut from the top layer's wide loose strips, 1-1.7 cm wide and
    # opaque to their ends in a coarse mip, they hung over Mano's ear tops as chunky black tufts with blunt ends)
    ew = st.get("ear_wisp") or None
    ew_w = float(ew.get("w", 1.0)) if ew else 1.0
    ew_strips = tuple(ew.get("strips", (4, 5, 6))) if ew else (4, 5, 6)
    ew_tip = ew.get("tip") if ew else None
    if st.get("ear_drape") and st.get("ear_free") and not st["long"]:
        ear_side = EarSide(base["body"].V, base["body"].T, fr)
        log(f"ears: {len(ear_side.sides)} side height fields, hair over them drapes on their outside")
    log(f"guide surface {area * 1e4:.0f} cm^2, {len(surf.V)} verts")
    t0 = time.time()
    curl = st.get("curl")
    body = base["body"]

    def on_guide(q):
        r = surf.nearest_n(q, 0.03)
        return None if r is None else (r[0], r[1])

    def strand(p, name, lrange, wrange, hrange, trange, strips, fade, fade_abs=None, taper=None, max_len=None):
        extra = 0.0
        if not st["long"] and on_brows(p, fr)[0]:
            # never rooted on the brows (the coverage pass rooted cards in the bare scalp a style's brow_band takes
            # in, under the fringe: with the guide's normal there pointing down along the strand, their ribbons
            # twisted into black Z-shaped flakes over Mano's right eye), but moved up over the guide to just above
            # them, longer by as much and opaque within a few mm, so the card still covers the spot it was for
            # (refused, the band over the brows was left to the faded roots of cards from higher up: a soft black
            # smear of the cap with no strands)
            p, extra = off_brows(p, fr, on_guide, rng)
            if p is None:
                return False
        if st["long"]:
            length = st["max_len"] if max_len is None else max_len
            # near the part: within 2 cm of it sideways, anywhere from the front hairline back to the crown (by the
            # 3D distance to the line at the top of the head, the front of the part was "far", its cards faded in
            # over 5 cm and the part opened into a wedge of bare forehead)
            near_part = st.get("part") and part_near(st, fr, p)
            # the root fade in absolute terms (a fraction of a 75 cm card would fade in over 20 cm)
            f = (fade_abs if fade_abs is not None else (0.004 if near_part else 0.05)) / length
        else:
            length = rng.uniform(*lrange) + extra
            f = fade if fade_abs is None else fade_abs / length
            if extra:
                f = min(f, max(0.003, 0.6 * extra) / length)
        lift = (rng.uniform(*hrange), rng.uniform(*hrange) * (1.15 if name == "top" else 1.0))
        if st.get("deflate"):
            # where the front of the guide was pulled in flat (deflate), the layers lie flat too: the top layer's
            # 5-9 mm stood off the temple and ended in the air at the guide's edge, a stiff card like a flyaway
            ef_ = fr["eye_front"]
            wd = float((1.0 - smoothstep(ef_ + 0.03, ef_ + 0.07, p[1])) *
                       smoothstep(fr["eye"][2], fr["eye"][2] + 0.03, p[2]))
            lift = (lift[0] * (1.0 - 0.6 * wd), lift[1] * (1.0 - 0.6 * wd))
        if fr.get("crown_w") is not None:
            # (style crown) rooted on the lowered crown, the layers lie flatter (no draw)
            z0_, z1_, kl_ = fr["crown_w"]
            wc_ = float(smoothstep(z0_, z1_, p[2]))
            lift = (lift[0] * (1.0 - (1.0 - kl_) * wc_), lift[1] * (1.0 - (1.0 - kl_) * wc_))
        fm = st["free_max"] * rng.uniform(0.25 if st["long"] else 0.3, 1.0)
        # (the under layer's wide dense cards stay on the guide: let down over the face they hung as solid dark
        # slabs, Mano's black bar over the eye)
        info = {}
        s = grow(surf, flow, p, length, st["seg"], lift, st, fr, rng, body, coll=coll, curl=curl, free_max=fm,
                 drape=drape, gfront=gfront, face_free=name != "under", info=info, ears=ear_side)
        if s is None:
            return False
        s_full = s
        w_ = rng.uniform(*wrange)
        strip_ = int(rng.choice(strips))
        tone_ = rng.uniform(*trange)
        if st.get("window_dense") and info.get("window"):
            # (style window_dense, long hair, off by default) a strand held off the face window, at the curtain's
            # front edge beside the cheek, takes one of the dense strips (0-2, from its own draw): the loose and
            # wispy strips' sparse clump edges, a stack of them along the window's edge, read as a comb of thin dark
            # and skin-coloured lines down the cheek (Anisha, 3/4 view)
            strip_ = strip_ % 3
        tip_ = None
        wk_ = None
        lit = np.zeros(len(s[0]))
        ear_lock = None
        if not st["long"] and (info.get("over_ear") or info.get("edge_hang")) and info.get("free_at") is not None:
            # hanging free over an ear (or in front of it, below the glasses' arm), it is outer hair, in the light:
            # no darker there than a top-layer strand (a mid layer's tone hung below Mano's arm in front of the ear
            # as two chunky black tufts)
            P_ = np.array(s[0])
            k0 = int(info["free_at"])
            Lf = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))])
            Lf = np.maximum(Lf - Lf[min(max(k0 - 1, 0), len(Lf) - 1)], 0.0) * (np.arange(len(P_)) >= k0)
            lit = np.maximum(lit, smoothstep(0.0, 0.003, Lf) * (np.arange(len(P_)) >= k0))
            if name == "under":
                # an under-layer strand: its card ends at the guide's edge as before, and its stretch over the ear
                # is a lock of its own drawn as a top-layer one (narrower, from the wispy strips, lit; mapped from
                # its own draws, so the random sequence does not shift). The whole card hanging on, wide and dense,
                # hung over the ear's top as a flat black tab; the whole card narrowed, the temple above the glasses'
                # hinge thinned out and the frame's top bar showed through it in grey stripes
                top_l = next(l for l in st["layers"] if l[0] == "top")
                lo, hi = wrange
                if len(P_) - (k0 - 1) >= 3:
                    ear_lock = (k0 - 1, ew_w * (top_l[3][0] + (w_ - lo) / max(hi - lo, 1e-9) *
                                                (top_l[3][1] - top_l[3][0])),
                                ew_strips[strip_ % len(ew_strips)] if ew else 4 + strip_ % 3)
                if k0 >= 3:
                    s = (s[0][:k0], s[1][:k0], s[2][:k0])
                    lit = lit[:k0] * 0.0
                else:
                    s = None
        if st.get("front_free") and not st["long"] and s is not None:
            # a strand that ends on the forehead (the fringe's tips): a narrower card from the wispy strips, so
            # the fringe thins out over the skin instead of ending in a solid edge
            # (only some of them, `front_wisp`: the strip is the card's whole length, and with every lock over the
            # forehead wispy the fringe was see-through down its whole lower half, a dark veil with no strands
            # where the cap showed through it)
            q_ = s[0][-1]
            ends_front = q_[1] < fr["eye_front"] + 0.035 and abs(q_[0] - fr["eye"][0]) < 0.07 and \
                q_[2] < fr["brow_z"] + 0.02
            if ends_front and rng.random() < st.get("front_wisp", 1.0):
                w_ *= 0.75
                strip_ = max(strip_, 4)
            if ends_front and st.get("front_tip"):
                # its strands thin out over its last `front_tip` metres only (the atlas' tips over a card's last
                # third: a 7 cm lock ending at the fringe's floor was see-through from 2.5 cm above it, and the
                # fringe's lower half read as a dark veil over the brows instead of locks)
                Ls = float(np.linalg.norm(np.diff(np.array(s[0]), axis=0), axis=1).sum())
                tip_ = min(1.0, float(st["front_tip"]) / max(Ls, 1e-6))
            # and its stretch hanging below the brows, or running along the fringe's edge, is in the light, not in
            # the hair's depth: no darker than a top-layer strand (an inner layer's tone there read as a black card
            # on the skin, or as a dark lip along the edge)
            P_ = np.array(s[0])
            fz = np.array([floor_z(q, fr, st) if floor_z(q, fr, st) is not None else -1.0 for q in P_])
            ex = ((P_[:, 1] < fr["eye_front"] + 0.035) & (np.abs(P_[:, 0] - fr["eye"][0]) < 0.07)) * \
                np.maximum(1.0 - smoothstep(fr["brow_z"] - 0.004, fr["brow_z"] + 0.008, P_[:, 2]),
                           (fz > 0) * (1.0 - smoothstep(0.003, 0.01, P_[:, 2] - fz)))
            lit = np.maximum(lit, ex)
        ct_ = st.get("clump_tone") or None
        if ct_ and name in tuple(ct_.get("layers", ("mid", "top", "fill", "hairline"))):
            # (style clump_tone, a dict, off by default) the card's tone x 1 +- `amp` by a smooth noise of its root
            # over `scale` metres: neighbouring cards share it, so the hair reads as lighter and darker clumps instead
            # of an even fine frizz that goes to one black mass at night. No draw
            k_ = vnoise(p, float(ct_.get("scale", 0.022)), int(ct_.get("seed", 5)))
            tone_ = float(min(1.0, max(0.2, tone_ * (1.0 + float(ct_.get("amp", 0.25)) * (2.0 * k_ - 1.0)))))
        tone0 = tone_
        if lit.any():
            tone_ = tone_ + (max(tone_, 0.82) - tone_) * lit
        if st.get("roll_drape") and not st["long"] and info.get("lie_at") is not None and s is not None:
            # (roll_drape) its stretch lying on over the temple: no darker than the drape's `tone` from where it left
            # the roll (over 5 mm), and its strands thin out over that stretch (the atlas' tips), so the curtain's
            # ends feather out on the temple instead of ending in a common edge. No draw
            P_ = np.array(s[0])
            k0 = min(int(info["lie_at"]), len(P_) - 1)
            Lw = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))])
            Lr = np.maximum(Lw - Lw[k0], 0.0) * (np.arange(len(P_)) >= k0)
            lw = smoothstep(0.0, 0.005, Lr) * (np.arange(len(P_)) >= k0)
            td_ = float(st["roll_drape"].get("tone", 0.6))
            tone_ = tone_ + (np.maximum(tone_, td_) - tone_) * lw
            if Lw[-1] > 1e-6:
                tip_ = min(1.0, max(float(st["roll_drape"].get("tip", 0.25)), float(Lr[-1] / Lw[-1])))
            if st["roll_drape"].get("w") is not None and Lr[-1] > 1e-6:
                # (`w`: the card narrows to w x its width over that stretch: lying on the temple at full width, a
                # drape read as a lighter flat plane with hard straight edges under the near roll, 3/4 view)
                wk_ = 1.0 - (1.0 - float(st["roll_drape"]["w"])) * np.clip(Lr / Lr[-1], 0.0, 1.0)
        if st["long"] and st.get("front_lit") and info.get("front_at") is not None and s is not None:
            # (style front_lit = a tone, long hair, off by default) a strand hanging free in front of the ears (off
            # the guide's front edge, or held off the face window) is the curtain's outer hair beside the face, in
            # the light: from where it first hung free there (over 2 cm) no darker than front_lit. With their layer's
            # depth tone, under-layer cards from the front hairline lay over the lit strands across a hand's width
            # at mouth height: a dark band with a hard straight top edge across the curtain, from the 3/4 view
            #. No draw
            P_ = np.array(s[0])
            k0 = min(int(info["front_at"]), len(P_) - 1)
            Lw = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))])
            Lw = np.maximum(Lw - Lw[k0], 0.0) * (np.arange(len(P_)) >= k0)
            lw = smoothstep(0.0, 0.02, Lw) * (np.arange(len(P_)) >= k0)
            fl_ = float(st["front_lit"])
            tone_ = tone_ + (np.maximum(tone_, fl_) - tone_) * lw
        if s is not None:
            cards.add(*s, width=w_, strip=strip_, tone=tone_,
                      fade=f, layer=name, taper=taper if taper is not None else st.get("taper", 0.55 if st["long"] else 0.5),
                      rng=rng, tip=tip_, wk=wk_)
        if ear_lock is not None:
            # (added once all the rest is grown, as their own layer: seen by the coverage pass, they changed which
            # fills it grew and reshuffled the random sequence of everything after)
            k1, w1, strip1 = ear_lock
            q = (s_full[0][k1:], s_full[1][k1:], s_full[2][k1:])
            Lq = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(np.array(q[0]), axis=0), axis=1))])
            # (lit from its root: it starts at the shell's edge, where its root fades in over the hair there; with
            # the under layer's deep tone over its first few mm it hung on the ear's top as a black clump)
            tq = max(tone0, 0.82) + 0.0 * Lq
            ear_locks.append((q, w1, strip1, tq, min(1.0, 0.003 / max(float(Lq[-1]), 1e-6)), ew_tip))
        return True

    for (name, per_m2, lrange, wrange, hrange, trange, strips, fade) in st["layers"]:
        count = int(per_m2 * area)
        P, _ = surf.sample(count, rng)
        made = sum(strand(p, name, lrange, wrange, hrange, trange, strips, fade) for p in P)
        log(f"layer {name}: {made}/{count} cards")
    if st.get("part"):
        # the part's edges: cards rooted 1.1-1.6 mm either side of the line, running straight off it, with no root
        # fade (a fade there widens the part into a stripe)
        a, b = part_line(st, fr)
        top_l = next(l for l in st["layers"] if l[0] == "top")
        made = n_try = 0
        for y in np.arange(a[1] + 0.003, b[1] - 0.012, 0.0022):
            for side in (-1.0, 1.0):
                q = np.array([a[0] + side * rng.uniform(0.0011, 0.0016), y, fr["top"] + 0.01])
                # straight down onto the scalp (the guide's band there), not onto the shell beside a slit
                rb = body.nearest(q, 0.1)
                if rb is None:
                    continue
                q = rb[0] + body.FN[rb[1]] * 0.0012
                q[0] = a[0] + side * abs(q[0] - a[0])
                r = surf.nearest_n(q)
                if r is None or r[2] > 0.004:
                    continue
                n_try += 1
                made += strand(r[0], "part", top_l[2], top_l[3], (0.0005, 0.0015), (0.85, 1.0), top_l[6], 0.0,
                               fade_abs=0.0008)
        log(f"part edges: {made}/{n_try} cards")
    if st.get("lock_clump") and not st["long"] and cards.n:
        # (off by default) before the coverage pass, which fills what it bares
        lock_clump(cards, st["lock_clump"], surf, flow, fr)
    # coverage: every guide vertex must lie under an opaque stretch of some card; where none passes, a card is
    # rooted a little upstream (so it is opaque by the time it gets there)
    mid = next(l for l in st["layers"] if l[0] == "mid")
    for it in range(2):
        cp = cards.opaque_points()
        d, _ = Points(cp).nearest(surf.V)
        # (cover_mask: the guide vertices to cover; the default, all of them)
        holes = surf.V[(d > st["cover"]) & (cover_mask if cover_mask is not None else True)]
        made = 0
        for v in holes:
            r = surf.nearest_n(v)
            if r is None:
                continue
            loc, n, _, tri, bc = r
            dd = flow(loc, n, tri, bc)
            t = dd - n * float(dd @ n)
            up = loc - (vunit(t) if vlen(t) > 1e-6 else t) * (0.02 if st["long"] else 0.01)
            # (long hair: a fill only has to cover its hole; full-length fills doubled the card count)
            made += strand(up, "fill", mid[2], mid[3], mid[4], mid[5], mid[6], 0.1, fade_abs=0.008,
                           max_len=st.get("fill_len"))
        log(f"coverage pass {it}: {len(holes)} bare guide verts -> {made} cards")
        if not len(holes):
            break
    if st["long"]:
        # slits: long hair's cards are wide and their opaque cores narrow, and where the flow parts (down the
        # middle of the back, the strands of each side heading to their own side) a slit between two cards' cores
        # stays open between the guide's vertices, a few mm wide in the rest pose and wider in the idle pose: the
        # cap or the clothes showed through as a smooth patch mid-way down the back hair. Dense samples
        # over the guide, a tighter cover, and only where cards lie all round (inside the hair, not its edges)
        cp = cards.opaque_points()
        pts_c = Points(cp)
        P, _ = surf.sample(int(float(surf.area.sum()) / 0.005 ** 2), rng)
        d, _ = pts_c.nearest(P)
        cand = P[d > 0.006]
        holes = []
        for v in cand:
            r = surf.nearest_n(v)
            if r is None:
                continue
            n = r[1]
            a1 = ortho(n)
            a2 = np.cross(n, a1)
            quad = set()
            for j, _ in pts_c.within(v, 0.014):
                o = cp[j] - v
                quad.add((float(o @ a1) > 0, float(o @ a2) > 0))
            if len(quad) == 4:
                holes.append(v)
        made = 0
        kept = []
        for v in holes:
            if any(vlen(v - k) < 0.006 for k in kept):
                continue
            kept.append(v)
            r = surf.nearest_n(v)
            loc, n, _, tri, bc = r
            dd = flow(loc, n, tri, bc)
            t = dd - n * float(dd @ n)
            up = loc - (vunit(t) if vlen(t) > 1e-6 else t) * 0.02
            made += strand(up, "fill", mid[2], mid[3], mid[4], mid[5], mid[6], 0.1, fade_abs=0.008,
                           max_len=st.get("fill_len"))
        log(f"coverage, slits: {len(cand)} of {len(P)} samples bare, {len(holes)} inside the hair, "
            f"{len(kept)} spots -> {made} cards")
    # the hairline: cards rooted on the scalp mask's iso-line (thinner, with a sharp root)
    hl = st["hairline"]
    pts = base["hairline"]
    moved = base.get("hairline_moved")
    moved = np.zeros(len(pts), bool) if moved is None or len(moved) != len(pts) else moved
    made = n_target = 0
    if len(pts):
        # one root every `step` along the iso-line: where the head's mesh is dense (round a brow the mask takes
        # in) it crossed the iso-line every millimetre, and 4 cards per crossing stacked into a solid black shard
        # (Mano, by his right eye: 70 cards from two spots)
        P_ = Points(pts)
        taken = np.zeros(len(pts), bool)
        keep_ = []
        for i in range(len(pts)):
            if not taken[i]:
                keep_.append(i)
                for j, _ in P_.within(pts[i], hl["step"]):
                    taken[j] = True
        if len(keep_) < len(pts):
            log(f"hairline: {len(pts)} iso points thinned to {len(keep_)} ({hl['step'] * 1000:.1f} mm apart)")
        pts = pts[keep_]
        moved = moved[keep_]
        kd = Points(pts)
        per = max(1, int(round(0.01 / hl["step"])))
        for i, p in enumerate(pts):
            nb = [pts[j] for j, _ in kd.near_n(p, 3) if j != i]
            for _ in range(per):
                q = p.copy()
                if nb:
                    o = nb[int(rng.integers(len(nb)))]
                    q = q + (o - q) * rng.uniform(0.0, 0.5)
                n_target += 1
                # (moved up off the brows: rooted under the fringe, not at a hairline, so the root fades in over a
                # few mm instead of starting as a hard edge)
                made += strand(q, "hairline", hl["length"], hl["width"], (0.0003, 0.0009), hl["tone"],
                               hl["strips"], 0.02, fade_abs=0.004 if moved[i] else None)
    # under the shell's lip at the front: short cards from the hairline up over the scalp itself (the style's flow,
    # without the texture's), so the band between the hairline and the shell's edge has strands
    pc = base.get("hairline_cov")
    if pc is not None and len(pc) and base.get("scalp") is not None:
        class StyleOnly:
            origin = flow.origin

            def __call__(self, q, n, tri=None, bc=None):
                return flow.style(q)

        style_only = StyleOnly()
        n_cov = 0
        for p in pc:
            for _ in range(per if len(pts) else 4):
                q = p + rng.normal(0, 0.0015, 3)
                s_ = grow(base["scalp"], style_only, q, rng.uniform(*(hl["length"] or (0.025, 0.05))), st["seg"],
                          (0.0003, 0.0012), st, fr, rng, body, coll=coll, curl=curl, free_max=0.0, gfront=gfront)
                n_target += 1
                if s_ is not None:
                    cards.add(*s_, width=rng.uniform(*hl["width"]), strip=int(rng.choice(hl["strips"])),
                              tone=rng.uniform(*hl["tone"]), fade=0.02, layer="hairline", taper=0.5, rng=rng)
                    made += 1
                    n_cov += 1
        log(f"hairline under the shell's lip: {n_cov} cards")
    # where the shell's own edge is the hairline (its strands start there: the flow runs into the shell), short
    # flat cards along it, so the shell's cut edge never shows as a line
    if shell_part is not None:
        Vsm, Tsm = shell_part
        E, tri, opp = boundary_edges(Tsm)
        a, b = Vsm[E[:, 0]], Vsm[E[:, 1]]
        mid_p = (a + b) * 0.5
        ed = unit(b - a)
        inward = Vsm[opp] - mid_p
        inward = unit(inward - ed * (inward * ed).sum(1, keepdims=True))
        n_edge = 0
        # (style roll_bare, with roll_under, off by default) the edge roll_under cut along the roll's underside is no
        # hairline: the hair does not start there, it rolls under. The short flat hairline cards rooted along that
        # jagged cut (115 of them), lit as a hairline (tone 0.72-0.95), stood at the far front corner's silhouette
        # as flat stacked planes with straight edges and dark slots between them, a lit grey plane with a hard
        # diagonal edge on the curtain's lower edge over the near temple, and a flyaway poking out of the far corner.
        # They are still grown (their draws taken, so the random sequence of everything after stays the same) and
        # dropped once the edge is done
        rb_cut = None
        if st.get("roll_bare") and not st["long"] and fr.get("roll_under") is not None:
            rb_cut = np.zeros(len(Vsm), bool)
            rb_cut[np.unique(fr["roll_under"][1])] = True
        rb_drop = []
        for k in range(len(E)):
            if mid_p[k, 2] < fr["brow_z"] + 0.005:
                continue
            r = surf.nearest_n(mid_p[k])
            if r is None:
                continue
            loc, n, _, tr, bc = r
            dd = flow(loc, n, tr, bc)
            tdir = vunit(dd - n * float(dd @ n))
            if float(tdir @ inward[k]) < 0.35:
                continue
            seg_len = vlen(b[k] - a[k])
            on_cut = rb_cut is not None and bool(rb_cut[E[k, 0]] and rb_cut[E[k, 1]])
            for _ in range(max(1, int(round(seg_len / hl["step"])))):
                q = a[k] + (b[k] - a[k]) * rng.uniform(0, 1)
                n_target += 1
                n_edge += 1
                n0_ = cards.n
                made += strand(q, "hairline", hl["length"] or (0.04, 0.08), hl["width"], (0.0003, 0.0009),
                               hl["tone"], hl["strips"], 0.04)
                if on_cut and cards.n > n0_:
                    rb_drop.append(n0_)
        log(f"shell edge hairline roots: {n_edge}")
        if rb_drop:
            cards.drop(rb_drop)
            made -= len(rb_drop)
            log(f"roll: {len(rb_drop)} hairline cards rooted on the cut underside's edge dropped")
    log(f"hairline: {made}/{n_target} cards")
    # silhouette: curl flicks springing off the surface (curly) and a few short flyaways
    if st.get("loops"):
        lp = st["loops"]
        count = int(lp["count_per_m2"] * area)
        wgt = np.clip(surf.N[surf.T].mean(1)[:, 2] + 0.6, 0.05, 1.6)
        P, _ = surf.sample(count, rng, wgt)
        for p in P:
            sp = loop_strand(surf, flow, p, rng.uniform(*lp["length"]), rng.uniform(*lp["bulge"]), rng, st)
            if sp and not (not st["long"] and any(floor_hit(q, fr, st) for q in sp[0])):
                cards.add(*sp, width=rng.uniform(*lp["width"]), strip=int(rng.choice(lp["strips"])),
                          tone=rng.uniform(0.8, 1.0), fade=0.2, layer="loops", taper=0.4, rng=rng)
    fl = st.get("fly")
    if fl and fl.get("count"):
        wgt = np.clip(surf.N[surf.T].mean(1)[:, 2] + 0.3, 0.02, 1.3)
        P, _ = surf.sample(int(fl["count"]), rng, wgt)
        for p in P:
            sp = loop_strand(surf, flow, p, rng.uniform(*fl["length"]), rng.uniform(*fl["bulge"]), rng, st,
                             seg=0.008 if not st["long"] else 0.012)
            # (never down over the face past the fringe's floor: one rooted at Mano's temple hung down past his
            # eye's outer corner to the cheek as a few thin straight lines)
            if sp and not (not st["long"] and any(floor_hit(q, fr, st) for q in sp[0])):
                cards.add(*sp, width=rng.uniform(*fl["width"]), strip=7, tone=rng.uniform(0.85, 1.0), fade=0.15,
                          layer="fly", taper=0.3, rng=rng)
    if ear_side is not None and shell_part is not None:
        # and along the shell's own edge over each ear (cut 6 mm round it): locks rooted 1.2 cm up the guide that
        # hang on over the ear's top, every 3 mm. The strands reaching that edge from higher up fell at their own
        # lengths and left the rim's highest point, at the back, bare: a pointed skin peak with straight edges
        # poking up into the hair. Their own random sequence (never the build's)
        rng_e = np.random.default_rng(11)
        top_l = next(l for l in st["layers"] if l[0] == "top")
        Vsm_, Tsm_ = shell_part
        E_, _, _ = boundary_edges(Tsm_)
        mids = (Vsm_[E_[:, 0]] + Vsm_[E_[:, 1]]) * 0.5
        seeds = []
        e_step = float(ew.get("step", 0.003)) if ew else 0.003
        for m_ in mids:
            if ear_side.below(m_) and all(vlen(m_ - q_) > e_step for q_ in seeds):
                seeds.append(m_)
        n_e = 0
        for m_ in seeds:
            r = surf.nearest_n(m_)
            if r is None:
                continue
            loc, n, _, tri, bc = r
            dd = flow(loc, n, tri, bc)
            t = dd - n * float(dd @ n)
            if vlen(t) < 1e-6:
                continue
            info = {}
            sp = grow(surf, flow, loc - vunit(t) * 0.012, 0.012 + st["ear_free"] * rng_e.uniform(0.5, 1.0) + 0.008,
                      st["seg"], (0.0015, 0.003), st, fr, rng_e, body, coll=coll, curl=curl, free_max=st["free_max"],
                      gfront=gfront, info=info, ears=ear_side)
            if sp is None or not info.get("over_ear") or info.get("free_at") is None:
                continue
            P_ = np.array(sp[0])
            k0 = int(info["free_at"])
            Lf = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))])
            Lf = np.maximum(Lf - Lf[min(max(k0 - 1, 0), len(Lf) - 1)], 0.0) * (np.arange(len(P_)) >= k0)
            tone_e = rng_e.uniform(0.82, 1.0)
            ear_locks.append((sp, rng_e.uniform(*top_l[3]) * 0.8 * ew_w, int(rng_e.choice(ew_strips)), tone_e + 0.0 * Lf,
                              min(1.0, 0.004 / max(float(Lf[-1] + 0.012), 1e-6)), ew_tip))
            n_e += 1
        log(f"ears: {len(seeds)} spots on the shell's edge over the ears -> {n_e} locks")
    ev = st.get("ear_veil") or None
    if ev and ear_side is not None and shell_part is not None:
        # (style ear_veil, a dict, off by default) a veil of fine locks over each ear's top: rooted every `step` along
        # the shell's edge over the ear (and `front` metres in front of it, down to the glasses' arm), in rows
        # `rows` metres up the guide, each hanging its own length past the edge (`len`), narrow (`w` x the top
        # layer's width, strips `strips`), its strands thinning over the last `tip` of its hanging stretch, lying
        # on the ear's outside at its own height over it. The strands reaching the edge from higher up are the
        # layers' wide cards, a few dozen over each ear: they hung over Mano's ear tops as separate chunky black
        # tufts with blunt ends and skin between them (his portrait: the hair covers the ears' tops, a mass that
        # thins out into fine wisps), and left a bare skin wedge at the temple above the arm. Their own random
        # sequence (never the build's), added with the other ear locks once all the rest is grown
        rng_v = np.random.default_rng(int(ev.get("seed", 13)))
        top_l = next(l for l in st["layers"] if l[0] == "top")
        Vsm_, Tsm_ = shell_part
        E_, _, _ = boundary_edges(Tsm_)
        step_v = float(ev.get("step", 0.001))
        front_v = float(ev.get("front", 0.0))
        front_top = float(ev.get("front_top", 0.03))
        # (`over`, optional: how far over the ear the shell's edge may lie and count as over it, default 2 cm: Ian's
        # edge over the front of his ear's top lies 2-3 cm above the rim, between the locks rooted over the ear and
        # those before it, and a bare skin strip was left over the ear's front top, the hair before it ending in a
        # squared notch)
        over_v = float(ev.get("over", 0.02))
        cands = []
        for ia, ib in E_:
            a_, b_ = Vsm_[ia], Vsm_[ib]
            nn = max(1, int(math.ceil(vlen(b_ - a_) / step_v)))
            for tt in (np.arange(nn) + 0.5) / nn:
                cands.append(a_ + (b_ - a_) * tt)
        ears_xyz = fr["ears"]

        def over_or_before(m_):
            if ear_side.below(m_, over_v):
                return True
            if front_v <= 0.0:
                return False
            # in front of the ear on its side, from its top down to the arm's level, up to `front` forward
            for t_ in ears_xyz:
                if (m_[0] - fr["eye"][0]) * (t_[0] - fr["eye"][0]) <= 0:
                    continue
                if t_[1] - front_v - 0.012 < m_[1] < t_[1] - 0.004 and t_[2] - 0.005 < m_[2] < t_[2] + front_top:
                    return True
            return False

        seeds = []
        for m_ in cands:
            if not over_or_before(m_):
                continue
            if seeds and float(np.linalg.norm(np.array(seeds) - m_, axis=1).min()) < step_v:
                continue
            seeds.append(m_)
        rows_v = [float(x) for x in ev.get("rows", (0.01, 0.02))]
        lr = tuple(float(x) for x in ev.get("len", (0.01, 0.026)))
        lr_front = tuple(float(x) for x in ev.get("front_len", lr))
        n_v = 0
        for m_ in seeds:
            r = surf.nearest_n(m_)
            if r is None:
                continue
            loc, n, _, tri, bc = r
            dd = flow(loc, n, tri, bc)
            t = dd - n * float(dd @ n)
            if vlen(t) < 1e-6:
                continue
            t = vunit(t)
            before = not ear_side.below(m_, over_v)
            for up in rows_v:
                hang = rng_v.uniform(*(lr_front if before else lr))
                lift_v = (rng_v.uniform(0.0008, 0.002), rng_v.uniform(0.0015, 0.0035))
                clear_v = float(st.get("ear_drape", 0.0015)) * rng_v.uniform(1.0, 3.0)
                w_v = rng_v.uniform(*top_l[3]) * float(ev.get("w", 0.45))
                strip_v = int(rng_v.choice(tuple(ev.get("strips", (4, 5, 6)))))
                tone_v = rng_v.uniform(0.82, 1.0)
                root_v = loc - t * (up + rng_v.uniform(-0.002, 0.002)) + rng_v.normal(0, 0.0006, 3)
                st_v = dict(st, ear_drape=clear_v, ear_free=hang)
                info = {}
                sp = grow(surf, flow, root_v, up + hang + 0.004, 0.004, lift_v, st_v, fr, rng_v, body, coll=coll,
                          curl=curl, free_max=hang, gfront=gfront, info=info, ears=ear_side)
                if sp is None or info.get("free_at") is None:
                    continue
                P_ = np.array(sp[0])
                Lq = float(np.linalg.norm(np.diff(P_, axis=0), axis=1).sum())
                k0 = int(info["free_at"])
                Lh = float(np.linalg.norm(np.diff(P_[max(k0 - 1, 0):], axis=0), axis=1).sum()) if k0 < len(P_) else 0.0
                tip_v = min(1.0, max(0.2, float(ev.get("tip", 0.6)) * Lh / max(Lq, 1e-6)))
                ear_locks.append((sp, w_v, strip_v, tone_v + 0.0 * np.arange(len(P_)),
                                  min(1.0, 0.004 / max(Lq, 1e-6)), tip_v))
                n_v += 1
        log(f"ears: veil, {len(seeds)} spots on the shell's edge over and before the ears -> {n_v} locks")
    for q, w1, strip1, tq, fd, tp in ear_locks:
        cards.add(*q, width=w1, strip=strip1, tone=tq, fade=fd, layer="ear", taper=0.5, rng=None, tip=tp)
    if ear_locks:
        log(f"ears: {len(ear_locks)} locks over the ears (under-layer strands going on, and along the shell's edge)")
    if st.get("front_free") and not st["long"] and cards.n:
        # short hair with a drawn fringe edge: a hairline card that touches none of the rest lies alone on the
        # skin below the edge (the scan paints the temples' hairline lower than its hair reaches) as a dark smudge
        Vc = np.array(cards.V).reshape(-1, 3)
        Ac = np.array(cards.COL)[:, 3]
        names = [k for k, v in cards.by_layer.items() for _ in range(v)]

        def solid(b0, m):
            # the card's centre line where it is opaque (past its root fade)
            c = (Vc[b0:b0 + 2 * m:2] + Vc[b0 + 1:b0 + 2 * m:2]) * 0.5
            return c[Ac[b0:b0 + 2 * m:2] > 0.6]

        mass = [solid(b0, m) for j, (b0, m) in enumerate(cards.rows) if names[j] != "hairline"]
        kd = Points(np.concatenate([x for x in mass if len(x)]))
        bad = []
        for j, (b0, m) in enumerate(cards.rows):
            if names[j] == "hairline":
                own = solid(b0, m)
                if len(own) and kd.nearest(own)[0].min() > 0.005:
                    bad.append(j)
        if bad:
            cards.drop(bad)
            log(f"{len(bad)} hairline cards apart from the hair dropped")
    rt = st.get("roll_tone") or None
    if rt and not st["long"] and fr.get("roll_under") is not None and cards.n:
        # (style roll_tone, a dict, with roll_under, off by default) the cards within `reach` of the roll's cut
        # underside no darker than `min` (their depth tone raised, ramped in over the reach's outer half): over the
        # roll's tight bend at the temples every layer shows edge-on at the outline, and the inner layers' deep
        # tones (0.3-0.4) there read as stacked dark card tabs and slots under the outer ones, seen from above at
        # the far front corner. The roll's own strands (roll_fill, added below) keep their tone. No draw
        rp_ = Points(fr["roll_under"][0][np.unique(fr["roll_under"][1])])
        if fr.get("roll_tuck") is not None:
            # (roll_tuck: and its tucked underside beside the temples, the same bend of the roll)
            rp_ = Points(np.concatenate([fr["roll_under"][0][np.unique(fr["roll_under"][1])],
                                         fr["roll_tuck"][0][np.unique(fr["roll_tuck"][1])]]))
        tmin_, reach_t = float(rt.get("min", 0.6)), float(rt.get("reach", 0.025))
        Vt_ = np.array(cards.V).reshape(-1, 3)
        dt_, _ = rp_.nearest(Vt_)
        wt_ = 1.0 - smoothstep(reach_t * 0.5, reach_t, dt_)
        # (`max`, optional: and no lighter than max: over the roll's bend the top layer's 0.85-1.0 cards, seen at a
        # grazing angle beside the inner layers raised to `min`, read as lit grey planes with hard edges on the
        # curtain's lower edge and as stacked bands of different tone at the far corner)
        tmax_ = float(rt["max"]) if rt.get("max") is not None else None
        n_t = n_tm = 0
        for i in np.nonzero(wt_ > 0.0)[0]:
            r_, g_, b_, a_ = cards.COL[i]
            if g_ < tmin_:
                g2_ = g_ + (tmin_ - g_) * float(wt_[i])
                f_ = g2_ / max(g_, 1e-6)
                cards.COL[i] = (min(1.0, r_ * f_), min(1.0, g2_), min(1.0, b_ * f_), a_)
                n_t += 1
            elif tmax_ is not None and g_ > tmax_:
                g2_ = g_ + (tmax_ - g_) * float(wt_[i])
                f_ = g2_ / max(g_, 1e-6)
                cards.COL[i] = (min(1.0, r_ * f_), min(1.0, g2_), min(1.0, b_ * f_), a_)
                n_tm += 1
        log(f"roll: {n_t} card vertices within {reach_t * 1000:.0f} mm of the cut underside raised to tone {tmin_}" +
            (f", {n_tm} lowered to {tmax_}" if tmax_ is not None else ""))
    rf = st.get("roll_fill") or None
    if rf and not st["long"] and fr.get("roll_under") is not None:
        # (style roll_fill, a dict, with roll_under, off by default) strands on the scalp under the roll whose
        # underside roll_under left out: rooted over the scalp under it (the cut underside within `reach`, on the
        # skin's outer side), lying on it and running up and back into the roll (against the style's
        # flow, `up` x up added), `len` long, their roots faded in over `fade` metres. Without the underside's cards
        # the scalp under the curtain was bare: from the 3/4 view, looking up under the near temple, a pale band of
        # skin and the cap's thin roots with the curtain's cut edge a hard line over it. Their own random
        # sequence (never the build's), added once all the rest is grown
        rng_r = np.random.default_rng(int(rf.get("seed", 17)))
        Vsm_r, Tu_r = fr["roll_under"]
        roll_m = Mesh(Vsm_r, Tu_r)
        Vb_, Tb_ = body.V, body.T
        Cb_ = Vb_[Tb_].mean(1)
        cap_ = base["cap"]
        cand_ = np.nonzero(cap_)[0]
        reach_ = float(rf.get("reach", 0.035))
        sel_ = []
        for t_ in cand_:
            r_ = roll_m.nearest(Cb_[t_], reach_)
            if r_ is not None and float((r_[0] - Cb_[t_]) @ body.FN[t_]) > 0.3 * r_[3]:
                sel_.append(t_)
        S_ = np.array(sel_, np.int64)
        n_rf = 0
        if len(S_):
            su_ = np.unique(Tb_[cap_])
            rm_ = -np.ones(len(Vb_), np.int64)
            rm_[su_] = np.arange(len(su_))
            scalp_r = Surface(Vb_[su_] + body.N[su_] * GUIDE_LIFT, rm_[Tb_[cap_]])
            up_ = float(rf.get("up", 0.6))

            class UpFlow:
                origin = flow.origin

                def __call__(self, q, n, tri=None, bc=None):
                    return vunit(-flow.style(q) + UP * up_)

            up_flow = UpFlow()
            area_s = float(body.area[S_].sum())
            count = int(area_s * float(rf.get("density", 90000)))
            pr = body.area[S_] / area_s
            tri_ = S_[rng_r.choice(len(S_), size=count, p=pr)]
            r1, r2 = rng_r.random(count), rng_r.random(count)
            sq = np.sqrt(r1)
            bc_ = np.stack([1 - sq, sq * (1 - r2), sq * r2], 1)
            seeds_ = (Vb_[Tb_[tri_]] * bc_[:, :, None]).sum(1) + body.FN[tri_] * GUIDE_LIFT
            lr_ = tuple(float(x) for x in rf.get("len", (0.02, 0.035)))
            wr_ = tuple(float(x) for x in rf.get("w", (0.006, 0.01)))
            tr_ = tuple(float(x) for x in rf.get("tone", (0.22, 0.38)))
            strips_r = tuple(rf.get("strips", (0, 1, 2, 3)))
            # (`under`: how much of the roll underside's normal they are shaded with, the rest the skin's)
            wu_ = float(rf.get("under", 0.8))
            wn_ = 1.0 - wu_ if "under" in rf else 0.2
            for q in seeds_:
                L_ = rng_r.uniform(*lr_)
                s_ = grow(scalp_r, up_flow, q, L_, st["seg"], (0.0003, 0.0012), st, fr, rng_r, body, coll=coll,
                          curl=None, free_max=0.0, gfront=gfront)
                if s_ is None:
                    continue
                # no further than the hair's own mass: where it comes within 4 mm of the guide it ends (on through
                # it, it would stand out of the curtain's top)
                k_end = len(s_[0])
                for k_, pt_ in enumerate(s_[0]):
                    if k_ >= 2 and surf.nearest(pt_, 0.004) is not None:
                        k_end = k_
                        break
                if k_end < 3:
                    continue
                # shaded as the underside of the hair over them, not as the skin they lie on (lit as the temple, they
                # read as a pale flat patch)
                nr_ = []
                for pt_, (n0_, tw_) in zip(s_[0][:k_end], s_[1][:k_end]):
                    rr_ = roll_m.nearest(pt_, 0.1)
                    nr_.append((vunit(roll_m.FN[rr_[1]] * wu_ + n0_ * wn_) if rr_ is not None else n0_, tw_))
                s_ = (s_[0][:k_end], nr_, s_[2][:k_end])
                Ls_ = float(np.linalg.norm(np.diff(np.array(s_[0]), axis=0), axis=1).sum())
                cards.add(*s_, width=rng_r.uniform(*wr_), strip=int(rng_r.choice(strips_r)), tone=rng_r.uniform(*tr_),
                          fade=min(1.0, float(rf.get("fade", 0.004)) / max(Ls_, 1e-6)), layer="roll", taper=0.5,
                          rng=rng_r)
                n_rf += 1
        log(f"roll: {len(S_)} scalp tris under the cut underside, {n_rf} cards on them")
    dcv = st.get("drape_cover") or None
    if dcv and st["long"] and drape is not None and cards.n:
        # (style drape_cover, a dict, long hair, off by default) the hair hanging free beside the neck, seen from the
        # front: a gap between two hanging locks with the body behind it is filled. Off the guide (whose underside
        # there `underside` leaves out) that hair is only the strands that happen to fall there, and the coverage
        # passes look at the guide alone: where two or three loose cards were all that hung between the front lock
        # and the hair over the shoulder, the neck and the sweater showed through a hard-edged slot between them, a
        # different one in every build. Over a grid in x and z (`cell`, `x` and `z` metres beside and below
        # the eyes), seen from the front and turned `turn` radians either way (the dialogue views and the idle
        # pose's head turn), the cards' cover of the body is reckoned (their strips' alpha-tested coverage across
        # and along them, FrontCover); a cell outside the face window covered less than `cover` with cover at least
        # that within `span` on both sides is a gap. For the highest gap, fills are grown from the guide above it
        # (up to `tries` roots, within 3 cm sideways and 2-18 cm up, in front of the shoulders' middle; from the
        # dense strips `strips`, depth tone `tone`) and the one that covers the most of the gaps is kept, until
        # none is left or none helps (at most `max` cards). Their own random sequence (never the build's), added
        # once all the rest is grown, as their own layer
        rng_d = np.random.default_rng(int(dcv.get("seed", 19)))
        cell_d = float(dcv.get("cell", 0.003))
        zr_d = tuple(float(v) for v in dcv.get("z", (0.1, 0.26)))
        xr_d = tuple(float(v) for v in dcv.get("x", (0.03, 0.16)))
        thr_d = float(dcv.get("cover", 0.85))
        span_d = float(dcv.get("span", 0.035))
        tries_d = int(dcv.get("tries", 12))
        max_d = int(dcv.get("max", 80))
        strips_d = tuple(dcv.get("strips", (0, 1, 2)))
        tone_r = tuple(float(v) for v in dcv.get("tone", (0.5, 0.66)))
        turns_d = tuple(float(v) for v in dcv.get("turn", (0.0,)))
        ex_, ez_ = float(fr["eye"][0]), float(fr["eye"][2])
        gx_ = np.arange(ex_ - xr_d[1], ex_ + xr_d[1] + 1e-9, cell_d)
        gz_ = np.arange(ez_ - zr_d[1], ez_ - zr_d[0] + 1e-9, cell_d)
        cov_tab = strip_cover(st["atlas"])
        ns_ = max(1, int(round(span_d / cell_d)))
        jaw_d = dcv.get("jaw")
        fcs, oks, jaws = [], [], []
        for tn_ in turns_d:
            fc = FrontCover(body, gx_, gz_, cov_tab, tn_, fr["eye"])
            for b0, m in cards.rows:
                fc.add(fc.card_trans(cards.V, cards.UV, cards.COL, b0, m))
            ok_ = (np.abs(gx_ - ex_) >= xr_d[0])[None, :] & np.isfinite(fc.yb)
            if st.get("face_window"):
                # (never the face itself: hair keeps out of its window; the body point turned back)
                GX_, GZ_ = np.meshgrid(gx_, gz_)
                Pb_ = np.stack([GX_.ravel(), np.where(np.isfinite(fc.yb), fc.yb, 1.0).ravel(), GZ_.ravel()], 1)
                if tn_ != 0.0:
                    Q_ = Pb_ - fc.o
                    Pb_ = np.stack([Q_[:, 0] * fc.c + Q_[:, 1] * fc.s, -Q_[:, 0] * fc.s + Q_[:, 1] * fc.c, Q_[:, 2]],
                                   1) + fc.o
                ok_ &= ~in_face_window(Pb_, fr, 0.003).reshape(fc.yb.shape)
            jm_ = np.zeros_like(ok_)
            if jaw_d is not None:
                # (`jaw`: the jaw's outline counts as the inner edge too: a cell whose body lies `jaw` metres further
                # back than the body one or two cells toward the middle is the neck seen past the jaw, and the neck
                # showed there between the jaw and the hair, in the mouth's close-up with the head turned)
                ybf = np.where(np.isfinite(fc.yb), fc.yb, -np.inf)
                for k_ in (1, 2):
                    inner = np.full_like(ybf, -np.inf)
                    inner[:, k_:] = np.where((gx_[k_:] > ex_)[None, :], ybf[:, :-k_], inner[:, k_:])
                    inner[:, :-k_] = np.where((gx_[:-k_] < ex_)[None, :], ybf[:, k_:], inner[:, :-k_])
                    jm_ |= np.isfinite(inner) & (inner < fc.yb - float(jaw_d))
                jm_ &= (gz_ > ez_ - float(dcv.get("jaw_z", 0.13)))[:, None]
            fcs.append(fc)
            oks.append(ok_)
            jaws.append(jm_)

        def gaps(f):
            c_ = fcs[f].covered()
            good = c_ >= thr_d
            left = np.zeros_like(good)
            right = np.zeros_like(good)
            for k_ in range(1, ns_ + 1):
                left[:, k_:] |= good[:, :-k_]
                right[:, :-k_] |= good[:, k_:]
            # (inner: toward the eyes' middle; there the jaw's outline may stand in for hair)
            inner_ok = np.where((gx_ > ex_)[None, :], left, right) | jaws[f]
            outer_ok = np.where((gx_ > ex_)[None, :], right, left)
            return (c_ < thr_d) & oks[f] & inner_ok & outer_ok, c_

        Vk_ = surf.V[np.unique(shell_part[1])] if shell_part is not None else surf.V
        mid_l = next(l for l in st["layers"] if l[0] == "mid")
        n_dc, gone, tried = 0, set(), {}
        n_gap0 = sum(int(gaps(f)[0].sum()) for f in range(len(fcs)))
        while n_dc < max_d:
            holes = [gaps(f) for f in range(len(fcs))]
            target = None
            for f, (hole, _) in enumerate(holes):
                for g_ in gone:
                    if g_[0] == f:
                        hole[g_[1], g_[2]] = False
                if hole.any():
                    hz, hx = np.nonzero(hole)
                    j_ = int(np.argmax(hz))
                    if target is None or hz[j_] > target[1]:
                        target = (f, int(hz[j_]), int(hx[j_]))
            if target is None:
                break
            tf, tz, tx = target
            xh, zh = float(gx_[tx]), float(gz_[tz])
            # (the target's own x, turned back to the head's frame: near enough for choosing roots)
            sd_ = math.copysign(1.0, xh - ex_)
            cand = Vk_[((Vk_[:, 0] - ex_) * sd_ > 0) & (np.abs(Vk_[:, 0] - xh) < 0.03) & (Vk_[:, 2] > zh + 0.02) &
                       (Vk_[:, 2] < zh + 0.18) & (Vk_[:, 1] < drape["y_sh"] + 0.03)]
            best = None
            if len(cand):
                pick = rng_d.choice(len(cand), size=min(tries_d, len(cand)), replace=False)
                for ci_ in pick:
                    r = surf.nearest_n(cand[ci_] + rng_d.normal(0, 0.002, 3))
                    if r is None:
                        continue
                    L_ = float(st.get("fill_len") or st["max_len"])
                    lift_d = (rng_d.uniform(*mid_l[4]), rng_d.uniform(*mid_l[4]))
                    info = {}
                    s_ = grow(surf, flow, r[0], L_, st["seg"], lift_d, st, fr, rng_d, body, coll=coll, curl=curl,
                              free_max=st["free_max"] * rng_d.uniform(0.25, 1.0), drape=drape, gfront=gfront,
                              face_free=True, info=info)
                    w_d = rng_d.uniform(*mid_l[3])
                    strip_d = int(rng_d.choice(strips_d))
                    tone_d = rng_d.uniform(*tone_r)
                    if s_ is None:
                        continue
                    if dcv.get("lit") and st.get("front_lit") and info.get("front_at") is not None:
                        # (as strand(): hanging free in front of the ears, in the light)
                        P_ = np.array(s_[0])
                        k0 = min(int(info["front_at"]), len(P_) - 1)
                        Lw = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))])
                        Lw = np.maximum(Lw - Lw[k0], 0.0) * (np.arange(len(P_)) >= k0)
                        lw = smoothstep(0.0, 0.02, Lw) * (np.arange(len(P_)) >= k0)
                        tone_d = tone_d + (np.maximum(tone_d, float(st["front_lit"])) - tone_d) * lw
                    Ls_ = float(np.linalg.norm(np.diff(np.array(s_[0]), axis=0), axis=1).sum())
                    args = dict(width=w_d, strip=strip_d, tone=tone_d, fade=min(1.0, 0.008 / max(Ls_, 1e-6)),
                                layer="drape", taper=st.get("taper", 0.55))
                    tmp = Cards(8)
                    tmp.add(*s_, rng=None, **args)
                    trs = [fc.card_trans(tmp.V, tmp.UV, tmp.COL, 0, tmp.rows[0][1]) for fc in fcs]
                    if (tz, tx) not in trs[tf]:
                        continue
                    # gain: how much of the gaps it covers (cover gained in gap cells, the target's counting double)
                    gain = 0.0
                    for f, tr_ in enumerate(trs):
                        hole, cov_ = holes[f]
                        for (iz, ix), t in tr_.items():
                            if hole[iz, ix]:
                                gain += (1.0 - cov_[iz, ix]) * (1.0 - t) * (2.0 if (f, iz, ix) == target else 1.0)
                    if best is None or gain > best[0]:
                        best = (gain, s_, args, trs)
            tried[target] = tried.get(target, 0) + 1
            if best is None or best[0] <= 0.0 or tried[target] >= 3:
                gone.add(target)
            if best is None or best[0] <= 0.0:
                continue
            cards.add(*best[1], rng=None, **best[2])
            for fc, tr_ in zip(fcs, best[3]):
                fc.add(tr_)
            n_dc += 1
        left_ = [gaps(f)[0] for f in range(len(fcs))]
        log(f"drape: {n_gap0} cells of gap between hanging locks in front of the body (seen from {len(fcs)} sides), "
            f"{n_dc} fills grown over them, {sum(int(h.sum()) for h in left_)} left")
        if os.environ.get("HAIR_DEBUG_DRAPE"):
            for f, h in enumerate(left_):
                hz, hx = np.nonzero(h)
                log(f"drape: turn {turns_d[f]:+.2f} left at (cm from the eyes) " +
                    " ".join(f"({(gx_[b] - ex_) * 100:.1f},{(gz_[a] - ez_) * 100:.1f})" for a, b in zip(hz, hx)))
    fl = st.get("front_locks") or None
    if fl and not st["long"] and shell_part is not None:
        front_locks(st, fl, surf, shell_part, cards, fr, body, coll, gfront, flow)
    if st.get("curl_tips") and not st["long"] and cards.n:
        curl_tips(st, st["curl_tips"], cards, fr)
    if not st["long"] and cards.n and fr.get("lids") is not None:
        # nothing over the eyes: the strands stop above the lids (floor_z), but a card is wider than its strand and
        # a slanted one swings its corners lower; any card that still reaches the eye opening ends a row before it
        cuts = eye_cuts(cards, fr)
        if cuts:
            cards.trim(cuts)
            log(f"eyes: {sum(1 for k in cuts.values() if k >= 3)} cards shortened, "
                f"{sum(1 for k in cuts.values() if k < 3)} dropped")
    if st["long"] and st.get("hem_min") and cards.n:
        # (style hem_min, long hair, off by default) no card shorter than hem_min ending at the hair's lower edge
        # below the shoulders (within 2.5 cm of the lowest tip within 1.5 cm across): rooted near the bottom of the
        # guide (the cape on the back), a strand runs off its edge and falls a few cm, a card 4-15 cm long, too
        # short for the shader's soft tips (hair_scan.gdshaderinc, tip_soft_len), and its clump's end in a coarse
        # mip hung from the back hair's hem as a round dark knob. Left out once all is grown: no draw moves
        Vc = np.array(cards.V).reshape(-1, 3)
        z_lo = drape["z_neck"] - 0.05 if drape is not None else fr["eye"][2] - 0.2
        tips, lens = [], []
        for b0, m in cards.rows:
            c_ = (Vc[b0:b0 + 2 * m:2] + Vc[b0 + 1:b0 + 2 * m:2]) * 0.5
            tips.append(c_[-1])
            lens.append(float(np.linalg.norm(np.diff(c_, axis=0), axis=1).sum()))
        tips, lens = np.array(tips), np.array(lens)
        low = tips[:, 2] < z_lo
        bad = []
        for j in np.nonzero(low & (lens < float(st["hem_min"])))[0]:
            nb = low & (np.abs(tips[:, 0] - tips[j, 0]) < 0.015) & (np.abs(tips[:, 1] - tips[j, 1]) < 0.04)
            if tips[j, 2] < float(tips[nb, 2].min()) + 0.025:
                bad.append(int(j))
        if bad:
            cards.drop(bad)
            log(f"hem: {len(bad)} cards shorter than {float(st['hem_min']) * 100:.0f} cm ending at the hair's lower "
                f"edge left out")
    if st["long"] and cards.n:
        # nothing below the shoulders out beside the body (an arm in the scan's A-pose): skinned to the spine, it
        # would float in mid-air once the arms come down
        Vc = np.array(cards.V).reshape(-1, 3)
        zs = fr["eye"][2] - 0.17
        bad = [j for j, (b0, m) in enumerate(cards.rows)
               if ((Vc[b0:b0 + 2 * m, 2] < zs) & (np.abs(Vc[b0:b0 + 2 * m, 0] - fr["eye"][0]) > 0.23)).any()]
        if bad:
            cards.drop(bad)
            log(f"{len(bad)} cards beside the body dropped")
        n_r = cards.refine(body, fr["eye"][2] - 0.04, clear=0.003)
        log(f"{n_r} rows added where cards cut into the neck and back between rows")
    if st.get("tone_exposed") and cards.n:
        tone_exposed(cards, st["tone_exposed"])
    if st.get("relief_tone") and not st["long"] and cards.n:
        # (off by default) last, once every card is grown: vertex colours only, no draw
        relief_tone(cards, st["relief_tone"], fr)
    cp = cards.opaque_points()
    out = cards.arrays()
    out["opaque"] = cp
    out["dense"] = cards.opaque_points(max_s=0.65)
    if len(out["V"]):
        # below the skull the cards lie on the neck, the shoulders and the back: no ribbon edge inside the body
        # (it would show as hair growing out of the clothes); on the head the cap and the skin hide any
        # (and around the ears, which the scan's hair volume passes through)
        low = np.nonzero((out["V"][:, 2] < fr["eye"][2] - 0.04) | near_ears(out["V"], fr))[0]
        if len(low):
            # (long hair 3 mm off the clothes: 1.5 mm left no room for the sweater's own movement in the pose)
            out["V"][low] = push_out(out["V"][low], body, 0.003 if st["long"] else 0.0015, solid=True, reach=0.03)
        if st.get("face_window"):
            out["V"], nmv = clamp_out_of_window(out["V"], fr, body=body)
            log(f"face window: {nmv} card vertices moved out of it")
    if coll is not None and len(out["V"]):
        # under the glasses' arms first (pushed off them they lay over them), then 3 mm off the rest of the frame
        out["V"], pressed = press_under_arms(out["V"], arms, body)
        if pressed.any():
            log(f"glasses: {int(pressed.sum())} card vertices pressed under the arms")
        rest = ~pressed
        if gfront is not None:
            # row by row (a card's two edge vertices, consecutive): both by the same amount, so the ribbon stays
            # flat (moved apart it twisted into a dark shard)
            n_f, big = 0, 0.0
            Vo = out["V"]
            for r in range(0, len(Vo) - 1, 2):
                if not (rest[r] and rest[r + 1]):
                    continue
                s = max(gfront.shift(Vo[r]), gfront.shift(Vo[r + 1]))
                if s > 0.0:
                    Vo[r, 1] -= s
                    Vo[r + 1, 1] -= s
                    rest[r] = rest[r + 1] = False
                    n_f += 2
                    big = max(big, s)
            if n_f:
                log(f"glasses: {n_f} card vertices moved in front of the lenses (at most {big * 1000:.1f} mm)")
        # (beside the head, the arms: over them; the front of the frame: away from it)
        side = rest & (np.abs(out["V"][:, 0] - fr["eye"][0]) > 0.055)
        out["V"][side] = push_over(out["V"][side], coll, body, 0.003)
        out["V"][rest & ~side] = push_out(out["V"][rest & ~side], coll, 0.003)
    log(f"cards grown in {time.time() - t0:.1f} s")
    return out


# ------------------------------------------------------------------ cap and underlayer images
def cap_image(G, fr, st, hair_tex, size=1024):
    """The cap's texture in head UV space: RGB = the root colour x 2.2 (sRGB), A = the mask (blurred a few texels
    so the hairline is soft, then sharpened, smoothstep 0.4-0.8) with a centre part's ~2 mm gap cut out."""
    m = hair_tex
    if m.shape[0] != size:
        k = max(1, m.shape[0] // size)
        m = m[:size * k, :size * k].reshape(size, k, size, k).mean((1, 3))
    a = box_blur(m.astype(np.float32), 1, 3)
    a = smoothstep(0.4, 0.8, a)
    if st.get("part"):
        # the part line, rasterised into head UV space: the texels' own 3D positions on the scalp
        Vb, Tb, UVb, head = G["body_V"], G["body_T"], G["body_UV"], G["body_head"]
        C = Vb[Tb].mean(1)
        pa, pb = part_line(st, fr)
        top = head & (C[:, 2] > fr["top"] - 0.08) & (np.abs(C[:, 0] - pa[0]) < 0.03)
        pos = uv_raster(UVb, Vb[Tb], size, top)
        x0, y0, y1 = pa[0], pa[1] - 0.012, pb[1]
        dx = np.abs(pos[..., 0] - x0)
        on = np.isfinite(dx) & (pos[..., 1] > y0) & (pos[..., 1] < y1 + 0.01)
        dxs = np.where(on, dx, 1.0)
        # dark roots right up to the part (the scan paints it skin), then the part itself: open within 0.5 mm,
        # closed by 1.5 mm (about 2 mm of scalp), fading out over its last 1.5 cm at the crown
        band = on & (dxs < 0.02) & (pos[..., 2] > fr["top"] - 0.075)
        ys = np.where(on, pos[..., 1], y0)
        # (fading out over the band's back end: cut off square there, the roots read as a dark plate behind the
        # crown with a hard edge)
        roots = smoothstep(0.02, 0.012, dxs) * (1.0 - smoothstep(y1 - 0.012, y1 + 0.01, ys))
        a = np.where(band, np.maximum(a, roots), a)
        # (style part_gap {r: [open, closed] metres, open: how see-through}, off by default: Silvia's 2 mm of bright
        # scalp read as a pale line along the part from behind)
        pg_ = st.get("part_gap") or {}
        r_ = pg_.get("r", (0.0005, 0.0015))
        gap = np.where(on, (1.0 - smoothstep(float(r_[0]), float(r_[1]), dxs)) *
                       (1.0 - smoothstep(y1 - 0.03, y1 - 0.015, ys)), 0.0) * float(pg_.get("open", 1.0))
        a = a * (1.0 - gap)
        log(f"part: {int((gap > 0.5).sum())} texels open, {int(band.sum())} texels of dark roots beside it")
    rgb = hair_atlas.lin_to_srgb(np.clip(np.array(st["root"]) * 2.2, 0, 1))
    if st.get("cap_color"):
        # (style cap_color, a hex colour, off by default) the cap's own colour instead of the root's x 2.2: Silvia's
        # strands are peach from the root (her regrowth is darkened in by root_tone), her scalp's roots near-black
        rgb = hair_atlas.lin_to_srgb(np.clip(np.array(lin(st["cap_color"])), 0, 1))
    img = np.ones((size, size, 4), np.float32)
    img[..., :3] = rgb
    img[..., 3] = a
    return img


def regrowth_weight(P, st, fr, rt):
    """root_tone's band by the part's distance alone (`part` [r0, r1] in the top `cap` metres) and its `crown`
    wedge, at points P: for the surfaces the cards do not cover (under_roots)."""
    pa, pb = part_line(st, fr)
    ab = (pb - pa)[:2]
    tpar = np.clip(((P[:, :2] - pa[:2]) @ ab) / max(float(ab @ ab), 1e-9), 0.0, 1.0)
    dp = np.linalg.norm(P[:, :2] - (pa[:2] + tpar[:, None] * ab), axis=1)
    r0, r1 = (float(x) for x in rt["part"])
    zc = float(fr["top"]) - float(rt.get("cap", 0.05))
    w = smoothstep(r1, r0, dp) * smoothstep(zc - 0.02, zc, P[:, 2])
    cr = rt.get("crown")
    if cr:
        dz = np.clip((float(fr["top"]) - P[:, 2]) / float(cr.get("depth", 0.09)), 0.0, 1.0)
        hw = float(cr.get("r", 0.025)) * (1.0 - dz)
        dx = np.abs(P[:, 0] - pb[0])
        wc = (np.clip(1.0 - (dx - hw) / float(cr.get("soft", 0.015)), 0.0, 1.0) ** 2 *
              (1.0 - smoothstep(0.55, 1.0, dz)) * smoothstep(pb[1] - 0.02, pb[1] + 0.01, P[:, 1]) *
              float(cr.get("amount", 0.7)))
        w = np.maximum(w, wc)
    return w


def under_image(G, st, size=1024, fr=None):
    """The underlayer's colour in the shell's UVs: its colour x a little of the bake's light and dark (0.7-1.3),
    so it is not a flat sheet. sRGB."""
    tex = np.asarray(G["shell_tex"], np.float32)
    if tex.shape[0] != size:
        k = max(1, tex.shape[0] // size)
        tex = tex[:size * k, :size * k].reshape(size, k, size, k, -1).mean((1, 3))
    lum = hair_atlas.srgb_to_lin(tex[..., :3]) @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    f = 0.7 + 0.6 * smoothstep(0.0, 0.08, lum)
    rgb = hair_atlas.lin_to_srgb(np.clip(np.array(st["under"], np.float32)[None, None] * f[..., None], 0, 1))
    ur, rt = st.get("under_roots"), st.get("root_tone") or {}
    if ur and fr is not None and st.get("part") and rt.get("part"):
        # (style under_roots {dark}, off by default) the underlayer darkened as root_tone darkens the cards (the
        # part's band and its crown wedge, x dark): where the cards part at the crown it would show as a pale streak
        # at the part's back end from behind
        Vs, Ts = np.asarray(G["shell_V"], np.float64), np.asarray(G["shell_T"], np.int64)
        C = Vs[Ts].mean(1)
        pa, _ = part_line(st, fr)
        sel = (np.abs(C[:, 0] - pa[0]) < 0.08) & (C[:, 2] > float(fr["top"]) - 0.16)
        pos = uv_raster(np.asarray(G["shell_UV"], np.float64), Vs[Ts], size, sel)
        ok = np.isfinite(pos[..., 0])
        w = regrowth_weight(np.where(ok[..., None], pos, 0.0).reshape(-1, 3), st, fr, rt).reshape(size, size) * ok
        rgb = rgb * (1.0 - w * (1.0 - float(ur.get("dark", 0.3))))[..., None].astype(np.float32)
        log(f"underlayer: {int((w > 0.5).sum())} texels darkened to x{float(ur.get('dark', 0.3)):.2f} along the part "
            f"and the crown, {int(((w > 0.05) & (w <= 0.5)).sum())} partly")
    return np.concatenate([rgb, np.ones((size, size, 1), np.float32)], -1).astype(np.float32)


def tone_exposed(cards, te):
    """(style tone_exposed, a dict, off by default) a card row with no other card's opaque stretch over it (within
    `r` metres beside it, 0.3 mm to `h` above it along the hair's normal) is outer hair, in the light: no darker than
    `min` (its depth tone raised; layers in `skip` keep theirs). The depth tone darkens the inner layers as if under
    other hair; where the outer layer leaves a gap (fanning out from the part, at the roll's bend) an inner card
    showed whole as a dark flat patch with its card's straight edges: a dark square by the part, dark slots at the
    far front corner. Vertex colours only, no draw."""
    tmin = float(te.get("min", 0.7))
    r = float(te.get("r", 0.003))
    h = float(te.get("h", 0.008))
    skip = set(te.get("skip", ("roll",)))
    names = cards.names()
    V = np.array(cards.V).reshape(-1, 3)
    A = np.array(cards.COL)[:, 3]
    N = np.array(cards.NRM).reshape(-1, 3)
    C, Nc, card, opq = [], [], [], []
    for j, (b0, m) in enumerate(cards.rows):
        C.append((V[b0:b0 + 2 * m:2] + V[b0 + 1:b0 + 2 * m:2]) * 0.5)
        Nc.append(N[b0:b0 + 2 * m:2])
        card.append(np.full(m, j))
        opq.append(A[b0:b0 + 2 * m:2] > 0.6)
    C, Nc, card, opq = np.concatenate(C), np.concatenate(Nc), np.concatenate(card), np.concatenate(opq)
    Cop, cop = C[opq], card[opq]
    pts = Points(Cop)
    rr = math.hypot(r, h)
    exposed = np.zeros(len(C), bool)
    for i in range(len(C)):
        cov = False
        for j, _ in pts.within(C[i], rr):
            if cop[j] == card[i]:
                continue
            dv = Cop[j] - C[i]
            up = float(dv @ Nc[i])
            if 0.0003 < up < h and vlen(dv - Nc[i] * up) < r:
                cov = True
                break
        exposed[i] = not cov
    n_t = 0
    k = 0
    for j, (b0, m) in enumerate(cards.rows):
        ex = exposed[k:k + m]
        k += m
        if names[j] in skip or not ex.any():
            continue
        for q in np.nonzero(ex)[0]:
            for v in (b0 + 2 * q, b0 + 2 * q + 1):
                r_, g_, b_, a_ = cards.COL[v]
                if g_ < tmin:
                    f_ = tmin / max(g_, 1e-6)
                    cards.COL[v] = (min(1.0, r_ * f_), min(1.0, tmin), min(1.0, b_ * f_), a_)
                    n_t += 1
    log(f"exposed: {int(exposed.sum())} of {len(C)} card rows with no card over them, {n_t} vertices raised to "
        f"tone {tmin}")


def _blur_wrap(E, s):
    """Gaussian blur (sigma s cells) of a (theta, phi) grid: wrapped in phi, clamped in theta. numpy only."""
    r = max(1, int(math.ceil(3 * s)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
    k /= k.sum()
    P = np.pad(E, ((r, r), (0, 0)), mode="edge")
    E = sum(w * P[i:i + E.shape[0]] for i, w in enumerate(k))
    P = np.pad(E, ((0, 0), (r, r)), mode="wrap")
    return sum(w * P[:, i:i + E.shape[1]] for i, w in enumerate(k))


def relief_tone(cards, rt, fr):
    """(style relief_tone, a dict, short hair, off by default) each card vertex's depth tone taken toward its depth
    under the hair's smooth outer surface: the outermost card vertex per direction from the skull's middle (`cell`
    degree cells, a 3-cell max), Gaussian-smoothed over `sigma` degrees; tone f = lo at `depth`[1] metres under it or
    deeper, 1 within depth[0], mixed in by `mix` (cards of the `skip` layers keep theirs). The layers' own tones
    (inner 0.3, middle 0.6, outer 0.9) lie over the hair as a random mosaic, because the guide's 8 mm relief of curl
    clumps puts any layer outermost on a clump, and the hair reads as a dark rounded mass of card patches. By depth, a
    clump's crest is lit and the grooves between clumps dark, the same on every card there. Vertex colours only, no
    draw."""
    cs = float(rt.get("cell", 1.5))
    sig = float(rt.get("sigma", 6.0))
    d0, d1 = (float(v) for v in rt.get("depth", (0.001, 0.009)))
    lo = float(rt.get("lo", 0.35))
    k = float(rt.get("mix", 0.75))
    skip = set(rt.get("skip", ("front_lock", "curl_tip", "fly", "ear")))
    names = cards.names()
    V = np.array(cards.V).reshape(-1, 3)
    COL = np.array(cards.COL, np.float64).reshape(-1, 4)
    d = V - fr["centre"]
    r = np.linalg.norm(d, axis=1)
    u = d / np.maximum(r, 1e-9)[:, None]
    nt, npf = int(180 / cs) + 1, int(round(360 / cs))
    it = np.clip((np.degrees(np.arccos(np.clip(u[:, 2], -1, 1))) / cs).astype(int), 0, nt - 1)
    ip = ((np.degrees(np.arctan2(u[:, 1], u[:, 0])) + 180.0) / cs).astype(int) % npf
    E = np.zeros((nt, npf))
    np.maximum.at(E, (it, ip), r * (COL[:, 3] > 0.3))
    Pm = np.pad(E, ((1, 1), (0, 0)), mode="edge")
    Em = np.maximum(np.maximum(Pm[:-2], Pm[1:-1]), Pm[2:])
    E = np.maximum(np.maximum(np.roll(Em, 1, 1), Em), np.roll(Em, -1, 1))
    W = _blur_wrap((E > 0).astype(np.float64), sig / cs)
    Es = _blur_wrap(E, sig / cs) / np.maximum(W, 1e-6)
    depth = Es[it, ip] - r
    f = lo + (1.0 - lo) * (1.0 - smoothstep(d0, d1, depth))
    keep = np.zeros(len(V), bool)
    # (`clump` {amp, scale, seed}, optional) each card's tone x 1 +- amp by a smooth noise of its root over `scale`
    # metres (clump_tone's, which the mix all but replaces): the relief alone left the hair over the forehead even at
    # the scale of locks (contrast there 0.37 -> 0.30 in Amphi 4 at golden hour)
    cl_ = rt.get("clump") or None
    cf = np.ones(len(V))
    for j, (b0, m) in enumerate(cards.rows):
        if names[j] in skip:
            keep[b0:b0 + 2 * m] = True
        elif cl_:
            k_ = vnoise((V[b0] + V[b0 + 1]) * 0.5, float(cl_.get("scale", 0.035)), int(cl_.get("seed", 5)))
            cf[b0:b0 + 2 * m] = 1.0 + float(cl_.get("amp", 0.3)) * (2.0 * k_ - 1.0)
    t0 = np.maximum(COL[:, 1], 1e-6)
    tn = np.where(keep, t0, np.clip((t0 * (1.0 - k) + f * k) * cf, 0.05, 1.0))
    COL[:, :3] = np.clip(COL[:, :3] * (tn / t0)[:, None], 0.0, 1.0)
    cards.COL = [tuple(float(x) for x in c) for c in COL]
    vis = COL[:, 3] > 0.5
    log(f"relief tone: depth under the outer surface p10/50/90 "
        f"{' / '.join(f'{v * 1000:.1f}' for v in np.percentile(depth[vis], [10, 50, 90]))} mm, tone {lo}-1 mixed "
        f"{k}, {int((~keep).sum())} vertices")


def roll_deflate(Vsm, Tw, und, body, fr, rd):
    """(style roll_deflate, a dict, with roll_under, off by default) beside the temples (more than `x` metres beside
    the eyes) the guide within `reach` of the roll's cut underside is pulled in toward the skin, to at most `max`
    metres off it (in full within half of reach, fading out over the rest). The scan sculpts the curtain swept out
    over each temple as a wing curling forward, its lip 1.5-3.6 cm off the skin; with the underside cut, the space
    under it was open: with the head turned toward the camera, the far front corner was a hollow lined with short
    fills on the bare scalp and the side hair's underlayer, near-black slots between stacked strands, and under the
    near curtain a pale band of faded roots. Pulled in, the wing comes down onto the temple as real hair does.
    Moves Vsm in place (before the cut's own rules read it). No draw."""
    e_ = fr["eye"]
    x0 = float(rd.get("x", 0.045))
    reach = float(rd.get("reach", 0.025))
    hmax = float(rd.get("max", 0.012))
    cv = np.unique(Tw[und])
    cv = cv[np.abs(Vsm[cv, 0] - e_[0]) > x0 - 0.01]
    if not len(cv):
        return
    d0, _ = Points(Vsm[cv]).nearest(Vsm)
    w = (1.0 - smoothstep(reach * 0.5, reach, d0)) * smoothstep(x0 - 0.01, x0, np.abs(Vsm[:, 0] - e_[0]))
    n_mv, mx = 0, 0.0
    for i in np.nonzero(w > 0.01)[0]:
        r = body.nearest(Vsm[i], 0.1)
        if r is None or r[3] <= hmax:
            continue
        loc, d = r[0], r[3]
        dn = d - w[i] * (d - hmax)
        Vsm[i] = loc + (Vsm[i] - loc) / d * dn
        n_mv += 1
        mx = max(mx, d - dn)
    log(f"roll: {n_mv} guide verts within {reach * 1000:.0f} mm of the underside beside the temples pulled in to "
        f"{hmax * 1000:.0f} mm off the skin (moved {mx * 1000:.0f} mm at most)")


def roll_tuck(Vsm, Tw, keep, und, Cs, body, fr, rk):
    """(style roll_tuck, a dict, with roll_under, off by default) beside the temples (more than `x` metres beside
    the eyes) the roll's underside is not cut but tucked in: its vertices (not the lip it shares with the outer
    surface) are laid on the skin `clear` off it and relaxed (`iters` steps, the lip and the rest of the guide held),
    so the underside becomes a slope from the roll's lip down onto the temple, guide like the rest (its strands run
    on down it, with underlayer under them). With roll_deflate the lip already lies within 12 mm of the skin; cut
    there, every under-layer strand ended on one line along the curtain's lower edge over the near temple, a row of
    short lighter card stubs with blunt ends. Moves Vsm in place; returns the underside still cut (in front,
    where roll_drape, roll_fill and roll_bare keep working; roll_tone also reaches from the tucked part). No draw."""
    e_ = fr["eye"]
    x0 = float(rk.get("x", 0.045))
    clear = float(rk.get("clear", 0.004))
    tu = und & (np.abs(Cs[:, 0] - e_[0]) > x0)
    if not tu.any():
        return und
    other = keep & ~und
    Nt = unit(np.cross(Vsm[Tw[:, 1]] - Vsm[Tw[:, 0]], Vsm[Tw[:, 2]] - Vsm[Tw[:, 0]]))
    vt = np.unique(Tw[tu])
    near_t = np.zeros(len(Vsm), bool)
    near_t[vt] = True
    # the kept faces round the tucked underside facing away from the skin: the roll's outer surface (its lip stays)
    adj = np.nonzero(other & near_t[Tw].any(1))[0]
    outer = np.zeros(len(Tw), bool)
    for t in adj:
        c = Vsm[Tw[t]].mean(0)
        r = body.nearest(c, 0.1)
        if r is None or float((c - r[0]) @ Nt[t]) > 0.0:
            outer[t] = True
    lip = np.zeros(len(Vsm), bool)
    lip[np.unique(Tw[outer])] = True
    mv = vt[~lip[vt]]
    P0 = Vsm[mv].copy()
    for k, i in enumerate(mv):
        r = body.nearest(Vsm[i], 0.1)
        if r is not None:
            Vsm[i] = r[0] + body.normal_at(r[1], r[2]) * clear
    # relaxed with the lip and everything else held (a slope from the lip, not a wall straight down to the skin)
    e = np.sort(np.concatenate([Tw[tu][:, [0, 1]], Tw[tu][:, [1, 2]], Tw[tu][:, [2, 0]]]), axis=1)
    e = np.unique(e, axis=0)
    free = np.zeros(len(Vsm), bool)
    free[mv] = True
    for _ in range(int(rk.get("iters", 12))):
        acc = np.zeros_like(Vsm)
        deg = np.zeros(len(Vsm))
        np.add.at(acc, e[:, 0], Vsm[e[:, 1]])
        np.add.at(acc, e[:, 1], Vsm[e[:, 0]])
        np.add.at(deg, e[:, 0], 1.0)
        np.add.at(deg, e[:, 1], 1.0)
        m = free & (deg > 0)
        Vsm[m] = Vsm[m] + 0.5 * (acc[m] / deg[m, None] - Vsm[m])
        for i in np.nonzero(m)[0]:
            r = body.nearest(Vsm[i], 0.1)
            if r is not None and r[3] < clear:
                Vsm[i] = r[0] + body.normal_at(r[1], r[2]) * clear
    mvd = np.linalg.norm(Vsm[mv] - P0, axis=1)
    log(f"roll: {int(tu.sum())} underside tris beside the temples tucked onto the skin ({len(mv)} verts moved "
        f"{float(np.median(mvd)) * 1000:.0f} mm median, {float(mvd.max()) * 1000:.0f} mm at most; lip "
        f"{int(lip[vt].sum())} verts)")
    fr["roll_tuck"] = (Vsm, Tw[tu])
    return und & ~tu


# ------------------------------------------------------------------ everything (no bpy: also runs in python3.11)
def root_tone(cards, G, Vs, Ts, fr, rt, st):
    """(style root_tone, a dict, off by default) the cards darkened where the scan paints the hair under them dark:
    regrowth, dark roots along a centre part and over the crown under dyed lengths. The atlas' root -> tip
    ramp cannot give that: most cards are rooted on top of other hair, not at the scalp, so their root colour lands
    anywhere, and the shader flattens it (ramp_flatten). Each card vertex's colour (COL.rgb, its depth tone) is
    multiplied by `dark` where the shell's baked lightness under it (Lab L per guide vertex, the median of its
    triangles' corners and centre, smoothed over its neighbours `iters` times) is at most L[0], not at all from L[1]
    up; only `z` metres or more over the eyes (fading in over 3 cm: lower down the scan's dark paint is the shading
    between locks) and within 3 cm of the shell."""
    tex = np.asarray(G["shell_tex"], np.float32)
    if tex.max() > 1.5:
        tex = tex / 255.0
    UV = np.asarray(G["shell_UV"], np.float64)
    samp = np.stack([sample_img(tex, UV[:, k]) for k in range(3)] + [sample_img(tex, UV.mean(1))])
    Lt = np.median(to_lab(samp)[..., 0], axis=0)
    acc = np.zeros(len(Vs))
    cnt = np.zeros(len(Vs))
    np.add.at(acc, Ts.ravel(), np.repeat(Lt, 3))
    np.add.at(cnt, Ts.ravel(), 1.0)
    Lv = acc / np.maximum(cnt, 1.0)
    e = np.unique(np.sort(np.concatenate([Ts[:, [0, 1]], Ts[:, [1, 2]], Ts[:, [2, 0]]]), axis=1), axis=0)
    deg = np.zeros(len(Vs))
    np.add.at(deg, e.ravel(), 1.0)
    for _ in range(int(rt.get("iters", 12))):
        s = np.zeros(len(Vs))
        np.add.at(s, e[:, 0], Lv[e[:, 1]])
        np.add.at(s, e[:, 1], Lv[e[:, 0]])
        Lv = 0.5 * Lv + 0.5 * s / np.maximum(deg, 1.0)
    L0, L1 = (float(x) for x in rt.get("L", (27.0, 40.0)))
    z0 = float(fr["eye"][2]) + float(rt.get("z", 0.03))
    wv = smoothstep(L1, L0, Lv) * smoothstep(z0, z0 + 0.03, Vs[:, 2])
    d, i = Points(Vs).nearest(cards["V"])
    ok = i >= 0
    w = np.zeros(len(cards["V"]))
    w[ok] = wv[i[ok]] * (1.0 - smoothstep(0.015, 0.03, d[ok]))
    if rt.get("part") and st.get("part"):
        # `part` [r0, r1]: also every card vertex within r0 (in full) to r1 (none) of the centre part, measured level
        # (x, y) to the part's segment from the front hairline to behind the top, and in the top `cap` metres of the
        # head (fading in over 2 cm below): the scan paints its roots on its own shell, which has holes along the
        # part where the cards grow over the bare scalp, so the texture alone darkened a strip 1.5 cm wide
        pa, pb = part_line(st, fr)
        P = cards["V"]
        ab = (pb - pa)[:2]
        tpar = np.clip(((P[:, :2] - pa[:2]) @ ab) / max(float(ab @ ab), 1e-9), 0.0, 1.0)
        dp = np.linalg.norm(P[:, :2] - (pa[:2] + tpar[:, None] * ab), axis=1)
        r0, r1 = (float(x) for x in rt["part"])
        zc = float(fr["top"]) - float(rt.get("cap", 0.05))
        if rt.get("tex_part") is not None:
            # (`tex_part`, metres, off by default) the scan's dark paint counts only within this of the part (fading
            # out over 1 cm), where the scan's paint is uneven from side to side
            w = w * (1.0 - smoothstep(float(rt["tex_part"]), float(rt["tex_part"]) + 0.01, dp))
        w = np.maximum(w, smoothstep(r1, r0, dp) * smoothstep(zc - 0.02, zc, P[:, 2]))
        w_core = smoothstep(r0 + 0.004, r0, dp) * smoothstep(zc - 0.02, zc, P[:, 2])
        if rt.get("crown"):
            # (`crown` {depth, r, soft, amount}, off by default) the regrowth carried on from the part's back end down
            # the middle of the back of the head, narrowing: within r (in full, + soft to none) of the head's middle
            # line at the top, to nothing `depth` metres under the top, at `amount` of the part's darkening. With the
            # scan's own paint off (L [0, 1]) the part's band alone stops at the crown
            cr = rt["crown"]
            dz = np.clip((float(fr["top"]) - P[:, 2]) / float(cr.get("depth", 0.09)), 0.0, 1.0)
            hw = float(cr.get("r", 0.025)) * (1.0 - dz)
            dx = np.abs(P[:, 0] - pb[0])
            soft = float(cr.get("soft", 0.015))
            wc = (np.clip(1.0 - (dx - hw) / soft, 0.0, 1.0) ** 2 * (1.0 - smoothstep(0.55, 1.0, dz))
                  * smoothstep(pb[1] - 0.02, pb[1] + 0.01, P[:, 1]) * float(cr.get("amount", 0.7)))
            w = np.maximum(w, wc)
            if cr.get("solid"):
                # (`crown.solid`, 0-1, off by default) the wedge kept dark on spared cards too (spare leaves it as
                # scattered dark streaks from behind instead of one dark V)
                w_core = np.maximum(w_core, wc * float(cr["solid"]))
            log(f"root tone: crown {int((wc > 0.5).sum())} card vertices over half, {int((wc > 0.05).sum())} touched")
    else:
        w_core = np.zeros(len(cards["V"]))
    if rt.get("spare") and len(cards.get("F", ())):
        # (`spare` [fraction, amount], off by default) that fraction of the cards (a hash of each card's root, not the
        # build's random sequence) keeps `amount` of its colour through the regrowth: her roots in her photos and
        # portrait are dark at the part with peach strands through them, not a solid plate
        frac_, amt_ = (float(x) for x in rt["spare"])
        nrow = len(cards["V"]) // 2
        link = np.zeros(nrow, bool)
        link[np.asarray(cards["F"])[:, 0] // 2] = True
        start = np.ones(nrow, bool)
        start[1:] = ~link[:-1]
        cid_ = np.cumsum(start) - 1
        roots_ = np.nonzero(start)[0]
        spared = np.array([hash01(cards["V"][2 * r] * 1.37 + 0.11) < frac_ for r in roots_], bool)
        sv = np.repeat(spared[cid_], 2)
        # (not within the part's own `part`[0]: the regrowth itself, at the scalp, is dark on every strand)
        w = np.where(sv, np.maximum(w * (1.0 - amt_), w_core), w)
        log(f"root tone: {int(spared.sum())} of {len(roots_)} cards spared ({amt_:.2f} of their colour kept)")
    if rt.get("part_cards") and rt.get("part") and st.get("part") and len(cards.get("F", ())):
        # (`part_cards` {r, side, len, soft, cap}, off by default) the cards rooted within r of the part (in the top
        # `cap` m of the head) darkened along their first `len` m from the root (fading out over `soft`), whatever
        # their position: those falling to `side` (-1 the character's right, +1 the left, 0 both; by the mean side of
        # their first `len`). Long hair's rows lie 2 cm apart, so such a card's colour ramps from the part's dark to
        # its second row's, already graded or spared (spare), and the part-rooted cards that all flow to one side
        # leave that side of the part light; spare does not apply to this
        pc = rt["part_cards"]
        pa_, pb_ = part_line(st, fr)
        V_ = cards["V"]
        nrow = len(V_) // 2
        link = np.zeros(nrow, bool)
        link[np.asarray(cards["F"])[:, 0] // 2] = True
        start = np.ones(nrow, bool)
        start[1:] = ~link[:-1]
        cid_ = np.cumsum(start) - 1
        rowP = 0.5 * (V_[0::2] + V_[1::2])
        seg = np.zeros(nrow)
        seg[1:] = np.where(start[1:], 0.0, np.linalg.norm(rowP[1:] - rowP[:-1], axis=1))
        cs = np.cumsum(seg)
        arc = cs - np.maximum.accumulate(np.where(start, cs, 0.0))
        ab_ = (pb_ - pa_)[:2]
        tq = np.clip(((rowP[:, :2] - pa_[:2]) @ ab_) / max(float(ab_ @ ab_), 1e-9), 0.0, 1.0)
        dxr = rowP[:, 0] - (pa_[0] + tq * ab_[0])
        roots_ = np.nonzero(start)[0]
        ln_, soft_ = float(pc.get("len", 0.035)), float(pc.get("soft", 0.015))
        near = (np.abs(dxr[roots_]) < float(pc.get("r", 0.004))) & \
            (rowP[roots_, 2] > float(fr["top"]) - float(pc.get("cap", rt.get("cap", 0.05))))
        # (`probe` m, default `len`: how far along a card its side is read, and `pass` looks for the part)
        pr_ = float(pc.get("probe", ln_))
        first = (arc > 0.005) & (arc < pr_)
        sx = np.zeros(len(roots_))
        nx = np.zeros(len(roots_))
        np.add.at(sx, cid_[first], dxr[first])
        np.add.at(nx, cid_[first], 1.0)
        side_ = float(pc.get("side", 0))
        on_side = (side_ == 0) | (np.sign(sx / np.maximum(nx, 1.0)) == np.sign(side_))
        sel = near & on_side
        wp = sel[cid_] * (1.0 - smoothstep(ln_, ln_ + soft_, arc))
        if pc.get("pass"):
            # (`pass` m, off by default) also the cards rooted anywhere whose rows within their first `probe` m come
            # within `pass` of the part (that row in the top `cap` m), on `side`: darkened by the distance along the
            # card from that closest row plus the row's own distance from the part (len, soft). Cards rooted off the
            # part lie over its edge as light strands between the part-rooted ones, whose dark would otherwise run
            # down as hard-edged patches; spare does not apply to this either
            zc_ = float(fr["top"]) - float(pc.get("cap", rt.get("cap", 0.05)))
            dd = np.where((arc < pr_) & (rowP[:, 2] > zc_), np.abs(dxr), np.inf)
            best = np.full(len(roots_), np.inf)
            np.minimum.at(best, cid_, dd)
            arc_c = np.zeros(len(roots_))
            hit = np.isfinite(dd) & (dd <= best[cid_])
            arc_c[cid_[hit]] = arc[hit]
            psel = (best < float(pc["pass"])) & on_side
            sq = np.abs(arc - arc_c[cid_]) + np.where(np.isfinite(best), best, 1.0)[cid_]
            wp = np.maximum(wp, psel[cid_] * (1.0 - smoothstep(ln_, ln_ + soft_, sq)))
            log(f"root tone: part cards: {int((psel & ~sel).sum())} more passing within {float(pc['pass']) * 1000:.0f} "
                f"mm of the part")
        w = np.maximum(w, np.repeat(wp, 2))
        log(f"root tone: part cards {int(near.sum())} rooted within {float(pc.get('r', 0.004)) * 1000:.0f} mm of the "
            f"part, {int(sel.sum())} darkened along their first {ln_ * 100:.1f} cm (side {side_:+.0f})")
    dark = float(rt.get("dark", 0.2))
    cards["COL"][:, :3] *= (1.0 - w * (1.0 - dark))[:, None].astype(cards["COL"].dtype)
    if rt.get("tint"):
        # (`tint` [r, g, b], off by default) the regrowth's colour: the darkened vertices' colour x tint in proportion
        # to their darkening (the atlas holds the lengths' colour, and a plain darkening of it keeps its warmth)
        tn = np.asarray(rt["tint"], np.float64)
        cards["COL"][:, :3] *= (1.0 + w[:, None] * (tn[None] - 1.0)).astype(cards["COL"].dtype)
    log(f"root tone: {int((wv > 0.5).sum())} of {len(Vs)} guide verts dark (L {L0:.0f}-{L1:.0f}); "
        f"{int((w > 0.5).sum())} card vertices darkened to x{dark:.2f}, {int(((w > 0.05) & (w <= 0.5)).sum())} partly")


def neck_clear(cards, body, fr, nc):
    """(style neck_clear, a dict, off by default) card rows lying in front of the neck under the jaw hidden (vertex
    alpha 0, from a card's first row in the zone to its tip): row midpoints `z` [top, bottom] metres under the eyes'
    centre, within `x` metres of the middle, within `d` metres of skin facing forward (its normal's y under `ny`; the
    character faces -y). Long hair can end in flat inner cards lying across the base of the neck at the collar, which
    read as smudges at the front dialogue cameras. The opaque points of the hidden rows go too (the underlayer and the
    cap read them). Vertex colours only, no draw."""
    e = fr["eye"]
    z0, z1 = (float(v) for v in nc.get("z", (0.085, 0.2)))
    xw = float(nc.get("x", 0.04))
    dmax = float(nc.get("d", 0.025))
    ny = float(nc.get("ny", -0.3))
    V = np.asarray(cards["V"])
    nrow = len(V) // 2
    M = 0.5 * (V[0::2] + V[1::2])
    zr = M[:, 2] - e[2]
    inz = np.zeros(nrow, bool)
    for r in np.nonzero((zr < -z0) & (zr > -z1) & (np.abs(M[:, 0] - e[0]) < xw))[0]:
        hit = body.nearest(M[r], dmax)
        if hit is not None and float(body.normal_at(hit[1], hit[2])[1]) < ny:
            inz[r] = True
    link = np.zeros(nrow, bool)
    link[np.asarray(cards["F"])[:, 0] // 2] = True
    start = np.ones(nrow, bool)
    start[1:] = ~link[:-1]
    cid = np.cumsum(start) - 1
    first = np.full(int(cid[-1]) + 1 if nrow else 0, nrow)
    np.minimum.at(first, cid[inz], np.nonzero(inz)[0])
    hide = np.arange(nrow) >= first[cid]
    cards["COL"][np.repeat(hide, 2), 3] = 0.0
    n_op = 0
    if hide.any():
        hp = Points(M[hide])
        for k in ("opaque", "dense"):
            pts = cards.get(k)
            if pts is not None and len(pts):
                dd, _ = hp.nearest(np.asarray(pts))
                keep = dd > 0.005
                n_op += int((~keep).sum())
                cards[k] = np.asarray(pts)[keep]
    log(f"neck: {int(hide.sum())} card rows of {int(len(np.unique(cid[hide])))} cards in front of the neck under the "
        f"jaw hidden ({int(inz.sum())} rows in the zone; {n_op} opaque points dropped)")


def generate(G, st, seed=1):
    t0 = time.time()
    rng = np.random.default_rng(seed)
    fr = frame_of(G)
    log(f"style {st['name']} ({st['flow']}), eye {np.round(fr['eye'], 3).tolist()}, top {fr['top']:.3f}")
    base = hair_base(G, fr, st)
    coll = Mesh(G["coll_V"], G["coll_T"]) if G.get("coll_T") is not None and len(G["coll_T"]) else None
    # the guide: the smoothed shell (outside the face window for long hair) + the bare scalp (+ cape)
    Vs, Ts = np.asarray(G["shell_V"], np.float64), np.asarray(G["shell_T"], np.int64)
    Vw, Tw, inv = weld_map(Vs, Ts)
    Vsm = taubin(Vw, Tw, int(st["smooth"]))
    mv = np.linalg.norm(Vsm - Vw, axis=1)
    log(f"shell smoothed ({st['smooth']} Taubin steps): mean move {mv.mean() * 1000:.1f} mm, max {mv.max() * 1000:.1f} mm")
    if st.get("deflate"):
        # the front of the head: the scan sculpts the hair at the hairline as a rolled ledge 1.5-2 cm off the
        # skin; the cards ran level along it and its underside showed as a flat dark beak beside the temple.
        # Lying flat from a part, hair there is a few mm thick: pull the guide in to `deflate` off the skin
        body0 = base["body"]
        e, ef = fr["eye"], fr["eye_front"]
        w = (1.0 - smoothstep(ef + 0.03, ef + 0.07, Vsm[:, 1])) * smoothstep(e[2], e[2] + 0.03, Vsm[:, 2])
        n_mv = 0
        for i in np.nonzero(w > 0.01)[0]:
            r = body0.nearest(Vsm[i], 0.1)
            if r is None or r[3] <= st["deflate"]:
                continue
            loc, d = r[0], r[3]
            Vsm[i] = loc + (Vsm[i] - loc) / d * (d - w[i] * (d - st["deflate"]))
            n_mv += 1
        log(f"front of the guide pulled in to {st['deflate'] * 1000:.0f} mm off the skin: {n_mv} verts")
    if st.get("fill_pits"):
        hv = G["body_V"][np.unique(G["body_T"][G["body_head"]])]
        Vsm, n_mv, mx = fill_pits(Vsm, Tw, base["body"], hv, fr, st, float(st["fill_pits"]))
        log(f"guide pits filled (closing over {st['fill_pits'] * 1000:.0f} mm): {n_mv} verts raised, at most "
            f"{mx * 1000:.0f} mm")
    if st.get("front_lift") and not st["long"]:
        # (style front_lift, a dict, short hair, off by default) the guide over the front of the top lifted out along
        # its smoothed normal by up to `h` metres: in front of `y` [full, none] metres behind the eyes' front, from
        # `z` [none, full] metres over the brows, none within `rim` [none, full] metres of the shell's edge (the
        # hairline stays on the skin), for hair that stands up off the front of the head where the scan's lies flat.
        # Cards and underlayer follow the guide
        fl_ = st["front_lift"]
        Nl_ = smooth_normals(Vsm, vertex_normals(Vsm, Tw), 0.02)
        El_, _, _ = boundary_edges(Tw)
        d_rim, _ = Points(Vsm[np.unique(El_.ravel())]).nearest(Vsm)
        ef_ = fr["eye_front"]
        yr_, zr_, rr_ = fl_.get("y", (0.05, 0.11)), fl_.get("z", (0.02, 0.05)), fl_.get("rim", (0.008, 0.03))
        w_l = (smoothstep(float(rr_[0]), float(rr_[1]), d_rim) *
               (1.0 - smoothstep(ef_ + float(yr_[0]), ef_ + float(yr_[1]), Vsm[:, 1])) *
               smoothstep(fr["brow_z"] + float(zr_[0]), fr["brow_z"] + float(zr_[1]), Vsm[:, 2]))
        Vsm = Vsm + Nl_ * (float(fl_.get("h", 0.008)) * w_l)[:, None]
        log(f"front lift: {int((w_l > 0.05).sum())} guide verts lifted, up to {float(fl_.get('h', 0.008)) * 1000:.0f} mm")
    # (only a dict: the fringe and curtain flows' `crown` is their origin's offset, a tuple)
    if isinstance(st.get("crown"), dict) and st["crown"] and not st["long"]:
        # (style crown, a dict, short hair, off by default) the guide over the top of the head lowered by up to `drop`
        # metres (straight down, in full from z[1] metres over the brows, none below z[0]; the move smoothed over the
        # guide), never closer than `min` to the skin; cards rooted there lift only `lift` x their layer's lift
        # (generate's strand()), for hair that is lower and flatter on top than the scan's
        cr_ = st["crown"]
        zr_ = cr_.get("z", (0.05, 0.085))
        w_c = smoothstep(fr["brow_z"] + float(zr_[0]), fr["brow_z"] + float(zr_[1]), Vsm[:, 2])
        mv_c = float(cr_.get("drop", 0.006)) * w_c
        nb_ = [[] for _ in range(len(Vsm))]
        for a_, b_ in np.concatenate([Tw[:, [0, 1]], Tw[:, [1, 2]], Tw[:, [2, 0]]]).tolist():
            nb_[a_].append(b_)
            nb_[b_].append(a_)
        for _ in range(int(cr_.get("smooth", 8))):
            mv_c = 0.5 * mv_c + 0.5 * np.array([mv_c[n_].mean() if n_ else mv_c[i_] for i_, n_ in enumerate(nb_)])
        body_c = base["body"]
        cmin_ = float(cr_.get("min", 0.004))
        # (crown "inside", off by default) a lowered vertex that lands inside the head counts as too close too (the
        # distance to the skin is unsigned: without this, guide vertices dropped past the skull go through the crown,
        # and the skin and the scalp cap stand over the cards)
        in_ = bool(cr_.get("inside", False))
        n_c, n_cap = 0, 0
        for i in np.nonzero(mv_c > 2e-4)[0]:
            q0 = Vsm[i].copy()
            m_ = float(mv_c[i])
            for _ in range(6):
                q = q0 - np.array([0.0, 0.0, m_])
                r = body_c.nearest(q, 0.1)
                if r is None or (r[3] >= cmin_ and not (in_ and float((q - r[0]) @ body_c.FN[r[1]]) < 0.0)):
                    break
                m_ *= 0.6
            else:
                m_ = 0.0
            if m_ < float(mv_c[i]) - 1e-4:
                n_cap += 1
            Vsm[i] = q0 - np.array([0.0, 0.0, m_])
            n_c += 1
        fr["crown_w"] = (float(fr["brow_z"] + float(zr_[0])), float(fr["brow_z"] + float(zr_[1])),
                         float(cr_.get("lift", 1.0)))
        log(f"crown: {n_c} guide verts lowered, up to {float(cr_.get('drop', 0.006)) * 1000:.0f} mm "
            f"({n_cap} held at {cmin_ * 1000:.0f} mm off the skin)")
    if st.get("side_trim") and not st["long"]:
        # (style side_trim, a dict, short hair, off by default) the guide's sides pulled in toward the head's middle
        # (x only): by up to `in` metres either side between z[1] and z[2] metres over the brows, none below z[0] or
        # above z[3], plus `right` metres on the character's right (-x) between rz[1] and rz[2] (none outside rz[0],
        # rz[3]); each vertex by (its offset from the middle over the guide's widest there) squared, so the front and
        # back of the head keep their shape; the move smoothed over the guide, never closer than `min` to the skin
        trm_ = st["side_trim"]
        ex_, bz_ = float(fr["eye"][0]), float(fr["brow_z"])

        def trap_(z_, zz):
            return smoothstep(bz_ + float(zz[0]), bz_ + float(zz[1]), z_) * \
                (1.0 - smoothstep(bz_ + float(zz[2]), bz_ + float(zz[3]), z_))
        dx_ = Vsm[:, 0] - ex_
        zb_ = np.round((Vsm[:, 2] - bz_) / 0.003).astype(int)
        wid_ = np.zeros(len(Vsm))
        for s_ in (-1.0, 1.0):
            side_ = dx_ * s_ > 0
            for b_ in np.unique(zb_[side_]):
                m_ = side_ & (np.abs(zb_ - b_) <= 2)
                wid_[side_ & (zb_ == b_)] = float(np.abs(dx_[m_]).max())
        amt_ = float(trm_.get("in", 0.012)) * trap_(Vsm[:, 2], trm_.get("z", (0.035, 0.05, 0.075, 0.095)))
        if trm_.get("right"):
            amt_ = amt_ + float(trm_["right"]) * (dx_ < 0) * trap_(Vsm[:, 2], trm_.get("rz", (-0.01, 0.01, 0.05, 0.07)))
        mv_t = amt_ * np.clip(np.abs(dx_) / np.maximum(wid_, 1e-3), 0.0, 1.0) ** 2
        nb_t = [[] for _ in range(len(Vsm))]
        for a_, b_ in np.concatenate([Tw[:, [0, 1]], Tw[:, [1, 2]], Tw[:, [2, 0]]]).tolist():
            nb_t[a_].append(b_)
            nb_t[b_].append(a_)
        for _ in range(int(trm_.get("smooth", 8))):
            mv_t = 0.5 * mv_t + 0.5 * np.array([mv_t[n_].mean() if n_ else mv_t[i_] for i_, n_ in enumerate(nb_t)])
        body_t = base["body"]
        tmin_ = float(trm_.get("min", 0.006))
        n_t, n_tc, mx_t = 0, 0, 0.0
        for i in np.nonzero(mv_t > 2e-4)[0]:
            q0 = Vsm[i].copy()
            m_ = float(mv_t[i])
            sx_ = -1.0 if q0[0] > ex_ else 1.0
            for _ in range(6):
                q = q0 + np.array([sx_ * m_, 0.0, 0.0])
                r = body_t.nearest(q, 0.1)
                # (inside the head counts as too close: the distance is unsigned)
                if r is None or (r[3] >= tmin_ and float((q - r[0]) @ body_t.FN[r[1]]) >= 0.0):
                    break
                m_ *= 0.6
            else:
                m_ = 0.0
            if m_ < float(mv_t[i]) - 1e-4:
                n_tc += 1
            Vsm[i] = q0 + np.array([sx_ * m_, 0.0, 0.0])
            n_t += 1
            mx_t = max(mx_t, m_)
        log(f"side trim: {n_t} guide verts pulled in, up to {mx_t * 1000:.1f} mm ({n_tc} held at {tmin_ * 1000:.0f} mm "
            f"off the skin)")
    arms = glasses_arms(coll, fr, base["body"], np.random.default_rng(7)) if coll is not None else None
    if arms is not None:
        Vsm, mv = press_under_arms(Vsm, arms, base["body"])
        log(f"glasses: {int(mv.sum())} guide verts pressed under the arms")
    if not st["long"] and st.get("roll_under") and st.get("roll_smooth"):
        # (style roll_smooth, a dict, with roll_under, off by default) the guide round the roll's underside smoothed
        # further (`iters` more Taubin steps, in full within half of `reach` of it, none past `reach`): the scan
        # sculpts the curtain's roll at the temples as a stack of folded clumps, and smoothed 10 steps the far front
        # corner was still a cascade of thin folds 0.5-1 cm apart; every card follows the guide, and seen along the
        # outline from the near side the folds' cards stood as flat stacked planes with dark slots between
        rs_ = st["roll_smooth"]
        Nw0 = smooth_normals(Vsm, vertex_normals(Vsm, Tw), float(st.get("normal_r", 0.012)))
        nz0 = unit(Nw0[Tw].sum(1))[:, 2]
        Cs0 = Vsm[Tw].mean(1)
        und0 = (nz0 < -float(st["roll_under"])) & (Cs0[:, 1] < float(fr["ears"][:, 1].max()) - 0.01) & \
            (Cs0[:, 2] > float(fr["eye"][2]))
        if und0.any():
            reach_s = float(rs_.get("reach", 0.03))
            d0_, _ = Points(Vsm[np.unique(Tw[und0])]).nearest(Vsm)
            w_s = 1.0 - smoothstep(reach_s * 0.5, reach_s, d0_)
            mv_s = (taubin(Vsm, Tw, int(rs_.get("iters", 30))) - Vsm) * w_s[:, None]
            Vsm = Vsm + mv_s
            log(f"roll: {int((w_s > 0).sum())} guide verts round the roll's underside smoothed "
                f"{int(rs_.get('iters', 30))} more steps (moved at most "
                f"{float(np.linalg.norm(mv_s, axis=1).max()) * 1000:.1f} mm)")
    keep = np.ones(len(Tw), bool)
    Cs = Vsm[Tw].mean(1)
    if st.get("face_window"):
        keep = ~in_face_window(Cs, fr, 0.004)
        log(f"face window: {int((~keep).sum())} shell tris cut")
    elif st.get("front_floor") is not None:
        # short hair: nothing of the shell below the brows in front of the temples (a fringe sits on the brows,
        # never over the eyes or the glasses)
        low = np.array([floor_hit(c, fr, st) for c in Cs])
        keep = ~low
        log(f"front floor: {int(low.sum())} shell tris below the brows cut")
    cover_mask = None
    if st["long"] and st.get("underside"):
        # (style underside = a cosine, long hair, off by default) the shell's underside below the ears (its volume
        # normal turned down past the cosine) is no guide: the scan's hair rests on the shoulders as a thick sheet
        # whose bottom faces down beside the neck, and cards rooted on it (and strands falling onto it) ran along it
        # lit from below, ending together at its front edge: seen from the front, down through the gap between a
        # front lock and the neck, a smooth dark sculpted lock with a hard rounded lower edge over a dark pocket
        #. Without it, the strands reaching its edge fall on (fall_on) and no fill is rooted to cover it
        Nw = smooth_normals(Vsm, vertex_normals(Vsm, Tw), float(st.get("normal_r", 0.012)))
        nz = unit(Nw[Tw].sum(1))[:, 2]
        und = keep & (nz < -float(st["underside"])) & (Cs[:, 2] < float(fr["ears"][:, 2].min()))
        keep &= ~und
        cover_mask = np.ones(len(Vsm) + len(base["guide"][0]), bool)
        cover_mask[np.setdiff1d(np.unique(Tw[und]), np.unique(Tw[keep]))] = False
        log(f"underside: {int(und.sum())} shell tris below the ears facing down left out of the guide")
    if not st["long"] and st.get("roll_under"):
        # (style roll_under = a cosine, short hair, off by default) the underside of the hair's roll in front of
        # the ears (the smoothed shell's normal turned down past the cosine, above the eyes) is no guide: the scan
        # sculpts a curtain swept out to the temple as a rolled lip whose underside faces down and in, and the cards
        # rooted there (coverage fills for its bare vertices, hairline cards snapped up onto it from the hairline
        # under it: 80 and 106 of them) ran round the roll every which way, lit as an underside; seen past the
        # silhouette from above, a stack of flat card layers with straight stepped edges and the dark underlayer in
        # the gaps (Ian's far front corner), and along the curtain's lower edge a dark jagged lip of card ends.
        # Without it the outer layers run over the roll and fall on off its edge, nothing is rooted under it, no
        # fill covers it and it has no underlayer
        Nw = smooth_normals(Vsm, vertex_normals(Vsm, Tw), float(st.get("normal_r", 0.012)))
        nz = unit(Nw[Tw].sum(1))[:, 2]
        ey_ = float(fr["ears"][:, 1].max()) - 0.01
        und = keep & (nz < -float(st["roll_under"])) & (Cs[:, 1] < ey_) & (Cs[:, 2] > float(fr["eye"][2]))
        if st.get("roll_deflate") and und.any():
            roll_deflate(Vsm, Tw, und, base["body"], fr, st["roll_deflate"])
        if st.get("roll_tuck") and und.any():
            und = roll_tuck(Vsm, Tw, keep, und, Cs, base["body"], fr, st["roll_tuck"])
        keep &= ~und
        if cover_mask is None:
            cover_mask = np.ones(len(Vsm) + len(base["guide"][0]), bool)
        cover_mask[np.setdiff1d(np.unique(Tw[und]), np.unique(Tw[keep]))] = False
        log(f"roll: {int(und.sum())} shell tris on the roll's underside in front of the ears left out of the guide")
        if st.get("roll_end") and und.any():
            # (roll_end) a strand leaving the guide at the cut ends there instead of falling on off it (a few hung
            # down in front of the temple as flat tabs lit pale as the forehead)
            fr["roll_edge"] = Points(Vsm[np.unique(Tw[und])])
        if st.get("roll_drape") and und.any():
            fr["roll_lie"] = Points(Vsm[np.unique(Tw[und])])
        if und.any():
            fr["roll_under"] = (Vsm, Tw[und])
    Vgc, Tgc = base["guide"]
    Vg = np.concatenate([Vsm, Vgc])
    Tg = np.concatenate([Tw[keep], Tgc + len(Vsm)])
    # (normal_r: how far the guide's normal is averaged; it is every card's shading normal, so sleek hair wants a
    # wide one: lumps a few cm across otherwise lit each card on them as its own chip)
    surf = Surface(Vg, Tg, float(st.get("normal_r", 0.012)))
    flow = Flow(st, fr)
    if st.get("tex_w", 0) > 0 and G.get("shell_tex") is not None:
        F, c = texture_flow(G["shell_tex"], Vsm, Tw, np.asarray(G["shell_UV"], np.float64))
        TFs, TCs = vertex_texture_flow(flow, Vsm, Tw[keep], F[keep], c[keep])
        TF = np.zeros((len(Vg), 3))
        TC = np.zeros(len(Vg))
        TF[:len(Vsm)], TC[:len(Vsm)] = TFs, TCs
        flow.set_texture(TF, TC, surf.T)
        log(f"texture flow: median coherence {float(np.median(c)):.2f}, vertex agreement {float(np.median(TCs)):.2f}")
    drape = None
    if st.get("drape"):
        B = G["bones"]
        drape = dict(z_neck=float(B["neck_01"][2]) + 0.03, y_sh=float(B.get("upperarm_l", B["neck_01"])[1]))
        if st.get("front_len"):
            # front locks: rooted in front of the ears (front_y: metres behind the ears' front landmarks), they
            # leave the guide below the jaw (front_det: metres below the eyes) and hang front_len further
            drape.update(front_len=float(st["front_len"]),
                         front_y=float(fr["ears"][:, 1].min()) + float(st.get("front_y", 0.0)),
                         z_det=float(fr["eye"][2]) - float(st.get("front_det", 0.08)))
    gfront = GlassesFront(coll, fr) if coll is not None else None
    cards = build_hair(st, surf, flow, base, fr, rng, coll=coll, drape=drape, shell_part=(Vsm, Tw[keep]), arms=arms,
                       gfront=gfront, cover_mask=cover_mask)
    if st.get("root_tone") and len(cards["V"]) and G.get("shell_tex") is not None:
        root_tone(cards, G, Vsm, Tw, fr, st["root_tone"], st)
    if st.get("neck_clear") and len(cards["V"]):
        neck_clear(cards, base["body"], fr, st["neck_clear"])
    if st.get("lip_light") and not st["long"] and len(cards["V"]):
        # (style lip_light = metres, off by default) the cards' shading normal within lip_light over a fringe's
        # floor (and below it) turned toward the skin's under them: there the guide's smoothed normal is the
        # underside of the shell's front lip, facing down, and the curtain's lower edge, lit as that underside, read
        # as a dark jagged lip of card ends or a darker brim along a swept hairline
        body0 = base["body"]
        Vc_, Nc_ = cards["V"], cards["NRM"]
        n_l = 0
        for i in range(len(Vc_)):
            fz = floor_z(Vc_[i], fr, st)
            if fz is None:
                continue
            w = 1.0 - float(smoothstep(0.0, float(st["lip_light"]), Vc_[i][2] - fz))
            if w <= 0.0:
                continue
            rb = body0.nearest(Vc_[i], 0.05)
            if rb is None:
                continue
            Nc_[i] = vunit(Nc_[i] * (1.0 - w) + body0.normal_at(rb[1], rb[2]) * w)
            n_l += 1
        log(f"lip: {n_l} card vertices near the fringe's floor lit as the skin under them")
    cards["SHADOW"] = shadow_cut(cards["V"], fr) if len(cards["V"]) else np.zeros((0, 2), np.float32)
    if st.get("ear_stencil") and len(cards["F"]):
        # (style ear_stencil, off by default) the cards lying on or just over an ear are their own surface
        # (make(): material <id>_hair_scancards_ear, hair_scan_ear.gdshader), which does not mark the stencil as
        # hair: glasses_over_hair draws the temple arms over hair a few mm above them, and over the ear, where the
        # hair lies over the arm (glasses_arms leaves it unpressed there), it drew the earpiece's highlight across
        # the strands lying on the ear
        es = EarSide(base["body"].V, base["body"].T, fr)
        Cf = cards["V"][cards["F"]].mean(1)
        cards["EARF"] = np.array([es.below(c, 0.012) for c in Cf], bool)
        log(f"ears: {int(cards['EARF'].sum())} of {len(Cf)} card faces over the ears on their own surface")
    if len(cards["V"]):
        sc = cards["SHADOW"]
        log(f"shadow: {int(((sc[:, 0] > 0.5) & (sc[:, 1] < 0.5)).sum())} card vertices in front of the face below "
            f"the brows (the shadow pass leaves them out)")
    # the underlayer: the smoothed shell, 1.5 mm further in
    Nsm = vertex_normals(Vsm, Tw)
    Vu = Vsm - Nsm * 0.0015
    # out of the ears (the scan's hair passes through them: the underlayer cut each ear in a smooth dark arc)
    ne = np.nonzero(near_ears(Vu, fr))[0]
    if len(ne):
        P0 = Vu[ne].copy()
        Vu[ne] = push_out(Vu[ne], base["body"], 0.0015, solid=True, reach=0.03)
        log(f"underlayer: {int((np.abs(Vu[ne] - P0).sum(1) > 1e-6).sum())} verts moved out of the ears")
    if coll is not None:
        Vu, pressed = press_under_arms(Vu, arms, base["body"], under=True)
        side = ~pressed & (np.abs(Vu[:, 0] - fr["eye"][0]) > 0.055)
        Vu[side] = push_over(Vu[side], coll, base["body"], 0.003)
        Vu[~pressed & ~side] = push_out(Vu[~pressed & ~side], coll, 0.003)
    # only where cards lie over it: a stretch with no opaque card above it (the shell's edges at the nape, beside
    # the ears, along a cut hairline) showed as a smooth dark slab; without it the cap's dark roots and the skin
    # show there instead
    ukeep = keep.copy()
    cp = cards.get("opaque")
    if cp is not None and len(cp):
        reach = max(1.8 * st["cover"], 0.011)
        d, _ = Points(cp).nearest(Vsm[Tw].mean(1))
        bare = keep & (d > reach)
        ukeep = keep & ~bare
        log(f"underlayer: {int(bare.sum())} of {int(keep.sum())} tris with no card over them dropped")
        if st.get("under_front") and not st["long"]:
            # (style under_front = metres, off by default) no underlayer within under_front over a fringe's floor:
            # kept wherever a card's opaque stretch lies within 11 mm, it showed under the curtain's or the swept
            # hairline's lower edge, seen from below the cards' ends, as a dark smooth lip, its cut triangles a thin
            # stair-stepped dark line under the hair
            Ct_ = Vsm[Tw].mean(1)
            tight = ukeep & np.array([(fz is not None and c[2] - fz < float(st["under_front"])) for c, fz in
                                      ((c, floor_z(c, fr, st)) for c in Ct_)], bool)
            ukeep &= ~tight
            log(f"underlayer: {int(tight.sum())} tris within {float(st['under_front']) * 1000:.0f} mm over the "
                f"fringe's floor dropped")
        # and only facing its cards (the underlayer is drawn single-sided, hair_under.gdshader): a long hair
        # shell is a thick sheet whose inner side faces the neck, with the cards on its outer side; seen from the
        # front between a front lock and the back hair, that inner side was a smooth black pocket. Gone, and
        # culled from behind, the view in there ends on the backs of the cards: strands
        pts = Points(cp)
        Ct = Vsm[Tw].mean(1)
        Nt = unit(np.cross(Vsm[Tw[:, 1]] - Vsm[Tw[:, 0]], Vsm[Tw[:, 2]] - Vsm[Tw[:, 0]]))
        inner = np.zeros(len(Tw), bool)
        for i in np.nonzero(ukeep)[0]:
            near = [j for j, dd in pts.near_n(Ct[i], 24) if dd <= reach]
            if near and not ((cp[near] - Ct[i]) @ Nt[i] > 0.0005).any():
                inner[i] = True
        ukeep &= ~inner
        log(f"underlayer: {int(inner.sum())} tris facing away from their cards dropped")
        if st["long"] and st.get("under_inner"):
            # (style under_inner = a cosine, long hair, off by default) below the ears, no underlayer that faces in,
            # toward the head's and the neck's vertical axis (its normal across, against the way out from the axis,
            # beyond under_inner): the hair beside the jaw and the neck is a thick sheet, and where it hangs off the
            # neck its inner side, seen from the front in the gap under the jaw, was drawn as a smooth sculpted lock
            # with a hard rounded edge over a dark pocket (Anisha, beside the neck), cards lying on its outer side
            # within reach. Without it the view in there ends on the backs of the cards: strands
            out_ = Ct[:, :2] - fr["centre"][None, :2]
            out_ = out_ / np.maximum(np.linalg.norm(out_, axis=1, keepdims=True), 1e-9)
            facing = (Nt[:, :2] * out_).sum(1)
            drop_ = ukeep & (Ct[:, 2] < float(fr["ears"][:, 2].min())) & (facing < -float(st["under_inner"]))
            ukeep &= ~drop_
            log(f"underlayer: {int(drop_.sum())} tris below the ears facing in toward the neck dropped")
    under = dict(V=Vu[inv], keep=ukeep, img=under_image(G, st, fr=fr))
    # the cap: the scalp mask's triangles 1 mm over the skin; per-vertex alpha = the region weight
    body = base["body"]
    capt = base["cap"].copy()
    cimg = cap_image(G, fr, st, base["hair_tex"])
    nape = np.zeros(len(G["body_T"]), bool)
    if st["long"] and cp is not None and len(cp):
        # long hair over the neck, shoulders and back: there is no shell under it (the guide is the clothes, the
        # "cape"), so between its cards the scan's clothes showed, painted with its hair: a flat tan patch in the
        # middle of the back hair (Anisha, from behind). The cap goes on under it: the body below the head where
        # opaque cards lie over it, on the back of the neck and the back only (on the shoulders' tops it showed
        # round the hair's edge), on clothes the scan painted dark (its hair: past the hair's ragged ends the
        # clothes are the clothes), in the cap's own root colour (one solid texel)
        Cb = G["body_V"][G["body_T"]].mean(1)
        e_ = fr["eye"]
        cand = np.nonzero(G["body_cloth"] & ~capt & (Cb[:, 2] < float(fr["ears"][:, 2].min()) - 0.02) &
                          (Cb[:, 2] > e_[2] - 0.62) & (body.FN[:, 1] > 0.2) & ~in_face_window(Cb, fr, 0.0))[0]
        if G.get("body_tex") is not None and len(cand):
            lum = sample_img(np.asarray(G["body_tex"], np.float32), G["body_UV"][cand].mean(1))[:, :3] @ \
                np.array([0.2126, 0.7152, 0.0722])
            cand = cand[lum < 0.25]
        pts_ = Points(cp)
        # (all three corners deep under the hair: a triangle reaching out past its edge stood off the shoulder as
        # a dark spike once the arms came down)
        dvt = pts_.nearest(G["body_V"][G["body_T"][cand].ravel()])[0].reshape(-1, 3).max(1) if len(cand) else []
        for i, dmax in zip(cand, dvt):
            if dmax > 0.007:
                continue
            for j, dd in pts_.near_n(Cb[i], 8):
                if dd <= 0.014 and float((cp[j] - Cb[i]) @ body.FN[i]) > 0.0:
                    nape[i] = True
                    break
        capt |= nape
    Tc = G["body_T"][capt]
    used = np.unique(Tc)
    remap = -np.ones(len(G["body_V"]), np.int64)
    remap[used] = np.arange(len(used))
    calpha = np.clip(base["reg"][used], 0, 1).astype(np.float32)
    UVc = np.array(G["body_UV"][capt], np.float64)
    if nape.any():
        nv = np.unique(G["body_T"][nape])
        dv, _ = Points(cp).nearest(G["body_V"][nv])
        av = (1.0 - smoothstep(0.004, 0.007, dv)).astype(np.float32)
        calpha[remap[nv]] = np.maximum(np.where(np.isin(nv, np.unique(G["body_T"][base["cap"]])), calpha[remap[nv]], 0.0), av)
        # a texel deep inside the hair in the cap's mask (its 9 x 9 neighbourhood all opaque): every corner there
        a = cimg[..., 3]
        m = a.copy()
        for ax in (0, 1):
            m0 = m.copy()
            for s_ in range(-4, 5):
                m = np.minimum(m, np.roll(m0, s_, ax))
        iy, ix = np.unravel_index(int(np.argmax(m)), m.shape)
        UVc[nape[capt]] = ((ix + 0.5) / a.shape[1], (iy + 0.5) / a.shape[0])
        log(f"cap: {int(nape.sum())} tris under the long hair below the head (texel alpha {float(m[iy, ix]):.2f})")
    if st.get("floor_arch") or st.get("floor_rise"):
        # a fringe edge drawn above the scan's painted hairline (Ian's curtain opens the forehead the scan covers):
        # no dark roots below it, where no hair lies (they showed as a hard dark band under the curtain's edge)
        for k, v in enumerate(G["body_V"][used]):
            fz = floor_z(v, fr, st)
            if fz is not None:
                calpha[k] *= float(smoothstep(fz - 0.002, fz + 0.012, v[2]))
    dp = cards.get("dense")
    if st.get("cap_side") and not st["long"] and dp is not None and len(dp):
        # (style cap_side = metres, off by default) beside the face in front of the ears (a sideburn), no dark roots
        # where no dense card lies within cap_side over them: the scan paints a sideburn the cards do not grow over
        # (the region weight keeps hair off the cheek there), and the cap drew it as a flat mottled brown patch under
        # the glasses' arm, dark roots with no strands
        Vu = G["body_V"][used]
        e_, ef_ = fr["eye"], fr["eye_front"]
        ear_y = float(fr["ears"][:, 1].max())
        zone = np.nonzero((np.abs(Vu[:, 0] - e_[0]) > 0.045) & (Vu[:, 1] < ear_y + 0.01) &
                          (Vu[:, 2] > e_[2] - 0.04) & (Vu[:, 2] < e_[2] + 0.05))[0]
        if len(zone):
            dd, _ = Points(dp).nearest(Vu[zone])
            k_ = 1.0 - smoothstep(float(st["cap_side"]), float(st["cap_side"]) + 0.004, dd)
            calpha[zone] *= k_.astype(np.float32)
            log(f"cap: {int((k_ < 0.5).sum())} of {len(zone)} verts beside the face in front of the ears faded out "
                f"(no dense card over them)")
    if st.get("front_free") and not st["long"] and dp is not None and len(dp):
        # a fringe lying on the forehead (short hair): no dark roots on the skin under its ends, only under its
        # dense part. Its last few cm are the atlas' thinning tips (and the wispy strips), and the cap's roots
        # under them showed through as a soft black band with no strands across the brows; a real
        # fringe's ends lie over the skin
        # (in front, up to 3 cm over the brows or 2 cm over the fringe's floor where that is higher: a curtain
        # fringe's opening, Ian's)
        Vu = G["body_V"][used]
        e_, ef_ = fr["eye"], fr["eye_front"]
        top = np.array([max(fr["brow_z"] + 0.03, (floor_z(v, fr, st) or 0.0) + 0.02) for v in Vu])
        zone = np.nonzero((Vu[:, 1] < ef_ + 0.035) & (np.abs(Vu[:, 0] - e_[0]) < 0.07) & (Vu[:, 2] < top))[0]
        if len(zone):
            dd, _ = Points(dp).nearest(Vu[zone])
            k_ = 1.0 - smoothstep(0.006, 0.01, dd)
            calpha[zone] *= k_.astype(np.float32)
            log(f"cap: {int((k_ < 0.5).sum())} of {len(zone)} verts in front of the face faded out (no dense "
                f"fringe over them)")
    Vcap = G["body_V"][used] + body.N[used] * 0.001
    if arms is not None:
        # under the glasses' arms as low as the underlayer, under the cards pressed there (0.6-1.6 mm over the
        # skin): 1 mm over it, the cap was drawn over them, a flat dark patch on the sideburn with no strands
        Vcap, pc = press_under_arms(Vcap, arms, body, under=True)
        if pc.any():
            log(f"cap: {int(pc.sum())} verts pressed under the glasses' arms")
    cap = dict(V=Vcap, T=remap[Tc], UV=UVc,
               alpha=calpha, src=used, img=cimg)
    nt = len(cards["F"]) * 2
    stats = dict(cards=int(cards["n"]), by_layer=cards["by_layer"], card_tris=nt, card_verts=len(cards["V"]),
                 under_tris=int(ukeep.sum()), cap_tris=len(Tc), total_tris=nt + int(ukeep.sum()) + len(Tc))
    log(f"STATS {stats}; {time.time() - t0:.1f} s")
    return dict(cards=cards, under=under, cap=cap, stats=stats, frame=fr)


# ------------------------------------------------------------------ the build (Blender)
def _world_tris(obj):
    """World vertices, loop triangles (vertex ids), their loops and polygons, per-loop UVs of a mesh object."""
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float64)
    me.vertices.foreach_get("co", co)
    M = np.array(obj.matrix_world)
    V = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    T = np.empty(nt * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", T)
    L = np.empty(nt * 3, np.int64)
    me.loop_triangles.foreach_get("loops", L)
    P = np.empty(nt, np.int64)
    me.loop_triangles.foreach_get("polygon_index", P)
    uv = None
    if me.uv_layers.active is not None:
        u = np.empty(len(me.loops) * 2, np.float64)
        me.uv_layers.active.data.foreach_get("uv", u)
        uv = u.reshape(-1, 2)
    return V, T.reshape(-1, 3), L.reshape(-1, 3), P, uv


def _small_image(path, size=1024):
    """An image file as an (size, size, 3) sRGB float array, Blender orientation (row 0 = v 0)."""
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = 'sRGB'
    if img.size[0] != size or img.size[1] != size:
        img.scale(size, size)
    px = np.empty(size * size * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(size, size, 4)[..., :3].copy()


def _face_attr(me, name):
    a = me.attributes.get(name)
    if a is None or a.domain != 'FACE':
        return None
    v = np.empty(len(me.polygons), np.int64)
    a.data.foreach_get("value", v)
    return v


def gather(basemesh, rig, spec, outfit, cid, root):
    """Everything the hair needs from the build, as plain arrays (also saved as hair_guide.npz)."""
    import scan_wrap as sw
    work = os.path.join(root, "tools", "out", f"scan_{cid}")
    me = basemesh.data
    bg = basemesh.vertex_groups["body"].index
    in_body = np.zeros(len(me.vertices), bool)
    for v in me.vertices:
        in_body[v.index] = any(g.group == bg and g.weight > 0.5 for g in v.groups)
    V, T, L, Pi, uv = _world_tris(basemesh)
    keep = in_body[T].all(1)
    hk, ck = _face_attr(me, "scan_head"), _face_attr(me, "scan_cloth")
    if hk is None or ck is None:
        raise RuntimeError("hair_scan_cards: the body has no scan_head / scan_cloth attributes (scan_wrap.apply first)")
    vid = np.nonzero(in_body)[0]
    remap = -np.ones(len(V), np.int64)
    remap[vid] = np.arange(len(vid))
    head = hk[Pi][keep] == 1
    G = dict(body_V=V[vid], body_T=remap[T[keep]], body_UV=uv[L[keep]], body_head=head,
             body_cloth=(ck[Pi][keep] == 1) & ~head, body_vid=vid)
    maps = json.loads(basemesh["scan_head_maps"])
    G["head_tex"] = _small_image(maps["color"])
    body_png = os.path.join(work, f"{cid}_scan_color.png")
    G["body_tex"] = _small_image(body_png) if os.path.exists(body_png) else None
    shell = bpy.data.objects.get(f"{cid}.scanhair")
    if shell is None:
        raise RuntimeError(f"hair_scan_cards: no {cid}.scanhair shell (the outfit needs a scan with hair)")
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    if any(len(f.verts) != 3 for f in bm.faces):
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bm.to_mesh(shell.data)
    bm.free()
    Vs, Ts, Ls, Ps, uvs = _world_tris(shell)
    if not np.array_equal(Ps, np.arange(len(Ps))):
        raise RuntimeError("hair_scan_cards: the shell's polygons are not its triangles")
    G.update(shell_V=Vs, shell_T=Ts, shell_UV=uvs[Ls], shell_tex=_small_image(os.path.join(work, "hair_color.png")))
    A = sw.anchor_points(basemesh, root)
    G["eye_c"] = np.mean([A[i] for i in (33, 133, 362, 263)], 0)
    G["eye_front"] = float(min(A[i][1] for i in (159, 145, 386, 374))) - 0.0015
    G["brow_z"] = float(np.mean([A[i][2] for i in BROWS if i in A]))
    G["ears"] = np.array([A[234], A[454]])
    # the upper lids, corner to corner (a fringe never hangs over the eyes: frame_of / eye_floor)
    if all(i in A for i in LIDS):
        G["eye_lids"] = np.array([A[i] for i in LIDS])
    G["top"] = float(max(V[vid][:, 2].max(), Vs[:, 2].max()))
    names = ("head", "neck_01", "spine_03", "spine_02", "spine_01", "upperarm_l", "upperarm_r", "clavicle_l",
             "clavicle_r")
    G["bones"] = {b: sw.bone_head(rig, b) for b in names if b in rig.pose.bones}
    # glasses: cards and underlayer keep clear of the frames
    cv, ct = [], []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in rig.children:
        if o.type == 'MESH' and "glasses" in o.name.lower():
            ev = o.evaluated_get(dg)
            m = ev.to_mesh()
            m.calc_loop_triangles()
            co = np.empty(len(m.vertices) * 3, np.float64)
            m.vertices.foreach_get("co", co)
            Mw = np.array(o.matrix_world)
            co = co.reshape(-1, 3) @ Mw[:3, :3].T + Mw[:3, 3]
            t = np.empty(len(m.loop_triangles) * 3, np.int64)
            m.loop_triangles.foreach_get("vertices", t)
            ct.append(t.reshape(-1, 3) + sum(len(x) for x in cv))
            cv.append(co)
            ev.to_mesh_clear()
    G["coll_V"] = np.concatenate(cv) if cv else np.zeros((0, 3))
    G["coll_T"] = np.concatenate(ct) if ct else np.zeros((0, 3), np.int64)
    return G


def save_guide(G, path):
    out = {}
    for k, v in G.items():
        if v is None:
            continue
        if k == "bones":
            out["bones_names"] = np.array(list(v.keys()))
            out["bones_pos"] = np.array(list(v.values()))
        elif k.endswith("_tex"):
            out[k] = (np.clip(v, 0, 1) * 255 + 0.5).astype(np.uint8)
        else:
            out[k] = np.asarray(v)
    np.savez_compressed(path, **out)


def load_guide(path):
    d = dict(np.load(path, allow_pickle=False))
    G = {k: v for k, v in d.items() if not k.startswith("bones_")}
    G["bones"] = {str(n): p for n, p in zip(d["bones_names"], d["bones_pos"])}
    for k in list(G):
        if k.endswith("_tex"):
            G[k] = G[k].astype(np.float32) / 255.0
    for k in ("eye_front", "brow_z", "top"):
        G[k] = float(G[k])
    return G


def _png(img, path):
    """(h, w, 4) floats in Blender orientation -> a PNG, loaded back as a Blender image."""
    hair_atlas.save_png(np.flipud(img), path)
    im = bpy.data.images.load(path, check_existing=False)
    im.colorspace_settings.name = 'sRGB'
    im.alpha_mode = 'STRAIGHT'
    return im


def _material(name, img, vcol=True, clip=True, rough=0.45):
    """Principled material the glTF exporter understands: base colour = image x the "Col" colour attribute (so it
    is exported as COLOR_0), alpha = image alpha x Col alpha (rounded: alpha-tested cards; else blended)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    bsdf.inputs["Roughness"].default_value = rough
    if vcol:
        vc = nt.nodes.new('ShaderNodeVertexColor')
        vc.layer_name = "Col"
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs[0].default_value = 1.0
        nt.links.new(tex.outputs[0], mix.inputs[6])
        nt.links.new(vc.outputs[0], mix.inputs[7])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        mul = nt.nodes.new('ShaderNodeMath')
        mul.operation = 'MULTIPLY'
        nt.links.new(tex.outputs[1], mul.inputs[0])
        nt.links.new(vc.outputs[1], mul.inputs[1])
        a = mul.outputs[0]
        if clip:
            rnd = nt.nodes.new('ShaderNodeMath')
            rnd.operation = 'ROUND'
            nt.links.new(a, rnd.inputs[0])
            a = rnd.outputs[0]
        nt.links.new(a, bsdf.inputs["Alpha"])
        for k_, v in (("surface_render_method", 'DITHERED'), ("blend_method", 'HASHED'), ("use_backface_culling", False)):
            try:
                setattr(mat, k_, v)
            except (AttributeError, TypeError):
                pass
    else:
        nt.links.new(tex.outputs[0], bsdf.inputs["Base Color"])
        bsdf.inputs["Specular IOR Level"].default_value = 0.1
    return mat


def _parent(obj, rig):
    mw = obj.matrix_world.copy()
    obj.parent = rig
    obj.matrix_world = mw
    obj.modifiers.new("Armature", 'ARMATURE').object = rig


def height_weights(Z, bones, long_hair):
    """Skinning by height (as scan_wrap.finish_hair): rigid on the head down to the skull base, then into the neck
    and the upper back; long hair below the shoulder blades follows spine_02."""
    zh, zn = float(bones["head"][2]), float(bones["neck_01"][2])
    h = smoothstep(zn + 0.02, zh, Z)
    nk = (1.0 - h) * smoothstep(zn - 0.06, zn + 0.01, Z)
    rest = np.clip(1.0 - h - nk, 0, 1)
    W = {"head": h, "neck_01": nk}
    if long_hair and "spine_02" in bones and "spine_03" in bones:
        z3 = float(bones["spine_03"][2])
        s2 = rest * (1.0 - smoothstep(z3 - 0.12, z3 - 0.02, Z))
        W["spine_03"], W["spine_02"] = rest - s2, s2
    else:
        W["spine_03"] = rest
    return W


def _body_blend(W, V, G, basemesh, rig, near=0.008, far=0.035):
    """Long hair lying on the neck and the back below the skull skinned as the body under it (the nearest body
    vertex's own weights), fading back to the height weights from `near` to `far` off the skin. By height alone,
    the hair over the nape followed the head while the collar under it followed the neck and the shoulders: in the
    game's idle pose the clothes (painted with the scan's hair) came up through the cards as a flat patch in the
    middle of the back hair. The cap under there uses the body's weights too.
    The fade is wide (fading out within 2 cm, the layers a few mm apart over the shoulder blades followed the
    shoulders or the spine by how far off the sweater each row lay, and in the idle pose the sweater came up through
    the middle of a card: its lower end hung below the hair's edge as a detached black drop), and a card's two edges
    take the same weights row by row (V: its vertices in pairs, as Cards lays them out), so a row moves as one."""
    zh = float(G["bones"]["head"][2])
    Vb = np.asarray(G["body_V"], np.float64)
    d, j = Points(Vb).nearest(V)
    f = (1.0 - smoothstep(near, far, d)) * (1.0 - smoothstep(zh - 0.03, zh, V[:, 2]))
    sel = np.nonzero(f > 1e-3)[0]
    if not len(sel):
        return W
    groups = {g.index: g.name for g in basemesh.vertex_groups}
    deform = {b.name for b in rig.data.bones if b.use_deform}
    cache = {}
    W = {k: np.array(v, np.float64) for k, v in W.items()}
    n = len(V)
    for i in sel:
        b = int(G["body_vid"][j[i]])
        if b not in cache:
            ws = {groups[g.group]: g.weight for g in basemesh.data.vertices[b].groups
                  if groups[g.group] in deform and g.weight > 1e-4}
            s = sum(ws.values())
            cache[b] = {k: v / s for k, v in ws.items()} if s > 0 else {}
        wb = cache[b]
        if not wb:
            continue
        for k in W:
            W[k][i] *= 1.0 - f[i]
        for k, v in wb.items():
            if k not in W:
                W[k] = np.zeros(n)
            W[k][i] += f[i] * v
    if n % 2 == 0:
        for k in W:
            m = 0.5 * (W[k][0::2] + W[k][1::2])
            W[k][0::2] = m
            W[k][1::2] = m
    log(f"cards: {len(sel)} vertices on the neck and back skinned as the body under them")
    return W


def _set_groups(obj, W):
    """Vertex groups from per-vertex weights (rounded to 1/1000: one add() call per distinct weight)."""
    for name, w in W.items():
        wr = np.round(np.asarray(w, np.float64), 3)
        vg = obj.vertex_groups.new(name=name)
        for val in np.unique(wr[wr > 0]):
            vg.add(np.nonzero(wr == val)[0].tolist(), float(val), 'REPLACE')


def _smooth(me):
    if hasattr(me, "shade_smooth"):
        me.shade_smooth()
    else:
        for p in me.polygons:
            p.use_smooth = True


def make(basemesh, rig, spec, outfit, cid, root):
    """Build the cards, the underlayer (the shell, edited in place) and the cap for a scanned outfit."""
    t0 = time.time()
    st = style_for(spec, outfit)
    work = os.path.join(root, "tools", "out", f"scan_{cid}")
    G = gather(basemesh, rig, spec, outfit, cid, root)
    save_guide(G, os.path.join(work, "hair_guide.npz"))
    with open(os.path.join(work, "hair_style.json"), "w") as f:
        json.dump(st, f, indent=1)
    R = generate(G, st, seed=int(spec.get("hair_seed", 1)))
    scene = bpy.context.scene
    # -- the cards
    C = R["cards"]
    atlas = hair_atlas.tinted(st["atlas"], st["root"], st["tip"])
    atlas_img = _png(np.flipud(atlas), os.path.join(work, f"{cid}_hair_atlas.png"))
    me = bpy.data.meshes.new(f"{cid}.scancards")
    me.from_pydata(C["V"].tolist(), [], C["F"].tolist())
    me.update()
    loops = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", loops)
    uvl = me.uv_layers.new(name="UVMap")
    uvl.data.foreach_set("uv", C["UV"][loops].astype(np.float32).ravel())
    sh = C.get("SHADOW")
    if sh is not None and len(sh) == len(C["V"]) and (sh[:, 0] > 0).any():
        # UV2 (glTF TEXCOORD_1): shadow_cut's (in front of the face, height over the brows + 0.5); Blender's v is
        # flipped on export
        uv2 = me.uv_layers.new(name="ShadowCut")
        uv2.data.foreach_set("uv", np.stack([sh[:, 0], 1.0 - sh[:, 1]], 1)[loops].astype(np.float32).ravel())
        me.uv_layers.active = uvl
        uvl.active_render = True
    col = me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
    col.data.foreach_set("color", C["COL"].astype(np.float32).ravel())
    me.color_attributes.active_color = col
    me.color_attributes.render_color_index = me.color_attributes.find("Col")
    _smooth(me)
    me.normals_split_custom_set_from_vertices(unit(C["NRM"]).tolist())
    cards = bpy.data.objects.new(f"{cid}.scancards", me)
    scene.collection.objects.link(cards)
    me.materials.append(_material(f"{cid}_hair_scancards", atlas_img, clip=True))
    ef_ = C.get("EARF")
    if ef_ is not None and len(ef_) == len(me.polygons) and ef_.any():
        # (style ear_stencil: the faces over the ears, a second surface; see generate())
        me.materials.append(_material(f"{cid}_hair_scancards_ear", atlas_img, clip=True))
        me.polygons.foreach_set("material_index", ef_.astype(np.int32))
        me.update()
    cards["baked_color"] = True
    cards["keep_material"] = True
    W = height_weights(C["V"][:, 2], G["bones"], st["long"])
    if st["long"]:
        W = _body_blend(W, C["V"], G, basemesh, rig)
    _set_groups(cards, W)
    _parent(cards, rig)
    # -- the underlayer: the scan shell itself, smoothed and 1.5 mm in, its own baked colour, face window cut
    shell = bpy.data.objects[f"{cid}.scanhair"]
    U = R["under"]
    smw = np.linalg.inv(np.array(shell.matrix_world))
    loc = U["V"] @ smw[:3, :3].T + smw[:3, 3]
    shell.data.vertices.foreach_set("co", loc.astype(np.float32).ravel())
    shell.data.update()
    if not U["keep"].all():
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(shell.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(~U["keep"])[0]], context='FACES')
        bm.to_mesh(shell.data)
        bm.free()
    under_img = _png(U["img"], os.path.join(work, f"{cid}_hair_under.png"))
    shell.data.materials.clear()
    shell.data.materials.append(_material(f"{cid}_hairunder_scan", under_img, vcol=False, rough=0.95))
    shell.name = f"{cid}.hairunder"
    shell.data.name = f"{cid}.hairunder"
    shell["kind"] = "hairunder"
    # -- the cap
    K = R["cap"]
    cme = bpy.data.meshes.new(f"{cid}.haircap")
    cme.from_pydata(K["V"].tolist(), [], K["T"].tolist())
    cme.update()
    cl = np.empty(len(cme.loops), np.int64)
    cme.loops.foreach_get("vertex_index", cl)
    # per loop UVs: the head's, corner by corner (from_pydata keeps the triangles' corner order)
    cme.uv_layers.new(name="UVMap").data.foreach_set("uv", K["UV"].reshape(-1, 2).astype(np.float32).ravel())
    ccol = cme.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
    rgba = np.ones((len(K["V"]), 4), np.float32)
    rgba[:, 3] = K["alpha"]
    ccol.data.foreach_set("color", rgba.ravel())
    cme.color_attributes.active_color = ccol
    cme.color_attributes.render_color_index = cme.color_attributes.find("Col")
    _smooth(cme)
    src = cme.attributes.new("body_vid", 'INT', 'POINT')
    src.data.foreach_set("value", G["body_vid"][K["src"]].astype(np.int32))
    cap = bpy.data.objects.new(f"{cid}.haircap", cme)
    scene.collection.objects.link(cap)
    cme.materials.append(_material(f"{cid}_haircap_scan", _png(K["img"], os.path.join(work, f"{cid}_hair_cap.png")),
                                   clip=False, rough=0.9))
    cap["kind"] = "haircap"
    cap["baked_color"] = True
    # the skin's own weights, vertex by vertex
    body_ids = G["body_vid"][K["src"]]
    groups = {g.index: g.name for g in basemesh.vertex_groups}
    acc = {}
    for i, b in enumerate(body_ids.tolist()):
        for g in basemesh.data.vertices[b].groups:
            name = groups[g.group]
            if name in rig.data.bones and rig.data.bones[name].use_deform and g.weight > 1e-4:
                acc.setdefault(name, []).append((i, g.weight))
    for name, items in acc.items():
        vg = cap.vertex_groups.new(name=name)
        for i, w in items:
            vg.add([i], w, 'REPLACE')
    _parent(cap, rig)
    log(f"{cid}: {R['stats']}, built in {time.time() - t0:.1f} s")
    return dict(cards=cards, under=shell, cap=cap, stats=R["stats"])


def cap_shapes(basemesh, objs):
    """After the face shapes are loaded and scaled: copy each one onto the cap (its vertices are the skin's, 1 mm
    out), so raised brows never push the forehead through the hairline."""
    cap = objs.get("cap") if isinstance(objs, dict) else None
    keys = basemesh.data.shape_keys
    if cap is None or keys is None:
        return
    a = cap.data.attributes.get("body_vid")
    if a is None:
        return
    ids = np.empty(len(cap.data.vertices), np.int64)
    a.data.foreach_get("value", ids)
    n = len(basemesh.data.vertices)
    B = np.empty(n * 3, np.float64)
    keys.reference_key.data.foreach_get("co", B)
    B = B.reshape(-1, 3)[ids]
    # body local -> cap local (both usually identity under the rig)
    M = np.linalg.inv(np.array(cap.matrix_world)) @ np.array(basemesh.matrix_world)
    base = np.empty(len(ids) * 3, np.float64)
    cap.data.vertices.foreach_get("co", base)
    base = base.reshape(-1, 3)
    K = np.empty(n * 3, np.float64)
    made = 0
    for kb in keys.key_blocks:
        if kb == keys.reference_key:
            continue
        kb.data.foreach_get("co", K)
        d = K.reshape(-1, 3)[ids] - B
        if np.abs(d).max() < 1e-5:
            continue
        if cap.data.shape_keys is None:
            cap.shape_key_add(name="Basis", from_mix=False)
        sk = cap.shape_key_add(name=kb.name, from_mix=False)
        sk.data.foreach_set("co", (base + d @ M[:3, :3].T).astype(np.float32).ravel())
        made += 1
    cap.data.attributes.remove(cap.data.attributes["body_vid"])
    log(f"cap: {made} face shapes copied from the skin")
