"""Checks of the HD UI output (no game run): the mod's DC6 pictures, grid sizes against D2R's, the layouts, the sprites.

  py -3 -I tools/ui_check.py          exit 1 on any problem; notes (not failures) are printed too
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dc6  # noqa: E402
import skill_tree_art  # noqa: E402
import ui_art  # noqa: E402
import ui_layouts  # noqa: E402
import ui_panels  # noqa: E402
from icon_paths import read_tsv  # noqa: E402
from ui_paths import BASE_UI, EXCEL, HD_OUT, LAYOUT_OUT, MOD_UI, PAL, STRINGS_OUT  # noqa: E402

PANEL_DC6 = {"invchar6.dc6": 2, "supertransmogrifier.dc6": 1, "tradestash.dc6": 1}
# untouched D2R layouts whose cellCount must equal the mod's table: layout -> [(table row, occurrence of "cellCount")]
UNTOUCHED = {"bankexpansionlayouthd.json": [("Big Bank Page 1", 0)],
             "tradelayouthd.json": [("Trade Page 1", 0), ("Trade Page 2", 1)],
             "vendorpanellayouthd.json": [("Monster", 0)]}
GRIDS = ("gridX", "gridY")
# the migrated tables (tools/txt_migrate.py output; both banks), checked when they exist
BUILT = Path(__file__).resolve().parent.parent / "work" / "mod" / "data" / "global" / "excel"
# panel -> (inventory.txt row, layouts that draw it); the "2" rows (800x600) carry the same sizes
PANELS = {"Player inventory": ("Amazon", ("playerinventoryoriginallayouthd.json", "playerinventoryexpansionlayouthd.json",
                                          "playerinventoryoriginallayout.json", "playerinventoryexpansionlayout.json")),
          "Horadric Cube": ("Transmogrify Box Page 1", ("horadriccubelayouthd.json", "horadriccubelayout.json")),
          "Personal stash": ("Big Bank Page 1", ("bankexpansionlayouthd.json", "bankexpansionlayout.json")),
          "Shared stash tab": ("Big Bank Page 1", ("bankexpansionlayouthd.json", "bankexpansionlayout.json")),
          "Classic bank (no expansion)": ("Bank Page 1", ("bankoriginallayouthd.json", "bankoriginallayout.json")),
          "Trade (each side)": ("Trade Page 1", ("tradelayouthd.json",)),
          "Vendor": ("Monster", ("vendorpanellayouthd.json",))}


def grid_dims(path: Path) -> dict[str, tuple[int, int]]:
    head, rows = read_tsv(path)
    return {r[0]: (int(r[head.index("gridX")]), int(r[head.index("gridY")])) for r in rows
            if r[0] and r[head.index("gridX")].lstrip("-").isdigit()}


def cell_counts(text: str) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in re.findall(r'"cellCount":\s*\{\s*"x":\s*(\d+),\s*"y":\s*(\d+)', text)]


def check_dc6(pal) -> tuple[list[str], list[str]]:
    """Frame structure of the mod's UI pictures (tile sizes included)."""
    problems, notes = [], []
    files = {f"spells/skltree_{l}_back.dc6": 4 for _p, l, _k in skill_tree_art.CLASSES.values()}
    files.update({f"panel/{n}": c for n, c in PANEL_DC6.items()})
    for rel, sets in files.items():
        try:
            got = len(ui_art.panel_sets(MOD_UI / rel, pal))
        except (OSError, ValueError) as e:
            problems.append(f"{rel}: {e}")
            continue
        if got != sets:
            problems.append(f"{rel}: {got} sets, expected {sets}")
    notes.append(f"{len(files)} mod UI DC6 checked (4-tile sets of 320x432)")
    return problems, notes


def check_tables() -> tuple[list[str], list[str]]:
    """The mod's grid sizes against D2R's (the table is what the game server uses) and against the layouts."""
    problems, notes = [], []
    mod, d2r = grid_dims(EXCEL / "inventory.txt"), grid_dims(BASE_UI / "excel" / "inventory.txt")
    for name in sorted(set(mod) | set(d2r)):
        if name not in mod:
            notes.append(f"inventory.txt row '{name}' is D2R's only (mod lacks it): {d2r[name][0]}x{d2r[name][1]}")
        elif name not in d2r:
            notes.append(f"inventory.txt row '{name}' is the mod's only: {mod[name][0]}x{mod[name][1]}")
        elif mod[name] != d2r[name] and not name.endswith("2"):
            notes.append(f"grid '{name}': mod {mod[name][0]}x{mod[name][1]}, D2R {d2r[name][0]}x{d2r[name][1]}")
    # the generated layouts and the untouched ones agree with the table
    expect = {"playerinventoryoriginallayouthd.json": [mod["Amazon"]], "playerinventoryexpansionlayouthd.json": None,
              "horadriccubelayouthd.json": [mod["Transmogrify Box Page 1"]],
              "playerinventoryoriginallayout.json": [mod["Amazon"]], "horadriccubelayout.json": [mod["Transmogrify Box Page 1"]]}
    for name, want in expect.items():
        if want is None:
            continue
        got = cell_counts((LAYOUT_OUT / name).read_text("utf-8")) if (LAYOUT_OUT / name).exists() else []
        if [g for g in got][:1] != want:
            problems.append(f"{name}: grid {got[:1]}, table {want}")
    for name, rows in UNTOUCHED.items():
        p = BASE_UI / "layouts" / name
        if not p.exists():
            notes.append(f"{name}: not in the baseline, grid not compared")
            continue
        counts = cell_counts(p.read_text("utf-8"))
        for row, n in rows:
            if n >= len(counts) or counts[n] != mod[row]:
                problems.append(f"{name}: cellCount #{n} {counts[n:n + 1]} differs from the mod's '{row}' {mod[row]}")
    # the six player rows share every number the layouts use
    head, rows = read_tsv(EXCEL / "inventory.txt")
    players = [r for r in rows if r[0] in ("Amazon", "Sorceress", "Necromancer", "Paladin", "Barbarian", "Druid", "Assassin")]
    if len({tuple(r[1:]) for r in players}) != 1:
        problems.append("the seven classic player rows of inventory.txt differ from each other")
    else:
        notes.append("the seven classic player rows of inventory.txt are identical")
    return problems, notes


def larger(mod: tuple[int, int] | None, d2r: tuple[int, int] | None) -> tuple[int, int] | None:
    """The owner's rule (2026-10-28): per panel the grid with more cells, D2R's on a tie or when the mod lacks the row."""
    if mod is None or d2r is None:
        return d2r or mod
    return mod if max(mod[0], 0) * max(mod[1], 0) > max(d2r[0], 0) * max(d2r[1], 0) else d2r


def panel_choices(mod: dict[str, tuple[int, int]], d2r: dict[str, tuple[int, int]]) -> list[tuple[str, str, str, str]]:
    """(panel, Median, D2R, chosen) per panel, for docs/hd-ui.md."""
    fmt = lambda g: f"{g[0]} x {g[1]}" if g else "-"  # noqa: E731
    out = []
    for panel, (row, _layouts) in PANELS.items():
        m, d = mod.get(row), d2r.get(row)
        c = larger(m, d)
        out.append((panel, fmt(m), fmt(d), f"{fmt(c)} ({'Median' if c == m and c != d else 'D2R'})"))
    return out


def check_built(built: Path = BUILT) -> tuple[list[str], list[str]]:
    """The migrated inventory.txt of both banks: every row holds the larger grid, Warlock rows the Assassin's, and the
    layouts the mod ships (or D2R's own) draw the table's size."""
    problems, notes = [], []
    if not (built / "inventory.txt").exists():
        return problems, [f"{built}: no migrated inventory.txt, built tables not checked"]
    mod, d2r = grid_dims(EXCEL / "inventory.txt"), grid_dims(BASE_UI / "excel" / "inventory.txt")
    for bank in ("", "base"):
        p = built / bank / "inventory.txt"
        if not p.exists():
            continue
        got = grid_dims(p)
        for name, size in got.items():
            want = larger(mod.get(name.replace("Warlock", "Assassin")), d2r.get(name))
            if want is not None and size != want:
                problems.append(f"{bank or 'rotw'} inventory.txt '{name}': {size}, expected the larger grid {want}")
        for panel, (row, layouts) in PANELS.items():
            for name in layouts:
                lp = next((d / name for d in (built.parent / "ui" / "layouts", LAYOUT_OUT, BASE_UI / "layouts")
                           if (d / name).exists()), None)
                if lp is None:
                    continue
                counts = cell_counts(lp.read_text("utf-8"))
                if counts and row in got and counts[0] != got[row]:
                    problems.append(f"{panel}: {name} draws {counts[0]}, {bank or 'rotw'} inventory.txt '{row}' {got[row]}")
    notes += [f"{p}: Median {m}, D2R {d} -> {c}" for p, m, d, c in panel_choices(mod, d2r)]
    return problems, notes


def check_layouts() -> tuple[list[str], list[str]]:
    problems, notes = [], []
    for p in sorted(LAYOUT_OUT.glob("*.json")):
        text = p.read_text("utf-8")
        if text.count("{") != text.count("}") or text.count("[") != text.count("]"):
            problems.append(f"{p.name}: unbalanced brackets")
        for ref in re.findall(r'PANEL\\\\mxl\\\\(\w+)"', text):
            if not (HD_OUT / "panel" / "mxl" / f"{ref}.sprite").exists():
                problems.append(f"{p.name}: PANEL\\mxl\\{ref} has no sprite")
        for m in re.finditer(r'"rect":\s*\{([^}]*)\}', text):
            for v in re.findall(r'"(?:x|y)":\s*(-?\d+)', m.group(1)):
                if abs(int(v)) > 2000:
                    problems.append(f"{p.name}: rect value {v} off the panel")
    notes.append(f"{len(list(LAYOUT_OUT.glob('*.json')))} layouts checked")
    return problems, notes


def check_sprites() -> tuple[list[str], list[str]]:
    problems, notes = [], []
    n = 0
    tree_dir = HD_OUT / "spells" / "skill_trees"
    for _cls, (prefix, _l, _k) in skill_tree_art.CLASSES.items():
        for suffix, (fw, fh, stride) in ((".sprite", (895, 1169, 897)), (".lowend.sprite", (447, 584, 449))):
            p = tree_dir / f"{prefix}skilltree{suffix}"
            try:
                info = dc6.sprite_info(p)
            except (OSError, ValueError) as e:
                problems.append(f"{p.name}: {e}")
                continue
            n += 1
            want = {"frames": 3, "frame_width": fw, "height": fh, "strip_width": stride * 3}
            bad = {k: (info[k], v) for k, v in want.items() if info[k] != v}
            if bad or info["file_size"] != 40 + info["strip_width"] * info["height"] * 4:
                problems.append(f"{p.name}: {bad or 'size'}")
            else:
                frames = ui_art.read_sprite(p)
                for i, f in enumerate(frames):
                    if f.crop((0, 0, fw, 90)).getchannel("A").getbbox() is None:
                        problems.append(f"{p.name}: frame {i} has no tab strip")
                    if f.crop((0, 100, fw, fh)).getchannel("A").getbbox() is None:
                        problems.append(f"{p.name}: frame {i} has no sockets")
    for name in ui_panels.PANELS:
        for suffix, (w, h) in ((".sprite", (1162, 1507)), (".lowend.sprite", (581, 753))):
            p = HD_OUT / "panel" / "mxl" / f"{name}{suffix}"
            try:
                info = dc6.sprite_info(p)
            except (OSError, ValueError) as e:
                problems.append(f"{p.name}: {e}")
                continue
            n += 1
            if (info["frame_width"], info["strip_width"], info["height"], info["frames"]) != (w, w, h, 1) \
                    or info["file_size"] != 40 + w * h * 4:
                problems.append(f"{p.name}: {info}")
    notes.append(f"{n} sprites checked")
    return problems, notes


def check_trees() -> tuple[list[str], list[str]]:
    problems, notes = [], []
    trees = skill_tree_art.load_trees()
    for cls in skill_tree_art.CLASSES:
        pages = trees.get(cls, {})
        if sorted(pages) != [1, 2, 3]:
            problems.append(f"{cls}: pages {sorted(pages)}, expected 1-3")
        for page, cells in pages.items():
            at = list(cells.values())
            if len(set(at)) != len(at):
                problems.append(f"{cls} page {page}: two skills share a cell")
            for r, c in at:
                if not (0 <= r < skill_tree_art.GRID_ROWS and 0 <= c < skill_tree_art.GRID_COLS):
                    problems.append(f"{cls} page {page}: cell {(r, c)} outside the 3x6 grid")
    cols = {c for pages in trees.values() for cells in pages.values() for _r, c in cells.values()}
    notes.append(f"skills on the trees: {sum(len(c) for p in trees.values() for c in p.values())}, columns used {sorted(cols)}")
    if (STRINGS_OUT / "skill_tab_titles.json").exists():
        recs = json.loads((STRINGS_OUT / "skill_tab_titles.json").read_text("utf-8"))
        if len(recs) != 21 or len({r["Key"] for r in recs}) != 21:
            problems.append("skill_tab_titles.json: expected 21 distinct keys")
    else:
        problems.append("skill_tab_titles.json missing")
    return problems, notes


def main() -> int:
    pal = ui_art.palette(PAL)
    problems = []
    for name, fn in (("mod DC6", lambda: check_dc6(pal)), ("tables", check_tables), ("built tables", check_built),
                     ("skill trees", check_trees),
                     ("layouts", check_layouts), ("sprites", check_sprites)):
        p, notes = fn()
        print(f"== {name}: {len(p)} problems")
        for line in notes:
            print(f"   {line}")
        for line in p:
            print(f"   PROBLEM {line}")
        problems += p
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
