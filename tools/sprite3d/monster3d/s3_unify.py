"""Stage 3u: one consistent surface texture from the classic sprite views instead of a patchwork of per-view pieces.

  venv python s3_unify.py stack <bake dir> <cams.json> <views dir> <out.npz> [--sigma 6]
  venv python s3_unify.py align <bake dir> <cams.json> <views dir> <consensus albedo.png> <out flows.npz> [--max 10] [--prev f.npz]
  venv python s3_unify.py stack ... --flow <flows.npz>      (the same stack, sprites read through the flows)
  venv python s3_unify.py make <stack.npz> <bake dir> <out dir> [--only a1,a2,...]
  venv python s3_unify.py measure <bake dir> <cams.json> <views dir> <classic nu dir> <out.json> "<label>=<albedo.png>" [...]

<bake dir> is a project_texture.py output (mesh_uv.npz, mesh_smooth.npz, part.png): the atlas layout is kept, so every texture
written here drops into the same model (same UVs) as the bake's own albedo.png.

`stack` looks every atlas texel up in every sprite view (the x4 upscaled standing frames nu_d<N>.png) and stores per texel and
view: the colour, a low-pass colour (Gaussian --sigma px in the x4 sprite), the facing (smooth normal . view direction), the
depth-test visibility, the distance to the sprite's silhouette and to the nearest depth break of the mesh in that view
(an occlusion border), and the normal in the view's camera frame. Per original mesh vertex it stores the same for the vertex.

`make` writes one albedo per option into <out dir>/<option>/albedo.png (+ weight.png = how much of the texel the views saw):
- a1 feather: every view that sees the texel, weight facing^4 x visibility, faded to 0 over 16 px towards the sprite's
  silhouette and towards occlusion borders (no hard switch where a view stops seeing a texel); unseen texels: nearest texel
  (as round 3 did).
- a2 equalise: a1, but each view's colour is first multiplied by a smooth gain field of its own (per vertex, per channel,
  log domain), solved so that all views agree where they overlap (least squares, mesh Laplacian smoothness, prior gain 1).
- a3 multiband: a2, but split in two bands in each sprite: the low band is blended wide (facing^2), the high band (sprite
  minus its low-pass) comes from nearly the single most direct view (weights normalised to the best view, power 8), so fine
  detail is not averaged away while the base colour has no steps.
- a4 deshade: a3 after dividing each view by the sprite's own baked shading, fitted as one smooth function (2nd order
  spherical harmonics) of the normal in camera space, shared by all views (the light turns with the camera, the monster turns
  under it); then a2's gains are solved again on the deshaded colours.
- a5 robust (--dark T --hi H --keep-part): a3 whose low band weights each view down by e per T levels it is brighter than
  the darkest view there, so a highlight only some views painted (classic's baked light, at a different place in each
  view) drops out, and the high band at H; with --keep-part the bake's part (the cap) keeps a3 with the full high band.
  --soft-vis (any option): the depth test fades over 0.02..0.06 instead of cutting, so view changes do not follow triangles.
- b inpaint (--base a3|a4|a5, default a4): that option plus a 3D push-pull fill: seen colours are splatted into voxel grids of 128^3 down to 4^3 and texels the
  views saw little or not at all take the trilinear estimate, blended in by their seen weight, so there is no flat
  nearest-texel patch and no step at the coverage border.
`measure` writes the numbers of each albedo (see METHOD.md, texture unification): chart-border colour step against the same
step inside charts, hard-step density in the atlas, and render-back error against the x4 and the classic sprites per view.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy import sparse
from scipy.sparse import linalg as sla
from scipy.spatial import cKDTree

import common

sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import project_texture as pt  # noqa: E402
import render_soft  # noqa: E402
import cam_fit  # noqa: E402

SOFT_VIS = [False]
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)
EPS = 10.0                       # log domain offset (sprite levels): dark body pixels are 10..30


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def load_bake(bake: Path):
    d = np.load(bake / "mesh_uv.npz")
    sm = np.load(bake / "mesh_smooth.npz")
    pos, tris = sm["pos"].astype(np.float64), sm["tris"].astype(np.int64)
    pos_s, tris_s, uv = d["pos"].astype(np.float64), d["tris"].astype(np.int64), d["uv"].astype(np.float64)
    dist, orig = cKDTree(pos).query(pos_s)
    assert dist.max() < 1e-6, "split vertices do not sit on the smooth mesh"
    return pos, tris, pos_s, tris_s, uv, orig


def charts(tris_s, nv):
    """Chart id per face: faces that share a split vertex are in one chart."""
    m = len(tris_s)
    rows = np.repeat(np.arange(m), 3)
    g = sparse.coo_matrix((np.ones(3 * m), (rows, tris_s.ravel())), shape=(m, nv)).tocsr()
    adj = g @ g.T
    return sparse.csgraph.connected_components(adj, directed=False)[1]


def sample_img(img, x, y):
    """Bilinear sample of an (H,W[,C]) float image at float pixel coords (pixel centres at integers)."""
    H, W = img.shape[:2]
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    out = 0
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = np.clip(x0 + dx, 0, W - 1), np.clip(y0 + dy, 0, H - 1)
        v = img[yi, xi]
        out = out + (v * (w[:, None] if v.ndim == 2 else w))
    return out


def view_lookup(vw, pos, tris, P, N, sigma, flow=None):
    """Everything `stack` keeps for one view at the points P (normals N). flow (H,W,2) (dy, dx): the sprite is sampled at
    x + flow(x), so a feature the mesh puts a few pixels off is read where the sprite really drew it (`align`)."""
    x, y, z = vw.project(pos)
    xy = np.stack([x[tris], y[tris]], 2)
    zt = z[tris].astype(np.float32)
    ids, zb = pt.raster_ids(xy.astype(np.float64), zt, np.argsort(zt.mean(1)).astype(np.int64), vw.H, vw.W)
    bg = ids < 0
    brk = np.zeros_like(bg)
    for sh in ((0, 1), (1, 0)):
        zs, bs = np.roll(zb, sh, (0, 1)), np.roll(bg, sh, (0, 1))
        e = (np.abs(zb - zs) > 0.06) | (bg != bs)
        brk |= e | np.roll(e, (-sh[0], -sh[1]), (0, 1))
    d_occ = ndi.distance_transform_edt(~brk).astype(np.float32)
    d_sil = ndi.distance_transform_edt(vw.a > 0.5).astype(np.float32)
    ab = ndi.gaussian_filter(vw.a, sigma)
    rb = np.dstack([ndi.gaussian_filter(vw.rgb[..., c], sigma) for c in range(3)])
    px, py, pz = vw.project(P)
    xi, yi = np.clip(np.round(px).astype(int), 0, vw.W - 1), np.clip(np.round(py).astype(int), 0, vw.H - 1)
    vis = (np.abs(zb[yi, xi] - pz) < 0.05) & (vw.a[yi, xi] > 0.5)
    if flow is not None:
        px, py = px + sample_img(flow[..., 1], px, py), py + sample_img(flow[..., 0], px, py)
        xi, yi = np.clip(np.round(px).astype(int), 0, vw.W - 1), np.clip(np.round(py).astype(int), 0, vw.H - 1)
        vis &= vw.a[yi, xi] > 0.5
    col, _ = vw.sample(px, py)
    low = sample_img(rb, px, py) / np.maximum(sample_img(ab, px, py), 1e-3)[:, None]
    ncam = np.stack([N @ vw.r, N @ vw.u, N @ vw.w], 1)
    dz = np.abs(zb[yi, xi] - pz)
    return dict(vis=vis, dz=dz.astype(np.float16), facing=np.clip(N @ vw.w, 0, 1).astype(np.float32), d_sil=d_sil[yi, xi], d_occ=d_occ[yi, xi],
                col=col.astype(np.float16), low=low.astype(np.float16), ncam=ncam.astype(np.float16))


def stack(a):
    bake, cams, vdir, out = Path(a[1]), json.load(open(a[2]))["cams"], a[3], Path(a[4])
    sigma = float(a[a.index("--sigma") + 1]) if "--sigma" in a else 6.0
    flows = np.load(a[a.index("--flow") + 1]) if "--flow" in a else None
    pos, tris, pos_s, tris_s, uv, orig = load_bake(bake)
    tris_o = orig[tris_s]
    vn, _ = pt.vertex_normals(pos, tris)
    size = 2048
    ids, bary = pt.raster_uv(uv[tris_s].astype(np.float64), size, size)
    ty, tx = np.nonzero(ids >= 0)
    f = ids[ty, tx]
    b = bary[ty, tx]
    P = np.einsum("nk,nkc->nc", b, pos[tris_o[f]])
    N = np.einsum("nk,nkc->nc", b, vn[tris_o[f]])
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    views = sorted(cams, key=int)
    res = {k: [] for k in ("vis", "dz", "facing", "d_sil", "d_occ", "col", "low", "ncam")}
    vres = {k: [] for k in res}
    for v in views:
        vw = pt.View(int(v), cams[v], vdir)
        fl = flows["f" + v] if flows is not None else None
        r = view_lookup(vw, pos, tris, P, N, sigma, fl)
        rv = view_lookup(vw, pos, tris, pos, vn, sigma, fl)
        for k in res:
            res[k].append(r[k])
            vres[k].append(rv[k])
        print("view", v, "texels seen", int(r["vis"].sum()), "of", len(P), flush=True)
    np.savez(out, size=size, ty=ty, tx=tx, face=f, bary=b.astype(np.float32), P=P.astype(np.float32),
             N=N.astype(np.float32), views=np.array([int(v) for v in views]), tris_o=tris_o, pos=pos, tris=tris,
             **{k: np.stack(v) for k, v in res.items()}, **{"v_" + k: np.stack(v) for k, v in vres.items()})
    print(out, len(P), "texels")


# ---------------------------------------------------------------- options

def base_weight(S, power, feather=16.0, pre=""):
    if pre + "dz" in S and SOFT_VIS[0]:      # soft depth test: 1 under 0.02, 0 over 0.06 (mesh height 1)
        vis = S[pre + "vis"] | (S[pre + "dz"] < 0.06)
        w = S[pre + "facing"].astype(np.float32) ** power * vis * smoothstep(0.06, 0.02, S[pre + "dz"].astype(np.float32))
        return w * smoothstep(2, feather, S[pre + "d_sil"]) * smoothstep(1, feather, S[pre + "d_occ"])
    w = S[pre + "facing"].astype(np.float32) ** power * S[pre + "vis"]
    return w * smoothstep(2, feather, S[pre + "d_sil"]) * smoothstep(1, feather, S[pre + "d_occ"])


def mesh_edges(tris):
    e = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e = np.unique(np.sort(e, 1), axis=0)
    return e


def solve_gains(S, colv, wv, lam_s=3.0, lam_0=0.3):
    """Per view, per vertex, per channel log gain g so that log(c_i) + g_i == log(c_j) + g_j where views i and j both see a
    vertex. colv (V,nv,3) vertex colours, wv (V,nv) their weights. Returns g (V,nv,3)."""
    V, nv = wv.shape
    lc = np.log(colv.astype(np.float64) + EPS)
    rows, cols, vals, rhs = [], [], [], []
    r = 0
    for i in range(V):
        for j in range(i + 1, V):
            m = np.nonzero((wv[i] > 0.05) & (wv[j] > 0.05))[0]
            if len(m) == 0:
                continue
            w = np.sqrt(wv[i, m] * wv[j, m])
            idx = np.arange(r, r + len(m))
            rows += [idx, idx]
            cols += [i * nv + m, j * nv + m]
            vals += [w, -w]
            rhs.append(-w[:, None] * (lc[i, m] - lc[j, m]))
            r += len(m)
    e = mesh_edges(S["tris"])
    for k in range(V):
        idx = np.arange(r, r + len(e))
        rows += [idx, idx]
        cols += [k * nv + e[:, 0], k * nv + e[:, 1]]
        vals += [np.full(len(e), lam_s), np.full(len(e), -lam_s)]
        rhs.append(np.zeros((len(e), 3)))
        r += len(e)
    idx = np.arange(r, r + V * nv)
    rows.append(idx)
    cols.append(np.arange(V * nv))
    vals.append(np.full(V * nv, lam_0))
    rhs.append(np.zeros((V * nv, 3)))
    r += V * nv
    A = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(r, V * nv))
    B = np.vstack(rhs)
    AtA = (A.T @ A).tocsc()
    lu = sla.splu(AtA)
    g = lu.solve(A.T @ B)
    return g.reshape(V, nv, 3)


def sh9(n):
    x, y, z = n[..., 0], n[..., 1], n[..., 2]
    return np.stack([np.ones_like(x), x, y, z, x * y, y * z, x * z, x * x - y * y, 3 * z * z - 1], -1)


def fit_shading(S, wv, iters=12):
    """log luminance of view k at vertex v = a(v) + s(n_cam), s a 2nd order SH of the camera space normal shared by all
    views. Alternating least squares on the vertices; returns the 9 coefficients (mean of s over the samples = 0)."""
    L = np.log(S["v_low"].astype(np.float64) @ LUMA + EPS)          # (V,nv)
    Y = sh9(S["v_ncam"].astype(np.float64))                          # (V,nv,9)
    w = wv.astype(np.float64)
    m = w > 0.05
    coef = np.zeros(9)
    for _ in range(iters):
        s = Y @ coef
        a_v = (w * (L - s)).sum(0) / np.maximum(w.sum(0), 1e-9)
        res = (L - a_v[None])[m]
        Ym, wm = Y[m], np.sqrt(w[m])
        coef = np.linalg.lstsq(Ym * wm[:, None], res * wm, rcond=None)[0]
        coef[0] -= (w[m] * (Ym @ coef)).sum() / w[m].sum()       # constant goes to the albedo
    s = Y @ coef
    a_v = (w * (L - s)).sum(0) / np.maximum(w.sum(0), 1e-9)
    resid = np.sqrt((w[m] * (L - a_v[None] - s)[m] ** 2).sum() / w[m].sum())
    resid0 = np.sqrt((w[m] * (L - ((w * L).sum(0) / np.maximum(w.sum(0), 1e-9))[None])[m] ** 2).sum() / w[m].sum())
    return coef, {"sh9": [round(float(c), 4) for c in coef], "log_resid_before": round(float(resid0), 4),
                  "log_resid_after": round(float(resid), 4),
                  "shade_factor_p5_p50_p95": [round(float(v), 3) for v in np.exp(np.percentile(s[m], [5, 50, 95]))]}


def make(a):
    S = dict(np.load(a[1]))
    bake, out = Path(a[2]), Path(a[3])
    only = a[a.index("--only") + 1].split(",") if "--only" in a else ["a1", "a2", "a3", "a4", "b"]
    base = a[a.index("--base") + 1] if "--base" in a else "a4"
    dark = float(a[a.index("--dark") + 1]) if "--dark" in a else 20.0
    hi_amp = float(a[a.index("--hi") + 1]) if "--hi" in a else 1.0
    SOFT_VIS[0] = "--soft-vis" in a
    keep_part = "--keep-part" in a       # the part (part.png of the bake: the cap) keeps the plain multiband, full detail
    size = int(S["size"])
    ty, tx = S["ty"], S["tx"]
    col = S["col"].astype(np.float32)
    low = S["low"].astype(np.float32)
    rep = {}
    V = col.shape[0]
    # interpolation of per-vertex fields to texels
    tv = S["tris_o"][S["face"]]                         # (n,3) vertex ids
    bw = S["bary"]

    def at_texels(fv):                                  # fv (V,nv,3) -> (V,n,3)
        return np.einsum("nk,vnkc->vnc", bw, fv[:, tv])

    cov = np.zeros((size, size), bool)
    cov[ty, tx] = True

    def write(name, rgb, wsum, fill="nearest"):
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        img = np.zeros((size, size, 3), np.float32)
        seen = np.zeros((size, size), bool)
        ok = wsum > 1e-3
        img[ty[ok], tx[ok]] = rgb[ok]
        seen[ty[ok], tx[ok]] = True
        if fill == "nearest":
            _, (iy, ix) = ndi.distance_transform_edt(~seen, return_indices=True)
            img = img[iy, ix]
        else:                                           # rgb already holds every covered texel; only the gutters
            img[ty, tx] = rgb
            _, (iy, ix) = ndi.distance_transform_edt(~cov, return_indices=True)
            img = img[iy, ix]
        Image.fromarray(np.clip(img, 0, 255).round().astype(np.uint8)).save(d / "albedo.png")
        wimg = np.zeros((size, size), np.float32)
        wimg[ty, tx] = np.clip(wsum, 0, 1)
        Image.fromarray((wimg * 255).astype(np.uint8)).save(d / "weight.png")
        print("wrote", d, "seen %.1f %%" % (100 * ok.mean()), flush=True)

    def blend(c, w):
        ws = w.sum(0)
        return (c * w[..., None]).sum(0) / np.maximum(ws, 1e-9)[:, None], ws

    W4 = base_weight(S, 4)
    Wv = base_weight(S, 2, pre="v_")                     # vertex weights for the gain and shading fits
    if "a1" in only:
        rgb, ws = blend(col, W4)
        write("a1_feather", rgb, ws)

    # view gains on the raw colours
    G = solve_gains(S, S["v_low"].astype(np.float32), Wv)
    rep["gain_raw"] = gain_stats(S, G, Wv)
    gt = np.exp(at_texels(G)).astype(np.float32)        # (V,n,3)
    if "a2" in only:
        rgb, ws = blend((col + EPS) * gt - EPS, W4)
        write("a2_equalise", rgb, ws)

    def multiband(c, l, g, robust=0.0, hi_amp=hi_amp):
        W2 = base_weight(S, 2)
        lg = (l + EPS) * g - EPS
        if robust:          # a highlight only some views drew drops out of the base: weight falls by e per `robust` levels
            Ll = np.where(W2 > 0, lg @ LUMA, 1e9)
            W2 = W2 * np.exp(-(Ll - Ll.min(0)) / robust)
        lo, ws = blend(lg, W2)
        Wh = (W4 / np.maximum(W4.max(0), 1e-9)) ** 8 * (W4 > 0)
        hi, _ = blend((c - l) * g, Wh)
        return lo + hi_amp * hi, (base_weight(S, 2).sum(0) if robust else ws)

    def fill(name, rgb, ws):
        seen = ws > 1e-3
        P = S["P"]
        full = push_pull_query(P[seen], rgb[seen], np.clip(ws[seen], 0, 1), P)
        k = np.clip(ws / 0.15, 0, 1)[:, None]           # little seen weight -> mostly the surface estimate
        res = k * np.where(seen[:, None], rgb, 0) + (1 - k) * full
        write(name, res, np.ones_like(ws), fill="all")
        rep[name + "_unseen_frac"] = round(float((~seen).mean()), 4)
        rep[name + "_lowweight_frac"] = round(float((ws < 0.15).mean()), 4)

    built = {}

    if "a3" in only or base == "a3":
        built["a3"] = multiband(col, low, gt)
        if "a3" in only:
            write("a3_multiband", *built["a3"])
    if "a5" in only or base == "a5":
        built["a5"] = multiband(col, low, gt, robust=dark)
        if keep_part:
            pm = np.asarray(Image.open(bake / "part.png").convert("L"))[ty, tx].astype(np.float32) / 255
            pm = pm[:, None]
            plain, _ = multiband(col, low, gt, hi_amp=1.0)
            built["a5"] = (pm * plain + (1 - pm) * built["a5"][0], built["a5"][1])
        rep["a5"] = {"dark": dark, "hi": hi_amp, "keep_part": keep_part}
        if "a5" in only:
            write("a5_robust", *built["a5"])
    if "a4" in only or ("b" in only and base == "a4"):
        coef, rep["shading"] = fit_shading(S, Wv)
        sh_t = np.exp(sh9(S["ncam"].astype(np.float32)) @ coef.astype(np.float32))      # (V,n)
        sh_v = np.exp(sh9(S["v_ncam"].astype(np.float64)) @ coef)
        col_d = (col + EPS) / sh_t[..., None] - EPS
        low_d = (low + EPS) / sh_t[..., None] - EPS
        vlow_d = (S["v_low"].astype(np.float64) + EPS) / sh_v[..., None] - EPS
        G2 = solve_gains(S, vlow_d, Wv)
        rep["gain_deshaded"] = gain_stats(S, G2, Wv, vlow_d)
        g2 = np.exp(at_texels(G2)).astype(np.float32)
        built["a4"] = multiband(col_d, low_d, g2)
        if "a4" in only:
            write("a4_deshade", *built["a4"])
    if "b" in only:
        fill("b_inpaint" if base == "a4" else "b_" + base, *built[base])
    (out / "make.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps(rep, indent=1))


def push_pull_query(Ps, cs, ws, Pq, levels=(128, 64, 32, 16, 8, 4), tau=2.0):
    lo = np.minimum(Ps.min(0), Pq.min(0)) - 1e-3
    hi = np.maximum(Ps.max(0), Pq.max(0)) + 1e-3
    est = None
    for n in levels[::-1]:
        qs = (Ps - lo) / (hi - lo) * (n - 1)
        qi = np.clip(np.round(qs).astype(int), 0, n - 1)
        lin = (qi[:, 0] * n + qi[:, 1]) * n + qi[:, 2]
        cnt = np.bincount(lin, ws, n ** 3).reshape(n, n, n)
        q = ((Pq - lo) / (hi - lo) * (n - 1)).T
        cw = ndi.map_coordinates(cnt, q, order=1, mode="nearest")
        cs_ = np.stack([ndi.map_coordinates(np.bincount(lin, ws * cs[:, c], n ** 3).reshape(n, n, n), q, order=1,
                                            mode="nearest") for c in range(3)], 1)
        e = cs_ / np.maximum(cw, 1e-9)[:, None]
        al = np.clip(cw / tau, 0, 1)[:, None]
        est = e if est is None else al * e + (1 - al) * est
    return est


def gain_stats(S, G, Wv, vlow=None):
    """Mean absolute log difference between view pairs at shared vertices, before and after the gains."""
    lc = np.log((S["v_low"] if vlow is None else vlow).astype(np.float64) + EPS)
    V = lc.shape[0]
    b, aft, n = 0.0, 0.0, 0
    for i in range(V):
        for j in range(i + 1, V):
            m = (Wv[i] > 0.05) & (Wv[j] > 0.05)
            if m.any():
                b += np.abs(lc[i, m] - lc[j, m]).sum()
                aft += np.abs(lc[i, m] + G[i, m] - lc[j, m] - G[j, m]).sum()
                n += m.sum() * 3
    return {"pair_logdiff_before": round(b / n, 4), "pair_logdiff_after": round(aft / n, 4),
            "gain_p5_p95": [round(float(v), 3) for v in np.exp(np.percentile(G, [5, 95]))]}


# ---------------------------------------------------------------- measures

def bilinear_tex(tex, uvp):
    H, W = tex.shape[:2]
    return sample_img(tex, uvp[:, 0] * W - 0.5, uvp[:, 1] * H - 0.5)


def border_steps(bake, tex, nudge=2.0):
    """Colour step across chart borders and across interior edges, both sampled `nudge` texels inside each face."""
    pos, tris, pos_s, tris_s, uv, orig = load_bake(bake)
    ch = charts(tris_s, len(pos_s))
    tris_o = orig[tris_s]
    H = tex.shape[0]
    e = np.vstack([tris_o[:, [0, 1]], tris_o[:, [1, 2]], tris_o[:, [2, 0]]])
    fid = np.tile(np.arange(len(tris_o)), 3)
    corner = np.repeat(np.arange(3), len(tris_o))
    key = np.sort(e, 1)
    k = key[:, 0] * (len(pos) + 1) + key[:, 1]
    order = np.argsort(k, kind="stable")
    ks = k[order]
    same = np.nonzero(ks[1:] == ks[:-1])[0]
    f1, f2 = fid[order[same]], fid[order[same + 1]]
    c1, c2 = corner[order[same]], corner[order[same + 1]]

    def side(f, c):
        ua = uv[tris_s[f, c]]
        ub = uv[tris_s[f, (c + 1) % 3]]
        mid = (ua + ub) / 2
        cen = uv[tris_s[f]].mean(1)
        d = cen - mid
        dn = np.linalg.norm(d, axis=1, keepdims=True)
        return mid + d / np.maximum(dn, 1e-12) * np.minimum(dn, nudge / H)

    s1, s2 = bilinear_tex(tex, side(f1, c1)), bilinear_tex(tex, side(f2, c2))
    d = np.abs(s1 - s2).mean(1)
    dl = np.abs(s1 @ LUMA - s2 @ LUMA)
    b = ch[f1] != ch[f2]
    return {"border_edges": int(b.sum()), "border_dRGB_mean": round(float(d[b].mean()), 2),
            "border_dL_p90": round(float(np.percentile(dl[b], 90)), 2),
            "interior_dRGB_mean": round(float(d[~b].mean()), 2),
            "border_over_interior": round(float(d[b].mean() / max(d[~b].mean(), 1e-6)), 2)}


def hard_steps(bake, tex, thr=6.0):
    """Share of chart texels whose luminance changes by more than thr per texel (sigma 0.7): the patch outlines."""
    pos, tris, pos_s, tris_s, uv, orig = load_bake(bake)
    ids, _ = pt.raster_uv(uv[tris_s].astype(np.float64), tex.shape[0], tex.shape[1])
    m = ndi.binary_erosion(ids >= 0, iterations=3)
    L = ndi.gaussian_filter(tex @ LUMA, 0.7)
    gy, gx = np.gradient(L)
    g = np.hypot(gx, gy)
    return {"hard_step_frac": round(float((g[m] > thr).mean()), 4), "grad_p99": round(float(np.percentile(g[m], 99)), 2)}


def renderback(bake, cams, vdir, cdir, tex):
    d = np.load(bake / "mesh_uv.npz")
    out = {}
    for v in sorted(cams, key=int):
        cam = cams[v]
        S = max(cam["w"], cam["h"]) + 64
        r, u, _ = cam_fit.basis(cam["az"], cam["el"])
        c = (np.array([0, cam["yoff"], 0]) + (S / 2 - cam["tx"] - 32) / cam["s"] * r
             + (cam["ty"] + 32 - S / 2) / (cam["s"] * cam["ky"]) * u)
        img = render_soft.render(d["pos"], d["tris"], cam["az"], cam["el"], S, cam["s"], c, uv=d["uv"], tex=tex,
                                 ky=cam["ky"], lit=False)[32:32 + cam["h"], 32:32 + cam["w"]].astype(np.float32)
        spr = np.asarray(Image.open(Path(vdir) / ("nu_d%s.png" % v)).convert("RGBA")).astype(np.float32)
        m = (img[..., 3] > 127) & (spr[..., 3] > 127)
        e4 = float(np.abs(img[..., :3] - spr[..., :3])[m].mean())
        cl = np.asarray(Image.open(Path(cdir) / ("d%s_f00.png" % v)).convert("RGBA")).astype(np.float32)
        small = np.asarray(Image.fromarray(img.astype(np.uint8)).resize(cl.shape[1::-1], Image.BOX)).astype(np.float32)
        m1 = (small[..., 3] > 127) & (cl[..., 3] > 127)
        e1 = float(np.abs(small[..., :3] - cl[..., :3])[m1].mean())
        out[v] = [round(e4, 1), round(e1, 1)]
    return {"renderback_mae_x4_1x": out, "mean_x4": round(float(np.mean([x[0] for x in out.values()])), 2),
            "mean_1x": round(float(np.mean([x[1] for x in out.values()])), 2)}


def render_view(d, cam, tex):
    S = max(cam["w"], cam["h"]) + 64
    r, u, _ = cam_fit.basis(cam["az"], cam["el"])
    c = (np.array([0, cam["yoff"], 0]) + (S / 2 - cam["tx"] - 32) / cam["s"] * r
         + (cam["ty"] + 32 - S / 2) / (cam["s"] * cam["ky"]) * u)
    return render_soft.render(d["pos"], d["tris"], cam["az"], cam["el"], S, cam["s"], c, uv=d["uv"], tex=tex, ky=cam["ky"],
                              lit=False)[32:32 + cam["h"], 32:32 + cam["w"]].astype(np.float32)


def align(a):
    """Per view a dense flow from the render of a consensus albedo to the sprite (TV-L1, scikit-image), clipped to
    --max px and smoothed, so the next `stack --flow` reads each sprite where its features are, not where the mesh says."""
    from skimage.registration import optical_flow_tvl1
    bake, cams, vdir, tex_p, out = Path(a[1]), json.load(open(a[2]))["cams"], Path(a[3]), a[4], Path(a[5])
    mx = float(a[a.index("--max") + 1]) if "--max" in a else 10.0
    prev = np.load(a[a.index("--prev") + 1]) if "--prev" in a else None
    d = np.load(bake / "mesh_uv.npz")
    tex = np.asarray(Image.open(tex_p).convert("RGB")).astype(np.float32)
    res, rep = {}, {}
    bgc = 40.0
    for v in sorted(cams, key=int):
        ren = render_view(d, cams[v], tex)
        spr = np.asarray(Image.open(vdir / ("nu_d%s.png" % v)).convert("RGBA")).astype(np.float32)
        if prev is not None:      # compose with the earlier flow: warp the sprite by it first
            f0 = prev["f" + v]
            yy, xx = np.mgrid[0:spr.shape[0], 0:spr.shape[1]].astype(np.float32)
            spr = np.dstack([ndi.map_coordinates(spr[..., c], [yy + f0[..., 0], xx + f0[..., 1]], order=1, mode="nearest")
                             for c in range(4)])
        def gray(im):
            al = im[..., 3] / 255
            return ((im[..., :3] @ LUMA) * al + bgc * (1 - al)) / 255
        g0, g1 = gray(ren), gray(spr)
        fy, fx = optical_flow_tvl1(g0, g1, attachment=8, tightness=0.3, num_warp=8, num_iter=30)
        fl = np.stack([fy, fx], -1)
        fl = np.stack([ndi.gaussian_filter(fl[..., c], 3) for c in range(2)], -1)
        m = np.linalg.norm(fl, axis=-1, keepdims=True)
        fl = fl * np.minimum(1, mx / np.maximum(m, 1e-6))
        both = (ren[..., 3] > 127) & (spr[..., 3] > 127)
        if prev is not None:
            f0 = prev["f" + v]
            yy, xx = np.mgrid[0:fl.shape[0], 0:fl.shape[1]].astype(np.float32)
            fl = fl + np.stack([ndi.map_coordinates(f0[..., c], [yy + fl[..., 0], xx + fl[..., 1]], order=1, mode="nearest")
                                for c in range(2)], -1)
        res["f" + v] = fl.astype(np.float32)
        mag = np.linalg.norm(fl, axis=-1)[both]
        rep[v] = [round(float(np.percentile(mag, p)), 2) for p in (50, 90, 99)]
        print("view", v, "flow px p50/p90/p99", rep[v], flush=True)
    np.savez(out, **res)
    Path(str(out) + ".json").write_text(json.dumps(rep, indent=1), encoding="utf-8")


def measure(a):
    bake, cams, vdir, cdir, outp = Path(a[1]), json.load(open(a[2]))["cams"], a[3], a[4], Path(a[5])
    res = json.loads(outp.read_text()) if outp.is_file() else {}
    for spec in a[6:]:
        if "=" not in spec:
            continue
        label, path = spec.split("=", 1)
        tex = np.asarray(Image.open(path).convert("RGB").resize((2048, 2048), Image.LANCZOS)).astype(np.float32)
        r = {"file": path, **border_steps(bake, tex), **hard_steps(bake, tex)}
        if not label.endswith("_relit"):
            r.update(renderback(bake, cams, vdir, cdir, tex))
        res[label] = r
        print(label, json.dumps(r), flush=True)
        outp.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    args = sys.argv[1:]
    {"stack": stack, "make": make, "measure": measure, "align": align}[args[0]](args)
