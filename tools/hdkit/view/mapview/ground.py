"""The HD ground of a map as D2R paints it (approximation, calibrated against game captures; docs/mapview.md "Ground"):

* which biome: a preset with a terrain entity (TerrainDefinitionComponent) is painted with the biome its terrain.model's
  material names (cathy3: act1_catacombs, while the preset's biomeFilename is act1_cathedral); without one the engine's
  ground plane under every floor cell is painted with the preset's biomeFilename;
* per cell: the base layer (0) of the cell's biome, which is the preset's `perTileBiomeOverrides` entry for that cell
  (tileX, tileY) or the ground biome; cells without a floor tile get no ground (black, as in game);
* terrain stamps (TerrainStampDefinitionComponent): the stamp texture's R / G / B channels x stomp / stompG / stompB paint
  layers layerIndexR / G / B of biome `biomeName` over a footprint of scale.x x scale.z world units centred on the
  transform's position, turned by its yaw;
* the layers blend per texel by weight x (layer height + 0.5)^SHARP, the height being the layer albedo's alpha
  (D2R's height blend, shape approximated); a tile edge is softened over EDGE_BLUR texels;
* terrain decals (TerrainDecalDefinitionComponent) and floor decals (DecalDefinitionComponent whose projection axis is
  near vertical): their albedo / normal / ORM on a flat quad just above the ground (scale.x x scale.z), alpha-blended by
  the albedo alpha x stomp (or weight). Decals on walls are not drawn (listed in the notes).

Not reproduced: the tile masks' path masks (data/hd/env/tilemasks: town and outdoor path edges), grass and clutter
(GrassDensity / Clutter of a layer), the noise textures, parallax.
"""
from __future__ import annotations

import json
import math

import numpy as np

RES = 16              # weight-map texels per cell (10 world units)
MAX_LAYERS = 16
LAYER_REPEAT = 20.0   # world units per terrain layer texture repeat (calibrated, see docs/mapview.md)
SHARP = 4.0
EDGE_BLUR = 3         # texels
NONE = 4294967295
LIFT = 0.03           # decals above the ground (world units)


def _comps(ent):
    return {c["type"]: c for c in ent.get("components", [])}


def _read_json(fs, logical):
    return json.loads(fs.read(logical).decode("utf-8-sig"))


def _biome_path(b: str) -> str:
    b = b.replace("\\", "/")
    if b.endswith(".json"):
        return b if b.startswith("data/") else "data/" + b
    return "data/hd/env/biome/%s.json" % b


def terrain_biome(fs, model_logical: str) -> str | None:
    """The biome a terrain.model's material names (its Texture FromFileName ending in .json)."""
    from .. import gr2, scene as S
    try:
        _g, t = gr2.load_tree(fs.read(S._model_path(fs, model_logical, 0)))
    except (OSError, FileNotFoundError, KeyError, ValueError):
        return None
    for tex in t["Textures"] or []:
        f = (tex.get("FromFileName") or "").replace("\\", "/")
        if f.lower().endswith(".json"):
            return _biome_path(f)
    return None


def floor_cells(ds) -> np.ndarray:
    """(H, W) bool: cells with a drawn floor tile."""
    out = np.zeros((ds.height, ds.width), bool)
    for f in ds.floors():
        f = f.astype(np.int64)
        out |= ((f & 0xFF) != 0) & (((f >> 31) & 1) == 0)
    return out


def _yaw(q) -> float:
    from ..preset import quat_matrix
    R = quat_matrix(q or {})
    return math.atan2(R[0, 2], R[0, 0])


class Ground:
    """Weights and layers of one map's ground. `slots`: [(biome logical, layer index)]."""

    def __init__(self, fs, preset_json: dict, ds, preset_biome: str | None, terrain_model: str | None):
        self.fs, self.ds = fs, ds
        self.notes = []
        self.slots = []
        self.biomes = {}
        gb = terrain_biome(fs, terrain_model) if terrain_model else None
        self.ground_biome = gb or (_biome_path(preset_biome) if preset_biome else None)
        self.has_terrain = terrain_model is not None
        H, W = ds.height, ds.width
        self.W = np.zeros((H * RES, W * RES, MAX_LAYERS), np.float32)
        floor = floor_cells(ds)
        over = {(int(o["tileX"]), int(o["tileY"])): _biome_path(o["biomeFilename"])
                for o in preset_json.get("perTileBiomeOverrides") or () if o.get("biomeFilename")}
        for y in range(H):
            for x in range(W):
                if not floor[y, x]:
                    continue
                b = over.get((x, y), self.ground_biome)
                s = self.slot(b, 0)
                if s is not None:
                    self.W[y * RES:(y + 1) * RES, x * RES:(x + 1) * RES, s] = 1.0
        if EDGE_BLUR:
            self.W = _blur(self.W, EDGE_BLUR)
        self.mask = self.W.sum(-1) > 0.0
        self.stamps = 0
        for ent in preset_json.get("entities", []):
            c = _comps(ent)
            st = c.get("TerrainStampDefinitionComponent")
            if st:
                self.stamp(st, c.get("TransformDefinitionComponent") or {})

    def biome(self, b: str) -> dict | None:
        if b not in self.biomes:
            try:
                self.biomes[b] = _read_json(self.fs, b)
            except (OSError, FileNotFoundError, ValueError):
                self.biomes[b] = None
                self.notes.append("biome %s not found" % b)
        return self.biomes[b]

    def layer(self, b: str, i: int) -> dict | None:
        d = self.biome(b)
        if not d:
            return None
        for q in ("terrainDataHigh", "terrainDataUltra", "terrainDataMed"):
            L = (d.get(q) or {}).get("terrainLayers") or []
            if L:
                return L[i] if 0 <= i < len(L) else None
        return None

    def slot(self, b: str | None, i: int) -> int | None:
        if b is None or self.layer(b, i) is None:
            return None
        k = (b, int(i))
        if k not in self.slots:
            if len(self.slots) >= MAX_LAYERS:
                self.notes.append("more than %d ground layers: %s layer %d dropped" % (MAX_LAYERS, b, i))
                return None
            self.slots.append(k)
        return self.slots.index(k)

    def stamp(self, st: dict, td: dict):
        from .. import scene as S
        try:
            tex = S.read_texture(self.fs, st["mask"], srgb=False).mips[0].astype(np.float32) / 255.0
        except (OSError, FileNotFoundError, KeyError, ValueError):
            self.notes.append("stamp mask %s not read" % st.get("mask"))
            return
        b = _biome_path(st.get("biomeName") or "")
        chans = []
        for ch, li, sk in ((0, "layerIndexR", "stomp"), (1, "layerIndexG", "stompG"), (2, "layerIndexB", "stompB")):
            L = int(st.get(li, NONE))
            if L == NONE:
                continue
            s = self.slot(b, L)
            if s is not None:
                chans.append((ch, s, float(st.get(sk, 1.0))))
        if not chans:
            return
        p, sc = td.get("position") or {}, td.get("scale") or {}
        cx, cz = float(p.get("x", 0)), float(p.get("z", 0))
        sx, sz = float(sc.get("x", 1)), float(sc.get("z", 1))
        a = _yaw(td.get("orientation"))
        ca, sa = math.cos(a), math.sin(a)
        r = 0.5 * math.hypot(sx, sz)
        H, W = self.W.shape[:2]
        x0, x1 = max(0, int((cx - r) / 10 * RES)), min(W, int((cx + r) / 10 * RES) + 1)
        z0, z1 = max(0, int((cz - r) / 10 * RES)), min(H, int((cz + r) / 10 * RES) + 1)
        if x0 >= x1 or z0 >= z1:
            return
        gx, gz = np.meshgrid((np.arange(x0, x1) + 0.5) * 10.0 / RES - cx, (np.arange(z0, z1) + 0.5) * 10.0 / RES - cz)
        lx = ca * gx - sa * gz            # world offset -> the stamp's local axes (inverse yaw)
        lz = sa * gx + ca * gz
        u, v = lx / sx + 0.5, lz / sz + 0.5
        inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
        th, tw = tex.shape[:2]
        iu = np.clip((u * tw).astype(int), 0, tw - 1)
        iv = np.clip((v * th).astype(int), 0, th - 1)
        blk = self.W[z0:z1, x0:x1]
        gm = self.mask[z0:z1, x0:x1] & inside
        for ch, s, stomp in chans:
            m = tex[iv, iu, ch] * stomp * gm
            blk *= (1.0 - m)[..., None]
            blk[..., s] += m
        self.stamps += 1

    # ---- GPU -----------------------------------------------------------------------------------------------------------
    def arrays(self, R) -> dict:
        from .. import scene as S
        alb, nrm, orm = [], [], []
        for b, i in self.slots:
            L = self.layer(b, i)
            for lst, key, srgb in ((alb, "Albedo", True), (nrm, "Normal", False), (orm, "ORM", False)):
                mips = None
                try:
                    mips = S.read_texture(self.fs, L[key], srgb=srgb).mips
                except (OSError, FileNotFoundError, KeyError, ValueError, TypeError):
                    self.notes.append("%s %s of %s layer %d not read" % (key, L.get(key), b, i))
                lst.append(_fit(mips, key))
        W8 = np.zeros((4, self.W.shape[0], self.W.shape[1], 4), np.uint8)
        tot = np.maximum(self.W.sum(-1, keepdims=True), 1e-6)
        Wn = np.where(self.mask[..., None], self.W / tot, 0.0)
        for q in range(4):
            W8[q] = np.round(Wn[..., 4 * q:4 * q + 4] * 255.0).astype(np.uint8)
        return {"alb": R.texture_array(alb, srgb=True), "nrm": R.texture_array(nrm), "orm": R.texture_array(orm),
                "wts": R.texture_array([[W8[q]] for q in range(4)])}

    def p3p4(self):
        return ((0.0, 0.0, self.ds.width * 10.0, self.ds.height * 10.0), (LAYER_REPEAT, float(max(1, len(self.slots))), SHARP))

    def info(self) -> dict:
        return {"ground_biome": self.ground_biome, "terrain_model": self.has_terrain,
                "layers": ["%s:%d" % (b.split("/")[-1][:-5], i) for b, i in self.slots], "stamps": self.stamps,
                "res_per_cell": RES, "layer_repeat_units": LAYER_REPEAT, "notes": self.notes[:20]}


DEFAULT_PX = {"Albedo": (40, 40, 40, 128), "Normal": (255, 128, 0, 128), "ORM": (255, 230, 0, 30)}


def _fit(mips, key, size=1024):
    """A mip chain of size x size (the arrays need equal layers): resized when another size, a flat default when none."""
    from PIL import Image
    if not mips:
        base = np.full((size, size, 4), DEFAULT_PX[key], np.uint8)
    elif mips[0].shape[:2] == (size, size):
        return [m[..., :4] if m.shape[-1] >= 4 else np.dstack([m, np.full(m.shape[:2], 255, np.uint8)]) for m in mips]
    else:
        m0 = mips[0]
        if m0.shape[-1] < 4:
            m0 = np.dstack([m0] + [np.full(m0.shape[:2], 255, np.uint8)] * (4 - m0.shape[-1]))
        base = np.asarray(Image.fromarray(np.ascontiguousarray(m0[..., :4])).resize((size, size), Image.BILINEAR))
    out = [base]
    while out[-1].shape[0] > 1:
        out.append(np.asarray(Image.fromarray(out[-1]).resize((out[-1].shape[1] // 2, out[-1].shape[0] // 2), Image.BOX)))
    return out


def _blur(W, r):
    return _box(_box(W, r, 0), r, 1)


def _box(a, r, ax):
    c = np.cumsum(np.pad(a, [(r + 1, r) if i == ax else (0, 0) for i in range(a.ndim)], mode="edge"), axis=ax)
    n = a.shape[ax]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=ax)
    lo = np.take(c, np.arange(0, n), axis=ax)
    return (hi - lo) / (2 * r + 1)


# ---- decals ---------------------------------------------------------------------------------------------------------------
def decal_units(fs, preset_json: dict, fr=None, margin: float = 30.0):
    """[(scene.Unit, 4x4)] for terrain decals and floor decals of a preset (flat quads), and notes."""
    from .. import gr2, scene as S
    from ..preset import trs
    out, notes, cache = [], {"wall decals skipped": 0, "decal textures missing": 0}, {}
    lim = None
    if fr is not None:
        lim = ((fr.x0 * 10 - margin, (fr.x1 + 1) * 10 + margin), (fr.y0 * 10 - margin, (fr.y1 + 1) * 10 + margin))
    quad_pos = np.array([[-0.5, 0, -0.5], [0.5, 0, -0.5], [0.5, 0, 0.5], [-0.5, 0, 0.5]], float)
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
    tris = np.array([[0, 1, 2], [0, 2, 3]])
    for ent in preset_json.get("entities", []):
        c = _comps(ent)
        td = c.get("TransformDefinitionComponent")
        dc = c.get("TerrainDecalDefinitionComponent")
        dd = c.get("DecalDefinitionComponent")
        if not td or not (dc or dd):
            continue
        M = trs(td)
        x, z = M[0, 3], M[2, 3]
        if lim and not (lim[0][0] <= x <= lim[0][1] and lim[1][0] <= z <= lim[1][1]):
            continue
        if dc:
            maps = {"AlbedoTexture": dc.get("albedo"), "NormalTexture": dc.get("normal"), "ORMTexture": dc.get("orm")}
            w = float(dc.get("stomp", 1.0))
        else:
            up = M[:3, 1] / max(np.linalg.norm(M[:3, 1]), 1e-9)
            if abs(up[1]) < 0.7:
                notes["wall decals skipped"] += 1
                continue
            maps = {"AlbedoTexture": dd.get("diffuseMap"), "NormalTexture": dd.get("normalMap"), "ORMTexture": dd.get("ormMap")}
            w = float(dd.get("weight", 1.0))
        sx, sz = float(np.linalg.norm(M[:3, 0])), float(np.linalg.norm(M[:3, 2]))
        yaw = _yaw(td.get("orientation"))
        key = tuple(maps.values())
        if key not in cache:
            tx = {}
            for u_, lg in maps.items():
                if lg and fs.exists(lg):
                    try:
                        tx[u_] = S.read_texture(fs, lg, srgb=(u_ == "AlbedoTexture"))
                    except (KeyError, ValueError):
                        pass
            cache[key] = tx
        tx = cache[key]
        if "AlbedoTexture" not in tx:
            notes["decal textures missing"] += 1
            continue
        ca, sa = math.cos(yaw), math.sin(yaw)
        Rm = np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]])
        P = (quad_pos * [sx, 0, sz]) @ Rm.T + [x, LIFT, z]
        nrm = np.tile([0.0, 1.0, 0.0], (4, 1))
        tan = np.tile(np.append(Rm[:, 0], 1.0), (4, 1))
        mesh = gr2.Mesh(ent.get("name", "decal"), P, nrm, tan, uv, tris, maps, [], None, None, {"blend": max(w, 1e-3)})
        out.append(S.Unit(ent.get("name", "decal"), [S.Part(ent.get("name", "decal"), "decal", [mesh], None, tx)]))
    return out, {k: v for k, v in notes.items() if v}
