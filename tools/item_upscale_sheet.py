"""Comparison sheet of the upscaling methods (tools/upscale.py) on sample item pictures (docs/hd-icons.md).

  py -3 -I tools/item_upscale_sheet.py <out.png> [mxl/<inv> | classic/<inv> | d2r/<folder>/<asset> ...]

One row per picture: the classic picture at 3.5x nearest (what the pixels are), then every method of upscale.METHODS at
D2R's HD size (98 px per cell), on the inventory's dark background. A `d2r/...` entry shows D2R's own HD sprite of that
asset (from the D2R extraction) as a reference row. The sheet is a picture of game art: keep it outside git
(mxl2012-runs/hditems/).
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402
import upscale  # noqa: E402
from dc6 import decode_frame, palette, read_dc6, read_sprite, write_png  # noqa: E402
from icon_paths import BASE  # noqa: E402
from item_art import CELL_CLASSIC, CELL_HD, GROUPS  # noqa: E402

DEFAULT = ["mxl/r-a-01", "mxl/ring01", "mxl/sigil1b", "mxl/zelixir1", "mxl/shinieblue", "mxl/pearl1", "mxl/hardmode",
           "mxl/jbscross", "mxl/s1", "mxl/summbook", "classic/invscp", "classic/invhmr", "d2r/misc/ring/ring",
           "d2r/misc/gem/perfect_ruby"]
BG = (24, 20, 16)
PAD = 6


def picture(entry: str, pal: list) -> np.ndarray:
    group, inv = entry.split("/", 1)
    w, h, _ox, _oy, block = read_dc6(GROUPS[group] / f"{inv}.dc6")[0]
    return upscale.rows_to_array(decode_frame(w, h, block, pal, fill=True))


def d2r_sprite(asset: str) -> np.ndarray:
    return upscale.rows_to_array(read_sprite(fxpaths.D2R_DATA / "hd" / "global" / "ui" / "items" / f"{asset}.sprite")[0])


def sheet(entries: list[str], pal: list) -> np.ndarray:
    rows = []
    for e in entries:
        if e.startswith("d2r/"):
            rows.append([d2r_sprite(e[4:])])
            continue
        a = picture(e, pal)
        f = CELL_HD / CELL_CLASSIC
        near = np.repeat(np.repeat(a, 4, 0), 4, 1)
        near = upscale.resize(near, round(a.shape[1] * f), round(a.shape[0] * f), upscale.Image.Resampling.NEAREST)
        rows.append([near] + [upscale.upscale(a, f, m) for m in upscale.METHODS])
    cols = 1 + len(upscale.METHODS)
    cw = max(img.shape[1] for r in rows for img in r) + PAD
    heights = [max(img.shape[0] for img in r) + PAD for r in rows]
    out = np.zeros((sum(heights) + PAD, cols * cw + PAD, 4), np.uint8)
    out[...] = (*BG, 255)
    y = PAD
    for r, rh in zip(rows, heights):
        for i, img in enumerate(r):
            x = PAD + i * cw
            h, w = img.shape[:2]
            al = img[..., 3:4].astype(np.float32) / 255
            dst = out[y:y + h, x:x + w, :3].astype(np.float32)
            out[y:y + h, x:x + w, :3] = np.rint(img[..., :3] * al + dst * (1 - al)).astype(np.uint8)
        y += rh
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    img = sheet(argv[1:] or DEFAULT, palette(BASE / "palette" / "pal.dat"))
    write_png(Path(argv[0]), img.shape[1], img.shape[0], img.tobytes())
    print(f"{argv[0]}: {img.shape[1]} x {img.shape[0]}, columns: nearest (reference), " + ", ".join(upscale.METHODS))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
