"""Bake a colour texture for a generated mesh from the Median sprite directions (3D venv: numpy, scipy, PIL, numba, xatlas).

    project_texture.py <mesh.npz> <cameras.json> <views dir> <out dir> [--size 2048] [--smooth 10]

mesh.npz holds pos and tris (tools/d2r_mesh.py's input); cameras.json is tools/sprite3d/cam_fit.py's output; the views dir holds
the upscaled neutral sprites nu_d<N>.png of all 16 directions. Steps:

1. The mesh is smoothed a little (Taubin) and every face is scored for each sprite camera: how directly the camera looks at it
   (n . w) times how much of it the camera sees (depth buffer of the mesh from that camera, probes kept off the sprite's edge).
2. Each face takes its best view; the labels are smoothed over the face adjacency and tiny pieces are merged, so every chart of the
   atlas is the surface one camera sees without self overlap. The chart's UVs are that camera's screen coordinates, xatlas only
   packs them (use_input_mesh_uvs).
3. Every texel of the packed atlas is looked up in its face's best view (then the next best ones where that view does not see it)
   and the sprite is sampled there. Texels no view sees and the gutters around the charts are filled from the nearest seen texel.

Writes mesh_uv.npz (pos, nrm, uv, tris, vertices split along chart borders), albedo.png and coverage.png (white = sampled
from a sprite, grey = filled) into the out dir.
"""
import json
import sys
from pathlib import Path

import numpy as np
import numba as nb
import xatlas
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cam_fit  # noqa: E402


@nb.njit(cache=True)
def raster_ids(xy, z, order, H, W):
    """Painter's rasterisation of triangles (xy (M,3,2) pixel coords, z (M,3) depth, larger = nearer): id and depth buffers."""
    ids = -np.ones((H, W), np.int32)
    zb = np.full((H, W), -1e9, np.float32)
    for n in range(len(order)):
        i = order[n]
        ax, ay, bx, by, cx, cy = xy[i, 0, 0], xy[i, 0, 1], xy[i, 1, 0], xy[i, 1, 1], xy[i, 2, 0], xy[i, 2, 1]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        x0 = max(int(np.floor(min(ax, bx, cx))), 0)
        x1 = min(int(np.ceil(max(ax, bx, cx))), W - 1)
        y0 = max(int(np.floor(min(ay, by, cy))), 0)
        y1 = min(int(np.ceil(max(ay, by, cy))), H - 1)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / den
                l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / den
                l3 = 1 - l1 - l2
                if l1 >= -0.02 and l2 >= -0.02 and l3 >= -0.02:
                    zz = l1 * z[i, 0] + l2 * z[i, 1] + l3 * z[i, 2]
                    if zz >= zb[y, x]:
                        zb[y, x] = zz
                        ids[y, x] = i
    return ids, zb


@nb.njit(cache=True)
def raster_uv(uv, H, W):
    """Face id and barycentrics of every texel of the atlas (texel centres at i + 0.5)."""
    ids = -np.ones((H, W), np.int32)
    bary = np.zeros((H, W, 3), np.float32)
    for i in range(len(uv)):
        ax, ay, bx, by, cx, cy = uv[i, 0, 0] * W, uv[i, 0, 1] * H, uv[i, 1, 0] * W, uv[i, 1, 1] * H, uv[i, 2, 0] * W, uv[i, 2, 1] * H
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


def vertex_normals(pos, tris):
    fn = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    vn = np.zeros_like(pos)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12), fn


def face_adjacency(tris):
    """(M,3) neighbouring face across edge k (v_k, v_k+1), -1 at open edges and at non manifold edges."""
    M = len(tris)
    e = np.stack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], 1).reshape(-1, 2)
    key = np.sort(e, 1)
    key = key[:, 0].astype(np.int64) * (tris.max() + 1) + key[:, 1]
    order = np.argsort(key, kind="stable")
    ks = key[order]
    adj = -np.ones(M * 3, np.int64)
    same = ks[1:] == ks[:-1]
    first = np.nonzero(same & np.concatenate([[True], ~same[:-1]]) & np.concatenate([~same[1:], [True]]))[0]  # exactly two faces
    a, b = order[first], order[first + 1]
    adj[a], adj[b] = b // 3, a // 3
    return adj.reshape(M, 3)


class View:
    def __init__(self, v, cam, vdir):
        self.v, self.cam = v, cam
        im = np.array(Image.open(f"{vdir}/nu_d{v}.png").convert("RGBA")).astype(np.float32)
        self.H, self.W = im.shape[:2]
        a = im[..., 3:] / 255
        self.rgb = im[..., :3] * a  # premultiplied for filtering
        self.a = a[..., 0]
        # texel probes must sit well inside the sprite
        self.inside = ndimage.distance_transform_edt(self.a > 0.5) >= 6
        self.r, self.u, self.w = cam_fit.basis(cam["az"], cam["el"])

    def project(self, p):
        q = p - np.array([0, self.cam["yoff"], 0])
        x = self.cam["tx"] - 0.5 + self.cam["s"] * (q @ self.r)
        y = self.cam["ty"] - 0.5 - self.cam["s"] * self.cam["ky"] * (q @ self.u)
        return x, y, q @ self.w

    def sample(self, x, y):
        """Bilinear colour and alpha at float pixel coordinates; coordinates outside give alpha 0."""
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = (x - x0)[:, None], (y - y0)[:, None]
        out = np.zeros((len(x), 3), np.float32)
        al = np.zeros(len(x), np.float32)
        for dx, dy, wgt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
            xi, yi = np.clip(x0 + dx, 0, self.W - 1), np.clip(y0 + dy, 0, self.H - 1)
            out += self.rgb[yi, xi] * wgt
            al += self.a[yi, xi] * wgt[:, 0]
        return out / np.maximum(al, 1e-3)[:, None], al


def main():
    a = sys.argv[1:]
    npz, camjson, vdir, out = a[:4]
    size = int(a[a.index("--size") + 1]) if "--size" in a else 2048
    nsm = int(a[a.index("--smooth") + 1]) if "--smooth" in a else 10
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    d = np.load(npz)
    pos, tris = d["pos"].astype(np.float64), d["tris"].astype(np.int64)
    if nsm:
        import pymeshlab
        ms = pymeshlab.MeshSet()
        ms.add_mesh(pymeshlab.Mesh(pos, tris))
        ms.apply_coord_taubin_smoothing(lambda_=0.5, mu=-0.53, stepsmoothnum=nsm)
        pos = ms.current_mesh().vertex_matrix()
    vn, fn = vertex_normals(pos, tris)
    area = np.linalg.norm(fn, axis=1) / 2
    fn = fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    M = len(tris)
    cams = json.load(open(camjson))["cams"]
    views = [View(v, cams[str(v)], vdir) for v in range(16)]
    cen = pos[tris].mean(1)
    # probes: centroid and the three corners pulled towards it
    probes = np.stack([cen] + [cen + (pos[tris[:, k]] - cen) * 0.7 for k in range(3)], 1)  # (M,4,3)

    score = np.zeros((M, 16), np.float32)
    raw = np.zeros((M, 16), np.float32)  # facing only, for faces no camera sees
    for k, vw in enumerate(views):
        x, y, z = vw.project(pos)
        xy = np.stack([x[tris], y[tris]], 2)
        zt = z[tris].astype(np.float32)
        order = np.argsort(zt.mean(1)).astype(np.int64)
        ids, zb = raster_ids(xy.astype(np.float64), zt, order, vw.H, vw.W)
        vw.ids, vw.zb = ids, zb
        px, py, pz = vw.project(probes.reshape(-1, 3))
        xi, yi = np.clip(np.round(px).astype(int), 0, vw.W - 1), np.clip(np.round(py).astype(int), 0, vw.H - 1)
        vis = (np.abs(zb[yi, xi] - pz) < 0.04) & vw.inside[yi, xi]
        vis = vis.reshape(M, 4).mean(1)
        facing = np.clip(fn @ vw.w, 0, 1)
        score[:, k] = facing * vis
        raw[:, k] = facing
        print("view", vw.v, "faces seen", int((vis > 0.5).sum()), flush=True)
    # raw best views per face (kept for the lookup fallbacks) and the smoothed label
    adj = face_adjacency(tris)
    score = score + 0.02 * raw
    lab = score.argmax(1)
    for _ in range(10):
        votes = np.zeros((M, 16), np.float32)
        for e in range(3):
            nb_ = adj[:, e]
            ok = nb_ >= 0
            np.add.at(votes, (np.nonzero(ok)[0], lab[nb_[ok]]), 1.0)
        lab = (score ** 1 + 0.18 * votes).argmax(1)
    # merge pieces below 40 faces into the neighbour label they touch most
    def components(lab):
        comp = -np.ones(M, int)
        n = 0
        for f0 in range(M):
            if comp[f0] >= 0:
                continue
            stack = [f0]
            comp[f0] = n
            while stack:
                f = stack.pop()
                for e in range(3):
                    g = adj[f, e]
                    if g >= 0 and comp[g] < 0 and lab[g] == lab[f]:
                        comp[g] = n
                        stack.append(g)
            n += 1
        return comp, n

    for _ in range(4):
        comp, n = components(lab)
        small = np.nonzero(np.bincount(comp, minlength=n) < 40)[0]
        if len(small) == 0:
            break
        for c in small:
            fs = np.nonzero(comp == c)[0]
            cnt = np.zeros(16)
            for f in fs:
                for e in range(3):
                    g = adj[f, e]
                    if g >= 0 and comp[g] != c:
                        cnt[lab[g]] += 1
            if cnt.sum() > 0:
                lab[fs] = cnt.argmax()
    comp, n = components(lab)
    print("charts", n, "labels used", np.bincount(lab, minlength=16).tolist())
    # split vertices per chart; the uv of a vertex is its screen position in the chart's camera
    pair = tris.astype(np.int64) * n + comp[:, None]
    uniq, inv = np.unique(pair.ravel(), return_inverse=True)
    split_src = uniq // n  # original vertex of every split vertex
    split_comp = uniq % n
    stris = inv.reshape(M, 3)
    suv = np.zeros((len(uniq), 2), np.float32)
    comp_label = np.zeros(n, int)
    comp_label[comp] = lab
    for k, vw in enumerate(views):
        m = comp_label[split_comp] == k
        if m.any():
            x, y, _ = vw.project(pos[split_src[m]])
            suv[m, 0], suv[m, 1] = x / 512, y / 512  # one scale for all views: the packed charts keep their relative pixel size
    atlas = xatlas.Atlas()
    atlas.add_mesh(pos[split_src].astype(np.float32), stris.astype(np.uint32), uvs=(suv * 256).astype(np.float32))
    co = xatlas.ChartOptions()
    co.use_input_mesh_uvs = True
    po = xatlas.PackOptions()
    po.resolution = size
    po.padding = 6
    po.bilinear = True
    po.texels_per_unit = 0
    atlas.generate(co, po)
    vm, idx, uvf = atlas[0]
    print("atlas", len(vm), "vertices", len(idx), "faces", "uv range", uvf.min(0), uvf.max(0))
    src_vert = split_src[vm]
    # xatlas keeps the input face order; check it through the corner vertices
    face_of = np.arange(M)
    assert (np.sort(split_src[vm][idx], 1) == np.sort(tris, 1)).all(), "xatlas changed the face order"
    uvt = uvf[idx]  # (M,3,2) in the atlas order
    ids, bary = raster_uv(uvt.astype(np.float64), size, size)
    cov = ids >= 0
    f_orig = np.where(cov, face_of[np.maximum(ids, 0)], 0)
    P = np.einsum("hwk,hwkc->hwc", bary, pos[tris[f_orig]])  # (H,W,3) positions
    color = np.zeros((size, size, 3), np.float32)
    seen = np.zeros((size, size), bool)
    top = np.argsort(-score, axis=1)[:, :4]
    cand = [lab[:, None]] + [top[:, i:i + 1] for i in range(3)]
    tx_, ty_ = np.nonzero(cov)
    ff = f_orig[tx_, ty_]
    pp = P[tx_, ty_]
    res_col = np.zeros((len(ff), 3), np.float32)
    res_ok = np.zeros(len(ff), bool)
    for c in cand:
        want = ~res_ok
        if not want.any():
            break
        vv = c[ff, 0]
        for k in range(16):
            m = want & (vv == k) & (score[ff, k] > 0.02 if c is not cand[0] else True)
            if not m.any():
                continue
            vw = views[k]
            x, y, z = vw.project(pp[m])
            xi, yi = np.clip(np.round(x).astype(int), 0, vw.W - 1), np.clip(np.round(y).astype(int), 0, vw.H - 1)
            good = (np.abs(vw.zb[yi, xi] - z) < 0.05) & vw.inside[yi, xi]
            col, al = vw.sample(x, y)
            idxs = np.nonzero(m)[0]
            res_col[idxs[good]] = col[good]
            res_ok[idxs[good]] = True
    color[tx_, ty_] = res_col
    seen[tx_, ty_] = res_ok
    print("texels covered by faces", int(cov.sum()), "sampled", int(res_ok.sum()))
    # fill: nearest sampled texel for everything else (holes inside charts and the gutters)
    dist, (iy, ix) = ndimage.distance_transform_edt(~seen, return_indices=True)
    filled = color[iy, ix]
    img = np.clip(filled, 0, 255).astype(np.uint8)
    Image.fromarray(img).save(out / "albedo.png")
    cv = np.where(seen, 255, np.where(cov, 128, 0)).astype(np.uint8)
    Image.fromarray(cv).save(out / "coverage.png")
    # mesh with the split vertices
    nrm = vn[src_vert]
    uv_out = uvf.astype(np.float64)
    np.savez(out / "mesh_uv.npz", pos=pos[src_vert], nrm=nrm, uv=uv_out, tris=idx.astype(np.int64))
    np.savez(out / "mesh_smooth.npz", pos=pos, tris=tris)
    print("vertices", len(src_vert), "tris", len(idx), "-> mesh_uv.npz, albedo.png")


if __name__ == "__main__":
    main()
