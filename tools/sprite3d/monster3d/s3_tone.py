"""Finish a projected albedo for D2R's lit material: clean colour outliers, set the body's tone, darken the cap's centre, and
make a corpse albedo from classic's corpse frames.

  venv python s3_tone.py tone <albedo.png> <mesh_uv.npz> <part.png> <out dir>
        [--blue-sat 0.55] [--brown 3] [--body-gamma 0.9] [--body-gain 1.3] [--body-chroma 0.8]
        [--centre 0.25,0.7,0.35] [--top 0.15] [--pale LO,HI,LIFT,DESAT]
  venv python s3_tone.py corpse <albedo.png> <part.png> <classic dd dir> <out dir> [--level 205] [--spread 0.45] [--chroma 1.5]

tone:
- **Clean** (body texels, part.png < 0.5): a texel is an outlier when its blue excess B - max(R, G) is more than
  --blue-sat of its luminance + 8 (a saturated blue speck that one sprite drew, e.g. on the d0 upper arm) or when it is
  red-brown (R - B > --brown and R - G > --brown: the x4 sprite's brown pixels at the knees). Its chroma is replaced by
  the median chroma of the clean body texels around it (31 px window), its luminance kept.
- **Body tone**: L' = 255 * --body-gain * (L / 255) ^ --body-gamma on the body texels (colour scaled by L' / L), and the
  chroma times --body-chroma: classic's body is an evenly pale, nearly neutral blue-grey; the raw projection is dark
  (p50 25) because the sprite's own shading is in it.
- **Cap centre** (--centre R0,R1,LEVEL): every top-facing cap texel (normal y > --top) gets its normalised radius r (the
  horizontal distance from the cap axis over the largest one at that angle, as s3_caprim.py's polar pick); its colour is
  times LEVEL inside R0, rising smoothly to 1 at R1. Classic's cap is a bright speckled rim on a DARK centre; the 8-view
  blend leaves the centre too light. The glow mask (s5_glow.py --mask sprite) is made from this albedo, so the glow fades
  with it.
- **Pale patches** (--pale LO,HI,LIFT,DESAT): body texels by smoothstep(LO, HI) of their toned luminance are lifted toward
  white by LIFT and lose DESAT of their chroma: classic's body shows pale grey highlights, ours a short, blue top end.
  Writes albedo_tone.png, cap_radius.png (r * 255 on top-facing cap texels, 0 elsewhere) and tone.json.

corpse: an albedo (same UV layout) for the corpse shell of s5_death.py --shell, in classic's corpse colours: the body
texels' luminance RANK is kept (the detail order of our texture), their values are taken from the classic DD frames' body
pixels (all 8 directions, cool or neutral, not the blue rim), squeezed toward their median by --spread and moved so the
median is --level; the chroma is classic's mean chroma at that luminance times --chroma (the lit material greys it). So the corpse is evenly pale like classic's,
without the black and white patches of the live texture. Writes albedo_corpse.png and corpse.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as nd

import s3_caprim

W709 = np.array([0.2126, 0.7152, 0.0722], np.float32)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def cap_radius(mesh, part, top):
    """(H, W) normalised radius of every top-facing cap texel (NaN elsewhere), as s3_caprim.polar."""
    H, W = part.shape
    pos, nrm, uv, tris = mesh["pos"], mesh["nrm"], mesh["uv"], mesh["tris"]
    ids, bary = s3_caprim.raster(np.ascontiguousarray(uv[tris], np.float64), H, W)
    cap = part & (ids >= 0)
    yy, xx = np.nonzero(cap)
    f = tris[ids[yy, xx]]
    b = bary[yy, xx]
    P = (pos[f] * b[..., None]).sum(1)
    N = (nrm[f] * b[..., None]).sum(1)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    up = N[:, 1] > top
    ctr = P[up].mean(0)
    d = np.hypot(P[:, 0] - ctr[0], P[:, 2] - ctr[2])
    phi = np.arctan2(P[:, 2] - ctr[2], P[:, 0] - ctr[0])
    bins = np.clip(((phi + np.pi) / (2 * np.pi) * 180).astype(int), 0, 179)
    rmax = np.zeros(180)
    np.maximum.at(rmax, bins[up], d[up])
    rmax = np.maximum(nd.maximum_filter1d(rmax, 3, mode="wrap"), 1e-6)
    r = np.full((H, W), np.nan, np.float32)
    r[yy[up], xx[up]] = np.clip(d[up] / rmax[bins[up]], 0, 1)
    return r


def local_median_chroma(chroma, ok, size=31):
    """Mean chroma of the ok texels in a size x size window (a robust-enough stand-in for a median at this scale)."""
    w = nd.uniform_filter(ok.astype(np.float32), size)
    return np.stack([nd.uniform_filter(chroma[..., i] * ok, size) for i in range(3)], -1) / np.maximum(w, 1e-6)[..., None]


def tone(a, opt):
    alb = np.asarray(Image.open(a[0]).convert("RGB")).astype(np.float32)
    mesh = np.load(a[1])
    part_px = np.asarray(Image.open(a[2]).convert("L").resize(alb.shape[1::-1], Image.BILINEAR)).astype(np.float32) / 255
    out = Path(a[3])
    out.mkdir(parents=True, exist_ok=True)
    body = part_px < 0.5
    used = alb.sum(-1) > 0
    L = alb @ W709
    chroma = alb - L[..., None]
    R, G, B = alb[..., 0], alb[..., 1], alb[..., 2]
    blue_sat, brown = float(opt("--blue-sat", "0.55")), float(opt("--brown", "3"))
    bad_blue = body & used & ((B - np.maximum(R, G)) > blue_sat * (L + 8))
    bad_brown = body & used & (R - B > brown) & (R - G > brown)
    bad = nd.binary_dilation(bad_blue | bad_brown, iterations=1) & body & used
    good = body & used & ~bad
    fix = local_median_chroma(chroma, good)
    chroma = np.where(bad[..., None], fix, chroma)
    # body tone: luminance curve, chroma scaled
    g, k, kc = float(opt("--body-gamma", "0.9")), float(opt("--body-gain", "1.3")), float(opt("--body-chroma", "0.8"))
    Lb = 255 * k * np.power(np.clip(L, 0, 255) / 255, g)
    wb = 1 - part_px                         # soft edge between body and cap
    L2 = wb * Lb + (1 - wb) * L
    c2 = chroma * (wb * kc + (1 - wb))[..., None]
    new = L2[..., None] + c2 * np.where(L > 1, L2 / np.maximum(L, 1), 1)[..., None] ** 0.5
    pale = None
    if opt("--pale", None) is not None:
        # classic's body has pale grey highlight patches (in game L 150+): the body's brighter texels (luminance LO..HI, a
        # smoothstep) are lifted toward white by LIFT and lose DESAT of their chroma (paler, less blue)
        lo, hi, lift, desat = (float(x) for x in opt("--pale", "60,140,0.35,0.5").split(","))
        Ln0 = new @ W709
        sp = smoothstep(lo, hi, Ln0) * wb * (body & used)
        Lp = Ln0 + lift * sp * (255 - Ln0)
        cp = (new - Ln0[..., None]) * (1 - desat * sp)[..., None]
        new = Lp[..., None] + cp
        pale = [lo, hi, lift, desat]
    # cap centre
    top = float(opt("--top", "0.15"))
    r0, r1, lev = (float(x) for x in opt("--centre", "0.25,0.7,0.35").split(","))
    rr = cap_radius(mesh, part_px > 0.5, top)
    has = ~np.isnan(rr)
    fac = np.ones_like(L)
    fac[has] = lev + (1 - lev) * smoothstep(r0, r1, rr[has])
    new = new * fac[..., None]
    new = np.where(used[..., None], new, alb)
    Image.fromarray(np.clip(np.rint(new), 0, 255).astype(np.uint8)).save(out / "albedo_tone.png")
    Image.fromarray(np.where(has, np.rint(np.nan_to_num(rr) * 255), 0).astype(np.uint8)).save(out / "cap_radius.png")
    Ln = new @ W709
    bl = body & used
    capt = has
    rep = {"cleaned_blue": int(bad_blue.sum()), "cleaned_brown": int(bad_brown.sum()), "cleaned_total": int(bad.sum()),
           "body_gamma": g, "body_gain": k, "body_chroma": kc, "centre": [r0, r1, lev], "pale": pale,
           "blue_sat": blue_sat,
           "body_L_before": [round(float(x), 1) for x in np.percentile(L[bl], [10, 50, 90])],
           "body_L_after": [round(float(x), 1) for x in np.percentile(Ln[bl], [10, 50, 90])],
           "cap_top_L_by_radius_before": [round(float(L[capt & (rr >= lo) & (rr < lo + 0.2)].mean()), 1) for lo in (0, .2, .4, .6, .8)],
           "cap_top_L_by_radius_after": [round(float(Ln[capt & (rr >= lo) & (rr < lo + 0.2)].mean()), 1) for lo in (0, .2, .4, .6, .8)]}
    (out / "tone.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep))


def corpse(a, opt):
    alb = np.asarray(Image.open(a[0]).convert("RGB")).astype(np.float32)
    part = np.asarray(Image.open(a[1]).convert("L").resize(alb.shape[1::-1], Image.BILINEAR)) < 128
    dd, out = Path(a[2]), Path(a[3])
    out.mkdir(parents=True, exist_ok=True)
    px = []
    for f in sorted(dd.glob("d*_f*.png")):
        s = np.asarray(Image.open(f).convert("RGBA")).astype(np.float32)
        R, G, B, A = s[..., 0], s[..., 1], s[..., 2], s[..., 3]
        rim = (B >= 120) & (B - np.maximum(R, G) > 50)
        m = (A > 127) & ~rim & (B >= R - 1) & (B >= G - 6) & ((s[..., :3] @ W709) >= 10)
        px.append(s[m][:, :3])
    px = np.vstack(px)
    Lc = px @ W709
    level, spread, kc = float(opt("--level", "205")), float(opt("--spread", "0.45")), float(opt("--chroma", "1.5"))
    # classic's chroma by luminance (16 bins)
    edges = np.percentile(Lc, np.linspace(0, 100, 17))
    cbin = np.clip(np.searchsorted(edges, Lc) - 1, 0, 15)
    cmean = np.stack([(px[cbin == i] - Lc[cbin == i, None]).mean(0) if (cbin == i).any() else np.zeros(3) for i in range(16)])
    used = alb.sum(-1) > 0
    m = used & part
    L = alb @ W709
    rank = np.argsort(np.argsort(L[m])) / max(m.sum() - 1, 1)
    q = np.percentile(Lc, rank * 100)
    med = np.median(Lc)
    q2 = level + spread * (q - med)
    qb = np.clip(np.searchsorted(edges, q) - 1, 0, 15)
    col = q2[:, None] + kc * cmean[qb]
    new = alb.copy()
    new[m] = col
    # cap texels (not on the shell) and unused texels: the median colour, so a filtered miniature does not bleed dark
    medc = np.median(col, 0)
    new[~m] = medc
    Image.fromarray(np.clip(np.rint(new), 0, 255).astype(np.uint8)).save(out / "albedo_corpse.png")
    Ln = np.clip(new[m], 0, 255) @ W709
    rep = {"classic_px": int(len(px)), "classic_L_p10_50_90": [round(float(x), 1) for x in np.percentile(Lc, [10, 50, 90])],
           "classic_rgb_mean": [round(float(x), 1) for x in px.mean(0)], "level": level, "spread": spread,
           "corpse_L_p10_50_90": [round(float(x), 1) for x in np.percentile(Ln, [10, 50, 90])],
           "corpse_rgb_median": [round(float(x), 1) for x in medc]}
    (out / "corpse.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep))


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("tone", "corpse"):
        print(__doc__)
        return 1
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    pos = [x for i, x in enumerate(a[1:], 1) if not x.startswith("--") and not a[i - 1].startswith("--")]
    (tone if a[0] == "tone" else corpse)(pos, opt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
