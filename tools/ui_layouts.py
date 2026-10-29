"""UI layout overrides (data/global/ui/layouts/*.json) for the mod's inventory and cube (adapted from another port's ui_layouts.py).

D2R reads the grid SIZES from inventory.txt but draws grids, slots and buttons where its layout JSON puts them, so the
layouts are D2R's own files (the copy in work/d2r-baseline/ui/layouts) with text edits:

HD (`...hd.json`; art = tools/ui_panels.py, the classic 320 x 432 picture scaled x 3.631 across, x 3.488 down)
  playerinventoryoriginallayouthd / playerinventoryexpansionlayouthd: background PANEL\\mxl\\inventory, the grid 10 x 6 at the
      table's place, the ten equipment slots at the table's boxes (D2R's widget size scaled to fit the box), the weapon swap
      tabs on the picture's I / II boxes, the gold button and amount on the picture's coin and bar.
  horadriccubelayouthd: background PANEL\\mxl\\cube, the grid 10 x 8, the transmute button on the picture's square.
  Items draw at D2R's HD size (98 pixels per cell) whatever cellSize says, so a grid keeps cellSize 98 x 94 and the widget
  gets `scale` 1.0745 (cell 105.3 across, 101.2 down = 29 classic pixels scaled; a first test showed that a bare
  smaller cellSize leaves items overlapping).
Classic (G key, `....json`, no scaling): the mod's own invchar6.dc6 / supertransmogrifier.dc6 are what the layouts name, only
  the grid, slot and tab positions change to the table's (classic pixels of the 320 x 432 panel).
The HD panels' title text is written out as a literal (docs/bugs.md #30): `"text": "@strpanel4"` / `"@box"` draw "Missing string"
  in the mod's HD inventory and cube layouts (checked in game, with another key too), a literal text draws. The inventory has
  none (the head slot of the mod's picture sits where the title would be), the cube reads "Horadric Cube".
The stash (10 x 10), trade, vendor and hireling layouts and every other panel stay D2R's. The HD skill tree layout stays D2R's too
(3 tabs; the tab titles come from strings, tools/skill_tree_art.py). The classic one (`skillstreepanel.json`) draws no tab title
for the seven classic classes (docs/bugs.md #33, coordinator decision): the mod's skltree_*_back.dc6 art has its own labels on the
tabs and D2R's text sat on top of them; its `textTab0-2` entries of those classes are empty literals, Warlock's keys stay. As for
the HD titles (#30), a `@key` in a widget's `text` / `tooltipString` of a layout the mod serves draws "Missing string" (the
"Skill Choices Remaining" box, seen in game), so those are written out as D2R's English text; the same for the close / drop gold /
transmute tooltips of the inventory and cube and the Warlock tab titles (`LITERALS`, `literalize` runs over every file written).

Slot/grid positions are the Amazon row of inventory.txt (the seven classic classes share every number) minus invLeft; the
cube's the "Transmogrify Box Page 1" row; the picture items (tabs, gold, transmute square) were measured on the DC6.

  py -3 -I tools/ui_layouts.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from icon_paths import EXCEL, read_tsv  # noqa: E402
from ui_paths import BASE_UI, LAYOUT_OUT  # noqa: E402

SX, SY = 1162 / 320, 1507 / 432
ITEM_CELL = 98                      # D2R's HD item sprite size per cell
GRID_SCALE = 29 * SX / ITEM_CELL    # 1.0745: a 29-pixel classic cell across
CELL = f'{{ "x": {ITEM_CELL}, "y": {round(29 * SY / GRID_SCALE)} }}'
RECT = re.compile(r'"rect":\s*\{[^}]*\}')

# widget -> table prefix
SLOTS = {"slot_right_arm": "rArm", "slot_torso": "torso", "slot_left_arm": "lArm", "slot_head": "head", "slot_neck": "neck",
         "slot_right_hand": "rHand", "slot_left_hand": "lHand", "slot_belt": "belt", "slot_feet": "feet",
         "slot_gloves": "gloves"}
# measured on invchar6.dc6 set 1 (classic pixels of the panel): weapon swap tab boxes I / II of the right arm, then the left
TAB_BOXES = {"right": ((17, 5, 47, 24), (51, 5, 82, 24)), "left": ((239, 5, 269, 24), (273, 5, 304, 24))}
TAB_W, TAB_H = 107, 60              # D2R's tab sprite
GOLD_COIN = (82, 391, 104, 411)     # coin recess, then the amount bar (classic pixels)
GOLD_BAR = (105, 391, 198, 411)
GOLD_BUTTON_SIZE = 48               # D2R goldbutton.sprite frame
CUBE_BUTTON = (144, 259, 178, 293)  # the picture's transmute square (D2R's classic convert button sits at 144, 260)
CUBE_BUTTON_SIZE = 117              # D2R transmutebutton.sprite frame
# The cube title: D2R's $InGamePanelTitleRect (x 91, y 64, 972 x 71) lands on the first grid row of the mod's picture, which has no
# title band (its grid starts under the 45-px top border); the title sits above the panel frame instead (player report 2026-10-29).
CUBE_TITLE = (91, -80, 972, 71)


def baseline(name: str) -> str:
    p = BASE_UI / "layouts" / name
    if not p.exists():
        sys.exit(f"{p} missing: run `py -3 tools/hd_ui.py baseline <a D2R 93847 extraction>`")
    return p.read_text("utf-8-sig")


def block_span(text: str, marker: str) -> tuple[int, int]:
    """Start/end of the {...} object containing marker (brace matching; the files have no braces in strings)."""
    i = text.index(marker)
    start = text.rindex("{", 0, i)
    depth, j = 0, start
    while True:
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                if text[end:end + 1] == ",":
                    end += 1
                return start, end
        j += 1


def set_title(text: str, title: str) -> str:
    """The `text` field of the "title" widget (D2R: "@strpanel4", "@box") replaced by the literal `title` (may be empty)."""
    s, e = block_span(text, '"name": "title"')
    block, n = re.subn(r'"text":\s*"[^"]*"', '"text": "%s"' % title, text[s:e], count=1)
    if n != 1:
        raise ValueError("no text field in the title widget")
    return text[:s] + block + text[e:]


def rect(x: float, y: float, w: float | None = None, h: float | None = None, scale: float | None = None) -> str:
    out = f'{{ "x": {round(x)}, "y": {round(y)}'
    if w is not None:
        out += f', "width": {round(w)}, "height": {round(h)}'
    if scale is not None:
        out += f', "scale": {round(scale, 4)}'
    return out + " }"


def set_title_rect(text: str, value: str) -> str:
    """The "title" widget's rect (D2R names the profile's $InGamePanelTitleRect) replaced by `value`."""
    s, e = block_span(text, '"name": "title"')
    block, n = re.subn(r'"rect":\s*(?:"[^"]*"|\{[^}]*\})', lambda _m: f'"rect": {value}', text[s:e], count=1)
    if n != 1:
        raise ValueError("no rect field in the title widget")
    return text[:s] + block + text[e:]


def set_rect(text: str, name: str, value: str) -> str:
    s, e = block_span(text, f'"name": "{name}"')
    return text[:s] + RECT.sub(lambda _m: f'"rect": {value}', text[s:e], count=1) + text[e:]


def set_grid(text: str, x: float, y: float, cols: int, rows: int, scale: float | None) -> str:
    """The grid widget of D2R's layouts: rect, cellCount and (HD) cellSize + scale."""
    s, e = block_span(text, '"name": "grid"')
    b = text[s:e]
    value = rect(x, y, scale=scale)
    b = RECT.sub(lambda _m: f'"rect": {value}', b, count=1)
    b = re.sub(r'"cellCount":\s*\{[^}]*\}', f'"cellCount": {{ "x": {cols}, "y": {rows} }}', b, count=1)
    if scale:
        b = re.sub(r'"cellSize":\s*"[^"]*"', f'"cellSize": {CELL}', b, count=1)
    return text[:s] + b + text[e:]


def widget_size(text: str, name: str) -> tuple[int, int]:
    s, e = block_span(text, f'"name": "{name}"')
    m = re.search(r'"width":\s*(\d+),\s*"height":\s*(\d+)', text[s:e])
    return int(m.group(1)), int(m.group(2))


# ---- table ---------------------------------------------------------------------------------------------------------
def table_rows(path: Path = EXCEL / "inventory.txt") -> dict[str, dict[str, int]]:
    head, rows = read_tsv(path)
    out = {}
    for r in rows:
        out[r[0]] = {h: int(v) for h, v in zip(head[1:], r[1:]) if h and re.fullmatch(r"-?\d+", v)}
    return out


def slot_boxes(row: dict[str, int]) -> dict[str, tuple[int, int, int, int]]:
    """widget -> (left, top, right, bottom) in classic panel pixels."""
    inv = row["invLeft"]
    return {w: (row[f"{p}Left"] - inv, row[f"{p}Top"], row[f"{p}Right"] - inv, row[f"{p}Bottom"]) for w, p in SLOTS.items()}


def box_hd(box: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    return box[0] * SX, box[1] * SY, box[2] * SX, box[3] * SY


# ---- HD ------------------------------------------------------------------------------------------------------------
def inventory_original_hd(row: dict[str, int]) -> str:
    t = baseline("playerinventoryoriginallayouthd.json")
    t = t.replace('"PANEL\\\\Inventory\\\\Classic_Background"', '"PANEL\\\\mxl\\\\inventory"')
    t = set_title(t, "")
    t = set_grid(t, (row["gridLeft"] - row["invLeft"]) * SX, row["gridTop"] * SY, row["gridX"], row["gridY"], GRID_SCALE)
    for widget, box in slot_boxes(row).items():
        l, top, r, b = box_hd(box)
        w, h = widget_size(t, widget)
        s = min((r - l) / w, (b - top) / h)
        t = set_rect(t, widget, rect(l + (r - l - w * s) / 2, top + (b - top - h * s) / 2, w, h, s))
    cx0, cy0, cx1, cy1 = box_hd(GOLD_COIN)
    bx0, by0, bx1, by1 = box_hd(GOLD_BAR)
    bx = cx0 + (cx1 - cx0 - GOLD_BUTTON_SIZE) / 2
    by = cy0 + (cy1 - cy0 - GOLD_BUTTON_SIZE) / 2
    t = set_rect(t, "gold_button", rect(bx, by))
    t = set_rect(t, "gold_amount_tooltip", rect(bx, by))
    t = set_rect(t, "gold_amount", rect(bx0 + 14, by0 + (by1 - by0 - 48) / 2, bx1 - bx0 - 28, 48))
    return t


def inventory_expansion_hd() -> str:
    t = baseline("playerinventoryexpansionlayouthd.json")
    t = t.replace('"PANEL\\\\Inventory\\\\Background"', '"PANEL\\\\mxl\\\\inventory"')
    # D2R's pairs: right arm I at x 99, II at 205; left arm I at 850, II at 956 (y 179 for the sprites, 180 for the text)
    new = {}
    for side, (old_i, old_ii) in (("right", ("99", "205")), ("left", ("850", "956"))):
        (i0, _t0, _i1, _b0), (ii0, _t1, _ii1, _b1) = TAB_BOXES[side]
        new[old_i] = round(i0 * SX)
        new[old_ii] = round(ii0 * SX)
    y = round((TAB_BOXES["right"][0][1] + TAB_BOXES["right"][0][3]) / 2 * SY - TAB_H / 2)
    for name in ("background_right_arm_selected", "background_left_arm_selected", "background_right_arm",
                 "background_left_arm", "text_i_left", "text_ii_left", "text_i_right", "text_ii_right",
                 "weaponswap_right_arm", "weaponswap_left_arm"):
        if f'"name": "{name}"' not in t:
            continue
        s, e = block_span(t, f'"name": "{name}"')
        block = re.sub(r'"x":\s*(\d+)', lambda m: f'"x": {new.get(m.group(1), m.group(1))}', t[s:e], count=1)
        block = re.sub(r'"y":\s*(\d+)', lambda m: f'"y": {y + int(m.group(1)) - 179}', block, count=1)
        t = t[:s] + block + t[e:]
    return t


def cube_hd(row: dict[str, int]) -> str:
    t = baseline("horadriccubelayouthd.json")
    t = t.replace('"PANEL\\\\Horadric_Cube\\\\HoradricCube_BG"', '"PANEL\\\\mxl\\\\cube"')
    t = set_title(t, "Horadric Cube")
    t = set_title_rect(t, rect(*CUBE_TITLE))
    t = set_grid(t, (row["gridLeft"] - row["invLeft"]) * SX, row["gridTop"] * SY, row["gridX"], row["gridY"], GRID_SCALE)
    x0, y0, x1, y1 = box_hd(CUBE_BUTTON)
    t = set_rect(t, "convert", rect((x0 + x1) / 2 - CUBE_BUTTON_SIZE / 2, (y0 + y1) / 2 - CUBE_BUTTON_SIZE / 2))
    return t


# ---- classic -------------------------------------------------------------------------------------------------------
def inventory_original(row: dict[str, int]) -> str:
    t = baseline("playerinventoryoriginallayout.json")
    t = t.replace('"PANEL\\\\invchar"', '"PANEL\\\\invchar6"')
    t = set_grid(t, row["gridLeft"] - row["invLeft"], row["gridTop"], row["gridX"], row["gridY"], None)
    for widget, (l, top, r, b) in slot_boxes(row).items():
        t = set_rect(t, widget, rect(l, top, r - l, b - top))
    return t


def inventory_expansion() -> str:
    """The expansion layout's weapon swap tabs sit 22 above the arm slots in D2R's art (y 22 for arms at 47); the mod's
    art has the arms at 31, so they move up by the same 16."""
    t = baseline("playerinventoryexpansionlayout.json")
    for name in ("background_right_arm", "background_left_arm", "weaponswap_right_arm", "weaponswap_left_arm"):
        s, e = block_span(t, f'"name": "{name}"')
        block = re.sub(r'"y":\s*(\d+)', lambda m: f'"y": {int(m.group(1)) - 16}', t[s:e], count=1)
        t = t[:s] + block + t[e:]
    return t


def cube(row: dict[str, int]) -> str:
    t = baseline("horadriccubelayout.json")
    return set_grid(t, row["gridLeft"] - row["invLeft"], row["gridTop"], row["gridX"], row["gridY"], None)


CLASSIC_TAB_KEY = re.compile(r'"@SkillCategory(?:Am|So|Ne|Pa|Ba|Dr|As)[123]"')


# D2R's English (ui.json / skills.json, the same in the mod's overrides.json) for every `@key` the served layouts name: a `@key`
# in a layout the mod serves draws "Missing string" (bugs #30, #33), so each is written out. tools/text_audit.py fails the build on
# any `@key` left in a layout file.
LITERALS = {"@StrSklTree1 @StrSklTree2 @StrSklTree3": "Skill Choices Remaining", "@StrSklTreea": "Skill Tab 1",
            "@StrSklTreeb": "Skill Tab 2", "@StrSklTreec": "Skill Tab 3", "@strClose": "Close", "@strGoldDrop": "Drop Gold",
            "@strUiMenu2": "Transmute", "@SkillCategoryWa1": "Demon", "@SkillCategoryWa2": "Eldritch", "@SkillCategoryWa3": "Chaos"}
AT_KEY = re.compile(r'"(@[^"\n]*)"')


def literalize(text: str, name: str) -> str:
    """Every `"@key"` value of a layout replaced by D2R's English text (LITERALS); a key without a literal is an error."""
    out = text
    for key, literal in LITERALS.items():
        out = out.replace(f'"{key}"', f'"{literal}"')
    left = AT_KEY.findall(out)
    if left:
        raise ValueError(f"{name}: widget text keys without a literal: {sorted(set(left))}")
    return out


CANCEL_CODE = re.compile(r'("cancelPositionCode"\s*:\s*\[)([^\]]*)(\])')
WARLOCK_CANCEL_FROM = 2  # the Necromancer's entry: D2R's skltree_w_back.dc6 is a byte copy of its skltree_n_back.dc6


def warlock_cancel_position(text: str) -> str:
    """D2R's classic `cancelPositionCode` (where the close button sits per class and tab) has 7 entries, the field is an
    int[8] (descriptor at exe 0x29ea8d0: element 4 bytes, count 8, panel +0x86c), so the Warlock's slot keeps its default;
    the 8th entry is the Necromancer's, whose tree art the Warlock's is (bugs.md #498)."""
    m = CANCEL_CODE.search(text)
    if not m:
        raise ValueError("skillstreepanel.json: no cancelPositionCode")
    vals = [v.strip() for v in m.group(2).split(",") if v.strip()]
    if len(vals) >= 8:
        return text
    if len(vals) != 7:
        raise ValueError(f"skillstreepanel.json: cancelPositionCode has {len(vals)} entries, 7 or 8 expected")
    vals.append(vals[WARLOCK_CANCEL_FROM])
    return text[:m.start(2)] + " " + ", ".join(vals) + " " + text[m.end(2):]


def skilltree_classic() -> str:
    """D2R's classic skill tree panel with the tab title strings of the seven classic classes emptied (bug #33), a Warlock
    entry in `cancelPositionCode` (bug #498) and its widget texts / tooltips written as literals."""
    t = baseline("skillstreepanel.json")
    out, n = CLASSIC_TAB_KEY.subn('""', t)
    if n != 21:
        raise ValueError(f"skillstreepanel.json: {n} classic tab title keys, 21 expected")
    return literalize(warlock_cancel_position(out), "skillstreepanel.json")


def build(out: Path = LAYOUT_OUT, table: Path = EXCEL / "inventory.txt") -> list[str]:
    rows = table_rows(table)
    player, box = rows["Amazon"], rows["Transmogrify Box Page 1"]
    files = {"playerinventoryoriginallayouthd.json": inventory_original_hd(player),
             "playerinventoryexpansionlayouthd.json": inventory_expansion_hd(),
             "horadriccubelayouthd.json": cube_hd(box),
             "playerinventoryoriginallayout.json": inventory_original(player),
             "playerinventoryexpansionlayout.json": inventory_expansion(),
             "horadriccubelayout.json": cube(box),
             "skillstreepanel.json": skilltree_classic()}
    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out / name).write_text(literalize(text, name), "utf-8", newline="")
    return [f"{name}: {len(text)} bytes" for name, text in files.items()]


def main(argv: list[str] | None = None) -> int:
    print("\n".join(build()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
