#!/usr/bin/env python
"""The map viewer against the game: a 3840x2160 in-game capture and the viewer's HD render of the same spot, aligned and
put side by side (lane hdmaps2, viewer calibration; docs/mapview.md "Calibration").

At 3840x2160 the game's camera draws k = K_1600x900 x 2.4 px per world unit; the viewer's HD render at classic scale 3.6
draws the same (k = 16.97 x scale x 2/3). The viewer renders the cells round the spot, both pictures' edge maps (the HUD and
the debug overlay masked out) are matched by FFT cross-correlation at 1/8 size and refined at 1/2, and the render is cut
to the capture's frame.

  python tools/maps_calib.py pair CAPTURE.png MAP CX,CY OUT_PREFIX [--layers ...] [--rig vis] [--reach 9] [--root SPEC]
      [--set hd.VIS_LIGHT_GAIN=0.4 --set ground.LAYER_REPEAT=20 ...]     module constants for a trial
writes OUT_PREFIX_pair.jpg (capture | viewer, half size), OUT_PREFIX_viewer.png (aligned crop) and OUT_PREFIX.json
(offset, match score, mean luminance of both over the shared world area, per 3x3 region).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401

SCALE_4K = 3.6
HUD_TOP, HUD_BOTTOM = 0.035, 0.80      # capture rows outside [top, bottom) x height are UI


def _grad(lum):
    from scipy import ndimage
    return np.hypot(ndimage.sobel(lum, 0), ndimage.sobel(lum, 1))


def _lum(a):
    a = a.astype(np.float32) / 255.0
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def align(cap: np.ndarray, ren: np.ndarray, coarse: int = 8, guess=None, window: int = 240):
    """(dx, dy) such that render[dy + y, dx + x] ~ capture[y, x]; match score. `guess`: the expected (dx, dy) (the player
    centred on the screen); the search then stays within `window` px of it."""
    from PIL import Image
    from scipy.signal import fftconvolve
    H, W = cap.shape[:2]
    m = np.zeros((H, W), np.float32)
    m[int(HUD_TOP * H):int(HUD_BOTTOM * H)] = 1

    def small(a, f, mask=None):
        img = Image.fromarray(a).resize((max(1, a.shape[1] // f), max(1, a.shape[0] // f)), Image.BOX)
        g = _grad(_lum(np.asarray(img)[..., :3]))
        if mask is not None:
            mk = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).resize(g.shape[::-1], Image.BOX)) > 250
            g = g * mk
        g = g - g.mean()
        return g / (g.std() + 1e-6)
    c, r = small(cap, coarse, m), small(ren, coarse)
    cor = fftconvolve(r, c[::-1, ::-1], mode="valid")
    if guess is not None:
        yy, xx = np.mgrid[0:cor.shape[0], 0:cor.shape[1]]
        far = (np.abs(xx * coarse - guess[0]) > window) | (np.abs(yy * coarse - guess[1]) > window)
        cor = np.where(far, -np.inf, cor)
    iy, ix = np.unravel_index(np.argmax(cor), cor.shape)
    dx, dy = ix * coarse, iy * coarse
    f = 2
    pad = coarse * 2
    y0, x0 = max(0, dy - pad), max(0, dx - pad)
    sub = ren[y0:min(ren.shape[0], dy + H + pad), x0:min(ren.shape[1], dx + W + pad)]
    c2, r2 = small(cap, f, m), small(sub, f)
    if r2.shape[0] >= c2.shape[0] and r2.shape[1] >= c2.shape[1]:
        cor2 = fftconvolve(r2, c2[::-1, ::-1], mode="valid")
        jy, jx = np.unravel_index(np.argmax(cor2), cor2.shape)
        dx, dy = x0 + jx * f, y0 + jy * f
        score = float(cor2.max() / c2.size)
    else:
        score = float(cor.max() / c.size)
    return int(dx), int(dy), score


def pair(capture, key, cx, cy, prefix, layers=None, rig="vis", reach=9, roots=None, log=print):
    from PIL import Image
    from hdkit.view.mapview import api, classic, hd
    src = api.open_map(key)
    cells = "%d,%d,%d,%d" % (int(cx) - reach, int(cy) - reach, int(cx) + reach, int(cy) + reach)
    fr = classic.frame_of(src, cells, SCALE_4K)
    img, info = hd.render(src, fr, hd.parse_layers(layers), None, roots, None, None, None, rig, 1, True, log,
                          player=(cx, cy))
    cap = np.asarray(Image.open(capture).convert("RGB"))
    ren = np.asarray(img.convert("RGBA"))
    rgb = (ren[..., :3].astype(np.float32) * (ren[..., 3:4] / 255.0)).astype(np.uint8)
    H, W = cap.shape[:2]
    if rgb.shape[0] < H or rgb.shape[1] < W:
        raise SystemExit("render %s smaller than the capture %s: raise --reach" % (rgb.shape, cap.shape))
    gx, gy = fr.px(cx, cy)
    dx, dy, score = align(cap, rgb, guess=(gx - W / 2.0, gy - H / 2.0))
    res_guess = [round(gx - W / 2.0, 1), round(gy - H / 2.0, 1)]
    crop = rgb[dy:dy + H, dx:dx + W]
    out = Path(prefix)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(crop).save(str(out) + "_viewer.png")
    both = Image.fromarray(np.concatenate([cap, crop], 1)).resize((W, H // 2), Image.LANCZOS)
    both.save(str(out) + "_pair.jpg", quality=90)
    lc, lr = _lum(cap), _lum(crop)
    t, b = int(HUD_TOP * H), int(HUD_BOTTOM * H)
    reg = []
    for i in range(3):
        for j in range(3):
            ys = slice(t + (b - t) * i // 3, t + (b - t) * (i + 1) // 3)
            xs = slice(W * j // 3, W * (j + 1) // 3)
            reg.append([round(float(lc[ys, xs].mean()), 4), round(float(lr[ys, xs].mean()), 4)])
    res = {"capture": str(capture), "map": key, "spot": [cx, cy], "offset": [dx, dy], "centred_offset": res_guess,
           "match": round(score, 4),
           "mean_lum_capture": round(float(lc[t:b].mean()), 4), "mean_lum_viewer": round(float(lr[t:b].mean()), 4),
           "regions_capture_viewer": reg, "viewer": {k: info.get(k) for k in ("ground", "lights", "vis", "units", "decals")}}
    Path(str(out) + ".json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


def _set(spec):
    import importlib
    mod, _, rest = spec.partition(".")
    name, _, val = rest.partition("=")
    m = importlib.import_module({"hd": "hdkit.view.mapview.hd", "ground": "hdkit.view.mapview.ground",
                                 "units": "hdkit.view.mapview.units", "gpu": "hdkit.view.gpu"}[mod])
    old = getattr(m, name)
    setattr(m, name, type(old)(val) if not isinstance(old, tuple) else tuple(float(v) for v in val.split(",")))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pair")
    p.add_argument("capture")
    p.add_argument("map")
    p.add_argument("spot")
    p.add_argument("prefix")
    p.add_argument("--layers", default=None)
    p.add_argument("--rig", default="vis")
    p.add_argument("--reach", type=int, default=9)
    p.add_argument("--root", action="append", default=[])
    p.add_argument("--set", action="append", default=[])
    a = ap.parse_args(argv)
    for s in a.set:
        _set(s)
    cx, cy = (float(v) for v in a.spot.split(","))
    print(json.dumps(pair(a.capture, a.map, cx, cy, a.prefix, a.layers, a.rig, a.reach, a.root or None,
                          log=lambda s: print(s, file=sys.stderr)), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
