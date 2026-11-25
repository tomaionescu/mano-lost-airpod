"""Clip A's time warp: output time -> clip time, so the camera's picture speed eases in gently and never runs over a cap.

    python3.11 tools/out/dream/engine/retime.py [--cap 10.5] [--ramp 1.0] [--src clipA.mp4] [--out retime.json]

The uniform render (clipA.mp4, 24 fps, frame i = clip time i / 24) is measured: the median dense-flow length per frame
(DIS at 960x540, px at 1920), the same measure join_dream.py reports. Its picture speed rises from 1 to 15 px/frame in
0.6 s around 1.0 s (the glide's ease-in plus aim()'s extra tilt as the earbud drops off the landing: a lunge), cruises
at 11-13 to 2.8 s and sags to 7-8 before mid.png. The warp plays the clip slower wherever it would run faster than a
target speed, never faster than real time:
    target(t_out) = cap * smoothstep(t_out / ramp)      (at least 0.3 px/frame)
    d t_clip / d t_out = min(1, target / native speed at t_clip)
integrated in steps of 1/192 s, the rate smoothed (Gaussian, sigma 2 frames) and the output axis stretched (under 1 %)
so that mid.png (clip time 95 / 24) lands exactly on a whole output frame. Writes the knots (output seconds, clip
seconds) that tumble.py --warp reads. Deterministic for a given clipA.mp4.
"""
import argparse
import json
import os
import subprocess

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 24
FRAMES = 96


def speeds(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf",
                        "scale=960:540:flags=area:in_color_matrix=bt709:in_range=tv:out_range=pc,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    g = np.frombuffer(r.stdout, np.uint8).reshape(-1, 540, 960)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    return np.array([2 * float(np.median(np.hypot(*dis.calc(a, b, None).transpose(2, 0, 1))))
                     for a, b in zip(g[:-1], g[1:])])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "clipA.mp4"))
    ap.add_argument("--cap", type=float, default=10.5, help="px per output frame at 1920")
    ap.add_argument("--ramp", type=float, default=1.0, help="seconds the target speed eases in over")
    ap.add_argument("--out", default=os.path.join(HERE, "retime.json"))
    a = ap.parse_args()
    v = speeds(a.src)
    assert len(v) == FRAMES - 1, len(v)
    tcs = (np.arange(len(v)) + 0.5) / FPS
    t_end = (FRAMES - 1) / FPS
    dt = 1.0 / (FPS * 8)
    to, tc, rates = 0.0, 0.0, []
    while tc < t_end:
        x = min(to / a.ramp, 1.0) if a.ramp > 0 else 1.0
        target = max(a.cap * x * x * (3 - 2 * x), 0.3)
        r = min(1.0, target / max(float(np.interp(tc, tcs, v)), 1e-3))
        rates.append(r)
        tc += r * dt
        to += dt
    rs = gaussian_filter1d(np.array(rates), 2 * 8, mode="nearest")
    tcl = np.concatenate([[0.0], np.cumsum(rs) * dt])
    tol = np.arange(len(tcl)) * dt
    T = float(np.interp(t_end, tcl, tol))            # output time at mid.png
    n_out = int(round(T * FPS)) + 1
    tol = tol * ((n_out - 1) / FPS) / T
    keep = tcl <= t_end + 0.05
    knots = [[round(float(x), 6), round(float(y), 6)] for x, y in zip(tol[keep], tcl[keep])]
    # what it does: the output's picture speed, predicted from the native one
    fo = np.arange(n_out) / FPS
    tcf = np.interp(fo, tol, tcl)
    vout = np.interp((tcf[:-1] + tcf[1:]) / 2, tcs, v) * np.diff(tcf) * FPS
    res = dict(cap=a.cap, ramp=a.ramp, src=os.path.relpath(a.src, HERE), frames_out=n_out,
               seconds_out=round((n_out - 1) / FPS, 4), added_s=round((n_out - FRAMES) / FPS, 4),
               min_rate=round(float(rs.min()), 3), native_speed=[round(float(x), 2) for x in v],
               predicted_speed=[round(float(x), 2) for x in vout], knots=knots)
    json.dump(res, open(a.out, "w"))
    print("warp: %d output frames for clip A's %d (+%.2f s), slowest rate %.2f; picture speed native max %.1f -> %.1f"
          % (n_out, FRAMES, res["added_s"], res["min_rate"], v.max(), vout.max()))
    print("  predicted speed every 4 frames:", " ".join("%.1f" % x for x in vout[::4]))


if __name__ == "__main__":
    main()
