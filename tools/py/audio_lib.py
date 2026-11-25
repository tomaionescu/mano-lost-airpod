"""Shared helpers for the audio build scripts (tools/py/audio_*.py).

Decoding goes through ffmpeg, encoding to OGG Vorbis through sox (libvorbis); all DSP in numpy/scipy.
Arrays are float32/float64 shaped (n,) for mono or (n, ch) for multichannel.
"""
import os
import subprocess
import tempfile

import numpy as np
from scipy import signal
from scipy.io import wavfile

FFMPEG = "/opt/homebrew/bin/ffmpeg"
SOX = "/opt/homebrew/bin/sox"
SR = 44100

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "tools", "audio_src")
OUT = os.path.join(ROOT, "assets", "audio")
TMP = os.environ.get("AUDIO_TMP") or os.path.join(SRC, "_tmp")
os.makedirs(TMP, exist_ok=True)


# ------------------------------------------------------------------ io
def load(path, channels=2, sr=SR, start=None, dur=None):
    cmd = [FFMPEG, "-v", "error"]
    if start is not None:
        cmd += ["-ss", "%.4f" % start]
    if dur is not None:
        cmd += ["-t", "%.4f" % dur]
    cmd += ["-i", path, "-f", "f32le", "-acodec", "pcm_f32le", "-ar", str(sr), "-ac", str(channels), "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    if channels == 1:
        return x
    return x.reshape(-1, channels)


def save_wav(path, x, sr=SR):
    wavfile.write(path, sr, np.asarray(x, dtype=np.float32))


def save_ogg(path, x, sr=SR, q=5):
    x = np.asarray(x, dtype=np.float64)
    pk = np.max(np.abs(x)) if x.size else 0
    if pk > 0.999:
        raise ValueError("would clip: peak %.3f for %s" % (pk, path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmpw = tempfile.mkstemp(suffix=".wav", dir=TMP)
    os.close(fd)
    try:
        save_wav(tmpw, x, sr)
        if os.path.exists(path):
            os.remove(path)
        subprocess.run([SOX, "-q", "-V1", tmpw, "-C", str(q), path], check=True)
    finally:
        os.remove(tmpw)
    return path


def ch(x):
    return 1 if x.ndim == 1 else x.shape[1]


def to_mono(x):
    return x if x.ndim == 1 else x.mean(axis=1)


def to_stereo(x):
    return np.stack([x, x], axis=1) if x.ndim == 1 else x


def dur(x, sr=SR):
    return x.shape[0] / sr


# ------------------------------------------------------------------ levels
def db(v):
    return 20 * np.log10(np.maximum(np.abs(v), 1e-12))


def undb(d):
    return 10 ** (d / 20.0)


def peak_db(x):
    return float(db(np.max(np.abs(x)))) if x.size else -240.0


def true_peak_db(x, sr=SR):
    y = signal.resample_poly(x, 4, 1, axis=0)
    return float(db(np.max(np.abs(y))))


def rms_db(x):
    return float(10 * np.log10(np.mean(np.asarray(x, dtype=np.float64) ** 2) + 1e-24))


def _biquad_hs(fs, G=3.99984385397, Q=0.7071752369554193, fc=1681.9744509555319):
    A = 10 ** (G / 40.0)
    w0 = 2 * np.pi * fc / fs
    alpha = np.sin(w0) / (2 * Q)
    cw = np.cos(w0)
    sA = np.sqrt(A)
    b = [A * ((A + 1) + (A - 1) * cw + 2 * sA * alpha), -2 * A * ((A - 1) + (A + 1) * cw),
         A * ((A + 1) + (A - 1) * cw - 2 * sA * alpha)]
    a = [(A + 1) - (A - 1) * cw + 2 * sA * alpha, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - 2 * sA * alpha]
    return np.array(b) / a[0], np.array(a) / a[0]


def _biquad_hp(fs, Q=0.5003270373253953, fc=38.13547087613982):
    w0 = 2 * np.pi * fc / fs
    alpha = np.sin(w0) / (2 * Q)
    cw = np.cos(w0)
    b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
    a = [1 + alpha, -2 * cw, 1 - alpha]
    return np.array(b) / a[0], np.array(a) / a[0]


def lufs(x, sr=SR):
    """ITU-R BS.1770-4 integrated loudness (mono measured as a single channel)."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    b1, a1 = _biquad_hs(sr)
    b2, a2 = _biquad_hp(sr)
    y = signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=0), axis=0)
    blk = int(0.4 * sr)
    hop = int(0.1 * sr)
    if y.shape[0] < blk:
        return float("-inf")
    n = 1 + (y.shape[0] - blk) // hop
    cs = np.concatenate([np.zeros((1, y.shape[1])), np.cumsum(y ** 2, axis=0)])
    idx = np.arange(n) * hop
    z = (cs[idx + blk] - cs[idx]) / blk  # (n, ch)
    zs = z.sum(axis=1)
    l = -0.691 + 10 * np.log10(zs + 1e-24)
    g = l > -70
    if not g.any():
        return float("-inf")
    rel = -0.691 + 10 * np.log10(zs[g].mean()) - 10
    g2 = g & (l > rel)
    return float(-0.691 + 10 * np.log10(zs[g2].mean()))


def short_term(x, sr=SR, win=3.0, hop=1.0):
    """momentary/short-term loudness curve (ungated) in LUFS"""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    b1, a1 = _biquad_hs(sr)
    b2, a2 = _biquad_hp(sr)
    y = signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=0), axis=0)
    w = int(win * sr)
    h = int(hop * sr)
    out = []
    for i in range(0, max(1, y.shape[0] - w + 1), h):
        out.append(-0.691 + 10 * np.log10((y[i:i + w] ** 2).mean(axis=0).sum() + 1e-24))
    return np.array(out)


def gain_to_lufs(x, target, sr=SR):
    return x * undb(target - lufs(x, sr))


def norm_peak(x, target_db=-3.0):
    return x * undb(target_db - peak_db(x))


# ------------------------------------------------------------------ filters / fx
def filt(x, sr, kind, freq, order=4, zero_phase=False):
    sos = signal.butter(order, freq, btype=kind, fs=sr, output="sos")
    if zero_phase:
        return signal.sosfiltfilt(sos, x, axis=0)
    return signal.sosfilt(sos, x, axis=0)


def lp(x, f, sr=SR, order=4):
    return filt(x, sr, "lowpass", f, order)


def hp(x, f, sr=SR, order=4):
    return filt(x, sr, "highpass", f, order)


def bp(x, lo, hi, sr=SR, order=4):
    return filt(x, sr, "bandpass", [lo, hi], order)


def shelf(x, f, gain_db, sr=SR, kind="low"):
    """RBJ shelf, S=1."""
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f / sr
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / 2 * np.sqrt(2)
    sA = np.sqrt(A)
    if kind == "low":
        b = [A * ((A + 1) - (A - 1) * cw + 2 * sA * alpha), 2 * A * ((A - 1) - (A + 1) * cw),
             A * ((A + 1) - (A - 1) * cw - 2 * sA * alpha)]
        a = [(A + 1) + (A - 1) * cw + 2 * sA * alpha, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - 2 * sA * alpha]
    else:
        b = [A * ((A + 1) + (A - 1) * cw + 2 * sA * alpha), -2 * A * ((A - 1) + (A + 1) * cw),
             A * ((A + 1) + (A - 1) * cw - 2 * sA * alpha)]
        a = [(A + 1) - (A - 1) * cw + 2 * sA * alpha, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - 2 * sA * alpha]
    return signal.lfilter(np.array(b) / a[0], np.array(a) / a[0], x, axis=0)


def peq(x, f, gain_db, q=1.0, sr=SR):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f / sr
    alpha = np.sin(w0) / (2 * q)
    cw = np.cos(w0)
    b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
    a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    return signal.lfilter(np.array(b) / a[0], np.array(a) / a[0], x, axis=0)


def fade(x, sr=SR, fin=0.0, fout=0.0, shape="cos"):
    y = np.array(x, dtype=np.float64, copy=True)
    n = y.shape[0]
    def curve(m):
        t = np.linspace(0, 1, m, endpoint=False) if m > 0 else np.zeros(0)
        return np.sin(t * np.pi / 2) ** 2 if shape == "cos" else t
    ni = min(n, int(round(fin * sr)))
    no = min(n, int(round(fout * sr)))
    if ni > 0:
        c = curve(ni)
        y[:ni] *= c if y.ndim == 1 else c[:, None]
    if no > 0:
        c = curve(no)[::-1]
        y[n - no:] *= c if y.ndim == 1 else c[:, None]
    return y


def resample_speed(x, factor):
    """play back `factor` times faster (pitch up when > 1), high-quality polyphase."""
    from fractions import Fraction
    fr = Fraction(1.0 / factor).limit_denominator(400)
    return signal.resample_poly(x, fr.numerator, fr.denominator, axis=0)


def make_ir(sr=SR, t60=1.2, predelay=0.012, channels=2, seed=1, lp_hz=6000, early=True):
    rng = np.random.default_rng(seed)
    n = int(sr * (t60 * 1.1 + predelay))
    t = np.arange(n) / sr
    env = np.exp(-6.91 * np.maximum(t - predelay, 0) / t60) * (t >= predelay)
    ir = rng.standard_normal((n, channels)) * env[:, None]
    # darker tail as it decays: blend a lowpassed copy in over time
    dark = lp(ir, lp_hz * 0.35, sr, 2)
    mixw = np.clip((t - predelay) / max(t60 * 0.5, 1e-3), 0, 1)[:, None]
    ir = lp(ir, lp_hz, sr, 2) * (1 - mixw) + dark * mixw
    if early:
        for k in range(6):
            d = int(sr * (predelay + rng.uniform(0.003, 0.04)))
            ir[d % n, :] += rng.uniform(0.2, 0.5) * rng.choice([-1, 1], size=channels)
    ir /= np.sqrt((ir ** 2).sum(axis=0, keepdims=True))
    return ir


def reverb(x, sr=SR, t60=1.2, wet=0.3, predelay=0.012, seed=1, lp_hz=6000, keep_len=True):
    xs = to_stereo(x)
    ir = make_ir(sr, t60, predelay, 2, seed, lp_hz)
    w = np.stack([signal.fftconvolve(xs[:, c], ir[:, c]) for c in range(2)], axis=1)
    if keep_len:
        w = w[: xs.shape[0]]
        dry = xs
    else:
        dry = np.zeros_like(w)
        dry[: xs.shape[0]] = xs
    # match wet energy roughly to dry
    return dry * (1 - wet) + w * wet


def env_db(x, sr=SR, win=0.05):
    m = to_mono(np.abs(x)) if x.ndim > 1 else np.abs(x)
    h = max(1, int(win * sr))
    n = len(m) // h
    if n == 0:
        return np.array([peak_db(x)])
    r = np.sqrt((m[: n * h].reshape(n, h) ** 2).mean(axis=1))
    return db(r)


def ascii_env(x, sr=SR, win=0.05, lo=-60, width=60):
    e = env_db(x, sr, win)
    rows = []
    for i, v in enumerate(e):
        k = int(np.clip((v - lo) / -lo * width, 0, width))
        rows.append("%6.2fs %6.1f |%s" % (i * win, v, "#" * k))
    return "\n".join(rows)


def centroid(x, sr=SR):
    m = to_mono(x)
    f, p = signal.welch(m, sr, nperseg=min(4096, len(m)))
    return float((f * p).sum() / (p.sum() + 1e-24))


def band_levels(x, sr=SR, bands=((20, 120), (120, 500), (500, 2000), (2000, 6000), (6000, 16000))):
    m = to_mono(x)
    f, p = signal.welch(m, sr, nperseg=min(8192, len(m)))
    tot = p.sum() + 1e-24
    return {"%d-%d" % b: round(float(10 * np.log10(p[(f >= b[0]) & (f < b[1])].sum() / tot + 1e-24)), 1) for b in bands}


# ------------------------------------------------------------------ editing
def onset_trim(x, sr=SR, thresh_db=-30.0, pre=0.004, rel_to_peak=True):
    """cut everything before the first transient (sample above peak+thresh_db), keep `pre` seconds lead."""
    m = np.abs(to_mono(x))
    ref = m.max() if rel_to_peak else 1.0
    idx = np.nonzero(m >= ref * undb(thresh_db))[0]
    if len(idx) == 0:
        return x
    s = max(0, idx[0] - int(pre * sr))
    return x[s:]


def tail_trim(x, sr=SR, floor_db=-50.0, win=0.01, fout=0.03):
    e = env_db(x, sr, win)
    pk = e.max()
    above = np.nonzero(e > pk + floor_db)[0]
    if len(above) == 0:
        return x
    end = min(x.shape[0], (above[-1] + 2) * int(win * sr))
    return fade(x[:end], sr, 0, min(fout, end / sr / 3))


def loopify(x, sr=SR, length=None, xfade=2.0, start=0.0):
    """Return a seamless loop of `length` seconds from x[start:]: the material just after the loop end is
    equal-power crossfaded into the head, so last sample -> first sample is a natural continuation."""
    s = int(start * sr)
    C = int(xfade * sr)
    L = int(length * sr) if length else x.shape[0] - s - C
    if s + L + C > x.shape[0]:
        raise ValueError("source too short: need %.1fs, have %.1fs" % ((s + L + C) / sr, x.shape[0] / sr))
    y = np.array(x[s:s + L], dtype=np.float64, copy=True)
    tail = x[s + L:s + L + C]
    t = (np.arange(C) + 0.5) / C
    fi = np.sin(t * np.pi / 2)
    fo = np.cos(t * np.pi / 2)
    if y.ndim > 1:
        fi, fo = fi[:, None], fo[:, None]
    y[:C] = y[:C] * fi + tail * fo
    return y


def seam_report(y, sr=SR):
    """level jump across the loop seam and sample discontinuity compared to typical sample steps"""
    w = int(0.5 * sr)
    a = rms_db(y[-w:])
    b = rms_db(y[:w])
    m = to_mono(y)
    d = np.abs(np.diff(m))
    jump = abs(m[0] - m[-1])
    return {"rms_end": round(a, 1), "rms_start": round(b, 1), "jump_db": round(b - a, 2),
            "seam_step": round(float(jump), 5), "p99_step": round(float(np.percentile(d, 99)), 5)}


def place(dst, src, at, sr=SR, gain=1.0):
    """mix src into dst at time `at` (seconds), wrapping around the end (for loops)"""
    i = int(at * sr) % dst.shape[0]
    n = src.shape[0]
    if dst.ndim > 1 and src.ndim == 1:
        src = to_stereo(src)
    first = min(n, dst.shape[0] - i)
    dst[i:i + first] += src[:first] * gain
    if first < n:
        rest = n - first
        dst[:rest] += src[first:first + rest] * gain
    return dst


def pan(x, p):
    """mono -> stereo, p in [-1, 1], equal power"""
    m = to_mono(x)
    a = (p + 1) * np.pi / 4
    return np.stack([m * np.cos(a), m * np.sin(a)], axis=1)


def limit(x, ceiling_db=-6.0, look=0.005, release=0.12, sr=SR, circular=True):
    """transparent-ish peak limiter: per-sample required gain, min-filtered over the lookahead window and
    smoothed; filters wrap around the ends when `circular` (so loops stay seamless)."""
    from scipy import ndimage
    c = undb(ceiling_db)
    a = np.abs(x) if x.ndim == 1 else np.abs(x).max(axis=1)
    g = np.minimum(1.0, c / (a + 1e-12))
    mode = "wrap" if circular else "nearest"
    n_look = max(1, int(look * sr))
    g = ndimage.minimum_filter1d(g, size=2 * n_look + 1, mode=mode)
    n_rel = max(1, int(release * sr))
    g = ndimage.uniform_filter1d(g, size=n_rel, mode=mode)
    g = ndimage.minimum_filter1d(g, size=2 * n_look + 1, mode=mode)
    g = np.minimum(g, c / (a + 1e-12))
    g = np.minimum(g, 1.0)
    return x * (g if x.ndim == 1 else g[:, None])


def circular(fn, x, pad_s=1.5, sr=SR):
    """apply a causal effect to a loop as if it had been playing forever: pre-roll the loop's own tail"""
    p = min(x.shape[0], int(pad_s * sr))
    xx = np.concatenate([x[-p:], x])
    return fn(xx)[p:]


def soft_limit(x, ceiling_db=-1.0):
    c = undb(ceiling_db)
    return np.tanh(x / c) * c


def describe(path):
    x = load(path, channels=2)
    m = to_mono(x)
    return {"dur": round(dur(x), 3), "lufs": round(lufs(x), 1), "peak": round(peak_db(x), 1),
            "centroid": round(centroid(m)), "bands": band_levels(m)}
