"""Stage 3 finish: map a part's albedo levels so that under D2R's light the part shows classic's darks AND highlights.

  venv python s3_levels.py <overlay dir> --classic <frames dir> --part <part.png> [--strip 0.125]
        [--modes nu,wl,a1] [--gain 3.75] [--gamma 1.6] [--knee 0.8] [--tint 0.89,0.96,1.13] [--chroma 1.0]
        [--orm-a 0] [--glow LO,HI,MAX] [--report <json>]

Why (round 9, Glowing Fungus): classic's body is mostly near-black with bright blue-white highlights. One gain, or a gamma
below 1 (round 8: 0.6), lifts the darks with the middle and gives an even grey; ORM alpha 255 (specular level, METHOD rule
10) adds an even sheen on top. Steps, for the body texels (live part of the atlas, not the part mask, not the corpse strip):
1. rank: each texel's luminance rank is mapped to the same quantile of classic's body pixels (the frames of --modes, below
   the cap), so the albedo has classic's distribution (its black share and its highlight share) and keeps its own detail order;
2. curve: L_alb = 255 * knee(gain * (L_classic / 255) ^ gamma). gamma > 1 is a contrast curve: darks stay dark, highlights
   rise. gain and gamma come from the game's light: if the game shows about k x albedo, pick them so k x L_alb at
   classic's p10/p50/p90 gives classic's in-game p10/p50/p90 (Fungus, Blood Moor night: k about 0.36). knee() is linear up
   to --knee and rolls off softly to 1, so the top keeps its order instead of clipping flat;
3. colour: classic's own colour per 16-level luminance bin, divided by the game light's tint (--tint, per channel, measured
   as in-game rgb / albedo rgb of an earlier run, normalised to mean 1), then scaled back to L_alb. --chroma scales the
   colour's distance from grey;
4. --orm-a: ORM alpha (specular level) on those texels (0 = matte);
5. --glow LO,HI,MAX: the body glow mask (vfx_glow_body) from the new albedo: smoothstep(LO..HI) of L_alb times MAX
   (0..255), so only the highlights are self-lit (a small emissive term the night light cannot take away).
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import d2r_texture as t  # noqa: E402

LUM = np.array([0.2126, 0.7152, 0.0722])


def pct(X):
    return [round(float(np.percentile(X, q)), 1) for q in (10, 25, 50, 75, 90)]


def classic_body(frames, modes):
    """classic's body pixels (opaque, not the cap rim, below the cap) of the given modes, all facings and frames."""
    from s5_corpsefit import rim_mask
    out = []
    for mode in modes:
        for p in sorted(glob.glob(str(Path(frames) / mode / "d*_f*.png"))):
            im = np.asarray(Image.open(p).convert("RGBA"))
            cap = rim_mask(im)
            body = (im[..., 3] > 0) & ~cap
            blue = im[..., 2].astype(int) - np.maximum(im[..., 0], im[..., 1]).astype(int)
            body &= ~((im[..., 2] >= 120) & (blue > 50))
            ys = np.nonzero(cap)[0]
            if len(ys):
                body[:ys.max() + 1] = False
            out.append(im[body][:, :3].astype(float))
    return np.vstack(out)


def knee(x, k):
    """linear to k, then a soft roll-off to 1."""
    x = np.asarray(x, float)
    if k >= 1:
        return np.clip(x, 0, 1)
    return np.where(x <= k, x, k + (1 - k) * np.tanh((x - k) / (1 - k)))


def level_map(L_tex, Lc, gain, gamma, kn):
    """texel luminance -> albedo luminance: rank to classic's quantile, then the contrast curve."""
    order = np.argsort(np.argsort(L_tex, kind="stable"), kind="stable")
    q = (order + 0.5) / len(L_tex)
    Ls = np.quantile(Lc, q)
    return 255 * knee(gain * (Ls / 255) ** gamma, kn), Ls


def colour_table(pix):
    """classic's mean colour / luminance per 16-level luminance bin (empty bins from their neighbours)."""
    L = pix @ LUM
    tab = np.full((16, 3), np.nan)
    for b in range(16):
        m = (L >= 16 * b) & (L < 16 * b + 16)
        if m.sum() >= 20:
            tab[b] = (pix[m] / np.maximum(L[m, None], 1)).mean(0)
    ok = ~np.isnan(tab[:, 0])
    for c in range(3):
        tab[~ok, c] = np.interp(np.nonzero(~ok)[0], np.nonzero(ok)[0], tab[ok, c])
    return tab


def main():
    a = sys.argv[1:]
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    ov = Path(a[0]) / "hd"
    name = opt("--name", "fungus")
    tex = next(ov.glob("character/enemy/mxl/m3d/%s" % name))
    ALB, ORM = tex / ("%s_alb.texture" % name), tex / ("%s_orm.texture" % name)
    s = float(opt("--strip", "0.125"))
    gain, gamma, kn = float(opt("--gain", "3.75")), float(opt("--gamma", "1.6")), float(opt("--knee", "0.8"))
    tint = np.array([float(x) for x in opt("--tint", "1,1,1").split(",")])
    tint = tint / tint.mean()
    chroma = float(opt("--chroma", "1.0"))
    rep = {"gain": gain, "gamma": gamma, "knee": kn, "tint": tint.round(3).tolist(), "chroma": chroma}

    fmt, w, h, lv = t.read_texture(ALB)[:4]
    nmip = len(lv)
    A = t.decode(fmt, w, h, lv[0]).astype(float)
    x0 = int(round(w * (1 - s)))
    import common
    part = common.squash_u(np.asarray(Image.open(opt("--part", "")).convert("L")).astype(np.uint8), s)
    part = np.asarray(Image.fromarray(part).resize((w, h), Image.NEAREST)) > 127
    body = np.zeros((h, w), bool)
    body[:, :x0] = True
    body &= (A[..., :3].sum(-1) > 3) & ~part

    pix = classic_body(opt("--classic", ""), opt("--modes", "nu,wl,a1").split(","))
    Lc = pix @ LUM
    rep["classic_L"] = pct(Lc)
    rep["classic_black"] = round(float((Lc < 12).mean()), 3)
    rep["classic_rgb"] = np.round(pix.mean(0), 1).tolist()

    X = A[body][:, :3]
    L0 = X @ LUM
    rep["before_L"], rep["before_rgb"] = pct(L0), np.round(X.mean(0), 1).tolist()
    L1, Ls = level_map(L0, Lc, gain, gamma, kn)
    tab = colour_table(pix)
    b = np.clip((Ls // 16).astype(int), 0, 15)
    col = tab[b] / tint                                  # classic's colour per bin, divided by the game light's tint
    col = 1 + chroma * (col - (col @ LUM)[:, None])      # luminance 1, chroma scaled
    col = col / np.maximum(col @ LUM, 1e-6)[:, None]
    Y = np.clip(L1[:, None] * col, 0, 255)
    A[body, :3] = Y
    LY = Y @ LUM
    rep["after_L"], rep["after_rgb"] = pct(LY), np.round(Y.mean(0), 1).tolist()
    rep["after_black"] = round(float((LY < 12).mean()), 3)
    rep["texels"] = int(body.sum())
    t.write_bc3(ALB, np.clip(np.rint(A), 0, 255).astype(np.uint8), mips=nmip)

    if "--orm-a" in a:
        fo, wo, ho, lo = t.read_texture(ORM)[:4]
        O = t.decode(fo, wo, ho, lo[0]).astype(float)
        bo = np.asarray(Image.fromarray(body.astype(np.uint8) * 255).resize((wo, ho), Image.NEAREST)) > 127
        rep["orm_before"] = np.round(O[bo].mean(0), 1).tolist()
        O[bo, 3] = float(opt("--orm-a", "0"))
        t.write_bc3(ORM, np.clip(np.rint(O), 0, 255).astype(np.uint8), mips=len(lo), linear=True)
        rep["orm_after"] = np.round(O[bo].mean(0), 1).tolist()

    if "--glow" in a:
        lo_, hi_, mx = [float(v) for v in opt("--glow", "").split(",")]
        MASK = next((Path(a[0]) / "hd").glob("vfx/textures/mxl/m3d/%s/%s_glow_body_mask.texture" % (name, name)))
        fm, wm, hm, lm = t.read_texture(MASK)[:4]
        M = t.decode(fm, wm, hm, lm[0]).astype(float)
        M = M[..., 0] if M.ndim == 3 else M
        Lfull = np.zeros((h, w))
        Lfull[body] = LY
        x = np.clip((Lfull - lo_) / max(hi_ - lo_, 1e-6), 0, 1)
        g = (x * x * (3 - 2 * x)) * mx * body
        g = np.asarray(Image.fromarray(g.astype(np.float32)).resize((wm, hm), Image.BILINEAR))
        rep["glow_before_mean"] = round(float(M.mean()), 2)
        t.write_bc4(MASK, np.clip(np.rint(g), 0, 255).astype(np.uint8), len(lm))
        rep["glow_after_mean"] = round(float(g.mean()), 2)
        rep["glow_share"] = round(float((g > 8).mean()), 4)

    print(json.dumps(rep))
    if "--report" in a:
        Path(opt("--report", "")).write_text(json.dumps(rep, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
