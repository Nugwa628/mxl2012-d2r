"""Owner sheet from the viewer (round 12): classic against one or more 3D stages, every mode x the 8 facings, no game run.

  python g7_viewersheet.py <classic frames dir> <out png> --stage <label>=<overlay dir> [--stage ...]
        --unit <logical unit json> --root base=<donor data> [--root ...] [--rig <rig>]
        [--modes nu:0,wl:5,a1:7,a2:5,gh:4,dt:6,dd:0] [--title "..."] [--work <dir>] [--py <python>]

For each mode:frame pair the sheet has one block: a row of classic's frame (s1_frames.py classic output, 8 facing keys
clockwise from the screen's bottom: file directions common.CLOCKWISE_8) and one row per stage rendered by
`python -m hdkit.view sheet` at the same time in the mode (frame / fps, fps = 25 x COF speed / 256 from frames.json).

Scale: hdkit.view's --scale 1 is a 1600x900 capture; legacy graphics fill 900 rows from 600, so classic pixels are drawn
x1.5 per viewer scale unit (x3 at --scale 2). Each cell puts the unit's ground point (classic: the mode box origin) at
the same pixel, so sizes and positions compare directly.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import common

sys.path.insert(0, str(common.WT / "tools"))
from hdkit.view import sheets  # noqa: E402

SCALE = 2.0
CELL = {"default": (300, 300, 150, 265), "dt": (380, 340, 190, 260), "dd": (400, 300, 200, 170)}


def opt(a, name, default=None):
    return a[a.index(name) + 1] if name in a else default


def opts(a, name):
    return [a[i + 1] for i, x in enumerate(a) if x == name]


def classic_cell(frames: Path, meta, mode, f, d, cell):
    w, h, ox, oy = cell
    im = Image.open(frames / mode / ("d%d_f%02d.png" % (d, f))).convert("RGBA")
    k = 1.5 * SCALE
    im = im.resize((round(im.width * k), round(im.height * k)), Image.NEAREST)
    bx, by = meta[mode]["box"][:2]
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(im, (round(ox + bx * k), round(oy + by * k)), im)
    return np.asarray(out)


def main(a):
    frames, out = Path(a[0]), Path(a[1])
    meta = json.loads((frames / "frames.json").read_text())
    stages = [s.split("=", 1) for s in opts(a, "--stage")]
    roots = opts(a, "--root")
    unit, rig = opt(a, "--unit"), opt(a, "--rig", "game")
    py = opt(a, "--py", sys.executable)
    work = Path(opt(a, "--work", str(out.parent / (out.stem + "_work"))))
    work.mkdir(parents=True, exist_ok=True)
    picks = [p.split(":") for p in opt(a, "--modes", "nu:0,wl:5,a1:7,a2:5,gh:4,dt:6,dd:0").split(",")]
    blocks = []
    for mode, f in picks:
        f = int(f)
        cell = CELL.get(mode, CELL["default"])
        fps = 25.0 * meta[mode]["speed"] / 256
        t = f / fps
        rows, names = [], []
        rows.append([classic_cell(frames, meta, mode, f, d, cell) for d in common.CLOCKWISE_8])
        names.append("classic")
        for label, overlay in stages:
            name = "%s_%s" % (label, mode)
            cmd = [py, "-m", "hdkit.view", "render", unit, "--root", "build=" + overlay]
            for r in roots:
                cmd += ["--root", r]
            cmd += ["--mode", mode, "--time", "%.4f" % t, "--facings", "8", "--rig", rig, "--scale", str(SCALE),
                    "--size", "%dx%d" % cell[:2], "--origin", "%d,%d" % cell[2:], "--out", str(work), "--name", name]
            subprocess.run(cmd, check=True, cwd=str(common.WT / "tools"), stdout=subprocess.DEVNULL)
            rows.append([np.asarray(Image.open(work / ("%s_k%d.png" % (name, k))).convert("RGBA")) for k in range(8)])
            names.append(label)
        g = sheets.grid([c for r in rows for c in r], 8, row_labels=names,
                        col_labels=["k%d" % k for k in range(8)],
                        title="%s  frame %d of %d  (t %.2f s)" % (mode.upper(), f, meta[mode]["frames"], t))
        blocks.append(g)
        print(mode, f, "t=%.3f" % t, flush=True)
    W = max(b.width for b in blocks)
    title = opt(a, "--title", "")
    th = 30 if title else 0
    sheet = Image.new("RGB", (W, th + sum(b.height for b in blocks)), sheets.BG)
    if title:
        ImageDraw.Draw(sheet).text((8, 8), title, fill=(235, 220, 170), font=sheets.font(16))
    y = th
    for b in blocks:
        sheet.paste(b, (0, y))
        y += b.height
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main(sys.argv[1:])
