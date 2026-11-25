"""Gameplay markers (Empties with glTF extras) - every position comes from the old Campus.js."""
import math
from campus_layout import *

PI = math.pi
AMPHI_EDGE = 0.01     # seat pan front edge relative to the tier centre (rows face the stage, -Z)
PC_EDGE = 0.5         # PC chairs stand at desk z + 0.75 facing north; seat front edge 0.25 in front of it


def V(x, y, z):
    return (float(x), float(y), float(z))


def npcs():
    t3, t5 = tier(3), tier(5)
    th = step_seat(0.45, 1.8)
    mx, mz = cafe_pt(10.9, 7.3)
    cx, cz = cafe_pt(12.6, 8.55)
    sx, sz = cafe_pt(7.0, 3.65)
    stx, stz = cafe_pt(7.0, 3.0)
    _d = math.hypot(stx - sx, stz - sz)
    sx, sz = sx + (stx - sx) / _d * 0.19, sz + (stz - sz) / _d * 0.19
    return [
        dict(id="toma", name="Toma", model="npc_toma", pos=V(17.55, t3["y"], t3["z"] + AMPHI_EDGE), yaw=PI, sit=True, color="#2f5d9f", range=2.2),
        dict(id="prof", name="M. Bernard", model="npc_prof", pos=V(18.2, AY, 7.4), yaw=0.0, color="#a0826d", range=2.6),
        dict(id="sleeper", name="Sleepy SUP", model="npc_lucas", pos=V(24.5, t5["y"], t5["z"] + AMPHI_EDGE), yaw=PI, sit=True, sleep=True, no_look=True, color="#e67e22"),
        dict(id="ian", name="Ian", model="friend_ian", pos=V(5.0, 0, 28.0), yaw=PI / 2, color="#b38a5e", range=2.2),
        dict(id="silvia", name="Silvia", model="friend_silvia", pos=V(7.0, 0, 28.0), yaw=-PI / 2, color="#e7a07a", range=2.2),
        dict(id="yanis", name="Yanis", model="npc_yanis", pos=V(10, 0, 20), yaw=0.0, color="#5d6d7e",
             path=[[10, 0, 20], [22, 0, 27], [16, 0, 33], [4, 0, 31], [2.2, 0, 27.5]]),   # loops back west of Ian & Silvia's table
        dict(id="theo", name="Theo", model="npc_student2", pos=V(th[0], 1.26 - 0.45, th[1]), yaw=th[2], sit=True, color="#16a085"),
        dict(id="anisha", name="Anisha", model="friend_anisha", pos=V(-12.25, F1, -20.6 + PC_EDGE), yaw=PI, sit=True, color="#3fbf8a", range=2.0),
        dict(id="acu", name="ACU Leo", model="npc_acu", pos=V(-14, F1, -14), yaw=PI / 2, color="#e74c3c", path=[[-14, F1, -14], [6, F1, -14]]),
        dict(id="student2", name="Piscine survivor", model="npc_student2", pos=V(1.75, F1, -17.8 + PC_EDGE), yaw=PI, sit=True, color="#27ae60"),
        dict(id="ines", name="Ines", model="npc_ines", pos=V(-7.9, F1, -23.6 + PC_EDGE), yaw=PI, sit=True, color="#e84393"),
        dict(id="karim", name="Karim (BDE)", model="npc_karim", pos=V(15, UY, 45.1), yaw=0.0, color="#e8b923", range=2.2),
        dict(id="chloe", name="Chloe (BDE)", model="npc_chloe", pos=V(4.2 + 0.42, UY, 43.1), yaw=PI / 2, sit=True, color="#16a085"),
        dict(id="madame", name="Mme Dupont", model="npc_madame", pos=V(mx, 0.02, mz), yaw=math.atan2(cx - mx, cz - mz), color="#6c5ce7", when="!coffeeGiven"),
        dict(id="madame2", name="Mme Dupont", model="npc_madame", pos=V(-3.4, 0, -24.25), yaw=0.0, color="#6c5ce7", range=2.4, when="coffeeGiven"),
        dict(id="student3", name="SPE student", model="npc_student3", pos=V(sx, 0.02, sz), yaw=math.atan2(stx - sx, stz - sz), sit=True, color="#8e44ad"),
        dict(id="waiting", name="Waiting student", model="npc_theo", pos=V(-7, 0, -8.2), yaw=PI, sit=True, color="#95a5a6"),
    ]


def spots():
    c = cafe_pt(12.6, 7.7)
    v = cafe_pt(2.1, 7.8)
    return [
        # no Velib' station on rue Pasteur, only bike stands; the id stays for the story text
        dict(id="velib", pos=V(14.9, 0.1, 3.75), range=2.0, label="Look at the bike rack"),
        dict(id="sign", pos=V(-3.6, 0, -22.6), range=1.8, label="Read the note on the desk", when="!coffeeGiven"),
        dict(id="lostbox", pos=V(-1.5, 0, -22.6), range=1.6, label="Lost & found box", when="!coffeeGiven"),
        # inside the doors of KB1's middle bay on rue Voltaire (campus_kb1.BAYS_N)
        dict(id="north_door", pos=V(-3.3, 0, -32.0), range=2.4, label="Rue Voltaire doors"),
        dict(id="logo", pos=V(-21, 0, -10.5), range=2.2, label="EPITA wall"),
        dict(id="elevator", pos=V(7.1, 0, -24.8), range=1.7, label="Elevator"),
        dict(id="rules", pos=V(-6, F1, -14.8), range=1.8, label="Read the poster"),
        dict(id="coffee", pos=V(c[0], 0, c[1]), range=1.6, label="Coffee machine"),
        dict(id="vending", pos=V(v[0], 0, v[1]), range=1.6, label="Vending machines"),
        dict(id="slide", pos=V(18.75, AY, 8.9), range=2.4, label="Read the slide"),
        dict(id="gate", pos=V(2, 0, 49.6), range=2.0, label="Gate to rue Roger Salengro"),   # street end of the south passage
        dict(id="coin_planter", pos=V(14, 0, 33.0), range=1.7, label="Planter"),   # south edge of the birch planter
        dict(id="stickers", pos=V(9, UY, 46.6), range=1.6, label="Sticker column"),
        dict(id="coin_sofa", pos=V(4.9, UY, 42.5), range=1.5, label="Sofa"),
    ]


def anchors():
    cx, cz = cafe_pt(12.6, 8.55)
    return [
        dict(id="lostfound", pos=V(-3.2, 1.1, -23.25), yaw=0.0),
        dict(id="pcSeat", pos=V(-10.8, F1, -20.6 + 0.62), yaw=PI, cam_from=[-9.85, F1 + 1.75, -18.8], cam_look=[-10.8, F1 + 1.05, -20.78]),
        dict(id="coffee", pos=V(cx, 0, cz), yaw=SE_YAW + PI),
        dict(id="babyfoot", pos=V(15, UY, 46), yaw=0.0),
        dict(id="babyfootSpot", pos=V(15, UY, 46.85), yaw=PI),
    ]


def ducks():
    ds = step_seat(0.92)
    cc = cafe_pt(15.3, 6.6)
    return [
        dict(id="amphi", pos=V(15.4, AY + 0.075, 6.9)),
        dict(id="sm15", pos=V(6.55, F1 + 0.76 + 0.075, -23.45)),
        dict(id="intl", pos=V(-15.0, 0.76 + 0.075, -23.15)),
        dict(id="steps", pos=V(ds[0] + math.sin(ds[2]) * 1.5, 0.42 + 0.075, ds[1] + math.cos(ds[2]) * 1.5)),
        dict(id="cafe", pos=V(cc[0], 1.095 + 0.075, cc[1])),
        dict(id="under", pos=V(12, UY + 1.8 + 0.075, 51.62)),
        dict(id="car", pos=V(-26.2, 1.5 + 0.075, 1.6)),
        dict(id="ramp", pos=V(28.1, UY + 0.075, 38.85)),
    ]


def crowd():
    def sofa_seat(cx, cz, a):
        # old sofaSeat (radius 1.3 = segment centre) moved to the cushion front edge, radius 0.92
        return (cx + math.sin(a) * 0.92, cz + math.cos(a) * 0.92, a + PI)

    def cafe_seat(lx, lz, tx, tz):
        # stool centre (old position) moved 0.19 towards the table = front edge of the round seat
        x, z = cafe_pt(lx, lz)
        ax, az = cafe_pt(tx, tz)
        d = math.hypot(ax - x, az - z)
        return dict(pos=V(x + (ax - x) / d * 0.19, 0.02, z + (az - z) / d * 0.19), yaw=math.atan2(ax - x, az - z))
    t4, t2 = tier(4), tier(2)
    s1 = sofa_seat(-19.5, -8.9, -0.45)
    s2 = sofa_seat(-19.5, -8.9, 0.45)
    walkers = [
        dict(model="npc_crowd1", path=[[4, 0, 17], [12, 0, 22], [20, 0, 23.5], [19, 0, 32], [9, 0, 34], [2, 0, 27]], loop=True, speed=1.0),
        dict(model="npc_crowd5", path=[[19, 0, 32], [9, 0, 34], [2, 0, 27], [4, 0, 17], [12, 0, 22], [20, 0, 23.5]], loop=True, speed=1.0),
        dict(model="npc_crowd2", path=[[3.15, 0, 15], [3.15, 0.1, 4.4], [-12, 0.1, 4.4], [-30, 0.1, 4.4]], loop=False, speed=1.0),
        dict(model="npc_crowd6", path=[[-30, 0.1, -3.9], [-12, 0.1, -3.9], [18, 0.1, -3.9]], loop=False, speed=1.3),   # clear of KB1's bays and portal
        dict(model="npc_crowd7", path=[[-21, 0, -10], [-12, 0, -10], [8, 0, -10], [16, 0, -10]], loop=False, speed=1.0),
    ]
    static = [
        dict(model="npc_crowd3", pos=V(16.2, 0, 26.7), yaw=-2.0, talk=True),   # trio and pair kept off the walker lines
        dict(model="npc_crowd4", pos=V(17.6, 0, 26.0), yaw=2.5, talk=True),
        dict(model="npc_crowd8", pos=V(17.3, 0, 27.6), yaw=3.7, talk=True),
        dict(model="npc_crowd2", pos=V(13.0, 0, 20.2), yaw=0.7, talk=True),
        dict(model="npc_crowd1", pos=V(14.0, 0, 20.9), yaw=-2.4, talk=True),
        dict(model="npc_crowd5", pos=V(s1[0], 0, s1[1]), yaw=s1[2], sit=True, talk=True),
        dict(model="npc_crowd3", pos=V(s2[0], 0, s2[1]), yaw=s2[2], sit=True),
        dict(model="npc_crowd4", sit=True, talk=True, **cafe_seat(3.5, 3.65, 3.0, 3.0)),
        dict(model="npc_crowd8", sit=True, **cafe_seat(8.0, 6.65, 8.0, 6.0)),
        dict(model="npc_crowd6", sit=True, talk=True, **cafe_seat(12.5, 2.35, 12.0, 3.0)),
        dict(model="npc_crowd7", pos=V(5.8, UY, 48.5 + 0.25), yaw=0.0, sit=True),
        dict(model="npc_crowd1", pos=V(8.2, UY, 50.5 - 0.25), yaw=PI, sit=True, talk=True),
        dict(model="npc_crowd2", pos=V(21.5, UY, 48.5 + 0.25), yaw=0.0, sit=True),
        dict(model="npc_crowd8", pos=V(14.2, UY, 44.4), yaw=0.3, talk=True),
        dict(model="npc_crowd3", pos=V(-1.15, F1, -20.6 + PC_EDGE), yaw=PI, sit=True),
        dict(model="npc_crowd5", pos=V(4.65, F1, -23.6 + PC_EDGE), yaw=PI, sit=True),
        dict(model="npc_crowd4", pos=V(-15.15, F1, -17.8 + PC_EDGE), yaw=PI, sit=True),
        dict(model="npc_crowd6", pos=V(13.0, t4["y"], t4["z"] + AMPHI_EDGE), yaw=PI, sit=True),
        dict(model="npc_crowd7", pos=V(22.6, t2["y"], t2["z"] + AMPHI_EDGE), yaw=PI, sit=True),
    ]
    return walkers, static


def zones():
    cx, cz = cafe_pt(SE_LEN / 2, CAFE_D / 2)

    def box(x0, x1, y0, y1, z0, z1):
        return dict(pos=V((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), half=((x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2), yaw=0.0)
    return [
        dict(id="under", label="The Under", sub="BDE  -  basement of cour Pasteur", surface="rubber", priority=10, **box(1.7, 28.7, -4.4, -1.6, 36.0, 52.3)),
        dict(id="sm14", label="SM14", sub="Batiment Voltaire  -  1st floor", surface="carpet", priority=9, **box(-18.0, -4.0, 2.4, 7.2, -26.0, -16.0)),
        dict(id="sm15", label="SM15", sub="Batiment Voltaire  -  1st floor", surface="carpet", priority=9, **box(-4.0, 8.0, 2.4, 7.2, -26.0, -16.0)),
        dict(id="volt_f1", label="Batiment Voltaire", sub="1st floor", surface="tile", priority=8, **box(-18.0, 13.0, 2.4, 7.2, -26.0, -12.0)),
        dict(id="volt_gf", label="Batiment Voltaire", sub="ground floor  -  accueil", surface="tile", priority=8, **box(-29.3, 22.4, -0.5, 2.4, -33.7, -5.0)),
        dict(id="amphi", label="Amphi 4", sub="cour Pasteur  -  east building", surface="carpet", priority=7, **box(9.5, 28.0, -3.0, 1.0, 6.0, 18.4)),
        dict(id="cafe", label="Cafeteria", sub="X building  -  cour Pasteur", surface="tile", priority=7,
             pos=V(cx, 1.25, cz), half=(SE_LEN / 2, 1.75, CAFE_D / 2), yaw=SE_YAW),
        dict(id="passage", label="Cour Pasteur", sub="passage couvert  -  24 rue Pasteur", surface="concrete", priority=6, **box(0.0, 6.7, -0.5, 4.2, 6.2, 14.3)),
        # between the gameplay walls (campus_backdrop.WALL_W / WALL_E), the junction's corners included; it stops where
        # cour Pasteur starts (z 14), the passage, Amphi 4 and KB1 win where they overlap it
        dict(id="street", label="Rue Pasteur", sub="Le Kremlin-Bicetre", surface="concrete", priority=5, **box(-48.0, 46.5, -1.0, 6.0, -13.5, 14.0)),
        dict(id="court", label="Cour Pasteur", sub="EPITA Paris  -  KB campus", surface="concrete", priority=1, **box(-13.5, 33.5, -1.6, 8.0, 14.0, 50.6)),
    ]


def portals():
    co, ci = cafe_pt(8, -1.6), cafe_pt(8, 1.4)
    return {
        "amphi__court": [V(16, 0, 17.6), V(16, 0, 19.6)],
        "court__passage": [V(3.1, 0, 15.6), V(3.2, 0, 13.4)],
        "passage__street": [V(3.35, 0, 8.0), V(3.35, 0.1, 4.6)],
        "court__under": [V(11, 0, 37.7), V(26.6, UY, 37.8), V(27, UY, 40.6)],
        "court__cafe": [V(co[0], 0, co[1]), V(ci[0], 0, ci[1])],
        "street__volt_gf": [V(9.3, 0.1, -4.4), V(9.3, 0, -7)],
        "volt_gf__volt_f1": [V(11.75, 0, -11.9), V(11.75, F1, -19.6), V(9.3, F1, -17.5), V(9.3, F1, -14)],
        "volt_f1__sm14": [V(-11, F1, -14.4), V(-11, F1, -17.2)],
        "volt_f1__sm15": [V(2, F1, -14.4), V(2, F1, -17.2)],
    }


SPAWN = dict(pos=V(18.75, -0.81 + 0.05, 14.0), yaw=PI)
TITLE_SHOT = dict(frm=V(25, 7, 37), look=V(3, 3, 20), fov=55.0)


def place_all(B):
    for n in npcs():
        ex = {k: v for k, v in n.items() if k not in ("id", "pos", "yaw")}
        ex["yaw"] = n["yaw"]
        ex.setdefault("sit", False)
        ex.setdefault("sleep", False)
        B.marker("NPC_" + n["id"], n["pos"], n["yaw"], ex, display="SINGLE_ARROW", size=0.5)
    for s in spots():
        ex = {k: v for k, v in s.items() if k not in ("id", "pos")}
        B.marker("SPOT_" + s["id"], s["pos"], 0.0, ex, display="SPHERE", size=0.25)
    for a in anchors():
        ex = {k: v for k, v in a.items() if k not in ("id", "pos")}
        B.marker("ANCHOR_" + a["id"], a["pos"], a["yaw"], ex, display="ARROWS", size=0.3)
    for d in ducks():
        B.marker("DUCK_" + d["id"], d["pos"], 0.0, {}, display="SPHERE", size=0.08)
    walkers, static = crowd()
    for i, w in enumerate(walkers):
        for k, p in enumerate(w["path"]):
            B.marker("PATH_crowd%02d_%02d" % (i, k), V(*p), 0.0, dict(loop=w["loop"], model=w["model"], speed=w["speed"]),
                     display="PLAIN_AXES", size=0.3)
    for i, c in enumerate(static):
        ex = {k: v for k, v in c.items() if k not in ("pos",)}
        ex.setdefault("sit", False)
        ex.setdefault("talk", False)
        ex["crowd"] = True
        B.marker("NPC_crowd_%02d" % i, c["pos"], c["yaw"], ex, display="SINGLE_ARROW", size=0.4)
    for z in zones():
        ex = dict(label=z["label"], sub=z["sub"], surface=z["surface"], priority=z["priority"])
        B.marker("ZONE_" + z["id"], z["pos"], z["yaw"], ex, display="CUBE", half=z["half"], size=1.0)
    for key, pts in portals().items():
        for k, p in enumerate(pts):
            B.marker("PORTAL_%s_%02d" % (key, k), p, 0.0, {}, display="PLAIN_AXES", size=0.4)
    B.marker("SPAWN_player", SPAWN["pos"], SPAWN["yaw"], dict(yaw=SPAWN["yaw"]), display="SINGLE_ARROW", size=0.6)
