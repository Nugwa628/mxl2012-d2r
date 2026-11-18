#!/usr/bin/env python
"""A classic missile / overlay animation as an HD particle flipbook (lane hdtools-effects): Median's own picture in HD.

D2R draws a missile from `data/hd/missiles/<model>.json`, whose entities name PopcornFX `.particles` files. A particle
billboard is camera-facing and unlit, its material (Diablo_Uber) has an `Atlas` feature (a grid of sub-pictures chosen per
particle by the `Atlas.TextureID` input), and D2R's own character-select campfire animates such a grid over the particle's
life. This tool builds the same thing from a classic DCC:

  texture     the frames (direction 0, on black: `additive` art) upscaled and packed row by row into one atlas of square
              cells; the cell centre is the centre of the animation's box. The billboard reads ONE channel of it, so the
              atlas is a level picture (BC4) and the colour comes from a 256-step ramp (`GradientRemap`): the art's own
              ramp when its colours lie on one line from dark to bright, else three layers (red, green and blue level,
              each with a ramp of that colour) that add up to the picture
  particles   D2R's smallest atlas effect (TEMPLATE: one billboard that follows the emitter) with its scripts and constants
              edited: one particle, a fixed size, no rotation, the frame number computed from the particle's age (`loop`:
              frac(age * fps / frames) * frames; `once`: age * fps, the particle dies after the last frame). The blend is
              additive, as classic `Trans` 1. The ramp is stored so that the screen gets the classic colour (RESPONSE)
  light       missiles.txt `Light` / `Red` `Green` `Blue` as a point light that follows the missile (LIGHT_TEMPLATE)
  definition  a UnitDefinition with one effect entity per layer (and the light), lifted so the picture stands where the
              classic one does (box centre and `zoffset`)

  py -3 tools/effect_flipbook.py build OUT --name mxl_fx_psiorb --art missiles/psiorb --mode loop
        [--scale 2] [--method lanczos | esrgan:<model> --esrgan EXE | mix:<share>:<method> | blur:<px>:<method>]
        [--colour auto|ramp|rgb] [--tint R,G,B] [--zoffset N] [--light LIGHT,RED,GREEN,BLUE] [--cache DIR]
        [--missiles bioneticmover,... --missiles-json BASE.json]

OUT is laid out like the mod's `data` folder. `--missiles` writes OUT/hd/missiles/missiles.json: BASE with those rows
pointing at the new definition. tools/effects_classic.py is the build step that uses this (data/hd-effects-classic.json).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import d2r_texture  # noqa: E402
import effect_sheet  # noqa: E402
import fxpaths  # noqa: E402
import hd_cbvm as cb  # noqa: E402
import hd_particles as hp  # noqa: E402

TEMPLATE = "data/hd/vfx/particles/missiles/chill_blood_puff/chill_blood_puff.particles"
T_WHITE = "data/hd/vfx/textures/default/White.texture"
LIGHT_TEMPLATE = "data/hd/vfx/particles/env/common/generic/vfx_candle_light.particles"
TEX_DIR = "data/hd/vfx/textures/mxl/flipbook/"
PARTICLE_DIR = "data/hd/vfx/particles/mxl/flipbook/"
RAMP_DIR = "data/hd/vfx/textures/gradient/mxl_fb_"
FPS = 25.0                      # classic frames per second (missiles.txt AnimSpeed 16 = one frame per game frame)
PX_PER_UNIT = 8 * math.sqrt(2)  # classic pixels per world unit across the screen (tools/monster_card.py: u = 8 (X - Z))
PX_PER_HEIGHT = 8 * math.sqrt(1.5)  # classic pixels per world unit of height
LOOP_LIFE = 600.0               # seconds a looping particle lives (the definition kills it with the missile)
MID_LIFE = 0.2                  # the template's emitter particle: gone before it would emit a second sprite (1 per second)
RESPONSE = (2.0, 1.5)           # what the game adds to the screen for a ramp value v (0..1): about 2.0 * v ** 1.5 (measured)
SIZE_FIT = 1.125                # measured: a billboard draws this much smaller than PX_PER_UNIT says
MULTI_HUE = 2.0                 # ramp_error (rms, 0..255) above which one ramp cannot carry the art: three layers instead
LIGHT_REACH = 3.0               # world units of light reach per missiles.txt `Light` unit (fits classic's light on the ground)
UPSCALE_PAD = 8                 # black pixels round a frame given to a scaler (its filter needs a neighbourhood)
MARGIN = 2                      # black classic pixels round the art in a cell (no neighbour bleeds in when filtered)
LAYER, FIELD, INPUT = "CLayerCompileCache", "CLayerCompileCacheField", "CLayerCompileCacheRendererParticleInput"


# ---------------------------------------------------------------- picture
def additive_frames(art: str, act: int = 1) -> dict:
    """Direction 0 of a classic animation on black. -> {'frames': [(h, w, 3) uint8], 'box': (x0, y0, w, h), 'dirs': n}."""
    a = effect_sheet.load(art, act)
    frames = [f[..., :3] * (f[..., 3:] > 0) for f in a["dirs"][0]]
    return {"frames": frames, "box": a["box"], "dirs": len(a["dirs"]), "bytes": a["bytes"], "raw": Path(a["path"]).read_bytes()}


def upscale(frames: list, scale: int, method: str, esrgan: dict | None = None, inner=None) -> list:
    """Each (h, w, 3) picture on black, `scale` times larger. Black stays black: the result is multiplied by the picture's
    own coverage (drawn pixels, Lanczos, widened by a pixel), so a model's noise in the empty part adds no haze.
    `inner(method)` gives the pictures a compound method is made of (default: this function)."""
    inner = inner or (lambda m: upscale(frames, scale, m, esrgan))
    from PIL import Image, ImageFilter
    if scale == 1:
        return list(frames)
    if method.startswith("mix:"):                             # mix:<share>:<method>: that share of `method`, the rest Lanczos
        _m, share, base = method.split(":", 2)
        a, b = inner(base), inner("lanczos")
        w = float(share)
        return [np.clip(x.astype(np.float32) * w + y.astype(np.float32) * (1.0 - w) + 0.5, 0, 255).astype(np.uint8)
                for x, y in zip(a, b)]
    if method.startswith("blur:"):                            # blur:<radius in output pixels>:<method>
        _m, radius, base = method.split(":", 2)
        return [np.asarray(Image.fromarray(x, "RGB").filter(ImageFilter.GaussianBlur(float(radius)))) for x in inner(base)]
    pad = UPSCALE_PAD
    padded = [np.pad(f, ((pad, pad), (pad, pad), (0, 0))) for f in frames]
    if method == "lanczos":
        big = [np.asarray(Image.fromarray(f, "RGB").resize((f.shape[1] * scale, f.shape[0] * scale), Image.LANCZOS)) for f in padded]
    else:                                                     # a model: the sprite upscaler of the monster tools, when present
        try:
            import monster_upscale as mu
        except ImportError:
            raise ValueError("upscale method %r needs tools/monster_upscale.py; this checkout builds `lanczos` only" % method) from None
        big = mu.colour_up(padded, scale, method, esrgan)
    out = []
    for f, b in zip(frames, big):
        b = b[pad * scale:-pad * scale, pad * scale:-pad * scale].astype(np.float32)
        drawn = (f.max(axis=2) > 0).astype(np.uint8) * 255
        wide = np.asarray(Image.fromarray(drawn, "L").filter(ImageFilter.MaxFilter(3))
                          .resize((f.shape[1] * scale, f.shape[0] * scale), Image.LANCZOS)).astype(np.float32) / 255.0
        cover = np.clip(wide * 2.0, 0.0, 1.0)[..., None]
        out.append(np.clip(b * cover + 0.5, 0, 255).astype(np.uint8))
    return out


def upscale_cached(frames: list, scale: int, method: str, esrgan: dict | None, cache: Path | None, source: bytes) -> list:
    """`upscale`, kept in `cache` under the hash of the classic file, the scale and the method (a model's run is the slow part
    of a build: 28 frames take the GPU about 20 s)."""
    if cache is None or scale == 1:
        return upscale(frames, scale, method, esrgan)
    if method.startswith(("mix:", "blur:")):                  # made from cached pictures, cheap to redo
        return upscale(frames, scale, method, esrgan, lambda m: upscale_cached(frames, scale, m, esrgan, cache, source))
    key = hashlib.sha256(source + ("|%d|%s|%d" % (scale, method, len(frames))).encode()).hexdigest()[:24]
    f = Path(cache) / (key + ".npz")
    if f.is_file():
        with np.load(f) as z:
            return [z["f%d" % i] for i in range(len(frames))]
    big = upscale(frames, scale, method, esrgan)
    f.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, **{"f%d" % i: b for i, b in enumerate(big)})
    return big


def levels(rgb: np.ndarray, how: str = "mean") -> np.ndarray:
    """A picture's one-channel level (uint8): the `mean` of a pixel's channels (deep blue and white, both with a channel
    at 255, get different levels), its brightest channel (`max`) or one channel (`r`, `g`, `b`: three layers, one per
    channel, add up to a picture of any hues). Black is level 0 either way."""
    px = rgb[..., :3].astype(np.float64)
    v = px[..., "rgb".index(how)] if how in ("r", "g", "b") else px.mean(axis=-1) if how == "mean" else px.max(axis=-1)
    return np.clip(np.ceil(v), 0, 255).astype(np.uint8)


def own_ramp(rgb: np.ndarray, how: str = "mean") -> np.ndarray:
    """(256, 4) RGBA: for each level the mean colour of the picture's pixels at that level, empty levels filled in between
    their neighbours; level 0 is black. With the level as the texture and this as the gradient, a picture whose colours
    lie on one line from dark to bright (one hue, or blue to white) comes back in its own colours."""
    px = rgb.reshape(-1, 3).astype(np.float64)
    v = levels(rgb, how).reshape(-1).astype(np.int64)
    n = np.bincount(v, minlength=256).astype(np.float64)
    ramp = np.zeros((256, 4), np.float64)
    have = np.flatnonzero(n > 0)
    for c in range(3):
        mean = np.bincount(v, weights=px[:, c], minlength=256) / np.maximum(n, 1)
        ramp[:, c] = np.interp(np.arange(256), have, mean[have])
    ramp[0, :3] = 0
    ramp[:, 3] = 255
    return np.clip(ramp + 0.5, 0, 255).astype(np.uint8)


def ramp_error(rgb: np.ndarray, ramp: np.ndarray, how: str = "mean") -> float:
    """Root mean square difference (0-255, over the drawn pixels) between a picture and its level-through-ramp copy."""
    px = rgb.reshape(-1, 3).astype(np.float64)
    v = levels(rgb, how).reshape(-1).astype(np.int64)
    d = (ramp[v, :3].astype(np.float64) - px)[v > 0]
    return float(np.sqrt((d ** 2).mean())) if len(d) else 0.0


def grid_for(n: int, cell: int, most: int = 4096) -> tuple[int, int]:
    """(columns, rows) for n square cells: the squarest grid no wider than `most` pixels."""
    cols = max(1, min(n, most // cell, math.ceil(math.sqrt(n))))
    return cols, math.ceil(n / cols)


def atlas(frames: list, scale: int) -> tuple[np.ndarray, tuple[int, int], int]:
    """Frames (all the same size) centred in square cells, row by row from the top left. -> (RGBA, (cols, rows), cell px).
    Alpha is opaque: the layer adds the colour to the scene, black adds nothing."""
    h, w = frames[0].shape[:2]
    cell = max(h, w) + 2 * MARGIN * scale
    cell += (-cell) % 4                                   # BC3 blocks: a cell edge never shares a block
    cols, rows = grid_for(len(frames), cell)
    out = np.zeros((rows * cell, cols * cell, 4), np.uint8)
    out[..., 3] = 255
    for i, f in enumerate(frames):
        y, x = (i // cols) * cell + (cell - h) // 2, (i % cols) * cell + (cell - w) // 2
        out[y:y + h, x:x + w, :3] = f
    return out, (cols, rows), cell


# ---------------------------------------------------------------- particle file
def _u32s(pf: hp.ParticleFile, i: int) -> dict[int, tuple[int, int]]:
    """{field id: (value, offset)} of an object whose fields are all one u32 (fields, renderer inputs)."""
    _c, off, size = pf.objects[i]
    n = struct.unpack_from("<H", pf.raw, off + 5)[0]
    out, q = {}, off + 7
    for _ in range(n):
        out[struct.unpack_from("<H", pf.raw, q)[0]] = (struct.unpack_from("<I", pf.raw, q + 2)[0], q + 2)
        q += 6
    if q != off + size:
        raise ValueError(f"object {i + 1} ({pf.cls(i)}) is not a list of u32 fields")
    return out


def _refs(pf: hp.ParticleFile, i: int, fid: int, cls: str) -> list[int]:
    """The object numbers (1-based) a layer lists under field `fid`: found as (u16 fid, u32 n, n numbers of objects of
    class `cls`). The layer's other fields are not decoded."""
    _c, off, size = pf.objects[i]
    b = bytes(pf.raw[off:off + size])
    for q in range(7, size - 6):
        if struct.unpack_from("<H", b, q)[0] != fid:
            continue
        n = struct.unpack_from("<I", b, q + 2)[0]
        if not 0 < n < 256 or q + 6 + 4 * n > size:
            continue
        refs = struct.unpack_from(f"<{n}I", b, q + 6)
        if all(0 < r <= len(pf.objects) and pf.cls(r - 1) == cls for r in refs):
            return list(refs)
    return []


def _consts(pf: hp.ParticleFile, i: int) -> tuple[int, int]:
    """(offset, count) of a layer's constant block: field 0, 16 bytes per entry, two entries per constant stream (the
    streams a spawn script declares and never stores: the life, plain renderer inputs)."""
    _c, off, _size = pf.objects[i]
    if struct.unpack_from("<H", pf.raw, off + 7)[0] != 0:
        return 0, 0
    return off + 13, struct.unpack_from("<I", pf.raw, off + 9)[0]


def _set_const(pf: hp.ParticleFile, layer: int, k: int, was, new) -> None:
    at, n = _consts(pf, layer)
    if 2 * k + 1 >= n:
        raise ValueError(f"layer {layer + 1} has no constant {k}")
    for e in (2 * k, 2 * k + 1):
        old = struct.unpack_from("<4f", pf.raw, at + 16 * e)
        if was is not None and not all(abs(a - b) < 1e-4 for a, b in zip(old, was)):
            raise ValueError(f"layer {layer + 1} constant {k} is {old}, not the template's {was}")
        struct.pack_into("<4f", pf.raw, at + 16 * e, *new)


def _with_value(pf: hp.ParticleFile, p: hp.Prop, value: bytes) -> bytes:
    """A property object's bytes with a stored value (field 2) set or added."""
    _c, off, _size = pf.objects[p.obj]
    cls = struct.unpack_from("<I", pf.raw, off + 1)[0]
    size = {0: 4, 1: 4, 2: 16, 3: 4}
    fields = {fid: bytes(pf.raw[at:at + size[fid]]) for fid, at in pf.fields(p.obj)}
    fields[2] = value
    return b"\x20" + struct.pack("<IH", cls, len(fields)) + b"".join(struct.pack("<H", f) + fields[f] for f in sorted(fields))


def _lines(s: cb.Script) -> tuple[list[str], list[str]]:
    """A script's text as (directive lines without the constants, instruction lines without comments)."""
    head, code = [], []
    for raw in cb.script_text(s).splitlines():
        if raw.startswith(".const") or not raw.strip() or raw.startswith(";"):
            continue
        (head if raw.startswith(".") else code).append(raw if raw.startswith(".") else raw.split(";")[0].rstrip())
    return head, code


def _script(s: cb.Script, head: list[str], consts: list[str], code: list[str]) -> cb.Script:
    text = "\n".join(head + [f".const {k} {c}" for k, c in enumerate(consts)] + [""] + code) + "\n"
    new = cb.script_parse(text, s.obj)
    new.head[0] = len(new.code)          # the first header word of every stock script is its instruction count
    new.pad = b""
    return new


def particles(template: bytes, texture: str, grid: tuple[int, int], frames: int, mode: str, size: float,
              intensity: float = 1.0, gain=(1.0, 1.0, 1.0, 1.0), fps: float = FPS, loop_life: float = LOOP_LIFE,
              gradient: str | None = None, alpha_remap: bool = False, cursor=(0.0, 0.0),
              alpha_cursor=None, dissolve: bool | None = None) -> bytes:
    """TEMPLATE as a flipbook of `frames` cells of `texture` (`grid` columns x rows): see the module text."""
    pf = hp.ParticleFile(template)
    scripts = {s.obj: s for s in cb.scripts(pf)}
    new: dict[int, bytes] = {}
    done = 0
    life = loop_life if mode == "loop" else frames / fps
    for li in [i for i in range(len(pf.objects)) if pf.cls(i) == LAYER]:
        rends = _refs(pf, li, 8, hp.RENDERER)
        progs = _refs(pf, li, 9, cb.BLOB)
        if not rends:
            # the emitter between the root and the sprite layer: it has a life (a constant block) and kills itself
            if _consts(pf, li)[1] == 2 and any("self.kill_bool_pCtxS" in (scripts[p - 1].fn_names or []) for p in progs):
                _set_const(pf, li, 0, (1.0,) * 4, (1.0 / MID_LIFE,) * 4)
            continue
        r = next(x for x in pf.renderers() if x.obj == rends[0] - 1)
        # the renderer: our atlas as the colour, no mask, gradient or alpha remap, the grid, the flipbook switch
        pf.set_texture(r, "Blend.TextureBase", texture)
        pf.set_texture(r, "AlphaMask.Mask", T_WHITE)
        pf.set_property(r, "AlphaMask.AtlasAlphaOnly", False)
        for switch, on in (("GradientRemap", gradient is not None), ("AlphaRemap", alpha_remap)):
            sw = r.props[switch]
            pf.raw[sw.value_at:sw.value_at + 16] = hp.ON if on else hp.OFF
        if dissolve is not None:
            sw = r.props["AlphaRemap.Dissolve"]
            pf.raw[sw.value_at:sw.value_at + 16] = hp.ON if dissolve else hp.OFF
        if gradient is not None:
            pf.set_texture(r, "GradientRemap.GradientMap", gradient)
            _set_const(pf, li, 4, None, (cursor[0], cursor[1], cursor[0], cursor[1]))
        sub = r.props["Atlas.SubDiv"]
        pf.raw[sub.value_at:sub.value_at + 16] = struct.pack("<4i", grid[0], grid[1], 1, 1)
        new[r.props["Atlas.Flipbook"].obj] = _with_value(pf, r.props["Atlas.Flipbook"], hp.ON)
        # constants: life, base UV scale and offset, physical intensity
        _set_const(pf, li, 0, (1.0,) * 4, (1.0 / life,) * 4)
        _set_const(pf, li, 1, (0.7, 0.7, 0.0, 0.0), (1.0, 1.0, 0.0, 0.0))
        _set_const(pf, li, 3, (2000.0,) * 4, (intensity,) * 4)
        # inputs: the frame number comes from the stream the evolve script already writes (the rotation's), and the
        # rotation from the old frame stream, which the spawn script now sets to 0
        fields = _refs(pf, li, 2, FIELD)
        inputs = {}
        for fid, at in pf.fields(r.obj):
            if fid == 1:
                n = struct.unpack_from("<I", pf.raw, at)[0]
                for ref in struct.unpack_from(f"<{n}I", pf.raw, at + 4):
                    u = _u32s(pf, ref - 1)
                    inputs[pf.strings[u[2][0]] if 2 in u else u.get(0, (0, 0))[0]] = u[1]
        (frame_field, frame_at), (rot_field, rot_at) = inputs["Atlas.TextureID"], inputs[6]
        # the template feeds its contributions, exposure multiplier and monster fade from the 1/life stream (1.0 in the
        # template: the baker merged equal constants), so a longer life would dim the picture; they move to the physical
        # intensity's stream (an input with no visible effect), which then holds the exposure
        inv_life = next(k for k, f in enumerate(fields) if _u32s(pf, f - 1)[0][0] == 0x80000001)
        exposure_field = inputs["Exposure.PhysicalIntensity"][0]
        for key, (field, at) in inputs.items():
            if field == inv_life:
                struct.pack_into("<I", pf.raw, at, exposure_field)
        name = lambda k: "%X" % ((_u32s(pf, fields[k] - 1)[0][0] & 0xFFFF) - 7)  # noqa: E731  (stream names are hex numbers)
        frame_name, rot_name = name(frame_field), name(rot_field)
        struct.pack_into("<I", pf.raw, frame_at, rot_field)
        struct.pack_into("<I", pf.raw, rot_at, frame_field)
        spawn, evolves = scripts[progs[0] - 1], [scripts[p - 1] for p in progs[1:]]
        # spawn: a fixed size, frame stream (now the rotation) 0
        head, code = _lines(spawn)
        consts = [cb._const_text(c) for c in spawn.consts]
        for k, c in enumerate(consts):                      # the script's own copies of the layer's constant streams
            if c.startswith("f 0.69999") and c.split()[3] == "0.0":
                consts[k] = "f 1.0 1.0 0.0 0.0"
            elif c.startswith("f 2000.0 "):
                consts[k] = "f %r" % float(intensity)
            elif c.startswith("f -0.05000") and gradient is not None:
                consts[k] = "f %r %r" % (float(cursor[0]), float(cursor[1]))
        size_at = next(k for k, ln in enumerate(code) if ln.startswith("st ") and ln.endswith("@%d" % spawn.ext("0")))
        zero_at = next(k for k, ln in enumerate(code) if ln.startswith("st ") and ln.endswith("@%d" % spawn.ext(frame_name)))
        m = re.search(r"<- a:(c\d+)\.float, a:(c\d+)\.float", code[size_at - 1])
        z = re.search(r"<- a:(c\d+)\.float, a:(c\d+)\.float", code[zero_at - 1])
        if not m or not z:
            raise ValueError("the template's spawn script does not set the size and the frame from rand()")
        consts.append("f %r" % size)
        code[size_at - 1] = code[size_at - 1].replace(m.group(0), "<- a:c%d.float, a:c%d.float" % ((len(consts) - 1,) * 2))
        consts.append("f 0.0")
        code[zero_at - 1] = code[zero_at - 1].replace(z.group(0), "<- a:c%d.float, a:c%d.float" % ((len(consts) - 1,) * 2))
        new[spawn.obj] = cb.payload(pf, _script(spawn, head, consts, code))
        # evolve: frame number, colour, the template's alpha cursor, position on the emitter, the rendering switch
        for ev in evolves:
            head, code = _lines(ev)
            e = ev.ext
            keep = [k for k, ln in enumerate(code) if ln.startswith("st ") and ln.endswith("@%d" % e("E"))][0]
            stock_cursor = code[keep - 2:keep + 1]                       # call sampler, swz, st: kept as they are
            if not stock_cursor[0].startswith("call") or "s0.float" not in stock_cursor[0]:
                raise ValueError("the template's evolve script is not the expected one")
            consts = ["f 0.0", "f %r" % (life * fps / frames if mode == "loop" else float(frames)), "i 17",
                      "f %r" % float(frames if mode == "loop" else frames - 0.01), "f " + " ".join(repr(float(v)) for v in gain)]
            body = ["prlg",
                    "ld s0.float, @%d" % e("self.lifeRatio"),
                    "mul s1.float, s0.float, c1.float"]
            body += ["mfn1.frac s1.float, s1.float", "mul s1.float, s1.float, c3.float"] if mode == "loop" else \
                    ["mfn2.min s1.float, s1.float, c3.float"]
            body += ["st s1.float, @%d" % e(rot_name),
                     "mul s2.float, s0.float, c0.float",
                     "swz.d9.6d.11 s2.float4, s2.float",
                     "add s2.float4, s2.float4, c4.float4",
                     "st s2.float4, @%d" % e("D")]
            if alpha_cursor is None:
                body += stock_cursor
            else:
                consts.append("f %r %r" % (float(alpha_cursor[0]), float(alpha_cursor[1])))
                body += ["mul s2.float, s0.float, c0.float",
                         "swz.1e.20.00 s2.float2, s2.float",
                         "add s2.float2, s2.float2, c5.float2",
                         "st s2.float2, @%d" % e("E")]
            body += ["ld s2.class, @%d" % e("ParticleContextS"),
                     "call.6.-1 #0 s0.float3 <- 8:c0.float3!, 0:c2.int, 8:s2.class",
                     "st s0.float3, @%d" % e("B"),
                     "ld u0.class, @%d" % e("ParticleContextI"),
                     "call.6.-1 #1 u1.bool <- 8:u0.class",
                     "st u1.bool, @%d" % e("F"),
                     "eplg"]
            for want in ("call.6.-1 #0 s0.float3 <- 8:c0.float3!, 0:c2.int, 8:s2.class", "call.6.-1 #1 u1.bool <- 8:u0.class"):
                if want not in code:
                    raise ValueError("the template's evolve script is not the expected one: no %r" % want)
            new[ev.obj] = cb.payload(pf, _script(ev, head, consts, body))
        done += 1
    if not done:
        raise ValueError("the template has no layer with a renderer")
    return cb.rebuild(pf, new)


def point_light(template: bytes, rgb, reach: float, power: float = 250.0) -> bytes:
    """LIGHT_TEMPLATE (D2R's candle: one point light that follows the emitter while the effect runs) with a steady
    colour (0..1 per channel), reach (world units) and power instead of the candle's flickering orange."""
    pf = hp.ParticleFile(template)
    scripts = {s.obj: s for s in cb.scripts(pf)}
    new: dict[int, bytes] = {}
    colour = tuple(float(v) for v in rgb) + (1.0,)
    for li in [i for i in range(len(pf.objects)) if pf.cls(i) == LAYER]:
        rends = _refs(pf, li, 8, hp.RENDERER)
        if not rends:
            continue
        r = next(x for x in pf.renderers() if x.obj == rends[0] - 1)
        if "Light" not in r.props:
            raise ValueError("the light template's renderer is not a light")
        _set_const(pf, li, 1, (0.89, 0.324, 0.0509, 1.0), colour)
        _set_const(pf, li, 2, (15.0,) * 4, (float(reach),) * 4)
        progs = _refs(pf, li, 9, cb.BLOB)
        for k, prog in enumerate(progs):
            sc = scripts[prog - 1]
            head, code = _lines(sc)
            consts = [cb._const_text(c) for c in sc.consts]
            for n, c in enumerate(consts):
                if k == 0 and c.startswith("f 0.89000"):
                    consts[n] = "f " + " ".join(repr(v) for v in colour * 2)
                elif k == 0 and c.startswith("f 15.0 "):
                    consts[n] = "f %r" % float(reach)
                elif k and c.startswith("f 250.0 "):
                    consts[n] = "f %r" % float(power)
                elif k and c.startswith("f 50.0000"):
                    consts[n] = "f 0.0"                      # no flicker
            new[sc.obj] = cb.payload(pf, _script(sc, head, consts, code))
    if not new:
        raise ValueError("the light template has no layer with a renderer")
    return cb.rebuild(pf, new)


# ---------------------------------------------------------------- definition
def definition(name: str, parts: list[dict], hard_kill: bool, hd_height: bool = True) -> dict:
    """A UnitDefinition whose effect entities are `parts`: {'particle', 'texture', 'pos': (x, y, z)} (y is up)."""
    uid = lambda k: zlib.crc32((name + k).encode())  # noqa: E731
    ents = []
    for k, part in enumerate(parts, 1):
        x, y, z = part["pos"]
        ents.append({"type": "Entity", "name": "entity_vfx%d" % k, "id": uid("vfx%d" % k), "components": [
            {"type": "VfxDefinitionComponent", "name": "component_vfx%d" % k, "filename": part["particle"],
             "hardKillOnDestroy": bool(part.get("hard_kill", hard_kill))},
            {"type": "TransformDefinitionComponent", "name": "component_transform%d" % k,
             "position": {"x": round(x, 3), "y": round(y, 3), "z": round(z, 3)},
             "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}, "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
             "inheritOnlyPosition": False}]})
    uniq = lambda key: [{"path": v} for v in dict.fromkeys(q[key] for q in parts if q.get(key))]  # noqa: E731
    return {"dependencies": {"particles": uniq("particle"), "models": [], "skeletons": [], "animations": [],
                             "textures": uniq("texture"), "physics": [], "json": [], "variantdata": [],
                             "objecteffects": [], "other": []},
            "type": "UnitDefinition", "name": name,
            "entities": [
                {"type": "Entity", "name": "entity_root", "id": uid("root"), "components": [
                    {"type": "UnitRootComponent", "name": "component_root", "state_machine_filename": "",
                     "doNotInheritRotation": False, "rotationOverride": {"x": 0.0, "y": 0.3826834, "z": 0.0, "w": 0.9238795},
                     "doNotUseHDHeight": not hd_height, "hideAllMeshWhenInOpenedMode": False, "onCreateEventName": "",
                     "animations": []}]}] + ents}


def build(out: Path, name: str, art: str, mode: str, scale: int = 2, method: str = "lanczos", esrgan: dict | None = None,
          intensity: float = 1.0, gain: float = 1.0, size: float = 1.0, lift: float | None = None, act: int = 1,
          template: bytes | None = None, cache: Path | None = None, loop_life: float = LOOP_LIFE,
          kind: str = "rgb", colour=None, ramp: str | np.ndarray | None = None, alpha_remap: bool = False,
          cursor=(0.0, 0.0), alpha_cursor=None, dissolve: bool | None = None, response=RESPONSE,
          level: str = "mean", tint=(1.0, 1.0, 1.0), write_definition: bool = True) -> dict:
    """Writes the texture, the particle file and the definition of ONE layer of an animation under `out` (`effect` makes
    a whole one). -> facts (sizes, bytes)."""
    src = additive_frames(art, act)
    x0, y0, w, h = src["box"]
    big = upscale_cached(src["frames"], scale, method, esrgan, cache, src["raw"])
    pixels, grid, cell = atlas(big, scale)
    key = name.lower()
    texture, particle = TEX_DIR + key + ".texture", PARTICLE_DIR + key + ".particles"
    dest = out / texture[len("data/"):]
    dest.parent.mkdir(parents=True, exist_ok=True)
    gradient = None
    value = levels(pixels, level)
    if kind == "rgb":
        d2r_texture.write_bc3(dest, pixels, 1)
    elif kind == "grey":
        d2r_texture.write_bc3(dest, np.dstack([value, value, value, pixels[..., 3]]), 1)
    elif kind == "index":
        d2r_texture.write_bc4(dest, value, 1)
    else:
        raise ValueError("no texture kind %r" % kind)
    if ramp is not None:
        strip = own_ramp(pixels[..., :3], level) if isinstance(ramp, str) and ramp == "own" else np.asarray(ramp)
        strip = strip.astype(np.float64)
        top = 255.0 * (response[0] if response else 1.0)      # a tint may lift a colour up to what the screen can show
        strip[:, :3] = np.clip(strip[:, :3] * np.asarray(tint, np.float64), 0, top)
        if response:                                           # so that the screen gets the classic colour added
            k, power = response
            strip[:, :3] = 255.0 * (strip[:, :3] / 255.0 / k) ** (1.0 / power)
        strip = np.clip(strip + 0.5, 0, 255).astype(np.uint8)
        gradient = RAMP_DIR + key + ".texture"
        d2r_texture.write_rgba(out / gradient[len("data/"):], np.repeat(strip[None, :, :], 16, axis=0), 1)
    half = cell / scale / 2.0 / PX_PER_UNIT * size              # the billboard's Size is its half edge
    up = -(y0 + h / 2.0) / PX_PER_HEIGHT if lift is None else lift   # the box centre's height over the anchor
    data = particles(template or fxpaths.d2r_file(TEMPLATE).read_bytes(), texture, grid, len(big), mode, half, intensity,
                     colour or (gain, gain, gain, 1.0), loop_life=loop_life, gradient=gradient, alpha_remap=alpha_remap,
                     cursor=cursor, alpha_cursor=alpha_cursor, dissolve=dissolve)
    dest_p = out / particle[len("data/"):]
    dest_p.parent.mkdir(parents=True, exist_ok=True)
    dest_p.write_bytes(data)
    if write_definition:
        dj = out / "hd" / "missiles" / (name + ".json")
        dj.parent.mkdir(parents=True, exist_ok=True)
        dj.write_text(json.dumps(definition(name, [{"particle": particle, "texture": texture, "pos": (0.0, up, 0.0)}],
                                            mode == "loop"), separators=(",", ":")), "utf-8")
    raw = dest.read_bytes()
    return {"name": name, "art": art, "mode": mode, "frames": len(big), "directions": src["dirs"], "box": [x0, y0, w, h],
            "scale": scale, "method": method, "grid": list(grid), "cell_px": cell, "atlas_px": [pixels.shape[1], pixels.shape[0]],
            "half_size_world": round(half, 4), "lift_world": round(up, 3), "intensity": intensity, "gain": gain,
            "classic_dcc_bytes": src["bytes"], "texture_bytes": len(raw), "texture_deflated": len(zlib.compress(raw, 9)),
            "particles_bytes": len(data), "particles_deflated": len(zlib.compress(data, 9)),
            "kind": kind, "gradient": gradient,
            "files": [texture, particle] + (["data/hd/missiles/%s.json" % name] if write_definition else [])
            + ([gradient] if gradient else [])}


def hue_spread(frames: list) -> float:
    """How far the art's colours are from one dark-to-bright line (ramp_error of its own ramp, rms, 0..255)."""
    lit = np.concatenate([f.reshape(-1, 3) for f in frames])
    lit = lit[lit.max(axis=1) > 0][None]
    return ramp_error(lit, own_ramp(lit)) if lit.size else 0.0


def light_of(row: dict) -> dict | None:
    """missiles.txt `Light`, `Red`, `Green`, `Blue` -> {'rgb': 0..1 each, 'range': world units}; None without a light."""
    num = lambda k: float(row.get(k) or 0)  # noqa: E731
    if num("Light") <= 0:
        return None
    rgb = tuple(num(k) / 255.0 for k in ("Red", "Green", "Blue"))
    return {"rgb": rgb if max(rgb) > 0 else (1.0, 1.0, 1.0), "range": num("Light") * LIGHT_REACH}


def effect(out: Path, name: str, art: str | None, mode: str = "once", *, scale: int = 2, method: str = "lanczos",
           esrgan: dict | None = None, cache: Path | None = None, colour: str = "auto", tint=(1.0, 1.0, 1.0),
           zoffset: float = 0.0, light: dict | None = None, act: int = 1, light_template: bytes | None = None) -> dict:
    """A whole effect under `out`: the animation `art` (None: a missile without a picture, light only) as one layer
    (`colour` ramp) or three (rgb; auto: by hue_spread), an optional point light ({'rgb', 'range', 'power'?}) and ONE
    definition `name`. `zoffset` is the missiles.txt column. -> facts with every file and the bytes."""
    parts, layers, files, spread = [], [], [], 0.0
    lift = 1.0
    if art:
        src = additive_frames(art, act)
        _x0, y0, _w, h = src["box"]
        lift = (-(y0 + h / 2.0) - zoffset) / PX_PER_HEIGHT
        spread = hue_spread(src["frames"])
        how = colour if colour != "auto" else ("ramp" if spread <= MULTI_HUE else "rgb")
        if how == "ramp":
            todo = [("", "mean", "own", tuple(tint))]
        elif how == "rgb":
            grey = np.dstack([np.arange(256)] * 3 + [np.full(256, 255)])[0].astype(np.uint8)
            todo = [("_" + c, c, grey, tuple(float(tint[k]) if i == k else 0.0 for i in range(3))) for k, c in enumerate("rgb")]
        else:
            raise ValueError("no colour mode %r" % colour)
        for suffix, level, ramp, tn in todo:
            f = build(out, name + suffix, art, mode, scale, method, esrgan, size=SIZE_FIT, lift=lift, act=act, cache=cache,
                      kind="index", ramp=ramp, level=level, tint=tn, write_definition=False)
            parts.append({"particle": f["files"][1], "texture": f["files"][0], "pos": (0.0, f["lift_world"], 0.0)})
            layers.append(f)
            files += f["files"]
    if light:
        lp = PARTICLE_DIR + name.lower() + "_light.particles"
        dest = out / lp[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(point_light(light_template or fxpaths.d2r_file(LIGHT_TEMPLATE).read_bytes(), light["rgb"],
                                     light["range"], light.get("power", 250.0)))
        parts.append({"particle": lp, "texture": None, "pos": (0.0, 1.0, 0.0)})
        files.append(lp)
    if not parts:
        raise ValueError("an effect needs a picture or a light")
    dj = out / "hd" / "missiles" / (name + ".json")
    dj.parent.mkdir(parents=True, exist_ok=True)
    dj.write_text(json.dumps(definition(name, parts, True), separators=(",", ":")), "utf-8")
    files.append("data/hd/missiles/%s.json" % name)
    raw = [(out / f[len("data/"):]).read_bytes() for f in files]
    return {"name": name, "art": art, "mode": mode, "scale": scale, "method": method, "layers": len(layers),
            "hue_spread": round(spread, 2), "lift_world": round(lift, 3), "light": light, "files": files,
            "bytes": sum(len(r) for r in raw), "deflated": sum(len(zlib.compress(r, 9)) for r in raw),
            "classic_dcc_bytes": layers[0]["classic_dcc_bytes"] if layers else 0, "layer_facts": layers}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("build",))
    ap.add_argument("out")
    ap.add_argument("--name", required=True)
    ap.add_argument("--art", required=True, help="missiles/<CelFile> or overlays/<Filename>")
    ap.add_argument("--mode", choices=("loop", "once"), required=True)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--method", default="lanczos")
    ap.add_argument("--esrgan", help="realesrgan-ncnn-vulkan.exe (for esrgan:<model>)")
    ap.add_argument("--colour", choices=("auto", "ramp", "rgb"), default="auto", help="one ramp layer or three channel layers")
    ap.add_argument("--tint", default="1,1,1", help="R,G,B gain on the classic colour")
    ap.add_argument("--zoffset", type=float, default=0.0, help="missiles.txt zoffset of the row")
    ap.add_argument("--light", help="missiles.txt Light,Red,Green,Blue of the row")
    ap.add_argument("--cache", help="folder that keeps the upscaled frames between builds")
    ap.add_argument("--missiles", help="comma-separated missiles.txt names to point at the definition")
    ap.add_argument("--missiles-json", help="the missiles.json to start from (default: OUT's, else D2R's)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    esr = {"exe": args.esrgan} if args.esrgan else None
    lamp = light_of(dict(zip(("Light", "Red", "Green", "Blue"), args.light.split(",")))) if args.light else None
    facts = effect(out, args.name, args.art, args.mode, scale=args.scale, method=args.method, esrgan=esr,
                   cache=Path(args.cache) if args.cache else None, colour=args.colour,
                   tint=tuple(float(v) for v in args.tint.split(",")), zoffset=args.zoffset, light=lamp)
    if args.missiles:
        mj = out / "hd" / "missiles" / "missiles.json"
        base = mj if mj.exists() else Path(args.missiles_json) if args.missiles_json else fxpaths.d2r_file("data/hd/missiles/missiles.json")
        table = json.loads(Path(base).read_text("utf-8"))
        for m in args.missiles.split(","):
            table[m.strip().lower()] = args.name
        mj.write_text(json.dumps(table, indent=1), "utf-8")
    print(json.dumps(facts, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
