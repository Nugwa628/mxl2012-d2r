"""Pixel-art upscaling for the HD inventory pictures and skill icon sheets (docs/hd-icons.md "Picture quality").

A classic item picture is 28 px per inventory cell, D2R's HD one 98 (lowend 49): a factor of 3.5 (1.75). Bilinear
scaling (dc6.scale) smears the 1-pixel outlines and dithering of palette art into a blur. The methods here, on an RGBA
array (h, w, 4) uint8 with alpha 0 or 255 as decoded from a DC6:

  bilinear   dc6.scale (the old output, kept for the comparison)
  lanczos    Lanczos-3 resize + mild unsharp mask
  scale2x    Scale2x (EPX) twice -> 4x, Lanczos down to the target size, mild unsharp mask
  scale3x    Scale3x (AdvMAME3x) -> 3x, Lanczos up to the target size, mild unsharp mask
  rune-*     Median's rune stones only: taken apart into stone, rim and sign and rebuilt crisp (tools/rune_hd.py)
  item-*     any picture rebuilt crisp: silhouette and brightness steps cut one by one, colours by edge-aware sampling
             (tools/item_rebuild.py)

ScaleNx are edge-directed: an output sub-pixel takes a neighbour's colour where two neighbours of the same colour meet
on a diagonal, so staircase edges become smooth lines and nothing is blended. "Same colour" is a YUV distance below
EQ_THRESHOLD (palette art shades an edge with neighbouring palette entries), transparent only equals transparent.
All resampling is on premultiplied alpha (no dark fringes); the sharpen works on premultiplied RGB and never exceeds
alpha. METHOD is the one the pipeline uses (chosen on the comparison sheet, docs/hd-icons.md).
Needs numpy and Pillow (both checked by tools/lane_setup.py).
"""
import numpy as np
from PIL import Image

METHODS = ("bilinear", "lanczos", "scale2x", "scale3x", "scale2x-loose", "hybrid", "rune-flat", "rune-hd", "rune-crisp",
           "item-hd", "item-soft")
METHOD = "hybrid"
EQ_THRESHOLD = 1.0   # YUV distance (0-255 scale) under which two opaque pixels count as the same colour (1: identical)
LOOSE_THRESHOLD = 24.0  # scale2x-loose: neighbouring shades count as one colour (posterizes pre-rendered texture)
SHARPEN = 0.5        # unsharp mask amount (0 = off)
ALPHA_FLOOR = 4      # resampled alpha below this is Lanczos ringing: made fully transparent
EDGE_LO, EDGE_HI = 40.0, 100.0  # hybrid: local contrast (YUV distance) where the edge weight goes from 0 to 1


def _yuv(a: np.ndarray) -> np.ndarray:
    rgb = a[..., :3].astype(np.float32)
    y = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    u = rgb @ np.array([-0.169, -0.331, 0.5], np.float32)
    v = rgb @ np.array([0.5, -0.419, -0.081], np.float32)
    return np.stack([y, u, v], -1)


def _neighbours(a: np.ndarray) -> dict[str, np.ndarray]:
    """The 3 x 3 neighbourhood of every pixel (outside the picture is transparent): keys A B C / D E F / G H I."""
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)))
    h, w = a.shape[:2]
    return {k: p[dy:dy + h, dx:dx + w] for k, (dy, dx) in zip("ABCDEFGHI", [(y, x) for y in range(3) for x in range(3)])}


def _eq_fn(threshold: float):
    def eq(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        ox, oy = x[..., 3] > 0, y[..., 3] > 0
        d = np.abs(_yuv(x) - _yuv(y)).max(-1)
        return (ox == oy) & (~ox | (d < threshold))
    return eq


def scale2x(a: np.ndarray, threshold: float = EQ_THRESHOLD) -> np.ndarray:
    """Scale2x / EPX: (h, w, 4) -> (2h, 2w, 4)."""
    n, eq = _neighbours(a), _eq_fn(threshold)
    B, D, E, F, H = n["B"], n["D"], n["E"], n["F"], n["H"]
    bd, bf, dh, fh = eq(B, D), eq(B, F), eq(D, H), eq(F, H)
    nbh, ndf = ~eq(B, H), ~eq(D, F)
    core = (nbh & ndf)[..., None]
    e0 = np.where(core & bd[..., None], D, E)
    e1 = np.where(core & bf[..., None], F, E)
    e2 = np.where(core & dh[..., None], D, E)
    e3 = np.where(core & fh[..., None], F, E)
    h, w = a.shape[:2]
    out = np.empty((2 * h, 2 * w, 4), a.dtype)
    out[0::2, 0::2], out[0::2, 1::2], out[1::2, 0::2], out[1::2, 1::2] = e0, e1, e2, e3
    return out


def scale3x(a: np.ndarray, threshold: float = EQ_THRESHOLD) -> np.ndarray:
    """Scale3x / AdvMAME3x: (h, w, 4) -> (3h, 3w, 4)."""
    n, eq = _neighbours(a), _eq_fn(threshold)
    A, B, C, D, E, F, G, H, I = (n[k] for k in "ABCDEFGHI")
    core = ~eq(B, H) & ~eq(D, F)
    db, bf, dh, hf = core & eq(D, B), core & eq(B, F), core & eq(D, H), core & eq(H, F)
    ne = lambda x: ~eq(E, x)  # noqa: E731
    c = lambda m: m[..., None]  # noqa: E731
    cells = [np.where(c(db), D, E),
             np.where(c((db & ne(C)) | (bf & ne(A))), B, E),
             np.where(c(bf), F, E),
             np.where(c((db & ne(G)) | (dh & ne(A))), D, E),
             E,
             np.where(c((bf & ne(I)) | (hf & ne(C))), F, E),
             np.where(c(dh), D, E),
             np.where(c((dh & ne(I)) | (hf & ne(G))), H, E),
             np.where(c(hf), F, E)]
    h, w = a.shape[:2]
    out = np.empty((3 * h, 3 * w, 4), a.dtype)
    for k, cell in enumerate(cells):
        out[k // 3::3, k % 3::3] = cell
    return out


def resize(a: np.ndarray, w: int, h: int, flt=Image.Resampling.LANCZOS) -> np.ndarray:
    """Premultiplied-alpha resize of an RGBA uint8 array. With Lanczos the colour is Lanczos' and the alpha a bilinear
    resize (Lanczos rings: it would dip the alpha inside a picture, making it see-through, and leave faint halos); alpha
    under ALPHA_FLOOR becomes transparent."""
    if a.shape[1] == w and a.shape[0] == h:
        return a
    im = Image.fromarray(np.ascontiguousarray(a), "RGBA").convert("RGBa")
    main = np.asarray(im.resize((w, h), flt)).astype(np.float32)
    if flt in (Image.Resampling.LANCZOS, Image.Resampling.BICUBIC):
        lin = np.asarray(im.resize((w, h), Image.Resampling.BILINEAR)).astype(np.float32)
        col = np.where(main[..., 3:4] >= 16, main[..., :3] / np.maximum(main[..., 3:4], 1) * 255,
                       lin[..., :3] / np.maximum(lin[..., 3:4], 1) * 255)
        alpha = lin[..., 3]
    else:
        col, alpha = main[..., :3] / np.maximum(main[..., 3:4], 1) * 255, main[..., 3]
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = np.clip(np.rint(col), 0, 255)
    out[..., 3] = np.clip(np.rint(alpha), 0, 255)
    out[out[..., 3] < ALPHA_FLOOR] = 0
    return out


def sharpen(a: np.ndarray, amount: float = SHARPEN) -> np.ndarray:
    """Unsharp mask (3 x 3 Gaussian) on premultiplied RGB; alpha is kept, colour never exceeds it."""
    if amount <= 0:
        return a
    al = a[..., 3:4].astype(np.float32) / 255
    pm = a[..., :3].astype(np.float32) * al
    p = np.pad(pm, ((1, 1), (1, 1), (0, 0)), mode="edge")
    h, w = a.shape[:2]
    k = np.array([1, 2, 1], np.float32) / 4
    blur = sum(k[i] * k[j] * p[i:i + h, j:j + w] for i in range(3) for j in range(3))
    pm = np.clip(pm + amount * (pm - blur), 0, 255 * al)
    out = a.copy()
    rgb = np.where(al > 0, pm / np.maximum(al, 1e-6), 0)
    out[..., :3] = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    return out


def upscale(a: np.ndarray, factor: float, method: str = METHOD) -> np.ndarray:
    """(h, w, 4) uint8 -> (round(h * factor), round(w * factor), 4) uint8."""
    h, w = a.shape[:2]
    sw, sh = max(1, round(w * factor)), max(1, round(h * factor))
    if method == "bilinear":
        from dc6 import scale
        rows = scale([[tuple(int(c) for c in p) for p in line] for line in a], sw, sh, factor)
        return np.array(rows, np.uint8).reshape(sh, sw, 4)
    if method.startswith("rune-"):
        import rune_hd
        return rune_hd.rune_upscale(a, sw, sh, method)
    if method.startswith("item-"):
        import item_rebuild
        return item_rebuild.rebuild(a, sw, sh, method)
    if method == "lanczos":
        big = a
    elif method == "scale2x":
        big = scale2x(scale2x(a)) if factor > 2 else scale2x(a)
    elif method == "scale2x-loose":
        big = scale2x(scale2x(a, LOOSE_THRESHOLD), LOOSE_THRESHOLD) if factor > 2 else scale2x(a, LOOSE_THRESHOLD)
    elif method == "hybrid":
        return sharpen(hybrid(a, sw, sh))
    elif method == "scale3x":
        big = scale3x(a)
    else:
        raise ValueError(f"unknown method {method!r}")
    return sharpen(resize(big, sw, sh))


def edge_weight(a: np.ndarray) -> np.ndarray:
    """Per source pixel 0..1: how strong an edge it sits on (largest YUV distance to a 4-neighbour; opaque next to
    transparent counts 255)."""
    n = _neighbours(a)
    E, yE = n["E"], _yuv(n["E"])
    e = np.zeros(a.shape[:2], np.float32)
    for k in "BDFH":
        x = n[k]
        d = np.abs(_yuv(x) - yE).max(-1)
        d = np.where((x[..., 3] > 0) != (E[..., 3] > 0), 255.0, np.where(E[..., 3] > 0, d, 0.0))
        e = np.maximum(e, d)
    return np.clip((e - EDGE_LO) / (EDGE_HI - EDGE_LO), 0, 1)


def hybrid(a: np.ndarray, sw: int, sh: int) -> np.ndarray:
    """Scale2x twice (exact colours) on edges, Lanczos in the texture: a premultiplied blend weighted by edge_weight
    (bilinearly upsampled), so outlines and silhouettes come out clean and dithered texture is not turned into blobs."""
    edge = scale2x(scale2x(a)) if sw > 2 * a.shape[1] else scale2x(a)
    r_edge, r_tex = resize(edge, sw, sh).astype(np.float32), resize(a, sw, sh).astype(np.float32)
    m = np.asarray(Image.fromarray(edge_weight(a), "F").resize((sw, sh), Image.Resampling.BILINEAR))[..., None]
    pm = lambda x: np.concatenate([x[..., :3] * x[..., 3:4] / 255, x[..., 3:4]], -1)  # noqa: E731
    out = m * pm(r_edge) + (1 - m) * pm(r_tex)
    al = out[..., 3:4]
    rgb = np.where(al > 0, out[..., :3] * 255 / np.maximum(al, 1e-6), 0)
    return np.clip(np.rint(np.concatenate([rgb, al], -1)), 0, 255).astype(np.uint8)


def place(img: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    """`img` centred on a transparent out_w x out_h canvas (cropped when it does not fit), as dc6.scale places it."""
    out = np.zeros((out_h, out_w, 4), np.uint8)
    h, w = img.shape[:2]
    ox, oy = (out_w - w) // 2, (out_h - h) // 2
    sx, sy = max(0, -ox), max(0, -oy)
    tx, ty = max(0, ox), max(0, oy)
    cw, ch = min(w - sx, out_w - tx), min(h - sy, out_h - ty)
    if cw > 0 and ch > 0:
        out[ty:ty + ch, tx:tx + cw] = img[sy:sy + ch, sx:sx + cw]
    return out


def scale_rows(rows: list, out_w: int, out_h: int, factor: float, method: str = METHOD) -> list:
    """dc6.scale's call with the pixel-art upscaler: dc6 rows scaled by `factor` and centred on a transparent out_w x out_h
    canvas, as dc6 rows (lists of (r, g, b, a) tuples). Used for the skill icon sheets (tools/skill_icons.py)."""
    if not rows or not rows[0]:
        return [[(0, 0, 0, 0)] * out_w for _ in range(out_h)]
    img = place(upscale(rows_to_array(rows), factor, method), out_w, out_h)
    return [[tuple(int(c) for c in p) for p in line] for line in img]


def rows_to_array(rows: list) -> np.ndarray:
    """dc6 rows (lists of (r, g, b, a)) as an (h, w, 4) uint8 array."""
    h, w = len(rows), (len(rows[0]) if rows else 0)
    return np.array(rows, np.uint8).reshape(h, w, 4)
