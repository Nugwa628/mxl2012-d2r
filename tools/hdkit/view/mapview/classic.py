"""The classic map: a .ds1's layers drawn with its resolved .dt1 tiles and the act palette, in D2's iso draw order.

Draw order (OpenDiablo2 d2maprenderer, which follows the game; ds1edit draws the same layers):
  pass 1, cell by cell (rows y, then x):  lower walls (orientations 16-19), floors (layer 1, 2), shadows (13: darkened 50%)
  pass 2, cell by cell:                   walls of orientations 1-9, 12 (pillars), 14 (trees), wall layer by layer;
                                          a north-corner right part (3) also draws its left part (4) of the same key
  pass 3:                                 roofs (15), lifted by the tile's roof height
Special tiles (10, 11: warps, level-entry markers) are invisible in the game; `special` draws them faded.
A cell whose prop1 byte is 0 or whose hidden bit is set draws nothing (ds1edit and OpenDiablo2's rule).

Overlays drawn after scaling, in output pixels: grid (cell diamonds) with coordinates every `grid_every` cells, the
sub-tile walk flags (red: blocks walking, blue: blocks light only), and object markers with names (type 1 monsters red,
type 2 objects cyan, the .ds1 index in brackets).

Big maps (downtown: 251 x 251 cells = 40,160 x 20,000 native px) are drawn in horizontal strips and scaled per strip, so
memory stays at one strip.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from . import dt1 as T
from .frame import CELL_DX, CELL_DY, Frame, parse_cells

LAYERS = ("floor", "shadow", "wall", "lower", "roof", "special", "objects", "grid", "coords", "walk", "labels")
DEFAULT_ON = {"floor", "shadow", "wall", "lower", "roof", "objects", "labels"}
STRIP_ROWS = 2048


@dataclass
class Options:
    layers: set = field(default_factory=lambda: set(DEFAULT_ON))
    floor_layers: tuple | None = None      # indexes of floor layers to draw (None = all)
    wall_layers: tuple | None = None
    isolate: bool = False                  # draw only the cells of the frame's range (else all cells that reach into it)
    grid_every: int = 5
    bg: tuple = (0, 0, 0, 0)
    label_size: int = 11
    light: float = 1.0                     # brightness multiplier (1 = the palette as is)


def parse_layers(spec: str | None) -> set:
    """'floor,wall,-roof,+grid' -> set. A list without +/- replaces the defaults; +x / -x edit them; 'all' = every layer."""
    if not spec:
        return set(DEFAULT_ON)
    items = [s.strip() for s in spec.split(",") if s.strip()]
    if all(s[0] in "+-" for s in items):
        out = set(DEFAULT_ON)
    else:
        out = set()
    for s in items:
        if s == "all":
            out |= set(LAYERS)
        elif s.startswith("-"):
            out.discard(s[1:])
        else:
            n = s.lstrip("+")
            if n not in LAYERS:
                raise ValueError("unknown layer %s (one of %s)" % (n, ", ".join(LAYERS)))
            out.add(n)
    return out


def tile_rise(src) -> int:
    """How far above its cell's top corner the tallest tile of the map reaches (native px), for the frame."""
    top = 0
    ds = src.ds
    used = set()
    for j, w in enumerate(ds.walls()):
        o = ds.orientation(j)
        m = (w & 0xFF) != 0
        keys = np.stack([o[m], (w[m] >> 20) & 0x3F, (w[m] >> 8) & 0x3F], 1) if m.any() else np.zeros((0, 3), int)
        used |= {tuple(int(v) for v in k) for k in np.unique(keys, axis=0)}
        if T.NC_RIGHT in o[m]:
            used |= {(T.NC_LEFT, s, q) for (oo, s, q) in list(used) if oo == T.NC_RIGHT}
    for k in used:
        tiles = src.lib.by_key.get(k)
        if not tiles:
            continue
        tl = tiles[0]
        if tl.orientation in (0, T.SHADOW):
            continue
        _img, _x0, y0 = tl.image()
        off = (-tl.roof_height) if tl.orientation == T.ROOF else 80
        top = max(top, -(y0 + off))
    return int(min(max(top + 16, 160), 1600))


def frame_of(src, cells=None, scale=1.0, rise=None) -> Frame:
    ds = src.ds
    x0, y0, x1, y1 = cells if isinstance(cells, tuple) else parse_cells(cells, ds.width, ds.height)
    return Frame(x0, y0, x1, y1, float(scale), tile_rise(src) if rise is None else int(rise))


def draw_list(src, opt: Options):
    """[(tile, native x, native y, mode, cell x, cell y)] in draw order; mode 0 opaque, 1 shadow, 2 faded (special)."""
    ds, lib = src.ds, src.lib
    L = opt.layers
    floors = [(j, f) for j, f in enumerate(ds.floors()) if opt.floor_layers is None or j in opt.floor_layers]
    walls = [(j, w, ds.orientation(j)) for j, w in enumerate(ds.walls()) if opt.wall_layers is None or j in opt.wall_layers]
    shadow = ds.shadow
    out = []
    missing = {}

    def add(o, c, x, y, mode=0, lift=None):
        if (c & 0xFF) == 0 or (c >> 31) & 1:
            return
        st, sq = (c >> 20) & 0x3F, (c >> 8) & 0x3F
        tl = lib.pick(o, st, sq, x, y)
        if tl is None:
            missing[(o, st, sq)] = missing.get((o, st, sq), 0) + 1
            return
        img, bx, by = tl.image()
        tx = (x - y) * CELL_DX - 80 + bx
        if o == 0:
            ty = (x + y) * CELL_DY + by
        elif o == T.ROOF:
            ty = (x + y) * CELL_DY + by - tl.roof_height
        else:
            ty = (x + y) * CELL_DY + by + 80
        out.append((tl, tx, ty, mode, x, y))

    H, W = ds.height, ds.width
    nz_f = [f != 0 for _j, f in floors]
    for y in range(H):
        for x in range(W):
            if "lower" in L:
                for j, w, o in walls:
                    c = int(w[y, x])
                    if c and o[y, x] in T.LOWER:
                        add(int(o[y, x]), c, x, y)
            if "floor" in L:
                for (j, f), nz in zip(floors, nz_f):
                    if nz[y, x]:
                        add(0, int(f[y, x]), x, y)
            if "shadow" in L:
                c = int(shadow[y, x])
                if c:
                    add(T.SHADOW, c, x, y, 1)
    for y in range(H):
        for x in range(W):
            for j, w, o in walls:
                c = int(w[y, x])
                if not c:
                    continue
                oo = int(o[y, x])
                if oo in T.UPPER and "wall" in L:
                    add(oo, c, x, y)
                    if oo == T.NC_RIGHT:
                        add(T.NC_LEFT, c, x, y)
                elif oo in (T.SPECIAL1, T.SPECIAL2) and "special" in L:
                    add(oo, c, x, y, 2)
    if "roof" in L:
        for y in range(H):
            for x in range(W):
                for j, w, o in walls:
                    c = int(w[y, x])
                    if c and o[y, x] == T.ROOF:
                        add(T.ROOF, c, x, y)
    return out, missing


def _blit(canvas, rect, items, pal_rgb):
    """Draw items into canvas (H, W, 3 uint8) + alpha (H, W) covering native rect (L, T, W, H)."""
    rgb, alpha = canvas
    L, Tp, Wd, Hd = rect
    for tl, tx, ty, mode, _x, _y in items:
        img, _bx, _by = tl.image()
        h, w = img.shape
        x0, y0 = tx - L, ty - Tp
        sx0, sy0 = max(0, -x0), max(0, -y0)
        dx0, dy0 = max(0, x0), max(0, y0)
        dx1, dy1 = min(Wd, x0 + w), min(Hd, y0 + h)
        if dx1 <= dx0 or dy1 <= dy0:
            continue
        sub = img[sy0:sy0 + (dy1 - dy0), sx0:sx0 + (dx1 - dx0)]
        m = sub != 0
        if not m.any():
            continue
        dst = rgb[dy0:dy1, dx0:dx1]
        if mode == 1:
            dst[m] = (dst[m] * 0.5).astype(np.uint8)
            a = alpha[dy0:dy1, dx0:dx1]
            a[m] = np.maximum(a[m], 128)
        elif mode == 2:
            dst[m] = ((dst[m].astype(np.uint16) + pal_rgb[sub[m]]) // 2).astype(np.uint8)
            a = alpha[dy0:dy1, dx0:dx1]
            a[m] = 255
        else:
            dst[m] = pal_rgb[sub[m]]
            alpha[dy0:dy1, dx0:dx1][m] = 255


def render(src, fr: Frame, opt: Options | None = None, log=None):
    """-> (PIL RGBA image of the frame, info dict)."""
    from PIL import Image
    opt = opt or Options()
    t0 = time.time()
    items, missing = draw_list(src, opt)
    if opt.isolate:
        items = [it for it in items if fr.x0 <= it[4] <= fr.x1 and fr.y0 <= it[5] <= fr.y1]
    pal = src.palette.astype(np.float32) * float(opt.light)
    pal = np.clip(pal, 0, 255).astype(np.uint8)
    # bounding boxes for the strip filter
    if items:
        bx0 = np.array([it[1] for it in items])
        by0 = np.array([it[2] for it in items])
        bx1 = bx0 + np.array([it[0].image()[0].shape[1] for it in items])
        by1 = by0 + np.array([it[0].image()[0].shape[0] for it in items])
    W, H = fr.size
    NW, NH = fr.native_size
    out = np.zeros((H, W, 4), np.uint8)
    out[..., :] = np.array(opt.bg, np.uint8)
    s = fr.scale
    # strip rows in native px; a multiple of 1/s when that is a whole number keeps strip edges on whole output rows
    step = STRIP_ROWS
    if s < 1 and abs(1 / s - round(1 / s)) < 1e-6:
        k = int(round(1 / s))
        step = max(k, (STRIP_ROWS // k) * k)
    y = 0
    drawn = 0
    while y < NH:
        h = min(step, NH - y)
        rect = (fr.left, fr.top + y, NW, h)
        rgb = np.zeros((h, NW, 3), np.uint8)
        rgb[...] = np.array(opt.bg[:3], np.uint8)
        alpha = np.zeros((h, NW), np.uint8)
        if items:
            sel = np.nonzero((bx1 > rect[0]) & (bx0 < rect[0] + NW) & (by1 > rect[1]) & (by0 < rect[1] + h))[0]
            drawn += len(sel)
            _blit((rgb, alpha), rect, [items[i] for i in sel], pal)
        a = alpha if opt.bg[3] == 0 else np.maximum(alpha, opt.bg[3])
        strip = np.dstack([rgb, a])
        oy0, oy1 = int(round(y * s)), int(round((y + h) * s))
        if oy1 > oy0:
            if s == 1:
                part = strip
            else:
                im = Image.fromarray(strip, "RGBA")
                resample = Image.NEAREST if s > 1 else Image.BOX
                part = np.asarray(im.resize((W, oy1 - oy0), resample))
            out[oy0:oy1] = part[:min(oy1, H) - oy0]
        y += h
    img = Image.fromarray(out, "RGBA")
    overlay(img, src, fr, opt)
    info = {"renderer": "classic", "map": src.key, "source": src.source, "frame": fr.as_dict(),
            "layers": sorted(opt.layers), "isolate": opt.isolate, "tiles_drawn": len(items),
            "missing_tiles": [{"orientation": k[0], "style": k[1], "sequence": k[2], "cells": n}
                              for k, n in sorted(missing.items())],
            "palette_act": src.act, "seconds": round(time.time() - t0, 2), "notes": list(src.notes)}
    if log:
        log("classic %s: %dx%d px, %d tiles, %d missing keys, %.1f s" % (src.key, W, H, len(items), len(missing),
                                                                        info["seconds"]))
    return img, info


# ---- overlays -------------------------------------------------------------------------------------------------------------
def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def overlay(img, src, fr: Frame, opt: Options):
    from PIL import ImageDraw
    L = opt.layers
    if not ({"grid", "coords", "walk", "objects"} & L):
        return
    d = ImageDraw.Draw(img, "RGBA")
    ds = src.ds
    xs = range(fr.x0, fr.x1 + 1)
    ys = range(fr.y0, fr.y1 + 1)
    if "walk" in L:
        _walk(d, src, fr, opt)
    if "grid" in L:
        for x in range(fr.x0, fr.x1 + 2):
            d.line([fr.px(x, fr.y0), fr.px(x, fr.y1 + 1)], fill=(255, 255, 255, 70 if x % opt.grid_every else 150), width=1)
        for y in range(fr.y0, fr.y1 + 2):
            d.line([fr.px(fr.x0, y), fr.px(fr.x1 + 1, y)], fill=(255, 255, 255, 70 if y % opt.grid_every else 150), width=1)
    if "coords" in L:
        f = _font(max(8, int(opt.label_size)))
        ev = max(1, opt.grid_every)
        for y in ys:
            for x in xs:
                if (x % ev == 0 and y % ev == 0) or (fr.x1 - fr.x0 < 12 and fr.y1 - fr.y0 < 12):
                    px, py = fr.px(x + 0.5, y + 0.5)
                    d.text((px, py), "%d,%d" % (x, y), fill=(255, 255, 160, 230), font=f, anchor="mm",
                           stroke_width=2, stroke_fill=(0, 0, 0, 200))
    if "objects" in L:
        f = _font(max(8, int(opt.label_size)))
        r = max(3.0, 6 * fr.scale)
        for i, ob in enumerate(ds.objects):
            cx, cy = (ob.x + 0.5) / 5.0, (ob.y + 0.5) / 5.0
            if not (fr.x0 <= cx < fr.x1 + 1 and fr.y0 <= cy < fr.y1 + 1):
                continue
            px, py = fr.px(cx, cy)
            col = {1: (255, 70, 70, 230), 2: (60, 220, 255, 230)}.get(ob.type, (255, 230, 60, 230))
            d.polygon([(px, py - r), (px + 2 * r, py), (px, py + r), (px - 2 * r, py)], outline=(0, 0, 0, 255), fill=col)
            if "labels" in L:
                d.text((px + 2 * r + 2, py), "[%d] %s" % (i, src.object_name(ob.type, ob.id)), fill=col[:3] + (255,),
                       font=f, anchor="lm", stroke_width=2, stroke_fill=(0, 0, 0, 220))


def cell_flags(src, x: int, y: int) -> np.ndarray:
    """5x5 [sy, sx] OR of the sub-tile flags of every tile drawn on the cell (floors and walls)."""
    ds, lib = src.ds, src.lib
    g = np.zeros((5, 5), np.uint8)
    for f in ds.floors():
        c = int(f[y, x])
        if c & 0xFF and not c >> 31 & 1:
            tl = lib.pick(0, (c >> 20) & 0x3F, (c >> 8) & 0x3F, x, y)
            if tl:
                g |= tl.flag_grid()
    for j, w in enumerate(ds.walls()):
        c = int(w[y, x])
        o = int(ds.orientation(j)[y, x])
        if c & 0xFF and not c >> 31 & 1:
            tl = lib.pick(o, (c >> 20) & 0x3F, (c >> 8) & 0x3F, x, y)
            if tl:
                g |= tl.flag_grid()
    return g


def _walk(d, src, fr, opt):
    for y in range(fr.y0, fr.y1 + 1):
        for x in range(fr.x0, fr.x1 + 1):
            g = cell_flags(src, x, y)
            if not g.any():
                continue
            for sy in range(5):
                for sx in range(5):
                    v = int(g[sy, sx])
                    if v & 1:
                        col = (255, 0, 0, 90)
                    elif v & 0x22:
                        col = (40, 80, 255, 80)
                    else:
                        continue
                    ax, ay = x + sx / 5.0, y + sy / 5.0
                    d.polygon([fr.px(ax, ay), fr.px(ax + 0.2, ay), fr.px(ax + 0.2, ay + 0.2), fr.px(ax, ay + 0.2)], fill=col)
