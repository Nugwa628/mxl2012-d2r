"""The Stat Book's HD layouts and art (docs/statbook.md, option C: folder tabs on D2R's character sheet). The widget names the
statbook plugin binds to are listed in docs/statbook-layout.md (`contract_names` below; tools/tests/test_statbook_layout.py
checks that both agree and that every name is in the built layouts).

Adds to the sheet layout copies tools/sheet_resists.py writes (it must run first):
  global/ui/layouts/characterstatspanelhd.json             (PC, HD graphics)
      the tab strip in the title band (one ButtonWidget per tab: normal / hovered / pressed art, the short label, the page's
      full title as its tooltip; a selected overlay and label per tab), the page body (one seamless stone sprite over the
      sheet's body, not a tiled crop), LINES line slots (a heading, a full row, or two half rows each), the All Stats page (a
      search box in the developer menu's text box pattern, ALL_ROWS list rows with the three-layer highlight, a scroll track),
      and the marker widget StatBookMarker. D2R's stat points line (CombinedPointsInfo, LevelUpInfo) stays on every page:
      D2R's code shows it each frame, a layout cannot hide it.
Visibility: in game a layout's `visible: false` does not hold on this panel (every widget is drawn when the sheet opens, seen
2026-11-15), so the plugin sets it at run time. The layouts still write it on every widget, each leaf's combined with its
groups' (the start state the plugin and the tests read).
  global/ui/layouts/controller/characterstatspanelhd.json  (gamepad UI)
      the same names with gamepad rects (it is `basedOn` the PC file, so every widget is named again, every field
      written: a field left out takes the PC widget's): the tab strip in the sheet's top band (above it is D2R's own menu
      tab bar) with LB / RB and LT / RT glyphs, the lines in two columns over D2R's own plain gamepad stone, All Stats in two
      columns.
The legacy layout gets nothing: the themed pages are HD only, legacy graphics keep D2R's sheet without tabs.

Art (hd/global/ui/panel/statbook/*.sprite and .lowend.sprite), built from D2R's own HD sprites at build time (nothing of
Blizzard's in git):
  PageBody       one stone picture of the whole page body: patches of the clean stone of D2R's sheet background
                 (PANEL\\Character_Sheet\\Character_Background, the left column between the attribute wells), random place and
                 mirror, laid on a jittered grid, each cut along a ragged line with a narrow blend; no repeated strip, no seam.
  HalfCell, FullCell, AllCell   the sheet's own Fire Resistance well (bevels, label cell, divider, value cell) cut to the
                 cell size without scaling: caps kept, the inside rebuilt from pieces of the same well joined along ragged
                 lines. Several frames per sprite, each from other pieces, so stacked cells do not repeat.
  PadHalfCell, PadFullCell, PadAllCell   the same from the gamepad sheet's resistance inset.
  Tab, PadTab    the stash tab (PANEL\\stash\\MKB_Tabs_195_TGA) cut to width: frames normal, hovered (lighter), pressed,
                 disabled; TabSelected / PadTabSelected: the active tab with its gem.
  Rule, AllRule, PadRule, PadAllRule   the gold heading rule with a gap for the heading text (drawn).
  ScrollTrack, PadScrollTrack        the Advanced Stats panel's scroll bar cut to the list height; Empty: a transparent pixel.

`--preview TAB` (dev only) shows one tab with placeholder values from the book (rows tone-coloured, some zero, All Stats with
`--query`), for screenshots before the plugin fills anything: the hidden widgets are left out (preview_look), and the layout
it started from is kept in work/mod/statbook-preview-base/ for the next build. A normal build writes every widget, tab 0
selected.

  py -3 -I tools/statbook_layout.py build [--d2r EXTRACT] [--mod DATA] [--book FILE] [--preview TAB] [--query TEXT]
                                          [--pad-buttons bumpers|triggers]
  py -3 -I tools/statbook_layout.py render [--mod DATA] [--out DIR]     PNGs of the built layouts (PIL, real fonts) to compare
  py -3 -I tools/statbook_layout.py plain    write statbook/src/statbook_plain_layout.h (the plain D2R panel; committed)
  py -3 -I tools/statbook_layout.py art [--d2r EXTRACT] [--data DIR]   only the sprites a plain D2R install ships
                                          (PLAIN_OWN_ART) into DIR/hd/global/ui/panel/statbook (default work/statbook-art)
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

LAYOUTS = Path("global") / "ui" / "layouts"
PC_HD, PAD = "characterstatspanelhd.json", "controller/characterstatspanelhd.json"
ART_DIR = Path("hd") / "global" / "ui" / "panel" / "statbook"
ART = "PANEL\\StatBook\\"
BOOK = Path("statbook") / "statbook.txt"
MARKER = "StatBookMarker"
CLICK = "PanelManager:OpenPanel:statbook/StatBook"   # one panel name for every button; the click position picks it

LINES = 22            # line slots of a themed page (the longest page of data/statbook_pages.tsv has 21)
ALL_ROWS = 22         # All Stats list rows (PC); the gamepad shows PAD_ALL_ROWS
PAD_ROWS = 11         # gamepad: lines per column (two columns: LINES slots)
PAD_ALL_ROWS = 20     # gamepad All Stats: 2 columns of 10

# The row tones of statbook/src/book_logic.h (enum Tone, in its order) and their text colours.
TONES = (("White", "$FontColorWhite"), ("Grey", "$FontColorGray"), ("Red", "$FontColorRed"), ("Blue", "$FontColorBlue"),
         ("Yellow", "$FontColorYellow"), ("Purple", {"r": 60, "g": 220, "b": 60, "a": 255}), ("Magic", "$FontColorOrange"),
         ("Gold", "$FontColorGoldYellow"), ("ItemBlue", "$FontColorBlue"), ("Green", "$FontColorGreen"))
COLOUR_TONE = {"w": "White", "r": "Red", "b": "Blue", "y": "Yellow", "p": "Purple", "m": "Magic", "gold": "Gold", "blue": "ItemBlue",
               "green": "Green"}
GOLD = "$FontColorGoldYellow"
SHORT = {"resist": "Resist", "skills": "Skills"}     # tab labels shorter than the page title (the title is the tooltip)

# Font metrics: D2R's point sizes in panel units, measured (Formal at $SmallFontSize, 22: 15.7 units a character of prose,
# tools/wiki_layout.py) = the TTF at 32 px.
PX_PER_POINT = 32 / 22
FONTS = {"Formal": "data/hd/ui/fonts/formal436bt.ttf", "": "data/hd/ui/fonts/exocetblizzardot-medium.otf"}
LABEL_SPACING = "$ReducedSpacing"   # D2R's own sheet labels: kerning 0.94 (_profilehd.json)
LABEL_KERNING = 0.94
FIT_MARGIN = 1.02                   # PIL's advance widths against D2R's renderer: a value or label this close to its box wraps
HIT = "$FontColorOrange"            # the All Stats search match (255, 168, 0): D2R's gold (199, 179, 119) is too close to white


class Geo:
    """One layout's geometry (panel units)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


# PC HD: D2R's sheet art is 1162 x 1507. Title band inside 60-132, name band to 299 (ledge 299-305), body from 306 between the
# frame's inner bevels at x 51 / 1110, down to the stat points bar (after sheetres' third resistance row: 1381, ledge to 1401).
PC = Geo(tab_x=58, tab_y=60, tab_w=124, tab_gap=2, tab_right=1070, tab_pad=6,
         body=(51, 306, 1110, 1381),
         cell_x=63, line_y=318, pitch=47, cell_h=43, half=(350, 162), half_gap=11, full=(600, 435),
         label_pt=20, value_pt=22, heading_pt=18, label_dy=-2,
         search_y=316, slot_scale=0.62, all_x=63, all_y=398, all_pitch=43, all_h=40, all_w=990, all_cols=1,
         all_rows=ALL_ROWS, track_x=1064, pad=False, art="")
# Gamepad: D2R's sheet art 2738 x 1413, a plain stone body below the name band (ledge at 340) to 1335.
PADG = Geo(tab_x=140, tab_y=0, tab_w=300, tab_gap=8, tab_right=2598, tab_pad=24,
           body=None,
           cell_x=60, line_y=372, pitch=86, cell_h=78, half=(440, 190), half_gap=19, full=(800, 479), col_x=(60, 1399),
           label_pt=24, value_pt=26, heading_pt=22, label_dy=-3,
           search_y=360, slot_scale=0.8, all_x=60, all_y=468, all_pitch=86, all_h=78, all_w=1279, all_cols=2,
           all_rows=PAD_ALL_ROWS, track_x=None, pad=True, art="Pad")
# Side panel (option B, docs/statbook.md "Side host"): the book as its own panel right of the sheet, where D2R puts its Advanced
# Stats panel (x 1398 of the left panel anchor), SIDE_W x SIDE_H: D2R's Advanced Stats frame widened (side_body). Tabs down the
# left of the page (no Character tab: the sheet is beside it), a header row (page title, the top / side toggle at its right),
# the lines and All Stats as on the sheet in a narrower page (labels 18 pt, values 19 pt: the fit check holds every row).
SIDE_W, SIDE_H = 1342, 1507
SIDE_X, SIDE_Y = 1398, -651          # the panel's rect at $LeftPanelAnchor (0, 0.397): beside the sheet (236 + 1162)
SIDE = Geo(tab_x=100, tab_y=230, tab_w=150, tab_h=118, tab_gap=8, tab_right=None, tab_pad=10,
           body=None,
           cell_x=262, line_y=230, pitch=47, cell_h=43, half=(320, 140), half_gap=10, full=(560, 370),
           label_pt=18, value_pt=19, heading_pt=18, label_dy=-2,
           search_y=228, slot_scale=0.62, all_x=262, all_y=306, all_pitch=43, all_h=40, all_w=890, all_cols=1,
           all_rows=ALL_ROWS, track_x=1162, pad=False, art="Side")
# The top / side toggle (icon only, tooltip TOGGLE_TIP): the top-right corner of the page on both hosts. On the sheet right of
# the All Stats count and above the scroll track (on a themed page over the faded end of the first heading's rule); on the side
# panel at the right of its header row.
# 69 px: D2R's level-up button (84 px) brought down once, its glyph from 8x. On the sheet its right edge at the frame's inner
# bevel (1110), from the name band's ledge to above the second line (365) and the All Stats rows (398); the All Stats count
# ends left of it. On the side panel between its title (to 133) and the search row (228).
TOGGLE = 69
TOGGLE_PC = (1039, 294)
TOGGLE_SIDE = (1123, 158)
TOGGLE_TIP = "Tabs: Top / Side"
SIDE_TAB_TEXT = "$FontColorDarkGrayGold"  # the side tabs' labels: D2R's grey-gold (173, 168, 148); its tab grey-blue is too dark
# on the side tabs' darker stone
SIDE_PAGE_BOTTOM = 1420              # the bottom of the side panel's inner page (its frame below)


def half_w(g: Geo) -> int:
    return g.half[0] + g.half[1]


def full_w(g: Geo) -> int:
    return g.full[0] + g.full[1]


# ---- the book ------------------------------------------------------------------------------------------------------------
def read_book(text: str) -> dict:
    """The book file (tools/statbook.py): pages [(id, title, [records])], all [(heading, [texts])]."""
    pages, groups = [], []
    for ln in text.splitlines():
        f = ln.split("\t")
        if f[0] == "page":
            pages.append((f[1], f[2], []))
        elif f[0] in ("section", "row") and pages and not groups:
            pages[-1][2].append(f)
        elif f[0] == "group":
            groups.append((f[2] if len(f) > 2 else f[1], []))
        elif f[0] == "all" and groups:
            groups[-1][1].append(f)
    return {"pages": pages, "all": groups}


def full_book_text() -> str:
    """The book with every row of data/statbook_pages.tsv kept (the most any game's book can hold)."""
    import statbook

    class Every(dict):
        def __contains__(self, k):
            return True

        def __getitem__(self, k):
            return 1

        def get(self, k, d=None):
            return 1
    return statbook.book_text(Every(), [])


def page_lines(records: list) -> list[tuple]:
    """book_logic.h PageLines: ('heading', text) | ('full', row) | ('pair', row, row|None)."""
    out, pending = [], None
    for f in records:
        if f[0] == "section":
            if pending:
                out.append(("pair", pending, None))
                pending = None
            out.append(("heading", f[1]))
            continue
        if f[-1] == "h":
            if pending:
                out.append(("pair", pending, f))
                pending = None
            else:
                pending = f
            continue
        if pending:
            out.append(("pair", pending, None))
            pending = None
        out.append(("full", f))
    if pending:
        out.append(("pair", pending, None))
    return out


def tabs(book: dict) -> list[tuple[str, str]]:
    """(label, full title) per tab: the sheet, the pages, All Stats."""
    out = [("Character", "Character")]
    for pid, title, _ in book["pages"]:
        out.append((SHORT.get(pid, title), title))
    out.append(("All Stats", "All Stats"))
    return out


# ---- fonts ---------------------------------------------------------------------------------------------------------------
_FONTS: dict = {}


def font(face: str, pt: float):
    """D2R's font file as a PIL font at `pt` points (None when the file is not available here)."""
    from PIL import ImageFont
    key = (face, round(pt * PX_PER_POINT * 4))
    if key not in _FONTS:
        try:
            import fxpaths
            path = fxpaths.d2r_file(FONTS[face])
            # Pillow's BASIC layout on every OS: Linux wheels have raqm (kerning, e.g. "Advanced" 130.3 px at 18 pt against
            # BASIC's 130), Windows wheels lack fribidi and always fell back to BASIC, so the shipped sizes are BASIC's.
            _FONTS[key] = ImageFont.truetype(str(path), round(pt * PX_PER_POINT), layout_engine=ImageFont.Layout.BASIC)
        except (SystemExit, OSError, ImportError):
            _FONTS[key] = None
    return _FONTS[key]


def text_w(text: str, face: str, pt: float) -> float | None:
    f = font(face, pt)
    return None if f is None else f.getlength(text)


def tab_point_size(labels: list[str], g: Geo) -> int:
    """The largest point size (at most 20 PC, 24 gamepad, 18 side) at which every tab label fits its tab (the side panel has
    no Character tab: labels[0] is left out there)."""
    room = g.tab_w - 2 * g.tab_pad
    if g is SIDE:
        labels = labels[1:]
    for pt in range(24 if g.pad else 18 if g is SIDE else 20, 9, -1):
        ws = [text_w(t, "", pt) for t in labels]
        if None in ws or max(ws) <= room:
            return pt
    return 10


def fit_problems(book: dict, g: Geo) -> list[str]:
    """Texts that do not fit their boxes with D2R's real fonts (empty when the fonts are not available here)."""
    out = []
    if font("Formal", 20) is None:
        return out
    if g.tab_right is None:             # the side panel's tabs run down the page (no Character tab)
        if g.tab_y + (len(tabs(book)) - 1) * (g.tab_h + g.tab_gap) - g.tab_gap > SIDE_PAGE_BOTTOM:
            out.append("the side tabs do not fit the column")
    elif len(tabs(book)) * (g.tab_w + g.tab_gap) - g.tab_gap > g.tab_right - g.tab_x:
        out.append("the tabs do not fit the strip")
    pt = tab_point_size([t for t, _ in tabs(book)], g)
    for t, _ in tabs(book)[1 if g is SIDE else 0:]:
        if text_w(t, "", pt) > g.tab_w - 2 * g.tab_pad:
            out.append(f"tab {t!r}")
    for pid, _title, recs in book["pages"]:
        lines = page_lines(recs)
        if len(lines) > LINES:
            out.append(f"page {pid}: {len(lines)} lines, {LINES} slots")
        for ln in lines:
            if ln[0] == "heading":
                if text_w(ln[1], "", g.heading_pt) > rule_gap(book, g):
                    out.append(f"heading {ln[1]!r}")
                continue
            box = g.full if ln[0] == "full" else g.half
            for r in ln[1:]:
                if r is None:
                    continue
                if text_w(r[1], "Formal", g.label_pt) * LABEL_KERNING * FIT_MARGIN > box[0] - 14:
                    out.append(f"{pid}: label {r[1]!r} ({ln[0]})")
                if text_w(value_sample(r[3]), "", g.value_pt) * FIT_MARGIN > box[1] - 12:
                    out.append(f"{pid}: value {value_sample(r[3])!r} of {r[1]!r} ({ln[0]})")
    return out


def value_sample(fmt: str) -> str:
    """The widest value of a format the layout must hold: four digits per value (\"+1000%\", \"1000% (max 1000%)\")."""
    import statbook
    if fmt in statbook.SPECIAL_FORMATS:
        return statbook.sample(fmt)
    return re.sub(r"%(%|\+d|d)", lambda m: {"%": "%", "+d": "+1000", "d": "1000"}[m.group(1)], fmt)


def rule_gap(book: dict, g: Geo) -> int:
    heads = [ln[1] for _p, _t, recs in book["pages"] for ln in page_lines(recs) if ln[0] == "heading"]
    ws = [text_w(h, "", g.heading_pt) for h in heads] or [0]
    return int(max((w or 260) for w in ws)) + 40


# ---- art -----------------------------------------------------------------------------------------------------------------
OV, BLEND = 10, 4     # overlap and blend of a ragged join
ART_VERSION = 4       # raised when the art method changes (the build's art cache key)
CENTRE_MARK = 80      # width kept clear around a centred mark


def _wander(n: int, lo: int, hi: int, rnd: random.Random) -> list[int]:
    c, out = (lo + hi) // 2, []
    for i in range(n):
        if i % 6 == 0:
            c = max(lo, min(hi, c + rnd.choice((-1, 0, 1))))
        out.append(c)
    return out


def join_h(a, b, rnd: random.Random):
    """a and b side by side, overlapping OV columns, joined along a ragged vertical line with a BLEND-pixel blend."""
    import numpy as np
    from PIL import Image
    a, b = np.asarray(a.convert("RGBA"), np.float32), np.asarray(b.convert("RGBA"), np.float32)
    h = a.shape[0]
    w = a.shape[1] + b.shape[1] - OV
    out = np.zeros((h, w, 4), np.float32)
    out[:, :a.shape[1]] = a
    x0 = a.shape[1] - OV
    cuts = np.array(_wander(h, BLEND // 2 + 1, OV - BLEND // 2 - 1, rnd), np.float32)[:, None]
    xs = np.arange(OV, dtype=np.float32)[None, :]
    al = np.clip((xs - cuts) / BLEND + 0.5, 0, 1)[..., None]
    out[:, x0:x0 + OV] = out[:, x0:x0 + OV] * (1 - al) + b[:, :OV] * al
    out[:, x0 + OV:] = b[:, OV:]
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")


def fit_width(img, w: int, cap_l: int, cap_r: int, rnd: random.Random, centre: bool = False, mirror: bool = True):
    """img cut to width w without scaling: its left cap_l and right cap_r columns kept, the inside between them rebuilt from
    pieces of the inside (random place and mirror; `centre`: one piece from the middle, for art with a centred mark), each
    joined along a ragged line."""
    from PIL import ImageOps
    W, H = img.size
    if w == W:
        return img.convert("RGBA")
    inner = img.crop((cap_l, 0, W - cap_r, H))
    out = img.crop((0, 0, cap_l + OV, H))
    first = True
    while out.width < w - cap_r:
        need = (w - cap_r) - out.width + OV
        cw = min(inner.width, max(need, OV * 3))
        if centre and first:
            x0 = (inner.width - cw) // 2
        elif centre:                        # the other pieces from beside the centred mark (a tab's gem), never across it
            side = max(OV * 3, (inner.width - CENTRE_MARK) // 2)
            cw = min(cw, side)
            x0 = rnd.choice((rnd.randint(0, side - cw), inner.width - side + rnd.randint(0, side - cw)))
        else:
            x0 = rnd.randint(0, inner.width - cw)
        piece = inner.crop((x0, 0, x0 + cw, H))
        if mirror and not (centre and first) and rnd.random() < 0.5:
            piece = ImageOps.mirror(piece)
        out = join_h(out, piece, rnd)
        first = False
    out = out.crop((0, 0, w - cap_r, H))
    right = img.crop((W - cap_r - OV, 0, W, H))
    return join_h(out, right, rnd)


def fit_height(img, h: int, cap_t: int, cap_b: int, rnd: random.Random):
    from PIL import Image
    t = img.transpose(Image.Transpose.TRANSPOSE)
    return fit_width(t, h, cap_t, cap_b, rnd, mirror=False).transpose(Image.Transpose.TRANSPOSE)


def feather(img, edge: int = 3):
    """Alpha falling off over the outer `edge` pixels."""
    import numpy as np
    from PIL import Image
    a = np.asarray(img.convert("RGBA")).copy()
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.minimum.reduce([xx + 1, w - xx, yy + 1, h - yy]).astype(np.float32)
    a[..., 3] = (a[..., 3] * np.clip(d / (edge + 1), 0, 1)).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


# D2R's sheet background: clean stone in the left column between the attribute wells, and the Fire Resistance well (sprite
# pixels; bevel lips 1181-1191 / 1241-1252, label cell 92-450, divider 450-455, value cell to the bevel at 575).
STONE_SOURCES = ((72, 460, 515, 640), (72, 715, 515, 897), (72, 970, 515, 1060))
FIRE_WELL = (86, 1179, 582, 1253)
FIRE_DIVIDER = 450 - FIRE_WELL[0]
PATCH, FADE = (220, 150), 44


def _patch_mask(w: int, h: int, rnd: random.Random, fade: int = FADE):
    """An opaque patch whose edge is a ragged line through the overlap with a 4-pixel blend (a soft fade would average two
    stones into a smooth band)."""
    import numpy as np
    from PIL import Image
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.minimum.reduce([xx + 1, w - xx, yy + 1, h - yy])
    small = np.array([[rnd.random() for _ in range(w // 12 + 2)] for _ in range(h // 12 + 2)]) * 255
    nz = np.asarray(Image.fromarray(small.astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
    edge = fade * (0.2 + 0.7 * nz)
    return Image.fromarray((np.clip((d - edge) / 4 + .5, 0, 1) * 255).astype(np.uint8))


def stone(sheet, w: int, h: int, seed: int = 7):
    """w x h of seamless stone from the sheet background's clean stone (see the header): no tile repeats at a period."""
    return stone_from([sheet.convert("RGB").crop(b) for b in STONE_SOURCES], w, h, seed)


def stone_from(srcs: list, w: int, h: int, seed: int = 7, patch: tuple[int, int] = PATCH, fade: int = FADE):
    """w x h of seamless stone from the RGB pictures `srcs`: patches of them (random place and mirror, brightness matched) on a
    jittered grid, each cut along a ragged line with a narrow blend."""
    from PIL import Image, ImageOps, ImageStat
    rnd = random.Random(seed)
    target = sum(ImageStat.Stat(s.convert("L")).mean[0] * s.width * s.height for s in srcs) / sum(s.width * s.height for s in srcs)
    out = Image.new("RGB", (w, h), (int(target),) * 3)
    pw, ph = patch
    FADE = fade  # noqa: N806  (this call's fade)
    step_x, step_y = pw - FADE * 2, ph - FADE * 2

    def piece():
        src = rnd.choice(srcs)
        hh = min(ph, src.height)
        sx, sy = rnd.randint(0, src.width - pw), rnd.randint(0, src.height - hh)
        p = src.crop((sx, sy, sx + pw, sy + hh))
        if rnd.random() < .5:
            p = ImageOps.mirror(p)
        if rnd.random() < .5:
            p = ImageOps.flip(p)
        d = target - ImageStat.Stat(p.convert("L")).mean[0]
        return p.point(lambda v, d=d: max(0, min(255, int(v + d))))

    for y in range(0, h, ph // 2):
        for x in range(0, w, pw):
            out.paste(piece(), (x, y))
    cells = [(x, y) for y in range(-FADE, h, step_y) for x in range(-FADE, w, step_x)]
    for _ in range(2):
        rnd.shuffle(cells)
        for x, y in cells:
            p = piece()
            jx, jy = rnd.randint(-step_x // 5, step_x // 5), rnd.randint(-step_y // 5, step_y // 5)
            out.paste(p, (x + jx, y + jy), _patch_mask(p.width, p.height, rnd, FADE))
    return out.convert("RGBA")


def cell(well, divider: int, label_w: int, value_w: int, h: int, caps: tuple[int, int, int, int], rnd: random.Random):
    """A label + value well: the well's label part and value part (from its divider) each cut to width, then to height."""
    from PIL import Image
    lab = fit_width(well.crop((0, 0, divider, well.height)), label_w, caps[0], 0, rnd)
    val = fit_width(well.crop((divider, 0, well.width, well.height)), value_w, 6, caps[1], rnd)
    both = Image.new("RGBA", (label_w + value_w, well.height))
    both.paste(lab, (0, 0))
    both.paste(val, (label_w, 0))
    return feather(fit_height(both, h, caps[2], caps[3], rnd))


def rule(w: int, gap: int):
    """The gold heading rule: a thin gold line with a dark line under it, fading at both ends and at the gap's edges."""
    import numpy as np
    from PIL import Image
    a = np.zeros((9, w, 4), np.uint8)
    x = np.arange(w, dtype=np.float32)
    g0, g1 = (w - gap) / 2, (w + gap) / 2
    fade = np.clip(np.minimum.reduce([x / 60, (w - 1 - x) / 60, np.where(x < w / 2, (g0 - x) / 30, (x - g1) / 30)]), 0, 1)
    for y, rgb, alpha in ((3, (120, 98, 47), 150), (4, (199, 179, 119), 230), (5, (150, 130, 80), 160), (6, (0, 0, 0), 120)):
        a[y, :, :3] = rgb
        a[y, :, 3] = (alpha * fade).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


def tab_frames(src, w: int, rnd_seed: int = 3):
    """Normal / hovered / pressed / disabled frames and the selected frame of a tab cut to width w."""
    from PIL import ImageEnhance
    normal = fit_width(src[0], w, 30, 30, random.Random(rnd_seed), centre=True)
    active = fit_width(src[1], w, 30, 30, random.Random(rnd_seed), centre=True)
    hovered = ImageEnhance.Brightness(normal).enhance(1.35)
    pressed = ImageEnhance.Brightness(active).enhance(0.85)
    disabled = ImageEnhance.Brightness(normal).enhance(0.6)
    return [normal, hovered, pressed, disabled], active


# D2R's Advanced Stats panel (PANEL\AdvancedCharacterSheet\AdvancedCharacterSheet_BG, 876 x 1507): its knotwork border repeats
# every 116.5 pixels (233 for two motifs, measured: the smallest column difference of the top and bottom border bands).
ADV_PERIOD2 = 233
ADV_SPLIT = 438                      # the column the widening goes in at (the middle, clear of the corner ornaments)
SIDE_INNER = (110, 176, 110, 1425)   # the inner page rebuilt as stone: x from the left, y top, x from the right, y bottom


def _feather_mask(w: int, h: int, edge: int):
    """Opaque inside, falling to 0 over `edge` pixels at every border (a wide soft edge: no line where it meets the frame)."""
    import numpy as np
    from PIL import Image
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.minimum.reduce([xx + 1, w - xx, yy + 1, h - yy])
    return Image.fromarray((np.clip(d / edge, 0, 1) ** 1.5 * 255).astype(np.uint8))


def side_body(adv, w: int = SIDE_W, seed: int = 21):
    """The side panel's background, w wide: D2R's Advanced Stats frame widened by whole border periods, then its inner page and
    title band rebuilt as one stone picture each (stone_from with the frame's own stone), laid in with a wide soft edge.

    The widening repeats the strip of two border motifs left of ADV_SPLIT; each piece starts where the one before ends in the
    pattern, so the knotwork runs on and the joins (ragged, blended) show no break. The inside of the strip would repeat the
    same cracks side by side, so the inner page and the title band are not kept: they are rebuilt from patches (no strip, no
    period), which leaves no vertical seam anywhere (owner rule)."""
    from PIL import Image
    adv = adv.convert("RGBA")
    W, H = adv.size
    extra = w - W
    if extra < 0 or extra % ADV_PERIOD2:
        raise ValueError(f"side width {w}: {W} plus whole multiples of {ADV_PERIOD2}")
    rnd = random.Random(seed)
    out = adv.crop((0, 0, ADV_SPLIT, H))
    for _ in range(extra // ADV_PERIOD2):
        out = join_h(out, adv.crop((ADV_SPLIT - ADV_PERIOD2 - OV, 0, ADV_SPLIT, H)), rnd)
    out = join_h(out, adv.crop((ADV_SPLIT - OV, 0, W, H)), rnd)
    # the bands with horizontal lines (the title band, the inner page's top and bottom with its frame line): rebuilt from
    # full-height pieces of the same rows joined with wide blends, so the lines run on and no join shows
    for y0, y1 in SIDE_BANDS:
        out.paste(band_rebuild(adv.crop((0, y0, W, y1)), w, rnd), (0, y0))
    rgb = adv.convert("RGB")
    l, t, r, b = SIDE_INNER        # the inner page: stone from three bands of it, so patches come from all its height
    x0, x1, y0, y1 = l + 20, W - r - 20, t + 20, b - 20
    third = (y1 - y0) // 3
    srcs = [rgb.crop((x0, y0 + k * third, x1, y0 + (k + 1) * third)) for k in range(3)]
    rw, rh = w - l - r, b - t
    out.paste(stone_from(srcs, rw, rh, seed + 1), (l, t), _feather_mask(rw, rh, 40))
    return out


SIDE_BANDS = ((52, 133), (133, 230), (1368, 1462))   # rows between the knotwork borders (they keep the period copy)
BAND_KEEP, BAND_PIECE, BAND_BLEND = 180, 240, 70


def _wide_join(a, b, blend: int):
    """a and b side by side, overlapping `blend` columns with a smooth (smoothstep) blend."""
    import numpy as np
    from PIL import Image
    a, b = np.asarray(a.convert("RGBA"), np.float32), np.asarray(b.convert("RGBA"), np.float32)
    x0 = a.shape[1] - blend
    out = np.zeros((a.shape[0], a.shape[1] + b.shape[1] - blend, 4), np.float32)
    out[:, :a.shape[1]] = a
    t = np.linspace(0, 1, blend, dtype=np.float32)
    al = (t * t * (3 - 2 * t))[None, :, None]
    out[:, x0:x0 + blend] = a[:, x0:] * (1 - al) + b[:, :blend] * al
    out[:, a.shape[1]:] = b[:, blend:]
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")


def band_rebuild(band, w: int, rnd: random.Random):
    """A horizontal band (full rows of the frame) at width w: its left and right BAND_KEEP columns kept (corner ornaments),
    the inside from full-height pieces of the band's own middle at random places (mirrored at random), wide blends between."""
    from PIL import ImageOps
    W, H = band.size
    out = band.crop((0, 0, BAND_KEEP + BAND_BLEND, H))
    right = band.crop((W - BAND_KEEP - BAND_BLEND, 0, W, H))
    need = w - right.width + BAND_BLEND
    while out.width < need:
        x = rnd.randint(BAND_KEEP, W - BAND_KEEP - BAND_PIECE)
        piece = band.crop((x, 0, x + BAND_PIECE, H))
        if rnd.random() < 0.5:
            piece = ImageOps.mirror(piece)
        out = _wide_join(out, piece, BAND_BLEND)
    return _wide_join(out.crop((0, 0, need, H)), right, BAND_BLEND)


def side_tab_frames(src, w: int, h: int, seed: int = 4):
    """A side tab, w x h: the stash tab (the top strip's art) turned to point left, its rounded edge to the left and its open
    side towards the page, cut to size like the top tabs. Frames normal / hovered / pressed / disabled, and the selected one."""
    from PIL import Image, ImageEnhance

    def turn(im, bottom):                     # fitted upright like a top tab (h wide, w tall), then turned
        im = im.convert("RGBA")
        up = fit_width(im, h, 30, 30, random.Random(seed), centre=True)
        up = fit_height(up, w, 12, bottom, random.Random(seed + 1))        # its frame lines: straight, run on unbroken
        # the stone inside rebuilt as one picture (no repeated rows), laid in with a soft edge over the fitted frame
        src = im.crop((8, 8, im.width - 8, im.height - bottom)).convert("RGB")
        rw, rh = h - 16, w - 8 - bottom + 4
        st = stone_from([src], rw, rh, seed, patch=(min(64, src.width), min(26, src.height)), fade=8)
        up.paste(st.convert("RGBA"), (8, 8), _feather_mask(rw, rh, 6))
        return up.transpose(Image.Transpose.ROTATE_90)                       # rounded top to the left, gem towards the page
    normal, active = turn(src[0], 12), turn(src[1], 36)
    return ([normal, ImageEnhance.Brightness(normal).enhance(1.35), ImageEnhance.Brightness(active).enhance(0.85),
             ImageEnhance.Brightness(normal).enhance(0.6)], active)


def toggle_frames(button, sheet, to: str, size: int = TOGGLE):
    """The top / side toggle, `to` = the mode a click switches to ("side" on the sheet, "top" on the side panel): D2R's level-up
    button (its gold frame, 83 x 84, and its four frames: normal, hovered, pressed, disabled) with the red inside replaced by
    the sheet's stone (darkened) under an inner bevel, and a gold glyph of a page with three tabs down its left ("side") or
    along its top ("top"), the first tab the bright one. The glyph is drawn at 8x and brought down, the whole button then
    brought down once to `size` (LANCZOS), so frame and glyph stay sharp."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    S = 8                                            # glyph supersampling
    out = []
    for n in range(4):
        fr = button[n].convert("RGBA")
        W, H = fr.size
        i0, i1, j1 = 15, W - 16, H - 16              # the inside (left / top 15, right / bottom 16 of the frame's dark line)
        st = stone(sheet, i1 - i0 + 1, j1 - i0 + 1, seed=3).convert("RGBA")
        st = ImageEnhance.Brightness(st).enhance((0.62, 0.78, 0.5, 0.55)[n])
        if n == 3:
            st = ImageEnhance.Color(st).enhance(0)
        a = np.asarray(st).astype(np.float32)
        h, w = a.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        bevel = np.clip(1 - np.minimum(xx, yy) / 4.0, 0, 1) * 34 - np.clip(1 - np.minimum(w - 1 - xx, h - 1 - yy) / 4.0, 0, 1) * 40
        if n == 2:                                   # pressed: the bevel turned round
            bevel = -bevel
        a[..., :3] = np.clip(a[..., :3] + bevel[..., None], 0, 255)
        a[..., 3] = 255
        img = fr.copy()
        img.paste(Image.fromarray(a.astype(np.uint8), "RGBA"), (i0, i0))

        # the glyph, at S x over the button's own pixels
        big = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        lit = [(238, 214, 150), (250, 232, 170), (214, 188, 124), (128, 128, 128)][n]
        dim = [(168, 140, 86), (190, 160, 100), (150, 124, 76), (92, 92, 92)][n]
        off = S if n == 2 else 0

        def r(x0, y0, x1, y1, **kw):
            d.rounded_rectangle([x0 * S + off, y0 * S + off, x1 * S + off, y1 * S + off], radius=S * 1.2, **kw)
        if to == "side":
            page, tabs_ = (35, 23, 63, 62), [(20, 25 + k * 12, 32, 34 + k * 12) for k in range(3)]
        else:
            page, tabs_ = (22, 35, 61, 63), [(24 + k * 12, 20, 33 + k * 12, 32) for k in range(3)]
        shadow = Image.new("RGBA", big.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        for x0, y0, x1, y1 in [page] + tabs_:
            sd.rounded_rectangle([(x0 - 1.5) * S + off, (y0 - 1.5) * S + off, (x1 + 2.5) * S + off, (y1 + 2.5) * S + off],
                                 radius=S * 2, fill=(0, 0, 0, 210))
        big.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(S * 0.8)))
        r(*page, fill=(26, 22, 16, 255), outline=lit + (255,), width=round(S * 3.2))
        for k, (x0, y0, x1, y1) in enumerate(tabs_):
            r(x0, y0, x1, y1, fill=(lit if k == 0 else dim) + (255,))
        x0, y0, x1, y1 = page
        for k in range(3):                           # lines of text on the page
            ly = y0 + 9 + k * 8
            if ly + 3 < y1 - 4:
                r(x0 + 7, ly, x1 - (7 if k < 2 else 14), ly + 2.6, fill=dim + (255,))
        img.alpha_composite(big.resize((W, H), Image.LANCZOS))
        out.append(img.resize((size, size), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=2)))
    return out


def build_art(sprites, book: dict) -> dict:
    """Every Stat Book sprite: name -> frames. `sprites(rel)` reads a D2R HD sprite (rel = 'panel/...')."""
    from PIL import Image
    sheet = sprites("panel/character_sheet/character_background")[0]
    well = sheet.convert("RGBA").crop(FIRE_WELL)
    inset = sprites("controller/panel/charactersheet/v2/charactersheet_resistanceinset")[0].convert("RGBA")
    pad_div = pad_divider(inset)
    tab_src = sprites("panel/stash/mkb_tabs_195_tga")
    track = sprites("panel/advancedcharactersheet/advancedcharactersheet_scrollbar")[0]
    art: dict[str, list] = {}
    x0, y0, x1, y1 = PC.body
    art["PageBody"] = [stone(sheet, x1 - x0, y1 - y0)]
    rnd = random.Random(11)
    pc_caps, pad_caps = (14, 22, 12, 12), (14, 18, 12, 14)
    art["HalfCell"] = [cell(well, FIRE_DIVIDER, *PC.half, PC.cell_h, pc_caps, rnd) for _ in range(16)]
    art["FullCell"] = [cell(well, FIRE_DIVIDER, *PC.full, PC.cell_h, pc_caps, rnd) for _ in range(8)]
    art["AllCell"] = [all_cell(well, FIRE_DIVIDER, PC.all_w, PC.all_h, pc_caps, rnd) for _ in range(8)]
    art["PadHalfCell"] = [cell(inset, pad_div, *PADG.half, PADG.cell_h, pad_caps, rnd) for _ in range(12)]
    art["PadFullCell"] = [cell(inset, pad_div, *PADG.full, PADG.cell_h, pad_caps, rnd) for _ in range(6)]
    art["PadAllCell"] = [all_cell(inset, pad_div, PADG.all_w, PADG.all_h, pad_caps, rnd) for _ in range(6)]
    for name, g in (("Tab", PC), ("PadTab", PADG)):
        frames, selected = tab_frames(tab_src, g.tab_w)
        art[name], art[name + "Selected"] = frames, [selected]
    art["Rule"] = [rule(full_w(PC), rule_gap(book, PC))]
    art["PadRule"] = [rule(full_w(PADG), rule_gap(book, PADG))]
    art["AllRule"] = [rule(PC.all_w, rule_gap(book, PC))]
    art["PadAllRule"] = [rule(PADG.all_w, rule_gap(book, PADG))]
    art["ScrollTrack"] = [fit_height(track.convert("RGBA"), all_list_h(PC), 40, 40, random.Random(5))]
    art["Empty"] = [Image.new("RGBA", (2, 2))]
    # the side panel (option B) and the top / side toggle
    art["SideBody"] = [side_body(sprites("panel/advancedcharactersheet/advancedcharactersheet_bg")[0])]
    art["SideHalfCell"] = [cell(well, FIRE_DIVIDER, *SIDE.half, SIDE.cell_h, pc_caps, rnd) for _ in range(16)]
    art["SideFullCell"] = [cell(well, FIRE_DIVIDER, *SIDE.full, SIDE.cell_h, pc_caps, rnd) for _ in range(8)]
    art["SideAllCell"] = [all_cell(well, FIRE_DIVIDER, SIDE.all_w, SIDE.all_h, pc_caps, rnd) for _ in range(8)]
    art["SideRule"] = [rule(full_w(SIDE), rule_gap(book, SIDE))]
    art["SideAllRule"] = [rule(SIDE.all_w, rule_gap(book, SIDE))]
    frames, selected = side_tab_frames(tab_src, SIDE.tab_w, SIDE.tab_h)
    art["SideTab"], art["SideTabSelected"] = frames, [selected]
    button, stone_sheet = sprites("panel/character_sheet/levelupbutton"), sheet
    art["TabsToggleSide"] = toggle_frames(button, stone_sheet, "side")   # on the sheet: a click shows the tabs down the side
    art["TabsToggleTop"] = toggle_frames(button, stone_sheet, "top")     # on the side panel: a click puts them back on top
    return art


def all_cell(well, divider: int, w: int, h: int, caps, rnd: random.Random):
    """An All Stats row: one long label cell, no divider: the well's label part (left of the divider) closed by the well's
    right bevel, cut to the row's size (the inside only from the label part, so no divider piece repeats)."""
    from PIL import Image
    W, H = well.size
    src = Image.new("RGBA", (divider + caps[1], H))
    src.paste(well.crop((0, 0, divider, H)), (0, 0))
    src.paste(well.crop((W - caps[1], 0, W, H)), (divider, 0))
    return feather(fit_height(fit_width(src, w, caps[0], caps[1], rnd), h, caps[2], caps[3], rnd))


def pad_divider(inset) -> int:
    """x of the gamepad resistance inset's label / value divider (its darkest column right of the middle)."""
    import numpy as np
    a = np.asarray(inset.convert("L"), np.float32)
    h, w = a.shape
    band = a[h // 4: 3 * h // 4, w // 2: w - 40].mean(0)
    return int(np.argmin(band)) + w // 2 - 2


def all_list_h(g: Geo) -> int:
    return (g.all_rows // g.all_cols - 1) * g.all_pitch + g.all_h


def write_art(art: dict, data: Path) -> list[str]:
    import median_stash
    import ui_art
    out = []
    for name, frames in art.items():
        p = data / ART_DIR / f"{name.lower()}.sprite"
        stride = None if len(frames) == 1 else frames[0].width + 2
        ui_art.write_sprite(p, frames, stride)
        low = [median_stash.lowend(f) if f.width > 3 else f for f in frames]
        ui_art.write_sprite(p.with_name(p.stem + ".lowend.sprite"), low, None if len(low) == 1 else low[0].width + 2)
        out.append(name)
    return out


# ---- widgets -------------------------------------------------------------------------------------------------------------
def _vis(fields: dict, visible: bool | None) -> dict:
    if visible is not None:
        fields["visible"] = visible
    return fields


def tb(name: str, x: int, y: int, w: int, h: int, text: str = "", colour="$FontColorWhite", pt: int = 20, face: str = "",
       align: str = "center", visible: bool | None = None, spacing: str | None = None) -> dict:
    style = {"fontColor": colour, "pointSize": pt, "alignment": {"h": align, "v": "center"}}
    if face:
        style["fontFace"] = face
    if spacing:
        style["spacing"] = spacing
    return {"type": "TextBoxWidget", "name": name,
            "fields": _vis({"rect": {"x": x, "y": y, "width": w, "height": h}, "text": text, "style": style}, visible)}


def img(name: str, x: int, y: int, art: str, frame: int = 0, visible: bool | None = None, scale: float | None = None) -> dict:
    r = {"x": x, "y": y}
    if scale is not None:
        r["scale"] = scale
    f = {"rect": r, "filename": art if "\\" in art or "/" in art else ART + art}
    f["frame"] = frame     # always: the gamepad file is `basedOn` the PC one and would take the PC widget's frame
    return {"type": "ImageWidget", "name": name, "fields": _vis(f, visible)}


def group(name: str, x: int, y: int, children: list, visible: bool | None = None) -> dict:
    return {"type": "Widget", "name": name, "fields": _vis({"rect": {"x": x, "y": y}}, visible), "children": children}


def button(name: str, x: int, y: int, art: str, text: str = "", tooltip: str = "", pt: int = 18, colour="$TabsInactiveTextColor",
           scale: float | None = None, visible: bool | None = None) -> dict:
    r = {"x": x, "y": y}
    if scale is not None:
        r["scale"] = scale
    f = {"rect": r, "filename": art if "\\" in art else ART + art, "normalFrame": 0, "hoveredFrame": 1, "pressedFrame": 2,
         "disabledFrame": 3, "onClickMessage": CLICK}
    if text:
        f.update(textString=text, textColor=colour, pointSize=pt)
    if tooltip:
        f["tooltipString"] = tooltip
    return {"type": "ButtonWidget", "name": name, "fields": _vis(f, visible)}


def cell_group(name: str, x: int, y: int, art: str, frame: int, box: tuple[int, int], g: Geo, fill: tuple | None) -> dict:
    """A label + value cell: the cell art, the label, one value box per tone (the plugin fills the box of the row's tone and
    empties the others). `fill`: (label, value, tone) for a preview."""
    lw, vw = box
    kids = [img(name + "Cell", 0, 0, art, frame),
            tb(name + "Label", 8, g.label_dy, lw - 14, g.cell_h, fill[0] if fill else "", pt=g.label_pt, face="Formal", spacing=LABEL_SPACING)]
    for tone, colour in TONES:
        kids.append(tb(f"{name}Value{tone}", lw + 6, 0, vw - 12, g.cell_h, fill[1] if fill and fill[2] == tone else "",
                       colour, pt=g.value_pt))
    return group(name, x, y, kids, visible=fill is not None)


def line_widgets(i: int, x: int, y: int, g: Geo, line: tuple | None, samples) -> list[dict]:
    """Line slot i: SbLine<ii>Heading / Full / Left / Right, the one(s) of `line`'s kind visible (none without a preview)."""
    p = g.art
    n = f"SbLine{i:02d}"
    kind = line[0] if line else None
    head = group(n + "Heading", x, y, [img(n + "HeadingRule", 0, (g.cell_h - 9) // 2, p + "Rule"),
                                        tb(n + "HeadingText", 0, 0, full_w(g), g.cell_h, line[1] if kind == "heading" else "", GOLD,
                                           pt=g.heading_pt)], visible=kind == "heading")
    out = [head,
           cell_group(n + "Full", x, y, p + "FullCell", i % (6 if g.pad else 8), g.full, g, samples(line[1]) if kind == "full" else None),
           cell_group(n + "Left", x, y, p + "HalfCell", (2 * i) % (12 if g.pad else 16), g.half, g,
                      samples(line[1]) if kind == "pair" else None),
           cell_group(n + "Right", x + half_w(g) + g.half_gap, y, p + "HalfCell", (2 * i + 1) % (12 if g.pad else 16), g.half, g,
                      samples(line[2]) if kind == "pair" and line[2] else None)]
    return out


def tab_xy(i: int, g: Geo) -> tuple[int, int]:
    """Tab i's place: along the strip, or (side panel) down the column, tab 1 at the top."""
    if g is SIDE:
        return g.tab_x, g.tab_y + (i - 1) * (g.tab_h + g.tab_gap)
    return g.tab_x + i * (g.tab_w + g.tab_gap), g.tab_y


def line_xy(i: int, g: Geo) -> tuple[int, int]:
    if not g.pad:
        return g.cell_x, g.line_y + i * g.pitch
    return g.col_x[i // PAD_ROWS], g.line_y + (i % PAD_ROWS) * g.pitch


def all_xy(j: int, g: Geo) -> tuple[int, int]:
    per = g.all_rows // g.all_cols
    x = g.all_x if g.all_cols == 1 else g.col_x[j // per]
    return x, g.all_y + (j % per) * g.all_pitch


# ---- previews --------------------------------------------------------------------------------------------------------------
def sample_fill(r: list, k: int) -> tuple[str, str, str]:
    """A placeholder value for a row (label, value, tone): every fifth row zero (grey), else a made-up value in its format."""
    fmt, colour = r[3], r[4]
    zero = k % 5 == 4
    if fmt == "yesno":
        return r[1], "no" if zero else "yes", "Grey" if zero else COLOUR_TONE.get(colour, "White")
    if fmt == "block":
        return r[1], "42%", "White"
    vals = iter([0, 0] if zero else [25 + 7 * (k % 9), 75 + 3 * (k % 7)])
    v = re.sub(r"%(%|\+d|d)", lambda m: "%" if m.group(1) == "%" else (("+" if m.group(1) == "+d" else "") + str(next(vals))), fmt)
    return r[1], v, "Grey" if zero else COLOUR_TONE.get(colour, "White")


STAT_TEXTS: dict[int, str] = {}       # stat id -> its item line's text (a preview's All Stats rows; set by `build`)


def load_stat_texts(data: Path) -> None:
    """Each stat's item line text from the mod's itemstatcost (descstrpos) and strings, for preview rows only."""
    isc = data / "global" / "excel" / "itemstatcost.txt"
    if not isc.exists():
        return
    table = {}
    for p in sorted((data / "local" / "lng" / "strings").rglob("*.json")):
        try:
            rows = json.loads(p.read_text("utf-8-sig"))
        except ValueError:
            continue
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and "Key" in r and "enUS" in r:
                table.setdefault(r["Key"], r["enUS"])
    lines = isc.read_text("latin-1").splitlines()
    col = lines[0].split("\t").index("descstrpos")
    for i, ln in enumerate(lines[1:]):
        f = ln.split("\t")
        key = f[col] if len(f) > col else ""
        if key in table:
            STAT_TEXTS[i] = re.sub(r"\s+", " ", re.sub(r"%[+]?d%?|%%|\n|ÿc.", "", table[key])).strip()


def all_texts(book: dict) -> list[tuple[bool, str]]:
    """All Stats lines for a preview: (heading, text). A stat row's text is the game's item line: here "+25%" and the stat's
    description string (load_stat_texts), a range / value row its own English."""
    labels = {}                                  # a stat's label on a themed page, when the strings do not have it
    for _p, _t, recs in book["pages"]:
        for r in recs:
            if r[0] == "row" and r[2].split(",")[0].isdigit():
                labels.setdefault(int(r[2].split(",")[0]), r[1])
    out = []
    for heading, rows in book["all"]:
        out.append((True, heading))
        for f in rows:
            first = int(f[2].split(",")[0]) if f[2].split(",")[0].isdigit() else -1
            text = STAT_TEXTS.get(first) or labels.get(first)
            eng = f[4] if len(f) > 4 and f[4] != "-" else ("+25% " + text if text else f"stat {f[2]}")
            out.append((False, re.sub(r"%[+]?d", "25", eng).replace("%%", "%")))
    return out


def search(lines: list[tuple[bool, str]], q: str) -> list[tuple[int, int]]:
    """book_logic.h Search: (line index, match position or -1)."""
    out, i = [], 0
    ql = q.lower()
    while i < len(lines):
        head = i
        i += 1
        whole = bool(q) and ql in lines[head][1].lower()
        kept = []
        while i < len(lines) and not lines[i][0]:
            at = lines[i][1].lower().find(ql) if q else -1
            if whole or (q and at >= 0) or not q:
                kept.append((i, at))
            i += 1
        if kept:
            out.append((head, -1))
            out += kept
    return out


# ---- the layouts -----------------------------------------------------------------------------------------------------------
def statbook_widgets(book: dict, g: Geo, preview: int | None = None, query: str = "", pad_buttons: str = "bumpers") -> list[dict]:
    """Every Stat Book widget of one layout (top level, in drawing order)."""
    p = g.art
    tl = tabs(book)
    sel = 0 if preview is None else preview
    pt = tab_point_size([t for t, _ in tl], g)
    out: list[dict] = [{"type": "Widget", "name": MARKER, "fields": {"rect": {"x": 0, "y": 0}}}]
    kids = []
    for i, (label, title) in enumerate(tl):
        if g is SIDE and i == 0:            # the side panel has no Character tab: the sheet is beside it
            continue
        x, y = tab_xy(i, g)
        kids.append(button(f"SbTab{i}", x, y, p + "Tab", label, title, pt, colour=SIDE_TAB_TEXT if g is SIDE else "$TabsInactiveTextColor"))
        kids.append(img(f"SbTab{i}Selected", x, y, p + "TabSelected", visible=i == sel))
        if g is SIDE:                        # the gem side (right) is the page's: the label centred left of it
            kids.append(tb(f"SbTab{i}SelectedLabel", x, y, g.tab_w - 14, g.tab_h, label, "$TabsActiveTextColor", pt=pt, visible=i == sel))
        else:
            kids.append(tb(f"SbTab{i}SelectedLabel", x, y, g.tab_w, 73 - 14, label, "$TabsActiveTextColor", pt=pt, visible=i == sel))
    if g.pad:
        y = g.tab_y - 8
        for name, art, x, show in (("SbPadPrevLB", "BumperLeft", 20, pad_buttons == "bumpers"),
                                   ("SbPadPrevLT", "TriggerLeft", 25, pad_buttons == "triggers"),
                                   ("SbPadNextRB", "BumperRight", 2618, pad_buttons == "bumpers"),
                                   ("SbPadNextRT", "TriggerRight", 2623, pad_buttons == "triggers")):
            kids.append(img(name, x, y, f"Controller\\ControllerButtons\\xbox\\{art}", visible=show))
    out.append(group("StatBookTabs", 0, 0, kids))

    page = preview is not None and 1 <= preview <= len(book["pages"])
    is_all = preview is not None and preview == len(tl) - 1
    if g.body:
        x0, y0, _x1, _y1 = g.body
        out.append(img("SbPageBody", x0, y0, "PageBody", visible=page or is_all))
    else:
        out.append(img("SbPageBody", 0, 0, "Empty", visible=False))

    lines = page_lines(book["pages"][preview - 1][2]) if page else []
    k = iter(range(10 ** 6))
    page_kids = []
    for i in range(LINES):
        x, y = line_xy(i, g)
        page_kids += line_widgets(i, x, y, g, lines[i] if i < len(lines) else None, lambda r: sample_fill(r, next(k)))
    out.append(group("StatBookPage", 0, 0, page_kids, visible=page))

    out.append(group("StatBookAll", 0, 0, all_widgets(book, g, is_all, query), visible=is_all))
    if not g.pad:                            # the top / side toggle: icon only, the page's top-right corner on both hosts
        tx, ty = TOGGLE_SIDE if g is SIDE else TOGGLE_PC
        out.append(button("SbTabsToggle", tx, ty, "TabsToggleTop" if g is SIDE else "TabsToggleSide", tooltip=TOGGLE_TIP, visible=page or is_all or g is SIDE))
    if g.pad:
        out.append(group("SbPadAllHint", 2380, 1360, [img("SbPadAllHintGlyph", 0, 0, "Controller\\ControllerButtons\\xbox\\ButtonSelect",
                                                          scale=0.55),
                                                      tb("SbPadAllHintText", 56, 0, 280, 50, "All Stats", "$FontColorWhite", pt=20,
                                                         align="left")], visible=page or is_all))
    leaf_visibility(out)
    return out


def leaf_visibility(widgets: list[dict], shown: bool = True) -> None:
    """Every leaf's `visible` set to its own flag AND its groups' (a group's flag alone does not hide its children in game)."""
    for w in widgets:
        f = w.setdefault("fields", {})
        eff = shown and f.get("visible", True)
        if w.get("children"):
            leaf_visibility(w["children"], eff)
        else:
            f["visible"] = eff


def all_widgets(book: dict, g: Geo, show: bool, query: str) -> list[dict]:
    p = g.art
    kids = []
    slot_w, slot_h = round(742 * g.slot_scale), round(113 * g.slot_scale)
    lab_w = 150 if not g.pad else 220
    sx = g.all_x + lab_w + 10
    kids.append(tb("SbSearchLabel", g.all_x, g.search_y, lab_w, slot_h, "Search", GOLD, pt=g.heading_pt, align="right"))
    kids.append(img("SbSearchSlot", sx, g.search_y, "PANEL\\Modals\\InputSlot", scale=g.slot_scale))
    kids.append({"type": "InputTextBoxWidget", "name": "SbSearchInput",
                 "fields": {"rect": {"x": sx + round(36 * g.slot_scale), "y": g.search_y + round(14 * g.slot_scale),
                                     "width": round(681 * g.slot_scale), "height": round(75 * g.slot_scale)},
                            "backgroundColor": {"r": 0, "g": 0, "b": 0, "a": 0}, "maxStringLength": 32, "fontType": "8pt",
                            "imeEnabled": False,
                            "fontStyle": {"alignment": {"v": "center"}, "pointSize": "$MediumFontSize", "fontFace": "BlizzardGlobal"}}})
    texts = all_texts(book)
    shown = search(texts, query) if show else []
    rows = sum(1 for _h, _t in texts if not _h)
    kept = sum(1 for i, _a in shown if not texts[i][0])
    right = min(g.all_x + g.all_w, (TOGGLE_SIDE if g is SIDE else TOGGLE_PC)[0] - 10) if not g.pad else (g.col_x[1] + g.all_w)
    kids.append(tb("SbSearchCount", sx + slot_w + 10, g.search_y, right - (sx + slot_w + 10), slot_h,
                   f"{kept}/{rows}" if show else "", "$FontColorDarkGrayGold", pt=g.value_pt - 2, align="right"))
    kids.append(tb("SbPreviewQuery", sx + round(36 * g.slot_scale) + 6, g.search_y, round(681 * g.slot_scale), slot_h,
                   query if show else "", "$FontColorWhite", pt=g.label_pt, face="Formal", align="left", visible=bool(show and query)))
    go_scale = round((g.all_h - 6) / 63, 3)
    for j in range(g.all_rows):
        x, y = all_xy(j, g)
        n = f"SbAll{j:02d}"
        hit = shown[j] if j < len(shown) else None
        heading = hit is not None and texts[hit[0]][0]
        row = hit is not None and not heading
        text = texts[hit[0]][1] if hit else ""
        kids.append(group(n + "Heading", x, y, [img(n + "HeadingRule", 0, (g.all_h - 9) // 2, p + "AllRule"),
                                                 tb(n + "HeadingText", 0, 0, g.all_w, g.all_h, text if heading else "", GOLD,
                                                    pt=g.heading_pt)], visible=heading))
        at = hit[1] if row else -1
        tx, tw = 16, g.all_w - 16 - 8 - round(63 * go_scale) - 8
        # the highlight: three left-aligned boxes at one place, drawn in this order: the whole text (white), the text up to the
        # match's end (HIT, orange) over it, the text before the match (white) over that: before / match / after in their colours.
        kids.append(group(n + "Row", x, y, [
            img(n + "Cell", 0, 0, p + "AllCell", j % 6 if g.pad else j % 8),
            tb(n + "Text", tx, 0, tw, g.all_h, text if row else "", "$FontColorWhite", pt=g.label_pt, face="Formal", align="left"),
            tb(n + "Hit", tx, 0, tw, g.all_h, text[:at + len(query)] if at >= 0 else "", HIT, pt=g.label_pt, face="Formal", align="left"),
            tb(n + "Pre", tx, 0, tw, g.all_h, text[:at] if at > 0 else "", "$FontColorWhite", pt=g.label_pt, face="Formal", align="left"),
            button(n + "Go", g.all_w - 8 - round(63 * go_scale), 3, "PANEL\\Stash\\Stash_RightArrow", scale=go_scale)], visible=row))
    if g.track_x is not None:
        kids.append(img("SbAllScrollTrack", g.track_x, g.all_y, "ScrollTrack"))
        kids.append(img("SbAllScrollThumb", g.track_x + 5, g.all_y + 4, "PANEL\\AdvancedCharacterSheet\\AdvancedCharacterSheet_ScrollIndicator"))
    return kids


STATBOOK_PREFIXES = ("Sb", "StatBook")


def strip(lay: dict) -> dict:
    """The layout without Stat Book widgets (a rebuild over an earlier one)."""
    lay["children"] = [c for c in lay.get("children", []) if not str(c.get("name", "")).startswith(STATBOOK_PREFIXES)]
    for c in lay["children"]:          # a preview's hiding undone (D2R's sheet widgets have no `visible` of their own)
        if c.get("fields", {}).get("visible") is False:
            del c["fields"]["visible"]
            if not c["fields"]:          # LevelUpInfo has no fields of its own; a preview gave it {"visible": false}
                del c["fields"]
    return lay


def add(lay: dict, widgets: list[dict], before: str | None = "CloseButton") -> dict:
    kids = strip(lay)["children"]
    i = next((k for k, c in enumerate(kids) if c.get("name") == before), len(kids))
    kids[i:i] = widgets
    return lay


# D2R's own sheet widgets that stay on every page (the frame, the title band, the name / level / experience band, close, and
# the stat points line: D2R's code shows CombinedPointsInfo / LevelUpInfo every frame, over a layout's `visible: false`).
KEEP_ON_PAGES = {"Background", "ClickCatcher", "click_catcher", "LeftHinge", "StatsPanelTitle", "CharacterName", "FullClassInfo",
                 "XpProgress", "CombinedXP", "CloseButton", "LevelUpInfo", "CombinedPointsInfo"}


def hidden_on_pages(lay: dict) -> list[str]:
    """The top-level widgets of D2R's sheet (and sheetres' rows) the plugin hides on the themed pages and All Stats: all but
    KEEP_ON_PAGES and the Stat Book's own (docs/statbook-layout.md)."""
    return [c["name"] for c in lay.get("children", []) if c.get("name") and c["name"] not in KEEP_ON_PAGES
            and not c["name"].startswith(STATBOOK_PREFIXES)]


def preview_hide(lay: dict, preview: int | None) -> None:
    if preview:
        for c in lay["children"]:
            if c.get("name") in hidden_on_pages(lay):
                c.setdefault("fields", {})["visible"] = False


OFF_PANEL = -20000     # a preview's hidden D2R widgets are moved here (removing them could break D2R's panel code)


def preview_look(lay: dict) -> dict:
    """What a preview writes: in game a layout's `visible: false` does not hold on this panel (every widget is drawn; the
    plugin hides them at run time), so without the plugin a preview leaves out the Stat Book's hidden widgets and moves D2R's
    hidden ones off the panel. Dev screenshots only; `build` keeps the normal layout to go back to."""
    def prune(ws):
        out = []
        for w in ws:
            if w.get("fields", {}).get("visible") is False:
                continue
            if w.get("children"):
                w["children"] = prune(w["children"])
            out.append(w)
        return out
    kids = []
    for c in lay["children"]:
        name = str(c.get("name", ""))
        if name.startswith(STATBOOK_PREFIXES):
            kids += prune([c])
            continue
        if c.get("fields", {}).get("visible") is False and isinstance(c["fields"].get("rect"), dict):
            c["fields"]["rect"] = dict(c["fields"]["rect"], x=OFF_PANEL, y=OFF_PANEL)
        kids.append(c)
    lay["children"] = kids
    return lay


def pc_hd(lay: dict, book: dict, **kw) -> dict:
    """The PC HD sheet: the Stat Book widgets before the close button; D2R's title text goes (the tabs are the title)."""
    for c in lay["children"]:
        if c.get("name") == "StatsPanelTitle":
            c["fields"]["text"] = ""
    lay = add(lay, statbook_widgets(book, PC, **kw))
    preview_hide(lay, kw.get("preview"))
    return lay


def pad(lay: dict, book: dict, **kw) -> dict:
    lay = add(lay, statbook_widgets(book, PADG, **kw), before=None)
    preview_hide(lay, kw.get("preview"))
    return lay


SIDE_LOCAL_ID = "SbSidePanel"    # not starting with "StatBook" (see PLAIN_LOCAL_ID)
SIDE_NAME = "statbook/" + SIDE_LOCAL_ID
SIDE_FILE = "sidepanelhd.json"   # beside statbook-layout.json; the plugin registers it as the panel's layout


def side_layout(book: dict, preview: int | None = None, query: str = "") -> dict:
    """The side panel (option B): D2R's Advanced Stats place right of the sheet, the book's frame, its title, the page title
    row (SbSideHeading, the toggle at its right), the tabs down the left and the same lines and All Stats as on the sheet."""
    tl = tabs(book)
    kids = [img("SbSideBody", 0, 0, "SideBody"),
            tb("SbSideTitle", 0, 52, SIDE_W, 133 - 52, "Stat Book", "$FontColorWhite", pt=24, face="Formal"),
            tb("SbSideHeading", SIDE.cell_x, TOGGLE_SIDE[1], TOGGLE_SIDE[0] - 12 - SIDE.cell_x, TOGGLE, tl[preview][1] if preview else "", GOLD,
               pt=SIDE.heading_pt + 2, align="left")]
    kids += statbook_widgets(book, SIDE, preview=preview or None, query=query)
    leaf_visibility(kids)
    return {"type": "Panel", "name": SIDE_NAME,
            "fields": {"rect": {"x": SIDE_X, "y": SIDE_Y, "width": SIDE_W, "height": SIDE_H}, "anchor": {"x": 0.0, "y": 0.397},
                       "priority": 5},
            "children": kids}


# ---- the contract ----------------------------------------------------------------------------------------------------------
def contract_names(book: dict, pad_layout: bool = False) -> set[str]:
    """Every widget name the plugin binds to (docs/statbook-layout.md)."""
    names = {MARKER, "StatBookTabs", "StatBookPage", "StatBookAll", "SbPageBody",
             "SbSearchLabel", "SbSearchSlot", "SbSearchInput", "SbSearchCount"}
    for i in range(len(tabs(book))):
        names |= {f"SbTab{i}", f"SbTab{i}Selected", f"SbTab{i}SelectedLabel"}
    for i in range(LINES):
        n = f"SbLine{i:02d}"
        names |= {n + "Heading", n + "HeadingText", n + "HeadingRule"}
        for part in ("Full", "Left", "Right"):
            names |= {n + part, n + part + "Cell", n + part + "Label"} | {f"{n}{part}Value{t}" for t, _ in TONES}
    for j in range(PAD_ALL_ROWS if pad_layout else ALL_ROWS):
        n = f"SbAll{j:02d}"
        names |= {n + "Heading", n + "HeadingText", n + "HeadingRule", n + "Row", n + "Cell", n + "Text", n + "Hit", n + "Pre", n + "Go"}
    if not pad_layout:
        names.add("SbTabsToggle")
    if pad_layout:
        names |= {"SbPadPrevLB", "SbPadPrevLT", "SbPadNextRB", "SbPadNextRT", "SbPadAllHint", "SbPadAllHintGlyph", "SbPadAllHintText"}
    else:
        names |= {"SbAllScrollTrack", "SbAllScrollThumb"}
    return names


def contract_json(book: dict) -> dict:
    """Rects the plugin needs for clicks and the mouse wheel (panel units of each layout), written next to the layouts."""
    out = {}
    for key, g in (("pc", PC), ("pad", PADG), ("side", SIDE)):
        out[key] = {"tabs": [[0, 0, 0, 0] if g is SIDE and i == 0 else [*tab_xy(i, g), g.tab_w, g.tab_h if g is SIDE else 73]
                             for i in range(len(tabs(book)))],
                    "lines": LINES, "allRows": g.all_rows, "allColumns": g.all_cols,
                    "allRowRects": [[*all_xy(j, g), g.all_w, g.all_h] for j in range(g.all_rows)],
                    "lineRects": [[*line_xy(i, g), full_w(g), g.cell_h] for i in range(LINES)],
                    "search": [g.all_x, g.search_y, (min(g.all_w, (TOGGLE_SIDE if g is SIDE else TOGGLE_PC)[0] - 10 - g.all_x) if not g.pad
                                                      else g.col_x[1] + g.all_w - g.all_x), round(113 * g.slot_scale)],
                    "tones": [t for t, _ in TONES]}
        if not g.pad:
            out[key]["toggle"] = [*(TOGGLE_SIDE if g is SIDE else TOGGLE_PC), TOGGLE, TOGGLE]
    return out


# ---- plain D2R: the plugin's own panels ----------------------------------------------------------------------------------
# Plain D2R has no mod to carry the sheet layout and art, so the plugin registers panels of its own (HD only), both written
# from the mod's layouts here so they cannot drift from them (test_statbook_layout.py Plain): statbook/SbPlainPanel at the
# sheet's rect (the sheet's book, the mod's PC widgets) and statbook/SbSidePanel beside it (the side host, tabs = "side", the
# mod's sidepanelhd.json). The sheet host opens the first while the sheet is open (the second as on the mod), hides D2R's sheet
# widgets on the pages as on the mod's sheet and fills both the same way. The Stat Book's own sprites (PLAIN_OWN_ART: the tabs,
# the row cells and heading rules, the side panel's frame and tabs, the toggle) are read by D2R from the install's data like
# the mod's art; for each one the install does not hold, the host swaps in D2R's stock sprite (Fallback rows in the header: the
# stash tab scaled to the tab, a darkened body, the level-up button; a bare widget for a cell or rule, the row then text on the
# dark body). Everything else is D2R's stock sprites: the developer menu's input slot, the stash arrow, the Advanced Stats
# scroll bar, and the sheet's darkened body (the Advanced Stats cell's translucent centre, stacked).
PLAIN_HEADER = ROOT / "statbook" / "src" / "statbook_plain_layout.h"
PLAIN_LOCAL_ID = "SbPlainPanel"  # not starting with "StatBook": the click panel statbook/StatBook took its opens
PLAIN_NAME = "statbook/" + PLAIN_LOCAL_ID
PLAIN_TAB = "PANEL\\stash\\MKB_Tabs_195_TGA"           # 195 x 73, frames: inactive, active
PLAIN_SHADE = "PANEL\\AdvancedCharacterSheet\\AdvancedCharacterSheet_Cell"   # frame 4: 33 x 33 black at alpha 68
PLAIN_SHADE_LAYERS = 5
PLAIN_TRACK = "PANEL\\AdvancedCharacterSheet\\AdvancedCharacterSheet_ScrollBar"  # 36 x 1253
PLAIN_BUTTON = "PANEL\\Character_Sheet\\LevelUpButton"  # 83 x 84, frames: normal, hovered, pressed, disabled
PLAIN_CELLS = ("HalfCell", "FullCell", "AllCell", "Rule", "AllRule",
               "SideHalfCell", "SideFullCell", "SideAllCell", "SideRule", "SideAllRule")
PLAIN_OWN_ART = ("Tab", "TabSelected", *PLAIN_CELLS, "SideBody", "SideTab", "SideTabSelected", "TabsToggleSide", "TabsToggleTop")
PLAIN_PART = 12000     # characters per C++ raw string piece (MSVC: 16380 before concatenation)


def plain_book() -> dict:
    """The plain D2R book compiled into the plugin (statbook/src/default_book.inc)."""
    text = (ROOT / "statbook" / "src" / "default_book.inc").read_text("utf-8")
    return read_book(text[text.index('R"BOOK(') + 7:text.rindex(')BOOK"')])


def shade(name: str, x: int, y: int, w: int, h: int, visible) -> dict:
    """A w x h dark body from D2R's stock sprites: the Advanced Stats cell's translucent centre (a square) scaled to the
    shorter side, at both ends of the longer one, stacked PLAIN_SHADE_LAYERS times."""
    side = min(w, h)
    scale = round(side / 33, 4)
    ends = [(0, d) for d in (0, h - side)] if h >= w else [(d, 0) for d in (0, w - side)]
    shades = [img(f"{name}Shade{k}", dx, dy, PLAIN_SHADE, frame=4, scale=scale) for k, (dx, dy) in enumerate(ends * PLAIN_SHADE_LAYERS)]
    return group(name, x, y, shades, visible=visible)


def _plain_art(w: dict, g: Geo, stock: bool = False) -> dict | None:
    """One widget of the mod's layout (geometry g) for plain D2R: the Stat Book's own sprites stay (D2R's stock ones instead
    when `stock`), its other sprites become D2R's stock ones."""
    f = w.get("fields", {})
    fn = f.get("filename", "")
    art = fn[len(ART):] if fn.startswith(ART) else None
    if art == "Empty" or (art in PLAIN_CELLS and stock):  # a bare widget: the side panel's SbPageBody (it has no page body), a cell
        return {"type": "Widget", "name": w["name"], "fields": {"rect": {"x": 0, "y": 0}, "visible": art in PLAIN_CELLS and f.get("visible", True)}}
    if art in PLAIN_OWN_ART and not stock:
        pass
    elif art in ("Tab", "TabSelected", "SideTab", "SideTabSelected"):
        scale = round(g.tab_w / 195, 4)
        f["filename"] = PLAIN_TAB
        f["rect"]["scale"] = scale
        f["rect"]["y"] += round(((g.tab_h if g is SIDE else 73) - 73 * scale) / 2)
        if art in ("Tab", "SideTab"):
            f.update(normalFrame=0, hoveredFrame=0, pressedFrame=1, disabledFrame=0)
        else:
            f["frame"] = 1
    elif art in ("TabsToggleSide", "TabsToggleTop"):
        f["filename"] = PLAIN_BUTTON
        f["rect"]["scale"] = round(TOGGLE / 84, 4)
    elif art == "SideBody":
        return shade(w["name"], f["rect"]["x"], f["rect"]["y"], SIDE_W, SIDE_H, f.get("visible"))
    elif art == "ScrollTrack":
        f["filename"] = PLAIN_TRACK
        f["rect"]["scale"] = round(g.all_rows * g.all_pitch / 1253, 4)
    elif art == "PageBody":
        x0, y0, x1, y1 = g.body
        return shade(w["name"], x0, y0, x1 - x0, y1 - y0, f.get("visible"))
    if w.get("children"):
        w["children"] = [c for c in (_plain_art(k, g, stock) for k in w["children"]) if c is not None]
    return w


def plain_layout(book: dict, stock: bool = False) -> dict:
    """The plain D2R panel over the sheet: the mod's PC widgets in a Panel at the sheet's rect ($LeftPanelRect,
    $LeftPanelAnchor of _profilehd.json, written out)."""
    kids = [c for c in (_plain_art(w, PC, stock) for w in statbook_widgets(book, PC)) if c is not None]
    leaf_visibility(kids)
    return {"type": "Panel", "name": PLAIN_NAME,
            "fields": {"rect": {"x": 236, "y": -651, "width": 1162, "height": 1507}, "anchor": {"x": 0.0, "y": 0.397}, "priority": 5},
            "children": kids}


def plain_side_layout(book: dict, stock: bool = False) -> dict:
    """The plain D2R side panel: the mod's side panel (side_layout) with plain D2R's art."""
    lay = side_layout(book)
    kids = [c for c in (_plain_art(w, SIDE, stock) for w in lay["children"]) if c is not None]
    leaf_visibility(kids)
    lay["children"] = kids
    return lay


def _compact(o) -> str:
    return json.dumps(o, separators=(",", ":"), ensure_ascii=True)


def widgets_of(lay: dict) -> list[dict]:
    out = []
    for c in lay.get("children", []):
        out.append(c)
        out += widgets_of(c)
    return out


def art_fallback(book: dict) -> list[tuple[str, str, str]]:
    """(sprite file, own, stock) for every widget of both plain layouts with the Stat Book's own art: the host replaces the
    own JSON text with the stock one when the install has no data/hd/global/ui/panel/statbook/<file>."""
    out = []
    for make in (plain_layout, plain_side_layout):
        stock = {w.get("name"): w for w in widgets_of(make(book, stock=True))}
        for w in widgets_of(make(book)):
            fn = w.get("fields", {}).get("filename", "")
            if fn.startswith(ART) and fn[len(ART):] in PLAIN_OWN_ART:
                out.append((fn[len(ART):].lower() + ".sprite", _compact(w), _compact(stock[w["name"]])))
    return out


def _cpp_parts(text: str) -> str:
    parts = [text[i:i + PLAIN_PART] for i in range(0, len(text), PLAIN_PART)]
    assert all(")SBJSON\"" not in p for p in parts)
    return ",\n".join(f'    R"SBJSON({p})SBJSON"' for p in parts)


def plain_header_text() -> str:
    book = plain_book()
    hd, side = _compact(plain_layout(book)), _compact(plain_side_layout(book))
    rows = art_fallback(book)
    assert all(hd.count(own) + side.count(own) == 1 for _, own, _ in rows)
    fallback = ",\n".join(f'    {{"{f}", R"SBJSON({a})SBJSON", R"SBJSON({b})SBJSON"}}' for f, a, b in rows)
    c = contract_json(book)
    geo = json.dumps({"pc": c["pc"], "side": c["side"]}, separators=(",", ":"))
    return ("// Written by tools/statbook_layout.py (`py -3 -I tools/statbook_layout.py plain`) from the plain D2R book\n"
            "// (default_book.inc); tools/tests/test_statbook_layout.py checks it is current. The plain D2R panels: the book over\n"
            "// the sheet and the side panel (tabs = \"side\"), both from the mod's layouts.\n"
            "#pragma once\n\n"
            "namespace statbook_plain {\n\n"
            f'inline constexpr char PanelLocalId[] = "{PLAIN_LOCAL_ID}";\n'
            f'inline constexpr char PanelName[] = "{PLAIN_NAME}";\n'
            f'inline constexpr char SideLocalId[] = "{SIDE_LOCAL_ID}";\n'
            f"inline constexpr int TabCount = {len(tabs(book))};\n"
            "// the HD layouts in pieces (joined at load; HD only), and the click rectangles in statbook-layout.json's form\n"
            f"inline constexpr const char* LayoutHd[] = {{\n{_cpp_parts(hd)}}};\n"
            f"inline constexpr const char* SideLayoutHd[] = {{\n{_cpp_parts(side)}}};\n"
            f"inline constexpr const char* Geometry[] = {{\n{_cpp_parts(geo)}}};\n"
            "// the widgets with the Stat Book's own art: {sprite file, own, stock}; the stock text replaces the own one when the\n"
            "// install has no data/hd/global/ui/panel/statbook/<sprite file>\n"
            f"inline constexpr const char* Fallback[][3] = {{\n{fallback}}};\n\n"
            "}  // namespace statbook_plain\n")


# ---- build ---------------------------------------------------------------------------------------------------------------
def d2r_sprites(d2r: Path):
    import ui_art

    def get(rel: str):
        p = Path(d2r) / "data" / "hd" / "global" / "ui" / f"{rel}.sprite"
        if not p.exists():
            import fxpaths
            p = fxpaths.d2r_file(f"data/hd/global/ui/{rel}.sprite")
        return ui_art.read_sprite(p)
    return get


def plain_art(d2r: Path, data: Path) -> list[str]:
    """The Stat Book's own sprites a plain D2R install ships (PLAIN_OWN_ART and their .lowend copies) into
    data/hd/global/ui/panel/statbook, from D2R's HD sprites; the same pictures as the mod build's (book: every row kept)."""
    art = build_art(d2r_sprites(d2r), read_book(full_book_text()))
    return write_art({k: v for k, v in art.items() if k in PLAIN_OWN_ART}, data)


def load_book(data: Path, book_file: Path | None) -> dict:
    p = book_file or (data / BOOK)
    return read_book(p.read_text("utf-8") if p.exists() else full_book_text())


def tab_index(book: dict, preview: str | None) -> int | None:
    if preview is None:
        return None
    if preview.isdigit():
        return int(preview)
    ids = ["character"] + [p[0] for p in book["pages"]] + ["all"]
    return ids.index(preview)


# A preview build changes D2R's widgets for good (preview_look), so the layout it started from is kept beside the data (not in
# it: the mod folder is copied whole) and the next build starts from that again, unless the layout was rewritten since
# (a new sheet_resists build: the preview's own text is no longer there).
def _base_dir(data: Path) -> Path:
    return Path(data).resolve().parent / "statbook-preview-base"


def preview_base(data: Path, name: str, p: Path) -> str:
    text = p.read_text("utf-8-sig")
    b = _base_dir(data) / name
    mark = b.with_name(b.name + ".preview")
    if b.exists() and mark.exists() and mark.read_text("utf-8") == text:
        return b.read_text("utf-8")
    return text


def keep_preview_base(data: Path, name: str, base: str, preview: str) -> None:
    b = _base_dir(data) / name
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(base, "utf-8", newline="")
    b.with_name(b.name + ".preview").write_text(preview, "utf-8", newline="")


def drop_preview_base(data: Path, name: str) -> None:
    b = _base_dir(data) / name
    for f in (b, b.with_name(b.name + ".preview")):
        if f.exists():
            f.unlink()


def build(d2r: Path, data: Path, book_file: Path | None = None, preview: str | None = None, query: str = "",
          pad_buttons: str = "bumpers") -> list[str]:
    import pad_ui
    book = load_book(data, book_file)
    if preview is not None:
        load_stat_texts(data)
    kw = {"preview": tab_index(book, preview), "query": query, "pad_buttons": pad_buttons}
    report = []
    for name, edit in ((PC_HD, pc_hd), (PAD, pad)):
        p = data / LAYOUTS / name
        if not p.exists():
            raise SystemExit(f"{p} missing: run tools/sheet_resists.py build first")
        text = preview_base(data, name, p)
        lay = edit(pad_ui.load(text), book, **kw)
        if kw["preview"] is not None:
            out = json.dumps(preview_look(lay), indent=1, ensure_ascii=False) + "\n"
            keep_preview_base(data, name, text, out)
        else:
            out = json.dumps(lay, indent=1, ensure_ascii=False) + "\n"
            drop_preview_base(data, name)
        p.write_text(out, "utf-8", newline="")
        report.append(f"{name}: Stat Book tabs ({len(tabs(book))}), {LINES} line slots, All Stats"
                      + (f", PREVIEW tab {kw['preview']}" if kw["preview"] is not None else ""))
    art_stamp = data / ART_DIR / "art-stamp.txt"
    stamp = json.dumps([ART_VERSION, LINES, PC.__dict__, PADG.__dict__, SIDE.__dict__, TOGGLE, [t for t, _ in tabs(book)], rule_gap(book, PC)], sort_keys=True, default=str)
    if not art_stamp.exists() or art_stamp.read_text("utf-8") != stamp:
        names = write_art(build_art(d2r_sprites(d2r), book), data)
        art_stamp.write_text(stamp, "utf-8")
        report.append(f"hd/global/ui/panel/statbook: {len(names)} sprites")
    (data / ART_DIR / "statbook-layout.json").write_text(json.dumps(contract_json(book), indent=1) + "\n", "utf-8")
    (data / ART_DIR / SIDE_FILE).write_text(json.dumps(side_layout(book, kw["preview"], query), indent=1) + "\n", "utf-8")
    report.append(f"{ART_DIR.as_posix()}/{SIDE_FILE}: the side panel")
    probs = fit_problems(book, PC) + fit_problems(book, PADG) + fit_problems(book, SIDE)
    if probs:
        raise SystemExit("texts that do not fit: " + "; ".join(probs))
    return report


# ---- render (a PIL picture of a built layout, to compare with the mockups) -------------------------------------------------
def _profile(d2r: Path) -> dict:
    import pad_ui
    text = (Path(d2r) / "data" / LAYOUTS / "_profilehd.json").read_text("utf-8-sig")
    prof = pad_ui.load(re.sub(r"(,|\{|\[|^)([ \t]*)//[^\n]*", r"\1\2", text, flags=re.M))

    def res(v, depth=0):
        while isinstance(v, str) and v.startswith("$") and depth < 8:
            v, depth = prof.get(v[1:], v), depth + 1
        return v
    return {k: res(v) for k, v in prof.items()} | {"__res__": res}


def render(lay: dict, data: Path, d2r: Path, size: tuple[int, int], base=None):
    """The layout's widgets drawn with PIL (ImageWidgets, buttons with their labels, text boxes with D2R's fonts); `visible`
    respected. An approximation for side-by-side checks, not the game's renderer."""
    from PIL import Image, ImageDraw
    import ui_art
    prof = _profile(d2r)
    res = prof["__res__"]
    canvas = base.convert("RGBA") if base is not None else Image.new("RGBA", size, (0, 0, 0, 255))
    cache: dict = {}

    def sprite(fn: str, frame: int):
        rel = fn.replace("\\", "/").lower()
        if rel not in cache:
            for root in (data / "hd" / "global" / "ui", Path(d2r) / "data" / "hd" / "global" / "ui"):
                p = root / f"{rel}.sprite"
                if p.exists():
                    cache[rel] = ui_art.read_sprite(p)
                    break
            else:
                try:
                    cache[rel] = d2r_sprites(d2r)(rel)
                except SystemExit:
                    cache[rel] = None
        fr = cache[rel]
        return None if not fr else fr[min(frame, len(fr) - 1)]

    def colour(c):
        c = res(c)
        if isinstance(c, dict):
            return (c.get("r", 255), c.get("g", 255), c.get("b", 255))
        return (240, 240, 240)

    def text(x, y, w, h, s, style):
        if not s:
            return
        style = res(style) if isinstance(style, str) else style
        pt = res(style.get("pointSize", 22))
        pt = pt if isinstance(pt, (int, float)) else 22
        f = font("Formal" if style.get("fontFace") == "Formal" else "", pt)
        if f is None:
            return
        al = style.get("alignment", {})
        tw = f.getlength(s)
        tx = x if al.get("h") == "left" else (x + w - tw if al.get("h") == "right" else x + (w - tw) / 2)
        asc, desc = f.getmetrics()
        ty = y + (h - (asc + desc)) / 2
        ImageDraw.Draw(canvas).text((tx, ty), s, font=f, fill=colour(style.get("fontColor", "$FontColorWhite")))

    def walk(node, ox, oy):
        f = node.get("fields", {})
        if f.get("visible") is False:
            return
        r = f.get("rect", {})
        r = res(r) if isinstance(r, str) else r
        x, y = ox + r.get("x", 0), oy + r.get("y", 0)
        t = node.get("type")
        if t in ("ImageWidget", "ButtonWidget") and f.get("filename"):
            fr = sprite(res(f["filename"]), f.get("frame", f.get("normalFrame", 0)) or 0)
            if fr is not None:
                sc = r.get("scale", 1)
                if sc != 1:
                    fr = fr.resize((max(1, round(fr.width * sc)), max(1, round(fr.height * sc))))
                canvas.alpha_composite(fr.convert("RGBA"), (int(x), int(y)))
                if t == "ButtonWidget" and f.get("textString"):
                    text(x, y, fr.width, fr.height - 14, f["textString"], {"pointSize": f.get("pointSize", 22),
                                                                            "fontColor": f.get("textColor", "$FontColorWhite"),
                                                                            "alignment": {"h": "center"}})
        elif t == "TextBoxWidget":
            txt = f.get("text", "")
            if isinstance(txt, str) and not txt.startswith("@"):
                text(x, y, r.get("width", 0), r.get("height", 0), txt, f.get("style", {}))
        for c in node.get("children", []):
            walk(c, x, y)
    for c in lay.get("children", []):
        walk(c, 0, 0)
    return canvas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["build", "render", "plain", "art"])
    ap.add_argument("--d2r", type=Path, default=None)
    ap.add_argument("--mod", type=Path, default=ROOT / "work" / "mod" / "data")
    ap.add_argument("--book", type=Path, default=None)
    ap.add_argument("--preview", default=None)
    ap.add_argument("--query", default="")
    ap.add_argument("--pad-buttons", choices=["bumpers", "triggers"], default="bumpers")
    ap.add_argument("--out", type=Path, default=ROOT / "work" / "statbook-render")
    ap.add_argument("--data", type=Path, default=ROOT / "work" / "statbook-art", help="art: the data folder the sprites go under")
    a = ap.parse_args(argv)
    if a.cmd == "plain":
        PLAIN_HEADER.write_text(plain_header_text(), "utf-8", newline="\n")
        print(PLAIN_HEADER)
        return 0
    if a.d2r is None:
        import fxpaths
        a.d2r = Path(fxpaths.D2R)
    if a.cmd == "art":
        names = plain_art(a.d2r, a.data)
        print(f"{(a.data / ART_DIR).as_posix()}: {len(names)} sprites (+ .lowend)")
        return 0
    if a.cmd == "build":
        for line in build(a.d2r, a.mod, a.book, a.preview, a.query, a.pad_buttons):
            print(line)
        return 0
    import pad_ui
    import ui_art
    a.out.mkdir(parents=True, exist_ok=True)
    pc = pad_ui.load((a.mod / LAYOUTS / PC_HD).read_text("utf-8"))
    bg = ui_art.read_sprite(a.mod / "hd" / "global" / "ui" / "panel" / "character_sheet" / "character_background.sprite")[0]
    render(pc, a.mod, a.d2r, bg.size, bg).save(a.out / "pc.png")
    pd = pad_ui.load((a.mod / LAYOUTS / PAD).read_text("utf-8"))
    pbg = d2r_sprites(a.d2r)("controller/panel/charactersheet/v2/charactersheet_bg")[0]
    from PIL import Image
    base = Image.new("RGBA", (pbg.width, pbg.height + 140), (10, 10, 10, 255))
    base.alpha_composite(pbg.convert("RGBA"), (0, 140))
    shifted = {"children": [group("_", 0, 140, pd["children"])]}
    render(shifted, a.mod, a.d2r, base.size, base).save(a.out / "pad.png")
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
