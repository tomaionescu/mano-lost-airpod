"""Blender: build a scanned outfit with a given head scan (or none) into another file, leaving cast.py and
assets/characters alone: to compare head scans (Hunyuan against Tripo) or check the pipeline before one goes into
cast.py. The outfit's own "head_scan" is replaced by the one given here.

usage: Blender -b -P tools/dev/head_scan_build.py -- <id>:<outfit> <head.glb|none> <out.glb> [fit=affine] [state=1]
                                                      [portrait=0] [jaw=<0..1>]
<head.glb>: a path under tools/scans (as cast.py's "head_scan") or an absolute one. fit=affine: the
"head_scan_fit". jaw=: the "head_scan_jaw" (scan_wrap.widen_jaw: the lower face wider and the chin angle softer,
0 = the head scan's, 1 = the full widening). state=1 also saves <out>.npz, the fitted body before export (vertices
with MakeHuman's helpers, the head's vertices, the face anchors), for tools/dev/head_scan_compare.py. Work files still
go to tools/out/scan_<id>/.
"""
import bpy, sys, os, importlib, shutil
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "blender"))
argv = sys.argv[sys.argv.index("--") + 1:]
target, head, out = argv[0], argv[1], os.path.abspath(argv[2])
opts = dict(a.split("=", 1) for a in argv[3:] if "=" in a)
import build_human as bh

cid, _, outfit = target.partition(":")
outfit = outfit or list(bh.cast.CAST[cid]["outfits"])[0]
fit = bh.cast.CAST[cid]["outfits"][outfit]
for k in ("head_scan", "head_scan_fit", "head_scan_jaw"):
    fit.pop(k, None)
if head != "none":
    fit["head_scan"] = head
if "fit" in opts:
    fit["head_scan_fit"] = opts["fit"]
if "jaw" in opts:
    fit["head_scan_jaw"] = float(opts["jaw"])
if opts.get("portrait") == "0":      # portrait=0: no portrait (shape and paint), to see the head scan's face alone
    fit.pop("face", None)

if opts.get("state"):
    # build() reloads scan_wrap: wrap scale_shapes (called once the face is fitted, before the helpers go) after
    # each reload, to save the body as it stands then
    _reload = importlib.reload

    def reload(m):
        r = _reload(m)
        if getattr(m, "__name__", "") == "scan_wrap":
            orig = m.scale_shapes

            def scale_shapes(basemesh, rig):
                names = [b.name for b in rig.data.bones if b.use_deform and b.name in basemesh.vertex_groups]
                W = m.deform_weights(basemesh, names)
                body = basemesh.vertex_groups["body"].index
                in_body = np.array([any(g.group == body and g.weight > 0.5 for g in v.groups)
                                    for v in basemesh.data.vertices])
                A = m.anchor_points(basemesh, ROOT)
                keys = sorted(A)
                np.savez(os.path.splitext(out)[0] + ".npz", V=m.world_verts(basemesh), in_body=in_body,
                         head=W[:, names.index("head")] > 0.5, anchor_ids=np.array(keys),
                         anchors=np.array([A[k] for k in keys]))
                return orig(basemesh, rig)
            m.scale_shapes = scale_shapes
        return r
    importlib.reload = reload

tmp = os.path.join(os.path.dirname(out), ".build_" + os.path.basename(out))
os.makedirs(tmp, exist_ok=True)
bh.OUT = tmp
path = bh.build(cid, outfit)
shutil.move(path, out)
shutil.rmtree(tmp, ignore_errors=True)
print("[head_scan_build]", target, "head scan", head, "->", os.path.relpath(out, ROOT))
