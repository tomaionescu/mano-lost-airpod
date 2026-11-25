"""Square head-and-shoulders crop of a studio portrait for single-image 3D generators (Hunyuan3D v3, Tripo H3.1):
the whole head with all the hair, the ears, the neck and the top of the shoulders, centred on the head, a small
margin over the hair, on the portrait's own plain grey background. Writes <out>/<stem>_2048.png and _1024.png and
a JSON with the crop box.
usage: python3.11 tools/dev/head_inputs.py <portrait.png> <out dir> [stem] [--shoulders=<frac>] [--margin=<frac>]
  --shoulders  how far below the chin the crop reaches, in head heights (hair top to chin); default 0.25
  --margin     space above the highest hair, as a fraction of the crop; default 0.035
e.g.   python3.11 tools/dev/head_inputs.py tools/scans/toma/portrait.png tools/scans/toma/head_inputs toma_head"""
import json, os, sys
import cv2, numpy as np

args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
src, out = args[0], args[1]
stem = args[2] if len(args) > 2 else "head"
SHOULDERS = float(opts.get("shoulders", 0.25))
MARGIN = float(opts.get("margin", 0.035))

img = cv2.imread(src, cv2.IMREAD_COLOR)
H, W = img.shape[:2]
lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)

# the background: plain grey, a little lighter towards the bottom; model it per row from both edges
edge = np.concatenate([lab[:, :48], lab[:, -48:]], axis=1)          # rows x 96 x 3
bg_row = np.median(edge, axis=1)                                     # rows x 3
dist = np.linalg.norm(lab - bg_row[:, None, :], axis=2)
mask = (dist > 9).astype(np.uint8)
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

lm_path = src + ".lm.json"
if os.path.exists(lm_path):
    face = json.load(open(lm_path))["faces"][0]["pts"]
else:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "py"))
    from landmarks import detect
    face = detect(src)["faces"][0]["pts"]
face = np.array(face)
chin_y = float(face[152][1])
mouth_y = float(face[14][1])
nose_x = float(face[1][0])

# the head: the subject above the mouth (hair, ears; the shoulders start lower, beside the chin)
rows = np.nonzero(mask[: int(mouth_y)].any(1))[0]
top = int(rows.min())
cols = np.nonzero(mask[top: int(mouth_y)].any(0))[0]
left, right = int(cols.min()), int(cols.max())
head_h = chin_y - top
bottom = chin_y + SHOULDERS * head_h                                  # neck and the top of the shoulders
S = int(round((bottom - top) / (1.0 - MARGIN)))
S = min(S, H, W)
y0 = int(round(top - MARGIN * S))
cx = (left + right) / 2.0
x0 = int(round(cx - S / 2.0))
pad = (max(0, -x0), max(0, x0 + S - W), max(0, -y0), max(0, y0 + S - H))
if any(pad):
    # extend the background cleanly: replicate each row's own grey (no mirrored hair)
    img = cv2.copyMakeBorder(img, pad[2], pad[3], pad[0], pad[1], cv2.BORDER_REPLICATE)
    x0 += pad[0]
    y0 += pad[2]
crop = img[y0: y0 + S, x0: x0 + S]


def resample(im, size):
    if size <= im.shape[0]:
        return cv2.resize(im, (size, size), interpolation=cv2.INTER_AREA)
    # Lanczos up, then clamp each pixel to the 3x3 range of the source around it: no ringing halos at the
    # hair's edge against the grey, no sharpening, nothing invented
    up = cv2.resize(im, (size, size), interpolation=cv2.INTER_LANCZOS4)
    k = np.ones((3, 3), np.uint8)
    lo = cv2.resize(cv2.erode(im, k), (size, size), interpolation=cv2.INTER_NEAREST)
    hi = cv2.resize(cv2.dilate(im, k), (size, size), interpolation=cv2.INTER_NEAREST)
    return np.clip(up, lo, hi)


os.makedirs(out, exist_ok=True)
info = {"source": os.path.relpath(src, out), "source_size": [W, H], "crop_xywh": [x0 - pad[0], y0 - pad[2], S, S],
        "padded": list(pad), "head_bbox_xyxy": [left, top, right, int(chin_y)], "nose_x": round(nose_x, 1),
        "shoulders": SHOULDERS, "margin": MARGIN, "files": {}}
for size in (2048, 1024):
    res = resample(crop, size)
    path = os.path.join(out, f"{stem}_{size}.png")
    cv2.imwrite(path, res, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    info["files"][os.path.basename(path)] = {"size": size, "scale_from_source": round(size / S, 4)}
    print(f"{path}: {size} px, {size / S:.3f}x the portrait's pixels")
json.dump(info, open(os.path.join(out, f"{stem}_crop.json"), "w"), indent=1)
print(f"crop x {x0 - pad[0]}..{x0 - pad[0] + S}, y {y0 - pad[2]}..{y0 - pad[2] + S} ({S} px); head "
      f"x {left}..{right}, hair top {top}, chin {chin_y:.0f}; pad {pad}")
