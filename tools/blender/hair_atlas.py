"""Strand atlases for the scanned characters' hair cards (tools/blender/hair_scan_cards.py).

Plain numpy (cv2 only speeds up the blur): runs in python3.11 or inside Blender.
  python3.11 tools/blender/hair_atlas.py neutral <kind> <out.png> [seed]
  python3.11 tools/blender/hair_atlas.py tint <kind> <root #rrggbb> <tip #rrggbb> <out.png>

Layout as hair_gen.strand_texture: 8 vertical strips, root at the top of the image (v = 0 in glTF, so UV.y runs
root -> tip on every card in Godot). Strip contents for every kind: 0-1 dense clumps, 2-3 medium, 4-5 loose,
6 wispy, 7 a few flyaway strands. The cards pick a strip by layer: inner layers the dense ones, outer layers and
silhouette cards the wispy ones.
kinds: "curly" (loose curls, each strip one curl clump seen side-on, 2048 x 1024) "straight" (long straight clumps
       with a slight wave, 2048 x 2048) "short" (short straight-to-wavy clumps, 2048 x 1024)
The neutral atlas keeps two things apart: alpha (coverage) and shade (each strand's own brightness, mean ~1).
tinted() turns it into one person's atlas: colour = lerp(root, tip, g(v)) x shade, written as 8-bit sRGB (dark
hair keeps its precision there; vertex colours, 8-bit linear in Godot, would band). The colour under the
transparent texels is bled from the strands so mip-maps keep no dark or light halo.
"""
import math, os, sys
import numpy as np

KINDS = {
    # per strip: strands, spread (fraction of the strip width, clump core), curl amplitude (fraction of the strip
    # width), curl periods down the strip, alpha gain
    "curly": dict(size=(2048, 1024), curly=True, strips=[
        (300, 0.13, 0.20, 2.0, 1.0), (280, 0.14, 0.24, 2.0, 1.0),
        (220, 0.15, 0.18, 2.5, 0.95), (200, 0.17, 0.26, 1.6, 0.95),
        (160, 0.17, 0.22, 2.2, 0.9), (140, 0.19, 0.18, 2.8, 0.9),
        (80, 0.2, 0.22, 2.0, 0.85), (14, 0.25, 0.26, 2.2, 0.9)]),
    # (hair_cards "atlas": "wavy"; no preset uses it) loose waves, not curls: each strip one chunky lock whose strands
    # wave together (the curly path: a shared phase, the wave's crest lit) about one period down the strip (1.4-1.8,
    # the curly 1.6-2.8), most of the curly amplitude, more strands to a denser core. With "curly" every card shows
    # two or three small curls and the hair reads as an even frizz; with about one period per strip it reads as sleek
    # and brushed
    "wavy": dict(size=(2048, 1024), curly=True, strips=[
        (420, 0.15, 0.17, 1.5, 1.0), (400, 0.16, 0.19, 1.6, 1.0),
        (340, 0.17, 0.18, 1.45, 0.95), (320, 0.18, 0.2, 1.7, 0.95),
        (260, 0.19, 0.19, 1.55, 0.9), (220, 0.2, 0.17, 1.8, 0.9),
        (120, 0.22, 0.19, 1.6, 0.85), (16, 0.25, 0.22, 1.7, 0.9)]),
    # (hair_cards "atlas": "wavy2"; no preset uses it) "wavy" with the lock split, because the unsplit waves read as
    # smeared brush strokes up close, with no strands or curl tips. `sub` sub-locks per strip, each its own centre
    # (`sub_sep` of the strip apart, `sub_spread` x the clump's spread: two narrow locks twisting round each other
    # with a gap between), phase, wave and brightness; `lo` the helix shade at the wave's trough (0.62 for the
    # others); `light` each strand's brightness range (0.8-1.2; here brighter, so the strip's mean stays near wavy's);
    # `tipcurl` (frac, periods, amp): over the last frac of a strand the curl turns `periods` more and opens to 1 +
    # amp of its amplitude (a curled end). Options absent: the draws and the result as before.
    "wavy2": dict(size=(2048, 1024), curly=True, sub=2, sub_sep=0.28, sub_spread=0.5, lo=0.5, light=(0.8, 1.45),
                  tipcurl=(0.3, 0.6, 0.6), strips=[
        (420, 0.15, 0.17, 1.5, 1.0), (400, 0.16, 0.19, 1.6, 1.0),
        (340, 0.17, 0.18, 1.45, 0.95), (320, 0.18, 0.2, 1.7, 0.95),
        (260, 0.19, 0.19, 1.55, 0.9), (220, 0.2, 0.17, 1.8, 0.9),
        (120, 0.22, 0.19, 1.6, 0.85), (16, 0.25, 0.22, 1.7, 0.9)]),
    # (tips: how the strands of a clump end. gather: how far they pull together at the tip; spread and shape: how
    # long the shortest are and how many stop early. Straight long hair ends feathered: gathered tips of equal
    # length made every card end in a rounded opaque drip, a row of icicles along the hair's lower edge)
    # (Anisha: gathered tips, even loosely, still closed each card's end into a rounded lobe in a coarse mip, a dense
    # clump core narrowing to a point; negative: the strands fan out toward their tips, so the end of a card thins
    # out across its whole width and its alpha-tested core ends in a ragged line instead of an icicle)
    "straight": dict(size=(2048, 2048), curly=False, tips=dict(gather=-2.5, spread=0.95, shape=0.7), strips=[
        (380, 0.17, 0.006, 1.3, 1.0), (360, 0.19, 0.008, 1.0, 1.0),
        (280, 0.2, 0.01, 1.5, 0.95), (260, 0.22, 0.012, 1.2, 0.95),
        (200, 0.22, 0.015, 1.8, 0.9), (170, 0.25, 0.012, 1.4, 0.9),
        (100, 0.26, 0.02, 1.6, 0.85), (16, 0.3, 0.03, 1.2, 0.9)]),
    # short cut hair: denser clumps (a short card must read as a lock, not as a few strands), a soft wave
    "short": dict(size=(2048, 1024), curly=False, tips=dict(gather=0.5, spread=0.8, shape=0.8), strips=[
        (360, 0.16, 0.012, 1.1, 1.0), (340, 0.18, 0.016, 0.9, 1.0),
        (280, 0.19, 0.02, 1.3, 0.95), (250, 0.21, 0.024, 1.0, 0.95),
        (200, 0.22, 0.028, 1.4, 0.9), (170, 0.24, 0.02, 1.2, 0.9),
        (100, 0.26, 0.03, 1.5, 0.85), (16, 0.3, 0.04, 1.2, 0.9)]),
}

# where the root -> tip colour ramp ends (fraction of the strip's height): hair is darker near the scalp
RAMP = 0.5


def ramp(H):
    return np.clip((np.arange(H, dtype=np.float32) / H) / RAMP, 0.0, 1.0)


def blur(img, sigma):
    try:
        import cv2
        return cv2.GaussianBlur(img, (0, 0), sigma)
    except ImportError:
        r = int(math.ceil(3 * sigma))
        k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
        k /= k.sum()
        out = img.astype(np.float32)
        for axis in (0, 1):
            p = np.pad(out, [(r, r) if a == axis else (0, 0) for a in range(out.ndim)], mode='edge')
            acc = np.zeros_like(out)
            for i, w in enumerate(k):
                sl = [slice(None)] * out.ndim
                sl[axis] = slice(i, i + out.shape[axis])
                acc += w * p[tuple(sl)]
            out = acc
        return out


def make(kind, seed=3):
    """Neutral atlas: (shade RGB (H, W, 3) around 1, warm/cool per strand; alpha (H, W))."""
    spec = KINDS[kind]
    W, H = spec["size"]
    strips = spec["strips"]
    ns = len(strips)
    sw = W // ns
    rng = np.random.default_rng(seed)
    rgb = np.zeros((H, W, 3), np.float32)
    alpha = np.zeros((H, W), np.float32)
    ys = np.arange(H, dtype=np.float32)
    curly = spec["curly"]
    for s, (n, spread, camp, periods, gain) in enumerate(strips):
        x_lo = s * sw
        centre = x_lo + sw * 0.5
        ph0 = rng.uniform(0, 2 * math.pi)
        # the clump's own slow sway (a whole lock bends a little)
        sway_a = rng.uniform(0.02, 0.06) * sw
        sway_f = rng.uniform(0.6, 1.4) * 2 * math.pi / H
        sway_p = rng.uniform(0, 6.28)
        flyaway = s == ns - 1
        sub = spec.get("sub")
        if sub:
            # (wavy2) the strip's sub-locks: centres, phases, waves, brightness and shares of the strands
            k_sub = 1 if flyaway else int(sub)
            offs = ((np.arange(k_sub) - (k_sub - 1) / 2.0) * float(spec.get("sub_sep", 0.2)) +
                    rng.normal(0, 0.02, k_sub)) * sw
            phs = rng.uniform(0, 2 * math.pi, k_sub)
            pers = rng.uniform(0.9, 1.1, k_sub)
            lights = rng.uniform(0.8, 1.2, k_sub)
            shares = rng.dirichlet(np.ones(k_sub) * 4.0) if k_sub > 1 else np.ones(1)
            spread_s = spread * float(spec.get("sub_spread", 1.0 / math.sqrt(k_sub)))
        lo_ = float(spec.get("lo", 0.62))
        light_r = spec.get("light", (0.8, 1.2))
        tc_ = spec.get("tipcurl")
        for _ in range(int(n * rng.uniform(0.92, 1.08))):
            j_ = int(rng.choice(k_sub, p=shares)) if sub else 0
            c_ = centre + offs[j_] if sub else centre
            stray = rng.random() < (0.5 if flyaway else 0.07)
            x0 = c_ + rng.normal(0, (spread_s if sub else spread) * sw) * (1.8 if stray else 1.0)
            # most strands run (almost) the full length; some stop early so the tip thins out
            tips = spec.get("tips") or {}
            length = H * (1.0 - rng.beta(1.3, 5.0) ** tips.get("shape", 1.0) *
                          tips.get("spread", 0.85 if curly else 0.7))
            if flyaway:
                length = H * rng.uniform(0.5, 1.0)
            amp = camp * sw * rng.uniform(0.75, 1.2) * (1.4 if stray else 1.0)
            ph = (phs[j_] if sub else ph0) + rng.normal(0, 0.35 if curly else 1.5)
            per = periods * rng.uniform(0.92, 1.08) * (pers[j_] if sub else 1.0)
            wpx = rng.uniform(0.75, 1.35)
            light = rng.uniform(*light_r) * (lights[j_] if sub else 1.0)
            warm = rng.uniform(-0.05, 0.05)
            yy = ys[ys < length]
            t = yy / H
            theta = 2 * math.pi * per * t + ph
            # curls: the projected helix x = A sin(theta); the strand is in front where cos(theta) > 0, and the
            # curl opens up towards the tip (loose ends)
            a_t = amp * (0.75 + 0.5 * t) if curly else amp
            if tc_:
                # (wavy2) a curled end: the last tipcurl[0] of the strand turns tipcurl[1] more and opens up
                u_ = np.clip((t - (1.0 - float(tc_[0])) * length / H) / max(float(tc_[0]) * length / H, 1e-3), 0, 1)
                theta = theta + 2 * math.pi * float(tc_[1]) * u_ * u_
                a_t = a_t * (1.0 + float(tc_[2]) * u_)
            xc = x0 + a_t * np.sin(theta) + sway_a * np.sin(yy * sway_f + sway_p)
            # tips gather into the clump (straight; fan out with a negative gather) or spring apart a little (curly)
            pull = (c_ - x0) * rng.uniform(0.1, 0.45) * tips.get("gather", 1.0) * \
                (t / max(length / H, 1e-3)) ** 1.6
            xc = xc + (pull if not curly else -0.3 * pull)
            if flyaway:
                xc = xc + rng.uniform(-0.25, 0.25) * sw * (t ** 1.5)
            # fine kinks: real strands are never perfectly smooth
            xc = xc + rng.uniform(0.2, 0.9) * np.sin(yy * rng.uniform(0.02, 0.06) + rng.uniform(0, 6.28))
            depth = np.cos(theta) if curly else np.zeros_like(theta)
            shade = light * ((lo_ + (1.0 - lo_) * (depth * 0.5 + 0.5)) if curly else np.ones_like(theta))
            a_mul = gain * ((0.7 + 0.3 * (depth * 0.5 + 0.5)) if curly else 1.0)
            fade = np.clip((length - yy) / (0.16 * length), 0, 1) * np.clip(yy / 3.0, 0, 1)
            col = shade[:, None] * np.array([1 + warm, 1.0, 1 - warm], np.float32)[None]
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
    rgb = rgb / np.maximum(alpha, 1e-4)[..., None]
    # strays cut by a strip's border would show as a hard vertical line along the card's edge: fade them out
    xs = (np.arange(W) % sw) / sw
    alpha *= np.clip(np.minimum(xs, 1 - xs) / 0.07, 0, 1)[None, :]
    return rgb, np.clip(alpha, 0, 1)


def bleed(rgb, alpha):
    """Colour under the transparent texels: each strip column's mean, then blurred into the gaps."""
    k = alpha > 0.04
    fill = np.where(k[..., None], rgb, 0).sum(0) / np.maximum(k.sum(0)[:, None], 1)
    filled = np.where(k[..., None], rgb, fill[None])
    return np.where(k[..., None], rgb, blur(filled, 3))


def lin_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def srgb_to_lin(c):
    c = np.clip(np.asarray(c, np.float32), 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def hex_lin(h):
    h = h.lstrip('#')
    return srgb_to_lin(np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32))


def tinted(kind, root_lin, tip_lin, seed=3):
    """One person's atlas (H, W, 4), sRGB-encoded floats: the root -> tip colour (linear RGB) along each strand,
    times each strand's own shade; alpha as the neutral atlas."""
    shade, alpha = make(kind, seed)
    H = shade.shape[0]
    g = ramp(H)[:, None, None]
    col = (np.asarray(root_lin, np.float32)[None, None] * (1 - g) + np.asarray(tip_lin, np.float32)[None, None] * g)
    lin = col * shade
    rgb = bleed(lin_to_srgb(lin).astype(np.float32), alpha)
    return np.concatenate([np.clip(rgb, 0, 1), alpha[..., None]], -1)


def save_png(img, path):
    """(H, W, 4) floats 0-1, row 0 = top of the image."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    try:
        import cv2
        bgra = (img[..., [2, 1, 0, 3]] * 255 + 0.5).astype(np.uint8)
        cv2.imwrite(path, bgra)
    except ImportError:
        import bpy
        h, w = img.shape[:2]
        im = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
        im.pixels.foreach_set(np.flipud(img).astype(np.float32).ravel())
        im.filepath_raw = path
        im.file_format = 'PNG'
        im.save()
        bpy.data.images.remove(im)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "neutral":
        kind, out = sys.argv[2], sys.argv[3]
        shade, alpha = make(kind, int(sys.argv[4]) if len(sys.argv) > 4 else 3)
        rgb = bleed(np.clip(shade * 0.7, 0, 1), alpha)
        save_png(np.concatenate([rgb, alpha[..., None]], -1), out)
        print("atlas", kind, alpha.shape, "coverage", round(float(alpha.mean()), 3), "->", out)
    elif mode == "tint":
        kind, root, tip, out = sys.argv[2:6]
        img = tinted(kind, hex_lin(root), hex_lin(tip))
        save_png(img, out)
        print("atlas", kind, root, "->", tip, img.shape, "coverage", round(float(img[..., 3].mean()), 3), "->", out)
    else:
        raise SystemExit(__doc__)
