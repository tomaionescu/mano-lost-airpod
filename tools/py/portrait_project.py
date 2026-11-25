"""Project a sharp studio portrait onto a scanned character's face (tools/blender/scan_wrap.py, portrait mode).

The face's geometry comes from the scan; the scan's own face texture is soft (a full-body image gives a face
~200 px wide). The portrait (same person, frontal, even light, ~1000 px face) is warped onto it instead: each
face vertex is placed in the portrait by a landmark-driven 2D map (least-squares affine from the character's
face landmarks seen from the front to the portrait's MediaPipe landmarks, plus a thin-plate correction), so
eyelids, brows, nostrils and lips land on the geometry's own. Every head triangle is rasterised in the head
texture's UV space; the result is colour-matched to the scan's skin around it and feathered in.

usage: python3.11 portrait_project.py <job.json>
job: {"mesh": npz (V world verts, T head triangles, UV per-corner uv (n,3,2), N vertex normals, W face weight per
      vertex, AK anchor landmark ids, AP anchor positions), "portrait": png, "landmarks": .lm.json,
      "texture": head colour png to paint over, "out": png}
"""
import json, sys
import numpy as np, cv2


OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149,
        150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
# outer lip contour: the lips curve away from the camera fast, so they get the portrait at steeper angles than the
# rest of the face (otherwise the scan's own, misplaced lip line showed through as torn pale strips)
LIPS_OUT = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]


def to_lab(bgr):
    return cv2.cvtColor(bgr.astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)


def tps_fit(src, dst, reg=1e-3):
    """Thin-plate spline src (n,2) -> dst (n,2) residual map, in units of the src spread."""
    n = len(src)
    d = np.sqrt(((src[:, None] - src[None]) ** 2).sum(-1))
    K = np.where(d > 0, d * d * np.log(d + 1e-12), 0.0) + reg * np.eye(n)
    P = np.hstack([np.ones((n, 1)), src])
    A = np.zeros((n + 3, n + 3))
    A[:n, :n], A[:n, n:], A[n:, :n] = K, P, P.T
    b = np.zeros((n + 3, 2))
    b[:n] = dst
    return np.linalg.solve(A, b)


def tps_apply(coef, src, pts):
    d = np.sqrt(((pts[:, None] - src[None]) ** 2).sum(-1))
    U = np.where(d > 0, d * d * np.log(d + 1e-12), 0.0)
    n = len(src)
    return U @ coef[:n] + coef[n] + pts @ coef[n + 1:n + 3]


def main():
    # numpy's Accelerate matmul on macOS raises spurious overflow / divide-by-zero flags on finite data
    np.seterr(all="ignore")
    job = json.load(open(sys.argv[1]))
    m = np.load(job["mesh"])
    V, T, UV, N, W = m["V"], m["T"], m["UV"], m["N"], m["W"]
    AK, AP = list(m["AK"]), m["AP"]
    lm = json.load(open(job["landmarks"]))["faces"]
    if not lm:
        raise SystemExit("no face in the portrait")
    L = np.array(lm[0]["pts"])[:, :2]
    img = cv2.imread(job["portrait"], cv2.IMREAD_COLOR)
    tex = cv2.imread(job["texture"], cv2.IMREAD_COLOR)
    size = tex.shape[0]

    # front view of the character: x to the right, z up (image y down); normalised by the landmark spread
    def front(P):
        return np.stack([P[:, 0], -P[:, 2]], 1)
    S = front(AP)
    c, s = S.mean(0), np.sqrt(((S - S.mean(0)) ** 2).sum(1).mean())
    Sn = (S - c) / s
    D = L[AK]
    # affine first, then a regularised thin-plate correction of what the affine leaves
    Ah = np.hstack([Sn, np.ones((len(Sn), 1))])
    M, *_ = np.linalg.lstsq(Ah, D, rcond=None)
    res = D - Ah @ M
    coef = tps_fit(Sn, res, reg=job.get("tps_reg", 2e-2))
    Vn = (front(V) - c) / s
    PV = np.hstack([Vn, np.ones((len(Vn), 1))]) @ M + tps_apply(coef, Sn, Vn)
    err = np.linalg.norm(Ah @ M + tps_apply(coef, Sn, Sn) - D, axis=1)
    print(f"[portrait] {len(AK)} landmarks, fit error median {np.median(err):.1f} px, max {err.max():.1f} px "
          f"(face {np.ptp(L[:, 0]):.0f} px wide)", flush=True)

    # the portrait only paints inside its own face outline (shrunk and feathered): beyond it the map is a guess
    # and painted hair or background onto the cheeks; the scan's texture stays there
    face = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(face, [np.round(L[OVAL]).astype(np.int32)], 255)
    fw = float(np.ptp(L[:, 0]))
    k = int(fw * 0.035) | 1
    face = cv2.erode(face, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    face = cv2.GaussianBlur(face, (0, 0), fw * 0.02)
    img4 = np.dstack([img, face])
    # how much of each vertex the portrait may paint: facing the camera, and on the face; on the lips (inside the
    # portrait's lip outline, grown a little) down to surfaces seen at a steep angle
    facing = np.clip((-N[:, 1] - 0.3) / 0.4, 0, 1)
    lip = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(lip, [np.round(L[LIPS_OUT]).astype(np.int32)], 255)
    mw = float(np.ptp(L[LIPS_OUT][:, 0]))
    k = int(mw * 0.12) | 1
    lip = cv2.GaussianBlur(cv2.dilate(lip, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))), (0, 0), mw * 0.04)
    px = np.clip(np.round(PV).astype(int), 0, [img.shape[1] - 1, img.shape[0] - 1])
    on_lip = lip[px[:, 1], px[:, 0]].astype(np.float32) / 255.0
    facing = np.maximum(facing, on_lip * np.clip((-N[:, 1] + 0.15) / 0.4, 0, 1))
    alpha_v = facing * np.clip(W, 0, 1)
    acc = np.zeros((size, size, 3), np.float32)
    wsum = np.zeros((size, size), np.float32)
    for t in range(len(T)):
        av = alpha_v[T[t]]
        if av.max() < 0.02:
            continue
        uv = UV[t] * [size, size]
        uv[:, 1] = size - uv[:, 1]                       # texture rows run top-down in the image
        x0, y0 = np.floor(uv.min(0)).astype(int) - 1
        x1, y1 = np.ceil(uv.max(0)).astype(int) + 2
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size), min(y1, size)
        if x1 <= x0 or y1 <= y0:
            continue
        src = PV[T[t]].astype(np.float32)
        dst = (uv - [x0, y0]).astype(np.float32)
        Mt = cv2.getAffineTransform(dst, src)             # texture pixel -> portrait pixel
        patch = cv2.warpAffine(img4, Mt, (x1 - x0, y1 - y0), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillConvexPoly(mask, np.round(dst * 4).astype(np.int32), 255, lineType=cv2.LINE_AA, shift=2)
        # the vertices' alpha interpolated across the triangle (barycentric), not one value per triangle: a
        # constant per triangle left a jagged patchwork wherever the alpha changes fast (the lips' edges)
        e = np.array([[dst[0, 0] - dst[2, 0], dst[1, 0] - dst[2, 0]], [dst[0, 1] - dst[2, 1], dst[1, 1] - dst[2, 1]]])
        if abs(np.linalg.det(e)) > 1e-9:
            gy, gx = np.mgrid[0:y1 - y0, 0:x1 - x0].astype(np.float32) + 0.5
            b01 = np.stack([gx - dst[2, 0], gy - dst[2, 1]], -1) @ np.linalg.inv(e).T
            ap = np.clip(b01[..., 0] * av[0] + b01[..., 1] * av[1] + (1 - b01[..., 0] - b01[..., 1]) * av[2], 0, 1)
        else:
            ap = float(av.mean())
        mk = (mask.astype(np.float32) / 255.0) * ap * (patch[..., 3].astype(np.float32) / 255.0)
        acc[y0:y1, x0:x1] += patch[..., :3].astype(np.float32) * mk[..., None]
        wsum[y0:y1, x0:x1] += mk
    paint = acc / np.maximum(wsum, 1e-6)[..., None]
    alpha = np.clip(wsum, 0, 1)
    # soft edge: shrink a little, then feather
    k = max(3, size // 400) | 1
    alpha = cv2.erode(alpha, np.ones((k, k), np.uint8))
    alpha = cv2.GaussianBlur(alpha, (0, 0), size / 600)

    # colour-match the portrait to the scan's skin where both exist (mean and spread per Lab channel)
    sel = alpha > 0.6
    if sel.sum() > 500:
        pl, tl = to_lab(paint.clip(0, 255))[sel], to_lab(tex)[sel]
        gain = np.clip(tl.std(0) / np.maximum(pl.std(0), 1e-3), 0.7, 1.3)
        gain[0] = 1.0                                     # keep the portrait's own shading contrast
        lab = to_lab(paint.clip(0, 255))
        lab = (lab - pl.mean(0)) * gain + pl.mean(0) + 0.7 * (tl.mean(0) - pl.mean(0))
        paint = cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2BGR) * 255.0
        print(f"[portrait] colour shift L {tl.mean(0)[0] - pl.mean(0)[0]:+.1f} a {tl.mean(0)[1] - pl.mean(0)[1]:+.1f} "
              f"b {tl.mean(0)[2] - pl.mean(0)[2]:+.1f}", flush=True)
    out = tex.astype(np.float32) * (1 - alpha[..., None]) + paint * alpha[..., None]
    cv2.imwrite(job["out"], np.clip(out + 0.5, 0, 255).astype(np.uint8))
    print(f"[portrait] painted {100 * (alpha > 0.5).mean():.1f}% of the head texture", flush=True)


if __name__ == "__main__":
    main()
