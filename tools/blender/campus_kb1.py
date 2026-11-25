"""KB1, the Batiment Voltaire, on its real outlines (docs/DESIGN.md §8.3):
- the 1990s building: the rue Pasteur wing (VOLT_STRIP, 51.7 m long, 11.2 m deep, 3 storeys, 11.7 m) and the north
  block (VOLT_GF, to z -31.6, three ground-floor bays to -33.7), with the two yards (8.2 m west, 8.0 m east) beside it;
- the 2016-18 raising (VOLT_RAISE): a storey-high void over the old roof, then a three-storey steel box on pillars
  over the whole block and both yards, top 22.5 m; cobalt ribbed steel and tilted red balcony boxes to rue Voltaire,
  wood-look Trespa with a steel mesh to the campus;
- the rue Pasteur front: white render over a grey plinth, two-storey dark-framed glass bays whose tops lean back to
  the wall, the white projecting "KB1" portal (the story's way in, x 9.3), a planter, the "19" plate (campus_dress);
- the rue Voltaire front: the white colonnade with blue bases under the box, the planted forecourt, the black-glass
  "KB1" canopy over the doors of the middle bay.
Rooms nobody enters (the first floor over the lobby, the second floor, the back offices) show through their windows as
interior-mapped panes (campus_arch.interior_quad, scripts/fx/interior.gdshader). The lobby, the stairs, the 1st-floor
corridor and SM14/SM15 are built by campus_voltaire. No logos: only the "KB1" building code."""
import math, os, random
import campus_arch as A
import campus_poly as PG
import campus_tex as T
import campus_voltaire as V
from campus_arch import Opening, wall_frame, interior_quad
from campus_layout import *
from campus_mat import K, mat as defmat

defmat("M_render_plinth", ("ph", "white_stucco", "2k"), tile=2.0, color="#8e9091", grime="ext", macro=0.07)
defmat("M_metal_cobalt", ("gen", "ribbed_steel", "1k"), tile=1.6, color="#2c4f8e", rough=0.42, metal=0.55, grime="ext",
       macro=0.05)
defmat("M_metal_cobalt_vent", ("gen", "ribbed_steel", "1k"), tile=0.5, color="#3b66ad", rough=0.4, metal=0.55,
       grime="none", macro=0.03)
defmat("M_soffit_ribbed", ("gen", "ribbed_steel", "1k"), tile=1.2, color="#9ea3a8", rough=0.72, metal=0.1, grime="none",
       macro=0.04)                # painted steel deck: matte, or it mirrors the sky's trees in waves
defmat("M_canopy_black", None, color="#0c0e11", rough=0.07, metal=0.35, grime="ext", macro=0.02)
defmat("M_paint_column", None, color="#efefea", rough=0.4, metal=0.1, grime="ext", macro=0.03)
defmat("M_paint_column_blue", None, color="#2d5ba6", rough=0.4, metal=0.2, grime="ext", macro=0.03)
defmat("M_resin_grey", ("ph", "concrete_floor_02", "2k"), tile=2.2, color="#b9b8b4", grime="floor", macro=0.05)
defmat("M_letter_grey", None, color="#b5b5b5", rough=0.45)
defmat("M_hedge", ("acg", "Foliage001", "1K"), tile=0.9, color="#6f8a4a", rough=0.8, grime="none", macro=0.1,
       maps=("diffa", "nor_gl", "arm"))

T_W = 0.3                         # outer walls
WX0, WX1 = -29.25, 22.4           # rue Pasteur wing (VOLT_STRIP x -29.3/-29.2 .. 22.4), party walls at both ends
WZS, WZN = -5.0, -16.15           # its street face and its back over the yards
NX0, NX1 = -21.1, 14.35           # 1990s north block (VOLT_GF)
NZN = -31.65                      # its rue Voltaire face
BAYS_N = ((-13.0, -7.35, -33.6), (-5.05, -1.55, -32.8), (0.7, 6.35, -33.65))   # ground-floor bays (VOLT_GF)
HALL = (-6.9, 0.55)               # entrance hall from the lobby to the rue Voltaire doors in the middle bay
RAISE = PG.cw([(-29.2, -16.1), (22.4, -16.1), (22.4, -31.1), (23.6, -34.5), (-28.5, -37.4)])   # box roof
PARCEL = ((-29.3, -39.1), (23.5, -34.5))   # the rue Voltaire property line
BOX0, BOX_ST = 14.1, 2.8          # the box: soffit, storey height; roof at 22.5 (IGN 22.5 m), parapet 22.95
BOX1 = BOX0 + 3 * BOX_ST
ROOF, PARA = V.ROOF, V.PARA

# rue Pasteur front: two-storey glass bays between white piers, the west door in the third bay, the KB1 portal
STREET_BAYS = ((-27.85, -23.05), (-21.85, -17.05), (-15.85, -11.05), (-9.85, -5.05), (-3.85, 0.95), (2.15, 6.95),
               (11.95, 16.75), (17.95, 21.05))
WEST_DOOR = (-14.65, -12.25)
PORTAL = (7.6, 11.0)              # the white "KB1" portal; its door 8.1 .. 10.5 (PORTAL_street__volt_gf at x 9.3)
PORTAL_DOOR = (8.1, 10.5)
BAY_Y0, BAY_GF, BAY_SP, BAY_Y1, BAY_TOP, BAY_OUT = 1.3, 3.3, 4.1, 6.7, 7.4, 0.3


def parcel_z(x):
    (ax, az), (bx, bz) = PARCEL
    return az + (bz - az) * (x - ax) / (bx - ax)


def box_edge_z(x):
    """z of the box's north face (-28.5, -37.4) -> (23.6, -34.5)"""
    return -37.4 + 2.9 * (x + 28.5) / 52.1


def build(B):
    ribbed_steel()
    street_front(B)
    yard_faces(B)
    north_faces(B)
    partitions(B)
    roofs(B)
    box(B)
    north_side(B)
    solids(B)


# ------------------------------------------------------------------ generated cladding texture
def ribbed_steel():
    """horizontal trapezoidal ribs (0.2 m pitch at tile 1.6) for the box's cobalt cladding and the grey soffit:
    diff + nor_gl + arm 1k in assets/textures/campus_gen (deterministic numpy, no download)"""
    import numpy as np
    G = os.path.join(T.TEX_DIR, "campus_gen")
    d, n, a = (os.path.join(G, f"ribbed_steel_{m}_1k.jpg") for m in ("diff", "nor_gl", "arm"))
    if all(os.path.exists(p) and os.path.getsize(p) > 0 for p in (d, n, a)):
        return
    os.makedirs(G, exist_ok=True)
    S = 1024
    rng = np.random.default_rng(31)
    y = np.arange(S, dtype=np.float32) / S * 8.0            # 8 ribs per tile
    f = y - np.floor(y)
    prof = np.clip(np.minimum(f / 0.18, (1.0 - f) / 0.18), 0.0, 1.0)
    prof = np.where((f > 0.42) & (f < 0.58), 0.35, prof)   # a shallow stiffening groove on each rib
    hgt = np.tile(prof[:, None], (1, S)).astype(np.float32)
    # faint broad blotches only: fine vertical streaks shimmer on the soffit seen edge-on
    blot = rng.random((16, 16)).astype(np.float32)
    blot = np.kron(blot, np.ones((S // 16, S // 16), np.float32))
    blot = (blot + np.roll(blot, S // 32, 0) + np.roll(blot, S // 32, 1) + np.roll(blot, S // 32, (0, 1))) / 4
    col = np.ones((S, S, 3), np.float32) * (0.95 + 0.05 * blot[:, :, None])
    col *= (0.86 + 0.14 * hgt)[:, :, None]
    noise = rng.random((S, S)).astype(np.float32)
    col *= (0.985 + 0.015 * noise)[:, :, None]
    gy = np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)
    nrm = np.stack([np.zeros_like(gy), gy * 6.0, np.ones_like(gy)], 2)
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    T._write_img(d, col)
    T._write_img(n, nrm * 0.5 + 0.5)
    T._write_img(a, np.stack([0.75 + 0.25 * hgt, 0.55 - 0.1 * hgt + 0.05 * noise, np.ones((S, S))], 2))
    for p in (d, n, a):
        T.write_import_preset(p)


# ------------------------------------------------------------------ rue Pasteur front
def street_front(B):
    B.use("volt_facade_s")
    B.use_col("COL_voltaire")
    u = lambda x: x - WX0
    L = WX1 - WX0
    with B.ground_at(0.1):
        gf = []
        for (x0, x1) in STREET_BAYS:
            if x0 < WEST_DOOR[0] < x1:
                gf.append(Opening(u(x0), u(x1), 0.0, BAY_GF, "passage"))     # the west door: the bay opens to the floor
            else:
                gf.append(Opening(u(x0), u(x1), BAY_Y0, BAY_GF, "blank"))
        gf.append(Opening(u(PORTAL_DOOR[0]), u(PORTAL_DOOR[1]), 0.0, 2.7, "passage"))
        V.fac(B, WX0, WZS, WX1, WZS, 0.0, FLOOR, T_W, "M_render_white", V.WALL_IN, gf, top=False, base_in=V.SKIRT)
        up = [V.ext_win(9.3 - WX0, 1.5, 4.6, 6.4, 120, lit=0.5, sill="M_concrete", cols=1)]
        for i, (x0, x1) in enumerate(STREET_BAYS):
            up.append(V.ext_win(u((x0 + x1) / 2), x1 - x0 - 0.9, 8.15, 9.85, 140 + i, lit=0.55, sill="M_concrete",
                                cols=3))
        up.append(V.ext_win(9.3 - WX0, 1.6, 8.15, 9.85, 139, lit=0.5, sill="M_concrete", cols=1))
        V.fac(B, WX0, WZS, WX1, WZS, FLOOR, ROOF, T_W, "M_render_white", False, up, top=False)
        V.fac(B, WX0, WZS, WX1, WZS, ROOF, PARA, T_W, "M_render_white", "M_concrete", (), top=True, mat_top="M_zinc")
    xf, _ = wall_frame(WX0, WZS, WX1, WZS)
    with B.frame(xf):
        # grey plinth, stopped at the west door and the portal
        for (a, b) in ((0.0, u(WEST_DOOR[0])), (u(WEST_DOOR[1]), u(PORTAL[0])), (u(PORTAL[1]), L)):
            B.box(a, 0.0, 0.0, b, BAY_Y0, 0.025, "M_render_plinth", skip="nb")
        B.box(-0.02, PARA, -T_W - 0.03, L + 0.02, PARA + 0.05, 0.04, "M_zinc")
        for i, (x0, x1) in enumerate(STREET_BAYS):
            door = (u(WEST_DOOR[0]), u(WEST_DOOR[1])) if x0 < WEST_DOOR[0] < x1 else None
            street_bay(B, u(x0), u(x1), 160 + i, door)
        portal(B, u(PORTAL[0]), u(PORTAL[1]), u(PORTAL_DOOR[0]), u(PORTAL_DOOR[1]))
        for uu in (0.35, L - 0.35):
            A.downpipe(B, uu, 0.0, PARA - 0.1)
        # thresholds: the sidewalk stops on the building line, the lobby floor starts behind the wall
        for (a, b) in ((u(WEST_DOOR[0]), u(WEST_DOOR[1])), (u(PORTAL_DOOR[0]), u(PORTAL_DOOR[1]))):
            B.box(a, 0.0, -T_W, b, 0.012, 0.0, "M_steel", skip="b")
            B.cbox(a, -0.5, -T_W, b, 0.0, 0.0)
    planter(B)
    V.light(B, "canopy_w", (WEST_DOOR[0] + WEST_DOOR[1]) / 2, 3.0, WZS + 0.15, K(3000), 1.0, 6.0)
    V.light(B, "canopy_e", 9.3, 2.6, WZS + 0.45, K(3000), 1.2, 6.0)


def street_bay(B, u0, u1, seed, door=None):
    """a two-storey glass bay standing BAY_OUT proud of the facade (local frame of the street wall, +z = street):
    the lobby behind clear glass up to the spandrel, the first-floor room as an interior-mapped pane, and a sloped
    glass top leaning back to the wall like a lean-to roof light"""
    o = BAY_OUT
    zf = o - 0.03                        # glass plane, the bars stand proud of it
    bar = "M_alu_anthracite"
    w = u1 - u0
    n = max(2, int(round(w / 1.2)))
    us = [u0 + w * i / n for i in range(n + 1)]
    # white cheeks with their sloped tops, the sill ledge, the soffit over the lobby glazing
    for (a, b) in ((u0 - 0.12, u0), (u1, u1 + 0.12)):
        y_lo = 0.0 if door else BAY_Y0 - 0.12
        B.box(a, y_lo, 0.0, b, BAY_Y1, o, "M_render_white", skip="n")
        for x, nrm in ((a, -1), (b, 1)):
            pts = [(x, BAY_Y1, 0.0), (x, BAY_Y1, o), (x, BAY_TOP, 0.0)]
            B.face(pts if nrm < 0 else pts[::-1], "M_render_white")
        B.quad((a, BAY_Y1, o), (b, BAY_Y1, o), (b, BAY_TOP, 0.0), (a, BAY_TOP, 0.0), "M_render_white")
    sills = [(u0 - 0.12, u1 + 0.12)] if not door else [(u0 - 0.12, door[0]), (door[1], u1 + 0.12)]
    for (a, b) in sills:
        B.box(a, BAY_Y0 - 0.12, -0.02, b, BAY_Y0, o + 0.05, "M_concrete")
        if door:
            # the bay opens to the floor for the door: a low plinth wall closes the glazing beside it
            B.box(a, 0.0, -T_W, b, BAY_Y0 - 0.12, o, "M_render_plinth", skip="b", mats={"n": V.WALL_IN})
    B.quad((u1, BAY_GF, 0.0), (u0, BAY_GF, 0.0), (u0, BAY_GF, o), (u1, BAY_GF, o), "M_render_white")
    # frame: mullions over the full height, transoms at the sill, the spandrel and the slope
    for x in us:
        B.box(x - 0.03, BAY_Y0 if not door or not (door[0] - 0.01 < x < door[1] + 0.01) else 2.75, zf - 0.03,
              x + 0.03, BAY_Y1, o + 0.02, bar)
    for y in (BAY_Y0, BAY_GF, BAY_SP, BAY_Y1):
        if door and y == BAY_Y0:
            for (a, b) in sills:
                B.box(max(a, u0), y - 0.03, zf - 0.03, min(b, u1), y + 0.03, o + 0.02, bar)
            continue
        B.box(u0, y - 0.03, zf - 0.03, u1, y + 0.03, o + 0.02, bar)
    # lobby glazing (Godot's glass), spandrel, the first-floor room, the sloped top
    uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    if door:
        for (a, b) in ((u0, door[0]), (door[1], u1)):
            B.quad((a, BAY_Y0, zf), (b, BAY_Y0, zf), (b, BAY_GF, zf), (a, BAY_GF, zf), "M_glass_clear", uvs=uv)
        B.quad((door[0], 2.75, zf), (door[1], 2.75, zf), (door[1], BAY_GF, zf), (door[0], BAY_GF, zf), "M_glass_clear", uvs=uv)
        # sliding leaves parked open behind the fixed panes, black frame round the opening
        A.frame_rect(B, door[0], door[1], 0.0, 2.75, zf - 0.05, zf + 0.03, 0.06, "M_plastic_black", bottom=False)
        for side in (-1, 1):
            x0 = door[0] - 1.15 if side < 0 else door[1] + 0.05
            A.frame_rect(B, x0, x0 + 1.1, 0.02, 2.65, zf - 0.12, zf - 0.08, 0.05, "M_plastic_black")
            B.quad((x0 + 0.05, 0.07, zf - 0.1), (x0 + 1.05, 0.07, zf - 0.1), (x0 + 1.05, 2.6, zf - 0.1),
                   (x0 + 0.05, 2.6, zf - 0.1), "M_glass_clear", uvs=uv)
        B.box(door[0], 2.75, zf - 0.04, door[1], 3.27, zf - 0.02, "M_alu_anthracite")   # lettering band (campus_dress)
    else:
        B.quad((u0, BAY_Y0, zf), (u1, BAY_Y0, zf), (u1, BAY_GF, zf), (u0, BAY_GF, zf), "M_glass_clear", uvs=uv)
    # A4 notices taped inside some panes, read from the pavement; no logo decals
    rng = random.Random(seed)
    for k in range(0 if door else rng.choice((0, 1, 1, 2))):
        cx = u0 + 0.35 + rng.random() * (w - 0.7)
        cy = BAY_Y0 + 0.45 + rng.random() * 0.5
        a = rng.uniform(-0.05, 0.05)
        pts = [(-0.105, -0.1485), (0.105, -0.1485), (0.105, 0.1485), (-0.105, 0.1485)]
        q = [(cx + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a), zf - 0.008) for px, py in pts]
        with B.in_part("volt_dress"):          # the lobby's notice boards already draw these materials there
            B.quad(*q, "M_notice_%d" % rng.choice((0, 1, 3, 5)), uvs=uv)
            B.quad(*[(x, y, z - 0.001) for x, y, z in q[::-1]], "M_paper_white")     # its back, from the lobby
    B.quad((u0, BAY_GF, zf), (u1, BAY_GF, zf), (u1, BAY_SP, zf), (u0, BAY_SP, zf), "M_spandrel_dark")
    interior_quad(B, u0, u1, BAY_SP, BAY_Y1, zf - 0.005, ("M_window_office", seed, 0.55))
    B.quad((u0, BAY_Y1, o - 0.005), (u1, BAY_Y1, o - 0.005), (u1, BAY_TOP - 0.02, 0.0), (u0, BAY_TOP - 0.02, 0.0),
           "M_spandrel_dark")
    for x in us:
        B.quad((x - 0.03, BAY_Y1, o + 0.02), (x + 0.03, BAY_Y1, o + 0.02), (x + 0.03, BAY_TOP, 0.02),
               (x - 0.03, BAY_TOP, 0.02), bar)
    # colliders: the bay above the pavement, the glazing beside a door
    if door:
        for (a, b) in sills:
            B.cbox(a, 0.0, -T_W, b, BAY_TOP, o)
        B.cbox(door[0], 2.75, 0.0, door[1], BAY_TOP, o)
    else:
        B.cbox(u0 - 0.12, 0.0, 0.0, u1 + 0.12, BAY_TOP, o)


def portal(B, u0, u1, d0, d1):
    """the white projecting "KB1" portal round a recessed black door. The two steps of the
    real portal are left out: the lobby floor is level with the pavement in the game."""
    p = 0.75
    with B.ground_at(0.1):
        for (a, b) in ((u0, d0), (d1, u1)):
            B.box(a, 0.0, 0.0, b, 3.5, p, "M_render_white", skip="n")
            B.box(a - 0.005, 0.0, -0.005, b + 0.005, 0.18, p + 0.005, "M_render_plinth", skip="nt")
            B.cbox(a, 0.0, 0.0, b, 3.5, p)
        B.box(d0, 2.72, 0.0, d1, 3.5, p, "M_render_white", skip="n")
    with B.at((u0 + u1) / 2, 3.11, p + 0.004):
        B.text("KB1", V_font("bold"), 0.36, "M_letter_grey", align="CENTER", valign="CENTER", depth=0.02)
    # black door frame, leaves parked open, transom; a downlight in the soffit
    A.frame_rect(B, d0, d1, 0.0, 2.7, -0.2, -0.06, 0.07, "M_plastic_black", bottom=False)
    for side in (-1, 1):
        x0 = d0 - 1.0 if side < 0 else d1 - 0.12
        A.frame_rect(B, x0, x0 + 1.12, 0.02, 2.62, -0.28, -0.24, 0.05, "M_plastic_black")
        B.quad((x0 + 0.05, 0.07, -0.26), (x0 + 1.07, 0.07, -0.26), (x0 + 1.07, 2.57, -0.26), (x0 + 0.05, 2.57, -0.26),
               "M_glass_clear", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.box(d0, 2.7, -0.2, d1, 2.72, p, "M_plastic_black")
    B.box((d0 + d1) / 2 - 0.15, 2.69, p * 0.5 - 0.15, (d0 + d1) / 2 + 0.15, 2.7, p * 0.5 + 0.15, "M_light_warm", skip="t")


def V_font(name):
    import campus_gen
    return campus_gen.font(name)


def planter(B):
    """the grey concrete planter wall with evergreen shrubs and ivy along the west end of the front"""
    from campus_props_out import foliage
    rng = random.Random(19)
    x0, x1, z0, z1 = WX0 + 0.4, -23.3, WZS, WZS + 0.55
    with B.ground_at(0.1):
        B.box(x0, 0.1, z0, x1, 0.62, z1, "M_render_plinth", skip="bn")
        B.box(x0 + 0.08, 0.5, z0 + 0.02, x1 - 0.08, 0.56, z1 - 0.08, "M_soil", skip="b")
    x = x0 + 0.5
    while x < x1 - 0.4:
        foliage(B, (x, 0.95, z0 + 0.3), (0.55, 0.42, 0.3), 9, 0.7, "M_leaves_plane", rng, bias=0.6)
        x += 0.9
    B.cbox(x0, 0.0, z0, x1, 0.62, z1)


# ------------------------------------------------------------------ the wing's back over the two yards
def yard_faces(B):
    """the wing's back over the west and east yards: lobby windows on the ground floor, rooms above"""
    B.use("volt_facade_n")
    B.use_col("COL_voltaire")
    for (ax, bx, seed) in ((NX0, WX0, 300), (WX1, NX1, 320)):
        L = abs(bx - ax)
        with B.ground_at(0.0):
            gf = [V.win(u, 2.4, 0.9, 2.8, cols=2, inner_sill="M_laminate_white", depth=0.1) for u in (L * 0.28, L * 0.72)]
            V.fac(B, ax, WZN, bx, WZN, 0.0, FLOOR, T_W, "M_render_white", V.WALL_IN, gf, top=False, base_in=V.SKIRT)
            up = []
            for k, y in enumerate((F1, 2 * FLOOR)):
                for j, uu in enumerate((L * 0.28, L * 0.72)):
                    up.append(V.ext_win(uu, 1.6, y + 0.9, y + 2.6, seed + k * 7 + j, lit=0.45, sill="M_concrete", cols=2))
            V.fac(B, ax, WZN, bx, WZN, FLOOR, ROOF, T_W, "M_render_white", False, up, top=False)
            V.fac(B, ax, WZN, bx, WZN, ROOF, PARA, T_W, "M_render_white", "M_concrete", (), top=True, mat_top="M_zinc")
        xf, _ = wall_frame(ax, WZN, bx, WZN)
        with B.frame(xf):
            B.box(-0.01, 0.0, 0.0, L + 0.01, 0.6, 0.02, "M_render_plinth", skip="nb")
            A.downpipe(B, 0.35, 0.0, PARA - 0.1)


# ------------------------------------------------------------------ the north block: yards and rue Voltaire
SM_WINDOWS_N = (-19.0, -15.6, -12.2, -8.8, -5.6, -2.3, 1.0, 4.3, 6.9)   # 1st floor, rue Voltaire side
SM14_WINDOWS_W = (-29.6, -26.0)                                          # SM14's west wall, over the west yard


def north_faces(B):
    B.use("volt_facade_n")
    B.use_col("COL_voltaire")
    with B.ground_at(0.0):
        # west face over the west yard: back offices, SM14 (its west windows; the whiteboard hangs further south)
        gf = [V.ext_win(u, 1.8, 0.9, 2.8, 400 + i, lit=0.4, sill="M_concrete", cols=2) for i, u in enumerate((2.6, 6.6, 10.6, 13.6))]
        V.fac(B, NX0, NZN, NX0, WZN, 0.0, FLOOR, T_W, "M_render_white", V.WALL_IN, gf, top=False)
        f1 = [V.win(z - NZN, 1.8, F1 + 0.9, F1 + 2.8, cols=2, inner_sill="M_laminate_white", depth=0.1) for z in SM14_WINDOWS_W]
        V.fac(B, NX0, NZN, NX0, WZN, F1, F1 + FLOOR, T_W, "M_render_white", "M_paint_white", f1, top=False, base_in=V.SKIRT)
        f2 = [V.ext_win(u, 1.8, 2 * FLOOR + 0.9, 2 * FLOOR + 2.8, 420 + i, lit=0.45, sill="M_concrete", cols=2)
              for i, u in enumerate((2.6, 6.6, 10.6, 13.6))]
        V.fac(B, NX0, NZN, NX0, WZN, 2 * FLOOR, ROOF, T_W, "M_render_white", False, f2, top=False)
        # east face over the east yard: everything behind it is out of reach
        ops = [V.ext_win(u, 1.8, y + 0.9, y + 2.8, 440 + k * 5 + i, lit=0.45, sill="M_concrete", cols=2)
               for k, y in enumerate((0.0, F1, 2 * FLOOR)) for i, u in enumerate((2.6, 6.6, 10.6, 13.6))]
        V.fac(B, NX1, WZN, NX1, NZN, 0.0, ROOF, T_W, "M_render_white", False, ops, top=False)
        # rue Voltaire face (walked from east to west): back offices and the hall on the ground floor, SM14 and SM15
        # on the first floor, offices and the big window grid over the entrance on the second
        Ln = NX1 - NX0
        un = lambda x: NX1 - x
        gf = []
        for i, x in enumerate((11.4, 8.4, -16.3, -19.3)):
            gf.append(V.ext_win(un(x), 1.6, 0.9, 2.8, 460 + i, lit=0.35, sill="M_concrete", cols=2))
        gf.append(Opening(un(BAYS_N[1][1]), un(BAYS_N[1][0]), 0.0, V.CEIL0 + 0.05, "passage"))
        V.fac(B, NX1, NZN, NX0, NZN, 0.0, FLOOR, T_W, "M_render_white", V.WALL_IN, gf, top=False, base_in=V.SKIRT)
        f1 = []
        for x in SM_WINDOWS_N:
            if x > 8.2:
                f1.append(V.ext_win(un(x), 1.6, F1 + 0.9, F1 + 2.8, 470, lit=0.4, sill="M_concrete", cols=2))
            else:
                f1.append(V.win(un(x), 1.9, F1 + 0.85, F1 + 2.8, cols=2, inner_sill="M_laminate_white", depth=0.1))
        f1.append(V.ext_win(un(11.6), 1.6, F1 + 0.9, F1 + 2.8, 471, lit=0.4, sill="M_concrete", cols=2))
        V.fac(B, NX1, NZN, NX0, NZN, F1, F1 + FLOOR, T_W, "M_render_white", "M_paint_white", f1, top=False, base_in=V.SKIRT)
        f2 = [V.ext_win(un(x), 1.6, 2 * FLOOR + 0.9, 2 * FLOOR + 2.8, 480 + i, lit=0.45, sill="M_concrete", cols=2)
              for i, x in enumerate((11.6, 8.0, 4.3, 1.0, -8.8, -12.2, -15.6, -19.0))]
        f2.append(V.ext_win(un((BAYS_N[1][0] + BAYS_N[1][1]) / 2), 3.3, 2 * FLOOR + 0.35, 2 * FLOOR + 3.3, 489, lit=0.6,
                            sill=None, cols=4, rows=4, frame="M_plastic_black"))
        V.fac(B, NX1, NZN, NX0, NZN, 2 * FLOOR, ROOF, T_W, "M_render_white", False, f2, top=False)
    xf, _ = wall_frame(NX1, NZN, NX0, NZN)
    with B.frame(xf):
        B.box(-0.01, 0.0, 0.0, NX1 - NX0 + 0.01, 0.6, 0.02, "M_render_plinth", skip="nb")
        # the tall narrow window strip of the east stair, one pane per storey
        for k in range(3):
            interior_quad(B, NX1 - 13.3, NX1 - 12.7, k * FLOOR + 0.6, (k + 1) * FLOOR - 0.2, 0.025, ("M_window_office", 490 + k, 0.5))
            A.frame_rect(B, NX1 - 13.36, NX1 - 12.64, k * FLOOR + 0.54, (k + 1) * FLOOR - 0.14, 0.0, 0.05, 0.06, "M_plastic_black")
        A.downpipe(B, 0.4, 0.0, ROOF)
    for (ax, az, bx, bz) in ((NX0, NZN, NX0, WZN), (NX1, WZN, NX1, NZN)):
        xf, L = wall_frame(ax, az, bx, bz)
        with B.frame(xf):
            B.box(-0.01, 0.0, 0.0, L + 0.01, 0.6, 0.02, "M_render_plinth", skip="nb")
    bays(B)


def bays(B):
    """the three single-storey bays on the rue Voltaire face (VOLT_GF): back offices west and east, the entrance in
    the middle with its black-glass "KB1" canopy"""
    B.use("volt_facade_n")
    B.use_col("COL_voltaire")
    for i, (x0, x1, zn) in enumerate(BAYS_N):
        mid = i == 1
        with B.ground_at(0.0):
            for (ax, az, bx, bz) in ((x0, zn, x0, NZN), (x1, NZN, x1, zn)):
                V.fac(B, ax, az, bx, bz, 0.0, FLOOR + 0.3, 0.15, "M_render_white", V.WALL_IN if mid else False, (),
                      top=True, mat_top="M_zinc", ends=False, base_in=V.SKIRT if mid else None)
            if mid:
                ops = [Opening(0.55, x1 - x0 - 0.55, 0.0, 2.6, "glassdoor", leaves=2, transom=None)]
                ops.append(Opening(0.55, x1 - x0 - 0.55, 2.62, 3.35, "window", frame="M_plastic_black", cols=2,
                                   glass="M_glass_clear", depth=0.1, sill=None))
            else:
                ops = [V.ext_win((x1 - x0) * f, 1.7, 0.9, 2.8, 500 + i * 3 + k, lit=0.4, sill="M_concrete", cols=2)
                       for k, f in enumerate((0.27, 0.73))]
            V.fac(B, x1, zn, x0, zn, 0.0, FLOOR + 0.3, 0.15, "M_render_white", V.WALL_IN if mid else False, ops,
                  top=True, mat_top="M_zinc", ends=False, base_in=V.SKIRT if mid else None)
            B.box(x0, FLOOR - 0.2, zn, x1, FLOOR + 0.05, NZN, "M_roof_gravel", skip="nsewb")
        if mid:
            # black-glass canopy box with the white "KB1" code over the rue Voltaire doors
            cz0, cz1 = zn - 1.6, zn
            B.box(x0 - 0.25, 2.95, cz0, x1 + 0.25, 3.55, cz1, "M_canopy_black")
            with B.at((x0 + x1) / 2, 3.25, cz0 - 0.004, math.pi):
                B.text("KB1", V_font("bold"), 0.32, "M_plate_white", align="CENTER", valign="CENTER", depth=0.015)
            B.box((x0 + x1) / 2 - 0.2, 2.94, cz0 + 0.5, (x0 + x1) / 2 + 0.2, 2.95, cz0 + 0.9, "M_light_warm", skip="t")
    V.light(B, "kb1_north", (BAYS_N[1][0] + BAYS_N[1][1]) / 2, 2.7, BAYS_N[1][2] - 0.9, K(3000), 1.0, 6.0)


# ------------------------------------------------------------------ partitions kept from the old plan
def partitions(B):
    """the old building's walls that now stand inside: the back of the lobby (accueil, elevator), the stair, the
    walls closing the back offices, the entrance hall to the rue Voltaire doors (V3, V4; the spot moves to z -32)"""
    B.use("volt_gf")
    B.use_col("COL_voltaire")
    W = V.WALL_IN
    with B.ground_at(0.0):
        # back of the lobby, z -26.15 (walked east -> west, the lobby on the inside): elevator, the passage to the hall,
        # a glass door into it beside the accueil
        u = lambda x: 12.85 - x
        ops = [Opening(u(7.95), u(6.25), 0.0, 2.3, "blank"),
               Opening(u(-4.5), u(-6.5), 0.0, 2.35, "passage"),
               Opening(u(0.35), u(-1.05), 0.0, 2.6, "glassdoor", leaves=1, transom=None)]
        V.fac(B, 12.85, -26.15, -17.85, -26.15, 0.0, FLOOR, T_W, W, W, ops, top=False, base_in=V.SKIRT, base_out=V.SKIRT)
        # west wall of the old north part and the hidden west strip's south wall
        V.fac(B, -18.15, -26.15, -18.15, -16.15, 0.0, FLOOR, T_W, False, W, (), top=False, base_in=V.SKIRT)
        V.fac(B, -18.15, WZN, NX0, WZN, 0.0, FLOOR, T_W, False, W, (), top=False, base_in=V.SKIRT)
        # the stair's east wall, x 13.15 (painted on both sides: the lobby wraps round its south end)
        V.fac(B, 13.15, -11.85, 13.15, -26.15, 0.0, FLOOR, T_W, W, W, (), top=False, base_in=V.SKIRT, base_out=V.SKIRT)
        V.fac(B, NX1, WZN, 13.15, WZN, 0.0, FLOOR, T_W, False, W, (), top=False, base_in=V.SKIRT)
        # the entrance hall
        V.fac(B, HALL[0], NZN, HALL[0], -26.15, 0.0, FLOOR, 0.15, False, W, (), top=False, base_in=V.SKIRT)
        V.fac(B, HALL[1], -26.15, HALL[1], NZN, 0.0, FLOOR, 0.15, False, W, (), top=False, base_in=V.SKIRT)
        # the wing's end walls on 13-17 rue Pasteur and ARPEJ (party walls: only the lobby side shows)
        V.fac(B, WX0, WZN, WX0, WZS, 0.0, FLOOR, T_W, False, W, (), top=False, base_in=V.SKIRT)
        V.fac(B, WX1, WZS, WX1, WZN, 0.0, FLOOR, T_W, False, W, (), top=False, base_in=V.SKIRT)
    turnstiles(B)
    B.use("volt_f1")
    with B.ground_at(F1):
        # first floor: the corridor's west end, SM14's wall to the hidden part of the wing, the landing's north wall,
        # the stair's east wall
        V.fac(B, -18.15, -15.925, -18.15, -12.15, F1, F1 + FLOOR, T_W, False, "M_paint_warm", (), top=False)
        V.fac(B, NX0 + T_W, -15.925, -17.85, -15.925, F1, V.CEIL1, 0.15, False, "M_paint_white", (), top=False,
              base_in=V.SKIRT)
        V.fac(B, 13.15, -26.0, 8.075, -26.0, F1, F1 + FLOOR, 0.15, False, "M_paint_white", (), top=False, base_in=V.SKIRT)
        V.fac(B, 13.15, -11.85, 13.15, -26.15, F1, F1 + FLOOR, T_W, False, "M_paint_white", (), top=False, base_in=V.SKIRT)


def turnstiles(B):
    """badge turnstiles across the entrance hall, the wide gate standing open"""
    z0, z1 = -29.4, -28.2
    posts = (-6.45, -5.3, -2.35, -1.2, -0.05)
    for x in posts:
        B.box(x - 0.13, 0.0, z0, x + 0.13, 1.0, z1, "M_steel")
        B.box(x - 0.14, 1.0, z0 - 0.01, x + 0.14, 1.04, z1 + 0.01, "M_plastic_black")
        B.box(x - 0.08, 1.04, z1 - 0.3, x + 0.08, 1.06, z1 - 0.12, "M_led_green")
        B.cbox(x - 0.13, 0.0, z0, x + 0.13, 1.1, z1)
    for (a, b) in ((-6.32, -5.43), (-2.22, -1.33), (-1.07, -0.18)):
        B.quad((a, 0.35, (z0 + z1) / 2), (b, 0.35, (z0 + z1) / 2), (b, 1.55, (z0 + z1) / 2), (a, 1.55, (z0 + z1) / 2),
               "M_glass_partition", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        B.cbox(a, 0.0, (z0 + z1) / 2 - 0.03, b, 1.6, (z0 + z1) / 2 + 0.03)
    # the accessible gate (x -5.17 .. -2.48) swung open toward the doors
    with B.at(-5.17, 0.0, (z0 + z1) / 2, -math.pi * 0.42):
        B.quad((0.0, 0.3, 0.0), (0.9, 0.3, 0.0), (0.9, 1.55, 0.0), (0.0, 1.55, 0.0), "M_glass_partition",
               uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        B.box(0.0, 1.5, -0.02, 0.9, 1.56, 0.02, "M_alu_silver")


# ------------------------------------------------------------------ roofs: the open wing terrace, the covered one
def roofs(B):
    B.use("volt_roof")
    B.use_col("COL_voltaire")
    with B.ground_at(ROOF):
        B.box(WX0 + T_W, ROOF - 0.3, WZN, WX1 - T_W, ROOF, WZS - T_W, "M_roof_gravel", skip="nsewb", sub=5.0)
        # the open part of the 3rd-floor terrace on the wing (V12: white parasols and tables at z -8..-12)
        B.box(-19.0, ROOF, -13.6, 9.0, ROOF + 0.08, -7.2, "M_wood_crate", skip="b", sub=3.0)
        for (x, z) in ((-15.0, -9.3), (-9.0, -11.4), (-3.0, -9.3), (3.0, -11.4)):
            parasol(B, x, ROOF + 0.08, z)
        with B.frame(wall_frame(-19.0, -7.2, 9.0, -7.2)[0]):
            A.glass_railing(B, 0.0, 28.0, ROOF + 0.08, col_group=False)
        # the north block's roof under the box: the covered terrace (V12; furnished by V2-37)
        B.box(NX0 + T_W, ROOF - 0.3, NZN + T_W, NX1 - T_W, ROOF, WZN, "M_resin_grey", skip="nsewb", sub=4.0)
        for (ax, az, bx, bz) in ((NX0, WZN, NX0, NZN), (NX0, NZN, NX1, NZN), (NX1, NZN, NX1, WZN)):
            xf, L = wall_frame(bx, bz, ax, az)
            with B.frame(xf):
                A.parapet(B, L, ROOF, 1.1, 0.25, "M_concrete", inner_mat="M_concrete")
        for x in (WX0, WX1):
            B.box(x - 0.15, ROOF, WZN, x + 0.15, PARA, WZS, "M_render_white", skip="b")


def parasol(B, x, y, z):
    """white market parasol over a small white table"""
    B.cyl(x, y, z, 0.03, 2.3, "M_paint_metal_white", seg=8)
    B.cyl(x, y + 2.05, z, 1.25, 0.32, "M_fabric_grey" if False else "M_paint_metal_white", seg=10, r2=0.04, caps=(True, False))
    B.cyl(x, y, z, 0.3, 0.04, "M_paint_metal_white", seg=10)
    B.cyl(x + 0.6, y, z + 0.4, 0.035, 0.72, "M_paint_metal_white", seg=6)
    B.cyl(x + 0.6, y + 0.72, z + 0.4, 0.35, 0.03, "M_paint_metal_white", seg=12)


# ------------------------------------------------------------------ the 2016-18 box (V5-V8)
# the rue Voltaire face, u from its east end (the wooden corner covers u 0 .. 3.2): windows, the tilted red balcony
# boxes in front of some of them, the blue vents (noise baffles) between them; (u, storey[, tilt])
NORTH_WINDOWS = ((4.6, 0), (7.4, 0), (13.0, 0), (19.5, 0), (24.0, 0), (31.0, 0), (36.4, 0), (43.0, 0), (48.0, 0),
                 (5.6, 1), (9.5, 1), (15.8, 1), (22.0, 1), (27.6, 1), (33.6, 1), (39.0, 1), (45.5, 1),
                 (4.8, 2), (8.2, 2), (12.5, 2), (18.4, 2), (25.6, 2), (30.0, 2), (35.0, 2), (41.4, 2), (47.0, 2))
BALCONIES = ((7.4, 0, 0.18), (19.5, 0, -0.14), (36.4, 0, 0.1), (9.5, 1, -0.2), (27.6, 1, 0.16), (45.5, 1, -0.1),
             (12.5, 2, 0.12), (30.0, 2, -0.18), (41.4, 2, 0.2))
VENTS = ((10.4, 0), (28.0, 0), (40.0, 0), (12.6, 1), (18.9, 1), (36.3, 1), (21.9, 2), (44.2, 2))


def box(B):
    B.use("volt_ext")
    B.use_col("COL_voltaire")
    P = RAISE
    with B.ground_at(0.0):
        # soffit (grey ribbed steel) with round downlights over the terrace and the yards
        for f in PG.grid_pieces(P, 4.0):
            B.face([(x, BOX0, z) for x, z in f][::-1], "M_soffit_ribbed")
        for x in range(-26, 22, 4):
            for z in (-19.0, -23.0, -27.0, -31.0):
                if PG.inside_poly((x + 0.5, z), P) and PG.poly_dist((x + 0.5, z), P) > 1.0:
                    B.box(x + 0.35, BOX0 - 0.012, z - 0.15, x + 0.65, BOX0, z + 0.15, "M_light_warm", skip="t")
        for i, (a, b) in enumerate(PG.edges(P)):
            L = PG.length(a, b)
            n = PG.outward(a, b)
            south, north = n[1] > 0.7, n[1] < -0.7
            if south:
                mat, band = "M_trespa", "M_alu_anthracite"
                ops = [V.ext_win(1.2 + 2.4 * j, 0.9, BOX0 + k * BOX_ST + 0.5, BOX0 + k * BOX_ST + 2.4, 600 + k * 31 + j,
                                 lit=0.55, sill=None, cols=1, depth=0.14)
                       for k in range(3) for j in range(int((L - 0.6) // 2.4)) if (j + k) % 3 != 1]
            elif north:
                mat, band = "M_metal_cobalt", "M_metal_blue_light"
                ops = [V.ext_win(u, 1.7, BOX0 + k * BOX_ST + 0.55, BOX0 + k * BOX_ST + 2.15, 700 + k * 29 + j, lit=0.5,
                                 sill=None, cols=2, depth=0.12, frame="M_paint_metal_dark")
                       for j, (u, k) in enumerate(NORTH_WINDOWS) if u < L - 1.0]
                ops += [Opening(u - 0.7, u + 0.7, BOX0 + k * BOX_ST + 0.6, BOX0 + k * BOX_ST + 2.0, "blank") for u, k in VENTS]
            else:
                # east: against ARPEJ except over its light court (u 2.5 .. 9.3); west: against 13-17 rue Pasteur
                # (19.5 m) on its last 7 m
                east = a[0] > 20.0
                us = (4.0, 7.2) if east else (3.5, 9.0, 14.5, 19.0)
                mat, band = "M_metal_cobalt", "M_metal_blue_light"
                ops = [V.ext_win(u, 1.6, BOX0 + k * BOX_ST + 0.55, BOX0 + k * BOX_ST + 2.15, 760 + i * 17 + k * 5 + j,
                                 lit=0.45, sill=None, cols=2, depth=0.12, frame="M_paint_metal_dark")
                       for k in range(3) for j, u in enumerate(us)
                       if u < L - 1.5 and (east or k == 2 or u < 13.5)]
            V.fac(B, a[0], a[1], b[0], b[1], BOX0, BOX1, 0.3, mat, False, ops, top=False, ends=False)
            xf, _ = wall_frame(a[0], a[1], b[0], b[1])
            with B.frame(xf):
                for k in (1, 2):
                    B.box(-0.02, BOX0 + k * BOX_ST - 0.07, 0.0, L + 0.02, BOX0 + k * BOX_ST + 0.07, 0.05, band)
                B.box(-0.03, BOX0 - 0.35, -0.3, L + 0.03, BOX0, 0.06, "M_alu_anthracite")      # edge beam under the box
                A.parapet(B, L, BOX1, 0.45, 0.25, mat, inner_mat="M_concrete")
                if north:
                    # the light wooden corner at the east end, the vents, the tilted red balcony boxes (fire access)
                    B.box(-0.02, BOX0, 0.0, 3.2, BOX1 + 0.45, 0.06, "M_trespa")
                    for (uu, k) in VENTS:
                        y = BOX0 + k * BOX_ST + 0.6
                        B.box(uu - 0.7, y, -0.12, uu + 0.7, y + 1.4, -0.1, "M_room_sleeve", skip="s")
                        for s in range(8):
                            B.box(uu - 0.68, y + 0.08 + s * 0.165, -0.11, uu + 0.68, y + 0.16 + s * 0.165, 0.02,
                                  "M_metal_cobalt_vent")
                    for (uu, k, tilt) in BALCONIES:
                        if uu < L - 1.0:
                            balcony(B, uu, BOX0 + k * BOX_ST, tilt)
                if south:
                    # steel mesh for climbers on the Trespa (Tragin), cables every 0.8 m
                    for k in range(int(L / 0.8)):
                        uu = 0.4 + k * 0.8
                        B.box(uu - 0.008, BOX0 + 0.1, 0.32, uu + 0.008, BOX1 + 0.3, 0.336, "M_steel")
                    for y in (BOX0 + 0.1, BOX0 + BOX_ST, BOX0 + 2 * BOX_ST, BOX1 + 0.3):
                        B.box(0.0, y - 0.02, 0.06, L, y + 0.02, 0.34, "M_steel")
        B.prism(P, BOX1 - 0.3, BOX1, "M_roof_gravel", top=True, sides=False)
    columns(B)
    for x, z in ((-21.0, -21.5), (-6.0, -21.5), (8.0, -21.5)):
        V.light(B, "terrace_%+03d" % int(x), x, BOX0 - 0.3, z, K(3000), 1.0, 10.0)


def balcony(B, u, y, tilt):
    """a small square red-framed balcony box standing out from the cobalt face, turned off true"""
    w, d, h = 1.45, 0.95, 1.1
    with B.at(u, y, 0.0, tilt):
        B.box(-w / 2, 0.0, 0.0, w / 2, 0.1, d, "M_paint_metal_red")
        for s in (-1, 1):
            B.box(s * w / 2 - 0.05, 0.1, 0.0, s * w / 2 + 0.05, h + 0.1, d, "M_paint_metal_red", skip="n")
        B.box(-w / 2, h + 0.05, 0.0, w / 2, h + 0.15, d, "M_paint_metal_red", skip="n")
        B.box(-w / 2, 0.95, d - 0.06, w / 2, 1.0, d, "M_paint_metal_red")
        for k in range(7):
            x = -w / 2 + 0.12 + k * (w - 0.24) / 6
            B.box(x - 0.012, 0.1, d - 0.04, x + 0.012, 0.95, d - 0.02, "M_paint_metal_red")


def columns(B):
    """the white colonnade with blue bases under the north edge of the box, the pillars through the yards and
    the white steel columns of the covered terrace"""
    B.use("volt_ext")
    (ax, az), (bx, bz) = (-28.5, -37.4), (23.6, -34.5)
    for i in range(8):
        t = (i + 0.5) / 8
        x = ax + (bx - ax) * t
        z = az + (bz - az) * t + 0.75
        B.cyl(x, 0.0, z, 0.24, 0.75, "M_paint_column_blue", seg=14)
        B.cyl(x, 0.75, z, 0.2, BOX0 - 1.1, "M_paint_column", seg=14, caps=(False, False))
        B.cyl(x, BOX0 - 0.35, z, 0.2, 0.35, "M_paint_column", seg=14, r2=0.34, caps=(False, False))
    for (x, z) in ((-25.2, -22.5), (-25.2, -30.5), (18.4, -22.5), (18.4, -29.0)):
        B.box(x - 0.18, 0.0, z - 0.18, x + 0.18, BOX0, z + 0.18, "M_paint_column", skip="tb")
    for x in (-17.5, -10.5, -3.5, 3.5, 10.5):
        for z in (-20.5, -27.5):
            B.cyl(x, ROOF, z, 0.14, BOX0 - ROOF, "M_paint_column", seg=10, caps=(False, False))
            B.box(x - 0.3, BOX0 - 0.45, z - 0.12, x + 0.3, BOX0, z + 0.12, "M_paint_column")


# ------------------------------------------------------------------ rue Voltaire side: forecourt, yards
def north_side(B):
    """the planted forecourt under the box's overhang (V8: the columns stand on its edge, the public pavement runs
    outside them), the two yards with their gates on the property line"""
    B.use("volt_north")
    from campus_props_out import foliage
    rng = random.Random(23)
    with B.ground_at(0.0):
        # the yards and the forecourt round the north block and its bays (the lobby floor is inside it)
        court = [(WX0, WZN), (NX0, WZN), (NX0, NZN)]
        for (x0, x1, zn) in BAYS_N:
            court += [(x0, NZN), (x0, zn), (x1, zn), (x1, NZN)]
        court = PG.cw(court + [(NX1, NZN), (NX1, WZN), (WX1, WZN), (WX1, parcel_z(WX1)), (WX0, parcel_z(WX0))])
        for f in PG.grid_pieces(court, 4.0):
            B.face([(x, 0.0, z) for x, z in f], "M_court_slabs")
        # low planters with clipped shrubs along the face between the bays, the path to the doors kept clear
        for (x0, x1) in ((NX0 + 0.6, -13.6), (-7.0, -5.6), (-1.0, 0.3), (6.9, NX1 - 0.6)):
            z0, z1 = NZN - 1.3, NZN - 0.2
            B.box(x0, 0.0, z0, x1, 0.55, z1, "M_render_plinth", skip="b")
            B.box(x0 + 0.08, 0.55, z0 + 0.08, x1 - 0.08, 0.95, z1 - 0.08, "M_hedge", skip="b")
            x = x0 + 0.5
            while x < x1 - 0.3:
                foliage(B, (x, 1.05, (z0 + z1) / 2), (0.45, 0.25, 0.4), 4, 0.6, "M_leaves_plane", rng, bias=0.7)
                x += 1.1
        # the yards' gates on the property line (bars) and a bike shelter in the east yard
        for (x0, x1) in ((WX0 + 0.1, NX0 - 0.1), (NX1 + 0.1, WX1 - 0.1)):
            za, zb_ = parcel_z(x0), parcel_z(x1)
            n = int((x1 - x0) / 0.13)
            for k in range(n):
                x = x0 + (k + 0.5) * (x1 - x0) / n
                z = za + (zb_ - za) * (x - x0) / (x1 - x0)
                B.box(x - 0.012, 0.0, z - 0.02, x + 0.012, 2.1, z + 0.02, "M_paint_metal_dark")
            for y in (0.12, 2.05):
                B.seg_box(x0, za, x1, zb_, y, y + 0.05, 0.05, "M_paint_metal_dark")
        B.box(15.2, 0.0, -27.8, 21.6, 0.08, -24.0, "M_concrete", skip="b")
        for k in range(5):
            x = 15.8 + k * 1.3
            B.cyl(x, 0.0, -24.6, 0.025, 0.8, "M_steel", seg=6)
            B.cyl(x, 0.0, -27.2, 0.025, 0.8, "M_steel", seg=6)
            B.box(x - 0.025, 0.78, -27.2, x + 0.025, 0.82, -24.6, "M_steel")
    # the west yard is closed by a boundary wall where 13-17 rue Pasteur's party wall stops
    B.use("volt_north")
    with B.ground_at(0.0):
        B.box(WX0 - 0.25, 0.0, parcel_z(WX0), WX0, 2.6, -23.3, "M_concrete", skip="b")


# ------------------------------------------------------------------ camera blockers for the rooms nobody enters
def solids(B):
    B.use_col("COL_voltaire")
    c = lambda *a: B.cbox(*a)
    # ground floor: the back offices round the lobby
    c(NX0, 0.0, NZN, -18.15, FLOOR, WZN)
    c(-18.15, 0.0, NZN, HALL[0], FLOOR, -26.15)
    c(HALL[1], 0.0, NZN, NX1, FLOOR, -26.15)
    c(13.15, 0.0, -26.15, NX1, FLOOR, WZN)
    for (x0, x1, zn) in (BAYS_N[0], BAYS_N[2]):
        c(x0, 0.0, zn, x1, FLOOR, NZN)
    # first floor: the wing beside the corridor, the strip east of the stair, the back of the landing
    c(WX0, FLOOR, WZS, WX1, ROOF, -12.15)
    c(WX0, FLOOR, -12.15, -18.15, ROOF, WZN)
    c(13.15, FLOOR, -12.15, WX1, ROOF, WZN)
    c(13.15, FLOOR, WZN, NX1, ROOF, NZN)
    c(8.075, FLOOR, -26.0, 13.15, F1 + FLOOR, NZN)
    # second floor over everything
    c(WX0, V.CEIL1, -12.15, WX1, ROOF, WZN)
    c(NX0, V.CEIL1, WZN, NX1, ROOF, NZN)
    # the box
    B.cprism(RAISE, BOX0, BOX1 + 0.45)
