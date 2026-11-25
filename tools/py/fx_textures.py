"""Build the lens and particle textures of the lens pass (docs/DESIGN.md §4.6, §4.8) -> assets/textures/fx/.

python3.11 -I tools/py/fx_textures.py
- lens_dirt.png   1280x720 RGB, mostly black: greasy finger smears, out-of-focus dust discs and a few fibres.
                  WorldEnv sets it as Environment.glow_map, so the bloom shows the dirt where it is bright.
                  A stand-in until a photographed smudged phone lens replaces it (same size, same name).
- grain.png       256x256 grey, tileable Gaussian film grain (about 1.4 px once post.gdshader scales it).
- leaves_fall.png 512x512 RGBA, 2x2 atlas of single October leaves for the falling-leaf particles, cut from the
                  CC0 ambientCG leaf sets the trees already use (LeafSet029 plane, LeafSet024 birch), turned yellow
                  and brown.
Deterministic (fixed seeds), so rerunning it gives the same files.
"""
import os
import sys

sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "assets", "textures", "fx")
TEX = os.path.join(ROOT, "assets", "textures")


def blur_wrap(a, sigma):
    """Gaussian blur that wraps at the borders (tileable)."""
    h, w = a.shape[:2]
    big = np.tile(a, (3, 3) + (1,) * (a.ndim - 2))
    big = cv2.GaussianBlur(big, (0, 0), sigma)
    return big[h:2 * h, w:2 * w]


def grain():
    rng = np.random.default_rng(7)
    n = rng.standard_normal((256, 256)).astype(np.float32)
    n = blur_wrap(n, 0.55)
    n = (n - n.mean()) / n.std()
    img = np.clip(0.5 + n * 0.16, 0.0, 1.0)
    Image.fromarray((img * 255.0 + 0.5).astype(np.uint8), "L").save(os.path.join(OUT, "grain.png"))


def lens_dirt():
    W, H = 1280, 720
    rng = np.random.default_rng(11)
    acc = np.zeros((H, W, 3), np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # a faint greasy film, uneven
    film = rng.standard_normal((H // 40, W // 40)).astype(np.float32)
    film = cv2.resize(film, (W, H), interpolation=cv2.INTER_CUBIC)
    film = cv2.GaussianBlur(film, (0, 0), 30)
    film = np.clip(film * 0.02 + 0.03, 0.0, 0.08)
    acc += film[..., None]
    # finger smears: soft arcs of streaky grease
    streak_src = rng.standard_normal((H, W)).astype(np.float32)
    for k in range(7):
        cx, cy = rng.uniform(0.05, 0.95) * W, rng.uniform(0.08, 0.92) * H
        r = rng.uniform(90, 260)
        a0 = rng.uniform(0, 2 * np.pi)
        span = rng.uniform(0.6, 1.6)
        width = rng.uniform(18, 46)
        d = np.hypot(xx - cx, yy - cy)
        ang = np.arctan2(yy - cy, xx - cx)
        da = np.angle(np.exp(1j * (ang - a0 - span / 2)))
        along = np.clip(1.0 - np.abs(da) / (span / 2), 0.0, 1.0)
        across = np.exp(-((d - r) / width) ** 2)
        m = across * along * along * (3.0 - 2.0 * along)   # smooth ends
        # streaks follow the wipe: blur the noise along the arc direction (approximated by its mean direction)
        dirx, diry = -np.sin(a0 + span / 2), np.cos(a0 + span / 2)
        kl = 41
        kern = np.zeros((kl, kl), np.float32)
        for t in np.linspace(-1, 1, 61):
            kern[int(round(kl // 2 + t * 20 * diry)), int(round(kl // 2 + t * 20 * dirx))] = 1.0
        kern /= kern.sum()
        streaks = cv2.filter2D(streak_src, -1, kern)
        streaks = np.clip(0.6 + streaks * 1.6, 0.0, 1.3)
        acc += (m * streaks * rng.uniform(0.22, 0.42))[..., None] * np.array([1.0, 0.97, 0.92], np.float32)
    # out-of-focus dust: soft discs with a slightly brighter rim and an uneven fill, more toward the edges
    blot = cv2.GaussianBlur(rng.standard_normal((H, W)).astype(np.float32), (0, 0), 3.0)
    blot = np.clip(0.75 + blot * 1.5, 0.35, 1.0)
    for k in range(150):
        while True:
            x, y = rng.uniform(0, W), rng.uniform(0, H)
            edge = max(abs(x / W - 0.5), abs(y / H - 0.5)) * 2.0
            if rng.uniform() < 0.3 + 0.7 * edge:
                break
        r = rng.uniform(1.5, 9.0) if rng.uniform() < 0.8 else rng.uniform(10.0, 26.0)
        v = rng.uniform(0.12, 0.5) * (0.6 if r > 10 else 1.0)
        d = np.hypot(xx - x, yy - y) / r
        sl = np.s_[max(0, int(y - r - 3)):min(H, int(y + r + 4)), max(0, int(x - r - 3)):min(W, int(x + r + 4))]
        dd = d[sl]
        disc = np.clip((1.0 - dd) * r * (0.5 if r > 6 else 0.25), 0.0, 1.0)   # big ones crisp, specks soft
        rim = np.exp(-((dd - 0.85) / 0.12) ** 2) * 0.35
        tint = np.array([1.0, 0.98, 0.94], np.float32) + rng.uniform(-0.04, 0.04, 3).astype(np.float32)
        acc[sl] += ((disc * 0.75 * blot[sl] + rim * disc) * v)[..., None] * tint
    # a few fibres
    for k in range(5):
        p = np.array([rng.uniform(0, W), rng.uniform(0, H)])
        ang = rng.uniform(0, 2 * np.pi)
        pts = []
        for s in range(rng.integers(40, 110)):
            ang += rng.normal(0, 0.12)
            p = p + 1.6 * np.array([np.cos(ang), np.sin(ang)])
            pts.append(p.copy())
        line = np.zeros((H, W), np.float32)
        cv2.polylines(line, [np.array(pts, np.int32)], False, 1.0, 1, cv2.LINE_AA)
        line = cv2.GaussianBlur(line, (0, 0), 1.2)
        acc += (line * rng.uniform(0.3, 0.5))[..., None]
    # Godot multiplies the glow by mix(1, map, glow_map_strength): only bright smudges stand out against the clean
    # glass, so the brightest ones go up to white (WorldEnv raises the glow to make up for the darker clean areas)
    img = np.clip(acc * 1.8, 0.0, 1.0)
    Image.fromarray((img * 255.0 + 0.5).astype(np.uint8), "RGB").save(os.path.join(OUT, "lens_dirt.png"))


def _cells(rgba, cols, rows):
    """Bounding boxes of the separate leaves of an ambientCG LeafSet atlas, one per grid cell (from the alpha)."""
    h, w = rgba.shape[:2]
    out = []
    for r in range(rows):
        for c in range(cols):
            y0, y1, x0, x1 = r * h // rows, (r + 1) * h // rows, c * w // cols, (c + 1) * w // cols
            a = rgba[y0:y1, x0:x1, 3] > 128
            ys, xs = np.nonzero(a)
            out.append((x0 + xs.min(), y0 + ys.min(), x0 + xs.max() + 1, y0 + ys.max() + 1))
    return out


def _leaf(rgba, box, size, rot):
    """One leaf cut out, centred on a transparent square of `size` px, turned `rot` degrees."""
    x0, y0, x1, y1 = box
    pad = 8
    crop = rgba[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
    s = max(crop.shape[0], crop.shape[1])
    sq = np.zeros((s, s, 4), np.uint8)
    oy, ox = (s - crop.shape[0]) // 2, (s - crop.shape[1]) // 2
    sq[oy:oy + crop.shape[0], ox:ox + crop.shape[1]] = crop
    m = cv2.getRotationMatrix2D((s / 2, s / 2), rot, 1.0)
    sq = cv2.warpAffine(sq, m, (s, s), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    return cv2.resize(sq, (size, size), interpolation=cv2.INTER_AREA)


def _autumn(leaf, hue_to, sat_k, val_k):
    """Turns a leaf's colour toward an autumn hue (OpenCV hue units, 0-180), keeping its veins and spots."""
    rgb = leaf[..., :3]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[..., 0] = hsv[..., 0] * 0.1 + hue_to * 0.9
    hsv[..., 1] = np.clip(hsv[..., 1] * sat_k, 0, 255)
    hsv[..., 2] = np.clip(hsv[..., 2] * val_k, 0, 255)
    out = leaf.copy()
    out[..., :3] = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    return out


def leaves():
    plane = np.array(Image.open(os.path.join(TEX, "LeafSet029", "LeafSet029_diffa_2k.png")).convert("RGBA"))
    birch = np.array(Image.open(os.path.join(TEX, "LeafSet024", "LeafSet024_diffa_2k.png")).convert("RGBA"))
    pc = _cells(plane, 3, 3)
    bc = _cells(birch, 3, 3)
    S = 256
    tiles = [
        _leaf(plane, pc[7], S, 0),                                    # the yellowed plane leaf, as photographed
        _autumn(_leaf(plane, pc[4], S, 20), 12, 0.95, 0.8),           # a plane leaf gone brown-orange
        _autumn(_leaf(birch, bc[1], S, -30), 22, 1.6, 1.1),          # birch, bright yellow
        _autumn(_leaf(plane, pc[8], S, 45), 17, 0.9, 0.9),            # the spotted plane leaf, ochre
    ]
    atlas = np.zeros((2 * S, 2 * S, 4), np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, 2)
        atlas[r * S:(r + 1) * S, c * S:(c + 1) * S] = t
    # bleed the colour under the transparent texels so mipmaps do not darken the edges
    rgb = atlas[..., :3].astype(np.float32)
    a = (atlas[..., 3:4] > 8).astype(np.float32)
    acc, wsum = rgb * a, a.copy()
    for s in (2, 4, 8, 16):
        acc_b = cv2.GaussianBlur(rgb * a, (0, 0), s)
        w_b = cv2.GaussianBlur(a, (0, 0), s)[..., None]
        fill = (wsum < 0.5)
        acc = np.where(fill, acc_b / np.maximum(w_b, 1e-4) * 1.0, acc)
        wsum = np.where(fill, (w_b > 1e-3).astype(np.float32), wsum)
    atlas[..., :3] = np.clip(np.where(a > 0.5, rgb, acc), 0, 255).astype(np.uint8)
    Image.fromarray(atlas, "RGBA").save(os.path.join(OUT, "leaves_fall.png"))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    grain()
    lens_dirt()
    leaves()
    print("wrote", sorted(os.listdir(OUT)))
