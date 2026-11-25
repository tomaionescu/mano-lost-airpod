"""Per-person touches on a MakeHuman hair asset (cast "hair": "hair/<asset>/<asset>.mhclo"), called by build_human
after the photo fit; off without the cast key.

- "hair_stretch" {from, k, clear}: the hair below `from` m under the shoulders' line (the clavicles' heads; negative is
  above it) made `k` times as long, straight down (each vertex's height under that line scaled by k), then every moved
  vertex pushed out of the body and the clothes to at least `clear` m off them. culturalibre_hair_01 is a centre-part
  straight cut ending at the collarbones; the stretch takes it past the shoulders.
"""
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def log(*a):
    print("[mhhair]", *a, flush=True)


def _hair_obj(rig, spec):
    key = spec["hair"].split("/")[-1].replace(".mhclo", "")
    for o in rig.children:
        if o.type == 'MESH' and key in o.name:
            return o
    return None


def stretch(basemesh, rig, spec, opts):
    hair = _hair_obj(rig, spec)
    if hair is None:
        log("stretch: no hair mesh")
        return
    pb = rig.pose.bones
    zs = [(rig.matrix_world @ pb[n].head).z for n in ("clavicle_l", "clavicle_r") if n in pb]
    z0 = (sum(zs) / len(zs) if zs else 1.3) - float(opts.get("from", 0.0))
    k = float(opts.get("k", 1.5))
    clear = float(opts.get("clear", 0.006))
    mw = hair.matrix_world
    inv = mw.inverted()
    me = hair.data
    P = [mw @ v.co for v in me.vertices]
    dg = bpy.context.evaluated_depsgraph_get()
    trees = [BVHTree.FromObject(basemesh, dg)]
    for o in rig.children:
        if o.type == 'MESH' and o not in (basemesh, hair) and o.get("kind", "") != "glasses" and \
                not any(w in o.name.lower() for w in ("glasses", "eyebrow", "eyelash", "teeth", "tongue", "high-poly", "shoe", "sneaker")):
            trees.append(BVHTree.FromObject(o, dg))
    moved = 0
    lowest = min(p.z for p in P)
    skin_clear = float(opts.get("skin", 0.002))
    for i, p in enumerate(P):
        if p.z >= z0:
            # above the line: only out of the skin (a widened face, photo_finish, can reach into the hair beside it)
            loc, n, _, d = trees[0].find_nearest(p)
            if loc is not None and ((p - loc).dot(n) < 0 or d < skin_clear):
                me.vertices[i].co = inv @ (loc + n * skin_clear)
                moved += 1
            continue
        q = Vector((p.x, p.y, z0 - (z0 - p.z) * k))
        for t in trees:
            loc, n, _, d = t.find_nearest(q)
            if loc is None:
                continue
            if (q - loc).dot(n) < 0 or d < clear:
                q = loc + n * clear
        me.vertices[i].co = inv @ q
        moved += 1
    me.update()
    log(f"stretch: {moved} vertices under {z0:.3f} m x{k}; lowest {lowest:.3f} -> {z0 - (z0 - lowest) * k:.3f} m")


def over_glasses(basemesh, rig, spec, opts):
    """(hair_stretch "over_glasses" {clear, behind, sz, st}, off by default) the hair beside the head pushed out over
    the glasses' temple arms, so they go into it at its front edge instead of lying on top of the hair. Arm points are
    the frame's vertices more than `behind` m behind its front; each hair vertex is moved out from the head's vertical
    axis (through the head bone) to `clear` m beyond the arm points round it, weighted by a Gaussian over height (`sz`
    m) and along the head (`st` m)."""
    hair = _hair_obj(rig, spec)
    gl = [o for o in rig.children if o.type == 'MESH' and "glasses" in o.name.lower()]
    if hair is None or not gl:
        log("over_glasses: no hair or no glasses")
        return
    G = np.concatenate([np.array([list(gl_.matrix_world @ v.co) for v in gl_.data.vertices]) for gl_ in gl])
    A = G[G[:, 1] > G[:, 1].min() + float(opts.get("behind", 0.015))]
    if not len(A):
        return
    hb = rig.matrix_world @ rig.pose.bones["head"].head
    cx, cy = hb.x, hb.y
    clear, sz, st = (float(opts.get(k, d)) for k, d in (("clear", 0.004), ("sz", 0.012), ("st", 0.015)))
    ra = np.hypot(A[:, 0] - cx, A[:, 1] - cy)
    ta = np.arctan2(A[:, 1] - cy, A[:, 0] - cx)
    mw = hair.matrix_world
    inv = mw.inverted()
    me = hair.data
    P = np.array([list(mw @ v.co) for v in me.vertices])
    rp = np.hypot(P[:, 0] - cx, P[:, 1] - cy)
    tp = np.arctan2(P[:, 1] - cy, P[:, 0] - cx)
    near = (P[:, 2] > A[:, 2].min() - 3 * sz) & (P[:, 2] < A[:, 2].max() + 3 * sz)
    moved = 0
    push_max = 0.0
    for i in np.flatnonzero(near):
        dt = np.angle(np.exp(1j * (tp[i] - ta)))
        w = np.exp(-((P[i, 2] - A[:, 2]) / sz) ** 2 - (dt * ra / st) ** 2)
        need = float(((ra + clear - rp[i]) * w).max())
        if need > 1e-4:
            k = (rp[i] + need) / max(rp[i], 1e-6)
            q = Vector((cx + (P[i, 0] - cx) * k, cy + (P[i, 1] - cy) * k, P[i, 2]))
            me.vertices[i].co = inv @ q
            moved += 1
            push_max = max(push_max, need)
    me.update()
    log(f"over_glasses: {moved} hair vertices moved out over {len(A)} arm points, up to {push_max * 1000:.1f} mm")


def apply(basemesh, rig, spec):
    if spec.get("hair_stretch") and spec.get("hair"):
        stretch(basemesh, rig, spec, spec["hair_stretch"])
        if spec["hair_stretch"].get("over_glasses"):
            over_glasses(basemesh, rig, spec, spec["hair_stretch"]["over_glasses"])
