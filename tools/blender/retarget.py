"""Retarget the mocap clip library onto an MPFB `game_engine` armature (any body proportions).

    import retarget
    retarget.apply(rig)                    # all clips in anim_clips.CLIPS -> one Blender action per clip
    retarget.apply(rig, ["idle", "walk"])  # a subset

How it works
  * anim_prep.py turns each BVH take once into a skeleton-independent clip (cached in assets/anims/cache):
    per body segment the world rotation relative to a canonical T-pose, plus joint positions in leg lengths.
  * Here every target bone gets   world(f) = G_segment(f) @ T_target   where T_target is the bone's rest frame
    moved into the same canonical T-pose (rest-pose compensation: A-pose arms swung up, elbows unbent, legs
    straightened, palms down). Hips height / stride are scaled by the target/source leg-length ratio.
  * Legs are then solved with analytic two-bone IK onto the scaled source ankles, with contact locking
    (planted feet do not slide) and a ground clamp; arms are pushed out of the torso; forearm twist is spread
    between hand and forearm; fingers get a relaxed curl. Sitting clips are put on a 0.45 m seat whose
    front edge is the root; `typing` puts the hands on a desk (top 0.74 m).
  * Actions are written with foreach_set (30 fps, loops have last key == first key). Locomotion is in place.
The scene fps is set to 30 so the glTF exporter samples the actions correctly.
"""
import os, sys, time, math
import numpy as np
import bpy

np.seterr(all="ignore")  # numpy 1.26 + Accelerate raises spurious matmul FP warnings on macOS

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import importlib
import anim_bvh as ab
import anim_clips as ac
import anim_prep as ap
for _m in (ab, ac, ap):
    importlib.reload(_m)

FPS = 30
SEAT_HEIGHT = 0.45      # chair seat surface (m); the seat front edge is at the root
KNEE_FRONT = -0.10      # seated knee joint position along -Y (in front of the seat edge)
DESK = {"z": 0.765, "y": -0.02, "x": 0.13}   # wrist targets for typing (desk top ~0.74 m)
FINGER_CURL = {  # degrees at fingers=1.0 for (01, 02, 03)
    "thumb": (4, 14, 14), "index": (22, 34, 22), "middle": (27, 40, 24), "ring": (31, 44, 25), "pinky": (35, 46, 26)}
FOREARM_TWIST = 0.6     # share of the hand's twist (about the forearm) carried by the forearm bone

SEG_SET = set(ac.SEGMENTS)
DEBUG = {}              # diagnostics of the last solve() (ankle targets, arm pushes)
PI = ap.PI
SI = ap.SI


def log(*a):
    print("[retarget]", *a, flush=True)


# ---------------------------------------------------------------------- math helpers (numpy, batched)
def nrm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def rot_axis_angle(axis, ang):
    """(..., 3) axes, (...) angles -> (..., 3, 3)."""
    axis = nrm(axis)
    x, y, z = axis[..., 0], axis[..., 1], axis[..., 2]
    c, s = np.cos(ang), np.sin(ang)
    C = 1 - c
    return np.stack([np.stack([c + x * x * C, x * y * C - z * s, x * z * C + y * s], -1),
                     np.stack([y * x * C + z * s, c + y * y * C, y * z * C - x * s], -1),
                     np.stack([z * x * C - y * s, z * y * C + x * s, c + z * z * C], -1)], -2)


def swing(a, b):
    return ab.swing_to(a, b)


def mT(m):
    return np.swapaxes(m, -1, -2)


# ---------------------------------------------------------------------- target rig description
class Target:
    def __init__(self, rig):
        self.rig = rig
        bones = list(rig.data.bones)
        self.names = [b.name for b in bones]
        self.idx = {n: i for i, n in enumerate(self.names)}
        self.parent = np.array([self.idx[b.parent.name] if b.parent else -1 for b in bones])
        self.R = np.array([np.array(b.matrix_local, float)[:3, :3] for b in bones])
        self.head = np.array([np.array(b.head_local, float) for b in bones])
        self.tail = np.array([np.array(b.tail_local, float) for b in bones])
        order, seen = [], set()

        def visit(i):
            if i in seen:
                return
            if self.parent[i] >= 0:
                visit(self.parent[i])
            seen.add(i)
            order.append(i)
        for i in range(len(bones)):
            visit(i)
        self.order = order
        for need in ac.SEGMENTS + ["Root"]:
            if need not in self.idx:
                raise ValueError(f"rig {rig.name} has no bone {need}: not an MPFB game_engine skeleton")
        i = self.idx
        H = self.head
        self.l_thigh = np.mean([np.linalg.norm(H[i["calf_" + s]] - H[i["thigh_" + s]]) for s in "lr"])
        self.l_calf = np.mean([np.linalg.norm(H[i["foot_" + s]] - H[i["calf_" + s]]) for s in "lr"])
        self.leg = self.l_thigh + self.l_calf
        self.ankle_z = np.mean([H[i["foot_" + s]][2] for s in "lr"])
        self.hips_mid = 0.5 * (H[i["thigh_l"]] + H[i["thigh_r"]])
        self.canonical()
        self.fingers()
        self.torso_profile()

    def dir(self, b, child=None):
        i = self.idx
        end = self.head[i[child]] if child else self.tail[i[b]]
        return nrm(end - self.head[i[b]])

    def canonical(self):
        """T[b]: armature-space rotation of bone b with the rig posed in the canonical T-pose."""
        i, R = self.idx, self.R
        T = {n: R[i[n]].copy() for n in ac.SEGMENTS}
        for s in "lr":
            sign = 1.0 if s == "l" else -1.0
            lat = np.array([sign, 0, 0])
            for b, c in (("thigh_", "calf_"), ("calf_", "foot_")):
                T[b + s] = swing(self.dir(b + s, c + s), np.array([0, 0, -1.0])) @ R[i[b + s]]
            ua, la, ha = "upperarm_" + s, "lowerarm_" + s, "hand_" + s
            du, dl = self.dir(ua, la), self.dir(la, ha)
            Su = swing(du, lat)
            hinge = np.cross(du, dl)
            ang = math.atan2(np.linalg.norm(hinge), float(np.dot(du, dl)))
            unbend = rot_axis_angle(hinge, -ang) if ang > 1e-4 else np.eye(3)
            T[ua] = Su @ R[i[ua]]
            T[la] = Su @ unbend @ R[i[la]]
            T[ha] = T[la] @ R[i[la]].T @ R[i[ha]]
            # palm must face down in the canonical pose: fix the forearm/hand twist if the rest pose disagrees
            n_rest = self.palm_normal(s)
            n_can = (T[ha] @ R[i[ha]].T) @ n_rest
            n_proj = nrm(n_can - np.dot(n_can, lat) * lat)
            tw = math.atan2(float(np.dot(np.cross(n_proj, np.array([0, 0, -1.0])), lat)), float(np.dot(n_proj, [0, 0, -1.0])))
            self.palm_twist = getattr(self, "palm_twist", {})
            self.palm_twist[s] = math.degrees(tw)
            if abs(tw) > math.radians(4):
                Rt = rot_axis_angle(lat, tw)
                T[la] = Rt @ T[la]
                T[ha] = Rt @ T[ha]
        self.T = T

    def palm_normal(self, s):
        i, H = self.idx, self.head
        u = nrm(H[i["middle_01_" + s]] - H[i["hand_" + s]])
        t = nrm(H[i["index_01_" + s]] - H[i["pinky_01_" + s]])
        return nrm(np.cross(u, t) if s == "l" else np.cross(t, u))

    def fingers(self):
        """Curl axis sign per finger bone (local X flexes towards the palm when the sign is +1)."""
        self.finger_bones = []
        for s in "lr":
            n = self.palm_normal(s)
            for f in FINGER_CURL:
                for k in (1, 2, 3):
                    b = f"{f}_0{k}_{s}"
                    if b not in self.idx:
                        continue
                    Rb = self.R[self.idx[b]]
                    # rotating about local X moves the bone's Y towards its Z: curl if Z points out of the palm
                    sign = 1.0 if np.dot(Rb[:, 2], n) > 0 else -1.0
                    self.finger_bones.append((b, f, k, sign))

    def torso_profile(self):
        """Elliptic torso cross-sections (half width, half depth, centre y) by height, from the skinned meshes."""
        rig = self.rig
        groups = {"pelvis", "spine_01", "spine_02", "spine_03"}
        pts = []
        for ob in rig.children:
            if ob.type != 'MESH' or not any(m.type == 'ARMATURE' for m in ob.modifiers):
                continue
            kind = ob.get("kind", "")
            if kind not in ("skin", "cloth", ""):
                continue
            vg = {g.index: g.name for g in ob.vertex_groups}
            if not groups & set(vg.values()):
                continue
            mw = np.linalg.inv(np.array(rig.matrix_world)) @ np.array(ob.matrix_world)
            co = np.empty(len(ob.data.vertices) * 3)
            ob.data.vertices.foreach_get("co", co)
            with np.errstate(all="ignore"):
                co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
            for v, p in zip(ob.data.vertices, co):
                best, bw = None, 0.0
                for g in v.groups:
                    if g.weight > bw:
                        best, bw = vg.get(g.group), g.weight
                if best in groups and bw > 0.45:
                    pts.append(p)
        self.torso = None
        if len(pts) < 50:
            return
        pts = np.array(pts)
        z0, z1 = self.head[self.idx["pelvis"]][2] - 0.12, self.head[self.idx["neck_01"]][2]
        zs = np.linspace(z0, z1, 12)
        prof = []
        for k in range(len(zs) - 1):
            sel = pts[(pts[:, 2] >= zs[k]) & (pts[:, 2] < zs[k + 1])]
            if len(sel) < 10:
                prof.append(prof[-1] if prof else (0.15, 0.1, 0.0))
                continue
            hw = np.percentile(np.abs(sel[:, 0]), 98)
            y0, y1 = np.percentile(sel[:, 1], [2, 98])
            prof.append((hw, (y1 - y0) / 2, (y1 + y0) / 2))
        self.torso = {"z": 0.5 * (zs[1:] + zs[:-1]), "prof": np.array(prof)}


# ---------------------------------------------------------------------- forward kinematics on the target
def fk_heads(tg, W, pelvis_pos):
    """Bone head positions (F, B, 3) from world rotations W (F, B, 3, 3) and the pelvis head position."""
    F = W.shape[0]
    Hd = np.zeros((F, len(tg.names), 3))
    for b in tg.order:
        p = tg.parent[b]
        if p < 0:
            Hd[:, b] = tg.head[b]
        elif tg.names[b] == "pelvis":
            Hd[:, b] = pelvis_pos
        else:
            off = tg.R[p].T @ (tg.head[b] - tg.head[p])
            Hd[:, b] = Hd[:, p] + np.einsum("fij,j->fi", W[:, p], off)
    return Hd


def child_offset(tg, parent, child):
    return tg.R[tg.idx[parent]].T @ (tg.head[tg.idx[child]] - tg.head[tg.idx[parent]])


# ---------------------------------------------------------------------- per-clip solve
def solve(tg, clip):
    """World rotations (F, B, 3, 3), pelvis head positions (F, 3) and extra local rotations (fingers, Root)."""
    DEBUG.clear()
    meta, G, pts, contact = clip["meta"], clip["G"].astype(float), clip["pts"].astype(float), clip["contact"] > 0.5
    F = len(G)
    nb = len(tg.names)
    i = tg.idx
    L = tg.leg
    W = np.tile(np.eye(3), (F, nb, 1, 1))
    Gm = ab.quat_to_mat(G)                     # (F, S, 3, 3)
    for s, seg in enumerate(ac.SEGMENTS):
        W[:, i[seg]] = Gm[:, s] @ tg.T[seg]

    # ---- root yaw (turn clips carry their turn on the Root bone so root motion can extract it)
    root_yaw = np.array(meta["root_yaw"]) if "root_yaw" in meta else None

    # ---- positions: scale by leg length, ankles at the target's flat ankle height
    P = pts * L
    P[..., 2] += tg.ankle_z
    seat = meta.get("seat")
    hips = P[:, PI["hips"]].copy()
    ank = {s: P[:, PI["ankle_" + s]].copy() for s in "lr"}

    if seat:
        hips, ank = seat_remap(tg, meta, W, hips, ank)

    # ---- feet: contact locking and ground clamp (ankle targets)
    for k, s in enumerate("lr"):
        ank[s] = plant_feet(tg, W, s, ank[s], contact[:, 2 * k], contact[:, 2 * k + 1], meta)

    # ---- pelvis head from the hip-joint midpoint
    off = tg.R[i["pelvis"]].T @ (tg.hips_mid - tg.head[i["pelvis"]])
    pelvis_pos = hips - np.einsum("fij,j->fi", W[:, i["pelvis"]], off)

    # ---- standing clips: mocap joint centres often read 20-30 deg of knee bend when people stand straight;
    #      raise the pelvis until the straighter (weight-bearing) leg reaches `straighten` extension
    ext = ac.CLIPS.get(meta["name"], {}).get("straighten")
    if ext:
        needs = []
        for s in "lr":
            th = i["thigh_" + s]
            hip = pelvis_pos + np.einsum("fij,j->fi", W[:, i["pelvis"]], tg.R[i["pelvis"]].T @ (tg.head[th] - tg.head[i["pelvis"]]))
            d = ank[s] - hip
            T = ext * tg.leg
            h2 = np.minimum(np.sum(d[:, :2] ** 2, 1), T * T * 0.999)
            needs.append(d[:, 2] + np.sqrt(T * T - h2))   # raise that makes |d - (0,0,dz)| = T for this leg
        dz = np.clip(np.minimum(needs[0], needs[1]), 0, 0.08)   # the straighter leg reaches T, the other stays bent
        dz = ap.smooth_time(dz, 3.0)
        pelvis_pos = pelvis_pos + dz[:, None] * np.array([0, 0, 1.0])

    # ---- leg IK
    for s in "lr":
        leg_ik(tg, W, pelvis_pos, s, ank[s])
    DEBUG["ank_target"] = ank

    # ---- arms: desk IK for typing, then keep them out of the torso
    if meta.get("hands") == "desk":
        for s in "lr":
            sign = 1 if s == "l" else -1
            tgt = np.array([sign * DESK["x"], DESK["y"], DESK["z"]]) + pts[:, PI["wrist_" + s]] * L * np.array([0.6, 0.6, 0.35])
            arm_ik(tg, W, pelvis_pos, s, tgt)
    arm_collision(tg, W, pelvis_pos)

    # ---- forearm twist distribution
    for s in "lr":
        la, ha = i["lowerarm_" + s], i["hand_" + s]
        rest_rel = tg.R[la].T @ tg.R[ha]
        basis = mT(rest_rel) @ mT(W[:, la]) @ W[:, ha]
        q = ab.mat_to_quat(basis)
        tw = 2 * np.arctan2(q[:, 2], q[:, 0])
        tw = (tw + np.pi) % (2 * np.pi) - np.pi
        W[:, la] = W[:, la] @ rot_axis_angle(np.array([0, 1.0, 0]), FOREARM_TWIST * tw)

    # ---- fingers + Root
    curl = ac.CLIPS.get(meta["name"], {}).get("fingers", 0.5)
    local = {}
    for b, f, k, sign in tg.finger_bones:
        ang = math.radians(FINGER_CURL[f][k - 1] * curl) * sign
        local[b] = rot_axis_angle(np.array([1.0, 0, 0]), ang)
    if root_yaw is not None:
        local["Root"] = rot_axis_angle(np.array([0, 0, 1.0]), root_yaw)[:, :, :]
    return W, pelvis_pos, local


def seat_remap(tg, meta, W, hips, ank):
    """Put seated frames on a SEAT_HEIGHT seat whose front edge is at y=0; keep standing frames as they are."""
    i = tg.idx
    seat_z = SEAT_HEIGHT + tg.seat_offset
    z_src = hips[:, 2]
    z_lo, z_hi = z_src.min(), z_src.max()
    if meta["seat"] == "sit" or (z_hi - z_lo) < 0.15:
        new_z = seat_z + (z_src - np.median(z_src)) * 0.8
        w = np.ones(len(z_src))
    else:
        # linear remap of the hips height: seated level -> seat_z, standing level unchanged
        B = (z_hi - seat_z) / max(z_hi - z_lo, 1e-3)
        new_z = seat_z + (z_src - z_lo) * B
        w = np.clip((z_hi - z_src) / max(z_hi - z_lo, 1e-3), 0, 1)
    hips = hips.copy()
    hips[:, 2] = new_z
    # horizontal: seated knees just in front of the seat edge (thigh direction from the retargeted pose)
    knee_y = []
    for s in "lr":
        th = i["thigh_" + s]
        hip_s = hips + np.einsum("fij,j->fi", W[:, i["pelvis"]], tg.R[i["pelvis"]].T @ (tg.head[th] - tg.hips_mid))
        knee_y.append((hip_s + np.einsum("fij,j->fi", W[:, th], child_offset(tg, "thigh_" + s, "calf_" + s)))[:, 1])
    knee_y = 0.5 * (knee_y[0] + knee_y[1])
    seated = w > 0.9
    if not np.any(seated):
        seated = w >= w.max() - 1e-6
    dy = KNEE_FRONT - np.median(knee_y[seated])
    shift = np.array([0, dy, 0])
    hips = hips + shift
    ank = {s: a + shift for s, a in ank.items()}
    return hips, ank


def plant_feet(tg, W, s, ank, heel_c, toe_c, meta):
    """Ankle targets with planted feet locked (no sliding), toe-pivot on push-off and no ground penetration."""
    i = tg.idx
    fo, ba = i["foot_" + s], i["ball_" + s]
    ank = ank.copy()
    F = len(ank)
    off_ball = tg.R[fo].T @ (tg.head[ba] - tg.head[fo])
    ball_rel = np.einsum("fij,j->fi", W[:, fo], off_ball)                   # ankle -> ball, posed
    tip_rel = ball_rel + np.einsum("fij,j->fi", W[:, ba], tg.R[ba].T @ (tg.tail[ba] - tg.head[ba]))
    heel_rest = np.array([tg.head[fo][0], tg.head[fo][1] + 0.035, 0.012])  # back of the sole
    heel_rel = np.einsum("fij,j->fi", W[:, fo], tg.R[fo].T @ (heel_rest - tg.head[fo]))
    ball_z0, tip_z0 = tg.head[ba][2], tg.tail[ba][2]
    v = np.zeros(3)
    if meta["kind"] == "loco":
        v = np.array([0, meta["speed_leg"] * tg.leg / FPS, 0])   # planted feet slide back on the treadmill
    loop = bool(meta.get("loop"))
    # loops: work on the n unique frames, rolled so the sequence starts in this foot's swing phase
    n = F - 1 if loop else F
    planted = (heel_c | toe_c)[:n]
    roll = 0
    if loop and planted.any() and not planted.all():
        roll = int(np.argmax(~planted))
    idx = (np.arange(n) + roll) % n
    A = ank[idx].copy()
    hc, tc = heel_c[idx], toe_c[idx]
    br = ball_rel[idx]
    toe_only = tc & ~hc
    heel_only = hc & ~tc
    # 1) toe pivot: when only the toes touch, the ball sits on the ground
    w_toe = ap.smooth_time(toe_only.astype(float), 0.8)
    A[:, 2] = A[:, 2] * (1 - w_toe) + (ball_z0 - br[:, 2]) * w_toe
    # 2) lock the pivot (ball whenever the toes are down, ankle during heel strike) at full strength during the
    #    contact; ease the correction in/out over 3 frames outside it so there are no pops
    corr = np.zeros((n, 3))
    inside = np.zeros(n, bool)
    E = 3
    for mask, use_ball in ((heel_only, False), (tc, True)):
        for a, b in ap.runs(mask):
            m = b - a
            if m < 2:
                continue
            t = np.arange(m)[:, None]
            piv = A[a:b] + (br[a:b] if use_ball else 0)
            want = np.median(piv - t * v, 0) + t * v
            fix = want - piv
            fix[:, 2] = 0
            corr[a:b] = fix
            inside[a:b] = True
            for k in range(1, E + 1):
                w = smoothstep(1 - k / (E + 1))
                if a - k >= 0 and not inside[a - k]:
                    corr[a - k] = fix[0] * w
                if b - 1 + k < n and not mask[b - 1 + k]:
                    corr[b - 1 + k] = fix[-1] * w
    A = A + corr
    out = np.empty_like(ank)
    out[idx] = A          # in-place loops are periodic: positions are continuous across the seam
    if loop:
        out[-1] = out[0]
    ank = out
    # 3) ground: heel, ball and toe tip never below their rest heights
    low = np.minimum.reduce([ank[:, 2] + heel_rel[:, 2] - heel_rest[2],
                             ank[:, 2] + ball_rel[:, 2] - ball_z0,
                             ank[:, 2] + tip_rel[:, 2] - tip_z0])
    lift = np.maximum(0, -low)
    lift = np.maximum(lift, ap.smooth_time(lift, 1.0))
    if meta.get("seat"):
        # seated: a resting foot always touches the floor (no chair rungs / footrests assumed)
        spd = np.zeros(F)
        spd[1:] = np.linalg.norm(np.diff(ank[:, :2], axis=0), axis=1) * FPS
        rest = ap.smooth_time((spd < 0.12).astype(float), 2.0)
        gap = np.clip(low, 0, 0.15)
        lift = lift - ap.smooth_time(gap * rest, 2.0)
    ank[:, 2] += lift
    return ank


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def leg_ik(tg, W, pelvis_pos, s, target):
    """Two-bone IK (thigh, calf) to put the ankle at `target`, keeping the knee's swivel direction."""
    i = tg.idx
    th, ca, fo, pe = i["thigh_" + s], i["calf_" + s], i["foot_" + s], i["pelvis"]
    hip = pelvis_pos + np.einsum("fij,j->fi", W[:, pe], tg.R[pe].T @ (tg.head[th] - tg.head[pe]))
    off_k = tg.R[th].T @ (tg.head[ca] - tg.head[th])
    off_a = tg.R[ca].T @ (tg.head[fo] - tg.head[ca])
    l1, l2 = np.linalg.norm(off_k), np.linalg.norm(off_a)
    knee0 = hip + np.einsum("fij,j->fi", W[:, th], off_k)
    ank0 = knee0 + np.einsum("fij,j->fi", W[:, ca], off_a)
    d = target - hip
    D = np.linalg.norm(d, axis=1)
    # soft limit near full extension so knees never pop straight
    Dmax = (l1 + l2)
    soft = 0.996 * Dmax
    over = D > soft
    D2 = np.where(over, soft + (Dmax - soft) * (1 - np.exp(-(D - soft) / ((Dmax - soft) + 1e-9))), D)
    D2 = np.clip(D2, abs(l1 - l2) + 1e-4, Dmax - 1e-5)
    dn = d / np.maximum(D[:, None], 1e-9)
    # pole: current knee offset perpendicular to the hip->target line (fallback: forward)
    pole = knee0 - hip
    pole = pole - np.sum(pole * dn, 1, keepdims=True) * dn
    bad = np.linalg.norm(pole, axis=1) < 1e-4
    if np.any(bad):
        fwd = np.einsum("fij,j->fi", W[:, pe], tg.R[pe].T @ np.array([0, -1.0, 0]))
        pole[bad] = fwd[bad] - np.sum(fwd[bad] * dn[bad], 1, keepdims=True) * dn[bad]
    pole = nrm(pole)
    cos_a = np.clip((l1 * l1 + D2 * D2 - l2 * l2) / (2 * l1 * D2), -1, 1)
    sin_a = np.sqrt(1 - cos_a ** 2)
    knee = hip + dn * (l1 * cos_a)[:, None] + pole * (l1 * sin_a)[:, None]
    ank = hip + dn * D2[:, None]
    W[:, th] = swing(knee0 - hip, knee - hip) @ W[:, th]
    knee1 = hip + np.einsum("fij,j->fi", W[:, th], off_k)
    cur = np.einsum("fij,j->fi", W[:, ca], off_a)
    W[:, ca] = swing(cur, ank - knee1) @ W[:, ca]


def arm_ik(tg, W, pelvis_pos, s, target):
    """Two-bone IK for the arm (wrist at target), keeping the elbow swivel; hand world rotation unchanged."""
    i = tg.idx
    ua, la, ha = i["upperarm_" + s], i["lowerarm_" + s], i["hand_" + s]
    Hd = fk_heads(tg, W, pelvis_pos)
    sh = Hd[:, ua]
    off_e = tg.R[ua].T @ (tg.head[la] - tg.head[ua])
    off_w = tg.R[la].T @ (tg.head[ha] - tg.head[la])
    l1, l2 = np.linalg.norm(off_e), np.linalg.norm(off_w)
    el0 = sh + np.einsum("fij,j->fi", W[:, ua], off_e)
    d = target - sh
    D = np.clip(np.linalg.norm(d, axis=1), abs(l1 - l2) + 1e-3, (l1 + l2) * 0.995)
    dn = nrm(d)
    pole = el0 - sh
    pole = nrm(pole - np.sum(pole * dn, 1, keepdims=True) * dn)
    cos_a = np.clip((l1 * l1 + D * D - l2 * l2) / (2 * l1 * D), -1, 1)
    el = sh + dn * (l1 * cos_a)[:, None] + pole * (l1 * np.sqrt(1 - cos_a ** 2))[:, None]
    wr = sh + dn * D[:, None]
    W[:, ua] = swing(el0 - sh, el - sh) @ W[:, ua]
    el1 = sh + np.einsum("fij,j->fi", W[:, ua], off_e)
    W[:, la] = swing(np.einsum("fij,j->fi", W[:, la], off_w), wr - el1) @ W[:, la]


def arm_collision(tg, W, pelvis_pos, margin=0.035):
    """Rotate upper arms outwards (about the chest's forward axis) when elbows / forearms sink into the torso."""
    if tg.torso is None:
        return
    i = tg.idx
    prof = tg.torso
    F = W.shape[0]
    for it in range(3):
        Hd = fk_heads(tg, W, pelvis_pos)
        chest = W[:, i["spine_03"]] @ tg.R[i["spine_03"]].T     # chest rotation relative to rest
        pel = W[:, i["pelvis"]] @ tg.R[i["pelvis"]].T
        c_piv, p_piv = Hd[:, i["spine_03"]], Hd[:, i["pelvis"]]
        for s in "lr":
            sign = 1 if s == "l" else -1
            ua, la, ha = i["upperarm_" + s], i["lowerarm_" + s], i["hand_" + s]
            sh = Hd[:, ua]
            fwd = np.einsum("fij,j->fi", chest, np.array([0, -1.0, 0]))
            ang = np.zeros(F)
            worst = 0.0
            for a, b, t in ((ua, la, 0.6), (la, None, 0.0), (la, ha, 0.5), (ha, None, 0.0)):
                p = Hd[:, a] if b is None else Hd[:, a] * (1 - t) + Hd[:, b] * t
                # express in the torso's rest frame (blend of pelvis and chest orientation by height)
                loc_c = np.einsum("fji,fj->fi", chest, p - c_piv) + tg.head[i["spine_03"]]
                loc_p = np.einsum("fji,fj->fi", pel, p - p_piv) + tg.head[i["pelvis"]]
                zc = np.clip((loc_c[:, 2] - prof["z"][0]) / (prof["z"][-1] - prof["z"][0]), 0, 1)
                loc = loc_p * (1 - zc[:, None]) + loc_c * zc[:, None]
                hw = np.interp(loc[:, 2], prof["z"], prof["prof"][:, 0])
                hd = np.interp(loc[:, 2], prof["z"], prof["prof"][:, 1])
                yc = np.interp(loc[:, 2], prof["z"], prof["prof"][:, 2])
                inside_z = (loc[:, 2] > prof["z"][0] - 0.05) & (loc[:, 2] < prof["z"][-1])
                # ellipse test, then the lateral push needed to get out
                ny = np.clip((loc[:, 1] - yc) / (hd + margin), -1, 1)
                need_x = (hw + margin) * np.sqrt(np.maximum(0, 1 - ny ** 2))
                px = np.where(inside_z & (np.abs(loc[:, 1] - yc) < hd + margin), need_x - sign * loc[:, 0], 0.0)
                px = np.maximum(px, 0)
                worst = max(worst, float(px.max()))
                # abduction angle that moves this point out by px: lever = distance from the shoulder across the axis
                r = p - sh
                r = r - np.sum(r * fwd, 1, keepdims=True) * fwd
                lever = np.maximum(np.linalg.norm(r, axis=1), 0.08)
                ang = np.maximum(ang, np.arcsin(np.clip(px / lever, 0, 0.9)))
            if worst < 1e-4:
                continue
            DEBUG.setdefault("arm_push", []).append((s, int((ang > 1e-3).sum()), round(worst, 4)))
            ang = ap.smooth_time(ang * 1.1, 1.5)
            Rm = rot_axis_angle(fwd * sign, ang)            # rotate the arm outward about the forward axis
            for b in (ua,):
                W[:, b] = Rm @ W[:, b]
            # forearm and hand keep their own world orientation except for the carried swing
            W[:, la] = Rm @ W[:, la]
            W[:, ha] = Rm @ W[:, ha]


# ---------------------------------------------------------------------- seat measurement
def measure_seat_offset(tg):
    """Distance from the hip joints down to the bottom of the buttocks/thighs when seated, from the meshes."""
    rig = tg.rig
    i = tg.idx
    pb = rig.pose.bones
    saved = {b.name: (b.rotation_mode, tuple(b.rotation_quaternion), tuple(b.rotation_euler), tuple(b.location)) for b in pb}
    act = rig.animation_data.action if rig.animation_data else None
    if rig.animation_data:
        rig.animation_data.action = None
    for b in pb:
        b.rotation_mode = 'QUATERNION'
        b.rotation_quaternion = (1, 0, 0, 0)
        b.location = (0, 0, 0)
    from mathutils import Matrix
    for s in "lr":
        b = pb["thigh_" + s]
        # flex the hip 90 degrees about the world X axis, expressed in the bone's local frame
        Rl = tg.R[i["thigh_" + s]]
        world = rot_axis_angle(np.array([1.0, 0, 0]), math.radians(-88))
        loc = Rl.T @ world @ Rl
        q = ab.mat_to_quat(loc)
        b.rotation_quaternion = tuple(q)
        c = pb["calf_" + s]
        Rc = tg.R[i["calf_" + s]]
        # bend knee back by 90 degrees (relative), so the shin hangs down
        world_c = rot_axis_angle(np.array([1.0, 0, 0]), math.radians(88))
        c.rotation_quaternion = tuple(ab.mat_to_quat(Rc.T @ world_c @ Rc))
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    hz = tg.hips_mid[2]
    knee_y = tg.hips_mid[1] - tg.l_thigh          # thighs point forward (-Y) in the test pose
    lows = []
    for ob in rig.children:
        if ob.type != 'MESH' or not any(m.type == 'ARMATURE' for m in ob.modifiers):
            continue
        if ob.get("kind", "") not in ("skin", "cloth", ""):
            continue
        # only buttock / thigh vertices (dominant weight on pelvis or thighs), not shins or shoes
        vg = {g.index: g.name for g in ob.vertex_groups}
        keep = np.zeros(len(ob.data.vertices), bool)
        for v in ob.data.vertices:
            best, bw = None, 0.0
            for g in v.groups:
                if g.weight > bw:
                    best, bw = vg.get(g.group), g.weight
            keep[v.index] = best in ("pelvis", "thigh_l", "thigh_r")
        if not keep.any():
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        mw = np.linalg.inv(np.array(rig.matrix_world)) @ np.array(ob.matrix_world)
        with np.errstate(all="ignore"):
            co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
        if len(co) != len(keep):
            continue
        sel = co[keep & (co[:, 1] > knee_y + 0.06) & (co[:, 2] < hz) & (co[:, 2] > hz - 0.3)]
        if len(sel):
            lows.append(np.percentile(sel[:, 2], 0.5))
    for b in pb:
        m, q, e, l = saved[b.name]
        b.rotation_mode = m
        b.rotation_quaternion = q
        b.rotation_euler = e
        b.location = l
    if rig.animation_data:
        rig.animation_data.action = act
    bpy.context.view_layer.update()
    if not lows:
        return 0.10
    return float(np.clip(hz - min(lows), 0.05, 0.2))


# ---------------------------------------------------------------------- action output
def to_local(tg, W, pelvis_pos, local_extra):
    """World rotations -> pose-bone basis quaternions (F, B, 4) and pelvis location (F, 3)."""
    F = W.shape[0]
    nb = len(tg.names)
    i = tg.idx
    Wf = W.copy()
    # unmapped bones (fingers, Root): world from parent + rest relation + extra local rotation
    for b in tg.order:
        n = tg.names[b]
        if n in SEG_SET:
            continue
        p = tg.parent[b]
        loc = local_extra.get(n)
        rest_rel = tg.R[b] if p < 0 else tg.R[p].T @ tg.R[b]
        if p < 0:
            Wf[:, b] = rest_rel if loc is None else rest_rel @ loc
        else:
            Wf[:, b] = Wf[:, p] @ rest_rel if loc is None else Wf[:, p] @ rest_rel @ loc
    Q = np.zeros((F, nb, 4))
    for b in range(nb):
        p = tg.parent[b]
        if p < 0:
            basis = tg.R[b].T @ Wf[:, b]
        else:
            basis = tg.R[b].T @ tg.R[p] @ mT(Wf[:, p]) @ Wf[:, b]
        Q[:, b] = ab.quat_continuity(ab.mat_to_quat(basis), 0)
    # pelvis location relative to its parent (Root)
    pe, ro = i["pelvis"], i["Root"]
    rel = np.einsum("fji,fj->fi", Wf[:, ro], pelvis_pos - tg.head[ro])        # W_root^T (p - root head)
    t = (tg.R[pe].T @ (tg.R[ro] @ rel.T)).T - (tg.R[pe].T @ (tg.head[pe] - tg.head[ro]))
    return Q, t


def write_action(rig, name, tg, Q, t_pelvis, loop):
    act = bpy.data.actions.get(name)
    if act is not None:
        bpy.data.actions.remove(act)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    if rig.animation_data is None:
        rig.animation_data_create()
    rig.animation_data.action = act
    F = Q.shape[0]
    frames = np.arange(F, dtype=np.float32)

    def put(path, idx, vals, group):
        if hasattr(act, "fcurve_ensure_for_datablock"):
            fc = act.fcurve_ensure_for_datablock(rig, path, index=idx)
        else:
            fc = act.fcurves.new(path, index=idx, action_group=group)
        fc.keyframe_points.add(F)
        co = np.empty(2 * F, dtype=np.float32)
        co[0::2] = frames
        co[1::2] = vals
        fc.keyframe_points.foreach_set("co", co)
        fc.keyframe_points.foreach_set("interpolation", np.ones(F, dtype=np.int32))  # LINEAR
        fc.update()

    for b, n in enumerate(tg.names):
        path = f'pose.bones["{n}"].rotation_quaternion'
        for k in range(4):
            put(path, k, Q[:, b, k], n)
    for k in range(3):
        put('pose.bones["pelvis"].location', k, t_pelvis[:, k], "pelvis")
    act.use_frame_range = True
    act.frame_start = 0
    act.frame_end = F - 1
    act.use_cyclic = bool(loop)
    act["loop"] = bool(loop)
    return act


# ---------------------------------------------------------------------- entry point
def apply(rig, clips=None, verbose=True):
    """Create one action per clip on `rig` (an MPFB game_engine armature object). Returns {clip: action}."""
    t0 = time.time()
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    names = list(ac.CLIPS) if clips is None else list(clips)
    data = ap.ensure(names)
    t1 = time.time()
    tg = Target(rig)
    tg.seat_offset = measure_seat_offset(tg) if any(data[n]["meta"].get("seat") for n in names) else 0.1
    for pbone in rig.pose.bones:
        pbone.rotation_mode = 'QUATERNION'
    t2 = time.time()
    out = {}
    report = {}
    for n in names:
        clip = data[n]
        W, pelvis_pos, extra = solve(tg, clip)
        Q, tp = to_local(tg, W, pelvis_pos, extra)
        out[n] = write_action(rig, n, tg, Q, tp, clip["meta"]["loop"])
        m = clip["meta"]
        report[n] = {"frames": m["nframes"], "seconds": round(m["duration"], 2), "loop": m["loop"],
                     "src": m["src"], "src_frames": m["frames"]}
        if "speed_leg" in m:
            report[n]["speed_mps"] = round(m["speed_leg"] * tg.leg, 3)
    if "idle" in out:
        rig.animation_data.action = out["idle"]
    # locomotion speeds of THIS body (they scale with leg length); exported as glTF extras on the armature node
    speeds_now = {n: r["speed_mps"] for n, r in report.items() if "speed_mps" in r}
    if speeds_now:
        old = dict(rig.get("anim_speeds", {}))
        old.update(speeds_now)
        rig["anim_speeds"] = old
    if verbose:
        log(f"{len(out)} clips on {rig.name} (leg {tg.leg:.3f} m, seat offset {tg.seat_offset:.3f} m, "
            f"palm twist fix {', '.join(f'{k}:{v:.0f}deg' for k, v in tg.palm_twist.items())}) "
            f"cache {t1 - t0:.2f}s rig {t2 - t1:.2f}s solve+write {time.time() - t2:.2f}s")
        for n, r in report.items():
            log(f"  {n:12s} {r['seconds']:5.2f}s {'loop' if r['loop'] else 'once'}"
                + (f"  {r['speed_mps']:.2f} m/s" if "speed_mps" in r else "") + f"  <- {r['src']} {r['src_frames']}")
    return out


def speeds(rig):
    """Locomotion clip speeds (m/s) for this rig."""
    tg_leg = Target(rig).leg
    d = ap.ensure([n for n, c in ac.CLIPS.items() if c["kind"] == "loco"])
    return {n: c["meta"]["speed_leg"] * tg_leg for n, c in d.items()}


if __name__ == "__main__":
    # Blender -b some.blend -P tools/blender/retarget.py -- [clip,clip,...] [--save]
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names = [a for a in argv if not a.startswith("--")]
    for ob in [o for o in bpy.data.objects if o.type == 'ARMATURE' and "Root" in o.data.bones]:
        apply(ob, names[0].split(",") if names else None)
    if "--save" in argv:
        bpy.ops.wm.save_mainfile()
