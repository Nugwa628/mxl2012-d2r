#!/usr/bin/env python
"""A classic missile or overlay animation (DCC) as RGBA frames, facts and a contact sheet (lane hdtools-effects).

  py -3 tools/effect_sheet.py info  missiles/psiorb
  py -3 tools/effect_sheet.py sheet missiles/psiorb OUT.png [--scale 2] [--dirs 0,4] [--act 1]

Frames come back on one canvas per animation (the union of every direction's box), so a frame's position in the cell is
its position against the missile's anchor. `additive` art (missiles.txt `Trans` 1: the classic blend adds the picture to the
screen, black draws nothing) is shown on black; its HD alpha is made in tools/effect_flipbook.py.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dcc  # noqa: E402
import fxpaths  # noqa: E402


def art_path(name: str) -> Path:
    """`missiles/psiorb` or `overlays/x` -> Median's DCC, else the D2R baseline's (names are case-insensitive)."""
    kind, _, stem = name.replace("\\", "/").partition("/")
    for base in (fxpaths.MXL, fxpaths.D2R_DATA / "global"):
        folder = Path(base) / kind
        if not folder.is_dir():
            continue
        for q in folder.rglob("*.dcc"):
            if q.relative_to(folder).with_suffix("").as_posix().lower() == stem.lower():
                return q
    raise FileNotFoundError(name)


def act_palette(act: int = 1) -> np.ndarray:
    d = fxpaths.d2r_file("data/global/palette/act%d/pal.dat" % act).read_bytes()
    lut = np.zeros((256, 4), np.uint8)
    for i in range(256):
        lut[i] = (d[i * 3 + 2], d[i * 3 + 1], d[i * 3], 255)
    lut[0] = 0
    return lut


def load(name: str, act: int = 1) -> dict:
    """{'dirs': [[RGBA array per frame] per direction], 'box': (x0, y0, w, h), 'anchor': (ax, ay), 'bytes': n}.
    Every frame is drawn on the same canvas `box`; `anchor` is the missile's position in that canvas."""
    path = art_path(name)
    raw = path.read_bytes()
    dirs = dcc.decode(raw)
    lut = act_palette(act)
    x0 = min(d[0] for d in dirs)
    y0 = min(d[1] for d in dirs)
    x1 = max(d[0] + d[2] for d in dirs)
    y1 = max(d[1] + d[3] for d in dirs)
    out = []
    for _dx, _dy, _dw, _dh, frames in dirs:
        fr = []
        for fx, fy, fw, fh, pix in frames:
            canvas = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
            if fw and fh:
                canvas[fy - y0:fy - y0 + fh, fx - x0:fx - x0 + fw] = lut[np.frombuffer(pix, np.uint8).reshape(fh, fw)]
            fr.append(canvas)
        out.append(fr)
    return {"path": str(path), "bytes": len(raw), "dirs": out, "box": (x0, y0, x1 - x0, y1 - y0), "anchor": (-x0, -y0)}


def info(name: str, act: int = 1) -> dict:
    a = load(name, act)
    d0 = a["dirs"][0]
    same = all(len(d) == len(d0) and all(np.array_equal(x, y) for x, y in zip(d, d0)) for d in a["dirs"][1:])
    lit = np.concatenate([f[f[..., 3] > 0][:, :3] for d in a["dirs"] for f in d]) if d0 else np.zeros((0, 3))
    return {"file": a["path"], "bytes": a["bytes"], "directions": len(a["dirs"]), "frames_per_direction": len(d0),
            "box_x0_y0_w_h": a["box"], "anchor_in_box": a["anchor"], "directions_identical": same,
            "mean_rgb": [round(float(v), 1) for v in lit.mean(axis=0)] if len(lit) else None,
            "max_rgb": [int(v) for v in lit.max(axis=0)] if len(lit) else None,
            "drawn_pixels_per_frame": round(float(np.mean([(f[..., 3] > 0).sum() for d in a["dirs"] for f in d])), 1)}


def sheet(name: str, out: Path, scale: int = 2, dirs=None, act: int = 1, title: str = "") -> Path:
    a = load(name, act)
    _x, _y, w, h = a["box"]
    pick = list(range(len(a["dirs"]))) if dirs is None else dirs
    n = len(a["dirs"][0])
    cw, ch, left, top = w * scale + 4, h * scale + 4, 46, 34
    im = Image.new("RGB", (left + cw * n, top + ch * len(pick)), (0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.text((4, 2), title or f"{name}: {len(a['dirs'])} directions x {n} frames, box {w}x{h}, shown {scale}x nearest on "
            "black (classic adds it to the screen)", fill=(255, 255, 255))
    for f in range(n):
        dr.text((left + f * cw + 2, 20), str(f), fill=(160, 160, 160))
    for r, d in enumerate(pick):
        dr.text((4, top + r * ch + ch // 2 - 6), f"dir {d}", fill=(160, 160, 160))
        for f, fr in enumerate(a["dirs"][d]):
            cell = Image.fromarray(fr[..., :3] * (fr[..., 3:] > 0), "RGB").resize((w * scale, h * scale), Image.NEAREST)
            im.paste(cell, (left + f * cw + 2, top + r * ch + 2))
            ax, ay = a["anchor"]
            dr.point((left + f * cw + 2 + ax * scale, top + r * ch + 2 + ay * scale), fill=(255, 0, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("info", "sheet"))
    ap.add_argument("name", help="missiles/<CelFile> or overlays/<Filename>")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--dirs", help="comma-separated directions (default: all)")
    ap.add_argument("--act", type=int, default=1)
    args = ap.parse_args(argv)
    if args.cmd == "info":
        print(json.dumps(info(args.name, args.act), indent=1))
    else:
        dirs = [int(x) for x in args.dirs.split(",")] if args.dirs else None
        print(sheet(args.name, Path(args.out), args.scale, dirs, args.act))
    return 0


if __name__ == "__main__":
    sys.exit(main())
