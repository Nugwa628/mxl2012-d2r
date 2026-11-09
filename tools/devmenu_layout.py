"""The developer menu's two panel layouts (plugin part `devmenu`, plugin/src/devmenu.cpp): HD and classic graphics.

One native D2R panel, `mxl2012-core/DevMenu`, in each graphics mode: background art (HD only), a click catcher, the tab / category / page / action
buttons with their written-out labels (no `@key`: docs/bugs.md #30), a text box for the search or the target level, and one arrow button
per result row. The result names, the page line and the status are empty TextBoxWidgets (`RowText<n>`, `HeaderText`, `StatusText<n>`) the plugin fills
through D2R's own text setter; `Metrics` holds how many characters fit each kind of line, so the plugin cuts a line before it leaves the panel.

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
ACTIONS = [("raise", "Raise to level"), ("unlock", "Unlock all waypoints"), ("quests", "Advanced: complete quests (rewards not guaranteed)"),
           ("confirm", "Confirm: complete quests")]
ROWS = {"hd": 12, "sd": 9}
STATUS_LINES = 3

# button ids, in the order the plugin indexes them
BUTTONS = ([f"tab{i}" for i in range(len(TABS))] + [f"cat{i}" for i in range(len(CATEGORIES))] + [f"row{i}" for i in range(max(ROWS.values()))] +
           ["prev", "next", "close"] + [a for a, _ in ACTIONS])


def message(name: str) -> str:
    return f"PanelManager:OpenPanel:mxl2012-core/DevMenuB_{BUTTONS.index(name)}"


def text_button(mode: str, name: str, label: str, x: int, y: int, scale: float, visible: bool = True) -> dict:
    fields = {"rect": {"x": x, "y": y, "scale": scale}, "onClickMessage": message(name), "textString": label, "visible": visible}
    if mode == "hd":
        fields.update({"filename": "PANEL\\Modals\\ModalButton", "pointSize": int((20 if name.startswith("cat") else 26) / scale), "textColor": "$FontColorWhite"})
    else:
        fields.update({"filename": "FrontEnd\\OkCancelButtonBlank", "fontType": "8ptE", "textColor": {"r": 255, "g": 255, "b": 255, "a": 255}})
    return {"type": "ButtonWidget", "name": f"Btn_{name}", "fields": fields}


def arrow_button(mode: str, name: str, x: int, y: int, left: bool = False) -> dict:
    if mode == "hd":
        fields = {"rect": {"x": x, "y": y, "width": 64, "height": 64}, "filename": f"PANEL\\Stash\\Stash_{'Left' if left else 'Right'}Arrow",
                  "normalFrame": 0, "pressedFrame": 2, "hoveredFrame": 1, "disabledFrame": 3}
    else:
        fields = {"rect": {"x": x, "y": y, "width": 32, "height": 32}, "filename": "PANEL\\buysellbtn",
                  "normalFrame": 12 if left else 14, "pressedFrame": 13 if left else 15}
    fields["onClickMessage"] = message(name)
    return {"type": "ButtonWidget", "name": f"Btn_{name}", "fields": fields}


def label(mode: str, text: str, x: int, y: int, w: int, h: int, name: str = "") -> dict:
    style = ({"fontColor": "$FontColorGoldYellow", "pointSize": "$MediumFontSize", "alignment": {"v": "center"}} if mode == "hd" else
             {"fontColor": {"r": 200, "g": 180, "b": 110, "a": 255}, "alignment": {"v": "center"}})
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
              "alwaysAcceptsKeyInput": True, "maxStringLength": 48, "fontType": "8pt", "imeEnabled": False}
    if mode == "hd":
        fields["fontStyle"] = {"alignment": {"v": "center"}, "pointSize": "$MediumFontSize", "fontFace": "BlizzardGlobal"}
    return {"type": "InputTextBoxWidget", "name": INPUT, "fields": fields}


def text_lines(mode: str, m: dict, rows: int) -> list:
    # Before the arrows: D2R hit-tests in list order and the arrows must stay on top.
    width = m["panelW"] - m["rowX"] - m["textX"]
    out = [text_line(mode, f"RowText{i}", m["textX"], m["rowY"] + i * m["rowPitch"], width, m["rowH"]) for i in range(rows)]
    out.append(text_line(mode, "HeaderText", m["textX"], m["headerY"], width - m["rowH"] * 3 // 2, m["rowH"], gold=True))
    out += [text_line(mode, f"StatusText{i}", m["rowX"], m["statusY"] + i * m["statusLineH"], m["panelW"] - 2 * m["rowX"], m["statusLineH"], gold=True) for i in range(STATUS_LINES)]
    return out


def layout(mode: str) -> dict:
    hd = mode == "hd"
    rows = ROWS[mode]
    panel_w, panel_h = (1248, 1359) if hd else (640, 590)
    # HD: native art under the native widgets. Classic graphics have no plain panel art (MENU\\dialogbackground has input boxes painted in), so
    # the classic panel floats over the game.
    children = []
    if hd:
        for i in range(3):
            children.append({"type": "ImageWidget", "name": f"Background{i}", "fields": {"rect": {"x": 0, "y": 453 * i}, "filename": "PANEL\\Modals\\Modal_BG" if i == 0 else "PANEL\\Modals\\Modal_No_Title_BG"}})
    children.append({"type": "ClickCatcherWidget", "name": "ClickCatcher", "fields": {"fitToParent": True}})
    metrics = {"panelX": -panel_w // 2, "panelY": -panel_h // 2, "panelW": panel_w, "panelH": panel_h}
    if hd:
        children.append(label(mode, "D2R-XL 2012 Developer Menu", 400, 18, 500, 44, "Title"))
        children.append(text_button(mode, "close", "X", 1150, 12, 0.14))
        for i, t in enumerate(TABS):
            children.append(text_button(mode, f"tab{i}", t, 28 + i * 240, 66, 0.44))
        children.append(label(mode, "Search / level", 32, 132, 260, 60, "InputLabel"))
        children.append({"type": "ImageWidget", "name": "InputSlot", "fields": {"rect": {"x": 300, "y": 128, "scale": 0.72}, "filename": "PANEL\\Modals\\InputSlot"}})
        children.append(input_box(mode, 326, 138, 490, 54))
        for i, t in enumerate(CATEGORIES):
            children.append(text_button(mode, f"cat{i}", t, 26 + i * 172, 208, 0.31))
        metrics.update({"rowX": 34, "rowY": 262, "rowPitch": 64, "rowH": 64, "textX": 110, "headerY": 1042, "statusY": 1120, "statusLineH": 52,
                        "rowChars": 62, "headerChars": 58, "statusChars": 66})
        children.extend(text_lines(mode, metrics, rows))
        for i in range(rows):
            children.append(arrow_button(mode, f"row{i}", metrics["rowX"], metrics["rowY"] + i * metrics["rowPitch"]))
        children.append(arrow_button(mode, "prev", 34, 1040, left=True))
        children.append(arrow_button(mode, "next", 1150, 1040))
        for i, (name, text) in enumerate(ACTIONS):
            children.append(text_button(mode, name, text, 80, 300 + i * 110, 1.3))
    else:
        children.append(label(mode, "D2R-XL 2012 Developer Menu", 170, 4, 300, 22, "Title"))
        children.append(text_button(mode, "close", "X", 590, 2, 0.28))
        for i, t in enumerate(TABS):
            children.append(text_button(mode, f"tab{i}", t, 8 + i * 124, 26, 0.9))
        children.append(label(mode, "Search / level", 10, 64, 90, 26, "InputLabel"))
        children.append(input_box(mode, 104, 64, 300, 26))
        for i, t in enumerate(CATEGORIES):
            children.append(text_button(mode, f"cat{i}", t, 2 + i * 90, 94, 0.65))
        metrics.update({"rowX": 12, "rowY": 124, "rowPitch": 33, "rowH": 32, "textX": 52, "headerY": 425, "statusY": 462, "statusLineH": 24,
                        "rowChars": 88, "headerChars": 80, "statusChars": 90})
        children.extend(text_lines(mode, metrics, rows))
        for i in range(rows):
            children.append(arrow_button(mode, f"row{i}", metrics["rowX"], metrics["rowY"] + i * metrics["rowPitch"]))
        children.append(arrow_button(mode, "prev", 12, metrics["headerY"] - 2, left=True))
        children.append(arrow_button(mode, "next", 596, metrics["headerY"] - 2))
        for i, (name, text) in enumerate(ACTIONS):
            children.append(text_button(mode, name, text, 60, 130 + i * 70, 3.2))
    root = {"type": "Panel", "name": PANEL, "fields": {"rect": {"x": metrics["panelX"], "y": metrics["panelY"], "width": panel_w, "height": panel_h},
                                                       "anchor": {"x": 0.5, "y": 0.5}, "priority": 8}, "children": children}
    return {"root": root, "metrics": {**metrics, "rows": rows}}


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
            f"{m['textX']}, {m['headerY']}, {m['statusY']}, {m['rowChars']}, {m['headerChars']}, {m['statusChars']}}};")


def header_text() -> str:
    hd, sd = layout("hd"), layout("sd")
    out = ["// Written by tools/devmenu_layout.py (`py -3 -I tools/devmenu_layout.py header`); tools/tests/test_devmenu_layout.py checks it is current.",
           "#pragma once", "", "namespace devmenu_layout {", "",
           f'inline constexpr char PanelLocalId[] = "{PANEL_LOCAL_ID}";', f'inline constexpr char PanelName[] = "{PANEL}";',
           f'inline constexpr char InputName[] = "{INPUT}";', f"inline constexpr int ButtonCount = {len(BUTTONS)};",
           f"inline constexpr int TabCount = {len(TABS)};", f"inline constexpr int CategoryCount = {len(CATEGORIES)};",
           f"inline constexpr int MaxRows = {max(ROWS.values())};", f"inline constexpr int StatusLines = {STATUS_LINES};",
           "inline constexpr const char* ButtonNames[ButtonCount] = {" + ", ".join(f'"{b}"' for b in BUTTONS) + "};", "",
           "struct Metrics {", "\tint panelX, panelY, panelW, panelH;  // the panel's rect, relative to the screen center (anchor 0.5, 0.5)",
           "\tint rows, rowX, rowY, rowPitch, rowH, textX, headerY, statusY;  // panel-local",
           "\tint rowChars, headerChars, statusChars;  // characters that fit one line of that kind", "};", "",
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
