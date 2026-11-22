"""Software render of a mesh .npz from the sprite camera (3D venv: numpy, numba, PIL): no Blender, no GPU.

    render_soft.py <mesh.npz> <out.png> [--az 0,45,...] [--elev 30] [--size 400] [--albedo a.png] [--bg 40,40,48] [--lod K]

One tile per azimuth in a row. The camera is cam_fit.py's: orthographic, azimuth 0 in front of the mesh (+z), `--elev` degrees
above the ground. Grey with a head light and a key light from the upper left when there is no albedo; with `--albedo` (and uv
in the npz) the texture is drawn unlit (`--lit`: times the same lighting), which is what a sprite comparison needs: the classic
frames carry their own baked light.

As a module: `render(pos, tris, az, el, size, ...)` returns an RGBA uint8 array; `scale` and `centre` fix the framing so that
several azimuths (or animation frames) share one camera.
"""
import sys
from pathlib import Path

import numba as nb
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cam_fit  # noqa: E402


@nb.njit(cache=True)
def _raster(xy, z, H, W):
    ids = -np.ones((H, W), np.int32)
    zb = np.full((H, W), -1e9, np.float32)
    bary = np.zeros((H, W, 3), np.float32)
    for i in range(len(xy)):
        ax, ay, bx, by, cx, cy = xy[i, 0, 0], xy[i, 0, 1], xy[i, 1, 0], xy[i, 1, 1], xy[i, 2, 0], xy[i, 2, 1]
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
                if l1 >= -1e-5 and l2 >= -1e-5 and l3 >= -1e-5:
                    zz = l1 * z[i, 0] + l2 * z[i, 1] + l3 * z[i, 2]
                    if zz > zb[y, x]:
                        zb[y, x] = zz
                        ids[y, x] = i
                        bary[y, x, 0], bary[y, x, 1], bary[y, x, 2] = l1, l2, l3
    return ids, zb, bary


def vertex_normals(pos, tris):
    fn = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    vn = np.zeros_like(pos)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)


def framing(pos, size, el=30.0, margin=0.06):
    """(scale, centre) that fit the mesh into a size x size tile from every azimuth at elevation `el`."""
    c = (pos.min(0) + pos.max(0)) / 2
    r = np.linalg.norm(pos - c, axis=1).max()
    return size * (1 - 2 * margin) / (2 * r), c


def render(pos, tris, az, el=30.0, size=400, scale=None, centre=None, nrm=None, uv=None, tex=None, lit=None, bg=None, ss=2,
           ky=1.0, colour=(0.72, 0.72, 0.74), rough=None, vcol=None):
    """RGBA (size, size, 4) uint8. tex: float (h, w, 3) 0..255 with uv (N, 2), v down; ss: supersampling factor.
    rough: float (h, w) 0..1 in the same uv; with `lit` it adds a highlight of the key light (a preview of a glossy ORM map,
    not the game's shading). vcol: (N, 3) 0..1 vertex colours, interpolated over each triangle (a weight paint), lit."""
    pos = np.asarray(pos, np.float64)
    tris = np.asarray(tris, np.int64)
    if scale is None:
        scale, centre = framing(pos, size, el)
    if lit is None:
        lit = tex is None
    S = size * ss
    r, u, w = cam_fit.basis(az, el)
    q = pos - centre
    x = S / 2 + scale * ss * (q @ r)
    y = S / 2 - scale * ss * ky * (q @ u)
    z = (q @ w).astype(np.float32)
    ids, zb, bary = _raster(np.stack([x[tris], y[tris]], 2), z[tris], S, S)
    cov = ids >= 0
    f = np.maximum(ids, 0)
    if tex is not None and uv is not None:
        uvp = np.einsum("hwk,hwkc->hwc", bary, np.asarray(uv, np.float32)[tris[f]])
        th, tw = tex.shape[:2]
        tx = np.clip(uvp[..., 0] * tw - 0.5, 0, tw - 1.001)
        ty = np.clip(uvp[..., 1] * th - 0.5, 0, th - 1.001)
        x0, y0 = tx.astype(int), ty.astype(int)
        fx, fy = (tx - x0)[..., None], (ty - y0)[..., None]
        col = (tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x0 + 1] * fx * (1 - fy) + tex[y0 + 1, x0] * (1 - fx) * fy
               + tex[y0 + 1, x0 + 1] * fx * fy) / 255.0
    elif vcol is not None:
        col = np.einsum("hwk,hwkc->hwc", bary, np.asarray(vcol, np.float32)[tris[f]])
    else:
        col = np.broadcast_to(np.array(colour, np.float32), (S, S, 3)).copy()
    if lit:
        vn = vertex_normals(pos, tris) if nrm is None else np.asarray(nrm, np.float64)
        n = np.einsum("hwk,hwkc->hwc", bary, vn[tris[f]].astype(np.float32))
        n /= np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-9)
        key = -r * 0.55 + u * 0.6 + w * 0.58
        key /= np.linalg.norm(key)
        shade = 0.28 + 0.5 * np.clip(n @ key, 0, 1) + 0.3 * np.clip(n @ w, 0, 1)
        col = col * shade[..., None]
        if rough is not None and tex is not None:
            g = 1.0 - rough[y0, x0]
            half = (key + w) / np.linalg.norm(key + w)
            col = col + (0.9 * g * g * np.clip(n @ half, 0, 1) ** (8 + 120 * g * g))[..., None] * np.array([0.75, 0.88, 1.0], np.float32)
    img = np.zeros((S, S, 4), np.float32)
    img[..., :3] = np.clip(col, 0, 1) * cov[..., None]
    img[..., 3] = cov
    img = img.reshape(size, ss, size, ss, 4).mean((1, 3))
    a = img[..., 3:]
    rgb = img[..., :3] / np.maximum(a, 1e-6)
    if bg is not None:
        rgb = rgb * a + np.array(bg, np.float32) / 255.0 * (1 - a)
        a = np.ones_like(a)
    return np.clip(np.dstack([rgb, a]) * 255 + 0.5, 0, 255).astype(np.uint8)


def main():
    a = sys.argv[1:]
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    d = np.load(a[0], allow_pickle=True)
    sfx = "" if opt("--lod", "0") == "0" else "_" + opt("--lod", "0")
    pos, tris = d["pos" + sfx], d["tris" + sfx]
    uv = d["uv" + sfx] if "uv" + sfx in d.files else None
    tex = np.asarray(Image.open(opt("--albedo", "")).convert("RGB")).astype(np.float32) if "--albedo" in a else None
    azs = [float(x) for x in opt("--az", "0,45,90,135,180,225,270,315").split(",")]
    el, size = float(opt("--elev", "30")), int(opt("--size", "400"))
    bg = [int(x) for x in opt("--bg", "40,40,48").split(",")]
    scale, centre = framing(pos, size, el)
    tiles = [render(pos, tris, az, el, size, scale, centre, uv=uv, tex=tex, lit=("--lit" in a) or tex is None, bg=bg) for az in azs]
    Image.fromarray(np.hstack(tiles)[..., :3]).save(a[1])
    print(a[1], len(pos), "vertices", len(tris), "triangles")


if __name__ == "__main__":
    main()
