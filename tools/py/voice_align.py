"""Find where each line starts in a multi-line voice take, and check every line was said (a listen-proxy).

  python3.11 tools/py/voice_align.py [job_id ...]     # all jobs in tools/audio_src/voice/jobs.json by default

Whisper (small.en, local) transcribes the take with word timings; the words are matched to the lines the job asked
for (difflib), and each cut goes in the quietest 10 ms inside the gap between one line's last word and the next
line's first. The cuts (seconds) and a per-line check {heard, match} are written back into jobs.json, so
voice_build.py needs no whisper. `match` is the share of the line's words heard in order (1.0 = all).
"""
import difflib
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audio_lib as A  # noqa: E402
import voice_build as VB  # noqa: E402

NUM = {"42": "forty two", "37": "thirty seven", "72": "seventy two", "3": "three", "14": "fourteen", "8": "eight",
       "9": "nine", "12": "twelve"}


def words(t):
    t = t.lower().replace("-", " ")
    out = []
    for w in re.findall(r"[a-z0-9']+", t):
        w = w.strip("'")
        out += NUM.get(w, w).split()
    return out


def main():
    import whisper
    jobs = json.load(open(VB.JOBS))
    lines = {r["key"]: r for r in json.load(open(VB.LINES))}
    ids = sys.argv[1:] or list(jobs)
    model = whisper.load_model("small.en")
    for jid in ids:
        j = jobs[jid]
        wav = os.path.join(VB.RAW, jid + ".wav")
        x = A.load(wav, channels=1)
        x16 = A.load(wav, channels=1, sr=16000).astype(np.float32)
        texts = [lines[k]["spoken"] for k in j["keys"]]
        # no initial prompt: what whisper hears must not be steered towards the expected words
        r = model.transcribe(x16, fp16=False, word_timestamps=True, condition_on_previous_text=False)
        heard = [(w, s["start"], s["end"]) for seg in r["segments"] for s in seg.get("words", []) for w in words(s["word"])]
        exp, owner = [], []
        for i, t in enumerate(texts):
            for w in words(t):
                exp.append(w)
                owner.append(i)
        sm = difflib.SequenceMatcher(a=exp, b=[h[0] for h in heard], autojunk=False)
        hit = {}
        for a, b, n in sm.get_matching_blocks():
            for k in range(n):
                hit[a + k] = b + k
        cuts = []
        hop = int(A.SR * 0.01)
        for i in range(len(texts) - 1):
            last = [hit[e] for e in range(len(exp)) if owner[e] == i and e in hit]
            first = [hit[e] for e in range(len(exp)) if owner[e] == i + 1 and e in hit]
            if not last or not first:
                raise SystemExit("%s: cannot place the cut after line %d" % (jid, i))
            t0, t1 = heard[max(last)][2], heard[min(first)][1]
            if t1 <= t0:
                t1 = t0 + 0.02
            a, b = int(t0 * A.SR), int(t1 * A.SR)
            seg = x[a:b]
            if len(seg) > hop * 2:
                n = len(seg) // hop
                e = np.mean(seg[:n * hop].reshape(n, hop) ** 2, axis=1)
                # the quietest stretch of the gap, nearer its middle on ties
                k = int(np.argmin(e + 1e-9 * np.abs(np.arange(n) - n / 2)))
                cuts.append(round((a + k * hop + hop // 2) / A.SR, 3))
            else:
                cuts.append(round((t0 + t1) / 2, 3))
        j["cuts"] = cuts
        check = []
        for i, t in enumerate(texts):
            ew = [e for e in range(len(exp)) if owner[e] == i]
            got = [heard[hit[e]][0] for e in ew if e in hit]
            lo = cuts[i - 1] if i else 0.0
            hi = cuts[i] if i < len(cuts) else 1e9
            said = " ".join(h[0] for h in heard if lo <= (h[1] + h[2]) / 2 < hi)
            check.append({"key": j["keys"][i], "match": round(len(got) / max(len(ew), 1), 2), "heard": said})
        j["check"] = check
        print(jid, j["speaker"], "cuts", cuts)
        for c in check:
            print("   %.2f  %-20s %s" % (c["match"], c["key"], c["heard"]))
    json.dump(jobs, open(VB.JOBS, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
