"""Build the one-shot SFX -> assets/audio/sfx/<stem>[_N].ogg (mono, 44.1 kHz, peak about -3 dBFS).

python3.11 -I tools/py/audio_sfx.py [stem ...]     # default: all
Writes tools/audio_src/sfx_manifest.json (sources + processing notes, used for CREDITS.md).
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
import numpy as np  # noqa: E402
from scipy import signal  # noqa: E402
import audio_lib as A  # noqa: E402

SR = A.SR
OUTDIR = os.path.join(A.OUT, "sfx")
FSD = os.path.join(A.SRC, "freesound")
KEN = os.path.join(A.SRC, "kenney")
MANIFEST = os.path.join(A.SRC, "sfx_manifest.json")


# ------------------------------------------------------------------ sources
def fs(sid, t0=None, t1=None):
    f = glob.glob(os.path.join(FSD, str(sid), "*-hq.mp3"))[0]
    d = None if t1 is None else t1 - (t0 or 0)
    return A.load(f, channels=1, start=t0, dur=d)


def ken(rel):
    return A.load(os.path.join(KEN, rel), channels=1)


# ------------------------------------------------------------------ synthesis helpers
def tt(d):
    return np.arange(int(round(d * SR))) / SR


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12.0)


def attack(y, a=0.0015):
    n = min(len(y), max(1, int(a * SR)))
    y = y.copy()
    y[:n] *= np.sin(np.linspace(0, np.pi / 2, n)) ** 2
    return y


def modal(f, dur, partials, tau, seed=0, strike=0.0, strike_band=(2000, 9000)):
    """sum of exponentially decaying partials (ratio, amp, decay multiplier) + optional strike noise"""
    rng = np.random.default_rng(seed)
    t = tt(dur)
    y = np.zeros_like(t)
    for r, a, m in partials:
        fr = f * r
        if fr > 15000:
            continue
        y += a * np.sin(2 * np.pi * fr * t + rng.uniform(0, 2 * np.pi)) * np.exp(-t * m / tau)
    y = attack(y)
    if strike > 0:
        n = int(0.008 * SR)
        nz = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.0012 * SR))
        lo, hi = strike_band
        nz = A.bp(nz, lo, min(hi, 0.45 * SR), SR, 2)
        y[:n] += strike * nz / (np.abs(nz).max() + 1e-12) * np.abs(y).max()
    return y


def mallet(f, dur=0.5, tau=None, strike=0.12, seed=0):
    """soft marimba / vibraphone-ish bar"""
    if tau is None:
        tau = 0.32 * (440.0 / f) ** 0.5
    return modal(f, dur, ((1, 1.0, 1.0), (4.0, 0.18, 3.2), (10.0, 0.05, 7.0)), tau, seed, strike)


def celesta(f, dur=0.9, tau=0.45, seed=0, strike=0.05):
    return modal(f, dur, ((1, 1.0, 1.0), (2, 0.28, 1.8), (3, 0.10, 2.6), (4.16, 0.07, 3.6), (5.43, 0.035, 5.0)),
                 tau, seed, strike, (3000, 12000))


def epiano(f, dur=1.4, tau=0.8, index=1.1, tine=0.12):
    """FM electric piano (1:1 modulator, decaying index) with a short tine partial"""
    t = tt(dur)
    I = index * np.exp(-t / 0.22)
    y = np.sin(2 * np.pi * f * t + I * np.sin(2 * np.pi * f * t)) * np.exp(-t / tau)
    y += tine * np.sin(2 * np.pi * f * 7.0 * t) * np.exp(-t / 0.045)
    return attack(y, 0.003)


def pluck(f, dur=1.2, damp=0.9965, soft=3, seed=0):
    """Karplus-Strong plucked string (block-vectorised), soft excitation"""
    n = int(dur * SR)
    L = max(2, int(round(SR / f - 0.5)))
    rng = np.random.default_rng(seed)
    exc = rng.uniform(-1, 1, L)
    for _ in range(soft):
        exc = 0.5 * (exc + np.roll(exc, 1))
    exc -= exc.mean()
    y = np.zeros(n + 2 * L)
    y[:L] = exc
    b = 1
    while b * L < n + L:
        s = b * L
        prev = y[s - L:s]
        prev1 = y[s - L - 1:s - 1] if s - L - 1 >= 0 else np.concatenate([[0.0], y[s - L:s - 1]])
        y[s:s + L] = damp * 0.5 * (prev + prev1)
        b += 1
    y = y[:n]
    return attack(y / (np.abs(y).max() + 1e-12), 0.001)


def sparkle(dur=0.8, n=10, seed=1, lo=84, hi=103, level=0.5):
    """random high celesta pings on a C-major pentatonic scale, thinning out over time"""
    rng = np.random.default_rng(seed)
    scale = [m for m in range(lo, hi + 1) if m % 12 in (0, 2, 4, 7, 9)]
    y = np.zeros(int(dur * SR))
    for k in range(n):
        t0 = (k / n) ** 1.25 * dur * 0.6 + rng.uniform(0, 0.02)
        f = midi(int(rng.choice(scale)))
        a = level * (1 - k / (n + 1)) ** 1.4 * rng.uniform(0.55, 1.0)
        tone = celesta(f, 0.3, tau=rng.uniform(0.05, 0.11), seed=seed * 100 + k, strike=0.0)
        A.place(y, tone * a, t0)
    return y


def noise_sweep(dur, fc, bw, env, seed=3):
    """white noise through a time-varying gaussian band (STFT domain). fc/bw/env: callables of t in [0, 1]"""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(int(dur * SR) + 4096)
    nper = 1024
    f, t, Z = signal.stft(x, SR, nperseg=nper, noverlap=nper * 3 // 4)
    tn = np.clip(t / dur, 0, 1)
    for i, ti in enumerate(tn):
        c, w = fc(ti), bw(ti)
        Z[:, i] *= np.exp(-0.5 * ((np.log2(np.maximum(f, 1)) - np.log2(c)) / w) ** 2) * env(ti)
    _, y = signal.istft(Z, SR, nperseg=nper, noverlap=nper * 3 // 4)
    return y[: int(dur * SR)]


def addp(*arrs):
    """sum arrays of different lengths (zero-padded)"""
    n = max(len(a) for a in arrs)
    y = np.zeros(n)
    for a in arrs:
        y[:len(a)] += a
    return y


def mix(length, *parts):
    """parts: (signal, start_seconds, gain)"""
    y = np.zeros(int(length * SR))
    for s, at, g in parts:
        i = int(at * SR)
        n = min(len(s), len(y) - i)
        if n > 0:
            y[i:i + n] += s[:n] * g
    return y


def room(y, t60=0.35, wet=0.15, seed=5, lp_hz=7000, tail=None):
    """small room/plate; extends the clip so the tail is not cut"""
    ext = int((tail if tail is not None else t60 * 0.9) * SR)
    y2 = np.concatenate([y, np.zeros(ext)])
    w = A.reverb(y2, SR, t60=t60, wet=wet, predelay=0.008, seed=seed, lp_hz=lp_hz)
    return A.to_mono(w) * np.sqrt(2) if w.ndim > 1 else w


def finish(y, peak=-3.0, fin=0.0005, fout=0.02, trim_db=-55.0, hp_hz=40, onset_db=-40.0):
    """high-pass, start right at the first transient, trim the tail at trim_db under peak, fade, normalise peak"""
    y = A.hp(np.asarray(y, dtype=np.float64), hp_hz, SR, 2)
    y = A.onset_trim(y, SR, thresh_db=onset_db, pre=0.002)
    y = A.tail_trim(y, SR, floor_db=trim_db, win=0.01, fout=fout)
    y = A.fade(y, SR, fin=fin, fout=0)
    return A.norm_peak(y, peak)


# ------------------------------------------------------------------ the sounds
BUILD = {}
NOTES = {}


def sound(stem, sources, note):
    def deco(fn):
        BUILD[stem] = fn
        NOTES[stem] = {"sources": sources, "note": note}
        return fn
    return deco


@sound("ui_hover", ["synth"], "synthesised soft wooden tick (modal mallet D7, 25 ms decay); peak -6 dBFS on purpose (frequent)")
def ui_hover():
    y = addp(mallet(midi(98), 0.12, tau=0.03, strike=0.25, seed=11) * 0.9, 0.25 * mallet(midi(86), 0.12, tau=0.025, strike=0.0, seed=12))
    return finish(A.lp(y, 7500), peak=-6.0, fout=0.015)


@sound("ui_click", ["synth"], "synthesised soft mallet 'tock' (A5 + woody strike noise), tiny room")
def ui_click():
    y = addp(mallet(midi(81), 0.25, tau=0.07, strike=0.35, seed=21), 0.35 * mallet(midi(93), 0.2, tau=0.03, strike=0.0, seed=22))
    return finish(room(y, 0.25, 0.10), peak=-3.0)


@sound("ui_back", ["synth"], "synthesised low mallet 'bup' (D5 with a slight downward pitch glide)")
def ui_back():
    t = tt(0.25)
    f = midi(74) * (1 - 0.03 * (1 - np.exp(-t / 0.03)))
    ph = 2 * np.pi * np.cumsum(f) / SR
    tau = 0.08
    y = np.sin(ph) * np.exp(-t / tau) + 0.15 * np.sin(4 * ph) * np.exp(-t * 3.2 / tau)
    y = addp(attack(y, 0.002), 0.2 * mallet(midi(86), 0.25, tau=0.03, strike=0.3, seed=31))
    return finish(room(y, 0.25, 0.1), peak=-3.0)


@sound("ui_open", ["synth"], "synthesised rising mallet pair (A5 -> E6) over a soft rising air swish")
def ui_open():
    sw = noise_sweep(0.32, lambda u: 700 * 2 ** (2.2 * u), lambda u: 0.6, lambda u: np.sin(np.pi * min(1, u * 1.1)) ** 2)
    y = mix(0.7, (sw, 0.0, 0.05), (mallet(midi(81), 0.5, tau=0.12, seed=41), 0.02, 0.8), (mallet(midi(88), 0.6, tau=0.14, seed=42), 0.09, 0.8))
    return finish(room(y, 0.4, 0.14), peak=-3.0)


@sound("ui_close", ["synth"], "synthesised falling mallet pair (E6 -> A5) over a soft falling air swish")
def ui_close():
    sw = noise_sweep(0.30, lambda u: 2600 * 2 ** (-2.0 * u), lambda u: 0.6, lambda u: np.sin(np.pi * min(1, u * 1.1)) ** 2)
    y = mix(0.7, (sw, 0.0, 0.05), (mallet(midi(88), 0.5, tau=0.11, seed=51), 0.02, 0.75), (mallet(midi(81), 0.6, tau=0.13, seed=52), 0.09, 0.8))
    return finish(room(y, 0.4, 0.14), peak=-3.0)


@sound("whoosh", ["synth"], "synthesised soft transition whoosh (band-swept noise 350 Hz -> 1.9 kHz -> 600 Hz, 0.55 s), gentle room")
def whoosh():
    def fc(u):
        return 350 * 2 ** (2.45 * np.sin(np.pi * u * 0.85))
    y = addp(noise_sweep(0.55, fc, lambda u: 0.45 + 0.25 * u, lambda u: (np.sin(np.pi * u) ** 1.6) * (1 - 0.3 * u)),
             0.4 * A.lp(noise_sweep(0.55, lambda u: 180, lambda u: 0.8, lambda u: np.sin(np.pi * u) ** 2, seed=4), 400))
    return finish(room(y, 0.5, 0.12), peak=-3.0, fin=0.03, fout=0.05)


@sound("toast", ["synth"], "synthesised soft notification chime (celesta E6 + B6 grace, small plate)")
def toast():
    y = mix(1.0, (celesta(midi(88), 0.9, tau=0.32, seed=61), 0.0, 0.9), (celesta(midi(95), 0.8, tau=0.25, seed=62), 0.035, 0.45),
            (mallet(midi(76), 0.6, tau=0.2, strike=0.0, seed=63), 0.0, 0.25))
    return finish(room(y, 0.7, 0.18), peak=-3.0, fout=0.1)


@sound("objective", ["synth"], "synthesised gentle 2-note sting: FM electric-piano E5 -> A5 with mallet octave doubling and a low A3 bed, plate reverb")
def objective():
    n1 = addp(epiano(midi(76), 1.6, tau=0.9), 0.25 * mallet(midi(88), 1.0, tau=0.25, strike=0.0, seed=71))
    n2 = addp(epiano(midi(81), 1.8, tau=1.0), 0.25 * mallet(midi(93), 1.0, tau=0.25, strike=0.0, seed=72))
    bed = 0.35 * epiano(midi(57), 1.8, tau=1.1, index=0.6, tine=0.05)
    y = mix(2.0, (n1, 0.0, 0.6), (n2, 0.18, 0.7), (bed, 0.18, 0.5))
    return finish(room(y, 1.2, 0.22, tail=0.8), peak=-3.0, fout=0.25)


@sound("coin", ["kenney:rpg-audio/handleCoins2.ogg", "synth"], "real coin clink (Kenney handleCoins2, high-passed) + synthesised 2-note celesta chime B5 -> E6")
def coin():
    c = A.hp(ken("rpg-audio/Audio/handleCoins2.ogg"), 1200, SR, 2)
    c = A.onset_trim(c, SR, thresh_db=-30, pre=0.001)
    c = A.norm_peak(c, 0)
    ch1 = celesta(midi(83), 0.4, tau=0.12, seed=81)
    ch2 = celesta(midi(88), 0.9, tau=0.3, seed=82)
    y = mix(1.1, (c, 0.0, 0.55), (ch1, 0.02, 0.55), (ch2, 0.10, 0.75))
    return finish(room(y, 0.5, 0.12), peak=-3.0, fout=0.1)


@sound("pickup", ["kenney:rpg-audio/cloth3.ogg", "synth"], "synthesised soft rising 'pop' + mallet G6 blip, with a short cloth rustle (Kenney cloth3)")
def pickup():
    t = tt(0.16)
    f = 520 * 2 ** (1.1 * (1 - np.exp(-t / 0.04)))
    pop = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.045)
    pop = attack(pop, 0.003)
    cl = ken("rpg-audio/Audio/cloth3.ogg")
    cl = A.fade(A.onset_trim(cl, SR, -30)[: int(0.22 * SR)], SR, 0.005, 0.08)
    cl = A.norm_peak(A.hp(cl, 300, SR, 2), 0)
    y = mix(0.7, (cl, 0.0, 0.18), (pop, 0.01, 0.8), (mallet(midi(91), 0.5, tau=0.12, seed=91), 0.06, 0.5))
    return finish(room(y, 0.35, 0.12), peak=-3.0)


@sound("duck", ["freesound:201285", "synth"], "rubber duck squeak (Freesound 201285, 1.78-2.25 s) + synthesised pentatonic celesta sparkle")
def duck():
    sq = fs(201285, 1.74, 2.30)
    sq = A.fade(A.onset_trim(A.hp(sq, 300, SR, 2), SR, -30), SR, 0.003, 0.05)
    sq = A.norm_peak(sq, 0)
    sp = sparkle(1.0, n=11, seed=7, lo=86, hi=103, level=0.55)
    y = mix(1.4, (sq, 0.0, 0.9), (sp, 0.16, 0.6))
    return finish(room(y, 0.9, 0.2, tail=0.5), peak=-3.0, fout=0.15)


@sound("fanfare", ["synth"], "synthesised short happy sting (C major: plucked-string arpeggio G4-C5-E5-G5 / E5-G5 -> C6, held C chord on FM e-piano, celesta sparkle), plate reverb")
def fanfare():
    seq = [(67, 0.00), (72, 0.11), (76, 0.22), (79, 0.33), (76, 0.55), (79, 0.66), (84, 0.80)]
    parts = []
    for i, (n, at) in enumerate(seq):
        last = i == len(seq) - 1
        parts.append((pluck(midi(n), 1.6 if last else 0.6, damp=0.997 if last else 0.993, seed=100 + i), at, 0.5))
        parts.append((mallet(midi(n + 12), 0.8 if last else 0.3, tau=0.25 if last else 0.08, strike=0.05, seed=120 + i), at, 0.22))
    for k, n in enumerate([60, 64, 67, 72]):
        parts.append((epiano(midi(n), 1.8, tau=0.9, index=0.8, tine=0.06), 0.80, 0.22))
    parts.append((pluck(midi(48), 1.8, damp=0.998, seed=140), 0.80, 0.35))
    parts.append((sparkle(1.0, n=9, seed=17, lo=91, hi=105, level=0.5), 0.85, 0.5))
    y = mix(2.8, *parts)
    return finish(room(y, 1.1, 0.2, tail=0.7), peak=-3.0, fout=0.3)


@sound("journal_open", ["kenney:rpg-audio/bookOpen.ogg", "kenney:rpg-audio/bookFlip3.ogg"], "Kenney bookOpen followed by a page flip (bookFlip3), small room")
def journal_open():
    a = A.norm_peak(A.onset_trim(ken("rpg-audio/Audio/bookOpen.ogg"), SR, -30), 0)
    b = A.norm_peak(A.onset_trim(ken("rpg-audio/Audio/bookFlip3.ogg"), SR, -30), 0)
    y = mix(0.6, (a, 0.0, 0.9), (A.lp(b, 9000), 0.12, 0.45))
    return finish(room(y, 0.3, 0.08), peak=-3.0)


@sound("journal_close", ["kenney:rpg-audio/bookClose.ogg"], "Kenney bookClose, gentle 9 kHz low-pass, small room")
def journal_close():
    y = A.lp(ken("rpg-audio/Audio/bookClose.ogg"), 9000)
    return finish(room(y, 0.3, 0.08), peak=-3.0, onset_db=-26.0)


@sound("map_open", ["freesound:447931"], "Freesound 447931 'Unfold a map' from 0.28 s (skips the faint pre-crinkle so the unfold starts at once), 20 ms fade-in, high-passed 120 Hz")
def map_open():
    y = A.fade(A.hp(fs(447931, 0.28, None), 120, SR, 2), SR, 0.02, 0)
    return finish(y, peak=-3.0, fout=0.08, onset_db=-30.0)


@sound("shutter", ["freesound:271010"], "Freesound 271010 camera shutter click (0.62-1.30 s), high-passed 150 Hz")
def shutter():
    y = A.hp(fs(271010, 0.62, 1.32), 150, SR, 2)
    return finish(y, peak=-3.0, fout=0.04, onset_db=-24.0)


@sound("plink", ["freesound:361661"], "Freesound 361661 small plastic item drop (bounce sequence), sped up x1.12 for a lighter object, short tiled-room reflection")
def plink():
    y = fs(361661, 0.08, 0.86)
    y = A.resample_speed(A.hp(y, 400, SR, 2), 1.12)
    return finish(room(y, 0.45, 0.16, lp_hz=9000), peak=-3.0, fout=0.08)


@sound("typing_burst", ["freesound:537473"], "Freesound 537473 keyboard typing, densest 2.0 s window (45.8-47.8 s), mono, fades")
def typing_burst():
    y = A.hp(fs(537473, 45.78, 47.9), 120, SR, 2)
    y = A.fade(y, SR, 0.005, 0.08)
    return finish(y, peak=-3.0, fout=0.06)


@sound("coffee_machine", ["freesound:503427", "freesound:402845"],
       "3.0 s seamless loop: coffee grinder (Freesound 503427) over espresso pump/brew (Freesound 402845, 24-33 s), 0.4 s crossfaded seam, fade-in/out not applied so it can loop")
def coffee_machine():
    g = A.hp(fs(503427, 1.0, 5.0), 150, SR, 2)
    b = A.hp(fs(402845, 24.0, 28.0), 60, SR, 2)
    g = A.norm_peak(g, 0)
    b = A.norm_peak(b, 0)
    y = 0.7 * g + 0.55 * b
    y = A.loopify(y, SR, length=3.0, xfade=0.4)
    return A.norm_peak(y, -3.0)


@sound("machine_clunk", ["freesound:448673", "kenney:impact-sounds/impactSoft_heavy_000.ogg"],
       "soda machine bottle drop (Freesound 448673, 18.00-18.60 s) layered with a low soft thud (Kenney impactSoft_heavy_000)")
def machine_clunk():
    d = A.hp(fs(448673, 18.02, 18.62), 60, SR, 2)
    d = A.norm_peak(A.fade(d, SR, 0.004, 0.12), 0)
    th = A.lp(ken("impact-sounds/Audio/impactSoft_heavy_000.ogg"), 1500)
    th = A.norm_peak(th, 0)
    y = mix(0.75, (d, 0.0, 0.9), (th, 0.055, 0.55))
    return finish(y, peak=-3.0, fout=0.08, onset_db=-24.0)


def _shake(seg_t0, seg_t1, sid, seed):
    y = A.hp(fs(sid, seg_t0, seg_t1), 70, SR, 2)
    y = A.fade(y, SR, 0.004, 0.18)
    th = A.norm_peak(A.lp(ken("impact-sounds/Audio/impactMetal_heavy_000.ogg"), 2500), 0)
    y = A.norm_peak(y, 0)
    out = mix(len(y) / SR + 0.05, (y, 0.0, 0.85), (th, 0.0, 0.4))
    return finish(out, peak=-3.0, fout=0.1)


@sound("machine_shake_1", ["freesound:104371", "kenney:impact-sounds/impactMetal_heavy_000.ogg"], "metal rattle (Freesound 104371, 6.85-7.55 s) + Kenney metal thud on the downbeat")
def machine_shake_1():
    return _shake(6.85, 7.55, 104371, 1)


@sound("machine_shake_2", ["freesound:104371", "kenney:impact-sounds/impactMetal_heavy_000.ogg"], "metal rattle (Freesound 104371, 7.75-8.45 s) + Kenney metal thud")
def machine_shake_2():
    return _shake(7.75, 8.45, 104371, 2)


@sound("machine_shake_3", ["freesound:849797", "kenney:impact-sounds/impactMetal_heavy_000.ogg"], "metal rattle hit (Freesound 849797, 22.42-23.05 s) + Kenney metal thud")
def machine_shake_3():
    return _shake(22.42, 23.05, 849797, 3)


@sound("babyfoot_kick_1", ["freesound:180320"], "table-football slapshot hit (Freesound 180320, 2.40-2.72 s)")
def babyfoot_kick_1():
    y = A.hp(fs(180320, 2.39, 2.75), 90, SR, 2)
    return finish(y, peak=-3.0, fout=0.05)


@sound("babyfoot_kick_2", ["freesound:186354"], "table-football rod/ball hit (Freesound 186354, 1.76-2.05 s)")
def babyfoot_kick_2():
    y = A.hp(fs(186354, 1.75, 2.06), 90, SR, 2)
    return finish(y, peak=-3.0, fout=0.05, onset_db=-22.0)


@sound("babyfoot_kick_3", ["freesound:186354"], "table-football rod/ball hit (Freesound 186354, 0.01-0.30 s)")
def babyfoot_kick_3():
    y = A.hp(fs(186354, 0.0, 0.31), 90, SR, 2)
    return finish(y, peak=-3.0, fout=0.05, onset_db=-22.0)


@sound("babyfoot_goal", ["freesound:387132"], "Freesound 387132 'Foosball Win': ball thud into the goal (0.80-1.25 s) spliced onto the return-channel rattle (2.00-3.25 s) with a 60 ms crossfade")
def babyfoot_goal():
    a = A.hp(fs(387132, 0.78, 1.28), 80, SR, 2)
    b = A.hp(fs(387132, 2.0, 3.3), 80, SR, 2)
    C = int(0.06 * SR)
    a = A.fade(a, SR, 0.002, 0)
    w = np.sin(np.linspace(0, np.pi / 2, C)) ** 2
    y = np.concatenate([a[:-C], a[-C:] * (1 - w) + b[:C] * w, b[C:]])
    return finish(y, peak=-3.0, fout=0.15, onset_db=-24.0)


@sound("crowd_cheer", ["freesound:752709"], "Freesound 752709 small crowd cheer + applause (0.28-2.60 s), mono, fades")
def crowd_cheer():
    y = A.hp(fs(752709, 0.28, 2.62), 100, SR, 2)
    y = A.fade(y, SR, 0.01, 0.35)
    return finish(y, peak=-3.0, fout=0.1)


@sound("sit", ["freesound:767051", "kenney:impact-sounds/impactSoft_medium_000.ogg"], "soft seat thud (Kenney impactSoft_medium_000, low-passed) + office-chair creak (Freesound 767051, 7.60-8.00 s)")
def sit():
    th = A.norm_peak(A.lp(ken("impact-sounds/Audio/impactSoft_medium_000.ogg"), 900), 0)
    cr = A.hp(fs(767051, 7.60, 8.02), 200, SR, 2)
    cr = A.norm_peak(A.fade(cr, SR, 0.004, 0.08), 0)
    y = mix(0.6, (th, 0.0, 0.6), (cr, 0.04, 0.85))
    return finish(room(y, 0.3, 0.08), peak=-3.0)


@sound("door_open", ["freesound:637479"], "Freesound 637479 institutional push-bar door, opening part (0.00-1.26 s)")
def door_open():
    y = A.hp(fs(637479, 0.0, 1.30), 50, SR, 2)
    return finish(y, peak=-3.0, fout=0.1, onset_db=-26.0)


@sound("door_close", ["freesound:637479"], "Freesound 637479 institutional push-bar door, closing part (1.96-2.89 s)")
def door_close():
    y = A.hp(fs(637479, 1.95, 2.89), 50, SR, 2)
    return finish(y, peak=-3.0, fout=0.12)


@sound("phone_buzz", ["freesound:384487"], "Freesound 384487 phone vibrating on glass, two pulses (0.00-1.66 s)")
def phone_buzz():
    y = A.hp(fs(384487, 0.0, 1.68), 80, SR, 2)
    return finish(y, peak=-3.0, fout=0.04)


@sound("zipper", ["freesound:763462"], "Freesound 763462 backpack zipper, first 1.15 s of the pull, fade-out")
def zipper():
    y = A.hp(fs(763462, 0.0, 1.25), 120, SR, 2)
    y = A.fade(y, SR, 0.003, 0.25)
    return finish(y, peak=-3.0, fout=0.05)


# ------------------------------------------------------------------ main
def main(argv):
    stems = argv or list(BUILD)
    man = {}
    if os.path.exists(MANIFEST):
        man = json.load(open(MANIFEST))
    for stem in stems:
        y = BUILD[stem]()
        path = os.path.join(OUTDIR, stem + ".ogg")
        A.save_ogg(path, y, SR, q=5)
        e = A.env_db(y, SR, 0.02)
        line = "".join(" .:-=+*#%@"[int(np.clip((v + 60) / 60 * 9.99, 0, 9))] for v in e)
        print("%-16s %.3fs peak=%5.1f |%s|" % (stem, len(y) / SR, A.peak_db(y), line[:90]))
        man[stem] = dict(NOTES[stem], dur=round(len(y) / SR, 3))
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
