"""Retarget test: build a character, apply every clip, export assets/characters/test_anim.glb, render contact sheets.

Blender -b -P tools/blender/anim_test.py -- [mano:street] [--clips idle,walk] [--no-render] [--no-export]
                                            [--frames 10] [--blend some.blend]
Contact sheets: tools/out/anim_<clip>.png (top row 3/4 front view, bottom row side view, checker floor 0.25 m,
chair proxy for sitting clips: seat 0.45 m high, front edge at the root; desk proxy for typing: top 0.74 m,
front edge 5 cm behind the root (over the thighs), keyboard ~0.1 m in front of the root).
"""
import bpy, sys, os, time, math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import retarget
import anim_clips as ac

OUT = os.path.join(ROOT, "tools", "out")
GLB = os.path.join(ROOT, "assets", "characters", "test_anim.glb")


def log(*a):
    print("[anim_test]", *a, flush=True)


def build_character(spec):
    import build_human
    cid, _, outfit = spec.partition(":")
    real = build_human.export
    build_human.export = lambda rig, path: None   # build only; we export test_anim.glb ourselves
    try:
        build_human.build(cid, outfit or "street", photo=False, preview=False)
    finally:
        build_human.export = real
    return bpy.data.objects[cid], build_human


# ---------------------------------------------------------------------- render helpers
def mat(name, col):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*col, 1)
    return m


def box(name, size, loc, col):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    o.color = (*col, 1)
    return o


def setup_stage():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    sh = scene.display.shading
    sh.light = 'STUDIO'
    sh.color_type = 'OBJECT'
    sh.show_cavity = True
    sh.cavity_type = 'WORLD'
    sh.show_shadows = True
    sh.shadow_intensity = 0.35
    scene.display.light_direction = (0.35, -0.45, 0.82)
    scene.render.film_transparent = False
    sh.background_type = 'VIEWPORT'
    sh.background_color = (0.82, 0.84, 0.88)
    scene.render.resolution_x, scene.render.resolution_y = 300, 400
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.use_stamp = True
    for k in ("use_stamp_date", "use_stamp_time", "use_stamp_render_time", "use_stamp_camera", "use_stamp_lens",
              "use_stamp_scene", "use_stamp_filename", "use_stamp_memory", "use_stamp_hostname", "use_stamp_marker",
              "use_stamp_frame_range", "use_stamp_sequencer_strip"):
        if hasattr(scene.render, k):
            setattr(scene.render, k, False)
    scene.render.use_stamp_frame = True
    scene.render.use_stamp_note = True
    scene.render.stamp_font_size = 14
    # checker floor 0.25 m
    for k, col in ((0, (0.92, 0.92, 0.9)), (1, (0.62, 0.64, 0.66))):
        verts, faces = [], []
        n = 0
        for ix in range(-12, 12):
            for iy in range(-12, 12):
                if (ix + iy) % 2 != k:
                    continue
                x0, y0 = ix * 0.25, iy * 0.25
                verts += [(x0, y0, 0), (x0 + .25, y0, 0), (x0 + .25, y0 + .25, 0), (x0, y0 + .25, 0)]
                faces.append((n, n + 1, n + 2, n + 3))
                n += 4
        me = bpy.data.meshes.new(f"floor{k}")
        me.from_pydata(verts, [], faces)
        ob = bpy.data.objects.new(f"floor{k}", me)
        ob.color = (*col, 1)
        bpy.context.collection.objects.link(ob)
    # chair (seat top 0.45 m, front edge at y = 0, extends behind the character) and desk
    props = {
        "seat": box("chair_seat", (0.46, 0.44, 0.04), (0, 0.22, 0.43), (0.45, 0.32, 0.22)),
        "back": box("chair_back", (0.46, 0.04, 0.45), (0, 0.46, 0.68), (0.45, 0.32, 0.22)),
        "legs": box("chair_legs", (0.40, 0.38, 0.41), (0, 0.22, 0.205), (0.35, 0.25, 0.18)),
        "desk": box("desk_top", (1.2, 0.6, 0.03), (0, -0.25, 0.725), (0.55, 0.5, 0.44)),
        "kbd": box("keyboard", (0.42, 0.14, 0.02), (0, -0.1, 0.75), (0.2, 0.2, 0.22)),
    }
    for o in props.values():
        o.hide_render = True
    world = bpy.data.worlds.new("w")
    world.color = (0.8, 0.82, 0.86)
    scene.world = world
    cam_d = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_d)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    return props, cam


def look(cam, loc, target, lens):
    from mathutils import Vector
    cam.location = loc
    cam.data.lens = lens
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()


def color_character(rig):
    for ob in rig.children:
        if ob.type != 'MESH':
            continue
        k = ob.get("kind", "")
        ob.color = {"skin": (0.85, 0.66, 0.55, 1), "cloth": (0.35, 0.45, 0.62, 1), "hair": (0.12, 0.1, 0.1, 1)}.get(k, (0.7, 0.7, 0.7, 1))
        if "pants" in ob.name or "jeans" in ob.name or "trousers" in ob.name:
            ob.color = (0.42, 0.40, 0.30, 1)
        if "shoes" in ob.name or "sneakers" in ob.name:
            ob.color = (0.9, 0.9, 0.92, 1)


def render_sheet(rig, clip, act, props, cam, nframes=10, detail=False, suffix=""):
    import OpenImageIO as oiio
    scene = bpy.context.scene
    rig.animation_data.action = act
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    loop = act.get("loop", False)
    frames = np.linspace(f0, f1 - (1 if loop else 0), nframes).round().astype(int)
    meta = ac.CLIPS[clip]
    sitting = bool(meta.get("seat"))
    for k in ("seat", "back", "legs"):
        props[k].hide_render = not sitting
    props["desk"].hide_render = props["kbd"].hide_render = clip != "typing"
    z = 0.62 if sitting and meta.get("seat") is True else 0.85
    if detail:
        scene.render.resolution_x, scene.render.resolution_y = 480, 640
        views = [((1.5, -2.4, 1.2), (0, 0, z), 50), ((2.7, 0.15, 0.95), (0, 0, z), 50),
                 ((1.25, -1.1, 0.35), (0, -0.05, 0.12), 50)]
    else:
        scene.render.resolution_x, scene.render.resolution_y = 300, 400
        views = [((2.0, -3.3, 1.25), (0, 0, z), 45), ((3.9, 0.0, 0.95), (0, 0, z), 45)]
    tmp = os.path.join(bpy.app.tempdir, "cell.png")
    W, H = scene.render.resolution_x, scene.render.resolution_y
    sheet = np.zeros((H * len(views), W * len(frames), 3), np.uint8)
    for r, (loc, tgt, lens) in enumerate(views):
        look(cam, loc, tgt, lens)
        for c, f in enumerate(frames):
            scene.frame_set(int(f))
            scene.render.stamp_note_text = clip
            scene.render.filepath = tmp
            bpy.ops.render.render(write_still=True)
            img = oiio.ImageInput.open(tmp)
            px = img.read_image(format="uint8")
            img.close()
            sheet[r * H:(r + 1) * H, c * W:(c + 1) * W] = np.asarray(px)[:, :, :3]
    path = os.path.join(OUT, f"anim_{clip}{suffix}.png")
    o = oiio.ImageOutput.create(path)
    o.open(path, oiio.ImageSpec(sheet.shape[1], sheet.shape[0], 3, "uint8"))
    o.write_image(sheet)
    o.close()
    return path


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    flags = {a.split("=")[0]: (a.split("=", 1)[1] if "=" in a else True) for a in argv if a.startswith("--")}
    pos = [a for a in argv if not a.startswith("--")]
    clips = None
    for i, a in enumerate(argv):
        if a == "--clips" and i + 1 < len(argv):
            clips = argv[i + 1].split(",")
            pos = [p for p in pos if p != argv[i + 1]]
        if a == "--blend" and i + 1 < len(argv):
            pos = [p for p in pos if p != argv[i + 1]]
    nframes = int(flags.get("--frames", 10)) if flags.get("--frames") not in (None, True) else 10
    for i, a in enumerate(argv):
        if a == "--frames" and i + 1 < len(argv):
            nframes = int(argv[i + 1])
            pos = [p for p in pos if p != argv[i + 1]]
    spec = pos[0] if pos else "mano:street"
    # --try name=src:kind:start:end[:key=val,...] adds a temporary clip (development)
    for i, a in enumerate(argv):
        if a == "--try" and i + 1 < len(argv):
            pos = [p for p in pos if p != argv[i + 1]]
            for item in argv[i + 1].split(";"):
                nm, _, rest = item.partition("=")
                parts = rest.split(":")
                cfg = {"src": parts[0], "kind": parts[1], "range": (float(parts[2]), float(parts[3]))}
                for kv in parts[4:]:
                    k, _, v = kv.partition("=")
                    try:
                        cfg[k] = eval(v)
                    except Exception:
                        cfg[k] = v
                if cfg["kind"] == "loop" and "length" not in cfg:
                    cfg["length"] = (4.0, 8.0)
                ac.CLIPS[nm] = cfg
                clips = (clips or []) + [nm]
    spec = pos[0] if pos else "mano:street"
    t0 = time.time()
    rig, bh = build_character(spec)
    log("built", spec, round(time.time() - t0, 1), "s")
    t1 = time.time()
    acts = retarget.apply(rig, clips)
    log("retarget.apply", round(time.time() - t1, 2), "s")
    if "--no-export" not in flags:
        t2 = time.time()
        bh.export(rig, GLB)
        log("exported", os.path.relpath(GLB, ROOT), round(time.time() - t2, 1), "s")
    if "--no-render" not in flags:
        os.makedirs(OUT, exist_ok=True)
        props, cam = setup_stage()
        color_character(rig)
        detail = "--detail" in flags
        for name, act in acts.items():
            p = render_sheet(rig, name, act, props, cam, nframes, detail, flags.get("--suffix", "") if detail else "")
            log("sheet", os.path.relpath(p, ROOT))
    log("total", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
