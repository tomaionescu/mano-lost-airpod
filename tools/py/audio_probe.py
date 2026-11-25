"""Print a quick analysis of audio files: duration, loudness, peak, spectrum balance and a loudness timeline.

python3.11 -I tools/py/audio_probe.py [--win 2] [--env] FILE...
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
import numpy as np  # noqa: E402
import audio_lib as A  # noqa: E402

SPARK = " .:-=+*#%@"


def main(argv):
    win = 2.0
    env = False
    files = []
    i = 0
    while i < len(argv):
        if argv[i] == "--win":
            win = float(argv[i + 1]); i += 2; continue
        if argv[i] == "--env":
            env = True; i += 1; continue
        files.append(argv[i]); i += 1
    for f in files:
        x = A.load(f, channels=2)
        m = A.to_mono(x)
        L = A.lufs(x)
        st = A.short_term(x, win=win, hop=win)
        lo, hi = (np.percentile(st, 5), np.percentile(st, 95)) if len(st) else (0, 0)
        line = "".join(SPARK[int(np.clip((v - (L - 12)) / 24 * (len(SPARK) - 1), 0, len(SPARK) - 1))] for v in st)
        side = A.rms_db(x[:, 0] - x[:, 1]) - A.rms_db(x[:, 0] + x[:, 1]) if x.ndim > 1 else -99
        print("%s\n  dur=%.2fs  I=%.1f LUFS  peak=%.1f dBFS  centroid=%d Hz  st5..95=%.1f..%.1f  S/M=%.1f dB" % (
            os.path.basename(f), A.dur(x), L, A.peak_db(x), A.centroid(m), lo, hi, side))
        print("  bands:", A.band_levels(m))
        print("  timeline(%gs/char, I-12..I+12): |%s|" % (win, line))
        if env:
            print(A.ascii_env(m, win=0.02, lo=-60, width=50))


if __name__ == "__main__":
    main(sys.argv[1:])
