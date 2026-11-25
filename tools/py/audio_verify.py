"""Verify every delivered file by decoding the OGG: format, duration, loudness (ffmpeg ebur128), peaks,
silence, onset position (one-shots/footsteps) and loop seams (ambience/music).

python3.11 -I tools/py/audio_verify.py            # prints a table, writes tools/audio_src/verify.json
"""
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
import numpy as np  # noqa: E402
import audio_lib as A  # noqa: E402

GROUPS = ["footsteps", "sfx", "amb", "music"]


def probe(path):
    err = subprocess.run([A.FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Audio: (\w+), (\d+) Hz, (\w+)", err)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else ("?", 0, "?")


def ebur128(path):
    err = subprocess.run([A.FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    s = err[err.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", s)
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s)
    lra = re.search(r"LRA:\s+(-?[\d.]+) LU", s)
    f = lambda m: float(m.group(1)) if m and m.group(1) != "-inf" else float("-inf")  # noqa: E731
    return f(i), f(tp), f(lra)


def main():
    rows = []
    problems = []
    for g in GROUPS:
        for path in sorted(glob.glob(os.path.join(A.OUT, g, "*.ogg"))):
            name = "%s/%s" % (g, os.path.basename(path))
            codec, sr, layout = probe(path)
            chans = 1 if layout == "mono" else 2
            x = A.load(path, channels=chans, sr=sr)
            d = A.dur(x, sr)
            I, TP, LRA = ebur128(path)
            pk = A.peak_db(x)
            r = {"file": name, "codec": codec, "sr": sr, "ch": layout, "dur": round(d, 3), "lufs": I, "tp": TP,
                 "peak": round(pk, 2), "lra": LRA, "size_kb": round(os.path.getsize(path) / 1024)}
            want_ch = "mono" if g in ("footsteps", "sfx") else "stereo"
            if codec != "vorbis" or sr not in (44100, 48000) or layout != want_ch:
                problems.append("%s: format %s %d %s" % (name, codec, sr, layout))
            if pk > -0.3:
                problems.append("%s: peak %.2f dBFS (clipping risk)" % (name, pk))
            if pk < -40:
                problems.append("%s: nearly silent (peak %.1f)" % (name, pk))
            if g in ("footsteps", "sfx"):
                m = np.abs(A.to_mono(x))
                first = np.nonzero(m > m.max() * 0.1)[0][0] / sr
                r["onset_ms"] = round(first * 1000, 1)
                if g == "footsteps" and (d >= 0.5 or first > 0.01):
                    problems.append("%s: footstep dur %.3f onset %.1f ms" % (name, d, first * 1000))
                if g == "sfx" and first > 0.06:
                    problems.append("%s: late onset %.0f ms" % (name, first * 1000))
            else:
                w = int(0.5 * sr)
                jump = A.rms_db(x[:w]) - A.rms_db(x[-w:])
                mm = A.to_mono(x)
                step = abs(mm[0] - mm[-1])
                p99 = float(np.percentile(np.abs(np.diff(mm)), 99))
                p999 = float(np.percentile(np.abs(np.diff(mm)), 99.9))
                # short-term loudness (3 s windows) across the seam vs. windows elsewhere around it
                ext = np.concatenate([x[-int(9 * sr):], x[:int(9 * sr)]])
                st = A.short_term(ext, sr, win=3.0, hop=0.5)
                centre = len(st) // 2 - 3  # window centred on the seam (9 s into ext)
                others = np.delete(st, range(centre - 1, centre + 2))
                st_dev = float(st[centre] - np.median(others))
                spread = float(np.percentile(np.abs(others - np.median(others)), 90))
                r.update({"seam_jump_db": round(jump, 2), "seam_step": round(float(step), 5), "p99_step": round(p99, 5),
                          "seam_st_dev": round(st_dev, 2), "st_spread": round(spread, 2)})
                natural_end = name == "music/ending.ogg"
                r["loop_kind"] = "restarts after natural ending" if natural_end else "seamless"
                if not natural_end:
                    if step > max(p999, 1e-4) * 1.5:
                        problems.append("%s: seam discontinuity %.4f (p99.9 step %.4f)" % (name, step, p999))
                    if g == "amb" and abs(jump) > 1.5 and abs(st_dev) > max(1.0, spread):
                        problems.append("%s: seam level jump %.1f dB" % (name, jump))
                    if abs(st_dev) > max(1.5, 1.5 * spread):
                        problems.append("%s: loudness bump at seam %.1f dB (spread %.1f)" % (name, st_dev, spread))
            rows.append(r)
    for r in rows:
        extra = ""
        if "onset_ms" in r:
            extra = "onset=%4.1fms" % r["onset_ms"]
        if "seam_jump_db" in r:
            extra = "seam: 0.5s-rms %+.1f dB, 3s-loudness %+.1f dB (spread %.1f), step %.4f (p99 %.4f)%s" % (
                r["seam_jump_db"], r["seam_st_dev"], r["st_spread"], r["seam_step"], r["p99_step"],
                "" if r["loop_kind"] == "seamless" else " [restarts after natural ending]")
        print("%-34s %s %5d %-6s %7.2fs  I=%6.1f LUFS  TP=%6.1f  peak=%6.1f  %4d KB  %s" % (
            r["file"], r["codec"], r["sr"], r["ch"], r["dur"], r["lufs"], r["tp"], r["peak"], r["size_kb"], extra))
    tot = sum(os.path.getsize(p) for g in GROUPS for p in glob.glob(os.path.join(A.OUT, g, "*.ogg")))
    print("\n%d files, %.1f MB" % (len(rows), tot / 1048576))
    print("problems:" if problems else "no problems found")
    for p in problems:
        print("  -", p)
    with open(os.path.join(A.SRC, "verify.json"), "w") as f:
        json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
