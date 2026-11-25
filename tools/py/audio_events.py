"""List loud events (regions above floor+X dB) in audio files, for picking one-shots.

python3.11 -I tools/py/audio_events.py [--rise 15] [--gap 0.15] FILE...
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
import numpy as np  # noqa: E402
import audio_lib as A  # noqa: E402


def events(x, sr=A.SR, rise=15.0, gap=0.15, win=0.01):
    e = A.env_db(x, sr, win)
    floor = np.percentile(e, 20)
    on = e > floor + rise
    out = []
    i = 0
    n = len(e)
    while i < n:
        if on[i]:
            j = i
            last = i
            while j < n and (on[j] or (j - last) * win < gap):
                if on[j]:
                    last = j
                j += 1
            seg = e[i:last + 1]
            out.append((i * win, (last + 1) * win, float(seg.max()), int(np.argmax(seg)) * win + i * win))
            i = last + 1
        else:
            i += 1
    return out, float(floor)


def main(argv):
    rise, gap = 15.0, 0.15
    files = []
    i = 0
    while i < len(argv):
        if argv[i] == "--rise":
            rise = float(argv[i + 1]); i += 2; continue
        if argv[i] == "--gap":
            gap = float(argv[i + 1]); i += 2; continue
        files.append(argv[i]); i += 1
    for f in files:
        x = A.to_mono(A.load(f, channels=2))
        ev, fl = events(x, rise=rise, gap=gap)
        print("%s  dur=%.2f floor=%.1f peak=%.1f cent=%d  events=%d" % (os.path.basename(f), A.dur(x), fl, A.peak_db(x), A.centroid(x), len(ev)))
        print("   " + "  ".join("%.2f-%.2f(%.0f)" % (a, b, m) for a, b, m, _ in ev[:40]))


if __name__ == "__main__":
    main(sys.argv[1:])
