"""Contact sheets of clip A for looking at it: every 6th frame, and crops that follow the earbud (every frame)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from earbud import Earbud   # noqa: E402
from tumble import project  # noqa: E402


def basis(a):
    return np.array(a[3:12]).reshape(3, 3).T


def main(frames_dir, out_prefix, track_path=os.path.join(HERE, "clipA_track.json")):
    tr = json.load(open(track_path))
    idx = list(range(0, 96, 6)) + [95]
    w, h = 480, 270
    sheet = Image.new("RGB", (w * 4, h * 5), "black")
    for k, i in enumerate(idx[:20]):
        im = Image.open(os.path.join(frames_dir, "f%03d.png" % i)).resize((w, h), Image.LANCZOS)
        ImageDraw.Draw(im).text((6, 4), "f%02d %.2fs" % (i, i / 24), fill=(255, 255, 0))
        sheet.paste(im, ((k % 4) * w, (k // 4) * h))
    sheet.save(out_prefix + "_sheet.png")
    bud = Earbud()
    cw, ch, cols = 200, 140, 12
    frames = list(range(0, 96))
    crops = Image.new("RGB", (cw * cols, ch * ((len(frames) + cols - 1) // cols)), "black")
    for k, f in enumerate(frames):
        s = tr["samples"][f * tr["sub"]]
        pos = np.array(s["cam"][:3])
        com = np.array(s["bud"][:3]) + basis(s["bud"]) @ bud.com
        x, y, _ = project(com, pos, basis(s["cam"]), s["fov"])
        im = Image.open(os.path.join(frames_dir, "f%03d.png" % f))
        crop = im.crop((int(x - cw / 2), int(y - ch / 2), int(x + cw / 2), int(y + ch / 2)))
        ImageDraw.Draw(crop).text((4, 2), "f%02d" % f, fill=(255, 255, 0))
        crops.paste(crop, ((k % cols) * cw, (k // cols) * ch))
    crops.save(out_prefix + "_crops.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
