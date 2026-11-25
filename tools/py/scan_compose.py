"""Finish the textures of a scanned character (tools/blender/scan_wrap.py): fill the texels where the bake's rays
missed the scan, match the kept hands' skin tone to the scanned face, and blend kept and baked parts.

usage: python3.11 scan_compose.py <job.json>
job: {"work": dir, "skin": template skin texture, "skin_normal": its normal map or null,
      "out_color": png, "out_normal": png, "out_rough": png}
Reads <work>/bake_{color,normal,rough,mask}.png. Bake alpha marks the texels a ray hit; the mask is
R = keep the template's skin (hands, ears; 0.75 for the mouth's inside: kept, but not sampled for the tone match),
G = inside the body's UV islands (1; down to 0.6 deep in the mouth: darker and wet there), B = 1 on the face (fitted
to the scan's landmarks), 0.5 elsewhere on the head. The head keeps its own shape, so it keeps its own normals too: there the
scan's normals would only record how its head differs from the body's (dark blobs at the nostrils).
"""
import json, sys
import numpy as np, cv2

Y = np.array([0.2126, 0.7152, 0.0722], np.float32)


def load(path):
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im is None:
        raise SystemExit(f"cannot read {path}")
    if im.ndim == 2:
        return im[..., None]
    return cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA if im.shape[2] == 4 else cv2.COLOR_BGR2RGB)


def save(path, rgb):
    out = np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)
    cv2.imwrite(path, cv2.cvtColor(out, cv2.COLOR_RGB2BGR))


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def push_pull(img, valid):
    """Fill invalid texels with the average of the valid ones around them, coarser the further they are."""
    w = valid.astype(np.float32)
    levels = [(img.astype(np.float32) * w[..., None], w)]
    while min(levels[-1][1].shape) > 1:
        a, b = levels[-1]
        size = (max(1, a.shape[1] // 2), max(1, a.shape[0] // 2))
        a2 = cv2.resize(a, size, interpolation=cv2.INTER_AREA).reshape(size[1], size[0], -1)
        levels.append((a2, cv2.resize(b, size, interpolation=cv2.INTER_AREA)))
    a, b = levels[-1]
    filled = a / np.maximum(b, 1e-6)[..., None]
    for a, b in reversed(levels[:-1]):
        up = cv2.resize(filled, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR).reshape(a.shape)
        f = np.clip(b, 0, 1)[..., None]
        filled = (a / np.maximum(b, 1e-6)[..., None]) * f + up * (1 - f)
    return filled


def main():
    job = json.load(open(sys.argv[1]))
    w, sfx = job["work"], job.get("suffix", "")
    col = load(f"{w}/bake_color{sfx}.png").astype(np.float32) / 255
    nrm = load(f"{w}/bake_normal{sfx}.png").astype(np.float32) / 255
    rough = load(f"{w}/bake_rough{sfx}.png").astype(np.float32) / 255
    mask = load(f"{w}/bake_mask{sfx}.png").astype(np.float32) / 255
    h, wd = col.shape[:2]
    covered = mask[..., 1] > 0.5
    keep = np.where(covered, smoothstep(0.3, 0.7, mask[..., 0]), 1.0)[..., None]
    face = covered & (mask[..., 2] > 0.75)
    head = np.where(covered, smoothstep(0.2, 0.45, mask[..., 2]), 0.0)[..., None]

    hit = col[..., 3] > 0.5
    print(f"[compose] rays missed {100 * (covered & ~hit & (keep[..., 0] < 0.5)).sum() / max(covered.sum(), 1):.1f}% "
          f"of the baked area", flush=True)
    col_f = push_pull(col[..., :3], hit)
    nrm_f = push_pull(nrm[..., :3], nrm[..., 3] > 0.5)
    rough_f = push_pull(rough[..., :1], rough[..., 3] > 0.5)[..., 0]

    skin = load(job["skin"]).astype(np.float32)[..., :3] / 255
    if skin.shape[:2] != (h, wd):
        skin = cv2.resize(skin, (wd, h), interpolation=cv2.INTER_AREA)
    # the kept hands take the scanned face's skin tone (median of mid-bright face texels, linear light)
    fl = srgb_to_lin(col[..., :3][face & hit].astype(np.float64))
    hands = covered & (mask[..., 0] > 0.8)
    hl = srgb_to_lin(skin[hands].astype(np.float64))
    if len(fl) > 1000 and len(hl) > 1000:
        fy, hy = (fl * Y).sum(1), (hl * Y).sum(1)
        fm = np.median(fl[(fy > np.percentile(fy, 35)) & (fy < np.percentile(fy, 80))], 0)
        hm = np.median(hl[(hy > np.percentile(hy, 35)) & (hy < np.percentile(hy, 80))], 0)
        gain = np.clip(fm / np.maximum(hm, 1e-4), 0.5, 2.0)
        print(f"[compose] hand skin gain {np.round(gain, 3).tolist()}", flush=True)
        skin = lin_to_srgb(srgb_to_lin(skin) * gain)
    out = keep * skin + (1 - keep) * col_f
    # the mouth's inside: dark with depth (no light reaches far into a mouth), wet
    cav = np.where(covered, np.clip((1.0 - mask[..., 1]) / 0.4, 0, 1), 0.0)[..., None]
    out = lin_to_srgb(srgb_to_lin(out) * (1.0 - 0.8 * cav))
    save(job["out_color"], out)

    if job.get("skin_normal"):
        sn = load(job["skin_normal"]).astype(np.float32)[..., :3] / 255
        if sn.shape[:2] != (h, wd):
            sn = cv2.resize(sn, (wd, h), interpolation=cv2.INTER_AREA)
    else:
        sn = np.broadcast_to(np.array([0.5, 0.5, 1.0], np.float32), (h, wd, 3))
    nk = np.maximum(keep, head)
    n = nk * sn + (1 - nk) * nrm_f
    v = n * 2 - 1
    v /= np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-6)
    save(job["out_normal"], v * 0.5 + 0.5)
    r = keep[..., 0] * 0.55 + (1 - keep[..., 0]) * np.clip(rough_f, 0.3, 1.0)
    r = r * (1 - cav[..., 0]) + 0.3 * cav[..., 0]
    save(job["out_rough"], np.repeat(r[..., None], 3, -1))
    print("[compose] done", flush=True)


if __name__ == "__main__":
    main()
