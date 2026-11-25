"""Texture fetching for the campus build (Poly Haven / ambientCG, CC0 only).

Every texture set ends up in assets/textures/<id>/ as
    <id>_diff_<res>.jpg     base colour (sRGB)
    <id>_nor_gl_<res>.jpg   OpenGL normal map (+Y up, what glTF and Godot expect)
    <id>_arm_<res>.jpg      packed AO (R) / roughness (G) / metallic (B) = glTF occlusion + metallicRoughness
    <id>_diffa_<res>.png    base colour with alpha (only for cut-out sets: leaves, grass)
plus a Godot .import preset next to each image (VRAM compressed, mipmaps, normal-map mode) so the level
glb, which references these files by relative URI instead of embedding them, imports with sane settings.
Downloads are cached; a set that is already on disk is never fetched again.
"""
import os, json, time, zipfile, hashlib, shutil, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TEX_DIR = os.path.join(ROOT, "assets", "textures")
CACHE = os.path.join(ROOT, "tools", "out", "campus_cache")
UA = "mano-campus-build/1.0 (+Blender script; CC0 texture fetch)"
SOURCES_JSON = os.path.join(TEX_DIR, "SOURCES.json")

_sources = None


def log(*a):
    print("[tex]", *a, flush=True)


def _http(url, tries=4):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # network hiccup: back off and retry
            last = e
            time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"download failed {url}: {last}")


def _fetch_json(url, cache_name):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, cache_name)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    data = _http(url)
    d = json.loads(data.decode("utf-8"))
    with open(p, "w") as f:
        json.dump(d, f)
    return d


def _download(url, dest, md5=None):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    data = _http(url)
    if md5 and hashlib.md5(data).hexdigest() != md5:
        raise RuntimeError(f"md5 mismatch for {url}")
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    log("downloaded", os.path.relpath(dest, ROOT), f"{len(data) // 1024} KB")
    return dest


def _load_sources():
    global _sources
    if _sources is None:
        _sources = {}
        if os.path.exists(SOURCES_JSON):
            with open(SOURCES_JSON) as f:
                _sources = json.load(f)
    return _sources


def _record(asset_id, entry):
    s = _load_sources()
    if s.get(asset_id) != entry:
        s[asset_id] = entry
        with open(SOURCES_JSON, "w") as f:
            json.dump(dict(sorted(s.items())), f, indent=1)


# ------------------------------------------------------------------ Godot import presets
_IMPORT_TMPL = """[remap]

importer="texture"
type="CompressedTexture2D"

[deps]

source_file="{src}"

[params]

compress/mode=2
compress/high_quality=false
compress/lossy_quality=0.7
compress/hdr_compression=1
compress/normal_map={nm}
compress/channel_pack=0
mipmaps/generate=true
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
"""


def write_import_preset(path, normal=None):
    """Godot .import next to an image: VRAM compressed + mipmaps (+ normal-map mode for *_nor_gl_*).
    An existing .import keeps its uid; only the relevant params are forced."""
    if normal is None:
        normal = "_nor_gl" in os.path.basename(path)
    imp = path + ".import"
    rel = "res://" + os.path.relpath(path, ROOT).replace(os.sep, "/")
    want = {"compress/mode": "2", "compress/normal_map": "1" if normal else "0", "mipmaps/generate": "true",
            "detect_3d/compress_to": "0"}
    if not os.path.exists(imp):
        with open(imp, "w") as f:
            f.write(_IMPORT_TMPL.format(src=rel, nm=want["compress/normal_map"]))
        return
    with open(imp) as f:
        lines = f.read().split("\n")
    changed = False
    for i, ln in enumerate(lines):
        k = ln.split("=", 1)[0]
        if k in want and ln != f"{k}={want[k]}":
            lines[i] = f"{k}={want[k]}"
            changed = True
    if changed:
        with open(imp, "w") as f:
            f.write("\n".join(lines))


# ------------------------------------------------------------------ Poly Haven
PH_MAPS = {"diff": "Diffuse", "nor_gl": "nor_gl", "arm": "arm"}


def polyhaven(tex_id, res="2k", maps=("diff", "nor_gl", "arm")):
    """Download a Poly Haven texture set; returns {map: abs path}."""
    out = {}
    folder = os.path.join(TEX_DIR, tex_id)
    want_gray = "diffg" in maps
    maps = tuple(m for m in maps if m != "diffg")
    if want_gray and "diff" not in maps:
        maps = ("diff",) + maps
    need = [m for m in maps if not os.path.exists(os.path.join(folder, f"{tex_id}_{m}_{res}.jpg"))]
    files = _fetch_json(f"https://api.polyhaven.com/files/{tex_id}", f"ph_files_{tex_id}.json") if need else None
    for m in maps:
        dest = os.path.join(folder, f"{tex_id}_{m}_{res}.jpg")
        if m in need:
            if m == "arm" and "arm" not in files:
                _pack_arm_from(files, folder, tex_id, res, dest)
            else:
                info = files[PH_MAPS[m]][res]["jpg"]
                _download(info["url"], dest, info.get("md5"))
        write_import_preset(dest)
        out[m] = dest
    if want_gray:
        out["diffg"] = make_gray(out["diff"], os.path.join(folder, f"{tex_id}_diffg_{res}.jpg"))
    _record(tex_id, {"source": "Poly Haven", "url": f"https://polyhaven.com/a/{tex_id}", "license": "CC0 1.0",
                     "files": sorted(os.path.basename(p) for p in out.values())})
    return out


def _pack_arm_from(files, folder, tex_id, res, dest):
    """some Poly Haven sets ship no packed arm map: build it from AO + Rough (+ metal if any)"""
    import numpy as np
    tmp = os.path.join(CACHE, "ph_parts", tex_id)
    got = {}
    for key in ("AO", "Rough", "Metal"):
        if key in files and res in files[key] and "jpg" in files[key][res]:
            info = files[key][res]["jpg"]
            p = os.path.join(tmp, f"{key}_{res}.jpg")
            _download(info["url"], p, info.get("md5"))
            a = _np_img(p)
            got[key] = a[:, :, 0] if a.ndim == 3 else a
    ref = got.get("Rough")
    if ref is None:
        raise RuntimeError(f"{tex_id}: no roughness map")
    h, w = ref.shape
    ao = got.get("AO", np.ones((h, w), np.float32))
    me = got.get("Metal", np.zeros((h, w), np.float32))
    _write_img(dest, np.stack([ao, ref, me], axis=2))
    log("packed arm for", tex_id)


# ------------------------------------------------------------------ ambientCG
def _np_img(path):
    import OpenImageIO as oiio
    b = oiio.ImageBuf(path)
    a = b.get_pixels(oiio.FLOAT)
    if a is None or a.size == 0:
        raise RuntimeError(f"cannot read {path}: {b.geterror()}")
    return a


def _write_img(path, arr, quality=92):
    import OpenImageIO as oiio
    import numpy as np
    h, w = arr.shape[:2]
    c = arr.shape[2] if arr.ndim == 3 else 1
    spec = oiio.ImageSpec(w, h, c, oiio.UINT8)
    if path.endswith(".jpg"):
        spec.attribute("CompressionQuality", quality)
        spec.attribute("Compression", f"jpeg:{quality}")
    o = oiio.ImageBuf(spec)
    o.set_pixels(oiio.ROI(0, w, 0, h, 0, 1, 0, c), np.clip(arr, 0, 1).astype("float32"))
    tmp = path + ".part" + os.path.splitext(path)[1]
    if not o.write(tmp):
        raise RuntimeError(o.geterror())
    os.replace(tmp, path)


def ambientcg(asset_id, res="2K", alpha=False, gray=False):
    """Download an ambientCG 2K/1K JPG set, keep only what we use, pack AO/rough/metal into *_arm_*.jpg."""
    import numpy as np
    r = res.lower()
    folder = os.path.join(TEX_DIR, asset_id)
    diff = os.path.join(folder, f"{asset_id}_diff_{r}.jpg")
    nor = os.path.join(folder, f"{asset_id}_nor_gl_{r}.jpg")
    arm = os.path.join(folder, f"{asset_id}_arm_{r}.jpg")
    diffa = os.path.join(folder, f"{asset_id}_diffa_{r}.png")
    want = [diff, nor, arm] + ([diffa] if alpha else [])
    if not all(os.path.exists(p) for p in want):
        zname = f"{asset_id}_{res}-JPG.zip"
        zpath = _download(f"https://ambientcg.com/get?file={zname}", os.path.join(CACHE, "acg", zname))
        tmpdir = os.path.join(CACHE, "acg", asset_id + "_" + res)
        os.makedirs(tmpdir, exist_ok=True)
        got = {}
        with zipfile.ZipFile(zpath) as z:
            for n in z.namelist():
                base = os.path.basename(n)
                if not base or "/" in base or "\\" in base or base.startswith("."):
                    continue
                low = base.lower()
                if not (low.endswith(".jpg") or low.endswith(".png")):
                    continue
                for key in ("_Color", "_NormalGL", "_Roughness", "_AmbientOcclusion", "_Metalness", "_Opacity"):
                    if key + "." in base:
                        dst = os.path.join(tmpdir, base)
                        with z.open(n) as src, open(dst, "wb") as f:
                            shutil.copyfileobj(src, f)
                        got[key[1:]] = dst
        os.makedirs(folder, exist_ok=True)
        if "Color" not in got or "NormalGL" not in got:
            raise RuntimeError(f"{asset_id}: missing maps in zip ({sorted(got)})")
        shutil.copyfile(got["Color"], diff)
        shutil.copyfile(got["NormalGL"], nor)
        col = _np_img(got["Color"])
        h, w = col.shape[:2]

        def chan(key, default):
            if key in got:
                a = _np_img(got[key])
                return a[:, :, 0] if a.ndim == 3 else a
            return np.full((h, w), default, np.float32)
        packed = np.stack([chan("AmbientOcclusion", 1.0), chan("Roughness", 0.7), chan("Metalness", 0.0)], axis=2)
        _write_img(arm, packed)
        if alpha:
            op = chan("Opacity", 1.0)
            _write_img(diffa, np.concatenate([col[:, :, :3], op[:, :, None]], axis=2))
        shutil.rmtree(tmpdir, ignore_errors=True)
        log("unpacked", asset_id)
    out = {"diff": diff, "nor_gl": nor, "arm": arm}
    if alpha:
        out["diffa"] = diffa
    if gray:
        out["diffg"] = make_gray(diff, os.path.join(folder, f"{asset_id}_diffg_{r}.jpg"))
    for p in out.values():
        write_import_preset(p)
    _record(asset_id, {"source": "ambientCG", "url": f"https://ambientcg.com/view?id={asset_id}", "license": "CC0 1.0",
                       "files": sorted(os.path.basename(p) for p in out.values())})
    return out


# ------------------------------------------------------------------ Poly Haven models (glTF 1k)
def polyhaven_model(model_id, res="1k"):
    """Download a Poly Haven model's glTF (+ bin) into assets/props/_src/<id>/ (ignored by Godot) and its
    textures into assets/textures/<id>/. Returns the .gltf path."""
    src_dir = os.path.join(ROOT, "assets", "props", "_src", model_id)
    os.makedirs(src_dir, exist_ok=True)
    gd = os.path.join(ROOT, "assets", "props", "_src", ".gdignore")
    if not os.path.exists(gd):
        open(gd, "w").close()
    gltf_path = os.path.join(src_dir, f"{model_id}.gltf")
    files = _fetch_json(f"https://api.polyhaven.com/files/{model_id}", f"ph_files_{model_id}.json")
    g = files["gltf"][res]["gltf"]
    _download(g["url"], gltf_path, g.get("md5"))
    for rel, info in g.get("include", {}).items():
        rel = rel.replace("\\", "/")
        if ".." in rel.split("/"):
            continue
        _download(info["url"], os.path.join(src_dir, rel), info.get("md5"))
    _record(model_id, {"source": "Poly Haven (model)", "url": f"https://polyhaven.com/a/{model_id}", "license": "CC0 1.0",
                       "files": [os.path.basename(gltf_path)]})
    return gltf_path


def make_gray(diff_path, out_path, mean=0.78):
    """desaturated copy of a base colour map with its mean luminance normalised (sRGB space), so the
    material colour factor alone decides the hue and brightness (tintable paints, carpets, woods)"""
    if os.path.exists(out_path) and os.path.getmtime(out_path) >= os.path.getmtime(diff_path):
        return out_path
    import numpy as np
    a = _np_img(diff_path)[:, :, :3]
    L = a[:, :, 0] * 0.2126 + a[:, :, 1] * 0.7152 + a[:, :, 2] * 0.0722
    L = L * (mean / max(1e-4, float(L.mean())))
    _write_img(out_path, np.repeat(np.clip(L, 0, 1)[:, :, None], 3, axis=2))
    write_import_preset(out_path)
    return out_path


def import_presets_for_folder(folder):
    for n in sorted(os.listdir(folder)):
        if n.lower().endswith((".jpg", ".png")) and not n.endswith(".part.jpg"):
            write_import_preset(os.path.join(folder, n))
