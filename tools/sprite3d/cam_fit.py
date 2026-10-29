"""Fit the sprite cameras to a generated mesh (3D venv: numpy, scipy, PIL).

    cam_fit.py <mesh.npz> <views dir (nu_d<N>.png, RGBA)> <out cameras.json> [--elev 20,25,30,35,40] [--ky 1.0,1.1547]

The 16 sprite directions of a Median monster sit on a ring 22.5 degrees apart (README.md): angular order
`0 9 5 10 1 11 6 12 2 13 7 14 3 15 4 8`; direction 4 is the mesh's front (+z) and 5, 6, 7 the left, back and right views the mesh
was generated from. The camera of one sprite is orthographic:

    px = tx + s * (p . r)        py = ty - s * ky * (p . u)        depth towards the camera = p . w
    r = (cos a, 0, -sin a)   u = (-sin a sin e, cos e, -cos a sin e)   w = (sin a cos e, sin e, cos a cos e)

a is the azimuth (0 = camera in front, on +z), e the elevation above the ground plane, ky a shared vertical stretch (Diablo II
sprites are drawn with the ground plane squashed 2:1, so a unit of height may not shrink with cos e). Azimuth, scale and the
offset of every sprite, and elevation and ky for all of them, are found by silhouette overlap (IoU of the splatted mesh
points against the sprite's alpha).
"""
import json
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

RING = [0, 9, 5, 10, 1, 11, 6, 12, 2, 13, 7, 14, 3, 15, 4, 8]
DS = 4  # masks are fitted at 1/4 of the x4 sprites


def basis(az, el):
    a, e = np.radians(az), np.radians(el)
    r = np.array([np.cos(a), 0, -np.sin(a)])
    u = np.array([-np.sin(a) * np.sin(e), np.cos(e), -np.cos(a) * np.sin(e)])
    w = np.array([np.sin(a) * np.cos(e), np.sin(e), np.cos(a) * np.cos(e)])
    return r, u, w


def project(pts, az, el, ky):
    r, u, _ = basis(az, el)
    return np.stack([pts @ r, ky * (pts @ u)], 1)


def splat(xy, s, tx, ty, shape):
    h, w = shape
    px = np.round(tx + s * xy[:, 0]).astype(int)
    py = np.round(ty - s * xy[:, 1]).astype(int)
    ok = (px >= 0) & (px < w) & (py >= 0) & (py < h)
    m = np.zeros(shape, bool)
    m[py[ok], px[ok]] = True
    m = ndimage.binary_closing(m, iterations=2)
    return ndimage.binary_fill_holes(m)


def iou(a, b):
    return (a & b).sum() / max((a | b).sum(), 1)


def fit_view(pts, mask, az0, el, ky, span=14, step=1.0):
    """Best (az, s, tx, ty, iou) near az0 for one sprite mask."""
    ys, xs = np.nonzero(mask)
    area, cx, cy = mask.sum(), xs.mean(), ys.mean()
    best = (-1,)
    for az in np.arange(az0 - span, az0 + span + 1e-6, step):
        xy = project(pts, az, el, ky)
        c = xy.mean(0)
        # scale from the area of the splat, centroids matched
        s = mask.shape[0] * 0.8 / max(np.ptp(xy[:, 1]), 1e-6)
        for _ in range(3):
            m = splat(xy, s, cx - s * c[0], cy + s * c[1], mask.shape)
            if m.sum() == 0:
                break
            s *= (area / m.sum()) ** 0.5
        tx, ty = cx - s * c[0], cy + s * c[1]
        sc = iou(splat(xy, s, tx, ty, mask.shape), mask)
        if sc > best[0]:
            best = (sc, az, s, tx, ty)
    sc, az, s, tx, ty = best
    # local refinement of the offset and scale
    for d in (2.0, 1.0, 0.5):
        improved = True
        while improved:
            improved = False
            for dtx, dty, ds in ((d, 0, 0), (-d, 0, 0), (0, d, 0), (0, -d, 0), (0, 0, d * 0.01), (0, 0, -d * 0.01)):
                xy = project(pts, az, el, ky)
                v = iou(splat(xy, s * (1 + ds), tx + dtx, ty + dty, mask.shape), mask)
                if v > sc + 1e-4:
                    sc, s, tx, ty, improved = v, s * (1 + ds), tx + dtx, ty + dty, True
    return sc, az, s, tx, ty


def main():
    a = sys.argv[1:]
    npz, vdir, out = a[:3]
    elevs = [float(x) for x in a[a.index("--elev") + 1].split(",")] if "--elev" in a else [20, 25, 30, 35, 40]
    kys = [float(x) for x in a[a.index("--ky") + 1].split(",")] if "--ky" in a else [1.0, 1.0 / np.cos(np.radians(30))]
    d = np.load(npz)
    rng = np.random.default_rng(0)
    # points on the surface
    pos, tris = d["pos"], d["tris"]
    p0, p1, p2 = pos[tris[:, 0]], pos[tris[:, 1]], pos[tris[:, 2]]
    area = np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1)
    k = rng.choice(len(tris), 100000, p=area / area.sum())
    b = rng.random((100000, 2))
    flip = b.sum(1) > 1
    b[flip] = 1 - b[flip]
    pts = p0[k] + b[:, :1] * (p1[k] - p0[k]) + b[:, 1:] * (p2[k] - p0[k])
    yoff = float(pts[:, 1].mean())
    pts = pts - np.array([0, yoff, 0])
    masks, full = {}, {}
    for v in range(16):
        im = Image.open(f"{vdir}/nu_d{v}.png").convert("RGBA")
        alpha = np.array(im)[..., 3]
        full[v] = alpha.shape
        small = np.array(Image.fromarray(alpha).resize((alpha.shape[1] // DS, alpha.shape[0] // DS), Image.BILINEAR)) > 100
        masks[v] = small
    i4 = RING.index(4)
    best = None
    for sign in (1, -1):
        for el in elevs:
            for ky in kys:
                tot, res = 0, {}
                for v in range(16):
                    az0 = sign * 22.5 * ((RING.index(v) - i4) % 16)
                    res[v] = fit_view(pts, masks[v], az0, el, ky, span=10, step=2.5)
                    tot += res[v][0]
                print("sign", sign, "elev", el, "ky %.3f" % ky, "mean IoU %.3f" % (tot / 16), flush=True)
                if best is None or tot > best[0]:
                    best = (tot, sign, el, ky)
    _, sign, el, ky = best
    # the ring is exact, the generated mesh is turned a few degrees about the vertical: one shared yaw offset, then a narrow search
    pred = {v: sign * 22.5 * ((RING.index(v) - i4) % 16) for v in range(16)}
    first = {v: fit_view(pts, masks[v], pred[v], el, ky, span=14, step=1.0)[1] for v in range(16)}
    dev = [((first[v] - pred[v] + 180) % 360) - 180 for v in range(16)]
    delta = float(np.median([dev[v] for v in (4, 5, 6, 7)]))  # the four views the mesh was generated from
    print("yaw offset %.1f (per view %s)" % (delta, [round(x) for x in dev]))
    cams = {}
    for v in range(16):
        sc, az, s, tx, ty = fit_view(pts, masks[v], pred[v] + delta, el, ky, span=4, step=1.0)
        cams[v] = dict(az=float(az), el=el, ky=float(ky), s=float(s * DS), tx=float(tx * DS + DS / 2), ty=float(ty * DS + DS / 2), iou=float(sc),
                       w=int(full[v][1]), h=int(full[v][0]), yoff=yoff)
        print("d%-2d az %6.1f iou %.3f" % (v, az, sc))
    json.dump(dict(sign=sign, el=el, ky=float(ky), cams=cams), open(out, "w"), indent=1)
    print("sign", sign, "elev", el, "ky", ky, "mean IoU %.3f" % np.mean([c["iou"] for c in cams.values()]))


if __name__ == "__main__":
    main()
