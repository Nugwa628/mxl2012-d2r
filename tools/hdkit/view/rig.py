"""Light rigs: the renderer's light (gpu.Light) plus exposure and tone, loaded from and saved to JSON.

Presets:
  default   phase 1's uncalibrated night key and ambient, tone = plain sRGB encode (what every earlier render used).
  game      the facts read from the 3.3 executable and the `env/vis` files (viewer/re/REPORT.md), nothing fitted:
              exposure        0.18 / (2^EV * 10/65), EV from the vis file (4 -> 0.0731)
              unit factor     characterBrightnessFactor 0.4
              unit key        player_key_light, power 30, colour (1, 0.937, 0.878), mask 68
              tone            HDR x 0.008 -> PQ -> SDR EETF (tone.py); the grading LUT is NOT applied (unknown)
            The way these factors combine in the unit shader is not known (cb2 slots unnamed): the rig composes them as
            key colour = colour x power x unit factor and output x exposure before the tone curve, and lists that as an
            assumption. Ambient / IBL strength for units, the light directions in our axes and the LUT are listed under
            `unknown` and fall back to the default rig's values (marked in every metrics.json). Tuning them is phase 4.
  `from_vis(path)` builds a game rig from any `data/hd/env/vis/*.json` (e.g. the copies in viewer/re/casc).
  `--rig "vis:<file>;env=6.03;unit=2,128,128,255"`: plus the environment reflection level and a unit's own light
  (monstats2 Light, light-r/g/b); the calibrated form for a Blood Moor night unit (viewer cal2 REPORT.md).

A rig file is the dict of `Rig.as_dict()`; unknown keys are kept in `meta`.
"""
import json
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

from .gpu import Light

GAME_EV = 4.0
UNIT_FACTOR = 0.4
UNIT_KEY = {"name": "player_key_light", "power": 30.0, "color": [1.0, 0.9372549, 0.8784314], "mask": 68}
CORPSE_MODES = ("dd",)
MONSTER_MASK = 19          # ModelDefinitionComponent lightMask of 1011 of the 1013 stock enemy model entries


def exposure_for_ev(ev: float) -> float:
    """0.18 / (2^EV * 10/65): camera +0x144 from EV at +0x140 (re/REPORT.md, 0xED6F90)."""
    return 0.18 / (2.0 ** ev * 10.0 / 65.0)


@dataclass
class Rig:
    name: str = "default"
    light: Light = field(default_factory=Light)
    exposure: float = 1.0
    tone: str = "srgb"                 # "srgb" (plain encode), "game" (tone.grey curve) or "lut" (tone.lut_chain)
    lut: str | None = None             # grading LUT path: not applied (not decoded yet)
    unknown: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    lights: list = field(default_factory=list)      # every light of the source file, used or not
    meta: dict = field(default_factory=dict)
    post: dict = field(default_factory=dict)        # tone "lut" options: peak, curve, bloom {...}, value {...}

    def as_dict(self) -> dict:
        return {"name": self.name, "light": {k: list(v) if isinstance(v, tuple) else v for k, v in self.light.as_dict().items()},
                "exposure": self.exposure, "tone": self.tone, "lut": self.lut, "unknown": self.unknown,
                "assumptions": self.assumptions, "lights": self.lights, "meta": self.meta, "post": self.post}

    def save(self, path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.as_dict(), indent=1) + "\n", encoding="utf-8")
        return p

    @classmethod
    def from_dict(cls, d: dict) -> "Rig":
        names = {f.name for f in fields(Light)}
        lt = Light(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in (d.get("light") or {}).items() if k in names})
        known = {"name", "light", "exposure", "tone", "lut", "unknown", "assumptions", "lights", "meta", "post"}
        meta = dict(d.get("meta") or {})
        meta.update({k: v for k, v in d.items() if k not in known})
        return cls(d.get("name", "custom"), lt, float(d.get("exposure", 1.0)), d.get("tone", "srgb"), d.get("lut"),
                   list(d.get("unknown") or []), list(d.get("assumptions") or []), list(d.get("lights") or []), meta,
                   dict(d.get("post") or {}))

    def for_mode(self, mode: str | None) -> "Rig":
        """This rig as a unit in `mode` sees it: a corpse (DD) has no unit light of its own (viewer cal2: the game's
        corpse is lit without it), so the points marked `unit_light` are dropped for it."""
        if (mode or "").lower() not in CORPSE_MODES:
            return self
        r = self
        if (self.post.get("value") or {}).get("live_only"):
            r = replace(r, post={k: v for k, v in self.post.items() if k != "value"})
        if any(p.get("unit_light") for p in self.light.points):
            r = replace(r, light=replace(r.light, points=tuple(p for p in r.light.points if not p.get("unit_light"))))
        return r

    def encode(self, lin_rgb):
        """Scene-linear rgb -> display sRGB 0..1 by this rig's exposure and tone."""
        import numpy as np
        if self.tone == "lut":
            from . import tone
            v = np.asarray(lin_rgb, float) * self.exposure
            vc = self.post.get("value")
            if vc:
                v = tone.value_curve(v, float(vc.get("brightness", 0.0)), tuple(vc.get("points", (0.25, 0.25, 0.75, 0.99))),
                                     float(vc.get("strength", 0.0)))
            return tone.lut_chain(v, float(self.post.get("peak", tone.PEAK_NITS)), self.post.get("curve"),
                                  bool(self.post.get("expand", True)))
        if self.tone == "game":
            from . import tone
            return tone.apply(lin_rgb, self.exposure)
        from .gpu import srgb_encode
        return srgb_encode(np.asarray(lin_rgb) * self.exposure)

    def encode_image(self, lin):
        """Linear premultiplied RGBA image (H, W, 4) -> (display sRGB straight (H, W, 3), alpha (H, W, 1)), with the
        rig's bloom (post["bloom"]) when set. The bloom is added before the tone map where the unit covers a pixel; the
        halo outside it is returned as a layer whose alpha is its display level (an over-blend that adds its light to the
        background; the game adds it in HDR before the tone map, so this is close for faint halos only). None: no bloom
        (the per-pixel encode is used)."""
        import numpy as np
        b = self.post.get("bloom")
        if not b or self.tone != "lut":
            return None
        from . import tone
        c, a = lin[..., :3], np.clip(lin[..., 3:4], 0.0, 1.0)
        B = tone.bloom(c * self.exposure, float(b.get("cutoff", 1.0)), float(b.get("intensity", 1.0)),
                       int(b.get("levels", 5)), float(b.get("gain", 1.0))) / max(self.exposure, 1e-12)
        straight = np.where(a > 1e-6, c / np.maximum(a, 1e-6), 0.0)
        du = np.clip(self.encode(straight + B), 0.0, 1.0)
        dh = np.clip(self.encode(B), 0.0, 1.0)
        from .gpu import srgb_decode, srgb_encode
        lu, lh = srgb_decode(du), srgb_decode(dh)
        ah = np.clip(lh.max(-1, keepdims=True), 0.0, 1.0)
        a2 = a + (1.0 - a) * ah
        lin_out = (lu * a + lh * (1.0 - a)) / np.maximum(a2, 1e-6)
        return np.clip(srgb_encode(np.clip(lin_out, 0.0, 1.0)), 0.0, 1.0), a2


def load(path) -> Rig:
    return Rig.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def default() -> Rig:
    return Rig()


def _game(ev, factor, key, lights, source) -> Rig:
    base = Light()
    col = tuple(c * key["power"] * factor for c in key["color"])
    unknown = ["unit ambient / IBL strength (iblIntensity is in the vis file; its weight in ps_models_p is not): "
               "default rig ambient kept",
               "light directions in the viewer's axes (vis quaternions are in engine axes; convention unverified): "
               "default rig key direction kept",
               "grading LUT (gradingLutFile, default.dds): not decoded, not applied",
               "lightMask bits (9 = terrain + ?, 68 = units + ?): which vis lights reach units",
               "environment reflection colour and specular weight: default rig values kept",
               "night cap cause (unit factor 0.4 or night key x exposure)"]
    assumptions = ["key colour = colour x power x characterBrightnessFactor",
                   "exposure multiplies the shaded colour before the tone curve",
                   "tone chain colour handling: hue-preserving through the grey curve (chroma path not emulated)"]
    light = Light(ambient=base.ambient, key_dir=base.key_dir, key_col=col, env_col=base.env_col,
                  glow_gain=base.glow_gain, spec_gain=base.spec_gain, nrm_green=base.nrm_green)
    return Rig("game", light, exposure_for_ev(ev), "game", None, unknown, assumptions, lights,
               {"source": source, "ev": ev, "unit_factor": factor, "unit_key": key,
                "exposure_formula": "0.18 / (2^EV * 10/65)"})


def game() -> Rig:
    """The game rig from the facts in the module note (EV 4, factor 0.4, unit key 30)."""
    return _game(GAME_EV, UNIT_FACTOR, dict(UNIT_KEY), [], "viewer/re/REPORT.md section 2 (344/369 vis files)")


def light_towards(quat) -> tuple:
    """Direction towards a vis DirectionalLight (world axes): its orientation applied to -z. Assumption: the engine's
    axes are the viewer's (the preset placements of hdkit.view.preset agree), so (0.60, 0.80, 0) for the act 1 monster
    light is 53 degrees up from the +x side."""
    from .preset import quat_matrix
    v = quat_matrix(quat or {}) @ [0.0, 0.0, -1.0]
    return tuple(float(x) for x in v)


def from_vis(path, light_mask: int | None = MONSTER_MASK) -> Rig:
    """A game rig from one `env/vis/*.json`: its EV, characterBrightnessFactor, depth fog and a list of every light it
    names (power, colour, mask, quaternion).

    light_mask: the drawn model's ModelDefinitionComponent lightMask (19 on every stock enemy model). The rig lights the
    model with the vis lights whose lightMask shares a bit with it and whose power is above 0: the strongest is the key
    (its vis direction), the others are directional terms (diffuse, as point lights at 10^4 units with no falloff), each
    colour x power x characterBrightnessFactor. None: the earlier rig (player_key_light, default direction), which
    lights the player (mask 68) and not a monster (68 & 19 = 0)."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    ev, factor, key, lights = GAME_EV, UNIT_FACTOR, dict(UNIT_KEY), []
    fog = (0.0, 0.0, 0.0, 0.0)
    for e in d.get("entities", []):
        comps = {c["type"]: c for c in e.get("components", [])}
        vd = comps.get("VisualDataComponent")
        if vd:
            ev = float(vd.get("exposureValue", ev))
            factor = float(vd.get("characterBrightnessFactor", factor))
            fc = vd.get("depthFogColor") or {}
            fog = tuple(float(fc.get(k, 0.0)) for k in "xyz") + (float(vd.get("depthFogDensity", 0.0)),)
        dl = comps.get("DirectionalLightDefinitionComponent")
        if dl:
            c = dl.get("color", {})
            q = (comps.get("TransformDefinitionComponent") or {}).get("orientation")
            L = {"name": e.get("name"), "power": float(dl.get("power", 0.0)),
                 "color": [float(c.get(k, 1.0)) for k in "xyz"], "mask": dl.get("lightMask"), "quat": q}
            lights.append(L)
            if e.get("name") == "player_key_light":
                key = {k: L[k] for k in ("name", "power", "color", "mask")}
    r = _game(ev, factor, key, lights, str(path))
    if any(fog[:3]) and fog[3] > 0:
        r.light = replace(r.light, fog=fog)
        r.assumptions.append("depth fog: lit x (1 - density) + depthFogColor x density in scene light before the exposure, "
                             "the same over the unit (no depth term); with Blood Moor night (0.15) a black albedo shows "
                             "about display 12, the floor monster3d METHOD rule 13 measured in game")
    if light_mask is None:
        return r
    use = [L for L in lights if L["mask"] is not None and int(L["mask"]) & light_mask and L["power"] > 0]
    if not use:
        r.assumptions.append("no vis light shares a bit with lightMask %d: the model is lit by ambient alone" % light_mask)
        r.light = replace(r.light, key_col=(0.0, 0.0, 0.0))
        return r
    use.sort(key=lambda L: -L["power"])
    k = use[0]
    pts = tuple({"name": L["name"], "pos": tuple(1e4 * x for x in light_towards(L["quat"])), "radius": 1e6, "atten": 0.0,
                 "color": [c * L["power"] * factor for c in L["color"]], "directional": True} for L in use[1:])
    r.light = replace(r.light, key_dir=light_towards(k["quat"]), key_col=tuple(c * k["power"] * factor for c in k["color"]),
                      points=pts)
    r.meta["light_mask"] = light_mask
    r.meta["unit_key"] = {x: k[x] for x in ("name", "power", "color", "mask")}
    r.meta["directional"] = [L["name"] for L in use[1:]]
    r.assumptions = [a for a in r.assumptions if not a.startswith("key colour")] + [
        "lights by lightMask %d: key %s, directional %s; colour x power x characterBrightnessFactor each"
        % (light_mask, k["name"], ", ".join(L["name"] for L in use[1:]) or "none")]
    r.unknown = [u for u in r.unknown if not u.startswith(("light directions", "lightMask bits"))] + [
        "light directions: vis quaternion applied to -z in the viewer's axes (engine axes assumed equal)"]
    return r


def add_unit_light(r: Rig, light: float, rgb, vis: dict | None = None, gain: float = 1.0, height: float | None = None,
                   radius: float | None = None) -> Rig:
    """The unit's own light (D2R: UnitLightComponent, UnitTranslationLayer::UpdateUnitLights, the debug toggle "Draw
    Monster Lights"), for a unit whose monstats2 row has `Light` > 0 (radius) and light-r/g/b (colour 0..255).
    Strength and reach come from the vis file's unitLightPower, unitLightAttenuation, unitLightDistanceScaler and
    unitLightDistanceOffsetRatio (act 1 outdoors night: 500, 5.0, 1.5, 0.5). The form is the viewer's point light
    (colour x power x (1 - (d/r)^2)^atten x N.L); assumed, not read from the shader:
      radius  = Light x 2 world units per sub-tile x unitLightDistanceScaler     (`radius` overrides)
      height  = radius x unitLightDistanceOffsetRatio above the feet, on the unit's axis   (`height` overrides)
      colour  = rgb/255 x unitLightPower x characterBrightnessFactor x gain
    A light at the unit's origin: only right for a unit rendered alone at the origin (render, sign-off), not for scenes."""
    v = vis or {}
    power = float(v.get("unitLightPower", 500.0))
    att = float(v.get("unitLightAttenuation", 5.0))
    scal = float(v.get("unitLightDistanceScaler", 1.5))
    off = float(v.get("unitLightDistanceOffsetRatio", 0.5))
    rad = float(radius) if radius else float(light) * 2.0 * scal
    h = float(height) if height is not None else rad * off
    f = float(r.meta.get("unit_factor", UNIT_FACTOR))
    col = [c / 255.0 * power * f * gain for c in rgb]
    pt = {"name": "unit_light", "pos": (0.0, h, 0.0), "radius": rad, "atten": att, "color": col, "unit_light": True}
    r.light = replace(r.light, points=tuple(r.light.points) + (pt,))
    r.meta["unit_light"] = {"light": light, "rgb": list(rgb), "gain": gain, "radius": rad, "height": h, "atten": att,
                            "power": power}
    r.assumptions.append("unit light (monstats2 Light %g, rgb %s): point at height %.2f, radius %.2f units, atten %g, "
                         "colour rgb/255 x unitLightPower %g x characterBrightnessFactor x gain %g; off for corpses"
                         % (light, list(rgb), h, rad, att, power, gain))
    return r


def _visual_data(path) -> dict:
    for e in json.loads(Path(path).read_text(encoding="utf-8")).get("entities", []):
        for c in e.get("components", []):
            if c.get("type") == "VisualDataComponent":
                return c
    return {}


PRESETS = {"default": default, "game": game}


def resolve(spec: str | None) -> Rig:
    """`--rig` value: a preset name, `vis:<file>` or a rig JSON path."""
    if not spec:
        return default()
    if spec in PRESETS:
        return PRESETS[spec]()
    if spec.startswith("vis:"):
        path, *opts = spec[4:].split(";")
        r = from_vis(path)
        o = dict(x.split("=", 1) for x in opts if "=" in x)
        if "env" in o:       # env=E: environment reflection colour (grey), e.g. 6.03 (viewer cal2, METHOD rule 15 anchor)
            e = float(o["env"])
            r.light = replace(r.light, env_col=(e, e, e))
            r.unknown = [u for u in r.unknown if not u.startswith("environment reflection")]
            r.assumptions.append("env colour %g: a black dielectric (~4 %% reflection) shows display L ~36 at Blood Moor "
                                 "night (monster3d METHOD rule 15), so env = srgb_decode(36/255) / (0.04 x exposure)" % e)
            if "envtint" in o:   # envtint=key|fog|R,G,B: the environment's colour, scaled to BT.709 luma 1 (env level kept)
                vd, t = _visual_data(path), o["envtint"]
                if t == "key":
                    t = next((L["color"] for L in r.lights if L.get("name") == "global_key_light"), [1.0, 1.0, 1.0])
                elif t == "fog":
                    t = [float((vd.get("depthFogColor") or {}).get(k, 1.0)) for k in "xyz"]
                else:
                    t = [float(x) for x in t.split(",")]
                y = 0.2126 * t[0] + 0.7152 * t[1] + 0.0722 * t[2]
                r.light = replace(r.light, env_col=tuple(e * c / y for c in t))
                r.assumptions.append("env tint %s (luma 1): the game's night IBL is assumed this colour" % [round(c, 3) for c in t])
        if "amb" in o:       # amb=S[,key|fog|R,G,B]: ambient (the game's SH sky irradiance, cb0[1..9] of ps_models_p)
            S, *t = o["amb"].split(",", 1)
            base = r.light.ambient
            y0 = 0.2126 * base[0] + 0.7152 * base[1] + 0.0722 * base[2]
            if t:
                t = t[0]
                if t == "key":
                    tt = next((L["color"] for L in r.lights if L.get("name") == "global_key_light"), [1.0, 1.0, 1.0])
                elif t == "fog":
                    tt = [float((_visual_data(path).get("depthFogColor") or {}).get(k, 1.0)) for k in "xyz"]
                else:
                    tt = [float(x) for x in t.split(",")]
                y = 0.2126 * tt[0] + 0.7152 * tt[1] + 0.0722 * tt[2]
                base = tuple(y0 * c / y for c in tt)
            r.light = replace(r.light, ambient=tuple(float(S) * c for c in base))
            r.assumptions.append("ambient %s (x%s, tint %s): stands in for the game's runtime SH sky irradiance"
                                 % ([round(c, 3) for c in r.light.ambient], S, t[0] if t else "default"))
        if o.get("tone") == "lut":   # the game's LUT colour path (tone.lut_chain) [;peak=nits][;curve=W,x0,y0,x1,y1]
            r.tone = "lut"
            r.post["peak"] = float(o.get("peak", 250.0))
            if "curve" in o:
                r.post["curve"] = [float(x) for x in o["curve"].split(",")]
            r.assumptions = [a for a in r.assumptions if not a.startswith("tone chain colour")] + [
                "tone: cs_lut_combine_c colour path (AP1, gamut expansion, ICtCp EETF to %g nits, sRGB 2.4); max-RGB curve "
                "%s" % (r.post["peak"], "W,x0,y0,x1,y1 = %s" % r.post["curve"] if "curve" in r.post else "off (values unknown)")]
        if "bloom" in o:     # bloom=gain[,levels]: vis bloomCutoff / bloomIntensity, tone.bloom (needs tone=lut)
            g, *lv = [float(x) for x in o["bloom"].split(",")]
            vd = _visual_data(path)
            r.post["bloom"] = {"cutoff": float(vd.get("bloomCutoff", 1.0)), "intensity": float(vd.get("bloomIntensity", 1.0)),
                               "levels": int(lv[0]) if lv else 5, "gain": g}
            r.assumptions.append("bloom %s: equal level weights x gain (level weights not in the bytecode)" % r.post["bloom"])
        if "vc" in o:        # vc=brightness,strength[,live]: tone.value_curve (hypothesis; needs tone=lut)
            b, st, *rest = o["vc"].split(",")
            vd = _visual_data(path)
            pts = vd.get("characterContrastPoints") or {}
            r.post["value"] = {"brightness": float(b), "strength": float(st),
                               "points": [float(pts.get(k, d)) for k, d in zip("xyzw", (0.25, 0.25, 0.75, 0.99))],
                               "live_only": "live" in rest}
            r.assumptions.append("unit value curve (ps_models_p, cb2[18..19]) %s: hypothesis" % r.post["value"])
        if "unit" in o:      # unit=Light,R,G,B (monstats2) [;ulgain=G][;ulh=H][;ulr=R]
            lt, *rgb = [float(x) for x in o["unit"].split(",")]
            vd = {}
            for e in json.loads(Path(path).read_text(encoding="utf-8")).get("entities", []):
                for c in e.get("components", []):
                    if c.get("type") == "VisualDataComponent":
                        vd = c
            add_unit_light(r, lt, rgb, vd, float(o.get("ulgain", 1.0)), float(o["ulh"]) if "ulh" in o else None,
                           float(o["ulr"]) if "ulr" in o else None)
        return r
    return load(spec)

