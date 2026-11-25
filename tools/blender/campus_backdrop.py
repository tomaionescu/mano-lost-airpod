"""The neighbourhood round the campus on its real footprints (docs/DESIGN.md §8.2, §8.6),
replacing the invented shops and the sound wall:
- rue Pasteur's neighbours: ARPEJ (21, 9 storeys, 18.4-24.9 m) east of KB1, 13-17 (7 storeys, 19.5 m) and 11
  (5 storeys) west of it, Paritalie's west annex; the street runs on west to avenue de Fontainebleau and, past the
  rue Emile Zola junction (x ~49.4, five zebra crossings), bends 12 degrees north between 32 rue Pasteur (the
  Francoise Dolto creche) and the hotels of 20-22 rue Voltaire (27.2 m);
- rue Voltaire about 9 m north of where v1 had it and turned 4.9 degrees, one eastbound lane and parking on the KB1
  side, LED lamps on its south pavement, trees on its north verge; behind the verge the slip road on its bridge, the
  balustrade over the cutting, the on-ramp 7 m down and the peripherique 7-8 m down, the limestone retaining wall at
  the west end, the grassed far side with trees on its crest and the red barrel roofs of the RATP Metro line 7
  workshop beyond (its sheds are placed in the right area, not on surveyed outlines);
- rue Roger Salengro through the south gate: one-way westbound with a one-way cycle track on each side;
- every other building outline of docs/campus_layout.svg (campus_backdrop_data.OTHERS) as a plain block with lit windows.
Parts named far_* cast no shadows (assets/levels/campus_import.gd). Windows are interior-mapped (M_window_*)."""
import math, os, random
import campus_arch as A
import campus_poly as PG
import campus_street as S
import campus_tex as T
import campus_voltaire as V
from campus_arch import Opening, wall_frame, interior_quad
from campus_layout import *
from campus_mat import K, mat as defmat
from campus_props_out import foliage
from campus_backdrop_data import NAMED, OTHERS

PI = math.pi
defmat("M_render_arpej", ("ph", "white_stucco", "2k"), tile=2.0, color="#e7e2da", grime="ext", macro=0.07)
defmat("M_render_1317", ("ph", "white_stucco", "2k"), tile=2.0, color="#f0eee9", grime="ext", macro=0.06)
defmat("M_far_beige", ("ph", "plastered_wall_02", "2k"), tile=3.0, color="#ddd3c3", grime="none", macro=0.0)
defmat("M_far_grey", ("ph", "plastered_wall_02", "2k"), tile=3.0, color="#c9c9c5", grime="none", macro=0.0)
defmat("M_far_white", ("ph", "white_stucco", "2k"), tile=3.0, color="#e9e6e0", grime="none", macro=0.0)
defmat("M_far_brick", ("ph", "brick_wall_001", "2k"), tile=3.0, color="#c8b3a5", grime="none", macro=0.0)
defmat("M_far_roof", ("ph", "bitumen", "1k"), tile=6.0, color="#8a8a8a", grime="none", macro=0.0)
defmat("M_far_ground", ("ph", "concrete_floor_02", "2k"), tile=6.0, color="#9a9894", grime="none", macro=0.0)
defmat("M_far_asphalt", ("ph", "asphalt_02", "2k"), tile=6.0, color="#d4d4d4", grime="none", macro=0.0)
defmat("M_roof_barrel", None, color="#a4432f", rough=0.55, metal=0.35, grime="none", macro=0.0)
defmat("M_roof_barrel_2", None, color="#8e3b2c", rough=0.6, metal=0.3, grime="none", macro=0.0)
defmat("M_far_shed", ("gen", "ribbed_steel", "1k"), tile=1.6, color="#b9b6ae", rough=0.8, metal=0.2, grime="none",
       macro=0.0)                 # the workshop's cladding: campus_kb1's generated ribs, light grey
defmat("M_balustrade", ("ph", "concrete_wall_008", "2k"), tile=2.0, color="#cfccc5", grime="ext", macro=0.06)
defmat("M_limestone_rough", ("ph", "concrete_wall_004", "2k"), tile=1.5, color="#cdbd9f", grime="ext", macro=0.14,
       maps=("diffg", "nor_gl", "arm"))
defmat("M_verge", ("gen", "lawn", "1k"), tile=3.0, grime="none", macro=0.14)   # lawn() below
defmat("M_sign_rose", None, color="#d9486f", rough=0.4)
defmat("M_track_paint", ("ph", "asphalt_02", "2k"), tile=4.0, color="#e6e6e0", maps=("nor_gl", "arm"), rough=0.75,
       grime="none", macro=0.0)

# street axes in game metres (docs/CAMPUS_LAYOUT.md §5.1 and the SVG's polylines)
AXIS_PASTEUR_E = [(49.4, -0.7), (56.8, -2.2), (122.2, -16.4)]
AXIS_VOLTAIRE = [(-165.1, -64.2), (-152.7, -60.3), (-86.2, -49.9), (-69.2, -48.3), (28.0, -40.0), (49.0, -39.6),
                 (72.1, -42.7), (93.0, -50.0), (112.9, -57.9)]
ZOLA_N = [(49.4, -0.7), (49.8, -8.5), (49.2, -33.5), (49.0, -39.6)]           # heading north: +d = east
ZOLA_S = [(49.4, -0.7), (49.9, 8.2), (52.7, 54.3), (53.1, 58.4), (53.4, 62.0)]  # heading south: +d = west
AXIS_SALENGRO = [(-130.4, 54.9), (-118.8, 55.3), (-106.4, 55.7), (-63.0, 57.2), (-52.3, 57.7), (1.8, 60.0),
                 (53.4, 62.0), (61.3, 62.3), (97.0, 63.5)]
SLIP_ROAD = [(22.0, -46.8), (10.8, -48.8), (-0.6, -51.5), (-93.7, -72.7)]      # street level, on its bridge
ON_RAMP = [(-110.0, -66.0), (-64.5, -58.5), (10.5, -54.1), (35.6, -53.0), (60.2, -54.6), (96.3, -64.7)]
PERIPH = [(-77.8, -86.6), (-56.3, -80.2), (-38.1, -75.7), (-25.4, -73.3), (-12.6, -71.0), (0.8, -69.6), (13.9, -69.1),
          (28.1, -69.0), (43.8, -69.3), (58.9, -70.8), (90.0, -76.5)]
PERIPH_IN = [(107.8, -96.9), (87.4, -99.5), (74.1, -97.5), (65.0, -95.2), (46.6, -93.7), (25.6, -93.3), (10.8, -93.7),
             (-5.0, -95.3), (-24.2, -98.0), (-42.6, -102.2), (-70.9, -111.2)]
CUT_Y = -7.5                       # the peripherique in its cutting (S11: 7-8 m below rue Voltaire)
WALL_W, WALL_E = -48.0, 46.5       # gameplay walls: past Paritalie's north-west wing end, on the rue Emile Zola kerb


def build(B):
    _props.clear()
    lawn()
    near_buildings(B)
    other_buildings(B)
    pasteur_west(B)
    junction(B)
    rue_voltaire(B)
    cutting(B)
    salengro(B)
    walls(B)


# ------------------------------------------------------------------ generated grass texture
def lawn():
    """the verges' and embankments' grass seen from a few metres up, worn in patches, with October leaves on it:
    diff + nor_gl + arm 1k in assets/textures/campus_gen, one tile per 3 m (deterministic numpy, no download)"""
    import numpy as np
    G = os.path.join(T.TEX_DIR, "campus_gen")
    paths = [os.path.join(G, f"lawn_{m}_1k.jpg") for m in ("diff", "nor_gl", "arm")]
    if all(os.path.exists(p) and os.path.getsize(p) > 0 for p in paths):
        return
    os.makedirs(G, exist_ok=True)
    S_ = 1024
    rng = np.random.default_rng(57)

    def vnoise(k):
        """tileable value noise on a k x k lattice"""
        g = rng.random((k, k)).astype(np.float32)
        t = np.arange(S_, dtype=np.float32) * k / S_
        i0 = np.floor(t).astype(np.int64) % k
        i1 = (i0 + 1) % k
        f = t - np.floor(t)
        f = f * f * (3.0 - 2.0 * f)
        r0 = g[i0][:, i0] * (1 - f)[None, :] + g[i0][:, i1] * f[None, :]
        r1 = g[i1][:, i0] * (1 - f)[None, :] + g[i1][:, i1] * f[None, :]
        return r0 * (1 - f)[:, None] + r1 * f[:, None]

    # worn and lush patches small enough not to show the tile's repeat; the metre-scale variation is the vertex
    # colours' (macro)
    patch = 0.5 * vnoise(12) + 0.3 * vnoise(24) + 0.2 * vnoise(48)
    clump = vnoise(96)                                                   # tufts a few centimetres across
    # blades: white noise smeared along one of four directions, the direction changing from tuft to tuft
    w = rng.random((S_, S_)).astype(np.float32)
    pick = np.floor(np.mod(vnoise(48) * 7.0, 1.0) * 4.0).astype(np.int64)
    blades = np.zeros((S_, S_), np.float32)
    for k, (dy, dx) in enumerate(((1, 0), (0, 1), (1, 1), (1, -1))):
        acc = np.zeros((S_, S_), np.float32)
        for s in range(14):
            acc += np.roll(w, (s * dy, s * dx), (0, 1))
        blades = np.where(pick == k, acc / 14.0, blades)
    blades = np.clip((blades - 0.5) * 6.0 + 0.5, 0.0, 1.0)
    hgt = 0.6 * blades + 0.4 * clump
    dark, light = np.array([0.16, 0.22, 0.09], np.float32), np.array([0.44, 0.48, 0.23], np.float32)
    dry, soil = np.array([0.55, 0.50, 0.30], np.float32), np.array([0.30, 0.25, 0.17], np.float32)
    col = dark + (light - dark) * hgt[..., None]
    dry_m = np.clip((patch - 0.62) * 4.0, 0.0, 0.45)[..., None]
    col = col * (1 - dry_m) + dry * (0.75 + 0.35 * hgt[..., None]) * dry_m
    soil_m = np.clip((0.33 - patch) * 4.0, 0.0, 0.5)[..., None] * (1.0 - blades[..., None] * 0.6)
    col = col * (1 - soil_m) + soil * soil_m
    # fallen leaves: soft ellipses in muted October colours, wrapped round the tile edges
    leaf_cols = np.array([(0.50, 0.30, 0.13), (0.60, 0.45, 0.20), (0.38, 0.25, 0.12), (0.66, 0.54, 0.27)], np.float32)
    yy, xx = np.mgrid[-24:25, -24:25].astype(np.float32)
    leaf = np.zeros((S_, S_), np.float32)
    for _ in range(130):
        cy, cx = rng.integers(0, S_, 2)
        a, b, th = rng.uniform(9.0, 16.0), rng.uniform(4.5, 8.0), rng.uniform(0.0, np.pi)
        u = (xx * np.cos(th) + yy * np.sin(th)) / a
        v = (-xx * np.sin(th) + yy * np.cos(th)) / b
        m = np.clip((1.0 - (u * u + v * v)) * 3.0, 0.0, 0.85)
        ix = np.ix_((cy + np.arange(-24, 25)) % S_, (cx + np.arange(-24, 25)) % S_)
        c = leaf_cols[rng.integers(len(leaf_cols))] * rng.uniform(0.8, 1.1)
        col[ix] = col[ix] * (1 - m[..., None]) + c * m[..., None]
        leaf[ix] = np.maximum(leaf[ix], m)
    hgt = np.maximum(hgt, leaf * 0.9)
    gx = np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)
    gy = np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)
    nrm = np.stack([-gx * 3.0, gy * 3.0, np.ones_like(gx)], 2)
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    arm = np.stack([0.55 + 0.45 * hgt, 0.93 - 0.12 * leaf, np.zeros_like(hgt)], 2)
    for p, img in zip(paths, (col, nrm * 0.5 + 0.5, arm)):
        T._write_img(p, img)
        T.write_import_preset(p)


# ------------------------------------------------------------------ geometry helpers
def face_out(B, pts, mat, want):
    """B.face with its winding picked so the face's normal points along `want` (Newell normal, right-handed)"""
    n = [0.0, 0.0, 0.0]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    B.face(pts if n[0] * want[0] + n[1] * want[1] + n[2] * want[2] >= 0 else pts[::-1], mat)


def _nrm(a, b):
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    return (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)


def offset(line, d):
    """the polyline moved d metres to its right (a line heading +x moves to +z), mitred at the joints"""
    out = []
    n = len(line)
    for i in range(n):
        if i == 0:
            nx, nz = _nrm(line[0], line[1])
        elif i == n - 1:
            nx, nz = _nrm(line[-2], line[-1])
        else:
            n0, n1 = _nrm(line[i - 1], line[i]), _nrm(line[i], line[i + 1])
            mx, mz = n0[0] + n1[0], n0[1] + n1[1]
            ml = math.hypot(mx, mz) or 1.0
            mx, mz = mx / ml, mz / ml
            k = 1.0 / max(0.3, mx * n0[0] + mz * n0[1])
            nx, nz = mx * k, mz * k
        out.append((line[i][0] + nx * d, line[i][1] + nz * d))
    return out


def clip_line(line, lo, hi, key=0):
    """the part of a polyline where coordinate `key` (0 = x, 1 = z) lies between lo and hi"""
    out = []
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]
        ta, tb = a[key], b[key]
        if ta == tb:
            if lo <= ta <= hi:
                out += [a, b]
            continue
        t0 = max(0.0, min(1.0, (lo - ta) / (tb - ta)))
        t1 = max(0.0, min(1.0, (hi - ta) / (tb - ta)))
        t0, t1 = min(t0, t1), max(t0, t1)
        if t1 - t0 < 1e-6:
            continue
        p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
        p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
        if not out or math.hypot(out[-1][0] - p0[0], out[-1][1] - p0[1]) > 1e-6:
            out.append(p0)
        out.append(p1)
    return out


def at_z(line, z):
    """x of the polyline where it crosses z (first crossing)"""
    for a, b in zip(line, line[1:]):
        if (a[1] - z) * (b[1] - z) <= 0 and a[1] != b[1]:
            return a[0] + (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1])
    return line[-1][0]


def at_x(line, x):
    for a, b in zip(line, line[1:]):
        if (a[0] - x) * (b[0] - x) <= 0 and a[0] != b[0]:
            return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])
    return line[-1][1]


def up_poly(B, poly, y, mat, cell=None):
    """a flat polygon facing up (any winding), cut on a grid for the vertex colours when cell is given"""
    pieces = PG.grid_pieces(poly, cell) if cell else PG.triangulate(poly)
    for f in pieces:
        B.face([(x, y, z) for x, z in PG.cw(list(f))], mat)


def ribbon(B, line, d0, d1, y, mat, cell=None):
    """a strip between the offsets d0 and d1 of a polyline, facing up"""
    a, b = offset(line, d0), offset(line, d1)
    for i in range(len(line) - 1):
        q = [a[i], a[i + 1], b[i + 1], b[i]]
        if PG.length(q[0], q[1]) < 1e-4:
            continue
        up_poly(B, q, y, mat, cell)


def slab(B, line, d0, d1, y0, y1, mat, side=None):
    """a raised strip (kerb, island, pavement) along a polyline: top face + the two long sides"""
    ribbon(B, line, d0, d1, y1, mat)
    for d, s in ((d0, -1), (d1, 1)):
        o = offset(line, d)
        for i in range(len(o) - 1):
            p, q = (o[i], o[i + 1]) if s > 0 else (o[i + 1], o[i])
            xf, L = wall_frame(p[0], p[1], q[0], q[1])
            if L < 1e-3:
                continue
            with B.frame(xf):
                B.rect((0, y0, 0), (L, 0, 0), (0, y1 - y0, 0), side or mat)


def wall_line(B, line, y0, y1, mat, thick=0.0, top=None):
    """vertical faces along a polyline, facing its right-hand side"""
    for p, q in zip(line, line[1:]):
        xf, L = wall_frame(p[0], p[1], q[0], q[1])
        if L < 1e-3:
            continue
        with B.frame(xf):
            B.rect((0, y0, 0), (L, 0, 0), (0, y1 - y0, 0), mat)
            if thick:
                B.rect((0, y1, 0), (L, 0, 0), (0, 0, -thick), top or mat)


def poly_area(p):
    return abs(PG.area(p))


# ------------------------------------------------------------------ buildings
def block(B, poly, h, mat, kind, seed, gf_h=3.2, st=2.9, seen=None, lean=True, flat=False, bay=2.8, ww=1.3, wh=1.5,
          sill=0.9, lit=0.4, roof="M_roof_gravel", parapet=0.5, col=False, frame="M_pvc_white", rails=False,
          shutters=False, gf=None, gf_open=None, skip_gf=False):
    """a building on a real footprint: storeys of st over a ground floor of gf_h, a window grid on the faces
    seen(a, b, i) accepts. lean: interior panes in plain openings (the shader draws the frames); otherwise modelled
    frames; flat: panes laid on the wall without openings (far backdrop). gf_open(a, b, L, i) gives the openings of
    a face's own ground floor (None: the usual windows), and gf(B, a, b, L, i) then dresses it."""
    P = PG.cw(poly)
    storeys = [0.0] if not skip_gf else []
    y = gf_h
    while y + st <= h - 0.4:
        storeys.append(y)
        y += st
    wmat = "M_window_" + kind
    for i, (a, b) in enumerate(PG.edges(P)):
        L = PG.length(a, b)
        if L < 0.2:
            continue
        show = seen(a, b, i) if seen else True
        n = int((L - 0.6) // bay) if show and L > ww + 0.9 else 0
        m = (L - n * bay) / 2
        gfo = gf_open(a, b, L, i) if (gf_open and show) else None
        wins = []
        for si, fy in enumerate(storeys):
            if fy == 0.0 and gfo is not None:
                continue
            for k in range(n):
                wins.append((m + bay * (k + 0.5), fy + sill, fy + sill + wh, seed + i * 131 + si * 17 + k))
        if flat:
            xf, _ = wall_frame(a[0], a[1], b[0], b[1])
            with B.frame(xf):
                B.rect((0, 0, 0), (L, 0, 0), (0, h, 0), mat, sub=0)
                for (u, y0, y1, s) in wins:
                    interior_quad(B, u - ww / 2, u + ww / 2, y0, y1, 0.012, (wmat, s, lit))
            continue
        if lean:
            ops = [Opening(u - ww / 2, u + ww / 2, y0, y1, "blank") for (u, y0, y1, s) in wins]
        else:
            ops = [V.ext_win(u, ww, y0, y1, s, lit=lit, kind=kind, frame=frame, cols=2, sill="M_concrete",
                             rail="M_paint_metal_dark" if rails and y0 > 1.0 else None,
                             shutter=(0.0 if (s % 5) else 0.6) if shutters else None) for (u, y0, y1, s) in wins]
        V.fac(B, a[0], a[1], b[0], b[1], 0.0, h, 0.3, mat, False, ops + (gfo or []), top=False, ends=False, col=col)
        xf, _ = wall_frame(a[0], a[1], b[0], b[1])
        with B.frame(xf):
            if lean:
                for (u, y0, y1, s) in wins:
                    interior_quad(B, u - ww / 2, u + ww / 2, y0, y1, -0.13, (wmat, s, lit))
                    B.box(u - ww / 2 - 0.04, y0 - 0.06, -0.02, u + ww / 2 + 0.04, y0, 0.05, "M_concrete")
            if parapet:
                B.box(-0.03, h, -0.33, L + 0.03, h + 0.06, 0.04, "M_zinc")
            if gf and gfo is not None:
                gf(B, a, b, L, i)
    B.prism(P, h - 0.3, h, roof, top=True, sides=False)


def _faces_street(a, b, i):
    """faces whose outside looks south-ish or east-west (not the party walls toward the campus)"""
    return True


def near_buildings(B):
    """the neighbours seen from the playable streets, on their real outlines"""
    rng = random.Random(5)
    B.use("bd_arpej")
    B.use_col("COL_buildings")
    # ARPEJ, 21 rue Pasteur: white render, 9 storeys on rue Pasteur and rue Emile Zola, the glazed ground
    # floor and its "Porte d'Italie - Residence etudiante" sign; KB1 and the box lean on its west side
    def arpej_seen(a, b, i):
        n = PG.outward(a, b)
        if n[0] < -0.7 and a[0] < 23.8:
            return False                            # party wall with KB1
        return not (23.0 < (a[0] + b[0]) / 2 < 30.8 and -28.2 < (a[1] + b[1]) / 2 < -18.5)   # its light court

    def arpej_open(a, b, L, i):
        if PG.outward(a, b)[1] < 0.7:
            return None
        return [Opening(2.0 + 3.0 * k - 1.4, 2.0 + 3.0 * k + 1.4, 0.15, 3.0, "blank") for k in range(int((L - 1.0) // 3.0))]

    def arpej_gf(B_, a, b, L, i):
        # street side: shop-front glazing of the residence's entrance hall and common rooms, the sign above
        for k in range(int((L - 1.0) // 3.0)):
            u = 0.5 + 3.0 * (k + 0.5)
            A.frame_rect(B_, u - 1.4, u + 1.4, 0.15, 3.0, -0.18, -0.08, 0.07, "M_alu_anthracite")
            interior_quad(B_, u - 1.33, u + 1.33, 0.22, 2.93, -0.14, ("M_window_office", 3300 + k, 0.8))
        B_.box(0.0, 3.0, 0.0, L, 3.25, 0.12, "M_concrete")
        if L > 10.0:
            with B_.at(L * 0.62, 3.55, 0.03):
                B_.box(-2.6, -0.32, -0.02, 2.6, 0.32, 0.0, "M_plate_white")
                B_.text("PORTE D'ITALIE", V_font("bold"), 0.26, "M_sign_rose", align="CENTER", valign="CENTER", depth=0.012,
                        maxw=4.9)
            with B_.at(L * 0.62, 3.06, 0.13):
                B_.text("Résidence étudiante", V_font("semi"), 0.14, "M_sign_rose", align="CENTER", valign="BOTTOM",
                        depth=0.008)
    for name, h in (("ARPEJ_W", 24.9), ("ARPEJ_CORNER", 24.9), ("ARPEJ_MID", 22.2), ("ARPEJ_N", 19.5), ("ARPEJ_BACK", 18.4)):
        poly = NAMED[name]
        street = name in ("ARPEJ_W", "ARPEJ_CORNER")
        block(B, poly, h, "M_render_arpej", "flat", 3000 + len(name) * 37, gf_h=3.3, st=2.7, seen=arpej_seen,
              lean=not street, bay=3.0, ww=1.3, wh=1.45, sill=0.85, lit=0.5, gf=arpej_gf if street else None,
              gf_open=arpej_open if street else None, frame="M_pvc_white")
    for name in ("ARPEJ_W", "ARPEJ_CORNER"):
        B.cprism(NAMED[name], -0.5, 25.0)
    # 13-17 rue Pasteur: the white 2021 block with balconies, 7 storeys, 19.5 m; its east side is KB1's party
    # wall, rising above KB1's parapet
    B.use("bd_1317")
    N = NAMED["N1317"]

    def n1317_seen(a, b, i):
        n = PG.outward(a, b)
        return not (n[0] > 0.7)

    def n1317_open(a, b, L, i):
        if PG.outward(a, b)[1] < 0.7:
            return None
        ops = [Opening(L / 2 - 1.1, L / 2 + 1.1, 0.0, 2.7, "blank")]
        return ops + [Opening(u - 0.7, u + 0.7, 1.2, 2.7, "blank") for u in [1.6 + 3.0 * k for k in range(int((L - 2.0) // 3.0))]
                      if abs(u - L / 2) >= 2.4]

    def n1317_gf(B_, a, b, L, i):
        # entrance hall in the middle, ground-floor flats behind high sills
        A.frame_rect(B_, L / 2 - 1.1, L / 2 + 1.1, 0.0, 2.7, -0.2, -0.1, 0.08, "M_alu_anthracite", bottom=False)
        interior_quad(B_, L / 2 - 1.02, L / 2 + 1.02, 0.02, 2.62, -0.16, ("M_window_office", 3500, 0.9))
        for u in [1.6 + 3.0 * k for k in range(int((L - 2.0) // 3.0))]:
            if abs(u - L / 2) < 2.4:
                continue
            A.frame_rect(B_, u - 0.7, u + 0.7, 1.2, 2.7, -0.2, -0.1, 0.06, "M_alu_anthracite")
            interior_quad(B_, u - 0.64, u + 0.64, 1.26, 2.64, -0.16, ("M_window_flat", 3510 + int(u), 0.45))
        B_.box(0.0, 0.0, 0.0, L, 0.45, 0.03, "M_concrete_dark", skip="nb")
    block(B, N, 19.5, "M_render_1317", "flat_tall", 3600, gf_h=3.0, st=2.75, seen=n1317_seen, lean=False, bay=3.0,
          ww=1.6, wh=2.25, sill=0.05, lit=0.5, gf=n1317_gf, gf_open=n1317_open, frame="M_alu_anthracite")
    # balconies on the street face: slabs and glass railings in a staggered pattern
    a, b = (-51.1, -5.5), (-29.2, -5.1)
    xf, L = wall_frame(a[0], a[1], b[0], b[1])
    with B.frame(xf):
        n = int((L - 0.6) // 3.0)
        m = (L - n * 3.0) / 2
        for si in range(6):
            fy = 3.0 + si * 2.75
            for k in range(n):
                if (k + si) % 2:
                    continue
                u = m + 3.0 * (k + 0.5)
                B.box(u - 1.35, fy - 0.12, 0.0, u + 1.35, fy + 0.04, 1.0, "M_render_1317")
                B.quad((u - 1.3, fy + 0.04, 0.98), (u + 1.3, fy + 0.04, 0.98), (u + 1.3, fy + 1.05, 0.98),
                       (u - 1.3, fy + 1.05, 0.98), "M_glass_railing", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
                B.box(u - 1.35, fy + 1.02, 0.95, u + 1.35, fy + 1.07, 1.01, "M_alu_silver")
    B.cprism(N, -0.5, 19.5)
    # 11 rue Pasteur: 5 storeys, 16.6 m, older render with roller shutters; the block behind it
    B.use("bd_west")
    block(B, NAMED["N11"], 16.6, "M_render_beige", "flat", 3700, gf_h=3.4, st=2.9, lean=False, bay=2.6, ww=1.2, wh=1.5,
          sill=0.9, lit=0.45, frame="M_pvc_white", shutters=True, rails=True)
    block(B, NAMED["N11_BACK"], 9.0, "M_far_grey", "flat_lean", 3720, lit=0.35)
    # Paritalie's west annex (x -66.9..-54.1, 3 storeys, 9.1 m; docs/CAMPUS_LAYOUT.md §3.3): offices in grey render
    block(B, NAMED["ANNEX"], 9.1, "M_render_grey", "office", 3740, gf_h=3.1, st=2.8, lean=False, bay=2.8, ww=1.8, wh=1.5,
          sill=0.85, lit=0.45, frame="M_alu_anthracite")
    # Paritalie's south gate porch (light structure, 14.6 m with its frame) on rue Roger Salengro
    B.use("far_south")
    g = PG.cw(NAMED["GATE_S"])
    for (x, z) in g:
        B.box(x - 0.15, 0.0, z - 0.15, x + 0.15, 9.0, z + 0.15, "M_paint_metal_dark", skip="b")
    B.prism(g, 9.0, 9.4, "M_paint_metal_dark", top=True, sides=True)
    # 32 rue Pasteur: 6 storeys, the Francoise Dolto creche on the corner; the block behind it on rue Emile Zola.
    # Everything east of the junction is out of reach and its shadows fall away from the campus: a far_ part
    B.use("far_pasteur_e")

    def p32_gf(B_, a, b, L, i):
        if L < 4.0:
            return
        for k in range(int((L - 1.0) // 2.6)):
            u = 0.5 + 2.6 * (k + 0.5)
            interior_quad(B_, u - 1.05, u + 1.05, 0.4, 2.7, 0.012, ("M_window_office", 3800 + i * 7 + k, 0.7))
    block(B, NAMED["P32"], 15.9, "M_render_white", "flat_lean", 3820, gf_h=3.4, st=2.5, bay=2.8, lit=0.45, gf=p32_gf,
          gf_open=lambda a, b, L, i: [] if L >= 4.0 else None)
    # the creche's name on the corner over rue Pasteur
    with B.at(59.8, 3.15, 9.0, math.atan2(1.0, -1.2)):
        B.box(-1.6, -0.25, -0.02, 1.6, 0.25, 0.0, "M_plate_white")
        B.text("Crèche Françoise Dolto", V_font("semi"), 0.16, "M_epita_blue", align="CENTER", valign="CENTER",
               depth=0.008, maxw=3.0)
    block(B, NAMED["P32_SOUTH"], 12.0, "M_far_beige", "flat_lean", 3840, lit=0.4)
    # the hotels, 20-22 rue Voltaire: 27.2 m, curtains drawn
    block(B, NAMED["HOTELS"], 27.2, "M_render_grey", "hotel", 3900, gf_h=3.6, st=2.95, bay=2.6, ww=1.4, wh=1.6, sill=0.8,
          lit=0.55)
    B.prism(NAMED["KIOSK"], 0.0, 2.6, "M_paint_metal_green", top=True, sides=True)
    # the two blocks on rue Roger Salengro west of Paritalie
    B.use("far_south")
    block(B, NAMED["SAL_W1"], 14.0, "M_far_beige", "flat_lean", 3950, flat=True, lit=0.4, roof="M_far_roof", parapet=0)
    block(B, NAMED["SAL_W2"], 11.5, "M_far_grey", "flat_lean", 3970, flat=True, lit=0.4, roof="M_far_roof", parapet=0)


def V_font(name):
    import campus_gen
    return campus_gen.font(name)


def other_buildings(B):
    """every other outline of docs/campus_layout.svg within reach of the eye, as plain blocks: heights from the footprint
    (no data; a shed, a house, a block of flats), windows laid flat on the walls"""
    mats = ("M_far_beige", "M_far_grey", "M_far_white", "M_far_brick")
    for i, poly in enumerate(OTHERS):
        ar = poly_area(poly)
        cx = sum(p[0] for p in poly) / len(poly)
        cz = sum(p[1] for p in poly) / len(poly)
        rng = random.Random(int(cx * 7.3 + cz * 13.1) & 0xFFFF)
        if ar < 25:
            h = 3.2
        elif ar < 70:
            h = 3.2 + 2.9 * rng.choice((1, 2, 2))
        elif ar < 160:
            h = 3.2 + 2.9 * rng.choice((2, 3, 4))
        elif ar < 450:
            h = 3.2 + 2.9 * rng.choice((3, 4, 5, 6))
        else:
            h = 3.2 + 2.9 * rng.choice((5, 6, 7))
        part = "far_south" if cz > 45 else ("far_north" if cz < -40 else ("far_west" if cx < 0 else "far_east"))
        B.use(part)
        block(B, poly, h, mats[rng.randrange(len(mats))], "flat_lean", 5000 + i * 53, flat=True, bay=2.9, ww=1.3,
              wh=1.5, lit=0.35, roof="M_far_roof", parapet=0, gf_h=3.2, st=2.9)
    # the bent rue Pasteur runs on past the outlines' reach: a row of plain blocks closes its vista where it bends again
    B.use("far_east")
    for k, (x0, x1, z0, z1, h) in enumerate(((150.0, 172.0, -52.0, -30.0, 19.0), (152.0, 170.0, -30.0, -8.0, 16.0),
                                             (148.0, 168.0, -8.0, 18.0, 21.0))):
        block(B, [(x0, z0), (x1, z0), (x1, z1), (x0, z1)], h, mats[(k + 1) % 4], "flat_lean", 6100 + k * 41, flat=True,
              lit=0.4, roof="M_far_roof", parapet=0)
    # avenue de Fontainebleau's far side closes the long view west down rue Pasteur
    B.use("far_west")
    for k, (z0, z1, h) in enumerate(((-70, -38, 19.0), (-38, -12, 22.0), (-12, 8, 17.0), (8, 32, 21.0), (32, 70, 18.0))):
        block(B, [(-215.0, z0), (-190.0, z0), (-190.0, z1), (-215.0, z1)], h, mats[k % 4], "flat_lean", 6000 + k * 41,
              flat=True, lit=0.4, roof="M_far_roof", parapet=0)


# ------------------------------------------------------------------ rue Pasteur west of the playable street
def pasteur_west(B):
    B.use("far_street_w")
    x0, x1 = -186.0, S.X_W
    with B.ground_at(0.0):
        B.box(x0, -0.3, S.CURB_N, x1, 0.0, S.CURB_S, "M_far_asphalt", skip="nsewb", sub=0)
        for (z0, z1) in ((S.SIDE_N, S.CURB_N), (S.CURB_S, S.SIDE_S)):
            B.box(x0, -0.3, z0, x1, S.SW_TOP, z1, "M_sidewalk", skip="nsewb", sub=0)
        for z in (S.CURB_N, S.CURB_S):
            B.box(x0, -0.3, z - 0.1, x1, S.SW_TOP, z + 0.1, "M_curb", skip="nsewb", sub=0)
            B.rect((x0, 0.0, z + (0.1 if z > 0 else -0.1)), (x1 - x0, 0, 0), (0, S.SW_TOP, 0), "M_curb")
        x = x0 + 2.0
        while x < x1 - 3.0:
            B.box(x, 0.0, S.BIKE_Z - 0.06, x + 3.0, 0.004, S.BIKE_Z + 0.06, "M_road_paint", skip="nsewb")
            x += 4.5
        # avenue de Fontainebleau, 12 m between its kerbs
        B.box(-182.0, -0.3, -80.0, -170.0, -0.002, 80.0, "M_far_asphalt", skip="nsewb", sub=0)
        for (a, b) in ((-190.0, -182.0), (-170.0, -166.0)):
            for (z0, z1) in ((-80.0, S.SIDE_N), (S.SIDE_S, 80.0)):
                B.box(a, -0.3, z0, b, S.SW_TOP, z1, "M_sidewalk", skip="nsewb", sub=0)
        B.box(-190.0, -0.3, S.SIDE_N, -182.0, S.SW_TOP, S.SIDE_S, "M_sidewalk", skip="nsewb", sub=0)
    for x in (-86.0, -102.0, -118.0, -134.0, -150.0):
        S_prop(B, "street_lamp", x, 0.1, -3.62, 0.0)
    for x in (-92.0, -110.0, -128.0):
        S_prop(B, "tree_plane", x, 0.1, 3.85, PI)


_props = {}


def S_prop(B, asset, x, y, z, yaw=0.0):
    """a PROP_ marker like campus_dress.prop(), numbered on its own (build_campus reloads campus_dress after the
    backdrop is built, which would restart its numbering and give two markers the same name)"""
    n = _props.get(asset, 0)
    _props[asset] = n + 1
    # beyond the playable streets: no shadow pass for them (LevelBinder reads `shadow`)
    B.marker("PROP_%s__bd%02d" % (asset, n), (x, y, z), yaw, {"asset": asset, "shadow": False}, display="ARROWS", size=0.25)


# ------------------------------------------------------------------ rue Emile Zola and the bend of rue Pasteur
def junction(B):
    """the rue Emile Zola junction at the east end of the playable street, and rue Pasteur's 12-degree bend
    beyond it; the walkable corners in front of ARPEJ and the east building get colliders"""
    B.use("bd_junction")
    B.use_col("COL_street")
    with B.ground_at(0.0):
        # carriageways: rue Emile Zola from rue Voltaire to rue Roger Salengro, rue Pasteur's bent arm
        B.box(S.X_E, -0.3, -40.0, 56.0, -0.002, 58.0, "M_asphalt", skip="nsewb", sub=6.0)
        ribbon(B, AXIS_PASTEUR_E, -2.6, 2.2, -0.004, "M_asphalt", cell=6.0)
        # pavements: the corners in front of ARPEJ and the east building (walkable up to the gameplay wall)
        nw = [(42.4, -5.0), (44.7, -7.1), (44.2, -13.0), (47.2, -13.0), (47.3, -8.5), (47.1, -5.0)]
        sw = [(40.8, 5.0), (45.6, 9.6), (45.85, 14.5), (47.65, 14.5), (47.4, 8.2), (47.0, 5.0)]
        for poly in (nw, sw):
            B.prism(poly, 0.0, S.SW_TOP, "M_sidewalk", top=True, sides=True, side_mat="M_curb")
            B.cprism(poly, -0.6, S.SW_TOP)
        # pavements beyond the corners (out of reach): rue Emile Zola's sides, the bent street's sides
        zn = clip_line(ZOLA_N, -36.9, -13.0, key=1)
        slab(B, zn, -7.0, -2.5, -0.1, S.SW_TOP + 0.002, "M_sidewalk", side="M_curb")
        slab(B, clip_line(ZOLA_N, -36.9, -3.5, key=1), 2.5, 6.5, -0.1, S.SW_TOP + 0.004, "M_sidewalk", side="M_curb")
        zs = clip_line(ZOLA_S, 14.5, 53.2, key=1)
        slab(B, zs, 2.5, 6.5, -0.1, S.SW_TOP + 0.002, "M_sidewalk", side="M_curb")
        slab(B, clip_line(ZOLA_S, 2.6, 56.0, key=1), -7.5, -2.5, -0.1, S.SW_TOP + 0.004, "M_sidewalk", side="M_curb")
        pe = clip_line(AXIS_PASTEUR_E, 52.1, 122.0, key=0)
        slab(B, pe, -8.5, -2.6, -0.1, S.SW_TOP + 0.006, "M_sidewalk", side="M_curb")
        slab(B, pe, 2.2, 9.0, -0.1, S.SW_TOP + 0.008, "M_sidewalk", side="M_curb")
        # the five zebra crossings round the junction
        zebra(B, 44.7, -0.6, 0.0, 2.4, 4.8)            # across rue Pasteur, west arm (in the playable street)
        zebra(B, 49.9, 8.2, PI / 2, 2.4, 5.0)          # rue Emile Zola, south arm
        zebra(B, 49.8, -8.5, PI / 2, 2.4, 5.0)         # north arm
        zebra(B, 49.2, -33.5, PI / 2, 2.4, 5.0)        # by rue Voltaire
        yaw_e = -math.atan2(-1.5, 7.4)
        zebra(B, 56.8, -2.3, yaw_e, 2.4, 4.8)           # rue Pasteur, east arm
        # the eastbound cycle lane's line and a westbound arrow carry on round the bend
        x = 53.0
        while x < 118.0:
            z = at_x(offset(AXIS_PASTEUR_E, 0.35), x)
            z2 = at_x(offset(AXIS_PASTEUR_E, 0.35), x + 3.0)
            B.seg_box(x, z, x + 3.0, z2, 0.0, 0.004, 0.12, "M_road_paint", skip="nsewb")
            x += 4.5
    # lamps on the north side, a light on the junction
    for (x, d) in ((54.0, -3.4), (70.0, -3.4), (86.0, -3.4), (102.0, -3.4)):
        z = at_x(offset(AXIS_PASTEUR_E, d), x)
        S_prop(B, "street_lamp", x, 0.1, z, math.atan2(1.5, 7.4) * 0)
    V.light(B, "street_zola", 52.0, 4.85, -3.0, K(3000), 2.2, 14.0)
    for (x, z) in ((46.2, 15.5), (46.6, 24.0), (47.1, 33.0)):
        S_prop(B, "bollard", x + 1.1, 0.1, z, 0.0)


def zebra(B, x, z, yaw, w, L):
    """zebra crossing centred on (x, z): bands of 0.5 m every metre across a road of width L, w long; yaw turns it
    (0: road along x)"""
    with B.at(x, 0.0, z, yaw):
        n = int(L)
        for k in range(n):
            z0 = -L / 2 + 0.25 + k * 1.0
            B.box(-w / 2, 0.0, z0, w / 2, 0.006, min(z0 + 0.5, L / 2), "M_road_paint", skip="nsewb")


# ------------------------------------------------------------------ rue Voltaire and the cutting
def rue_voltaire(B):
    B.use("bd_voltaire")
    v = clip_line(AXIS_VOLTAIRE, -160.0, 105.0)
    with B.ground_at(0.0):
        ribbon(B, v, -2.4, 2.9, 0.0, "M_asphalt", cell=8.0)
        slab(B, v, 2.9, 6.0, -0.1, 0.1, "M_sidewalk", side="M_curb")
        slab(B, v, -2.75, -2.4, -0.1, 0.1, "M_curb")
        # parking lane line and a few cars along the KB1 side (Panoramax 30 Jun 2025: parking on the KB1 side)
        o = offset(v, 0.9)
        for p, q in zip(o, o[1:]):
            if p[0] > -60.0 and q[0] < 40.0:
                B.seg_box(p[0], p[1], q[0], q[1], 0.0, 0.004, 0.1, "M_road_paint", skip="nsewb")
        # the north verge with its trees, out to the slip road
        kerb = offset(clip_line(AXIS_VOLTAIRE, -95.0, 22.0), -2.75)          # west -> east
        slip_s = offset(clip_line(SLIP_ROAD, -95.0, 22.0), -3.5)             # the slip road runs east -> west
        verge = kerb + slip_s
        if poly_area(verge) > 1.0:
            up_poly(B, verge, 0.05, "M_verge", cell=6.0)
        # east of the slip road the verge runs on to rue Emile Zola, up to the balustrade over the cutting
        east = offset(clip_line(AXIS_VOLTAIRE, 22.0, 49.0), -2.75) + [(49.0, -49.0), (40.0, -48.6), (22.0, -50.3)]
        up_poly(B, east, 0.05, "M_verge", cell=6.0)
    for x in (-69.0, -58.0, -47.0, -36.0, -25.8, -18.9, -11.5, 2.0, 12.0):
        z = at_x(AXIS_VOLTAIRE, x) - 5.4
        # set 1.6 cm down so the street tree's grate (1.4 cm high) stays under the grass
        S_prop(B, "tree_plane", x, 0.034, z, 0.0)
    # low shrubs along the verge between the trees
    rng = random.Random(41)
    x = -66.0
    while x < 18.0:
        z = at_x(AXIS_VOLTAIRE, x) - 3.9 - rng.uniform(0.0, 0.7)
        foliage(B, (x, 0.5, z), (1.3, 0.42, 0.6), 7, 0.85, "M_leaves_plane", rng, bias=0.6)
        x += rng.uniform(3.0, 5.5)
    # LED lamps on the south pavement (OSM), the arm over the road
    for (x, z) in ((13.4, -38.0), (-19.6, -40.2)):
        S_prop(B, "street_lamp", x, 0.1, z, PI)
        V.light(B, "rue_voltaire_%+03d" % int(x), x, 4.85, z - 0.8, K(3000), 2.2, 14.0)
    for (x, kind) in ((-24.0, "car_hatch_blue"), (-8.0, "car_sedan_white"), (5.5, "car_hatch_red"), (30.5, "car_sedan_green")):
        z = at_x(offset(AXIS_VOLTAIRE, 1.9), x)
        S_prop(B, kind, x, 0.0, z, PI / 2 - 0.085)
    # the slip road at street level on its bridge, then down toward the peripherique past the limestone wall
    B.use("bd_slip")
    with B.ground_at(0.0):
        s = SLIP_ROAD
        a, b = offset(s, -3.5), offset(s, 3.5)
        for i in range(len(s) - 1):
            y0, y1 = _slip_y(s[i][0]), _slip_y(s[i + 1][0])
            if y0 == y1:
                up_poly(B, [a[i], a[i + 1], b[i + 1], b[i]], y0, "M_asphalt", cell=8.0)
            else:
                xs = [s[i][0] + (s[i + 1][0] - s[i][0]) * t / 8 for t in range(9)]
                for k in range(8):
                    ta, tb = k / 8, (k + 1) / 8
                    pa = [(a[i][0] + (a[i + 1][0] - a[i][0]) * t, a[i][1] + (a[i + 1][1] - a[i][1]) * t) for t in (ta, tb)]
                    pb = [(b[i][0] + (b[i + 1][0] - b[i][0]) * t, b[i][1] + (b[i + 1][1] - b[i][1]) * t) for t in (ta, tb)]
                    ya, yb = _slip_y(xs[k]), _slip_y(xs[k + 1])
                    pts = [(pa[0][0], ya, pa[0][1]), (pa[1][0], yb, pa[1][1]), (pb[1][0], yb, pb[1][1]), (pb[0][0], ya, pb[0][1])]
                    B.face(pts if _normal_up(pts) else pts[::-1], "M_asphalt")
        # balustrade on the edge of the cutting: along the slip road, then behind rue Voltaire's verge
        edge = offset(clip_line(SLIP_ROAD, -45.0, 22.0), 3.6) + [(40.0, -48.6), (75.0, -50.0), (105.0, -58.0)]
        edge = sorted(edge, key=lambda p: p[0])
        for p, q in zip(edge, edge[1:]):
            B.seg_box(p[0], p[1], q[0], q[1], 0.0, 1.0, 0.25, "M_balustrade")
            B.seg_box(p[0], p[1], q[0], q[1], 1.0, 1.08, 0.32, "M_balustrade")
        # the rough limestone retaining wall where the slip road goes down (west end of the view north)
        low = offset(clip_line(SLIP_ROAD, -95.0, -45.0), -3.7)
        wall_line(B, low[::-1], CUT_Y, 0.4, "M_limestone_rough", thick=0.5)


def _slip_y(x):
    return 0.0 if x >= -45.0 else max(CUT_Y + 1.0, (x + 45.0) * 0.14)


def _normal_up(pts):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = pts[0], pts[1], pts[2]
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    return (uz * vx - ux * vz) > 0


FAR_EDGE = [(140.0, -104.0), (60.0, -101.0), (20.0, -100.0), (-20.0, -103.0), (-60.0, -114.0), (-160.0, -128.0)]


def cutting(B):
    """the peripherique 7-8 m down in its cutting, mostly hidden behind the balustrade, the on-ramp, the far
    side's planted embankment with a row of trees along its crest and, beyond, the RATP workshop's sheds under red
    barrel vaults and the 13th arrondissement"""
    B.use("far_north")
    rng = random.Random(61)
    top = offset(FAR_EDGE, 5.0)          # the edge runs west, so +d is north: the embankment's crest at street level
    with B.ground_at(CUT_Y):
        up_poly(B, [(-160.0, -50.0), (140.0, -50.0)] + FAR_EDGE, CUT_Y, "M_far_ground")
        ribbon(B, PERIPH, -7.0, 7.0, CUT_Y + 0.01, "M_far_asphalt")
        ribbon(B, PERIPH_IN, -7.0, 7.0, CUT_Y + 0.01, "M_far_asphalt")
        ribbon(B, ON_RAMP, -3.5, 3.5, CUT_Y + 1.5, "M_far_asphalt")
        slab(B, ON_RAMP, -3.8, 3.8, CUT_Y, CUT_Y + 1.49, "M_far_ground")
        for line in (PERIPH, PERIPH_IN):
            for d in (-7.3, 7.3):
                slab(B, offset(line, d), -0.25, 0.25, CUT_Y, CUT_Y + 0.8, "M_balustrade")
            # four lanes each way: dashed lane lines (3 m dashes, 10 m gaps)
            for d in (-3.5, 0.0, 3.5):
                o = offset(line, d)
                for p, q in zip(o, o[1:]):
                    L = PG.length(p, q)
                    for k in range(int(L // 13.0)):
                        t0, t1 = k * 13.0 / L, (k * 13.0 + 3.0) / L
                        B.seg_box(p[0] + (q[0] - p[0]) * t0, p[1] + (q[1] - p[1]) * t0, p[0] + (q[0] - p[0]) * t1,
                                  p[1] + (q[1] - p[1]) * t1, CUT_Y + 0.01, CUT_Y + 0.016, 0.12, "M_road_paint",
                                  skip="nsewb")
        # the near side's retaining wall under the balustrade, facing the cutting (out of sight from the campus)
        near = sorted(offset(clip_line(SLIP_ROAD, -45.0, 22.0), 3.6) + [(40.0, -48.6), (75.0, -50.0), (105.0, -58.0)])
        wall_line(B, near[::-1], CUT_Y, 0.0, "M_far_grey")
        # the far side: a steep grassed embankment back up to street level (a bare wall there read as a sound wall),
        # cut in 6 m pieces so the vertex colours vary along it
        lerp = lambda p, q, t: (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
        for i in range(len(FAR_EDGE) - 1):
            a, b, c, d = FAR_EDGE[i], FAR_EDGE[i + 1], top[i + 1], top[i]
            n = max(1, int(math.ceil(PG.length(a, b) / 6.0)))
            for k in range(n):
                t0, t1 = k / n, (k + 1) / n
                lo0, lo1, hi1, hi0 = lerp(a, b, t0), lerp(a, b, t1), lerp(d, c, t1), lerp(d, c, t0)
                face_out(B, [(lo0[0], CUT_Y, lo0[1]), (lo1[0], CUT_Y, lo1[1]), (hi1[0], 0.0, hi1[1]),
                             (hi0[0], 0.0, hi0[1])], "M_verge", (0.0, 0.6, 1.0))
                # self-sown shrubs on the slope
                if rng.random() < 0.75:
                    s, h = rng.uniform(0.15, 0.85), rng.uniform(0.25, 0.75)
                    p = lerp(lerp(a, b, t0 + s * (t1 - t0)), lerp(d, c, t0 + s * (t1 - t0)), h)
                    foliage(B, (p[0], CUT_Y * (1.0 - h) + 0.7, p[1]), (rng.uniform(1.2, 2.2), 0.9, 1.1), 7, 1.3,
                            "M_leaves_plane", rng, bias=0.6)
    with B.ground_at(0.0):
        # the ground beyond, out under the city blocks (gaps between sheds and blocks must not show the void)
        up_poly(B, top + [(-200.0, top[-1][1]), (-200.0, -300.0), (175.0, -300.0), (175.0, top[0][1])], 0.0,
                "M_far_ground")
        # a row of trees and shrubs along the crest breaks the long horizontal lines of the view north
        x = -152.0
        while x < 136.0:
            z = at_x(top, x) - rng.uniform(1.0, 3.5)
            if rng.random() < 0.8:
                far_tree(B, x, z, rng.uniform(8.5, 13.0), rng)
            else:
                foliage(B, (x, 1.2, z), (2.4, 1.3, 1.6), 9, 1.6, "M_leaves_plane", rng, bias=0.6)
            x += rng.uniform(6.5, 11.0)
        # the RATP line 7 workshop (Atelier de Choisy): two rows of sheds with gaps between them
        for (x0, x1) in ((-98.0, -62.0), (-56.0, -18.0), (-12.0, 30.0), (36.0, 84.0)):
            zs = min(at_x(top, x0), at_x(top, x1)) - 6.0
            shed(B, x0, x1, zs, zs - 17.0, rng)
        for (x0, x1) in ((-86.0, -40.0), (-34.0, 18.0), (24.0, 76.0)):
            zs = min(at_x(top, x0), at_x(top, x1)) - 27.0
            shed(B, x0, x1, zs, zs - 17.0, rng)
        # the 13th arrondissement beyond (Porte d'Italie): along the boulevard, a near-continuous row of 7-storey
        # brick blocks of flats (the 1930s HBM ring: red brick, a light band under the top storey); behind them
        # towers and slabs of mixed heights, so the skyline is never a regular row
        rng = random.Random(77)
        x, k = -180.0, 0
        while x < 165.0:
            w = rng.uniform(26.0, 48.0)
            z1 = -182.0 - rng.uniform(0.0, 5.0)
            h = 3.4 + 2.85 * rng.choice((6, 7, 7, 8))
            mat = ("M_far_brick", "M_far_brick", "M_far_beige")[rng.randrange(3)]
            block(B, [(x, z1 - 12.0), (x + w, z1 - 12.0), (x + w, z1), (x, z1)], h, mat, "flat_lean", 6500 + k * 61,
                  flat=True, lit=0.45, roof="M_far_roof", parapet=0, bay=2.9, ww=1.2)
            if mat == "M_far_brick":
                B.box(x - 0.1, h - 3.05, z1 - 12.1, x + w + 0.1, h - 2.75, z1 + 0.12, "M_far_white", skip="b")
            x += w + rng.uniform(5.0, 14.0)
            k += 1
        x = -170.0
        while x < 160.0:
            tower = rng.random() < 0.45
            w, d = (rng.uniform(16.0, 22.0), rng.uniform(15.0, 20.0)) if tower else (rng.uniform(28.0, 44.0), rng.uniform(11.0, 14.0))
            h = 3.2 + 2.9 * (rng.randrange(14, 22) if tower else rng.randrange(8, 13))
            z1 = -206.0 - rng.uniform(0.0, 40.0)
            ribbon_glazing = not tower and rng.random() < 0.4      # 1970s slabs with continuous window bands
            bay = 2.4 if ribbon_glazing else rng.choice((2.6, 2.9, 3.3))
            block(B, [(x, z1 - d), (x + w, z1 - d), (x + w, z1), (x, z1)], h,
                  ("M_far_white", "M_far_grey", "M_far_beige", "M_far_white")[rng.randrange(4)], "flat_lean", 6500 + k * 61,
                  flat=True, lit=0.45, roof="M_far_roof", parapet=0, bay=bay,
                  ww=2.38 if ribbon_glazing else rng.choice((1.1, 1.3, 1.6)), wh=1.3 if ribbon_glazing else 1.5)
            # lift and plant rooms on the roof
            for j in range(rng.choice((1, 1, 2))):
                cx = x + w * rng.uniform(0.2, 0.75)
                cz = z1 - d * rng.uniform(0.3, 0.7)
                B.box(cx, h, cz - 1.6, cx + rng.uniform(3.0, 6.0), h + rng.uniform(2.2, 3.2), cz + 1.6, "M_far_grey",
                      skip="b", sub=0)
            x += w + rng.uniform(6.0, 22.0)
            k += 1


def far_tree(B, x, z, h, rng, y=0.0):
    """a cheap tree for the far backdrop, built into the far mesh: a trunk and a crown of large leaf cards"""
    B.cyl(x, y, z, 0.2, h * 0.5, "M_bark_plane", seg=6, caps=(False, False), r2=0.12)
    foliage(B, (x, y + h * 0.66, z), (h * 0.3, h * 0.27, h * 0.3), 30, h * 0.26, "M_leaves_plane", rng, bias=0.55)


def shed(B, x0, x1, zs, zn, rng):
    """a shed of the RATP line 7 workshop, z from zs (south) to zn: low ribbed walls with a band of high windows
    and pilasters, two red barrel vaults along its length; across the cutting the vaults' rise is what reads"""
    wall, rise, seg = 3.4, 2.6, 8
    roof = "M_roof_barrel" if rng.random() < 0.6 else "M_roof_barrel_2"
    B.box(x0, 0.0, zn, x1, wall, zs, "M_far_shed", skip="bt", sub=0)
    face_out(B, [(x0 + 0.5, 2.25, zs + 0.02), (x1 - 0.5, 2.25, zs + 0.02), (x1 - 0.5, 3.0, zs + 0.02),
                 (x0 + 0.5, 3.0, zs + 0.02)], "M_spandrel_dark", (0.0, 0.0, 1.0))
    n = max(1, int((x1 - x0) // 6.0))
    for k in range(n + 1):
        xp = x0 + (x1 - x0) * k / n
        B.box(xp - 0.18, 0.0, zs, xp + 0.18, wall + 0.08, zs + 0.2, "M_far_grey", skip="b", sub=0)
    for _ in range(rng.choice((1, 2))):
        xd = rng.uniform(x0 + 3.0, x1 - 8.0)
        face_out(B, [(xd, 0.0, zs + 0.03), (xd + 4.5, 0.0, zs + 0.03), (xd + 4.5, 2.05, zs + 0.03), (xd, 2.05, zs + 0.03)],
                 "M_paint_metal_dark", (0.0, 0.0, 1.0))
    w = (zs - zn) / 2
    for v in range(2):
        zc, r = zn + w * (v + 0.5), w / 2
        arc = [(wall + math.sin(PI * i / seg) * rise, zc + math.cos(PI * i / seg) * r) for i in range(seg + 1)]
        for (ya, za), (yb, zb) in zip(arc, arc[1:]):
            out = (0.0, ((ya + yb) / 2 - wall) / rise + 0.05, ((za + zb) / 2 - zc) / r)
            face_out(B, [(x0, ya, za), (x0, yb, zb), (x1, yb, zb), (x1, ya, za)], roof, out)
        for xe, s in ((x0, -1.0), (x1, 1.0)):
            face_out(B, [(xe, yy, zz) for (yy, zz) in arc], "M_far_shed", (s, 0.0, 0.0))


# ------------------------------------------------------------------ rue Roger Salengro
def salengro(B):
    """the street through the south gate: setts pavements, a one-way cycle track on each side (westbound on the
    campus side, crossing the gate's path at (1.9, 54.9)), the westbound road"""
    B.use("far_salengro")
    s = AXIS_SALENGRO
    with B.ground_at(0.0):
        ribbon(B, s, -9.4, -6.1, 0.0, "M_setts_dark", cell=6.0)
        ribbon(B, s, -6.1, -4.1, -0.01, "M_asphalt", cell=6.0)
        slab(B, s, -4.1, -3.6, -0.12, 0.08, "M_curb")
        ribbon(B, s, -3.6, 3.4, -0.12, "M_asphalt", cell=6.0)
        slab(B, s, 3.4, 3.9, -0.12, 0.08, "M_curb")
        ribbon(B, s, 3.9, 5.9, -0.01, "M_asphalt", cell=6.0)
        ribbon(B, s, 5.9, 10.0, 0.0, "M_setts_dark", cell=6.0)
        for d in (-5.95, 4.05):
            o = offset(s, d)
            for p, q in zip(o, o[1:]):
                L = PG.length(p, q)
                n = int(L // 2.0)
                for k in range(n):
                    t0, t1 = k * 2.0 / L, (k * 2.0 + 1.0) / L
                    B.seg_box(p[0] + (q[0] - p[0]) * t0, p[1] + (q[1] - p[1]) * t0, p[0] + (q[0] - p[0]) * t1,
                              p[1] + (q[1] - p[1]) * t1, 0.0, 0.006, 0.1, "M_track_paint", skip="nsewb")
        # the gate path crosses the westbound track: a row of white squares on either side
        for x in (1.0, 2.8):
            for k in range(4):
                z = at_x(offset(s, -5.85 + k * 0.5), x)
                B.box(x - 0.2, -0.01, z - 0.2, x + 0.2, -0.004, z + 0.2, "M_track_paint", skip="nsewb")
    for (x, d) in ((-14.0, 7.6), (10.0, 7.6), (34.0, 7.6)):
        z = at_x(offset(s, d), x)
        S_prop(B, "street_lamp", x, 0.0, z, PI)
    V.light(B, "street_salengro", 10.0, 4.75, at_x(offset(s, 6.8), 10.0), K(3000), 2.0, 14.0)
    for x in (-5.0, -3.2, 7.4, 9.2):
        S_prop(B, "bollard", x, 0.0, at_x(offset(s, -6.4), x), 0.0)


# ------------------------------------------------------------------ gameplay limits (docs/DESIGN.md §8.2)
def walls(B):
    B.use_col("COL_bounds")
    # west: across rue Pasteur past Paritalie's north-west wing end, up to the closed alley gate
    B.cbox(WALL_W - 0.25, -1.0, -5.2, WALL_W + 0.25, 8.0, 6.7)
    # east: on the rue Emile Zola kerb, with returns to ARPEJ's and the east building's faces
    B.cbox(WALL_E - 0.25, -1.0, -13.2, WALL_E + 0.25, 8.0, 14.7)
    B.cbox(43.8, -1.0, -13.45, WALL_E + 0.25, 8.0, -12.95)
    B.cbox(45.4, -1.0, 14.45, WALL_E + 0.25, 8.0, 14.95)
