"""HD scenes of Median's maps from the D2R scenes their regions were copied from (docs/maps-hd-method.md).

A Median map on stock tiles is mostly a paste-up of D2R's own maps: whole presets or parts of them, tile for tile, at some
offset. D2R's artists built an HD scene for each of those maps by hand. This tool finds the copied regions (`find_regions`)
and moves everything D2R placed on them into the Median map's scene (`transplant`): walls, roofs, props, decals, terrain
stamps, lights, effects, visual data boxes, with their ids, fade targets and wall tile coordinates kept consistent, and
D2R's terrain mesh of each region's map as a plain entity (`ground_piece`): the pits, terraces and painted ground. A map
that is one D2R map at offset 0 takes D2R's scene whole, terrain included (`whole_source`). Cells that belong to no copied
region keep the entities of a fallback scene (the walls_hd / walls_scene one). `walk_check` compares what a scene draws with
the walkable sub-tiles of the map's tiles.

    py -3 -I tools/maps_transplant.py survey                 where each of the 17 maps comes from
    py -3 -I tools/maps_transplant.py build <map> --out DIR  the scene (work/maps_hd/transplant by default)
    py -3 -I tools/maps_transplant.py walk <map> [scene]     walkable area against drawn geometry
    py -3 -I tools/maps_transplant.py calibrate [keys]       the same numbers for D2R's own maps and scenes
"""
import argparse
import collections
import copy
import json
import math
import pickle
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401

import ds1_remap  # noqa: E402
import maps_floor  # noqa: E402
import maps_hd  # noqa: E402
import walls_hd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "maps_hd" / "transplant"
TILE = 10.0
SUB = 2.0                 # a sub-tile: 5 by 5 per tile
VOTE_MAX = 4000           # a cell signature on more D2R cells than this does not vote for an offset
VOTE_TOP = 400            # offsets verified per map
VOTE_MIN = 4
MIN_CELLS, MIN_WALLS = 20, 6   # a copied region with fewer cells and fewer wall cells is left to the fallback scene
WHOLE_SHARE = 0.97        # one D2R map at offset 0 on this share of the cells (and every wall cell): take its scene whole
BORDER = 1                # an entity on a cell without tiles belongs to a region within this many cells
PIECE_SHARE = 0.6         # a region with this share of its D2R map's cells takes that map's terrain mesh along
PIECE_LIFT = 0.05         # terrain pieces lie this far over the engine's ground plane, larger regions 0.01 higher each
TALL, LOW = 3.0, 1.0      # a model lower than TALL (or standing higher than LOW off the ground) does not block the way
THICK = 4.0               # nor does one wider than this both ways (a building with a room inside, a roof)
SHRINK = 0.5              # a model box is taken this much smaller on each side


# ---- cells ---------------------------------------------------------------------------------------------------------------
def full_cells(ds, paths, tiles_of, donor_of=lambda p: p):
    """{(x, y): (wall tiles, floor tiles)} of a .ds1, each tile as (stock tile set folder, orientation, style, sequence)."""
    walls = walls_hd.wall_cells(ds, walls_hd.wall_index(paths, tiles_of), donor_of)
    floors = walls_hd.floor_cells(ds, walls_hd.floor_index(paths, tiles_of), donor_of, ())
    return {xy: (walls.get(xy, ()), floors.get(xy, ())) for xy in set(walls) | set(floors)}


def components(cells):
    """Connected groups (4 neighbours) of a set of cells."""
    cells, out = set(cells), []
    while cells:
        stack = [cells.pop()]
        comp = set(stack)
        while stack:
            x, y = stack.pop()
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in cells:
                    cells.remove(n)
                    comp.add(n)
                    stack.append(n)
        out.append(comp)
    return out


class Region:
    """Cells of a Median map that equal the cells of D2R map `stock` at (x + dx, y + dy)."""

    def __init__(self, stock, dx, dy, cells, walls):
        self.stock, self.dx, self.dy, self.cells, self.walls = stock, dx, dy, set(cells), walls

    def __repr__(self):
        return "Region(%s, %d, %d, %d cells, %d walls)" % (self.stock, self.dx, self.dy, len(self.cells), self.walls)


def build_index(stock: dict):
    """signature -> [(stock map, x, y)] over {map: cells}."""
    index = collections.defaultdict(list)
    for key in sorted(stock):
        for (x, y), sig in stock[key].items():
            index[sig].append((key, x, y))
    return index


def find_regions(cells: dict, stock: dict, index=None, small=(2, 12)):
    """The copied regions of a map, largest first, every cell in at most one. Cells with walls (and rare floor cells) vote
    for (stock map, offset); the strongest offsets are verified cell by cell (walls and floors equal) and cut into connected
    regions; a region must keep `small[0]` wall cells or `small[1]` cells after larger ones took theirs."""
    index = index if index is not None else build_index(stock)
    votes = collections.Counter()
    for (x, y), sig in cells.items():
        cand = index.get(sig, ())
        if len(cand) > VOTE_MAX or (not sig[0] and len(cand) > VOTE_MAX // 10):
            continue
        for key, sx, sy in cand:
            votes[(key, sx - x, sy - y)] += 1
    found = []
    for (key, dx, dy), n in votes.most_common(VOTE_TOP):
        if n < VOTE_MIN and found:
            break
        sc = stock[key]
        match = [xy for xy, sig in cells.items() if sc.get((xy[0] + dx, xy[1] + dy)) == sig]
        for comp in components(match):
            w = sum(1 for xy in comp if cells[xy][0])
            if w >= small[0] or len(comp) >= small[1]:
                found.append((w, len(comp), key, dx, dy, comp))
    found.sort(key=lambda r: (-r[0], -r[1], r[2], r[3], r[4]))
    taken, out = set(), []
    for _w, _n, key, dx, dy, comp in found:
        for part in components(comp - taken):
            w = sum(1 for xy in part if cells[xy][0])
            if w >= small[0] or len(part) >= small[1]:
                taken |= part
                out.append(Region(key, dx, dy, part, w))
    return out


def big(regions, cells=MIN_CELLS, walls=MIN_WALLS):
    return [r for r in regions if len(r.cells) >= cells or r.walls >= walls]


def layout(cells: dict) -> dict:
    """The cells by their walls alone. Regions found on these are places where a mapper drew D2R's wall layout over floors
    of their own (Fauztinville has no copied region, but 37 pieces of Travincal's wall layout with 8 or more wall cells)."""
    return {xy: (sig[0], ()) for xy, sig in cells.items()}


def whole_source(cells: dict, regions, share=WHOLE_SHARE):
    """The D2R map whose scene fits the whole map: one region at offset 0 with every wall cell and `share` of all cells."""
    walls = sum(1 for s in cells.values() if s[0])
    for r in regions:
        if r.dx == 0 and r.dy == 0 and r.walls == walls and len(r.cells) >= share * len(cells):
            return r.stock
    return None


def coverage(cells: dict, regions) -> dict:
    walls = [xy for xy, s in cells.items() if s[0]]
    reg = big(regions)
    inb = set().union(*(r.cells for r in reg)) if reg else set()
    ina = set().union(*(r.cells for r in regions)) if regions else set()
    return {"cells": len(cells), "wall_cells": len(walls), "regions": len(reg), "sources": len({r.stock for r in reg}),
            "cells_in": len(inb), "walls_in": sum(1 for xy in walls if xy in inb), "walls_in_any": sum(1 for xy in walls if xy in ina),
            "whole": whole_source(cells, regions)}


# ---- entities --------------------------------------------------------------------------------------------------------------
def new_id(tag: str, old) -> int:
    return zlib.crc32(("%s:%s" % (tag, old)).encode()) or 1


def yaw_of(t) -> float:
    q = (t or {}).get("orientation") or {}
    return 2 * math.atan2(float(q.get("y", 0.0)), float(q.get("w", 1.0)))


def anchor(e, ground=None):
    """(x, z, g) of an entity: its position and the height of D2R's terrain under it. D2R's camera is orthographic along
    (-1, -1, -1), so a piece on ground raised by g stands at (x + g, y + g, z + g) to show over its tile: (x - g, z - g) is
    the tile it belongs to (walls_hd.wall_entities)."""
    t = walls_hd.transform(e)
    if not t:
        return None
    p = t.get("position", {})
    x, z = float(p.get("x", 0.0)), float(p.get("z", 0.0))
    return x, z, (ground.height(x, z) if ground is not None else 0.0)


def is_terrain(e) -> bool:
    return (e.get("name") == "terrain" or str(e.get("name", "")).startswith("ground_")
            or any(c.get("type") == "TerrainDefinitionComponent" for c in e.get("components", ())))


def ground_piece(scene: dict, tag: str, dx: int, dy: int, lift: float = PIECE_LIFT):
    """D2R's terrain of a map as a plain entity at a region's offset: the mesh D2R's artists modelled for that map (its
    pits, terraces and painted ground) and its floor physics, which units stand on. None for a scene without a terrain.
    The terrain component is left out: a preset has one terrain, and a Median map made of many D2R maps has none."""
    if not walls_hd.terrain_path(scene):
        return None
    e = copy.deepcopy(scene["terrain"])
    e["id"], e["name"] = new_id(tag, "terrain"), "ground_" + tag
    e["components"] = [c for c in e["components"] if c.get("type") != "TerrainDefinitionComponent"]
    p = walls_hd.transform(e).setdefault("position", {})
    p["x"] = round(float(p.get("x", 0.0)) - dx * TILE, 4)
    p["y"] = round(float(p.get("y", 0.0)) + lift, 4)
    p["z"] = round(float(p.get("z", 0.0)) - dy * TILE, 4)
    return e


def move(e, tag: str, dx: int, dy: int, drop: float = 0.0, ids=None):
    """A copy of a D2R entity for a region at offset (dx, dy): position moved by whole cells (and down the view axis by
    `drop`), a new id, fade and visual-box targets pointing at the new ids, wall tile coordinates moved along."""
    e = copy.deepcopy(e)
    e["id"] = new_id(tag, e.get("id"))
    for c in e.get("components", ()):
        kind = c.get("type")
        if kind == "TransformDefinitionComponent":
            p = c.setdefault("position", {})
            p["x"] = round(float(p.get("x", 0.0)) - dx * TILE - drop, 4)
            p["y"] = round(float(p.get("y", 0.0)) - drop, 4)
            p["z"] = round(float(p.get("z", 0.0)) - dy * TILE - drop, 4)
        elif kind == "WallTransparencyComponent":
            w = c.get("wallTileLocalCoord")
            if w and w.get("x", -1) >= 0 and w.get("y", -1) >= 0:
                w["x"], w["y"] = w["x"] - dx, w["y"] - dy
        if "targetId" in c and (ids is None or str(c["targetId"]) in ids):
            c["targetId"] = str(new_id(tag, c["targetId"]))
    return e


def transplant(region: Region, scene: dict, tag: str, ground=None, here=None, there=None, flat=True):
    """The entities D2R's scene has on a region, moved to the Median map. An entity belongs to the cell under it (terrain
    height taken out); one on a cell without tiles in both maps (stairs beside their tiles, pieces past the map edge)
    belongs to a region within BORDER cells. `here` / `there`: the cells of the Median and of the D2R map. With `flat`
    every entity is moved down the view axis by D2R's terrain height (the Median scene has no terrain of its own)."""
    out = []
    ids = {str(e.get("id")) for e in scene.get("entities", ())}
    for e in scene.get("entities", ()):
        a = anchor(e, ground)
        if a is None or is_terrain(e):
            continue
        x, z, g = a
        sx, sy = int((x - g) // TILE), int((z - g) // TILE)
        cell = (sx - region.dx, sy - region.dy)
        if cell not in region.cells:
            if (here is not None and cell in here) or (there is not None and (sx, sy) in there):
                continue
            if not any((cell[0] + ax, cell[1] + ay) in region.cells
                       for ax in range(-BORDER, BORDER + 1) for ay in range(-BORDER, BORDER + 1)):
                continue
        out.append(move(e, tag, region.dx, region.dy, g if flat else 0.0, ids))
    return out


def cell_of(e):
    a = anchor(e)
    return None if a is None else (int(a[0] // TILE), int(a[1] // TILE))


def keep_fallback(scene: dict, covered: set):
    """The fallback scene's entities on cells no region covers."""
    return [e for e in scene.get("entities", ()) if not is_terrain(e) and cell_of(e) not in covered]


def fits_piece(region: Region, cells: dict, there: dict, ground, step=0.5) -> bool:
    """Whether D2R's terrain mesh suits a region: the region is most of its D2R map, and wherever that map's ground is off
    level (a pit, a terrace) the Median map has the same cell or none. A mapper who redrew part of a pit gets no pit."""
    if not there or len(region.cells) < PIECE_SHARE * len(there):
        return False
    for sx, sy in there:
        cell = (sx - region.dx, sy - region.dy)
        if cell in region.cells or cell not in cells or ground is None:
            continue
        h = ground.height(sx * TILE + TILE / 2, sy * TILE + TILE / 2)
        if h is not None and abs(h) > step:
            return False
    return True


def merge_dependencies(scenes) -> dict:
    out = collections.OrderedDict()
    for s in scenes:
        for kind, items in (s.get("dependencies") or {}).items():
            have = out.setdefault(kind, [])
            seen = {i.get("path") for i in have}
            for i in items:
                if i.get("path") not in seen:
                    seen.add(i.get("path"))
                    have.append(i)
    return dict(out)


def compose(cells: dict, regions, fallback: dict, scene_of, ground_of=lambda key, scene: None, stock_cells=None, pieces=True,
            keep=big):
    """-> (scene, stats): the fallback scene with every big copied region replaced by D2R's own entities. With `pieces` a
    region that D2R's terrain suits (`fits_piece`) also takes that map's terrain mesh (`ground_piece`) and keeps D2R's
    heights; any other region is flattened onto the engine's ground plane. keep(regions) -> the regions to use."""
    regions = keep(regions)
    covered = set().union(*(r.cells for r in regions)) if regions else set()
    ents = keep_fallback(fallback, covered)
    stats = {"fallback_entities": len(ents), "regions": []}
    used, grounds, scenes = [fallback], {}, {}
    for n, r in enumerate(regions):
        if r.stock not in scenes:
            scenes[r.stock] = scene_of(r.stock)
            grounds[r.stock] = ground_of(r.stock, scenes[r.stock]) if scenes[r.stock] else None
        scene = scenes[r.stock]
        if not scene:
            continue
        there = (stock_cells or {}).get(r.stock)
        piece = None
        if pieces and fits_piece(r, cells, there, grounds[r.stock]):
            piece = ground_piece(scene, "r%d" % n, r.dx, r.dy, PIECE_LIFT + 0.01 * (len(regions) - n))
        got = transplant(r, scene, "r%d" % n, grounds[r.stock], cells, there, piece is None)
        ents += got + ([piece] if piece else [])
        used.append(scene)
        stats["regions"].append({"stock": r.stock, "dx": r.dx, "dy": r.dy, "cells": len(r.cells), "walls": r.walls,
                                 "entities": len(got), "terrain": piece is not None})
    ids = collections.Counter(e.get("id") for e in ents)
    for e in ents:                      # a fallback id that meets a transplanted one
        if ids[e.get("id")] > 1:
            ids[e["id"]] -= 1
            e["id"] = new_id("dup", "%s:%s" % (e["id"], ids[e["id"]]))
    out = dict(fallback)
    out["dependencies"] = merge_dependencies(used)
    out["entities"] = ents
    stats["entities"] = len(ents)
    stats["covered_cells"] = len(covered)
    return out, stats


# ---- walkable area against drawn geometry ---------------------------------------------------------------------------------
def tile_table(paths, tiles_of):
    """(orientation, style, sequence) -> Tile, the first file of the level type that has it."""
    out = {}
    for p in paths:
        for t in tiles_of(p) or ():
            out.setdefault(t.key, t)
    return out


def blocked_subtiles(ds, table, flip=0) -> set:
    """{(sub x, sub y)} of the map's sub-tiles a unit cannot walk on (flag bit 0 of any tile of the cell; `flip` 0-3 picks
    the sub-tile order inside a tile: bit 0 mirrors x, bit 1 mirrors y)."""
    out = set()

    def add(i, tile):
        if tile is None:
            return
        cx, cy = i % ds.width, i // ds.width
        for n, f in enumerate(tile.meta[40:65]):
            if f & 1:
                sx, sy = n % 5, n // 5
                out.add((cx * 5 + (4 - sx if flip & 1 else sx), cy * 5 + (4 - sy if flip & 2 else sy)))

    for lay in ds.floor_layers():
        for i, c in enumerate(lay):
            if c:
                add(i, table.get((0,) + ds1_remap.cell_key(c)))
    for lay, ori in ds.wall_layers():
        for i, (c, o) in enumerate(zip(lay, ori)):
            if c:
                add(i, table.get((o & 0xFF,) + ds1_remap.cell_key(c)))
    return out


_BOXES = {}


def box_of(model: str):
    if model not in _BOXES:
        _BOXES[model] = walls_hd.model_box(model)
    return _BOXES[model]


def footprint(e, drop=0.0, box_of=box_of):
    """(centre x, centre z, half x, half z, yaw, bottom, top) of an entity's model box on the map, its terrain height `drop`
    taken out; None without a model, without its file, or for a piece tipped over (its box says little then)."""
    t, model = walls_hd.transform(e), walls_hd.model_of(e)
    if not t or not model:
        return None
    q = t.get("orientation") or {}
    if abs(float(q.get("x", 0.0))) > 0.2 or abs(float(q.get("z", 0.0))) > 0.2:
        return None
    box = box_of(model)
    if not box:
        return None
    (x0, y0, z0), (x1, y1, z1) = box
    p, s, a = t.get("position", {}), t.get("scale", {}), yaw_of(t)
    sx, sy, sz = float(s.get("x", 1)), float(s.get("y", 1)), float(s.get("z", 1))
    lx, lz = (x0 + x1) / 2 * sx, (z0 + z1) / 2 * sz
    py = float(p.get("y", 0)) - drop
    lo, hi = sorted((py + y0 * sy, py + y1 * sy))
    return (float(p.get("x", 0)) - drop + lx * math.cos(a) + lz * math.sin(a),
            float(p.get("z", 0)) - drop - lx * math.sin(a) + lz * math.cos(a),
            abs(x1 - x0) / 2 * abs(sx), abs(z1 - z0) / 2 * abs(sz), a, lo, hi)


def raster(cx, cz, hx, hz, yaw):
    """The sub-tiles whose centre is inside a turned rectangle."""
    out = set()
    if hx <= 0 or hz <= 0:
        return out
    r = math.hypot(hx, hz)
    co, si = math.cos(yaw), math.sin(yaw)
    for i in range(int((cx - r) // SUB), int((cx + r) // SUB) + 1):
        for j in range(int((cz - r) // SUB), int((cz + r) // SUB) + 1):
            ux, uz = (i + 0.5) * SUB - cx, (j + 0.5) * SUB - cz
            if abs(ux * co - uz * si) <= hx and abs(ux * si + uz * co) <= hz:
                out.add((i, j))
    return out


def drawn_subtiles(entities, ground=None, box_of=box_of):
    """({sub-tiles under a tall model that stands on the ground}, {sub-tiles within half a tile of any model over knee
    height}) of a scene's entities. Model boxes, so an arch or an L-shaped piece counts as filled: the numbers are for
    comparing a scene with D2R's own scenes (`calibrate`), not absolute."""
    solid, near = set(), set()
    for e in entities:
        a = anchor(e, ground)
        if a is None or is_terrain(e):
            continue
        f = footprint(e, a[2], box_of)
        if f is None:
            continue
        cx, cz, hx, hz, yaw, lo, hi = f
        if hi >= LOW:
            near |= raster(cx, cz, hx + TILE / 2, hz + TILE / 2, yaw)
        if hi >= TALL and lo <= LOW and min(hx, hz) <= THICK:
            solid |= raster(cx, cz, max(hx - SHRINK, 0.3), max(hz - SHRINK, 0.3), yaw)
    return solid, near


def walk_check(ds, table, entities, ground=None, flip=None, box_of=box_of) -> dict:
    """How far a scene's drawn walls agree with where units can walk. `walk_through`: walkable sub-tiles under a tall thin
    model (share of all walkable sub-tiles on tiles); `unseen`: blocked sub-tiles of wall tiles with no model within half a
    tile (share of the blocked ones). With `flip` None the sub-tile order that agrees best is taken."""
    solid, near = drawn_subtiles(entities, ground, box_of)
    floor = {(i % ds.width, i // ds.width) for lay in ds.floor_layers() for i, c in enumerate(lay) if c}
    wallc = {(i % ds.width, i // ds.width) for lay, _o in ds.wall_layers() for i, c in enumerate(lay) if c}
    best = None
    for f in ((0, 1, 2, 3) if flip is None else (flip,)):
        blocked = blocked_subtiles(ds, table, f)
        open_ = {(cx * 5 + i, cy * 5 + j) for cx, cy in floor for i in range(5) for j in range(5)} - blocked
        wall_blocked = {s for s in blocked if (s[0] // 5, s[1] // 5) in wallc}
        through = len(open_ & solid)
        unseen = len(wall_blocked - near)
        res = {"flip": f, "walkable": len(open_), "blocked_on_walls": len(wall_blocked), "solid": len(solid),
               "walk_through": through, "walk_through_share": through / max(1, len(open_)),
               "unseen": unseen, "unseen_share": unseen / max(1, len(wall_blocked)),
               "solid_on_blocked_share": len(solid & blocked) / max(1, len(solid))}
        if best is None or res["solid_on_blocked_share"] > best["solid_on_blocked_share"]:
            best = res
    return best


# ---- data ------------------------------------------------------------------------------------------------------------------
class Data:
    """The Median maps and D2R's maps as cells, cached in work/maps_hd/transplant_cells.pkl."""

    def __init__(self, inp=None):
        self.inp = inp or maps_hd.Inputs.load(None, None)
        self.maps, _dt1s, _levels = maps_hd.plan(self.inp)
        self.stock_tiles = maps_hd.parse_tiles(self.inp.d2r_tiles)
        mod = maps_hd.parse_tiles(self.inp.mod_tiles)
        self.tiles = dict(self.stock_tiles)
        self.tiles.update(mod)
        self.donors = maps_hd.donor_table({k: v for k, v in mod.items() if k not in self.inp.d2r_tiles}, self.stock_tiles)
        self._stock = None

    def donor_of(self, p):
        return self.donors[p]["donor"] if p in self.donors else p

    def entry(self, name: str):
        hit = [e for e in self.maps if e["map"] == name or e["map"].endswith("/" + name + ".ds1")]
        if len(hit) != 1:
            raise SystemExit("map %r: %d matches" % (name, len(hit)))
        return hit[0]

    def ds1(self, entry):
        return ds1_remap.Ds1(self.inp.mod_tiles.read(entry["map"]))

    def cells(self, entry):
        return full_cells(self.ds1(entry), entry["dt1_files"], self.tiles.get, self.donor_of)

    def stock(self):
        if self._stock is None:
            cache = ROOT / "work" / "maps_hd" / "transplant_cells.pkl"
            if cache.exists():
                self._stock = pickle.loads(cache.read_bytes())
            else:
                self._stock = {}
                for key in sorted(k[:-4] for k in self.inp.d2r_tiles.keys(".ds1")):
                    if key not in self.inp.scenes:
                        continue
                    try:
                        ds = ds1_remap.Ds1(self.inp.d2r_tiles.read(key + ".ds1"))
                    except (ValueError, IndexError, OSError):
                        continue
                    self._stock[key] = full_cells(ds, walls_hd.header_dt1(ds), self.stock_tiles.get)
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(pickle.dumps(self._stock))
        return self._stock


CALIBRATE = ("act1/cathedrl/cathy3", "act3/temple/temple3", "act3/kurast/slums16x16_0", "act3/kurast/slums08x16_1",
             "act3/docktown/docktown3", "act2/tomb/duriel", "act4/diab/entry1", "act1/barracks/barew")


def walk_stock(data: Data, key: str) -> dict:
    """walk_check of one of D2R's own maps against its own scene: what a hand-made scene scores."""
    ds = ds1_remap.Ds1(data.inp.d2r_tiles.read(key + ".ds1"))
    scene = walls_hd.d2r_scene(key)
    return walk_check(ds, tile_table(walls_hd.header_dt1(ds), data.stock_tiles.get), scene.get("entities", ()),
                      walls_hd.d2r_ground(key, scene))


def survey(data: Data, only=None):
    stock = data.stock()
    index = build_index(stock)
    rows = {}
    for e in data.maps:
        if e["map"] not in walls_hd.MAPS or (only and only not in e["map"]):
            continue
        cells = data.cells(e)
        regions = find_regions(cells, stock, index)
        c = coverage(cells, regions)
        c["top"] = [(r.stock, r.dx, r.dy, len(r.cells), r.walls) for r in big(regions)[:6]]
        rows[e["map"]] = c
    return rows


def survey_table(rows: dict) -> str:
    out = ["| map | cells | wall cells | wall cells in copied regions | all cells in copied regions | regions (D2R maps) | whole D2R scene | method |",
           "|-|-|-|-|-|-|-|-|"]
    for m, c in rows.items():
        share = c["walls_in"] / max(1, c["wall_cells"])
        how = "D2R's scene whole" if c["whole"] else "transplant" if share >= 0.4 else "transplant in part, kit elsewhere" if share >= 0.1 else "kit composition"
        out.append("| %s | %d | %d | %d (%.0f%%) | %d (%.0f%%) | %d (%d) | %s | %s |" % (
            m, c["cells"], c["wall_cells"], c["walls_in"], 100 * share, c["cells_in"], 100 * c["cells_in"] / max(1, c["cells"]),
            c["regions"], c["sources"], c["whole"] or "-", how))
    return "\n".join(out)


def floor_colours(data: Data, entry) -> dict:
    """maps_floor.tile_colours of a Median map: the mean legacy colour of every cell's floor tile."""
    import map_tint
    read = lambda p: (data.inp.mod_tiles if p in data.inp.mod_tiles else data.inp.d2r_tiles).read(p)   # noqa: E731
    return maps_floor.tile_colours(data.ds1(entry), entry["dt1_files"], data.tiles.get, read,
                                   map_tint.act_palette(entry["level_acts"][0]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["survey", "build", "walk", "calibrate"])
    ap.add_argument("map", nargs="?")
    ap.add_argument("scene", nargs="?", help="walk: the scene json to check (default: the one build wrote)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--fallback", help="build: the scene to keep outside the copied regions (default: the built walls_hd scene)")
    ap.add_argument("--flat", action="store_true", help="build: no terrain pieces, every region flattened onto the ground plane")
    ap.add_argument("--layout", type=int, metavar="WALLS", help="build: regions matched on walls alone, with at least WALLS "
                    "wall cells (a map in D2R's vocabulary with the mapper's own floors); implies --flat")
    ap.add_argument("--paint", action="store_true", help="build: floor paint from the legacy map (maps_floor): per-tile biome "
                    "overrides in the scene and the scene's biome with a void base layer in <out>/biome/")
    a = ap.parse_args(argv)
    data = Data()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "survey":
        rows = survey(data, a.map)
        (out / "survey.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(survey_table(rows))
        return 0
    if a.cmd == "calibrate":
        rows = {k: walk_stock(data, k) for k in (a.map.split(",") if a.map else CALIBRATE)}
        (out / "calibrate.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        for k, r in rows.items():
            print("%-34s walk-through %5.1f%%  unseen %5.1f%%  (flip %d)" % (k, 100 * r["walk_through_share"], 100 * r["unseen_share"], r["flip"]))
        return 0
    entry = data.entry(a.map)
    key = entry["map"][:-len(".ds1")]
    cells = data.cells(entry)
    stock = data.stock()
    target = out / (key + ".json")
    if a.cmd != "build" or not a.layout:
        regions = find_regions(cells, stock)
    if a.cmd == "build":
        whole = None if a.layout else whole_source(cells, regions)
        if whole:
            scene, stats = walls_hd.d2r_scene(whole), {"whole": whole}
        else:
            fb = Path(a.fallback) if a.fallback else ROOT / "work" / "maps_hd" / "walls_data" / "hd" / "env" / "preset" / (key + ".json")
            fallback = json.loads(fb.read_text("utf-8-sig"))
            if a.layout:
                colours = floor_colours(data, entry)
                bare = maps_floor.void_cells(cells, colours)       # black floor without walls: not part of any layout
                regions = find_regions({xy: sig for xy, sig in layout(cells).items() if xy not in bare},
                                       {k: layout(v) for k, v in stock.items()})
                scene, stats = compose(cells, regions, fallback, walls_hd.d2r_scene, walls_hd.d2r_ground, stock, pieces=False,
                                       keep=lambda rs: [r for r in rs if r.walls >= a.layout])
            else:
                scene, stats = compose(cells, regions, fallback, walls_hd.d2r_scene, walls_hd.d2r_ground, stock, pieces=not a.flat)
        if a.paint and not whole:
            colours = floor_colours(data, entry)
            biomes_of, save = maps_floor.d2r_biomes(ROOT / "work" / "maps_hd" / "transplant_biomes.pkl")
            learnt = maps_floor.learn(stock, {t for sig in cells.values() for t in sig[1]}, biomes_of)
            save()
            over, stats["paint"] = maps_floor.paint(cells, colours, learnt)
            scene = maps_floor.set_overrides(scene, over)
            name = Path(scene.get("biomeFilename", "")).stem
            env = next((p for p in fb.resolve().parents if p.name == "env"), fb.parent)      # the mod's own biome, by the scene
            src = env / "biome" / (name + ".json")
            biome = json.loads(src.read_text("utf-8-sig")) if src.exists() else maps_floor.d2r_biome(name)
            (out / "biome").mkdir(parents=True, exist_ok=True)
            (out / "biome" / (name + ".json")).write_text(json.dumps(maps_floor.void_biome(biome), separators=(",", ":")),
                                                          encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(scene, separators=(",", ":")), encoding="utf-8")
        (out / (key.replace("/", "_") + ".stats.json")).write_text(json.dumps(stats, indent=1), encoding="utf-8")
        print("%s: %d entities, %d bytes -> %s" % (key, len(scene.get("entities", ())), target.stat().st_size, target))
        print(json.dumps({k: v for k, v in stats.items() if k != "regions"}))
        return 0
    scene = json.loads(Path(a.scene or target).read_text("utf-8-sig"))
    res = walk_check(data.ds1(entry), tile_table(entry["dt1_files"], data.tiles.get), scene.get("entities", ()),
                     walls_hd.d2r_ground(key, scene))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
