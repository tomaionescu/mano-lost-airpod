"""Synthesise the stage-4 one-shots offline (no generation service, no samples) -> assets/audio/sfx/<stem>.ogg.

python3.11 -I tools/py/sfx_synth.py            # all
python3.11 -I tools/py/sfx_synth.py airpod_chirp

- airpod_chirp: the right AirPod ringing from inside the Under's sofa (scripts/minigames/findmy.gd): a bright
  rising four-note sine chirp, played twice, 1.4 s (an earbud's "find me" tone, not any brand's sound).
- soundcheck_thump: the BDE's sound check through the Under: a kick drum (pitch-swept sine, sub tail, a click),
  0.6 s.
- kebab_bell: the counter bell of the kebab (scripts/minigames/kebab.gd): a struck bell, 1.1 s.
Mono, 44.1 kHz, peak about -3 dBFS, written through tools/py/audio_lib.py (sox, libvorbis).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
import numpy as np  # noqa: E402
import audio_lib as A  # noqa: E402

SR = A.SR
OUT = os.path.join(A.OUT, "sfx")


def tt(d):
    return np.arange(int(round(d * SR))) / SR


def env_adsr(n, a=0.004, r=0.06):
    e = np.ones(n)
    na = max(1, int(a * SR))
    nr = max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] *= np.linspace(1, 0, nr)
    return e


def airpod_chirp():
    notes = [1760.0, 2217.5, 2637.0, 3520.0]   # A6, C#7, E7, A7
    one = []
    for f in notes:
        t = tt(0.085)
        y = np.sin(2 * np.pi * f * t) + 0.18 * np.sin(2 * np.pi * 2 * f * t)
        one.append(y * env_adsr(len(t), 0.003, 0.03))
        one.append(np.zeros(int(0.018 * SR)))
    one = np.concatenate(one)
    gap = np.zeros(int(0.22 * SR))
    y = np.concatenate([one, gap, one, np.zeros(int(0.25 * SR))])
    # a little room: the sofa's cushions damp the top
    y = A.lp(y, 7000)
    y = A.to_mono(A.reverb(y, t60=0.35, wet=0.12))
    return A.norm_peak(A.fade(y, fout=0.05), -3.0)


def soundcheck_thump():
    d = 0.6
    t = tt(d)
    f = 48.0 + 92.0 * np.exp(-t * 28.0)          # 140 Hz down to 48 Hz
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase) * np.exp(-t * 6.5)
    rng = np.random.default_rng(7)
    click = rng.normal(0, 1, len(t)) * np.exp(-t * 180.0) * 0.35
    click = A.bp(click, 1500, 6000)
    y = body + click
    y = np.tanh(y * 1.6) / np.tanh(1.6)
    y = A.to_mono(A.reverb(y, t60=0.9, wet=0.18))
    return A.norm_peak(A.fade(y, fout=0.08), -3.0)


def kebab_bell():
    d = 1.1
    t = tt(d)
    f = 1318.5   # E6
    y = np.zeros_like(t)
    for r, a, m in [(1.0, 1.0, 1.0), (2.76, 0.5, 1.8), (5.40, 0.25, 3.0), (8.93, 0.12, 4.5)]:
        y += a * np.sin(2 * np.pi * f * r * t) * np.exp(-t * 3.2 * m)
    y *= env_adsr(len(t), 0.001, 0.05)
    y = A.to_mono(A.reverb(y, t60=0.6, wet=0.15))
    return A.norm_peak(y, -3.0)


SOUNDS = {"airpod_chirp": airpod_chirp, "soundcheck_thump": soundcheck_thump, "kebab_bell": kebab_bell}

if __name__ == "__main__":
    want = sys.argv[1:] or list(SOUNDS)
    for stem in want:
        x = SOUNDS[stem]()
        path = A.save_ogg(os.path.join(OUT, stem + ".ogg"), x)
        print("%s: %.2f s, peak %.1f dBFS -> %s" % (stem, A.dur(x), A.peak_db(x), path))
