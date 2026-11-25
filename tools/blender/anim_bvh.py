"""Minimal BVH reader + vectorised forward kinematics (numpy only, no bpy).

Used by retarget.py / anim_prep.py. Works in Blender's bundled Python and in any Python with numpy.

    bvh = load("assets/anims/src/07_01.bvh")
    rot, pos = bvh.fk()            # world rotations (F, J, 3, 3) and joint positions (F, J, 3), source units
"""
import numpy as np

_AXIS = {"X": 0, "Y": 1, "Z": 2}


class BVH:
    def __init__(self):
        self.names = []        # joint names (end sites excluded)
        self.parents = []      # parent index, -1 for root
        self.offsets = []      # rest offset in parent frame (3,)
        self.channels = []     # list of channel names per joint
        self.end_sites = {}    # joint index -> end site offset (3,)
        self.frame_time = 1 / 30
        self.data = None       # (F, C) raw channel values

    # ------------------------------------------------------------------ parse
    @classmethod
    def parse(cls, text):
        self = cls()
        tok = text.split()
        i = 0
        stack = []
        cur = None
        in_end = False
        while i < len(tok):
            t = tok[i]
            if t in ("ROOT", "JOINT"):
                name = tok[i + 1]
                self.names.append(name)
                self.parents.append(stack[-1] if stack else -1)
                self.offsets.append(np.zeros(3))
                self.channels.append([])
                cur = len(self.names) - 1
                i += 2
            elif t == "End":
                in_end = True
                i += 2
            elif t == "{":
                if not in_end:
                    stack.append(cur)
                i += 1
            elif t == "}":
                if in_end:
                    in_end = False
                else:
                    stack.pop()
                i += 1
            elif t == "OFFSET":
                v = np.array([float(x) for x in tok[i + 1:i + 4]])
                if in_end:
                    self.end_sites[stack[-1]] = v
                else:
                    self.offsets[cur] = v
                i += 4
            elif t == "CHANNELS":
                n = int(tok[i + 1])
                self.channels[cur] = tok[i + 2:i + 2 + n]
                i += 2 + n
            elif t == "MOTION":
                i += 1
                break
            else:
                i += 1
        # MOTION section
        assert tok[i] == "Frames:"
        nframes = int(tok[i + 1])
        assert tok[i + 2] == "Frame" and tok[i + 3] == "Time:"
        self.frame_time = float(tok[i + 4])
        vals = np.array(tok[i + 5:], dtype=np.float64)
        nch = sum(len(c) for c in self.channels)
        nframes = min(nframes, len(vals) // nch)
        self.data = vals[:nframes * nch].reshape(nframes, nch)
        self.offsets = np.array(self.offsets)
        self.parents = np.array(self.parents)
        return self

    @property
    def fps(self):
        return 1.0 / self.frame_time

    @property
    def nframes(self):
        return self.data.shape[0]

    def index(self, name):
        return self.names.index(name)

    # ------------------------------------------------------------------ kinematics
    def local(self, frames=None):
        """Local rotations (F, J, 3, 3) and translations (F, J, 3) per joint."""
        d = self.data if frames is None else self.data[frames]
        F, J = d.shape[0], len(self.names)
        rot = np.tile(np.eye(3), (F, J, 1, 1))
        trans = np.tile(self.offsets, (F, 1, 1)).astype(np.float64)
        c = 0
        for j, chans in enumerate(self.channels):
            pos_axes = {}
            r = None
            for ch in chans:
                ax = _AXIS[ch[0]]
                v = d[:, c]
                c += 1
                if ch.endswith("position"):
                    pos_axes[ax] = v
                else:
                    m = axis_rot(ax, np.radians(v))
                    r = m if r is None else r @ m
            if pos_axes:
                # position channels replace the offset (MotionBuilder / Blender importer convention)
                for ax, v in pos_axes.items():
                    trans[:, j, ax] = v
            if r is not None:
                rot[:, j] = r
        return rot, trans

    def fk(self, frames=None, local=None):
        """World rotations (F, J, 3, 3) and joint positions (F, J, 3) in BVH units/axes."""
        lrot, ltrans = self.local(frames) if local is None else local
        F, J = lrot.shape[:2]
        wrot = np.empty_like(lrot)
        wpos = np.empty((F, J, 3))
        for j in range(J):
            p = self.parents[j]
            if p < 0:
                wrot[:, j] = lrot[:, j]
                wpos[:, j] = ltrans[:, j]
            else:
                wrot[:, j] = wrot[:, p] @ lrot[:, j]
                wpos[:, j] = wpos[:, p] + np.einsum("fij,fj->fi", wrot[:, p], ltrans[:, j])
        return wrot, wpos

    def end_position(self, j, wrot, wpos):
        """World position of joint j's end site (F, 3), or None."""
        if j not in self.end_sites:
            return None
        return wpos[:, j] + np.einsum("fij,j->fi", wrot[:, j], self.end_sites[j])


def load(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return BVH.parse(f.read())


# ---------------------------------------------------------------------- rotation helpers (numpy)
def axis_rot(ax, ang):
    """Rotation matrices (N, 3, 3) about principal axis ax (0/1/2) by angles ang (N,) radians."""
    ang = np.asarray(ang, dtype=np.float64)
    c, s = np.cos(ang), np.sin(ang)
    m = np.zeros(ang.shape + (3, 3))
    i, j = [(1, 2), (2, 0), (0, 1)][ax]
    m[..., ax, ax] = 1
    m[..., i, i] = c
    m[..., j, j] = c
    m[..., i, j] = -s
    m[..., j, i] = s
    return m


def mat_to_quat(m):
    """(..., 3, 3) -> (..., 4) quaternions (w, x, y, z), w >= 0."""
    m = np.asarray(m)
    shp = m.shape[:-2]
    m = m.reshape(-1, 3, 3)
    q = np.empty((m.shape[0], 4))
    tr = m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2]
    cands = np.stack([tr, m[:, 0, 0], m[:, 1, 1], m[:, 2, 2]], 1)
    k = np.argmax(cands, 1)
    for case in range(4):
        sel = k == case
        if not np.any(sel):
            continue
        a = m[sel]
        if case == 0:
            s = np.sqrt(np.maximum(tr[sel] + 1.0, 1e-12)) * 2
            q[sel] = np.stack([0.25 * s, (a[:, 2, 1] - a[:, 1, 2]) / s, (a[:, 0, 2] - a[:, 2, 0]) / s, (a[:, 1, 0] - a[:, 0, 1]) / s], 1)
        elif case == 1:
            s = np.sqrt(np.maximum(1.0 + a[:, 0, 0] - a[:, 1, 1] - a[:, 2, 2], 1e-12)) * 2
            q[sel] = np.stack([(a[:, 2, 1] - a[:, 1, 2]) / s, 0.25 * s, (a[:, 0, 1] + a[:, 1, 0]) / s, (a[:, 0, 2] + a[:, 2, 0]) / s], 1)
        elif case == 2:
            s = np.sqrt(np.maximum(1.0 + a[:, 1, 1] - a[:, 0, 0] - a[:, 2, 2], 1e-12)) * 2
            q[sel] = np.stack([(a[:, 0, 2] - a[:, 2, 0]) / s, (a[:, 0, 1] + a[:, 1, 0]) / s, 0.25 * s, (a[:, 1, 2] + a[:, 2, 1]) / s], 1)
        else:
            s = np.sqrt(np.maximum(1.0 + a[:, 2, 2] - a[:, 0, 0] - a[:, 1, 1], 1e-12)) * 2
            q[sel] = np.stack([(a[:, 1, 0] - a[:, 0, 1]) / s, (a[:, 0, 2] + a[:, 2, 0]) / s, (a[:, 1, 2] + a[:, 2, 1]) / s, 0.25 * s], 1)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    q[q[:, 0] < 0] *= -1
    return q.reshape(shp + (4,))


def quat_to_mat(q):
    q = np.asarray(q)
    shp = q.shape[:-1]
    q = q.reshape(-1, 4)
    q = q / np.linalg.norm(q, axis=1, keepdims=True)
    w, x, y, z = q.T
    m = np.stack([
        1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
        2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
        2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], 1)
    return m.reshape(shp + (3, 3))


def quat_mul(a, b):
    aw, ax, ay, az = np.moveaxis(a, -1, 0)
    bw, bx, by, bz = np.moveaxis(b, -1, 0)
    return np.stack([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw], -1)


def quat_conj(q):
    return q * np.array([1, -1, -1, -1])


def quat_continuity(q, axis=0):
    """Flip signs along `axis` so consecutive quaternions stay in the same hemisphere."""
    q = np.array(q)
    q = np.moveaxis(q, axis, 0)
    for i in range(1, q.shape[0]):
        d = np.sum(q[i] * q[i - 1], axis=-1)
        q[i][d < 0] *= -1
    return np.moveaxis(q, 0, axis)


def quat_slerp(a, b, t):
    """Slerp between quaternion arrays a, b (..., 4) with t broadcastable to (...)."""
    t = np.asarray(t)[..., None]
    d = np.sum(a * b, -1, keepdims=True)
    b = np.where(d < 0, -b, b)
    d = np.abs(d)
    lin = d > 0.9995
    th = np.arccos(np.clip(d, -1, 1))
    s = np.sin(th)
    s = np.where(lin, 1.0, s)
    wa = np.where(lin, 1 - t, np.sin((1 - t) * th) / s)
    wb = np.where(lin, t, np.sin(t * th) / s)
    r = wa * a + wb * b
    return r / np.linalg.norm(r, axis=-1, keepdims=True)


def quat_log(q):
    """Unit quaternion -> rotation vector (axis * angle)."""
    q = np.where(q[..., :1] < 0, -q, q)
    v = q[..., 1:]
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    ang = 2 * np.arctan2(n, q[..., :1])
    return np.where(n > 1e-9, v / np.maximum(n, 1e-12) * ang, 2 * v)


def quat_exp(r):
    ang = np.linalg.norm(r, axis=-1, keepdims=True)
    half = ang / 2
    s = np.where(ang > 1e-9, np.sin(half) / np.maximum(ang, 1e-12), 0.5)
    return np.concatenate([np.cos(half), r * s], -1)


def look_rot(primary, secondary, primary_axis=1, secondary_axis=2):
    """Rotation matrices whose column `primary_axis` is `primary` and column `secondary_axis`
    is `secondary` orthogonalised against it. Arrays (..., 3)."""
    p = primary / np.linalg.norm(primary, axis=-1, keepdims=True)
    s = secondary - np.sum(secondary * p, -1, keepdims=True) * p
    s = s / np.maximum(np.linalg.norm(s, axis=-1, keepdims=True), 1e-12)
    third = 3 - primary_axis - secondary_axis
    m = np.zeros(p.shape + (3,))
    m[..., :, primary_axis] = p
    m[..., :, secondary_axis] = s
    # right-handed: col(k) = col(k+1) x col(k+2)
    cols = {primary_axis: p, secondary_axis: s}
    a, b = (third + 1) % 3, (third + 2) % 3
    m[..., :, third] = np.cross(cols[a], cols[b])
    return m


def swing_to(a, b):
    """Minimal rotation matrices taking unit vectors a to b (..., 3)."""
    a = a / np.linalg.norm(a, axis=-1, keepdims=True)
    b = b / np.linalg.norm(b, axis=-1, keepdims=True)
    v = np.cross(a, b)
    c = np.sum(a * b, -1)
    s = np.linalg.norm(v, axis=-1)
    q = np.concatenate([(1 + c)[..., None], v], -1)
    # opposite vectors: rotate 180 degrees about any perpendicular axis
    opp = (1 + c) < 1e-9
    if np.any(opp):
        perp = np.cross(a, np.array([1.0, 0, 0]))
        bad = np.linalg.norm(perp, axis=-1) < 1e-6
        perp = np.where(bad[..., None], np.cross(a, np.array([0, 1.0, 0])), perp)
        q = np.where(opp[..., None], np.concatenate([np.zeros_like(c)[..., None], perp], -1), q)
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    return quat_to_mat(q)
