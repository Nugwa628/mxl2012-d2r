"""Stage 6: contact sheet of one game run: every moncard shot cropped round the character.

  python g6_contact.py <shots dir> <out.png> [x0,y0,x1,y1] [zoom]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

src, out = Path(sys.argv[1]), sys.argv[2]
box = tuple(int(v) for v in sys.argv[3].split(",")) if len(sys.argv) > 3 else (620, 180, 1060, 500)
zoom = float(sys.argv[4]) if len(sys.argv) > 4 else 1.5
order = ["spot", "near", "fight", "burst0", "burst1", "burst2", "burst3", "death"]
rows = {}
for p in sorted(src.glob("moncard_*.png")):
    stem = p.stem
    what = stem.rsplit("_", 1)[1]
    rows.setdefault(stem.rsplit("_", 1)[0], {})[what] = p
font = ImageFont.load_default(size=18)
w, h = int((box[2] - box[0]) * zoom), int((box[3] - box[1]) * zoom)
cols = [c for c in order if any(c in r for r in rows.values())]
sheet = Image.new("RGB", (w * len(cols), (h + 26) * len(rows)), (16, 16, 16))
d = ImageDraw.Draw(sheet)
for j, (name, r) in enumerate(rows.items()):
    for i, c in enumerate(cols):
        if c in r:
            im = Image.open(r[c]).convert("RGB").crop(box).resize((w, h), Image.LANCZOS)
            sheet.paste(im, (i * w, j * (h + 26) + 26))
        d.text((i * w + 6, j * (h + 26) + 3), "%s %s" % (name.replace("moncard_", ""), c), fill=(255, 255, 255), font=font)
sheet.save(out)
print(out, sheet.size)
