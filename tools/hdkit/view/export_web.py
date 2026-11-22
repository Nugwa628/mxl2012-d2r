"""Export a unit to a compact local bundle for the browser page (hdkit/view/web): everything is decoded here, in Python,
by the same readers the CLI uses; the page only skins, samples the pre-sampled clips and draws with the same
shaders.wgsl.

  python -m hdkit.view export-web <unit json|.model> --root ... --out <bundle folder> [--refs ...]

Bundle layout (all little-endian):
  scene.json        what follows, plus the camera facts, the passes, the rigs, the state machine and the provenance
  mesh_<i>.bin      per mesh: pos, nrm (f32 or f64, whichever holds the decoded values exactly), tan (4), uv (2), tris
                    (u32), joints (u16, already remapped to skeleton bone indices), weights (u8; the CLI divides by 255)
  skel_<p>.bin      per part: the inverse world transforms (f64, bones x 16, row-major, as gr2.Skeleton.iwt)
  clip_<name>.bin   per clip: bone locals (pos 3, quat 4, scale/shear 9; f64) at t = min(i / fps, duration), i = 0..n-1,
                    from gr2.locals_at (the CLI's pose: exact B-spline, root translation dropped, clamped, no loop)
  tex/*.png         every mip level of every texture as the CLI decodes it (lossless RGBA PNG)
  tone.bin          tone.py's luminance table (_XS, _YS; f32) for the `game` tone in the page's present shader
  refs/*.png        CLI renders of chosen stills with their arguments, for the page's "match CLI" check

The shaders are not copied: the page loads hdkit/view/shaders.wgsl itself (the server maps it), and scene.json holds that
file's sha256 so the page can prove it runs the CLI's shader.
"""
import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np

from . import camera, gpu, gr2, player, rig as rig_mod, scene, tone

BUNDLE_VERSION = 1
ZOOM_RANGE = (1.0, 2.25)


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _exact_f32(a: np.ndarray) -> bool:
    return bool(np.array_equal(a.astype(np.float32).astype(np.float64), np.asarray(a, np.float64)))


def _rgba(arr: np.ndarray) -> np.ndarray:
    """The texel bytes gpu.Renderer._upload sends to the GPU."""
    return np.ascontiguousarray(arr[..., :4] if arr.shape[-1] >= 4 else np.dstack([arr, np.full(arr.shape[:2], 255, np.uint8)]),
                                np.uint8)


def _png(arr: np.ndarray, path: Path) -> str:
    from PIL import Image
    a = _rgba(arr)
    Image.fromarray(a, "RGBA").save(path, compress_level=6)
    return hashlib.sha256(a.tobytes()).hexdigest()


class _Writer:
    def __init__(self, out: Path):
        self.out = out
        self.files = []

    def blob(self, name: str, parts: list) -> dict:
        """One .bin of several arrays; returns {"file", "fields": {name: [offset, dtype, shape]}}."""
        fields, off, chunks = {}, 0, []
        for key, arr in parts:
            a = np.ascontiguousarray(arr)
            pad = (-off) % 8
            if pad:
                chunks.append(b"\0" * pad)
                off += pad
            fields[key] = [off, a.dtype.str.lstrip("<|="), list(a.shape)]
            b = a.astype(a.dtype.newbyteorder("<")).tobytes()
            chunks.append(b)
            off += len(b)
        (self.out / name).write_bytes(b"".join(chunks))
        self.files.append(name)
        return {"file": name, "bytes": off, "fields": fields}


def _texture(w: _Writer, tx: scene.Texture, stem: str) -> dict:
    (w.out / "tex").mkdir(exist_ok=True)
    mips = []
    for i, m in enumerate(tx.mips):
        rel = "tex/%s_m%02d.png" % (stem, i)
        h = _png(m, w.out / rel)
        w.files.append(rel)
        mips.append({"file": rel, "w": int(m.shape[1]), "h": int(m.shape[0]), "sha256": h})
    return {"logical": tx.logical, "srgb": bool(tx.srgb), "fmt": int(tx.fmt), "mips": mips}


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def mesh_arrays(m: gr2.Mesh, sk) -> list:
    """The arrays of one mesh as the page reads them (see the module note)."""
    fl = np.float32 if all(_exact_f32(x) for x in (m.pos, m.nrm, m.tan, m.uv)) else np.float64
    parts = [("pos", m.pos.astype(fl)), ("nrm", m.nrm.astype(fl)), ("tan", m.tan.astype(fl)), ("uv", m.uv.astype(fl)),
             ("tris", m.tris.astype(np.uint32))]
    if m.joints is not None and sk is not None:
        remap = np.array([sk.idx.get(n, 0) for n in m.bones], int)
        parts.append(("joints", remap[m.joints].astype(np.uint16)))
        wb = np.round(m.weights * 255.0)
        if not np.allclose(wb / 255.0, m.weights, rtol=0, atol=1e-12):
            parts.append(("weights_f64", m.weights.astype(np.float64)))
        else:
            parts.append(("weights", wb.astype(np.uint8)))
    return parts


def sample_clip(sk: gr2.Skeleton, clip: gr2.Clip, fps: float) -> np.ndarray:
    """(n, bones, 16) f64 bone locals at t = min(i / fps, duration): exactly what the CLI's render poses with."""
    n = max(1, int(math.ceil(clip.duration * fps - 1e-9)) + 1)
    out = np.zeros((n, len(sk.names), 16))
    for i in range(n):
        loc, _t, _u, _n = gr2.locals_at(sk, clip, min(i / fps, clip.duration))
        for b, (p, q, s) in enumerate(loc):
            out[i, b, 0:3], out[i, b, 3:7], out[i, b, 7:16] = p, q, np.asarray(s).ravel()
    return out


def state_machine(fs, unit_logical: str, clips: dict, classic: dict | None) -> dict | None:
    """Modes of the unit's state machine as the page's player needs them (player.Player's rules, per mode token)."""
    if fs is None or not unit_logical.lower().endswith(".json"):
        return None
    u = json.loads(fs.read(unit_logical).decode("utf-8"))
    smf = None
    for e in u.get("entities", []):
        for c in e.get("components", []):
            if c.get("type") == "UnitRootComponent" and c.get("state_machine_filename"):
                smf = c["state_machine_filename"]
    if not smf:
        return None
    logical = smf[len("data/"):] if smf.lower().startswith("data/") and not fs.exists(smf) else smf
    if not fs.exists(logical):
        return {"file": smf, "missing": True}
    sm = player.StateMachine.from_json(fs.read(logical))
    pl_clip = player.Player(sm, clips, classic, timing="clip")
    pl_cls = player.Player(sm, clips, classic, timing="classic")
    modes = {}
    for st in sm.states:
        tok = player.MODE_TOKENS.get(st.mode, str(st.mode))
        name = sm.clip_name(st.mode)
        modes[tok] = {"mode": st.mode, "state": st.name, "state_id": st.state_id, "loop": st.loop, "clip": name,
                      "bindings": st.bindings, "length_clip": pl_clip.length(st.mode),
                      "length_classic": pl_cls.length(st.mode) if classic else None}
    return {"file": smf, "name": sm.name, "modes": modes,
            "crossfade": [[a, b, s] for (a, b), s in sorted(sm.crossfade.items())],
            "classic": classic, "timing_note": player.__doc__.split("Timing")[1].split("Loops")[0].strip()}


def export(unit: scene.Unit, out, fs=None, asset: str = "", fps: float = 50.0, classic: dict | None = None,
           rigs: dict | None = None, notes=None, msaa: int = 4, aniso: int = 16, ref_aniso: int = 1) -> dict:
    """Write the bundle of a loaded scene.Unit (model kind) into `out`; returns scene.json as a dict."""
    if unit.kind != "model":
        raise ValueError("export-web takes a unit or model, not a card")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    w = _Writer(out)
    shader = Path(gpu.SHADER)
    parts, skel_of = [], {}
    for pi, part in enumerate(unit.parts):
        sk = part.skeleton
        pd = {"name": part.name, "model": part.model, "meshes": [], "textures": {}, "layers": [], "skeleton": None}
        if sk is not None:
            rest = np.zeros((len(sk.names), 16))
            for b, (p, q, s) in enumerate(sk.rest):
                rest[b, 0:3], rest[b, 3:7], rest[b, 7:16] = p, q, np.asarray(s).ravel()
            pd["skeleton"] = dict(w.blob("skel_%d.bin" % pi, [("iwt", sk.iwt.reshape(len(sk.names), 16)),
                                                              ("rest", rest)]),
                                  names=sk.names, parent=sk.parent, name=sk.name)
            skel_of[pi] = sk
        for kind, usage in (("alb", "AlbedoTexture"), ("nrm", "NormalTexture"), ("orm", "ORMTexture")):
            if usage in part.textures:
                pd["textures"][kind] = _texture(w, part.textures[usage], "p%d_%s" % (pi, kind))
        alb = part.textures.get("AlbedoTexture")
        for mi, m in enumerate(part.meshes):
            b = w.blob("mesh_%d_%d.bin" % (pi, mi), mesh_arrays(m, sk))
            pd["meshes"].append(dict(b, name=m.name, vertices=int(len(m.pos)), triangles=int(len(m.tris)),
                                     skinned=m.joints is not None and sk is not None,
                                     material=alb.logical if alb else ""))
        for li, L in enumerate(part.layers):
            pd["layers"].append({"name": L.name, "effect": L.effect, "picked": L.picked,
                                 "mask": _texture(w, L.mask, "p%d_l%d_mask" % (pi, li)),
                                 "strip": _texture(w, L.strip, "p%d_l%d_strip" % (pi, li))})
        parts.append(pd)
    clips = {}
    sk0 = next(iter(skel_of.values()), None)
    if sk0 is not None:
        for name, c in unit.clips.items():
            arr = sample_clip(sk0, c, fps)
            b = w.blob("clip_%s.bin" % _safe(name), [("locals", arr)])
            clips[name] = dict(b, duration=c.duration, fps=fps, samples=int(arr.shape[0]), decodable=c.decodable())
    tb = w.blob("tone.bin", [("xs", tone._XS.astype(np.float32)), ("ys", tone._YS.astype(np.float32))])
    rigs = rigs or {"default": rig_mod.default(), "game": rig_mod.game()}
    doc = {
        "bundle_version": BUNDLE_VERSION, "asset": asset, "name": unit.name, "root_scale": unit.root_scale,
        "rotation_override": list(unit.rotation_override), "notes": list(unit.notes) + list(notes or []),
        "shader": {"file": "hdkit/view/shaders.wgsl", "sha256": _sha(shader)},
        "camera": dict(camera.facts(900.0, 1.0), k_1600x900=camera.K_1600x900, zoom_range=list(ZOOM_RANGE),
                       game_el=camera.GAME_EL, game_az=camera.GAME_AZ, yaw0=camera.GAME_AZ, sign=-1.0,
                       feet_1600x900=list(camera.FEET_1600x900), view_height_units=camera.VIEW_HEIGHT_UNITS),
        "render": {"passes": gpu.PASSES, "srgb_passes": sorted(gpu.SRGB_PASSES), "rig_passes": sorted(gpu.RIG_PASSES),
                   "floats_per_vertex": gpu.FLOATS, "msaa": int(msaa), "aniso": max(1, int(aniso)), "ref_aniso": max(1, int(ref_aniso)),
                   "uniform_floats": getattr(gpu, "UBUF_BYTES", 256) // 4,
                   "points": {"offset": 44, "max": gpu.MAX_POINTS} if hasattr(gpu, "MAX_POINTS") else None,
                   "defaults": {"alb": [255, 255, 255, 255], "nrm": [255, 128, 0, 128], "orm": [255, 255, 0, 0],
                                "mask": [0, 0, 0, 255], "strip": [255, 255, 255, 255]}},
        "tone": dict(tb, luma=tone.LUMA.tolist(), note="tone.apply: hue-preserving through the grey curve; no LUT"),
        "parts": parts, "clips": clips, "mode_clip": scene.MODE_CLIP,
        "state_machine": state_machine(fs, asset, unit.clips, classic) if fs is not None else None,
        "rigs": {k: r.as_dict() for k, r in rigs.items()},
        "files": fs.provenance() if fs is not None else [], "refs": [],
    }
    doc["bytes"] = sum((out / f).stat().st_size for f in w.files)
    (out / "scene.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    return doc


# ---- reference stills rendered by the CLI ---------------------------------------------------------------------------------

REF_KEYS = ("pass_name", "dir64", "mode", "clip", "time", "scale", "size", "ss", "bg", "rig", "glow", "hide", "el", "az",
            "yaw0", "sign", "origin", "layer_scale", "aniso")


def add_refs(out, S, specs: list, log=print) -> list:
    """Render each spec (dict of CLI render options) with the CLI's own render_cmd on Session S, copy the PNG into
    refs/, and list the effective arguments in scene.json (the page renders the same still and compares)."""
    from . import cli
    out = Path(out)
    (out / "refs").mkdir(exist_ok=True)
    doc = json.loads((out / "scene.json").read_text(encoding="utf-8"))
    refs = []
    for i, spec in enumerate(specs):
        argv = ["render", S.a.asset, "--no-gate", "--out", str(out / "refs" / "_work"), "--name", "ref%02d" % i]
        for r in S.a.root:
            argv += ["--root", r]
        for k, v in spec.items():
            flag = "--" + ("pass" if k == "pass_name" else k.replace("_", "-"))
            if k == "glow":
                argv.append("--glow" if v else "--no-glow")
            elif isinstance(v, list):
                for x in v:
                    argv += [flag, str(x)]
            else:
                argv += [flag, str(v)]
        a = cli.build_parser().parse_args(argv)
        S.a = a
        S.rig = rig_mod.resolve(a.rig)          # the unit stays loaded; only the rig follows the spec
        if a.glow_gain is not None:
            S.rig.light.glow_gain = a.glow_gain
        rep = cli.render_cmd(a, log, S)
        img = rep["images"][0]
        dst = out / "refs" / ("ref%02d.png" % i)
        shutil.copyfile(img["png"], dst)
        eff = {k: getattr(a, k) for k in REF_KEYS if hasattr(a, k)}
        eff["time"] = rep["time"]
        eff["clip"] = cli.clip_name(a)
        eff["origin"] = list(rep["origin"])
        eff["dir64"] = img["dir64"]
        eff["yaw"] = img["yaw"]
        eff["rig_dict"] = S.rig.as_dict()
        refs.append({"id": "ref%02d" % i, "png": "refs/ref%02d.png" % i, "args": eff, "argv": argv[1:],
                     "adapter": {k: rep["adapter"].get(k) for k in ("device", "backend_type")}})
    shutil.rmtree(out / "refs" / "_work", ignore_errors=True)
    doc["refs"] = refs
    (out / "scene.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    return refs


def default_refs(passes=("lit", "normals", "depth"), dir64=(0, 24), mode="nu", time_s=0.4, size="320x320", scale=1.5,
                 ss=2, rig="game", bg="#202020", aniso=1) -> list:
    """The match set of the brief: passes x facings of one still, at the matched anisotropy (1 by default)."""
    return [{"pass_name": p, "dir64": str(d), "mode": mode, "time": time_s, "size": size, "scale": scale, "ss": ss,
             "rig": rig, "bg": bg, "aniso": aniso} for p in passes for d in dir64]


# ---- CLI: export-web, serve-web ---------------------------------------------------------------------------------------

def add_parsers(sub, add_common):
    e = sub.add_parser("export-web", help="export a unit to a bundle for the browser page (hdkit/view/web)")
    add_common(e)
    e.add_argument("--clip-fps", type=float, default=50.0, help="clip samples per second (default 50)")
    e.add_argument("--classic", default=None, help="frames.json of the classic modes (for the player's classic timing)")
    e.add_argument("--no-refs", action="store_true", help="no CLI reference stills (no GPU needed)")
    e.add_argument("--ref-passes", default="lit,normals,depth")
    e.add_argument("--ref-dir64", default="0,24")
    e.add_argument("--ref-mode", default="nu")
    e.add_argument("--ref-time", type=float, default=0.4)
    e.add_argument("--ref-size", default="320x320")
    e.add_argument("--ref-scale", type=float, default=1.5)
    e.add_argument("--ref-ss", type=int, default=2)
    e.add_argument("--ref-rig", default="game")
    e.add_argument("--ref-bg", default="#202020")
    e.add_argument("--ref-aniso", type=int, default=1,
                   help="anisotropy of the CLI stills and of the page's Match CLI (default 1: matched; Chrome's D3D12 and "
                        "the CLI's Vulkan filter anisotropically differently, up to 26/255 apart at 16)")
    w = sub.add_parser("serve-web", help="serve the page and one bundle on 127.0.0.1 (Ctrl+C stops it)")
    w.add_argument("bundle")
    w.add_argument("--port", type=int, default=8765)
    w.add_argument("--accept-results", default=None)


def run(a) -> int:
    if a.cmd == "serve-web":
        from . import webserve
        argv = [a.bundle, "--port", str(a.port)] + (["--accept-results", a.accept_results] if a.accept_results else [])
        return webserve.main(argv)
    print(json.dumps(export_cmd(a), indent=1, default=str))
    return 0


def export_cmd(a, log=print, S=None) -> dict:
    """export-web: the bundle (scene.json, binaries, textures) and, unless --no-refs, the CLI stills of the match set.
    S, when given, must be a Session whose renderer samples at a.ref_aniso (the stills' anisotropy)."""
    from . import cli, vfs
    if a.asset.startswith("card:"):
        raise SystemExit("export-web: a unit JSON or .model, not a card")
    if a.msaa != 4:
        raise SystemExit("export-web: the page renders with MSAA 4; use --msaa 4")
    classic = json.loads(Path(a.classic).read_text(encoding="utf-8")) if a.classic else None
    if a.no_refs and S is None:
        fs = vfs.Layered(vfs.parse_roots(a.root))
        unit = scene.load_unit(fs, a.asset, a.lod)
    else:
        if S is None:            # the stills render at the matched anisotropy (the renderer's sampler is fixed)
            from . import gpu
            S = cli.Session(a, log, R=gpu.Renderer(msaa=a.msaa, aniso=a.ref_aniso))
        fs, unit = S.fs, S.unit
    rigs = {"default": rig_mod.default(), "game": rig_mod.game()}
    if a.rig not in rigs:
        rigs[Path(a.rig[4:] if a.rig.startswith("vis:") else a.rig).stem] = rig_mod.resolve(a.rig)
    doc = export(unit, a.out, fs, a.asset, a.clip_fps, classic, rigs, msaa=a.msaa, aniso=a.aniso,
                 ref_aniso=a.ref_aniso)
    refs = []
    if not a.no_refs:
        refs = add_refs(a.out, S, default_refs(a.ref_passes.split(","), [int(x) for x in a.ref_dir64.split(",")],
                                               a.ref_mode, a.ref_time, a.ref_size, a.ref_scale, a.ref_ss, a.ref_rig,
                                               a.ref_bg, a.ref_aniso), log)
    return {"bundle": str(Path(a.out).resolve()), "scene": str(Path(a.out).resolve() / "scene.json"),
            "bytes": doc["bytes"], "clips": len(doc["clips"]), "parts": len(doc["parts"]), "refs": len(refs),
            "shader_sha256": doc["shader"]["sha256"],
            "open": "python -m hdkit.view serve-web %s  then http://127.0.0.1:8765/" % Path(a.out).resolve()}
