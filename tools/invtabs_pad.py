"""invtabs: the controller (gamepad) panel of a tab, docs/invtabs-pad.md.

D2R's gamepad menu (UISwitcher: Quest Log, Character, Inventory, ..., Options) gets one extra entry through D2RLoader's
controller route (PanelService::registerControllerRoute, PairWithPlayerInventory, AfterPlayerInventory): our panel on the
left, D2R's player inventory on the right, as the stash, Cube and hireling inventory have it. This module is the reference
for that panel's layout: invtabs/src/pad_layout.h builds the same JSON at run time (the grid size comes from invtabs.toml),
and its unit test compares against the golden strings this module writes (`golden`).

Panel (D2R's $ConsoleLeftPanelRect, PANEL_W x PANEL_H; HD only, the gamepad UI is HD in legacy graphics too):
  - the summary area at the top (`invtabs/Summary`, a plain Widget the summary module fills; never smaller than SUMMARY_MIN
    high, it takes whatever the grid leaves),
  - the grid at the bottom (`invtabs/Grid`, an InventoryGridWidget bound to the custom page by the core), centred,
    cellCount = the tab's size, its bottom at GRID_BOTTOM, scaled down (rect scale, thousandths) when the tab does not fit,
  - the background art `d2rloader\\invtabs\\pad_<cols>x<rows>` (PANEL_W x PANEL_H; art lane / core; spec: `art_spec`).
Focus: the panel's default widget is the grid; right from the grid's last column crosses to the inventory
(`panelBoundary`), as on D2R's own left panels. The inventory's left edge (weapon, gloves, grid, gold: D2R's `panelBoundary`)
crosses back. A, X, Y and the right stick on the grid are D2R's own grid controls (pick up / place, drop, use, sort).

  py -3 -I tools/invtabs_pad.py layout [COLS ROWS [SLOT]]   the layout (pretty JSON) on stdout
  py -3 -I tools/invtabs_pad.py art [COLS ROWS]             the art spec (cell rectangles, summary well)
  py -3 -I tools/invtabs_pad.py golden                      writes invtabs/src/pad_golden.inc (C++ test data)
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "invtabs" / "src" / "pad_golden.inc"

PLUGIN = "invtabs"
PANEL_W, PANEL_H = 1305, 1421       # D2R _profilehd.json $ConsoleLeftPanelRect (controller); the Cube / stash / hireling panels
CELL = 98                           # $ItemCellSize (HD)
MARGIN = 60                         # left / right / top inner margin of the panel art
GRID_BOTTOM = 1371                  # the grid's lower edge (50 above the panel's bottom)
GAP = 30                            # between the summary area and the grid
SUMMARY_MIN = 240                   # the summary area is never lower than this
FIELD_W = PANEL_W - 2 * MARGIN      # 1185: widest grid at scale 1 is 12 columns
MARKER_BASE = 7400                  # the core's grid marker: chronicleFlourishOffset {7400 + slot, 7400} (docs/invtabs.md)
MAX_CELLS = 16                      # the custom page is 16 x 16
GOLDEN_SIZES = ((10, 6, 0), (10, 4, 0), (12, 8, 0), (16, 16, 0), (1, 1, 3), (16, 2, 11))


@dataclass(frozen=True)
class Spec:
    cols: int = 10
    rows: int = 6
    slot: int = 0                   # the core's tab slot N: panel invtabs/Pad<N>, grid marker 7400 + N

    def __post_init__(self):
        if not (1 <= self.cols <= MAX_CELLS and 1 <= self.rows <= MAX_CELLS):
            raise ValueError(f"tab size {self.cols} x {self.rows}: each side 1..{MAX_CELLS}")
        if not 0 <= self.slot <= 63:
            raise ValueError(f"slot {self.slot}: 0..63")


def local_id(spec: Spec) -> str:
    return f"Pad{spec.slot}"


def panel_name(spec: Spec) -> str:
    return f"{PLUGIN}/{local_id(spec)}"


def layout_path(spec: Spec) -> str:
    """Where the core registers the layout (ResourceService, the plugin's panel-layout namespace)."""
    return f"data/global/ui/layouts/{PLUGIN}/{local_id(spec)}hd.json"


def background(spec: Spec) -> str:
    return f"d2rloader\\{PLUGIN}\\pad_{spec.cols}x{spec.rows}"


def geometry(spec: Spec) -> dict:
    """Integer geometry in panel pixels: scale in thousandths, grid and summary rectangles (x, y, w, h)."""
    avail_h = GRID_BOTTOM - (MARGIN + SUMMARY_MIN + GAP)
    milli = min(1000, FIELD_W * 1000 // (spec.cols * CELL), avail_h * 1000 // (spec.rows * CELL))
    gw, gh = spec.cols * CELL * milli // 1000, spec.rows * CELL * milli // 1000
    gx, gy = (PANEL_W - gw + 1) // 2, GRID_BOTTOM - gh  # odd spare pixel on the left: 10 columns at x 163, as CharmInv
    return {"scale_milli": milli, "grid": (gx, gy, gw, gh), "cell": CELL * milli / 1000,
            "summary": (MARGIN, MARGIN, FIELD_W, gy - GAP - MARGIN)}


def scale_text(milli: int) -> str:
    """The scale as JSON writes it: 0.663, 0.7, 0.05 (shortest decimal; pad_layout.h writes the same)."""
    return ("%d.%03d" % divmod(milli, 1000)).rstrip("0").rstrip(".")


def layout(spec: Spec = Spec()) -> dict:
    g = geometry(spec)
    gx, gy, _gw, _gh = g["grid"]
    sx, sy, sw, sh = g["summary"]
    rect = {"x": gx, "y": gy}
    if g["scale_milli"] < 1000:
        rect["scale"] = float(scale_text(g["scale_milli"]))
    return {
        "type": "Panel", "name": panel_name(spec),
        "fields": {"priority": 10, "rect": "$ConsoleLeftPanelRect", "anchor": "$LeftPanelAnchor", "defaultWidget": f"{PLUGIN}/Grid"},
        "children": [
            {"type": "ClickCatcherWidget", "name": f"{PLUGIN}/PadClickCatcher",
             "fields": {"rect": {"x": 0, "y": 0, "width": 0, "height": 0}, "fitToParent": True}},
            {"type": "ImageWidget", "name": f"{PLUGIN}/PadBackground",
             "fields": {"rect": {"x": 0, "y": 0}, "filename": background(spec)}},
            {"type": "Widget", "name": f"{PLUGIN}/Summary",
             "fields": {"rect": {"x": sx, "y": sy, "width": sw, "height": sh}}},
            {"type": "InventoryGridWidget", "name": f"{PLUGIN}/Grid",
             "fields": {"rect": rect, "cellCount": {"x": spec.cols, "y": spec.rows}, "cellSize": "$ItemCellSize",
                        "gemSocketFilename": "PANEL\\gemsocket",
                        "chronicleFlourishOffset": {"x": MARKER_BASE + spec.slot, "y": MARKER_BASE},
                        "navigation": {"right": {"panelBoundary": True}}}},
        ],
    }


def dumps(lay: dict) -> str:
    """Compact JSON, exactly as pad_layout.h writes it (key order kept, no spaces, ASCII)."""
    return json.dumps(lay, separators=(",", ":"), ensure_ascii=True)


def art_spec(spec: Spec = Spec()) -> dict:
    """What the panel art must show, in panel pixels: its size, the summary well and every grid cell."""
    g = geometry(spec)
    gx, gy, _gw, _gh = g["grid"]
    c = g["cell"]
    cells = [[round(gx + i * c), round(gy + j * c), round(c), round(c)] for j in range(spec.rows) for i in range(spec.cols)]
    return {"sprite": f"data/hd/global/ui/{background(spec).replace(chr(92), '/')}.sprite", "size": [PANEL_W, PANEL_H],
            "summary": list(g["summary"]), "grid": list(g["grid"]), "scale": g["scale_milli"] / 1000, "cells": cells}


def golden_text() -> str:
    lines = ["// Generated by tools/invtabs_pad.py golden: the controller panel layouts pad_layout.h must reproduce byte for byte.",
             "// Do not edit; run `py -3 -I tools/invtabs_pad.py golden` after changing the generator.",
             "struct PadGolden { int cols, rows, slot; const char* json; };",
             "inline constexpr PadGolden kPadGolden[] = {"]
    for cols, rows, slot in GOLDEN_SIZES:
        text = dumps(layout(Spec(cols, rows, slot)))
        lines.append('\t{%d, %d, %d, R"PADJSON(%s)PADJSON"},' % (cols, rows, slot, text))
    lines.append("};")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    nums = [int(a) for a in argv[1:]]
    if argv[:1] == ["layout"]:
        print(json.dumps(layout(Spec(*nums)), indent=1))
        return 0
    if argv[:1] == ["art"]:
        print(json.dumps(art_spec(Spec(*nums))))
        return 0
    if argv[:1] == ["golden"]:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(golden_text(), "utf-8", newline="\n")
        print(f"{GOLDEN.relative_to(ROOT)}: {len(GOLDEN_SIZES)} layouts")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
