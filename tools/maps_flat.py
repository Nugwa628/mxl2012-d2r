#!/usr/bin/env python
"""Flat maps (owner ruling 2026-11-12): a hand-built Median map in HD as one flat floor, with only its walls standing up.

The owner: classic Median maps look flat; stairs, kerbs and low edges are floor art, and nothing sticks out of the floor
except what is a wall in classic. So every tile kind a map uses gets a verdict from the classic data (rule()):

  wall    an upright classic draws standing up and seeing past it is blocked: the HD pieces on its cells stay 3D
  flat    floor art (floor tiles, low edges, kerbs, steps): no geometry; painted on the floor from the classic picture where
          the HD biome cannot show it (paint 'art'), the HD biome paint where it can ('biome'), black in the void ('void'),
          or not drawn at all ('none': tiles classic draws below the floor line or not at all)
  unsure  doubtful kinds; treated as flat until the owner rules

The verdicts are a data file (tools/data/flat_tiles.tsv, one line per map and tile kind), so a correction is a one-line
change; `table` writes the rule's verdicts for a map's kinds that have no line yet and leaves existing lines alone.

  py -3 -I tools/maps_flat.py table cypherpunk                      verdict lines for the map's kinds (new kinds only)
  py -3 -I tools/maps_flat.py sheet cypherpunk OUT.png              contact sheet: classic picture, uses, verdict, reason
  py -3 -I tools/maps_flat.py build cypherpunk SCENE.json OUTDIR [--lod-base FILE]
        the flat scene from a converted scene (round one's, maps_transplant build --layout --paint) plus the painted
        floor's models, atlas and LOD index entries, under OUTDIR (a mod `data` folder)

Collision is not touched: walkable cells stay the .ds1's (.dt1 sub-tile flags), whatever stands in the scene.
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "tools" / "data" / "flat_tiles.tsv"
COLUMNS = ("map", "orientation", "main", "sub", "folder", "cells", "rise_px", "blocked", "verdict", "paint", "reason")
VERDICTS = ("wall", "flat", "unsure")
PAINTS = ("art", "biome", "void", "none")

TILE = 10.0
WALL_Y = 80                # a wall tile's frame y 0 lies this far below the diamond's top corner (walls_sprite.WALL_Y)
CENTRE_Y = 40 - WALL_Y     # the cell's centre in a wall tile's frame
RISE_WALL = 120            # px a wall-layer picture reaches above the cell's centre: at or above, a wall
RISE_UNSURE = 70           # from here to RISE_WALL: a wall if it blocks a sub-tile (ruined or low walls, hedges, fences
                           # of docktown, graveyard, fort, monastery), unsure if it blocks none (see-through railings)
WALL_SIDES = range(1, 10)  # orientations of wall pieces proper (left, right, corners)
PROPS = (12, 14)           # props and trees: stand when they reach RISE_WALL or block movement, else painted
SPECIAL = (10, 11)         # warps and markers: classic does not draw them in play
SHADOW = 13
ROOF = 15
LOWER = (16, 17, 18, 19)   # lower walls: hang below the floor line (cliff faces into the void)
STEP_SETS = {("act3/kurast", 30), ("act3/kurast", 31)}   # D2R's terrace tile set: its stairs, ramps and kerbs (stock
                                                         # maps give these tiles height; round two's study)
CAVE_SETS = ("act1/caves",)  # cave tile sets: the rock walls are floor tiles (and low props) that block sub-tiles, and the
                             # HD scene stands D2R's cave wall, fence and rock models on those cells (Duncraig)
WHOLE_STRUCTURES = {"epicwhiners"}   # maps whose composed wall structures (walls_scene's mxs_<n>: gateways, junctions, wall
STRUCTURE_REACH = 2                  # runs) stay whole within this many cells of a wall cell; their pivots lie up to 1.5
                                     # cells off the wall line (Duncraig's monastery gateways and junctions)
SQRT15 = math.sqrt(1.5)    # the camera's axis is (-s, -1, -s): a lift g moves a piece by (s g, g, s g) to stay on its pixels
LIFT_VOID = 0.03
LIFT_FLOOR = 0.04          # walls_sprite.FLOOR_LIFT
LIFT_WALL = 0.06           # flat-painted wall-layer art lies over the floor art ...
LIFT_ROW = 0.0008          # ... and over the art of cells nearer the top of the screen (classic's drawing order)
LIFT_LAYER = 0.0003
PAINT_MAX = LIFT_WALL + LIFT_ROW * 256 + LIFT_LAYER * 4    # the highest a painted piece lies over the floor
ID_BASE = 0x6E900000       # entity ids of the painted floor: above walls_sprite's floor sprites (0x6E7C0000 + 0x9000)
MODEL = "data/hd/env/model/mxl/flat/%s/%s_%d_%d_%d.model"
CHUNK_MODEL = "data/hd/env/model/mxl/flat/%s/paint_%s.model"
ATLAS = "data/hd/env/texture/mxl/flat/%s_alb.texture"
VOID_ALB = "data/hd/env/texture/mxl/flat/void_alb.texture"
VOID_ORM = "data/hd/env/texture/mxl/flat/void_orm.texture"
VOID_MAX = 16              # largest side of one void piece, in cells
VOID_OVERLAP = 0.02        # units a void piece reaches past its cells, so neighbouring pieces leave no hairline
CHUNK = 16                 # painted pieces are merged into one model per CHUNK x CHUNK cells (fewer entities: the frame
                           # rate of the flat scene followed its entity count, 2026-11-12)
QUADS_MAX = 38             # quads one painted model holds: the donor's smallest LOD has 155 vertices and 324 indices
ART_SCALE = 2              # the atlas of classic art is upscaled (Lanczos) and its colour matched to the HD paving
PAVING = "data/hd/env/texture/terrain/act3/kurast/act3_kurast_stone_path01_ALB.texture"   # Kurast's street paving (act3_kurast's
                                                                                         # first layer): the art's colour target
FLAT_BIOMES = {"act3_travincal_outdoors": "act3_kurast"}   # biome overrides swapped in a flat scene: the terrace floors take
                                                           # Kurast's street paving, as the shipped scene paints them
                                                           # (Travincal's outdoor stone is about 20% darker)

FLAT_COMPONENTS = {"TerrainDecalDefinitionComponent", "DecalDefinitionComponent", "TerrainStampDefinitionComponent"}
SOLID_COMPONENTS = {"ModelDefinitionComponent", "ModelVariationDefinitionComponent", "PrefabPlacementDefinitionComponent",
                    "PhysicsBodyDefinitionComponent"}
AIR_EFFECTS = ("leaves",)  # particle files kept anywhere off the void: weather, not things
DROP_EFFECTS = ("fog",)    # particle files dropped everywhere: Travincal's fog layers grey the whole floor (the shipped scene
                           # has none)


# ---- verdicts ---------------------------------------------------------------------------------------------------------------
def rise(pixels, o: int) -> int:
    """Pixels a tile's picture reaches above its cell's centre (wall frame for wall layers, the diamond for floors)."""
    if not pixels:
        return 0
    top = min(p[1] for p in pixels)
    return int(round((40 - top) if o == 0 else (CENTRE_Y - top)))


def rule(o: int, folder, main: int, rise_px: int, blocked: int, void: bool = False, roof: int = 0):
    """-> (verdict, paint, reason) of one tile kind from the classic data."""
    if o == 0:
        if folder in CAVE_SETS and blocked and void:
            return "wall", "void", "black cave rock that blocks %d sub-tiles: kept black, the scene's cave walls stand on it" % blocked
        if void:
            return "flat", "void", "black floor (mean brightness under 16): the void, kept black"
        if (folder, main) in STEP_SETS and blocked:
            return "flat", "art", "terrace-set floor that blocks %d sub-tiles: classic picture painted (colour matched)" % blocked
        if (folder, main) in STEP_SETS:
            return "flat", "biome", "terrace-set floor (paving, stair or kerb art), nothing blocked: Kurast's HD street paving"
        if folder in CAVE_SETS and blocked:
            return "wall", "biome", "cave floor whose rock wall blocks %d sub-tiles: the scene's cave walls stand on it" % blocked
        if blocked == 25:
            return "flat", "art", "floor that blocks all 25 sub-tiles: classic picture painted, collision unchanged"
        return "flat", "biome", "plain floor: HD biome paint"
    if o in SPECIAL:
        if folder and rise_px > 0:
            return "flat", "art", "special tile with art (doorway, orientation %d): painted at its classic pixels" % o
        return "unsure", "none", "special tile (orientation %d) with no picture: nothing to draw" % o
    if o == SHADOW:
        return "flat", "none", "shadow tile"
    if o == ROOF:
        return "wall", "none", "roof: classic draws it %d px up over a building's walls" % roof
    if o in LOWER:
        return "flat", "none", "lower wall: hangs below the floor line into the void, which stays black"
    if not folder:
        return "flat", "none", "no tile with this key in the map's tile sets: classic draws nothing"
    how = "%d px above the cell centre, blocks %d of 25 sub-tiles" % (rise_px, blocked)
    if (folder, main) in STEP_SETS:
        return "flat", "art", "stair, ramp or kerb piece (D2R's terrace set), " + how
    if rise_px >= RISE_WALL:
        return "wall", "none", "upright, " + how
    if rise_px >= RISE_UNSURE:
        if o in WALL_SIDES and blocked:
            return "wall", "none", "low wall (blocks movement), " + how
        if o in PROPS:
            if blocked:
                return "wall", "none", "low prop that blocks movement, " + how
            return "flat", "art", "low prop that blocks nothing: painted, " + how
        return "unsure", "art", "low upright that blocks nothing (railing), " + how
    return "flat", "art", "low edge or kerb, " + how


def load_table(path=TABLE) -> dict:
    """{(map stem, o, main, sub): row} of the verdict file."""
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    with p.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader((ln for ln in f if not ln.startswith("#")), delimiter="\t"):
            if row["verdict"] not in VERDICTS or row["paint"] not in PAINTS:
                raise ValueError("flat_tiles: bad verdict or paint in %r" % (row,))
            out[(row["map"], int(row["orientation"]), int(row["main"]), int(row["sub"]))] = row
    return out


def save_table(rows: dict, path=TABLE):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        f.write("# Flat maps: wall / flat / unsure per map and tile kind (tools/maps_flat.py; unsure is built as flat).\n")
        f.write("# paint: art = classic picture on the floor, biome = HD paint, void = black, none = not drawn.\n")
        w = csv.DictWriter(f, COLUMNS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for k in sorted(rows):
            w.writerow({c: rows[k][c] for c in COLUMNS})


def verdicts(table: dict, stem: str) -> dict:
    """{(o, main, sub): (verdict, paint)} of one map; unsure is flat."""
    return {k[1:]: ("wall" if r["verdict"] == "wall" else "flat", r["paint"]) for k, r in table.items() if k[0] == stem}


# ---- the map's tiles ----------------------------------------------------------------------------------------------------------
def placements(ds) -> list:
    """[(x, y, 'floor' | 'wall', layer, (o, main, sub))] of every tile of a .ds1."""
    import ds1_remap
    out = []
    for n, lay in enumerate(ds.floor_layers()):
        for i, c in enumerate(lay):
            if c:
                out.append((i % ds.width, i // ds.width, "floor", n, (0,) + tuple(ds1_remap.cell_key(c))))
    for n, (lay, ori) in enumerate(ds.wall_layers()):
        for i, (c, o) in enumerate(zip(lay, ori)):
            if c:
                out.append((i % ds.width, i // ds.width, "wall", n, (o & 0xFF,) + tuple(ds1_remap.cell_key(c))))
    return out


def kinds(places, folders: dict, tiles: dict, table: dict, palette) -> dict:
    """{key: {cells, folder, rise, blocked, void, roof}} of the kinds in `places`. folders: key -> stock folder; tiles: key ->
    pixels [(x, y, index)]; table: key -> dt1.Tile (sub-tile flags at meta[40:65], roof height at meta[4:6])."""
    import struct
    import maps_floor
    out = {}
    for _x, _y, _layer, _n, k in places:
        if k not in out:
            t = table.get(k)
            px = tiles.get(k) or ()
            drawn = [c for _a, _b, c in px if c]
            mean = [sum(int(palette[c][i]) for c in drawn) / len(drawn) for i in range(3)] if drawn else None
            roof = struct.unpack_from("<h", t.meta, 4)[0] if t else 0
            out[k] = {"cells": 0, "folder": folders.get(k) or "", "rise": roof if k[0] == ROOF else rise(px, k[0]),
                      "blocked": sum(1 for f in t.meta[40:65] if f & 1) if t else 0,
                      "void": k[0] == 0 and mean is not None and maps_floor.luma(mean) < maps_floor.VOID_LUMA, "roof": roof}
        out[k]["cells"] += 1
    return out


def rule_rows(stem: str, ks: dict) -> dict:
    rows = {}
    for k, v in ks.items():
        verdict, paint, why = rule(k[0], v["folder"], k[1], v["rise"], v["blocked"], v["void"], v["roof"])
        rows[(stem,) + k] = {"map": stem, "orientation": k[0], "main": k[1], "sub": k[2], "folder": v["folder"], "cells": v["cells"],
                             "rise_px": v["rise"], "blocked": v["blocked"], "verdict": verdict, "paint": paint, "reason": why}
    return rows


# ---- the flat scene -------------------------------------------------------------------------------------------------------------
def types_of(e) -> set:
    return {c.get("type") for c in e.get("components", ())}


def position(e):
    t = next((c for c in e.get("components", ()) if c.get("type") == "TransformDefinitionComponent"), None)
    return (t["position"]["x"], t["position"]["y"], t["position"]["z"]) if t else None


def cells_near(x: float, z: float, slack: float = 1.0) -> set:
    """The cells within `slack` units of a point (a pivot on a cell edge counts for both cells)."""
    return {(int((x + dx) // TILE), int((z + dz) // TILE)) for dx in (-slack, 0.0, slack) for dz in (-slack, 0.0, slack)}


def particles(e) -> str:
    return " ".join(c.get("filename", "") for c in e.get("components", ()) if c.get("type") == "VfxDefinitionComponent").lower()


def flat_sprite(e, flat_kinds) -> bool:
    """Whether an entity draws a classic tile as an upright wall sprite (walls_sprite's models, as the shipped scene draws
    kerbs and edge ridges) of a kind whose verdict is flat: that kind is painted on the floor instead."""
    for c in e.get("components", ()):
        f = c.get("filename") or ""
        if c.get("type") == "ModelDefinitionComponent" and "/mxl/wallsprite/" in f and f.endswith(".model"):
            try:
                key = tuple(int(v) for v in f.rsplit("/", 1)[-1][:-len(".model")].split("_")[1:])
            except ValueError:
                continue
            if key in flat_kinds:
                return True
    return False


def structure_piece(e) -> bool:
    """Whether an entity is one of walls_scene's composed wall structure pieces (named mxs_<n>; walls_sprite's per-cell
    sprites are mxs_<x>_<y>_<n>)."""
    parts = str(e.get("name", "")).split("_")
    return len(parts) == 2 and parts[0] == "mxs" and parts[1].isdigit()


def keep(e, walls: set, void: set, flat_kinds=frozenset(), whole_structures=False) -> bool:
    """Whether a scene's entity stays in the flat scene: anything solid (model, prefab, physics) only near a wall cell
    (with whole_structures, a composed wall structure piece within STRUCTURE_REACH cells of one), and no upright sprite of
    a flat kind (flat_kinds: (o, main, sub)); floor decals and stamps, sound, mount points and leaves anywhere but the
    void; other effects only near walls, fog nowhere."""
    p = position(e)
    if p is None:
        return True
    near = cells_near(p[0], p[2])
    ts = types_of(e)
    if ts & SOLID_COMPONENTS:
        if whole_structures and structure_piece(e):
            cx, cy, r = int(p[0] // TILE), int(p[2] // TILE), STRUCTURE_REACH
            near = {(cx + dx, cy + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)}
        return bool(near & walls) and not flat_sprite(e, flat_kinds)
    cell = (int(p[0] // TILE), int(p[2] // TILE))
    if "VfxDefinitionComponent" in ts:
        if any(a in particles(e) for a in DROP_EFFECTS):
            return False
        return bool(near & walls) or (cell not in void and any(a in particles(e) for a in AIR_EFFECTS))
    return cell not in void


def lifted(x: float, z: float, g: float):
    """A floor point lifted by g along the camera's axis: drawn on the same pixel, in front of what lies lower."""
    return {"x": x + SQRT15 * g, "y": g, "z": z + SQRT15 * g}


def piece(model: str, name: str, ident: int, pos: dict, scale=(1.0, 1.0)) -> dict:
    return {"type": "Entity", "name": name, "id": ident, "components": [
        {"type": "TransformDefinitionComponent", "name": name + "_t", "position": pos,
         "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}, "scale": {"x": float(scale[0]), "y": 1.0, "z": float(scale[1])},
         "inheritOnlyPosition": False},
        {"type": "ModelDefinitionComponent", "name": name + "_m", "filename": model, "visibleLayers": 1, "lightMask": 19,
         "shadowMask": 0, "ghostShadows": False, "floorModel": False, "terrainBlendEnableYUpBlend": False, "terrainBlendMode": 0}]}


def model_path(stem: str, key) -> str:
    return MODEL % (stem, "floor" if key[0] == 0 else "wall", key[0], key[1], key[2])


def rectangles(cells: set, limit: int = VOID_MAX) -> list:
    """[(x, y, w, h)] covering exactly `cells`, greedy: rows first, then grown down while the whole row is there."""
    todo = set(cells)
    out = []
    for x, y in sorted(cells, key=lambda c: (c[1], c[0])):
        if (x, y) not in todo:
            continue
        w = 1
        while w < limit and (x + w, y) in todo:
            w += 1
        h = 1
        while h < limit and all((x + i, y + h) in todo for i in range(w)):
            h += 1
        for j in range(h):
            for i in range(w):
                todo.discard((x + i, y + j))
        out.append((x, y, w, h))
    return out


def void_cells(places, verdict: dict) -> set:
    """Cells painted black: every floor tile there is the void and no tile there stands (a wall verdict). Flat wall-layer art
    on such a cell (the kerb along a road's edge) is painted over the black."""
    floors, standing = {}, set()
    for x, y, layer, _n, k in places:
        if layer == "floor":
            floors.setdefault((x, y), set()).add(k)
        elif verdict.get(k, ("flat",))[0] == "wall":
            standing.add((x, y))
    return {xy for xy, ks in floors.items() if xy not in standing and ks and all(verdict.get(k, ("", ""))[1] == "void" for k in ks)}


def art_pieces(places, verdict: dict, void: set) -> list:
    """[(key, x, y, lift)] of the painted classic art, in classic drawing order: floor art (not on the void), then flat
    wall-layer art by row and layer (also over the void)."""
    out = []
    for x, y, layer, n, k in places:
        v, paint = verdict.get(k, ("flat", "art" if layer == "wall" else "biome"))
        if v == "wall" or paint != "art" or (layer == "floor" and (x, y) in void):
            continue
        if layer == "floor":
            out.append((k, x, y, LIFT_FLOOR + LIFT_LAYER * n))
        else:
            out.append((k, x, y, LIFT_WALL + LIFT_ROW * (x + y) + LIFT_LAYER * n))
    out.sort(key=lambda q: (q[3], q[2], q[1]))
    return out


def chunked(items, cell_of, size: int = CHUNK, most: int = QUADS_MAX) -> list:
    """items grouped by size x size block of cells (cell_of(item) -> (x, y)), each group cut into runs of at most `most`,
    order kept. -> [((block x, block y, run), [item])]."""
    blocks = {}
    for it in items:
        x, y = cell_of(it)
        blocks.setdefault((x // size, y // size), []).append(it)
    out = []
    for b in sorted(blocks, key=lambda b: (b[1], b[0])):
        its = blocks[b]
        for i in range(0, len(its), most):
            out.append((b + (i // most,), its[i:i + most]))
    return out


def flat_entities(stem: str, places, verdict: dict, void: set, void_key=None) -> tuple:
    """The painted floor, merged: (entities, {model: spec}). Classic art lies on the floor in models of up to QUADS_MAX
    pictures per CHUNK x CHUNK cells (spec {'kind': 'art', 'origin': (X, Z), 'quads': [(key, x, y, lift)]}: the lift is in
    the vertices); the void is opaque black rectangles ({'kind': 'void', 'origin', 'rects': [(x, y, w, h)]}). Each entity
    stands at its model's origin on the floor (y 0)."""
    ents, models = [], {}

    def add(name, spec):
        m = CHUNK_MODEL % (stem, name)
        models[m] = spec
        ox, oz = spec["origin"]
        ents.append(piece(m, "mxp_" + name, ID_BASE + len(ents), {"x": ox, "y": 0.0, "z": oz}))
    for (bx, by, run), quads in chunked(art_pieces(places, verdict, void), lambda q: (q[1], q[2])):
        add("a_%d_%d_%d" % (bx, by, run), {"kind": "art", "origin": ((bx + 0.5) * CHUNK * TILE, (by + 0.5) * CHUNK * TILE),
                                         "quads": quads})
    if void and void_key:
        rects = rectangles(void)
        for (bx, by, run), rs in chunked(rects, lambda r: (r[0], r[1]), size=VOID_MAX * 2):
            xs = [v for x, _y, w, _h in rs for v in (x, x + w)]
            ys = [v for _x, y, _w, h in rs for v in (y, y + h)]
            add("v_%d_%d_%d" % (bx, by, run), {"kind": "void", "origin": ((min(xs) + max(xs)) * TILE / 2, (min(ys) + max(ys)) * TILE / 2),
                                             "rects": rs})
    return ents, models


def flatten(scene: dict, places, verdict: dict, void: set, stem: str, void_key=None) -> tuple:
    """-> (flat scene, stats, {painted model: spec}): the converted scene's solid pieces kept only near wall cells, the
    painted floor added, biome overrides swapped (FLAT_BIOMES), and the model and physics dependencies cut to what the
    entities use."""
    walls = {(x, y) for x, y, _l, _n, k in places if verdict.get(k, ("flat",))[0] == "wall"}
    flat_kinds = {k for k, (v, _p) in verdict.items() if v != "wall"}
    whole = stem in WHOLE_STRUCTURES
    kept = [e for e in scene.get("entities", ()) if keep(e, walls, void, flat_kinds, whole)]
    painted, models = flat_entities(stem, places, verdict, void, void_key)
    out = dict(scene)
    out["entities"] = kept + painted
    used = set()
    for e in out["entities"]:
        files_in(e, used)
    deps = dict(scene.get("dependencies", {}))
    deps["models"] = [d for d in deps.get("models", []) if d.get("path") in used] +         [{"path": m} for m in sorted(models) if m not in {d.get("path") for d in deps.get("models", [])}]
    deps["physics"] = [d for d in deps.get("physics", []) if d.get("path") in used]
    over = scene.get("perTileBiomeOverrides")
    swapped = 0
    if isinstance(over, list):
        over = [o for o in over if not _void_override(o, void)]
        new = []
        for o in over:
            b = Path(str(o.get("biomeFilename", ""))).stem.lower()
            if b in FLAT_BIOMES:
                o = dict(o, biomeFilename="data/hd/env/biome/%s.json" % FLAT_BIOMES[b])
                swapped += 1
            new.append(o)
        out["perTileBiomeOverrides"] = new
        named = {str(o.get("biomeFilename")) for o in new}
        js = [d for d in deps.get("json", []) if not (d.get("path", "").startswith("data/hd/env/biome/")
                                                      and Path(d["path"]).stem.lower() in FLAT_BIOMES and d["path"] not in named)]
        have = {d.get("path") for d in js}
        deps["json"] = js + [{"path": p} for p in sorted(named) if p.startswith("data/hd/env/biome/") and p not in have
                             and Path(p).stem.lower() in FLAT_BIOMES.values()]
    out["dependencies"] = deps
    stats = {"entities_in": len(scene.get("entities", ())), "kept": len(kept), "painted": len(painted),
             "art_pictures": sum(len(s.get("quads", ())) for s in models.values()),
             "void_rects": sum(len(s.get("rects", ())) for s in models.values()), "biome_swapped": swapped,
             "wall_cells": len(walls), "void_cells": len(void), "models": len(deps["models"]), "painted_models": len(models)}
    return out, stats, models


def _void_override(o, void) -> bool:
    try:
        return (int(o.get("tileX")), int(o.get("tileY"))) in void
    except (TypeError, ValueError, AttributeError):
        return False


def files_in(obj, out: set) -> set:
    """Every .model / .physics / .json path named anywhere inside a scene object."""
    if isinstance(obj, dict):
        for v in obj.values():
            files_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            files_in(v, out)
    elif isinstance(obj, str) and obj.startswith("data/") and obj.endswith((".model", ".physics", ".json")):
        out.add(obj)
    return out


def is_painted(e) -> bool:
    """A painted floor model of this tool (art mxp_a_*, void mxp_v_*); walls_hd's props are mxp_<x>_<y>_<n> and stay solid."""
    return e.get("name", "")[:6] in ("mxp_a_", "mxp_v_")


def solid_cells(entities) -> set:
    """Cells under the pivot of every solid entity but the painted floor; these must all be near wall cells."""
    out = set()
    for e in entities:
        if types_of(e) & SOLID_COMPONENTS and position(e) and not is_painted(e):
            p = position(e)
            out.add((int(p[0] // TILE), int(p[2] // TILE)))
    return out


# ---- painted pieces ------------------------------------------------------------------------------------------------------------
def floor_point(px: float, py: float):
    """(X, Z) on the floor of a diamond-frame pixel (top corner (80, 0) -> (0, 0), (160, 40) -> (10, 0), (0, 40) -> (0, 10))."""
    dx, s = (px - 80) / 8.0, py / 4.0
    return (s + dx) / 2, (s - dx) / 2


def paint_mesh(rect, uv_rect, frame_dy: int):
    """(vertices, triangles) of a tile's picture lying on the floor so that the game's camera shows it where classic draws it:
    the picture's rectangle (tile frame; frame_dy moves it into the diamond frame: 0 for floors, WALL_Y for walls) mapped
    corner by corner to the floor, which is affine to the screen."""
    import walls_sprite
    x0, y0, x1, y1 = rect
    u0, v0, u1, v1 = uv_rect
    n, t = (0.0, 1.0, 0.0), (0.7071, 0.0, -0.7071, -1.0)
    verts = []
    for px, py, u, v in ((x0, y0, u0, v0), (x1, y0, u1, v0), (x1, y1, u1, v1), (x0, y1, u0, v1)):
        fx, fz = floor_point(px, py + frame_dy)
        verts.append(((fx, 0.0, fz), n, t, (u, v)))
    return verts, walls_sprite.wound(verts, (0.0, 1.0, 0.0), 0, [(0, 1, 2), (0, 2, 3)])


def chunk_mesh(spec: dict, rects: dict, uvs: dict):
    """(vertices, triangles) of one painted model, relative to its origin. Art: each picture laid on the floor (paint_mesh)
    at its cell, lifted along the camera's axis by its lift; rects / uvs: key -> picture rectangle / atlas UV rectangle.
    Void: each rectangle of cells as one opaque quad at LIFT_VOID, VOID_OVERLAP wider on every side."""
    import walls_sprite
    ox, oz = spec["origin"]
    verts, tris = [], []
    n, t = (0.0, 1.0, 0.0), (0.7071, 0.0, -0.7071, -1.0)
    if spec["kind"] == "art":
        for k, x, y, g in spec["quads"]:
            v, f = paint_mesh(rects[k], uvs[k], 0 if k[0] == 0 else WALL_Y)
            dx, dz = x * TILE - ox + SQRT15 * g, y * TILE - oz + SQRT15 * g
            base = len(verts)
            verts += [((p[0] + dx, g, p[2] + dz), nn, tt, uv) for p, nn, tt, uv in v]
            tris += [(a + base, b + base, c + base) for a, b, c in f]
        return verts, tris
    g, e = LIFT_VOID, VOID_OVERLAP
    for x, y, w, h in spec["rects"]:
        x0, z0 = x * TILE - e - ox + SQRT15 * g, y * TILE - e - oz + SQRT15 * g
        x1, z1 = x0 + w * TILE + 2 * e, z0 + h * TILE + 2 * e
        base = len(verts)
        verts += [((x0, g, z0), n, t, (0.0, 0.0)), ((x1, g, z0), n, t, (1.0, 0.0)), ((x1, g, z1), n, t, (1.0, 1.0)),
                  ((x0, g, z1), n, t, (0.0, 1.0))]
        tris += walls_sprite.wound(verts, (0.0, 1.0, 0.0), base, [(0, 1, 2), (0, 2, 3)])
    return verts, tris


def paving_target(read):
    """(mean, std, pixels) of Kurast's street paving albedo (PAVING), the colour the classic art is moved toward; None when
    the texture is not at hand."""
    import d2r_texture
    import walls_sprite as ws
    t = read(PAVING)
    if not t:
        return None
    px = d2r_texture.small_mip(t, ws.ALBEDO_MIP)
    return ws.colour_stats(px[..., :3].reshape(-1, 3))


def art_atlas(keys, tiles: dict, palette, target=None, scale: int = ART_SCALE):
    """(rgba atlas, {key: picture rect}, {key: uv rect}) of the classic pictures: colour moved toward `target`
    (walls_sprite.match_colour), edges bled, upscaled `scale` times (colour and alpha by Lanczos; the material thresholds the
    alpha at a half)."""
    import numpy as np
    import walls_sprite as ws
    rects = {k: ws.rect_of(tiles[k]) for k in keys}
    places, used_h = ws.pack({k: (r[2] - r[0], r[3] - r[1]) for k, r in rects.items()})
    height = 1 << max(4, math.ceil(math.log2(max(used_h, 1))))
    atlas = np.zeros((height, ws.ATLAS_WIDTH), np.uint8)
    for k in keys:
        (ax, ay), (x0, y0, _x1, _y1) = places[k], rects[k]
        for x, y, c in tiles[k]:
            atlas[ay + y - y0, ax + x - x0] = c
    rgba = ws.upscale(ws.bleed(ws.match_colour(palette[atlas], target)), scale, "lanczos")
    H, W = float(atlas.shape[0]), float(atlas.shape[1])
    uvs = {k: (places[k][0] / W, places[k][1] / H, (places[k][0] + r[2] - r[0]) / W, (places[k][1] + r[3] - r[1]) / H)
           for k, r in rects.items()}
    return rgba, rects, uvs


def void_textures(out: Path) -> list:
    """The void's albedo (opaque black) and ORM (no occlusion light, fully rough, not metal): the void cover shows no ground
    and catches no highlight under the player's light."""
    import numpy as np
    import d2r_texture
    import walls_sprite as ws
    alb = np.zeros((ws.FLAT_SIZE, ws.FLAT_SIZE, 4), np.uint8)
    alb[..., 3] = 255
    orm = np.zeros((ws.FLAT_SIZE, ws.FLAT_SIZE, 4), np.uint8)
    orm[..., 1], orm[..., 3] = 255, 255
    files = []
    for path, px, lin in ((VOID_ALB, alb, False), (VOID_ORM, orm, True)):
        dest = Path(out) / path[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        d2r_texture.write_bc3(dest, px, ws.SET_MIPS, linear=lin)
        files.append(dest)
    return files


def write_pieces(out: Path, stem: str, models: dict, tiles: dict, palette, read, target=None) -> tuple:
    """Atlas, void textures and the painted models (chunk_mesh) under `out` (a mod `data` folder). -> (lod entries, files)."""
    import d2r_texture
    import walls_sprite as ws
    keys = sorted({q[0] for s in models.values() if s["kind"] == "art" for q in s["quads"]})
    files = []
    rects = uvs = {}
    alb = ATLAS % stem
    if keys:
        rgba, rects, uvs = art_atlas(keys, tiles, palette, target)
        dest = Path(out) / alb[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        d2r_texture.write_bc3(dest, rgba, ws.SET_MIPS)
        files.append(dest)
    if any(s["kind"] == "void" for s in models.values()):
        files += void_textures(out)
    donors = [read(ws.SET_DONOR[:-len(".model")] + "_lod%d.model" % n) for n in range(ws.LODS)]
    if not all(donors):
        raise SystemExit("maps_flat: the donor's LOD files are not at hand; run once with MXL_SLOT set")
    lod = []
    for m, spec in sorted(models.items()):
        tex = {"alb": alb, "nrm": ws.FLAT_NRM, "orm": ws.FLAT_ORM} if spec["kind"] == "art" else             {"alb": VOID_ALB, "nrm": ws.FLAT_NRM, "orm": VOID_ORM}
        verts, tris = chunk_mesh(spec, rects, uvs)
        d = Path(out) / m[len("data/"):]
        d.parent.mkdir(parents=True, exist_ok=True)
        for n, donor in enumerate(donors):
            data, lo, hi = ws.sprite_model(donor, verts, tris, tex)
            f = d.with_name(d.stem + "_lod%d.model" % n)
            f.write_bytes(data)
            files.append(f)
        lod.append((m, ws.SET_DONOR, (tuple(lo), tuple(hi))))
    return lod, files


# ---- inputs ------------------------------------------------------------------------------------------------------------------
class MapData:
    """One Median map's classic data: .ds1, tiles, pixels, palette, stock folders."""

    def __init__(self, name: str, data=None):
        import numpy as np
        import maps_transplant as mt
        import map_tint
        import walls_sprite
        self.data = data or mt.Data()
        self.entry = self.data.entry(name)
        self.stem = Path(self.entry["map"]).stem.lower()
        self.ds = self.data.ds1(self.entry)
        self.table = mt.tile_table(self.entry["dt1_files"], self.data.tiles.get)
        self.tiles = walls_sprite.map_tiles(self.data.inp, self.entry)
        pal = np.zeros((256, 4), np.uint8)
        pal[:, :3] = map_tint.act_palette(self.entry["level_acts"][0])
        pal[1:, 3] = 255
        self.palette = pal
        self.places = placements(self.ds)
        self.folders = {}
        for walls, floors in self.data.cells(self.entry).values():
            for f, o, s, q in walls + floors:
                self.folders.setdefault((o, s, q), f)

    def kinds(self) -> dict:
        return kinds(self.places, self.folders, self.tiles, self.table, self.palette)


# ---- contact sheet -------------------------------------------------------------------------------------------------------------
def sheet(md: MapData, rows: dict, out: Path):
    """One row per tile kind: the classic picture on its cell, uses, verdict, paint and reason (PNG and a .md beside it)."""
    from PIL import Image, ImageDraw
    import numpy as np
    keys = sorted((k for k in rows if k[0] == md.stem), key=lambda k: ({"wall": 0, "unsure": 1, "flat": 2}[rows[k]["verdict"]], k[1:]))
    cw, ch, cols = 290, 300, 8
    rows_n = (len(keys) + cols - 1) // cols
    img = Image.new("RGB", (cw * cols, 70 + ch * rows_n), (24, 24, 28))
    d = ImageDraw.Draw(img)
    counts = {v: sum(1 for k in keys if rows[k]["verdict"] == v) for v in VERDICTS}
    d.text((10, 8), "%s: %d tile kinds - wall %d, flat %d, unsure %d (unsure is built as flat). Picture: the classic tile on its "
           "cell (red diamond), at most life size." % (md.stem, len(keys), counts["wall"], counts["flat"], counts["unsure"]),
           fill=(240, 240, 240))
    d.text((10, 30), "Rule: a wall-layer picture reaching %d px or more above the cell centre = wall, under %d px = flat, between "
           "= unsure. Floors flat (paint: art = classic picture on the floor, biome = HD paint, void = black). Roofs wall. "
           "Lower walls and specials not drawn." % (RISE_WALL, RISE_UNSURE), fill=(200, 200, 200))
    colour = {"wall": (240, 120, 90), "flat": (120, 210, 120), "unsure": (240, 210, 80)}
    lut = (255 * (np.arange(256) / 255.0) ** 0.6).astype(np.uint8)
    for i, k in enumerate(keys):
        r = rows[k]
        ox, oy = (i % cols) * cw, 70 + (i // cols) * ch
        pic = np.zeros((760, 240, 3), np.uint8) + 44
        bx, by = 40, 520          # diamond top corner in the picture
        dy = 0 if k[1] == 0 else WALL_Y
        if k[1] == ROOF:
            dy -= int(r.get("roof", 0) or 0)
        ys = [by]
        for x, y, c in md.tiles.get(k[1:], ()):
            X, Y = bx + x, by + y + dy
            if c and 0 <= X < 240 and 0 <= Y < 760:
                pic[Y, X] = md.palette[c][:3]
                ys.append(Y)
        p = Image.fromarray(lut[pic])
        pd = ImageDraw.Draw(p)
        pd.polygon([(bx + 80, by), (bx + 160, by + 40), (bx + 80, by + 80), (bx, by + 40)], outline=(220, 50, 50))
        top, bottom = max(0, min(ys) - 6), min(760, max(max(ys), by + 80) + 6)
        p = p.crop((0, top, 240, bottom))
        f = min(1.0, 200.0 / p.height, 270.0 / p.width)
        p = p.resize((max(1, int(p.width * f)), max(1, int(p.height * f))))
        img.paste(p, (ox + (cw - p.width) // 2, oy + 4 + (200 - p.height)))
        d.rectangle((ox + 2, oy + 2, ox + cw - 3, oy + ch - 3), outline=colour[r["verdict"]])
        d.text((ox + 8, oy + 210), "o %s  main %s  sub %s  %s" % (r["orientation"], r["main"], r["sub"], r["folder"] or "?"), fill=(230, 230, 230))
        d.text((ox + 8, oy + 226), "%s cells  rise %s px  blocks %s/25" % (r["cells"], r["rise_px"], r["blocked"]), fill=(200, 200, 200))
        d.text((ox + 8, oy + 242), "%s  (paint: %s)" % (r["verdict"].upper(), r["paint"]), fill=colour[r["verdict"]])
        why = str(r["reason"])
        d.text((ox + 8, oy + 258), why[:46], fill=(185, 185, 185))
        d.text((ox + 8, oy + 274), why[46:92], fill=(185, 185, 185))
    out = Path(out)
    img.save(out)
    lines = ["# Tile verdicts: %s" % md.stem, "", "Rule (tools/maps_flat.py `rule`): a wall-layer tile whose picture reaches %d px "
             "or more above its cell's centre is a wall; under %d px it is flat floor art; between, unsure (built as flat). "
             "Floor tiles are flat (stair and kerb art and blocked floors painted from the classic picture, the void black, the "
             "rest HD paint). Roofs count as wall; lower walls (cliff faces into the void) and special tiles are not drawn." % (
                 RISE_WALL, RISE_UNSURE), "",
             "Counts: wall %d, flat %d, unsure %d. Correct a verdict in `tools/data/flat_tiles.tsv` (one line per kind)." % (
                 counts["wall"], counts["flat"], counts["unsure"]), "",
             "| o | main | sub | folder | cells | rise px | blocks | verdict | paint | reason |", "|-|-|-|-|-|-|-|-|-|-|"]
    for k in keys:
        r = rows[k]
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % tuple(r[c] for c in COLUMNS[1:]))
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---- command line ---------------------------------------------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["table", "sheet", "build"])
    ap.add_argument("map")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--lod-base", help="build: the model_lod_desc.bin to add the painted models to (default: D2R's)")
    a = ap.parse_args(argv)
    md = MapData(a.map)
    table = load_table()
    if a.cmd == "table":
        new = {k: v for k, v in rule_rows(md.stem, md.kinds()).items() if k not in table}
        table.update(new)
        save_table(table)
        print("%s: %d kinds, %d new lines -> %s" % (md.stem, sum(1 for k in table if k[0] == md.stem), len(new), TABLE))
        return 0
    if a.cmd == "sheet":
        rows = {k: dict(v) for k, v in table.items() if k[0] == md.stem}
        ks = md.kinds()
        for k, v in rows.items():
            v["roof"] = ks.get(k[1:], {}).get("roof", 0)
        sheet(md, rows, Path(a.args[0]))
        print("sheet ->", a.args[0])
        return 0
    import walls_hd
    src, out = Path(a.args[0]), Path(a.args[1])
    verdict = verdicts(table, md.stem)
    missing = {k for *_r, k in md.places} - set(verdict)
    if missing:
        raise SystemExit("maps_flat: %d tile kinds of %s have no verdict line; run `table` first: %s" % (len(missing), md.stem, sorted(missing)[:8]))
    void_keys = [k for k, (_v, p) in verdict.items() if p == "void"]
    void = void_cells(md.places, verdict)
    scene = json.loads(src.read_text("utf-8-sig"))
    flat, stats, models = flatten(scene, md.places, verdict, void, md.stem, void_keys[0] if void_keys else None)
    read = walls_hd.d2r_bytes
    lod, files = write_pieces(out, md.stem, models, md.tiles, md.palette, read, paving_target(read))
    base = Path(a.lod_base).read_bytes() if a.lod_base else None
    walls_hd.write_lod_desc(out, lod, (lambda rel: base) if base else None)
    dest = out / "hd" / "env" / "preset" / (md.entry["map"][:-4].lower() + ".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(flat, separators=(",", ":")), encoding="utf-8")
    stats.update({"files": len(files), "scene_bytes": dest.stat().st_size,
                  "piece_bytes": sum(f.stat().st_size for f in files)})
    notes = ROOT / "work" / "maps_flat"   # not under OUTDIR: that is the mod's data folder in the build
    notes.mkdir(parents=True, exist_ok=True)
    (notes / (md.stem + ".flat.stats.json")).write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
