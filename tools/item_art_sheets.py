"""Review sheets and candidate pictures for the upscaled HD item pictures (lane itemart; tools/item_art_review.py).

A candidate for a picture is, in this order (docs/hd-icons.md "Picture review"):
  reuse    a D2R HD sprite of the same kind of object: a looser silhouette match than item_reuse's (loose_candidates:
           mask IoU of the two tight crops stretched to one box, times an aspect penalty), scaled to the size of Median's
           picture and recoloured to its mean hue / saturation / brightness (colour_match); judged by eye on the sheet
  glyph    (a `reuse` entry with "glyph": "median", lane itemart3) a D2R HD rune stone with its own glyph taken out
           (blank_stone) and Median's glyph cut in instead (glyph_mask, carve): the stone is D2R's, the sign is Median's
  seal     (a `reuse` entry with "seal": "median", lane itemart3 round 2) a round D2R gold disc as a signet: its centre
           enamelled in the colours of Median's centre disc and Median's sign stamped in (seal)
  chisel   (round 3: "glyph": "chisel" / "seal": "chisel" with "sign": <picture key>) as glyph / seal, but the sign is
           Median's redrawn as clean strokes (item_glyphs) and cut in at the output size with crisp V-cut edges
           (engrave_rune, seal with `sign`) instead of the classic pixels scaled up
  method   another upscale setting (upscale.METHODS, or the hybrid with other edge / sharpen values: VARIANTS)
  keep     the current hybrid upscale
Sheet row: Median classic (legacy look: nearest x3.5) | current HD upscale | candidate, all at D2R's HD size (98 px per
cell) on an inventory-like cell grid, the item name and code under the row; written at real pixel size and at 2x
(nearest). At most PER_SHEET rows per sheet (read on a phone). The sheets are game art: keep them out of git.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upscale  # noqa: E402
from colour_shift import shift_pixels  # noqa: E402
from dc6 import decode_frame, palette, read_dc6, read_sprite  # noqa: E402
import item_glyphs  # noqa: E402
from item_art import CELL_CLASSIC, CELL_HD, D2R_ITEMS, MOD_ITEMS, asset_size  # noqa: E402

PER_SHEET = 8
BG, CELL_BG, CELL_LINE, TEXT = (14, 12, 10), (30, 26, 22), (58, 50, 40), (220, 205, 170)
PAD, MIN_COL = 10, 200
MASK = 24
VARIANTS = {  # name -> (base method, upscale module settings)
    "hybrid-crisp": ("hybrid", {"EDGE_LO": 20.0, "EDGE_HI": 60.0, "SHARPEN": 0.8}),
    "hybrid-sharp": ("hybrid", {"SHARPEN": 1.0}),
    "hybrid-smooth": ("hybrid", {"EDGE_LO": 150.0, "EDGE_HI": 250.0, "SHARPEN": 0.3}),  # Scale2x on the outline only
}


# -- pictures -----------------------------------------------------------------------------------------------------
def classic_rgba(key: str, pal: list) -> np.ndarray:
    group, inv = key.split("/", 1)
    w, h, _ox, _oy, block = read_dc6((MOD_ITEMS if group == "mxl" else D2R_ITEMS) / f"{inv}.dc6")[0]
    return upscale.rows_to_array(decode_frame(w, h, block, pal, fill=True))


def nearest(a: np.ndarray, factor: float) -> np.ndarray:
    h, w = a.shape[:2]
    return np.asarray(Image.fromarray(np.ascontiguousarray(a), "RGBA").resize(
        (max(1, round(w * factor)), max(1, round(h * factor))), Image.Resampling.NEAREST))


def upscaled(a: np.ndarray, method: str = upscale.METHOD, cell: int = CELL_HD) -> np.ndarray:
    """`a` at `cell` pixels per cell (HD) with an upscale method or a VARIANTS name (module settings restored afterwards)."""
    f = cell / CELL_CLASSIC
    if method not in VARIANTS:
        return upscale.upscale(a, f, method)
    base, settings = VARIANTS[method]
    old = {k: getattr(upscale, k) for k in settings}
    try:
        for k, v in settings.items():
            setattr(upscale, k, v)
        return upscale.upscale(a, f, base)
    finally:
        for k, v in old.items():
            setattr(upscale, k, v)


def crop(a: np.ndarray) -> np.ndarray:
    nz = a[..., 3] > 0
    if not nz.any():
        return a[:0, :0]
    r, c = np.nonzero(nz.any(1))[0], np.nonzero(nz.any(0))[0]
    return a[r[0]:r[-1] + 1, c[0]:c[-1] + 1]


# -- loose silhouette match -----------------------------------------------------------------------------------------
def mask(a: np.ndarray, n: int = MASK) -> np.ndarray:
    """Opaque mask of the tight crop of RGBA `a`, stretched (nearest) to n x n."""
    c = crop(a)
    if c.size == 0:
        return np.zeros((n, n), bool)
    m = c[..., 3] > 0
    ys = (np.arange(n) * m.shape[0] / n).astype(int)
    xs = (np.arange(n) * m.shape[1] / n).astype(int)
    return m[ys][:, xs]


def silhouette_score(a: np.ndarray, b: np.ndarray) -> float:
    """IoU of the stretched masks times exp(-2 |log aspect ratio|): 1 for the same outline, ~0.5 for a loose one."""
    ca, cb = crop(a), crop(b)
    if ca.size == 0 or cb.size == 0:
        return 0.0
    ma, mb = mask(a), mask(b)
    iou = (ma & mb).sum() / max((ma | mb).sum(), 1)
    asp = abs(math.log((ca.shape[1] / ca.shape[0]) / (cb.shape[1] / cb.shape[0])))
    return float(iou * math.exp(-2 * asp))


def loose_candidates(src: np.ndarray, library: dict[str, np.ndarray], n: int = 4, floor: float = 0.55) -> list[tuple[str, float]]:
    """The n library keys whose picture's silhouette is closest to `src` (score >= floor), best first."""
    scored = [(k, silhouette_score(src, v)) for k, v in library.items()]
    return sorted([s for s in scored if s[1] >= floor], key=lambda s: (-s[1], s[0]))[:n]


# -- colour match -----------------------------------------------------------------------------------------------------
def hsv_stats(a: np.ndarray) -> tuple[float, float, float]:
    """(mean hue in turns weighted by saturation x value, mean saturation, mean value) of the opaque pixels."""
    op = a[..., 3] > 0
    rgb = a[..., :3][op].astype(np.float64) / 255
    if not len(rgb):
        return 0.0, 0.0, 0.0
    mx, mn = rgb.max(1), rgb.min(1)
    d = mx - mn
    dd = np.maximum(d, 1e-9)
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6.0
    s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0.0)
    w = s * mx
    hue = math.atan2((w * np.sin(2 * np.pi * h)).sum(), (w * np.cos(2 * np.pi * h)).sum()) / (2 * np.pi) % 1.0
    return float(hue), float(s.mean()), float(mx.mean())


def colour_match(src: np.ndarray, cand: np.ndarray) -> dict:
    """{"hue", "sat" (factor), "val" (log2)} that brings `cand`'s mean colour to `src`'s (as item_reuse's shift)."""
    hs, ss, vs = hsv_stats(src)
    hc, sc, vc = hsv_stats(cand)
    dh = (hs - hc + 0.5) % 1.0 - 0.5
    return {"hue": round(dh, 3), "sat": round(min(max(ss / max(sc, 1e-6), 0.0), 4.0), 3),
            "val": round(math.log2(max(vs, 1e-6) / max(vc, 1e-6)), 3)}


def _hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rgb = rgb.astype(np.float64) / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    dd = np.maximum(d, 1e-9)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6.0
    return np.where(d == 0, 0.0, h) % 1.0, np.where(mx > 0, d / np.maximum(mx, 1e-9), 0.0), mx


def _rgb(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    out = np.zeros(h.shape + (3,))
    for k, (ra, ga, ba) in enumerate([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]):
        m = i == k
        out[..., 0][m], out[..., 1][m], out[..., 2][m] = ra[m], ga[m], ba[m]
    return np.clip(np.rint(out * 255), 0, 255).astype(np.uint8)


def colour_by_position(hd: np.ndarray, src: np.ndarray) -> np.ndarray:
    """`hd` (a cropped D2R HD picture) with the hue and saturation of Median's picture `src` at the same relative
    position (src's colours smoothed and stretched over hd's box; transparent src pixels take the nearest opaque
    colour), hd's own brightness scaled to src's mean: D2R's form and shading, Median's colours (a gem of many colours)."""
    c = crop(src)
    big = upscale.resize(c, hd.shape[1], hd.shape[0], Image.Resampling.BILINEAR)
    blur = np.asarray(Image.fromarray(np.ascontiguousarray(big), "RGBa").filter(
        ImageFilter.GaussianBlur(max(hd.shape[:2]) / 40))).astype(np.float64)
    al = np.maximum(blur[..., 3:4], 1e-6)
    col = np.clip(blur[..., :3] / al * 255, 0, 255)
    hs, ss, _v = _hsv(col)
    hh, sh, vh = _hsv(hd[..., :3])
    _h0, s0, v0 = hsv_stats(src)
    _h1, s1, v1 = hsv_stats(hd)
    sat = np.clip(np.maximum(ss, sh) * (1.0 if s0 > s1 else s0 / max(s1, 1e-6)), 0, 1)
    val = np.clip(vh * (v0 / max(v1, 1e-6)), 0, 1)
    out = hd.copy()
    out[..., :3] = _rgb(hs, sat, val)
    return out


def render_reuse(hd: np.ndarray, src: np.ndarray, out_w: int, out_h: int, shift: dict | None,
                 by_position: bool = False, cell: int = CELL_HD) -> np.ndarray:
    """D2R HD sprite `hd` cropped, scaled so its area matches Median's picture `src` at `cell` pixels per cell (HD; the
    lowend sprite at 49), recoloured, centred."""
    c, s = crop(hd), crop(src)
    f = cell / CELL_CLASSIC
    k = math.sqrt((s.shape[0] * f * s.shape[1] * f) / max(c.shape[0] * c.shape[1], 1))
    k = min(k, out_w / c.shape[1], out_h / c.shape[0])
    a = upscale.resize(c, max(1, round(c.shape[1] * k)), max(1, round(c.shape[0] * k)))
    if by_position:
        a = colour_by_position(a, src)
    elif shift:
        a = shift_pixels(a, shift["hue"], 0.0, shift["val"], shift["sat"])
    return upscale.place(a, out_w, out_h)


def tint(img: np.ndarray, t: dict) -> np.ndarray:
    """`img` (RGBA) retinted (owner's colour notes, lane itemart3 round 3): the pixels whose hue lies in t["from"]
    (degrees, [lo, hi], may wrap past 360; default all) and whose saturation is over t.get("min_sat", 0) take hue
    t["hue"] and at least saturation t["sat"] (less on the brightest highlights, which stay near white); brightness kept
    (times t.get("val", 1))."""
    h, s, v = _hsv(img[..., :3])
    lo, hi = t.get("from", [0, 360])
    hd = h * 360
    sel = ((hd >= lo) & (hd <= hi)) if lo <= hi else ((hd >= lo) | (hd <= hi))
    sel &= (s >= t.get("min_sat", 0.0)) & (img[..., 3] > 0)
    h2 = np.where(sel, t["hue"] / 360.0, h)
    s2 = np.where(sel, np.maximum(s, t["sat"]) * (1 - 0.55 * v ** 6), s)
    v2 = np.where(sel, np.clip(v * t.get("val", 1.0), 0, 1), v)
    out = img.copy()
    out[..., :3] = _rgb(h2, s2, v2)
    return out


def hd_sprite(hd_items: Path, folder_asset: str) -> np.ndarray:
    return upscale.rows_to_array(read_sprite(Path(hd_items) / f"{folder_asset}.sprite")[0])


# -- rune stones: D2R's stone, Median's glyph (lane itemart3) -------------------------------------------------------
def blur(a: np.ndarray, r: float) -> np.ndarray:
    """Gaussian blur (sigma r) of a 2D float array, edges repeated."""
    n = max(1, int(3 * r + 0.5))
    x = np.arange(-n, n + 1)
    k = np.exp(-x * x / (2 * r * r))
    k /= k.sum()
    p = np.pad(a.astype(np.float64), n, mode="edge")
    p = sum(k[i] * p[i:i + p.shape[0] - 2 * n] for i in range(2 * n + 1))
    return sum(k[i] * p[:, i:i + p.shape[1] - 2 * n] for i in range(2 * n + 1))


def _erode(m: np.ndarray, n: int, outside: bool = False) -> np.ndarray:
    """m shrunk by n pixels (4-neighbours); beyond the array counts as `outside`."""
    for _ in range(n):
        p = np.pad(m, 1, constant_values=outside)
        m = m & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m


def _dilate(m: np.ndarray, n: int) -> np.ndarray:
    return ~_erode(~m, n, outside=True)


def _diffuse(v: np.ndarray, hole: np.ndarray, steps: int = 300) -> np.ndarray:
    """v with the pixels under `hole` replaced by the mean of their neighbours, repeated (a smooth fill)."""
    v = v.copy()
    v[hole] = v[~hole].mean()
    for _ in range(steps):
        p = np.pad(v, 1, mode="edge")
        v[hole] = ((p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) / 4)[hole]
    return v


GLYPH_DARK = 80   # a D2R rune glyph: pixels darker than this inside the stone
GLYPH_EDGE = 0.45  # carve: glyph strength (stretched, blurred) where the groove starts; higher = thinner strokes


def blank_stone(a: np.ndarray) -> np.ndarray:
    """A D2R rune sprite (RGBA) with its glyph taken out: the glyph (dark pixels inside the stone, grown by 2) is filled
    with a smooth fill of the stone around it plus the stone's own fine texture copied from a nearby spot."""
    op = a[..., 3] > 200
    rgb = a[..., :3].astype(np.float64)
    size = max(a.shape[:2])
    inner = _erode(op, max(2, size // 25))
    hole = _dilate((rgb.mean(-1) < GLYPH_DARK) & inner, 2) & op
    if not hole.any():
        return a
    low = np.stack([_diffuse(rgb[..., c], hole) for c in range(3)], -1)
    fine = rgb - np.stack([blur(rgb[..., c], size / 30) for c in range(3)], -1)
    tex, got = np.zeros_like(rgb), np.zeros(hole.shape, bool)
    h, w = hole.shape
    for s in range(max(3, size // 16), size // 2, max(2, size // 40)):
        for dy, dx in ((0, s), (0, -s), (s, 0), (-s, 0), (s, s), (-s, -s), (s, -s), (-s, s)):
            ys, xs = np.nonzero(hole & ~got)
            yy, xx = ys + dy, xs + dx
            ok = (yy >= 0) & (yy < h) & (xx >= 0) & (xx < w)
            ys, xs, yy, xx = ys[ok], xs[ok], yy[ok], xx[ok]
            ok = inner[yy, xx] & ~hole[yy, xx]
            tex[ys[ok], xs[ok]] = fine[yy[ok], xx[ok]]
            got[ys[ok], xs[ok]] = True
    out = a.copy()
    out[..., :3][hole] = np.clip(np.rint(low[hole] + tex[hole]), 0, 255).astype(np.uint8)
    return out


def glyph_mask(src: np.ndarray, rim: int = 3, strong: float = 0.70, weak: float = 0.86) -> np.ndarray:
    """Glyph mask (0 / 1) over the tight crop of Median's rune picture, by hysteresis on the brightness inside the stone
    (`rim` px in): strokes darker than `strong` x the stone's median brightness, grown into the connected pixels darker
    than `weak` x it; the stone's darker rim and shading join only where they touch a stroke."""
    c = crop(src)
    v = c[..., :3].astype(np.float64).mean(-1)
    inner = _erode(c[..., 3] > 0, rim)
    if not inner.any():
        return np.zeros(v.shape)
    stone = float(np.median(v[inner]))
    m, ok = (v < strong * stone) & inner, (v < weak * stone) & inner
    while True:
        grown = _dilate(m, 1) & ok | m
        if (grown == m).all():
            return m.astype(np.float64)
        m = grown

def carve(blank: np.ndarray, g: np.ndarray, depth: float = 0.85) -> np.ndarray:
    """Glyph `g` (glyph_mask) stretched over the stone of `blank` and cut in as D2R draws its glyphs: a dark groove
    with a lighter lower-right lip; smooth edges from a bicubic stretch, a slight blur and a soft threshold."""
    ys, xs = np.nonzero(blank[..., 3] > 0)
    if not len(ys) or not g.size:
        return blank
    y0, x0 = ys.min(), xs.min()
    h, w = ys.max() + 1 - y0, xs.max() + 1 - x0
    big = np.asarray(Image.fromarray(np.rint(g * 255).astype(np.uint8), "L").resize((w, h), Image.Resampling.BICUBIC))
    big = np.clip((blur(big / 255.0, max(w, h) / 40) - GLYPH_EDGE) / 0.12, 0, 1)
    full = np.zeros(blank.shape[:2])
    full[y0:y0 + h, x0:x0 + w] = big
    k = max(1, round(max(w, h) / 60))
    shifted = np.zeros_like(full)
    shifted[k:, k:] = full[:-k, :-k]
    lip = np.clip(shifted - full, 0, 1)
    rgb = blank[..., :3].astype(np.float64) * (1 - depth * full)[..., None] + (60 * lip)[..., None]
    out = blank.copy()
    out[..., :3] = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    return out


def engrave_rune(img: np.ndarray, src: np.ndarray, sign: list) -> np.ndarray:
    """A blank D2R rune stone `img` (RGBA at its output size) with `sign` (item_glyphs strokes over Median's classic
    rune crop) cut in, the crop stretched over the stone's opaque box, crisp at this size."""
    op = img[..., 3] > 0
    ys, xs = np.nonzero(op)
    c = crop(src)
    if not len(ys) or not c.size:
        return img
    y0, x0 = ys.min(), xs.min()
    h, w = ys.max() + 1 - y0, xs.max() + 1 - x0
    ch, cw = c.shape[:2]

    def to_classic(x, y):
        return (x - x0) / w * cw, (y - y0) / h * ch
    out, _cut = item_glyphs.chisel(img[..., :3], sign, to_classic, inside=_erode(op, max(1, max(h, w) // 30)))
    res = img.copy()
    res[..., :3] = np.clip(np.rint(out), 0, 255).astype(np.uint8)
    return res


# -- signets: a D2R gold disc as the seal, Median's enamel and sign (lane itemart3, round 2) ------------------------
SEAL_SRC_R = 0.55   # Median's signet: its coloured centre disc, as a fraction of the picture's radius
SEAL_INNER = 0.5    # the enamel centre on the D2R disc, as a fraction of its radius
SEAL_EDGE = 0.3     # sign strength (stretched, blurred) where the stamp starts; higher = thinner strokes


def _sample(img: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    """Bilinear sample of `img` (2D or HxWxC) at float coordinates sx, sy (clamped)."""
    h, w = img.shape[:2]
    sx, sy = np.clip(sx, 0, w - 1), np.clip(sy, 0, h - 1)
    x0, y0 = np.floor(sx).astype(int), np.floor(sy).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = sx - x0, sy - y0
    if img.ndim == 3:
        fx, fy = fx[..., None], fy[..., None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy) + img[y1, x0] * (1 - fx) * fy
            + img[y1, x1] * fx * fy)


def seal(disc: np.ndarray, src: np.ndarray, strokes: list | None = None) -> np.ndarray:
    """A round D2R picture `disc` (cropped RGBA, the disc filling its box) made into Median's signet `src`: its centre
    (SEAL_INNER of the radius) enamelled with the colours of Median's centre disc (the sign filled out from around it,
    smoothed; D2R's shading kept faintly, a slight dome), and Median's sign (the dark strokes of the centre against their
    surroundings) stamped in as a dark groove with a lighter lower-right lip; with `strokes` (item_glyphs) that
    sign is engraved instead, crisp (item_glyphs.chisel)."""
    h, w = disc.shape[:2]
    c = crop(src)
    if not h or not w or not c.size:
        return disc
    sh, sw = c.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    u, t = (xx - (w - 1) / 2) / (w / 2), (yy - (h - 1) / 2) / (h / 2)
    r = np.hypot(u, t)  # 1 at the rim
    sy, sx = np.mgrid[0:sh, 0:sw]
    centre = (np.hypot((sy - (sh - 1) / 2) / (sh / 2), (sx - (sw - 1) / 2) / (sw / 2)) < SEAL_SRC_R) & (c[..., 3] > 0)
    if not centre.any():
        return disc
    rgb = c[..., :3].astype(np.float64)
    v = rgb.mean(-1)
    ref = blur(v * centre, 2.0) / np.maximum(blur(centre.astype(np.float64), 2.0), 1e-6)
    sign = centre & (v < 0.62 * ref)
    fill = np.stack([_diffuse(rgb[..., i], sign | ~centre, 200) for i in range(3)], -1)
    k = SEAL_SRC_R / SEAL_INNER  # output coordinates -> Median's
    px, py = (u * k + 1) / 2 * (sw - 1), (t * k + 1) / 2 * (sh - 1)
    enamel = np.stack([blur(_sample(fill, px, py)[..., i], max(w, h) / 60) for i in range(3)], -1)
    _h, _s, bv = _hsv(disc[..., :3])
    bvs = blur(bv, max(w, h) / 18)
    inside = r < SEAL_INNER
    shade = (0.85 + 0.15 * bvs / max(float(bvs[inside].mean()) if inside.any() else 1.0, 1e-6)) * (
        1.1 - 0.25 * np.clip(r / SEAL_INNER, 0, 1) ** 2)
    m = np.clip((SEAL_INNER - r) / 0.04, 0, 1)[..., None]
    out = disc[..., :3].astype(np.float64) * (1 - m) + np.clip(enamel * shade[..., None], 0, 255) * m
    if strokes is not None:
        def to_classic(x, y):
            return ((x - w / 2) / (w / 2) * k + 1) / 2 * sw, ((y - h / 2) / (h / 2) * k + 1) / 2 * sh
        out, _cut = item_glyphs.chisel(out, strokes, to_classic, wall=0.5, floor=0.22, inside=r < SEAL_INNER - 0.02)
        res = disc.copy()
        res[..., :3] = np.clip(np.rint(out), 0, 255).astype(np.uint8)
        return res
    g = np.clip((blur(_sample(sign.astype(np.float64), px, py) * inside, max(w, h) / 110) - SEAL_EDGE) / 0.15, 0, 1)
    n = max(1, round(max(w, h) / 70))
    shifted = np.zeros_like(g)
    shifted[n:, n:] = g[:-n, :-n]
    out = out * (1 - 0.85 * g[..., None]) + 50 * np.clip(shifted - g, 0, 1)[..., None]
    res = disc.copy()
    res[..., :3] = np.clip(np.rint(out), 0, 255).astype(np.uint8)
    return res


# -- candidates of one picture -------------------------------------------------------------------------------------
def candidate(prop: dict | None, src: np.ndarray, out_w: int, out_h: int, hd_items: Path,
              cell: int = CELL_HD) -> tuple[np.ndarray, str]:
    """(image, label) of a proposal entry; the current upscale for none / keep. The sheets show it at HD size; the build
    (item_art.convert) makes the HD sprite with the same call and the lowend one at cell 49 from D2R's lowend sprite."""
    if prop and prop.get("reuse"):
        r = prop["reuse"]
        shift = {k: r[k] for k in ("hue", "sat", "val")} if "hue" in r else None
        asset = f"{r['folder']}/{r['asset']}" + (".lowend" if cell != CELL_HD else "")
        hd = hd_sprite(hd_items, asset)
        if r.get("glyph") == "median":
            hd = carve(blank_stone(hd), glyph_mask(src))
        elif r.get("glyph") == "chisel":
            hd = blank_stone(hd)
        img = render_reuse(hd, src, out_w, out_h, shift, r.get("colour") == "by position", cell)
        if r.get("tint"):
            img = tint(img, r["tint"])
        if r.get("glyph") == "chisel":
            img = engrave_rune(img, src, item_glyphs.GLYPHS[r["sign"]])
        if r.get("seal") in ("median", "chisel"):
            ys, xs = np.nonzero(img[..., 3] > 0)
            if len(ys):
                y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
                img = img.copy()
                img[y0:y1, x0:x1] = seal(img[y0:y1, x0:x1], src,
                                         item_glyphs.GLYPHS[r["sign"]] if r.get("seal") == "chisel" else None)
        how = (", Median's glyph" if r.get("glyph") == "median" else ", Median's sign chiselled" if r.get(
            "glyph") == "chisel" else "") + (", a seal with Median's enamel and sign" if r.get("seal") in (
            "median", "chisel") else "") + (", retinted" if r.get("tint") else "") + (
            ", Median's colours" if r.get("colour") == "by position" else ", Median's mean colour" if shift else "")
        return img, f"D2R {r['asset'].split('/')[-1]}{how}"
    if prop and prop.get("method"):
        return upscale.place(upscaled(src, prop["method"], cell), out_w, out_h), prop["method"]
    return upscale.place(upscaled(src, cell=cell), out_w, out_h), "keep (no better)"


# -- sheet drawing --------------------------------------------------------------------------------------------------
def _font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def grid(cw: int, ch: int, cell: int = CELL_HD) -> Image.Image:
    """An inventory-like cw x ch cell field (98 px cells: HD size)."""
    im = Image.new("RGBA", (cw * cell, ch * cell), (*CELL_BG, 255))
    d = ImageDraw.Draw(im)
    for i in range(cw + 1):
        d.line([(i * cell - (i == cw), 0), (i * cell - (i == cw), ch * cell)], (*CELL_LINE, 255))
    for j in range(ch + 1):
        d.line([(0, j * cell - (j == ch)), (cw * cell, j * cell - (j == ch))], (*CELL_LINE, 255))
    return im


def on_grid(img: np.ndarray, cw: int, ch: int) -> Image.Image:
    g = grid(cw, ch, img.shape[0] // ch)
    g.alpha_composite(Image.fromarray(np.ascontiguousarray(img), "RGBA"))
    return g


def wrap(text: str, font, width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """`text` broken into lines no wider than `width` pixels (at spaces)."""
    lines, cur = [], ""
    for word in text.split(" "):
        t = f"{cur} {word}".strip()
        if cur and draw.textlength(t, font=font) > width:
            lines.append(cur)
            cur = word
        else:
            cur = t
    return lines + ([cur] if cur else [])


def draw_sheet(rows: list[dict], title: str) -> Image.Image:
    """rows: {"cells": (cw, ch), "images": [RGBA arrays at cw*cell x ch*cell, cell 98 or smaller], "caption": str,
    "labels": [str per image]}. One column per image, at least MIN_COL wide (labels wrapped above each picture), the
    caption wrapped under the row."""
    col_w = max(MIN_COL, max(r["cells"][0] for r in rows) * CELL_HD)
    width = PAD + max(len(r["images"]) for r in rows) * (col_w + PAD)
    f, fs = _font(15), _font(13)
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lay = []
    for r in rows:
        labels = [wrap(t, fs, col_w, d0) for t in r["labels"]]
        cap = wrap(r["caption"], f, width - 2 * PAD, d0)
        lab_h = 16 * max(len(x) for x in labels) + 4
        lay.append((labels, cap, lab_h, lab_h + r["cells"][1] * CELL_HD + 6 + 19 * len(cap) + PAD))
    head = wrap(title, f, width - 2 * PAD, d0)
    top = 8 + 19 * len(head) + 4
    im = Image.new("RGBA", (width, top + sum(x[3] for x in lay) + PAD), (*BG, 255))
    d = ImageDraw.Draw(im)
    for i, line in enumerate(head):
        d.text((PAD, 8 + 19 * i), line, (*TEXT, 255), font=f)
    y = top
    for r, (labels, cap, lab_h, rh) in zip(rows, lay):
        cw, ch = r["cells"]
        for i, img in enumerate(r["images"]):
            x = PAD + i * (col_w + PAD)
            for j, line in enumerate(labels[i]):
                d.text((x, y + 16 * j), line, (160, 150, 128, 255), font=fs)
            im.alpha_composite(on_grid(img, cw, ch), (x + (col_w - img.shape[1]) // 2, y + lab_h))
        for j, line in enumerate(cap):
            d.text((PAD, y + lab_h + ch * CELL_HD + 6 + 19 * j), line, (*TEXT, 255), font=f)
        y += rh
    return im


def save_pair(im: Image.Image, path: Path) -> list[Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    z = path.with_name(path.stem + "_2x.png")
    im.resize((im.width * 2, im.height * 2), Image.Resampling.NEAREST).save(z)
    return [path, z]


def caption(p) -> str:
    named = []
    for u in p.users:
        s = f"{u['name']} ({u['code']})"
        if s not in named:
            named.append(s)
    more = f" + {len(named) - 2} more" if len(named) > 2 else ""
    return f"{p.key}: " + ", ".join(named[:2]) + more


def write_all(out: Path, plan, order: list, proposals: dict) -> int:
    """Review sheets of `order` ((rank, picture, has a proposal), item_art_review.review_order), PER_SHEET rows each:
    first the pictures with a proposal, then the ones kept as they are (their own sheets)."""
    pal = palette(Path(__file__).resolve().parent.parent / "work" / "d2r-baseline" / "palette" / "pal.dat")
    props = proposals.get("pictures", {})
    groups: dict[bool, list] = {True: [], False: []}
    for n, p, has in order:
        src = classic_rgba(p.key, pal)
        cw, ch = asset_size(src.shape[1], src.shape[0], *plan.needs[(p.folder, *p.key.split("/", 1))])
        W, H = cw * CELL_HD, ch * CELL_HD
        legacy = upscale.place(nearest(src, CELL_HD / CELL_CLASSIC), W, H)
        current = upscale.place(upscaled(src), W, H)
        cand, label = candidate(props.get(p.key), src, W, H, plan.hd_items)
        groups[has].append({"cells": (cw, ch), "images": [legacy, current, cand], "caption": f"#{n} {caption(p)}",
                            "labels": ["Median classic (legacy)", "current HD upscale", f"candidate: {label}"]})
    written, k = [], 0
    for has, what in ((True, "candidates"), (False, "no better picture found (kept)")):
        rows = groups[has]
        for i in range(0, len(rows), PER_SHEET):
            k += 1
            title = f"D2R-XL 2012 item pictures {k}: {what}, real pixel size (98 px per cell)"
            written += save_pair(draw_sheet(rows[i:i + PER_SHEET], title), Path(out) / f"sheet_{k:02}.png")
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "sheets.json").write_text(json.dumps([str(w) for w in written], indent=1), "utf-8")
    for w in written:
        print(w)
    return 0


IN_GAME = CELL_HD // 2   # px per cell of D2R's inventory at 1920 x 1080 (the HD sprite drawn at half size)


def in_game(img: np.ndarray, cw: int, ch: int) -> np.ndarray:
    """The HD picture `img` (cw x ch cells at 98 px) as D2R draws it at 1920 x 1080: IN_GAME px per cell."""
    return upscale.resize(img, cw * IN_GAME, ch * IN_GAME)


def write_lane(out: Path, plan, ranked: list, proposals: dict, lane: str) -> int:
    """Review sheets of one lane's proposals (entries with "lane": lane) in the order of their "pick" (best first),
    PER_SHEET rows each: Median classic (legacy) | current HD upscale | proposal | the proposal at in-game size."""
    pal = palette(Path(__file__).resolve().parent.parent / "work" / "d2r-baseline" / "palette" / "pal.dat")
    rank_of = {p.key: (n, p) for n, p in enumerate(ranked, 1)}
    picks = sorted((v.get("pick", 999), k, v) for k, v in proposals.get("pictures", {}).items()
                   if v.get("lane") == lane and k in rank_of)
    rows = []
    for pick, key, prop in picks:
        n, p = rank_of[key]
        src = classic_rgba(key, pal)
        cw, ch = asset_size(src.shape[1], src.shape[0], *plan.needs[(p.folder, *key.split("/", 1))])
        W, H = cw * CELL_HD, ch * CELL_HD
        cand, label = candidate(prop, src, W, H, plan.hd_items)
        rows.append({"cells": (cw, ch), "caption": f"pick {pick} (rank #{n}) {caption(p)}. {prop.get('why', '')}",
                     "images": [upscale.place(nearest(src, CELL_HD / CELL_CLASSIC), W, H),
                                upscale.place(upscaled(src), W, H), cand, in_game(cand, cw, ch)],
                     "labels": ["Median classic (legacy)", "current HD upscale", f"proposal: {label}",
                                "proposal at 1920x1080 (49 px per cell)"]})
    written = []
    for k, i in enumerate(range(0, len(rows), PER_SHEET), 1):
        title = (f"D2R-XL 2012 item pictures, lane {lane}, sheet {k}: proposals best first (all OFF until approved), "
                 f"real pixel size (98 px per cell)")
        written += save_pair(draw_sheet(rows[i:i + PER_SHEET], title), Path(out) / f"sheet_{k:02}.png")
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "sheets.json").write_text(json.dumps([str(w) for w in written], indent=1), "utf-8")
    for w in written:
        print(w)
    return 0


def _round2(prop: dict) -> dict:
    """The round-2 form of a round-3 proposal: the classic glyph carved (not the redrawn sign), no tint."""
    r = {k: v for k, v in prop["reuse"].items() if k not in ("sign", "tint")}
    for k in ("glyph", "seal"):
        if r.get(k) == "chisel":
            r[k] = "median"
    return {**prop, "reuse": r}


def write_round3(out: Path, plan, ranked: list, proposals: dict) -> int:
    """Lane itemart3 round 3: sheets of the redrawn signs (runes, then signets, by pick) and the retinted pictures,
    PER_SHEET rows each: Median classic | round 2 | round 3 | round 3 at in-game size; and overview_2x.png, every one
    of them as Median classic | round 3 at 2x."""
    pal = palette(Path(__file__).resolve().parent.parent / "work" / "d2r-baseline" / "palette" / "pal.dat")
    rank_of = {p.key: p for p in ranked}
    pics = proposals.get("pictures", {})

    def group(k, v):
        r = v.get("reuse", {})
        return 0 if r.get("glyph") == "chisel" else 1 if r.get("seal") == "chisel" else 2 if r.get("tint") else None
    picks = sorted((group(k, v), v.get("pick", 999), k, v) for k, v in pics.items()
                   if group(k, v) is not None and k in rank_of)
    rows, tiles = [], []
    for g, pick, key, prop in picks:
        p = rank_of[key]
        src = classic_rgba(key, pal)
        cw, ch = asset_size(src.shape[1], src.shape[0], *plan.needs[(p.folder, *key.split("/", 1))])
        W, H = cw * CELL_HD, ch * CELL_HD
        old, _ = candidate(_round2(prop), src, W, H, plan.hd_items)
        new, label = candidate(prop, src, W, H, plan.hd_items)
        classic = upscale.place(nearest(src, CELL_HD / CELL_CLASSIC), W, H)
        what = ("rune" if g == 0 else "signet" if g == 1 else "retint") + (f" {pick}" if g < 2 else "")
        rows.append({"cells": (cw, ch), "caption": f"{what}: {caption(p)}. {'ON' if prop.get('enabled') else 'off'}",
                     "images": [classic, old, new, in_game(new, cw, ch)],
                     "labels": ["Median classic (legacy)", "round 2" + (" (the current picture)" if g == 2 else ""),
                                f"round 3: {label}", "round 3 at 1920x1080 (49 px per cell)"]})
        tiles.append((p, classic, new))
    written = []
    for k, i in enumerate(range(0, len(rows), PER_SHEET), 1):
        title = (f"D2R-XL 2012 item pictures, lane itemart3 round 3, sheet {k}: Median's signs redrawn as clean strokes "
                 f"and chiselled in (runes, signets: off until approved); retints (on); real pixel size (98 px per cell)")
        written += save_pair(draw_sheet(rows[i:i + PER_SHEET], title), Path(out) / f"sheet_{k:02}.png")
    per_row, z = 4, 2
    tw = max(t[1].shape[1] for t in tiles) * z
    th = max(t[1].shape[0] for t in tiles) * z
    f = _font(15)
    cols = per_row * (2 * tw + 3 * PAD)
    im = Image.new("RGBA", (cols + PAD, PAD + -(-len(tiles) // per_row) * (th + 24 + PAD)), (*BG, 255))
    d = ImageDraw.Draw(im)
    for n, (p, classic, new) in enumerate(tiles):
        x, y = PAD + (n % per_row) * (2 * tw + 3 * PAD), PAD + (n // per_row) * (th + 24 + PAD)
        name = sorted({u["name"] for u in p.users})[0] if p.users else p.key
        d.text((x, y), name, (*TEXT, 255), font=f)
        for j, img in enumerate((classic, new)):
            big = Image.fromarray(np.ascontiguousarray(img), "RGBA").resize((img.shape[1] * z, img.shape[0] * z),
                                                                             Image.Resampling.NEAREST)
            im.alpha_composite(big, (x + j * (tw + PAD), y + 22))
    ov = Path(out) / "overview_2x.png"
    im.save(ov)
    written.append(ov)
    (Path(out) / "sheets.json").write_text(json.dumps([str(w) for w in written], indent=1), "utf-8")
    for w in written:
        print(w)
    return 0


# -- lane runehd: Median's runes upscaled again (owner, 2026-10-30) -------------------------------------------------
def round4_rune(key: str) -> dict:
    """The round-4 proposal of a rune (lane itemart3: D2R's blank Ist stone, Median's sign redrawn and chiselled in),
    kept for the comparison sheets."""
    return {"reuse": {"folder": "misc", "asset": "rune/ist_rune", "glyph": "chisel", "sign": key}}


def write_runehd(out: Path, plan, ranked: list, proposals: dict, lane: str = "runehd") -> int:
    """Lane runehd's sheets of the 23 runes (entries with "lane": lane, by "pick"), PER_SHEET rows each: Median classic
    (nearest) | today's shipped HD (the plain upscale) | round 4 (chiselled) | the proposal, at HD size, then the same four
    at in-game size (49 px per cell); methods_NN.png: rune-flat | rune-hd | rune-crisp (the approaches tried); and
    overview_2x.png: every proposal side by side at 2x."""
    import rune_hd
    pal = palette(Path(__file__).resolve().parent.parent / "work" / "d2r-baseline" / "palette" / "pal.dat")
    rank_of = {p.key: p for p in ranked}
    picks = sorted((v.get("pick", 999), k, v) for k, v in proposals.get("pictures", {}).items()
                   if v.get("lane") == lane and k in rank_of)
    rows, alts, tiles = [], [], []
    for pick, key, prop in picks:
        p = rank_of[key]
        src = classic_rgba(key, pal)
        cw, ch = asset_size(src.shape[1], src.shape[0], *plan.needs[(p.folder, *key.split("/", 1))])
        W, H = cw * CELL_HD, ch * CELL_HD
        four = [upscale.place(nearest(src, CELL_HD / CELL_CLASSIC), W, H), upscale.place(upscaled(src), W, H),
                candidate(round4_rune(key), src, W, H, plan.hd_items)[0], candidate(prop, src, W, H, plan.hd_items)[0]]
        name = sorted({u["name"] for u in p.users})[0] if p.users else key
        rows.append({"cells": (cw, ch), "images": four + [in_game(x, cw, ch) for x in four],
                     "caption": f"{pick}. {caption(p)}: {prop.get('method')}. {'ON' if prop.get('enabled') else 'off'}",
                     "labels": ["Median classic (nearest)", "shipped HD (plain upscale)", "round 4 (chiselled)",
                                f"new: {prop.get('method')}", "classic, in game", "shipped, in game", "round 4, in game",
                                "new, in game (1920x1080)"]})
        alts.append({"cells": (cw, ch), "caption": f"{pick}. {caption(p)}",
                     "images": [upscale.place(nearest(src, CELL_HD / CELL_CLASSIC), W, H)]
                     + [upscale.place(upscaled(src, m), W, H) for m in rune_hd.METHODS],
                     "labels": ["Median classic (nearest)"] + [m + (" (picked)" if m == prop.get("method") else "")
                                                               for m in rune_hd.METHODS]})
        tiles.append((name, four[3]))
    written = []
    for k, i in enumerate(range(0, len(rows), PER_SHEET), 1):
        title = (f"D2R-XL 2012 runes, lane {lane}, sheet {k}: Median's own rune pictures upscaled again (off until "
                 f"approved); left four at HD size (98 px per cell), right four at 1920 x 1080 (49 px per cell)")
        written += save_pair(draw_sheet(rows[i:i + PER_SHEET], title), Path(out) / f"sheet_{k:02}.png")
    for k, i in enumerate(range(0, len(alts), PER_SHEET), 1):
        title = f"D2R-XL 2012 runes, lane {lane}, the approaches tried {k}: rune_hd.METHODS at HD size (98 px per cell)"
        written += save_pair(draw_sheet(alts[i:i + PER_SHEET], title), Path(out) / f"methods_{k:02}.png")
    if tiles:
        per_row, z = 6, 2
        tw, th = max(t[1].shape[1] for t in tiles) * z, max(t[1].shape[0] for t in tiles) * z
        f = _font(15)
        im = Image.new("RGBA", (PAD + per_row * (tw + PAD), PAD + -(-len(tiles) // per_row) * (th + 24 + PAD)), (*BG, 255))
        d = ImageDraw.Draw(im)
        for n, (name, img) in enumerate(tiles):
            x, y = PAD + (n % per_row) * (tw + PAD), PAD + (n // per_row) * (th + 24 + PAD)
            d.text((x, y), name, (*TEXT, 255), font=f)
            im.alpha_composite(Image.fromarray(np.ascontiguousarray(img), "RGBA").resize(
                (img.shape[1] * z, img.shape[0] * z), Image.Resampling.NEAREST), (x, y + 22))
        ov = Path(out) / "overview_2x.png"
        im.save(ov)
        written.append(ov)
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "sheets.json").write_text(json.dumps([str(w) for w in written], indent=1), "utf-8")
    for w in written:
        print(w)
    return 0


# -- lane itemart5: Median's own pictures rebuilt crisp (tools/item_rebuild.py) -------------------------------------
def write_rebuild(out: Path, plan, ranked: list, proposals: dict, lane: str = "itemart5") -> int:
    """Lane itemart5's sheets (entries with "lane": lane, by "pick"), PER_SHEET rows each: Median classic (nearest) |
    today's HD (the plain upscale) | the proposal | its `alt` entries (shown, never built), at HD size, then classic, today
    and the proposal at in-game size (49 px per cell); and overview_2x.png, every picture as classic | proposal at 2x."""
    pal = palette(Path(__file__).resolve().parent.parent / "work" / "d2r-baseline" / "palette" / "pal.dat")
    rank_of = {p.key: (n, p) for n, p in enumerate(ranked, 1)}
    picks = sorted((v.get("pick", 999), k, v) for k, v in proposals.get("pictures", {}).items()
                   if v.get("lane") == lane and k in rank_of)
    rows, tiles = [], []
    for pick, key, prop in picks:
        n, p = rank_of[key]
        src = classic_rgba(key, pal)
        cw, ch = asset_size(src.shape[1], src.shape[0], *plan.needs[(p.folder, *key.split("/", 1))])
        W, H = cw * CELL_HD, ch * CELL_HD
        classic, now = upscale.place(nearest(src, CELL_HD / CELL_CLASSIC), W, H), upscale.place(upscaled(src), W, H)
        cand, label = candidate(prop, src, W, H, plan.hd_items)
        alts = [candidate(a, src, W, H, plan.hd_items) for a in prop.get("alt", [])]
        rows.append({"cells": (cw, ch),
                     "caption": f"{pick}. (rank #{n}) {caption(p)}: {label}. {'ON' if prop.get('enabled') else 'off'}. "
                                f"{prop.get('why', '')}",
                     "images": [classic, now, cand] + [a[0] for a in alts] + [in_game(x, cw, ch) for x in (classic, now, cand)],
                     "labels": ["Median classic (nearest)", "HD now (plain upscale)", f"proposal: {label}"]
                     + [f"alternative: {a[1]}" for a in alts]
                     + ["classic, in game", "HD now, in game", "proposal, in game (1920x1080)"]})
        name = sorted({u["name"] for u in p.users})[0] if p.users else key
        tiles.append((name, classic, cand))
    written = []
    for k, i in enumerate(range(0, len(rows), PER_SHEET), 1):
        title = (f"D2R-XL 2012 item pictures, lane {lane}, sheet {k}: Median's own pictures rebuilt crisp (off until "
                 f"approved); HD size (98 px per cell), the last three at 1920 x 1080 (49 px per cell)")
        written += save_pair(draw_sheet(rows[i:i + PER_SHEET], title), Path(out) / f"sheet_{k:02}.png")
    if tiles:
        per_row, z = 4, 2
        tw, th = max(t[1].shape[1] for t in tiles) * z, max(t[1].shape[0] for t in tiles) * z
        f = _font(15)
        im = Image.new("RGBA", (PAD + per_row * (2 * tw + 3 * PAD), PAD + -(-len(tiles) // per_row) * (th + 24 + PAD)),
                       (*BG, 255))
        d = ImageDraw.Draw(im)
        for n, (name, classic, new) in enumerate(tiles):
            x, y = PAD + (n % per_row) * (2 * tw + 3 * PAD), PAD + (n // per_row) * (th + 24 + PAD)
            d.text((x, y), f"{name}: classic | new", (*TEXT, 255), font=f)
            for j, img in enumerate((classic, new)):
                im.alpha_composite(Image.fromarray(np.ascontiguousarray(img), "RGBA").resize(
                    (img.shape[1] * z, img.shape[0] * z), Image.Resampling.NEAREST), (x + j * (tw + PAD), y + 22))
        ov = Path(out) / "overview_2x.png"
        Path(out).mkdir(parents=True, exist_ok=True)
        im.save(ov)
        written.append(ov)
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "sheets.json").write_text(json.dumps([str(w) for w in written], indent=1), "utf-8")
    for w in written:
        print(w)
    return 0
