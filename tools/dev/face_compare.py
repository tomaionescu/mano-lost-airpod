"""One sheet per character set: the portrait next to the in-engine viewer shots (scripts/dev/char_viewer.gd).
usage: python3.11 tools/dev/face_compare.py <shots dir under shots/> <out.png> <id>=<glb stem> [...]
e.g.   python3.11 tools/dev/face_compare.py mouthfix tools/out/review/faces.png toma=toma_fit1 ian=ian"""
import os, sys
import cv2, numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
shots, out = sys.argv[1], sys.argv[2]
H = 420


def fit(img, h=H):
    return cv2.resize(img, (int(img.shape[1] * h / img.shape[0]), h), interpolation=cv2.INTER_AREA)


rows = []
for arg in sys.argv[3:]:
    cid, stem = arg.split("=")
    tiles = []
    p = os.path.join(ROOT, "tools", "scans", cid, "portrait.png")
    if os.path.exists(p):
        tiles.append(fit(cv2.imread(p)))
    for shot in ("face", "face34", "face_mouth"):
        f = os.path.join(ROOT, "shots", shots, f"char_{stem}_{shot}.png")
        if os.path.exists(f):
            img = cv2.imread(f)
            if shot == "face":
                # the viewer's face shot is wide: keep the middle
                w = img.shape[1]
                img = img[:, int(w * 0.18):int(w * 0.82)]
            tiles.append(fit(img))
    row = np.hstack(tiles)
    cv2.putText(row, cid, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    rows.append(row)
w = max(r.shape[1] for r in rows)
rows = [np.hstack([r, np.zeros((r.shape[0], w - r.shape[1], 3), np.uint8)]) for r in rows]
sheet = np.vstack(rows)
cv2.imwrite(out, sheet)
print("sheet", out, sheet.shape)
