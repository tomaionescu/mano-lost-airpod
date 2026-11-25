"""Build the EPITA Kremlin-Bicetre campus level for the Godot remake.

Run (from the project root):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P tools/blender/build_campus.py
Options after `--`:
    --no-props       skip building / exporting the prop glbs (assets/props/*.glb)
    --props-only     only rebuild the props
    --preview        render Eevee check images into tools/out/campus_*.png
    --preview-only   (re)render previews from the already built scene, no export
    --fast           low sample count for previews
    --blend          also save tools/out/campus_cache/campus.blend for inspection
    --no-export      build (and preview) without writing the level glb
    --views=a,b      only render these preview views

Output:
    assets/levels/campus.glb   level geometry, -colonly colliders, gameplay markers (Empties + extras),
                               CAM_title. Textures are NOT embedded: images are referenced by relative URI
                               (../textures/<id>/...), so Godot shares them with the prop glbs.
    assets/props/<asset>.glb   props placed by PROP_<asset>__<nn> markers
Conventions: docs/PIPELINE.md. Deterministic: no wall-clock or unseeded randomness.
"""
import bpy, os, sys, json, math, time, shutil, importlib, urllib.parse, struct

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import campus_tex, campus_mat, campus_geo, campus_arch, campus_layout, campus_markers, campus_street, campus_voltaire, campus_south, campus_gen
import campus_props, campus_props_out, campus_kb1, campus_backdrop_data, campus_backdrop
for m in (campus_tex, campus_mat, campus_geo, campus_arch, campus_layout, campus_markers, campus_street, campus_voltaire, campus_south,
          campus_gen, campus_props, campus_props_out, campus_kb1, campus_backdrop_data, campus_backdrop):
    importlib.reload(m)   # campus_props*, campus_south, campus_kb1 and campus_backdrop register extra materials on import

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OPT = {a.lstrip("-").split("=")[0] for a in ARGS}
VIEWS = next((a.split("=", 1)[1].split(",") for a in ARGS if a.startswith("--views=")), None)
PROPS_ONLY = next((a.split("=", 1)[1].split(",") for a in ARGS if a.startswith("--props=")), None)
LEVEL_GLB = os.path.join(ROOT, "assets", "levels", "campus.glb")
PROPS_DIR = os.path.join(ROOT, "assets", "props")
CACHE = os.path.join(ROOT, "tools", "out", "campus_cache")
T0 = time.time()


def log(*a):
    print("[campus %6.1fs]" % (time.time() - T0), *a, flush=True)


# ------------------------------------------------------------------ glTF packing
def gltf_to_glb(gltf_path, glb_path):
    """Pack a .gltf + .bin into a .glb whose images stay external: their URIs are rewritten relative to the
    glb location (assets/levels or assets/props -> ../textures/...)."""
    base = os.path.dirname(gltf_path)
    with open(gltf_path) as f:
        d = json.load(f)
    bufs = d.get("buffers", [])
    if len(bufs) != 1:
        raise RuntimeError("expected exactly one buffer")
    b = bufs[0]
    with open(os.path.join(base, urllib.parse.unquote(b["uri"])), "rb") as f:
        data = f.read()
    del b["uri"]
    b["byteLength"] = len(data)
    out_dir = os.path.dirname(os.path.abspath(glb_path))
    for im in d.get("images", []):
        uri = im.get("uri")
        if not uri:
            continue
        src = os.path.normpath(os.path.join(base, urllib.parse.unquote(uri)))
        rel = os.path.relpath(src, out_dir).replace(os.sep, "/")
        if not os.path.exists(src):
            raise RuntimeError(f"missing texture {src}")
        im["uri"] = urllib.parse.quote(rel)
    js = json.dumps(d, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    data += b"\0" * ((4 - len(data) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(data)
    tmp = glb_path + ".part"
    with open(tmp, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(data), b"BIN\0"))
        f.write(data)
    os.replace(tmp, glb_path)


IMPORT_SCRIPT = "res://assets/levels/campus_import.gd"


def ensure_scene_import(glb_path):
    """make sure the glb's .import runs our post-import script (vertex colours as albedo multiplier)"""
    imp = glb_path + ".import"
    rel = "res://" + os.path.relpath(glb_path, ROOT).replace(os.sep, "/")
    if not os.path.exists(imp):
        with open(imp, "w") as f:
            f.write('[remap]\n\nimporter="scene"\nimporter_version=1\ntype="PackedScene"\n\n[deps]\n\n'
                    f'source_file="{rel}"\n\n[params]\n\nimport_script/path="{IMPORT_SCRIPT}"\n')
        return
    with open(imp) as f:
        txt = f.read()
    if f'import_script/path="{IMPORT_SCRIPT}"' in txt:
        return
    lines = txt.split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith("import_script/path="):
            lines[i] = f'import_script/path="{IMPORT_SCRIPT}"'
            break
    else:
        lines.append(f'import_script/path="{IMPORT_SCRIPT}"')
    with open(imp, "w") as f:
        f.write("\n".join(lines))


def export_scene(scene, glb_path, tag):
    tmpdir = os.path.join(CACHE, "export", tag)
    shutil.rmtree(tmpdir, ignore_errors=True)
    os.makedirs(tmpdir, exist_ok=True)
    gltf = os.path.join(tmpdir, tag + ".gltf")
    win = bpy.context.window
    prev = None
    if win is not None:
        prev = win.scene
        win.scene = scene
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        bpy.ops.export_scene.gltf(filepath=gltf, export_format="GLTF_SEPARATE", export_keep_originals=True,
                                  use_active_scene=True, export_extras=True, export_yup=True, export_lights=False,
                                  export_cameras=True, export_apply=True, export_vertex_color="MATERIAL",
                                  export_tangents=False, export_texcoords=True, export_normals=True,
                                  export_materials="EXPORT", export_image_format="AUTO", export_animations=False,
                                  export_skins=False, export_morph=False)
    if win is not None and prev is not None:
        win.scene = prev
    os.makedirs(os.path.dirname(glb_path), exist_ok=True)
    gltf_to_glb(gltf, glb_path)
    ensure_scene_import(glb_path)
    return os.path.getsize(glb_path)


# ------------------------------------------------------------------ level
def new_collection(scene, name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c


def build_level():
    G = campus_geo
    B = G.Builder()
    log("street")
    campus_street.ground(B)
    log("backdrop")
    campus_backdrop.build(B)
    log("voltaire")
    campus_voltaire.build(B)
    campus_kb1.build(B)
    log("south block")
    campus_south.build(B)
    try:
        import campus_dress
        importlib.reload(campus_dress)
        log("dressing")
        campus_dress.build(B)
    except ImportError:
        log("no campus_dress module yet")
    log("markers")
    campus_markers.place_all(B)
    return B


def add_title_camera(scene, coll):
    t = campus_markers.TITLE_SHOT
    cam = bpy.data.cameras.new("CAM_title")
    cam.sensor_fit = "VERTICAL"
    cam.angle_y = math.radians(t["fov"])
    cam.clip_start = 0.05
    cam.clip_end = 400.0
    ob = bpy.data.objects.new("CAM_title", cam)
    coll.objects.link(ob)
    from mathutils import Vector
    P = campus_geo.P
    ob.location = P(*t["frm"])
    d = Vector(P(*t["look"])) - Vector(P(*t["frm"]))
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    ob["look"] = list(t["look"])
    return ob


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    scene.name = "campus"
    scene.unit_settings.system = "METRIC"
    log("generated textures")
    campus_gen.build_all(log)
    if "gen-only" in OPT:
        return
    if "props-only" not in OPT:
        B = build_level()
        lvl = new_collection(scene, "LEVEL")
        col = new_collection(scene, "COLLISION")
        mk = new_collection(scene, "MARKERS")
        log("commit meshes")
        obs = campus_geo.commit_parts(B, lvl)
        cols = campus_geo.commit_colliders(B, col)
        mks = campus_geo.commit_markers(B, mk)
        add_title_camera(scene, mk)
        tris = sum(p.tri_count() for p in B.parts.values())
        log(f"parts {len(obs)}  colliders {len(cols)}  markers {len(mks)}  level tris {tris}")
        stats = {name: p.tri_count() for name, p in sorted(B.parts.items(), key=lambda kv: -kv[1].tri_count())}
        os.makedirs(CACHE, exist_ok=True)
        with open(os.path.join(CACHE, "level_stats.json"), "w") as f:
            json.dump({"level_tris": tris, "parts": stats, "markers": sorted(m["name"] for m in B.markers)}, f, indent=1)
        if "no-export" not in OPT:
            log("export level")
            size = export_scene(scene, LEVEL_GLB, "campus")
            log(f"wrote {os.path.relpath(LEVEL_GLB, ROOT)} ({size / 1e6:.1f} MB)")
        if "blend" in OPT:
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(CACHE, "campus.blend"), compress=True)
    if "no-props" not in OPT:
        campus_props.build_all(export_scene, log, only=PROPS_ONLY)
    if "preview" in OPT:
        import campus_preview
        importlib.reload(campus_preview)
        campus_preview.render_all(fast="fast" in OPT, log=log, views=VIEWS)
    log("done")


if __name__ == "__main__":
    main()
