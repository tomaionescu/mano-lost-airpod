"""Music: find seamless loop points (feature self-similarity at bar multiples + sample-accurate
cross-correlation refinement), cut, crossfade the seam, normalise to -18 LUFS.

python3.11 -I tools/py/audio_music.py analyze <stem>
python3.11 -I tools/py/audio_music.py build [stem ...]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
import numpy as np  # noqa: E402
from scipy import signal  # noqa: E402
import audio_lib as A  # noqa: E402

SR = A.SR
INC = os.path.join(A.SRC, "incompetech")
OUTDIR = os.path.join(A.OUT, "music")
MANIFEST = os.path.join(A.SRC, "music_manifest.json")
TARGET = -18.0
HOP = 1024

# stem -> source + loop search constraints (seconds). bpm from incompetech pieces.json; beats per bar
TRACKS = {
    "title": {"file": "Morning/Morning.mp3", "title": "Morning", "bpm": 60, "bar": 3, "len": (80, 140), "start": (0, 30), "free": True},
    "explore": {"file": "Almost_Bliss/Almost_Bliss.mp3", "title": "Almost Bliss", "bpm": 90, "bar": 4, "len": (150, 240), "start": (0, 60)},
    "explore_dusk": {"file": "Study_And_Relax/Study_And_Relax.mp3", "title": "Study And Relax", "bpm": 72, "bar": 4, "len": (140, 215), "start": (0, 50), "xfade": 0.6},
    "tension": {"file": "Sneaky_Snitch/Sneaky_Snitch.mp3", "title": "Sneaky Snitch", "bpm": 87, "bar": 4, "len": (80, 130), "start": (0, 30)},
    "under_party": {"file": "Raving_Energy/Raving_Energy.mp3", "title": "Raving Energy", "bpm": 122, "bar": 4, "len": (150, 240), "start": (0, 60)},
    "ending": {"file": "Evening/Evening.mp3", "title": "Evening", "bpm": 101, "bar": 4, "len": None, "start": None},
}


def load_track(stem):
    return A.load(os.path.join(INC, TRACKS[stem]["file"]), channels=2)


# ------------------------------------------------------------------ features
def mel_fb(n_fft, n_mels=24, fmin=40, fmax=12000):
    def hz2mel(f):
        return 2595 * np.log10(1 + f / 700.0)

    def mel2hz(m):
        return 700 * (10 ** (m / 2595.0) - 1)
    freqs = np.fft.rfftfreq(n_fft, 1 / SR)
    m = np.linspace(hz2mel(fmin), hz2mel(fmax), n_mels + 2)
    hz = mel2hz(m)
    fb = np.zeros((n_mels, len(freqs)))
    for i in range(n_mels):
        lo, c, hi = hz[i], hz[i + 1], hz[i + 2]
        fb[i] = np.clip(np.minimum((freqs - lo) / (c - lo), (hi - freqs) / (hi - c)), 0, None)
    return fb


def features(x):
    m = A.to_mono(x)
    n_fft = 4096
    f, t, Z = signal.stft(m, SR, nperseg=n_fft, noverlap=n_fft - HOP, boundary=None, padded=False)
    S = np.abs(Z)
    with np.errstate(all="ignore"):  # Accelerate BLAS raises spurious FP flags
        mel = np.log(mel_fb(n_fft) @ (S ** 2) + 1e-10)
    # chroma 100..4000 Hz
    fr = f.copy()
    sel = (fr > 100) & (fr < 4000)
    pc = (np.round(12 * np.log2(fr[sel] / 261.6256)) % 12).astype(int)
    C = np.zeros((12, S.shape[1]))
    for k in range(12):
        C[k] = (S[sel][pc == k] ** 2).sum(axis=0)
    C = np.log(C + 1e-10)
    C = C - C.mean(axis=0, keepdims=True)
    flux = np.maximum(np.diff(np.log(S + 1e-6), axis=1), 0).sum(axis=0)
    flux = np.concatenate([[0], flux])
    lowflux = np.maximum(np.diff(np.log(S[f < 150] + 1e-6), axis=1), 0).sum(axis=0)
    lowflux = np.concatenate([[0], lowflux])
    F = np.vstack([mel, 1.5 * C, 2.0 * flux[None, :] / (flux.std() + 1e-9)])
    F = (F - F.mean(axis=1, keepdims=True)) / (F.std(axis=1, keepdims=True) + 1e-9)
    return F, flux, lowflux, t


def frame_rate():
    return SR / HOP


def refine_period(flux, bpm, span=0.03):
    """precise beat period around the catalogue bpm: maximise peakiness of the onset envelope folded at P"""
    fr = frame_rate()
    env = flux - np.convolve(flux, np.ones(43) / 43, mode="same")
    env = np.maximum(env, 0)
    tt = np.arange(len(env)) / fr
    best = None
    for P in np.linspace(60 / bpm * (1 - span), 60 / bpm * (1 + span), 1201):
        ph = (tt % P) / P
        h, _ = np.histogram(ph, bins=48, weights=env)
        score = h.max() / (h.mean() + 1e-9)
        if best is None or score > best[0]:
            best = (score, P, (np.argmax(h) + 0.5) / 48 * P)
    return best[1], best[2], best[0]


def similarity_search(F, Lr, start_r, bar_s):
    fr = frame_rate()
    Fn = F / (np.linalg.norm(F, axis=0, keepdims=True) + 1e-9)
    W = int(6.0 * fr)
    best = None
    k_lo = int(np.ceil(Lr[0] / bar_s))
    k_hi = int(np.floor(Lr[1] / bar_s))
    n = Fn.shape[1]
    for k in range(k_lo, k_hi + 1):
        Lf = k * bar_s * fr
        for t1 in range(int(start_r[0] * fr) + W, int(start_r[1] * fr) + W):
            t2 = int(round(t1 + Lf))
            if t2 + W >= n:
                break
            a = Fn[:, t1 - W:t1 + W]
            b = Fn[:, t2 - W:t2 + W]
            s = float((a * b).sum(axis=0).mean())
            if best is None or s > best[0]:
                best = (s, t1 / fr, k)
    return best


def free_search(F, Lr, start_r, W_s=6.0):
    """no bar constraint (for live/rubato playing): best (t1, lag) over all frame lags via diagonal sums"""
    fr = frame_rate()
    Fn = (F / (np.linalg.norm(F, axis=0, keepdims=True) + 1e-9)).astype(np.float64)
    n = Fn.shape[1]
    W = int(W_s * fr)
    box = np.ones(2 * W + 1) / (2 * W + 1)
    lo_t = int(start_r[0] * fr) + W
    hi_t = int(start_r[1] * fr) + W
    best = None
    for lag in range(int(Lr[0] * fr), int(Lr[1] * fr) + 1):
        if lag >= n - W:
            break
        d = (Fn[:, :n - lag] * Fn[:, lag:]).sum(axis=0)
        sm = np.convolve(d, box, mode="same")
        hi = min(hi_t, n - lag - W - 1)
        if hi <= lo_t:
            continue
        i = lo_t + int(np.argmax(sm[lo_t:hi]))
        if best is None or sm[i] > best[0]:
            best = (float(sm[i]), i / fr, lag / fr)
    return best


def xcorr_refine(x, t1, L, search=0.03):
    """sample-accurate lag: compare x around t1 and x around t1+L, return refined L (seconds)"""
    m = A.to_mono(x)
    a0 = int(t1 * SR)
    b0 = int((t1 + L) * SR)
    w = int(0.4 * SR)
    s = int(search * SR)
    a = m[a0:a0 + w]
    best = None
    for d in range(-s, s + 1, 1):
        b = m[b0 + d:b0 + d + w]
        if len(b) < w:
            continue
        c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
        if best is None or c > best[0]:
            best = (c, d)
    return L + best[1] / SR, best[0]


def first_sound(x, thresh_db=-45):
    e = A.env_db(A.to_mono(x), SR, 0.01)
    idx = np.nonzero(e > e.max() + thresh_db)[0]
    return idx[0] * 0.01 if len(idx) else 0.0


def last_sound(x, thresh_db=-50):
    e = A.env_db(A.to_mono(x), SR, 0.01)
    idx = np.nonzero(e > e.max() + thresh_db)[0]
    return (idx[-1] + 1) * 0.01 if len(idx) else A.dur(x)


def analyze(stem, verbose=True):
    cfg = TRACKS[stem]
    x = load_track(stem)
    F, flux, lowflux, _ = features(x)
    P, phase, score = refine_period(flux, cfg["bpm"])
    bar_s = P * cfg["bar"]
    res = {"P": P, "phase": phase, "bar_s": bar_s, "dur": A.dur(x), "first": first_sound(x), "last": last_sound(x)}
    if cfg["len"] and not cfg.get("free"):
        s, t1, k = similarity_search(F, cfg["len"], cfg["start"], bar_s)
        L0 = k * bar_s
        L, c = xcorr_refine(x, t1, L0)
        res.update({"sim": s, "t1": t1, "bars": k, "L0": L0, "L": L, "xcorr": c})
    elif cfg["len"]:
        s, t1, L0 = free_search(F, cfg["len"], cfg["start"])
        L, c = xcorr_refine(x, t1, L0, search=0.05)
        res.update({"sim": s, "t1": t1, "bars": round(L0 / bar_s, 2), "L0": L0, "L": L, "xcorr": c})
    if verbose:
        print(stem, json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()}))
    return x, res


def build(stem):
    cfg = TRACKS[stem]
    x, r = analyze(stem)
    if cfg["len"]:
        C = cfg.get("xfade", 0.35)
        y = A.loopify(x, SR, length=r["L"], xfade=C, start=r["t1"])
        how = ("loop %.3f-%.3f s of the original (%d bars of %d at %.2f bpm), %.2f s equal-power crossfade of the "
               "post-loop audio into the loop head (self-similarity %.2f, waveform xcorr %.2f)" % (
                   r["t1"], r["t1"] + r["L"], int(round(r["bars"])), cfg["bar"], 60 / r["P"], C, r["sim"], r["xcorr"]))
    else:
        a = max(0.0, r["first"] - 0.01)
        b = min(r["dur"], r["last"] + 0.3)
        y = A.fade(x[int(a * SR):int(b * SR)], SR, 0.005, 0.25)
        y = np.concatenate([y, np.zeros((int(1.5 * SR), 2))])
        how = "full piece %.2f-%.2f s (leading silence trimmed, natural ending kept, 1.5 s silence before it repeats)" % (a, b)
    g = TARGET - A.lufs(y)
    y = y * A.undb(g)
    tp = A.true_peak_db(y)
    if tp > -1.0:
        y = A.soft_limit(y * A.undb(-1.0 - tp + 1.0), -1.0)  # only if ever needed
    path = os.path.join(OUTDIR, stem + ".ogg")
    A.save_ogg(path, y, SR, q=6)
    sr = A.seam_report(y) if cfg["len"] else {}
    print("  -> %s %.1fs I=%.1f TP=%.1f gain=%.1f seam=%s" % (stem, A.dur(y), A.lufs(y), A.true_peak_db(y), g, sr))
    return {"title": cfg["title"], "src": "https://incompetech.com/music/royalty-free/mp3-royaltyfree/%s.mp3" % cfg["title"].replace(" ", "%20"),
            "processing": how + "; static gain %+.1f dB to %.0f LUFS" % (g, TARGET), "dur": round(A.dur(y), 2), "loop": True}


def main(argv):
    if not argv:
        print(__doc__)
        return
    if argv[0] == "analyze":
        for s in argv[1:] or TRACKS:
            analyze(s)
    elif argv[0] == "build":
        man = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {}
        for s in argv[1:] or TRACKS:
            man[s] = build(s)
        with open(MANIFEST, "w") as f:
            json.dump(man, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
