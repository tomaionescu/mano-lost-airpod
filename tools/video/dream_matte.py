#!/usr/bin/env python3.11
"""Clip A's earbud from the engine's own passes: a true soft matte, its own colour, its own shadow. Used by
join_dream.py --earbud-matte (step 4b); run on its own it checks the passes against clipA_mb.

  python3.11 tools/video/dream_matte.py --name clipA_mb16

Why: join_dream.py's --earbud-grade lifts the shaded earbud inside a matte cut from a brightness key (GrabCut seeded
with the bright core) against an inpainted floor. On the motion-blurred frames the key misses the blurred fringe and
the inpainting smears the yellow stripe under the earbud, so the lift flickers.

The passes. The engine renders the tumble again along clip A's own camera path and earbud tumble, 16 steps per frame
(tumble.py --warp retime.json --sub 16 --shutter 0.5 --name clipA_mb16, every step saved), in four passes
(scripts/dev/autotest.gd _dream3_clip_a: autotest=dream round2 clipA track=clipA_mb16_track passes=<pass>
crop=576x512, one Godot run each, --fixed-fps 384):
  normal   as clipA_mb was rendered (its background matches clipA_mb's to ~1 level, bias under 0.3)
  plate    the same without the earbud (matches the normal pass away from the earbud to 0.1 levels median)
  white    the earbud unshaded white (0.8), the fogs, glow, SSR, SSIL, colour adjustment, auto exposure and the dust
  black    off, a linear tonemap; the same with the earbud unshaded black
Each step is a 576x512 crop around the earbud (crops.json, the same in every pass). A frame averages its middle 12
steps in linear light under a tent (tent(): about the spread of clipA_mb's 180-degree shutter, but soft-edged, so the
spinning stem's stepped copies are gone). Then, in linear light:
  alpha = (white - black) / WHITE_LIN      the earbud's coverage: soft edge, motion blur, the carpet fibres in front
  E     = (normal - (1 - alpha) plate) / alpha   its own colour, unmixed from the floor (where alpha >= 0.12; further
                                           out it is carried in from the nearest reliable pixels)
E and the normal pass get clipA_mb's finish grade (finish.py: per-channel gain and offset eased along the clip).

The grade (grade_plan, grade): per frame, the highlight hl (95th percentile of E's luma where alpha >= 0.6). The
output's highlight is a smooth target T (max(hl, TARGET), Gaussian over +-2 frames), reached exactly on every frame by
L' = T (L / hl) ^ g: it cannot flicker with the source's own highlight. Then what the picture shows is measured
(the composite's own P95 where alpha >= 0.9: the shutter mixes floor into the fast frames) and each shaded frame's T
is corrected once by it (at most 12 %), so the viewer's highlight sits on T, +-1 level. The shade's share s (hl under the sun's ~235
levels, smoothed over +-2 frames) eases in g (1 in the sun, GAMMA in the shade: the shading kept, compressed), the
chroma (the earbud takes the cream of its own sunlit frames, A8-A20, keeping 1 - CHROMA of its own) and a roll-off
above 236. In the sun too, what is bluer than the cream (the render's sky-blue specular under the bud and the stem)
takes it (COOL_SUN). Only on the earbud's body (body(): the 1-2 px carpet fibres it shows through below it keep their
colour; lifted they hang under it as light drips).

The composite (composite): the normal pass itself, finish-graded and softened as the frame, plus alpha (E' - E) in
linear light, so its rendered shadow and fibres stay as they are; plus the smooth fill of (frame - normal pass) from
just outside, inside the earbud's support (alpha over 0.003 near its body, dilated 6 px; with flip.py's re-posed
frames, also where the old pose was), its outer 3 px fading into the frame. Every other pixel is left as it was.
"""
import argparse, glob, json, math, os, re, sys

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENGINE = os.path.join(ROOT, "tools", "out", "dream", "engine")
PASSES = ("normal", "plate", "white", "black")
SHUTTER = tuple(range(2, 14))          # the middle 12 of 16 steps, weighted by a tent (tent()): a soft shutter
WHITE_LIN = (0.8 + 0.055) / 1.055       # sRGB 0.8 in linear light, times the exposure (measured, see check())
WHITE_LIN = WHITE_LIN ** 2.4
A_RELIABLE = 0.12                       # E is unmixed where alpha is at least this
SUPPORT_T, SUPPORT_R = 0.003, 6         # the composite's region: alpha over this, dilated by this many px
COOL_SUN = 0.85                         # the blue specular's share taken to cream where the earbud is in the sun

_L = np.arange(256) / 255.0
LUT = np.where(_L <= 0.04045, _L / 12.92, ((_L + 0.055) / 1.055) ** 2.4).astype(np.float32)


def to_lin(v):
    """Display values 0..255 (float) -> linear light."""
    x = np.clip(np.asarray(v, np.float32) / 255.0, 0, None)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def to_disp(lin):
    x = np.clip(lin, 0, None)
    return (255.0 * np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)).astype(np.float32)


def luma(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def pass_dir(name, p):
    return os.path.join(ENGINE, name if p == "normal" else "%s_%s" % (name, p))


def rects(name):
    out = None
    for p in PASSES:
        r = json.load(open(os.path.join(pass_dir(name, p), "crops.json")))
        r = {int(k): tuple(v) for k, v in r.items()}
        if out is None:
            out = r
        elif r != out:
            sys.exit("dream_matte: %s's crops differ from the normal pass's" % p)
    return out


def tent(steps):
    """Weights of a tent over the steps, 1 at their middle, falling to 1/(n/2 + 0.5) at each end: a soft shutter.
    Over the middle 12 of 16 steps it spreads the motion about as far as a box over the middle 8 (a 180-degree
    shutter: standard deviation 2.45 steps against 2.31), but its steps fade in and out, so a fast-spinning stem shows
    no ribbed copies (the box's 8 equal copies, 1/16 of a frame apart, still read as ribs at 4x)."""
    c = 0.5 * (steps[0] + steps[-1])
    half = 0.5 * (steps[-1] - steps[0]) + 1
    return [1 - abs(m - c) / half for m in steps]


def average(d, f, steps, weights=None):
    """Steps of frame f in folder d averaged in linear light (weighted)."""
    weights = weights or [1.0] * len(steps)
    acc = None
    for m, w in zip(steps, weights):
        im = cv2.imread(os.path.join(d, "f%03d_%d.png" % (f, m)), cv2.IMREAD_COLOR)
        if im is None:
            raise FileNotFoundError(os.path.join(d, "f%03d_%d.png" % (f, m)))
        lin = LUT[im[..., ::-1]] * w
        acc = lin if acc is None else acc + lin
    return acc / sum(weights)


def finish_grade(i, n=108):
    """clipA_mb's finish.py grade at frame i: per-channel (gain, offset) on display values, eased by smoothstep."""
    chk = json.load(open(os.path.join(ENGINE, "clipA_mb_check.json")))
    g0, g1 = np.array(chk["grade_first"]), np.array(chk["grade_last"])
    u = min(max(i / (n - 1), 0.0), 1.0)
    w = u * u * (3 - 2 * u)
    g = g0 * (1 - w) + g1 * w
    return g[:, 0].astype(np.float32), g[:, 1].astype(np.float32)


def parse_smear(spec):
    """F0-F1:S0-S1 -> {frame: steps}."""
    out = {}
    for part in filter(None, (spec or "").split(";")):
        fr, st = part.split(":")
        f0, f1 = (int(x) for x in fr.split("-"))
        s0, s1 = (int(x) for x in st.split("-"))
        for f in range(f0, f1 + 1):
            out[f] = tuple(range(s0, s1 + 1))
    return out


class Matte:
    """The passes of one render (name), averaged per frame (cached in <name>_matte/fNNN.npz)."""

    def __init__(self, name, smear=None, n=108, flip=None):
        self.name, self.n = name, n
        self.rect = rects(name)
        self.smear = parse_smear(smear) if isinstance(smear, str) else (smear or {})
        self.cache = os.path.join(ENGINE, name + "_matte")
        os.makedirs(self.cache, exist_ok=True)
        # flip.py's re-posed track: its own normal, white and black passes for the frames it changes (the plate,
        # without the earbud, is this render's)
        self.flip, self.flip_frames = flip, set()
        if flip:
            ft = json.load(open(os.path.join(ENGINE, flip + "_track.json")))
            j0, j1 = ft["flip"]["steps"]
            sub = ft["sub"]
            self.flip_frames = set(range(j0 // sub, j1 // sub + 1))
            fr = json.load(open(os.path.join(ENGINE, flip, "crops.json")))
            for f in self.flip_frames:
                if tuple(fr[str(f)]) != self.rect[f]:
                    sys.exit("dream_matte: %s's crop at frame %d differs" % (flip, f))

    def dirs(self, f):
        if f in self.flip_frames:
            return [pass_dir(self.flip, p) if p != "plate" else pass_dir(self.name, p) for p in PASSES]
        return [pass_dir(self.name, p) for p in PASSES]

    def steps(self, f):
        return self.smear.get(f, SHUTTER)

    def frame(self, f):
        """dict(rect, a, E (straight, linear), P (plate, linear), N (normal, linear), rel)."""
        st = self.steps(f)
        tag = "t%d-%d%s" % (st[0], st[-1], "_flip" if f in self.flip_frames else "")
        path = os.path.join(self.cache, "f%03d_%s.npz" % (f, tag))
        srcs = [os.path.join(d, "f%03d_%d.png" % (f, st[-1])) for d in self.dirs(f)]
        if os.path.exists(path) and all(os.path.getmtime(path) >= os.path.getmtime(s) for s in srcs):
            z = np.load(path)
            N, P, Wt, Bk = (z[k].astype(np.float32) for k in ("N", "P", "W", "B"))
        else:
            N, P, Wt, Bk = (average(d, f, st, tent(st)) for d in self.dirs(f))
            np.savez_compressed(path, N=N.astype(np.float16), P=P.astype(np.float16), W=Wt.astype(np.float16),
                                B=Bk.astype(np.float16))
        a = np.clip((Wt - Bk).mean(2) / WHITE_LIN, 0, 1)
        a[a < 0.002] = 0
        pe = N - (1 - a[..., None]) * P
        rel = np.clip((a - A_RELIABLE) / 0.25, 0, 1)
        E = np.where(a[..., None] > 0.02, pe / np.maximum(a, 0.02)[..., None], 0)
        E = np.clip(E, 0, 1.2)
        # unreliable E (thin blur, the very edge): carried in from reliable pixels nearby (normalized convolution)
        w = (rel * a).astype(np.float32)
        Ef = E.copy()
        todo = rel < 1
        for s in (1.5, 3, 6, 12):
            den = cv2.GaussianBlur(w, (0, 0), s)
            num = cv2.GaussianBlur(E * w[..., None], (0, 0), s)
            ok = todo & (den > 0.02)
            ext = num / np.maximum(den, 1e-6)[..., None]
            Ef[ok] = (rel[..., None] * E + (1 - rel[..., None]) * ext)[ok]
            todo &= ~ok
        x, y, ww, hh = self.rect[f]
        out = dict(rect=(x, y, ww, hh), a=a.astype(np.float32), E=Ef.astype(np.float32), P=P, N=N, rel=rel)
        if f in self.flip_frames:
            # the earbud's old place in the frame (clipA_mb's pose) is replaced too
            ao = np.clip((average(pass_dir(self.name, "white"), f, st, tent(st))
                          - average(pass_dir(self.name, "black"), f, st, tent(st))).mean(2) / WHITE_LIN, 0, 1)
            out["old_support"] = (ao > SUPPORT_T) & (cv2.dilate((body(ao) > 0.5).astype(np.uint8),
                                                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                                                          (21, 21))) > 0)
        return out


def stats(E_disp, a):
    """Highlight (P95), median and low (P20) luma of the earbud where alpha >= 0.6 (or 0.35 on a thin frame)."""
    for t in (0.6, 0.35, 0.15):
        m = a >= t
        if m.sum() >= 40:
            L = luma(E_disp[m])
            return dict(hl=float(np.percentile(L, 95)), md=float(np.median(L)), lo=float(np.percentile(L, 20)),
                        n=int(m.sum()), t=t)
    return None


def cream(Ed_list, a_list):
    """The earbud's chroma per unit luma in its sunlit frames (the cream it should keep in the shade): the median of
    rgb / luma over pixels with alpha >= 0.8 and luma 150-235."""
    vals = []
    for Ed, a in zip(Ed_list, a_list):
        L = luma(Ed)
        m = (a >= 0.8) & (L > 150) & (L < 235)
        if m.any():
            vals.append(Ed[m] / L[m][:, None])
    v = np.concatenate(vals, 0)
    c = np.median(v, 0)
    return c / float(luma(c[None])[0])


def grade_plan(st, target=216.0, gamma=0.7, sun=235.0, sigma=2.0, chroma=0.85):
    """Per frame: [hl, T (the output's highlight), s (shade share), g (exponent), c (chroma replaced)]. st: {frame:
    stats}; frames without stats are interpolated."""
    ks = sorted(k for k, v in st.items() if v)
    hl = np.array([st[k]["hl"] for k in ks])
    full = np.arange(ks[0], ks[-1] + 1)
    hlf = np.interp(full, ks, hl)
    T = gaussian_filter1d(np.maximum(hlf, target), sigma, mode="nearest")
    s = gaussian_filter1d(np.clip((sun - hlf) / 30.0, 0, 1), sigma, mode="nearest")
    out = {}
    for j, f in enumerate(full):
        g = 1.0 - (1.0 - gamma) * s[j]
        out[int(f)] = dict(hl=float(hlf[j]), T=float(T[j]), s=float(s[j]), g=float(g), c=float(chroma * s[j]))
    return out


def body(a):
    """The earbud's body in its matte (0..1): alpha over 0.06, opened by a 5 px disc (so the carpet fibres' 1-2 px
    gaps it shows through below it drop out), its largest piece, dilated 1 px and softened. The fibre strands keep
    their own colour: lifted to cream they hung under the earbud as light drips."""
    m = cv2.morphologyEx((a > 0.06).astype(np.uint8), cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        m = (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8)
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    return cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.0)


def grade(Ed, plan, tint, kb=None):
    """E' (display) from E (display) by a frame's plan: L' = T (L / hl)^g, chroma toward tint * L', rolled off; kb
    (the body, 0..1) weighs it per pixel."""
    L = np.maximum(luma(Ed), 0.5)
    Lp = plan["T"] * np.power(L / plan["hl"], plan["g"])
    own = Ed * (Lp / L)[..., None]
    # in the sun too, whatever is bluer than the cream (the render's sky-blue specular under the bud and along the
    # stem, which the old grade's COOL took out there) takes the cream: c is the shade's share, COOL_SUN the rest
    cool = np.clip(((own[..., 2] - own[..., 0]) - (tint[2] - tint[0]) * Lp) / (0.05 * Lp + 4.0), 0, 1)
    c = plan["c"] + (1 - plan["c"]) * COOL_SUN * cool
    J = own + c[..., None] * (tint[None, None, :] * Lp[..., None] - own)
    J = J + plan["s"] * (np.where(J > 236, 236 + (J - 236) * 0.35, J) - J)    # the roll-off in the shade only
    return J if kb is None else Ed + kb[..., None] * (J - Ed)


def fill(D, known, sigmas=(2, 4, 8, 16, 32, 64)):
    """D (h, w, 3) known where `known`, filled in elsewhere by normalized convolution, finest scale first."""
    out = D * known[..., None]
    todo = ~known
    w = known.astype(np.float32)
    for s in sigmas:
        if not todo.any():
            break
        den = cv2.GaussianBlur(w, (0, 0), s)
        num = cv2.GaussianBlur(D * w[..., None], (0, 0), s)
        ok = todo & (den > 0.03)
        out[ok] = (num / np.maximum(den, 1e-6)[..., None])[ok]
        todo &= ~ok
    return out


def support(a, extra=None):
    """The composite's region: alpha over SUPPORT_T near the earbud's body (isolated specks of the white - black
    difference elsewhere are 8-bit noise), with `extra` (the earbud's old place, for re-posed frames), dilated
    SUPPORT_R px."""
    near = cv2.dilate((body(a) > 0.5).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))) > 0
    m = (a > SUPPORT_T) & near
    if extra is not None:
        m |= extra
    return cv2.dilate(m.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                      (2 * SUPPORT_R + 1, 2 * SUPPORT_R + 1))) > 0


def composite(raw, fr, Ed, Eg, sigma, gain, off):
    """The frame `raw` (uint8 RGB, clip A's decoded and softened frame) with its earbud replaced by the normal pass's
    (8 steps, its own rendered shadow and fibres), graded: in linear light the normal pass plus alpha (Eg - Ed), the
    earbud's own colour change (Ed as rendered, Eg graded, display values in clip A's space), finish-graded and
    softened as the frame. Only inside the support; a smooth fill of (frame - normal pass) from just outside it takes
    out any low-frequency difference (the encode, the dust), and its outer 3 px fade into the frame. Returns (new
    raw, support mask in the crop, stats)."""
    x, y, w, h = fr["rect"]
    R = raw[y:y + h, x:x + w].astype(np.float32)
    a = fr["a"]
    sup = support(a, fr.get("old_support"))
    Ng = to_disp(fr["N"]) * gain + off
    if sigma > 0.05:
        Ng = cv2.GaussianBlur(Ng, (0, 0), sigma)
    ring = (cv2.dilate(sup.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))) > 0) & ~sup
    D = R - Ng
    Dfill = fill(D, ring | ~sup)
    delta = a[..., None] * (to_lin(Eg) - to_lin(Ed))
    if sigma > 0.05:
        delta = cv2.GaussianBlur(delta, (0, 0), sigma)
    out = to_disp(to_lin(Ng + Dfill) + delta)
    # meet the untouched frame: the support's outer 3 px fade into it (alpha is ~0 there, so out ~ normal ~ raw)
    dist = cv2.distanceTransform(sup.astype(np.uint8), cv2.DIST_L2, 3)
    wgt = np.clip(dist / 3.0, 0, 1)[..., None]
    new = R * (1 - wgt) + out * wgt
    res = raw.copy()
    res[y:y + h, x:x + w] = np.clip(new + 0.5, 0, 255).astype(np.uint8)
    edge = sup & (dist <= 4)
    st = dict(ring_resid=float(np.abs(D[ring]).mean()) if ring.any() else 0.0,
              edge_step=float(np.abs(new - R)[edge].mean()) if edge.any() else 0.0)
    return res, sup, st


def apply_to_clip(raw, frames, matte, sigmas, target=216.0, gamma=0.7, chroma=0.85, log=print):
    """Step 4b with --earbud-matte: every frame in `frames` gets the matte's earbud (graded) composited in place of its
    own. raw: clip A's frames (N, 1080, 1920, 3) uint8, modified in place. Returns the per-frame record."""
    Ed, A, st = {}, {}, {}
    for f in frames:
        fr = matte.frame(f)
        gain, off = finish_grade(f, len(raw))
        Ed[f] = to_disp(fr["E"]) * gain + off
        A[f] = fr["a"]
        st[f] = stats(Ed[f], fr["a"])
    sunlit = [f for f in frames if 8 <= f <= 20]
    tint = cream([Ed[f] for f in sunlit], [A[f] for f in sunlit])
    plan = grade_plan(st, target, gamma, chroma=chroma)
    # what the picture shows: the composite's own highlight (P95 of its luma where the earbud covers the pixel,
    # alpha >= 0.9) falls below T on the fast frames, where the shutter mixes the floor in. So each shaded frame's
    # target is corrected once by what its first composite showed (by the shade's share s, at most 12 %), and the
    # composite is made again: the highlight the viewer sees is the smooth T on every frame.
    src = {}
    for f in frames:
        x, y, w, h = matte.rect[f]
        src[f] = raw[f][y:y + h, x:x + w].copy()
    seen = {}
    for rnd in range(2):
        rec = {}
        for f in frames:
            fr = matte.frame(f)
            gain, off = finish_grade(f, len(raw))
            p = plan.get(f)
            if p and rnd == 1 and seen.get(f):
                k = np.clip(p["T0"] / seen[f], 1.0, 1.12) if "T0" in p else 1.0
                p = dict(p, T=p["T0"] * (1 + p["s"] * (k - 1)))
            Eg = grade(Ed[f], p, tint, body(fr["a"])) if p else Ed[f]
            sig = float(sigmas[f]) if sigmas is not None else 0.0
            x, y, w, h = fr["rect"]
            raw[f][y:y + h, x:x + w] = src[f]
            raw[f], sup, cst = composite(raw[f], fr, Ed[f], Eg, sig, gain, off)
            shown = None
            for t in (0.9, 0.7, 0.5):
                m = fr["a"] >= t
                if m.sum() >= 40:
                    shown = float(np.percentile(luma(raw[f][y:y + h, x:x + w][m].astype(np.float32)), 95))
                    break
            if rnd == 0:
                seen[f] = shown
                if p:
                    p["T0"] = p["T"]
            after = stats(Eg, fr["a"])
            rec[f] = dict(hl_src=round(st[f]["hl"], 1) if st[f] else None, T=round(p["T"], 1) if p else None,
                          s=round(p["s"], 3) if p else None, g=round(p["g"], 3) if p else None,
                          hl_out=round(after["hl"], 1) if after else None,
                          md_out=round(after["md"], 1) if after else None,
                          hl_shown=round(shown, 1) if shown else None, hl_shown_first=round(seen[f], 1)
                          if seen.get(f) else None, ring_resid=round(cst["ring_resid"], 2),
                          edge_step=round(cst["edge_step"], 2), steps=list(matte.steps(f))[::len(matte.steps(f)) - 1])
    log("    earbud matte %s: frames %d-%d, cream %s, highlight out %s" % (
        matte.name, frames[0], frames[-1], np.round(tint, 3).tolist(),
        {f: rec[f]["hl_shown"] for f in frames[::8]}))
    return dict(tint=np.round(tint, 4).tolist(), target=target, gamma=gamma, chroma=chroma, frames=rec)


def check(name):
    """The passes against each other and against clipA_mb (the 4-step render the clip is made of)."""
    m = Matte(name)
    rows = []
    for f in range(0, m.n, 1):
        fr = m.frame(f)
        x, y, w, h = fr["rect"]
        Wt_minus_B = fr["a"]
        orig = cv2.imread(os.path.join(ENGINE, "clipA_mb_avg", "f%03d.png" % f))[..., ::-1][y:y + h, x:x + w]
        Nd = to_disp(fr["N"])
        far = cv2.dilate((fr["a"] > 0.002).astype(np.uint8), np.ones((31, 31), np.uint8)) == 0
        rows.append(dict(f=f, a_max=round(float(Wt_minus_B.max()), 3), a_area=round(float(Wt_minus_B.sum()), 1),
                         bg_normal_vs_orig=round(float(np.abs(Nd[far] - orig[far]).mean()), 2),
                         bg_bias=np.round((Nd[far] - orig[far]).mean(0), 2).tolist()))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="clipA_mb16")
    ap.add_argument("--frames", default="0-107")
    args = ap.parse_args()
    rows = check(args.name)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
