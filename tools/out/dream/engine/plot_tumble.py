"""Side and top views of a simulated tumble: the aisle's profile and the earbud's outline every few hundredths
of a second (earlier = lighter), for judging the bounces before rendering."""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.spatial import ConvexHull
from earbud import SECTIONS


def plot(t, o, b, verts, path, every=0.04, title="", target=None):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(16, 9), gridspec_kw={"height_ratios": [1.3, 1]})
    zs, ys = [], []
    for z0, z1, h in SECTIONS:
        zs += [min(z1, 16.6), max(z0, 13.4)]
        ys += [h, h]
    a1.plot(zs, ys, "k-", lw=1)
    a1.fill_between(zs, ys, -1.2, color="0.85")
    step = max(int(round(every / (t[1] - t[0]))), 1)
    idx = list(range(0, len(t), step)) + [len(t) - 1]
    for n, i in enumerate(idx):
        P = verts @ b[i].T + o[i]
        c = plt.cm.viridis(i / max(len(t) - 1, 1))
        for ax, (u, v) in ((a1, (2, 1)), (a2, (2, 0))):
            pts = P[:, [u, v]]
            try:
                h = ConvexHull(pts)
                poly = pts[h.vertices]
                ax.fill(poly[:, 0], poly[:, 1], color=c, alpha=0.55, lw=0)
            except Exception:
                pass
    if target is not None:
        for ax, (u, v) in ((a1, (2, 1)), (a2, (2, 0))):
            pts = target[:, [u, v]]
            h = ConvexHull(pts)
            poly = pts[h.vertices]
            ax.plot(np.r_[poly[:, 0], poly[:1, 0]], np.r_[poly[:, 1], poly[:1, 1]], "r-", lw=1)
    a1.set_xlim(16.15, 13.85)
    a1.set_ylim(-0.85, -0.05)
    a1.set_aspect("equal")
    a1.set_title(title + "  side view (z ->, y up)")
    a2.set_xlim(16.15, 13.85)
    a2.set_ylim(18.6, 19.4)
    a2.set_aspect("equal")
    a2.set_title("top view (z, x)")
    for z0, z1, h in SECTIONS:
        a2.axvline(z0, color="0.7", lw=0.5)
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)
