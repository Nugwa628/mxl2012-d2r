"""Inventory the excel tables of a classic D2 mod extraction against D2R baselines (read-only on all inputs).

Usage: py -3 -I tools/table_inventory.py <mod-excel-dir> <d2r-excel-dir> [<d2r-base-excel-dir>] [<median214-excel-dir>]

Prints a TSV: table, txt rows, txt columns, bin record count (first dword of .bin), bin size, D2R rows,
D2R base rows, reference bin record count, note. "Expansion" separator rows are not counted.
"""
import struct
import sys
from pathlib import Path


def txt_rows(p: Path):
    if not p.exists():
        return None, None
    lines = p.read_bytes().decode("latin-1").splitlines()
    if not lines:
        return 0, 0
    cols = len(lines[0].split("\t"))
    rows = [ln for ln in lines[1:] if ln.strip() and ln.split("\t")[0].strip().lower() != "expansion"]
    return len(rows), cols


def bin_count(p: Path):
    if not p.exists():
        return None, None
    b = p.read_bytes()
    return (struct.unpack_from("<I", b, 0)[0] if len(b) >= 4 else None), len(b)


def main():
    mod = Path(sys.argv[1])
    d2r = Path(sys.argv[2])
    base = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    m214 = Path(sys.argv[4]) if len(sys.argv) > 4 else None
    stems = sorted({p.stem.lower() for p in mod.iterdir() if p.suffix.lower() in (".txt", ".bin")})
    print("table\ttxt_rows\ttxt_cols\tbin_count\tbin_size\td2r_rows\td2r_base_rows\tm214_bin_count\tnote")
    for s in stems:
        tr, tc = txt_rows(mod / f"{s}.txt")
        bc, bs = bin_count(mod / f"{s}.bin")
        dr, _ = txt_rows(d2r / f"{s}.txt")
        br, _ = txt_rows(base / f"{s}.txt") if base else (None, None)
        mc, _ = bin_count(m214 / f"{s}.bin") if m214 else (None, None)
        notes = []
        if dr is None and (d2r / f"{s}.bin").exists():
            notes.append("d2r bin only")
        elif dr is None:
            notes.append("not in D2R")
        if tr is not None and bc is not None and tr != bc:
            notes.append(f"txt/bin differ ({tr} vs {bc})")
        if tr is None:
            notes.append("bin only")
        if bc is None:
            notes.append("txt only")
        f = lambda v: "" if v is None else str(v)  # noqa: E731
        print("\t".join([s, f(tr), f(tc), f(bc), f(bs), f(dr), f(br), f(mc), "; ".join(notes)]))


if __name__ == "__main__":
    main()
