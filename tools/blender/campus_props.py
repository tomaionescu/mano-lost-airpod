"""Props: each is built around its own origin (floor contact, front facing +Z = local yaw 0, like the old
Kit.js props) and exported to assets/props/<name>.glb with its own -colonly collider when it is solid.
Placed in the level by PROP_<name>__<nn> markers (campus_dress.py)."""
import bpy, math, random, os
from mathutils import Vector
import campus_geo as G
import campus_mat as CM
from campus_mat import mat as defmat

PI = math.pi
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PROPS_DIR = os.path.join(ROOT, "assets", "props")

# extra prop materials
defmat("M_locker_blue", None, color="#2e3c9f", rough=0.42, metal=0.35, grime="none", macro=0.0)
defmat("M_locker_grey", None, color="#9aa1aa", rough=0.42, metal=0.35, grime="none", macro=0.0)
defmat("M_screen_off", None, color="#07080a", rough=0.08, grime="none", macro=0.0)
defmat("M_bin_bag", None, color="#a9b8a3", rough=0.45, grime="none", macro=0.0)
defmat("M_velib_green", None, color="#6fae3a", rough=0.4, metal=0.3)
defmat("M_velib_blue", None, color="#3f8fd4", rough=0.4, metal=0.3)
defmat("M_moped_red", None, color="#b8241f", rough=0.3, metal=0.4)
defmat("M_moped_blue", None, color="#2551a8", rough=0.3, metal=0.4)
defmat("M_vend_red", None, color="#b8282c", rough=0.4, metal=0.25)
defmat("M_vend_blue", None, color="#1d5fa8", rough=0.4, metal=0.25)
defmat("M_vend_glow", None, color="#ffffff", emit=("#dfeefa", 1.6))
defmat("M_arcade_purple", None, color="#2a1f4a", rough=0.5)
defmat("M_babyfoot_wood", (CM.PH, "oak_veneer_01", "1k"), tile=0.8, color="#7a4e2c", rough=0.45, maps=("diffg", "nor_gl", "arm"))
defmat("M_babyfoot_field", None, color="#2f8f55", rough=0.8)
defmat("M_table_blue", None, color="#1f6fbf", rough=0.45)
defmat("M_stool_red", None, color="#e85a3a", rough=0.5)
defmat("M_stool_blue", None, color="#2e3c9f", rough=0.5)
defmat("M_beanbag_red", (CM.ACG, "Fabric061", "1K"), tile=0.4, color="#e0552f", maps=("diffg", "nor_gl", "arm"))
defmat("M_beanbag_blue", (CM.ACG, "Fabric061", "1K"), tile=0.4, color="#2e3c9f", maps=("diffg", "nor_gl", "arm"))
defmat("M_beanbag_lime", (CM.ACG, "Fabric061", "1K"), tile=0.4, color="#a8d61c", maps=("diffg", "nor_gl", "arm"))
defmat("M_pot_white", None, color="#e9e5dc", rough=0.6)
defmat("M_pot_dark", None, color="#3b3f45", rough=0.6)
defmat("M_leaf_green", None, color="#3f7d4c", rough=0.6)
defmat("M_paper_white", None, color="#f3f1ea", rough=0.85)
defmat("M_cardboard", None, color="#b8915e", rough=0.85)
defmat("M_clock_face", None, color="#f8f8f6", rough=0.4)
defmat("M_coffee_body", None, color="#1c1d21", rough=0.35, metal=0.3)
defmat("M_coffee_panel", None, color="#2a1b10", emit=("#7a4a22", 0.8))
defmat("M_trash_yellow", None, color="#e9b31b", rough=0.5)
defmat("M_trash_green", None, color="#2f7a43", rough=0.5)
defmat("M_trash_grey", None, color="#5e6268", rough=0.5)
defmat("M_plate_white", None, color="#f4f4f0", rough=0.4)
defmat("M_plate_blue", None, color="#1f4fa8", rough=0.4)
defmat("M_sign_red", None, color="#c8202a", rough=0.45)
defmat("M_sign_blue", None, color="#1c4fa0", rough=0.45)
defmat("M_barrier_red", None, color="#d63b2f", rough=0.5)


# ------------------------------------------------------------------ small geometry helpers
def chbox(B, x0, y0, z0, x1, y1, z1, mat, c=0.02, top=True, bottom=True):
    """box with chamfered vertical edges (octagonal prism)"""
    c = min(c, (x1 - x0) / 2.5, (z1 - z0) / 2.5)
    pts = [(x0 + c, z0), (x1 - c, z0), (x1, z0 + c), (x1, z1 - c), (x1 - c, z1), (x0 + c, z1), (x0, z1 - c), (x0, z0 + c)]
    B.prism(pts, y0, y1, mat, top=top, bottom=bottom)


def ring(B, cx, cy, cz, r, rt, mat, seg=16, axis="y"):
    """torus-like ring made with a closed tube"""
    pts = []
    for i in range(seg + 1):
        a = 2 * PI * i / seg
        if axis == "y":
            pts.append((cx + math.cos(a) * r, cy, cz + math.sin(a) * r))
        elif axis == "x":
            pts.append((cx, cy + math.cos(a) * r, cz + math.sin(a) * r))
        else:
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r, cz))
    B.tube(pts, rt, mat, seg=6, caps=False)


def wheel_x(B, cx, cy, cz, r, w, tire="M_rubber_black", rim="M_alu_silver", spokes=5, seg=16):
    """wheel with its axle along X"""
    B.cyl_axis((cx - w / 2, cy, cz), (cx + w / 2, cy, cz), r, tire, seg=seg)
    for s in (-1, 1):
        x = cx + s * (w / 2 + 0.002)
        pts = [(x, cy + math.cos(2 * PI * i / seg) * r * 0.62, cz + math.sin(2 * PI * i / seg) * r * 0.62) for i in range(seg)]
        B.face(pts if s > 0 else pts[::-1], rim)
        for k in range(spokes):
            a = 2 * PI * k / spokes
            B.cyl_axis((x + s * 0.003, cy, cz), (x + s * 0.003, cy + math.cos(a) * r * 0.6, cz + math.sin(a) * r * 0.6), 0.012, rim, seg=5, caps=False)


def bulb(B, x, y, z, r, mat):
    B.sphere(x, y, z, r, mat, seg=8, rings=5)


# ------------------------------------------------------------------ computer room
def pc_desk(B, screen="M_screen_0"):
    top = "M_laminate_white"
    B.box(-0.7, 0.73, -0.375, 0.7, 0.76, 0.375, top)
    B.box(-0.7, 0.722, 0.36, 0.7, 0.76, 0.375, "M_plastic_dark")
    for sx in (-0.64, 0.64):
        for sz in (-0.3, 0.3):
            B.box(sx - 0.02, 0.0, sz - 0.02, sx + 0.02, 0.73, sz + 0.02, "M_paint_metal_dark")
        B.box(sx - 0.025, 0.0, -0.34, sx + 0.025, 0.035, 0.34, "M_paint_metal_dark")
        B.box(sx - 0.02, 0.69, -0.3, sx + 0.02, 0.73, 0.3, "M_paint_metal_dark")
    B.box(-0.62, 0.36, -0.335, 0.62, 0.7, -0.315, "M_paint_metal_dark")
    B.box(-0.6, 0.6, -0.3, 0.6, 0.62, -0.18, "M_steel_dark")            # cable tray
    # monitor
    mz = -0.16
    B.box(-0.03, 0.76, mz - 0.1, 0.03, 0.775, mz + 0.06, "M_plastic_black")
    B.box(-0.11, 0.76, mz - 0.07, 0.11, 0.772, mz + 0.07, "M_plastic_black")
    B.box(-0.025, 0.772, mz - 0.03, 0.025, 0.93, mz - 0.005, "M_plastic_black")
    B.box(-0.285, 0.88, mz - 0.03, 0.285, 1.22, mz + 0.008, "M_plastic_black")
    B.quad((-0.27, 0.896, mz + 0.0085), (0.27, 0.896, mz + 0.0085), (0.27, 1.205, mz + 0.0085), (-0.27, 1.205, mz + 0.0085), screen,
           uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    # keyboard + mouse + pad
    B.box(-0.22, 0.76, 0.02, 0.22, 0.775, 0.16, "M_plastic_dark")
    for k in range(4):
        B.box(-0.205, 0.775, 0.035 + k * 0.03, 0.205, 0.781, 0.057 + k * 0.03, "M_plastic_black")
    B.box(0.27, 0.76, 0.03, 0.47, 0.762, 0.2, "M_fabric_black")
    chbox(B, 0.335, 0.762, 0.07, 0.395, 0.785, 0.16, "M_plastic_black", c=0.015)
    # thin client under the desk
    B.box(-0.55, 0.0, -0.25, -0.37, 0.42, 0.15, "M_plastic_black")
    B.box(-0.54, 0.38, 0.152, -0.52, 0.39, 0.154, "M_led_green")
    B.cbox(-0.7, 0.0, -0.375, 0.7, 0.77, 0.375)


def office_chair(B, fabric="M_fabric_black"):
    """swivel chair, the sitter faces +Z; seat top at 0.45, seat front edge at local z +0.25"""
    for k in range(5):
        a = 2 * PI * k / 5 + 0.3
        ex, ez = math.sin(a) * 0.3, math.cos(a) * 0.3
        B.tube([(0, 0.09, 0), (ex, 0.07, ez)], 0.018, "M_plastic_black", seg=6, caps=False)
        B.cyl(ex, 0.0, ez, 0.03, 0.05, "M_plastic_black", seg=8)
    B.cyl(0, 0.07, 0, 0.045, 0.05, "M_plastic_black", seg=10)
    B.cyl(0, 0.1, 0, 0.025, 0.24, "M_chrome", seg=10)
    B.box(-0.12, 0.32, -0.12, 0.12, 0.36, 0.12, "M_plastic_black")
    chbox(B, -0.25, 0.36, -0.23, 0.25, 0.45, 0.25, fabric, c=0.05)
    with B.at(0, 0.0, -0.24, 0.0, -0.12):
        B.box(-0.03, 0.34, -0.02, 0.03, 0.54, 0.02, "M_plastic_black")
        chbox(B, -0.23, 0.52, -0.04, 0.23, 1.0, 0.03, fabric, c=0.05)
    for s in (-1, 1):
        B.box(s * 0.25 - 0.015, 0.37, -0.05, s * 0.25 + 0.015, 0.58, -0.01, "M_plastic_black")
        B.box(s * 0.25 - 0.03, 0.57, -0.16, s * 0.25 + 0.03, 0.6, 0.14, "M_plastic_black")


def desk_office(B, w=1.6, d=0.7):
    pc_like = "M_laminate_white"
    B.box(-w / 2, 0.73, -d / 2, w / 2, 0.76, d / 2, pc_like)
    for sx in (-w / 2 + 0.04, w / 2 - 0.04):
        B.box(sx - 0.03, 0.0, -d / 2 + 0.04, sx + 0.03, 0.73, d / 2 - 0.04, "M_paint_metal_white")
    B.box(-w / 2 + 0.1, 0.0, -0.3, -w / 2 + 0.52, 0.66, 0.25, "M_paint_metal_white")     # drawer block
    for k in range(3):
        B.box(-w / 2 + 0.12, 0.08 + k * 0.2, 0.252, -w / 2 + 0.5, 0.25 + k * 0.2, 0.258, "M_paint_metal_white")
        B.box(-w / 2 + 0.26, 0.2 + k * 0.2, 0.258, -w / 2 + 0.36, 0.215 + k * 0.2, 0.27, "M_alu_silver")
    # monitor, papers, mug, plant
    B.box(0.0, 0.76, -0.2, 0.05, 0.77, -0.1, "M_plastic_black")
    B.box(-0.26, 0.86, -0.2, 0.26, 1.16, -0.17, "M_plastic_black")
    B.quad((-0.245, 0.875, -0.169), (0.245, 0.875, -0.169), (0.245, 1.145, -0.169), (-0.245, 1.145, -0.169), "M_screen_1",
           uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.box(-0.02, 0.77, -0.19, 0.02, 0.87, -0.175, "M_plastic_black")
    B.box(0.3, 0.76, -0.05, 0.6, 0.775, 0.17, "M_paper_white")
    B.cyl(-0.45, 0.76, 0.1, 0.04, 0.1, "M_plastic_red", seg=10)
    B.box(-0.2, 0.76, 0.05, 0.22, 0.775, 0.19, "M_plastic_dark")
    B.cbox(-w / 2, 0.0, -d / 2, w / 2, 0.77, d / 2)


def lockers_4(B, mat="M_locker_blue"):
    """four 0.4 m locker columns, two doors each, 1.9 m tall, front +Z"""
    W = 1.6
    B.box(-W / 2, 0.0, -0.25, W / 2, 1.9, 0.22, mat)
    B.box(-W / 2, 0.0, 0.2, W / 2, 0.08, 0.235, "M_paint_metal_dark")
    for i in range(4):
        x0 = -W / 2 + i * 0.4
        for j, (y0, y1) in enumerate(((0.1, 0.98), (1.0, 1.88))):
            B.box(x0 + 0.012, y0, 0.22, x0 + 0.388, y1, 0.235, mat)
            for k in range(4):
                yy = y1 - 0.12 - k * 0.035
                B.box(x0 + 0.1, yy, 0.235, x0 + 0.29, yy + 0.012, 0.237, "M_room_sleeve")
            B.box(x0 + 0.31, (y0 + y1) / 2 - 0.06, 0.235, x0 + 0.34, (y0 + y1) / 2 + 0.06, 0.255, "M_alu_silver")
            B.box(x0 + 0.06, y1 - 0.08, 0.235, x0 + 0.13, y1 - 0.05, 0.238, "M_plate_white")
    B.cbox(-W / 2, 0.0, -0.25, W / 2, 1.9, 0.25)


def vending(B, body="M_vend_red", label="SNACKS"):
    B.box(-0.45, 0.0, -0.37, 0.45, 1.85, 0.36, body)
    B.box(-0.45, 1.68, 0.36, 0.45, 1.85, 0.375, "M_plastic_black")
    # window with product spirals
    B.box(-0.4, 0.55, 0.3, 0.22, 1.65, 0.36, "M_vend_glow", skip="s")
    rng = random.Random(len(body) + len(label))
    cols = ["M_plastic_yellow", "M_plastic_green", "M_plastic_orange", "M_plastic_red", "M_plastic_blue", "M_plastic_white"]
    for r in range(5):
        y = 0.62 + r * 0.205
        B.box(-0.39, y - 0.012, 0.18, 0.21, y, 0.35, "M_chrome")
        for c in range(5):
            x = -0.34 + c * 0.11
            B.box(x - 0.042, y, 0.26, x + 0.042, y + 0.13, 0.33, cols[rng.randrange(len(cols))])
    B.quad((-0.4, 0.55, 0.37), (0.22, 0.55, 0.37), (0.22, 1.65, 0.37), (-0.4, 1.65, 0.37), "M_glass_clear", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    A_frame = "M_plastic_black"
    B.box(-0.43, 0.53, 0.36, 0.24, 0.55, 0.38, A_frame)
    B.box(-0.43, 1.65, 0.36, 0.24, 1.67, 0.38, A_frame)
    B.box(-0.43, 0.55, 0.36, -0.4, 1.65, 0.38, A_frame)
    B.box(0.22, 0.55, 0.36, 0.24, 1.65, 0.38, A_frame)
    # keypad, coin slot, pickup flap
    B.box(0.26, 0.95, 0.36, 0.42, 1.45, 0.38, "M_plastic_black")
    for r in range(4):
        for c in range(3):
            B.box(0.28 + c * 0.045, 1.0 + r * 0.05, 0.38, 0.31 + c * 0.045, 1.035 + r * 0.05, 0.387, "M_alu_silver")
    B.box(0.29, 1.32, 0.38, 0.39, 1.4, 0.383, "M_led_green")
    B.box(-0.38, 0.12, 0.36, 0.2, 0.4, 0.375, "M_plastic_black")
    B.box(-0.36, 0.14, 0.375, 0.18, 0.38, 0.378, "M_room_sleeve")
    B.cbox(-0.45, 0.0, -0.37, 0.45, 1.85, 0.38)


def CM_font(n):
    import campus_gen
    return campus_gen.font(n)


def vending_label(B, label):
    with B.at(0.0, 1.765, 0.376):
        B.text(label, CM_font("bold"), 0.09, "M_plate_white", align="CENTER")


def vending_red(B):
    vending(B, "M_vend_red")
    vending_label(B, "SNACKS")


def vending_blue(B):
    vending(B, "M_vend_blue")
    vending_label(B, "BOISSONS")


def coffee_machine(B):
    B.box(-0.375, 0.0, -0.35, 0.375, 1.8, 0.33, "M_coffee_body")
    B.box(-0.3, 1.08, 0.33, 0.3, 1.63, 0.345, "M_coffee_panel")
    B.box(-0.14, 0.45, 0.2, 0.14, 0.77, 0.34, "M_room_sleeve", skip="s")
    B.box(-0.15, 0.44, 0.2, 0.15, 0.45, 0.35, "M_chrome")
    B.cyl(0.0, 0.45, 0.27, 0.035, 0.09, "M_paper_white", seg=12)
    for k in range(6):
        B.box(-0.26 + k * 0.09, 0.92, 0.33, -0.2 + k * 0.09, 0.98, 0.35, "M_alu_silver")
        B.box(-0.245 + k * 0.09, 0.985, 0.33, -0.215 + k * 0.09, 1.0, 0.345, "M_led_amber")
    B.box(0.18, 1.0, 0.33, 0.3, 1.06, 0.36, "M_led_amber")
    B.box(-0.375, 1.66, 0.33, 0.375, 1.8, 0.35, "M_plastic_black")
    with B.at(0.0, 1.695, 0.351):
        B.text("CAFE  2 EUR", CM_font("semi"), 0.085, "M_paint_metal_yellow", align="CENTER")
    B.cbox(-0.375, 0.0, -0.35, 0.375, 1.8, 0.36)


def microwave(B):
    B.box(-0.27, 0.0, -0.2, 0.27, 0.32, 0.2, "M_plastic_white")
    B.box(-0.25, 0.04, 0.2, 0.12, 0.28, 0.21, "M_plastic_black")
    B.quad((-0.23, 0.06, 0.211), (0.1, 0.06, 0.211), (0.1, 0.26, 0.211), (-0.23, 0.26, 0.211), "M_glass_car", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.box(0.15, 0.22, 0.2, 0.25, 0.26, 0.205, "M_plastic_black")
    B.box(0.17, 0.23, 0.205, 0.23, 0.25, 0.207, "M_led_green")
    for k in range(3):
        B.box(0.16 + k * 0.03, 0.12, 0.2, 0.18 + k * 0.03, 0.18, 0.206, "M_plastic_grey")


def cafe_table(B, w=1.6, d=0.8):
    chbox(B, -w / 2, 0.72, -d / 2, w / 2, 0.75, d / 2, "M_laminate_white", c=0.06)
    B.box(-w / 2 + 0.06, 0.705, -0.02, w / 2 - 0.06, 0.72, 0.02, "M_steel_dark")
    for sx in (-w / 2 + 0.3, w / 2 - 0.3):
        B.cyl(sx, 0.0, 0.0, 0.035, 0.71, "M_steel_dark", seg=10)
        B.box(sx - 0.03, 0.0, -d / 2 + 0.08, sx + 0.03, 0.025, d / 2 - 0.08, "M_steel_dark")
    B.cbox(-w / 2, 0.0, -d / 2, w / 2, 0.76, d / 2)


def stool(B, seat="M_stool_red"):
    B.cyl(0, 0.4, 0, 0.19, 0.045, seat, seg=18)
    B.cyl(0, 0.445, 0, 0.18, 0.005, seat, seg=18)
    B.cyl(0, 0.03, 0, 0.026, 0.38, "M_chrome", seg=8)
    B.cyl(0, 0.0, 0, 0.2, 0.03, "M_steel_dark", seg=18)
    ring(B, 0, 0.2, 0, 0.13, 0.008, "M_chrome", seg=14)


def stool_red(B):
    stool(B, "M_stool_red")


def stool_blue(B):
    stool(B, "M_stool_blue")


def bench_oak(B, w=2.0):
    B.box(-w / 2, 0.41, -0.2, w / 2, 0.45, 0.2, "M_wood_oak")
    for i in range(1, 8):
        x = -w / 2 + w * i / 8
        B.box(x - 0.004, 0.449, -0.2, x + 0.004, 0.451, 0.2, "M_wood_dark")
    for sx in (-w / 2 + 0.2, w / 2 - 0.2):
        B.box(sx - 0.02, 0.0, -0.17, sx + 0.02, 0.41, -0.13, "M_paint_metal_dark")
        B.box(sx - 0.02, 0.0, 0.13, sx + 0.02, 0.41, 0.17, "M_paint_metal_dark")
        B.box(sx - 0.02, 0.37, -0.17, sx + 0.02, 0.41, 0.17, "M_paint_metal_dark")
        B.box(sx - 0.02, 0.0, -0.17, sx + 0.02, 0.03, 0.17, "M_paint_metal_dark")
    B.cbox(-w / 2, 0.0, -0.2, w / 2, 0.45, 0.2)


def sofa(B, w=2.6, fabric="M_fabric_navy"):
    d = 0.88
    chbox(B, -w / 2, 0.08, -d / 2, w / 2, 0.32, d / 2, fabric, c=0.06)
    chbox(B, -w / 2, 0.32, -d / 2, w / 2, 0.86, -d / 2 + 0.22, fabric, c=0.06)
    for s in (-1, 1):
        chbox(B, s * w / 2 - (0.18 if s > 0 else 0), 0.08, -d / 2, s * w / 2 + (0.0 if s > 0 else 0.18), 0.66, d / 2, fabric, c=0.05)
    n = max(2, int(round(w / 0.85)))
    cw = (w - 0.36) / n
    for k in range(n):
        x0 = -w / 2 + 0.18 + k * cw
        chbox(B, x0 + 0.01, 0.32, -d / 2 + 0.22, x0 + cw - 0.01, 0.45, d / 2 - 0.02, fabric, c=0.05)
        with B.at(x0 + cw / 2, 0.0, -d / 2 + 0.3, 0.0, -0.18):
            chbox(B, -cw / 2 + 0.02, 0.5, -0.1, cw / 2 - 0.02, 0.92, 0.06, fabric, c=0.06)
    for sx in (-w / 2 + 0.08, w / 2 - 0.08):
        for sz in (-d / 2 + 0.08, d / 2 - 0.08):
            B.cyl(sx, 0.0, sz, 0.025, 0.08, "M_wood_dark", seg=8)
    B.cbox(-w / 2, 0.0, -d / 2, w / 2, 0.62, d / 2)


def sofa_navy(B):
    sofa(B, 2.6, "M_fabric_navy")


def armchair(B, fabric="M_fabric_mustard"):
    chbox(B, -0.42, 0.1, -0.4, 0.42, 0.42, 0.4, fabric, c=0.06)
    chbox(B, -0.42, 0.42, -0.4, 0.42, 0.95, -0.22, fabric, c=0.06)
    for s in (-1, 1):
        chbox(B, s * 0.42 - (0.15 if s > 0 else 0), 0.1, -0.4, s * 0.42 + (0 if s > 0 else 0.15), 0.64, 0.4, fabric, c=0.05)
    chbox(B, -0.27, 0.42, -0.22, 0.27, 0.53, 0.38, fabric, c=0.05)
    for sx in (-0.36, 0.36):
        for sz in (-0.34, 0.34):
            B.cyl(sx, 0.0, sz, 0.02, 0.1, "M_wood_dark", seg=8)
    B.cbox(-0.43, 0.0, -0.4, 0.43, 0.7, 0.4)


def armchair_mustard(B):
    armchair(B, "M_fabric_mustard")


def round_sofa(B):
    """5 navy segments on an arc of radius 1.3 around the origin, facing the centre (the old roundSofa);
    backrests outside, cushion front edges at radius 0.92, seat top 0.45"""
    for k in range(5):
        a = -0.9 + k * 0.45
        with B.at(math.sin(a) * 1.3, 0.0, math.cos(a) * 1.3, a + PI):
            chbox(B, -0.33, 0.08, -0.42, 0.33, 0.36, 0.38, "M_fabric_navy", c=0.05)
            chbox(B, -0.33, 0.36, -0.42, 0.33, 0.86, -0.18, "M_fabric_navy", c=0.05)
            chbox(B, -0.31, 0.36, -0.18, 0.31, 0.45, 0.38, "M_fabric_navy", c=0.05)
            B.box(-0.3, 0.0, -0.38, 0.3, 0.08, 0.34, "M_plastic_black")
    for k in range(5):
        a = -0.9 + k * 0.45
        with B.at(math.sin(a) * 1.3, 0.0, math.cos(a) * 1.3, a + PI):
            B.cbox(-0.33, 0.0, -0.42, 0.33, 0.6, 0.38)


def low_table(B, r=0.45, mat="M_laminate_white"):
    B.cyl(0, 0.4, 0, r, 0.04, mat, seg=28)
    B.cyl(0, 0.03, 0, 0.04, 0.37, "M_steel_dark", seg=10)
    B.cyl(0, 0.0, 0, 0.25, 0.03, "M_steel_dark", seg=20)
    B.cbox(-r * 0.7, 0.0, -r * 0.7, r * 0.7, 0.44, r * 0.7)


def drum_lamp(B, h=1.55):
    B.cyl(0, 0.0, 0, 0.18, 0.03, "M_chrome", seg=20)
    B.cyl(0, 0.03, 0, 0.012, h - 0.18, "M_chrome", seg=8)
    B.cyl(0, h - 0.15, 0, 0.22, 0.3, "M_light_warm", seg=24, caps=(False, False))
    B.cyl(0, h - 0.15, 0, 0.215, 0.3, "M_light_warm", seg=24, caps=(False, False))
    B.cbox(-0.1, 0.0, -0.1, 0.1, h, 0.1)


def stanchion(B):
    B.cyl(0, 0.0, 0, 0.16, 0.025, "M_chrome", seg=20)
    B.cyl(0, 0.025, 0, 0.025, 0.93, "M_chrome", seg=10)
    B.cyl(0, 0.955, 0, 0.032, 0.04, "M_chrome", seg=10)
    B.box(0.02, 0.88, -0.03, 0.06, 0.94, 0.03, "M_plastic_black")


def wall_clock(B):
    """origin on the wall at the clock centre; face towards +Z; hands at 17:42 (forever)"""
    B.cyl_axis((0, 0, 0.0), (0, 0, 0.04), 0.205, "M_plastic_black", seg=32)
    B.face([(math.cos(2 * PI * i / 32) * 0.19, math.sin(2 * PI * i / 32) * 0.19, 0.041) for i in range(32)], "M_clock_face")
    for k in range(12):
        a = 2 * PI * k / 12
        ca, sa = math.cos(a), math.sin(a)
        r0, r1, w = (0.15, 0.18, 0.008) if k % 3 else (0.14, 0.18, 0.012)
        B.quad((sa * r0 - ca * w, ca * r0 + sa * w, 0.042), (sa * r0 + ca * w, ca * r0 - sa * w, 0.042),
               (sa * r1 + ca * w, ca * r1 - sa * w, 0.042), (sa * r1 - ca * w, ca * r1 + sa * w, 0.042), "M_plastic_black")
    for ang, ln, w, z in (((5 + 42 / 60) / 12 * 2 * PI, 0.1, 0.012, 0.044), (42 / 60 * 2 * PI, 0.155, 0.008, 0.046)):
        ca, sa = math.cos(ang), math.sin(ang)
        B.quad((-ca * w - sa * 0.02, sa * w - ca * 0.02, z), (ca * w - sa * 0.02, -sa * w - ca * 0.02, z),
               (sa * ln + ca * w, ca * ln - sa * w, z), (sa * ln - ca * w, ca * ln + sa * w, z), "M_plastic_black")
    B.cyl_axis((0, 0, 0.04), (0, 0, 0.05), 0.012, "M_sign_red", seg=10)


def extinguisher(B):
    """wall-mounted CO2 extinguisher + sign; origin on the floor at the wall, front +Z"""
    B.box(-0.06, 0.95, 0.0, 0.06, 1.05, 0.03, "M_paint_metal_dark")
    B.cyl(0, 0.62, 0.12, 0.085, 0.5, "M_paint_metal_red", seg=14)
    B.sphere(0, 1.12, 0.12, 0.085, "M_paint_metal_red", seg=14, rings=6, hemi=True)
    B.box(-0.03, 1.17, 0.09, 0.03, 1.25, 0.15, "M_plastic_black")
    B.box(-0.06, 1.23, 0.1, 0.04, 1.25, 0.14, "M_plastic_black")
    B.tube([(0.02, 1.2, 0.18), (0.11, 1.0, 0.2), (0.12, 0.75, 0.2)], 0.012, "M_rubber_black", seg=6)
    B.box(-0.05, 0.72, 0.205, 0.05, 0.88, 0.207, "M_plate_white")
    B.box(-0.1, 1.45, 0.0, 0.1, 1.65, 0.01, "M_sign_red")
    B.box(-0.03, 1.48, 0.01, 0.03, 1.6, 0.012, "M_plate_white")


def exit_sign(B):
    """ceiling/wall emergency exit sign; origin at its mounting point (top centre), face +Z"""
    B.box(-0.18, -0.16, -0.03, 0.18, 0.0, 0.03, "M_plastic_white")
    B.quad((-0.165, -0.15, 0.031), (0.165, -0.15, 0.031), (0.165, -0.01, 0.031), (-0.165, -0.01, 0.031), "M_exit_sign",
           uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.quad((0.165, -0.15, -0.031), (-0.165, -0.15, -0.031), (-0.165, -0.01, -0.031), (0.165, -0.01, -0.031), "M_exit_sign",
           uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])


def lectern(B):
    B.box(-0.3, 0.0, -0.22, 0.3, 1.0, 0.22, "M_wood_oak")
    with B.at(0, 1.0, 0.0, 0.0, -0.18):
        B.box(-0.33, 0.0, -0.25, 0.33, 0.04, 0.25, "M_wood_oak")
    B.box(-0.31, 0.0, 0.22, 0.31, 0.1, 0.24, "M_plastic_black")
    B.tube([(0.15, 1.05, -0.05), (0.15, 1.2, 0.05), (0.13, 1.3, 0.15)], 0.006, "M_plastic_black", seg=5)
    B.sphere(0.13, 1.31, 0.16, 0.018, "M_plastic_black", seg=8, rings=5)
    B.cbox(-0.31, 0.0, -0.23, 0.31, 1.1, 0.24)


def laptop(B, screen="M_screen_2"):
    B.box(-0.16, 0.0, -0.11, 0.16, 0.015, 0.11, "M_alu_silver")
    B.box(-0.14, 0.015, -0.06, 0.14, 0.017, 0.07, "M_plastic_black")
    with B.at(0, 0.015, -0.11, 0.0, -0.3):
        B.box(-0.16, 0.0, -0.008, 0.16, 0.21, 0.0, "M_alu_silver")
        B.quad((-0.145, 0.012, 0.0005), (0.145, 0.012, 0.0005), (0.145, 0.198, 0.0005), (-0.145, 0.198, 0.0005), screen,
               uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])


def backpack(B, mat="M_fabric_navy"):
    with B.at(0, 0, 0, 0, -0.15):
        chbox(B, -0.15, 0.0, -0.09, 0.15, 0.42, 0.09, mat, c=0.04)
        chbox(B, -0.12, 0.05, 0.09, 0.12, 0.22, 0.15, mat, c=0.03)
        B.tube([(-0.09, 0.4, -0.09), (-0.1, 0.3, -0.13), (-0.1, 0.06, -0.11)], 0.015, "M_fabric_black", seg=5)
        B.tube([(0.09, 0.4, -0.09), (0.1, 0.3, -0.13), (0.1, 0.06, -0.11)], 0.015, "M_fabric_black", seg=5)
        B.tube([(-0.04, 0.42, 0.0), (0.0, 0.47, 0.0), (0.04, 0.42, 0.0)], 0.01, "M_fabric_black", seg=5)


def backpack_navy(B):
    backpack(B, "M_fabric_navy")


def backpack_red(B):
    backpack(B, "M_fabric_red")


def backpack_green(B):
    backpack(B, "M_trash_green")


def bottle(B):
    B.cyl(0, 0.0, 0, 0.032, 0.17, "M_glass_clear", seg=12)
    B.cyl(0, 0.17, 0, 0.032, 0.03, "M_glass_clear", seg=12, r2=0.017)
    B.cyl(0, 0.2, 0, 0.018, 0.025, "M_plastic_epita", seg=10)


def bins_tri(B):
    """three sorting bins (yellow recycling, green glass, grey general)"""
    for k, m in enumerate(("M_trash_yellow", "M_trash_green", "M_trash_grey")):
        x = -0.42 + k * 0.42
        chbox(B, x - 0.19, 0.0, -0.22, x + 0.19, 0.85, 0.22, m, c=0.04)
        chbox(B, x - 0.2, 0.85, -0.23, x + 0.2, 0.9, 0.23, "M_plastic_black", c=0.04)
        B.box(x - 0.08, 0.9, -0.05, x + 0.08, 0.905, 0.05, "M_room_sleeve")
    B.cbox(-0.62, 0.0, -0.23, 0.62, 0.9, 0.23)


# ------------------------------------------------------------------ amphi
def amphi_row(B, seats, length=7.6, seat_mat="M_fabric_navy"):
    """continuous oak writing tablet + modesty panel with fold-down seats behind it (row faces +Z)"""
    h = length / 2
    B.box(-h, 0.74, 0.04, h, 0.78, 0.36, "M_wood_oak")
    B.box(-h, 0.0, 0.32, h, 0.74, 0.36, "M_wood_oak")
    for s in (-1, 1):
        B.box(s * h - (0.04 if s > 0 else 0), 0.0, -0.42, s * h + (0 if s > 0 else 0.04), 0.82, 0.38, "M_wood_oak")
    B.box(-h, 0.0, 0.3, h, 0.06, 0.32, "M_paint_metal_dark")
    xs = list(seats)
    bounds = [xs[0] - 0.3] + [(a + b) / 2 for a, b in zip(xs, xs[1:])] + [xs[-1] + 0.3]
    for x in bounds:
        if abs(x) > h - 0.05:
            continue
        B.box(x - 0.025, 0.0, -0.32, x + 0.025, 0.45, -0.26, "M_paint_metal_dark")
        B.box(x - 0.03, 0.45, -0.42, x + 0.03, 0.66, 0.0, "M_wood_oak")
    for x in xs:
        hw = 0.22
        chbox(B, x - hw, 0.385, -0.38, x + hw, 0.45, 0.04, seat_mat, c=0.03)
        B.box(x - hw + 0.02, 0.365, -0.36, x + hw - 0.02, 0.385, 0.02, "M_plastic_black")
        with B.at(x, 0.0, -0.4, 0.0, -0.16):
            chbox(B, -hw, 0.48, -0.035, hw, 0.98, 0.035, seat_mat, c=0.03)
            B.box(-hw + 0.01, 0.5, -0.05, hw - 0.01, 0.96, -0.035, "M_wood_oak")
    B.cbox(-h, 0.0, 0.02, h, 0.78, 0.38)


AMPHI_L_SEATS = [10.7305 + 0.56875 * i - 14.1 for i in range(13)]
AMPHI_R_SEATS = [20.06667 + 0.633333 * i - 23.45 for i in range(11)]


def amphi_row_l(B):
    amphi_row(B, AMPHI_L_SEATS)


def amphi_row_r(B):
    amphi_row(B, AMPHI_R_SEATS)


# ------------------------------------------------------------------ the Under
def babyfoot(B):
    w, d = 1.4, 0.86
    B.box(-w / 2, 0.7, -d / 2, w / 2, 0.86, d / 2, "M_babyfoot_wood", skip="t")
    B.box(-0.6, 0.84, -0.34, 0.6, 0.85, 0.34, "M_babyfoot_field")
    B.box(-0.004, 0.85, -0.34, 0.004, 0.852, 0.34, "M_plate_white")
    for s in (-1, 1):
        B.box(s * 0.6 - 0.006, 0.85, -0.12, s * 0.6 + 0.006, 0.852, 0.12, "M_plate_white")
    for s in (-1, 1):
        B.box(-w / 2, 0.86, s * d / 2 - (0.03 if s > 0 else 0), w / 2, 1.0, s * d / 2 + (0 if s > 0 else 0.03), "M_babyfoot_wood")
        B.box(s * w / 2 - (0.05 if s > 0 else 0), 0.86, -d / 2, s * w / 2 + (0 if s > 0 else 0.05), 1.0, d / 2, "M_babyfoot_wood")
        B.box(s * 0.625 - 0.02, 0.86, -0.12, s * 0.625 + 0.02, 0.96, 0.12, "M_room_sleeve")
        for t in (-1, 1):
            B.box(s * 0.6 - 0.05, 0.0, t * 0.36 - 0.05, s * 0.6 + 0.05, 0.7, t * 0.36 + 0.05, "M_babyfoot_wood")
            B.box(s * 0.6 - 0.07, 0.0, t * 0.36 - 0.07, s * 0.6 + 0.07, 0.03, t * 0.36 + 0.07, "M_plastic_black")
    # 8 rods with players (red team handles on +z, blue team on -z)
    rods = [(-0.53, 1, 1), (-0.38, 1, 2), (-0.15, -1, 3), (-0.05, 1, 5), (0.05, -1, 5), (0.15, 1, 3), (0.38, -1, 2), (0.53, -1, 1)]
    for x, side, n in rods:
        team = "M_plastic_red" if side > 0 else "M_plastic_blue"
        B.cyl_axis((x, 0.93, -0.62), (x, 0.93, 0.62), 0.008, "M_chrome", seg=6)
        B.cyl_axis((x, 0.93, side * 0.62), (x, 0.93, side * 0.75), 0.017, "M_plastic_black", seg=8)
        for k in range(n):
            z = (-0.25 + 0.5 * (k + 0.5) / n) if n > 1 else 0.0
            B.box(x - 0.012, 0.86, z - 0.02, x + 0.012, 0.97, z + 0.02, team)
            B.sphere(x, 0.985, z, 0.018, "M_plate_white", seg=6, rings=4)
    B.sphere(0.12, 0.865, 0.05, 0.016, "M_plate_white", seg=8, rings=5)
    B.cbox(-w / 2, 0.0, -d / 2, w / 2, 1.0, d / 2)


def blue_table(B, w=3.2, d=1.4):
    B.box(-w / 2, 0.73, -d / 2, w / 2, 0.77, d / 2, "M_table_blue")
    B.box(-w / 2 - 0.01, 0.715, -d / 2 - 0.01, w / 2 + 0.01, 0.73, d / 2 + 0.01, "M_wood_oak")
    for sx in (-1, 1):
        for sz in (-1, 1):
            B.box(sx * (w / 2 - 0.08) - 0.025, 0.0, sz * (d / 2 - 0.08) - 0.025, sx * (w / 2 - 0.08) + 0.025, 0.715,
                  sz * (d / 2 - 0.08) + 0.025, "M_paint_metal_dark")
    B.cbox(-w / 2, 0.0, -d / 2, w / 2, 0.77, d / 2)


def shelf_unit(B):
    """1.4 x 1.8 x 0.35 steel shelving with boxes, binders and board games; top exactly at 1.8"""
    w, h, d = 1.4, 1.8, 0.35
    for sx in (-w / 2 + 0.02, w / 2 - 0.02):
        for sz in (-d / 2 + 0.02, d / 2 - 0.02):
            B.box(sx - 0.02, 0.0, sz - 0.02, sx + 0.02, h, sz + 0.02, "M_paint_metal_dark")
    rng = random.Random(9)
    cols = ["M_plastic_red", "M_plastic_yellow", "M_plastic_blue", "M_plastic_white", "M_plastic_green", "M_cardboard", "M_plastic_orange"]
    for j, y in enumerate((0.08, 0.5, 0.92, 1.34, h - 0.02)):
        B.box(-w / 2, y, -d / 2, w / 2, y + 0.02, d / 2, "M_paint_metal_dark")
        if y > h - 0.1:
            continue
        x = -w / 2 + 0.06
        while x < w / 2 - 0.12:
            kind = rng.random()
            if kind < 0.45:
                bw, bh = rng.uniform(0.18, 0.32), rng.uniform(0.16, 0.3)
                B.box(x, y + 0.02, -0.15, x + bw, y + 0.02 + bh, 0.15, cols[rng.randrange(len(cols))])
                x += bw + 0.03
            else:
                for k in range(rng.randrange(3, 8)):
                    bw = rng.uniform(0.03, 0.06)
                    if x + bw > w / 2 - 0.06:
                        break
                    bh = rng.uniform(0.22, 0.32)
                    B.box(x, y + 0.02, -0.12, x + bw, y + 0.02 + bh, 0.13, cols[rng.randrange(len(cols))])
                    x += bw + 0.004
                x += 0.05
    B.cbox(-w / 2, 0.0, -d / 2, w / 2, h, d / 2)


def arcade(B):
    B.box(-0.35, 0.0, -0.37, 0.35, 1.75, 0.3, "M_arcade_purple")
    with B.at(0, 1.12, 0.3, 0.0, 0.22):
        B.box(-0.3, 0.0, -0.04, 0.3, 0.44, 0.0, "M_plastic_black")
        B.quad((-0.27, 0.03, 0.001), (0.27, 0.03, 0.001), (0.27, 0.41, 0.001), (-0.27, 0.41, 0.001), "M_screen_4", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.box(-0.35, 0.86, 0.3, 0.35, 0.95, 0.52, "M_plastic_black")
    with B.at(0, 0.95, 0.42, 0.0, -0.25):
        B.box(-0.35, 0.0, -0.12, 0.35, 0.03, 0.12, "M_arcade_purple")
        B.cyl(-0.18, 0.03, 0.0, 0.01, 0.07, "M_chrome", seg=6)
        B.sphere(-0.18, 0.1, 0.0, 0.025, "M_plastic_red", seg=8, rings=5)
        for k in range(6):
            B.cyl(0.0 + (k % 3) * 0.07, 0.03, -0.035 + (k // 3) * 0.06, 0.02, 0.01, "M_plastic_yellow" if k % 2 else "M_plastic_blue", seg=10)
    B.box(-0.35, 1.6, 0.3, 0.35, 1.75, 0.33, "M_neon_pink")
    B.box(-0.37, 0.0, -0.37, -0.35, 1.75, 0.33, "M_neon_blue")
    B.box(0.35, 0.0, -0.37, 0.37, 1.75, 0.33, "M_neon_blue")
    B.cbox(-0.37, 0.0, -0.37, 0.37, 1.75, 0.52)


def beanbag(B, mat="M_beanbag_red"):
    B.sphere(0, 0.27, 0, 0.45, mat, seg=14, rings=8, sy=0.62)
    B.sphere(0.05, 0.42, -0.12, 0.25, mat, seg=10, rings=6, sy=0.7)
    B.cbox(-0.35, 0.0, -0.35, 0.35, 0.45, 0.35)


def beanbag_red(B):
    beanbag(B, "M_beanbag_red")


def beanbag_blue(B):
    beanbag(B, "M_beanbag_blue")


def beanbag_lime(B):
    beanbag(B, "M_beanbag_lime")


# ------------------------------------------------------------------ plants (indoor)
def plant_pot(B, s=1.0, pot="M_pot_white"):
    """indoor plant (rubber fig / monstera style): pot + stems + leaf cards"""
    B.cyl(0, 0.0, 0, 0.2 * s, 0.42 * s, pot, seg=16, r2=0.24 * s)
    B.cyl(0, 0.4 * s, 0, 0.22 * s, 0.01, "M_soil", seg=16)
    rng = random.Random(int(s * 100))
    for k in range(9):
        a = rng.uniform(0, 2 * PI)
        h = rng.uniform(0.6, 1.25) * s
        r = rng.uniform(0.08, 0.3) * s
        tip = (math.cos(a) * r, 0.42 * s + h, math.sin(a) * r)
        B.tube([(0, 0.42 * s, 0), (tip[0] * 0.4, 0.42 * s + h * 0.5, tip[2] * 0.4), tip], 0.008 * s, "M_moss", seg=5, caps=False)
        for j in range(3):
            t = 0.5 + j * 0.25
            c = Vector((tip[0] * t, 0.42 * s + h * t, tip[2] * t))
            ang = a + rng.uniform(-0.6, 0.6)
            right = Vector((math.cos(ang + PI / 2), 0, math.sin(ang + PI / 2))) * 0.13 * s
            up = Vector((math.cos(ang) * 0.5, 0.75, math.sin(ang) * 0.5)).normalized() * 0.2 * s
            q = rng.randrange(4)
            uv = ((q % 2) * 0.5, (q // 2) * 0.5, (q % 2) * 0.5 + 0.5, (q // 2) * 0.5 + 0.5)
            B.card(c + up * 0.6, right, up, "M_leaves_plane", uv=uv, normal=(0, 1, 0))
    B.cbox(-0.22 * s, 0.0, -0.22 * s, 0.22 * s, 0.8 * s, 0.22 * s)


def plant_lobby(B):
    plant_pot(B, 1.15)


def plant_small(B):
    plant_pot(B, 0.85, "M_pot_dark")


# ------------------------------------------------------------------ extra lobby / cafeteria / Under props
def rollup_banner(B):
    """roll-up stand banner 0.85 x 2.1 m, print on +Z"""
    chbox(B, -0.43, 0.0, -0.12, 0.43, 0.1, 0.12, "M_alu_silver", c=0.04)
    B.cyl(0.0, 0.1, -0.05, 0.012, 2.0, "M_alu_silver", seg=6)
    B.quad((-0.42, 0.1, 0.001), (0.42, 0.1, 0.001), (0.42, 2.12, 0.001), (-0.42, 2.12, 0.001), "M_rollup", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.quad((0.42, 0.1, -0.001), (-0.42, 0.1, -0.001), (-0.42, 2.12, -0.001), (0.42, 2.12, -0.001), "M_plate_white")
    B.box(-0.43, 2.1, -0.012, 0.43, 2.13, 0.012, "M_alu_silver")
    B.cbox(-0.43, 0.0, -0.12, 0.43, 2.13, 0.12)


def water_cooler(B):
    chbox(B, -0.16, 0.0, -0.16, 0.16, 0.98, 0.16, "M_plastic_white", c=0.03)
    B.box(-0.1, 0.62, 0.16, 0.1, 0.8, 0.2, "M_plastic_dark")
    for x, m in ((-0.04, "M_plastic_blue"), (0.04, "M_plastic_red")):
        B.box(x - 0.015, 0.76, 0.19, x + 0.015, 0.79, 0.22, m)
    B.cyl(0, 0.98, 0, 0.13, 0.32, "M_glass_clear", seg=16, r2=0.135)
    B.cyl(0, 1.3, 0, 0.135, 0.05, "M_glass_clear", seg=16, r2=0.06)
    B.cbox(-0.17, 0.0, -0.17, 0.17, 1.35, 0.17)


def wet_floor_sign(B):
    for s in (-1, 1):
        with B.at(0, 0, s * 0.11, 0.0, s * 0.2):
            B.box(-0.15, 0.0, -0.01, 0.15, 0.62, 0.01, "M_plastic_yellow")
    with B.at(0, 0.32, 0.17, 0.0, 0.2):
        B.box(-0.1, -0.08, 0.0, 0.1, 0.12, 0.002, "M_plastic_black")


def fridge_drinks(B):
    """glass-door drinks fridge, lit"""
    B.box(-0.35, 0.0, -0.35, 0.35, 1.95, 0.32, "M_plastic_white")
    B.box(-0.32, 0.12, 0.1, 0.32, 1.72, 0.32, "M_vend_glow", skip="s")
    cols = ["M_plastic_red", "M_plastic_green", "M_plastic_orange", "M_plastic_blue", "M_plastic_yellow"]
    for r in range(5):
        y = 0.18 + r * 0.31
        B.box(-0.31, y - 0.012, 0.12, 0.31, y, 0.3, "M_chrome")
        for k in range(7):
            x = -0.27 + k * 0.09
            B.cyl(x, y, 0.22, 0.03, 0.2 if r % 2 else 0.24, cols[(r + k) % 5], seg=8)
    B.quad((-0.33, 0.1, 0.325), (0.33, 0.1, 0.325), (0.33, 1.75, 0.325), (-0.33, 1.75, 0.325), "M_glass_clear", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    for (a, b, c, d) in ((-0.35, 0.08, -0.33, 1.77), (0.33, 0.08, 0.35, 1.77)):
        B.box(a, b, 0.32, c, d, 0.335, "M_plastic_dark")
    B.box(-0.35, 0.08, 0.32, 0.35, 0.1, 0.335, "M_plastic_dark")
    B.box(-0.35, 1.75, 0.32, 0.35, 1.95, 0.335, "M_plastic_red")
    with B.at(0, 1.81, 0.336):
        B.text("FRAIS", CM_font("black"), 0.09, "M_plate_white", align="CENTER")
    B.box(0.27, 0.6, 0.335, 0.3, 1.2, 0.36, "M_alu_silver")
    B.cbox(-0.35, 0.0, -0.35, 0.35, 1.95, 0.36)


def cash_register(B):
    chbox(B, -0.18, 0.0, -0.15, 0.18, 0.08, 0.15, "M_plastic_dark", c=0.02)
    with B.at(0, 0.08, -0.05, 0.0, 0.5):
        B.box(-0.14, 0.0, -0.01, 0.14, 0.2, 0.01, "M_plastic_black")
        B.quad((-0.12, 0.02, 0.0105), (0.12, 0.02, 0.0105), (0.12, 0.18, 0.0105), (-0.12, 0.18, 0.0105), "M_screen_3", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.box(0.2, 0.0, -0.06, 0.32, 0.08, 0.08, "M_plastic_dark")
    B.box(0.22, 0.08, -0.02, 0.3, 0.1, 0.06, "M_led_green")


def tray_stack(B):
    for k in range(6):
        B.box(-0.22, k * 0.018, -0.16, 0.22, k * 0.018 + 0.012, 0.16, "M_plastic_orange" if k % 2 else "M_plastic_dark")


def tv_unit(B):
    """low TV cabinet + wall-height flat screen showing a game (Under)"""
    B.box(-0.9, 0.0, -0.22, 0.9, 0.45, 0.22, "M_wood_dark")
    B.box(-0.88, 0.05, 0.22, 0.88, 0.4, 0.225, "M_plastic_black")
    B.box(-0.2, 0.45, -0.1, 0.2, 0.47, 0.1, "M_plastic_black")
    B.box(-0.03, 0.47, -0.05, 0.03, 0.62, -0.02, "M_plastic_black")
    B.box(-0.62, 0.6, -0.06, 0.62, 1.32, -0.02, "M_plastic_black")
    B.quad((-0.6, 0.62, -0.019), (0.6, 0.62, -0.019), (0.6, 1.3, -0.019), (-0.6, 1.3, -0.019), "M_screen_5", uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    B.box(0.3, 0.45, -0.05, 0.6, 0.5, 0.15, "M_plastic_white")
    for x in (-0.5, -0.3):
        chbox(B, x - 0.07, 0.45, 0.05, x + 0.07, 0.48, 0.15, "M_plastic_black", c=0.02)
    B.cbox(-0.9, 0.0, -0.22, 0.9, 1.32, 0.22)


# ------------------------------------------------------------------ registry + export
def registry():
    import campus_props_out as O
    R = {
        "pc_desk_0": (pc_desk, {"screen": "M_screen_0"}), "pc_desk_1": (pc_desk, {"screen": "M_screen_1"}),
        "pc_desk_2": (pc_desk, {"screen": "M_screen_2"}), "pc_desk_3": (pc_desk, {"screen": "M_screen_3"}),
        "pc_desk_4": (pc_desk, {"screen": "M_screen_4"}), "pc_desk_5": (pc_desk, {"screen": "M_screen_5"}),
        "office_chair": (office_chair, {}), "desk_office": (desk_office, {}),
        "lockers_4": (lockers_4, {}), "vending_red": (vending_red, {}), "vending_blue": (vending_blue, {}),
        "coffee_machine": (coffee_machine, {}), "microwave": (microwave, {}), "cafe_table": (cafe_table, {}),
        "stool_red": (stool_red, {}), "stool_blue": (stool_blue, {}), "bench_oak": (bench_oak, {}),
        "sofa_navy": (sofa_navy, {}), "armchair_mustard": (armchair_mustard, {}), "round_sofa": (round_sofa, {}),
        "low_table": (low_table, {}), "drum_lamp": (drum_lamp, {}), "stanchion": (stanchion, {}),
        "wall_clock": (wall_clock, {}), "extinguisher": (extinguisher, {}), "exit_sign": (exit_sign, {}),
        "lectern": (lectern, {}), "laptop": (laptop, {}), "backpack_navy": (backpack_navy, {}),
        "backpack_red": (backpack_red, {}), "backpack_green": (backpack_green, {}), "bottle": (bottle, {}),
        "bins_tri": (bins_tri, {}), "amphi_row_l": (amphi_row_l, {}), "amphi_row_r": (amphi_row_r, {}),
        "babyfoot": (babyfoot, {}), "blue_table": (blue_table, {}), "shelf_unit": (shelf_unit, {}),
        "arcade": (arcade, {}), "beanbag_red": (beanbag_red, {}), "beanbag_blue": (beanbag_blue, {}),
        "beanbag_lime": (beanbag_lime, {}), "plant_lobby": (plant_lobby, {}), "plant_small": (plant_small, {}),
        "rollup_banner": (rollup_banner, {}), "water_cooler": (water_cooler, {}), "wet_floor_sign": (wet_floor_sign, {}),
        "fridge_drinks": (fridge_drinks, {}), "cash_register": (cash_register, {}), "tray_stack": (tray_stack, {}),
        "tv_unit": (tv_unit, {}),
    }
    R.update(O.registry())
    return R


def build_prop(name, fn, kw):
    B = G.Builder()
    B.auto_sub = False
    B.use(name)
    B.use_col(name)
    with B.ground_at(0.0):
        fn(B, **kw)
    coll = bpy.data.collections.new("PROP_" + name)
    obs = G.commit_parts(B, coll)
    for ob in G.commit_colliders(B, coll):
        ob.name = name + "_col-colonly"
    tris = sum(p.tri_count() for p in B.parts.values())
    return coll, tris


def build_all(export_scene, log, only=None):
    os.makedirs(PROPS_DIR, exist_ok=True)
    R = registry()
    total = {}
    for name, (fn, kw) in R.items():
        if only and name not in only:
            continue
        coll, tris = build_prop(name, fn, kw)
        sc = bpy.data.scenes.new("prop_" + name)
        sc.collection.children.link(coll)
        size = export_scene(sc, os.path.join(PROPS_DIR, name + ".glb"), "prop_" + name)
        total[name] = tris
        bpy.data.scenes.remove(sc)
        log(f"prop {name}: {tris} tris, {size / 1024:.0f} KB")
    import json
    with open(os.path.join(ROOT, "tools", "out", "campus_cache", "prop_tris.json"), "w") as f:
        json.dump(total, f, indent=1)
    return total
