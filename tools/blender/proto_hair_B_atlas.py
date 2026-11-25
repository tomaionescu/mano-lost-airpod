"""Prototype B (hair cards laid over the scan's hair shell): the strand atlas.

Plain numpy + OpenCV (no Blender): python3.11 tools/blender/proto_hair_B_atlas.py <kind> <out.png> [seed]
kind: "curly" (loose curls, each strip one curl clump seen side-on) or "straight" (long straight clumps with a slight
wave). Layout like hair_gen.strand_texture: 8 vertical strips, root at the top (v = 0), RGBA, colour premultiplied out
and bled under the transparent texels so mip-maps keep no dark halo.

Strip contents (both kinds): 0-1 dense clumps, 2-3 medium, 4-5 loose, 6 wispy, 7 a few flyaway strands. The
cards pick a strip by layer: inner layers the dense ones, outer layers and silhouette cards the wispy ones.
Colour is neutral grey-brown x a root->tip ramp; the per-character tint comes from the material.
"""
import sys, math
import numpy as np
import cv2

KINDS = {
    # per strip: strands, spread (fraction of the strip width, clump core), curl amplitude (fraction of the strip
    # width), curl periods down the strip, alpha gain
    "curly": dict(size=(2048, 1024), strips=[
        (300, 0.13, 0.20, 2.0, 1.0), (280, 0.14, 0.24, 2.0, 1.0),
        (220, 0.15, 0.18, 2.5, 0.95), (200, 0.17, 0.26, 1.6, 0.95),
        (160, 0.17, 0.22, 2.2, 0.9), (140, 0.19, 0.18, 2.8, 0.9),
        (80, 0.2, 0.22, 2.0, 0.85), (14, 0.25, 0.26, 2.2, 0.9)]),
    "straight": dict(size=(2048, 2048), strips=[
        (380, 0.17, 0.006, 1.3, 1.0), (360, 0.19, 0.008, 1.0, 1.0),
        (280, 0.2, 0.01, 1.5, 0.95), (260, 0.22, 0.012, 1.2, 0.95),
        (200, 0.22, 0.015, 1.8, 0.9), (170, 0.25, 0.012, 1.4, 0.9),
        (100, 0.26, 0.02, 1.6, 0.85), (16, 0.3, 0.03, 1.2, 0.9)]),
}


def make(kind, seed=3):
    spec = KINDS[kind]
    W, H = spec["size"]
    strips = spec["strips"]
    ns = len(strips)
    sw = W // ns
    rng = np.random.default_rng(seed)
    rgb = np.zeros((H, W, 3), np.float32)
    alpha = np.zeros((H, W), np.float32)
    ys = np.arange(H, dtype=np.float32)
    curly = kind == "curly"
    for s, (n, spread, camp, periods, gain) in enumerate(strips):
        x_lo = s * sw
        centre = x_lo + sw * 0.5
        ph0 = rng.uniform(0, 2 * math.pi)
        # the clump's own slow sway (a whole lock bends a little)
        sway_a = rng.uniform(0.02, 0.06) * sw
        sway_f = rng.uniform(0.6, 1.4) * 2 * math.pi / H
        sway_p = rng.uniform(0, 6.28)
        flyaway = s == ns - 1
        for _ in range(int(n * rng.uniform(0.92, 1.08))):
            stray = rng.random() < (0.5 if flyaway else 0.07)
            x0 = centre + rng.normal(0, spread * sw) * (1.8 if stray else 1.0)
            # most strands run (almost) the full length; some stop early so the tip thins out
            length = H * (1.0 - rng.beta(1.3, 5.0) * (0.85 if curly else 0.7))
            if flyaway:
                length = H * rng.uniform(0.5, 1.0)
            amp = camp * sw * rng.uniform(0.75, 1.2) * (1.4 if stray else 1.0)
            ph = ph0 + rng.normal(0, 0.35 if curly else 1.5)
            per = periods * rng.uniform(0.92, 1.08)
            wpx = rng.uniform(0.75, 1.35)
            light = rng.uniform(0.78, 1.22)
            warm = rng.uniform(-0.05, 0.05)
            yy = ys[ys < length]
            t = yy / H
            theta = 2 * math.pi * per * t + ph
            # curls: the projected helix x = A sin(theta); the strand is in front where cos(theta) > 0
            # the curl opens up towards the tip (loose ends)
            a_t = amp * (0.75 + 0.5 * t) if curly else amp
            xc = x0 + a_t * np.sin(theta) + sway_a * np.sin(yy * sway_f + sway_p)
            # tips gather into the clump (straight) or spring apart a little (curly)
            pull = (centre - x0) * rng.uniform(0.1, 0.45) * (t / max(length / H, 1e-3)) ** 1.6
            xc = xc + (pull if not curly else -0.3 * pull)
            if flyaway:
                xc = xc + rng.uniform(-0.25, 0.25) * sw * (t ** 1.5)
            # fine kinks: real strands are never perfectly smooth
            xc = xc + rng.uniform(0.2, 0.9) * np.sin(yy * rng.uniform(0.02, 0.06) + rng.uniform(0, 6.28))
            depth = np.cos(theta) if curly else np.zeros_like(theta)
            shade = light * ((0.62 + 0.38 * (depth * 0.5 + 0.5)) if curly else 1.0)
            a_mul = gain * ((0.7 + 0.3 * (depth * 0.5 + 0.5)) if curly else 1.0)
            fade = np.clip((length - yy) / (0.16 * length), 0, 1) * np.clip(yy / 6.0, 0, 1)
            g = np.clip(t / 0.5, 0, 1)
            # neutral strand colour: root darker, tip lighter (multiplied by the character tint later)
            base = (0.42 + 0.58 * g)[:, None] * np.array([1 + warm, 1.0, 1 - warm], np.float32)[None]
            col = base * shade[:, None] if curly else base * shade
            xi = np.floor(xc).astype(int)
            r = int(math.ceil(wpx * 2.0))
            for dx in range(-r, r + 1):
                x = xi + dx
                ok = (x >= x_lo + 2) & (x < x_lo + sw - 2)
                d = np.abs(x + 0.5 - xc)
                a = np.exp(-(d / (wpx * 0.6)) ** 2) * fade * 0.9 * a_mul
                a = a[ok]
                yi = yy[ok].astype(int)
                xo = x[ok]
                prev = alpha[yi, xo]
                rgb[yi, xo] += col[ok] * (a * (1 - prev))[:, None]
                alpha[yi, xo] = prev + a * (1 - prev)
    # strays cut by a strip's border would show as a hard vertical line along the card's edge: fade them out
    rgb = rgb / np.maximum(alpha, 1e-4)[..., None]
    xs = (np.arange(W) % sw) / sw
    alpha *= np.clip(np.minimum(xs, 1 - xs) / 0.07, 0, 1)[None, :]
    # bleed the strand colour under transparent texels (per strip column mean, then a blur)
    k = alpha > 0.04
    fill = np.where(k[..., None], rgb, 0).sum(0) / np.maximum(k.sum(0)[:, None], 1)
    filled = np.where(k[..., None], rgb, fill[None])
    blur = cv2.GaussianBlur(filled, (0, 0), 3)
    filled = np.where(k[..., None], rgb, blur)
    return np.concatenate([np.clip(filled, 0, 1), np.clip(alpha, 0, 1)[..., None]], -1)


def save(img, path):
    bgra = (img[..., [2, 1, 0, 3]] * 255 + 0.5).astype(np.uint8)
    cv2.imwrite(path, bgra)


if __name__ == "__main__":
    kind, out = sys.argv[1], sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    img = make(kind, seed)
    save(img, out)
    print("atlas", kind, img.shape, "coverage", round(float(img[..., 3].mean()), 3), "->", out)
