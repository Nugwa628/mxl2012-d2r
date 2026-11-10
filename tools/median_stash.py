"""Median's own runes and gems in the Reign of the Warlock stash's Runes and Gems pages (lane medstash, owner 2026-11-05).

D2R's RotW stash takes an item into its Gems / Materials / Runes pages when the misc row has `AdvancedStashStackable` 1 and
the HD layout (`bankexpansionlayouthd.json`) has an `AdvancedStashSlotWidget` with its `itemCode` (docs/stacking-research.md,
bug #510). Nothing else knows the codes: a slot for a Median code works like D2R's own (Ctrl-click deposit, stacks, count,
withdraw; in game, docs/testing.md "Lane medstash"). Median 2012 adds 23 runes (`r34`-`r56`) and 25 gems in five families
(Rainbow Stone `yo1`-`yo5`, Onyx `g$a`-`g$e`, Bloodstone `9$a`-, Turquoise `7$a`-, Amber `5$a`-) to D2R's 33 runes and 35
gems / skulls. D2R's pages have no room for them (slot recesses painted for its own codes), so both pages are redrawn:

  grid    9 columns (x 114 + 104 i, D2R's Runes page pitch) x 5 rows (y 218 + 98 j, D2R's Gems page pitch) above the cube
          plinth (y 717), then up to 5 more rows (y 708 + 98 j) in four columns beside the plinth (x 114, 218 | 842, 946).
          9 columns at pitch 104 is also the most the classic page takes (28-pixel cells, x / 3.631)
  Runes   r01-r45 in the grid in reading order, r46-r56 in the side columns (3 rows, reading order across both sides)
  Gems    one column per family, chipped at the top as D2R: D2R's 7, Rainbow Stone, Onyx in the grid; Bloodstone,
          Turquoise and Amber in the side columns x 114, 218, 946 (rows 6-10; the lower band is stone on the sides)
  art     D2R's Materials page (one stone field with the cube plinth): its recesses filled with stone from its own clean
          side field, then a recess on every slot (D2R's own 1 x 1 recesses of that page, in turn, each found by
          its dark inside and cut to the slot's 98 x 98, the inside 3 pixels in: D2R's sit -4 to +5 pixels off their
          rects), written as
          PANEL\\Stash\\AdditionalStash\\PANEL_AdditionalStash_{Gems,Runes} (+ .lowend): the mod's file replaces D2R's

tools/ui_layouts.py (stash_hd) writes the slots into the HD layout, tools/hd_ui.py build the page art,
tools/rotw_stash_legacy.py the classic pages from both, tools/d2r_adds.py the misc flag (`advanced_stash`). The gamepad
layout (controller/bankexpansionlayouthd.json) has D2R's console art and stays D2R's: with a gamepad the Median codes have
no slot (their stacks stay in the save).

  py -3 -I tools/median_stash.py preview DIR   the two HD pages as PNG with the slot codes drawn in, for review
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # the art only: d2r_adds reads the code lists without Pillow
    from PIL import Image, ImageDraw
except ImportError:
    Image = ImageDraw = None

PAGE_W, PAGE_H = 1162, 1507
SLOT = 98
MEDIAN_RUNES = [f"r{n}" for n in range(34, 57)]
MEDIAN_GEM_FAMILIES = [[f"yo{q}" for q in range(1, 6)]] + [[f"{p}${q}" for q in "abcde"] for p in "g975"]
MEDIAN_GEMS = [c for fam in MEDIAN_GEM_FAMILIES for c in fam]
CODES = MEDIAN_RUNES + MEDIAN_GEMS              # the misc rows that get AdvancedStashStackable 1 (d2r_adds)
PAGES = ("gems", "runes")
COL_X = [114 + 104 * i for i in range(9)]
ROW_Y = [218 + 98 * j for j in range(5)]
SIDE_X = (114, 218, 842, 946)
SIDE_Y = [708 + 98 * j for j in range(5)]
GEM_SIDE_X = (114, 218, 946)                    # Bloodstone, Turquoise, Amber
RUNE_SIDE_ROWS = 3
ART = {"gems": "panel_additionalstash_gems", "runes": "panel_additionalstash_runes"}
BASE_ART = "panel_additionalstash_consumables"  # D2R's Materials page
STONE = (100, 725, 355, 1095)                   # a clean stone field of the Materials page (left of the plinth)
TOP_FIELD = (86, 216, 1077, 716)                # the Materials page's slot field above the plinth
BAND_SIDES = ((86, 1096, 361, 1203), (800, 1096, 1077, 1203))  # the lower band beside the plinth (gems: a fifth side row)


def slots(page: str, d2r_slots: list[tuple[str, tuple[int, int, int, int]]]) -> list[tuple[str, tuple[int, int, int, int]]]:
    """The page's [(code, (x, y, w, h))] for D2R's slots of that page (its HD layout, in order) plus Median's."""
    if page == "runes":
        codes = [c for c, _r in d2r_slots] + MEDIAN_RUNES
        places = [(x, y) for y in ROW_Y for x in COL_X] + [(x, y) for y in SIDE_Y[:RUNE_SIDE_ROWS] for x in SIDE_X]
        if len(codes) > len(places):
            raise ValueError(f"runes: {len(codes)} codes, {len(places)} places")
    elif page == "gems":
        cols: dict[int, list[tuple[int, str]]] = {}
        for c, (x, y, _w, _h) in d2r_slots:
            cols.setdefault(x, []).append((y, c))
        families = [[c for _y, c in sorted(v)] for _x, v in sorted(cols.items())] + MEDIAN_GEM_FAMILIES
        xs = [(x, ROW_Y) for x in COL_X] + [(x, SIDE_Y) for x in GEM_SIDE_X]
        if len(families) > len(xs) or any(len(f) > 5 for f in families):
            raise ValueError(f"gems: {len(families)} families for {len(xs)} columns")
        codes, places = [], []
        for fam, (x, ys) in zip(families, xs):
            codes += fam
            places += [(x, y) for y in ys[:len(fam)]]
    else:
        raise ValueError(page)
    return [(c, (x, y, SLOT, SLOT)) for c, (x, y) in zip(codes, places)]


def widget(page: str, d2r_widget: dict) -> dict:
    """D2R's `advancedstash_<page>` widget with the slots of `slots`."""
    d2r_slots = _rects(d2r_widget.get("children", []))
    others = [c for c in d2r_widget.get("children", []) if c.get("type") != "AdvancedStashSlotWidget"]
    kids = [{"type": "AdvancedStashSlotWidget", "name": c,
             "fields": {"rect": {"width": w, "height": h, "x": x, "y": y}, "itemCode": c}}
            for c, (x, y, w, h) in slots(page, d2r_slots)]
    return {**d2r_widget, "children": kids + others}


def _find(node: dict, name: str) -> dict | None:
    if node.get("name") == name:
        return node
    for c in node.get("children", []):
        r = _find(c, name)
        if r is not None:
            return r
    return None


def apply(layout: dict) -> dict:
    """A parsed HD stash layout with Median's slots (in place; returned)."""
    for page in PAGES:
        w = _find(layout, f"advancedstash_{page}")
        if w is None:
            raise ValueError(f"no advancedstash_{page} in the layout")
        w.update(widget(page, w))
    return layout


def _stone_fill(im: Image.Image, box: tuple[int, int, int, int], src: Image.Image, rng: random.Random) -> None:
    """`box` covered with tiles of `src` (mirrored in turn so the seams meet their own edge)."""
    x0, y0, x1, y1 = box
    tw, th = src.size
    variants = [src, src.transpose(Image.FLIP_LEFT_RIGHT), src.transpose(Image.FLIP_TOP_BOTTOM),
                src.transpose(Image.ROTATE_180)]
    for ty in range(y0, y1, th):
        for tx in range(x0, x1, tw):
            t = variants[rng.randrange(4)].crop((0, 0, min(tw, x1 - tx), min(th, y1 - ty)))
            im.paste(t, (tx, ty))


RECESS_IN = 91                                              # a Materials recess's dark inside: 91 x 91, 1 x 2: 91 x 190
RECESS_LEAD = 3                                             # its frame left of / above the inside: cell 3 + 91 + 4, 3 + 190 + 3
RECESS_DARK = 28                                            # brightness under which a pixel is recess inside (stone: 40+)


def _runs(flags) -> tuple[int, int]:
    """First and last index of the longest run of True in `flags`."""
    best, start = (0, -1), None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start > best[1] - best[0] + 1:
                best = (start, i - 1)
            start = None
    return best


def recess_inside(lum, rect: tuple[int, int, int, int], margin: int = 10) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the dark inside of the recess D2R painted for the slot `rect` (`lum`: the page's brightness, rows x
    columns). D2R's recesses sit -2 to +5 pixels off their layout rects (the Materials page's own slots), so the art is placed
    by this box, never by the rect: copied by the rect, every cell's frame drifted against its slot and its neighbours."""
    import numpy as np
    x, y, w, h = rect
    dark = np.asarray(lum)[y - margin:y + h + margin, x - margin:x + w + margin] < RECESS_DARK
    x0, x1 = _runs(dark.mean(0) > 0.6)
    y0, y1 = _runs(dark.mean(1) > 0.6)
    return x - margin + x0, y - margin + y0, x1 - x0 + 1, y1 - y0 + 1


def recess_tiles(materials, d2r_mat_slots) -> dict[tuple[int, int], list]:
    """D2R's Materials recesses as cell pictures {(w, h): [RGBA]} of exactly a slot's size (98 x 98, 98 x 196), each cut so its
    inside starts RECESS_LEAD pixels in: pasted at a slot's rect, every frame sits the same on its slot."""
    import numpy as np
    base = materials.convert("RGBA")
    lum = np.asarray(base.convert("L"), dtype=np.int16)
    out: dict[tuple[int, int], list] = {(SLOT, SLOT): [], (SLOT, 2 * SLOT): []}
    for code, (x, y, w, h) in d2r_mat_slots:
        if (w, h) not in out:
            continue
        ix, iy, iw, ih = recess_inside(lum, (x, y, w, h))
        if (iw, ih) != (RECESS_IN, h - 2 * RECESS_LEAD if h > SLOT else RECESS_IN):
            raise ValueError(f"Materials recess of {code}: inside {iw} x {ih} at ({ix}, {iy}), {RECESS_IN} wide expected")
        out[(w, h)].append(base.crop((ix - RECESS_LEAD, iy - RECESS_LEAD, ix - RECESS_LEAD + w, iy - RECESS_LEAD + h)))
    if not out[(SLOT, SLOT)]:
        raise ValueError("D2R's Materials page has no 1 x 1 recess")
    return out


def page_art(page: str, materials: Image.Image, materials_slots: list[tuple[str, tuple[int, int, int, int]]],
             page_slots: list[tuple[str, tuple[int, int, int, int]]]) -> Image.Image:
    """The HD page (1162 x 1507 RGBA) for `page_slots`, drawn on D2R's Materials page (`materials`, its layout slots)."""
    if materials.size != (PAGE_W, PAGE_H):
        raise ValueError(f"{BASE_ART}: {materials.size}, {PAGE_W} x {PAGE_H} expected")
    base = materials.convert("RGBA")
    im = base.copy()
    rng = random.Random(page)
    stone = base.crop(STONE)
    _stone_fill(im, TOP_FIELD, stone, rng)
    if page == "gems":
        for box in BAND_SIDES:
            _stone_fill(im, box, stone, rng)
    tiles = recess_tiles(materials, materials_slots)[(SLOT, SLOT)]
    for i, (_c, (x, y, _w, _h)) in enumerate(page_slots):
        im.paste(tiles[i % len(tiles)], (x, y))  # the recess fills the slot's rect exactly (recess_tiles)
    return im


def lowend(im: Image.Image) -> Image.Image:
    return im.resize((im.width // 2, im.height // 2), Image.LANCZOS)


def _rects(children: list[dict]) -> list[tuple[str, tuple[int, int, int, int]]]:
    return [(c["fields"]["itemCode"], tuple(c["fields"]["rect"][k] for k in ("x", "y", "width", "height")))
            for c in children if c.get("type") == "AdvancedStashSlotWidget"]


def page_image(page: str, d2r_layout: dict, materials: Image.Image, stone_only: bool = False) -> Image.Image:
    """The HD page picture for D2R's layout (`d2r_layout`, unchanged) and D2R's Materials page (`materials`); `stone_only`: the
    same page without the recesses (what the classic page shrinks before it puts a recess on each classic box)."""
    mat_slots = _rects(_find(d2r_layout, "advancedstash_materials")["children"])
    slots = [] if stone_only else _rects(widget(page, _find(d2r_layout, f"advancedstash_{page}"))["children"])
    return page_art(page, materials, mat_slots, slots)


def build(d2r_layout: dict, materials: Image.Image, out_dir: Path) -> list[str]:
    """The two HD page pictures (+ .lowend) into `out_dir` (data/hd/global/ui/panel/stash/additionalstash)."""
    import ui_art
    report = []
    for page in PAGES:
        im = page_image(page, d2r_layout, materials)
        ui_art.write_sprite(out_dir / f"{ART[page]}.sprite", [im])
        ui_art.write_sprite(out_dir / f"{ART[page]}.lowend.sprite", [lowend(im)])
        n = len(_rects(widget(page, _find(d2r_layout, f"advancedstash_{page}"))["children"]))
        report.append(f"{ART[page]}.sprite: {n} slots on D2R's Materials page (+ lowend)")
    return report


def preview(d2r_layout: dict, materials: Image.Image, dest: Path) -> list[Path]:
    """PNG of each page with the slot codes written in (review only)."""
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for page in PAGES:
        im = page_image(page, d2r_layout, materials)
        d = ImageDraw.Draw(im)
        for c, (x, y, _w, _h) in _rects(widget(page, _find(d2r_layout, f"advancedstash_{page}"))["children"]):
            d.text((x + 6, y + 4), c, fill=(255, 220, 120) if c in CODES else (160, 160, 160))
        p = dest / f"median_stash_{page}.png"
        im.save(p)
        out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    import fxpaths
    import rotw_stash_legacy as rsl
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != "preview":
        print(__doc__)
        return 2
    d2r = rsl.D2R(fxpaths.D2R)
    for p in preview(d2r.layout(rsl.HD_LAYOUT), d2r.sprite(f"panel/stash/additionalstash/{BASE_ART}")[0], Path(argv[1])):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
