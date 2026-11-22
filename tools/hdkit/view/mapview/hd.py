"""The HD map: a map's preset (data/hd/env/preset/...json) drawn with hdkit's wgpu renderer in the game camera, on the
classic frame's pixels (frame.py), so a cell range shows the same ground in both renders.

Preset lookup (mod first for source mod): hd/env/preset/mxl2012/<map>.json (the build moves Median's own maps there,
tools/ds1_paths.py), then hd/env/preset/<map>.json, over the roots: a working copy's data folder, the built mod data
(MAPVIEW_MOD_DATA, default the newest release package under /d2work/runs/relpkg), then CASC (slot 5's game folder,
read-only, cached; hdkit.view.casc).

Layers: terrain (the baked terrain.model, one biome layer projected from above: preset.py), walls (entities and prefab
placements with a WallTransparencyComponent), props (other model entities), prefabs (other prefab members), lights (the
preset's point lights, nearest 8 to the frame's centre: the renderer's limit), objects (.ds1 object markers drawn as in
the classic overlay). Placements whose origin lies more than MARGIN cells outside the range are skipped (the terrain never).

Not drawn: decals (DecalDefinitionComponent, TerrainDecal/Stamp), particles (Vfx), the biome's per-tile layer blend and
grass, spot lights, physics; the light is hdkit's `game` rig (not the biome's vis file), preset light power is uncalibrated.
"""
from __future__ import annotations

import math
import os
import re
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from .. import camera, preset
from .frame import Frame

HD_LAYERS = ("terrain", "decals", "walls", "props", "prefabs", "lights", "fx", "units", "objects", "grid")
DEFAULT_HD = {"terrain", "decals", "walls", "props", "prefabs", "lights", "fx", "units"}
MARGIN = 3          # cells beside and above a crop on the screen (select)
MARGIN_BELOW = 12   # cells below a crop on the screen: a tall wall or building standing there reaches up into the frame
# merged floor / paint models (sprite_scene.CHUNK_MODEL, maps_flat.CHUNK_MODEL): pivot at the chunk's first cell, art over the
# next 16 x 16 cells, so a crop keeps those whose pivot lies up to 16 cells before it
CHUNK_MODEL = re.compile(r"/(wallsprite/m/[^/]+/rock_|flat/[^/]+/paint_)[^/]*\.model$", re.I)
CHUNK_REACH = 16 * 10.0
LIGHT_GAIN = 1.0 / 400.0      # preset power -> renderer colour scale with the old `game`/`default` rigs (uncalibrated)
VIS_LIGHT_GAIN = 0.01         # with the map's own vis rig: preset light colour x power x this (calibrated on cathy3 4K captures)
WORLD_MASK = 1                # lightMask bit of the environment in the vis files (global key 9, fill/back 1; preset lights 1)
AMBIENT = 0.004               # world ambient (the IBL's share) per unit of the vis file's iblIntensity, grey (calibrated, cathy3)
PLAYER_LIGHT = 10.0           # the player's light radius in sub-tiles for --player (a fresh character; calibrated)
PLAYER_GAIN = 0.15            # x playerUnitLightPower x characterBrightnessFactor (calibrated, cathy3)
_R = []                       # one wgpu Renderer per process (textures cached across renders)
_FS = {}


def parse_layers(spec):
    if not spec:
        return set(DEFAULT_HD)
    items = [s.strip() for s in spec.split(",") if s.strip()]
    out = set(DEFAULT_HD) if all(s[0] in "+-" for s in items) else set()
    for s in items:
        if s == "all":
            out |= set(HD_LAYERS)
        elif s.startswith("-"):
            out.discard(s[1:])
        else:
            n = s.lstrip("+")
            if n not in HD_LAYERS:
                raise ValueError("unknown HD layer %s (one of %s)" % (n, ", ".join(HD_LAYERS)))
            out.add(n)
    return out


def mod_data() -> Path | None:
    env = os.environ.get("MAPVIEW_MOD_DATA")
    if env:
        return Path(env)
    cands = sorted(Path("/d2work/runs/relpkg").glob("*/mxl2012/mxl2012.mpq/data"), key=lambda p: p.stat().st_mtime)
    cands = [c for c in cands if (c / "hd" / "env" / "preset").is_dir()]
    return cands[-1] if cands else None


def roots_for(source: str, work_data: Path | None = None, extra=None) -> list:
    specs = []
    if work_data:
        specs.append("work=%s" % work_data)
    if extra:
        specs += list(extra)
    else:
        if source == "mod":
            m = mod_data()
            if m:
                specs.append("mod=%s" % m)
        specs.append("casc")
    return specs


def fs_for(specs):
    from .. import vfs
    k = tuple(specs)
    if k not in _FS:
        _FS[k] = vfs.Layered(vfs.parse_roots(list(specs)))
    fs = _FS[k]
    return fs


def find_preset(fs, key: str, source: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    cands = (["hd/env/preset/mxl2012/%s.json" % key] if source == "mod" else []) + ["hd/env/preset/%s.json" % key]
    for c in cands:
        if fs.exists(c):
            return c
    return None


def renderer():
    if not _R:
        from ..gpu import Renderer
        _R.append(Renderer(msaa=4))
    return _R[0]


def release():
    """Frees what renders keep between calls (the renderer's texture and skinning caches, the file systems' read caches):
    a process that renders many pictures in a row (maps_rounds) stays at the memory of one picture."""
    import gc
    if _R:
        _R[0]._tex.clear()
        _R[0]._tex_bytes = 0
        _R[0]._skinned.clear()
    _FS.clear()
    from .. import scene as scene_mod
    scene_mod._TEXTURES.clear()
    gc.collect()


def select(sc, fr: Frame, layers: set, cull: bool = True):
    """The placements of the layers that can show in the frame. Culled on the screen, not in a box of cells: a crop's
    rectangle on the screen covers cells far outside its own cell range (screen x follows x - y). A placement's ground
    point (a merged chunk: the corners of its 16 x 16 cells) must lie within the frame widened by MARGIN cells to the
    sides and above, and MARGIN_BELOW cells below (a tall wall standing below the frame reaches up into it)."""
    keep = []
    for p in sc.placements:
        if p.kind == "terrain":
            if "terrain" in layers:
                keep.append(p)
            continue
        lay = "walls" if p.wall else ("prefabs" if p.kind == "prefab" else "props")
        if p.kind == "object":
            lay = "objects"
        if lay not in layers:
            continue
        if cull:
            reach = CHUNK_REACH / 10.0 if CHUNK_MODEL.search(p.model or "") else 0.0   # a chunk reaches 16 cells on
            if not fr.near(float(p.matrix[0, 3]) / 10.0, float(p.matrix[2, 3]) / 10.0, MARGIN, MARGIN_BELOW, reach):
                continue
        keep.append(p)
    return keep


def preset_lights(fs, logical: str, gain: float = LIGHT_GAIN):
    """Point lights of a preset, and its spot lights as points (half way along the spot's axis, radius its distance x
    tan(angle / 2) + half the distance): [{name, pos, radius, color, atten}] in the renderer's form."""
    d = preset._read_json(fs, logical)
    out = []
    for ent in d.get("entities", []):
        c = {k["type"]: k for k in ent.get("components", [])}
        pl = c.get("PointLightDefinitionComponent")
        sl = c.get("SpotLightDefinitionComponent")
        if not (pl or sl):
            continue
        M = preset.trs(c.get("TransformDefinitionComponent"))
        L = pl or sl
        col = L.get("color") or {}
        pw = float(L.get("power", 0.0)) * gain * float(L.get("diffuseContribution", 1.0))
        pos = M[:3, 3]
        if pl:
            rad = float(pl.get("radius", 10.0))
        else:
            fwd = M[:3, :3] @ np.array([0.0, 0.0, -1.0])
            fwd /= max(np.linalg.norm(fwd), 1e-9)
            dist = float(sl.get("distance", 20.0))
            pos = pos + fwd * dist * 0.5
            rad = dist * math.tan(math.radians(float(sl.get("angle", 45.0))) / 2.0) + dist * 0.5
        out.append({"name": ent.get("name", ""), "pos": tuple(float(v) for v in pos), "radius": rad,
                    "atten": float(L.get("attenuation", 2.0)), "spot": bool(sl),
                    "color": [pw * float(col.get(k, 1.0)) for k in "xyz"]})
    return out


def _vis_component(fs, logical) -> dict:
    try:
        for e in preset._read_json(fs, logical).get("entities", []):
            for c in e.get("components", []):
                if c.get("type") == "VisualDataComponent":
                    return c
    except (OSError, FileNotFoundError, ValueError):
        pass
    return {}


def vis_rig(fs, biome_logical: str | None, prefer: str = "day"):
    """hdkit's game rig from the biome's own visual data file (data/hd/env/vis), for environment models (lightMask 19);
    None without one. The file is copied to MAPVIEW_OUT/_vis/ (rig.from_vis reads a path)."""
    from .. import rig as rigmod
    if not biome_logical:
        return None, None
    try:
        b = preset._read_json(fs, biome_logical)
    except (OSError, FileNotFoundError, ValueError):
        return None, None
    names = [v.get("visualDataFilename") for v in b.get("visualDataFilenames") or [] if v.get("visualDataFilename")]
    if not names:
        return None, None
    pick = next((n for n in names if prefer in n.lower()), names[0])
    try:
        data = fs.read(pick)
    except (OSError, FileNotFoundError):
        return None, pick
    out = Path(os.environ.get("MAPVIEW_OUT", "/d2work/runs/mapview")) / "_vis"
    out.mkdir(parents=True, exist_ok=True)
    f = out / pick.replace("/", "_")
    f.write_bytes(data)
    return rigmod.from_vis(str(f), light_mask=WORLD_MASK), pick


K_4K = 40.73          # px per world unit at 3840x2160 (camera.K_1600x900 x 2.4; the 4K capture calibration)


def texel_density(prep, cam) -> dict:
    """Screen pixels per albedo texel at 3840x2160, area-weighted over every textured triangle drawn (occlusion ignored):
    1 is the texture's full detail on screen, 3.6 is a 1x classic atlas (each classic pixel a 3.6 px block)."""
    import numpy as _np
    vals, wts = [], []
    r, u, _w = cam.basis()
    for d in prep.draws:
        if d.terrain or d.uv_tris is None or not len(d.uv_tris) or d.material.startswith("mapview:"):
            continue
        W = d.world
        P = _np.stack([W @ r, W @ u], -1) * K_4K
        sa = 0.5 * _np.abs((P[:, 1, 0] - P[:, 0, 0]) * (P[:, 2, 1] - P[:, 0, 1]) - (P[:, 2, 0] - P[:, 0, 0]) * (P[:, 1, 1] - P[:, 0, 1]))
        T = d.uv_tris
        ta = 0.5 * _np.abs((T[:, 1, 0] - T[:, 0, 0]) * (T[:, 2, 1] - T[:, 0, 1]) - (T[:, 2, 0] - T[:, 0, 0]) * (T[:, 1, 1] - T[:, 0, 1]))
        ok = (sa > 1e-3) & (ta > 1e-6)
        vals.append(_np.sqrt(sa[ok] / ta[ok]))
        wts.append(sa[ok])
    if not vals:
        return {}
    v, w = _np.concatenate(vals), _np.concatenate(wts)
    o = _np.argsort(v)
    c = _np.cumsum(w[o]) / w.sum()
    q = lambda f: float(v[o][min(len(v) - 1, _np.searchsorted(c, f))])   # noqa: E731
    return {"px_per_texel_4k_median": round(q(0.5), 2), "p90": round(q(0.9), 2),
            "share_over_2px": round(float(w[v > 2.0].sum() / w.sum()), 3)}


def view_box(fr: Frame, cam, top: float = 40.0):
    """Pixel bbox of the frame's cells as boxes from the ground to `top` units, for orbit views."""
    xs = [fr.x0 * 10.0, (fr.x1 + 1) * 10.0]
    zs = [fr.y0 * 10.0, (fr.y1 + 1) * 10.0]
    P = np.array([[x, y, z] for x in xs for z in zs for y in (0.0, top)])
    px = cam.to_pixels(P, (0.0, 0.0))
    return px.min(0), px.max(0)


def render(src, fr: Frame, layers=None, preset_path=None, roots=None, work_data=None, el=None, az=None, rig="vis", ss=1,
           gate=True, log=None, light_gain=None, player=None, pass_name="lit"):
    """-> (PIL RGBA image, info). Default angles: pixel-aligned with the classic frame; other angles (orbit): the frame's
    cells fitted into an image of about the same size."""
    from PIL import Image
    from .. import rig as rigmod
    t0 = time.time()
    layers = parse_layers(layers) if not isinstance(layers, set) else layers
    if gate:
        from ... import gpugate
        rd = gpugate.check()
        if not rd.free:
            raise RuntimeError("GPU gate: %s (gate=False / --no-gate overrides)" % rd.why)
    from .. import scene as scene_mod
    # a frame far below 1:1 needs none of the top mips: at scale s < 1 one classic pixel is s px, so floor(log2(1 / s))
    # levels are dropped (texels stay at or under one screen pixel even for 1x art); saves most of the memory of 4x atlases
    scene_mod.MIP_DROP = max(0, int(math.floor(math.log2(1.0 / fr.scale)))) if fr.scale < 1.0 else 0
    # and below 1:1 no texture side over 2048: a 4x atlas's texel is then still under half a screen pixel (moskvich whole
    # map at 0.4x: 9 GB with the full 4096 x 8192 atlases)
    scene_mod.MAX_TEX_SIDE = 2048 if fr.scale < 1.0 else None
    specs = roots_for(src.source, work_data, roots)
    fs = fs_for(specs)
    logical = find_preset(fs, src.key, src.source, preset_path)
    info = {"renderer": "hd", "map": src.key, "source": src.source, "roots": specs, "preset": logical,
            "layers": sorted(layers), "frame": fr.as_dict(), "mip_drop": scene_mod.MIP_DROP}
    if logical is None:
        raise FileNotFoundError("no HD preset for %s (looked for hd/env/preset/[mxl2012/]%s.json in %s)"
                                % (src.key, src.key, specs))
    sc = preset.build_scene(fs, logical)
    pj = preset._read_json(fs, logical)
    pl = select(sc, fr, layers)
    terr = [p for p in pl if p.kind == "terrain"]
    pl = [p for p in pl if p.kind != "terrain"]
    sc2 = replace(sc, placements=pl, lights=[])
    R = renderer()
    default_view = el is None and az is None
    el = camera.GAME_EL if el is None else float(el)
    az = camera.GAME_AZ if az is None else float(az)
    k = camera.K_1600x900 * fr.hd_scale()
    cam = camera.OrthoCamera(el, az, k)
    if default_view:
        size, origin = fr.size, fr.hd_origin()
    else:
        lo, hi = view_box(fr, cam)
        W0, H0 = fr.size
        fit = min(W0 / max(hi[0] - lo[0], 1), H0 / max(hi[1] - lo[1], 1))
        cam = camera.OrthoCamera(el, az, k * fit)
        lo, hi = view_box(fr, cam)
        size = (int(math.ceil(hi[0] - lo[0])) + 8, int(math.ceil(hi[1] - lo[1])) + 8)
        origin = (-lo[0] + 4, -lo[1] + 4)
        info["orbit"] = {"el": el, "az": az, "note": "pixels do not line up with the classic frame at these angles"}
    prep = preset.prepare_scene(R, fs, sc2, cam, log=(log or (lambda s: None)))
    from . import ground as G, units as U
    from .. import scene as S_, gpu as gpu_
    gnd = None
    if "terrain" in layers:
        gnd = G.Ground(fs, pj, src.ds, sc.biome, terr[0].model if terr else None)
        arrays = gnd.arrays(R)
        p3, p4 = gnd.p3p4()
        if terr:
            for t in terr:
                try:
                    unit = S_.load_unit(fs, t.model)
                except (OSError, FileNotFoundError, KeyError, ValueError) as e:
                    info.setdefault("notes", []).append("terrain %s not loaded (%s)" % (t.model, e))
                    continue
                for part in unit.parts:
                    for m in part.meshes:
                        P = m.pos @ t.matrix[:3, :3].T + t.matrix[:3, 3]
                        Nn = m.nrm @ t.matrix[:3, :3].T
                        Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-9)
                        prep.draws.append(R.terrain_draw(P, Nn, m.tan, m.uv, m.tris, arrays, p3, p4))
        else:
            x0, x1 = max(0, fr.x0 - MARGIN) * 10.0, min(src.ds.width, fr.x1 + 1 + MARGIN) * 10.0
            z0, z1 = max(0, fr.y0 - MARGIN) * 10.0, min(src.ds.height, fr.y1 + 1 + MARGIN) * 10.0
            P = np.array([[x0, 0, z0], [x1, 0, z0], [x1, 0, z1], [x0, 0, z1]], float)
            Nn = np.tile([0.0, 1.0, 0.0], (4, 1))
            Tn = np.tile([1.0, 0.0, 0.0, 1.0], (4, 1))
            prep.draws.append(R.terrain_draw(P, Nn, Tn, np.zeros((4, 2)), np.array([[0, 1, 2], [0, 2, 3]]), arrays, p3, p4,
                                             "ground plane"))
        info["ground"] = gnd.info()
    if "decals" in layers:
        dus, dn = G.decal_units(fs, pj, fr)
        for unit in dus:
            prep.draws += R.prepare(unit, None, 0.0, 0.0, cam, light_class="world").draws
        info["decals"] = dict(dn, drawn=len(dus))
    extra_pts = []
    if "fx" in layers or "units" in layers:
        ux = U.scene_extras(fs, pj, src, fr, R, cam, fx="fx" in layers, objects="units" in layers, log=log)
        prep.draws += ux["draws"]
        extra_pts = ux["lights"]
        info["units"] = ux["info"]
    info["texel_density"] = texel_density(prep, cam)
    if rig == "vis":
        rg, vis = vis_rig(fs, gnd.ground_biome if gnd else (G._biome_path(sc.biome) if sc.biome else None))
        if rg is None:
            rg = rigmod.resolve("game")
            info.setdefault("notes", []).append("no vis file for the biome: the generic game rig")
        info["vis"] = vis
        gain = VIS_LIGHT_GAIN if light_gain is None else light_gain
        vd = _vis_component(fs, vis) if vis else {}
        amb = AMBIENT * float(vd.get("iblIntensity", 1.0))
        rg = replace(rg, light=replace(rg.light, ambient=(amb, amb, amb), env_col=(amb, amb, amb)))
        if player is not None:
            px, pz = player[0] * 10.0, player[1] * 10.0         # cell coordinates (fractions: the exact spot)
            rad = PLAYER_LIGHT * 2.0 * float(vd.get("playerUnitLightDistanceScaler", 1.333))
            pw = float(vd.get("playerUnitLightPower", 2125.0)) * float(vd.get("characterBrightnessFactor", 0.4)) * PLAYER_GAIN
            extra_pts = list(extra_pts) + [{"name": "player", "pos": (px, rad * 0.5, pz), "radius": rad,
                                            "atten": float(vd.get("playerUnitLightAttenuation", 5.5)),
                                            "color": [pw / gain] * 3}]
            info["player_light"] = {"cell": list(player), "radius": rad, "power": pw}
    else:
        rg = rigmod.resolve(rig)
        gain = LIGHT_GAIN if light_gain is None else light_gain
    pts = []
    if "lights" in layers:
        allp = preset_lights(fs, logical, gain) + [dict(p, color=[c * gain for c in p["color"]]) for p in extra_pts]
        pts = allp
        info["lights"] = {"preset_lights": len(allp) - len(extra_pts), "fx_object_lights": len(extra_pts),
                          "gain": gain, "per_draw_max": gpu_.MAX_POINTS}
    rg = replace(rg, light=replace(rg.light, floor_clip=0.0, points=tuple(rg.light.points) + tuple(pts)))
    if prep.draws:
        arr = R.render(prep, cam, size, origin, pass_name, None, pass_name == "lit", ss, None, None,
                       rig=rg if pass_name == "lit" else None)
    else:
        arr = np.zeros((size[1], size[0], 4), np.uint8)
    img = Image.fromarray(arr, "RGBA")
    if "objects" in layers or "grid" in layers:
        if default_view:
            from . import classic
            opt = classic.Options(layers=({"objects", "labels"} if "objects" in layers else set()) |
                                  ({"grid"} if "grid" in layers else set()))
            classic.overlay(img, src, fr, opt)
        else:
            info.setdefault("notes", []).append("object / grid overlays are drawn only at the game angles")
    info.update({"size": list(size), "origin_px": list(origin), "camera": {"el": el, "az": az, "k": cam.k},
                 "placements": len(pl), "placements_in_preset": len(sc.placements), "draws": len(prep.draws),
                 "skipped_components": sc.skipped, "biome": sc.biome,
                 "notes": info.get("notes", []) + list(prep.notes[:20]) +
                 ["approximate: ground splat (no path masks, grass, clutter), decals flat on the ground, fire effects as "
                  "glow cards, spot lights as points; light rig %s" % rig],
                 "seconds": round(time.time() - t0, 2), "adapter": dict(getattr(R.adapter, "info", {}) or {})})
    if log:
        log("hd %s: %dx%d px, %d placements, %.1f s" % (src.key, size[0], size[1], len(pl), info["seconds"]))
    return img, info


def entities_near(fs, logical: str, cx: float, cy: float, near: float = 0.0) -> list:
    """Preset entities whose origin lies on cell (cx, cy) (or within `near` cells of it): index, name, components,
    model, prefab, transform."""
    d = preset._read_json(fs, logical)
    out = []
    lo_x, hi_x = (cx - near) * 10.0, (cx + 1 + near) * 10.0
    lo_z, hi_z = (cy - near) * 10.0, (cy + 1 + near) * 10.0
    for i, ent in enumerate(d.get("entities", [])):
        c = {k["type"]: k for k in ent.get("components", [])}
        td = c.get("TransformDefinitionComponent")
        if not td:
            continue
        p = td.get("position") or {}
        x, z = float(p.get("x", 0)), float(p.get("z", 0))
        if not (lo_x <= x < hi_x and lo_z <= z < hi_z):
            continue
        e = {"index": i, "name": ent.get("name"), "id": ent.get("id"), "components": sorted(c),
             "position": [x, float(p.get("y", 0)), z], "cell": [x / 10.0, z / 10.0],
             "orientation": td.get("orientation"), "scale": td.get("scale")}
        if "ModelDefinitionComponent" in c:
            e["model"] = c["ModelDefinitionComponent"].get("filename")
        if "PrefabPlacementDefinitionComponent" in c:
            e["prefab"] = c["PrefabPlacementDefinitionComponent"].get("prefab")
        if "WallTransparencyComponent" in c:
            e["wall"] = True
        for lt in ("PointLightDefinitionComponent", "SpotLightDefinitionComponent"):
            if lt in c:
                e["light"] = {k: v for k, v in c[lt].items() if k not in ("type", "name")}
        out.append(e)
    return out
