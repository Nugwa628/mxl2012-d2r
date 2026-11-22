#!/usr/bin/env python
"""A Median monster's classic animation as an HD unit: one card per frame, shown and hidden by bones (lane hdtools-monster).

tools/monster_card.py shows one frame. This tool carries every frame of the chosen modes and directions on one mesh and lets
D2R's own animation system pick the card to show, with data only:

  mesh       one card (2 triangles) per mode x direction x frame, all on one texture atlas. Each card hangs half on a
             DIRECTION bone (d0..d7) and half on a FRAME bone (f<mode><nn>). A bone that is "off" sits OFF_Y under the ground,
             so a card is where it belongs only while both of its bones are on (linear skinning: v + (t_dir + t_frame) / 2).
  clips      one Granny clip per mode: its frame bones come on one after the other at the classic frame time (25 per second at
             COF speed 256); the frame bones of the other modes stay off. `death` plays DT once, `dead` holds its last frame.
  states     an own state machine: modeId -> clip (crossfade 0: a blend would put every card half way under the ground).
  direction  `turn`: one clip per mode AND facing (that facing's direction bone on), each state binding its eight clips under
             the engine's first eight weapon class keys (WEAPON_KEYS, clockwise on screen from "down"). The plugin part
             `spritedir` (plugin/src/sprite_dir.cpp) hands the engine the key of the monster's facing in place of its
             weapon class, so the card shows the classic direction. A monster's own weapon class is hth: without the
             plugin part the unit shows "down" in every state. States get a loop count above 0 (LOOPS): the engine plays
             a state again under another key only then.
             Without `turn` ONE direction's art is shown (`shown`): the engine turns a unit's model by the monster's
             facing (a continuous yaw; `inherit`), or leaves it on the world's axes (the default here: the card always
             faces the camera). Tried and failed in game: `fan` (all 8 directions' cards at once, one-sided, each turned
             back by its direction's yaw: back-face culling leaves 3 to 4 cards on screen), `lean` (narrows that window,
             smears the art), `aim` (the trap units' aim layer driving the direction bones: every direction is drawn at
             once). See docs/testing.md, "Lane hdtools-monster".
  texture    `scale` 2 or 4 with a method of tools/monster_upscale.py; `gain` brightens the colours (the card is lit by the
             scene like any model and comes out darker than the classic sprite).

  py -3 tools/monster_flipbook.py build OUT_DATA_DIR --monster hardliner [--modes NU,WL,A1,GH,DT] [--dirs 8] [--aim]
        [--turn] [--scale 1] [--act 1] [--base MONSTERS_JSON] [--lod-base MODEL_LOD_DESC] [--d2r DIR]
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import monster_card  # noqa: E402
import monster_sheet  # noqa: E402
import monster_upscale  # noqa: E402

OFF_Y = -4000.0            # an "off" bone: its cards go half this far under the ground, far off the screen
TICK = 1.0 / 25.0          # a classic frame at COF speed 256
EDGE = 0.02                # share of a frame's time in which a card goes away (two knots: the curves are linear)
AIM_SECONDS = 0.6333334    # D2R's additive_aim clips: one turn over this long
ATLAS_WIDTH = 2048
CLIP_DONOR = "data/hd/character/enemy/wakeofdestruction/animation/combined.animations"
SKELETON_DONOR = "data/hd/character/enemy/infernosentry/skeleton/infernosentry.skeleton"
FOLDER = "data/hd/character/enemy/mxl/flip/%s"
UNIT = "data/hd/character/enemy/mxl_flip_%s.json"
MODE_IDS = {"dt": 0, "nu": 1, "wl": 2, "gh": 3, "a1": 4, "a2": 5, "bl": 6, "sc": 7, "s1": 8, "s2": 9, "s3": 10, "s4": 11,
            "dd": 12, "kb": 13, "sq": 14, "rn": 15}
CLIP_OF = {"dt": "death", "nu": "neutral", "wl": "walk", "gh": "gethit", "a1": "attack1", "a2": "attack2", "bl": "block",
           "sc": "cast", "s1": "skill1", "s2": "skill2", "s3": "skill3", "s4": "skill4", "dd": "dead", "kb": "knockback",
           "sq": "sequence", "rn": "run"}
FALLBACK = {"wl": "nu", "gh": "nu", "a1": "nu", "a2": "a1", "bl": "nu", "sc": "a1", "s1": "a1", "s2": "a1", "s3": "a1",
            "s4": "a1", "kb": "gh", "sq": "nu", "rn": "wl", "dt": "nu", "dd": "dt"}
AIM_COMPONENTS = ("AimLayersComponent", "LookAtAnimationControlComponent")
# `turn`: the weapon class keys of a state's animationBindings in the engine's own order (its loader gives them 0 to 7);
# key k binds the clip of the k-th facing clockwise on screen from "down" (monster_sheet.CLOCKWISE_8[k])
WEAPON_KEYS = ("hth", "bow", "1hs", "1ht", "stf", "2hs", "2ht", "xbw")
LOOPS = 1000000            # `turn`: a looping state's loop count (0 = for ever is not played again under another key)


def facing_clip(base: str, key) -> str:
    """The clip of a mode's `base` clip for facing `key` (None: the unit has one clip per mode)."""
    return base if key is None else "%s_%d" % (base, key)


def frame_bone(mode: str, f: int) -> str:
    return "f%s%02d" % (mode, f)


def bone_names(frames: dict, dirs) -> list:
    """Direction bones, then the frame bones of every mode ({mode: frame count}); lower case, so every sort agrees."""
    return ["d%d" % d for d in dirs] + [frame_bone(m, f) for m in frames for f in range(frames[m])]


def frame_keys(f: int, n: int, dt: float, edge: float = EDGE):
    """(knots, on) of frame f of n: on from f * dt to (f + 1) * dt, off elsewhere, with linear edges of edge * dt."""
    e = dt * edge
    pts = [(0.0, f == 0)]
    if f > 0:
        pts += [(f * dt - e, False), (f * dt, True)]
    if f < n - 1:
        pts += [((f + 1) * dt - e, True), ((f + 1) * dt, False)]
    pts.append((n * dt, f == n - 1))
    return [p[0] for p in pts], [p[1] for p in pts]


def sector_keys(j: int, n: int, length: float, edge: float = EDGE):
    """(knots, on) of direction sector j of n over a clip of one turn: on within half a sector of j * length / n (sector 0
    wraps round the ends). Every bone is on at t = 0 exactly: the clip's first pose is the rest pose, whichever of the two the
    engine takes as the additive reference."""
    w = length / n
    e = w * edge
    lo, hi = (j - 0.5) * w, (j + 0.5) * w
    if j == 0:
        pts = [(0.0, True), (hi - e, True), (hi, False), (length - 0.5 * w - e, False), (length - 0.5 * w, True), (length, True)]
    else:
        pts = [(0.0, True), (e, False), (lo - e, False), (lo, True), (hi - e, True), (hi, False), (length, False)]
    return [p[0] for p in pts], [p[1] for p in pts]


def atlas(token: str, modes, dirs, act: int, scale: int = 1, method: str = "lanczos", width: int = 0, esrgan=None):
    """Every frame of `modes` x `dirs`, each cut to its opaque pixels, packed on one texture.
    -> (pixels, {(mode, d, f): (x, y, w, h on the atlas, x0, y0 in anchor space, w, h in classic pixels)}, {mode: frames},
    {mode: COF speed})."""
    import walls_sprite
    pal = monster_sheet.act_palette(act)
    data = monster_sheet.load(token, [m.lower() for m in modes])
    keys, raw, spots, cuts, sizes, counts, speeds = [], [], [], {}, {}, {}, {}
    for mode, entry in data.items():
        box = monster_sheet.mode_box(entry)
        counts[mode], speeds[mode] = entry["cof"]["frames"], entry["cof"]["speed"]
        for d in dirs:
            for f in range(entry["cof"]["frames"]):
                rgba = np.asarray(monster_sheet.compose(entry, d, f, box, pal))
                ys, xs = np.nonzero(rgba[..., 3])
                if not len(ys):
                    continue
                x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
                keys.append((mode, d, f))
                raw.append(rgba[y0:y1, x0:x1].copy())
                spots.append((box[0] + x0, box[1] + y0, x1 - x0, y1 - y0))
    for key, cut, spot in zip(keys, monster_upscale.upscale(raw, scale, method, esrgan), spots):   # one batch: one exe start
        cuts[key] = (cut,) + spot
        sizes[key] = (cut.shape[1], cut.shape[0])
    width = width or ATLAS_WIDTH * scale
    places, used = walls_sprite.pack(sizes, width)
    height = max(monster_card.MIN_SIDE, 1 << (used - 1).bit_length())
    px = np.zeros((height, width, 4), np.uint8)
    where = {}
    for key, (cut, x0, y0, w, h) in cuts.items():
        x, y = places[key]
        px[y:y + cut.shape[0], x:x + cut.shape[1]] = cut
        where[key] = (x, y, cut.shape[1], cut.shape[0], x0, y0, w, h)
    return walls_sprite.bleed(px), where, counts, speeds


def brightened(px, gain: float):
    """The atlas with its colours times `gain` (alpha kept)."""
    out = px.copy()
    out[..., :3] = np.clip(px[..., :3].astype(np.float32) * gain + 0.5, 0, 255).astype(np.uint8)
    return out


def turned(v, angle: float):
    """v turned about the up axis: +Z goes towards +X for a positive angle (radians)."""
    c, s = math.cos(angle), math.sin(angle)
    return (v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c) + tuple(v[3:])


def unit_yaw(d: int, zero: float = 45.0, step: float = -45.0) -> float:
    """The yaw (radians) of a unit that faces classic direction d, on the guess that a model looks along +Z: `zero` for
    "down" (towards the camera), `step` more for each next direction clockwise on the screen."""
    return math.radians(zero + step * monster_sheet.CLOCKWISE_8.index(d))


def cull_window(lean: float) -> float:
    """Half the range of yaw (degrees) over which a one-sided card that leans `lean` degrees towards the camera shows its
    front: 90 upright, less the more it leans, nothing from 60 on (the camera looks down at 30 degrees)."""
    x = math.tan(math.radians(30.0)) * math.tan(math.radians(lean))
    return math.degrees(math.acos(x)) if x < 1.0 else 0.0


def leaned(pos, lean: float):
    """The point of a card that leans `lean` degrees towards the camera (about its line on the ground) which the camera
    sees where it saw `pos` of the upright card."""
    a = math.radians(lean)
    s = pos[1] * monster_card.PX_HEIGHT / (monster_card.PX_HEIGHT * math.cos(a) - 4.0 * math.sqrt(2.0) * math.sin(a))
    side = s * math.sin(a) / math.sqrt(2.0)
    return (pos[0] + side, s * math.cos(a), pos[2] + side)


def marker(uv, bone: int, long: float = 8.0, short: float = 4.0, width: float = 0.6):
    """Two strips flat on the ground from the unit's origin: the long one along the model's +X, the short one along its +Z.
    They show in a screenshot how the engine has turned the model."""
    verts, tris = [], []
    up, tangent = (0.0, 1.0, 0.0), (1.0, 0.0, 0.0, 1.0)
    for x0, z0, x1, z1 in ((0.0, -width / 2, long, width / 2), (-width / 2, 0.0, width / 2, short)):
        base = len(verts)
        corners = ((x0, z0), (x1, z0), (x1, z1), (x0, z1))
        verts += [((x, 0.05, z), up, tangent, (uv[0] if i in (0, 3) else uv[2], uv[1] if i < 2 else uv[3]), (bone, bone))
                  for i, (x, z) in enumerate(corners)]
        tris += [(base, base + 2, base + 1), (base, base + 3, base + 2)]
    return verts, tris


def solid_uv(px, side: int = 4):
    """The uv box of a fully opaque side x side block of the atlas (for the marker)."""
    alpha = px[..., 3] == 255
    h, w = alpha.shape
    for y, x in np.argwhere(alpha)[::97]:
        if y + side <= h and x + side <= w and alpha[y:y + side, x:x + side].all():
            return ((x + 1) / w, (y + 1) / h, (x + side - 1) / w, (y + side - 1) / h)
    raise ValueError("the atlas has no opaque block")


def mesh(where: dict, size, bones: list, turn=None, lean: float = 0.0):
    """Cards of every packed frame. -> (verts: (position, normal, tangent, uv, (direction bone, frame bone) indices), tris).
    `turn`: {direction: the unit's yaw when it faces that way}; each card is turned back by it, so it faces the camera when
    the engine has turned the model that far. `lean`: see leaned()."""
    cw, ch = size
    verts, tris = [], []
    for (mode, d, f), (x, y, w, h, x0, y0, pw, ph) in sorted(where.items()):
        uv = (x / cw, y / ch, (x + w) / cw, (y + h) / ch)
        quad, faces = monster_card.card_mesh(pw, ph, x0, y0, uv)
        if lean:
            quad = [(leaned(q, lean), n, t, c) for q, n, t, c in quad]
        if turn is not None:
            quad = [(turned(q, -turn[d]), turned(n, -turn[d]), turned(t, -turn[d]), c) for q, n, t, c in quad]
        pair = (bones.index("d%d" % d), bones.index(frame_bone(mode, f)))
        base = len(verts)
        verts += [v + (pair,) for v in quad]
        tris += [tuple(base + i for i in t) for t in faces]
    return verts, tris


def flip_model(donor: bytes, verts, tris, textures: dict, bones: list, double_sided: bool = True, emissive: float = 0.0):
    """The donor's one mesh replaced by the cards, bound to `bones` (under a root). -> (bytes, bbMin, bbMax)."""
    import d2r_model as dm
    import walls_sprite
    gr2 = dm.Gr2File.read(donor)
    tree = dm.parse_tree(gr2)
    m = tree["Meshes"][0]
    vertices, topo = m["PrimaryVertexData"]["Vertices"], m["PrimaryTopology"]
    pts = [v[0] for v in verts]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    scale = max(1.0, max(abs(c) for p in pts for c in p))
    w = int(round(np.log2(scale) / 13 * 32767))
    vtd = vertices.obj[0].td
    vertices.obj = [dm.Obj(vtd, {"Position": [int(round(c / scale * 32767)) for c in p] + [w],
                                 "BoneWeights": [128, 127, 0, 0], "BoneIndices": [pair[0], pair[1], 0, 0],
                                 "Normal": [int(round(c * 127)) for c in n] + [0], "Tangent": [int(round(c * 127)) for c in t],
                                 "TextureCoordinates0": [monster_card._half(uv[0]), monster_card._half(uv[1])]})
                    for p, n, t, uv, pair in verts]
    itd = topo["Indices16"][0].td
    topo["Indices16"] = [dm.Obj(itd, {"Int16": i}) for t in tris for i in t]
    topo["Groups"] = topo["Groups"][:1]
    topo["Groups"][0]["TriFirst"], topo["Groups"][0]["TriCount"] = 0, len(tris)
    ed = m["ExtendedData"].obj
    ed["bbMin"], ed["bbMax"], ed["VertexScale"], ed["needsSingleJointSkinning"] = lo, hi, float(scale), 0
    bind = m["BoneBindings"][0]
    m["BoneBindings"] = [dm.Obj(bind.td, dict(bind.f, BoneName=b, OBBMin=lo, OBBMax=hi)) for b in bones]
    tree["Skeletons"][0]["Bones"] = skeleton_bones(tree["Skeletons"][0]["Bones"][0], bones)
    identity = dm.Transform(0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    for model in tree["Models"]:
        model["InitialPlacement"] = identity
    for mat in tree["Materials"]:
        tex = mat.get("Texture")
        if tex is not None:
            walls_sprite._retexture(tex, textures)
        med = mat["ExtendedData"].obj if mat.get("ExtendedData") is not None else None
        if med is not None and med.get("PrimaryAlphaThresholdEnabled") is not None:
            med["PrimaryAlphaThresholdEnabled"], med["PrimaryAlphaThreshold"], med["IsDoubleSided"] = 1, 0.5, int(double_sided)
            if "EmissiveIntensity" in med.f:
                med["EmissiveIntensity"] = float(emissive)
    for tex in tree["Textures"]:
        walls_sprite._retexture(tex, textures)
    data = dm.Writer(gr2).build(tree).write()
    dm.parse_tree(dm.Gr2File.read(data))
    return data, lo, hi


def skeleton_bones(template, bones: list) -> list:
    """`root` and one child bone per name, all at the origin (the rest pose shows every card)."""
    import d2r_model as dm
    identity = dm.Transform(0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    unit = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    return [dm.Obj(template.td, dict(template.f, Name=name, ParentIndex=-1 if i == 0 else 0, Transform=identity,
                                     InverseWorldTransform=list(unit))) for i, name in enumerate(["root"] + list(bones))]


def skeleton_file(donor: bytes, bones: list) -> bytes:
    import d2r_model as dm
    gr2 = dm.Gr2File.read(donor)
    tree = dm.parse_tree(gr2)
    sk = tree["Skeletons"][0]
    sk["Bones"] = skeleton_bones(sk["Bones"][0], bones)
    data = dm.Writer(gr2).build(tree).write()
    dm.parse_tree(dm.Gr2File.read(data))
    return data


class Curves:
    """The curve shapes of a D2R clip file, taken from its own objects: identity, a constant position, keyed positions."""

    def __init__(self, tree):
        import d2r_model as dm
        self.dm = dm
        self.track = self.keyed = self.const = None
        self.ident = {}
        for a in tree["Animations"]:
            for tg in a["TrackGroups"]:
                for tr in tg["TransformTracks"]:
                    self.track = self.track or tr
                    for c in ("OrientationCurve", "PositionCurve", "ScaleShearCurve"):
                        v = tr[c]["CurveData"]
                        kind = v.td.members[0].name
                        if kind.endswith("DaK32fC32f"):
                            self.keyed = self.keyed or (tr[c], v)
                        elif kind.endswith("D3Constant32f"):
                            self.const = self.const or (tr[c], v)
                        elif kind.endswith("DaIdentity"):
                            self.ident.setdefault(v.obj["Dimension"], (tr[c], v))
        if not (self.keyed and self.const and set(self.ident) >= {3, 4, 9}):
            raise ValueError("the clip donor lacks a curve shape (keyed, constant, identity 3 / 4 / 9)")

    def _wrap(self, pair, fields):
        curve, v = pair
        dm = self.dm
        obj = dm.Obj(v.td, dict(v.obj.f, **fields))
        return dm.Obj(curve.td, {"CurveData": dm.Variant(v.td, obj)})

    def identity(self, dim: int):
        return self._wrap(self.ident[dim], {})

    def constant(self, xyz):
        return self._wrap(self.const, {"Controls": [float(c) for c in xyz]})

    def keyed_y(self, knots, ys):
        """A linear position curve (0, y, 0) through (knot, y)."""
        dm = self.dm
        v = self.keyed[1]
        head = v.obj[v.td.members[0].name]
        real = v.obj["Knots"][0].td
        return self._wrap(self.keyed, {v.td.members[0].name: dm.Obj(head.td, dict(head.f, Degree=1)),
                                       "Knots": [dm.Obj(real, {"Real32": float(k)}) for k in knots],
                                       "Controls": [dm.Obj(real, {"Real32": float(c)}) for y in ys for c in (0.0, y, 0.0)]})

    def transform_track(self, name: str, position):
        return self.dm.Obj(self.track.td, {"Name": name, "Flags": 0, "OrientationCurve": self.identity(4),
                                           "PositionCurve": position, "ScaleShearCurve": self.identity(9)})


def clips_file(donor: bytes, frames: dict, speeds: dict, dirs, bounds, shown=None, aim=False, all_on=False, turn=False):
    """The unit's clip file. `frames`: {mode: frame count}; `shown`: the one direction on (with `aim` or `all_on` every direction
    is on: the aim clip, or the geometry, takes the others away); `turn`: one clip per mode and facing instead
    (facing_clip(base, k) shows direction CLOCKWISE_8[k]). -> (bytes, [clip names])."""
    import d2r_model as dm
    gr2 = dm.Gr2File.read(donor)
    tree = dm.parse_tree(gr2)
    cv = Curves(tree)
    anim0 = tree["Animations"][0]
    aim0 = next((a for a in tree["Animations"] if a["Name"] == "additive_aim"), None)
    group0 = anim0["TrackGroups"][0]
    off = lambda: cv.constant((0.0, OFF_Y, 0.0))
    lo, hi = bounds

    def clip(name, length, tracks, loop, vectors=()):
        tracks = dict(tracks, root=cv.identity(3))
        tts = [cv.transform_track(n, tracks[n]) for n in sorted(tracks)]
        group = dm.Obj(group0.td, dict(group0.f, Name="root", TransformTracks=tts, VectorTracks=list(vectors), TransformLODErrors=[],
                                       TextTracks=[]))
        ext = anim0["ExtendedData"]
        ext = dm.Variant(ext.td, dm.Obj(ext.obj.td, dict(ext.obj.f, bbAnimMin=list(lo), bbAnimMax=list(hi))))
        return dm.Obj(anim0.td, dict(anim0.f, Name=name, Duration=float(length), TrackGroups=[group], DefaultLoopCount=loop,
                                     ExtendedData=ext))

    def directions(on):
        return {"d%d" % d: (cv.identity(3) if aim or all_on or d == on else off()) for d in dirs}

    if turn and sorted(dirs) != list(range(8)):
        raise ValueError("turn needs all eight directions")
    facings = list(enumerate(monster_sheet.CLOCKWISE_8)) if turn else [(None, shown)]
    out = []
    for mode, n in frames.items():
        dt = TICK * 256.0 / (speeds.get(mode) or 256)
        for key, d in facings:
            tracks = directions(d)
            for other, k in frames.items():
                for f in range(k):
                    if other != mode:
                        tracks[frame_bone(other, f)] = off()
                    elif n == 1:
                        tracks[frame_bone(other, f)] = cv.identity(3)
                    else:
                        knots, on = frame_keys(f, n, dt)
                        tracks[frame_bone(other, f)] = cv.keyed_y(knots, [0.0 if o else OFF_Y for o in on])
            out.append(clip(facing_clip(CLIP_OF[mode], key), max(n * dt, 1.0 / 30), tracks, 1 if mode == "dt" else 0))
    if "dt" in frames and "dd" not in frames:      # the corpse: the last frame of the death
        for key, d in facings:
            tracks = directions(d)
            for other, k in frames.items():
                for f in range(k):
                    tracks[frame_bone(other, f)] = cv.identity(3) if (other, f) == ("dt", frames["dt"] - 1) else off()
            out.append(clip(facing_clip("dead", key), 1.0 / 30, tracks, 0))
    if aim:
        if aim0 is None:
            raise ValueError("the clip donor has no additive_aim clip")
        order = [d for d in monster_sheet.CLOCKWISE_8 if d in dirs] if len(dirs) == 8 else list(dirs)
        tracks = {b: cv.identity(3) for b in bone_names(frames, dirs)}
        for j, d in enumerate(order):
            knots, on = sector_keys(j, len(order), AIM_SECONDS)
            tracks["d%d" % d] = cv.keyed_y(knots, [0.0 if o else OFF_Y for o in on])
        out.append(clip("additive_aim", AIM_SECONDS, tracks, 1, aim0["TrackGroups"][0]["VectorTracks"]))
    tree["Animations"] = out
    tree["TrackGroups"] = [a["TrackGroups"][0] for a in out]
    data = dm.Writer(gr2).build(tree).write()
    dm.parse_tree(dm.Gr2File.read(data))
    return data, [a["Name"] for a in out]


def state_machine(name: str, folder: str, clips: list, frames: dict, aim=False, turn=False) -> dict:
    """modeId -> clip, every mode of the game covered (a mode without frames plays its FALLBACK), no crossfades. `turn`:
    every state binds its clip of each facing under that facing's weapon class key, loops a counted number of times, and
    has a transition to itself (the engine's default for a pair without one is a 0.2 s blend)."""
    first = lambda base: facing_clip(base, 0 if turn else None)

    def clip_of(mode):
        seen = set()
        while first(CLIP_OF[mode]) not in clips and mode in FALLBACK and mode not in seen:
            seen.add(mode)
            mode = FALLBACK[mode]
        if first(CLIP_OF[mode]) in clips:
            return CLIP_OF[mode]
        return clips[0][:-2] if turn else clips[0]

    def bindings(mode):
        base = clip_of(mode)
        return {key: [facing_clip(base, k)] for k, key in enumerate(WEAPON_KEYS)} if turn else {"hth": [base]}
    path = lambda c: "%s/animation/%s.animation" % (folder, c)
    states = [{"type": "AnimationState", "name": "State_%s" % m.upper(), "_name": m.upper(), "audioId": "",
               "loopCount": 1 if m == "dt" else LOOPS if turn else 0, "stateId": i, "enableVfxAttributes": False, "modeId": i,
               "skillIndex": -1, "stepIndex": 0, "animationBindings": bindings(m), "enterEvents": [], "exitEvents": [],
               "exitBlendType": 0}
              for m, i in sorted(MODE_IDS.items(), key=lambda kv: kv[1]) if m != "sq"]   # a sequence state must name its skill
    if aim:
        states.append({"type": "AnimationState", "name": "State_AIM", "_name": "Additive_Aim", "audioId": "", "loopCount": 1,
                       "stateId": 17, "enableVfxAttributes": False, "modeId": 100, "skillIndex": -1, "stepIndex": 0,
                       "animationBindings": {"hth": ["additive_aim"]}, "enterEvents": [], "exitEvents": [], "exitBlendType": 0})
    ids = [s["stateId"] for s in states]
    transitions = [{"type": "AnimationTransitionGroup", "name": "from_%d" % a, "from": a,
                    "settings": [{"type": "AnimationTransitionItem", "name": "from_%d_to_%d" % (a, b), "crossfadeSeconds": 0.0,
                                  "to": b} for b in ids if turn or b != a]} for a in ids]   # turn: a state follows itself
    empty = ("particles", "models", "skeletons", "textures", "physics", "json", "variantdata", "objecteffects", "other")
    return {"dependencies": dict({k: [] for k in empty}, animations=[{"path": path(c)} for c in clips]),
            "type": "AnimationStateMachine", "name": name, "unitType": "UNIT_MONSTER",
            "animations": [{"type": "AnimationItem", "name": c, "filename": path(c)} for c in clips],
            "states": states, "transitions": transitions}


def build(out: Path, monster: str, modes=("NU", "WL", "A1", "GH", "DT"), dirs=tuple(range(8)), shown=4, aim=False, act=1,
          scale=1, method="lanczos", base=None, lod_base=None, read=None, esrgan=None, aim_offset=0.0, inherit=False,
          fan=False, lean=0.0, mark=False, tag="", art=None, zero=45.0, step=-45.0, width=0, emissive=0.0, gain=1.0,
          turn=False) -> dict:
    """The flipbook unit of one monster under `out` (a mod's data folder, or an overlay of one). -> a report.
    `inherit`: the engine turns the model with the monster's facing (else the model keeps the world's axes); `fan`: with
    that, every direction's cards are in place at once, one-sided, each turned back by its direction's yaw (`zero`, `step`:
    unit_yaw); `lean`: cards lean towards the camera; `mark`: ground strips along the model's axes; `tag`: a suffix of the
    unit's names (several variants side by side); `art`: the token whose art is drawn (default: the monster's own);
    `gain`: the colours times this (sRGB values, clipped); `turn`: one clip per mode and facing, bound by weapon class key
    (the plugin part `spritedir` picks the facing's; not with `aim`, `fan` or `inherit`)."""
    import d2r_texture
    import model_lod_desc
    read = read or monster_card.d2r_reader()
    out = Path(out)
    token = art or monster_card.token_of(monster)
    safe = monster_sheet.safe(token) + tag
    folder = FOLDER % safe
    inherit = inherit or fan
    if turn and (aim or inherit):
        raise ValueError("turn: the card keeps the world's axes and has no aim clip")
    report = {"monster": monster, "token": token, "unit": "mxl_flip_%s" % safe, "files": []}

    def write(rel: str, data: bytes):
        dest = out / rel[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        report["files"].append(rel)

    px, where, frames, speeds = atlas(token, modes, dirs, act, scale, method, width, esrgan)
    if gain != 1.0:
        px = brightened(px, gain)
    bones = bone_names(frames, dirs)
    yaws = {d: unit_yaw(d, zero, step) for d in dirs} if fan else None
    verts, tris = mesh(where, (px.shape[1], px.shape[0]), bones, yaws, lean)
    if mark:
        more, faces = marker(solid_uv(px), bones.index("d%d" % dirs[0]))
        tris += [tuple(len(verts) + i for i in t) for t in faces]
        verts += more
    textures = {k: "%s/%s_%s.texture" % (folder, safe, k) for k in ("alb", "nrm", "orm")}
    nrm, orm = monster_card.flat_maps((256, 256))
    for kind, pixels, linear in (("alb", px, False), ("nrm", nrm, True), ("orm", orm, True)):
        d2r_texture.write_bc3(out / textures[kind][len("data/"):], pixels, monster_card.MIPS, linear=linear)
        report["files"].append(textures[kind])
    model = "%s/torso.model" % folder
    for k in range(monster_card.LODS):
        data, lo, hi = flip_model(read(monster_card.DONOR[:-len(".model")] + "_lod%d.model" % k), verts, tris, textures, bones,
                                  double_sided=not fan, emissive=emissive)
        write(model[:-len(".model")] + "_lod%d.model" % k, data)
    skeleton = "%s/skeleton/%s.skeleton" % (folder, safe)
    write(skeleton, skeleton_file(read(SKELETON_DONOR), bones))
    clips, names = clips_file(read(CLIP_DONOR), frames, speeds, dirs, (lo, hi), shown=shown, aim=aim, all_on=fan, turn=turn)
    write("%s/animation/combined.animations" % folder, clips)
    machine = "%s/%s_state_machine.json" % (folder, safe)
    write(machine, json.dumps(state_machine("%s_statemachine" % safe, folder, names, frames, aim, turn),
                              separators=(",", ":")).encode())
    donor_unit = json.loads(read(monster_card.DONOR_UNIT).decode("utf-8"))
    unit = monster_card.unit_json(donor_unit, report["unit"], model, textures,
                                  keep=monster_card.KEEP + (AIM_COMPONENTS if aim else ()))
    for c in unit["entities"][0]["components"]:
        if c["type"] == "UnitRootComponent":
            c["state_machine_filename"] = machine
            c["doNotInheritRotation"] = not inherit
        elif c["type"] == "SkeletonDefinitionComponent":
            c["filename"] = skeleton
        elif c["type"] == "AimLayersComponent":
            for layer in c["aimLayers"]:
                layer["yawAngleOffset"] = float(aim_offset)
    unit["dependencies"]["skeletons"] = [{"path": skeleton}]
    unit["dependencies"]["json"] = [{"path": machine}]
    write(UNIT % safe, json.dumps(unit, separators=(",", ":")).encode("utf-8"))
    table = json.loads(Path(base).read_text(encoding="utf-8") if base else read(monster_card.MONSTERS).decode("utf-8"))
    table[monster] = report["unit"]
    write(monster_card.MONSTERS, json.dumps(table, indent=4).encode("utf-8"))
    lod = Path(lod_base).read_bytes() if lod_base else read(monster_card.LOD_DESC)
    record = {"bounds": (lo, hi), "model_type": 256,
              "lods": [{"flipbook": 0, "meshes": [{"bounds": (lo, hi), "layer": 1, "bones": len(bones),
                                                   "format": model_lod_desc.FMT_SKINNED}]} for _ in range(monster_card.LODS)]}
    write(monster_card.LOD_DESC, model_lod_desc.add_own(lod, {model: record}))
    report.update(frames=frames, speeds=speeds, cards=len(where), bones=len(bones) + 1, clips=names, turn=bool(turn),
                  texture_px=[px.shape[1], px.shape[0]], scale=scale, bounds=[lo, hi],
                  bytes={rel: (out / rel[len("data/"):]).stat().st_size for rel in report["files"]})
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("out")
    b.add_argument("--monster", required=True)
    b.add_argument("--modes", default="NU,WL,A1,GH,DT")
    b.add_argument("--dirs", type=int, default=8, help="8: every direction; 1: the shown one only")
    b.add_argument("--shown", type=int, default=4)
    b.add_argument("--aim", action="store_true")
    b.add_argument("--aim-offset", type=float, default=0.0)
    b.add_argument("--inherit", action="store_true", help="the engine turns the model with the monster's facing")
    b.add_argument("--fan", action="store_true", help="every direction's cards at once, one-sided, turned back by their yaw")
    b.add_argument("--lean", type=float, default=0.0, help="degrees the cards lean towards the camera")
    b.add_argument("--mark", action="store_true", help="ground strips along the model's +X (long) and +Z (short)")
    b.add_argument("--turn", action="store_true", help="one clip per mode and facing, bound by weapon class key (plugin part spritedir)")
    b.add_argument("--tag", default="")
    b.add_argument("--art", help="draw this token's art for the monster")
    b.add_argument("--zero", type=float, default=45.0)
    b.add_argument("--step", type=float, default=-45.0)
    b.add_argument("--act", type=int, default=1)
    b.add_argument("--scale", type=int, default=1)
    b.add_argument("--method", default="lanczos", help="see tools/monster_upscale.py (esrgan:<model> needs --esrgan)")
    b.add_argument("--esrgan", help="realesrgan-ncnn-vulkan.exe")
    b.add_argument("--atlas-width", type=int, default=0, help="default: 2048 x scale")
    b.add_argument("--emissive", type=float, default=0.0, help="the material's EmissiveIntensity (0: lit by the scene only)")
    b.add_argument("--gain", type=float, default=1.0, help="the colours times this")
    b.add_argument("--base")
    b.add_argument("--lod-base")
    b.add_argument("--d2r")
    a = ap.parse_args(argv)
    dirs = tuple(range(8)) if a.dirs == 8 else (a.shown,)
    rep = build(Path(a.out), a.monster, a.modes.split(","), dirs, a.shown, a.aim, a.act, a.scale, a.method, a.base, a.lod_base,
                monster_card.d2r_reader(a.d2r), aim_offset=a.aim_offset, inherit=a.inherit, fan=a.fan, lean=a.lean,
                mark=a.mark, tag=a.tag, art=a.art, zero=a.zero, step=a.step, width=a.atlas_width, emissive=a.emissive, gain=a.gain,
                esrgan={"exe": a.esrgan} if a.esrgan else None, turn=a.turn)
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
