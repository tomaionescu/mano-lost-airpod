"""Procedural hair cards for the MPFB characters.

Roots are scattered over the scalp (above a hairline traced from the face landmarks), each strand is grown
through a style flow field with gravity, kept outside the head/body, pulled into clumps towards the tips,
and turned into a tapered ribbon card mapped onto a generated strand texture (fine strands with alpha,
root-to-tip colour). A thin "cap" under the cards hides the scalp the way game hair does.
Output: one mesh object weighted to the head (and neck/spine for long hair), plus its material.
"""
import bpy, bmesh, os, math, json, random
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

# landmark ids (MediaPipe face mesh) used to trace the hairline
FOREHEAD_TOP, FOREHEAD_MID = 10, 151
BROW_L, BROW_R = 105, 334
TEMPLE_L, TEMPLE_R = 54, 284
EAR_L, EAR_R = 127, 356

STYLES = {
    # thick straight hair, fringe down to the brows, sides over the top of the ears
    "fringe": {"lengths": {"front": 0.13, "top": 0.14, "side": 0.1, "back": 0.085}, "cards": 3400,
               "crown": (0.0, 0.035, 0.1), "fringe_to_brow": True, "gravity": 0.34, "lift": 0.014,
               "layers": (0.004, 0.03), "width": 0.012, "clump": 0.5, "messy": 0.08, "segments": 12,
               "sweep": 0.35, "floors": {"front": "eye", "side": "ear_mid", "back": "nape"}},
    # medium top swept up and back, short tapered sides
    "swept": {"lengths": {"front": 0.1, "top": 0.09, "side": 0.035, "back": 0.04}, "cards": 2300,
              "sweep_back": True, "gravity": 0.12, "lift": 0.04, "front_lift": 1.6, "layers": (0.004, 0.026),
              "width": 0.010, "clump": 0.6, "messy": 0.07, "segments": 10,
              "floors": {"front": "brow", "side": "ear", "back": "nape"}},
    # long straight hair with a centre part, past the shoulders
    "long_part": {"lengths": {"front": 0.42, "top": 0.48, "side": 0.46, "back": 0.5}, "cards": 2000,
                  "part": True, "gravity": 0.9, "lift": 0.006, "layers": (0.004, 0.014), "width": 0.013,
                  "clump": 0.5, "messy": 0.06, "segments": 22},
    # shoulder-length layered, centre part, a few face-framing strands
    "layered": {"lengths": {"front": 0.2, "top": 0.26, "side": 0.24, "back": 0.25}, "cards": 2100,
                "part": True, "gravity": 1.0, "lift": 0.006, "layers": (0.003, 0.012), "width": 0.012,
                "clump": 0.72, "messy": 0.05, "segments": 16},
    # medium-length curls, fuller on top, ears half covered
    "curly": {"lengths": {"front": 0.14, "top": 0.15, "side": 0.09, "back": 0.1}, "cards": 2900,
              "crown": (0.0, 0.03, 0.1), "fringe_to_brow": True, "gravity": 0.36, "lift": 0.013, "layers": (0.005, 0.03),
              "width": 0.011, "clump": 0.55, "messy": 0.12, "segments": 40, "curl": (0.006, 0.045), "sweep": 0.15,
              "floors": {"front": "eye", "side": "ear_mid", "back": "nape"}},
    # long box braids from a centre part, down past the shoulders
    "braids": {"lengths": {"front": 0.46, "top": 0.52, "side": 0.5, "back": 0.55}, "cards": 240,
               "sweep_back": True, "gravity": 0.75, "lift": 0.012, "front_lift": 1.4, "layers": (0.006, 0.016),
               "width": 0.011, "clump": 0.0, "messy": 0.03, "segments": 26, "braid": True,
               "floors": {"front": "brow", "side": "jaw", "back": "free"}},   # braids sweep back off the face
    # generic short cut for NPCs
    "short": {"lengths": {"front": 0.05, "top": 0.06, "side": 0.025, "back": 0.03}, "cards": 1600,
              "crown": (0.0, 0.04, 0.1), "gravity": 0.3, "lift": 0.012, "layers": (0.003, 0.012),
              "width": 0.009, "clump": 0.5, "messy": 0.1, "segments": 8,
              "floors": {"front": "brow", "side": "ear", "back": "nape"}},
}


def _anchor_points(basemesh, root):
    anchors = json.load(open(os.path.join(root, "tools", "models", "mpfb_face_anchors.json")))["anchors"]
    mw = basemesh.matrix_world
    V = [mw @ v.co for v in basemesh.data.vertices]
    def at(i):
        a = anchors[i]
        return sum((V[v] * w for v, w in zip(a["v"], a["w"])), Vector())
    return at


def _head_frame(rig):
    pb = rig.pose.bones["head"]
    m = rig.matrix_world @ pb.matrix
    head = rig.matrix_world @ pb.head
    tail = rig.matrix_world @ pb.tail
    up = (tail - head).normalized()
    fwd = Vector((0, -1, 0))  # MPFB characters face -Y in Blender
    fwd = (fwd - up * fwd.dot(up)).normalized()
    side = fwd.cross(up).normalized()  # character's left (+X)
    return head, up, fwd, side


# ------------------------------------------------------------------ strand texture
def braid_texture(path, root_col, tip_col, size=(2048, 1024), strips=8, seed=1):
    """RGBA atlas for box braids: each strip is one three-strand braid seen from the front, root at the top."""
    rng = np.random.default_rng(seed)
    W, H = size
    sw = W // strips
    yy, xx = np.mgrid[0:H, 0:sw].astype(np.float32)
    root_col = np.array(root_col, np.float32)
    tip_col = np.array(tip_col, np.float32)
    rgb = np.zeros((H, W, 3), np.float32)
    alpha = np.zeros((H, W), np.float32)
    for s in range(strips):
        seg = rng.uniform(34, 44)                      # one crossing every ~seg pixels
        half = sw * rng.uniform(0.36, 0.42)            # braid half width
        cx = sw / 2 + 2.0 * np.sin(yy / 90.0 + s)      # a gentle wobble down the braid
        x = (xx - cx) / half                           # -1..1 across the braid
        ph = yy / seg
        lobe = np.abs(((ph + np.where(x < 0, 0.0, 0.5)) % 1.0) - 0.5) * 2.0   # 0 at a crossing, 1 mid-lobe
        edge = 1.0 - np.clip((np.abs(x) - (0.78 + 0.18 * lobe)) / 0.12, 0, 1)
        tipfade = np.clip((H * rng.uniform(0.93, 0.99) - yy) / 40.0, 0, 1)
        a = edge * tipfade
        # strands run diagonally inside each lobe; crossings are darker, lobe centres catch light
        strands = 0.82 + 0.18 * np.sin((x * 3.0 + np.sign(x) * ph * 6.283) * 3.0 + rng.uniform(0, 6.28))
        shade = (0.55 + 0.45 * np.sin(lobe * 1.5708)) * strands * (1.0 - 0.25 * np.abs(x) ** 2)
        t = np.clip(yy / (H * 0.6), 0, 1)[..., None]
        col = (root_col * (1 - t) + tip_col * t) * shade[..., None]
        rgb[:, s * sw:(s + 1) * sw] = col
        alpha[:, s * sw:(s + 1) * sw] = a
    img = np.concatenate([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)[..., None]], -1)
    _save_png(path, img)
    return path


def strand_texture(path, root_col, tip_col, size=(2048, 1024), strips=8, seed=1, braid=False):
    """RGBA atlas: `strips` vertical card strips (root at v=0 / top), each one hair clump.

    Real hair cards are dense: an almost opaque core of overlapping strands that thins out into wisps at the
    edges and the tips. Strips cycle through dense, medium and wispy clumps so cards don't all look alike.
    """
    if braid:
        return braid_texture(path, root_col, tip_col, size, strips, seed)
    rng = np.random.default_rng(seed)
    W, H = size
    sw = W // strips
    k = W / 2048.0                                   # pixel sizes are tuned for a 2048-wide atlas
    rgb = np.zeros((H, W, 3), np.float32)
    alpha = np.zeros((H, W), np.float32)
    ys = np.arange(H, dtype=np.float32)
    root_col = np.array(root_col, np.float32)
    tip_col = np.array(tip_col, np.float32)
    kinds = [(380, 0.20), (320, 0.24), (240, 0.30), (110, 0.36)]   # (strands, spread as a fraction of the strip)
    for s in range(strips):
        n, spread = kinds[s % len(kinds)]
        n = int(n * rng.uniform(0.9, 1.1))
        x_lo = s * sw
        centre = x_lo + sw * rng.uniform(0.46, 0.54)
        for _ in range(n):
            # clumped: strands gather around the clump centre, a few strays wander to the edges
            x0 = centre + rng.normal(0, spread * sw) * (1.6 if rng.random() < 0.08 else 1.0)
            x0 = float(np.clip(x0, x_lo + 0.05 * sw, x_lo + 0.95 * sw))
            # most strands run the full length, some stop early: the tip thins out naturally
            length = H * (1.0 - rng.beta(1.2, 4.0) * 0.75)
            amp = rng.uniform(0.3, 2.6) * k
            freq = rng.uniform(0.003, 0.01) / k
            ph = rng.uniform(0, 6.28)
            towards = (centre - x0) * rng.uniform(0.15, 0.55)   # tips pull into the clump
            wpx = rng.uniform(0.7, 1.6) * k
            light = rng.uniform(0.8, 1.2)
            warm = rng.uniform(-0.04, 0.04)
            yy = ys[ys < length]
            t = yy / H
            xc = x0 + amp * np.sin(yy * freq + ph) + towards * (yy / length) ** 1.6
            xi = np.floor(xc).astype(int)
            fade = np.clip((length - yy) / (0.22 * length), 0, 1) * np.clip(yy / (8.0 * k), 0, 1)
            g = np.clip(t / 0.4, 0, 1)[:, None]
            col = (root_col * (1 - g) + tip_col * g) * light
            col = col * np.array([1 + warm, 1.0, 1 - warm], np.float32)
            r = int(math.ceil(wpx * 2.2))
            for dx in range(-r, r + 1):
                x = xi + dx
                ok = (x >= x_lo) & (x < x_lo + sw)
                d = np.abs(x + 0.5 - xc)
                a = np.exp(-(d / (wpx * 0.62)) ** 2) * fade * 0.92
                a = a[ok]
                yi = yy[ok].astype(int)
                xo = x[ok]
                prev = alpha[yi, xo]
                rgb[yi, xo] += col[ok] * (a * (1 - prev))[:, None]
                alpha[yi, xo] = prev + a * (1 - prev)
    rgb = rgb / np.maximum(alpha, 1e-4)[..., None]
    # fill RGB under transparent texels with the local colour so mip-maps don't bleed dark halos
    filled = rgb.copy()
    for _ in range(3):
        k_ = alpha > 0.05
        if k_.all():
            break
        mean = np.where(k_[..., None], filled, 0).sum(0) / np.maximum(k_.sum(0)[:, None], 1)
        filled = np.where(k_[..., None], filled, mean[None, :, :])
    img = np.concatenate([np.clip(filled, 0, 1), np.clip(alpha, 0, 1)[..., None]], -1)
    _save_png(path, img)
    return path

def _save_png(path, img):
    h, w = img.shape[:2]
    im = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    im.pixels.foreach_set(np.flipud(img).astype(np.float32).ravel())
    im.filepath_raw = path
    im.file_format = 'PNG'
    im.save()
    bpy.data.images.remove(im)


# ------------------------------------------------------------------ geometry
def make_hair(basemesh, rig, style_name, colors, name, root, seed=7, extra_colliders=(), density=1.0, style_over=None):
    style = dict(STYLES[style_name])
    if style_over:
        # (cast "hair_gen", off by default) per-person overrides of the style's keys
        style.update(style_over)
    style["cards"] = int(style["cards"] * density)
    rng = random.Random(seed)
    at = _anchor_points(basemesh, root)
    head, up, fwd, side = _head_frame(rig)
    mw = basemesh.matrix_world
    me = basemesh.data
    body_vg = basemesh.vertex_groups["body"].index
    head_vg = basemesh.vertex_groups.get("head")
    verts = [mw @ v.co for v in me.vertices]
    in_body = [any(g.group == body_vg and g.weight > 0.5 for g in v.groups) for v in me.vertices]
    head_w = [0.0] * len(me.vertices)
    neck_vg = basemesh.vertex_groups.get("neck_01")
    wanted = {g.index for g in (head_vg, neck_vg) if g is not None}
    for v in me.vertices:
        for g in v.groups:
            if g.group in wanted:
                head_w[v.index] += g.weight

    # collision surfaces: the body, plus clothes for long hair
    tris = []
    for p in me.polygons:
        vs = list(p.vertices)
        if all(in_body[i] for i in vs):
            for k in range(1, len(vs) - 1):
                tris.append((vs[0], vs[k], vs[k + 1]))
    bvh = BVHTree.FromPolygons([tuple(v) for v in verts], tris)
    col_bvhs = [bvh]
    for ob in extra_colliders:
        dg = bpy.context.evaluated_depsgraph_get()
        col_bvhs.append(BVHTree.FromObject(ob, dg))

    # hairline from landmarks, in head-local terms (height above the head origin along `up`)
    def h(p):
        return (p - head).dot(up)
    forehead = h(at(FOREHEAD_TOP)) - 0.004
    if style.get("fringe_to_brow"):
        forehead -= 0.006
    temple = (h(at(TEMPLE_L)) + h(at(TEMPLE_R))) * 0.5 + 0.012
    ear = (h(at(EAR_L)) + h(at(EAR_R))) * 0.5 + 0.035
    brow = (h(at(BROW_L)) + h(at(BROW_R))) * 0.5
    nape = ear - 0.075
    center = head + up * (forehead - 0.07)
    if style.get("hairline_up"):
        # (style "hairline_up" {front, temple} m, off by default) the hairline raised over the forehead and the
        # temples (after the head's centre is placed, so the zones stay), for a hairline higher than the landmark line
        # gives (about 0.7 inter-ocular distances over the eyes' centres)
        forehead += style["hairline_up"].get("front", 0.0)
        temple += style["hairline_up"].get("temple", 0.0)

    def region(p):
        d = p - center
        f = d.dot(fwd)
        s = d.dot(side)
        az = math.atan2(s, f)  # 0 = front, ±pi = back
        return az, f, s

    def hairline(az):
        a = abs(az)
        # a few millimetres of irregularity so the edge never reads as a cut line
        wobble = 0.0025 * math.sin(az * 9.0 + 1.3) + 0.0018 * math.sin(az * 23.0 + 0.4)
        if a < 0.55:
            return forehead + (temple - forehead) * (a / 0.55) ** 2 + wobble
        if a < 1.55:
            return temple + (ear - temple) * ((a - 0.55) / 1.0) + wobble
        return ear + (nape - ear) * min(1.0, (a - 1.55) / 0.9) + wobble

    # (style "face_clear" {w, margin, ahead}, off by default) hanging hair kept out of a window in front of
    # the face: from the brows down to 3 cm under the chin, `w` x the skin's widest half width there (in front of the
    # ears' landmarks by `ahead` m) plus `margin` m either side. A strand point that grows into it is moved sideways to
    # its edge before the collision push, so locks rooted along the front hairline fall beside the cheeks, not over
    # the eyes (the landmarks' own width put them inside a widened cheek, and the push brought them out in front).
    # `top` (m over the brows, default 0.012) raises the window's top over the forehead and `profile` makes its half
    # width the skin's own in each 1 cm band (2 cm wide) instead of its widest: from the brows up, locks rooted at the
    # front hairline sagged over the forehead to the window's top and were pushed aside there, a straight fringe.
    fclear = style.get("face_clear")
    if fclear:
        _ear_c = (at(EAR_L) + at(EAR_R)) * 0.5
        fc_front = (_ear_c - center).dot(fwd) + fclear.get("ahead", 0.01)
        fc_top = brow + fclear.get("top", 0.012)
        fc_bot = h(at(152)) - 0.03
        fc_half = abs((at(EAR_L) - at(EAR_R)).dot(side)) * 0.5
        fc_nb = int(math.ceil((fc_top - fc_bot) / 0.01)) + 1
        fc_band = [0.0] * fc_nb
        for _i, _v in enumerate(verts):
            if in_body[_i] and fc_bot < h(_v) < fc_top:
                _, _f, _s = region(_v)
                if _f > fc_front:
                    fc_half = max(fc_half, abs(_s))
                    _k = int((h(_v) - fc_bot) / 0.01)
                    fc_band[_k] = max(fc_band[_k], abs(_s))
        fc_w, fc_m = fclear.get("w", 1.0), fclear.get("margin", 0.008)
        fc_half = fc_half * fc_w + fc_m
        fc_band = [max(fc_band[max(0, k - 1):k + 2]) * fc_w + fc_m for k in range(fc_nb)]
        print(f"[hair] {name}: face_clear half width {fc_half * 1000:.0f} mm, front {fc_front * 1000:.0f} mm, "
              f"{fc_bot * 1000:.0f} to {fc_top * 1000:.0f} mm over the head bone"
              + (f", by height {[round(x * 1000) for x in fc_band]} mm" if fclear.get("profile") else ""))

    def clear_face(q, s_root):
        if not fclear:
            return q
        _, f, s = region(q)
        hq = h(q)
        if f < fc_front or hq > fc_top or hq < fc_bot:
            return q
        half = fc_band[min(fc_nb - 1, int((hq - fc_bot) / 0.01))] if fclear.get("profile") else fc_half
        if abs(s) >= half:
            return q
        sg = (1.0 if s >= 0 else -1.0) if abs(s) > 0.004 else (1.0 if s_root >= 0 else -1.0)
        mv = sg * half - s
        if fclear.get("slide") and hq > brow + 0.012:
            # (`slide`, m per step) over the forehead a lock moves aside at most this far per growth step, so it
            # sweeps along the skin to the temple instead of jumping there in one long straight row
            mv = max(-fclear["slide"], min(fclear["slide"], mv))
        return q + side * mv

    # scalp triangles and area-weighted root sampling
    scalp = []
    for (a, b, c) in tris:
        if min(head_w[a], head_w[b], head_w[c]) < 0.5:
            continue
        P = (verts[a] + verts[b] + verts[c]) / 3
        az, f, s = region(P)
        if h(P) > hairline(az) - 0.004 and h(P) > nape - 0.012:
            area = (verts[b] - verts[a]).cross(verts[c] - verts[a]).length * 0.5
            scalp.append((a, b, c, area))
    areas = np.array([s[3] for s in scalp])
    cdf = np.cumsum(areas) / areas.sum()
    n_cards = style["cards"]
    roots = []
    tries = 0
    while len(roots) < n_cards and tries < n_cards * 14:
        tries += 1
        k = int(np.searchsorted(cdf, rng.random()))
        a, b, c, _ = scalp[min(k, len(scalp) - 1)]
        u, v = rng.random(), rng.random()
        if u + v > 1:
            u, v = 1 - u, 1 - v
        P = verts[a] + (verts[b] - verts[a]) * u + (verts[c] - verts[a]) * v
        # density ramps up over the first 1.5 cm above the hairline: soft, natural edge
        az_p, _, _ = region(P)
        dh = h(P) - hairline(az_p)
        if rng.random() > max(0.0, min(1.0, (dh + 0.004) / 0.016)):
            continue
        _, n, _, _ = bvh.find_nearest(P)
        roots.append((P, n.normalized()))

    lo, hi = style["layers"]
    seg = style["segments"]
    crown = center + side * style.get("crown", (0, 0.03, 0.1))[0] - fwd * style.get("crown", (0, 0.03, 0.1))[1] + up * style.get("crown", (0, 0.03, 0.1))[2]

    # (style "flow_zones" {front, front_side, back, back_out, fall}, off by default) the flow by the zone of the
    # strand's root (`_root`: its |azimuth| and side), not of the point it has grown to: roots in front of |az|
    # `front` sweep back over the scalp (and `front_side` sideways off the part), as braids pulled back from the
    # hairline (parted sideways from there they lie over the top of the forehead as a flat band); roots behind `back`
    # hang straight down the back (`back_out`: a little away from it; parted sideways, they leave the nape bare); in
    # between, the part's sideways push fades out from `fall` [from, span] m under the ears' hairline line down (a
    # constant sideways push flares the braids out at the shoulders)
    fzones = style.get("flow_zones")
    _root = [None]

    def flow_dir(P, n):
        az, f, s = region(P)
        if fzones and _root[0] is not None:
            ra, rs = _root[0]
            sg = 1.0 if rs >= 0 else -1.0
            if ra < fzones.get("front", -1.0):
                d = -fwd + up * 0.35 + side * sg * fzones.get("front_side", 0.3)
            elif ra > fzones.get("back", 9.0):
                d = -up - fwd * fzones.get("back_out", 0.15)
            else:
                f0, span = fzones.get("fall", (0.0, 0.08))
                k = max(0.0, min(1.0, (h(P) - (ear - f0)) / max(span, 1e-4)))
                d = side * sg * k - up * (0.3 + 0.7 * (1.0 - k))
            d = d - n * d.dot(n)
            return d.normalized() if d.length > 1e-6 else -up
        if style.get("part"):
            # away from a centre parting line running front to back
            d = side * (1 if s >= 0 else -1) - up * 0.3
        elif style.get("sweep_back"):
            d = -fwd + up * 0.35 + side * (s * 2.5)
        else:
            d = (P - crown)
            d = d - up * d.dot(up) * 0.4
            if style.get("sweep") and f > 0:
                d = d + side * style["sweep"] * d.length
        d = d - n * d.dot(n)
        return d.normalized() if d.length > 1e-6 else -up

    def length_for(P):
        az, f, s = region(P)
        L = style["lengths"]
        a = abs(az)
        topness = max(0.0, min(1.0, (h(P) - (temple + 0.02)) / 0.045))
        zone = L["front"] if a < 0.7 else (L["side"] if a < 2.1 else L["back"])
        return (zone * (1 - topness) + L["top"] * topness) * rng.uniform(0.85, 1.1)

    floors = style.get("floors")  # lowest tip height per zone, relative to landmarks

    def floor_at(p):
        if not floors:
            return -1e9
        az, _, _ = region(p)
        a = abs(az)
        ref = {"brow": brow + 0.004, "eye": brow - 0.012, "ear": ear - 0.035, "ear_mid": ear - 0.06,
               "nape": nape, "jaw": ear - 0.09, "free": -1e9}
        zf = ref[floors["front"]] if a < 0.7 else (ref[floors["side"]] if a < 2.1 else ref[floors["back"]])
        return zf

    def push_out(p, minh):
        for i, tree in enumerate(col_bvhs):
            hit = tree.find_nearest(p)
            if hit[0] is None:
                continue
            q, n, _, dist = hit
            if style.get("collide_reach") and dist > style["collide_reach"]:
                # (style "collide_reach", off by default) surfaces further than this are not collided with
                # (one growth step goes ~1 cm in): a strand point far from a garment read as inside it by the normal
                # of its nearest point (a hem, a collar's inner face) and jumped there (a braid from the forehead to
                # the sweater's hem, 63 cm in one row)
                continue
            off = p - q
            inside = off.dot(n) < 0
            want = minh if i == 0 else 0.008
            if inside or dist < want:
                p = q + n * want
        return p

    strands = []
    layers = []
    for P0, n0 in roots:
        layer = lo + (hi - lo) * (rng.random() ** 1.6)
        L = length_for(P0)
        step = L / seg
        p = P0 + n0 * layer * 0.5
        az_r, _, _ = region(P0)
        _root[0] = (abs(az_r), region(P0)[2])
        lift = style["lift"] * 25 * (style.get("front_lift", 1.0) if abs(az_r) < 0.8 else 1.0)
        d = (flow_dir(P0, n0) + n0 * lift).normalized()
        pts = [P0 - n0 * 0.002, p]
        wander = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        for k in range(seg):
            t = (k + 1) / seg
            _, n, _, _ = bvh.find_nearest(p)
            fd = flow_dir(p, n)
            grav = -up * style["gravity"] * min(1.0, t * 1.6)
            jitter = (wander * 0.7 + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * 0.3) * style["messy"]
            d = (d * 0.6 + fd * 0.4 + grav + jitter).normalized()
            q = push_out(clear_face(p + d * step, region(P0)[2]) if fclear else p + d * step, layer)
            if h(q) < min(floor_at(q), h(P0) - 0.025):
                break
            p = q
            pts.append(p)
        if len(pts) >= 3:
            strands.append(pts)
            layers.append(layer)

    # (style "scalp_hug" {max, layer, up, above}, off by default) on the top of the head (the scalp's normal facing up
    # past up[0], in full from up[1]; `above` m over the ears' hairline line) every strand point kept within `max` +
    # `layer` x its strand's layer of the scalp: front braids, lifted at the root and swept back, otherwise arch up
    # off the crown and stand as thin loops over the head's silhouette
    hug = style.get("scalp_hug")
    if hug:
        u0, u1 = hug.get("up", (0.25, 0.55))
        n_hug, worst = 0, 0.0
        for i, s in enumerate(strands):
            cap_d = hug.get("max", 0.006) + hug.get("layer", 0.5) * layers[i]
            for k in range(1, len(s)):
                p = s[k]
                if h(p) < ear + hug.get("above", 0.0):
                    continue
                q, n, _, dist = bvh.find_nearest(p)
                if q is None or dist <= cap_d:
                    continue
                z = max(0.0, min(1.0, (n.dot(up) - u0) / max(u1 - u0, 1e-6)))
                z = z * z * (3.0 - 2.0 * z)
                if z <= 0.0:
                    continue
                worst = max(worst, dist)
                s[k] = q + (p - q).normalized() * (dist + z * (cap_d - dist))
                n_hug += 1
        print(f"[hair] {name}: scalp_hug moved {n_hug} points (up to {worst * 1000:.0f} mm off the scalp) to within "
              f"{hug.get('max', 0.006) * 1000:.0f} mm + {hug.get('layer', 0.5):.2f} x layer")

    # clumping: pull strands towards their clump's mean shape, more at the tips
    kd = KDTree(len(strands))
    for i, s in enumerate(strands):
        kd.insert(s[0], i)
    kd.balance()
    n_clumps = max(8, len(strands) // 14)
    centers = rng.sample(range(len(strands)), n_clumps)
    ckd = KDTree(n_clumps)
    for j, i in enumerate(centers):
        ckd.insert(strands[i][0], j)
    ckd.balance()
    members = {j: [] for j in range(n_clumps)}
    owner = []
    for i, s in enumerate(strands):
        _, j, _ = ckd.find(s[0])
        members[j].append(i)
        owner.append(j)
    means = {}
    for j, ids in members.items():
        if not ids:
            continue
        n = max(len(strands[i]) for i in ids)
        means[j] = []
        for k in range(n):
            pts_k = [strands[i][k] for i in ids if k < len(strands[i])]
            means[j].append(sum(pts_k, Vector()) / len(pts_k))
    for i, s in enumerate(strands):
        m = means.get(owner[i])
        if m is None:
            continue
        for k in range(2, min(len(s), len(m))):
            t = k / (len(s) - 1)
            s[k] = s[k].lerp(m[k] + (s[0] - m[0]) * (1 - t) * 0.6, style["clump"] * t ** 1.2)

    spines = {}   # uncurled centre lines: ribbons are oriented along these so curls wave instead of twisting
    if style.get("curl"):
        amp, wavelength = style["curl"]
        clump_phase = {j: rng.uniform(0, 6.283) for j in members}
        for i, s in enumerate(strands):
            ph0 = clump_phase.get(owner[i], 0.0) + rng.uniform(-0.5, 0.5)
            arc = 0.0
            spine = [q.copy() for q in s]
            spines[i] = spine
            for k in range(2, len(s)):
                arc += (spine[k] - spine[k - 1]).length
                t = k / (len(s) - 1)
                tan = (spine[min(k + 1, len(s) - 1)] - spine[k - 1]).normalized()
                b1 = tan.cross(up)
                if b1.length < 1e-6:
                    b1 = tan.cross(side)
                b1.normalize()
                b2 = tan.cross(b1).normalized()
                phase = ph0 + 6.283 * arc / wavelength
                ramp = min(1.0, t / 0.18)
                s[k] = spine[k] + (b1 * math.cos(phase) + b2 * math.sin(phase)) * amp * ramp

    # ribbons
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    tone = bm.loops.layers.color.new("Col")   # rgb: occlusion by depth in the hair volume x per-clump tone
    deform = bm.verts.layers.deform.verify()
    strips = 8
    width = style["width"]
    vert_meta = []
    for i, s in enumerate(strands):
        depth = max(0.0, min(1.0, (layers[i] - lo) / max(hi - lo, 1e-6))) if i < len(layers) else 1.0
        ao = 0.5 + 0.5 * depth ** 0.6
        shade = rng.uniform(0.86, 1.1) * ao
        warm = rng.uniform(-0.035, 0.035)
        card_col = (min(1.0, shade * (1 + warm)), min(1.0, shade), min(1.0, shade * (1 - warm)), 1.0)
        col_u = rng.randrange(strips)
        u0, u1 = col_u / strips + 0.004, (col_u + 1) / strips - 0.004
        wscale = rng.uniform(0.75, 1.3)
        prev = None
        rows = []
        guide = spines.get(i, s)
        # (style "root_taper" {len, w} and "fin_flat" {h, near, far}, off by default) front braids swept back over the
        # scalp otherwise start square at full width, with their second (upright) card standing up off the scalp.
        # root_taper widens a braid from `w` of its width over its first `len` m; fin_flat lowers the upright card to
        # `h` of its width where the braid lies within `near` m of the scalp (full height from `far` on)
        rtap = style.get("root_taper")
        ffin = style.get("fin_flat")
        arc = 0.0
        for k, p in enumerate(s):
            t = k / (len(s) - 1)
            tan = (guide[min(k + 1, len(s) - 1)] - guide[max(k - 1, 0)]).normalized()
            loc_k, n, _, _ = bvh.find_nearest(guide[k])
            wv = tan.cross(n)
            if wv.length < 1e-6:
                wv = side
            wv.normalize()
            taper = (1.0 - 0.2 * t ** 2) if style.get("braid") else (1.0 - 0.55 * t ** 1.5)
            if rtap:
                if k > 0:
                    arc += (guide[k] - guide[k - 1]).length
                x = min(1.0, arc / max(rtap.get("len", 0.02), 1e-6))
                taper *= rtap.get("w", 0.3) + (1.0 - rtap.get("w", 0.3)) * x * x * (3.0 - 2.0 * x)
            wdt = width * wscale * taper
            a = bm.verts.new(p - wv * wdt * 0.5)
            b = bm.verts.new(p + wv * wdt * 0.5)
            if style.get("braid"):
                wv2 = tan.cross(wv).normalized()
                fh = 1.0
                if ffin and loc_k is not None:
                    y = min(1.0, max(0.0, ((p - loc_k).length - ffin.get("near", 0.012)) /
                                     max(ffin.get("far", 0.03) - ffin.get("near", 0.012), 1e-6)))
                    fh = ffin.get("h", 0.35) + (1.0 - ffin.get("h", 0.35)) * y * y * (3.0 - 2.0 * y)
                    # only on the top of the head (the scalp facing up): beside the face the upright card is the
                    # one seen from the front, and lowered there the braids read thin, the temple bare
                    z = min(1.0, max(0.0, (n.dot(up) - ffin.get("up", (0.35, 0.65))[0]) /
                                     max(ffin.get("up", (0.35, 0.65))[1] - ffin.get("up", (0.35, 0.65))[0], 1e-6)))
                    fh = 1.0 - z * z * (3.0 - 2.0 * z) * (1.0 - fh)
                c = bm.verts.new(p - wv2 * wdt * 0.5 * fh)
                e = bm.verts.new(p + wv2 * wdt * 0.5 * fh)
                rows.append((a, b, t, c, e))
            else:
                rows.append((a, b, t))
        for k in range(len(rows) - 1):
            a0, b0, t0 = rows[k][:3]
            a1, b1, t1 = rows[k + 1][:3]
            quads = [(a0, b0, b1, a1)]
            if style.get("braid"):
                quads.append((rows[k][3], rows[k][4], rows[k + 1][4], rows[k + 1][3]))
            for quad in quads:
                f = bm.faces.new(quad)
                f.smooth = True
                for loop, (uu, vv) in zip(f.loops, ((u0, t0), (u1, t0), (u1, t1), (u0, t1))):
                    loop[uv].uv = (uu, 1.0 - vv)
                    loop[tone] = card_col
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = rig

    # weights: head, and for long hair blend into neck / upper spine by height
    vg_head = obj.vertex_groups.new(name="head")
    vg_neck = obj.vertex_groups.new(name="neck_01")
    vg_sp = obj.vertex_groups.new(name="spine_03")
    for v in mesh.vertices:
        hh = h(v.co)
        w_head = max(0.0, min(1.0, (hh - (nape - 0.04)) / 0.06))
        rest = 1.0 - w_head
        if w_head > 0:
            vg_head.add([v.index], w_head, 'REPLACE')
        if rest > 0:
            w_sp = max(0.0, min(1.0, (nape - 0.08 - hh) / 0.12))
            vg_sp.add([v.index], rest * w_sp, 'REPLACE')
            vg_neck.add([v.index], rest * (1 - w_sp), 'REPLACE')
    mod = obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig

    # (style "cap_below", m, default 0.014: how far under the hairline the dark cap reaches, fading in)
    cap = _make_cap(basemesh, rig, verts, tris, head_w, h, region, hairline, nape, colors, name, bvh,
                    below=style.get("cap_below", 0.014))

    # material: generated strand atlas tinted per character
    tex_path = os.path.join(root, "tools", "out", f"hair_{name}.png")
    strand_texture(tex_path, colors["root"], colors["tip"], size=(4096, 2048) if density >= 1.0 else (2048, 1024),
                   seed=seed, braid=bool(style.get("braid")))
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(tex_path)
    vcol = nt.nodes.new('ShaderNodeVertexColor')
    vcol.layer_name = "Col"
    mul = nt.nodes.new('ShaderNodeMix')
    mul.data_type = 'RGBA'
    mul.blend_type = 'MULTIPLY'
    mul.inputs[0].default_value = 1.0
    nt.links.new(tex.outputs[0], mul.inputs[6])
    nt.links.new(vcol.outputs[0], mul.inputs[7])
    nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
    rnd = nt.nodes.new('ShaderNodeMath')
    rnd.operation = 'ROUND'
    nt.links.new(tex.outputs[1], rnd.inputs[0])
    nt.links.new(rnd.outputs[0], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.45
    mesh.materials.append(mat)
    print(f"[hair] {name}: {len(strands)} cards, {len(mesh.vertices)} verts, style {style_name}, cap {len(cap.data.vertices)} verts")
    return obj


def _make_cap(basemesh, rig, verts, tris, head_w, h, region, hairline, nape, colors, name, bvh, below=0.014):
    """Dark shell 1.5 mm above the scalp; vertex alpha fades to 0 across 1.2 cm at the hairline."""
    bm = bmesh.new()
    vmap = {}
    col = bm.loops.layers.color.new("Col")
    root = colors["root"]
    for (a, b, c) in tris:
        if min(head_w[a], head_w[b], head_w[c]) < 0.3:
            continue
        P = (verts[a] + verts[b] + verts[c]) / 3
        az, _, _ = region(P)
        if h(P) < hairline(az) - below or h(P) < nape - 0.02:
            continue
        fv = []
        for i in (a, b, c):
            if i not in vmap:
                _, n, _, _ = bvh.find_nearest(verts[i])
                vmap[i] = bm.verts.new(verts[i] + n * 0.0015)
            fv.append(vmap[i])
        try:
            f = bm.faces.new(fv)
        except ValueError:
            continue
        f.smooth = True
        for loop, i in zip(f.loops, (a, b, c)):
            az, _, _ = region(verts[i])
            edge = min(h(verts[i]) - (hairline(az) - below), h(verts[i]) - (nape - 0.02))
            alpha = max(0.0, min(1.0, edge / 0.012))
            loop[col] = (root[0] * 1.4, root[1] * 1.4, root[2] * 1.4, alpha)
    mesh = bpy.data.meshes.new(name + "cap")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name.replace("hairgen", "haircap"), mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = rig
    vg = obj.vertex_groups.new(name="head")
    vg.add([v.index for v in mesh.vertices], 1.0, 'REPLACE')
    obj.modifiers.new("Armature", 'ARMATURE').object = rig
    mat = bpy.data.materials.new(name + "cap")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    vc = nt.nodes.new('ShaderNodeVertexColor')
    vc.layer_name = "Col"
    nt.links.new(vc.outputs[0], bsdf.inputs["Base Color"])
    nt.links.new(vc.outputs[1], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.7
    mesh.materials.append(mat)
    obj["kind"] = "haircap"
    obj["baked_color"] = True
    return obj
