"""Batiment Voltaire (KB1), inside: the lobby (accueil, lost & found, international office), the stairs to the 1st floor
corridor and the SM14 / SM15 computer rooms. The shell, the roofs, the 2016-18 box and the rue Voltaire side are
campus_kb1 (the real outlines, docs/DESIGN.md §8.3). The lobby fills the rue Pasteur wing (x -29.0..22.1, z -5.3..-15.85)
and the old north part (x -17.85..12.85 to z -25.85), with the entrance hall to the rue Voltaire doors behind it;
SM14 / SM15 run back to the rue Voltaire face (z -31.35)."""
import math
import campus_arch as A
from campus_arch import Opening, wall_frame
from campus_street import card_rect
from campus_layout import *
from campus_mat import K, mat as defmat

# KB1's corridor kit: blue tube handrails; the navy dado is M_paint_epita
defmat("M_paint_rail_blue", None, color="#2b66b0", rough=0.35, metal=0.2, grime="none", macro=0.02)

CEIL0 = FLOOR - 0.35       # GF suspended ceiling (3.25)
CEIL1 = F1 + FLOOR - 0.35  # 1F suspended ceiling (6.85)
ROOF = 11.25
PARA = 11.85
WALL_IN = "M_paint_white"
SKIRT = ("M_paint_metal_dark", 0.08)


def fac(B, ax, az, bx, bz, y0, y1, t, mo, mi, ops=(), **kw):
    xf, L = wall_frame(ax, az, bx, bz)
    with B.frame(xf):
        A.wall(B, L, y0, y1, t, mo, mi, ops, **kw)
    return L


def win(u, w, y0, y1, **o):
    o.setdefault("frame", "M_alu_anthracite")
    return Opening(u - w / 2, u + w / 2, y0, y1, "window", **o)


def ext_win(u, w, y0, y1, seed, lit=0.45, kind=None, **o):
    """window of a room nobody enters: an interior-mapped pane (scripts/fx/interior.gdshader) of `kind` (office;
    flat behind white PVC frames), lit at night with chance `lit`; an explicit card= keeps the old flat card"""
    o.setdefault("frame", "M_alu_anthracite")
    if "card" not in o:
        kind = kind or ("flat" if o["frame"] == "M_pvc_white" else "office")
        o.setdefault("interior", ("M_window_" + kind, seed, lit))
    o.setdefault("blind", None)
    return Opening(u - w / 2, u + w / 2, y0, y1, "window", **o)


def light(B, name, x, y, z, color="#ffe2c0", energy=1.5, rng=9.0, shadow=False, kind="omni", look=None, angle=None):
    ex = {"type": kind, "color": color, "energy": float(energy), "range": float(rng), "shadow": bool(shadow)}
    if angle is not None:
        ex["angle"] = float(angle)
    B.marker("LIGHT_" + name, (x, y, z), 0.0, ex, display="SPHERE" if kind == "omni" else "CONE", size=0.15, look=look)


def ceiling(B, x0, x1, z0, z1, y, mat="M_ceiling_tiles"):
    """suspended ceiling facing down"""
    B.rect((x0, y, z0), (x1 - x0, 0, 0), (0, 0, z1 - z0), mat, sub=3.0)


def panel(B, cx, cz, y, w=0.6, d=0.6, mat="M_light_panel"):
    """recessed LED panel: emissive face + thin frame, just under the ceiling"""
    B.rect((cx - w / 2, y - 0.006, cz - d / 2), (w, 0, 0), (0, 0, d), mat)
    B.box(cx - w / 2 - 0.02, y - 0.012, cz - d / 2 - 0.02, cx + w / 2 + 0.02, y, cz - d / 2, "M_paint_metal_white", skip="t")
    B.box(cx - w / 2 - 0.02, y - 0.012, cz + d / 2, cx + w / 2 + 0.02, y, cz + d / 2 + 0.02, "M_paint_metal_white", skip="t")
    B.box(cx - w / 2 - 0.02, y - 0.012, cz - d / 2, cx - w / 2, y, cz + d / 2, "M_paint_metal_white", skip="t")
    B.box(cx + w / 2, y - 0.012, cz - d / 2, cx + w / 2 + 0.02, y, cz + d / 2, "M_paint_metal_white", skip="t")


def build(B):
    ground_floor(B)
    stairs(B)
    first_floor(B)


# ------------------------------------------------------------------ ground floor (lobby)
def ground_floor(B):
    B.use("volt_gf")
    B.use_col("COL_voltaire")
    with B.ground_at(0.0):
        # terrazzo floor: the wing, the old north part, the entrance hall and its bay (campus_kb1 HALL, BAYS_N)
        B.box(-29.0, -0.3, -15.85, 22.1, 0.0, -5.3, "M_terrazzo", skip="nsewb", sub=3.0)
        B.box(-18, -0.3, -26.15, 13, 0.0, -15.85, "M_terrazzo", skip="nsewb", sub=3.0)
        B.box(-6.75, -0.3, -31.65, 0.4, 0.0, -26.15, "M_terrazzo", skip="nsewb", sub=3.0)
        B.box(-4.9, -0.3, -32.65, -1.7, 0.0, -31.65, "M_terrazzo", skip="nsewb", sub=3.0)
        # entrance mats behind the west door and the KB1 portal
        for x in (-13.45, 9.3):
            B.box(x - 1.3, 0.0, -7.3, x + 1.3, 0.012, -5.3, "M_rubber_floor", skip="b")
        B.box(-4.6, 0.0, -32.6, -2.0, 0.012, -31.0, "M_rubber_floor", skip="b")
    B.cbox(-29.0, -0.5, -15.85, 22.1, 0.0, -5.3)
    B.cbox(-18, -0.5, -26.15, 13, 0.0, -15.85)
    B.cbox(-6.75, -0.5, -31.65, 0.4, 0.0, -26.15)
    B.cbox(-4.9, -0.5, -32.65, -1.7, 0.0, -31.65)
    # suspended ceilings + LED panels (0.6 m grid aligned on x, z = 0); the stair rises through the wing's back
    B.use("volt_gf_ceiling", cast=False)
    ceiling(B, -29.0, 10.42, -15.85, -5.3, CEIL0)
    ceiling(B, 10.42, 13.15, -11.85, -5.3, CEIL0)
    ceiling(B, 13.15, 22.1, -15.85, -5.3, CEIL0)
    ceiling(B, -17.85, 10.55, -25.85, -15.85, CEIL0)
    ceiling(B, 10.55, 12.85, -25.85, -19.1, CEIL0)
    ceiling(B, -6.75, 0.4, -31.5, -26.15, CEIL0)
    ceiling(B, -4.9, -1.7, -32.65, -31.5, CEIL0)
    for x in [-26.1 + 3.6 * k for k in range(14)]:
        for z in (-7.5, -10.2, -13.5):
            if 9.6 < x < 13.6 and z < -12.0:
                continue
            panel(B, round(x / 0.6) * 0.6 + 0.3, round(z / 0.6) * 0.6 + 0.3, CEIL0)
    for x in [-15.9 + 3.6 * k for k in range(8)]:
        for z in (-17.7, -21.3, -24.3):
            if x > 10.0:
                continue
            panel(B, round(x / 0.6) * 0.6 + 0.3, round(z / 0.6) * 0.6 + 0.3, CEIL0)
    for (x, z) in ((-4.5, -28.2), (-1.5, -28.2), (-4.5, -30.6), (-1.5, -30.6)):
        panel(B, round(x / 0.6) * 0.6 + 0.3, round(z / 0.6) * 0.6 + 0.3, CEIL0)
    B.cbox(-29.0, CEIL0, -15.85, 10.42, F1, -5.3)
    B.cbox(10.42, CEIL0, -11.85, 13.15, F1, -5.3)
    B.cbox(13.15, CEIL0, -15.85, 22.1, F1, -5.3)
    B.cbox(-6.75, CEIL0, -32.65, 0.4, F1, -26.15)
    # lights (LIGHT_ markers): the main fixtures, 4 of them with shadows
    for i, (x, z) in enumerate(((-18, -8.5), (-8, -8.5), (2, -8.5), (12, -8.5), (-12, -21), (-3, -21), (5, -16), (-14, -14.5), (16.5, -8.5),
                                (-25.5, -11.5), (18.5, -13.0), (-2.8, -29.6))):
        light(B, "lobby_%02d" % i, x, CEIL0 - 0.15, z, K(4000), 1.6, 9.5, shadow=i in (1, 2, 5, 6))
    light(B, "lobby_lamp", -19.5, 2.2, -7.6, K(3000), 0.9, 6.0)

    B.use("volt_gf")
    # structural columns on the old z=-12 line, lockers backing wall, EPITA feature wall
    for x in (-9.5, -1.5, 7.5):
        B.box(x - 0.25, 0.0, -12.25, x + 0.25, CEIL0, -11.75, "M_paint_white", skip="tb")
        B.box(x - 0.26, 0.0, -12.26, x + 0.26, 0.1, -11.74, "M_paint_metal_dark", skip="tb")
        B.cbox(x - 0.25, 0.0, -12.25, x + 0.25, CEIL0, -11.75)
    B.box(2.8, 0.0, -12.15, 6.2, CEIL0, -11.9, "M_paint_warm", skip="tb")
    B.cbox(2.8, 0.0, -12.15, 6.2, CEIL0, -11.9)
    B.box(-24.7, 0.0, -11.85, -16.5, CEIL0, -11.7, "M_paint_epita", skip="tb", mats={"e": "M_paint_epita"})
    B.cbox(-24.7, 0.0, -11.85, -16.5, CEIL0, -11.7)
    # behind the vending machine: short wall stub
    B.box(-14.6, 0.0, -12.15, -13.0, CEIL0, -11.9, "M_paint_white", skip="tb")
    B.cbox(-14.6, 0.0, -12.15, -13.0, CEIL0, -11.9)
    international_office(B)


def international_office(B):
    """glass box in the north-west corner: x[-18,-10] z[-26,-19], door at x=-11.6"""
    B.use("volt_gf")
    y1 = CEIL0
    # east partition x=-10 (z -25.85..-19)
    with B.frame(wall_frame(-10.0, -19.0, -10.0, -25.85)[0]):
        A.curtain_wall(B, 0.0, 6.85, 0.0, y1, 0.0, 1.37, 2.3, frame="M_alu_silver", glass="M_glass_partition", depth=0.06, mw=0.05)
    B.cbox(-10.03, 0.0, -25.85, -9.97, y1, -19.0)
    # south partition z=-19 (x -17.85..-10) with an open door at x=-11.6
    xf, L = wall_frame(-17.85, -19.0, -10.0, -19.0)
    with B.frame(xf):
        A.curtain_wall(B, 0.0, 5.65, 0.0, y1, 0.0, 1.41, 2.3, frame="M_alu_silver", glass="M_glass_partition", depth=0.06, mw=0.05)
        A.curtain_wall(B, 5.65, 6.85, 2.3, y1, 0.0, 1.2, 2.3, frame="M_alu_silver", glass="M_glass_partition", depth=0.06, mw=0.05)
        # door frame + glass leaf swung open into the office
        B.box(5.65, 0.0, -0.03, 5.7, 2.3, 0.03, "M_alu_silver")
        B.box(6.8, 0.0, -0.03, 6.85, 2.3, 0.03, "M_alu_silver")
        with B.at(5.7, 0, 0.0, math.pi / 2 * 0.85):
            A.frame_rect(B, 0.0, 1.08, 0.01, 2.27, -0.02, 0.02, 0.04, "M_alu_silver")
            B.quad((0.04, 0.05, 0.0), (1.04, 0.05, 0.0), (1.04, 2.23, 0.0), (0.04, 2.23, 0.0), "M_glass_partition", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
            B.quad((1.04, 0.05, 0.0), (0.04, 0.05, 0.0), (0.04, 2.23, 0.0), (1.04, 2.23, 0.0), "M_glass_partition", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        A.curtain_wall(B, 6.85, L, 0.0, y1, 0.0, 1.0, 2.3, frame="M_alu_silver", glass="M_glass_partition", depth=0.06, mw=0.05)
    B.cbox(-17.85, 0.0, -19.03, -12.15, y1, -18.97)
    B.cbox(-11.0, 0.0, -19.03, -10.0, y1, -18.97)
    B.cbox(-12.15, 2.3, -19.03, -11.0, y1, -18.97)
    # carpet inside the office
    B.box(-17.85, 0.0, -25.85, -10.03, 0.008, -19.03, "M_carpet", skip="nsewb")


# ------------------------------------------------------------------ stairs
def stairs(B):
    B.use("volt_stairs")
    B.use_col("COL_voltaire")
    A.stairs(B, 11.7, 2.3, -12.4, -19.0, 0.0, F1, "M_terrazzo", "M_terrazzo", "M_paint_white", nosing="M_alu_silver")
    # wall on the lobby side of the flight, closed under-stair
    fac(B, 10.42, -19.0, 10.42, -12.4, 0.0, CEIL0, 0.13, "M_paint_white", "M_paint_white", (), top=True, mat_top="M_paint_white", base_out=SKIRT)
    fac(B, 12.85, -19.1, 10.55, -19.1, 0.0, CEIL0, 0.1, "M_paint_white", "M_paint_white", (), base_out=SKIRT)
    # handrail along the east wall: KB1's blue tube
    A.handrail(B, [(12.78, 0.0, -12.4), (12.78, F1, -19.0)], h=0.9, r=0.022, mat="M_paint_rail_blue", post_every=99,
               posts=False)
    for z in (-12.9, -15.7, -18.5):
        y = (-12.4 - z) / 6.6 * F1
        B.box(12.78, y + 0.86, z - 0.02, 12.85, y + 0.9, z + 0.02, "M_alu_silver")
    # landing floor + slab edges around the void
    with B.ground_at(F1):
        B.box(10.55, CEIL0, -25.85, 12.85, F1, -19.0, "M_vinyl", skip="nwesb", sub=3.0)
    B.box(10.42, CEIL0, -19.0, 10.55, F1, -12.15, "M_paint_white", skip="ns")
    B.cbox(10.55, CEIL0, -25.85, 12.85, F1, -19.0)
    light(B, "stairwell", 11.7, CEIL1 - 0.2, -15.6, K(4000), 1.4, 9.0, shadow=True)
    stair_door(B)
    B.use("volt_gf_ceiling", cast=False)
    panel(B, 11.7, -15.3, CEIL1, 0.6, 1.2)


def stair_door(B):
    """the door to the stairwell on the first-floor landing: navy, with KB1's giant white floor numeral painted
    across leaf and frame"""
    B.use("volt_stairs")
    x0, x1, z = 11.15, 12.35, -25.85
    with B.at(0.0, F1, 0.0):
        A.frame_rect(B, x0, x1, 0.0, 2.15, z, z + 0.05, 0.07, "M_paint_metal_dark", bottom=False)
        B.box(x0 + 0.07, 0.0, z, x1 - 0.07, 2.08, z + 0.03, "M_paint_epita", skip="nb")
        B.box(x1 - 0.25, 0.98, z + 0.03, x1 - 0.12, 1.02, z + 0.08, "M_alu_silver")
    with B.at((x0 + x1) / 2, F1 + 1.2, z + 0.052):
        B.text("1", V_font("sign"), 1.7, "M_plate_white", align="CENTER", valign="CENTER", depth=0.003)


def V_font(name):
    import campus_gen
    return campus_gen.font(name)


# ------------------------------------------------------------------ 1st floor
def first_floor(B):
    B.use("volt_f1")
    B.use_col("COL_voltaire")
    with B.ground_at(F1):
        # floors: vinyl corridor, carpet tiles in the rooms (per-tile turn + tint, like real carpet tiles)
        B.box(-17.85, CEIL0, -16.0, 10.42, F1, -12.15, "M_vinyl", skip="nsewb", sub=3.0)
        B.box(8.0, CEIL0, -25.85, 10.42, F1, -16.0, "M_vinyl", skip="nsewb", sub=3.0)
        carpet_tiles(B, -20.8, -4.0, -31.35, -16.0, F1)
        carpet_tiles(B, -4.0, 8.0, -31.35, -16.0, F1)
    B.cbox(-18.0, CEIL0, -16.0, 10.42, F1, -12.0)
    B.cbox(-20.8, CEIL0, -31.35, 8.075, F1, -15.9)
    B.cbox(8.0, CEIL0, -26.0, 10.42, F1, -16.0)
    # corridor south wall (blank, lockers against it)
    fac(B, 12.85, -12.15, -17.85, -12.15, CEIL0, CEIL1, 0.3, "M_paint_warm", False, (), top=False, ends=False)
    B.box(-17.85, F1, -12.164, 10.42, F1 + SKIRT[1], -12.15, SKIRT[0], skip="sb")
    # SM14 / SM15 partitions with open doors and glazed panels
    ops = [Opening(6.15, 7.55, F1, F1 + 2.3, "door_open", leaf="M_wood_oak", glazed=True, open_frac=0.9, kick="M_steel"),
           Opening(8.25, 10.85, F1 + 1.1, F1 + 2.4, "window", frame="M_alu_silver", cols=2, glass="M_glass_partition", depth=0.075, sill=None),
           Opening(14.45, 18.45, F1 + 1.1, F1 + 2.4, "window", frame="M_alu_silver", cols=3, glass="M_glass_partition", depth=0.075, sill=None),
           Opening(19.15, 20.55, F1, F1 + 2.3, "door_open", leaf="M_wood_oak", glazed=True, open_frac=0.9, kick="M_steel")]
    fac(B, -17.85, -15.925, 8.075, -15.925, F1, CEIL1, 0.15, "M_paint_warm", "M_paint_white", ops, top=False, base_in=SKIRT, base_out=SKIRT)
    fac(B, -3.925, -16.075, -3.925, -31.35, F1, CEIL1, 0.15, "M_paint_white", "M_paint_white", (), top=False, base_in=SKIRT, base_out=SKIRT)
    fac(B, 8.075, -16.075, 8.075, -31.35, F1, CEIL1, 0.15, "M_paint_warm", "M_paint_white", (), top=False, base_in=SKIRT, base_out=SKIRT)
    # glass balustrade along the stair void
    with B.frame(wall_frame(10.5, -12.15, 10.5, -19.0)[0]):
        A.glass_railing(B, 0.0, 6.85, F1, col_group="COL_voltaire")
    # ceilings + panels + lights
    B.use("volt_f1_ceiling", cast=False)
    ceiling(B, -17.85, 12.85, -25.85, -12.15, CEIL1)
    ceiling(B, -20.8, -17.85, -31.35, -15.925, CEIL1)
    ceiling(B, -17.85, 8.075, -31.35, -25.85, CEIL1)
    for x in [-15.3 + 3.0 * k for k in range(9)]:
        panel(B, x, -14.1, CEIL1, 1.2, 0.3)
    for x in (9.3, 11.7):
        for z in (-17.7, -21.3, -24.3):
            panel(B, x if x < 10 else x, z, CEIL1, 0.6, 0.6)
    for x in [-18.6 + 2.4 * k for k in range(11)]:
        for z in (-18.9, -21.3, -23.7, -26.1, -28.5, -30.6):
            if -4.6 < x < -3.4:
                continue
            panel(B, round(x / 0.6) * 0.6 + 0.3, z, CEIL1, 1.2, 0.3)
    B.cbox(-21.1, CEIL1, -31.65, 13.0, F1 + FLOOR, -12.0)
    for i, x in enumerate((-15.0, -9.0, -3.0, 3.0, 9.0)):
        light(B, "f1_corridor_%02d" % i, x, CEIL1 - 0.15, -14.0, K(4300), 1.0, 7.0, shadow=i == 2)
    for i, (x, z) in enumerate(((-14, -21), (-8, -21), (0, -21), (5, -21), (-14, -24.5), (2, -24.5), (-12, -28.8), (2, -28.8))):
        light(B, "sm_%02d" % i, x, CEIL1 - 0.15, z, K(4500), 1.3, 8.0, shadow=i in (0, 1, 2, 3))
    light(B, "f1_landing", 11.7, CEIL1 - 0.15, -22.5, K(4300), 1.0, 7.0)
    dado(B)


def dado(B):
    """the navy dado of KB1's corridors: the wall painted navy from the skirting to 0.95 m, along
    the 1st-floor corridor (broken at SM14's and SM15's doors) and round the landing"""
    B.use("volt_f1")
    y0, h = F1 + SKIRT[1], 0.95 - SKIRT[1]
    up = (0, h, 0)
    B.rect((10.42, y0, -12.153), (-28.27, 0, 0), up, "M_paint_epita")                  # corridor, south wall
    for (x0, x1) in ((-17.85, -11.7), (-10.3, 1.3), (2.7, 8.075)):
        B.rect((x0, y0, -15.922), (x1 - x0, 0, 0), up, "M_paint_epita")              # the SM rooms' wall
    B.rect((-17.847, y0, -12.15), (0, 0, -3.775), up, "M_paint_epita")                # corridor, west end
    B.rect((8.078, y0, -16.075), (0, 0, -9.775), up, "M_paint_epita")                 # toward the landing
    B.rect((12.847, y0, -25.85), (0, 0, 6.85), up, "M_paint_epita")                   # landing, stair side


def carpet_tiles(B, x0, x1, z0, z1, y, size=0.5):
    """50 cm carpet tiles laid quarter-turned (checkerboard of pile direction) with a little tint jitter"""
    import random
    rng = random.Random(int(x0 * 13 + z0 * 7))
    nx = int(round((x1 - x0) / size + 0.49))
    nz = int(round((z1 - z0) / size + 0.49))
    for i in range(nx):
        for j in range(nz):
            a, b = x0 + i * size, min(x1, x0 + (i + 1) * size)
            c, d = z0 + j * size, min(z1, z0 + (j + 1) * size)
            if b - a < 0.01 or d - c < 0.01:
                continue
            uvs = [(0, 0), ((b - a) / size, 0), ((b - a) / size, (d - c) / size), (0, (d - c) / size)]
            if (i + j) % 2:
                uvs = [(v, 1 - u) for u, v in uvs]
            t = 0.93 + rng.random() * 0.1
            with B.tinted((t, t, t)):
                B.face([(a, y, d), (b, y, d), (b, y, c), (a, y, c)], "M_carpet", uvs=uvs)
