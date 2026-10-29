"""List duplicate keys (case-insensitive) in the built tables of the indexed entities (work/mod, both banks).
A mod row whose key equals the key of a D2R row kept at another ID makes name references ambiguous."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import idmap  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "work" / "mod" / "data" / "global" / "excel"
EXTRA = {"skilldesc": ("skilldesc", "skilldesc"), "itemtypes": ("itemtypes", "Code"), "treasureclassex": ("treasureclassex", "Treasure Class")}


def main() -> int:
    n = 0
    for bank in ("base", ""):
        for ent, (table, key) in [(e, (e, x.key)) for e, x in idmap.ENTITIES.items()] + list(EXTRA.items()):
            p = OUT / bank / f"{table}.txt"
            if not p.exists():
                continue
            lines = p.read_text("utf-8").splitlines()
            h = lines[0].split("\t")
            col = key
            k = h.index(col) if col in h else 0
            keys = [l.split("\t")[k] for l in lines[1:] if l and not l.startswith("Expansion") and len(l.split("\t")) > k]
            dup = {a: c for a, c in Counter(x.lower() for x in keys if x).items() if c > 1}
            if dup:
                n += len(dup)
                print(bank or "rotw", ent, len(dup), list(dup)[:10])
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
