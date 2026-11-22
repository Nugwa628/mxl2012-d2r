"""Numbers of a rendered (or captured) image, and of how densely the textures are drawn.

Image measures work on 8-bit RGBA with straight alpha, or RGB with a separate mask:
  height_px        rows between the top and bottom covered pixel (the on-screen height)
  coverage         covered pixels / all pixels, and the covered count
  luma_mean/median Rec. 709 luma of the sRGB-encoded values (0..255), over covered pixels: comparable with game captures
  hist16           16-bin histogram of that luma over covered pixels (fractions)
  rgb_mean         mean sRGB colour of covered pixels

`texels_per_pixel` measures the texture density on screen: per triangle, sqrt(texel area / pixel area), its median weighted by
pixel area. Below 1 the texture is magnified (more pixels than texels), above 1 minified (detail is lost to filtering).
"""
import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722])


def image(rgba: np.ndarray, mask: np.ndarray | None = None, alpha_cut: int = 128) -> dict:
    a = np.asarray(rgba)
    if mask is None:
        mask = a[..., 3] >= alpha_cut if a.shape[-1] == 4 else np.ones(a.shape[:2], bool)
    mask = np.asarray(mask, bool)
    n = int(mask.sum())
    out = {"size": [int(a.shape[1]), int(a.shape[0])], "covered_px": n, "coverage": round(n / mask.size, 6)}
    if a.shape[-1] == 4:
        out["alpha_coverage_any"] = round(float((a[..., 3] > 0).mean()), 6)
    if n == 0:
        out.update(height_px=0, width_px=0, bbox=None, luma_mean=None, luma_median=None, hist16=[0.0] * 16, rgb_mean=None)
        return out
    ys, xs = np.nonzero(mask)
    rgb = a[..., :3][mask].astype(float)
    luma = rgb @ LUMA
    hist = np.histogram(luma, bins=16, range=(0, 256))[0] / n
    out.update(height_px=int(ys.max() - ys.min() + 1), width_px=int(xs.max() - xs.min() + 1),
               bbox=[int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
               luma_mean=round(float(luma.mean()), 2), luma_median=round(float(np.median(luma)), 2),
               luma_p90=round(float(np.percentile(luma, 90)), 2),
               hist16=[round(float(h), 4) for h in hist], rgb_mean=[round(float(c), 1) for c in rgb.mean(0)])
    return out


def iou(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def texels_per_pixel(screen_tris: np.ndarray, texel_tris: np.ndarray) -> dict:
    """screen_tris, texel_tris: (m, 3, 2) pixel and texel coordinates of the same triangles."""
    def area(t):
        e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
        return 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    sa, ta = area(np.asarray(screen_tris, float)), area(np.asarray(texel_tris, float))
    ok = (sa > 1e-9) & (ta > 1e-12)
    if not ok.any():
        return {"median": None, "p10": None, "p90": None, "triangles": 0}
    r, w = np.sqrt(ta[ok] / sa[ok]), sa[ok]
    order = np.argsort(r)
    cw = np.cumsum(w[order]) / w.sum()

    def q(p):
        return round(float(r[order][min(np.searchsorted(cw, p), len(r) - 1)]), 3)
    return {"median": q(0.5), "p10": q(0.1), "p90": q(0.9), "triangles": int(ok.sum())}
