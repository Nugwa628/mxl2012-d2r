"""Decode a Median DCC into PNG frames (all directions) for the sprite -> 3D prototype (lane wereowl-3d).

    py -I tools/sprite3d/dcc_frames.py <dcc> <out dir> [--root <repo with extract/>] [--frame N ...] [--sheet]

Writes <out>/d<dir>_f<frame>.png (RGBA on the direction's canvas; palette = D2R units pal.dat). With --sheet also writes a
contact sheet of one frame in every direction. Direction numbering is the DCC's own (0..N-1).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import dcc  # noqa: E402

DEFAULT_ROOT = Path.home() / "mxl2012-d2r"


def palette(root: Path):
    d = (root / "extract" / "d2r" / "93847" / "data" / "global" / "palette" / "units" / "pal.dat").read_bytes()
    return [(d[i * 3 + 2], d[i * 3 + 1], d[i * 3]) for i in range(256)]  # stored BGR


def render(path: Path, pal):
    """{direction: [RGBA Image per frame]} on each direction's canvas."""
    lut = np.zeros((256, 4), np.uint8)
    for i, (r, g, b) in enumerate(pal):
        lut[i] = (r, g, b, 255)
    lut[0] = 0
    out = {}
    for d, (x0, y0, dw, dh, frames) in enumerate(dcc.decode(path.read_bytes())):
        ims = []
        for fx, fy, fw, fh, pix in frames:
            canvas = np.zeros((dh, dw, 4), np.uint8)
            canvas[fy - y0:fy - y0 + fh, fx - x0:fx - x0 + fw] = lut[np.frombuffer(pix, np.uint8).reshape(fh, fw)]
            ims.append(Image.fromarray(canvas, "RGBA"))
        out[d] = ims
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dcc")
    ap.add_argument("out")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--frame", type=int, nargs="*", help="only these frame indices (default all)")
    ap.add_argument("--sheet", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    dirs = render(Path(a.dcc), palette(Path(a.root)))
    for d, ims in dirs.items():
        for i, im in enumerate(ims):
            if a.frame is None or i in a.frame:
                im.save(out / f"d{d}_f{i}.png")
    print(f"{len(dirs)} directions, {len(dirs[0])} frames, canvas {dirs[0][0].size}")
    if a.sheet:
        f = (a.frame or [0])[0]
        w, h = max(im[f].size[0] for im in dirs.values()), max(im[f].size[1] for im in dirs.values())
        sheet = Image.new("RGBA", (w * len(dirs), h), (40, 40, 40, 255))
        for d, ims in dirs.items():
            sheet.alpha_composite(ims[f], (d * w, 0))
        sheet.save(out / f"sheet_f{f}.png")


if __name__ == "__main__":
    main()
