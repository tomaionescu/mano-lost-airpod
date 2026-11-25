"""Review renders of a character .glb for a head scan, and comparison sheets of them.

Blender (85 mm lens, EEVEE, rest pose):
  Blender -b -P tools/dev/head_scan_review.py -- <file.glb> <outprefix> [set=neck|ear|eyes|extra] [only=a,b] [res=800]
      [hide=<name>,...] [nohair=1] [head=<png>] [body=<png>] [key=1]
  default set: f75, r3475, l3475, rp75, lp75 (0.75 m: front, both three-quarters, both profiles), the same at 0.3 m
  (f30 ...), clay_f ... (lit clay), under (from below), back. neck: both sides and front of the neck, both ears,
  both temples (each also in clay). ear: both ears at 0.18 m, with each hair layer hidden in turn. eyes: each eye and
  the nose in clay and textured. extra: the nape at 0.35 m and dialogue framing at 1.35 m. head=<png> swaps the head's
  colour map (to try a texture pass without a rebuild); nohair=1 hides the cards, underlayer and cap. key=1 lights the
textured shots with a key light from the camera's upper left (as the game lights faces) instead of the even world
light alone, which hides what a normal map does (a bright wedge on the neck shows only under a key light).
set=eyeprof: each eye from its side at 0.15 m (90 and 70 deg), clay and without lashes. set=chin: the chin and jaw in
clay and textured (front, both three-quarters, both profiles, from below), set=lobe: below each ear at 0.2 m (textured
and clay, no hair). set=temple: both temples and ears at 0.4 m (three-quarter and profile) with and without hair.
set=r4: close checks at 0.22-0.3 m (nostrils from below, sideburns, under each lobe, the ears' tops, the nape, the
neck's sides, the eyes in profile, the crown, both eyes shut) and the back down to the knees (backbody). set=r5: the
nape and the hood's top from behind and above, the hair at 0.55 m from the front, 30 deg and both profiles, the
temples and ears' tops at 0.3 m, the lashes at 45 deg. body=<png> swaps the body's colour map.
python3.11 (sheets):
  python3.11 tools/dev/head_scan_review.py sheet <out.png> <size> <view,view,...> <prefix|portrait> ...
  a grid, one row per view, one column per render prefix ("portrait": the outfit's portrait, cropped for f30 / f75).
"""
import sys, os, math


def sheet(argv):
    from PIL import Image, ImageDraw
    out, size, views = argv[0], int(argv[1]), argv[2].split(",")
    pres = argv[3:]
    port = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scans", "toma", "portrait.png")
    c = Image.new("RGB", (size * len(pres), size * len(views)), (40, 40, 40))
    d = ImageDraw.Draw(c)
    for r, v in enumerate(views):
        for k, p in enumerate(pres):
            try:
                if p == "portrait":
                    im = Image.open(port).convert("RGB")
                    w, h = im.size
                    if v.startswith("f30"):
                        im = im.crop((int(w * .28), int(h * .3), int(w * .72), int(h * .74)))
                    elif v.startswith("f75"):
                        im = im.crop((int(w * .1), int(h * .02), int(w * .9), int(h * .82)))
                else:
                    im = Image.open(f"{p}_{v}.png").convert("RGB")
            except Exception:
                continue
            c.paste(im.resize((size, size)), (k * size, r * size))
            d.text((k * size + 5, r * size + 5), f"{os.path.basename(p)} {v}", fill=(255, 255, 0))
    c.save(out)


try:
    import bpy
    from mathutils import Vector
except ImportError:
    bpy = None
if bpy is None:
    if len(sys.argv) > 2 and sys.argv[1] == "sheet":
        sheet(sys.argv[2:])
    else:
        print(__doc__)
    sys.exit(0)
argv = sys.argv[sys.argv.index("--") + 1:]
glb, pre = argv[0], argv[1]
opts = dict(a.split("=", 1) for a in argv[2:] if "=" in a)
only = set(opts["only"].split(",")) if "only" in opts else None
RES = int(opts.get("res", 800))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
for o in sc.objects:
    if o.name.startswith("Icosphere"):
        o.hide_render = True
meshes = [o for o in sc.objects if o.type == 'MESH' and not o.name.startswith("Icosphere")]
if opts.get("head"):
    hi = bpy.data.images.load(opts["head"])
    for mt in bpy.data.materials:
        if mt.name.endswith("skin_head") and mt.node_tree:
            for nd in mt.node_tree.nodes:
                if nd.type == 'TEX_IMAGE' and nd.image and not any(l.to_node.type == 'NORMAL_MAP' for o_ in nd.outputs for l in o_.links):
                    print("head image", nd.image.name, "->", hi.name)
                    nd.image = hi
if opts.get("body"):
    bi = bpy.data.images.load(opts["body"])
    for mt in bpy.data.materials:
        if (mt.name.endswith("skin_Human") or mt.name.endswith("cloth_scan")) and mt.node_tree:
            for nd in mt.node_tree.nodes:
                if nd.type == 'TEX_IMAGE' and nd.image and "scan_color" in nd.image.name and "head" not in nd.image.name:
                    print("body image", nd.image.name, "->", bi.name)
                    nd.image = bi
for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        sc.render.engine = e; break
    except TypeError:
        pass
sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.5, 0.5, 0.52, 1); bg.inputs[1].default_value = 1.0
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN')); sc.collection.objects.link(sun)
sun.data.energy = 0.0
sun.rotation_euler = (math.radians(55), 0, math.radians(-35))
orig = {o.name: [s.material for s in o.material_slots] for o in meshes}
clay = bpy.data.materials.new("clay"); clay.use_nodes = True
clay.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.55, 0.55, 1)
clay.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.6
HAIR = ("scancards", "hairunder", "haircap")


def setup(is_clay=False, hide=(), shapes=()):
    for o in meshes:
        if o.data.shape_keys:
            for kb in o.data.shape_keys.key_blocks[1:]:
                kb.value = 0.0
            for k, v in shapes:
                if k in o.data.shape_keys.key_blocks:
                    o.data.shape_keys.key_blocks[k].value = v
        o.hide_render = any(h in o.name for h in tuple(hide) + (HAIR if opts.get("nohair") else ()) + tuple(x for x in opts.get("hide", "").split(",") if x))
        for i, s in enumerate(o.material_slots):
            s.material = clay if (is_clay and not any(x in o.name.lower() for x in ("eye", "cornea"))) else orig[o.name][i]
    sun.data.energy = 3.0 if is_clay else (2.6 if opts.get("key") else 0.0)
    bg.inputs[1].default_value = 0.35 if is_clay else (0.55 if opts.get("key") else 1.0)
    bpy.context.view_layer.update()


def shoot(name, target, yaw=0.0, elev=0.0, dist=0.75, lens=85, **kw):
    if only and name not in only:
        return
    setup(**kw)
    t = Vector(target)
    d = Vector((math.sin(math.radians(yaw)) * math.cos(math.radians(elev)), -math.cos(math.radians(yaw)) * math.cos(math.radians(elev)), math.sin(math.radians(elev))))
    cam.location = t + d * dist
    cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()
    if opts.get("key") and not kw.get("is_clay"):
        # the key light from the camera's upper left: 40 deg to its side, 35 deg up
        sun.rotation_euler = (math.radians(55), 0, math.radians(yaw - 40))
    else:
        sun.rotation_euler = (math.radians(55), 0, math.radians(-35))
    cam.data.lens = lens; cam.data.clip_start = 0.005; cam.data.type = 'PERSP'
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.filepath = f"{pre}_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("shot", name)


F = (0.0, -0.06, 1.69)
C = (0.0, -0.08, 1.685)
if opts.get("set") == "ear":
    t = (-0.075, -0.03, 1.685)
    shoot("earRz", t, yaw=-90, dist=0.18)
    shoot("earRz_nocards", t, yaw=-90, dist=0.18, hide=("scancards",))
    shoot("earRz_nounder", t, yaw=-90, dist=0.18, hide=("hairunder",))
    shoot("earRz_nocap", t, yaw=-90, dist=0.18, hide=("haircap",))
    shoot("earRz_nohair", t, yaw=-90, dist=0.18, hide=HAIR)
    t = (0.075, -0.03, 1.685)
    shoot("earLz", t, yaw=90, dist=0.18)
    shoot("earLz_nohair", t, yaw=90, dist=0.18, hide=HAIR)
    sys.exit(0)
if opts.get("set") == "neck":
    for nm, t, yaw, el, dist in (("neckR", (-0.04, -0.06, 1.6), -70, -10, 0.35), ("neckL", (0.04, -0.06, 1.6), 70, -10, 0.35),
                                 ("neckF", (0.0, -0.08, 1.58), 0, -25, 0.35), ("earR", (-0.07, -0.02, 1.68), -90, 0, 0.3),
                                 ("earL", (0.07, -0.02, 1.68), 90, 0, 0.3), ("earRb", (-0.07, 0.0, 1.68), -135, 0, 0.3),
                                 ("templeR", (-0.06, -0.08, 1.74), -45, 0, 0.3), ("templeL", (0.06, -0.08, 1.74), 45, 0, 0.3)):
        shoot(nm, t, yaw=yaw, elev=el, dist=dist)
        shoot(nm + "_clay", t, yaw=yaw, elev=el, dist=dist, is_clay=True, hide=HAIR)
    sys.exit(0)
if opts.get("set") == "extra":
    shoot("nape35", (0.0, 0.03, 1.62), yaw=180, elev=5, dist=0.35)
    shoot("napeR35", (-0.02, 0.02, 1.62), yaw=-140, elev=5, dist=0.35)
    shoot("napeL35", (0.02, 0.02, 1.62), yaw=140, elev=5, dist=0.35)
    for nm, yaw in (("dlg0", 0), ("dlgR30", -30), ("dlgL30", 30), ("dlgR80", -80)):
        shoot(nm, (0.0, -0.03, 1.66), yaw=yaw, dist=1.35, lens=65)
    sys.exit(0)
if opts.get("set") == "chin":
    t = (0.0, -0.1, 1.6)
    for nm, yaw, el in (("chinF", 0, 0), ("chinR34", -35, 0), ("chinL34", 35, 0), ("chinRP", -90, 0), ("chinLP", 90, 0),
                        ("chinU", 0, -35)):
        shoot(nm + "_clay", t, yaw=yaw, elev=el, dist=0.3, is_clay=True, hide=HAIR)
        shoot(nm, t, yaw=yaw, elev=el, dist=0.3)
    sys.exit(0)
if opts.get("set") == "lobe":
    for side, s_ in (("R", -1), ("L", 1)):
        t = (s_ * 0.07, -0.03, 1.668)
        shoot("lobe" + side, t, yaw=s_ * 60, dist=0.2, hide=HAIR)
        shoot("lobe" + side + "_clay", t, yaw=s_ * 60, dist=0.2, is_clay=True, hide=HAIR)
    sys.exit(0)
if opts.get("set") == "temple":
    for side, s_ in (("R", -1), ("L", 1)):
        t = (s_ * 0.065, -0.05, 1.71)
        for nm, yaw in (("34", 55), ("p", 90)):
            shoot("temple" + side + nm, t, yaw=s_ * yaw, dist=0.4)
            shoot("temple" + side + nm + "_nohair", t, yaw=s_ * yaw, dist=0.4, hide=HAIR)
    sys.exit(0)
if opts.get("set") == "eyeprof":
    for side, s_ in (("R", -1), ("L", 1)):
        t = (s_ * 0.031, -0.14, 1.707)
        for nm, yaw in (("90", 90), ("70", 70)):
            shoot("eye" + side + nm, t, yaw=s_ * yaw, dist=0.15)
            shoot("eye" + side + nm + "_clay", t, yaw=s_ * yaw, dist=0.15, is_clay=True, hide=HAIR)
            shoot("eye" + side + nm + "_nolash", t, yaw=s_ * yaw, dist=0.15, hide=HAIR + ("lash",))
    sys.exit(0)
if opts.get("set") == "r4":
    # set=r4: close checks at 0.22-0.3 m (key light with key=1): nostrils from below and low three-quarters, the
    # sideburns and ears in profile and three-quarters, under each lobe, the ears' tops from behind, the nape, the
    # right side of the neck, the eyes in profile; clay where geometry matters
    N_ = (0.0, -0.15, 1.655)
    shoot("noseU", N_, elev=-35, dist=0.25)
    shoot("noseR34lo", N_, yaw=-35, elev=-20, dist=0.25)
    shoot("noseL34lo", N_, yaw=35, elev=-20, dist=0.25)
    shoot("noseRp", N_, yaw=-90, elev=-5, dist=0.25)
    for side, s_ in (("R", -1), ("L", 1)):
        shoot("sideburn" + side + "p", (s_ * 0.07, -0.045, 1.70), yaw=s_ * 90, dist=0.26)
        shoot("sideburn" + side + "34", (s_ * 0.065, -0.06, 1.70), yaw=s_ * 55, dist=0.26)
        shoot("lobe" + side, (s_ * 0.07, -0.03, 1.668), yaw=s_ * 60, dist=0.22, hide=HAIR)
        shoot("lobe" + side + "_clay", (s_ * 0.07, -0.03, 1.668), yaw=s_ * 60, dist=0.22, is_clay=True, hide=HAIR)
        shoot("eartop" + side, (s_ * 0.075, -0.01, 1.715), yaw=s_ * 120, elev=10, dist=0.26)
        shoot("eartop" + side + "f", (s_ * 0.075, -0.03, 1.715), yaw=s_ * 70, elev=5, dist=0.26)
        shoot("eye" + side + "90", (s_ * 0.031, -0.14, 1.707), yaw=s_ * 90, dist=0.25)
    shoot("nape30", (0.0, 0.03, 1.63), yaw=180, elev=5, dist=0.3)
    shoot("napeR30", (-0.02, 0.02, 1.63), yaw=-140, elev=5, dist=0.3)
    shoot("napeL30", (0.02, 0.02, 1.63), yaw=140, elev=5, dist=0.3)
    shoot("neckR", (-0.05, -0.06, 1.62), yaw=-70, elev=-5, dist=0.28)
    shoot("neckL", (0.05, -0.06, 1.62), yaw=70, elev=-5, dist=0.28)
    shoot("crown", (0.0, 0.0, 1.78), yaw=-30, elev=45, dist=0.35)
    # (the back down to the knees: the nape's paint once ran down the spine as a dark stripe)
    shoot("backbody", (0.0, 0.05, 1.25), yaw=180, elev=5, dist=2.4)
    blink = (("eyeBlinkLeft", 1.0), ("eyeBlinkRight", 1.0))
    shoot("blinkL", (0.032, -0.13, 1.705), yaw=25, dist=0.22, shapes=blink)
    shoot("blinkR", (-0.032, -0.13, 1.705), yaw=-25, dist=0.22, shapes=blink)
    shoot("eyesF", (0.0, -0.13, 1.705), yaw=0, dist=0.25)
    sys.exit(0)
if opts.get("set") == "r5":
    # set=r5: the nape and the hood's top from behind (and from above behind, as the game's over-the-shoulder camera),
    # the hair at dialogue distance (0.55 m) from the front, 30 deg and both profiles (the side hair over the ears),
    # the temples and ears' tops at 0.3 m, the lashes at 45 deg
    H_ = (0.0, -0.06, 1.675)
    shoot("nape30", (0.0, 0.03, 1.63), yaw=180, elev=5, dist=0.3)
    shoot("napeR30", (-0.02, 0.02, 1.63), yaw=-140, elev=5, dist=0.3)
    shoot("napeL30", (0.02, 0.02, 1.63), yaw=140, elev=5, dist=0.3)
    shoot("nape75", (0.0, 0.0, 1.66), yaw=180, elev=5, dist=0.75)
    shoot("hoodtop", (0.0, 0.03, 1.6), yaw=180, elev=40, dist=0.4)
    shoot("hoodtopR", (-0.02, 0.03, 1.6), yaw=-150, elev=45, dist=0.45)
    for nm, yaw in (("d0", 0), ("dR30", -30), ("dL30", 30), ("dR90", -90), ("dL90", 90)):
        shoot(nm, H_, yaw=yaw, dist=0.55, lens=50)
    for side, s_ in (("R", -1), ("L", 1)):
        shoot("temple" + side + "30", (s_ * 0.065, -0.06, 1.72), yaw=s_ * 60, elev=5, dist=0.3)
        shoot("eartop" + side + "p", (s_ * 0.075, -0.035, 1.71), yaw=s_ * 90, elev=5, dist=0.26)
        shoot("lash" + side + "45", (s_ * 0.032, -0.135, 1.707), yaw=s_ * 45, dist=0.18)
    sys.exit(0)
if opts.get("set") == "eyes":
    for side, x in (("R", -0.032), ("L", 0.032)):
        t = (x, -0.13, 1.705)
        shoot("eye" + side + "_clay", t, yaw=0, dist=0.2, is_clay=True, hide=HAIR)
        shoot("eye" + side + "_clay_noeye", t, yaw=0, dist=0.2, is_clay=True, hide=HAIR + ("eye", "cornea", "lash"))
        shoot("eye" + side + "_side", t, yaw=-60 if side == "R" else 60, dist=0.2, is_clay=True, hide=HAIR)
        shoot("eye" + side + "_tex", t, yaw=0, dist=0.2)
    shoot("nose_clay", (0, -0.15, 1.665), yaw=0, elev=-20, dist=0.2, is_clay=True, hide=HAIR)
    shoot("nose_tex", (0, -0.15, 1.665), yaw=0, elev=-20, dist=0.2)
    sys.exit(0)
for nm, yaw in (("f", 0), ("r34", -35), ("l34", 35), ("rp", -90), ("lp", 90)):
    shoot(nm + "75", F, yaw=yaw)
    t = C if abs(yaw) < 60 else ((-0.03 if yaw < 0 else 0.03), -0.11, 1.695)
    shoot(nm + "30", t, yaw=yaw, dist=0.3)
    shoot("clay_" + nm, F, yaw=yaw, is_clay=True, hide=HAIR)
shoot("under", (0.0, -0.07, 1.62), elev=-35, dist=0.45)
shoot("back", (0.0, 0.0, 1.68), yaw=180)
