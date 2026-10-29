"""Median XL 2012 .txt tables -> work/named/ (normalised, UTF-8).

Replaces an mxl_names.py + formula.py convert: 2012 ships real .txt tables (and 1.13c's own formula text, which
already uses the `skill('Name'.blvl)` / `stat('name'.accr)` syntax D2R keeps), so there is nothing to decode or to resolve.
This step only makes the files uniform:

  * decode: cp1252-ish bytes -> UTF-8 (the files are not UTF-8). 0xB5 (µ) is a letter of 24 item codes (`µ01`, `6oµ`, in
    misc / cubemain / treasureclassex); D2R item codes are 4 raw bytes, so it becomes CODE_CHAR (one ASCII character no
    other code uses). 0xA0 -> space, 0x85 -> `...` (comment cells).
  * line endings CRLF, rows padded / cut to the header length; tables nothing reads (SKIP) are not written.
  * names the formulas use with 32 or more characters (D2R's formula parser keeps 31, trap 8) get a compact key; the key
    row, every reference to it (tools/idmap.py NAME_REFS) and the formula text follow.

The id mapping itself (row numbers, renames of D2R-renamed keys, slots) is tools/idmap.py's, run by txt_migrate.py.

Usage: py -3 -I tools/mxl2012_prep.py [--src <assets/median>/data/global/excel] [--out work/named]
(default --src: MXL2012_SRC, else tools/fxpaths.py's Median tree: assets/median, else <MXL2012_RUNS>/extract-mpq)
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402
import idmap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = Path(os.environ.get("MXL2012_SRC") or fxpaths.MXL_EXCEL)
CODE_CHAR = "^"  # replaces the 0xB5 letter of the 24 µ item codes (checked: no other item code uses it)
BYTE_FIXES = {0xB5: CODE_CHAR, 0xA0: " ", 0x85: "..."}
# Tables the mod ships that nothing reads (older copies / tools' notes): not migrated.
SKIP = {"treasureclass", "uniqueitems2", "aiparms", "cubetype", "monname", "weaponclass"}
# Formula function -> id space whose key it names
FORMULA_FUNCS = {"skill": "skills", "sksrc": "skills", "sklvl": "skills", "miss": "missiles", "stat": "itemstatcost"}


def decode(raw: bytes) -> str:
    out = []
    for b in raw:
        out.append(BYTE_FIXES.get(b) if b in BYTE_FIXES else chr(b) if b < 0x80 else bytes([b]).decode("cp1252", "replace"))
    return "".join(out)


def normalise(text: str) -> tuple[list[str], list[list[str]]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    header = lines[0].split("\t")
    rows = []
    for l in lines[1:]:
        cells = l.split("\t")
        cells = (cells + [""] * len(header))[:len(header)]
        rows.append(cells)
    return header, rows


def write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.writelines("\t".join(r) + "\r\n" for r in [header, *rows])


def long_formula_names(named: Path) -> dict[str, dict[str, str]]:
    """entity -> {name: compact key} for every skill / missile / stat the formulas name with 32+ characters."""
    rx = re.compile(r"\b(skill|sksrc|sklvl|miss|stat)\('([^']{32,})'")
    out: dict[str, dict[str, str]] = {}
    for p in sorted(named.glob("*.txt")):
        for m in rx.finditer(p.read_text("utf-8")):
            name = m.group(2)
            out.setdefault(FORMULA_FUNCS[m.group(1)], {})[name] = name[:24] + "_" + hashlib.sha1(name.encode()).hexdigest()[:5]
    return out


def apply_renames(named: Path, renames: dict[str, dict[str, str]]) -> int:
    """Rename keys: the key cell of the entity's own table, every name-reference column of idmap.NAME_REFS and the quoted
    names in formulas (`skill('old'.x)`)."""
    n = 0
    for p in sorted(named.glob("*.txt")):
        header, rows = normalise(p.read_text("utf-8"))
        cols: dict[int, dict[str, str]] = {}
        for ent, mapping in renames.items():
            low = {k.lower(): v for k, v in mapping.items()}
            if p.stem == ent:
                ki = idmap.col(header, idmap.ENTITIES[ent].key)
                if ki is not None:
                    cols[ki] = {**cols.get(ki, {}), **low}
            for tables, cre, entity in idmap.NAME_REFS:
                if re.fullmatch(tables, p.stem) and ent in entity.split("|"):
                    for ci, h in enumerate(header):
                        if re.fullmatch(cre, h, re.I):
                            cols[ci] = {**cols.get(ci, {}), **low}
        funcs = "|".join(f for f, e in FORMULA_FUNCS.items() if e in renames)
        rx = re.compile(r"\b(%s)\('([^']{32,})'" % funcs)
        changed = False
        for r in rows:
            for ci, mapping in cols.items():
                if r[ci].lower() in mapping:
                    r[ci] = mapping[r[ci].lower()]
                    n += 1
                    changed = True
            for ci, v in enumerate(r):
                if "('" in v:
                    new = rx.sub(lambda m: "%s('%s'" % (m.group(1), renames[FORMULA_FUNCS[m.group(1)]].get(m.group(2), m.group(2))), v)
                    if new != v:
                        r[ci] = new
                        n += 1
                        changed = True
        if changed:
            write(p, header, rows)
    return n


def superunique_separator(header: list[str], rows: list[list[str]]) -> int:
    """Median 2012's superuniques.txt row 42 is vanilla's "Expansion" separator with the label moved from the first column to
    `Name` (first column, Class and hcIdx blank). 1.13c then compiled it as a record (Median's .bin has 84), every superunique from
    Siege Boss on sat one number above the ones the quest code names, and the Ancients altar summoned Siege Boss + two Ancients:
    the quest never completes and the Worldstone Keep stays shut (docs/bugs.md #362). The label goes back into the first column,
    so the row is a separator again for the id map and for D2R (whose own table has the same row). Returns the rows changed."""
    low = [h.lower() for h in header]
    if not low or low[0] != "superunique" or "name" not in low:
        return 0
    ni, ci = low.index("name"), low.index("class") if "class" in low else None
    hi = low.index("hcidx") if "hcidx" in low else None
    n = 0
    for r in rows:
        blank = r[0].strip() == "" and (ci is None or r[ci].strip() == "") and (hi is None or r[hi].strip() == "")
        if blank and r[ni].strip().lower() == "expansion":
            r[0] = "Expansion"
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=ROOT / "work" / "named")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    count = 0
    for p in sorted(args.src.glob("*.txt")):
        if p.stem in SKIP:
            continue
        header, rows = normalise(decode(p.read_bytes()))
        if p.stem == "superuniques":
            print(f"superuniques: {superunique_separator(header, rows)} separator row restored (bug #362)")
        write(args.out / p.name, header, rows)
        count += 1
    renames = long_formula_names(args.out)
    n = apply_renames(args.out, renames) if renames else 0
    (ROOT / "work" / "prep_renames.json").write_text(json.dumps(renames, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{count} tables from {args.src} -> {args.out}; formula names of 32+ characters shortened: "
          f"{ {e: len(m) for e, m in renames.items()} } ({n} cells)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
