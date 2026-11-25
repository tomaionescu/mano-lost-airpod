"""Hair prototype C (the scan shell, done right), step 1: capture.

Rebuilds scanned characters with the real pipeline (build_human.build), untouched except for where things go and
what is kept, so the hair prototype (proto_hair_C.py) can iterate without a 100 s rebuild per try:
  - the build's own work files land in tools/out/proto_C/root/tools/out/ (a root of links to the real inputs),
    the .glb in tools/out/proto_C/glb/; nothing under assets/ or tools/out/scan_<id>/ is written;
  - the re-posed, textured scan (scan_wrap.apply() deletes it) is kept as the object "protoC_scan";
  - segment_hair()'s landmarks and mask are saved;
  - after export the whole scene is saved as tools/out/proto_C/<stem>_capture.blend (+ <stem>_capture.npz).

usage: Blender -b -P tools/blender/proto_hair_C_capture.py -- toma:fit1 anisha
"""
import bpy, os, sys, types
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "tools", "out", "proto_C")
FAKE = os.path.join(OUT, "root")
os.makedirs(os.path.join(FAKE, "tools", "out"), exist_ok=True)
for sub in ("scans", "py", "models", "photos"):
    link = os.path.join(FAKE, "tools", sub)
    if not os.path.lexists(link):
        os.symlink(os.path.join(ROOT, "tools", sub), link)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
sys.path.insert(0, HERE)
import build_human, scan_wrap, cast

build_human.ROOT = FAKE
build_human.OUT = os.path.join(OUT, "glb")
build_human.PREVIEW = os.path.join(OUT, "preview")
os.makedirs(build_human.OUT, exist_ok=True)
# build() reloads scan_wrap / face_fit: keep the patched modules
build_human.importlib = types.SimpleNamespace(reload=lambda m: m)

CAP = {}
_segment = scan_wrap.segment_hair
_shell = scan_wrap.hair_shell
_export = build_human.export


def segment_hair(scan, basemesh, rig, names, W, in_body, lms, long_hair):
    mask = _segment(scan, basemesh, rig, names, W, in_body, lms, long_hair)
    CAP["lms_k"] = np.array(sorted(lms), np.int64)
    CAP["lms_v"] = np.array([list(lms[k]) for k in sorted(lms)], np.float64)
    CAP["long_hair"] = bool(long_hair)
    CAP["mask"] = np.asarray(mask, bool).copy()
    return mask


def hair_shell(scan, mask, cid):
    me = scan.data.copy()
    for i, m in enumerate(me.materials):
        if m is not None:
            me.materials[i] = m.copy()
    ob = bpy.data.objects.new("protoC_scan", me)
    ob.matrix_world = scan.matrix_world.copy()
    bpy.context.scene.collection.objects.link(ob)
    ob.hide_render = True
    ob.hide_set(True)
    return _shell(scan, mask, cid)


def export(rig, path):
    _export(rig, path)
    stem = os.path.splitext(os.path.basename(path))[0]
    np.savez(os.path.join(OUT, f"{stem}_capture.npz"), **CAP)
    for img in bpy.data.images:
        if img.source == 'GENERATED' or (img.is_dirty and not img.packed_file):
            try:
                img.pack()
            except Exception as e:
                print("[protoC] could not pack", img.name, e)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, f"{stem}_capture.blend"), copy=True)
    print("[protoC] captured", stem, flush=True)


scan_wrap.segment_hair = segment_hair
scan_wrap.hair_shell = hair_shell
build_human.export = export

for t in argv or ["toma:fit1"]:
    cid, _, outfit = t.partition(":")
    outfit = outfit or list(cast.CAST[cid]["outfits"].keys())[0]
    CAP.clear()
    build_human.build(cid, outfit, photo=True, preview=False, anim=False)
