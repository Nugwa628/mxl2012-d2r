"""The Warlock's classic (legacy graphics, G) skill tree in Median's look, on the Warlock's own grid (owner choice, lane wltree).

D2R 93847 ships no real classic art for its 8th class: `skltree_w_back.dc6` is a byte copy of vanilla's Necromancer tree
(arrows and cells of the Necromancer's trees, 15 of the Warlock's 30 skills on cells that art leaves empty) and
`waskillicon.dc6` a copy of the Druid's icons. The classic layout also titles the tabs the wrong way round (top tab "Demon"
over the Chaos page: classic tab n shows SkillPage 3 - n, but D2R's `textTab0[7]` is SkillCategoryWa1 = page 1). This step
writes, from Median's own classic art and D2R's HD Warlock icons (nothing of either is in git):

  data/global/ui/spells/skltree_w_back.dc6   4 sets of D2R's 4 classic tiles (ui_art.TILES). Set 0 (always drawn under the
      active tab) = page 1 with no tab lit; set k (1-3) = SkillPage k with its tab (3 - k, top = 0) lit. The page: Median's
      stone and frame (its Necromancer page 1 with the cells taken out, MEDIAN_STONE), Median's skill box with its level box
      (cut from the Necromancer's passive column, MEDIAN_BOX) on every cell that holds a Warlock skill at the layout's
      skillColumn / skillRow, one arrow per prerequisite (reqskill on the same page) in Median's arrow colours. The tab
      column: Median's bare tab column (set 0 of the Necromancer's file), the lit tab brightened as Median's are, each tab
      the page's name (Chaos / Eldritch / Demon, D2R's own SkillCategoryWa3..1) in Median's lettering (letters cut from the
      Sorceress' tab labels, `median_glyphs`) above one of its skill icons in Median's small icon frame.
  data/global/ui/spells/waskillicon.dc6      60 frames of 48 x 48: D2R's HD Warlock icons (`waskillicon.sprite`, frame i =
      IconCel i, odd = pressed) scaled down, toned like Median's icons (white glyph on a dark plate), D2R's units palette
      (indices 1-224).

The classic layout (ui_layouts.skilltree_classic) then draws no Warlock tab title (the art carries it, as for the 7 classes)
and puts the Close button per page where row 6 is free (`cancel_code`). Nothing changes in the tables: SkillRow / SkillColumn
stay D2R's, so HD and the gamepad UI keep D2R's own Warlock trees.

  py -3 -I tools/warlock_tree.py [--preview DIR]      build into ui_paths.OUT_DATA (the hd_ui.py build step), then the check
  py -3 -I tools/warlock_tree.py check                only the check (exit 1 on a problem)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import ui_art  # noqa: E402
from icon_paths import col, read_tsv  # noqa: E402
from rotw_stash_legacy import dc6_bytes, lenient_json, panel_tiles, quantise  # noqa: E402
from ui_paths import BASE_UI, EXCEL, MOD_UI, OUT, OUT_DATA, PAL, ROOT  # noqa: E402

CLASS = "war"
PAGES = (1, 2, 3)
TITLES = {1: "DEMON", 2: "ELDRITCH", 3: "CHAOS"}            # D2R's SkillCategoryWa1..3, in Median's capitals
TAB_SKILL = {1: "Summon Goatman", 2: "Mirrored Blades", 3: "Apocalypse"}  # the icon shown in each page's tab
OUT_BACK = Path("global/ui/spells/skltree_w_back.dc6")
OUT_ICONS = Path("global/ui/spells/waskillicon.dc6")
HD_ICONS = Path("spells/warlock/waskillicon.sprite")       # in the D2R baseline (hd_ui.py baseline)
ICON = 48
PAGE_W = 228                                               # the page; x 228-320 is the tab column
STONE_FROM = ("n", 1)                                      # Median's Necromancer page 1: two plain chains, no tints
BOX_FROM = ("n", 3, 1, 2)                                  # its page 3, row 2, column 3: a passive box (no arrows)
TABCOL_FROM = ("n", 0)                                     # its set 0: the bare tab column
FRAME_FROM = ("s", 3, (268, 160, 309, 201))                # the Sorceress' small icon frame (its MANA entry), 41 x 41
GLYPHS_FROM = "s"                                          # the Sorceress' tab labels: every letter the titles need
LABELS = (("MANA", 178, 1), ("POISON", 232, 1), ("LIGHTN.", 286, 1), ("COLD", 342, 3), ("FIRE", 393, 3))  # word, y, set
LETTER_W = {"M": 7, "I": 2, ".": 2, "A": 6, "N": 6, "D": 6}  # expected widths (others 5) for the letter split
ARROW_FILL, ARROW_EDGE = (30, 30, 30), (168, 166, 160)    # Median's arrows: dark shaft, light rim
ARROW = (7, 9, 17)                                         # shaft width, head length, head width (classic px)
BOX_HALF = 27                                              # arrows start / end this far from a cell's centre
LIT_GAIN = (1.9, 8)                                        # the lit tab's stone: x * gain + offset (Median's lit tabs)
LEVEL_BOX = (44, 43, 58, 58)                               # inside Median's level box, relative to the icon (dark)
BEVEL = (-2, 10, 0, 40)                                    # the box's light left bevel (2 px), relative to the icon
SEED = 2012


# ---- data ----------------------------------------------------------------------------------------------------------
def excel_dir() -> Path:
    """The built tables (the Warlock rows are D2R's, kept by the build): the output's, else work/mod's."""
    for d in (OUT_DATA / "global" / "excel", ROOT / "work" / "mod" / "data" / "global" / "excel"):
        if (d / "skilldesc.txt").exists():
            return d
    return EXCEL


def load(excel: Path | None = None) -> tuple[dict[int, dict[str, tuple[int, int]]], dict[str, list[str]], dict[str, int]]:
    """(page -> skill -> (row, column) 0-based, skill -> same-table reqskills, skill -> IconCel) of the Warlock."""
    excel = Path(excel or excel_dir())
    dh, drows = read_tsv(excel / "skilldesc.txt")
    sh, srows = read_tsv(excel / "skills.txt")
    desc = {r[0]: r for r in drows}
    pg, ro, co, ic = col(dh, "SkillPage"), col(dh, "SkillRow"), col(dh, "SkillColumn"), col(dh, "IconCel")
    cc, sd, nm = col(sh, "charclass"), col(sh, "skilldesc"), col(sh, "skill")
    req = [col(sh, f"reqskill{i}") for i in (1, 2, 3)]
    pages: dict = {p: {} for p in PAGES}
    reqs, icons = {}, {}
    for r in srows:
        d = desc.get(r[sd])
        if r[cc] != CLASS or not d or d[pg] in ("", "0"):
            continue
        pages[int(d[pg])][r[nm]] = (int(d[ro]) - 1, int(d[co]) - 1)
        reqs[r[nm]] = [r[i] for i in req if i is not None and r[i]]
        icons[r[nm]] = int(d[ic])
    return pages, reqs, icons


def links(cells: dict[str, tuple[int, int]], reqs: dict[str, list[str]]) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """(required cell, skill cell) for every reqskill on the same page."""
    return sorted({(cells[q], cells[n]) for n in cells for q in reqs.get(n, []) if q in cells and cells[q] != cells[n]})


def layout() -> dict:
    return lenient_json((BASE_UI / "layouts" / "skillstreepanel.json").read_text("utf-8-sig"))


def geometry(lay: dict | None = None) -> tuple[list[int], list[int], list[tuple[int, int]]]:
    """(cell x per column, cell y per row, tab y ranges top to bottom) in the 320 x 432 panel, from D2R's classic layout."""
    lay = lay or layout()
    f = lay["fields"]
    bg = next(c for c in lay["children"] if c["name"] == "Background")["fields"]["rect"]
    oy = -bg.get("y", 0)
    tabs = []
    for n in range(3):
        r = next(c for c in lay["children"] if c["name"] == f"Tab{n}")["fields"]["activationRect"]
        tabs.append((r["y"] + oy, r["y"] + oy + r["height"]))
    return [x - bg.get("x", 0) for x in f["skillColumn"]], [y + oy for y in f["skillRow"]], tabs


def cancel_code(pages: dict[int, dict[str, tuple[int, int]]], lay: dict | None = None) -> int:
    """The Warlock's `cancelPositionCode`: digit k (k = 1..3, left to right) = SkillPage k's Close button, the first of
    `cancelPositionX` (1-based) whose 32-px button keeps clear of that page's row-6 skills. D2R's 7 codes (321, 113, ...)
    read the same way: each digit of theirs is a free place on that page's row 6 (checked on D2R's tables, lane wltree)."""
    lay = lay or layout()
    xs, cols = lay["fields"]["cancelPositionX"], geometry(lay)[0]
    digits = []
    for p in PAGES:
        used = [c for r, c in pages[p].values() if r == 5]
        free = [i for i, x in enumerate(xs) if all(not (x < cols[c] + ICON and cols[c] < x + 32) for c in used)]
        if not free:
            raise ValueError(f"Warlock page {p}: no free place for the Close button on row 6")
        digits.append(free[0] + 1)
    return int("".join(map(str, digits)))


# ---- pieces of Median's art -------------------------------------------------------------------------------------------
def sets(letter: str, pal) -> list[Image.Image]:
    return ui_art.panel_sets(MOD_UI / "spells" / f"skltree_{letter}_back.dc6", pal)


def fill_masked(im: Image.Image, mask: np.ndarray, region: tuple[int, int, int, int], seed: int = SEED) -> Image.Image:
    """`mask` (True = replace) filled with overlapping 24-px stone patches (raised-cosine weights) picked at random from the
    unmasked stone of `region`, blended in over a 1.2-px soft edge. Deterministic for a seed."""
    rng = np.random.default_rng(seed)
    a = np.asarray(im, np.float64).copy()
    x0, y0, x1, y1 = region
    P, S = 24, 12
    win = np.outer(np.hanning(P + 2)[1:-1], np.hanning(P + 2)[1:-1])[..., None]
    acc, wsum = np.zeros(a.shape[:2] + (3,)), np.zeros(a.shape[:2] + (1,))
    free = [(sx, sy) for sy in range(y0, y1 - P, 3) for sx in range(x0, x1 - P, 3) if not mask[sy:sy + P, sx:sx + P].any()]
    if not free:
        raise ValueError("no clean stone to fill from")
    for by in range(y0, y1 - P + S, S):
        for bx in range(x0, x1 - P + S, S):
            if not mask[by:by + P, bx:bx + P].any():
                continue
            sx, sy = free[rng.integers(len(free))]
            hh, ww = min(P, a.shape[0] - by), min(P, a.shape[1] - bx)
            acc[by:by + hh, bx:bx + ww] += a[sy:sy + hh, sx:sx + ww, :3] * win[:hh, :ww]
            wsum[by:by + hh, bx:bx + ww] += win[:hh, :ww]
    fill = np.where(wsum > 1e-3, acc / np.maximum(wsum, 1e-3), a[..., :3])
    soft = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float64)[..., None] / 255
    a[..., :3] = soft * fill + (1 - soft) * a[..., :3]
    return Image.fromarray(np.clip(np.rint(a), 0, 255).astype(np.uint8), "RGBA")


def stone_page(page: Image.Image, cols: list[int], rows: list[int]) -> Image.Image:
    """A Median page with its cells (columns 1 and 3, rows 1-5: box, level box, arrow) taken out."""
    m = np.zeros((page.height, page.width), bool)
    for r in range(5):
        for c in (0, 2):
            m[rows[r] - 9:rows[r] + 70, cols[c] - 10:cols[c] + 68] = True
    m[:, PAGE_W - 6:] = False
    m[:8, :] = False
    return fill_masked(page, m, (9, 9, PAGE_W - 9, page.height - 9))


def box_piece(page: Image.Image, x: int, y: int) -> Image.Image:
    """Median's skill box at icon (x, y): its bevel outline and level box (alpha = structure only), the icon square opaque."""
    crop = page.crop((x - 8, y - 8, x + 67, y + 67))
    L = np.asarray(crop.convert("RGB"), np.float64).mean(-1)
    yy, xx = np.mgrid[0:crop.height, 0:crop.width]
    rx, ry = xx - 8, yy - 8
    ring = (rx >= -8) & (rx <= 52) & (ry >= -8) & (ry <= 52) & ~((rx >= 1) & (rx <= 46) & (ry >= 1) & (ry <= 46))
    level = (rx >= 37) & (ry >= 36)
    inner = (rx >= -1) & (rx <= ICON) & (ry >= -1) & (ry <= ICON)
    keep = ((ring | level) & ((L > 128) | (L < 52))) | inner
    a = np.asarray(crop).copy()
    a[..., 3] = np.where(keep, 255, 0)
    return Image.fromarray(a, "RGBA")


def arrows_layer(arrows, cols, rows, size=(ui_art.PANEL_W, ui_art.PANEL_H)) -> Image.Image:
    import skill_tree_art as sta
    old = sta.ARROW_FILL, sta.ARROW_EDGE
    sta.ARROW_FILL, sta.ARROW_EDGE = ARROW_FILL, ARROW_EDGE
    try:
        return sta.draw_arrows(arrows, lambda c: (cols[c[1]] + ICON // 2, rows[c[0]] + ICON // 2), (BOX_HALF, BOX_HALF),
                               *ARROW, size, scale=4)
    finally:
        sta.ARROW_FILL, sta.ARROW_EDGE = old


def split_letters(ink: list[float], word: str, wmin: int = 2, wmax: int = 8) -> list[tuple[int, int]]:
    """Touching letters of one label: the n - 1 cut columns with the least ink, each letter's width near LETTER_W
    (dynamic programming). Returns (start, end) column spans."""
    n, L, INF = len(word), len(ink), float("inf")

    def pen(w: int, ch: str) -> float:
        return 40.0 * (w - LETTER_W.get(ch, 5)) ** 2

    best = [[INF] * (L + 1) for _ in range(n + 1)]
    back = [[-1] * (L + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for k in range(1, n + 1):
        for j in range(1, L + 1):
            for w in range(wmin, wmax + 1):
                s = j - w
                if k == 1:
                    if s != 0:
                        continue
                    cost = pen(w, word[0])
                else:
                    if s < 2 or best[k - 1][s - 1] == INF:
                        continue
                    cost = best[k - 1][s - 1] + ink[s - 1] + pen(w, word[k - 1])
                if cost < best[k][j]:
                    best[k][j], back[k][j] = cost, s
    if best[n][L] == INF:
        raise ValueError(f"cannot split {word!r} into {n} letters")
    spans, j = [], L
    for k in range(n, 0, -1):
        s = back[k][j]
        spans.append((s, j))
        j = s - 1
    return spans[::-1]


def median_glyphs(src_sets: list[Image.Image]) -> dict[str, np.ndarray]:
    """letter -> alpha (0-1) of Median's tab lettering, cut from the labels in LABELS (unlit tabs: dark behind)."""
    out: dict[str, np.ndarray] = {}
    for word, y, s in LABELS:
        lum = np.asarray(src_sets[s].convert("RGB"), np.float64)[y - 8:y + 8, 231:268].mean(-1)
        on = lum > 170
        rows, cols_ = np.nonzero(on.any(1))[0], np.nonzero(on.any(0))[0]
        box = lum[rows.min():rows.max() + 1, cols_.min():cols_.max() + 1]
        for ch, (a, b) in zip(word, split_letters(list(np.clip(box - 90, 0, None).sum(0)), word)):
            if ch.isalpha() and ch not in out:
                out[ch] = np.clip((box[:, a:b] - 45) / 190, 0, 1)
    return out


def lettering(glyphs: dict[str, np.ndarray], text: str, colour=(236, 232, 220)) -> Image.Image:
    missing = sorted(set(text) - set(glyphs))
    if missing:
        raise ValueError(f"no Median letter for {missing}")
    h = max(glyphs[c].shape[0] for c in text)
    w = sum(glyphs[c].shape[1] for c in text) + len(text) - 1
    alpha = np.zeros((h, w))
    x = 0
    for c in text:
        g = glyphs[c]
        alpha[h - g.shape[0]:, x:x + g.shape[1]] = g
        x += g.shape[1] + 1
    rgba = np.dstack([np.full((h, w), v, np.float64) for v in colour] + [alpha * 255])
    return Image.fromarray(np.rint(rgba).astype(np.uint8), "RGBA")


def icon48(hd: Image.Image) -> Image.Image:
    """An HD icon at classic size, toned like Median's icons (white glyph, near-black plate)."""
    im = hd.convert("RGBa").resize((ICON, ICON), Image.LANCZOS).convert("RGBA")
    a = np.asarray(im, np.float64)
    v = np.maximum(np.clip((a[..., :3].mean(-1) - 95) * 2.2, 0, 255), 18)
    return Image.fromarray(np.rint(np.dstack([v, v, v, a[..., 3]])).astype(np.uint8), "RGBA")


# ---- the pictures ----------------------------------------------------------------------------------------------------
def tab_column(base: Image.Image, lit: int | None, tabs, frame: Image.Image, glyphs, pages_icons: dict[int, Image.Image]) -> Image.Image:
    """Median's bare tab column with tab `lit` (0 = top, None = none) brightened, each tab its page's title above its icon."""
    a = np.asarray(base, np.float64).copy()
    if lit is not None:
        y0, y1 = tabs[lit]
        a[y0 + 2:y1 - 2, 231:316, :3] = np.clip(a[y0 + 2:y1 - 2, 231:316, :3] * LIT_GAIN[0] + LIT_GAIN[1], 0, 255)
    im = Image.fromarray(np.rint(a).astype(np.uint8), "RGBA")
    for t, (y0, y1) in enumerate(tabs):
        page = 3 - t
        cy = (y0 + y1) // 2 + 10
        im.alpha_composite(frame, (253, cy - 20))
        im.alpha_composite(pages_icons[page].resize((31, 31), Image.LANCZOS), (258, cy - 15))
        lab = lettering(glyphs, TITLES[page])
        im.alpha_composite(lab, (274 - lab.width // 2, cy - 33))
    return im


def page_picture(stone: Image.Image, box: Image.Image, cells, arrows, cols, rows) -> Image.Image:
    im = stone.copy()
    im.alpha_composite(arrows_layer(arrows, cols, rows))
    for r, c in cells:
        im.alpha_composite(box, (cols[c] - 8, rows[r] - 8))
    return im


def pictures(pal) -> tuple[list[Image.Image], list[Image.Image], dict]:
    """(the 4 panel sets, the 60 icons, report) of the Warlock's classic tree."""
    pages, reqs, iconcel = load()
    lay = layout()
    cols, rows, tabs = geometry(lay)
    nsets = sets(STONE_FROM[0], pal)
    stone = stone_page(nsets[STONE_FROM[1]], cols, rows)
    box = box_piece(sets(BOX_FROM[0], pal)[BOX_FROM[1]], cols[BOX_FROM[3]], rows[BOX_FROM[2]])
    ssets = sets(FRAME_FROM[0], pal)
    frame = ssets[FRAME_FROM[1]].crop(FRAME_FROM[2])
    glyphs = median_glyphs(sets(GLYPHS_FROM, pal))
    hd = ui_art.read_sprite(BASE_UI / HD_ICONS)
    icons = [icon48(f) for f in hd]
    tab_icons = {p: icons[iconcel[TAB_SKILL[p]]] for p in PAGES}
    out = []
    for s in range(4):
        page = s or 1
        cells = pages[page]
        im = tab_column(nsets[TABCOL_FROM[1]] if TABCOL_FROM[0] == STONE_FROM[0] else sets(TABCOL_FROM[0], pal)[TABCOL_FROM[1]],
                        None if s == 0 else 3 - page, tabs, frame, glyphs, tab_icons)
        pg = page_picture(stone, box, cells.values(), links(cells, reqs), cols, rows)
        im.paste(pg.crop((0, 0, PAGE_W, pg.height)), (0, 0))
        out.append(im)
    report = {"skills": sum(len(v) for v in pages.values()), "arrows": sum(len(links(pages[p], reqs)) for p in PAGES),
              "icons": len(icons), "cancel_code": cancel_code(pages, lay)}
    return out, icons, report


def build(out_data: Path = OUT_DATA, preview: Path | None = None) -> list[str]:
    pal = ui_art.palette(PAL)
    panel, icons, rep = pictures(pal)
    idx = [quantise(im, pal, dither=False) for im in panel]
    back = out_data / OUT_BACK
    back.parent.mkdir(parents=True, exist_ok=True)
    back.write_bytes(dc6_bytes([t for i in idx for t in panel_tiles(i)]))
    (out_data / OUT_ICONS).write_bytes(dc6_bytes([quantise(i, pal, dither=False) for i in icons]))
    if preview:
        sh = Image.new("RGBA", (4 * 330, 432), (20, 20, 20, 255))
        for k, im in enumerate(ui_art.panel_sets(back, pal)):
            sh.alpha_composite(im, (k * 330, 0))
        ui_art.save_png(Path(preview) / "warlock_classic_tree.png", sh)
    return [f"{OUT_BACK.as_posix()}: 4 sets ({rep['skills']} skills, {rep['arrows']} arrows), "
            f"{OUT_ICONS.as_posix()}: {rep['icons']} icons, Close button code {rep['cancel_code']}"]


# ---- the check --------------------------------------------------------------------------------------------------------
def cell_has_box(page: Image.Image, x: int, y: int) -> bool:
    """Median's box at icon (x, y): a dark level box and the light bevel left of the icon."""
    L = np.asarray(page.convert("RGB"), np.float64).mean(-1)
    lx0, ly0, lx1, ly1 = LEVEL_BOX
    bx0, by0, bx1, by1 = BEVEL
    return L[y + ly0:y + ly1, x + lx0:x + lx1].mean() < 50 and L[y + by0:y + by1, x + bx0:x + bx1].mean() > 120


def arrow_seen(page: Image.Image, a, b, cols, rows) -> bool:
    """The arrow from cell a to cell b: dark shaft pixels at the midpoint of the gap between their boxes."""
    (ra, ca), (rb, cb) = a, b
    ax, ay = cols[ca] + ICON // 2, rows[ra] + ICON // 2
    bx, by = cols[cb] + ICON // 2, rows[rb] + ICON // 2
    L = np.asarray(page.convert("RGB"), np.float64).mean(-1)
    d = max(abs(bx - ax), abs(by - ay))
    t = 0.5 if d < 120 else (BOX_HALF + 20) / d   # long arrows: a point just past the first box
    mx, my = round(ax + (bx - ax) * t), round(ay + (by - ay) * t)
    return L[my - 1:my + 2, mx - 1:mx + 2].min() < 60


def check(out_data: Path = OUT_DATA) -> list[str]:
    """Problems of the built files: every Warlock skill's button rect (layout skillColumn / skillRow, 48 x 48) on a
    Median box, no box without a skill, every prerequisite arrow present, every arrow a real reqskill, the icon sheet
    covering every IconCel + 1, the tab title order."""
    problems = []
    back, icons_path = out_data / OUT_BACK, out_data / OUT_ICONS
    if not back.exists() or not icons_path.exists():
        return [f"missing {p}" for p in (back, icons_path) if not p.exists()]
    pal = ui_art.palette(PAL)
    pages, reqs, iconcel = load()
    cols, rows, _tabs = geometry()
    panel = ui_art.panel_sets(back, pal)
    if len(panel) != 4:
        problems.append(f"{OUT_BACK}: {len(panel)} sets, 4 expected")
    for p in PAGES:
        if p >= len(panel):
            continue
        im, cells = panel[p], set(pages[p].values())
        for r in range(len(rows)):
            for c in range(len(cols)):
                boxed = cell_has_box(im, cols[c], rows[r])
                if (r, c) in cells and not boxed:
                    problems.append(f"page {p}: skill at row {r + 1} column {c + 1} has no box under its button")
                if (r, c) not in cells and boxed:
                    problems.append(f"page {p}: empty box at row {r + 1} column {c + 1}")
        for a, b in links(pages[p], reqs):
            if not arrow_seen(im, a, b, cols, rows):
                problems.append(f"page {p}: no arrow from {a} to {b}")
        req_pairs = {(pages[p][q], pages[p][n]) for n in pages[p] for q in reqs.get(n, []) if q in pages[p]}
        problems += [f"page {p}: arrow {ab} is no prerequisite" for ab in links(pages[p], reqs) if ab not in req_pairs]
    n_icons = len(ui_art.dc6.read_dc6(icons_path))
    for name, cel in iconcel.items():
        if cel + 1 >= n_icons:
            problems.append(f"{name}: IconCel {cel} + 1 outside the {n_icons}-frame icon sheet")
    served = out_data / "global" / "ui" / "layouts" / "skillstreepanel.json"
    if served.exists():  # the classic layout ui_layouts writes: no Warlock title text over the art, its Close button code
        f = lenient_json(served.read_text("utf-8-sig"))["fields"]
        for n in range(3):
            if len(f[f"textTab{n}"]) < 8 or f[f"textTab{n}"][7] != "":
                problems.append(f"skillstreepanel.json textTab{n}: the Warlock's entry is not empty")
        code = f["cancelPositionCode"]
        if len(code) < 8 or code[7] != cancel_code(pages):
            problems.append(f"skillstreepanel.json cancelPositionCode: Warlock {code[7:] or 'missing'}, {cancel_code(pages)} expected")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="?", default="build", choices=("build", "check"))
    ap.add_argument("--preview", type=Path)
    args = ap.parse_args(argv)
    if args.what == "build":
        for line in build(preview=args.preview):
            print(line)
    problems = check()
    for p in problems:
        print(f"PROBLEM: {p}")
    print(f"warlock classic tree: {'OK' if not problems else f'{len(problems)} problem(s)'} ({OUT})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
