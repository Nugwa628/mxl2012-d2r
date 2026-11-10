"""CharmInv's tables for Median XL 2012 (Dimentio's D2RLoader plugin, bundled: docs/bundled-plugins.md "CharmInv").

CharmInv (`d2rl-charm-inv.dll` + `d2rl-charm-inv.mpq`, plugin id `charm-inv`) owns D2RLoader's one custom player page (item
page 6 of the .d2s) and shows it as a "Charm Inventory" panel. Two plugin tables (D2RLoader CustomTableService, RotW bank
only) set it up; its companion MPQ has the vanilla defaults (10 x 4, item type `char`). A mod overrides a plugin table by
the same virtual path in its own data (mod -> plugin -> base), so this step writes ours into the mod:

  data/global/excel/d2rloader/charm-inv/charminv.txt       Id gridX gridY: one row `charm-inv` (the grid, 1-16 each)
  data/global/excel/d2rloader/charm-inv/charminvtypes.txt  itemType: the item types the panel admits

The admitted types are every item type of the built itemtypes.txt whose Equiv1 / Equiv2 chain reaches `char`, the type
D2R's charm rule tests (a charm's stats count only while it sits where charms work). In Median XL 2012 that is `char`,
D2R's `scha` / `mcha` / `lcha` (no Median item uses them), `csch` (Sunder charms, none in Median), `grtz` (the trophies,
uniques and quest charms: Optical Detector, Sunstones, Jolly Roger ...), `araa`-`arag` (the class challenge rewards) and
`summ` (the Scroll of Summoning). Jewels (`jewl`, `cjwl`: Equiv `sock`) are not charms in Median and stay out. CharmInv
gives the item policy the exact type and its parents, so `char` alone would do; the full list keeps the panel right if a
future D2RLoader compares the exact type only. The grid stays at the plugin's 10 x 4: its HD panel art
(`charminv_bg.sprite`) draws exactly that many cells.

The files are strict TSV (D2RLoader: header with every column, LF line ends, final LF, printable ASCII).

  py -3 -I tools/charm_inv.py apply [--mod work/mod]    write both tables (build.py data step, idempotent)
  py -3 -I tools/charm_inv.py show  [--mod work/mod]    print the admitted types
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "work" / "mod"
PLUGIN_ID = "charm-inv"
TABLE_DIR = Path("data") / "global" / "excel" / "d2rloader" / PLUGIN_ID  # RotW bank (the plugin registers no base bank)
GRID = (10, 4)  # the plugin's own size: its panel art has 10 x 4 cells
CHARM = "char"


def read_tsv(path: Path) -> list[dict]:
    lines = path.read_text("utf-8-sig").splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln.strip()]


def charm_types(rows: list[dict]) -> list[str]:
    """The codes whose Equiv1 / Equiv2 chain reaches `char` (itself included), in itemtypes.txt order."""
    parents = {r.get("Code", ""): [r.get("Equiv1", ""), r.get("Equiv2", "")] for r in rows if r.get("Code")}

    def is_charm(code: str, seen: frozenset = frozenset()) -> bool:
        if code == CHARM:
            return True
        if code in seen or code not in parents:
            return False
        return any(is_charm(p, seen | {code}) for p in parents[code] if p)

    out = []
    for r in rows:
        code = r.get("Code", "")
        if code and code not in out and is_charm(code):
            out.append(code)
    return out


def check_code(code: str) -> None:
    if not 1 <= len(code) <= 4 or not all(33 <= ord(c) < 127 for c in code):
        raise SystemExit(f"item type {code!r} cannot go into charminvtypes (1-4 printable non-blank ASCII characters)")


def tables(types: list[str], grid: tuple = GRID) -> dict[str, str]:
    """{file name: text} of both tables."""
    if not types:
        raise SystemExit("no charm item types found (itemtypes.txt without `char`?)")
    for c in types:
        check_code(c)
    if not all(1 <= n <= 16 for n in grid):
        raise SystemExit(f"grid {grid} out of range (D2S coordinates: 1-16)")
    return {"charminv.txt": "Id\tgridX\tgridY\n%s\t%d\t%d\n" % (PLUGIN_ID, grid[0], grid[1]),
            "charminvtypes.txt": "itemType\n" + "".join(c + "\n" for c in types)}


def apply(mod: Path) -> list[str]:
    types = charm_types(read_tsv(mod / "data" / "global" / "excel" / "itemtypes.txt"))
    out = mod / TABLE_DIR
    out.mkdir(parents=True, exist_ok=True)
    for name, text in tables(types).items():
        (out / name).write_bytes(text.encode("ascii"))
    return types


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("apply", "show"))
    ap.add_argument("--mod", type=Path, default=MOD)
    a = ap.parse_args()
    if a.cmd == "show":
        print(" ".join(charm_types(read_tsv(a.mod / "data" / "global" / "excel" / "itemtypes.txt"))))
        return 0
    types = apply(a.mod)
    print(f"charm_inv: {GRID[0]} x {GRID[1]}, {len(types)} item types ({' '.join(types)}) -> {a.mod / TABLE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
