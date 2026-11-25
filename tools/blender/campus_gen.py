"""Generated textures (deterministic): posters, PC screens, the lecture slide, whiteboards, the sticker
column, fake room interiors for exterior-only windows, exit signs, notices, menu board, birch bark and
leaf-cluster cards. 2D layouts are rendered with Workbench (flat colours, orthographic camera) using the
project fonts; foliage clusters with Eevee. Output: assets/textures/campus_gen/*.png|jpg (+ Godot presets).
"""
import bpy, os, math, random
import campus_tex as T
import campus_mat as CM

GEN = os.path.join(T.TEX_DIR, "campus_gen")
FONTS = os.path.join(T.ROOT, "assets", "fonts")
_fonts = {}


SYS_FONTS = {
    # static fonts with clean outlines (the Fontsource woff2 instances in assets/fonts keep overlapping
    # contours, which Blender fills even-odd -> holes in T, F, P, e...)
    "title": ["/System/Library/Fonts/Avenir Next.ttc"],
    "title7": ["/System/Library/Fonts/Avenir Next.ttc"],
    "bold": ["/System/Library/Fonts/Avenir Next.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "semi": ["/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "sign": ["/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "cond": ["/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"],
    "black": ["/System/Library/Fonts/Supplemental/Arial Black.ttf"],
    "reg": ["/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"],
    "mono": ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf"],
    "mono4": ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf"],
}


def builtin_font():
    f = bpy.data.fonts.get("Bfont Regular")
    if f is None:
        cu = bpy.data.curves.new("tmp_font_probe", "FONT")
        f = cu.font
        bpy.data.curves.remove(cu)
    return f


def font(name):
    if name in _fonts:
        return _fonts[name]
    f = None
    for path in SYS_FONTS.get(name, []):
        if os.path.exists(path):
            try:
                f = bpy.data.fonts.load(path, check_existing=True)
                break
            except Exception:
                f = None
    _fonts[name] = f or builtin_font()
    return _fonts[name]


def lin(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


class Canvas:
    """2D drawing in pixels (origin top-left, y down) rendered flat with Workbench."""

    def __init__(self, w, h, bg="#000000", transparent=False):
        self.w, self.h = w, h
        self.sc = bpy.data.scenes.new("gen_canvas")
        sc = self.sc
        sc.render.engine = "BLENDER_WORKBENCH"
        sc.display.shading.light = "FLAT"
        sc.display.shading.color_type = "MATERIAL"
        sc.display.shading.show_object_outline = False
        sc.display.shading.show_cavity = False
        sc.display.shading.show_shadows = False
        sc.display.shading.show_specular_highlight = False
        sc.display.render_aa = "16"
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
        sc.render.film_transparent = transparent
        sc.render.resolution_x, sc.render.resolution_y = w, h
        sc.render.resolution_percentage = 100
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
        cam = bpy.data.cameras.new("gen_cam")
        cam.type = "ORTHO"
        cam.ortho_scale = max(w, h) / 100.0
        co = bpy.data.objects.new("gen_cam", cam)
        sc.collection.objects.link(co)
        co.location = (w / 200.0, h / 200.0, 50.0)
        sc.camera = co
        self.z = 0.0
        self._mats = {}
        self._obs = [co]
        self._data = [cam]
        if not transparent:
            self.rect(0, 0, w, h, bg)

    def _mat(self, color, alpha=1.0):
        key = (color, alpha)
        m = self._mats.get(key)
        if m is None:
            m = bpy.data.materials.new("gen_" + color)
            c = lin(color)
            m.diffuse_color = (c[0], c[1], c[2], alpha)
            if alpha < 1:
                m.blend_method = "BLEND"
            self._mats[key] = m
        return m

    def _z(self):
        self.z += 0.001
        return self.z

    def _ob(self, me):
        ob = bpy.data.objects.new("gen", me)
        self.sc.collection.objects.link(ob)
        self._obs.append(ob)
        self._data.append(me)
        return ob

    def poly(self, pts, color, alpha=1.0):
        z = self._z()
        me = bpy.data.meshes.new("gen_poly")
        me.from_pydata([(x / 100.0, (self.h - y) / 100.0, z) for x, y in pts], [], [list(range(len(pts)))])
        me.materials.append(self._mat(color, alpha))
        self._ob(me)

    def rect(self, x, y, w, h, color, alpha=1.0):
        self.poly([(x, y + h), (x + w, y + h), (x + w, y), (x, y)], color, alpha)

    def circle(self, cx, cy, r, color, n=40, alpha=1.0):
        self.poly([(cx + r * math.cos(2 * math.pi * i / n), cy - r * math.sin(2 * math.pi * i / n)) for i in range(n)], color, alpha)

    def line(self, x0, y0, x1, y1, wdt, color):
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L * wdt / 2, dx / L * wdt / 2
        self.poly([(x0 - nx, y0 - ny), (x1 - nx, y1 - ny), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)], color)

    def text(self, s, x, y, size, color, fnt="bold", align="LEFT", rot=0.0, spacing=1.0, valign="BASE"):
        """baseline at (x, y) for valign BASE; size = em size in px"""
        z = self._z()
        cu = bpy.data.curves.new("gen_txt", "FONT")
        cu.body = s
        cu.font = font(fnt)
        cu.size = size / 100.0
        cu.align_x = align
        cu.align_y = {"BASE": "TOP_BASELINE", "CENTER": "CENTER", "TOP": "TOP"}[valign]
        cu.space_character = spacing
        cu.materials.append(self._mat(color))
        ob = bpy.data.objects.new("gen_txt", cu)
        self.sc.collection.objects.link(ob)
        ob.location = (x / 100.0, (self.h - y) / 100.0, z)
        ob.rotation_euler = (0, 0, -rot)
        self._obs.append(ob)
        self._data.append(cu)

    def render(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.sc.render.filepath = path
        bpy.ops.render.render(write_still=True, scene=self.sc.name)
        for ob in self._obs:
            bpy.data.objects.remove(ob, do_unlink=True)
        for d in self._data:
            try:
                if isinstance(d, bpy.types.Mesh):
                    bpy.data.meshes.remove(d)
                elif isinstance(d, bpy.types.Curve):
                    bpy.data.curves.remove(d)
                elif isinstance(d, bpy.types.Camera):
                    bpy.data.cameras.remove(d)
            except Exception:
                pass
        for m in self._mats.values():
            bpy.data.materials.remove(m)
        bpy.data.scenes.remove(self.sc)
        T.write_import_preset(path)
        return path


def out(name, ext="png"):
    return os.path.join(GEN, f"{name}.{ext}")


def fresh(path):
    return os.path.exists(path) and os.path.getsize(path) > 0


# ------------------------------------------------------------------ posters
POSTERS = {
    "forum": (("#2E3C9F", "#BCFB0B", "#ffffff"), "FORUM\nENTREPRISES", "jeudi - amphi 4"),
    "piscine": (("#111111", "#ff6fb5", "#ffffff"), "PISCINE\nJOUR 9", "courage. l'ACU veille."),
    "wei": (("#BCFB0B", "#2E3C9F", "#111111"), "WEI\n2026", "inscriptions au BDE"),
    "rules": (("#ffffff", "#ff7b72", "#111111"), "NO FOOD.\nWATER ONLY.", "bouteilles fermees - charte PIE"),
    "moulinette": (("#0d1117", "#2ea043", "#ffffff"), "MOULINETTE\nJ09: 3/7", "resultats a minuit"),
    "rush": (("#BCFB0B", "#2E3C9F", "#111111"), "RUSH\n42SH", "vendredi 18h - salle 401"),
    "acu": (("#ff6fb5", "#2E3C9F", "#ffffff"), "ACU\nQ&A", "mardi, SM14"),
    "menu": (("#BCFB0B", "#2E3C9F", "#111111"), "MENU\nETUDIANT", "formule 4.50"),
    "microondes": (("#2E3C9F", "#ffcf7a", "#ffffff"), "MICRO-\nONDES", "max 2 min par personne svp"),
    "soiree": (("#ff6fb5", "#111111", "#ffffff"), "SOIREE\nBDE", "vendredi, 22h, here"),
    "ctf": (("#111111", "#BCFB0B", "#ffffff"), "CTF\nNIGHT", "jeudi - bring snacks"),
    "gamejam": (("#2E3C9F", "#ff6fb5", "#ffffff"), "GAME\nJAM", "48h - inscriptions BDE"),
    "bde_asso": (("#f2efe6", "#e85a3a", "#111111"), "ASSOS\nFAIR", "mercredi - cour Pasteur"),
    "concert": (("#1b1b2f", "#ffcf7a", "#ffffff"), "OPEN\nMIC", "le Under - 20h"),
}


def poster(key):
    path = out("poster_" + key)
    if fresh(path):
        return path
    (bg, ac, fg), title, sub = POSTERS[key]
    w, h = 384, 512
    c = Canvas(w, h, bg)
    c.circle(w * 0.7, h * 0.32, w * 0.36, ac, n=60)
    c.rect(28, 30, 70, 6, fg)
    c.text("EPITA KB", 28, 62, 22, fg, "semi")
    for i, ln in enumerate(title.split("\n")):
        c.text(ln, 28, h * 0.68 + i * 56, 54, fg, "title")
    c.text(sub, 28, h - 34, 21, fg, "semi")
    return c.render(path)


# ------------------------------------------------------------------ screens (i3 tiling desktop, like the PIE machines)
def screen(k):
    path = out("screen_%d" % k)
    if fresh(path):
        return path
    rng = random.Random(1000 + k)
    w, h = 512, 320
    c = Canvas(w, h, "#0d1117")
    c.rect(0, h - 16, w, 16, "#1f2430")
    c.rect(6, h - 13, 18, 10, "#4f8cff")
    c.text("1  2  3", 30, h - 4, 11, "#8b949e", "mono4")
    c.text("17:42  BAT 64%", w - 8, h - 4, 11, "#8b949e", "mono4", align="RIGHT")
    H = h - 18
    if k % 3 == 0:
        panes = [(0, 0, w / 2, H), (w / 2, 0, w / 2, H / 2), (w / 2, H / 2, w / 2, H / 2)]
    elif k % 3 == 1:
        panes = [(0, 0, w, H)]
    else:
        panes = [(0, 0, w / 2, H), (w / 2, 0, w / 2, H)]
    cols = ["#7ee787", "#c9d1d9", "#79c0ff", "#ff7b72", "#c9d1d9", "#8b949e", "#d2a8ff"]
    for i, (x, y, pw, ph) in enumerate(panes):
        b = "#4f8cff" if i == 0 else "#30363d"
        c.rect(x + 2, y + 2, pw - 4, 2, b)
        c.rect(x + 2, y + ph - 4, pw - 4, 2, b)
        c.rect(x + 2, y + 2, 2, ph - 4, b)
        c.rect(x + pw - 4, y + 2, 2, ph - 4, b)
        for l in range(int(ph / 12) - 1):
            L = 20 + rng.random() * (pw - 60)
            ind = 16 if rng.random() < 0.3 else 0
            c.rect(x + 10 + ind, y + 10 + l * 12, L, 5, cols[rng.randrange(len(cols))])
    return c.render(path)


def slide():
    path = out("slide_dijkstra")
    if fresh(path):
        return path
    w, h = 1600, 900
    c = Canvas(w, h, "#f7f8fb")
    c.rect(0, 0, w, 110, "#2E3C9F")
    c.text("Algorithmique  -  Plus courts chemins", 50, 76, 58, "#ffffff", "title")
    code = ["dijkstra(G, s):", "  for v in G.V: d[v] = inf", "  d[s] = 0;  Q = tas(G.V)", "  while Q:", "    u = extract_min(Q)",
            "    for (u, v, w) in G.adj[u]:", "      relax(u, v, w)", "", "# complexite : O((V + E) log V)"]
    for i, ln in enumerate(code):
        c.text(ln, 60, 196 + i * 66, 40, "#1d1d1f" if not ln.startswith("#") else "#2E3C9F", "mono")
    # little graph on the right
    nodes = [(1180, 260), (1420, 300), (1250, 470), (1460, 520), (1330, 650)]
    edges = [(0, 1, "4"), (0, 2, "1"), (2, 1, "2"), (1, 3, "5"), (2, 4, "8"), (3, 4, "3")]
    for a, b, wt in edges:
        (x0, y0), (x1, y1) = nodes[a], nodes[b]
        c.line(x0, y0, x1, y1, 4, "#3b3b40")
        c.text(wt, (x0 + x1) / 2 + 10, (y0 + y1) / 2 - 8, 30, "#c0392b", "mono")
    for i, (x, y) in enumerate(nodes):
        c.circle(x, y, 30, "#2E3C9F")
        c.text("abcde"[i], x, y + 12, 34, "#ffffff", "bold", align="CENTER")
    c.rect(w - 380, h - 120, 330, 70, "#BCFB0B")
    c.text("QCM vendredi 9h", w - 360, h - 72, 32, "#111111", "bold")
    c.text("EPITA  -  S2 2026", 50, h - 30, 24, "#8a8f99", "semi")
    return c.render(path)


WHITEBOARDS = {
    "wb_amphi_a": ["QCM vendredi", "graphe = (V, E)", "-42 si triche"],
    "wb_amphi_b": ["BFS / DFS", "tas binaire", "O(n log n)"],
    "wb_sm14": ["PISCINE J09", "rush 42sh vendredi", "norme : 25 lignes max"],
}


def whiteboard(key):
    path = out(key)
    if fresh(path):
        return path
    w, h = 1024, 384
    c = Canvas(w, h, "#fbfbfa")
    rng = random.Random(len(key) * 31)
    for i in range(14):  # faint ghost of erased marker
        x, y = rng.random() * w, rng.random() * h
        c.rect(x, y, 60 + rng.random() * 200, 6, "#e9eaee")
    for i, ln in enumerate(WHITEBOARDS[key]):
        c.text(ln, 40, 80 + i * 72, 46, ["#2a5bd7", "#c0392b", "#1e1e1e"][i % 3], "mono")
    # doodle: a small tree / graph
    pts = [(820, 90), (760, 190), (880, 190), (720, 290), (800, 290)]
    for a, b in ((0, 1), (0, 2), (1, 3), (1, 4)):
        c.line(*pts[a], *pts[b], 4, "#2a5bd7")
    for x, y in pts:
        c.circle(x, y, 18, "#2a5bd7")
        c.circle(x, y, 13, "#fbfbfa")
    return c.render(path)


def stickers():
    path = out("stickers")
    if fresh(path):
        return path
    rng = random.Random(4242)
    w, h = 512, 1024
    c = Canvas(w, h, "#c9cbcf")
    cols = ["#e74c3c", "#f1c40f", "#2ecc71", "#3498db", "#9b59b6", "#ffffff", "#111111", "#e67e22", "#1abc9c", "#ff6fb5"]
    words = ["EPITA", "LSE", "ACU", "YAKA", "BDE", "GCC", "VIM", "RUST", "GNU", "C", "42SH", "TIGER", "NIX", "i3", "SEGV", "git", "CTF", "PIE"]
    for k in range(95):
        x, y, r = rng.random() * w, rng.random() * h, 22 + rng.random() * 40
        col = cols[rng.randrange(len(cols))]
        a = (rng.random() - 0.5) * 0.8
        if rng.random() < 0.5:
            c.circle(x, y, r, col, n=28)
        else:
            ca, sa = math.cos(a), math.sin(a)
            pts = [(-r, -r * 0.6), (r, -r * 0.6), (r, r * 0.6), (-r, r * 0.6)]
            c.poly([(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in pts], col)
        tc = "#111111" if col in ("#ffffff", "#f1c40f", "#2ecc71", "#1abc9c") else "#ffffff"
        c.text(words[rng.randrange(len(words))], x, y + r * 0.2, r * 0.55, tc, "bold", align="CENTER", rot=a)
    return c.render(path)


# ------------------------------------------------------------------ fake interiors behind exterior-only windows
def room_atlas():
    """4 x 2 cells of 512: 0-3 lit rooms (warm offices, blinds, apartment), 4-7 dark ones."""
    path = out("room_atlas")
    if fresh(path):
        return path
    W, H = 2048, 1024
    c = Canvas(W, H, "#000000")
    rng = random.Random(77)

    def band(x, y, w, h, c0, c1, n=10):
        for i in range(n):
            t = i / (n - 1)
            col = "#%02x%02x%02x" % tuple(int(int(c0[j:j + 2], 16) * (1 - t) + int(c1[j:j + 2], 16) * t) for j in (1, 3, 5))
            c.rect(x, y + h * i / n, w, h / n + 1, col)

    def office(ox, oy, lit, blinds=0.0, warm=True):
        S = 512
        wall0, wall1 = ("#e9d3b0", "#b8976c") if lit and warm else (("#d9dee6", "#9aa3ad") if lit else ("#22262d", "#121418"))
        band(ox, oy, S, S, wall0, wall1)
        # ceiling + light panels
        c.rect(ox, oy, S, 70, "#f4ead8" if lit else "#1a1c20")
        for k in range(3):
            c.rect(ox + 40 + k * 160, oy + 26, 110, 16, "#fff8e8" if lit else "#2a2f36")
        # back wall details: shelf, poster, window to the other side
        c.rect(ox + 300, oy + 150, 160, 120, "#8fb3d9" if lit else "#1c2633")
        c.rect(ox + 60, oy + 140, 90, 120, "#c0392b" if rng.random() < 0.5 else "#2e3c9f")
        # desks + monitors + chairs (silhouettes)
        c.rect(ox, oy + 330, S, 182, "#7a6650" if lit else "#16181c")
        for k in range(3):
            dx = ox + 30 + k * 165
            c.rect(dx, oy + 330, 140, 16, "#4b3f33" if lit else "#0d0e10")
            c.rect(dx + 40, oy + 268, 70, 50, "#1d232c")
            c.rect(dx + 46, oy + 274, 58, 38, "#6fa8ff" if (lit or rng.random() < 0.6) else "#1d232c")
            c.rect(dx + 70, oy + 318, 10, 14, "#1d232c")
            c.rect(dx + 30, oy + 360, 60, 90, "#2a2d33" if lit else "#0b0c0e")
        if rng.random() < 0.6 and lit:
            # someone working
            c.circle(ox + 255, oy + 300, 26, "#6b4f3a")
            c.rect(ox + 222, oy + 324, 66, 110, "#34495e")
        if blinds > 0:
            for k in range(int(S * blinds / 18)):
                c.rect(ox, oy + k * 18, S, 13, "#e8e2d4" if lit else "#3a3d42")

    def apartment(ox, oy, lit):
        S = 512
        band(ox, oy, S, S, "#f0c98f" if lit else "#1e1d22", "#a8784a" if lit else "#101014")
        c.rect(ox, oy, 120, S, "#b23a48" if lit else "#2a1b20")       # curtain
        c.rect(ox + S - 100, oy, 100, S, "#b23a48" if lit else "#2a1b20")
        c.rect(ox + 200, oy + 120, 120, 90, "#3a5a40")                # painting
        c.circle(ox + 380, oy + 300, 40, "#fff2c8" if lit else "#24242a")  # lamp shade
        c.rect(ox + 375, oy + 340, 10, 120, "#2b2b2b")
        c.rect(ox + 130, oy + 380, 220, 132, "#5b4a3f" if lit else "#151417")  # sofa back

    for i in range(4):
        ox, oy = i * 512, 0
        if i == 3:
            apartment(ox, oy, True)
        else:
            office(ox, oy, True, blinds=(0.0, 0.45, 0.0)[i], warm=i != 2)
    for i in range(4):
        ox, oy = i * 512, 512
        if i == 2:
            apartment(ox, oy, False)
        elif i == 3:
            band(ox, oy, 512, 512, "#15171b", "#0b0c0e")
        else:
            office(ox, oy, False, blinds=(0.0, 0.85)[i])
    return c.render(path)


def exit_sign():
    path = out("exit_sign")
    if fresh(path):
        return path
    w, h = 256, 128
    c = Canvas(w, h, "#13a659")
    c.rect(6, 6, w - 12, h - 12, "#17b864")
    # door
    c.rect(150, 20, 56, 88, "#ffffff")
    c.rect(156, 26, 44, 82, "#17b864")
    # running man
    c.circle(120, 32, 10, "#ffffff")
    c.poly([(108, 46), (126, 46), (132, 74), (120, 76)], "#ffffff")
    c.line(124, 72, 142, 100, 9, "#ffffff")
    c.line(118, 72, 100, 92, 9, "#ffffff")
    c.line(100, 92, 86, 90, 8, "#ffffff")
    c.line(112, 50, 94, 64, 8, "#ffffff")
    c.line(124, 52, 142, 48, 8, "#ffffff")
    # arrow
    c.poly([(26, 64), (52, 40), (52, 56), (80, 56), (80, 72), (52, 72), (52, 88)], "#ffffff")
    return c.render(path)


def notice(k):
    path = out("notice_%d" % k)
    if fresh(path):
        return path
    rng = random.Random(300 + k)
    w, h = 256, 362
    c = Canvas(w, h, "#fbfaf6")
    heads = ["RAPPEL", "PARTIELS S2", "OBJETS TROUVES", "STAGE ETE", "COVOIT KB", "SALLE 401"]
    c.rect(0, 0, w, 40, ["#2E3C9F", "#c0392b", "#16a085", "#111111"][k % 4])
    c.text(heads[k % len(heads)], 14, 28, 20, "#ffffff", "bold")
    y = 66
    while y < h - 30:
        c.rect(14, y, 60 + rng.random() * 160, 7, "#9a9a9a")
        y += 16 + (12 if rng.random() < 0.2 else 0)
    return c.render(path)


def menu_board():
    path = out("menu_board")
    if fresh(path):
        return path
    w, h = 512, 640
    c = Canvas(w, h, "#5a4632")
    c.rect(16, 16, w - 32, h - 32, "#1f2a24")
    c.text("MENU DU JOUR", w / 2, 92, 46, "#f2efe6", "title", align="CENTER")
    items = [("pates bolo", "4,50"), ("salade cesar", "3,80"), ("quiche + salade", "4,20"), ("yaourt", "0,90"), ("cafe", "1,00"),
             ("formule etu", "4,50")]
    for i, (a, b) in enumerate(items):
        y = 180 + i * 66
        c.text(a, 50, y, 30, "#f2efe6", "semi")
        c.text(b, w - 50, y, 30, "#ffd84a", "bold", align="RIGHT")
    c.text("(encore des pates)", w / 2, h - 60, 24, "#b9d7c4", "reg", align="CENTER")
    return c.render(path)


def info_screen():
    path = out("jpo_screen")
    if fresh(path):
        return path
    w, h = 960, 400
    c = Canvas(w, h, "#2E3C9F")
    c.circle(w * 0.86, h * 0.2, 150, "#3d4fc2", n=60)
    c.text("JOURNEE PORTES OUVERTES", 40, 150, 62, "#ffffff", "title")
    c.text("samedi  -  10h-17h  -  KB & Villejuif", 40, 230, 36, "#BCFB0B", "semi")
    c.text("epita.fr", 40, h - 40, 28, "#c8d0ff", "semi")
    return c.render(path)


def birch_bark():
    """procedural birch bark (white with dark lenticels and patches): diff + nor + arm 1k"""
    import numpy as np
    d = os.path.join(GEN, "birch_bark_diff_1k.jpg")
    n = os.path.join(GEN, "birch_bark_nor_gl_1k.jpg")
    a = os.path.join(GEN, "birch_bark_arm_1k.jpg")
    if all(fresh(p) for p in (d, n, a)):
        return {"diff": d, "nor_gl": n, "arm": a}
    os.makedirs(GEN, exist_ok=True)
    S = 1024
    rng = np.random.default_rng(12)
    hgt = np.zeros((S, S), np.float32)
    col = np.ones((S, S, 3), np.float32) * np.array([0.86, 0.85, 0.80], np.float32)
    yy, xx = np.mgrid[0:S, 0:S]
    # horizontal lenticels
    for _ in range(520):
        x0, y0 = rng.integers(0, S), rng.integers(0, S)
        L, th = rng.integers(14, 70), rng.integers(1, 4)
        xs = (np.arange(L) + x0) % S
        for t in range(th):
            col[(y0 + t) % S, xs] = (0.12, 0.11, 0.10)
            hgt[(y0 + t) % S, xs] = -1.0
    # a few dark rough patches (branch scars), wide and thin
    for _ in range(7):
        cx, cy, r = rng.integers(0, S), rng.integers(0, S), rng.integers(12, 30)
        m = ((xx - cx) ** 2 / (r * 3.5) ** 2 + (yy - cy) ** 2 / r ** 2) < 1
        col[m] = col[m] * 0.3 + np.array([0.08, 0.075, 0.07]) * 0.7
        hgt[m] -= 0.6
    noise = rng.random((S, S)).astype(np.float32)
    col *= (0.92 + 0.08 * noise)[:, :, None]
    hgt += noise * 0.2
    gx = np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)
    gy = np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)
    nrm = np.stack([-gx * 1.5, gy * 1.5, np.ones_like(gx)], 2)
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    T._write_img(d, col)
    T._write_img(n, nrm * 0.5 + 0.5)
    rough = 0.7 + 0.25 * (hgt < -0.3)
    T._write_img(a, np.stack([np.ones((S, S)) * 0.95, rough, np.zeros((S, S))], 2))
    for p in (d, n, a):
        T.write_import_preset(p)
    return {"diff": d, "nor_gl": n, "arm": a}


def leaf_clusters(leaf_set, name, tint=(1, 1, 1), seed=1, leaf_size=0.10, n_leaves=40, spread=0.42):
    """render 4 leafy twig clusters (2 x 2 atlas, 1024 px) seen from the front with alpha, from a CC0 leaf set.
    Returned path is an RGBA png used as an alpha-masked card texture."""
    path = out(name + "_clusters")
    if fresh(path):
        return path
    leaf = T.ambientcg(leaf_set, "2K", alpha=True)
    sc = bpy.data.scenes.new("gen_leaves")
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = 1024
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "Standard"
    sc.eevee.taa_render_samples = 16
    w = bpy.data.worlds.new("gen_leaves_w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    sc.world = w
    cam = bpy.data.cameras.new("gen_leaves_cam")
    cam.type = "ORTHO"
    cam.ortho_scale = 2.0
    co = bpy.data.objects.new("gen_leaves_cam", cam)
    sc.collection.objects.link(co)
    co.location = (0, 0, 10)
    sc.camera = co
    # leaf material: emission of the leaf albedo (flat, exact colours), alpha from the set's opacity
    m = bpy.data.materials.new("gen_leaf_mat")
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    N.remove(N["Principled BSDF"])
    tex = N.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(leaf["diffa"], check_existing=True)
    tex.image.alpha_mode = "STRAIGHT"
    em = N.new("ShaderNodeEmission")
    mixc = N.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    mixc.blend_type = "MULTIPLY"
    mixc.inputs[0].default_value = 1.0
    attr = N.new("ShaderNodeAttribute")
    attr.attribute_name = "shade"
    attr.attribute_type = "OBJECT"
    L.new(tex.outputs["Color"], mixc.inputs[6])
    L.new(attr.outputs["Color"], mixc.inputs[7])
    L.new(mixc.outputs[2], em.inputs["Color"])
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    gt = N.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = 0.5
    L.new(tex.outputs["Alpha"], gt.inputs[0])
    L.new(gt.outputs[0], mx.inputs[0])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], N["Material Output"].inputs["Surface"])
    m.surface_render_method = "DITHERED"
    # the leaf set is a grid of individual leaves: find their cells (3 x 3 or 3 x 2 layouts)
    cells = _leaf_cells(leaf["diffa"])
    twig = bpy.data.materials.new("gen_twig")
    twig.use_nodes = True
    tn = twig.node_tree.nodes
    tn.remove(tn["Principled BSDF"])
    e2 = tn.new("ShaderNodeEmission")
    e2.inputs["Color"].default_value = (0.09, 0.07, 0.05, 1)
    twig.node_tree.links.new(e2.outputs[0], tn["Material Output"].inputs["Surface"])
    rng = random.Random(seed)
    obs = []
    for q in range(4):
        qx, qy = (q % 2) * 1.0 - 0.5, (q // 2) * 1.0 - 0.5
        # twig: a few line segments
        stem = [(qx + 0.0, qy - 0.48), (qx + rng.uniform(-0.08, 0.08), qy - 0.05), (qx + rng.uniform(-0.15, 0.15), qy + 0.38)]
        for (x0, y0), (x1, y1) in zip(stem, stem[1:]):
            me = bpy.data.meshes.new("tw")
            dx, dy = x1 - x0, y1 - y0
            ln = math.hypot(dx, dy)
            nx, ny = -dy / ln * 0.006, dx / ln * 0.006
            me.from_pydata([(x0 - nx, y0 - ny, 0), (x1 - nx, y1 - ny, 0), (x1 + nx, y1 + ny, 0), (x0 + nx, y0 + ny, 0)], [], [[0, 1, 2, 3]])
            me.materials.append(twig)
            ob = bpy.data.objects.new("tw", me)
            sc.collection.objects.link(ob)
            obs.append(ob)
        for i in range(n_leaves):
            u0, v0, u1, v1 = cells[rng.randrange(len(cells))]
            t = rng.random()
            sx = stem[0][0] + (stem[2][0] - stem[0][0]) * t + rng.gauss(0, spread * 0.35)
            sy = stem[0][1] + (stem[2][1] - stem[0][1]) * t + rng.gauss(0, spread * 0.25) + 0.05
            sz = leaf_size * rng.uniform(0.75, 1.25)
            ang = rng.uniform(-math.pi, math.pi)
            asp = (v1 - v0) / max(1e-6, (u1 - u0))
            hw, hh = sz * 0.5, sz * 0.5 * asp
            ca, sa = math.cos(ang), math.sin(ang)
            pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
            me = bpy.data.meshes.new("lf")
            me.from_pydata([(sx + px * ca - py * sa, sy + px * sa + py * ca, 0.01 + i * 0.0005) for px, py in pts], [], [[0, 1, 2, 3]])
            uv = me.uv_layers.new()
            for li, (uu, vv) in enumerate(((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
                uv.data[li].uv = (uu, vv)
            me.materials.append(m)
            ob = bpy.data.objects.new("lf", me)
            k = rng.uniform(0.6, 1.0)
            ob["shade"] = (tint[0] * k, tint[1] * k, tint[2] * k, 1.0)
            sc.collection.objects.link(ob)
            obs.append(ob)
    os.makedirs(GEN, exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    for ob in obs + [co]:
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if isinstance(me, bpy.types.Mesh):
            bpy.data.meshes.remove(me)
    bpy.data.scenes.remove(sc)
    T.write_import_preset(path)
    return path


def _leaf_cells(path):
    """bounding boxes (uv) of the separate leaves in an ambientCG LeafSet atlas (via its alpha)"""
    import numpy as np
    a = T._np_img(path)
    al = a[:, :, 3] if a.shape[2] > 3 else np.ones(a.shape[:2])
    m = al > 0.5
    h, w = m.shape
    cols = np.where(m.any(axis=0))[0]
    rows = np.where(m.any(axis=1))[0]

    def runs(idx):
        out, start = [], idx[0]
        for p, q in zip(idx, idx[1:]):
            if q != p + 1:
                out.append((start, p))
                start = q
        out.append((start, idx[-1]))
        return [r for r in out if r[1] - r[0] > 20]
    cells = []
    for (r0, r1) in runs(rows):
        sub = m[r0:r1 + 1]
        cidx = np.where(sub.any(axis=0))[0]
        for (c0, c1) in runs(cidx):
            sub2 = m[r0:r1 + 1, c0:c1 + 1]
            rr = np.where(sub2.any(axis=1))[0]
            y0, y1 = r0 + rr[0], r0 + rr[-1]
            # image row 0 is the top: uv v = 1 - row / h
            cells.append((c0 / w, 1 - (y1 + 1) / h, (c1 + 1) / w, 1 - y0 / h))
    return cells or [(0, 0, 1, 1)]


def lobby_mural():
    path = out("lobby_mural")
    if fresh(path):
        return path
    w, h = 1024, 1024
    c = Canvas(w, h, "#1f2a52")
    for k in range(9):
        c.rect(0, 120 + k * 96, w, 3, "#2b3a6e")
    c.circle(w * 0.78, h * 0.26, 210, "#2E3C9F", n=80)
    c.circle(w * 0.78, h * 0.26, 150, "#1f2a52", n=80)
    c.rect(70, 140, 180, 16, "#BCFB0B")
    c.text("EPITA", 70, 330, 190, "#ffffff", "title")
    c.text("L'ECOLE DE L'INTELLIGENCE", 74, 400, 40, "#BCFB0B", "semi")
    c.text("INFORMATIQUE", 74, 452, 40, "#BCFB0B", "semi")
    # stylised campus map
    c.rect(70, 560, 880, 380, "#16204a")
    c.rect(110, 600, 360, 120, "#c79a7a")      # Voltaire
    c.rect(110, 740, 800, 26, "#3a4462")       # rue Pasteur
    c.poly([(520, 790), (700, 790), (760, 840), (760, 910), (520, 910)], "#557a3e")   # cour / amphi
    c.rect(560, 800, 120, 70, "#4f86a6")
    c.text("Batiment Voltaire", 130, 670, 26, "#ffffff", "semi")
    c.text("rue Pasteur", 600, 760, 22, "#c8d0ff", "semi")
    c.text("cour Pasteur", 540, 900, 22, "#ffffff", "semi")
    c.text("Kremlin-Bicetre  -  Paris  -  Lyon  -  Rennes  -  Strasbourg  -  Toulouse", 74, 990, 24, "#8f9bd6", "semi")
    return c.render(path)


def rollup():
    path = out("rollup_epita")
    if fresh(path):
        return path
    w, h = 400, 1000
    c = Canvas(w, h, "#ffffff")
    c.rect(0, 0, w, 330, "#2E3C9F")
    c.poly([(0, 330), (w, 250), (w, 330)], "#2E3C9F")
    c.text("EPITA", w / 2, 170, 110, "#ffffff", "title", align="CENTER")
    c.text("ADMISSIONS 2027", w / 2, 230, 30, "#BCFB0B", "semi", align="CENTER")
    for i, ln in enumerate(["Cycle ingenieur", "Bachelor", "MSc", "Mastere specialise"]):
        c.text(ln, 40, 430 + i * 70, 34, "#1f2a52", "bold")
        c.rect(40, 444 + i * 70, 50, 4, "#BCFB0B")
    c.circle(w * 0.5, 820, 90, "#BCFB0B", n=50)
    c.text("JPO", w * 0.5, 840, 56, "#1f2a52", "black", align="CENTER")
    c.text("epita.fr", w / 2, h - 40, 28, "#2E3C9F", "semi", align="CENTER")
    return c.render(path)


def cafe_mural():
    path = out("cafe_mural")
    if fresh(path):
        return path
    w, h = 1600, 512
    c = Canvas(w, h, "#BCFB0B")
    c.rect(0, h - 90, w, 90, "#1f2a52")
    c.text("CAFET'", 60, 230, 210, "#1f2a52", "title")
    c.text("bon appetit  -  pense a ramener ton plateau", 64, h - 34, 34, "#BCFB0B", "semi")
    # coffee cup + croissant + steam, flat shapes
    cx, cy = 1050, 230
    c.rect(cx - 90, cy - 70, 180, 150, "#ffffff")
    c.circle(cx + 110, cy, 50, "#ffffff", n=30)
    c.circle(cx + 110, cy, 28, "#BCFB0B", n=30)
    c.rect(cx - 120, cy + 80, 240, 18, "#ffffff")
    for k in range(3):
        c.line(cx - 50 + k * 50, cy - 90, cx - 30 + k * 50, cy - 160, 10, "#1f2a52")
    c.poly([(1280, 300), (1330, 210), (1420, 180), (1510, 210), (1560, 300), (1500, 330), (1420, 310), (1340, 330)], "#e0a64a")
    c.line(1370, 210, 1360, 320, 6, "#b07a2a")
    c.line(1420, 185, 1420, 312, 6, "#b07a2a")
    c.line(1470, 210, 1480, 320, 6, "#b07a2a")
    return c.render(path)


def under_mural():
    path = out("under_mural")
    if fresh(path):
        return path
    rng = random.Random(808)
    w, h = 2048, 640
    c = Canvas(w, h, "#22252c")
    cols = ["#ff4fb0", "#b8ff2a", "#3f8cff", "#ffcf3a", "#9b5cff", "#21d4c4", "#ff6a3d"]
    for k in range(40):
        x, y, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(30, 140)
        c.circle(x, y, r, cols[rng.randrange(len(cols))], n=36)
        c.circle(x, y, r * 0.8, "#22252c", n=36)
    for k in range(18):
        x0, y0 = rng.uniform(0, w), rng.uniform(0, h)
        c.line(x0, y0, x0 + rng.uniform(-300, 300), y0 + rng.uniform(-120, 120), rng.uniform(8, 22), cols[rng.randrange(len(cols))])
    c.text("THE UNDER", 120, 360, 230, "#b8ff2a", "black", rot=-0.04)
    c.text("BDE EPITA", 1320, 300, 120, "#ff4fb0", "black", rot=0.05)
    c.text("since 1984 - hack, eat, sleep, babyfoot", 140, 520, 52, "#ffffff", "semi")
    c.text("<3 ACU", 1500, 520, 70, "#3f8cff", "black", rot=-0.08)
    return c.render(path)


def morris_posters():
    path = out("morris_posters")
    if fresh(path):
        return path
    w, h = 1024, 512
    c = Canvas(w, h, "#d8d2c4")
    cols = [("#1f2a52", "#ffcf3a"), ("#b23a48", "#ffffff"), ("#111111", "#ff4fb0"), ("#2e7d4f", "#ffffff"), ("#e9e1d0", "#1f2a52"), ("#3f8cff", "#111111")]
    titles = ["THEATRE", "CONCERT", "EXPO", "CINEMA", "FESTIVAL", "OPERA"]
    for k in range(6):
        x = k * 170 + 6
        bg, fg = cols[k]
        c.rect(x, 20, 160, 470, bg)
        c.circle(x + 80, 170, 60, fg, n=30)
        c.text(titles[k], x + 80, 330, 30, fg, "bold", align="CENTER")
        c.text("mars 2027", x + 80, 380, 18, fg, "semi", align="CENTER")
    return c.render(path)


# ------------------------------------------------------------------ register everything as materials
def build_all(log=print):
    os.makedirs(GEN, exist_ok=True)
    for k in POSTERS:
        CM.register_image_material("M_poster_" + k, poster(k), rough=0.7)
    for k in range(6):
        CM.register_image_material("M_screen_%d" % k, screen(k), emit=1.6, rough=0.25)
    CM.register_image_material("M_slide", slide(), emit=0.9, rough=0.6)
    for k in WHITEBOARDS:
        CM.register_image_material("M_" + k, whiteboard(k), rough=0.15)
    CM.register_image_material("M_stickers", stickers(), rough=0.55)
    CM.register_image_material("M_room_card", room_atlas(), emit=1.3, rough=0.6)
    CM.register_image_material("M_exit_sign", exit_sign(), emit=2.5, rough=0.4)
    for k in range(6):
        CM.register_image_material("M_notice_%d" % k, notice(k), rough=0.8)
    CM.register_image_material("M_menu_board", menu_board(), rough=0.85)
    CM.register_image_material("M_jpo_screen", info_screen(), emit=1.4, rough=0.3)
    CM.register_image_material("M_lobby_mural", lobby_mural(), rough=0.6)
    CM.register_image_material("M_rollup", rollup(), rough=0.5)
    CM.register_image_material("M_cafe_mural", cafe_mural(), rough=0.7)
    CM.register_image_material("M_under_mural", under_mural(), rough=0.8)
    CM.register_image_material("M_morris", morris_posters(), rough=0.8)
    bb = birch_bark()
    CM.M["M_bark_birch"]["tex"] = ("gen", "birch_bark", "1k")
    leaves_plane = leaf_clusters("LeafSet029", "plane", tint=(0.78, 0.86, 0.62), seed=3, leaf_size=0.16, n_leaves=34)
    leaves_birch = leaf_clusters("LeafSet024", "birch", tint=(0.9, 0.97, 0.66), seed=5, leaf_size=0.085, n_leaves=58)
    CM.register_image_material("M_leaves_plane", leaves_plane, rough=0.7, alpha="MASK", double=True)
    CM.register_image_material("M_leaves_birch", leaves_birch, rough=0.7, alpha="MASK", double=True)
    log("generated textures ready")
