"""Skill icons: the mod's icon sheets as D2R HD skill icon sprites (adapted from another port's skill_icons.py).

Median XL 2012 v005 is a data mod on 1.13c, so it does what 1.13c does: skills.txt `charclass` picks the sheet
(ama/sor/nec/pal/bar/dru/ass -> Spells\\<xx>skillicon.dc6, everything else -> Spells\\skillicon.dc6) and skilldesc.txt
`IconCel` is a frame of that sheet; the button shows IconCel, pressed it shows IconCel + 1. D2R reads the same fields the
same way (Spells/<Class>/<Xx>Skillicon, Spells/SubMenu/Skillicon), so unlike another Median XL release (which drew icons from
D2Sigma sheets with its own frame numbers) nothing is renumbered: every frame of a sheet becomes the same frame of the
sprite, skilldesc.txt is left as the mod has it, and IconCel keeps meaning what the mod's author wrote - including the odd
cels (a pressed frame named as the icon) and a shared sheet that is not strictly pairs (never rounded to pairs).

D2R's HD sprites are one horizontal strip under the 16384-pixel texture limit and are drawn at their own pixel size (no
scaling to the slot), so icons are D2R's 130 pixels (stride 132); a sheet of more than 124 frames would get a smaller
stride (the mod's biggest sheet has 118 frames, so none does). The 48 x 48 classic frames are scaled up bilinearly
(premultiplied alpha). The `.lowend` sprite is half size, as D2R's (65 pixels, stride 67).

The shared sheet is the exception: when tools/shared_icons.py has rewritten the built tables (work/mod/shared_icons.json),
its frames are that plan's pairs (every icon twice, so IconCel + 1, the pressed button, is the same icon; class sheet
frames for the class-less copies of class rows; D2R's own HD frame for a vanilla row such as Fire Wall).

Skills are tiered for the report only: TREE (class skill on a skill tree page), START (the
basic skills and the character start grants), BAR (skills items put on the skill bar: charges, oskills), ITEM (skills
the item tables name otherwise, e.g. procs), MONSTER (the rest: monster skills and vanilla leftovers).

Writes work/hd/data/hd/global/ui/spells/<class>/<xx>skillicon.sprite (+ .lowend.sprite) and work/hd/skill_sheets.json.
Usage: py -3 -I tools/skill_icons.py [--preview DIR]   (--preview also writes a PNG strip per sheet)
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dc6 import MAX_STRIP, decode_frame, palette, read_dc6, read_sprite, scale, strip, write_png, write_sheet_sprite  # noqa: E402
from icon_paths import BASE, EXCEL, HD_OUT, MOD, OUT, col, read_tsv  # noqa: E402
import fxpaths  # noqa: E402
import shared_icons  # noqa: E402
from dc6 import scale as scale_painted  # noqa: E402  (bilinear, for D2R's painted HD frames)
from upscale import scale_rows as scale  # noqa: E402,F811  (hybrid pixel-art upscale, not dc6's bilinear)

SPELLS = MOD / "ui" / "spells"
D2R_STRIDE = 132
# charclass -> (mod sheet, D2R HD file under data/hd/global/ui/spells/)
TARGETS = {
    "ama": ("amskillicon", "amazon/amskillicon"),
    "sor": ("soskillicon", "sorceress/soskillicon"),
    "nec": ("neskillicon", "necromancer/neskillicon"),
    "pal": ("paskillicon", "paladin/paskillicon"),
    "bar": ("baskillicon", "barbarian/baskillicon"),
    "dru": ("drskillicon", "druid/drskillicon"),
    "ass": ("asskillicon", "assassin/asskillicon"),
    "": ("skillicon", "submenu/skillicon"),
}
TREE, START, BAR, ITEM, MONSTER = range(5)
TIER_NAMES = ["tree", "start", "bar", "item", "monster"]
# Item stats that put a skill on the skill bar (charges, oskills); their property parameter is the skill's name or id
BAR_STATS = {"item_charged_skill", "item_nonclassskill", "item_singleskill"}
ITEM_TABLES = ("uniqueitems", "setitems", "sets", "runes", "magicprefix", "magicsuffix", "automagic", "cubemain",
               "gems", "qualityitems")


def sheet_of(charclass: str) -> str:
    return charclass if charclass in TARGETS else ""


def strip_geometry(frames: int) -> tuple[int, int]:
    """(stride, icon size) of an HD sheet with that many frames."""
    stride = min(D2R_STRIDE, MAX_STRIP // max(frames, 1))
    return stride, stride - 2


def lowend_geometry(frames: int) -> tuple[int, int]:
    """(stride, icon size) of the `.lowend` sheet: half the icon, 2 pixels apart (D2R's 65 / 67)."""
    size = strip_geometry(frames)[1] // 2
    return size + 2, size


def shared_frames(plan, pal: list, size: int, low: int, spells: Path = SPELLS, d2r: Path | None = None) -> tuple[list, list]:
    """(HD frames, lowend frames) of the paired shared sheet: Median's DC6 frames scaled, D2R's frames taken from D2R's own
    HD sprites (its 130-pixel art, the lowend from its .lowend sprite)."""
    d2r = d2r or fxpaths.D2R
    hd, lo, cache = [], [], {}
    for icon, path in shared_icons.frame_sources(plan, spells, d2r):
        if icon.origin == "mxl":
            w, h, _x, _y, blk = read_dc6(path)[icon.cel]
            rows = decode_frame(w, h, blk, pal, fill=True)
            a, b = scale(rows, size, size, size / max(w, h)), scale(rows, low, low, low / max(w, h))
        else:
            base = d2r / "data" / "hd" / "global" / "ui" / "spells" / shared_icons.SHEETS[icon.sheet][1]
            got = []
            for suffix, want in ((".sprite", size), (".lowend.sprite", low)):
                path_s = base.with_name(base.name + suffix)
                if path_s not in cache:
                    cache[path_s] = read_sprite(path_s)
                got.append(_fit(cache[path_s][icon.cel], want))
            a, b = got
        hd += [a, a]
        lo += [b, b]
    return hd, lo


def _fit(rows: list, size: int) -> list:
    """A D2R frame on a size x size canvas (scaled when D2R's is another size)."""
    if len(rows) == size and len(rows[0]) == size:
        return rows
    return scale_painted(rows, size, size, size / max(len(rows), len(rows[0])))


def item_skills(excel: Path, name_of_id: dict[str, str]) -> Counter:
    """Skills items put on the skill bar -> how many item rows do (the parameter is a name or an id)."""
    ph, prows = read_tsv(excel / "properties.txt")
    stats = [i for i, c in enumerate(ph) if c.lower().startswith("stat")]
    props = {r[0] for r in prows if BAR_STATS & {r[i] for i in stats}}
    out = Counter()
    for t in ITEM_TABLES:
        if not (excel / f"{t}.txt").exists():
            continue
        h, rows = read_tsv(excel / f"{t}.txt")
        pairs = []  # (property column, its parameter column): prop1/par1, mod1code/mod1param, T1Code1/T1Param1, mod 1/mod 1 param
        for i, c in enumerate(h):
            for a, b in (("prop", "par"), ("Code", "Param"), ("code", "param")):
                if a in c and c.replace(a, b, 1) in h:
                    pairs.append((i, h.index(c.replace(a, b, 1))))
            if c.startswith("mod ") and c[4:].isdigit() and f"{c} param" in h:
                pairs.append((i, h.index(f"{c} param")))
        out.update(name_of_id.get(r[j], r[j]) for r in rows for i, j in pairs if r[i] in props and r[j])
    return out


def load_skills(excel: Path = EXCEL) -> list[dict]:
    """Every skills.txt row that names a skilldesc: its sheet, IconCel (None when the row or cell is missing) and tier."""
    sh, srows = read_tsv(excel / "skills.txt")
    dh, drows = read_tsv(excel / "skilldesc.txt")
    c_name, c_id, c_cls, c_desc = 0, col(sh, "Id"), col(sh, "charclass"), col(sh, "skilldesc")
    d_cel, d_page = col(dh, "IconCel"), col(dh, "SkillPage")
    desc = {r[0]: r for r in drows}
    start = set()
    if (excel / "charstats.txt").exists():
        start = {c for r in read_tsv(excel / "charstats.txt")[1] for c in r if c}
    named = set()
    for t in ("weapons", "armor", "misc") + ITEM_TABLES:
        if (excel / f"{t}.txt").exists():
            named |= {c for r in read_tsv(excel / f"{t}.txt")[1] for c in r if c}
    bar = Counter()
    if (excel / "properties.txt").exists():
        bar = item_skills(excel, {r[c_id]: r[c_name] for r in srows if c_id is not None and r[c_id]})
    out = []
    for i, r in enumerate(srows):
        if not r[c_name] or not r[c_desc]:
            continue
        cls = sheet_of(r[c_cls])
        d = desc.get(r[c_desc])
        cel = None
        page = ""
        if d is not None:
            page = d[d_page]
            cel = int(d[d_cel]) if d[d_cel].lstrip("-").isdigit() else None
        if cls and page not in ("", "0"):
            tier = TREE
        elif i < 6 or r[c_name] in start:
            tier = START
        else:
            tier = BAR if r[c_name] in bar else ITEM if r[c_name] in named else MONSTER
        out.append({"name": r[c_name], "id": r[c_id] if c_id is not None else str(i), "sheet": cls,
                    "desc": r[c_desc], "has_desc": d is not None, "cel": cel, "tier": tier})
    return out


def convert(pal: list, preview: Path | None = None, spells: Path = SPELLS, hd: Path = HD_OUT, plan=None,
            d2r: Path | None = None) -> dict:
    """Writes the HD sprite of every sheet (the shared one from `plan` when given); returns {sheet: {...}} for
    skill_sheets.json."""
    report = {}
    for cls, (sheet, target) in TARGETS.items():
        src = read_dc6(spells / f"{sheet}.dc6")
        n = 2 * len(plan.icons) if cls == "" and plan else len(src)
        stride, size = strip_geometry(n)
        low_stride, low = lowend_geometry(n)
        if cls == "" and plan:
            images, lows = shared_frames(plan, pal, size, low, spells, d2r)
        else:
            rows = [decode_frame(w, h, blk, pal, fill=True) for w, h, _x, _y, blk in src]
            images = [scale(r, size, size, size / max(len(r[0]), len(r))) for r in rows]
            lows = [scale(r, low, low, low / max(len(r[0]), len(r))) for r in rows]
        base = hd / "global" / "ui" / "spells" / target
        write_sheet_sprite(base.with_name(base.name + ".sprite"), images, stride, size)
        write_sheet_sprite(base.with_name(base.name + ".lowend.sprite"), lows, low_stride, low)
        if preview:
            write_png(preview / f"{sheet}.png", stride * len(images), size, strip(images, stride, size))
        report[cls] = {"dc6": f"{sheet}.dc6", "sprite": f"data/hd/global/ui/spells/{target}.sprite",
                       "frames": n, "src_size": [src[0][0], src[0][1]] if src else None, "hd_size": size,
                       "stride": stride, "lowend_size": low, "paired": bool(cls == "" and plan)}
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path, help="also write PNG strips of the HD sheets here")
    args = ap.parse_args()
    pal = palette(BASE / "palette" / "pal.dat")
    plan = shared_icons.load_plan()
    report = convert(pal, args.preview, plan=plan)
    if plan:
        dc = shared_icons.sheet_dc6(plan, SPELLS, fxpaths.D2R)
        print(f"shared sheet in pairs ({shared_icons.PLAN.name}): {len(plan.icons)} icons; classic {dc.name} "
              f"{dc.stat().st_size} bytes -> shipped by legacy_art.py")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "skill_sheets.json").write_text(json.dumps(report, indent=1), "utf-8")
    skills = load_skills()
    tiers = Counter(TIER_NAMES[s["tier"]] for s in skills)
    for cls, r in report.items():
        print(f"{r['dc6']}: {r['frames']} frames -> HD {r['hd_size']}px (stride {r['stride']})")
    print(f"{sum(r['frames'] for r in report.values())} frames in {len(report)} sheets; {len(skills)} skills name a skilldesc "
          f"({', '.join(f'{n} {t}' for t, n in tiers.items())})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
