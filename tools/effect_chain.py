#!/usr/bin/env python
"""Every missile a skill can put on the screen (lane hdtools-effects), so none is left on a stock HD effect.

A skill names missiles in skills.txt (srvmissile, srvmissilea..c, cltmissile, cltmissilea..d) and each missile names more
in missiles.txt (ExplosionMissile, SubMissile1..3, HitSubMissile1..4, CltSubMissile1..3, CltHitSubMissile1..4). The
picture of a cast is the sum of all of them: Bionetic Slam's white star is not its burst missile but 16 `teethexplodeblue`
that its damage missiles leave behind.

  py -3 tools/effect_chain.py 329                    the chain of skill 329 (Id or skill name)
  py -3 tools/effect_chain.py 329 --hd MISSILES.json and what each row draws in HD (default: D2R's missiles.json)
  py -3 tools/effect_chain.py --missile bioneticmover
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import effect_sheet  # noqa: E402
import effects_hd  # noqa: E402
import fxpaths  # noqa: E402

SKILL_COLS = ("srvmissile", "srvmissilea", "srvmissileb", "srvmissilec", "cltmissile", "cltmissilea", "cltmissileb",
              "cltmissilec", "cltmissiled")
MISSILE_COLS = ("explosionmissile", "submissile1", "submissile2", "submissile3", "hitsubmissile1", "hitsubmissile2",
                "hitsubmissile3", "hitsubmissile4", "cltsubmissile1", "cltsubmissile2", "cltsubmissile3", "clthitsubmissile1",
                "clthitsubmissile2", "clthitsubmissile3", "clthitsubmissile4")


def _lower(rows: list[dict]) -> list[dict]:
    return [{k.lower(): (v or "").strip() for k, v in r.items() if k} for r in rows]


def tables(folder: Path | None = None) -> tuple[list[dict], list[dict]]:
    """(skills.txt rows, missiles.txt rows), column names in lower case."""
    folder = Path(folder or fxpaths.TABLES)
    return _lower(effects_hd.table(folder / "skills.txt")[1]), _lower(effects_hd.table(folder / "missiles.txt")[1])


def skill_missiles(skills: list[dict], skill: str) -> list[str]:
    """The missiles a skill row names (skill: its Id or its name)."""
    key = str(skill).strip().lower()
    row = next((r for r in skills if key in (r.get("id", r.get("*id", "")).lower(), r.get("skill", "").lower())), None)  # built tables: *Id
    if row is None:
        raise KeyError("no skill %r" % skill)
    return [row[c].lower() for c in SKILL_COLS if row.get(c)]


def chain(missiles: list[dict], start: list[str]) -> list[dict]:
    """Every missiles.txt row reachable from `start`, in the order found: {'missile', 'via' (the row and column that names
    it, '' for a start), 'row'}. A name without a row is kept with row None."""
    by_name = {r.get("missile", "").lower(): r for r in missiles}
    out, seen, todo = [], set(), [(n.lower(), "") for n in start]
    while todo:
        name, via = todo.pop(0)
        if not name or name in seen:
            continue
        seen.add(name)
        row = by_name.get(name)
        out.append({"missile": name, "via": via, "row": row})
        if row:
            todo += [(row[c].lower(), "%s.%s" % (name, c)) for c in MISSILE_COLS if row.get(c)]
    return out


def describe(links: list[dict], hd: dict | None = None) -> list[dict]:
    """What each link draws: the classic art (and whether Median brings it) and the HD definition `hd` gives the row."""
    out = []
    for link in links:
        row = link["row"] or {}
        cel = row.get("celfile", "")
        art, median = None, None
        if cel and cel.lower() != "null":
            try:
                art = effect_sheet.art_path("missiles/" + cel)
                median = Path(fxpaths.MXL) in art.parents
            except FileNotFoundError:
                art = None
        item = {"missile": link["missile"], "via": link["via"], "celfile": cel, "art": str(art) if art else None,
                "median_art": median, "light": row.get("light", ""), "known_row": link["row"] is not None}
        if hd is not None:
            item["hd"] = hd.get(link["missile"], "<no entry>")
        out.append(item)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("skill", nargs="?", help="skills.txt Id or skill name")
    ap.add_argument("--missile", help="start from a missiles.txt row instead of a skill")
    ap.add_argument("--hd", help="a missiles.json (default: D2R's)")
    ap.add_argument("--tables", help="folder with skills.txt and missiles.txt (default: the build's or Median's)")
    args = ap.parse_args(argv)
    if not args.skill and not args.missile:
        ap.error("a skill or --missile")
    skills, missiles = tables(args.tables)
    start = [args.missile] if args.missile else skill_missiles(skills, args.skill)
    hd = json.loads((Path(args.hd) if args.hd else fxpaths.d2r_file("data/hd/missiles/missiles.json")).read_text("utf-8"))
    for item in describe(chain(missiles, start), hd):
        print(json.dumps(item))
    return 0


if __name__ == "__main__":
    sys.exit(main())
