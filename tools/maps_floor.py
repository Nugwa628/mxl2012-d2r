"""Floor paint of a converted Median map, taken from the legacy map itself.

HD draws a map's floor on the engine's ground plane and paints each cell with a biome's ground textures (the scene's biome,
or a per-tile override). Which biome a cell gets is decided here from two things the legacy map shows:

- the tile's own pixels: a floor tile that is black in legacy (Fauztinville's `neonmile/bridge.dt1`, 5,095 cells) is the
  map's void, not ground, and gets the scene's void biome (`void_biome`: D2R's darkest ground as its base layer);
- the tile's use in D2R: every other cell gets the biome D2R's own scenes paint that floor tile with (`learn`), which is not
  always the biome of the tile's folder (the Kurast terrace floors are Travincal's paving in D2R).

D2R asserts when more than a few biomes are in view (walls_scene.OVERRIDE_BIOMES), so only the biomes with the most cells
are kept; a cell of another biome takes the kept biome whose cells look most like it in legacy (mean tile brightness).

    py -3 -I tools/maps_transplant.py build <map> --paint ...    uses this module
"""
from __future__ import annotations

import collections
import copy
import json
import pickle
from pathlib import Path

import projtemp  # noqa: F401
import ds1_remap
import walls_hd
import walls_scene

VOID_LUMA = 16.0                          # a floor tile darker than this on average (0-255) is void
VOID_TEXTURE = "data/hd/env/texture/terrain/act4/lava/act4_lava_volcanic_dirt01"   # D2R's darkest ground (mean 11, 10, 10)
BIOME = "data/hd/env/biome/%s.json"
TIERS = ("terrainDataUltra", "terrainDataHigh", "terrainDataMed", "terrainDataLow")


def luma(rgb) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def tile_colours(ds, paths, tiles_of, read, palette) -> dict:
    """{(x, y): mean (r, g, b)} of the legacy floor tile of every cell: the floor layer whose tile has the most opaque
    pixels there (the upper one on a tie). read(path) -> the .dt1's bytes; palette: 256 (r, g, b)."""
    import dt1_pixels
    index = walls_hd.floor_index(paths, tiles_of)
    pixels, means = {}, {}

    def mean(path, key):
        if (path, key) not in means:
            if path not in pixels:
                pixels[path] = dt1_pixels.tiles(read(path))
            px = [c for _x, _y, c in pixels[path].get(key, ()) if c]
            rgb = tuple(sum(palette[c][i] for c in px) / len(px) for i in range(3)) if px else None
            means[(path, key)] = (len(px), rgb)
        return means[(path, key)]

    best = {}
    for layer in ds.floor_layers():
        for i, c in enumerate(layer):
            if not c:
                continue
            key = (0,) + ds1_remap.cell_key(c)
            path = index.get(key)
            if not path:
                continue
            n, rgb = mean(path, key)
            xy = (i % ds.width, i // ds.width)
            if rgb is not None and n >= best.get(xy, (0, None))[0]:
                best[xy] = (n, rgb)
    return {xy: rgb for xy, (_n, rgb) in best.items()}


def scene_biomes(scene: dict):
    """(biome name, {(x, y): biome name}) of a D2R scene: its biome and its per-tile overrides."""
    def name(path):
        return Path(path or "").stem.lower()
    return name(scene.get("biomeFilename")), {(o["tileX"], o["tileY"]): name(o.get("biomeFilename"))
                                               for o in scene.get("perTileBiomeOverrides") or ()}


def learn(stock: dict, wanted: set, biomes_of) -> dict:
    """{floor tile: biome}: the biome D2R's scenes paint each wanted floor tile with most. stock: {D2R map: cells}
    (maps_transplant.full_cells); biomes_of(map) -> scene_biomes() of its scene, None without one."""
    count = collections.defaultdict(collections.Counter)
    for key in sorted(stock):
        hits = [(xy, t) for xy, sig in stock[key].items() for t in sig[1] if t in wanted]
        got = biomes_of(key) if hits else None
        if not got:
            continue
        biome, over = got
        for xy, t in hits:
            b = over.get(xy, biome)
            if b:
                count[t][b] += 1
    return {t: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for t, c in count.items()}


def void_cells(cells: dict, colours: dict) -> set:
    """The cells that are void in legacy: a black floor tile and no wall."""
    return {xy for xy, (walls, floors) in cells.items()
            if floors and not walls and colours.get(xy) is not None and luma(colours[xy]) < VOID_LUMA}


def paint(cells: dict, colours: dict, learnt: dict, limit: int = walls_scene.OVERRIDE_BIOMES):
    """-> ({(x, y): biome}, stats): the biome override of every cell that is ground. A cell whose legacy floor is black is
    void and gets none; a wall cell without a floor tile takes the biome most of its painted neighbours have (no black hole
    under a wall); only `limit` biomes are kept."""
    want, void = {}, set()
    for xy, (_walls, floors) in cells.items():
        if not floors:
            continue
        rgb = colours.get(xy)
        if rgb is not None and luma(rgb) < VOID_LUMA:
            void.add(xy)
            continue
        want[xy] = next((learnt[t] for t in floors if t in learnt), None)
    count = collections.Counter(b for b in want.values() if b)
    kept = [b for b, _n in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]
    tone = {}
    for b in kept:
        ls = [luma(colours[xy]) for xy, w in want.items() if w == b and xy in colours]
        tone[b] = sum(ls) / len(ls) if ls else 0.0
    out, moved = {}, 0
    for xy, b in want.items():
        if b in kept:
            out[xy] = b
        elif kept:
            rgb = colours.get(xy)
            out[xy] = min(kept, key=lambda k: (abs(tone[k] - luma(rgb)), k)) if rgb is not None else kept[0]
            moved += 1
    edge = {}
    for xy, (walls, floors) in cells.items():
        if walls and not floors:
            near = collections.Counter(out[n] for n in ((xy[0] + 1, xy[1]), (xy[0] - 1, xy[1]), (xy[0], xy[1] + 1), (xy[0], xy[1] - 1))
                                       if n in out)
            if near:
                edge[xy] = sorted(near.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    out.update(edge)
    return out, {"void": len(void), "painted": len(out), "under_walls": len(edge), "other_biome": moved,
                 "biomes": dict(collections.Counter(out.values())), "tone": {b: round(v, 1) for b, v in tone.items()}}


def set_overrides(scene: dict, overrides: dict) -> dict:
    """The scene with `overrides` ({(x, y): biome name}) as its per-tile biome overrides (row order) and their biomes among
    its json dependencies."""
    scene = dict(scene)
    scene["perTileBiomeOverrides"] = [
        {"type": "TileBiomeOverride", "name": "mxb_%d_%d" % (x, y), "tileX": x, "tileY": y, "biomeFilename": BIOME % b}
        for (x, y), b in sorted(overrides.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    deps = copy.deepcopy(scene.get("dependencies") or {})
    have = {d.get("path") for d in deps.setdefault("json", [])}
    deps["json"] += [{"path": BIOME % b} for b in sorted(set(overrides.values())) if BIOME % b not in have]
    scene["dependencies"] = deps
    return scene


def void_biome(biome: dict, texture: str = VOID_TEXTURE) -> dict:
    """A copy of a scene's biome whose base layer, in every quality tier, shows `texture` (a game path without the
    _alb / _nrm / _orm ending): cells without an override (the void) are painted with that ground. The three textures join
    the dependencies."""
    out = copy.deepcopy(biome)
    paths = {"Albedo": texture + "_alb.texture", "Normal": texture + "_nrm.texture", "ORM": texture + "_orm.texture"}
    for tier in TIERS:
        layers = (out.get(tier) or {}).get("terrainLayers")
        if not layers:
            raise ValueError("void_biome: no layers in tier %s" % tier)
        layers[0].update(paths)
    deps = out.setdefault("dependencies", {}).setdefault("textures", [])
    have = {d.get("path") for d in deps}
    deps += [{"path": p} for p in paths.values() if p not in have]
    return out


def d2r_biomes(cache: Path):
    """biomes_of for learn(): reads D2R's scenes (walls_hd.d2r_scene) and remembers the answers in `cache`."""
    known = pickle.loads(cache.read_bytes()) if cache.exists() else {}
    fresh = [0]

    def biomes_of(key):
        if key not in known:
            scene = walls_hd.d2r_scene(key)
            known[key] = scene_biomes(scene) if scene else None
            fresh[0] += 1
        return known[key]

    def save():
        if fresh[0]:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(pickle.dumps(known))
    return biomes_of, save


def d2r_biome(name: str) -> dict:
    return json.loads(walls_hd.d2r_bytes(BIOME % name).decode("utf-8-sig"))
