"""Per-person touches on a scanned character's fitted face (cast "face_finish": {...}, off without it). Called by
build_human after scan_wrap.apply (the head is fitted, its 4K texture composed) and before the glasses are seated and
the hair cards grown, so both follow the face as it ends up.

- "widen" {amount, top, bottom, under, front, back} (inter-ocular distances, IOD, and metres): the cheeks and the jaw
  pushed out sideways by `amount` of their distance from the face's middle, in full from `top` IOD under the eyes'
  centres down to `bottom`, fading out to none at the eyes and `under` IOD under them (the neck), and from `front`
  to `back` metres behind the eyes' front (the ears and the back of the jaw stay). Teeth and tongue move with it.
  `inner` [none, full] (m, off by default): only the face's sides move, none within inner[0] of its middle.
- "brows" {dark, desat, fill, reach}: the brows deepened in the head texture: within `reach` metres of each brow's
  landmarks (MediaPipe, the template's anchors), texels darker than the skin round them darkened by up to `dark` and
  desaturated by up to `desat`, the whole brow by `fill` more (the portrait's projection can leave dark brows a light
  warm brown).
- "eye_corners" {reach}: texels at the eyes' corners that are light, grey-blue and unsaturated (the portrait's
  whites painted onto the lids where the template's lids lie) take the skin round them.
"""
import json, os
import numpy as np
import bpy
import scan_wrap as SW


def log(*a):
    print("[face]", *a, flush=True)


def _eyes(rig):
    eyes = [o for o in rig.children if o.type == 'MESH' and "high-poly" in o.name]
    if not eyes:
        return None
    E = np.concatenate([SW.world_verts(o) for o in eyes])
    cr, cl = E[E[:, 0] < 0].mean(0), E[E[:, 0] > 0].mean(0)
    return cr, cl, float(abs(cl[0] - cr[0])), float(E[:, 1].min())


def _set_world(obj, P):
    M = np.array(obj.matrix_world)
    Minv = np.linalg.inv(M)
    L = P @ Minv[:3, :3].T + Minv[:3, 3]
    L0 = np.empty(len(obj.data.vertices) * 3, np.float32)
    obj.data.vertices.foreach_get("co", L0)
    obj.data.vertices.foreach_set("co", L.astype(np.float32).ravel())
    if obj.data.shape_keys:
        # every shape key moves with the basis (the same displacement)
        dL = L.astype(np.float32).ravel() - L0
        for kb in obj.data.shape_keys.key_blocks:
            K = np.empty(len(obj.data.vertices) * 3, np.float32)
            kb.data.foreach_get("co", K)
            kb.data.foreach_set("co", K + dL)
    obj.data.update()


def widen(basemesh, rig, w):
    ey = _eyes(rig)
    if ey is None:
        return
    cr, cl, iod, ef = ey
    ec = (cr + cl) / 2
    amt = float(w.get("amount", 0.04))
    top, bot, und = (float(w.get(k, d)) * iod for k, d in (("top", 0.45), ("bottom", 1.5), ("under", 2.2)))
    fr_, bk_ = float(w.get("front", 0.045)), float(w.get("back", 0.085))
    objs = [basemesh] + [o for o in rig.children if o.type == 'MESH' and any(k in o.name.lower() for k in
                                                                            ("teeth", "tongue"))]
    moved = 0.0
    for o in objs:
        P = SW.world_verts(o)
        dz = ec[2] - P[:, 2]                 # under the eyes
        wz = SW.smoothstep(0.0, top, dz) * (1.0 - SW.smoothstep(bot, und, dz))
        wy = 1.0 - SW.smoothstep(ef + fr_, ef + bk_, P[:, 1])
        k = amt * wz * wy
        if not (k > 1e-6).any():
            continue
        dx = P[:, 0] - ec[0]
        if w.get("inner") is not None:
            # ("inner" [none, full] m, off by default) only the face's sides: no move within inner[0] of its middle,
            # in full beyond inner[1] (widened whole, the mouth, nose and lower lids go out with the cheekbones, and
            # the outer eye corners come off the eyeballs)
            k = k * SW.smoothstep(float(w["inner"][0]), float(w["inner"][1]), np.abs(dx))
        P2 = P.copy()
        P2[:, 0] = ec[0] + dx * (1.0 + k)
        moved = max(moved, float(np.abs(P2[:, 0] - P[:, 0]).max()))
        _set_world(o, P2)
    log(f"widen: cheeks and jaw {amt * 100:.1f} % wider ({top / iod:.2f}-{bot / iod:.2f} IOD under the eyes, fading out by "
        f"{und / iod:.2f}; in front of {fr_ * 100:.1f}-{bk_ * 100:.1f} cm behind the eyes' front), up to "
        f"{moved * 1000:.1f} mm")


def _texture_mask(basemesh, m, head_faces, W_, H_):
    """A vertex weight rasterised into the head texture over the head's faces (as scan_wrap.clean_eye_corners)."""
    me = basemesh.data
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    tv = np.empty(n * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tv)
    tl = np.empty(n * 3, np.int64)
    me.loop_triangles.foreach_get("loops", tl)
    tp = np.empty(n, np.int64)
    me.loop_triangles.foreach_get("polygon_index", tp)
    tv, tl = tv.reshape(-1, 3), tl.reshape(-1, 3)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2) * np.array([W_, H_])
    sel = head_faces[tp] & (m[tv].max(1) > 0.01)
    mask = np.zeros((H_, W_), np.float32)
    for t in np.nonzero(sel)[0]:
        P = uv[tl[t]]
        x0, y0 = np.floor(P.min(0)).astype(int)
        x1, y1 = np.ceil(P.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W_ - 1), min(y1, H_ - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        Q = np.stack([gx.ravel(), gy.ravel()], 1)
        T = np.array([[P[1, 0] - P[0, 0], P[2, 0] - P[0, 0]], [P[1, 1] - P[0, 1], P[2, 1] - P[0, 1]]])
        if abs(np.linalg.det(T)) < 1e-9:
            continue
        b = np.linalg.solve(T, (Q - P[0]).T).T
        w = np.stack([1 - b.sum(1), b[:, 0], b[:, 1]], 1)
        ins = (w >= -0.01).all(1)
        val = (w[ins] * m[tv[t]]).sum(1)
        yy, xx = (Q[ins, 1] - 0.5).astype(int), (Q[ins, 0] - 0.5).astype(int)
        mask[yy, xx] = np.maximum(mask[yy, xx], val)
    return mask


def _head_faces(basemesh):
    a = basemesh.data.attributes.get("scan_head")
    if a is None:
        return None
    hk = np.empty(len(basemesh.data.polygons), np.int32)
    a.data.foreach_get("value", hk)
    return hk == 1


def _polyline_dist(V, pts):
    d = np.full(len(V), np.inf)
    for a, b in zip(pts[:-1], pts[1:]):
        ab = b - a
        t = np.clip(((V - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
        d = np.minimum(d, np.linalg.norm(V - (a + t[:, None] * ab), axis=1))
    return d


BROWS = ([70, 63, 105, 66, 107], [46, 53, 52, 65, 55], [300, 293, 334, 296, 336], [276, 283, 282, 295, 285])


def texture(basemesh, rig, ff, root):
    maps = json.loads(basemesh.get("scan_head_maps", "{}") or "{}")
    hf = _head_faces(basemesh)
    if not maps.get("color") or hf is None:
        log("texture: no head texture")
        return
    V = SW.world_verts(basemesh)
    A = SW.anchor_points(basemesh, root)
    img = bpy.data.images.load(maps["color"], check_existing=False)
    W_, H_ = img.size
    px = np.empty(W_ * H_ * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(H_, W_, 4)
    lw = np.array([0.2126, 0.7152, 0.0722], np.float32)
    if ff.get("brows"):
        b = ff["brows"]
        reach = float(b.get("reach", 0.004))
        m = np.zeros(len(V))
        for up, lo in ((BROWS[0], BROWS[1]), (BROWS[2], BROWS[3])):
            if not all(k in A for k in up + lo):
                continue
            mid = np.array([(A[u] + A[l]) / 2 for u, l in zip(up, lo)])
            d = _polyline_dist(V, mid)
            m = np.maximum(m, 1.0 - SW.smoothstep(reach, reach * 1.6, d))
        mask = _texture_mask(basemesh, m, hf, W_, H_)
        ys, xs = np.nonzero(mask > 0.01)
        if len(ys):
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            c = px[y0:y1, x0:x1, :3]
            mk = mask[y0:y1, x0:x1]
            lum = c @ lw
            ls = float(np.percentile(lum[mk > 0.05], 80))
            hairy = np.clip((ls - lum) / (0.4 * ls), 0.0, 1.0)
            k = mk * hairy
            grey = lum[..., None]
            c2 = c + (grey - c) * (float(b.get("desat", 0.35)) * k)[..., None]
            c2 = c2 * (1.0 - float(b.get("dark", 0.45)) * k - float(b.get("fill", 0.12)) * mk)[..., None]
            px[y0:y1, x0:x1, :3] = np.clip(c2, 0.0, 1.0)
            l0 = float(np.median(lum[(mk > 0.5) & (hairy > 0.3)])) if ((mk > 0.5) & (hairy > 0.3)).any() else 0.0
            l1 = float(np.median((c2 @ lw)[(mk > 0.5) & (hairy > 0.3)])) if ((mk > 0.5) & (hairy > 0.3)).any() else 0.0
            log(f"brows: {int((mask > 0.5).sum())} texels, the brow hairs' median value {l0:.3f} -> {l1:.3f} (skin "
                f"{ls:.3f})")
    if ff.get("eye_corners"):
        reach = float(ff["eye_corners"].get("reach", 0.004))
        m = np.zeros(len(V))
        for k in (33, 133, 362, 263):
            if k in A:
                m = np.maximum(m, 1.0 - SW.smoothstep(reach, reach * 1.5, np.linalg.norm(V - A[k], axis=1)))
        mask = _texture_mask(basemesh, m, hf, W_, H_)
        ys, xs = np.nonzero(mask > 0.01)
        if len(ys):
            pad = 40
            y0, y1 = max(ys.min() - pad, 0), min(ys.max() + 1 + pad, H_)
            x0, x1 = max(xs.min() - pad, 0), min(xs.max() + 1 + pad, W_)
            c = px[y0:y1, x0:x1, :3]
            mk = mask[y0:y1, x0:x1]
            mx, mn = c.max(-1), c.min(-1)
            sat = (mx - mn) / np.maximum(mx, 1e-4)
            white = SW.smoothstep(0.2, 0.08, sat) * SW.smoothstep(-0.02, 0.04, c[..., 2] - c[..., 0] * 0.8)
            skin = (mk > 0.01) & (white < 0.2)
            ref = np.median(c[skin], axis=0) if skin.sum() > 20 else np.median(c.reshape(-1, 3), axis=0)
            k = (mk * white)[..., None]
            px[y0:y1, x0:x1, :3] = c + (ref[None, None] - c) * k
            log(f"eye corners: {int(((mk * white) > 0.5).sum())} grey-blue texels at the corners take the skin "
                f"{np.round(ref, 3).tolist()}")
    if ff.get("temples"):
        # ("temples" {top, shade}) the skin beside the face, outside its outline (MediaPipe's oval, by height) and in
        # front of the ears, from the jaw's angles up to `top` IOD over the eyes, painted with the skin just inside
        # the outline x `shade`: the scan bakes its hair onto the template's skin there, and where the cards keep off
        # the face, in profile, it reads as a pale grey veil over the temple and cheek
        tp_ = ff["temples"]
        ey = _eyes(rig)
        OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148,
                176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
        O = np.array([A[k] for k in OVAL if k in A])
        if ey is not None and len(O) > 20 and all(k in A for k in (234, 454, 136, 365)):
            cr, cl, iod, ef = ey
            ec = (cr + cl) / 2
            oz, ow = O[:, 2] - ec[2], np.abs(O[:, 0] - ec[0])
            bins = np.linspace(oz.min(), oz.max(), 24)
            bw = np.array([ow[np.abs(oz - b) < 0.006].max() if (np.abs(oz - b) < 0.006).any() else np.nan for b in bins])
            ok = np.isfinite(bw)
            hw = np.interp(V[:, 2] - ec[2], bins[ok], bw[ok])
            dx = np.abs(V[:, 0] - ec[0])
            z_lo = float(max(A[136][2], A[365][2]))   # the jaw's lower outline (MakeHuman has no anchors at its angles)
            z_hi = ec[2] + float(tp_.get("top", 0.35)) * iod
            y_ear = float(max(A[234][1], A[454][1])) + float(tp_.get("ear", 0.012))
            zone = SW.smoothstep(z_lo - 0.005, z_lo + 0.005, V[:, 2]) * (1.0 - SW.smoothstep(z_hi - 0.008, z_hi, V[:, 2])) * \
                (1.0 - SW.smoothstep(y_ear - 0.006, y_ear, V[:, 1]))
            if tp_.get("out") is not None:
                # (`out`, IOD: from that far out of the face's middle instead of the oval, whose side anchors lie by
                # the ears on the fitted head: outside them the first build painted only behind the ears)
                hw = np.full(len(V), float(tp_["out"]) * iod)
            m_out = SW.smoothstep(hw + 0.001, hw + 0.005, dx) * zone
            m_in = SW.smoothstep(hw - 0.014, hw - 0.009, dx) * (1.0 - SW.smoothstep(hw - 0.005, hw - 0.002, dx)) * zone
            mask = _texture_mask(basemesh, m_out, hf, W_, H_)
            inner = _texture_mask(basemesh, m_in, hf, W_, H_)
            if (inner > 0.5).sum() > 50 and (mask > 0.01).any():
                ref = np.median(px[..., :3][inner > 0.5], axis=0) * float(tp_.get("shade", 0.96))
                k = mask[..., None]
                px[..., :3] = px[..., :3] + (ref[None, None] - px[..., :3]) * k
                log(f"temples: {int((mask > 0.5).sum())} texels beside the face painted with the skin inside its "
                    f"outline {np.round(ref, 3).tolist()} ({int((inner > 0.5).sum())} texels sampled)")
    if ff.get("temple_skin"):
        # ("temple_skin" {beyond, z, ear, fade, blur, shade}) the head texture beside the face, from `beyond` metres
        # outside each outer eye corner back to `ear` metres in front of the ear (MakeHuman's "ears" group), `z`
        # [bottom, top] metres from the eyes' centre, soft edges over `fade`: with `blur` (texels) its own texture
        # blurred that much (normalised over the head's texels: the strands go, its tone and shading stay) x `shade`,
        # else the skin just outside the eye's outer corner (one flat colour, which gives a large flat patch). The
        # portrait's and the scan's hair painted there can be too close to the skin's colour for a colour mask, and
        # shows between the hair cards and the cheek in profile as a pale streaky strip (`temples` stops at
        # MediaPipe's face side landmarks, well in front of the ears)
        ts = ff["temple_skin"]
        ey = _eyes(rig)
        vg = basemesh.vertex_groups.get("ears")
        if ey is not None and 33 in A and 263 in A and vg is not None:
            cr, cl, iod, ef = ey
            ec = (cr + cl) / 2
            ear = np.zeros(len(V), bool)
            for v in basemesh.data.vertices:
                for g in v.groups:
                    if g.group == vg.index and g.weight > 0.5:
                        ear[v.index] = True
            fade = float(ts.get("fade", 0.006))
            zb, zt = (float(x) for x in ts.get("z", (-0.045, 0.03)))
            m_out = np.zeros(len(V))
            m_in = np.zeros(len(V))
            for s in (-1.0, 1.0):
                corner = A[33] if (A[33][0] - ec[0]) * s > 0 else A[263]
                xin = abs(float(corner[0] - ec[0])) + float(ts.get("beyond", 0.01))
                es = ear & ((V[:, 0] - ec[0]) * s > 0)
                if not es.any():
                    continue
                ey_ = float(V[es, 1].min()) - float(ts.get("ear", 0.004))
                dx = (V[:, 0] - ec[0]) * s
                dz = V[:, 2] - ec[2]
                zone = SW.smoothstep(zb - fade, zb, dz) * (1.0 - SW.smoothstep(zt, zt + fade, dz)) * \
                    (1.0 - SW.smoothstep(ey_ - fade, ey_, V[:, 1])) * (dx > 0)
                m_out = np.maximum(m_out, SW.smoothstep(xin, xin + fade, dx) * zone)
                m_in = np.maximum(m_in, ((dx > xin - 0.012) & (dx < xin - 0.004) & (dz > -0.03) & (dz < -0.012) &
                                         (V[:, 1] < ey_)).astype(float))
            mask = _texture_mask(basemesh, m_out, hf, W_, H_)
            inner = _texture_mask(basemesh, m_in, hf, W_, H_)
            if ts.get("blur") and (mask > 0.01).any():
                ys, xs = np.nonzero(mask > 0.01)
                pad = int(3 * float(ts["blur"])) + 8
                y0, y1 = max(ys.min() - pad, 0), min(ys.max() + 1 + pad, H_)
                x0, x1 = max(xs.min() - pad, 0), min(xs.max() + 1 + pad, W_)
                cov = _texture_mask(basemesh, np.ones(len(V)), hf, W_, H_)[y0:y1, x0:x1]
                c = px[y0:y1, x0:x1, :3]
                sg = float(ts["blur"])
                num = SW.gauss_blur(c * cov[..., None], sg)
                den = SW.gauss_blur(cov, sg)
                fill = num / np.maximum(den, 1e-4)[..., None] * float(ts.get("shade", 1.0))
                if ts.get("warm") and (inner > 0.5).sum() > 50:
                    # (`warm`, off by default) the blurred fill's hue and chroma pulled that far to the skin's by the
                    # eyes' outer corners, its lightness kept (hair painted above the glasses' arm otherwise blurs to
                    # a blue-grey patch)
                    lw = np.array([0.2126, 0.7152, 0.0722], np.float32)
                    ref = np.median(px[..., :3][inner > 0.5], axis=0)
                    tgt = (fill @ lw)[..., None] * (ref / max(float(ref @ lw), 1e-4))[None, None]
                    fill = fill + (tgt - fill) * float(ts["warm"])
                k = mask[y0:y1, x0:x1, None]
                px[y0:y1, x0:x1, :3] = c + (fill - c) * k
                log(f"temple skin: {int((mask > 0.5).sum())} texels beside the face back to the ears blurred over "
                    f"{sg:.0f} texels (their strands smoothed, tone kept)")
            elif (inner > 0.5).sum() > 50 and (mask > 0.01).any():
                ref = np.median(px[..., :3][inner > 0.5], axis=0) * float(ts.get("shade", 0.95))
                k = mask[..., None]
                px[..., :3] = px[..., :3] + (ref[None, None] - px[..., :3]) * k
                log(f"temple skin: {int((mask > 0.5).sum())} texels beside the face back to the ears painted with "
                    f"the skin by the eyes' outer corners {np.round(ref, 3).tolist()} ({int((inner > 0.5).sum())} "
                    f"texels sampled)")
            else:
                log(f"temple skin: skipped ({int((inner > 0.5).sum())} reference texels)")
    if ff.get("mouth_dark"):
        # ("mouth_dark" {from, to, dark}) the mouth's inside (scan_wrap.mouth_inside: its own UV island) darkened to
        # `dark` from `from` to `to` metres behind the mouth's middle (A13/A14): the cheeks' inner walls lie over the
        # molars (the arch scaled 0.95 still touches them), and shaded as skin with its pores, lit by the blue sky,
        # they read as grey-blue speckle on the back teeth at the mouth's corners in dialogue
        md = ff["mouth_dark"]
        vg = basemesh.vertex_groups.get("body")
        if vg is not None and 13 in A and 14 in A:
            in_body = np.zeros(len(V), bool)
            for v in basemesh.data.vertices:
                in_body[v.index] = any(g.group == vg.index and g.weight > 0.5 for g in v.groups)
            inside, _ = SW.mouth_inside(basemesh, in_body, hf, root)
            c = (A[13] + A[14]) / 2
            wv = inside * SW.smoothstep(float(md.get("from", 0.003)), float(md.get("to", 0.012)), V[:, 1] - c[1])
            mask = _texture_mask(basemesh, wv, hf, W_, H_)
            px[..., :3] *= (1.0 - (1.0 - float(md.get("dark", 0.35))) * mask)[..., None]
            log(f"mouth dark: {int((mask > 0.5).sum())} texels of the mouth's inside ({int(inside.sum())} vertices) "
                f"darkened to x{float(md.get('dark', 0.35)):.2f} with depth")
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = maps["color"]
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def teeth(rig, t):
    """("teeth" {scale, back}) the teeth's arch narrowed and shortened about its middle (x and y, level) by `scale`
    and moved `back` metres: fitted rigidly into the fitted mouth, the upper teeth can lie on the lips' and cheeks'
    inner surface and z-fight it at the mouth's corners in dialogue."""
    for o in [o for o in rig.children if o.type == 'MESH' and "teeth" in o.name.lower()]:
        P = SW.world_verts(o)
        c = 0.5 * (P.min(0) + P.max(0))
        s = float(t.get("scale", 0.95))
        P2 = P.copy()
        P2[:, :2] = c[:2] + (P[:, :2] - c[:2]) * s
        P2[:, 1] += float(t.get("back", 0.0))
        _set_world(o, P2)
        log(f"teeth: {o.name} arch x{s:.2f} about its middle, {float(t.get('back', 0.0)) * 1000:.1f} mm back (moved up "
            f"to {np.linalg.norm(P2 - P, axis=1).max() * 1000:.1f} mm)")
        if t.get("dilate"):
            # (`dilate`, texels) MakeHuman's teeth texture is small islands on black (alpha 0): the molars, small on
            # screen, read their mips' black margins as a grey speckled blob at the mouth's corners in the game. A
            # copy with each island's colour grown out over the black (the asset's own file is shared, untouched)
            for m in o.data.materials:
                if not (m and m.node_tree):
                    continue
                for n in m.node_tree.nodes:
                    if n.type != 'TEX_IMAGE' or not n.image or n.image.name.endswith("_dil"):
                        continue
                    img = n.image
                    W_, H_ = img.size
                    px = np.empty(W_ * H_ * 4, np.float32)
                    img.pixels.foreach_get(px)
                    px = px.reshape(H_, W_, 4)
                    rgb, known = px[..., :3].copy(), px[..., 3] > 0.5
                    n0 = int((~known).sum())
                    for _ in range(int(t["dilate"])):
                        acc = np.zeros_like(rgb)
                        cnt = np.zeros(known.shape, np.float32)
                        for ax, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
                            k_ = np.roll(known, sh, ax)
                            acc += np.roll(rgb, sh, ax) * k_[..., None]
                            cnt += k_
                        grow = ~known & (cnt > 0)
                        rgb[grow] = acc[grow] / cnt[grow][:, None]
                        known = known | grow
                    out = px.copy()
                    out[..., :3] = rgb
                    if t.get("molars"):
                        # ("molars" {from, to, shade, blur}) the back teeth, `from`-`to` metres behind the front of
                        # the arch, darkened to `shade` and their texels blurred (a box over `blur` texels, three
                        # passes): MakeHuman's molar crowns are light grey with dark fissures, which read as grey
                        # speckle at the mouth's corners in dialogue; deep in the mouth they lie in its shadow
                        mo = t["molars"]
                        depth = P2[:, 1] - float(P2[:, 1].min())
                        wv = SW.smoothstep(float(mo.get("from", 0.012)), float(mo.get("to", 0.02)), depth)
                        mk = _texture_mask(o, wv, np.ones(len(o.data.polygons), bool), W_, H_)
                        if (mk > 0.01).any():
                            bl = rgb.copy()
                            r_ = int(mo.get("blur", 3))
                            for _ in range(3):
                                acc = np.zeros_like(bl)
                                for ax in (0, 1):
                                    for sh in range(-r_, r_ + 1):
                                        acc += np.roll(bl, sh, ax)
                                bl = acc / (2 * (2 * r_ + 1))
                            k_ = mk[..., None]
                            sm = rgb + (bl - rgb) * k_
                            out[..., :3] = sm * (1.0 - (1.0 - float(mo.get("shade", 0.6))) * k_)
                            if mo.get("tint"):
                                # (`tint` [r, g, b], off by default) the darkened back teeth also x this (sRGB
                                # texels): grey, in the mouth's shade under the blue sky, they read slate-blue; warmed
                                # they read as the mouth's dark
                                out[..., :3] *= 1.0 - (1.0 - np.asarray(mo["tint"], np.float32)) * k_
                            log(f"teeth: {int((mk > 0.5).sum())} texels of the back teeth ({float(mo.get('from', 0.012)) * 1000:.0f}"
                                f"-{float(mo.get('to', 0.02)) * 1000:.0f} mm behind the arch's front) darkened to "
                                f"x{float(mo.get('shade', 0.6)):.2f} and smoothed")
                    new = bpy.data.images.new(img.name + "_dil", W_, H_, alpha=True)
                    new.colorspace_settings.name = img.colorspace_settings.name
                    new.pixels.foreach_set(out.ravel())
                    new.pack()
                    n.image = new
                    log(f"teeth: {img.name} islands grown {int(t['dilate'])} texels over the black "
                        f"({n0 - int((~known).sum())} of {n0} background texels filled)")


def _lab(rgb):
    """sRGB (0-1) -> CIE Lab (D65)."""
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    X = c @ np.array([0.4124, 0.3576, 0.1805]) / 0.95047
    Y = c @ np.array([0.2126, 0.7152, 0.0722])
    Z = c @ np.array([0.0193, 0.1192, 0.9505]) / 1.08883
    f = lambda t: np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16.0 / 116.0)
    return np.stack([116.0 * f(Y) - 16.0, 500.0 * (f(X) - f(Y)), 200.0 * (f(Y) - f(Z))], -1)


def neck_skin(basemesh, rig, ns):
    """("neck_skin" {z, x, ny, y}) the body's faces on the front of the neck that scan_wrap classed as cloth but whose
    colour in the body texture is skin (Lab L 30-88, a 6-32, b 9-36: not the white T-shirt nor the black jacket)
    become skin: `z` [top, bottom] metres under the eyes' centre, within `x` metres of the middle, facing forward
    (normal y under `ny`; the character faces -y) and in front of `y` metres behind the eyes. Shaded as fabric (no
    subsurface, a rim) the lower half of the neck down to the collar reads as a lighter rectangular patch."""
    a = basemesh.data.attributes.get("scan_cloth")
    ey = _eyes(rig)
    mat = basemesh.active_material
    if a is None or ey is None or mat is None or not mat.node_tree:
        log("neck skin: no cloth attribute, eyes or material")
        return
    col = next((n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image and
                not any(l.to_node.type in ('NORMAL_MAP', 'BUMP') for o in n.outputs for l in o.links)), None)
    if col is None:
        log("neck skin: no colour image")
        return
    cr, cl, iod, ef = ey
    ec = (cr + cl) / 2
    me = basemesh.data
    n = len(me.polygons)
    ck = np.empty(n, np.int32)
    a.data.foreach_get("value", ck)
    V = SW.world_verts(basemesh)
    loops = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", loops)
    ls = np.empty(n, np.int64)
    me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(n, np.int64)
    me.polygons.foreach_get("loop_total", lt)
    C = np.add.reduceat(V[loops], ls) / lt[:, None]
    p0, p1, p2 = V[loops[ls]], V[loops[ls + 1]], V[loops[ls + 2]]
    N = np.cross(p1 - p0, p2 - p0)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    z0, z1 = (float(x) for x in ns.get("z", (0.06, 0.2)))
    zr = C[:, 2] - ec[2]
    cand = (ck == 1) & (zr < -z0) & (zr > -z1) & (np.abs(C[:, 0] - ec[0]) < float(ns.get("x", 0.07))) & \
        (N[:, 1] < float(ns.get("ny", -0.2))) & (C[:, 1] < ec[1] + float(ns.get("y", 0.075)))
    if not cand.any():
        log("neck skin: no cloth faces on the front of the neck")
        return
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    UVc = np.add.reduceat(uv.reshape(-1, 2).astype(np.float64), ls) / lt[:, None]
    img = col.image
    W_, H_ = img.size
    px = np.empty(W_ * H_ * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(H_, W_, 4)
    idx = np.nonzero(cand)[0]
    xi = np.clip((UVc[idx, 0] % 1.0 * W_).astype(int), 0, W_ - 1)
    yi = np.clip((UVc[idx, 1] % 1.0 * H_).astype(int), 0, H_ - 1)
    lab = _lab(np.clip(px[yi, xi, :3].astype(np.float64), 0, 1))
    skin = (lab[:, 0] > 30) & (lab[:, 0] < 88) & (lab[:, 1] > 6) & (lab[:, 1] < 32) & (lab[:, 2] > 9) & (lab[:, 2] < 36)
    ck[idx[skin]] = 0
    a.data.foreach_set("value", ck)
    me.update()
    log(f"neck skin: {int(skin.sum())} of {len(idx)} cloth faces on the front of the neck "
        f"({z0 * 100:.0f}-{z1 * 100:.0f} cm under the eyes) skin-coloured in the body texture: now skin "
        f"(median Lab {np.round(np.median(lab[skin], axis=0), 1).tolist() if skin.any() else []}; the rest "
        f"{np.round(np.median(lab[~skin], axis=0), 1).tolist() if (~skin).any() else []})")


def collar_hair(basemesh, rig, ch):
    """("collar_hair" {z, x, ny, ref, dilate}, off by default) the scan's hair baked onto the back of the jacket under
    the long hair, painted as the jacket: cloth faces facing back (normal y over `ny`; the character faces -y), `z`
    [top, bottom] metres under the eyes' centre and within `x` metres of the middle, whose texel is hair-coloured (Lab
    L > 35, a > 5, b > 8) take the median colour of the cloth facing back `ref` [top, bottom] under the eyes (the
    jacket), or `color` (hex, sRGB) when given, over their UV triangles grown by `dilate` texels. Left as
    hair-coloured cloth it catches the backlight as a glowing fringe along the hair's ends. The `ref` median can
    itself pick up hair-coloured texels; give `color` in that case."""
    a = basemesh.data.attributes.get("scan_cloth")
    ey = _eyes(rig)
    mat = basemesh.active_material
    if a is None or ey is None or mat is None or not mat.node_tree:
        log("collar hair: no cloth attribute, eyes or material")
        return
    col = next((n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image and
                not any(l.to_node.type in ('NORMAL_MAP', 'BUMP') for o in n.outputs for l in o.links)), None)
    if col is None:
        log("collar hair: no colour image")
        return
    cr, cl, iod, ef = ey
    ec = (cr + cl) / 2
    me = basemesh.data
    n = len(me.polygons)
    ck = np.empty(n, np.int32)
    a.data.foreach_get("value", ck)
    V = SW.world_verts(basemesh)
    loops = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", loops)
    ls = np.empty(n, np.int64)
    me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(n, np.int64)
    me.polygons.foreach_get("loop_total", lt)
    C = np.add.reduceat(V[loops], ls) / lt[:, None]
    p0, p1, p2 = V[loops[ls]], V[loops[ls + 1]], V[loops[ls + 2]]
    N = np.cross(p1 - p0, p2 - p0)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    zr = C[:, 2] - ec[2]
    back = (ck == 1) & (N[:, 1] > float(ch.get("ny", 0.3))) & (np.abs(C[:, 0] - ec[0]) < float(ch.get("x", 0.15)))
    z0, z1 = (float(v) for v in ch.get("z", (0.08, 0.24)))
    r0, r1 = (float(v) for v in ch.get("ref", (0.27, 0.4)))
    cand = back & (zr < -z0) & (zr > -z1)
    ref = back & (zr < -r0) & (zr > -r1)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    UVc = np.add.reduceat(uv.reshape(-1, 2).astype(np.float64), ls) / lt[:, None]
    img = col.image
    W_, H_ = img.size
    px = np.empty(W_ * H_ * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(H_, W_, 4)

    def texel(idx):
        xi = np.clip((UVc[idx, 0] % 1.0 * W_).astype(int), 0, W_ - 1)
        yi = np.clip((UVc[idx, 1] % 1.0 * H_).astype(int), 0, H_ - 1)
        return px[yi, xi, :3].astype(np.float64)
    ci, ri = np.nonzero(cand)[0], np.nonzero(ref)[0]
    if not len(ci) or not len(ri):
        log("collar hair: no cloth faces at the back")
        return
    lab = _lab(np.clip(texel(ci), 0, 1))
    hair = (lab[:, 0] > 35) & (lab[:, 1] > 5) & (lab[:, 2] > 8)
    jacket = np.median(texel(ri), axis=0)
    if ch.get("color"):
        hx_ = str(ch["color"]).lstrip("#")
        jacket = np.array([int(hx_[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])
    faces = np.zeros(n, bool)
    faces[ci[hair]] = True
    mask = _texture_mask(basemesh, np.ones(len(V)), faces, W_, H_) > 0.5
    k = int(ch.get("dilate", 3))
    m0 = mask.copy()
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            mask |= np.roll(np.roll(m0, dy, 0), dx, 1)
    px[mask, :3] = jacket.astype(np.float32)
    img.pixels.foreach_set(px.ravel())
    img.update()
    if img.filepath_raw:
        img.save()
    log(f"collar hair: {int(hair.sum())} of {len(ci)} cloth faces on the back {z0 * 100:.0f}-{z1 * 100:.0f} cm under "
        f"the eyes hair-coloured (median Lab {np.round(np.median(lab[hair], axis=0), 1).tolist() if hair.any() else []}"
        f"): {int(mask.sum())} texels painted as the jacket (sRGB {np.round(jacket * 255).astype(int).tolist()})")


def apply(basemesh, rig, ff, cid, root):
    if ff.get("widen"):
        widen(basemesh, rig, ff["widen"])
    if ff.get("teeth"):
        teeth(rig, ff["teeth"])
    if ff.get("brows") or ff.get("eye_corners") or ff.get("temples") or ff.get("temple_skin") or ff.get("mouth_dark"):
        texture(basemesh, rig, ff, root)
    if ff.get("neck_skin"):
        neck_skin(basemesh, rig, ff["neck_skin"])
    if ff.get("collar_hair"):
        collar_hair(basemesh, rig, ff["collar_hair"])
