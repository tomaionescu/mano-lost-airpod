"""Make an MPFB head look like a real person from photos (called by build_human.py).

1. Landmark anchors (face_calib.py) give 468 points on this character's face.
2. tools/py/face_solve.py fits them to each photo's MediaPipe landmarks: camera pose + per-point displacements.
   With several photos (spec["photos"], best frontal one first) the displacements are averaged: each photo only
   moves points within its own image plane, so different angles together pin down the face better than one.
3. A Gaussian RBF spreads the displacements over the head (and the eyes, teeth, lashes, hair, glasses).
4. tools/py/face_texture.py projects the cleaned, de-lit first photo into the skin texture.
"""
import bpy, os, json, subprocess
import numpy as np

PY = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"
SIGMA = 0.022     # RBF radius (m): landmarks are ~1 cm apart
LAMBDA = 2e-3     # regularisation


def log(*a):
    print("[face]", *a, flush=True)


def world_verts(obj):
    mw = np.array(obj.matrix_world)
    co = np.empty(len(obj.data.vertices) * 3, np.float64)
    obj.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return co @ mw[:3, :3].T + mw[:3, 3]


def set_world_verts(obj, P):
    mw = np.array(obj.matrix_world)
    inv = np.linalg.inv(mw)
    local = P @ inv[:3, :3].T + inv[:3, 3]
    obj.data.vertices.foreach_set("co", local.astype(np.float32).ravel())
    obj.data.update()


class Field:
    def __init__(self, X, D):
        self.X = X
        d2 = ((X[:, None, :] - X[None, :, :]) ** 2).sum(-1)
        Kmat = np.exp(-d2 / SIGMA ** 2) + LAMBDA * np.eye(len(X))
        self.alpha = np.linalg.solve(Kmat, D)

    def __call__(self, P):
        out = np.zeros_like(P)
        for s in range(0, len(P), 4000):
            d2 = ((P[s:s + 4000, None, :] - self.X[None, :, :]) ** 2).sum(-1)
            out[s:s + 4000] = np.exp(-d2 / SIGMA ** 2) @ self.alpha
        return out


def photo_png(photo, root):
    """OpenCV-friendly copy of the photo (webp -> png)."""
    out = os.path.join(root, "tools", "out", os.path.basename(photo) + ".png")
    if not os.path.exists(out):
        subprocess.run([PY, "-c", f"from PIL import Image; Image.open({photo!r}).convert('RGB').save({out!r})"], check=True)
    return out


def landmarks_for(photo, root):
    lm_path = photo + ".lm.json"
    if not os.path.exists(lm_path):
        subprocess.run([PY, os.path.join(root, "tools", "py", "landmarks.py"), photo], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return lm_path


def run_solve(cfg, work, tag, cid, root):
    solve_in, solve_out = os.path.join(work, f"solve_in{tag}.json"), os.path.join(work, f"solve{tag}.json")
    json.dump(cfg, open(solve_in, "w"))
    r = subprocess.run([PY, os.path.join(root, "tools", "py", "face_solve.py"), solve_in, solve_out], capture_output=True, text=True)
    log(cid, tag or "", (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else "solve failed")
    return solve_out


def apply(basemesh, rig, spec, cid, root):
    photos = spec.get("photos") or [spec["photo"]]
    photo = os.path.join(root, "tools", "photos", photos[0])
    lm_path = landmarks_for(photo, root)
    anchors = json.load(open(os.path.join(root, "tools", "models", "mpfb_face_anchors.json")))["anchors"]
    V = world_verts(basemesh)
    A = [None if a is None else (V[a["v"]] * np.array(a["w"])[:, None]).sum(0).tolist() for a in anchors]
    work = os.path.join(root, "tools", "out", f"face_{cid}")
    os.makedirs(work, exist_ok=True)
    base_cfg = {"anchors": A, "ignore": spec.get("photo_ignore", []), "oval_weight": spec.get("oval_weight", 0.35)}
    solve_out = run_solve(dict(base_cfg, photo_lm=lm_path), work, "", cid, root)
    if len(photos) > 1:
        # average the shape over every photo that fitted well (the main photo counts double)
        acc = np.zeros((len(A), 3))
        wsum = np.zeros(len(A))
        for i, ph in enumerate(photos):
            out_i = solve_out if i == 0 else run_solve(
                dict(base_cfg, photo_lm=landmarks_for(os.path.join(root, "tools", "photos", ph), root)), work, f"_{i}", cid, root)
            sol_i = json.load(open(out_i))
            rel = sol_i["err_after_px"] / max(sol_i["face_px"], 1.0)
            if rel > 0.035:
                log(cid, f"skipping {ph}: fit error {rel:.3f} of the face width")
                continue
            w = 2.0 if i == 0 else 1.0
            for k, d in enumerate(sol_i["disp"]):
                if d is not None:
                    acc[k] += w * np.array(d)
                    wsum[k] += w
        fixed = [(acc[k] / wsum[k]).tolist() if wsum[k] > 0 else None for k in range(len(A))]
        solve_out = run_solve(dict(base_cfg, photo_lm=lm_path, fixed_disp=fixed), work, "_avg", cid, root)
    sol = json.load(open(solve_out))
    valid = [i for i, d in enumerate(sol["disp"]) if d is not None]
    X = np.array([A[i] for i in valid])
    D = np.array([sol["disp"][i] for i in valid])
    field = Field(X, D)

    # deform the head and everything that sits on it
    set_world_verts(basemesh, V + field(V))
    for obj in [o for o in rig.children if o.type == 'MESH' and o != basemesh]:
        P = world_verts(obj)
        name = obj.name.lower()
        d = field(P)
        if any(k in name for k in ("high-poly", "low-poly", "teeth", "tongue")):
            d = np.repeat(d.mean(0, keepdims=True), len(P), 0)          # rigid: keep eyeballs round
        elif "glasses" in name:
            d = np.repeat(np.median(d, 0, keepdims=True), len(P), 0)
        if np.abs(d).max() > 1e-5:
            set_world_verts(obj, P + d)

    # mesh data for the texture projection (body faces only, deformed)
    mesh = basemesh.data
    body = basemesh.vertex_groups["body"].index
    in_body = np.zeros(len(mesh.vertices), bool)
    for v in mesh.vertices:
        in_body[v.index] = any(g.group == body and g.weight > 0.5 for g in v.groups)
    mesh.calc_loop_triangles()
    uv_layer = mesh.uv_layers.active.data
    T, UVs = [], []
    for lt in mesh.loop_triangles:
        vs = list(lt.vertices)
        if not in_body[vs].all():
            continue
        T.append(vs)
        UVs.append([tuple(uv_layer[l].uv) for l in lt.loops])
    Vd = world_verts(basemesh)
    N = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("normal", N)
    N = N.reshape(-1, 3) @ np.array(basemesh.matrix_world)[:3, :3].T
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    npz = os.path.join(work, "mesh.npz")
    np.savez(npz, V=Vd, T=np.array(T), UV=np.array(UVs), N=N)

    # base skin texture of the current material
    mat = basemesh.active_material
    tex_node = next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image)
    base_path = bpy.path.abspath(tex_node.image.filepath)
    out = os.path.join(work, f"{cid}_skin.png")
    job = {"mesh": npz, "solve": solve_out, "photo_png": photo_png(photo, root), "photo_lm": lm_path,
           "base_texture": base_path, "out": out, "size": spec.get("skin_size", 4096),
           "glasses_in_photo": bool(spec.get("glasses_in_photo", spec.get("glasses"))),
           "ignore": spec.get("photo_ignore", []), "delight": spec.get("delight", 0.7),
           "skin_ref": spec.get("skin_ref"), "eye_weight": spec.get("eye_weight", 0.35),
           "no_forehead": spec.get("no_forehead", False),
           # (cast "glasses_smooth" / "photo_tex_keep", off by default; face_texture.py)
           "glasses_smooth": spec.get("glasses_smooth"), "tex_keep": spec.get("photo_tex_keep"),
           # (cast "mouth_lift", off by default; face_texture.mouth_lift)
           "mouth_lift": spec.get("mouth_lift"),
           # (cast "brow_deepen", off by default; face_texture.brow_deepen)
           "brow_deepen": spec.get("brow_deepen")}
    job_path = os.path.join(work, "texture_job.json")
    json.dump(job, open(job_path, "w"))
    r = subprocess.run([PY, os.path.join(root, "tools", "py", "face_texture.py"), job_path], capture_output=True, text=True)
    lines = (r.stdout + r.stderr).strip().splitlines()
    log(cid, lines[-1] if lines else "texture failed")
    if r.returncode != 0:
        raise RuntimeError("face_texture failed:\n" + r.stderr[-2000:])
    tex_node.image = bpy.data.images.load(out, check_existing=False)
    return sol
