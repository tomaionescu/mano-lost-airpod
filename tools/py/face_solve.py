"""Fit MakeHuman face anchor points to a photo's MediaPipe landmarks.

Input JSON: {"anchors": [[x,y,z] or null]*468 (Blender coords, metres), "photo_lm": path, "ignore": ["mouth", ...]}
Output JSON: per-anchor displacement (metres, Blender coords), camera (R, t, K), reprojection error.
Pose comes from solvePnP (focal length searched); shape changes are residuals pushed back into 3D in the
image plane, symmetrised, clamped and iterated. Depth is never invented: only x/y in the photo's view.
"""
import json, sys
import numpy as np, cv2

# MediaPipe face mesh regions (subset of FaceLandmarksConnections, as vertex index sets)
LIPS = {0, 13, 14, 17, 37, 39, 40, 61, 78, 80, 81, 82, 84, 87, 88, 91, 95, 146, 178, 181, 185, 191, 267, 269, 270,
        291, 308, 310, 311, 312, 314, 317, 318, 321, 324, 375, 402, 405, 409, 415}
LEFT_EYE = {263, 249, 390, 373, 374, 380, 381, 382, 362, 466, 388, 387, 386, 385, 384, 398}
RIGHT_EYE = {33, 7, 163, 144, 145, 153, 154, 155, 133, 246, 161, 160, 159, 158, 157, 173}
BROWS = {276, 283, 282, 295, 285, 300, 293, 334, 296, 336, 46, 53, 52, 65, 55, 70, 63, 105, 66, 107}
OVAL = {10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149,
        150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109}
NOSE = {1, 2, 4, 5, 6, 19, 45, 48, 64, 94, 97, 98, 115, 168, 195, 197, 220, 275, 278, 294, 326, 327, 344, 440}
CHIN = {152, 148, 176, 149, 150, 377, 400, 378, 379, 175, 171, 396, 199, 200, 208, 428}


def weights_for(n, ignore, oval_w=0.35):
    w = np.full(n, 0.55)
    for i in NOSE: w[i] = 1.0
    for i in LEFT_EYE | RIGHT_EYE: w[i] = 1.0
    for i in BROWS: w[i] = 0.8
    for i in OVAL: w[i] = oval_w   # silhouette points slide with head pose
    for i in LIPS: w[i] = 0.0 if "mouth" in ignore else 0.75
    if "mouth" in ignore:
        for i in CHIN: w[i] = 0.25
    return w


def solve(X, L, size, ignore):
    """X: (n,3) object points, L: (n,2) image points (pixels). Returns best (err, f, rvec, tvec)."""
    w, h = size
    valid = ~np.isnan(X[:, 0])
    # rigid points: nose, eye corners, brows, oval — not the mouth (expressions move it)
    rigid = np.array([i in NOSE or i in LEFT_EYE or i in RIGHT_EYE or i in BROWS for i in range(len(X))]) & valid
    best = None
    for k in (0.6, 0.75, 0.9, 1.1, 1.35, 1.7, 2.2, 3.0, 4.5, 7.0, 12.0, 25.0):
        f = k * max(w, h)
        K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=np.float64)
        ok, rv, tv = cv2.solvePnP(X[rigid].astype(np.float64), L[rigid].astype(np.float64), K, None, flags=cv2.SOLVEPNP_EPNP)
        if not ok:
            continue
        ok, rv, tv = cv2.solvePnP(X[rigid].astype(np.float64), L[rigid].astype(np.float64), K, None, rv, tv, True, cv2.SOLVEPNP_ITERATIVE)
        proj, _ = cv2.projectPoints(X[rigid].astype(np.float64), rv, tv, K, None)
        err = np.sqrt(((proj[:, 0] - L[rigid]) ** 2).sum(1)).mean()
        if best is None or err < best[0]:
            best = (err, f, rv, tv, K)
    return best


def mirror_pairs(X):
    """For each anchor, the index of its mirror image across the face's symmetry plane (Blender x -> -x)."""
    valid = ~np.isnan(X[:, 0])
    M = X.copy(); M[:, 0] *= -1
    pairs = np.full(len(X), -1)
    for i in range(len(X)):
        if not valid[i]: continue
        d = np.linalg.norm(X[valid] - M[i], axis=1)
        j = np.flatnonzero(valid)[np.argmin(d)]
        if d.min() < 0.006: pairs[i] = j
    return pairs


def main(inp, outp):
    cfg = json.load(open(inp))
    A = np.array([a if a is not None else [np.nan] * 3 for a in cfg["anchors"]], dtype=np.float64)
    lm = json.load(open(cfg["photo_lm"]))
    face = lm["faces"][0]
    L = np.array(face["pts"])[:468, :2]
    size = (lm["w"], lm["h"])
    ignore = cfg.get("ignore", [])
    blend = face.get("blend", {})
    if blend.get("jawOpen", 0) > 0.25 or blend.get("mouthPucker", 0) > 0.5 or blend.get("mouthFunnel", 0) > 0.4:
        ignore = list(set(ignore) | {"mouth"})
    wts = weights_for(len(A), ignore, cfg.get("oval_weight", 0.35))
    valid = ~np.isnan(A[:, 0])
    if cfg.get("fixed_disp") is not None:
        # shape already decided (several photos averaged): only find this photo's camera for the texture
        D = np.array([d if d is not None else [0.0, 0.0, 0.0] for d in cfg["fixed_disp"]], dtype=np.float64)
        err, f, rv, tv, K = solve(A + D, L, size, ignore)
        R, _ = cv2.Rodrigues(rv)
        total = np.linalg.norm(D[valid], axis=1)
        out = {"disp": [list(map(float, x)) if v else None for x, v in zip(D, valid)],
               "R": R.tolist(), "t": tv.ravel().tolist(), "K": K.tolist(), "size": list(size),
               "err_before_px": float(err), "err_after_px": float(err), "face_px": float(np.ptp(L[list(OVAL)][:, 0])),
               "max_disp_mm": float(total.max() * 1000), "mean_disp_mm": float(total.mean() * 1000), "ignore": ignore}
        json.dump(out, open(outp, "w"))
        print(f"[solve] camera for the averaged shape: err {err:.1f}px, f={f / max(size):.2f}*max")
        return
    pairs = mirror_pairs(A)
    X = A.copy()
    D = np.zeros_like(A)
    best = solve(X, L, size, ignore)
    err0 = best[0]
    face_px = np.ptp(L[list(OVAL)][:, 0])
    for it in range(6):
        err, f, rv, tv, K = best
        R, _ = cv2.Rodrigues(rv)
        Xc = (R @ X[valid].T).T + tv.reshape(1, 3)
        proj, _ = cv2.projectPoints(X[valid], rv, tv, K, None)
        r = L[valid] - proj[:, 0]
        # residual (pixels) -> camera-plane displacement (metres) -> object space
        dc = np.zeros((len(r), 3))
        dc[:, 0] = r[:, 0] * Xc[:, 2] / f
        dc[:, 1] = r[:, 1] * Xc[:, 2] / f
        d = np.zeros_like(A)
        d[valid] = (R.T @ dc.T).T
        d *= wts[:, None]
        # half-symmetrise: real faces are a little asymmetric, photos and landmarks add noise
        ds = d.copy()
        for i in range(len(d)):
            j = pairs[i]
            if j >= 0:
                m = d[j].copy(); m[0] *= -1
                ds[i] = 0.5 * (d[i] + m)
        d = 0.4 * d + 0.6 * ds
        mag = np.linalg.norm(d, axis=1, keepdims=True)
        d *= np.minimum(1.0, 0.012 / np.maximum(mag, 1e-9))
        step = 0.85
        X[valid] += step * d[valid]
        D[valid] += step * d[valid]
        tot = np.linalg.norm(D, axis=1, keepdims=True)
        over = np.minimum(1.0, 0.014 / np.maximum(tot, 1e-9))
        X[valid] = A[valid] + D[valid] * over[valid]
        D[valid] = D[valid] * over[valid]
        best = solve(X, L, size, ignore)
    total = np.linalg.norm(D[valid], axis=1)
    err, f, rv, tv, K = best
    R, _ = cv2.Rodrigues(rv)
    out = {"disp": [list(map(float, x)) if v else None for x, v in zip(D, valid)],
           "R": R.tolist(), "t": tv.ravel().tolist(), "K": K.tolist(), "size": list(size),
           "err_before_px": float(err0), "err_after_px": float(err), "face_px": float(face_px),
           "max_disp_mm": float(total.max() * 1000), "mean_disp_mm": float(total.mean() * 1000), "ignore": ignore}
    json.dump(out, open(outp, "w"))
    print(f"[solve] err {err0:.1f}px -> {err:.1f}px (face {face_px:.0f}px), f={f / max(size):.2f}*max, "
          f"disp mean {out['mean_disp_mm']:.1f}mm max {out['max_disp_mm']:.1f}mm, ignore={ignore}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
