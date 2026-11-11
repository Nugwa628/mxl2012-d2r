"""Classic (legacy graphics, G) art of invtabs: each tab's 320 x 432 panel for its grid size, the tab buttons and the classic
inventory's button (lane invtabs-legacy; layout and geometry: tools/invtabs_legacy.py).

Built at mod build time from Median's and D2R's extractions; nothing of Blizzard's or Median's is in git (outputs go to the
mod's data folder under work/, previews to work/invtabs_art/):

  data/global/ui/panel/invtabs_<tab>.dc6       the tab's panel, 4 tiles (ui_art.TILES): Median's `tradestash.dc6` as it is
      (header, vine border, bottom band with the close square), its title drawn centred into the header's lower name box in
      D2R's classic font6 (the upper box plain, its divider covered); inside the stash frame above the grid a dark body with
      the summary box (Median's name box, stretched: its corners kept, its rims drawn longer) and the tab row; the grid: the
      stash's bottom `rows` rows of cells (its frame's top line above them), `cols` columns centred (the sides dark), so the
      last row always ends on the stash's own bottom line. Cells are 29 px, as Median's.
  data/global/ui/panel/invtabs_tab_<tab>.dc6   the tab's button, 3 frames of 24 x 24: normal (grey rim), pressed (icon one
      pixel down-right, darker rim), this tab (gold rim, lighter inside); the tab's classic item picture
      (global/items/<icon>.dc6) scaled down to fit 20 x 20 in the middle.
  data/global/ui/panel/invtabs_button.dc6      the classic inventory's button, 2 frames of 32 x 32 (normal, pressed): D2R's
      blank square `buysellbtn` frames 0 / 1 with the first tab's picture centred (pressed one pixel down-right).

Palette: D2R's units palette without dither (the sources are palette pictures), indices 1-224 only (0 transparent; 225-254
draw hot pink in D2R's UI).

    py -3 -I tools/invtabs_art.py build --out work/mod/data [--target invtabs|charminv] [--grid 10x6] [--tabs tabs.json]
           [--d2r <D2R 93847 extraction>] [--median <Median extraction>] [--preview work/invtabs_art] [--mock maps,potions]
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import dc6  # noqa: E402
import fxpaths  # noqa: E402
import invtabs_legacy as il  # noqa: E402
import rotw_stash_legacy as rsl  # noqa: E402
import ui_art  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PREVIEW = ROOT / "work" / "invtabs_art"
W, H = ui_art.PANEL_W, ui_art.PANEL_H
BODY_TOP = 83                          # under the stash frame's top line (rows 80-82)
GRID_LEFT = il.INNER_X0 - 2            # x 14: the grid's left line (x0 + 29k - 2 .. x0 + 29k)
BODY_X = (il.INNER_X0 + 1, il.INNER_X1)  # x 17..305: inside the frame's vertical lines (x 14-16, 306)
BODY_RGB = (10, 9, 8)                  # the dark inside of the stash cells
UPPER_DIVIDER = (90, 18, 101, 45)      # tradestash's upper name box: its divider, covered with the plain box from x 150
UPPER_PLAIN_X = 150
NAME_OUTER = (72, 46, 250, 69)         # the lower name box with its rim (x1 / y1 exclusive): the summary box's source
NAME_CORNER = 4
TITLE_FONT = "font6"
TITLE_COLOUR = (191, 169, 105)         # D2R's classic gold (rotw_stash_legacy.TAB_COLOURS active)
SAMPLE_FONT = "font8"                  # previews only: the summary lines' look (classic 8pt)
TAB_ICON = 20
RIM_GREY, RIM_DARK = (120, 120, 116), (60, 60, 58)
TAB_INSIDE, TAB_INSIDE_ON = (14, 13, 12), (40, 34, 22)
BUTTON = 32


def _dc6_image(path: Path, pal, frame: int = 0) -> Image.Image:
    w, h, _ox, _oy, block = dc6.read_dc6(path)[frame]
    return ui_art.to_image(dc6.decode_frame(w, h, block, pal))


def nine_slice(src: Image.Image, w: int, h: int, corner: int = NAME_CORNER) -> Image.Image:
    """`src` stretched to w x h: corners kept, edges and the middle drawn longer (nearest, so rims stay sharp)."""
    c, sw, sh = corner, src.width, src.height
    if w < 2 * c + 1 or h < 2 * c + 1:
        raise ValueError(f"nine_slice: {w} x {h} is smaller than two corners")
    out = Image.new("RGBA", (w, h))
    xs = ((0, c, 0, c), (c, sw - c, c, w - c), (sw - c, sw, w - c, w))
    ys = ((0, c, 0, c), (c, sh - c, c, h - c), (sh - c, sh, h - c, h))
    for sx0, sx1, dx0, dx1 in xs:
        for sy0, sy1, dy0, dy1 in ys:
            out.paste(src.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0), Image.NEAREST), (dx0, dy0))
    return out


def panel_image(median_data: Path, d2r, tab: "il.Tab") -> Image.Image:
    """The classic 320 x 432 panel of `tab` (RGBA, before quantising). `d2r`: a rotw_stash_legacy.D2R (palette, font)."""
    il.check_size(tab.cols, tab.rows)
    ts = ui_art.panel_sets(Path(median_data) / "global" / "ui" / "panel" / "tradestash.dc6", d2r.pal)[0]
    im = ts.copy()
    gx, gy = il.grid_origin(tab.cols, tab.rows)
    top = gy - il.LINE + 1                      # the grid's top line
    # the dark body inside the frame: from under the frame's top line down to the stash's bottom line (the grid goes back on)
    im.paste(Image.new("RGBA", (BODY_X[1] - BODY_X[0], il.GRID_BOTTOM - il.LINE + 1 - BODY_TOP), BODY_RGB + (255,)),
             (BODY_X[0], BODY_TOP))
    # the grid: the stash's last `rows` rows with the cell line above them (the frame's own top line, rows 80-82, carries
    # specks of the header's ornament: seen in game 2026-11-11), its first `cols` columns with their right line
    block = ts.crop((GRID_LEFT, top, il.INNER_X0 + tab.cols * il.CELL + 1, il.GRID_BOTTOM + 1))
    im.paste(block, (gx - 2, top))
    # the summary box: the lower name box, stretched
    x0, y0, x1, y1 = il.summary_box(tab.rows)
    im.alpha_composite(nine_slice(ts.crop(NAME_OUTER), x1 - x0, y1 - y0), (x0, y0))
    # header: the upper name box plain, the title in the lower one
    dx0, dy0, dx1, dy1 = UPPER_DIVIDER
    im.paste(ts.crop((UPPER_PLAIN_X, dy0, UPPER_PLAIN_X + dx1 - dx0, dy1)), (dx0, dy0))
    font = d2r.font(TITLE_FONT)
    if font is None:
        raise SystemExit(f"invtabs_art: D2R's classic font {TITLE_FONT} not found (extraction or the shared cache)")
    text = font.render(tab.title, TITLE_COLOUR)
    nx0, ny0, nx1, ny1 = il.TITLE_BOX
    if text.width > nx1 - nx0 or text.height > ny1 - ny0:
        raise ValueError(f"invtabs_art: title {tab.title!r} is {text.size}, the name box {nx1 - nx0} x {ny1 - ny0}")
    im.alpha_composite(text, (nx0 + (nx1 - nx0 - text.width) // 2, ny0 + (ny1 - ny0 - text.height) // 2))
    return im


def item_picture(d2r, icon: str) -> Image.Image:
    p = Path(d2r.data) / "global" / "items" / f"{icon}.dc6"
    if not p.exists():
        raise SystemExit(f"invtabs_art: item picture {p} not found")
    return _dc6_image(p, d2r.pal)


def _fit(im: Image.Image, box: int) -> Image.Image:
    bb = im.getbbox()
    im = im.crop(bb) if bb else im
    k = min(1.0, box / im.width, box / im.height)
    if k < 1.0:
        im = im.convert("RGBa").resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS).convert("RGBA")
    return im


def tab_frames(d2r, tab: "il.Tab") -> list[Image.Image]:
    """[normal, pressed, this tab], TAB_W x TAB_H each."""
    icon = _fit(item_picture(d2r, tab.icon), TAB_ICON)
    out = []
    for rim, inside, shift in ((RIM_GREY, TAB_INSIDE, 0), (RIM_DARK, TAB_INSIDE, 1), (TITLE_COLOUR, TAB_INSIDE_ON, 0)):
        f = Image.new("RGBA", (il.TAB_W, il.TAB_H), rim + (255,))
        f.paste(Image.new("RGBA", (il.TAB_W - 2, il.TAB_H - 2), inside + (255,)), (1, 1))
        f.alpha_composite(icon, ((il.TAB_W - icon.width) // 2 + shift, (il.TAB_H - icon.height) // 2 + shift))
        out.append(f)
    return out


def button_frames(d2r, tab: "il.Tab") -> list[Image.Image]:
    """[normal, pressed], 32 x 32: D2R's buysellbtn frames 0 / 1 with the tab's picture centred (pressed: +1, +1)."""
    pic = _fit(item_picture(d2r, tab.icon), BUTTON - 4)
    out = []
    for frame, shift in ((0, 0), (1, 1)):
        b = _dc6_image(Path(d2r.data) / "global" / "ui" / "panel" / "buysellbtn.dc6", d2r.pal, frame)
        if b.size != (BUTTON, BUTTON):
            raise ValueError(f"buysellbtn frame {frame}: {b.size}, {BUTTON} x {BUTTON} expected")
        b.alpha_composite(pic, ((BUTTON - pic.width) // 2 + shift, (BUTTON - pic.height) // 2 + shift))
        out.append(b)
    return out


def _check_indices(idx: np.ndarray, what: str) -> None:
    if idx.min() < 0 or idx.max() > 224:
        raise ValueError(f"{what}: palette index {int(idx.min())}..{int(idx.max())} outside 0..224")


def _q(im: Image.Image, pal, what: str) -> np.ndarray:
    idx = rsl.quantise(im, pal, dither=False)
    _check_indices(idx, what)
    return idx


def art(out_data: Path, median_data: Path, d2r, tabs: tuple, preview_dir: Path | None = PREVIEW, mock: tuple = ()) -> list[str]:
    """Write the DC6 files of every tab that fits classic (and previews); one line per file or skipped tab."""
    dest = Path(out_data) / "global" / "ui" / "panel"
    dest.mkdir(parents=True, exist_ok=True)
    done, files = [], []
    for tab in tabs:
        try:
            panel = _q(panel_image(median_data, d2r, tab), d2r.pal, il.art_name(tab))
        except il.ClassicSizeError as e:
            done.append(f"{tab.id}: no classic panel: {e}")
            continue
        files.append((il.art_name(tab), rsl.panel_tiles(panel)))
        files.append((il.tab_art_name(tab), [_q(f, d2r.pal, il.tab_art_name(tab)) for f in tab_frames(d2r, tab)]))
    files.append((il.BUTTON_ART, [_q(f, d2r.pal, il.BUTTON_ART) for f in button_frames(d2r, tabs[0])]))
    for name, frames in files:
        p = dest / f"{name}.dc6"
        p.write_bytes(rsl.dc6_bytes(frames))
        done.append(f"{p}: {len(frames)} frames ({' '.join(f'{f.shape[1]}x{f.shape[0]}' for f in frames)})")
    if preview_dir:
        preview(dest, d2r, tabs, Path(preview_dir), mock)
    return done


def _decoded(path: Path, pal) -> list[Image.Image]:
    return [ui_art.to_image(dc6.decode_frame(w, h, b, pal)) for w, h, _ox, _oy, b in dc6.read_dc6(path)]


def mock_up(dest: Path, d2r, tab: "il.Tab", tabs: tuple, mock_tabs: tuple = ()) -> Image.Image:
    """The panel as the game should draw it, decoded back from the DC6 files: tab buttons (this one active, the others
    normal; `mock_tabs` are extra tabs drawn for the review only), sample summary lines in classic font8, the close button."""
    im = ui_art.panel_sets(dest / f"{il.art_name(tab)}.dc6", d2r.pal)[0]
    shown = list(il.classic_tabs(tabs)) + [t for t in mock_tabs if t.id not in {x.id for x in tabs}]
    for i, t in enumerate(shown[:il.MAX_TABS]):
        p = dest / f"{il.tab_art_name(t)}.dc6"
        frames = _decoded(p, d2r.pal) if p.exists() else tab_frames(d2r, t)
        x, y, _w, _h = il.tab_rect(i, tab.rows)
        im.alpha_composite(frames[2 if t.id == tab.id else 0], (x, y))
    font = d2r.font(SAMPLE_FONT)
    if font:
        x0, y0, _x1, _y1 = il.summary_box(tab.rows)
        inset = il.SUMMARY_RIM + il.SUMMARY_PAD
        sample = ["12 charms count: 3 small, 6 large, 3 grand", "+35 to Strength", "+20 to Dexterity", "+41 to Life",
                  "+12% Fire Resistance", "+8% Faster Hit Recovery", "5% Chance to Find Magic Items", "+3 to Light Radius"]
        for i in range(il.summary_lines(tab.rows)):
            t = font.render(sample[i % len(sample)], (255, 255, 255) if i else TITLE_COLOUR)
            im.alpha_composite(t, (x0 + inset, y0 + inset + i * il.LINE_H + (il.LINE_H - t.height) // 2))
    close = _decoded(Path(d2r.data) / "global" / "ui" / "panel" / "buysellbtn.dc6", d2r.pal)[il.CLOSE_FRAMES["normal"]]
    im.alpha_composite(close, il.CLOSE_RECT[:2])
    return im


def preview(dest: Path, d2r, tabs: tuple, out: Path, mock: tuple = ()) -> list[Path]:
    """PNGs decoded back from the DC6 files: per tab the panel x2 with the cells traced, the mock-up x2; the buttons x4."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for tab in tabs:
        p = dest / f"{il.art_name(tab)}.dc6"
        if not p.exists():
            continue
        panel = ui_art.panel_sets(p, d2r.pal)[0]
        x2 = panel.resize((W * 2, H * 2), Image.NEAREST)
        px = x2.load()
        gx, gy = il.grid_origin(tab.cols, tab.rows)
        for k in range(tab.cols + 1):
            for y in range(gy * 2, (gy + tab.rows * il.CELL) * 2):
                px[(gx + k * il.CELL) * 2, y] = (0, 255, 255, 255)
        for k in range(tab.rows + 1):
            for x in range(gx * 2, (gx + tab.cols * il.CELL) * 2):
                px[x, (gy + k * il.CELL) * 2] = (0, 255, 255, 255)
        tag = f"{tab.id}_{tab.cols}x{tab.rows}"
        for name, im in ((f"panel_{tag}.png", panel), (f"panel_{tag}_x2_grid.png", x2),
                         (f"mock_{tag}_x2.png", mock_up(dest, d2r, tab, tabs, mock).resize((W * 2, H * 2), Image.NEAREST))):
            ui_art.save_png(out / name, im)
            written.append(out / name)
    for name in [il.tab_art_name(t) for t in il.classic_tabs(tabs)] + [il.BUTTON_ART]:
        frames = _decoded(dest / f"{name}.dc6", d2r.pal)
        fw = max(f.width for f in frames)
        sheet = Image.new("RGBA", (len(frames) * (fw + 4), max(f.height for f in frames)))
        for i, f in enumerate(frames):
            sheet.alpha_composite(f, (i * (fw + 4), 0))
        ui_art.save_png(out / f"{name}_x4.png", sheet.resize((sheet.width * 4, sheet.height * 4), Image.NEAREST))
        written.append(out / f"{name}_x4.png")
    return written


# review-only stand-ins (D2R's own classic pictures; the real tabs name theirs in the data lane's table)
MOCK_TABS = {"maps": il.Tab("maps", "Maps", "Maps", "invbsc"), "potions": il.Tab("potions", "Potions", "Potions", "invhp5"),
             "scrolls": il.Tab("scrolls", "Scrolls", "Scrolls", "invbsc"), "gems": il.Tab("gems", "Gems", "Gems", "invgsva"),
             "runes": il.Tab("runes", "Runes", "Runes", "invrber"), "keys": il.Tab("keys", "Keys", "Keys", "invkey")}


def resolve_inputs(args) -> tuple[Path, "rsl.D2R", Path]:
    """Median's data folder, D2R's extraction and the output, as legacy_art / charm_inv_art find them."""
    med = Path(args.median) if args.median else fxpaths.MXL_ROOT
    root = args.d2r or os.environ.get("MXL_D2R_EXTRACT") or os.environ.get("MXL_D2R_BASE") or fxpaths.D2R
    return med / "data", rsl.D2R(Path(root), use_cache=True), Path(args.out) if args.out else fxpaths.OUT


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("build",))
    ap.add_argument("--median", help="Median's extraction (its data/ folder is read); default fxpaths.MXL_ROOT")
    ap.add_argument("--d2r", help="D2R 93847's extraction; default MXL_D2R_EXTRACT / MXL_D2R_BASE / fxpaths.D2R")
    ap.add_argument("--out", help="the mod's data folder (default work/mod/data)")
    ap.add_argument("--target", choices=sorted(il.TARGETS), default="invtabs")
    ap.add_argument("--grid", type=il.parse_grid, help="the first tab's grid, COLSxROWS")
    ap.add_argument("--tabs", type=Path, help="JSON list of tabs {id, label, title, icon, cols, rows}")
    ap.add_argument("--preview", type=Path, default=PREVIEW, help="preview PNG folder")
    ap.add_argument("--mock", default="", help="review only: extra tabs drawn on the mock-up (" + ",".join(MOCK_TABS) + ")")
    a = ap.parse_args(argv)
    median_data, d2r, out = resolve_inputs(a)
    if not (median_data / "global" / "ui" / "panel" / "tradestash.dc6").exists():
        print(f"Median's files not found at {median_data} (MXL_EXTRACT / --median)")
        return 2
    tabs = il.load_tabs(a.tabs, il.TARGETS[a.target], a.grid)
    mock = tuple(MOCK_TABS[m] for m in a.mock.split(",") if m)
    for line in art(out, median_data, d2r, tabs, a.preview, mock):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
