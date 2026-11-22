"""A render against a game capture: the unit's mask in the shot, silhouette overlap, luminance and cap colour.

The measures of the calibration work (lane hdtools viewer p1 and p4 evidence scripts `compare_p1.py`, `fit_p4.py`), moved
here so that the CLI (`compare`) and the MCP server share one copy:

  twin_mask(shot, twin, feet)   the unit in a shot, from its twin (same camera, no unit): any channel off by more than
                                `thresh`, minus the unit's shadow (ground darker than the twin that keeps the twin's texture:
                                local luma correlation > 0.6), opened, the parts near the feet, closed and filled
  best_shift(a, b, valid)       the shift of mask a (within +-reach px) with the best IoU against b
  luma_median(rgb, m)           Rec. 709 luma median of the sRGB values inside a mask
  cap_colour(rgb, m)            mean colour of the brightest fifth of the upper third of a silhouette (the lit cap, `rim`)
  compare(render, shot, ...)    all of it for one render PNG (RGBA, its feet at `render_feet`) and one shot PNG (its feet at
                                `shot_feet`): the shot is cut to the render's size around the feet

Exclusions (the player, HUD parts) are rectangles in shot pixels. Nothing here is specific to one unit or one game build.
"""
import numpy as np

from . import metrics


def _f(x, n=7):
    from scipy import ndimage
    return ndimage.uniform_filter(x, n)


def twin_mask(shot, twin, feet, valid=None, thresh: float = 28.0, reach: float = 90.0, min_px: int = 60,
              weak: float | None = None, grow: int = 6) -> np.ndarray:
    """weak: hysteresis. Pixels off by more than `weak` (not `thresh`) are kept where they connect to a pixel above
    `thresh`, lie within `grow` px of one, and are not relit ground (the twin's texture kept, brighter or darker: a
    unit's own light or shadow on the ground). Without it, dark body parts on dark ground fall out of the mask, and the
    game's median is biased towards the bright cap (viewer cal2). None: the single threshold of the earlier phases."""
    from scipy import ndimage
    sf, tf = np.asarray(shot, float)[..., :3], np.asarray(twin, float)[..., :3]
    dmax = np.abs(sf - tf).max(-1)
    ls, lt = sf @ metrics.LUMA, tf @ metrics.LUMA
    ms, mt = _f(ls), _f(lt)
    vs, vt = _f(ls * ls) - ms * ms, _f(lt * lt) - mt * mt
    ncc = (_f(ls * lt) - ms * mt) / np.sqrt(np.maximum(vs * vt, 1e-6))
    relit = (ncc > 0.6) & (vt > 12.0)
    diff = (dmax > thresh) & ~((ls < lt) & relit)
    if weak is not None and weak < thresh:
        near = ndimage.binary_dilation(diff, np.ones((2 * grow + 1, 2 * grow + 1)))
        lab, _k = ndimage.label(((dmax > weak) & ~relit & near) | diff)
        hit = np.unique(lab[diff & (lab > 0)])
        diff = np.isin(lab, hit[hit > 0])
    valid = np.ones(diff.shape, bool) if valid is None else np.asarray(valid, bool)
    m = ndimage.binary_opening(diff & valid, np.ones((3, 3)))
    lab, k = ndimage.label(ndimage.binary_closing(m, np.ones((5, 5))))
    keep = np.zeros_like(m)
    yy, xx = np.mgrid[:m.shape[0], :m.shape[1]]
    for i in range(1, k + 1):
        c = lab == i
        if c.sum() >= min_px and np.hypot(xx[c] - feet[0], (yy[c] - (feet[1] - 20)) * 0.7).min() < reach:
            keep |= c
    keep = ndimage.binary_closing(keep, np.ones((7, 7)))
    return ndimage.binary_fill_holes(keep) & valid


def twin_diff(shot, twin):
    """Per pixel: the largest channel difference to the twin, and `relit`: the twin's texture kept (local luma
    correlation > 0.6 on textured ground), i.e. ground that only got lighter or darker. Also both lumas."""
    sf, tf = np.asarray(shot, float)[..., :3], np.asarray(twin, float)[..., :3]
    ls, lt = sf @ metrics.LUMA, tf @ metrics.LUMA
    ms, mt = _f(ls), _f(lt)
    vs, vt = _f(ls * ls) - ms * ms, _f(lt * lt) - mt * mt
    ncc = (_f(ls * lt) - ms * mt) / np.sqrt(np.maximum(vs * vt, 1e-6))
    return np.abs(sf - tf).max(-1), (ncc > 0.6) & (vt > 12.0), ls, lt


def best_shift(a, b, valid=None, reach: int = 10, step: int = 1) -> tuple:
    """(IoU, dx, dy): a rolled by (dx, dy) against b, inside `valid`."""
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    valid = np.ones(a.shape, bool) if valid is None else np.asarray(valid, bool)
    best = (-1.0, 0, 0)
    for dy in range(-reach, reach + 1, step):
        for dx in range(-reach, reach + 1, step):
            v = metrics.iou(np.roll(np.roll(a, dy, 0), dx, 1) & valid, b & valid)
            if v > best[0]:
                best = (v, dx, dy)
    return best


def luma_median(rgb, m) -> float | None:
    m = np.asarray(m, bool)
    return round(float(np.median(np.asarray(rgb)[..., :3][m].astype(float) @ metrics.LUMA)), 2) if m.any() else None


def cap_colour(rgb, m) -> list | None:
    m = np.asarray(m, bool)
    if not m.any():
        return None
    ys = np.nonzero(m.any(1))[0]
    top = m.copy()
    top[ys.min() + (ys.max() - ys.min()) // 3:] = False
    px = np.asarray(rgb)[..., :3][top].astype(float)
    if len(px) == 0:
        return None
    lum = px @ metrics.LUMA
    return [round(float(c), 1) for c in px[lum >= np.percentile(lum, 80)].mean(0)]


def cut(img, feet_src, feet_dst, size) -> np.ndarray:
    """The part of `img` that puts pixel feet_src at feet_dst of a (W, H) image; outside the source is 0."""
    W, H = size
    a = np.asarray(img)
    out = np.zeros((H, W) + a.shape[2:], a.dtype)
    ox, oy = int(round(feet_src[0] - feet_dst[0])), int(round(feet_src[1] - feet_dst[1]))
    x0, y0, x1, y1 = max(ox, 0), max(oy, 0), min(ox + W, a.shape[1]), min(oy + H, a.shape[0])
    if x1 > x0 and y1 > y0:
        out[y0 - oy:y1 - oy, x0 - ox:x1 - ox] = a[y0:y1, x0:x1]
    return out


def compare(render, shot, shot_feet, render_feet=None, twin=None, shot_mask=None, exclude=(), reach: int = 10,
            alpha_cut: int = 128, thresh: float = 28.0, weak: float | None = 10.0) -> dict:
    """render: (H, W, 4) uint8 RGBA; shot, twin: (h, w, 3) uint8 game captures; shot_mask: a (h, w) bool mask of the unit
    in the shot (else made from the twin); exclude: [(x0, y0, x1, y1)] shot pixels left out of every measure."""
    r = np.asarray(render)
    H, W = r.shape[:2]
    rf = render_feet or (W / 2.0, H * 0.75)
    s = cut(np.asarray(shot)[..., :3], shot_feet, rf, (W, H))
    valid_full = np.ones(np.asarray(shot).shape[:2], bool)
    for x0, y0, x1, y1 in exclude or ():
        valid_full[max(0, int(y0)):max(0, int(y1)), max(0, int(x0)):max(0, int(x1))] = False
    valid = cut(valid_full, shot_feet, rf, (W, H))
    if shot_mask is not None:
        gm = cut(np.asarray(shot_mask, bool), shot_feet, rf, (W, H)) & valid
        how = "given"
    elif twin is not None:
        gm = twin_mask(s, cut(np.asarray(twin)[..., :3], shot_feet, rf, (W, H)), rf, valid, thresh)
        how = "twin"
    else:
        raise ValueError("compare: a twin shot or a shot mask is needed for the unit's mask")
    rm = r[..., 3] >= alpha_cut if r.shape[-1] == 4 else np.ones((H, W), bool)
    iou0 = metrics.iou(rm & valid, gm & valid)
    iou, dx, dy = best_shift(rm, gm, valid, reach)
    rm2 = np.roll(np.roll(rm, dy, 0), dx, 1)
    ri2 = np.roll(np.roll(r[..., :3], dy, 0), dx, 1)
    gl, vl = luma_median(s, gm), luma_median(ri2, rm2)
    gc, vc = cap_colour(s, gm), cap_colour(ri2, rm2)
    both = gm & rm2 & valid
    if twin is not None and weak is not None:     # like with like: the render's pixels the game unit covers, dark ones too
        dm, relit, _a, _b = twin_diff(s, cut(np.asarray(twin)[..., :3], shot_feet, rf, (W, H)))
        both = rm2 & valid & (gm | ((dm > weak) & ~relit))
    shared = _shared(s, ri2, both, rm2)
    shared["weak"] = weak if twin is not None else None
    shared["own"] = _own(s, ri2, gm & valid, rm2 & valid)
    if twin is not None and shot_mask is None and r.shape[-1] == 4:
        ra2 = np.roll(np.roll(r, dy, 0), dx, 1)
        shared["fair"] = _fair(s, cut(np.asarray(twin)[..., :3], shot_feet, rf, (W, H)), ra2, gm, rf, valid, thresh)

    def rows(m):
        ys = np.nonzero(m.any(1))[0]
        return [int(ys.min()), int(ys.max())] if len(ys) else None
    return {"mask": how, "size": [W, H], "render_feet": list(rf), "shot_feet": list(shot_feet),
            "iou_at_feet": round(iou0, 4), "iou_best": round(float(iou), 4), "shift": [int(dx), int(dy)], "reach": reach,
            "game_px": int(gm.sum()), "render_px": int(rm.sum()), "game_rows": rows(gm), "render_rows": rows(rm2),
            "luma_game": gl, "luma_render": vl, "luma_ratio": round(vl / gl, 4) if gl and vl else None,
            "cap_game": gc, "cap_render": vc,
            "cap_distance": round(float(np.linalg.norm(np.subtract(gc, vc))), 2) if gc and vc else None,
            "shared": shared,
            "excluded": [list(e) for e in exclude or ()]}, {"shot": s, "game_mask": gm, "render_mask": rm2, "render": ri2}


def _own(shot, render, gm, rm, near: int = 8) -> dict:
    """Alignment-free: each image on its own mask (the game's limited to within `near` px of the render's, which drops
    lit ground blobs far from the unit). Luma p50 / p90 and the ring colour (cap_colour: brightest fifth of the top
    third). Use it where the silhouettes differ (live poses, the live cap ~13 % wider: viewer p4) and pixels do not pair."""
    from scipy import ndimage
    g = gm & ndimage.binary_dilation(rm, np.ones((2 * near + 1, 2 * near + 1)))
    if g.sum() < 8 or rm.sum() < 8:
        return {}
    lg, lr = shot[..., :3][g].astype(float) @ metrics.LUMA, render[..., :3][rm].astype(float) @ metrics.LUMA
    gc, vc = cap_colour(shot, g), cap_colour(render, rm)
    out = {"px": [int(g.sum()), int(rm.sum())]}
    for q in (50, 90):
        a, b = float(np.percentile(lg, q)), float(np.percentile(lr, q))
        out["p%d" % q] = {"game": round(a, 1), "render": round(b, 1), "err": round(abs(float(np.log((b + 1) / (a + 1)))), 3)}
    if gc and vc:
        out["ring"] = {"game": gc, "render": vc, "dist": round(float(np.linalg.norm(np.subtract(gc, vc))), 2)}
    return out


def _fair(shot, twin, render_rgba, gm, feet, valid, thresh) -> dict:
    """Like with like for the mask: the render (at the best shift) laid over the game's twin and cut out by the same
    twin-difference mask as the game unit, so pixels the game mask cannot see (dark body on dark ground, the cap's
    inside against the ring) drop out of both. Luma p50 / p90 and the ring colour on each image's own mask, and the
    IoU of the two masks."""
    a = render_rgba[..., 3:4].astype(float) / 255.0
    comp = render_rgba[..., :3].astype(float) * a + twin.astype(float) * (1.0 - a)
    vm = twin_mask(comp, twin, feet, valid, thresh)
    out = {"px": [int(gm.sum()), int(vm.sum())], "iou": round(float(metrics.iou(vm, gm)), 4)}
    if gm.sum() < 8 or vm.sum() < 8:
        return out
    lg, lr = shot[..., :3][gm].astype(float) @ metrics.LUMA, comp[vm] @ metrics.LUMA
    for q in (50, 90):
        x, y = float(np.percentile(lg, q)), float(np.percentile(lr, q))
        out["p%d" % q] = {"game": round(x, 1), "render": round(y, 1), "ratio": round((y + 1) / (x + 1), 3)}
    gc, vc = cap_colour(shot, gm), cap_colour(comp, vm)
    if gc and vc:
        out["ring"] = {"game": gc, "render": vc, "dist": round(float(np.linalg.norm(np.subtract(gc, vc))), 2)}
    return out


def _shared(shot, render, both, rmask) -> dict:
    """Like with like: measures on the pixels both masks hold (game mask AND render mask at the best shift), split into
    the cap (top third of the render's rows) and the body. err = |log(viewer / game)| of the medians (luma + 1)."""
    out = {"px": int(both.sum())}
    if not both.any():
        return out
    g, v = shot[..., :3].astype(float) @ metrics.LUMA, render[..., :3].astype(float) @ metrics.LUMA
    ys = np.nonzero(rmask.any(1))[0]
    top = np.zeros_like(both)
    top[ys.min():ys.min() + (ys.max() - ys.min()) // 3] = True
    for name, m in (("all", both), ("cap", both & top), ("body", both & ~top)):
        if m.sum() < 8:
            continue
        a, b = float(np.median(g[m])), float(np.median(v[m]))
        out[name] = {"px": int(m.sum()), "game": round(a, 1), "render": round(b, 1),
                     "err": round(abs(float(np.log((b + 1.0) / (a + 1.0)))), 3)}
    for name, m in (("cap_rgb", both & top),):
        if m.sum() >= 8:
            lum = g[m]
            sel = lum >= np.percentile(lum, 80)       # the lit ring: the brightest fifth of the game's cap pixels
            gc, vc = shot[..., :3][m][sel].astype(float).mean(0), render[..., :3][m][sel].astype(float).mean(0)
            out[name] = {"game": [round(float(x), 1) for x in gc], "render": [round(float(x), 1) for x in vc],
                         "dist": round(float(np.linalg.norm(gc - vc)), 2),
                         "blue_game": round(float(gc[2] / max(gc.mean(), 1e-6)), 3),
                         "blue_render": round(float(vc[2] / max(vc.mean(), 1e-6)), 3)}
    return out


def panel(render, extra, result) -> np.ndarray:
    """Shot with the game mask outlined (red) and the shifted render outline (cyan) | the render over the shot."""
    from scipy import ndimage
    s, gm, rm, ri = extra["shot"], extra["game_mask"], extra["render_mask"], extra["render"]
    a = s.copy()
    a[gm & ~ndimage.binary_erosion(gm)] = (255, 60, 60)
    a[rm & ~ndimage.binary_erosion(rm)] = (60, 230, 255)
    al = np.roll(np.roll(np.asarray(render)[..., 3:4], result["shift"][1], 0), result["shift"][0], 1) / 255.0
    b = (ri * al + s * (1 - al)).astype(np.uint8)
    return np.concatenate([a, np.full((s.shape[0], 4, 3), 16, np.uint8), b], 1)
