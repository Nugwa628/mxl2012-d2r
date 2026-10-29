"""txt vs bin check for the two tables the inventory lane found with different row counts (objects, objgroup).

The game reads the .bin; the mod also ships the .txt. This decodes the 1.13c bin records (objgroup: 52 bytes, 8 x i32 ids,
8 x u8 density, 8 x u8 prob, u8 shrines, u8 wells; objects: counted by record size only) and compares with the txt rows.
Usage: py -3 -I tools/bin_check.py <excel dir of the pure MPQ extraction>
"""
import struct
import sys
from pathlib import Path


def txt(d: Path, name: str):
    t = (d / f"{name}.txt").read_bytes().decode("latin-1").replace("\r\n", "\n").split("\n")
    if t[-1] == "":
        t.pop()
    return [l.split("\t") for l in t]


def main(d: Path) -> int:
    rows = txt(d, "objgroup")
    h, body = rows[0], rows[1:]
    b = (d / "objgroup.bin").read_bytes()
    n = struct.unpack_from("<I", b)[0]
    bad = 0
    for i in range(n):
        o = 4 + i * 52
        ids = struct.unpack_from("<8i", b, o)
        den, pr = list(b[o + 32:o + 40]), list(b[o + 40:o + 48])
        r = dict(zip(h, body[i]))
        t_ids = [int(r[f"ID{k}"] or 0) for k in range(8)]
        t_den = [int(r[f"DENSITY{k}"] or 0) for k in range(8)]
        t_pr = [int(r[f"PROB{k}"] or 0) for k in range(8)]
        t_sw = (int(r["SHRINES"] or 0), int(r["WELLS"] or 0))
        if (list(ids), den, pr, t_sw) != (t_ids, t_den, t_pr, (b[o + 48], b[o + 49])):
            bad += 1
            print("objgroup row", i, "differs", ids, t_ids)
    print(f"objgroup: txt {len(body)} rows, bin {n} records, {bad} differ")
    ob = (d / "objects.bin").read_bytes()
    on = struct.unpack_from("<I", ob)[0]
    orows = txt(d, "objects")[1:]
    rec = [r for r in orows if r[0] != "Expansion"]
    print(f"objects: txt {len(orows)} lines, {len(orows) - len(rec)} 'Expansion' separator, {len(rec)} records; bin {on} records "
          f"({(len(ob) - 4) / on:g} bytes each)")
    return 1 if bad or on != len(rec) else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
