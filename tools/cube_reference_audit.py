"""Inspect every built cube row's references; does not prove runtime behavior.

Run after build.py: py -3 tools/cube_reference_audit.py. Findings refer to
one-based data row numbers, excluding the header. Both banks are checked.

An input that names nothing compiles to an empty slot in 1.13c (Median's own cubemain.bin, row 10627 "upgrade dark
ring": numinputs 6, input 3 `oµo` absent from the record, the other five present). D2R's input matcher passes an empty
slot at once (0x529d50: slot flags & 3 == 0 -> 1) after the search compared the cube's item count with numinputs, so the
row still needs six items and the sixth may be anything, as in 1.13c. txt_migrate.cube_unresolved_inputs empties such
cells with unresolved_inputs() below (bug #311) instead of leaving D2R a name it cannot resolve.
"""
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCEL = ROOT / "work/mod/data/global/excel"
TABLES = (("weapons", "code"), ("armor", "code"), ("misc", "code"),
          ("itemtypes", "Code"), ("uniqueitems", "index"), ("setitems", "index"))
OUTPUT_WORDS = {"useitem", "usetype", "Cow Portal", "void"}
OPS = {"", "3", "6", "10", "15", "16", "17", "18", "28"}
INPUTS = tuple(f"input {i}" for i in range(1, 8))


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def token(value):
    return value.strip().strip('"').partition(",")[0]


def unresolved_inputs(rows, known):
    """(one-based row, column, name) of every input cell whose item name is not in `known`."""
    return [(n, col, token(row.get(col, ""))) for n, row in enumerate(rows, 1) for col in INPUTS
            if token(row.get(col, "")) and token(row.get(col, "")) not in known]


def audit(rows, known):
    findings = unresolved_inputs(rows, known)
    for n, row in enumerate(rows, 1):
        for col in ("output", "output b", "output c"):
            name = token(row.get(col, ""))
            if name and name not in known | OUTPUT_WORDS:
                findings.append((n, col, name))
        if row.get("op", "") not in OPS:
            findings.append((n, "op", row["op"]))
    return sorted(findings, key=lambda f: f[0])


def main():
    for bank in (EXCEL, EXCEL / "base"):
        known = set()
        for table, col in TABLES:
            known.update(r[col] for r in read(bank / (table + ".txt")))
        rows = read(bank / "cubemain.txt")
        findings = audit(rows, known)
        print(f"{bank.name}: {len(rows)} rows; ops {dict(Counter(r['op'] for r in rows))}; {len(findings)} unresolved")
        for n, col, value in findings:
            print(f"  row {n}: {col}: {value}")


if __name__ == "__main__":
    main()
