"""Clip A's finish: match the levels of its ends to the keyframes, encode, check.

    python3.11 tools/out/dream/engine/finish.py

1. Grade. The engine's frames (clipA/) start on start.png's levels, but end about 3.4 levels brighter than mid.png:
   mid.png was shot 53 frames after a cut from the start view, before SDFGI and the fog's GI had settled there (a
   re-render with the same frame counts, --fixed-fps 33, matches it with no bias; any longer hold, or the clip's
   gradual approach, comes out as bright as the clip's last frame). A per-channel affine grade (gain, offset) is fit
   on each end frame against its keyframe (blurred quarter-size images, so texture noise and dust don't steer it)
   and eased in along the clip (smoothstep), so frame 0 stays as rendered and frame 95 takes mid.png's levels.
   Written to clipA_graded/.
2. Encode clipA.mp4 (graded) and clipA_raw.mp4 (as rendered): h264 High, CRF 12, yuv420p, 24 fps, the RGB -> YUV
   matrix BT.709 (swscale's default is 601) and tagged BT.709 (primaries, transfer, matrix, limited range; set on
   the frames with setparams, since ffmpeg 9 otherwise passes the PNGs' own sRGB transfer, or nothing, through).
3. Check: decode each mp4 back (BT.709) and compare with its PNGs; MAD of the first and last frames against
   start.png and mid.png at 1792x1008, from the PNGs and from the decoded mp4.

    python3.11 tools/out/dream/engine/finish.py --src clipA_mb --name clipA_mb

does the same for another render (autotest track=...): when its folder holds several steps per frame (fNNN_m.png,
tumble.py --warp --sub), they are first averaged in linear light (sRGB decoded, averaged, encoded again) into
<src>_avg/fNNN.png: a 180-degree shutter's motion blur. The frame count is the folder's.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from measure import load, mad, shift, aligned_mad, R2   # noqa: E402

RAW = os.path.join(HERE, "clipA")
GRADED = os.path.join(HERE, "clipA_graded")
N = 96


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def fit(frame, ref):
    a = cv2.GaussianBlur(cv2.resize(ref.astype(np.float32), (448, 252), interpolation=cv2.INTER_AREA), (0, 0), 1.5)
    f = cv2.GaussianBlur(cv2.resize(frame.astype(np.float32), (448, 252), interpolation=cv2.INTER_AREA), (0, 0), 1.5)
    g = []
    for c in range(3):
        X = np.stack([f[..., c].ravel(), np.ones(f[..., c].size)], 1)
        g.append(np.linalg.lstsq(X, a[..., c].ravel(), rcond=None)[0].tolist())
    return np.array(g)


def average(src, dst):
    """fNNN_m.png steps -> fNNN.png, averaged in linear light. Returns the frame count."""
    groups = {}
    for p in sorted(glob.glob(os.path.join(src, "f*_*.png"))):
        m = re.match(r"f(\d+)_(\d+)\.png$", os.path.basename(p))
        groups.setdefault(int(m.group(1)), []).append(p)
    os.makedirs(dst, exist_ok=True)
    lut = np.where(np.arange(256) / 255 <= 0.04045, np.arange(256) / 255 / 12.92,
                   ((np.arange(256) / 255 + 0.055) / 1.055) ** 2.4).astype(np.float64)
    for k in sorted(groups):
        acc = None
        for p in groups[k]:
            lin = lut[np.asarray(Image.open(p).convert("RGB"))]
            acc = lin if acc is None else acc + lin
        lin = acc / len(groups[k])
        srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(np.maximum(lin, 0), 1 / 2.4) - 0.055)
        Image.fromarray(np.clip(np.round(srgb * 255), 0, 255).astype(np.uint8)).save(os.path.join(dst, "f%03d.png" % k))
    assert sorted(groups) == list(range(len(groups))), "missing frames in %s" % src
    print("averaged %d frames of %s steps each into %s" % (len(groups), sorted({len(v) for v in groups.values()}), dst))
    return len(groups)


def grade():
    os.makedirs(GRADED, exist_ok=True)
    g0 = fit(load(os.path.join(RAW, "f000.png")), load(os.path.join(R2, "start.png")))
    g1 = fit(load(os.path.join(RAW, "f%03d.png" % (N - 1))), load(os.path.join(R2, "mid.png")))
    for i in range(N):
        w = smooth(i / (N - 1))
        g = g0 * (1 - w) + g1 * w
        im = np.asarray(Image.open(os.path.join(RAW, "f%03d.png" % i)).convert("RGB")).astype(np.float64)
        out = im * g[:, 0] + g[:, 1]
        Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8)).save(os.path.join(GRADED, "f%03d.png" % i))
    return g0, g1


def encode(src, dst):
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", "24", "-i", os.path.join(src, "f%03d.png"),
           "-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,"
           "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709",
           "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
           "-movflags", "+faststart", dst]
    subprocess.run(cmd, check=True)


def decode(mp4, idx):
    """Frames idx of the mp4 as RGB arrays, converted with the BT.709 matrix."""
    out = {}
    cmd = ["ffmpeg", "-v", "error", "-i", mp4, "-vf", "scale=in_color_matrix=bt709:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb24",
           "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 1080, 1920, 3)
    for i in idx:
        out[i] = fr[i].astype(np.float64)
    return out, len(fr)


def to1792(a):
    return np.asarray(Image.fromarray(a.astype(np.uint8)).resize((1792, 1008), Image.LANCZOS)).astype(np.float64)


def main():
    global RAW, GRADED, N
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="clipA", help="the render's frames folder (in this folder)")
    ap.add_argument("--name", default="clipA", help="writes <name>.mp4, <name>_raw.mp4, <name>_check.json, "
                                                    "<name>_graded/")
    a = ap.parse_args()
    RAW = os.path.join(HERE, a.src)
    if glob.glob(os.path.join(RAW, "f000_*.png")):
        N = average(RAW, RAW + "_avg")
        RAW = RAW + "_avg"
    else:
        N = len(glob.glob(os.path.join(RAW, "f[0-9][0-9][0-9].png")))
    GRADED = os.path.join(HERE, a.name + "_graded")
    g0, g1 = grade()
    print("grade: frame 0 gain/offset per channel %s, frame %d %s" % (np.round(g0, 3).tolist(), N - 1,
                                                                       np.round(g1, 3).tolist()))
    s0, m0 = load(os.path.join(R2, "start.png")), load(os.path.join(R2, "mid.png"))
    res = {"grade_first": g0.tolist(), "grade_last": g1.tolist()}
    for name, d in (("raw", RAW), ("graded", GRADED)):
        f0, f1 = load(os.path.join(d, "f000.png")), load(os.path.join(d, "f%03d.png" % (N - 1)))
        dx0, dy0, _ = shift(s0, f0)
        dx1, dy1, _ = shift(m0, f1)
        res[name] = {"first_vs_start": mad(s0, f0), "last_vs_mid": mad(m0, f1), "first_shift_px": [dx0, dy0],
                     "last_shift_px": [dx1, dy1]}
        print("%-6s PNGs: frame 0 vs start.png MAD %.2f (shift %+.2f %+.2f px), frame %d vs mid.png MAD %.2f "
              "(shift %+.2f %+.2f px)" % (name, mad(s0, f0), dx0, dy0, N - 1, mad(m0, f1), dx1, dy1))
    for name, d, mp4 in (("graded", GRADED, a.name + ".mp4"), ("raw", RAW, a.name + "_raw.mp4")):
        path = os.path.join(HERE, mp4)
        encode(d, path)
        fr, n = decode(path, [0, N // 2, N - 1])
        png = {i: np.asarray(Image.open(os.path.join(d, "f%03d.png" % i)).convert("RGB")).astype(np.float64)
               for i in fr}
        rt = {i: mad(png[i], fr[i]) for i in fr}
        bias = {i: (fr[i] - png[i]).mean((0, 1)).round(2).tolist() for i in fr}
        a0, a1 = to1792(fr[0]), to1792(fr[N - 1])
        res[mp4] = {"frames": n, "roundtrip_mad": rt, "roundtrip_bias": bias, "first_vs_start": mad(s0, a0),
                    "last_vs_mid": mad(m0, a1)}
        print("%s: %d frames; decoded vs PNG MAD %s, bias %s; frame 0 vs start.png %.2f, frame %d vs mid.png %.2f" % (
            mp4, n, {k: round(v, 2) for k, v in rt.items()}, bias, mad(s0, a0), N - 1, mad(m0, a1)))
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=codec_name,profile,width,height,pix_fmt,r_frame_rate,nb_frames,color_space,"
                                "color_primaries,color_transfer,color_range", "-of", "json", path],
                               capture_output=True, text=True, check=True).stdout
        res[mp4]["ffprobe"] = json.loads(probe)["streams"][0]
        print("   ", res[mp4]["ffprobe"])
    # this run's own re-renders of the keyframes: the noise floor
    for k, ref in (("start.png", s0), ("mid.png", m0)):
        for kd in ("keys", "keys33"):
            p = os.path.join(HERE, kd, k)
            if os.path.exists(p):
                b = load(p)
                dx, dy, _ = shift(ref, b)
                res["%s_%s" % (kd, k)] = {"mad": mad(ref, b), "aligned_mad": aligned_mad(ref, b, dx, dy)}
                print("noise floor: %s/%s vs round2/%s MAD %.2f, %.2f once aligned (handheld sway %+.1f %+.1f px)" % (
                    kd, k, k, mad(ref, b), aligned_mad(ref, b, dx, dy), dx, dy))
    json.dump(res, open(os.path.join(HERE, a.name + "_check.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
