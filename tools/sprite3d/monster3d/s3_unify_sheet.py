"""Close-up sheet of texture options on the same model: the classic sprite, its x4 card, then one column per albedo.

  venv python s3_unify_sheet.py <out.png> <bake dir> <cams.json> "<label>=<albedo.png>" [...] [--zoom 4] [--rows d4cap,d4body,...]

Rows (crop of one camera view, zoom times the x4 sprite size, lit by the mesh normals like s3_detail.py's sheet):
  d<N>cap / d<N>body / d<N>full: the fitted camera of sprite direction N (the classic and x4 columns show that frame);
  m<N>full: the camera of direction N turned by 22.5 degrees, between two sprite views (no classic frame exists there: the
  classic columns show direction N for reference, marked "nearest sprite").
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import common
import s3_detail

BG = np.array([40, 40, 48], np.float32)


def over(t):
    al = t[..., 3:].astype(np.float32) / 255
    return (t[..., :3] * al + BG * (1 - al)).astype(np.uint8)


BOXES = {"cap": (0.08, 0.10, 0.92, 0.42), "body": (0.25, 0.42, 0.75, 0.80), "full": (0.0, 0.0, 1.0, 1.0)}


def main():
    a = sys.argv[1:]
    out, bake, cams = Path(a[0]), Path(a[1]), json.load(open(a[2]))["cams"]
    zoom = int(a[a.index("--zoom") + 1]) if "--zoom" in a else 4
    rows = (a[a.index("--rows") + 1] if "--rows" in a else "d4cap,d4body,d0cap,d0body,m4full,d6full").split(",")
    specs = [x for x in a[3:] if "=" in x and not x.startswith("--")]
    d = np.load(bake / "mesh_uv.npz")
    texs = [(s.split("=", 1)[0], np.asarray(Image.open(s.split("=", 1)[1]).convert("RGB")).astype(np.float32)) for s in specs]
    xv = common.STAGES / "1-frames" / "x4" / "nu00"
    cells = []
    for rname in rows:
        kind, v, box = rname[0], int(rname[1]), rname[2:]
        cam = dict(cams[str(v)])
        if kind == "m":
            cam["az"] = cam["az"] + 22.5
        cl = np.asarray(Image.open(common.STAGES / "1-frames" / "classic" / "nu" / ("d%d_f00.png" % v)).convert("RGBA"))
        up = np.asarray(Image.open(xv / ("nu_d%d.png" % v)).convert("RGBA"))
        sz = (up.shape[1] * zoom, up.shape[0] * zoom)
        row = [over(np.asarray(Image.fromarray(cl).resize(sz, Image.NEAREST))),
               over(np.asarray(Image.fromarray(up).resize(sz, Image.LANCZOS)))]
        for _, tex in texs:
            row.append(over(s3_detail.through(cam, d, tex, zoom)))
        H, W = row[0].shape[:2]
        bx = BOXES[box]
        crop = (int(W * bx[0]), int(H * bx[1]), int(W * bx[2]), int(H * bx[3]))
        name = ("between d%d and the next view (+22.5 deg); classic = nearest sprite" % v) if kind == "m" else "%s d%d" % (box, v)
        cells.append((name, [Image.fromarray(t).crop(crop) for t in row]))
        print("row", rname, flush=True)
    labels = ["classic (nearest)", "sprite x4 (card)"] + [t[0] for t in texs]
    cw, pad, top = 330, 6, 40
    font = ImageFont.load_default(size=20)
    tiles = [(n, [t.resize((cw, int(t.height * cw / t.width)), Image.LANCZOS) for t in r]) for n, r in cells]
    total_h = top + sum(max(t.height for t in r) + pad + 28 for _, r in tiles)
    S = Image.new("RGB", (len(labels) * (cw + pad) + pad, total_h), (24, 24, 28))
    dr = ImageDraw.Draw(S)
    for i, lab in enumerate(labels):
        dr.text((pad + i * (cw + pad), 8), lab, fill=(235, 235, 235), font=font)
    y = top
    for n, r in tiles:
        dr.text((pad, y), n, fill=(200, 200, 160), font=font)
        y += 26
        for i, t in enumerate(r):
            S.paste(t, (pad + i * (cw + pad), y))
        y += max(t.height for t in r) + pad + 2
    out.parent.mkdir(parents=True, exist_ok=True)
    S.save(out)
    print(out, S.size)


if __name__ == "__main__":
    main()
