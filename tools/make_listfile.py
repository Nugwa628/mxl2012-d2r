"""Build a candidate MPQ listfile for a classic D2 mod from known path sources (read-only on all of them).

Usage: py -3 -I tools/make_listfile.py <out.txt> [--manifest <mpq_extract manifest.json>]... [--tree <dir>]...
       [--extra <names.txt>]...

Sources: mpq_extract manifests ("files" keys), directory trees (paths relative to the tree's parent
of data/), and plain name lists. Each name is also written with .txt <-> .bin swapped for excel tables, and for
every directory seen, the standard classic table/palette/font names are added.
"""
import argparse
import json
from pathlib import Path

EXCEL = """armor arena armtype automagic automap belts bodylocs books charstats colors compcode composit cubemain
cubemod difficultylevels elemtypes events experience gamble gems hireling hitclass inventory itemratio itemstatcost
itemtypes levels lowqualityitems lvlmaze lvlprest lvlsub lvltypes lvlwarp magicprefix magicsuffix misc misscalc
missiles monai monequip monitempercent monlvl monmode monplace monpreset monprop monseq monsounds monstats monstats2
monumod montype npc objects objgroup objmode objtype overlay pettype playerclass plrmode plrtype properties qualityitems
rareprefix raresuffix runes setitems sets shrines skillcalc skilldesc skills soundenviron sounds states storepage
superuniques treasureclass treasureclassex uniqueappellation uniqueitems uniqueprefix uniquesuffix uniquetitle weapons
wanderingmon cubetype hiredesc""".split()


def add(names: set, n: str):
    n = n.replace("/", "\\").strip()
    if not n:
        return
    names.add(n)
    low = n.lower()
    if "\\excel\\" in low:
        if low.endswith(".txt"):
            names.add(n[:-4] + ".bin")
        elif low.endswith(".bin"):
            names.add(n[:-4] + ".txt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--manifest", action="append", default=[])
    ap.add_argument("--tree", action="append", default=[])
    ap.add_argument("--extra", action="append", default=[])
    a = ap.parse_args()
    names: set[str] = set()
    for m in a.manifest:
        for k in json.loads(Path(m).read_text(encoding="utf-8"))["files"]:
            add(names, k)
    for t in a.tree:
        root = Path(t)
        for p in root.rglob("*"):
            if p.is_file():
                add(names, p.relative_to(root).as_posix())
    for e in a.extra:
        for line in Path(e).read_text(encoding="latin-1").splitlines():
            add(names, line)
    for t in EXCEL:
        for ext in ("txt", "bin"):
            names.add(f"data\\global\\excel\\{t}.{ext}")
    dirs = {n.rsplit("\\", 1)[0] for n in names if "\\" in n}
    Path(a.out).write_text("\n".join(sorted(names)) + "\n", encoding="latin-1", errors="replace")
    print(f"{len(names)} names, {len(dirs)} dirs -> {a.out}")


if __name__ == "__main__":
    main()
