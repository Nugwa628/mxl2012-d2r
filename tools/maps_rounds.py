#!/usr/bin/env python
"""Round pictures for the map rounds page (lane hdmaps2): one folder per map or crop, the same frame rendered as classic,
the shipped HD and one or more new builds, side by side on http://127.0.0.1:8766/rounds
(`python -m hdkit.view map serve`; tools/hdkit/view/mapview/webmap.py).

  python tools/maps_rounds.py crop ROUND NAME MAP CELLS [--scale 3.6] [--hd LABEL=ROOTS ...] [--note TEXT]
  python tools/maps_rounds.py whole ROUND NAME MAP [--px 3000] [--hd LABEL=ROOTS ...] [--note TEXT]
  python tools/maps_rounds.py auto ROUND MAP [--crops 2] [--size 6] [--px 3000] [--hd ...] [--note TEXT]
      the whole map and its `crops` busiest SIZE x SIZE cell windows (classic walls and floor together, kept apart)
  python tools/maps_rounds.py table ROUND     the crops' measures (metrics.info) as a markdown table

CELLS x0,y0,x1,y1. Scale 3.6 is the 4K game camera (one picture pixel = one screen pixel at 3840x2160).
--hd LABEL[@albedo|@player]=ROOTS: one HD picture from these roots (the viewer's `--root` specs, ';' between them);
@albedo: the unlit colour, for judging the art in dark maps; @player: lit, a player's light at the crop's centre. E.g.
  --hd "shipped@albedo=mod=/d2work/runs/relpkg/x27c/mxl2012/mxl2012.mpq/data;casc"
  --hd "esrgan4x@albedo=out=/d2work/runs/hdmaps2/build/cyp3/data;mod=...;casc"
Without --hd: classic and the default HD.
Writes ROUNDS/ROUND/NAME/<n>_<label>.png (ROUNDS: env MXL_ROUNDS, else /d2work/runs/hdmaps2/rounds) and note.txt.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401


GATE_WAIT = 1800     # seconds an HD picture waits for the GPU gate (hdkit/gpugate.py: game locks, GPU and CPU load)


def crop_metrics(classic_png, hd_png, scale: float) -> dict:
    """How an HD crop at the 4K camera compares with classic's:
    fidelity_de  mean CIELAB distance after shrinking the HD picture back to classic's own pixels (1 / scale), over the
                 pixels both draw: are the colours and the painted light Median's (under ~2: hard to tell apart);
    sharpness    gradient energy of the HD picture over that of classic upscaled with Lanczos to the same size: 1 is a
                 plain upscale, more is finer detail (a 1x atlas through the game's own filtering scores under 1)."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    import maps_audit
    c = Image.open(classic_png).convert("RGBA")
    h = Image.open(hd_png).convert("RGBA")
    W, H = c.size
    w, hh = max(1, int(round(W / scale))), max(1, int(round(H / scale)))
    c1 = np.asarray(c.resize((w, hh), Image.NEAREST)).astype(np.float32) / 255.0      # classic's own pixels
    h1 = np.asarray(h.resize((w, hh), Image.BOX)).astype(np.float32) / 255.0
    both = (c1[..., 3] > 0.5) & (h1[..., 3] > 0.5)
    de = np.linalg.norm(maps_audit._lab(c1[..., :3]) - maps_audit._lab(h1[..., :3]), axis=-1)
    up = np.asarray(c.resize((w, hh), Image.NEAREST).resize((W, H), Image.LANCZOS).convert("L")).astype(np.float32)
    hl = np.asarray(h.convert("L")).astype(np.float32)
    mask = np.asarray(h)[..., 3] > 0
    g = lambda a: float((np.hypot(ndimage.sobel(a, 0), ndimage.sobel(a, 1))[mask] ** 2).mean())   # noqa: E731
    return {"fidelity_de": round(float(de[both].mean()), 2) if both.any() else None,
            "sharpness": round(g(hl) / max(g(up), 1e-6), 3)}


def render_set(round_name, name, key, cells, scale, hds, note="", layers=None, log=print):
    from hdkit.view.mapview import api, hd, webmap
    d = webmap.rounds_root() / round_name / name
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "1_classic.png").is_file():              # a rerun picks up where a stopped one left off
        api.render_classic(key, cells, scale, None, png=str(d / "1_classic.png"))
        log("%s: classic" % name)
    player = None
    if cells:
        x0, y0, x1, y1 = (float(v) for v in cells.split(","))
        player = ((x0 + x1) / 2, (y0 + y1) / 2)
    for i, (label, roots) in enumerate(hds or [("hd", None)], 2):
        how = label.partition("@")[2]
        png = d / ("%d_%s.png" % (i, label.replace("@", "_")))
        if png.is_file():
            continue
        from hdkit import gpugate                       # the shared PC's GPU gate: wait for it, never override it
        t0 = time.time()
        while True:
            rd = gpugate.wait_free(every=30.0, most=max(0.0, GATE_WAIT - (time.time() - t0)), log=log)
            if not rd.free:
                raise SystemExit("maps_rounds: GPU gate still busy after %d s (%s)" % (GATE_WAIT, rd.why))
            try:
                api.render_hd(key, cells, scale, layers, png=str(png), roots=roots, log=log,
                              pass_name="albedo" if how == "albedo" else "lit", player=player if how == "player" else None)
                break
            except RuntimeError as e:                   # a game took the gate between the check and the render
                if "GPU gate" not in str(e):
                    raise
                log("maps_rounds: %s; waiting again" % e)
        hd.release()                                    # one picture's memory at a time (4x crops take ~7 GB)
        log("%s: %s" % (name, label))
    for js in d.glob("*.json"):          # the renders' info files: keep the folder to pictures and the note
        js.rename(js.with_suffix(".info"))
    if cells:                            # measures per HD picture of a crop (crop_metrics)
        import json
        m = {p.stem: crop_metrics(d / "1_classic.png", p, scale) for p in sorted(d.glob("*_albedo.png"))}
        (d / "metrics.info").write_text(json.dumps(m, indent=1), encoding="utf-8")
        if m:
            note = (note + "\n" if note else "") + "  ".join("%s: colour dE %s, sharpness %s" % (
                k.split("_", 1)[1].replace("_albedo", ""), v["fidelity_de"], v["sharpness"]) for k, v in m.items())
    if note:
        (d / "note.txt").write_text(note, encoding="utf-8")
    return d


def busy_windows(key, n=2, size=6, scale=0.25) -> list:
    """The n SIZE x SIZE cell windows of a map with the most classic structure (walls, roofs) and floor, SIZE cells apart:
    ['x0,y0,x1,y1']."""
    import numpy as np
    from scipy import ndimage
    from hdkit.view.mapview import api, classic
    src = api.open_map(key)
    fr = classic.frame_of(src, None, scale)
    def share(layers):
        img, _ = classic.render(src, fr, classic.Options(layers=classic.parse_layers(layers)))
        a = (np.asarray(img.convert("RGBA"))[..., 3] > 0).astype(np.float32)
        return ndimage.uniform_filter(a, (win // 2, win))
    win = max(4, int(size * 160 * scale))                  # a cell is 160 x 80 px at scale 1
    d = share("wall,roof") * share("floor")                # walls with the floor they stand on (not the map's outer wall)
    out, cells = [], []
    for _ in range(n):
        y, x = np.unravel_index(int(np.argmax(d)), d.shape)
        if d[y, x] <= 0:
            break
        cx, cy = fr.cell_at(float(x), float(y))
        cx, cy = int(round(cx)), int(round(cy))
        if all(abs(cx - ox) >= size or abs(cy - oy) >= size for ox, oy in cells):
            cells.append((cx, cy))
            h = size // 2
            out.append("%d,%d,%d,%d" % (max(0, cx - h), max(0, cy - h), cx - h + size, cy - h + size))
        d[max(0, y - win):y + win, max(0, x - win):x + win] = 0
    return out


def table(round_name) -> str:
    """Markdown: one row per crop of the round, colour dE and sharpness per HD picture (metrics.info)."""
    import json
    from hdkit.view.mapview import webmap
    rows, labels = [], []
    for f in sorted((webmap.rounds_root() / round_name).glob("*/metrics.info")):
        m = json.loads(f.read_text(encoding="utf-8"))
        names = [k.split("_", 1)[1].replace("_albedo", "") for k in m]
        labels = labels or names
        if names == labels:
            rows.append((f.parent.name, [m[k] for k in m]))
    if not rows:
        return "(no measured crops)"
    out = ["| crop | " + " | ".join("%s dE / sharpness" % n for n in labels) + " |", "|-" * (len(labels) + 1) + "|"]
    for name, ms in rows:
        out.append("| %s | %s |" % (name, " | ".join("%s / %s" % (v["fidelity_de"], v["sharpness"]) for v in ms)))
    mean = lambda k, i: sum(ms[i][k] for _n, ms in rows) / len(rows)   # noqa: E731
    out.append("| **mean of %d** | %s |" % (len(rows), " | ".join("**%.2f / %.2f**" % (mean("fidelity_de", i), mean(
        "sharpness", i)) for i in range(len(labels)))))
    return "\n".join(out)


def _hd(spec):
    label, _, roots = spec.partition("=")
    return label, [r for r in roots.split(";") if r] or None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crop")
    w = sub.add_parser("whole")
    au = sub.add_parser("auto")
    au.add_argument("round")
    au.add_argument("map")
    au.add_argument("--crops", type=int, default=2)
    au.add_argument("--size", type=int, default=6)
    au.add_argument("--px", type=int, default=3000)
    au.add_argument("--hd", action="append", default=[])
    au.add_argument("--note", default="")
    au.add_argument("--layers", default=None)
    tb = sub.add_parser("table")
    tb.add_argument("round")
    for p in (c, w):
        p.add_argument("round")
        p.add_argument("name")
        p.add_argument("map")
    c.add_argument("cells")
    c.add_argument("--scale", type=float, default=3.6)
    w.add_argument("--px", type=int, default=3000)
    for p in (c, w):
        p.add_argument("--hd", action="append", default=[])
        p.add_argument("--note", default="")
        p.add_argument("--layers", default=None)
    a = ap.parse_args(argv)
    log = lambda s: print(s, file=sys.stderr)   # noqa: E731
    if a.cmd == "table":
        print(table(a.round))
        return 0
    if a.cmd == "auto":
        from hdkit.view.mapview import api, classic
        hds = [_hd(s) for s in a.hd]
        stem = a.map.rsplit("/", 1)[-1]
        fr = classic.frame_of(api.open_map(a.map), None, 1.0)
        print(render_set(a.round, stem + "_0_whole", a.map, None, a.px / max(fr.native_size), hds, a.note, a.layers, log))
        for i, cells in enumerate(busy_windows(a.map, a.crops, a.size), 1):
            print(render_set(a.round, "%s_%d_crop" % (stem, i), a.map, cells, 3.6, hds,
                             (a.note + "\n" if a.note else "") + "cells " + cells + " at the 4K camera", a.layers, log))
        return 0
    cells, scale = (a.cells, a.scale) if a.cmd == "crop" else (None, None)
    if a.cmd == "whole":
        from hdkit.view.mapview import api, classic
        fr = classic.frame_of(api.open_map(a.map), None, 1.0)
        scale = a.px / max(fr.native_size)
    d = render_set(a.round, a.name, a.map, cells, scale, [_hd(s) for s in a.hd], a.note, a.layers,
                   log=lambda s: print(s, file=sys.stderr))
    print(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
