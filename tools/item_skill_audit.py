"""Bug #16 audit: every skill / monster parameter of Median's item properties, checked in the built tables.

Median's property tables (work/named/*.txt) give skill and monster parameters as Median row numbers; D2R keeps its own
rows at their ids, so the migration moves Median's (skills from 357 on by +72) and rewrites the parameters
(txt_migrate.py remap_property_params). This audit checks the result without the migration's id map: the parameter's
skill is taken by NAME from Median's skills table (named/skills.txt, row -> name) and looked up by name in the built
skills.txt (*Id). Same for monsters (named/monstats.txt first column -> row of the built monstats.txt).

A property's parameter is a skill / monster row when its properties.txt row says so (the same rule as
txt_migrate.param_kinds: func 11/19/22, a skill tooltip function, Encode 2/3; func 12 takes skills in min / max; descfunc
23 is a monster). Empty parameters of the properties that take a default skill (propertiesext) are checked too.

`py -3 tools/item_skill_audit.py` prints the totals and every mismatch. `audit()` returns (checked, mismatches, samples);
samples are item rows (unique / set / runeword) with a skill parameter, for the in-game check (game_checks.py itemskills).
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strings_ns import bare  # noqa: E402  (the built tables qualify string-key cells as `mxl2012:<key>`; the named ones are bare)

NAMED = os.path.join(ROOT, "work", "named")
BUILT = os.path.join(ROOT, "work", "mod", "data", "global", "excel")
SIGMA = os.path.join(ROOT, "work", "sigma", "propertiesext.txt")
TABLES = ("uniqueitems", "setitems", "sets", "runes", "magicprefix", "magicsuffix", "automagic", "rareprefix",
          "raresuffix", "qualityitems", "lowqualityitems", "gems", "cubemain", "monprop")
SKILL_DESCFUNCS = {"15", "16", "24", "27", "28", "33", "37", "38"}


def read(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        return list(csv.reader(f, delimiter="\t"))


def groups(header):
    """(code, param, min, max) column indexes of each property slot (same rule as txt_migrate.property_columns)."""
    lower = {c.lower(): i for i, c in enumerate(header)}
    out = []
    for i, c in enumerate(header):
        if m := re.fullmatch(r"(a?)prop(\d+[ab]?)((?: \([nh]\))?)", c, re.I):
            keys = [f"{m[1]}{x}{m[2]}{m[3]}" for x in ("par", "min", "max")]
        elif m := re.fullmatch(r"([pf]|t1)code(\d+[ab]?)", c, re.I):
            keys = [f"{m[1]}{x}{m[2]}" for x in ("param", "min", "max")]
        elif m := re.fullmatch(r"(\w*mod\d+)code", c, re.I):
            keys = [f"{m[1]}{x}" for x in ("param", "min", "max")]
        elif m := re.fullmatch(r"((?:[bc] )?mod \d+)", c, re.I):
            keys = [f"{m[1]} {x}" for x in ("param", "min", "max")]
        else:
            continue
        out.append((i, *(lower.get(k.lower()) for k in keys)))
    return out


def kinds_and_stats():
    """property code -> (kind, stat name of func1); kind skill / skill-range / monster, from the built tables."""
    ph, prows = (lambda t: (t[0], t[1:]))(read(os.path.join(BUILT, "properties.txt")))
    ih, irows = (lambda t: (t[0], t[1:]))(read(os.path.join(BUILT, "itemstatcost.txt")))
    stats = {r[0]: r for r in irows if r and r[0]}
    kinds = {}
    for r in prows:
        if not r or not r[0]:
            continue
        func, stat = r[ph.index("func1")], r[ph.index("stat1")]
        s = stats.get(stat)
        descfunc = s[ih.index("descfunc")] if s else ""
        encode = s[ih.index("Encode")] if s else ""
        if func == "12":
            kinds[r[0]] = ("skill-range", stat)
        elif func in ("11", "19", "22") or descfunc in SKILL_DESCFUNCS or encode in ("2", "3"):
            kinds[r[0]] = ("skill", stat)
        elif descfunc == "23":
            kinds[r[0]] = ("monster", stat)
    return kinds


def name_oracles():
    """Median row -> name from the named tables, and name -> built id (skills: *Id column, monsters: row number)."""
    sn = read(os.path.join(NAMED, "skills.txt"))
    median_skill = {i: bare(r[0]) for i, r in enumerate(sn[1:]) if r and r[0]}
    sb = read(os.path.join(BUILT, "skills.txt"))
    idc = sb[0].index("*Id")
    built_skill = {}
    for r in sb[1:]:
        if r and r[0] and r[idc].isdigit():
            built_skill.setdefault(bare(r[0]), int(r[idc]))
    mn = read(os.path.join(NAMED, "monstats.txt"))
    median_mon = {i: bare(r[0]) for i, r in enumerate(mn[1:]) if r and r[0]}
    mb = read(os.path.join(BUILT, "monstats.txt"))
    built_mon = {}
    for i, r in enumerate(mb[1:]):
        if r and r[0]:
            built_mon.setdefault(bare(r[0]), i)
    return median_skill, built_skill, median_mon, built_mon


def audit():
    kinds = kinds_and_stats()
    median_skill, built_skill, median_mon, built_mon = name_oracles()
    defaults = {}
    if os.path.exists(SIGMA):
        for r in read(SIGMA)[1:]:
            if len(r) > 2 and r[2].lstrip("-").isdigit() and int(r[2]) != 0:
                defaults[r[1]] = int(r[2])
    checked, bad, samples = Counter(), [], defaultdict(list)
    unmapped = Counter()
    audit.wanted = set()  # tables whose Median rows carry a skill / monster parameter at all (a row the build lost still counts)

    def expect(kind, value):
        if kind == "monster":
            name = median_mon.get(value)
            return name, built_mon.get(name)
        name = median_skill.get(value)
        return name, built_skill.get(name)

    for table in TABLES:
        npath, bpath = os.path.join(NAMED, table + ".txt"), os.path.join(BUILT, table + ".txt")
        if not (os.path.exists(npath) and os.path.exists(bpath)):
            continue
        nt, bt = read(npath), read(bpath)
        ng, bg = groups(nt[0]), groups(bt[0])
        built_rows = defaultdict(list)
        for i, r in enumerate(bt[1:]):
            if r and r[0]:
                built_rows[bare(r[0])].append((i, r))
        seen = Counter()
        for r in nt[1:]:
            if not r or not r[0] or r[0] == "Expansion":
                continue
            key = bare(r[0])  # rows are matched by their name cell, whatever the namespace prefix
            nth = seen[key]
            seen[key] += 1
            if any(c < len(r) and r[c] and kinds.get(r[c]) and r[p].isdigit() for c, p, _lo, _hi in ng if p is not None and p < len(r)):
                audit.wanted.add(table)
            if nth >= len(built_rows.get(key, [])):
                continue  # a Median row the build dropped (disabled / replaced): nothing to compare
            index, br = built_rows[key][nth]
            for (ncode, npar, nlo, nhi), (bcode, bpar, blo, bhi) in zip(ng, bg):
                code = r[ncode] if ncode < len(r) else ""
                if not code or code != br[bcode]:
                    continue
                kind = kinds.get(code)
                if kind is None:
                    continue
                kind, stat = kind
                cols = [(nlo, blo), (nhi, bhi)] if kind == "skill-range" else [(npar, bpar)]
                for nc, bc in cols:
                    if nc is None or bc is None or nc >= len(r) or bc >= len(br):
                        continue
                    value = r[nc]
                    if value == "" and kind == "skill" and code in defaults:  # propertiesext default skill
                        want_name, want = expect("skill", defaults[code])
                    elif value.isdigit():
                        want_name, want = expect(kind, int(value))
                    else:
                        continue  # a name or an element: nothing to translate
                    checked[(table, kind)] += 1
                    got = br[bc]
                    if want_name is None:  # not a row of Median's table (e.g. 3374): the migration leaves it alone
                        unmapped[(table, kind)] += 1
                        if got != value:
                            bad.append((table, r[0], code, kind, value, want_name, want, got))
                        continue
                    if want is None or str(want) != got:
                        bad.append((table, r[0], code, kind, value, want_name, want, got))
                    elif table in ("uniqueitems", "setitems", "runes") and kind == "skill" and want is not None:
                        samples[code].append((table, index, r[0], int(got), want_name, stat))
    audit.unmapped = unmapped
    return checked, bad, samples


def main():
    checked, bad, samples = audit()
    print("checked parameters:", {f"{t}/{k}": n for (t, k), n in sorted(checked.items())}, "total", sum(checked.values()))
    print("not a Median skill / monster row, left alone:", dict(sorted(audit.unmapped.items())))
    print("mismatches:", len(bad))
    for b in bad[:60]:
        print("  %s %r prop %s (%s): Median %s = %s -> built id %s, table has %r" % b)
    print("sample property codes with items:", len(samples))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
