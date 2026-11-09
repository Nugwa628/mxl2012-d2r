#!/usr/bin/env python
"""Prototype: Median's own .dt1 wall tiles drawn in HD, as cut-out models (lane hdwallart; findings in mxl2012-runs/hdwallart/FINDINGS.md).

Each wall tile a map uses becomes one small D2R model: a vertical "curtain" over the back edges of its cell, textured with
the tile's sprite through D2R's AlphaThresholdMaterial. A cell's sprite lies over the diamond's two upper edges, so the
curtain is one or two flat pieces: x < 80 runs along the cell's X = 0 edge, x > 80 along its Z = 0 edge. UVs are the sprite's
own pixels, so the wall shows the classic picture from the game's camera.

  py -3 -I tools/walls_sprite.py build expansion/dystopic/desertpeak.ds1 OUT [--scale 2] [--method lanczos|nearest|esrgan]
                                 [--normals sprite|flat] [--esrgan EXE] [--base SCENE.json] [--light floor|wall] [--shadow N] [--relief UNITS]
                                 [--export DIR] [--albedo IMAGE]

OUT is a mod `data` folder (hd/env/..., hd/model_lod_desc.bin). Needs D2R's model_lod_desc.bin and the donor's LOD files, read
like tools/walls_hd.py d2r_bytes (extraction, shared cache, or MXL_SLOT's CASC). Not part of tools/build.py.
"""
import argparse
import copy
import json
import math
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

TILE = 10.0                # world units per cell
KINK = 80                  # the sprite column of the diamond's top corner
PX_PER_UNIT = 8.0          # classic pixels per world unit along a cell edge, in screen x
PX_PER_HEIGHT = 9.24       # classic pixels per world unit of height: 160 px = 14.14 units across, D2R's camera shows height at 0.816
WALL_Y = 80                # a wall tile's y = 0 lies this far above the diamond frame's y = 0
ORIENTATIONS = set(range(1, 10)) | {12, 14}   # walls, corners, ends, wall decor, tree tiles (10, 11: specials, 13: shadows)
LAYER_GAP = 0.03           # world units between the wall layers of a cell, against z-fighting
DONOR = "data/hd/env/model/global/prop/objects/wood/wood_burning06.model"   # one mesh, one AlphaThresholdMaterial
LODS = 5
DONOR_LOD0_VERTS, DONOR_LOD0_INDICES = 739, 3276
PAD = 4                    # atlas pixels around a tile (colour bleeds into them, for mips)
ATLAS_WIDTH = 2048
OUT_MODEL = "data/hd/env/model/mxl/wallsprite/%s/%d_%d_%d.model"
OUT_TEXTURE = "data/hd/env/texture/mxl/wallsprite/%s_%s.texture"


def foot(x: float) -> float:
    """The y of the diamond's upper edge at sprite column x (diamond frame: top corner at (80, 0))."""
    return abs(x - KINK) / 2


def edge_point(x: float):
    """(X, Z) in world units within the cell of the point on the diamond's upper edges at sprite column x."""
    return (0.0, (KINK - x) / PX_PER_UNIT) if x <= KINK else ((x - KINK) / PX_PER_UNIT, 0.0)


def rect_of(pixels):
    """(x0, y0, x1, y1) of a tile's pixels (x1, y1 exclusive), y in the tile's own frame."""
    xs, ys = [p[0] for p in pixels], [p[1] for p in pixels]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def columns(x0: int, x1: int, bottom: float) -> list:
    """The sprite columns where the curtain needs vertices: its ends, the kink and where the foot crosses the sprite's bottom."""
    cuts = {x0, x1}
    for x in (KINK, KINK - 2 * bottom, KINK + 2 * bottom):
        if x0 < x < x1:
            cuts.add(x)
    return sorted(cuts)


def tile_mesh(rect, uv_rect, light: str = "floor"):
    """(vertices, triangles) of the curtain of a tile: vertices are (position, normal, tangent + sign, uv). rect: rect_of();
    uv_rect: (u0, v0, u1, v1) of the sprite in the atlas. Triangles wound as D2R's terrain: (b - a) x (c - a) along the wall's
    normal. light: 'floor' shades the wall with an upward normal, so it gets the light the floor gets (the sprite has its
    shading painted in; true wall normals leave every wall that faces away from the map's key light black), 'wall' with
    the wall's own normal."""
    x0, y0, x1, y1 = rect
    top, bottom = y0 + WALL_Y, y1 + WALL_Y
    u0, v0, u1, v1 = uv_rect

    def vertex(x, y, n, t):
        ex, ez = edge_point(x)
        pos = (ex, (foot(x) - y) / PX_PER_HEIGHT, ez)
        return (pos, n, t, (u0 + (u1 - u0) * (x - x0) / (x1 - x0), v0 + (v1 - v0) * (y - top) / (bottom - top)))

    verts, tris = [], []
    xs = columns(x0, x1, bottom)
    for a, b in zip(xs, xs[1:]):
        left = (a + b) / 2 < KINK
        wall = (1.0, 0.0, 0.0) if left else (0.0, 0.0, 1.0)
        if light == "floor":
            n, t = (0.0, 1.0, 0.0), (0.7071, 0.0, -0.7071, -1.0)     # tangent along the screen's right, as the sprite's U
        else:
            n, t = wall, (0.0, 0.0, -1.0, -1.0) if left else (1.0, 0.0, 0.0, -1.0)
        base_a, base_b = min(bottom, foot(a)), min(bottom, foot(b))
        if base_a <= top and base_b <= top:
            continue          # all of this piece would be under the floor
        i = len(verts)
        verts += [vertex(a, min(top, base_a), n, t), vertex(b, min(top, base_b), n, t), vertex(b, base_b, n, t), vertex(a, base_a, n, t)]
        tris += wound(verts, wall, i, [(0, 1, 2), (0, 2, 3)])
    return verts, tris


def relief_mesh(rect, uv_rect, height, depth: float, step: int = 16, light: str = "floor"):
    """tile_mesh with real depth: a grid over each flat piece, every vertex pushed out of the wall by depth * height(x, y)
    (height: sprite column, row in the tile's own frame -> 0..1). The UV stays the vertex's own sprite pixel moved along the view
    line, so the game's camera shows the same picture and only depth and light change."""
    x0, y0, x1, y1 = rect
    top, bottom = y0 + WALL_Y, y1 + WALL_Y
    u0, v0, u1, v1 = uv_rect
    verts, tris = [], []
    xs = columns(x0, x1, bottom)
    for a, b in zip(xs, xs[1:]):
        wall = (1.0, 0.0, 0.0) if (a + b) / 2 < KINK else (0.0, 0.0, 1.0)
        n, t = (0.0, 1.0, 0.0), (0.7071, 0.0, -0.7071, -1.0)
        if light != "floor":
            n, t = wall, (0.0, 0.0, -1.0, -1.0) if wall[0] else (1.0, 0.0, 0.0, -1.0)
        cols = max(1, int((b - a) // step))
        rows = max(1, int((bottom - top) // step))
        base = len(verts)
        for j in range(rows + 1):
            for i in range(cols + 1):
                x = a + (b - a) * i / cols
                low = min(bottom, foot(x))
                y = min(top, low) + (low - min(top, low)) * j / rows
                ex, ez = edge_point(x)
                d = depth * height(x, y - WALL_Y)
                pos = (ex + d, (foot(x) - y) / PX_PER_HEIGHT + d, ez + d)   # along the view line (1, 1, 1): the same screen point
                verts.append((pos, n, t, (u0 + (u1 - u0) * (x - x0) / (x1 - x0), v0 + (v1 - v0) * (y - top) / (bottom - top))))
        for j in range(rows):
            for i in range(cols):
                q = base + j * (cols + 1) + i
                faces = [(0, 1, cols + 2), (0, cols + 2, cols + 1)]
                tris += wound(verts, wall, q, faces)
    return verts, tris


def wound(verts, n, base, faces):
    """The faces (offsets from base) as index triples, each turned so that (b - a) x (c - a) points along the normal n."""
    out = []
    for f in faces:
        a, b, c = (np.array(verts[base + k][0]) for k in f)
        cross = np.cross(b - a, c - a)
        out.append((base + f[0], base + f[1], base + f[2]) if np.dot(cross, n) >= 0 else (base + f[0], base + f[2], base + f[1]))
    return out


def _half(f: float) -> int:
    return struct.unpack("<H", struct.pack("<e", f))[0]


def sprite_model(donor: bytes, verts, tris, textures: dict) -> tuple:
    """A .model: the donor's mesh replaced by (verts, tris), padded to the donor's counts (D2R's LOD index stores them), with
    identity bone and placement and the textures {'alb' | 'nrm' | 'orm': game path}. -> (bytes, bbMin, bbMax)."""
    import d2r_model as dm
    gr2 = dm.Gr2File.read(donor)
    tree = dm.parse_tree(gr2)
    mesh = tree["Meshes"][0]
    vertices, topo = mesh["PrimaryVertexData"]["Vertices"], mesh["PrimaryTopology"]
    nv, ni = len(vertices.obj), len(topo["Indices16"])
    if len(verts) > nv or len(tris) * 3 > ni:
        raise ValueError("sprite_model: %d vertices / %d indices do not fit the donor's %d / %d" % (len(verts), len(tris) * 3, nv, ni))
    pts = [v[0] for v in verts]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    scale = max(1.0, max(abs(c) for p in pts for c in p))
    w = int(round(math.log2(scale) / 13 * 32767))
    vtd = vertices.obj[0].td

    def vertex(v):
        (p, n, t, uv) = v
        return dm.Obj(vtd, {"Position": [int(round(c / scale * 32767)) for c in p] + [w],
                            "Normal": [int(round(c * 127)) for c in n] + [0],
                            "Tangent": [int(round(c * 127)) for c in t],
                            "TextureCoordinates0": [_half(uv[0]), _half(uv[1])]})
    out = [vertex(v) for v in verts]
    vertices.obj = out + [out[0]] * (nv - len(out))
    itd = topo["Indices16"][0].td
    index = [i for t in tris for i in t]
    index += [0] * (ni - len(index))
    topo["Indices16"] = [dm.Obj(itd, {"Int16": i}) for i in index]
    topo["Groups"] = topo["Groups"][:1]
    topo["Groups"][0]["TriFirst"], topo["Groups"][0]["TriCount"] = 0, ni // 3
    ed = mesh["ExtendedData"].obj
    ed["bbMin"], ed["bbMax"], ed["VertexScale"] = lo, hi, float(scale)
    for bind in mesh["BoneBindings"]:
        bind["OBBMin"], bind["OBBMax"] = lo, hi
    identity = dm.Transform(0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    for bone in tree["Skeletons"][0]["Bones"]:
        bone["Transform"] = identity
        bone["InverseWorldTransform"] = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    for model in tree["Models"]:
        model["InitialPlacement"] = identity
    for mat in tree["Materials"]:
        tex = mat.get("Texture")
        if tex is not None:
            _retexture(tex, textures)
        ed = mat["ExtendedData"].obj if mat.get("ExtendedData") is not None else None
        if ed is not None and ed.get("AlphaThreshold") is not None:
            ed["AlphaThreshold"], ed["IsDoubleSided"] = 0.5, 1
    for tex in tree["Textures"]:
        _retexture(tex, textures)
    data = dm.Writer(gr2).build(tree).write()
    dm.parse_tree(dm.Gr2File.read(data))     # well formed
    return data, lo, hi


def _retexture(tex, textures: dict):
    name = tex["FromFileName"].lower()
    for kind, path in textures.items():
        if name.endswith("_%s.texture" % kind):
            tex["FromFileName"] = path


# ---- atlas -------------------------------------------------------------------------------------------------------------------
def pack(sizes: dict, width: int = ATLAS_WIDTH, pad: int = PAD):
    """Shelf packing, tallest first. sizes: {key: (w, h)}. -> ({key: (x, y)}, height used)."""
    x = y = shelf = 0
    places = {}
    for key in sorted(sizes, key=lambda k: (-sizes[k][1], -sizes[k][0], k)):
        w, h = sizes[key][0] + 2 * pad, sizes[key][1] + 2 * pad
        if x + w > width:
            x, y, shelf = 0, y + shelf, 0
        places[key] = (x + pad, y + pad)
        x, shelf = x + w, max(shelf, h)
    return places, y + shelf


def bleed(rgba: np.ndarray, steps: int = PAD) -> np.ndarray:
    """Colour of opaque pixels spread into the transparent ones around them, so mips and upscaling keep clean edges."""
    out = rgba.copy()
    have = rgba[..., 3] > 0
    for _ in range(steps):
        grow = np.zeros_like(have)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(have, (dy, dx), (0, 1))
            new = src & ~have & ~grow
            out[new, :3] = np.roll(out, (dy, dx), (0, 1))[new, :3]
            grow |= new
        have |= grow
    return out


def upscale(rgba: np.ndarray, scale: int, method: str, esrgan=None) -> np.ndarray:
    """(h, w, 4) uint8 upscaled by `scale`: colour by `method`, alpha always by Lanczos (the material thresholds it)."""
    from PIL import Image
    h, w = rgba.shape[:2]
    size = (w * scale, h * scale)
    if scale == 1:
        return rgba
    alpha = np.asarray(Image.fromarray(rgba[..., 3], "L").resize(size, Image.LANCZOS))
    rgb = Image.fromarray(rgba[..., :3], "RGB")
    if method == "esrgan":
        with tempfile.TemporaryDirectory(dir=str(Path(esrgan["work"]))) as tmp:
            src, dst = Path(tmp) / "in.png", Path(tmp) / "out.png"
            rgb.save(src)
            subprocess.run([esrgan["exe"], "-i", str(src), "-o", str(dst), "-n", "realesrgan-x4plus", "-s", "4"], check=True, cwd=str(Path(esrgan["exe"]).parent),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            big = Image.open(dst).convert("RGB").resize(size, Image.LANCZOS)
            big.load()
    else:
        big = rgb.resize(size, Image.NEAREST if method == "nearest" else Image.LANCZOS)
    return np.dstack([np.asarray(big), alpha])


def normal_map(rgb: np.ndarray, strength: float = 2.5) -> np.ndarray:
    """D2R's normal map layout (255, y, 0, x; 128 = flat) from the sprite's brightness, read as a height field."""
    luma = (rgb[..., 0] * 0.3 + rgb[..., 1] * 0.59 + rgb[..., 2] * 0.11) / 255.0
    dx = (np.roll(luma, -1, 1) - np.roll(luma, 1, 1)) * strength
    dy = (np.roll(luma, -1, 0) - np.roll(luma, 1, 0)) * strength
    length = np.sqrt(dx * dx + dy * dy + 1)
    x, y = np.clip((-dx / length + 1) * 127.5, 0, 255), np.clip((dy / length + 1) * 127.5, 0, 255)
    out = np.zeros(rgb.shape[:2] + (4,), np.uint8)
    out[..., 0], out[..., 1], out[..., 3] = 255, y, x
    return out


# ---- map ----------------------------------------------------------------------------------------------------------------------
def map_tiles(inp, entry):
    """{key: palette pixels [(x, y, index)]} of the wall tiles the map's files hold (the first file with a key wins)."""
    import dt1_pixels
    out = {}
    for f in entry["dt1_files"]:
        store = inp.mod_tiles if f in inp.mod_tiles else inp.d2r_tiles if f in inp.d2r_tiles else None
        if store is None:
            continue
        for k, px in dt1_pixels.tiles(store.read(f)).items():
            if px:
                out.setdefault(k, px)
    return out


def map_placements(ds, tiles: dict) -> list:
    """[(x, y, layer, key)] of every wall layer tile the prototype draws, in layer order."""
    import ds1_remap
    out = []
    for n, (lay, ori) in enumerate(ds.wall_layers()):
        for i, (c, o) in enumerate(zip(lay, ori)):
            o &= 0xFF
            if c == 0 or o not in ORIENTATIONS:
                continue
            s, q = ds1_remap.cell_key(c)
            if (o, s, q) in tiles:
                out.append((i % ds.width, i // ds.width, n, (o, s, q)))
    return out


def entity(model: str, x: int, y: int, n: int, serial: int, shadow: int = 0) -> dict:
    """A cell's wall piece; wall layer n sits LAYER_GAP nearer the camera per layer (the camera looks along (1, 1, 1))."""
    name = "mxs_%d_%d_%d" % (x, y, n)
    gap = n * LAYER_GAP
    return {"type": "Entity", "name": name, "id": 0x6E780000 + serial, "components": [
        {"type": "TransformDefinitionComponent", "name": name + "_t", "position": {"x": x * TILE + gap, "y": gap, "z": y * TILE + gap},
         "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}, "scale": {"x": 1.0, "y": 1.0, "z": 1.0}, "inheritOnlyPosition": False},
        {"type": "ModelDefinitionComponent", "name": name + "_m", "filename": model, "visibleLayers": 1, "lightMask": 19,
         "shadowMask": shadow, "ghostShadows": False, "floorModel": False, "terrainBlendEnableYUpBlend": False, "terrainBlendMode": 0},
        {"type": "WallTransparencyComponent", "name": name + "_w", "drawOrder": 0, "wallTileLocalCoord": {"x": -1, "y": -1}}]}


def build(map_name: str, out: Path, scale=2, method="lanczos", normals="sprite", esrgan=None, base=None, inp=None, read=None,
          light="floor", shadow=0, relief=0.0, export=None, albedo=None):
    """Writes the map's scene, models, textures and LOD index under `out`. -> stats."""
    import d2r_texture
    import ds1_remap
    import maps_hd
    import map_tint
    import walls_hd
    from PIL import Image
    read = read or walls_hd.d2r_bytes
    inp = inp or maps_hd.Inputs.load()
    entry = next(e for e in maps_hd.plan(inp)[0] if e["map"].lower() == map_name.lower())
    ds = ds1_remap.Ds1(inp.mod_tiles.read(entry["map"]))
    tiles = map_tiles(inp, entry)
    placements = map_placements(ds, tiles)
    used = sorted({p[3] for p in placements})
    palette = np.zeros((256, 4), np.uint8)
    palette[:, :3] = map_tint.act_palette(entry["level_acts"][0])      # level_acts counts from 1
    palette[1:, 3] = 255
    rects = {k: rect_of(tiles[k]) for k in used}
    places, used_h = pack({k: (r[2] - r[0], r[3] - r[1]) for k, r in rects.items()})
    height = 1 << max(8, math.ceil(math.log2(used_h)))
    atlas = np.zeros((height, ATLAS_WIDTH), np.uint8)
    for k in used:
        (ax, ay), (x0, y0, _x1, _y1) = places[k], rects[k]
        for x, y, c in tiles[k]:
            atlas[ay + y - y0, ax + x - x0] = c
    rgba = bleed(palette[atlas])
    if export:
        Path(export).mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgba, "RGBA").save(Path(export) / (Path(entry["map"]).stem.lower() + "_atlas.png"))
        (Path(export) / (Path(entry["map"]).stem.lower() + "_atlas.json")).write_text(json.dumps(
            {"pixels_per_atlas_pixel": 1, "tiles": {"%d_%d_%d" % k: {"atlas_xy": places[k], "sprite_rect": rects[k]} for k in used}}, indent=0), encoding="utf-8")
    if albedo:     # a local render of the exported atlas, same layout: any integer multiple of its size; its alpha is kept if it has one
        art = Image.open(albedo).convert("RGBA")
        if art.width % rgba.shape[1] or art.width / rgba.shape[1] != art.height / rgba.shape[0]:
            raise SystemExit("walls_sprite: %s is %dx%d, not a multiple of the atlas's %dx%d" % (albedo, art.width, art.height, rgba.shape[1], rgba.shape[0]))
        scale, big = art.width // rgba.shape[1], np.array(art)
    else:
        big = upscale(rgba, scale, method, esrgan)
    stem = Path(entry["map"]).stem.lower()
    tex = {k: OUT_TEXTURE % (stem, k) for k in ("alb", "nrm", "orm")}
    for path in tex.values():
        (out / path[len("data/"):]).parent.mkdir(parents=True, exist_ok=True)
    mips = 6
    d2r_texture.write_bc3(out / tex["alb"][len("data/"):], big, mips)
    half = np.asarray(Image.fromarray(big[..., :3], "RGB").resize((big.shape[1] // 2, big.shape[0] // 2), Image.LANCZOS))
    flat = np.zeros(half.shape[:2] + (4,), np.uint8)
    flat[..., 0], flat[..., 1], flat[..., 3] = 255, 128, 128
    d2r_texture.write_bc3(out / tex["nrm"][len("data/"):], normal_map(half) if normals == "sprite" else flat, mips, linear=True)
    orm = np.zeros(half.shape[:2] + (4,), np.uint8)
    orm[..., 0], orm[..., 1], orm[..., 3] = 255, 217, 255
    d2r_texture.write_bc3(out / tex["orm"][len("data/"):], orm, mips, linear=True)
    donors = [read(DONOR[:-len(".model")] + "_lod%d.model" % n) for n in range(LODS)]
    if not all(donors):
        raise SystemExit("walls_sprite: the donor's LOD files are not at hand; run once with MXL_SLOT set")
    W, H = float(big.shape[1]), float(big.shape[0])
    lod, models = [], {}
    for k in used:
        (ax, ay), r = places[k], rects[k]
        w, h = r[2] - r[0], r[3] - r[1]
        uv = (ax * scale / W, ay * scale / H, (ax + w) * scale / W, (ay + h) * scale / H)
        path = OUT_MODEL % ((stem,) + k)
        verts, tris = tile_mesh(r, uv, light)
        detail = None
        if relief:
            # brightness as height, blurred over the grid; empty pixels count as the wall's plane
            lum = (rgba[ay:ay + h, ax:ax + w, :3] @ np.array([0.3, 0.59, 0.11])) / 255.0
            height_of = lambda sx, sy, a0=ax, b0=ay, x0=r[0], y0=r[1]: float(lum[min(h - 1, max(0, int(sy - y0))), min(w - 1, max(0, int(sx - x0)))])
            detail = relief_mesh(r, uv, height_of, relief, light=light)
        dest = out / path[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        for n, donor in enumerate(donors):
            fine = detail if detail and n == 0 and len(detail[0]) <= DONOR_LOD0_VERTS and len(detail[1]) * 3 <= DONOR_LOD0_INDICES else None
            data, lo, hi = sprite_model(donor, *(fine or (verts, tris)), tex)
            dest.with_name(dest.stem + "_lod%d.model" % n).write_bytes(data)
        lod.append((path, DONOR, (tuple(lo), tuple(hi))))
        models[k] = path
    ents = [entity(models[k], x, y, n, i, shadow) for i, (x, y, n, k) in enumerate(placements)]
    biome = entry["biome"]
    if base:
        biome = Path(json.loads(Path(base).read_text(encoding="utf-8"))["biomeFilename"]).stem
    scene = json.loads(maps_hd.scene_json(biome))
    scene["dependencies"]["models"] = [{"path": m} for m in sorted(models.values())]
    scene["entities"] = ents
    dest = out / "hd" / "env" / "preset" / (entry["map"][:-4].lower() + ".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(scene, separators=(",", ":")), encoding="utf-8")
    index = out / walls_hd.LOD_DESC[len("data/"):]
    walls_hd.write_lod_desc(out, lod, lambda rel: index.read_bytes() if index.exists() else read(rel))    # adds to an earlier map's
    return {"map": entry["map"], "tiles": len(used), "entities": len(ents), "atlas": list(big.shape[:2]), "biome": biome,
            "bytes": sum(f.stat().st_size for f in out.rglob("*") if f.is_file() and "model_lod_desc" not in f.name)}


# ---- build step: sprite walls where D2R has no full-height piece (lane hdscene2) --------------------------------------------
# walls_hd.build calls these for the wall cells walls_scene could not compose with a full-height D2R piece and whose per-tile
# pick stays under full height too (walls_hd.build_scene `sprites`): Kurast and docktown runs, where D2R's pieces for those tile
# sets are footings and trims. The cells get Median's own tiles as cut-out models, so they have legacy's height and look.
# The donor is the prototype's (DONOR, seen in game with the harness); the 25-vertex docktown thatch03 would give smaller files
# but D2R fails to create its index buffer for every model made from it ("Failed to create index buffer", then the device is
# removed; lane hdscene2, entering level 60). Kept small for the download otherwise: the atlas at the classic size (1x: the
# art has no more detail; the prototype's 2x Lanczos only blurred), and one flat normal map and one ORM map for every map.
SET_DONOR = DONOR
SET_MODEL = "data/hd/env/model/mxl/wallsprite/%s/wall_%d_%d_%d.model"    # 'wall' in the file name: walls_hd.tier 2, never capped as a prop
SET_ATLAS = "data/hd/env/texture/mxl/wallsprite/%s_alb.texture"
FLAT_NRM = "data/hd/env/texture/mxl/wallsprite/flat_nrm.texture"
FLAT_ORM = "data/hd/env/texture/mxl/wallsprite/flat_orm.texture"
SET_SCALE = 1
SET_MIPS = 5
FLAT_SIZE = 64
ID_BASE = 0x6E780000       # entity ids: above walls_hd's per-cell range (0x6D780000 + 0x80000)
FLOOR_ID_BASE = 0x6E7C0000  # floor sprites (STEP_TILES): above the wall sprites' range (4 per cell, a 96 x 96 map: 0x9000)
STEP_MODEL = "data/hd/env/model/mxl/wallsprite/%s/step_%d_%d_%d.model"   # 'step' in the file name: walls_hd.tier 3, kept first
FLOOR_LIFT = 0.04          # world units a floor sprite floats over the HD floor, against z-fighting

# Classic tiles HD draws flat or wrong, drawn from Median's own art on every cell that has them, not only in gaps (lane
# hdscene2). STEP_TILES: floor tiles whose steps are painted in (charismatic's stepped dais, sequences with the dark tread
# lines; HD paints every floor tile from the biome's terrain, so the steps came out as plain floor). ARCH_TILES: wall tiles
# D2R has a model for that does not look like them (dungrm6a's portcullis arches, style 0 sequences 17-21 and the barred
# corners: the per-tile pick gave broken ruin arches).
STEP_TILES = {"expansion/zakarum/charismatic.ds1": frozenset((0, 0, q) for q in (0, 1, 3, 4, 5, 9, 12, 13, 16, 17, 20, 22))}
ARCH_TILES = {"act3/jungle/dungrm6a.ds1": frozenset({(o, 0, q) for o in (1, 2) for q in range(17, 22)} | {(3, 0, 1), (3, 0, 2), (4, 0, 1)})}


# Colour match (lane walljoins): a map's sprite atlas is moved toward the albedo of the D2R wall pieces next to its sprite walls,
# per channel: mean and spread (standard deviation) of the opaque pixels, COLOUR_STRENGTH of the way, the spread's ratio kept
# within SPREAD_RANGE (match_colour). Median's art is darker and more saturated than D2R's albedo (its light is baked in).
COLOUR_STRENGTH = 0.75
SPREAD_RANGE = (0.5, 2.0)
ALBEDO_MIP = 128           # the albedo mip measured (pixels on its longer side)


def colour_stats(rgb: np.ndarray):
    """(mean, standard deviation, pixel count) per channel of (n, 3) pixels, as float arrays."""
    rgb = np.asarray(rgb, np.float64).reshape(-1, 3)
    return rgb.mean(0), rgb.std(0), len(rgb)


def pool_stats(parts):
    """One (mean, std, count) of several (mean, std, weight) parts, as if their pixels were put together by weight."""
    parts = [(np.asarray(m, np.float64), np.asarray(sd, np.float64), float(w)) for m, sd, w in parts if w > 0]
    if not parts:
        return None
    total = sum(w for _m, _s, w in parts)
    mean = sum(w * m for m, _s, w in parts) / total
    var = sum(w * (sd ** 2 + m ** 2) for m, sd, w in parts) / total - mean ** 2
    return mean, np.sqrt(np.maximum(var, 0.0)), total


def match_colour(rgba: np.ndarray, target, strength: float = COLOUR_STRENGTH) -> np.ndarray:
    """rgba (h, w, 4 uint8) with its opaque pixels' colour moved toward target (mean, std per channel): per channel
    c' = mean_t + (c - mean_s) * clamp(std_t / std_s, SPREAD_RANGE), then strength of the way from c to c'. Alpha and the
    transparent pixels stay. Deterministic (no randomness, numpy float64)."""
    out = rgba.copy()
    opaque = rgba[..., 3] > 0
    if target is None or not opaque.any():
        return out
    px = rgba[opaque][:, :3].astype(np.float64)
    ms, ss, _n = colour_stats(px)
    mt, st = np.asarray(target[0], np.float64), np.asarray(target[1], np.float64)
    ratio = np.clip(st / np.maximum(ss, 1e-6), SPREAD_RANGE[0], SPREAD_RANGE[1])
    moved = mt + (px - ms) * ratio
    out[opaque, :3] = np.clip(np.rint(px + strength * (moved - px)), 0, 255).astype(np.uint8)
    return out


def albedo_stats(model: str, read):
    """(mean, std, pixels) of a D2R model's albedo (its *_alb texture, mip ALBEDO_MIP, pixels with alpha over half), or None.
    read(rel) -> bytes or None (walls_hd.d2r_bytes)."""
    import d2r_model
    import d2r_texture
    data = read(model[:-len(".model")] + "_lod0.model") if model.endswith(".model") else None
    if not data:
        return None
    tree = d2r_model.parse_tree(d2r_model.Gr2File.read(data))
    for tex in tree.get("Textures") or ():
        name = tex["FromFileName"]
        if name.lower().endswith("_alb.texture"):
            t = read(name if name.startswith("data/") else "data/" + name)
            if not t:
                continue
            px = d2r_texture.small_mip(t, ALBEDO_MIP)
            px = px[px[..., 3] > 127][:, :3]
            return colour_stats(px) if len(px) else None
    return None


def model_path(stem: str, key) -> str:
    return (STEP_MODEL if key[0] == 0 else SET_MODEL) % ((stem,) + tuple(key))


def is_sprite(model: str) -> bool:
    return "/mxl/wallsprite/" in (model or "")


def key_of(model: str):
    """(o, s, q) of a sprite model path (model_path)."""
    return tuple(int(v) for v in model.rsplit("/", 1)[-1][:-len(".model")].split("_")[1:])


def flat_textures(out: Path) -> list:
    """The shared flat normal map and ORM map (written once, 64 x 64 with SET_MIPS levels like the atlases; 16 x 16 with one level
    lost the GPU device on entering a map that draws them, lane hdscene2). -> their files."""
    import d2r_texture
    nrm = np.zeros((FLAT_SIZE, FLAT_SIZE, 4), np.uint8)
    nrm[..., 0], nrm[..., 1], nrm[..., 3] = 255, 128, 128
    orm = np.zeros((FLAT_SIZE, FLAT_SIZE, 4), np.uint8)
    orm[..., 0], orm[..., 1], orm[..., 3] = 255, 217, 255
    files = []
    for path, px in ((FLAT_NRM, nrm), (FLAT_ORM, orm)):
        dest = Path(out) / path[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        d2r_texture.write_bc3(dest, px, SET_MIPS, linear=True)
        files.append(dest)
    return files


def floor_mesh(rect, uv_rect):
    """(vertices, triangles) of a floor tile laid flat over its cell (diamond corners: (80, 0) -> X 0 Z 0, (160, 40) -> X 10,
    (0, 40) -> Z 10, (80, 80) -> X 10 Z 10), lifted FLOOR_LIFT. Screen and floor are affine to each other, so the UVs
    interpolate exactly."""
    x0, y0, x1, y1 = rect
    u0, v0, u1, v1 = uv_rect
    n, t = (0.0, 1.0, 0.0), (0.7071, 0.0, -0.7071, -1.0)
    verts = []
    for px, py in ((KINK, 0), (2 * KINK, KINK / 2), (KINK, KINK), (0, KINK / 2)):
        dx, s = (px - KINK) / PX_PER_UNIT, py / (PX_PER_UNIT / 2)
        pos = ((s + dx) / 2, FLOOR_LIFT, (s - dx) / 2)
        verts.append((pos, n, t, (u0 + (u1 - u0) * (px - x0) / (x1 - x0), v0 + (v1 - v0) * (py - y0) / (y1 - y0))))
    return verts, wound(verts, (0.0, 1.0, 0.0), 0, [(0, 1, 2), (0, 2, 3)])


def mesh_of(key, rect, uv_rect):
    return floor_mesh(rect, uv_rect) if key[0] == 0 else tile_mesh(rect, uv_rect, "floor")


def floor_entity(model: str, x: int, y: int, n: int, serial: int) -> dict:
    """A cell's floor sprite (floor layer n), without wall transparency."""
    e = entity(model, x, y, 0, 0)
    name = "mxf_%d_%d_%d" % (x, y, n)
    e["name"], e["id"] = name, FLOOR_ID_BASE + serial
    e["components"] = e["components"][:2]
    for c, part in zip(e["components"], ("_t", "_m")):
        c["name"] = name + part
    return e


class MapSprites:
    """One map's wall tiles as sprite models. by_cell: {(x, y): [(layer, key)]}; entities(xy, serial) for the scene;
    write(out, keys, read) the atlas and models of the keys the scene kept. -> lod entries for walls_hd.write_lod_desc.
    steps: floor keys drawn on every cell that has them (STEP_TILES, by_floor, floor_entities()); arches: wall keys drawn
    on every cell (ARCH_TILES, forced(xy))."""

    def __init__(self, stem: str, ds, tiles: dict, palette, steps=(), arches=()):
        self.stem, self.tiles, self.palette = stem, tiles, palette
        self.arches = frozenset(k for k in arches if k in tiles)
        self.by_cell, self.by_floor = {}, {}
        shown = {k: bool(tile_mesh(rect_of(px), (0, 0, 1, 1))[0]) for k, px in tiles.items() if k[0]}   # all under the floor: nothing to draw
        for x, y, n, k in map_placements(ds, tiles):
            if shown[k]:
                self.by_cell.setdefault((x, y), []).append((n, k))
        steps = {k for k in steps if k in tiles}
        if steps:
            import ds1_remap
            for n, lay in enumerate(ds.floor_layers()):
                for i, c in enumerate(lay):
                    if c and (0,) + tuple(ds1_remap.cell_key(c)) in steps:
                        self.by_floor.setdefault((i % ds.width, i // ds.width), []).append((n, (0,) + tuple(ds1_remap.cell_key(c))))

    def forced(self, xy) -> bool:
        """Whether one of the cell's wall layers is an ARCH_TILES key (the cell draws sprites whatever D2R's pick)."""
        return any(k in self.arches for _n, k in self.by_cell.get(xy, ()))

    def floor_entities(self) -> list:
        out = []
        for xy in sorted(self.by_floor, key=lambda t: (t[1], t[0])):
            for n, k in self.by_floor[xy]:
                out.append(floor_entity(model_path(self.stem, k), xy[0], xy[1], n, len(out)))
        return out

    @classmethod
    def load(cls, inp, entry):
        import ds1_remap
        import map_tint
        ds = ds1_remap.Ds1(inp.mod_tiles.read(entry["map"]))
        palette = np.zeros((256, 4), np.uint8)
        palette[:, :3] = map_tint.act_palette(entry["level_acts"][0])      # level_acts counts from 1
        palette[1:, 3] = 255
        return cls(Path(entry["map"]).stem.lower(), ds, map_tiles(inp, entry), palette, STEP_TILES.get(entry["map"], ()),
                   ARCH_TILES.get(entry["map"], ()))

    def entities(self, xy, serial: int, only=None) -> list:
        """The cell's sprite entities (only: the (o, s, q) keys to draw, default all of the cell's wall layers)."""
        layers = [(n, k) for n, k in self.by_cell.get(xy, ()) if only is None or k in only]
        return [entity(model_path(self.stem, k), xy[0], xy[1], n, serial * 4 + i) for i, (n, k) in enumerate(layers)]

    def box(self, key):
        """((x0, y0, z0), (x1, y1, z1)) of a key's model, in the cell's frame."""
        pts = [v[0] for v in mesh_of(key, rect_of(self.tiles[key]), (0, 0, 1, 1))[0]]
        return tuple(min(p[i] for p in pts) for i in range(3)), tuple(max(p[i] for p in pts) for i in range(3))

    def write(self, out: Path, keys, read, colour=None) -> tuple:
        """Atlas (BC3, SET_SCALE) and one model per key under out (a mod `data` folder); colour: (mean, std) per channel the
        atlas is moved toward (match_colour), None keeps Median's colours. -> (lod entries, files written)."""
        keys = sorted(set(keys))
        if not keys:
            return [], []
        rects = {k: rect_of(self.tiles[k]) for k in keys}
        places, used_h = pack({k: (r[2] - r[0], r[3] - r[1]) for k, r in rects.items()})
        height = 1 << max(4, math.ceil(math.log2(used_h)))
        atlas = np.zeros((height, ATLAS_WIDTH), np.uint8)
        for k in keys:
            (ax, ay), (x0, y0, _x1, _y1) = places[k], rects[k]
            for x, y, c in self.tiles[k]:
                atlas[ay + y - y0, ax + x - x0] = c
        rgba = upscale(bleed(match_colour(self.palette[atlas], colour)), SET_SCALE, "lanczos")
        import d2r_texture
        alb = SET_ATLAS % self.stem
        dest = Path(out) / alb[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        d2r_texture.write_bc3(dest, rgba, SET_MIPS)
        files = [dest]
        donors = [read(SET_DONOR[:-len(".model")] + "_lod%d.model" % n) for n in range(LODS)]
        if not all(donors):
            raise SystemExit("walls_sprite: the donor's LOD files are not at hand; run once with MXL_SLOT set")
        tex = {"alb": alb, "nrm": FLAT_NRM, "orm": FLAT_ORM}
        H, W = float(rgba.shape[0]), float(rgba.shape[1])
        lod = []
        for k in keys:
            (ax, ay), r = places[k], rects[k]
            uv = (ax * SET_SCALE / W, ay * SET_SCALE / H, (ax + r[2] - r[0]) * SET_SCALE / W, (ay + r[3] - r[1]) * SET_SCALE / H)
            path = model_path(self.stem, k)
            verts, tris = mesh_of(k, r, uv)
            dest = Path(out) / path[len("data/"):]
            dest.parent.mkdir(parents=True, exist_ok=True)
            for n, donor in enumerate(donors):
                data, lo, hi = sprite_model(donor, verts, tris, tex)
                f = dest.with_name(dest.stem + "_lod%d.model" % n)
                f.write_bytes(data)
                files.append(f)
            lod.append((path, SET_DONOR, (tuple(lo), tuple(hi))))
        return lod, files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("map")
    b.add_argument("out", type=Path)
    b.add_argument("--scale", type=int, default=2)
    b.add_argument("--method", choices=("lanczos", "nearest", "esrgan"), default="lanczos")
    b.add_argument("--normals", choices=("sprite", "flat"), default="sprite")
    b.add_argument("--esrgan", help="realesrgan-ncnn-vulkan.exe")
    b.add_argument("--base", help="a built scene of the map: its biome is kept")
    b.add_argument("--light", choices=("floor", "wall"), default="floor")
    b.add_argument("--export", help="also write <map>_atlas.png / .json here, for art made outside this tool")
    b.add_argument("--albedo", help="use this image of the exported atlas's layout instead of upscaling")
    b.add_argument("--relief", type=float, default=0.0, help="units of real depth, from the sprite's brightness (LOD 0)")
    b.add_argument("--shadow", type=int, default=0, help="the entities' shadowMask (D2R's walls: 3)")
    a = ap.parse_args(argv)
    esrgan = {"exe": a.esrgan, "work": str(a.out)} if a.method == "esrgan" else None
    a.out.mkdir(parents=True, exist_ok=True)
    print(json.dumps(build(a.map, a.out, a.scale, a.method, a.normals, esrgan, a.base, light=a.light, shadow=a.shadow, relief=a.relief, export=a.export, albedo=a.albedo)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
