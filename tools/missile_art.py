"""Median's own missile and overlay animations as D2R HD sprite effects (Phase 5, docs/hd-effects.md).

D2R's HD effects are PopcornFX particle effects (data/hd/vfx/particles/*.particles, a baked binary we cannot author) that
JSON definitions (data/hd/missiles/<model>.json, data/hd/overlays/<folder>/<name>.json) instantiate. There is no 2D sprite
component, but D2R has one real sprite effect: the character-select campfire (data/hd/vfx/particles/env/ui/
vfx_character_create_fire.particles) plays a flipbook atlas (T_FX_fireFlipbook_64x64: 8 x 8 frames of 128 px, one
channel) through a gradient map. This tool clones that effect per Median animation and swaps its textures:

  1. decode Median's DCC (tools/dcc.py, direction 0), palette = D2R's units palette;
  2. resample the frames to 64 flipbook frames of 128 or 256 px cells (bilinear, premultiplied alpha), one BC4
     atlas of 1024 x 1024 or 2048 x 2048 (the mask = brightest colour channel x coverage, tools/d2r_texture.py);
  3. colour gradient (256 x 16 RGBA8): per mask level the mean colour of the sprite pixels at that level;
  4. copy the template .particles with its texture paths replaced by same-length paths to the new textures (the baked
     file stores each path with a one-byte length in front, so the length must not change); the template's other layers
     (glow, licks) get a black texture so only the flipbook shows;
  5. a UnitDefinition (missiles) or OverlayDefinition (overlays) JSON that plays the effect, scaled so one classic
     pixel keeps its size; missiles.json maps every Median missile using that CelFile to it; overlay.txt rows get the
     Character folder "mxl" (D2R's HD overlay folder column).

Input:  assets/median/data/global/{missiles,overlays}/*.dcc, work/mod/data/global/excel/{skills,missiles,overlay,states}.txt
Output: <out>/hd/vfx/textures/mxl/*.texture, <out>/hd/vfx/particles/mxl/*.particles, <out>/hd/missiles/mxl_*.json,
        <out>/hd/overlays/mxl/*.json, <out>/hd/missiles/missiles.json (updated), <out>/global/excel/overlay.txt (Character)
Usage:  python tools/missile_art.py [--class bar ...] [--all] [--out DIR] [--only KEY ...]
"""
import d2r_game  # noqa: E402
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import d2r_texture  # noqa: E402
import dcc  # noqa: E402
from txt_migrate import read_tsv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAME = d2r_game.read_game_dir()
D2R = ROOT / "extract" / "d2r" / "93847"
MXL = ROOT / "assets" / "median" / "data" / "global"
MOD = ROOT / "work" / "mod" / "data"
TEMPLATE = "data/hd/vfx/particles/env/ui/vfx_character_create_fire.particles"
TEX_DIR = "data/hd/vfx/textures/mxl/"
PARTICLE_DIR = "data/hd/vfx/particles/mxl/"
OVERLAY_FOLDER = "mxl"
GRID, FRAMES = 8, 64
CELLS = (128, 256)  # flipbook cell size in pixels: the small one when the animation is at most SMALL_MAX classic pixels
SMALL_MAX = 96
SCALE_MAX = 3.5  # upscale of a classic pixel, as tools/item_art.py
# The template's textures: flipbook -> atlas, gradient -> gradient, the others are layers we hide with a black mask.
T_ATLAS = "data/hd/vfx/textures/mask/T_FX_fireFlipbook_64x64.texture"
T_GRADIENT = "data/hd/vfx/textures/gradient/T_FX_flame_gradient_07.texture"
T_HIDE = ["data/hd/vfx/textures/mask/T_FX_radialGradient_Mask_soft_02.texture",
          "data/hd/vfx/textures/mask/T_FX_soft_glowcard.texture",
          "data/hd/vfx/textures/mask/T_FX_softFlame_mask_.texture",
          "data/hd/vfx/textures/mask/T_FX_fire_mask.texture"]
# World size of one flipbook cell at JSON scale 1 and of one classic pixel (a classic subtile is 32 px wide and about
# one yard); tuned in game (docs/hd-effects.md).
CELL_WORLD = 4.0
PIXEL_WORLD = 1 / 32
SCALE_MULT = 1.0  # --scale: multiplier on the effect scale (calibration)
CLASSES = {"ama": "amazon", "sor": "sorceress", "nec": "necromancer", "pal": "paladin", "bar": "barbarian",
           "dru": "druid", "ass": "assassin"}

_d2r_files = None
_palette = None


def d2r_has(kind: str, name: str) -> bool:
    global _d2r_files
    if _d2r_files is None:
        _d2r_files = {l.strip().lower() for l in (D2R / "filelist.txt").read_text("utf-8").splitlines()}
    return f"data:data/global/{kind}/{name.lower().replace(chr(92), '/')}.dcc" in _d2r_files


def units_palette() -> list[tuple[int, int, int]]:
    import skill_icons
    return skill_icons.palette()


def dcc_path(kind: str, name: str) -> Path:
    base = MXL / kind
    p = base / (name.replace("\\", "/") + ".dcc")
    if p.exists():
        return p
    want = name.replace("\\", "/").lower()  # case-insensitive lookup (Median's names mix cases)
    for q in base.rglob("*.dcc"):
        if q.relative_to(base).with_suffix("").as_posix().lower() == want:
            return q
    raise FileNotFoundError(p)


def key_of(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# ---------------------------------------------------------------- sprite sheet
def render_frames(path: Path, pal) -> tuple[list[Image.Image], tuple[int, int], tuple[int, int]]:
    """RGBA frames of direction 0, all on the direction's canvas; returns (frames, (w, h), (anchor x, anchor y))."""
    x0, y0, dw, dh, frames = dcc.decode(path.read_bytes())[0]
    lut = np.zeros((256, 4), np.uint8)
    for i, (r, g, b) in enumerate(pal):
        lut[i] = (r, g, b, 255)
    lut[0] = 0
    out = []
    for fx, fy, fw, fh, pix in frames:
        canvas = np.zeros((dh, dw, 4), np.uint8)
        canvas[fy - y0:fy - y0 + fh, fx - x0:fx - x0 + fw] = lut[np.frombuffer(pix, np.uint8).reshape(fh, fw)]
        out.append(Image.fromarray(canvas, "RGBA"))
    return out, (dw, dh), (-x0, -y0)


def build_sheet(frames: list[Image.Image], size: tuple[int, int], additive: bool):
    """(atlas mask (8 cells x 8 cells, uint8), gradient (16 x 256 x 4 uint8), classic pixels per cell)."""
    dw, dh = size
    CELL = CELLS[0] if max(dw, dh) <= SMALL_MAX else CELLS[1]
    ATLAS = GRID * CELL
    s = min(CELL / dw, CELL / dh, SCALE_MAX)
    w, h = max(1, round(dw * s)), max(1, round(dh * s))
    n = len(frames)
    atlas = np.zeros((ATLAS, ATLAS), np.uint8)
    levels = np.zeros((256, 3), np.float64)
    counts = np.zeros(256, np.float64)
    for i in range(FRAMES):
        src = frames[min(n - 1, i * n // FRAMES)]  # 64 slots over the n frames, same timing
        im = src.convert("RGBa").resize((w, h), Image.BILINEAR).convert("RGBA")
        a = np.asarray(im).astype(np.float32)
        cover = a[..., 3] / 255.0
        mask = a[..., :3].max(axis=2) / 255.0 * cover if additive else cover
        m = np.clip(np.rint(mask * 255), 0, 255).astype(np.uint8)
        cx, cy = (i % GRID) * CELL + (CELL - w) // 2, (i // GRID) * CELL + (CELL - h) // 2
        atlas[cy:cy + h, cx:cx + w] = m
        sel = m > 0
        idx = m[sel].astype(np.int64)
        for c in range(3):
            levels[:, c] += np.bincount(idx, weights=a[..., c][sel], minlength=256)
        counts += np.bincount(idx, minlength=256)
    grad = np.zeros((256, 3), np.float64)
    known = counts > 0
    for c in range(3):
        grad[known, c] = levels[known, c] / counts[known]
    xs = np.arange(256)
    if known.any():
        for c in range(3):  # fill unseen levels by interpolation, then smooth
            grad[:, c] = np.interp(xs, xs[known], grad[known, c])
            grad[:, c] = np.convolve(np.pad(grad[:, c], 4, mode="edge"), np.ones(9) / 9, mode="valid")
    ramp = np.concatenate([np.clip(np.rint(grad), 0, 255), np.full((256, 1), 255)], axis=1).astype(np.uint8)
    return atlas, np.repeat(ramp[None], 16, axis=0), CELL / s


# ---------------------------------------------------------------- template patching
def tex_name(prefix: str, length: int, seed: str) -> str:
    """A path under TEX_DIR that is exactly `length` characters long."""
    room = length - len(TEX_DIR) - len(".texture")
    tag = hashlib.md5(seed.encode()).hexdigest()[:6]
    stem = f"{prefix}_{tag}".ljust(room, "_")[:room]
    if room < len(tag) + 2:
        raise ValueError(f"path of {length} characters is too short for a texture name")
    return f"{TEX_DIR}{stem}.texture"


def patch_particles(template: bytes, repl: dict[str, str]) -> bytes:
    out = bytearray(template)
    for old, new in repl.items():
        assert len(old) == len(new), (old, new)
        needle = bytes([len(old)]) + old.encode()
        n = template.count(needle)
        if n < 1:
            raise ValueError(f"template has no texture {old}")
        out = bytearray(bytes(out).replace(needle, bytes([len(new)]) + new.encode()))
    return bytes(out)


def get_template() -> bytes:
    p = D2R / Path(TEMPLATE)
    if not p.exists():
        import native
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(native.casc_read(native.open_casc(GAME), "data:" + TEMPLATE))
    return p.read_bytes()


def quat_iso() -> dict:
    return {"x": 0.0, "y": 0.3826834, "z": 0.0, "w": 0.9238795}


def vfx_json(kind: str, name: str, particles: str, textures: list[str], k: float, height: float) -> dict:
    deps = {"particles": [{"path": particles}], "models": [], "skeletons": [], "animations": [],
            "textures": [{"path": t} for t in textures], "physics": [], "json": [], "variantdata": [],
            "objecteffects": [], "other": []}
    vfx = {"type": "VfxDefinitionComponent", "name": "component_vfx", "filename": particles, "hardKillOnDestroy": True}
    tr = {"type": "TransformDefinitionComponent", "name": "component_transform",
          "position": {"x": 0.0, "y": height, "z": 0.0}, "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
          "scale": {"x": k, "y": k, "z": k}, "inheritOnlyPosition": False}
    eid = int(hashlib.md5(name.encode()).hexdigest()[:7], 16)
    if kind == "missile":
        root = {"type": "Entity", "name": "entity_root", "id": eid, "components": [
            {"type": "UnitRootComponent", "name": "component_root", "state_machine_filename": "",
             "doNotInheritRotation": False, "rotationOverride": quat_iso(), "doNotUseHDHeight": False,
             "hideAllMeshWhenInOpenedMode": False, "onCreateEventName": "", "animations": []}]}
        return {"dependencies": deps, "type": "UnitDefinition", "name": name,
                "entities": [root, {"type": "Entity", "name": "entity_vfx1", "id": eid + 1, "components": [tr, vfx]}]}
    return {"dependencies": deps, "type": "OverlayDefinition", "name": name,
            "entities": [{"type": "Entity", "name": "entity_root", "id": eid, "components": [tr, vfx]}]}


# ---------------------------------------------------------------- what to convert
def art_of_classes(classes: list[str]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(missile CelFile -> missile names, overlay Filename -> overlay names) used by the classes' skills."""
    ex = MOD / "global" / "excel"
    sh, srows = read_tsv(ex / "skills.txt")
    mh, mrows = read_tsv(ex / "missiles.txt")
    oh, orows = read_tsv(ex / "overlay.txt")
    th, trows = read_tsv(ex / "states.txt")
    missiles = {r[0]: r for r in mrows if r[0]}
    overlays = {r[0]: r for r in orows if r[0]}
    states = {r[0]: r for r in trows if r[0]}
    sub = [c for c in mh if c.endswith(("SubMissile1", "SubMissile2", "SubMissile3", "SubMissile4")) or c == "ExplosionMissile"]
    s_cols = [c for c in ("srvmissile", "srvmissilea", "srvmissileb", "srvmissilec", "cltmissile", "cltmissilea",
                          "cltmissileb", "cltmissilec", "cltmissiled") if c in sh]
    o_cols = [c for c in ("castoverlay", "srvoverlay", "cltoverlaya", "cltoverlayb") if c in sh]
    st_cols = [c for c in ("castoverlay", "overlay1", "overlay2", "overlay3", "overlay4", "pgsvoverlay", "removerlay")
               if c in th]
    seen: list[str] = []

    def walk(name):
        if name in seen or name not in missiles:
            return
        seen.append(name)
        for c in sub:
            v = missiles[name][mh.index(c)]
            if v:
                walk(v)

    ovs: list[str] = []
    for r in srows:
        if not r[0] or r[sh.index("charclass")] not in classes or not r[sh.index("skilldesc")]:
            continue  # monster skills carry a class code too; only skills with a description are the player's
        for c in s_cols:
            if r[sh.index(c)]:
                walk(r[sh.index(c)])
        ovs += [r[sh.index(c)] for c in o_cols if r[sh.index(c)]]
        st = r[sh.index("aurastate")]
        if st in states:
            ovs += [states[st][th.index(c)] for c in st_cols if states[st][th.index(c)]]
    cels: dict[str, set[str]] = {}
    for n in seen:
        cel = missiles[n][mh.index("CelFile")]
        if cel and cel.lower() != "null" and not d2r_has("missiles", cel):
            cels.setdefault(cel, set()).add(n)
    fnames: dict[str, set[str]] = {}
    for o in dict.fromkeys(ovs):
        if o in overlays:
            f = overlays[o][oh.index("Filename")]
            if f and not d2r_has("overlays", f):
                fnames.setdefault(f, set()).add(o)
    return cels, fnames


def all_art() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Every Median-only missile CelFile and overlay Filename with an animation (the plan for all classes)."""
    ex = MOD / "global" / "excel"
    mh, mrows = read_tsv(ex / "missiles.txt")
    oh, orows = read_tsv(ex / "overlay.txt")
    cels: dict[str, set[str]] = {}
    for r in mrows:
        cel = r[mh.index("CelFile")]
        if r[0] and cel and cel.lower() != "null" and not d2r_has("missiles", cel):
            cels.setdefault(cel, set()).add(r[0])
    fnames: dict[str, set[str]] = {}
    for r in orows:
        f = r[oh.index("Filename")]
        if r[0] and f and not d2r_has("overlays", f):
            fnames.setdefault(f, set()).add(r[0])
    return cels, fnames


def is_additive(trans: str) -> bool:
    return trans not in ("", "0")


# ---------------------------------------------------------------- main
def convert(kind: str, art: str, users: set[str], out: Path, template: bytes, pal, trans: str, hide: dict[str, str],
           log: list[str]) -> str | None:
    try:
        path = dcc_path("missiles" if kind == "missile" else "overlays", art)
    except FileNotFoundError:
        log.append(f"| {kind} | {art} | missing in Median's files | |")
        return None
    frames, size, anchor = render_frames(path, pal)
    return emit(kind, art, users, out, template, frames, size, anchor, is_additive(trans) or kind == "overlay", hide, log)


def emit(kind: str, art: str, users: set[str], out: Path, template: bytes, frames: list[Image.Image],
         size: tuple[int, int], anchor: tuple[int, int], additive: bool, hide: dict[str, str], log: list[str]) -> str:
    """Writes the textures, the patched particles and the JSON for one animation; returns the model/overlay name."""
    atlas, grad, px_per_cell = build_sheet(frames, size, additive)
    key = key_of(art)
    t_atlas = tex_name("a_" + key, len(T_ATLAS), "atlas" + art)
    t_grad = tex_name("g_" + key, len(T_GRADIENT), "grad" + art)
    d2r_texture.write_bc4(out / "hd" / "vfx" / "textures" / "mxl" / Path(t_atlas).name, atlas, mips=atlas.shape[0].bit_length())
    d2r_texture.write_rgba(out / "hd" / "vfx" / "textures" / "mxl" / Path(t_grad).name, grad)
    repl = {T_ATLAS: t_atlas, T_GRADIENT: t_grad, **hide}
    particles = f"{PARTICLE_DIR}{key}.particles"
    dest = out / particles.replace("data/", "", 1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(patch_particles(template, repl))
    scale = px_per_cell * PIXEL_WORLD / CELL_WORLD * SCALE_MULT
    height = (size[1] - anchor[1]) * PIXEL_WORLD * 0.5  # centre of the sprite above the origin (classic: y down)
    name = f"mxl_{key}"
    # a missile model is shared by every missile using the CelFile; an overlay JSON is named after its overlay.txt row
    targets = ([(name, out / "hd" / "missiles" / f"{name}.json")] if kind == "missile" else
               [(u.lower(), out / "hd" / "overlays" / OVERLAY_FOLDER / f"{u.lower()}.json") for u in sorted(users)])
    for jname, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(vfx_json(kind, jname, particles, [t_atlas, t_grad], scale, max(height, 0.0)),
                                     separators=(",", ":")), encoding="utf-8")
    log.append(f"| {kind} | {art} | {len(frames)} frames {size[0]}x{size[1]}, additive={additive} "
               f"| {', '.join(sorted(users))[:80]} |")
    return name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class", dest="classes", action="append", help="class code (bar, sor, ...); default bar")
    ap.add_argument("--all", action="store_true", help="every Median-only animation, all classes")
    ap.add_argument("--only", action="append", default=[], help="only these CelFiles / overlay filenames")
    ap.add_argument("--out", default=str(MOD), help="mod data folder (default work/mod/data)")
    ap.add_argument("--scale", type=float, default=1.0, help="multiplier on the effect scale (calibration)")
    args = ap.parse_args()
    global SCALE_MULT
    SCALE_MULT = args.scale
    out = Path(args.out)
    cels, fnames = all_art() if args.all else art_of_classes(args.classes or ["bar"])
    if args.only:
        want = {w.lower() for w in args.only}
        cels = {k: v for k, v in cels.items() if k.lower() in want}
        fnames = {k: v for k, v in fnames.items() if k.lower() in want}
    ex = MOD / "global" / "excel"
    mh, mrows = read_tsv(ex / "missiles.txt")
    trans_of = {r[mh.index("CelFile")].lower(): r[mh.index("Trans")] for r in mrows if r[0]}
    template = get_template()
    # hidden layers: same-length black textures
    hide = {}
    for old in T_HIDE:
        hide[old] = tex_name("black", len(old), "black")
    black = d2r_texture
    for new in set(hide.values()):
        black.write_bc4(out / "hd" / "vfx" / "textures" / "mxl" / Path(new).name, np.zeros((4, 4), np.uint8))
    pal = units_palette()
    log: list[str] = []
    missile_models: dict[str, str] = {}
    for cel, users in sorted(cels.items()):
        name = convert("missile", cel, users, out, template, pal, trans_of.get(cel.lower(), "0"), hide, log)
        if name:
            for u in users:
                missile_models[u] = name
    overlay_done: dict[str, str] = {}
    for fn, users in sorted(fnames.items()):
        name = convert("overlay", fn, users, out, template, pal, "1", hide, log)
        if name:
            for u in users:
                overlay_done[u] = name
    # missiles.json: every Median missile that uses one of the CelFiles
    mj = out / "hd" / "missiles" / "missiles.json"
    base = mj if mj.exists() else D2R / "data" / "hd" / "missiles" / "missiles.json"
    hd = json.loads(base.read_text("utf-8-sig"))
    by_cel = {c.lower(): next(iter(v)) for c, v in cels.items()}
    count = 0
    for r in mrows:
        cel = r[mh.index("CelFile")].lower()
        if r[0] and cel in by_cel and missile_models.get(by_cel[cel]):
            hd[r[0].lower()] = missile_models[by_cel[cel]]
            count += 1
    mj.parent.mkdir(parents=True, exist_ok=True)
    mj.write_text(json.dumps(hd, separators=(",", ":")), encoding="utf-8")
    # overlay.txt (both banks): Character folder
    changed = 0
    for ov in (out / "global" / "excel" / "overlay.txt", out / "global" / "excel" / "base" / "overlay.txt"):
        if not ov.exists() or not overlay_done:
            continue
        text = ov.read_text("utf-8-sig")
        nl = "\r\n" if "\r\n" in text[:4096] else "\n"
        rows = [l.split("\t") for l in text.split(nl)]
        ci = rows[0].index("Character")
        for r in rows[1:]:
            if len(r) > ci and r[0] in overlay_done and not r[ci]:
                r[ci] = OVERLAY_FOLDER
                changed += 1
        ov.write_text(nl.join("\t".join(r) for r in rows), encoding="utf-8")
    report = ["# Median animations converted to HD sprite effects", "", "| Kind | Art | Source | Used by |", "|---|---|---|---|"]
    (out.parent / "missile_art_report.md").write_text("\n".join(report + log) + "\n", encoding="utf-8")
    print(f"missile_art: {len(cels)} missile + {len(fnames)} overlay animations -> HD sprite effects; "
          f"{count} missiles mapped, {changed} overlay rows given a Character folder")
    return 0


if __name__ == "__main__":
    sys.exit(main())
