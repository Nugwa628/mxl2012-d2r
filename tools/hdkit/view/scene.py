"""What gets drawn: a unit JSON (or a bare .model) as model entities with their textures and self-lit layers, or a classic
sprite frame as a card.

Unit JSON (D2R `UnitDefinition`): the root entity gives the skeleton file, the state machine, `rotationOverride` and the
root scale (TransformDefinitionComponent); every other entity with a ModelDefinitionComponent is a part, unless the same
entity also has an ObjectEffectDefinitionComponent: then it is a self-lit layer drawn over that model (the Fire Golem
pattern: the skinned model drawn a second time, additive, through a mask in the model's UV layout coloured by a gradient
strip; monster3d METHOD rule 2). The layer's PopcornFX scripts are not run: of the textures the effect names, the last
one-channel (BC4) texture is taken as its mask and the last RGBA strip (at most 16 rows) as its gradient, and the choice is
reported. A part's `<name>.model` is looked up as `<name>_lod<N>.model` when the plain name does not exist.

Card: a classic frame (PNG) on an upright quad that faces the camera, placed as tools/monster_card.py (lane fungusfix)
places it: a sprite pixel (px, py) relative to the frame anchor sits at  X = px/16 + b/8, Y = (b - py)/9.798,
Z = -px/16 + b/8  (b = the frame's lowest opaque row), the geometry of the 30-degree camera. Copied relation, not code.
Its material is its own: the frame's colours as albedo, a flat normal, ORM (255, 255, 0, 0); no self-lit layer.
"""
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import gr2

_TOOLS = Path(__file__).resolve().parents[2]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import d2r_texture  # noqa: E402

CLOCKWISE_8 = (4, 0, 5, 1, 6, 2, 7, 3)    # classic direction of facing key 0..7 (0 = the screen's bottom, clockwise)
MODE_CLIP = {"dt": "death", "nu": "neutral", "wl": "walk", "gh": "gethit", "a1": "attack1", "a2": "attack2",
             "bl": "block", "sc": "cast", "s1": "skill1", "s2": "skill2", "s3": "skill3", "s4": "skill4", "dd": "dead",
             "kb": "knockback", "sq": "sequence", "rn": "run"}
FMT_BC4 = 0x3F
FMT_RGBA8 = 0x1F


@dataclass
class Texture:
    logical: str
    fmt: int
    mips: list            # [(h, w, 4) uint8], largest first
    srgb: bool = False


@dataclass
class Layer:
    name: str
    effect: str
    mask: Texture
    strip: Texture
    picked: dict = field(default_factory=dict)


@dataclass
class Part:
    name: str
    model: str            # logical path that answered
    meshes: list          # [gr2.Mesh]
    skeleton: object      # gr2.Skeleton or None
    textures: dict        # usage -> Texture
    layers: list = field(default_factory=list)


@dataclass
class Unit:
    name: str
    parts: list
    clips: dict = field(default_factory=dict)       # name -> gr2.Clip
    root_scale: float = 1.0
    rotation_override: tuple = (0.0, 0.0, 0.0, 1.0)
    notes: list = field(default_factory=list)
    kind: str = "model"
    card: dict | None = None                        # card: {"rgba": (h, w, 4), "quad": 4x3 corners, "uv": 4x2}


MIP_DROP = 0   # top mip levels not decoded (a whole-map render far below 1:1 needs none of them; mapview.hd.render sets it)


MAX_TEX_SIDE = None   # top mips larger than this are not decoded either (mapview.hd.render: 2048 below 1:1)


TEXTURE_CACHE_BYTES = 3 << 30
_TEXTURES = {}   # (vfs, path, srgb, MIP_DROP, MAX_TEX_SIDE) -> Texture: the tile models of an atlas share one decode (and one
#                 GPU upload, gpu.Renderer.texture keys on the array); mapview.hd.release() empties it


def read_texture(vfs, logical, srgb=False) -> Texture:
    key = (id(vfs), logical, srgb, MIP_DROP, MAX_TEX_SIDE)
    hit = _TEXTURES.get(key)
    if hit is not None and hit[0] is vfs:
        return hit[1]
    tex = _read_texture(vfs, logical, srgb)
    size = sum(m.nbytes for m in tex.mips)
    if sum(t.nbytes for _v, x in _TEXTURES.values() for t in x.mips) + size > TEXTURE_CACHE_BYTES:
        _TEXTURES.clear()          # long-lived processes (the MCP server): start over rather than grow
    _TEXTURES[key] = (vfs, tex)
    return tex


def _read_texture(vfs, logical, srgb=False) -> Texture:
    fmt, w, h, mips = d2r_texture.parse_texture(vfs.read(logical))
    drop = MIP_DROP
    while MAX_TEX_SIDE and max(w, h) >> drop > MAX_TEX_SIDE:
        drop += 1
    drop = min(drop, max(0, len(mips) - 1))
    arr = [d2r_texture.decode(fmt, max(1, w >> i), max(1, h >> i), m) for i, m in enumerate(mips) if i >= drop]
    return Texture(logical, fmt, arr, srgb)


def _model_path(vfs, logical, lod):
    if vfs.exists(logical):
        return logical
    stem = logical[:-len(".model")] if logical.endswith(".model") else logical
    alt = "%s_lod%d.model" % (stem, lod)
    if vfs.exists(alt):
        return alt
    raise FileNotFoundError(logical)


def _components(ent):
    return {c["type"]: c for c in ent.get("components", [])}


def effect_textures(data: bytes) -> list:
    """Texture paths an effect file names, in file order (strings in .particles are length-prefixed, so match lazily)."""
    return [m.group().decode("ascii", "replace") for m in re.finditer(rb"data/hd/[A-Za-z0-9_/.\-]+?\.texture", data)]


def pick_layer_textures(vfs, effect_logical):
    names = effect_textures(vfs.read(effect_logical))
    mask = strip = None
    for n in names:
        if not vfs.exists(n):
            continue
        fmt, w, h, _m = d2r_texture.parse_texture(vfs.read(n))
        if fmt == FMT_BC4:
            mask = n
        elif fmt == FMT_RGBA8 and h <= 16 and w >= 4 * h:
            strip = n
    return names, mask, strip


def load_model_part(vfs, logical, name="model", lod=0) -> Part:
    path = _model_path(vfs, logical, lod)
    meshes, sk = gr2.load_meshes(vfs.read(path))
    tex = {}
    for m in meshes:
        for usage, tl in m.maps.items():
            if usage in tex or not vfs.exists(tl):
                continue
            try:
                tex[usage] = read_texture(vfs, tl, srgb=(usage == "AlbedoTexture"))
            except KeyError:        # a format d2r_texture does not decode (terrain maps use 112): drawn without that map
                continue
    return Part(name, path, meshes, sk, tex)


def load_unit(vfs, logical, lod=0) -> Unit:
    if logical.lower().endswith(".model"):
        part = load_model_part(vfs, logical, "model", lod)
        return Unit(Path(logical).stem, [part])
    u = json.loads(vfs.read(logical).decode("utf-8"))
    unit = Unit(u.get("name", Path(logical).stem), [])
    skeleton_file, layers_for = None, {}
    for ent in u.get("entities", []):
        c = _components(ent)
        if "UnitRootComponent" in c:
            ro = c["UnitRootComponent"].get("rotationOverride") or {}
            unit.rotation_override = tuple(float(ro.get(k, d)) for k, d in (("x", 0), ("y", 0), ("z", 0), ("w", 1)))
            if "SkeletonDefinitionComponent" in c:
                skeleton_file = c["SkeletonDefinitionComponent"]["filename"]
            td = c.get("TransformDefinitionComponent")
            if td:
                s = td.get("scale", {})
                unit.root_scale = float(s.get("y", 1.0))
                if abs(float(s.get("x", 1)) - float(s.get("z", 1))) > 1e-6 or abs(float(s.get("x", 1)) - unit.root_scale) > 1e-6:
                    unit.notes.append("root scale not uniform; y used: %s" % s)
            continue
        md = c.get("ModelDefinitionComponent")
        if md is None:
            continue
        if "ObjectEffectDefinitionComponent" in c:
            layers_for.setdefault(md["filename"].lower(), []).append((ent.get("name", ""), c["ObjectEffectDefinitionComponent"]["filename"]))
            continue
        try:
            part = load_model_part(vfs, md["filename"], ent.get("name", "part"), lod)
        except FileNotFoundError:          # a unit may name a mode's model that does not ship (braziers: special1)
            unit.notes.append("%s: model %s not found; part skipped" % (ent.get("name", "part"), md["filename"]))
            continue
        part.model_key = md["filename"].lower()
        unit.parts.append(part)
    for part in unit.parts:
        for lname, eff in layers_for.get(getattr(part, "model_key", ""), []):
            names, mask, strip = pick_layer_textures(vfs, eff)
            if mask is None or strip is None:
                unit.notes.append("layer %s: no mask/strip found among %d textures; skipped" % (lname, len(names)))
                continue
            part.layers.append(Layer(lname, eff, read_texture(vfs, mask), read_texture(vfs, strip, srgb=True),
                                     {"mask": mask, "strip": strip, "named": len(names)}))
    # skeleton: the model's own when it has one (its inverse world transforms match its vertices), else the unit's
    for part in unit.parts:
        if part.skeleton is None and skeleton_file and vfs.exists(skeleton_file):
            _g, t = gr2.load_tree(vfs.read(skeleton_file))
            part.skeleton = gr2.Skeleton(t["Skeletons"][0])
            unit.notes.append("%s: skeleton from %s" % (part.name, skeleton_file))
    # clips: <model folder>/animation/combined.animations, as D2R lays a unit out
    for part in unit.parts:
        anim = str(Path(part.model).parent / "animation" / "combined.animations").replace("\\", "/")
        if vfs.exists(anim) and part.skeleton is not None:
            unit.clips = gr2.load_clips(vfs.read(anim), part.skeleton)
            break
    return unit


# ---- classic card ---------------------------------------------------------------------------------------------------------------

def card_corners(x0, y0, x1, y1, b):
    """World corners (top-left, top-right, bottom-right, bottom-left) of a card covering sprite pixels x0..x1, y0..y1
    (relative to the anchor; y down) whose lowest opaque row is b. See the module note."""
    def P(px, py):
        return [px / 16.0 + b / 8.0, (b - py) / (8.0 * math.sqrt(1.5)), -px / 16.0 + b / 8.0]
    return np.array([P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)], float)


def load_card(frames_dir, mode="nu", key=0, frame=0) -> Unit:
    """A classic frame as a card: frames_dir/<mode>/d<dir>_f<frame>.png with frames_dir/frames.json (box per mode,
    the PNG is that box). `key` is the facing key; the classic direction is CLOCKWISE_8[key]."""
    from PIL import Image
    fd = Path(frames_dir)
    meta = json.loads((fd / "frames.json").read_text(encoding="utf-8"))[mode]
    d = CLOCKWISE_8[int(key) % 8]
    f = int(frame) % int(meta["frames"])
    rgba = np.array(Image.open(fd / mode / ("d%d_f%02d.png" % (d, f))).convert("RGBA"))
    x0, y0 = meta["box"][0], meta["box"][1]
    h, w = rgba.shape[:2]
    rows = np.nonzero((rgba[..., 3] > 0).any(1))[0]
    b = (y0 + int(rows.max()) + 1) if len(rows) else (y0 + h)
    quad = card_corners(x0, y0, x0 + w, y0 + h, b)
    unit = Unit("card:%s/d%d_f%02d" % (mode, d, f), [], kind="card",
                card={"rgba": rgba, "quad": quad, "uv": np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float),
                      "dir": d, "frame": f, "mode": mode, "bottom": b})
    return unit
