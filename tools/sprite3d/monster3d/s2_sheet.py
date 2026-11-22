"""Stage 2: the shape sheet: the classic sprites, the 4x sprites and each scored shape in the 8 directions.

  venv python s2_sheet.py [--token T] <out.png> <name>[=<label>] [...] [--views <dir>] [--note "<line>"]

Names are entries of stages/2-shape/score (s2_score.py). A shape is drawn grey through its fitted cameras, with the outline
of the sprite of that direction in orange on top: where the grey leaves the outline or the outline holds no grey, the shape
is wrong. Each row's label carries the mean IoU and the IoU per direction (d4 d0 d5 d1 d6 d2 d7 d3, clockwise from front).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import common

sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import cam_fit  # noqa: E402
import render_soft  # noqa: E402

BG = (40, 40, 48)


def over(rgba):
    a = rgba[..., 3:].astype(np.float32) / 255
    return (rgba[..., :3] * a + np.array(BG, np.float32) * (1 - a)).astype(np.uint8)


def through(cam, pos, tris):
    S = max(cam["w"], cam["h"]) + 64
    r, u, _ = cam_fit.basis(cam["az"], cam["el"])
    c = np.array([0, cam["yoff"], 0]) + (S / 2 - cam["tx"] - 32) / cam["s"] * r + (cam["ty"] + 32 - S / 2) / (cam["s"] * cam["ky"]) * u
    img = render_soft.render(pos, tris, cam["az"], cam["el"], S, cam["s"], c, ky=cam["ky"])
    return img[32:32 + cam["h"], 32:32 + cam["w"]]


def main():
    a = sys.argv[1:]
    views = Path(a[a.index("--views") + 1]) if "--views" in a else common.STAGES / "1-frames" / "x4" / "nu00"
    note = a[a.index("--note") + 1] if "--note" in a else ""
    skip = {a.index(k) + 1 for k in ("--views", "--note") if k in a}
    names = [x for i, x in enumerate(a[1:], 1) if i not in skip and not x.startswith("--")]
    score = common.STAGES / "2-shape" / "score"
    book = json.loads((score / "scores.json").read_text())
    ring = common.CLOCKWISE_8
    classic = [np.asarray(Image.open(common.STAGES / "1-frames" / "classic" / "nu" / ("d%d_f00.png" % d)).convert("RGBA")) for d in ring]
    big = [np.asarray(Image.open(views / ("nu_d%d.png" % d)).convert("RGBA")) for d in ring]
    h4, w4 = big[0].shape[:2]
    edges = []
    for b in big:
        m = b[..., 3] > 100
        edges.append(ndimage.binary_dilation(m, iterations=2) & ~ndimage.binary_erosion(m, iterations=1))
    rows = [[over(np.asarray(Image.fromarray(c).resize((w4, h4), Image.NEAREST))) for c in classic], [over(b) for b in big]]
    labels = ["classic   (directions d4 d0 d5 d1 d6 d2 d7 d3: front, then clockwise)", "4x sprite (the sprite card's picture)"]
    for spec in names:
        name, label = spec.split("=", 1) if "=" in spec else (spec, spec)
        d = np.load(score / name / "body.npz")
        cams = json.loads((score / name / "cams.json").read_text())["cams"]
        row = []
        for v, e in zip(ring, edges):
            t = over(through(cams[str(v)], d["pos"], d["tris"])).copy()
            t[e] = (255, 150, 40)
            row.append(t)
        rows.append(row)
        s = book[name]
        labels.append("%s: %d triangles, mean IoU %.3f  (%s)" % (label, len(d["tris"]), s["mean"], " ".join("%.2f" % x for x in s["per"])))
    pad = 22
    tiles = [np.hstack(r) for r in rows]
    top = 22 if note else 0
    sheet = Image.new("RGB", (tiles[0].shape[1], top + sum(t.shape[0] + pad for t in tiles)), BG)
    dr, y = ImageDraw.Draw(sheet), top
    if note:
        dr.text((6, 4), note, fill=(255, 220, 140))
    for t, lab in zip(tiles, labels):
        dr.text((6, y + 4), lab, fill=(230, 230, 230))
        sheet.paste(Image.fromarray(t), (0, y + pad))
        y += t.shape[0] + pad
    sheet.save(a[0])
    print(a[0], sheet.size)


if __name__ == "__main__":
    main()
