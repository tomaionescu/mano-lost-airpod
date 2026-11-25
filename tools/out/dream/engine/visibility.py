"""How much of the earbud the camera sees in each frame of a clip A track: the share of its outline's points with a
clear line of sight past the aisle's steps (their profile along z; the line stays inside the aisle), and its size."""
import json
import sys
import numpy as np
from earbud import Earbud, floor_height

BUD = Earbud()


def basis(a):
    return np.array(a[3:12]).reshape(3, 3).T


def visible_share(cam, P, n=48):
    """Share of points P whose segment from cam is never below the steps' surface (excluding the last 3 mm)."""
    vis = 0
    for p in P:
        d = p - cam
        L = np.linalg.norm(d)
        ts = np.linspace(0.0, 1.0 - 0.004 / L, n)
        pts = cam + ts[:, None] * d
        if np.all(pts[:, 1] >= floor_height(pts[:, 2]) - 1e-4):
            vis += 1
    return vis / len(P)


def frames(track, sub=3):
    out = []
    for f in range(track["frames"]):
        s = track["samples"][f * sub]
        cam = np.array(s["cam"][:3])
        P = BUD.pod_verts[::25] @ basis(s["bud"]).T + np.array(s["bud"][:3])
        # only the points facing up-ish matter little; take the hull's points
        out.append(visible_share(cam, P))
    return out


if __name__ == "__main__":
    tr = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "clipA_track.json"))
    v = frames(tr)
    low = [(i, round(x, 2)) for i, x in enumerate(v) if x < 0.9]
    print("frames with under 90% of the earbud in sight:", low)
