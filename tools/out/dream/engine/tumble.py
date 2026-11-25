"""Engine dream clip A (start.png -> mid.png): the earbud's tumble and the camera's glide, sampled for the render.

    python3.11 tools/out/dream/engine/tumble.py --sway=-0.00142,-0.00355,0.00181,-0.00004

writes tools/out/dream/engine/clipA_track.json, which `autotest=dream round2 clipA` (scripts/dev/autotest.gd,
_dream3_clip_a) plays back frame by frame: 4 s at 24 fps, 3 render steps per frame (72 Hz, every third saved).
Deterministic: the same command writes the same file, byte for byte.

The earbud: sim.py simulates it rolling off the top step's edge from its start.png pose (autotest DREAM2_START_BUD)
and tumbling down the aisle steps under the dream's draw (a horizontal pull down the aisle, faded out over the last
tread; search.py then refine.py found the parameters Q: it touches every tread, two or three low bounces on each,
under 2.2 cm high, tumbles and rolls, and comes to rest on the third tier's half step 3 cm from mid.png's earbud).
What is left at rest (3.2 cm, a 25 deg turn) is taken out while the earbud is in the air (none of it while it
touches a tread, so nothing slides), and while it touches a tread its lowest point is kept on the tread (at most
3 mm of lift). The last pose is mid.png's exactly (DREAM2_MID_BUD). Sim time is played at about 0.58x: the draw
starts at T0, it lies still from T_REST on.

The camera: the dream's path (autotest _dream2_path: Hermite/Catmull-Rom through start -> mid -> the desk shot), from
the start camera to the mid camera. The glide starts from rest, eases in over the first second and then keeps a
constant speed along the path's parameter into mid (glide(): no acceleration there, so B's leg can carry on at the
same speed, one glide); it turns right on the same curve; it tilts down with a smoothstep (no tilt rate at either end:
B tilts back up), plus up to 7 deg more in the middle (aim()) so the falling earbud stays in the frame's upper 80 %.
Field of view and depth of field go from the start keyframe's to the middle one's. --sway adds the handheld offsets
the keyframes were shot with (camera_rig._apply_sway: rotate_object_local RIGHT rx then UP ry, radians), measured with
measure.py on a first render without them (start.png: 4.2 px left and 1.7 px up of the swayless frame; mid.png: 2.3 px
down), eased from the first to the last frame.

The slowed, motion-blurred clip:

    python3.11 tools/out/dream/engine/retime.py          # writes retime.json (the time warp)
    python3.11 tools/out/dream/engine/tumble.py --sway=-0.00142,-0.00355,0.00181,-0.00004 --warp retime.json \
        --sub 8 --shutter 0.5 --name clipA_mb

writes clipA_mb_track.json for `autotest=dream round2 clipA track=clipA_mb_track` (run with --fixed-fps 192). The
same camera path and tumble on clip time, sampled at output times through the warp (retime.json: output seconds ->
clip seconds; the clip plays slower where the camera's picture speed would run over a cap, never faster), with --sub
steps per output frame centred on it (offsets (m - (sub - 1) / 2) / sub of a frame) of which the middle
round(shutter * sub) are saved, fNNN_m.png, for finish.py to average: a real 180-degree shutter (the camera, the
earbud's tumble, the dust), not a vector blur. aim()'s extra tilt is computed on the original 72 Hz grid and read
at each step's clip time, so the camera's path in clip time is exactly the uniform clip's; the few samples past
mid.png (half a shutter) carry the glide on (glide() and path_a() unclamped there).
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from earbud import Earbud, rot, floor_height   # noqa: E402
import search                                   # noqa: E402

FPS = 24
SUB = 3                 # render steps per frame
FRAMES = 96             # 4 s; frame 0 = start.png, frame 95 = mid.png
T0 = 0.30               # clip time the draw starts (the earbud lies still before it)
T_REST = 3.65           # clip time it comes to rest (still for the last 0.3 s)
U_EASE = 0.25           # the camera's ease-in, as a share of the clip (1 s)

# the tumble (refine_0_2_6_1.json, candidate 0)
Q = {"a1": 7.874081225576998, "t1": 0.2637244395643421, "tr": 0.1257728433333454, "ay1": 0.3688938040007374,
     "a2": 3.8908060741658645, "dxr": 0.25215658475351144, "zf1": 14.705464883015983, "zfw": 0.3065959826451015,
     "e": 0.3292746891151109, "mu": 0.6131482828608641, "crr": 0.0031709506211065543, "rd": 2.6474021492894986}

# keyframes (autotest.gd DREAM2_START, DREAM2_MID, the desk shot from main.wake_shots())
CAM0 = (np.array([18.8, 0.1, 16.6]), np.array([18.8, -1.2, 9.5]), 46.0, [8.0, 8.0, 0.42, 0.25, 0.035])
CAM1 = (np.array([18.9, 0.6, 15.3]), np.array([19.56, -0.83, 13.35]), 44.0, [4.5, 8.0, 0.0, 0.0, 0.045])
DESK = np.array([19.55, 0.22, 14.7])
BUD0 = (np.array([18.86, -0.15, 15.985]), 0.35)
BUD1 = (np.array([19.05, -0.75, 14.12]), -0.4)
W, H = 1920, 1080


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u)


def glide(u, extend=False):
    """The camera's progress along its path: from rest, a smoothstep rise in speed over the first U_EASE of the clip,
    then a constant speed (1/(1 - U_EASE/2) times the average), so it arrives at mid without acceleration and can glide
    on into B. (An earlier, slower start, 1.5u^2 - 0.5u^3, left the camera so low that the second tier's edge hid the
    earbud for three frames as it dropped past it; see visibility.py.)"""
    u = max(u, 0.0) if extend else min(max(u, 0.0), 1.0)
    vc = 1.0 / (1.0 - U_EASE / 2.0)
    if u < U_EASE:
        x = u / U_EASE
        return vc * U_EASE * (x ** 3 - 0.5 * x ** 4)
    return vc * (U_EASE * 0.5 + (u - U_EASE))


def hermite(a, ma, b, mb, s):
    s2, s3 = s * s, s * s * s
    return a * (2 * s3 - 3 * s2 + 1) + ma * (s3 - 2 * s2 + s) + b * (-2 * s3 + 3 * s2) + mb * (s3 - s2)


def path_a(s):
    """autotest _dream2_path's first half (t = s / 2)."""
    p0, p1, p2 = CAM0[0], CAM1[0], DESK
    return hermite(p0, p1 - p0, p1, (p2 - p0) * 0.5, s)


def yaw_pitch(d):
    return math.atan2(d[0], -d[2]), math.atan2(d[1], math.hypot(d[0], d[2]))


def looking_at(d):
    """Godot Basis.looking_at(d, UP): columns x, y, z with -z along d."""
    z = -np.asarray(d, float) / np.linalg.norm(d)
    x = np.cross([0.0, 1.0, 0.0], z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=1)


def slerp_rot(C, w):
    """The rotation C raised to the power w (C = exp(axis*angle))."""
    tr = np.clip((np.trace(C) - 1) / 2, -1.0, 1.0)
    ang = math.acos(tr)
    if ang < 1e-9:
        return np.eye(3)
    axis = np.array([C[2, 1] - C[1, 2], C[0, 2] - C[2, 0], C[1, 0] - C[0, 1]]) / (2 * math.sin(ang))
    return rot(axis, ang * w)


def tumble():
    """The corrected tumble on sim time: t, pod origins, pod bases (1 kHz), and the sim's own result."""
    r = search.run(Q, t_end=2.4)
    bud = search.BUD
    t, o, b, x = r["t"], r["o"].copy(), r["b"].copy(), r["x"].copy()
    an = search.analyse(r, bud, every=1)
    touch = an["touch"]
    # rest: the last sample anything moves
    speed = np.linalg.norm(r["v"], axis=1)
    spin = np.linalg.norm(r["w"], axis=1)
    i_rest = int(np.nonzero((speed > 0.004) | (spin > 0.08))[0][-1]) + 1
    # what is left to take out, at the end
    Rt = rot((0, 1, 0), BUD1[1])
    com_t = BUD1[0] + Rt @ bud.com
    C = Rt @ b[i_rest].T
    d_xz = com_t - x[i_rest]
    d_xz[1] = 0.0
    # spent only in the air, up to the last landing
    last_land = int(np.nonzero(~touch[:i_rest])[0][-1]) + 1
    air = (~touch).astype(float)
    air[last_land:] = 0.0
    wgt = np.cumsum(air)
    wgt /= wgt[-1]
    wgt = np.r_[0.0, wgt[:-1]]
    O, B = [], []
    gaps = np.zeros(len(t))
    pv = bud.pod_verts[::3]
    for i in range(len(t)):
        k = i if i < i_rest else i_rest
        Ci = slerp_rot(C, wgt[k])
        Rb = Ci @ b[k]
        com = x[k] + wgt[k] * d_xz
        o_i = com - Rb @ bud.com
        P = pv @ Rb.T + o_i
        gaps[i] = (P[:, 1] - floor_height(P[:, 2])).min()
        O.append(o_i)
        B.append(Rb)
    O, B = np.array(O), np.array(B)
    # keep the lowest point on the tread while touching; ease the lift across the flights
    lift = np.where(touch, -gaps, np.nan)
    lift[0] = 0.0
    idx = np.arange(len(t))
    ok = ~np.isnan(lift)
    lift = np.interp(idx, idx[ok], lift[ok])
    lift = np.maximum(lift, -gaps)          # never into a tread
    O[:, 1] += lift
    # the end: exactly the middle keyframe's pose
    O[i_rest:] = BUD1[0]
    B[i_rest:] = Rt
    err = np.linalg.norm(O[i_rest - 1] - BUD1[0])
    return t, O, B, i_rest, {"d_xz_m": float(np.linalg.norm(d_xz)), "rot_deg": math.degrees(math.acos(
        np.clip((np.trace(C) - 1) / 2, -1, 1))), "t_rest_sim": float(t[i_rest]), "step_into_rest_m": float(err),
        "max_lift_mm": float(np.abs(lift).max() * 1000), "touch": touch}


def camera(u, sway=(0.0, 0.0, 0.0, 0.0), tilt=0.0, extend=False):
    """The camera at clip progress u: position, basis, fov, depth of field. `tilt` (radians) tilts it further down
    (aim(): it keeps the earbud out of the bottom of the frame)."""
    s = glide(u, extend)
    k = smooth(u)
    pos = path_a(s)
    y0, p0 = yaw_pitch(CAM0[1] - CAM0[0])
    y1, p1 = yaw_pitch(CAM1[1] - CAM1[0])
    yaw = y0 + (y1 - y0) * s
    pitch = p0 + (p1 - p0) * k - tilt
    d = np.array([math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch)])
    Bc = looking_at(d)
    rx = sway[0] + (sway[2] - sway[0]) * k
    ry = sway[1] + (sway[3] - sway[1]) * k
    Bc = Bc @ rot((1, 0, 0), rx) @ rot((0, 1, 0), ry)
    fov = CAM0[2] + (CAM1[2] - CAM0[2]) * k
    dof = [a + (b - a) * k for a, b in zip(CAM0[3], CAM1[3])]
    return pos, Bc, fov, dof


AIM_Y = 0.80            # the earbud's centre is kept above this share of the frame's height (mid.png has it at 0.81)


def aim(us, coms, sway):
    """The extra tilt down, per step, that keeps the earbud's centre above AIM_Y of the frame: the need per step,
    spread by a running max over +-6 frames and a Gaussian (sigma 5 frames) so the camera moves smoothly ahead of
    it, and faded to nothing at both ends (the keyframes' own framing)."""
    need = np.zeros(len(us))
    for j, (u, com) in enumerate(zip(us, coms)):
        pos, Bc, fov, _ = camera(u, sway)
        d = Bc.T @ (com - pos)
        now = math.atan2(d[1], -d[2])
        want = math.atan((1.0 - 2.0 * AIM_Y) * math.tan(math.radians(fov) / 2))
        need[j] = max(want - now, 0.0)
    r = 6 * SUB
    spread = np.array([need[max(j - r, 0):j + r + 1].max() for j in range(len(need))])
    sig = 5 * SUB
    ker = np.exp(-0.5 * (np.arange(-3 * sig, 3 * sig + 1) / sig) ** 2)
    ker /= ker.sum()
    sm = np.convolve(np.pad(spread, 3 * sig, mode="edge"), ker, mode="valid")
    fade = np.array([smooth(min(u / 0.15, 1.0)) * smooth(min((1.0 - u) / 0.15, 1.0)) for u in us])
    return sm * fade, need


def project(P, pos, Bc, fov):
    d = Bc.T @ (P - pos)
    th = math.tan(math.radians(fov) / 2)
    xn = d[0] / -d[2] / (th * W / H)
    yn = d[1] / -d[2] / th
    return (xn + 1) / 2 * W, (1 - yn) / 2 * H, -d[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sway", default="0,0,0,0")
    ap.add_argument("--plot", action="store_true")
    ap.add_argument("--warp", help="retime.json (output seconds -> clip seconds); with --sub, --shutter, --name")
    ap.add_argument("--sub", type=int, default=8, help="with --warp: render steps per output frame")
    ap.add_argument("--shutter", type=float, default=0.5, help="with --warp: share of a frame the saved steps span")
    ap.add_argument("--name", default="clipA_mb", help="with --warp: <name>_track.json, frames into <name>/")
    args = ap.parse_args()
    sway = [float(v) for v in args.sway.split(",")]
    if args.warp:
        return main_warped(args, sway)
    t, O, B, i_rest, info = tumble()
    slowmo = t[i_rest] / (T_REST - T0)
    bud = search.BUD
    n = (FRAMES - 1) * SUB + 1
    us, ids = [], []
    for j in range(n):
        tc = j / (FPS * SUB)
        ts = min(max((tc - T0) * slowmo, 0.0), t[-1])
        i = min(int(round(ts / (t[1] - t[0]))), len(t) - 1)
        ids.append(len(t) - 1 if j == n - 1 else i)
        us.append(j / (n - 1))
    coms = [O[i] + B[i] @ bud.com for i in ids]
    tilt, need = aim(us, coms, sway)
    samples, stats = [], []
    for j in range(n):
        i, u = ids[j], us[j]
        pos, Bc, fov, dof = camera(u, sway, tilt[j])
        samples.append({"cam": [*pos.tolist(), *Bc.T.reshape(-1).tolist()], "fov": fov, "dof": dof,
                        "bud": [*O[i].tolist(), *B[i].T.reshape(-1).tolist()]})
        if j % SUB == 0:
            P = bud.pod_verts @ B[i].T + O[i]
            pts = np.array([project(p, pos, Bc, fov) for p in P[::9]])
            com = project(coms[j], pos, Bc, fov)
            stats.append((j // SUB, com[0], com[1], pts[:, 0].max() - pts[:, 0].min(), pts[:, 1].max() - pts[:, 1].min(),
                          com[2], math.degrees(tilt[j])))
    out = {"fps": FPS, "sub": SUB, "frames": FRAMES, "t0": T0, "t_rest": T_REST, "slowmo": slowmo, "sway": sway,
           "params": Q, "info": {k: v for k, v in info.items() if k != "touch"}, "samples": samples}
    json.dump(out, open(os.path.join(HERE, "clipA_track.json"), "w"))
    print("sim rest %.3f s -> clip %.2f s (played at %.2fx); corrections %s" % (
        t[i_rest], T_REST, slowmo, {k: round(v, 4) for k, v in info.items() if k != "touch"}))
    xs = np.array([s[1] for s in stats])
    ys = np.array([s[2] for s in stats])
    print("earbud on screen (1920x1080): x %.0f..%.0f  y %.0f..%.0f; size %.0f..%.0f px; distance %.2f..%.2f m" % (
        xs.min(), xs.max(), ys.min(), ys.max(), min(s[3] for s in stats), max(s[3] for s in stats),
        min(s[5] for s in stats), max(s[5] for s in stats)))
    print("extra tilt down up to %.2f deg" % math.degrees(tilt.max()))
    for s in stats[::6]:
        print("  f%02d  x %4.0f y %4.0f  w %3.0f h %3.0f  %.2f m  tilt %.2f" % s)
    return out, stats


def main_warped(args, sway):
    """The slowed, motion-blurred track (see the module's docstring): --sub steps per output frame around it, at
    output times through the warp; the middle round(shutter * sub) of them are saved."""
    t, O, B, i_rest, info = tumble()
    slowmo = t[i_rest] / (T_REST - T0)
    bud = search.BUD
    t_clip = (FRAMES - 1) / FPS
    dt_sim = t[1] - t[0]

    def sim_index(tc):
        ts = min(max((tc - T0) * slowmo, 0.0), t[-1])
        return min(int(round(ts / dt_sim)), len(t) - 1)

    # aim()'s tilt on the uniform clip's own 72 Hz grid, read back at any clip time
    n0 = (FRAMES - 1) * SUB + 1
    tc0 = np.arange(n0) / (FPS * SUB)
    ids0 = [sim_index(tc) for tc in tc0]
    ids0[-1] = len(t) - 1
    tilt0, _ = aim([j / (n0 - 1) for j in range(n0)], [O[i] + B[i] @ bud.com for i in ids0], sway)
    warp = json.load(open(args.warp if os.path.isabs(args.warp) else os.path.join(HERE, args.warp)))
    kn = np.array(warp["knots"])
    n_out = int(warp["frames_out"])
    slope1 = (kn[-1, 1] - kn[-2, 1]) / (kn[-1, 0] - kn[-2, 0])

    def clip_time(to):
        if to <= kn[-1, 0]:
            return float(np.interp(to, kn[:, 0], kn[:, 1]))
        return float(kn[-1, 1] + slope1 * (to - kn[-1, 0]))

    sub = args.sub
    k_open = int(round(args.shutter * sub))
    m0 = (sub - k_open) // 2
    save = list(range(m0, m0 + k_open))
    samples, stats, tcs = [], [], []
    for k in range(n_out):
        for m in range(sub):
            to = (k + (m - (sub - 1) / 2) / sub) / FPS
            tc = max(clip_time(to), 0.0)
            i = len(t) - 1 if tc >= t_clip else sim_index(tc)
            u = tc / t_clip
            tl = float(np.interp(tc, tc0, tilt0))
            pos, Bc, fov, dof = camera(u, sway, tl, extend=True)
            samples.append({"cam": [*pos.tolist(), *Bc.T.reshape(-1).tolist()], "fov": fov, "dof": dof,
                            "bud": [*O[i].tolist(), *B[i].T.reshape(-1).tolist()]})
            tcs.append(tc)
            if m == save[len(save) // 2]:
                com = project(O[i] + B[i] @ bud.com, pos, Bc, fov)
                stats.append((k, com[0], com[1], com[2], math.degrees(tl), tc))
    out = {"fps": FPS, "sub": sub, "frames": n_out, "save": save, "out": args.name, "shutter": args.shutter,
           "warp": os.path.basename(args.warp), "t0": T0, "t_rest": T_REST, "slowmo": slowmo, "sway": sway,
           "params": Q, "info": {k: v for k, v in info.items() if k != "touch"}, "samples": samples}
    dst = os.path.join(HERE, args.name + "_track.json")
    json.dump(out, open(dst, "w"))
    print("%s: %d output frames x %d steps (%d samples), saving steps %s (shutter %.0f deg); clip time %.3f..%.3f s"
          % (dst, n_out, sub, len(samples), save, 360 * len(save) / sub, min(tcs), max(tcs)))
    print("frame centres: frame 0 at clip %.3f s, last (%d) at clip %.4f s (mid.png is %.4f)" % (
        stats[0][5], n_out - 1, clip_time((n_out - 1) / FPS), t_clip))
    for s in stats[::8]:
        print("  f%03d  x %4.0f y %4.0f  %.2f m  tilt %.2f  clip %.3f s" % s)
    return out, stats


if __name__ == "__main__":
    main()
