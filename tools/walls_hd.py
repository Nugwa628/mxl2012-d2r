"""HD walls for Median XL 2012's maps: wall scenes made of D2R's own wall models (docs/maps-hd.md "Walls").

D2R's HD client draws a map's walls, cliffs and buildings only from the scene preset `data/hd/env/preset/<map>.json`
(tools/maps_hd.py writes a minimal one: biome only, so floors and no walls). D2R's own presets place their walls as entities
(a model, a transform and some components) on the map's wall cells, 10 world units per tile (x = tile column * 10, z = row * 10).

This tool learns from D2R's own maps which entities sit on which wall tile, and writes a scene for a Median map with those
entities on its wall cells:

  1. learn: every D2R .ds1 that has a scene and uses one of the stock tile files a Median map needs. Its wall cells are
     resolved through the .ds1 header's tile files ((orientation, style, sequence) -> the first file that has it); each scene
     entity with a model goes to the wall cells of the tile it stands on, with its offset inside the tile. The cell's key is
     the set of wall tiles on it (stock .dt1 path + orientation + style + sequence, all wall layers).
  2. per key the library keeps the variant (the models and offsets) seen most often; ties go to the first map in path order.
  3. scene: for every wall cell of the Median map (Median's new .dt1 swapped for their stock donor: tools/maps_hd.py
     donor_table; every new .dt1 is a retextured copy with the same tile keys) the variant of its key, moved to the cell.
     A cell whose full key was never seen falls back to the best single-tile key (the most layers in common).
     Floor-only cells are keyed by their floor tiles the same way (floor_cells: D2R draws the Act 1 cave walls, the ice cave
     ledges, Kurast stairs and the Arcane platforms' trims on floor tiles); a floor D2R leaves bare stays bare.
     Cells without any match stay without a wall model (counted in the report: `uncovered`).

What the player sees is D2R's stock walls of the donor tile set (the same layout Median's tiles have), not Median's
retextured look: that needs custom art (docs/unported.md). Collision and walkability come from the tiles, never the scene.

Physics bodies of the copied entities are dropped (they only serve ragdolls / effects in HD, and a stray body inside a walkable
cell of Median's layout would stop corpses there); wall transparency (WallTransparencyComponent) is kept.

  py -3 -I tools/walls_hd.py report [--out DIR]       coverage per map -> DIR/walls_report.json / walls_report.md
  py -3 -I tools/walls_hd.py build DATA_DIR           write DATA_DIR/hd/env/preset/<map>.json for the maps in MAPS
                                                      (replaces the minimal scene of tools/maps_hd.py build)
  py -3 -I tools/walls_hd.py docs [FILE]              refresh the generated table in docs/maps-hd.md

D2R's scenes are read from the D2R extraction or the shared cache (tools/fxpaths.py d2r_file; once from a game slot's CASC
with MXL_SLOT=2..5 when the cache lacks them). Nothing of D2R's or Median's is written into the repo.
"""
import argparse
import collections
import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ds1_remap  # noqa: E402
import map_tint  # noqa: E402
import maps_hd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SET_PIECE_CELLS = 3              # see Library.set_piece()
MIN_MODEL_SHARE = 1 / 3          # see choose()
ANCHOR_RADIUS = 2                # see Library.anchor()
TILE = 10.0                      # world units per tile in D2R's scenes
WALL_ORIENTATIONS = set(range(1, 10))   # .dt1 orientations 1-9: walls and their corners/ends (10+: specials, shadow, tree, roof)
# The cap (cache lane, bug #360 asset cache overflow): no generated scene above D2R's largest map scene, act3/docktown/docktown3
# (4,989 entities, 4,423 of them with a model, 679 distinct models, 4,651,080 bytes). cap() drops pieces past these.
MAX_PLACED = 4423
MAX_BYTES = 4_651_080
# cap() tiers, dropped lowest first: 0 props (books, gold, mud piles), 1 details on a wall (buttresses, pillars, arches,
# beams, stairs, gargoyles), 2 the walls, cliffs and fences that close rooms and block the view.
DETAIL = re.compile(r"buttress|pillar|arch|column|support|beam|cap_|trim|roof|lip|stair|step|gargoyle|statue|mural|crenel|"
                    r"banner|torch|lamp|chain|ornament|post", re.I)
SIGHT = re.compile(r"wall|cliff|elevation|fence|treeline|gate|rock|ruin|segment|corner|end_", re.I)
# The 8 maps whose tiles Median retextured (docs/maps-hd.md, art class "custom", lane walls) ...
RETEXTURED = ["expansion/dystopic/desertpeak.ds1", "expansion/ghetto/cypherpunk.ds1", "expansion/glados/glados.ds1",
              "expansion/neonmile/downtown.ds1", "expansion/redsquare/moskvich.ds1", "expansion/terror/borgir.ds1",
              "expansion/voodoo/macumba.ds1", "expansion/zakarum/charismatic.ds1"]
# ... and the 9 on stock tiles (art class "generate" and the 4 edits too far from D2R's scene, lane hdwalls2), the ones players
# walk through in normal play first: Flayer Dungeon 3 (Khalim's Brain), Forgotten Reliquary (one of its two maps at random),
# Hole 2, Spider Cave, Ancient Tunnels, Cave 2, Underground Passage 2, Drifter Cavern.
STOCK = ["act3/jungle/dungrm6a.ds1", "act3/temple/temple5.ds1", "act3/temple/temple6.ds1", "act1/caves/caveroom4.ds1",
         "act3/kurast/excelsior3.ds1", "act2/arcane/belial.ds1", "expansion/morework/epicwhiners.ds1",
         "act1/cathedrl/inarius.ds1", "expansion/icecave/rockisdead.ds1"]
MAPS = RETEXTURED + STOCK   # every map tools/maps_hd.py gives a minimal scene (17): each gets a wall scene from stock models
# Maps whose HD scene gets its own terrain mesh over its floor and wall cells only (lane walls3): -> the D2R map whose terrain
# model is the template. Without a terrain entity the engine paints the biome's floor over the whole map rectangle; in the
# Arcane Sanctuary that put floor where classic has the starry void, and hid the arches that hang under the platform edges.
# D2R's own Arcane maps have a mesh over their platforms only (sancte: 482 flat triangles at y = 0). Tried on belial
# ({"act2/arcane/belial.ds1": "act2/arcane/sancte"}, also with sancte's physics body): the scene loads, no assert, but HD still
# draws floor over the void (docs/maps-hd.md item 12), so no map uses it yet.
TERRAIN_MAPS = {}
KEEP_COMPONENTS = {"TransformDefinitionComponent", "ModelDefinitionComponent", "ModelVariationDefinitionComponent",
                   "ModelPlatformTierComponent", "WallTransparencyComponent"}
# Decoration that D2R's artists put on and around walls (plants, rubble, bones, stains): not part of the wall, and copied per
# cell it multiplies (desertpeak: 18,565 entities, 14 MB, most of it ivy, ferns and stones). Dropped unless the entity fades
# with the wall (WallTransparencyComponent) or its file names a structural piece (STRUCTURE: skull arches, gargoyle pillars,
# rubble walls, the jungle treeline).
STRUCTURE = re.compile(r"arch|pillar|wall|treeline|support|fence")
DECOR = re.compile(r"weed|fern|cinchona|ivy|root|vine|debris|dirt|blood|rubble|sapling|pottery|remains|scum|web|lea(f|ves)|"
                   r"grounding|grass|offering|bone|skull|skeleton|candle|grunge|moss|bush|flower|sand_pile|snow_pile|stain|"
                   r"decal|puddle|ritual|_props|clutter|junk|trash|corpse|cluster|chest|sword|spear|shield|weapon|barrel|potstack|_pot|"
                   r"vase|bottle|urns?/|_urn|basket|_mat|mats/|rug|straw|lumber|pallet|plank|cloth|dryrack|stool|food|slush|"
                   r"snow_pile|snowprops|shrub|elephant_ear|tree_dead|gore/|guts", re.I)
# D2R's own (29,475 of D2R's 31,217 have these values: the fade follows the entity's position)
WALL_TRANSPARENCY = {"type": "WallTransparencyComponent", "drawOrder": 0, "wallTileLocalCoord": {"x": -1, "y": -1}}
DEP_KEYS = ("particles", "models", "skeletons", "animations", "textures", "physics", "json", "variantdata", "objecteffects", "other")
DOCS_BEGIN, DOCS_END = "<!-- walls_hd:begin (generated: py -3 -I tools/walls_hd.py docs) -->", "<!-- walls_hd:end -->"


# ---- tiles ---------------------------------------------------------------------------------------------------------------
def header_dt1(ds: ds1_remap.Ds1):
    """The .ds1 header's tile files as normalised .dt1 paths below data/global/tiles (editor metadata, but right for D2R's own
    maps): '/d2/data/global/tiles/Act3/Kurast/Floors.tg1' -> 'act3/kurast/floors.dt1'."""
    out = []
    for f in ds.files:
        low = f.replace("\\", "/").lower()
        i = low.find("/tiles/")
        if i < 0:
            continue
        p = low[i + len("/tiles/"):]
        if p.endswith(".tg1"):
            p = p[:-4] + ".dt1"
        if p.endswith(".dt1") and p not in out:
            out.append(p)
    return out


def wall_index(paths, tiles_of):
    """(orientation, style, sequence) -> the first file in `paths` that has the tile (non-floor tiles only)."""
    idx = {}
    for p in paths:
        for t in tiles_of(p) or ():
            if t.orientation != 0:
                idx.setdefault(t.key, p)
    return idx


def wall_cells(ds: ds1_remap.Ds1, idx, donor_of=lambda p: p):
    """{(x, y): tuple of (tile set folder, orientation, style, sequence)} for every tile with a wall in any layer. The folder is
    that of the stock donor of a new file (`donor_of`): D2R's tile sets repeat their keys across the files of one folder
    (Harrogath's buildings.dt1 / buildingses.dt1), and a level type resolves a key to its first file anyway. An unresolved tile
    is kept as (None, o, s, q) so it is counted, never matched."""
    cells = collections.defaultdict(list)
    for lay, ori in ds.wall_layers():
        for i, (c, o) in enumerate(zip(lay, ori)):
            if c == 0:
                continue
            o &= 0xFF
            s, q = ds1_remap.cell_key(c)
            p = idx.get((o, s, q))
            cells[(i % ds.width, i // ds.width)].append((maps_hd.tiledir(donor_of(p)) if p else None, o, s, q))
    return {xy: tuple(sorted(v, key=lambda k: (k[0] or "", k[1:]))) for xy, v in cells.items()}


def floor_index(paths, tiles_of):
    """(0, style, sequence) -> the first file in `paths` that has the floor tile."""
    idx = {}
    for p in paths:
        for t in tiles_of(p) or ():
            if t.orientation == 0:
                idx.setdefault(t.key, p)
    return idx


def floor_cells(ds: ds1_remap.Ds1, idx, donor_of=lambda p: p, skip=()):
    """{(x, y): tuple of (folder, 0, style, sequence)} for every cell with a floor tile and no wall (cells in `skip`). D2R
    draws the walls of some tile sets on floor tiles (lane hdwalls2): the Act 1 caves (82% of their wall models stand on
    floor-only cells, 5% on wall cells), Diablo's sanctuary, the bigcliff; Median's cave maps need those to get any wall.
    Floor tiles that D2R leaves bare (open ground) get no model through choose(); unresolved floor tiles are left out."""
    cells = collections.defaultdict(list)
    for lay in ds.floor_layers():
        for i, c in enumerate(lay):
            if c == 0:
                continue
            xy = (i % ds.width, i // ds.width)
            if xy in skip:
                continue
            s, q = ds1_remap.cell_key(c)
            p = idx.get((0, s, q))
            if p:
                cells[xy].append((maps_hd.tiledir(donor_of(p)), 0, s, q))
    return {xy: tuple(sorted(set(v))) for xy, v in cells.items()}


def map_cells(ds: ds1_remap.Ds1, paths, tiles_of, donor_of=lambda p: p):
    """wall_cells() plus floor_cells() of the cells without a wall: every cell a wall model can stand on."""
    walls = wall_cells(ds, wall_index(paths, tiles_of), donor_of)
    out = dict(walls)
    out.update(floor_cells(ds, floor_index(paths, tiles_of), donor_of, walls))
    return out


def is_floor(key) -> bool:
    return all(k[1] == 0 for k in key)


# ---- scenes ----------------------------------------------------------------------------------------------------------------
def transform(e):
    return next((c for c in e.get("components", ()) if c.get("type") == "TransformDefinitionComponent"), None)


def model_of(e):
    """The entity's model: its ModelDefinitionComponent, else the first entry of its ModelVariationDefinitionComponent (lane
    hdwalls2: 87k of D2R's 393k model entities draw one of several weighted models that way, all of the Flayer Dungeon's
    fences and most of the ice caves'; before, those walls were never learnt)."""
    for c in e.get("components", ()):
        if c.get("type") == "ModelDefinitionComponent":
            return c.get("filename")
    for c in e.get("components", ()):
        if c.get("type") == "ModelVariationDefinitionComponent":
            return next((v.get("filename") for v in c.get("variations", ()) if v.get("filename")), None)
    return None


def models_of(e):
    """Every model the entity may draw (the scene's `dependencies` must name all variations)."""
    out = []
    for c in e.get("components", ()):
        if c.get("type") == "ModelDefinitionComponent" and c.get("filename"):
            out.append(c["filename"])
        elif c.get("type") == "ModelVariationDefinitionComponent":
            out += [v["filename"] for v in c.get("variations", ()) if v.get("filename")]
    return out


def is_decor(e) -> bool:
    if any(c.get("type") == "WallTransparencyComponent" for c in e.get("components", ())):
        return False
    m = (model_of(e) or "").lower().rsplit("/", 2)
    m = "/".join(m[-2:])
    return bool(DECOR.search(m)) and not STRUCTURE.search(m)


def wall_entities(scene: dict, ground=None):
    """The scene's entities that carry a model and are neither the baked terrain nor decoration: [(entity, x, z)].

    With `ground` (a Ground of the scene's terrain), every entity is moved down to the gameplay plane: D2R's HD camera is an
    orthographic one at the true isometric angle, so a piece standing on terrain raised by g is drawn at (x + g, y + g, z + g)
    to stay over its tile (the Fortress interior stands about 35 units up and its walls sit 3-4 tiles off their wall cells;
    lane walls3). (x - g, y - g, z - g) is the same spot on screen at ground level: the tile it belongs to, and the height
    it needs in a scene without D2R's terrain (Median's maps are flat). The entity is a copy with a new transform then."""
    out = []
    for e in scene.get("entities", ()):
        t, m = transform(e), model_of(e)
        if not t or not m or e.get("name") == "terrain" or any(c.get("type") == "TerrainDefinitionComponent" for c in e["components"]) or is_decor(e):
            continue
        p = t.get("position", {})
        x, z = float(p.get("x", 0.0)), float(p.get("z", 0.0))
        g = ground.height(x, z) if ground is not None else 0.0
        if abs(g) >= 0.01:
            t2 = dict(t, position=dict(p, x=round(x - g, 3), y=round(float(p.get("y", 0.0)) - g, 3), z=round(z - g, 3)))
            e = dict(e, components=[t2 if c is t else c for c in e["components"]])
            x, z = x - g, z - g
        out.append((e, x, z))
    return out


# ---- D2R's terrain (heights of its baked terrain mesh) ------------------------------------------------------------------
class Ground:
    """Height of a D2R map's baked terrain: the preset's `terrain` entity draws one GR2 mesh (terrain_lod0.model), in world
    units like the entities. height(x, z): the highest triangle over the point; outside the mesh (Arcane void, a cliff
    foot) the nearest vertex within `near` units, else 0."""

    def __init__(self, pos, tris, near=15.0):
        self.pos, self.tris, self.near = pos, tris, near
        self.cells = collections.defaultdict(list)
        for n, (a, b, c) in enumerate(tris):
            xs, zs = (pos[a][0], pos[b][0], pos[c][0]), (pos[a][2], pos[b][2], pos[c][2])
            for cx in range(int(min(xs) // TILE), int(max(xs) // TILE) + 1):
                for cz in range(int(min(zs) // TILE), int(max(zs) // TILE) + 1):
                    self.cells[(cx, cz)].append(n)

    def height(self, x: float, z: float) -> float:
        best = None
        for n in self.cells.get((int(x // TILE), int(z // TILE)), ()):
            a, b, c = (self.pos[i] for i in self.tris[n])
            d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(d) < 1e-9:
                continue
            u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d
            v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d
            if u < -1e-6 or v < -1e-6 or u + v > 1 + 1e-6:
                continue
            y = u * a[1] + v * b[1] + (1 - u - v) * c[1]
            best = y if best is None else max(best, y)
        if best is not None:
            return best
        d2, y = min(((p[0] - x) ** 2 + (p[2] - z) ** 2, p[1]) for p in self.pos) if self.pos else (0.0, 0.0)
        return y if d2 <= self.near ** 2 else 0.0


def terrain_mesh(tree):
    """(positions [(x, y, z)], triangles [(a, b, c)]) of every mesh of a parsed terrain model (tools/d2r_model.py tree):
    BinormalInt16 positions scaled by the mesh's VertexScale."""
    pos, tris = [], []
    for m in tree["Meshes"]:
        ed = m["ExtendedData"].obj if m.get("ExtendedData") is not None else None
        scale = float(ed["VertexScale"]) if ed is not None and ed.get("VertexScale") else 1.0
        base = len(pos)
        for v in m["PrimaryVertexData"]["Vertices"].obj:
            p = v["Position"]
            pos.append(tuple(float(p[i]) / 32767 * scale for i in range(3)) if isinstance(p[0], int) else tuple(float(p[i]) for i in range(3)))
        topo = m["PrimaryTopology"]
        idx = [o["Int16"] for o in topo.get("Indices16") or ()] or [o["Int32"] for o in topo.get("Indices") or ()]
        tris += [(base + idx[i], base + idx[i + 1], base + idx[i + 2]) for i in range(0, len(idx) - 2, 3)]
    return pos, tris


def terrain_path(scene: dict):
    """The game path of the scene's terrain mesh: 'data/hd/env/preset/act2/arcane/sanctE/terrain.model' names
    data/hd/env/preset/act2/arcane/sancte/terrain_lod0.model (the engine adds the LOD; CASC names are lower case)."""
    comp = next((c for c in (scene.get("terrain") or {}).get("components", ()) if c.get("type") == "ModelDefinitionComponent"), None)
    if not comp or not comp.get("filename", "").endswith(".model"):
        return None
    return comp["filename"].lower()[:-len(".model")] + "_lod0.model"


def d2r_ground(key: str, scene: dict):
    """Ground of a D2R map's scene, None without a terrain mesh (read like d2r_scene: extraction, cache, slot CASC)."""
    import d2r_model
    rel = terrain_path(scene)
    data = d2r_bytes(rel) if rel else None
    if not data:
        return None
    pos, tris = terrain_mesh(d2r_model.parse_tree(d2r_model.Gr2File.read(data)))
    return Ground(pos, tris)


def terrain_cells(cells) -> set:
    """The cells a generated terrain covers: every floor or wall cell with a floor or wall cell next to it (the lone corner
    tiles that mark a preset's extent, (0, 0) and (w-1, h-1) in the Arcane maps, stay bare, as in D2R's sancte)."""
    have = set(cells)
    return {(x, y) for x, y in have if {(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)} & have}


def terrain_model(template: bytes, cells, width: int, height: int) -> bytes:
    """A terrain_lod0.model: the template (a D2R terrain model: one rigid mesh 'terrainShape', vertices Position int16[4],
    Normal, Tangent, half-float UV) with its mesh replaced by flat quads at y = 0 over `cells` (tile coordinates). As in D2R's
    own: world positions, UV = position / map size, the bone and the model placed at the map's centre, the bone binding's box
    in bone space, the reflective plane the mesh's bounds, triangles wound as D2R's (clockwise seen from above)."""
    import math
    import d2r_model as dm
    gr2 = dm.Gr2File.read(template)
    tree = dm.parse_tree(gr2)
    corners, tris = {}, []

    def corner(x, z):
        return corners.setdefault((x, z), len(corners))
    for x, z in sorted(cells, key=lambda c: (c[1], c[0])):
        a, b, c, d = corner(x, z), corner(x + 1, z), corner(x + 1, z + 1), corner(x, z + 1)
        tris += [(a, c, b), (a, d, c)]
    if not tris or len(corners) > 65535:
        raise ValueError("terrain_model: %d cells, %d corners" % (len(cells), len(corners)))
    pos = sorted(corners, key=corners.get)
    xs, zs = [p[0] * TILE for p in pos], [p[1] * TILE for p in pos]
    scale = max(max(xs), max(zs), 1.0)
    w = int(round(math.log2(scale) / 13 * 32767))
    mesh = tree["Meshes"][0]
    vertices = mesh["PrimaryVertexData"]["Vertices"]
    vtd = vertices.obj[0].td
    sx, sz = width * TILE, height * TILE
    vertices.obj = [dm.Obj(vtd, {
        "Position": [int(round(x / scale * 32767)), 0, int(round(z / scale * 32767)), w],
        "Normal": [0, 127, 0, 0], "Tangent": [127, 0, 0, -127],
        "TextureCoordinates0": [_half(x / sx), _half(z / sz)]}) for x, z in zip(xs, zs)]
    topo = mesh["PrimaryTopology"]
    itd = topo["Indices16"][0].td
    topo["Indices16"] = [dm.Obj(itd, {"Int16": i}) for t in tris for i in t]
    topo["Groups"] = topo["Groups"][:1]
    topo["Groups"][0]["TriFirst"], topo["Groups"][0]["TriCount"] = 0, len(tris)
    lo, hi = [min(xs), 0.0, min(zs)], [max(xs), 0.0, max(zs)]
    centre = (sx / 2, 0.0, sz / 2)
    ed = mesh["ExtendedData"].obj
    ed["bbMin"], ed["bbMax"], ed["VertexScale"] = lo, hi, float(scale)
    for plane in ed.get("ReflectivePlanes") or ():
        plane["Position"] = [(lo[0] + hi[0]) / 2, 0.0, (lo[2] + hi[2]) / 2]
        plane["Size"] = [hi[0] - lo[0], 0.0, hi[2] - lo[2]]
    for bind in mesh["BoneBindings"]:
        bind["OBBMin"] = [lo[i] - centre[i] for i in range(3)]
        bind["OBBMax"] = [hi[i] - centre[i] for i in range(3)]
    for bone in tree["Skeletons"][0]["Bones"]:
        bone["InverseWorldTransform"] = list(bone["InverseWorldTransform"][:12]) + [-centre[0], 0.0, -centre[2], 1.0]
    for model in tree["Models"]:
        p = model["InitialPlacement"]
        model["InitialPlacement"] = dm.Transform(p.flags, centre, p.orientation, p.scale_shear)
    out = dm.Writer(gr2).build(tree).write()
    dm.parse_tree(dm.Gr2File.read(out))      # well formed
    return out


def _half(f: float) -> int:
    import struct
    return struct.unpack("<H", struct.pack("<e", f))[0]


def terrain_entity(path: str) -> dict:
    """The scene's `terrain` for a generated mesh at game path `path` (…/terrain.model; the file is …/terrain_lod0.model):
    D2R's own terrain entity (sancte's) without the physics body (classic does the collision; no physics file to ship)."""
    name = "terrain"
    return {"type": "Entity", "name": name, "id": 1449264087, "components": [
        {"type": "TransformDefinitionComponent", "name": name + "_TransformDefinitionComponent", "position": {"x": 0.0, "y": 0.0, "z": 0.0},
         "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}, "scale": {"x": 1.0, "y": 1.0, "z": 1.0}, "inheritOnlyPosition": False},
        {"type": "TerrainDefinitionComponent", "name": name + "_TerrainDefinitionComponent"},
        {"type": "ModelDefinitionComponent", "name": name + "_ModelDefinitionComponent", "filename": path, "visibleLayers": 1,
         "lightMask": 19, "shadowMask": 3, "ghostShadows": False, "floorModel": False, "terrainBlendEnableYUpBlend": False,
         "terrainBlendMode": 1}]}


def add_terrain(text: str, path: str) -> str:
    """A scene_json() text with terrain_entity(path) as its terrain (also named in the dependencies, as D2R's are)."""
    scene = json.loads(text)
    scene["terrain"] = terrain_entity(path)
    scene["dependencies"]["other"] = scene["dependencies"].get("other", []) + [{"path": path}]
    return json.dumps(scene, separators=(",", ":"))


def strip_entity(e: dict) -> dict:
    """A copy with only the components a drawn wall needs (no physics, no effects, no terrain stamps), and wall transparency
    on every one: D2R gives it only to walls that can stand between the camera and the player in its own layout (docktown's
    upper walls stand at the back and have none); in Median's layout any of them can, and without it the view is blocked
    (desertpeak in HD was black at the arrival)."""
    e = copy.deepcopy(e)
    e["components"] = [c for c in e["components"] if c.get("type") in KEEP_COMPONENTS]
    if not any(c.get("type") == "WallTransparencyComponent" for c in e["components"]):
        e["components"].append(dict(WALL_TRANSPARENCY, name="WallTransparencyComponent"))
    return e


class Library:
    """key (tuple of wall tiles on one cell) -> Counter(variant signature) and the variants themselves."""

    def __init__(self):
        self.seen = collections.defaultdict(collections.Counter)   # key -> Counter(signature)
        self.variants = {}                                         # signature -> [(entity, dx, dz)]
        self.single = collections.defaultdict(collections.Counter)  # one wall tile -> Counter(signature)
        self.sources = collections.Counter()                       # map -> cells learnt
        self.model_cells = collections.Counter()                    # model -> D2R wall cells it stands on
        self.generic = collections.defaultdict(collections.Counter)  # (tile set folder or act, orientation) -> Counter(signature)
        self._generic = {}
        self.maps = {}                                             # map -> (cells, [(entity, x, z) on no cell]) until anchor()
        self.anchored = {}                                         # key -> [(entity, dx, dz)] anchor() hangs on it

    def learn(self, name: str, cells: dict, scene: dict, ground=None):
        """cells: wall_cells() of a D2R map; scene: its preset json; ground: its Ground (wall_entities)."""
        per_cell, homeless = collections.defaultdict(list), []
        for e, x, z in wall_entities(scene, ground):
            xy = (int(x // TILE), int(z // TILE))
            if xy in cells:
                per_cell[xy].append((e, round(x - xy[0] * TILE, 3), round(z - xy[1] * TILE, 3)))
            else:
                homeless.append((strip_entity(e), x, z))
        if homeless:
            self.maps[name] = (cells, homeless)
        for ents in per_cell.values():
            for e, _dx, _dz in ents:
                self.model_cells[model_of(e)] += 1
        for xy, key in cells.items():
            if any(k[0] is None for k in key):
                continue
            ents = sorted(per_cell.get(xy, []), key=lambda t: (model_of(t[0]), t[1], t[2]))
            sig = tuple((model_of(e), dx, dz) for e, dx, dz in ents)
            if sig not in self.variants:
                self.variants[sig] = [(strip_entity(e), dx, dz) for e, dx, dz in ents]
            self.seen[key][sig] += 1
            if len(key) == 1:
                self.single[key[0]][sig] += 1
                if sig and key[0][1] in WALL_ORIENTATIONS:
                    self.generic[(key[0][0], key[0][1])][sig] += 1
                    self.generic[(act_of(key[0][0]), key[0][1])][sig] += 1
            self.sources[name] += 1

    def anchor(self, radius=ANCHOR_RADIUS, share=MIN_MODEL_SHARE):
        """Hang the pieces that stand on no learnt cell on the rarest key next to them. D2R's artists place a model where it
        looks right, not on the tile it belongs to: the Act 1 caves' stairs (back_stairs01) stand on the void cell beside the
        stairs tiles in all 21 cave maps that have them, so they were never learnt and caveroom4's arrival had no stairs (lane
        walls3). Such an entity is counted on the rarest learnt key within `radius` cells, at its offset from that cell; a
        (model, offset) found on at least `share` of that key's cells, and on SET_PIECE_CELLS of them, is placed with the key
        from then on (build_scene). (Hanging also the pieces a cell's own pick() leaves out raised the self-check from 55% to
        71%, but grew glados, cypherpunk and desertpeak past the cap with props: not done.)"""
        total = {k: sum(c.values()) for k, c in self.seen.items()}
        counts, items = collections.defaultdict(collections.Counter), {}
        for cells, homeless in self.maps.values():
            for e, x, z in homeless:
                xy = (int(x // TILE), int(z // TILE))
                near = [(total[cells[n]], max(abs(n[0] - xy[0]), abs(n[1] - xy[1])), n)
                        for n in ((xy[0] + i, xy[1] + j) for i in range(-radius, radius + 1) for j in range(-radius, radius + 1))
                        if cells.get(n) in total]
                if not near:
                    continue
                n = min(near)[2]
                m, off = model_of(e), (round(x - n[0] * TILE, 1), round(z - n[1] * TILE, 1))
                counts[cells[n]][(m, off)] += 1
                items.setdefault((cells[n], m, off), e)
        self.anchored = {}
        for k, c in counts.items():
            keep = [(items[(k, m, off)], off[0], off[1]) for (m, off), n in sorted(c.items())
                    if n >= share * total[k] and n >= SET_PIECE_CELLS]
            if keep:
                self.anchored[k] = keep
        self.maps = {}

    def set_piece(self, model) -> bool:
        """A model D2R puts on fewer than SET_PIECE_CELLS wall cells in all its maps (Tal Rasha's chamber in duriel.ds1, a
        sword in Harrogath): part of a one-off set, not of the tile. Copied onto every Median cell of that key it blocked
        the view in desertpeak and filled downtown with 244 swords."""
        return self.model_cells.get(model, 0) < SET_PIECE_CELLS

    def pick(self, key):
        """-> (signature, how) for a cell key: 'exact', 'partial' (a learnt single tile or key sharing a tile) or (None, None)."""
        if key in self.seen:
            return choose(self.seen[key]), "exact"
        best, score = None, 0
        for k in key:
            if k in self.single and sum(self.single[k].values()) > score:
                best, score = choose(self.single[k]), sum(self.single[k].values())
        if is_floor(key):  # a floor D2R never has: bare ground (no search over every learnt key, no generic wall)
            return (best, "partial") if best is not None else ((), "floor")
        if best is None:   # any learnt key that holds one of this cell's tiles
            tiles = set(key)
            for k, c in self.seen.items():
                common = len(tiles & set(k))
                if common > score:
                    best, score = choose(c), common
            if best == ():   # ... bare there: weaker than a wall of the tile set (charismatic's Fortress walls of style 4, lane walls3)
                best = self.generic_pick(key) or ()
                if best:
                    return best, "generic"
        if best is not None:
            return best, "partial"
        best = self.generic_pick(key)
        return (best, "generic") if best is not None else (None, None)

    def generic_pick(self, key):
        """A wall tile D2R never puts in a scene (downtown's Harrogath walls of style 3: Harrogath's own maps resolve those keys
        to other files) gets D2R's most common single-tile wall of the same orientation in the same tile set, else in the
        same act's sets ('expansion', 'act3', ...), set pieces and variants with props (tier 0: a book stack, a flagpole)
        excluded. Orientations that are not walls (specials, shadows, trees, roofs) stay uncovered."""
        for scope in (lambda d: d, act_of):
            for d, o, _s, _q in key:
                if d is None or o not in WALL_ORIENTATIONS:
                    continue
                g = (scope(d), o)
                if g not in self._generic:
                    ok = [(n, sig) for sig, n in self.generic.get(g, {}).items()
                          if not any(self.set_piece(m) or tier(m) == 0 for m, _dx, _dz in sig)]
                    self._generic[g] = max(ok, key=lambda t: t[0])[1] if ok else None
                if self._generic[g] is not None:
                    return self._generic[g]
        return None


def choose(seen: collections.Counter):
    """The variant for a key: the most common one with models when D2R gives the tile models in at least MIN_MODEL_SHARE of
    its cells (a wall model spans several tiles but stands on one, so its neighbours count as empty and a plain majority
    leaves gaps), else the empty one. Ties: the first seen."""
    total = sum(seen.values())
    full = [(n, sig) for sig, n in seen.items() if sig]
    if full and sum(n for n, _ in full) >= MIN_MODEL_SHARE * total:
        return max(full, key=lambda t: t[0])[1]
    return ()


# Short component names: the long "<entity>_<type>" form made cypherpunk's scene larger than D2R's largest (docktown3, 4.65 MB).
SHORT = {"ModelDefinitionComponent": "m", "TransformDefinitionComponent": "t", "ModelPlatformTierComponent": "p",
         "WallTransparencyComponent": "w", "ModelVariationDefinitionComponent": "v"}


def place(variant, x: int, y: int, serial: int):
    """The variant's entities moved onto cell (x, y), with fresh names and ids."""
    out = []
    for n, (e, dx, dz) in enumerate(variant):
        e = copy.deepcopy(e)
        t = transform(e)
        t["position"]["x"] = round(x * TILE + dx, 3)
        t["position"]["z"] = round(y * TILE + dz, 3)
        e["name"] = "mxw_%d_%d_%d" % (x, y, n)
        e["id"] = 0x6D780000 + (serial * 8 + n) % 0x80000   # unique per scene; D2R's ids are plain 32-bit numbers
        for c in e["components"]:
            if "name" in c:
                c["name"] = "%s_%s" % (e["name"], SHORT.get(c["type"], c["type"]))
        out.append(e)
    return out


def scene_json(biome: str, entities: list) -> str:
    """maps_hd's minimal scene plus wall entities and the models they name in `dependencies`."""
    scene = json.loads(maps_hd.scene_json(biome))
    models = sorted({m for e in entities for m in models_of(e)})
    scene["dependencies"]["models"] = [{"path": m} for m in models]
    scene["entities"] = entities
    return json.dumps(scene, separators=(",", ":"))


def act_of(folder: str) -> str:
    """'act3/kurast' -> 'act3', 'expansion/town' -> 'expansion'."""
    return folder.split("/", 1)[0]


def tier(model: str) -> int:
    """cap() order: 0 props, 1 details on a wall, 2 walls that close rooms (DETAIL / SIGHT, on the file name)."""
    name = (model or "").rsplit("/", 1)[-1]
    return 1 if DETAIL.search(name) else 2 if SIGHT.search(name) else 0


def spread(i: int) -> float:
    """Van der Corput rank of the i-th copy of a model (0, .5, .25, .75, ...): dropping the lowest ranks thins a model out
    evenly over the map instead of cutting one region."""
    r, f = 0.0, 0.5
    i += 1
    while i:
        r, i, f = r + f * (i & 1), i >> 1, f / 2
    return r


def cap(ents: list, limit: int) -> list:
    """At most `limit` entities: props go first, then details on walls, then walls; within a tier every model loses the
    same share, spread over the map, the most repeated model first on a tie. Order kept."""
    if len(ents) <= limit:
        return ents
    count, seen, rank = collections.Counter(model_of(e) for e in ents), collections.Counter(), []
    for n, e in enumerate(ents):
        m = model_of(e)
        rank.append((tier(m), spread(seen[m]), -count[m], n))
        seen[m] += 1
    drop = {r[3] for r in sorted(rank)[:len(ents) - limit]}
    return [e for n, e in enumerate(ents) if n not in drop]


def build_scene(cells: dict, lib: Library, biome: str, limit=MAX_PLACED, max_bytes=MAX_BYTES):
    """-> (scene json text, stats). The scene keeps at most `limit` entities and `max_bytes` bytes (cap())."""
    ents, stats = [], collections.Counter()
    for serial, (xy, key) in enumerate(sorted(cells.items(), key=lambda t: (t[0][1], t[0][0]))):
        sig, how = lib.pick(key)
        extra = list(lib.anchored.get(key, ())) if how == "exact" else []
        stats["anchored"] += len(extra)
        if is_floor(key):          # floor-only cells: counted apart, never 'uncovered' (most floors are bare ground)
            stats["floor_cells"] += 1
            if not sig:
                ents += place(extra, xy[0], xy[1], serial)
                continue
            stats["floor_walls"] += 1
        elif sig is None:
            stats["uncovered"] += 1
            continue
        else:
            stats[how] += 1
            if not sig:
                stats["empty"] += 1     # D2R draws this tile without an entity (baked into its terrain, or nothing)
        variant = lib.variants.get(sig, [])
        keep = [v for v in variant if not lib.set_piece(model_of(v[0]))]
        stats["set_pieces"] += len(variant) - len(keep)
        ents += place(keep + extra, xy[0], xy[1], serial)
    kept = cap(ents, limit)
    text = scene_json(biome, kept)
    while len(text.encode("utf-8")) > max_bytes and kept:
        kept = cap(ents, min(len(kept) - 1, int(len(kept) * max_bytes / len(text.encode("utf-8")))))
        text = scene_json(biome, kept)
    stats["cells"] = len(cells) - stats["floor_cells"]
    stats["placed"] = len(ents)
    stats["capped"] = len(ents) - len(kept)
    stats["entities"] = len(kept)
    stats["models"] = len({m for e in kept for m in models_of(e)})
    return text, stats


# ---- inputs ------------------------------------------------------------------------------------------------------------------
_CASC = []


def d2r_bytes(rel: str):
    """A D2R file (rel = 'data/hd/...'): the D2R extraction, else the shared cache (fxpaths.D2R_CACHE), else read once from a
    game slot's CASC (MXL_SLOT, read-only, one storage handle for the whole run) into the cache, as fxpaths.d2r_file does.
    None when it is in none of them."""
    import os
    import fxpaths
    for p in (fxpaths.D2R / rel, fxpaths.D2R_CACHE / rel):
        if p.exists():
            return p.read_bytes()
    if not os.environ.get("MXL_SLOT") and not os.environ.get("MXL_D2R_GAME"):
        raise SystemExit("walls_hd: D2R's %s is in neither the D2R extraction nor the cache (%s); run once with MXL_SLOT=2..5 "
                         "to read D2R's scenes and terrain from that slot's CASC into the shared cache" % (rel, fxpaths.D2R_CACHE))
    import d2r_game
    import native
    if not _CASC:
        _CASC.append(native.open_casc(d2r_game.read_game_dir()))
    try:
        data = native.casc_read(_CASC[0], "data:" + rel)
    except OSError:
        return None
    cache = fxpaths.D2R_CACHE / rel
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_name(cache.name + ".%d.tmp" % os.getpid())   # a shared cache: readers never see half a file
    tmp.write_bytes(data)
    os.replace(tmp, cache)
    return data


def d2r_scene(key: str):
    """D2R's preset json of a map key (no .ds1), read by d2r_bytes. None when the scene is nowhere or not json (two of D2R's
    own, kurastbazaar_02 and trav1a, are not)."""
    data = d2r_bytes("data/hd/env/preset/%s.json" % key)
    try:
        return json.loads(data.decode("utf-8-sig")) if data is not None else None
    except ValueError:
        return None


def needed_stock(maps_by_key, donors):
    """The stock tile set folders the Median maps' wall cells resolve to."""
    return {k[0] for cells in maps_by_key.values() for key in cells.values() for k in key if k[0]}


def learns_from(files, needed_dirs) -> bool:
    return any(maps_hd.tiledir(f) in needed_dirs for f in files)


def learn_library(inp: maps_hd.Inputs, needed: set, scene_of=d2r_scene, tiles=None, ground_of=d2r_ground):
    """Library from every D2R map with a scene whose header names a tile file of one of the `needed` folders."""
    tiles = tiles or maps_hd.parse_tiles(inp.d2r_tiles)
    lib = Library()
    for key in sorted(k[:-4] for k in inp.d2r_tiles.keys(".ds1")):
        if key not in inp.scenes:
            continue
        ds = ds1_remap.Ds1(inp.d2r_tiles.read(key + ".ds1"))
        files = header_dt1(ds)
        if not learns_from(files, needed):
            continue
        scene = scene_of(key)
        if scene is None:
            continue
        lib.learn(key, map_cells(ds, files, tiles.get), scene, ground_of(key, scene))
    lib.anchor()
    return lib


def recall(cells: dict, scene: dict, lib: Library, near=1.5, ground=None):
    """Self-check on one of D2R's own maps: the share of its wall entities (on wall cells, decor dropped) that the library's
    scene for the same cells has too (same model within `near` units). -> (found, total)."""
    want = [(model_of(e), x, z) for e, x, z in wall_entities(scene, ground) if (int(x // TILE), int(z // TILE)) in cells]
    have = collections.defaultdict(list)
    for xy, key in cells.items():
        sig, how = lib.pick(key)
        for m, dx, dz in list(sig or ()) + [(model_of(e), dx, dz) for e, dx, dz in (lib.anchored.get(key, ()) if how == "exact" else ())]:
            have[m].append((xy[0] * TILE + dx, xy[1] * TILE + dz))
    found = sum(1 for m, x, z in want if any(abs(x - hx) <= near and abs(z - hz) <= near for hx, hz in have[m]))
    return found, len(want)


def self_check(inp: maps_hd.Inputs, lib: Library, sample=40, scene_of=d2r_scene, ground_of=d2r_ground):
    """recall() over every n-th learnt map (at most `sample`). -> (found, total, maps)."""
    tiles = maps_hd.parse_tiles(inp.d2r_tiles)
    keys = sorted(lib.sources)
    keys = keys[:: max(1, len(keys) // sample)][:sample]
    f = t = 0
    for key in keys:
        ds = ds1_remap.Ds1(inp.d2r_tiles.read(key + ".ds1"))
        scene = scene_of(key)
        a, b = recall(map_cells(ds, header_dt1(ds), tiles.get), scene, lib, ground=ground_of(key, scene))
        f, t = f + a, t + b
    return f, t, len(keys)


def floor_tiles(inp: maps_hd.Inputs, name: str) -> set:
    """The cells of a Median map with a floor tile in any floor layer (walls standing over the void have none)."""
    ds = ds1_remap.Ds1(inp.mod_tiles.read(name))
    return {(i % ds.width, i // ds.width) for lay in ds.floor_layers() for i, c in enumerate(lay) if c}


def median_cells(inp: maps_hd.Inputs, entry: dict, donors: dict, tiles: dict):
    ds = ds1_remap.Ds1(inp.mod_tiles.read(entry["map"]))
    return map_cells(ds, entry["dt1_files"], tiles.get, lambda p: donors[p]["donor"] if p in donors else p)


def run(inp: maps_hd.Inputs, only=None, scene_of=d2r_scene, ground_of=d2r_ground):
    """-> (maps entries, {map: cells}, Library)."""
    maps, _dt1s, _levels = maps_hd.plan(inp)
    stock = maps_hd.parse_tiles(inp.d2r_tiles)
    mod = maps_hd.parse_tiles(inp.mod_tiles)
    tiles = dict(stock)
    tiles.update(mod)
    new = {k: v for k, v in mod.items() if k not in inp.d2r_tiles}
    donors = maps_hd.donor_table(new, stock)
    wanted = [e for e in maps if e["map"] in (only or MAPS)]
    cells = {e["map"]: median_cells(inp, e, donors, tiles) for e in wanted}
    lib = learn_library(inp, needed_stock(cells, donors), scene_of, stock, ground_of)
    return wanted, cells, lib


def build(data_dir: Path, wanted, cells, lib, biomes=None, read=None, d2r_read=None, floors=None):
    """Write the wall scenes. -> {map: stats + bytes}. biomes: {map: biome name}; None = the biome of the scene maps_hd's
    build wrote into data_dir (a generated floor biome, maps_hd.floor_biomes), else the plan's. The maps of map_tint.TINTS get a
    copy of that biome with their own key light (tools/map_tint.py); read(rel) -> D2R json for it (default fxpaths).
    The maps of TERRAIN_MAPS also get their terrain mesh (terrain_model; d2r_read(rel) -> the template's bytes, default
    d2r_bytes), next to the scene as <map>/terrain_lod0.model, over floors[map] (floor_tiles; default: the map's cells);
    the map's size is its cells' extent (the corner tiles)."""
    out = {}
    for e in wanted:
        biome = (biomes.get(e["map"]) if biomes is not None else maps_hd.scene_biome(data_dir, e["map"])) or e["biome"]
        biome = map_tint.apply(data_dir, e["map"], map_tint.base_biome(data_dir, biome, e["biome"]), read)   # the 8 retextured maps: a biome with the map's own light
        text, st = build_scene(cells[e["map"]], lib, biome)
        dest = Path(data_dir) / "hd" / "env" / "preset" / (e["map"][:-4] + ".json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if e["map"] in TERRAIN_MAPS:
            mc = cells[e["map"]]
            template = (d2r_read or d2r_bytes)("data/hd/env/preset/%s/terrain_lod0.model" % TERRAIN_MAPS[e["map"]])
            ground = terrain_cells((floors or {}).get(e["map"]) or mc)
            model = terrain_model(template, ground, max(x for x, _ in mc) + 1, max(y for _, y in mc) + 1)
            (dest.parent / dest.stem).mkdir(exist_ok=True)
            (dest.parent / dest.stem / "terrain_lod0.model").write_bytes(model)
            text = add_terrain(text, "data/hd/env/preset/%s/terrain.model" % e["map"][:-4])
            st = dict(st, terrain_cells=len(ground), terrain_bytes=len(model))
        dest.write_text(text, encoding="utf-8")
        out[e["map"]] = dict(st, bytes=len(text.encode("utf-8")), biome=biome)
    return out


def md_table(stats: dict, lib: Library) -> str:
    lines = ["| map | biome | wall cells | exact | partial | generic | no D2R model | uncovered | floor cells (with models) "
             "| set pieces left out | placed | capped | models in scene | distinct models | scene size |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    tot = collections.Counter()
    for m in MAPS:
        s = stats.get(m)
        if not s:
            continue
        lines.append("| %s | %s | %d | %d | %d | %d | %d | %d | %d (%d) | %d | %d | %d | %d | %d | %.0f KB |" % (
            m, s.get("biome", ""), s["cells"], s.get("exact", 0), s.get("partial", 0), s.get("generic", 0), s.get("empty", 0),
            s.get("uncovered", 0), s.get("floor_cells", 0), s.get("floor_walls", 0), s.get("set_pieces", 0), s.get("placed", s["entities"]), s.get("capped", 0), s["entities"],
            s.get("models", 0), s["bytes"] / 1024))
        tot.update({k: v for k, v in s.items() if isinstance(v, int) and k != "models"})
    lines.append("| all | | %d | %d | %d | %d | %d | %d | %d (%d) | %d | %d | %d | %d | | %.0f KB |" % (
        tot["cells"], tot["exact"], tot["partial"], tot["generic"], tot["empty"], tot["uncovered"], tot["floor_cells"],
        tot["floor_walls"], tot["set_pieces"],
        tot["placed"], tot["capped"], tot["entities"], tot["bytes"] / 1024))
    lines += ["", "Learnt from %d D2R maps (%d wall and floor cells, %d distinct cell keys, %d variants). *exact*: the cell's wall tiles "
              "were seen together in a D2R map; *partial*: the variant of a learnt key that shares a tile; *generic*: a wall "
              "tile D2R never has in a scene gets D2R's most common wall of the same orientation in the same tile set or act "
              "(Library.generic_pick); *no D2R model*: D2R draws that tile without an entity (part of a map's baked terrain or "
              "nothing); *uncovered*: no wall drawn in HD (not a wall orientation, or no learnt wall of that orientation); *floor "
              "cells*: cells with a floor and no wall, in brackets those that get the models D2R puts on that floor tile (cave "
              "walls, ledges, stairs, trims; floor_cells); *set "
              "pieces*: models D2R places on fewer than %d wall cells (Library.set_piece); *capped*: pieces cap() dropped to stay "
              "within D2R's largest scene (docktown3: %d placed models, %.2f MB)." % (
                  len(lib.sources), sum(lib.sources.values()), len(lib.seen), len(lib.variants), SET_PIECE_CELLS, MAX_PLACED,
                  MAX_BYTES / 1048576)]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["report", "build", "docs"])
    ap.add_argument("path", nargs="?", help="build: the data folder (default work/maps_hd/data); docs: the file")
    ap.add_argument("--out", default=str(ROOT / "work" / "maps_hd"), help="report folder")
    ap.add_argument("--extract", help="the mod's extracted MPQ")
    ap.add_argument("--d2r", help="D2R 93847 baseline extract with filelist.txt")
    a = ap.parse_args(argv)
    inp = maps_hd.Inputs.load(a.extract, a.d2r)
    wanted, cells, lib = run(inp)
    data_dir = Path(a.path) if a.cmd == "build" and a.path else ROOT / "work" / "maps_hd" / "walls_data"
    biomes = None
    if a.cmd != "build":     # no maps_hd build in this folder: write the floor biomes here too
        maps, dt1s, _levels = maps_hd.plan(inp)
        biomes = maps_hd.floor_biomes(data_dir, maps, dt1s)
    stats = build(data_dir, wanted, cells, lib, biomes, floors={m: floor_tiles(inp, m) for m in TERRAIN_MAPS if m in cells})
    table = md_table(stats, lib)
    if a.cmd in ("report", "docs"):
        f, t, n = self_check(inp, lib)
        table += ("\n\nSelf-check (D2R's own maps, `self_check`): the scenes this method makes for %d of the learnt D2R maps have "
                  "%d of their %d wall entities (%.0f%%; same model within 1.5 units)." % (n, f, t, 100.0 * f / max(1, t)))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "walls_report.json").write_text(json.dumps({"maps": stats, "sources": dict(lib.sources)}, indent=1), encoding="utf-8")
    (out / "walls_report.md").write_text("# HD wall scenes\n\n" + table + "\n", encoding="utf-8")
    if a.cmd == "docs":
        target = Path(a.path or ROOT / "docs" / "maps-hd.md")
        text = target.read_text("utf-8")
        if DOCS_BEGIN not in text:
            raise SystemExit("%s lacks the %s ... %s markers" % (target, DOCS_BEGIN, DOCS_END))
        head, rest = text.split(DOCS_BEGIN, 1)
        tail = rest.split(DOCS_END, 1)[1]
        new = head + DOCS_BEGIN + "\n\n" + table + "\n\n" + DOCS_END + tail
        if new != text:
            target.write_text(new, encoding="utf-8")
        print("updated" if new != text else "unchanged", target)
    print(table)
    total = sum(s["bytes"] for s in stats.values())
    print("wrote %d wall scenes (%.1f MB) to %s" % (len(stats), total / 1048576, data_dir / "hd" / "env" / "preset"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
