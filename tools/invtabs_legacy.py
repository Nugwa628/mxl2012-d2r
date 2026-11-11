"""invtabs in legacy graphics (G): the classic layout of a tab's panel, its geometry and the inventory button (lane invtabs-legacy).

D2R picks a panel's layout file by graphics mode: `<name>hd.json` in HD, `<name>.json` in classic (proven in game on 2026-11-11
with CharmInv 1.0.1, whose MPQ has the HD file only: a loose classic `charm-inv/CharmInvPanel.json` in the mod is drawn in
legacy, its grid binds to the plugin's page, the close button and a classic inventory button work; docs/invtabs-legacy.md).
mxl2012-core registers its own panels the same way (stash_pages.cpp / send_stash.cpp: `<id>hd.json` and `<id>.json` through
ResourceService).

One classic panel per tab: D2R's 320 x 432 left panel ($LeftPanelAnchor, the rect of the classic cube / stash layouts), drawn on
the tab's picture `PANEL\\invtabs_<tab>` (tools/invtabs_art.py builds it for the tab's grid size and title), top to bottom:

  header       Median's tradestash header, the title drawn into its lower name box (art)
  summary      a dark box of `summary_lines` (2..8) empty TextBoxWidgets `<prefix>/Summary<i>` (classic 8pt, LINE_H apart); the summary
               lane fills them through D2R's text setter
  tab row      up to MAX_TABS ButtonWidgets `<prefix>/Tab<i>` (TAB_W x TAB_H, art PANEL\\invtabs_tab_<id>, frames 0 normal,
               1 pressed, 2 this tab); only the tabs that exist and have a classic panel are written; a click opens
               that tab's panel
  grid         the tab's InventoryGridWidget, cols x rows cells of CELL px, centred; its last row ends on the stash's bottom line
  bottom band  the stash's, with the close ButtonWidget `<prefix>/Close` (PANEL\\buysellbtn 10 / 11, D2R's classic close)

Sizes: at most MAX_COLS (10) columns (290 px of grid in a 320 px panel) and as many rows as leave MIN_SUMMARY_LINES summary
lines above the tab row (7 rows at the default geometry); anything larger is refused (ClassicSizeError): the tab then has no
classic layout and shows in HD only. Grid sizes are 1..16 (the custom page is 16 x 16).

Targets: `invtabs` (panels `invtabs/<Tab>`, grid `invtabs/Grid`, or with --template the host's `@PANEL@` / `@GRID@` placeholders,
aaa-player-page-host's client-layout convention) and `charminv` (Dimentio's CharmInv as a stand-in: panel
`charm-inv/CharmInvPanel`, grid `charm-inv/InventoryGrid`, 10 x 4) for game checks before the invtabs plugin exists.

  py -3 -I tools/invtabs_legacy.py build --out work/mod/data [--target invtabs|charminv] [--grid 10x6] [--tabs tabs.json]
  py -3 -I tools/invtabs_legacy.py check --out work/mod/data [same options]
  py -3 -I tools/invtabs_legacy.py geometry [--grid 10x6]      (the numbers the core and the summary lane need, as JSON)
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # ui_layouts (run with -I too)

PANEL_W, PANEL_H = 320, 432
PANEL_RECT = (-320, -240, PANEL_W, PANEL_H)
PANEL_ANCHOR = "$LeftPanelAnchor"
CELL = 29                    # classic item cell (Median's tradestash / cube grids, D2R's $ItemCellSize in classic)
MAX_PAGE = 16                # D2RLoader's custom player page is 16 x 16
MAX_COLS = 10                # 10 x 29 = 290: the tradestash grid, x 16..306 inside the panel's frame
INNER_X0, INNER_X1 = 16, 306  # inside the stash frame's vertical lines (x 15 and 306)
BODY_TOP = 83                # first row under the stash frame's top line (80-82)
GRID_BOTTOM = 372            # the stash's line under its last row (370-372); the bottom band starts at 373
LINE = 3                     # a grid line: y0 + 29k - 2 .. y0 + 29k
MAX_TABS = 12
TAB_W, TAB_H = 24, 24
TAB_X0 = INNER_X0 + 1        # 12 tabs x 24 = 288: x 17..305
TAB_GAP = 4                  # between the tab row and the grid's top line
SUMMARY_MARGIN = 4           # the summary box inside the frame / above the tab row
SUMMARY_RIM, SUMMARY_PAD = 2, 3
LINE_H = 12                  # classic 8pt line pitch
SUMMARY_FONT = "8pt"
SUMMARY_CHAR = 6.4           # classic 8pt: mean advance per character (tools/devmenu_layout.SD_CHAR)
MIN_SUMMARY_LINES = 2
MAX_SUMMARY_LINES = 8        # "a short summary": a small grid leaves dark stone under the box instead of more lines
CLOSE_RECT = (275, 383, 32, 32)                 # the stash bottom band's gold-framed close square
CLOSE_FRAMES = {"normal": 10, "pressed": 11}    # PANEL\buysellbtn's close frames (D2R's classic cube close)
TOOLTIP_OFFSET = {"x": 0, "y": -3}              # D2R's classic buttons' (cube / inventory close)
TITLE_BOX = (75, 49, 247, 66)                   # the header's lower name box, inside (tools/invtabs_art.py draws the title)

BUTTON_NAME = "InvTabsButton"                   # the classic inventory's button
BUTTON_ART = "invtabs_button"
BUTTON_RECT = (272, 386, 32, 32)                # the free stone right of the gold box (classic inventory, both layouts)
BUTTON_FRAMES = {"normal": 0, "pressed": 1}
BUTTON_TIP = "Inventory Tabs"
CLASSIC_INVENTORY = ("playerinventoryoriginallayout.json", "playerinventoryexpansionlayout.json")
HD_INVENTORY = ("playerinventoryoriginallayouthd.json", "playerinventoryexpansionlayouthd.json")
AFTER_SEND_STASH = '"name": "MxlSendStash"'
AFTER_CLOSE = '"type": "ButtonWidget", "name": "close"'


class ClassicSizeError(ValueError):
    """A grid the classic 320 x 432 panel cannot show: the tab has no classic layout (HD only)."""


@dataclass(frozen=True)
class Tab:
    id: str                  # [a-z0-9_]+: file names (PANEL\invtabs_<id>, PANEL\invtabs_tab_<id>)
    label: str               # tooltip of its tab button
    title: str               # drawn into the panel's header
    icon: str = "invchm"     # classic inventory picture (global/items/<icon>.dc6) on its tab button
    cols: int = 10
    rows: int = 6
    panel: str = ""          # the panel's name; "" = Target.panel_fmt

    def __post_init__(self):
        if not re.fullmatch(r"[a-z0-9_]+", self.id):
            raise ValueError(f"tab id {self.id!r}: only a-z, 0-9 and _")


@dataclass(frozen=True)
class Target:
    name: str
    prefix: str              # widget name prefix (the panel's plugin id)
    panel_fmt: str           # panel name of a tab, {Tab} = the id with a capital first letter
    grid_name: str
    layout_dir: str          # data/global/ui/layouts/<layout_dir>/<panel's local id>.json
    tabs: tuple = field(default_factory=tuple)


CHARMS = Tab("charms", "Charms", "Charm Inventory", "invchm", 10, 6)
INVTABS = Target("invtabs", "invtabs", "invtabs/{Tab}", "invtabs/Grid", "invtabs", (CHARMS,))
CHARMINV = Target("charminv", "charm-inv", "charm-inv/CharmInvPanel", "charm-inv/InventoryGrid", "charm-inv",
                  (Tab("charms", "Charms", "Charm Inventory", "invchm", 10, 4),))
TARGETS = {t.name: t for t in (INVTABS, CHARMINV)}


# ---------------------------------------------------------------- geometry

def grid_origin(cols: int, rows: int) -> tuple[int, int]:
    """Top-left of cell (0, 0): centred in the frame, the last row ending on the stash's bottom line."""
    return INNER_X0 + (MAX_COLS - cols) * CELL // 2, GRID_BOTTOM - rows * CELL


def tab_row_y(rows: int) -> int:
    return grid_origin(MAX_COLS, rows)[1] - LINE + 1 - TAB_GAP - TAB_H


def summary_box(rows: int) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the summary box (rim included, x1 / y1 exclusive): under the frame's top line, down to the tab
    row, at most MAX_SUMMARY_LINES lines tall."""
    y0 = BODY_TOP + SUMMARY_MARGIN - 1
    y1 = min(tab_row_y(rows) - SUMMARY_MARGIN, y0 + 2 * (SUMMARY_RIM + SUMMARY_PAD) + MAX_SUMMARY_LINES * LINE_H)
    return INNER_X0 + SUMMARY_MARGIN, y0, INNER_X1 - SUMMARY_MARGIN, y1


def summary_lines(rows: int) -> int:
    _x0, y0, _x1, y1 = summary_box(rows)
    return max(0, (y1 - y0 - 2 * (SUMMARY_RIM + SUMMARY_PAD)) // LINE_H)


def max_rows() -> int:
    return max(r for r in range(1, MAX_PAGE + 1) if r == 1 or summary_lines(r) >= MIN_SUMMARY_LINES)


def check_size(cols: int, rows: int) -> None:
    """Raises ClassicSizeError (with the reason the player / the core logs) for a grid the classic panel cannot show."""
    if not (1 <= cols <= MAX_PAGE and 1 <= rows <= MAX_PAGE):
        raise ClassicSizeError(f"grid {cols} x {rows}: each side must be 1 to {MAX_PAGE} (the custom page is {MAX_PAGE} x {MAX_PAGE})")
    if cols > MAX_COLS:
        raise ClassicSizeError(f"grid {cols} x {rows}: the classic panel ({PANEL_W} x {PANEL_H}, {CELL}-pixel cells) fits at most "
                               f"{MAX_COLS} columns; this tab has no classic layout and shows in HD graphics only")
    if rows > max_rows():
        raise ClassicSizeError(f"grid {cols} x {rows}: the classic panel ({PANEL_W} x {PANEL_H}, {CELL}-pixel cells) fits at most "
                               f"{max_rows()} rows under the title, {MIN_SUMMARY_LINES} summary lines and the tab row; this tab has "
                               f"no classic layout and shows in HD graphics only")


def fits(tab: "Tab") -> bool:
    try:
        check_size(tab.cols, tab.rows)
        return True
    except ClassicSizeError:
        return False


def classic_tabs(tabs) -> tuple:
    """The tabs that have a classic panel: the only ones on a classic tab row (a click on another would open a panel D2R has
    no classic layout for)."""
    return tuple(t for t in tabs if fits(t))


def tab_rect(i: int, rows: int) -> tuple[int, int, int, int]:
    if not 0 <= i < MAX_TABS:
        raise ValueError(f"tab {i}: at most {MAX_TABS} tabs")
    return TAB_X0 + i * TAB_W, tab_row_y(rows), TAB_W, TAB_H


def geometry(cols: int, rows: int) -> dict:
    """The numbers the core lane (grid origin for the host's @GRID@) and the summary lane (lines, characters) need."""
    check_size(cols, rows)
    x0, y0, x1, y1 = summary_box(rows)
    gx, gy = grid_origin(cols, rows)
    n = summary_lines(rows)
    return {"panel": {"rect": list(PANEL_RECT), "anchor": PANEL_ANCHOR}, "grid": {"x": gx, "y": gy, "cols": cols, "rows": rows,
            "cell": CELL}, "summary": {"box": [x0, y0, x1, y1], "lines": n, "line_h": LINE_H, "font": SUMMARY_FONT,
            "chars": int((x1 - x0 - 2 * (SUMMARY_RIM + SUMMARY_PAD)) / SUMMARY_CHAR)},
            "tabs": {"max": MAX_TABS, "rects": [list(tab_rect(i, rows)) for i in range(MAX_TABS)]},
            "close": list(CLOSE_RECT), "title_box": list(TITLE_BOX)}


# ---------------------------------------------------------------- layout

def _rect(x: int, y: int, w: int | None = None, h: int | None = None) -> dict:
    r = {"x": x, "y": y}
    if w is not None:
        r.update(width=w, height=h)
    return r


def panel_name(target: Target, tab: Tab) -> str:
    return tab.panel or target.panel_fmt.format(Tab=tab.id[:1].upper() + tab.id[1:], tab=tab.id)


def art_name(tab: Tab) -> str:
    return f"invtabs_{tab.id}"


def tab_art_name(tab: Tab) -> str:
    return f"invtabs_tab_{tab.id}"


GRID_PLACEHOLDER = "@GRID@"
PANEL_PLACEHOLDER = "@PANEL@"


def panel_layout(target: Target, tab: Tab, tabs: tuple | None = None, template: bool = False) -> dict:
    """The classic panel of `tab` (draw order: click catcher, picture, summary lines, tabs, grid, close). `template`: the
    root name is @PANEL@ and the grid a "@GRID@" string the host replaces with its grid widget (layout_text unquotes it)."""
    tabs = classic_tabs(tabs if tabs is not None else target.tabs)
    if len(tabs) > MAX_TABS:
        raise ValueError(f"{len(tabs)} tabs: at most {MAX_TABS}")
    check_size(tab.cols, tab.rows)
    name = PANEL_PLACEHOLDER if template else panel_name(target, tab)
    p = target.prefix
    kids = [{"type": "ClickCatcherWidget", "name": f"{p}/PanelClickCatcher", "fields": {"rect": _rect(0, 0, PANEL_W, PANEL_H)}},
            {"type": "GridImageWidget", "name": f"{p}/Background",
             "fields": {"rect": _rect(0, 0, PANEL_W, PANEL_H), "filename": f"PANEL\\{art_name(tab)}", "frames": 4, "rows": 2}}]
    x0, y0, x1, _y1 = summary_box(tab.rows)
    inset = SUMMARY_RIM + SUMMARY_PAD
    for i in range(summary_lines(tab.rows)):
        kids.append({"type": "TextBoxWidget", "name": f"{p}/Summary{i}",
                     "fields": {"rect": _rect(x0 + inset, y0 + inset + i * LINE_H, x1 - x0 - 2 * inset, LINE_H), "text": "",
                                "style": {"fontColor": {"r": 255, "g": 255, "b": 255, "a": 255}, "alignment": {"v": "center"}},
                                "fontType": SUMMARY_FONT}})
    for i, t in enumerate(tabs):
        mine = t.id == tab.id
        other = panel_name(target, t) if not template or not mine else PANEL_PLACEHOLDER
        kids.append({"type": "ButtonWidget", "name": f"{p}/Tab{i}",
                     "fields": {"rect": _rect(*tab_rect(i, tab.rows)), "filename": f"PANEL\\{tab_art_name(t)}",
                                "normalFrame": 2 if mine else 0, "pressedFrame": 2 if mine else 1, "tooltipString": t.label,
                                "tooltipOffset": dict(TOOLTIP_OFFSET), "onClickMessage": f"PanelManager:OpenPanel:{other}"}})
    gx, gy = grid_origin(tab.cols, tab.rows)
    if template:
        kids.append(GRID_PLACEHOLDER)
    else:
        kids.append({"type": "InventoryGridWidget", "name": target.grid_name,
                     "fields": {"rect": _rect(gx, gy), "cellCount": {"x": tab.cols, "y": tab.rows}, "cellSize": "$ItemCellSize",
                                "gemSocketFilename": "PANEL\\gemsocket"}})
    kids.append({"type": "ButtonWidget", "name": f"{p}/Close",
                 "fields": {"rect": _rect(*CLOSE_RECT), "filename": "PANEL\\buysellbtn", "normalFrame": CLOSE_FRAMES["normal"],
                            "pressedFrame": CLOSE_FRAMES["pressed"], "tooltipString": "Close", "tooltipOffset": dict(TOOLTIP_OFFSET),
                            "onClickMessage": f"PanelManager:ClosePanel:{name}"}})
    return {"type": "Panel", "name": name, "fields": {"priority": 10, "rect": _rect(*PANEL_RECT), "anchor": PANEL_ANCHOR},
            "children": kids}


def layout_text(layout: dict) -> str:
    text = json.dumps(layout, indent=1) + "\n"
    return text.replace(json.dumps(GRID_PLACEHOLDER), GRID_PLACEHOLDER)  # the host splices its grid widget object in


def layout_rel(target: Target, tab: Tab) -> Path:
    """Where the classic layout goes in the mod's data folder: <panel name>.json (D2R's HD file is <panel name>hd.json)."""
    return Path("global/ui/layouts") / f"{panel_name(target, tab)}.json"


# ---------------------------------------------------------------- the classic inventory's button

def button_widget(target: Target, tab: Tab | None = None) -> dict:
    """The classic inventory's button: toggles the first tab's panel (no hoveredFrame: classic buttons have none)."""
    tab = tab or target.tabs[0]
    return {"type": "ButtonWidget", "name": BUTTON_NAME,
            "fields": {"rect": _rect(*BUTTON_RECT), "filename": f"PANEL\\{BUTTON_ART}", "normalFrame": BUTTON_FRAMES["normal"],
                       "pressedFrame": BUTTON_FRAMES["pressed"], "tooltipString": BUTTON_TIP, "tooltipOffset": dict(TOOLTIP_OFFSET),
                       "onClickMessage": f"PanelManager:TogglePanel:{panel_name(target, tab)}"}}


def add_button_to_layout(text: str, target: Target = INVTABS) -> str:
    """A classic inventory layout's text with the button after MxlSendStash (else after `close`). Idempotent. The build's
    `button` step (tools/build.py, only for the charm inventory invtabs) runs it on the two finished classic layouts; with
    CharmInv the layouts stay without it, because CharmInv has no classic panel for it to open."""
    import ui_layouts  # lazily: ui_layouts imports this module to add the button
    if f'"name": "{BUTTON_NAME}"' in text:
        return text
    marker = AFTER_SEND_STASH if AFTER_SEND_STASH in text else AFTER_CLOSE
    s, e = ui_layouts.block_span(text, marker)
    line_start = text.rindex("\n", 0, s) + 1
    indent = text[line_start:s]
    if text[e - 1] != ",":
        text, e = text[:e] + "," + text[e:], e + 1
    return text[:e] + f"\n{indent}{json.dumps(button_widget(target))}," + text[e:]


# ---------------------------------------------------------------- build / check

def load_tabs(path: Path | None, target: Target, grid: tuple[int, int] | None) -> tuple:
    """The target's tabs, or a JSON list of {id, label, title, icon, cols, rows}; `grid` overrides the first tab's size."""
    tabs = list(target.tabs)
    if path:
        tabs = [Tab(**t) for t in json.loads(Path(path).read_text("utf-8"))]
    if grid:
        t = tabs[0]
        tabs[0] = Tab(t.id, t.label, t.title, t.icon, grid[0], grid[1], t.panel)
    return tuple(tabs)


def build(out_data: Path, target: Target, tabs: tuple, template: bool = False) -> list[str]:
    """Write each tab's classic layout (a tab too large for classic is skipped with its reason). Lines for the log."""
    done = []
    for tab in tabs:
        try:
            text = layout_text(panel_layout(target, tab, tabs, template))
        except ClassicSizeError as e:
            done.append(f"{tab.id}: no classic layout: {e}")
            continue
        rel = layout_rel(target, tab) if not template else Path("global/ui/layouts") / target.layout_dir / f"{tab.id}.template.json"
        p = Path(out_data) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, "utf-8", newline="")
        done.append(f"{rel.as_posix()}: {tab.cols} x {tab.rows}, {summary_lines(tab.rows)} summary lines, {len(text)} bytes")
    return done


def _walk(node):
    if isinstance(node, dict):
        yield node
        for c in node.get("children", []):
            yield from _walk(c)


def check_layout(root: dict, target: Target, tab: Tab, tabs: tuple) -> list[str]:
    """Problems of one classic panel layout (parsed)."""
    problems = []
    name = panel_name(target, tab)
    if root.get("type") != "Panel" or root.get("name") != name:
        problems.append(f"root is {root.get('type')} {root.get('name')!r}, not Panel {name!r}")
    f = root.get("fields", {})
    if f.get("rect") != _rect(*PANEL_RECT) or f.get("anchor") != PANEL_ANCHOR:
        problems.append(f"root rect / anchor {f.get('rect')} {f.get('anchor')} are not {PANEL_RECT} {PANEL_ANCHOR}")
    w = {c.get("name"): c for c in _walk(root)}
    grid = w.get(target.grid_name)
    if not grid or grid.get("type") != "InventoryGridWidget":
        problems.append(f"no InventoryGridWidget {target.grid_name!r}")
    else:
        g = grid["fields"]
        if (g.get("cellCount", {}).get("x"), g.get("cellCount", {}).get("y")) != (tab.cols, tab.rows):
            problems.append(f"grid cellCount {g.get('cellCount')} is not {tab.cols} x {tab.rows}")
        gx, gy = g.get("rect", {}).get("x"), g.get("rect", {}).get("y")
        if (gx, gy) != grid_origin(tab.cols, tab.rows):
            problems.append(f"grid at {gx},{gy}, not {grid_origin(tab.cols, tab.rows)}")
    boxes = []
    for c in _walk(root):
        r = c.get("fields", {}).get("rect", {})
        if c is root or "width" not in r:
            continue
        x, y, cw, ch = r["x"], r["y"], r["width"], r["height"]
        if x < 0 or y < 0 or x + cw > PANEL_W or y + ch > PANEL_H:
            problems.append(f"{c.get('name')}: {x},{y} {cw} x {ch} leaves the {PANEL_W} x {PANEL_H} panel")
        if c.get("type") in ("ButtonWidget", "TextBoxWidget"):
            boxes.append((c.get("name"), x, y, x + cw, y + ch))
    gx, gy = grid_origin(tab.cols, tab.rows)
    boxes.append(("grid", gx, gy, gx + tab.cols * CELL, gy + tab.rows * CELL))
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]:
                problems.append(f"{a[0]} and {b[0]} overlap")
    close = w.get(f"{target.prefix}/Close")
    if not close or close["fields"].get("onClickMessage") != f"PanelManager:ClosePanel:{name}":
        problems.append(f"close button missing or it does not close {name!r}")
    tabs = classic_tabs(tabs)
    want_tabs = [f"PanelManager:OpenPanel:{panel_name(target, t)}" for t in tabs]
    got_tabs = [w[f"{target.prefix}/Tab{i}"]["fields"].get("onClickMessage") if f"{target.prefix}/Tab{i}" in w else None
                for i in range(len(tabs))]
    if got_tabs != want_tabs or f"{target.prefix}/Tab{len(tabs)}" in w:
        problems.append(f"tab buttons {got_tabs}, expected {want_tabs}")
    lines = [n for n in w if n and n.startswith(f"{target.prefix}/Summary")]
    if len(lines) != summary_lines(tab.rows) or len(lines) < MIN_SUMMARY_LINES:
        problems.append(f"{len(lines)} summary lines, expected {summary_lines(tab.rows)} (at least {MIN_SUMMARY_LINES})")
    return problems


def check(out_data: Path, target: Target, tabs: tuple, inventory: bool = True) -> list[str]:
    """Every tab that fits classic has a strict-JSON layout without '@' keys and with the panel's widgets; the classic
    inventory layouts have the button once, the HD ones never (`inventory`)."""
    out_data = Path(out_data)
    problems = []
    for tab in tabs:
        try:
            check_size(tab.cols, tab.rows)
        except ClassicSizeError:
            continue
        rel = layout_rel(target, tab)
        p = out_data / rel
        if not p.exists():
            problems.append(f"{rel.as_posix()} missing")
            continue
        text = p.read_text("utf-8")
        try:
            root = json.loads(text)
        except ValueError as e:
            problems.append(f"{rel.as_posix()}: not strict JSON ({e})")
            continue
        if "@" in text:
            problems.append(f"{rel.as_posix()}: has an '@' (a @key draws \"Missing string\"; a template is not for the mod)")
        problems += [f"{rel.as_posix()}: {m}" for m in check_layout(root, target, tab, tabs)]
    if inventory:
        problems += check_buttons(out_data)
    return problems


def check_buttons(out_data: Path) -> list[str]:
    """The classic inventory layouts have the button once, the HD ones never (the plugin adds its own HD button)."""
    problems = []
    layouts = Path(out_data) / "global" / "ui" / "layouts"
    marker = re.compile(rf'"name":\s*"{BUTTON_NAME}"')
    for name in CLASSIC_INVENTORY:
        lp = layouts / name
        n = len(marker.findall(lp.read_text("utf-8-sig"))) if lp.exists() else None
        if n != 1:
            problems.append(f"{name}: {'missing' if n is None else f'{n} x {BUTTON_NAME}'}, expected the button once")
    for name in HD_INVENTORY:
        lp = layouts / name
        if lp.exists() and marker.search(lp.read_text("utf-8-sig")):
            problems.append(f"{name}: has {BUTTON_NAME} (HD has its own button)")
    return problems


def parse_grid(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)\s*[xX*]\s*(\d+)", s.strip())
    if not m:
        raise argparse.ArgumentTypeError(f"grid {s!r}: COLSxROWS, e.g. 10x6")
    return int(m.group(1)), int(m.group(2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("cmd", choices=("build", "check", "geometry", "button"))
    ap.add_argument("--out", type=Path, help="the mod's data folder (work/mod/data)")
    ap.add_argument("--target", choices=sorted(TARGETS), default="invtabs")
    ap.add_argument("--grid", type=parse_grid, help="the first tab's grid, COLSxROWS (default: the target's)")
    ap.add_argument("--tabs", type=Path, help="JSON list of tabs {id, label, title, icon, cols, rows}")
    ap.add_argument("--template", action="store_true", help="build: @PANEL@ / @GRID@ templates for the host instead")
    ap.add_argument("--no-inventory", action="store_true", help="check: skip the inventory button check")
    a = ap.parse_args(argv)
    target = TARGETS[a.target]
    tabs = load_tabs(a.tabs, target, a.grid)
    if a.cmd == "geometry":
        try:
            print(json.dumps(geometry(tabs[0].cols, tabs[0].rows)))
        except ClassicSizeError as e:
            print(f"REFUSED: {e}")
            return 1
        return 0
    if not a.out:
        ap.error("--out is required")
    if a.cmd == "button":  # the button into the finished classic inventory layouts (tools/build.py, charm inventory invtabs)
        for name in CLASSIC_INVENTORY:
            p = a.out / "global" / "ui" / "layouts" / name
            if not p.is_file():
                print(f"PROBLEM: {name} is missing (hd_ui.py build writes it)")
                return 1
            p.write_text(add_button_to_layout(p.read_text("utf-8-sig"), target), "utf-8", newline="")
            print(f"{name}: {BUTTON_NAME}")
        problems = check_buttons(a.out)
        for line in problems:
            print(f"PROBLEM: {line}")
        return 1 if problems else 0
    if a.cmd == "build":
        print("\n".join(build(a.out, target, tabs, a.template)))
        if a.template:
            return 0
    problems = check(a.out, target, tabs, inventory=not a.no_inventory)
    for p in problems:
        print(f"PROBLEM: {p}")
    print(f"invtabs_legacy {a.cmd}: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
