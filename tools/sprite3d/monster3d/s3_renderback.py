"""Stage 3: render-back sheet. The textured mesh through each fitted sprite camera, beside the classic frame and its 4x upscale
(what the sprite card shows).

  venv python s3_renderback.py <out.png> "<label>=<bake dir>|<cams.json>[|<albedo.png>[|<axe.npz>]]" [...] [--scale 4|1] [--views dir]

Rows: classic (nearest), upscaled sprite, then one row per mesh; columns: the 8 directions clockwise from the front.
--scale 1 gives the sheet at classic sprite size (every row reduced to the 1x frame size, shown 3x nearest so it can be read).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import common

sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import cam_fit  # noqa: E402
import render_soft  # noqa: E402

BG = (40, 40, 48)


def over(rgba, bg=BG):
    a = rgba[..., 3:].astype(np.float32) / 255
    return (rgba[..., :3] * a + np.array(bg, np.float32) * (1 - a)).astype(np.uint8)


def through(cam, pos, tris, uv, tex, extra=(), rough=None):
    """The mesh (and extra (pos, tris, uv) pieces) through one cam_fit camera: RGBA of the sprite's size."""
    S = max(cam["w"], cam["h"]) + 64
    r, u, _ = cam_fit.basis(cam["az"], cam["el"])
    c = np.array([0, cam["yoff"], 0]) + (S / 2 - cam["tx"] - 32) / cam["s"] * r + (cam["ty"] + 32 - S / 2) / (cam["s"] * cam["ky"]) * u
    P, T, U = [pos], [tris], [uv]
    n = len(pos)
    for ep, et, eu in extra:
        P.append(ep), T.append(et + n), U.append(eu)
        n += len(ep)
    img = render_soft.render(np.vstack(P), np.vstack(T), cam["az"], cam["el"], S, cam["s"], c, uv=np.vstack(U), tex=tex, ky=cam["ky"],
                             lit=rough is not None, rough=rough)
    return img[32:32 + cam["h"], 32:32 + cam["w"]]


def main():
    a = sys.argv[1:]
    scale = int(a[a.index("--scale") + 1]) if "--scale" in a else 4
    views = Path(a[a.index("--views") + 1]) if "--views" in a else common.STAGES / "1-frames" / "x4" / "nu00"
    specs = [x for x in a[1:] if "=" in x]
    rows, labels = [], ["classic", "upscaled x4 (sprite card)"]
    ring = common.CLOCKWISE_8
    classic = [np.asarray(Image.open(common.STAGES / "1-frames" / "classic" / "nu" / ("d%d_f00.png" % d)).convert("RGBA")) for d in ring]
    big = [np.asarray(Image.open(views / ("nu_d%d.png" % d)).convert("RGBA")) for d in ring]
    h4, w4 = big[0].shape[:2]
    rows.append([np.asarray(Image.fromarray(c).resize((w4, h4), Image.NEAREST)) for c in classic])
    rows.append(big)
    for spec in specs:
        label, rest = spec.split("=", 1)
        parts = rest.split("|")
        bake, cams = Path(parts[0]), json.load(open(parts[1]))["cams"]
        d = np.load(bake / "mesh_uv.npz")
        tex = np.asarray(Image.open(parts[2] if len(parts) > 2 and parts[2] else bake / "albedo.png").convert("RGB")).astype(np.float32)
        extra, rough = [], None
        if len(parts) > 4:      # "lit:<roughness off the part>:<on the part>": a lit preview with the bake's part.png as gloss mask
            _, r0, r1 = parts[4].split(":")
            pm = np.asarray(Image.open(bake / "part.png").convert("L")) > 127
            rough = np.where(pm, float(r1), float(r0)).astype(np.float32)
        if len(parts) > 3 and parts[3]:
            e = np.load(parts[3])
            extra = [(e["pos"], e["tris"], e["uv"])]
        rows.append([through(cams[str(v)], d["pos"], d["tris"], d["uv"], tex, extra, rough) for v in ring])
        labels.append(label + "  (IoU " + " ".join("%.2f" % cams[str(v)]["iou"] for v in ring) + ")")
    tiles = []
    for row in rows:
        out = []
        for t in row:
            if scale == 1:
                small = Image.fromarray(t).resize((w4 // 4, h4 // 4), Image.LANCZOS)
                t = np.asarray(small.resize((w4 // 4 * 3, h4 // 4 * 3), Image.NEAREST))
            out.append(over(t))
        tiles.append(np.hstack(out))
    pad = 22
    sheet = Image.new("RGB", (tiles[0].shape[1], sum(t.shape[0] + pad for t in tiles)), BG)
    dr, y = ImageDraw.Draw(sheet), 0
    for t, lab in zip(tiles, labels):
        dr.text((6, y + 4), lab, fill=(230, 230, 230))
        sheet.paste(Image.fromarray(t), (0, y + pad))
        y += t.shape[0] + pad
    sheet.save(a[0])
    print(a[0], sheet.size)


if __name__ == "__main__":
    main()
