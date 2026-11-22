#!/usr/bin/env python
"""Parity audit of the HD maps against classic (lane hdmaps2): scores per map from the map viewer's pixel-aligned renders.

For each map, at one scale (the whole map, longest side about --px pixels), the viewer (tools/hdkit/view/mapview) draws:
  classic structure (wall, lower, roof), classic full (floor, shadow, wall, lower, roof): the palette art, unlit;
  HD albedo (every layer, unlit colour), HD height (world height of what is drawn, the `height` pass), HD lit (the map's
  own vis file and lights; for the sheets and the light figure)
and the measures are:
  missing      share of classic structure pixels (walls, props, trees, roofs; not the lower walls, flat paint in HD)
               with no standing HD geometry (1 unit or more above the ground) within TOL px: a wall, roof or prop
               classic draws that HD does not
  extra        share of standing HD pixels with no classic structure within TOL px: pieces standing where classic is flat
               (protrusions, wrong walls; height, which classic Median maps do not have, owner ruling 2026-11-12)
  edges        F1 of the edges (Sobel, top 12 % of each picture) of classic full and HD albedo within TOL px
  floor_corr   per floor cell with nothing standing on it in either, the luminance of classic and HD albedo at the cell's
               centre: Pearson correlation (does the HD floor follow classic's pattern of materials: roads, pavements, rugs,
               void); floor_de the median CIE76 difference after both are brought to the same mean luminance
  void         share of floor cells classic shows black that HD shows not black, and the other way
  cast, light  colour cast (chromaticity distance x 100) and mean luminance ratio of HD lit against classic full: for
               information only, not scored (the viewer's classic is drawn at full palette brightness, unlit)
  px/texel 4K  screen pixels per albedo texel at 3840x2160 (median over the drawn area; hd.texel_density): the 4K
               sharpness, not part of the score. About 1 = full detail; a 1x classic atlas is about 3.6 (blocky / blurry)
Score (0-100): 35 (1-missing) + 20 (1-extra) + 20 edges + 25 max(floor_corr, 0).

  python tools/maps_audit.py run [MAP ...] [--out /d2work/runs/hdmaps2/audit/<tag>] [--px 2400] [--root SPEC ...]
  python tools/maps_audit.py report DIR                 ranked table (markdown) of a run
MAP defaults to the 24 maps of AUDIT_MAPS. --root replaces the HD roots (e.g. a new build over the shipped mod).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401

OWN = ["expansion/dystopic/desertpeak", "expansion/ghetto/cypherpunk", "expansion/glados/glados",
       "expansion/neonmile/downtown", "expansion/redsquare/moskvich", "expansion/terror/borgir", "expansion/voodoo/macumba",
       "expansion/zakarum/charismatic", "act3/jungle/dungrm6a", "act3/temple/temple5", "act3/temple/temple6",
       "act1/caves/caveroom4", "act3/kurast/excelsior3", "act2/arcane/belial", "expansion/morework/epicwhiners",
       "act1/cathedrl/inarius", "expansion/icecave/rockisdead"]
EDITED = ["act1/cathedrl/cathy3", "act1/caves/caveroom5", "act1/outdoors/bivouac", "act2/maggot/magqueen",
          "act2/palace/harem2", "act2/tomb/duriel", "act4/diab/heart"]
AUDIT_MAPS = OWN + EDITED
TOL = 3
WEIGHTS = {"missing": 35, "extra": 20, "edges": 20, "floor_corr": 25}
HEIGHT_MIN = 1.0 / 20.0        # the height pass is world y / 20: 1 unit


def _arr(img):
    return np.asarray(img.convert("RGBA")).astype(np.float32) / 255.0


def _over_black(a):
    return a[..., :3] * a[..., 3:4] if a.shape[-1] == 4 else a


def _lum(rgb):
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def _dilate(m, r):
    from scipy import ndimage
    return ndimage.binary_dilation(m, iterations=r) if r > 0 else m


def _edges(lum, mask):
    from scipy import ndimage
    gx, gy = ndimage.sobel(lum, 1), ndimage.sobel(lum, 0)
    g = np.hypot(gx, gy) * mask
    v = g[mask]
    if v.size == 0:
        return np.zeros_like(mask)
    return g > np.percentile(v, 88)


def _lab(rgb):
    def lin(c):
        return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = lin(rgb[..., 0]), lin(rgb[..., 1]), lin(rgb[..., 2])
    X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.9505
    Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.089

    def f(t):
        return np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16 / 116)
    return np.stack([116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))], -1)


def measures(cs, cfull, halb, hheight, hlit, fr, floor_cells) -> dict:
    """The audit measures of one map from its pictures (float RGBA arrays of one frame)."""
    mc = cs[..., 3] > 0.3
    mh = (hheight[..., 3] > 0.3) & (hheight[..., 0] > HEIGHT_MIN)
    missing = float((mc & ~_dilate(mh, TOL)).sum() / max(mc.sum(), 1))
    extra = float((mh & ~_dilate(mc, TOL)).sum() / max(mh.sum(), 1))
    a, b = _over_black(cfull), _over_black(halb)
    both = (cfull[..., 3] > 0.3) & (halb[..., 3] > 0.3)
    ea, eb = _edges(_lum(a), both), _edges(_lum(b), both)
    p = float((eb & _dilate(ea, TOL)).sum() / max(eb.sum(), 1))
    r = float((ea & _dilate(eb, TOL)).sum() / max(ea.sum(), 1))
    f1 = 2 * p * r / max(p + r, 1e-9)
    H, W = a.shape[:2]
    k = max(1, int(round(10 * fr.scale)))
    stand = mc | mh
    vc, vh = [], []
    for (x, y) in floor_cells:
        px, py = fr.px(x + 0.5, y + 0.5)
        px, py = int(px), int(py)
        if k <= px < W - k and k <= py < H - k and not stand[py - k:py + k, px - k:px + k].any():
            vc.append(a[py - k:py + k, px - k:px + k].reshape(-1, 3).mean(0))
            vh.append(b[py - k:py + k, px - k:px + k].reshape(-1, 3).mean(0))
    out = {"missing": round(missing, 4), "extra": round(extra, 4), "edges": round(f1, 4), "edge_precision": round(p, 4),
           "edge_recall": round(r, 4), "struct_px_classic": int(mc.sum()), "standing_px_hd": int(mh.sum())}
    if len(vc) >= 8:
        vc, vh = np.array(vc), np.array(vh)
        lc, lh = _lum(vc), _lum(vh)
        corr = float(np.corrcoef(lc, lh)[0, 1]) if lc.std() > 1e-6 and lh.std() > 1e-6 else 0.0
        sc = max(lc.mean(), 1e-6) / max(lh.mean(), 1e-6)
        de = np.linalg.norm(_lab(np.clip(vc, 0, 1)) - _lab(np.clip(vh * sc, 0, 1)), axis=-1)
        vb_c, vb_h = lc < 0.03, lh < 0.03
        out.update({"floor_cells": len(vc), "floor_corr": round(corr, 4), "floor_de": round(float(np.median(de)), 2),
                    "void_classic_not_hd": round(float((vb_c & ~vb_h).sum() / max(vb_c.sum(), 1)), 4),
                    "void_hd_not_classic": round(float((vb_h & ~vb_c).sum() / max(vb_h.sum(), 1)), 4)})
    else:
        out.update({"floor_cells": len(vc), "floor_corr": 0.0, "floor_de": None})

    def chroma(rgb, m):
        s_ = rgb[m].sum(0)
        t = max(s_.sum(), 1e-6)
        return s_[:2] / t, float(_lum(rgb[m]).mean()) if m.any() else 0.0
    lit = _over_black(hlit)
    (cc, lc0), (ch, lh0) = chroma(a, cfull[..., 3] > 0.3), chroma(lit, hlit[..., 3] > 0.3)
    out["cast"] = round(float(np.linalg.norm(cc - ch) * 100), 3)
    out["light"] = round(lh0 / max(lc0, 1e-6), 3)
    s_ = (WEIGHTS["missing"] * (1 - missing) + WEIGHTS["extra"] * (1 - extra) + WEIGHTS["edges"] * f1
          + WEIGHTS["floor_corr"] * max(out["floor_corr"], 0.0))
    out["score"] = round(float(s_), 1)
    return out


def audit_map(key: str, out: Path, px: int = 2400, roots=None, log=print) -> dict:
    from hdkit.view.mapview import api, classic, hd, ground
    src = api.open_map(key)
    probe = classic.frame_of(src, None, 1.0)
    W0, H0 = probe.native_size
    scale = min(0.5, px / max(W0, H0))
    fr = classic.frame_of(src, None, scale)
    d = out / key.replace("/", "_")
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    pics = {}

    def cl(name, layers):
        opt = classic.Options(layers=classic.parse_layers(layers))
        img, _ = classic.render(src, fr, opt)
        img.save(d / ("%s.png" % name))
        pics[name] = _arr(img)

    def hdr(name, layers, pass_name="lit"):
        img, info = hd.render(src, fr, hd.parse_layers(layers), None, roots, None, None, None, "vis", 1, True, None,
                              pass_name=pass_name)
        img.save(d / ("%s.png" % name))
        pics[name] = _arr(img)
        return info
    full = "terrain,decals,walls,props,prefabs,lights,fx,units"
    cl("classic_struct", "wall,roof")          # lower walls are flat paint in HD: judged by edges, not height
    cl("classic_full", "floor,shadow,wall,lower,roof")
    art = "terrain,decals,walls,props,prefabs"     # the map's art only: effects and units would count as floor colour
    hdr("hd_albedo", art, "albedo")
    hdr("hd_height", art, "height")
    info = hdr("hd_full", full)
    fc = ground.floor_cells(src.ds)
    cells = [(x, y) for y in range(fc.shape[0]) for x in range(fc.shape[1]) if fc[y, x]]
    m = measures(pics["classic_struct"], pics["classic_full"], pics["hd_albedo"], pics["hd_height"], pics["hd_full"], fr,
                 cells)
    m["texel_density"] = info.get("texel_density")
    m.update({"map": key, "scale": round(scale, 4), "size": list(fr.size), "preset": info.get("preset"),
              "roots": info.get("roots"), "seconds": round(time.time() - t0, 1)})
    (d / "audit.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    _sheet(d, pics)
    log("%s: score %.1f (%.0f s)" % (key, m["score"], m["seconds"]))
    return m


def _sheet(d: Path, pics):
    """classic full | HD full side by side, at most 4096 px wide."""
    from PIL import Image
    a = (np.clip(_over_black(pics["classic_full"]), 0, 1) * 255).astype(np.uint8)
    b = (np.clip(_over_black(pics["hd_full"]), 0, 1) * 255).astype(np.uint8)
    img = Image.fromarray(np.concatenate([a, b], 1), "RGB")
    if img.width > 4096:
        img = img.resize((4096, int(img.height * 4096 / img.width)), Image.LANCZOS)
    img.save(d / "sheet.jpg", quality=88)


def report(run: Path) -> str:
    rows = []
    for f in sorted(run.glob("*/audit.json")):
        rows.append(json.loads(f.read_text(encoding="utf-8")))
    rows.sort(key=lambda r: r["score"])
    md = ["| rank | map | score | missing | extra | edges F1 | floor corr | floor dE | void c/h | px/texel 4K | cast* | light* |",
          "|-|-|-|-|-|-|-|-|-|-|-|-|"]
    for i, r in enumerate(rows, 1):
        td = r.get("texel_density") or {}
        md.append("| %d | %s | %.1f | %.0f%% | %.0f%% | %.2f | %.2f | %s | %s / %s | %s | %.2f | %.2f |" % (
            i, r["map"].split("/")[-1], r["score"], 100 * r["missing"], 100 * r["extra"], r["edges"], r["floor_corr"],
            r.get("floor_de"), r.get("void_classic_not_hd", "-"), r.get("void_hd_not_classic", "-"),
            td.get("px_per_texel_4k_median", "-"), r["cast"], r["light"]))
    return "\n".join(md)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("maps", nargs="*")
    r.add_argument("--out", default="/d2work/runs/hdmaps2/audit/current")
    r.add_argument("--px", type=int, default=2400)
    r.add_argument("--root", action="append", default=[])
    r.add_argument("--gb", type=float, default=9.0, help="memory limit per map process (several maps: one process each)")
    r.add_argument("--one", action="store_true", help="audit the maps in this process, no report (the per-map child)")
    p = sub.add_parser("report")
    p.add_argument("dir")
    a = ap.parse_args(argv)
    if a.cmd == "report":
        print(report(Path(a.dir)))
        return 0
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MAPVIEW_OUT", str(out / "_mapview"))
    keys = a.maps or AUDIT_MAPS
    if len(keys) > 1 and not a.one:
        # one process per map under memwatch: the GPU and texture memory of a map goes back when its process ends, and a
        # map that grows past --gb is stopped and reported instead of the kernel's OOM killer taking the run down
        import subprocess
        here = Path(__file__).resolve().parent
        for key in keys:
            cmd = [sys.executable, str(here / "memwatch.py"), "--gb", str(a.gb), "--", sys.executable,
                   str(Path(__file__).resolve()), "run", key, "--one", "--out", str(out), "--px", str(a.px)]
            cmd += sum((["--root", r] for r in a.root), [])
            rc = subprocess.call(cmd)
            if rc:
                err = out / (key.replace("/", "_") + ".error.txt")
                if not err.exists():
                    err.write_text("process exit %d (137: stopped by memwatch at %s GB)\n" % (rc, a.gb), encoding="utf-8")
    else:
        for key in keys:
            try:
                audit_map(key, out, a.px, a.root or None)
            except Exception as e:  # noqa: BLE001 (one map failing is reported, the others go on)
                print("%s: FAILED %r" % (key, e), file=sys.stderr)
                import traceback
                (out / (key.replace("/", "_") + ".error.txt")).write_text(traceback.format_exc(), encoding="utf-8")
        if a.one:
            return 0
    (out / "REPORT.md").write_text(report(out) + "\n", encoding="utf-8")
    print(report(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
