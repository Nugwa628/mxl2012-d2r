"""Median's edits of D2R's own maps under a path of their own (bug #525, docs/maps-hd.md "Edited D2R maps").

D2R reads a preset's .ds1 at a path its CASC holds from the CASC, not from the mod: Hole Level 2 (lvlprest `Act1/Caves/
CaveRoom4.ds1`) was built from D2R's own caveroom4 in both graphics modes (the harness `presets` spots are D2R's map's,
check `hole2_room`), while the mod's HD scene for that path was made for Median's room, so HD drew no walls. A map at a path
only the mod has (Median's own maps, `expansion/...`) loads from the mod. So every .ds1 of the mod whose path D2R also has and
whose bytes differ moves to `mxl2012/<path>`:

- the .ds1 itself: data/global/tiles/<path> -> data/global/tiles/mxl2012/<path> (the old copy goes: D2R never reads it);
- the lvlprest File1..File6 cells naming it, in every lvlprest.txt of the mod (excel and excel/base), keep their case;
- its HD scene (D2R takes it from the .ds1 path: data/hd/env/preset/<path without .ds1>.json): the mod's own scene moves
  along (tools/walls_hd.py, tools/maps_hd.py); a map on D2R's scene gets a copy of D2R's json, which names its terrain
  (preset/<path>/terrain.model) by its full D2R path, so that still loads.

Runs after the steps that write tiles and scenes (maps_hd, walls_hd, legacy_art), before validate. A .ds1 equal to D2R's
stays where it is (D2R's copy is the same map).

  py -3 tools/ds1_paths.py build [--mod work/mod/data] [--d2r <D2R extract with filelist.txt>]
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402,F401
import fxpaths  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MOD_DATA = ROOT / "work" / "mod" / "data"
PREFIX = "mxl2012"  # the folder below data/global/tiles (and data/hd/env/preset) that only the mod has
LVLPREST = ("global/excel/lvlprest.txt", "global/excel/base/lvlprest.txt")
FILE_COLUMNS = tuple("File%d" % i for i in range(1, 7))


def d2r_paths(filelist: Path) -> set[str]:
    """The lower-case `data/...` paths of D2R's filelist.txt (`data:` entries)."""
    out = set()
    for line in filelist.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("data:"):
            out.add(line[5:].strip().lower())
    return out


def shadowed(mod_data: Path, d2r: Path, paths: set[str]) -> list[str]:
    """Tile paths (below data/global/tiles, lower case, with .ds1) of the mod's .ds1 files that D2R has at the same path
    with other bytes. Already moved ones (under PREFIX) are not looked at."""
    tiles = mod_data / "global" / "tiles"
    out = []
    for p in sorted(tiles.rglob("*")):
        if p.suffix.lower() != ".ds1" or not p.is_file():
            continue
        rel = p.relative_to(tiles).as_posix().lower()
        if rel.split("/")[0] == PREFIX or "data/global/tiles/" + rel not in paths:
            continue
        theirs = d2r / "data" / "global" / "tiles" / rel
        if theirs.exists() and theirs.read_bytes() == p.read_bytes():
            continue
        out.append(rel)
    return out


def rewrite_lvlprest(text: str, moved: set[str]) -> tuple[str, int]:
    """lvlprest.txt with every File cell that names a moved tile path (case-insensitive, either slash) prefixed by PREFIX/.
    Line endings and every other cell stay as they are. -> (text, cells changed)."""
    lines = text.split("\n")
    head = lines[0].rstrip("\r").split("\t")
    cols = [i for i, c in enumerate(head) if c in FILE_COLUMNS]
    changed = 0
    for n in range(1, len(lines)):
        line = lines[n]
        cr = line.endswith("\r")
        cells = (line[:-1] if cr else line).split("\t")
        hit = False
        for i in cols:
            if i < len(cells) and cells[i].replace("\\", "/").lower() in moved:
                cells[i] = PREFIX + "/" + cells[i].replace("\\", "/")
                changed += 1
                hit = True
        if hit:
            lines[n] = "\t".join(cells) + ("\r" if cr else "")
    return "\n".join(lines), changed


def scene_rel(tile_rel: str) -> str:
    """data/hd/env/preset/<tile path without .ds1>.json, the HD scene D2R takes for a .ds1 path."""
    return "hd/env/preset/" + tile_rel[:-4] + ".json"


def build(mod_data: Path, d2r: Path) -> int:
    paths = d2r_paths(d2r / "filelist.txt")
    todo = shadowed(mod_data, d2r, paths)
    report = []
    for rel in todo:
        src = mod_data / "global" / "tiles" / rel
        dst = mod_data / "global" / "tiles" / PREFIX / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        own = mod_data / scene_rel(rel)
        new = mod_data / scene_rel(PREFIX + "/" + rel)
        new.parent.mkdir(parents=True, exist_ok=True)
        if own.exists():
            os.replace(own, new)
            scene = "the mod's scene"
        else:
            import walls_hd
            data = walls_hd.d2r_bytes("data/" + scene_rel(rel))
            if data is None:
                raise SystemExit("ds1_paths: D2R has no HD scene data/%s for %s" % (scene_rel(rel), rel))
            new.write_bytes(data)
            scene = "D2R's scene copied"
        report.append("  %s -> %s/%s (%s)" % (rel, PREFIX, rel, scene))
    cells = 0
    moved = set(todo)
    for t in LVLPREST:
        p = mod_data / t
        if not p.exists():
            continue
        text, n = rewrite_lvlprest(p.read_bytes().decode("latin-1"), moved)
        if n:
            p.write_bytes(text.encode("latin-1"))
        cells += n
    print("ds1_paths: %d edited D2R maps moved under %s/, %d lvlprest File cells" % (len(todo), PREFIX, cells))
    print("\n".join(report))
    if todo and not cells:
        raise SystemExit("ds1_paths: moved maps but no lvlprest cell names them")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--mod", type=Path, default=MOD_DATA, help="the mod's data folder")
    b.add_argument("--d2r", type=Path, default=fxpaths.D2R, help="D2R 93847 extract with filelist.txt")
    a = ap.parse_args(argv)
    return build(a.mod, a.d2r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
