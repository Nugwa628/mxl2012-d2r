"""One call per map-viewer action, shared by the CLI (`python -m hdkit.view map ...`), the MCP server and the web page.
Results are plain dicts (JSON-ready); images are written as PNG next to a JSON of the same name.

Working copies: `work` names a folder made by mapview.edit (`map edit init`); the map's .ds1 and preset JSON are then read
from it instead of the extracts. Outputs default to /d2work/runs/mapview/<map name>/ (MAPVIEW_OUT overrides).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import classic, world
from .frame import parse_cells

DEFAULT_OUT = Path(os.environ.get("MAPVIEW_OUT") or "/d2work/runs/mapview")
_SOURCES = {}


def out_dir(src, out=None) -> Path:
    p = Path(out) if out else DEFAULT_OUT / src.key.replace("/", "_")
    p.mkdir(parents=True, exist_ok=True)
    return p


def open_map(name: str, source: str = "auto", work: str | None = None, fresh: bool = False):
    """A world.MapSource (cached per (name, source, work); a working copy is re-read every call)."""
    if work:
        from . import edit
        wc = edit.WorkCopy.open(work)
        return world.MapSource(wc.map, wc.source, ds1_path=wc.ds1_path)
    k = (world.norm(name), source)
    if fresh or k not in _SOURCES:
        _SOURCES[k] = world.MapSource(name, source)
    return _SOURCES[k]


def tag_of(cells, scale, extra=""):
    c = "whole" if not cells else "c" + "_".join(str(int(v)) for v in str(cells).replace(":", ",").split(","))
    return "%s_s%g%s" % (c, scale, extra)


def save(img, info: dict, path: Path) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    info["png"] = str(path)
    path.with_suffix(".json").write_text(json.dumps(info, indent=1, default=str), encoding="utf-8")
    return info


def render_classic(name: str, cells: str | None = None, scale: float = 1.0, layers: str | None = None,
                   source: str = "auto", work: str | None = None, isolate: bool = False, out: str | None = None,
                   png: str | None = None, grid_every: int = 5, light: float = 1.0, rise: int | None = None,
                   log=None) -> dict:
    src = open_map(name, source, work)
    fr = classic.frame_of(src, cells, scale, rise)
    opt = classic.Options(layers=classic.parse_layers(layers), isolate=isolate, grid_every=grid_every, light=light)
    img, info = classic.render(src, fr, opt, log=log)
    p = Path(png) if png else out_dir(src, out) / ("classic_%s%s.png" % (tag_of(cells, scale), "_work" if work else ""))
    if work:
        info["work"] = work
    return save(img, info, p)


def map_info(name: str, source: str = "auto", work: str | None = None) -> dict:
    src = open_map(name, source, work)
    d = src.describe()
    d["frame_whole_scale1"] = classic.frame_of(src, None, 1.0).as_dict()
    from collections import Counter
    d["object_types"] = dict(Counter(o.type for o in src.ds.objects))
    return d


def list_maps(source: str = "mod", pattern: str | None = None) -> dict:
    r = world.Roots()
    ms = [m for m in r.maps(source) if not pattern or pattern.lower() in m]
    return {"source": source, "count": len(ms), "maps": ms}


def cells_of(src, cells):
    return parse_cells(cells, src.ds.width, src.ds.height)


def _work_data(work):
    if not work:
        return None
    from . import edit
    return edit.WorkCopy.open(work).data_dir


def render_hd(name: str, cells: str | None = None, scale: float = 1.0, layers: str | None = None, source: str = "auto",
              work: str | None = None, out: str | None = None, png: str | None = None, preset: str | None = None,
              roots=None, el=None, az=None, rig: str = "vis", ss: int = 1, gate: bool = True, rise: int | None = None,
              grid: bool = False, log=None, _return_image=False, pass_name: str = "lit", player=None) -> dict:
    """pass_name: lit, albedo, normal, ... (hd.render); player: (cell x, y) of a player's light, else none."""
    from . import hd
    src = open_map(name, source, work)
    fr = classic.frame_of(src, cells, scale, rise)
    lay = hd.parse_layers(layers)
    if grid:
        lay.add("grid")
    img, info = hd.render(src, fr, lay, preset, roots, _work_data(work), el, az, rig, ss, gate, log, pass_name=pass_name,
                          player=player)
    view = "" if el is None and az is None else "_el%g_az%g" % (el if el is not None else 30, az if az is not None else 45)
    p = Path(png) if png else out_dir(src, out) / ("hd_%s%s%s.png" % (tag_of(cells, scale), view, "_work" if work else ""))
    if work:
        info["work"] = work
    info = save(img, info, p)
    if _return_image:
        return info, img
    return info


def render_sheet(name: str, cells: str | None = None, scale: float = 1.0, layers: str | None = None,
                 classic_layers: str | None = None, source: str = "auto", work: str | None = None, out: str | None = None,
                 png: str | None = None, blend: bool = True, log=None, **hd_kw) -> dict:
    """Classic | HD (| 50 % blend) side by side, one header row naming map, cells and scale."""
    from PIL import Image, ImageDraw
    src = open_map(name, source, work)
    hd_kw.pop("el", None), hd_kw.pop("az", None)
    ci = render_classic(name, cells, scale, classic_layers, source, work, out=out, rise=hd_kw.get("rise"), log=log)
    hi, himg = render_hd(name, cells, scale, layers, source, work, out=out, log=log, _return_image=True, **hd_kw)
    cimg = Image.open(ci["png"]).convert("RGBA")
    panels = [("classic", cimg), ("HD", himg)]
    if blend:
        bl = Image.alpha_composite(Image.new("RGBA", cimg.size, (0, 0, 0, 255)), cimg)
        bl = Image.blend(bl, Image.alpha_composite(Image.new("RGBA", himg.size, (0, 0, 0, 255)), himg), 0.5)
        panels.append(("50% blend", bl))
    W, H = cimg.size
    head = 28
    sheet = Image.new("RGBA", (W * len(panels) + 8 * (len(panels) - 1), H + head), (24, 24, 28, 255))
    d = ImageDraw.Draw(sheet)
    f = classic._font(16)
    for i, (lab, im) in enumerate(panels):
        x = i * (W + 8)
        sheet.alpha_composite(Image.alpha_composite(Image.new("RGBA", im.size, (0, 0, 0, 255)), im), (x, head))
        d.text((x + 6, 5), "%s  %s  cells %s  scale %g" % (lab, src.key, cells or "whole", scale), fill=(230, 230, 230),
               font=f)
    p = Path(png) if png else out_dir(src, out) / ("sheet_%s%s.png" % (tag_of(cells, scale), "_work" if work else ""))
    info = {"renderer": "sheet", "map": src.key, "classic": ci, "hd": hi, "panels": [lab for lab, _ in panels]}
    return save(sheet, info, p)


def cell_info(name: str, x: int, y: int, source: str = "auto", work: str | None = None, near: float = 0.0,
              hd: bool = True, roots=None) -> dict:
    from . import dt1 as T
    src = open_map(name, source, work)
    ds = src.ds
    if not (0 <= x < ds.width and 0 <= y < ds.height):
        raise ValueError("cell %d,%d outside the map (%dx%d)" % (x, y, ds.width, ds.height))
    info = ds.cell_info(x, y)

    def tile_of(entry, orientation):
        c = entry["dword"]
        if not c or entry["prop1"] == 0:
            entry["tile"] = None
            return
        v = src.lib.variants(orientation, entry["style"], entry["sequence"])
        tl = src.lib.pick(orientation, entry["style"], entry["sequence"], x, y)
        entry["tile"] = None if tl is None else {
            "dt1": src.lib.file_of.get((orientation, entry["style"], entry["sequence"])), "index_in_dt1": tl.index,
            "variants": len(v), "rarities": [t.rarity for t in v], "size": [tl.width, tl.height],
            "roof_height": tl.roof_height, "orientation_name": T.ORIENT_NAMES.get(orientation, "?"),
            "flags": [" ".join("%02x" % v for v in row) for row in tl.flag_grid().tolist()]}
        if tl is None:
            entry["missing"] = "no tile (%d, %d, %d) in the map's tile files" % (orientation, entry["style"], entry["sequence"])

    for f in info["floors"]:
        tile_of(f, 0)
    for w in info["walls"]:
        tile_of(w, w["orientation"])
    tile_of(info["shadow"], T.SHADOW)
    g = classic.cell_flags(src, x, y)
    info["walk"] = {"flags": [" ".join("%02x" % v for v in row) for row in g.tolist()], "blocked_subtiles": int(((g & 1) != 0).sum()),
                    "legend": {"1": "block walk", "2": "block light+LOS", "4": "block jump", "8": "block player",
                               "32": "block light"}}
    info["objects"] = [{"index": i, "type": o.type, "id": o.id, "x": o.x, "y": o.y, "flags": o.flags,
                        "name": src.object_name(o.type, o.id)} for i, o in ds.objects_in_cell(x, y)]
    out = {"map": src.key, "source": src.source, "cell": [x, y], "subtiles": [x * 5, y * 5, x * 5 + 4, y * 5 + 4],
           "hd_world_box": [x * 10.0, y * 10.0, (x + 1) * 10.0, (y + 1) * 10.0], "classic": info}
    if hd:
        from . import hd as H
        try:
            specs = H.roots_for(src.source, _work_data(work), roots)
            fs = H.fs_for(specs)
            logical = H.find_preset(fs, src.key, src.source)
            out["hd"] = {"preset": logical, "entities": H.entities_near(fs, logical, x, y, near) if logical else []}
        except Exception as e:      # CASC unavailable etc.: the classic part still answers
            out["hd"] = {"error": str(e)}
    return out
