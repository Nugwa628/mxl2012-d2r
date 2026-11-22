"""The WebGPU renderer (wgpu-py: BSD-2-Clause, bundles wgpu-native under MIT / Apache-2.0).

Offscreen only. Colour targets are linear rgba16float with premultiplied alpha, MSAA resolved on the GPU; the CPU box-filters
supersampled pixels, then encodes sRGB (straight alpha, or composited over a background). Images larger than the GPU's
texture limit are rendered as tiles of exact sub-frusta (camera.OrthoCamera.matrix) and stitched or streamed to a PNG.

`probe()` reports the adapter (name, backend, limits, sample counts) and renders one triangle to prove the read-back.
"""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import gr2, tiling
from .camera import rot_y

SHADER = Path(__file__).with_name("shaders.wgsl")
PASSES = {"lit": 0, "albedo": 1, "normals": 2, "depth": 3, "wire": 4, "unlit": 5, "glow": 6,
          "orm_ao": 7, "orm_rough": 8, "orm_metal": 9, "orm_spec": 10, "height": 11}   # height: world y / 20 (grey)
SRGB_PASSES = {"lit", "albedo", "unlit", "glow"}
RIG_PASSES = {"lit", "glow"}           # passes a light rig's exposure and tone apply to (the others show data)
FLOATS = 15         # pos 3, nrm 3, tan 4, uv 2, bary 3


def _wgpu():
    import wgpu
    return wgpu


@dataclass
class Light:
    """Uncalibrated scene light (linear rgb). Defaults: a cool night key from the upper left of the screen."""
    ambient: tuple = (0.42, 0.46, 0.50)
    key_dir: tuple = (-0.55, 0.75, 0.35)        # towards the light, world axes
    key_col: tuple = (0.95, 1.00, 1.08)
    env_col: tuple = (0.30, 0.34, 0.38)
    glow_gain: float = 1.0
    spec_gain: float = 1.0
    nrm_green: float = 1.0                     # sign of the normal map's green (y) channel
    points: tuple = ()                         # point lights: dicts pos (x, y, z), radius, color (rgb x power), atten
    classes: dict = field(default_factory=dict)  # light class of a draw ('unit', 'world') -> overrides of ambient, key_dir,
    #                                            key_col, env_col and point_gain (scales every point light's colour)
    floor_clip: float = 1.0                    # 1: nothing below y = 0 is drawn (a unit alone); 0 for scenes
    fog: tuple = (0.0, 0.0, 0.0, 0.0)          # depth fog: rgb colour, density f; lit = lit x (1 - f) + colour x f

    def as_dict(self):
        d = {k: getattr(self, k) for k in ("ambient", "key_dir", "key_col", "env_col", "glow_gain", "spec_gain", "nrm_green")}
        if self.points:
            d["points"] = [dict(p) for p in self.points]
        if self.classes:
            d["classes"] = {k: dict(v) for k, v in self.classes.items()}
        if self.floor_clip != 1.0:
            d["floor_clip"] = self.floor_clip
        if any(self.fog):
            d["fog"] = list(self.fog)
        return d

    def for_class(self, cls: str) -> "Light":
        """This light as a draw of light class `cls` sees it (the class's overrides applied)."""
        o = self.classes.get(cls) if cls else None
        if not o:
            return self
        from dataclasses import replace
        kw = {k: tuple(v) for k, v in o.items() if k in ("ambient", "key_dir", "key_col", "env_col")}
        g = float(o.get("point_gain", 1.0))
        pts = tuple(p if p.get("directional") else dict(p, color=[c * g for c in p["color"]]) for p in self.points) \
            if g != 1.0 else self.points
        return replace(self, points=pts, **kw)


TEX_CACHE_BYTES = 3 << 29   # the texture cache's source arrays (and their GPU copies) before it is emptied
MAX_POINTS = 32
UBUF_BYTES = 1280
FOG_AT = 304            # floats: fog rgb x f, f; then p3 (terrain map corner, size), p4 (layer repeat, layers, sharpness)


def pack_points(points) -> np.ndarray:
    """p2 and the point-light array of the uniform block (floats 44..303)."""
    u = np.zeros(4 + 8 * MAX_POINTS, np.float32)
    pts = list(points)[:MAX_POINTS]
    u[0] = len(pts)
    for i, p in enumerate(pts):
        o = 4 + 8 * i
        u[o:o + 3] = p["pos"]
        u[o + 3] = p["radius"]
        u[o + 4:o + 7] = p["color"]
        u[o + 7] = p.get("atten", 1.0)
    return u


def pick_points(points, centre, rad):
    """At most MAX_POINTS of `points` for a draw whose world bounds are the sphere (centre, rad): every directional term,
    then the local lights that reach the sphere, nearest first. A scene may hold any number of lights this way."""
    pts = list(points)
    if len(pts) <= MAX_POINTS:
        return pts
    out = [p for p in pts if p.get("directional")]
    loc = []
    for p in pts:
        if p.get("directional"):
            continue
        d = float(np.linalg.norm(np.asarray(p["pos"], float) - centre))
        if d < float(p["radius"]) + rad:
            loc.append((d - float(p["radius"]), p))
    loc.sort(key=lambda t: t[0])
    return (out + [p for _d, p in loc])[:MAX_POINTS]


def srgb_encode(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1.0 / 2.4) - 0.055)


def srgb_decode(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def box_down(a: np.ndarray, ss: int) -> np.ndarray:
    if ss == 1:
        return a
    h, w = a.shape[0] // ss, a.shape[1] // ss
    return a[:h * ss, :w * ss].reshape(h, ss, w, ss, -1).mean((1, 3))


def to_uint8(lin: np.ndarray, pass_name: str, bg=None, encode=None) -> np.ndarray:
    """Linear premultiplied RGBA (float) -> 8-bit RGBA. bg None: straight alpha; bg (h, w, 3) or (3,) linear: composited.
    `encode(linear rgb) -> display sRGB` (a light rig's exposure and tone) replaces the plain sRGB encode of the lit and
    glow passes; the unit is then composited over bg in linear display light."""
    c, a = lin[..., :3], np.clip(lin[..., 3:4], 0.0, 1.0)
    img = getattr(getattr(encode, "__self__", None), "encode_image", None) if pass_name in RIG_PASSES else None
    da = img(lin) if img is not None else None      # a rig with bloom: whole-image encode (rig.Rig.encode_image)
    if da is not None:
        disp, a = da
    if encode is not None and pass_name in RIG_PASSES:
        if da is None:
            straight = np.where(a > 1e-6, c / np.maximum(a, 1e-6), 0.0)
            disp = np.clip(encode(straight), 0.0, 1.0)
        if bg is None:
            out = np.concatenate([disp, a], -1)
        else:
            bgl = np.broadcast_to(np.asarray(bg, float), c.shape)
            out = np.concatenate([srgb_encode(srgb_decode(disp) * a + bgl * (1.0 - a)), np.ones_like(a)], -1)
        return np.round(out * 255.0).astype(np.uint8)
    enc = srgb_encode if pass_name in SRGB_PASSES else (lambda x: np.clip(x, 0.0, 1.0))
    if bg is None:
        straight = np.where(a > 1e-6, c / np.maximum(a, 1e-6), 0.0)
        out = np.concatenate([enc(straight), a], -1)
    else:
        bgl = np.broadcast_to(np.asarray(bg, float), c.shape)
        out = np.concatenate([enc(c + bgl * (1.0 - a)), np.ones_like(a)], -1)
    return np.round(out * 255.0).astype(np.uint8)


@dataclass
class Draw:
    vbuf: object
    count: int
    ubuf: object
    bind: object
    layers: list            # [(ubuf, bind)]
    alpha_cut: float
    world: np.ndarray       # (m, 3, 3) world triangles (bounds, depth range, texel density)
    uv_tris: np.ndarray     # (m, 3, 2) texel coordinates of each triangle (texels-per-pixel measure)
    name: str = ""          # mesh name
    part: str = ""          # unit part (entity) name
    material: str = ""      # albedo texture path (the material's identity here)
    layer_names: list = field(default_factory=list)     # name of each self-lit layer, parallel to `layers`
    hidden_body: bool = False                           # body drawn black (it still hides what is behind it)
    light_class: str = "unit"                           # which of Light.classes lights it ('unit', 'world')
    blend: float = 0.0                                  # > 0: alpha-blended material, alpha x blend (D2R AlphaIntensity)
    emissive: float = 0.0                               # EmissiveIntensity: albedo x mask x this, added
    terrain: dict | None = None                         # splat ground: {"p3": (x, z, w, h), "p4": (repeat, layers, sharp)}


@dataclass
class Prepared:
    draws: list
    notes: list = field(default_factory=list)
    pose: dict = field(default_factory=dict)

    def select(self, hide=()) -> "Prepared":
        """Layer toggles: a copy without what `hide` names. Each entry is `mesh:<name>`, `part:<name>`,
        `material:<substring of the albedo path>`, `layer:<self-lit layer name>` (`layer:*` = every layer, the same as
        --no-glow), or `body` (the model drawn black but still hiding what is behind it, its self-lit layers on top: the
        glow pass's convention). Names match without case; `<kind>:*` matches all."""
        hide = [h.lower() for h in hide]
        if not hide:
            return self

        def hit(kind, value):
            v = (value or "").lower()
            for h in hide:
                if not h.startswith(kind + ":"):
                    continue
                arg = h[len(kind) + 1:]
                if arg == "*" or arg == v or (kind == "material" and arg and arg in v):
                    return True
            return False
        out = []
        for d in self.draws:
            if hit("mesh", d.name) or hit("part", d.part) or hit("material", d.material):
                continue
            names = d.layer_names or [""] * len(d.layers)
            keep = [(lb, nm) for lb, nm in zip(d.layers, names) if not hit("layer", nm)]
            out.append(Draw(d.vbuf, d.count, d.ubuf, d.bind, [lb for lb, _n in keep], d.alpha_cut, d.world, d.uv_tris,
                            d.name, d.part, d.material, [n for _l, n in keep], d.hidden_body or "body" in hide,
                            d.light_class, d.blend, d.emissive, d.terrain))
        return Prepared(out, self.notes + ["hidden: %s" % ", ".join(hide)], self.pose)


class Renderer:
    def __init__(self, msaa: int = 4, aniso: int = 1, power: str = "high-performance"):
        wgpu = _wgpu()
        self.wgpu = wgpu
        self.adapter = wgpu.gpu.request_adapter_sync(power_preference=power)
        lim = dict(self.adapter.limits)
        self.max_tex = int(lim["max-texture-dimension-2d"])
        self.device = self.adapter.request_device_sync(required_limits={"max-texture-dimension-2d": self.max_tex})
        self.msaa = int(msaa)
        mod = self.device.create_shader_module(code=SHADER.read_text(encoding="utf-8"))
        T = wgpu.ShaderStage
        tex = {"sample_type": "float", "view_dimension": "2d"}
        self.bgl = self.device.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": T.VERTEX | T.FRAGMENT, "buffer": {"type": "uniform"}},
            {"binding": 1, "visibility": T.FRAGMENT, "sampler": {"type": "filtering"}},
            *[{"binding": b, "visibility": T.FRAGMENT, "texture": tex} for b in range(2, 7)]])
        layout = self.device.create_pipeline_layout(bind_group_layouts=[self.bgl])
        A = wgpu.VertexFormat
        vb = [{"array_stride": FLOATS * 4, "step_mode": "vertex", "attributes": [
            {"format": A.float32x3, "offset": 0, "shader_location": 0},
            {"format": A.float32x3, "offset": 12, "shader_location": 1},
            {"format": A.float32x4, "offset": 24, "shader_location": 2},
            {"format": A.float32x2, "offset": 40, "shader_location": 3},
            {"format": A.float32x3, "offset": 48, "shader_location": 4}]}]
        add = {"color": {"src_factor": "one", "dst_factor": "one", "operation": "add"},
               "alpha": {"src_factor": "zero", "dst_factor": "one", "operation": "add"}}

        def pipe(entry, blend, depth_write, compare):
            return self.device.create_render_pipeline(
                layout=layout,
                vertex={"module": mod, "entry_point": "vs", "buffers": vb},
                primitive={"topology": "triangle-list", "cull_mode": "none"},
                depth_stencil={"format": "depth32float", "depth_write_enabled": depth_write, "depth_compare": compare},
                multisample={"count": self.msaa},
                fragment={"module": mod, "entry_point": entry,
                          "targets": [{"format": "rgba16float", **({"blend": blend} if blend else {})}]})
        self.p_main = pipe("fs_main", None, True, "less")
        self.p_glow = pipe("fs_glow", add, False, "less-equal")
        over = {"color": {"src_factor": "one", "dst_factor": "one-minus-src-alpha", "operation": "add"},
                "alpha": {"src_factor": "one", "dst_factor": "one-minus-src-alpha", "operation": "add"}}
        self.p_blend = pipe("fs_main", over, False, "less-equal")
        arr = {"sample_type": "float", "view_dimension": "2d-array"}
        self.bgl_t = self.device.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": T.VERTEX | T.FRAGMENT, "buffer": {"type": "uniform"}},
            {"binding": 1, "visibility": T.FRAGMENT, "sampler": {"type": "filtering"}},
            *[{"binding": b, "visibility": T.FRAGMENT, "texture": arr} for b in range(7, 11)]])
        lay_t = self.device.create_pipeline_layout(bind_group_layouts=[self.bgl_t])
        self.p_terrain = self.device.create_render_pipeline(
            layout=lay_t, vertex={"module": mod, "entry_point": "vs", "buffers": vb},
            primitive={"topology": "triangle-list", "cull_mode": "none"},
            depth_stencil={"format": "depth32float", "depth_write_enabled": True, "depth_compare": "less"},
            multisample={"count": self.msaa},
            fragment={"module": mod, "entry_point": "fs_terrain", "targets": [{"format": "rgba16float"}]})
        self.clamp_sampler = self.device.create_sampler(address_mode_u="clamp-to-edge", address_mode_v="clamp-to-edge",
                                                        mag_filter="linear", min_filter="linear", mipmap_filter="linear")
        self.sampler = self.device.create_sampler(address_mode_u="repeat", address_mode_v="repeat", mag_filter="linear",
                                                  min_filter="linear", mipmap_filter="linear", max_anisotropy=max(1, int(aniso)))
        self._defaults = {}
        self._targets = {}
        self._tex = {}            # id(first mip) -> view: a unit's textures go up once
        self._tex_bytes = 0
        self._skinned = {}        # (id(mesh), pose hash) -> (mesh, (pos, nrm, tan)): a pose is skinned once for all facings

    # ---- resources ---------------------------------------------------------------------------------------------------------
    def texture(self, mips, srgb=False):
        key = (id(mips[0]), srgb)
        if key not in self._tex:
            size = sum(m.nbytes for m in mips)
            if self._tex_bytes + size > TEX_CACHE_BYTES:   # long runs (audits) load many maps: start over
                self._tex.clear()
                self._tex_bytes = 0
            self._tex[key] = (mips[0], self._upload(mips, srgb))      # the array is kept so its id stays unique
            self._tex_bytes += size
        return self._tex[key][1]

    def _upload(self, mips, srgb):
        wgpu = self.wgpu
        h, w = mips[0].shape[:2]
        t = self.device.create_texture(size=(w, h, 1), format="rgba8unorm-srgb" if srgb else "rgba8unorm",
                                       usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
                                       mip_level_count=len(mips))
        for i, m in enumerate(mips):
            m = np.ascontiguousarray(m[..., :4] if m.shape[-1] >= 4 else np.dstack([m, np.full(m.shape[:2], 255, np.uint8)]),
                                     np.uint8)
            mh, mw = m.shape[:2]
            self.device.queue.write_texture({"texture": t, "mip_level": i, "origin": (0, 0, 0)}, m.tobytes(),
                                            {"offset": 0, "bytes_per_row": mw * 4, "rows_per_image": mh}, (mw, mh, 1))
        return t.create_view()

    def texture_array(self, layers, srgb=False):
        """A 2d-array view of equally sized mip chains (one list of mips per layer)."""
        wgpu = self.wgpu
        h, w = layers[0][0].shape[:2]
        nm = min(len(m) for m in layers)
        t = self.device.create_texture(size=(w, h, len(layers)), format="rgba8unorm-srgb" if srgb else "rgba8unorm",
                                       usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
                                       mip_level_count=nm, dimension="2d")
        for li, mips in enumerate(layers):
            for i in range(nm):
                m = np.ascontiguousarray(mips[i][..., :4], np.uint8)
                mh, mw = m.shape[:2]
                self.device.queue.write_texture({"texture": t, "mip_level": i, "origin": (0, 0, li)}, m.tobytes(),
                                                {"offset": 0, "bytes_per_row": mw * 4, "rows_per_image": mh}, (mw, mh, 1))
        return t.create_view(dimension="2d-array")

    def terrain_draw(self, pos, nrm, tan, uv, tris, arrays: dict, p3, p4, name="terrain") -> "Draw":
        """A splat-ground draw: `arrays` = views of the layer albedo / normal / ORM arrays and the weight array
        ({"alb", "nrm", "orm", "wts"}), p3 = (x0, z0, w, h) of the weight map in world units, p4 = (units per layer
        repeat, layers, height-blend sharpness)."""
        vbuf, n = self._vbuf(pos, nrm, tan, uv, tris)
        ub = self._ubuf()
        bind = self.device.create_bind_group(layout=self.bgl_t, entries=[
            {"binding": 0, "resource": {"buffer": ub, "offset": 0, "size": ub.size}},
            {"binding": 1, "resource": self.sampler},
            {"binding": 7, "resource": arrays["alb"]}, {"binding": 8, "resource": arrays["nrm"]},
            {"binding": 9, "resource": arrays["orm"]}, {"binding": 10, "resource": arrays["wts"]}])
        return Draw(vbuf, n, ub, bind, [], 0.0, pos[tris], uv[tris], name, name, "terrain:splat", light_class="world",
                    terrain={"p3": tuple(p3), "p4": tuple(p4)})

    def default(self, kind):
        if kind not in self._defaults:
            px = {"alb": (255, 255, 255, 255), "nrm": (255, 128, 0, 128), "orm": (255, 255, 0, 0), "mask": (0, 0, 0, 255),
                  "strip": (255, 255, 255, 255)}[kind]
            self._defaults[kind] = self.texture([np.full((4, 4, 4), px, np.uint8)], srgb=kind in ("alb", "strip"))
        return self._defaults[kind]

    def _bind(self, ubuf, alb, nrm, orm, mask, strip):
        return self.device.create_bind_group(layout=self.bgl, entries=[
            {"binding": 0, "resource": {"buffer": ubuf, "offset": 0, "size": ubuf.size}},
            {"binding": 1, "resource": self.sampler},
            {"binding": 2, "resource": alb}, {"binding": 3, "resource": nrm}, {"binding": 4, "resource": orm},
            {"binding": 5, "resource": mask}, {"binding": 6, "resource": strip}])

    def _ubuf(self):
        return self.device.create_buffer(size=UBUF_BYTES, usage=self.wgpu.BufferUsage.UNIFORM | self.wgpu.BufferUsage.COPY_DST)

    def _vbuf(self, pos, nrm, tan, uv, tris):
        n = len(tris) * 3
        v = np.zeros((n, FLOATS), np.float32)
        idx = tris.reshape(-1)
        v[:, 0:3], v[:, 3:6], v[:, 6:10], v[:, 10:12] = pos[idx], nrm[idx], tan[idx], uv[idx]
        v[:, 12:15] = np.tile(np.eye(3, dtype=np.float32), (len(tris), 1))
        buf = self.device.create_buffer_with_data(data=v.tobytes(), usage=self.wgpu.BufferUsage.VERTEX)
        return buf, n

    # ---- scene -> draws ----------------------------------------------------------------------------------------------------
    def prepare(self, unit, clip=None, t=0.0, yaw=0.0, cam=None, pose_kw=None, poser=None, layer_scale=1.0, place=None,
                light_class="unit") -> Prepared:
        """Draws of a scene.Unit: the part models posed with `clip` at time t (gr2.pose_at; `pose_kw` passes its loop,
        method and keep_root_translation; `poser(skeleton) -> gr2.Pose` replaces all of that, e.g. player.Player),
        turned by `yaw` degrees and scaled by the unit's root scale; a card faces `cam`. `layer_scale` draws the self-lit
        layers scaled about the unit's origin by that factor relative to the body (1: the same mesh; a test lever for the
        size gap of viewer/p3, where the game's layer may skip the root scale). `place`: a 4x4 world matrix applied after
        all that (a placed scene object; rotation and uniform scale), `light_class`: the Light.classes entry its draws use."""
        prep = Prepared([])
        if unit.kind == "card":
            return self._prepare_card(unit, cam, prep)
        R = rot_y(yaw) * unit.root_scale
        Rn = rot_y(yaw)
        for part in unit.parts:
            if part.skeleton is None:
                pose = None
            elif poser is not None:
                pose = poser(part.skeleton)
            else:
                pose = gr2.pose_at(part.skeleton, unit.clips.get(clip) if clip else None, t, **(pose_kw or {}))
            if pose is not None:
                prep.pose = {"clip": pose.clip or "(rest)", "time": round(pose.time, 4), "tracks": pose.tracks,
                             "unsupported_parts": pose.unsupported}
                if poser is None and clip and clip not in unit.clips:
                    prep.notes.append("clip %s not in the unit's clips %s: rest pose" % (clip, sorted(unit.clips)))
            tx = part.textures
            views = {k: (self.texture(tx[u].mips, srgb=tx[u].srgb) if u in tx else self.default(k))
                     for k, u in (("alb", "AlbedoTexture"), ("nrm", "NormalTexture"), ("orm", "ORMTexture"))}
            alb_size = tx["AlbedoTexture"].mips[0].shape[:2] if "AlbedoTexture" in tx else (4, 4)
            for m in part.meshes:
                sk_key = (id(m), None if pose is None else hash(pose.worlds.tobytes()))
                hit = self._skinned.get(sk_key)
                if hit is None or hit[0] is not m:   # id() is reused once a mesh is freed: keep the mesh, check it
                    if len(self._skinned) > 512:
                        self._skinned.clear()
                    hit = self._skinned[sk_key] = (m, gr2.skin(m, part.skeleton, pose))
                P, N, Tn = hit[1]
                Pw, Nw = P @ R.T, N @ Rn.T
                Tw = np.hstack([Tn[:, :3] @ Rn.T, Tn[:, 3:4]])
                if place is not None:
                    Mp = np.asarray(place, float)
                    Rp = Mp[:3, :3] / max(np.cbrt(abs(np.linalg.det(Mp[:3, :3]))), 1e-12)
                    Pw = Pw @ Mp[:3, :3].T + Mp[:3, 3]
                    Nw = Nw @ Rp.T
                    Tw = np.hstack([Tw[:, :3] @ Rp.T, Tw[:, 3:4]])
                vbuf, n = self._vbuf(Pw, Nw, Tw, m.uv, m.tris)
                ub = self._ubuf()
                bind = self._bind(ub, views["alb"], views["nrm"], views["orm"], self.default("mask"), self.default("strip"))
                layers, lnames = [], []
                lvbuf = vbuf if layer_scale == 1.0 else self._vbuf(Pw * float(layer_scale), Nw, Tw, m.uv, m.tris)[0]
                for L in part.layers:
                    lub = self._ubuf()
                    layers.append((lub, self._bind(lub, views["alb"], views["nrm"], views["orm"],
                                                   self.texture(L.mask.mips), self.texture(L.strip.mips, srgb=True)), lvbuf))
                    lnames.append(L.name)
                prm = getattr(m, "params", None) or {}
                emis = float(prm.get("emissive", 0.0))
                if emis > 0.0:
                    mk = self.texture(tx["MaskTexture"].mips) if "MaskTexture" in tx else self.default("alb")
                    bind = self._bind(ub, views["alb"], views["nrm"], views["orm"], mk, self.default("strip"))
                uvt = m.uv[m.tris] * np.array([alb_size[1], alb_size[0]], float)
                prep.draws.append(Draw(vbuf, n, ub, bind, layers, float(prm.get("alpha_cut", 0.0)), Pw[m.tris], uvt,
                                       m.name, part.name,
                                       tx["AlbedoTexture"].logical if "AlbedoTexture" in tx else "", lnames,
                                       light_class=light_class, blend=float(prm.get("blend", 0.0)), emissive=emis))
        return prep

    def _prepare_card(self, unit, cam, prep):
        c = unit.card
        r, _u, w = cam.basis()
        quad = c["quad"] * unit.root_scale
        nrm = np.tile(w, (4, 1))
        tan = np.tile(np.append(r, 1.0), (4, 1))
        tris = np.array([[0, 1, 2], [0, 2, 3]])
        vbuf, n = self._vbuf(quad, nrm, tan, c["uv"], tris)
        ub = self._ubuf()
        alb = self.texture(_mip_chain(c["rgba"]), srgb=True)
        bind = self._bind(ub, alb, self.default("nrm"), self.default("orm"), self.default("mask"), self.default("strip"))
        h, wd = c["rgba"].shape[:2]
        prep.draws.append(Draw(vbuf, n, ub, bind, [], 0.5, quad[tris], c["uv"][tris] * np.array([wd, h], float), unit.name,
                               "card", "card:%s" % c["mode"]))
        prep.notes.append("card %s: classic dir %d frame %d, bottom row %d" % (c["mode"], c["dir"], c["frame"], c["bottom"]))
        return prep

    # ---- rendering ---------------------------------------------------------------------------------------------------------
    def _target(self, w, h):
        key = (w, h)
        if key not in self._targets:
            wgpu = self.wgpu
            U = wgpu.TextureUsage
            col = self.device.create_texture(size=(w, h, 1), format="rgba16float", sample_count=self.msaa,
                                             usage=U.RENDER_ATTACHMENT)
            res = self.device.create_texture(size=(w, h, 1), format="rgba16float", usage=U.RENDER_ATTACHMENT | U.COPY_SRC)
            dep = self.device.create_texture(size=(w, h, 1), format="depth32float", sample_count=self.msaa,
                                             usage=U.RENDER_ATTACHMENT)
            if len(self._targets) > 4:
                self._targets.clear()
            self._targets[key] = (col, res, dep)
        return self._targets[key]

    def depth_range(self, prep, cam):
        d = np.concatenate([cam.depth(dr.world.reshape(-1, 3)) for dr in prep.draws]) if prep.draws else np.zeros(1)
        return float(d.min()) - 1.0, float(d.max()) + 1.0

    def render_rect(self, prep, cam, origin, rect, pass_name="lit", light=None, glow=True, drange=None) -> np.ndarray:
        """Linear premultiplied RGBA float32 (h, w, 4) of the pixel rectangle rect = (x0, y0, w, h) of the image whose
        world origin is at pixel `origin`."""
        light = light or Light()
        x0, y0, w, h = rect
        wp = -(-w // 32) * 32                    # rows read back in multiples of 256 bytes
        if max(wp, h) > self.max_tex:
            raise ValueError("tile %dx%d over the GPU limit %d" % (wp, h, self.max_tex))
        col, res, dep = self._target(wp, h)
        dmin, dmax = drange or self.depth_range(prep, cam)
        M = cam.matrix(origin, (x0, y0, wp, h), dmin, dmax)
        _r, _u, wv = cam.basis()
        pid = PASSES[pass_name]
        lights = {}
        many = {}
        for dr in prep.draws:
            body_pid = PASSES["glow"] if dr.hidden_body and pid in (0, 5) else pid
            if dr.light_class not in lights:
                lc0 = light.for_class(dr.light_class)
                lights[dr.light_class] = (lc0, pack_points(lc0.points))
                many[dr.light_class] = len(lc0.points) > MAX_POINTS
            lc, packed = lights[dr.light_class]
            if many[dr.light_class]:
                W3 = dr.world.reshape(-1, 3)
                lo, hi = W3.min(0), W3.max(0)
                packed = pack_points(pick_points(lc.points, (lo + hi) / 2.0, float(np.linalg.norm(hi - lo)) / 2.0))
            for ub, cut, p in [(dr.ubuf, dr.alpha_cut, body_pid)] + [(lay[0], dr.alpha_cut, pid) for lay in dr.layers]:
                u = np.zeros(UBUF_BYTES // 4, np.float32)
                u[0:16] = M.T.ravel()
                u[16:19] = wv
                u[20:23] = lc.ambient
                kd = np.asarray(lc.key_dir, float)
                u[24:27] = kd / max(np.linalg.norm(kd), 1e-9)
                u[28:31] = lc.key_col
                u[32:35] = lc.env_col
                u[36:40] = (p, lc.glow_gain, lc.nrm_green, cut)
                u[40:44] = (dmin, dmax, lc.floor_clip, lc.spec_gain)
                u[44:44 + len(packed)] = packed
                u[45] = dr.emissive
                u[46] = dr.blend
                fr, fg, fb, ff = (tuple(lc.fog) + (0.0, 0.0, 0.0, 0.0))[:4]
                u[FOG_AT:FOG_AT + 4] = (fr * ff, fg * ff, fb * ff, ff)
                if dr.terrain:
                    u[FOG_AT + 4:FOG_AT + 8] = dr.terrain["p3"]
                    u[FOG_AT + 8:FOG_AT + 12] = (tuple(dr.terrain["p4"]) + (0.0,))[:4]
                self.device.queue.write_buffer(ub, 0, u.tobytes())
        enc = self.device.create_command_encoder()
        rp = enc.begin_render_pass(
            color_attachments=[{"view": col.create_view(), "resolve_target": res.create_view(), "load_op": "clear",
                                "store_op": "discard", "clear_value": (0, 0, 0, 0)}],
            depth_stencil_attachment={"view": dep.create_view(), "depth_load_op": "clear", "depth_store_op": "discard",
                                      "depth_clear_value": 1.0})
        terr = [dr for dr in prep.draws if dr.terrain]
        if terr:
            rp.set_pipeline(self.p_terrain)
            for dr in terr:
                rp.set_bind_group(0, dr.bind)
                rp.set_vertex_buffer(0, dr.vbuf)
                rp.draw(dr.count)
        rp.set_pipeline(self.p_main)
        for dr in prep.draws:
            if dr.terrain or dr.blend > 0.0:
                continue
            rp.set_bind_group(0, dr.bind)
            rp.set_vertex_buffer(0, dr.vbuf)
            rp.draw(dr.count)
        bl = [dr for dr in prep.draws if dr.blend > 0.0 and not dr.terrain]
        if bl:                                  # back to front (camera.depth grows towards the camera)
            dk = [float(cam.depth(dr.world.reshape(-1, 3)).mean()) for dr in bl]
            rp.set_pipeline(self.p_blend)
            for _d, dr in sorted(zip(dk, bl), key=lambda t: t[0]):
                rp.set_bind_group(0, dr.bind)
                rp.set_vertex_buffer(0, dr.vbuf)
                rp.draw(dr.count)
        if glow and pass_name in ("lit", "unlit", "glow"):
            rp.set_pipeline(self.p_glow)
            for dr in prep.draws:
                for lay in dr.layers:
                    rp.set_bind_group(0, lay[1])
                    rp.set_vertex_buffer(0, lay[2] if len(lay) > 2 else dr.vbuf)
                    rp.draw(dr.count)
        rp.end()
        self.device.queue.submit([enc.finish()])
        data = self.device.queue.read_texture({"texture": res, "mip_level": 0, "origin": (0, 0, 0)},
                                              {"offset": 0, "bytes_per_row": wp * 8, "rows_per_image": h}, (wp, h, 1))
        a = np.frombuffer(data, np.float16).reshape(h, wp, 4)[:, :w].astype(np.float32)
        return a

    def render(self, prep, cam, size, origin, pass_name="lit", light=None, glow=True, ss=1, tile=None, bg=None, rig=None):
        """8-bit RGBA (H, W, 4) at `size` = (W, H): rendered at ss x (camera scale and image), tiled when larger than
        `tile` (default: the GPU limit), box-filtered down, sRGB-encoded (or by `rig`: its light, exposure and tone)."""
        if rig is not None:
            light = rig.light
        W, H = size
        big = _scaled_cam(cam, ss)
        tile = min(tile or self.max_tex, self.max_tex)
        tile -= tile % (32 * ss) if tile > 32 * ss else 0
        drange = self.depth_range(prep, big)
        Wss, Hss = W * ss, H * ss
        out = np.zeros((Hss, Wss, 4), np.float32)
        for rect in tiling.plan(Wss, Hss, tile):
            x0, y0, w, h = rect
            out[y0:y0 + h, x0:x0 + w] = self.render_rect(prep, big, (origin[0] * ss, origin[1] * ss), rect, pass_name,
                                                         light, glow, drange)
        return to_uint8(box_down(out, ss), pass_name, bg, rig.encode if rig is not None else None)

    def render_streamed(self, prep, cam, size, origin, path, pass_name="lit", light=None, glow=True, ss=1, tile=4096,
                        gate=None, log=print, keep=(), rig=None) -> dict:
        """Like render, but each row of tiles goes straight into a PNG at `path` (straight alpha); each tile is
        reduced to 8 bits as it arrives, so memory holds one row of 8-bit tiles. `gate()` is called before each tile row
        and may wait (GPU gate). `keep`: output-pixel rectangles (x0, y0, w, h) whose stitched pixels are returned (seam
        checks). Returns timing, the plan and the kept crops."""
        if rig is not None:
            light = rig.light
        enc = rig.encode if rig is not None else None
        W, H = size
        big = _scaled_cam(cam, ss)
        tile = min(tile, self.max_tex)
        tile -= tile % (32 * ss)
        drange = self.depth_range(prep, big)
        Wss, Hss = W * ss, H * ss
        plan = tiling.plan(Wss, Hss, tile)
        png = tiling.PngStream(path, W, H, 4)
        kept = {}
        t0 = time.time()
        for row in tiling.rows(plan):
            if gate:
                gate()
            y0, h = row[0][1], row[0][3]
            block = np.zeros((h // ss, W, 4), np.uint8)
            for rect in row:
                x0, _y, w, _h = rect
                px = self.render_rect(prep, big, (origin[0] * ss, origin[1] * ss), rect, pass_name, light, glow, drange)
                block[:, x0 // ss:(x0 + w) // ss] = to_uint8(box_down(px, ss), pass_name, None, enc)
            oy = y0 // ss
            for i, (kx, ky, kw, kh) in enumerate(keep):
                a, b = max(ky, oy), min(ky + kh, oy + block.shape[0])
                if a < b:
                    kept.setdefault(i, np.zeros((kh, kw, 4), np.uint8))[a - ky:b - ky] = block[a - oy:b - oy, kx:kx + kw]
            png.write(block)
            log("row y=%d..%d of %d done (%.0fs)" % (y0 // ss, (y0 + h) // ss, H, time.time() - t0))
        png.close()
        return {"tiles": len(plan), "tile": tile, "ss": ss, "seconds": round(time.time() - t0, 1),
                "kept": [kept.get(i) for i in range(len(keep))]}


def _scaled_cam(cam, ss):
    from .camera import OrthoCamera
    return OrthoCamera(cam.el, cam.az, cam.k * ss)


def _mip_chain(rgba: np.ndarray) -> list:
    """Box-filtered mips of a straight-alpha sRGB image, colour averaged weighted by alpha (no dark fringes)."""
    out = [np.ascontiguousarray(rgba, np.uint8)]
    cur = rgba.astype(np.float64)
    while min(cur.shape[:2]) > 1:
        h, w = cur.shape[0] // 2 * 2, cur.shape[1] // 2 * 2
        if h == 0 or w == 0:
            break
        c = cur[:h, :w]
        a = c[..., 3:4] / 255.0
        lin = srgb_decode(c[..., :3] / 255.0) * a
        a2 = a.reshape(h // 2, 2, w // 2, 2, 1).mean((1, 3))
        l2 = lin.reshape(h // 2, 2, w // 2, 2, 3).mean((1, 3))
        col = srgb_encode(np.where(a2 > 1e-6, l2 / np.maximum(a2, 1e-6), 0.0)) * 255.0
        cur = np.concatenate([col, a2 * 255.0], -1)
        out.append(np.round(cur).astype(np.uint8))
    return out


def probe(render=True) -> dict:
    """Adapter, backend, limits and sample counts of this machine's GPU, and one triangle rendered and read back."""
    wgpu = _wgpu()
    t0 = time.time()
    out = {"wgpu_py": wgpu.__version__}
    try:
        out["adapters"] = [{k: v for k, v in dict(a.info).items() if k in ("device", "description", "adapter_type",
                                                                            "backend_type", "vendor", "architecture")}
                           for a in wgpu.gpu.enumerate_adapters_sync()]
    except Exception as e:  # noqa: BLE001
        out["adapters"] = repr(e)
    ad = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    out["chosen"] = {k: v for k, v in dict(ad.info).items() if k in ("device", "description", "adapter_type", "backend_type",
                                                                      "vendor", "architecture")}
    lim = dict(ad.limits)
    out["limits"] = {k: lim.get(k) for k in ("max-texture-dimension-2d", "max-buffer-size", "max-bind-groups",
                                             "max-color-attachment-bytes-per-sample", "max-sampled-textures-per-shader-stage")}
    out["features"] = sorted(str(f) for f in ad.features)
    if not render:
        return out
    dev = ad.request_device_sync(required_limits={"max-texture-dimension-2d": lim["max-texture-dimension-2d"]})
    sh = dev.create_shader_module(code="""
@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4<f32> {
  var p = array<vec2<f32>, 3>(vec2(-0.8, -0.8), vec2(0.8, -0.8), vec2(0.0, 0.8));
  return vec4<f32>(p[i], 0.5, 1.0);
}
@fragment fn fs() -> @location(0) vec4<f32> { return vec4<f32>(1.0, 0.5, 0.25, 1.0); }
""")
    W = H = 256
    res = {}
    for samples in (1, 2, 4, 8, 16):
        try:
            U = wgpu.TextureUsage
            col = dev.create_texture(size=(W, H, 1), format="rgba16float", sample_count=samples,
                                     usage=U.RENDER_ATTACHMENT | (U.COPY_SRC if samples == 1 else 0))
            dst = col if samples == 1 else dev.create_texture(size=(W, H, 1), format="rgba16float",
                                                              usage=U.RENDER_ATTACHMENT | U.COPY_SRC)
            pipe = dev.create_render_pipeline(layout="auto", vertex={"module": sh, "entry_point": "vs"},
                                              fragment={"module": sh, "entry_point": "fs", "targets": [{"format": "rgba16float"}]},
                                              primitive={"topology": "triangle-list"}, multisample={"count": samples})
            enc = dev.create_command_encoder()
            att = {"view": col.create_view(), "load_op": "clear", "store_op": "store", "clear_value": (0, 0, 0, 0)}
            if samples > 1:
                att["resolve_target"] = dst.create_view()
            rp = enc.begin_render_pass(color_attachments=[att])
            rp.set_pipeline(pipe)
            rp.draw(3)
            rp.end()
            dev.queue.submit([enc.finish()])
            data = dev.queue.read_texture({"texture": dst}, {"bytes_per_row": W * 8, "rows_per_image": H}, (W, H, 1))
            err = None
            a = np.frombuffer(data, np.float16).reshape(H, W, 4).astype(np.float32)
            res[samples] = {"ok": err is None, "error": None if err is None else str(getattr(err, "message", err))[:160],
                            "coverage": round(float((a[..., 3] > 0).mean()), 4),
                            "edge_pixels_partial": int(((a[..., 3] > 0) & (a[..., 3] < 1)).sum()),
                            "rgb_centre": [round(float(x), 3) for x in a[128, 128, :3]]}
        except Exception as e:  # noqa: BLE001
            res[samples] = {"ok": False, "error": repr(e)[:200]}
    out["msaa_rgba16float"] = res
    out["seconds"] = round(time.time() - t0, 2)
    return out


if __name__ == "__main__":
    print(json.dumps(probe(), indent=1, default=str))
