"""Copy classic's cap pattern (rim speckle, green ring, dark centre) onto the cap texels, one sprite view per texel.

    s3_caprim.py <mesh_uv.npz> <part.png> <albedo.png> <cams.json> <views dir> <out dir> [--top 0.15] [--soft 0.35] [--pick polar|far|facing] [--residual SIGMA] [--gain G] [--inner R] [--speck-grow N]

project_texture.py's `--blend` averages all views that see a texel. On the cap that wipes out the small pale and dark
specks of classic's rim (they sit at a different place in every view), so the rim turns into an even band. Here every
top-facing cap texel takes its colour from ONE view, nearest neighbour, so the specks keep classic's size and contrast:

1. The atlas is rasterised (face id + barycentrics per texel) and every texel gets its 3D point and smooth normal.
2. Per view (the views dir holds nu_d<N>.png, the x4 neutral sprites; cams.json is cam_fit's fit), the cap is found in the
   sprite as the convex hull of its blue rim (B >= 120, B - max(R, G) > 50), and in the model as the convex hull of the
   projected front-facing cap points. The mean and covariance of both hulls give an affine map model -> sprite, so a
   loose camera fit (IoU about 0.7) still lands every point on the right ring of classic's cap.
3. Every cap texel whose normal points up (n.y > --top) takes ONE view and the sprite pixel there (nearest). `--pick far`
   (default) takes the view that sees the texel on the far half of the cap, where classic shows the top squarely;
   `--pick facing` takes the view that faces the texel most (n . w), which lands the outer rim on the pale side face of
   classic's front rim and smears it over the top. Texels that land outside the classic hull or on a transparent pixel try the next view.
4. The copy is blended in by smoothstep(--top, --soft, n.y), so the side and the underside of the cap keep the old colour.

`--residual SIGMA` (polar only; x4 sprite px) copies only the specks: the sprite minus its Gaussian local mean inside the
cap, as luminance only, added (times `--gain`) to the albedo's own cap colour, and only beyond radius `--inner` (faded in over
0.25): near the axis the eight view sectors meet and their specks would form a pinwheel. The ring layout stays the blended bake's, so a speck that lands a
little off its ring or a seam between two views does not show; what classic gives is the specks' size, contrast and how
they thin out toward the dark centre.

Writes albedo_caprim.png (the albedo with the cap copied), caprim_view.png (which view each texel took) and caprim.json.
"""
import json
import sys
from pathlib import Path

import numba as nb
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd
from scipy.spatial import ConvexHull

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cam_fit  # noqa: E402


@nb.njit(cache=True)
def raster(uvt, H, W):
    ids = -np.ones((H, W), np.int32)
    bary = np.zeros((H, W, 3), np.float32)
    for i in range(uvt.shape[0]):
        ax, ay = uvt[i, 0, 0] * W, uvt[i, 0, 1] * H
        bx, by = uvt[i, 1, 0] * W, uvt[i, 1, 1] * H
        cx, cy = uvt[i, 2, 0] * W, uvt[i, 2, 1] * H
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        x0 = max(int(np.floor(min(ax, bx, cx))), 0)
        x1 = min(int(np.ceil(max(ax, bx, cx))), W - 1)
        y0 = max(int(np.floor(min(ay, by, cy))), 0)
        y1 = min(int(np.ceil(max(ay, by, cy))), H - 1)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px, py = x + 0.5, y + 0.5
                l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
                l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
                l3 = 1 - l1 - l2
                if l1 >= -1e-4 and l2 >= -1e-4 and l3 >= -1e-4:
                    ids[y, x] = i
                    bary[y, x, 0], bary[y, x, 1], bary[y, x, 2] = l1, l2, l3
    return ids, bary


def hull_mask(pts, shape):
    hull = ConvexHull(pts)
    poly = Image.new("L", (shape[1], shape[0]))
    ImageDraw.Draw(poly).polygon([tuple(map(float, pts[v])) for v in hull.vertices], fill=1)
    return np.asarray(poly).astype(bool)


def sprite_cap(a):
    """Convex hull mask of the cap in a sprite (h, w, 4): the biggest blue rim piece and the pieces near it."""
    R, G, B = (a[..., i].astype(float) for i in range(3))
    rim = (B >= 120) & (B - np.maximum(R, G) > 50) & (a[..., 3] > 127)
    lab, n = nd.label(rim, structure=np.ones((3, 3)))
    size = nd.sum(rim, lab, range(1, n + 1))
    ys, xs = np.nonzero(lab == 1 + np.argmax(size))
    m = 48  # px at x4
    keep = []
    for i in range(n):
        yy, xx = np.nonzero(lab == i + 1)
        if size[i] >= 24 and yy.min() >= ys.min() - m and yy.max() <= ys.max() + m and xx.min() >= xs.min() - m \
                and xx.max() <= xs.max() + m:
            keep.append(i + 1)
    ys, xs = np.nonzero(np.isin(lab, keep))
    return hull_mask(np.c_[xs, ys].astype(float), a.shape[:2])


def moments(mask):
    ys, xs = np.nonzero(mask)
    p = np.c_[xs, ys].astype(float)
    return p.mean(0), np.cov(p.T)


def msqrt(c, inv=False):
    w, v = np.linalg.eigh(c)
    w = np.maximum(w, 1e-9)
    return (v * (w ** (-0.5 if inv else 0.5))) @ v.T


GROW = 0


def residual(spr, m, sigma):
    """The sprite's colour minus its local mean inside the cap mask (normalised Gaussian blur): classic's specks alone.
    With --speck-grow N (x4 px) every bright speck is grown by a max filter and every dark one by a min filter of size N, so
    a speck of one sprite pixel stays a full-contrast speck after the game's mip filtering."""
    rgb = spr[..., :3].astype(np.float32)
    w = nd.gaussian_filter(m.astype(np.float32), sigma)
    mean = np.stack([nd.gaussian_filter(rgb[..., i] * m, sigma) for i in range(3)], -1) / np.maximum(w, 1e-6)[..., None]
    d = rgb - mean
    dl = 0.2126 * d[..., 0] + 0.7152 * d[..., 1] + 0.0722 * d[..., 2]  # luminance only: a hue residual reads as brown
    if GROW > 1:
        dl = nd.maximum_filter(np.maximum(dl, 0), GROW) + nd.minimum_filter(np.minimum(dl, 0), GROW)
    return np.where(m[..., None], dl[..., None].repeat(3, -1), 0)


def polar(P, up, ctr, rad, keys, cams, views, rep, sigma=0.0):
    """Sample every cap texel by (absolute angle, normalised radius) on classic's top disc.

    In a sprite, the top of the cap is a disc seen from `el` degrees: an ellipse whose half width a is half the cap's width
    and whose half height is a * sin(el), hanging from the top edge of the cap (the far rim, where no side face is drawn).
    A point at screen angle t and radius r of the disc is at (cx + r a cos t, cy + r a sin(el) sin t). On the model, r is
    the texel's horizontal distance from the cap axis over the largest one in its angle bin, and the screen angle in a view
    is the texel's angle around the axis minus the view's azimuth. Each texel takes the view where it lies nearest the
    left or right end of the ellipse (sin t = 0), where the disc is not foreshortened along the radius."""
    d = np.hypot(P[:, 0] - ctr[0], P[:, 2] - ctr[2])
    phi = np.arctan2(P[:, 2] - ctr[2], P[:, 0] - ctr[0])
    bins = np.clip(((phi + np.pi) / (2 * np.pi) * 180).astype(int), 0, 179)
    rmax = np.zeros(180)
    np.maximum.at(rmax, bins[up], d[up])
    rmax = np.maximum(nd.maximum_filter1d(rmax, 3, mode="wrap"), 1e-6)
    r = np.clip(d / rmax[bins], 0, 1)
    n = len(P)
    score = np.full((len(keys), n), -9.0)
    col = np.zeros((len(keys), n, 3), np.float32)
    ok = np.zeros((len(keys), n), bool)
    for k, key in enumerate(keys):
        c = cams["cams"][key]
        spr = np.asarray(Image.open(views / ("nu_d%s.png" % key)).convert("RGBA"))
        m = sprite_cap(spr)
        ys, xs = np.nonzero(m)
        a = (xs.max() - xs.min() + 1) / 2
        b = a * np.sin(np.radians(c["el"]))
        cx, cy = (xs.max() + xs.min() + 1) / 2, ys.min() + b
        # screen x = P . r_cam: the horizontal direction (cos phi, sin phi) is at screen angle t with cos t = dir . r_cam
        rc, _, wc = cam_fit.basis(c["az"], c["el"])
        hx, hz = np.cos(phi), np.sin(phi)
        ct = hx * rc[0] + hz * rc[2]
        # toward the camera (w's horizontal part) is the near rim, the bottom of the ellipse (larger row)
        st = (hx * wc[0] + hz * wc[2]) / max(np.hypot(wc[0], wc[2]), 1e-9)
        x = cx + r * a * ct
        y = cy + r * b * st
        xi, yi = np.rint(x - 0.5).astype(int), np.rint(y - 0.5).astype(int)
        ins = (xi >= 0) & (xi < spr.shape[1]) & (yi >= 0) & (yi < spr.shape[0])
        xi[~ins], yi[~ins] = 0, 0
        px = spr[yi, xi]
        ok[k] = ins & (px[:, 3] > 127) & m[yi, xi]
        col[k] = residual(spr, m, sigma)[yi, xi] if sigma > 0 else px[:, :3]
        score[k] = -np.abs(st)
        rep["views"][key] = {"az": c["az"], "half_width": float(a), "centre": [float(cx), float(cy)]}
    return score, col, ok, r


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def main():
    a = sys.argv[1:]
    if len(a) < 6:
        print(__doc__)
        return 1
    opt = lambda k, d: float(a[a.index(k) + 1]) if k in a else d  # noqa: E731
    top, soft = opt("--top", 0.15), opt("--soft", 0.35)
    sigma, gain, inner = opt("--residual", 0.0), opt("--gain", 1.0), opt("--inner", 0.35)
    global GROW
    GROW = int(opt("--speck-grow", 0))
    mesh = np.load(a[0])
    part = np.asarray(Image.open(a[1]).convert("L")) > 127
    alb = np.asarray(Image.open(a[2]).convert("RGB")).astype(np.float32)
    cams = json.load(open(a[3]))
    views, out = Path(a[4]), Path(a[5])
    out.mkdir(parents=True, exist_ok=True)
    H, W = part.shape
    pos, nrm, uv, tris = mesh["pos"], mesh["nrm"], mesh["uv"], mesh["tris"]
    ids, bary = raster(np.ascontiguousarray(uv[tris], np.float64), H, W)
    cap = part & (ids >= 0)
    yy, xx = np.nonzero(cap)
    f = tris[ids[yy, xx]]
    b = bary[yy, xx]
    P = (pos[f] * b[..., None]).sum(1)
    N = (nrm[f] * b[..., None]).sum(1)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    up = N[:, 1] > top
    pick = a[a.index("--pick") + 1] if "--pick" in a else "polar"
    ctr = P[up].mean(0)
    rad = P - ctr
    rad[:, 1] = 0
    rad /= np.maximum(np.linalg.norm(rad, axis=1, keepdims=True), 1e-9)
    keys = sorted(cams["cams"], key=int)
    score = np.full((len(keys), len(P)), -9.0)
    col = np.zeros((len(keys), len(P), 3), np.float32)
    ok = np.zeros((len(keys), len(P)), bool)
    rep = {"views": {}}
    for k, key in enumerate(keys):
        c = cams["cams"][key]
        spr = np.asarray(Image.open(views / ("nu_d%s.png" % key)).convert("RGBA"))
        r, u, w = cam_fit.basis(c["az"], c["el"])
        s_mask = sprite_cap(spr)
        Q = P - np.array([0, c.get("yoff", 0.0), 0])  # as project_texture.py
        sx = c["tx"] - 0.5 + c["s"] * (Q @ r)
        sy = c["ty"] - 0.5 - c["s"] * c["ky"] * (Q @ u)
        front = (N @ w) > 0
        m_mask = hull_mask(np.c_[sx[front], sy[front]], spr.shape[:2])
        mu_m, c_m = moments(m_mask)
        mu_s, c_s = moments(s_mask)
        A = msqrt(c_s) @ msqrt(c_m, inv=True)
        q = (np.c_[sx, sy] - mu_m) @ A.T + mu_s
        qi = np.rint(q - 0.5).astype(int)
        inside = (qi[:, 0] >= 0) & (qi[:, 0] < spr.shape[1]) & (qi[:, 1] >= 0) & (qi[:, 1] < spr.shape[0])
        qi[~inside] = 0
        px = spr[qi[:, 1], qi[:, 0]]
        ok[k] = inside & s_mask[qi[:, 1], qi[:, 0]] & (px[:, 3] > 127) & front
        col[k] = px[:, :3]
        # far: the view that sees the texel on the far half of the cap (the top seen squarely, not the rim's side face)
        score[k] = -(rad @ w) if pick == "far" else N @ w
        rep["views"][key] = {"az": c["az"], "sprite_cap_px": int(s_mask.sum()), "model_cap_px": int(m_mask.sum()),
                             "scale": [float(x) for x in np.linalg.eigvalsh(A)]}
    if pick == "polar":
        score, col, ok, rr = polar(P, up, ctr, rad, keys, cams, views, rep, sigma)
    score[~ok] = -9.0
    best = score.argmax(0)
    got = score.max(0) > -9.0
    use = up & got
    new = alb.copy()
    t = smoothstep(top, soft, N[:, 1]) * use
    src = col[best, np.arange(len(P))]
    if sigma > 0:  # add classic's specks to the colour the cap already has, on the outer part of the top only
        t = t * smoothstep(inner, inner + 0.25, rr)
        new[yy, xx] = alb[yy, xx] + gain * t[:, None] * src
    else:
        new[yy, xx] = (1 - t[:, None]) * alb[yy, xx] + t[:, None] * src
    Image.fromarray(np.clip(np.rint(new), 0, 255).astype(np.uint8)).save(out / "albedo_caprim.png")
    vis = np.zeros((H, W, 3), np.uint8)
    pal = np.array([[230, 25, 75], [60, 180, 75], [255, 225, 25], [0, 130, 200], [245, 130, 48], [145, 30, 180],
                    [70, 240, 240], [240, 50, 230]], np.uint8)
    vis[yy[use], xx[use]] = pal[best[use]]
    Image.fromarray(vis).save(out / "caprim_view.png")
    rep.update(cap_texels=int(len(P)), top_texels=int(up.sum()), copied=int(use.sum()),
               per_view={keys[k]: int(((best == k) & use).sum()) for k in range(len(keys))}, top=top, soft=soft, pick=pick, residual=sigma, gain=gain, inner=inner)
    json.dump(rep, open(out / "caprim.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != "views"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
