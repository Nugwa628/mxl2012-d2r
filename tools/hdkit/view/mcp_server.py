"""hdkit.view as a local stdio MCP server: the CLI's commands as tools, one warm process (GPU device and units stay loaded).

  <python with wgpu and mcp> -m hdkit.view.mcp_server          (from tools/; stdio only: no port, no listener)

Every tool builds the CLI's own argument list and calls the CLI's function (`cli.render_cmd`, `sheet_cmd`, `turntable_cmd`,
`compare_cmd`, `info_cmd`, `rig.resolve`): this file holds no rendering or measuring code. GPU tools pass `hdkit.gpugate`
first on every call and answer {"refused": true, "why": ...} while a game-slot run holds its lock or the GPU or CPU is
busy (`wait_s` waits up to that long). Paths are returned, not image bytes, except one PNG of at most HDKIT_MCP_INLINE_KB
(default 256) KiB per call. Outputs of at least `store_min_mb` (default HDKIT_MCP_STORE_MB, 16) move into the content
store by hash (hdkit.store; HDKIT_STORE or the site store) with an art-manifest.json next to metrics.json.

Environment:
  HDKIT_VIEW_ROOTS   default roots, os.pathsep separated `name=folder` (a tool's `roots` replaces them)
  HDKIT_VIEW_OUT     output folder (default ./hdview-out); each call writes <out>/<command>/<name>_<hash of its arguments>
  HDKIT_MCP_INLINE_KB, HDKIT_MCP_STORE_MB   as above

The `mcp` package (official Python SDK, MIT) is only needed here; the library and its tests never import it.
"""
import base64
import contextlib
import hashlib
import json
import os
import sys
import threading
from pathlib import Path

from . import cli, rig as rig_mod
from .. import gpugate

INLINE_MAX = int(float(os.environ.get("HDKIT_MCP_INLINE_KB", "256")) * 1024)
STORE_MIN_MB = float(os.environ.get("HDKIT_MCP_STORE_MB", "16"))
_LOCK = threading.Lock()
_STATE = {"renderer": None, "sessions": {}}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def default_roots() -> list:
    env = os.environ.get("HDKIT_VIEW_ROOTS", "")
    return [r for r in env.split(os.pathsep) if r]


def out_root() -> Path:
    return Path(os.environ.get("HDKIT_VIEW_OUT") or (Path.cwd() / "hdview-out")).resolve()


def argv_of(cmd: str, positional: list, opts: dict) -> list:
    """CLI argument list: True -> --flag, False/None -> left out, lists -> the option repeated, else --key value."""
    out = [cmd] + [str(p) for p in positional]
    for k, v in opts.items():
        flag = "--" + k.replace("_", "-")
        if v is None or v is False:
            continue
        if v is True:
            out.append(flag)
        elif isinstance(v, (list, tuple)):
            for x in v:
                out += [flag, str(x)]
        else:
            out += [flag, str(v)]
    return out


def parse(argv: list):
    with contextlib.redirect_stdout(sys.stderr):
        try:
            return cli.build_parser().parse_args(argv)
        except SystemExit as e:
            raise ValueError("bad arguments %s (exit %s)" % (argv, e.code)) from None


def gate(wait_s: float = 0.0) -> dict | None:
    """None when a GPU job may run; else the polite refusal."""
    rd = gpugate.check() if wait_s <= 0 else gpugate.wait_free(every=min(15.0, wait_s), most=wait_s, log=log)
    if rd.free:
        return None
    return {"refused": True, "why": rd.why, "gate": rd.as_dict(),
            "advice": "GPU jobs wait while a game-slot run holds its lock or the GPU/CPU is busy; ask again later "
                      "(or pass wait_s)"}


def _png(path) -> list:
    from mcp.types import ImageContent
    p = Path(path) if path else None
    if p is None or not p.is_file() or p.stat().st_size > INLINE_MAX:
        return []
    return [ImageContent(type="image", data=base64.b64encode(p.read_bytes()).decode("ascii"), mimeType="image/png")]


def _content(result: dict, image=None) -> list:
    from mcp.types import TextContent
    return [TextContent(type="text", text=json.dumps(result, indent=1, default=str))] + _png(image)


def session(a):
    """The CLI Session of these inputs, kept warm (one GPU device for the process; units cached per roots/asset/rig)."""
    from . import gpu
    if _STATE["renderer"] is None:
        _STATE["renderer"] = gpu.Renderer(msaa=4, aniso=16)
    R = _STATE["renderer"]
    rig_key = a.rig
    if a.rig.startswith("vis:") or a.rig not in rig_mod.PRESETS:
        p = Path(a.rig[4:] if a.rig.startswith("vis:") else a.rig)
        rig_key = (a.rig, p.stat().st_mtime if p.exists() else None)
    key = (tuple(a.root), a.asset, a.lod, rig_key, a.glow_gain, a.msaa, a.aniso)
    S = _STATE["sessions"].get(key)
    if S is None:
        if (a.msaa, a.aniso) != (4, 16):
            R = gpu.Renderer(msaa=a.msaa, aniso=a.aniso)
        S = cli.Session(a, log, R=R)
        _STATE["sessions"][key] = S
    S.a = a
    return S


def _summary(rep: dict, out: Path) -> dict:
    keep = ("command", "asset", "clip", "time", "passes", "pass", "modes", "frames", "camera", "size", "ss", "msaa", "glow",
            "hide", "layer_scale", "sheet", "anim", "metrics", "stored", "art_manifest", "unit_notes", "origin")
    s = {k: rep[k] for k in keep if k in rep}
    s["out"] = str(out)
    s["rig"] = {k: rep["rig"].get(k) for k in ("name", "exposure", "tone", "unknown")} if rep.get("rig") else None
    s["adapter"] = {k: rep.get("adapter", {}).get(k) for k in ("device", "backend_type")}
    s["files"] = len(rep.get("files", []))
    s["images"] = []
    for e in rep.get("images", []):
        img = e.get("image") or {}
        s["images"].append({k: e[k] for k in ("png", "pass", "mode", "facing_key", "dir64", "yaw", "frame", "stored",
                                               "seconds") if k in e}
                           | {"measures": {k: img.get(k) for k in ("height_px", "width_px", "bbox", "coverage",
                                                                    "luma_mean", "luma_median", "luma_p90", "rgb_mean")},
                              "texels_per_pixel": (e.get("texels_per_pixel") or {}).get("median")})
    return s


def run_gpu(cmd: str, asset: str, opts: dict, wait_s: float = 0.0, store_min_mb: float | None = None) -> list:
    refusal = gate(wait_s)
    if refusal:
        return _content(refusal)
    roots = opts.pop("root", None) or default_roots()
    if not roots and not asset.startswith("card:"):
        raise ValueError("no roots: pass roots=[\"name=folder\", ...] or set HDKIT_VIEW_ROOTS")
    name = opts.get("name") or Path(asset.split(":", 1)[-1]).stem
    tag = hashlib.sha256(json.dumps([cmd, asset, roots, opts], sort_keys=True, default=str).encode()).hexdigest()[:10]
    out = Path(opts.pop("out", None) or (out_root() / cmd / ("%s_%s" % (name, tag))))
    opts.update(root=roots, out=str(out), no_gate=True,
                store_min_mb=STORE_MIN_MB if store_min_mb is None else store_min_mb)
    a = parse(argv_of(cmd, [asset], opts))
    with _LOCK, contextlib.redirect_stdout(sys.stderr):
        S = session(a)
        rep = cli.COMMANDS[cmd](a, log, S)
    summary = _summary(rep, out)
    first = rep.get("sheet") or next((e.get("png") for e in rep.get("images", []) if e.get("png")), None)
    return _content(summary, first if first and Path(first).exists() else None)


def _render_opts(mode, clip, frame, time, fps, scale, size, ss, pass_name, rig, glow, hide, layer_scale, bg, el, origin,
                 lod, out, name, roots) -> dict:
    return {"mode": mode, "clip": clip, "frame": frame, "time": time, "fps": fps, "scale": scale, "size": size, "ss": ss,
            "pass": pass_name, "rig": rig, "no_glow": not glow, "hide": hide or None, "layer_scale": layer_scale,
            "bg": bg, "el": el, "origin": origin, "lod": lod, "out": out, "name": name, "root": roots}


def _facing_opts(facing, dir64, facings) -> dict:
    if dir64:
        return {"dir64": ",".join(str(int(d)) for d in dir64)}
    if facing is not None:
        from . import camera
        return {"dir64": str(camera.key_dir64(int(facing)))}
    return {"facings": facings}


def build():
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    ro = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    wr = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    srv = FastMCP("hdkit-view")

    @srv.tool(annotations=ro)
    def view_assets(kind: str = "units", pattern: str | None = None, asset: str | None = None,
                    roots: list[str] | None = None, limit: int = 200) -> dict:
        """List what the roots hold: kind 'units' (unit JSONs), 'models' (.model files) or 'clips' (the clips, modes,
        parts and self-lit layers of one unit or model named by `asset`). `pattern`: substring or fnmatch on the logical
        path. `roots`: ["name=folder", ...], first wins (default HDKIT_VIEW_ROOTS)."""
        a = parse(argv_of("ls", [kind] + ([asset] if asset else []),
                          {"root": roots or default_roots(), "pattern": pattern, "limit": limit}))
        return cli.info_cmd(a)

    @srv.tool(annotations=ro)
    def view_resolve(path: str, roots: list[str] | None = None) -> dict:
        """Which root answers a logical game path (data/hd/...), the file on disk, and which other roots also hold it."""
        return cli.info_cmd(parse(argv_of("resolve", [path], {"root": roots or default_roots()})))

    @srv.tool(annotations=ro)
    def view_camera(height: float = 900.0, zoom: float = 1.0) -> dict:
        """The game camera the renderer uses: orthographic, elevation, azimuth, px per world unit at a screen height,
        sub-tile step, feet pixel, basis vectors, facing formula, and where each number comes from."""
        return cli.info_cmd(parse(argv_of("camera", [], {"height": height, "zoom": zoom})))

    @srv.tool(annotations=ro)
    def view_gate() -> dict:
        """May a GPU job run now: held game-slot locks, GPU engine and CPU load."""
        return cli.info_cmd(parse(["gate"]))

    @srv.tool(annotations=wr)
    def view_render(asset: str, roots: list[str] | None = None, mode: str | None = None, clip: str | None = None,
                    facing: int | None = 0, dir64: list[int] | None = None, facings: int = 1, frame: float = 0.0,
                    time: float | None = None, fps: float = 25.0, pass_name: str = "lit", passes: list[str] | None = None,
                    rig: str = "default", size: str = "300x300", scale: float = 1.0, ss: int = 2, glow: bool = True,
                    hide: list[str] | None = None, layer_scale: float = 1.0, bg: str = "transparent", el: float = 30.0,
                    origin: str | None = None, lod: int = 0, name: str | None = None, out: str | None = None,
                    store_min_mb: float | None = None, wait_s: float = 0.0):
        """Render a still of a unit, model or classic card (`card:<frames folder>`) at the game camera: PNG path(s) and
        measures (on-screen height, luma, coverage, texels per pixel); the full report is in metrics.json. facing: key
        0..7 (0 = screen bottom, clockwise), or dir64 list, or facing=None with facings=8. mode: dt nu wl gh a1 ...
        (or clip). time in seconds overrides frame. pass_name: lit unlit albedo normals depth wire glow orm_ao orm_rough
        orm_metal orm_spec (passes: several, adds a sheet). rig: default | game | vis:<file> | <rig.json>. size WxH,
        scale 1 = a 1600x900 capture, ss supersampling per axis."""
        o = _render_opts(mode, clip, frame, time, fps, scale, size, ss, pass_name, rig, glow, hide, layer_scale, bg, el,
                         origin, lod, out, name, roots)
        o.update(_facing_opts(facing, dir64, facings))
        if passes:
            o["passes"] = ",".join(passes)
        return run_gpu("render", asset, o, wait_s, store_min_mb)

    @srv.tool(annotations=wr)
    def view_sheet(asset: str, modes: list[str] | None = None, roots: list[str] | None = None, facings: int = 8,
                   dir64: list[int] | None = None, frame: float = 0.0, time: float | None = None, pass_name: str = "lit",
                   rig: str = "default", size: str = "200x220", scale: float = 1.0, ss: int = 2, glow: bool = True,
                   hide: list[str] | None = None, bg: str = "transparent", el: float = 30.0, origin: str | None = None,
                   name: str | None = None, out: str | None = None, store_min_mb: float | None = None,
                   wait_s: float = 0.0):
        """A contact sheet of modes (rows: mode codes or clip names) x facings (columns) of one unit: the sheet PNG (inline
        when small), each cell's measures, metrics.json."""
        o = _render_opts(None, None, frame, time, None, scale, size, ss, pass_name, rig, glow, hide, None, bg, el, origin,
                         None, out, name, roots)
        o.update(_facing_opts(None, dir64, facings), modes=",".join(modes or ["nu"]))
        return run_gpu("sheet", asset, o, wait_s, store_min_mb)

    @srv.tool(annotations=wr)
    def view_turntable(asset: str, frames: int = 24, roots: list[str] | None = None, mode: str | None = None,
                       clip: str | None = None, facing: int = 0, time: float | None = None, frame: float = 0.0,
                       pass_name: str = "lit", rig: str = "default", size: str = "240x260", scale: float = 1.0,
                       ss: int = 2, glow: bool = True, bg: str = "transparent", anim: list[str] | None = None,
                       anim_fps: float = 12.0, name: str | None = None, out: str | None = None,
                       store_min_mb: float | None = None, wait_s: float = 0.0):
        """One full turn of a unit in `frames` steps from facing key `facing`: the frame PNGs, a contact sheet, GIF and/or
        APNG and/or MP4 (anim: gif, apng, mp4)."""
        o = _render_opts(mode, clip, frame, time, None, scale, size, ss, pass_name, rig, glow, None, None, bg, None, None,
                         None, out, name, roots)
        o.update(_facing_opts(facing, None, 1), frames=frames, anim=",".join(anim or ["gif", "apng"]), anim_fps=anim_fps)
        return run_gpu("turntable", asset, o, wait_s, store_min_mb)

    @srv.tool(annotations=ro)
    def view_rig_load(spec: str = "game") -> dict:
        """A light rig as JSON: preset 'default' or 'game', 'vis:<env/vis json>', or a rig JSON file. Lists the rig's
        unknowns and assumptions."""
        return rig_mod.resolve(spec).as_dict()

    @srv.tool(annotations=wr)
    def view_rig_save(path: str, spec: str = "game", changes: dict | None = None) -> dict:
        """Write a rig JSON (for render rig=<path>): the rig of `spec`, with `changes` merged into its dict (for example
        {"exposure": 0.1} or {"light": {"ambient": [0.1, 0.1, 0.1]}})."""
        d = rig_mod.resolve(spec).as_dict()
        for k, v in (changes or {}).items():
            d[k] = dict(d.get(k) or {}, **v) if isinstance(v, dict) and isinstance(d.get(k), dict) else v
        p = rig_mod.Rig.from_dict(d).save(path)
        return {"path": str(Path(p).resolve()), "rig": rig_mod.load(p).as_dict()}

    @srv.tool(annotations=wr)
    def view_compare(render: str, shot: str, shot_feet: list[float], twin: str | None = None, mask: str | None = None,
                     render_feet: list[float] | None = None, exclude: list[list[float]] | None = None, reach: int = 10,
                     panel: str | None = None):
        """Compare a render PNG with a game capture: the unit's mask in the shot (from its twin shot without the unit, or
        a given mask), silhouette IoU at the feet and at the best shift within +-reach px, luma medians and their ratio,
        cap colour (brightest fifth of the top third) and its distance. shot_feet / render_feet: [x, y] feet pixels.
        exclude: [[x0, y0, x1, y1], ...] shot pixels left out (the player). Writes a panel PNG (inline when small)."""
        xy = lambda v: ",".join("%g" % x for x in v) if v else None  # noqa: E731
        if panel is None:
            tag = hashlib.sha256(json.dumps([render, shot, twin, mask, shot_feet], default=str).encode()).hexdigest()[:10]
            panel = str(out_root() / "compare" / ("%s_%s.png" % (Path(render).stem, tag)))
        a = parse(argv_of("compare", [render, shot], {"twin": twin, "mask": mask, "shot_feet": xy(shot_feet),
                                                         "render_feet": xy(render_feet),
                                                         "exclude": [xy(e) for e in exclude or []] or None,
                                                         "reach": reach, "panel": panel,
                                                         "out": str(Path(panel).with_suffix(".json"))}))
        with _LOCK, contextlib.redirect_stdout(sys.stderr):
            res = cli.compare_cmd(a, log)
        return _content(res, res.get("panel"))

    @srv.tool(annotations=wr)
    def view_signoff_sheet(token: str, tag: str, modes: str = "nu,a1,gh,dt,dd", facings: str = "0,2,4,6",
                           glow_off: bool = False, slot: int = 2, sheet: str | None = None):
        """The viewer half of the in-game sign-off (hdkit.signoff views): renders every (key, mode) captured by an earlier
        game run `tag` at its polled dir64 and time, compares each with its game cut, and writes the labelled sheet
        game | viewer | outlines. Never starts a game run (that is `python -m hdkit.signoff run|all`, under the slot lock)."""
        from ..signoff import cli as so
        argv = ["views", token, "--tag", tag, "--modes", modes, "--facings", facings, "--slot", str(slot)]
        argv += ["--glow-off"] if glow_off else []
        argv += ["--sheet", sheet] if sheet else []
        with _LOCK, contextlib.redirect_stdout(sys.stderr):
            so.main(argv)
        a = so.build_parser().parse_args(argv)
        path = sheet or str(a.ev / ("sheet_%s.png" % tag))
        return _content({"sheet": path, "summary": str(a.ev / ("signoff_%s.json" % tag))}, path)

    @srv.tool(annotations=wr)
    def view_export_web(asset: str, out: str, roots: list[str] | None = None, classic: str | None = None,
                        clip_fps: float = 50.0, refs: bool = True, ref_aniso: int = 1, wait_s: float = 0.0) -> dict:
        """Export a unit as a bundle for the browser viewer (scene.json, meshes, skeleton, sampled clips, texture mips,
        tone table) plus, unless refs=False, the CLI stills the page's Match CLI check compares against. classic:
        frames.json of the classic modes. ref_aniso: anisotropy of the stills and of the page's check (1 = matched: Chrome's
        D3D12 and the CLI's Vulkan filter anisotropically differently). Open with `python -m hdkit.view serve-web <out>`."""
        from . import export_web
        if refs:
            refusal = gate(wait_s)
            if refusal:
                return refusal
        a = parse(argv_of("export-web", [asset], {"root": roots or default_roots(), "out": out, "classic": classic,
                                                  "clip_fps": clip_fps, "no_refs": not refs, "ref_aniso": ref_aniso,
                                                  "no_gate": True}))
        with _LOCK, contextlib.redirect_stdout(sys.stderr):
            S = None
            if refs:
                from . import gpu
                key = "renderer_aniso%d" % a.ref_aniso       # the stills' sampler: the matched anisotropy
                _STATE[key] = _STATE.get(key) or gpu.Renderer(msaa=4, aniso=a.ref_aniso)
                S = cli.Session(a, log, R=_STATE[key])
            return export_web.export_cmd(a, log, S)

    # ---- maps (hdkit.view.mapview, docs/mapview.md) --------------------------------------------------------------------
    from .mapview import api as map_api

    @srv.tool(annotations=ro)
    def map_list(source: str = "mod", pattern: str | None = None) -> dict:
        """Maps (.ds1 paths below data/global/tiles, no extension) of the mod's extract (source 'mod') or D2R's ('d2r')."""
        return map_api.list_maps(source, pattern)

    @srv.tool(annotations=ro)
    def map_info(map: str, source: str = "auto", work: str | None = None) -> dict:
        """A map's size in cells, act, levels using it, the .dt1 files the game loads for it (lvltypes + Dt1Mask), object
        counts and the whole-map frame. source auto|mod|d2r; work: a working copy folder (map_edit_init)."""
        with _LOCK:
            return map_api.map_info(map, source, work)

    @srv.tool(annotations=wr)
    def map_render(map: str, kind: str = "classic", cells: str | None = None, scale: float | None = None,
                   layers: str | None = None, source: str = "auto", work: str | None = None, el: float | None = None,
                   az: float | None = None, isolate: bool = False, grid: bool = False, out: str | None = None,
                   wait_s: float = 0.0):
        """Render a whole map (cells None) or a region (cells 'x0,y0,x1,y1', inclusive) as kind 'classic' (.ds1 + .dt1 +
        act palette, D2 draw order), 'hd' (the D2R/mod preset in the game camera) or 'sheet' (classic | HD | blend on the
        same cell pixels). scale: px per native classic px (default 0.5 whole, 1 region; HD uses scale x 2/3 so cells
        match). layers classic: floor shadow wall lower roof special objects labels grid coords walk (+x/-x edits the
        defaults); hd: terrain walls props prefabs lights objects grid. el/az: HD orbit angles (pixels then do not line up
        with classic). Returns the PNG path and the render's JSON (missing tiles, notes); small PNGs inline."""
        if scale is None:
            scale = 1.0 if cells else 0.5
        if kind in ("hd", "sheet"):
            refused = gate(wait_s)
            if refused:
                return _content(refused)
        with _LOCK:
            if kind == "classic":
                lay = layers
                if grid:
                    lay = (lay + ",+grid,+coords") if lay else "+grid,+coords"
                r = map_api.render_classic(map, cells, scale, lay, source, work, isolate, out)
            elif kind == "hd":
                r = map_api.render_hd(map, cells, scale, layers, source, work, out, el=el, az=az, gate=False, grid=grid)
            elif kind == "sheet":
                r = map_api.render_sheet(map, cells, scale, layers, None, source, work, out, gate=False, grid=grid)
            else:
                return _content({"error": "kind: classic, hd or sheet"})
        return _content(r, r.get("png"))

    @srv.tool(annotations=ro)
    def map_cell(map: str, x: int, y: int, source: str = "auto", work: str | None = None, near: float = 0.0,
                 hd: bool = True) -> dict:
        """What is on cell (x, y): each floor / wall / shadow dword (style, sequence, orientation, hidden), the tile it
        resolves to (dt1 file, index, rarity variants, sub-tile flags), walk flags, the .ds1 objects on it with names, and
        the HD preset entities whose origin is on the cell (or within `near` cells): name, model, prefab, transform."""
        with _LOCK:
            return map_api.cell_info(map, x, y, source, work, near, hd)

    @srv.tool(annotations=wr)
    def map_edit_init(map: str, source: str = "auto", work: str | None = None, force: bool = False) -> dict:
        """Start a working copy of a map: its .ds1 and HD preset copied to `work` (default
        /d2work/runs/mapview/work/<map>); edits and renders with work=<folder> use it. Game files are never written."""
        from .mapview import edit
        with _LOCK:
            wc = edit.WorkCopy.init(map, work, source, True, force)
        return {"work": str(wc.root), "meta": wc.meta}

    @srv.tool(annotations=wr)
    def map_edit(work: str, op: str, x: int | None = None, y: int | None = None, layer: str = "floor", index: int = 0,
                 style: int | None = None, seq: int | None = None, orientation: int | None = None,
                 prop1: int | None = None, hidden: bool = False, clear: bool = False, type: int | None = None,
                 id: int | None = None, flags: int = 0, model: str | None = None, pos: list[float] | None = None,
                 yaw: float | None = None, name: str | None = None) -> dict:
        """Edit a working copy. op 'tile' (x, y cell; layer floor|wall|shadow, index; style+seq [orientation, prop1,
        hidden] or clear), 'obj-add' (type 1 monster / 2 object, id, x/y in SUB-tiles, flags), 'obj-move' (index, x, y
        sub-tiles), 'obj-remove' (index), 'ent-add' (model logical path, pos [x, y, z] world units: 10 per cell, yaw deg,
        name), 'ent-move' (index, pos, yaw), 'ent-remove' (index), 'show' (edits and changed cells). Render after an edit
        with map_render(work=...)."""
        from .mapview import edit
        with _LOCK:
            wc = edit.WorkCopy.open(work)
            if op == "tile":
                return wc.set_tile(x, y, layer, index, style, seq, orientation, prop1, hidden, clear)
            if op == "obj-add":
                return wc.obj_add(type, id, x, y, flags)
            if op == "obj-move":
                return wc.obj_move(index, x, y)
            if op == "obj-remove":
                return wc.obj_remove(index)
            if op == "ent-add":
                return wc.ent_add(model, pos, yaw or 0.0, name)
            if op == "ent-move":
                return wc.ent_move(index, pos, yaw)
            if op == "ent-remove":
                return wc.ent_remove(index)
            if op == "show":
                return wc.show()
        return {"error": "op: tile, obj-add, obj-move, obj-remove, ent-add, ent-move, ent-remove, show"}

    return srv


TOOL_NAMES = ("view_assets", "view_resolve", "view_camera", "view_gate", "view_render", "view_sheet", "view_turntable",
              "view_rig_load", "view_rig_save", "view_compare", "view_export_web", "view_signoff_sheet",
              "map_list", "map_info", "map_render", "map_cell", "map_edit_init", "map_edit")


def main() -> int:
    build().run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
