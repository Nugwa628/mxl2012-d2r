"""The Stat Book in D2R's legacy (classic) graphics: the classic character sheet layout with the book's tabs, page lines and All
Stats, the classic side panel, and their DC6 art (docs/statbook.md, docs/statbook-layout.md "Legacy").

D2R picks the layout by graphics mode (characterstatspanel.json in legacy, characterstatspanelhd.json in HD), so the legacy sheet
gets the same contract widgets (statbook_layout.contract_names, the same names and groups: the plugin's WidgetService handles are
paths and outlive a graphics switch) with classic rects, classic fonts (fontType 6pt / 8pt) and explicit RGB colours (_profilesd
has no yellow, orange or gold-yellow).

The classic sheet stays 320 x 432 at $LeftPanelAnchor (rect -320, -240): D2R draws a classic left panel only inside the classic
panel area (80, 60, 320, 432 of 800 x 600) whatever the layout's rect says (a widened sheet was cut there in game), so the book
fits that area:
  head        TAB_H high tab strip over the sheet's frame top and name / class boxes; the name / class row moved below it (the
              SbHead picture: the sheet's own name and class boxes, the class box narrower for the top / side toggle)
  tabs        widths from their font6 labels (tab art: D2R's HD stash tab down-rendered, as D2R's own classic stash tabs, the
              name drawn into the art); short labels when the full ones do not fit
  page body   320 x 363 below the header band (D2R's level / experience boxes and texts stay): the Stat Book's HD stone page
              down-rendered
  lines       LINES slots from LINE_Y, PITCH apart: heading (8pt gold, a gold rule), full row or two half rows (the sheet's
              resistance box: title cell and value cell, nine-sliced)
  All Stats   a search row (classic InputTextBoxWidget) and ALL_ROWS rows with a Go arrow (D2R's classic buysell arrow)
  SbAdvanced  a classic Advanced Stats arrow (D2R's HD button down-rendered) right of the stat points plate: it opens All
              Stats (a Stat Book click; the plugin finds it by its rect, `advanced` in statbook-layout.json)
The side panel (statbook/SbSidePanel, classic layout `sidepanel.json` beside the HD one) is the same page as its own panel in
the classic right panel area (400, 60), its tabs along its top (no Character tab): a 4:3 screen has no room for a tab column
beside the sheet.

  py -3 -I tools/statbook_legacy.py build [--d2r EXTRACT] [--mod DATA] [--book FILE]
  py -3 -I tools/statbook_legacy.py preview [--mod DATA] [--out DIR] [--tab N] [--query TEXT]   PNGs of the built layouts
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import statbook_layout as sl  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEGACY = "characterstatspanel.json"
SIDE_FILE = "sidepanel.json"            # beside sidepanelhd.json (statbook_layout.SIDE_FILE)
ART_DIR = Path("global") / "ui" / "panel" / "statbook"
ART = "PANEL\\StatBook\\"
MARKER = "SbLegacyMarker"
ADVANCED_NAME = "SbAdvanced"            # not D2R's own name: as AdvancedStats the classic arrow never sent its click in game
INVCHAR = Path("global") / "ui" / "panel" / "invchar6.dc6"

PANEL_W, PANEL_H = 320, 432             # D2R's classic sheet (and the area D2R draws a classic left panel in)
TAB_H = 18                              # the tab strip
NAME_Y, NAME_H = TAB_H + 1, 14          # the name / class row below it (in the sheet's art at y 9, 15 high)
NAME_BOX, CLASS_BOX = (10, 171), (194, 98)    # x, width
HEAD_H = 33                             # the SbHead picture: the strip and the name / class row
HEADER_H = 69                           # the sheet's header band (with the level / experience boxes) in its art
BODY = (6, HEADER_H, PANEL_W - 6, PANEL_H - 4)   # the page's stone inside the frame
LINE_X, LINE_W = 6, 308
LINE_Y, PITCH, CELL_H = 77, 14, 13
FULL = (190, 118)                       # label cell, value cell
VALUE_PAD = 4                           # a value's room from its bar's ends (right-aligned)
HALF = (104, 50)
HALF_GAP = LINE_W - 2 * sum(HALF)
ALL_Y, ALL_ROWS = 93, 21
SEARCH_LABEL_W = 44
# The search box right of D2R's stat point buttons (the Strength + at 125-147, 76-98 is under the All Stats row): D2R hit-tests
# the hidden All Stats page's input box too, and over the + it took the Strength + clicks on the Character tab. The count left.
PLUS_RIGHT = 150
SEARCH_SLOT = (PLUS_RIGHT, LINE_X + LINE_W - PLUS_RIGHT)  # x, width
SEARCH = (SEARCH_SLOT[0], LINE_Y, SEARCH_SLOT[1], CELL_H)   # the click that types into the box (sheet_host SearchBox)
GO = 13                                 # the All Stats row's arrow (square)
TOGGLE = 14
TOGGLE_XY = (CLASS_BOX[0] + CLASS_BOX[1] + 4, NAME_Y)   # right of the class box
ADVANCED = (142, 340, 26)               # x, y, height: between the stat points plate (3-138) and the resistance boxes (172)
CLOSE = (128, 388, 32, 32)              # D2R's close button
SIDE_X = 320                            # the side panel's corner from the sheet's: the classic right panel area
LABEL_FONT, VALUE_FONT, HEAD_FONT = "6pt", "6pt", "8pt"   # values: font8 is taller than a 13 pixel bar
TAB_FONT = "font6"
TAB_TEXT = ((253, 253, 253), (199, 179, 119))  # inactive, active (D2R's classic stash tab text)
GOLD = {"r": 199, "g": 179, "b": 119, "a": 255}
WHITE = {"r": 255, "g": 255, "b": 255, "a": 255}
NOTE = {"r": 173, "g": 168, "b": 148, "a": 255}
HIT = {"r": 255, "g": 168, "b": 0, "a": 255}
# book_logic.h Tone, in its order (statbook_layout.TONES): the classic look's RGB, bright on the dark bars (HD's grey for a
# zero value is near white here: a darker grey could not be read on them)
TONE_RGB = {"White": (255, 255, 255), "Grey": (215, 215, 215), "Red": (255, 80, 80), "Blue": (130, 140, 255), "Yellow": (255, 255, 100),
            "Purple": (60, 220, 60), "Magic": (255, 168, 0), "Gold": (199, 179, 119), "ItemBlue": (120, 120, 255), "Green": (0, 252, 0)}
SHORT_TABS = {"Character": "Char", "All Stats": "All"}   # when the full names do not fit the strip
SHORTER_TABS = {"Character": "Char", "Offense": "Off", "Spells": "Spell", "Defense": "Def", "Resistances": "Res", "Resist": "Res",
                "Skills": "Skill", "Utility": "Util", "All Stats": "All"}   # when the short ones do not fit either
TAB_PAD = 10                            # the least room round a tab's label


def rgb(c: tuple[int, int, int]) -> dict:
    return {"r": c[0], "g": c[1], "b": c[2], "a": 255}


# ---- geometry --------------------------------------------------------------------------------------------------------------
def tab_labels(book: dict, side: bool) -> list[tuple[str, str]]:
    """(label as drawn, tooltip) per tab of the book (the side panel leaves tab 0 out)."""
    return [(t, title) for i, (t, title) in enumerate(sl.tabs(book)) if not (side and i == 0)]


def tab_boxes(widths: list[int], total: int = PANEL_W, x0: int = 0) -> list[tuple[int, int]]:
    """(x, width) per tab: each label's ink plus an equal share of the strip's rest."""
    pad = (total - sum(widths)) // len(widths)
    out, x = [], x0
    for k, w in enumerate(widths):
        tw = w + pad + (total - sum(widths) - pad * len(widths) if k == len(widths) - 1 else 0)
        out.append((x, tw))
        x += tw
    return out


def tab_texts(book: dict, side: bool, width) -> list[str]:
    """The upper-case label per tab: the full names, else Character / All Stats short, else every name short (SHORTER_TABS, or
    its first four letters), whichever first leaves TAB_PAD round each label."""
    names = [t for t, _ in tab_labels(book, side)]
    tries = [[n.upper() for n in names], [SHORT_TABS.get(n, n).upper() for n in names],
             [SHORTER_TABS.get(n, n[:4]).upper() for n in names]]
    for labels in tries:
        if sum(width(n) for n in labels) + TAB_PAD * len(labels) <= PANEL_W:
            return labels
    return tries[-1]


def line_xy(i: int) -> tuple[int, int]:
    return LINE_X, LINE_Y + i * PITCH


def all_xy(j: int) -> tuple[int, int]:
    return LINE_X, ALL_Y + j * PITCH


def geometry(book: dict, boxes: list[tuple[int, int]], side: bool) -> dict:
    """statbook-layout.json's "legacy" / "legacyside" (statbook_layout.contract_json's keys; panel units of the classic layout)."""
    n = len(sl.tabs(book))
    tabs = [[0, 0, 0, 0]] * n
    for k, (x, w) in enumerate(boxes):
        tabs[k + (1 if side else 0)] = [x, 0, w, TAB_H]
    return {"tabs": tabs, "lines": sl.LINES, "allRows": ALL_ROWS, "allColumns": 1,
            "allRowRects": [[*all_xy(j), LINE_W, CELL_H] for j in range(ALL_ROWS)],
            "lineRects": [[*line_xy(i), LINE_W, CELL_H] for i in range(sl.LINES)],
            "search": list(SEARCH), "tones": [t for t, _ in sl.TONES], "toggle": [*TOGGLE_XY, TOGGLE, TOGGLE],
            "origin": [SIDE_X if side else 0, 0], **({} if side else {"advanced": [ADVANCED[0], ADVANCED[1], 24, ADVANCED[2]]})}


# ---- widgets ---------------------------------------------------------------------------------------------------------------
def r(x: int, y: int, w: int | None = None, h: int | None = None) -> dict:
    out = {"x": x, "y": y}
    if w is not None:
        out.update(width=w, height=h)
    return out


def text(name: str, x: int, y: int, w: int, h: int, s: str = "", colour: dict = WHITE, font: str = LABEL_FONT, align: str = "center",
         visible: bool | None = None) -> dict:
    f = {"rect": r(x, y, w, h), "text": s, "fontType": font,
         "style": {"fontColor": colour, "alignment": {"h": align, "v": "center"}}}
    return {"type": "TextBoxWidget", "name": name, "fields": sl._vis(f, visible)}


def image(name: str, x: int, y: int, art: str, frame: int = 0, visible: bool | None = None) -> dict:
    return {"type": "ImageWidget", "name": name, "fields": sl._vis({"rect": r(x, y), "filename": ART + art, "frame": frame}, visible)}


def group(name: str, x: int, y: int, kids: list, visible: bool | None = None) -> dict:
    return {"type": "Widget", "name": name, "fields": sl._vis({"rect": r(x, y)}, visible), "children": kids}


def button(name: str, x: int, y: int, art: str, frames: tuple[int, int], tooltip: str = "", message: str = sl.CLICK,
           visible: bool | None = None) -> dict:
    f = {"rect": r(x, y), "filename": ART + art, "normalFrame": frames[0], "hoveredFrame": frames[0], "pressedFrame": frames[1],
         "disabledFrame": frames[0], "onClickMessage": message}
    if tooltip:
        f["tooltipString"] = tooltip
    return {"type": "ButtonWidget", "name": name, "fields": sl._vis(f, visible)}


CELL_FRAMES = {"FullL": 0, "FullV": 1, "HalfL": 2, "HalfV": 3, "AllA": 4, "AllB": 5, "Slot": 6, "Rule": 7}
ALL_SPLIT = 256                         # the All Stats row's box: two frames (a DC6 frame of a widget is drawn whole up to 256)


def cell(name: str, x: int, y: int, box: tuple[int, int], kind: str, fill) -> dict:
    lw, vw = box
    kids = [group(name + "Cell", 0, 0, [image(name + "CellL", 0, 0, "Cells", CELL_FRAMES[kind + "L"]),
                                         image(name + "CellV", lw, 0, "Cells", CELL_FRAMES[kind + "V"])]),
            text(name + "Label", 3, 0, lw - 4, CELL_H, fill[0] if fill else "", align="left")]
    for tone, _c in sl.TONES:
        kids.append(text(f"{name}Value{tone}", lw + VALUE_PAD, 0, vw - 2 * VALUE_PAD, CELL_H, fill[1] if fill and fill[2] == tone else "",
                         rgb(TONE_RGB[tone]), VALUE_FONT, "right"))
    return group(name, x, y, kids, visible=fill is not None)


def heading(name: str, x: int, y: int, w: int, s: str, show: bool) -> dict:
    # the rule's line (its frame's bottom row) in the gap below the row, clear of the heading's text
    return group(name + "Heading", x, y, [group(name + "HeadingRule", 0, 1, [image(name + "HeadingRuleA", 0, 0, "Cells", CELL_FRAMES["Rule"]),
                                                                                     image(name + "HeadingRuleB", w // 2, 0, "Cells", CELL_FRAMES["Rule"])]),
                                          text(name + "HeadingText", 0, -1, w, CELL_H, s, GOLD, HEAD_FONT)], visible=show)


def line_widgets(i: int, line, samples) -> list[dict]:
    x, y = line_xy(i)
    n = f"SbLine{i:02d}"
    kind = line[0] if line else None
    return [heading(n, x, y, LINE_W, line[1] if kind == "heading" else "", kind == "heading"),
            cell(n + "Full", x, y, FULL, "Full", samples(line[1]) if kind == "full" else None),
            cell(n + "Left", x, y, HALF, "Half", short_fill(samples(line[1])) if kind == "pair" else None),
            cell(n + "Right", x + sum(HALF) + HALF_GAP, y, HALF, "Half", short_fill(samples(line[2])) if kind == "pair" and line[2] else None)]


def short_labels() -> dict[str, str]:
    """sheet_host_logic.h ShortLabels: the plugin draws a half row's label on the legacy sheet in its short form from them."""
    import re
    text = (ROOT / "statbook" / "src" / "sheet_host_logic.h").read_text("utf-8")
    body = re.search(r"ShortLabels\[\]\[2\] = \{(.*?)\n\};", text, re.S).group(1)
    return dict(re.findall(r'\{"([^"]*)", "([^"]*)"\}', body))


def short_label(s: str) -> str:
    return short_labels().get(s, s)


def short_fill(fill):
    return (short_label(fill[0]), *fill[1:]) if fill else fill


def all_widgets(book: dict, show: bool, query: str) -> list[dict]:
    kids = [text("SbSearchLabel", SEARCH_SLOT[0] - 4 - SEARCH_LABEL_W, LINE_Y, SEARCH_LABEL_W, CELL_H, "SEARCH", GOLD, align="right"),
            image("SbSearchSlot", SEARCH_SLOT[0], LINE_Y, "Cells", CELL_FRAMES["Slot"]),
            {"type": "InputTextBoxWidget", "name": "SbSearchInput",
             "fields": {"rect": r(SEARCH_SLOT[0] + 3, LINE_Y + 1, SEARCH_SLOT[1] - 6, CELL_H - 2), "fontType": LABEL_FONT,
                        "backgroundColor": {"r": 0, "g": 0, "b": 0, "a": 0}, "maxStringLength": 32, "imeEnabled": False}}]
    texts = sl.all_texts(book)
    shown = sl.search(texts, query) if show else []
    rows = sum(1 for h, _t in texts if not h)
    kept = sum(1 for i, _a in shown if not texts[i][0])
    cw = SEARCH_SLOT[0] - 8 - SEARCH_LABEL_W - LINE_X
    kids.append(text("SbSearchCount", LINE_X + 2, LINE_Y, cw, CELL_H, f"{kept}/{rows}" if show else "", NOTE, align="left"))
    kids.append(text("SbPreviewQuery", SEARCH_SLOT[0] + 4, LINE_Y, SEARCH_SLOT[1] - 8, CELL_H, query if show else "", align="left",
                     visible=bool(show and query)))
    tw = LINE_W - 4 - GO - 6
    for j in range(ALL_ROWS):
        x, y = all_xy(j)
        n = f"SbAll{j:02d}"
        hit = shown[j] if j < len(shown) else None
        head = hit is not None and texts[hit[0]][0]
        row = hit is not None and not head
        s = texts[hit[0]][1] if hit else ""
        kids.append(heading(n, x, y, LINE_W, s if head else "", head))
        at = hit[1] if row else -1
        kids.append(group(n + "Row", x, y, [
            group(n + "Cell", 0, 0, [image(n + "CellA", 0, 0, "Cells", CELL_FRAMES["AllA"]),
                                     image(n + "CellB", ALL_SPLIT, 0, "Cells", CELL_FRAMES["AllB"])]),
            text(n + "Text", 4, 0, tw, CELL_H, s if row else "", align="left"),
            text(n + "Hit", 4, 0, tw, CELL_H, s[:at + len(query)] if at >= 0 else "", HIT, align="left"),
            text(n + "Pre", 4, 0, tw, CELL_H, s[:at] if at > 0 else "", align="left"),
            button(n + "Go", LINE_W - GO - 2, 0, "Go", (0, 1))], visible=row))
    kids.append({"type": "Widget", "name": "SbAllScrollTrack", "fields": {"rect": r(0, 0)}})
    kids.append({"type": "Widget", "name": "SbAllScrollThumb", "fields": {"rect": r(0, 0)}})
    return kids


def book_widgets(book: dict, boxes: list[tuple[int, int]], side: bool, preview: int | None = None, query: str = "") -> list[dict]:
    """The contract widgets of one classic layout (top level, in drawing order)."""
    sel = 0 if preview is None else preview
    out: list[dict] = [{"type": "Widget", "name": sl.MARKER, "fields": {"rect": r(0, 0)}},
                       {"type": "Widget", "name": MARKER, "fields": {"rect": r(0, 0)}}]
    page = preview is not None and 1 <= preview <= len(book["pages"])
    is_all = preview is not None and preview == len(sl.tabs(book)) - 1
    stone = [image(f"SbPageBody{k}", x0, y0, "Body" if y0 == 0 else "BodyLow", k % 2) for k, (x0, y0, _x1, _y1) in enumerate(body_tiles())]
    if side:
        band = [image(f"SbSideBand{k}", x0, 0, "Band", k) for k, x0 in enumerate((0, 256))]
        out.append(group("SbSideBody", 0, 0, [{"type": "ClickCatcherWidget", "name": "SbCatch", "fields": {"rect": r(0, 0, PANEL_W, PANEL_H)}}]
                         + band + [group("SbSideStone", 0, HEADER_H, stone)]))
        out.append(text("SbSideTitle", NAME_BOX[0], NAME_Y - 3, NAME_BOX[1], NAME_H, "Stat Book", WHITE, HEAD_FONT))
        out.append(text("SbSideHeading", 10, 36, PANEL_W - 20, 30, sl.tabs(book)[preview][1] if preview else "", GOLD, HEAD_FONT))
    body = [{"type": "ClickCatcherWidget", "name": "SbCatch", "fields": {"rect": r(0, 0, PANEL_W, PANEL_H - HEADER_H)}}] + stone
    tabs = []
    labels = tab_labels(book, side)
    for k, (x, w) in enumerate(boxes):
        i = k + (1 if side else 0)
        tabs.append(button(f"SbTab{i}", x, 0, "Tabs", (2 * k, 2 * k + 1), labels[k][1]))
        tabs.append(image(f"SbTab{i}Selected", x, 0, "TabsSelected", k, visible=i == sel))
        tabs.append({"type": "Widget", "name": f"SbTab{i}SelectedLabel", "fields": sl._vis({"rect": r(x, 0)}, i == sel)})
    out.append(group("StatBookTabs", 0, 0, tabs))
    if not side:
        out.append(group("SbPageBody", 0, HEADER_H, body, visible=page or is_all))
    else:   # as in HD: a bare SbPageBody (the side host hides it), the stone is part of SbSideBody
        out.append({"type": "Widget", "name": "SbPageBody", "fields": sl._vis({"rect": r(0, 0)}, False)})
    lines = sl.page_lines(book["pages"][preview - 1][2]) if page else []
    k = iter(range(10 ** 6))
    page_kids = []
    for i in range(sl.LINES):
        page_kids += line_widgets(i, lines[i] if i < len(lines) else None, lambda row: sl.sample_fill(row, next(k)))
    out.append(group("StatBookPage", 0, 0, page_kids, visible=page))
    out.append(group("StatBookAll", 0, 0, all_widgets(book, is_all, query), visible=is_all))
    out.append(button("SbTabsToggle", *TOGGLE_XY, "TabsToggle", (2, 3) if side else (0, 1), sl.TOGGLE_TIP, visible=page or is_all or side))
    sl.leaf_visibility(out)
    return out


STONE_H = PANEL_H - HEADER_H
# One DC6 per frame height: D2R draws a classic ImageWidget's frame bottom-aligned to the DC6's frame 0 (seen in game: a
# 33-high frame of a DC6 whose frame 0 is 256 high came out 223 lower). Body / BodyLow: the stone's upper and lower tiles;
# Band: the side panel's header band (strip, name row, level boxes); Head: the sheet's SbHead (strip and name / class row).


def body_tiles() -> list[tuple[int, int, int, int]]:
    """The page body's DC6 frames 0-3 (x0, y0, x1, y1 in the 320 x STONE_H stone): 256 wide at most."""
    out = []
    for y0, y1 in ((0, 256), (256, STONE_H)):
        out += [(0, y0, 256, y1), (256, y0, PANEL_W, y1)]
    return out


def head_widget() -> dict:
    """The sheet's head picture (drawn before D2R's texts, so its name and class stay on top)."""
    return group("SbHead", 0, 0, [image(f"SbHead{k}", x0, 0, "Head", k) for k, x0 in enumerate((0, 256))])


def advanced_button() -> dict:
    x, y, _h = ADVANCED
    f = {"rect": r(x, y), "filename": ART + "Advanced", "normalFrame": 0, "hoveredFrame": 0, "pressedFrame": 1, "disabledFrame": 0,
         "onClickMessage": sl.CLICK, "tooltipString": "Advanced Stats"}
    return {"type": "ButtonWidget", "name": ADVANCED_NAME, "fields": f}


# ---- the layouts -----------------------------------------------------------------------------------------------------------
def name_row(lay: dict) -> dict:
    """D2R's name and class texts moved into the row below the tab strip (classic 8pt: the row is NAME_H high)."""
    for c in lay.get("children", []):
        box = {"CharacterName": NAME_BOX, "ClassInfo": CLASS_BOX}.get(c.get("name"))
        if box:
            f = c.setdefault("fields", {})
            f["rect"] = r(box[0], NAME_Y - 3, box[1], NAME_H)    # classic text sits low in its box
            f["fontType"] = HEAD_FONT
            f.get("style", {}).pop("pointSize", None)
    return lay


def strip(lay: dict) -> dict:
    lay = sl.strip(lay)
    lay["children"] = [c for c in lay["children"] if c.get("name") != "AdvancedStats"]
    return lay


def without_catcher(body: dict) -> dict:
    """The sheet's page body without its ClickCatcher. D2R hit-tests the widgets of a hidden group too (a ClickCatcher, and
    buttons as well: seen in game, check statbook_legacy_points), so the page body's ClickCatcher took every click on D2R's
    stat point buttons (LevelUpInfo, drawn under it) on the Character tab: no stat point could be spent in legacy graphics
    (player report, 2026-11-21). As in HD (its page body has none) and the plain D2R panel. D2R shows LevelUpInfo every
    frame, so it stays under the page stone; on a page a click where a + sits still reaches it, as in HD."""
    return {**body, "children": [c for c in body["children"] if c["type"] != "ClickCatcherWidget"]}


def legacy_sheet(lay: dict, book: dict, boxes, preview: int | None = None, query: str = "") -> dict:
    lay = name_row(strip(lay))
    kids = lay["children"]
    i = next((k + 1 for k, c in enumerate(kids) if c.get("name") == "background"), 0)
    kids[i:i] = [head_widget()]
    i = next((k for k, c in enumerate(kids) if c.get("name") == "CloseButton"), len(kids))
    # the arrow after the book: D2R hit-tests the hidden page body's ClickCatcher too, which ate the arrow's clicks (the page
    # body has none any more, without_catcher; the arrow stays after the book)
    book_kids = [without_catcher(w) if w["name"] == "SbPageBody" else w for w in book_widgets(book, boxes, False, preview, query)]
    kids[i:i] = book_kids + [advanced_button()]
    if preview:
        for c in kids:
            if c.get("name") in hidden_on_pages(lay):
                c.setdefault("fields", {})["visible"] = False
    return lay


# D2R's classic widgets that stay on the pages: the header texts (on the page body's copy of the header band) and close.
KEEP_ON_PAGES = {"background", "CharacterName", "ClassInfo", "LevelTitle", "Level", "CurrentXPTitle", "CurrentXP", "NextLevelXPText", "NextLevelXP",
                 "CloseButton"}


def hidden_on_pages(lay: dict) -> list[str]:
    return [c["name"] for c in lay.get("children", []) if c.get("name") and c["name"] not in KEEP_ON_PAGES
            and not c["name"].startswith(sl.STATBOOK_PREFIXES)]


def side_layout(book: dict, boxes, preview: int | None = None, query: str = "") -> dict:
    kids = book_widgets(book, boxes, True, preview, query)
    for t in kids:
        if t.get("name") == "StatBookTabs":     # the side tabs' own art (no Character tab)
            for b in t["children"]:
                if b["fields"].get("filename", "").endswith(("\\Tabs", "\\TabsSelected")):
                    b["fields"]["filename"] = b["fields"]["filename"].replace("\\Tabs", "\\SideTabs")
    return {"type": "Panel", "name": sl.SIDE_NAME,
            "fields": {"rect": r(0, -240, PANEL_W, PANEL_H), "anchor": "$RightPanelAnchor", "priority": 5},
            "children": kids}


def contract_names(book: dict) -> set[str]:
    """The contract (statbook_layout.contract_names, PC) and the legacy layout's own: its marker and the Advanced Stats arrow."""
    extra = {n for n in sl.contract_names(book) if n.startswith("SbAll") and n[5:7].isdigit() and int(n[5:7]) >= ALL_ROWS}
    return (sl.contract_names(book) - extra) | {MARKER, ADVANCED_NAME}


# ---- art -------------------------------------------------------------------------------------------------------------------
def _box(src, w: int, h: int, corner: int = 3):
    import invtabs_art
    return invtabs_art.nine_slice(src, w, h, corner)


def sheet_picture(data: Path, pal):
    """Set 0 of the mod's classic sheet (320 x 432 RGBA)."""
    import ui_art
    return ui_art.panel_sets(data / INVCHAR, pal)[0].convert("RGBA")


def body_picture(sheet, stone):
    """(stone, band, head): the 320 x STONE_H page below the header band (the HD page stone down-rendered inside the sheet's own
    frame), the side panel's 320 x HEADER_H band and the sheet's 320 x HEAD_H head (the sheet's frame top, its name and class
    boxes moved down to the name row, the class box narrower for the toggle)."""
    import rotw_stash_legacy as rsl
    page = sheet.crop((0, HEADER_H, PANEL_W, PANEL_H))
    x0, y0, x1, y1 = BODY
    page.paste(rsl.down(stone, x1 - x0, y1 - y0), (x0, 0))
    head = sheet.crop((0, 0, PANEL_W, HEAD_H))
    head.paste(sheet.crop((0, HEAD_H - 9, PANEL_W, HEAD_H)), (0, NAME_Y - 4))      # the stone between the boxes, lower
    head.paste(sheet.crop((0, HEAD_H - 9, PANEL_W, HEAD_H)), (0, HEAD_H - 9))
    head.paste(_box(sheet.crop((8, 7, 185, 26)), NAME_BOX[1] + 4, NAME_H + 1), (NAME_BOX[0] - 2, NAME_Y - 1))
    head.paste(_box(sheet.crop((192, 7, 313, 26)), CLASS_BOX[1] + 4, NAME_H + 1), (CLASS_BOX[0] - 2, NAME_Y - 1))
    band = sheet.crop((0, 0, PANEL_W, HEADER_H))
    band.paste(head, (0, 0))
    return page, band, head


def cell_frames(sheet):
    """The row boxes from the sheet's Fire Resistance box (title cell x 172-270, value cell 272-313, rows 329-351)."""
    from PIL import Image
    title, value = sheet.crop((172, 329, 271, 351)), sheet.crop((270, 329, 313, 351))
    frames = {"FullL": _box(title, FULL[0], CELL_H), "FullV": _box(value, FULL[1], CELL_H),
              "HalfL": _box(title, HALF[0], CELL_H), "HalfV": _box(value, HALF[1], CELL_H)}
    whole = _box(title, LINE_W, CELL_H)
    frames["AllA"], frames["AllB"] = whole.crop((0, 0, ALL_SPLIT, CELL_H)), whole.crop((ALL_SPLIT, 0, LINE_W, CELL_H))
    frames["Slot"] = _box(value, SEARCH_SLOT[1], CELL_H)
    rim = value.getpixel((value.width // 2, 0))
    rule = Image.new("RGBA", (LINE_W // 2, CELL_H))       # the line at the bottom: every frame of a DC6 is CELL_H high
    rule.paste(Image.new("RGBA", (LINE_W // 2, 1), rim), (0, CELL_H - 1))   # (D2R draws a frame bottom-aligned to frame 0)
    frames["Rule"] = rule
    return [frames[k] for k, _v in sorted(CELL_FRAMES.items(), key=lambda kv: kv[1])]


def tab_frames(hd_tabs, font, labels: list[str], boxes, pal):
    """Normal and pressed frame per tab (Tabs.dc6), selected per tab (TabsSelected.dc6): D2R's HD stash tab down-rendered to the
    strip's height, its middle stretched to the tab's width, the label drawn into it."""
    import numpy as np
    from PIL import Image, ImageEnhance
    import rotw_stash_legacy as rsl
    hw = round(hd_tabs[0].width * TAB_H / hd_tabs[0].height)
    small = [rsl.down(t, hw, TAB_H) for t in hd_tabs[:2]]

    def fit(im, w):
        cap = 10
        out = Image.new("RGBA", (w, TAB_H))
        out.paste(im.crop((0, 0, cap, TAB_H)), (0, 0))
        out.paste(im.crop((cap, 0, hw - cap, TAB_H)).resize((w - 2 * cap, TAB_H), Image.LANCZOS), (cap, 0))
        out.paste(im.crop((hw - cap, 0, hw, TAB_H)), (w - cap, 0))
        return out

    def labelled(im, s, colour, dy=0):
        base = rsl.quantise(im, pal)
        t = font.render(s, colour)
        layer = Image.new("RGBA", im.size)
        layer.alpha_composite(t, ((im.width - t.width) // 2, (TAB_H - t.height) // 2 + 1 + dy))
        ink = np.asarray(layer.getchannel("A")) >= 128
        base[ink] = rsl.quantise(layer, pal, dither=False)[ink]
        return base

    normal, selected = [], []
    for s, (_x, w) in zip(labels, boxes):
        n = fit(small[0], w)
        normal.append(labelled(n, s, TAB_TEXT[0]))
        normal.append(labelled(ImageEnhance.Brightness(n).enhance(0.7), s, TAB_TEXT[0], 1))
        selected.append(labelled(fit(small[1], w), s, TAB_TEXT[1]))
    return normal, selected


HD_SOURCES = ("PageBody", "TabsToggleSide", "TabsToggleTop")   # the Stat Book's HD sprites the classic art is drawn from


def mod_hd_art(data: Path) -> dict[str, list]:
    """HD_SOURCES as the mod build wrote them (statbook_layout.py build)."""
    import ui_art
    return {k: ui_art.read_sprite(data / sl.ART_DIR / f"{k.lower()}.sprite") for k in HD_SOURCES}


def build_art(d2r, sheet, hd: dict, book: dict, boxes, side_boxes) -> dict[str, list]:
    """name -> DC6 frames (palette index arrays). `sheet`: set 0 of the classic sheet (RGBA); `hd`: HD_SOURCES, name -> frames."""
    import dc6
    import rotw_stash_legacy as rsl
    import ui_art
    pal = d2r.pal
    q = lambda im, dither=True: rsl.quantise(im, pal, dither)  # noqa: E731
    page, band, head = body_picture(sheet, hd["PageBody"][0].convert("RGBA"))
    halves = lambda im: [im.crop((0, 0, 256, im.height)), im.crop((256, 0, PANEL_W, im.height))]  # noqa: E731
    tiles = [q(page.crop(b), False) for b in body_tiles()]
    art = {"Body": tiles[:2], "BodyLow": tiles[2:], "Band": [q(f, False) for f in halves(band)], "Head": [q(f, False) for f in halves(head)],
           "Cells": [q(f, False) for f in cell_frames(sheet)]}
    font = d2r.font(TAB_FONT)
    hd_tabs = d2r.sprite("panel/stash/mkb_tabs_195_tga")
    tops = tab_texts(book, False, font.width)
    sides = tab_texts(book, True, font.width)
    n, s = tab_frames(hd_tabs, font, tops, boxes, pal)
    sn, ss = tab_frames(hd_tabs, font, sides, side_boxes, pal)
    art["Tabs"], art["TabsSelected"] = n, s
    art["SideTabs"], art["SideTabsSelected"] = sn, ss
    toggles = []
    for f in ("TabsToggleSide", "TabsToggleTop"):
        t = [im.convert("RGBA") for im in hd[f]]
        toggles += [q(rsl.down(t[0], TOGGLE, TOGGLE)), q(rsl.down(t[min(2, len(t) - 1)], TOGGLE, TOGGLE))]
    art["TabsToggle"] = toggles
    adv = d2r.sprite("panel/character_sheet/advancedstatsbutton")
    ah = ADVANCED[2]
    aw = round(adv[0].width * ah / adv[0].height)
    backing = _box(sheet.crop((270, 329, 313, 351)), aw + 4, ah)   # the sheet's value box: D2R hit-tests a classic button's
    arrows = []                                                     # ink, so the hollow arrow gets a solid box under it
    for k in (0, min(2, len(adv) - 1)):
        b = backing.copy()
        b.alpha_composite(rsl.down(adv[k], aw, ah), (2, 0))
        arrows.append(q(b))
    art["Advanced"] = arrows
    frames = dc6.read_dc6(_stock(d2r, "global/ui/panel/buysellbtn.dc6"))
    arrows = []
    for k in (14, 15):
        w, h, _ox, _oy, block = frames[k]
        arrows.append(q(rsl.down(ui_art.to_image(dc6.decode_frame(w, h, block, pal)).convert("RGBA"), GO, GO)))
    art["Go"] = arrows
    return art


def _stock(d2r, rel: str) -> Path:
    p = d2r.data / rel
    if p.exists():
        return p
    import fxpaths
    return fxpaths.d2r_file("data/" + rel)


def write_art(art: dict, data: Path) -> list[str]:
    import rotw_stash_legacy as rsl
    out = data / ART_DIR
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for name, frames in art.items():
        for f in frames:
            if f.min() < 0 or f.max() > 224:
                raise ValueError(f"{name}: palette index outside 0..224")
        (out / f"{name.lower()}.dc6").write_bytes(rsl.dc6_bytes(frames))
        names.append(name)
    return names


# ---- fit -------------------------------------------------------------------------------------------------------------------
def fit_problems(book: dict, font6, font8) -> list[str]:
    """Labels and sample values wider than their boxes in the classic fonts (font6 labels and values, font8 headings)."""
    probs = []
    for _pid, _title, recs in book["pages"]:
        for ln in sl.page_lines(recs):
            if ln[0] == "heading":
                if font8.width(ln[1]) > LINE_W - 4:
                    probs.append(f"heading {ln[1]!r}")
                continue
            box = FULL if ln[0] == "full" else HALF
            for row in ln[1:]:
                if not row:
                    continue
                label = row[1] if box is FULL else short_label(row[1])
                if font6.width(label) > box[0] - 4:
                    probs.append(f"label {label!r} {font6.width(label)} > {box[0] - 4}")
                v = sl.value_sample(row[3])
                if font6.width(v) > box[1] - 2 * VALUE_PAD:
                    probs.append(f"value {v!r} of {row[1]!r} {font6.width(v)} > {box[1] - 2 * VALUE_PAD}")
    return probs


# ---- build -----------------------------------------------------------------------------------------------------------------
def build(d2r_root: Path, data: Path, book_file: Path | None = None, preview: int | None = None, query: str = "") -> list[str]:
    import pad_ui
    import rotw_stash_legacy as rsl
    d2r = rsl.D2R(Path(d2r_root), use_cache=True)
    book = sl.load_book(data, book_file)
    if preview is not None:
        sl.load_stat_texts(data)
    font6, font8 = d2r.font("font6"), d2r.font("font8")
    if font6 is None or font8 is None:
        raise SystemExit("D2R's classic fonts font6 / font8 not found (fxpaths.d2r_file)")
    tops = tab_texts(book, False, font6.width)
    sides = tab_texts(book, True, font6.width)
    boxes = tab_boxes([font6.width(t) for t in tops])
    side_boxes = tab_boxes([font6.width(t) for t in sides])
    p = data / sl.LAYOUTS / LEGACY
    if not p.exists():
        raise SystemExit(f"{p} missing: run tools/sheet_resists.py build first")
    lay = legacy_sheet(pad_ui.load(p.read_text("utf-8-sig")), book, boxes, preview, query)
    p.write_text(json.dumps(lay, indent=1, ensure_ascii=False) + "\n", "utf-8", newline="")
    report = [f"{LEGACY}: Stat Book tabs ({len(boxes)}), {sl.LINES} line slots, All Stats, Advanced Stats arrow"]
    hd_dir = data / sl.ART_DIR
    side = side_layout(book, side_boxes, preview, query)
    (hd_dir / SIDE_FILE).write_text(json.dumps(side, indent=1) + "\n", "utf-8")
    report.append(f"{(sl.ART_DIR / SIDE_FILE).as_posix()}: the classic side panel")
    gp = hd_dir / "statbook-layout.json"
    geo = json.loads(gp.read_text("utf-8"))
    geo["legacy"] = geometry(book, boxes, False)
    geo["legacyside"] = geometry(book, side_boxes, True)
    gp.write_text(json.dumps(geo, indent=1) + "\n", "utf-8")
    names = write_art(build_art(d2r, sheet_picture(data, d2r.pal), mod_hd_art(data), book, boxes, side_boxes), data)
    report.append(f"{ART_DIR.as_posix()}: {len(names)} DC6")
    probs = fit_problems(book, font6, font8)
    if probs:
        raise SystemExit("texts that do not fit the legacy sheet: " + "; ".join(probs))
    return report


# ---- plain D2R: the standalone plugin's own classic panels ---------------------------------------------------------------
# Plain D2R keeps its own classic sheet (no mod layout to add the book to), so the plugin registers a classic layout for its
# own panel over the sheet (statbook_layout.PLAIN_NAME: D2R picks <localId>.json in legacy, <localId>hd.json in HD) and one for
# the side panel. The panel over the sheet is the mod's classic book (book_widgets) with what the mod gets from its sheet
# drawn on top: the head picture, the name and class texts (the host fills them) and, on the pages (inside SbPageBody, which
# covers D2R's own), the close button. No ClickCatcher (as the plain HD panel): on the Character tab the hidden page body would
# take the clicks of D2R's stat buttons below. Its art is the mod's, drawn from D2R's stock classic sheet and HD sprites.
PLAIN_HEADER = ROOT / "statbook" / "src" / "statbook_plain_legacy.h"
PLAIN_NAME_TEXT, PLAIN_CLASS_TEXT = "SbPlainName", "SbPlainClass"


def plain_sheet(book: dict, boxes, preview: int | None = None) -> dict:
    kids = [head_widget(),
            text(PLAIN_NAME_TEXT, NAME_BOX[0], NAME_Y - 3, NAME_BOX[1], NAME_H, "", WHITE, HEAD_FONT),
            text(PLAIN_CLASS_TEXT, CLASS_BOX[0], NAME_Y - 3, CLASS_BOX[1], NAME_H, "", WHITE, HEAD_FONT)]
    for w in book_widgets(book, boxes, False, preview):
        if w["name"] == "SbPageBody":
            x, y, _w, _h = CLOSE
            w["children"] = [c for c in w["children"] if c["type"] != "ClickCatcherWidget"]
            w["children"].append({"type": "ButtonWidget", "name": "SbClose", "fields": {
                "rect": r(x, y - HEADER_H), "filename": "PANEL\\buysellbtn", "normalFrame": 10, "hoveredFrame": 10, "pressedFrame": 11,
                "disabledFrame": 10, "onClickMessage": "CharacterStatsPanelMessage:Close", "tooltipString": "@strClose"}})
        kids.append(w)
    kids.append(advanced_button())
    return {"type": "Panel", "name": sl.PLAIN_NAME,
            "fields": {"rect": r(-PANEL_W, -240, PANEL_W, PANEL_H), "anchor": "$LeftPanelAnchor", "priority": 5},
            "children": kids}


def plain_parts(d2r_root: Path):
    """(d2r, book, boxes, side_boxes) of the plain D2R book."""
    import rotw_stash_legacy as rsl
    d2r = rsl.D2R(Path(d2r_root), use_cache=True)
    f6 = d2r.font("font6")
    if f6 is None:
        raise SystemExit("D2R's classic font font6 not found (fxpaths.d2r_file)")
    book = sl.plain_book()
    boxes = tab_boxes([f6.width(t) for t in tab_texts(book, False, f6.width)])
    side_boxes = tab_boxes([f6.width(t) for t in tab_texts(book, True, f6.width)])
    return d2r, book, boxes, side_boxes


def plain_art_names(lays) -> list[str]:
    """The DC6 files (lower case) the plain classic layouts name."""
    names = set()
    for lay in lays:
        for w in sl.widgets_of(lay):
            fn = w.get("fields", {}).get("filename", "")
            if fn.startswith(ART):
                names.add(fn[len(ART):].lower() + ".dc6")
    return sorted(names)


def plain_header_text(d2r_root: Path) -> str:
    _d2r, book, boxes, side_boxes = plain_parts(d2r_root)
    sheet, side = plain_sheet(book, boxes), side_layout(book, side_boxes)
    geo = json.dumps({"legacy": geometry(book, boxes, False), "legacyside": geometry(book, side_boxes, True)}, separators=(",", ":"))
    files = ", ".join(f'"{n}"' for n in plain_art_names((sheet, side)))
    return ("// Written by D2R-XL 2012's tools/statbook_legacy.py (`py -3 -I tools/statbook_legacy.py plain`) from the plain D2R\n"
            "// book (default_book.inc) and D2R's classic fonts. The plain D2R panels in legacy graphics: the book over D2R's classic\n"
            "// sheet and the classic side panel, both the mod's classic layouts; their art is data/global/ui/panel/statbook/*.dc6.\n"
            "#pragma once\n\n"
            "namespace statbook_plain {\n\n"
            f'inline constexpr char NameText[] = "{PLAIN_NAME_TEXT}";\n'
            f'inline constexpr char ClassText[] = "{PLAIN_CLASS_TEXT}";\n'
            "// the classic layouts in pieces (joined at load), and the click rectangles in statbook-layout.json's form\n"
            f"inline constexpr const char* LayoutLegacy[] = {{\n{sl._cpp_parts(sl._compact(sheet))}}};\n"
            f"inline constexpr const char* SideLayoutLegacy[] = {{\n{sl._cpp_parts(sl._compact(side))}}};\n"
            f"inline constexpr const char* GeometryLegacy[] = {{\n{sl._cpp_parts(geo)}}};\n"
            "// the art they name (data/global/ui/panel/statbook/): without all of it legacy graphics keep D2R's own sheet\n"
            f"inline constexpr const char* LegacyArt[] = {{{files}}};\n\n"
            "}  // namespace statbook_plain\n")


def plain_art(d2r_root: Path, data: Path) -> list[str]:
    """The plain classic layouts' DC6 art into data/global/ui/panel/statbook: the mod's pictures, drawn from D2R's stock
    classic sheet (invchar6.dc6) and the Stat Book's HD sprites as statbook_layout.plain_art draws them."""
    d2r, book, boxes, side_boxes = plain_parts(d2r_root)
    hd = sl.build_art(sl.d2r_sprites(d2r_root), sl.read_book(sl.full_book_text()))
    import ui_art
    sheet = ui_art.panel_sets(_stock(d2r, INVCHAR.as_posix()), d2r.pal)[0].convert("RGBA")
    return write_art(build_art(d2r, sheet, {k: hd[k] for k in HD_SOURCES}, book, boxes, side_boxes), data)


# ---- preview (a PIL picture of a built classic layout) ---------------------------------------------------------------------
def render(lay: dict, data: Path, d2r, base=None):
    """The layout drawn with PIL: DC6 images, buttons (normal frame), text boxes in the classic fonts; `visible` respected."""
    from PIL import Image
    import dc6
    import ui_art
    fonts = {"6pt": d2r.font("font6"), "8pt": d2r.font("font8"), "16pt": d2r.font("font16")}
    cache: dict = {}

    def frame(fn: str, k: int):
        key = (fn, k)
        if key not in cache:
            rel = fn.replace("\\", "/").lower() + ".dc6"
            p = data / "global" / "ui" / rel
            if not p.exists():
                try:
                    p = _stock(d2r, "global/ui/" + rel)
                except SystemExit:
                    cache[key] = None
                    return None
            fr = dc6.read_dc6(p)
            if k >= len(fr):
                cache[key] = None
                return None
            w, h, _ox, _oy, block = fr[k]
            cache[key] = ui_art.to_image(dc6.decode_frame(w, h, block, d2r.pal)).convert("RGBA")
        return cache[key]

    rect = lay["fields"]["rect"]
    out = base.copy() if base is not None else Image.new("RGBA", (rect["width"], rect["height"]), (20, 20, 20, 255))

    def walk(ws, ox, oy):
        for w in ws:
            f = w.get("fields", {})
            if f.get("visible") is False:
                continue
            rr = f.get("rect", {})
            if not isinstance(rr, dict) or not all(isinstance(rr.get(k, 0), int) for k in ("x", "y")):
                continue
            x, y = ox + rr.get("x", 0), oy + rr.get("y", 0)
            t = w.get("type")
            if t == "ImageWidget" and "filename" in f:
                im = frame(f["filename"], f.get("frame", 0))
                if im is not None:
                    out.alpha_composite(im, (x, y))
            elif t == "ButtonWidget" and "filename" in f:
                im = frame(f["filename"], f.get("normalFrame", 0))
                if im is not None:
                    out.alpha_composite(im, (x, y))
            elif t == "TextBoxWidget" and f.get("text") and not f["text"].startswith("@"):
                fnt = fonts.get(f.get("fontType", "16pt")) or fonts["8pt"]
                c = f.get("style", {}).get("fontColor", WHITE)
                c = (c["r"], c["g"], c["b"]) if isinstance(c, dict) else (255, 255, 255)
                im = fnt.render(f["text"], c)
                al = f.get("style", {}).get("alignment", {}).get("h", "left")
                bw, bh = rr.get("width", im.width), rr.get("height", im.height)
                tx = x if al == "left" else x + bw - im.width if al == "right" else x + (bw - im.width) // 2
                out.alpha_composite(im, (max(0, tx), max(0, y + (bh - im.height) // 2)))
            if w.get("children"):
                walk(w["children"], x, y)
    walk(lay.get("children", []), 0, 0)
    return out


def preview(data: Path, d2r_root: Path, out: Path, tab: int, query: str = "") -> list[Path]:
    """PNGs (2x) of the sheet and the side panel at tab `tab`, from the built book (no plugin: sample values)."""
    import pad_ui
    import rotw_stash_legacy as rsl
    from PIL import Image
    d2r = rsl.D2R(Path(d2r_root), use_cache=True)
    book = sl.load_book(data, None)
    sl.load_stat_texts(data)
    f6 = d2r.font("font6")
    boxes = tab_boxes([f6.width(t) for t in tab_texts(book, False, f6.width)])
    side_boxes = tab_boxes([f6.width(t) for t in tab_texts(book, True, f6.width)])
    lay = pad_ui.load((data / sl.LAYOUTS / LEGACY).read_text("utf-8-sig"))
    lay = legacy_sheet(lay, book, boxes, tab, query)
    if tab:
        lay["children"] = [c for c in lay["children"] if c.get("fields", {}).get("visible") is not False]
    sheet = sheet_picture(data, d2r.pal)
    base = Image.new("RGBA", (PANEL_W, PANEL_H), (20, 20, 20, 255))
    base.alpha_composite(sheet, (0, 0))
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    im = render(lay, data, d2r, base)
    p = out / f"legacy_sheet_tab{tab}.png"
    im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(p)
    paths.append(p)
    side = side_layout(book, side_boxes, tab or 1, query)
    im = render(side, data, d2r)
    p = out / f"legacy_side_tab{tab or 1}.png"
    im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(p)
    paths.append(p)
    return paths


def plain_preview(data: Path, d2r_root: Path, out: Path, tab: int) -> list[Path]:
    """PNG (2x) of the plain classic panel at tab `tab` over D2R's stock classic sheet (DC6s from plain-art in `data`)."""
    from PIL import Image
    import ui_art
    d2r, book, boxes, _side = plain_parts(d2r_root)
    sheet = ui_art.panel_sets(_stock(d2r, INVCHAR.as_posix()), d2r.pal)[0].convert("RGBA")
    lay = plain_sheet(book, boxes, tab)
    lay["children"][1]["fields"]["text"], lay["children"][2]["fields"]["text"] = "SbPlain", "Amazon"
    base = Image.new("RGBA", (PANEL_W, PANEL_H), (20, 20, 20, 255))
    base.alpha_composite(sheet, (0, 0))
    im = render(lay, data, d2r, base)
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"plain_legacy_tab{tab}.png"
    im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(p)
    return [p]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["build", "preview", "plain", "plain-art", "plain-preview"])
    ap.add_argument("--d2r", type=Path, default=None)
    ap.add_argument("--mod", type=Path, default=ROOT / "work" / "mod" / "data")
    ap.add_argument("--book", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "work" / "statbook-legacy-preview")
    ap.add_argument("--tab", type=int, default=1)
    ap.add_argument("--query", default="")
    ap.add_argument("--data", type=Path, default=ROOT / "work" / "statbook-art", help="plain-art: the data folder the DC6s go under")
    a = ap.parse_args(argv)
    if a.d2r is None:
        import fxpaths
        a.d2r = Path(fxpaths.D2R)
    if a.cmd == "plain":
        PLAIN_HEADER.write_text(plain_header_text(a.d2r), "utf-8", newline="\n")
        print(PLAIN_HEADER)
        return 0
    if a.cmd == "plain-art":
        names = plain_art(a.d2r, a.data)
        print(f"{(a.data / ART_DIR).as_posix()}: {len(names)} DC6")
        return 0
    if a.cmd == "plain-preview":
        for p in plain_preview(a.data, a.d2r, a.out, a.tab):
            print(p)
        return 0
    if a.cmd == "build":
        for line in build(a.d2r, a.mod, a.book):
            print(line)
        return 0
    for p in preview(a.mod, a.d2r, a.out, a.tab, a.query):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
