"""Compare the value sets of engine-dispatch columns (function ids, calc codes) between a mod's TXT tables and a
baseline (read-only). A mod value outside the baseline's set means either an engine change or reuse of an id the
baseline does not use in its rows (both need a look).

Usage: py -3 -I tools/func_ranges.py <mod-excel-dir> <baseline-excel-dir>
"""
import sys
from pathlib import Path

COLS = {
    "skills": ["srvstfunc", "srvdofunc", "srvprgfunc1", "srvprgfunc2", "srvprgfunc3", "cltstfunc", "cltdofunc",
               "cltprgfunc1", "cltprgfunc2", "cltprgfunc3", "prgcalc1", "aurastat1", "passivestat1", "restrict",
               "ItemTarget", "ItemCltEffect", "ItemEffect", "SrvMissileA", "ItemCastSound"],
    "missiles": ["pCltDoFunc", "pCltHitFunc", "pSrvDoFunc", "pSrvHitFunc", "pSrvDmgFunc", "CollideType"],
    "itemstatcost": ["descfunc", "dgrpfunc", "op", "Encode"],
    "properties": ["func1", "func2", "func3", "func4", "func5", "func6", "func7"],
    "skilldesc": ["descline1", "dsc2line1", "dsc3line1"],
    "monstats": ["AI"],
    "monstats2": [],
    "states": ["setfunc", "remfunc", "cltevent", "cltactivefunc", "srvactivefunc"],
    "objects": ["OperateFn", "PopulateFn", "InitFn", "ClientFn"],
    "misc": ["pSpell", "spelldescfunc"],
    "gems": [],
    "levels": ["LevelType", "DrlgType"],
    "lvltypes": [],
    "pettype": ["group"],
}


def read(p: Path):
    if not p.exists():
        return None, []
    lines = p.read_bytes().decode("latin-1").splitlines()
    hdr = lines[0].split("\t")
    return hdr, [ln.split("\t") for ln in lines[1:] if ln.strip()]


def values(hdr, rows, col):
    lower = [h.lower() for h in hdr]
    if col.lower() not in lower:
        return None
    i = lower.index(col.lower())
    return {r[i].strip() for r in rows if i < len(r) and r[i].strip()}


def as_num(v):
    try:
        return int(v)
    except ValueError:
        return None


def main():
    mod, base = Path(sys.argv[1]), Path(sys.argv[2])
    print("table\tcolumn\tmod_distinct\tmod_max\tbase_max\tnot_in_baseline")
    for t, cols in COLS.items():
        mh, mr = read(mod / f"{t}.txt")
        bh, br = read(base / f"{t}.txt")
        if mh is None or bh is None:
            continue
        for c in cols:
            mv, bv = values(mh, mr, c), values(bh, br, c)
            if mv is None:
                continue
            bv = bv or set()
            new = sorted(mv - bv, key=lambda v: (as_num(v) is None, as_num(v) or 0, v))
            mn = [as_num(v) for v in mv if as_num(v) is not None]
            bn = [as_num(v) for v in bv if as_num(v) is not None]
            print(f"{t}\t{c}\t{len(mv)}\t{max(mn) if mn else ''}\t{max(bn) if bn else ''}\t"
                  f"{len(new)}: {', '.join(new[:30])}{' ...' if len(new) > 30 else ''}")


if __name__ == "__main__":
    main()
