"""South of rue Pasteur, on the real footprints of campus_layout (docs/CAMPUS_LAYOUT.md §5.1):
Paritalie (the X: two lower wing ends on rue Pasteur around the tree-filled V forecourt, the NE wing with the
concrete bleachers, the SE wing with the cafeteria, the gate porch to the Paritalie alley), 24 rue Pasteur (the
recess and covered passage, cour Pasteur, the one-storey east building with Amphi 4 sunk below the courtyard, the two
south buildings, the south passage with its gate, 29-31 rue Roger Salengro), the ramp and the Under."""
import math, random
import campus_arch as A
import campus_poly as PG
from campus_arch import Opening, wall_frame
from campus_geo import Xf
from campus_street import card_rect
from campus_voltaire import fac, win, ext_win, light, ceiling, panel, SKIRT
from campus_layout import *
from campus_mat import K, mat as defmat

# beige stone-look panels (1.2 x 0.6 m) of the X's street ends and the 24 rue Pasteur buildings
defmat("M_limestone", ("ph", "concrete_wall_004", "2k"), tile=2.4, color="#ebd5b1", grime="ext", macro=0.06,
       maps=("diffg", "nor_gl", "arm"))
defmat("M_fascia_blue", None, color="#2d5fae", rough=0.35, metal=0.15, grime="ext", macro=0.03)
defmat("M_setts_dark", ("ph", "concrete_pavers_02", "2k"), tile=0.7, color="#8c8b88", grime="floor", macro=0.08)
defmat("M_sign_green", None, color="#13874a", rough=0.45)


def build(B):
    passage(B)
    courtyard(B)
    xbuilding(B)
    forecourt(B)
    paritalie_gate(B)
    cafeteria(B)
    amphi_exterior(B)
    amphi_interior(B)
    eartsup(B)
    salengro_29_31(B)          # rue Roger Salengro itself and the facades opposite: campus_backdrop.salengro()
    ramp(B)
    under(B)


# ------------------------------------------------------------------ 24 rue Pasteur: recess + covered passage
PASS_SOFFIT = 4.2     # clear height under the light roof ("4m" signs on both piers)
PASS_X = 3.35         # centre line of the passage (x 0.0..6.7)


def floor_poly(B, poly, y, mat, cell=4.0, down=False):
    """flat floor (or soffit with down=True) over a footprint, cut on a grid so vertex colours vary"""
    for f in PG.grid_pieces(poly, cell):
        pts = [(x, y, z) for x, z in f]
        B.face(pts[::-1] if down else pts, mat)


def passage(B):
    """the open recess between the two piers (z 5.0..7.1), then the covered passage between the X's wing end and
    the east building, under a light roof: no building above, the blue fascia over the opening"""
    R, N = PG.cw(RECESS_N), PG.cw(PASSAGE_N)
    B.use("passage")
    B.use_col("COL_court")
    with B.ground_at(0.0):
        # step-free: the recess slopes from the sidewalk (0.1) down to the passage (0.0)
        for tri in PG.triangulate(R):
            B.face([(x, max(0.0, 0.1 * (7.1 - z) / 2.1), z) for x, z in tri], "M_pavers_passage")
        floor_poly(B, N, 0.0, "M_pavers_passage", 3.0)
        B.box(0.05, -0.004, 7.55, 6.65, 0.0, 7.75, "M_cast_iron", skip="b")      # drainage channel at the gate
        # light roof: soffit, deck, edge beams; the fascia sits on the street edge
        floor_poly(B, N, PASS_SOFFIT, "M_concrete", 3.0, down=True)
        B.prism(N, PASS_SOFFIT, PASS_SOFFIT + 0.4, "M_roof", top=True, sides=False)
        for (a, b) in ((PASSAGE_N[3], PASSAGE_N[0]), (PASSAGE_N[1], PASSAGE_N[2])):
            xf, L = wall_frame(a[0], a[1], b[0], b[1])
            with B.frame(xf):
                B.box(-0.05, PASS_SOFFIT - 0.05, -0.3, L + 0.05, PASS_SOFFIT + 0.45, 0.0, "M_paint_metal_dark")
        xf, L = wall_frame(PASSAGE_N[3][0], PASSAGE_N[3][1], PASSAGE_N[0][0], PASSAGE_N[0][1])
        with B.frame(xf):
            # blue fascia about 1.5 m deep, topping out level with the east building's parapet; no lettering
            B.box(-0.05, PASS_SOFFIT + 0.45, -0.25, L + 0.05, 6.1, 0.08, "M_fascia_blue")
            B.box(-0.07, 6.1, -0.27, L + 0.07, 6.16, 0.1, "M_zinc")
        # the grey gate at the street end (3.0, 7.2), both leaves parked open against the walls
        for (xw, s) in ((0.06, 1), (6.62, -1)):
            B.box(xw - 0.06, 0.0, 7.12, xw + 0.06, 2.6, 7.32, "M_paint_metal_dark")
            x0 = xw + 0.08 * s
            for k in range(25):
                z = 7.45 + k * 0.13
                B.box(x0 - 0.012, 0.03, z - 0.012, x0 + 0.012, 2.35, z + 0.012, "M_steel")
            for y in (0.08, 1.2, 2.32):
                B.box(x0 - 0.03, y, 7.35, x0 + 0.03, y + 0.05, 10.75, "M_steel")
        for z in (8.6, 10.7, 12.8):
            B.box(PASS_X - 0.6, PASS_SOFFIT - 0.08, z - 0.15, PASS_X + 0.6, PASS_SOFFIT, z + 0.15, "M_paint_metal_dark", skip="t")
            B.box(PASS_X - 0.55, PASS_SOFFIT - 0.09, z - 0.11, PASS_X + 0.55, PASS_SOFFIT - 0.08, z + 0.11, "M_light_warm", skip="t")
    B.cramp(3.75, 0.1, 5.0, 3.75, 0.0, 7.2, 11.2)
    B.cprism(N, -0.5, 0.0)
    B.cprism(N, PASS_SOFFIT, PASS_SOFFIT + 0.45)
    for (xw, s) in ((0.06, 1), (6.62, -1)):
        B.cbox(xw + 0.08 * s - 0.04, 0.0, 7.12, xw + 0.08 * s + 0.04, 2.4, 10.75)
    light(B, "passage", PASS_X, 3.7, 9.6, K(3200), 1.6, 9.0, shadow=True)
    light(B, "passage_b", PASS_X, 3.7, 13.0, K(3200), 0.9, 7.0)


# ------------------------------------------------------------------ cour Pasteur
TRENCH = (12.0, 36.0, 28.7, 39.2)      # the ramp down to the Under, cut out of the courtyard floor


def court_pieces():
    """cour Pasteur (COURT, about 1,030 m2) around the ramp trench"""
    C = PG.cw(COURT)
    x0, z0, x1, z1 = TRENCH
    band = PG.clip_half(PG.clip_half(C, (0.0, z0), (0.0, -1.0)), (0.0, z1), (0.0, 1.0))
    pieces = [PG.clip_half(C, (0.0, z0), (0.0, 1.0)), PG.clip_half(C, (0.0, z1), (0.0, -1.0)),
              PG.clip_half(band, (x0, 0.0), (1.0, 0.0)), PG.clip_half(band, (x1, 0.0), (-1.0, 0.0))]
    return [p for p in pieces if len(p) >= 3 and abs(PG.area(p)) > 0.01]


def courtyard(B):
    B.use("court_ground")
    B.use_col("COL_court")
    with B.ground_at(0.0):
        for pc in court_pieces():
            floor_poly(B, pc, 0.0, "M_court_slabs", 4.0)
            B.cprism(pc, -0.6, 0.0)
        # linear drains
        for (x0, z0, x1, z1) in ((1.0, 24.0, 23.0, 24.2), (-6.0, 36.4, 9.5, 36.6)):
            B.box(x0, 0.0, z0, x1, 0.004, z1, "M_cast_iron", skip="b")
    bleachers(B)
    # courtyard LIGHT_court_a..d are created with the pendants in campus_dress.courtyard()


BLEACH_U0 = 3.2       # the steps start this far along the NE wing, clear of the passage mouth (NE0)


def bleachers(B):
    """five concrete steps against the NE wing (old B.seg steps), timber seat boards flush with the tops"""
    B.use("court_bleachers")
    B.use_col("COL_court")
    u0 = BLEACH_U0
    with B.frame(Xf.at(NE0[0], 0, NE0[1], NE_YAW)):
        with B.ground_at(0.0):
            for k in range(5):
                d = 0.3 + 0.6 * k
                h = 0.42 * (5 - k)
                z0, z1 = -d - 0.3, -d + 0.3
                B.box(u0, 0.0, z0, NE_LEN, h - 0.04, z1, "M_concrete", skip="bs")
                # seat boards (slats with gaps) on the front of each step
                for i in range(5):
                    zz0 = z0 + 0.03 + i * 0.105
                    B.box(u0, h - 0.04, zz0, NE_LEN, h, zz0 + 0.09, "M_wood_crate", skip="b")
                B.box(u0, h - 0.04, z0 + 0.555, NE_LEN, h, z1, "M_concrete", skip="b")
                B.cbox(u0, 0.0, z0, NE_LEN, h, z1)


# ------------------------------------------------------------------ Paritalie (the X)
X_GF = FLOOR                  # ground floor, the cafeteria's height
X_ST = (X_H - X_GF) / 5.0     # five upper storeys (R+5)
X_PEAK = 19.6                 # top of the penthouse on the octagonal core (IGN's highest point)
X_CORE = (-24.4, 28.3)        # centre of the octagonal core


def _axis(a, b):
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


# The wing ends on rue Pasteur are lower than the R+5 wings: each is cut off perpendicular to its wing a few metres
# behind the street corners. The NE end has a ground floor plus 3 floors; the NW end's 4-5 storeys
# are uncertain, so it keeps the old street wing's ground + 4.
_NE_AX = _axis((-0.2, 13.9), (-12.3, 24.9))
_NW_AX = _axis((-38.7, 4.9), (-27.6, 16.7))
X_ENDS = (dict(name="ne", p0=(-0.2 + 2.4 * _NE_AX[0], 13.9 + 2.4 * _NE_AX[1]), n=_NE_AX, levels=4),
          dict(name="nw", p0=(-38.7 + 3.0 * _NW_AX[0], 4.9 + 3.0 * _NW_AX[1]), n=_NW_AX, levels=5))


def x_level(k):
    """floor level of storey k (0 = ground floor)"""
    return 0.0 if k == 0 else X_GF + (k - 1) * X_ST


def x_pieces():
    """[(name, footprint, roof level, storeys, cladding)]: the R+5 body (cream precast) and the two limestone wing ends"""
    X = PG.cw(X_PARITALIE)
    body, ends = X, []
    for e in X_ENDS:
        ends.append((e["name"], PG.clip_half(X, e["p0"], e["n"]), x_level(e["levels"]), e["levels"], "M_limestone"))
        body = PG.clip_half(body, e["p0"], (-e["n"][0], -e["n"][1]))
    return [("body", body, X_H, 6, "M_concrete_x")] + ends


def same_edge(a, b, p, q, tol=0.06):
    """a-b is the footprint edge p-q (either direction)"""
    d = lambda u, v: math.hypot(u[0] - v[0], u[1] - v[1]) < tol
    return (d(a, p) and d(b, q)) or (d(a, q) and d(b, p))


def _x_seen(a, b):
    """faces on rue Pasteur, the V forecourt, cour Pasteur and the south passage (the patios are out of reach)"""
    n = PG.outward(a, b)
    return n[1] < -0.3 or n[0] > 0.3


def x_windows(L, k0, k1, stone, seed, lit, gf="window", skip=()):
    """window grid of one X facade, storeys k0..k1-1. Precast body: rows of single windows; limestone wing ends:
    2 x 2 windows. gf: 'window', 'glazed' (courtyard shop-front glazing) or 'none'"""
    bay, w = (3.0, 2.0) if stone else (2.6, 1.5)
    n = int((L - 0.9) // bay)
    if n < 1:
        if L < w + 0.6:
            return []
        n = 1
    m = (L - n * bay) / 2
    ops = []
    for k in range(k0, k1):
        if k in skip or (k == 0 and gf == "none"):
            continue
        y = x_level(k)
        for i in range(n):
            u = m + bay * (i + 0.5)
            s = seed + k * 37 + i
            if k == 0 and gf == "glazed":
                ops.append(ext_win(u, min(bay - 0.35, 2.3), 0.35, 2.95, s, lit=0.6, sill=None, cols=2, transom=2.25))
            elif k == 0:
                ops.append(ext_win(u, w, 0.6 if stone else 0.9, 2.75, s, lit=lit, sill=None, cols=2))
            elif stone:
                ops.append(ext_win(u, w, y + 0.65, y + 2.3, s, lit=lit, sill=None, cols=2, rows=2))
            else:
                ops.append(ext_win(u, w, y + 0.85, y + 2.3, s, lit=lit, sill=None, cols=1))
    return ops


def _x_trim(B, a, b, y0, h, stone, levels):
    """storey bands on the precast, a dark plinth under the limestone, parapet and coping"""
    xf, L = wall_frame(a[0], a[1], b[0], b[1])
    with B.frame(xf):
        if stone:
            if y0 < 0.01:
                B.box(-0.01, 0.0, 0.0, L + 0.01, 0.35, 0.03, "M_concrete_dark", skip="b")
        else:
            for k in range(1, levels):
                y = x_level(k)
                if y > y0 + 0.2:
                    B.box(-0.02, y - 0.07, 0.0, L + 0.02, y + 0.07, 0.05, "M_concrete")
        A.parapet(B, L, h, 0.6, 0.3, "M_limestone" if stone else "M_concrete_x", inner_mat="M_concrete")


def xbuilding(B):
    """Paritalie: the 32-point X footprint extruded to R+5 with lower wing ends on rue Pasteur"""
    B.use_col("COL_buildings")
    for name, poly, h, levels, clad in x_pieces():
        B.use("xb_" + name)
        stone = clad == "M_limestone"
        with B.ground_at(0.0):
            for i, (a, b) in enumerate(PG.edges(poly)):
                L = PG.length(a, b)
                if L < 0.05:
                    continue
                seed = 2000 + i * 211 + (7000 if stone else 0)
                seen = _x_seen(a, b)
                lit = 0.45 if seen else 0.15
                cut = next((e for e in X_ENDS if PG.on_line(a, e["p0"], e["n"]) and PG.on_line(b, e["p0"], e["n"])), None)
                if cut is not None:
                    if stone:
                        continue          # the body's wall rises behind the lower wing end
                    y0 = x_level(cut["levels"])
                    fac(B, a[0], a[1], b[0], b[1], y0, h, 0.3, clad, False,
                        x_windows(L, cut["levels"], levels, False, seed, lit), top=False, ends=False)
                    _x_trim(B, a, b, y0, h, False, levels)
                    continue
                y0, k0, gf, skip, extra = 0.0, 0, "window", (), []
                if not stone and seen and PG.outward(a, b)[0] > 0.3:
                    gf = "glazed"
                if same_edge(a, b, *SE_FACE):
                    y0, k0 = X_GF, 1                                   # cafeteria() builds the glass front
                elif same_edge(a, b, (0.0, 7.1), (-0.2, 13.9)):
                    # the passage's west wall: a service door; the 1st floor is behind the light roof
                    gf, skip = "none", (1,)
                    extra = [Opening(1.5, 2.5, 0.0, 2.2, "door", leaf="M_paint_metal_white")]
                elif same_edge(a, b, (0.0, 7.1), (-1.7, 5.0)):
                    gf, skip = "none", tuple(range(levels))            # west pier: the banner hangs here
                elif same_edge(a, b, (-38.7, 4.9), (-45.2, 4.9)):
                    # the pharmacy in the NW wing end
                    gf = "none"
                    extra = [Opening(0.45, L - 0.45, 0.15, 2.9, "window", frame="M_alu_anthracite", cols=4, sill=None,
                                     depth=0.15, card=("M_room_card", card_rect(seed, 0.95)), card_depth=1.2)]
                elif same_edge(a, b, (-11.7, 30.9), (-11.6, 25.9)):
                    # the X's courtyard door on the inner corner face, at (-11.6, 27.0) (docs/CAMPUS_LAYOUT.md §3.4)
                    u = math.hypot(-11.6 - a[0], 27.0 - a[1])
                    gf = "none"
                    extra = [Opening(u - 1.0, u + 1.0, 0.0, 2.6, "glassdoor", leaves=2),
                             ext_win(L - u if u < L / 2 else 1.2, 1.4, 0.35, 2.95, seed, lit=0.6, sill=None, cols=1)]
                ops = x_windows(L, k0, levels, stone, seed, lit, gf, skip) + extra
                fac(B, a[0], a[1], b[0], b[1], y0, h, 0.3, clad, False, ops, top=False, ends=False)
                _x_trim(B, a, b, y0, h, stone, levels)
                if seen and not stone and L > 8.0:
                    xf, _ = wall_frame(a[0], a[1], b[0], b[1])
                    with B.frame(xf):
                        A.downpipe(B, 0.35, 0.0, h)
            B.prism(poly, h - 0.3, h, "M_roof_gravel", top=True, sides=False)
    # paving round the rest of the block (west patio, south forecourt, the alley): out of reach, seen from above
    B.use("x_grounds", cast=False)
    with B.ground_at(0.0):
        B.box(-70.0, -0.3, 12.7, -13.2, -0.01, 58.0, "M_concrete_floor", skip="nsewb", sub=6.0)
        B.box(-13.2, -0.3, 45.0, -1.9, -0.01, 58.0, "M_concrete_floor", skip="nsewb", sub=6.0)
    # penthouse on the octagonal core
    B.use("xb_body")
    octa = [(X_CORE[0] + 4.6 * math.cos(math.radians(22.5 + 45 * k)), X_CORE[1] + 4.6 * math.sin(math.radians(22.5 + 45 * k)))
            for k in range(8)]
    B.prism(octa, X_H, X_PEAK, "M_concrete_x", top=True, sides=True, top_mat="M_roof_gravel")
    B.prism([(X_CORE[0] + 4.68 * math.cos(math.radians(22.5 + 45 * k)), X_CORE[1] + 4.68 * math.sin(math.radians(22.5 + 45 * k)))
             for k in range(8)], X_PEAK, X_PEAK + 0.06, "M_zinc", top=True, sides=True)


def forecourt(B):
    """the V between the two wing ends on rue Pasteur: planted, behind a low kerb wall and a
    hedge on the building line. Its trees are PROP_tree_plane markers (campus_dress.south_side)."""
    V = PG.cw([(-7.5, 5.0), (-20.2, 16.9), (-21.2, 15.7), (-26.4, 15.6), (-27.6, 16.7), (-38.7, 4.9)])
    from campus_props_out import foliage, grass_tuft
    rng = random.Random(51)
    B.use("x_forecourt")
    B.use_col("COL_buildings")
    with B.ground_at(0.1):
        floor_poly(B, V, 0.1, "M_soil", 4.0)
        B.box(-38.6, 0.0, 5.0, -7.6, 0.5, 5.3, "M_concrete", skip="b")
        B.box(-38.65, 0.5, 4.97, -7.55, 0.55, 5.33, "M_zinc")
        x = -37.6
        while x < -8.4:
            foliage(B, (x, 0.95, 5.85), (0.95, 0.55, 0.6), 16, 0.9, "M_leaves_plane", rng, bias=0.6)
            x += 1.5
        for k in range(70):
            p = (rng.uniform(-36.0, -9.0), rng.uniform(6.6, 15.0))
            if PG.inside_poly(p, V) and PG.poly_dist(p, V) > 0.6:
                grass_tuft(B, p[0], 0.1, p[1], rng.uniform(0.3, 0.6), rng)
    B.cbox(-38.7, 0.0, 5.0, -7.5, 1.4, 5.7)


def paritalie_gate(B):
    """the Paritalie gate porch on rue Pasteur, x -54.2..-47.1 (a light structure about 9 m high) with the gate to the
    alley at z 6.6, closed (docs/CAMPUS_LAYOUT.md §3.3); the 3-storey annex next to it is a campus_street
    neighbour"""
    B.use("x_gate")
    B.use_col("COL_buildings")
    x0, x1 = -54.1, -47.15
    with B.ground_at(0.1):
        B.box(x0, -0.3, 5.0, x1, 0.1, 9.5, "M_concrete_floor", skip="nsewb", sub=3.0)
        for x in (x0 + 0.15, x1 - 0.15):
            for z in (6.75, 12.5):
                B.box(x - 0.12, 0.1, z - 0.12, x + 0.12, 9.0, z + 0.12, "M_paint_metal_dark")
            B.box(x - 0.1, 8.7, 6.6, x + 0.1, 9.0, 12.6, "M_paint_metal_dark")
        B.box(x0, 9.0, 6.4, x1, 9.25, 12.7, "M_paint_metal_dark")
        B.box(x0 + 0.1, 8.98, 6.5, x1 - 0.1, 9.0, 12.6, "M_concrete", skip="t")
        # closed bar gate on the building line
        n = int((x1 - x0 - 0.5) / 0.13)
        for k in range(n):
            x = x0 + 0.3 + k * 0.13
            B.box(x - 0.012, 0.12, 6.58, x + 0.012, 2.4, 6.62, "M_paint_metal_dark")
        for y in (0.18, 1.3, 2.38):
            B.box(x0 + 0.25, y, 6.56, x1 - 0.25, y + 0.05, 6.64, "M_paint_metal_dark")
        # the alley drops one level behind the gate (OSM layer -1): a dark slope into the patio
        B.quad((x0 + 0.3, 0.1, 9.5), (x0 + 0.3, -2.5, 12.6), (x1 - 0.3, -2.5, 12.6), (x1 - 0.3, 0.1, 9.5), "M_concrete_floor")
    B.cbox(x0, 0.0, 6.5, x1, 3.0, 6.7)


def cafeteria(B):
    """GF of the SE wing behind its courtyard face SE_FACE: glass front on cour Pasteur (xbuilding() builds the
    storeys above)"""
    B.use_col("COL_cafe")
    with B.frame(Xf.at(SE0[0], 0, SE0[1], SE_YAW)):
        L = SE_LEN
        B.use("cafe")
        with B.ground_at(0.02):
            B.box(0.0, -0.3, 0.0, L, 0.02, CAFE_D, "M_tiles_cafe", skip="nsewb", sub=3.0)
            # front: glass bays + door (u measured from the x=L end because outward is local -z)
            ops = []
            for lx in (1.9, 5.4, 10.6, 14.0):
                u = L - lx
                ops.append(Opening(u - 1.6, u + 1.6, 0.15, 3.1, "window", frame="M_alu_anthracite", cols=2, glass="M_glass_clear",
                                   depth=0.1, sill=None, transom=2.3))
            u = L - 8.0
            ops.append(Opening(u - 0.9, u + 0.9, 0.0, 2.5, "passage"))
            fac(B, L, -0.25, 0.0, -0.25, 0.0, FLOOR, 0.25, "M_alu_anthracite", "M_paint_cafe", ops, top=False, ends=False,
                base_in=SKIRT)
            fac(B, 0.0, CAFE_D + 0.25, L, CAFE_D + 0.25, 0.0, FLOOR, 0.25, False, "M_paint_cafe", (), top=False, ends=False, base_in=SKIRT)
            fac(B, -0.25, 0.0, -0.25, CAFE_D, 0.0, FLOOR, 0.25, False, "M_paint_cafe", (), top=False, ends=False, base_in=SKIRT)
            fac(B, L + 0.25, CAFE_D, L + 0.25, 0.0, 0.0, FLOOR, 0.25, False, "M_paint_cafe", (), top=False, ends=False, base_in=SKIRT)
            # door: open glass doors parked inside
            for s in (-1, 1):
                ux = 8.0 + s * 0.9
                B.box(ux - 0.04, 0.0, -0.25, ux + 0.04, 2.5, 0.0, "M_alu_anthracite")
            B.box(8.0 - 0.9, 2.5, -0.25, 8.0 + 0.9, 2.62, 0.0, "M_alu_anthracite")
        B.cbox(0.0, -0.5, 0.0, L, 0.02, CAFE_D)
        B.cbox(0.0, FLOOR - 0.35, 0.0, L, FLOOR, CAFE_D)
        # ceiling + panels
        B.use("cafe_ceiling", cast=False)
        ceiling(B, 0.0, L, 0.0, CAFE_D, FLOOR - 0.35)
        for lx in (2.0, 5.2, 8.4, 11.6, 14.8):
            for lz in (2.3, 4.6, 6.9):
                panel(B, lx, lz, FLOOR - 0.35, 1.2, 0.3)
        # canopy band over the glass front, where the precast storeys start
        B.use("cafe")
        B.box(-0.02, FLOOR - 0.12, -0.45, L + 0.02, FLOOR + 0.18, -0.25, "M_concrete")
        lx4 = cafe_pt(4, 4.5)
        lx11 = cafe_pt(11, 4.5)
    light(B, "cafe_a", lx4[0], FLOOR - 0.5, lx4[1], K(3800), 1.8, 10.0, shadow=True)
    light(B, "cafe_b", lx11[0], FLOOR - 0.5, lx11[1], K(3800), 1.8, 10.0, shadow=True)
    c = cafe_pt(8.0, -1.0)
    light(B, "cafe_sign", c[0], 3.2, c[1], K(3500), 0.8, 5.0)


# ------------------------------------------------------------------ 24 rue Pasteur, east building (Amphi 4)
AH = 6.4      # one tall storey; the raised hall roof reaches about 9 m
HALL_ROOF = 8.9


def plinth(B, L, ops, h=0.35, mat="M_concrete_dark"):
    """dark base band along a wall (local frame), interrupted where an opening reaches the ground"""
    cuts = sorted((o.u0, o.u1) for o in ops if o.y0 <= 0.05)
    cur = -0.01
    for a, b in cuts + [(L + 0.01, L + 0.01)]:
        if a - cur > 0.05:
            B.box(cur, 0.0, 0.0, a, h, 0.03, mat, skip="b")
        cur = max(cur, b)


def amphi_exterior(B):
    """the one-storey east building on EAST_24: beige panels, a glass front on the courtyard
    with the Amphi 4 doors, a planted roof garden behind a railing, the raised roof over the hall"""
    from campus_props_out import foliage, grass_tuft
    rng = random.Random(77)
    E = PG.cw(EAST_24)
    B.use("amphi_ext")
    B.use_col("COL_amphi")
    with B.ground_at(0.0):
        for i, (a, b) in enumerate(PG.edges(E)):
            L = PG.length(a, b)
            seed = 1800 + i * 23
            ops, t, street, fins = [], 0.3, False, False
            if same_edge(a, b, (40.8, 5.0), (9.2, 5.0)):
                # rue Pasteur: offices at the east end, then the hall's blank wall with a louvre band
                street = True
                ops = [ext_win(u, 1.8, 1.0, 4.3, seed + k, lit=0.4, sill="M_concrete", cols=2, rows=2)
                       for k, u in enumerate((1.6, 4.4, 7.2, 10.0))]
            elif same_edge(a, b, (45.6, 9.6), (40.8, 5.0)):
                street = True
                ops = [ext_win(u, 1.8, 1.0, 4.3, seed + k, lit=0.4, sill="M_concrete", cols=2, rows=2) for k, u in enumerate((1.8, 4.8))]
            elif same_edge(a, b, (47.1, 40.0), (45.6, 9.6)):
                ops = [ext_win(u, 1.8, 1.0, 4.3, seed + k, lit=0.35, sill="M_concrete", cols=2, rows=2)
                       for k, u in enumerate(range(2, int(L) - 1, 3))]
            elif same_edge(a, b, (10.5, 18.6), (25.8, 18.9)):
                # the Amphi 4 doors (x 15..17); the wall is thick enough to meet the hall's own wall
                ops, t, fins = [Opening(4.5, 6.5, 0.0, 2.5, "passage")], 0.5, True
            elif same_edge(a, b, (25.8, 18.9), (33.2, 26.6)):
                # the diagonal corner and its door at (29.7, 23.0)
                ops = [Opening(4.86, 6.46, 0.0, 2.6, "glassdoor", leaves=2)] + \
                      [ext_win(u, 2.2, 0.35, 3.9, seed + k, lit=0.55, sill=None, cols=2, transom=2.7) for k, u in enumerate((2.2, 8.9))]
            elif same_edge(a, b, (6.5, 14.3), (10.5, 18.6)) or same_edge(a, b, (33.2, 26.6), (33.0, 38.3)):
                # glass front on cour Pasteur
                n = max(1, int((L - 0.6) // 2.9))
                m = (L - n * 2.9) / 2
                ops = [ext_win(m + 2.9 * (k + 0.5), 2.5, 0.35, 3.9, seed + k, lit=0.55, sill=None, cols=2, transom=2.7)
                       for k in range(n)]
            elif same_edge(a, b, (6.7, 7.4), (6.5, 14.3)):
                ops = [Opening(3.6, 4.6, 0.0, 2.2, "door", leaf="M_paint_metal_white")]      # the passage's east wall
            fac(B, a[0], a[1], b[0], b[1], 0.0, AH, t, "M_limestone", False, ops, top=False, ends=False,
                ground_out=0.1 if street else None)
            xf, _ = wall_frame(a[0], a[1], b[0], b[1])
            with B.frame(xf):
                plinth(B, L, ops)
                A.parapet(B, L, AH, 0.6, 0.3, "M_limestone", inner_mat="M_concrete")
                if street and L > 20:
                    for y in (2.6, 2.9, 3.2, 3.5, 3.8, 4.1, 4.4, 4.7, 5.0):      # louvres over the hall
                        B.box(13.2, y, 0.0, 30.9, y + 0.08, 0.14, "M_alu_silver")
                    B.box(0.0, 4.6, 0.0, L, 4.72, 0.1, "M_concrete")
                if fins:
                    u = 0.4
                    while u < L - 0.2:
                        if not (4.1 < u < 6.9):
                            B.box(u, 0.0, 0.15, u + 0.07, 5.3, 0.45, "M_alu_silver")
                        u += 0.9
                    B.box(4.1, 2.75, 0.0, 6.9, 2.88, 1.8, "M_paint_metal_dark")
                    B.box(4.7, 2.73, 0.8, 6.3, 2.75, 1.1, "M_light_warm", skip="t")
                    B.box(0.0, 5.3, 0.0, L, 5.6, 0.5, "M_concrete")
                if not same_edge(a, b, (30.6, 39.4), (47.1, 40.0)):
                    # the roof garden's railing, above the parapet
                    A.handrail(B, [(0.1, AH + 0.6, -0.15), (L - 0.1, AH + 0.6, -0.15)], h=0.5, r=0.02, mat="M_zinc",
                               post_every=1.8)
        light(B, "amphi_entrance", 16.0, 2.5, 19.5, K(3000), 1.2, 8.0, shadow=True)
        # planted roof garden and the raised roof over the hall
        B.prism(E, AH - 0.3, AH, "M_moss", top=True, sides=False)
        B.box(12.0, AH - 0.3, 8.0, 26.0, HALL_ROOF, 16.5, "M_limestone", skip="b", mats={"t": "M_roof_gravel"})
        B.box(11.97, HALL_ROOF, 7.97, 26.03, HALL_ROOF + 0.06, 16.53, "M_zinc", skip="b")
        for k in range(15):
            foliage(B, (8.5 + k * 2.3, AH + 0.55, 6.0 + rng.uniform(0.0, 0.5)), (1.0, 0.65, 0.6), 14, 0.85, "M_leaves_plane", rng,
                    bias=0.6)
        for p in ((11.0, 17.6), (14.0, 17.8), (20.0, 18.0), (24.0, 18.0), (27.5, 20.3), (30.5, 23.4), (32.0, 29.0), (32.0, 34.0),
                  (8.0, 14.0), (42.0, 8.0), (44.5, 20.0), (44.0, 30.0)):
            foliage(B, (p[0], AH + 0.5, p[1]), (0.9, 0.6, 0.9), 12, 0.8, "M_leaves_plane", rng, bias=0.6)
        for k in range(60):
            p = (rng.uniform(7.0, 46.0), rng.uniform(5.5, 39.0))
            if PG.inside_poly(p, E) and PG.poly_dist(p, E) > 0.5 and not (11.8 < p[0] < 26.2 and 7.8 < p[1] < 16.7):
                grass_tuft(B, p[0], AH, p[1], rng.uniform(0.3, 0.55), rng)
    # the hall's roof keeps the camera inside Amphi 4
    B.cbox(9.65, 5.3, 5.6, 27.85, AH, 18.5)


def amphi_interior(B):
    B.use("amphi")
    B.use_col("COL_amphi")
    x0, x1 = 9.65, 27.85
    zs, ze = 6.1, 18.2
    with B.ground_at(AY):
        # walls: north (screen wall), south (entrance wall), west, east
        fac(B, x1, 5.6, x0, 5.6, AY - 0.3, 5.3, 0.5, False, "M_paint_amphi", (), top=False, ends=False, base_in=SKIRT, col=False)
        ops = [Opening(16.0 - x0 - 1.0, 16.0 - x0 + 1.0, 0.0, 2.5, "passage")]
        fac(B, x0, 18.5, x1, 18.5, 0.0, 5.3, 0.3, False, "M_paint_amphi", ops, top=False, ends=False, base_in=SKIRT, col=False)
        fac(B, x0, 18.2, x0, 6.1, AY - 0.3, 5.3, 0.35, "M_paint_amphi", False, (), top=False, ends=False, col=False)
        fac(B, x1, 6.1, x1, 18.2, AY - 0.3, 5.3, 0.35, "M_paint_amphi", False, (), top=False, ends=False, col=False)
        # timber acoustic slats on the side walls (upper half)
        for xw, s in ((x0, 1), (x1, -1)):
            z = 6.4
            while z < 17.9:
                B.box(xw if s > 0 else xw - 0.04, 1.2, z, xw + 0.04 if s > 0 else xw, 5.0, z + 0.07, "M_wood_oak")
                z += 0.16
    B.cbox(x0, AY - 0.6, 5.6, x1, 5.3, zs)
    B.cbox(x0 - 0.35, AY - 0.6, zs, x0, 5.3, ze)
    B.cbox(x1, AY - 0.6, zs, x1 + 0.35, 5.3, ze)
    B.cbox(x0, 2.5, ze, x1, 5.3, 18.5)
    B.cbox(x0, -0.6, ze, 15.0, 2.5, 18.5)
    B.cbox(17.0, -0.6, ze, x1, 2.5, 18.5)
    # entrance landing (y=0) + 7 tiers (carpet treads, oak nosings) + aisle steps + stage
    B.use("amphi")
    with B.ground_at(AY):
        B.box(x0, AY - 0.3, AMPHI_TOP_Z, x1, 0.0, ze, "M_carpet_amphi", skip="nsewb", sub=3.0)
        B.box(x0, AY - 0.3, AMPHI_TOP_Z - 0.04, x1, 0.0, AMPHI_TOP_Z, "M_wood_oak", skip="sb")
        B.cbox(x0, AY - 0.3, AMPHI_TOP_Z, x1, 0.0, ze)
        for k in range(1, TIERS + 1):
            z0, z1, top = tier_z(k)
            B.box(x0, AY - 0.3, z0, x1, top, z1, "M_carpet_amphi", skip="sewb", sub=3.0,
                  mats={"n": "M_paint_amphi"})
            B.box(x0, top - 0.04, z0 - 0.002, x1, top + 0.004, z0 + 0.04, "M_wood_oak", skip="b")
            B.cbox(x0, top - 0.4, z0, x1, top, z1)
        # aisle (x 17.9..19.65): two half steps per tier, painted nosings
        ax0, ax1 = 17.9, 19.65
        for k in range(1, TIERS + 1):
            z0, z1, top = tier_z(k)
            zm = (z0 + z1) / 2
            B.box(ax0, top, zm, ax1, top + 0.15, z1, "M_carpet_amphi", skip="b")
            B.box(ax0, top + 0.15 - 0.03, zm - 0.002, ax1, top + 0.152, zm + 0.04, "M_paint_metal_yellow", skip="b")
            # LED step light
            B.box(ax0 + 0.05, top + 0.05, zm - 0.004, ax0 + 0.15, top + 0.09, zm, "M_light_warm", skip="s")
        stage_z1 = AMPHI_TOP_Z - TIER_D * TIERS
        B.box(x0, AY - 0.3, zs, x1, AY, stage_z1, "M_wood_floor", skip="nsewb", sub=3.0)
        B.cbox(x0, AY - 0.6, zs, x1, AY, stage_z1)
    B.cramp(18.75, 0.0, AMPHI_TOP_Z, 18.75, -TIER_H * TIERS - 0.3, AMPHI_TOP_Z - TIER_D * TIERS - 0.4, 1.4, 0.2)
    # threshold of the courtyard door (inside the wall thickness)
    B.box(15.0, -0.02, ze, 17.0, 0.0, 18.5, "M_steel", skip="nsewb")
    B.cbox(15.0, -0.5, ze - 0.05, 17.0, 0.0, 18.55)
    # ceiling: acoustic panels with gaps + light lines
    B.use("amphi_ceiling", cast=False)
    ceiling(B, x0, x1, zs, ze, 5.3, "M_ceiling_plain")
    for z in (8.0, 10.6, 13.2, 15.8):
        B.box(x0 + 0.4, 4.95, z - 1.1, x1 - 0.4, 5.05, z + 1.1, "M_paint_white", skip="t")
    for x in (12.0, 15.5, 19.0, 22.5, 26.0):
        for z in (9.0, 12.5, 16.0):
            B.box(x - 0.7, 4.93, z - 0.12, x + 0.7, 4.95, z + 0.12, "M_light_panel", skip="t")
    for i, (x, z) in enumerate(((13, 9), (24, 9), (13, 14), (24, 14), (18.75, 7))):
        light(B, "amphi_%02d" % i, x, 4.6, z, "#ffe9d6", 1.15, 12.0, shadow=i in (0, 1, 2, 3, 4))
    light(B, "amphi_slide", 18.75, 4.4, 9.5, "#f4f6ff", 0.7, 8.0, kind="spot", look=(0.0, -0.35, -1.0), angle=38.0)


# ------------------------------------------------------------------ the south side, on rue Roger Salengro
def south_block(B, poly, h, floor_h, seed, party=(), above=None):
    """one of the two 2-storey south buildings (beige panels, big windows on both floors).
    party: edges against a neighbour (no windows); above: (edge, y) a party wall that only shows above y"""
    P = PG.cw(poly)
    roof = h - 0.5
    doors = 0
    for i, (a, b) in enumerate(PG.edges(P)):
        L = PG.length(a, b)
        y0, ops = 0.0, []
        if above and same_edge(a, b, *above[0]):
            y0 = above[1]
        elif not any(same_edge(a, b, *e) for e in party):
            k = int((L - 0.8) // 3.0)
            m = (L - k * 3.0) / 2
            north = PG.outward(a, b)[1] < -0.7
            for j in range(k):
                u = m + 3.0 * (j + 0.5)
                if north and doors == 0 and j == k // 2:
                    ops.append(Opening(u - 1.0, u + 1.0, 0.0, 2.6, "glassdoor", leaves=2))
                    doors += 1
                else:
                    ops.append(ext_win(u, 2.4, 0.35, floor_h - 0.5, seed + i * 31 + j, lit=0.55, sill=None, cols=2, transom=2.3))
                ops.append(ext_win(u, 2.4, floor_h + 0.6, 2 * floor_h - 0.45, seed + i * 31 + 7 + j, lit=0.45, sill=None, cols=2))
        fac(B, a[0], a[1], b[0], b[1], y0, roof, 0.3, "M_limestone", False, ops, top=False, ends=False)
        xf, _ = wall_frame(a[0], a[1], b[0], b[1])
        with B.frame(xf):
            if y0 == 0.0:
                plinth(B, L, ops)
                B.box(-0.01, floor_h - 0.1, 0.0, L + 0.01, floor_h + 0.12, 0.05, "M_concrete")
            A.parapet(B, L, roof, h - roof, 0.3, "M_limestone", inner_mat="M_concrete")
    B.prism(P, roof - 0.3, roof, "M_roof_gravel", top=True, sides=False)


def eartsup(B):
    """the two 2-storey south buildings, 8.4 m and 9.3 m, and the south passage"""
    B.use("eartsup")
    B.use_col("COL_buildings")
    with B.ground_at(0.0):
        south_block(B, SOUTH_W, 8.4, 3.9, 1900, party=(((20.2, 41.4), (19.8, 53.1)),))
        south_block(B, SOUTH_E, 9.3, 4.3, 1960, party=(((30.0, 53.5), (30.5, 41.7)),),
                    above=(((20.2, 41.4), (19.8, 53.1)), 8.4))
    south_passage(B)


def south_passage(B):
    """the covered passage to rue Roger Salengro: the gate is at its street end, (2.0, 50.5), under a footbridge
    with a railing at first-floor level, below a light roof at 8.4 m"""
    S = PG.cw(PASSAGE_S)
    B.use("south_passage")
    B.use_col("COL_court")
    with B.ground_at(0.0):
        floor_poly(B, S, 0.0, "M_pavers_passage", 3.0)
        # footbridge at first-floor level over the street half, galvanised railings on both edges
        B.box(-1.85, 3.85, 47.4, 5.75, 4.3, 50.4, "M_concrete")
        for z in (47.47, 50.33):
            A.handrail(B, [(-1.8, 4.3, z), (5.7, 4.3, z)], h=1.05, r=0.025, mat="M_zinc", post_every=1.25)
            B.box(-1.8, 4.3, z - 0.015, 5.7, 4.45, z + 0.015, "M_zinc")
        # light roof between the X's wing end and the south building
        B.box(-1.85, 8.2, 44.7, 5.8, 8.4, 50.5, "M_paint_metal_dark")
        # the gate, closed: locked after 18:00
        n = int(7.3 / 0.13)
        for k in range(n):
            x = -1.7 + k * 0.13
            B.box(x - 0.012, 0.02, 50.43, x + 0.012, 2.55, 50.47, "M_paint_metal_dark")
        for y in (0.08, 1.2, 2.5):
            B.box(-1.75, y, 50.4, 5.65, y + 0.06, 50.5, "M_paint_metal_dark")
        for x in (-1.8, 5.62):
            B.box(x, 0.0, 50.38, x + 0.14, 2.7, 50.52, "M_paint_metal_dark")
    B.cprism(S, -0.3, 0.0)
    B.cbox(-1.9, 0.0, 50.35, 5.8, 3.0, 50.55)
    B.cbox(-1.9, 3.85, 47.4, 5.8, 4.3, 50.4)
    light(B, "gate", 2.0, 3.55, 48.9, K(3000), 0.8, 6.0)


RS29 = [(30.3, 44.8), (30.0, 53.5), (38.1, 53.8), (38.4, 46.9), (38.4, 45.0), (35.5, 44.9), (35.6, 43.8), (34.2, 43.8),
        (34.3, 44.9)]                                   # docs/campus_layout.svg outlines (cadastre)
RS31 = [(38.6, 39.7), (38.4, 42.7), (40.8, 42.8), (40.5, 47.0), (38.4, 46.9), (38.1, 53.8), (45.4, 54.0), (47.7, 51.7),
        (47.0, 40.0), (38.5, 39.5)]
RS_SHARED = ((38.1, 53.8), (38.4, 46.9))


def salengro_29_31(B):
    """29 and 31 rue Roger Salengro: brick, 1894 and 1900, 3 and 5 levels, 12.8 m and 17.2 m.
    They rise behind the east building; between them and the courtyard's south-east pocket lies their yard, behind
    a wall on the parcel line. Windows only where they can be seen from the campus."""
    B.use("rs_29_31")
    B.use_col("COL_buildings")
    with B.ground_at(0.0):
        B.box(30.3, -0.3, 39.3, 41.0, -0.01, 47.1, "M_concrete_floor", skip="nsewb", sub=4.0)
        fac(B, 30.6, 39.4, 30.5, 41.7, 0.0, 2.6, 0.25, "M_concrete", "M_concrete", (), top=True, mat_top="M_zinc")
        for poly, h, levels, seed in ((RS29, 12.8, 3, 2600), (RS31, 17.2, 5, 2700)):
            P = PG.cw(poly)
            roof = h - 0.6
            st = roof / levels
            for i, (a, b) in enumerate(PG.edges(P)):
                L = PG.length(a, b)
                n = PG.outward(a, b)
                y0, y_min = 0.0, 2.6                      # above the yard wall
                if same_edge(a, b, *RS_SHARED):
                    if h < 13:
                        continue                          # 29's side of the party wall is inside 31
                    y0 = y_min = 12.8
                elif same_edge(a, b, (30.0, 53.5), (30.3, 44.8)) or n[1] > 0.7:
                    y_min = None                          # against the south building, or on the street: out of sight
                elif n[1] < -0.7 and (a[1] + b[1]) / 2 < 40.6:
                    y_min = 6.4                           # behind the east building
                ops = []
                if y_min is not None:
                    k = int((L - 0.6) // 2.4)
                    m = (L - k * 2.4) / 2
                    for f in range(levels):
                        fy = f * st
                        if fy + 0.3 < y_min:
                            continue
                        for j in range(k):
                            ops.append(ext_win(m + 2.4 * (j + 0.5), 1.15, fy + 0.35, fy + 2.35, seed + i * 53 + f * 11 + j,
                                               lit=0.35, frame="M_pvc_white", cols=2, sill="M_concrete"))
                fac(B, a[0], a[1], b[0], b[1], y0, roof, 0.3, "M_brick", False, ops, top=False, ends=False)
                xf, _ = wall_frame(a[0], a[1], b[0], b[1])
                with B.frame(xf):
                    B.box(-0.02, roof - 0.35, 0.0, L + 0.02, roof - 0.15, 0.08, "M_concrete")
                    A.parapet(B, L, roof, 0.6, 0.3, "M_brick", inner_mat="M_concrete", coping="M_zinc")
            B.prism(P, roof - 0.3, roof, "M_roof", top=True, sides=False)


# ------------------------------------------------------------------ ramp down to the Under
def ramp(B):
    B.use("ramp")
    B.use_col("COL_court")
    x0, x1 = 12.0, 25.5
    with B.ground_at(UY):
        # sloped slab (visual) + landing
        B.quad((x0, 0.0, 39.2), (x1, UY, 39.2), (x1, UY, 36.2), (x0, 0.0, 36.2), "M_concrete_floor")
        B.box(x1, UY - 0.3, 36.2, 28.5, UY, 39.2, "M_concrete_floor", skip="nsewb")
        # anti-slip grooves across the ramp
        n = 26
        for k in range(1, n):
            t = k / n
            x = x0 + (x1 - x0) * t
            y = UY * t
            B.box(x - 0.03, y, 36.25, x + 0.03, y + 0.008, 39.15, "M_steel_dark", skip="b")
        # retaining walls: north (under the courtyard edge) and east
        fac(B, 12.0, 36.2, 28.7, 36.2, UY - 0.3, 0.0, 0.2, "M_concrete", False, (), top=True, mat_top="M_concrete", ends=True, col=False)
        fac(B, 28.7, 39.2, 28.7, 36.0, UY - 0.3, 0.0, 0.2, False, "M_concrete", (), top=True, mat_top="M_concrete", col=False)
        # the eart-sup / Under wall on the south side of the trench, with the Under door
        ops = [Opening(28.5 - 27.8, 28.5 - 26.2, UY, UY + 2.3, "passage")]
        fac(B, 28.5, 39.2, 12.0, 39.2, UY, 0.0, 0.3, "M_concrete_dark", False, ops, top=False, ends=False, col=False)
    B.cramp(x0, 0.0, 37.7, x1, UY, 37.7, 3.0, 0.3)
    B.cbox(x1, UY - 0.5, 36.2, 28.5, UY, 39.2)
    B.cbox(12.0, UY - 0.5, 36.0, 28.7, 0.0, 36.2)
    B.cbox(28.5, UY - 0.5, 36.0, 28.7, 0.0, 39.2)
    B.cbox(12.0, UY, 39.2, 26.2, 0.0, 39.5)
    B.cbox(27.8, UY, 39.2, 28.5, 0.0, 39.5)
    B.cbox(26.2, UY + 2.3, 39.2, 27.8, 0.0, 39.5)
    B.cbox(26.2, UY - 0.5, 39.15, 27.8, UY, 39.55)        # door threshold
    B.box(26.2, UY - 0.02, 39.2, 27.8, UY + 0.004, 39.5, "M_steel", skip="nsewb")
    # glass balustrade on the courtyard edge + steel rail on the east edge, handrails down the ramp
    with B.frame(wall_frame(12.0, 36.1, 28.6, 36.1)[0]):
        A.glass_railing(B, 0.0, 16.6, 0.0, col_group="COL_court")
    with B.frame(wall_frame(28.6, 36.1, 28.6, 39.2)[0]):
        A.glass_railing(B, 0.0, 3.1, 0.0, col_group="COL_court")
    # the south buildings now stand back at z 41.1-41.7, so the trench's south edge is open courtyard too
    with B.frame(wall_frame(28.6, 39.3, 12.0, 39.3)[0]):
        A.glass_railing(B, 0.0, 16.6, 0.0, col_group="COL_court")
    A.handrail(B, [(12.0, 0.0, 36.32), (25.5, UY, 36.32), (28.4, UY, 36.32)], h=0.9, r=0.025, post_every=2.0)
    A.handrail(B, [(12.0, 0.0, 39.08), (25.5, UY, 39.08), (26.0, UY, 39.08)], h=0.9, r=0.025, post_every=2.0)
    # teal door frame of the Under (door leaf swung inwards)
    B.box(26.1, UY, 39.1, 26.2, UY + 2.4, 39.6, "M_paint_metal_teal")
    B.box(27.8, UY, 39.1, 27.9, UY + 2.4, 39.6, "M_paint_metal_teal")
    B.box(26.1, UY + 2.3, 39.1, 27.9, UY + 2.4, 39.6, "M_paint_metal_teal")
    with B.at(26.2, 0, 39.5, -math.pi / 2 * 0.92):
        B.box(0.0, UY + 0.01, -0.025, 1.58, UY + 2.29, 0.025, "M_paint_metal_teal")
        B.box(1.35, UY + 1.0, 0.025, 1.47, UY + 1.04, 0.07, "M_alu_silver")
    light(B, "ramp_neon", 26.5, -1.4, 37.7, "#c6ff7a", 1.4, 8.0, shadow=True)
    light(B, "ramp_top", 18.0, -0.6, 37.7, K(3000), 0.8, 8.0)


# ------------------------------------------------------------------ the Under (BDE basement)
def under(B):
    B.use("under")
    B.use_col("COL_under")
    x0, x1, z0, z1 = 2.0, 28.0, 39.5, 52.0
    with B.ground_at(UY):
        B.box(x0, UY - 0.3, z0, x1, UY, z1, "M_rubber_floor", skip="nsewb", sub=3.0)
        ops = [Opening(26.2 - x0, 27.8 - x0, UY, UY + 2.3, "passage")]
        fac(B, x1, z0 - 0.3, x0, z0 - 0.3, UY, -0.3, 0.3, False, "M_paint_under", [Opening(28.0 - 27.8, 28.0 - 26.2, UY, UY + 2.3, "passage")],
            top=False, ends=False, base_in=("M_paint_metal_dark", 0.12), col=False)
        fac(B, x0, z1 + 0.3, x1, z1 + 0.3, UY, -0.3, 0.3, False, "M_paint_under", (), top=False, ends=False, base_in=("M_paint_metal_dark", 0.12))
        fac(B, x0 - 0.3, z0, x0 - 0.3, z1, UY, -0.3, 0.3, False, "M_paint_under_teal", (), top=False, ends=False, base_in=("M_paint_metal_dark", 0.12))
        ops = [Opening(z1 - 49.0, z1 - 47.6, UY, UY + 2.2, "blank")]
        fac(B, x1 + 0.3, z1, x1 + 0.3, z0, UY, -0.3, 0.3, False, "M_paint_under", ops, top=False, ends=False, base_in=("M_paint_metal_dark", 0.12))
        # emergency exit (blocked) on the east wall
        B.box(27.9, UY, 47.6, 28.0, UY + 2.2, 49.0, "M_paint_metal_teal")
        B.box(27.88, UY + 1.0, 48.0, 27.9, UY + 1.06, 48.6, "M_alu_silver")
        # concrete ceiling slab
        B.rect((x0, -0.3, z0), (x1 - x0, 0, 0), (0, 0, z1 - z0), "M_concrete_dark", sub=3.0)
        # sticker columns
        for (cx, cz) in ((9.0, 45.5), (21.0, 45.5)):
            B.box(cx - 0.3, UY, cz - 0.3, cx + 0.3, -0.3, cz + 0.3, "M_concrete", skip="tb")
            B.cbox(cx - 0.3, UY, cz - 0.3, cx + 0.3, -0.3, cz + 0.3)
    B.cbox(x0, UY - 0.5, z0, x1, UY, z1)
    B.cbox(x0, -0.3, z0 - 0.3, x1, 0.0, z1)
    B.cbox(x0 - 0.3, UY, z0 - 0.3, x0, -0.3, z1 + 0.3)
    B.cbox(x1, UY, z0 - 0.3, x1 + 0.3, -0.3, z1 + 0.3)
    B.cbox(x0, UY, z1, x1, -0.3, z1 + 0.3)
    B.cbox(x0, UY, z0 - 0.3, 26.2, -0.3, z0)
    B.cbox(27.8, UY, z0 - 0.3, x1, -0.3, z0)
    B.cbox(26.2, UY + 2.3, z0 - 0.3, 27.8, -0.3, z0)
    # ducts (the old Indoor.duct) and a cable tray
    B.use("under_services")
    for z in (42.0, 46.0, 50.0):
        B.cyl_axis((3.0, -0.75, z), (27.0, -0.75, z), 0.3, "M_zinc", seg=16)
        for x in (5.0, 11.0, 17.0, 23.0):
            B.box(x - 0.03, -0.45, z - 0.33, x + 0.03, -0.3, z + 0.33, "M_steel_dark")
    B.cyl_axis((8.0, -0.6, 40.0), (8.0, -0.6, 51.5), 0.22, "M_zinc", seg=14)
    B.box(14.0, -0.52, 39.8, 14.4, -0.48, 51.7, "M_steel_dark")
    for (x, z, c, n) in ((6, 43, K(2700), "under_sofa"), (15, 46, K(5000), "under_babyfoot"), (22, 49.5, K(5000), "under_tables"),
                         (25, 42, "#ff9ad1", "under_bar")):
        light(B, n, x, -0.9, z, c, 1.6, 11.0, shadow=n in ("under_babyfoot", "under_tables", "under_sofa"))
        B.box(x - 0.6, -0.36, z - 0.15, x + 0.6, -0.3, z + 0.15, "M_paint_metal_dark", skip="t")
        B.box(x - 0.56, -0.37, z - 0.11, x + 0.56, -0.36, z + 0.11, "M_light_panel" if n != "under_bar" else "M_neon_pink", skip="t")
    light(B, "under_neon_lime", 15.0, -1.2, 51.6, "#b8ff2a", 1.0, 6.0)
