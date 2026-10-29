"""Static item-rule checks behind docs/median-rules-audit.md (items sections); proves data, not runtime behaviour.

    py -3 -I tools/item_rules_audit.py [--median DIR]

DIR = Median's data/global/excel with the compiled .bin files (default: assets/median/... of the asset pack, else
<MXL2012_RUNS>/extract-mpq/...). Reads work/named (Median's tables as the build normalised them) and work/mod (the build),
so run it after tools/build.py. Read-only. Checks:

  cube-bin    every built cubemain input / output against the record 1.13c compiled from Median's own txt (cubemain.bin,
              0x148-byte records: +0 enabled, +2 min diff, +3 class, +4 op, +8 param, +0xc value, +0x10 numinputs,
              +0x12 version, inputs at +0x14 (8 bytes: flags, item / type, unique id + 1, quality, qty), outputs at
              +0x4c + 0x54 * n (+4 unique id + 1)); header fields of the txt against the bin
  properties  every property code an item table uses exists in the built properties.txt, and none is inert (no stat)
  vendors     every vendor cell (17 NPCs x Min / Max / MagicMin / MagicMax / MagicLvl) of the three base tables
  tc-reach    treasure classes holding a cleared entry (work/mod/migrate_report.md): which root reaches them
"""
import argparse
import csv
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMED = ROOT / "work" / "named"
BUILT = ROOT / "work" / "mod" / "data" / "global" / "excel"
RECORD = 0x148
CLASSES = {"ama": 0, "sor": 1, "nec": 2, "pal": 3, "bar": 4, "dru": 5, "ass": 6, "": 255}
VENDORS = ("Charsi", "Gheed", "Akara", "Fara", "Lysander", "Drognan", "Hralti", "Alkor", "Ormus", "Elzix", "Asheara",
           "Cain", "Halbu", "Jamella", "Larzuk", "Drehya", "Malah")
VENDOR_RENAMES = {"Hralti": "Hratli", "Drehya": "Anya"}  # txt_migrate.RENAMES
ITEM_PROP_TABLES = ("uniqueitems", "setitems", "sets", "runes", "magicprefix", "magicsuffix", "automagic",
                    "qualityitems", "gems", "cubemain")
TC_ROOTS = ("monstats", "superuniques", "objects", "levels", "npc", "cubemain", "difficultylevels", "hireling", "misc")


def read(path: Path, enc: str = "utf-8-sig") -> list[dict]:
    with path.open(encoding=enc, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def token(cell: str) -> str:
    return (cell or "").strip().strip('"').partition(",")[0]


def cube_record(data: bytes, row: int) -> dict:
    """One record of a 1.13c cubemain.bin (layout in the module docstring)."""
    r = data[4 + row * RECORD: 4 + (row + 1) * RECORD]
    param, value, numinputs, version = struct.unpack_from("<iihH", r, 8)
    return {"enabled": r[0], "min diff": r[2], "class": r[3], "op": r[4], "param": param, "value": value,
            "numinputs": numinputs, "version": version,
            "inputs": [struct.unpack_from("<HHHBB", r, 0x14 + 8 * k) for k in range(7)],
            "outputs": [struct.unpack_from("<HHH", r, 0x4c + 0x54 * k) for k in range(3)]}


def number(v: str) -> int:
    v = (v or "").strip()
    return int(v) if v.lstrip("-").isdigit() else 0


def header_diffs(src: dict, rec: dict) -> list[str]:
    """Fields where Median's txt row and the compiled record disagree."""
    want = {"enabled": number(src.get("enabled")), "min diff": number(src.get("min diff")),
            "class": CLASSES.get(src.get("class", ""), -1), "op": number(src.get("op")), "param": number(src.get("param")),
            "value": number(src.get("value")), "numinputs": number(src.get("numinputs")),
            "version": number(src.get("version"))}
    return [k for k, v in want.items() if rec[k] != v]


def first_rows(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, r in enumerate(rows):
        out.setdefault(r[key], i)
    return out


def check_cube(median: Path) -> Counter:
    data = (median / "cubemain.bin").read_bytes()
    n = struct.unpack_from("<I", data, 0)[0]
    src, built = read(median / "cubemain.txt", "latin-1"), read(BUILT / "cubemain.txt")
    items = [r["code"] for t in ("weapons", "armor", "misc") for r in read(median / f"{t}.txt", "latin-1")
             if r.get("name") != "Expansion" and r["code"]]
    types = [r["Code"] for r in read(median / "itemtypes.txt", "latin-1") if r["ItemType"] != "Expansion"]
    uniques = first_rows(read(BUILT / "uniqueitems.txt"), "index")
    out = Counter(records=n, txt_rows=len(src), built_rows=len(built))
    for row in range(n):
        rec = cube_record(data, row)
        for f in header_diffs(src[row], rec):
            out[f"header differs: {f}"] += 1
        for k, (flags, item, uid, _q, _qty) in enumerate(rec["inputs"]):
            name = token(built[row][f"input {k + 1}"])
            if not name:
                out["input empty" if not flags else "input DIFF: bin has one, txt none"] += 1
            elif not flags:
                out["input DIFF: txt names one, 1.13c compiled none"] += 1
                print(f"  cube row {row + 1} input {k + 1}: '{name}' is not in 1.13c's record")
            elif flags & 0x40:  # a unique by name; the record holds its row + 1
                out["input unique " + ("same" if uniques.get(name) == uid - 1 else "DIFF")] += 1
            else:
                compiled = types[item] if flags & 2 else items[item]
                ok = compiled.replace("\xb5", "^") == name  # mxl2012_prep.CODE_CHAR
                out[("input type " if flags & 2 else "input code ") + ("same" if ok else "DIFF")] += 1
        for k, (_flags, _item, uid) in enumerate(rec["outputs"]):
            name = token(built[row][("output", "output b", "output c")[k]])
            if name in uniques:
                out["output unique " + ("same" if uniques[name] == uid - 1 else "DIFF")] += 1
    return out


def property_columns(header: list[str]) -> list[str]:
    import re
    return [c for c in header if re.fullmatch(r"(a?prop\d+[ab]?|[PF]Code\d+[ab]?|T1Code\d+|mod\d+code|(?:[bc] )?mod \d"
                                              r"|(?:weapon|helm|shield)Mod\d+Code)", c)]


def check_properties() -> Counter:
    props = read(BUILT / "properties.txt")
    codes = {r["code"] for r in props}
    inert = {r["code"] for r in props if not any(r.get(f"stat{i}") for i in range(1, 8))
             and not any(r.get(f"func{i}") in ("5", "6", "7", "13", "14", "20", "23") for i in range(1, 8))}
    out = Counter()
    for t in ITEM_PROP_TABLES:
        rows = read(BUILT / f"{t}.txt")
        cols = property_columns(list(rows[0]) if rows else [])
        for r in rows:
            for c in cols:
                v = (r.get(c) or "").strip()
                if v:
                    out["cells"] += 1
                    out["missing code" if v not in codes else "inert code" if v in inert else "ok"] += 1
    return out


def check_vendors() -> Counter:
    out = Counter()
    for t in ("weapons", "armor", "misc"):
        for s, b in zip(read(NAMED / f"{t}.txt"), read(BUILT / f"{t}.txt")):
            for v in VENDORS:
                for suf in ("Min", "Max", "MagicMin", "MagicMax", "MagicLvl"):
                    if v + suf in s:
                        out["cells"] += 1
                        out["same" if s[v + suf] == b.get(VENDOR_RENAMES.get(v, v) + suf) else "DIFF"] += 1
    return out


def tc_reach(tc_rows: list[dict], root_cells: dict[str, list[str]], start: str) -> list[str]:
    """Roots (table.column of a cell naming a class) from which `start` is reachable through other classes."""
    names = {r["Treasure Class"] for r in tc_rows}
    parents = defaultdict(set)
    for r in tc_rows:
        for i in range(1, 11):
            v = token(r.get(f"Item{i}", ""))
            if v in names:
                parents[v].add(r["Treasure Class"])
    found, seen, todo = [], set(), [start]
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        found += root_cells.get(n, [])
        todo += parents[n]
    return found


def check_tc() -> Counter:
    tc = read(NAMED / "treasureclassex.txt")
    names = {r["Treasure Class"] for r in tc}
    roots: dict[str, list[str]] = defaultdict(list)
    for t in TC_ROOTS:
        p = NAMED / f"{t}.txt"
        for r in read(p) if p.exists() else []:
            for c, v in r.items():
                if token(v) in names:
                    roots[token(v)].append(f"{t}.{c}")
    report = (BUILT.parents[2] / "migrate_report.md").read_text(encoding="utf-8")
    line = next((x for x in report.splitlines() if x.startswith("treasureclassex: cleared")), "")
    holders = {e.split(": ")[0].strip() for e in line.partition("): ")[2].split("; ") if ": " in e}
    out = Counter(cleared_entries=len(holders))
    for h in sorted(holders):
        reach = tc_reach(tc, roots, h)
        out["reachable" if reach else "unreachable"] += 1
        if reach:
            print(f"  tc {h}: reached from {reach[:3]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--median", type=Path)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fxpaths
    median = a.median or Path(fxpaths.MXL_EXCEL)
    for name, fn in (("cube-bin", lambda: check_cube(median)), ("properties", check_properties),
                     ("vendors", check_vendors), ("tc-reach", check_tc)):
        print(f"{name}: {dict(fn())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
