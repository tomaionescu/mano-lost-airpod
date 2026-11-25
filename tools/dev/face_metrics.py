"""Scale-free face proportions from MediaPipe face landmarks (the same Face Landmarker as tools/py/landmarks.py),
to compare a person's photos, their studio portrait, renders of their character and of a raw scan with one
instrument. Every length is divided by the interocular distance (IOD: between the eye centres, each the midpoint of
its two corners), heights by the face height where that reads better.

Each face is first turned to face the camera with MediaPipe's own head pose (its facial transformation matrix),
using the landmarks' depth, so a few degrees of yaw or pitch do not read as a narrower face. Perspective is not
undone: a camera close to the face (a phone selfie at arm's length, a game close-up) makes the nose and the middle
of the face bigger than the outline. `--persp` prints how much, from MediaPipe's canonical face model at each camera
distance; `<image>#<cm>` divides that image's ratios by the bias of a camera that far from the nose tip (if you know
or assume it), so a selfie can be set against an orthographic render.

usage: python3.11 tools/dev/face_metrics.py [options] <image>[@label][#<cm>] [...]
  <image> may also be a build's tools/out/scan_<id>/portrait_mesh.npz: its own landmark points, seen orthographically
  --ref=<n>        compare every image with image n (0-based; default 0), in % (the reference row stays absolute)
  --jitter=<n>     detect again on n slightly scaled / rotated / shifted copies of each image: the landmarker's own
                   noise per ratio (shown as +-), so a difference can be told from noise; the value shown is then
                   the mean of all detections
  --fresh          detect again even when <image>.lm.json exists (by default the cached landmarks are used)
  --raw            measure the landmarks as they lie in the image (no head-pose correction)
  --persp          print the perspective bias table (canonical face) and exit if no image is given
  --overlay=<dir>  write <dir>/<label>_metrics.png: the face crop with the measured points and lines
  --json=<out>     write every image's ratios, noise, pose and landmark count
  --md=<out>       write the comparison as a Markdown table
e.g.   python3.11 tools/dev/face_metrics.py --jitter=8 tools/scans/toma/portrait.png@portrait tools/photos/toma/toma_01.jpg
"""
import json, math, os, struct, sys, zipfile
import numpy as np
import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODEL = os.path.join(ROOT, "tools", "models", "face_landmarker.task")

# ------------------------------------------------------------------ what is measured
EYE_R, EYE_L = (33, 133), (263, 362)          # subject's right eye (image left): outer, inner corner
N, SN, ME, UL, LL, ST_U, ST_L = 168, 2, 152, 0, 17, 13, 14   # nasion, subnasale, menton, lip tops, stomion
# (name, kind, ids, description). kind: "w" width between a left/right pair (along the eye line), "h" height
# between two points (across the eye line); both over the IOD unless noted
METRICS = [
    ("cheek_w",    "w", (234, 454), "face width at the cheekbones (outline by the ears) / IOD"),
    ("lowcheek_w", "w", (132, 361), "face width under the cheekbones, upper-lip level / IOD"),
    ("mouthlvl_w", "w", (58, 288),  "face width at mouth level / IOD"),
    ("jaw_w",      "w", (172, 397), "jaw width at the jaw angles (gonial) / IOD"),
    ("chin_w",     "w", (149, 378), "chin width, outline beside the chin / IOD"),
    ("nose_w",     "w", (129, 358), "nose width at the wings (alar) / IOD"),
    ("mouth_w",    "w", (61, 291),  "mouth width, corner to corner / IOD"),
    ("eyes_out_w", "w", (33, 263),  "outer eye corners / IOD"),
    ("eye_open",   "eye", ((159, 145, 33, 133), (386, 374, 263, 362)), "eye opening (lid to lid) / eye length, both eyes"),
    ("face_h",     "h", (N, ME),    "face height, nasion to chin / IOD"),
    ("nose_len",   "h", (N, SN),    "nasion to under the nose / IOD"),
    ("lower_face", "h/h", ((SN, ME), (N, ME)), "under the nose to chin / face height"),
    ("upper_lip",  "h/h", ((SN, "sto"), (SN, ME)), "under the nose to lip line / lower face"),
    ("chin_h",     "h", ("sto", ME), "lip line to chin / IOD"),
    ("lips_h",     "h/w", ((UL, LL), (61, 291)), "lip height (top of upper to bottom of lower) / mouth width"),
    ("face_wh",    "w/h", ((234, 454), (N, ME)), "cheekbone width / face height (higher = wider face)"),
    ("taper",      "w/w", ((172, 397), (234, 454)), "jaw width / cheekbone width (lower = more V-shaped)"),
    ("chin_angle", "deg", (172, ME, 397), "angle at the chin between the jaw lines, degrees (lower = sharper)"),
]
def _ids(x):
    if isinstance(x, (tuple, list)):
        for y in x:
            yield from _ids(y)
    elif isinstance(x, int):
        yield x


POINTS = sorted(set(_ids([m[2] for m in METRICS])) | {33, 133, 263, 362, ST_U, ST_L})   # drawn on overlays


def _pt(P, i):
    return (P[ST_U] + P[ST_L]) / 2 if i == "sto" else P[i]


def metrics(P):
    """P: (478+, 2) landmarks in a frame with x to the image's right and y up. Returns {name: value}."""
    cr, cl = (P[EYE_R[0]] + P[EYE_R[1]]) / 2, (P[EYE_L[0]] + P[EYE_L[1]]) / 2
    iod = float(np.linalg.norm(cl - cr))
    xa = (cl - cr) / iod
    ya = np.array([-xa[1], xa[0]])                       # up, across the eye line

    def w(a, b):
        return abs(float((_pt(P, b) - _pt(P, a)) @ xa))

    def h(a, b):
        return abs(float((_pt(P, b) - _pt(P, a)) @ ya))

    out = {}
    for name, kind, ids, _ in METRICS:
        if kind == "w":
            out[name] = w(*ids) / iod
        elif kind == "h":
            out[name] = h(*ids) / iod
        elif kind == "h/h":
            out[name] = h(*ids[0]) / h(*ids[1])
        elif kind == "h/w":
            out[name] = h(*ids[0]) / w(*ids[1])
        elif kind == "w/h":
            out[name] = w(*ids[0]) / h(*ids[1])
        elif kind == "w/w":
            out[name] = w(*ids[0]) / w(*ids[1])
        elif kind == "eye":
            out[name] = float(np.mean([h(a, b) / w(c, d) for a, b, c, d in ids]))
        elif kind == "deg":
            a, c, b = (_pt(P, i) for i in ids)
            u, v = a - c, b - c
            out[name] = math.degrees(math.acos(float(u @ v) / (np.linalg.norm(u) * np.linalg.norm(v))))
    return out


# ------------------------------------------------------------------ landmarks
_LM = None


def landmarker():
    global _LM
    if _LM is None:
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
        opts = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=MODEL),
                                            output_face_blendshapes=True,
                                            output_facial_transformation_matrixes=True, num_faces=4)
        _LM = vision.FaceLandmarker.create_from_options(opts)
    return _LM


def detect(img):
    """As tools/py/landmarks.detect, on a BGR array: faces sorted widest first."""
    import mediapipe as mp
    h, w = img.shape[:2]
    res = landmarker().detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                       data=np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))))
    faces = []
    for i, f in enumerate(res.face_landmarks):
        pts = [[p.x * w, p.y * h, p.z * w] for p in f]
        xs = [p[0] for p in pts]
        faces.append({"pts": pts, "width": max(xs) - min(xs),
                      "blend": {b.category_name: b.score for b in res.face_blendshapes[i]} if res.face_blendshapes else {},
                      "matrix": np.array(res.facial_transformation_matrixes[i]).tolist()
                      if res.facial_transformation_matrixes else None})
    faces.sort(key=lambda f: -f["width"])
    return {"w": w, "h": h, "faces": faces}


def load(path):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        from PIL import Image
        img = cv2.cvtColor(np.array(Image.open(path).convert("RGB")), cv2.COLOR_RGB2BGR)
    return img


def find_face(img):
    """Detect; a face that fills or overflows the frame (a game close-up) is found once the frame is padded."""
    r = detect(img)
    if r["faces"]:
        return r["faces"][0], (0, 0)
    for frac in (0.25, 0.6):
        p = int(max(img.shape[:2]) * frac)
        big = cv2.copyMakeBorder(img, p, p, p, p, cv2.BORDER_CONSTANT, value=(128, 128, 128))
        r = detect(big)
        if r["faces"]:
            f = r["faces"][0]
            f["pts"] = [[x - p, y - p, z] for x, y, z in f["pts"]]
            return f, (p, p)
    return None, None


def pose(face):
    """Rotation (canonical face -> camera) and yaw / pitch / roll in degrees (yaw > 0: the face turns to the
    image's right; pitch > 0: it looks up)."""
    M = np.array(face["matrix"])
    U, _, Vt = np.linalg.svd(M[:3, :3])
    R = U @ Vt
    f, x = R[:, 2], R[:, 0]
    yaw = math.degrees(math.atan2(f[0], f[2]))
    pitch = math.degrees(math.atan2(f[1], math.hypot(f[0], f[2])))
    roll = math.degrees(math.atan2(x[1], x[0]))
    return R, (yaw, pitch, roll)


def frontal(face, raw=False):
    """2D landmarks, x right, y up; turned to face the camera with the head pose unless raw."""
    P = np.array(face["pts"], float)
    Q = np.stack([P[:, 0], -P[:, 1], -P[:, 2]], 1)       # image (y down, z away) -> right-handed, z to the viewer
    if raw or face.get("matrix") is None:
        return Q[:, :2]
    R, _ = pose(face)
    Q = (Q - Q.mean(0)) @ R                                # camera -> face frame (R^T applied to each point)
    return Q[:, :2]


# ------------------------------------------------------------------ perspective
def canonical():
    """MediaPipe's canonical face (468 points, cm; x to the face's left = image right, y up, z out of the face),
    read from the geometry metadata inside face_landmarker.task."""
    b = zipfile.ZipFile(MODEL).read("geometry_pipeline_metadata_landmarks.binarypb")

    def varint(b, i):
        r = s = 0
        while True:
            c = b[i]; i += 1; r |= (c & 0x7F) << s; s += 7
            if c < 0x80:
                return r, i

    def fields(b):
        i = 0
        while i < len(b):
            k, i = varint(b, i)
            f, t = k >> 3, k & 7
            if t == 0:
                v, i = varint(b, i)
            elif t == 1:
                v = b[i:i + 8]; i += 8
            elif t == 5:
                v = struct.unpack("<f", b[i:i + 4])[0]; i += 4
            elif t == 2:
                n, i = varint(b, i); v = b[i:i + n]; i += n
            else:
                raise ValueError(f"wire type {t}")
            yield f, t, v

    mesh = next(v for f, t, v in fields(b) if f == 1)       # canonical_mesh
    fl = []
    for f, t, v in fields(mesh):
        if f == 3:                                          # vertex_buffer: x y z u v per vertex
            fl += [v] if t == 5 else list(struct.unpack(f"<{len(v) // 4}f", v))
    return np.array(fl).reshape(-1, 5)[:, :3]


def perspective_bias(dist_cm, C=None):
    """{metric: ratio seen by a pinhole camera dist_cm in front of the nose tip / the same ratio orthographic}."""
    C = canonical() if C is None else C
    ortho = metrics(C[:, :2])
    depth = dist_cm + (C[4, 2] - C[:, 2])
    proj = metrics(C[:, :2] * (dist_cm / depth)[:, None])
    return {k: proj[k] / ortho[k] for k in ortho}


# ------------------------------------------------------------------ measuring an image
def jittered(img, rng):
    h, w = img.shape[:2]
    s = rng.uniform(0.82, 1.18)
    a = rng.uniform(-4, 4)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), a, s)
    M[:, 2] += rng.uniform(-0.04, 0.04, 2) * (w, h)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def measure_anchors(path):
    """A built character's own landmark points (tools/out/scan_<id>/portrait_mesh.npz from scan_wrap.paint_portrait:
    AK = MediaPipe ids, AP = their points on the final mesh, Blender metres), seen orthographically from the front.
    Ids without an MPFB anchor (the jaw angles 58/172/288/397) give nan."""
    d = np.load(path)
    P = np.full((478, 2), np.nan)
    P[d["AK"]] = d["AP"][:, [0, 2]]
    with np.errstate(invalid="ignore"):
        m = metrics(P)
    return {"path": path, "landmarks": "mesh anchors", "size": None, "iod_px": None, "yaw": 0.0, "pitch": 0.0,
            "roll": 0.0, "smile": 0.0, "jaw_open": 0.0, "metrics": m, "face": None}


def measure(path, fresh=False, raw=False, jitter=0, seed=1):
    if path.endswith(".npz"):
        return measure_anchors(path)
    img = load(path)
    cache = path + ".lm.json"
    face = None
    if not fresh and os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(path):
        faces = json.load(open(cache))["faces"]
        face = faces[0] if faces else None
        src = "cached"
    if face is None:
        face, _ = find_face(img)
        src = "detected"
    if face is None:
        return {"path": path, "error": "no face found"}
    m = metrics(frontal(face, raw))
    _, (yaw, pitch, roll) = pose(face) if face.get("matrix") else (None, (float("nan"),) * 3)
    P = np.array(face["pts"])
    iod_px = float(np.linalg.norm((P[33, :2] + P[133, :2]) / 2 - (P[263, :2] + P[362, :2]) / 2))
    out = {"path": path, "landmarks": src, "size": [img.shape[1], img.shape[0]], "iod_px": round(iod_px, 1),
           "yaw": round(yaw, 1), "pitch": round(pitch, 1), "roll": round(roll, 1),
           "smile": round(float(np.mean([face.get("blend", {}).get(k, 0) for k in ("mouthSmileLeft", "mouthSmileRight")])), 2),
           "jaw_open": round(float(face.get("blend", {}).get("jawOpen", 0)), 2),
           "metrics": m, "face": face}
    if jitter:
        rng = np.random.default_rng(seed)
        runs = []
        for _ in range(jitter):
            f, _ = find_face(jittered(img, rng))
            if f is not None:
                runs.append(metrics(frontal(f, raw)))
        if runs:
            # the reported value is the mean over the image and its jittered copies (steadier than one detection)
            out["noise"] = {k: float(np.std([r[k] for r in runs] + [m[k]])) for k in m}
            out["metrics_single"] = m
            out["metrics"] = {k: float(np.mean([r[k] for r in runs] + [m[k]])) for k in m}
            out["jitter_runs"] = len(runs)
    return out


def overlay(res, path, out_dir, label):
    img = load(res["path"])
    P = np.array(res["face"]["pts"])[:, :2]
    x0, y0 = P.min(0); x1, y1 = P.max(0)
    pad = 0.12 * max(x1 - x0, y1 - y0)       # tight: keep people beside the subject out
    x0, y0 = int(max(0, x0 - pad)), int(max(0, y0 - pad))
    x1, y1 = int(min(img.shape[1], x1 + pad)), int(min(img.shape[0], y1 + pad))
    crop = img[y0:y1, x0:x1].copy()
    k = 900.0 / max(crop.shape[:2])
    crop = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    Q = (P - (x0, y0)) * k
    col = {"w": (60, 220, 255), "h": (255, 160, 60)}
    for name, kind, ids, _ in METRICS:
        pairs = ([ids] if kind in ("w", "h") else [(e[0], e[1]) for e in ids] if kind == "eye"
                 else [(ids[0], ids[1]), (ids[1], ids[2])] if kind == "deg" else [ids[0], ids[1]])
        for a, b in pairs:
            pa = (Q[ST_U] + Q[ST_L]) / 2 if a == "sto" else Q[a]
            pb = (Q[ST_U] + Q[ST_L]) / 2 if b == "sto" else Q[b]
            c = col["w"] if kind.startswith("w") else col["h"] if kind.startswith("h") else (120, 255, 120)
            cv2.line(crop, tuple(np.round(pa).astype(int)), tuple(np.round(pb).astype(int)), c, 1, cv2.LINE_AA)
    for i in POINTS:
        cv2.circle(crop, tuple(np.round(Q[i]).astype(int)), 3, (0, 0, 255), -1, cv2.LINE_AA)
    for e in (EYE_R, EYE_L):
        c = (Q[e[0]] + Q[e[1]]) / 2
        cv2.drawMarker(crop, tuple(np.round(c).astype(int)), (255, 255, 255), cv2.MARKER_CROSS, 12, 1)
    cv2.putText(crop, f"{label}  yaw {res['yaw']:+.0f}  pitch {res['pitch']:+.0f}", (10, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"{label}_metrics.png")
    cv2.imwrite(p, crop)
    return p


def main():
    opts = {a[2:].split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else "1") for a in sys.argv[1:] if a.startswith("--")}
    items = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not items and "persp" not in opts:
        print(__doc__)
        return
    if "persp" in opts:
        C = canonical()
        dists = (25, 35, 50, 75, 150, 300)
        print("perspective bias, canonical face: ratio seen at <cm> from the nose tip / orthographic, in %")
        print(f"{'':12s}" + "".join(f"{d:>8d}" for d in dists))
        tab = {d: perspective_bias(d, C) for d in dists}
        for name, *_ in METRICS:
            print(f"{name:12s}" + "".join(f"{(tab[d][name] - 1) * 100:+8.1f}" for d in dists))
        if not items:
            return
    ref = int(opts.get("ref", 0))
    results = []
    for it in items:
        it, _, dist = it.partition("#")
        path, _, label = it.partition("@")
        label = label or os.path.splitext(os.path.basename(path))[0]
        r = measure(path, fresh="fresh" in opts, raw="raw" in opts, jitter=int(opts.get("jitter", 0)))
        r["label"] = label
        if "error" in r:
            print(f"{label}: {r['error']}")
            results.append(r)
            continue
        if dist:
            # as if seen orthographically: undo a camera this far from the nose tip (canonical face's depths)
            bias = perspective_bias(float(dist))
            r["metrics"] = {k: v / bias[k] for k, v in r["metrics"].items()}
            r["perspective_undone_cm"] = float(dist)
        if "overlay" in opts and r["face"] is not None:
            r["overlay"] = overlay(r, path, opts["overlay"], label)
        results.append(r)
    ok = [r for r in results if "error" not in r]
    if not ok:
        return
    base = results[ref] if ref < len(results) and "error" not in results[ref] else ok[0]
    lab_w = max(12, max(len(r["label"]) for r in ok) + 1)
    names = [m[0] for m in METRICS]
    lines = []
    head = f"{'':{lab_w}s}" + "".join(f"{n:>12s}" for n in names)
    print(head + "   (reference row: values; others: % from it" + (", jitter means" if "jitter" in opts else "") + ")")
    for r in ok:
        if r is base:
            row = "".join(f"{r['metrics'][n]:12.3f}" for n in names)
        else:
            row = "".join(f"{(r['metrics'][n] / base['metrics'][n] - 1) * 100:+11.1f}%" for n in names)
        print(f"{r['label']:{lab_w}s}{row}")
        if "noise" in r:
            nz = "".join(f"{'+-' + format(r['noise'][n] / base['metrics'][n] * 100, '.1f') + '%':>12s}" for n in names)
            print(f"{'  noise':{lab_w}s}{nz}")
    print()
    for r in ok:
        print(f"{r['label']}: {r['landmarks']}, IOD {r['iod_px']} px, yaw {r['yaw']:+.1f} pitch {r['pitch']:+.1f} "
              f"roll {r['roll']:+.1f}, smile {r['smile']}, jaw open {r['jaw_open']}"
              + (f", {r['jitter_runs']} jitter runs" if "jitter_runs" in r else "")
              + (f", overlay {r['overlay']}" if "overlay" in r else ""))
    if "json" in opts:
        dump = [{k: v for k, v in r.items() if k != "face"} for r in results]
        json.dump({"reference": base["label"],
                   "definitions": {m[0]: m[3] for m in METRICS}, "images": dump}, open(opts["json"], "w"), indent=1)
    if "md" in opts:
        md = ["| ratio | " + " | ".join(r["label"] for r in ok) + " |",
              "|---|" + "---|" * len(ok)]
        for name, _, _, desc in METRICS:
            cells = []
            for r in ok:
                v = r["metrics"][name]
                s = f"{v:.3f}" if r is base else f"{v:.3f} ({(v / base['metrics'][name] - 1) * 100:+.1f}%)"
                if "noise" in r:
                    s += f" ±{r['noise'][name] / base['metrics'][name] * 100:.1f}%"
                cells.append(s)
            md.append(f"| `{name}` {desc} | " + " | ".join(cells) + " |")
        md.append("| pose yaw / pitch (deg) | " + " | ".join(f"{r['yaw']:+.0f} / {r['pitch']:+.0f}" for r in ok) + " |")
        open(opts["md"], "w").write("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
