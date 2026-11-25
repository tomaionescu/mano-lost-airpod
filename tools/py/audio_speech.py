"""Speech-likeness timeline (syllabic 2.5-8 Hz envelope modulation in the 300-3400 Hz band) per window.
High values = a close, single talker (intelligible); low = steady noise or dense walla.

python3.11 -I tools/py/audio_speech.py [--win 4] FILE...
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
import numpy as np  # noqa: E402
from scipy import signal  # noqa: E402
import audio_lib as A  # noqa: E402


def speechiness(x, sr=A.SR, win=4.0):
    m = A.bp(A.to_mono(x), 300, 3400, sr, 4)
    env = np.abs(signal.hilbert(m)) if len(m) < sr * 30 else np.abs(m)
    env = signal.resample_poly(A.lp(env, 40, sr, 2), 1, sr // 100)  # 100 Hz envelope
    w = int(win * 100)
    out = []
    for i in range(0, len(env) - w + 1, w):
        e = env[i:i + w]
        e = e - e.mean()
        f, p = signal.welch(e, 100, nperseg=min(256, len(e)))
        band = p[(f >= 2.5) & (f <= 8)].sum()
        tot = p[(f > 0.3) & (f <= 20)].sum() + 1e-18
        depth = np.sqrt(np.mean(e ** 2)) / (np.mean(env[i:i + w]) + 1e-12)
        out.append(depth * band / tot)
    return np.array(out)


def main(argv):
    win = 4.0
    if argv and argv[0] == "--win":
        win = float(argv[1]); argv = argv[2:]
    for f in argv:
        x = A.load(f, channels=1)
        s = speechiness(x, win=win)
        line = "".join(" .:-=+*#%@"[int(np.clip(v / 0.35 * 9.99, 0, 9))] for v in s)
        print("%-28s mean=%.3f max=%.3f |%s|" % (os.path.basename(f)[:28], s.mean(), s.max(), line))


if __name__ == "__main__":
    main(sys.argv[1:])
