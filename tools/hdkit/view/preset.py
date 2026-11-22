"""Map presets as scenes: a D2R preset JSON (`data/hd/env/preset/...`) and its classic .ds1 turned into placed models and
point lights for gpu.Renderer.

  placements(fs, preset)     every model the preset places: entities with a ModelDefinitionComponent (props, rocks,
                             foliage, the `terrain` entity's terrain.model) and one level of PrefabPlacementDefinitionComponent
                             (the prefab's own model entities, their transforms composed with the placement's)
  ds1_objects(ds1, objects)  the .ds1's object list mapped through `objects` ((type, id) -> HD unit JSON and classic light) to
                             placed units and point lights; positions are sub-tiles of the .ds1 (world = 2 units each)
  Scene / build_scene(...)   both, plus extra units (e.g. corpses) and the lights, ready for prepare_scene(renderer, scene)

Not drawn (listed in Scene.notes): terrain decals and stamps, particle effects, audio, physics bodies, the biome's grass and
clutter. The ground is the preset's terrain.model with ONE biome layer's textures projected from above (the per-tile
blend of the biome's layers lives in data this module does not read).

Axes: world x, z = 2 x the .ds1 sub-tile x, y (sprite_scene.point_entity's rule, also the harness's), y up; transforms are
TransformDefinitionComponent position, orientation (x, y, z, w quaternion, the usual convention; unverified against the
engine beyond the placements looking right on the sheet) and scale.
"""
import json
from dataclasses import dataclass, field

import numpy as np

UNITS_PER_SUBTILE = 2.0

# (ds1 object type, id) in act 1 -> what the HD game draws and the classic light (objects.txt) it carries
ACT1_OBJECTS = {
    (2, 1): {"name": "Torch1 Tiki (objects.txt Id 37)", "unit": "data/hd/objects/braziers/tiki_torch_1.json",
             "light": {"radius_subtiles": 19, "rgb": (255, 178, 0), "height": 6.5}},
}


def quat_matrix(q) -> np.ndarray:
    x, y, z, w = (float(q.get(k, d)) for k, d in (("x", 0), ("y", 0), ("z", 0), ("w", 1))) if isinstance(q, dict) else q
    n = (x * x + y * y + z * z + w * w) ** 0.5 or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def trs(td: dict | None) -> np.ndarray:
    """4x4 of a TransformDefinitionComponent (identity when None)."""
    M = np.eye(4)
    if not td:
        return M
    p, s = td.get("position") or {}, td.get("scale") or {}
    S = np.diag([float(s.get(k, 1.0)) for k in "xyz"])
    M[:3, :3] = quat_matrix(td.get("orientation") or {}) @ S
    M[:3, 3] = [float(p.get(k, 0.0)) for k in "xyz"]
    return M


def _components(ent):
    return {c["type"]: c for c in ent.get("components", [])}


@dataclass
class Placement:
    name: str
    model: str                 # logical path of the .model (or a unit JSON for objects)
    matrix: np.ndarray         # 4x4 world
    kind: str = "prop"         # prop, terrain, prefab, object, unit
    light_mask: int | None = None
    floor: bool = False
    entity: int = -1           # index in the preset's entity list (-1: not from the preset)
    wall: bool = False         # the entity (or its prefab placement) has a WallTransparencyComponent
    prefab: str = ""           # the prefab JSON a member came from


@dataclass
class Scene:
    preset: str
    placements: list
    lights: list = field(default_factory=list)       # gpu point-light dicts (pos, radius, color, atten) + name
    biome: str | None = None
    notes: list = field(default_factory=list)
    skipped: dict = field(default_factory=dict)      # component type -> count not drawn


def _read_json(fs, logical):
    return json.loads(fs.read(logical).decode("utf-8-sig"))


SKIP = {"TerrainDecalDefinitionComponent", "TerrainStampDefinitionComponent", "AudioEmitterComponent",
        "PhysicsBodyDefinitionComponent", "VfxDefinitionComponent", "ParticleDefinitionComponent"}


def placements(fs, preset: str, prefabs: bool = True):
    """-> (placements, skipped component counts, biome file) of a preset JSON."""
    d = _read_json(fs, preset)
    out, skipped = [], {}
    for ei, ent in enumerate(d.get("entities", [])):
        c = _components(ent)
        M = trs(c.get("TransformDefinitionComponent"))
        wall = "WallTransparencyComponent" in c
        for t in c:
            if t in SKIP:
                skipped[t] = skipped.get(t, 0) + 1
        md = c.get("ModelDefinitionComponent")
        if md:
            kind = "terrain" if "TerrainDefinitionComponent" in c else "prop"
            out.append(Placement(ent.get("name", ""), md["filename"], M, kind, md.get("lightMask"), bool(md.get("floorModel")),
                                 ei, wall))
        pf = c.get("PrefabPlacementDefinitionComponent")
        if pf and prefabs:
            try:
                sub = _read_json(fs, pf["prefab"])
            except (OSError, KeyError, ValueError):
                skipped["prefab missing"] = skipped.get("prefab missing", 0) + 1
                continue
            for e2 in sub.get("entities", []):
                c2 = _components(e2)
                m2 = c2.get("ModelDefinitionComponent")
                if m2:
                    out.append(Placement("%s/%s" % (ent.get("name", ""), e2.get("name", "")), m2["filename"],
                                         M @ trs(c2.get("TransformDefinitionComponent")), "prefab", m2.get("lightMask"),
                                         bool(m2.get("floorModel")), ei, wall or "WallTransparencyComponent" in c2,
                                         pf["prefab"]))
    return out, skipped, d.get("biomeFilename")


def point_light(x_sub: float, y_sub: float, radius_subtiles: float, rgb, height: float, power: float = 1.0,
                atten: float = 2.0, name: str = "") -> dict:
    """A gpu point light for a classic light: at sub-tile (x, y), `height` units up, radius = the classic radius in
    sub-tiles x 2 units, colour = rgb (0-255) linearised (gamma 2.2) and normalised to its largest channel, x power."""
    lin = [(c / 255.0) ** 2.2 for c in rgb]
    top = max(lin) or 1.0
    return {"name": name, "pos": (x_sub * UNITS_PER_SUBTILE, float(height), y_sub * UNITS_PER_SUBTILE),
            "radius": radius_subtiles * UNITS_PER_SUBTILE, "color": [power * c / top for c in lin], "atten": float(atten)}


def ds1_objects(objects_list, table=None, power: float = 1.0, atten: float = 2.0):
    """-> (object placements, point lights, unknown objects) of a .ds1 object list [type, id, x, y, flags]."""
    table = ACT1_OBJECTS if table is None else table
    out, lights, unknown = [], [], []
    for i, (t, ident, x, y, _f) in enumerate(objects_list):
        e = table.get((t, ident))
        if e is None:
            unknown.append((t, ident, x, y))
            continue
        M = np.eye(4)
        M[:3, 3] = (x * UNITS_PER_SUBTILE, 0.0, y * UNITS_PER_SUBTILE)
        out.append(Placement("%s@%d,%d" % (e["name"], x, y), e["unit"], M, "object", 19))
        L = e.get("light")
        if L:
            lights.append(point_light(x, y, L["radius_subtiles"], L["rgb"], L["height"], power, atten,
                                      "%s@%d,%d" % (e["name"], x, y)))
    return out, lights, unknown


def build_scene(fs, preset: str, ds1_bytes: bytes | None = None, object_power: float = 1.0, object_atten: float = 2.0,
                table=None) -> Scene:
    pl, skipped, biome = placements(fs, preset)
    sc = Scene(preset, pl, [], biome, [], skipped)
    if ds1_bytes is not None:
        import ds1_remap
        ds = ds1_remap.Ds1(ds1_bytes)
        objs, lights, unknown = ds1_objects(ds.objects, table, object_power, object_atten)
        sc.placements += objs
        sc.lights += lights
        if unknown:
            sc.notes.append("ds1 objects without an HD mapping (not drawn): %s" % unknown)
    sc.notes.append("not drawn: %s" % ", ".join("%s x%d" % kv for kv in sorted(skipped.items())))
    return sc


def ground_textures(fs, biome: str, layer: int = 1, quality: str = "terrainDataHigh") -> dict:
    """usage -> logical texture of one terrain layer of a biome (Albedo / Normal / ORM)."""
    b = _read_json(fs, biome)
    lay = b[quality]["terrainLayers"][layer]
    return {"AlbedoTexture": lay["Albedo"], "NormalTexture": lay["Normal"], "ORMTexture": lay["ORM"]}


def prepare_scene(R, fs, sc: Scene, cam, ground_layer: int = 1, ground_tile: float = 10.0, lod: int = 0, log=print,
                  extra=()):
    """gpu.Prepared of a scene: every placement loaded (scene.load_unit / load_model_part through `fs`), its draws with
    light class 'world'; the terrain re-textured with one biome layer, UV = world (x, z) / ground_tile. `extra`: more
    (Prepared) draws to add, e.g. corpses with light class 'unit'."""
    from . import scene as S
    from .gpu import Prepared
    out = Prepared([])
    cache = {}
    tex = ground_textures(fs, sc.biome, ground_layer) if sc.biome else {}
    for p in sc.placements:
        try:
            if p.model not in cache:
                if p.model.lower().endswith(".json"):
                    cache[p.model] = S.load_unit(fs, p.model, lod)
                else:
                    cache[p.model] = S.Unit(p.name, [S.load_model_part(fs, p.model, p.name, lod)])
            unit = cache[p.model]
        except (OSError, FileNotFoundError, KeyError, ValueError) as e:
            out.notes.append("%s: %s not loaded (%s)" % (p.name, p.model, e))
            continue
        if p.kind == "terrain" and tex:
            unit = _retextured_ground(fs, unit, tex, p.matrix, ground_tile)
        prep = R.prepare(unit, None, 0.0, 0.0, cam, place=p.matrix, light_class="world")
        out.draws += prep.draws
    for e in extra:
        out.draws += e.draws
    out.notes += sc.notes
    log("scene %s: %d placements, %d draws" % (sc.preset, len(sc.placements), len(out.draws)))
    return out


def _retextured_ground(fs, unit, tex: dict, M, tile: float):
    from dataclasses import replace
    from . import scene as S
    part = unit.parts[0]
    meshes = []
    for m in part.meshes:
        P = m.pos @ M[:3, :3].T + M[:3, 3]
        meshes.append(replace(m, uv=np.stack([P[:, 0] / tile, P[:, 2] / tile], 1).astype(np.float32)))
    tx = {u: S.read_texture(fs, lg, srgb=(u == "AlbedoTexture")) for u, lg in tex.items() if fs.exists(lg)}
    return S.Unit(unit.name, [S.Part(part.name, part.model, meshes, part.skeleton, tx)])
