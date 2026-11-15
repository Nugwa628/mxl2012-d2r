"""Cut the stash's HD grid cells for the invtabs HD panel (D2R-XL 2012, docs/invtabs.md "HD panel art").

Writes data/hd/global/ui/panel/invtabs/stockgrid.sprite (and its .lowend half): the 10 x 10 cells of 98 px of D2R's
personal stash background (PANEL\\Stash\\StashPanel_BG_Personal, grid at 89,219) with the 8 px of frame around them,
996 x 996 RGBA. The plugin re-tiles it at run time to each tab's size (invtabs/src/layouts.h TileStockGrid).

Also data/hd/global/ui/panel/invtabs/button.sprite (and .lowend): the inventory's Charms button, 56 x 56, 4 frames in the
plugin's order (normal, pressed, disabled, hovered), in D2R HD's button style (tools/hd_buttons.py: D2R's stone rim, a dark
well, a charm drawn at native size; bug #592). The plugin uses it when the mod has it (invtabs.cpp AddButton), else its drawn
stand-in. The art is read from the D2R extraction or the shared cache at build time; nothing of Blizzard's is in git.

    py -3 -I tools/invtabs_hdart.py build --out work/mod/data
    py -3 -I tools/invtabs_hdart.py check --out work/mod/data
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dc6  # noqa: E402
import fxpaths  # noqa: E402

SOURCE = "data/hd/global/ui/panel/stash/stashpanel_bg_personal.sprite"
OUT_REL = Path("hd/global/ui/panel/invtabs/stockgrid.sprite")
GRID_X, GRID_Y, CELL, CELLS, FRAME = 89, 219, 98, 10, 8
SIZE = CELLS * CELL + 2 * FRAME  # 996 (layouts.h StockSize)
BUTTON_REL = Path("hd/global/ui/panel/invtabs/button.sprite")
BUTTON = 56  # invtabs.cpp ButtonSize: the drawn stand-in's size, so the button keeps its place and size in the inventory
BUTTON_FRAMES = ("normal", "pressed", "greyed", "hovered")  # the plugin's normal, pressed, disabled, hovered frames


def cut(sprite: bytes) -> bytes:
    """The grid block (RGBA rows) out of a version-31 sprite's first frame."""
    if sprite[:4] != b"SpA1":
        raise ValueError("not a sprite")
    ver, fw, sw, h, _z, frames = struct.unpack_from("<HHIIII", sprite, 4)
    if ver != 31 or frames < 1:
        raise ValueError(f"sprite version {ver} with {frames} frame(s): expected an uncompressed version 31 sprite")
    x0, y0 = GRID_X - FRAME, GRID_Y - FRAME
    if fw < x0 + SIZE or h < y0 + SIZE:
        raise ValueError(f"sprite {fw} x {h} is too small for the stash grid")
    data = sprite[dc6.HEADER:]
    rows = [data[((y0 + y) * sw + x0) * 4:((y0 + y) * sw + x0 + SIZE) * 4] for y in range(SIZE)]
    return b"".join(rows)


def half(rgba: bytes, w: int, h: int) -> bytes:
    out = bytearray()
    for y in range(h // 2):
        for x in range(w // 2):
            for k in range(4):
                s = sum(rgba[((2 * y + dy) * w + 2 * x + dx) * 4 + k] for dy in (0, 1) for dx in (0, 1))
                out.append(s // 4)
    return bytes(out)


def build(out_data: Path) -> list[str]:
    rgba = cut(fxpaths.d2r_file(SOURCE).read_bytes())
    path = Path(out_data) / OUT_REL
    dc6.write_item_sprite(path, SIZE, SIZE, rgba)
    low = path.with_name(path.stem + ".lowend.sprite")
    dc6.write_item_sprite(low, SIZE // 2, SIZE // 2, half(rgba, SIZE, SIZE))
    return [path.as_posix(), low.as_posix()] + build_button(out_data)


def button_frames(src=None) -> list:
    """The Charms button's 4 frames (BUTTON_FRAMES order). src: hd_buttons.Sources (default D2R's own pictures)."""
    import hd_buttons
    return hd_buttons.frames("charms", BUTTON, BUTTON, BUTTON_FRAMES, src)


def build_button(out_data: Path, src=None) -> list[str]:
    import hd_buttons
    import ui_art
    frames = button_frames(src)
    path = Path(out_data) / BUTTON_REL
    ui_art.write_sprite(path, frames, BUTTON + 2)
    low = path.with_name(path.stem.split(".")[0] + ".lowend.sprite")
    ui_art.write_sprite(low, hd_buttons.lowend(frames), BUTTON // 2 + 2)
    return [path.as_posix(), low.as_posix()]


def check(out_data: Path) -> list[str]:
    path = Path(out_data) / OUT_REL
    if not path.exists():
        return [f"{path.as_posix()}: missing (run build)"]
    info = dc6.sprite_info(path)
    if (info["version"], info["frame_width"], info["height"], info["frames"]) != (31, SIZE, SIZE, 1):
        return [f"{path.as_posix()}: {info} is not a {SIZE} x {SIZE} version 31 sprite"]
    problems = []
    for rel, size in ((BUTTON_REL, BUTTON), (BUTTON_REL.with_name("button.lowend.sprite"), BUTTON // 2)):
        p = Path(out_data) / rel
        if not p.exists():
            problems.append(f"{p.as_posix()}: missing (run build)")
            continue
        info = dc6.sprite_info(p)
        if (info["frame_width"], info["height"], info["frames"]) != (size, size, len(BUTTON_FRAMES)):
            problems.append(f"{p.as_posix()}: {info} is not {len(BUTTON_FRAMES)} frames of {size} x {size}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=("build", "check"))
    ap.add_argument("--out", type=Path, required=True, help="the mod's data folder (work/mod/data)")
    a = ap.parse_args(argv)
    if a.command == "build":
        print("\n".join(build(a.out)))
        return 0
    problems = check(a.out)
    print("\n".join(problems) or "invtabs HD art: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
