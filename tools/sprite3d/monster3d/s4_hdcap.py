"""Round 18: the Glowing Fungus cap designed and modelled from scratch (it replaces the donor-derived cap).

The cap keeps the old cap's frame: its centre, tilt (up axis) and outline (radius per angle, low harmonics), so it sits
and moves as before (it stays rigid on `jaw`, the round-16 clips move it). Everything else is new:

- shape: one closed grid. Each angle k is a ray from the cap's centre; the profile runs from the top centre over a
  flattened dome, a thick rolled rim (the bead curls under), then the underside runs from the bead's inner edge to the
  stalk's apex S (off centre, where the stalk meets the cap), rising into a shallow gill chamber. Low = game mesh
  (one resolution per LOD, all from the same parameters, so one bake serves every LOD); high = bake source with the
  sculpt detail: gills (with short gills between), rim lumps and radial creases, warts in the pale blotches, fine pores.
- UVs: two discs in the atlas. The top (centre to the rim's outermost point) and the underside (S to the same point),
  radius in the disc = arc length along the profile, angle = the ray's angle; no seam except the rim's equator.
- paint (high mesh vertex colours, baked): classic's layout, a dark navy/black centre with navy mottles and a few blue
  specks, green flecks at the inner edge of a bright blue ring, pale-blue/white blotches growing toward the rim, a few
  dark blotches on the bead; the underside dark blue-grey gills with lighter crests. Glow (the cap's glow mask) on the
  ring, the pale blotches and the green flecks; roughness moist on top, dry under.

  design <src stage> W [--cap cap.json]   cap_frame.json, cap_lod{k}.npz (pos, nrm, uv v down, tris), cap_high.npz
                                          (V, T, col, glow, rough), cap_texels.npy, and W/occupied.npy updated (the
                                          atlas the body may use: everything but the strip and the cap's discs)
  (blender) hdcap_bl.py bake W            capbake_{nrm,alb,aux,ao}.png
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage as nd
from scipy.spatial import cKDTree

import s4_hdbody as hb
import s4_procbody as pb

opt = pb.opt
SIZE = 2048

CAP = {
    # profile: (d / R, h) control points from the top centre over the bead to its inner edge under the rim; the
    # point named by "equator" is the rim's outermost (the UV seam between the two discs)
    "profile": [[0.0, 0.86], [0.3, 0.83], [0.58, 0.69], [0.78, 0.48], [0.9, 0.26], [0.97, 0.04], [1.0, -0.17],
                [0.975, -0.38], [0.92, -0.51], [0.85, -0.57]],
    "equator": 6,
    "R_scale": 1.0, "harmonics": 3,            # outline: the old cap's radius per angle, low harmonics
    "wobble": [0.035, 5, 9],                   # rim wobble: amplitude (of R), harmonics lo..hi
    "tilt_h": 0.05,                            # lopsided dome: height factor 1 + a cos(theta - phase)
    "tilt_phase": 40,
    "h_stalk": -0.64,                          # underside at the stalk apex
    "gill_rise": 0.17,                         # how far the gill chamber rises (mid underside)
    "lump_low": [0.045, 1.1],                  # big lumps in the low mesh: amplitude, frequency
    "res": [[128, 36], [96, 24], [64, 16], [40, 10], [28, 7]],
    "res_high": [2048, 700],
    "uv_top": [8, 920, 560], "uv_under": [1176, 1176, 432],   # disc: left, top, radius (px in the 2048 atlas)
    # sculpt (high only)
    "gills": 150, "gill_amp": 0.075, "gill_w": 0.22, "short_from": 0.45,
    "crease": [0.022, 46], "rim_lump": [0.05, 2.6], "wart": [0.016, 4.2], "pore": [0.007, 26.0],
    "fine": [0.004, 9.0],
}

PAINT = {
    "centre": [6, 8, 22], "navy": [20, 30, 98], "speck": [40, 82, 205],
    "green": [24, 112, 66], "blue": [34, 88, 230], "blue_dk": [22, 56, 170],
    "pale": [140, 196, 226], "pale_core": [212, 236, 242], "dark_blot": [10, 14, 38],
    "gill": [20, 26, 50], "gill_crest": [52, 66, 118], "under_rim": [32, 74, 190], "apex": [14, 16, 26],
    "c_edge": [0.57, 0.05],                    # navy centre boundary (d / R) and its noise
    "pale_lo": 0.62, "pale_cov": [0.10, 0.55], # pale blotch coverage from the ring's inner edge to the rim
    "green_cov": 0.34, "blot_cov": 0.06, "speck_cov": 0.05,
    "glow": {"ring": 0.12, "pale": 0.8, "core": 1.0, "green": 0.3, "speck": 0.25},
    "rough": {"top": 0.55, "pale": 0.45, "centre": 0.62, "under": 0.85},
}


# ------------------------------------------------------------------------------------------------------------- frame
def old_frame(src):
    z = np.load(Path(src) / "skinned_lod0.npz")
    bones = [str(x) for x in z["bones"]]
    c = (z["bone_idx"][:, 0] == bones.index("jaw")) & (z["weights"][:, 0] > 0.99)
    p = z["pos"][c]
    cen = p.mean(0)
    _u, _s, vt = np.linalg.svd(p - cen, full_matrices=False)
    up = vt[2] * np.sign(vt[2][1])
    ex = np.cross([0.0, 0.0, 1.0], up)
    ex /= np.linalg.norm(ex)
    ez = np.cross(ex, up)
    q = np.c_[(p - cen) @ ex, (p - cen) @ up, (p - cen) @ ez]
    th = np.arctan2(q[:, 2], q[:, 0])
    rho = np.hypot(q[:, 0], q[:, 2])
    nb = 72
    b = ((th + np.pi) / (2 * np.pi) * nb).astype(int) % nb
    R = np.array([rho[b == i].max() if (b == i).any() else np.nan for i in range(nb)])
    R = np.where(np.isnan(R), np.nanmean(R), R)
    return {"cen": cen.tolist(), "up": up.tolist(), "ex": ex.tolist(), "ez": ez.tolist(), "R_bins": R.tolist(),
            "h_top": float(q[:, 1].max()), "h_bottom": float(q[:, 1].min()), "verts": int(c.sum())}


def outline(fr, C, th):
    """R(theta): the old outline's low harmonics, scaled, plus a rim wobble."""
    R = np.array(fr["R_bins"])
    nb = len(R)
    tb = -np.pi + (np.arange(nb) + 0.5) * 2 * np.pi / nb
    out = np.full_like(th, R.mean())
    for h in range(1, C["harmonics"] + 1):
        a, b = 2 * np.mean(R * np.cos(h * tb)), 2 * np.mean(R * np.sin(h * tb))
        out += a * np.cos(h * th) + b * np.sin(h * th)
    amp, lo, hi = C["wobble"]
    rng = np.random.default_rng(7)
    wob = np.zeros_like(th)
    for h in range(int(lo), int(hi) + 1):
        wob += rng.normal() * np.cos(h * th + rng.uniform(0, 2 * np.pi)) / h
    wob /= max(np.abs(wob).max(), 1e-9)
    return out * C["R_scale"] * (1 + amp * wob)


# ------------------------------------------------------------------------------------------------------------- shape
def catmull(P, n_per=64):
    P = np.asarray(P, float)
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out, seg = [], []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        t = np.linspace(0, 1, n_per, endpoint=False)[:, None]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
        seg.append(np.full(n_per, i - 1))
    out.append(P[-1:])
    seg.append([len(P) - 1])
    return np.vstack(out), np.concatenate(seg)


def profile_rows(C, R_nom, ns, kappa=0.35):
    """sample positions along the whole profile: (n_rows) values of the curve parameter, shared by every angle.
    Returns (rows: list of ('top', curve index) or ('under', u)), the equator row, arc lengths (nominal, top part from
    the centre and underside part from S)."""
    curve, seg = catmull(C["profile"], 96)
    d = curve.copy()
    d[:, 0] *= R_nom
    ds = np.linalg.norm(np.diff(d, axis=0), axis=1)
    tang = np.diff(d, axis=0)
    ang = np.unwrap(np.arctan2(tang[:, 1], tang[:, 0]))
    dturn = np.abs(np.diff(np.r_[ang[0], ang]))
    w_curve = np.r_[0, np.cumsum(ds + kappa * dturn)]
    eq_i = int(np.nonzero(seg == C["equator"])[0][0])
    # underside: straight run (nominal length R_nom * (last d) - stalk offset ~ 1.3), weight by length
    L_under = 0.75 * R_nom
    total = w_curve[-1] + L_under
    s = np.linspace(0, total, ns + 1)[1:]          # row 0 = the top pole itself (a fan), rows 1..ns
    rows = []
    for v in s:
        if v <= w_curve[-1]:
            rows.append(("top", float(np.interp(v, w_curve, np.arange(len(curve))))))
        else:
            rows.append(("under", float((v - w_curve[-1]) / L_under)))
    rows[-1] = ("under", 1.0)
    # snap the row nearest to the equator onto it
    ci = np.array([r[1] if r[0] == "top" else 1e9 for r in rows])
    j = int(np.argmin(np.abs(ci - eq_i)))
    rows[j] = ("top", float(eq_i))
    return rows, j, curve


def build_grid(fr, C, nth, ns, lump=True):
    """the cap as a grid in the cap's local frame: X (nth, ns+1, 3) local (x, h, z); rows 0 = top pole, ns = S pole.
    Also per-vertex info for paint/sculpt: theta, region ('top' 0 / 'under' 1), dn (d / R on top), u (underside),
    arc length from the pole of the vertex's disc."""
    th = -np.pi + np.arange(nth) * 2 * np.pi / nth
    R = outline(fr, C, th)
    rows, eq_row, curve = profile_rows(C, float(np.mean(R)), ns)
    curve_i = np.arange(len(curve))
    S = np.array(fr["S_local"], float)          # stalk apex (x, z) in the cap frame
    hfac = 1 + C["tilt_h"] * np.cos(th - np.radians(C["tilt_phase"]))
    last = curve[-1]
    X = np.zeros((nth, len(rows) + 1, 3))
    reg = np.zeros((nth, len(rows) + 1), int)
    dn = np.zeros((nth, len(rows) + 1))
    uu = np.zeros((nth, len(rows) + 1))
    dirs = np.c_[np.cos(th), np.sin(th)]
    X[:, 0] = [0, curve[0, 1], 0]
    for r, (kind, v) in enumerate(rows, start=1):
        if kind == "top":
            p = np.array([np.interp(v, curve_i, curve[:, 0]), np.interp(v, curve_i, curve[:, 1])])
            xz = dirs * (p[0] * R)[:, None]
            hf = 1 + (hfac - 1) * min(1.0, p[0] / 0.45)
            h = p[1] * np.where(p[1] > 0, hf, 1.0)
            X[:, r] = np.c_[xz[:, 0], h, xz[:, 1]]
            dn[:, r] = p[0]
        else:
            P0 = dirs * (last[0] * R)[:, None]
            xz = P0 + v * (S[None] - P0)
            h = last[1] + v * (C["h_stalk"] - last[1]) + C["gill_rise"] * np.sin(np.pi * v) ** 0.8
            X[:, r] = np.c_[xz[:, 0], np.full(nth, h), xz[:, 1]]
            reg[:, r] = 1
            uu[:, r] = v
            dn[:, r] = last[0] * (1 - v)
    reg[:, 0] = 0
    if lump:
        G = local_to_game(fr, X.reshape(-1, 3))
        L = hb.fbm(G * C["lump_low"][1], 3, 101) * C["lump_low"][0]
        nrm = grid_normals(X)
        X = X + (L.reshape(X.shape[:2]))[..., None] * nrm * (1 - 0.6 * reg[..., None])
    return {"X": X, "th": th, "R": R, "reg": reg, "dn": dn, "u": uu, "eq_row": eq_row, "rows": rows}


def grid_normals(X):
    """outward normals of the closed grid (central differences, poles straight up / toward the underside)."""
    nth, nr, _ = X.shape
    dth = np.roll(X, -1, 0) - np.roll(X, 1, 0)
    ds = np.zeros_like(X)
    ds[:, 1:-1] = X[:, 2:] - X[:, :-2]
    ds[:, 0] = X[:, 1] - X[:, 0]
    ds[:, -1] = X[:, -1] - X[:, -2]
    n = np.cross(ds, dth)
    ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = n / np.maximum(ln, 1e-12)
    n[:, 0] = [0, 1, 0]
    n[:, -1] = n[:, -2].mean(0) / max(np.linalg.norm(n[:, -2].mean(0)), 1e-9)
    # outward: the top pole's normal points up; flip the whole grid if the first ring disagrees
    if (n[:, 1, 1]).mean() < 0:
        n = -n
        n[:, 0] = [0, 1, 0]
    return n


def grid_tris(nth, nr):
    """triangles of the closed grid: fans at the poles (row 0 and row nr-1 are poles, one vertex each after welding)."""
    idx = np.arange(nth * nr).reshape(nth, nr)
    T = []
    k1 = np.roll(np.arange(nth), -1)
    # top fan (pole = idx[0, 0])
    T.append(np.c_[np.full(nth, idx[0, 0]), idx[k1, 1], idx[:, 1]])
    for r in range(1, nr - 2):
        a, b = idx[:, r], idx[:, r + 1]
        a1, b1 = idx[k1, r], idx[k1, r + 1]
        T.append(np.c_[a, a1, b])
        T.append(np.c_[a1, b1, b])
    T.append(np.c_[idx[:, nr - 2], idx[k1, nr - 2], np.full(nth, idx[0, nr - 1])])
    return np.vstack(T)


def local_to_game(fr, X):
    cen, ex, up, ez = (np.array(fr[k], float) for k in ("cen", "ex", "up", "ez"))
    return cen + X[:, 0:1] * ex + X[:, 1:2] * up + X[:, 2:3] * ez


def vec_to_game(fr, N):
    ex, up, ez = (np.array(fr[k], float) for k in ("ex", "up", "ez"))
    return N[:, 0:1] * ex + N[:, 1:2] * up + N[:, 2:3] * ez


def mesh_from_grid(fr, g, C, with_uv=True):
    """flat arrays (pos game, nrm game, uv v down, tris) with the poles welded and the equator split for the UV seam."""
    X = g["X"]
    nth, nr, _ = X.shape
    N = grid_normals(X)
    T = grid_tris(nth, nr)
    pos = local_to_game(fr, X.reshape(-1, 3))
    nrm = vec_to_game(fr, N.reshape(-1, 3))
    # area-weighted vertex normals on the welded mesh (poles: every copy of the pole is one vertex)
    weld = np.arange(nth * nr).reshape(nth, nr)
    weld[:, 0] = weld[0, 0]
    weld[:, -1] = weld[0, -1]
    weld = weld.ravel()
    Tw = weld[T]
    Tw = Tw[(Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 0] != Tw[:, 2])]
    vn = hb.vnormals(pos, Tw)
    nrm = vn[weld]
    if not with_uv:
        keep = np.unique(Tw)
        rm = -np.ones(len(pos), int)
        rm[keep] = np.arange(len(keep))
        return pos[keep], nrm[keep], None, rm[Tw]
    uv = disc_uv(g, C).reshape(-1, 2)
    # split at the equator: rows <= eq_row are top-disc vertices; the equator row gets a second copy (underside disc)
    eq = g["eq_row"]
    ridx = np.tile(np.arange(nr), nth)
    uv_under_eq = disc_uv(g, C, under_at_eq=True).reshape(-1, 2)
    dup = np.nonzero(ridx == eq)[0]
    base = len(pos)
    newid = np.arange(len(pos))
    pos2 = np.vstack([pos, pos[dup]])
    nrm2 = np.vstack([nrm, nrm[dup]])
    uv2 = np.vstack([uv, uv_under_eq[dup]])
    dmap = -np.ones(len(pos), int)
    dmap[dup] = base + np.arange(len(dup))
    # triangles touching rows > eq use the underside copy of equator vertices
    tri_under = (ridx[T] > eq).any(1)
    T2 = Tw.copy()
    Tsrc = T[(weld[T][:, 0] != weld[T][:, 1]) & (weld[T][:, 1] != weld[T][:, 2]) & (weld[T][:, 0] != weld[T][:, 2])]
    tri_under = (ridx[Tsrc] > eq).any(1)
    for c in range(3):
        on_eq = (ridx[Tsrc[:, c]] == eq) & tri_under
        T2[on_eq, c] = dmap[Tsrc[on_eq, c]]
    del newid
    keep = np.unique(T2)
    rm = -np.ones(len(pos2), int)
    rm[keep] = np.arange(len(keep))
    return pos2[keep], nrm2[keep], uv2[keep], rm[T2]


def disc_uv(g, C, under_at_eq=False):
    """(nth, nr, 2) atlas uv (v down) of every grid vertex: top disc for rows <= eq_row, underside disc beyond."""
    X = g["X"]
    nth, nr, _ = X.shape
    eq = g["eq_row"]
    # arc length along each ray: from the top pole to the equator, and from the S pole back to the equator
    seg = np.linalg.norm(np.diff(X, axis=1), axis=-1)
    ac = np.c_[np.zeros(nth), np.cumsum(seg, 1)]
    top_len = ac[:, eq]
    under_from_S = ac[:, -1:] - ac
    under_len = under_from_S[:, eq]
    lt, tt, rt = C["uv_top"]
    lu, tu, ru = C["uv_under"]
    th = g["th"][:, None]
    out = np.zeros((nth, nr, 2))
    r_top = np.clip(ac / top_len[:, None], 0, 1) * (rt - 3)
    r_und = np.clip(under_from_S / under_len[:, None], 0, 1) * (ru - 3)
    top = np.stack([lt + rt + r_top * np.cos(th), tt + rt + r_top * np.sin(th)], -1)
    # underside seen from below: mirror the angle so the disc is not flipped against the surface
    und = np.stack([lu + ru + r_und * np.cos(-th), tu + ru + r_und * np.sin(-th)], -1)
    ridx = np.arange(nr)[None, :, None]
    if under_at_eq:
        out = np.where(ridx >= eq, und, top)
    else:
        out = np.where(ridx <= eq, top, und)
    return out / SIZE


# ------------------------------------------------------------------------------------------------------------- sculpt
def worley(P, freq, seed, k=2):
    """distances to the nearest k jittered feature points (cells of size 1 / freq), P (n, 3)."""
    Q = P * freq
    lo, hi = np.floor(Q.min(0)) - 1, np.ceil(Q.max(0)) + 2
    rng = np.random.default_rng(seed)
    grid = np.stack(np.meshgrid(*[np.arange(a, b) for a, b in zip(lo, hi)], indexing="ij"), -1).reshape(-1, 3)
    pts = grid + rng.uniform(0, 1, grid.shape)
    d, i = cKDTree(pts).query(Q, k=k, workers=-1)
    return d, i


def sculpt(fr, g, C, Xg, Ng):
    """displacement along the normal (game units) for the high grid; Xg/Ng game-space positions/normals (flat)."""
    nth, nr = g["reg"].shape
    reg = g["reg"].ravel()
    dn = g["dn"].ravel()
    u = g["u"].ravel()
    th = np.repeat(g["th"], nr)
    disp = np.zeros(len(Xg))
    aux = {}
    # gills: thin ridges hanging down from the underside (displaced along -normal = into the chamber's opening),
    # every other one short (starts at u < 1 - short_from)
    Ng_ = int(C["gills"])
    ph = (th + np.pi) / (2 * np.pi) * Ng_
    fr_ = ph - np.floor(ph)
    ridge = np.exp(-((fr_ - 0.5) / C["gill_w"]) ** 2 * 3)
    gi = np.floor(ph).astype(int)
    short = (gi % 2 == 1) & (u > 1 - C["short_from"])
    env = np.clip(u / 0.12, 0, 1) * np.clip((1 - u) / 0.18, 0, 1)
    gill = (reg == 1) * ridge * env * (~short)
    wav = 1 + 0.25 * hb.fbm(Xg * 3.0, 2, 211)
    disp += C["gill_amp"] * gill * wav
    aux["gill"] = gill
    # rim: radial creases and lumps on the bead and the outer top
    rimw = np.clip((dn - 0.8) / 0.12, 0, 1) * (reg == 0) + (reg == 1) * np.clip(1 - u / 0.2, 0, 1)
    ca, cf = C["crease"]
    wob = hb.fbm(Xg * 1.6, 2, 223)
    cr = 1 - np.abs(np.sin(th * cf / 2 + 2.5 * wob))
    disp -= ca * rimw * cr ** 6 * np.clip(0.55 + 0.9 * hb.fbm(Xg * 2.1, 2, 225), 0, 1.3)
    la, lf = C["rim_lump"]
    disp += la * rimw * hb.fbm(Xg * lf, 3, 227)
    # warts: rounded bumps in cells over the ring (more toward the rim), the pale blotches sit on them
    wa, wf = C["wart"]
    d, _i = worley(Xg, wf, 229, 1)
    wart = np.clip(1 - d / 0.45, 0, 1) ** 2 * (reg == 0) * np.clip((dn - 0.55) / 0.15, 0, 1)
    disp += wa * wart
    aux["wart"] = wart
    # pores: small pits all over the top, fewer on the underside
    pa, pf = C["pore"]
    d, _i = worley(Xg, pf, 233, 1)
    pit = np.clip(1 - d / 0.3, 0, 1) ** 2
    disp -= pa * pit * np.where(reg == 0, 1.0, 0.3)
    aux["pore"] = pit
    fa, ff = C["fine"]
    disp += fa * hb.fbm(Xg * ff, 3, 239)
    return disp, aux


# ------------------------------------------------------------------------------------------------------------- paint
def smooth(x, lo, hi):
    t = np.clip((x - lo) / np.maximum(hi - lo, 1e-9), 0, 1)
    return t * t * (3 - 2 * t)


def blobs(Xg, freq, seed, radius, warp=0.12):
    """round soft blobs: 1 at a feature point, 0 beyond radius (in cells), each blob its own random strength."""
    w = np.stack([hb.fbm(Xg * 2.7, 2, seed + k) for k in (11, 12, 13)], 1)
    d, i = worley(Xg + warp * w, freq, seed, 1)
    rng = np.random.default_rng(seed + 1)
    s = rng.uniform(0.4, 1.0, int(i.max()) + 1)[i]
    return np.clip(1 - d / radius, 0, 1) ** 0.7 * s


def mix(col, c, t):
    t = np.asarray(t, float)[:, None]
    return col * (1 - t) + np.asarray(c, float)[None] * t


def paint(fr, g, C, Pt, Xg, aux):
    nth, nr = g["reg"].shape
    reg = g["reg"].ravel()
    dn = g["dn"].ravel()
    u = g["u"].ravel()
    lin = hb.lin
    n = len(Xg)
    top = (reg == 0).astype(float)
    und = reg == 1
    # the navy centre: a ragged edge
    ce, cn = Pt["c_edge"]
    edge = ce + cn * hb.fbm(Xg * 1.4, 3, 301) + 0.025 * hb.fbm(Xg * 6.0, 2, 302)
    centre = smooth(edge - dn, -0.012, 0.012) * top
    m1 = hb.fbm(Xg * 2.4, 3, 303)
    m2 = hb.fbm(Xg * 5.0, 3, 305)
    # ring: blue, mottled darker and lighter
    col = np.tile(lin(Pt["blue"]), (n, 1))
    col = mix(col, lin(Pt["blue_dk"]), smooth(-m2, 0.05, 0.45) * 0.8)
    col = mix(col, lin(Pt.get("blue_lt", [70, 130, 240])), smooth(m2, 0.15, 0.5) * 0.7)
    glow = np.full(n, Pt["glow"]["ring"])
    rough = np.full(n, Pt["rough"]["top"])
    # centre: near black with navy clouds and a few blue specks
    cc = np.tile(lin(Pt["centre"]), (n, 1))
    cc = mix(cc, lin(Pt["navy"]), smooth(m1, -0.05, 0.4))
    sp = blobs(Xg, 6.0, 307, 0.28) * smooth(hb.fbm(Xg * 2.5, 2, 309), 0.1, 0.3)
    cc = mix(cc, lin(Pt["speck"]), smooth(sp, 0.25, 0.45))
    col = col * (1 - centre[:, None]) + cc * centre[:, None]
    glow = glow * (1 - centre) + Pt["glow"]["speck"] * smooth(sp, 0.25, 0.45) * centre
    rough = rough * (1 - centre) + Pt["rough"]["centre"] * centre
    # green flecks around the centre's edge
    band = np.exp(-((dn - edge - 0.04) / 0.07) ** 2) * top
    gb = blobs(Xg, 5.5, 311, 0.55) * (0.6 + 0.6 * hb.fbm(Xg * 3.0, 2, 312))
    gm = smooth(gb * band, 1 - Pt["green_cov"] - 0.25, 1 - Pt["green_cov"] + 0.05)
    col = mix(col, lin(Pt["green"]), gm)
    glow = glow * (1 - gm) + Pt["glow"]["green"] * gm
    # pale blotches: large soft ones and small spots, more toward the rim (and on the bead's underside)
    lo_, hi_ = Pt["pale_cov"]
    t_out = np.clip((dn - Pt["pale_lo"]) / (1 - Pt["pale_lo"]), 0, 1)
    t_out = np.where(und, np.clip(1 - u / 0.15, 0, 1), t_out)
    cov = (lo_ + (hi_ - lo_) * t_out) * np.where(und, 1.0, 1 - centre)
    big = blobs(Xg, 2.3, 313, 0.85) * (0.75 + 0.5 * hb.fbm(Xg * 4.0, 2, 314))
    small = blobs(Xg, 6.5, 315, 0.5, 0.06)
    f = np.maximum(big, small * Pt.get("small_w", 0.6)) + 0.25 * aux["wart"]
    thr = 1 - cov
    pm = smooth(f, thr - 0.06, thr + 0.06) * (cov > 0.02)
    cm = smooth(f, thr + 0.16, thr + 0.3) * (cov > 0.02)
    col = mix(col, lin(Pt["pale"]), pm)
    col = mix(col, lin(Pt["pale_core"]), cm)
    glow = glow * (1 - pm) + Pt["glow"]["pale"] * pm
    glow = glow * (1 - cm) + Pt["glow"]["core"] * cm
    rough = rough * (1 - pm) + Pt["rough"]["pale"] * pm
    # a few dark spots on the bead
    bead = np.where(und, np.clip(1 - u / 0.1, 0, 1), smooth(dn, 0.93, 0.98))
    db = blobs(Xg, 3.0, 319, 0.35) * smooth(hb.fbm(Xg * 1.7, 2, 320), 0.15, 0.35)
    dm = smooth(db, 0.45, 0.6) * bead * (1 - pm) * (Pt["blot_cov"] > 0)
    col = mix(col, lin(Pt["dark_blot"]), dm * 0.9)
    glow = glow * (1 - dm)
    # underside: gills, crests lighter, blue at the rim, dark at the apex
    gl = aux["gill"][und]
    cu = mix(np.tile(lin(Pt["gill"]), (int(und.sum()), 1)), lin(Pt["gill_crest"]), gl)
    cu = mix(cu, lin(Pt["under_rim"]), smooth(1 - u[und], 0.85, 0.95))
    cu = mix(cu, lin(Pt["apex"]), smooth(u[und], 0.75, 0.95))
    w_ = 1 - pm[und]
    col[und] = col[und] * (1 - w_[:, None]) + cu * w_[:, None]
    glow[und] = glow[und] * (1 - w_) + 0.05 * smooth(1 - u[und], 0.85, 0.95) * w_
    rough[und] = rough[und] * (1 - w_) + Pt["rough"]["under"] * w_
    # pores darken a little
    col *= (1 - 0.35 * aux["pore"])[:, None]
    return col, np.clip(glow, 0, 1), np.clip(rough, 0, 1)


# ------------------------------------------------------------------------------------------------------------- design
def cmd_design(a):
    src, W = Path(a[0]), Path(a[1])
    W.mkdir(parents=True, exist_ok=True)
    C = json.loads(json.dumps(CAP))
    if "--cap" in a:
        C.update(json.loads(Path(opt(a, "--cap", "")).read_text()))
    Pt = json.loads(json.dumps(PAINT))
    if "--paint" in a:
        Pt.update(json.loads(Path(opt(a, "--paint", "")).read_text()))
    fr = old_frame(src)
    # the stalk apex: the body design's top torso node, in the cap frame
    G = json.loads((W / "graph.json").read_text())
    top = max((n for n in G["nodes"] if n["kind"] == "torso"), key=lambda n: n["p"][1])
    p = np.array(top["p"]) - np.array(fr["cen"])
    fr["S_local"] = [float(p @ np.array(fr["ex"])), float(p @ np.array(fr["ez"]))]
    fr["S_h"] = float(p @ np.array(fr["up"]))
    (W / "cap_frame.json").write_text(json.dumps(fr, indent=1))
    rep = {"frame": {k: fr[k] for k in ("cen", "up", "h_top", "h_bottom", "S_local", "S_h")}, "lods": {}}
    for k, (nth, ns) in enumerate(C["res"]):
        g = build_grid(fr, C, nth, ns)
        pos, nrm, uv, tris = mesh_from_grid(fr, g, C)
        np.savez(W / ("cap_lod%d.npz" % k), pos=pos, nrm=nrm, uv=uv, tris=tris)
        rep["lods"][k] = {"verts": len(pos), "tris": len(tris)}
        if k == 0:
            g0 = g
    # high: sculpt and paint
    nth, ns = C["res_high"]
    g = build_grid(fr, C, nth, ns)
    X = g["X"]
    N = grid_normals(X)
    Xg = local_to_game(fr, X.reshape(-1, 3))
    Ng = vec_to_game(fr, N.reshape(-1, 3))
    disp, aux = sculpt(fr, g, C, Xg, Ng)
    col, glow, rough = paint(fr, g, C, Pt, Xg, aux)
    Xh = Xg + disp[:, None] * Ng
    T = grid_tris(*X.shape[:2])
    weld = np.arange(X.shape[0] * X.shape[1]).reshape(X.shape[:2])
    weld[:, 0] = weld[0, 0]
    weld[:, -1] = weld[0, -1]
    Tw = weld.ravel()[T]
    Tw = Tw[(Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 0] != Tw[:, 2])]
    keep = np.unique(Tw)
    rm = -np.ones(len(Xh), int)
    rm[keep] = np.arange(len(keep))
    np.savez(W / "cap_high.npz", V=Xh[keep], T=rm[Tw], col=col[keep], glow=glow[keep], rough=rough[keep])
    rep["high"] = {"verts": int(len(keep)), "tris": int(len(Tw)), "disp_range": [float(disp.min()), float(disp.max())]}
    # atlas: the cap's discs, and the body's free texels (everything but the strip and the discs)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE] + 0.5
    cap = np.zeros((SIZE, SIZE), bool)
    for (l, t, r) in (C["uv_top"], C["uv_under"]):
        cap |= (xx - l - r) ** 2 + (yy - t - r) ** 2 <= (r + 1) ** 2
    np.save(W / "cap_texels.npy", cap)
    strip = np.zeros((SIZE, SIZE), bool)
    F = 0.125
    strip[:int(np.ceil(F * SIZE)) + 8, int((1 - F) * SIZE) - 8:] = True
    np.save(W / "strip_texels.npy", strip)
    occ = nd.binary_dilation(cap | strip, iterations=6)
    np.save(W / "occupied.npy", occ)
    rep["free_texels"] = int((~occ).sum())
    rep["cap_texels"] = int(cap.sum())
    (W / "cap_design.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep))


# ------------------------------------------------------------------------------------------------------------ textures
def write_textures(dst, P):
    """round 18: the whole atlas is the new body and cap (everything but the corpse miniature's strip, whose blocks keep
    the old bytes at every mip). Texels neither part uses take the nearest used texel (no dark halos in coarse mips).
    alb/nrm/orm from the body bakes (bake_*) on the body's texels and the cap bakes (capbake_*) on the cap's; the body's
    glow goes to glow_body_mask (x hd_glow), the cap's to glow_cap_mask (x cap_glow)."""
    W = Path(P["hd_dir"])
    body = nd.binary_dilation(np.load(W / "body_texels.npy"), iterations=2)
    cap = np.load(W / "cap_texels.npy")
    strip = np.load(W / "strip_texels.npy")
    body &= ~strip
    cap &= ~strip
    body &= ~cap
    used = body | cap
    _d, (iy, ix) = nd.distance_transform_edt(~used, return_indices=True)
    rep = {"body_texels": int(body.sum()), "cap_texels": int(cap.sum())}
    from PIL import Image

    def png(prefix, name):
        return np.asarray(Image.open(W / ("%s_%s.png" % (prefix, name))).convert("RGB"))

    def compose(name):
        b, c = png("bake", name), png("capbake", name)
        out = np.where(cap[..., None], c, b)
        return out[iy, ix]

    def splice(kind, full):
        """full: (2048, 2048, C) or (2048, 2048) uint8 at the atlas size; resized to the file's size"""
        src = pb.bm.tex_path(dst, kind) if kind in ("alb", "nrm", "orm") else \
            sorted(Path(dst, "overlay").rglob("*_%s.texture" % kind))[0]
        fmt, w, h, mips = pb.d2r_texture.read_texture(src)
        A = pb.d2r_texture.decode(fmt, w, h, mips[0])
        bc4 = fmt == pb.d2r_texture.FMT_BC4
        if bc4 and A.ndim == 3:
            A = A[..., 0]
        if full.shape[:2] != (h, w):
            full = np.asarray(Image.fromarray(full).resize((w, h), Image.BOX))
        sm = strip if strip.shape == (h, w) else \
            np.asarray(Image.fromarray(strip.astype(np.uint8) * 255).resize((w, h), Image.BOX)) > 0
        A2 = A.copy()
        if A2.ndim == 2:
            A2[~sm] = full[~sm]
        else:
            A2[~sm, :full.shape[-1]] = full[~sm]
        ch = (A2 != A).reshape(h, w, -1).any(-1)
        if bc4:
            rep[kind] = hb.write_spliced_capsafe(src, fmt, w, h, pb.bm.levels_keeping_part(A2, fmt, mips, sm, kind="BC4"),
                                                 mips, ch, 8, sm)
        else:
            rep[kind] = hb.write_spliced_capsafe(src, fmt, w, h, pb.bm.levels_keeping_part(A2, fmt, mips, sm), mips, ch,
                                                 16, sm)

    alb = compose("alb")
    splice("alb", np.dstack([alb, np.full(alb.shape[:2], 255, np.uint8)]))
    nb = compose("nrm").astype(int)
    nrm = np.zeros(nb.shape[:2] + (4,), np.uint8)
    nrm[..., 0] = 255
    nrm[..., 1] = 255 - nb[..., 1]       # Blender's OpenGL y up the image -> the game's convention (see s4_hdbody)
    nrm[..., 3] = nb[..., 0]
    splice("nrm", nrm)
    ao = compose("ao")[..., 0]
    aux = compose("aux")
    orm = np.zeros(ao.shape + (4,), np.uint8)
    orm[..., 0] = ao
    orm[..., 1] = aux[..., 1]
    orm[..., 2] = 0
    orm[..., 3] = np.where(cap[iy, ix], int(P.get("cap_spec", 60)), int(P.get("hd_spec", 12)))
    splice("orm", orm)
    g = aux[..., 0].astype(float)
    gb = np.where(body[iy, ix] & ~cap[iy, ix], g * float(P.get("hd_glow", 1.0)), 0)
    gc = np.where(cap[iy, ix], g * float(P.get("cap_glow", 0.94)), 0)
    # masks: no nearest-fill bleed of the other part's glow (zero outside each part, then a small grow)
    gb = np.where(body, gb, 0)
    gc = np.where(cap, gc, 0)
    splice("glow_body_mask", np.clip(gb, 0, 255).astype(np.uint8))
    splice("glow_cap_mask", np.clip(gc, 0, 255).astype(np.uint8))
    return rep


# ------------------------------------------------------------------------------------------------------------ corpse
def cmd_shell(a):
    """shell <stage> [--shell-lod 3] [--eps 0.01] [--drop 12]: the corpse shell made from this stage's own body and cap.

    s5_death.py's corpse is a rigid copy of the body on the shell bone (loin_cloth), shown at the end of `death` (while
    --hide-body puts the live skeleton under the floor) and in `dead`. Until round 18 it was round 13's reconstructed
    body and cap with UVs in the 256 px miniature strip: blocky, jagged and the old cap. Here, per LOD k, the old shell
    is dropped and replaced by the stage's own mesh (body and cap) of LOD max(k, --shell-lod), skinned in the death
    clip's last pose (its end with the hide-body drop of --drop units undone), pushed out by --eps along its normals,
    lifted so nothing is under the floor, re-expressed in the shell bone's frame in `dead`, bound to it with weight 1.
    Its UVs are the live mesh's own (the full-size atlas) and its normals the posed ones."""
    stage = Path(a[0])
    slod = int(opt(a, "--shell-lod", "3"))
    eps, drop = float(opt(a, "--eps", "0.01")), float(opt(a, "--drop", "12"))
    od = stage / "overlay" / pb.FOLDER
    gr2, d2r_mesh, dm = pb.gr2, pb.d2r_mesh, pb.dm
    _ms, gsk = gr2.load_meshes((od / "torso_lod0.model").read_bytes())
    clips = gr2.load_clips((od / "animation" / "combined.animations").read_bytes(), gsk)
    death, dead = clips["death"], clips["dead"]
    pose = gr2.pose_at(gsk, death, death.duration).worlds.copy()
    pose[:, 1, 3] += drop
    Mskin = {n: pose[i] @ gsk.iwt[i] for i, n in enumerate(gsk.names)}
    sbi = gsk.names.index("loin_cloth")
    S_inv = np.linalg.inv(gr2.pose_at(gsk, dead, 0.0).worlds[sbi] @ gsk.iwt[sbi])
    rep = {"shell_lod": slod, "eps": eps, "lods": {}}
    for lod in range(5):
        z = np.load(stage / ("skinned_lod%d.npz" % max(lod, slod)))
        names_z = [str(x) for x in z["bones"]]
        pos, nrm, uv, tris = z["pos"], z["nrm"], z["uv"], z["tris"]
        Pw = np.zeros_like(pos)
        Nw = np.zeros_like(pos)
        for c in range(z["bone_idx"].shape[1]):
            M = np.stack([Mskin[names_z[j]] for j in z["bone_idx"][:, c]])
            w = z["weights"][:, c, None]
            Pw += w * (np.einsum("nij,nj->ni", M[:, :3, :3], pos) + M[:, :3, 3])
            Nw += w * np.einsum("nij,nj->ni", M[:, :3, :3], nrm)
        Nw /= np.maximum(np.linalg.norm(Nw, axis=1, keepdims=True), 1e-9)
        Pw = Pw + eps * Nw
        Pw[:, 1] += max(0.0, 0.02 - Pw[:, 1].min())
        Ps = Pw @ S_inv[:3, :3].T + S_inv[:3, 3]
        Ns = Nw @ S_inv[:3, :3].T
        Ns /= np.maximum(np.linalg.norm(Ns, axis=1, keepdims=True), 1e-9)
        path = od / ("torso_lod%d.model" % lod)
        g, tree = d2r_mesh.load_model(path)
        m = tree["Meshes"][0]
        vs = m["PrimaryVertexData"]["Vertices"].obj
        names = [b["BoneName"] for b in m["BoneBindings"]]
        bi = np.array([v["BoneIndices"] for v in vs])
        bw = np.array([v["BoneWeights"] for v in vs])
        main = np.array(names)[bi[np.arange(len(bi)), bw.argmax(1)]]
        shell = main == "loin_cloth"
        t_old = np.array([x["Int16"] for x in m["PrimaryTopology"]["Indices16"]], int).reshape(-1, 3) % 65536
        keepv = ~shell
        remap = -np.ones(len(vs), int)
        remap[keepv] = np.arange(keepv.sum())
        kept_t = remap[t_old[keepv[t_old].all(1)]]
        sb = names.index("loin_cloth")
        bidx = np.full((len(Ps), 4), sb)
        wts = np.zeros((len(Ps), 4))
        wts[:, 0] = 1
        scale = float(m["ExtendedData"].obj["VertexScale"])
        assert np.abs(Ps).max() < scale, (np.abs(Ps).max(), scale)
        new = d2r_mesh.encode_vertices(vs[0].td, Ps, Ns, uv, tris, bidx, wts, scale)
        kept = [v for v, k in zip(vs, keepv) if k]
        m["PrimaryVertexData"]["Vertices"].obj = kept + new
        allt = np.vstack([kept_t, tris + len(kept)])
        assert len(kept) + len(new) <= 65535
        topo = m["PrimaryTopology"]
        idx_td = topo["Indices16"][0].td
        topo["Indices16"] = [dm.Obj(idx_td, {"Int16": int(i) - 65536 if i > 32767 else int(i)}) for i in allt.reshape(-1)]
        topo["Groups"][0]["TriCount"] = len(allt)
        # the shell bone's box in its bind space (as s4_procbody.write_lod), and the whole mesh's box
        inv = {x["Name"]: np.array(x["InverseWorldTransform"], float).reshape(4, 4) for x in tree["Skeletons"][0]["Bones"]}
        bb = next(x for x in m["BoneBindings"] if x["BoneName"] == "loin_cloth")
        pts = Ps @ inv["loin_cloth"][:3, :3] + inv["loin_cloth"][3, :3]
        bb["OBBMin"] = [float(v) for v in pts.min(0)]
        bb["OBBMax"] = [float(v) for v in pts.max(0)]
        ed = m["ExtendedData"].obj
        ed["bbMin"] = [float(min(x, y)) for x, y in zip(ed["bbMin"], Ps.min(0))]
        ed["bbMax"] = [float(max(x, y)) for x, y in zip(ed["bbMax"], Ps.max(0))]
        rep["lods"][lod] = {"old_shell_vertices": int(shell.sum()), "shell_vertices": len(new), "shell_tris": len(tris),
                            "total_tris": len(allt), "vertices": len(kept) + len(new),
                            "bytes": d2r_mesh.write_model(g, tree, path)}
        print(lod, rep["lods"][lod], flush=True)
    (stage / "hdcap_shell.json").write_text(json.dumps(rep, indent=1))


CORPSE_BONES = ["L_Thigh", "R_Thigh", "L_Calf", "R_Calf", "L_UpperArm", "R_UpperArm", "L_ForeArm", "R_ForeArm"]


def _skin(z, names_z, sk, W):
    """World positions of a skinned npz's vertices for bone worlds W (gr2 skeleton order)."""
    Ms = {n: W[i] @ sk.iwt[i] for i, n in enumerate(sk.names)}
    P = np.zeros_like(z["pos"])
    for c in range(z["bone_idx"].shape[1]):
        M = np.stack([Ms[names_z[j]] for j in z["bone_idx"][:, c]])
        P += z["weights"][:, c, None] * (np.einsum("nij,nj->ni", M[:, :3, :3], z["pos"]) + M[:, :3, 3])
    return P


def _repose(sk, W, rots, lift):
    """W with world-axis turns {bone index: 3x3} about each bone's (moved) joint, children following, and every bone
    under cog moved up by lift."""
    import s5_death as sd
    out = W.copy()
    cog = sk.names.index("cog")
    for i, p in enumerate(sk.parent):
        if p >= 0:
            out[i] = out[p] @ np.linalg.inv(W[p]) @ W[i]
        if i == cog:
            out[i] = sd.trans([0.0, lift, 0.0]) @ out[i]
        if i in rots:
            out[i] = sd.about(rots[i], out[i][:3, 3]) @ out[i]
    return out


def cmd_corpse(a):
    """corpse <stage> [--from <stage with the source clip>] [--target <s4_hdcorpse pose.json>] [--iters 3000] [--seed 1] [--sink 0.05] [--drop 12] [--pose-in json] [--pose-out json] [--dry]

    The death clip (s5_death.py, round 13) put its body on the floor with a lift on the root bone, which the engine and
    hdkit ignore, and fitted its corpse to round 13's mesh. With the round 17/18 body the engine's last pose has the legs
    2.3 units under the floor and the cap 1.9; the corpse shell (cmd_shell) lifted all of it 2.3 units, so the corpse
    floated with its long arms in the air. Here the corpse pose is redone for this body:
    - turns of the thighs, calves, upper arms and forearms (world axes about their joints, |angle| <= 60 deg) are
      searched on the last pose so the limbs lie low and close to the trunk (mean height, the arms' 90th percentile
      height, a pull to the start pose, the limbs' footprint kept near the trunk), with the body always set on the floor;
    - the fall from 0.40 s eases into those turns (smoothstep to 0.60 s); every sample before the hide (0.64 s) is lifted
      so nothing is under the floor and, from 0.60 s, so the body rests on it; from the hide on, the new last pose under
      the floor (the --drop of s5_death --hide-body);
    - the cap (jaw) keeps its path but, from the throw (0.50 s), eases up so it lands with its lowest point --sink under
      the floor, standing on its rim as classic's DD does;
    - loin_cloth (the corpse shell's bone) keeps its world matrices, so the shell still shows where it did.
    --target: the last pose and the landed cap are a pose fitted to classic's DD frames (s4_hdcorpse.py fit: on its
    side, limbs folded into the heap, the cap on its rim beside the head) instead of the searched limb turns.
    The tracks of the bones under cog and of loin_cloth are rewritten (60 samples a second, linear), in
    `death` and `dead`. Rebuild the shell afterwards (cmd_shell)."""
    import s5_death as sd
    stage = Path(a[0])
    drop, sink = float(opt(a, "--drop", "12")), float(opt(a, "--sink", "0.05"))
    od = stage / "overlay" / pb.FOLDER
    gr2, d2r_mesh, dm = pb.gr2, pb.d2r_mesh, pb.dm
    anim = od / "animation" / "combined.animations"
    src = Path(opt(a, "--from", str(stage))) / "overlay" / pb.FOLDER / "animation" / "combined.animations"
    _ms, sk = gr2.load_meshes((od / "torso_lod0.model").read_bytes())
    clips = gr2.load_clips(src.read_bytes(), sk)
    death = clips["death"]
    L = float(death.duration)
    under = np.zeros(len(sk.names), bool)
    cog, jaw, sb = sk.names.index("cog"), sk.names.index("jaw"), sk.names.index("loin_cloth")
    head = sk.names.index("head")
    for i, p in enumerate(sk.parent):
        under[i] = i == cog or (p >= 0 and under[p])
    up = np.where(under & (np.arange(len(under)) != sb))[0]

    def undrop(W, d):
        W = W.copy()
        W[up, 1, 3] += d
        return W
    z3 = np.load(stage / "skinned_lod3.npz")
    n3 = [str(x) for x in z3["bones"]]
    k3 = z3["kind"]
    body3 = k3 != "cap"
    z0 = np.load(stage / "skinned_lod0.npz")
    n0 = [str(x) for x in z0["bones"]]
    cap0 = z0["kind"] == "cap"
    z0c = {"pos": z0["pos"][cap0], "bone_idx": z0["bone_idx"][cap0], "weights": z0["weights"][cap0]}
    Wend = undrop(gr2.pose_at(sk, death, L).worlds, drop)
    bi = [sk.names.index(b) for b in CORPSE_BONES]
    arm = np.isin(k3, ["arm"])
    leg = np.isin(k3, ["leg", "foot"])
    tor = k3 == "torso"

    def rots_of(x):
        return {i: sd.euler(*x[3 * k:3 * k + 3]) for k, i in enumerate(bi)}

    def body_lift(W, x):
        P = _skin(z3, n3, sk, _repose(sk, W, rots_of(x), 0.0))[body3]
        return -P[:, 1].min()

    P0 = _skin(z3, n3, sk, Wend)
    tc = P0[tor][:, [0, 2]].mean(0)
    foot0 = {nm: np.linalg.norm(P0[m][:, [0, 2]] - tc, axis=1).mean() for nm, m in (("arm", arm), ("leg", leg))}

    def score(x):
        W = _repose(sk, Wend, rots_of(x), 0.0)
        P = _skin(z3, n3, sk, W)
        h = P[:, 1] - P[body3, 1].min()
        J = h[body3].mean() + h[arm].mean() + 0.5 * np.percentile(h[arm], 90) + 0.3 * np.percentile(h[leg], 90)
        for nm, m in (("arm", arm), ("leg", leg)):
            J += 0.4 * max(0.0, np.linalg.norm(P[m][:, [0, 2]] - tc, axis=1).mean() - foot0[nm])
        return J + 2e-5 * float(x @ x)

    target = None
    if "--target" in a:
        # a corpse pose fitted to classic's DD frames (s4_hdcorpse.py fit, s5_death's pose model on this skeleton)
        target = json.loads(Path(opt(a, "--target", "")).read_text())
        x = np.zeros(3 * len(bi))
    elif "--pose-in" in a:
        x = np.array(json.loads(Path(opt(a, "--pose-in", "")).read_text())["x"], float)
    else:
        rng = np.random.default_rng(int(opt(a, "--seed", "1")))
        iters = int(opt(a, "--iters", "3000"))
        x = np.zeros(3 * len(bi))
        best = score(x)
        s0 = best
        for it in range(iters):
            step = 25.0 * (1 - it / iters) + 2.0
            y = x.copy()
            k = rng.integers(len(bi))
            y[3 * k:3 * k + 3] += rng.normal(0, step, 3)
            y = np.clip(y, -60, 60)
            v = score(y)
            if v < best:
                x, best = y, v
        print("corpse score %.3f -> %.3f" % (s0, best), flush=True)
    rep = {"x": [round(float(v), 3) for v in x], "bones": CORPSE_BONES}
    if target is None:
        Wf = _repose(sk, Wend, rots_of(x), body_lift(Wend, x))
    else:
        sd.set_pose(target)
        ssk = sd.Skeleton(od / "torso_lod0.model")
        assert ssk.names == sk.names
        _l, Wl = ssk.pose(sd.body_motion(ssk, sd.LENGTH))
        Wf = Wend.copy()
        Wf[up] = np.stack(Wl)[up]
        att = bool(target["cap"].get("attached"))
        Wf[up, 1, 3] -= _skin(z3, n3, sk, Wf)[:, 1].min() if att else _skin(z3, n3, sk, Wf)[body3][:, 1].min()
        rep["target"] = target.get("params")
        rep["cap_attached"] = att
    Pf = _skin(z3, n3, sk, Wf)
    rep["end_heights"] = {k: [round(float(Pf[k3 == k, 1].min()), 2), round(float(Pf[k3 == k, 1].max()), 2)]
                          for k in np.unique(k3)}
    capfix_end = -_skin(z0c, n0, sk, Wend)[:, 1].min() - sink
    rep["cap_lift_end"] = round(float(capfix_end), 3)
    if "--pose-out" in a:
        Path(opt(a, "--pose-out", "")).write_text(json.dumps(rep, indent=1))
    if "--dry" in a:
        print(json.dumps(rep))
        return
    T_RAMP0, T_RAMP1, T_THROW, T_LAND, T_HIDE = 0.40, 0.60, 0.50, 0.60, 0.64
    sm = lambda u: float(np.clip(u, 0, 1) ** 2 * (3 - 2 * np.clip(u, 0, 1)))  # noqa: E731
    times = sorted(set(np.round(np.arange(0, L + 1e-6, 1 / 60), 6).tolist()) | {T_HIDE - 0.01, T_HIDE, round(L, 6)})
    times = [t for t in times if t <= L + 1e-6]
    wset = {}
    lifts = []
    Lf = [np.linalg.inv(Wf[p]) @ Wf[i] if p >= 0 else Wf[i] for i, p in enumerate(sk.parent)]
    Jend = sd.trans([0, capfix_end, 0]) @ Wend[jaw]
    attached = target is not None and bool(target["cap"].get("attached"))
    W0 = gr2.pose_at(sk, death, 0.0).worlds
    jaw_rest = np.linalg.inv(W0[head]) @ W0[jaw]
    if attached:
        Jend = Wf[jaw]
    elif target is not None:
        cap3 = z3["pos"][k3 == "cap"]
        C, _c, _R = sd.cap_rest(cap3, cap3.mean(0), target)
        Jend = C @ np.linalg.inv(sk.iwt[jaw])
        rep["cap_end_min_y"] = round(float(_skin(z0c, n0, sk, np.where(np.arange(len(sk.names))[:, None, None] == jaw,
                                                                         Jend[None], Wf))[:, 1].min()), 3)

    def blend(Wo, s):
        """Bones under cog: locals slerped from the clip's toward the new last pose's by s; the rest as in the clip."""
        W = Wo.copy()
        for i, p in enumerate(sk.parent):
            if not (under[i] and i != sb):
                if p >= 0 and under[p]:
                    W[i] = W[p] @ np.linalg.inv(Wo[p]) @ Wo[i]
                continue
            Lo = jaw_rest if (attached and i == jaw) else np.linalg.inv(Wo[p]) @ Wo[i]
            Lc = np.eye(4)
            Lc[:3, :3] = sd.slerp_m(Lo[:3, :3], Lf[i][:3, :3], s)
            Lc[:3, 3] = (1 - s) * Lo[:3, 3] + s * Lf[i][:3, 3]
            W[i] = W[p] @ Lc
        return W

    cc = z0c["pos"].mean(0)

    def mixj(A, B, v):
        """Rigid blend of two cap placements about the cap's centre."""
        if v <= 0:
            return A
        R = sd.slerp_m(A[:3, :3], B[:3, :3], v)
        c = (1 - v) * (A[:3, :3] @ cc + A[:3, 3]) + v * (B[:3, :3] @ cc + B[:3, 3])
        M = np.eye(4)
        M[:3, :3] = R
        M[:3, 3] = c - R @ cc
        return M

    def lift_of(W):
        return -_skin(z3, n3, sk, W)[:, 1].min() if attached else -_skin(z3, n3, sk, W)[body3][:, 1].min()

    for t in times:
        Wo = gr2.pose_at(sk, death, t).worlds
        if t >= T_HIDE - 1e-6:
            Wn = Wf.copy()
            Wn[up, 1, 3] -= drop
            Wn[jaw] = Jend.copy()
            Wn[jaw][1, 3] -= drop
            Wn[sb] = Wo[sb]
            wset[t] = Wn
            lifts.append(None)
            continue
        s = sm((t - T_RAMP0) / (T_RAMP1 - T_RAMP0))
        Wn = blend(Wo, s) if s > 0 else Wo.copy()
        if attached and s == 0:
            Wn[jaw] = Wn[head] @ jaw_rest
        lift = lift_of(Wn)
        lift = max(lift, 0.0) if t < 0.55 else (lift if t >= T_RAMP1 else max(lift, lift * sm((t - 0.55) / 0.05)))
        Wn[up, 1, 3] += lift
        if attached:
            pass                      # the cap rides the head (blended with the rest of the body, lifted with it)
        elif t >= T_LAND:
            Wn[jaw] = Jend
        elif t >= T_THROW:
            cl = -_skin(z0c, n0, sk, Wo)[:, 1].min() - sink
            u = sm((t - T_THROW) / (T_LAND - T_THROW))
            Jh = Wn[head] @ np.linalg.inv(Wo[head]) @ Wo[jaw]          # still riding the (re-posed) head
            Jo = sd.trans([0, max(cl * u, 0.0), 0]) @ Wo[jaw]           # the clip's throw, lifted to land on the floor
            J = mixj(Jh, Jo, u)
            J = mixj(J, Jend, sm((t - 0.55) / (T_LAND - 0.55)))
            Wn[jaw] = J
        else:
            Wn[jaw] = Wn[head] @ np.linalg.inv(Wo[head]) @ Wo[jaw]
        Wn[sb] = Wo[sb]
        wset[t] = Wn
        lifts.append(round(float(lift), 3))
    rep["lifts"] = lifts
    rep["times"] = times
    # write the tracks (as s5_limbfit.write)
    g = dm.Gr2File.read(src.read_bytes())
    tree = dm.parse_tree(g)
    kinds = {}
    for an in tree["Animations"]:
        for tg in an["TrackGroups"]:
            for tr in tg["TransformTracks"]:
                for kk in ("OrientationCurve", "PositionCurve"):
                    v = tr[kk]["CurveData"]
                    kinds.setdefault(list(v.obj.f)[0], v)
    tmpl_k, tmpl_q, tmpl_p = (kinds["CurveDataHeader_DaK32fC32f"], kinds["CurveDataHeader_D4Constant32f"],
                              kinds["CurveDataHeader_D3Constant32f"])
    real = tmpl_k.obj["Knots"][0].td

    def header(tmpl, deg):
        hk = list(tmpl.obj.f)[0]
        h = tmpl.obj[hk]
        return hk, dm.Obj(h.td, {"Format": h["Format"], "Degree": deg})

    def curve_k(knots, controls):
        hk, h = header(tmpl_k, 1)
        return dm.Variant(tmpl_k.td, dm.Obj(tmpl_k.obj.td, {hk: h, "Padding": 0,
                                                             "Knots": [dm.Obj(real, {"Real32": float(v)}) for v in knots],
                                                             "Controls": [dm.Obj(real, {"Real32": float(v)}) for v in controls]}))

    def curve_c(tmpl, values):
        hk, h = header(tmpl, 0)
        return dm.Variant(tmpl.td, dm.Obj(tmpl.obj.td, {hk: h, "Padding": 0, "Controls": [float(v) for v in values]}))

    def set_track(tr, qs, ps, ts):
        qs = np.array(qs)
        for i in range(1, len(qs)):
            if qs[i] @ qs[i - 1] < 0:
                qs[i] = -qs[i]
        ps = np.array(ps)
        tr["OrientationCurve"]["CurveData"] = curve_c(tmpl_q, qs[0]) if np.abs(qs - qs[0]).max() < 1e-6 else curve_k(ts, qs.ravel())
        tr["PositionCurve"]["CurveData"] = curve_c(tmpl_p, ps[0]) if np.abs(ps - ps[0]).max() < 1e-6 else curve_k(ts, ps.ravel())

    names = [sk.names[i] for i in up] + ["loin_cloth"]
    for clip, ts, getw in (("death", times, lambda t: wset[t]), ("dead", [0.0], lambda t: wset[times[-1]])):
        qs = {b: [] for b in names}
        ps = {b: [] for b in names}
        for t in ts:
            W = getw(t)
            for b in names:
                i = sk.names.index(b)
                Lc = np.linalg.inv(W[sk.parent[i]]) @ W[i]
                qs[b].append(sd.mat_q(Lc[:3, :3]))
                ps[b].append(Lc[:3, 3])
        an = next(v for v in tree["Animations"] if v["Name"] == clip)
        grp = max(an["TrackGroups"], key=lambda tg: len(tg["TransformTracks"]))
        done = []
        for tr in grp["TransformTracks"]:
            if tr["Name"] in qs:
                set_track(tr, qs[tr["Name"]], ps[tr["Name"]], ts)
                done.append(tr["Name"])
        assert len(done) == len(names), (clip, done)
    rep["bytes"] = d2r_mesh.write_model(g, tree, anim)
    (stage / "hdcap_corpse.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in ("x", "end_heights", "cap_lift_end", "bytes")}))


if __name__ == "__main__":
    {"design": cmd_design, "shell": cmd_shell, "corpse": cmd_corpse}[sys.argv[1]](sys.argv[2:])
