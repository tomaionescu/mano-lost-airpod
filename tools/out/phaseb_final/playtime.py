"""A playtime estimate for the main path from a walk.gd log (python3 playtime.py <sl_walk.log>).

Per chapter, for a first-time player who reads every card:
  reading   = cards x 0.8 s (to see the card and press) + characters / 15 per second (subtitles, relaxed)
  walking   = metres walked / the jog speed x 1.4 (looking round, a wrong turn, slowing at doors), + 15 s for each leg
              the harness could not walk (the amphi's tiers, the stair ramp)
  minigames = MINI below (a first play; the design's ranges and the minigame autotests' real-key runs)
  cutscenes = as measured (cold open, dream, chapter cards; the credits at their full 46 s), and the holds inside
              talks (`$ wait`, framed shots, song previews) as measured
  the phone = 60 s for the first read of the flood, 15 s for each later look
Low and high: a player who jogs straight there, reads at 20 characters a second and is quick at the minigames, and one
who walks everywhere, reads at 12 and takes 1.3 x as long at the minigames.
v1 by the same formula: its 58 critical-path cards at v1's mean card length (tests/fixtures/v1_cards.json), chapter 1
and 2's walking without the planter wall, its four minigames, the dream and the wake-up.
"""
import json, os, re, sys

MINI = {"moulinette": 90, "babyfoot": 150, "coffee": 30, "lostfound": 60, "kebab": 90, "findmy": 100, "soleil": 60}
JOG, WALK, CREDITS = 3.23, 1.49, 46
stats = {}
for line in open(sys.argv[1], errors="replace"):
    m = re.search(r"\[walk\] STATS c(\d+): walk (\d+) s \((\d+) m, (\d+) s at walking pace\), talk (\d+) s, cut (\d+) s, "
                  r"mini (\d+) s \[(.*?)\], sit (\d+) s, cards (\d+) \(think (\d+)\), chars (\d+), stuck (\d+), nudges (\d+), "
                  r"fallbacks (\d+), phone (\d+)(?:, holds (\d+) s)?", line)
    if m:
        g = m.groups()
        stats[int(g[0])] = dict(m=int(g[2]), cut=int(g[5]), minis=[x.strip().strip('"') for x in g[7].split(",") if x.strip()],
                                cards=int(g[9]), chars=int(g[11]), fallbacks=int(g[14]), phone=int(g[15]), hold=int(g[16] or 0))


def est(s, cps, walk_k, mini_k, credits):
    read = s["cards"] * (0.8 if cps <= 15 else 0.6) + s["chars"] / cps
    walk = s["m"] / (WALK if walk_k == 0 else JOG) * (walk_k or 1.0) + 15 * s["fallbacks"]
    mini = sum(MINI.get(mg, 60) for mg in s["minis"]) * mini_k
    phone = (60 * min(s["phone"], 1) + 15 * max(s["phone"] - 1, 0)) * (0.5 if cps > 15 else 1.0)
    return read, walk, mini, s["cut"] + s["hold"] + credits, phone


tot = [0.0, 0.0, 0.0]
print("ch | cards | chars | read s | walk m | walk s | minigames | mini s | cutscenes s | phone s | min | low | high")
for c in sorted(stats):
    s = stats[c]
    cr = CREDITS - 11 if c == 5 else 0   # the harness left the credits after 11 s
    mid = est(s, 15, 1.4, 1.0, cr)
    low = est(s, 20, 1.0, 0.7, cr)
    high = est(s, 12, 0, 1.3, cr)
    for k, e in enumerate((mid, low, high)):
        tot[k] += sum(e)
    print("%d | %d | %d | %.0f | %d | %.0f | %s | %.0f | %.0f | %.0f | %.1f | %.1f | %.1f" % (c, s["cards"], s["chars"], mid[0], s["m"], mid[1],
          "+".join(s["minis"]) or "-", mid[2], mid[3], mid[4], sum(mid) / 60, sum(low) / 60, sum(high) / 60))
print("v2 main path: %.1f min (low %.1f, high %.1f)" % (tot[0] / 60, tot[1] / 60, tot[2] / 60))

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
v1 = json.load(open(os.path.join(root, "tests", "fixtures", "v1_cards.json")))
mean = sum(len(c["text"]) for c in v1) / len(v1)
if 1 in stats and 2 in stats:
    metres = stats[1]["m"] + stats[2]["m"] - 60          # no planter wall
    read = 58 * 0.8 + 58 * mean / 15
    walk = metres / JOG * 1.4 + 15 * 2                   # the amphi's tiers, the stairs
    mini = MINI["moulinette"] + MINI["babyfoot"] + MINI["coffee"] + MINI["lostfound"]
    print("v1 main path, same formula: %.1f min (58 cards of %.1f characters: %.0f s; %d m: %.0f s; minigames %d s; dream and wake-up 20 s)"
          % ((read + walk + mini + 20) / 60, mean, read, metres, walk, mini))
