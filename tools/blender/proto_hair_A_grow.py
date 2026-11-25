"""Prototype A: hair cards grown from the scalp and shaped by the person's scan (python3.11: numpy + scipy).

usage: python3.11 tools/blender/proto_hair_A_grow.py toma_fit1 anisha [seed=N]
reads  assets/characters/<stem>.glb (the current build: wrapped body + the scan hair shell)
writes tools/out/proto_A/<stem>_cards.npz (cards: V F UV C N TG; scalp cap: cap_V/F/C; inner occluder: occ_V/F/C;
       the old shell-darkening offsets) and a debug splat image. Runs in ~3 s per character.

How the scan shapes the cards (all measured on the shipped glb, nothing else is needed):
- where hair grows: scalp under the shell, plus scalp the head bake painted hair-coloured (the shell misses hair
  lying within 4 mm of the skull); the face is cut out below the brows, the sideburns at mid-ear;
- volume and silhouette: each card has a layer 0..1 and is kept at that fraction of the way between the skull
  and the shell (outer cards hug the shell's surface, inner ones fill the volume); cards end where the shell ends;
- flow: the style's field (part, crown, gravity) blended with the strand direction read from the shell's baked
  colour texture (structure tensor of the scan's painted strands, mapped to 3D through the shell's UVs);
- colour: the shell texture under each card, normalised, times the cast's hair colour;
- long hair below the shell (the hair "cape" baked on the back of the body) carries on down the back as long as
  the body texture under it is still hair-coloured (clothes count only for long hair: a dark hoodie is not hair);
- the guide is the shell after Taubin smoothing (its sculpted lumps read as clay when cards hug them);
- long hair: a face window keeps strands beside the face, shoulders drape them to the front or the back, the centre
  part is a thin skin-coloured line in the scalp cap;
- under the cards: a scalp cap (root colour, alpha ramp at the hairline) and, for voluminous hair, an occluder (the
  shell pulled half-way to the skull, cut to the scalp interior), instead of the solid shell.
"""
import os, sys, math, time, json
import numpy as np
from scipy.spatial import cKDTree
from scipy.ndimage import gaussian_filter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import proto_hair_A_glb as G

OUT = os.path.join(ROOT, "tools", "out", "proto_A")


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def hx(h):
    h = h.lstrip("#")
    return srgb_to_lin(np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]))


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


# per character: style of flow and card look; colours from cast.py hair_colors (linear)
PRESETS = {
    "toma_fit1": dict(style="curly", atlas="curly", colors=("#0e0907", "#2a1c14"), cards=1700, max_len=0.17,
                      seg_len=0.008, width=(0.02, 0.03), taper=0.4, layer=(0.3, 1.0), emerge=0.03,
                      lift=0.9, tex_flow=0.55, curl=(0.004, 0.07), clump=0.12, twist=8, fly=0.035, jitter=0.05,
                      tex_len=0.13, front_floor=0.035, side_floor=-0.03, nape=-0.07, min_thick=0.006, neck_stop=-0.11,
                      smooth=4, cap_lift=0.0015, occluder=0.5, edge_lift=0.1, edge_len=0.15, front_stop=0.03,
                      edge_frac=0.22),       # band_thr=0.5 tried: it turned the painted hairline into a wider grey haze
    "anisha": dict(style="long_part", atlas="straight", colors=("#0b0908", "#1e1612"), cards=1900, max_len=0.6,
                   seg_len=0.016, width=(0.016, 0.026), taper=0.35, layer=(0.25, 1.0), emerge=0.02,
                   lift=0.15, tex_flow=0.1, curl=None, clump=0.3, twist=6, fly=0.03, jitter=0.015,
                   tex_len=0.5, front_floor=0.04, side_floor=-0.06, nape=-0.06, min_thick=0.005, cape=True,
                   smooth=25, face_window=True, part=True, cap_lift=0.0012, edge_lift=0.0),
}


# ------------------------------------------------------------------ surfaces
class Surface:
    """Dense random samples of a triangle mesh, for nearest-point / signed-distance queries."""

    def __init__(self, P, N, T, spacing, rng, UV=None):
        a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
        area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
        n = rng.poisson(area / spacing ** 2) + 1
        tri = np.repeat(np.arange(len(T)), n)
        r1, r2 = rng.random(len(tri)), rng.random(len(tri))
        f = r1 + r2 > 1
        r1[f], r2[f] = 1 - r1[f], 1 - r2[f]
        w = np.stack([1 - r1 - r2, r1, r2], 1)
        self.X = (P[T[tri]] * w[..., None]).sum(1)
        self.N = unit((N[T[tri]] * w[..., None]).sum(1))
        self.tri, self.w = tri, w
        self.uv = (UV[T[tri]] * w[..., None]).sum(1) if UV is not None else None
        self.kd = cKDTree(self.X)

    def query(self, Q):
        d, i = self.kd.query(Q)
        return i, d


def boundary_points(P, T, step=0.0015):
    inv, X = weld(P)               # UV seams are not boundaries
    P, T = X, inv[T]
    E = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), 1)
    u, cnt = np.unique(E, axis=0, return_counts=True)
    B = u[cnt == 1]
    pts = []
    for a, b in B:
        L = np.linalg.norm(P[b] - P[a])
        k = max(1, int(L / step))
        t = np.linspace(0, 1, k + 1)[:, None]
        pts.append(P[a] * (1 - t) + P[b] * t)
    return np.concatenate(pts) if pts else np.zeros((0, 3))


def weld(P):
    """Merge glTF seam duplicates: welded index per vertex and the unique positions."""
    key = np.round(P / 1e-6).astype(np.int64)
    u, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return inv.ravel(), P[first]


def taubin(P, T, iters, lam=0.5, mu=-0.53):
    """Volume-preserving smoothing of a triangle mesh (glTF seams welded first, open boundary kept fixed).
    Returns the smoothed positions and area-weighted vertex normals, in the original (unwelded) indexing."""
    import scipy.sparse as sp
    inv, X = weld(P)
    TW = inv[T]
    E = np.sort(np.concatenate([TW[:, [0, 1]], TW[:, [1, 2]], TW[:, [2, 0]]]), 1)
    Eu, cnt = np.unique(E, axis=0, return_counts=True)
    n = len(X)
    A = sp.coo_matrix((np.ones(2 * len(Eu)), (np.r_[Eu[:, 0], Eu[:, 1]], np.r_[Eu[:, 1], Eu[:, 0]])), (n, n)).tocsr()
    deg = np.asarray(A.sum(1)).ravel()
    W = sp.diags(1.0 / np.maximum(deg, 1)) @ A
    fixed = np.zeros(n, bool)
    fixed[Eu[cnt == 1].ravel()] = True
    X = X.copy()
    for _ in range(iters):
        for f in (lam, mu):
            L = W @ X - X
            L[fixed] = 0
            X = X + f * L
    fn = np.cross(X[TW[:, 1]] - X[TW[:, 0]], X[TW[:, 2]] - X[TW[:, 0]])
    VN = np.zeros_like(X)
    for k in range(3):
        np.add.at(VN, TW[:, k], fn)
    return X[inv], unit(VN)[inv]


def texture_flow(img_srgb, uv, tri, w, P, T, UV, sigma=7.0):
    """Strand direction (3D, sign-free) and coherence at shell samples, from the structure tensor of the baked
    colour texture (the scan's painted strands), mapped through each triangle's UV -> 3D Jacobian."""
    import cv2
    L = (img_srgb @ np.array([0.2126, 0.7152, 0.0722])).astype(np.float32)
    valid = (L > 0.012).astype(np.float32)
    valid = cv2.erode(valid, np.ones((5, 5), np.uint8))
    Lb = cv2.GaussianBlur(L, (0, 0), 1.2)
    gx = cv2.Sobel(Lb, cv2.CV_32F, 1, 0, ksize=3) * valid
    gy = cv2.Sobel(Lb, cv2.CV_32F, 0, 1, ksize=3) * valid
    norm = gaussian_filter(valid, sigma) + 1e-6
    Jxx = gaussian_filter(gx * gx, sigma) / norm
    Jxy = gaussian_filter(gx * gy, sigma) / norm
    Jyy = gaussian_filter(gy * gy, sigma) / norm
    theta = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy) + np.pi / 2          # along the streaks, not across
    tr = Jxx + Jyy
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / np.maximum(tr, 1e-9)
    coh = coh * (norm > 0.5)
    H, Wd = L.shape
    x = np.clip((uv[:, 0] % 1) * Wd, 0, Wd - 1).astype(int)
    y = np.clip((uv[:, 1] % 1) * H, 0, H - 1).astype(int)
    th, c = theta[y, x], coh[y, x]
    d2 = np.stack([np.cos(th), np.sin(th)], 1)          # (du, dv) in glTF UV (v down = image rows)
    # per-triangle Jacobian dP/d(uv)
    e1 = P[T[:, 1]] - P[T[:, 0]]
    e2 = P[T[:, 2]] - P[T[:, 0]]
    q1 = UV[T[:, 1]] - UV[T[:, 0]]
    q2 = UV[T[:, 2]] - UV[T[:, 0]]
    det = q1[:, 0] * q2[:, 1] - q1[:, 1] * q2[:, 0]
    ok = np.abs(det) > 1e-12
    det = np.where(ok, det, 1.0)
    dPdu = (e1 * q2[:, 1:2] - e2 * q1[:, 1:2]) / det[:, None]
    dPdv = (e2 * q1[:, 0:1] - e1 * q2[:, 0:1]) / det[:, None]
    F = unit(dPdu[tri] * d2[:, :1] + dPdv[tri] * d2[:, 1:2])
    c = np.where(ok[tri], c, 0.0)
    return F, c


# ------------------------------------------------------------------ the character
def load(stem, rng):
    g = G.GLB(os.path.join(ROOT, "assets", "characters", stem + ".glb"))
    J, jn = g.joints()
    body = g.mesh("_body")
    shell = g.mesh("hairshell")
    eye = g.mesh("_eye_")
    mats = [m["name"] for m in g.J["materials"]]
    head_mat = next(i for i, m in enumerate(mats) if m.endswith("skin_head"))
    cloth_mat = next((i for i, m in enumerate(mats) if "cloth_scan" in m), -1)

    def tex_of(mi):
        ti = g.J["materials"][mi]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
        return G.decode_png(g.image_bytes(g.texture_image(ti)))

    shell_mat = shell["mat"][0]
    # every material that carries the scan bake: the head, the body skin (the nape's painted hair) and the clothes
    # (Anisha's long hair below the shoulders is baked onto her jumper: the "cape")
    texs = {}
    for i, m in enumerate(mats):
        if ("_skin_" in m or "cloth_scan" in m) and "baseColorTexture" in g.J["materials"][i].get("pbrMetallicRoughness", {}):
            texs[i] = tex_of(i)
    D = dict(g=g, J=J, jn=jn, body=body, shell=shell, eye=eye, head_tex=tex_of(head_mat),
             shell_tex=tex_of(shell_mat), cloth_tex=tex_of(cloth_mat) if cloth_mat >= 0 else None,
             head_mat=head_mat, cloth_mat=cloth_mat, texs=texs)
    return D


def surface_colors(D, mats_of, uv):
    """sRGB colour of the scan bake at surface points (white where a material has no bake)."""
    out = np.ones((len(uv), 3))
    for mi, img in D["texs"].items():
        m = mats_of == mi
        if m.any():
            out[m] = G.sample(img, uv[m])
    return out


def vertex_colors(mesh, tri_mask, img):
    """sRGB colour of each vertex used by the masked triangles (NaN elsewhere)."""
    out = np.full((len(mesh["P"]), 3), np.nan)
    vs = np.unique(mesh["T"][tri_mask])
    out[vs] = G.sample(img, mesh["UV"][vs])
    return out


def grow(stem, seed=7):
    t0 = time.time()
    cfg = PRESETS[stem]
    rng = np.random.default_rng(seed)
    D = load(stem, rng)
    body, shell, J = D["body"], D["shell"], D["J"]
    head = J["head"]
    up, fwd, side = np.array([0, 0, 1.0]), np.array([0, -1.0, 0]), np.array([1.0, 0, 0])
    z_eye = float(D["eye"]["P"][:, 2].mean())
    top = float(body["P"][:, 2].max())
    centre = np.array([0.0, head[1] + 0.005, (z_eye + top) / 2 - 0.01])    # middle of the skull
    hw = D["g"].joint_weight(body, ["head"], D["jn"])
    nw = D["g"].joint_weight(body, ["neck_01"], D["jn"])

    # surfaces: the whole body (collisions, the cape), the skull, the shell
    up_body = body["T"][(body["P"][body["T"]][:, :, 2].min(1) > head[2] - 0.75)]
    S_body = Surface(body["P"], body["N"], up_body, 0.003, rng, body["UV"])
    S_body.mat = body["mat"][np.nonzero(body["P"][body["T"]][:, :, 2].min(1) > head[2] - 0.75)[0]][S_body.tri]
    head_tris = body["T"][(hw[body["T"]].min(1) > 0.5) | (body["mat"] == D["head_mat"])]
    S_skull = Surface(body["P"], body["N"], head_tris, 0.002, rng)
    # the guide: the scan shell, smoothed (its sculpted lumps read as clay when cards hug them; long straight hair
    # wants a sleek envelope, curls keep more of the scan's volume)
    if cfg.get("smooth"):
        shP, shN = taubin(shell["P"], shell["T"], cfg["smooth"])
    else:
        shP, shN = shell["P"], shell["N"]
    S_sh = Surface(shP, shN, shell["T"], 0.002, rng, shell["UV"])
    Bp = boundary_points(shP, shell["T"])
    kdB = cKDTree(Bp)
    edge_d = kdB.query(S_sh.X)[0]
    # shell thickness: from each shell sample down to the body
    thick = S_body.query(S_sh.X)[1]
    # shell colour (linear luminance, normalised) and the scan's strand flow
    sh_rgb = G.sample(D["shell_tex"], S_sh.uv)
    sh_lum = srgb_to_lin(sh_rgb) @ np.array([0.2126, 0.7152, 0.0722])
    med = np.median(sh_lum[sh_lum > 1e-4])
    sh_rel = np.clip(sh_lum / med, 0.55, 1.8)
    TF, TC = texture_flow(D["shell_tex"], S_sh.uv, S_sh.tri, S_sh.w, shP, shell["T"], shell["UV"])
    shell_lum_srgb = float(np.median((D["shell_tex"] @ np.array([0.2126, 0.7152, 0.0722]))[
        (D["shell_tex"] @ np.array([0.2126, 0.7152, 0.0722])) > 0.012]))
    hair_thr = max(0.16, shell_lum_srgb * 2.6)
    print(f"[A] {stem}: shell lum {shell_lum_srgb:.3f}, hair threshold {hair_thr:.3f}, z_eye {z_eye:.3f}")

    # ---------------------------------------------------------- where hair grows on the scalp
    P, Nb = body["P"], body["N"]
    cand = ((hw + nw) > 0.3) & (P[:, 2] > head[2] - 0.08)
    vmat = np.full(len(P), -1)
    vmat[body["T"].ravel()] = np.repeat(body["mat"], 3)
    skin_m = np.array([("_skin_" in m["name"]) for m in D["g"].J["materials"]])
    col = surface_colors(D, np.where((vmat >= 0) & skin_m[np.maximum(vmat, 0)], vmat, -1), body["UV"])
    lum = col @ np.array([0.2126, 0.7152, 0.0722])
    hairy = lum < hair_thr
    i_sh, d_sh = S_sh.query(P)
    dv = S_sh.X[i_sh] - P
    along = (dv * Nb).sum(1)
    covered = (d_sh < 0.1) & (along > 0.55 * d_sh) | (d_sh < 0.008)
    rel = P - centre
    az = np.arctan2(rel @ side, rel @ fwd)               # 0 = front, +-pi = back
    a = np.abs(az)
    # front / sides / nape, blended across the back of the ear so no strands start on the sides of the neck
    floor = np.where(a < 0.9, z_eye + cfg["front_floor"],
                     z_eye + cfg["side_floor"] + (head[2] + cfg["nape"] - z_eye - cfg["side_floor"])
                     * smoothstep(1.9, 2.6, a))
    floor = np.where((a >= 0.9) & (a < 1.3), np.maximum(floor, z_eye + 0.0), floor)   # temples: above the eye
    # the bake's hairline is a soft gradient (grey band on the forehead): with band_thr the front hairline takes it in,
    # so short flat edge cards grow over it instead of leaving it bare
    if cfg.get("band_thr"):
        hairy |= (lum < cfg["band_thr"]) & (a < 1.3)
    scalp = cand & (hairy | covered) & (P[:, 2] > floor)
    # the shell's thickness over each scalp vertex (hair lying on the skull: a minimum)
    T_v = np.where(covered, np.maximum(along, cfg["min_thick"]), cfg["min_thick"])
    print(f"[A] scalp verts: {int(scalp.sum())} (shell-covered {int((scalp & covered).sum())}, painted only "
          f"{int((scalp & ~covered).sum())})")

    # distance (along the mesh) to the edge of the hair region, for a soft hairline
    Tb = body["T"]
    E = np.unique(np.sort(np.concatenate([Tb[:, [0, 1]], Tb[:, [1, 2]], Tb[:, [2, 0]]]), 1), axis=0)
    # merge coincident vertices (UV seams) so the region is connected across seams
    kdv = cKDTree(P)
    pairs = kdv.query_pairs(1e-6, output_type='ndarray')
    E = np.concatenate([E, pairs])
    elen = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1)
    dist = np.where(scalp, np.inf, 0.0)
    for _ in range(40):
        nd = np.minimum(dist[E[:, 0]], dist[E[:, 1]] + elen)
        nd2 = np.minimum(dist[E[:, 1]], dist[E[:, 0]] + elen)
        new = dist.copy()
        np.minimum.at(new, E[:, 0], nd)
        np.minimum.at(new, E[:, 1], nd2)
        if np.allclose(new, dist):
            break
        dist = new
    dist = np.minimum(dist, 0.1)

    # ---------------------------------------------------------- roots
    tri_ok = scalp[Tb].sum(1) >= 2
    tri_ok &= (body["mat"] == D["head_mat"]) | ((hw + nw)[Tb].min(1) > 0.3)
    TT = Tb[tri_ok]
    A_ = 0.5 * np.linalg.norm(np.cross(P[TT[:, 1]] - P[TT[:, 0]], P[TT[:, 2]] - P[TT[:, 0]]), axis=1)
    n_try = cfg["cards"] * 3
    k = rng.choice(len(TT), n_try, p=A_ / A_.sum())
    r1, r2 = rng.random(n_try), rng.random(n_try)
    f = r1 + r2 > 1
    r1[f], r2[f] = 1 - r1[f], 1 - r2[f]
    bw = np.stack([1 - r1 - r2, r1, r2], 1)
    R = (P[TT[k]] * bw[..., None]).sum(1)
    RN = unit((Nb[TT[k]] * bw[..., None]).sum(1))
    Rd = (dist[TT[k]] * bw).sum(1)
    RT = (T_v[TT[k]] * bw).sum(1)
    keep = rng.random(n_try) < smoothstep(-0.004, 0.008, Rd)
    if cfg.get("part"):
        # a centre part: no roots on the line itself (top of the head, in front of the crown)
        on_top = (RN[:, 2] > 0.35) & (R[:, 1] < centre[1] + 0.04)
        keep &= ~(on_top & (np.abs(R[:, 0]) < 0.003))
    edge_root = keep & (Rd < 0.012)
    n_edge = int(cfg["cards"] * cfg.get("edge_frac", 0.12))
    ei = np.nonzero(edge_root)[0][-n_edge:]
    mi = np.nonzero(keep)[0][:cfg["cards"]]
    sel = np.concatenate([mi, ei])
    is_edge = np.concatenate([np.zeros(len(mi), bool), np.ones(len(ei), bool)])
    R, RN, RT = R[sel], RN[sel], RT[sel]
    S = len(R)
    lo, hi = cfg["layer"]
    lam = lo + (hi - lo) * rng.random(S) ** 0.7              # more cards on the outside
    fly = rng.random(S) < cfg["fly"]
    lam[fly] = 1.0
    lam[is_edge] = rng.uniform(0.85, 1.0, int(is_edge.sum()))
    print(f"[A] {S} roots")

    # ---------------------------------------------------------- flow
    crown = centre + up * 0.09 + fwd * -0.035

    def style_flow(p):
        r = p - centre
        if cfg["style"] == "long_part":
            sx = np.sign(r @ side)[:, None]
            sx[sx == 0] = 1
            topness = smoothstep(z_eye + 0.03, top - 0.012, p[:, 2])[:, None]
            front = smoothstep(-0.04, 0.05, r @ fwd)[:, None]
            d = side[None] * sx * (0.25 + 0.75 * topness) - up[None] * (0.45 + 0.55 * (1 - topness)) \
                - fwd[None] * 0.35 * (1 - front)
            hang = smoothstep(z_eye + 0.04, z_eye - 0.03, p[:, 2])[:, None]     # below the ears: straight down
            return unit(d * (1 - hang) + (-up[None]) * hang)
        d = p - crown
        d = d - up[None] * (d @ up)[:, None] * 0.25
        front = smoothstep(0.0, 0.04, r @ fwd)[:, None]
        d = d + up[None] * 0.25 * front * np.linalg.norm(d, axis=1, keepdims=True)   # front lifts up
        return unit(d)

    def flow_at(p, n, i_q):
        A = style_flow(p)
        F = TF[i_q]
        s = np.sign((F * A).sum(1))[:, None]
        s[s == 0] = 1
        w = (cfg["tex_flow"] * TC[i_q])[:, None]
        d = A * (1 - w) + F * s * w
        d = d - n * (d * n).sum(1, keepdims=True)
        return unit(d)

    eyeP = D["eye"]["P"]
    y_face = float(eyeP[:, 1].mean()) + 0.045      # a little behind the eyes: the temples' plane

    def face_window(q, margin):
        """Long hair falls beside the face, never across it: a frontal window (forehead below the hairline, eyes,
        cheeks, chin) that strands in front of the temples' plane are pushed out of, sideways."""
        z = q[:, 2] - z_eye
        hw = np.interp(z, [-0.14, -0.12, -0.07, 0.0, 0.03, 0.05, 0.068], [0.0, 0.046, 0.064, 0.07, 0.058, 0.036, 0.0])
        hw = np.where(hw > 0, hw + margin, 0.0)
        inside = (np.abs(q[:, 0]) < hw) & (q[:, 1] < y_face)
        if inside.any():
            sx = np.sign(q[inside, 0])
            sx[sx == 0] = 1
            q[inside, 0] = sx * hw[inside]
        return q

    # ---------------------------------------------------------- strands: trace layer by layer through the volume
    seg = cfg["seg_len"]
    nmax = int(cfg["max_len"] / seg) + 2
    L_max = cfg["max_len"] * rng.uniform(0.8, 1.05, S) * np.where(is_edge, cfg.get("edge_len", 0.35), 1.0)
    if not cfg.get("cape"):
        # short hair: the nape's hair lies flat and short (a few cm), it does not run down the neck
        L_max = np.minimum(L_max, 0.03 + 0.12 * smoothstep(head[2] - 0.05, head[2] + 0.03, R[:, 2]))
    pts = np.full((S, nmax + 1, 3), np.nan)
    p = R + RN * 0.0005
    pts[:, 0] = p
    fw_margin = rng.uniform(0.0, 0.009, S)
    drape = np.zeros(S)
    z_neck = float(J["neck_01"][2]) + 0.03
    y_sh = float(J["upperarm_l"][1]) if "upperarm_l" in J else float(J["neck_01"][1])
    lift_s = cfg["lift"] * np.where(is_edge, cfg.get("edge_lift", 0.35), 1.0)
    d0 = flow_at(R, RN, S_sh.query(R)[0])
    d = unit(d0 + RN * lift_s[:, None])
    alive = np.ones(S, bool)
    arc = np.zeros(S)
    count = np.ones(S, int)
    jit = rng.normal(0, 1, (S, 3)) * cfg["jitter"]
    off_hair = np.zeros(S, int)
    for k in range(1, nmax + 1):
        idx = np.nonzero(alive)[0]
        if not len(idx):
            break
        pa = pts[idx, k - 1]
        iq, dq = S_sh.query(pa)
        nq = S_sh.N[iq]
        fd = flow_at(pa, nq, iq)
        # direction: inertia + flow; emerging strands also rise along the scalp normal
        emerge = 1.0 - smoothstep(0.0, cfg["emerge"], arc[idx])[:, None]
        grav = -up[None] * (0.25 if cfg["style"] == "long_part" else 0.08) * smoothstep(0.02, 0.1, arc[idx])[:, None]
        nd = unit(d[idx] * 0.55 + fd * 0.45 + RN[idx] * lift_s[idx, None] * emerge + grav + jit[idx])
        nd = unit(nd - nq * ((nd * nq).sum(1, keepdims=True) * 0.7 * (1 - emerge)))
        q = pa + nd * seg
        # layer constraint against the shell: target depth below its surface
        iq, dq = S_sh.query(q)
        nq, Xq = S_sh.N[iq], S_sh.X[iq]
        h = ((q - Xq) * nq).sum(1)
        tan_off = np.linalg.norm((q - Xq) - nq * h[:, None], axis=1)
        under = ((tan_off < 0.006) | (edge_d[iq] > 0.005)) & (h > -0.12)
        ramp = smoothstep(0.0, cfg["emerge"], arc[idx] + seg)
        target = -(1.0 - lam[idx] * ramp) * np.minimum(thick[iq], 0.09) - 0.0015 * (1 - lam[idx]) \
            + 0.002 * lam[idx] * ramp
        corr = np.where(under, target - h, 0.0)
        corr = np.where(under & (h > target), corr, corr * 0.5)       # always pushed below the surface
        q = q + nq * corr[:, None]
        # keep clear of the body (2.5 mm, more for inner layers so they don't sink into the skull)
        ib, db = S_body.query(q)
        nb, Xb = S_body.N[ib], S_body.X[ib]
        hb = ((q - Xb) * nb).sum(1)
        clear = 0.0025 + 0.002 * lam[idx]
        q = q + nb * np.maximum(clear - hb, 0)[:, None]
        lie = 0.003 + lam[idx] * cfg["min_thick"]
        q = q - nb * (np.where(~under & (hb > lie), (hb - lie) * 0.8, 0.0))[:, None]
        # long hair frames the face: nothing crosses the face window (it is pushed out to the side instead)
        if cfg.get("face_window"):
            q = face_window(q, fw_margin[idx])
            # over the shoulders: drape to the front or to the back (whichever side the strand arrives on), instead
            # of sliding sideways along the shoulder line (that piles strands into a ridge)
            on_sh = (nb[:, 2] > 0.45) & (q[:, 2] < z_neck) & (hb < clear + 0.004)
            if on_sh.any():
                new_side = on_sh & (drape[idx] == 0)
                drape[idx[new_side]] = np.where(q[new_side, 1] < y_sh, -1.0, 1.0)
                q[on_sh, 1] += drape[idx[on_sh]] * seg * 0.7
        # beyond the shell: hair continues only over hair-coloured skin (painted scalp, the cape on the back)
        # (clothes count only for long hair, whose ends were baked onto the clothes: a dark hoodie is not hair)
        mats_here = S_body.mat[ib] if cfg.get("cape") else np.where(S_body.mat[ib] == D["cloth_mat"], -1, S_body.mat[ib])
        c_rgb = surface_colors(D, mats_here, S_body.uv[ib])
        hairy_here = (c_rgb @ np.array([0.2126, 0.7152, 0.0722])) < hair_thr
        beyond = ~under
        off_hair[idx] = np.where(beyond & ~hairy_here, off_hair[idx] + 1, 0)
        # floors: the fringe stops above the eyes (long hair: the face window does that job)
        r = q - centre
        azq = np.abs(np.arctan2(r @ side, r @ fwd))
        fl = np.where((azq < 0.9) & (not cfg.get("face_window")), z_eye + cfg.get("front_stop", 0.012), -1e9)
        stop = (off_hair[idx] >= 2) | (q[:, 2] < fl) | (arc[idx] + seg > L_max[idx])
        if not cfg.get("cape"):
            stop |= beyond & (q[:, 2] < head[2] + cfg.get("neck_stop", -0.06))
        go = ~stop
        gi = idx[go]
        pts[gi, k] = q[go]
        d[gi] = unit(q[go] - pa[go])
        arc[gi] += seg
        count[gi] += 1
        alive[idx[stop]] = False
    keep = count >= 4
    print(f"[A] traced in {time.time() - t0:.1f}s; kept {int(keep.sum())}/{S}; mean length {arc[keep].mean():.3f} m")
    pts, count, lam, fly, arc, is_edge = pts[keep], count[keep], lam[keep], fly[keep], arc[keep], is_edge[keep]
    S = len(pts)

    # ---------------------------------------------------------- clumps (pull tips together), curls
    roots = pts[:, 0]
    n_cl = max(12, S // 9)
    cid = rng.choice(S, n_cl, replace=False)
    owner = cKDTree(roots[cid]).query(roots)[1]
    for j in range(n_cl):
        m = np.nonzero(owner == j)[0]
        if len(m) < 2:
            continue
        n = count[m].min()
        mean = np.nanmean(pts[m, :n], axis=0)
        t = (np.arange(n) / max(n - 1, 1)) ** 1.3 * cfg["clump"]
        pts[m, :n] = pts[m, :n] * (1 - t[None, :, None]) + (mean[None] + (pts[m, :1] - mean[:1]) * (1 - t)[None, :, None]) * t[None, :, None]
    spine = pts.copy()
    if cfg["curl"]:
        amp, wl = cfg["curl"]
        ph_cl = rng.uniform(0, 6.283, n_cl)
        for i in range(S):
            n = count[i]
            s = spine[i, :n]
            tan = unit(np.gradient(s, axis=0))
            iq = S_sh.query(s)[0]
            b1 = unit(np.cross(tan, S_sh.N[iq]))
            b2 = unit(np.cross(tan, b1))
            a_ = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(s, axis=0), axis=1))])
            ph = ph_cl[owner[i]] + rng.normal(0, 0.4) + 6.283 * a_ / (wl * rng.uniform(0.85, 1.15))
            ramp = smoothstep(0.015, 0.05, a_)[:, None] * amp * rng.uniform(0.7, 1.3)
            pts[i, :n] = s + (b1 * np.sin(ph)[:, None] * 0.6 + b2 * np.cos(ph)[:, None]) * ramp

    # ---------------------------------------------------------- cards
    verts, uvs, cols, faces, norms, tangs = [], [], [], [], [], []
    strips = 8
    base = 0
    c_root, c_tip = hx(cfg["colors"][0]), hx(cfg["colors"][1])
    for i in range(S):
        n = count[i]
        s, g_ = pts[i, :n], spine[i, :n]
        tan = unit(np.gradient(g_, axis=0))
        iq, dq_ = S_sh.query(g_)
        nrm = S_sh.N[iq]
        ib_ = S_body.query(g_)[0]
        vol_n = np.where((dq_ < 0.03)[:, None], nrm, S_body.N[ib_])
        wv = unit(np.cross(tan, nrm))
        tw = math.radians(rng.normal(0, cfg["twist"] * (1.6 if fly[i] else 1.0)))
        wv = unit(wv * math.cos(tw) + np.cross(tan, wv) * math.sin(tw))
        a_ = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(s, axis=0), axis=1))])
        L = a_[-1]
        t = a_ / max(L, 1e-6)
        width = rng.uniform(*cfg["width"]) * (0.45 if fly[i] else (0.6 if is_edge[i] else 1.0))
        wdt = width * (1.0 - cfg["taper"] * t ** 1.3) * smoothstep(-0.3, 0.08, t)
        wdt = wdt * (0.35 + 0.65 * smoothstep(0.0, 0.02, a_))      # narrow roots: no straight card cut at the hairline
        left, right = s - wv * (wdt / 2)[:, None], s + wv * (wdt / 2)[:, None]
        # texture: strip per card (wispy strips for flyaways); v keeps a constant world scale up to tex_len
        stp = (rng.integers(0, strips // 2) * 2 + 1) if fly[i] else rng.integers(0, strips)
        u0, u1 = stp / strips + 0.003, (stp + 1) / strips - 0.003
        Lt = cfg["tex_len"]
        v = (a_ + max(Lt - L, 0.0)) / max(Lt, L)            # tip at the texture's tip
        # colour: cast colour (root -> tip) x scan shell brightness under the card x depth occlusion
        rel = np.median(sh_rel[iq])
        ao = (0.42 + 0.58 * lam[i] ** 0.9) * (0.62 + 0.38 * smoothstep(0.0, 0.3, t))
        tone = rng.uniform(0.85, 1.15)
        cc = (c_root[None] * (1 - t[:, None]) + c_tip[None] * t[:, None]) * (rel * ao * tone)[:, None]
        vv = np.empty((2 * n, 3))
        vv[0::2], vv[1::2] = left, right
        uu = np.empty((2 * n, 2))
        uu[0::2, 0], uu[1::2, 0] = u0, u1
        uu[0::2, 1] = uu[1::2, 1] = 1.0 - v                 # Blender UV: v up; the strip's root is the image top
        col4 = np.ones((2 * n, 4))
        col4[0::2, :3] = col4[1::2, :3] = cc
        col4[:, 3] = lam[i]
        f = np.array([[base + 2 * j, base + 2 * j + 1, base + 2 * j + 3, base + 2 * j + 2] for j in range(n - 1)])
        nn = np.empty((2 * n, 3))
        nn[0::2] = nn[1::2] = unit(vol_n * 0.85 + unit(np.cross(wv, tan)) * 0.15)
        # strand direction (root -> tip) along the card's actual, curled centre line: what a strand shader uses
        # (Kajiya-Kay); on curls it turns with the helix, so every curl gets its own highlight
        tg = np.empty((2 * n, 3))
        tg[0::2] = tg[1::2] = unit(np.gradient(s, axis=0))
        verts.append(vv), uvs.append(uu), cols.append(col4), faces.append(f), norms.append(nn), tangs.append(tg)
        base += 2 * n
    V = np.concatenate(verts)
    F = np.concatenate(faces)
    print(f"[A] {S} cards, {len(V)} verts, {2 * len(F)} tris, {time.time() - t0:.1f}s")

    # ---------------------------------------------------------- the scalp cap (replaces the shell under the cards)
    # the scalp region of the body, 1-2 mm out, in the root colour; alpha ramps in over ~1.2 cm from the hairline so
    # the edge is soft, and a centre part shows a thin line of skin
    cap_tri = Tb[(scalp[Tb].sum(1) >= 1) & (((hw + nw)[Tb].min(1) > 0.25) | (body["mat"] == D["head_mat"]))]
    cv, cinv = np.unique(cap_tri, return_inverse=True)
    cap_F = cinv.reshape(-1, 3)
    cap_V = P[cv] + Nb[cv] * cfg.get("cap_lift", 0.0015)
    c_dist, c_scalp, c_nz = dist[cv].astype(float), scalp[cv].astype(float), Nb[cv, 2].astype(float)
    if cfg.get("part"):
        # the body mesh is ~1 cm per edge: subdivide the cap twice along the part, or the skin line comes out 1 cm wide
        for _ in range(2):
            on_line = (np.abs(cap_V[cap_F, 0]) < 0.012).any(1) & (c_nz[cap_F] > 0.3).all(1) & (cap_V[cap_F, 1] < centre[1] + 0.05).all(1)
            Fs, Fk = cap_F[on_line], cap_F[~on_line]
            e = np.sort(np.concatenate([Fs[:, [0, 1]], Fs[:, [1, 2]], Fs[:, [2, 0]]]), 1)
            eu, einv = np.unique(e, axis=0, return_inverse=True)
            mid = len(cap_V) + np.arange(len(eu))
            cap_V = np.concatenate([cap_V, (cap_V[eu[:, 0]] + cap_V[eu[:, 1]]) / 2])
            c_dist, c_scalp, c_nz = [np.concatenate([x, (x[eu[:, 0]] + x[eu[:, 1]]) / 2]) for x in (c_dist, c_scalp, c_nz)]
            m = mid[einv.ravel()].reshape(3, -1).T
            a0, b0, c0 = Fs[:, 0], Fs[:, 1], Fs[:, 2]
            cap_F = np.concatenate([Fk, np.stack([a0, m[:, 0], m[:, 2]], 1), np.stack([m[:, 0], b0, m[:, 1]], 1),
                                    np.stack([m[:, 2], m[:, 1], c0], 1), np.stack([m[:, 0], m[:, 1], m[:, 2]], 1)])
    c_alpha = np.where(c_scalp > 0.5, smoothstep(0.002, 0.010, c_dist), 0.0)
    c_rgb = np.repeat((c_root * 1.3)[None], len(cap_V), 0)
    if cfg.get("part"):
        # the part is a thin line of skin: the cap takes the forehead's skin colour there (the bake under it is
        # hair-coloured, so a transparent cap would show a grey line)
        fh = (np.abs(P[:, 0]) < 0.03) & (P[:, 2] > z_eye + 0.025) & (P[:, 2] < z_eye + 0.05) & (P[:, 1] < centre[1] - 0.04)
        skin = srgb_to_lin(np.median(col[fh & ~scalp], axis=0)) if (fh & ~scalp).any() else np.array([0.5, 0.35, 0.28])
        on_top = (c_nz > 0.35) & (cap_V[:, 1] < centre[1] + 0.04)
        pm = np.where(on_top, 1.0 - smoothstep(0.0006, 0.0028, np.abs(cap_V[:, 0])), 0.0)
        c_rgb = c_rgb * (1 - pm[:, None]) + (skin * 0.62)[None] * pm[:, None]     # a thin line, in the hair's shade
        c_alpha = np.maximum(c_alpha, pm * (c_scalp > 0.5))
    cap_C = np.concatenate([c_rgb, c_alpha[:, None]], 1)
    print(f"[A] cap: {len(cap_V)} verts, {len(cap_F)} tris")

    # ---------------------------------------------------------- the inner occluder (optional, short hair)
    # the scan shell pulled half-way to the skull and cut to the part the cards cover: dense hair is dark inside,
    # light should not pass through the curls to the scalp. Faces more than ~1 cm from any card are dropped
    # (that is where the old shell showed as a grey band on the forehead / a veil in front of the face).
    occ = {}
    if cfg.get("occluder"):
        i_b, d_b = S_body.query(shell["P"])
        inward = np.clip(cfg["occluder"] * d_b, 0.002, 0.03)
        oV = shell["P"] - shell["N"] * inward[:, None]
        dcard = cKDTree(V).query(oV)[0]
        # only over the scalp (at least 5 mm inside the hairline) and only where cards pass close by
        nb_i = cKDTree(P).query(oV)[1]
        inside = scalp[nb_i] & (dist[nb_i] > 0.01)
        okv = (dcard < 0.009) & inside
        oT = shell["T"][okv[shell["T"]].all(1)]
        ov, oinv = np.unique(oT, return_inverse=True)
        o_alpha = smoothstep(0.009, 0.004, dcard[ov]) * smoothstep(0.01, 0.02, dist[nb_i[ov]])
        occ = dict(occ_V=oV[ov].astype(np.float32), occ_F=oinv.reshape(-1, 3).astype(np.int32),
                   occ_C=np.concatenate([np.repeat((c_root * 0.8)[None], len(ov), 0), o_alpha[:, None]], 1).astype(np.float32))
        print(f"[A] occluder: {len(ov)} verts, {len(oT)} tris (of {len(shell['T'])})")

    # ---------------------------------------------------------- the shell as a darker under-layer
    i_b, d_b = S_body.query(shell["P"])
    inward = np.clip(0.4 * d_b - 0.004, 0.0025, 0.015)
    sh_off = -shell["N"] * inward[:, None]
    sh_edge = kdB.query(shell["P"])[0]
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(os.path.join(OUT, f"{stem}_cards.npz"), V=V.astype(np.float32), F=F.astype(np.int32),
                        UV=np.concatenate(uvs).astype(np.float32), C=np.concatenate(cols).astype(np.float32),
                        N=np.concatenate(norms).astype(np.float32), TG=np.concatenate(tangs).astype(np.float32),
                        shell_P=shell["P"].astype(np.float32), shell_off=sh_off.astype(np.float32),
                        shell_edge=sh_edge.astype(np.float32),
                        cap_V=cap_V.astype(np.float32), cap_F=cap_F.astype(np.int32), cap_C=cap_C.astype(np.float32), **occ,
                        head=head, z_eye=z_eye, atlas=cfg["atlas"], scalp_P=P[scalp].astype(np.float32),
                        roots=roots.astype(np.float32))
    debug_view(stem, V, F, P[scalp], shell["P"], roots)
    return V, F


def debug_view(stem, V, F, scalp, shellP, roots):
    """Orthographic splats (front / side / back / top) of cards, scalp region and shell, for a quick look."""
    import cv2
    views = [("front", np.array([1, 0, 0]), np.array([0, 0, 1])), ("side", np.array([0, -1, 0]), np.array([0, 0, 1])),
             ("back", np.array([-1, 0, 0]), np.array([0, 0, 1])), ("top", np.array([1, 0, 0]), np.array([0, -1, 0]))]
    c = V.mean(0)
    s = 1400
    tiles = []
    for name, ax, ay in views:
        im = np.full((560, 560, 3), 40, np.uint8)
        for X, colr, r in ((shellP, (90, 90, 160), 1), (scalp, (60, 160, 60), 1), (V, (220, 220, 220), 0), (roots, (0, 0, 255), 1)):
            x = ((X - c) @ ax * s + 280).astype(int)
            y = (280 - (X - c) @ ay * s).astype(int)
            ok = (x >= 0) & (x < 560) & (y >= 0) & (y < 560)
            if r == 0:
                im[y[ok], x[ok]] = colr
            else:
                for xx, yy in zip(x[ok][::3], y[ok][::3]):
                    im[yy, xx] = colr
        cv2.putText(im, name, (8, 22), 0, 0.7, (255, 255, 255), 1)
        tiles.append(im)
    cv2.imwrite(os.path.join(OUT, f"{stem}_debug.png"), np.concatenate(tiles, 1))


if __name__ == "__main__":
    args = sys.argv[1:]
    seed = int(next((a.split("=")[1] for a in args if a.startswith("seed=")), 7))
    for stem in [a for a in args if "=" not in a] or ["toma_fit1", "anisha"]:
        grow(stem, seed)
