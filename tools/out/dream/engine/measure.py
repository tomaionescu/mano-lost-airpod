"""MAD (mean absolute difference, 8-bit levels over RGB) of clip A's first and last frames against the round-2
keyframes, at the keyframes' 1792x1008 (frames downscaled with Lanczos), with the noise floor of this run's own
re-renders of the keyframes, and the sub-pixel shift between them (phase correlation), which register.py turns into
the handheld sway offsets.

usage: python3.11 measure.py [frames dir] [keys dir]
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
R2 = os.path.join(ROOT, "shots", "dream", "round2")


def load(path, size=(1792, 1008)):
    im = Image.open(path).convert("RGB")
    if im.size != size:
        im = im.resize(size, Image.LANCZOS)
    return np.asarray(im).astype(np.float64)


def mad(a, b):
    return float(np.abs(a - b).mean())


def shift(a, b):
    """(dx, dy) in pixels to move b onto a (phase correlation on grey, Hann window)."""
    ga = cv2.cvtColor(a.astype(np.float32), cv2.COLOR_RGB2GRAY)
    gb = cv2.cvtColor(b.astype(np.float32), cv2.COLOR_RGB2GRAY)
    win = cv2.createHanningWindow(ga.shape[::-1], cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(gb, ga, win)
    return dx, dy, resp


def aligned_mad(a, b, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    bb = cv2.warpAffine(b.astype(np.float32), M, (b.shape[1], b.shape[0]), flags=cv2.INTER_LANCZOS4,
                        borderMode=cv2.BORDER_REFLECT)
    m = 24
    return float(np.abs(a[m:-m, m:-m] - bb[m:-m, m:-m]).mean())


def report(name, a, b):
    dx, dy, resp = shift(a, b)
    print("%-34s MAD %.2f   shift %+.2f %+.2f px (resp %.2f)   MAD after shift %.2f" % (
        name, mad(a, b), dx, dy, resp, aligned_mad(a, b, dx, dy)))
    return dx, dy


if __name__ == "__main__":
    fr = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "clipA")
    keys = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "keys")
    s0, m0 = load(os.path.join(R2, "start.png")), load(os.path.join(R2, "mid.png"))
    names = sorted(f for f in os.listdir(fr) if f.endswith(".png"))
    first, last = load(os.path.join(fr, names[0])), load(os.path.join(fr, names[-1]))
    out = {}
    out["first"] = report("frame %s vs start.png" % names[0], s0, first)
    out["last"] = report("frame %s vs mid.png" % names[-1], m0, last)
    if os.path.isdir(keys):
        for k, ref in (("start.png", s0), ("mid.png", m0)):
            p = os.path.join(keys, k)
            if os.path.exists(p):
                report("this run's %s vs round2/%s" % (k, k), ref, load(p))
        if os.path.exists(os.path.join(keys, "start.png")):
            report("frame %s vs this run's start.png" % names[0], load(os.path.join(keys, "start.png")), first)
        if os.path.exists(os.path.join(keys, "mid.png")):
            report("frame %s vs this run's mid.png" % names[-1], load(os.path.join(keys, "mid.png")), last)
