#!/usr/bin/env python
"""Walls no player can reach, kept off the automap (lanes hdmaps2, automapall; art step after every tile and scene writer).

Some of Median's maps have wall tiles standing in the void, far from any floor a player can walk on: Fauztinville's east
kerb runs 43 cells straight out into the black. The world draws them as thin lines nobody gets near, but the automap
draws every wall of a revealed room, so once automap_rows.py gives their key a row they show as long lines into nothing.
A row belongs to a tile key, not to a place, so those places get a key of their own: a copy of the same tile (same
pixels, same walk flags) under a free sequence number of the same style, appended to the tile set that holds it. The
copy has no automap row. The world looks exactly as before in both graphics modes, and the automap leaves those walls
out.

A wall counts as unreachable when no walkable floor (a floor tile with at least one walkable sub-tile) lies within
REACH cells and it is not next to a roof (building blocks are walkable only around them).

  python tools/automap_void.py find MAP                          list the unreachable walls (cells, keys)
  python tools/automap_void.py build MOD_DATA --plan PLAN [--map MAP ...]
      rewrite the .ds1 of the plan's maps that Median ships (automap_rows.py's automap_plan.json; D2R's own maps are never
      touched) and the tile sets in MOD_DATA. Only walls whose key got a new row in the plan move.
"""
import argparse
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401
import automap_render as ar  # noqa: E402
import automap_rows  # noqa: E402

REACH = 3
# maps whose room walls stand further from the floor they bound: Duncraig's thick front walls (the arcade faces on each
# room's south sides) stand 4-5 cells from the nearest floor, and with REACH 3 they read as void (lane automapall review:
# its rooms lost a whole side on the minimap). Beyond 6 cells its picks are real stubs into the void.
REACH_MAP = {"expansion/morework/epicwhiners": 6}
WALL_ORIENT = range(1, 13)         # wl .. co (automap_rows.WALL_CODES)
ROOF = 15
COUNT_AT, PTR_AT, HEAD = 0x10C, 0x110, 96


def _walkable(dt1_paths) -> dict:
    import dt1
    out = {}
    for p in dt1_paths:
        for t in dt1.parse_file(p):
            if t.orientation == 0:
                out[(t.main, t.sub)] = out.get((t.main, t.sub), False) or any((b & 1) == 0 for b in t.meta[40:65])
    return out


def find(ds, dt1_paths, reach: int = REACH) -> list:
    """[(x, y, wall layer, orientation, style, sequence)] of the unreachable walls of a map (no walkable floor within
    `reach` cells)."""
    from scipy import ndimage
    walk = _walkable(dt1_paths)
    W = np.zeros((ds.height, ds.width), bool)
    roof = np.zeros_like(W)
    for f in ds.floors():
        for y, x in zip(*np.nonzero(f)):
            c = int(f[y, x])
            if (c & 0xFF) and not (c >> 31) & 1 and walk.get(((c >> 20) & 0x3F, (c >> 8) & 0x3F), False):
                W[y, x] = True
    for j, w in enumerate(ds.walls()):
        roof |= ((w & 0xFF) != 0) & (ds.orientation(j) == ROOF)
    near = ndimage.binary_dilation(W, np.ones((3, 3), bool), reach)
    near |= ndimage.binary_dilation(roof, np.ones((3, 3), bool), 1)
    out = []
    for j, w in enumerate(ds.walls()):
        o = ds.orientation(j)
        for y, x in zip(*np.nonzero(w)):
            c = int(w[y, x])
            if (c & 0xFF) and not (c >> 31) & 1 and int(o[y, x]) in WALL_ORIENT and not near[y, x]:
                out.append((int(x), int(y), j, int(o[y, x]), (c >> 20) & 0x3F, (c >> 8) & 0x3F))
    return out


def add_tile(data: bytes, key: tuple, new_sub: int) -> bytes:
    """A .dt1 with one more tile: a copy of the tile `key` (orientation, main, sub; the first one) under sub `new_sub`,
    its block data copied to the end of the file."""
    count, ptr = struct.unpack_from("<ii", data, COUNT_AT)
    heads = [bytearray(data[ptr + i * HEAD:ptr + (i + 1) * HEAD]) for i in range(count)]
    src = next((bytes(h) for h in heads if struct.unpack_from("<iii", h, 20) == key), None)   # before the shift below
    if src is None:
        raise ValueError("tile %s not in this tile set" % (key,))
    end = ptr + count * HEAD
    for h in heads:                                   # every block pointer moves by the new header
        bptr = struct.unpack_from("<i", h, 72)[0]
        if bptr >= end:
            struct.pack_into("<i", h, 72, bptr + HEAD)
    bptr, blen = struct.unpack_from("<ii", src, 72)
    new = bytearray(src)
    struct.pack_into("<i", new, 28, new_sub)
    struct.pack_into("<i", new, 72, len(data) + HEAD)  # the copy of the blocks, at the new end
    out = bytearray(data[:COUNT_AT]) + struct.pack("<ii", count + 1, ptr) + data[PTR_AT + 4:ptr]
    out += b"".join(bytes(h) for h in heads) + bytes(new) + data[end:] + data[bptr:bptr + blen]
    return bytes(out)


def all_keys(mod_data: Path, info: dict) -> dict:
    """(orientation, main) -> the subs of every tile set there is (D2R's, Median's, the mod's): a copy's new key may not
    exist in any of them, or a level type listing that set and another holding the key would pick between the two."""
    import dt1
    roots = {Path(f["path"]).parents[len(Path(f["file"]).parts) - 1] for f in info["dt1_files"]}
    roots |= {ar.D2R / "global" / "tiles", mod_data / "global" / "tiles"}
    taken = defaultdict(set)
    for r in roots:
        for p in Path(r).rglob("*"):
            if p.suffix.lower() == ".dt1" and p.is_file():
                try:
                    ts = dt1.parse_file(p)
                except ValueError:                        # a few unused old-format sets (4.1) the game never loads
                    continue
                for t in ts:
                    taken[(t.orientation, t.main)].add(t.sub)
    return taken


def build(mod_data: Path, maps: list, plan: dict, log=print) -> dict:
    import dt1
    from hdkit.view.mapview import world
    from hdkit.view.mapview.ds1 import Ds1, make_cell
    report = {}
    shipped = set(world.Roots().maps("mod"))
    for key in maps:
        # the keys this map got rows for (a D2R map a Median level uses gets none: it stays D2R's)
        new_keys = {(c, int(st), int(sq)) for keys in plan["maps"].get(key, {}).get("keys", {}).values()
                    for c, st, sq in (k.split() for k in keys)}
        if key not in shipped or not new_keys:
            continue
        info = automap_rows.open_map(key).describe()
        ds1_path = mod_data / "global" / "tiles" / (key + ".ds1")
        if not ds1_path.is_file():
            ds1_path = next((p for p in (mod_data / "global" / "tiles").rglob("*.ds1")
                             if p.relative_to(mod_data / "global" / "tiles").as_posix().lower() == key + ".ds1"), None)
        if ds1_path is None:
            raise SystemExit("automap_void: %s.ds1 not in %s" % (key, mod_data))
        files = [(f["file"], mod_data / "global" / "tiles" / f["file"]) for f in info["dt1_files"]]
        files = [(n, p if p.is_file() else Path(f["path"])) for (n, p), f in zip(files, info["dt1_files"])]
        ds = Ds1.read(ds1_path)
        # only walls on a new row: a copy has none, so a second run leaves the first one's copies alone
        hits = [h for h in find(ds, [p for _n, p in files], REACH_MAP.get(key, REACH))
                if (ar.CODES[h[3]], h[4], h[5]) in new_keys]
        if not hits:
            report[key] = {"walls": 0}
            continue
        tiles = {n: dt1.parse_file(p) for n, p in files}
        taken = all_keys(mod_data, info)
        rekey, owner = {}, {}
        for _x, _y, _j, o, st, sq in hits:
            k = (o, st, sq)
            if k in rekey:
                continue
            n = next((n for n, ts in tiles.items() if any(t.key == k for t in ts)), None)
            free = [s for s in range(63, -1, -1) if s not in taken[(o, st)]]
            if n is None or not free:
                raise SystemExit("automap_void: %s: no tile set or no free sequence for %s" % (key, k))
            rekey[k] = free[0]
            taken[(o, st)].add(free[0])
            owner[k] = n
        for k, sub in rekey.items():
            n = owner[k]
            dst = mod_data / "global" / "tiles" / n
            data = add_tile((dst if dst.is_file() else dict(files)[n]).read_bytes(), k, sub)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
        for x, y, j, o, st, sq in hits:
            w = ds.layers[("wall", j)]
            w[y, x] = make_cell(st, rekey[(o, st, sq)], keep=int(w[y, x]), prop1=int(w[y, x]) & 0xFF,
                                hidden=bool(int(w[y, x]) >> 31 & 1))
        ds.write(ds1_path)
        report[key] = {"walls": len(hits), "keys": {"%s %d %d" % (ar.CODES[k[0]], k[1], k[2]): {
            "copy_sequence": v, "tile_set": owner[k]} for k, v in rekey.items()}}
        log("automap_void: %s: %d walls on %d new tile keys" % (key, len(hits), len(rekey)))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["find", "build"])
    ap.add_argument("target", help="find: a map; build: the mod's data folder")
    ap.add_argument("--map", action="append", default=None)
    ap.add_argument("--plan", default=None, help="automap_rows.py's automap_plan.json (build)")
    a = ap.parse_args(argv)
    if a.cmd == "find":
        src = automap_rows.open_map(a.target)
        hits = find(src.ds, [p for _rel, p in src.files if p is not None], REACH_MAP.get(a.target, REACH))
        print(json.dumps([{"cell": [x, y], "layer": j, "key": "%s %d %d" % (ar.CODES[o], st, sq)}
                          for x, y, j, o, st, sq in hits]))
        print("automap_void: %d unreachable walls" % len(hits), file=sys.stderr)
        return 0
    if not a.plan:
        ap.error("build needs --plan")
    plan = automap_rows.load_plan(a.plan)
    print(json.dumps(build(Path(a.target), a.map or sorted(plan["maps"]), plan,
                           log=lambda m: print(m, file=sys.stderr)), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
