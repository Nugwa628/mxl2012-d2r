"""HD UI pipeline driver (phase 5, the 2D UI part): skill tree pages, inventory and cube panels, their layouts.

  py -3 -I tools/hd_ui.py baseline <a D2R 93847 extraction>   copy the D2R baseline pieces we read into work/d2r-baseline
                                                                (read-only source: an extraction of D2R 93847)
  py -3 -I tools/hd_ui.py build                                  skill trees (HD, gamepad, the Warlock's classic one) -> panels
                                                                 -> layouts -> check (about 1 min)
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
CONTROLLER_LAYOUTS = ("horadriccubelayouthd", "bankexpansionlayouthd",  # layouts/controller: ui_layouts (gamepad UI)
                      "skillstreepanelhd")                             # pad_skill_trees reads its geometry
CLASSIC_LAYOUTS = ("skillstreepanel",)  # classic only (ui_layouts.skilltree_classic, bug #33)
CLASS_PREFIXES = ("am", "so", "ne", "pa", "ba", "dr", "as")
STASH_ART_DIR = Path("panel") / "stash" / "additionalstash"
STASH_ART = ("panel_additionalstash_consumables",)  # D2R's Materials page: the base of the Gems / Runes pages (median_stash)


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
    for name in CONTROLLER_LAYOUTS:
        jobs.append((src / "data" / "global" / "ui" / "layouts" / "controller" / f"{name}.json",
                     BASE_UI / "layouts" / "controller" / f"{name}.json"))
    for name in [f"{p}skilltree" for p in CLASS_PREFIXES] + ["panel_skilltreebg"]:  # bg: lane skillhd's candidates
        jobs.append((src / "data" / "hd" / "global" / "ui" / "spells" / "skill_trees" / f"{name}.sprite",
                     BASE_UI / "spells" / "skill_trees" / f"{name}.sprite"))
    for prefix in CLASS_PREFIXES:  # the gamepad UI's trees: pad_skill_trees
        for suffix in ("", ".lowend"):
            jobs.append((src / "data" / "hd" / "global" / "ui" / "controller" / "panel" / "spells" / "v2" / f"{prefix}skilltree{suffix}.sprite",
                         BASE_UI / "controller" / "panel" / "spells" / "v2" / f"{prefix}skilltree{suffix}.sprite"))
    jobs.append((src / "data" / "hd" / "global" / "ui" / "spells" / "warlock" / "waskillicon.sprite",  # warlock_tree
                 BASE_UI / "spells" / "warlock" / "waskillicon.sprite"))
    for name in STASH_ART:
        jobs.append((src / "data" / "hd" / "global" / "ui" / STASH_ART_DIR / f"{name}.sprite",
                     BASE_UI / STASH_ART_DIR / f"{name}.sprite"))
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
    import pad_skill_trees
    import warlock_tree
    for name, mod in (("skill trees", skill_tree_art), ("controller skill trees", pad_skill_trees)):
        print(f"== {name}")
        rc |= mod.main([])
    print("== warlock classic tree")  # before the layouts (they take its Close button code), checked after them
    for line in warlock_tree.build():
        print(line)
    for name, mod in (("panels", ui_panels), ("layouts", ui_layouts)):
        print(f"== {name}")
        rc |= mod.main([])
    print("== warlock classic tree: check (with the served classic layout)")
    left = warlock_tree.check()
    for p in left:
        print(f"PROBLEM: {p}")
    rc |= 1 if left else 0
    print("== stash pages")
    import median_stash
    from rotw_stash_legacy import lenient_json
    from ui_art import read_sprite
    from ui_paths import HD_OUT
    d2r_layout = lenient_json((BASE_UI / "layouts" / "bankexpansionlayouthd.json").read_text("utf-8-sig"))
    materials = read_sprite(BASE_UI / STASH_ART_DIR / f"{STASH_ART[0]}.sprite")[0]
    for line in median_stash.build(d2r_layout, materials, HD_OUT / STASH_ART_DIR):
        print(line)
    print("== send to stash button")
    import send_stash
    from ui_paths import OUT_DATA
    for line in send_stash.art(OUT_DATA):
        print(line)
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
