"""Static save-format audit of the built mod (docs/save-format.md): does everything Median XL 2012 can put on a character fit
the fields D2R 3.3 + D2RLoader's extended mode save it in?

Checks, on the built tables (`work/mod/data/global/excel`, or `--excel DIR`):
  item stats   every property of uniqueitems / setitems / sets / runes / magic and rare affixes / automagic / gems /
               qualityitems / lowqualityitems: the stat is saved at all (Save Bits > 0; a stat without them is dropped on
               Save and Exit), its value range fits Save Bits after Save Add, and a skill parameter fits the engine's
               16-bit stat layer (extended mode saves 32 bits, the running game keeps 16: skill << 6 | level for the
               skill-event and charged stats, so those skills must be below 1024)
  item fields  item codes (3 characters, only characters the code tree or the extended escape table can write), stack
               sizes (9-bit quantity), sockets (4 bits), grid sizes (4-bit x / y), unique / set / runeword / affix ids
  character    level, experience, unused stat / skill points, gold against CSvBits; skills per class against the
               30-byte `if` section; skill levels against its one byte per skill

  py -3 tools/save_audit.py [--excel DIR]      prints every finding, exit 1 if any is an error
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import d2save  # noqa: E402
from item_skill_audit import groups  # noqa: E402

PROP_TABLES = ("uniqueitems", "setitems", "sets", "runes", "magicprefix", "magicsuffix", "automagic", "rareprefix",
               "raresuffix", "qualityitems", "lowqualityitems", "gems")
# extended-mode field widths (tools/d2save.py)
ID_WIDTHS = {"uniqueitems": 16, "setitems": 16, "magicprefix": 16, "magicsuffix": 16, "rareprefix": 16, "raresuffix": 16,
             "runes": 12}
SUMMED = ("uniqueitems", "setitems", "runes")  # tables whose own property columns all land on one item stat list
QUANTITY_BITS, SOCKET_BITS, GRID_BITS = 9, 4, 4
SKILL_SECTION = 30  # bytes of the `if` section: one per class skill


def read(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    return rows[0], [r + [""] * (len(rows[0]) - len(r)) for r in rows[1:]]


def num(v):
    v = (v or "").strip()
    return int(v) if re.fullmatch(r"-?\d+", v) else None


class Finding:
    def __init__(self, level, area, text):
        self.level, self.area, self.text = level, area, text

    def __repr__(self):
        return f"{self.level.upper():5} {self.area}: {self.text}"


def fits(value, bits, add=0):
    v = value + add
    return 0 <= v < (1 << bits)


def stat_value_ranges(func, par, lo, hi):
    """(param, values) a property slot gives one of its stats (D2's property functions). None = not checked."""
    p, a, b = num(par), num(lo), num(hi)
    vals = [v for v in (a, b) if v is not None]
    if func in (1, 2, 3, 5, 6, 7, 8, 9, 13, 14, 20, 21, 23, 24):
        return None, vals
    if func == 15:
        return None, [a] if a is not None else []
    if func == 16:
        return None, [b] if b is not None else []
    if func == 17:  # per level: the stat holds the parameter
        return None, [p] if p is not None else []
    if func == 22:  # oskill / single skill: param = skill, value = levels
        return par, vals
    if func == 11:  # skill on event: param = skill << 6 | level (max), value = chance (min)
        return ("event", par, b), [a] if a is not None else []
    if func == 19:  # charged: param = skill << 6 | level (max), value = charges | charges << 8
        return ("event", par, b), []
    if func == 10:  # skill tab: param = tab, value = points
        return None, vals
    return None, []


def stat_ranges(excel):
    """stat name -> [lowest, highest] value Median's item tables give a parameter-less item stat (one property, or the sum of a
    unique / set / runeword row's properties of that stat). The build's `stat_save_add` (txt_migrate.py) widens Save Add / Save
    Bits from it."""
    path = lambda n: os.path.join(excel, n)  # noqa: E731
    ph, prows = read(path("properties.txt"))
    props = {}
    for r in prows:
        if r[0]:
            props.setdefault(r[0], [(num(r[ph.index(f"func{i}")]), r[ph.index(f"stat{i}")]) for i in range(1, 8)
                                    if num(r[ph.index(f"func{i}")]) is not None])
    ih, irows = read(path("itemstatcost.txt"))
    has_param = {r[0] for r in irows if r[0] and (num(r[ih.index("Save Param Bits")]) or 0) > 0}
    out = {}

    def note(stat, v):
        acc = out.setdefault(stat, [v, v])
        acc[0], acc[1] = min(acc[0], v), max(acc[1], v)
    for table in PROP_TABLES:
        if not os.path.exists(path(table + ".txt")):
            continue
        h, rows = read(path(table + ".txt"))
        for r in rows:
            if not r[0] or r[0] == "Expansion":
                continue
            sums = {}
            for c, pc, lc, hc in groups(h):
                for func, stat in props.get(r[c], []) if r[c] else []:
                    if not stat or stat in has_param:
                        continue
                    param, values = stat_value_ranges(func, *(r[x] if x is not None else "" for x in (pc, lc, hc)))
                    if param is not None or not values:
                        continue
                    for v in values:
                        note(stat, v)
                    if table in SUMMED and re.match(r"(prop|T1Code)\d", h[c], re.I):
                        acc = sums.setdefault(stat, [0, 0])
                        acc[0] += min(values)
                        acc[1] += max(values)
            for stat, (low, high) in sums.items():
                note(stat, low)
                note(stat, high)
    return out


def audit(excel=d2save.EXCEL):
    out = []
    path = lambda n: os.path.join(excel, n)  # noqa: E731
    t = d2save.Tables.from_excel(excel)
    by_name = {s["name"]: (i, s) for i, s in t.stats.items()}
    ph, prows = read(path("properties.txt"))
    props = {}
    for r in prows:
        if r[0]:
            props.setdefault(r[0], [(num(r[ph.index(f"func{i}")]), r[ph.index(f"stat{i}")]) for i in range(1, 8)
                                    if num(r[ph.index(f"func{i}")]) is not None])
    sh, srows = read(path("skills.txt"))
    skill_id = {}
    for r in srows:
        if r[0] and num(r[sh.index("*Id")]) is not None:
            skill_id.setdefault(r[0], num(r[sh.index("*Id")]))

    def skill_of(par):
        if num(par) is not None:
            return num(par)
        return skill_id.get(par)

    checked = Counter()
    unsaved, overflow, layer = {}, {}, {}
    for table in PROP_TABLES:
        if not os.path.exists(path(table + ".txt")):
            continue
        h, rows = read(path(table + ".txt"))
        for r in rows:
            if not r[0] or r[0] == "Expansion":
                continue
            sums = {}  # stat -> [low, high, slots] of the properties that land on the same item list
            for c, pc, lc, hc in groups(h):
                code = r[c]
                if not code or code not in props:
                    continue
                par, lo, hi = (r[x] if x is not None else "" for x in (pc, lc, hc))
                for func, stat in props[code]:
                    if stat:
                        if stat not in by_name:
                            continue
                        sid, st = by_name[stat]
                    else:
                        continue  # functions without a stat (sockets, ethereal, indestructible) set item fields
                    checked[table] += 1
                    if not st["bits"]:
                        unsaved.setdefault((stat, code), f"{table} {r[0]!r}")
                        continue
                    param, values = stat_value_ranges(func, par, lo, hi)
                    if param is None and not st["par"] and values and table in SUMMED and re.match(r"(prop|T1Code)\d", h[c], re.I):
                        acc = sums.setdefault(stat, [0, 0, 0])
                        acc[0] += min(values)
                        acc[1] += max(values)
                        acc[2] += 1
                    for v in values:
                        if not fits(v, st["bits"], st["add"]):
                            overflow.setdefault((stat, v), f"{table} {r[0]!r} prop {code} = {v}: Save Bits {st['bits']} "
                                                           f"Add {st['add']} hold {-st['add']}..{(1 << st['bits']) - 1 - st['add']}")
                    if isinstance(param, tuple):
                        skill, level = skill_of(param[1]), param[2]
                        if skill is not None and (skill << 6 | max(level or 0, 0)) > 0xFFFF:
                            layer.setdefault((stat, skill), f"{table} {r[0]!r} prop {code} skill {skill}: skill << 6 does not "
                                                            "fit the 16-bit stat layer")
                    elif param is not None:
                        skill = skill_of(param)
                        if skill is not None and skill > 0xFFFF:
                            layer.setdefault((stat, skill), f"{table} {r[0]!r} prop {code} skill {skill} > 16 bits")
            for stat, (low, high, n) in sums.items():
                st = by_name[stat][1]
                if n > 1:
                    for v in (low, high):
                        if not fits(v, st["bits"], st["add"]):
                            overflow.setdefault((stat, v), f"{table} {r[0]!r}: {n} properties add up to {stat} = {v}: Save Bits "
                                                           f"{st['bits']} Add {st['add']} hold {-st['add']}..{(1 << st['bits']) - 1 - st['add']}")
    for (stat, code), where in sorted(unsaved.items()):
        out.append(Finding("warn", "item stats", f"stat {stat} (property {code}, e.g. {where}) has Save Bits 0: not written "
                                                  "to the save; the item is fine only if the game re-derives it on load"))
    for _k, text in sorted(overflow.items()):
        out.append(Finding("error", "item stats", text))
    for _k, text in sorted(layer.items()):
        out.append(Finding("error", "item stats", text))
    out.append(Finding("info", "item stats", "property stats checked: " + ", ".join(f"{k} {v}" for k, v in checked.items())))

    # item fields
    codes, unknown_chars = [], Counter()
    for f in ("armor.txt", "weapons.txt", "misc.txt"):
        h, rows = read(path(f))
        ci, si, mi = h.index("code"), h.index("stackable") if "stackable" in h else None, h.index("maxstack") if "maxstack" in h else None
        gi = h.index("gemsockets") if "gemsockets" in h else None
        for r in rows:
            code = r[ci]
            if not code:
                continue
            codes.append(code)
            if len(code) > 4 or len(code) < 1:
                out.append(Finding("error", "item codes", f"{f} code {code!r} is not 1-4 characters"))
            bad = [ch for ch in code if ch not in d2save.HUFF and ch not in d2save.EXT_CHARS]
            unknown_chars.update(set(bad))
            if si is not None and r[si] == "1" and mi is not None and (num(r[mi]) or 0) >= 1 << QUANTITY_BITS and code != "gld":
                out.append(Finding("error", "stacks", f"{f} {code} maxstack {r[mi]} > {(1 << QUANTITY_BITS) - 1} (9-bit quantity)"))
            if gi is not None and (num(r[gi]) or 0) >= 1 << SOCKET_BITS:
                out.append(Finding("error", "sockets", f"{f} {code} gemsockets {r[gi]} > 15"))
    if unknown_chars:
        out.append(Finding("warn", "item codes", "characters written with the extended escape whose 8-bit value is not in "
                                                 "d2save.EXT_CHARS yet (codes using each): "
                                                 + " ".join(f"{c}:{n}" for c, n in sorted(unknown_chars.items()))))
    dup = [c for c, n in Counter(codes).items() if n > 1]
    if dup:
        out.append(Finding("warn", "item codes", f"codes used twice across armor/weapons/misc: {dup[:10]}"))
    for table, bits in ID_WIDTHS.items():
        if os.path.exists(path(table + ".txt")):
            n = len(read(path(table + ".txt"))[1])
            out.append(Finding("error" if n >= 1 << bits else "info", "item ids", f"{table}: {n} rows, field {bits} bits"))
    h, rows = read(path("inventory.txt"))
    for r in rows:
        x, y = num(r[h.index("gridX")]), num(r[h.index("gridY")])
        if x and y and (x > 1 << GRID_BITS or y > 1 << GRID_BITS):
            out.append(Finding("error", "grids", f"inventory {r[0]} {x}x{y} does not fit 4-bit x / y"))

    # character
    cs = {s["name"]: s for s in t.char_stats.values()}
    h, rows = read(path("experience.txt"))
    maxlvl = num(next(r for r in rows if r[0] == "MaxLvl")[1])
    maxexp = max(num(r[1]) or 0 for r in rows if num(r[0]) is not None and num(r[0]) <= maxlvl)
    ch, crow = read(path("charstats.txt"))
    classes = [r for r in crow if r[0] and r[0] != "Expansion"]
    spl = max(num(r[ch.index("StatPerLevel")]) or 0 for r in classes)
    kpl = max(num(r[ch.index("SkillsPerLevel")]) or 0 for r in classes) if "SkillsPerLevel" in ch else 1
    limits = [("level", maxlvl, "MaxLvl"), ("experience", maxexp, f"experience of level {maxlvl}"),
              ("statpts", spl * (maxlvl - 1) + 15, f"{spl} per level + 15 from quests"),
              ("newskills", kpl * (maxlvl - 1) + 12, f"{kpl} per level + 12 from quests"),
              ("gold", maxlvl * 10000, "10,000 per level (D2's carry cap)"), ("goldbank", 2500000, "D2R's stash cap")]
    for name, need, why in limits:
        st = cs.get(name)
        if not st:
            out.append(Finding("error", "character", f"{name} is not a saved character stat"))
            continue
        cap = (1 << st["csv_bits"]) - 1
        out.append(Finding("error" if need > cap else "info", "character",
                           f"{name}: CSvBits {st['csv_bits']} hold {cap:,}; needed {need:,} ({why})"))
    per_class = Counter(r[sh.index("charclass")] for r in srows if r[sh.index("charclass")])
    for cls, n in sorted(per_class.items()):
        if n > SKILL_SECTION:
            out.append(Finding("error", "skills", f"class {cls}: {n} skills, the save keeps {SKILL_SECTION}"))
    out.append(Finding("info", "skills", "skills per class: " + ", ".join(f"{k} {v}" for k, v in sorted(per_class.items()))))
    mx = max(num(r[sh.index("maxlvl")]) or 0 for r in srows)
    if mx > 255:
        out.append(Finding("error", "skills", f"maxlvl {mx} > 255 (one byte per skill)"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--excel", default=os.environ.get("MXL2012_EXCEL", d2save.EXCEL))
    a = ap.parse_args(argv)
    found = audit(a.excel)
    for f in found:
        print(f)
    n = Counter(f.level for f in found)
    print(f"errors {n['error']}, warnings {n['warn']}")
    return 1 if n["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
