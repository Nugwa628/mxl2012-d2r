"""Things on an HD map that are not preset models: the .ds1's objects as their HD units, and the preset's effects.

* Objects (`.ds1` type 2): (act, id) -> ObjPreset ObjectClass -> objects.txt row -> D2R's `data/hd/objects/objects.json`
  (its keys follow objects.txt's rows in order: row 37 TikiTorch1 = "tiki_torch_1") -> `data/hd/objects/<asset_path>/
  <key>.json`, drawn in its rest pose at sub-tile (x, y) x 2 world units, turned by the unit's rotationOverride. Units
  whose effects (dependencies.particles) look like fire also get a fire card and a light (below).
* Effects (VfxDefinitionComponent): particle systems are not simulated. Fire-like ones (file name with fire, flame, torch,
  candle, brazier, bonfire, ember, lava) are drawn as an emissive, alpha-blended flame card facing the camera and carry a
  warm point light (FIRE_KINDS: size, radius, power; calibrated against game captures, docs/mapview.md). Others (dust,
  fog, leaves, sparkles) are counted, not drawn.
* Monsters and NPCs (`.ds1` type 1) are not drawn in HD (the classic overlay marks them).
"""
from __future__ import annotations

import json
import math
import re

import numpy as np

# kind: (card width, card height, light radius, light power, light height) in world units / preset power units
FIRE_KINDS = {
    "candle": (1.0, 1.6, 14.0, 160.0, 2.0),
    "torch": (2.2, 3.4, 26.0, 700.0, 6.0),
    "brazier": (2.6, 3.6, 30.0, 900.0, 5.0),
    "fire": (3.6, 5.0, 34.0, 1000.0, 4.0),
}
FIRE_RE = re.compile(r"(candle|torch|brazier|bonfire|fire|flame|ember|lava)", re.I)
FIRE_RGB = (1.0, 0.56, 0.18)
EMISSIVE = 30.0              # flame cards: emissive x the albedo (exposure 0.073 brings it near 2)


def fire_kind(name: str) -> str | None:
    m = FIRE_RE.search(name or "")
    if not m:
        return None
    w = m.group(1).lower()
    if w == "candle":
        return "candle"
    if w in ("torch",):
        return "torch"
    if w in ("brazier",):
        return "brazier"
    return "fire"


_FLAME = {}


def flame_texture():
    """A soft flame picture (RGBA): white-yellow core, orange rim, alpha falling to 0 at the edge and the top."""
    if "t" not in _FLAME:
        from .. import scene as S
        from ..gpu import _mip_chain
        h, w = 128, 64
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        u = (x + 0.5) / w * 2 - 1
        v = 1 - (y + 0.5) / h                       # 0 bottom, 1 top
        width = 0.85 * np.clip(1.15 - v, 0, 1) ** 0.8 * np.clip(v * 4, 0, 1) ** 0.5 + 1e-3
        r = np.abs(u) / width
        core = np.clip(1 - r, 0, 1) * np.clip(1 - v * 0.9, 0, 1)
        a = np.clip(core * 1.6, 0, 1) ** 1.2
        t = np.clip(core * 1.4, 0, 1)
        rgb = np.stack([np.ones_like(t), 0.35 + 0.6 * t, 0.08 + 0.7 * t ** 2], -1)
        img = np.dstack([np.round(rgb * 255), np.round(a * 255)]).astype(np.uint8)
        _FLAME["t"] = S.Texture("mapview:flame", 0, _mip_chain(img), True)
    return _FLAME["t"]


def fire_card(name, pos, kind, cam):
    from .. import gr2, scene as S
    w, h = FIRE_KINDS[kind][:2]
    r, u, _w = cam.basis()
    p = np.asarray(pos, float)
    P = np.array([p - r * w / 2, p + r * w / 2, p + r * w / 2 + u * h, p - r * w / 2 + u * h])
    nrm = np.tile(_w, (4, 1))
    tan = np.tile(np.append(r, 1.0), (4, 1))
    uv = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], float)
    mesh = gr2.Mesh(name, P, nrm, tan, uv, np.array([[0, 1, 2], [0, 2, 3]]), {}, [], None, None,
                    {"blend": 1.0, "emissive": EMISSIVE})
    return S.Unit(name, [S.Part(name, "mapview:flame", [mesh], None, {"AlbedoTexture": flame_texture()})])


def fire_light(name, pos, kind):
    _w, _h, rad, power, hgt = FIRE_KINDS[kind]
    return {"name": name, "pos": (float(pos[0]), float(pos[1]) + hgt * 0.5, float(pos[2])), "radius": rad, "atten": 2.0,
            "color": [power * c for c in FIRE_RGB], "fire": kind}


_OBJ_INDEX = {}


def hd_object_units(fs) -> list:
    """[(key, asset_path)] of D2R's objects.json in file order (= objects.txt rows)."""
    if "x" not in _OBJ_INDEX:
        try:
            d = json.loads(fs.read("data/hd/objects/objects.json").decode("utf-8-sig"))
            _OBJ_INDEX["x"] = [(k, (v or {}).get("asset_path", "")) for k, v in d.items()]
        except (OSError, FileNotFoundError, ValueError):
            _OBJ_INDEX["x"] = []
    return _OBJ_INDEX["x"]


_D2R_ROWS = {}


def d2r_object_rows(roots) -> dict:
    """objects.txt Class (lower case) -> row, from D2R's own table (Median's objects.txt has no Class column; it keeps
    D2R's 574 rows in place, docs/maps-hd.md "IDs inside the maps")."""
    if "x" not in _D2R_ROWS:
        from . import world
        out = {}
        try:
            for i, r in enumerate(world.read_table(roots.tables("d2r") / "objects.txt")):
                out.setdefault((r.get("Class") or "").strip().lower(), i)
        except (OSError, FileNotFoundError, AttributeError):
            pass
        _D2R_ROWS["x"] = out
    return _D2R_ROWS["x"]


def object_unit_path(fs, tables, act: int, ident: int, roots=None) -> str | None:
    cls = tables.objpreset.get((act, ident))
    if cls is None:
        return None
    row = tables.object_row.get(cls.strip().lower())
    if row is None and roots is not None:
        row = d2r_object_rows(roots).get(cls.strip().lower())
    idx = hd_object_units(fs)
    if row is None or row >= len(idx):
        return None
    key, folder = idx[row]
    if not folder or folder == "dummy":
        return None
    p = "data/hd/objects/%s/%s.json" % (folder, key)
    return p if fs.exists(p) else None


def scene_extras(fs, pj: dict, src, fr, R, cam, fx=True, objects=True, log=None, margin=3):
    """-> {"draws", "lights", "info"} for the range of frame `fr`."""
    from .. import scene as S
    from ..preset import trs, quat_matrix
    draws, lights = [], []
    info = {"fx_fire": 0, "fx_other": 0, "objects_drawn": 0, "objects_without_hd_unit": 0, "object_errors": []}
    if fx:
        for ent in pj.get("entities", []):
            c = {k["type"]: k for k in ent.get("components", [])}
            vx = c.get("VfxDefinitionComponent")
            if not vx:
                continue
            M = trs(c.get("TransformDefinitionComponent"))
            x, y, z = M[:3, 3]
            if not fr.near(x / 10.0, z / 10.0, margin, 12.0):      # on the screen (Frame.near), not a box of cells
                continue
            kind = fire_kind(vx.get("filename", "") + " " + ent.get("name", ""))
            if kind is None:
                info["fx_other"] += 1
                continue
            info["fx_fire"] += 1
            draws += R.prepare(fire_card(ent.get("name", "fire"), (x, y, z), kind, cam), cam=cam, light_class="world").draws
            lights.append(fire_light(ent.get("name", "fire"), (x, y, z), kind))
    if objects:
        cache = {}
        act = src.ds.act + 1
        for o in src.ds.objects:
            if o.type != 2:
                continue
            x, z = o.x * 2.0, o.y * 2.0
            if not fr.near(x / 10.0, z / 10.0, margin, 12.0):
                continue
            path = object_unit_path(fs, src.tables, act, o.id, src.roots)
            if path is None:
                info["objects_without_hd_unit"] += 1
                continue
            if path not in cache:
                try:
                    cache[path] = S.load_unit(fs, path)
                except Exception as e:  # noqa: BLE001 (any unit that does not load is listed, not fatal)
                    cache[path] = None
                    info["object_errors"].append("%s: %s" % (path, repr(e)[:120]))
            unit = cache[path]
            if unit is None:
                continue
            M = np.eye(4)
            M[:3, :3] = quat_matrix(unit.rotation_override)
            M[:3, 3] = (x, 0.0, z)
            try:
                ud = R.prepare(unit, None, 0.0, 0.0, cam, place=M, light_class="world").draws
                draws += ud
            except Exception as e:  # noqa: BLE001
                info["object_errors"].append("%s: %s" % (path, repr(e)[:120]))
                continue
            info["objects_drawn"] += 1
            deps = " ".join(d.get("path", "") for d in (json.loads(fs.read(path).decode("utf-8-sig")).get("dependencies") or {})
                            .get("particles", []))
            kind = fire_kind(deps)
            if kind:
                top = max((float(dr.world[..., 1].max()) for dr in ud), default=2.0)
                pos = (x, max(top - FIRE_KINDS[kind][1] * 0.5, 0.0), z)
                draws += R.prepare(fire_card("%s-fire" % path, pos, kind, cam), cam=cam, light_class="world").draws
                lights.append(fire_light(path, pos, kind))
    info["object_errors"] = info["object_errors"][:10]
    return {"draws": draws, "lights": lights, "info": info}
