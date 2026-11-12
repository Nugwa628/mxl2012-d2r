#!/usr/bin/env python3
"""Sets, runewords and gemwords for the wiki generator (docs/wiki-plan.md), with tooltip lines printed by items.py.

  py -3 tools/wiki/setwords.py               write work/wiki/sets.json, runewords.json and gemwords.json
        [--show NAME ...]                    also print the sets / runewords whose shown name or key contains NAME

Reads sets.txt, setitems.txt and runes.txt next to the tables items.py reads.

Sets: a set item is kept when its `spawnable` column is 1, it is not disabled and its item level is at most DROP_LEVEL
(Median parks the classic D2 sets at 126 and its own retired versions at 200, where nothing drops them). A set is kept
when it has a kept item. One record per set:
  name, key          the shown name and the index column
  items              one record per piece, the fields of a unique (items.py) plus `bonus`: its own partial bonuses
                     [{items: n, lines}] (setitems "add func" 2: the a/b props of slot n need n + 1 pieces worn)
  bonus              the set's partial bonuses [{items: n, lines, props}] (sets.txt P*2a/2b .. 5a/5b)
  full, full_props   the full set bonus lines and props (sets.txt F*1..8)

Runewords: a runes.txt row is kept when `complete` is 1. Median repeats every word with one to five jewels in front
of the runes (the item may have more sockets than the word has runes); the rows of one Name are one record:
  name, key          the shown name and the Name column
  runes, rune_names  the rune codes (no jewels) and their shown names
  sockets            the socket counts the word fits in
  itypes, etypes     the allowed and the excluded item types (itemtypes.txt names)
  lvlreq             the highest level requirement of its runes
  props, lines       the stats of the row without jewels

Gemwords are the Gemword rows (one gem, the other sockets jewels; jewels only for the "Secret Jewel Bonus!" rows): one
record per gem with its item kinds, each with the lines per socket count and `lines`, the lines of all counts merged
("+15/30/45% Enhanced Damage").
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import items  # noqa: E402
from items import Data, num, read, strip, tooltip, tier_of  # noqa: E402

OUT = items.ROOT / "work" / "wiki"
DROP_LEVEL = 125
JEWEL = "jew"
GEMWORD = re.compile(r"Gemword\d+$|09\w+$")  # the gemwords and the jewel-only words
NUMBER = re.compile(r"\d+")


def shown(data: Data, key: str):
    """(shown name, the lines drawn under it) of a string key: D2 draws a multi-line string from its last line up."""
    text = data.shown(key)
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    return parts[-1], parts[-2::-1]


def quads_of(row: dict, head: list, slots) -> list:
    return [[row[head[c]], row[head[p]], row[head[lo]], row[head[hi]]] for c, p, lo, hi in slots if row[head[c]]]


def lines_of(data: Data, quads) -> list:
    return tooltip(data, quads)[0]


def base_fields(data: Data, code: str) -> dict:
    base = data.bases.get(code, {})
    base_name = data.base_name(code)
    rec = {"base_code": code, "base_name": base_name, "type": data.types.get(base.get("type", ""), base.get("type", ""))}
    tier = tier_of(base_name)
    if tier is not None:
        rec["tier"] = tier
    return rec


def slot_groups(head: list):
    """{label: [(code, par, min, max) column indexes]} of a table's property columns: '' for the plain props, '2a'.. for
    the numbered ones (items.groups gives them in column order)."""
    out = collections.OrderedDict()
    for c, p, lo, hi in items.groups(head):
        col = head[c].lower()
        label = "F" if col.startswith("fcode") else re.sub(r"^(aprop|pcode)", "", col) if col.startswith(("aprop", "pcode")) else ""
        out.setdefault(label, []).append((c, p, lo, hi))
    return out


def bonus_lines(data: Data, row: dict, head: list, groups: dict, first: int, last: int):
    """[{items, lines, props}] of the numbered a/b slots: the a and b props of number n print together."""
    out = []
    for n in range(first, last + 1):
        quads = quads_of(row, head, groups.get("%da" % n, []) + groups.get("%db" % n, []))
        if quads:
            out.append({"items": n, "lines": lines_of(data, quads), "props": quads})
    return out


def sets(data: Data):
    shead = list(read("sets.txt")[0].keys())
    sgroups = slot_groups(shead)
    rows = read("setitems.txt")
    head = list(rows[0].keys())
    groups = slot_groups(head)
    by_set = collections.OrderedDict()
    for r in rows:
        if r.get("spawnable") != "1" or r.get("disabled") == "1" or not r.get("item") or num(r.get("lvl")) > DROP_LEVEL:
            continue
        name, flavour = shown(data, r["index"])
        quads = quads_of(r, head, groups.get("", []))
        lines, colours = tooltip(data, quads)
        rec = {"name": name, "key": r["index"], **base_fields(data, r["item"]), "lvl": num(r.get("lvl")),
               "lvlreq": num(r.get("lvl req"))}
        if flavour:
            rec["flavour"] = flavour
        rec["props"] = quads
        rec["lines"] = lines
        if any(colours):
            rec["colours"] = colours
        if r.get("add func") in ("1", "2"):  # 1 (a named piece worn) is not used by a kept row: printed as a count too
            rec["bonus"] = [{"items": b["items"] + 1, "lines": b["lines"]} for b in bonus_lines(data, r, head, groups, 1, 5)]
        by_set.setdefault(r["set"], []).append(rec)
    out = []
    for s in read("sets.txt"):
        pieces = by_set.get(s["index"])
        if not pieces:
            continue
        full = quads_of(s, shead, sgroups.get("F", []))
        out.append({"name": shown(data, s["name"] or s["index"])[0], "key": s["index"], "items": pieces,
                    "bonus": bonus_lines(data, s, shead, sgroups, 2, 5),
                    "full": lines_of(data, full), "full_props": full})
    return out


def runes_of(row: dict) -> list:
    return [row["Rune%d" % i] for i in range(1, 7) if row.get("Rune%d" % i)]


def type_names(data: Data, row: dict, prefix: str, count: int) -> list:
    return sorted({name for c in ("%s%d" % (prefix, i) for i in range(1,count+1)) if row.get(c)
                   for name in data.type_bases(row[c])})


def rune_name(data: Data, code: str) -> str:
    return data.base_name(code)


def rune_level(data: Data, code: str) -> int:
    return num(data.bases.get(code, {}).get("levelreq"))


def word_rows():
    """The complete runes.txt rows by Name, in table order; and the property column slots."""
    rows = read("runes.txt")
    head = list(rows[0].keys())
    slots = items.groups(head)
    by_key = collections.OrderedDict()
    for r in rows:
        if r.get("complete") == "1":
            by_key.setdefault(r["Name"], []).append(r)
    return by_key, head, slots


def runewords(data: Data):
    by_key, head, slots = word_rows()
    out = []
    for key, rows in by_key.items():
        if GEMWORD.search(key):
            continue
        rows.sort(key=lambda r: len(runes_of(r)))
        first = rows[0]
        rs = [c for c in runes_of(first) if c != JEWEL]
        quads = quads_of(first, head, slots)
        name, flavour = shown(data, key)
        rec = {"name": name, "key": key, "runes": rs, "rune_names": [rune_name(data, c) for c in rs],
               "sockets": sorted({len(runes_of(r)) for r in rows}), "itypes": type_names(data, first, "itype", 6),
               "etypes": type_names(data, first, "etype", 3), "lvlreq": max((rune_level(data, c) for c in rs), default=0)}
        if flavour:
            rec["flavour"] = flavour
        rec["props"] = quads
        rec["lines"] = lines_of(data, quads)
        out.append(rec)
    return out


def merge_counts(per_count: list) -> list:
    """The lines of several socket counts as one: the numbers of a line are joined with '/' ("+15/30/45% Enhanced
    Damage"), 0 for a count that has no such line."""
    order = list(dict.fromkeys(NUMBER.sub("#", t) for texts in reversed(per_count) for t in texts))
    out = []
    for skel in order:
        values = []
        for texts in per_count:
            hit = next((t for t in texts if NUMBER.sub("#", t) == skel), None)
            values.append(NUMBER.findall(hit) if hit else ["0"] * skel.count("#"))
        it = iter("/".join(dict.fromkeys(c)) for c in zip(*values))
        out.append(re.sub("#", lambda _m: next(it), skel))
    return out


def gemwords(data: Data):
    by_key, head, slots = word_rows()
    gems = collections.OrderedDict()
    for key, rows in by_key.items():
        if not GEMWORD.search(key):
            continue
        for r in rows:
            rs = runes_of(r)
            gem = next((c for c in rs if c != JEWEL), JEWEL)
            kind = (tuple(type_names(data, r, "itype", 6)), tuple(type_names(data, r, "etype", 3)))
            g = gems.setdefault(gem, {"gem": gem, "gem_name": rune_name(data, gem) if gem != JEWEL else "Jewel",
                                      "lvlreq": rune_level(data, gem), "word": shown(data, key)[0], "kinds": {}})
            quads = quads_of(r, head, slots)
            g["kinds"].setdefault(kind, []).append({"sockets": len(rs), "lines": lines_of(data, quads), "props": quads})
    out = []
    for g in gems.values():
        kinds = []
        for (itypes, etypes), counts in g["kinds"].items():
            counts.sort(key=lambda c: c["sockets"])
            kinds.append({"itypes": list(itypes), "etypes": list(etypes), "counts": counts,
                          "lines": merge_counts([c["lines"] for c in counts])})
        out.append({**g, "kinds": kinds})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", nargs="*", default=[])
    a = ap.parse_args()
    data = Data()
    OUT.mkdir(parents=True, exist_ok=True)
    out = {"sets": sets(data), "runewords": runewords(data), "gemwords": gemwords(data)}
    for name, recs in out.items():
        path = OUT / (name + ".json")
        path.write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print("%d %s -> %s" % (len(recs), name, path))
    print("%d set items" % sum(len(s["items"]) for s in out["sets"]))
    if data.unrendered:
        print("descfuncs not printed:", dict(data.unrendered.most_common()))
    sys.stdout.reconfigure(encoding="utf-8")
    for want in a.show:
        for rec in out["sets"] + out["runewords"]:
            if want.lower() in rec["name"].lower() or want.lower() in rec["key"].lower():
                print("\n%s [%s]" % (rec["name"], rec["key"]))
                if "items" in rec:
                    for it in rec["items"]:
                        print("  %s (%s, req %d): %s" % (it["name"], it["base_name"], it["lvlreq"], " | ".join(it["lines"])))
                    for b in rec["bonus"]:
                        print("  (%d items): %s" % (b["items"], " | ".join(b["lines"])))
                    print("  full:", " | ".join(rec["full"]))
                else:
                    print("  runes %s sockets %s types %s not %s req %d" % (" ".join(rec["rune_names"]), rec["sockets"],
                                                                           rec["itypes"], rec["etypes"], rec["lvlreq"]))
                    print("  props:", " ".join("/".join(q) for q in rec["props"]))
                    for ln in rec["lines"]:
                        print("   ", ln)
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
