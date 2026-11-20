#!/usr/bin/env python
"""Median's classic wall tiles drawn in HD on any map, merged into the scene the normal build made (lane hdtools-spritewall).

tools/walls_sprite.py draws a classic wall tile as a cut-out model; the normal build uses it for the wall cells D2R has no
piece for. This tool draws EVERY upright tile of a map that way and keeps the rest of the map's scene: a switch for chosen
maps (tools/data/sprite_walls.json, empty: tools/build.py's step does nothing then). With --classic the whole map is drawn
from its classic art; tools/build.py does that for the maps of tools/data/sprite_classic.json (docs/maps-hd.md "Classic maps").

  py -3 tools/sprite_scene.py build MAP [MAP ...] OUT [--base DATA] [--lods N] [--pad] [--scale N] [--black-fill cut]
                                    [--export DIR] [--albedo DIR|PNG] [--floors blocked|all|none] [--rule auto|all]
                                    [--light up|camera] [--ground keep|bare] [--classic]
                                    [--pinholes fill|keep] [--fade wall|none]
  py -3 tools/sprite_scene.py build --all OUT ...            the 17 maps of walls_hd.MAPS
  py -3 tools/sprite_scene.py build --list tools/data/sprite_walls.json OUT ...     what tools/build.py runs, and
  py -3 tools/sprite_scene.py build --list tools/data/sprite_classic.json --classic OUT
  py -3 tools/walls_sprite.py build ...                     the same

MAP is a map of the mod or of D2R ('expansion/ghetto/cypherpunk.ds1', or a file name that only one map has: 'cypherpunk'),
or a .ds1 file on disk (its tile files: --dt1 a.dt1,b.dt1, else the names in its header; its palette: --act). OUT is a mod
`data` folder; DATA (default OUT) is the `data` folder whose scene of the map is the base: the normal build's, else D2R's
own scene of a stock map, else an empty scene with --biome.

What a map needs (MapHandle): its .ds1, the .dt1 files its cells resolve in, in order, and an act's palette. Nothing else is
read per map, and nothing in here names a map.

What is drawn, from the tile data alone:
  wall layers, orientations 1-9 (walls), 12 (props), 14 (trees): one curtain model per tile over its cell's two back edges
      (walls_sprite.tile_mesh), heights by the measured camera (PX_HEIGHT);
  wall layers, orientation 15 (roofs): the tile's picture on a level plane, as high as its roof height is drawn up;
  floor tiles that block a sub-tile (cave rock, kerbs, solid black): their picture flat on the cell, merged into one model
      per CHUNK x CHUNK cells (--floors; not on a map the flat build already painted). `--floors all` draws every floor
      tile so, on a flat-painted map too: the ground is then Median's own floor, not the biome's (`--ground bare`: the
      biome under it grows no grass and no clutter, and the art's cells lose their biome override);
  rarity variants: a tile key with several tiles in its file draws them by their rarity, picked per cell by a fixed hash.
Not drawn: orientations 10 and 11 (specials), 13 (shadows), 16-19 (lower walls, below the floor line).

Sharing: a model belongs to its TILE, not to a map: data/hd/env/model/mxl/wallsprite/t/<tile file>-a<act>/<class>_o_s_q.model,
with one albedo atlas per tile file and palette, so every cell and every map that uses a tile draws the same files.
A run adds the tiles it needs to the atlases already in OUT (the models there name the tiles in use), so maps built in
separate runs into one OUT stay right.

The merge rule (merge_scene), by entity name; `sprite cell` = a cell that gets a curtain, a roof or floor art here:
  dropped  mxt_*, mxc_*                        this tool's own, from an earlier run
  dropped  mxw_x_y_n, mxs_x_y_n, mxp_x_y_n     the build's pieces of a sprite cell (D2R's pick, a gap sprite, a set piece:
                                               that one within REACH cells of a sprite cell)
  dropped  mxs_<n>, mxj_*                      composed wall structures and joints within REACH cells of a sprite cell
  dropped  entities of D2R's own scene (no mx name) that carry a wall model (walls_hd.wall_entities: not the terrain,
           not decoration) on or next to a sprite cell
  kept     everything else: terrain, walkways, the flat build's painted floor, step sprites (mxf_), props on floor cells,
           lights, effects, sounds, the biome and its tile overrides

`--classic` is the all-classic scene in one switch: `--floors all --ground bare --rule all`, every entity of the base that
draws a model is dropped (D2R's pieces and the build's alike) and no cell keeps a biome override. What the map then shows is
its own .dt1 art; lights, effects and sounds of the base stay, and so do the level's units (monsters, chests, corpses),
which no scene file holds. The ground is the map's own copy of its biome (`mxl2012_classic_<map>`): nothing grows on it and
every terrain layer is black, so a cell without a floor tile shows black as in classic, not D2R's ground; and its light is
the map's own (CLASSIC_LIGHT: the key light that lights the cut-outs, by default a plain one where the biome has none, as
D2R's indoor biomes do, whose walls would stand black).
"""
import argparse
import json
import math
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import walls_sprite as ws  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "tools" / "data" / "sprite_walls.json"
CLASSIC_LIST = ROOT / "tools" / "data" / "sprite_classic.json"   # the maps tools/build.py builds with --classic
S = math.sqrt(1.5)                 # the camera looks along (-S, -1, -S): 30 degrees above the ground (docs/maps-hd-method.md)
PX_HEIGHT = ws.PX_PER_UNIT * S     # classic pixels per world unit of height: 9.80 (walls_sprite's 9.24 drew walls 6% too tall)
WALL, PROP, TREE, ROOF = "wall", "prop", "tree", "roof"
CLASS_OF = {**{o: WALL for o in range(1, 12)}, 12: PROP, 14: TREE, 15: ROOF}   # the file names' first word: walls_hd.tier
SPECIAL = frozenset((10, 11))      # the .dt1's special wall tiles (doorways, level exits): drawn only on the maps of DOOR_MAPS
DRAWN = frozenset(CLASS_OF) - SPECIAL   # the orientations drawn by default
# maps whose special tiles are drawn as walls, as classic draws them: Island of the Sunless Sea's cave exit (two orientation 11
# tiles between its torches) is otherwise D2R's flat dark plane
DOOR_MAPS = {"rockisdead"}
MODEL = "data/hd/env/model/mxl/wallsprite/t/%s/%s_%d_%d_%d.model"      # group, class + variant, orientation, style, sequence
ATLAS = "data/hd/env/texture/mxl/wallsprite/t/%s_alb.texture"
CHUNK_MODEL = "data/hd/env/model/mxl/wallsprite/m/%s/rock_%d_%d.model"   # 'rock': walls_hd.tier 2
FLOOR_ATLAS = "data/hd/env/texture/mxl/wallsprite/m/%s_floor_alb.texture"
ID_BASE = 0x71000000               # entity ids count up from here, past any id the scene already uses
CHUNK = 16                         # cells per side of one floor art model
CAMERA_NORMAL = (0.5, 0.7071, 0.5)  # half way between up and the camera's side of the map: lit from above and from the front;
#                                     at right angles to the curtain's tangent (0.7071, 0, -0.7071)
REACH = 2                        # cells: a composed structure's or set piece's pivot lies up to 1.5 cells off its wall cells
WIDTHS = (256, 512, 1024, 2048, 4096)
MIN_SIDE = 64                      # an atlas's smallest side (16 x 16 with one mip lost the GPU device, lane hdscene2)
BLACK = 12                         # --black-fill cut: a pixel whose brightest channel is under this ...
BLACK_AREA = 96                    # ... in a connected patch of at least this many pixels is fill, not art
ROOF_FRAME_DY = 0                  # a roof tile's y 0 is the diamond's top corner, like a floor's (walls: ws.WALL_Y lower)
EMPTY_BIOME = {1: "act1_wilderness", 2: "act2_desert", 3: "act3_kurast", 4: "act4_mesa", 5: "expansion_siege"}   # --biome's default
BIOME = "data/hd/env/biome/%s.json"
BARE_PREFIX = "mxl2012_bare_"      # --ground bare: the scene's biome copied without grass and clutter
TIERS = ("terrainDataUltra", "terrainDataHigh", "terrainDataMed", "terrainDataLow")
CLASSIC_PREFIX = "mxl2012_classic_"   # --classic: the map's own biome (bare, black ground) and its visual data file
BLACK_GROUND = "data/hd/env/texture/mxl/wallsprite/black_%s.texture"   # alb, nrm, orm of the black terrain layer
GROUND_SIZE, GROUND_MIPS = 1024, 11   # D2R's own terrain textures: 1024 x 1024, every level
VIS = "data/hd/env/vis/%s.json"
KEY_LIGHT = "global_key_light"
# --classic: the map's light, derived from classic's own light (classic_light): levels.txt gives every level of the 17 maps a
# fixed ambient light (Intensity and Red / Green / Blue; none of them follows the day), the player carries a white pool of
# light, and invisible monsters that never move (monstats2 Light, light-r/g/b; Fauztinville's pink and blue lamps) light
# their spot. Classic multiplies the art by the light in display (sRGB) values, HD in linear values: a classic factor f is
# f ** AMBIENT_GAMMA in HD. LIGHT_RULE holds the numbers that turn that into D2R's light file and scene, measured against
# classic frames (the lane's report, mxl2012-runs/hdtools/maplight/REPORT.md):
#   key      key light power per unit of linear ambient (the key light stands in for classic's ambient: it lights the floor and
#            every cut-out alike, their normals point up)
#   ibl      image based light (D2R's sky light: a grey fill classic does not have)
#   player   the player's light power, reach its distance scaler, attenuation its fall-off
#   point    a light monster's point light power, point_reach world units of radius per step of its Light value, point_height
#            its height over the ground, point_attenuation its fall-off
#   lut      the grading LUT (D2R's neutral one: the biomes' own tint the picture)
AMBIENT_GAMMA = 2.2
LIGHT_RULE = {"key": 250.0, "ibl": 0.0, "player": 3500.0, "reach": 4.5, "attenuation": 5.5, "point": 2500.0, "point_reach": 2.0,
              "point_height": 6.0, "point_attenuation": 2.0, "lut": "data/hd/env/lut/default.dds"}
# hand-tuned what the rule leaves: {map key: {light file values that replace the rule's}}; "gain" multiplies the rule's key
# light power, "pgain" the player's light power. Both are measured: a brightness ratio HD / classic r (in display values) of
# the map's frames, far from the player for the key light and at the player for the player's light, gives a gain r ** -1.6
# (display to linear is 2.2; damped, as each light also reaches the other's zone), applied on the previous gain, rounded.
# "key" replaces the level's colour where the full colour tints far more than classic does (Vizjun, Tran Athulua): the
# colour of classic's frames there, gain scaled by the luminance change. "spec" is the key light's specular share (D2R's 1.0
# when absent): the black ground still reflects a strong key light, so a map whose key is strong and saturated (Hole Level 2,
# The Proving Grounds) shows a coloured sheet over the empty area off its floor where classic is black; at 0 that area is
# black and the art keeps the key's plain (diffuse) light, as classic has no specular light at all.
CLASSIC_LIGHT = {"macumba": {"gain": 0.06, "pgain": 0.44}, "moskvich": {"gain": 0.7, "pgain": 0.79},
                 "cypherpunk": {"pgain": 0.94, "reach": 2.5}, "desertpeak": {"gain": 3.2, "pgain": 0.49, "key": (1.0, 0.9, 0.35)},
                 "glados": {"gain": 1.3, "pgain": 0.35, "key": (0.85, 1.0, 1.0)}, "epicwhiners": {"pgain": 1.2, "reach": 5.5},
                 "downtown": {"gain": 4.0, "pgain": 0.8}, "charismatic": {"gain": 0.38, "pgain": 0.61}, "borgir": {"gain": 1.4, "pgain": 0.88},
                 "excelsior3": {"gain": 0.13, "pgain": 0.5}, "inarius": {"gain": 0.3, "pgain": 0.4}, "rockisdead": {"gain": 0.39},
                 "belial": {"gain": 0.52, "pgain": 1.2},
                 "caveroom4": {"gain": 0.264, "pgain": 0.77, "key": (1.0, 0.03, 0.0), "spec": 0.0},
                 "dungrm6a": {"gain": 0.54, "pgain": 0.21, "key": (1.0, 0.55, 0.85), "spec": 0.0},
                 "temple5": {"gain": 0.245, "pgain": 0.41, "key": (1.0, 0.43, 0.10)},
                 "temple6": {"gain": 0.245, "pgain": 0.41, "key": (1.0, 0.43, 0.10)}}
DEFAULT_LIGHT = {"key": (1.0, 1.0, 1.0), "power": 8.0}    # a map with no level row (a .ds1 file on disk): a plain key light
# maps whose wall tiles go into atlas groups of their own ('<group>-<suffix>'), so that adding them to sprite_classic.json leaves
# the atlases and models of the maps already on it byte for byte as they were (Hole Level 2 shares the cave tiles of Duncraig,
# Azmodan's Reliquary the Kurast interior tiles of Vizjun and Rathma Square, Island of the Sunless Sea the ice cave props of
# Welcome to Toraja); a few tiles are then stored twice
OWN_GROUP = {"caveroom4": "hole2", "dungrm6a": "proving", "temple5": "reliquary", "temple6": "reliquary",
             "rockisdead": "rockisdead"}


# ---- tiles -------------------------------------------------------------------------------------------------------------------
class Variant:
    """One tile of a .dt1: its number among the tiles of its key (file order), rarity, pixels, roof height, blocked sub-tiles,
    animated (the tile header's animation flag: the key's tiles are frames, not rarity variants)."""
    __slots__ = ("key", "n", "rarity", "pixels", "roof", "blocked", "animated")

    def __init__(self, key, n, rarity, pixels, roof=0, blocked=0, animated=False):
        self.key, self.n, self.rarity, self.pixels, self.roof, self.blocked = key, n, rarity, pixels, roof, blocked
        self.animated = animated


def file_tiles(data: bytes) -> dict:
    """{(orientation, style, sequence): [Variant]} of every tile with a picture in a .dt1, rarity variants included."""
    import dt1_pixels
    count, ptr = struct.unpack_from("<ii", data, 0x10C)
    out = {}
    for t in range(count):
        o = ptr + t * 96
        roof = struct.unpack_from("<h", data, o + 4)[0]
        animated = bool(data[o + 7])
        orient, main, sub, rarity = struct.unpack_from("<4i", data, o + 20)
        bptr, _blen, nblocks = struct.unpack_from("<iii", data, o + 72)
        px = []
        for b in range(nblocks):
            h = bptr + b * dt1_pixels.BLOCK_HEADER
            if h + dt1_pixels.BLOCK_HEADER > len(data):
                break
            bx, by, _u, _gx, _gy, fmt, length, _u2, off = struct.unpack_from("<hhhBBhihi", data, h)
            px += [(bx + x, by + y, c) for x, y, c in dt1_pixels.block_pixels(fmt, data[bptr + off:bptr + off + length])]
        if not px:
            continue
        vs = out.setdefault((orient, main, sub), [])
        vs.append(Variant((orient, main, sub), len(vs), rarity, px, roof, sum(1 for f in data[o + 40:o + 65] if f & 1), animated))
    return out


def pick(variants: list, x: int, y: int, layer: int) -> Variant:
    """The cell's variant: as classic, the tiles with a rarity share the cell by their rarity (all 0: the first); the choice is
    a fixed hash of the cell, so every build draws the same map (classic rolls it per game)."""
    live = [v for v in variants if v.rarity > 0]
    if len(variants) == 1 or not live:
        return variants[0]
    roll = zlib.crc32(b"%d,%d,%d" % (x, y, layer)) % sum(v.rarity for v in live)
    for v in live:
        roll -= v.rarity
        if roll < 0:
            return v
    return live[-1]


def cut_black(pixels: list, palette, area: int = BLACK_AREA, dark: int = BLACK) -> list:
    """The pixels without the tile's black fill: connected patches (4 neighbours) of at least `area` near-black pixels."""
    black = {(x, y) for x, y, c in pixels if c and max(int(v) for v in palette[c][:3]) < dark}
    drop, seen = set(), set()
    for start in black:
        if start in seen:
            continue
        patch, todo = [start], [start]
        seen.add(start)
        while todo:
            x, y = todo.pop()
            for p in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if p in black and p not in seen:
                    seen.add(p)
                    patch.append(p)
                    todo.append(p)
        if len(patch) >= area:
            drop.update(patch)
    return [p for p in pixels if (p[0], p[1]) not in drop]


def group_of(dt1_path: str, act: int) -> str:
    """The folder and atlas name of a tile file drawn with an act's palette: 'act3/kurast/walls.dt1', 3 -> 'act3-kurast-walls-a3'."""
    p = dt1_path.replace("\\", "/").lower()
    return "%s-a%d" % ((p[:-4] if p.endswith(".dt1") else p).replace("/", "-").replace(" ", "_"), act)


def tile_name(key, n: int = 0) -> str:
    """A tile's model file name without the extension: 'wall_1_0_3', its second variant 'wallv1_1_0_3'. walls_sprite.key_of and
    maps_flat.flat_sprite read the three numbers; walls_hd.tier reads the first word."""
    return "%s%s_%d_%d_%d" % (CLASS_OF[key[0]], "v%d" % n if n else "", *key)


def parse_name(name: str):
    """((o, s, q), variant) of a tile_name, or None."""
    head, *nums = name.split("_")
    try:
        key = tuple(int(v) for v in nums)
    except ValueError:
        return None
    if len(key) != 3 or key[0] not in CLASS_OF:
        return None
    cls = CLASS_OF[key[0]]
    if head == cls:
        return key, 0
    if head.startswith(cls + "v") and head[len(cls) + 1:].isdigit():
        return key, int(head[len(cls) + 1:])
    return None


# ---- a map -------------------------------------------------------------------------------------------------------------------
class MapHandle:
    """All this tool reads of a map: name ('expansion/ghetto/cypherpunk.ds1'), its parsed .ds1 (ds1_remap.Ds1 or anything with
    width, wall_layers() and floor_layers()), its tile files [(path, bytes)] in the order its cells resolve in (the first file
    with a key wins) and its palette (256 x 4 uint8, index 0 transparent; default: the act's)."""

    def __init__(self, name: str, ds, files, act: int = 1, palette=None, biome=None, level=""):
        self.name = name.replace("\\", "/").lower()
        self.key = self.name[:-4] if self.name.endswith(".ds1") else self.name
        self.stem = self.key.rsplit("/", 1)[-1]
        self.ds, self.act, self.biome, self.level = ds, act, biome, level
        self.variants, self.source, self.by_file = {}, {}, {}
        for path, data in files:
            path = path.replace("\\", "/").lower()
            self.by_file[path] = file_tiles(data)
            for k, vs in self.by_file[path].items():
                if k not in self.variants:
                    self.variants[k], self.source[k] = vs, path
        if palette is None:
            import map_tint
            palette = np.zeros((256, 4), np.uint8)
            palette[:, :3] = map_tint.act_palette(act)
            palette[1:, 3] = 255
        self.palette = palette

    @staticmethod
    def _files(paths, inp):
        out = []
        for f in paths:
            f = f.replace("\\", "/")
            store = inp.mod_tiles if f.lower() in inp.mod_tiles else inp.d2r_tiles if f.lower() in inp.d2r_tiles else None
            if store is not None:
                out.append((f.lower(), store.read(f.lower())))
            elif Path(f).is_file():
                out.append((Path(f).name.lower(), Path(f).read_bytes()))
        return out

    @classmethod
    def from_plan(cls, inp, entry, level=""):
        """A map of the mod or of D2R that tools/maps_hd.py plans (every map of lvlprest.txt)."""
        import ds1_remap
        name = entry["map"].lower()
        store = inp.mod_tiles if name in inp.mod_tiles else inp.d2r_tiles
        acts = entry.get("level_acts") or [1]
        return cls(name, ds1_remap.Ds1(store.read(name)), cls._files(entry["dt1_files"], inp), acts[0] or 1, biome=entry.get("biome"), level=level)

    @classmethod
    def from_file(cls, path, inp, dt1=None, act=None, name=None, biome=None):
        """A .ds1 file on disk that no table names: its tile files are `dt1` (paths below data/global/tiles, or files) or the
        .dt1 names of its own header; its palette that of `act` (1-5), else of its header's act."""
        import ds1_remap
        import walls_hd
        ds = ds1_remap.Ds1(Path(path).read_bytes())
        files = cls._files(dt1 or walls_hd.header_dt1(ds), inp)
        if not files:
            raise SystemExit("sprite_scene: none of the tile files of %s is at hand; name them with --dt1" % path)
        return cls(name or "adhoc/%s.ds1" % Path(path).stem, ds, files, act or min(5, max(1, ds.act + 1)), biome=biome)

    def group(self, dt1_path: str) -> str:
        """The atlas group this map draws a tile file's tiles into: group_of, with the map's OWN_GROUP suffix."""
        own = OWN_GROUP.get(self.stem)
        return group_of(dt1_path, self.act) + ("-" + own if own else "")

    def walls(self, orientations=DRAWN) -> list:
        """[(x, y, layer, Variant)] of the upright tiles: every wall layer cell of the orientations that has a tile."""
        import ds1_remap
        out = []
        for n, (lay, ori) in enumerate(self.ds.wall_layers()):
            for i, (c, o) in enumerate(zip(lay, ori)):
                o &= 0xFF
                if not c or o not in orientations:
                    continue
                key = (o,) + tuple(ds1_remap.cell_key(c))
                if key in self.variants:
                    x, y = i % self.ds.width, i // self.ds.width
                    out.append((x, y, n, pick(self.variants[key], x, y, n)))
        return out

    def floors(self, which: str = "blocked") -> list:
        """[(x, y, layer, Variant)] of the floor tiles drawn as art: those that block a sub-tile ('blocked'), 'all' or 'none'.
        A key's tiles share the cells by their rarity as the walls' do (pick); an animated key (its tiles are frames) draws
        its first tile."""
        import ds1_remap
        out = []
        if which == "none":
            return out
        for n, lay in enumerate(self.ds.floor_layers()):
            for i, c in enumerate(lay):
                vs = self.variants.get((0,) + tuple(ds1_remap.cell_key(c))) if c else None
                x, y = i % self.ds.width, i // self.ds.width
                v = (vs[0] if any(t.animated for t in vs) else pick(vs, x, y, n)) if vs else None
                if v is not None and (which == "all" or v.blocked):
                    out.append((x, y, n, v))
        return out

    def rise(self, v: Variant) -> int:
        """Pixels the tile's picture reaches above its cell's centre (maps_flat.rise)."""
        import maps_flat
        return maps_flat.rise(v.pixels, v.key[0])

    def flat_keys(self, keys, table=None) -> set:
        """The keys of `keys` the flat build paints on the floor (verdict flat or unsure): its table's line for this map where
        there is one, else maps_flat.rule on the tile's own data."""
        import maps_flat
        table = maps_flat.verdicts(maps_flat.load_table(), self.stem) if table is None else table
        out = set()
        for k in keys:
            if k in table:
                verdict = table[k][0]
            else:
                v = self.variants[k][0]
                folder = self.source[k].rsplit("/", 1)[0] if "/" in self.source[k] else ""
                verdict = maps_flat.rule(k[0], folder, k[1], v.roof if k[0] == 15 else self.rise(v), v.blocked, False, v.roof)[0]
            if verdict != "wall":
                out.add(k)
        return out


# ---- geometry ----------------------------------------------------------------------------------------------------------------
def roof_mesh(rect, uv_rect, roof_px: int):
    """(vertices, triangles) of a roof tile: its picture on the level plane roof_px classic pixels over the floor. The picture's
    rectangle (the tile's frame, ROOF_FRAME_DY from the diamond's) maps corner by corner to the floor under it (the floor is
    affine to the screen), then goes straight up: the camera shows every pixel where classic draws it."""
    import maps_flat
    x0, y0, x1, y1 = rect
    u0, v0, u1, v1 = uv_rect
    n, t = (0.0, 1.0, 0.0), (0.7071, 0.0, -0.7071, -1.0)
    up = roof_px / PX_HEIGHT
    verts = []
    for px, py, u, v in ((x0, y0, u0, v0), (x1, y0, u1, v0), (x1, y1, u1, v1), (x0, y1, u0, v1)):
        fx, fz = maps_flat.floor_point(px, py + ROOF_FRAME_DY)
        verts.append(((fx, up, fz), n, t, (u, v)))
    return verts, ws.wound(verts, (0.0, 1.0, 0.0), 0, [(0, 1, 2), (0, 2, 3)])


def mesh_of(v: Variant, rect, uv_rect, light: str = "up"):
    """A tile's mesh in its cell's frame: a floor's flat diamond, a roof's raised plane, else the curtain. light: a curtain's
    shading normal, 'up' (the light the floor gets: right under a sky light, black where the only light is the player's, which
    is lower than most of a wall) or 'camera' (CAMERA_NORMAL)."""
    if v.key[0] == 0:
        return ws.floor_mesh(rect, uv_rect)
    if v.key[0] == 15:
        return roof_mesh(rect, uv_rect, v.roof)
    verts, tris = ws.tile_mesh(rect, uv_rect, "floor", PX_HEIGHT)
    if light == "camera":
        verts = [(p, CAMERA_NORMAL, t, uv) for p, _n, t, uv in verts]
    return verts, tris


def sprite_entity(model: str, x: int, y: int, n: int, ident: int, gap: int = 0, fade: bool = True) -> dict:
    """A cell's n-th sprite: walls_sprite.entity under this tool's name and id; `gap` steps of LAYER_GAP nearer the camera,
    along its axis (S, 1, S), so a cell's later wall layers lie over its earlier ones on the same pixels. fade False: no
    wall transparency component, so D2R does not fade the piece when it stands in front of the player (classic never does)."""
    e = ws.entity(model, x, y, 0, 0)
    if not fade:
        e["components"] = e["components"][:2]
    name = "mxt_%d_%d_%d" % (x, y, n)
    e["name"], e["id"] = name, ident
    g = gap * ws.LAYER_GAP
    e["components"][0]["position"] = {"x": round(x * ws.TILE + S * g, 4), "y": round(g, 4), "z": round(y * ws.TILE + S * g, 4)}
    for c, part in zip(e["components"], ("_t", "_m", "_w")):
        c["name"] = name + part
    return e


def chunk_entity(model: str, cx: int, cy: int, ident: int) -> dict:
    """The floor art model of chunk (cx, cy): at the chunk's first cell, no wall transparency."""
    e = ws.entity(model, cx * CHUNK, cy * CHUNK, 0, 0)
    name = "mxc_%d_%d" % (cx, cy)
    e["name"], e["id"] = name, ident
    e["components"] = e["components"][:2]
    for c, part in zip(e["components"], ("_t", "_m")):
        c["name"] = name + part
    return e


def chunk_mesh(quads, rects: dict, uvs: dict):
    """(vertices, triangles) of one chunk's floor art: quads [(dx, dy, layer, key)] in cells from the chunk's first cell; each
    a walls_sprite.floor_mesh at its cell, a layer a hair over the one below."""
    verts, tris = [], []
    for dx, dy, layer, k in quads:
        v, f = ws.floor_mesh(rects[k], uvs[k])
        base = len(verts)
        verts += [((p[0] + dx * ws.TILE, p[1] + layer * 0.01, p[2] + dy * ws.TILE), n, t, uv) for p, n, t, uv in v]
        tris += [(a + base, b + base, c + base) for a, b, c in f]
    return verts, tris


# ---- atlas -------------------------------------------------------------------------------------------------------------------
def make_atlas(pixels: dict, palette, pad: int = ws.PAD):
    """One atlas of {id: [(x, y, index)]}: -> (rgba (h, w, 4) uint8 with the colour bled into the padding, {id: (x, y)} of each
    picture's top left, {id: rect}). The width of WIDTHS that gives the smallest atlas (both sides a power of two), the
    squarest of equals."""
    rects = {k: ws.rect_of(px) for k, px in pixels.items()}
    sizes = {k: (r[2] - r[0], r[3] - r[1]) for k, r in rects.items()}
    widest = max(s[0] for s in sizes.values()) + 2 * pad
    best = None
    for width in WIDTHS:
        if width < widest:
            continue
        places, used = ws.pack(sizes, width, pad)
        height = 1 << max(int(math.log2(MIN_SIDE)), math.ceil(math.log2(used)))
        if best is None or (width * height, max(width, height)) < best[:2]:     # the smallest, then the squarest
            best = (width * height, max(width, height), width, height, places)
    if best is None:
        raise ValueError("make_atlas: a picture %d pixels wide fits no atlas" % widest)
    _area, _side, width, height, places = best
    index = np.zeros((height, width), np.uint8)
    for k, px in pixels.items():
        (ax, ay), (x0, y0, _x1, _y1) = places[k], rects[k]
        for x, y, c in px:
            index[ay + y - y0, ax + x - x0] = c
    return ws.bleed(palette[index]), places, rects


def albedo_file(albedo, name: str):
    """The owner-made picture for atlas `name`: `albedo` is a folder of <name>_atlas.png files or one such file."""
    if not albedo:
        return None
    p = Path(albedo)
    f = p / (name + "_atlas.png") if p.is_dir() else p
    return f if f.is_file() and f.name.lower() == name + "_atlas.png" else None


def texture_pixels(rgba: np.ndarray, name: str, opts) -> tuple:
    """(pixels to write, scale) of an atlas: the --albedo picture of the same layout (any whole multiple of the atlas's size,
    1x, 2x, 4x ...; its alpha is kept), else the atlas upscaled by --scale. --export writes the atlas first."""
    from PIL import Image
    if opts.export:
        Path(opts.export).mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgba, "RGBA").save(Path(opts.export) / (name + "_atlas.png"))
    art = albedo_file(opts.albedo, name)
    if art is None:
        return ws.upscale(rgba, opts.scale, opts.method), opts.scale
    img = Image.open(art).convert("RGBA")
    h, w = rgba.shape[:2]
    if img.width % w or img.height % h or img.width // w != img.height // h:
        raise SystemExit("sprite_scene: %s is %d x %d, not a whole multiple of the atlas's %d x %d" % (art, img.width, img.height, w, h))
    return np.array(img), img.width // w


def write_texture(dest: Path, px: np.ndarray, scale: int):
    import d2r_texture
    dest.parent.mkdir(parents=True, exist_ok=True)
    d2r_texture.write_bc3(dest, px, ws.SET_MIPS + int(math.log2(scale)))


# ---- models ------------------------------------------------------------------------------------------------------------------
class Models:
    """Writes sprite models and collects their model_lod_desc entries. lods: LOD files per model (1-5); pad: every mesh padded
    to the donor's counts and the donor's index entry shared (the build's old way, needs all 5 LODs); else the mesh's own
    counts and index records of its own (model_lod_desc.add `own`)."""

    def __init__(self, out: Path, read, lods: int = 1, pad: bool = False):
        self.out, self.lods, self.pad = Path(out), (ws.LODS if pad else lods), pad
        self.donors = [read(ws.DONOR[:-len(".model")] + "_lod%d.model" % n) for n in range(self.lods)]
        if not all(self.donors):
            raise SystemExit("sprite_scene: the donor's LOD files are not at hand; run once with MXL_SLOT set")
        self.entries, self.own, self.files = [], {}, {}

    def write(self, path: str, verts, tris, tex: dict):
        dest = self.out / path[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        for n, donor in enumerate(self.donors):
            data, lo, hi = ws.sprite_model(donor, verts, tris, tex, self.pad)
            dest.with_name(dest.stem + "_lod%d.model" % n).write_bytes(data)
            size += len(data)
        for n in range(self.lods, ws.LODS):       # an earlier run's further LODs
            old = dest.with_name(dest.stem + "_lod%d.model" % n)
            if old.exists():
                old.unlink()
        box = (tuple(lo), tuple(hi))
        self.entries.append((path, ws.DONOR, box))
        if not self.pad:
            self.own[path] = [[box]] * self.lods
        self.files[path] = size

    def write_index(self, base: bytes) -> bytes:
        import model_lod_desc
        import walls_hd
        table = model_lod_desc.add(base, {p: d for p, d, _b in self.entries}, {p: b for p, _d, b in self.entries}, self.own or None)
        dest = self.out / walls_hd.LOD_DESC[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(table)
        return table


def existing_tiles(out: Path, group: str) -> set:
    """{(key, variant)} of the tile models a group already has under `out` (an earlier run's)."""
    folder = Path(out) / (MODEL % (group, "x", 0, 0, 0))[len("data/"):]
    found = set()
    for f in folder.parent.glob("*_lod0.model"):
        got = parse_name(f.name[:-len("_lod0.model")])
        if got:
            found.add(got)
    return found


def write_groups(out: Path, handles, needed: dict, models: Models, opts) -> dict:
    """The atlas and the models of every tile group. needed: {group: {(key, variant)}} of this run; a group's earlier tiles
    under `out` are kept in its atlas. -> {group: {"atlas": bytes, "tiles": n, "size": (w, h), "scale": n}}."""
    stats = {}
    tex_base = {"nrm": ws.FLAT_NRM, "orm": ws.FLAT_ORM}
    for group in sorted(needed):
        h, variants = next((h, t) for h in handles for p, t in h.by_file.items() if h.group(p) == group)
        tiles = {}
        for key, n in needed[group] | existing_tiles(out, group):
            vs = variants.get(key)
            if vs and n < len(vs):
                px = vs[n].pixels
                if opts.black_fill == "cut" and CLASS_OF[key[0]] == WALL:
                    px = cut_black(px, h.palette) or px
                tiles[(key, n)] = px
        rgba, places, rects = make_atlas({tile_name(*t): px for t, px in tiles.items()}, h.palette)
        if getattr(opts, "pinholes", "fill") == "fill":
            rgba = fill_pinholes(rgba)
        if opts.export:
            Path(opts.export).mkdir(parents=True, exist_ok=True)
            (Path(opts.export) / (group + "_atlas.json")).write_text(json.dumps(
                {"atlas": group, "size": [rgba.shape[1], rgba.shape[0]], "maps": sorted(x.name for x in handles),
                 "tiles": {k: {"atlas_xy": places[k], "sprite_rect": rects[k]} for k in sorted(places)}}, indent=0), encoding="utf-8")
        px, scale = texture_pixels(rgba, group, opts)
        alb = ATLAS % group
        dest = Path(out) / alb[len("data/"):]
        write_texture(dest, px, scale)
        H, W = float(rgba.shape[0]), float(rgba.shape[1])
        for (key, n) in sorted(tiles):
            name = tile_name(key, n)
            (ax, ay), r = places[name], rects[name]
            uv = (ax / W, ay / H, (ax + r[2] - r[0]) / W, (ay + r[3] - r[1]) / H)
            verts, tris = mesh_of(variants[key][n], r, uv, getattr(opts, "light", "up"))
            if tris:
                models.write(MODEL % ((group, name.split("_")[0]) + key), verts, tris, dict(tex_base, alb=alb))
        stats[group] = {"atlas": dest.stat().st_size, "tiles": len(tiles), "size": [px.shape[1], px.shape[0]], "scale": scale}
    return stats


def fill_pinholes(rgba: np.ndarray, rounds: int = 2) -> np.ndarray:
    """The atlas with its pinholes closed: a transparent texel with opaque texels on at least three of its four sides
    becomes opaque, `rounds` times (holes of one or two texels; its colour is the bled one). Median's wall art has stray
    pixels of the transparent colour inside its stone: classic shows the dark behind them, HD the lit floor behind the wall,
    as bright specks all over a wall."""
    a = rgba[..., 3] > 0
    for _ in range(rounds):
        p = np.pad(a, 1)
        a = a | ((p[:-2, 1:-1].astype(np.uint8) + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) >= 3)
    out = rgba.copy()
    out[..., 3] = np.where(a, 255, 0).astype(np.uint8)
    return out


def solid_edges(rgba: np.ndarray, steps: int = 2) -> np.ndarray:
    """The atlas with every picture's alpha spread `steps` texels into its bled padding. A floor tile's picture is a pixel
    staircase: 79 rows, the lower two edges up to two texels inside the cell's exact diamond, which the mesh draws. Classic
    closes that with the next tile's upper edge; here each cell samples its own picture, so without this the cut-out
    leaves a hairline of the ground under the art along every cell's lower edges (lane hdtools-spritewall, Fauztinville)."""
    a = rgba[..., 3]
    for _ in range(steps):
        p = np.pad(a, 1)
        a = np.maximum.reduce([p[1:-1, 1:-1], p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])
    out = rgba.copy()
    out[..., 3] = a
    return out


def write_floor(out: Path, h: MapHandle, floors: list, models: Models, opts, ids) -> tuple:
    """A map's floor art: one atlas of its floor tiles, one model per chunk. -> (entities, atlas bytes)."""
    if not floors:
        return [], 0
    rgba, places, rects = make_atlas({v.key: v.pixels for _x, _y, _n, v in floors}, h.palette)
    rgba = solid_edges(rgba, min(2, ws.PAD - 1))
    name = h.stem + "_floor"
    px, scale = texture_pixels(rgba, name, opts)
    alb = FLOOR_ATLAS % h.stem
    dest = Path(out) / alb[len("data/"):]
    write_texture(dest, px, scale)
    H, W = float(rgba.shape[0]), float(rgba.shape[1])
    uvs = {k: (places[k][0] / W, places[k][1] / H, (places[k][0] + r[2] - r[0]) / W, (places[k][1] + r[3] - r[1]) / H) for k, r in rects.items()}
    chunks = {}
    for x, y, n, v in floors:
        chunks.setdefault((x // CHUNK, y // CHUNK), []).append((x % CHUNK, y % CHUNK, n, v.key))
    ents = []
    for (cx, cy) in sorted(chunks):
        path = CHUNK_MODEL % (h.stem, cx, cy)
        models.write(path, *chunk_mesh(chunks[(cx, cy)], rects, uvs), {"alb": alb, "nrm": ws.FLAT_NRM, "orm": ws.FLAT_ORM})
        ents.append(chunk_entity(path, cx, cy, next(ids)))
    return ents, dest.stat().st_size


# ---- scene -------------------------------------------------------------------------------------------------------------------
def _cell_of_name(name: str):
    """(prefix, x, y) of an entity name `mxw_3_4_0`, (prefix, None, None) of `mxs_17` or `mxj_2_1`, else None."""
    parts = str(name or "").split("_")
    if len(parts[0]) != 3 or not parts[0].startswith("mx"):
        return None
    if len(parts) == 4 and all(p.lstrip("-").isdigit() for p in parts[1:]):
        return parts[0], int(parts[1]), int(parts[2])
    return parts[0], None, None


def _near(cell, cells: set, reach: int) -> bool:
    return any((cell[0] + dx, cell[1] + dy) in cells for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1))


def dropped(e: dict, cells: set, everything: bool = False):
    """Why merge_scene drops a base entity (the module's rule), or None when it stays. everything: every entity that draws
    a model goes (the all-classic scene: no piece of the base, D2R's or the build's, next to the map's own art)."""
    import walls_hd
    got = _cell_of_name(e.get("name"))
    if everything and walls_hd.models_of(e):
        return "own" if got and got[0] in ("mxt", "mxc") else "base piece"
    t = walls_hd.transform(e)
    p = (t or {}).get("position") or {}
    at = (int(float(p.get("x", 0.0)) // ws.TILE), int(float(p.get("z", 0.0)) // ws.TILE))
    if got is None:
        if t is not None and walls_hd.wall_entities({"entities": [e]}) and _near(at, cells, 1):
            return "d2r wall"
        return None
    prefix, x, y = got
    if prefix in ("mxt", "mxc"):
        return "own"
    if prefix in ("mxw", "mxs") and x is not None:
        return "cell piece" if (x, y) in cells else None
    if prefix == "mxp" and x is not None:
        return "set piece" if _near((x, y), cells, REACH) else None
    if prefix in ("mxs", "mxj"):
        return "structure" if t is not None and _near(at, cells, REACH) else None
    return None


def merge_scene(scene: dict, new: list, cells: set, everything: bool = False) -> tuple:
    """The base scene with `new` (this tool's entities) in place of the base's pieces of the sprite cells `cells` (the
    module's rule). `dependencies.models`: the models of the entities left, and what the base listed without an entity
    drawing it. -> (scene, {reason: dropped})."""
    import collections
    import walls_hd
    out = dict(scene)
    stats = collections.Counter()
    kept, gone = [], []
    for e in scene.get("entities", ()):
        why = dropped(e, cells, everything)
        if why:
            stats[why] += 1
            gone.append(e)
        else:
            kept.append(e)
    out["entities"] = kept + new
    deps = dict(scene.get("dependencies") or {})
    drawn = {m for e in out["entities"] for m in walls_hd.models_of(e)}
    orphan = {m for e in gone for m in walls_hd.models_of(e)} - drawn
    listed = [d.get("path") for d in deps.get("models") or ()]
    deps["models"] = [{"path": m} for m in sorted((set(listed) - orphan) | drawn)]
    out["dependencies"] = deps
    return out, dict(stats)


def bare_biome(biome: dict, name: str) -> dict:
    """A copy of a biome named `name` on which nothing grows: no grass and no clutter models on any layer of any quality
    tier (the values D2R's own bare layers have). The ground's textures stay."""
    import copy
    out = copy.deepcopy(biome)
    out["name"] = name
    for tier in TIERS:
        for lay in (out.get(tier) or {}).get("terrainLayers") or ():
            lay["GrassDensity"] = 0.0
            lay["Clutter"] = []
    return out


def black_ground(biome: dict) -> dict:
    """A copy of a biome whose every terrain layer, in every quality tier, is black (BLACK_GROUND: black albedo, flat normal,
    rough and unlit ORM): where no floor art lies the ground shows nothing, as classic shows black where a map has no floor."""
    import copy
    out = copy.deepcopy(biome)
    paths = {"Albedo": BLACK_GROUND % "alb", "Normal": BLACK_GROUND % "nrm", "ORM": BLACK_GROUND % "orm"}
    for tier in TIERS:
        for lay in (out.get(tier) or {}).get("terrainLayers") or ():
            lay.update(paths)
    deps = out.setdefault("dependencies", {}).setdefault("textures", [])
    have = {d.get("path") for d in deps}
    deps += [{"path": p} for p in paths.values() if p not in have]
    return out


def write_black_ground(out: Path) -> list:
    """The three textures of the black terrain layer, in the format and size of D2R's terrain textures. -> their files."""
    import d2r_texture
    px = np.zeros((GROUND_SIZE, GROUND_SIZE, 4), np.uint8)
    files = []
    for kind, rgba, linear in (("alb", (0, 0, 0, 128), False), ("nrm", (255, 128, 0, 128), True), ("orm", (0, 255, 0, 0), True)):
        dest = Path(out) / (BLACK_GROUND % kind)[len("data/"):]
        if not dest.is_file():
            px[...] = rgba
            dest.parent.mkdir(parents=True, exist_ok=True)
            d2r_texture.write_bc3(dest, px, GROUND_MIPS, linear=linear)
        files.append(dest)
    return files


def key_power(vis: dict) -> float:
    return max((float(c.get("power", 0.0)) for e in vis.get("entities", ()) if e.get("name") == KEY_LIGHT
                for c in e.get("components", ()) if c.get("type") == "DirectionalLightDefinitionComponent"), default=0.0)


def classic_light(ambient, rule=None) -> dict:
    """The light file values of a level whose classic ambient light is `ambient` (levels.txt Intensity, Red, Green, Blue,
    0-255): the key light in the ambient's linear colour (brightest channel 1) and power, the rule's player light, no sky
    light, no fog, a neutral grading. ambient None: DEFAULT_LIGHT."""
    rule = dict(LIGHT_RULE, **(rule or {}))
    if ambient is None:
        return dict(DEFAULT_LIGHT)
    i, *rgb = ambient
    lin = [(i / 255.0 * c / 255.0) ** AMBIENT_GAMMA for c in rgb]
    top = max(lin)
    key = tuple(round(c / top, 4) for c in lin) if top > 0 else (1.0, 1.0, 1.0)
    return {"key": key, "power": round(rule["key"] * top, 4), "ibl": rule["ibl"], "player": rule["player"],
            "reach": rule["reach"], "attenuation": rule["attenuation"], "lut": rule["lut"], "fog": 0.0}


def classic_vis(vis: dict, name: str, light: dict) -> dict:
    """A copy of a visual data file named `name` with the map's light (classic_light, a CLASSIC_LIGHT entry): the global key
    light's colour and power (and its specular share, `spec`), and where given the image based light's intensity, the player's light power, reach and
    fall-off, the grading LUT (`lut`) and the fog densities (`fog`); no screen particles."""
    import copy
    out = copy.deepcopy(vis)
    out["name"] = name
    for e in out.get("entities", ()):
        for c in e.get("components", ()):
            if c.get("type") == "VisualDataComponent":
                for mine, theirs in (("ibl", "iblIntensity"), ("player", "playerUnitLightPower"), ("reach", "playerUnitLightDistanceScaler"),
                                     ("attenuation", "playerUnitLightAttenuation"), ("lut", "gradingLutFile")):
                    if light.get(mine) is not None:
                        c[theirs] = light[mine]
                if "screenspaceVfx" in c:
                    c["screenspaceVfx"] = ""   # the biome's screen particles (Duncraig's green motes): classic has none
                if light.get("fog") is not None:
                    for k in ("fogDensity", "depthFogDensity", "heightFogDensity"):
                        if k in c:
                            c[k] = light["fog"]
            if e.get("name") == KEY_LIGHT and c.get("type") == "DirectionalLightDefinitionComponent":
                c["color"] = dict(zip("xyz", light["key"]))
                c["power"] = light["power"]
                if light.get("spec") is not None:
                    c["specularContribution"] = light["spec"]
    if light.get("lut"):
        other = out.setdefault("dependencies", {}).setdefault("other", [])
        other[:] = [d for d in other if not str(d.get("path", "")).startswith("data/hd/env/lut/")] + [{"path": light["lut"]}]
    return out


def light_monsters(ds, monsters) -> list:
    """The classic lamps of a map: [(sub-tile x, sub-tile y, Light, (r, g, b))] for each monster of the .ds1 (type 1, id =
    monstats hcIdx) that never moves and cannot be killed (Velocity and Run 0, killable empty: Median's idle*light lamps)
    and has a light (monstats2 Light > 0). monsters: {hcIdx: (Light, (r, g, b))} of those monsters (scenery_lights)."""
    return [(x, y) + monsters[i] for t, i, x, y, *_f in getattr(ds, "objects", ()) if t == 1 and i in monsters]


def scenery_lights(excel: Path) -> dict:
    """{hcIdx: (Light, (r, g, b))} of the monsters of `excel` (monstats.txt, monstats2.txt) light_monsters takes."""
    import maps_hd
    ex = {r.get("Id"): r for r in maps_hd.read_table(Path(excel) / "monstats2.txt")}
    out = {}
    for r in maps_hd.read_table(Path(excel) / "monstats.txt"):
        r2 = ex.get(r.get("MonStatsEx"))
        if not r2 or not str(r.get("hcIdx", "")).isdigit() or (r.get("killable") or "").strip():
            continue
        if (r.get("Velocity") or "0") != "0" or (r.get("Run") or "0") != "0":
            continue
        light = int(r2.get("Light") or 0)
        if light > 0:
            out[int(r["hcIdx"])] = (light, tuple(int(r2.get("light-" + c) or 0) for c in "rgb"))
    return out


def lit_objects(ds, lit) -> list:
    """The classic lit objects of a map (torches, fires, braziers): [(sub-tile x, sub-tile y, Light, (r, g, b))] for each
    object of the .ds1 (type 2, id = objpreset Index of the map's act) in `lit` (object_lights)."""
    act = str(getattr(ds, "act", 0) + 1)
    return [(x, y) + lit[(act, str(i))] for t, i, x, y, *_f in getattr(ds, "objects", ()) if t == 2 and (act, str(i)) in lit]


def object_lights(excel: Path, d2r_excel: Path) -> dict:
    """{(act, objpreset Index): (Light, (r, g, b))} of the objects that give light as the map starts: the mod's objects.txt
    (`excel`) Lit0 (the neutral mode), or Lit1 / Lit2 for objects whose init function puts them in that mode (InitFn not 0
    or 1: torches, braziers, fires; a shrine or chest that lights up only when used gives no light here). A .ds1 object id
    is D2R's objpreset.txt Index of the map's act -> ObjectClass -> D2R objects.txt Class -> its Id -> the mod's row of
    that Id (classic's objects.txt has no Class column)."""
    import maps_hd
    by = {}
    for r in maps_hd.read_table(Path(excel) / "objects.txt"):
        lit = [int(r.get("Lit%d" % m) or 0) for m in range(3)]
        light = lit[0] or (max(lit[1:]) if (r.get("InitFn") or "0") not in ("0", "1") else 0)
        if light > 0 and str(r.get("Id", "")).isdigit():
            by[r["Id"]] = (light, tuple(int(r.get(c) or 0) for c in ("Red", "Green", "Blue")))
    ids = {(r.get("Class") or "").lower(): r.get("Id", r.get("*ID")) for r in maps_hd.read_table(Path(d2r_excel) / "objects.txt")}
    return {(str(r.get("Act")), str(r.get("Index"))): by[ids[(r.get("ObjectClass") or "").lower()]]
            for r in maps_hd.read_table(Path(d2r_excel) / "objpreset.txt")
            if ids.get((r.get("ObjectClass") or "").lower()) in by}


def point_entity(x: int, y: int, n: int, ident: int, light: int, rgb, rule=None) -> dict:
    """A point light at sub-tile (x, y) for a classic lamp of radius `light` and colour rgb (0-255, linear in HD). Named as a
    cell entity of this tool (mxc_<cell x>_<cell y>_<n>), so a later run drops it with the rest of its own."""
    rule = dict(LIGHT_RULE, **(rule or {}))
    lin = [(c / 255.0) ** AMBIENT_GAMMA for c in rgb]
    top = max(lin) or 1.0
    name = "mxc_%d_%d_%d" % (x // 5, y // 5, n)
    return {"type": "Entity", "name": name, "id": ident, "components": [
        {"type": "TransformDefinitionComponent", "name": name + "_t",
         "position": {"x": x * ws.TILE / 5 + 1.0, "y": rule["point_height"], "z": y * ws.TILE / 5 + 1.0},
         "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}, "scale": {"x": 1.0, "y": 1.0, "z": 1.0}, "inheritOnlyPosition": False},
        {"type": "PointLightDefinitionComponent", "name": name + "_l", "color": dict(zip("xyz", (round(c / top, 4) for c in lin))),
         "power": rule["point"], "radius": round(light * rule["point_reach"], 3), "attenuation": rule["point_attenuation"],
         "lightMask": 1, "isLocalLight": False, "diffuseContribution": 1.0, "specularContribution": 0.0}]}


def _own_or_d2r(rel: str, roots, read) -> dict:
    own = next((Path(r) / rel[len("data/"):] for r in roots if r and (Path(r) / rel[len("data/"):]).is_file()), None)
    return json.loads(own.read_text("utf-8-sig") if own else read(rel).decode("utf-8-sig"))


def write_classic_biome(out: Path, base, scene: dict, read, key: str, ambient=None) -> tuple:
    """Write map `key`'s own biome for the all-classic scene into `out`: the scene's biome bare (bare_biome), its ground black
    (black_ground, the textures written too) and its light the map's (classic_vis of the biome's day file, written as
    mxl2012_classic_<key>.json: classic_light of the level's classic `ambient` with CLASSIC_LIGHT's entry over it; a map
    without an ambient: CLASSIC_LIGHT's entry, else DEFAULT_LIGHT when the biome's key light is off, else the biome's light
    as it is). Files are read from `out`, then `base`, then D2R. A scene already on such a biome keeps it.
    -> (biome name, the light written or None)."""
    import map_tint
    stem = Path(str(scene.get("biomeFilename") or "")).stem
    if stem.startswith(CLASSIC_PREFIX):
        return stem, None
    name = CLASSIC_PREFIX + key
    biome = black_ground(bare_biome(_own_or_d2r(BIOME % stem, (out, base), read), name))
    write_black_ground(out)
    light, rel = CLASSIC_LIGHT.get(key), None
    if ambient is not None:
        over = dict(light or {})
        gain, pgain = over.pop("gain", None), over.pop("pgain", None)
        light = dict(classic_light(ambient), **over)
        if gain is not None:
            light["power"] = round(light["power"] * gain, 4)
        if pgain is not None:
            light["player"] = round(light["player"] * pgain, 4)
    try:
        rel = map_tint.day_vis(biome)
    except ValueError:
        pass
    if rel:
        vis = _own_or_d2r(rel, (out, base), read)
        light = light or (DEFAULT_LIGHT if key_power(vis) <= 0.0 else None)
        if light:
            dest = Path(out) / (VIS % name)[len("data/"):]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(classic_vis(vis, name, light), separators=(",", ":")), encoding="utf-8")
            biome = map_tint.tinted_biome(biome, name, VIS % name)
    else:
        light = None
    dest = Path(out) / (BIOME % name)[len("data/"):]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(biome, separators=(",", ":")), encoding="utf-8")
    return name, light


def bare_ground(scene: dict, cells: set, name: str) -> tuple:
    """The scene for floor art on `cells`: its biome is the bare copy `name` (bare_biome of the scene's own), and the cells'
    per-tile biome overrides are gone, so under the art lies one plain ground and no blade or stone of a biome stands
    through it. cells None: every override goes. -> (scene, overrides dropped)."""
    out = dict(scene)
    old = str(scene.get("biomeFilename") or "")
    over = [o for o in scene.get("perTileBiomeOverrides") or () if cells is not None and (o.get("tileX"), o.get("tileY")) not in cells]
    gone = len(scene.get("perTileBiomeOverrides") or ()) - len(over)
    out["biomeFilename"], out["perTileBiomeOverrides"] = BIOME % name, over
    named = {str(o.get("biomeFilename")) for o in over} | {BIOME % name}
    deps = dict(scene.get("dependencies") or {})
    js = [d for d in deps.get("json") or () if not str(d.get("path", "")).startswith("data/hd/env/biome/") or d["path"] in named]
    deps["json"] = js + [{"path": p} for p in sorted(named - {d.get("path") for d in js})]
    out["dependencies"] = deps
    return out, gone if old else 0


def write_bare_biome(out: Path, base, scene: dict, read) -> str:
    """Write the bare copy of the scene's biome into `out`; -> its name. The biome is read from `out`, then `base` (mod data
    folders), then D2R (read(rel) -> bytes). A scene already on a bare biome keeps it."""
    stem = Path(str(scene.get("biomeFilename") or "")).stem
    if stem.startswith(BARE_PREFIX):
        return stem
    rel = BIOME % stem
    own = next((Path(r) / rel[len("data/"):] for r in (out, base) if r and (Path(r) / rel[len("data/"):]).is_file()), None)
    biome = json.loads(own.read_text("utf-8-sig") if own else read(rel).decode("utf-8-sig"))
    name = BARE_PREFIX + (stem[len("mxl2012_"):] if stem.startswith("mxl2012_") else stem)
    dest = Path(out) / (BIOME % name)[len("data/"):]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(bare_biome(biome, name), separators=(",", ":")), encoding="utf-8")
    return name


def count_ids(scene: dict, start: int = ID_BASE):
    """Ids from `start` up that no entity of the scene has."""
    used = {e.get("id") for e in scene.get("entities", ()) if _cell_of_name(e.get("name")) is None or e["name"][:3] not in ("mxt", "mxc")}
    n = start
    while True:
        if n not in used:
            yield n
        n += 1


def scene_file(root, key: str) -> Path:
    """Where a mod data folder has the map's scene: `preset/<key>.json`, or, once tools/ds1_paths.py has moved an edited D2R
    map (a later build step), `preset/mxl2012/<key>.json`."""
    import ds1_paths
    preset = Path(root) / "hd" / "env" / "preset"
    moved = preset / ds1_paths.PREFIX / (key + ".json")
    return moved if moved.is_file() else preset / (key + ".json")


def base_scene(h: MapHandle, base, out, biome=None) -> tuple:
    """(scene, source) of the map's base: the built scene under `base` (a mod data folder, default `out`), else D2R's own,
    else an empty scene with the biome."""
    import maps_hd
    import walls_hd
    for root in (base, out):
        f = scene_file(root, h.key) if root else None
        if f is not None and f.is_file():
            return json.loads(f.read_text("utf-8-sig")), "built"
    try:
        scene = walls_hd.d2r_scene(h.key)
    except SystemExit:
        scene = None
    if scene is not None:
        return scene, "d2r"
    return json.loads(maps_hd.scene_json(biome or h.biome or EMPTY_BIOME.get(h.act, EMPTY_BIOME[1]))), "empty"


def is_flat(scene: dict) -> bool:
    """Whether the flat build painted this scene's floor (its models are under /mxl/flat/)."""
    import walls_hd
    return any("/mxl/flat/" in m for e in scene.get("entities", ()) for m in walls_hd.models_of(e))


def limits(h: MapHandle) -> tuple:
    import walls_hd
    return walls_hd.MAP_LIMITS.get(h.name, (walls_hd.MAX_PLACED, walls_hd.MAX_BYTES))


def build_map(h: MapHandle, scene: dict, source: str, opts) -> dict:
    """The map's plan: which tiles stand where. -> {"walls": [(x, y, layer, Variant)], "floors": [...], "skipped": n}."""
    walls = h.walls(frozenset(opts.orientations) | (SPECIAL if h.stem in DOOR_MAPS else frozenset()))
    flat = is_flat(scene)
    skip = h.flat_keys({v.key for *_r, v in walls}) if flat and opts.rule == "auto" else set()
    floors = [] if flat and opts.floors == "blocked" else h.floors(opts.floors)   # the flat build painted its blocked floors
    return {"walls": [w for w in walls if w[3].key not in skip], "floors": floors,
            "skipped": sum(1 for w in walls if w[3].key in skip), "flat": flat, "source": source}


def build(handles: list, out: Path, opts) -> dict:
    """Builds the maps' sprite scenes into `out`. -> {map name: stats}."""
    import walls_hd
    out = Path(out)
    read = walls_hd.d2r_bytes
    models = Models(out, read, opts.lods, opts.pad)
    plans, needed = {}, {}
    for h in handles:
        scene, source = base_scene(h, opts.base, out, opts.biome)
        plans[h.name] = (scene, build_map(h, scene, source, opts))
        for _x, _y, _n, v in plans[h.name][1]["walls"]:
            needed.setdefault(h.group(h.source[v.key]), set()).add((v.key, v.n))
    flat_files = ws.flat_textures(out)
    groups = write_groups(out, handles, needed, models, opts)
    stats = {}
    for h in handles:
        scene, plan = plans[h.name]
        ids = count_ids(scene)
        new, per_cell, used = [], {}, {}
        for x, y, n, v in plan["walls"]:
            group = h.group(h.source[v.key])
            path = MODEL % ((group, tile_name(v.key, v.n).split("_")[0]) + v.key)
            if path not in models.files:
                continue                                  # a picture all under the floor line: nothing to draw
            i = per_cell.get((x, y), 0)
            per_cell[(x, y)] = i + 1
            new.append(sprite_entity(path, x, y, i, next(ids), 0 if v.key[0] == 15 else i, getattr(opts, "fade", "wall") == "wall"))
            used[path] = group
        floor_ents, floor_atlas = write_floor(out, h, plan["floors"], models, opts, ids)
        art = {(x, y) for x, y, _n, _v in plan["floors"]}
        cells = set(per_cell) | {(x, y) for x, y, _n, v in plan["floors"] if v.blocked}   # a walkable floor replaces no piece
        bare, light, lamp_ents = 0, None, []
        classic = bool(getattr(opts, "classic", False))
        if classic:
            name, light = write_classic_biome(out, opts.base, scene, read, h.stem, getattr(h, "ambient", None))
            scene, bare = bare_ground(scene, None, name)                                    # no biome override anywhere
            lamps = light_monsters(h.ds, getattr(h, "lamps", None) or {}) + lit_objects(h.ds, getattr(h, "lit", None) or {})
            lamp_ents = [point_entity(x, y, n, next(ids), r, rgb) for n, (x, y, r, rgb) in enumerate(lamps)]
        elif art and getattr(opts, "ground", "keep") == "bare":
            scene, bare = bare_ground(scene, art, write_bare_biome(out, opts.base, scene, read))
        limit, max_bytes = limits(h)
        base_left = len(merge_scene(scene, [], cells, classic)[0]["entities"])
        kept = walls_hd.cap(new, max(0, limit - base_left - len(floor_ents) - len(lamp_ents)))
        while True:
            merged, gone = merge_scene(scene, kept + floor_ents + lamp_ents, cells, classic)
            text = json.dumps(merged, separators=(",", ":"))
            size = len(text.encode("utf-8"))
            if size <= max_bytes or not kept:
                break
            kept = walls_hd.cap(new, min(len(kept) - 1, int(len(kept) * max_bytes / size)))
        dest = scene_file(out, h.key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        classes = {}
        for _x, _y, _n, v in plan["walls"]:
            classes[CLASS_OF[v.key[0]]] = classes.get(CLASS_OF[v.key[0]], 0) + 1
        chunk_paths = [walls_hd.model_of(e) for e in floor_ents]
        stats[h.name] = {
            "level": h.level, "base": plan["source"], "flat_base": plan["flat"], "act": h.act, "classic": classic,
            "classic_light": light, "cells_without_floor": (h.ds.width + 1) * (h.ds.height + 1) - len(art) if classic else None,
            "wall_pieces": len(new), "classes": classes, "painted_by_flat_build": plan["skipped"],
            "distinct_tiles": len(used), "variant_tiles": sum(1 for p in used if parse_name(p.rsplit("/", 1)[-1][:-len(".model")])[1]),
            "floor_cells": len(plan["floors"]), "floor_chunks": len(floor_ents), "lamps": len(lamp_ents), "floor_atlas_bytes": floor_atlas,
            "biome": Path(str(merged.get("biomeFilename") or "")).stem, "biome_overrides_dropped": bare,
            "biome_overrides": len(merged.get("perTileBiomeOverrides") or ()),
            "entities": len(merged["entities"]), "limit": limit, "capped": len(new) - len(kept), "base_entities_kept": base_left,
            "base_entities_dropped": gone, "scene_bytes": size,
            "groups": sorted(set(used.values())),
            "bytes": {"models": sum(models.files[p] for p in used) + sum(models.files[p] for p in chunk_paths),
                      "albedo": sum(groups[g]["atlas"] for g in set(used.values())) + floor_atlas,
                      "normal": flat_files[0].stat().st_size, "orm": flat_files[1].stat().st_size}}
    index = out / walls_hd.LOD_DESC[len("data/"):]
    lod_base = Path(opts.lod_base) if opts.lod_base else index if index.exists() else \
        Path(opts.base) / walls_hd.LOD_DESC[len("data/"):] if opts.base and (Path(opts.base) / walls_hd.LOD_DESC[len("data/"):]).exists() else None
    table = models.write_index(lod_base.read_bytes() if lod_base else read(walls_hd.LOD_DESC))
    stats["_all"] = {"maps": len(handles), "lods": models.lods, "padded": models.pad, "models": len(models.files),
                     "model_bytes": sum(models.files.values()), "atlases": {g: s for g, s in groups.items()},
                     "albedo_bytes": sum(s["atlas"] for s in groups.values()), "lod_desc_bytes": len(table),
                     "lod_base": str(lod_base or "D2R"), "px_per_height": round(PX_HEIGHT, 3)}
    return stats


# ---- command line --------------------------------------------------------------------------------------------------------------
def listed_maps(path) -> list:
    """The maps of a list file ({"maps": ["expansion/ghetto/cypherpunk.ds1", ...]}); none when the file is missing."""
    p = Path(path)
    if not p.is_file():
        return []
    return [str(m) for m in json.loads(p.read_text("utf-8")).get("maps", [])]


def handles_for(names: list, opts, inp=None) -> list:
    import maps_hd
    inp = inp or maps_hd.Inputs.load()
    files = [n for n in names if Path(n).is_file() and n.lower().endswith(".ds1")]
    plan, levels, lamps, lit = None, {}, None, None
    if len(files) < len(names):
        maps, _dt1s, _levels = maps_hd.plan(inp)
        plan = {e["map"].lower(): e for e in maps}
        levels = {int(r["Id"]): (r.get("LevelName") or r.get("Name") or "") for r in inp.mod_levels if str(r.get("Id", "")).isdigit()}
    out = []
    for n in names:
        if n in files:
            name = getattr(opts, "name", None) if len(files) == 1 else None    # one name cannot be two maps'
            name = name.replace("\\", "/").lower() if name else None
            out.append(MapHandle.from_file(n, inp, opts.dt1.split(",") if opts.dt1 else None, opts.act, name, opts.biome))
            continue
        low = n.replace("\\", "/").lower()
        low = low if low.endswith(".ds1") else low + ".ds1"
        hits = [k for k in plan if k == low or k.rsplit("/", 1)[-1] == low]
        if len(hits) != 1:
            raise SystemExit("sprite_scene: %s names %d maps%s" % (n, len(hits), ": " + ", ".join(hits[:6]) if hits else ""))
        e = plan[hits[0]]
        ids = sorted({u["level"] for u in maps_hd.level_usage(inp.mod_levels, inp.mod_prest).get(hits[0][:-4], ()) if u["level"]})
        h = MapHandle.from_plan(inp, e, "; ".join("%d %s" % (i, levels.get(i, "")) for i in ids))
        h.ambient = level_ambient(inp.mod_levels, ids)
        if lamps is None:
            lamps = scenery_lights(maps_hd.default_extract() / "data" / "global" / "excel")
            lit = object_lights(maps_hd.default_extract() / "data" / "global" / "excel",
                                maps_hd.default_d2r() / "data" / "global" / "excel")
        h.lamps, h.lit = lamps, lit
        out.append(h)
    return out


def level_ambient(rows, ids):
    """(Intensity, Red, Green, Blue) of the first of the level ids `ids` in levels.txt rows that has a fixed ambient light
    (Intensity > 0; 0 is classic's day cycle, which none of the 17 maps uses), else None."""
    by = {str(r.get("Id", "")): r for r in rows}
    for i in ids:
        r = by.get(str(i))
        if r and str(r.get("Intensity", "")).isdigit() and int(r["Intensity"]) > 0:
            return tuple(int(r.get(k) or 0) for k in ("Intensity", "Red", "Green", "Blue"))
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("targets", nargs="+", help="MAP [MAP ...] OUT")
    b.add_argument("--all", action="store_true", help="the 17 maps of walls_hd.MAPS")
    b.add_argument("--list", help='a json file {"maps": [...]}; with no map in it nothing is done')
    b.add_argument("--base", help="the mod data folder whose scenes are the base (default: OUT)")
    b.add_argument("--lod-base", help="the model_lod_desc.bin the models are added to (default: OUT's, else --base's, else D2R's)")
    b.add_argument("--lods", type=int, default=1, choices=range(1, ws.LODS + 1), help="LOD files per model")
    b.add_argument("--pad", action="store_true", help="pad every mesh to the donor's counts and share its index entry (5 LODs)")
    b.add_argument("--scale", type=int, default=1, help="upscale the atlases (Lanczos unless --method)")
    b.add_argument("--method", choices=("lanczos", "nearest"), default="lanczos")
    b.add_argument("--black-fill", choices=("keep", "cut"), default="keep", help="cut: a wall tile's black fill is transparent")
    b.add_argument("--fade", choices=("wall", "none"), default="wall", help="none: a sprite in front of the player stays solid, as in classic (no wall transparency component)")
    b.add_argument("--pinholes", choices=("fill", "keep"), default="fill", help="fill: stray transparent pixels inside a wall tile's art are closed")
    b.add_argument("--export", help="write every atlas here as <name>_atlas.png / .json, for art made outside this tool")
    b.add_argument("--albedo", help="a folder of <name>_atlas.png (or one such file): used instead of the atlas, any whole multiple of its size")
    b.add_argument("--light", choices=("up", "camera"), default="up", help="a wall's shading normal: up (as the floor), or tilted to the camera for levels lit by the player's light alone")
    b.add_argument("--floors", choices=("blocked", "all", "none"), default="blocked", help="floor tiles drawn as classic art")
    b.add_argument("--ground", choices=("keep", "bare"), default="keep", help="bare: under floor art the scene's biome without grass and clutter, and no biome override")
    b.add_argument("--classic", action="store_true", help="the whole map from its own classic art: --floors all --ground bare --rule all, every model of the base scene dropped, black ground where the map has no floor, and the map's own light")
    b.add_argument("--rule", choices=("auto", "all"), default="auto", help="auto: tiles the flat build painted on the floor are not drawn upright")
    b.add_argument("--orientations", default=",".join(str(o) for o in sorted(DRAWN)), help="wall layer orientations drawn (10, 11 also on DOOR_MAPS)")
    b.add_argument("--dt1", help="a .ds1 file's tile files, in order (paths below data/global/tiles or files)")
    b.add_argument("--act", type=int, help="a .ds1 file's palette (1-5)")
    b.add_argument("--name", help="a .ds1 file's map name in the game (act1/town/townn1.ds1): where its scene goes, and D2R's scene of that name is its base")
    b.add_argument("--biome", help="the biome of a map without a scene")
    b.add_argument("--report", help="write the stats here as json")
    a = ap.parse_args(argv)
    a.orientations = [int(o) for o in a.orientations.split(",") if o]
    if a.classic:
        a.floors, a.ground, a.rule = "all", "bare", "all"
    *names, out = a.targets
    if a.all:
        import walls_hd
        names = list(walls_hd.MAPS) + names
    if a.list:
        names = listed_maps(a.list) + names
    if not names:
        print("sprite_scene: no map listed, nothing to do")
        return 0
    stats = build(handles_for(names, a), Path(out), a)
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(json.dumps(stats, indent=1), encoding="utf-8")
    for name, s in stats.items():
        if name != "_all":
            print("%s: %d wall pieces, %d tiles, %d entities of %d (%d capped), base %s" % (
                name, s["wall_pieces"], s["distinct_tiles"], s["entities"], s["limit"], s["capped"], s["base"]))
    print(json.dumps(stats["_all"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
