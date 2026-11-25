"""Seat a scanned character's glasses clear of the fitted face (cast "glasses": {"clear": <metres>}, off without it).

scan_wrap moves the glasses by the median of the face's displacement, rigidly; on a fuller face than the template's
the frame then sinks into it, and thin rims show gaps and stray pieces along the brows and cheeks. This moves the
glasses straight forward (the face looks along -Y in Blender) until every vertex of the front of the frame (within 2
cm of its frontmost point) stands at least `clear` outside the skin, measured along the skin's normal at the nearest
point; at most `max_shift` (default 8 mm). The arms move with it (a few mm in front of the ears' tops). Called by
build_human after scan_wrap.apply, before the hair cards (which keep off the glasses). Known limit: the nearest-normal
measure misreads some lens vertices in front of the eyes (nearest to the lids' inner edges) as 5 mm inside, so the
move can run to its 8 mm cap. shape() below seats the frame by rays instead.
"""
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def log(*a):
    print("[glasses]", *a, flush=True)


def _world(obj):
    M = np.array(obj.matrix_world)
    V = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", V)
    V = V.reshape(-1, 3)
    return V @ M[:3, :3].T + M[:3, 3], M


def _signed(bvh, P):
    out = np.empty(len(P))
    for i, p in enumerate(P):
        loc, n, _, _ = bvh.find_nearest(Vector(p.tolist()), 0.1)
        out[i] = 0.1 if loc is None else float(np.dot(p - np.array(loc), np.array(n)))
    return out


def _smoothstep(a, b, x):
    t = np.clip((np.asarray(x, np.float64) - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _eyes(rig):
    """The eyeballs' centres (right, left) and the inter-ocular distance."""
    eyes = [o for o in rig.children if o.type == 'MESH' and "high-poly" in o.name]
    if not eyes:
        return None
    E = np.concatenate([_world(o)[0] for o in eyes])
    cr, cl = E[E[:, 0] < 0].mean(0), E[E[:, 0] > 0].mean(0)
    return cr, cl, float(abs(cl[0] - cr[0]))


def _skin_bvh(basemesh):
    Vb, _ = _world(basemesh)
    vg = basemesh.vertex_groups.get("body")
    body = np.ones(len(Vb), bool)
    if vg is not None:
        body[:] = False
        for v in basemesh.data.vertices:
            for ge in v.groups:
                if ge.group == vg.index and ge.weight > 0.5:
                    body[v.index] = True
    tris = []
    for p in basemesh.data.polygons:
        vs = list(p.vertices)
        if not body[vs].all():
            continue
        for k in range(1, len(vs) - 1):
            tris.append((vs[0], vs[k], vs[k + 1]))
    return BVHTree.FromPolygons(Vb.tolist(), tris, all_triangles=True)


def _ray_clear(bvh, P):
    """Per point: how far in front of the skin it is, along the face's view (-Y): from 15 mm in front, a ray back
    (+Y) to the first skin facing it; 0.1 where it meets none within 5 cm (over an eye: the eye sockets are holes in
    the body mesh). Where it first meets the skin from inside (the hinges and the arms' front, beside the temples
    and behind the cheekbones' front), the nearest-normal distance instead."""
    out = np.full(len(P), 0.1)
    for i, p in enumerate(P):
        loc, n, _, _ = bvh.ray_cast(Vector((p[0], p[1] - 0.015, p[2])), Vector((0.0, 1.0, 0.0)), 0.05)
        if loc is None:
            continue
        if n.y < 0.0:
            out[i] = float(loc.y - p[1])
        else:
            q = Vector(p.tolist())
            loc2, n2, _, _ = bvh.find_nearest(q, 0.1)
            if loc2 is not None:
                out[i] = float((q - loc2).dot(n2))
    return out


def wire(P, E, o):
    """(cast glasses "lens_fit" "wire" {k, depth, panto}, off without it) the rims thinned to wire: the round asset's
    front is a ~3 mm wide band round each lens (several stacked rings), which reads as thick rims with a second arc
    inside the lens. Each lens is the front piece whose box centre lies on it; the rim is every other front vertex on
    that side within 0.8-1.4 of the lens' half-axes. Per 20 deg round the lens the rim's inner and outer edge are
    taken, and every rim vertex moved toward their middle, `k` of its radial offset kept (the endpiece and bridge
    outside 1.22-1.32 stay), `depth` of its offset front to back; the lens disc grows to the thinned rim's inner edge.
    `panto` raises the top's shoulders (sin^2 of twice the angle, fading out toward the bridge) for a flatter, more
    angular top. P: world points (metres), E: edges; returns the new points and which vertices are lenses."""
    n = len(P)
    par = np.arange(n)

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for a, b in E:
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb
    root = np.array([find(i) for i in range(n)])
    front = (P[:, 1] - P[:, 1].min()) < 0.02
    k, kd, pan = float(o.get("k", 0.4)), float(o.get("depth", 0.75)), float(o.get("panto", 0.0))
    Q = P.copy()
    lenses = np.zeros(n, bool)
    for r in np.unique(root):
        lens = root == r
        L = P[lens]
        if not front[lens].all() or np.ptp(L[:, 0]) < 0.02:
            continue
        c = (L.min(0) + L.max(0)) / 2
        if np.hypot(L[:, 0] - c[0], L[:, 2] - c[2]).min() > 0.003:
            continue
        a, b = np.ptp(L[:, 0]) / 2, np.ptp(L[:, 2]) / 2
        side = np.sign(c[0])
        u = (P[:, 0] - c[0]) / a * side
        w = (P[:, 2] - c[2]) / b
        s = np.hypot(u, w)
        th = np.arctan2(w, u)
        rim = front & ~lens & (np.sign(P[:, 0]) == side) & (s > 0.8) & (s < 1.4)
        nb = 18
        bi = ((th + np.pi) / (2 * np.pi) * nb).astype(int) % nb
        s_in, s_out, yc = np.full(nb, np.nan), np.full(nb, np.nan), np.full(nb, np.nan)
        for j in range(nb):
            m = rim & (bi == j) & (s < 1.25)
            if m.sum() >= 4:
                s_in[j], s_out[j], yc[j] = s[m].min(), s[m].max(), np.median(P[m, 1])
        good = ~np.isnan(s_in)
        if good.sum() < 3:
            continue
        for arr in (s_in, s_out, yc):
            arr[~good] = np.interp(np.nonzero(~good)[0], np.nonzero(good)[0], arr[good], period=nb)
            if o.get("even", True):
                # one ellipse for the whole rim: the per-bin edges kinked the thinned wire every 20 deg
                arr[:] = np.median(arr)
        sc = (s_in + s_out) / 2
        f = (th + np.pi) / (2 * np.pi) * nb - 0.5
        j0 = np.floor(f).astype(int) % nb
        j1 = (j0 + 1) % nb
        t = f - np.floor(f)
        scv, yv, siv = (x[j0] * (1 - t) + x[j1] * t for x in (sc, yc, s_in))
        wt = rim * (1.0 - _smoothstep(1.22, 1.32, s))
        s_new = np.where(rim, s + wt * (scv + (s - scv) * k - s), s)
        s_new = np.where(lens, s * ((scv + (siv - scv) * k) / np.maximum(siv, 1e-6) + 0.01), s_new)
        w2 = s_new * np.sin(th)
        u2 = s_new * np.cos(th)
        sq = float(o.get("square", 0.0))
        if sq > 0:
            # (wire "square" and "square_in", off by default) the rim a superellipse of exponent 2 + square (x
            # square_in on the bridge side) instead of the ellipse, for frames with a flat top and angular corners
            # (panto's raised shoulders read as a hump on a round lens); the endpieces and bridge (outside the rim's
            # band) stay. "square_bottom" (default 1): the share of it under the lens' middle
            sb = float(o.get("square_bottom", 1.0))
            nn = 2.0 + sq * np.where(np.cos(th) < 0, float(o.get("square_in", 0.5)), 1.0) * \
                (sb + (1.0 - sb) * _smoothstep(-0.35, 0.35, np.sin(th)))
            fsq = (np.abs(np.cos(th)) ** nn + np.abs(np.sin(th)) ** nn) ** (-1.0 / nn)
            fsq = 1.0 + (fsq - 1.0) * np.where(lens, 1.0, wt)
            u2 = u2 * fsq
            w2 = w2 * fsq
        if pan > 0:
            d = np.degrees(th)
            amt = np.where((d > 0) & (d < 180), np.sin(2 * th) ** 2, 0.0) * (1.0 - np.where(d > 90, _smoothstep(115, 150, d), 0.0))
            w2 = w2 + pan * s_new * amt * np.where(lens, 1.0, wt)
        mv = rim | lens
        lenses |= lens
        Q[mv, 0] = c[0] + side * a * u2[mv]
        Q[mv, 2] = c[2] + b * w2[mv]
        Q[rim, 1] = (P[:, 1] + wt * (yv + (P[:, 1] - yv) * kd - P[:, 1]))[rim]
        log(f"wire: lens {a * 1000:.1f} x {b * 1000:.1f} mm, its rim {np.median(s_out - s_in) * b * 1000:.2f} mm wide "
            f"-> {np.median(s_out - s_in) * k * b * 1000:.2f}; {int(rim.sum())} rim and {int(lens.sum())} lens vertices, "
            f"moved up to {np.linalg.norm(Q - P, axis=1).max() * 1000:.1f} mm")
    return Q, lenses


def shape(basemesh, rig, opts):
    """(cast glasses "lens" and "seat", off without them) the front of the frame moved and reshaped by the eyes, then
    seated by rays instead of the nearest-normal measure. lens {top, bottom, width} (inter-ocular distances, IOD): the
    lenses' outer top edge `top` over the eyeballs' centres, their bottom edge `bottom` under them (the whole front
    translated, then stretched about its top), each lens `width` wide about its own centre (the bridge stretches, the
    hinges move in). The arms follow the hinges, fading out over 3 cm behind them. seat {clear, sigma}: from 6 cm in
    front of each front-frame vertex a ray back to the first skin (the nearest-normal measure read lens vertices over
    the lids' inner edges as 5 mm inside and ran to its 8 mm cap); the frame moves forward rigidly until the rims
    outside the bridge stand `clear` off the skin, and what is still closer (the bridge on the nose) is pushed further
    forward by a smooth bump (Gaussian, `sigma` metres)."""
    glasses = [o for o in rig.children if o.type == 'MESH' and "glasses" in o.name.lower()]
    ey = _eyes(rig)
    if not glasses or ey is None:
        return
    cr, cl, iod = ey
    ez = float((cr[2] + cl[2]) / 2)
    lens = opts.get("lens")
    seat = opts.get("seat")
    bvh = _skin_bvh(basemesh) if seat else None
    for g in glasses:
        P, M = _world(g)
        P0 = P.copy()
        if opts.get("wire"):
            # (glasses "wire", off by default) the rims thinned to wire before the lenses are fitted
            E = np.empty(len(g.data.edges) * 2, np.int64)
            g.data.edges.foreach_get("vertices", E)
            P, lens_v = wire(P, E.reshape(-1, 2), opts["wire"])
            vmax = opts["wire"].get("lens_v_max")
            if vmax is not None and g.data.uv_layers.active is not None:
                # the leopard lens texture's alpha reaches 1 over its top tenth (v > 0.94), which glasses.gdshader
                # draws as frame: an opaque gold band inside the top of each lens, a second rim under the real one
                uvd = g.data.uv_layers.active.data
                lv = np.empty(len(g.data.loops), np.int64)
                g.data.loops.foreach_get("vertex_index", lv)
                UV = np.empty(len(uvd) * 2)
                uvd.foreach_get("uv", UV)
                UV = UV.reshape(-1, 2)
                hit = lens_v[lv] & (UV[:, 1] > float(vmax))
                UV[hit, 1] = float(vmax)
                uvd.foreach_set("uv", UV.ravel())
                log(f"{g.name}: lens UVs held under v {float(vmax):.2f} ({int(hit.sum())} loops)")
        ymin = float(P[:, 1].min())
        depth = P[:, 1] - ymin
        front = depth < 0.02
        hinge = np.argmax(np.where(front, np.abs(P[:, 0]), -1.0))
        dh = float(depth[hinge])
        w = 1.0 - _smoothstep(dh + 0.002, dh + 0.03, depth)
        fz = P[front, 2]
        top, bot = float(fz.max()), float(fz.min())
        if lens:
            t_top = ez + float(lens.get("top", 0.17)) * iod
            t_bot = ez - float(lens.get("bottom", 0.58)) * iod
            sz = (t_top - t_bot) / max(top - bot, 1e-6)
            znew = t_top + (P[:, 2] - top) * sz
            if lens.get("width"):
                zc = 0.5 * (top + bot)
                ring = front & (np.abs(P[:, 2] - (zc - 0.005)) < 0.0012)
                xo = float(np.abs(P[front, 0]).max())
                x_in = float(np.abs(P[ring, 0]).min()) if ring.any() else 0.3 * xo
                cx = 0.5 * (x_in + xo)
                sx = float(lens["width"]) * iod / max(xo - x_in, 1e-6)
                ax = np.abs(P[:, 0])
                xin2 = cx + (x_in - cx) * sx
                anew = np.where(ax >= x_in, cx + (ax - cx) * sx, ax * xin2 / max(x_in, 1e-6))
                P[:, 0] = P[:, 0] + w * (np.sign(P[:, 0]) * anew - P[:, 0])
                log(f"{g.name}: lenses {(xo - x_in) * 1000:.1f} mm wide ({(xo - x_in) / iod:.2f} IOD) -> "
                    f"{(xo - x_in) * sx * 1000:.1f}; bridge half-width {x_in * 1000:.1f} -> {xin2 * 1000:.1f} mm")
            P[:, 2] = P[:, 2] + w * (znew - P[:, 2])
            log(f"{g.name}: front {(top - ez) / iod:+.2f} to {(bot - ez) / iod:+.2f} IOD about the eyes (IOD "
                f"{iod * 1000:.1f} mm) -> {(t_top - ez) / iod:+.2f} to {(t_bot - ez) / iod:+.2f}; moved "
                f"{(t_top - top) * 1000:+.1f} mm at the top, {(t_bot - bot) * 1000:+.1f} at the bottom")
        if seat:
            clear = float(seat.get("clear", 0.0015))
            sig = float(seat.get("sigma", 0.006))
            fi = np.nonzero(front)[0]
            c0 = _ray_clear(bvh, P[fi])
            bridge = np.abs(P[fi, 0]) < float(seat.get("bridge", 0.012))
            s = max(0.0, clear - float(c0[~bridge].min())) if (~bridge).any() else 0.0
            need = np.maximum(0.0, clear - (c0 + s))
            push = np.zeros(len(P))
            hot = np.nonzero(need > 1e-5)[0]
            if len(hot):
                Q = P[fi[hot]][:, [0, 2]]
                for i in range(0, len(P), 2048):
                    d2 = ((P[i:i + 2048, None, :][:, :, [0, 2]] - Q[None]) ** 2).sum(-1)
                    push[i:i + 2048] = (need[hot][None] * np.exp(-0.5 * d2 / sig ** 2)).max(1)
            P[:, 1] = P[:, 1] - w * (s + push)
            c1 = _ray_clear(bvh, P[fi])
            log(f"{g.name}: seated by rays: rims {c0[~bridge].min() * 1000:.1f} mm off the skin at the closest, "
                f"bridge {c0[bridge].min() * 1000 if bridge.any() else 0:.1f}; moved {s * 1000:.1f} mm forward, the "
                f"bridge zone up to {push.max() * 1000:.1f} more -> closest {c1.min() * 1000:.1f} mm "
                f"(median {np.median(c1) * 1000:.1f})")
        Minv = np.linalg.inv(M)
        Pl = P @ Minv[:3, :3].T + Minv[:3, 3]
        g.data.vertices.foreach_set("co", Pl.astype(np.float32).ravel())
        g.data.update()
        log(f"{g.name}: front reshaped, vertices moved up to {np.linalg.norm(P - P0, axis=1).max() * 1000:.1f} mm")


def apply(basemesh, rig, clear, max_shift=0.008, opts=None):
    if opts and (opts.get("lens") or opts.get("seat")):
        shape(basemesh, rig, opts)
        return
    glasses = [o for o in rig.children if o.type == 'MESH' and "glasses" in o.name.lower()]
    if not glasses:
        return
    Vb, _ = _world(basemesh)
    # the skin only: MakeHuman's helper geometry (tights, skirt, hair helpers, joint cubes) is still on the base mesh
    vg = basemesh.vertex_groups.get("body")
    body = np.ones(len(Vb), bool)
    if vg is not None:
        body[:] = False
        for v in basemesh.data.vertices:
            for ge in v.groups:
                if ge.group == vg.index and ge.weight > 0.5:
                    body[v.index] = True
    tris = []
    for p in basemesh.data.polygons:
        vs = list(p.vertices)
        if not body[vs].all():
            continue
        for k in range(1, len(vs) - 1):
            tris.append((vs[0], vs[k], vs[k + 1]))
    bvh = BVHTree.FromPolygons(Vb.tolist(), tris, all_triangles=True)
    for g in glasses:
        P, M = _world(g)
        front = P[:, 1] < P[:, 1].min() + 0.02
        sd0 = _signed(bvh, P[front])
        shift = 0.0
        sd = sd0
        for _ in range(6):
            need = clear - float(sd.min())
            if need <= 1e-4 or shift >= max_shift:
                break
            # moving along -Y raises the distance by about the normal's forward part (0.6-1 on the brows and cheeks)
            shift = min(max_shift, shift + need / 0.7)
            sd = _signed(bvh, P[front] + np.array([0.0, -shift, 0.0]))
        if shift <= 0.0:
            log(f"{g.name}: front of the frame already {sd0.min() * 1000:.1f} mm or more outside the skin")
            continue
        Minv = np.linalg.inv(M)
        Pl = (P + np.array([0.0, -shift, 0.0])) @ Minv[:3, :3].T + Minv[:3, 3]
        g.data.vertices.foreach_set("co", Pl.astype(np.float32).ravel())
        g.data.update()
        log(f"{g.name}: moved {shift * 1000:.1f} mm forward; front of the frame {int((sd0 < 0).sum())} of "
            f"{int(front.sum())} vertices inside the skin (deepest {-sd0.min() * 1000:.1f} mm) -> "
            f"{int((sd < 0).sum())} (closest {sd.min() * 1000:.1f} mm)")
