"""Assemble in-game captures into showcase sheets (shots/showcase_*.png)."""
import sys, glob, os
from PIL import Image, ImageDraw, ImageFont

def sheet(files, out, cols=2, w=960):
    ims = []
    for f in files:
        if os.path.exists(f):
            im = Image.open(f).convert("RGB")
            ims.append(im.resize((w, int(w * im.height / im.width))))
    if not ims:
        return
    h = max(i.height for i in ims)
    rows = (len(ims) + cols - 1) // cols
    s = Image.new("RGB", (cols * w + (cols - 1) * 8, rows * h + (rows - 1) * 8), (12, 13, 16))
    for i, im in enumerate(ims):
        s.paste(im, ((i % cols) * (w + 8), (i // cols) * (h + 8)))
    s.save(out)
    print(out, s.size)

if __name__ == "__main__":
    S = "shots/"
    sheet([S + f for f in sys.argv[2:]], S + sys.argv[1])
