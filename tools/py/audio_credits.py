"""Generate assets/audio/CREDITS.md from the build manifests, the Freesound licence records and verify.json.

python3.11 -I tools/py/audio_credits.py
"""
import json
import os
import re
from urllib.parse import unquote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "tools", "audio_src")
OUT = os.path.join(ROOT, "assets", "audio", "CREDITS.md")

KENNEY = {
    "impact-sounds": "https://kenney.nl/assets/impact-sounds",
    "rpg-audio": "https://kenney.nl/assets/rpg-audio",
}
CC0 = "CC0 1.0 (public domain)"
BY4 = "CC BY 4.0"


def load(name):
    p = os.path.join(SRC, name)
    return json.load(open(p)) if os.path.exists(p) else {}


def fsinfo(sid):
    return json.load(open(os.path.join(SRC, "freesound", str(sid), "info.json")))


def lic_name(d):
    l = d["licence"]
    if l.lower().startswith("creative commons 0"):
        return CC0
    return l


def src_cell(s, used):
    m = re.match(r"freesound:(\d+)", s)
    if m:
        d = fsinfo(int(m.group(1)))
        used.setdefault("fs", {})[d["id"]] = d
        return "[Freesound #%d \"%s\"](%s) by %s (%s)" % (d["id"], d["title"].replace("|", "/"), d["page"], unquote(d["user"]), lic_name(d))
    m = re.match(r"kenney:([\w-]+)[/ ]?(.*)", s)
    if m:
        pack = m.group(1)
        used.setdefault("kenney", set()).add(pack)
        detail = m.group(2).replace("Audio/", "").strip(" ()")
        return "[Kenney %s](%s)%s by Kenney (%s)" % (pack, KENNEY.get(pack, "https://kenney.nl"), (" - " + detail) if detail else "", CC0)
    m = re.match(r"incompetech:(.+)", s)
    if m:
        t = m.group(1)
        used.setdefault("km", set()).add(t)
        return "[\"%s\"](https://incompetech.com/music/royalty-free/mp3-royaltyfree/%s.mp3) by Kevin MacLeod (%s)" % (t, t.replace(" ", "%20"), BY4)
    if s == "synth":
        return "original synthesis for this game (`tools/py/audio_sfx.py`, %s)" % CC0
    return s


def fmt_row(v):
    if v is None:
        return ""
    lufs = "" if v["lufs"] in (float("-inf"),) or v["lufs"] <= -69 else ", %.1f LUFS" % v["lufs"]
    return "%.2f s%s, peak %.1f dBFS" % (v["dur"], lufs, v["peak"])


def main():
    ver = {r["file"]: r for r in load("verify.json")}
    sfx = load("sfx_manifest.json")
    amb = load("amb_manifest.json")
    mus = load("music_manifest.json")
    fst = load("footsteps_report.json")
    used = {}
    L = []
    A = L.append
    A("# Audio credits - Mano & the Lost AirPod")
    A("")
    A("Every file the game loads from `assets/audio/` is listed below with its source(s), author, licence and the edits made.")
    A("Format: OGG Vorbis 44.1 kHz; footsteps and one-shots mono, ambience and music stereo.")
    A("Ambience and music are imported with `loop=true` (see their `.ogg.import`); one-shots/footsteps play once.")
    A("Build scripts: `tools/py/audio_*.py` (raw downloads in `tools/audio_src/`, not shipped).")
    A("")
    A("## Attribution required (must appear in the game's credits)")
    A("")
    A("All music is by Kevin MacLeod, licensed CC BY 4.0. Use these lines verbatim in the in-game credits:")
    A("")
    titles = sorted({v["title"] for v in mus.values()})
    for t in titles:
        A("- \"%s\" Kevin MacLeod (incompetech.com)  Licensed under Creative Commons: By Attribution 4.0 License  "
          "http://creativecommons.org/licenses/by/4.0/" % t)
    A("")
    A("Everything else is CC0 (Freesound uploads listed below, Kenney packs, or synthesised for this game); no attribution "
      "is legally required, but credit is given here anyway. Suggested optional line: *Sound effects: Kenney (kenney.nl) "
      "and Freesound contributors (see CREDITS.md).*")
    A("")
    A("## Music (`music/`, -18 LUFS integrated)")
    A("")
    A("| File | Source | Duration / loudness / peak | What was done |")
    A("|---|---|---|---|")
    for stem in ["title", "explore", "explore_dusk", "tension", "under_party", "ending"]:
        v = mus.get(stem)
        if not v:
            continue
        A("| `music/%s.ogg` | %s | %s | %s |" % (stem, src_cell("incompetech:" + v["title"], used), fmt_row(ver.get("music/%s.ogg" % stem)), v["processing"]))
    A("")
    A("## Ambience loops (`amb/`, seamless)")
    A("")
    A("Each loop: the audio just after the loop end is equal-power crossfaded into the head (2-3 s), so the last sample "
      "flows into the first; static gain to the target loudness; a gentle wrap-around peak limiter at -8.5 dBFS only where "
      "rare transients exceeded it.")
    A("")
    A("| File | Sources | Duration / loudness / peak | What was done |")
    A("|---|---|---|---|")
    for stem, v in amb.items():
        cells = "<br>".join(src_cell(s, used) for s in v["sources"])
        A("| `amb/%s.ogg` | %s | %s | %s; target %.0f LUFS |" % (stem, cells, fmt_row(ver.get("amb/%s.ogg" % stem)), v["note"], v["target_lufs"]))
    A("")
    A("## One-shots (`sfx/`, mono, peak about -3 dBFS)")
    A("")
    A("Numbered variants (`machine_shake_1..3`, `babyfoot_kick_1..3`) are picked at random by `Sfx._load`.")
    A("")
    A("| File | Sources | Duration / loudness / peak | What was done |")
    A("|---|---|---|---|")
    for stem in sorted(sfx):
        v = sfx[stem]
        cells = "<br>".join(src_cell(s, used) for s in v["sources"])
        tail = "" if stem == "coffee_machine" else "; start trimmed to the first transient, tail faded, peak-normalised"
        A("| `sfx/%s.ogg` | %s | %s | %s%s |" % (stem, cells, fmt_row(ver.get("sfx/%s.ogg" % stem)), v["note"], tail))
    A("")
    A("## Footsteps (`footsteps/`, mono, single sneaker steps < 0.5 s)")
    A("")
    A("Each step was sliced from a walking recording at the transient (2 ms lead-in), high-passed (50-70 Hz), cut where it "
      "decays 38 dB under its peak (or before the next step) with a short fade-out, then level-matched inside its set "
      "(RMS of the first 120 ms: -27 dBFS for concrete/tile/rubber, -27.5 wood, -29.5 grass, -31 carpet; peaks <= -6 dBFS).")
    A("")
    A("| Files | Source | Source times (s) | Peaks |")
    A("|---|---|---|---|")
    for surf in ["concrete", "tile", "carpet", "wood", "rubber", "grass"]:
        rows = fst.get(surf, [])
        by_src = {}
        for r in rows:
            by_src.setdefault(r["src"], []).append(r)
        for sid, rs in by_src.items():
            names = ", ".join("`%s`" % os.path.basename(r["file"]) for r in rs)
            A("| %s | %s | %s | %s dBFS |" % (names, src_cell("freesound:%d" % sid, used), ", ".join("%.2f" % r["t"] for r in rs),
                                            " / ".join("%.1f" % ver.get(r["file"], {"peak": r["peak"]})["peak"] for r in rs)))
    A("")
    A("## Source index")
    A("")
    A("### Freesound (HQ previews, downloaded without login; licence checked on each sound page)")
    A("")
    for sid in sorted(used.get("fs", {})):
        d = used["fs"][sid]
        A("- #%d \"%s\" by **%s** - %s - %s" % (sid, d["title"], unquote(d["user"]), lic_name(d), d["page"]))
    A("")
    A("### Kenney (CC0, https://kenney.nl)")
    A("")
    for p in sorted(used.get("kenney", [])):
        A("- %s - %s - Creative Commons Zero (CC0)" % (p, KENNEY.get(p, "https://kenney.nl")))
    A("")
    A("### Kevin MacLeod (incompetech.com, CC BY 4.0)")
    A("")
    for t in sorted(used.get("km", set()) | set(titles)):
        A("- \"%s\" - https://incompetech.com/music/royalty-free/mp3-royaltyfree/%s.mp3" % (t, t.replace(" ", "%20")))
    A("")
    open(OUT, "w").write("\n".join(L))
    print("wrote", OUT, len(L), "lines")


if __name__ == "__main__":
    main()
