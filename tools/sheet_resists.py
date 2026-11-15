"""Magic Resistance and Physical Resistance on D2R's character sheet (docs/hd-ui.md "Magic and Physical Resistance on the
character sheet"): the mod's copies of D2R's three sheet layouts with two more resistance rows, and the art they need.

D2R's sheet code fills only the widgets it knows by name (FireText, ColdText, ...); a layout cannot bind a text box to a stat.
So each row here is a literal title and three value boxes at the same place, one per colour (white, gold at the cap, red below
0: a text box has the one colour of its style, colour codes print as text), named as statbook/src/sheet_resist_logic.h expects.
The plugin part sheetres fills the box of the row's colour and empties the other two.

  global/ui/layouts/characterstatspanelhd.json (PC, HD graphics)
      Magic Resistance under Fire, Physical Resistance under Lightning, in a third row of resistance boxes. The background
      (PANEL\\Character_Sheet\\Character_Background, sprite + lowend) gets that row: the separator repeated under the
      Poison row, then the boxes of the Fire / Lightning row (other stone than the Cold / Poison row right above it, so no
      repeated strip shows), and the ledge below cut to LEDGE_H rows (its top and bottom bevels kept at full size, joined by a
      ragged cut with a 4-pixel blend) so the frame keeps its height. The stat points line (CombinedPointsInfo) moves down by the same amount into the rest of its bar.
  global/ui/layouts/characterstatspanel.json (PC, legacy graphics)
      The classic panel ends 8 pixels under the Poison box: no room for rows under it. The two rows sit left of the elemental
      stack instead, beside the Lightning and Poison rows (Magic, Physical), in boxes cut from the Fire box (its title cell
      narrowed) and drawn into the mod's invchar6.dc6 (set 0, the sheet), right of the stat points plate (which ends at y 364)
      and left of the close button. The values go without "%" as the classic elemental ones (marker widget LEGACY_MARKER).
  global/ui/layouts/controller/characterstatspanelhd.json (gamepad UI)
      Two more resistance insets under Poison's, in the free space of D2R's gamepad sheet. It is `basedOn` the PC file above,
      so every new widget is named here too (else it would inherit the PC rect).

Every `@key` of the served layouts is written out as D2R's English text (a `@key` in a layout the mod serves draws "Missing
string", bugs #30, #33). A step of tools/build.py after tools/legacy_art.py (it edits the invchar6.dc6 that step copies).

  py -3 -I tools/sheet_resists.py build [--d2r EXTRACT] [--mod DATA]   (defaults: fxpaths.D2R, work/mod/data)
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

LAYOUTS = Path("global") / "ui" / "layouts"
PC_HD, LEGACY, PAD = "characterstatspanelhd.json", "characterstatspanel.json", "controller/characterstatspanelhd.json"
BACKGROUND = "panel/character_sheet/character_background"   # PANEL\Character_Sheet\Character_Background (D2R hd/global/ui)
INVCHAR = Path("global") / "ui" / "panel" / "invchar6.dc6"

# the two rows: (title, value box base name, tooltip). The value box names are the plugin's (sheet_resist_logic.h Names).
ROWS = (("Magic", "MxlMagicText",
         "Reduces Magic damage received.\nMaximum 75% plus maximum magic resistance, at most 95%."),
        ("Physical", "MxlPhysicalText", "Reduces Physical damage received.\nMaximum 50%."))
COLOURS = (("", "$FontColorWhite"), ("Capped", "$FontColorGold"), ("Negative", "$FontColorRed"))  # box suffix, style colour
LEGACY_MARKER = "MxlSheetLegacy"    # an empty widget of the legacy layout only: the plugin writes its values without "%", as D2R's

# ---- PC HD -------------------------------------------------------------------------------------------------------------
# D2R's art (1162 x 1507): rows of resistance boxes 1186-1247 (Fire / Lightning) and 1258-1314 (Cold / Poison) with an
# 11-pixel separator 1247-1258, then a ledge 1314-1344 and the stat points bar. The frame's knot borders are outside
# INTERIOR and stay as they are.
ROW1 = (1186, 1247)
SEPARATOR = (1247, 1258)
ROW2 = (1258, 1314)
LEDGE = (1314, 1344)
LEDGE_H = 20                        # the ledge after the new row (cut, not scaled): the art keeps its height
LEDGE_TOP = 11                      # ledge rows kept from its top (around the cut), the rest come from its bottom
BLEND = 4                           # rows blended across the ledge cut
INTERIOR = (48, 1114)               # x range rebuilt
NEW_ROW_Y = LEDGE[0] + (SEPARATOR[1] - SEPARATOR[0])                     # 1325: the third row's boxes
SPLICE_END = NEW_ROW_Y + (ROW2[1] - ROW2[0]) + LEDGE_H                  # 1401: original art from here on
HD_ROW = (NEW_ROW_Y + 3, ROW2[1] - ROW2[0] - 3)                          # text rect y / height (D2R: Cold row 1261 / 57)


def new_row(art, x0: int, x1: int):
    """The third row's boxes: the Fire / Lightning row's art (ROW1 from its top, ROW2's height: its last rows are the
    shadow above the separator, which the ledge gives here), so it is not a pixel copy of the Cold / Poison row above."""
    return art.crop((x0, ROW1[0], x1, ROW1[0] + ROW2[1] - ROW2[0]))


def ledge_cuts(width: int) -> list[int]:
    """Per column, the ledge row where its top part ends: LEDGE_TOP give or take 2, wandering by one row per 24-pixel run
    (a ragged seam, not a straight line across the sheet)."""
    import random
    rnd = random.Random(1314)
    cuts, c = [], LEDGE_TOP
    for x in range(width):
        if x % 24 == 0:
            c = max(LEDGE_TOP - 2, min(LEDGE_TOP + 2, c + rnd.choice((-1, 0, 1))))
        cuts.append(c)
    return cuts


def ledge_cut(art, x0: int, x1: int):
    """The ledge cut from LEDGE[1] - LEDGE[0] rows to LEDGE_H without scaling: rows above the cut from its top, the rest
    from its bottom (so both bevels keep their size), BLEND rows blended across the cut."""
    from PIL import Image
    src = art.crop((x0, LEDGE[0], x1, LEDGE[1])).convert("RGBA")
    w, full = src.size
    skip = full - LEDGE_H                       # rows left out of the middle
    sp, out = src.load(), Image.new("RGBA", (w, LEDGE_H))
    op = out.load()
    for x, cut in enumerate(ledge_cuts(w)):
        for y in range(LEDGE_H):
            a = min(1.0, max(0.0, (y - cut + BLEND / 2 + 0.5) / BLEND))     # 0: top part, 1: bottom part
            top, bot = sp[x, y], sp[x, y + skip]
            op[x, y] = tuple(round(t * (1 - a) + b * a) for t, b in zip(top, bot))
    return out.convert(art.mode)


def hd_art(art):
    """D2R's sheet background with a third row of resistance boxes (see the header)."""
    w, h = art.size
    x0, x1 = INTERIOR
    out = art.copy()
    parts = [art.crop((x0, SEPARATOR[0], x1, SEPARATOR[1])), new_row(art, x0, x1), ledge_cut(art, x0, x1)]
    y = LEDGE[0]
    for p in parts:
        out.paste(p, (x0, y))
        y += p.height
    assert y == SPLICE_END and out.size == (w, h)
    return out


def points_rect(rect: dict) -> dict:
    """CombinedPointsInfo (D2R: y 1388, 60 high, text from its top; glyphs centred at about 1408 in a bar 1374-1445): in
    the bar's rest under the new row, SPLICE_END-1445, 42 high."""
    r = dict(rect)
    r["y"], r["height"] = SPLICE_END + 2, 42
    return r


# ---- legacy --------------------------------------------------------------------------------------------------------------
# invchar6.dc6 set 0 (classic pixels of the 320 x 432 panel): the Fire box spans x 172-312, y 329-350 (title cell to the
# separator at 270-271, value cell 272-309); the rows are 24 apart. The new boxes: the Fire box without title-cell columns
# LEGACY_CUT, at x LEGACY_X, on the Lightning (y 377) and Poison (401) rows.
FIRE_BOX = (172, 329, 313, 351)     # x0, y0, x1, y1 (exclusive)
LEGACY_CUT = (210, 232)
LEGACY_X = 4
LEGACY_ROWS = (377, 401)            # box tops: Magic beside Lightning, Physical beside Poison
LEGACY_CLOSE_X = 127                # the close button's box (D2R: rect 128, 388); the boxes end left of it
LEGACY_PLATE_BOTTOM = 341 + 23      # the stat points plate (PANEL\skillpoints 135 x 23 at 3, 341)


def legacy_box_width() -> int:
    return (FIRE_BOX[2] - FIRE_BOX[0]) - (LEGACY_CUT[1] - LEGACY_CUT[0])


def legacy_x(fire_x: int) -> int:
    """A Fire box column right of the cut, in the new box."""
    return fire_x - FIRE_BOX[0] - (LEGACY_CUT[1] - LEGACY_CUT[0]) + LEGACY_X


def legacy_art(idx):
    """Panel indices (320 x 432, set 0) with the two boxes drawn (copies of the Fire box's indices)."""
    import numpy as np
    x0, y0, x1, y1 = FIRE_BOX
    box = np.concatenate([idx[y0:y1, x0:LEGACY_CUT[0]], idx[y0:y1, LEGACY_CUT[1]:x1]], axis=1)
    out = idx.copy()
    for top in LEGACY_ROWS:
        out[top:top + box.shape[0], LEGACY_X:LEGACY_X + box.shape[1]] = box
    return out


def edit_invchar(path: Path, pal) -> str:
    """Draws the boxes into set 0 of the mod's invchar6.dc6 (only its bottom-left tile changes)."""
    import numpy as np
    import dc6
    import rotw_stash_legacy as rsl
    import ui_art
    frames = dc6.read_dc6(path)
    if len(frames) != 8:
        raise ValueError(f"{path}: {len(frames)} frames, 8 (2 sets) expected")
    panel = ui_art.panel_sets(path, pal)[0]
    idx = rsl.quantise(panel, pal, dither=False)
    # the art must round-trip exactly (D2R's palette has no two entries the art uses with the same colour)
    if not (np.asarray(rsl.to_rgba(idx, pal)) == np.asarray(panel)).all():
        raise ValueError(f"{path}: set 0 does not map back to palette indices exactly")
    new = rsl.panel_tiles(legacy_art(idx))
    tile = 2                                                     # ui_art.TILES[2]: 0-256 x 256-432
    tx0, ty0, _tx1, _ty1 = ui_art.TILES[tile]
    for top in LEGACY_ROWS:
        assert ty0 <= top and LEGACY_X + legacy_box_width() <= 256
    fw, fh, ox, oy, _block = frames[tile]
    frames[tile] = (fw, fh, ox, oy, rsl.encode_frame(new[tile]))
    path.write_bytes(dc6.build_dc6(frames))
    return f"{INVCHAR.as_posix()}: set 0 tile {tile} with the Magic / Physical Resistance boxes"


# ---- gamepad -------------------------------------------------------------------------------------------------------------
PAD_INSET = "Controller/Panel/CharacterSheet/V2/CharacterSheet_ResistanceInset"
PAD_ROWS = (823, 932)               # inset tops (D2R's: 385, 497, 606, 714)
PAD_TEXT_DY = 21                    # title / value rect y below the inset (D2R: 714 -> 735)


# ---- layouts -------------------------------------------------------------------------------------------------------------
def strings(d2r: Path) -> dict[str, str]:
    """D2R's English strings by key (every file of data/local/lng/strings)."""
    out: dict[str, str] = {}
    for p in sorted((Path(d2r) / "data" / "local" / "lng" / "strings").glob("*.json")):
        try:
            rows = json.loads(p.read_text("utf-8-sig"))
        except ValueError:
            continue
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and "Key" in r and "enUS" in r:
                out.setdefault(r["Key"], r["enUS"])
    return out


AT_KEY = re.compile(r"@([A-Za-z0-9_]+)")


def literalize(node, table: dict[str, str], used: set[str]):
    """Every string value that starts with `@` with each `@key` replaced by its English text (in place)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and v.startswith("@"):
                def sub(m):
                    if m.group(1) not in table:
                        raise ValueError(f"no English text for @{m.group(1)}")
                    used.add(m.group(1))
                    return table[m.group(1)]
                node[k] = AT_KEY.sub(sub, v)
            else:
                literalize(v, table, used)
    elif isinstance(node, list):
        for v in node:
            literalize(v, table, used)
    return node


def find(node: dict, name: str) -> dict:
    from rotw_stash_legacy import find as _find
    hit = _find(node, name)
    if hit is None:
        raise ValueError(f"no widget {name}")
    return hit


def rect(x: int, y: int, w: int | None = None, h: int | None = None) -> dict:
    r = {"x": x, "y": y}
    if w is not None:
        r.update(width=w, height=h)
    return r


def row_widgets(title_tpl: dict, value_tpl: dict, title: str, base: str, tooltip: str, title_rect: dict,
                value_rect: dict) -> list[dict]:
    """The row's title (a copy of D2R's elemental title with the literal text and tooltip) and its three value boxes."""
    t = copy.deepcopy(title_tpl)
    t["name"] = f"{base[:-4]}ResistanceTitle"
    t["fields"]["rect"] = title_rect
    t["fields"]["text"] = title
    for c in t.get("children", []):
        if c.get("name") == "Tooltip":
            c.setdefault("fields", {})["tooltipString"] = tooltip
            c["fields"].setdefault("fitToParent", True)
    out = [t]
    for suffix, colour in COLOURS:
        v = copy.deepcopy(value_tpl)
        v["name"] = base + suffix
        v["fields"]["rect"] = value_rect
        v["fields"].pop("text", None)
        v["fields"].setdefault("style", {})["fontColor"] = colour
        out.append(v)
    return out


def insert_after(lay: dict, after: str, widgets: list[dict]) -> None:
    kids = lay["children"]
    i = next(i for i, c in enumerate(kids) if c.get("name") == after)
    kids[i + 1:i + 1] = widgets


def pc_hd(lay: dict) -> dict:
    fire_t, fire_v = find(lay, "FireResistanceTitle"), find(lay, "FireText")
    light_t, light_v = find(lay, "LightningResistanceTitle"), find(lay, "LightningText")
    y, h = HD_ROW
    widgets = []
    for (title, base, tip), (t, v) in zip(ROWS, ((fire_t, fire_v), (light_t, light_v))):
        tr, vr = t["fields"]["rect"], v["fields"]["rect"]
        widgets += row_widgets(fire_t, fire_v, f"{title} Resistance", base, tip,
                               rect(tr["x"], y, tr["width"], h), rect(vr["x"], y, vr["width"], h))
    insert_after(lay, "PoisonText", widgets)
    pts = find(lay, "CombinedPointsInfo")
    pts["fields"]["rect"] = points_rect(pts["fields"]["rect"])
    return lay


def legacy(lay: dict) -> dict:
    fire_t, fire_v = find(lay, "FireResistanceTitle"), find(lay, "FireText")
    ft, fv = fire_t["fields"]["rect"], fire_v["fields"]["rect"]
    widgets = []
    for (title, base, tip), top in zip(ROWS, LEGACY_ROWS):
        dy = top - FIRE_BOX[1]
        tx = LEGACY_X + (ft["x"] - FIRE_BOX[0])
        tw = legacy_x(270) - tx                                  # to the cell separator
        widgets += row_widgets(fire_t, fire_v, f"{title}\nResistance", base, tip,
                               rect(tx, ft["y"] + dy, tw, ft["height"]), rect(legacy_x(fv["x"]), fv["y"] + dy, fv["width"], fv["height"]))
    for w in widgets:                                            # no tooltips in D2R's classic sheet either
        w.pop("children", None)
    widgets.append({"type": "Widget", "name": LEGACY_MARKER})
    insert_after(lay, "PoisonText", widgets)
    return lay


def pad(lay: dict) -> dict:
    bg, t, v = find(lay, "PoisonResistanceBG"), find(lay, "PoisonResistanceTitle"), find(lay, "PoisonText")
    tr, vr = t["fields"]["rect"], v["fields"]["rect"]
    widgets = []
    for (title, base, tip), top in zip(ROWS, PAD_ROWS):
        img = copy.deepcopy(bg)
        img["name"] = f"{base[:-4]}ResistanceBG"
        img["fields"]["rect"] = rect(bg["fields"]["rect"]["x"], top)
        widgets.append(img)
        widgets += row_widgets(t, v, f"{title} Resistance", base, tip, rect(tr["x"], top + PAD_TEXT_DY, tr["width"], tr["height"]),
                               rect(vr["x"], top + PAD_TEXT_DY, vr["width"], vr["height"]))
    insert_after(lay, "PoisonText", widgets)
    return lay


def build(d2r: Path, data: Path) -> list[str]:
    import dc6
    import pad_ui
    import rotw_stash_legacy as rsl
    import ui_art
    import median_stash
    report: list[str] = []
    table = strings(d2r)
    src = Path(d2r) / "data" / LAYOUTS
    for name, edit in ((PC_HD, pc_hd), (LEGACY, legacy), (PAD, pad)):
        lay = edit(pad_ui.load((src / name).read_text("utf-8-sig")))
        used: set[str] = set()
        literalize(lay, table, used)
        p = data / LAYOUTS / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(lay, indent=1, ensure_ascii=False) + "\n", "utf-8", newline="")
        report.append(f"{name}: Magic / Physical Resistance rows, {len(used)} string keys written out")
    art = hd_art(rsl.D2R(d2r).sprite(BACKGROUND)[0])
    out = data / "hd" / "global" / "ui" / f"{BACKGROUND}.sprite"
    ui_art.write_sprite(out, [art])
    ui_art.write_sprite(out.with_name(out.stem + ".lowend.sprite"), [median_stash.lowend(art)])
    report.append(f"hd/global/ui/{BACKGROUND}(.lowend).sprite: third row of resistance boxes")
    inv = data / INVCHAR
    if not inv.exists():
        raise SystemExit(f"{inv} missing: run tools/legacy_art.py first")
    report.append(edit_invchar(inv, dc6.palette(Path(d2r) / "data" / "global" / "palette" / "units" / "pal.dat")))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--d2r", type=Path, default=None)
    ap.add_argument("--mod", type=Path, default=ROOT / "work" / "mod" / "data")
    a = ap.parse_args(argv)
    if a.d2r is None:
        import fxpaths
        a.d2r = Path(fxpaths.D2R)
    for line in build(a.d2r, a.mod):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
