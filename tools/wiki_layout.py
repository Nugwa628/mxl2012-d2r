"""The wiki panel's layout (plugin part `wiki`, plugin/src/wiki.cpp, docs/wiki-panel.md): HD graphics only.

One native D2R panel, `mxl2012-core/Wiki`, most of the screen wide: a title, the search box, one row of category buttons, a result list on
the left (one arrow button per row, the page line and its two arrows under it) and the selected entry's text on the right (one line of
text boxes per line, an arrow button beside each line for the lines that are links, the "Lines a-b of n" line and its two scroll arrows
under it), a Back button and one status line. The texts are empty TextBoxWidgets the plugin fills through D2R's own text setter, as the
developer menu does (tools/devmenu_layout.py, whose art sizes and measured text widths are used here). `Metrics` holds how many rows,
lines and characters fit, and the rectangles the plugin needs for the mouse wheel and the search box.

Colours. D2R's text setter does not read colour codes inside a text (seen in game: `ÿc4` is drawn as written, with and without the style
option `pipeCharacterBehavior`), and a text box has one colour, set by its style. So every detail line is a stack of text boxes at the same
place, one per colour of the content table (`DetailText<line>_<colour>`), and the plugin fills the one of the line's colour and empties the
others. A result row is two boxes for its name (`RowText<row>_0` white, `RowText<row>_1` yellow for the selected row) and a grey one,
right-aligned, for its subtitle (`RowSub<row>`). `LineMark<line>` is a small gold box left of a detail line for the search-hit marker.

Fonts. The rows and the entry's lines use D2R's `Formal` face (mixed case, the face of its own long texts); the default face draws capitals
only and is kept for the title, the labels and the two foot lines.

The category buttons' labels are not known here: they are the content table's (`C` lines of wiki.tsv), so each button's label is the
placeholder `@C<n>@`, which the plugin replaces before it registers the layout (slot 0 is "All"; unused slots are hidden).

There is no classic layout: the plugin does not open the panel in classic graphics.

Every button sends the same message, `PanelManager:OpenPanel:mxl2012-core/WikiB_0`, a panel name registered by the plugin (D2R hands
PanelManager messages to UI listeners only for known panels, and allows a plugin 64 such names: the developer menu's one name per button
does not fit this panel's 66 buttons). The plugin finds the button from where the click was: `ButtonRects` holds each button's rectangle
in the order of `BUTTONS`; the rectangles do not overlap (tools/tests/test_wiki_layout.py).

  py -3 -I tools/wiki_layout.py header     write plugin/src/mxl_wiki_layout.h (committed; tools/tests/test_wiki_layout.py checks it is current)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import devmenu_layout as dev  # noqa: E402  (art sizes, measured text widths)

ROOT = Path(__file__).resolve().parent.parent
HEADER = ROOT / "plugin" / "src" / "mxl_wiki_layout.h"

PANEL = "mxl2012-core/Wiki"
PANEL_LOCAL_ID = "Wiki"
INPUT = "WikiInput"
TITLE = "D2R-XL 2012 Wiki"

CATEGORY_SLOTS = 11          # "All" and the ten categories of the content table
ROWS = 22                    # result rows a page
LINES = 27                   # detail lines
ARROW = 64                   # PANEL\Stash\Stash_LeftArrow / RightArrow, one frame, at scale 1
ROW_ARROW_SCALE = 0.75       # 48: the result rows' arrows
LINE_ARROW_SCALE = 0.625     # 40: the arrows beside link lines

# The content table's colours (wiki_logic.h Colour, in its order) as D2R's HD tooltip colours (_profilehd.json).
COLOURS = [("white", (240, 240, 240)), ("grey", (148, 148, 148)), ("blue", (110, 110, 255)), ("gold", (199, 179, 119)), ("green", (0, 252, 0)),
           ("orange", (255, 168, 0)), ("red", (252, 70, 70)), ("yellow", (255, 255, 100)), ("purple", (192, 128, 242)), ("tan", (204, 195, 176))]
SELECTED = (255, 215, 80)    # the selected row's name
TEXT_FACE = "Formal"
# Formal at $SmallFontSize, measured on game screenshots at 1600 x 900 (lane wikipanel): a prose line 15.7 panel units a character, digits
# 16.8. The plugin wraps by character count, and a text box does not cut what is too wide, so the count is on the safe side.
FORMAL_CHAR = 18.0

# button ids, in the order the plugin indexes them
BUTTONS = ([f"cat{i}" for i in range(CATEGORY_SLOTS)] + [f"row{i}" for i in range(ROWS)] + [f"line{i}" for i in range(LINES)] +
           ["prev", "next", "up", "down", "back", "close"])
CLICK_MESSAGE = "PanelManager:OpenPanel:mxl2012-core/WikiB_0"

PANEL_W, PANEL_H = 2800, 1660   # of the 3840 x 2160 units of a 16:9 screen; 2880 units is a 4:3 screen's width
PANEL_Y = -1000                 # top at 80, bottom at 1740: above the HUD (the side panels end at 1833)
MARGIN = 60
PANE_Y, PANE_H = 296, 1188      # both panes
LIST_X, LIST_W = MARGIN, 1150
DETAIL_X = LIST_X + LIST_W + 20
DETAIL_W = PANEL_W - MARGIN - DETAIL_X
ROW_PITCH, LINE_PITCH = 52, 42
PAD = 10
CAT_W, CAT_GAP, CAT_Y, CAT_SIZE = 242, 8, 216, 20


def message(name: str) -> str:
    assert name in BUTTONS, name
    return CLICK_MESSAGE


def text_button(name: str, label: str, x: int, y: int, width: int, size: int, visible: bool = True) -> dict:
    """ModalButton scaled to `width`, the label `size` panel units high."""
    scale = width / dev.ART["PANEL\\Modals\\ModalButton"][0]
    return {"type": "ButtonWidget", "name": f"Btn_{name}",
            "fields": {"rect": {"x": x, "y": y, "scale": scale}, "onClickMessage": message(name), "textString": label, "visible": visible,
                       "filename": "PANEL\\Modals\\ModalButton", "pointSize": int(size / scale), "textColor": "$FontColorWhite"}}


def arrow_button(name: str, x: int, y: int, scale: float = 1.0, left: bool = False, visible: bool = True) -> dict:
    return {"type": "ButtonWidget", "name": f"Btn_{name}",
            "fields": {"rect": {"x": x, "y": y, "scale": scale}, "filename": f"PANEL\\Stash\\Stash_{'Left' if left else 'Right'}Arrow",
                       "normalFrame": 0, "pressedFrame": 2, "hoveredFrame": 1, "disabledFrame": 3, "onClickMessage": message(name),
                       "visible": visible}}


def text_box(name: str, x: int, y: int, w: int, h: int, text: str = "", colour="$FontColorWhite", align: str = "left",
             size: str = "$SmallFontSize", face: str = "") -> dict:
    if isinstance(colour, tuple):
        colour = {"r": colour[0], "g": colour[1], "b": colour[2], "a": 255}
    style = {"fontColor": colour, "pointSize": size, "alignment": {"h": align, "v": "center"}}
    if face:
        style["fontFace"] = face
    return {"type": "TextBoxWidget", "name": name, "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}, "text": text, "style": style}}


def frame(name: str, x: int, y: int, w: int, h: int, fill: list, border: tuple) -> dict:
    return {"type": "RectangleWidget", "name": name, "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}, "color": fill,
                                                                 "borderColor": {"r": border[0], "g": border[1], "b": border[2], "a": 255}}}


def layout() -> dict:
    gold = "$FontColorGoldYellow"
    children = [frame("Background", 0, 0, PANEL_W, PANEL_H, [0.03, 0.03, 0.04, 0.97], (150, 130, 80)),
                {"type": "ClickCatcherWidget", "name": "ClickCatcher", "fields": {"fitToParent": True}},
                frame("ListPane", LIST_X, PANE_Y, LIST_W, PANE_H, [0.0, 0.0, 0.0, 0.55], (90, 78, 48)),
                frame("DetailPane", DETAIL_X, PANE_Y, DETAIL_W, PANE_H, [0.0, 0.0, 0.0, 0.55], (90, 78, 48)),
                text_box("Title", 0, 22, PANEL_W, 72, TITLE, gold, align="center", size="$MediumFontSize")]
    close_w = dev.ART["PANEL\\closebtn_4x"][0]
    children.append({"type": "ButtonWidget", "name": "Btn_close",
                     "fields": {"rect": {"x": PANEL_W - close_w - 16, "y": 14, "scale": 1.0}, "filename": "PANEL\\closebtn_4x", "hoveredFrame": 3,
                                "onClickMessage": message("close")}})

    # the search label and its box, left; Back, right
    slot_scale, label_w, gap = 0.8, 180, 16
    slot_w, slot_h = dev.art_size("PANEL\\Modals\\InputSlot", slot_scale)
    slot_x, slot_y = MARGIN + label_w + gap, 104
    children.append(text_box("InputLabel", MARGIN, slot_y, label_w, slot_h, "Search", gold, align="right", size="$MediumFontSize"))
    children.append({"type": "ImageWidget", "name": "InputSlot", "fields": {"rect": {"x": slot_x, "y": slot_y, "scale": slot_scale},
                                                                            "filename": "PANEL\\Modals\\InputSlot"}})
    # the slot's inner field: (36, 14) in, 681 x 75 at scale 1 (tools/devmenu_layout.py)
    box = {"x": slot_x + round(36 * slot_scale), "y": slot_y + round(14 * slot_scale), "width": round(681 * slot_scale), "height": round(75 * slot_scale)}
    children.append({"type": "InputTextBoxWidget", "name": INPUT,
                     "fields": {"rect": box, "backgroundColor": {"r": 0, "g": 0, "b": 0, "a": 0}, "maxStringLength": 48, "fontType": "8pt",
                                "imeEnabled": False, "fontStyle": {"alignment": {"v": "center"}, "pointSize": "$MediumFontSize",
                                                                   "fontFace": "BlizzardGlobal"}}})
    back_w = 308
    children.append(text_button("back", "Back", PANEL_W - MARGIN - back_w, slot_y + 14, back_w, 24, visible=False))

    # the categories: one centred row of equal buttons
    for i, x in enumerate(dev.centred_row(PANEL_W, CATEGORY_SLOTS, CAT_W, CAT_GAP)):
        children.append(text_button(f"cat{i}", f"@C{i}@", x, CAT_Y, CAT_W, CAT_SIZE))

    m = {"panelX": -PANEL_W // 2, "panelY": PANEL_Y, "panelW": PANEL_W, "panelH": PANEL_H, "rows": ROWS, "lines": LINES,
         "listX": LIST_X, "listY": PANE_Y, "listW": LIST_W, "listH": PANE_H, "detailX": DETAIL_X, "detailY": PANE_Y, "detailW": DETAIL_W, "detailH": PANE_H,
         "rowX": LIST_X + PAD, "rowY": PANE_Y + PAD, "rowPitch": ROW_PITCH, "lineX": DETAIL_X + PAD, "lineY": PANE_Y + PAD, "linePitch": LINE_PITCH,
         "inputX": box["x"], "inputY": box["y"], "inputW": box["width"], "inputH": box["height"]}
    row_arrow, line_arrow = round(ARROW * ROW_ARROW_SCALE), round(ARROW * LINE_ARROW_SCALE)
    m["rowTextX"] = m["rowX"] + row_arrow + 12
    m["rowTextW"] = LIST_X + LIST_W - PAD - m["rowTextX"]
    m["lineTextX"] = m["lineX"] + line_arrow + 12
    m["lineTextW"] = DETAIL_X + DETAIL_W - PAD - m["lineTextX"]
    m["rowChars"] = int(m["rowTextW"] / FORMAL_CHAR)
    m["lineChars"] = int(m["lineTextW"] / FORMAL_CHAR)

    # Text boxes before the arrows: D2R hit-tests in list order and the arrows must stay on top.
    for i in range(ROWS):
        y = m["rowY"] + i * ROW_PITCH
        children.append(text_box(f"RowSub{i}", m["rowTextX"], y, m["rowTextW"], ROW_PITCH, colour=COLOURS[1][1], align="right", face=TEXT_FACE))
        children.append(text_box(f"RowText{i}_0", m["rowTextX"], y, m["rowTextW"], ROW_PITCH, face=TEXT_FACE))
        children.append(text_box(f"RowText{i}_1", m["rowTextX"], y, m["rowTextW"], ROW_PITCH, colour=SELECTED, face=TEXT_FACE))
    for i in range(LINES):
        y = m["lineY"] + i * LINE_PITCH
        children.append(text_box(f"LineMark{i}", m["lineX"], y, line_arrow, LINE_PITCH, colour=gold, align="center", face=TEXT_FACE))
        for c, (_name, rgb) in enumerate(COLOURS):
            children.append(text_box(f"DetailText{i}_{c}", m["lineTextX"], y, m["lineTextW"], LINE_PITCH, colour=rgb, face=TEXT_FACE))
    foot_y = PANE_Y + PANE_H + 8
    m["footY"] = foot_y
    children.append(text_box("PageText", LIST_X + ARROW + 12, foot_y, LIST_W - 2 * (ARROW + 12), ARROW, colour=gold, align="center"))
    children.append(text_box("LinesText", DETAIL_X + ARROW + 12, foot_y, DETAIL_W - 2 * (ARROW + 12), ARROW, colour=gold, align="center"))
    status_y = foot_y + ARROW + 8
    m["statusChars"] = int((PANEL_W - 2 * MARGIN) / dev.HD_ROW_CHAR)
    children.append(text_box("StatusText", MARGIN, status_y, PANEL_W - 2 * MARGIN, 44, colour=gold, align="center"))

    for i in range(ROWS):
        children.append(arrow_button(f"row{i}", m["rowX"], m["rowY"] + i * ROW_PITCH + (ROW_PITCH - row_arrow) // 2, ROW_ARROW_SCALE, visible=False))
    for i in range(LINES):
        children.append(arrow_button(f"line{i}", m["lineX"], m["lineY"] + i * LINE_PITCH + (LINE_PITCH - line_arrow) // 2, LINE_ARROW_SCALE, visible=False))
    children.append(arrow_button("prev", LIST_X, foot_y, left=True))
    children.append(arrow_button("next", LIST_X + LIST_W - ARROW, foot_y))
    children.append(arrow_button("up", DETAIL_X, foot_y, left=True))
    children.append(arrow_button("down", DETAIL_X + DETAIL_W - ARROW, foot_y))

    root = {"type": "Panel", "name": PANEL, "fields": {"rect": {"x": m["panelX"], "y": m["panelY"], "width": PANEL_W, "height": PANEL_H},
                                                       "anchor": {"x": 0.5, "y": 0.5}, "priority": 8}, "children": children}
    return {"root": root, "metrics": m}


def widget_box(child: dict) -> tuple:
    """(x, y, width, height) a widget covers in the panel: its rect, or the art at its scale."""
    f = child["fields"]
    r = f.get("rect", {})
    if "width" in r:
        return r["x"], r["y"], r["width"], r["height"]
    name = f["filename"]
    w, h = (ARROW, ARROW) if "Arrow" in name else dev.ART[name]
    scale = r.get("scale", 1.0)
    return r["x"], r["y"], round(w * scale), round(h * scale)


def label_width(child: dict, text: str) -> float:
    """A button label's estimated width on one line, panel units."""
    f = child["fields"]
    return len(text) * dev.HD_CHAR_PER_POINT * f["pointSize"] * f["rect"].get("scale", 1.0)


def cpp_parts(name: str, data: dict, piece: int = 4000) -> str:
    """The layout as compact JSON in pieces (one string literal is limited in size), which the plugin joins."""
    text = json.dumps(data, separators=(",", ":"))
    pieces = [text[i:i + piece] for i in range(0, len(text), piece)]
    lines = [f"inline constexpr const char* {name}[] = {{"]
    for p in pieces:
        lines.append('    "' + p.replace("\\", "\\\\").replace('"', '\\"') + '",')
    lines.append("};")
    return "\n".join(lines)


METRIC_FIELDS = ["panelX", "panelY", "panelW", "panelH", "rows", "lines", "rowChars", "lineChars", "statusChars",
                 "listX", "listY", "listW", "listH", "detailX", "detailY", "detailW", "detailH", "inputX", "inputY", "inputW", "inputH"]


def header_text() -> str:
    built = layout()
    m = built["metrics"]
    kids = {c["name"]: c for c in built["root"]["children"]}
    out = ["// Written by tools/wiki_layout.py (`py -3 -I tools/wiki_layout.py header`); tools/tests/test_wiki_layout.py checks it is current.",
           "#pragma once", "", '#include "panel_logic.h"', "", "namespace wiki_layout {", "",
           f'inline constexpr char PanelLocalId[] = "{PANEL_LOCAL_ID}";', f'inline constexpr char PanelName[] = "{PANEL}";',
           f'inline constexpr char InputName[] = "{INPUT}";', f"inline constexpr int ButtonCount = {len(BUTTONS)};",
           f"inline constexpr int CategorySlots = {CATEGORY_SLOTS};", f"inline constexpr int MaxRows = {ROWS};", f"inline constexpr int MaxLines = {LINES};",
           f"inline constexpr int ColourCount = {len(COLOURS)};  // DetailText<line>_<colour>: wiki_logic.h Colour, in its order",
           "inline constexpr const char* ButtonNames[ButtonCount] = {" + ", ".join(f'"{b}"' for b in BUTTONS) + "};", "",
           "struct Metrics {", "\tint panelX, panelY, panelW, panelH;  // the panel's rect, relative to the screen center (anchor 0.5, 0.5)",
           "\tint rows, lines;  // result rows a page, detail lines",
           "\tint rowChars, lineChars, statusChars;  // characters that fit one line of that kind",
           "\tint listX, listY, listW, listH, detailX, detailY, detailW, detailH;  // the two panes, panel-local (the mouse wheel)",
           "\tint inputX, inputY, inputW, inputH;  // the search box, panel-local", "};", "",
           "inline constexpr Metrics Hd = {" + ", ".join(str(m[k]) for k in METRIC_FIELDS) + "};", "",
           "// Each button's rectangle in the panel, in the order of ButtonNames: every button sends one message, the click's place says which.",
           "inline constexpr panel_logic::UnitRect ButtonRects[ButtonCount] = {" + ", ".join(
               "{%d, %d, %d, %d}" % widget_box(kids[f"Btn_{b}"]) for b in BUTTONS) + "};", "",
           "// The layout's JSON in pieces, to be joined in order.",
           cpp_parts("LayoutHdParts", built["root"]), "", "}  // namespace wiki_layout", ""]
    return "\n".join(out)


def main() -> int:
    if sys.argv[1:] == ["header"]:
        HEADER.write_text(header_text(), encoding="utf-8", newline="\n")
        print(f"wrote {HEADER.relative_to(ROOT)}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
