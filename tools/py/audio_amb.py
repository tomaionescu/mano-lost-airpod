"""Build the seamless ambience loops -> assets/audio/amb/<stem>.ogg (stereo, 44.1 kHz).

python3.11 -I tools/py/audio_amb.py [stem ...]
Each loop: source segment(s) -> EQ / distance treatment / layering -> loopify (equal-power crossfade of the
material after the loop end into the head) -> static gain to the target LUFS. Writes tools/audio_src/amb_manifest.json.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
import numpy as np  # noqa: E402
import audio_lib as A  # noqa: E402

SR = A.SR
OUTDIR = os.path.join(A.OUT, "amb")
FSD = os.path.join(A.SRC, "freesound")
KEN = os.path.join(A.SRC, "kenney")
MANIFEST = os.path.join(A.SRC, "amb_manifest.json")


def fs(sid, t0=None, t1=None, ch=2):
    f = glob.glob(os.path.join(FSD, str(sid), "*-hq.mp3"))[0]
    d = None if t1 is None else t1 - (t0 or 0)
    return A.load(f, channels=ch, start=t0, dur=d)


def ken(rel):
    return A.load(os.path.join(KEN, rel), channels=1)


def fit(x, n):
    """pad/cut to n samples"""
    if x.shape[0] >= n:
        return x[:n]
    pad = np.zeros((n - x.shape[0],) + x.shape[1:])
    return np.concatenate([x, pad])


def decorrelate(mono, n, offset_s):
    """stereo from a mono noise-like source: right channel taken offset_s later"""
    o = int(offset_s * SR)
    return np.stack([mono[:n], mono[o:o + n]], axis=1)


def width(x, w):
    """scale the side signal (w=0 mono, 1 unchanged)"""
    m = (x[:, 0] + x[:, 1]) / 2
    s = (x[:, 0] - x[:, 1]) / 2 * w
    return np.stack([m + s, m - s], axis=1)


def at_lufs(x, target):
    return x * A.undb(target - A.lufs(x))


def events(x, rise=15.0, gap=0.4, win=0.02):
    e = A.env_db(A.to_mono(x), SR, win)
    fl = np.percentile(e, 30)
    on = e > fl + rise
    out = []
    i = 0
    while i < len(e):
        if on[i]:
            j = i
            last = i
            while j < len(e) and (on[j] or (j - last) * win < gap):
                if on[j]:
                    last = j
                j += 1
            out.append((max(0, i - 2) * win, (last + 3) * win, float(e[i:last + 1].max())))
            i = last + 1
        else:
            i += 1
    return out


BUILD = {}
NOTES = {}


def amb(stem, sources, note, target, length, xfade):
    def deco(fn):
        BUILD[stem] = (fn, target, length, xfade)
        NOTES[stem] = {"sources": sources, "note": note, "target_lufs": target}
        return fn
    return deco


# every builder returns a stereo array of at least length + xfade seconds
@amb("city_traffic", ["freesound:513729", "freesound:36734", "freesound:523959", "freesound:3185"],
     "calm Paris street (513729) + distant low traffic roar (36734 calm section, low-passed 1.4 kHz) + one moped pass "
     "(523959, low-passed, ~38 s) + a fainter distant moped (3185, ~14 s)", -23.0, 80.0, 3.0)
def city_traffic(n):
    base = A.hp(fs(513729, 4.0, 4.0 + n / SR + 0.1), 35, SR, 2)
    base = at_lufs(fit(base, n), -26.0)
    roar = A.hp(A.lp(fs(36734, 60.0, 60.0 + n / SR + 0.1), 1400, SR, 2), 35, SR, 2)
    roar = at_lufs(fit(roar, n), -31.0)
    y = base + roar
    mp = A.hp(A.lp(fs(523959, 1.5, 13.0), 4500, SR, 2), 90, SR, 2)
    mp = A.fade(mp, SR, 1.5, 3.0)
    mp = at_lufs(mp, -31.0)
    A.place(y, mp, 36.0)
    mp2 = A.hp(A.lp(fs(3185, 0.0, 9.0, ch=1), 3000, SR, 2), 120, SR, 2)
    mp2 = A.fade(mp2, SR, 1.0, 2.5)
    mp2 = A.pan(mp2, -0.5)
    mp2 = at_lufs(mp2, -36.0)
    A.place(y, mp2, 13.0)
    return y


@amb("wind_light", ["freesound:181250"], "gentle breeze (181250, mono) made stereo by taking the right channel 17 s later; "
     "high-passed 70 Hz, low-passed 5.5 kHz", -28.0, 70.0, 3.0)
def wind_light(n):
    m = fs(181250, 60.0, 156.0, ch=1)
    m = A.lp(A.hp(m, 70, SR, 2), 5500, SR, 2)
    return decorrelate(m, n, 17.0)


@amb("courtyard_crowd", ["freesound:741283", "freesound:407051"],
     "outdoor walla, mostly French (741283) + a farther student crowd layer (407051); both band-limited (150 Hz-3.6 kHz / "
     "2.5 kHz) with a little reverb for distance so words stay unintelligible", -24.0, 65.0, 3.0)
def courtyard_crowd(n):
    a = A.lp(A.hp(fs(741283, 1.0, 1.0 + n / SR + 0.1), 150, SR, 2), 3600, SR, 2)
    a = A.reverb(fit(a, n), SR, t60=1.1, wet=0.22, seed=21, lp_hz=3500)
    a = at_lufs(a, -24.0)
    b = A.lp(A.hp(fs(407051, 10.0, 10.0 + n / SR + 0.1), 180, SR, 2), 2500, SR, 2)
    b = A.reverb(fit(b, n), SR, t60=1.4, wet=0.3, seed=22, lp_hz=3000)
    b = at_lufs(b, -31.0)
    return a + b


@amb("birds_evening", ["freesound:509682", "freesound:521558"],
     "sparse dusk birds: high-passed (1.2 kHz) bird bed from a Warsaw campus dusk recording (509682, 62-145 s) + "
     "seven blackbird phrases (521558) placed irregularly with varied level/pan and a little distance reverb", -27.0, 80.0, 3.0)
def birds_evening(n):
    bed = A.lp(A.hp(fs(509682, 62.0, 62.0 + n / SR + 0.1), 1200, SR, 4), 9000, SR, 2)
    bed = at_lufs(fit(bed, n), -36.0)
    y = bed.copy()
    bb = A.hp(fs(521558), 1300, SR, 4)
    ph = [e for e in events(bb, rise=18, gap=0.5) if 0.6 < e[1] - e[0] < 4.5]
    ph.sort(key=lambda e: -e[2])
    ph = ph[:7]
    rng = np.random.default_rng(4)
    times = [5.0, 15.5, 24.0, 35.5, 47.0, 58.5, 68.0]
    for k, (t0, t1, _) in enumerate(ph):
        seg = bb[int(t0 * SR):int(t1 * SR)]
        seg = A.fade(seg, SR, 0.02, 0.15)
        seg = width(seg, 0.6)
        seg = A.reverb(seg, SR, t60=1.3, wet=0.28, seed=40 + k, lp_hz=7000, keep_len=False)
        seg = at_lufs(seg, -29.0 - rng.uniform(0, 6))
        p = rng.uniform(-0.5, 0.5)
        seg = seg * np.array([np.cos((p + 1) * np.pi / 4), np.sin((p + 1) * np.pi / 4)]) * np.sqrt(2)
        A.place(y, seg, times[k % len(times)])
    return y


@amb("room_tone_large", ["freesound:454165", "freesound:144046"],
     "large convention-room tone with ventilation and a very distant crowd (454165) + low theatre control-room hum (144046) "
     "for weight; low-passed 6 kHz", -26.0, 66.0, 3.0)
def room_tone_large(n):
    a = A.lp(A.hp(fs(454165, 1.0, 70.5), 30, SR, 2), 6000, SR, 2)
    a = at_lufs(fit(a, n), -26.0)
    b = A.hp(fs(144046, 20.0, 20.0 + n / SR + 0.1), 30, SR, 2)
    b = at_lufs(fit(b, n), -31.0)
    return a + b


@amb("hvac", ["freesound:637804"], "office hallway with heavy ventilation (637804, 12-90 s), low-passed 7 kHz", -27.0, 75.0, 3.0)
def hvac(n):
    return A.lp(A.hp(fs(637804, 12.0, 12.0 + n / SR + 0.1), 30, SR, 2), 7000, SR, 2)


@amb("room_tone", ["freesound:203306", "freesound:144046"], "office room tone (203306) blended with a soft low hum (144046)", -28.0, 70.0, 3.0)
def room_tone(n):
    a = A.hp(fs(203306, 10.0, 10.0 + n / SR + 0.1), 30, SR, 2)
    a = at_lufs(fit(a, n), -28.0)
    b = A.hp(fs(144046, 50.0, 50.0 + n / SR + 0.1), 30, SR, 2)
    b = at_lufs(fit(b, n), -32.0)
    return A.lp(a + b, 8000, SR, 2)


@amb("lobby_murmur", ["freesound:733849"], "French crowd murmur in a big hall (733849), band-limited 120 Hz-6 kHz", -24.0, 62.0, 3.0)
def lobby_murmur(n):
    return A.lp(A.hp(fs(733849, 0.5, 0.5 + n / SR + 0.1), 120, SR, 2), 6000, SR, 2)


@amb("computer_room", ["freesound:455828"], "small room full of computer fans (455828, 20-98 s)", -25.0, 75.0, 3.0)
def computer_room(n):
    return A.hp(fs(455828, 20.0, 20.0 + n / SR + 0.1), 35, SR, 2)


@amb("keyboards", ["freesound:537473", "freesound:489424"],
     "sparse distant typing: 14 typing bursts (537473 laptop/keyboard, 489424 mechanical) at different distances "
     "(low-pass 2.5-6 kHz, room reverb, pan), with silent gaps", -27.0, 75.0, 3.0)
def keyboards(n):
    y = np.zeros((n, 2))
    src1 = A.hp(fs(537473, ch=1), 200, SR, 2)
    src2 = A.hp(A.lp(fs(489424, ch=1), 6000, SR, 2), 200, SR, 2)
    rng = np.random.default_rng(12)
    t = 4.0
    k = 0
    while t < 70.0:
        src = src1 if k % 3 else src2
        d = rng.uniform(1.0, 3.8)
        s0 = rng.uniform(2.0, A.dur(src) - d - 2.0)
        seg = src[int(s0 * SR):int((s0 + d) * SR)]
        seg = A.fade(seg, SR, 0.08, 0.4)
        dist = rng.uniform(0.3, 1.0)
        seg = A.lp(seg, 4500 - 2500 * dist, SR, 2)
        st = A.pan(seg, rng.uniform(-0.7, 0.7))
        st = A.reverb(st, SR, t60=0.7, wet=0.3 + 0.3 * dist, seed=60 + k, lp_hz=4000, keep_len=False)
        st = A.limit(at_lufs(st, -27.0 - 8.0 * dist), -14.0, circular=False)
        A.place(y, st, t)
        t += d + rng.uniform(0.8, 5.5)
        k += 1
    return y


@amb("cafeteria", ["freesound:625112", "freesound:128291", "kenney:impact-sounds (impactPlate_light, impactGlass_light, impactMetal_light)"],
     "canteen chatter (625112, Turkish university cafeteria) + far school-canteen layer (128291, low-passed 3.5 kHz) + "
     "soft scattered plate/glass/cutlery clinks (Kenney impact sounds, low-passed, reverb)", -23.0, 80.0, 3.0)
def cafeteria(n):
    a = A.lp(A.hp(fs(625112, 4.0, 4.0 + n / SR + 0.1), 120, SR, 2), 7000, SR, 2)
    a = at_lufs(fit(a, n), -23.5)
    b = A.lp(A.hp(fs(128291, 5.0, 5.0 + n / SR + 0.1), 150, SR, 2), 3500, SR, 2)
    b = A.reverb(fit(b, n), SR, t60=1.0, wet=0.25, seed=71, lp_hz=3500)
    b = at_lufs(b, -31.0)
    y = a + b
    files = sorted(glob.glob(os.path.join(KEN, "impact-sounds/Audio/impactPlate_light_*.ogg"))) + \
        sorted(glob.glob(os.path.join(KEN, "impact-sounds/Audio/impactGlass_light_*.ogg"))) + \
        sorted(glob.glob(os.path.join(KEN, "impact-sounds/Audio/impactMetal_light_*.ogg")))
    rng = np.random.default_rng(9)
    t = 5.0
    k = 0
    while t < 74.0:
        c = A.load(files[int(rng.integers(len(files)))], channels=1)
        c = A.resample_speed(c, rng.uniform(1.15, 1.6))
        c = A.lp(c, 7000, SR, 2)
        st = A.pan(c, rng.uniform(-0.8, 0.8))
        st = A.reverb(st, SR, t60=0.9, wet=0.35, seed=80 + k, lp_hz=6000, keep_len=False)
        st = st * A.undb(-24.0 - rng.uniform(0, 8) - A.peak_db(st))
        A.place(y, st, t)
        t += rng.uniform(1.5, 6.0)
        k += 1
    return y


@amb("fridge_hum", ["freesound:730438"], "vending machine cooling hum (730438, 2-52 s)", -28.0, 47.0, 3.0)
def fridge_hum(n):
    return A.hp(fs(730438, 2.0, 2.0 + n / SR + 0.1), 30, SR, 2)


@amb("basement_tone", ["freesound:451924"], "large church-basement room tone with deep ventilation/furnace hum (451924)", -27.0, 64.0, 3.0)
def basement_tone(n):
    return A.lp(A.hp(fs(451924, 1.0, 1.0 + n / SR + 0.1), 25, SR, 2), 6000, SR, 2)


@amb("under_music", ["incompetech:Raving Energy"],
     "muffled party music through a wall: a bar-aligned loop of Kevin MacLeod 'Raving Energy' (same track as music/under_party), folded to near-mono, "
     "low-passed (400 Hz + 900 Hz, 2nd order each), +3 dB at 90 Hz, small basement reverb", -24.0, None, None)
def under_music(_n):
    import audio_music as M
    M.TRACKS["under_wall"] = {"file": "Raving_Energy/Raving_Energy.mp3", "title": "Raving Energy", "bpm": 122, "bar": 4,
                              "len": (60, 90), "start": (40, 100)}
    x, r = M.analyze("under_wall", verbose=False)
    NOTES["under_music"]["note"] += " (loop %.2f-%.2f s, %d bars, waveform xcorr %.2f)" % (r["t1"], r["t1"] + r["L"], r["bars"], r["xcorr"])
    y = A.loopify(x, SR, length=r["L"], xfade=0.3, start=r["t1"])

    def wall(z):
        z = width(z, 0.25)
        z = A.lp(A.lp(z, 400, SR, 2), 900, SR, 2)
        z = A.peq(z, 90, 3.0, 0.9, SR)
        return A.reverb(z, SR, t60=0.9, wet=0.22, seed=91, lp_hz=1200)
    # every filter/reverb runs on a pre-rolled copy of the loop, so the seam stays continuous
    return A.circular(wall, y, pad_s=2.0), True


def build(stem):
    fn, target, length, xfade = BUILD[stem]
    if length is None:
        y, _ = fn(0)
        loop = y
    else:
        n = int((length + xfade) * SR)
        y = fn(n)
        loop = A.loopify(y, SR, length=length, xfade=xfade)
    loop = at_lufs(loop, target)
    for _ in range(2):  # tame rare transients (circular limiter keeps the seam intact), re-level
        if A.peak_db(loop) > -8.0:
            loop = at_lufs(A.limit(loop, -8.5, circular=True), target)
    path = os.path.join(OUTDIR, stem + ".ogg")
    A.save_ogg(path, loop, SR, q=4)
    sr = A.seam_report(loop)
    st = A.short_term(loop, win=3.0, hop=1.0)
    print("%-16s %.1fs I=%.1f peak=%.1f st(3s) %.1f..%.1f seam=%s" % (stem, A.dur(loop), A.lufs(loop), A.peak_db(loop), st.min(), st.max(), sr))
    return dict(NOTES[stem], dur=round(A.dur(loop), 2))


def main(argv):
    stems = argv or list(BUILD)
    man = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {}
    for s in stems:
        man[s] = build(s)
    with open(MANIFEST, "w") as f:
        json.dump(man, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
