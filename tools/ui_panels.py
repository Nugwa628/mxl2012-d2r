"""The mod's inventory and Horadric Cube panels as D2R HD panel backgrounds (adapted from another port's ui_panels.py).

Median XL 2012's grids differ from D2R's in two places (inventory.txt, `docs/hd-ui.md` has the table): the player inventory is
10 x 6 (D2R 10 x 4) and the Horadric Cube ("Transmogrify Box") 10 x 8 (D2R 3 x 4); the stash is 10 x 10 in both (so D2R's
HD stash panel is used as it is), trade, vendor and hireling grids equal D2R's too.

D2R's HD panels draw a 1162 x 1507 background sprite (PANEL\\Inventory\\Background = data/hd/global/ui/panel/inventory/
background.sprite, plus a `.lowend` at half size). The mod's panels are classic 320 x 432 pictures in sets of four DC6 tiles
(ui_art.panel_sets): `invchar6.dc6` set 1 is the inventory (set 0 the character sheet, which D2R's own HD sheet replaces:
the same statistics boxes as vanilla), `supertransmogrifier.dc6` the cube. Each is scaled to 1162 x 1507 (x 3.631 across,
x 3.488 down; tools/upscale.py's hybrid, Scale2x on edges + Lanczos texture) and written to data/hd/global/ui/panel/mxl/<name>.sprite (+ .lowend), where
the layouts (tools/ui_layouts.py) name them as PANEL\\mxl\\<name>. D2R's HD art is drawn for 1162 x 1507 and the classic art
only has 320 x 432 pixels, so these panels are soft next to D2R's native ones: a redrawn HD frame is the next step.

Classic mode (G) needs no panel files: the mod's own DC6 files are what D2R's classic layouts name (`PANEL\\invchar6`,
`PANEL\\supertransmogrifier`); only the layouts' positions change.

  py -3 -I tools/ui_panels.py [--preview DIR]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import ui_art  # noqa: E402
import upscale  # noqa: E402
from ui_paths import HD_OUT, MOD_UI, PAL  # noqa: E402

HD_W, HD_H = 1162, 1507
SX, SY = HD_W / ui_art.PANEL_W, HD_H / ui_art.PANEL_H
# sprite name -> (dc6 file in ui/panel, set)
PANELS = {"inventory": ("invchar6.dc6", 1), "cube": ("supertransmogrifier.dc6", 0)}


def scale_panel(im: Image.Image, w: int = HD_W, h: int = HD_H, method: str = "hybrid") -> Image.Image:
    """The pixel-art upscaler (tools/upscale.py: Scale2x on edges, Lanczos in the texture, mild sharpen); "lanczos": the old
    plain Lanczos. Both on premultiplied alpha, so edges next to transparent pixels do not go dark."""
    if method == "lanczos":
        return im.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")
    return Image.fromarray(upscale.sharpen(upscale.hybrid(np.asarray(im.convert("RGBA")), w, h)), "RGBA")


def build(out_dir: Path = HD_OUT / "panel" / "mxl", preview: Path | None = None) -> list[str]:
    pal = ui_art.palette(PAL)
    report = []
    for name, (dc6_name, number) in PANELS.items():
        sets = ui_art.panel_sets(MOD_UI / "panel" / dc6_name, pal)
        full = scale_panel(sets[number])
        low = scale_panel(sets[number], HD_W // 2, HD_H // 2)
        ui_art.write_sprite(out_dir / f"{name}.sprite", [full])
        ui_art.write_sprite(out_dir / f"{name}.lowend.sprite", [low])
        report.append(f"panel {name}: {dc6_name} set {number} -> {HD_W}x{HD_H} (+ lowend {HD_W // 2}x{HD_H // 2})")
        if preview:
            ui_art.save_png(preview / f"panel_{name}.png", full.resize((HD_W // 3, HD_H // 3), Image.LANCZOS))
    dc6_name, number = PANELS["cube"]
    cube = ui_art.panel_sets(MOD_UI / "panel" / dc6_name, pal)[number]
    full, low = stash_cube(cube), stash_cube(cube, 2)
    ui_art.write_sprite(out_dir / f"{STASH_CUBE}.sprite", [full])
    ui_art.write_sprite(out_dir / f"{STASH_CUBE}.lowend.sprite", [low])
    report.append(f"panel {STASH_CUBE}: the cube's 10 x 8 cells -> {full.width}x{full.height} (+ lowend {low.width}x{low.height})")
    if preview:
        ui_art.save_png(preview / f"panel_{STASH_CUBE}.png", full)
    return report


STASH_CUBE = "stashcube"  # PANEL\\mxl\\stashcube: the RotW stash's cube window (ui_layouts.stash_hd, bug #515)


STASH_CUBE_BEVEL_RAMP = ((49, 38, 31), (128, 107, 99), (67, 54, 43))  # outer to inner, the window's grey bevel


def stash_cube(cube: Image.Image, div: int = 1) -> Image.Image:
    """The RotW stash's cube window (ui_layouts.STASH_CUBE_WINDOW, 287 x 385 inside a 3-pixel bevel): the bevel drawn
    whole, a black inside with the cube picture's own 10 x 8 cells (the classic grid of inventory.txt's Transmogrify Box,
    29 pixels a cell) resized to the cells the window's grid draws its items on (ui_layouts.stash_cube_grid), so each item
    sits in its own cell. `div` 2: the lowend."""
    import ui_layouts
    row = ui_layouts.table_rows()["Transmogrify Box Page 1"]
    cols, rows = row["gridX"], row["gridY"]
    wx, wy, ww, wh = ui_layouts.STASH_CUBE_WINDOW
    b = ui_layouts.STASH_CUBE_BEVEL
    gx, gy, cell = ui_layouts.stash_cube_grid(cols, rows)
    left, top = row["gridLeft"] - row["invLeft"], row["gridTop"]
    e = round(ui_layouts.STASH_CUBE_EDGE * row["gridBoxWidth"])  # the line round the cells, in the picture's pixels
    cells = cube.crop((left - e, top - e, left + cols * row["gridBoxWidth"] + e, top + rows * row["gridBoxHeight"] + e))
    w, h = ww + 2 * b, wh + 2 * b
    im = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    for i, colour in enumerate(STASH_CUBE_BEVEL_RAMP):
        ImageDraw.Draw(im).rectangle((i, i, w - 1 - i, h - 1 - i), outline=colour + (255,))
    im.paste((0, 0, 0, 255), (b, b, b + ww, b + wh))
    edge = ui_layouts.STASH_CUBE_EDGE * cell
    im.paste(cells.convert("RGBA").resize((round(cols * cell + 2 * edge), round(rows * cell + 2 * edge)), Image.LANCZOS),
             (round(gx - edge - wx + b), round(gy - edge - wy + b)))
    return im if div == 1 else im.resize((round(w / div), round(h / div)), Image.LANCZOS)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path, help="also write a reduced PNG of each panel here")
    args = ap.parse_args(argv)
    print("\n".join(build(preview=args.preview)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
