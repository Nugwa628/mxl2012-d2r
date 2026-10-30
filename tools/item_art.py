"""Classic inventory pictures (DC6) as D2R HD inventory sprites (adapted from another port's item_art.py).

D2R's HD inventory sprites (data/hd/global/ui/items/<weapon|armor|misc>/...) are one RGBA frame, 98 pixels per inventory
cell (classic: 28), plus a .lowend.sprite at 49 pixels per cell; header as dc6.write_item_sprite. A picture (frame 0, units
palette) is scaled by 3.5 (tools/upscale.py METHOD: Scale2x on edges, Lanczos in the texture, mild sharpen; premultiplied
alpha) and centred on its item's invwidth x invheight cells, then written to <folder>/<group>/<inv>.sprite; the asset name
is "<group>/<inv>":
  mxl      the mod's own picture (data/global/items/<inv>.dc6 in the mod's MPQ)
  classic  D2R's classic picture of a vanilla invfile that no D2R item maps to an HD sprite (fallback, rare)
A picture that is vanilla art (tools/item_reuse.py: exact, recolour, rescale of a D2R picture with an HD sprite) is
rendered from D2R's HD sprite instead (recoloured / scaled), at the same path. A picture with a proposal switched on
(tools/data/item_art_proposals.json, item_art_review.enabled_proposals) is made from that entry instead, by the review
sheets' own code (item_art_sheets.candidate): a D2R HD (lowend) sprite recoloured, or another upscale setting.
Results are cached: a sprite newer than its DC6 and than the converting tools is kept.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upscale  # noqa: E402
from dc6 import decode_frame, read_dc6, write_item_sprite  # noqa: E402
from icon_paths import BASE, HD_OUT, MOD  # noqa: E402

MOD_ITEMS = MOD / "items"
D2R_ITEMS = BASE / "items"
CELL_CLASSIC, CELL_HD, CELL_LOW = 28, 98, 49
GROUPS = {"mxl": MOD_ITEMS, "classic": D2R_ITEMS}
TOOLS = [Path(__file__).resolve().parent / f for f in ("item_art.py", "upscale.py", "item_reuse.py", "colour_shift.py", "dc6.py",
                                                       "item_art_sheets.py", "rune_hd.py")]


def asset_size(w: int, h: int, cells_w: int, cells_h: int) -> tuple[int, int]:
    """Cells the sprite spans: the table's, or more when the picture itself is bigger."""
    return max(cells_w or 1, -(-w // CELL_CLASSIC)), max(cells_h or 1, -(-h // CELL_CLASSIC))


def convert(src: Path, dst: Path, cells_w: int, cells_h: int, pal: list, cell: int = CELL_HD, reuse=None,
            hd_items: Path | None = None, proposal: dict | None = None) -> tuple[int, int] | None:
    """Writes one sprite of the DC6 `src` at `cell` pixels per cell (from the proposal entry `proposal` when given, else
    from D2R's HD sprite when `reuse` is an item_reuse.Match); returns its size in pixels, None for an empty DC6."""
    frames = read_dc6(src)
    if not frames:
        return None
    w, h, _ox, _oy, block = frames[0]
    cw, ch = asset_size(w, h, cells_w, cells_h)
    if proposal is not None:
        import item_art_sheets
        img, _label = item_art_sheets.candidate(proposal, upscale.rows_to_array(decode_frame(w, h, block, pal, fill=True)),
                                                cw * cell, ch * cell, hd_items, cell)
    elif reuse is not None:
        import item_reuse
        img = item_reuse.render(reuse, cw * cell, ch * cell, cell == CELL_LOW, hd_items)
    else:
        img = upscale.place(upscale.upscale(upscale.rows_to_array(decode_frame(w, h, block, pal, fill=True)), cell / CELL_CLASSIC),
                            cw * cell, ch * cell)
    write_item_sprite(dst, cw * cell, ch * cell, img.tobytes())
    return cw * cell, ch * cell


def make_asset(group: str, inv: str, folder: str, cells_w: int, cells_h: int, pal: list,
               hd_root: Path = HD_OUT, sources: dict | None = None, reuse=None, hd_items: Path | None = None,
               proposal: dict | None = None, deps: tuple = ()) -> str | None:
    """Writes the HD + lowend sprites of picture <inv> of `group` (if needed) and returns its asset name, else None.
    `reuse`: an item_reuse.Match (render from D2R's HD sprite under `hd_items`); `proposal`: a proposal entry switched on
    (wins over `reuse`); `deps`: more files whose change remakes the sprites (the proposals file)."""
    src = (sources or GROUPS)[group] / f"{inv}.dc6"
    if not src.exists():
        return None
    base = hd_root / "global" / "ui" / "items" / folder / group
    hd, low = base / f"{inv}.sprite", base / f"{inv}.lowend.sprite"
    newest = max([src.stat().st_mtime] + [Path(t).stat().st_mtime for t in (*TOOLS, *deps) if Path(t).exists()])
    if not (hd.exists() and low.exists() and min(hd.stat().st_mtime, low.stat().st_mtime) >= newest):
        if convert(src, hd, cells_w, cells_h, pal, CELL_HD, reuse, hd_items, proposal) is None:
            return None
        convert(src, low, cells_w, cells_h, pal, CELL_LOW, reuse, hd_items, proposal)
    return f"{group}/{inv}"

