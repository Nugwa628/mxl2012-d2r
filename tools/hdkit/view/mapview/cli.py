"""python -m hdkit.view map <command> ...: the map viewer (docs/mapview.md).

  ls [--source mod|d2r] [--pattern p]            maps of an extract (JSON)
  info <map>                                      size, level, tile files, palette act, notes (JSON)
  classic <map> [--cells x0,y0,x1,y1] [--scale s] [--layers ...] [--isolate]
                                                  classic render (PNG + JSON) of the whole map or a cell range
  hd <map> [--cells ...] [--scale s] [--layers terrain,walls,props,objects,lights] [--el 30 --az 45]
                                                  HD render of the map's D2R preset in the game camera (or orbit angles)
  sheet <map> [--cells ...] [--scale s]           classic | HD side by side, same cells on the same pixels
  cell <map> <x> <y> [--near 1]                   what is on a cell: tiles, flags, objects, HD entities (JSON)
  edit ...                                        working copies: see `map edit -h`
  serve [<map>] [--port 8766]                     the map page (pan/zoom, classic/HD/overlay, cell info, region
                                                  screenshots and renders) on 127.0.0.1; Ctrl+C stops it

<map> is the path below data/global/tiles without .ds1 (act1/cathedrl/cathy3, expansion/ghetto/cypherpunk).
--source auto (default: the mod's map when it has one, else D2R's), mod or d2r; --work <folder> reads a working copy.
Layers (classic): floor shadow wall lower roof special objects labels grid coords walk; "-roof,+grid" edits the
defaults (floor shadow wall lower roof objects labels), a plain list replaces them, "all" = every one.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import api


def _common(p, cells=True):
    p.add_argument("map")
    p.add_argument("--source", default="auto", choices=("auto", "mod", "d2r"))
    p.add_argument("--work", default=None, help="a working copy folder (map edit init)")
    if cells:
        p.add_argument("--cells", default=None, help="x0,y0,x1,y1 inclusive cell range (default: whole map)")
        p.add_argument("--scale", type=float, default=None, help="pixels per native classic pixel (default 1 for a "
                       "region, 0.5 for a whole map)")
        p.add_argument("--out", default=None, help="output folder (default /d2work/runs/mapview/<map>)")
        p.add_argument("--png", default=None, help="exact output PNG path")
        p.add_argument("--rise", type=int, default=None, help="native px kept above the top cells (default: tallest tile)")


def build_parser(prog="python -m hdkit.view map"):
    ap = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("ls", help="list maps")
    ls.add_argument("--source", default="mod", choices=("mod", "d2r"))
    ls.add_argument("--pattern", default=None)
    i = sub.add_parser("info", help="map facts (JSON)")
    _common(i, cells=False)
    c = sub.add_parser("classic", help="classic render")
    _common(c)
    c.add_argument("--layers", default=None)
    c.add_argument("--isolate", action="store_true", help="draw only the range's cells")
    c.add_argument("--grid-every", type=int, default=5)
    c.add_argument("--light", type=float, default=1.0)
    _hd_args(sub.add_parser("hd", help="HD render of the D2R preset"))
    s = sub.add_parser("sheet", help="classic | HD side by side")
    _hd_args(s)
    s.add_argument("--classic-layers", default=None)
    ce = sub.add_parser("cell", help="cell info (JSON)")
    _common(ce, cells=False)
    ce.add_argument("x", type=int)
    ce.add_argument("y", type=int)
    ce.add_argument("--near", type=float, default=0.0, help="also HD entities this many cells around")
    ce.add_argument("--no-hd", action="store_true", help="skip the preset (no CASC read)")
    sv = sub.add_parser("serve", help="the map page on 127.0.0.1 (Ctrl+C stops it)")
    sv.add_argument("map", nargs="?", default=None)
    sv.add_argument("--source", default="auto", choices=("auto", "mod", "d2r"))
    sv.add_argument("--port", type=int, default=8766)
    from . import edit
    edit.add_parser(sub)
    return ap


def _hd_args(h):
    _common(h)
    h.add_argument("--layers", default=None, help="terrain,walls,props,prefabs,objects,lights (default all but objects)")
    h.add_argument("--preset", default=None, help="logical preset path (default data/hd/env/preset/<map>.json)")
    h.add_argument("--root", action="append", default=[], help="hdkit roots (default: casc); a working copy adds its own")
    h.add_argument("--el", type=float, default=None)
    h.add_argument("--az", type=float, default=None)
    h.add_argument("--rig", default="vis", help="vis (the map biome's own vis file, default), game, default, vis:<file> or a rig JSON")
    h.add_argument("--ss", type=int, default=1)
    h.add_argument("--no-gate", action="store_true")
    h.add_argument("--grid", action="store_true", help="draw the cell grid over the HD image")


def _default_scale(a):
    if a.scale is not None:
        return a.scale
    return 1.0 if a.cells else 0.5


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    log = lambda s: print(s, file=sys.stderr)   # noqa: E731
    if a.cmd == "ls":
        r = api.list_maps(a.source, a.pattern)
    elif a.cmd == "info":
        r = api.map_info(a.map, a.source, a.work)
    elif a.cmd == "classic":
        r = api.render_classic(a.map, a.cells, _default_scale(a), a.layers, a.source, a.work, a.isolate, a.out, a.png,
                               a.grid_every, a.light, a.rise, log=log)
    elif a.cmd in ("hd", "sheet"):
        fn = api.render_hd if a.cmd == "hd" else api.render_sheet
        kw = dict(cells=a.cells, scale=_default_scale(a), layers=a.layers, source=a.source, work=a.work, out=a.out,
                  png=a.png, preset=a.preset, roots=a.root or None, el=a.el, az=a.az, rig=a.rig, ss=a.ss,
                  gate=not a.no_gate, rise=a.rise, grid=a.grid, log=log)
        if a.cmd == "sheet":
            kw["classic_layers"] = a.classic_layers
        r = fn(a.map, **kw)
    elif a.cmd == "cell":
        r = api.cell_info(a.map, a.x, a.y, a.source, a.work, near=a.near, hd=not a.no_hd)
    elif a.cmd == "serve":
        from . import webmap
        return webmap.serve(a.map, a.source, a.port)
    elif a.cmd == "edit":
        from . import edit
        r = edit.run(a, log)
    else:
        raise SystemExit("unknown command")
    print(json.dumps(r, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
