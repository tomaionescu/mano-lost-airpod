"""Mano's algo notebook, open on the desk in the opening's wake-up shot (docs/DESIGN.md §7) -> assets/textures/notebook_algo/.

python3.11 -I tools/py/notebook_tex.py
- notebook_algo.png  2040x1320 RGB: a small Seyès cahier (17 x 22 cm a page) open on two pages, 6 px per mm.
  Left page: today's date in red, the Dijkstra notes in his ballpoint (Mynerve, the UI's `pen` voice), and the line
  he was writing when he fell asleep sliding off down the page. Right page: the example graph with the shortest path
  gone over in red, and a tiny earbud in the margin. The gutter darkens toward the middle (the pages curve into it).
Used by scripts/level/algo_notebook.gd (UV u across both pages, v from the top edge). Deterministic.
"""
import math
import os
import random
import sys

sys.path.append(os.path.expanduser("~/Library/Python/3.11/lib/python/site-packages"))
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "assets", "textures", "notebook_algo")
FONT = os.path.join(ROOT, "assets", "fonts", "Mynerve-Regular.ttf")

PX = 6                      # pixels per mm
PAGE_W, PAGE_H = 170, 220   # mm
W, H = 2 * PAGE_W * PX, PAGE_H * PX
SS = 2                      # supersampling for the ink

PAPER = (250, 248, 242)
SEYES_LINE = (185, 175, 221)
SEYES_INTER = (203, 216, 238)
MARGIN_RED = (224, 96, 90)
INK_BLUE = (35, 62, 148)
INK_RED = (194, 48, 43)

R = random.Random(15)


def mm(v):
    return int(round(v * PX * SS))


def seyes(d, x0):
    """Seyès ruling on the page starting at x0 (mm): 8 mm squares, three fine lines between, margin at 34 mm."""
    top = 24.0
    y = top
    while y < PAGE_H - 4:
        for k in range(1, 4):
            yy = y + 2.0 * k
            if yy < PAGE_H - 4:
                d.line([(mm(x0), mm(yy)), (mm(x0 + PAGE_W), mm(yy))], fill=SEYES_INTER, width=SS)
        d.line([(mm(x0), mm(y)), (mm(x0 + PAGE_W), mm(y))], fill=SEYES_LINE, width=2 * SS)
        y += 8.0
    x = x0 + 34.0 + 8.0
    while x < x0 + PAGE_W - 2:
        d.line([(mm(x), mm(top)), (mm(x), mm(PAGE_H - 4))], fill=SEYES_INTER, width=SS)
        x += 8.0
    d.line([(mm(x0 + 34.0), 0), (mm(x0 + 34.0), mm(PAGE_H))], fill=MARGIN_RED, width=2 * SS)


def line_y(n):
    """baseline of the n-th major line (from 0)"""
    return 24.0 + 8.0 * n


def write(d, text, x, n, size=7.4, color=INK_BLUE, wobble=0.25):
    """handwriting on major line n, starting x mm, letter by letter with a slight drift"""
    font = ImageFont.truetype(FONT, mm(size))
    cx = mm(x)
    base = mm(line_y(n) - 0.6)
    for ch in text:
        dy = R.uniform(-wobble, wobble)
        d.text((cx, base + mm(dy)), ch, font=font, fill=color, anchor="ls")
        cx += font.getlength(ch) * R.uniform(0.97, 1.02)
    return cx / (PX * SS)


def stroke(d, pts, color=INK_BLUE, w=0.45):
    d.line([(mm(x), mm(y)) for x, y in pts], fill=color, width=max(1, mm(w)), joint="curve")


def circle(d, cx, cy, r, color=INK_BLUE, w=0.45, turns=1.08):
    n = 40
    a0 = R.uniform(0, math.tau)
    pts = []
    for i in range(int(n * turns) + 1):
        a = a0 + math.tau * i / n
        rr = r * (1.0 + 0.04 * math.sin(3 * a))
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a) * 0.95))
    stroke(d, pts, color, w)


def left_page(d):
    x0 = 0
    write(d, "jeudi 15 octobre", x0 + 112, 0, 6.4, INK_RED)
    end = write(d, "Plus courts chemins : Dijkstra", x0 + 38, 2, 8.2)
    stroke(d, [(x0 + 38, line_y(2) + 1.6), (end, line_y(2) + 1.2)], INK_RED, 0.5)
    lines = [
        (40, "d[s] = 0, d[v] = inf sinon"),
        (40, "Q = tas(G.V)"),
        (40, "tant que Q non vide :"),
        (48, "u = extract_min(Q)"),
        (48, "pour (u, v, w) dans adj[u] :"),
        (56, "si d[u] + w < d[v] :"),
        (64, "d[v] = d[u] + w"),
    ]
    n = 4
    for x, t in lines:
        write(d, t, x0 + x, n)
        n += 1
    end = write(d, "O((V + E) log V)", x0 + 40, n + 1)
    stroke(d, [(x0 + 38.5, line_y(n + 1) - 7), (end + 1.5, line_y(n + 1) - 7), (end + 1.5, line_y(n + 1) + 2),
               (x0 + 38.5, line_y(n + 1) + 2), (x0 + 38.5, line_y(n + 1) - 7.5)], INK_BLUE, 0.4)
    # the line he was writing when he fell asleep: a word, then the pen slides off down the page
    n += 3
    end = write(d, "-> on relache les", x0 + 40, n)
    pts = []
    x, y = end + 1.0, line_y(n) - 1.5
    for i in range(60):
        t = i / 59
        pts.append((x + 55 * t + 1.2 * math.sin(t * 19), y + 34 * t * t + 0.8 * math.sin(t * 13)))
    stroke(d, pts, INK_BLUE, 0.42)


def right_page(d):
    x0 = PAGE_W
    write(d, "ex. :", x0 + 38, 2, 7.0)
    nodes = {"s": (60, 70), "a": (95, 50), "b": (100, 95), "c": (135, 62), "t": (148, 110)}
    edges = [("s", "a", "4"), ("s", "b", "2"), ("a", "b", "1"), ("a", "c", "5"), ("b", "c", "8"),
             ("b", "t", "10"), ("c", "t", "2")]
    path = [{"s", "b"}, {"a", "b"}, {"a", "c"}, {"c", "t"}]   # s-b-a-c-t = 10
    font = ImageFont.truetype(FONT, mm(6.4))
    small = ImageFont.truetype(FONT, mm(5.2))
    r = 6.0
    for p, q, wgt in edges:
        (ax, ay), (bx, by) = nodes[p], nodes[q]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        ux, uy = dx / L, dy / L
        a = (x0 + ax + ux * r, ay + uy * r)
        b = (x0 + bx - ux * r, by - uy * r)
        mid = ((a[0] + b[0]) / 2 + R.uniform(-0.6, 0.6), (a[1] + b[1]) / 2 + R.uniform(-0.6, 0.6))
        stroke(d, [a, mid, b], INK_BLUE, 0.42)
        if {p, q} in path:
            stroke(d, [(a[0] + 0.8, a[1] - 0.8), (mid[0] + 0.8, mid[1] - 0.8), (b[0] + 0.8, b[1] - 0.8)], INK_RED, 0.55)
        d.text((mm((a[0] + b[0]) / 2 - uy * 4.5), mm((a[1] + b[1]) / 2 + ux * 4.5)), wgt, font=small, fill=INK_BLUE,
               anchor="mm")
    for k, (cx, cy) in nodes.items():
        circle(d, x0 + cx, cy, r, INK_BLUE, 0.45)
        d.text((mm(x0 + cx), mm(cy + 0.4)), k, font=font, fill=INK_BLUE, anchor="mm")
    write(d, "d[t] = 10", x0 + 40, 17, 7.4)
    stroke(d, [(x0 + 39, line_y(17) + 1.4), (x0 + 66, line_y(17) + 1.0)], INK_RED, 0.5)
    # a tiny earbud doodled in the margin: a tilted bean and its stem
    bx, by = x0 + 20, 158
    bean = []
    for i in range(43):
        a = math.tau * i / 40
        x, y = 3.6 * math.cos(a), 2.6 * math.sin(a)
        bean.append((bx + x * 0.87 - y * 0.5, by + x * 0.5 + y * 0.87))
    stroke(d, bean, INK_BLUE, 0.4)
    stroke(d, [(bx + 1.2, by + 2.4), (bx + 1.0, by + 12.0), (bx + 1.8, by + 12.9), (bx + 2.7, by + 12.2), (bx + 3.3, by + 2.2)],
           INK_BLUE, 0.4)


def main():
    os.makedirs(OUT, exist_ok=True)
    img = Image.new("RGB", (W * SS, H * SS), PAPER)
    d = ImageDraw.Draw(img)
    seyes(d, 0)
    seyes(d, PAGE_W)
    left_page(d)
    right_page(d)
    img = img.resize((W, H), Image.LANCZOS)
    # paper: a faint fibre noise, the ink a touch soft, the gutter shaded where the pages curve into it
    px = img.load()
    noise = Image.effect_noise((W // 4, H // 4), 18).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.2))
    nz = noise.load()
    for y in range(H):
        for x in range(W):
            g = abs(x - W / 2) / (12.0 * PX)
            shade = 1.0 - 0.16 * math.exp(-g * g * 2.2) - 0.03 * (y / H)
            n = (nz[x, y] - 128) / 128.0 * 0.012
            r, gg, b = px[x, y]
            k = shade + n
            px[x, y] = (int(min(255, r * k)), int(min(255, gg * k)), int(min(255, b * k)))
    path = os.path.join(OUT, "notebook_algo.png")
    img.save(path, optimize=True)
    print(path, img.size)


if __name__ == "__main__":
    main()
