"""Personal stash page 2 (plugin part `stashpage2`, docs/plugin-plan.md section 8.2): the layouts of its page strip and panel.

D2RLoader gives a plugin ONE custom player page (item page 6 of the .d2s plus `<char>.d2rl`, saved and restored by D2RCore); the
plugin (plugin/src/stash_pages.cpp) registers it at the stock stash's 10 x 10 and shows it in its own panel
`mxl2012-core/StashPage2`. That panel is an overlay ON the open stock stash (same rect and anchor), not a stash of its own: it
holds only page 2's grid (at the stock grid's place) and its "2 / 2" strip. The stock stash stays open under it, so its frame,
tabs, gold box, X and D2R's left border (PanelBordersPanel) stay as they are (bug #543: the 0.1.11 panel took D2R's left slot,
which closed the stock stash; page 2 had no tabs or gold and the left border was gone after the way back). While page 2 shows,
the plugin hides the stock grid and the stock strip. Both panels get two arrows exactly where D2R's shared stash has its page
arrows (StashNavigation):

  stock stash   `MxlPersonalNavigation` in `basicstash_container` (HD: tools/ui_layouts.stash_hd; classic:
                tools/rotw_stash_legacy.classic_layout), arrows only. They send MxlStashPage:Show:2.
                On the Shared tab D2R's own arrows and "Page n / m" draw over them (SharedStashTabContainer comes after the
                strip); the Gems / Materials / Runes tabs hide basicstash_container with it. The plugin cannot hide the strip
                per tab: D2R 3.3 sends BankPanelMessage:SelectTab with an empty text (seen in game), so it hides it only when
                the page could not be registered (part off, another plugin owns the page). For the same reason the stock strip
                has no "1 / 2" text: it would show under D2R's "Page n / m" on the Shared tab.
  page 2 panel  `MxlPageNavigation` "2 / 2": its arrows send MxlStashPage:Show:1.

`MxlStashPage:Show:<page>` is the plugin's own message (its UI message listener takes it, D2R never sees it). A tab click, the
stock X and the stock stash opening or closing also bring page 1 back (stash_pages.cpp).

The panel's two layouts (HD `StashPage2hd.json`, classic `StashPage2.json`) are strict JSON and go into the plugin as C++ strings (`header`, plugin/src/mxl_stash_page.h, committed;
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
STOCK_GRID = "grid"                          # the stock personal grid (hidden while page 2 shows)
PAGES = 2
# the arrows' messages, page -> message. D2R passes only known targets to plugin UI listeners, so they are PanelManager
# messages naming the plugin panel; stash_pages.cpp consumes them and shows the page itself.
SHOW = {1: f"PanelManager:ClosePanel:{PANEL}", 2: f"PanelManager:OpenPanel:{PANEL}"}
GRID_CELLS = (10, 10)                        # the stock personal stash (inventory.txt Big Bank, Median 2012's 10 x 10)

# HD (bankexpansionlayouthd.json): D2R's shared stash arrows `StashNavigation` (420 x 93 at 369, 1211; arrows 64 x 64) and the
# personal grid at 89, 219
HD_NAV = (369, 1211, 420, 93)
HD_GRID = (89, 219)
HD_ARROW = {"normalFrame": 0, "pressedFrame": 2, "hoveredFrame": 1, "disabledFrame": 3}
# classic (bankexpansionlayout.json): `StashNavigation` 164 x 32 at 15, 385 (buysellbtn frames 12-15), the grid at 15, 63, the
# 320 x 432 panel
SD_NAV = (15, 385, 164, 32)
SD_GRID = (15, 63)
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
    return hd_strip(STRIP, 1, SHOW[2])


def stock_strip_sd() -> dict:
    return sd_strip(STRIP, 1, SHOW[2])


def grid(x: int, y: int) -> dict:
    return {"type": "InventoryGridWidget", "name": GRID,
            "fields": {"rect": {"x": x, "y": y}, "cellCount": {"x": GRID_CELLS[0], "y": GRID_CELLS[1]}, "cellSize": "$ItemCellSize",
                       "gemSocketFilename": "PANEL\\gemsocket"}}


def panel_hd() -> dict:
    """The plugin panel in HD: the stock stash panel's rect and anchor (bankoriginallayouthd.json), page 2's grid at the
    personal grid's place of bankexpansionlayouthd.json and the page strip, nothing else: no click catcher, so the stock
    stash's tabs, gold and X under it take their clicks. Priority 6: drawn over the stock stash (5)."""
    return {
        "type": "Panel", "name": PANEL,
        "fields": {"priority": 6, "rect": "$LeftPanelRect", "anchor": "$LeftPanelAnchor"},
        "children": [hd_strip(PAGE_STRIP, 2, SHOW[1]), grid(*HD_GRID)],
    }


def panel_sd() -> dict:
    """The plugin panel in classic graphics: the rect of D2R's bankoriginallayout.json (320 x 432), the grid at the personal
    stash's place, the page strip."""
    return {
        "type": "Panel", "name": PANEL,
        "fields": {"priority": 6, "rect": {"x": -320, "y": -240, "width": 320, "height": 432}, "anchor": "$LeftPanelAnchor"},
        "children": [sd_strip(PAGE_STRIP, 2, SHOW[1]), grid(*SD_GRID)],
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
            f'inline constexpr char StockGrid[] = "{STOCK_GRID}";\n'
            f'inline constexpr char PanelName[] = "{PANEL}";\n'
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
