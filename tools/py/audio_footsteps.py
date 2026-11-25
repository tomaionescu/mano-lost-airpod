"""Slice single sneaker steps out of walking recordings -> assets/audio/footsteps/<surface>_<n>.ogg

python3.11 -I tools/py/audio_footsteps.py analyze <surface>   # list detected steps + features
python3.11 -I tools/py/audio_footsteps.py build [surface...]  # write the OGGs (and print a report)
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
import numpy as np  # noqa: E402
import audio_lib as A  # noqa: E402

FS = os.path.join(A.SRC, "freesound")
OUTDIR = os.path.join(A.OUT, "footsteps")


def fs_file(sid):
    return glob.glob(os.path.join(FS, str(sid), "*-hq.mp3"))[0]


# surface -> list of (source id, hp cutoff, optional time window (t0, t1), extra gain dB, optional pick list of onset times)
SURFACES = {
    # src entries: (freesound id, high-pass Hz, time window or None, explicit onset picks or None)
    "concrete": {"src": [(713428, 70, None, None)], "count": 6, "level": 0.0},
    "tile": {"src": [(170506, 60, None, None)], "count": 6, "level": 0.0},
    "carpet": {"src": [(256209, 50, None, None)], "count": 6, "level": -4.0, "margin": 13.0},
    "wood": {"src": [(405114, 60, None, [0.98, 2.34, 3.47, 4.53]), (863017, 60, None, [8.78, 13.87])], "count": 6, "level": -0.5},
    "rubber": {"src": [(546826, 60, (0.0, 17.0), None)], "count": 6, "level": 0.0},
    "grass": {"src": [(476119, 50, None, None)], "count": 4, "level": -2.5},
}

MAXLEN = 0.45      # seconds per step (brief: < 0.5 s)
PRE = 0.002        # lead-in before the transient
RMS_REF = -27.0    # dBFS RMS of the first 120 ms for a level-0 surface
PEAK_CAP = -6.0    # no step peaks above this


def detect(x, sr=A.SR, rise_db=14.0, min_gap=0.22):
    env = np.abs(x)
    k = max(1, int(0.002 * sr))
    env = np.convolve(env, np.ones(k) / k, mode="same")
    floor = np.percentile(env, 25)
    e_db = A.db(env)
    thr = A.db(floor) + rise_db
    above = e_db > thr
    idx = np.nonzero(above[1:] & ~above[:-1])[0] + 1
    out = []
    last = -1e9
    for j in idx:
        if (j - last) / sr < min_gap:
            continue
        # refine: first sample within this rise that reaches 10% of the local 30 ms peak
        win = np.abs(x[j:j + int(0.03 * sr)])
        if len(win) == 0:
            continue
        pk = win.max()
        k2 = np.nonzero(np.abs(x[max(0, j - int(0.01 * sr)):j + int(0.03 * sr)]) >= 0.1 * pk)[0]
        s = max(0, j - int(0.01 * sr)) + (k2[0] if len(k2) else 0)
        out.append(s)
        last = j
    return out, float(A.db(floor))


def cut_steps(x, sr, onsets, floor_db):
    steps = []
    for i, s in enumerate(onsets):
        nxt = onsets[i + 1] if i + 1 < len(onsets) else len(x)
        a = max(0, s - int(PRE * sr))
        b = min(len(x), s + int(MAXLEN * sr), nxt - int(0.015 * sr))
        seg = np.array(x[a:b])
        if len(seg) < int(0.06 * sr):
            continue
        # start right at the main transient: first sample above 20 % of the step's peak, minus PRE
        k = np.nonzero(np.abs(seg[: int(0.15 * sr)]) >= 0.2 * np.abs(seg).max())[0]
        if len(k) and k[0] > int(PRE * sr):
            cut = k[0] - int(PRE * sr)
            seg = seg[cut:]
            s = a + cut + int(PRE * sr)
        e = A.env_db(seg, sr, 0.005)
        pk = e.max()
        # end where the envelope has decayed 38 dB under the peak (or to the floor + 4 dB)
        lim = max(pk - 38.0, floor_db + 4.0)
        ipk = int(np.argmax(e))
        tail = np.nonzero(e[ipk:] > lim)[0]
        end = (ipk + (tail[-1] if len(tail) else 0) + 2) * int(0.005 * sr)
        end = int(min(len(seg), max(end, int(0.08 * sr))))
        seg = seg[:end]
        seg = A.fade(seg, sr, fin=0.0015, fout=min(0.06, end / sr * 0.35))
        main = seg[: int(0.12 * sr)]
        rest = seg[int(0.15 * sr):]
        steps.append({
            "t": s / sr, "dur": len(seg) / sr, "seg": seg,
            "peak": A.peak_db(seg), "rms": A.rms_db(main),
            "tail": (A.rms_db(rest) - A.rms_db(main)) if len(rest) > int(0.02 * sr) else -60.0,
            "cent": A.centroid(seg) if len(seg) > 256 else 0,
            "crest": A.peak_db(seg) - A.rms_db(main),
        })
    return steps


def gather(surface):
    cfg = SURFACES[surface]
    allsteps = []
    for sid, hpf, win, picks in cfg["src"]:
        x = A.load(fs_file(sid), channels=1)
        off = 0.0
        if win:
            x = x[int(win[0] * A.SR):int(win[1] * A.SR)]
            off = win[0]
        raw_peak = np.abs(x).copy()
        x = A.hp(x, hpf, A.SR, 4)
        ons, fl = detect(x)
        st = cut_steps(x, A.SR, ons, fl)
        keep = []
        for s in st:
            s["src"] = sid
            i0 = int(s["t"] * A.SR)
            s["src_peak"] = float(A.db(raw_peak[i0:i0 + int(0.1 * A.SR)].max()))
            s["t"] += off
            # real steps only: well above the noise floor, not clipped in the source
            if s["rms"] < max(fl + cfg.get("margin", 20.0), -75.0) or s["src_peak"] > -1.5:
                continue
            s["forced"] = False
            keep.append(s)
        if picks:
            chosen = []
            for pt in picks:
                best = min(keep, key=lambda s: abs(s["t"] - pt))
                if abs(best["t"] - pt) < 0.1:
                    best["forced"] = True
                    chosen.append(best)
            keep = chosen
        allsteps += keep
    return allsteps


def choose(steps, n):
    """keep real steps: strong (top of the level distribution), no second hit in the tail, typical spectrum"""
    if not steps:
        return []
    forced = [s for s in steps if s.get("forced")]
    if forced:
        return sorted(forced, key=lambda s: (s["src"], s["t"]))[:n]
    rms = np.array([s["rms"] for s in steps])
    cent = np.array([s["cent"] for s in steps])
    hi = np.percentile(rms, 90)
    cand = [s for s in steps if s["rms"] > hi - 14 and s["tail"] < -8 and s["dur"] >= 0.1]
    if len(cand) < n:
        cand = sorted(steps, key=lambda s: -s["rms"])[: max(n * 2, n)]
    med_c = np.median([s["cent"] for s in cand])
    med_r = np.median([s["rms"] for s in cand])
    for s in cand:
        s["score"] = abs(np.log2(max(s["cent"], 50) / med_c)) * 2.0 + abs(s["rms"] - med_r) / 6.0 + max(0, s["tail"] + 20) / 10.0
    cand.sort(key=lambda s: s["score"])
    picked = []
    for s in cand:
        if all(abs(s["t"] - p["t"]) > 0.3 or s["src"] != p["src"] for p in picked):
            picked.append(s)
        if len(picked) == n:
            break
    picked.sort(key=lambda s: (s["src"], s["t"]))
    return picked


def build(surface, write=True):
    cfg = SURFACES[surface]
    steps = choose(gather(surface), cfg["count"])
    target = RMS_REF + cfg["level"]
    outs = []
    for s in steps:
        s["g"] = target - s["rms"]
    # cap: the loudest resulting peak must stay under PEAK_CAP (+ level offset)
    worst = max(s["peak"] + s["g"] for s in steps)
    trim = min(0.0, PEAK_CAP + min(0.0, cfg["level"]) - worst)
    report = []
    for i, s in enumerate(steps, 1):
        y = s["seg"] * A.undb(s["g"] + trim)
        path = os.path.join(OUTDIR, "%s_%d.ogg" % (surface, i))
        if write:
            A.save_ogg(path, y, A.SR, q=5)
        report.append({"file": "footsteps/%s_%d.ogg" % (surface, i), "src": s["src"], "t": round(s["t"], 3),
                       "dur": round(len(y) / A.SR, 3), "peak": round(A.peak_db(y), 1), "rms120": round(A.rms_db(y[: int(0.12 * A.SR)]), 1),
                       "cent": int(s["cent"])})
        outs.append(path)
    return report


def main(argv):
    if not argv:
        print(__doc__)
        return
    if argv[0] == "analyze":
        for surface in argv[1:]:
            st = gather(surface)
            print("== %s: %d steps" % (surface, len(st)))
            for s in st:
                print("  src=%d t=%6.2f dur=%.3f peak=%6.1f rms=%6.1f tail=%6.1f cent=%5d crest=%4.1f" % (
                    s["src"], s["t"], s["dur"], s["peak"], s["rms"], s["tail"], s["cent"], s["crest"]))
            pk = choose(st, SURFACES[surface]["count"])
            print("  picked:", [(p["src"], round(p["t"], 2)) for p in pk])
    elif argv[0] == "build":
        surfaces = argv[1:] or list(SURFACES)
        allrep = {}
        man = os.path.join(A.SRC, "footsteps_report.json")
        if os.path.exists(man):
            allrep = json.load(open(man))
        for surface in surfaces:
            rep = build(surface)
            allrep[surface] = rep
            for r in rep:
                print(r)
        with open(man, "w") as f:
            json.dump(allrep, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
