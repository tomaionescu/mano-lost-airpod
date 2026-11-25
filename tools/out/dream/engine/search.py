"""Random search over the tumble's parameters (the dream's draw down the aisle, carpet friction, bounce,
rolling resistance) for a simulated tumble from the start keyframe's earbud pose that touches every tread on the
way down, keeps its hops low, rolls, and comes to rest close to the middle keyframe's pose (tumble.py then blends
out the small remainder). Writes search.json with the best candidates.

usage: python3.11 search.py [n] [seed]
"""
import json
import math
import sys
import time
from multiprocessing import Pool

import numpy as np

from earbud import Earbud, rot, floor_height

START = ((18.86, -0.15, 15.985), 0.35)
MID = ((19.05, -0.75, 14.12), -0.4)
BUD = None


def pull_table(q):
    """The dream's draw as a piecewise-linear table of acceleration over sim time: a stronger draw (with a lift,
    q["ay1"] g, that lightens it on the carpet) rolls it over the top step's yellow nosing, then a gentler one
    keeps it going down the aisle."""
    a1, t1, a2, dxr = q["a1"], q["t1"], q["a2"], q["dxr"]
    tr = q.get("tr", 0.15)
    ay1 = q.get("ay1", 0.0) * 9.81
    t1 = max(t1, tr + 0.02)
    ts = [0.0, tr, t1, t1 + 0.15, 9.0]
    acc = [[0.0, 0.0, 0.0], [dxr * a1, ay1, -a1], [dxr * a1, ay1, -a1], [dxr * a2, 0.0, -a2], [dxr * a2, 0.0, -a2]]
    return ts, acc


def run(q, log_dt=1.0 / 1000.0, t_end=2.4):
    from sim import simulate
    global BUD
    if BUD is None:
        BUD = Earbud()
    ts, acc = pull_table(q)
    r = simulate(BUD, START[0], rot((0, 1, 0), START[1]), ts, acc, log_dt=log_dt, t_end=t_end, e=q["e"], mu=q["mu"],
                 c_rr=q["crr"], roll_damp=q["rd"], zf0=q["zf1"] - q["zfw"], zf1=q["zf1"])
    return r


def yaw_split(R):
    psi = math.atan2(R[0, 2] - R[2, 0], R[0, 0] + R[2, 2])
    D = rot((0, 1, 0), psi).T @ R
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(D) - 1) / 2))))
    return psi, tilt


def analyse(r, bud, every=2):
    """Per-sample lowest point, floor under it, contact flag; contact periods ("touches") with their tread level."""
    t, o, b = r["t"][::every], r["o"][::every], r["b"][::every]
    P = np.einsum("nij,kj->nki", b, bud.pod_verts[::5]) + o[:, None, :]
    fl = floor_height(P[..., 2].ravel()).reshape(P.shape[:2])
    gap = (P[..., 1] - fl).min(axis=1)
    lowest = P[..., 1].min(axis=1)
    touch = gap < 0.0015
    # contact periods separated by at least 25 ms in the air
    periods = []
    i, n = 0, len(t)
    dt = t[1] - t[0]
    while i < n:
        if touch[i]:
            j = i
            while j + 1 < n and (touch[j + 1] or (not touch[j + 1] and any(touch[j + 1:j + 1 + int(0.025 / dt)]))):
                j += 1
            periods.append((t[i], t[j], int(round(lowest[i:j + 1].min() / 0.15))))
            i = j + 1
        else:
            i += 1
    # rise: how high the lowest point gets over the level it last touched
    rise, last = 0.0, lowest[0]
    for k in range(n):
        if touch[k]:
            last = lowest[k]
        else:
            rise = max(rise, lowest[k] - last)
    return {"periods": periods, "rise": float(rise), "lowest": lowest, "touch": touch, "t": t}


def score(q, r):
    bud = BUD
    t, o, b, nc, v, w = r["t"], r["o"], r["b"], r["nc"], r["v"], r["w"]
    speed = np.linalg.norm(v, axis=1)
    spin = np.linalg.norm(w, axis=1)
    moving = (speed > 0.004) | (spin > 0.08)
    idx = np.nonzero(moving)[0]
    t_rest = t[idx[-1]] if len(idx) else 0.0
    an = analyse(r, bud)
    levels = sorted(set(p[2] for p in an["periods"]))
    per_level = {l: sum(1 for p in an["periods"] if p[2] == l) for l in (-2, -3, -4, -5)}
    x_rng = (o[:, 0].min(), o[:, 0].max())
    psi, tilt = yaw_split(b[-1])
    tgt = np.array(MID[0])
    d_xz = math.hypot(o[-1][0] - tgt[0], o[-1][2] - tgt[2])
    d_y = o[-1][1] - tgt[1]
    dpsi = (psi - MID[1] + math.pi) % (2 * math.pi) - math.pi
    turns = float(np.sum(spin) * (t[1] - t[0]) / (2 * math.pi))
    vh = float(np.hypot(v[:, 0], v[:, 2]).max())
    multi = sum(1 for l in per_level if per_level[l] >= 2)
    ok = levels[:1] == [-5] and all(l in levels for l in (-5, -4, -3, -2, -1)) and abs(d_y) < 0.01
    ok = ok and x_rng[0] > 18.55 and x_rng[1] < 19.35
    cost = (d_xz * 30.0 + tilt * 0.015 + abs(dpsi) * 0.2 + max(an["rise"] - 0.035, 0.0) * 60.0
            + max(t_rest - 2.0, 0.0) * 5.0 + max(vh - 0.9, 0.0) * 3.0 + (4 - multi) * 0.6)
    return {"ok": bool(ok), "cost": float(cost), "d_xz": d_xz, "d_y": float(d_y), "tilt": tilt, "dpsi": dpsi,
            "rise": an["rise"], "t_rest": float(t_rest), "levels": levels, "x": [float(x_rng[0]), float(x_rng[1])],
            "turns": turns, "vh": vh, "per_level": per_level, "final": [float(c) for c in o[-1]]}


def sample(rng):
    return {"a1": rng.uniform(3.0, 12.0), "t1": rng.uniform(0.12, 0.45), "tr": rng.uniform(0.05, 0.25),
            "ay1": rng.uniform(0.0, 0.7), "a2": rng.uniform(0.5, 4.5), "dxr": rng.uniform(0.0, 0.25),
            "zf1": rng.uniform(14.45, 14.95), "zfw": rng.uniform(0.05, 0.35), "e": rng.uniform(0.1, 0.4),
            "mu": rng.uniform(0.4, 0.9), "crr": rng.uniform(0.002, 0.005), "rd": rng.uniform(1.0, 6.0)}


def job(args):
    seed, n = args
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        q = sample(rng)
        try:
            r = run(q)
            s = score(q, r)
        except Exception as ex:   # a numerical blow-up: skip
            continue
        out.append((q, s))
    return out


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    t0 = time.time()
    with Pool(10) as pool:
        res = pool.map(job, [(seed * 1000 + i, n // 10) for i in range(10)])
    allr = [x for chunk in res for x in chunk]
    good = sorted([x for x in allr if x[1]["ok"]], key=lambda x: x[1]["cost"])
    print("ran %d in %.0f s, %d ok" % (len(allr), time.time() - t0, len(good)))
    for q, s in good[:15]:
        print("cost %.3f d_xz %.3f tilt %.1f dpsi %.2f rise %.3f rest %.2f turns %.1f vh %.2f x %s per %s" % (
            s["cost"], s["d_xz"], s["tilt"], s["dpsi"], s["rise"], s["t_rest"], s["turns"], s["vh"],
            np.round(s["x"], 2), s["per_level"]))
    json.dump([{"q": q, "s": s} for q, s in good[:60]], open("search_%d.json" % seed, "w"), indent=1)


RANGES = {"a1": (3.0, 12.0), "t1": (0.12, 0.45), "tr": (0.05, 0.25), "ay1": (0.0, 0.7), "a2": (0.5, 4.5),
          "dxr": (0.0, 0.3), "zf1": (14.45, 14.95), "zfw": (0.05, 0.35), "e": (0.1, 0.4), "mu": (0.4, 0.9),
          "crr": (0.002, 0.005), "rd": (1.0, 6.0)}


def refine_cost(s):
    """The local search's cost: land on the middle keyframe's pose, in the lie, at a dream's pace."""
    return (s["d_xz"] * 80.0 + s["tilt"] * 0.03 + abs(s["dpsi"]) * 0.4 + max(s["rise"] - 0.03, 0.0) * 60.0
            + max(s["t_rest"] - 1.8, 0.0) * 6.0 + max(1.3 - s["t_rest"], 0.0) * 6.0 + max(s["vh"] - 1.7, 0.0) * 3.0
            + sum(max(2 - s["per_level"][l], 0) for l in s["per_level"]) * 0.5)


def refine_job(args):
    q0, seed, n, scale = args
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        q = dict(q0)
        for k, (lo, hi) in RANGES.items():
            q[k] = float(np.clip(q[k] + rng.normal(0.0, scale * (hi - lo)), lo, hi))
        try:
            r = run(q)
            s = score(q, r)
        except Exception:
            continue
        if s["ok"]:
            out.append((q, s, refine_cost(s)))
    return out


def refine(q0, rounds=4, n=400, seed=7):
    best = None
    with Pool(10) as pool:
        for rd in range(rounds):
            scale = 0.06 / (1.6 ** rd)
            res = pool.map(refine_job, [(q0, seed * 100 + rd * 10 + i, n // 10, scale) for i in range(10)])
            allr = sorted([x for c in res for x in c], key=lambda x: x[2])
            if allr and (best is None or allr[0][2] < best[2]):
                best = allr[0]
                q0 = best[0]
            if best:
                s = best[1]
                print("round %d: cost %.3f d_xz %.3f tilt %.1f dpsi %.2f rise %.3f rest %.2f vh %.2f per %s" % (
                    rd, best[2], s["d_xz"], s["tilt"], s["dpsi"], s["rise"], s["t_rest"], s["vh"], s["per_level"]),
                    flush=True)
    return best
