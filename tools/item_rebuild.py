"""Clean HD rebuilds of Median's own classic item pictures (lane itemart5; docs/hd-icons.md "Rebuilt pictures").

For the pictures with no D2R HD item of the same kind (the arcane crystals, the catalysts, the shrine cross, the apple,
...). Owner rules (2026-10-30): no new 3D models and no new drawing; a picture is either D2R's HD art reused or "an HD
version of the original" (as lane runehd's tools/rune_hd.py for the runes): crisp, true to the original, its colours
kept. rune_hd is made for a convex stone with a cut-in sign; this is the same idea for any picture:

  silhouette  the opaque pixels as a mask, EPX-scaled twice (staircases become 45 degree edges), lightly blurred and cut
              with an anti-aliased edge at the HD size: clean outlines, thin parts (a stem, a cross arm) kept
  tones       threshold decomposition of the brightness: every brightness step of the original (the midpoints between
              its distinct tones) is a mask, scaled like the silhouette and cut on its own, and the steps are stacked:
              every contour is crisp and every tone of the original stays (a highlight stays a highlight, an outline an
              outline); then an edge-preserving (bilateral) smoothing evens out the small steps of soft shading while
              the large steps (outlines, highlights) stay sharp
  colour      joint bilateral upsampling: each HD pixel takes the colour of the classic pixels around it whose brightness
              is close to its own (so a red cherry does not bleed into its green stem), set to the rebuilt brightness

METHODS (also upscale.METHODS: an item proposal's `method`, tools/data/item_art_proposals.json):
  item-hd     as above
  item-soft   item-hd with the original's low-contrast speckle (dither) evened out first (a pixel within SPECK of the
              median of its opaque neighbours takes that median): smooth surfaces (the orbs) come out clean, the edges,
              outlines and highlights stay
Only numpy and Pillow; the helpers are rune_hd's.
"""
import warnings

import numpy as np
from PIL import Image

from rune_hd import epx, gauss, resize_f, smooth_fill

METHODS = ("item-hd", "item-soft")
SIL_SMOOTH = 0.45    # classic px: Gaussian on the EPX-scaled silhouette before the cut (rounds the outline)
TONE_SMOOTH = 0.30   # classic px: the same for the tone masks
AA = 0.7             # HD px: half-width of the anti-aliasing ramp of every cut
MERGE = 2.0          # brightness (0-255): tones closer than this are one step
BIL_R = 0.45         # classic px: spatial sigma of the bilateral smoothing of the rebuilt brightness
BIL_RANGE = 12.0     # brightness: its range sigma (steps far above this stay sharp)
JBU_S = 0.65         # classic px: spatial sigma of the colour upsampling
JBU_RANGE = 22.0     # brightness: its range sigma
SPECK = 14.0         # item-soft: speckle threshold (brightness)


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def cut(m: np.ndarray, sw: int, sh: int, r: float = TONE_SMOOTH) -> np.ndarray:
    """A classic-size boolean mask at sw x sh: EPX twice, blurred r classic px, cut at 0.5 with an AA px ramp (0..1)."""
    f = resize_f(gauss(epx(epx(m)), r * 4), sw, sh)
    gy, gx = np.gradient(f)
    return np.clip((f - 0.5) / (2 * AA * np.maximum(np.hypot(gx, gy), 0.05)) + 0.5, 0, 1)


def despeckle(y: np.ndarray, op: np.ndarray, t: float = SPECK) -> np.ndarray:
    """y with every opaque pixel within t of the median of its opaque 8-neighbours set to that median."""
    h, w = y.shape
    p, q = np.pad(np.where(op, y, np.nan), 1, constant_values=np.nan), np.pad(op, 1)
    stack = np.stack([p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
    has = np.stack([q[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]).sum(0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an all-transparent neighbourhood: nan, not used
        med = np.nanmedian(stack, 0)
    ok = op & (has >= 5) & (np.abs(y - med) < t)
    return np.where(ok, med, y)


def tones(y: np.ndarray, op: np.ndarray, sw: int, sh: int) -> np.ndarray:
    """The brightness y (classic size) at sw x sh by threshold decomposition over its distinct tones on op."""
    ext = np.where(op, y, smooth_fill(y, op, 1.0))  # outside the picture: the nearby tones (the silhouette cuts it)
    vals = np.unique(np.round(y[op]))
    steps = [vals[0]]
    for v in vals[1:]:
        if v - steps[-1] >= MERGE:
            steps.append(v)
    out = np.full((sh, sw), float(steps[0]))
    for a, b in zip(steps, steps[1:]):
        m = ext > (a + b) / 2
        if m.any():
            out += (b - a) * cut(m, sw, sh)
    return out


def bilateral(img: np.ndarray, r: float, rng: float) -> np.ndarray:
    """Edge-preserving smoothing of a 2D field (spatial sigma r px, range sigma rng), edges repeated."""
    n = max(1, int(2.5 * r + 0.5))
    p = np.pad(img, n, mode="edge")
    h, w = img.shape
    acc, wsum = np.zeros_like(img), np.zeros_like(img)
    for dy in range(-n, n + 1):
        for dx in range(-n, n + 1):
            s = p[n + dy:n + dy + h, n + dx:n + dx + w]
            wt = np.exp(-(dx * dx + dy * dy) / (2 * r * r) - (s - img) ** 2 / (2 * rng * rng))
            acc += wt * s
            wsum += wt
    return acc / wsum


def colour(rgb: np.ndarray, y: np.ndarray, op: np.ndarray, Y: np.ndarray, sw: int, sh: int) -> np.ndarray:
    """Joint bilateral upsampling: the colour at each HD pixel from the opaque classic pixels within 2 px, weighted by
    distance (JBU_S) and by how close their brightness y is to the HD brightness Y (JBU_RANGE)."""
    h, w = y.shape
    kx, ky = sw / w, sh / h
    cx = (np.arange(sw) + 0.5) / kx - 0.5
    cy = (np.arange(sh) + 0.5) / ky - 0.5
    X, Yc = np.meshgrid(cx, cy)
    x0, y0 = np.floor(X).astype(int), np.floor(Yc).astype(int)
    acc, wsum = np.zeros((sh, sw, 3)), np.zeros((sh, sw))
    for dy in range(-1, 3):
        for dx in range(-1, 3):
            xi, yi = x0 + dx, y0 + dy
            ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
            xc, yc = np.clip(xi, 0, w - 1), np.clip(yi, 0, h - 1)
            o = op[yc, xc] & ok
            d2 = (X - xi) ** 2 + (Yc - yi) ** 2
            wt = o * np.exp(-d2 / (2 * JBU_S ** 2) - (y[yc, xc] - Y) ** 2 / (2 * JBU_RANGE ** 2))
            acc += wt[..., None] * rgb[yc, xc]
            wsum += wt
    # where no opaque neighbour is close in brightness: the plain nearby colour
    fb = np.stack([resize_f(smooth_fill(rgb[..., c], op, 0.8), sw, sh) for c in range(3)], -1)
    wn = (wsum / (wsum + 1e-3))[..., None]
    col = np.where(wsum[..., None] > 0, acc / np.maximum(wsum, 1e-12)[..., None], fb)
    col = wn * col + (1 - wn) * fb
    return col


def rebuild(src: np.ndarray, sw: int, sh: int, method: str = "item-hd") -> np.ndarray:
    """Median's classic picture `src` ((h, w, 4) uint8, alpha 0 / 255) as a clean HD picture of sw x sh px."""
    if method not in METHODS:
        raise ValueError(f"unknown rebuild method {method!r}")
    op = src[..., 3] > 0
    out = np.zeros((sh, sw, 4), np.uint8)
    if not op.any():
        return out
    rgb = src[..., :3].astype(np.float64)
    y = luma(rgb)
    if method == "item-soft":
        y2 = despeckle(y, op)
        rgb = rgb + (y2 - y)[..., None]
        y = y2
    alpha = cut(op, sw, sh, SIL_SMOOTH)
    k = sw / src.shape[1]
    Y = bilateral(tones(y, op, sw, sh), BIL_R * k, BIL_RANGE)
    col = colour(rgb, y, op, Y, sw, sh)
    col = col + (Y - luma(col))[..., None]
    out[..., :3] = np.clip(np.rint(col), 0, 255)
    out[..., 3] = np.clip(np.rint(alpha * 255), 0, 255)
    out[out[..., 3] < 4] = 0
    return out
