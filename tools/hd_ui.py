"""HD UI pipeline driver (phase 5, the 2D UI part): skill tree pages, inventory and cube panels, their layouts.

  py -3 -I tools/hd_ui.py baseline <a D2R 93847 extraction>   copy the D2R baseline pieces we read into work/d2r-baseline
                                                                (read-only source: an extraction of D2R 93847)
  py -3 -I tools/hd_ui.py build                                  skill trees -> panels -> layouts -> check (about 1 min)
  py -3 -I tools/hd_ui.py check                                  only the check

The mod side is read from <R>/mxl2012-runs/extract-mpq (MXL2012_EXTRACT overrides); everything is written to work/hd-ui (ignored).
Needs Pillow. See docs/hd-ui.md.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_paths import BASE, BASE_UI, PAL  # noqa: E402

LAYOUTS = ("playerinventoryoriginallayout", "playerinventoryexpansionlayout", "horadriccubelayout")
CHECK_LAYOUTS = ("bankexpansionlayouthd", "tradelayouthd", "vendorpanellayouthd")  # only read by the check (grid sizes)
CLASSIC_LAYOUTS = ("skillstreepanel",)  # classic only (ui_layouts.skilltree_classic, bug #33)
CLASS_PREFIXES = ("am", "so", "ne", "pa", "ba", "dr", "as")


def baseline(src: Path) -> int:
    """Copies the layouts, skill tree sprites, inventory.txt and the units palette of a D2R extraction."""
    src = Path(src)
    jobs = [(src / "data" / "global" / "palette" / "units" / "pal.dat", PAL),
            (src / "data" / "global" / "excel" / "inventory.txt", BASE_UI / "excel" / "inventory.txt")]
    for name in LAYOUTS:
        for suffix in ("", "hd"):
            jobs.append((src / "data" / "global" / "ui" / "layouts" / f"{name}{suffix}.json",
                         BASE_UI / "layouts" / f"{name}{suffix}.json"))
    for name in CHECK_LAYOUTS + CLASSIC_LAYOUTS:
        jobs.append((src / "data" / "global" / "ui" / "layouts" / f"{name}.json", BASE_UI / "layouts" / f"{name}.json"))
    for p in CLASS_PREFIXES:
        jobs.append((src / "data" / "hd" / "global" / "ui" / "spells" / "skill_trees" / f"{p}skilltree.sprite",
                     BASE_UI / "spells" / "skill_trees" / f"{p}skilltree.sprite"))
    for a, b in jobs:
        b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a, b)
    print(f"baseline: {len(jobs)} files -> {BASE}")
    return 0


def build() -> int:
    import skill_tree_art
    import ui_check
    import ui_layouts
    import ui_panels
    rc = 0
    for name, mod in (("skill trees", skill_tree_art), ("panels", ui_panels), ("layouts", ui_layouts)):
        print(f"== {name}")
        rc |= mod.main([])
    print("== check")
    return rc | ui_check.main()


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "baseline":
        return baseline(Path(argv[1]))
    if argv == ["build"]:
        return build()
    if argv == ["check"]:
        import ui_check
        return ui_check.main()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
