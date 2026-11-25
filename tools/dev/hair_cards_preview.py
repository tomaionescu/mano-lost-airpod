"""Regrow a scanned character's hair cards (tools/blender/hair_scan_cards.py) in plain python3.11, without Blender or
the Godot lock, and look at the geometry: stats plus a quick software render (orthographic, alpha-tested cards,
one key light). For tuning the cards' geometry only: the shading is nothing like the game's.

usage: python3.11 tools/dev/hair_cards_preview.py <cast id> [stem=<glb stem>] [out=<dir>] [views=front,34,side,back,top]
                                                   [res=640] [seed=1] [set=key:json ...]
Inputs: tools/out/scan_<id>/hair_guide.npz (written by every build with "hair": "scan_cards") or, without one, the
shipped assets/characters/<stem>.glb (its body, head texture and hair shell; the face frame is then estimated from
the eye meshes instead of the face landmarks, so it is a little off). set=curl:null style=... overrides the style.
"""
import json, math, os, sys, time
import numpy as np
import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "blender"))
import hair_scan_cards as H
import hair_atlas
import cast

STEMS = {"toma": "toma_fit1", "mano": "mano_street"}
OUTFITS = {"toma": "fit1", "mano": "street"}


# ------------------------------------------------------------------ inputs from a shipped .glb
def guide_from_glb(stem):
    import proto_hair_A_glb as GL
    g = GL.GLB(os.path.join(ROOT, "assets", "characters", stem + ".glb"))
    mats = [m["name"] for m in g.J["materials"]]
    body = g.mesh("_body")
    shell = g.mesh("hairshell") or g.mesh("hairunder")
    eyes = g.mesh("_eye_")
    J, _ = g.joints()

    def tex(mi, size=1024):
        ti = g.J["materials"][mi]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
        im = GL.decode_png(g.image_bytes(g.texture_image(ti)))
        im = cv2.resize(im, (size, size), interpolation=cv2.INTER_AREA)
        return np.flipud(im).copy()                       # Blender orientation: row 0 = v 0

    def buv(uv):
        return np.stack([uv[:, 0], 1.0 - uv[:, 1]], 1)   # glTF -> Blender UVs

    head_mi = next(i for i, m in enumerate(mats) if m.endswith("_skin_head"))
    cloth_mi = next((i for i, m in enumerate(mats) if "cloth_scan" in m), -1)
    T = body["T"]
    G = dict(body_V=body["P"], body_T=T, body_UV=buv(body["UV"])[T], body_head=body["mat"] == head_mi,
             body_cloth=body["mat"] == cloth_mi, body_vid=np.arange(len(body["P"])))
    G["head_tex"] = tex(head_mi)
    G["body_tex"] = tex(cloth_mi) if cloth_mi >= 0 else None
    G["shell_V"], G["shell_T"] = shell["P"], shell["T"]
    G["shell_UV"] = buv(shell["UV"])[shell["T"]]
    G["shell_tex"] = tex(shell["mat"][0])
    E = eyes["P"]
    G["eye_c"] = E.mean(0)
    G["eye_front"] = float(E[:, 1].min())
    G["brow_z"] = float(G["eye_c"][2] + 0.024)
    P = body["P"]
    hv = P[(np.abs(P[:, 2] - (G["eye_c"][2] - 0.012)) < 0.006) & (P[:, 1] > G["eye_front"] + 0.05) &
           (P[:, 1] < G["eye_front"] + 0.1)]
    ears = []
    for side in (1, -1):
        s = hv[(hv[:, 0] - G["eye_c"][0]) * side > 0]
        q = s[np.argmax((s[:, 0] - G["eye_c"][0]) * side)]
        ears.append(np.array([q[0] - side * 0.004, q[1] - 0.012, q[2]]))
    G["ears"] = np.array(ears)
    G["top"] = float(max(P[G["body_T"][G["body_head"]]][:, :, 2].max(), shell["P"][:, 2].max()))
    G["bones"] = {k: v for k, v in J.items()}
    gl = g.mesh("_glasses_")
    G["coll_V"] = gl["P"] if gl else np.zeros((0, 3))
    G["coll_T"] = gl["T"] if gl else np.zeros((0, 3), np.int64)
    return G


# ------------------------------------------------------------------ a small software renderer
def view_matrix(fr, view, long_hair):
    yaw, pitch, h = {"front": (0, 5, 0.34), "34": (40, 8, 0.34), "side": (90, 5, 0.34), "back": (165, 10, 0.36),
                     "top": (25, 55, 0.36), "crown": (200, 50, 0.36), "part": (0, 70, 0.16),
                     "close": (30, 10, 0.17)}[view]
    if long_hair and view not in ("top", "crown", "part", "close"):
        h *= 1.9
    yw, pt = math.radians(yaw), math.radians(pitch)
    # camera looks along -fwd; character faces -Y, so the front view looks along +Y
    fwd = np.array([-math.sin(yw) * math.cos(pt), math.cos(yw) * math.cos(pt), -math.sin(pt)])
    right = np.cross(fwd, np.array([0, 0, 1.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    c = fr["centre"] + np.array([0, 0, -0.02 - (0.16 if long_hair and view not in ("top", "crown", "part", "close")
                                                else 0.0)])
    if view in ("part", "close"):
        c = fr["centre"] + np.array([0, -0.03, 0.05 if view == "part" else 0.03])
    return c, right, up, fwd, h


class Raster:
    def __init__(self, res, c, right, up, fwd, h):
        self.res = res
        self.c, self.r, self.u, self.f, self.h = c, right, up, fwd, h
        self.z = np.full((res, res), np.inf)
        self.img = np.zeros((res, res, 3))
        self.img[:] = (0.11, 0.12, 0.14)
        self.L = H.unit(-fwd * 0.5 + right * 0.55 + up * 0.65)

    def project(self, P):
        d = P - self.c
        x = (d @ self.r) / self.h * self.res + self.res / 2
        y = self.res / 2 - (d @ self.u) / self.h * self.res
        return np.stack([x, y], 1), d @ self.f

    def draw(self, P, T, shade, alpha=None, UV=None, tex=None, N=None, two_sided=True):
        """shade(tri, bary (k,3), uv (k,2) or None) -> rgb (k,3); alpha test against tex alpha x alpha."""
        xy, z = self.project(P)
        R = self.res
        for t in range(len(T)):
            a, b, c = T[t]
            p = xy[[a, b, c]]
            x0, y0 = np.floor(p.min(0)).astype(int)
            x1, y1 = np.ceil(p.max(0)).astype(int)
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, R - 1), min(y1, R - 1)
            if x1 < x0 or y1 < y0:
                continue
            den = (p[1, 1] - p[2, 1]) * (p[0, 0] - p[2, 0]) + (p[2, 0] - p[1, 0]) * (p[0, 1] - p[2, 1])
            if abs(den) < 1e-9:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            l0 = ((p[1, 1] - p[2, 1]) * (xs - p[2, 0]) + (p[2, 0] - p[1, 0]) * (ys - p[2, 1])) / den
            l1 = ((p[2, 1] - p[0, 1]) * (xs - p[2, 0]) + (p[0, 0] - p[2, 0]) * (ys - p[2, 1])) / den
            l2 = 1 - l0 - l1
            m = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
            if not m.any():
                continue
            bc = np.stack([l0[m], l1[m], l2[m]], 1)
            zz = bc @ z[[a, b, c]]
            iy, ix = (ys[m] - 0.5).astype(int), (xs[m] - 0.5).astype(int)
            ok = zz < self.z[iy, ix]
            if not ok.any():
                continue
            bc, zz, iy, ix = bc[ok], zz[ok], iy[ok], ix[ok]
            uv = bc @ UV[[a, b, c]] if UV is not None else None
            if tex is not None:
                tx = H.sample_img(tex, uv)
                al = tx[:, 3] if tex.shape[2] > 3 else np.ones(len(tx))
                if alpha is not None:
                    al = al * (bc @ alpha[[a, b, c]])
                keep = al >= 0.5
                if not keep.any():
                    continue
                bc, zz, iy, ix, uv, tx = bc[keep], zz[keep], iy[keep], ix[keep], uv[keep], tx[keep]
            else:
                tx = None
            n = H.unit(bc @ N[[a, b, c]]) if N is not None else None
            col = shade(t, bc, tx, n)
            self.z[iy, ix] = zz
            self.img[iy, ix] = col

    def lit(self, n, two=True):
        d = n @ self.L
        if two:
            d = np.abs(d) * 0.85
        return 0.32 + 0.68 * np.clip(d, 0, 1)


def render(G, R, st, view, res, path, atlas):
    fr = R["frame"]
    c, right, up, fwd, h = view_matrix(fr, view, st["long"])
    rs = Raster(res, c, right, up, fwd, h)
    # the body near the head (flat skin), the cap, the underlayer, the cards
    Vb, Tb = G["body_V"], G["body_T"]
    near = (Vb[Tb][:, :, 2].min(1) > fr["eye"][2] - (0.55 if st["long"] else 0.3))
    Tn = Tb[near]
    Nb = H.vertex_normals(Vb, Tb)
    skin = np.array([0.62, 0.42, 0.33]) ** 1.0
    cloth = np.array([0.35, 0.33, 0.32])
    clothf = G["body_cloth"][near]
    rs.draw(Vb, Tn, lambda t, bc, tx, n: (cloth if clothf[t] else skin)[None] * rs.lit(n, False)[:, None], N=Nb)
    K = R["cap"]
    KT = np.asarray(K["T"], np.int64)
    # per corner (the head's UVs are per corner)
    Vk, Tk = K["V"][KT].reshape(-1, 3), np.arange(KT.size).reshape(-1, 3)
    Nk = H.vertex_normals(K["V"], KT)[KT].reshape(-1, 3)
    rs.draw(Vk, Tk, lambda t, bc, tx, n: hair_atlas.srgb_to_lin(tx[:, :3]) * rs.lit(n, False)[:, None],
            alpha=K["alpha"][KT].reshape(-1), UV=K["UV"].reshape(-1, 2), tex=K["img"], N=Nk)
    U = R["under"]
    Vs = U["V"]
    Ts = np.asarray(G["shell_T"])[U["keep"]]
    ucol = np.array(st["under"])
    rs.draw(Vs, Ts, lambda t, bc, tx, n: ucol[None] * rs.lit(n)[:, None] * 1.0, N=H.vertex_normals(Vs, Ts))
    C = R["cards"]
    F = C["F"]
    T = np.concatenate([F[:, [0, 1, 2]], F[:, [0, 2, 3]]])
    atlas_b = np.flipud(atlas)          # Blender orientation, as the cards' (Blender) UVs
    rs.draw(C["V"], T, lambda t, bc, tx, n: hair_atlas.srgb_to_lin(tx[:, :3]) * (bc @ C["COL"][T[t], :3])
            * rs.lit(n)[:, None], alpha=C["COL"][:, 3], UV=C["UV"], tex=atlas_b, N=C["NRM"])
    out = hair_atlas.lin_to_srgb(np.clip(rs.img * 1.6, 0, 1))
    cv2.imwrite(path, (out[..., ::-1] * 255 + 0.5).astype(np.uint8))
    return path


def main():
    args = sys.argv[1:]
    cid = args[0]
    opts = dict(a.split("=", 1) for a in args[1:] if "=" in a and not a.startswith("set="))
    sets = [a[4:] for a in args[1:] if a.startswith("set=")]
    stem = opts.get("stem", STEMS.get(cid, cid))
    outfit = OUTFITS.get(cid, "default")
    npz = os.path.join(ROOT, "tools", "out", f"scan_{cid}", "hair_guide.npz")
    t0 = time.time()
    if os.path.exists(npz) and opts.get("src") != "glb":
        G = H.load_guide(npz)
        print("[preview] guide", os.path.relpath(npz, ROOT))
    else:
        G = guide_from_glb(stem)
        print("[preview] guide from", stem + ".glb (frame estimated from the eyes)")
    spec = cast.CAST[cid]
    st = H.style_for(spec, outfit)
    for s in sets:
        k, v = s.split(":", 1)
        st[k] = json.loads(v)
    R = H.generate(G, st, seed=int(opts.get("seed", spec.get("hair_seed", 1))))
    out = opts.get("out", os.path.join(ROOT, "tools", "out", "review", "hair_cards"))
    os.makedirs(out, exist_ok=True)
    atlas = hair_atlas.tinted(st["atlas"], st["root"], st["tip"])
    res = int(opts.get("res", 640))
    for v in opts.get("views", "front,34,side,back,top").split(","):
        p = render(G, R, st, v, res, os.path.join(out, f"{cid}_{v}.png"), atlas)
        print("[preview]", os.path.relpath(p, ROOT))
    print(f"[preview] done in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
