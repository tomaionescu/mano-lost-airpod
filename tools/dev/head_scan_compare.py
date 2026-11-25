"""Compare fitted bodies saved by tools/dev/head_scan_build.py (state=1): how far the head's vertices moved between
two builds, and the face's widths (between left and right face landmarks, in X) and height in each.

usage: python3.11 tools/dev/head_scan_compare.py <reference.npz> <other.npz> [...]"""
import sys, os
import numpy as np

PAIRS = {"temples 127-356": (127, 356), "cheeks 234-454": (234, 454), "cheekbones 93-323": (93, 323),
         "jaw 58-288": (58, 288), "jaw angle 172-397": (172, 397), "lower jaw 136-365": (136, 365),
         "chin sides 150-379": (150, 379), "eyes 33-263": (33, 263), "nose wings 98-327": (98, 327),
         "mouth 61-291": (61, 291)}


def load(p):
    d = np.load(p)
    return d, dict(zip(d["anchor_ids"].tolist(), d["anchors"]))


def widths(A):
    w = {k: abs(A[a][0] - A[b][0]) * 1000 for k, (a, b) in PAIRS.items() if a in A and b in A}
    if 10 in A and 152 in A:
        w["height 10-152"] = abs(A[10][2] - A[152][2]) * 1000
    return w


ref, Aref = load(sys.argv[1])
wref = widths(Aref)
sel = ref["in_body"] & ref["head"]
print(f"reference {os.path.basename(sys.argv[1])}: {int(sel.sum())} head vertices")
for p in sys.argv[2:]:
    d, A = load(p)
    dist = np.linalg.norm(d["V"][sel] - ref["V"][sel], axis=1) * 1000
    face = sel & (ref["V"][:, 1] < np.mean([Aref[i][1] for i in (234, 454)]))
    df = np.linalg.norm(d["V"][face] - ref["V"][face], axis=1) * 1000
    w = widths(A)
    face_w = [w[k] / wref[k] - 1 for k in w if k in wref and not k.startswith("height")]
    print(f"\n{os.path.basename(p)}: head vertices moved mean {dist.mean():.2f} mm, 95% {np.percentile(dist, 95):.2f} mm, "
          f"max {dist.max():.2f} mm; face (front of the ears) mean {df.mean():.2f} mm")
    print(f"  face widths vs reference: mean {np.mean(face_w) * 100:+.2f}%, "
          f"lower face (jaw, chin, mouth) {np.mean([w[k] / wref[k] - 1 for k in w if k.split()[0] in ('jaw', 'lower', 'chin', 'mouth')]) * 100:+.2f}%")
    for k in w:
        if k in wref:
            print(f"    {k:22s} {wref[k]:7.1f} -> {w[k]:7.1f} mm  ({(w[k] / wref[k] - 1) * 100:+.2f}%)")
