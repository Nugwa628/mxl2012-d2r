"""Median XL 2012 maps in D2R's HD client: which map uses what, tile-set stand-ins, scene presets (docs/maps-hd.md).

Adapted from another port's maps_hd.py (574 maps) to this mod's 34 .ds1 / 52 .dt1.
What D2R's HD client draws for a map is a scene preset `data/hd/env/preset/<ds1 path without .ds1>.json` (baked terrain model,
wall/prop entities, biome = ground textures + lighting). A map without one still loads with a default biome and the floor
painted from the tile data, but without walls or buildings. So per map:

  * same bytes as D2R's own .ds1            -> D2R's scene as is (exact)
  * D2R's path, edited by Median            -> D2R's scene when the size is unchanged and at most 25% of the wall/floor cells
                                               changed, else a minimal scene (biome only)
  * a new map                               -> a MINIMAL scene (the shape of D2R's own empty presets) naming the closest
                                               vanilla biome, voted by the stock tile set each map cell comes from; walls and
                                               buildings need custom art (flagged)

Median's 52 new .dt1 files are all re-textured copies of stock D2R tile sets: same tile keys, sizes and (for 47 of 52) the same
walkability flags. `donors` writes that table; the map's tile ids are (style, sequence) keys, so swapping a new .dt1 for its donor
in a level type's file list needs no .ds1 rewrite. HD paints a floor tile through the biome's tile mask, keyed by .dt1 path: a
new .dt1 is in no mask and gets the biome's base layer. `floor_biomes` (build) writes a copy of the map's biome whose mask also
names each new .dt1 with its donor's entries, when the donor belongs to that biome (docs/maps-hd.md "Floors").

  py -3 -I tools/maps_hd.py report [--out DIR]      decide every map; writes report.json / report.md / dt1_donors.json
  py -3 -I tools/maps_hd.py build DATA_DIR          write DATA_DIR/hd/env/preset/<map>.json for every map that needs one, and
                                                    Median's classic tiles to DATA_DIR/global/tiles with the .ds1 monster ids
                                                    renumbered (tools/ds1_remap.py; tools/build.py passes work/mod/data)
  py -3 -I tools/maps_hd.py docs [FILE]             refresh the generated tables in docs/maps-hd.md

Inputs (read-only): the mod's extracted MPQ (MXL2012_EXTRACT, default assets/median from the asset pack, else extract-mpq) and the D2R 93847
baseline extract with filelist.txt (MXL2012_D2R_EXTRACT; default: localconfig.default_d2r_extract()).
"""
import argparse
import collections
import copy
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dt1  # noqa: E402
import ds1_remap  # noqa: E402
import localconfig  # noqa: E402  (.mxl-local.json defaults, D2R extraction)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EDITED_THRESHOLD = 0.25   # share of wall/floor cells that changed above which D2R's baked scene is dropped
BIOME = "data/hd/env/biome/%s.json"
PRESET = "data/hd/env/preset/"
DOCS_BEGIN, DOCS_END = "<!-- maps_hd:begin (generated: py -3 -I tools/maps_hd.py docs) -->", "<!-- maps_hd:end -->"


def first_existing(*paths):
    for p in paths:
        if p and Path(p).exists():
            return Path(p)
    return Path(paths[0])


def default_extract() -> Path:
    env = os.environ.get("MXL2012_EXTRACT") or os.environ.get("MXL_EXTRACT")
    return first_existing(env, ROOT / "assets" / "median", ROOT / "extract" / "mpq", ROOT.parent / "mxl2012-runs" / "extract-mpq",
                          ROOT.parent.parent / "mxl2012-runs" / "extract-mpq")


def default_d2r() -> Path:
    env = os.environ.get("MXL2012_D2R_EXTRACT") or os.environ.get("MXL_D2R_EXTRACT")
    return first_existing(env, ROOT / "extract" / "d2r" / "93847", localconfig.default_d2r_extract())


# ---- stock tile set -> D2R biome -----------------------------------------------------------------------------------------
# Stock tile-set directory (data/global/tiles/<dir>) -> biome. Directories not listed use "<act>_<name>" when D2R has that biome.
BIOME_BY_TILEDIR = {
    "act1/cathedrl": "act1_cathedral", "act1/catacomb": "act1_catacombs", "act1/graveyard": "act1_outdoors",
    "act1/monastry": "act1_outdoors", "act1/town": "act1_campfire", "act1/barracks": "act1_barracks",
    "act1/tristram": "act1_tristram", "act1/jail": "act1_barracks", "act1/river": "act1_outdoors",
    "act2/ruin": "act2_ruin", "act3/temple": "act3_temple", "act4/expansion": "act4_fort",
    "expansion/town": "expansion_town", "expansion/icecave": "expansion_icecave", "expansion/siege": "expansion_siege",
}
# level type (lvltypes Id) -> biome, the fallback for a map none of whose cells resolve (vanilla types 1..36)
BIOME_BY_LEVELTYPE = {
    1: "act1_outdoors", 2: "act1_outdoors", 3: "act1_caves", 4: "act1_crypt", 5: "act1_outdoors", 6: "act1_court",
    7: "act1_barracks", 8: "act1_barracks", 9: "act1_cathedral", 10: "act1_catacombs", 11: "act1_tristram",
    12: "act2_town", 13: "act2_sewer", 14: "act2_palace", 15: "act2_palace_cells", 16: "act2_outdoors",
    17: "act2_tomb", 18: "act2_maggot", 19: "act2_arcane", 20: "act3_kurast", 21: "act3_jungle", 22: "act3_kurast",
    23: "act3_spider", 24: "act3_jungle_dungeon", 25: "act3_sewer", 26: "act4_fort", 27: "act4_mesa", 28: "act4_lava",
    29: "expansion_town", 30: "expansion_siege", 31: "expansion_mountaintop", 32: "expansion_wildtemple",
    33: "expansion_icecave", 34: "expansion_baallair", 35: "act4_lava", 36: "act2_town",
}
LEVELTYPE_FALLBACK = "act1_outdoors"
# tile sets every level type of an act shares (ground, rivers, specials): they say nothing about the area, so they do not vote
SHARED_TILEDIRS = {"act1/river", "act2/ground", "act3/ground", "act3/river", "act4/expansion"}
# New map -> (biome, why): where the tile vote is known to mislead. Inarius is cathy3 (same size and tile-file list), whose floors
# are the Barracks floor tile that the Cathedral level type shares.
BIOME_OVERRIDE = {
    "act1/cathedrl/inarius": ("act1_cathedral", "clone of cathy3 (same size and tile-file list; the vote only sees the shared Barracks floor)"),
}


def tiledir(path: str) -> str:
    """'act3/kurast/floors.dt1' -> 'act3/kurast'."""
    return path.rsplit("/", 1)[0] if "/" in path else path


def biome_for_dir(d: str, biomes) -> str | None:
    if d in SHARED_TILEDIRS:
        return None
    b = BIOME_BY_TILEDIR.get(d)
    if b is None:
        b = d.replace("/", "_")
    return b if b in biomes else None


# ---- tables --------------------------------------------------------------------------------------------------------------
def norm(rel: str) -> str:
    return rel.replace("\\", "/").strip().lower().lstrip("/")


def read_table(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    return [dict(zip(rows[0], r)) for r in rows[1:]]


def num(s, default=0):
    try:
        return int(str(s).strip())
    except ValueError:
        return default


class TileStore:
    """A set of tile files by normalised path (below data/global/tiles), read on demand."""

    def __init__(self, files: dict):
        self.files = files            # path -> Path | bytes

    @classmethod
    def from_dir(cls, root: Path):
        root = Path(root)
        return cls({p.relative_to(root).as_posix().lower(): p for p in root.rglob("*") if p.is_file()})

    def __contains__(self, k):
        return k in self.files

    def read(self, k) -> bytes:
        v = self.files[k]
        return v if isinstance(v, bytes) else v.read_bytes()

    def keys(self, suffix=""):
        return sorted(k for k in self.files if k.endswith(suffix))


def level_usage(levels: list[dict], prest: list[dict]):
    """map key (no .ds1) -> list of {row, def, level, mask, files}; level 0 = a maze piece / unclaimed row."""
    use = collections.defaultdict(list)
    for n, r in enumerate(prest):
        for k in range(1, 7):
            f = r.get("File%d" % k, "").strip()
            if f and f != "0":
                use[norm(f)[:-4]].append({"row": r["Name"], "def": num(r.get("Def"), n), "level": num(r.get("LevelId")),
                                          "mask": num(r.get("Dt1Mask")), "slot": k})
    return use


def level_label(levels_by_id, lid):
    r = levels_by_id.get(lid)
    return "%d %s" % (lid, r["Name"]) if r else "%d" % lid


def selected_files(lvltype_row: dict, mask: int):
    """[(slot 1..32, normalised dt1 path)] the level type lists and the mask selects."""
    out = []
    for b in range(32):
        if mask >> b & 1:
            f = (lvltype_row.get("File %d" % (b + 1)) or "0").strip()
            if f not in ("", "0"):
                out.append((b + 1, norm(f)))
    return out


# ---- tiles ---------------------------------------------------------------------------------------------------------------
def tile_index(files, tiles_of):
    """Lookups for a map's tile resolution: floors (orientation 0) and non-floors, (style, sequence) -> first file in order."""
    floor, wall = {}, {}
    for _slot, path in files:
        for t in tiles_of(path) or ():
            (floor if t.orientation == 0 else wall).setdefault((t.main, t.sub), path)
    return floor, wall


def resolve_tiles(ds: ds1_remap.Ds1, floor_idx, wall_idx):
    """Which .dt1 file each non-empty floor / wall cell of the map comes from (style/sequence only, no orientation: heuristic).
    -> {"floor": Counter(path -> cells), "wall": Counter(...), "floor_missing": n, "wall_missing": n}"""
    res = {"floor": collections.Counter(), "wall": collections.Counter(), "floor_missing": 0, "wall_missing": 0}
    for lay in ds.floor_layers():
        for c in lay:
            if c == 0:
                continue
            p = floor_idx.get(ds1_remap.cell_key(c))
            if p is None:
                res["floor_missing"] += 1
            else:
                res["floor"][p] += 1
    for lay, orient in ds.wall_layers():
        for c, o in zip(lay, orient):
            if c == 0:
                continue
            p = wall_idx.get(ds1_remap.cell_key(c))
            if p is None:
                res["wall_missing"] += 1
            else:
                res["wall"][p] += 1
    return res


def donor_table(new: dict, stock: dict):
    """new, stock: path -> list[Tile]. -> path -> {donor, jaccard, meta_same, tiles}: the stock .dt1 with the most similar tile
    set (key + size multiset), and how many tiles of the new file have the donor's own walkability/size header."""
    sig = {p: collections.Counter((t.key, t.width, t.height) for t in ts) for p, ts in stock.items()}
    out = {}
    for path, ts in sorted(new.items()):
        mine = collections.Counter((t.key, t.width, t.height) for t in ts)
        best, bj = None, -1.0
        for sp, c in sig.items():
            union = sum((mine | c).values())
            j = sum((mine & c).values()) / union if union else 0.0
            if j > bj:
                best, bj = sp, j
        meta = collections.Counter(t.meta for t in stock[best]) if best else collections.Counter()
        mine_meta = collections.Counter(t.meta for t in ts)
        out[path] = {"donor": best, "jaccard": round(bj, 3), "tiles": len(ts),
                     "meta_same": sum((mine_meta & meta).values()),
                     "pixels_same": sum((collections.Counter(t.digest for t in ts) & collections.Counter(t.digest for t in stock[best])).values())}
    return out


def donor_class(d: dict) -> str:
    if d["jaccard"] >= 0.999 and d["meta_same"] >= d["tiles"] * 0.9:
        return "copy"            # same keys and sizes, same walkability: a drop-in stand-in
    if d["jaccard"] >= 0.999:
        return "copy-layout"     # same keys and sizes, some walkability/roof flags differ
    if d["jaccard"] >= 0.8:
        return "similar"
    return "none"


# ---- maps ----------------------------------------------------------------------------------------------------------------
def ds1_diff(mbytes: bytes, dbytes: bytes) -> dict:
    """How Median's edit differs from D2R's map: size, changed wall/floor cells (share), objects added/removed."""
    m, d = ds1_remap.Ds1(mbytes), ds1_remap.Ds1(dbytes)
    r = {"size_m": [m.width, m.height], "size_d": [d.width, d.height]}
    if (m.width, m.height) != (d.width, d.height):
        r.update(cls="size changed", visual_changed=1.0)
        return r
    cells = m.width * m.height
    if (m.walls, m.floors, m.tag_type) != (d.walls, d.floors, d.tag_type):
        nm, nd = m.walls * 2, d.walls * 2
        ch = sum(1 for a, b in zip(m.cells(0), d.cells(0)) if a != b) + sum(1 for a, b in zip(m.cells(nm), d.cells(nd)) if a != b)
        r.update(cls="layers differ", visual_changed=min(1.0, ch / (2 * cells)))
    else:
        n = m.walls * 2 + m.floors
        lm, ld = [m.cells(i) for i in range(n)], [d.cells(i) for i in range(n)]
        vis = [i for i in range(n) if i >= m.walls * 2 or i % 2 == 0]   # wall styles and floors, not orientations
        ch = sum(sum(1 for a, b in zip(lm[i], ld[i]) if a != b) for i in vis)
        r.update(cls="tiles changed" if ch else "tiles same", visual_changed=ch / (len(vis) * cells) if vis else 0.0)
    mo = collections.Counter(tuple(o[:4]) for o in m.objects)
    do = collections.Counter(tuple(o[:4]) for o in d.objects)
    r["objects_added"], r["objects_removed"] = sum((mo - do).values()), sum((do - mo).values())
    return r


def scene_json(biome: str) -> str:
    """The minimal scene: the shape of D2R's own empty presets (act3/kurast/chaos08x08_4.json), as measured in game."""
    path = BIOME % biome
    scene = {"dependencies": {"particles": [], "models": [], "skeletons": [], "animations": [], "textures": [],
                              "physics": [], "json": [{"path": path}], "variantdata": [], "objecteffects": [],
                              "other": []},
             "type": "Preset", "name": "preset", "entities": [], "terrain": {}, "biomeFilename": path,
             "perTileBiomeOverrides": [], "specialTiles": {}}
    return json.dumps(scene, separators=(",", ":"))


def vote_biome(res: dict, donor_of, biomes, level_types, fallback_types=BIOME_BY_LEVELTYPE):
    """-> (biome, how, alt): the stock tile set most wall/floor cells come from (through the stand-in of a new .dt1), the
    level type's stock biome as the fallback and as `alt` (what D2R uses for a stock map of that type).
    The floor cells vote first (the biome paints the floor; walls are scene entities): cypherpunk's walls are Kurast's but its
    floors mostly Docktown's bridge, and Kurast's biome painted them as grass where classic has dark stone. The walls vote
    only when no floor cell names a biome."""
    alt = next((fallback_types[lt] for lt in level_types if fallback_types.get(lt) in biomes), None)
    for kinds in (("floor",), ("floor", "wall")):
        votes = collections.Counter()
        for kind in kinds:
            for path, n in res[kind].items():
                votes[tiledir(donor_of(path))] += n
        for d, _n in votes.most_common():
            b = biome_for_dir(d, biomes)
            if b:
                return b, "%s cells: %s" % ("+".join(kinds), ", ".join("%s %d" % (k, v) for k, v in votes.most_common(3))), alt
    if alt:
        return alt, "level type %s" % ",".join(map(str, level_types)), alt
    return LEVELTYPE_FALLBACK, "no tile resolved, no level type", alt


def ds1_usage_note(ds: ds1_remap.Ds1, mons_raw: collections.Counter, maps: ds1_remap.Maps | None):
    mons = collections.Counter()
    for t, i, *_ in ds.objects:
        if t == 1:
            mons["row" if 0 <= i < (maps.presets.get(ds.act + 1, 0) if maps else 0) else "raw"] += 1
            if not (0 <= i < (maps.presets.get(ds.act + 1, 0) if maps else 0)):
                mons_raw[i] += 1
    return mons


class Inputs:
    """Everything plan() reads, so tests can pass synthetic data."""

    def __init__(self, mod_levels, mod_prest, mod_types, mod_tiles: TileStore, d2r_levels, d2r_prest, d2r_tiles: TileStore,
                 scenes: set, biomes: set, monstats_names=None, monpreset_counts=None, d2r_obj_classes=None,
                 d2r_object_rows=None, mod_object_rows=0, mod_lvlmaze_levels=(), id_maps=None):
        self.mod_levels, self.mod_prest, self.mod_types, self.mod_tiles = mod_levels, mod_prest, mod_types, mod_tiles
        self.d2r_levels, self.d2r_prest, self.d2r_tiles = d2r_levels, d2r_prest, d2r_tiles
        self.scenes, self.biomes = scenes, biomes
        self.monstats_names = monstats_names or []
        self.monpreset_counts = monpreset_counts or {}
        self.d2r_obj_classes = d2r_obj_classes or {}              # act (1-based) -> {ObjPreset index: ObjectClass}
        self.d2r_obj_slots = {a: set(c) for a, c in self.d2r_obj_classes.items()} if d2r_obj_classes else None
        self.d2r_object_rows = d2r_object_rows or {}               # D2R Objects Class (lower) -> row
        self.mod_object_rows = mod_object_rows                     # rows in the mod's objects.txt (the 574 vanilla rows)
        self.mod_lvlmaze_levels = set(mod_lvlmaze_levels)
        # ds1_remap.Maps from tools/idmap.py (monster ids, objects, superuniques); None = ids unchanged (tests)
        self.id_maps = id_maps

    @classmethod
    def load(cls, extract: Path = None, d2r: Path = None):
        extract, d2r = Path(extract or default_extract()), Path(d2r or default_d2r())
        mg, dg = extract / "data" / "global", d2r / "data" / "global"
        scenes, biomes = set(), set()
        for line in (d2r / "filelist.txt").read_text("utf-8", errors="replace").splitlines():
            low = line.strip().lower()
            if low.startswith("data:" + PRESET) and low.endswith(".json"):
                scenes.add(low[len("data:" + PRESET):-5])
            elif low.startswith("data:data/hd/env/biome/") and low.endswith(".json"):
                biomes.add(low[len("data:data/hd/env/biome/"):-5])
        presets = collections.Counter(num(r.get("Act")) for r in read_table(mg / "excel" / "monpreset.txt") if r.get("Act", "").isdigit())
        classes = {}
        for r in read_table(dg / "excel" / "objpreset.txt"):
            if r.get("Act", "").isdigit() and r.get("Index", "").lstrip("-").isdigit():
                classes.setdefault(int(r["Act"]), {})[int(r["Index"])] = r.get("ObjectClass", "")
        rows_by_class = {}
        for n, r in enumerate(read_table(dg / "excel" / "objects.txt")):
            rows_by_class.setdefault(r.get("Class", "").strip().lower(), n)
        id_maps = ds1_remap.Maps.build(mg / "excel", dg / "excel" if (dg / "excel" / "base" / "skills.txt").exists() else None)
        return cls(read_table(mg / "excel" / "levels.txt"), read_table(mg / "excel" / "lvlprest.txt"),
                   read_table(mg / "excel" / "lvltypes.txt"), TileStore.from_dir(mg / "tiles"),
                   read_table(dg / "excel" / "levels.txt"), read_table(dg / "excel" / "lvlprest.txt"),
                   TileStore.from_dir(dg / "tiles"), scenes, biomes,
                   [r.get("Id", "") for r in read_table(mg / "excel" / "monstats.txt")], presets, classes, rows_by_class,
                   len(read_table(mg / "excel" / "objects.txt")),
                   {num(r.get("Level")) for r in read_table(mg / "excel" / "lvlmaze.txt")}, id_maps)


def parse_tiles(store: TileStore, suffix=".dt1"):
    out = {}
    for k in store.keys(suffix):
        try:
            out[k] = dt1.parse(store.read(k))
        except (ValueError, OSError):
            pass
    return out


def plan(inp: Inputs, threshold=DEFAULT_EDITED_THRESHOLD):
    """Decide every map and every .dt1. -> (maps, dt1s, levels) lists of dicts."""
    lv = {num(r.get("Id"), -1): r for r in inp.mod_levels}
    dlv = {num(r.get("Id"), -1): r for r in inp.d2r_levels}
    types = {num(r.get("Id"), j): r for j, r in enumerate(inp.mod_types)}
    use = level_usage(inp.mod_levels, inp.mod_prest)
    stock_dt1 = parse_tiles(inp.d2r_tiles)
    mod_dt1 = {k: v for k, v in parse_tiles(inp.mod_tiles).items()}
    new_dt1 = {k: v for k, v in mod_dt1.items() if k not in inp.d2r_tiles}   # a path D2R lacks
    donors = donor_table(new_dt1, stock_dt1)
    all_tiles = dict(stock_dt1)
    all_tiles.update(mod_dt1)       # the mod's copy wins where both exist
    maps_ctx = inp.id_maps or ds1_remap.Maps(lambda r: r, inp.monpreset_counts, inp.d2r_obj_slots)

    def donor_of(path):
        return donors[path]["donor"] if path in donors else path

    # .dt1 usage by maps is filled in below
    dt1_use = collections.defaultdict(lambda: {"maps": set(), "cells": 0, "types": set()})
    for p, rows in use.items():
        for r in rows:
            lt = types.get(num(lv.get(r["level"], {}).get("LevelType"), -1))
            if lt:
                for _slot, f in selected_files(lt, r["mask"]):
                    if f in donors:
                        dt1_use[f]["types"].add(lt["Name"])

    maps = []
    for key in sorted(k[:-4] for k in inp.mod_tiles.keys(".ds1")):
        mb = inp.mod_tiles.read(key + ".ds1")
        ds = ds1_remap.Ds1(mb)
        rows = use.get(key, [])
        lids = sorted({r["level"] for r in rows if r["level"]})
        e = {"map": key + ".ds1", "levels": [level_label(lv, l) for l in lids], "level_ids": lids,
             "preset_rows": sorted({r["row"] for r in rows}), "size": [ds.width, ds.height], "act_header": ds.act + 1,
             "level_acts": sorted({num(lv[l].get("Act")) + 1 for l in lids if l in lv}),
             "layers": "%d wall, %d floor" % (ds.walls, ds.floors)}
        # tiles: union of the dt1 files all its presets select
        sel, ltypes = {}, set()
        for r in rows:
            lt = types.get(num(lv.get(r["level"], {}).get("LevelType"), -1)) if r["level"] else None
            if lt is not None:
                ltypes.add(num(lt.get("Id")))
                for slot, f in selected_files(lt, r["mask"]):
                    sel.setdefault(f, slot)
        files = sorted(((s, f) for f, s in sel.items()))
        floor_idx, wall_idx = tile_index(files, lambda p: all_tiles.get(p))
        res = resolve_tiles(ds, floor_idx, wall_idx)
        e["level_types"] = sorted(ltypes)
        e["dt1_files"] = [f for _s, f in files]
        nfl, nwl = sum(res["floor"].values()), sum(res["wall"].values())
        newc = {"floor": sum(n for p, n in res["floor"].items() if p in donors), "wall": sum(n for p, n in res["wall"].items() if p in donors)}
        e["tiles"] = {"floor_cells": nfl + res["floor_missing"], "wall_cells": nwl + res["wall_missing"],
                      "floor_new": newc["floor"], "wall_new": newc["wall"],
                      "floor_missing": res["floor_missing"], "wall_missing": res["wall_missing"],
                      "new_dt1_used": sorted({p for kind in ("floor", "wall") for p in res[kind] if p in donors}),
                      "floor_new_dt1": sorted(p for p in res["floor"] if p in donors)}
        for kind in ("floor", "wall"):
            for p, n in res[kind].items():
                if p in donors:
                    dt1_use[p]["maps"].add(key + ".ds1")
                    dt1_use[p]["cells"] += n
        # objects
        mraw = collections.Counter()
        e["monsters"] = dict(ds1_usage_note(ds, mraw, maps_ctx))
        e["monster_raw_rows"] = sorted(mraw)
        e["monster_raw_new"] = [maps_ctx.monster(i) for i in sorted(mraw)]       # the ID map's final id (None: no such row)
        rs = collections.Counter()
        ds1_remap.remap_bytes(mb, maps_ctx, rs)
        e["remap"] = dict(rs)
        e["monster_raw_names_by_row"] = [inp.monstats_names[i] if 0 <= i < len(inp.monstats_names) else "?" for i in sorted(mraw)]
        e["monster_raw_names"] = sorted(set(e["monster_raw_names_by_row"]))
        e["monster_negative"] = sum(1 for t, i, *_ in ds.objects if t == 1 and i < 0)
        e["objects"] = sum(1 for t, *_ in ds.objects if t == 2)
        e["objects_unresolved"] = sum(1 for t, i, *_ in ds.objects if t == 2 and not maps_ctx.object_valid(ds.act, i))
        # objects resolve through D2R's ObjPreset (the 1.13c table + D2R's additions) to an Objects row; a row the mod's
        # objects.txt lacks (D2R-only objects: shrines of the desert, colossal altar, ...) would be an object the mod cannot define
        cls_of = lambda act, i: inp.d2r_obj_classes.get(act, {}).get(i)   # noqa: E731
        rows_of = lambda c: inp.d2r_object_rows.get((c or "").lower())    # noqa: E731
        e["objects_d2r_only"] = sum(1 for t, i, *_ in ds.objects if t == 2 and inp.mod_object_rows and
                                    (rows_of(cls_of(ds.act + 1, i)) or 0) >= inp.mod_object_rows)
        la = e["level_acts"]
        e["act_mismatch"] = bool(la) and (ds.act + 1) not in la
        e["objects_act_differs"] = sum(1 for t, i, *_ in ds.objects if t == 2 and e["act_mismatch"] and any(
            cls_of(ds.act + 1, i) != cls_of(a, i) for a in la)) if e["act_mismatch"] else 0
        # decision
        d2k = key + ".ds1"
        if d2k in inp.d2r_tiles:
            db = inp.d2r_tiles.read(d2k)
            has_scene = key in inp.scenes
            if mb == db:
                e.update(kind="D2R map, unchanged", action="D2R scene", confidence="exact", has_d2r_scene=has_scene,
                         note="byte-identical to D2R's map" + ("" if has_scene else "; D2R has no scene for it"))
                if not has_scene:
                    b, how, alt = vote_biome(res, donor_of, inp.biomes, e["level_types"])
                    e.update(action="minimal scene", biome=b, alt_biome=alt, confidence="low", note="D2R has the map but no scene (%s)" % how)
            else:
                diff = ds1_diff(mb, db)
                e["diff"], e["kind"], e["has_d2r_scene"] = diff, "D2R map, edited by Median", has_scene
                share = diff["visual_changed"]
                if not has_scene:
                    b, how, alt = vote_biome(res, donor_of, inp.biomes, e["level_types"])
                    e.update(action="minimal scene", biome=b, alt_biome=alt, confidence="low", note="D2R has the map but no scene (%s)" % how)
                elif diff["cls"] == "size changed" or share > threshold:
                    b, how, alt = vote_biome(res, donor_of, inp.biomes, e["level_types"])
                    e.update(action="minimal scene", biome=b, alt_biome=alt, confidence="medium",
                             note="layout differs too much for D2R's baked scene (%s, %.0f%% of wall/floor cells); biome by %s" % (
                                 diff["cls"], 100 * share, how))
                else:
                    od = "; %d objects added, %d removed" % (diff["objects_added"], diff["objects_removed"]) \
                        if diff["objects_added"] or diff["objects_removed"] else ""
                    e.update(action="D2R scene", confidence="high" if share <= 0.03 else "medium",
                             note="Median's layout on D2R's scene: %.1f%% of wall/floor cells differ%s" % (100 * share, od))
        else:
            b, how, alt = vote_biome(res, donor_of, inp.biomes, e["level_types"])
            tiles = e["tiles"]
            if key in BIOME_OVERRIDE:
                b, how = BIOME_OVERRIDE[key][0], "override: " + BIOME_OVERRIDE[key][1]
            low = how.startswith("level type") or how.startswith("no tile")
            e.update(kind="Median map", action="minimal scene", biome=b, alt_biome=alt, has_d2r_scene=False,
                     confidence="low" if low else "medium", note="biome by %s" % how)
            if tiles["new_dt1_used"]:
                e["art"] = ("missing in HD: stand-in tiles are stock %s; Median's re-textured look needs custom art "
                            "(%d of %d wall cells on new .dt1)" % (
                                ", ".join(sorted({tiledir(donor_of(p)) for p in tiles["new_dt1_used"]})[:4]), tiles["wall_new"], tiles["wall_cells"]))
                e["art_class"] = "custom"
            else:
                e["art"] = "missing in HD: all %d wall cells are stock tiles, a generated scene (stage 2) can use stock wall models" % tiles["wall_cells"]
                e["art_class"] = "generate"
        if e["action"] == "minimal scene" and e["biome"] not in inp.biomes:
            raise SystemExit("biome %s of %s is not in D2R" % (e["biome"], key))
        maps.append(e)

    dt1s = []
    for path, d in sorted(donors.items()):
        u = dt1_use.get(path, {"maps": set(), "cells": 0, "types": set()})
        dt1s.append(dict(path=path, **d, cls=donor_class(d), maps=sorted(u["maps"]), cells=u["cells"], level_types=sorted(u["types"]),
                         biome=biome_for_dir(tiledir(d["donor"]), inp.biomes)))

    levels = []
    for i in sorted(lv):
        r, d = lv[i], dlv.get(i)
        mine = sorted({f for p, rows in use.items() for q in rows if q["level"] == i for f in [p]})
        theirs = sorted({norm(q.get("File%d" % k, ""))[:-4] for q in inp.d2r_prest if num(q.get("LevelId")) == i
                         for k in range(1, 7) if q.get("File%d" % k, "").strip() not in ("", "0")})
        diffs = {}
        if d is not None:
            for c in ("SizeX", "SizeY", "DrlgType", "LevelType", "Act"):
                if c in r and c in d and r[c] != d[c]:
                    diffs[c] = (d[c], r[c])
        if mine != theirs or diffs:
            levels.append({"id": i, "name": r["Name"], "maps": mine, "d2r_maps": theirs, "diff": diffs})
    return maps, dt1s, levels


def monster_rows(maps):
    """Raw MonStats rows the maps place (ids at or above the act's MonPreset count) and the id tools/idmap.py gives them.
    -> {row: {"name": ..., "new_id": ..., "maps": [...]}}"""
    out = {}
    for e in maps:
        for row, name, new in zip(e["monster_raw_rows"], e["monster_raw_names_by_row"], e["monster_raw_new"]):
            out.setdefault(row, {"name": name, "new_id": new, "maps": []})["maps"].append(e["map"])
    return out


def audit(inp: Inputs, maps) -> list:
    """Static consistency checks of the mod's tables against its files and D2R's (subset of an area audit that
    matters for a mod with 34 maps). -> [(severity, text)] with severity PROBLEM / WARN / INFO."""
    out = []
    have = lambda k: k in inp.mod_tiles or k in inp.d2r_tiles   # noqa: E731
    lv = {num(r.get("Id"), -1): r for r in inp.mod_levels}
    types = {num(r.get("Id"), j): r for j, r in enumerate(inp.mod_types)}
    claimed, used = set(), set()
    for n, r in enumerate(inp.mod_prest):
        lid = num(r.get("LevelId"))
        if lid:
            claimed.add(lid)
        for k in range(1, 7):
            f = r.get("File%d" % k, "").strip()
            if f and f != "0":
                used.add(norm(f))
                if not have(norm(f)):
                    out.append(("PROBLEM", "lvlprest row %d (%s) names a map the mod and D2R lack: %s" % (n, r["Name"], f)))
        mask = num(r.get("Dt1Mask"))
        lt = types.get(num(lv.get(lid, {}).get("LevelType"), -1)) if lid else None
        if lt is not None and mask:
            for b in range(32):
                if mask >> b & 1 and (lt.get("File %d" % (b + 1)) or "0").strip() in ("", "0"):
                    out.append(("WARN", "lvlprest row %d (%s): Dt1Mask bit %d selects an empty slot of level type %s" % (
                        n, r["Name"], b, lt["Name"])))
    for j, t in types.items():
        for k in range(1, 33):
            f = (t.get("File %d" % k) or "0").strip()
            if f not in ("", "0") and not have(norm(f)):
                out.append(("PROBLEM", "lvltypes %d (%s) File %d is in neither the mod nor D2R: %s" % (j, t["Name"], k, f)))
    for i, r in sorted(lv.items()):
        if i <= 0 or r.get("Name", "").startswith("levels_"):
            continue
        d = num(r.get("DrlgType"))
        if d == 2 and i not in claimed:
            out.append(("PROBLEM", "level %d %s is a preset level but no lvlprest row claims it (D2R asserts)" % (i, r["Name"])))
        if d == 1 and inp.mod_lvlmaze_levels and i not in inp.mod_lvlmaze_levels:
            out.append(("PROBLEM", "level %d %s is a maze level with no lvlmaze row" % (i, r["Name"])))
    for k in inp.mod_tiles.keys(".ds1"):
        if k not in used:
            out.append(("INFO", "%s is referenced by no lvlprest row" % k))
    for e in maps:
        t = e["tiles"]
        tot = t["floor_cells"] + t["wall_cells"]
        miss = t["floor_missing"] + t["wall_missing"]
        if e["dt1_files"] and tot and miss / tot > 0.05:
            out.append(("WARN", "%s: %d of %d wall/floor cells name a tile none of its selected .dt1 files has" % (e["map"], miss, tot)))
        if e["act_mismatch"]:
            out.append(("WARN", "%s: header act %d, but its levels are act %s (D2R resolves objects/monster rows by the header act; "
                        "%d object ids resolve to another class in the level's act)" % (
                            e["map"], e["act_header"], "/".join(map(str, e["level_acts"])), e["objects_act_differs"])))
        if e["objects_unresolved"]:
            out.append(("WARN", "%s: %d object ids name no slot of D2R's ObjPreset for the act (the engine skips them)" % (
                e["map"], e["objects_unresolved"])))
        if e["objects_d2r_only"]:
            out.append(("WARN", "%s: %d objects resolve to an Objects row the mod's objects.txt lacks" % (e["map"], e["objects_d2r_only"])))
        if e["monster_negative"]:
            out.append(("WARN", "%s: %d negative monster ids (read outside the MonPreset table; the remap drops them)" % (
                e["map"], e["monster_negative"])))
    if inp.id_maps is not None:
        for row, new in inp.id_maps.moved_objects():
            out.append(("PROBLEM", "idmap moves Objects row %d to %d: the ds1 type-2 ids (ObjPreset indexes) would need ObjectClass rewritten" % (row, new)))
        shifted = inp.id_maps.shifted_superuniques()
        if shifted:
            out.append(("INFO", "superuniques from row %d up (%d rows) sit one id above vanilla as Median ran them; no .ds1 holds a "
                        "superunique id (monpreset Place names them by key), D2R quest code that tests ids must be game-checked" % (
                            shifted[0][0], len(shifted))))
        for e in maps:
            gone = [r for r, n in zip(e["monster_raw_rows"], e["monster_raw_new"]) if n is None]
            if gone:
                out.append(("PROBLEM", "%s: raw monster rows %s have no id in the ID map (the remap drops them)" % (e["map"], gone)))
    return out


# ---- output --------------------------------------------------------------------------------------------------------------
def counts(maps):
    return collections.Counter((e["kind"], e["action"], e["confidence"]) for e in maps)


def md_tables(maps, dt1s, levels, findings=(), mons=None) -> str:
    out = ["### Maps (%d .ds1)" % len(maps), "",
           "| map | levels (lvlprest -> levels.txt) | size | kind | plan | scene / biome | conf. | art needed for walls/buildings |",
           "|---|---|---|---|---|---|---|---|"]
    for e in maps:
        lv = "; ".join(e["levels"]) or ("(unused)" if not e["preset_rows"] else "preset rows: " + ", ".join(e["preset_rows"]))
        scene = e.get("biome") or ("D2R scene" if e.get("has_d2r_scene") else "-")
        if e.get("alt_biome") and e["alt_biome"] != e.get("biome"):
            scene += " (level type: %s)" % e["alt_biome"]
        if "art" in e:
            art = e["art"]
        elif e["action"] == "D2R scene":
            art = "none (D2R's scene)"
        else:
            art = "missing in HD (D2R scene dropped: layout changed); stock tiles, generatable"
        out.append("| %s | %s | %dx%d | %s | %s | %s | %s | %s |" % (
            e["map"], lv, e["size"][0], e["size"][1], e["kind"], e["action"], scene, e["confidence"], art))
    out += ["", "Notes per map: diff against D2R, tile resolution through lvlprest Dt1Mask + lvltypes, ids the remap / ID map must see:", "",
            "| map | note | floor / wall cells (on new .dt1) | monsters: preset rows / raw MonStats rows | objects (unresolved in D2R's table) |",
            "|---|---|---|---|---|"]
    for e in maps:
        t = e["tiles"]
        raw = ", ".join(e["monster_raw_names"][:5]) + ("..." if len(e["monster_raw_names"]) > 5 else "")
        miss = t["floor_missing"] + t["wall_missing"]
        if not e["dt1_files"]:
            unres = "; no level, tiles not resolved"
        elif miss:
            unres = "; %d unresolved" % miss
        else:
            unres = ""
        out.append("| %s | %s | %d (%d) / %d (%d)%s | %d / %d%s | %d (%d) |" % (
            e["map"], e["note"].replace("|", "/"), t["floor_cells"], t["floor_new"], t["wall_cells"], t["wall_new"], unres,
            e["monsters"].get("row", 0), e["monsters"].get("raw", 0), (": " + raw) if raw else "", e["objects"], e["objects_unresolved"]))
    out += ["", "### Tile sets (%d new .dt1) and their stock stand-ins" % len(dt1s), "",
            "Match = same set of (orientation, style, sequence, width, height) as a stock .dt1 (J = Jaccard of the multisets); "
            "walkability = tiles whose header (sub-tile flags, roof, sound, animation) equals the stand-in's. "
            "Level types are the lvltypes rows that list the file.", "",
            "| new .dt1 | tiles | stock stand-in | match | walkability same | stock biome | maps using it | level types |",
            "|---|---|---|---|---|---|---|---|"]
    for d in dt1s:
        out.append("| %s | %d | %s | %s (J %.2f) | %d/%d | %s | %s | %s |" % (
            d["path"], d["tiles"], d["donor"], d["cls"], d["jaccard"], d["meta_same"], d["tiles"], d["biome"] or "-",
            ", ".join(m.replace(".ds1", "") for m in d["maps"]) or "none", ", ".join(d["level_types"]) or "-"))
    out += ["", "### Levels whose map set or key columns differ from D2R's", "",
            "| level | Median maps (lvlprest) | D2R maps | levels.txt change (D2R -> mod) |", "|---|---|---|---|"]
    for lv in levels:
        out.append("| %d %s | %s | %s | %s |" % (lv["id"], lv["name"], ", ".join(lv["maps"]) or "-", ", ".join(lv["d2r_maps"]) or "-",
                                                ", ".join("%s %s->%s" % (c, a, b) for c, (a, b) in lv["diff"].items()) or "-"))
    if mons:
        out += ["", "### Raw MonStats rows the maps place (renumbered by tools/idmap.py)", "",
                "| mod row | Id | D2R id (tools/idmap.py) | maps |", "|---|---|---|---|"]
        for row, m in sorted(mons.items()):
            out.append("| %d | %s | %s | %s |" % (row, m["name"], "none" if m["new_id"] is None else m["new_id"], ", ".join(x.replace(".ds1", "") for x in m["maps"])))
    if findings:
        out += ["", "### Audit", "", "| severity | finding |", "|---|---|"]
        for sev, text in findings:
            out.append("| %s | %s |" % (sev, text.replace("|", "/")))
    return "\n".join(out) + "\n"


def write_report(maps, dt1s, levels, out: Path, findings=(), mons=None):
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps({"maps": maps, "dt1": dt1s, "levels": levels, "audit": findings,
                                                 "monster_rows": {str(k): v for k, v in (mons or {}).items()}}, indent=1),
                                     encoding="utf-8")
    (out / "dt1_donors.json").write_text(json.dumps({d["path"]: {"donor": d["donor"], "class": d["cls"], "jaccard": d["jaccard"]}
                                                     for d in dt1s}, indent=1), encoding="utf-8")
    (out / "monster_rows.json").write_text(json.dumps({str(k): v for k, v in (mons or {}).items()}, indent=1), encoding="utf-8")
    md = ["# Median XL 2012 maps in HD: stand-in report (tools/maps_hd.py)", "", "Generated.", "",
          "| maps | kind | action | confidence |", "|---|---|---|---|"]
    for (kind, action, conf), n in sorted(counts(maps).items()):
        md.append("| %d | %s | %s | %s |" % (n, kind, action, conf))
    md += ["", md_tables(maps, dt1s, levels, findings, mons)]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")
    return out / "report.md"


# ---- floors -------------------------------------------------------------------------------------------------------------------
FLOOR_PREFIX = "mxl2012_"          # generated copies: data/hd/env/biome/mxl2012_<biome>.json + tilemasks/mxl2012_<biome>_masks.json
MASKS = "data/hd/env/tilemasks/%s_masks.json"
TILES_PREFIX = "data/global/tiles/"


def native_floors(e: dict, dt1s) -> list:
    """The map's new floor .dt1 whose donor belongs to the map's biome: [(new path, donor path)]. Only those get the donor's
    mask entries: a donor of another biome (cypherpunk's Fortress interior under Docktown) has mask types that name that
    other biome's layers, so its tiles keep the base layer as before."""
    by = {d["path"]: d for d in dt1s}
    return [(p, by[p]["donor"]) for p in e.get("tiles", {}).get("floor_new_dt1", ())
            if p in by and by[p].get("biome") == e.get("biome")]


def mask_key(path: str) -> str:
    return path.replace("\\", "/").lower()


def extend_mask(mask: dict, pairs) -> int:
    """Add each new .dt1 to a copy of D2R's tile mask with its donor's path / wall mask entries and filter flag (the mask's
    keys are .dt1 paths, either slash). -> mask entries added."""
    added = 0
    for part in ("path_masks", "wall_masks", "filters"):
        have = {mask_key(k): k for k in mask.get(part) or {}}
        for new, donor in pairs:
            k = have.get(mask_key(TILES_PREFIX + donor))
            if k is not None and mask_key(TILES_PREFIX + new) not in have:
                mask[part][TILES_PREFIX + new] = copy.deepcopy(mask[part][k])
                added += part != "filters"
    return added


def floor_biome(biome: dict, mask: dict, pairs, name: str):
    """-> (biome json, mask json) of the generated copies, or None when no new .dt1 gains a mask entry."""
    mask = copy.deepcopy(mask)
    if not extend_mask(mask, pairs):
        return None
    biome = copy.deepcopy(biome)
    old, biome["name"], biome["tileMaskFilename"] = biome["tileMaskFilename"], name, MASKS % name
    for dep in biome.get("dependencies", {}).get("json", ()):
        if mask_key(dep.get("path", "")) == mask_key(old):
            dep["path"] = MASKS % name
    return biome, mask


def floor_biomes(data_dir: Path, maps, dt1s, read=None) -> dict:
    """Write the generated biome + tile mask for every biome that minimal scenes use with native new floors. -> {map: biome
    name} for the maps that get one. `read(rel)` -> parsed D2R json (default fxpaths.d2r_file: the D2R extraction, the
    shared cache, or once from a slot's CASC)."""
    if read is None:
        import fxpaths
        read = lambda rel: json.loads(fxpaths.d2r_file(rel).read_text("utf-8"))   # noqa: E731
    pairs = collections.defaultdict(set)
    for e in maps:
        if e["action"] == "minimal scene":
            pairs[e["biome"]].update(native_floors(e, dt1s))
    made = {}
    for b, ps in sorted(pairs.items()):
        if not ps:
            continue
        biome = read(BIOME % b)
        if not biome.get("tileMaskFilename"):
            continue                     # no mask: every tile gets the biome's base layers anyway
        got = floor_biome(biome, read(biome["tileMaskFilename"]), sorted(ps), FLOOR_PREFIX + b)
        if got is None:
            continue
        for rel, js in ((BIOME % (FLOOR_PREFIX + b), got[0]), (MASKS % (FLOOR_PREFIX + b), got[1])):
            dest = Path(data_dir) / rel[len("data/"):]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(js, separators=(",", ":")), encoding="utf-8")
        made[b] = FLOOR_PREFIX + b
    return {e["map"]: made[e["biome"]] for e in maps
            if e["action"] == "minimal scene" and e["biome"] in made and native_floors(e, dt1s)}


def scene_biome(data_dir: Path, ds1: str):
    """The biome name of the scene `build` wrote for map `ds1` into data_dir, or None (walls_hd keeps it)."""
    p = Path(data_dir) / "hd" / "env" / "preset" / (ds1[:-4] + ".json")
    if not p.exists():
        return None
    b = json.loads(p.read_text("utf-8")).get("biomeFilename") or ""
    return b.rsplit("/", 1)[-1][:-5] or None


def build(data_dir: Path, maps, dt1s=(), read=None) -> int:
    floors = floor_biomes(data_dir, maps, dt1s, read) if dt1s else {}
    n = 0
    for e in maps:
        if e["action"] != "minimal scene":
            continue
        dest = Path(data_dir) / "hd" / "env" / "preset" / (e["map"][:-4] + ".json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(scene_json(floors.get(e["map"], e["biome"])), encoding="utf-8")
        n += 1
    if floors:
        print("floor masks (new .dt1 painted as their donor): %s" % ", ".join("%s -> %s" % (m, b) for m, b in sorted(floors.items())))
    return n


def write_tiles(data_dir: Path, tiles_dir: Path, id_maps=None) -> collections.Counter:
    """Median's classic tiles (.dt1 / .ds1, original names) -> data_dir/global/tiles, every .ds1 with its monster ids
    renumbered for the built tables (id_maps None: ds1_remap's default, the data step's work/mod/ds1_ids.json). D2R loads
    them for the map layout in HD too; the level types name Median's own."""
    import shutil
    dest = Path(data_dir) / "global" / "tiles"
    shutil.copytree(tiles_dir, dest, dirs_exist_ok=True)
    return ds1_remap.remap_tree(dest, id_maps)


def update_docs(path: Path, tables: str) -> bool:
    text = path.read_text("utf-8")
    if DOCS_BEGIN not in text or DOCS_END not in text:
        raise SystemExit("%s lacks the %s ... %s markers" % (path, DOCS_BEGIN, DOCS_END))
    head, rest = text.split(DOCS_BEGIN, 1)
    _old, tail = rest.split(DOCS_END, 1)
    new = head + DOCS_BEGIN + "\n\n" + tables + "\n" + DOCS_END + tail
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["report", "build", "docs"])
    ap.add_argument("path", nargs="?", help="build: the data folder to write into (default work/maps_hd/data); docs: the file")
    ap.add_argument("--out", default=str(ROOT / "work" / "maps_hd"), help="report folder")
    ap.add_argument("--extract", help="the mod's extracted MPQ (default: MXL2012_EXTRACT or the inventory lane's)")
    ap.add_argument("--d2r", help="D2R 93847 baseline extract with filelist.txt")
    ap.add_argument("--edited-threshold", type=float, default=DEFAULT_EDITED_THRESHOLD)
    a = ap.parse_args()
    inp = Inputs.load(a.extract, a.d2r)
    maps, dt1s, levels = plan(inp, a.edited_threshold)
    findings, mons = audit(inp, maps), monster_rows(maps)
    if a.cmd == "build":
        data_dir = Path(a.path or ROOT / "work" / "maps_hd" / "data")
        print("wrote %d minimal scenes" % build(data_dir, maps, dt1s))
        s = write_tiles(data_dir, Path(a.extract or default_extract()) / "data" / "global" / "tiles")
        print("tiles -> %s; ds1 ids: %s" % (data_dir / "global" / "tiles", ", ".join(f"{k}={v}" for k, v in sorted(s.items()))))
    if a.cmd == "docs":
        target = Path(a.path or ROOT / "docs" / "maps-hd.md")
        print("updated" if update_docs(target, md_tables(maps, dt1s, levels, findings, mons)) else "unchanged", target)
    p = write_report(maps, dt1s, levels, Path(a.out), findings, mons)
    for (kind, action, conf), n in sorted(counts(maps).items()):
        print("%4d  %-28s %-14s %s" % (n, kind, action, conf))
    c = collections.Counter(sev for sev, _ in findings)
    print("audit: %d problems, %d warnings, %d info" % (c["PROBLEM"], c["WARN"], c["INFO"]))
    print("report:", p)
    return 1 if c["PROBLEM"] else 0


if __name__ == "__main__":
    sys.exit(main())
