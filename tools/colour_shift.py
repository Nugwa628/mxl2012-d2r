"""Hue / saturation / brightness shift of RGBA8 pixels: the recolour of tools/hd_recolour.py (effect gradients) and
tools/item_reuse.py (D2R's HD item pictures of art Median recoloured). No game files, no game slot."""
import numpy as np


def shift_pixels(a: np.ndarray, hue: float, sat: float, val: float, sat_mul: float = 1.0) -> np.ndarray:
    """Hue rotation (turns), saturation offset, saturation factor `sat_mul` and brightness factor 2**val of RGBA8 pixels;
    alpha is kept."""
    rgb = a[..., :3].astype(np.float32) / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    dd = np.maximum(d, 1e-9)
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6.0
    h = np.where(d == 0, 0.0, h)
    s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0)
    h = (h + hue) % 1.0
    s = np.clip((s + sat * (s > 0.02)) * sat_mul, 0, 1)
    v = np.clip(mx * (2.0 ** val), 0, 1)
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    out = np.zeros_like(rgb)
    for k, (ra, ga, ba) in enumerate([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]):
        m = i == k
        out[..., 0][m], out[..., 1][m], out[..., 2][m] = ra[m], ga[m], ba[m]
    res = a.copy()
    res[..., :3] = np.clip(np.rint(out * 255), 0, 255).astype(np.uint8)
    return res
