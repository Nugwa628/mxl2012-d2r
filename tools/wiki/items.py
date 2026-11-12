#!/usr/bin/env python3
"""Unique items for the wiki generator (docs/wiki-plan.md): every unique the game can drop, with its tooltip lines.

  py -3 tools/wiki/items.py                  write work/wiki/uniques.json
        [--out FILE]                         another output file
        [--show NAME ...]                    also print the records whose shown name or key contains NAME
        [--gaps]                             print the stats that get no line, by count

Reads the built tables (work/mod/data/global/excel: uniqueitems, properties, itemstatcost, weapons / armor / misc,
itemtypes, skills, skilldesc, monstats, charstats, playerclass) and the strings the player reads
(tools/strings_ns.effective_texts). A row is kept when its `spawnable` column is 1 (the rule the game's unique roll uses);
rows keep the table order.

One record per row:
  name, flavour      the shown name (the last line of a multi-line name) and the lines drawn under it
  key                the index column
  base_code, base_name, type   the base item, its shown name and its item type name
  lvl, lvlreq        item level and required level
  tier               1..n for tiered uniques (the base's "(n)"), "sacred" on a sacred base; missing otherwise
  props              the raw [prop, par, min, max] quads
  lines              the stat lines as the tooltip prints them, highest descpriority first, then "Socketed (n)"
  colours            same length as lines, the colour code a line's string carries (null when none); only when one has

Stat lines: each property goes through properties.txt (func, stat1..7) to stats; each stat is printed with the built
itemstatcost row (descfunc / descval / descstrpos / descstrneg / descstr2) using tooltip_audit.expected (Median's descfunc
text rules) for the plain value functions and the skill / class / monster functions here. A rolled value prints as
"[min-max]" where the number goes. Group lines (dgrp: all attributes, all resistances ...) replace their stats when every
stat of the group is on the item with the same value. Damage pairs print as the game merges them ("Adds X-Y fire damage",
"+N% Enhanced Damage"); per-level stats print their rate and range, "+(0.5 per Character Level) 0-60 to Strength (Based
on Character Level)" (value * level >> op param, level 1 to experience.txt's MaxLvl). A stat with no descfunc (item_aura,
state, fade, item_lightcolor, damage_vs_montype: Median shows what they do through its desc-* stats) gets no line, as in
the game; --gaps lists them apart from the stats whose descfunc is not printed here.
"""
import argparse
from functools import cache
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import localconfig  # noqa: E402,F401  (MXL_D2R_EXTRACT: D2R's own strings)

if os.environ.get("MXL_D2R_EXTRACT") and not os.environ.get("D2R_LNG"):
    os.environ["D2R_LNG"] = str(Path(os.environ["MXL_D2R_EXTRACT"]) / "data" / "local" / "lng")
import strings_ns  # noqa: E402
import tooltip_audit  # noqa: E402
from item_skill_audit import groups  # noqa: E402

EXCEL = ROOT / "work" / "mod" / "data" / "global" / "excel"
OUT = ROOT / "work" / "wiki" / "uniques.json"
SLOTS = 12
SENTINEL = 987654300  # the printed value tooltip_audit.expected is made to print; replaced by the range (x 128 / 100 is whole)
COLOUR_NAMES = {"0": "white", "1": "red", "2": "green", "3": "blue", "4": "gold", "5": "grey", "6": "black", "7": "tan",
                "8": "orange", "9": "yellow", ":": "dark green", ";": "purple", "/": "white"}
COLOUR_CODE = re.compile("(?:ÿc|)(.)", re.S)
PLACEHOLDER = re.compile(r"%%|%(\d)|%([-+ #0]*)\d*([dius])")
PER_LEVEL = {6, 7, 8, 9}
CHOICE_LIMIT = 6  # a random monster of a range: its names are listed up to this many
# damage pairs the game prints as one line: (min stat, max stat, length stat, text when equal, text for a range)
DAMAGE = (("mindamage", "maxdamage", None, "strModMinDamage", "strModMinDamageRange"),
          ("firemindam", "firemaxdam", None, "strModFireDamage", "strModFireDamageRange"),
          ("lightmindam", "lightmaxdam", None, "strModLightningDamage", "strModLightningDamageRange"),
          ("magicmindam", "magicmaxdam", None, "strModMagicDamage", "strModMagicDamageRange"),
          ("coldmindam", "coldmaxdam", "coldlength", "strModColdDamage", "strModColdDamageRange"),
          ("poisonmindam", "poisonmaxdam", "poisonlength", "strModPoisonDamage", "strModPoisonDamageRange"))
ENHANCED = ("item_mindamage_percent", "item_maxdamage_percent", "strModEnhancedDamage")
SILENT = {"coldlength", "poisonlength", "item_numsockets"}  # printed with their damage pair / as "Socketed (n)"
# properties.txt functions whose stats the column leaves empty (D2's fixed stats)
FIXED_STATS = {5: ("mindamage",), 6: ("maxdamage",), 7: ("item_maxdamage_percent", "item_mindamage_percent"),
               20: ("item_indesctructible",)}


def read(name: str):
    return tooltip_audit.read_table(EXCEL / name)


def num(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class Data:
    """The tables and strings one run reads."""

    def __init__(self):
        self.texts = strings_ns.effective_texts()
        self.props = {r["code"]: r for r in read("properties.txt")}
        self.stats = {r["Stat"]: r for r in read("itemstatcost.txt")}
        self.stat_id = {name: num(r["*ID"]) for name, r in self.stats.items()}
        self.bases = {}
        for table in ("weapons.txt", "armor.txt", "misc.txt"):
            for r in read(table):
                if r.get("code"):
                    self.bases.setdefault(r["code"], r)
        self.types = {r["Code"]: r["ItemType"] for r in read("itemtypes.txt") if r.get("Code")}
        desc = {r["skilldesc"]: r for r in read("skilldesc.txt")}
        self.skills = {}
        for r in read("skills.txt"):
            if r.get("*Id", "").isdigit():
                d = desc.get(r.get("skilldesc", ""))
                name = self.text(d["str name"]) if d and d.get("str name") else ""
                self.skills[int(r["*Id"])] = (strip(name)[0].strip(), r.get("charclass", ""))
        self.monsters = {num(r["*hcIdx"]): strip(self.text(r.get("NameStr", "")))[0].strip() for r in read("monstats.txt")
                         if r.get("*hcIdx", "").isdigit()}
        self.charstats = read("charstats.txt")
        self.max_level = next((num(v) for r in read("experience.txt") if r.get("Level") == "MaxLvl"
                               for k, v in r.items() if k != "Level" and num(v)), 99)
        lines = (EXCEL / "playerclass.txt").read_text("utf-8-sig").splitlines()[1:]  # two columns: read_table skips them
        self.class_index = {ln.split("	")[1]: i for i, ln in enumerate(lines) if ln.count("	") >= 1 and ln.split("	")[1]}
        self.dgrp = {}
        for name, r in self.stats.items():
            if r.get("dgrp"):
                self.dgrp.setdefault(r["dgrp"], []).append(name)
        self.no_line = Counter()      # stat -> times it had no descfunc (the game prints no line for it either)
        self.unrendered = Counter()   # descfunc -> times it could not be printed

    def text(self, cell: str) -> str:
        return self.texts.get(strings_ns.bare(cell), "") if cell else ""

    def shown(self, cell: str) -> str:
        text = strip(self.text(cell))[0].strip()
        if not text:
            raise ValueError('Missing game name string: '+cell)
        return text

    def base_name(self, code: str) -> str:
        return self.shown(self.bases[code].get('namestr','')).split('\n')[-1].strip()

    @cache
    def type_bases(self, code: str) -> list:
        """Concrete allowed base names, never the itemtypes editor labels."""
        rows = {r['Code']:r for r in read('itemtypes.txt') if r.get('Code')}
        def matches(start):
            todo, seen = [start], set()
            while todo:
                c = todo.pop()
                if c == code:
                    return True
                if c and c not in seen:
                    seen.add(c)
                    todo.extend(rows.get(c,{}).get(k,'') for k in ('Equiv1','Equiv2'))
            return False
        return sorted({re.sub(r'\s*\((?:\d+|Sacred)\)$','',self.base_name(c))
                       for c,r in self.bases.items() if r.get('spawnable')=='1' and matches(r.get('type',''))})

    def type_label(self, code: str) -> str:
        # Generic ingredient descriptions are player wording, not editor labels.
        generic = {'weap':'Weapon','armo':'Armor','misl':'quiver','tier':'tiered weapon or armour',
                   'ct1a':'sacred armour','ct2a':'sacred armour','ct1w':'sacred weapon','ct2w':'sacred weapon',
                   'hpot':'Healing Potion','mpot':'Mana Potion','gem4':'Perfect Gem','rune':'Rune'}
        if code in generic:
            return generic[code]
        names = self.type_bases(code)
        if not names:
            raise ValueError('No named bases for item type: '+code)
        return ' / '.join(names)


def strip(text: str):
    """(text without colour codes, the first colour's name or None)."""
    m = COLOUR_CODE.search(text)
    colour = COLOUR_NAMES.get(m.group(1), m.group(1)) if m else None
    return COLOUR_CODE.sub("", text), colour


def rng(lo: int, hi: int, plus: bool = False) -> str:
    """A value or a rolled range as the tooltip prints it: '+12', '[10-20]', '+[10-20]'."""
    sign = "+" if plus and lo > 0 else ""
    return sign + ("%d" % lo if lo == hi else "[%d-%d]" % (lo, hi))


def fill(text: str, args) -> str:
    """D2R's printf on a string: %d / %+d / %i / %s in order, %0..%9 by position; an argument is a str or a (lo, hi)."""
    it = iter(range(len(args)))

    def one(m):
        if m.group(0) == "%%":
            return "%"
        i = int(m.group(1)) if m.group(1) is not None else next(it, None)
        if i is None or i >= len(args):
            return m.group(0)
        a = args[i]
        if isinstance(a, tuple):
            return rng(a[0], a[1], "+" in (m.group(2) or ""))
        return str(a)
    return PLACEHOLDER.sub(one, text)


def per_level(data: Data, stat: str, lo: int, hi: int) -> str:
    """A stat that grows with another one (itemstatcost op 2 / 4 / 5): value * base >> op param. On the character level it
    prints its rate and its values at level 1 and the highest level: '(0.5 per Character Level) 0-60'."""
    row = data.stats.get(stat, {})
    shift = num(row.get("op param"))
    rate = "%g" % (lo / (1 << shift)) if lo == hi else "[%g-%g]" % (lo / (1 << shift), hi / (1 << shift))
    if row.get("op base") != "level":
        return "(%s per Level)" % rate
    return "(%s per Character Level) %d-%d" % (rate, lo >> shift, (hi * data.max_level) >> shift)


DESC_CELLS = ("descstrpos", "descstrneg", "descstr2")


def plain_line(data: Data, stat: str, fn: int, row: dict, lo: int, hi: int):
    """tooltip_audit.expected for a value range: the sentinel's digits replaced by the range. The cells are read as the game
    reads them (the key the cell names), not through Median's `_mxl` alias."""
    neg = hi < 0
    cells = {c: ("cell_" + c if row.get(c) else "") for c in DESC_CELLS}
    texts = {"cell_" + c: data.text(row[c]) for c in DESC_CELLS if row.get(c)}
    value = SENTINEL * 128 // 100 if fn == 5 else SENTINEL  # descfunc 5 prints value * 100 / 128
    if fn == 5:
        lo, hi = lo * 100 // 128, hi * 100 // 128
    text, kind = tooltip_audit.expected(data.stat_id.get(stat, -1), fn, {**row, **cells}, texts, -value if neg else value)
    if kind == "none":
        return ""
    if kind != "text":
        return None
    a, b = sorted((abs(lo), abs(hi))) if neg or lo >= 0 else (lo, hi)
    shown = per_level(data, stat, lo, hi) if fn in PER_LEVEL else rng(a, b)
    return text.replace(str(SENTINEL), shown)


def roll(lo, hi):
    lo, hi = num(lo), num(hi)
    return lo, max(lo, hi)


def item_stats(data: Data, quads):
    """The stats of the properties, in property order: dicts stat, lo, hi, layer, extra (skill / chance / level / ...)."""
    out = {}
    sockets = None
    for slot, (code, par, lo_cell, hi_cell) in enumerate(quads):
        prop = data.props.get(code)
        if prop is None:
            continue
        prev = None
        for j in range(1, 8):
            func = num(prop.get("func%d" % j))
            if not func:
                continue
            stat = prop.get("stat%d" % j, "")
            names = (stat,) if stat else FIXED_STATS.get(func, ())
            lo, hi = roll(lo_cell, hi_cell)
            layer, extra = 0, {}
            if func == 3 and prev is not None:
                lo, hi = prev
            elif func == 14:
                sockets = (lo, hi)
                continue
            elif func == 15:  # the min of a damage pair
                lo = hi = num(lo_cell)
            elif func == 16:
                lo = hi = num(hi_cell)
            elif func == 17:
                lo = hi = num(par)
            elif func == 20:
                lo = hi = 1
            elif func == 21:
                layer = num(prop.get("val%d" % j))
            elif func in (11, 19):  # skill on an event: chance / charges in min, level in max
                layer = num(par)
                extra = {"skill": num(par), "first": num(lo_cell), "level": num(hi_cell)}
                lo = hi = 1
            elif func in (22, 24):
                layer = num(par)
            elif func == 12:  # a random skill / monster of min..max, value = par
                extra = {"choice": (num(lo_cell), num(hi_cell))}
                lo = hi = num(par)
            if func != 3:
                prev = (lo, hi)
            for name in names:
                key = (name, layer, json.dumps(extra, sort_keys=True) if extra else "")
                if key in out:
                    e = out[key]
                    e["lo"] += lo
                    e["hi"] += hi
                    e["roll"] = None
                else:
                    out[key] = {"stat": name, "lo": lo, "hi": hi, "layer": layer, "extra": extra, "order": len(out),
                                "roll": slot}
    return list(out.values()), sockets


def prio(data: Data, stat: str) -> int:
    return num(data.stats.get(stat, {}).get("descpriority"))


def skill_name(data: Data, sid: int) -> str:
    return data.skills.get(sid, ("", ""))[0]


def class_only(data: Data, sid: int) -> str:
    cls = data.class_index.get(data.skills.get(sid, ("", ""))[1])
    if cls is None or cls >= len(data.charstats):
        return ""
    return data.text(data.charstats[cls].get("StrClassOnly", ""))


def item_line(data: Data, e: dict, fn: int, row: dict):
    """The descfuncs that name a skill, a class or a monster of the item. None when not printable here."""
    pos = data.text(row.get("descstrpos", ""))
    x, lo, hi, layer = e["extra"], e["lo"], e["hi"], e["layer"]
    if fn in (15,24,16,27,28) and not skill_name(data, x['skill'] if fn in (15,24) else layer):
        return ''
    if fn == 11:  # repairs: 1 durability in 100 / value seconds, or value / 100 per second
        if lo < 100:
            return fill(data.text("ModStre9u"), [1, 100 // max(lo, 1)])
        return fill(pos, [lo // 100])
    if fn == 13:
        cls = data.charstats[layer] if layer < len(data.charstats) else {}
        return fill(data.text(cls.get("StrAllSkills", "")), [(lo, hi)])
    if fn == 15:
        return fill(pos, [x["first"], x["level"], skill_name(data, x["skill"])])
    if fn == 24:
        return fill(pos, [x["level"], skill_name(data, x["skill"]), x["first"], x["first"]])
    if fn == 16:
        return fill(pos, [(lo, hi), skill_name(data, layer)])
    if fn == 23:
        if "choice" in x:
            a, b = x["choice"]  # a dropped item rolls one monster of the range and names it
            names = list(dict.fromkeys(n for m, n in sorted(data.monsters.items()) if a <= m <= b and n))
            mon = "[%s]" % " / ".join(names) if len(names) <= CHOICE_LIMIT else "[a random monster]"
        else:
            mon = data.monsters.get(layer, "")
            if not mon:
                return ''
        return fill(pos, [(lo, hi), mon])
    if fn == 27:
        return fill(pos, [(lo, hi), skill_name(data, layer), class_only(data, layer)]).strip()
    if fn == 28:
        return fill(pos, [(lo, hi), skill_name(data, layer)])
    return None


def stat_line(data: Data, e: dict):
    row = data.stats.get(e["stat"], {})
    fn = num(row.get("descfunc"))
    if not fn:
        if e["stat"] not in SILENT:
            data.no_line[e["stat"]] += 1
        return ""
    line = item_line(data, e, fn, row) if fn in tooltip_audit.ITEM_FUNCS else plain_line(data, e["stat"], fn, row,
                                                                                       e["lo"], e["hi"])
    if line is None:
        data.unrendered[fn] += 1
        return ""
    return line


def damage_lines(data: Data, by_stat: dict):
    """The merged damage lines: [(priority, order, text)]; the stats they print are removed from by_stat."""
    out = []
    for lo_s, hi_s, len_s, same, ranged in DAMAGE:
        a, b = by_stat.get(lo_s), by_stat.get(hi_s)
        if not (a and b):
            continue
        p = max(prio(data, lo_s), prio(data, hi_s))
        if len_s == "poisonlength":
            ln = by_stat.get(len_s, {"lo": 0})["lo"]
            a_lo, a_hi = (a["lo"] * ln) // 256, (a["hi"] * ln) // 256
            b_lo, b_hi = (b["lo"] * ln) // 256, (b["hi"] * ln) // 256
            secs = ln // 25
        else:
            a_lo, a_hi, b_lo, b_hi, secs = a["lo"], a["hi"], b["lo"], b["hi"], 0
        if (a_lo, a_hi) == (b_lo, b_hi) and a_lo == a_hi:
            text = fill(data.text(same), [(a_lo, a_hi), secs])
        else:
            text = fill(data.text(ranged), [(a_lo, a_hi), (b_lo, b_hi), secs])
        out.append((p, min(a["order"], b["order"]), text))
        for s in (lo_s, hi_s, len_s):
            by_stat.pop(s, None)
    lo_s, hi_s, key = ENHANCED
    a, b = by_stat.get(lo_s), by_stat.get(hi_s)
    if a and b and (a["lo"], a["hi"]) == (b["lo"], b["hi"]):
        out.append((max(prio(data, lo_s), prio(data, hi_s)), min(a["order"], b["order"]),
                    fill(data.text(key), [(a["lo"], a["hi"])])))
        by_stat.pop(lo_s)
        by_stat.pop(hi_s)
    return out


def group_lines(data: Data, by_stat: dict):
    """The dgrp lines: a group prints one line when all of its stats are on the item with the same value."""
    out = []
    for g, members in data.dgrp.items():
        es = [by_stat.get(m) for m in members]
        if not all(es) or len({(e["lo"], e["hi"]) for e in es}) != 1:
            continue
        if es[0]["lo"] != es[0]["hi"] and (es[0]["roll"] is None or len({e["roll"] for e in es}) != 1):
            continue  # separate rolls: the values differ on a dropped item
        row = data.stats[members[0]]
        desc = {"descfunc": row.get("dgrpfunc", ""), "descval": row.get("dgrpval", ""), "descstrpos": row.get("dgrpstrpos", ""),
                "descstrneg": row.get("dgrpstrneg", ""), "descstr2": row.get("dgrpstr2", "")}
        fn = num(desc["descfunc"])
        line = plain_line(data, members[0], fn, desc, es[0]["lo"], es[0]["hi"]) if fn else None
        if line is None:
            data.unrendered["dgrp %s" % fn] += 1
            continue
        out.append((max(prio(data, m) for m in members), min(e["order"] for e in es), line))
        for m in members:
            by_stat.pop(m)
    return out


def tooltip(data: Data, quads):
    """(lines, colours) of one item's properties."""
    stats, sockets = item_stats(data, quads)
    by_stat = {e["stat"]: e for e in stats if not e["layer"] and not e["extra"]}
    entries = damage_lines(data, by_stat) + group_lines(data, by_stat)
    kept = {id(e) for e in by_stat.values()}
    for e in stats:
        if (not e["layer"] and not e["extra"]) and id(e) not in kept:
            continue
        line = stat_line(data, e)
        if line:
            entries.append((prio(data, e["stat"]), e["order"], line))
    entries.sort(key=lambda t: (-t[0], t[1]))
    texts = [t for _p, _o, t in entries]
    if sockets:
        texts.append(fill(data.text("Socketable"), [sockets]))
    lines, colours = [], []
    for t in texts:
        for part in reversed(t.split("\n")):  # D2 draws the lines of a string from the last one up
            text, colour = strip(part)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                lines.append(text)
                colours.append(colour)
    return lines, colours


def tier_of(base_name: str):
    m = re.search(r"\((\d+|Sacred)\)\s*$", base_name)
    if not m:
        return None
    return "sacred" if m.group(1) == "Sacred" else int(m.group(1))


def uniques(data: Data):
    rows = read("uniqueitems.txt")
    head = list(rows[0].keys()) if rows else []
    slots = [(c, p, lo, hi) for c, p, lo, hi in groups(head)][:SLOTS]
    out = []
    for r in rows:
        if r.get("spawnable") != "1" or r.get("disabled") == "1" or not r.get("code"):
            continue
        quads = [[r[head[c]], r[head[p]], r[head[lo]], r[head[hi]]] for c, p, lo, hi in slots if r[head[c]]]
        shown, name_colour = strip(data.text(r['index']))
        if not shown.strip():
            continue
        parts = [p.strip() for p in shown.split("\n") if p.strip()]
        base = data.bases.get(r["code"], {})
        base_name = data.base_name(r['code'])
        lines, colours = tooltip(data, quads)
        rec = {"name": parts[-1], "key": r["index"], "base_code": r["code"],
               "base_name": base_name, "type": data.types.get(base.get("type", ""), base.get("type", "")),
               "lvl": num(r.get("lvl")), "lvlreq": num(r.get("lvl req"))}
        if len(parts) > 1:
            rec["flavour"] = parts[-2::-1]
        if name_colour:
            rec["name_colour"] = name_colour
        tier = tier_of(base_name)
        if tier is not None:
            rec["tier"] = tier
        rec["props"] = quads
        rec["lines"] = lines
        if any(colours):
            rec["colours"] = colours
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--show", nargs="*", default=[])
    ap.add_argument("--gaps", action="store_true")
    a = ap.parse_args()
    data = Data()
    recs = uniques(data)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("%d uniques -> %s" % (len(recs), out))
    if data.unrendered or a.gaps:
        print("descfuncs not printed (gaps):", dict(data.unrendered.most_common()))
    if a.gaps:
        print("stats with no descfunc (no line in game either):", dict(data.no_line.most_common()))
    for want in a.show:
        for rec in recs:
            if want.lower() in rec["name"].lower() or want.lower() in rec["key"].lower():
                print("\n%s [%s] %s (%s) lvl %d req %d%s" % (rec["name"], rec["key"], rec["base_name"], rec["type"], rec["lvl"],
                                                           rec["lvlreq"], " tier %s" % rec["tier"] if "tier" in rec else ""))
                print("  props:", " ".join("/".join(q) for q in rec["props"]))
                for ln in rec["lines"]:
                    print("   ", ln)
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
