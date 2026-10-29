"""Comparison sheets of the HD upscales lane hdpolish switched (docs/hd-icons.md "Picture quality"): skill icon sheets and the
inventory / cube panels, old method next to the new one, and the classic 225-254 remap (old nearest colour vs neighbour fill).

  py -3 -I tools/hd_polish_sheet.py <out_dir> [--legacy]

Writes <out_dir>/skill_icons.png (per row: one sheet's frames that draw palette indices 225-254, then a few others; columns:
classic 2x nearest, bilinear, hybrid), <out_dir>/panels.png (a 1:1 crop of each HD panel: Lanczos, hybrid) and, with
--legacy, <out_dir>/legacy_225.png (Median's DC6 with 225-254 pixels: as D2R's units palette draws the file, the old
nearest-colour remap, the neighbour fill; 4x nearest). Game art: keep the output out of git.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dc6  # noqa: E402
import legacy_art  # noqa: E402
import ui_art  # noqa: E402
import ui_panels  # noqa: E402
import upscale  # noqa: E402
from icon_paths import BASE, MOD  # noqa: E402
from skill_icons import SPELLS, TARGETS, strip_geometry  # noqa: E402
from ui_paths import MOD_UI  # noqa: E402

GAP = 6


def grid(rows: list[list[np.ndarray]], bg=(60, 0, 60, 255)) -> Image.Image:
    cw = [max(r[c].shape[1] for r in rows if c < len(r)) for c in range(max(map(len, rows)))]
    rh = [max(a.shape[0] for a in r) for r in rows]
    out = Image.new("RGBA", (sum(cw) + GAP * (len(cw) + 1), sum(rh) + GAP * (len(rh) + 1)), bg)
    y = GAP
    for r, h in zip(rows, rh):
        x = GAP
        for c, a in enumerate(r):
            out.alpha_composite(Image.fromarray(np.ascontiguousarray(a), "RGBA"), (x, y))
            x += cw[c] + GAP
        y += h + GAP
    return out


def skill_sheet(pal: list, per_sheet: int = 4) -> Image.Image:
    rows = []
    for _cls, (sheet, _target) in TARGETS.items():
        src = dc6.read_dc6(SPELLS / f"{sheet}.dc6")
        _stride, size = strip_geometry(len(src))
        pick = [i for i, f in enumerate(src) if any(c in dc6.UNUSED for c in f[4])][:per_sheet // 2]
        pick += [i for i in range(0, len(src), max(1, len(src) // per_sheet)) if i not in pick][:per_sheet - len(pick)]
        for i in pick:
            w, h, _x, _y, blk = src[i]
            rows_ = dc6.decode_frame(w, h, blk, pal, fill=True)
            a = upscale.rows_to_array(rows_)
            near = upscale.resize(a, w * 2, h * 2, Image.Resampling.NEAREST)
            old = upscale.rows_to_array(dc6.scale(rows_, size, size, size / max(w, h)))
            new = upscale.rows_to_array(upscale.scale_rows(rows_, size, size, size / max(w, h)))
            rows.append([near, old, new])
    return grid(rows)


def panel_sheet(pal: list, crop=(0, 0, 520, 640)) -> Image.Image:
    rows = []
    for _name, (dc6_name, number) in ui_panels.PANELS.items():
        im = ui_art.panel_sets(MOD_UI / "panel" / dc6_name, pal)[number]
        old = ui_panels.scale_panel(im, method="lanczos").crop(crop)
        new = ui_panels.scale_panel(im).crop(crop)
        rows.append([np.asarray(old), np.asarray(new)])
    return grid(rows)


def legacy_sheet(pal: list, limit: int = 24) -> Image.Image:
    remap = legacy_art.nearest_map(pal)
    rows = []
    for p in sorted(MOD.rglob("*.dc6")):  # Median's own files (the extraction), not the built copies
        b = p.read_bytes()
        hist = legacy_art.dc6_index_hist(b)
        if not any(k in legacy_art.HAZARD for k in hist):
            continue
        row = []
        for data in (b, legacy_art.remap_dc6(b, remap), legacy_art.remap_dc6(b, remap, pal)):
            frames = dc6.parse_dc6(data)
            i = next(k for k, f in enumerate(frames) if any(c in dc6.UNUSED for c in dc6.parse_dc6(b)[k][4])) \
                if p.name.endswith("skillicon.dc6") else 0
            w, h, _x, _y, blk = frames[i]
            a = upscale.rows_to_array(dc6.decode_frame(w, h, blk, pal))
            row.append(upscale.resize(a, w * 4, h * 4, Image.Resampling.NEAREST))
        rows.append(row)
        if len(rows) >= limit:
            break
    return grid(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--legacy", action="store_true", help="also the classic 225-254 sheet")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    pal = dc6.palette(BASE / "palette" / "pal.dat")
    ui_art.save_png(args.out / "skill_icons.png", skill_sheet(pal))
    ui_art.save_png(args.out / "panels.png", panel_sheet(pal))
    if args.legacy:
        ui_art.save_png(args.out / "legacy_225.png", legacy_sheet(pal))
    print(f"sheets written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
