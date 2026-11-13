"""Generated terrain for a hand-built Median map: a terrain-material mesh and its floor physics (docs/maps-hd-method.md).

D2R expresses height in a terrain mesh modelled per map (`preset/<map>/terrain.model`, painted by the floor tiles' biomes
through the TerrainMaterial) with a floor body (`terrain.physics`) that units stand on. A hand-built Median map has neither.
This tool writes both from a height per tile corner:

  model()    a `_lod0.model` from one of D2R's own terrain models as template (vertex layout, material and bone kept; the
             mesh replaced and padded to the template's counts, which the engine's model index stores)
  physics()  a `.physics` file: vertices, triangles with the vertex across each edge, and a box tree over the triangles
  entity()   the scene entity that draws the mesh and carries the floor body (a plain entity, no terrain component)
  lift_quads()  the mesh of ground described in tile space with a height per corner, in D2R's convention: the camera
             looks down at 30 degrees along the tile diagonal (a tile is twice as wide as high on the screen), so
             the ground of tile point (x, z) at height g is modelled at (x + SLIDE * g, g, z + SLIDE * g) and stays over
             its tile
  rect(), stair()  the quads of a cell or a flat run, and of a flight of steps (treads and upright risers)
  raise_entities() the scene's own pieces moved up the view axis onto the ground under them

What the engine does with it (docs/maps-hd-method.md "Generated terrain: one terrace"): the mesh draws as a plain entity
when its `.model` path is in data/hd/model_lod_desc.bin (lod_table: an entry copied from the D2R terrain model that served
as template, whose vertex and index counts the file keeps); it is painted by the floor tiles' biomes like the engine's
ground plane, lit by its normals, and it hides what stands behind it. A height only shows through that: ground lifted
along the view axis stays over its tile on the screen.

    py -3 -I tools/maps_terrain.py info <terrain_lod0.model | terrain.physics | data/hd/... path>
"""
import collections
import copy
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401

TILE = 10.0
SLIDE = math.sqrt(1.5)   # what a point raised by 1 moves along x and along z to stay where it was on the screen: the view
#                          axis is (-SLIDE, -1, -SLIDE). Seen in game: a piece raised by 18.2 with a slide of 1 per unit
#                          stood 50 pixels (of 12 per unit along x) too high.
STEP = 6 / SLIDE         # 4.899: one terrace step of D2R's Travincal and Kurast terrain, a slide of 6
MARGIN = 0.0328084       # physics boxes are 1 cm (in D2R's feet) wider than the triangles
LEAF_MAX = 4             # triangles per leaf of the box tree, as in D2R's files
NODE, VERTEX, TRIANGLE, HEADER = 32, 16, 32, 48
MODEL_PATH = "data/hd/env/model/mxl/terrain/%s.model"
PHYSICS_PATH = "data/hd/env/model/mxl/terrain/%s.physics"
ID_BASE = 0x6F100000     # entity ids of terrain pieces: clear of walls_hd (0x6D78...), walkways (0x6D7F...) and sprites (0x6E78...)
# D2R terrain models that serve as template and as donor of the model index entry, by size: (vertices, indices, .model path)
DONORS = ((4, 6, "data/hd/env/preset/act3/travincal/mephswarpu/terrain.model"),
          (159, 369, "data/hd/env/preset/act3/travincal/travn/terrain.model"),
          (877, 1890, "data/hd/env/preset/act3/travincal/travs/terrain.model"),
          (6561, 38400, "data/hd/env/preset/act3/kurast/borderburbsw1/terrain.model"),
          (10210, 59832, "data/hd/env/preset/act3/kurast/burbs16x08_2/terrain.model"),
          (20716, 114051, "data/hd/env/preset/expansion/icecave/riverice04/terrain.model"))


def donor(vertices: int, triangles: int) -> str:
    """The smallest of DONORS that holds a mesh of this size."""
    for nv, ni, path in DONORS:
        if vertices <= nv and triangles * 3 <= ni:
            return path
    raise ValueError("maps_terrain: no donor for %d vertices / %d triangles; split the mesh" % (vertices, triangles))


def lod0(path: str) -> str:
    """The file of a `.model` path."""
    return path[:-len(".model")] + "_lod0.model"


# ---- mesh ---------------------------------------------------------------------------------------------------------------------
def normal(a, b, c):
    """Unit normal of a triangle, (b - a) x (c - a): up for D2R's winding seen from above."""
    u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    length = math.sqrt(sum(x * x for x in n))
    return tuple(x / length for x in n) if length > 1e-12 else (0.0, 1.0, 0.0)


def area(a, b, c) -> float:
    u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return math.sqrt(sum(x * x for x in n)) / 2


def lift(x: float, z: float, g: float):
    """The world point of the ground of tile-space point (x, z) at height g."""
    return (x + SLIDE * g, g, z + SLIDE * g)


def lift_quads(quads, origin=(0.0, 0.0)):
    """(positions, triangles) of ground given in tile space: each quad is 4 corners (x, z, g) in world units of the flat
    map with the height g of the ground there, in the order (x0, z0), (x1, z0), (x1, z1), (x0, z1). Every corner is lifted
    along the view axis (lift), so the quad is drawn over the same tiles whatever its heights. A tread is a quad with one
    height; the riser under its near edge is a quad whose far corners have the tread's height and whose near corners, the
    drop further on in x or z, the lower one: lifted, it stands upright. Corners that coincide are shared.
    Positions are relative to `origin` (tile space)."""
    index, pos, tris = {}, [], []

    def corner(c):
        key = (round(c[0], 3), round(c[1], 3), round(c[2], 3))
        if key not in index:
            index[key] = len(pos)
            pos.append(lift(c[0] - origin[0], c[1] - origin[1], c[2]))
        return index[key]
    for q in quads:
        a, b, c, d = (corner(v) for v in q)
        tris += [t for t in ((a, c, b), (a, d, c)) if len(set(t)) == 3]
    return pos, tris


def rect(x0, z0, x1, z1, g00, g10=None, g11=None, g01=None):
    """One quad for lift_quads: the tile-space rectangle with a height per corner (x0 z0, x1 z0, x1 z1, x0 z1; one height
    for flat ground)."""
    g10 = g00 if g10 is None else g10
    g11 = g00 if g11 is None else g11
    g01 = g00 if g01 is None else g01
    return ((x0, z0, g00), (x1, z0, g10), (x1, z1, g11), (x0, z1, g01))


def stair(x0, z0, x1, z1, top, bottom, steps, axis="z"):
    """The quads of a flight of steps over a tile-space rectangle, falling from `top` to `bottom` along +z (or +x): per step
    a flat tread and an upright riser. A riser of height r takes SLIDE * r of the run on the screen, so a step of run d has
    a tread of d - SLIDE * r, which must be more than nothing."""
    a0, a1 = (z0, z1) if axis == "z" else (x0, x1)
    d, r = (a1 - a0) / steps, (top - bottom) / steps
    if not 0 < SLIDE * r < d:
        raise ValueError("maps_terrain: steps of rise %.3f do not fit a run of %.3f" % (r, d))
    out = []
    for k in range(steps):
        g, a, b, c = top - k * r, a0 + k * d, a0 + k * d + d - SLIDE * r, a0 + (k + 1) * d
        if axis == "z":
            out += [rect(x0, a, x1, b, g), rect(x0, b, x1, c, g, g, g - r, g - r)]
        else:
            out += [rect(a, z0, b, z1, g), rect(b, z0, c, z1, g, g - r, g - r, g)]
    return out


def stair_height(a, a0, a1, top, bottom, steps):
    """The tread height of stair() at run position a."""
    k = min(max(int((a - a0) / ((a1 - a0) / steps)), 0), steps - 1)
    return top - k * (top - bottom) / steps


def merge_flat(cells, height_of):
    """Rectangles (x0, z0, x1, z1, g), x1 and z1 exclusive, covering the cells that are flat (height_of(cell) is a number,
    None for a cell that is not flat): rows of equal height first, then equal rows joined downwards. Fewer triangles than
    one quad per cell; the corners of two rectangles of one height do not have to meet, both lie in one plane."""
    flat = {c: height_of(c) for c in cells}
    flat = {c: round(g, 3) for c, g in flat.items() if g is not None}
    runs = collections.defaultdict(list)
    for x, z in sorted(flat, key=lambda c: (c[1], c[0])):
        g = flat[(x, z)]
        row = runs[z]
        if row and row[-1][1] == x and row[-1][2] == g:
            row[-1][1] = x + 1
        else:
            row.append([x, x + 1, g])
    out, open_ = [], {}
    for z in sorted(runs):
        nxt = {}
        for x0, x1, g in runs[z]:
            r = open_.pop((x0, x1, g), None)
            if r is not None and r[3] == z:
                r[3] = z + 1
            else:
                r = [x0, z, x1, z + 1, g]
                out.append(r)
            nxt[(x0, x1, g)] = r
        open_ = nxt
    return [tuple(r) for r in out]


def vertex_normals(pos, tris):
    """Per vertex the area-weighted mean of its triangles' normals."""
    acc = [[0.0, 0.0, 0.0] for _ in pos]
    for t in tris:
        a, b, c = (pos[i] for i in t)
        n, w = normal(a, b, c), area(a, b, c)
        for i in t:
            for k in range(3):
                acc[i][k] += n[k] * w
    out = []
    for n in acc:
        length = math.sqrt(sum(x * x for x in n))
        out.append(tuple(x / length for x in n) if length > 1e-12 else (0.0, 1.0, 0.0))
    return out


def split_faces(pos, tris, crease=0.5):
    """(positions, triangles, normals) with the vertices of faces that meet at a sharp edge (normals' dot under `crease`)
    doubled, so a riser is not shaded like the tread above it."""
    face = [normal(*(pos[i] for i in t)) for t in tris]
    groups = collections.defaultdict(list)          # vertex -> [(group normal, new index)]
    out_pos, out_n, out_tris = [], [], []
    for t, n in zip(tris, face):
        new = []
        for i in t:
            for gn, k in groups[i]:
                if sum(gn[j] * n[j] for j in range(3)) >= crease:
                    new.append(k)
                    break
            else:
                groups[i].append((n, len(out_pos)))
                new.append(len(out_pos))
                out_pos.append(pos[i])
                out_n.append(n)
        out_tris.append(tuple(new))
    return out_pos, out_tris, out_n


# ---- model --------------------------------------------------------------------------------------------------------------------
def _half(f: float) -> int:
    return struct.unpack("<H", struct.pack("<e", f))[0]


def counts(template: bytes):
    """(vertices, indices) of a one-mesh model: what a mesh made from it may hold."""
    import d2r_model as dm
    tree = dm.parse_tree(dm.Gr2File.read(template))
    if len(tree["Meshes"]) != 1 or not tree["Meshes"][0]["PrimaryTopology"]["Indices16"]:
        raise ValueError("maps_terrain: the template is not a one-mesh model with 16-bit indices")
    mesh = tree["Meshes"][0]
    return len(mesh["PrimaryVertexData"]["Vertices"].obj), len(mesh["PrimaryTopology"]["Indices16"])


def model(template: bytes, pos, tris, normals=None, size=None, pad=True):
    """A terrain `_lod0.model`: the template (one of D2R's terrain models: one rigid mesh 'terrainShape', vertices Position
    int16[4], Normal, Tangent, half-float UV, the TerrainMaterial) with its mesh replaced by (pos, tris). Positions are the
    model's own space, the entity's transform places it. Bone and placement at the mesh's centre and the bone box in bone
    space, as in D2R's; UV = position / size (size: (x, z) extent, the mesh's own by default).
    pad: as many vertices and indices as the template (copies of the first vertex, empty triangles), so the template's entry
    in model_lod_desc.bin fits the file. -> (bytes, bbMin, bbMax)"""
    import d2r_model as dm
    gr2 = dm.Gr2File.read(template)
    tree = dm.parse_tree(gr2)
    mesh = tree["Meshes"][0]
    vertices, topo = mesh["PrimaryVertexData"]["Vertices"], mesh["PrimaryTopology"]
    nv, ni = len(vertices.obj), len(topo["Indices16"])
    if not tris or not pos:
        raise ValueError("maps_terrain: empty mesh")
    if pad and (len(pos) > nv or len(tris) * 3 > ni or ni % 3):
        raise ValueError("maps_terrain: %d vertices / %d indices do not fit the template's %d / %d" % (len(pos), len(tris) * 3, nv, ni))
    if len(pos) > 65535:
        raise ValueError("maps_terrain: %d vertices" % len(pos))
    normals = list(normals) if normals is not None else vertex_normals(pos, tris)
    lo = [min(p[i] for p in pos) for i in range(3)]
    hi = [max(p[i] for p in pos) for i in range(3)]
    size = size or (max(hi[0] - lo[0], 1e-6), max(hi[2] - lo[2], 1e-6))
    scale = max(1.0, max(abs(c) for p in pos for c in p))
    w = int(round(math.log2(scale) / 13 * 32767))
    vtd = vertices.obj[0].td

    def vertex(p, n):
        return dm.Obj(vtd, {"Position": [int(round(c / scale * 32767)) for c in p] + [w],
                            "Normal": [int(round(c * 127)) for c in n] + [0], "Tangent": [127, 0, 0, -127],
                            "TextureCoordinates0": [_half((p[0] - lo[0]) / size[0]), _half((p[2] - lo[2]) / size[1])]})
    out = [vertex(p, n) for p, n in zip(pos, normals)]
    index = [i for t in tris for i in t]
    if pad:
        out += [out[0]] * (nv - len(out))
        index += [0] * (ni - len(index))
    vertices.obj = out
    itd = topo["Indices16"][0].td
    topo["Indices16"] = [dm.Obj(itd, {"Int16": i}) for i in index]
    topo["Groups"] = topo["Groups"][:1]
    topo["Groups"][0]["TriFirst"], topo["Groups"][0]["TriCount"] = 0, len(index) // 3
    centre = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    ed = mesh["ExtendedData"].obj
    ed["bbMin"], ed["bbMax"], ed["VertexScale"] = lo, hi, float(scale)
    for plane in ed.get("ReflectivePlanes") or ():
        plane["Position"] = [centre[0], lo[1], centre[2]]
        plane["Size"] = [hi[0] - lo[0], 0.0, hi[2] - lo[2]]
    for bind in mesh["BoneBindings"]:
        bind["OBBMin"] = [lo[i] - centre[i] for i in range(3)]
        bind["OBBMax"] = [hi[i] - centre[i] for i in range(3)]
    for bone in tree["Skeletons"][0]["Bones"]:
        bone["InverseWorldTransform"] = list(bone["InverseWorldTransform"][:12]) + [-centre[0], -centre[1], -centre[2], 1.0]
    for m in tree["Models"]:
        p = m["InitialPlacement"]
        m["InitialPlacement"] = dm.Transform(p.flags, centre, p.orientation, p.scale_shear)
    data = dm.Writer(gr2).build(tree).write()
    dm.parse_tree(dm.Gr2File.read(data))      # well formed
    return data, tuple(lo), tuple(hi)


def read_model(data: bytes):
    """(positions, triangles) of a model's meshes, empty triangles left out."""
    import d2r_model as dm
    import walls_hd
    pos, tris = walls_hd.terrain_mesh(dm.parse_tree(dm.Gr2File.read(data)))
    return pos, [t for t in tris if len(set(t)) == 3]


# ---- physics ------------------------------------------------------------------------------------------------------------------
def _box(pos, tris, order):
    pts = [pos[i] for n in order for i in tris[n]]
    return ([min(p[k] for p in pts) - MARGIN for k in range(3)], [max(p[k] for p in pts) + MARGIN for k in range(3)])


def physics(pos, tris) -> bytes:
    """A `.physics` file of a static triangle mesh, as D2R's terrain.physics (little endian):
      header 48 B  u64 offset of the nodes, the vertices, the triangles; u32 nodes, vertices, triangles, tree depth;
                   f32 area of all triangles; u32 0
      node 32 B    f32 min[3], max[3] (MARGIN wider); u32 first triangle (leaf) or index distance to the second child;
                   u16 0xFFFF; u8 3 (leaf) or the split axis; u8 triangles in the leaf
      vertex 16 B  f32 x, y, z, 0
      triangle 32 B  i32 vertex[3]; i32 per edge (v0 v1, v1 v2, v2 v0) the third vertex of the triangle across it, -1 for
                   an open edge; u32 0; u16 0xFFFF; u16 0
    Triangles are wound like the model's (normal up); a leaf's triangles follow each other in the file."""
    tris = [tuple(t) for t in tris if len(set(t)) == 3]
    if not tris:
        raise ValueError("maps_terrain: no triangles")
    mid = [tuple(sum(pos[i][k] for i in t) / 3 for k in range(3)) for t in tris]
    nodes, order = [], []

    def build(items, depth):
        lo, hi = _box(pos, tris, items)
        at = len(nodes)
        nodes.append(None)
        if len(items) <= LEAF_MAX:
            nodes[at] = (lo, hi, len(order), 3, len(items))
            order.extend(items)
            return depth
        axis = max((0, 2, 1), key=lambda k: max(mid[n][k] for n in items) - min(mid[n][k] for n in items))
        items = sorted(items, key=lambda n: (mid[n][axis], n))
        half = len(items) // 2
        d1 = build(items[:half], depth + 1)
        second = len(nodes)
        d2 = build(items[half:], depth + 1)
        nodes[at] = (lo, hi, second - at, axis, 0)
        return max(d1, d2)
    depth = build(list(range(len(tris))), 1)
    tris = [tris[n] for n in order]
    across = {}
    for t in tris:
        for k in range(3):
            across[(t[k], t[(k + 1) % 3])] = t[(k + 2) % 3]
    out = bytearray(struct.pack("<3Q4IfI", HEADER, HEADER + NODE * len(nodes), HEADER + NODE * len(nodes) + VERTEX * len(pos),
                                len(nodes), len(pos), len(tris), depth, sum(area(*(pos[i] for i in t)) for t in tris), 0))
    for lo, hi, a, kind, n in nodes:
        out += struct.pack("<6fIHBB", *lo, *hi, a, 0xFFFF, kind, n)
    for p in pos:
        out += struct.pack("<4f", p[0], p[1], p[2], 0.0)
    for t in tris:
        adj = [across.get((t[(k + 1) % 3], t[k]), -1) for k in range(3)]
        out += struct.pack("<6iIHH", *t, *adj, 0, 0xFFFF, 0)
    return bytes(out)


def read_physics(data: bytes) -> dict:
    """The parts of a `.physics` file: {"nodes": [(min, max, a, kind, n)], "pos": [...], "tris": [...], "adjacent": [...],
    "depth": n, "area": f}. ValueError when the layout is not the one physics() writes."""
    o1, o2, o3, nn, nv, nt, depth, total, zero = struct.unpack_from("<3Q4IfI", data, 0)
    if (o1, o2, o3) != (HEADER, HEADER + NODE * nn, HEADER + NODE * nn + VERTEX * nv) or o3 + TRIANGLE * nt != len(data) or zero:
        raise ValueError("maps_terrain: not a triangle-mesh .physics file")
    nodes = []
    for i in range(nn):
        b = struct.unpack_from("<6fIHBB", data, o1 + i * NODE)
        nodes.append((b[:3], b[3:6], b[6], b[8], b[9]))
    pos = [struct.unpack_from("<3f", data, o2 + i * VERTEX) for i in range(nv)]
    rows = [struct.unpack_from("<6i", data, o3 + i * TRIANGLE) for i in range(nt)]
    return {"nodes": nodes, "pos": pos, "tris": [r[:3] for r in rows], "adjacent": [r[3:] for r in rows], "depth": depth, "area": total}


# ---- scene --------------------------------------------------------------------------------------------------------------------
def entity(name: str, serial: int, model_path: str, physics_path=None, position=(0.0, 0.0, 0.0), shadows=True) -> dict:
    """The entity that draws a terrain mesh: D2R's own terrain entity without the terrain component (a preset has one
    terrain and the engine does not draw a mod's through it), with D2R's floor body when a physics file is given.
    shadows=False: the mesh casts none (ground lifted over lower ground is a sheet in the air to the light)."""
    comps = [
        {"type": "TransformDefinitionComponent", "name": name + "_t",
         "position": {"x": round(position[0], 4), "y": round(position[1], 4), "z": round(position[2], 4)},
         "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}, "scale": {"x": 1.0, "y": 1.0, "z": 1.0}, "inheritOnlyPosition": False},
        {"type": "ModelDefinitionComponent", "name": name + "_m", "filename": model_path, "visibleLayers": 1, "lightMask": 19,
         "shadowMask": 3 if shadows else 0, "ghostShadows": False, "floorModel": False, "terrainBlendEnableYUpBlend": False, "terrainBlendMode": 1}]
    if physics_path:
        comps.append({
            "type": "PhysicsBodyDefinitionComponent", "name": name + "_p", "bodytype": "static",
            "fixturedefs": [{"type": "PhysicsFixtureDefinition", "name": "physicsFixtureDefinition",
                             "shapetype": {"type": "PhysicsFileDefinition", "name": "physicsFileDefinition", "filename": physics_path},
                             "friction": 0.6, "restitution": 0.0, "rollingresistance": 0.2, "impulsefactor": 1.0, "explosionfactor": 1.0,
                             "explosionliftfactor": 1.0, "windfactor": 0.0, "dragfactor": 0.0, "liftfactor": 1.0, "density": 37.5,
                             "boneindex": -1}],
            "filter": "floor", "allowTransition": True, "removeOnDeath": True, "lineardamping": 0.0, "angulardamping": 0.0,
            "gravityscale": 1.0})
    return {"type": "Entity", "name": name, "id": ID_BASE + serial, "components": comps}


def add_entities(scene: dict, entities) -> dict:
    """A copy of the scene with the terrain entities added and their model and physics files named in the dependencies."""
    scene = copy.copy(scene)
    scene["entities"] = list(scene.get("entities", ())) + list(entities)
    deps = scene["dependencies"] = {k: list(v) for k, v in scene.get("dependencies", {}).items()}
    for e in entities:
        for c in e["components"]:
            if c["type"] == "ModelDefinitionComponent":
                _depend(deps, "models", c["filename"])
            elif c["type"] == "PhysicsBodyDefinitionComponent":
                for f in c["fixturedefs"]:
                    _depend(deps, "physics", f["shapetype"]["filename"])
    return scene


def _depend(deps: dict, kind: str, path: str):
    lst = deps.setdefault(kind, [])
    if not any(d.get("path") == path for d in lst):
        lst.append({"path": path})


def raise_entities(entities, height_at, drop=lambda e: False):
    """The entities standing on raised ground: each moved up the view axis by the height of the ground under it
    (height_at(x, z), tile space), so it shows over the same tile and stands on the terrain there. Entities `drop` says yes
    to are left out. -> (entities, moved)"""
    out, moved = [], 0
    for e in entities:
        if drop(e):
            continue
        t = next((c for c in e.get("components", ()) if c.get("type") == "TransformDefinitionComponent"), None)
        p = (t or {}).get("position")
        g = height_at(float(p.get("x", 0.0)), float(p.get("z", 0.0))) if p else 0.0
        if g:
            e = copy.deepcopy(e)
            p = next(c for c in e["components"] if c.get("type") == "TransformDefinitionComponent")["position"]
            for k in ("x", "y", "z"):
                p[k] = round(float(p.get(k, 0.0)) + (g if k == "y" else SLIDE * g), 4)
            moved += 1
        out.append(e)
    return out, moved


def lod_table(table: bytes, entries) -> bytes:
    """model_lod_desc.bin with the generated models added: entries [(new .model path, donor .model path, (bbMin, bbMax))]."""
    import model_lod_desc
    return model_lod_desc.add(table, {new: donor for new, donor, _b in entries}, {new: b for new, _d, b in entries})


# ---- command line -------------------------------------------------------------------------------------------------------------
def info(path: str) -> str:
    import walls_hd
    p = Path(path)
    data = p.read_bytes() if p.exists() else walls_hd.d2r_bytes(path)
    if data is None:
        return "%s: not found" % path
    if path.endswith(".physics"):
        ph = read_physics(data)
        ys = [v[1] for v in ph["pos"]]
        return "%s: %d B, %d nodes, %d vertices, %d triangles, depth %d, area %.1f, y %.2f..%.2f" % (
            path, len(data), len(ph["nodes"]), len(ph["pos"]), len(ph["tris"]), ph["depth"], ph["area"], min(ys), max(ys))
    pos, tris = read_model(data)
    nv, ni = counts(data)
    lo = [min(v[i] for v in pos) for i in range(3)]
    hi = [max(v[i] for v in pos) for i in range(3)]
    return "%s: %d B, %d vertices, %d indices, %d triangles drawn, box %s .. %s" % (
        path, len(data), nv, ni, len(tris), [round(v, 2) for v in lo], [round(v, 2) for v in hi])


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2 or argv[0] != "info":
        print(__doc__)
        return 1
    for p in argv[1:]:
        print(info(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
