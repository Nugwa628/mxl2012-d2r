"""Check that every skill's icon reference resolves to a frame of a generated HD sprite (adapted from another port's
tools/skill_icon_check.py, which compared pixels with Median's D2Sigma sheets; here the references are 1.13c's).

For each skills.txt row that names a skilldesc:
  - the skilldesc row exists and has a numeric IconCel                      (else: unresolved, "no skilldesc row" / "no IconCel")
  - the frame IconCel exists in the skill's sheet (charclass picks the sheet) (else: unresolved, "frame beyond the sheet")
  - class sheets: the pressed frame IconCel + 1 exists too (else: a warning); Median's shared sheet holds one frame per icon,
    so its pressed frame is the next icon (a note, counted)
  - with tools/shared_icons.py's plan (work/mod/shared_icons.json) the class-less skills are read with the plan's rows and cels
    (the built tables), the shared sheet is in pairs: IconCel must be even and IconCel + 1 the same picture
For each sheet: the HD sprite has the DC6's frame count (the plan's 2 x icons for the shared one), and every frame matches its
source frame (opaque fraction and mean colour of the scaled picture against the original DC6 frame; a D2R frame against D2R's
own HD frame; empty frames only where the source is empty); the `.lowend` sprite has the same frames at half size.

Unresolved skills are grouped by tier (tools/skill_icons.py): tree / start skills must resolve (exit 1 otherwise),
bar skills (on the skill bar from items) are the gap that matters, item / monster ones are leftovers of the vanilla tables
that the mod's own UI never draws. `--strict` also fails on bar skills.
Usage: py -3 -I tools/skill_icon_check.py [--strict]   (reads work/hd from tools/skill_icons.py; writes work/hd/skill_icon_check.json)
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dc6 import decode_frame, palette, read_dc6, read_sprite, scale, sprite_info, stats  # noqa: E402
from icon_paths import BASE, HD_OUT, OUT  # noqa: E402
import fxpaths  # noqa: E402
import idmap  # noqa: E402
import shared_icons  # noqa: E402
from skill_icons import BAR, MONSTER, SPELLS, START, TARGETS, TIER_NAMES, TREE, load_skills, lowend_geometry  # noqa: E402

FRACTION_LIMIT = 0.03   # opaque fraction difference
COLOUR_LIMIT = 4.0      # mean premultiplied colour difference (0-255)


def planned(skills: list[dict], plan) -> list[dict]:
    """The skills as the built tables have them after tools/shared_icons.py: class-less ones on the plan's row and cel."""
    out = []
    for s in skills:
        p = plan.skills.get(s["name"], plan.skills.get(s["name"] + shared_icons.RENAMED)) if not s["sheet"] else None
        out.append({**s, "desc": p["row"], "cel": p["cel"], "has_desc": True} if p else s)
    return out


def bank_problems(plan, banks: dict) -> list[str]:
    """Each bank of the built tables (shared_icons.load_banks) as the plan says: every class-less skill of the plan names
    the plan's skilldesc row, and that row the plan's IconCel."""
    out = []
    for b, (dh, drows, sh, srows) in banks.items():
        ic, cc, sd = shared_icons._col(dh, "IconCel"), shared_icons._col(sh, "charclass"), shared_icons._col(sh, "skilldesc")
        cel = {r[0]: r[ic] for r in drows if idmap.is_record(r)}
        for r in srows:
            p = plan.skills.get(r[0]) if idmap.is_record(r) and not r[cc] and r[sd] else None  # (base: RotW's have none)
            if p and (r[sd] != p["row"] or cel.get(r[sd]) != str(p["cel"])):
                out.append(f"bank {b or 'rotw'}: {r[0]} names {r[sd]} (IconCel {cel.get(r[sd])}), the plan {p['row']} "
                           f"(IconCel {p['cel']})")
    return out


def check_skills(skills: list[dict], frames: dict[str, int], paired: bool = False) -> tuple[list[dict], dict]:
    """(problems, counts). A problem is the skill plus 'kind' ('unresolved' or 'warning') and 'why'. paired: the shared
    sheet is in pairs (tools/shared_icons.py), checked like a class sheet."""
    problems, counts = [], Counter()
    for s in skills:
        n = frames[s["sheet"]]
        why = None
        if not s["has_desc"]:
            why = "no skilldesc row"
        elif s["cel"] is None:
            why = "no IconCel"
        elif not 0 <= s["cel"] < n:
            why = f"frame {s['cel']} beyond the sheet ({n} frames)"
        if why:
            problems.append({**s, "kind": "unresolved", "why": why})
            continue
        counts["resolved"] += 1
        if (s["sheet"] or paired) and s["cel"] + 1 >= n:
            problems.append({**s, "kind": "warning", "why": f"no pressed frame {s['cel'] + 1}"})
        elif (s["sheet"] or paired) and s["cel"] % 2:
            problems.append({**s, "kind": "warning", "why": "odd IconCel (a pressed frame as the icon)"})
        elif not s["sheet"]:
            counts["shared sheet: pressed frame is the next icon"] += 1
    return problems, counts


def expected(cls: str, pal: list, plan=None, d2r: Path | None = None) -> list:
    """The source picture of every frame of a sheet: decoded DC6 frames, or (shared sheet with a plan) each icon twice,
    D2R's own HD frame for a D2R icon."""
    if not (cls == "" and plan):
        return [decode_frame(w, h, blk, pal, fill=True) for w, h, _x, _y, blk in read_dc6(SPELLS / f"{TARGETS[cls][0]}.dc6")]
    d2r = d2r or fxpaths.D2R
    out, cache = [], {}
    for icon, path in shared_icons.frame_sources(plan, SPELLS, d2r):
        if icon.origin == "mxl":
            w, h, _x, _y, blk = read_dc6(path)[icon.cel]
            pic = decode_frame(w, h, blk, pal, fill=True)
        else:
            sp = d2r / "data" / "hd" / "global" / "ui" / "spells" / f"{shared_icons.SHEETS[icon.sheet][1]}.sprite"
            if sp not in cache:
                cache[sp] = read_sprite(sp)
            pic = cache[sp][icon.cel]
        out += [pic, pic]
    return out


def check_sheet(cls: str, pal: list, plan=None) -> list[str]:
    """Problems of one generated sheet against its sources ([] when it matches)."""
    sheet, target = TARGETS[cls]
    src = expected(cls, pal, plan)
    path = HD_OUT / "global" / "ui" / "spells" / f"{target}.sprite"
    low = path.with_name(path.name.replace(".sprite", ".lowend.sprite"))
    out = []
    if not path.exists() or not low.exists():
        return [f"{sheet}: sprite or lowend sprite missing"]
    info, linfo = sprite_info(path), sprite_info(low)
    if info["frames"] != len(src):
        return [f"{sheet}: sprite has {info['frames']} frames, its sources {len(src)}"]
    _ls, lsize = lowend_geometry(len(src))
    if linfo["frames"] != len(src) or linfo["frame_width"] != lsize or linfo["height"] != lsize:
        out.append(f"{sheet}: lowend sprite is {linfo['frames']} x {linfo['frame_width']}px, expected {len(src)} x {lsize}px")
    ours = read_sprite(path)
    for i, pic in enumerate(src):
        want = stats(pic)
        got = stats(ours[i])
        if abs(want[0] - got[0]) > FRACTION_LIMIT or max(abs(a - b) for a, b in zip(want[1:], got[1:])) > COLOUR_LIMIT:
            out.append(f"{sheet}: frame {i} differs from the DC6 (opaque {want[0]:.3f} vs {got[0]:.3f})")
        elif want[0] > 0 and got[0] == 0:
            out.append(f"{sheet}: frame {i} is empty")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="also fail when skills on the skill bar have no icon")
    args = ap.parse_args()
    pal = palette(BASE / "palette" / "pal.dat")
    plan = shared_icons.load_plan()
    frames = {cls: len(read_dc6(SPELLS / f"{sheet}.dc6")) for cls, (sheet, _t) in TARGETS.items()}
    skills = load_skills()
    if plan:
        frames[""] = 2 * len(plan.icons)
        skills = planned(skills, plan)
    problems, counts = check_skills(skills, frames, paired=bool(plan))
    class_sheets = defaultdict(set)  # skilldesc -> class sheets whose skills use the row (where a classless user's frame may be)
    for s in skills:
        if s["sheet"]:
            class_sheets[s["desc"]].add(s["sheet"])
    for p in problems:
        if class_sheets.get(p["desc"]) and p["sheet"] == "":
            p["why"] += f"; the row is also read from the {'/'.join(sorted(class_sheets[p['desc']]))} sheet"
    sheet_problems = [p for cls in TARGETS for p in check_sheet(cls, pal, plan)]
    if plan:   # every visible class-less skill on a picture of its own (not the "?" of frame 0 / of an unresolved one)
        sheet_problems += [f"visible skill {n} has no picture of its own ({p['method']}; tools/data/item_skill_icons.tsv)"
                           for n, p in plan.skills.items() if p["tier"] in shared_icons.VISIBLE_TIERS
                           and (p["method"].startswith("unresolved") or p["cel"] == 0)]
        sheet_problems += bank_problems(plan, shared_icons.load_banks(shared_icons.BUILT_EXCEL))
    by_tier = defaultdict(list)
    for p in problems:
        by_tier[p["kind"], p["tier"]].append(p)
    report = {"skills": len(skills), "resolved": counts["resolved"], "shared_sheet_paired": bool(plan),
              "shared_pressed_is_next_icon": counts["shared sheet: pressed frame is the next icon"],
              "sheet_problems": sheet_problems,
              "unresolved": {TIER_NAMES[t]: [f"{p['id']} {p['name']} ({p['desc']}): {p['why']}" for p in by_tier["unresolved", t]]
                             for t in range(MONSTER + 1)},
              "warnings": [f"{p['id']} {p['name']}: {p['why']}" for p in problems if p["kind"] == "warning"]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "skill_icon_check.json").write_text(json.dumps(report, indent=1), "utf-8")
    print(f"skill icons: {len(skills)} skills name a skilldesc, {counts['resolved']} resolve to a frame; "
          f"{len(sheet_problems)} sheet problems, {len(report['warnings'])} warnings")
    for t in range(MONSTER + 1):
        n = len(report["unresolved"][TIER_NAMES[t]])
        if n:
            print(f"  unresolved {TIER_NAMES[t]}: {n}")
    for p in sheet_problems[:20]:
        print("  SHEET", p)
    bad = bool(sheet_problems) or any(by_tier["unresolved", t] for t in (TREE, START))
    if args.strict:
        bad = bad or bool(by_tier["unresolved", BAR])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
