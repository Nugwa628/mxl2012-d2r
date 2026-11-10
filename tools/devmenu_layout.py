"""The developer menu's two panel layouts (plugin part `devmenu`, plugin/src/devmenu.cpp): HD and classic graphics.

One native D2R panel, `mxl2012-core/DevMenu`, in each graphics mode, one frame and background behind everything (HD: D2R's wide panel art
`PANEL\\Options\\FrontEndOptionsBG`, the Chronicle panel's, scaled to the side panels' height; classic: one filled rectangle with a border), a
click catcher, the tab / category / page / action buttons with their written-out labels (no `@key`: docs/bugs.md #30), a text box for the search
or the target level, and one arrow button per result row. The result names, the page line and the status are empty TextBoxWidgets
(`RowText<n>`, `HeaderText<n>`, `StatusText<n>`) the plugin fills through D2R's own text setter; `Metrics` holds how many characters fit each
kind of line, so the plugin wraps the page line and status and cuts a row before it leaves the panel.

Geometry: every button row (tabs, categories) is centred, its buttons the same size with the same gap; the search label and its box are one
centred group, the label right-aligned against the box. HD buttons are ModalButton at a scale chosen so that the label fits on one line; classic
buttons are art of a fixed size (D2R draws classic button art at its own size whatever the scale, and only moves the text with it), so each row
uses art wide enough for its labels. Text widths are estimated from game screenshots (`HD_CHAR_PER_POINT`, `HD_ROW_CHAR`, `SD_CHAR`);
tools/tests/test_devmenu_layout.py checks that labels fit, the longest catalog rows fit, rows are symmetric and the panel fits the screen.

The text box is a plain InputTextBoxWidget (no `alwaysAcceptsKeyInput`, no `focusOnMouseOver`: the pointer passing over it must not take the
keyboard). Keys reach it through D2R's own text input; the plugin keeps key bindings from claiming them while the box has the keyboard
(devmenu.cpp "typing", docs/d2r-addresses.md "Text boxes and key bindings"). `Metrics` carries the box's rectangle so the plugin can tell a click
on it from a click elsewhere.

Each button sends `PanelManager:OpenPanel:mxl2012-core/DevMenuB_<n>`, a panel name registered by the plugin (D2R hands PanelManager
messages to UI listeners only for known panels, plugin/src/send_stash.cpp) and consumed there; `n` indexes `BUTTONS`.

  py -3 -I tools/devmenu_layout.py header     write plugin/src/mxl_devmenu_layout.h (committed; tools/tests/test_devmenu_layout.py checks it is current)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = ROOT / "plugin" / "src" / "mxl_devmenu_layout.h"

PANEL = "mxl2012-core/DevMenu"
PANEL_LOCAL_ID = "DevMenu"
INPUT = "DevMenuInput"
ROW_PREFIX = "Row"

TABS = ["Items", "Travel", "Character", "Unlocks", "Quests"]
CATEGORIES = ["All", "Uniques", "Sets", "Charms", "Quest / misc", "Bases", "Runewords"]
ACTIONS = [("raise", "Raise to level"), ("unlock", "Unlock all waypoints"), ("quests", "Advanced: complete quests"),
           ("confirm", "Confirm: complete quests")]
# The Quests action's warning (rewards are not guaranteed) is the tab's page line right under the buttons, and Confirm asks again: the label
# itself stays short enough for one line at a readable size (0.1.18's two-line label sat in a button; in classic it cannot).
ACTION_SCALE_HD = 1.3                            # ModalButton 690 x 133
ACTION_Y = {"hd": (440, 620), "sd": (160, 220)}  # the tab's action; Confirm below the Quests button
ROWS = {"hd": 12, "sd": 8}
HEADER_LINES = 2
STATUS_LINES = 4

# button ids, in the order the plugin indexes them
BUTTONS = ([f"tab{i}" for i in range(len(TABS))] + [f"cat{i}" for i in range(len(CATEGORIES))] + [f"row{i}" for i in range(max(ROWS.values()))] +
           ["prev", "next", "close"] + [a for a, _ in ACTIONS])

# Art sizes, one frame (panel units at scale 1): HD sprites and classic DC6 frames of build 93847's CASC.
HD_BG = "PANEL\\Options\\FrontEndOptionsBG"  # 1950 x 1635: frame about 54 at the sides and 68 at the bottom, title band to about 140
HD_BG_SIZE = (1950, 1635)
HD_BG_SCALE = 0.92                           # as tall as the side panels (1507), so it sits where the 0.1.18 panel did, 632 units wider
ART = {"PANEL\\Modals\\ModalButton": (531, 102), "PANEL\\Modals\\InputSlot": (742, 113), "PANEL\\closebtn_4x": (83, 84),
       "FrontEnd\\MediumButtonBlank": (128, 35), "FrontEnd\\OkCancelButtonBlank": (96, 32), "FrontEnd\\WideButtonBlank": (272, 35),
       "PANEL\\buysellbtn": (32, 32)}
# Text width per character in panel units, measured on game screenshots: HD labels 0.73 ("Quest / misc") to 0.84 ("Character") x the point
# size, HD rows (SmallFontSize) about 18; classic 8pt about 6.2, 8ptE (capitals) about 9. A button keeps about 84 % of its width for its label
# (the HD end caps, the classic bevel).
HD_CHAR_PER_POINT = 0.85
HD_ROW_CHAR = 18.5
SD_CHAR = {"8pt": 6.4, "8ptE": 9.0}
BUTTON_TEXT_SHARE = 0.84


def message(name: str) -> str:
    return f"PanelManager:OpenPanel:mxl2012-core/DevMenuB_{BUTTONS.index(name)}"


def art_size(filename: str, scale: float = 1.0) -> tuple:
    w, h = ART[filename]
    return round(w * scale), round(h * scale)


def text_button(mode: str, name: str, label: str, x: int, y: int, scale: float = 1.0, visible: bool = True, size: int = 26, art: str = "",
                font: str = "8pt") -> dict:
    """HD: ModalButton at `scale`, the label `size` panel units high. Classic: `art` at its own size, the label in `font`."""
    if mode == "hd":
        fields = {"rect": {"x": x, "y": y, "scale": scale}, "onClickMessage": message(name), "textString": label, "visible": visible,
                  "filename": "PANEL\\Modals\\ModalButton", "pointSize": int(size / scale), "textColor": "$FontColorWhite"}
    else:
        fields = {"rect": {"x": x, "y": y}, "onClickMessage": message(name), "textString": label, "visible": visible, "filename": art,
                  "fontType": font, "textColor": {"r": 255, "g": 255, "b": 255, "a": 255}}
        if art == "FrontEnd\\WideButtonBlank":
            # two-piece art (256 + 16): the button takes no size from it, and without one its label wraps after every letter (seen in game)
            fields.update({"multiFrame": True, "pressedFrame": 2})
            fields["rect"].update({"width": ART[art][0], "height": ART[art][1]})
    return {"type": "ButtonWidget", "name": f"Btn_{name}", "fields": fields}


def close_button(mode: str, x: int, y: int, scale: float = 1.0) -> dict:
    if mode == "hd":
        fields = {"rect": {"x": x, "y": y, "scale": scale}, "filename": "PANEL\\closebtn_4x", "hoveredFrame": 3}
    else:
        fields = {"rect": {"x": x, "y": y}, "filename": "PANEL\\buysellbtn", "normalFrame": 10, "pressedFrame": 11}
    fields["onClickMessage"] = message("close")
    return {"type": "ButtonWidget", "name": "Btn_close", "fields": fields}


def arrow_button(mode: str, name: str, x: int, y: int, left: bool = False) -> dict:
    if mode == "hd":
        fields = {"rect": {"x": x, "y": y, "width": 64, "height": 64}, "filename": f"PANEL\\Stash\\Stash_{'Left' if left else 'Right'}Arrow",
                  "normalFrame": 0, "pressedFrame": 2, "hoveredFrame": 1, "disabledFrame": 3}
    else:
        fields = {"rect": {"x": x, "y": y, "width": 32, "height": 32}, "filename": "PANEL\\buysellbtn",
                  "normalFrame": 12 if left else 14, "pressedFrame": 13 if left else 15}
    fields["onClickMessage"] = message(name)
    return {"type": "ButtonWidget", "name": f"Btn_{name}", "fields": fields}


def label(mode: str, text: str, x: int, y: int, w: int, h: int, name: str = "", align: str = "left") -> dict:
    style = ({"fontColor": "$FontColorGoldYellow", "pointSize": "$MediumFontSize", "alignment": {"h": align, "v": "center"}} if mode == "hd" else
             {"fontColor": {"r": 200, "g": 180, "b": 110, "a": 255}, "alignment": {"h": align, "v": "center"}})
    return {"type": "TextBoxWidget", "name": name or f"Text_{x}_{y}", "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}, "text": text,
                                                                                 "style": style, **({} if mode == "hd" else {"fontType": "8pt"})}}


def text_line(mode: str, name: str, x: int, y: int, w: int, h: int, gold: bool = False) -> dict:
    if mode == "hd":
        style = {"fontColor": "$FontColorGoldYellow" if gold else "$FontColorWhite", "pointSize": "$SmallFontSize", "alignment": {"v": "center"}}
    else:
        style = {"fontColor": {"r": 200, "g": 180, "b": 110, "a": 255} if gold else {"r": 255, "g": 255, "b": 255, "a": 255}, "alignment": {"v": "center"}}
    return {"type": "TextBoxWidget", "name": name, "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}, "text": "", "style": style,
                                                              **({} if mode == "hd" else {"fontType": "8pt"})}}


def input_box(mode: str, x: int, y: int, w: int, h: int) -> dict:
    fields = {"rect": {"x": x, "y": y, "width": w, "height": h}, "backgroundColor": {"r": 0, "g": 0, "b": 0, "a": 0 if mode == "hd" else 160},
              "maxStringLength": 48, "fontType": "8pt", "imeEnabled": False}
    if mode == "hd":
        fields["fontStyle"] = {"alignment": {"v": "center"}, "pointSize": "$MediumFontSize", "fontFace": "BlizzardGlobal"}
    return {"type": "InputTextBoxWidget", "name": INPUT, "fields": fields}


def centred_row(panel_w: int, count: int, width: int, gap: int) -> list:
    """x of `count` buttons `width` wide with `gap` between them, the row centred in the panel."""
    x0 = (panel_w - (count * width + (count - 1) * gap)) // 2
    return [x0 + i * (width + gap) for i in range(count)]


def text_lines(mode: str, m: dict, rows: int) -> list:
    # Before the arrows: D2R hit-tests in list order and the arrows must stay on top. Rows start right of their arrows and end as far from the
    # right edge as the arrows are from the left; the page line sits between the page arrows, the status spans the panel inside its margins.
    out = [text_line(mode, f"RowText{i}", m["textX"], m["rowY"] + i * m["rowPitch"], m["panelW"] - m["rowX"] - m["textX"], m["rowH"]) for i in range(rows)]
    out += [text_line(mode, f"HeaderText{i}", m["textX"], m["headerY"] + i * m["headerLineH"], m["panelW"] - 2 * m["textX"], m["headerLineH"], gold=True)
            for i in range(HEADER_LINES)]
    out += [text_line(mode, f"StatusText{i}", m["rowX"], m["statusY"] + i * m["statusLineH"], m["panelW"] - 2 * m["rowX"], m["statusLineH"], gold=True)
            for i in range(STATUS_LINES)]
    return out


def line_chars(mode: str, m: dict) -> dict:
    per = HD_ROW_CHAR if mode == "hd" else SD_CHAR["8pt"]
    return {"rowChars": int((m["panelW"] - m["rowX"] - m["textX"]) / per), "headerChars": int((m["panelW"] - 2 * m["textX"]) / per),
            "statusChars": int((m["panelW"] - 2 * m["rowX"]) / per)}


def layout(mode: str) -> dict:
    hd = mode == "hd"
    rows = ROWS[mode]
    panel_w, panel_h = (round(HD_BG_SIZE[0] * HD_BG_SCALE), round(HD_BG_SIZE[1] * HD_BG_SCALE)) if hd else (760, 502)
    # One frame and background behind every widget: D2R's wide panel art in HD, and a plain rectangle in classic graphics, which have no empty
    # panel art (MENU\\dialogbackground has input boxes painted in).
    if hd:
        children = [{"type": "ImageWidget", "name": "Background", "fields": {"rect": {"x": 0, "y": 0, "scale": HD_BG_SCALE}, "filename": HD_BG}}]
    else:
        children = [{"type": "RectangleWidget", "name": "Background", "fields": {"rect": {"x": 0, "y": 0, "width": panel_w, "height": panel_h}, "color": [0.03, 0.03, 0.04, 0.97],
                                                                                 "borderColor": {"r": 150, "g": 130, "b": 80, "a": 255}}}]
    children.append({"type": "ClickCatcherWidget", "name": "ClickCatcher", "fields": {"fitToParent": True}})
    # classic: the top of the 800 x 600 screen (y 2 to 504), above the HUD's orbs and control bar, 20 units left free at each side
    metrics = {"panelX": -panel_w // 2, "panelY": -panel_h // 2 if hd else -298, "panelW": panel_w, "panelH": panel_h}
    if hd:
        s = HD_BG_SCALE
        modal_w = ART["PANEL\\Modals\\ModalButton"][0]
        children.append(label(mode, "D2R-XL 2012 Developer Menu", 0, round(45 * s), panel_w, round(103 * s), "Title", align="center"))
        children.append(close_button(mode, round(1868 * s), round(8 * s), s))  # where D2R's Chronicle panel puts it on this art
        for i, (t, x) in enumerate(zip(TABS, centred_row(panel_w, len(TABS), 308, 22))):
            children.append(text_button(mode, f"tab{i}", t, x, 150, 308 / modal_w, size=24))
        slot_scale, label_w, gap = 0.8, 300, 16
        slot_w, slot_h = art_size("PANEL\\Modals\\InputSlot", slot_scale)
        slot_x, slot_y = (panel_w - (label_w + gap + slot_w)) // 2 + label_w + gap, 224
        children.append(label(mode, "Search / level", slot_x - gap - label_w, slot_y, label_w, slot_h, "InputLabel", align="right"))
        children.append({"type": "ImageWidget", "name": "InputSlot", "fields": {"rect": {"x": slot_x, "y": slot_y, "scale": slot_scale},
                                                                                "filename": "PANEL\\Modals\\InputSlot"}})
        # the slot's inner field: (36, 14) in, 681 x 75 at scale 1
        children.append(input_box(mode, slot_x + round(36 * slot_scale), slot_y + round(14 * slot_scale), round(681 * slot_scale), round(75 * slot_scale)))
        for i, (t, x) in enumerate(zip(CATEGORIES, centred_row(panel_w, len(CATEGORIES), 224, 10))):
            children.append(text_button(mode, f"cat{i}", t, x, 330, 224 / modal_w, size=18))
        metrics.update({"rowX": 74, "rowY": 390, "rowPitch": 64, "rowH": 64, "textX": 150, "headerY": 1166, "headerLineH": 42, "statusY": 1256,
                        "statusLineH": 42})
        metrics.update(line_chars(mode, metrics))
        children.extend(text_lines(mode, metrics, rows))
        for i in range(rows):
            children.append(arrow_button(mode, f"row{i}", metrics["rowX"], metrics["rowY"] + i * metrics["rowPitch"]))
        children.append(arrow_button(mode, "prev", metrics["rowX"], metrics["headerY"] + 10, left=True))
        children.append(arrow_button(mode, "next", panel_w - metrics["rowX"] - 64, metrics["headerY"] + 10))
        # one tab shows one action (Character: raise, Unlocks: unlock, Quests: quests, then Confirm below it)
        action_w = art_size("PANEL\\Modals\\ModalButton", ACTION_SCALE_HD)[0]
        for name, text in ACTIONS:
            children.append(text_button(mode, name, text, (panel_w - action_w) // 2, ACTION_Y[mode][name == "confirm"], ACTION_SCALE_HD))
    else:
        children.append(label(mode, "D2R-XL 2012 Developer Menu", 0, 3, panel_w, 20, "Title", align="center"))
        children.append(close_button(mode, panel_w - 34, 2))
        tab_art, cat_art, action_art = "FrontEnd\\MediumButtonBlank", "FrontEnd\\OkCancelButtonBlank", "FrontEnd\\WideButtonBlank"
        for i, (t, x) in enumerate(zip(TABS, centred_row(panel_w, len(TABS), ART[tab_art][0], 20))):
            children.append(text_button(mode, f"tab{i}", t, x, 26, art=tab_art, font="8pt"))  # 8ptE reads poorly on the stone art
        label_w, gap, frame_w = 96, 8, 404
        frame_x = (panel_w - (label_w + gap + frame_w)) // 2 + label_w + gap
        children.append(label(mode, "Search / level", frame_x - gap - label_w, 65, label_w, 28, "InputLabel", align="right"))
        children.append({"type": "RectangleWidget", "name": "InputFrame", "fields": {"rect": {"x": frame_x, "y": 64, "width": frame_w, "height": 30},
                                                                                     "color": [0.0, 0.0, 0.0, 0.85], "borderColor": {"r": 150, "g": 130, "b": 80, "a": 255}}})
        children.append(input_box(mode, frame_x + 2, 66, frame_w - 4, 26))
        for i, (t, x) in enumerate(zip(CATEGORIES, centred_row(panel_w, len(CATEGORIES), ART[cat_art][0], 8))):
            children.append(text_button(mode, f"cat{i}", t, x, 100, art=cat_art, font="8pt"))
        metrics.update({"rowX": 12, "rowY": 138, "rowPitch": 32, "rowH": 32, "textX": 52, "headerY": 398, "headerLineH": 16, "statusY": 434,
                        "statusLineH": 16})
        metrics.update(line_chars(mode, metrics))
        children.extend(text_lines(mode, metrics, rows))
        for i in range(rows):
            children.append(arrow_button(mode, f"row{i}", metrics["rowX"], metrics["rowY"] + i * metrics["rowPitch"]))
        children.append(arrow_button(mode, "prev", metrics["rowX"], metrics["headerY"], left=True))
        children.append(arrow_button(mode, "next", panel_w - metrics["rowX"] - 32, metrics["headerY"]))
        for name, text in ACTIONS:
            children.append(text_button(mode, name, text, (panel_w - ART[action_art][0]) // 2, ACTION_Y[mode][name == "confirm"],
                                        art=action_art))
    box = next(c for c in children if c["name"] == INPUT)["fields"]["rect"]
    metrics.update({"inputX": box["x"], "inputY": box["y"], "inputW": box["width"], "inputH": box["height"]})
    root = {"type": "Panel", "name": PANEL, "fields": {"rect": {"x": metrics["panelX"], "y": metrics["panelY"], "width": panel_w, "height": panel_h},
                                                       "anchor": {"x": 0.5, "y": 0.5}, "priority": 8}, "children": children}
    return {"root": root, "metrics": {**metrics, "rows": rows}}


def widget_box(mode: str, child: dict) -> tuple:
    """(x, y, width, height) a widget covers in the panel: its rect, or the art at its scale (classic art is drawn at its own size)."""
    f = child["fields"]
    r = f.get("rect", {})
    if "width" in r:
        return r["x"], r["y"], r["width"], r["height"]
    scale = r.get("scale", 1.0) if mode == "hd" else 1.0
    w, h = HD_BG_SIZE if f.get("filename") == HD_BG else ART[f["filename"]]
    return r["x"], r["y"], round(w * scale), round(h * scale)


def label_width(mode: str, child: dict) -> float:
    """A button label's estimated width on one line, panel units."""
    f = child["fields"]
    if mode == "hd":
        return len(f["textString"]) * HD_CHAR_PER_POINT * f["pointSize"] * f["rect"].get("scale", 1.0)
    return len(f["textString"]) * SD_CHAR[f["fontType"]]


def cpp_string(name: str, data: dict) -> str:
    lines = [f'inline constexpr char {name}[] =']
    text = json.dumps(data, indent=0)
    for line in text.split("\n"):
        escaped = line.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'    "{escaped}\\n"')
    lines[-1] += ";"
    return "\n".join(lines)


def metrics_struct(name: str, m: dict) -> str:
    return (f"inline constexpr Metrics {name} = {{{m['panelX']}, {m['panelY']}, {m['panelW']}, {m['panelH']}, {m['rows']}, {m['rowX']}, {m['rowY']}, {m['rowPitch']}, {m['rowH']}, "
            f"{m['textX']}, {m['headerY']}, {m['statusY']}, {m['rowChars']}, {m['headerChars']}, {m['statusChars']}, "
            f"{m['inputX']}, {m['inputY']}, {m['inputW']}, {m['inputH']}}};")


def header_text() -> str:
    hd, sd = layout("hd"), layout("sd")
    out = ["// Written by tools/devmenu_layout.py (`py -3 -I tools/devmenu_layout.py header`); tools/tests/test_devmenu_layout.py checks it is current.",
           "#pragma once", "", "namespace devmenu_layout {", "",
           f'inline constexpr char PanelLocalId[] = "{PANEL_LOCAL_ID}";', f'inline constexpr char PanelName[] = "{PANEL}";',
           f'inline constexpr char InputName[] = "{INPUT}";', f"inline constexpr int ButtonCount = {len(BUTTONS)};",
           f"inline constexpr int TabCount = {len(TABS)};", f"inline constexpr int CategoryCount = {len(CATEGORIES)};",
           f"inline constexpr int MaxRows = {max(ROWS.values())};", f"inline constexpr int HeaderLines = {HEADER_LINES};", f"inline constexpr int StatusLines = {STATUS_LINES};",
           "inline constexpr const char* ButtonNames[ButtonCount] = {" + ", ".join(f'"{b}"' for b in BUTTONS) + "};", "",
           "struct Metrics {", "\tint panelX, panelY, panelW, panelH;  // the panel's rect, relative to the screen center (anchor 0.5, 0.5)",
           "\tint rows, rowX, rowY, rowPitch, rowH, textX, headerY, statusY;  // panel-local",
           "\tint rowChars, headerChars, statusChars;  // characters that fit one line of that kind",
           "\tint inputX, inputY, inputW, inputH;  // the search / level box, panel-local", "};", "",
           metrics_struct("Hd", hd["metrics"]), metrics_struct("Sd", sd["metrics"]), "",
           cpp_string("LayoutHd", hd["root"]), "", cpp_string("LayoutSd", sd["root"]), "", "}  // namespace devmenu_layout", ""]
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
