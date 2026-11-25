"""Outdoor props: street lamps, bollards, plane trees, Paris bins, parked cars, the Velib' dock, mopeds,
road barriers, signs, Gally planters with birches, picnic tables, courtyard pendants."""
import math, random
from mathutils import Vector, Matrix
import campus_geo as G
from campus_props import chbox, ring, wheel_x, bulb, CM_font
from campus_mat import mat as defmat

PI = math.pi
defmat("M_lamp_grey", None, color="#3c4146", rough=0.45, metal=0.6, grime="ext", macro=0.03)
defmat("M_bollard", None, color="#4a3427", rough=0.55, metal=0.4, grime="ext", macro=0.04)   # dark-brown cast iron
defmat("M_planter_stencil", None, color="#3b2a18", rough=0.9)


# ------------------------------------------------------------------ helpers
def taper_tube(B, path, r0, r1, mat, seg=10, cap_end=True):
    """tube along a polyline with linearly tapering radius (smooth normals)"""
    path = [Vector(p) for p in path]
    total = sum((path[i + 1] - path[i]).length for i in range(len(path) - 1)) or 1.0
    rings, acc = [], 0.0
    for i, p in enumerate(path):
        if i > 0:
            acc += (path[i] - path[i - 1]).length
        t = (path[1] - path[0]) if i == 0 else ((path[-1] - path[-2]) if i == len(path) - 1 else (path[i + 1] - path[i - 1]))
        t.normalize()
        up = Vector((0, 1, 0)) if abs(t.y) < 0.95 else Vector((1, 0, 0))
        u = t.cross(up).normalized()
        v = u.cross(t).normalized()
        r = r0 + (r1 - r0) * acc / total
        rings.append([(p + (u * math.cos(2 * PI * k / seg) + v * math.sin(2 * PI * k / seg)) * r,
                       (u * math.cos(2 * PI * k / seg) + v * math.sin(2 * PI * k / seg)), acc) for k in range(seg)])
    tile = 1.0
    for i in range(len(rings) - 1):
        for k in range(seg):
            k2 = (k + 1) % seg
            a0, a1, b1, b0 = rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]
            uv = [(k / seg, a0[2] / tile), ((k + 1) / seg, a0[2] / tile), ((k + 1) / seg, b0[2] / tile), (k / seg, b0[2] / tile)]
            B.face([a0[0], a1[0], b1[0], b0[0]], mat, uvs=uv, smooth=True, normals=[a0[1], a1[1], b1[1], b0[1]])
    if cap_end:
        B.face([q[0] for q in rings[-1]], mat)


def foliage(B, center, radii, n, size, mat, rng, bias=0.55, flat=0.35):
    """alpha-cut leaf-cluster cards scattered in an ellipsoid crown; normals point away from the crown centre
    so the crown shades like a volume"""
    c = Vector(center)
    for i in range(n):
        while True:
            d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
            if 0.2 < d.length <= 1.0:
                break
        d = d.normalized() * (bias + (1 - bias) * rng.random())
        p = c + Vector((d.x * radii[0], d.y * radii[1], d.z * radii[2]))
        nrm = Vector((d.x / radii[0], d.y / radii[1] * 0.7 + 0.25, d.z / radii[2])).normalized()
        yaw = rng.uniform(0, 2 * PI)
        tilt = rng.uniform(-flat, flat)
        s = size * rng.uniform(0.75, 1.25)
        right = Vector((math.cos(yaw), 0, math.sin(yaw))) * (s / 2)
        up = Vector((-math.sin(yaw) * math.sin(tilt), math.cos(tilt), math.cos(yaw) * math.sin(tilt))).normalized() * (s / 2)
        q = rng.randrange(4)
        uv = ((q % 2) * 0.5 + 0.003, (q // 2) * 0.5 + 0.003, (q % 2) * 0.5 + 0.497, (q // 2) * 0.5 + 0.497)
        B.card(p, right, up, mat, uv=uv, normal=tuple(nrm))


def grass_tuft(B, x, y, z, h, rng, n=3):
    for k in range(n):
        a = rng.uniform(0, PI)
        r = Vector((math.cos(a), 0, math.sin(a))) * (h * 0.45)
        q = rng.randrange(2)
        B.card((x, y + h / 2, z), r, (0, h / 2, 0), "M_grass", uv=(q * 0.5, 0.0, q * 0.5 + 0.5, 1.0), normal=(0, 1, 0))


# ------------------------------------------------------------------ street
def street_lamp(B):
    """LED street light: tapered pole, arm reaching towards +Z, luminaire at y 5.0 / z 0.8"""
    B.cyl(0, 0.0, 0, 0.16, 0.06, "M_lamp_grey", seg=16)
    B.cyl(0, 0.06, 0, 0.13, 0.6, "M_lamp_grey", seg=16, r2=0.1)
    B.cyl(0, 0.66, 0, 0.085, 4.4, "M_lamp_grey", seg=14, r2=0.06)
    B.tube([(0, 5.0, 0), (0, 5.22, 0.08), (0, 5.3, 0.3), (0, 5.24, 0.62), (0, 5.12, 0.82)], 0.045, "M_lamp_grey", seg=10)
    with B.at(0, 5.05, 0.9, 0.0, 0.08):
        chbox(B, -0.16, -0.06, -0.38, 0.16, 0.02, 0.38, "M_lamp_grey", c=0.06)
        B.rect((-0.13, -0.061, -0.33), (0.26, 0, 0), (0, 0, 0.66), "M_light_street")
    B.box(-0.11, 2.6, 0.06, 0.11, 2.95, 0.075, "M_plate_white")
    B.cbox(-0.14, 0.0, -0.14, 0.14, 5.3, 0.14)


def bollard(B):
    B.cyl(0, 0.0, 0, 0.068, 0.78, "M_bollard", seg=12, r2=0.058)
    B.cyl(0, 0.62, 0, 0.072, 0.05, "M_bollard", seg=12)
    B.cyl(0, 0.78, 0, 0.058, 0.04, "M_bollard", seg=12, r2=0.04)
    B.sphere(0, 0.84, 0, 0.042, "M_bollard", seg=10, rings=5)
    B.cbox(-0.08, 0.0, -0.08, 0.08, 0.95, 0.08)


def bin_paris(B):
    """Paris 'Bagatelle' bin: post, hoop and a translucent bag"""
    B.cyl(0, 0.0, -0.27, 0.03, 0.95, "M_paint_metal_green", seg=10)
    ring(B, 0, 0.86, 0, 0.245, 0.02, "M_paint_metal_green", seg=18)
    B.box(-0.03, 0.82, -0.27, 0.03, 0.9, -0.22, "M_paint_metal_green")
    B.cyl(0, 0.24, 0, 0.2, 0.6, "M_bin_bag", seg=16, r2=0.235, caps=(True, False))
    B.cyl(0, 0.24, 0, 0.19, 0.58, "M_bin_bag", seg=16, r2=0.225, caps=(False, False))
    B.cbox(-0.26, 0.0, -0.3, 0.26, 0.95, 0.26)


def road_barrier(B):
    """red/white works barrier (barriere de chantier), 1.6 m, with a flasher"""
    for s in (-1, 1):
        x = s * 0.7
        B.box(x - 0.025, 0.0, -0.3, x + 0.025, 0.05, 0.3, "M_plastic_black")
        B.box(x - 0.02, 0.05, -0.02, x + 0.02, 1.05, 0.02, "M_paint_metal_white")
    for k in range(8):
        x0 = -0.8 + k * 0.2
        B.box(x0, 0.75, -0.015, x0 + 0.2, 1.0, 0.015, "M_barrier_red" if k % 2 == 0 else "M_plastic_white")
    for k in range(8):
        x0 = -0.8 + k * 0.2
        B.box(x0, 0.35, -0.015, x0 + 0.2, 0.5, 0.015, "M_plastic_white" if k % 2 == 0 else "M_barrier_red")
    B.box(0.55, 1.0, -0.04, 0.7, 1.05, 0.04, "M_plastic_black")
    B.cyl(0.625, 1.05, 0, 0.06, 0.12, "M_led_amber", seg=10)
    B.cbox(-0.8, 0.0, -0.3, 0.8, 1.1, 0.3)


def bike_rack(B):
    path = [(-0.35, 0.0, 0)]
    for i in range(9):
        a = PI * i / 8
        path.append((-0.35 * math.cos(a) * 0.92, 0.55 + math.sin(a) * 0.25, 0))
    path.append((0.35, 0.0, 0))
    B.tube(path, 0.03, "M_steel_dark", seg=8)
    B.cbox(-0.38, 0.0, -0.04, 0.38, 0.8, 0.04)


def _sign_plate(B, kind):
    """round sign face at local origin facing +Z (radius 0.3)"""
    def disc(r, mat, z, n=28):
        B.face([(math.cos(2 * PI * i / n) * r, math.sin(2 * PI * i / n) * r, z) for i in range(n)], mat)
    B.cyl_axis((0, 0, -0.012), (0, 0, 0.0), 0.31, "M_zinc", seg=28)
    if kind == "no_parking":
        disc(0.3, "M_sign_red", 0.001)
        disc(0.24, "M_sign_blue", 0.002)
        a = PI / 4
        w = 0.035
        B.quad((-math.cos(a) * 0.24 + w, -math.sin(a) * 0.24 - w, 0.003), (math.cos(a) * 0.24 + w, math.sin(a) * 0.24 - w, 0.003),
               (math.cos(a) * 0.24 - w, math.sin(a) * 0.24 + w, 0.003), (-math.cos(a) * 0.24 - w, -math.sin(a) * 0.24 + w, 0.003), "M_sign_red")
    elif kind == "zone30":
        disc(0.3, "M_sign_red", 0.001)
        disc(0.24, "M_plate_white", 0.002)
        with B.at(0, -0.1, 0.003):
            B.text("30", CM_font("black"), 0.3, "M_plastic_black", align="CENTER", valign="BOTTOM")
    elif kind == "one_way":
        disc(0.3, "M_sign_red", 0.001)
        B.box(-0.2, -0.05, 0.0, 0.2, 0.05, 0.004, "M_plate_white")
    # back of the plate
    B.face([(math.cos(-2 * PI * i / 28) * 0.31, math.sin(-2 * PI * i / 28) * 0.31, -0.013) for i in range(28)], "M_zinc")


def sign_post(B, kind="no_parking"):
    B.cyl(0, 0.0, 0, 0.03, 2.75, "M_zinc", seg=10)
    with B.at(0, 2.45, 0.045):
        _sign_plate(B, kind)
    B.cbox(-0.05, 0.0, -0.05, 0.05, 2.7, 0.05)


def parking_meter(B):
    chbox(B, -0.2, 0.0, -0.15, 0.2, 0.08, 0.15, "M_lamp_grey", c=0.03)
    chbox(B, -0.16, 0.08, -0.12, 0.16, 1.45, 0.12, "M_lamp_grey", c=0.03)
    with B.at(0, 1.45, 0.0, 0.0, 0.35):
        chbox(B, -0.17, 0.0, -0.14, 0.17, 0.08, 0.14, "M_lamp_grey", c=0.03)
    B.box(-0.11, 1.1, 0.12, 0.11, 1.32, 0.125, "M_screen_off")
    B.box(-0.1, 1.12, 0.125, 0.1, 1.3, 0.127, "M_led_green")
    B.box(-0.06, 0.95, 0.12, 0.06, 1.0, 0.13, "M_plastic_black")
    B.box(-0.12, 1.36, 0.12, 0.0, 1.42, 0.125, "M_sign_blue")
    with B.at(-0.06, 1.37, 0.126):
        B.text("P", CM_font("black"), 0.05, "M_plate_white", align="CENTER", valign="BOTTOM")
    B.cbox(-0.2, 0.0, -0.15, 0.2, 1.6, 0.15)


def utility_cabinet(B):
    B.box(-0.55, 0.0, -0.2, 0.55, 0.12, 0.2, "M_concrete")
    chbox(B, -0.5, 0.12, -0.17, 0.5, 1.3, 0.17, "M_paint_metal_green", c=0.02)
    B.box(-0.52, 1.3, -0.19, 0.52, 1.34, 0.19, "M_paint_metal_green")
    for s in (-1, 1):
        B.box(s * 0.01 - (0.47 if s < 0 else 0), 0.18, 0.17, s * 0.47 + (0.01 if s < 0 else 0) if s > 0 else -0.01, 1.25, 0.175, "M_paint_metal_green")
    for k in range(6):
        B.box(-0.35, 1.0 + k * 0.03, 0.172, 0.35, 1.012 + k * 0.03, 0.178, "M_room_sleeve")
    B.box(-0.06, 0.7, 0.175, -0.03, 0.8, 0.19, "M_alu_silver")
    B.box(0.03, 0.7, 0.175, 0.06, 0.8, 0.19, "M_alu_silver")
    B.cbox(-0.55, 0.0, -0.2, 0.55, 1.34, 0.2)


# ------------------------------------------------------------------ trees
def tree_plane(B):
    """London plane on the sidewalk: tree grate, mottled trunk, crown pruned away from the facades
    (crown pushed towards local +Z = the road once placed)"""
    rng = random.Random(21)
    # grate
    B.box(-0.65, -0.01, -0.65, 0.65, 0.0, 0.65, "M_soil")
    for k in range(5):
        r = 0.2 + k * 0.1
        B.box(-r, 0.0, -r, r, 0.012, -r + 0.03, "M_cast_iron")
        B.box(-r, 0.0, r - 0.03, r, 0.012, r, "M_cast_iron")
        B.box(-r, 0.0, -r, -r + 0.03, 0.012, r, "M_cast_iron")
        B.box(r - 0.03, 0.0, -r, r, 0.012, r, "M_cast_iron")
    B.box(-0.65, 0.0, -0.65, 0.65, 0.014, -0.6, "M_cast_iron")
    B.box(-0.65, 0.0, 0.6, 0.65, 0.014, 0.65, "M_cast_iron")
    B.box(-0.65, 0.0, -0.6, -0.6, 0.014, 0.6, "M_cast_iron")
    B.box(0.6, 0.0, -0.6, 0.65, 0.014, 0.6, "M_cast_iron")
    # trunk + main limbs
    trunk = [(0, 0.0, 0), (0.03, 1.2, 0.05), (-0.02, 2.4, 0.12), (0.02, 3.3, 0.25)]
    taper_tube(B, trunk, 0.2, 0.15, "M_bark_plane", seg=12, cap_end=False)
    top = Vector(trunk[-1])
    crown_c = (0.0, 6.0, 1.0)
    for k in range(5):
        a = 2 * PI * k / 5 + 0.4
        end = Vector((math.cos(a) * 1.8, 5.6 + rng.uniform(-0.5, 0.9), 1.0 + math.sin(a) * 1.5))
        mid = top.lerp(end, 0.5) + Vector((0, 0.5, 0))
        taper_tube(B, [top, mid, end], 0.12, 0.04, "M_bark_plane", seg=8)
        for j in range(2):
            e2 = end + Vector((rng.uniform(-1.0, 1.0), rng.uniform(0.3, 1.4), rng.uniform(-0.9, 0.9)))
            taper_tube(B, [end, end.lerp(e2, 0.5) + Vector((0, 0.2, 0)), e2], 0.04, 0.015, "M_bark_plane", seg=6)
    foliage(B, crown_c, (2.6, 2.3, 2.1), 260, 1.05, "M_leaves_plane", rng, bias=0.5)
    B.cbox(-0.25, 0.0, -0.25, 0.25, 3.2, 0.25)


def birch(B, y0, rng, h=4.0):
    lean = Vector((rng.uniform(-0.25, 0.25), 0, rng.uniform(-0.2, 0.2)))
    pts = [Vector((0, y0, 0))]
    for k in range(1, 6):
        t = k / 5
        pts.append(Vector((lean.x * t * t + rng.uniform(-0.03, 0.03), y0 + h * t, lean.z * t * t + rng.uniform(-0.03, 0.03))))
    taper_tube(B, pts, 0.075, 0.018, "M_bark_birch", seg=10)
    for k in range(7):
        t = 0.45 + 0.5 * k / 7
        p = pts[0].lerp(pts[-1], t)
        a = rng.uniform(0, 2 * PI)
        e = p + Vector((math.cos(a) * 0.8, 0.6 + rng.uniform(0, 0.5), math.sin(a) * 0.8))
        taper_tube(B, [p, p.lerp(e, 0.5) + Vector((0, 0.15, 0)), e], 0.022, 0.006, "M_bark_birch", seg=5)
    foliage(B, (lean.x * 0.8, y0 + h * 0.72, lean.z * 0.8), (1.05, 1.45, 1.05), 90, 0.62, "M_leaves_birch", rng, bias=0.45, flat=0.6)


def planter_birch(B):
    """Gally wooden crate planter (2.4 x 1.2 x 0.75) with a birch and grasses (old Outdoor.crate + birch + grass)"""
    rng = random.Random(33)
    w, d, h = 2.4, 1.2, 0.75
    for s in (-1, 1):
        for k in range(5):
            y = 0.02 + k * 0.146
            B.box(-w / 2, y, s * d / 2 - (0.025 if s > 0 else 0), w / 2, y + 0.135, s * d / 2 + (0 if s > 0 else 0.025), "M_wood_crate")
            B.box(s * w / 2 - (0.025 if s > 0 else 0), y, -d / 2 + 0.025, s * w / 2 + (0 if s > 0 else 0.025), y + 0.135, d / 2 - 0.025, "M_wood_crate")
    for sx in (-1, 1):
        for sz in (-1, 1):
            B.box(sx * w / 2 - 0.05 * (sx > 0), 0.0, sz * d / 2 - 0.05 * (sz > 0), sx * w / 2 + 0.05 * (sx < 0), h + 0.02, sz * d / 2 + 0.05 * (sz < 0), "M_wood_crate")
    B.box(-w / 2 + 0.025, 0.66, -d / 2 + 0.025, w / 2 - 0.025, 0.7, d / 2 - 0.025, "M_soil", skip="b")
    for s in (-1, 1):
        with B.at(0.25, 0.3, s * (d / 2 + 0.002), 0.0 if s > 0 else PI):
            B.text("LES FERMES DE GALLY", CM_font("black"), 0.085, "M_planter_stencil", align="CENTER")
    birch(B, 0.7, rng)
    for k in range(16):
        grass_tuft(B, rng.uniform(-0.05, w / 2 - 0.15), 0.7, rng.uniform(-d / 2 + 0.12, d / 2 - 0.12), rng.uniform(0.35, 0.65), rng)
    B.cbox(-w / 2, 0.0, -d / 2, w / 2, 0.8, d / 2)
    B.cbox(-0.12, 0.8, -0.12, 0.12, 3.0, 0.12)


def picnic_table(B):
    for k in range(5):
        z0 = -0.4 + k * 0.162
        B.box(-1.0, 0.74, z0, 1.0, 0.78, z0 + 0.15, "M_wood_crate")
    for s in (-1, 1):
        for k in range(2):
            z0 = s * 0.62 - 0.14 + k * 0.145
            B.box(-1.0, 0.43, z0, 1.0, 0.46, z0 + 0.13, "M_wood_crate")
        x = s * 0.78
        for t in (-1, 1):
            with B.at(x, 0.0, 0.0, 0.0, t * 0.46):
                B.box(-0.04, 0.0, -0.04, 0.04, 0.86, 0.04, "M_wood_crate")
        B.box(x - 0.04, 0.38, -0.8, x + 0.04, 0.43, 0.8, "M_wood_crate")
        B.box(x - 0.04, 0.68, -0.42, x + 0.04, 0.74, 0.42, "M_wood_crate")
    B.box(-0.78, 0.25, -0.03, 0.78, 0.3, 0.03, "M_wood_crate")
    B.cbox(-1.0, 0.0, -0.8, 1.0, 0.8, 0.8)


def court_pendant(B):
    """pendant lamp hanging from the courtyard catenaries; origin = cable attachment (top)"""
    B.cyl(0, -1.0, 0, 0.004, 1.0, "M_plastic_black", seg=4, caps=(False, False))
    B.cyl(0, -1.25, 0, 0.26, 0.25, "M_paint_metal_dark", seg=20, r2=0.05, caps=(False, True))
    B.cyl(0, -1.252, 0, 0.255, 0.24, "M_paint_metal_white", seg=20, r2=0.045, caps=(False, False))
    B.sphere(0, -1.2, 0, 0.07, "M_light_string", seg=10, rings=6)


# ------------------------------------------------------------------ vehicles
def car(B, paint="M_car_blue", length=4.1, hatch=True, seed=1):
    """lofted car body (front towards +Z): stations along z, symmetric rings; glass where the ring crosses
    the greenhouse; roof flat at ~1.49 so the duck on the old car roof sits on it"""
    L = length
    zr, zf = -L / 2, L / 2
    wb = 2.55 if hatch else 2.7
    zw_r, zw_f = -wb / 2 + (0.0 if hatch else -0.05), wb / 2
    roof = 1.49
    # side silhouette (z -> top y) and cabin span
    if hatch:
        prof = [(zr, 0.6), (zr + 0.05, 0.86), (zr + 0.12, 1.0), (zr + 0.35, 1.38), (zr + 0.6, roof), (0.35, roof), (0.95, 1.06),
                (1.55, 0.92), (zf - 0.1, 0.78), (zf, 0.55)]
        cab0, cab1 = zr + 0.12, 0.95
    else:
        prof = [(zr, 0.62), (zr + 0.05, 0.9), (zr + 0.55, 0.98), (zr + 0.95, 1.06), (zr + 1.35, roof), (0.4, roof), (1.0, 1.05),
                (1.6, 0.92), (zf - 0.1, 0.78), (zf, 0.55)]
        cab0, cab1 = zr + 0.95, 1.0

    def top_at(z):
        for (a, ya), (b, yb) in zip(prof, prof[1:]):
            if a <= z <= b:
                t = (z - a) / (b - a) if b > a else 0
                return ya + (yb - ya) * t
        return prof[-1][1]

    def belt_at(z):
        return 0.98 if cab0 <= z <= cab1 else top_at(z)

    zs = sorted(set([zr, zr + 0.05, zr + 0.12, zr + 0.3] + [p[0] for p in prof] +
                    [zr + (zf - zr) * i / 24 for i in range(25)] + [zf - 0.05, zf]))
    zs = [z for z in zs if zr <= z <= zf]
    rings = []
    for z in zs:
        end = min(z - zr, zf - z)
        pinch = min(1.0, 0.86 + end * 0.9)
        w = 0.89 * pinch
        top = top_at(z)
        belt = min(belt_at(z), top)
        bot = 0.2
        for zc in (zw_r, zw_f):
            dz = abs(z - zc)
            if dz < 0.44:
                bot = max(bot, 0.2 + 0.45 * math.sqrt(max(0.0, 1 - (dz / 0.44) ** 2)))
        cabin = cab0 < z < cab1 and top > belt + 0.05
        pts = [(0.0, 0.2), (w * 0.9, 0.21), (w, bot + 0.04 if bot > 0.25 else 0.33), (w, max(0.58, bot + 0.08)), (w * 0.985, 0.85),
               (w * 0.95, belt)]
        if cabin:
            rw = 0.62
            ft = (top - belt) / max(0.01, roof - belt)
            pts += [(w * 0.9, belt + 0.03), (rw + (w * 0.88 - rw) * (1 - ft) + 0.02, top - 0.06), (rw, top), (0.0, top + 0.012)]
        else:
            pts += [(w * 0.86, top), (w * 0.6, top + 0.006), (w * 0.3, top + 0.012), (0.0, top + 0.015)]
        rings.append((z, pts, cabin))
    K = len(rings[0][1])
    # glass rules: side windows between ring points 6-7 inside the cabin (minus pillars),
    # windscreen / rear window on points 7..9 where the roof line slopes
    pillars = ([cab0 + 0.06, cab1 - 0.06, (cab0 + cab1) / 2 - 0.05] if True else [])

    def is_glass(j, za, zb, cab):
        zm = (za + zb) / 2
        if not cab:
            return False
        if j == 6:
            return all(abs(zm - p) > 0.06 for p in pillars)
        if j in (7, 8):
            slope = abs(top_at(zb) - top_at(za)) / max(1e-3, zb - za)
            return slope > 0.35
        return False
    for i in range(len(rings) - 1):
        za, pa, ca = rings[i]
        zb, pb, cb = rings[i + 1]
        cab = ca and cb
        for j in range(K - 1):
            m = "M_glass_car" if is_glass(j, za, zb, cab) else (paint if j >= 2 else "M_car_trim")
            if j == 0:
                m = "M_car_trim"
            for s in (1, -1):
                A = (s * pa[j][0], pa[j][1], za)
                Bq = (s * pb[j][0], pb[j][1], zb)
                C = (s * pb[j + 1][0], pb[j + 1][1], zb)
                D = (s * pa[j + 1][0], pa[j + 1][1], za)
                quad = [A, Bq, C, D] if s > 0 else [A, D, C, Bq]
                if (Vector(quad[1]) - Vector(quad[0])).length < 1e-5 and (Vector(quad[2]) - Vector(quad[3])).length < 1e-5:
                    continue
                B.face(quad, m)
    # end caps (bumpers)
    for idx, sgn in ((0, -1), (-1, 1)):
        z, pts, _ = rings[idx]
        loop = [(p[0], p[1], z) for p in pts] + [(-p[0], p[1], z) for p in reversed(pts)]
        if sgn > 0:
            loop = loop[::-1]
        B.face(loop, paint)
    # wheels + arches liners
    for zc in (zw_r, zw_f):
        for s in (-1, 1):
            wheel_x(B, s * 0.78, 0.31, zc, 0.31, 0.2)
    # lights, grille, plates, mirrors, handles
    zf_ = zf + 0.004
    for s in (-1, 1):
        hl = [(s * 0.7, 0.61, zf - 0.02), (s * 0.42, 0.615, zf - 0.02), (s * 0.42, 0.75, zf - 0.08), (s * 0.7, 0.745, zf - 0.08)]
        B.quad(*(hl if s < 0 else hl[::-1]), "M_head_light")
        zt = zr - 0.004
        if s > 0:
            B.quad((s * 0.82, 0.86, zt + 0.06), (s * 0.82, 0.98, zt + 0.1), (s * 0.55, 0.98, zt + 0.04), (s * 0.55, 0.86, zt + 0.0), "M_tail_light")
        else:
            B.quad((s * 0.82, 0.86, zt + 0.06), (s * 0.55, 0.86, zt + 0.0), (s * 0.55, 0.98, zt + 0.04), (s * 0.82, 0.98, zt + 0.1), "M_tail_light")
        # mirror
        mz = cab1 - 0.12
        B.box(s * 0.86 - (0.0 if s > 0 else 0.16), 1.0, mz - 0.04, s * 0.86 + (0.16 if s > 0 else 0.0), 1.1, mz + 0.06, paint)
        # door handles + door seam
        for hz in (0.25, -0.75) if hatch else (0.3, -0.8):
            B.box(s * 0.875 - (0.0 if s > 0 else 0.02), 0.9, hz - 0.08, s * 0.875 + (0.02 if s > 0 else 0.0), 0.93, hz + 0.06, "M_car_trim")
    B.box(-0.38, 0.4, zf - 0.03, 0.38, 0.58, zf + 0.004, "M_car_trim")
    for zz, sgn in ((zf + 0.006, 1), (zr - 0.006, -1)):
        y0 = 0.42 if sgn > 0 else 0.58
        pts = [(-0.26, y0, zz), (0.26, y0, zz), (0.26, y0 + 0.11, zz), (-0.26, y0 + 0.11, zz)]
        B.quad(*(pts if sgn > 0 else pts[::-1]), "M_plate_white")
        bx = -0.255 if sgn > 0 else 0.255
        blue = [(bx, y0 + 0.005, zz + sgn * 0.001), (bx + sgn * 0.045, y0 + 0.005, zz + sgn * 0.001),
                (bx + sgn * 0.045, y0 + 0.105, zz + sgn * 0.001), (bx, y0 + 0.105, zz + sgn * 0.001)]
        B.quad(*(blue if sgn > 0 else blue[::-1]), "M_plate_blue")
        with B.at(0.02 * sgn, y0 + 0.03, zz + sgn * 0.002, 0.0 if sgn > 0 else PI):
            B.text("GA-%03d-PZ" % (100 + seed * 37 % 900), CM_font("cond"), 0.075, "M_plastic_black", align="CENTER")
    B.box(-0.82, 0.18, zr + 0.2, 0.82, 0.2, zf - 0.2, "M_car_trim")
    B.cbox(-0.9, 0.0, zr, 0.9, roof, zf)


def car_hatch_blue(B):
    car(B, "M_car_blue", 4.1, True, 1)


def car_hatch_red(B):
    car(B, "M_car_red", 4.05, True, 2)


def car_sedan_white(B):
    car(B, "M_car_white", 4.55, False, 3)


def car_sedan_green(B):
    car(B, "M_car_green", 4.55, False, 4)


def velib_post(B):
    B.box(-0.18, 0.0, -0.22, 0.18, 0.04, 0.22, "M_steel_dark")
    chbox(B, -0.08, 0.04, -0.12, 0.08, 1.02, 0.12, "M_plastic_grey", c=0.03)
    B.box(-0.085, 0.9, -0.125, 0.085, 1.05, 0.125, "M_paint_metal_dark")
    B.box(-0.05, 0.93, 0.125, 0.05, 1.0, 0.13, "M_screen_off")
    B.box(-0.07, 0.86, 0.12, 0.07, 0.875, 0.13, "M_led_green")
    B.box(-0.05, 0.38, 0.12, 0.05, 0.6, 0.2, "M_paint_metal_dark")
    B.cbox(-0.09, 0.0, -0.13, 0.09, 1.05, 0.2)


def velib_bike(B, paint="M_velib_green"):
    """Velib' city bike, front wheel towards +Z, wheelbase 1.1 m"""
    r = 0.33
    zf, zb = 0.55, -0.55
    for zc in (zf, zb):
        ring(B, 0.0, r, zc, r - 0.025, 0.025, "M_rubber_black", seg=18, axis="x")
        ring(B, 0.0, r, zc, r - 0.055, 0.012, "M_alu_silver", seg=18, axis="x")
        B.cyl_axis((-0.05, r, zc), (0.05, r, zc), 0.04, "M_steel_dark", seg=8)
        for k in range(6):
            a = 2 * PI * k / 6
            B.cyl_axis((0.0, r, zc), (0.0, r + math.cos(a) * (r - 0.06), zc + math.sin(a) * (r - 0.06)), 0.004, "M_alu_silver", seg=4, caps=False)
    # step-through frame
    bb = Vector((0, 0.28, -0.05))
    head = Vector((0, 0.95, 0.42))
    seat = Vector((0, 0.95, -0.28))
    B.tube([head, (0, 0.62, 0.25), (0, 0.32, 0.05), bb], 0.03, paint, seg=8)
    B.tube([bb, (0, 0.6, -0.2), seat], 0.026, paint, seg=8)
    B.tube([bb, (0, r, zb)], 0.016, paint, seg=6)
    B.tube([(0, 0.62, -0.24), (0, r, zb)], 0.014, paint, seg=6)
    B.tube([head + Vector((0, 0.1, 0)), (0, r + 0.05, zf - 0.02), (0, r, zf)], 0.02, paint, seg=6)
    # handlebar, saddle, basket, mudguards, chain case
    B.tube([(-0.28, 1.12, 0.38), (-0.12, 1.1, 0.44), (0.12, 1.1, 0.44), (0.28, 1.12, 0.38)], 0.014, "M_steel_dark", seg=6)
    B.cyl(0, 1.0, 0.45, 0.018, 0.12, "M_steel_dark", seg=6)
    with B.at(0, 1.0, -0.3, 0.0, 0.05):
        chbox(B, -0.09, 0.0, -0.14, 0.09, 0.07, 0.12, "M_plastic_black", c=0.04)
    B.box(-0.18, 0.86, 0.6, 0.18, 1.08, 0.88, "M_plastic_grey")
    B.box(-0.16, 0.88, 0.62, 0.16, 1.08, 0.86, "M_room_sleeve", skip="b")
    for zc in (zf, zb):
        pts = [(0, r + math.cos(a) * (r + 0.04), zc + math.sin(a) * (r + 0.04)) for a in [0.35 + i * 0.2 for i in range(9)]]
        if zc < 0:
            pts = [(0, p[1], 2 * zc - p[2]) for p in pts]
        B.tube(pts, 0.03, paint, seg=6, caps=False)
    B.box(-0.035, 0.22, -0.55, 0.035, 0.34, 0.02, "M_plastic_black")
    B.cbox(-0.3, 0.0, -0.9, 0.3, 1.15, 0.9)


def velib_bike_green(B):
    velib_bike(B, "M_velib_green")


def velib_bike_blue(B):
    velib_bike(B, "M_velib_blue")


def velib_totem(B):
    B.box(-0.3, 0.0, -0.2, 0.3, 0.05, 0.2, "M_steel_dark")
    chbox(B, -0.26, 0.05, -0.12, 0.26, 2.2, 0.12, "M_plastic_grey", c=0.04)
    B.box(-0.2, 1.25, 0.12, 0.2, 1.6, 0.13, "M_screen_off")
    B.box(-0.18, 1.27, 0.13, 0.18, 1.58, 0.132, "M_screen_3")
    B.box(-0.26, 1.85, 0.12, 0.26, 2.2, 0.13, "M_velib_green")
    with B.at(0, 1.97, 0.131):
        B.text("velib'", CM_font("bold"), 0.13, "M_plate_white", align="CENTER", valign="BOTTOM")
    B.box(-0.2, 0.4, 0.12, 0.2, 1.1, 0.125, "M_paper_white")
    B.cbox(-0.27, 0.0, -0.13, 0.27, 2.2, 0.13)


def moped(B, paint="M_moped_red"):
    """Vespa-like scooter, front towards +Z: ellipsoid rear cowl, saddle, floorboard, leg shield, fender"""
    for zc, r in ((0.62, 0.2), (-0.52, 0.2)):
        B.cyl_axis((-0.05, r, zc), (0.05, r, zc), r, "M_rubber_black", seg=18)
        for sgn in (-1, 1):
            x = sgn * 0.052
            pts = [(x, r + math.cos(2 * PI * i / 14) * 0.12, zc + math.sin(2 * PI * i / 14) * 0.12) for i in range(14)]
            B.face(pts if sgn > 0 else pts[::-1], "M_alu_silver")
    with B.at(0, 0.5, -0.36, s=(0.21, 0.23, 0.46)):
        B.sphere(0, 0, 0, 1.0, paint, seg=16, rings=10)
    with B.at(0, 0.74, -0.3, s=(0.15, 0.055, 0.34)):
        B.sphere(0, 0, 0, 1.0, "M_plastic_black", seg=14, rings=7)
    B.box(-0.03, 0.66, -0.66, 0.03, 0.76, -0.62, "M_tail_light")
    chbox(B, -0.16, 0.24, -0.05, 0.16, 0.3, 0.42, "M_plastic_black", c=0.05)
    with B.at(0, 0.27, 0.46, 0.0, -0.22):
        chbox(B, -0.21, 0.0, -0.035, 0.21, 0.66, 0.025, paint, c=0.09)
    with B.at(0, 0.22, 0.62, s=(0.075, 0.11, 0.2)):
        B.sphere(0, 0, 0, 1.0, paint, seg=12, rings=6, hemi=True)
    B.tube([(0, 0.86, 0.58), (0, 0.5, 0.64), (0, 0.22, 0.62)], 0.024, "M_steel_dark", seg=8)
    with B.at(0, 0.92, 0.6, s=(0.11, 0.08, 0.09)):
        B.sphere(0, 0, 0, 1.0, paint, seg=12, rings=6)
    B.cyl_axis((0, 0.93, 0.66), (0, 0.93, 0.7), 0.05, "M_head_light", seg=12)
    B.tube([(-0.33, 0.97, 0.53), (-0.1, 0.95, 0.58), (0.1, 0.95, 0.58), (0.33, 0.97, 0.53)], 0.014, "M_steel_dark", seg=6)
    for sx in (-0.33, 0.33):
        B.cyl_axis((sx - 0.05 * (sx < 0), 0.97, 0.53), (sx + 0.05 * (sx > 0), 0.97, 0.53), 0.018, "M_rubber_black", seg=8)
        B.tube([(sx * 0.75, 0.97, 0.55), (sx * 0.9, 1.18, 0.5)], 0.006, "M_steel_dark", seg=4)
        with B.at(sx * 0.9, 1.2, 0.5, s=(0.05, 0.035, 0.012)):
            B.sphere(0, 0, 0, 1.0, "M_chrome", seg=8, rings=4)
    B.box(-0.12, 0.3, -0.62, 0.12, 0.42, -0.6, "M_plate_white")
    B.box(-0.025, 0.0, -0.22, 0.025, 0.25, -0.19, "M_steel_dark")
    B.cbox(-0.24, 0.0, -0.75, 0.24, 1.0, 0.82)


def moped_red(B):
    moped(B, "M_moped_red")


def moped_blue(B):
    moped(B, "M_moped_blue")


def hvac_unit(B):
    """rooftop air-handling unit with two fans"""
    B.box(-1.1, 0.0, -0.7, 1.1, 0.12, 0.7, "M_steel_dark")
    chbox(B, -1.05, 0.12, -0.65, 1.05, 1.15, 0.65, "M_zinc", c=0.03)
    for k in range(12):
        B.box(-1.051, 0.3 + k * 0.06, -0.55, -1.05, 0.33 + k * 0.06, 0.55, "M_steel_dark")
    for x in (-0.48, 0.5):
        B.cyl(x, 1.15, 0, 0.44, 0.08, "M_steel_dark", seg=20)
        B.cyl(x, 1.16, 0, 0.4, 0.075, "M_room_sleeve", seg=20, caps=(False, True))
        B.box(x - 0.4, 1.225, -0.012, x + 0.4, 1.235, 0.012, "M_zinc")
        B.box(x - 0.012, 1.225, -0.4, x + 0.012, 1.235, 0.4, "M_zinc")
    B.tube([(0.9, 0.6, 0.65), (0.9, 0.6, 1.1), (0.9, 0.05, 1.1)], 0.07, "M_zinc", seg=8)
    B.cbox(-1.1, 0.0, -0.7, 1.1, 1.25, 0.7)


def ac_wall(B):
    """split air-con outdoor unit on wall brackets (origin on the wall, front +Z)"""
    B.box(-0.42, 0.0, 0.0, 0.42, 0.04, 0.32, "M_steel_dark")
    chbox(B, -0.4, 0.04, 0.02, 0.4, 0.62, 0.3, "M_plastic_white", c=0.02)
    B.cyl_axis((-0.12, 0.33, 0.3), (-0.12, 0.33, 0.302), 0.2, "M_room_sleeve", seg=20)
    for k in range(5):
        B.box(-0.32, 0.17 + k * 0.065, 0.302, 0.08, 0.18 + k * 0.065, 0.306, "M_plastic_grey")
    B.tube([(0.3, 0.2, 0.02), (0.3, 0.2, -0.05)], 0.012, "M_alu_silver", seg=5)


def morris_column(B):
    """Paris advertising column (colonne Morris): dark green shaft, poster band, dome roof"""
    B.cyl(0, 0.0, 0, 0.66, 0.25, "M_paint_metal_green", seg=24)
    B.cyl(0, 0.25, 0, 0.6, 2.2, "M_morris", seg=24, caps=(False, False), uv_scale=None)
    B.cyl(0, 2.45, 0, 0.66, 0.15, "M_paint_metal_green", seg=24)
    B.cyl(0, 2.6, 0, 0.62, 0.35, "M_paint_metal_green", seg=24, r2=0.4)
    B.sphere(0, 2.95, 0, 0.4, "M_paint_metal_green", seg=16, rings=8, hemi=True)
    B.sphere(0, 3.37, 0, 0.07, "M_paint_metal_green", seg=8, rings=5)
    B.cbox(-0.62, 0.0, -0.62, 0.62, 3.0, 0.62)


def registry():
    return {
        "morris_column": (morris_column, {}),
        "hvac_unit": (hvac_unit, {}), "ac_wall": (ac_wall, {}),
        "street_lamp": (street_lamp, {}), "bollard": (bollard, {}), "bin_paris": (bin_paris, {}),
        "road_barrier": (road_barrier, {}), "bike_rack": (bike_rack, {}),
        "sign_no_parking": (sign_post, {"kind": "no_parking"}), "sign_zone30": (sign_post, {"kind": "zone30"}),
        "sign_one_way": (sign_post, {"kind": "one_way"}), "parking_meter": (parking_meter, {}),
        "utility_cabinet": (utility_cabinet, {}), "tree_plane": (tree_plane, {}), "planter_birch": (planter_birch, {}),
        "picnic_table": (picnic_table, {}), "court_pendant": (court_pendant, {}),
        "car_hatch_blue": (car_hatch_blue, {}), "car_hatch_red": (car_hatch_red, {}),
        "car_sedan_white": (car_sedan_white, {}), "car_sedan_green": (car_sedan_green, {}),
        "velib_post": (velib_post, {}), "velib_bike_green": (velib_bike_green, {}), "velib_bike_blue": (velib_bike_blue, {}),
        "velib_totem": (velib_totem, {}), "moped_red": (moped_red, {}), "moped_blue": (moped_blue, {}),
    }
