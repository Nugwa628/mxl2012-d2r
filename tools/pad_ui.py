"""The mod's panels in D2R's gamepad (controller) UI: the inventory sized for Median's backpack with the Send to stash button
(bug #556) and the stash with the MEDIAN / ORBS tabs and Median's Gems / Runes pages (bug #557). docs/controller-support.md.

D2R loads data/global/ui/layouts/controller/<layout>.json while the gamepad UI is on (in legacy graphics too: it draws HD).
A step of tools/build.py after tools/median_tabs.py (it reads the finished keyboard / mouse layouts of work/mod/data):

  controller/playerinventoryoriginallayouthd.json, controller/playerinventoryexpansionlayouthd.json
      D2R's gamepad inventories (`basedOn` the PC ones, so they inherited the mod's PC grid scale 1.0745 and cell size: the
      right column and rows 5-6 ran out of the 10 x 4 frame) with their own grid fields: Median's 10 x 6 at GRID_SCALE on
      D2R's gamepad art grown to 6 rows (PANEL\\mxl\\padinventory, _classic), the gold button and the three Send to stash
      buttons (tools/send_stash.py; the plugin part send_stash finds them by name in either panel) in the free stone left and
      right of the belt row, and navigation through them (gloves -> send -> grid, boots -> gold -> grid).
  controller/bankexpansionlayouthd.json (tools/ui_layouts.stash_hd: D2R's with the mod's stash cube; rewritten here)
      the seven tabs of the PC layout (tools/median_tabs.py; PANEL\\mxl\\medtab_tabs_pad), and the PC layout's Gems /
      Materials / Runes pages with every slot, the MEDIAN / ORBS / Median materials pictures and the selector moved by
      PAGE_SHIFT: D2R's gamepad pages are its PC pages without the outer frame, at that offset (measured on the art). Their
      backgrounds (PANEL\\mxl\\padstash_*) are D2R's gamepad pages with the PC page's inside (the mod's Gems / Runes art,
      D2R's Materials) pasted at the same offset. The plugin part medtab finds its widgets by name, so it drives this panel too.

  py -3 -I tools/pad_ui.py build [DATA]   (default work/mod/data)
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

LAYOUTS = Path("global") / "ui" / "layouts"
CONTROLLER = LAYOUTS / "controller"
MXL_ART = Path("hd") / "global" / "ui" / "panel" / "mxl"

# ---- inventory -------------------------------------------------------------------------------------------------------
# D2R's gamepad inventory art (1015 x 1400, drawn at panel x 196, y 43: "anchor" 0.5 / 0.5 and "rect" -508, -700 in the
# 1408 x 1486 $ConsoleRightPanelRect). Its grid: cells 98 apart from x 20, y 850 (rect 216, 893), the parchment bar above
# from y 830, the bottom line at 1241; below it the gold plate (gone here).
INV_ART = {"PlayerInventoryExpansionLayout": ("controller/panel/inventorypanel/v2/inventorybg", "padinventory"),
           "PlayerInventoryOriginalLayout": ("controller/panel/inventorypanel/v2/inventorybg_classic", "padinventory_classic")}
INV_ORIGIN = (196, 43)              # the art's top left in panel coordinates
ART_W, ART_H = 1015, 1400
CELL = 98
GRID_ART = (20, 850)                # first cell in the art
BAND_TOP = 830                      # the parchment bar: the grid block starts here
GRID_ROWS = 6                       # Median's backpack (inventory.txt: 10 x 6)
# 6 rows of 98 do not fit under the belt row in the frame the stash / cube draw round the inventory (1411 high, the art
# 1400 from its top): the grid block is scaled to end at the art's bottom
GRID_SCALE = round((ART_H - BAND_TOP - 8) / (GRID_ART[1] - BAND_TOP + GRID_ROWS * CELL + 2), 3)
# the stone left and right of the belt row, under the gloves / boots boxes (art pixels): send buttons, gold
SEND_RECT = (100, 773, 64, 62)
GOLD_RECT = (770, 783, 232, 44)
GOLD_TEXT = (54, 0, 172, 48)        # the amount inside the gold button (D2R: button 551, text 605, 257 wide in 317)
SEND_ART = "sendstash_pad"


def grid_block(art):
    """D2R's 4-row grid block (from the parchment bar to the bottom line) grown to GRID_ROWS by repeating its second row."""
    from PIL import Image
    y0, y1 = GRID_ART[1] + CELL, GRID_ART[1] + 2 * CELL           # row 1
    last = GRID_ART[1] + 3 * CELL                                  # row 3 and the bottom line
    parts = [art.crop((0, BAND_TOP, ART_W, y1))] + [art.crop((0, y0, ART_W, y1))] * (GRID_ROWS - 3) + \
            [art.crop((0, last, ART_W, last + CELL + 2))]
    out = Image.new("RGBA", (ART_W, sum(p.height for p in parts)))
    y = 0
    for p in parts:
        out.paste(p, (0, y))
        y += p.height
    return out


def inventory_art(art):
    """(picture, grid origin in the picture): D2R's top half, the grown grid scaled by GRID_SCALE and centred, no gold plate."""
    from PIL import Image
    block = grid_block(art)
    w, h = round(block.width * GRID_SCALE), round(block.height * GRID_SCALE)
    small = block.resize((w, h), Image.LANCZOS)
    out = Image.new("RGBA", (ART_W, ART_H))
    out.paste(art.crop((0, 0, ART_W, BAND_TOP)), (0, 0))
    bx = (ART_W - w) // 2
    out.alpha_composite(small, (bx, BAND_TOP))
    return out, (bx + GRID_ART[0] * GRID_SCALE, BAND_TOP + (GRID_ART[1] - BAND_TOP) * GRID_SCALE)


def panel_rect(x: float, y: float, w: float | None = None, h: float | None = None, scale: float | None = None) -> dict:
    r = {"x": round(x + INV_ORIGIN[0]), "y": round(y + INV_ORIGIN[1])}
    if w is not None:
        r.update(width=round(w), height=round(h))
    if scale is not None:
        r["scale"] = scale
    return r


def send_buttons() -> list[dict]:
    """tools/send_stash.py's three buttons at SEND_RECT with the gamepad's legend and navigation."""
    import send_stash
    x, y, w, h = SEND_RECT
    out = []
    for b in send_stash.widgets(hd=True):
        f = b["fields"]
        f["rect"] = panel_rect(x, y, w, h)
        f["filename"] = f"PANEL\\mxl\\{SEND_ART}"
        f["navigation"] = {"left": {"panelBoundary": True}, "up": {"name": "slot_gloves"}, "right": {"name": "slot_right_hand"},
                           "down": {"name": "grid"}}
        f["buttonLegendAction"] = "select"
        f["buttonLegendString"] = send_stash.TIP.split("\n")[0]
        out.append(b)
    return out


def load(text: str) -> dict:
    """D2R's layout json: lenient_json plus the comments after a value (`"x": 1, // ...`) the gamepad files have."""
    from rotw_stash_legacy import lenient_json
    return lenient_json(re.sub(r'\s//[^\n"]*$', "", text, flags=re.M))


def child(node: dict, name: str) -> dict:
    hit = next((c for c in node.get("children", []) if c.get("name") == name), None)
    if hit is None:
        raise ValueError(f"{node.get('name')}: no child {name}")
    return hit


def set_nav(widget: dict, **dirs: str | None) -> None:
    nav = widget.setdefault("fields", {}).setdefault("navigation", {})
    for d, target in dirs.items():
        if target is None:
            nav.pop(d, None)
        else:
            nav[d] = {"name": target}


def inventory_original(text: str) -> dict:
    """D2R's controller/playerinventoryoriginallayouthd.json: the classic art, Median's grid, gold and send buttons."""
    lay = load(text)
    child(lay, "background")["fields"]["filename"] = f"PANEL\\mxl\\{INV_ART['PlayerInventoryOriginalLayout'][1]}"
    gx, gy = grid_origin()
    grid = child(lay, "grid")["fields"]
    grid["rect"] = panel_rect(gx, gy, scale=GRID_SCALE)
    grid["cellCount"] = {"x": 10, "y": GRID_ROWS}
    grid["cellSize"] = {"x": CELL, "y": CELL}
    x, y, w, h = GOLD_RECT
    child(lay, "gold_button")["fields"]["rect"] = panel_rect(x, y, w, h)
    tx, ty, tw, th = GOLD_TEXT
    child(lay, "gold_amount")["fields"]["rect"] = panel_rect(x + tx, y + ty, tw, th)
    set_nav(child(lay, "grid"), down=None)
    set_nav(child(lay, "gold_button"), left="slot_left_hand", up="slot_feet", down="grid")
    set_nav(child(lay, "slot_feet"), down="gold_button")
    set_nav(child(lay, "slot_gloves"), down=send_buttons()[-1]["name"])
    at = lay["children"].index(child(lay, "gold_button")) + 1
    lay["children"][at:at] = send_buttons()
    return lay


def inventory_expansion(text: str) -> dict:
    """D2R's controller/playerinventoryexpansionlayouthd.json (`basedOn` the original above): the expansion art, the send
    buttons named in its child list (a child the derived file does not name is not drawn)."""
    lay = load(text)
    child(lay, "background")["fields"]["filename"] = f"PANEL\\mxl\\{INV_ART['PlayerInventoryExpansionLayout'][1]}"
    at = lay["children"].index(child(lay, "gold_button")) + 1
    lay["children"][at:at] = [{"type": b["type"], "name": b["name"]} for b in send_buttons()]
    return lay


_GRID_ORIGIN: list[tuple[float, float]] = []


def grid_origin() -> tuple[float, float]:
    """The grid's first cell in the art (inventory_art's, the same for both pictures)."""
    if not _GRID_ORIGIN:
        from PIL import Image
        _GRID_ORIGIN.append(inventory_art(Image.new("RGBA", (ART_W, ART_H)))[1])
    return _GRID_ORIGIN[0]


# ---- stash -----------------------------------------------------------------------------------------------------------
PAGES = ("advancedstash_gems", "advancedstash_materials", "advancedstash_runes")
PAGE_SHIFT = (66, -72)              # PC page slot -> gamepad page slot (D2R's own: gcw 164, 232 -> 230, 160; r01 114, 268 -> 180, 196)
ART_SHIFT = (68, -172)              # PC page art -> gamepad page art (drawn at -2, 100: the same offset in panel pixels)
PAGE_FIELD = (86, 212, 1077, 1430)  # the PC page's inside (median_tabs.FIELD)
PAGE_ART = {"gems": ("panel/stash/additionalstash/panel_additionalstash_gems",
                     "controller/panel/stash/v2/additionalstash/advancedstash_gems_console"),
            "consumables": ("panel/stash/additionalstash/panel_additionalstash_consumables",
                            "controller/panel/stash/v2/additionalstash/advancedstash_consumables_console"),
            "runes": ("panel/stash/additionalstash/panel_additionalstash_runes",
                      "controller/panel/stash/v2/additionalstash/advancedstash_runes_console")}
PAD_TAB_W = 1075 // 7               # D2R's 5 x 215 row shared by 7
PAD_TAB_FONT = 22


def shifted(widget: dict, dx: int, dy: int) -> dict:
    w = copy.deepcopy(widget)
    r = w.get("fields", {}).get("rect")
    if isinstance(r, dict):
        r["x"] = r.get("x", 0) + dx
        r["y"] = r.get("y", 0) + dy
    return w


def stash(ctrl: dict, pc: dict) -> dict:
    """The gamepad stash with the PC layout's seven tabs and pages (pc: the finished bankexpansionlayouthd.json)."""
    import median_tabs
    if median_tabs.applied(ctrl):
        raise ValueError("the gamepad stash layout has 7 tabs already")
    pc_tabs = median_tabs.find(pc, "BankTabs")["fields"]
    t = median_tabs.find(ctrl, "BankTabs")["fields"]
    t.update({"tabCount": median_tabs.HD_TABS, "filename": "PANEL\\mxl\\medtab_tabs_pad",
              "inactiveFrames": pc_tabs["inactiveFrames"], "activeFrames": pc_tabs["activeFrames"],
              "disabledFrames": pc_tabs["disabledFrames"], "textStrings": pc_tabs["textStrings"],
              "tabSize": {"x": PAD_TAB_W, "y": t["tabSize"]["y"]}, "textStyle": {"pointSize": PAD_TAB_FONT}})
    dx, dy = PAGE_SHIFT
    for page in PAGES:
        median_tabs.find(ctrl, page)["children"] = [shifted(c, dx, dy) for c in median_tabs.find(pc, page)["children"]]
    # the PC root's pictures and selectors (median_tabs.place): each before / after the same page widget as there
    root, pc_root = ctrl["children"], pc["children"]
    for i, c in enumerate(pc_root):
        if not c.get("name", "").startswith("medtab_"):
            continue
        nxt = next(p["name"] for p in pc_root[i + 1:] if p.get("name") in PAGES + ("advancedstash_horadriccube",))
        at = next(j for j, p in enumerate(root) if p.get("name") == nxt)
        root.insert(at, shifted(c, dx, dy))
    files = ctrl["fields"]["backgroundFile"]
    files[2:5] = [f"PANEL\\mxl\\padstash_{p}" for p in ("gems", "consumables", "runes")]
    return ctrl


def page_art(pc_art, pad_art):
    """D2R's gamepad page with the PC page's inside pasted at ART_SHIFT."""
    out = pad_art.convert("RGBA").copy()
    x0, y0, x1, y1 = PAGE_FIELD
    out.paste(pc_art.convert("RGBA").crop(PAGE_FIELD), (x0 + ART_SHIFT[0], y0 + ART_SHIFT[1]))
    return out


# ---- build -----------------------------------------------------------------------------------------------------------
def art(data: Path, report: list[str]) -> None:
    import fxpaths
    import median_stash
    import median_tabs
    import rotw_stash_legacy as rsl
    import send_stash
    import ui_art
    d2r = rsl.D2R(fxpaths.D2R, use_cache=True)
    out = data / MXL_ART
    out.mkdir(parents=True, exist_ok=True)

    def write(name, frames):
        ui_art.write_sprite(out / f"{name}.sprite", frames)
        ui_art.write_sprite(out / f"{name}.lowend.sprite", [median_stash.lowend(f) for f in frames])
    for src, name in INV_ART.values():
        im, _origin = inventory_art(d2r.sprite(src)[0])
        write(name, [im])
    write(SEND_ART, send_stash.hd_frames(*SEND_RECT[2:]))
    for page, (pc_rel, pad_rel) in PAGE_ART.items():
        mod = data / "hd" / "global" / "ui" / f"{pc_rel}.sprite"   # the mod's Gems / Runes pages (tools/median_stash.py)
        pc_art = ui_art.read_sprite(mod)[0] if mod.exists() else d2r.sprite(pc_rel)[0]
        write(f"padstash_{page}", [page_art(pc_art, d2r.sprite(pad_rel)[0])])
    tabs = median_tabs.tab_frames(d2r.sprite("controller/panel/stash/v2/additionalstash/ctrl_tabs_215_tga"), PAD_TAB_W)
    write("medtab_tabs_pad", tabs)
    report.append(f"art: {', '.join(n for _s, n in INV_ART.values())} (grid scale {GRID_SCALE}), {SEND_ART}, padstash_* (3), "
                  f"medtab_tabs_pad {PAD_TAB_W} x {tabs[0].height}")


def build(data: Path) -> list[str]:
    import fxpaths
    import ui_layouts
    report: list[str] = []
    base = Path(fxpaths.D2R) / "data" / CONTROLLER
    lay_dir = data / LAYOUTS
    files = {"playerinventoryoriginallayouthd.json": inventory_original(
                 (base / "playerinventoryoriginallayouthd.json").read_text("utf-8-sig")),
             "playerinventoryexpansionlayouthd.json": inventory_expansion(
                 (base / "playerinventoryexpansionlayouthd.json").read_text("utf-8-sig"))}
    ctrl_stash = ui_layouts.stash_hd(ui_layouts.table_rows()["Transmogrify Box Page 1"], "controller/bankexpansionlayouthd.json")
    files["bankexpansionlayouthd.json"] = stash(load(ctrl_stash), load((lay_dir / "bankexpansionlayouthd.json").read_text("utf-8-sig")))
    for name, lay in files.items():
        p = data / CONTROLLER / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(ui_layouts.literalize(json.dumps(lay, indent=1, ensure_ascii=False) + "\n", name), "utf-8", newline="")
        report.append(f"controller/{name}: {p.stat().st_size} bytes")
    art(data, report)
    return report


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["build"]:
        for line in build(Path(argv[1]) if len(argv) > 1 else ROOT / "work" / "mod" / "data"):
            print(line)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
