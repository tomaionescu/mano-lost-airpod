"""The earbud's fall off the second nosing as a cartwheel.

    python3.11 tools/out/dream/engine/flip.py [--src clipA_mb16] [--name clipA_mb16f] [--from 63.25] [--to 69.0]
                                              [--turns -1]

In clipA_mb (out 66-69, A63-A66) the earbud drops off the nosing and, seen from the camera, hangs stem straight down
under the bud for two to three frames, like a lollipop on its stick. In 3D it does turn evenly then (its stem swings
34-52 degrees a frame), but through the plane of the view, so its picture barely moves: the stem's angle on screen
goes 155 -> 92 degrees, stays at 92-95 for two frames, then whips back round through 180 to 224 in about one frame (as
the stem passes the line of sight).

This keeps the fall and everything else of the pose, and turns the earbud about its line of sight (the ray from the
camera through its centre of mass) by just what makes the stem's angle on screen follow a smooth, one-way path over
the flight [--from, --to] (output frames): a cubic from the angle and rate it has at --from to its angle at --to plus
--turns whole turns (so it lands in the very same pose) and its rate there. With -1 the stem keeps turning the way it
started, about 50 degrees a frame on screen, a cartwheel, smeared along the turn by the 180-degree shutter. Every
centre of mass stays exactly where it was; nothing changes outside the window; every new pose is checked against the
steps (earbud.penetration). Writes <name>_track.json (frames into <name>/), the same steps and crops as the source
track: render it with autotest=dream round2 clipA track=<name>_track passes=normal / white / black crop=576x512 (the
plate pass, without the earbud, is the source's).
"""
import argparse, json, math, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from earbud import Earbud, penetration, lathe   # noqa: E402
from tumble import project                      # noqa: E402


def exp_rot(w):
    ang = float(np.linalg.norm(w))
    if ang < 1e-12:
        return np.eye(3)
    k = w / ang
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * K @ K


def unpack(s):
    c, b = s["cam"], s["bud"]
    return (np.array(c[:3]), np.array(c[3:12]).reshape(3, 3).T, s["fov"], np.array(b[:3]),
            np.array(b[3:12]).reshape(3, 3).T)


def stem_points():
    """The stem's tip and the bud's centre in the pod frame."""
    bud = Earbud()
    v, t, rings, segs = lathe()
    pod = bud.pod_verts
    head_ring = int(rings * 0.031 / (0.031 + 0.0088 * 1.12))
    return pod[:segs].mean(0), pod[head_ring * segs:(head_ring + 1) * segs].mean(0)


def screen_angle(s, tip, head, B=None, O=None):
    pos, Bc, fov, O0, B0 = unpack(s)
    B = B0 if B is None else B
    O = O0 if O is None else O
    tx, ty, _ = project(O + B @ tip, pos, Bc, fov)
    hx, hy, _ = project(O + B @ head, pos, Bc, fov)
    return math.atan2(ty - hy, tx - hx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="clipA_mb16")
    ap.add_argument("--name", default="clipA_mb16f")
    ap.add_argument("--from", dest="f0", type=float, default=63.25, help="output frame the extra turn starts")
    ap.add_argument("--to", dest="f1", type=float, default=69.0, help="output frame it ends")
    ap.add_argument("--turns", type=int, default=-1, help="whole turns added on screen over the window")
    args = ap.parse_args()
    tr = json.load(open(os.path.join(HERE, args.src + "_track.json")))
    S, sub = tr["samples"], tr["sub"]
    bud = Earbud()
    com = bud.com
    tip, head = stem_points()
    j0, j1 = int(round(args.f0 * sub)), int(round(args.f1 * sub))
    # the stem's angle on screen, unwrapped, from a step before the window to one after it
    js = list(range(j0 - 2, j1 + 3))
    th = np.unwrap([screen_angle(S[j], tip, head) for j in js])
    t0, t1 = th[2], th[-3]
    r0, r1 = (th[3] - th[1]) / 2, (th[-2] - th[-4]) / 2          # per step
    n = j1 - j0
    t1t = t1 + 2 * math.pi * args.turns
    out = json.loads(json.dumps(tr))
    worst, worst0, target, extra, got = 0.0, 0.0, [], [], []
    prev = 0.0
    for k, j in enumerate(range(j0, j1 + 1)):
        u = k / n
        h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
        want = h00 * t0 + h10 * n * r0 + h01 * t1t + h11 * n * r1
        pos, Bc, fov, O, B = unpack(S[j])
        c = O + B @ com
        ray = (c - pos) / np.linalg.norm(c - pos)
        # the angle about the line of sight that turns the stem's picture to `want`: Newton on the picture's angle
        # (numeric slope; perspective makes it not quite one for one), from the better of the two signs
        def err(x):
            Rx = exp_rot(ray * x) @ B
            g = screen_angle(S[j], tip, head, Rx, c - Rx @ com)
            return math.atan2(math.sin(want - g), math.cos(want - g))
        d0 = want - th[k + 2]
        a = min((d0, -d0, prev), key=lambda x: abs(err(x)))
        for _ in range(8):
            e = err(a)
            if abs(e) < 1e-5:
                break
            slope = (err(a + 1e-3) - e) / 1e-3
            a -= e / slope if abs(slope) > 1e-3 else -e
        prev = a
        Rn = exp_rot(ray * a) @ B
        on = c - Rn @ com
        for P0, new in ((bud.pod_verts @ B.T + O, False), (bud.pod_verts @ Rn.T + on, True)):
            hit, depth, _ = penetration(P0)
            d = float(depth[hit].max()) if hit.any() else 0.0
            if new:
                worst = max(worst, d)
            else:
                worst0 = max(worst0, d)
        out["samples"][j]["bud"] = [*on.tolist(), *Rn.T.reshape(-1).tolist()]
        target.append(want)
        extra.append(a)
        got.append(screen_angle(out["samples"][j], tip, head))
    got = np.unwrap(got)
    rate = np.diff(got) * sub
    out["out"] = args.name
    out["flip"] = dict(src=args.src, frames=[args.f0, args.f1], steps=[j0, j1], turns=args.turns,
                       screen_deg_from_to=[math.degrees(t0), math.degrees(t1t)],
                       screen_deg_per_frame_min_max=[float(np.degrees(rate.min())), float(np.degrees(rate.max()))],
                       extra_deg_max=float(np.degrees(np.abs(extra).max())), deepest_mm=worst * 1000,
                       deepest_src_mm=worst0 * 1000)
    dst = os.path.join(HERE, args.name + "_track.json")
    json.dump(out, open(dst, "w"))
    print("%s: steps %d-%d (frames %.2f-%.2f); the stem on screen %.0f -> %.0f deg, %.0f..%.0f deg/frame; extra turn "
          "up to %.0f deg; deepest into a step %.2f mm (the source's %.2f mm)" % (
              dst, j0, j1, args.f0, args.f1, math.degrees(t0), math.degrees(t1t),
              *out["flip"]["screen_deg_per_frame_min_max"], out["flip"]["extra_deg_max"], worst * 1000, worst0 * 1000))


if __name__ == "__main__":
    main()
