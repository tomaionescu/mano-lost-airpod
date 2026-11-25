"""Voice lines for the fictional NPCs: inventory, job plan, and the build from Higgsfield takes.

The friends get no synthetic voice: lines they record themselves go through the same `build` step. The inner voice
(`nar`) is never voiced.

  python3.11 tools/py/voice_build.py lines    # tools/out/voices/cards.json -> tools/out/voices/lines.json
  python3.11 tools/py/voice_build.py plan     # cost of tools/audio_src/voice/plan.json's jobs, and the cards no take covers
  python3.11 tools/py/voice_build.py build    # raw takes -> assets/audio/voice/<key>.ogg + manifest.json
  python3.11 tools/py/voice_build.py build KEY...   # only those cards (the rest of the manifest is kept as it is)

cards.json comes from `Godot --headless --path . res://scenes/dev/voice_lines.tscn` (every card story.gd can show).
A card's key is VoiceLines.key(): speaker id + "_" + sha1("<speaker>|<exact card text>")[:10], where the speaker
is the voice's id (VoiceLines.ALIAS: crowd models by build, Mme Dupont's two spots). A changed line finds no file
and stays silent.

Takes: tools/audio_src/voice/jobs.json lists every Higgsfield job {job_id: {speaker, keys: [...], prompt, ...}};
the wav is tools/audio_src/voice/raw/<job_id>.wav. A job may speak several cards of one voice (one line each,
newline-separated: Qwen bills per job, rounded up to 23 characters), and `build` cuts it at the pauses between them.
"""
import hashlib
import json
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audio_lib as A  # noqa: E402

ROOT = A.ROOT
CARDS = os.path.join(ROOT, "tools", "out", "voices", "cards.json")
LINES = os.path.join(ROOT, "tools", "out", "voices", "lines.json")
SRC = os.path.join(ROOT, "tools", "audio_src", "voice")
RAW = os.path.join(SRC, "raw")
JOBS = os.path.join(SRC, "jobs.json")
OUT = os.path.join(ROOT, "assets", "audio", "voice")
MANIFEST = os.path.join(OUT, "manifest.json")
ENV_RATE = 30.0
TARGET_LUFS = -18.0
PEAK_DB = -3.0
# quieter by design: a sleeper's mumble, a whisper in a silent computer room (dB from TARGET_LUFS)
QUIET = {"sleeper": -7.0, "ines": -4.0}

FRIENDS = {"nar", "mano", "toma", "ian", "joaquin", "anisha", "silvia", "ishita", "cristina"}
# same table as VoiceLines.ALIAS (scripts/story/voice.gd)
ALIAS = {"madame2": "madame", "crowd1": "crowd_m", "crowd3": "crowd_m", "crowd5": "crowd_m", "crowd7": "crowd_m",
         "crowd2": "crowd_f", "crowd4": "crowd_f", "crowd6": "crowd_f", "crowd8": "crowd_f"}

# Lines shown outside story.gd's dialogue cards (the lost & found minigame's replies, scripts/minigames/lostfound.gd).
EXTRA = [
    ("madame2", "Mme Dupont", "...yes. That one. Gross."),
    ("madame2", "Mme Dupont", "That one belongs to a SPE student who doesn't chew things. Respectable."),
    ("madame2", "Mme Dupont", "That's a W, Mano. Did you sleep through the alphabet too?"),
    ("madame2", "Mme Dupont", "A 42 sticker? Mano. Have some respect for your school."),
    ("madame2", "Mme Dupont", "Touch that and the ACUs will give you -42. For life."),
    ("madame2", "Mme Dupont", "That's the director's. Put it DOWN. Slowly."),
]

# What the voice says where the card's text would read badly aloud (stage directions, shouting caps, numbers).
SPOKEN = {
    "M scratch, chewed stem... gross. Yes, that one is yours.": "Em scratch, chewed stem... gross. Yes, that one is yours.",
    "*sips coffee* Wonderful. Now leave.": "Wonderful. Now leave.",
    "*sips coffee* Not my problem, sweetie.": "Not my problem, sweetie.",
    "The machine ate my coins and I have NOT had my coffee.": "The machine ate my coins and I have not had my coffee.",
    "No coffee, no lost & found. That is the law.": "No coffee, no lost and found. That is the law.",
    "Lost something? Tell me WHO brought it here and maybe I'll look.": "Lost something? Tell me who brought it here, and maybe I'll look.",
    "You have money. The machine is RIGHT THERE.": "You have money. The machine is right there.",
    "zzz... segmentation fault (core dumped)... zzz": "Mmh... segmentation fault... core dumped...",
    "Remember: cheating is -42. Losing AirPods is just sad.": "Remember: cheating is minus forty-two. Losing AirPods is just sad.",
    "Touch that and the ACUs will give you -42. For life.": "Touch that and the ACUs will give you minus forty-two. For life.",
    "That's the director's. Put it DOWN. Slowly.": "That's the director's. Put it down. Slowly.",
    "I've been in SM14 since 8:00.": "I've been in S M fourteen since eight.",
    "I have been waiting for the accueil since 9:00.": "I have been waiting for the accueil since nine.",
    "...WHAT. Nobody beats me at babyfoot.": "...What. Nobody beats me at babyfoot.",
    "HAHAHA. BDE champion, baby.": "Ha ha ha! B.D.E. champion, baby.",
    # digits: with language "fr" Qwen reads them in French ("trente-sept"), so they are spelled out
    "Students lose about 37 AirPods a week here.": "Students lose about thirty-seven AirPods a week here.",
    "But I'm a fair man. Beat me at babyfoot. First to 3.": "But I'm a fair man. Beat me at babyfoot. First to three.",
    "The salle machine smells like 72 hours of piscine.": "The salle machine smells like seventy-two hours of piscine.",
    "A 42 sticker? Mano. Have some respect for your school.": "A forty-two sticker? Mano. Have some respect for your school.",
    "Take? I FOUND it. Finders keepers. BDE rules.": "Take? I found it. Finders keepers. B.D.E. rules.",
}


def key(who, text):
    s = ALIAS.get(who, who)
    return s + "_" + hashlib.sha1((s + "|" + text).encode("utf-8")).hexdigest()[:10]


def spoken(text):
    t = SPOKEN.get(text, text).replace(" & ", " and ")
    return re.sub(r"\*[^*]*\*\s*", "", t).strip()


def cost(n_chars):
    """qwen_audio_tts: 0.01 credit per started 23 characters, per job."""
    return math.ceil(n_chars / 23) * 0.01


# ------------------------------------------------------------------ lines
def cmd_lines():
    cards = json.load(open(CARDS))
    rows, seen = [], {}
    for c in cards + [{"speaker": s, "name": n, "text": t} for s, n, t in EXTRA]:
        if c["speaker"] in FRIENDS:
            continue
        k = key(c["speaker"], c["text"])
        if k in seen:
            if c["speaker"] not in seen[k]["who"]:
                seen[k]["who"].append(c["speaker"])
            continue
        r = {"key": k, "speaker": ALIAS.get(c["speaker"], c["speaker"]), "who": [c["speaker"]], "name": c["name"],
             "text": c["text"], "spoken": spoken(c["text"])}
        seen[k] = r
        rows.append(r)
    extra = {t for _, _, t in EXTRA}
    for r in rows:
        r["source"] = "scripts/minigames/lostfound.gd" if r["text"] in extra else "scripts/story/story.gd"
    rows.sort(key=lambda r: (r["speaker"], r["key"]))
    os.makedirs(os.path.dirname(LINES), exist_ok=True)
    json.dump(rows, open(LINES, "w"), indent=1, ensure_ascii=False)
    n = sum(len(r["spoken"]) for r in rows)
    print("%d voiced cards (%d characters spoken) -> %s" % (len(rows), n, os.path.relpath(LINES, ROOT)))


# ------------------------------------------------------------------ plan
def cmd_plan():
    """plan.json: {voices: {speaker: {voice_id, voice_name, instruction, language}}, jobs: [{speaker, keys}]}."""
    lines = {r["key"]: r for r in json.load(open(LINES))}
    plan = json.load(open(os.path.join(SRC, "plan.json")))
    jobs = json.load(open(JOBS)) if os.path.exists(JOBS) else {}
    have = {k for j in jobs.values() if not j.get("skip") for k in j["keys"] if k not in j.get("drop", [])}
    total = 0.0
    for j in plan["jobs"]:
        prompt = "\n".join(lines[k]["spoken"] for k in j["keys"])
        todo = [k for k in j["keys"] if k not in have]
        total += cost(len(prompt)) if todo else 0.0
        print("%-9s %-8s %3d chars %.2f  %s" % (j["speaker"], plan["voices"][j["speaker"]]["voice_name"], len(prompt),
                                               cost(len(prompt)), "done" if not todo else "TODO %d" % len(todo)))
    missing = [k for k in lines if k not in have]
    print("cards without a take: %d (%s); jobs still to run: about %.2f credits" % (len(missing), ", ".join(missing), total))


# ------------------------------------------------------------------ build
def _frames_db(x, sr, hop):
    n = len(x) // hop
    f = x[:n * hop].reshape(n, hop)
    return 10 * np.log10(np.mean(f ** 2, axis=1) + 1e-12)


def split_take(x, sr, texts):
    """Cut a take that speaks len(texts) lines in order at the pauses between them. Candidate cuts are silent runs
    (>= 140 ms, 35 dB under the take's loud frames); the chosen N-1 maximise pause length while keeping each piece's
    duration close to its share of the characters. Returns [(start, end)] in samples."""
    n = len(texts)
    if n == 1:
        return [(0, len(x))]
    hop = int(sr * 0.01)
    e = _frames_db(x, sr, hop)
    loud = np.percentile(e, 95)
    quiet = e < loud - 35
    runs, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if j - i >= 14 and i > 0 and j < len(quiet):
                runs.append(((i + j) // 2, j - i))
            i = j
        else:
            i += 1
    if len(runs) < n - 1:
        raise ValueError("only %d pauses for %d lines" % (len(runs), n))
    w = np.array([len(t) + 6.0 for t in texts])
    total = len(e)
    want = np.cumsum(w)[:-1] / w.sum() * total   # expected boundary frames
    # DP: pick runs r_1 < ... < r_{n-1}; score = sum(log pause) - k * ((pos - want) / total)^2
    m = len(runs)
    best = np.full((n - 1, m), -1e18)
    back = np.zeros((n - 1, m), dtype=int)
    for b in range(n - 1):
        for c in range(m):
            pos, ln = runs[c]
            s = math.log(ln) - 60.0 * ((pos - want[b]) / total) ** 2
            if b == 0:
                best[b, c] = s
            else:
                prev = best[b - 1, :c]
                if len(prev) == 0:
                    continue
                k = int(np.argmax(prev))
                best[b, c] = prev[k] + s
                back[b, c] = k
    c = int(np.argmax(best[n - 2]))
    cuts = []
    for b in range(n - 2, -1, -1):
        cuts.append(runs[c][0] * hop)
        c = back[b, c]
    cuts = cuts[::-1]
    edges = [0] + cuts + [len(x)]
    return [(edges[i], edges[i + 1]) for i in range(n)]


def trim(x, sr, floor=-45.0, lead=0.04, tail=0.12, speech=-30.0, hold=0.03, gap=0.2):
    """Cut to the line: `lead` before its first sound, `tail` after its last. The first sound is the start of the
    run (pauses under `gap` bridged) that leads into the first `hold` within `speech` dB of the loud frames, so the
    low thump or click a Qwen take opens with, ~0.3 s before the first word, is not taken for it."""
    hop = int(sr * 0.005)
    e = _frames_db(x, sr, hop)
    ref = np.percentile(e, 97)
    on = np.nonzero(e > ref + floor)[0]
    if len(on) == 0:
        return x
    w = max(1, int(round(hold * sr / hop)))
    held = np.nonzero(np.lib.stride_tricks.sliding_window_view(e, w).min(axis=1) > ref + speech)[0] \
        if len(e) >= w else []
    first = int(held[0]) if len(held) else int(on[0])
    before = on[on < first][::-1]
    for i in before:
        if (first - i - 1) * hop > gap * sr:
            break
        first = int(i)
    a = max(0, first * hop - int(lead * sr))
    b = min(len(x), (on[-1] + 1) * hop + int(tail * sr))
    return A.fade(x[a:b], sr, 0.006, 0.05)


def envelope(x, sr):
    """Jaw opening at ENV_RATE Hz: frame RMS mapped from 38 dB under the line's loud frames (closed) to its peak
    (0.85 open), with a slight curve so quiet consonants barely move the jaw."""
    hop = int(sr / ENV_RATE)
    e = _frames_db(x, sr, hop)
    top = np.percentile(e, 95)
    v = np.clip((e - (top - 38.0)) / 38.0, 0.0, 1.0) ** 1.6 * 0.85
    return [round(float(a), 3) for a in v]


def level(y, target=TARGET_LUFS):
    """About -18 LUFS with true peaks at most -3 dBFS: gain to the target, then a fast lookahead peak limiter on
    the few syllables above the ceiling (speech crest factors are 15-20 dB); at most 6 dB of limiting, the rest
    stays quieter."""
    for _ in range(3):
        g = target - A.lufs(y, A.SR)
        y = y * A.undb(g)
        pre = A.peak_db(y)
        y = A.limit(y, PEAK_DB - 0.6, look=0.003, release=0.08, sr=A.SR, circular=False)
        if pre - A.peak_db(y) > 6.0:
            y = y * A.undb(-(pre - A.peak_db(y) - 6.0))
            break
    tp = A.true_peak_db(y, A.SR)
    if tp > PEAK_DB:
        y = y * A.undb(PEAK_DB - tp)
    return y


def cmd_build():
    lines = {r["key"]: r for r in json.load(open(LINES))}
    jobs = json.load(open(JOBS))
    only = set(sys.argv[2:])
    unknown = only - set(lines)
    if unknown:
        raise SystemExit("no such card: " + ", ".join(sorted(unknown)))
    manifest = {}
    if os.path.exists(MANIFEST):
        manifest = json.load(open(MANIFEST))
    report = []
    for job_id, j in jobs.items():
        wav = os.path.join(RAW, job_id + ".wav")
        if not os.path.exists(wav) or j.get("skip") or (only and not only & (set(j["keys"]) - set(j.get("drop", [])))):
            continue
        x = A.load(wav, channels=1)
        texts = [lines[k]["spoken"] for k in j["keys"]]
        spans = split_take(x, A.SR, texts) if "cuts" not in j else \
            [(int(a * A.SR), int(b * A.SR)) for a, b in zip([0] + j["cuts"], j["cuts"] + [len(x) / A.SR])]
        for k, (a, b) in zip(j["keys"], spans):
            if k in j.get("drop", []) or (only and k not in only):
                continue
            y = trim(x[a:b], A.SR)
            y = level(A.hp(y, 70, A.SR, order=2), TARGET_LUFS + QUIET.get(lines[k]["speaker"], 0.0))
            path = os.path.join(OUT, k + ".ogg")
            A.save_ogg(path, y, A.SR, q=5)
            r = lines[k]
            manifest[k] = {"speaker": r["speaker"], "text": r["text"], "file": k + ".ogg",
                           "seconds": round(len(y) / A.SR, 3), "job": job_id, "env": envelope(y, A.SR)}
            report.append((k, len(y) / A.SR, A.lufs(y, A.SR), A.true_peak_db(y, A.SR), r["spoken"]))
    os.makedirs(OUT, exist_ok=True)
    json.dump(dict(sorted(manifest.items())), open(MANIFEST, "w"), indent=1, ensure_ascii=False)
    for k, d, l, p, t in report:
        print("%-22s %5.2f s %6.1f LUFS %5.1f dBTP  %s" % (k, d, l, p, t))
    print("%d files, manifest -> %s" % (len(manifest), os.path.relpath(MANIFEST, ROOT)))


if __name__ == "__main__":
    {"lines": cmd_lines, "plan": cmd_plan, "build": cmd_build}[sys.argv[1] if len(sys.argv) > 1 else "lines"]()
