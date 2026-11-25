"""Prototype A: strand atlases for scan-shaped hair cards (plain python3.11: numpy + cv2, no Blender needed).

usage: python3.11 tools/blender/proto_hair_A_tex.py [straight|curly|all]
-> tools/out/proto_A/strands_<kind>.png  (RGBA; 8 vertical strips, root at the top, tip at the bottom)

RGB is a neutral brightness map (the hair colour comes from the card's vertex colour, sampled from the scan),
alpha is strand coverage. Each strip is one lock: a dense core of overlapping strands that thins out into wisps
at the edges and the tip. The curly atlas draws each lock as a helix seen from the side: strands follow a shared
sine path (same phase within a lock, so it reads as one ringlet), are brighter where the helix turns towards the
viewer and slightly see-through where it turns away; the geometry then only has to bend the card gently.
"""
import os, sys, math
import numpy as np
import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "tools", "out", "proto_A")


def _splat(rgb, alpha, xs, ys, wpx, a_row, bright, x_lo, x_hi, nrm=None, tilt=None):
    """Composite one strand (x per row) with a Gaussian cross-section, front-to-back 'over' (back strands first)."""
    r = int(math.ceil(wpx * 2.4))
    xi = np.floor(xs).astype(int)
    for dx in range(-r, r + 1):
        x = xi + dx
        ok = (x >= x_lo) & (x < x_hi) & (a_row > 0)
        if not ok.any():
            continue
        d = np.abs(x + 0.5 - xs)
        a = np.exp(-(d / (wpx * 0.6)) ** 2) * a_row
        a, yi, xo, b = a[ok], ys[ok], x[ok], bright[ok]
        # fade strands out near the strip's sides: a lock never shows the card's straight cut edge
        e = np.minimum(xo - x_lo, x_hi - 1 - xo) / (0.1 * (x_hi - x_lo))
        a = a * np.clip(e, 0, 1) ** 1.5
        prev = alpha[yi, xo]
        rgb[yi, xo] = rgb[yi, xo] * (1 - a) + b * a          # newer strands lie on top
        if nrm is not None:
            nrm[yi, xo] = nrm[yi, xo] * (1 - a[:, None]) + tilt[ok] * a[:, None]
        alpha[yi, xo] = prev + a * (1 - prev)


def atlas(kind, size=(2048, 2048), strips=8, seed=3):
    rng = np.random.default_rng(seed)
    W, H = size
    sw = W // strips
    rgb = np.zeros((H, W), np.float32)
    alpha = np.zeros((H, W), np.float32)
    nrm = np.zeros((H, W, 2), np.float32)        # per-strand normal tilt (across, along): breaks highlights into strands
    ys_all = np.arange(H)
    # per strip: (strand count, clump spread as a fraction of the strip, curl amplitude px, wavelength px)
    if kind == "curly":
        kinds = [(440, 0.15, 0.17, 0.33), (400, 0.16, 0.19, 0.28), (340, 0.14, 0.15, 0.38), (190, 0.17, 0.17, 0.3)]
    else:
        kinds = [(520, 0.16, 0, 0), (440, 0.19, 0, 0), (360, 0.22, 0, 0), (160, 0.26, 0, 0)]
    for s in range(strips):
        n, spread, camp, cwl = kinds[s % len(kinds)]
        n = int(n * rng.uniform(0.9, 1.1))
        x_lo, x_hi = s * sw, (s + 1) * sw
        centre = x_lo + sw * rng.uniform(0.47, 0.53)
        amp = camp * sw * rng.uniform(0.85, 1.15)
        wl = cwl * H * rng.uniform(0.85, 1.15)
        ph_lock = rng.uniform(0, 6.283)
        lock_len = H * rng.uniform(0.9, 0.98)
        # back strands first (darker, a little deeper in the lock), then the front ones over them
        order = np.sort(rng.random(n))
        for depth in order:
            off = rng.normal(0, spread * sw) * (1.7 if rng.random() < 0.07 else 1.0)
            length = lock_len * (1.0 - rng.beta(1.3, 3.5) * 0.7)
            ys = ys_all[ys_all < length]
            if len(ys) < 8:
                continue
            t = ys / H
            wpx = rng.uniform(0.75, 1.5)
            fade = np.clip((length - ys) / (0.2 * length), 0, 1) * np.clip(ys / 10.0, 0, 1)
            tone = rng.uniform(0.72, 1.0) * (0.78 + 0.22 * depth)
            grad = 0.72 + 0.28 * np.clip(t / 0.35, 0, 1)          # roots a little darker
            if kind == "curly":
                # the lock's helix: shared phase, each strand a little off it; the curl opens up towards the tip
                frizz = rng.random() < 0.12
                ph = ph_lock + rng.normal(0, 1.4 if frizz else 0.35) + 6.283 * ys / wl * (1 + rng.normal(0, 0.12 if frizz else 0.03))
                ramp = np.clip(ys / (0.12 * H), 0, 1)
                a_t = amp * ramp * (0.8 + 0.4 * t) * rng.uniform(0.85, 1.15)
                tight = off * (1.0 - 0.45 * ramp)                  # strands gather into the ringlet
                xs = centre + tight + a_t * np.sin(ph)
                facing = np.cos(ph)                                # +1: this turn of the helix faces us
                bright = tone * grad * (0.74 + 0.26 * facing)
                a_row = fade * (0.86 + 0.14 * facing) * 0.95
            else:
                wav = rng.uniform(0.3, 2.2) * np.sin(ys * rng.uniform(0.002, 0.007) + rng.uniform(0, 6.28))
                towards = -off * 0.4 * (ys / max(length, 1)) ** 1.5   # tips pull into the clump
                xs = centre + off + wav + towards
                bright = tone * grad
                a_row = fade * 0.93
            ta = rng.normal(0, 0.42)
            tb = 0.12 * np.sin(ys * rng.uniform(0.004, 0.012) + rng.uniform(0, 6.28))
            if kind == "curly":
                ta = ta + 0.5 * np.sin(ph)          # the helix turns the strand's normal round with it
            tilt = np.stack([np.broadcast_to(ta, ys.shape), np.broadcast_to(tb, ys.shape)], 1).astype(np.float32)
            _splat(rgb, alpha, xs.astype(np.float32), ys, wpx, a_row.astype(np.float32),
                   np.broadcast_to(bright, ys.shape).astype(np.float32), x_lo, x_hi, nrm, tilt)
    col = rgb / np.maximum(alpha, 1e-4)
    # colour under transparent texels: the column's mean, so mip-maps don't bleed a dark halo
    k = alpha > 0.05
    mean = np.where(k, col, 0).sum(0) / np.maximum(k.sum(0), 1)
    col = np.where(k, col, mean[None, :])
    img = np.dstack([col, col * 0.985, col * 0.97, alpha])
    img8 = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"strands_{kind}.png")
    cv2.imwrite(path, cv2.cvtColor(img8, cv2.COLOR_RGBA2BGRA))
    # tangent-space normal map (x across the card = UV u, y along it), flat under transparent texels
    t = nrm / np.maximum(alpha, 1e-4)[..., None]
    t = np.where(k[..., None], t, 0.0)
    nx, ny = np.sin(np.clip(t[..., 0], -1.2, 1.2)), np.sin(np.clip(t[..., 1], -0.6, 0.6))
    nz = np.sqrt(np.clip(1 - nx ** 2 - ny ** 2, 0, 1))
    nm = (np.dstack([nx, -ny, nz]) * 0.5 + 0.5)
    cv2.imwrite(path.replace(".png", "_n.png"), cv2.cvtColor((nm * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR))
    print("atlas", path, "coverage", round(float(alpha.mean()), 3))
    return path


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for k in (("straight", "curly") if which == "all" else (which,)):
        atlas(k)
