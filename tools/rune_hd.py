"""HD versions of Median's classic rune pictures (lane runehd; owner, 2026-10-30: "just upscale the runes again, try to
make them look more like HD versions of the original without losing the symbol feel too much"; docs/hd-icons.md "Runes").

A Median rune is a ~23 px grey stone in a 28 px cell: a soft dark rim, a speckled stone face with its shading (lighter
left, darker lower right), and a dark sign of 1-3 px strokes. A pixel-art upscaler keeps the staircase and the speckle,
Lanczos smears both (the blurry / blobby look of the plain upscale). Here the picture is taken apart at the classic size,
each layer is scaled the way that suits it and the layers are put back together at the HD size; every colour comes from
the original picture (no new palette):

  silhouette  the convex hull of the opaque pixels (the stone is convex), drawn at the HD size supersampled, its corners
              rounded by EDGE_ROUND: straight anti-aliased sides instead of a staircase
  face        the stone's colour without the sign and the speckle (a normalised Gaussian of the stone pixels inside the
              rim, FACE_R), scaled bicubic, so the original's shading comes back as smooth gradients; the speckle (the
              picture minus that) comes back at GRAIN of its strength, Lanczos-scaled; the rim: a band OUTLINE classic px
              wide in the colour of the original's outer ring
  sign        each pixel's darkness against the stone around it (0 = stone, 0.5 = half as bright), kept on the groups
              of connected dark pixels that hold a clearly dark pixel or form a faint line (SEED / GROW / FAINT_SIZE:
              speckle and the stone's own darker edge are no sign), scaled by threshold decomposition (sign_upscale:
              every darkness level EPX-scaled and cut on its own, then stacked): the original strokes and their tones,
              crisp, a 1 px gap kept open; drawn as that darkness over the stone

METHODS (also upscale.METHODS: an item proposal's `method`, tools/data/item_art_proposals.json):
  rune-flat    the layers as above: clean and flat, the closest to the original
  rune-hd      rune-flat with a light shading pass: the stone's edge bevelled (lit top left, as the original's light),
               a fine grain on the face instead of part of the scaled speckle, and the sign cut in (a shadowed upper-left
               wall, a thin lit lower-right lip)
  rune-crisp   rune-hd with the sign SIGN_GAIN_CRISP times darker, for the faint signs (On, Qor)
Only numpy and Pillow.
"""
import math

import numpy as np
from PIL import Image, ImageDraw

METHODS = ("rune-flat", "rune-hd", "rune-crisp")
SS = 4               # silhouette supersampling
EDGE_ROUND = 0.55    # classic px: Gaussian on the hull mask (rounds the corners)
EDGE_GROW = 0.45     # classic px: the hull of the pixel centres pushed out by this much (to the pixels' outer edges)
FACE_R = 1.2         # classic px: Gaussian of the face colour (the stone's shading kept, the speckle out)
GRAIN = 0.55         # rune-flat: strength of the original speckle (0: a flat face)
FACE_DARK = 0.86     # a face pixel darker than this x the stone around it is left out of the stone estimate
RIM_DARK = 0.65      # the same near the edge (SEED_RIM + 1 px): there only the clearly dark pixels
SEED, GROW = 0.24, 0.09  # sign: a connected group of pixels darker than GROW is part of the sign when one of them is
FAINT_SIZE = 6       # darker than SEED, or (a faint line) when it has FAINT_SIZE pixels, all SEED_RIM + 1 px inside
SEED_RIM = 3         # a seed lies at least this many px inside the silhouette (the rim's shading is no sign)
SIGN_SMOOTH = 0.25   # classic px: Gaussian on each level mask before the cut (rounds the staircase, keeps 1 px gaps)
LEVELS = (0.08, 0.14, 0.20, 0.27, 0.34, 0.42, 0.50)  # darkness levels of the threshold decomposition
STROKE = 0.20        # the level whose contour is the stroke edge (shading)
SIGN_GAIN_CRISP = 1.25  # rune-crisp: the sign this much darker
AA = 0.7             # HD px: half-width of the anti-aliasing ramp of the sign levels and the rim band
BEVEL = 0.14         # rune-hd: brightness change of the lit / shadowed bevel
BEVEL_W = 1.6        # rune-hd: bevel width inside the rim (classic px)
OUTLINE = 0.7        # classic px: width of the dark rim band
LIP = 0.30           # rune-hd: brightness of the sign's lit lower-right lip / shadowed upper-left wall
FINE = 2.5           # rune-hd: fine grain amplitude (0-255 scale)
HD_GRAIN = 0.40      # rune-hd: the scaled speckle's strength (the fine grain carries the rest)


def gauss(a: np.ndarray, r: float) -> np.ndarray:
    """Gaussian blur (sigma r px) of a 2D float array, zero outside."""
    a = a.astype(np.float64)
    if r <= 0:
        return a
    n = max(1, int(3 * r + 0.5))
    x = np.arange(-n, n + 1)
    k = np.exp(-x * x / (2 * r * r))
    k /= k.sum()
    p = np.pad(a, n)
    p = sum(k[i] * p[i:i + a.shape[0]] for i in range(2 * n + 1))
    return sum(k[i] * p[:, i:i + a.shape[1]] for i in range(2 * n + 1))


def smooth_fill(v: np.ndarray, m: np.ndarray, r: float) -> np.ndarray:
    """Normalised Gaussian: v averaged over the pixels of mask m only (sigma r), defined everywhere (far from m: m's
    mean)."""
    w = gauss(m, r)
    out = gauss(v * m, r) / np.maximum(w, 1e-9)
    return np.where(w > 1e-4, out, (v * m).sum() / max(m.sum(), 1))


def resize_f(a: np.ndarray, w: int, h: int, flt=Image.Resampling.BICUBIC) -> np.ndarray:
    """A 2D float field resized to w x h (pixel centres aligned, as PIL)."""
    return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize((w, h), flt)).astype(np.float64)


def erode(m: np.ndarray, n: int, outside: bool = False) -> np.ndarray:
    """m shrunk by n px (4-neighbours); beyond the array counts as `outside`."""
    for _ in range(n):
        p = np.pad(m, 1, constant_values=outside)
        m = m & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m


def dilate(m: np.ndarray, n: int) -> np.ndarray:
    return ~erode(~m, n, outside=True)


def hull(points: np.ndarray) -> list[tuple[float, float]]:
    """Convex hull (monotone chain) of (x, y) points, counter-clockwise."""
    pts = sorted(set(map(tuple, points.tolist())))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def silhouette(op: np.ndarray, sw: int, sh: int) -> tuple[np.ndarray, np.ndarray]:
    """(coverage 0..1, depth) at sw x sh: the convex hull of the opaque pixels' centres pushed out EDGE_GROW classic px,
    corners rounded by EDGE_ROUND (drawn SS x SS supersampled); depth = distance inside its edge in classic px (0
    outside)."""
    h, w = op.shape
    kx, ky = sw / w, sh / h
    ys, xs = np.nonzero(op)
    poly = hull(np.stack([xs, ys], 1))
    W, H = sw * SS, sh * SS
    im = Image.new("L", (W, H), 0)
    if len(poly) >= 3:
        ImageDraw.Draw(im).polygon([((x + 0.5) * kx * SS, (y + 0.5) * ky * SS) for x, y in poly], fill=255)
    b = gauss(np.asarray(im, np.float64) / 255, EDGE_ROUND * kx * SS)
    # a straight edge blurred by sigma r crosses level Phi(-g / r) at g outside the original edge
    level = 0.5 * (1 + math.erf(-EDGE_GROW / EDGE_ROUND / math.sqrt(2)))
    m = b > level
    cov = m.reshape(sh, SS, sw, SS).mean((1, 3))
    edge = m & ~erode(m, 1)
    ey, ex = (np.nonzero(edge)[0] + 0.5) / SS, (np.nonzero(edge)[1] + 0.5) / SS
    cy, cx = (np.mgrid[0:sh, 0:sw] + 0.5).reshape(2, -1)
    d = np.full(cx.shape, np.inf)
    for i in range(0, len(ex), 512):
        d = np.minimum(d, np.hypot(cx[:, None] - ex[None, i:i + 512], cy[:, None] - ey[None, i:i + 512]).min(1))
    depth = np.where(cov.reshape(-1) > 0, d, 0.0).reshape(sh, sw) / kx
    return cov, depth


def epx(m: np.ndarray) -> np.ndarray:
    """Scale2x / EPX of a boolean mask: (h, w) -> (2h, 2w), staircase diagonals become 45 degree edges."""
    p = np.pad(m, 1)
    B, D, F, H = p[:-2, 1:-1], p[1:-1, :-2], p[1:-1, 2:], p[2:, 1:-1]
    core = (B != H) & (D != F)
    out = np.empty((2 * m.shape[0], 2 * m.shape[1]), bool)
    out[0::2, 0::2] = np.where(core & (B == D), D, m)
    out[0::2, 1::2] = np.where(core & (B == F), F, m)
    out[1::2, 0::2] = np.where(core & (D == H), D, m)
    out[1::2, 1::2] = np.where(core & (F == H), F, m)
    return out


def components(m: np.ndarray) -> list[np.ndarray]:
    """The 8-connected components of a boolean mask, each as a mask."""
    seen, out = np.zeros(m.shape, bool), []
    h, w = m.shape
    for y0, x0 in zip(*np.nonzero(m)):
        if seen[y0, x0]:
            continue
        comp, todo = np.zeros(m.shape, bool), [(y0, x0)]
        seen[y0, x0] = comp[y0, x0] = True
        while todo:
            y, x = todo.pop()
            for yy in range(max(0, y - 1), min(h, y + 2)):
                for xx in range(max(0, x - 1), min(w, x + 2)):
                    if m[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = comp[yy, xx] = True
                        todo.append((yy, xx))
        out.append(comp)
    return out


def sign_layers(src: np.ndarray, op: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(darkness, sign mask) at the classic size. darkness: each pixel's darkness relative to the stone around it (a
    normalised Gaussian of the face without its dark pixels; 0 = stone, 0.5 = half as bright), kept on the sign mask
    grown by 1 px (speckle elsewhere is no sign); mask: the groups of connected pixels darker than GROW that hold a
    pixel darker than SEED (SEED_RIM px inside, at least half of the group SEED_RIM + 1 px inside: the rim's
    shading is no sign) or are a faint line of FAINT_SIZE pixels."""
    v = src[..., :3].astype(np.float64).mean(-1)
    inner = erode(op, 1)
    ring = inner & ~erode(op, SEED_RIM + 1)  # near the edge the stone itself darkens (its shading)
    stone = smooth_fill(v, inner, 1.5)
    for _ in range(2):  # leave the dark (sign) pixels out of the stone estimate
        stone = smooth_fill(v, inner & (v > np.where(ring, RIM_DARK, FACE_DARK) * stone), 1.5)
    d = np.where(op, np.clip((stone - v) / np.maximum(stone, 1), 0, 1), 0)
    m = np.zeros(op.shape, bool)
    seedable, core = erode(op, SEED_RIM), erode(op, SEED_RIM + 1)
    for comp in components((d > GROW) & erode(op, 2)):
        cd = d[comp]
        inside = (comp & core).sum() / comp.sum()  # the rim's shading runs along the edge: mostly outside the core
        if (cd.max() > SEED and (comp & seedable).any() and inside >= 0.5) or (comp.sum() >= FAINT_SIZE and inside == 1):
            m |= comp
    region = dilate(m, 1) & op
    return d * region, m


def sign_upscale(dark: np.ndarray, sw: int, sh: int, gain: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """(darkness, stroke coverage) at sw x sh by threshold decomposition: for every level of LEVELS the pixels darker
    than it are EPX-scaled twice (staircases become diagonals), blurred SIGN_SMOOTH and cut with an anti-aliased edge;
    the darkness is the sum of the level steps covered (each level a crisp contour, the original's tones kept, a 1 px
    gap stays open as far as it is open in the original). coverage: the cut of the STROKE level (for the shading)."""
    D = np.zeros((sh, sw))
    sc = np.zeros((sh, sw))
    prev = 0.0
    for t in LEVELS:
        m = dark > t
        if not m.any():
            break
        f = resize_f(gauss(epx(epx(m)), SIGN_SMOOTH * 4), sw, sh)
        gy, gx = np.gradient(f)
        c = np.clip((f - 0.5) / (2 * AA * np.maximum(np.hypot(gx, gy), 0.05)) + 0.5, 0, 1)
        D += (t - prev) * c
        prev = t
        if t == STROKE:
            sc = c
    top = dark.max() if dark.size else 0.0
    if top > prev:  # the darkest pixels above the last level
        f = resize_f(gauss(np.clip(dark - prev, 0, None), SIGN_SMOOTH), sw, sh, Image.Resampling.BILINEAR)
        D += f * (D >= prev - 1e-6)
    return np.clip(D * gain, 0, 0.95), sc


def rune_upscale(src: np.ndarray, sw: int, sh: int, method: str = "rune-hd", seed: int = 0) -> np.ndarray:
    """Median's classic rune picture `src` ((h, w, 4) uint8, alpha 0 / 255) as an HD picture of sw x sh px."""
    if method not in METHODS:
        raise ValueError(f"unknown rune method {method!r}")
    shade = method != "rune-flat"
    crisp = method == "rune-crisp"
    h, w = src.shape[:2]
    k = sw / w  # HD px per classic px
    op = src[..., 3] > 0
    out = np.zeros((sh, sw, 4), np.uint8)
    if not op.any():
        return out
    rgb = src[..., :3].astype(np.float64)
    alpha, depth = silhouette(op, sw, sh)
    dark, sm = sign_layers(src, op)
    big = lambda a, f=Image.Resampling.BICUBIC: np.stack([resize_f(a[..., c], sw, sh, f) for c in range(3)], -1)  # noqa: E731
    # the face: the stone inside the rim, without the sign; the rim: the outer ring's colour
    rim = op & ~erode(op, 1)
    face_m = erode(op, 1) & ~dilate(sm, 1)
    if not face_m.any():
        face_m = op
    low = np.stack([smooth_fill(rgb[..., c], face_m, FACE_R) for c in range(3)], -1)
    speck = np.where(face_m[..., None], rgb - low, 0)
    face = big(low) + (HD_GRAIN if shade else GRAIN) * big(speck, Image.Resampling.LANCZOS)
    rim_col = big(np.stack([smooth_fill(rgb[..., c], rim, 1.5) for c in range(3)], -1))
    D, sc = sign_upscale(dark, sw, sh, SIGN_GAIN_CRISP if crisp else 1.0)
    if shade:
        lit = np.clip(1 - (depth - OUTLINE) / BEVEL_W, 0, 1)  # 1 at the rim's inner edge .. 0 BEVEL_W further in
        deep = resize_f(gauss(op, 1.5), sw, sh)
        gy, gx = np.gradient(deep)
        facing = -(gx + gy) / (np.hypot(gx, gy) + 1e-9) / np.sqrt(2)  # +1: an edge facing the top-left light
        face = face * (1 + BEVEL * facing * lit)[..., None]
        fine = gauss(np.random.default_rng(seed).standard_normal((sh, sw)), 0.55)
        face = face + FINE * (fine / max(fine.std(), 1e-6))[..., None]
        if sc.any():
            s = max(1, round(k * 0.3))
            moved = np.zeros_like(sc)
            moved[s:, s:] = sc[:-s, :-s]  # the sign moved down-right
            lip = np.clip(moved - sc, 0, 1)   # just below / right of a stroke: the lit far wall
            wall = np.clip(sc - moved, 0, 1)  # the stroke's upper-left edge: the wall in shadow
            face = face * (1 + LIP * lip)[..., None]
            D = np.clip(D + LIP * wall * (1 - D), 0, 1)
    col = face * (1 - D[..., None])
    ow = np.clip((OUTLINE - depth) * k / (2 * AA) + 0.5, 0, 1)  # the rim band, OUTLINE classic px wide
    col = col * (1 - ow[..., None]) + rim_col * ow[..., None]
    out[..., :3] = np.clip(np.rint(col), 0, 255)
    out[..., 3] = np.clip(np.rint(alpha * 255), 0, 255)
    out[out[..., 3] < 4] = 0
    return out
