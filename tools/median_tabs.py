"""Median XL stash tabs (lane medtab, owner 2026-11-06): tabs 6 MEDIAN and 7 ORBS, and a Vanilla / Median selector inside the
Materials tab (docs/median-stash-tab.md). A build step (tools/build.py, after rotw_stash_legacy.py) applies it to work/mod/data;
tools/d2r_adds.py sets the codes' misc flag `AdvancedStashStackable`; the plugin part `medtab` (plugin/src/median_tabs.cpp)
drives the tabs. The layouts and the plugin ship together: without the plugin tab 6 asserts and crashes, so tools/install_mod.py
and tools/package_release.py refuse a 7-tab layout without a medtab plugin (docs/median-stash-tab.md "Plugin and layout").

D2R's stash init builds each advanced tab's accepted codes from the direct AdvancedStashSlotWidget children of
advancedstash_gems / _materials / _runes (static table 0x2363fa0: categories 1-3 -> pages 2-4), so the new slots are direct
children of those widgets:
  advancedstash_runes      + MEDIAN (55 elixirs / signets / trophies, 20 full shrines) and ORBS (100 Mystic Orbs), each with
                           a background picture (`medtab_median_bg`, `medtab_orbs_bg`) that covers the Runes art (no plinth)
  advancedstash_materials  + the Median page (29 oils, arcane pieces, reagents; `medtab_mat_bg` over the vanilla recesses,
                           plinth kept) and a selector on both pages (`medtab_sel_vanilla`, `medtab_sel_median`)
D2R's own slots whose code is no item of the mod (20 on the vanilla Materials page: keys, organs, essences, shards, `ua1`-`ua5`)
are removed first: their empty-slot placeholder had item class -1 and every draw of one asserted (bug #548).
The plugin shows one group at a time (tab 5 / 6 / Runes; selector Vanilla / Median). The tab bar gets 7 tabs (HD 139 x 72,
classic 44 x 24 with the names in the art).

The 9 codes with "@" (b@b c@c !@B l@l m@m o@o p@p q@q u@v): D2R's layout loader reads "@key" anywhere in a string as a string key,
so "b@b" grew past 4 characters and AdvancedStashSlotWidget's code read (0x2ce910) asserted. The layouts write them with
PLACEHOLDER ("b_b"; no item code has "_") and the plugin puts the "@" back into the widget's own string before that read: the
items keep their codes, so no save changes.

  py -3 -I tools/median_tabs.py apply [DATA]   (default work/mod/data; the misc flag must be set already: tools/d2r_adds.py)
  py -3 -I tools/median_tabs.py header [DATA]  plugin/src/medtab_names.h (the plugin's group lists)
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from median_stash import RECESS_IN, RECESS_LEAD, recess_inside, recess_tiles  # noqa: E402,F401  (the recess art, shared)

ELIXIRS = "eo7 eo8 eo9 ey1 ey2 ey3 ey4 ey5 ey6 ey7 ey8 ey9 et1 0g7 0g8 0g0 0g1 0g2 0g3 0g4 0g5 0g6 b@b".split()
SIGNETS = "zkw zku zkq zkx zky zkr zka zkb zkc zkd zke zkf quz zog zoh c@c !@B dog".split()
TROPHIES = [f"^{n:02d}" for n in range(1, 15)]
SHRINES = [f"{chr(65 + k)}0+" for k in range(20)]           # charge 10 of each kind
OILS = "6o^ 2o^ 4o^ 5o^ 1o^ 7o^ 8o^ 0o^ 3o^ 9o^".split()
ARCANE = "qus qut qux quy qul qum".split()
REAGENTS = "2x5 2x6 2x7 2x8 2x9 vic mec l@l m@m o@o p@p q@q u@v".split()
ORBS = ("&01 &02 &03 &04 &45 &11 &17 &18 &19 &20 &05 &06 &07 &08 &09 &10 &12 &13 &14 &15 &16 &41 &42 &43 &44 &21 &22 &23 "
        "&24 &25 &26 &27 &28 &29 &30 &46 &47 &48 &49 &50 &51 &52 &53 &54 &55 &31 &32 &33 &34 &35 &36 &37 &38 &39 &40 &56 "
        "&57 &58 &59 &60 &61 &62 &63 &64 &65 &66 &67 &68 &69 &70 &71 &72 &73 &74 &75 &76 &77 &78 &79 &80 &81 &82 &83 &84 "
        "&85 &a1 &a2 &a3 &a4 &a5 &86 &87 &88 &89 &90 &91 &92 &93 &94 &95").split()
SINGLES = ELIXIRS + SIGNETS + TROPHIES
MAT_MEDIAN = OILS + ARCANE + REAGENTS
CODES = SINGLES + SHRINES + ORBS + MAT_MEDIAN               # AdvancedStashStackable 1
assert len(SINGLES) == 55 and len(ORBS) == 100 and len(MAT_MEDIAN) == 29 and len(set(CODES)) == len(CODES) == 204
PLACEHOLDER = "_"
AT_CODES = [c for c in CODES if "@" in c]


def layout_code(code: str) -> str:
    """The itemCode written into a layout: "@" as PLACEHOLDER (the plugin restores it, median_tabs_logic.h)."""
    return code.replace("@", PLACEHOLDER)


def real_code(code: str) -> str:
    """The item code of a layout itemCode (layout_code reversed)."""
    return code.replace(PLACEHOLDER, "@") if code in {layout_code(c) for c in AT_CODES} else code

SLOT = 98
GRID = (89, 219)                                            # the shared stash grid: a Median page is its 10 x 10
FIELD = (86, 212, 1077, 1430)                               # the page interior the MEDIAN / ORBS background covers
MAT_FIELD = (86, 216, 1077, 716)                            # the Materials page's slot field above the plinth
COL_X = [114 + 104 * i for i in range(9)]                   # tools/median_stash.py's grid on the Materials art
ROW_Y = [218 + 98 * j for j in range(5)]
HD_TABS = 7
HD_TAB_W = 975 // HD_TABS                                   # D2R's 5 x 195 row shared by 7
HD_TAB_FONT = 18                                            # $SmallFontSize is 22: "Materials" fits 139
TAB_NAMES = ["Personal", "Shared", "Gems", "Materials", "Runes", "Median", "Orbs"]
SD_TAB_NAMES = ["PERSON", "SHARED", "GEMS", "MATS", "RUNES", "MEDIAN", "ORBS"]
SD_TAB_W, SD_TAB_H, SD_TAB_PAD = 44, 24, 1
TOGGLE = "PanelManager:OpenPanel:mxl2012-core/MedtabMaterials"   # the selector arrows; the plugin consumes it
LAYOUT_MARK = "medtab_sel_vanilla"                          # the plugin's sign of a 7-tab layout (HD and classic)
SEL_HD = (98, 1236, 250, 150)                               # the selector: left ornament under the plinth's band
SEL_SD = (25, 350, 72, 56)
TEXT_HD = {"fontColor": "$PanelTitleColor", "pointSize": "$MediumFontSize", "alignment": {"v": "center", "h": "center"},
           "dropShadow": "$DefaultDropShadow"}


def median_slots() -> list[tuple[str, tuple[int, int, int, int]]]:
    gx, gy = GRID
    out = [(c, (gx + SLOT * (i % 10), gy + SLOT * (i // 10), SLOT, SLOT)) for i, c in enumerate(SINGLES)]
    out += [(c, (gx + SLOT * (k % 10), gy + SLOT * (6 + 2 * (k // 10)), SLOT, 2 * SLOT)) for k, c in enumerate(SHRINES)]
    return out


def orbs_slots() -> list[tuple[str, tuple[int, int, int, int]]]:
    gx, gy = GRID
    return [(c, (gx + SLOT * (i % 10), gy + SLOT * (i // 10), SLOT, SLOT)) for i, c in enumerate(ORBS)]


def mat_slots() -> list[tuple[str, tuple[int, int, int, int]]]:
    places = [(x, y) for y in ROW_Y for x in COL_X]
    return [(c, (x, y, SLOT, SLOT)) for c, (x, y) in zip(MAT_MEDIAN, places)]


# the new pages: background picture name, HD slots, the HD field the picture covers
PAGES = [("medtab_median_bg", median_slots(), FIELD), ("medtab_orbs_bg", orbs_slots(), FIELD),
         ("medtab_mat_bg", mat_slots(), MAT_FIELD)]


def slot(code, r):
    x, y, w, h = r
    return {"type": "AdvancedStashSlotWidget", "name": layout_code(code),
            "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}, "itemCode": layout_code(code)}}


def image(name, x, y, filename):
    return {"type": "ImageWidget", "name": name, "fields": {"rect": {"x": x, "y": y}, "filename": filename}}


def selector_hd(name: str, label: str) -> dict:
    x, y, w, h = SEL_HD
    arrow = {"normalFrame": 0, "pressedFrame": 2, "hoveredFrame": 1, "disabledFrame": 3}
    return {"type": "ImageWidget", "name": name, "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}, "filename": "PANEL\\mxl\\medtab_sel"},
            "children": [
                {"type": "TextBoxWidget", "name": name + "_text", "fields": {"text": label, "rect": {"x": 0, "y": 10, "width": w, "height": 56}, "style": TEXT_HD}},
                {"type": "ButtonWidget", "name": name + "_l", "fields": {"rect": {"x": 45, "y": 74, "width": 64, "height": 64},
                 "filename": "PANEL\\Stash\\Stash_LeftArrow", **arrow, "onClickMessage": TOGGLE}},
                {"type": "ButtonWidget", "name": name + "_r", "fields": {"rect": {"x": 141, "y": 74, "width": 64, "height": 64},
                 "filename": "PANEL\\Stash\\Stash_RightArrow", **arrow, "onClickMessage": TOGGLE}}]}


def selector_sd(name: str, label: str) -> dict:
    x, y, w, h = SEL_SD
    return {"type": "ImageWidget", "name": name, "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}, "filename": "PANEL\\mxl\\medtab_sel"},
            "children": [
                {"type": "TextBoxWidget", "name": name + "_text", "fields": {"text": label, "rect": {"x": 0, "y": 2, "width": w, "height": 18},
                 "style": {**TEXT_HD, "pointSize": "$MediumFontSize"}}},
                {"type": "ButtonWidget", "name": name + "_l", "fields": {"rect": {"x": 4, "y": 22, "width": 32, "height": 32},
                 "filename": "PANEL\\buysellbtn", "normalFrame": 12, "pressedFrame": 13, "onClickMessage": TOGGLE}},
                {"type": "ButtonWidget", "name": name + "_r", "fields": {"rect": {"x": 36, "y": 22, "width": 32, "height": 32},
                 "filename": "PANEL\\buysellbtn", "normalFrame": 14, "pressedFrame": 15, "onClickMessage": TOGGLE}}]}


def find(node, name):
    if node.get("name") == name:
        return node
    for c in node.get("children", []):
        r = find(c, name)
        if r is not None:
            return r
    return None


# D2R's stash init casts every direct child of advancedstash_gems / _materials / _runes to a slot (0x2ce910 on a null cast
# crashed: lane medtab), so the pages' pictures and the selectors are siblings of the page widgets in the panel root, hidden
# until the plugin shows them: the pictures just before advancedstash_runes (drawn under its slots), the selectors after it.


def hidden(w: dict) -> dict:
    w["fields"]["visible"] = False
    return w


def place(lay: dict, page: str, slots: list[dict], pictures: list[dict], selectors: list[dict]) -> None:
    find(lay, page)["children"] += slots
    root = lay["children"]
    at = next(i for i, c in enumerate(root) if c.get("name") == page)
    root[at:at] = [hidden(w) for w in pictures]
    at = next(i for i, c in enumerate(root) if c.get("name") == "advancedstash_runes") + 1
    root[at:at] = [hidden(w) for w in selectors]


# ---- HD ----------------------------------------------------------------------------------------------------------------

def applied(lay: dict) -> bool:
    return find(lay, "BankTabs")["fields"].get("tabCount") == HD_TABS


def apply_hd(lay: dict) -> dict:
    if applied(lay):
        raise ValueError("the HD stash layout has 7 tabs already (median_tabs applied twice)")
    t = find(lay, "BankTabs")["fields"]
    t.update({"tabCount": HD_TABS, "filename": "PANEL\\mxl\\medtab_tabs", "inactiveFrames": [0] * HD_TABS,
              "activeFrames": [1] * HD_TABS, "disabledFrames": [-1] + [0] * (HD_TABS - 1),
              "textStrings": list(t["textStrings"]) + TAB_NAMES[5:], "tabSize": {"x": HD_TAB_W, "y": 72},
              "textStyle": {"pointSize": HD_TAB_FONT}})
    # backgroundFile stays 5 (D2UI WidgetLoader: "maximum is 5"; 7 asserted and crashed): tabs 5 / 6 draw entry 4, the getter's Runes
    place(lay, "advancedstash_runes", [slot(c, r) for c, r in median_slots() + orbs_slots()],
          [image("medtab_median_bg", FIELD[0], FIELD[1], "PANEL\\mxl\\medtab_median_bg"),
           image("medtab_orbs_bg", FIELD[0], FIELD[1], "PANEL\\mxl\\medtab_orbs_bg")], [])
    place(lay, "advancedstash_materials", [slot(c, r) for c, r in mat_slots()],
          [image("medtab_mat_bg", MAT_FIELD[0], MAT_FIELD[1], "PANEL\\mxl\\medtab_mat_bg")],
          [selector_hd("medtab_sel_vanilla", "Vanilla"), selector_hd("medtab_sel_median", "Median")])
    return lay


# ---- classic -----------------------------------------------------------------------------------------------------------

def apply_sd(lay: dict) -> dict:
    import rotw_stash_legacy as rsl
    if applied(lay):
        raise ValueError("the classic stash layout has 7 tabs already (median_tabs applied twice)")
    t = find(lay, "BankTabs")["fields"]
    t.update({"tabCount": HD_TABS, "inactiveFrames": list(range(HD_TABS)), "activeFrames": list(range(HD_TABS, 2 * HD_TABS)),
              "disabledFrames": [-1] + list(range(1, HD_TABS)), "textStrings": [""] * HD_TABS,
              "tabSize": {"x": SD_TAB_W, "y": SD_TAB_H}, "tabPadding": {"x": SD_TAB_PAD, "y": 0}})

    def cslots(group):
        return [{"type": "AdvancedStashSlotWidget", "name": layout_code(c),
                 "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}, "itemCode": layout_code(c)}}
                for c, (x, y, w, h) in classic_slots(group)]

    def tiles(name, box):
        x0, y0, w, h = classic_field(box)
        return [image(f"{name}_{i}", x0 + tx, y0 + ty, f"PANEL\\mxl\\{name}_{i}") for i, (tx, ty) in enumerate(_tile_origins(w, h))]

    place(lay, "advancedstash_runes", cslots(median_slots()) + cslots(orbs_slots()),
          tiles("medtab_median_bg", FIELD) + tiles("medtab_orbs_bg", FIELD), [])
    place(lay, "advancedstash_materials", cslots(mat_slots()), tiles("medtab_mat_bg", MAT_FIELD),
          [selector_sd("medtab_sel_vanilla", "VANILLA"), selector_sd("medtab_sel_median", "MEDIAN")])
    return lay


def _tile_origins(w, h, n=256):
    return [(x, y) for y in range(0, h, n) for x in range(0, w, n)]


# ---- art ---------------------------------------------------------------------------------------------------------------

def stone_art(materials, box, seed):
    """`box` of D2R's Materials page covered with its own clean stone (no recess)."""
    import median_stash as ms
    base = materials.convert("RGBA")
    im = base.copy()
    ms._stone_fill(im, box, base.crop(ms.STONE), random.Random(seed))
    return im.crop(box)


def page_art(materials, d2r_mat_slots, slots, box, seed):
    """`box` of D2R's Materials page: stone, with one of D2R's recesses of that page filling every slot's rect exactly."""
    im = stone_art(materials, box, seed)
    tiles = recess_tiles(materials, d2r_mat_slots)
    if not tiles[(SLOT, 2 * SLOT)]:
        raise ValueError("D2R's Materials page has no 1 x 2 recess")
    for i, (_c, (x, y, w, h)) in enumerate(slots):
        pick = tiles[(w, h)]
        im.paste(pick[i % len(pick)], (x - box[0], y - box[1]))
    return im


# ---- classic geometry and art ------------------------------------------------------------------------------------------
# Classic slots sit on an integer grid (the first slot's classic_box, then a whole-pixel pitch per axis: MEDIAN / ORBS 27 x 28,
# Median Materials 29 x 28), not on each HD rect rounded on its own: rounding gave 27 / 28 and 28 / 29 steps. The classic
# picture is drawn at classic size with a recess on exactly each of those boxes (not the HD picture shrunk, whose cells
# landed up to a pixel off the boxes).

def classic_field(box) -> tuple[int, int, int, int]:
    """The classic (x, y, w, h) of an HD field box (the background tiles' place)."""
    import rotw_stash_legacy as rsl
    return (round(box[0] / rsl.SX), round(box[1] / rsl.SY),
            round((box[2] - box[0]) / rsl.SX), round((box[3] - box[1]) / rsl.SY))


def classic_pitch(slots) -> tuple[int, int, int, int]:
    """(HD pitch x, HD pitch y, classic pitch x, classic pitch y) of a page's slot grid (rotw_stash_legacy.grid_pitch)."""
    import rotw_stash_legacy as rsl
    return rsl.grid_pitch(slots)


def classic_slots(slots) -> list[tuple[str, tuple[int, int, int, int]]]:
    """The classic [(code, (x, y, w, h))] of a page's HD slots on one integer grid (rotw_stash_legacy.grid_boxes)."""
    import rotw_stash_legacy as rsl
    return rsl.grid_boxes(slots)


def classic_page_art(hd_stone, hd_tiles, slots, box):
    """The classic picture of `box`: the HD stone shrunk, then a shrunk recess on exactly every classic slot box."""
    import rotw_stash_legacy as rsl
    fx, fy, fw, fh = classic_field(box)
    im = rsl.down(hd_stone, fw, fh)
    for i, (_c, (x, y, w, h)) in enumerate(classic_slots(slots)):
        if x < fx or y < fy or x + w > fx + fw or y + h > fy + fh:
            raise ValueError(f"classic slot {_c} {(x, y, w, h)} outside its field {(fx, fy, fw, fh)}")
        pick = hd_tiles[(SLOT, SLOT) if h < 2 * rsl.CELL else (SLOT, 2 * SLOT)]
        im.paste(rsl.down(pick[i % len(pick)], w, h), (x - fx, y - fy))
    return im


def tab_frames(sprite, width=HD_TAB_W):
    """D2R's two tab frames narrowed to `width` (the middle squeezed, the 22-pixel ends kept; tools/pad_ui.py: the gamepad tabs)."""
    from PIL import Image
    out = []
    for f in sprite[:2]:
        e = 22
        mid = f.crop((e, 0, f.width - e, f.height)).resize((width - 2 * e, f.height), Image.LANCZOS)
        im = Image.new("RGBA", (width, f.height))
        im.paste(f.crop((0, 0, e, f.height)), (0, 0))
        im.paste(mid, (e, 0))
        im.paste(f.crop((f.width - e, 0, f.width, f.height)), (width - e, 0))
        out.append(im)
    return out


def plate(w, h):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (w, h), (16, 15, 14, 235))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w - 1, h - 1), outline=(120, 98, 58, 255), width=max(1, w // 120))
    return im


def apply_art(data: Path, report: list[str]) -> None:
    import fxpaths
    import median_stash as ms
    import rotw_stash_legacy as rsl
    import ui_art
    d2r = rsl.D2R(fxpaths.D2R, use_cache=True)
    mat_art = d2r.sprite(f"panel/stash/additionalstash/{ms.BASE_ART}")[0]
    d2r_mat = ms._rects(ms._find(d2r.layout(rsl.HD_LAYOUT), "advancedstash_materials")["children"])
    hd_dir = data / "hd" / "global" / "ui" / "panel" / "mxl"
    sd_dir = data / "global" / "ui" / "panel" / "mxl"
    hd_dir.mkdir(parents=True, exist_ok=True)
    sd_dir.mkdir(parents=True, exist_ok=True)
    hd_tiles = recess_tiles(mat_art, d2r_mat)
    for name, slots, box in PAGES:
        im = page_art(mat_art, d2r_mat, slots, box, name)
        ui_art.write_sprite(hd_dir / f"{name}.sprite", [im])
        ui_art.write_sprite(hd_dir / f"{name}.lowend.sprite", [ms.lowend(im)])
        small = classic_page_art(stone_art(mat_art, box, name), hd_tiles, slots, box)
        w, h = small.size
        for i, (tx, ty) in enumerate(_tile_origins(w, h)):
            tile = small.crop((tx, ty, min(w, tx + 256), min(h, ty + 256)))
            (sd_dir / f"{name}_{i}.dc6").write_bytes(rsl.dc6_bytes([rsl.quantise(tile, d2r.pal)]))
        report.append(f"{name}: HD {im.size}, classic {w} x {h} in {len(_tile_origins(w, h))} tiles")
    sel = plate(*SEL_HD[2:])
    ui_art.write_sprite(hd_dir / "medtab_sel.sprite", [sel])
    ui_art.write_sprite(hd_dir / "medtab_sel.lowend.sprite", [ms.lowend(sel)])
    (sd_dir / "medtab_sel.dc6").write_bytes(rsl.dc6_bytes([rsl.quantise(plate(*SEL_SD[2:]), d2r.pal, dither=False)]))
    tabs = tab_frames(d2r.sprite("panel/stash/mkb_tabs_195_tga"))
    ui_art.write_sprite(hd_dir / "medtab_tabs.sprite", tabs)
    ui_art.write_sprite(hd_dir / "medtab_tabs.lowend.sprite", [ms.lowend(t) for t in tabs])
    # classic tab art: 7 inactive then 7 active frames with the names in font6 (rotw_stash_legacy.named_tab_frames, 44 wide)
    font = d2r.font(rsl.TAB_FONT)
    frames = []
    for state in (0, 1):
        base = rsl.down(d2r.sprite("panel/stash/mkb_tabs_195_tga")[state], SD_TAB_W, SD_TAB_H)
        for label in SD_TAB_NAMES:
            from PIL import Image
            text = font.render(label, rsl.TAB_COLOURS[state])
            if text.width > SD_TAB_W - 2 * rsl.TAB_TEXT_MARGIN:
                raise ValueError(f"classic tab {label}: {text.width} wide")
            layer = Image.new("RGBA", base.size)
            layer.alpha_composite(text, ((SD_TAB_W - text.width) // 2, (SD_TAB_H - text.height) // 2))
            import numpy as np
            ink = np.asarray(layer.getchannel("A")) >= 128
            idx = rsl.quantise(base, d2r.pal)
            idx[ink] = rsl.quantise(layer, d2r.pal, dither=False)[ink]
            frames.append(idx)
    (data / "global" / "ui" / "panel" / f"{rsl.TABS}.dc6").write_bytes(rsl.dc6_bytes(frames))
    report.append(f"tabs: HD medtab_tabs {HD_TAB_W} x 73 (2 frames), classic {rsl.TABS}.dc6 14 x {SD_TAB_W} x {SD_TAB_H}")


def check_misc(data: Path, report: list[str]) -> None:
    """Every code with a slot needs the misc flag AdvancedStashStackable (tools/d2r_adds.py step_advanced_stash): a slot without
    it takes nothing, and a build that drops the flag of a code deletes that code's stacks (#545)."""
    lines = (data / "global" / "excel" / "misc.txt").read_bytes().decode("latin-1").splitlines()
    head = lines[0].split("\t")
    ci, fi = head.index("code"), head.index("AdvancedStashStackable")
    flagged = {f[ci] for f in (line.split("\t") for line in lines[1:]) if len(f) > fi and f[fi] == "1"}
    missing = sorted(set(CODES) - flagged)
    if missing:
        raise ValueError(f"misc.txt: AdvancedStashStackable not set on {missing} (tools/d2r_adds.py)")
    report.append(f"misc.txt: AdvancedStashStackable 1 on all {len(CODES)} codes")


def item_codes(data: Path) -> set[str]:
    codes = set()
    for name in ("misc", "weapons", "armor"):
        lines = (data / "global" / "excel" / f"{name}.txt").read_bytes().decode("latin-1").splitlines()
        ci = lines[0].split("\t").index("code")
        codes |= {f[ci] for f in (line.split("\t") for line in lines[1:]) if len(f) > ci and f[ci]}
    return codes


def drop_unknown_slots(lay: dict, known: set[str]) -> list[str]:
    """Removes D2R's slots whose code is no item of the mod (the vanilla Materials page's keys, organs, essences, shards and
    `ua1`-`ua5`). Each empty slot draws a placeholder item made from its code (0x2cf260); an unknown code gives an item of class
    -1, and the first draw of one raised a burst of engine asserts (bug #548). Such a slot can never hold an item."""
    dropped = []
    for page in ("advancedstash_gems", "advancedstash_materials", "advancedstash_runes"):
        node = find(lay, page)
        keep = []
        for c in node["children"]:
            code = c.get("fields", {}).get("itemCode")
            if c.get("type") == "AdvancedStashSlotWidget" and real_code(code) not in known:
                dropped.append(code)
            else:
                keep.append(c)
        node["children"] = keep
    return dropped


def apply(data: Path) -> list[str]:
    import rotw_stash_legacy as rsl
    report = []
    check_misc(data, report)
    known = item_codes(data)
    lay_dir = data / "global" / "ui" / "layouts"
    hp = lay_dir / "bankexpansionlayouthd.json"
    hd = rsl.lenient_json(hp.read_text("utf-8"))
    report.append(f"HD layout: {len(drop_unknown_slots(hd, known))} slots without an item of the mod removed (#548)")
    hd = apply_hd(hd)
    hp.write_text(json.dumps(hd, indent=1, ensure_ascii=False) + "\n", "utf-8", newline="")
    sp = lay_dir / "bankexpansionlayout.json"
    if sp.exists():
        sd = rsl.lenient_json(sp.read_text("utf-8"))
        report.append(f"classic layout: {len(drop_unknown_slots(sd, known))} slots without an item of the mod removed (#548)")
        sd = apply_sd(sd)
        sp.write_text(json.dumps(sd, indent=1, ensure_ascii=False) + "\n", "utf-8", newline="")
    else:  # MXL2012_ROTW_LEGACY=0: legacy graphics keep D2R's 5 tabs (the plugin finds no LAYOUT_MARK there and stays out)
        report.append("classic layout: not in the mod (MXL2012_ROTW_LEGACY=0), left as D2R")
    report.append(f"layouts: 7 tabs; runes + {len(median_slots())} MEDIAN + {len(orbs_slots())} ORBS slots; materials + "
                  f"{len(mat_slots())} slots, 2 selectors; {len(AT_CODES)} codes written with {PLACEHOLDER!r} for '@'")
    apply_art(data, report)
    return report


def header(data: Path) -> str:
    """The plugin's widget groups, read from the applied layouts (HD and classic names together)."""
    import rotw_stash_legacy as rsl
    groups = {"RunesOwn": [], "Median": [], "Orbs": [], "MatVanilla": [], "MatMedian": [], "MatPicture": [], "Selector": []}
    median, orbs, mat = ({layout_code(c) for c in g} for g in (SINGLES + SHRINES, ORBS, MAT_MEDIAN))
    for f in ("bankexpansionlayouthd.json", "bankexpansionlayout.json"):
        lay = rsl.lenient_json((data / "global" / "ui" / "layouts" / f).read_text("utf-8-sig"))
        for c in rsl.find(lay, "advancedstash_runes")["children"]:
            n = c["name"]
            g = ("Median" if n in median or n.startswith("medtab_median") else "Orbs" if n in orbs or n.startswith("medtab_orbs")
                 else "RunesOwn")
            groups[g].append(n)
        for c in rsl.find(lay, "advancedstash_materials")["children"]:
            n = c["name"]
            groups["MatMedian" if n in mat else "MatVanilla"].append(n)
        for c in lay["children"]:
            n = c.get("name", "")
            if n.startswith("medtab_"):
                groups[{"medtab_me": "Median", "medtab_or": "Orbs", "medtab_ma": "MatPicture", "medtab_se": "Selector"}[n[:9]]].append(n)

    def arr(name, items):
        items = list(dict.fromkeys(items))
        return f"inline constexpr const char* {name}[] = {{\n" + "".join(f"    {json.dumps(s)},\n" for s in items) + "};\n"
    return ("// Generated by tools/median_tabs.py (header); do not edit.\n#pragma once\n\nnamespace medtab_names {\n\n"
            f'inline constexpr char Toggle[] = "{TOGGLE.split(":", 2)[2]}";\n'
            f'inline constexpr char LayoutMark[] = "{LAYOUT_MARK}";\n'
            f"inline constexpr char Placeholder = '{PLACEHOLDER}';\n"
            + arr("AtCodes", [layout_code(c) for c in AT_CODES])
            + "".join(arr(k, v) for k, v in groups.items()) + "\n}  // namespace medtab_names\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["apply"]:
        data = Path(argv[1]) if len(argv) > 1 else ROOT / "work" / "mod" / "data"
        for line in apply(data):
            print(line)
        return 0
    if argv[:1] == ["header"]:
        data = Path(argv[1]) if len(argv) > 1 else ROOT / "work" / "mod" / "data"
        p = ROOT / "plugin" / "src" / "medtab_names.h"
        p.write_text(header(data), encoding="utf-8", newline="\n")
        print(p)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
