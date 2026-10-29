"""HD icon pipeline driver (phase 5, the 2D sprite part): skill icon sheets and inventory item pictures.

  py -3 -I tools/hd_icons.py baseline <a D2R 93847 extraction>   copy the D2R baseline pieces we read into work/d2r-baseline
                                                                   (read-only source: an extraction of D2R 93847)
  py -3 -I tools/hd_icons.py build                                  skill sheets -> item sprites + maps -> both checks

The mod side is read from <R>/mxl2012-runs/extract-mpq (MXL2012_EXTRACT overrides); everything is written to work/hd (ignored).
See docs/hd-icons.md.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from icon_paths import BASE  # noqa: E402

EXCEL_TABLES = ("weapons", "armor", "misc", "uniqueitems", "setitems", "itemtypes")


def baseline(src: Path) -> int:
    """Copies filelist.txt, the item tables, HD item maps, the classic item DC6 and the units palette of a D2R extraction."""
    src = Path(src)
    jobs = [(src / "filelist.txt", BASE / "filelist.txt"),
            (src / "data" / "global" / "palette" / "units" / "pal.dat", BASE / "palette" / "pal.dat")]
    jobs += [(src / "data" / "global" / "excel" / f"{t}.txt", BASE / "excel" / f"{t}.txt") for t in EXCEL_TABLES]
    jobs += [(src / "data" / "hd" / "items" / f"{n}.json", BASE / "hd-items" / f"{n}.json") for n in ("items", "uniques", "sets")]
    jobs += [(p, BASE / "items" / p.name) for p in sorted((src / "data" / "global" / "items").glob("*.dc6"))]
    for a, b in jobs:
        b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a, b)
    print(f"baseline: {len(jobs)} files -> {BASE}")
    return 0


def build() -> int:
    import item_hd
    import item_icon_check
    import skill_icon_check
    import skill_icons
    rc = 0
    for name, mod in (("skill sheets", skill_icons), ("item sprites", item_hd), ("skill icon check", skill_icon_check),
                      ("item icon check", item_icon_check)):
        print(f"== {name}")
        rc |= mod.main()
    return rc


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "baseline":
        return baseline(Path(argv[1]))
    if argv == ["build"]:
        sys.argv = sys.argv[:1]  # the steps parse their own (empty) argument lists
        return build()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
