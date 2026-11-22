"""python -m hdkit.view <command> <asset> [options]: PNGs of a unit, model or classic card, plus metrics.json.

Commands:
  render <asset>      one image per facing (and per pass with --passes; a contact sheet passes x facings when more than one)
  sheet <asset>       contact sheet of modes x facings (--modes nu,a1,dt; one pass)
  turntable <asset>   --frames N images over one full turn, their contact sheet, and a GIF and/or APNG (--anim gif,apng)
  watch <command> <asset> [options]   run the command, then again whenever an input file (every file the render read,
                      the rig file, --also files) changes; --every 1 s, --max-runs, --idle-exit seconds
  rig <preset|vis:<file>|rig.json> <out.json>   write a light rig file (presets: default, game)
  ls units|models|clips [<asset>] --root ... [--pattern p]   what the roots hold (JSON)
  resolve <logical path> --root ...   which root answers a path (JSON)
  camera [--height 900 --zoom 1]      the game camera as numbers (JSON)
  compare <render.png> <shot.png> --shot-feet x,y (--twin <shot without the unit> | --mask <png|npy>) [--exclude ...]
                      silhouette IoU (at the feet and at the best shift), luma medians, cap colour (hdkit.view.compare)
  gate                may a GPU job run now (slot locks, GPU and CPU load)
  map <command> ...   the map viewer: classic / HD map renders, side-by-side sheets, cell info, working-copy edits
                      (hdkit.view.mapview, docs/mapview.md)

<asset> is a logical path (a unit JSON or a .model) found over --root folders (first wins), or `card:<frames folder>` for a
classic frame on a card. Every image is rendered at the game camera: --scale 1 is the size of a 1600x900 capture.

  --facings 8          the 8 facing keys (0 = the screen's bottom, then clockwise); --dir64 a,b,... picks exact facings
  --mode dt            animation mode (clip from the mode code, or --clip <name>); --frame 0 frame index, --fps 25,
                       or --time seconds
  --scale 4 --size 512x512 --ss 4  camera scale, image size, supersampling per axis (box filter, on top of tiling)
  --pass lit|unlit|albedo|normals|depth|wire|glow|orm_ao|orm_rough|orm_metal|orm_spec;  --passes a,b,... several
  --glow / --no-glow   self-lit layers;  --hide mesh:<n>|part:<n>|material:<substr>|layer:<n>|body  (repeatable)
  --layer-scale F      draw the self-lit layers F times larger about the unit's origin (test lever, default 1)
  --rig default|game|vis:<vis json>|<rig.json>   light, exposure and tone;  --save-rig <out.json> writes the rig used
  --bg transparent | #rrggbb | tile:<png>  (a tile is repeated in screen space)
  --el 30 --az 45 --yaw0 45 --sign -1    camera elevation/azimuth, facing yaw = yaw0 + sign * dir64 * 5.625
  --origin x,y         pixel of the world origin (the unit's feet); default the image's centre, 3/4 down
  --tile N             largest tile (default the GPU limit); images larger than the tile are rendered as tiles
  --stream             write each tile row straight to the PNG (images too large to hold), single facing only
  --store-min-mb N     outputs of at least N MB move into the content store by hash (art-manifest.json next to them)

Writes <out>/<name>_<tag>.png and <out>/metrics.json (provenance of every file used, pose, notes, adapter, rig with its
unknowns, the image measures of hdkit.view.metrics and texels per pixel), per command.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import camera, metrics, scene, vfs

PASS_NAMES = ("lit", "unlit", "albedo", "normals", "depth", "wire", "glow", "orm_ao", "orm_rough", "orm_metal", "orm_spec", "height")


def parse_size(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def parse_bg(s, size):
    if s in (None, "", "transparent", "none"):
        return None
    from .gpu import srgb_decode
    if s.startswith("#"):
        rgb = [int(s[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
        return srgb_decode(np.array(rgb))
    if s.startswith("tile:"):
        from PIL import Image
        t = np.array(Image.open(s[5:]).convert("RGB"), float) / 255.0
        W, H = size
        reps = (-(-H // t.shape[0]), -(-W // t.shape[1]), 1)
        return srgb_decode(np.tile(t, reps)[:H, :W])
    raise ValueError("--bg: transparent, #rrggbb or tile:<png>")


def add_common(r):
    r.add_argument("asset")
    r.add_argument("--root", action="append", default=[], help="name=folder or folder; first wins (repeatable)")
    r.add_argument("--facings", type=int, default=1, help="1 (key 0) or 8")
    r.add_argument("--dir64", default=None, help="comma list of exact facings 0..63 (overrides --facings)")
    r.add_argument("--mode", default=None, help="mode code (dt, dd, nu, a1, ...)")
    r.add_argument("--clip", default=None, help="clip name (overrides --mode)")
    r.add_argument("--frame", type=float, default=0.0)
    r.add_argument("--fps", type=float, default=25.0)
    r.add_argument("--time", type=float, default=None, help="seconds (overrides --frame)")
    r.add_argument("--scale", type=float, default=1.0)
    r.add_argument("--size", default="300x300")
    r.add_argument("--ss", type=int, default=2)
    r.add_argument("--msaa", type=int, default=4, choices=(1, 4))
    r.add_argument("--aniso", type=int, default=16)
    r.add_argument("--bg", default="transparent")
    r.add_argument("--pass", dest="pass_name", default="lit", choices=PASS_NAMES)
    r.add_argument("--glow", dest="glow", action="store_true", default=True)
    r.add_argument("--no-glow", dest="glow", action="store_false")
    r.add_argument("--glow-gain", type=float, default=None, help="overrides the rig's glow gain")
    r.add_argument("--hide", action="append", default=[], help="mesh:<n> part:<n> material:<substr> layer:<n> body")
    r.add_argument("--layer-scale", type=float, default=1.0)
    r.add_argument("--rig", default="default", help="default | game | vis:<vis json> | <rig.json>")
    r.add_argument("--save-rig", default=None)
    r.add_argument("--el", type=float, default=camera.EL_MAPS)
    r.add_argument("--az", type=float, default=camera.GAME_AZ)
    r.add_argument("--yaw0", type=float, default=camera.GAME_AZ)
    r.add_argument("--sign", type=float, default=-1.0)
    r.add_argument("--origin", default=None)
    r.add_argument("--tile", type=int, default=None)
    r.add_argument("--lod", type=int, default=0)
    r.add_argument("--no-gate", action="store_true", help="skip the GPU/slot-lock gate")
    r.add_argument("--out", default="hdview-out")
    r.add_argument("--name", default=None)
    r.add_argument("--store-min-mb", type=float, default=None,
                   help="outputs of at least this size move into the content store by hash (HDKIT_STORE / site store)")


def build_parser():
    ap = argparse.ArgumentParser(prog="python -m hdkit.view", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="render an asset")
    add_common(r)
    r.add_argument("--passes", default=None, help="comma list of passes (overrides --pass); >1 adds a contact sheet")
    r.add_argument("--stream", action="store_true")
    s = sub.add_parser("sheet", help="contact sheet modes x facings")
    add_common(s)
    s.add_argument("--modes", default="nu", help="comma list of mode codes or clip names (rows)")
    t = sub.add_parser("turntable", help="frames over one full turn, contact sheet, GIF/APNG")
    add_common(t)
    t.add_argument("--frames", type=int, default=24)
    t.add_argument("--anim", default="gif,apng", help="comma list of gif, apng, mp4")
    t.add_argument("--anim-fps", type=float, default=12.0)
    t.add_argument("--sheet-cols", type=int, default=8)
    w = sub.add_parser("watch", help="re-run a command when an input file changes")
    w.add_argument("--every", type=float, default=1.0)
    w.add_argument("--max-runs", type=int, default=None)
    w.add_argument("--idle-exit", type=float, default=None)
    w.add_argument("--also", action="append", default=[], help="more files to watch")
    w.add_argument("inner", nargs=argparse.REMAINDER, help="render|sheet|turntable <asset> [options]")
    g = sub.add_parser("rig", help="write a light rig file")
    g.add_argument("spec")
    g.add_argument("out")
    ls = sub.add_parser("ls", help="list units, models, or the clips of one asset, over the roots (JSON)")
    ls.add_argument("kind", choices=("units", "models", "clips"))
    ls.add_argument("asset", nargs="?", default=None)
    ls.add_argument("--root", action="append", default=[])
    ls.add_argument("--pattern", default=None, help="substring or fnmatch pattern on the logical path")
    ls.add_argument("--limit", type=int, default=200)
    ls.add_argument("--lod", type=int, default=0)
    rs = sub.add_parser("resolve", help="which root answers a logical path (JSON)")
    rs.add_argument("path")
    rs.add_argument("--root", action="append", default=[])
    cm = sub.add_parser("camera", help="the game camera as numbers (JSON)")
    cm.add_argument("--height", type=float, default=900.0)
    cm.add_argument("--zoom", type=float, default=1.0)
    cp = sub.add_parser("compare", help="a render PNG against a game shot: IoU, luma, cap colour (JSON, panel PNG)")
    cp.add_argument("render")
    cp.add_argument("shot")
    cp.add_argument("--twin", default=None, help="the same shot without the unit (gives the unit's mask)")
    cp.add_argument("--mask", default=None, help="the unit's mask in the shot (PNG, white = unit, or .npy)")
    cp.add_argument("--shot-feet", required=True, help="x,y: the unit's feet pixel in the shot")
    cp.add_argument("--render-feet", default=None, help="x,y in the render (default its centre, 3/4 down)")
    cp.add_argument("--exclude", action="append", default=[], help="x0,y0,x1,y1 shot pixels to leave out (repeatable)")
    cp.add_argument("--reach", type=int, default=10)
    cp.add_argument("--panel", default=None, help="write the comparison panel PNG here")
    cp.add_argument("--out", default=None, help="write the JSON here")
    sub.add_parser("gate", help="may a GPU job run now (JSON; exit 1 = busy)")
    from . import export_web
    export_web.add_parsers(sub, add_common)
    return ap


def facings(a):
    if a.dir64:
        return [(None, int(x)) for x in a.dir64.split(",")]
    return [(k, camera.key_dir64(k)) for k in range(max(1, a.facings))]


def clip_of(code):
    return scene.MODE_CLIP.get(code.lower(), code) if code else None


def clip_name(a):
    if a.clip:
        return a.clip
    return clip_of(a.mode)


class Session:
    """The device, the file layer and the unit of one command line; `reload()` re-reads every input (watch mode)."""

    def __init__(self, a, log=print, R=None):
        from . import gpu, rig
        if not a.no_gate:
            from .. import gpugate
            rd = gpugate.check()
            if not rd.free:
                raise SystemExit("GPU gate: %s (use --no-gate to override)" % rd.why)
        self.a, self.log = a, log
        self.R = R or gpu.Renderer(msaa=a.msaa, aniso=a.aniso)
        self.rig_mod = rig
        self.reload()

    def reload(self):
        a = self.a
        self.rig = self.rig_mod.resolve(a.rig)
        if a.glow_gain is not None:
            self.rig.light.glow_gain = a.glow_gain
        if a.save_rig:
            self.rig.save(a.save_rig)
        self.R._tex.clear()
        self.R._skinned.clear()
        self.fs = vfs.Layered(vfs.parse_roots(a.root)) if not a.asset.startswith("card:") else None
        self.unit = None if self.fs is None else scene.load_unit(self.fs, a.asset, a.lod)

    def inputs(self) -> list:
        out = [h["path"] for h in self.fs.provenance()] if self.fs is not None else []
        if self.a.asset.startswith("card:"):
            out.append(str(Path(self.a.asset[5:]) / "frames.json"))
        spec = self.a.rig
        if spec.startswith("vis:"):
            out.append(spec[4:].split(";")[0])
        elif spec not in self.rig_mod.PRESETS:
            out.append(spec)
        return out

    def name(self):
        a = self.a
        return a.name or (Path(a.asset.split(":", 1)[-1]).stem if self.unit is None else self.unit.name)

    def camera(self, scale=None):
        a = self.a
        return camera.OrthoCamera(a.el, a.az, camera.K_1600x900 * (a.scale if scale is None else scale))

    def prepare(self, d64, key, clip, t, yaw=None):
        a = self.a
        cam = self.camera()
        if self.unit is None:
            u = scene.load_card(a.asset.split(":", 1)[1], a.mode or "nu", key if key is not None else round(d64 / 8) % 8,
                                int(a.frame))
            y = 0.0
        else:
            u, y = self.unit, (camera.facing_yaw(d64, a.yaw0, a.sign) if yaw is None else yaw)
        prep = self.R.prepare(u, clip, t, y, cam, layer_scale=a.layer_scale).select(a.hide)
        return prep, cam, y

    def image(self, prep, cam, size, origin, pass_name, bg=None):
        a = self.a
        return self.R.render(prep, cam, size, origin, pass_name, None, a.glow, a.ss, a.tile, bg,
                             rig=self.rig.for_mode(getattr(a, "mode", None)))

    def measures(self, prep, cam, origin, img=None) -> dict:
        scr = np.concatenate([cam.to_pixels(dr.world.reshape(-1, 3), origin).reshape(-1, 3, 2) for dr in prep.draws]) \
            if prep.draws else np.zeros((0, 3, 2))
        tex = np.concatenate([dr.uv_tris for dr in prep.draws]) if prep.draws else np.zeros((0, 3, 2))
        out = {"texels_per_pixel": metrics.texels_per_pixel(scr, tex), "pose": prep.pose, "notes": prep.notes}
        if img is not None:
            out["image"] = metrics.image(img)
        return out

    def report(self, extra=None) -> dict:
        a = self.a
        W, H = parse_size(a.size)
        rep = {"command": a.cmd, "asset": a.asset, "adapter": dict(self.R.adapter.info), "max_texture": self.R.max_tex,
               "camera": {"el": a.el, "az": a.az, "k": camera.K_1600x900 * a.scale, "scale": a.scale},
               "size": [W, H], "ss": a.ss, "msaa": a.msaa, "glow": a.glow, "hide": a.hide, "layer_scale": a.layer_scale,
               "rig": self.rig.as_dict(), "clip": clip_name(a), "images": []}
        if self.fs is not None:
            rep["files"] = self.fs.provenance()
            rep["unit_notes"] = self.unit.notes
            rep["clips"] = {n: {"duration": c.duration, "decodable": c.decodable()} for n, c in self.unit.clips.items()}
        rep.update(extra or {})
        return rep


def _origin(a, W, H):
    return tuple(float(x) for x in a.origin.split(",")) if a.origin else (W / 2.0, H * 0.75)


def _time(a):
    return a.time if a.time is not None else a.frame / a.fps


def _save(img, path):
    from PIL import Image
    Image.fromarray(img).save(path)
    return str(path)


def _finish(a, report, out):
    """Large outputs (at least --store-min-mb) move into the content store by hash (hdkit.store); metrics.json last."""
    if getattr(a, "store_min_mb", None) is not None:
        from .. import store
        paths = [e["png"] for e in report["images"] if e.get("png")] + [report[k] for k in ("sheet",) if report.get(k)]
        paths += report.get("anim", [])
        moved = store.offload(paths, int(a.store_min_mb * (1 << 20)), out / "art-manifest.json",
                              {"command": a.cmd, "asset": a.asset})
        if moved:
            for e in report["images"]:
                if e.get("png") in moved:
                    e["stored"] = moved[e["png"]]
            if report.get("sheet") in moved:
                report["sheet_stored"] = moved[report["sheet"]]
            report["stored"] = list(moved.values())
            report["art_manifest"] = str(out / "art-manifest.json")
    report["metrics"] = str(out / "metrics.json")
    (out / "metrics.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report


def render_cmd(a, log=print, S=None) -> dict:
    S = S or Session(a, log)
    W, H = parse_size(a.size)
    origin = _origin(a, W, H)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    bg = parse_bg(a.bg, (W, H))
    clip, t = clip_name(a), _time(a)
    passes = a.passes.split(",") if getattr(a, "passes", None) else [a.pass_name]
    for p in passes:
        if p not in PASS_NAMES:
            raise SystemExit("unknown pass %s" % p)
    name = S.name()
    report = S.report({"passes": passes, "time": t, "origin": origin})
    if getattr(a, "stream", False) and (len(facings(a)) != 1 or len(passes) != 1):
        raise SystemExit("--stream renders one facing and one pass")
    cells, labels = [], []
    for p in passes:
        for key, d64 in facings(a):
            t0 = time.time()
            prep, cam, yaw = S.prepare(d64, key, clip, t)
            tag = ("k%d" % key) if key is not None else ("d%02d" % d64)
            if len(passes) > 1 or p != "lit":
                tag = "%s_%s" % (p, tag)
            png = out / ("%s_%s.png" % (name, tag))
            if getattr(a, "stream", False):
                info = S.R.render_streamed(prep, cam, (W, H), origin, png, p, None, a.glow, a.ss, a.tile or 4096, log=log,
                                           rig=S.rig)
                entry = {"pass": p, "facing_key": key, "dir64": d64, "yaw": yaw, "png": str(png), "stream": info}
                entry.update(S.measures(prep, cam, origin))
            else:
                img = S.image(prep, cam, (W, H), origin, p, bg)
                _save(img, png)
                entry = {"pass": p, "facing_key": key, "dir64": d64, "yaw": yaw, "png": str(png)}
                entry.update(S.measures(prep, cam, origin, img))
                cells.append(img)
                labels.append("%s %s" % (p, tag.split("_")[-1]))
            entry["seconds"] = round(time.time() - t0, 2)
            report["images"].append(entry)
            log("%s: %s" % (png.name, json.dumps({k: entry.get("image", {}).get(k) for k in ("height_px", "luma_mean", "coverage")})))
    if len(passes) > 1 and cells:
        from . import sheets
        nf = len(facings(a))
        sh = sheets.grid(cells, nf, labels, title="%s: passes x facings, rig %s" % (name, S.rig.name))
        sp = out / ("%s_passes.png" % name)
        sh.save(sp)
        report["sheet"] = str(sp)
    _finish(a, report, out)
    return report


def sheet_cmd(a, log=print, S=None) -> dict:
    from . import sheets
    S = S or Session(a, log)
    W, H = parse_size(a.size)
    origin = _origin(a, W, H)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    bg = parse_bg(a.bg, (W, H))
    modes = [m for m in a.modes.split(",") if m]
    t = _time(a)
    name = S.name()
    report = S.report({"modes": modes, "time": t, "pass": a.pass_name})
    cells, labels = [], []
    for m in modes:
        clip = clip_of(m)
        for key, d64 in facings(a):
            prep, cam, yaw = S.prepare(d64, key, clip, t)
            img = S.image(prep, cam, (W, H), origin, a.pass_name, bg)
            cells.append(img)
            tag = ("k%d" % key) if key is not None else ("d%02d" % d64)
            labels.append("%s %s" % (m, tag))
            e = {"mode": m, "clip": clip, "facing_key": key, "dir64": d64, "yaw": yaw}
            e.update(S.measures(prep, cam, origin, img))
            report["images"].append(e)
    sh = sheets.grid(cells, len(facings(a)), labels, row_labels=modes,
                     title="%s: modes x facings, pass %s, rig %s" % (name, a.pass_name, S.rig.name))
    sp = out / ("%s_sheet_%s.png" % (name, a.pass_name))
    sh.save(sp)
    report["sheet"] = str(sp)
    _finish(a, report, out)
    log("sheet %s (%d cells)" % (sp, len(cells)))
    return report


def turntable_cmd(a, log=print, S=None) -> dict:
    from . import sheets
    S = S or Session(a, log)
    if S.unit is None:
        raise SystemExit("turntable: a model or unit, not a card")
    W, H = parse_size(a.size)
    origin = _origin(a, W, H)
    out = Path(a.out)
    fdir = out / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    bg = parse_bg(a.bg, (W, H))
    clip, t = clip_name(a), _time(a)
    d64 = facings(a)[0][1]
    start = camera.facing_yaw(d64, a.yaw0, a.sign)
    name = S.name()
    report = S.report({"frames": a.frames, "start_dir64": d64, "time": t, "pass": a.pass_name})
    frames, labels = [], []
    for i, yaw in enumerate(sheets.turntable_yaws(a.frames, start)):
        prep, cam, _y = S.prepare(d64, None, clip, t, yaw=yaw)
        img = S.image(prep, cam, (W, H), origin, a.pass_name, bg)
        png = fdir / ("%s_t%03d.png" % (name, i))
        _save(img, png)
        frames.append(img)
        labels.append("%d: %+.0f deg" % (i, yaw - start))
        e = {"frame": i, "yaw": yaw, "png": str(png)}
        e.update(S.measures(prep, cam, origin, img))
        report["images"].append(e)
    sh = sheets.grid(frames, min(a.sheet_cols, a.frames), labels,
                     title="%s turntable: %d frames, pass %s, rig %s" % (name, a.frames, a.pass_name, S.rig.name))
    sp = out / ("%s_turntable_sheet.png" % name)
    sh.save(sp)
    report["sheet"] = str(sp)
    report["anim"] = []
    for kind in [k for k in a.anim.split(",") if k]:
        ext = {"gif": ".gif", "apng": ".png", "mp4": ".mp4"}.get(kind)
        if ext is None:
            raise SystemExit("--anim: gif, apng, mp4")
        p = out / ("%s_turntable%s%s" % (name, ".anim" if ext == ".png" else "", ext))
        sheets.write_anim(frames, p, a.anim_fps)
        report["anim"].append(str(p))
    _finish(a, report, out)
    log("turntable %s, %s" % (sp, report["anim"]))
    return report


COMMANDS = {"render": render_cmd, "sheet": sheet_cmd, "turntable": turntable_cmd}


def watch_cmd(w, log=print) -> int:
    from . import sheets
    if not w.inner or w.inner[0] not in COMMANDS:
        raise SystemExit("watch: render|sheet|turntable <asset> [options]")
    a = build_parser().parse_args(w.inner)
    S = Session(a, log)
    fn = COMMANDS[a.cmd]
    first = [True]

    def run():
        if not first[0]:
            S.reload()
        first[0] = False
        fn(a, log, S)

    return sheets.watch(run, lambda: S.inputs() + list(w.also), w.every, w.max_runs, w.idle_exit, log)


def _xy(s):
    return tuple(float(v) for v in s.split(",")) if s else None


def _img(path, mode):
    from PIL import Image
    return np.array(Image.open(path).convert(mode))


def compare_cmd(a, log=print) -> dict:
    from . import compare
    mask = None
    if a.mask:
        mask = np.load(a.mask) if a.mask.endswith(".npy") else _img(a.mask, "L") > 127
    render = _img(a.render, "RGBA")
    res, extra = compare.compare(render, _img(a.shot, "RGB"), _xy(a.shot_feet), _xy(a.render_feet),
                                 _img(a.twin, "RGB") if a.twin else None, mask,
                                 [tuple(float(v) for v in e.split(",")) for e in a.exclude], a.reach)
    res.update(render=str(a.render), shot=str(a.shot), twin=a.twin, given_mask=a.mask)
    if a.panel:
        from PIL import Image
        Path(a.panel).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(compare.panel(render, extra, res)).save(a.panel)
        res["panel"] = str(a.panel)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    return res


def info_cmd(a) -> dict:
    """ls, resolve, camera, gate: the JSON the command prints."""
    from . import assets
    if a.cmd == "ls":
        return assets.listing(vfs.Layered(vfs.parse_roots(a.root)), a.kind, a.pattern, a.asset, a.limit, a.lod)
    if a.cmd == "resolve":
        return assets.resolve(vfs.Layered(vfs.parse_roots(a.root)), a.path)
    if a.cmd == "camera":
        return camera.facts(a.height, a.zoom)
    from .. import gpugate
    return gpugate.check().as_dict()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["map"]:
        from .mapview import cli as mapcli
        return mapcli.main(argv[1:])
    a = build_parser().parse_args(argv)
    if a.cmd in ("ls", "resolve", "camera", "gate"):
        r = info_cmd(a)
        print(json.dumps(r, indent=1, default=str))
        return 0 if a.cmd != "gate" or r["free"] else 1
    if a.cmd == "compare":
        print(json.dumps(compare_cmd(a), indent=1, default=str))
        return 0
    if a.cmd in COMMANDS:
        COMMANDS[a.cmd](a)
    elif a.cmd == "watch":
        watch_cmd(a)
    elif a.cmd in ("export-web", "serve-web"):
        from . import export_web
        return export_web.run(a)
    elif a.cmd == "rig":
        from . import rig
        p = rig.resolve(a.spec).save(a.out)
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
