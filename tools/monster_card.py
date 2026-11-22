#!/usr/bin/env python
"""A Median monster's classic sprite as an HD unit: a camera-facing card that carries one DCC frame (lane hdtools-monster).

D2R's HD renderer draws a monster as a skinned Granny model; it has no sprite path for units. A monster of Median's own art
therefore gets a D2R stand-in model (tools/hd_monsters.py). This tool writes the other answer: an HD unit whose only mesh is a
flat card with the classic frame as its texture, standing where the sprite stands and sized so that it covers the same pixels.

  unit    data/hd/character/enemy/mxl_card_<token>.json    (D2R's infernosentry unit, cut down: the unit does not turn)
  model   data/hd/character/enemy/mxl/card/<token>/torso_lod0..4.model   (D2R's one-mesh infernosentry torso, new vertices)
  maps    data/hd/character/enemy/mxl/card/<token>/<token>_alb|_nrm|_orm.texture
  index   data/hd/character/monsters.json (the monster's Id -> the unit), data/hd/model_lod_desc.bin (the model path)

Geometry (the HD camera looks along (-s, -1, -s), s = sqrt(1.5): 30 degrees above the ground, turned 45 degrees). A scene
offset (X, Y, Z) lands on the classic screen at  u = 8 (X - Z),  v = 4 (X + Z) - 9.798 Y  pixels (v down). The card is upright,
spans the screen's right axis (1, 0, -1) and stands on the ground under the frame's lowest pixel, so a sprite pixel (px, py)
relative to the DCC anchor sits at  X = px / 16 + b / 8,  Y = (b - py) / 9.798,  Z = -px / 16 + b / 8  with b = the frame's
bottom edge. The unit keeps the world's axes (`doNotInheritRotation`), so the card faces the camera whatever the monster does.

  py -3 tools/monster_card.py build OUT_DATA_DIR --monster hardliner [--mode NU --dir 4 --frame 0] [--scale 2 --method lanczos]
        [--base MONSTERS_JSON] [--lod-base MODEL_LOD_DESC] [--drop ID ...] [--d2r DIR]
"""
import argparse
import csv
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402
import monster_sheet  # noqa: E402

PX_ACROSS = 16.0           # classic pixels per world unit of X (and of -Z) along the screen's right axis
PX_DEPTH = 8.0             # classic pixels per world unit of X + Z (towards the camera, down the screen)
PX_HEIGHT = 8.0 * math.sqrt(1.5)   # 9.798 classic pixels per world unit of height
DONOR = "data/hd/character/enemy/infernosentry/torso.model"      # one skinned mesh on one bone, VariantMaterial, 5 LODs
DONOR_UNIT = "data/hd/character/enemy/infernosentry.json"
LODS = 5
BONE = "root"              # a bone of the unit's skeleton that no clip moves
UNIT = "data/hd/character/enemy/mxl_card_%s.json"
MODEL = "data/hd/character/enemy/mxl/card/%s/torso.model"
TEXTURE = "data/hd/character/enemy/mxl/card/%s/%s_%s.texture"
MONSTERS = "data/hd/character/monsters.json"
LOD_DESC = "data/hd/model_lod_desc.bin"
MIPS = 5
MIN_SIDE = 64              # a texture smaller than this lost the GPU device once (lane hdscene2)
KEEP = ("UnitRootComponent", "SkeletonDefinitionComponent", "VariantDefinitionComponent")
NORMAL = (0.5, 0.7071, 0.5)       # between "up" and "towards the camera": lit like the ground it stands on
TANGENT = (0.7071, 0.0, -0.7071, 1.0)


def _half(f: float) -> int:
    return struct.unpack("<H", struct.pack("<e", f))[0]


def token_of(monster: str) -> str:
    """The monstats Code (animation token, lower case) of a monster Id."""
    with open(fxpaths.MXL_EXCEL / "monstats.txt", newline="", encoding="latin-1") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row["Id"].lower() == monster.lower():
                return row["Code"].lower()
    raise KeyError("no monstats row %r" % monster)


def card_frame(token: str, mode: str, d: int, f: int, act: int):
    """One classic frame cut to its opaque pixels. -> ((h, w, 4) uint8, (x0, y0): the cut's top left in anchor space)."""
    entry = monster_sheet.load(token, [mode.lower()])[mode.lower()]
    box = monster_sheet.mode_box(entry)
    rgba = np.asarray(monster_sheet.compose(entry, d, f, box, monster_sheet.act_palette(act)))
    ys, xs = np.nonzero(rgba[..., 3])
    if not len(ys):
        raise ValueError("%s %s direction %d frame %d is empty" % (token, mode, d, f))
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    return rgba[y0:y1, x0:x1].copy(), (box[0] + int(x0), box[1] + int(y0))


def canvas(rgba: np.ndarray, pad: int = 4):
    """The frame centred on a power-of-two canvas (at least MIN_SIDE) with colour bled into the border. -> (pixels, (x, y) of
    the frame's top left on it)."""
    import walls_sprite
    h, w = rgba.shape[:2]
    side = lambda n: max(MIN_SIDE, 1 << (n + 2 * pad - 1).bit_length())
    cw, ch = side(w), side(h)
    out = np.zeros((ch, cw, 4), np.uint8)
    x, y = (cw - w) // 2, (ch - h) // 2
    out[y:y + h, x:x + w] = rgba
    return walls_sprite.bleed(out, pad), (x, y)


def card_mesh(w: float, h: float, x0: float, y0: float, uv, lift: float = 0.0):
    """The card of a w x h pixel frame whose top left is (x0, y0) in anchor space: 4 vertices (position, normal, tangent, uv)
    and 2 triangles. `uv` = (u0, v0, u1, v1) of the frame on its texture."""
    import walls_sprite
    bottom = max(y0 + h, 0.0)             # the card stands under the lowest pixel, never behind the anchor
    u0, v0, u1, v1 = uv
    verts = []
    for px, py, u, v in ((x0, y0, u0, v0), (x0 + w, y0, u1, v0), (x0 + w, y0 + h, u1, v1), (x0, y0 + h, u0, v1)):
        pos = (px / PX_ACROSS + bottom / PX_DEPTH, (bottom - py) / PX_HEIGHT + lift, -px / PX_ACROSS + bottom / PX_DEPTH)
        verts.append((pos, NORMAL, TANGENT, (u, v)))
    tris = walls_sprite.wound(verts, np.array((1.0, 0.0, 1.0)), 0, ((0, 1, 2), (0, 2, 3)))
    return verts, tris


def screen_of(pos):
    """Classic pixel offset (u right, v down) of a scene offset: the inverse of card_mesh."""
    x, y, z = pos
    return PX_ACROSS / 2 * (x - z), PX_DEPTH / 2 * (x + z) - PX_HEIGHT * y


def card_model(donor: bytes, verts, tris, textures: dict, bone: str = BONE):
    """A .model: the donor's one mesh replaced by (verts, tris), every vertex on `bone`, alpha-tested and two-sided, with the
    textures {'alb' | 'nrm' | 'orm': game path}. -> (bytes, bbMin, bbMax)."""
    import d2r_model as dm
    import walls_sprite
    gr2 = dm.Gr2File.read(donor)
    tree = dm.parse_tree(gr2)
    if len(tree["Meshes"]) != 1:
        raise ValueError("card_model: the donor has %d meshes, one is wanted" % len(tree["Meshes"]))
    mesh = tree["Meshes"][0]
    vertices, topo = mesh["PrimaryVertexData"]["Vertices"], mesh["PrimaryTopology"]
    pts = [v[0] for v in verts]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    scale = max(1.0, max(abs(c) for p in pts for c in p))
    w = int(round(math.log2(scale) / 13 * 32767))
    vtd = vertices.obj[0].td
    skinned = "BoneWeights" in vertices.obj[0].f

    def vertex(v):
        (p, n, t, uv) = v
        f = {"Position": [int(round(c / scale * 32767)) for c in p] + [w],
             "Normal": [int(round(c * 127)) for c in n] + [0],
             "Tangent": [int(round(c * 127)) for c in t],
             "TextureCoordinates0": [_half(uv[0]), _half(uv[1])]}
        if skinned:
            f["BoneWeights"], f["BoneIndices"] = [255, 0, 0, 0], [0, 0, 0, 0]
        return dm.Obj(vtd, f)
    vertices.obj = [vertex(v) for v in verts]
    itd = topo["Indices16"][0].td
    topo["Indices16"] = [dm.Obj(itd, {"Int16": i}) for t in tris for i in t]
    topo["Groups"] = topo["Groups"][:1]
    topo["Groups"][0]["TriFirst"], topo["Groups"][0]["TriCount"] = 0, len(tris)
    ed = mesh["ExtendedData"].obj
    ed["bbMin"], ed["bbMax"], ed["VertexScale"] = lo, hi, float(scale)
    mesh["BoneBindings"] = mesh["BoneBindings"][:1]
    for bind in mesh["BoneBindings"]:
        bind["BoneName"], bind["OBBMin"], bind["OBBMax"] = bone, lo, hi
    identity = dm.Transform(0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    for b in tree["Skeletons"][0]["Bones"]:
        b["Transform"] = identity
        b["InverseWorldTransform"] = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    if bone not in [b["Name"] for b in tree["Skeletons"][0]["Bones"]]:
        tree["Skeletons"][0]["Bones"][0]["Name"] = bone
    for model in tree["Models"]:
        model["InitialPlacement"] = identity
    for mat in tree["Materials"]:
        tex = mat.get("Texture")
        if tex is not None:
            walls_sprite._retexture(tex, textures)
        med = mat["ExtendedData"].obj if mat.get("ExtendedData") is not None else None
        if med is None:
            continue
        if med.get("PrimaryAlphaThresholdEnabled") is not None:      # VariantMaterial (units)
            med["PrimaryAlphaThresholdEnabled"], med["PrimaryAlphaThreshold"], med["IsDoubleSided"] = 1, 0.5, 1
        elif med.get("AlphaThreshold") is not None:                  # AlphaThresholdMaterial (props)
            med["AlphaThreshold"], med["IsDoubleSided"] = 0.5, 1
    for tex in tree["Textures"]:
        walls_sprite._retexture(tex, textures)
    data = dm.Writer(gr2).build(tree).write()
    dm.parse_tree(dm.Gr2File.read(data))     # well formed
    return data, lo, hi


def unit_json(donor: dict, name: str, model: str, textures: dict, scale: float = 1.0, keep=KEEP) -> dict:
    """D2R's sentry unit turned into the card's: the root keeps the state machine, the skeleton and the colour table (the unit
    neither turns nor aims), the torso draws `model`."""
    unit = json.loads(json.dumps(donor))
    unit["name"] = name
    root, torso = unit["entities"][0], unit["entities"][1]
    root["components"] = [c for c in root["components"] if c["type"] in keep]
    for c in root["components"]:
        if c["type"] == "UnitRootComponent":
            c["doNotInheritRotation"] = True
            c["rotationOverride"] = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    old = None
    for c in torso["components"]:
        if c["type"] == "ModelDefinitionComponent":
            old, c["filename"] = c["filename"], model
        elif c["type"] == "TransformDefinitionComponent":
            c["scale"] = {"x": scale, "y": scale, "z": scale}
    dep = unit["dependencies"]
    dep["models"] = [{"path": model if m["path"] == old else m["path"]} for m in dep["models"]]
    dep["textures"] = [t for t in dep["textures"] if "/common/" in t["path"]] + [{"path": p} for p in textures.values()]
    dep["json"] = [j for j in dep["json"] if "/missiles/" not in j["path"]]
    return unit


def flat_maps(shape):
    """Flat normal map and matt, non-metal ORM map of a canvas, a quarter of its size (never under MIN_SIDE)."""
    h, w = max(MIN_SIDE, shape[0] // 4), max(MIN_SIDE, shape[1] // 4)
    nrm = np.zeros((h, w, 4), np.uint8)
    nrm[..., 0], nrm[..., 1], nrm[..., 3] = 255, 128, 128
    orm = np.zeros((h, w, 4), np.uint8)
    orm[..., 0], orm[..., 1], orm[..., 3] = 255, 217, 255
    return nrm, orm


def d2r_reader(extra=None):
    """rel -> bytes: `extra` (a folder laid out like the game's data), then the D2R extraction, the shared cache, a slot."""
    import walls_hd

    def read(rel: str):
        if extra and (Path(extra) / rel).exists():
            return (Path(extra) / rel).read_bytes()
        return walls_hd.d2r_bytes(rel)
    return read


def build(out: Path, monsters, mode="NU", d=4, f=0, act=1, scale=1, method="lanczos", base=None, lod_base=None, drop=(),
          read=None, esrgan=None, keep=KEEP, shadow=True) -> dict:
    """Card units for `monsters` (monstats Ids) under `out` (a mod's data folder, or an overlay of one). `base` / `lod_base`:
    the monsters.json / model_lod_desc.bin to extend (the installed mod's; D2R's when None). `drop`: Ids taken out of
    monsters.json (a monster with no HD definition). -> a report."""
    import d2r_texture
    import model_lod_desc
    import walls_sprite
    read = read or d2r_reader()
    out = Path(out)
    table = json.loads(Path(base).read_text(encoding="utf-8") if base else read(MONSTERS).decode("utf-8"))
    donor_unit = json.loads(read(DONOR_UNIT).decode("utf-8"))
    report = {"monsters": {}, "dropped": [], "files": []}
    new_models, bounds = {}, {}

    def write(rel: str, data: bytes):
        dest = out / rel[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        report["files"].append(rel)

    done = {}
    for monster in monsters:
        token = token_of(monster)
        safe = monster_sheet.safe(token)
        if token not in done:
            rgba, (x0, y0) = card_frame(token, mode, d, f, act)
            h, w = rgba.shape[:2]
            big = walls_sprite.upscale(rgba, scale, method, esrgan)
            px, (cx, cy) = canvas(big)
            ch, cw = px.shape[:2]
            uv = (cx / cw, cy / ch, (cx + w * scale) / cw, (cy + h * scale) / ch)
            verts, tris = card_mesh(w, h, x0, y0, uv)
            textures = {k: TEXTURE % (safe, safe, k) for k in ("alb", "nrm", "orm")}
            nrm, orm = flat_maps(px.shape)
            for kind, pixels, linear in (("alb", px, False), ("nrm", nrm, True), ("orm", orm, True)):
                dest = out / textures[kind][len("data/"):]
                d2r_texture.write_bc3(dest, pixels, MIPS, linear=linear)
                report["files"].append(textures[kind])
            model = MODEL % safe
            for k in range(LODS):
                data, lo, hi = card_model(read(DONOR[:-len(".model")] + "_lod%d.model" % k), verts, tris, textures)
                write(model[:-len(".model")] + "_lod%d.model" % k, data)
            new_models[model], bounds[model] = DONOR, (lo, hi)
            unit = unit_json(donor_unit, "mxl_card_%s" % safe, model, textures, keep=keep)
            if not shadow:
                for c in unit["entities"][1]["components"]:
                    if c["type"] == "ModelDefinitionComponent":
                        c["shadowMask"] = 0
            write(UNIT % safe, json.dumps(unit, separators=(",", ":")).encode("utf-8"))
            done[token] = {"token": token, "unit": "mxl_card_%s" % safe, "frame": [mode, d, f], "frame_px": [w, h],
                           "anchor_px": [x0, y0], "texture_px": [cw, ch], "scale": scale, "bounds": [lo, hi]}
        report["monsters"][monster] = done[token]
        table[monster] = done[token]["unit"]
    for monster in drop:
        if table.pop(monster, None) is not None:
            report["dropped"].append(monster)
    write(MONSTERS, json.dumps(table, indent=4).encode("utf-8"))
    lod = Path(lod_base).read_bytes() if lod_base else read(LOD_DESC)
    write(LOD_DESC, model_lod_desc.add(lod, new_models, bounds))
    report["bytes"] = {rel: (out / rel[len("data/"):]).stat().st_size for rel in report["files"]}
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("out")
    b.add_argument("--monster", action="append", default=[])
    b.add_argument("--mode", default="NU")
    b.add_argument("--dir", type=int, default=4)
    b.add_argument("--frame", type=int, default=0)
    b.add_argument("--act", type=int, default=1)
    b.add_argument("--scale", type=int, default=1)
    b.add_argument("--method", default="lanczos", choices=("nearest", "lanczos"))
    b.add_argument("--base")
    b.add_argument("--lod-base")
    b.add_argument("--drop", action="append", default=[])
    b.add_argument("--d2r")
    b.add_argument("--no-shadow", action="store_true")
    b.add_argument("--bare", action="store_true", help="root entity with the root and skeleton components only")
    a = ap.parse_args(argv)
    rep = build(Path(a.out), a.monster, a.mode, a.dir, a.frame, a.act, a.scale, a.method, a.base, a.lod_base, a.drop,
                d2r_reader(a.d2r), keep=KEEP[:2] if a.bare else KEEP, shadow=not a.no_shadow)
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
