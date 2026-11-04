"""Personal stash page 2 (plugin part `stashpage2`, docs/plugin-plan.md section 8.2): the layouts of its page strip and panel.

D2RLoader gives a plugin ONE custom player page (item page 6 of the .d2s plus `<char>.d2rl`, saved and restored by D2RCore); the
plugin (plugin/src/stash_pages.cpp) registers it at the stock stash's 10 x 10 and shows it in its own panel
`mxl2012-core/StashPage2`, a copy of the stock personal stash (same picture, same grid place) without tabs and gold. Both panels
get two arrows exactly where D2R's shared stash has its page arrows (StashNavigation):

  stock stash   `MxlPersonalNavigation` in `basicstash_container` (HD: tools/ui_layouts.stash_hd; classic:
                tools/rotw_stash_legacy.classic_layout), arrows only. They send PanelManager:TogglePanel:mxl2012-core/StashPage2.
                On the Shared tab D2R's own arrows and "Page n / m" draw over them (SharedStashTabContainer comes after the
                strip); the Gems / Materials / Runes tabs hide basicstash_container with it. The plugin cannot hide the strip
                per tab: D2R 3.3 sends BankPanelMessage:SelectTab with an empty text (seen in game), so it hides it only when
                the page could not be registered (part off, another plugin owns the page).
  page 2 panel  `MxlPageNavigation` "2 / 2": its arrows open the stock stash again (PanelManager:OpenPanel:BankExpansionLayout).
                Both panels take D2R's left panel slot, so opening one closes the other (seen in game: the plugin panel's
                TogglePanel is followed by ClosePanel:BankExpansionLayout); a ClosePanel of the plugin panel alone left no
                stash on screen. Its X closes the stock stash (PanelManager:ClosePanel:BankExpansionLayout). Esc closes the
                plugin panel.

All of it is D2R's own PanelManager messages: no plugin code is in the switch. The panel's two layouts (HD `StashPage2hd.json`,
classic `StashPage2.json`) are strict JSON and go into the plugin as C++ strings (`header`, plugin/src/mxl_stash_page.h, committed;
tools/tests/test_stash_page2.py checks that it is current). Text is written out (no `@key`: docs/bugs.md #30).

  py -3 -I tools/stash_page2.py header     write plugin/src/mxl_stash_page.h
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER = ROOT / "plugin" / "src" / "mxl_stash_page.h"

PLUGIN_ID = "mxl2012-core"
STOCK_PANEL = "BankExpansionLayout"          # the stock stash's PanelManager name: its layout's root
PANEL_LOCAL_ID = "StashPage2"
PANEL = f"{PLUGIN_ID}/{PANEL_LOCAL_ID}"
GRID = f"{PLUGIN_ID}/StashPage2Grid"
STRIP = "MxlPersonalNavigation"              # on the stock stash
PAGE_STRIP = "MxlPageNavigation"             # on the plugin panel
PAGES = 2
GRID_CELLS = (10, 10)                        # the stock personal stash (inventory.txt Big Bank, Median 2012's 10 x 10)

# HD (bankexpansionlayouthd.json): D2R's shared stash arrows `StashNavigation` (420 x 93 at 369, 1211; arrows 64 x 64) and the
# personal grid at 89, 219
HD_NAV = (369, 1211, 420, 93)
HD_GRID = (89, 219)
HD_ARROW = {"normalFrame": 0, "pressedFrame": 2, "hoveredFrame": 1, "disabledFrame": 3}
# classic (bankexpansionlayout.json): `StashNavigation` 164 x 32 at 15, 385 (buysellbtn frames 12-15), the grid at 15, 63, the
# close button buysellbtn 10 / 11 at 272, 384 of the 320 x 432 panel
SD_NAV = (15, 385, 164, 32)
SD_GRID = (15, 63)
SD_CLOSE = (272, 384)
TEXT_STYLE = {"fontColor": "$PanelTitleColor", "pointSize": "$MediumFontSize", "alignment": {"v": "center", "h": "center"},
              "spacing": "$MinimumSpacing", "dropShadow": "$DefaultDropShadow"}


def page_text(page: int) -> str:
    return f"{page} / {PAGES}"


def page_label(page: int, rect: dict) -> list:
    """The "2 / 2" text of page 2's strip. The stock strip has none: on the Shared tab D2R draws its own "Page n / m" there,
    and the plugin cannot hide our strip on that tab (D2R 3.3's BankPanelMessage:SelectTab has no tab index in its text)."""
    if page == 1:
        return []
    return [{"type": "TextBoxWidget", "name": "MxlPageText", "fields": {"text": page_text(page), "rect": rect, "style": TEXT_STYLE}}]


def hd_strip(name: str, page: int, message: str) -> dict:
    """D2R's HD shared-stash arrows (StashNavigation) with our name, text and message."""
    x, y, w, h = HD_NAV
    return {"type": "ImageWidget", "name": name, "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}},
            "children": [
                {"type": "ButtonWidget", "name": "MxlPageLeft",
                 "fields": {"rect": {"x": 29, "y": 13, "width": 64, "height": 64}, "filename": "PANEL\\Stash\\Stash_LeftArrow",
                            **HD_ARROW, "onClickMessage": message}},
                *page_label(page, {"x": 95, "y": 13, "width": 230, "height": 64}),
                {"type": "ButtonWidget", "name": "MxlPageRight",
                 "fields": {"rect": {"x": 327, "y": 13, "width": 64, "height": 64}, "filename": "PANEL\\Stash\\Stash_RightArrow",
                            **HD_ARROW, "onClickMessage": message}}]}


def sd_strip(name: str, page: int, message: str) -> dict:
    """D2R's classic shared-stash arrows (StashNavigation, buysellbtn) with our name, text and message."""
    x, y, w, h = SD_NAV
    return {"type": "Widget", "name": name, "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}},
            "children": [
                {"type": "ButtonWidget", "name": "MxlPageLeft",
                 "fields": {"rect": {"x": 0, "y": 0, "width": 32, "height": 32}, "filename": "PANEL\\buysellbtn",
                            "normalFrame": 12, "pressedFrame": 13, "onClickMessage": message}},
                *page_label(page, {"x": 42, "y": 5, "width": 105, "height": 23}),
                {"type": "ButtonWidget", "name": "MxlPageRight",
                 "fields": {"rect": {"x": 153, "y": 0, "width": 32, "height": 32}, "filename": "PANEL\\buysellbtn",
                            "normalFrame": 14, "pressedFrame": 15, "onClickMessage": message}}]}


def stock_strip_hd() -> dict:
    return hd_strip(STRIP, 1, f"PanelManager:TogglePanel:{PANEL}")


def stock_strip_sd() -> dict:
    return sd_strip(STRIP, 1, f"PanelManager:TogglePanel:{PANEL}")


def grid(x: int, y: int) -> dict:
    return {"type": "InventoryGridWidget", "name": GRID,
            "fields": {"rect": {"x": x, "y": y}, "cellCount": {"x": GRID_CELLS[0], "y": GRID_CELLS[1]}, "cellSize": "$ItemCellSize",
                       "gemSocketFilename": "PANEL\\gemsocket"}}


def panel_hd() -> dict:
    """The plugin panel in HD: D2R's stash panel (bankoriginallayouthd.json: frame, hinge, title, close) with the personal
    stash picture and grid place of bankexpansionlayouthd.json, the page strip and nothing else."""
    return {
        "type": "Panel", "name": PANEL,
        "fields": {"priority": 5, "rect": "$LeftPanelRect", "anchor": "$LeftPanelAnchor"},
        "children": [
            {"type": "ClickCatcherWidget", "name": "click_catcher", "fields": {"rect": "$PanelClickCatcherRect"}},
            {"type": "ImageWidget", "name": "background", "fields": {"filename": "PANEL\\Stash\\StashPanel_BG_Personal"}},
            {"type": "ImageWidget", "name": "LeftHinge", "fields": {"rect": "$LeftHingeRect", "filename": "$LeftHingeSprite"}},
            {"type": "TextBoxWidget", "name": "title", "fields": {"rect": "$InGamePanelTitleRect", "style": "$StyleTitleBlock", "text": "Stash"}},
            {"type": "ButtonWidget", "name": "close",
             "fields": {"rect": {"x": 1075, "y": 9}, "filename": "PANEL\\closebtn_4x", "hoveredFrame": 3, "tooltipString": "Close",
                        "sound": "cursor_close_window_hd", "onClickMessage": f"PanelManager:ClosePanel:{STOCK_PANEL}"}},
            hd_strip(PAGE_STRIP, 2, f"PanelManager:OpenPanel:{STOCK_PANEL}"),
            grid(*HD_GRID),
        ],
    }


def panel_sd() -> dict:
    """The plugin panel in classic graphics: D2R's bankoriginallayout.json / bankexpansionlayout.json frame (320 x 432,
    expandedstash picture, buysellbtn close), the grid at the personal stash's place, the page strip."""
    return {
        "type": "Panel", "name": PANEL,
        "fields": {"priority": 5, "rect": {"x": -320, "y": -240, "width": 320, "height": 432}, "anchor": "$LeftPanelAnchor"},
        "children": [
            {"type": "ClickCatcherWidget", "name": "click_catcher", "fields": {"rect": {"width": 320, "height": 432}}},
            {"type": "GridImageWidget", "name": "background", "fields": {"filename": "PANEL\\expandedstash", "frames": 4, "rows": 2}},
            {"type": "ButtonWidget", "name": "close",
             "fields": {"rect": {"x": SD_CLOSE[0], "y": SD_CLOSE[1]}, "filename": "PANEL\\buysellbtn", "normalFrame": 10,
                        "pressedFrame": 11, "tooltipString": "Close", "tooltipOffset": {"x": 0, "y": -3},
                        "onClickMessage": f"PanelManager:ClosePanel:{STOCK_PANEL}"}},
            sd_strip(PAGE_STRIP, 2, f"PanelManager:OpenPanel:{STOCK_PANEL}"),
            grid(*SD_GRID),
        ],
    }


def _cstring(name: str, text: str) -> str:
    lines = [json.dumps(line + "\n") for line in text.split("\n")]
    return f"inline constexpr char {name}[] =\n" + "\n".join(f"    {l}" for l in lines) + ";\n"


def header() -> str:
    """plugin/src/mxl_stash_page.h: names and both panel layouts as C++ strings."""
    return ("// Generated by tools/stash_page2.py (header); do not edit.\n#pragma once\n\nnamespace mxl_stash_page {\n\n"
            f'inline constexpr char PanelLocalId[] = "{PANEL_LOCAL_ID}";\n'
            f'inline constexpr char GridName[] = "{GRID}";\n'
            f'inline constexpr char StockPanel[] = "{STOCK_PANEL}";\n'
            f'inline constexpr char StockStrip[] = "{STRIP}";\n'
            f"inline constexpr unsigned Width = {GRID_CELLS[0]}, Height = {GRID_CELLS[1]};\n"
            + _cstring("LayoutHd", json.dumps(panel_hd(), indent=1))
            + _cstring("LayoutClassic", json.dumps(panel_sd(), indent=1))
            + "\n}  // namespace mxl_stash_page\n")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["header"]:
        print(__doc__)
        return 2
    HEADER.write_text(header(), encoding="utf-8", newline="\n")
    print(f"{HEADER}: {HEADER.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
