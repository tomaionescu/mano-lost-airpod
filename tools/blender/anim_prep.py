"""Pre-process mocap takes into skeleton-independent clips: assets/anims/cache/<clip>.json.

Each cached clip holds, at 30 fps, for every canonical segment (see anim_clips.SEGMENTS) the world-space
rotation *relative to the canonical T-pose* (character facing -Y, +X its left, Z up, palms down, legs straight),
plus key joint positions normalised by the source leg length (hip joint -> ankle) and foot contacts.
retarget.py turns that into actions for any MPFB game_engine rig. numpy only (runs inside Blender or not):

    python anim_prep.py [clip ...]        # (re)build caches; done automatically by retarget.apply()
"""
import os, sys, json, hashlib, base64, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import anim_bvh as ab
import anim_clips as ac

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC_DIR = os.path.join(ROOT, "assets", "anims", "src")
CACHE_DIR = os.environ.get("ANIM_CACHE_DIR") or os.path.join(ROOT, "assets", "anims", "cache")
# extra source folders (development only: evaluating takes before copying them into assets/anims/src)
SRC_DIRS = [SRC_DIR] + [d for d in os.environ.get("ANIM_SRC_EXTRA", "").split(os.pathsep) if d]
FPS = 30.0
PREP_VERSION = 14
M = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)  # BVH (Y up, +Z forward) -> Blender (Z up, -Y forward)

_bvh_cache = {}
_calib_cache = {}


def log(*a):
    print("[anim_prep]", *a, flush=True)


# ---------------------------------------------------------------------- sources
def src_path(take):
    for d in SRC_DIRS:
        p = os.path.join(d, take + ".bvh")
        if os.path.exists(p):
            return p
    return os.path.join(SRC_DIR, take + ".bvh")


def load_src(take):
    if take not in _bvh_cache:
        _bvh_cache[take] = ab.load(src_path(take))
    return _bvh_cache[take]


def file_sig(take):
    p = src_path(take)
    st = os.stat(p)
    return f"{take}:{st.st_size}"


# ---------------------------------------------------------------------- small helpers
def rz(yaw):
    c, s = np.cos(yaw), np.sin(yaw)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def rx(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def gauss_kernel(sigma):
    if sigma <= 1e-3:
        return np.array([1.0])
    r = int(np.ceil(3 * sigma))
    x = np.arange(-r, r + 1)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    return k / k.sum()


def smooth_time(x, sigma):
    """Gaussian filter along axis 0 with edge padding."""
    k = gauss_kernel(sigma)
    if len(k) == 1 or len(x) < 3:
        return x
    r = len(k) // 2
    pad = np.concatenate([np.repeat(x[:1], r, 0), x, np.repeat(x[-1:], r, 0)], 0)
    out = np.zeros_like(x)
    for i, w in enumerate(k):
        out += w * pad[i:i + len(x)]
    return out


def smooth_quats(q, sigma):
    q = ab.quat_continuity(q, 0)
    q = smooth_time(q, sigma)
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def project_so3(m):
    u, _, vt = np.linalg.svd(m)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return r


def smoothstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def runs(mask):
    """[(start, end_exclusive)] of True runs."""
    m = np.concatenate([[False], mask, [False]]).astype(int)
    d = np.diff(m)
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def clean_mask(mask, min_on=2, max_gap=2):
    mask = mask.copy()
    for s, e in runs(~mask):
        if 0 < s and e < len(mask) and e - s <= max_gap:
            mask[s:e] = True
    for s, e in runs(mask):
        if e - s < min_on:
            mask[s:e] = False
    return mask


# ---------------------------------------------------------------------- calibration (source canonical frames)
def calibration(take):
    """T[j]: world rotation (Blender axes) of joint j when the source skeleton stands in the canonical T-pose."""
    bvh = load_src(take)
    sk_name = ac.skeleton_of(bvh)
    sk = ac.SKELETONS[sk_name]
    key = take if sk["calib"] == "tpose" else sk_name
    if key in _calib_cache:
        return _calib_cache[key]
    J = len(bvh.names)
    idx = {n: i for i, n in enumerate(bvh.names)}
    T = np.tile(np.eye(3), (J, 1, 1))
    if sk["calib"] == "tpose":
        W, P = bvh.fk(frames=[0])
        W = np.einsum("ij,kjl->kil", M, W[0])
        P = P[0] @ M.T
        T[:] = W
        for seg, dirc in ac.LIMB_DIRS.items():
            for jn, _ in sk["segments"][seg]:
                j, c = idx[jn], idx[sk["children"][jn]]
                T[j] = ab.swing_to(P[c] - P[j], np.array(dirc, float)) @ T[j]
        ref_pose = P
    else:
        acc = np.zeros((J, 3, 3))
        ref_pose = None
        for rtake, t0, t1 in sk["ref"]:
            rb = load_src(rtake)
            fr = np.arange(int(t0 * rb.fps), max(int(t0 * rb.fps) + 1, int(t1 * rb.fps)))
            W, P = rb.fk(frames=fr)
            W = np.einsum("ij,fkjl->fkil", M, W)
            P = P @ M.T
            pts = sk["points"]
            lat = P[:, idx[pts["hip_l"]]] - P[:, idx[pts["hip_r"]]]
            yaw = np.arctan2(lat[:, 1].mean(), lat[:, 0].mean())
            R = rz(-yaw)
            acc += np.einsum("ij,fkjl->kil", R, W)
            if ref_pose is None:
                ref_pose = (P[0] - P[0, idx["Hips"]] * [1, 1, 0]) @ R.T
        for j in range(J):
            T[j] = project_so3(acc[j])
        for jn, (xd, yd) in sk["axes"].items():
            X = M @ np.array(xd, float)
            Y = M @ np.array(yd, float)
            T[idx[jn]] = np.stack([X, Y, np.cross(X, Y)], 1)
    leg = sk["leg"]
    L = np.linalg.norm(bvh.offsets[idx[leg[1]]]) + np.linalg.norm(bvh.offsets[idx[leg[2]]])
    pts = sk["points"]
    foot_pitch = {}
    for side in "lr":
        d = ref_pose[idx[pts["toe_" + side]]] - ref_pose[idx[pts["ankle_" + side]]]
        foot_pitch[side] = np.arctan2(-d[2], np.linalg.norm(d[:2]))
    res = {"T": T, "L": L, "skel": sk_name, "foot_pitch": foot_pitch}
    _calib_cache[key] = res
    return res


# ---------------------------------------------------------------------- sampling
def sample_take(take, t0, t1, rate=1.0, smooth=0.7):
    """World rotations (F,J,3,3) and positions (F,J,3) in Blender axes at 30 fps for source time [t0, t1]."""
    bvh = load_src(take)
    fps = bvh.fps
    n_out = int(round((t1 - t0) * FPS / rate)) + 1
    times = t0 + np.arange(n_out) * rate / FPS
    times = np.clip(times, 0, (bvh.nframes - 1) / fps)
    s0 = max(0, int(np.floor(times[0] * fps)) - 12)
    s1 = min(bvh.nframes, int(np.ceil(times[-1] * fps)) + 13)
    fr = np.arange(s0, s1)
    lrot, ltrans = bvh.local(fr)
    q = ab.mat_to_quat(lrot)
    sig = max(smooth * fps / FPS, 0.55 * fps / FPS) if fps > FPS * 1.01 else smooth
    q = smooth_quats(q, sig)
    ltrans = smooth_time(ltrans, sig)
    u = times * fps - s0
    i0 = np.clip(np.floor(u).astype(int), 0, len(fr) - 1)
    i1 = np.clip(i0 + 1, 0, len(fr) - 1)
    w = (u - i0)[:, None]
    qa, qb = q[i0], q[i1]
    qs = ab.quat_slerp(qa, qb, np.broadcast_to(w, qa.shape[:-1]))
    ts = ltrans[i0] * (1 - w[..., None]) + ltrans[i1] * w[..., None]
    W, P = bvh.fk(local=(ab.quat_to_mat(qs), ts))
    W = np.einsum("ij,fkjl->fkil", M, W)
    P = P @ M.T
    return W, P, bvh


def canonical(W, take, cal):
    """Segment rotations relative to the canonical T-pose, (F, S, 4) quaternions."""
    bvh = load_src(take)
    sk = ac.SKELETONS[cal["skel"]]
    T = cal["T"]
    idx = {n: i for i, n in enumerate(bvh.names)}
    out = []
    for seg in ac.SEGMENTS:
        acc = None
        for jn, wgt in sk["segments"][seg]:
            j = idx[jn]
            g = ab.quat_continuity(ab.mat_to_quat(W[:, j] @ T[j].T), 0)
            if acc is None:
                acc = g * wgt
            else:
                d = np.sum(acc * g, -1, keepdims=True)
                acc = acc + np.where(d < 0, -g, g) * wgt
        out.append(acc / np.linalg.norm(acc, axis=-1, keepdims=True))
    return np.stack(out, 1)


def points(P, take, cal):
    bvh = load_src(take)
    sk = ac.SKELETONS[cal["skel"]]
    idx = {n: i for i, n in enumerate(bvh.names)}
    d = {k: P[:, idx[v]] for k, v in sk["points"].items()}
    d["hips"] = 0.5 * (d["hip_l"] + d["hip_r"])
    return np.stack([d[k] for k in ac.POINTS], 1)


PI = {k: i for i, k in enumerate(ac.POINTS)}
SI = {k: i for i, k in enumerate(ac.SEGMENTS)}


# ---------------------------------------------------------------------- analysis
def contacts(pts, L, v_ground=None):
    """Per frame [heel_l, toe_l, heel_r, toe_r] booleans from normalised points (z relative to flat ankle).
    v_ground: treadmill velocity (leg lengths per second) of planted feet in in-place loops."""
    F = len(pts)
    out = np.zeros((F, 4), bool)
    vg = np.zeros(2) if v_ground is None else np.asarray(v_ground, float)[:2]
    for k, side in enumerate("lr"):
        for m, name in enumerate(("ankle_", "toe_")):
            p = pts[:, PI[name + side]]
            base = np.percentile(p[:, 2], 8)
            v = np.zeros(F)
            if F > 2:
                d = (p[2:, :2] - p[:-2, :2]) * FPS / 2 - vg
                v[1:-1] = np.linalg.norm(d, axis=1)
                v[0], v[-1] = v[1], v[-2]
            low = (p[:, 2] - base) < (0.045 if m == 0 else 0.035)
            slow = v < max(0.45, 0.22 * np.linalg.norm(vg))
            out[:, 2 * k + m] = clean_mask(low & slow)
    return out


def pose_features(pts):
    rel = pts - pts[:, PI["hips"]][:, None, :] * np.array([1, 1, 0])
    f = rel.reshape(len(pts), -1)
    vel = np.gradient(f, axis=0) * 4.0
    return np.concatenate([f, vel], 1)


def best_loop(pts, lo, hi, nmin, nmax):
    feat = pose_features(pts)
    best = (1e18, lo, lo + nmin)
    for a in range(lo, hi - nmin + 1):
        b0, b1 = a + nmin, min(a + nmax, hi)
        if b1 < b0:
            break
        d = np.sum((feat[b0:b1 + 1] - feat[a]) ** 2, 1)
        k = int(np.argmin(d))
        if d[k] < best[0]:
            best = (d[k], a, b0 + k)
    return best


def crossfade_rot(Q, a, b, N):
    out = Q[a:b].copy()
    n = b - a
    if a - N >= 0:
        for i in range(N):
            w = smoothstep((i + 1) / (N + 1))
            out[n - N + i] = ab.quat_slerp(Q[b - N + i], Q[a - N + i], w)
    elif b + N <= len(Q):
        for i in range(N):
            w = smoothstep((i + 1) / (N + 1))
            out[i] = ab.quat_slerp(Q[b + i], Q[a + i], w)
    return out


def crossfade_pos(X, a, b, N):
    out = X[a:b].copy()
    n = b - a
    if a - N >= 0:
        for i in range(N):
            w = smoothstep((i + 1) / (N + 1))
            out[n - N + i] = X[b - N + i] * (1 - w) + X[a - N + i] * w
    elif b + N <= len(X):
        for i in range(N):
            w = smoothstep((i + 1) / (N + 1))
            out[i] = X[b + i] * (1 - w) + X[a + i] * w
    return out


def facing_yaw(pts, frames):
    lat = pts[frames, PI["hip_l"]] - pts[frames, PI["hip_r"]]
    lat2 = pts[frames, PI["shoulder_l"]] - pts[frames, PI["shoulder_r"]]
    v = lat / np.linalg.norm(lat, axis=1, keepdims=True) + 0.5 * lat2 / np.linalg.norm(lat2, axis=1, keepdims=True)
    return np.arctan2(v[:, 1].mean(), v[:, 0].mean())


def apply_yaw(G, pts, yaw, center):
    R = rz(-yaw)
    Rq = ab.mat_to_quat(R)
    G = ab.quat_mul(np.broadcast_to(Rq, G.shape), G)
    pts = (pts - center) @ R.T
    return G, pts


def mirror(G, pts):
    """Mirror across the character's sagittal plane (x -> -x), swapping left and right."""
    S = np.diag([-1.0, 1, 1])
    mats = ab.quat_to_mat(G)
    mats = S @ mats @ S
    G2 = ab.mat_to_quat(mats)
    perm = [SI[s.replace("_l", "_X").replace("_r", "_l").replace("_X", "_r")] if s.endswith(("_l", "_r")) else SI[s] for s in ac.SEGMENTS]
    G2 = G2[:, perm]
    pts = pts * np.array([-1, 1, 1])
    pperm = [PI[p.replace("_l", "_X").replace("_r", "_l").replace("_X", "_r")] if p.endswith(("_l", "_r")) else PI[p] for p in ac.POINTS]
    return ab.quat_continuity(G2, 0), pts[:, pperm]


def flat_pitch(pts, contact):
    """Median foot pitch (radians, toe below ankle) over frames where heel and toes are both planted."""
    out = {}
    for k, side in enumerate("lr"):
        flat = contact[:, 2 * k] & contact[:, 2 * k + 1]
        if flat.sum() < 4:
            continue
        d = pts[flat, PI["toe_" + side]] - pts[flat, PI["ankle_" + side]]
        out[side] = float(np.median(np.arctan2(-d[:, 2], np.linalg.norm(d[:, :2], axis=1))))
    return out


def foot_correction(G, pts, cal, contact, ref=None):
    """Rotate the canonical foot frames so the take's flat-standing foot pitch maps to the target's flat foot.
    ref: flat pitches measured elsewhere in the take (e.g. its walking part) when the clip has no flat feet."""
    out = {}
    measured = ref if ref is not None else flat_pitch(pts, contact)
    for k, side in enumerate("lr"):
        if side not in measured:
            out[side] = 0.0
            continue
        pitch = measured[side]
        delta = float(pitch - cal["foot_pitch"][side])
        delta = float(np.clip(delta, -0.35, 0.35))
        out[side] = delta
        # G = W T^-1 ; T' = Rx(delta) T  ->  G' = W T^-1 Rx(-delta) = G Rx(-delta)
        cq = ab.mat_to_quat(rx(-delta))
        s = SI["foot_" + side]
        G[:, s] = ab.quat_mul(G[:, s], np.broadcast_to(cq, G[:, s].shape))
    return out


def _yaw_scale(q_parent, q_child, k):
    """Scale the yaw (twist about the parent's up axis) of child relative to parent by k."""
    rel = ab.quat_mul(ab.quat_conj(q_parent), q_child)
    tw = rel * np.array([1, 0, 0, 1])
    tw = tw / np.maximum(np.linalg.norm(tw, axis=-1, keepdims=True), 1e-9)
    sw = ab.quat_mul(rel, ab.quat_conj(tw))
    ang = 2 * np.arctan2(tw[:, 3], tw[:, 0])
    ang = (ang + np.pi) % (2 * np.pi) - np.pi
    tw2 = np.stack([np.cos(k * ang / 2), np.zeros_like(ang), np.zeros_like(ang), np.sin(k * ang / 2)], 1)
    return ab.quat_mul(q_parent, ab.quat_mul(sw, tw2))


def head_fix(G, cfg, kind):
    """Level the gaze: mocap head joints carry per-subject calibration offsets (CMU T-pose heads look 10-30 deg
    up or down). The head's median pitch/roll over the clip (first 0.5 s for one-shots) is moved to cfg['head']
    degrees (default 0 = level, negative = looking down). cfg['head_yaw'] scales head/neck turns (e.g. 0.3)."""
    G = G.copy()
    k = cfg.get("head_yaw", 1.0)
    if k != 1.0:
        for seg, par in (("neck_01", "spine_03"), ("head", "neck_01")):
            G[:, SI[seg]] = _yaw_scale(G[:, SI[par]], G[:, SI[seg]], k)
    k = cfg.get("head_damp", 1.0)
    if k != 1.0:
        # shrink neck/head motion (relative to the chest) towards its median orientation
        for seg, par in (("neck_01", "spine_03"), ("head", "neck_01")):
            rel = ab.quat_continuity(ab.quat_mul(ab.quat_conj(G[:, SI[par]]), G[:, SI[seg]]), 0)
            med = np.median(rel, 0)
            med /= np.linalg.norm(med)
            dev = ab.quat_mul(np.broadcast_to(ab.quat_conj(med), rel.shape), rel)
            dev = ab.quat_slerp(np.broadcast_to(np.array([1.0, 0, 0, 0]), dev.shape), dev, k)
            G[:, SI[seg]] = ab.quat_mul(G[:, SI[par]], ab.quat_mul(np.broadcast_to(med, rel.shape), dev))
    if cfg.get("head") is False:
        return G, 0.0, 0.0
    h = ab.quat_to_mat(G[:, SI["head"]])
    n = max(1, int(0.5 * FPS))
    where = cfg.get("head_ref", "start" if kind == "oneshot" else "all")
    ref = slice(0, n) if where == "start" else (slice(len(G) - n, None) if where == "end" else slice(None))
    f = h[ref] @ np.array([0, -1.0, 0])
    lat = h[ref] @ np.array([1.0, 0, 0])
    pitch = np.median(np.arctan2(f[:, 2], np.linalg.norm(f[:, :2], axis=1)))
    roll = np.median(np.arcsin(np.clip(lat[:, 2], -1, 1)))
    want = np.radians(cfg.get("head", 0.0))
    corr = rx(pitch - want) @ ab.quat_to_mat(ab.quat_exp(np.array([0.0, roll, 0.0])))
    cq = ab.mat_to_quat(corr)
    G[:, SI["head"]] = ab.quat_mul(G[:, SI["head"]], np.broadcast_to(cq, G[:, SI["head"]].shape))
    return G, float(np.degrees(pitch)), float(np.degrees(roll))


def floor_normalize(pts, L, sel):
    """Points in leg lengths with z measured from the flat ankle height of the lower foot (a foot resting on a
    rung must not lift the floor); small left/right differences are skeleton asymmetry, removed per foot."""
    pts = pts.copy()
    lows = [np.percentile(pts[sel, PI["ankle_" + sd], 2], 8) for sd in "lr"]
    a0 = min(lows)
    pts[..., 2] -= a0
    pts /= L
    for sd, lo in zip("lr", lows):
        r = (lo - a0) / L
        if 0 < r < 0.03:
            pts[:, PI["ankle_" + sd], 2] -= r
            pts[:, PI["toe_" + sd], 2] -= r
    return pts


# ---------------------------------------------------------------------- clip preparation
def prepare(name, cfg):
    t_start = time.time()
    take = cfg["src"]
    bvh = load_src(take)
    cal = calibration(take)
    L = cal["L"]
    rate = cfg.get("rate", 1.0)
    kind = cfg["kind"]
    t0, t1 = cfg["range"]
    dur = bvh.nframes / bvh.fps
    pre = min(1.0, t0) if kind != "oneshot" else 0.0
    post = min(1.0, dur - t1) if kind != "oneshot" else 0.0
    W, P, _ = sample_take(take, t0 - pre, t1 + post, rate, cfg.get("smooth", 0.7))
    G = canonical(W, take, cal)
    pts = points(P, take, cal)
    for (s0, s1) in cfg.get("splice", []):
        # append another segment of the same take, joined at the best matching pose (shortens long takes)
        W2, P2, _ = sample_take(take, s0, s1, rate, cfg.get("smooth", 0.7))
        G2, p2 = canonical(W2, take, cal), points(P2, take, cal)
        fa, fb = pose_features(pts / L), pose_features(p2 / L)
        na, nb = max(1, min(12, len(G) // 3)), max(1, min(12, len(G2) // 3))
        best = (1e18, len(G) - 1, 0)
        for ia in range(len(G) - na, len(G)):
            d = np.sum((fb[:nb] - fa[ia]) ** 2, 1)
            k = int(np.argmin(d))
            if d[k] < best[0]:
                best = (d[k], ia, k)
        _, ia, ib = best
        G2, p2 = G2[ib:].copy(), p2[ib:].copy()
        p2 += (pts[ia, PI["hips"]] - p2[0, PI["hips"]]) * np.array([1, 1, 0])
        G, pts = G[:ia + 1], pts[:ia + 1]
        N = min(6, len(G2) - 1)
        for k in range(N):
            w = smoothstep((k + 1) / (N + 1))
            G2[k] = ab.quat_slerp(G[-1], G2[k], w)
            p2[k] = pts[-1] * (1 - w) + p2[k] * w
        G = np.concatenate([G, G2[1:]], 0)
        pts = np.concatenate([pts, p2[1:]], 0)
    F = len(G)
    i_lo = int(round(pre * FPS / rate))
    i_hi = F - 1 - int(round(post * FPS / rate))

    # vertical reference: flat ankle height of the lower foot (a foot resting on a rung must not lift the floor);
    # small left/right differences are skeleton asymmetry and are removed per foot
    pts = floor_normalize(pts, L, slice(i_lo, i_hi + 1))
    contact = contacts(pts, L)

    meta = {"name": name, "src": take, "skel": cal["skel"], "kind": kind, "fps": FPS, "rate": rate,
            "loop": kind in ("loop", "loco"), "src_range": [t0, t1], "leg_src": L}

    if kind == "loco":
        cycles = cfg.get("cycles", 2)
        # foot strikes of the left foot (heel or toes first: runners land on the forefoot)
        hs = [s for s, e in runs(contact[:, 0] | contact[:, 1]) if i_lo <= s <= i_hi]
        best = None
        feat = pose_features(pts)
        for i in range(len(hs) - cycles):
            a, b = hs[i], hs[i + cycles]
            for bb in range(b - 2, b + 3):
                if bb > i_hi + 2 or bb >= F:
                    continue
                d = np.sum((feat[bb] - feat[a]) ** 2)
                mid = abs((a + bb) / 2 - (i_lo + i_hi) / 2) / F
                score = d + 0.5 * mid
                if best is None or score < best[0]:
                    best = (score, a, bb)
        if best is None:
            raise RuntimeError(f"{name}: no {cycles} gait cycles found in range")
        _, a, b = best
        travel = pts[b, PI["hips"]] - pts[a, PI["hips"]]
        yaw = np.arctan2(travel[1], travel[0]) + np.pi / 2  # travel direction -> -Y
        G, pts = apply_yaw(G, pts, yaw, np.zeros(3))
        v = (pts[b, PI["hips"]] - pts[a, PI["hips"]]) / (b - a)
        v[2] = 0
        pts = pts - (np.arange(F) - a)[:, None, None] * v[None, None, :]
        N = 4
        G = np.stack([crossfade_rot(G[:, s], a, b, N) for s in range(G.shape[1])], 1)
        pts = crossfade_pos(pts, a, b, N)
        c = pts[:, PI["hips"]].mean(0) * np.array([1, 1, 0])
        pts = pts - c
        meta["speed_leg"] = float(np.linalg.norm(v) * FPS)  # leg lengths per second
        meta["frames"] = [int(a), int(b)]
    elif kind == "loop":
        nmin = int(cfg["length"][0] * FPS / rate)
        nmax = int(cfg["length"][1] * FPS / rate)
        _, a, b = best_loop(pts, i_lo, i_hi, nmin, nmax)
        yaw = facing_yaw(pts, np.arange(a, b))
        G, pts = apply_yaw(G, pts, yaw, np.zeros(3))
        N = min(15, (b - a) // 4)
        G = np.stack([crossfade_rot(G[:, s], a, b, N) for s in range(G.shape[1])], 1)
        pts = crossfade_pos(pts, a, b, N)
        feet = 0.5 * (pts[:, PI["ankle_l"]] + pts[:, PI["ankle_r"]])
        c = feet.mean(0) * np.array([1, 1, 0])
        if cfg.get("seat"):
            c = pts[:, PI["hips"]].mean(0) * np.array([1, 1, 0])
        pts = pts - c
        meta["frames"] = [int(a), int(b)]
    else:
        a, b = i_lo, i_hi + 1
        G, pts = G[a:b], pts[a:b]
        n0 = min(len(G), int(0.4 * FPS))
        ref = cfg.get("face", "start")
        frames = np.arange(n0) if ref == "start" else (np.arange(len(G) - n0, len(G)) if ref == "end" else np.arange(len(G)))
        yaw = facing_yaw(pts, frames)
        G, pts = apply_yaw(G, pts, yaw, np.zeros(3))
        feet = 0.5 * (pts[:n0, PI["ankle_l"]] + pts[:n0, PI["ankle_r"]])
        c = feet.mean(0) * np.array([1, 1, 0])
        if cfg.get("seat") == "up":
            c = pts[:n0, PI["hips"]].mean(0) * np.array([1, 1, 0])
        pts = pts - c
        meta["frames"] = [int(a), int(b)]

    if cfg.get("legs"):
        G, pts = graft_legs(G, pts, cfg)

    if cfg.get("mirror"):
        G, pts = mirror(G, pts)
    v_ground = (0.0, meta["speed_leg"], 0.0) if kind == "loco" else None
    contact = contacts(pts, L, v_ground)
    ref = None
    if cfg.get("foot_ref"):
        r0, r1 = cfg["foot_ref"]
        _, Pr, _ = sample_take(take, r0, r1, 1.0, cfg.get("smooth", 0.7))
        pr = floor_normalize(points(Pr, take, cal), L, slice(None))
        ref = flat_pitch(pr, contacts(pr, L))
    meta["foot_delta"] = foot_correction(G, pts, cal, contact, ref)

    G, hp, hr = head_fix(G, cfg, kind)
    meta["head_fix"] = [round(hp, 1), round(hr, 1)]

    if cfg.get("upper"):
        G, wr = graft_upper(G, cfg, len(G))
        pts[:, PI["wrist_l"]] = wr[:, 0]
        pts[:, PI["wrist_r"]] = wr[:, 1]
        meta["hands"] = cfg.get("hands", "")

    if cfg.get("turn"):
        lat = pts[:, PI["hip_l"]] - pts[:, PI["hip_r"]]
        lat2 = pts[:, PI["shoulder_l"]] - pts[:, PI["shoulder_r"]]
        v = lat / np.linalg.norm(lat, axis=1, keepdims=True) + 0.5 * lat2 / np.linalg.norm(lat2, axis=1, keepdims=True)
        yaw = np.unwrap(np.arctan2(v[:, 1], v[:, 0]))
        yaw = smooth_time(yaw - yaw[0], 4.0)
        # make the clip turn exactly cfg['turn'] degrees: spread the difference over the turn
        k = np.radians(cfg["turn"]) / np.mean(yaw[-4:])
        if 0.7 < k < 1.3:
            corr = yaw * (k - 1)
            piv = 0.5 * (pts[0, PI["ankle_l"]] + pts[0, PI["ankle_r"]]) * np.array([1, 1, 0])
            Rq = ab.mat_to_quat(np.stack([rz(c) for c in corr]))
            G = ab.quat_mul(Rq[:, None, :], G)
            pts = np.einsum("fij,fpj->fpi", np.stack([rz(c) for c in corr]), pts - piv) + piv
            yaw = yaw * k
        meta["turn_deg"] = float(np.degrees(yaw[-1]))
        meta["root_yaw"] = yaw.tolist()

    seat = cfg.get("seat")
    if seat:
        hz = pts[:, PI["hips"], 2]
        meta["seat"] = seat if isinstance(seat, str) else "sit"
        meta["hips_z_src"] = [float(hz.min()), float(hz.max())]

    if kind in ("loop", "loco"):
        # duplicate frame 0 at the end so the loop length is exactly n frames
        G = np.concatenate([G, G[:1]], 0)
        pts = np.concatenate([pts, pts[:1]], 0)
        if "root_yaw" in meta:
            meta["root_yaw"].append(meta["root_yaw"][0])
    contact = contacts(pts, L, v_ground)
    meta["nframes"] = len(G)
    meta["duration"] = (len(G) - 1) / FPS
    meta["prep_seconds"] = round(time.time() - t_start, 2)
    return {"meta": meta, "G": ab.quat_continuity(G, 0).astype(np.float32), "pts": pts.astype(np.float32),
            "contact": contact.astype(np.float32)}


LOWER_SEGS = ["pelvis", "thigh_l", "calf_l", "foot_l", "ball_l", "thigh_r", "calf_r", "foot_r", "ball_r"]
LOWER_PTS = ["hips", "hip_l", "hip_r", "ankle_l", "ankle_r", "toe_l", "toe_r"]


def graft_legs(G, pts, cfg):
    """Replace pelvis + legs with a calm stance from another take (e.g. a gesture captured with a wide stance)."""
    take, start = cfg["legs"]
    cal = calibration(take)
    n = len(G)
    W, P, _ = sample_take(take, start, start + (n - 1) / FPS, 1.0, cfg.get("smooth", 0.7))
    Gb = canonical(W, take, cal)[:n]
    pb = floor_normalize(points(P, take, cal), cal["L"], slice(None))[:n]
    Gb, pb = apply_yaw(Gb, pb, facing_yaw(pb, np.arange(len(pb))), np.zeros(3))
    feet = 0.5 * (pb[:, PI["ankle_l"]] + pb[:, PI["ankle_r"]]).mean(0) * np.array([1, 1, 0])
    pb = pb - feet
    G, pts = G.copy(), pts.copy()
    # keep the upper body attached: shift its points by the hips difference
    dh = pb[:, PI["hips"]] - pts[:, PI["hips"]]
    for k in ac.POINTS:
        if k in LOWER_PTS:
            pts[:, PI[k]] = pb[:, PI[k]]
        else:
            pts[:, PI[k]] += dh
    for seg in LOWER_SEGS:
        G[:, SI[seg]] = Gb[:, SI[seg]]
    return ab.quat_continuity(G, 0), pts


def graft_upper(G, cfg, n):
    """Replace the upper body with a loop of the same length cut from another take (e.g. typing)."""
    take, start = cfg["upper"]
    cal = calibration(take)
    bvh = load_src(take)
    dur = bvh.nframes / bvh.fps
    W, P, _ = sample_take(take, start, min(dur - 0.05, start + 30.0), 1.0, cfg.get("smooth", 0.7))
    Gu = canonical(W, take, cal)
    pu = points(P, take, cal) / cal["L"]
    feat = pose_features(pu)[:, :len(ac.POINTS) * 3]
    upper_pts = [PI[k] for k in ("wrist_l", "wrist_r", "elbow_l", "elbow_r", "head")]
    cols = np.concatenate([[3 * i, 3 * i + 1, 3 * i + 2] for i in upper_pts])
    f = feat[:, cols]
    best = (1e18, 0)
    for a in range(16, len(Gu) - n - 1):
        d = np.sum((f[a + n] - f[a]) ** 2)
        if d < best[0]:
            best = (d, a)
    a = best[1]
    yaw = facing_yaw(pu, np.arange(a, a + n))
    Gu, pu = apply_yaw(Gu, pu, yaw, np.zeros(3))
    N = min(12, n // 4)
    Gu = np.stack([crossfade_rot(Gu[:, s], a, a + n, N) for s in range(Gu.shape[1])], 1)
    wr = crossfade_pos(pu[:, [PI["wrist_l"], PI["wrist_r"]]], a, a + n, N)
    wr = wr - wr.mean(0, keepdims=True)  # wrist motion around its mean (leg lengths)
    G = G.copy()
    for seg, w in (("spine_02", 0.5), ("spine_03", 1.0), ("neck_01", 1.0), ("head", 1.0),
                   ("clavicle_l", 1), ("upperarm_l", 1), ("lowerarm_l", 1), ("hand_l", 1),
                   ("clavicle_r", 1), ("upperarm_r", 1), ("lowerarm_r", 1), ("hand_r", 1)):
        s = SI[seg]
        G[:, s] = ab.quat_slerp(G[:, s], Gu[:n, s], w)
    return G, wr


# ---------------------------------------------------------------------- cache io
def _enc(a):
    a = np.ascontiguousarray(a, dtype=np.float32)
    return {"shape": list(a.shape), "b64": base64.b64encode(a.tobytes()).decode("ascii")}


def _dec(d):
    return np.frombuffer(base64.b64decode(d["b64"]), dtype=np.float32).reshape(d["shape"])


def clip_key(name, cfg):
    takes = [cfg["src"]] + ([cfg["upper"][0]] if cfg.get("upper") else [])
    sk = ac.skeleton_of(load_src(cfg["src"]))
    if ac.SKELETONS[sk]["calib"] == "axes":
        takes += [r[0] for r in ac.SKELETONS[sk]["ref"]]
    blob = json.dumps({"v": PREP_VERSION, "cfg": cfg, "src": [file_sig(t) for t in takes],
                       "sk": ac.SKELETONS[sk]}, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def cache_path(name):
    return os.path.join(CACHE_DIR, name + ".json")


def load_cached(name):
    with open(cache_path(name)) as f:
        d = json.load(f)
    return {"meta": d["meta"], "G": _dec(d["G"]), "pts": _dec(d["pts"]), "contact": _dec(d["contact"]), "key": d.get("key")}


def ensure(names=None, force=False):
    """Build missing / outdated caches. Returns {name: clip dict}."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    names = list(ac.CLIPS) if names is None else list(names)
    out = {}
    for n in names:
        cfg = ac.CLIPS[n]
        key = clip_key(n, cfg)
        p = cache_path(n)
        if not force and os.path.exists(p):
            try:
                d = load_cached(n)
                if d.get("key") == key:
                    out[n] = d
                    continue
            except Exception:
                pass
        d = prepare(n, cfg)
        d["key"] = key
        with open(p, "w") as f:
            json.dump({"key": key, "meta": d["meta"], "G": _enc(d["G"]), "pts": _enc(d["pts"]),
                       "contact": _enc(d["contact"])}, f)
        m = d["meta"]
        log(f"{n:12s} <- {m['src']} frames {m['frames']} n={m['nframes']} ({m['duration']:.2f}s)"
            + (f" speed {m['speed_leg']:.3f} leg/s" if "speed_leg" in m else "") + f" [{m['prep_seconds']}s]")
        out[n] = d
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    ensure(args or None, force="--force" in sys.argv)
