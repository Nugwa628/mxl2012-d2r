"""Recolour a D2R HD effect: a hue/saturation/brightness-shifted copy of its gradient textures (docs/hd-effects.md section 6).

D2R draws an effect with a PopcornFX `.particles` file. 51 of 373 missile and 74 of 331 overlay definitions take their
colour from RGBA8 gradient textures (`data/hd/vfx/textures/gradient/T_FX_*.texture`, 256 x 16); the rest has colours
baked into the particle program, which cannot be edited. The texture paths are stored as `<1 byte length><path>` inside
the `.particles` file, so a path replaced by one of the same length is safe (the technique of tools/missile_art.py).

For a recolour (Median's art is vanilla art in another colour, tools/art_provenance.py) this module
  - finds the colourful gradient textures of an effect's particle files (RGBA8 under textures/gradient, mean saturation
    >= MIN_SAT; alpha ramps and grey ramps are left alone),
  - writes a hue/saturation/value shifted copy of each under a same-length path (tag = hash of the shift),
  - writes a patched copy of the `.particles` file (data/hd/vfx/particles/mxl/<name>.particles) and a definition whose
    VfxDefinitionComponents point at it.
A few effects need more than a shift (TINT_OVERRIDES, keyed by the D2R definition and Median's art): a ramp named there
is recoloured even when it is grey-ish, by mapping its brightness onto an explicit colour ramp (`ramp_pixels`), because a
hue turn of a near-white ramp stays near-white (bug #403: the fire bolt that is a recoloured Ice Blast).
A hand pick (data/hd-effects-picks.tsv) can name a ramp of RAMPS in its `tint` column (`pick_spec`): its effect's colourful
gradients, or the ones the cell names, are mapped onto that ramp and nothing else of the effect changes.
An effect with no colourful gradient is reported as not recolourable (effects_hd.py then chooses the effect of the
nearest colour instead). Patched particles are not yet confirmed in game for every effect: see docs/hd-effects.md.

The particles and gradients are D2R files the baseline extraction lacks: they are read through fxpaths.d2r_file (the
shared D2R file cache that tools/lane_setup.py fills from the committed list tools/data/d2r_vfx_files.txt, else a game
slot's CASC when MXL_SLOT is set). A file that is in neither is recorded in MISSING and its effect counts as not
recolourable, so the build still runs; `py -3 tools/hd_recolour.py list` rewrites the list from what the last
effects_hd.py run asked for (work/mod/hd_recolour.json).

Size: a recoloured texture keeps the original's format, size and mip count, a patched .particles file only swaps paths
of the same length, and a definition keeps its name length (`recolour_name`), so no recoloured asset is larger than the
D2R file it comes from (checked in `recolour_def`).
"""
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import d2r_texture  # noqa: E402
from colour_shift import shift_pixels  # noqa: E402,F401  (moved there so the item pictures can use it without a game slot)
import fxpaths  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D2R = fxpaths.D2R
VFX_LIST = fxpaths.VFX_LIST
MIN_SAT = 0.18
TEX_RE = re.compile(rb"data/hd/vfx/textures/")
ASKED: set[str] = set()     # every D2R vfx file asked for (for the list)
WRITTEN: dict[str, str] = {}  # file written ('data/hd/...') -> the D2R file it is a copy of (size check)
MISSING: set[str] = set()   # asked for but neither extracted nor cached (and no slot to read it from)


def casc_read(path: str) -> bytes:
    """A D2R file (path 'data/hd/...'): the baseline extraction, the shared cache, else a slot's CASC when MXL_SLOT /
    MXL_D2R_GAME is set (fxpaths.d2r_file caches it). b'' when it is nowhere."""
    ASKED.add(path)
    for base in (D2R, fxpaths.D2R_CACHE):
        if (base / path).exists():
            return (base / path).read_bytes()
    if os.environ.get("MXL_SLOT") or os.environ.get("MXL_D2R_GAME"):
        try:
            return fxpaths.d2r_file(path).read_bytes()
        except Exception:  # noqa: BLE001  (a file CASC does not have)
            pass
    MISSING.add(path)
    return b""


def texture_refs(data: bytes) -> list[str]:
    """Texture paths stored in a .particles file (length-prefixed strings)."""
    out = []
    for m in TEX_RE.finditer(data):
        n = data[m.start() - 1] if m.start() else 0
        p = data[m.start():m.start() + n]
        if n and p.endswith(b".texture") and len(p) == n:
            out.append(p.decode())
    return list(dict.fromkeys(out))


def parse_texture(d: bytes):
    import struct
    _m, v, w, h = struct.unpack_from("<4I", d, 0)
    n = (v >> 24) & 0xFF
    mips = []
    for i in range(n):
        size, off = struct.unpack_from("<II", d, 0x24 + 8 * i)
        pos = 0x28 + 8 * i + off
        mips.append(d[pos:pos + size])
    return v & 0xFF, w, h, mips


_grad: dict[str, np.ndarray | None] = {}
_pix: dict[str, np.ndarray | None] = {}

# Per-effect tint rules: (D2R definition: missile model or overlay definition name, Median art) -> {"name", "ramps":
# {gradient texture: colour stops}}. A gradient named there is recoloured by `ramp_pixels` with those stops instead of
# the hue shift, whatever its saturation. Stops are (position 0..1, r, g, b).
FIRE_RAMP = ((0.0, 190, 52, 6), (0.35, 240, 104, 16), (0.7, 255, 160, 40), (1.0, 255, 214, 110))
VIOLET_RAMP = ((0.0, 120, 16, 176), (0.35, 176, 40, 232), (0.7, 214, 100, 255), (1.0, 240, 184, 255))
TINT_OVERRIDES: dict[tuple[str, str], dict] = {
    # bug #403: Median's fire bolt art (newfiremissile) is an orange Ice Blast; D2R's Ice Blast takes most of its colour
    # from T_FX_IceBolt_gradient, light blue to white (saturation 0.126, under MIN_SAT), so the shift left it blue-white
    ("ice_blast", "newfiremissile"): {
        "name": "fire", "ramps": {"data/hd/vfx/textures/gradient/T_FX_IceBolt_gradient.texture": FIRE_RAMP}},
    # bug #404: Dark Power's nova (purplefrostnova) is a violet Frost Nova; Frost Nova's only colour ramp,
    # T_FX_Bluelightning_Gradient, is a pale light blue (saturation 0.338), so the hue turn gave a pale indigo
    ("frost_nova", "purplefrostnova"): {
        "name": "violet", "ramps": {"data/hd/vfx/textures/gradient/T_FX_Bluelightning_Gradient.texture": VIOLET_RAMP}},
}
# Ramps a hand pick can name in its `tint` column (data/hd-effects-picks.tsv, lane picktint): Median's classic colours
GOLD_RAMP = ((0.0, 120, 60, 0), (0.35, 200, 110, 8), (0.7, 240, 160, 24), (1.0, 255, 190, 40))
GREEN_RAMP = ((0.0, 18, 70, 8), (0.35, 48, 138, 26), (0.7, 104, 208, 56), (1.0, 196, 255, 148))
RED_RAMP = ((0.0, 110, 0, 0), (0.35, 196, 18, 8), (0.7, 255, 64, 36), (1.0, 255, 186, 166))
RAMPS = {"fire": FIRE_RAMP, "violet": VIOLET_RAMP, "gold": GOLD_RAMP, "green": GREEN_RAMP, "red": RED_RAMP}


def gradient_pixels(path: str) -> np.ndarray | None:
    """(h, w, 4) uint8 pixels of an RGBA8 texture under textures/gradient (else None)."""
    if path not in _pix:
        res = None
        if "/gradient/" in path:
            try:
                fmt, w, h, mips = parse_texture(casc_read(path))
                if fmt == d2r_texture.FMT_RGBA8 and len(mips[0]) >= w * h * 4:
                    res = np.frombuffer(mips[0][:w * h * 4], np.uint8).reshape(h, w, 4)
            except Exception:
                res = None
        _pix[path] = res
    return _pix[path]


def colour_gradient(path: str) -> np.ndarray | None:
    """(h, w, 4) uint8 pixels of an RGBA8 gradient texture with a real colour (else None)."""
    if path not in _grad:
        res = None
        a = gradient_pixels(path)
        if a is not None:
            rgb = a[:, :, :3].astype(np.float32) / 255
            mx, mn = rgb.max(2), rgb.min(2)
            sat = np.where(mx > 0.05, (mx - mn) / np.maximum(mx, 1e-6), 0)
            wgt = mx
            if (sat * wgt).sum() / max(wgt.sum(), 1e-6) >= MIN_SAT:
                res = a
        _grad[path] = res
    return _grad[path]


def ramp_pixels(a: np.ndarray, stops) -> np.ndarray:
    """The pixels recoloured along `stops` ((t, r, g, b), t rising 0..1): a pixel's luma, scaled from the texture's
    darkest (t 0) to its brightest (t 1), picks the colour; alpha is kept."""
    y = a[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    lo, hi = float(y.min()), float(y.max())
    t = (y - lo) / (hi - lo) if hi > lo else np.ones_like(y)
    xs = [st[0] for st in stops]
    res = a.copy()
    for k in range(3):
        res[..., k] = np.clip(np.rint(np.interp(t, xs, [st[k + 1] for st in stops])), 0, 255).astype(np.uint8)
    return res


def with_override(spec: dict, model: str, art: str) -> dict:
    """spec plus the effect's TINT_OVERRIDES rule ("override": its name, "ramps"); spec itself when it has none."""
    o = TINT_OVERRIDES.get((model.lower(), art.lower()))
    if not o:
        return spec
    return {**spec, "override": o["name"], "ramps": o["ramps"], "label": f"{spec['label']} {o['name']} ramp"}


def parse_tint(text: str) -> tuple[str, tuple[str, ...]] | None:
    """A pick's `tint` cell: '' -> None; '<ramp>' -> (ramp, ()): every colourful gradient of the effect; '<ramp>:<stem>+<stem>'
    -> (ramp, stems): only the gradients of those file stems, whatever their saturation (a grey-ish colour ramp).
    ValueError for an unknown ramp."""
    text = text.strip()
    if not text:
        return None
    ramp, _, rest = text.partition(":")
    ramp = ramp.strip().lower()
    if ramp not in RAMPS:
        raise ValueError(f"unknown tint ramp {ramp!r} (known: {', '.join(sorted(RAMPS))})")
    return ramp, tuple(x.strip() for x in rest.split("+") if x.strip())


def pick_spec(tint: str, particles: list[str]) -> dict | None:
    """The recolour of a hand pick's effect (its particle files) by its `tint` cell: the gradients it names (else its
    colourful ones) mapped onto the ramp by `ramp_pixels`; nothing else of the effect changes ("only"). None when no
    such gradient is there (or the files are not cached)."""
    ramp, stems = parse_tint(tint)
    want = {s.lower() for s in stems}
    texs = [t for p in particles for t in texture_refs(casc_read(p))
            if gradient_pixels(t) is not None
            and (Path(t).stem.lower() in want if want else colour_gradient(t) is not None)]
    if not texs:
        return None
    name = ramp + (":" + "+".join(sorted(want)) if want else "")
    return {"hue": 0.0, "sat": 0.0, "val": 0.0, "override": f"pick {name}", "only": True,
            "ramps": {t: RAMPS[ramp] for t in dict.fromkeys(texs)}, "label": f"{name} ramp (hand pick)"}


def spec_of(shift: dict | None, m_art: dict | None, c_art: dict | None) -> dict:
    """The colour change from the vanilla art (c) to Median's (m): provenance shift, else the mean colours."""
    if shift and "hue" in shift:
        hue, sat, val = shift["hue"], shift["sat"], shift["val"]
    else:
        (h1, s1, v1), (h2, s2, v2) = m_art["hsv"], c_art["hsv"]
        hue = (h1 - h2 + 0.5) % 1.0 - 0.5
        sat, val = s1 - s2, math.log2(max(v1, 0.03) / max(v2, 0.03))
    hue, sat, val = round(max(-0.5, min(0.5, hue)), 2), round(max(-0.9, min(0.9, sat)), 2), round(max(-2.0, min(2.0, val)), 1)
    return {"hue": hue, "sat": sat, "val": val, "label": f"hue {hue:+.2f} sat {sat:+.2f} val {val:+.1f}"}


def tag_of(spec: dict, source: str = "") -> str:
    """6 hex digits naming a shift; with `source` (the path or name being copied) unique per source too, so two sources
    whose shortened names agree never share a file."""
    key = f"{spec['hue']}/{spec['sat']}/{spec['val']}" + (f"/{spec['override']}" if spec.get("override") else "") \
        + (f"/{source}" if source else "")
    return hashlib.md5(key.encode()).hexdigest()[:6]


def new_texture_path(path: str, tag: str) -> str:
    """A path in the same folder and of the same length (the .particles file stores it length-prefixed)."""
    folder, _, name = path.rpartition("/")
    stem = name[:-len(".texture")]
    t = f"_{tag}"
    if len(stem) <= len(t) + 3:
        raise ValueError(f"texture name too short to tag: {path}")
    return f"{folder}/{stem[:len(stem) - len(t)]}{t}.texture"


def recolourable(particles: str, spec: dict | None = None) -> list[str]:
    """The gradients of a .particles file that a recolour by `spec` changes (colourful ones, and its override's ramps)."""
    ramps = (spec or {}).get("ramps", {})
    only = (spec or {}).get("only")  # a hand pick's tint: its ramps and nothing else
    return [t for t in texture_refs(casc_read(particles))
            if (t in ramps and gradient_pixels(t) is not None) or (not only and colour_gradient(t) is not None)]


def _defs_particles(d: dict) -> list[str]:
    return [c["filename"] for e in d.get("entities", []) for c in e["components"]
            if c["type"] == "VfxDefinitionComponent" and c.get("filename")]


def can_recolour(d: dict, spec: dict | None = None) -> bool:
    return any(recolourable(p, spec) for p in _defs_particles(d))


def recolour_particles(out: Path | None, particles: str, spec: dict) -> tuple[str, dict[str, str]] | None:
    """Write the patched .particles file and the shifted gradients under `out` (work/mod/data; None: write nothing).
    (new path, textures)."""
    grads = recolourable(particles, spec)
    ramps = spec.get("ramps", {})
    if not grads:
        return None
    data = casc_read(particles)
    repl = {}
    for g in grads:
        n = new_texture_path(g, tag_of(spec, g))
        if out is not None:
            _fmt, _w, _h, mips = parse_texture(casc_read(g))
            px = (ramp_pixels(gradient_pixels(g), ramps[g]) if g in ramps
                  else shift_pixels(colour_gradient(g), spec["hue"], spec["sat"], spec["val"]))
            d2r_texture.write_rgba(out / n.split("/", 1)[1], px, mips=len(mips))  # same mips: at most D2R's size
            WRITTEN[n] = g
        needle = bytes([len(g)]) + g.encode()
        data = data.replace(needle, bytes([len(n)]) + n.encode())
        repl[g] = n
    name = Path(particles).stem
    new = f"data/hd/vfx/particles/mxl/{name[:40]}_{tag_of(spec, particles)}.particles"
    if out is not None:
        p = out / new.split("/", 1)[1]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        WRITTEN[new] = particles
    return new, repl


def recolour_name(name: str, spec: dict) -> str:
    """A name for the recoloured copy of the definition `name`, as long as it (so the definition does not grow):
    the end of the name becomes `_<tag>`; names too short for that get `mxl_<name>_c<tag>`."""
    t = f"_{tag_of(spec, name)}"
    return f"{name[:len(name) - len(t)]}{t}" if len(name) >= len(t) + 3 else f"mxl_{name}_c{tag_of(spec, name)}"


def recolour_def(out: Path | None, d: dict, spec: dict, name: str) -> dict | None:
    """The definition with every colourful effect recoloured, or None when none of its particles can be (out None: a dry
    run that writes no file). Texture dependencies are renamed in place, never added."""
    import copy
    d = copy.deepcopy(d)
    d["name"] = name
    swaps, any_ = {}, False
    texs = {}
    for e in d.get("entities", []):
        for c in e["components"]:
            if c["type"] == "VfxDefinitionComponent" and c.get("filename"):
                r = recolour_particles(out, c["filename"], spec)
                if r:
                    swaps[c["filename"]] = r[0]
                    texs.update(r[1])
                    c["filename"] = r[0]
                    any_ = True
    if not any_:
        return None
    deps = d.get("dependencies", {})
    for ent in deps.get("particles", []):
        ent["path"] = swaps.get(ent["path"], ent["path"])
    for ent in deps.get("textures", []):
        ent["path"] = texs.get(ent["path"], ent["path"])
    return d


def size(d: dict) -> int:
    return len(json.dumps(d, separators=(",", ":")).encode("utf-8"))


# ---- hooks of tools/effects_hd.py -----------------------------------------------------------------
TOO_LARGE: list[str] = []   # definitions a recolour would make larger than D2R's (not recoloured)


def fits(src: Path, d: dict, spec: dict, name: str) -> bool:
    """The recoloured copy of the definition d (file src) would exist and be no larger than src."""
    nd = recolour_def(None, d, spec, name)
    if nd is None:
        return False
    if size(nd) > src.stat().st_size:
        TOO_LARGE.append(src.name)
        return False
    return True


def plan_missile(hdm: Path):
    """recolour(c, shift, m_art, c_art, art) -> spec when the D2R missile row c's effect can be recoloured, else None
    (art: Median's art name, for TINT_OVERRIDES)."""
    def plan(c, shift, m_art, c_art, art=""):
        src = hdm / f"{c.model}.json"
        d = json.loads(src.read_text("utf-8-sig"))
        spec = with_override(spec_of(shift, m_art, c_art), c.model, art)
        return spec if fits(src, d, spec, recolour_name(d.get("name") or c.model, spec)) else None
    return plan


def plan_overlay(hdo: Path, norm_key):
    def plan(c, shift, m_art, c_art, art=""):
        src = hdo / c.folder / f"{norm_key(c.name)}.json"
        d = json.loads(src.read_text("utf-8-sig"))
        spec = with_override(spec_of(shift, m_art, c_art), d.get("name", ""), art)
        return spec if fits(src, d, spec, d.get("name", "")) else None
    return plan


def plan_pick_missile(hdm: Path):
    """pick(model, tint) -> spec when the hand-picked D2R missile effect `model` can be tinted by the pick's `tint` cell
    (and its copy is no larger than D2R's), else None."""
    def plan(model, tint):
        src = hdm / f"{model}.json"
        d = json.loads(src.read_text("utf-8-sig"))
        spec = pick_spec(tint, _defs_particles(d))
        return spec if spec and fits(src, d, spec, recolour_name(d.get("name") or model, spec)) else None
    return plan


def plan_pick_overlay(hdo: Path):
    """pick(effect 'folder/name', tint) -> spec for a hand-picked overlay definition, else None."""
    def plan(effect, tint):
        src = hdo / f"{effect}.json"
        d = json.loads(src.read_text("utf-8-sig"))
        spec = pick_spec(tint, _defs_particles(d))
        return spec if spec and fits(src, d, spec, d.get("name", "")) else None
    return plan


def recolour_missile(out: Path, model: str, spec: dict, hdm: Path | None = None) -> dict:
    """The recoloured copy of D2R's missile definition `model` (its "name" is the new model name)."""
    hdm = hdm or D2R / "data" / "hd" / "missiles"
    d = json.loads((hdm / f"{model}.json").read_text("utf-8-sig"))
    nd = recolour_def(out, d, spec, recolour_name(d.get("name") or model, spec))
    if nd is None:
        raise ValueError(f"{model}: nothing to recolour")
    return nd


def recolour_overlay(out: Path, d: dict, spec: dict) -> dict:
    nd = recolour_def(out, d, spec, d.get("name", ""))
    return nd if nd is not None else d


# ---- the list of D2R files the recolours read ------------------------------------------------------
def sizes(out: Path) -> tuple[int, list[str]]:
    """(bytes of every file written, the files larger than the D2R file they copy) under `out` (work/mod/data)."""
    total, larger = 0, []
    for new, src in sorted(WRITTEN.items()):
        n = (out / new.split("/", 1)[1]).stat().st_size
        total += n
        o = D2R / src if (D2R / src).exists() else fxpaths.D2R_CACHE / src
        if o.exists() and n > o.stat().st_size:
            larger.append(new)
    return total, larger


def write_report(path: Path, done: list[dict], out: Path) -> tuple[int, list[str]]:
    """work/mod/hd_recolour.json: the recolours made, bytes written, larger-than-D2R files (none by construction), and
    the D2R vfx files asked for / missing."""
    total, larger = sizes(out)
    path.write_text(json.dumps({"recolours": done, "bytes": total, "larger_than_d2r": larger, "written": WRITTEN,
                                "asked": sorted(ASKED), "missing": sorted(MISSING)}, indent=1), encoding="utf-8")
    return total, larger


def clean(report: Path, out: Path) -> int:
    """Deletes the files the last run wrote (its report's `written`), so a changed shift leaves no stale copy in the mod
    when effects_hd.py runs on its own (tools/build.py starts from an empty work/mod anyway)."""
    if not report.exists():
        return 0
    n = 0
    for new in json.loads(report.read_text("utf-8")).get("written", {}):
        f = out / new.split("/", 1)[1]
        if f.is_file():
            f.unlink()
            n += 1
    return n


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["list"])
    ap.add_argument("--report", default=str(fxpaths.MOD / "hd_recolour.json"))
    a = ap.parse_args()
    rep = json.loads(Path(a.report).read_text("utf-8"))
    files = sorted(set(rep["asked"]) - set(rep["missing"]))
    if rep["missing"]:
        print(f"{len(rep['missing'])} files were missing in that run (set MXL_SLOT=2|3|4 and run effects_hd.py again)")
    VFX_LIST.write_text("# D2R files tools/hd_recolour.py reads (cached by tools/lane_setup.py); "
                        "written by `py -3 tools/hd_recolour.py list`\n" + "\n".join(files) + "\n", encoding="utf-8")
    print(f"{len(files)} files -> {VFX_LIST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
