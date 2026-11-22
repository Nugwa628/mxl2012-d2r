"""Viewer part of the sign-off: render each game frame's view in hdkit.view, compare, and lay out one labelled sheet.

  render_all(index, shots_dir, roots, asset, out)   per row of signoff_index.json: a render at the polled dir64, the mode's
                                                    clip at the polled time since the mode began, the game rig, the cut's
                                                    size and feet; then hdkit.view.compare against the game cut and its
                                                    twin (the character's box left out)
  sheet(rows, path, title)                          rows = modes, columns = facing keys; each cell game | viewer | outlines
                                                    (game mask red, render cyan) with IoU, shift, luma and cap numbers

Every render and measure is hdkit.view's own (cli.render_cmd, compare.compare, compare.panel): no second implementation.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ..view import cli, compare as cmp, sheets

CELL = 180          # px per image in the sheet (the 400 x 400 cuts are shown from their centre part)
VIEW = (300, 340)   # the part of each 400 x 400 cut shown: feet at (150, 250) of it


def _args(asset, roots, out, mode, dir64, t, size, feet, rig, glow):
    argv = ["render", asset, "--dir64", str(int(dir64)), "--mode", mode, "--time", "%.4f" % t, "--size",
            "%dx%d" % size, "--origin", "%g,%g" % feet, "--rig", rig, "--ss", "2", "--out", str(out), "--no-gate",
            "--name", "signoff"]
    for r in roots:
        argv += ["--root", r]
    if not glow:
        argv.append("--no-glow")
    return cli.build_parser().parse_args(argv)


def render_all(index, shots_dir, roots, asset, out, rig="game", glow=True, log=print) -> list:
    """index: rows of signoff_index.json; shots_dir holds their PNGs. Returns one result dict per row."""
    from .. import gpugate
    rd = gpugate.wait_free(every=30.0, most=900.0, log=log)     # waits while a slot run or a busy GPU/CPU holds it
    if not rd.free:
        raise SystemExit("GPU gate: %s" % rd.why)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    S, results = None, []
    for row in index:
        shot = np.array(Image.open(Path(shots_dir) / row["shot"]).convert("RGB"))
        twin = np.array(Image.open(Path(shots_dir) / row["twin"]).convert("RGB"))
        size = (shot.shape[1], shot.shape[0])
        feet = tuple(row["feet"])
        d = out / ("k%d_%s" % (row["spawn_key"], row["mode"]))
        # DD is the corpse pose: the clip's last frame (the game holds it); others at the polled time since the mode began
        t = float(row["t_mode"]) if row["mode"] != "dd" else 0.0
        a = _args(asset, roots, d, row["mode"], row["dir64"], t, size, feet, rig, glow)
        if S is None:
            a.no_gate = True
            S = cli.Session(a, log)
        S.a = a
        rep = cli.render_cmd(a, log, S=S)
        png = rep["images"][0]["png"]
        render = np.array(Image.open(png).convert("RGBA"))
        res, extra = cmp.compare(render, shot, feet, feet, twin, None, [tuple(b) for b in row.get("exclude") or [row["player_box"]]], 10)
        panel = cmp.panel(render, extra, res)
        Image.fromarray(panel).save(d / "panel.png")
        res.update(key=row["spawn_key"], attempt=row.get("attempt", 1), twin_cover=row.get("twin_cover", 0.0), mode=row["mode"], dir64=row["dir64"], t_mode=row["t_mode"],
                   game=str(Path(shots_dir) / row["shot"]), twin=str(Path(shots_dir) / row["twin"]), render=png, panel=str(d / "panel.png"),
                   clip=rep.get("clip"), clip_known=rep.get("clip") in (rep.get("clips") or {}))
        (d / "compare.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        results.append(res)
        log("k%d %s dir64 %s t %.2f: IoU %.3f (best %.3f at %s), luma %s/%s, cap dist %s" % (
            row["spawn_key"], row["mode"], row["dir64"], t, res["iou_at_feet"], res["iou_best"], res["shift"],
            res["luma_game"], res["luma_render"], res["cap_distance"]))
    return results


def _view(img, feet):
    """The VIEW-sized part of an image around its feet pixel, as RGB uint8 (RGBA composited over the sheet colour)."""
    a = np.asarray(img)
    if a.shape[-1] == 4:
        a = sheets.over(a)
    w, h = VIEW
    c = cmp.cut(a[..., :3], feet, (w / 2.0, h * 0.735), (w, h))
    return np.array(Image.fromarray(c).resize((CELL, int(CELL * h / w)), Image.LANCZOS))


def sheet(results, path, title, modes, keys) -> Path:
    f, fb = sheets.font(12), sheets.font(15)
    ch = int(CELL * VIEW[1] / VIEW[0])
    cw = 3 * CELL + 8
    txt_h = 46
    left, top = 54, 46
    W = max(left + len(keys) * (cw + 12) + 8, 1100)
    H = top + len(modes) * (ch + txt_h + 14) + 30
    sh = Image.new("RGB", (W, H), sheets.BG)
    d = ImageDraw.Draw(sh)
    d.text((8, 6), title, fill=(255, 255, 255), font=fb)
    d.text((8, 26), "each cell: game | viewer (hdkit.view render over the game's twin shot) | outlines: game mask red, render cyan (best shift)",
           fill=(170, 170, 170), font=f)
    by = {(r["mode"], r["key"]): r for r in results}
    for c, k in enumerate(keys):
        d.text((left + c * (cw + 12), top - 2), "asked facing key %d" % k, fill=(255, 230, 140), font=f)
    for r_i, m in enumerate(modes):
        y = top + 14 + r_i * (ch + txt_h + 14)
        d.text((6, y + ch // 2), m.upper(), fill=(255, 230, 140), font=fb)
        for c, k in enumerate(keys):
            x = left + c * (cw + 12)
            r = by.get((m, k))
            if r is None:
                d.rectangle([x, y, x + cw, y + ch], outline=(90, 40, 40))
                d.text((x + 6, y + ch // 2), "no steady game frame", fill=(255, 120, 120), font=f)
                continue
            feet = tuple(r["shot_feet"])
            game = np.array(Image.open(r["game"]).convert("RGB"))
            rend = np.array(Image.open(r["render"]).convert("RGBA"))
            if r.get("twin"):          # the render over the twin (the same ground without the unit), as the game shows it
                tw = np.array(Image.open(r["twin"]).convert("RGB")).astype(float)
                al = rend[..., 3:4] / 255.0
                rend = np.round(rend[..., :3] * al + tw * (1 - al)).astype(np.uint8)
            pan = np.array(Image.open(r["panel"]).convert("RGB"))
            pw = (pan.shape[1] - 4) // 2
            outl = pan[:, :pw]
            for j, (img, ft) in enumerate(((game, feet), (rend, tuple(r["render_feet"])), (outl, tuple(r["render_feet"])))):
                sh.paste(Image.fromarray(_view(img, ft)), (x + j * (CELL + 4), y))
            lines = ["got key %d dir64 %s  try %d  t %.2f s  IoU %.3f / best %.3f (%d,%d)" % (
                         ((int(r["dir64"]) + 4) >> 3) & 7, r["dir64"], r.get("attempt", 1), r["t_mode"] if m != "dd" else 0.0,
                         r["iou_at_feet"], r["iou_best"], *r["shift"]),
                     "luma game %s  viewer %s  (x%s)" % (r["luma_game"], r["luma_render"], r["luma_ratio"]),
                     "cap game %s  viewer %s  dist %s" % (_c(r["cap_game"]), _c(r["cap_render"]), r["cap_distance"])]
            if r.get("twin_cover", 0) > 0.15:      # the twin's character (shot before it moved) stood on the unit
                lines[0] += "  TWIN %d%% COVERED" % round(100 * r["twin_cover"])
            for li, t in enumerate(lines):
                d.text((x + 2, y + ch + 3 + li * 14), t, fill=(220, 220, 220), font=f)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sh.save(path)
    return path


def _c(v):
    return "-" if not v else "%d,%d,%d" % tuple(int(round(x)) for x in v)
