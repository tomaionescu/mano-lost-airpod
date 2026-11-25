"""Set dressing: PROP_ markers for every repeated prop (positions from the old Campus.js) and the unique
pieces built straight into the level: signage + logo, reception desk, counters, whiteboards, the slide,
posters, notice boards, radiators, string lights, the Under's neon and stickers, rooftop units."""
import math, random
from mathutils import Vector
import campus_arch as A
from campus_arch import wall_frame
from campus_geo import Xf
from campus_layout import *
from campus_mat import K
import campus_gen
import campus_poly as PG
import campus_street
from campus_voltaire import light, CEIL0, CEIL1, ROOF

PI = math.pi
_count = {}


def prop(B, asset, x, y, z, yaw=0.0):
    n = _count.get(asset, 0)
    _count[asset] = n + 1
    B.marker("PROP_%s__%02d" % (asset, n), (x, y, z), yaw, {"asset": asset}, display="ARROWS", size=0.25)


def font(n):
    return campus_gen.font(n)


def panel_text(B, lines, w, h, bg, depth=0.03, pad=0.08):
    """sign plate centred on the local origin in the XY plane, text on its front (+Z) face.
    lines: [(text, size, font, mat), ...] laid out top to bottom"""
    if bg:
        B.box(-w / 2, -h / 2, -depth, w / 2, h / 2, 0.0, bg)
    total = sum(sz for _, sz, _, _ in lines) * 1.25
    y = total / 2
    for txt, sz, fn, m in lines:
        y -= sz * 1.0
        with B.at(0.0, y, 0.002):
            B.text(txt, font(fn), sz, m, align="CENTER", valign="BASE", maxw=w - pad * 2)
        y -= sz * 0.25


def sign(B, x, y, z, yaw, w, h, bg, lines, depth=0.03):
    with B.at(x, y, z, yaw):
        panel_text(B, lines, w, h, bg, depth)


def poster(B, key, x, y, z, yaw, w=0.6, h=0.8):
    with B.at(x, y, z, yaw):
        B.quad((-w / 2, -h / 2, 0.004), (w / 2, -h / 2, 0.004), (w / 2, h / 2, 0.004), (-w / 2, h / 2, 0.004), "M_poster_" + key,
               uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        for cx, cy in ((-w / 2 + 0.03, h / 2 - 0.03), (w / 2 - 0.03, h / 2 - 0.03)):
            B.box(cx - 0.012, cy - 0.012, 0.004, cx + 0.012, cy + 0.012, 0.007, "M_alu_silver")


def notice_board(B, x, y, z, yaw, w=1.2, h=0.9, seed=0):
    rng = random.Random(seed)
    with B.at(x, y, z, yaw):
        B.box(-w / 2, -h / 2, 0.0, w / 2, h / 2, 0.02, "M_alu_silver")
        B.box(-w / 2 + 0.03, -h / 2 + 0.03, 0.0, w / 2 - 0.03, h / 2 - 0.03, 0.024, "M_cork")
        for k in range(rng.randrange(3, 6)):
            pw, ph = 0.21, 0.297
            cx = rng.uniform(-w / 2 + 0.16, w / 2 - 0.16)
            cy = rng.uniform(-h / 2 + 0.2, h / 2 - 0.2)
            a = rng.uniform(-0.08, 0.08)
            ca, sa = math.cos(a), math.sin(a)
            pts = [(-pw / 2, -ph / 2), (pw / 2, -ph / 2), (pw / 2, ph / 2), (-pw / 2, ph / 2)]
            z0 = 0.026 + k * 0.001
            B.quad(*[(cx + px * ca - py * sa, cy + px * sa + py * ca, z0) for px, py in pts], "M_notice_%d" % rng.randrange(6),
                   uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
            B.box(cx - 0.008, cy + ph / 2 - 0.03, z0, cx + 0.008, cy + ph / 2 - 0.014, z0 + 0.012, "M_plastic_red")


def radiator(B, x, y, z, yaw, w=1.2, h=0.55):
    with B.at(x, y, z, yaw):
        n = int(w / 0.05)
        for k in range(n):
            xx = -w / 2 + (k + 0.5) * w / n
            B.box(xx - 0.018, 0.0, 0.03, xx + 0.018, h, 0.11, "M_paint_metal_white")
        B.box(-w / 2, 0.05, 0.05, w / 2, 0.09, 0.09, "M_paint_metal_white")
        B.box(-w / 2, h - 0.09, 0.05, w / 2, h - 0.05, 0.09, "M_paint_metal_white")
        B.cyl(w / 2 + 0.04, 0.0, 0.07, 0.012, 0.15, "M_chrome", seg=6)
        B.box(w / 2 + 0.02, 0.12, 0.05, w / 2 + 0.06, 0.18, 0.09, "M_plastic_white")


def string_lights(B, a, b, sag=0.6, step=0.55, mat="M_light_string", wire="M_plastic_black", r=0.045):
    a, b = Vector(a), Vector(b)
    L = (b - a).length
    n = max(2, int(L / step))
    pts = []
    for i in range(n + 1):
        t = i / n
        p = a.lerp(b, t)
        p.y -= sag * 4 * t * (1 - t)
        pts.append(p)
    B.tube(pts, 0.006, wire, seg=4, caps=False)
    for p in pts[1:-1]:
        B.box(p.x - 0.004, p.y - 0.06, p.z - 0.004, p.x + 0.004, p.y, p.z + 0.004, wire)
        B.sphere(p.x, p.y - 0.06 - r, p.z, r, mat, seg=6, rings=4)
    return pts


def hang_points(a, b, sag, ts):
    a, b = Vector(a), Vector(b)
    out = []
    for t in ts:
        p = a.lerp(b, t)
        p.y -= sag * 4 * t * (1 - t)
        out.append(p)
    return out


# ------------------------------------------------------------------ the street
def street(B):
    B.use("street_dress")
    B.use_col("COL_street")
    S = campus_street
    # curved single-arm lamps on grey poles, on the north side only; east of rue Emile Zola
    # the bent street has its own (campus_backdrop.junction)
    lamp_shadow = {-6, 10, 26}
    north = [-70, -54, -38, -22, -6, 10, 26, 40]
    for x in north:
        prop(B, "street_lamp", x, 0.1, -3.62, 0.0)
        light(B, "street_n%+04d" % int(x), x, 4.85, -2.72, K(3000), 2.6, 15.0, shadow=x in lamp_shadow)
    # street trees in pits on the south sidewalk (kept) and dark-brown bollards along the south kerb
    trees = [-60, -44, -28, -16.5, 21.5, 31]
    for x in trees:
        prop(B, "tree_plane", x, 0.1, 3.85, PI)
    racks = (11.9, 13.9, 15.9, 17.9)
    x = -34.0
    while x < 43:
        if not (S.DROP_S[0] - 0.4 < x < S.DROP_S[1] + 0.4) and all(abs(x - t) > 1.0 for t in trees) and \
                not (racks[0] - 1.2 < x < racks[-1] + 1.2) and abs(x + 23.0) > 0.6 and abs(x + 2.6) > 0.5:
            prop(B, "bollard", x, 0.1, 3.5)
        x += 2.2
    # no parking on the north side: concrete separator blocks on the road along the yellow kerb
    x = -34.5
    while x < 43.0:
        if not (S.DROP_N[0] - 1.0 < x < S.DROP_N[1] + 0.6) and abs(x - S.BUMP_X) > 1.2:
            B.box(x - 0.3, 0.0, -3.17, x + 0.3, 0.17, -2.93, "M_concrete", skip="b")
            B.box(x - 0.27, 0.17, -3.15, x + 0.27, 0.2, -2.95, "M_concrete", skip="b")
            B.cbox(x - 0.3, 0.0, -3.17, x + 0.3, 0.2, -2.93)
        x += 3.0
    for (bx, bz, yaw) in ((-9, -3.78, PI), (14.5, -3.78, PI), (-4, 3.78, 0.0), (24.5, 3.78, 0.0), (-40, -3.78, PI)):
        prop(B, "bin_paris", bx, 0.1, bz, yaw)
    # parked cars along the south kerb only, west of the passage and in front of the east building (S4 corrected)
    for (cx, kind) in ((-60.0, "car_sedan_green"), (-47.0, "car_sedan_white"), (-41.5, "car_hatch_red"), (-26.0, "car_hatch_blue"),
                       (-18.1, "car_hatch_red"), (-14.0, "car_sedan_white"), (30.2, "car_sedan_green"), (34.8, "car_hatch_blue")):
        prop(B, kind, cx, 0.0, 2.2, PI / 2)
    # motorcycle bay for 5 at x 25.5 (OSM), in the parking lane, mopeds nose to the kerb
    for (a, b, c, d) in ((23.0, 1.3, 28.0, 1.38), (23.0, 3.0, 28.0, 3.08), (23.0, 1.3, 23.08, 3.08), (27.92, 1.3, 28.0, 3.08)):
        B.box(a, 0.0, b, c, 0.004, d, "M_road_paint", skip="nsewb")
    for (mx, kind, r) in ((23.8, "moped_red", 0.06), (25.3, "moped_blue", -0.08), (26.9, "moped_red", 0.1)):
        prop(B, kind, mx, 0.0, 2.15, r)
    prop(B, "moped_red", -9.4, 0.0, 2.5, 0.2 + PI / 2)
    prop(B, "moped_blue", -10.9, 0.0, 2.55, -0.1 + PI / 2)
    # bike stands for 10 bikes on the south sidewalk at x ~13.6 (OSM): no Velib' station on rue Pasteur
    for xr in racks:
        prop(B, "bike_rack", xr, 0.1, 4.2, 0.0)
    for (xb, zb, kind, yaw) in ((12.9, 3.9, "velib_bike_blue", PI / 2), (16.9, 4.55, "velib_bike_green", -PI / 2)):
        prop(B, kind, xb, 0.1, zb, yaw)
    # barriers at the gameplay walls (campus_backdrop.WALL_W / WALL_E): past Paritalie's north-west wing end and at
    # the rue Emile Zola kerb
    for xb in (-47.5, 46.0):
        for zb in (-4.2, -2.6, -0.85, 0.85, 2.6, 4.2):
            prop(B, "road_barrier", xb, 0.1 if abs(zb) > 3.3 else 0.0, zb, PI / 2)
    prop(B, "sign_zone30", -33.0, 0.1, -3.62, 0.0)
    prop(B, "sign_zone30", 41.0, 0.1, 3.62, PI)
    prop(B, "sign_no_parking", -2.6, 0.1, 3.62, PI)
    prop(B, "sign_no_parking", 4.6, 0.1, -3.62, 0.0)
    prop(B, "parking_meter", -23.0, 0.1, 3.72, PI)
    prop(B, "utility_cabinet", -33.5, 0.1, -4.75, 0.0)
    prop(B, "utility_cabinet", 42.0, 0.1, 5.6, PI)
    # manhole covers
    for (mx, mz) in ((-14.0, 0.8), (6.0, -1.3), (28.0, 0.6), (-40.0, -0.7), (50.0, 1.0)):
        B.cyl(mx, 0.0, mz, 0.34, 0.006, "M_cast_iron", seg=24)
        for k in range(5):
            B.box(mx - 0.28 + k * 0.14 - 0.02, 0.006, mz - 0.25, mx - 0.28 + k * 0.14 + 0.02, 0.009, mz + 0.25, "M_cast_iron")
    # direction sign (old: x=-31 'Porte d'Italie ->  M7 - T3a')
    B.cyl(-31.0, 0.1, 4.8, 0.035, 2.95, "M_zinc", seg=10)
    B.cbox(-31.05, 0.1, 4.75, -30.95, 2.9, 4.85)
    sign(B, -31.0, 2.5, 4.76, PI, 1.4, 0.45, "M_signal_white",
         [("Porte d'Italie  >", 0.15, "sign", "M_signal_blue"), ("M7  -  T3a", 0.11, "sign", "M_signal_blue")], depth=0.02)
    prop(B, "morris_column", 36.0, 0.1, -4.4, 0.0)


# ------------------------------------------------------------------ Batiment Voltaire
def voltaire(B):
    B.use("volt_dress")
    B.use_col("COL_voltaire")
    # rue Pasteur front (campus_kb1 builds it and the "KB1" portal; no logo): the building's name
    # behind the glass on the lettering band over the west door, the street plate on the west corner pier, the
    # "19" house plate on the pier where OSM has the back entrance's address
    with B.at(-13.45, 3.01, -4.749):
        B.text("BATIMENT VOLTAIRE", font("sign"), 0.15, "M_plate_white", align="CENTER", valign="CENTER", depth=0.004,
               maxw=2.2)
    sign(B, -28.42, 3.3, -4.98, 0.0, 0.8, 0.3, "M_signal_blue",
         [("RUE PASTEUR", 0.12, "cond", "M_plate_white"), ("Le Kremlin-Bicetre", 0.055, "semi", "M_plate_white")], depth=0.02)
    with B.at(-28.42, 3.3, -4.96):
        B.box(-0.4, -0.15, 0.0, 0.4, -0.137, 0.004, "M_plate_white")
        B.box(-0.4, 0.137, 0.0, 0.4, 0.15, 0.004, "M_plate_white")
    sign(B, -4.45, 2.65, -4.985, 0.0, 0.26, 0.2, "M_signal_blue", [("19", 0.13, "semi", "M_plate_white")], depth=0.012)
    with B.at(-4.45, 2.65, -4.972):
        A.frame_rect(B, -0.12, 0.12, -0.09, 0.09, 0.0, 0.003, 0.012, "M_plate_white")
    # GF: reception desk (accueil) with the lost & found box
    reception(B)
    sign(B, -3.0, 2.7, -25.84, 0.0, 2.4, 0.6, "M_plate_white",
         [("ACCUEIL", 0.26, "bold", "M_epita_blue"), ("reception  -  lost & found", 0.1, "semi", "M_epita_blue")])
    with B.at(7.1, 1.4, -25.69):
        B.box(-0.3, -0.09, 0.0, 0.3, 0.09, 0.003, "M_paint_metal_yellow")
        with B.at(0, -0.04, 0.004):
            B.text("EN PANNE", font("black"), 0.09, "M_plastic_black", align="CENTER", valign="BOTTOM")
    sign(B, -14.0, 2.75, -18.96, 0.0, 1.6, 0.3, "M_epita_blue", [("International Office", 0.12, "bold", "M_plate_white")], depth=0.015)
    # hanging stair sign
    with B.at(11.7, 2.6, -11.95):
        for s in (-0.6, 0.6):
            B.box(s - 0.004, 0.22, -0.004, s + 0.004, CEIL0 - 2.6, 0.004, "M_alu_silver")
        panel_text(B, [("1er etage", 0.15, "bold", "M_plate_white"), ("SM14  -  SM15", 0.1, "semi", "M_epita_lime")], 1.4, 0.45, "M_epita_blue",
                   depth=0.03)
    # EPITA feature wall + JPO screen + info
    epita_logo(B, -21.0, 2.0, -11.69, 0.0, 4.2)
    with B.at(-8.0, 2.1, -11.9):
        for s in (-1.0, 1.0):
            B.box(s - 0.004, 0.5, -0.004, s + 0.004, CEIL0 - 2.1, 0.004, "M_alu_silver")
        B.box(-1.25, -0.55, -0.05, 1.25, 0.55, 0.0, "M_plastic_black")
        B.quad((-1.2, -0.5, 0.001), (1.2, -0.5, 0.001), (1.2, 0.5, 0.001), (-1.2, 0.5, 0.001), "M_jpo_screen", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    light(B, "jpo_screen", -8.0, 2.0, -11.0, "#4d61d6", 0.6, 4.0)
    poster(B, "forum", 16.0, 1.7, -11.84, 0.0)
    poster(B, "piscine", 17.0, 1.7, -11.84, 0.0)
    poster(B, "wei", -24.69, 1.7, -8.0, PI / 2)
    notice_board(B, -5.0, 1.55, -25.84, 0.0, seed=1)
    notice_board(B, 1.5, 1.55, -25.84, 0.0, seed=2)
    # radiators under the street bays (campus_kb1.STREET_BAYS, not the west door's) and the yard windows
    for x in (-25.45, -19.45, -7.45, -1.45, 4.55, 14.35, 19.5):
        radiator(B, x, 0.12, -5.3, PI, w=1.6)
    for z in (-22.0, -16.0):
        radiator(B, -17.85, 0.12, z, PI / 2, w=1.6)
    # props
    prop(B, "lockers_4", 3.7, 0.0, -11.65, 0.0)
    prop(B, "lockers_4", 5.3, 0.0, -11.65, 0.0)
    prop(B, "vending_red", -13.8, 0.0, -11.4, 0.0)
    prop(B, "bench_oak", -7.0, 0.0, -8.0, 0.0)
    prop(B, "bench_oak", 1.0, 0.0, -8.0, 0.0)
    for (x, z) in ((-24.0, -6.3), (19.0, -6.3), (-16.7, -24.8), (-3.6, -6.1), (6.2, -6.1), (-24.2, -11.3), (19.2, -11.2)):
        prop(B, "plant_lobby", x, 0.0, z, 0.0)
    prop(B, "round_sofa", -19.5, 0.0, -8.9, 0.0)
    prop(B, "low_table", -19.5, 0.0, -8.9, 0.0)
    prop(B, "drum_lamp", -21.4, 0.0, -6.6, 0.0)
    prop(B, "drum_lamp", -17.6, 0.0, -6.6, 0.0)
    prop(B, "armchair_mustard", 16.4, 0.0, -8.6, -PI / 2 - 0.3)
    prop(B, "armchair_mustard", 16.4, 0.0, -6.7, -PI / 2 + 0.3)
    prop(B, "low_table", 16.75, 0.0, -7.65, 0.0)
    for x in (-5.4, -3.8, -2.2, -0.6):
        prop(B, "stanchion", x, 0.0, -21.7, 0.0)
    for k in range(3):
        x0, x1 = -5.4 + k * 1.6, -3.8 + k * 1.6
        B.box(x0, 0.86, -21.705, x1, 0.91, -21.695, "M_epita_blue")
    prop(B, "wall_clock", -6.5, 2.55, -25.85, 0.0)
    prop(B, "extinguisher", 10.42, 0.0, -13.4, -PI / 2)
    prop(B, "extinguisher", -8.6, 0.0, -25.85, 0.0)
    prop(B, "exit_sign", -12.0, 3.0, -5.62, PI)
    prop(B, "exit_sign", 9.3, 3.0, -5.62, PI)
    for x in (-15.5, -12.5):
        prop(B, "desk_office", x, 0.0, -23.0, 0.0)
        prop(B, "office_chair", x, 0.0, -22.3, PI)
    prop(B, "plant_small", -10.8, 0.0, -25.4, 0.0)
    with B.at(4.5, 1.65, -12.16, PI):
        B.quad((-1.5, -1.3, 0.0), (1.5, -1.3, 0.0), (1.5, 1.3, 0.0), (-1.5, 1.3, 0.0), "M_lobby_mural", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    prop(B, "rollup_banner", -7.0, 0.0, -24.9, 0.3)
    prop(B, "rollup_banner", 1.0, 0.0, -24.9, -0.3)
    prop(B, "water_cooler", 8.65, 0.0, -25.6, 0.0)
    prop(B, "wet_floor_sign", 2.5, 0.0, -8.9, 0.4)
    prop(B, "bins_tri", -12.0, 0.0, -11.55, 0.0)
    # 1st floor
    for z in PC_ROWS_Z:
        for (xa, xb) in PC_ROW_X:
            for x in pc_row_xs(xa, xb):
                k = int(abs(x * 7 + z * 3)) % 6
                prop(B, "pc_desk_%d" % k, x, F1, z, 0.0)
                prop(B, "office_chair", x, F1, z + 0.75, PI)
    for (x, z) in ((-15.15, -23.6), (-9.35, -20.6), (-13.7, -17.8), (0.3, -23.6), (3.2, -20.6), (4.65, -17.8)):
        prop(B, "bottle", x + 0.48, F1 + 0.76, z + 0.12, 0.0)
    for (x, z, kind) in ((-16.6, -22.75, "backpack_navy"), (-7.9, -19.75, "backpack_red"), (-1.15, -16.95, "backpack_green"), (6.1, -22.75, "backpack_navy")):
        prop(B, kind, x + 0.35, F1, z + 0.25, 0.4)
    for x in (-10.6, -9.0, -7.4):
        prop(B, "lockers_4", x, F1, -12.4, PI)
    prop(B, "bench_oak", -1.0, F1, -12.55, PI)
    prop(B, "bench_oak", 1.0, F1, -12.55, PI)
    prop(B, "extinguisher", 7.6, F1, -12.15, PI)
    prop(B, "wall_clock", -4.075, F1 + 2.3, -20.5, -PI / 2)
    prop(B, "wall_clock", 7.925, F1 + 2.3, -20.5, -PI / 2)
    prop(B, "exit_sign", 9.3, CEIL1, -15.0, 0.0)
    whiteboard(B, -17.85, F1, -21.0, PI / 2, 3.0, "M_wb_sm14")
    poster(B, "moulinette", -16.2, F1 + 1.6, -15.92, 0.0)
    poster(B, "rush", -15.4, F1 + 1.6, -15.92, 0.0)
    poster(B, "rules", -6.0, F1 + 1.6, -15.92, 0.0)
    poster(B, "acu", 5.2, F1 + 1.6, -15.92, 0.0)
    notice_board(B, -2.4, F1 + 1.5, -12.14, PI, seed=3)
    sign(B, -11.0, F1 + 2.55, -15.92, 0.0, 0.8, 0.3, "M_epita_blue", [("SM14", 0.18, "bold", "M_plate_white")], depth=0.015)
    sign(B, 2.0, F1 + 2.55, -15.92, 0.0, 0.8, 0.3, "M_epita_blue", [("SM15", 0.18, "bold", "M_plate_white")], depth=0.015)
    for (x, z) in ((-15.0, -26.0), (-11.0, -26.0), (-7.0, -26.0), (-2.5, -26.0), (2.0, -26.0), (6.0, -26.0)):
        radiator(B, x, F1 + 0.12, -25.85, 0.0, w=1.8)
    # cable tray along the corridor ceiling
    B.box(-17.5, CEIL1 - 0.25, -13.2, 10.2, CEIL1 - 0.2, -12.9, "M_steel_dark")
    for x in range(-17, 10, 2):
        B.box(x - 0.01, CEIL1 - 0.2, -13.06, x + 0.01, CEIL1, -13.04, "M_steel_dark")
    # rooftop units: on the wing's roof east of the terrace deck, on the box (campus_kb1, roof 22.5 m); wall units on
    # the wing's back over the two yards
    for (x, z, yaw) in ((14.0, -9.0, 0.0), (18.5, -12.4, 0.3)):
        prop(B, "hvac_unit", x, ROOF, z, yaw)
    import campus_kb1
    for (x, z, yaw) in ((-10.0, -22.0, 0.0), (4.0, -24.0, 0.3), (-15.0, -19.5, PI / 2)):
        prop(B, "hvac_unit", x, campus_kb1.BOX1, z, yaw)
    for (x, z) in ((-25.2, -16.15), (18.4, -16.15)):
        prop(B, "ac_wall", x, 5.2, z, PI)
    for (x, z) in ((-12.0, -22.0), (-4.0, -18.0), (6.0, -23.0), (-14.0, -14.5), (8.0, -14.0)):
        prop(B, "plant_small", x, ROOF + 0.06, z, 0.0)


def epita_logo(B, x, y, z, yaw, width):
    """the EPITA mark: four overlapping blue triangles + wordmark (old Decor.epitaLogo), plate-mounted"""
    s = width / 2.5
    with B.at(x, y, z, yaw):
        x0 = -width / 2 + width * 0.06
        y0 = -s * 0.42
        tris = [((0.0, 0.0), (0.6, 0.8), (1.2, 0.0), "M_logo_1"), ((0.3, 0.0), (0.95, 0.68), (1.6, 0.0), "M_logo_2"),
                ((0.8, 0.0), (1.35, 0.56), (1.9, 0.0), "M_logo_3"), ((1.2, 0.0), (1.7, 0.44), (2.2, 0.0), "M_logo_4")]
        for i, (a, b, c, m) in enumerate(tris):
            zz = 0.01 + i * 0.006
            B.face([(x0 + a[0] * s, y0 + a[1] * s, zz), (x0 + c[0] * s, y0 + c[1] * s, zz), (x0 + b[0] * s, y0 + b[1] * s, zz)], m)
        with B.at(x0 + 0.42 * s, y0 + 0.12 * s, 0.04):
            B.text("EPITA", font("bold"), 0.42 * s, "M_light_panel", align="LEFT", valign="BOTTOM", depth=0.02)


def reception(B):
    """accueil counter (old Props.counter(-3, 0, -23.4, 0, 3.6, navy)): visitor ledge at 1.07-1.1, desk behind"""
    x0, x1, zc = -4.8, -1.2, -23.4
    B.box(x0, 0.0, zc - 0.3, x1, 1.05, zc + 0.3, "M_paint_epita")
    B.box(x0 - 0.03, 1.05, zc - 0.32, x1 + 0.03, 1.1, zc + 0.36, "M_laminate_white")
    B.box(x0, 0.0, zc + 0.3, x1, 0.08, zc + 0.31, "M_paint_metal_dark")
    B.box(x0 + 0.1, 0.35, zc + 0.3, x1 - 0.1, 0.4, zc + 0.31, "M_light_panel")
    with B.at((x0 + x1) / 2, 0.62, zc + 0.302):
        B.text("ACCUEIL", font("bold"), 0.16, "M_plate_white", align="CENTER", valign="CENTER")
    B.box(x0, 0.72, zc - 0.95, x1, 0.75, zc - 0.3, "M_laminate_white")
    B.box(x0 + 0.05, 0.0, zc - 0.9, x0 + 0.1, 0.72, zc - 0.35, "M_paint_metal_dark")
    B.box(x1 - 0.1, 0.0, zc - 0.9, x1 - 0.05, 0.72, zc - 0.35, "M_paint_metal_dark")
    for xm in (-4.2, -2.4):
        B.box(xm - 0.25, 0.9, zc - 0.75, xm + 0.25, 1.2, zc - 0.72, "M_plastic_black")
        B.quad((xm + 0.24, 0.915, zc - 0.721), (xm - 0.24, 0.915, zc - 0.721), (xm - 0.24, 1.185, zc - 0.721), (xm + 0.24, 1.185, zc - 0.721),
               "M_screen_1", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        B.box(xm - 0.02, 0.75, zc - 0.76, xm + 0.02, 0.9, zc - 0.73, "M_plastic_black")
    B.cbox(x0 - 0.03, 0.0, zc - 0.32, x1 + 0.03, 1.1, zc + 0.36)
    # lost & found box on the counter (old: x -1.75..-1.25, y 1.1..1.42)
    B.box(-1.75, 1.1, -23.55, -1.25, 1.42, -23.15, "M_cardboard")
    B.box(-1.73, 1.42, -23.53, -1.27, 1.425, -23.17, "M_cardboard")
    with B.at(-1.5, 1.24, -23.148):
        B.box(-0.23, -0.05, 0.0, 0.23, 0.05, 0.002, "M_paper_white")
        B.text("LOST & FOUND", font("black"), 0.045, "M_plastic_black", align="CENTER", valign="CENTER")
    # the note on the desk (spot 'sign')
    B.box(-3.75, 1.1, -23.35, -3.45, 1.102, -23.15, "M_paper_white")
    prop(B, "office_chair", -3.4, 0.0, -24.6, 0.0)


def whiteboard(B, x, y, z, yaw, w, mat):
    with B.at(x, y, z, yaw):
        B.box(-w / 2 - 0.04, 0.96, 0.0, w / 2 + 0.04, 2.24, 0.025, "M_alu_silver")
        B.quad((-w / 2, 1.0, 0.026), (w / 2, 1.0, 0.026), (w / 2, 2.2, 0.026), (-w / 2, 2.2, 0.026), mat, uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        B.box(-w / 2, 0.93, 0.0, w / 2, 0.96, 0.08, "M_alu_silver")
        for k, m in enumerate(("M_plastic_blue", "M_plastic_red", "M_plastic_black")):
            B.box(-w / 2 + 0.25 + k * 0.15, 0.96, 0.035, -w / 2 + 0.37 + k * 0.15, 0.98, 0.055, m)


# ------------------------------------------------------------------ Amphi 4
def amphi(B):
    B.use("amphi_dress")
    B.use_col("COL_amphi")
    for k in range(1, TIERS + 1):
        z0, z1, top = tier_z(k)
        zc = (z0 + z1) / 2
        prop(B, "amphi_row_l", 14.1, top, zc + 0.05, PI)
        prop(B, "amphi_row_r", 23.45, top, zc + 0.05, PI)
        if k >= 2:
            for x in (11.2, 13.5, 16.4, 21.4, 24.1, 26.3):
                if (k * 7 + round(x * 3)) % 3 == 0:
                    prop(B, "laptop", x, top + 0.78, zc - 0.17, 0.0)
            if k % 2:
                prop(B, "backpack_navy" if k % 3 else "backpack_red", 12.3 if k % 4 == 1 else 25.2, top, zc + 0.45, 0.3)
    prop(B, "lectern", 21.6, AY, 8.5, 0.0)
    # stage desk + PC (old Props.desk(16.5, AY, 8.3, w 2.2) + Props.pc)
    B.box(15.4, AY + 0.72, 7.9, 17.6, AY + 0.76, 8.7, "M_wood_oak")
    B.box(15.4, AY, 8.62, 17.6, AY + 0.72, 8.7, "M_wood_oak")
    for sx in (15.45, 17.55):
        B.box(sx - 0.03, AY, 7.95, sx + 0.03, AY + 0.72, 8.65, "M_wood_oak")
    B.box(16.22, AY + 0.88, 8.36, 16.78, AY + 1.22, 8.39, "M_plastic_black")
    B.quad((16.235, AY + 0.895, 8.359), (16.765, AY + 0.895, 8.359), (16.765, AY + 1.205, 8.359), (16.235, AY + 1.205, 8.359), "M_screen_1",
           uvs=[(0, 0), (1, 0), (1, 1), (0, 1)], flip=True)
    B.box(16.47, AY + 0.76, 8.37, 16.53, AY + 0.88, 8.4, "M_plastic_black")
    B.cbox(15.4, AY, 7.9, 17.6, AY + 0.76, 8.7)
    # projected slide, screen frame, projector, whiteboards, AMPHI 4 sign
    B.box(15.5, 0.0, 6.1, 22.0, 3.9, 6.115, "M_plate_white")
    B.quad((15.55, 0.1, 6.116), (21.95, 0.1, 6.116), (21.95, 3.7, 6.116), (15.55, 3.7, 6.116), "M_slide", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.box(15.4, 3.9, 6.1, 22.1, 4.05, 6.3, "M_paint_metal_dark")
    B.box(18.4, 4.75, 13.0, 19.1, 4.95, 13.6, "M_plastic_white")
    B.box(18.7, 4.95, 13.25, 18.8, 5.3, 13.35, "M_steel_dark")
    B.cyl_axis((18.75, 4.85, 12.99), (18.75, 4.85, 12.95), 0.06, "M_room_sleeve", seg=12)
    whiteboard(B, 12.2, AY, 6.1, 0.0, 3.2, "M_wb_amphi_a")
    whiteboard(B, 25.3, AY, 6.1, 0.0, 3.2, "M_wb_amphi_b")
    sign(B, 16.0, 3.4, 18.735, 0.0, 2.0, 0.5, "M_epita_blue", [("AMPHI 4", 0.3, "bold", "M_plate_white")], depth=0.04)
    prop(B, "extinguisher", 13.0, 0.0, 18.2, PI)
    prop(B, "exit_sign", 16.0, 2.75, 18.18, PI)
    prop(B, "wall_clock", 9.65, 3.3, 12.0, PI / 2)


# ------------------------------------------------------------------ cafeteria
def cafeteria(B):
    B.use("cafe_dress")
    B.use_col("COL_cafe")
    yw = SE_YAW
    for (lx, lz) in ((3, 3), (3, 6), (7.5, 3), (7.5, 6), (12, 3)):
        x, z = cafe_pt(lx, lz)
        prop(B, "cafe_table", x, 0.02, z, yw)
        for s in (-1, 1):
            a = cafe_pt(lx + s * 0.5, lz + 0.65)
            b = cafe_pt(lx + s * 0.5, lz - 0.65)
            prop(B, "stool_red", a[0], 0.02, a[1], 0.0)
            prop(B, "stool_blue", b[0], 0.02, b[1], 0.0)
    for lx, kind in ((1.6, "vending_red"), (2.7, "vending_blue")):
        x, z = cafe_pt(lx, 8.6)
        prop(B, kind, x, 0.02, z, yw + PI)
    x, z = cafe_pt(12.6, 8.55)
    prop(B, "coffee_machine", x, 0.02, z, yw + PI)
    for (lx, lz, kind) in ((0.8, 8.4, "plant_small"), (15.2, 1.0, "plant_small")):
        x, z = cafe_pt(lx, lz)
        prop(B, kind, x, 0.02, z, 0.0)
    x, z = cafe_pt(9.7, 0.35)
    prop(B, "bins_tri", x, 0.02, z, yw)
    with B.frame(Xf.at(SE0[0], 0, SE0[1], yw)):
        # serving counter (old Props.counter at local (15.3, 5.2), yaw -pi/2, w 5): top at 1.095
        cx = 15.3
        B.box(cx - 0.3, 0.02, 2.7, cx + 0.3, 1.05, 7.7, "M_paint_metal_dark")
        B.box(cx - 0.36, 1.05, 2.67, cx + 0.33, 1.095, 7.73, "M_laminate_white")
        B.box(cx - 0.31, 0.12, 2.75, cx - 0.3, 0.9, 7.65, "M_wood_oak")
        B.box(cx - 0.5, 0.95, 3.0, cx - 0.36, 0.98, 7.4, "M_steel")
        for k in range(4):
            B.box(cx - 0.25, 1.095, 3.2 + k * 1.1, cx + 0.2, 1.4, 3.9 + k * 1.1, "M_glass_clear")
        B.cbox(cx - 0.36, 0.0, 2.67, cx + 0.33, 1.095, 7.73)
        # microwave counter along the west end (old More.microwaves at local (0.65, 5.2), 6 units)
        B.box(0.35, 0.02, 3.24, 0.95, 0.9, 7.16, "M_laminate_grey")
        B.box(0.33, 0.9, 3.22, 0.97, 0.93, 7.18, "M_laminate_white")
        B.cbox(0.3, 0.0, 3.2, 0.97, 1.3, 7.2)
        # signs + posters
        with B.at(7.5, 2.55, 9.19, PI):
            panel_text(B, [("CAFETERIA", 0.3, "bold", "M_plastic_black"), ("plat du jour : pates (encore)", 0.11, "semi", "M_plastic_black")],
                       3.0, 0.75, "M_epita_lime", depth=0.03)
        with B.at(8.0, 3.25, -0.27, PI):
            panel_text(B, [("CAFETERIA", 0.2, "bold", "M_plate_white")], 2.2, 0.4, "M_epita_blue", depth=0.04)
        poster(B, "menu", 4.6, 1.7, 9.19, PI)
        poster(B, "microondes", 10.4, 1.7, 9.19, PI)
        with B.at(5.8, 0.02, 1.1, PI * 0.9):
            B.box(-0.3, 0.0, -0.25, -0.28, 1.4, -0.23, "M_wood_dark")
            B.box(0.28, 0.0, -0.25, 0.3, 1.4, -0.23, "M_wood_dark")
            B.box(-0.3, 0.6, -0.26, 0.3, 1.38, -0.22, "M_wood_dark")
            B.quad((-0.27, 0.63, -0.219), (0.27, 0.63, -0.219), (0.27, 1.35, -0.219), (-0.27, 1.35, -0.219), "M_menu_board",
                   uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    for k in range(6):
        x, z = cafe_pt(0.65, 3.55 + k * 0.62)
        prop(B, "microwave", x, 0.93, z, yw + PI / 2)
    x, z = cafe_pt(14.2, 8.75)
    prop(B, "fridge_drinks", x, 0.02, z, yw + PI)
    x, z = cafe_pt(15.25, 3.4)
    prop(B, "cash_register", x, 1.095, z, yw + PI / 2)
    x, z = cafe_pt(15.2, 7.45)
    prop(B, "tray_stack", x, 1.095, z, yw)
    for (lx, lz) in ((3, 3), (3, 6), (7.5, 3), (7.5, 6), (12, 3)):
        x, z = cafe_pt(lx, lz)
        prop(B, "court_pendant", x, FLOOR - 0.35 + 0.35, z, 0.0)
    with B.frame(Xf.at(SE0[0], 0, SE0[1], yw)):
        with B.at(15.99, 2.3, 5.2, -PI / 2):
            B.quad((-2.4, -0.75, 0.0), (2.4, -0.75, 0.0), (2.4, 0.75, 0.0), (-2.4, 0.75, 0.0), "M_cafe_mural", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])


# ------------------------------------------------------------------ cour Pasteur
def courtyard(B):
    B.use("court_dress", cast=False)
    # old positions (8.5,23) (14,33) (-3,33.5) (20.5,22): nudged so the looping NPC / crowd paths clear them
    for (x, z, r) in ((10.5, 23.0, 0.0), (14.0, 31.3, 0.0), (-3.0, 33.5, 0.5), (21.0, 21.6, PI / 2)):
        prop(B, "planter_birch", x, 0.0, z, r)
    # (6,27) stays: Ian and Silvia stand at its ends; (18,30.5) and (3,22.5) moved off the walker lines
    for (x, z, r) in ((6.0, 27.0, 0.0), (12.5, 28.5, 0.3), (17.2, 30.0, 0.0), (5.3, 22.2, -0.2)):
        prop(B, "picnic_table", x, 0.0, z, r)
    # catenaries with string lights, pendants on three of them (LIGHT_court_* at the pendant bulbs)
    ne = lambda t: (NE0[0] + (NE1[0] - NE0[0]) * t + NE_NX * 0.05, NE0[1] + (NE1[1] - NE0[1]) * t + NE_NZ * 0.05)
    se = lambda t: PG.along(SE_FACE[1], SE_FACE[0], 1.0 - t, 0.05)
    east = lambda a, b, t: PG.along(a, b, t, 0.05)      # on an EAST_24 / SOUTH_W edge, listed clockwise
    cables = [
        ((*ne(0.22),), east((10.5, 18.6), (25.8, 18.9), 0.196), 5.0, 1.1, [("court_a", 4.0)]),
        ((*ne(0.75),), east((25.8, 18.9), (33.2, 26.6), 0.25), 5.6, 1.3, [("court_b", 16.0)]),
        ((*se(0.5),), east((33.2, 26.6), (33.0, 38.3), 0.29), 5.8, 1.4, [("court_c", 6.0), ("court_d", 24.0)]),
        ((*ne(0.5),), east((20.2, 41.4), (10.0, 41.1), 0.95), 6.2, 1.5, []),
        (PG.along((-12.3, 24.9), (-0.2, 13.9), 0.97, 0.05), east((10.5, 18.6), (25.8, 18.9), 0.752), 4.8, 0.6, []),
    ]
    for (a, b, y, sag, pendants) in cables:
        pa, pb = (a[0], y, a[1]), (b[0], y, b[1])
        string_lights(B, pa, pb, sag=sag * 0.45)
        for (name, xp) in pendants:
            t = (xp - a[0]) / (b[0] - a[0])
            p = hang_points(pa, pb, sag * 0.45, [t])[0]
            prop(B, "court_pendant", p.x, p.y - 0.05, p.z, 0.0)
            light(B, name, p.x, p.y - 1.3, p.z, K(2700), 1.7, 12.0, shadow=True)
        for p in (pa, pb):
            B.box(p[0] - 0.05, p[1] - 0.05, p[2] - 0.05, p[0] + 0.05, p[1] + 0.05, p[2] + 0.05, "M_steel_dark")
    prop(B, "bin_paris", 9.65, 0.0, 19.25, 0.0)
    prop(B, "bin_paris", -6.5, 0.0, 30.5, 0.0)
    for x in (24.0, 25.0, 26.0):
        prop(B, "bike_rack", x, 0.0, 35.2, 0.0)
    # wall lights on the Amphi 4 front, between the fins
    for t in (0.114, 0.595):
        x, z = PG.along((10.5, 18.6), (25.8, 18.9), t)
        with B.at(x, 3.2, z, PG.yaw_out((10.5, 18.6), (25.8, 18.9))):
            B.box(-0.15, -0.08, 0.0, 0.15, 0.08, 0.12, "M_paint_metal_dark")
            B.box(-0.12, -0.081, 0.01, 0.12, -0.08, 0.1, "M_light_warm")
    # THE UNDER sign over the ramp, on the south building's courtyard face (the south side stands back at z 41.4)
    x, z = PG.along((30.5, 41.7), (20.2, 41.4), 0.777, 0.015)
    with B.at(x, 4.55, z, PI):
        panel_text(B, [("THE UNDER", 0.32, "black", "M_neon_lime"), ("BDE  -  associations", 0.11, "semi", "M_neon_lime")], 2.6, 0.7,
                   "M_plastic_black", depth=0.05)
    light(B, "under_sign", x, 4.2, z - 0.9, "#b8ff2a", 0.9, 5.0)
    # the passage fascia, lit from below the roof edge (the old "EPITA" plate is gone: the real one is the blue fascia)
    light(B, "passage_sign", 3.35, 4.0, 6.3, K(3500), 0.8, 5.0)
    # Paritalie roof units (off the penthouse on the octagonal core)
    for (x, z, yaw) in ((-17.0, 26.0, 0.4), (-12.0, 40.0, -0.9), (-31.0, 31.5, 0.0), (-40.0, 16.0, 0.8)):
        prop(B, "hvac_unit", x, X_H, z, yaw)


# ------------------------------------------------------------------ the Under
def under(B):
    B.use("under_dress")
    B.use_col("COL_under")
    prop(B, "sofa_navy", 4.2, UY, 42.5, PI / 2)
    prop(B, "armchair_mustard", 6.6, UY, 41.4, -2.4)
    prop(B, "armchair_mustard", 6.9, UY, 43.8, -0.8)
    prop(B, "babyfoot", 15.0, UY, 46.0, 0.0)
    prop(B, "blue_table", 7.0, UY, 49.5, 0.0)
    prop(B, "blue_table", 21.5, UY, 49.5, 0.0)
    for x in (5.8, 7.0, 8.2, 20.3, 21.5, 22.7):
        prop(B, "office_chair", x, UY, 48.5, 0.0)
        prop(B, "office_chair", x, UY, 50.5, PI)
    prop(B, "shelf_unit", 12.0, UY, 51.7, PI)
    prop(B, "shelf_unit", 16.5, UY, 51.7, PI)
    prop(B, "arcade", 27.35, UY, 50.9, -PI / 2)
    for (x, z, kind) in ((3.6, 45.4, "beanbag_red"), (4.8, 46.4, "beanbag_blue"), (3.5, 47.4, "beanbag_lime")):
        prop(B, kind, x, UY, z, 0.0)
    prop(B, "low_table", 5.6, UY, 42.6, 0.0)
    for x in (25.0,):
        for z in (43.2, 44.5, 45.8):
            prop(B, "stool_red", x - 0.05, UY, z, 0.0)
    prop(B, "extinguisher", 2.0, UY, 41.0, PI / 2)
    prop(B, "exit_sign", 27.0, UY + 2.65, 39.5, 0.0)
    prop(B, "bins_tri", 3.0, UY, 50.9, PI / 2)
    # bar counter (old Props.counter(25.8, UY, 44.5, -pi/2, 4, black))
    with B.at(25.8, UY, 44.5, -PI / 2):
        B.box(-2.0, 0.0, -0.3, 2.0, 1.05, 0.3, "M_plastic_black")
        B.box(-2.03, 1.05, -0.32, 2.03, 1.1, 0.36, "M_wood_oak")
        B.box(-1.95, 0.1, 0.3, 1.95, 0.13, 0.31, "M_neon_pink")
        B.box(-1.9, 1.1, -0.25, -1.6, 1.4, 0.05, "M_plastic_red")
        B.cbox(-2.03, 0.0, -0.32, 2.03, 1.1, 0.36)
    # sticker wraps on the two columns
    for (cx, cz) in ((9.0, 45.5), (21.0, 45.5)):
        h0, h1 = UY + 0.05, -0.35
        for (nx, nz) in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            with B.at(cx + nx * 0.302, 0.0, cz + nz * 0.302, math.atan2(nx, nz)):
                B.quad((-0.3, h0, 0.0), (0.3, h0, 0.0), (0.3, h1, 0.0), (-0.3, h1, 0.0), "M_stickers",
                       uvs=[(0, 0), (1, 0), (1, (h1 - h0) / 0.6 * 0.5), (0, (h1 - h0) / 0.6 * 0.5)])
    # neon + signs + posters
    with B.at(15.0, UY + 2.55, 51.99, PI):
        B.box(-1.25, -0.32, -0.03, 1.25, 0.32, 0.0, "M_plastic_black")
        with B.at(0, -0.1, 0.004):
            B.text("BDE EPITA", font("black"), 0.36, "M_neon_pink", align="CENTER", valign="BOTTOM", depth=0.02)
    light(B, "under_neon_bde", 15.0, UY + 2.3, 51.2, "#ff4fb0", 1.2, 6.0)
    for (z0, z1, y, m) in ((41.0, 50.5, UY + 2.9, "M_neon_blue"),):
        B.box(2.0, y, z0, 2.03, y + 0.03, z1, m)
    B.box(27.97, UY + 2.9, 40.5, 28.0, UY + 2.93, 51.5, "M_neon_lime")
    poster(B, "soiree", 27.84, UY + 1.6, 42.0, -PI / 2)
    poster(B, "ctf", 2.16, UY + 1.6, 45.0, PI / 2)
    poster(B, "gamejam", 2.16, UY + 1.6, 46.0, PI / 2)
    poster(B, "concert", 2.16, UY + 1.6, 47.2, PI / 2)
    poster(B, "bde_asso", 27.84, UY + 1.6, 46.6, -PI / 2)
    notice_board(B, 5.0, UY + 1.5, 39.52, 0.0, seed=7)
    with B.at(18.0, UY + 1.75, 39.51, 0.0):
        B.quad((-4.0, -1.15, 0.0), (4.0, -1.15, 0.0), (4.0, 1.15, 0.0), (-4.0, 1.15, 0.0), "M_under_mural", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    prop(B, "tv_unit", 8.4, UY, 42.6, -PI / 2)
    light(B, "under_mural", 18.0, -0.7, 41.0, "#c9a6ff", 0.9, 7.0)
    string_lights(B, (3.0, -0.6, 40.5), (27.0, -0.6, 40.5), sag=0.25, mat="M_light_string")
    string_lights(B, (3.0, -0.6, 51.0), (27.0, -0.6, 51.0), sag=0.25, mat="M_neon_pink")
    # cable trays + conduits on the ceiling
    for x in (4.0, 26.0):
        B.box(x - 0.15, -0.42, 39.8, x + 0.15, -0.38, 51.7, "M_steel_dark")


# ------------------------------------------------------------------ Paritalie and 24 rue Pasteur, street side
def round_sign(B, x, y, z, yaw, text, r=0.27):
    """red-ringed round sign plate (the "4m" height limit), front +Z"""
    n = 24
    with B.at(x, y, z, yaw):
        B.cyl_axis((0, 0, -0.015), (0, 0, 0.0), r + 0.012, "M_zinc", seg=n)
        for rr, mat, zz in ((r, "M_sign_red", 0.001), (r * 0.78, "M_plate_white", 0.002)):
            B.face([(math.cos(2 * PI * i / n) * rr, math.sin(2 * PI * i / n) * rr, zz) for i in range(n)], mat)
        with B.at(0.0, -0.075, 0.003):
            B.text(text, font("black"), 0.16, "M_plastic_black", align="CENTER", valign="BOTTOM")


def assembly_sign(B, x, y, z, yaw, s=0.42):
    """ISO 7010 evacuation assembly point (green square, four arrows and figures), front +Z"""
    h = s / 2
    with B.at(x, y, z, yaw):
        B.box(-h, -h, -0.012, h, h, 0.0, "M_sign_green")
        w = 0.022
        for (a, b, c, d) in ((-h * 0.62, h * 0.62 - w, h * 0.62, h * 0.62), (-h * 0.62, -h * 0.62, h * 0.62, -h * 0.62 + w),
                             (-h * 0.62, -h * 0.62, -h * 0.62 + w, h * 0.62), (h * 0.62 - w, -h * 0.62, h * 0.62, h * 0.62)):
            B.box(a, b, 0.0, c, d, 0.002, "M_plate_white")
        for sx in (-1, 1):
            for sy in (-1, 1):
                tip = (sx * h * 0.68, sy * h * 0.68)
                base = (sx * h * 0.9, sy * h * 0.9)
                side = (-sy * 0.05, sx * 0.05)
                pts = [(tip[0], tip[1], 0.003), (base[0] + side[0], base[1] + side[1], 0.003), (base[0] - side[0], base[1] - side[1], 0.003)]
                if (pts[1][0] - pts[0][0]) * (pts[2][1] - pts[0][1]) - (pts[1][1] - pts[0][1]) * (pts[2][0] - pts[0][0]) < 0:
                    pts = pts[::-1]
                B.face(pts, "M_plate_white")
        for k in range(4):
            fx = -0.09 + k * 0.06
            B.cyl_axis((fx, 0.035, 0.0), (fx, 0.035, 0.004), 0.016, "M_plate_white", seg=10)
            B.box(fx - 0.014, -0.06, 0.0, fx + 0.014, 0.012, 0.004, "M_plate_white")


def network_graphic(B, w, h, seed):
    """white nodes and links on a banner (local XY plane, front +Z): the network graphic of the passage's west pier"""
    rng = random.Random(seed)
    nodes = [(-w / 2 + w * (i + 0.5) / 3 + rng.uniform(-0.2, 0.2), -h / 2 + h * (j + 0.5) / 4 + rng.uniform(-0.22, 0.22))
             for i in range(3) for j in range(4) if (i, j) != (1, 2)]
    seen = set()
    for i, p in enumerate(nodes):
        for j in sorted(range(len(nodes)), key=lambda j: (nodes[j][0] - p[0]) ** 2 + (nodes[j][1] - p[1]) ** 2)[1:3]:
            if (min(i, j), max(i, j)) in seen:
                continue
            seen.add((min(i, j), max(i, j)))
            q = nodes[j]
            L = math.hypot(q[0] - p[0], q[1] - p[1])
            nx, ny = -(q[1] - p[1]) / L * 0.012, (q[0] - p[0]) / L * 0.012
            B.quad((p[0] - nx, p[1] - ny, 0.003), (q[0] - nx, q[1] - ny, 0.003), (q[0] + nx, q[1] + ny, 0.003),
                   (p[0] + nx, p[1] + ny, 0.003), "M_plate_white")
    for k, (px, py) in enumerate(nodes):
        r = rng.uniform(0.06, 0.12)
        B.cyl_axis((px, py, 0.0), (px, py, 0.006), r, "M_plate_white", seg=14)
        if k % 3 == 0:
            B.cyl_axis((px, py, 0.0), (px, py, 0.008), r * 0.55, "M_fascia_blue", seg=12)


def south_side(B):
    """the street side of Paritalie and 24 rue Pasteur: the V forecourt's trees, the pharmacy, the passage's
    banners and signs, and the east building's roof garden. Generic lettering only: the {EPITECH} fascia stays blank
    and no EPITA, Epitech or IONIS logo is used."""
    B.use("south_dress")
    B.use_col("COL_buildings")
    # big trees in the V between the wing ends, crowns leaning to the street
    for (x, z) in ((-16.5, 8.0), (-23.5, 8.4), (-30.5, 8.0), (-20.0, 12.0), (-27.0, 12.0)):
        prop(B, "tree_plane", x, 0.1, z, PI)
    # the pharmacy in the NW wing end: sign band and a green cross square to the street
    xf, L = wall_frame(-38.7, 4.9, -45.2, 4.9)
    with B.frame(xf):
        B.box(0.3, 3.0, 0.0, L - 0.3, 3.5, 0.12, "M_paint_metal_green")
        with B.at(L / 2, 3.07, 0.122):
            B.text("PHARMACIE", font("bold"), 0.3, "M_plate_white", align="CENTER", maxw=L - 1.2)
        with B.at(L - 0.45, 4.4, 0.0):
            B.box(-0.03, -0.02, 0.0, 0.03, 0.02, 0.2, "M_paint_metal_dark")
            B.box(-0.035, -0.3, 0.38, 0.035, 0.3, 0.58, "M_led_green")
            B.box(-0.035, -0.1, 0.18, 0.035, 0.1, 0.78, "M_led_green")
    light(B, "pharmacie", -44.75, 4.4, 4.0, "#4cff7a", 0.5, 3.5)
    # the passage at no. 24: banners on both piers, the "4m" signs, the assembly point, "24"
    for (a, b), side in ((((0.0, 7.1), (-1.7, 5.0)), "w"), (((9.2, 5.0), (6.7, 7.4)), "e")):
        xf, L = wall_frame(a[0], a[1], b[0], b[1])
        with B.frame(xf):
            with B.at(L / 2, 4.55, 0.04):
                B.box(-1.0, -1.5, -0.03, 1.0, 1.5, 0.0, "M_fascia_blue")
                B.box(-1.04, 1.5, -0.04, 1.04, 1.55, 0.01, "M_steel_dark")
                if side == "w":
                    network_graphic(B, 2.0, 3.0, 24)
                else:
                    with B.at(0.0, 0.62, 0.0):
                        panel_text(B, [("KB", 0.62, "bold", "M_plate_white"), ("2,3,4", 0.4, "bold", "M_plate_white")], 2.0, 1.4, None)
                    with B.at(0.0, -0.75, 0.0):
                        panel_text(B, [("CAMPUS", 0.12, "sign", "M_plate_white"), ("KREMLIN-BICÊTRE", 0.12, "sign", "M_plate_white"),
                                       ("COUR PASTEUR", 0.15, "sign", "M_plate_white")], 2.0, 0.8, None)
            round_sign(B, L / 2 - (0.35 if side == "e" else 0.0), 2.6, 0.03, 0.0, "4m")
            if side == "e":
                assembly_sign(B, L / 2 + 0.45, 2.6, 0.03, 0.0)
    xf, L = wall_frame(40.8, 5.0, 9.2, 5.0)
    with B.frame(xf):
        with B.at(L - 0.9, 2.55, 0.0):
            B.box(-0.17, -0.13, 0.0, 0.17, 0.13, 0.015, "M_signal_blue")
            B.box(-0.15, -0.11, 0.015, 0.15, 0.11, 0.017, "M_plate_white")
            B.box(-0.14, -0.1, 0.017, 0.14, 0.1, 0.019, "M_signal_blue")
            with B.at(0.0, 0.0, 0.02):
                B.text("24", font("cond"), 0.16, "M_plate_white", align="CENTER", valign="CENTER")
    # inside the passage: a ventilation grille and a grey cabinet on the east wall
    xf, L = wall_frame(6.7, 7.4, 6.5, 14.3)
    with B.frame(xf):
        B.box(2.2, 2.6, 0.0, 3.0, 3.1, 0.03, "M_paint_metal_dark")
        for k in range(6):
            B.box(2.25, 2.65 + k * 0.075, 0.03, 2.95, 2.68 + k * 0.075, 0.045, "M_steel")
    x, z = PG.along((6.7, 7.4), (6.5, 14.3), 0.8, 0.22)
    prop(B, "utility_cabinet", x, 0.0, z, PG.yaw_out((6.7, 7.4), (6.5, 14.3)))
    # the east building's roof garden: a few planters with small trees behind the parapet (the
    # shrubs are leaf cards in amphi_ext, one surface for the whole roof)
    for (x, z, r) in ((14.0, 6.6, 0.0), (30.0, 6.6, 0.0), (12.0, 17.6, 0.0), (36.0, 31.0, PI / 2)):
        prop(B, "planter_birch", x, 6.4, z, r)


def build(B):
    street(B)
    voltaire(B)
    amphi(B)
    cafeteria(B)
    courtyard(B)
    south_side(B)
    under(B)
