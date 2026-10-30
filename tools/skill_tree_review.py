"""Review sheets of the HD skill tree page candidates (lane skillhd, skill_tree_hd.py; owner review before anything ships).

Per class one sheet: a row per tab (tab 0 = leftmost = SkillPage 3), columns legacy (Median's classic page, the set the
classic UI draws, scaled to the HD height pixel for pixel), HD now (`lanczos`, shipped) and each candidate method, every HD
frame over D2R's panel_skilltreebg as the game draws it (frame at 64, 15 of the background), at half size. Plus per class a
1:1 detail sheet (the upper left of tab 2 = SkillPage 1: two cells, an arrow, a level box) and an overview of all classes'
SkillPage 1 per method.

  py -3 -I tools/skill_tree_review.py OUT_DIR [--methods lanczos,rebuild,...] [--classes ama,sor]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageDraw  # noqa: E402

import skill_tree_art as sta  # noqa: E402
import skill_tree_hd  # noqa: E402
import ui_art  # noqa: E402
from ui_paths import BASE_UI, MOD_UI, PAL  # noqa: E402

LABEL_H = 28
GAP = 8
BG = (24, 20, 18)
DETAIL = (40, 100, 520, 520)   # tree frame px of the 1:1 detail (column 1, rows 1-2, its level boxes)
NAMES = {"lanczos": "HD now (shipped)", "rebuild": "A rebuild", "rebuild-stone": "B rebuild + D2R stone",
         "d2r": "C D2R panel + Median layout"}


def on_bg(frame: Image.Image, bg: Image.Image) -> Image.Image:
    """The frame over D2R's tree background, cropped to the frame."""
    c = bg.copy()
    c.alpha_composite(frame, skill_tree_hd.BG_AT)
    x, y = skill_tree_hd.BG_AT
    return c.crop((x, y, x + sta.FW, y + sta.FH))


def legacy(page: Image.Image) -> Image.Image:
    """Median's classic page as the classic UI draws it (with its tab column), nearest-scaled to the HD frame height."""
    k = sta.FH / page.height
    return page.resize((round(page.width * k), sta.FH), Image.NEAREST)


def labelled(im: Image.Image, text: str) -> Image.Image:
    out = Image.new("RGB", (im.width, im.height + LABEL_H), BG)
    out.paste(im.convert("RGB"), (0, LABEL_H))
    ImageDraw.Draw(out).text((6, 6), text, fill=(230, 220, 200))
    return out


def row(images: list[Image.Image]) -> Image.Image:
    out = Image.new("RGB", (sum(i.width for i in images) + GAP * (len(images) - 1), max(i.height for i in images)), BG)
    x = 0
    for i in images:
        out.paste(i, (x, 0))
        x += i.width + GAP
    return out


def column(images: list[Image.Image]) -> Image.Image:
    out = Image.new("RGB", (max(i.width for i in images), sum(i.height for i in images) + GAP * (len(images) - 1)), BG)
    y = 0
    for i in images:
        out.paste(i, (0, y))
        y += i.height + GAP
    return out


def half(im: Image.Image) -> Image.Image:
    return im.resize((im.width // 2, im.height // 2), Image.LANCZOS)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--methods", default=",".join(skill_tree_hd.METHODS))
    ap.add_argument("--classes", default=",".join(sta.CLASSES))
    args = ap.parse_args(argv)
    methods = [m for m in args.methods.split(",") if m]
    args.out.mkdir(parents=True, exist_ok=True)
    trees, reqs = sta.load_trees(), sta.load_reqs()
    pal = ui_art.palette(PAL)
    bg = ui_art.read_sprite(BASE_UI / "spells" / "skill_trees" / "panel_skilltreebg.sprite")[0]
    art = ui_art.read_sprite(BASE_UI / "spells" / "skill_trees" / f"{skill_tree_hd.D2R_ART[0]}skilltree.sprite")
    overview: dict[str, list[Image.Image]] = {m: [] for m in ["legacy"] + methods}
    for cls in args.classes.split(","):
        prefix, letter, _key = sta.CLASSES[cls]
        sets = ui_art.panel_sets(MOD_UI / "spells" / f"skltree_{letter}_back.dc6", pal)
        frames = {m: sta.median_pages(letter, trees[cls], pal, m, art[skill_tree_hd.D2R_ART[1]], bg, reqs) for m in methods}
        strip = ui_art.read_sprite(BASE_UI / "spells" / "skill_trees" / f"{prefix}skilltree.sprite")
        rows, details = [], []
        for tab in range(sta.TABS):
            page = sta.page_of(tab)
            cells = [legacy(sets[page])]
            hd = {}
            for m in methods:
                f = frames[m][tab].copy()
                f.alpha_composite(strip[tab].crop((0, 0, sta.FW, sta.STRIP_H)), (0, 0))
                hd[m] = on_bg(f, bg)
                cells.append(hd[m])
            names = ["legacy (classic page, x%.2f nearest)" % (sta.FH / sets[page].height)] + [NAMES.get(m, m) for m in methods]
            rows.append(labelled(row([half(labelled(c, n)) for c, n in zip(cells, names)]),
                                 f"{cls} tab {tab} = SkillPage {page}: {sta.tab_titles(cls)[page - 1]}"))
            if page == 1:
                k = sta.K
                left_x = sta.SKILL_COL[0] - sta.ORIGIN[0] + (sta.LEFT_PART[0] - sta.CLASSIC_COL[0]) * k
                x0 = max(0, round((DETAIL[0] - left_x) / k))
                y0 = round((DETAIL[1] - (sta.SKILL_ROW[0] - sta.ORIGIN[1] - sta.CLASSIC_ROW[0] * k)) / k)
                w, h = round((DETAIL[2] - DETAIL[0]) / k), round((DETAIL[3] - DETAIL[1]) / k)
                lg = sets[page].crop((x0, y0, x0 + w, y0 + h)).resize((DETAIL[2] - DETAIL[0], DETAIL[3] - DETAIL[1]),
                                                                     Image.NEAREST)
                details = [labelled(lg, "legacy x2.63 nearest (its level boxes not moved)")] + [labelled(hd[m].crop(DETAIL), NAMES.get(m, m)) for m in methods]
                overview["legacy"].append(half(legacy(sets[page])))
                for m in methods:
                    overview[m].append(half(hd[m]))
        column(rows).save(args.out / f"sheet_{cls}.png")
        labelled(row(details), f"{cls} SkillPage 1, 1:1 HD pixels (upper left)").save(args.out / f"detail_{cls}.png")
        print(f"{cls}: sheet_{cls}.png, detail_{cls}.png")
    for m, ims in overview.items():
        if ims:
            labelled(row(ims), f"SkillPage 1 of every class: {NAMES.get(m, m)}").save(args.out / f"overview_{m}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
