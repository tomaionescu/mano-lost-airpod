"""Rue Pasteur between x -80 and the rue Emile Zola kerb: road, curbs, sidewalks, markings, drains. The buildings
along it, the street's ends and the streets beyond are campus_backdrop."""
import math, random
import campus_arch as A
import campus_poly as PG
from campus_arch import Opening, wall_frame
from campus_layout import *

SIDE_N = -5.0     # building line north side (KB1, ARPEJ, 13-17 rue Pasteur)
SIDE_S = 5.0      # building line south side (Paritalie's wing ends, 24 rue Pasteur); 10 m apart
X_W, X_E = -80.0, 47.1   # extent of this street piece; east of X_E the rue Emile Zola junction (campus_backdrop)
CURB_N, CURB_S = -3.2, 3.2       # kerb lines
SW_TOP = 0.1
BIKE_Z = -0.25    # dashed edge of the eastbound contraflow cycle lane; cars park south of it
DROP_N = (6.0, 11.0)             # dropped kerbs: the zebra in front of no. 24 ...
DROP_S = (-1.7, 11.0)            # ... and on the south side also the passage's step-free driveway


def card_rect(seed, lit=0.4):
    """pick a cell of the fake-interior atlas (4 x 2 cells; cells 0-3 lit, 4-7 dark) for a window"""
    r = random.Random(seed)
    cell = r.randrange(0, 4) if r.random() < lit else r.randrange(4, 8)
    cx, cy = cell % 4, cell // 4
    return (cx / 4 + 0.004, 1 - (cy + 1) / 2 + 0.004, (cx + 1) / 4 - 0.004, 1 - cy / 2 - 0.004)


def facade(B, ax, az, bx, bz, y0, y1, thick, mat_out, openings, mat_in=False, **kw):
    xf, L = wall_frame(ax, az, bx, bz)
    with B.frame(xf):
        A.wall(B, L, y0, y1, thick, mat_out, mat_in, openings, **kw)
    return L


def window_grid(L, storeys, bay, w, sill, h, margin=None, skip=(), kind="window", seed=0, lit=0.4, **opt):
    """regular grid of exterior-only windows with fake-interior cards. storeys: list of floor levels"""
    n = max(1, int((L - (margin or 0) * 2) // bay))
    m = (L - n * bay) / 2 if margin is None else margin + ((L - 2 * margin) - n * bay) / 2
    ops = []
    for si, fy in enumerate(storeys):
        for k in range(n):
            if (si, k) in skip:
                continue
            u = m + bay * (k + 0.5)
            card = ("M_room_card", card_rect(seed * 7919 + si * 131 + k, lit))
            o = dict(opt)
            o.setdefault("card", card)
            ops.append(Opening(u - w / 2, u + w / 2, fy + sill, fy + sill + h, kind, **o))
    return ops


# ------------------------------------------------------------------ ground
def ground(B):
    B.use("street_ground")
    B.use_col("COL_street")
    with B.ground_at(0.0):
        # road + gutters (caniveaux)
        B.box(X_W, -0.3, CURB_N + 0.25, X_E, 0.0, CURB_S - 0.25, "M_asphalt", skip="nsewb", sub=6.0)
        for z0, z1 in ((CURB_N, CURB_N + 0.25), (CURB_S - 0.25, CURB_S)):
            B.box(X_W, -0.3, z0, X_E, -0.005, z1, "M_gutter", skip="nsewb", sub=6.0)
        # granite curbs in 1 m stones with slight colour variation, dropped at the zebra and the passage driveway
        rng = random.Random(7)
        for side, (z0, z1), (d0, d1) in (("n", (-3.35, CURB_N), DROP_N), ("s", (CURB_S, 3.35), DROP_S)):
            x = X_W
            while x < X_E - 1e-6:
                L = min(1.0, X_E - x)
                drop = d0 <= x + L / 2 <= d1
                top = 0.02 if drop else SW_TOP
                t = 0.94 + rng.random() * 0.1
                with B.tinted((t, t, t * 1.01)):
                    B.box(x, -0.3, z0, x + L, top, z1, "M_curb", skip="b", sub=None)
                x += L
        # no stopping on the north side: yellow kerb paint
        for (x0, x1) in ((X_W, DROP_N[0]), (DROP_N[1], X_E)):
            B.box(x0, 0.0, CURB_N, x1, SW_TOP + 0.002, CURB_N + 0.004, "M_road_paint_yellow", skip="nb")
            B.box(x0, SW_TOP, -3.3, x1, SW_TOP + 0.003, CURB_N, "M_road_paint_yellow", skip="b")
        # sidewalks
        B.box(X_W, -0.3, SIDE_N, X_E, SW_TOP, -3.35, "M_sidewalk", skip="nsb", sub=4.0)
        B.box(X_W, -0.3, 3.35, X_E, SW_TOP, SIDE_S, "M_sidewalk", skip="nsb", sub=4.0)
        # tactile warning strips at the crosswalk
        for z0, z1 in ((-3.95, -3.35), (3.35, 3.95)):
            B.box(DROP_N[0] + 0.2, SW_TOP, z0, DROP_N[1] - 0.2, SW_TOP + 0.006, z1, "M_gutter", skip="b")
    # colliders: road, curb slopes (walkable), sidewalks
    B.cbox(X_W, -0.6, CURB_N, X_E, 0.0, CURB_S)
    B.cramp(5, 0.0, CURB_N + 0.05, 5, SW_TOP, -3.45, X_E - X_W + 10)
    B.cramp(5, 0.0, CURB_S - 0.05, 5, SW_TOP, 3.45, X_E - X_W + 10)
    B.cbox(X_W, -0.6, SIDE_N, X_E, SW_TOP, -3.45)
    B.cbox(X_W, -0.6, 3.45, X_E, SW_TOP, SIDE_S)
    markings(B)
    drains(B)


ZEBRA = (6.0, 11.0)   # in front of no. 24
BUMP_X = -21.1        # the one speed bump


def arrow(B, x, z, dirx, length=4.0, width=0.9, y=0.004, mat="M_road_paint"):
    """painted lane arrow along x (dirx = +1 east, -1 west)"""
    head = width * 1.1
    sx = length - head
    x0 = x - dirx * length / 2
    xs = x0 + dirx * sx
    B.box(min(x0, xs), 0, z - 0.09, max(x0, xs), y, z + 0.09, mat, skip="nsewb")
    tip = x0 + dirx * length
    pts = [(xs, y, z - width / 2), (tip, y, z), (xs, y, z + width / 2)]
    B.face(pts if dirx < 0 else pts[::-1], mat)


def bike_symbol(B, x, z, y=0.004, mat="M_road_paint"):
    """cycle-lane pictogram (two wheels and a frame), riders heading east"""
    for cx in (x - 0.55, x + 0.55):
        n = 14
        for k in range(n):
            a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
            pts = [(cx + math.cos(a) * r, y, z + math.sin(a) * r) for a, r in ((a0, 0.36), (a1, 0.36), (a1, 0.28), (a0, 0.28))]
            B.face(pts[::-1], mat)
    for (ax, az, bx, bz) in ((x - 0.55, z, x - 0.05, z), (x - 0.05, z, x + 0.35, z - 0.45), (x - 0.55, z, x - 0.15, z - 0.45),
                             (x - 0.15, z - 0.45, x + 0.35, z - 0.45), (x + 0.35, z - 0.45, x + 0.55, z),
                             (x - 0.2, z - 0.55, x - 0.05, z - 0.55)):
        B.seg_box(ax, az, bx, bz, 0.0, y, 0.07, mat, skip="nsewb")


def markings(B):
    """one-way westbound with an eastbound contraflow cycle lane on the south side; cars park
    along the south kerb only; zebra in front of no. 24 and one speed bump"""
    B.use("street_marks", cast=False)
    y = 0.004
    # dashed edge of the cycle lane (3 m dash / 1.5 m gap), broken at the zebra and the bump; it stops before the
    # zebra across the rue Emile Zola junction (campus_backdrop)
    x = X_W + 1
    while x < 40.3:
        if not (ZEBRA[0] - 3.2 < x < ZEBRA[1] + 0.2) and not (BUMP_X - 3.5 < x < BUMP_X + 0.5):
            B.box(x, 0, BIKE_Z - 0.06, x + 3.0, y, BIKE_Z + 0.06, "M_road_paint", skip="nsewb")
        x += 4.5
    for xa in (-31.0, 24.0):
        arrow(B, xa, -1.75, -1)
    for xb in (-13.5, 17.0, 39.0):
        bike_symbol(B, xb, 0.75)
        arrow(B, xb + 2.4, 0.5, 1, length=1.6, width=0.45)
    # zebra crossing: bands parallel to the road, 0.5 m wide every metre, kerb to kerb
    for k in range(6):
        z0 = -2.9 + k * 1.0 + 0.25
        B.box(ZEBRA[0], 0, z0, ZEBRA[1], y + 0.001, z0 + 0.5, "M_road_paint", skip="nsewb")
    # the speed bump
    xb = BUMP_X - 0.3
    B.box(xb, 0, -2.9, xb + 0.6, 0.06, 2.9, "M_asphalt", skip="b")
    for k in range(6):
        B.box(xb + 0.1, 0.06, -2.7 + k * 1.0, xb + 0.5, 0.064, -2.3 + k * 1.0, "M_road_paint_yellow", skip="b")
    B.cramp(xb - 0.6, 0.0, 0, xb, 0.06, 0, 6.2)
    B.cramp(xb + 1.2, 0.0, 0, xb + 0.6, 0.06, 0, 6.2)
    B.cbox(xb, -0.1, -3.1, xb + 0.6, 0.06, 3.1)


def drains(B):
    """gutter inlets (avaloirs): dark slot in the curb + grate in the gutter"""
    B.use("street_ground")
    for x in (-70.0, -52.0, -24.0, 0.5, 26.0):
        for zg, zc, s in ((CURB_N + 0.125, -3.275, -1), (CURB_S - 0.125, 3.275, 1)):
            xx = x + (7 if s > 0 else 0)
            B.box(xx - 0.45, -0.004, zg - 0.13, xx + 0.45, 0.0, zg + 0.13, "M_cast_iron", skip="b")
            for k in range(9):
                gx = xx - 0.4 + k * 0.1
                B.box(gx - 0.012, 0.0, zg - 0.11, gx + 0.012, 0.006, zg + 0.11, "M_cast_iron", skip="b")
            # curb mouth
            B.box(xx - 0.5, 0.02, zc - 0.08, xx + 0.5, 0.075, zc + 0.08, "M_room_sleeve", skip="b")

