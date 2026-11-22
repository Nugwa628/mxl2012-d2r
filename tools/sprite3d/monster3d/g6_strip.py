"""Stage 6: the in-game sheet. Top: classic | HD today (stand-in) | sprite card | 3D model at the same Blood Moor spot (spawn
offset 8,-8), rows = the check's shots (0.5 s, 2.5 s, 5 s after the spawn, after the kill). Bottom: the four spawn sides (the
facings), sprite card against 3D model.

  python g6_strip.py <3D shots dir> <out.png>

The first three columns and the card rows of the bottom block are captures of lane hdtools-monster (prototype F): runs base2
(classic = legacy graphics, HD = the stand-in), upD (2x upscaled card) and flip2 (animated 1x cards, four sides). Same check,
same area, same character, same offsets; another game session.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import common

F = common.EV.parent / "monster" / "shots"
mine, out = Path(sys.argv[1]), sys.argv[2]
BOX, ZOOM = (640, 190, 1040, 470), 1.6
WIDE, WZOOM = (540, 150, 1060, 500), 640 / 520
font, small = ImageFont.load_default(size=24), ImageFont.load_default(size=18)


def cell(path, box, zoom):
    im = Image.open(path).convert("RGB").crop(box)
    return im.resize((round(im.width * zoom), round(im.height * zoom)), Image.LANCZOS)


cols = [("classic (legacy graphics; F, run base2)", F / "base2", "moncard_hardliner_legacy_%s.png"),
        ("HD today: stand-in (F, run base2)", F / "base2", "moncard_hardliner_hd_%s.png"),
        ("sprite card, 2x upscaled (F, run upD)", F / "upD", "moncard_hardliner_hd_%s.png"),
        ("3D model (this lane)", mine, "moncard_hardliner_hd_o0_%s.png")]
rows = [("0.5 s", "spot"), ("2.5 s", "near"), ("5 s: fight", "fight"), ("after the kill", "death")]
cw, ch = round((BOX[2] - BOX[0]) * ZOOM), round((BOX[3] - BOX[1]) * ZOOM)
ww, wh = round((WIDE[2] - WIDE[0]) * WZOOM), round((WIDE[3] - WIDE[1]) * WZOOM)
top, gap, left = 40, 6, 0
H1 = top + len(rows) * (ch + gap)
sheet = Image.new("RGB", (4 * cw + 3 * gap, H1 + 2 * (top + wh + gap) + 10), (16, 16, 16))
d = ImageDraw.Draw(sheet)
for i, (label, folder, pat) in enumerate(cols):
    x = i * (cw + gap)
    d.text((x + 8, 6), label, fill=(255, 255, 255), font=font)
    for j, (rl, what) in enumerate(rows):
        y = top + j * (ch + gap)
        sheet.paste(cell(folder / (pat % what), BOX, ZOOM), (x, y))
        if i == 0:
            d.text((x + 8, y + 6), rl, fill=(255, 255, 160), font=small)
sides = ["8,-8", "-8,8", "8,8", "-8,-8"]
for r, (label, folder) in enumerate((("sprite card, animated 1x (F, run flip2)", F / "flip2"), ("3D model (this lane)", mine))):
    y = H1 + r * (top + wh + gap)
    for i, side in enumerate(sides):
        x = i * (ww + gap)
        d.text((x + 8, y + 6), "%s: spawned at %s, 5 s" % (label, side), fill=(255, 255, 255), font=small)
        sheet.paste(cell(folder / ("moncard_hardliner_hd_o%d_fight.png" % i), WIDE, WZOOM), (x, y + top))
sheet.save(out)
print(out, sheet.size)
