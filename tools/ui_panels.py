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
from PIL import Image  # noqa: E402

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
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path, help="also write a reduced PNG of each panel here")
    args = ap.parse_args(argv)
    print("\n".join(build(preview=args.preview)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
