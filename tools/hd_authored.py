"""Authored HD effects: D2R definitions made of layers of D2R effects, with edited particle files (docs/hd-effects-authoring.md).

`data/hd-effects-authored.json` (committed, our own data) names effects that D2R does not have. Each is one missile
(`UnitDefinition`) or overlay (`OverlayDefinition`) built from layers:

    {"name": "mxl_thunderstone", "kind": "missile", "base": "rock_large", "why": "...",   (an overlay's base: folder/name)
     "layers": [
        {"from": "missile:rock_large", "scale": 1.5},
        {"from": "overlay:common/progressive_lightning_1", "scale": 0.8,
         "edit": {"hide": "mesh", "ramps": {"<gradient texture>": "rainbow"}, "textures": {"<old>": "<new>"}}},
        {"particles": "data/hd/vfx/particles/...", "offset": [0, 0, 0]}]}

  - `from` copies the entities of a D2R definition that draw something (a particle file and its transform; the
    missile root is taken from the first missile layer), `particles` makes one entity for a particle file;
  - `scale` multiplies the layer's transforms (one is added where an entity has none), `offset` moves it;
  - `edit` is a recipe of tools/hd_particles.py `apply` for every particle file of the layer (`hide` / `show`
    renderers, `textures`, `props`), plus `ramps`: a gradient texture of the file mapped onto a colour ramp of
    tools/hd_recolour.py `RAMPS` (written as a new RGBA8 texture under data/hd/vfx/textures/mxl/authored/), and `tint`:
    the colour the effect's code computes multiplied by [r, g, b, a] (tools/hd_cbvm.py `tint`; a list tints every grey
    colour stream, {"<stream>": [r, g, b, a]} names them). An edited file is written under
    data/hd/vfx/particles/mxl/authored/<effect>/;
  - `base` is the D2R effect the hand pick's scale and reports count from; an overlay goes to its base's folder (the
    row's HD Character).

A hand pick (data/hd-effects-picks.tsv) names an authored effect in its `effect` column like a D2R one; tools/effects_hd.py
asks `build` for the definition. D2R files come through hd_recolour.casc_read (the shared cache, else a slot's CASC).
"""
from __future__ import annotations

import copy
import hashlib
import json
import zlib
from pathlib import Path

import fxpaths
import hd_cbvm as hc
import hd_particles as hp
import hd_recolour as hr
import d2r_texture

AUTHORED_JSON = fxpaths.ROOT / "data" / "hd-effects-authored.json"
PART_DIR = "data/hd/vfx/particles/mxl/authored"
TEX_DIR = "data/hd/vfx/textures/mxl/authored"
DEP_KEYS = ["particles", "models", "skeletons", "animations", "textures", "physics", "json", "variantdata",
            "objecteffects", "other"]


def load(path: Path | None = AUTHORED_JSON) -> dict[str, dict]:
    """name -> entry; SystemExit on a malformed entry."""
    if path is None or not Path(path).exists():
        return {}
    doc = json.loads(Path(path).read_text("utf-8"))
    out = {}
    for e in doc.get("effects", []):
        name = e.get("name", "")
        where = f"{path}: effect {name or '?'}"
        if not name or e.get("kind") not in ("missile", "overlay") or not e.get("base") or not e.get("layers"):
            raise SystemExit(f"{where}: needs name, kind (missile/overlay), base and layers")
        for ly in e["layers"]:
            if bool(ly.get("from")) == bool(ly.get("particles")):
                raise SystemExit(f"{where}: a layer has either `from` or `particles`")
            for t, ramp in ly.get("edit", {}).get("ramps", {}).items():
                if ramp not in hr.RAMPS:
                    raise SystemExit(f"{where}: unknown ramp {ramp!r} for {t} (known: {', '.join(sorted(hr.RAMPS))})")
        if name in out:
            raise SystemExit(f"{where}: named twice")
        out[name] = e
    return out


def entity_id(name: str, k: int) -> int:
    return zlib.crc32(f"{name}/{k}".encode()) & 0x7FFFFFFF


def transform(scale: float = 1.0, offset=(0.0, 0.0, 0.0)) -> dict:
    return {"type": "TransformDefinitionComponent", "name": "component_transform_mxl",
            "position": dict(zip("xyz", map(float, offset))), "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            "scale": {"x": scale, "y": scale, "z": scale}, "inheritOnlyPosition": False}


def place(entity: dict, scale: float, offset) -> dict:
    """The entity with its transform scaled (and moved by `offset`); one added where it has none."""
    e = copy.deepcopy(entity)
    comps = e["components"]
    tr = next((c for c in comps if c["type"] == "TransformDefinitionComponent"), None)
    if tr is None:
        if scale != 1 or any(offset):  # none needed: an entity without one keeps D2R's size (and a later scale skips it)
            comps.append(transform(scale, offset))
        return e
    for ax, d in zip("xyz", offset):
        tr["scale"][ax] = round(tr["scale"][ax] * scale, 4)
        tr["position"][ax] = round(tr["position"][ax] * scale + float(d), 4)
    return e


def source_definition(ref: str, hdm: Path, hdo: Path) -> dict:
    kind, _, name = ref.partition(":")
    p = (hdm / f"{name}.json") if kind == "missile" else (hdo / f"{name}.json") if kind == "overlay" else None
    if p is None or not p.exists():
        raise SystemExit(f"data/hd-effects-authored.json: no D2R definition {ref!r} (missile:<model> or overlay:<folder/name>)")
    return json.loads(p.read_text("utf-8-sig"))


def derived_texture(src: str, ramp: str) -> str:
    stem = Path(src).stem
    return f"{TEX_DIR}/{stem[:48]}_{ramp}_{hashlib.md5((src + ramp).encode()).hexdigest()[:6]}.texture"


def edit_particles(out: Path | None, effect: str, path: str, edit: dict, written: dict[str, str]) -> tuple[str, list[str]]:
    """The edited copy of a particle file (written under out = work/mod/data unless None): (new path, new textures)."""
    data = hr.casc_read(path)
    if not data:
        raise SystemExit(f"authored effect {effect}: D2R file {path} is not cached (tools/lane_setup.py, or MXL_SLOT=3)")
    names = set(hp.ParticleFile(data).strings)  # a layer's recipe applies to those of its files that name the texture
    texs = {o: n for o, n in edit.get("textures", {}).items() if o in names}
    for t, ramp in edit.get("ramps", {}).items():
        if t not in names:
            continue
        px = hr.gradient_pixels(t)
        if px is None:
            raise SystemExit(f"authored effect {effect}: {t} is not an RGBA8 gradient texture (or not cached)")
        n = derived_texture(t, ramp)
        if out is not None:
            _f, _w, _h, mips = hr.parse_texture(hr.casc_read(t))
            d2r_texture.write_rgba(out / n.split("/", 1)[1], hr.ramp_pixels(px, hr.RAMPS[ramp]), mips=len(mips))
            written[n] = t
        texs[t] = n
    new = hp.apply(data, {k: v for k, v in edit.items() if k not in ("ramps", "textures", "tint")}, texs)
    if "tint" in edit:  # colour computed by the effect's code: tools/hd_cbvm.py tint (a list = every grey colour stream)
        tints = edit["tint"]
        if not isinstance(tints, dict):
            tints = {st: tints for st in hc.colour_streams(new)}
            if not tints:
                raise SystemExit(f"authored effect {effect}: {path} computes no grey colour to tint (name the stream)")
        for stream, rgba in tints.items():
            new, _n = hc.tint(new, stream, rgba)
    np_ = f"{PART_DIR}/{effect.replace('/', '_')}/{Path(path).name}"
    if out is not None:
        p = out / np_.split("/", 1)[1]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(new)
        written[np_] = path
    return np_, list(texs.values())


def build(entry: dict, hdm: Path, hdo: Path, out: Path | None, written: dict[str, str] | None = None) -> dict:
    """The definition of an authored effect (its edited particle files and textures written under `out`)."""
    written = {} if written is None else written
    name, kind = entry["name"], entry["kind"]
    short = name.rsplit("/", 1)[-1]
    deps = {k: [] for k in DEP_KEYS}
    ents, root = [], None

    def dep(key: str, path: str):
        if path and {"path": path} not in deps[key]:
            deps[key].append({"path": path})

    for k, ly in enumerate(entry["layers"]):
        scale, offset = float(ly.get("scale", 1.0)), ly.get("offset", (0.0, 0.0, 0.0))
        if ly.get("from"):
            src = source_definition(ly["from"], hdm, hdo)
            for key in DEP_KEYS:
                for x in src.get("dependencies", {}).get(key, []):
                    dep(key, x["path"])
            layer = []
            for e in src.get("entities", []):
                if any(c["type"] == "UnitRootComponent" for c in e["components"]):
                    if root is None and kind == "missile":
                        root = copy.deepcopy(e)
                    continue
                if any(c["type"] == "UnitSourceSkillFilterComponent" and c.get("sourceSkill") for c in e["components"]):
                    continue  # drawn only for one D2R skill (Gleam's Shiver Armor entity)
                if any(c["type"] == "VfxDefinitionComponent" for c in e["components"]):
                    layer.append(place(e, scale, offset))
        else:
            layer = [{"type": "Entity", "name": f"entity_mxl{k}", "id": 0,
                      "components": [{"type": "VfxDefinitionComponent", "name": f"component_vfx_mxl{k}",
                                      "filename": ly["particles"], "hardKillOnDestroy": False}, transform(scale, offset)]}]
        for e in layer:
            for c in e["components"]:
                if c["type"] != "VfxDefinitionComponent" or not c.get("filename"):
                    continue
                if ly.get("edit"):
                    old = c["filename"]
                    c["filename"], texs = edit_particles(out, name, old, ly["edit"], written)
                    deps["particles"] = [x for x in deps["particles"] if x["path"] != old]
                    for t in texs:
                        dep("textures", t)
                dep("particles", c["filename"])
            e["name"] = f"{e['name']}_l{k}"
            ents.append(e)
    if not any(c["type"] == "VfxDefinitionComponent" for e in ents for c in e["components"]):
        raise SystemExit(f"authored effect {name}: its layers draw nothing")
    for i, e in enumerate(ents):
        e["id"] = entity_id(name, i)
    if kind == "missile":
        if root is None:
            root = {"type": "Entity", "name": "entity_root", "id": 0, "components": [
                {"type": "UnitRootComponent", "name": "component_root", "state_machine_filename": "",
                 "doNotInheritRotation": False, "rotationOverride": {"x": 0.0, "y": 0.3826834, "z": 0.0, "w": 0.9238795},
                 "doNotUseHDHeight": False, "hideAllMeshWhenInOpenedMode": False, "onCreateEventName": "", "animations": []}]}
        root["id"] = entity_id(name, -1)
        ents = [root] + ents
    return {"dependencies": deps, "type": "UnitDefinition" if kind == "missile" else "OverlayDefinition",
            "name": short, "entities": ents}


def edited_files(entry: dict, hdm: Path, hdo: Path) -> list[str]:
    """The D2R files an entry's edits read: the particle files of its layers with an `edit` and the gradients they ramp
    (for tools/data/d2r_vfx_files.txt, so every candidate builds from the shared cache, picked or not)."""
    out = []
    for ly in entry["layers"]:
        if not ly.get("edit"):
            continue
        if ly.get("particles"):
            out.append(ly["particles"])
        else:
            out += [c["filename"] for e in source_definition(ly["from"], hdm, hdo).get("entities", [])
                    for c in e["components"] if c["type"] == "VfxDefinitionComponent" and c.get("filename")]
        out += list(ly["edit"].get("ramps", {}))
    return out


def clean(out: Path) -> None:
    """Remove the edited particle files and textures of an earlier run (work/mod/data)."""
    import shutil
    for d in (PART_DIR, TEX_DIR):
        shutil.rmtree(out / d.split("/", 1)[1], ignore_errors=True)
