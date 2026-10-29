"""HD skill tree pages for the 7 classic classes (adapted from another port's skill_tree_art.py).

Median XL 2012 v005 is a 1.13c data mod: every class has 3 skill pages (tabs) like D2R, but each page holds two chains of
5 skills, in columns 1 and 3 and rows 1-5 of the 3 x 6 grid (skilldesc.txt SkillPage / SkillRow / SkillColumn; D2R's own
trees fill other cells). The mod draws the sockets and arrows into `skltree_<x>_back.dc6` (classic mode reads these
as they are: set 0 = the tab column, sets 1-3 = a page each).

D2R HD draws the tree from one sprite per class (data/hd/global/ui/spells/skill_trees/<xx>skilltree.sprite): 3 frames of
895 x 1169 (stride 897, `.lowend` half size), frame n = tab n active: the tab strip across the top (stone tabs, the active
one lit, no text: D2R puts the title text on top), the skill sockets and the arrows. The panel shows it at 132, 160.
Tab n (0 = leftmost) shows SkillPage 3 - n (`page_of`), as the classic tab column lists page 3 at the top; seen in game
2026-10-29 (lane hdicons2: a page 3 skill's level on tab 0, page 1's on tab 2).
This tool keeps D2R's strip and draws the mod's own page art below it (`median_page`): the page part of the classic set
(left of the tab column, 228 x 432) with its stone, socket boxes, level boxes and arrows, scaled by K = 2.63 (the classic
row pitch 68 -> D2R's HD row pitch, so a 48-pixel box hole holds D2R's 130-pixel icon) and cut in three: the part
holding column 1 is placed so that its cells sit on D2R's HD column 1, the part holding column 3 on D2R's column 3, and
the empty stone of column 2 between them is stretched sideways to fill the wider HD gap (x 2.8). D2R draws the level number in a box right
of the icon's upper half, Median's art has it at the lower-right corner, so each cell's level box is moved there in the
classic picture first (the corner it leaves is filled with the mirrored lower-left corner of the same box). The mod's
pages only use columns 1 and 3 (all 7 classes); a class whose cells are elsewhere, or no classic DC6, falls back to the
older drawing: D2R's socket art (cut from its frame 1) on each cell that holds a skill, arrows between them.
`panel_skilltreebg` (the stone around the page) and the layout stay D2R's, and so does Warlock's page (`waskilltree`),
D2R's 8th class. The tab column of the classic art (labelled tree icons) has no place in D2R's HD tree: D2R's tab strip
and the title strings below replace it.

Arrows: the classic art has an arrow from each skill down to the next one in its column; a skill with `reqskill1/2` gets
one from the skill it requires when that sits on the same page, else from the cell above (the mod's art draws its chains
that way even where the required skill is an item/hidden one), a skill without a requirement gets none (page 3, column 3:
Amazon "Curare" ... "War Spirit", the passives, are loose boxes in the art too).

Tab titles: the classic art has them as small labelled icons (two per page: column 1's and column 3's tree), D2R as text
from the string keys `SkillCategory<Cl><n>` of its layout (`textTab0-2`), which D2R's own strings fill with its class tab
names ("Bow and Crossbow"...). So the titles go into `skill_tab_titles.json` as `d2r:SkillCategory..` override records for
the strings lane to merge into mxl2012/overrides.json (no sprite or layout edit; Warlock's keys are not touched).

  py -3 -I tools/skill_tree_art.py [--preview DIR]
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageDraw  # noqa: E402

import ui_art  # noqa: E402
from icon_paths import col, read_tsv  # noqa: E402
from ui_paths import BASE_UI, EXCEL, HD_OUT, MOD_UI, OUT, PAL, STRINGS_OUT  # noqa: E402

# charclass of skills.txt -> (D2R sprite prefix, classic file letter, D2R string key prefix)
CLASSES = {"ama": ("am", "a", "Am"), "sor": ("so", "s", "So"), "nec": ("ne", "n", "Ne"), "pal": ("pa", "p", "Pa"),
           "bar": ("ba", "b", "Ba"), "dru": ("dr", "d", "Dr"), "ass": ("as", "i", "As")}
TABS = 3


def page_of(tab: int) -> int:
    """SkillPage (1-3) the game shows on HD tab `tab` (0 = leftmost) and classic tab column entry `tab` (0 = top)."""
    return TABS - tab
GRID_COLS, GRID_ROWS = 3, 6

# The labels of the six trees as the classic art writes them (tab column of skltree_<x>_back.dc6, two per page, the
# first page's first one is the "special" box), words the art cuts short written out. Read by eye from the pictures.
TAB_LABELS = {
    "ama": ["Special", "Defensive", "Blood", "Spear", "Javelin", "Bow"],
    "bar": ["Special", "Rage", "Stances", "Spirits", "Throw", "Melee"],
    "dru": ["Special", "Bow", "Poison", "Elemental", "Charms II", "Charms I"],
    "ass": ["Special", "Ninja", "Bombs", "Throw", "Ki", "Melee"],
    "nec": ["Special", "Summoning", "Suppression", "Battle", "Totems II", "Totems I"],
    "pal": ["Special", "Neutral", "Shadows", "Wicked", "Light", "Honor"],
    "sor": ["Special", "Mana", "Poison", "Lightning", "Cold", "Fire"],
}
LANGS = ["enUS", "zhTW", "deDE", "esES", "frFR", "itIT", "koKR", "plPL", "esMX", "jaJP", "ptBR", "ruRU", "zhCN"]

# ---- HD geometry of D2R's 1162-wide panel (frame origin = panel 132, 160); all D2R's, as measured ----
FW, FH, STRIDE = 895, 1169, 897
LOW_FW, LOW_FH, LOW_STRIDE = 447, 584, 449
SKILL_COL = (253, 515, 775)                       # layout skillColumn / skillRow: left / top of each 130-pixel icon
SKILL_ROW = (296, 478, 654, 834, 1014, 1190)
ORIGIN = (132, 160)
SOCKET_CROP = (106, 124, 328, 272)                # D2R's socket + level box in its frame 1 (cell column 0, row 0)
SOCKET_AT = (-15, -12)                            # where that crop starts, relative to (icon left, icon top) - origin
SOCKET_HALF = (74, 73)                            # half size of the socket square
STRIP_H = 96
ARROW_FILL, ARROW_EDGE = (52, 40, 30), (150, 118, 82)

# ---- the mod's classic page art (skltree_<x>_back.dc6 sets 1-3), classic panel coordinates ----
CLASSIC_COL = (15, 84, 153)                       # D2R's classic layout skillColumn
CLASSIC_ROW = (14, 82, 150, 218, 287, 355)        # its skillRow + 240 (the background's y)
PAGE_W = 228                                      # the page; the tab column (228-320) is not used in HD
K = (SKILL_ROW[4] - SKILL_ROW[0]) / (CLASSIC_ROW[4] - CLASSIC_ROW[0])   # 2.63
LEFT_PART, RIGHT_PART = (0, 90), (124, PAGE_W)    # page x ranges holding column 1 / column 3 (incl. moved level boxes)
LEVEL_BOX = (40, 39, 63, 62)                      # Median's level box (with its bevel), relative to the icon's top left
LEVEL_HD = (163, 105)                             # centre of D2R's level box, relative to the HD icon (frame 1's socket)
CORNER_W = 13                                     # of the old level box: the icon box's corner (mirrored), then stone
MEDIAN_COLUMNS = {0, 2}


# ---- data ---------------------------------------------------------------------------------------------------------
def load_trees(excel: Path = EXCEL) -> dict[str, dict[int, dict[str, tuple[int, int]]]]:
    """class -> page (1-3) -> skill name -> (row, column), both 0-based, for the skills of the seven classic classes.
    Skills without a skilldesc page (0 or empty) are not on a tree."""
    dh, drows = read_tsv(excel / "skilldesc.txt")
    sh, srows = read_tsv(excel / "skills.txt")
    desc = {r[0]: r for r in drows}
    pg, ro, co = col(dh, "SkillPage"), col(dh, "SkillRow"), col(dh, "SkillColumn")
    cc, sd, nm = col(sh, "charclass"), col(sh, "skilldesc"), col(sh, "skill")
    trees: dict = {}
    for r in srows:
        d = desc.get(r[sd])
        if r[cc] in CLASSES and d and d[pg] not in ("", "0"):
            trees.setdefault(r[cc], {}).setdefault(int(d[pg]), {})[r[nm]] = (int(d[ro]) - 1, int(d[co]) - 1)
    return trees


def load_reqs(excel: Path = EXCEL) -> dict[str, list[str]]:
    """skill name -> its non-empty reqskill1 / reqskill2."""
    sh, srows = read_tsv(excel / "skills.txt")
    nm, r1, r2 = col(sh, "skill"), col(sh, "reqskill1"), col(sh, "reqskill2")
    return {r[nm]: [x for x in (r[r1], r[r2]) if x] for r in srows}


def page_arrows(cells: dict[str, tuple[int, int]], reqs: dict[str, list[str]]) -> list[tuple[tuple, tuple]]:
    """(from cell, to cell) arrows of one page (see the module text)."""
    at = set(cells.values())
    out = []
    for name, cell in cells.items():
        wanted = reqs.get(name, [])
        if not wanted:
            continue
        found = [cells[w] for w in wanted if w in cells and cells[w] != cell]
        if not found and (cell[0] - 1, cell[1]) in at:
            found = [(cell[0] - 1, cell[1])]
        out += [(src, cell) for src in found]
    return sorted(set(out))


def tab_titles(cls: str) -> list[str]:
    labels = TAB_LABELS[cls]
    return [f"{labels[2 * n]} / {labels[2 * n + 1]}" for n in range(TABS)]


def title_records() -> list[dict]:
    """d2r: override records for the 21 tab title keys (English text in every language, as the mod's strings)."""
    recs = []
    for cls, (_p, _l, key) in CLASSES.items():
        for n, title in enumerate(tab_titles(cls)):
            recs.append({"Key": f"d2r:SkillCategory{key}{n + 1}", **{lang: title for lang in LANGS}})
    return recs


# ---- drawing ------------------------------------------------------------------------------------------------------
def draw_arrows(arrows, centre, half, shaft: float, head_len: float, head_w: float, size: tuple[int, int],
                scale: int = 2) -> Image.Image:
    """Arrows between cell boxes (centre(cell) -> (x, y), half = box half sizes), anti-aliased by drawing at scale."""
    layer = Image.new("RGBA", (size[0] * scale, size[1] * scale))
    d = ImageDraw.Draw(layer)
    for ca, cb in arrows:
        (ax, ay), (bx, by) = centre(ca), centre(cb)
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        ta = min(half[0] / abs(ux) if ux else 1e9, half[1] / abs(uy) if uy else 1e9)
        sx, sy = ax + ux * ta, ay + uy * ta
        ex, ey = bx - ux * ta, by - uy * ta
        vx, vy = -uy, ux
        bx0, by0 = ex - ux * head_len, ey - uy * head_len
        for pts in ([(sx + vx * shaft / 2, sy + vy * shaft / 2), (bx0 + vx * shaft / 2, by0 + vy * shaft / 2),
                     (bx0 - vx * shaft / 2, by0 - vy * shaft / 2), (sx - vx * shaft / 2, sy - vy * shaft / 2)],
                    [(ex, ey), (bx0 + vx * head_w / 2, by0 + vy * head_w / 2), (bx0 - vx * head_w / 2, by0 - vy * head_w / 2)]):
            d.polygon([(x * scale, y * scale) for x, y in pts], fill=ARROW_FILL + (255,), outline=ARROW_EDGE + (255,),
                      width=max(1, scale))
    return layer.resize(size, Image.LANCZOS)


def cell_centre(c: tuple[int, int]) -> tuple[int, int]:
    return SKILL_COL[c[1]] - ORIGIN[0] - 9 + 74, SKILL_ROW[c[0]] - ORIGIN[1] - 7 + 73


def level_shift() -> tuple[int, int]:
    """Classic pixels Median's level box moves by to sit where D2R draws the level number."""
    cx, cy = (LEVEL_BOX[0] + LEVEL_BOX[2]) / 2, (LEVEL_BOX[1] + LEVEL_BOX[3]) / 2
    return round(LEVEL_HD[0] / K - cx), round(LEVEL_HD[1] / K - cy)


def move_level_boxes(page: Image.Image, cells) -> Image.Image:
    """A copy of a classic page with each cell's level box moved to D2R's place (module text)."""
    out, (dx, dy) = page.copy(), level_shift()
    x0, y0, x1, y1 = LEVEL_BOX
    for r, c in cells:
        x, y = CLASSIC_COL[c], CLASSIC_ROW[r]
        box = page.crop((x + x0, y + y0, x + x1, y + y1))
        mid = x + 24                                                     # the icon's vertical centre line
        corner = page.crop((2 * mid - (x + x0) - CORNER_W + 1, y + y0, 2 * mid - (x + x0) + 1, y + y1))
        out.paste(corner.transpose(Image.FLIP_LEFT_RIGHT), (x + x0, y + y0))  # the icon box's lower-right corner, mirrored
        stone = page.crop((x + x0 + CORNER_W, y + y0 - (y1 - y0) - 11, x + x1, y + y0 - 11))
        out.paste(stone, (x + x0 + CORNER_W, y + y0))                        # right of it: the stone above the old box
        out.paste(box, (x + x0 + dx, y + y0 + dy))
    return out


def median_page(page: Image.Image, cells) -> Image.Image:
    """One HD tree frame (FW x FH, transparent where D2R's stone shows) from a classic 320 x 432 page set."""
    page = move_level_boxes(page.crop((0, 0, PAGE_W, page.height)), cells)
    top = SKILL_ROW[0] - ORIGIN[1] - CLASSIC_ROW[0] * K
    im = Image.new("RGBA", (FW, FH))

    def part(x0: int, x1: int) -> Image.Image:
        return page.crop((x0, 0, x1, page.height)).resize((round((x1 - x0) * K), round(page.height * K)), Image.LANCZOS)

    left_x = SKILL_COL[0] - ORIGIN[0] + (LEFT_PART[0] - CLASSIC_COL[0]) * K
    right_x = SKILL_COL[2] - ORIGIN[0] + (RIGHT_PART[0] - CLASSIC_COL[2]) * K
    left, right, mid = part(*LEFT_PART), part(*RIGHT_PART), part(LEFT_PART[1], RIGHT_PART[0])
    gap = round(right_x) - round(left_x) - left.width                    # column 2's stone, stretched to the HD width
    im.paste(mid.resize((gap + 2, mid.height), Image.LANCZOS), (round(left_x) + left.width - 1, round(top)))
    im.paste(left, (round(left_x), round(top)))
    im.paste(right, (round(right_x), round(top)))
    return im


def median_pages(letter: str, pages: dict, pal) -> list[Image.Image] | None:
    """The 3 HD frames from the mod's skltree_<letter>_back.dc6, None when it is missing or a cell is off columns 1 / 3."""
    path = MOD_UI / "spells" / f"skltree_{letter}_back.dc6"
    if not path.exists() or any(c not in MEDIAN_COLUMNS for cells in pages.values() for _r, c in cells.values()):
        return None
    sets = ui_art.panel_sets(path, pal)
    if len(sets) != TABS + 1:
        return None
    return [median_page(sets[page_of(tab)], pages.get(page_of(tab), {}).values()) for tab in range(TABS)]


def build_class(prefix: str, pages: dict[int, dict[str, tuple[int, int]]], reqs, out_dir: Path,
                median: list[Image.Image] | None = None) -> tuple[int, int]:
    """Writes <prefix>skilltree.sprite (+ .lowend); returns (skills, arrows drawn here). median: the mod's page frames
    (median_pages), else D2R's sockets and drawn arrows."""
    d2r = ui_art.read_sprite(BASE_UI / "spells" / "skill_trees" / f"{prefix}skilltree.sprite")
    if len(d2r) != TABS or d2r[0].size != (FW, FH):
        raise ValueError(f"D2R's {prefix}skilltree.sprite is not {TABS} frames of {FW}x{FH}")
    sockets = d2r[1].crop(SOCKET_CROP)
    frames, n_skills, n_arrows = [], 0, 0
    for tab in range(TABS):
        cells = pages.get(page_of(tab), {})
        n_skills += len(cells)
        if median:
            im = median[tab].copy()
        else:
            im = Image.new("RGBA", (FW, FH))
            arrows = page_arrows(cells, reqs)
            n_arrows += len(arrows)
            im.alpha_composite(draw_arrows(arrows, cell_centre, SOCKET_HALF, 14, 26, 36, (FW, FH)))
            for r, c in cells.values():
                im.alpha_composite(sockets, (SKILL_COL[c] - ORIGIN[0] + SOCKET_AT[0], SKILL_ROW[r] - ORIGIN[1] + SOCKET_AT[1]))
        im.alpha_composite(d2r[tab].crop((0, 0, FW, STRIP_H)), (0, 0))
        frames.append(im)
    ui_art.write_sprite(out_dir / f"{prefix}skilltree.sprite", frames, STRIDE)
    ui_art.write_sprite(out_dir / f"{prefix}skilltree.lowend.sprite",
                        [f.resize((LOW_FW, LOW_FH), Image.LANCZOS) for f in frames], LOW_STRIDE)
    return n_skills, n_arrows


def preview(prefix: str, out: Path, frames: list[Image.Image]) -> None:
    sheet = Image.new("RGBA", (FW * TABS // 2, FH // 2))
    for i, f in enumerate(frames):
        sheet.alpha_composite(f.resize((FW // 2, FH // 2), Image.LANCZOS), (i * FW // 2, 0))
    ui_art.save_png(out / f"skilltree_{prefix}.png", sheet)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path, help="also write a PNG of the 3 frames of each class here")
    args = ap.parse_args(argv)
    trees, reqs = load_trees(), load_reqs()
    pal = ui_art.palette(PAL)
    for cls, (prefix, letter, _key) in CLASSES.items():
        median = median_pages(letter, trees[cls], pal)
        skills, arrows = build_class(prefix, trees[cls], reqs, HD_OUT / "spells" / "skill_trees", median)
        how = f"the mod's page art (skltree_{letter}_back.dc6)" if median else f"D2R's sockets, {arrows} arrows drawn"
        print(f"{prefix}skilltree: {TABS} frames, {skills} skills, {how}")
        if args.preview:
            preview(prefix, args.preview, ui_art.read_sprite(HD_OUT / "spells" / "skill_trees" / f"{prefix}skilltree.sprite"))
    path = STRINGS_OUT / "skill_tab_titles.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(title_records(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{path.relative_to(OUT)}: {len(title_records())} title keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
