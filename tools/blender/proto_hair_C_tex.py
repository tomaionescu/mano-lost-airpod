"""Hair prototype C, step 3 (plain python3.11 + OpenCV, called by proto_hair_C.py): the shell's texture maps.

usage: python3.11 tools/blender/proto_hair_C_tex.py <work dir> [key=value ...]
Reads <work>/maps.npz (Blender bakes of the shell: coverage, 3D position, normal, flow, per-vertex scalars, the scan's
colour, AO; rows bottom-up like Blender images) and <work>/style.json. Writes albedo.png (sRGB), normal.png (tangent
space, OpenGL), rough.png and mask.png (R, G: the two fuzz layers' strands; B: the core's alpha at free tips and the
hairline; A: AO) into <work>.

Strands are line integrals of 3D noise along the flow, run in UV space (cv2.remap steps) but seeded from each texel's
3D position, so they line up across UV seams.
"""
import cv2, json, math, os, sys, time
import numpy as np

T0 = time.time()


def log(*a):
    print(f"[tex {time.time() - T0:5.1f}s]", *a, flush=True)


def hash01(ix, iy, iz, seed):
    h = (ix * np.int64(73856093)) ^ (iy * np.int64(19349663)) ^ (iz * np.int64(83492791)) ^ np.int64(seed * 2654435761 % (1 << 31))
    h = (h ^ (h >> np.int64(13))) * np.int64(1274126177)
    h = h ^ (h >> np.int64(16))
    return (h & np.int64(0xFFFFFF)).astype(np.float32) / float(0xFFFFFF)


def vnoise3(P, seed):
    f = np.floor(P)
    i = f.astype(np.int64)
    t = (P - f).astype(np.float32)
    u = t * t * t * (t * (t * 6 - 15) + 10)
    acc = np.zeros(P.shape[:-1], np.float32)
    for dx in (0, 1):
        wx = u[..., 0] if dx else 1 - u[..., 0]
        for dy in (0, 1):
            wy = u[..., 1] if dy else 1 - u[..., 1]
            for dz in (0, 1):
                wz = u[..., 2] if dz else 1 - u[..., 2]
                acc += wx * wy * wz * (hash01(i[..., 0] + dx, i[..., 1] + dy, i[..., 2] + dz, seed) * 2 - 1)
    return acc


def nearest_fill(a, valid):
    """Every texel outside `valid` takes the value of the nearest valid texel."""
    src = (~valid).astype(np.uint8)
    _, lab = cv2.distanceTransformWithLabels(src, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(src == 0)
    idx = np.clip(lab - 1, 0, len(ys) - 1)
    return a[ys[idx], xs[idx]]


def lic(noise, fx, fy, L, step=1.0):
    H, W = noise.shape
    gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    acc = noise.copy()
    wsum = np.ones_like(noise)
    n = max(1, int(L / step))
    for sgn in (1.0, -1.0):
        x, y = gx.copy(), gy.copy()
        px, py = fx * sgn, fy * sgn
        for k in range(1, n + 1):
            ux = cv2.remap(fx, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            uy = cv2.remap(fy, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            s = np.where(ux * px + uy * py < 0, -1.0, 1.0).astype(np.float32)
            ux *= s
            uy *= s
            x += step * ux
            y += step * uy
            px, py = ux, uy
            w = 0.5 + 0.5 * math.cos(math.pi * k / (n + 1))
            acc += w * cv2.remap(noise, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            wsum += w
    return acc / wsum


def norm_in(a, M):
    m, s = float(a[M].mean()), float(a[M].std()) + 1e-9
    return (a - m) / s


def lin_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def srgb_hex(h):
    h = h.lstrip('#')
    c = np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def write(path, img, data=True):
    """img: float [0,1], rows bottom-up (Blender); PNG rows top-down."""
    a = np.flipud(np.clip(img, 0, 1))
    if a.ndim == 3:
        a = a[..., ::-1] if a.shape[2] == 3 else a[..., [2, 1, 0, 3]]
    cv2.imwrite(path, (a * 255 + 0.5).astype(np.uint8))


def main():
    work = sys.argv[1]
    opts = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
    st = json.load(open(os.path.join(work, "style.json")))
    for k, v in opts.items():
        if k in st and isinstance(st[k], (int, float)):
            st[k] = type(st[k])(v)
    nstrength = float(opts.get("nstrength", 0.7))
    mp = np.load(os.path.join(work, "maps.npz"))
    M = mp["coverage"][..., 0] > 0.5
    H, W = M.shape
    pos = np.array(st["pos_lo"]) + mp["pos"][..., :3].astype(np.float64) * st["pos_ext"]
    flow = mp["flow"][..., :3] * 2 - 1
    scal = mp["scal"]
    ao = np.clip(mp["ao"][..., 0], 0, 1)
    col = mp["color"][..., :3]
    # inside the islands only (the bake margin repeats edge texels); then every map is filled outwards from there
    pos = nearest_fill(pos, M)
    flow = nearest_fill(flow, M)
    scal = nearest_fill(scal, M)
    ao = nearest_fill(ao, M)
    col = nearest_fill(col, M)
    # texel size, and the flow in UV pixel space: least squares through dP/dx, dP/dy
    def diff(axis):
        f = np.roll(pos, -1, axis) - pos
        b = pos - np.roll(pos, 1, axis)
        Mf = M & np.roll(M, -1, axis)
        Mb = M & np.roll(M, 1, axis)
        return np.where(Mf[..., None], f, np.where(Mb[..., None], b, 0.0))
    dx, dy = diff(1), diff(0)
    tsz = float(np.median(np.linalg.norm(dx[M], axis=1)))
    a = (dx * dx).sum(-1)
    b = (dx * dy).sum(-1)
    c = (dy * dy).sum(-1)
    r1 = (dx * flow).sum(-1)
    r2 = (dy * flow).sum(-1)
    det = a * c - b * b
    ok = M & (det > 1e-20)
    fx = np.where(ok, (c * r1 - b * r2) / np.where(ok, det, 1), 0)
    fy = np.where(ok, (a * r2 - b * r1) / np.where(ok, det, 1), 0)
    nf = np.sqrt(fx * fx + fy * fy)
    ok &= nf > 1e-6
    fx = nearest_fill(np.where(ok, fx / np.maximum(nf, 1e-9), 0), ok).astype(np.float32)
    fy = nearest_fill(np.where(ok, fy / np.maximum(nf, 1e-9), 0), ok).astype(np.float32)
    log(f"{W}x{H}, {M.mean() * 100:.0f}% covered, texel {tsz * 1000:.3f} mm")
    # for Godot's ANISOTROPY_FLOW: the direction ACROSS the strands in tangent space (x = +u, y = +v as Blender
    # lays out UVs, i.e. up in the image), so the anisotropic GGX lobe stretches across them like a fibre's
    # highlight. The sign does not matter (the lobe is symmetric), so the flow's sign flips leave no seams.
    write(os.path.join(work, "flow.png"), np.dstack([0.5 - 0.5 * fy, 0.5 + 0.5 * fx, np.full_like(fx, 0.5)]))

    def strands(cell, L, seed):
        n = vnoise3(pos / cell, seed).astype(np.float32)
        return norm_in(lic(n, fx, fy, L / tsz, step=max(1.0, 0.35 * cell / tsz)), M)

    fine_cell = max(1.5 * tsz, 0.0003)
    fine = strands(fine_cell, st["fine_len"], 1)
    mid = strands(0.0011, st["mid_len"], 2)
    coarse = strands(0.003, st["coarse_len"], 3)
    log("strands: fine cell", round(fine_cell * 1000, 2), "mm")
    # relief: mostly fine strand grooves (they break every highlight into streaks, like the anisotropic lobe of
    # real hair), some strand groups; broad locks only a little (broad grooves read as brush strokes / wet hair)
    wf, wm, wc = (float(opts.get(k, d)) for k, d in (("wfine", 0.6), ("wmid", 0.4), ("wcoarse", 0.22)))
    Hh = np.tanh(1.1 * norm_in(wf * fine + wm * mid + wc * coarse, M)).astype(np.float32)

    # tangent-space normal from the strand height (central differences in texels)
    gx = (np.roll(Hh, -1, 1) - np.roll(Hh, 1, 1)) * 0.5
    gy = (np.roll(Hh, -1, 0) - np.roll(Hh, 1, 0)) * 0.5
    n = np.dstack([-nstrength * gx, -nstrength * gy, np.ones_like(gx)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    write(os.path.join(work, "normal.png"), n * 0.5 + 0.5)

    # albedo: the person's colour, roots (deep, near the scalp) darker, tips lighter; the scan's own variation
    # (compressed), per-strand brightness, darker grooves, cavity AO
    d_free = scal[..., 0] * 0.05
    d_hl = scal[..., 1] * 0.03
    depth = scal[..., 2]
    relief = scal[..., 3]
    tipness = np.clip(0.75 * smoothstep(0.0, 0.7, depth) + 0.35 * (1 - smoothstep(0.0, 0.04, d_free)), 0, 1)
    root, tip = srgb_hex(st["root"]), srgb_hex(st["tip"])
    base = root[None, None] * (1 - tipness[..., None]) + tip[None, None] * tipness[..., None]
    # the scan's own brightness is NOT used: its texture has the generator's lighting painted in (white streaks,
    # dark pits), which turned into white daubs under real light. Only a very soft, compressed trace of it.
    lum = col @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    lum = cv2.GaussianBlur(lum.astype(np.float32), (0, 0), 24.0)
    scanvar = float(opts.get("scanvar", 0.12))
    vs = np.clip((lum / max(float(np.median(lum[M])), 1e-4)) ** scanvar, 0.9, 1.1)
    s1 = strands(fine_cell * 1.3, st["fine_len"], 5)
    strand_v = np.clip(1 + 0.16 * s1 + 0.1 * np.maximum(s1 - 1.5, 0), 0.72, 1.4)
    groove = 0.8 + 0.2 * (Hh * 0.5 + 0.5)
    ao_c = cv2.medianBlur(np.clip(ao, 0, 1).astype(np.float32), 5)
    occ = np.power(np.clip(ao_c, 0.25, 1), 0.75) * (0.86 + 0.14 * relief)
    alb = base * (vs * strand_v * groove * occ)[..., None]
    write(os.path.join(work, "albedo.png"), lin_to_srgb(alb))
    rough = np.clip(float(opts.get("rough", 0.36)) + 0.12 * (1 - (Hh * 0.5 + 0.5)) + 0.16 * (1 - ao_c), 0.3, 0.7)
    write(os.path.join(work, "rough.png"), np.dstack([rough] * 3))
    ao = ao_c

    # alpha: strands end at varying lengths at free edges, a ragged hairline, sparse loose strands on two fuzz layers
    def unif(x):   # standard normal -> uniform (normal CDF, tanh approximation)
        return 0.5 * (1 + np.tanh(0.7978845608 * (x + 0.044715 * x ** 3)))
    u = unif(strands(fine_cell, st["fine_len"], 7))
    # a strand starts where the hairline's density ramp passes its own threshold (staggered roots, scalp shows)
    u_hl = unif(strands(fine_cell, st["fine_len"], 8))
    core = smoothstep(-0.6 * tsz, 0.6 * tsz, d_free - st["tip_len"] * u ** 1.6) * \
        smoothstep(-0.012, 0.012, smoothstep(0.0, float(opts.get("hl_ramp", 0.006)), d_hl) - u_hl)
    fz1 = smoothstep(0.52, 0.6, unif(strands(fine_cell, st["fine_len"] * 1.2, 9))) * smoothstep(0.006, 0.014, d_hl) * \
        smoothstep(0.3 * st["tip_len"], st["tip_len"], d_free)
    fz2 = smoothstep(0.74, 0.8, unif(strands(fine_cell, st["fine_len"] * 1.5, 10))) * smoothstep(0.01, 0.02, d_hl) * \
        smoothstep(0.5 * st["tip_len"], 1.2 * st["tip_len"], d_free)
    write(os.path.join(work, "mask.png"), np.dstack([fz1, fz2, core, ao]))
    # preview strip for review
    view = np.hstack([lin_to_srgb(alb * 6), n * 0.5 + 0.5, np.dstack([fz1, fz2, core])])
    write(os.path.join(work, "preview.png"), cv2.resize(view, (3 * 1024, 1024), interpolation=cv2.INTER_AREA))
    log("done; core alpha < 0.5 on", f"{(core[M] < 0.5).mean() * 100:.1f}% of texels")


main()
