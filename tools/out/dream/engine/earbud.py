"""The round-2 earbud (autotest.gd _dream_earbud2) and the Amphi 4 aisle steps, in Python, for the tumble
simulation of the engine dream clip A (tumble.py).

Everything is in game space (metres, Y up). The earbud's "pod" frame is the Node3D the autotest moves: at rest its
origin is on the floor under the earbud's vertex centre and its basis is a yaw (rotation about +Y); the mesh lies in
it through the piece transform `lie` (the builder's roll about the stem, then tipped until its centre is lowest).
"""
import math
import warnings
import numpy as np

# numpy 2.2 on Accelerate flags spurious divide/overflow warnings in small matmuls; the results are finite
warnings.filterwarnings("ignore", message=".*encountered in matmul")


def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def rot(axis, ang):
    """Godot's Basis(axis, angle): the right-handed rotation about a unit axis."""
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    x, y, z = a
    c, s = math.cos(ang), math.sin(ang)
    C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def lathe(k=1.3):
    """The lathe mesh exactly as _dream_earbud2 builds it: vertices (scaled by k) and triangles."""
    stem_r, tip_r, head_c, head_r, egg = 0.003, 0.0012, 0.031, 0.0088, 1.12
    pivot, bend, fillet = 0.0215, math.radians(32.0), 0.0055
    rings, segs = 80, 40
    total = head_c + head_r * egg
    verts = []
    for i in range(rings + 1):
        u = total * i / rings
        rs = 0.0
        if u < tip_r:
            rs = stem_r - tip_r + math.sqrt(max(tip_r * tip_r - (tip_r - u) * (tip_r - u), 0.0))
        elif u <= head_c:
            rs = stem_r * (1.0 + 0.08 * (u / head_c))
        e = (u - head_c) / egg
        rh = math.sqrt(max(head_r * head_r - e * e, 0.0))
        r = rh
        if u <= head_c:
            h = max(fillet - abs(rs - rh), 0.0) / fillet
            r = max(rs, rh) + h * h * fillet * 0.25
        if i == 0 or i == rings:
            r = 0.0
        a = bend * smoothstep(pivot - 0.004, pivot + 0.006, u)
        for j in range(segs):
            phi = 2 * math.pi * j / segs
            p = (u - pivot, r * math.cos(phi), r * math.sin(phi))
            p = (p[0] * math.cos(a) - p[1] * math.sin(a) + pivot, p[0] * math.sin(a) + p[1] * math.cos(a), p[2])
            verts.append((p[0] * k, p[1] * k, p[2] * k))
    tris = []
    for i in range(rings):
        for j in range(segs):
            a0 = i * segs + j
            a1 = i * segs + (j + 1) % segs
            b0, b1 = a0 + segs, a1 + segs
            tris.append((a0, b0, a1))
            tris.append((a1, b0, b1))
    return np.array(verts), np.array(tris), rings, segs


def lie_transform(verts, roll):
    """The piece transform (basis, origin) of _dream_earbud2 for this roll."""
    lie = rot((1, 0, 0), roll)
    centre = verts.mean(axis=0)
    best, best_b = math.inf, lie
    for t in range(-50, 51):
        b = rot((0, 0, 1), math.radians(t * 0.5)) @ lie
        pts = verts @ b.T
        hgt = (b @ centre)[1] - pts[:, 1].min()
        if hgt < best:
            best, best_b = hgt, b
    lo2 = (verts @ best_b.T)[:, 1].min()
    c = best_b @ centre
    return best_b, np.array([-c[0], -lo2, -c[2]])


def mass_props(verts, tris):
    """Volume, centre of mass and inertia tensor (about the centre, unit density) of a closed triangle mesh."""
    A = verts[tris[:, 0]]
    B = verts[tris[:, 1]]
    C = verts[tris[:, 2]]
    det = np.einsum("ij,ij->i", A, np.cross(B, C))
    vol = det.sum() / 6.0
    sign = 1.0 if vol > 0 else -1.0
    det *= sign
    vol *= sign
    com = (det[:, None] * (A + B + C)).sum(axis=0) / 24.0 / vol
    can = np.array([[2, 1, 1], [1, 2, 1], [1, 1, 2]]) / 120.0
    cov = np.zeros((3, 3))
    for a, b, c, d in zip(A, B, C, det):
        M = np.stack([a, b, c], axis=1)
        cov += d * M @ can @ M.T
    cov -= vol * np.outer(com, com)
    inertia = np.trace(cov) * np.eye(3) - cov
    return vol, com, inertia


# ---- the Amphi 4 aisle (tools/blender/campus_south.py amphi_interior, campus_layout.tier_z) ----
AMPHI_TOP_Z, TIER_D, TIER_H = 16.4, 0.95, 0.3
AISLE_X = (17.9, 19.65)


def aisle_sections(tiers=5):
    """The aisle floor's profile along z as (z_lo, z_hi, height) sections from the landing down, nosings included
    (the yellow strip on each half step's edge 2 mm proud, the oak nosing on each tier's edge 4 mm proud)."""
    s = [(AMPHI_TOP_Z, 99.0, 0.0)]
    for k in range(1, tiers + 1):
        z1 = AMPHI_TOP_Z - TIER_D * (k - 1)
        z0 = z1 - TIER_D
        top = -TIER_H * k
        zm = (z0 + z1) / 2
        s.append((zm + 0.04, z1, top + 0.15))
        s.append((zm, zm + 0.04, top + 0.152))
        s.append((z0 + 0.04, zm, top))
        s.append((z0, z0 + 0.04, top + 0.004))
    s.append((-99.0, s[-1][0], s[-1][2] - 0.3))
    return s


SECTIONS = aisle_sections()
Z_LO = np.array([s[0] for s in SECTIONS])
Z_HI = np.array([s[1] for s in SECTIONS])
H = np.array([s[2] for s in SECTIONS])


def floor_height(z):
    """The aisle floor's height at each z."""
    return H[section_index(np.atleast_1d(z))]


def section_index(z):
    """Index into SECTIONS of each z (vectorised)."""
    z = np.asarray(z, float)
    # Z_LO decreasing: find the first i with Z_LO[i] < z
    idx = np.argmax(Z_LO[None, :] < z[:, None], axis=1)
    return idx


def penetration(P):
    """Contacts of world points P (N,3) with the aisle's steps and its side panels: (mask, depth, normal)."""
    n = len(P)
    idx = section_index(P[:, 2])
    h = H[idx]
    depth = np.full(n, -1.0)
    normal = np.zeros((n, 3))
    inside = P[:, 1] < h
    # up through the tread
    d_up = h - P[:, 1]
    # out through the face in front (toward -z) when the section in front is lower than the point
    nxt = np.minimum(idx + 1, len(SECTIONS) - 1)
    d_front = np.where(H[nxt] <= P[:, 1], P[:, 2] - Z_LO[idx], np.inf)
    # out through the face behind (toward +z) when the section behind is lower (the nosing strips)
    prv = np.maximum(idx - 1, 0)
    d_back = np.where((H[prv] <= P[:, 1]) & (idx > 0), Z_HI[idx] - P[:, 2], np.inf)
    best = np.minimum(d_up, np.minimum(d_front, d_back))
    depth = np.where(inside, best, -1.0)
    normal[:, 1] = np.where(d_up <= np.minimum(d_front, d_back), 1.0, 0.0)
    normal[:, 2] = np.where((normal[:, 1] == 0) & (d_front <= d_back), -1.0, 0.0)
    normal[:, 2] = np.where((normal[:, 1] == 0) & (d_back < d_front), 1.0, normal[:, 2])
    # the aisle's side panels (end panels of the rows at x 17.9 and 19.65)
    for dw, sgn in ((AISLE_X[0] - P[:, 0], 1.0), (P[:, 0] - AISLE_X[1], -1.0)):
        sel = (dw > 0.0) & (dw > depth)
        depth = np.where(sel, dw, depth)
        normal[sel] = (sgn, 0.0, 0.0)
    return depth > 0.0, depth, normal


class Earbud:
    def __init__(self, k=1.3, roll=-0.6, density=1100.0, ring_step=4, seg_step=4):
        v, t, rings, segs = lathe(k)
        self.lie_b, self.lie_o = lie_transform(v, roll)
        pod = v @ self.lie_b.T + self.lie_o        # mesh vertices in the pod frame
        vol, com, inertia = mass_props(pod, t)
        self.mass = vol * density
        self.com = com                              # centre of mass in the pod frame
        self.inertia = inertia * density            # about the centre of mass, pod axes
        self.inv_inertia = np.linalg.inv(self.inertia)
        sel = [i * segs + j for i in range(0, rings + 1, ring_step) for j in range(0, segs, seg_step)]
        sel += [rings * segs]
        self.points = pod[sorted(set(sel))] - com   # contact points about the centre of mass
        self.verts = pod
        self.tris = t
        self.pod_verts = pod
