"""Project a face photo onto a MakeHuman skin texture.

Input: <job.json> with mesh npz (deformed verts, body triangles, per-corner UVs, normals), camera from
face_solve.py, photo + landmarks, base skin texture, options. Output: skin texture PNG.

Steps: clean the photo (inpaint eyes, open mouth, glasses rims), remove most of the photo's lighting
(keep detail, flatten shading), z-buffer the head from the photo camera, rasterise every face triangle
in UV space sampling the photo, then blend into a colour-matched base skin with a feathered mask.
"""
import json, sys, os
import numpy as np, cv2

LEFT_EYE = [263, 249, 390, 373, 374, 380, 381, 382, 362, 466, 388, 387, 386, 385, 384, 398]
RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 246, 161, 160, 159, 158, 157, 173]
INNER_LIPS = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191]
OUTER_LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149,
        150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
CHEEKS = [50, 280, 101, 330, 205, 425, 36, 266]


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def poly_mask(shape, pts, dilate=0):
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillConvexPoly(m, cv2.convexHull(np.round(pts).astype(np.int32)), 255)
    if dilate > 0:
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate + 1, 2 * dilate + 1)))
    return m


def glasses_mask(gray, L, face_px):
    """Thin rims around the eyes, the bridge and the temples: black-hat/top-hat lines inside a band."""
    h, w = gray.shape
    band = np.zeros((h, w), np.uint8)
    for eye in (LEFT_EYE, RIGHT_EYE):
        P = L[eye]
        c = P.mean(0)
        ew = np.ptp(P[:, 0])
        cv2.ellipse(band, (int(c[0]), int(c[1] - ew * 0.08)), (int(ew * 1.25), int(ew * 0.95)), 0, 0, 360, 255, -1)
        inner = np.zeros_like(band)
        cv2.ellipse(inner, (int(c[0]), int(c[1])), (int(ew * 0.62), int(ew * 0.42)), 0, 0, 360, 255, -1)
        band[inner > 0] = 0
    # bridge between the inner eye corners, and temples out to the face edge
    a, b = L[133], L[362]
    cv2.line(band, tuple(np.int32(a)), tuple(np.int32(b)), 255, int(face_px * 0.05))
    for corner, edge in ((L[33], L[234]), (L[263], L[454])):
        cv2.line(band, tuple(np.int32(corner)), tuple(np.int32(edge)), 255, int(face_px * 0.045))
    k = max(3, int(face_px * 0.03)) | 1
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, se).astype(np.float32)
    th = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, se).astype(np.float32)
    resp = np.maximum(bh, th * 0.8)
    sel = resp[band > 0]
    thr = max(10.0, float(sel.mean() + 1.4 * sel.std())) if sel.size else 255
    m = ((resp > thr) & (band > 0)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    return m


def rim_smooth(img, L, face_px, o):
    """(job "glasses_smooth", off by default) thin metal rims taken out of the photo by a median filter over a band
    round each eye, with no detection: thin rims can be too faint for glasses_mask's threshold, and its band stops
    short of large frames' lower rims. o: rx, ry, dy (the band's radii and downward offset, in the larger eye's
    widths), k (filter size, face widths), passes, feather (face widths). The eyes themselves (inpainted anyway) stay
    out of it."""
    ew = max(np.ptp(L[LEFT_EYE][:, 0]), np.ptp(L[RIGHT_EYE][:, 0]))
    band = np.zeros(img.shape[:2], np.uint8)
    for eye in (LEFT_EYE, RIGHT_EYE):
        c = L[eye].mean(0)
        cv2.ellipse(band, (int(c[0]), int(c[1] + ew * o.get("dy", 0.18))),
                    (int(ew * o.get("rx", 1.55)), int(ew * o.get("ry", 1.4))), 0, 0, 360, 255, -1)
        inner = np.zeros_like(band)
        cv2.ellipse(inner, (int(c[0]), int(c[1])), (int(ew * 0.62), int(ew * 0.42)), 0, 0, 360, 255, -1)
        band[inner > 0] = 0
    cv2.line(band, tuple(np.int32(L[133])), tuple(np.int32(L[362])), 255, int(face_px * 0.05))
    for corner, edge in ((L[33], L[234]), (L[263], L[454])):
        cv2.line(band, tuple(np.int32(corner)), tuple(np.int32(edge)), 255, int(face_px * 0.045))
    w = cv2.GaussianBlur(band.astype(np.float32) / 255, (0, 0), max(1.0, face_px * o.get("feather", 0.02)))
    ks = max(3, int(face_px * o.get("k", 0.028))) | 1
    med = img
    for _ in range(int(o.get("passes", 2))):
        med = cv2.medianBlur(med, ks)
    return (img * (1 - w[..., None]) + med * w[..., None]).astype(np.uint8)


# (job "mouth_lift", off by default) regions round the mouth, by landmarks
MOUTH_REGIONS = {
    # the upper lip's red, between its outer and inner contours
    "upper": [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191, 78],
    # the skin between the upper lip and the nose's base (philtrum and the band over the red)
    "above": [61, 186, 92, 165, 167, 2, 393, 391, 322, 410, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185],
    # the lower lip's red
    "lower": [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 78],
}


def mouth_lift(flat, L, face_px, face_color, o):
    """(job "mouth_lift", off by default) the photo's colour round the mouth lifted toward the cheek's: in the game
    (SSAO, the key light from above) the upper lip and the skin over it can read as a dark grey band and the hollow
    under the lower lip as a grey patch, though the texture there is 0.7-1.1 of the cheek's lightness. o: {region:
    {to, k, warm}, "feather": face widths} with region "upper", "above", "lower" (MOUTH_REGIONS) or "chin" (under the
    lower lip's red, down `depth` (default 0.45) of the way to the chin's tip): each region's low-pass luminance
    raised toward `to` x the cheek's (never lowered; gain^k), its chromaticity moved `warm` of the way to the cheek's.
    flat: linear RGB photo; returns it changed."""
    lumw = np.array([0.2126, 0.7152, 0.0722], np.float32)
    Y = flat @ lumw
    yc = float(face_color @ lumw)
    chroma_c = face_color / max(yc, 1e-6)
    fe = max(1.0, face_px * float(o.get("feather", 0.015)))
    out = flat.copy()
    for name, p in o.items():
        if not isinstance(p, dict):
            continue
        m = np.zeros(flat.shape[:2], np.uint8)
        if name == "chin":
            top = L[[146, 91, 181, 84, 17, 314, 405, 321, 375]]
            d = float(p.get("depth", 0.45))
            bot = top + (L[152] - L[17]) * d
            cv2.fillPoly(m, [np.round(np.concatenate([top, bot[::-1]])).astype(np.int32)], 255)
        else:
            cv2.fillPoly(m, [np.round(L[MOUTH_REGIONS[name]]).astype(np.int32)], 255)
        w =cv2.GaussianBlur(m.astype(np.float32) / 255, (0, 0), fe)
        sel = m > 0
        if not sel.any():
            continue
        y_reg = float(np.median(Y[sel]))
        gain = max(1.0, float(p.get("to", 0.8)) * yc / max(y_reg, 1e-6)) ** float(p.get("k", 1.0))
        ch = out / np.maximum(Y, 1e-6)[..., None]
        ch2 = ch + float(p.get("warm", 0.0)) * (chroma_c.reshape(1, 1, 3) - ch)
        new = ch2 * (Y * gain)[..., None]
        out = out * (1 - w[..., None]) + new * w[..., None]
        print(f"[texture] mouth_lift {name}: {int(sel.sum())} px at {y_reg / yc:.2f} of the cheek's lightness, x{gain:.2f}")
    return out


# (job "brow_deepen", off by default) each brow between its upper and lower MediaPipe contours
BROW_REGIONS = {"right": [70, 63, 105, 66, 107, 55, 65, 52, 53, 46],
                "left": [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]}


def brow_deepen(flat, L, face_px, face_color, o):
    """(job "brow_deepen", off by default) the photo's brows darkened and warmed before projection, where the white
    balance leaves dark brows blue-grey and too light to read in the game. o: to (the brow's median luminance x the
    cheek's), color (sRGB hex: its hue), k (0-1, how far), grow and feather (face widths: the contour polygon dilated,
    then softened), keep (0-1: the photo's own variation inside the brow kept, as (Y / median)^keep). flat: linear
    RGB; returns it."""
    lumw = np.array([0.2126, 0.7152, 0.0722], np.float32)
    Y = flat @ lumw
    yc = float(face_color @ lumw)
    h = str(o.get("color", "#2a1c15")).lstrip("#")
    col = srgb_to_lin(np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255)
    chroma_t = col / max(float(col @ lumw), 1e-6)
    m = np.zeros(flat.shape[:2], np.uint8)
    for ids in BROW_REGIONS.values():
        cv2.fillPoly(m, [np.round(L[ids]).astype(np.int32)], 255)
    g = int(round(face_px * float(o.get("grow", 0.008))))
    if g > 0:
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * g + 1, 2 * g + 1)))
    sel = m > 0
    if not sel.any():
        return flat
    w = cv2.GaussianBlur(m.astype(np.float32) / 255, (0, 0), max(1.0, face_px * float(o.get("feather", 0.01))))
    w = w * float(o.get("k", 1.0))
    y_med = float(np.median(Y[sel]))
    y_t = float(o.get("to", 0.3)) * yc
    rel = (np.maximum(Y, 1e-6) / max(y_med, 1e-6)) ** float(o.get("keep", 0.5))
    new = chroma_t.reshape(1, 1, 3) * (y_t * rel)[..., None]
    out = flat * (1 - w[..., None]) + new * w[..., None]
    print(f"[texture] brow_deepen: {int(sel.sum())} px at {y_med / yc:.2f} of the cheek's lightness -> {y_t / yc:.2f}")
    return out


def rasterize_depth(P2, Z, tris, shape):
    """Nearest-depth buffer of triangles (pixel coords P2, depth Z) at image resolution."""
    h, w = shape
    zb = np.full((h, w), np.inf, np.float32)
    for t in tris:
        p = P2[t]
        x0, y0 = np.floor(p.min(0)).astype(int)
        x1, y1 = np.ceil(p.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = p
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= -1e-4) & (l2 >= -1e-4) & (l3 >= -1e-4)
        if not inside.any():
            continue
        z = l1 * Z[t[0]] + l2 * Z[t[1]] + l3 * Z[t[2]]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        upd = inside & (z < sub)
        sub[upd] = z[upd]
    return zb


def main(job_path):
    job = json.load(open(job_path))
    mesh = np.load(job["mesh"])
    V, T, UV, N = mesh["V"], mesh["T"], mesh["UV"], mesh["N"]
    sol = json.load(open(job["solve"]))
    R, t, K = np.array(sol["R"]), np.array(sol["t"]), np.array(sol["K"])
    S = job.get("size", 4096)

    photo = cv2.cvtColor(cv2.imread(job["photo_png"]), cv2.COLOR_BGR2RGB)
    lm = json.load(open(job["photo_lm"]))
    L = np.array(lm["faces"][0]["pts"])[:, :2]
    h, w = photo.shape[:2]
    face_px = np.ptp(L[OVAL][:, 0])
    ignore = set(sol.get("ignore", [])) | set(job.get("ignore", []))
    # (job "tex_keep", off by default) regions left out of the shape fit but kept in the texture
    ignore -= set(job.get("tex_keep") or [])

    # ---------------------------------------------------------------- clean the photo
    clean = photo.copy()
    hole = np.zeros((h, w), np.uint8)
    for eye in (LEFT_EYE, RIGHT_EYE):
        hole |= poly_mask(photo.shape, L[eye], dilate=max(2, int(face_px * 0.012)))
    if "mouth" in ignore:
        hole |= poly_mask(photo.shape, L[INNER_LIPS], dilate=2)
    if job.get("glasses_in_photo"):
        gm = glasses_mask(cv2.cvtColor(photo, cv2.COLOR_RGB2GRAY), L, face_px)
        hole |= gm
        cv2.imwrite(job["out"].replace(".png", "_glassmask.png"), gm)
    clean = cv2.inpaint(clean, hole, max(3, int(face_px * 0.02)), cv2.INPAINT_TELEA)
    if job.get("glasses_smooth"):
        clean = rim_smooth(clean, L, face_px, job["glasses_smooth"])

    # ---------------------------------------------------------------- flatten the photo's lighting
    lin = srgb_to_lin(clean.astype(np.float32) / 255.0)
    Y = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    face_m = poly_mask(photo.shape, L[OVAL], dilate=int(face_px * 0.05)).astype(np.float32) / 255
    sig = face_px * 0.09
    low = cv2.GaussianBlur(Y * face_m, (0, 0), sig) / np.maximum(cv2.GaussianBlur(face_m, (0, 0), sig), 1e-4)
    cheek = np.zeros((h, w), np.uint8)
    for i in CHEEKS:
        cv2.circle(cheek, tuple(np.int32(L[i])), max(3, int(face_px * 0.04)), 255, -1)
    target = float(np.median(Y[cheek > 0]))
    k = job.get("delight", 0.7)
    gain = (target / np.maximum(low, 1e-4)) ** k
    flat = lin * gain[..., None]
    Yf = flat @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    hi = Yf > target * 1.5   # tame specular hot spots
    flat[hi] *= ((target * 1.5 + (Yf[hi] - target * 1.5) * 0.3) / Yf[hi])[:, None]
    face_color = np.median(flat[cheek > 0], axis=0)
    ref = job.get("skin_ref")
    if ref:
        r = srgb_to_lin(np.array([int(ref[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255)
        lum = lambda c: float(c @ np.array([0.2126, 0.7152, 0.0722]))
        wb = (r / lum(r)) / (face_color / lum(face_color))
        wb = wb ** job.get("wb_strength", 0.75)
        expo = (lum(r) / lum(face_color * wb)) ** job.get("exposure_strength", 0.6)
        flat = flat * (wb * expo).reshape(1, 1, 3)
        face_color = face_color * wb * expo
    if job.get("mouth_lift"):
        flat = mouth_lift(flat, L, face_px, face_color, job["mouth_lift"])
    if job.get("brow_deepen"):
        flat = brow_deepen(flat, L, face_px, face_color, job["brow_deepen"])

    # ---------------------------------------------------------------- project the head into the photo
    Pc = (R @ V.T).T + t.reshape(1, 3)
    Z = Pc[:, 2]
    P2 = np.stack([K[0, 0] * Pc[:, 0] / Z + K[0, 2], K[1, 1] * Pc[:, 1] / Z + K[1, 2]], 1)
    cam = -R.T @ t
    view = cam.reshape(1, 3) - V
    view /= np.linalg.norm(view, axis=1, keepdims=True)
    facing = np.clip(((N * view).sum(1) - 0.2) / 0.45, 0, 1)
    oval = L[OVAL].astype(np.float32).reshape(-1, 1, 2)
    inset = face_px * job.get("inset", 0.035)
    feather = face_px * 0.08
    sd = np.array([cv2.pointPolygonTest(oval, (float(x), float(y)), True) for x, y in P2])
    w_oval = np.clip((sd - inset) / feather, 0, 1)
    w_oval = w_oval * w_oval * (3 - 2 * w_oval)
    wv = facing * w_oval
    # around the eyes the photo is lashes, lenses and frames: fade to the base skin there
    eye_floor = job.get("eye_weight", 0.35)
    for eye in (LEFT_EYE, RIGHT_EYE):
        P = L[eye]; c = P.mean(0); ew = np.ptp(P[:, 0])
        de = np.linalg.norm((P2 - c) / np.array([ew * 0.75, ew * 0.55]), axis=1)
        wv *= eye_floor + (1 - eye_floor) * np.clip((de - 1.0) / 0.8, 0, 1)
    if job.get("no_forehead"):
        brow_y = min(L[105][1], L[334][1], L[66][1], L[296][1])
        span = face_px * 0.06
        wv *= np.clip((P2[:, 1] - (brow_y + span * 0.2)) / span, 0, 1)
    if "mouth" in ignore:
        mc = L[OUTER_LIPS].mean(0)
        mw = np.ptp(L[OUTER_LIPS][:, 0])
        dm = np.linalg.norm((P2 - mc) / np.array([mw * 0.85, mw * 0.6]), axis=1)
        wv *= np.clip((dm - 0.8) / 0.5, 0, 1)
    head_tris = T[(wv[T] > 0).any(1)]
    front = T[(facing[T] > 0).all(1) & (Z[T] > 0).all(1)]
    zbuf = rasterize_depth(P2, Z, front, (h, w))

    # ---------------------------------------------------------------- rasterise into UV space
    acc = np.zeros((S, S, 3), np.float32)
    wacc = np.zeros((S, S), np.float32)
    sel = np.flatnonzero((wv[T] > 0).any(1))
    tol = 0.004
    for ti in sel:
        tri = T[ti]
        uv = UV[ti] * np.array([S, S])
        uv[:, 1] = S - uv[:, 1]
        x0, y0 = np.floor(uv.min(0)).astype(int)
        x1, y1 = np.ceil(uv.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, S - 1), min(y1, S - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = uv
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
        if not inside.any():
            continue
        px = l1 * P2[tri[0], 0] + l2 * P2[tri[1], 0] + l3 * P2[tri[2], 0]
        py = l1 * P2[tri[0], 1] + l2 * P2[tri[1], 1] + l3 * P2[tri[2], 1]
        pz = l1 * Z[tri[0]] + l2 * Z[tri[1]] + l3 * Z[tri[2]]
        ww = l1 * wv[tri[0]] + l2 * wv[tri[1]] + l3 * wv[tri[2]]
        ix = np.clip(px.astype(int), 0, w - 1)
        iy = np.clip(py.astype(int), 0, h - 1)
        vis = pz <= zbuf[iy, ix] + tol
        ok = inside & vis & (ww > 0) & (px >= 0) & (px < w - 1) & (py >= 0) & (py < h - 1)
        if not ok.any():
            continue
        col = cv2.remap(flat, px[ok].astype(np.float32).reshape(-1, 1), py[ok].astype(np.float32).reshape(-1, 1),
                        cv2.INTER_LINEAR).reshape(-1, 3)
        gy, gx = ys[ok].astype(int), xs[ok].astype(int)
        acc[gy, gx] = col * ww[ok, None]
        wacc[gy, gx] = ww[ok]
    # soften the mask in UV space and fill tiny gaps
    filled = wacc > 0
    acc_col = np.where(filled[..., None], acc / np.maximum(wacc[..., None], 1e-6), 0)
    blur_r = max(2.0, S / 900)
    wsm = cv2.GaussianBlur(wacc, (0, 0), blur_r)
    num = cv2.GaussianBlur(acc_col * filled[..., None], (0, 0), blur_r * 0.6)
    den = cv2.GaussianBlur(filled.astype(np.float32), (0, 0), blur_r * 0.6)
    photo_uv = np.where(den[..., None] > 1e-3, num / np.maximum(den[..., None], 1e-6), 0)
    photo_uv = np.where(filled[..., None], acc_col, photo_uv)

    # ---------------------------------------------------------------- colour-matched base skin
    base = cv2.cvtColor(cv2.imread(job["base_texture"], cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    base = cv2.resize(base, (S, S), interpolation=cv2.INTER_CUBIC)
    base_lin = srgb_to_lin(base.astype(np.float32) / 255)
    core = wsm > 0.6
    base_mean = np.median(base_lin[core], axis=0) if core.any() else base_lin.reshape(-1, 3).mean(0)
    photo_mean = np.median(photo_uv[core], axis=0) if core.any() else face_color
    gain = np.clip(photo_mean / np.maximum(base_mean, 1e-4), 0.25, 4.0)
    base_lin = base_lin * gain.reshape(1, 1, 3)
    a = np.clip(wsm, 0, 1)[..., None]
    out = base_lin * (1 - a) + photo_uv * a
    cv2.imwrite(job["out"], cv2.cvtColor((lin_to_srgb(out) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR))
    cv2.imwrite(job["out"].replace(".png", "_clean.png"), cv2.cvtColor((lin_to_srgb(flat) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    json.dump({"skin_gain": gain.tolist(), "face_color": face_color.tolist()}, open(job["out"] + ".json", "w"))
    print(f"[texture] {os.path.basename(job['out'])} {S}px, gain {np.round(gain, 2)}, face texels {int(filled.sum())}")


if __name__ == "__main__":
    main(sys.argv[1])
